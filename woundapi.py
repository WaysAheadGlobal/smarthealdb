from flask import Flask, request, jsonify, send_from_directory, url_for
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pymysql
import jwt
import random
import string
import datetime
import os
import uuid
from dotenv import load_dotenv
from twilio.rest import Client
import requests
from werkzeug.utils import secure_filename
load_dotenv()
app = Flask(__name__, static_url_path='/static', static_folder='uploads')
# Database credentials
DB_HOST = os.getenv('host')
DB_DATABASE = os.getenv('db')
DB_USERNAME = os.getenv('username')
DB_PASSWORD = os.getenv('psswd')
DATABASE_URL = f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}/{DB_DATABASE}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

account_sid = os.getenv('acc_sid')
auth_token = os.getenv('auth_token')
twilio_number = os.getenv('tn')

JWT_SECRET_KEY = 'CkOPcOppyh31sQcisbyOM3RKD4C2G7SzQmuG5LePt9XBarsxgjm0fc7uOECcqoGm'

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
BASE_URL = 'https://api.smartheal.waysdatalabs.com'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Utility function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_session_id():
    return str(uuid.uuid4())

def generate_license_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def generate_patient_id():
    with Session() as session:
        result = session.execute(text("SELECT MAX(id) FROM patients")).fetchone()
        last_id = result[0] if result[0] is not None else 0  # Handle the case when the table is empty
        prefix = "AB"  # Your 2 characters prefix
        formatted_id = f"{prefix}000{last_id + 1}"
        return formatted_id

