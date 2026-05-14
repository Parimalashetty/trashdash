from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
import random, string, time, os, requests

# ML imports
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

# Twilio real OTP
from twilio.rest import Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "trashdash_super_secret_2024")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trashdash.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
CORS(app, supports_credentials=True)


otps = {}
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    joined = db.Column(db.String(50), nullable=False)


class Order(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    user_email = db.Column(db.String(120), nullable=False)
    waste_type = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    base_price = db.Column(db.Float, nullable=False)
    platform_fee = db.Column(db.Float, nullable=False)
    distance_fee = db.Column(db.Float, default=0)
    handling_fee = db.Column(db.Float, default=0)
    total = db.Column(db.Float, nullable=False)
    collector_name = db.Column(db.String(120), nullable=False)
    collector_rating = db.Column(db.Float, nullable=False)
    collector_distance = db.Column(db.String(30), nullable=False)
    collector_avatar = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='confirmed')
    eta = db.Column(db.String(30), nullable=False)
    payment_method = db.Column(db.String(30), nullable=True)
    created = db.Column(db.String(50), nullable=False)


with app.app_context():
    db.create_all()

COLLECTORS = [
    {'id': 1, 'name': 'Ravi Kumar', 'rating': 4.8, 'distance_km': 0.8, 'avatar': '👷'},
    {'id': 2, 'name': 'Suresh Babu', 'rating': 4.6, 'distance_km': 1.2, 'avatar': '🧹'},
    {'id': 3, 'name': 'Anita Singh', 'rating': 4.9, 'distance_km': 0.5, 'avatar': '♻️'},
    {'id': 4, 'name': 'Deepak Raj', 'rating': 4.7, 'distance_km': 0.9, 'avatar': '🚛'},
]

# ---------------- ML MODEL ----------------
def train_ml_model():
    data = {
        "waste_code": [0,0,0,1,1,1,2,2,2],
        "quantity":   [2,5,10,2,5,10,2,5,10],
        "distance":   [1,3,5,1,3,5,1,3,5],
        "eta":        [10,15,23,12,18,27,14,21,30]
    }
    df = pd.DataFrame(data)
    X = df[["waste_code", "quantity", "distance"]]
    y = df["eta"]
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    return model

ml_model = train_ml_model()

def waste_to_code(waste_type):
    if waste_type == "dry":
        return 0
    if waste_type == "wet":
        return 1
    return 2

def predict_eta(waste_type, quantity, distance):
    code = waste_to_code(waste_type)
    prediction = ml_model.predict([[code, float(quantity), float(distance)]])[0]
    return max(8, round(prediction))


# ---------------- HELPERS ----------------
def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def calculate_price(waste_type, quantity_kg, distance_km=1):
    rates = {'dry': 15, 'wet': 20, 'mixed': 18}
    rate = rates.get(waste_type, 15)

    quantity_kg = float(quantity_kg)
    distance_km = float(distance_km)

    base = rate * quantity_kg
    platform_fee = 5.0
    distance_fee = distance_km * 3

    if quantity_kg >= 10:
        handling_fee = 10
    elif quantity_kg >= 5:
        handling_fee = 5
    else:
        handling_fee = 0

    total = base + platform_fee + distance_fee + handling_fee

    return {
        'base_price': round(base, 2),
        'platform_fee': platform_fee,
        'distance_fee': round(distance_fee, 2),
        'handling_fee': handling_fee,
        'total': round(total, 2),
        'rate': rate
    }

