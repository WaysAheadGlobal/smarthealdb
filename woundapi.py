from flask import Flask, request, jsonify
import pymysql
import jwt
import random
import string
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime
import os
import uuid

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

# Secret key used for verifying JWT tokens (should be the same as in your PHP API)
JWT_SECRET_KEY = 'CkOPcOppyh31sQcisbyOM3RKD4C2G7SzQmuG5LePt9XBarsxgjm0fc7uOECcqoGm'

# SMTP credentials
SENDER_EMAIL = 'ghoshrudrakshi@gmail.com'
PASSWORD = None

def generate_session_id():
    return str(uuid.uuid4())

# Function to generate random license key
def generate_license_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

# Function to send email
def send_email(email, license_key):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = email
    msg['Subject'] = 'License Key'
    body = f'Your license key is: {license_key}'
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP('smtp.freesmtpservers.com', 587) as smtp:
        #smtp.starttls()
        smtp.login(SENDER_EMAIL, PASSWORD)
        smtp.send_message(msg)  

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
                # Insert data into organisations table
                query = "INSERT INTO organisations (name, email, c_code, phone, uuid) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, c_code, phone, uuid))
                db.commit()
                # Generate license key and update organisations table
                license_key = generate_license_key()
                query = "UPDATE organisations SET licence_key = %s WHERE email = %s"
                cursor.execute(query, (license_key, email))
                db.commit()
                return jsonify({'message': 'Data added successfully', 'license_key': license_key}), 200
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
            query = "SELECT name, phone FROM organisations"
            cursor.execute(query)
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

    if not (department and location):
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
            query = "UPDATE organisations SET departments = %s, location = %s WHERE email = %s;"
            cursor.execute(query, (department, location))
            db.commit()
        return jsonify({'message': 'Department and location saved successfully'}), 200
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

    if not (length and breadth and depth and area and moisture):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        with db.cursor() as cursor:
            query = "INSERT INTO wounds (height, breadth, depth, area, moisture, position, tissue, exudate, periwound, periwound_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(query, (length, breadth, depth, area, moisture, wound_location, tissue, exudate, periwound, periwound_type))
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
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
    uuid = generate_session_id()
    name = data.get('name')
    dob = data.get('dob')
    gender = data.get('gender')
    
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
            query = "INSERT INTO patients (name, dob, gender, uuid) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (name, dob, gender, uuid))
        db.commit()
    finally:
        db.close()

    return jsonify({'message': 'Patient added successfully'})

if __name__ == '__main__':
    app.run(debug=True)
