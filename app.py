
from flask import Flask ,jsonify, request,redirect,url_for,session, render_template
from flask_dance.contrib.google import make_google_blueprint ,google
from flask_cors import CORS
from scrape_data import run_full_outage_pipeline
from models import Outage, User,Base
from flask_apscheduler import APScheduler
from dotenv import load_dotenv
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import math,os

THRESHOLD_KM = 20

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
    
    distance = 6371 * c
    return distance



load_dotenv()
app = Flask(__name__)
CORS(app)

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT')) 
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
DB_URL = os.getenv("DATABASE_URL")


if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

# 3. Fallback to your local sqlite if no URL is found
final_db_url = DB_URL or 'sqlite:///outages.db'

# 4. Create the engine
engine = create_engine(final_db_url)

# 5. Create the tables (This tells Postgres/SQLite to build the columns)
Base.metadata.create_all(engine)

# 6. Create the Session factory
Session = sessionmaker(bind=engine)





app.config['SCHEDULER_JOBDEFAULTS']={
    "coalesce":True,
    "max_instances":1
}
scheduler = APScheduler()
scheduler.init_app(app)

scheduler.add_job(
    id='full_pipeline_job',
    func=run_full_outage_pipeline, 
    kwargs={
        "session":Session(),
        'SENDER_EMAIL': SENDER_EMAIL,
        'SENDER_PASSWORD': SENDER_PASSWORD,
        'SMTP_SERVER': SMTP_SERVER,
        'SMTP_PORT': SMTP_PORT
    },
    trigger='interval',
    hours=24, 
    # seconds=60, # For testing purposes
    misfire_grace_time=3600*36
)


GOOGLE_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

google_blueprint = make_google_blueprint(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    scope=["openid", "email", "profile"], 
    redirect_to='google_authorized' 
)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

app.register_blueprint(google_blueprint, url_prefix="/login")

@app.route('/')
def index():
    user_email = session.get('email') 
    return render_template('index.html', user_email=user_email)

@app.route('/api/outages')
def get_outages():
    session =Session()
    try:
        outages = session.query(Outage).all() #returns list of Outage objects
        
        outages_list = []
        for outage in outages:
            sub_areas_list = outage.sub_areas.split(",") if outage.sub_areas else []

            outages_list.append({
                "id": outage.id,
                "area": outage.area,
                "sub_areas" : sub_areas_list,
                # "status": outage.
                "date" : outage.outage_date.isoformat() if outage.outage_date else None,
                "time" : outage.outage_time.isoformat() if outage.outage_time else None,
            })

        return jsonify(outages_list)

    except Exception as e:
        print(f"Database Error: {e}")
        return jsonify({'error':'Couldnt retrieve outage data.'}), 500
    finally:
        session.close()

@app.route("/api/register", methods = ['POST'])
def register_user():
    data = request.get_json() #gets json data form front end

    required_fields = ['email', 'password', 'latitude', 'longitude']

    for field in required_fields:
        if field not in data:
            return jsonify({"message": f"Missing required field: {field}"}), 400

    email = data['email']
    password = data['password']
    latitude = data['latitude']
    longitude = data['longitude']

    session = Session()

    try:
        existing_user = session.query(User).filter_by(email = email).first()
        if existing_user:
            return jsonify({"message":"User withthis email already exists."}), 409 #409 = Confilct

        new_user = User(
            email = email,
            latitude = latitude,
            longitude = longitude
        )
        new_user.set_password(password)

        session.add(new_user)
        session.commit()

        return jsonify({"message":"Registration Successful!",'user_id':new_user.id}), 201
    
    except IntegrityError: #oomly when non unique email is used
        session.rollback()
        return jsonify({"status": "ERROR", "message": "Email already registered. Please Try a different email."}), 409 #conflict
    
    except Exception as e:
        session.rollback()
        print(f"Registration Error: {e}")
        return jsonify({"status": "ERROR", "message": "Internal server error during registration."}), 500
    finally:
        session.close()

@app.route('/api/check_outage',methods=["GET"])
def check_outage_query():
    user_lat= request.args.get('lat', type=float)
    user_lon = request.args.get('lon', type=float)
    
    if not user_lat or  not user_lon :
        return jsonify({"status": "ERROR","message": "Missing latitude (lat) or longitude (lon) query parameters."}), 400
    try:
        user_lat = float(user_lat)
        user_lon = float(user_lon)
    except ValueError:
        return jsonify({"status": "ERROR", "message": "Latitude and longitude must be valid numbers."}), 400

    session = Session()
    proximate_outages = []

    try:
        outages = session.query(Outage).all()
        
        for outage in outages:
            sub_areas_list = outage.sub_areas.split(', ') if outage.sub_areas else []

            if outage.latitude is None or outage.longitude is None:
                    continue

            outage_lat = outage.latitude
            outage_lon = outage.longitude

            if not isinstance(outage_lat, (int, float)) or not isinstance(outage_lon, (int, float)):
                 print(f"Skipping outage {outage.id}: Invalid coordinates defined in simulation.")
                 continue

            distance = haversine_distance(user_lat, user_lon, outage_lat, outage_lon)
            print(distance)
            if distance <= THRESHOLD_KM:
                proximate_outages.append({
                    "area": outage.area,
                    "sub_areas": sub_areas_list,
                    "date": outage.outage_date.isoformat() if outage.outage_date else None,
                    "time": outage.outage_time.isoformat() if outage.outage_time else None,
                    "distance_km": round(distance, 2)
                })
            # print("out of for loop")
        
        if proximate_outages:
            response_data = {
            "status": "ALERT",
            "message": f"Found {len(proximate_outages)} scheduled outage(s) within {THRESHOLD_KM} km of your location.",
            "outages": proximate_outages
            }
            return jsonify(response_data), 200
        else:
            response_data = {
            "status": "CLEAR",
            "message": "No scheduled outages found near your location."
            }
            return jsonify(response_data), 200

    except Exception as e:
        print(f"Error in making outage data query: {e}") 
        return jsonify({"status": "ERROR", "message": "Internal error during outage check. See server console for details."}), 500
        
    finally:
        session.close()

