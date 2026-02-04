import requests
from bs4 import BeautifulSoup
from datetime import  datetime
from models import Outage, User, Notification
from geopy.geocoders import Nominatim
import math
# import os
import smtplib
from email.message import EmailMessage

R = 6371
THRESHOLD_KM = 20
geolocator = Nominatim(user_agent="power-outage-app-v1")


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculates the great-circle distance between two points 
    on the surface of a sphere (Earth) using the Haversine formula.
    Returns distance in kilometers.
    """
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Haversine formula components
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance

def send_outage_email(recipient_email, outage_details, SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT):
    outage_list_html = "<ul>"
    for outage in outage_details:
        # Note: Using 'area' for consistency, ensure this key is correct
        outage_list_html += f"<li>District: {outage['area']} (Approx. {outage['distance_km']}km away starting <strong>{outage['date']}</strong> at {outage['time']} )</li>"
    outage_list_html +='</ul>'

    html_content = f"""\
    <html>
        <body>
            <p>Dear Customer,</p>
            <p>This is an automated power outage alert. Your saved location is within <strong>{THRESHOLD_KM} km</strong> of a scheduled power interruption.</p>
            <p><strong>Affected Areas Near You:</strong></p>
            {outage_list_html}
            <p>Please prepare for the interruption. This alert is based on data provided by Uganda Electricity Distribution Company Limited (UEDCL).</p>
            <p>Thank you.</p>
        </body>
    </html>
    """
    msg = EmailMessage()
    msg['Subject'] = '⚡ URGENT: Scheduled Power Outage Alert Near Your Location'
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    msg.set_content('Your client does not support HTML emails. Please upgrade to view the alert.')
    msg.add_alternative(html_content, subtype='html')
    
    try:
        with smtplib.SMTP(SMTP_SERVER,SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL,SENDER_PASSWORD)
            server.send_message(msg)
        print(f"SUCCESS: Email sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"FAILURE: Could not send email to {recipient_email}. Error: {e}")
        return False

def scrape_outage_data():
    url="https://www.uedcl.co.ug/outage-alerts/"
    outageDict = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    data = requests.get(url,timeout=10,headers=headers)
    if data.status_code == 200:
        print("Request Successful!")
        soup = BeautifulSoup(data.text,"html.parser")
        outage_Table_container = soup.find("table")
        if not outage_Table_container:
            print("Couldn't find the required Table")
            return []

        for row in outage_Table_container.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) > 3:
                district = cells[1].string
                status = cells[2].string
                dateTime = cells[0].string.split(" ")
                affected_areas = cells[3].get_text(strip=True)
                
                outageDict[district] = {
                    "Status":status,
                    "Areas":affected_areas,
                    "Date": dateTime[0],
                    "Time":dateTime[1]
                }
        return outageDict
    else:
        print(f"Request Failed: {data.status_code}\nTry again later")
        return None

def run_full_outage_pipeline(session,SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT):
    print("starting full ootage ppieline scrape save notify")
    # session = Session()

    try:
        outage_data_dict = scrape_outage_data()
        if not outage_data_dict:
            print("No new data scraped. Stopping pipeline.")
            return

        session.query(Outage).delete()
        
        newly_saved_outages = [] 

        for area, details in outage_data_dict.items():
            outage_date_obj = datetime.strptime(details['Date'], "%Y-%m-%d").date()
            outage_time_obj = datetime.strptime(details['Time'], "%H:%M").time()
            sub_areas_string = details["Areas"]
            lat = None
            lon = None

            if area:
                try:
                    location = geolocator.geocode(f"{area}, Uganda")
                    if location:
                        lat = location.latitude
                        lon = location.longitude
                        print(f"Geocoded '{area}': ({lat},{lon})")
                except Exception as e:
                    print(f"Geocoding Error for {area}: {e}. Skipping coordinates.")

            new_outage = Outage(
                area = area,
                sub_areas = sub_areas_string,
                outage_date = outage_date_obj,
                outage_time = outage_time_obj,
                latitude = lat,
                longitude = lon
            )

            session.add(new_outage)
            newly_saved_outages.append(new_outage)
        
        session.commit() 
        print(f"Successfully scraped and saved {len(outage_data_dict)} records.")


        users = session.query(User).filter(
            User.is_subscribed == True,
            User.latitude.isnot(None), 
            User.longitude.isnot(None)
        ).all()
        
        for user in users:
            proximate_outages = []

            for outage in newly_saved_outages:
                if not outage.latitude or not outage.longitude:
                    continue

                already_notified = session.query(Notification).filter( #prevents spamming emails
                    Notification.user_id == user.id,
                    Notification.outage_id == outage.id
                ).first()

                if already_notified:
                    continue

                distance = haversine_distance(user.latitude, user.longitude, outage.latitude, outage.longitude)

                if distance <= THRESHOLD_KM:
                    proximate_outages.append({
                        "id": outage.id,
                        "area": outage.area,
                        "distance_km": round(distance, 2),
                        # Ensure date/time format consistency with the email function
                        "date": outage.outage_date.isoformat(), 
                        "time": outage.outage_time.isoformat(),
                    })
            
            if proximate_outages:
                print(f"Attempting to alert user {user.email} about {len(proximate_outages)} outage(s)...")
                
                email_sent_successfully = send_outage_email(
                    user.email, 
                    proximate_outages, 
                    SENDER_EMAIL, 
                    SENDER_PASSWORD, 
                    SMTP_SERVER, 
                    SMTP_PORT
                )

                if email_sent_successfully:
                    for alert in proximate_outages:
                        new_notification = Notification(
                            user_id = user.id,
                            outage_id = alert["id"],
                            sent_at = datetime.utcnow()
                        )
                        session.add(new_notification)

                    # Commit notification flags only after successful email send
                    session.commit()
                    print(f"SUCCESS: Notification flags set for {len(proximate_outages)} outages for user {user.email}.")

    except Exception as e:
        session.rollback()
        print(f"ERROR in full pipeline: {e}")
    finally:
        session.close()
        print("===> Full Pipeline Complete <===")


if __name__ == "__main__":
   
    print("Scraper module ready.")