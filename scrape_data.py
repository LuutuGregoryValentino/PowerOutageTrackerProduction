import requests
from datetime import  datetime
from models import Outage, User, Notification
from geopy.geocoders import Nominatim
import math,time
import os,json
import smtplib
from email.message import EmailMessage

R = 6371
THRESHOLD_KM = 10
geolocator = Nominatim(user_agent="gregory_power_tracker_ug_contact_me_at_snowchildwolf@gmail.com")
APIFYURL = os.getenv("APIFYURL")

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
    # Create the list items with consistent styling
    outage_items_html = ""
    for outage in outage_details:
        outage_items_html += f"""
        <div style="padding: 15px; border-bottom: 1px solid #eeeeee;">
            <p style="margin: 0; color: #1F2A44; font-weight: bold;">📍 {outage['area']}</p>
            <p style="margin: 5px 0; font-size: 14px; color: #666666;">
                <strong>Date:</strong> {outage['date']} | <strong>Time:</strong> {outage['time']}
            </p>
            <p style="margin: 0; font-size: 12px; color: #DC3545;">
                Approx. {outage['distance_km']} km from your saved location
            </p>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: 'Segoe UI', Helvetica, Arial, sans-serif; background-color: #F0F2F5; margin: 0; padding: 20px;">
        <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            <tr>
                <td style="background-color: #1F2A44; padding: 20px; text-align: center;">
                    <h1 style="color: #F5B301; margin: 0; font-size: 24px;">⚡ Power Alert</h1>
                </td>
            </tr>
            <tr>
                <td style="padding: 30px;">
                    <p style="font-size: 16px; color: #333333;">Dear Customer,</p>
                    <p style="font-size: 14px; color: #555555; line-height: 1.6;">
                        Our system has detected a scheduled power outage within <strong>{THRESHOLD_KM} km</strong> of your saved coordinates.
                    </p>
                    
                    <div style="background-color: #FFF9F0; border-left: 4px solid #FF9800; padding: 10px 20px; margin: 20px 0;">
                        <h3 style="color: #FF9800; margin: 0; font-size: 16px;">Scheduled Interruptions:</h3>
                    </div>

                    {outage_items_html}

                    <div style="text-align: center; margin-top: 30px;">
                        <a href="https://uedcl-power-outage-tracker.onrender.com" style="background-color: #F5B301; color: #1F2A44; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">View Live Tracker</a>
                    </div>
                </td>
            </tr>
            <tr>
                <td style="background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #999999;">
                    <p>This is an automated alert based on UEDCL public data.</p>
                    <p>To manage your alerts or change your location, or to stop receiving warning emails <strong>log in to your profile.</strong></p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    msg = EmailMessage()
    msg['Subject'] = '⚡ URGENT: Power Outage Alert Near You'
    msg['From'] = f"Power Alert <{SENDER_EMAIL}>"
    msg['To'] = recipient_email
    msg.set_content('A power outage is scheduled near your area. Please enable HTML to view details.')
    msg.add_alternative(html_content, subtype='html')
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"SUCCESS: Alert sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"FAILURE: Email error for {recipient_email}: {e}")
        return False
    
def scrape_outage_data():
    outageDict= {}  #format = {district:{details dict}}
    with requests.Session() as s:
        response = s.get(APIFYURL, timeout=3000)
        if response.status_code == 200:
            a = json.loads(response.text)[1]["tables"][0]["data"]
            for j in a:
                date_time_raw = j["Date"].split(" ")
                outageDict[j["District"]] = {
                "Status": j["Status"],
                "Areas": j['Affected Areas'],
                "Date": date_time_raw[0],
                "Time": date_time_raw[1]
                }
            return outageDict
        else:
            return dict()
        
import time

def run_full_outage_pipeline(session, SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT):
    print("starting full ootage ppieline scrape save notify")
    
    is_factory = False
    if hasattr(session, '__call__'):
        managed_session = session()
        is_factory = True
    else:
        managed_session = session

    try:
        outage_data_dict = scrape_outage_data()
        
        if not outage_data_dict:
            print("No new data scraped. Stopping pipeline.")
            return
        
        managed_session.query(Outage).delete()
        
        newly_saved_outages = [] 

        for area, details in outage_data_dict.items():
            outage_date_obj = datetime.strptime(details['Date'], "%Y-%m-%d").date()
            outage_time_obj = datetime.strptime(details['Time'], "%H:%M").time()
            sub_areas_string = details["Areas"]
            lat, lon = None, None

            if area:
                try:
                    time.sleep(1) 
                    location = geolocator.geocode(f"{area}, Uganda")
                    if location:
                        lat = location.latitude
                        lon = location.longitude
                        print(f"Geocoded '{area}': ({lat},{lon})")
                except Exception as e:
                    print(f"Geocoding Error for {area}: {e}. Skipping coordinates.")

            new_outage = Outage(
                area=area,
                sub_areas=sub_areas_string,
                outage_date=outage_date_obj,
                outage_time=outage_time_obj,
                latitude=lat,
                longitude=lon
            )

            managed_session.add(new_outage)
            newly_saved_outages.append(new_outage)
        
        managed_session.commit() 
        print(f"Successfully scraped and saved {len(outage_data_dict)} records.")

        users = managed_session.query(User).filter(
            User.is_subscribed == True,
            User.latitude.isnot(None), 
            User.longitude.isnot(None)
        ).all()
        
        for user in users:
            proximate_outages = []

            for outage in newly_saved_outages:
                if not outage.latitude or not outage.longitude:
                    continue

                already_notified = managed_session.query(Notification).filter(
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
                            user_id=user.id,
                            outage_id=alert["id"],
                            sent_at=datetime.utcnow()
                        )
                        managed_session.add(new_notification)

                    managed_session.commit()
                    print(f"SUCCESS: Notification flags set for {user.email}.")

    except Exception as e:
        managed_session.rollback()
        print(f"ERROR in full pipeline: {e}")
    finally:
        if is_factory:
            managed_session.close()
        print("===> Full Pipeline Complete <===")

if __name__ == "__main__":
    scrape_outage_data()
    # print("Scraper module ready.")