@app.route('/send_email', methods=['POST'])
def add_data():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    c_code = data.get('c_code')
    phone = data.get('phone')

    if not (name and email and c_code and phone):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Check if email or phone already exists
            query = text("SELECT email, phone FROM organisations WHERE email = :email OR phone = :phone")
            existing_user = session.execute(query, {'email': email, 'phone': phone}).fetchone()

            if existing_user:
                return jsonify({'error': 'Email or phone already exists. Please login.'}), 401
            else:
                # Generate UUID for session
                uuid = generate_session_id()
                # Generate license key
                license_key = generate_license_key()

                # Send email with license key
                email_payload = {
                    'Recipient': email,
                    'Subject': 'License key for SmartHeal',
                    'Body': f'Your license key is: {license_key}',
                    'ApiKey': '6A7339A3-E70B-4A8D-AA23-0264125F4959'
                }

                email_response = requests.post(
                    'https://api.waysdatalabs.com/api/EmailSender/SendMail',
                    headers={},
                    data=email_payload
                )

                if email_response.status_code == 200:
                    return jsonify({'message': 'License key sent to email successfully', 'license_key': license_key}), 200
                else:
                    return jsonify({'error': 'Failed to send email'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/verify_license_key', methods=['POST'])
def verify_license_key():
    data = request.json
    email = data.get('email')
    license_key = data.get('license_key')

    if not (email and license_key):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("SELECT licence_key FROM organisations WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()
            if result and result.licence_key == license_key:
                # Generate JWT token
                token = jwt.encode({'email': email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'message': 'License key verified successfully', 'token': token}), 200
            else:
                return jsonify({'error': 'Invalid license key'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create_pin', methods=['POST'])
def create_pin():
    data = request.json
    license_key = data.get('license_key')
    email= data.get('email')
    pin = data.get('pin')
    if not pin:
        return jsonify({'error': 'Missing required fields'}), 401

    # Set created_at, updated_at, and scheduled_date
    created_at = datetime.datetime.utcnow() 
    updated_at = datetime.datetime.utcnow()
    
    try:
        with Session() as session:
            token = jwt.encode({'email': email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)}, JWT_SECRET_KEY, algorithm='HS256')
            query = text("INSERT INTO organisations (name, email, c_code, phone, uuid, licence_key, pin, created_at, updated_at) VALUES (:name, :email, :c_code, :phone, :uuid, :license_key, :pin, :created_at, :updated_at)")
            session.execute(query, {
                'name': data.get('name'),
                'email': email,
                'c_code': data.get('c_code'),
                'phone': data.get('phone'),
                'uuid': generate_session_id(),
                'license_key': license_key,
                'pin': pin,
                'created_at': created_at,
                'updated_at': updated_at
            })
            session.commit()
        return jsonify({'message': 'PIN created and data saved successfully', 'token': token}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/fetch_data', methods=['POST'])
def fetch_name_phone():
    try:
        data = request.get_json()
        email = data.get('email') if data else None
    except Exception as e:
        return jsonify({'error': 'Invalid JSON input'}), 400

    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401

    if not email:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Fetch only name and phone for the specified email
            query = text("SELECT name, phone FROM organisations WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchall()
            # Convert rows to list of dictionaries
            result_dicts = [{'name': row[0], 'phone': row[1]} for row in result]
            return jsonify(result_dicts), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to save department and location
@app.route('/save_additional_data', methods=['POST'])
def save_department_location():
    data = request.json
    department = data.get('department')
    #category = data.get('category')
    location = data.get('location') 
    email = data.get('email')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not (department and location and latitude and longitude):
        return jsonify({'error': 'Missing required fields'}), 400
    
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error':'Invalid Token'}), 401

    try:
        with Session() as session:
            query = text("UPDATE organisations SET departments = :department, location = :location, latitude = :latitude, longitude = :longitude WHERE email = :email;")
            session.execute(query, {'department': department, 'location': location, 'latitude': latitude, 'longitude': longitude, 'email': email})
            session.commit()
        return jsonify({'message': 'Department, location, latitude, and longitude saved successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API endpoint to add wound details
@app.route('/add_wound_details', methods=['POST'])
def add_wound_details():
    # Get the Authorization header
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401

    # Get the data from the request
    data = request.json
    length = data.get('length')
    breadth = data.get('breadth')
    depth = data.get('depth')
    area = data.get('area')
    moisture = data.get('moisture')
    wound_location = data.get('wound_location')
    tissue = data.get('tissue')
    exudate = data.get('exudate')
    periwound = data.get('periwound')
    periwound_type = data.get('periwound_type')
    patient_id = data.get('patient_id') 
    type = data.get('type')
    category = data.get('category')
    edge = data.get('edge')
    infection = data.get('infection')
    last_dressing_date = data.get('last_dressing_date')

    if not (length and breadth and depth and area and moisture):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("UPDATE wounds SET height = :length, width = :breadth, depth = :depth, area = :area, moisture = :moisture, position = :wound_location, tissue = :tissue, exudate = :exudate, periwound = :periwound, periwound_type = :periwound_type, type = :type, category = :category, edges = :edge, infection = :infection, last_dressing = :last_dressing_date WHERE patient_id = :patient_id;")
            session.execute(query, {'length': length, 'breadth': breadth, 'depth': depth, 'area': area, 'moisture': moisture, 'wound_location': wound_location, 'tissue': tissue, 'exudate': exudate, 'periwound': periwound, 'periwound_type': periwound_type, 'type': type, 'category': category, 'edge': edge, 'infection': infection, 'last_dressing_date': last_dressing_date, 'patient_id': patient_id})
            session.commit()
            return jsonify({'message': 'Wound details added successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_all_patient_details', methods=['GET'])
def get_all_patient_details():
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401

    try:
        data = request.get_json()
        email = data.get('email') if data else None

        if not email:
            return jsonify({'error': 'Missing required fields'}), 400

        with Session() as session:
            query = text("SELECT * FROM patients WHERE email = :email")
            patient_details = session.execute(query, {'email': email}).fetchall()
            # Convert rows to list of dictionaries using _mapping attribute
            patient_dicts = [dict(row._mapping) for row in patient_details]
            return jsonify({'patient_details': patient_dicts}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    

@app.route('/add_patient', methods=['POST'])
def add_patient():
    # Get data from request
    data = request.json
    name = data.get('name')
    dob = data.get('dob')
    gender = data.get('gender')
    age = data.get('age')
    height = data.get('height')
    weight = data.get('weight')
    email = data.get('email')
    doctor = data.get('doctor')
    patient_id = generate_patient_id()
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error':'Invalid Token'}), 401
    
    # Set created_at, updated_at, and scheduled_date
    created_at = datetime.datetime.utcnow() 
    updated_at = datetime.datetime.utcnow()
    scheduled_date = datetime.datetime.utcnow()  # Set this appropriately as per your application logic


    try:
        with Session() as session:
            uuid = generate_session_id()
            pat_query = text("INSERT INTO patients (name, dob, gender, age, height, weight, email, doctor, uuid, patient_id, created_at, updated_at, scheduled_date) VALUES (:name, :dob, :gender, :age, :height, :weight, :email, :doctor, :uuid, :patient_id, :created_at, :updated_at, :scheduled_date)")
            session.execute(pat_query, {'name': name, 'dob': dob, 'gender': gender, 'age': age, 'height': height, 'weight': weight, 'email': email, 'doctor': doctor, 'uuid': uuid, 'patient_id': patient_id, 'created_at': created_at, 'updated_at': updated_at, 'scheduled_date': scheduled_date})
            wound_query = text("INSERT INTO wounds ( uuid, patient_id, created_at, updated_at) VALUES (:uuid, :patient_id, :created_at, :updated_at)")
            session.execute(wound_query, {'uuid': uuid, 'patient_id': patient_id,  'created_at': created_at, 'updated_at': updated_at})
            # Commit the transaction to insert data into the database
            session.commit()
        return jsonify({'message': 'Patient added successfully', 'patient_id': patient_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/search_patient', methods=['GET'])
def search_patient():
    auth_header = request.headers.get('Authorization')

    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    token = auth_header.split(' ')[1]

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid or missing JSON data'}), 400

    name = data.get('name')
    if not name:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("SELECT * FROM patients WHERE name = :name")
            patients = session.execute(query, {'name': name}).fetchall()
            
            if not patients:
                return jsonify({'message': 'No patients found with this name'}), 404
            
            # Convert rows to list of dictionaries
            patients_dicts = [dict(row._mapping) for row in patients]

            return jsonify({'patients': patients_dicts}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/generate_prescription', methods=['GET'])
def generate_prescription():
    auth_header = request.headers.get('Authorization')

    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    token = auth_header.split(' ')[1]

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    patient_id = data.get('patient_id')
    
    if not patient_id:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Fetch patient details
            patient_query = text("SELECT * FROM patients WHERE patient_id = :patient_id ")
            patient = session.execute(patient_query, {'patient_id': patient_id}).fetchone()
            if not patient:
                return jsonify({'message': 'No patient found with this ID'}), 404

            # Fetch wound details
            wound_query = text("SELECT * FROM patients WHERE patient_id = :patient_id ")
            wounds = session.execute(wound_query, {'patient_id': patient_id}).fetchall()

            # Determine wound dimension category based on area
            wound_category = []
            for wound in wounds:
                area = wound.height * wound.width
                if area <= 5:
                    dimension = 'Small'
                elif 5 < area <= 20:
                    dimension = 'Medium'
                else:
                    dimension = 'Large'
                wound_category.append((wound.wound_type, dimension))

            # Fetch medications for the wounds
            medication_details = []
            for wound_type, dimension in wound_category:
                medication_query = """
                SELECT * FROM WoundMedications
                WHERE WoundType = :WoundType AND WoundDimensions = :WoundDimensions
                """
                medications = session.execute(medication_query, {'wound_type': wound_type, 'dimension': dimension}).fetchall()
                medication_details.extend(medications)

            prescription = {
                'patient_details': patient.to_dict(),
                'wound_details': [w.to_dict() for w in wounds],
                'medication_details': [m.to_dict() for m in medication_details]
            }

            return jsonify({'prescription': prescription}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/verify_pin', methods=['POST'])
def verify_pin():
    data = request.json
    email = data.get('email')
    pin = data.get('pin')

    if not (email and pin):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Query to verify the pin
            query = text("SELECT pin FROM organisations WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                if result.pin == pin:  # Using attribute access instead of dictionary-style indexing
                    return jsonify({'message': 'Pin verified successfully'}), 200
                else:
                    return jsonify({'error': 'Invalid pin'}), 400
            else:
                return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')

    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400

    try:
        with Session() as session:
            # Fetch professional details from the database
            query = text("SELECT * FROM organisations WHERE phone = :phone")
            organisation = session.execute(query, {'phone': phone}).fetchone()

            if organisation:
                phone_with_code = organisation.c_code + organisation.phone
                #otp = generate_otp()
                otp="1234"
                #send_sms(phone_with_code, otp)

                # Update OTP details in database
                updated_at = datetime.datetime.utcnow()
                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
                update_otp_in_database(session, phone, otp, expiry_time, updated_at)
                
                token = jwt.encode({'email': organisation.email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'status': 200, 'message': 'OTP Sent on mobile.', 'token': token, 'otp': otp, 'email': organisation.email, 'name': organisation.name, 'pin': organisation.pin}), 200
            else:
                return jsonify({'status': 0, 'message': 'OOPS! Phone Does Not Exist!'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def send_sms(phone, otp):
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=f"Your verification code is: {otp}. Don't share this code with anyone; our employees will never ask for the code.",
        from_=twilio_number,
        to=phone
    )


def generate_otp():
    return str(random.randint(1000, 9999))


def update_otp_in_database(session, phone, otp, expiry_time, updated_at):
    try:
        # Query to update OTP details
        query = text("UPDATE organisations SET otp= :otp, otp_expiry= :expiry_time, updated_at = :updated_at WHERE phone= :phone")
        session.execute(query, {'otp': otp, 'expiry_time': expiry_time, 'phone': phone, 'updated_at': updated_at})
        session.commit()
    except Exception as e:
        return str(e)



@app.route('/med_send_email', methods=['POST'])
def med_add_data():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    c_code = data.get('c_code')
    phone = data.get('phone')

    if not (name and email and c_code and phone):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Check if email or phone already exists
            query = text("SELECT email, phone FROM users WHERE email = :email OR phone = :phone")
            existing_user = session.execute(query, {'email': email, 'phone': phone}).fetchone()
            if existing_user:
                return jsonify({'error': 'Email or phone already exists. Please login.'}), 401
            else:
                # Generate UUID for session
                uuid = generate_session_id()
                # Generate license key
                license_key = generate_license_key()

                # Send email with license key
                email_payload = {
                    'Recipient': email,
                    'Subject': 'License key for SmartHeal',
                    'Body': f'Your license key is: {license_key}',
                    'ApiKey': '6A7339A3-E70B-4A8D-AA23-0264125F4959'
                }

                email_response = requests.post(
                    'https://api.waysdatalabs.com/api/EmailSender/SendMail',
                    headers={},
                    data=email_payload
                )

                if email_response.status_code == 200:
                    return jsonify({'message': 'License key sent to email successfully', 'license_key': license_key}), 200
                else:
                    return jsonify({'error': 'Failed to send email'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/med_verify_license_key', methods=['POST'])
def med_verify_license_key():
    data = request.json
    email = data.get('email')
    license_key = data.get('license_key')

    if not (email and license_key):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("SELECT licence_key FROM users WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()
            if result and result.licence_key == license_key:
                # Generate JWT token
                token = jwt.encode({'email': email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'message': 'License key verified successfully', 'token': token}), 200
            else:
                return jsonify({'error': 'Invalid license key'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/med_create_pin', methods=['POST'])
def med_create_pin():
    data = request.json
    license_key = data.get('license_key')
    email= data.get('email')
    pin = data.get('pin')
    if not pin:
        return jsonify({'error': 'Missing required fields'}), 401
    # Set created_at, updated_at, and scheduled_date
    created_at = datetime.datetime.utcnow() 
    updated_at = datetime.datetime.utcnow()
    try:
        with Session() as session:
            token = jwt.encode({'email': email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)}, JWT_SECRET_KEY, algorithm='HS256')
            query = text("INSERT INTO users (name, email, c_code, phone, uuid, licence_key, pin, created_at, updated_at) VALUES (:name, :email, :c_code, :phone, :uuid, :license_key, :pin, :created_at, :updated_at)")
            session.execute(query, {
                'name': data.get('name'),
                'email': email,
                'c_code': data.get('c_code'),
                'phone': data.get('phone'),
                'uuid': generate_session_id(),
                'license_key': license_key,
                'pin': pin,
                'created_at': created_at,
                'updated_at': updated_at
                
            })
            session.commit()
        return jsonify({'message': 'PIN created and data saved successfully', 'token': token}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/med_fetch_data', methods=['POST'])
def med_fetch_name_phone():
    try:
        data = request.get_json()
        email = data.get('email') if data else None
    except Exception as e:
        return jsonify({'error': 'Invalid JSON input'}), 400

    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401

    if not email:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Fetch only name and phone for the specified email
            query = text("SELECT name, phone FROM users WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchall()
            # Convert rows to list of dictionaries
            result_dicts = [{'name': row[0], 'phone': row[1]} for row in result]
            return jsonify(result_dicts), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to save department and location
@app.route('/save_med_data', methods=['POST'])
def med_save_department_location():
    data = request.json
    speciality = data.get('speciality')
    location = data.get('location')
    email = data.get('email')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    org = data.get('org')
    designation = data.get('designation')

    if not (speciality, location, latitude, longitude, org and email):
        return jsonify({'error': 'Missing required fields'}), 400
    
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error':'Invalid Token'}), 401

    try:
        with Session() as session:
            query = text("UPDATE users SET speciality = :speciality, location = :location, latitude = :latitude, longitude = :longitude, org = :org, designation = :designation WHERE email = :email;")
            session.execute(query, {'speciality': speciality, 'location': location, 'latitude': latitude, 'longitude': longitude, 'org': org, 'designation': designation, 'email': email})
            session.commit()
        return jsonify({'message': 'Speciality, location, organisation and designation saved successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/med_verify_pin', methods=['POST'])
def med_verify_pin():
    data = request.json
    email = data.get('email')
    pin = data.get('pin')

    if not (email and pin):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Query to verify the pin
            query = text("SELECT pin FROM users WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                if result.pin == pin:  # Using attribute access instead of dictionary-style indexing
                    return jsonify({'message': 'Pin verified successfully'}), 200
                else:
                    return jsonify({'error': 'Invalid pin'}), 400
            else:
                return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/med_send_otp', methods=['POST'])
def med_send_otp():
    data = request.json
    phone = data.get('phone')

    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400

    try:
        with Session() as session:
            # Fetch professional details from the database
            query = text("SELECT * FROM users WHERE phone = :phone")
            user = session.execute(query, {'phone': phone}).fetchone()

            if user:
                phone_with_code = user.c_code + user.phone
                #otp = generate_otp()
                otp="1234"
                #send_sms(phone_with_code, otp)

                # Update OTP details in database
                updated_at = datetime.datetime.utcnow()
                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
                update_otp_in_med_database(session, phone, otp, expiry_time, updated_at)
                
                token = jwt.encode({'email': user.email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'status': 200, 'message': 'OTP Sent on mobile.', 'token': token, 'otp': otp, 'email': user.email, 'name': user.name, 'pin': user.pin}), 200
            else:
                return jsonify({'status': 0, 'message': 'OOPS! Phone Does Not Exist!'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def send_sms(phone, otp):
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=f"Your verification code is: {otp}. Don't share this code with anyone; our employees will never ask for the code.",
        from_=twilio_number,
        to=phone
    )


def generate_otp():
    return str(random.randint(1000, 9999))


def update_otp_in_med_database(session, phone, otp, expiry_time, updated_at):
    try:
        # Query to update OTP details
        query = text("UPDATE users SET otp= :otp, otp_expiry= :expiry_time, updated_at = :updated_at WHERE phone= :phone")
        session.execute(query, {'otp': otp, 'expiry_time': expiry_time, 'phone': phone, 'updated_at': updated_at})
        session.commit()
    except Exception as e:
        return str(e)




@app.route('/update_scheduled_date', methods=['POST'])
def update_scheduled_date():
    data = request.json
    email = data.get('email')
    patient_id = data.get('patient_id')
    doctor = data.get('doctor')
    scheduled_date = data.get('scheduled_date')

    if not (email and patient_id and scheduled_date and doctor):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("UPDATE patients SET scheduled_date = :scheduled_date WHERE email = :email AND patient_id = :patient_id AND doctor = :doctor")
            result = session.execute(query, {'scheduled_date': scheduled_date, 'email': email, 'patient_id': patient_id, 'doctor': doctor})
            session.commit()

            if result.rowcount == 0:
                return jsonify({'error': 'No matching record found'}), 404

            return jsonify({'message': 'Scheduled date updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/total_appointments_till_date', methods=['GET'])
def total_appointments_till_date():
    data = request.json
    date = data.get('date')

    if not date:
        return jsonify({'error': 'Date parameter is required'}), 400

    try:
        with Session() as session:
            query = text("SELECT COUNT(*) as total_appointments FROM patients WHERE scheduled_date <= :date")
            result = session.execute(query, {'date': date}).fetchone()

            total_appointments = result[0]  # Accessing the first element of the tuple

            return jsonify({'total_appointments': total_appointments}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500





@app.route('/total_appointments_till_month', methods=['GET'])
def total_appointments_till_month():
    data = request.json
    year = data.get('year')
    month = data.get('month')

    if not (year and month):
        return jsonify({'error': 'Year and month parameters are required'}), 400

    try:
        with Session() as session:
            query = text("""
                SELECT COUNT(*) as total_appointments
                FROM patients
                WHERE YEAR(scheduled_date) = :year AND MONTH(scheduled_date) = :month
            """)
            result = session.execute(query, {'year': year, 'month': month}).fetchone()

            total_appointments = result[0]  # Accessing the first element of the tuple

            return jsonify({'total_appointments': total_appointments}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    


@app.route('/change_pin_org', methods=['POST'])
def change_pin_org():
    data = request.json
    email = data.get('email')
    current_pin = data.get('current_pin')
    new_pin = data.get('new_pin')

    if not (email and current_pin and new_pin):
        return jsonify({'error': 'Missing required fields'}), 400
    try:
        current_pin = int(current_pin)
        new_pin = int(new_pin)
    except ValueError:
        return jsonify({'error': 'Pins must be numeric'}), 400
    
    try:
        with Session() as session:
            # Verify the current pin
            query = text("SELECT pin FROM organisations WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                if result.pin == current_pin:
                    # Update with the new pin
                    update_query = text("UPDATE organisations SET pin = :new_pin WHERE email = :email")
                    session.execute(update_query, {'new_pin': new_pin, 'email': email})
                    session.commit()
                    return jsonify({'message': 'Pin updated successfully'}), 200
                else:
                    return jsonify({'error': 'Invalid current pin', 'pin': 'pin'}), 400
            else:
                return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/forgot_pin_org', methods=['POST'])
def forgot_pin_org():
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
        
    data = request.json
    email = data.get('email')
    otp = data.get('otp')
    new_pin = data.get('new_pin')

    if not (email and otp and new_pin):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        # Typecast otp and new_pin to integers
        otp = int(otp)
        new_pin = int(new_pin)
    except ValueError:
        return jsonify({'error': 'OTP and new PIN must be integers'}), 400

    try:
        with Session() as session:
            # Verify the OTP
            query = text("SELECT otp FROM organisations WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                if result.otp == otp :
                    # Update with the new pin
                    update_query = text("UPDATE organisations SET pin = :new_pin WHERE email = :email")
                    session.execute(update_query, {'new_pin': new_pin, 'email': email})
                    session.commit()
                    return jsonify({'message': 'Pin updated successfully'}), 200
                else:
                    return jsonify({'error': 'Invalid OTP'}), 400
            else:
                return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/organisation_details', methods=['GET'])
def organisation_details():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email parameter is required'}), 400

    try:
        with Session() as session:
            # Query to fetch organisation details and count of email occurrences in patients table
            query = text("""
                SELECT o.name, o.departments, o.location, o.latitude, o.longitude, o.about,
                    o.profile_photo_path, COUNT(p.email) as patient_count
                FROM organisations o
                LEFT JOIN patients p ON o.email = p.email
                WHERE o.email = :email
            """)
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                response = {
                    'name': result.name,
                    'departments': result.departments,
                    'location': result.location,
                    'latitude': result.latitude,
                    'longitude': result.longitude,
                    'about': result.about,
                    'profile_photo_path': result.profile_photo_path,
                    'patient_count': result.patient_count
                }
                return jsonify(response), 200
            else:
                return jsonify({'error': 'Organisation not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/change_pin_med', methods=['POST'])
def change_pin_med():
    data = request.json
    email = data.get('email')
    current_pin = data.get('current_pin')
    new_pin = data.get('new_pin')

    if not (email and current_pin and new_pin):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Verify the current pin
            query = text("SELECT pin FROM users WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                if result.pin == current_pin:
                    # Update with the new pin
                    update_query = text("UPDATE users SET pin = :new_pin WHERE email = :email")
                    session.execute(update_query, {'new_pin': new_pin, 'email': email})
                    session.commit()
                    return jsonify({'message': 'Pin updated successfully'}), 200
                else:
                    return jsonify({'error': 'Invalid current pin', 'pin': 'pin'}), 400
            else:
                return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/forgot_pin_med', methods=['POST'])
def forgot_pin_med():
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
        
    data = request.json
    email = data.get('email')
    otp = data.get('otp')
    new_pin = data.get('new_pin')

    if not (email and otp and new_pin):
        return jsonify({'error': 'Missing required fields'}), 400
    try:
        # Typecast otp and new_pin to integers
        otp = int(otp)
    except ValueError:
        return jsonify({'error': 'OTP must be integers'}), 400

    try:
        with Session() as session:
            # Verify the OTP
            query = text("SELECT otp FROM users WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                if result.otp == otp :
                    # Update with the new pin
                    update_query = text("UPDATE users SET pin = :new_pin WHERE email = :email")
                    session.execute(update_query, {'new_pin': new_pin, 'email': email})
                    session.commit()
                    return jsonify({'message': 'Pin updated successfully'}), 200
                else:
                    return jsonify({'error': 'Invalid OTP'}), 400
            else:
                return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/med_details', methods=['GET'])
def med_details():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email parameter is required'}), 400

    try:
        with Session() as session:
            # Query to fetch organisation details and count of email occurrences in patients table
            query = text("""
                SELECT o.name, o.departments, o.location, o.latitude, o.longitude, o.about,
                    o.profile_photo_path, COUNT(p.email) as patient_count
                FROM users o
                LEFT JOIN patients p ON o.email = p.email
                WHERE o.email = :email
            """)
            result = session.execute(query, {'email': email}).fetchone()

            if result:
                response = {
                    'name': result.name,
                    'departments': result.departments,
                    'location': result.location,
                    'latitude': result.latitude,
                    'longitude': result.longitude,
                    'about': result.about,
                    'profile_photo_path': result.profile_photo_path,
                    'patient_count': result.patient_count
                }
                return jsonify(response), 200
            else:
                return jsonify({'error': 'Organisation not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/update_patient_details', methods=['POST'])
def update_patient_details():
    data = request.json
    patient_id = data.get('patient_id')
    allergies = data.get('allergies')
    past_history = data.get('past_history')
    care_facilities = data.get('care_facilities')

    if not patient_id:
        return jsonify({'error': 'Patient ID parameter is required'}), 400

    try:
        with Session() as session:
            query = text("""
                UPDATE patients
                SET allergy = :allergies, illness = :past_history, org = :care_facilities
                WHERE patient_id = :patient_id
            """)
            session.execute(query, {
                'allergies': allergies, 
                'past_history': past_history, 
                'care_facilities': care_facilities, 
                'patient_id': patient_id
            })
            session.commit()

            return jsonify({'message': 'Patient details updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/patient_details', methods=['GET'])
def get_patient_details():
    data = request.json
    patient_id = data.get('patient_id')

    if not patient_id:
        return jsonify({'error': 'Patient ID parameter is required'}), 400

    try:
        with Session() as session:
            # Query to get patient details
            patient_query = text("""
                SELECT *
                FROM patients
                WHERE patient_id = :patient_id
            """)
            patient_result = session.execute(patient_query, {'patient_id': patient_id}).fetchone()

            if patient_result:
                # Query to get all wound details
                wound_query = text("""
                    SELECT *
                    FROM wounds
                    WHERE patient_id = :patient_id
                """)
                wound_results = session.execute(wound_query, {'patient_id': patient_id}).fetchall()

                # Convert wound results to a list of dictionaries
                wound_details = [
                    {
                        'length': wound.height,
                        'breadth': wound.width,
                        'depth': wound.depth,
                        'area': wound.area,
                        'wound_location': wound.position,
                        'tissue': wound.tissue,
                        'exudate': wound.exudate,
                        'periwound':wound.periwound,
                        'periwound_type': wound.periwound_type,
                        'image': wound.image,
                        'moisture': wound.moisture
                    } for wound in wound_results
                ]

                # Combine patient and wound details
                patient_details = {
                    'patient_id': patient_result.patient_id,
                    'name': patient_result.name,
                    'age': patient_result.age,
                    'gender': patient_result.gender,
                    'dob': patient_result.dob,
                    'profile_photo_path': patient_result.profile_photo_path,
                    'allergies': patient_result.allergy,
                    'past_history': patient_result.illness,
                    'doctor_name': patient_result.doctor,
                    'care_facilities': patient_result.org,
                    'register_date': patient_result.created_at,
                    'wound_details': wound_details
                }
                return jsonify(patient_details), 200
            else:
                return jsonify({'error': 'Patient not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        

@app.route('/store_image', methods=['POST'])
def store_image():
    if 'image' not in request.files or 'patient_id' not in request.form:
        return jsonify({'error': 'No image or patient_id provided'}), 400

    image_file = request.files['image']
    patient_id = request.form['patient_id']

    if image_file.filename == '':
        return jsonify({'error': 'Empty filename provided'}), 400

    filename = secure_filename(image_file.filename)

    try:
        # Create patient folder if it doesn't exist
        patient_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'patients', patient_id)
        os.makedirs(patient_folder, exist_ok=True)

        # Save image to the filesystem
        image_path = os.path.join(patient_folder, filename)
        image_file.save(image_path)

        # Construct full URL for the image
        image_url = f"{BASE_URL}/uploads/patients/{patient_id}/{filename}"

         # Update the database with the image URL
        with Session() as session:
            query = text("UPDATE patients SET profile_photo_path = :image_url WHERE patient_id = :patient_id")
            session.execute(query, {'image_url': image_url, 'patient_id': patient_id})
            session.commit()

        return jsonify({
            'message': 'Image stored successfully',
            'image_url': image_url
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/patients/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'patients'), filename)


# Endpoint to retrieve and serve the image using patient_id
@app.route('/get_image', methods=['GET'])
def get_image():
    data = request.json
    patient_id = data.get('patient_id')

    if not patient_id:
        return jsonify({'error': 'Patient ID parameter is required'}), 400

    try:
        with Session() as session:
            query = text("SELECT profile_photo_path FROM patients WHERE patient_id = :patient_id")
            result = session.execute(query, {'patient_id': patient_id}).fetchone()

            if result and result.profile_photo_path:
                # Parse the full URL to get the filename and patient_id
                image_url = result.profile_photo_path
                filename = image_url.split('/')[-1]

                # Send the image file from the patient's folder
                return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'patients', patient_id), filename)
            else:
                return jsonify({'error': 'Image not found for the given patient ID'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/store_wound_image', methods=['POST'])
def store_wound_image():
    if 'image' not in request.files or 'patient_id' not in request.form:
        return jsonify({'error': 'No image or patient_id provided'}), 400

    image_file = request.files['image']
    patient_id = request.form['patient_id']

    if image_file.filename == '':
        return jsonify({'error': 'Empty filename provided'}), 400

    filename = secure_filename(image_file.filename)

    try:
        # Create patient folder if it doesn't exist
        patient_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'wounds', patient_id)
        os.makedirs(patient_folder, exist_ok=True)

        # Save image to the filesystem
        image_path = os.path.join(patient_folder, filename)
        image_file.save(image_path)

        # Construct full URL for the image
        image_url = f"{BASE_URL}/uploads/wounds/{patient_id}/{filename}"

        # Update the database with the image URL
        with Session() as session:
            query = text("UPDATE wounds SET image = :image_url WHERE patient_id = :patient_id")
            session.execute(query, {'image_url': image_url, 'patient_id': patient_id})
            session.commit()

        print(f"Image stored successfully: {image_url}")

        return jsonify({
            'message': 'Image stored successfully',
            'image_url': image_url
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/wounds/<patient_id>/<filename>')
def wound_uploaded_file(patient_id, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'wounds', patient_id), filename)



# Endpoint to retrieve and serve the image for a wound using patient_id
@app.route('/get_wound_image', methods=['GET'])
def get_wound_image():
    data = request.json
    patient_id = data.get('patient_id')

    if not patient_id:
        return jsonify({'error': 'Patient ID parameter is required'}), 400

    try:
        with Session() as session:
            query = text("SELECT image FROM wounds WHERE patient_id = :patient_id")
            result = session.execute(query, {'patient_id': patient_id}).fetchone()

            if result and result.image:
                # Parse the full URL to get the filename and patient_id
                image_url = result.image
                filename = image_url.split('/')[-1]

                # Send the image file from the patient's folder
                return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'wounds', patient_id), filename)
            else:
                return jsonify({'error': 'Image not found for the given patient ID'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500






@app.route('/store_med_image', methods=['POST'])
def store_med_image():
    # Check if request contains image data
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    image_file = request.files['image']
    email = request.form.get('email')

    # Check if image file is empty
    if image_file.filename == '' or not email:
        return jsonify({'error': 'Empty filename or email provided'}), 400

    # Generate a unique filename for the image
    filename = secure_filename(image_file.filename)

    try:
        # Create medical practitioner folder if it doesn't exist
        med_practitioner_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'medical_practitioners', email)
        os.makedirs(med_practitioner_folder, exist_ok=True)

        # Save image to the filesystem
        image_path = os.path.join(med_practitioner_folder, filename)
        image_file.save(image_path)
        
        # Construct full URL for the image
        image_url = f"{BASE_URL}/uploads/medical_practitioners/{email}/{filename}"

        # Update the database with the image path
        with Session() as session:
            query = text("UPDATE users SET profile_photo_path = :image_url WHERE email = :email")
            session.execute(query, {'image_url': image_url, 'email': email})
            session.commit()

        return jsonify({'message': 'Image stored and path updated successfully', 'image_url': image_url}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/medical_practitioners/<email>/<filename>')
def med_uploaded_file(email, filename):
    try:
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'medical_practitioners', email), filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# Endpoint to retrieve and serve the image for a medical practitioner using email
@app.route('/get_med_image', methods=['GET'])
def get_med_image():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email parameter is required'}), 400

    try:
        with Session() as session:
            query = text("SELECT profile_photo_path FROM users WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result and result.profile_photo_path:
                # Parse the full URL to get the filename and patient_id
                image_url = result.profile_photo_path
                filename = image_url.split('/')[-1]
                
                # Send the image file from the medical practitioner's folder
                return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'medical_practitioners', email), filename)
            else:
                return jsonify({'error': 'Image not found for the given email'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500




# Endpoint to store an image for a medical practitioner in the filesystem and save path in the database
@app.route('/store_org_image', methods=['POST'])
def store_org_image():
    # Check if request contains image data
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    image_file = request.files['image']
    email = request.form.get('email')

    # Check if image file is empty
    if image_file.filename == '' or not email:
        return jsonify({'error': 'Empty filename or email provided'}), 400

    # Generate a unique filename for the image
    filename = secure_filename(image_file.filename)

    try:
        # Create medical practitioner folder if it doesn't exist
        org_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'organisations', email)
        os.makedirs(org_folder, exist_ok=True)

        # Save image to the filesystem
        image_path = os.path.join(org_folder, filename)
        image_file.save(image_path)
        
        # Construct full URL for the image
        image_url = f"{BASE_URL}/uploads/organisations/{email}/{filename}"

        # Update the database with the image path
        with Session() as session:
            query = text("UPDATE organisations SET profile_photo_path = :image_url WHERE email = :email")
            session.execute(query, {'image_url': image_url, 'email': email})
            session.commit()

        return jsonify({'message': 'Image stored and path updated successfully', 'image_url': image_url}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/organisations/<email>/<filename>')
def org_uploaded_fil(email, filename):
    try:
        # Serve the image file from the organization's folder
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'organisations', email), filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# Endpoint to retrieve and serve the image for a medical practitioner using email
@app.route('/get_org_image', methods=['GET'])
def get_org_image():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email parameter is required'}), 400

    try:
        with Session() as session:
            query = text("SELECT profile_photo_path FROM organisations WHERE email = :email")
            result = session.execute(query, {'email': email}).fetchone()

            if result and result.profile_photo_path:
                # Parse the full URL to get the filename and patient_id
                image_url = result.profile_photo_path
                filename = image_url.split('/')[-1]
                
                # Send the image file from the medical practitioner's folder
                return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'organisations', email), filename)
            else:
                return jsonify({'error': 'Image not found for the given email'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save_notes', methods=['POST'])
def save_notes():
    data = request.json
    patient_id = data.get('patient_id')
    notes = data.get('notes')

    if not patient_id or not notes:
        return jsonify({'error': 'Patient ID and notes are required'}), 400

    try:
        with Session() as session:
            query = text("UPDATE patients SET notes = :notes WHERE patient_id = :patient_id")
            session.execute(query, {'notes': notes, 'patient_id': patient_id})
            session.commit()

        return jsonify({'message': 'Notes saved successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/total_appointments', methods=['GET'])
def total_appointments():
    data = request.json
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    doctor = data.get('doctor')

    if not (start_date_str and end_date_str and doctor):
        return jsonify({'error': 'Start date, end date, and doctor name parameters are required'}), 400

    try:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
        
        
        with Session() as session:
            query = text("""
                SELECT DATE(scheduled_date) as date, COUNT(*) as total_appointments
                FROM patients
                WHERE scheduled_date BETWEEN :start_date AND :end_date
                AND doctor = :doctor
                GROUP BY DATE(scheduled_date)
                ORDER BY DATE(scheduled_date)
            """)

            # Execute query
            results = session.execute(query, {
                'start_date': start_date,
                'end_date': end_date,
                'doctor': doctor
            }).fetchall()

            appointments_by_day = {}

            for row in results:
                date_str = row.date.strftime('%Y-%m-%d')
                appointments_by_day[date_str] = row.total_appointments

            # Ensure all dates in the range are included, even if they have 0 appointments
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                if date_str not in appointments_by_day:
                    appointments_by_day[date_str] = 0
                current_date += datetime.timedelta(days=1)

            return jsonify({'appointments_by_day': appointments_by_day}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin_add_practitioner', methods=['POST'])
def add_practitioner():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    c_code = data.get('c_code')
    phone = data.get('phone')
    org = data.get('org')

    if not (name and email and c_code and phone and org):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            # Check if email or phone already exists
            query = text("SELECT email FROM users WHERE email = :email")
            existing_email = session.execute(query, {'email': email}).fetchone()

            query = text("SELECT phone FROM users WHERE phone = :phone")
            existing_phone = session.execute(query, {'phone': phone}).fetchone()

            if existing_email:
                return jsonify({'error': 'Email already exists. Please login.'}), 400
            elif existing_phone:
                return jsonify({'error': 'Phone number already exists. Please use another phone number.'}), 400
            else:
                # Generate UUID for session
                uuid = generate_session_id()
                # Generate license key
                license_key = generate_license_key()

                # Insert data into users table
                query = text("INSERT INTO users (name, email, c_code, phone, uuid, licence_key, org) VALUES (:name, :email, :c_code, :phone, :uuid, :license_key, :org)")
                session.execute(query, {
                    'name': name, 
                    'email': email, 
                    'c_code': c_code, 
                    'phone': phone, 
                    'uuid': uuid, 
                    'license_key': license_key,
                    'org': org
                })
                session.commit()
                return jsonify({'message': 'Data added successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Endpoint to update organisation profile
@app.route('/update_org_profile', methods=['POST'])
def update_org_profile():
    data = request.json
    name = data.get('name', "")
    department = data.get('department', "")
    about = data.get('about', "")
    location = data.get('location', "")
    latitude = data.get('latitude', "")
    longitude = data.get('longitude', "")
    email = data.get('email')

    if email is None:
        return jsonify({'error': 'Email is required'}), 400

    try:
        with Session() as session:
            # Check if organisation exists
            query = text("SELECT email FROM organisations WHERE email = :email")
            existing_org = session.execute(query, {'email': email}).fetchone()

            if not existing_org:
                return jsonify({'error': 'Organisation not found'}), 404

            # Update organisation profile
            update_query = text("""
                UPDATE organisations
                SET name = :name,
                    departments = :department,
                    about = :about,
                    location = :location,
                    latitude = :latitude,
                    longitude = :longitude
                WHERE email = :email
            """)
            session.execute(update_query, {
                'name': name,
                'department': department,
                'about': about,
                'location': location,
                'latitude': latitude,
                'longitude': longitude,
                'email': email
            })
            session.commit()
            return jsonify({'message': 'Organisation profile updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to update medical profile
@app.route('/update_med_profile', methods=['POST'])
def update_med_profile():
    data = request.json
    name = data.get('name', "")
    department = data.get('department', "")
    about = data.get('about', "")
    location = data.get('location', "")
    latitude = data.get('latitude', "")
    longitude = data.get('longitude', "")
    email = data.get('email')

    if email is None:
        return jsonify({'error': 'Email is required'}), 400

    try:
        with Session() as session:
            # Check if medical user exists
            query = text("SELECT email FROM users WHERE email = :email")
            existing_user = session.execute(query, {'email': email}).fetchone()

            if not existing_user:
                return jsonify({'error': 'Medical user not found'}), 404

            # Update medical profile
            update_query = text("""
                UPDATE users
                SET name = :name,
                    departments = :department,
                    about = :about,
                    location = :location,
                    latitude = :latitude,
                    longitude = :longitude
                WHERE email = :email
            """)
            session.execute(update_query, {
                'name': name,
                'department': department,
                'about': about,
                'location': location,
                'latitude': latitude,
                'longitude': longitude,
                'email': email
            })
            session.commit()
            return jsonify({'message': 'Medical profile updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/add_wound_details_v2', methods=['POST'])
def add_wound_details_v2():
    # Get the Authorization header
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401

    # Get the data from the request
    data = request.form
    length = data.get('length')
    breadth = data.get('breadth')
    depth = data.get('depth')
    area = data.get('area')
    moisture = data.get('moisture')
    wound_location = data.get('wound_location')
    tissue = data.get('tissue')
    exudate = data.get('exudate')
    periwound = data.get('periwound')
    periwound_type = data.get('periwound_type')
    patient_id = data.get('patient_id')
    type = data.get('type')
    category = data.get('category')
    edge = data.get('edge')
    infection = data.get('infection')
    last_dressing_date = data.get('last_dressing_date')

    if not (length and breadth and depth and area and moisture):
        return jsonify({'error': 'Missing required fields'}), 400
    
    updated_at = datetime.datetime.utcnow()

    # Image handling
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    image_file = request.files['image']

    if image_file.filename == '':
        return jsonify({'error': 'Empty filename provided'}), 400

    filename = secure_filename(image_file.filename)

    try:
        with Session() as session:
            # Fetch the existing area from the 'wounds' table
            query = text("SELECT area, id, created_at FROM wounds WHERE patient_id = :patient_id")
            result = session.execute(query, {'patient_id': patient_id}).fetchone()
            
            if not result:
                return jsonify({'error': 'Patient not found'}), 404

            existing_area = result[0]
            if not existing_area: 
                existing_area = 0
            wound_id = result[1]
            created_at = result[2]
            area_difference = float(area) - float(existing_area)
            if area_difference > 0:
                size_variation = 'wound area increased'
            elif area_difference < 0:
                size_variation = 'wound area reduced'
            else:
                size_variation = 'wound area same'

            
            patient_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'wounds', patient_id)
            os.makedirs(patient_folder, exist_ok=True)
            image_path = os.path.join(patient_folder, filename)
            image_file.save(image_path)

            # Construct full URL for the image
            image_url = f"{BASE_URL}/uploads/wounds/{patient_id}/{filename}"

            # Insert the data into the 'wound_images' table
            uuid = generate_session_id()
            query1 = text("""
                INSERT INTO wound_images (depth, width, height, uuid, updated_at, patient_id, size_variation, image, wound_id, created_at, area)
                VALUES (:depth, :breadth, :length, :uuid, :updated_at, :patient_id, :size_variation, :image_url, :wound_id, :created_at, :area)
            """)
            session.execute(query1, {
                'depth': depth, 'breadth': breadth, 'length': length, 'uuid': uuid, 
                'updated_at': updated_at, 'patient_id': patient_id, 'size_variation': size_variation,
                'image_url': image_url, 'wound_id': wound_id, 'created_at': created_at, 'area': area
            })

            # Update the 'wounds' table
            query2 = text("""
                UPDATE wounds SET height = :length, width = :breadth, depth = :depth, area = :area, 
                moisture = :moisture, position = :wound_location, tissue = :tissue, exudate = :exudate, 
                periwound = :periwound, periwound_type = :periwound_type, type = :type, category = :category, 
                edges = :edge, infection = :infection, updated_at = :updated_at, last_dressing = :last_dressing_date,
                image = :image_url  
                WHERE patient_id = :patient_id
            """)
            session.execute(query2, {
                'length': length, 'breadth': breadth, 'depth': depth, 'area': area, 
                'moisture': moisture, 'wound_location': wound_location, 'tissue': tissue, 
                'exudate': exudate, 'periwound': periwound, 'periwound_type': periwound_type, 
                'type': type, 'category': category, 'edge': edge, 'infection': infection,
                'updated_at': updated_at, 'last_dressing_date': last_dressing_date, 'patient_id': patient_id,
                'image_url': image_url
            })

            session.commit()
        return jsonify({
            'message': 'Wound details and image stored successfully',
            'image_url': image_url
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/wound_progress_timeline', methods=['GET'])
def get_wound_details_v2():
    data = request.json
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'patient_id is required'}), 400

    try:
        with Session() as session:
            query = text("""
                SELECT * FROM wound_images WHERE patient_id = :patient_id ORDER BY updated_at DESC """)
            results = session.execute(query, {'patient_id': patient_id}).fetchall()

            wound_details = []
            for row in results:
                wound_details.append({
                    'length': row.height,
                    'breadth': row.width,
                    'depth': row.depth,
                    'size_variation': row.size_variation,
                    'image': row.image,
                    'patient_id': row.patient_id,
                    'area': row.area,
                    'updated_at': row.updated_at.isoformat()
                })

        return jsonify(wound_details), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/med/forgot/pin/otp', methods=['POST'])
def med_forgot_pin_otp():
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    phone = data.get('phone')

    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400
    try:
        with Session() as session:
            # Fetch professional details from the database
            query = text("SELECT * FROM users WHERE phone = :phone")
            user = session.execute(query, {'phone': phone}).fetchone()

            if user:
                phone_with_code = user.c_code + user.phone
                #otp = generate_otp()
                otp="1234"
                #send_sms(phone_with_code, otp)

                # Update OTP details in database
                updated_at = datetime.datetime.utcnow()
                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
                update_otp_in_med_database(session, phone, otp, expiry_time, updated_at)
                
                return jsonify({'status': 200, 'message': 'OTP Sent on mobile.', 'otp': otp}), 200
            else:
                return jsonify({'status': 0, 'message': 'OOPS! Phone Does Not Exist!'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/org/forgot/pin/otp', methods=['POST'])
def org_forgot_pin_otp():
    auth_header = request.headers.get('Authorization')

    # Check if the Authorization header is present and has the correct format
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Invalid Authorization header'}), 401

    # Extract the JWT token from the Authorization header
    token = auth_header.split(' ')[1]

    try:
        # Verify the JWT token using the secret key
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    phone = data.get('phone')

    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400  
    try:
        with Session() as session:
            # Fetch professional details from the database
            query = text("SELECT * FROM organisations WHERE phone = :phone")
            user = session.execute(query, {'phone': phone}).fetchone()

            if user:
                phone_with_code = user.c_code + user.phone
                #otp = generate_otp()
                otp="1234"
                #send_sms(phone_with_code, otp)

                # Update OTP details in database
                updated_at = datetime.datetime.utcnow()
                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
                update_otp_in_database(session, phone, otp, expiry_time, updated_at)
                
                return jsonify({'status': 200, 'message': 'OTP Sent on mobile.', 'otp': otp}), 200
            else:
                return jsonify({'status': 0, 'message': 'OOPS! Phone Does Not Exist!'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/update_scheduled_date_v2', methods=['POST'])
def update_scheduled_date_v2():
    data = request.json
    email = data.get('email')
    patient_id = data.get('patient_id')
    scheduled_date = data.get('scheduled_date')

    if not (email and patient_id and scheduled_date ):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("UPDATE patients SET scheduled_date = :scheduled_date WHERE email = :email AND patient_id = :patient_id")
            result = session.execute(query, {'scheduled_date': scheduled_date, 'email': email, 'patient_id': patient_id})
            session.commit()

            if result.rowcount == 0:
                return jsonify({'error': 'No matching record found'}), 404

            return jsonify({'message': 'Scheduled date updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False)
