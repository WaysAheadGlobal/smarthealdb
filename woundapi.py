from flask import Flask, request, jsonify
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
load_dotenv()

app = Flask(__name__)

# Database credentials
DB_HOST = '103.239.89.99'
DB_DATABASE = 'SmartHealAppDB'
DB_USERNAME = 'SmartHealAppUsr'
DB_PASSWORD = 'I^4y1b12y'

# Create database engine
DATABASE_URL = f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}/{DB_DATABASE}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create session factory
Session = sessionmaker(bind=engine)

account_sid = os.getenv('acc_sid')
auth_token = os.getenv('auth_token')
twilio_number = os.getenv('tn')

# Secret key used for verifying JWT tokens (should be the same as in your PHP API)
JWT_SECRET_KEY = 'CkOPcOppyh31sQcisbyOM3RKD4C2G7SzQmuG5LePt9XBarsxgjm0fc7uOECcqoGm'


def generate_session_id():
    return str(uuid.uuid4())

# Function to generate random license key
def generate_license_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def generate_patient_id():
    with Session() as session:
        result = session.execute(text("SELECT MAX(id) FROM patients")).fetchone()
        last_id = result[0] if result[0] is not None else 0  # Handle the case when the table is empty
        prefix = "AB"  # Your 2 characters prefix
        formatted_id = f"{prefix}000{last_id + 1}"
        return formatted_id

@app.route('/add_data', methods=['POST'])
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
            # Check if email already exists
            query = text("SELECT email FROM organisations WHERE email = :email")
            existing_email = session.execute(query, {'email': email}).fetchone()

            if existing_email:
                return jsonify({'error': 'Email already exists. Please login.'}), 400
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
                    # Insert data into organisations table
                    query = text("INSERT INTO organisations (name, email, c_code, phone, uuid, licence_key) VALUES (:name, :email, :c_code, :phone, :uuid, :license_key)")
                    session.execute(query, {'name': name, 'email': email, 'c_code': c_code, 'phone': phone, 'uuid': uuid, 'license_key': license_key})
                    session.commit()
                    return jsonify({'message': 'Data added successfully', 'license_key': license_key}), 200
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
    pin = data.get('pin')
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

    if not pin:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("UPDATE organisations SET pin = :pin WHERE licence_key = :license_key")
            session.execute(query, {'pin': pin, 'license_key': license_key})
            session.commit()
        return jsonify({'message': 'PIN created successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/fetch_data', methods=['GET'])
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

    if not (length and breadth and depth and area and moisture):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with Session() as session:
            query = text("UPDATE wounds SET height = :length, width = :breadth, depth = :depth, area = :area, moisture = :moisture, position = :wound_location, tissue = :tissue, exudate = :exudate, periwound = :periwound, periwound_type = :periwound_type WHERE patient_id = :patient_id;")
            session.execute(query, {'length': length, 'breadth': breadth, 'depth': depth, 'area': area, 'moisture': moisture, 'wound_location': wound_location, 'tissue': tissue, 'exudate': exudate, 'periwound': periwound, 'periwound_type': periwound_type, 'patient_id': patient_id})
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

    try:
        with Session() as session:
            uuid = generate_session_id()
            pat_query = text("INSERT INTO patients (name, dob, gender, age, height, weight, email, uuid, patient_id) VALUES (:name, :dob, :gender, :age, :height, :weight, :email, :uuid, :patient_id)")
            session.execute(pat_query, {'name': name, 'dob': dob, 'gender': gender, 'age': age, 'height': height, 'weight': weight, 'email': email, 'uuid': uuid, 'patient_id': patient_id})
            wound_query = text("INSERT INTO wounds ( uuid, patient_id) VALUES (:uuid, :patient_id)")
            session.execute(wound_query, {'uuid': uuid, 'patient_id': patient_id})
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
                otp = generate_otp()
                send_sms(phone_with_code, otp)

                # Update OTP details in database
                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
                update_otp_in_database(session, phone, otp, expiry_time)
                
                token = jwt.encode({'email': organisation.email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'status': 200, 'message': 'OTP Sent on mobile.', 'token': token, 'otp': otp, 'email': organisation.email}), 200
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


def update_otp_in_database(session, phone, otp, expiry_time):
    try:
        # Query to update OTP details
        query = text("UPDATE organisations SET otp= :otp, otp_expiry= :expiry_time WHERE phone= :phone")
        session.execute(query, {'otp': otp, 'expiry_time': expiry_time, 'phone': phone})
        session.commit()
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    app.run(debug=False)


