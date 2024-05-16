from flask import Flask, request, jsonify
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

# Connect to the database
db = pymysql.connect(
    host=DB_HOST,
    user=DB_USERNAME,
    password=DB_PASSWORD,
    database=DB_DATABASE,
    cursorclass=pymysql.cursors.DictCursor
)

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
    cursor = db.cursor()
    cursor.execute("SELECT MAX(id) FROM patients")
    result = cursor.fetchone()
    last_id = result['MAX(id)'] if result['MAX(id)'] is not None else 0  # Handle the case when the table is empty
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
        with db.cursor() as cursor:
            # Check if email already exists
            query = "SELECT email FROM organisations WHERE email = %s"
            cursor.execute(query, (email,))
            existing_email = cursor.fetchone()

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
                    query = "INSERT INTO organisations (name, email, c_code, phone, uuid, licence_key) VALUES (%s, %s, %s, %s, %s, %s)"
                    cursor.execute(query, (name, email, c_code, phone, uuid, license_key))
                    db.commit()
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
        with db.cursor() as cursor:
            query = "SELECT licence_key FROM organisations WHERE email = %s"
            cursor.execute(query, (email))
            result = cursor.fetchone()
            if result and result['licence_key'] == license_key:
                # Generate JWT token
                token = jwt.encode({'email': email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, JWT_SECRET_KEY, algorithm='HS256')
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
        with db.cursor() as cursor:
            query = "UPDATE organisations SET pin = %s WHERE licence_key = %s;"
            cursor.execute(query, (pin, license_key))
            db.commit()
        return jsonify({'message': 'PIN created successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/fetch_data', methods=['GET'])
def fetch_name_phone():
    data = request.json
    email = data.get('email')
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
        with db.cursor() as cursor:
            query = "SELECT name, phone FROM organisations WHERE email = %s"
            cursor.execute(query, (email))
            data = cursor.fetchall()
            return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API endpoint to save department and location
@app.route('/save_additional_data', methods=['POST'])
def save_department_location():
    data = request.json
    department = data.get('department')
    location = data.get('location') 
    email = data.get('email')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not (department, location, latitude and longitude):
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
        with db.cursor() as cursor:
            query = "UPDATE organisations SET departments = %s, location = %s, latitude = %s, longitude = %s  WHERE email = %s;"
            cursor.execute(query, (department, location,latitude,longitude, email))
            db.commit()
        return jsonify({'message': 'Department, location, latitude and longitude saved successfully'}), 200
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
        with db.cursor() as cursor:
            query = "UPDATE wounds SET height = %s, breadth = %s, depth = %s , area = %s , moisture = %s, position = %s , tissue = %s, exudate = %s, periwound = %s, periwound_type = %s WHERE patient_id = %s;"
            cursor.execute(query, (length, breadth, depth, area, moisture, wound_location, tissue, exudate, periwound, periwound_type, patient_id))
            db.commit()
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
        with db.cursor() as cursor:
            query = "SELECT * FROM patients"
            cursor.execute(query)
            patient_details = cursor.fetchall()
            return jsonify({'patient_details': patient_details}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/add_patient', methods=['POST'])
def add_patient():
    # Get data from request
    data = request.json
    name = data.get('name')
    dob = data.get('dob')
    gender = data.get('gender')
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
        with db.cursor() as cursor:
            uuid = generate_session_id()
            pat_query = "INSERT INTO patients (name, dob, gender, uuid, patient_id) VALUES (%s, %s, %s, %s, %s)"
            wound_query = "INSERT INTO WOUNDS (patient_id) VALUES (%s)"
            cursor.execute(pat_query, (name, dob, gender, uuid, patient_id))
            cursor.execute(wound_query, ( patient_id))
            db.commit()
        return jsonify({'message': 'Patient added successfully', 'patient_id': patient_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    


# API endpoint to search existing patients
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

    data = request.json
    name = data.get('name')
    
    if not name:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with db.cursor() as cursor:
            query = "SELECT * FROM patients WHERE name = %s"
            cursor.execute(query, (name,))
            patient = cursor.fetchall()
            if not patient:
                return jsonify({'message': 'No patients found with this name'}), 404
            return jsonify({'patient': patient}), 200
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
        with db.cursor() as cursor:
            # Fetch patient details
            patient_query = "SELECT * FROM patients WHERE patient_id = %s"
            cursor.execute(patient_query, (patient_id,))
            patient_details = cursor.fetchone()
            if not patient_details:
                return jsonify({'message': 'No patient found with this ID'}), 404

            # Fetch wound details
            wound_query = "SELECT * FROM wounds WHERE patient_id = %s"
            cursor.execute(wound_query, (patient_id,))
            wound_details = cursor.fetchall()

            # Determine wound dimension category based on area
            wound_category = []
            for wound in wound_details:
                area = wound['area_cm2']
                if area <= 5:
                    dimension = 'Small'
                elif 5 < area <= 20:
                    dimension = 'Medium'
                else:
                    dimension = 'Large'
                wound_category.append((wound['wound_type'], dimension))

            # Fetch medications for the wounds
            medication_details = []
            for wound_type, dimension in wound_category:
                medication_query = """
                SELECT * FROM WoundMedications
                WHERE WoundType = %s AND WoundDimensions = %s
                """
                cursor.execute(medication_query, (wound_type, dimension))
                medications = cursor.fetchall()
                medication_details.extend(medications)

            prescription = {
                'patient_details': patient_details,
                'wound_details': wound_details,
                'medication_details': medication_details
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
        with db.cursor() as cursor:
            # Query to verify the pin
            query = "SELECT pin FROM organisations WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()

            if result:
                if result['pin'] == pin:
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

    # Connect to database
    
    cursor = db.cursor(pymysql.cursors.DictCursor)

    # Fetch professional details from the database
    cursor.execute("SELECT * FROM organisations WHERE phone=%s", (phone))
    professional = cursor.fetchone()
    if professional:
        phone_with_code = professional['c_code'] + professional['phone']
        otp = generate_otp()
        send_sms(phone_with_code, otp)

        # Update OTP details in database
        expiry_time = datetime.datetime.utcnow()  +  datetime.timedelta(minutes=5)
        update_otp_in_database(phone, otp, expiry_time)
        token = jwt.encode({'email':professional['email'], 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, JWT_SECRET_KEY, algorithm='HS256')
        return jsonify({'status': 200, 'message': 'OTP Sent on mobile.'}), 200
    else:
        return jsonify({'status': 0, 'message': 'OOPS! phone Does Not Exit!','token':token}), 404

def send_sms(phone, otp):
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=f"Your verification code is: {otp}. Don't share this code with anyone; our employees will never ask for the code.",
        from_=twilio_number,
        to=phone
    )
    

def generate_otp():
    return str(random.randint(1000, 9999))

def update_otp_in_database(phone, otp, expiry_time):
    # Connect to database
    
    cursor = db.cursor()

    # Update OTP details
    cursor.execute("UPDATE organisations SET otp=%s, otp_expiry=%s WHERE phone=%s", (otp, expiry_time, phone))
    db.commit()


@app.route('/med_add_data', methods=['POST'])
def med_add_data():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    c_code = data.get('c_code')
    phone = data.get('phone')

    if not (name and email and c_code and phone):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with db.cursor() as cursor:
            # Check if email already exists
            query = "SELECT email FROM users WHERE email = %s"
            cursor.execute(query, (email,))
            existing_email = cursor.fetchone()

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
                    # Insert data into users table
                    query = "INSERT INTO users (name, email, c_code, phone, uuid, licence_key) VALUES (%s, %s, %s, %s, %s, %s)"
                    cursor.execute(query, (name, email, c_code, phone, uuid, license_key))
                    db.commit()
                    return jsonify({'message': 'Data added successfully', 'license_key': license_key}), 200
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
        with db.cursor() as cursor:
            query = "SELECT licence_key FROM users WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            if result and result['licence_key'] == license_key:
                # Generate JWT token
                token = jwt.encode({'email': email, 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=5)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'message': 'License key verified successfully', 'token': token}), 200
            else:
                return jsonify({'error': 'Invalid license key'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/med_create_pin', methods=['POST'])
def med_create_pin():
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
        with db.cursor() as cursor:
            query = "UPDATE users SET pin = %s WHERE licence_key = %s;"
            cursor.execute(query, (pin, license_key))
            db.commit()
        return jsonify({'message': 'PIN created successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/med_fetch_data', methods=['GET'])
def med_fetch_name_phone():
    data = request.json
    email = data.get('email')
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
        with db.cursor() as cursor:
            query = "SELECT name, phone FROM users WHERE email = %s"
            cursor.execute(query, (email))
            data = cursor.fetchall()
            return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': 'Invalid token'}), 401

    try:
        with db.cursor() as cursor:
            query = "UPDATE users SET speciality = %s, location = %s, latitude = %s, longitude = %s, org = %s, designation = %s WHERE email = %s;"
            cursor.execute(query, (speciality, location, latitude, longitude, org, designation, email))
            db.commit()
        return jsonify({'message': 'specialization, location, organisation and designation saved successfully'}), 200
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
        with db.cursor() as cursor:
            # Query to verify the pin
            query = "SELECT pin FROM users WHERE email = %s"
            cursor.execute(query, (email))
            result = cursor.fetchone()

            if result:
                if result['pin'] == pin:
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

    try:
        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            # Fetch user details from the database
            cursor.execute("SELECT * FROM users WHERE phone=%s", (phone))
            user = cursor.fetchone()
            
            if user:
                phone_with_code = user['c_code'] + user['phone']
                otp = generate_otp()
                send_sms(phone_with_code, otp)

                # Update OTP details in database
                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
                update_otp_in_med_database(phone, otp, expiry_time)
                token = jwt.encode({'email': user['email'], 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=5)}, JWT_SECRET_KEY, algorithm='HS256')
                return jsonify({'status': 200, 'message': 'OTP Sent on mobile.', 'token': token}), 200
            else:
                return jsonify({'status': 0, 'message': 'OOPS! phone Does Not Exist!'}), 404
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

def update_otp_in_med_database(phone, otp, expiry_time):
    try:
        with db.cursor() as cursor:
            query = "UPDATE users SET otp = %s, otp_expiry = %s WHERE phone = %s"
            cursor.execute(query, (otp, expiry_time, phone))
            db.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)