@app.route("/google/authorized")
def google_authorized():
    if not google.authorized:
        return redirect(url_for("google.login"))
    
    try:
        resp = google.get("/oauth2/v2/userinfo")
        if resp.ok:
            user_info = resp.json()
            email = user_info["email"]
            full_name = user_info.get("name") 
        else:
            return redirect(url_for("register"))
    except Exception as e:
        print(f"Failed to fethc user inof form google: {e}")
        return jsonify({"status":"ERROR","message":"Failed to retrieve user data form google."}), 500
    
    session_db= Session()

    try:
        user = session_db.query(User).filter_by(email=email).first()
        if user is None:
            new_user = User(
                email=email,
                is_subscribed = False,
                name= full_name
            )
            session_db.add(new_user)
            session_db.commit()

            user = new_user
            print(f"New user created: {email}, pending setup: {full_name}")

        else:
            session['user_name'] = user.name if user.name else user.email
            print(f"Existing user logged in: {user.email}")

        session["user_id"] = user.id
        session['email'] = user.email
        session['user_name'] = user.name if user.name else user.email

        if user.latitude is None or user.longitude is None:
            return redirect(url_for("setup_location"))
        else:
            return redirect(url_for("index"))    
        

    except Exception as e:
        session_db.rollback()
        print(f"Database error during Google login: {e}")
        return jsonify({"status": "ERROR", "message": "Internal database error during login."}), 500
    
    finally:
        session_db.close()
    
@app.route('/setup_location', methods=['GET', 'POST'])
def setup_location():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    session_db = Session()
    try:
        user = session_db.query(User).filter_by(id=session['user_id']).one()

        if request.method == 'POST':
            lat = request.json.get('latitude')
            lon = request.json.get('longitude')

            phone =  request.json.get("phone_number")
            is_subscribed_str = request.json.get("is_subscribed")

            if isinstance(is_subscribed_str, bool):
                is_subscribed = is_subscribed_str
            elif isinstance(is_subscribed_str, str):
                is_subscribed = is_subscribed_str.lower() == 'true'
            else:
                    is_subscribed = False
            
            if lat and lon:
                user.latitude = float(lat)
                user.longitude = float(lon)

                user.phone_number = phone if phone else None
                user.is_subscribed = is_subscribed


            
                session_db.commit()
                return jsonify({"status": "SUCCESS", "message": "Location and Preferences saved!"}), 200
            else:
                return jsonify({"status": "ERROR", "message": "Missing location data."}), 400

        return render_template('setup_location.html') 

    except NoResultFound:
        return redirect(url_for('logout'))
    except Exception as e:
        session_db.rollback()
        print(f"Location setup error: {e}")
        return jsonify({"status": "ERROR", "message": "Internal error."}), 500
    finally:
        session_db.close()

@app.route("/login")
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    return redirect(url_for("google.login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route('/profile', methods=['GET', 'POST'])
def profile_management():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    session_db = Session()
    try:
        user = session_db.query(User).filter_by(id=session['user_id']).one()
        print(user)
        
        if request.method == 'POST':
            data = request.json
            user.is_subscribed = data.get('is_subscribed', user.is_subscribed)
            phone = data.get('phone_number')
            user.phone_number = phone if phone else None
            lat = data.get('latitude')
            lon = data.get('longitude')
            if lat is not None and lon is not None:
                user.latitude = float(lat)
                user.longitude = float(lon)
            
            session_db.commit()
            
            session['is_subscribed'] = user.is_subscribed

            return jsonify({"status": "SUCCESS", "message": "Profile updated successfully."}), 200

        return render_template('profile_management.html', 
                               user=user, 
                               is_subscribed=user.is_subscribed) 
    except NoResultFound:
        return redirect(url_for('logout'))
    except Exception as e:
        session_db.rollback()
        print(f"Profile management error: {e}")
        return jsonify({"status": "ERROR", "message": f"Internal error.{e}"}), 500
    finally:
        session_db.close()

@app.route('/delete_account', methods=['POST'])

def delete_account():
    if 'user_id' not in session:
        return jsonify({"status": "ERROR", "message": "Not logged in"}), 401

    session_db = Session()
    try:
        user = session_db.query(User).filter_by(id=session['user_id']).one()
        
        session_db.delete(user)
        session_db.commit()
        
        session.clear()

        return jsonify({"status": "SUCCESS", "message": "Account deleted successfully."}), 200

    except NoResultFound:
        session.clear()
        return jsonify({"status": "ERROR", "message": "User not found."}), 404
    except Exception as e:
        session_db.rollback()
        print(f"Account deletion error: {e}")
        return jsonify({"status": "ERROR", "message": "Internal error."}), 500
    finally:
        session_db.close()


run_full_outage_pipeline(
        session=Session(),
        SENDER_EMAIL= SENDER_EMAIL,
        SENDER_PASSWORD= SENDER_PASSWORD,
        SMTP_SERVER= SMTP_SERVER,
        SMTP_PORT=SMTP_PORT)
scheduler.start()


if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")