def reverse_geocode(lat, lng):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json"
        }
        headers = {
            "User-Agent": "TrashDashCollegeProject/1.0"
        }
        res = requests.get(url, params=params, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            return data.get("display_name", "Address not found")
    except Exception:
        pass
    return "Address not available"

def send_real_otp(phone):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    verify_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")

    if not account_sid or not auth_token or not verify_sid:
        return False

    client = Client(account_sid, auth_token)
    client.verify.v2.services(verify_sid).verifications.create(
        to=phone,
        channel="sms"
    )
    return True

def check_real_otp(phone, otp):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    verify_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")

    if not account_sid or not auth_token or not verify_sid:
        return False

    client = Client(account_sid, auth_token)
    result = client.verify.v2.services(verify_sid).verification_checks.create(
        to=phone,
        code=otp
    )
    return result.status == "approved"


# ---------------- ROUTES ----------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/register', methods=['POST'])
@app.route('/api/register', methods=['POST'])
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')

    if not all([name, email, phone, password]):
        return jsonify({'error': 'All fields are required'}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({'error': 'Account already exists. Please login.'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    new_user = User(
        name=name,
        email=email,
        phone=phone,
        password_hash=generate_password_hash(password),
        joined=datetime.now().strftime('%d %b %Y')
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'Account created! Please login.'})
@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({'error': 'No account found with this email'}), 404

    if not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Incorrect password'}), 401

    phone = user.phone

    if send_real_otp(phone):
        return jsonify({'message': 'Real OTP sent successfully!'})

    otp = generate_otp()
    otps[email] = {'otp': otp, 'time': time.time()}
    print(f"\n[TrashDash DEV OTP] → {email} : {otp}\n")

    return jsonify({
        'message': 'OTP sent successfully!',
        'otp_hint': otp
    })


@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json
    email = data.get('email', '').strip().lower()
    otp = data.get('otp', '').strip()

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({'error': 'Account not found'}), 404

    phone = user.phone

    if os.getenv("TWILIO_ACCOUNT_SID"):
        if not check_real_otp(phone, otp):
            return jsonify({'error': 'Incorrect OTP'}), 401
    else:
        if email not in otps:
            return jsonify({'error': 'Please request an OTP first'}), 400

        rec = otps[email]

        if time.time() - rec['time'] > 300:
            del otps[email]
            return jsonify({'error': 'OTP expired. Please try again.'}), 400

        if rec['otp'] != otp:
            return jsonify({'error': 'Incorrect OTP'}), 401

        del otps[email]

    session['user_email'] = email
    session['user_name'] = user.name

    return jsonify({
        'message': 'Login successful!',
        'user': {
            'name': user.name,
            'email': user.email,
            'phone': user.phone
        }
    })


@app.route('/api/place-order', methods=['POST'])
def place_order():
    if 'user_email' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    waste_type = data.get('waste_type')
    quantity = data.get('quantity')
    location = data.get('location', {})

    if not waste_type or not quantity:
        return jsonify({'error': 'Waste type and quantity are required'}), 400

    collector = random.choice(COLLECTORS)
    distance = collector['distance_km']

    lat = location.get('lat')
    lng = location.get('lng')
    address = reverse_geocode(lat, lng) if lat and lng else "Location not provided"

    pricing = calculate_price(waste_type, quantity, distance)
    eta_minutes = predict_eta(waste_type, quantity, distance)
    eta = f"{eta_minutes} mins"

    order_id = f"TD{random.randint(10000, 99999)}"

    new_order = Order(
        id=order_id,
        user_email=session['user_email'],
        waste_type=waste_type,
        quantity=float(quantity),
        base_price=pricing['base_price'],
        platform_fee=pricing['platform_fee'],
        distance_fee=pricing.get('distance_fee', 0),
        handling_fee=pricing.get('handling_fee', 0),
        total=pricing['total'],
        collector_name=collector['name'],
        collector_rating=collector['rating'],
        collector_distance=f"{collector['distance_km']} km",
        collector_avatar=collector['avatar'],
        address=address,
        status='confirmed',
        eta=eta,
        created=datetime.now().strftime('%d %b %Y, %I:%M %p')
    )

    db.session.add(new_order)
    db.session.commit()

    session['current_order'] = order_id

    collector_display = {
        'id': collector['id'],
        'name': collector['name'],
        'rating': collector['rating'],
        'distance': f"{collector['distance_km']} km",
        'avatar': collector['avatar']
    }

    return jsonify({
        'order_id': order_id,
        'collector': collector_display,
        'pricing': pricing,
        'eta': eta,
        'ml_prediction': {
            'eta_minutes': eta_minutes,
            'model_used': 'Random Forest Regression'
        },
        'address': address,
        'status': 'confirmed'
    })
@app.route('/api/order-history', methods=['GET'])
def order_history():
    if 'user_email' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    email = session['user_email']

    user_orders = Order.query.filter_by(user_email=email).order_by(Order.created.desc()).all()

    result = []

    for order in user_orders:
        result.append({
            'id': order.id,
            'waste_type': order.waste_type,
            'quantity': order.quantity,
            'status': order.status,
            'eta': order.eta,
            'address': order.address,
            'payment_method': order.payment_method,
            'created': order.created,
            'pricing': {
                'base_price': order.base_price,
                'platform_fee': order.platform_fee,
                'distance_fee': order.distance_fee,
                'handling_fee': order.handling_fee,
                'total': order.total
            },
            'collector': {
                'name': order.collector_name,
                'rating': order.collector_rating,
                'distance': order.collector_distance,
                'avatar': order.collector_avatar
            }
        })

    return jsonify({
        'orders': result,
        'count': len(result)
    })

@app.route('/api/order-status/<order_id>', methods=['GET'])
def order_status(order_id):
    order = Order.query.filter_by(id=order_id).first()

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify({
        'id': order.id,
        'user': order.user_email,
        'waste_type': order.waste_type,
        'quantity': order.quantity,
        'status': order.status,
        'eta': order.eta,
        'address': order.address,
        'payment_method': order.payment_method,
        'created': order.created
    })

@app.route('/api/admin/orders', methods=['GET'])
def admin_orders():
    all_orders = Order.query.order_by(Order.created.desc()).all()

    result = []

    for order in all_orders:
        result.append({
            'id': order.id,
            'user': order.user_email,
            'waste_type': order.waste_type,
            'quantity': order.quantity,
            'pricing': {
                'base_price': order.base_price,
                'platform_fee': order.platform_fee,
                'distance_fee': order.distance_fee,
                'handling_fee': order.handling_fee,
                'total': order.total
            },
            'collector': {
                'name': order.collector_name,
                'rating': order.collector_rating,
                'distance': order.collector_distance,
                'avatar': order.collector_avatar
            },
            'address': order.address,
            'status': order.status,
            'eta': order.eta,
            'payment_method': order.payment_method,
            'created': order.created
        })

    return jsonify({
        'orders': result,
        'total': len(result)
    })

@app.route('/api/admin/update-status', methods=['POST'])
def update_status():
    data = request.json
    order_id = data.get('order_id')
    status = data.get('status')

    allowed = ['confirmed', 'assigned', 'on_the_way', 'collected', 'paid', 'completed']

    order = Order.query.filter_by(id=order_id).first()

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if status not in allowed:
        return jsonify({'error': 'Invalid status'}), 400

    order.status = status
    db.session.commit()

    return jsonify({
        'message': 'Status updated successfully',
        'order': {
            'id': order.id,
            'status': order.status
        }
    })

@app.route('/api/pay', methods=['POST'])
def pay():
    if 'user_email' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    order_id = data.get('order_id')
    payment_method = data.get('payment_method')

    order = Order.query.filter_by(id=order_id).first()

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    order.status = 'paid'
    order.payment_method = payment_method
    db.session.commit()

    txn_id = f"TXN{random.randint(100000, 999999)}"

    return jsonify({
        'success': True,
        'message': 'Payment successful! Thank you for keeping the city clean 🌱',
        'transaction_id': txn_id
    })



@app.route('/api/ml-predict', methods=['POST'])
def ml_predict():
    data = request.json
    waste_type = data.get('waste_type', 'dry')
    quantity = float(data.get('quantity', 1))
    distance = float(data.get('distance', 1))

    eta = predict_eta(waste_type, quantity, distance)

    return jsonify({
        'waste_type': waste_type,
        'quantity': quantity,
        'distance': distance,
        'predicted_eta_minutes': eta,
        'model': 'Random Forest Regression'
    })


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


if __name__ == '__main__':
    app.run(debug=True)