from flask import Flask, request, jsonify
import pymysql
import jwt

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
SECRET_KEY = 'CkOPcOppyh31sQcisbyOM3RKD4C2G7SzQmuG5LePt9XBarsxgjm0fc7uOECcqoGm'

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
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
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

if __name__ == '__main__':
    app.run(debug=True)
