from flask import Blueprint, request, jsonify, current_app
from app.db_models.raw_db import Admin
from app.extensions import db
import jwt
import datetime
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header:
            token = auth_header.split(" ")[1] if " " in auth_header else auth_header
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = Admin.query.filter_by(id=data['id']).first()
        except Exception:
            return jsonify({'message': 'Token is invalid!'}), 401

        if current_user is None:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(current_user, *args, **kwargs)
    return decorated

def secret_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_secret_key = current_app.config.get('ADMIN_SECRET_KEY')
        if not admin_secret_key:
            return jsonify({'message': 'Server misconfiguration: ADMIN_SECRET_KEY is not set'}), 500

        key = request.headers.get('X-Secret-Key')
        if not key or key != admin_secret_key:
            return jsonify({'message': 'Unauthorized: Invalid Secret Key'}), 401
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/api/admin/users', methods=['POST'])
@secret_key_required
def create_user():
    data = request.get_json()
    if data is None:
        return jsonify({'message': 'Invalid JSON or empty body'}), 400
    username = data.get('username')
    password = data.get('password')
    division = data.get('division')

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400
    
    if not division:
        return jsonify({'message': 'Division is required'}), 400
    
    # Check if division is only 'teacher' or 'student'
    if division not in ['teacher', 'student']:
        return jsonify({'message': 'Invalid division'}), 400

    if Admin.query.filter_by(email=username).first():
        return jsonify({'message': 'Username already exists'}), 409

    # Create new user (using username as email)
    new_user = Admin(email=username, name=username.split('@')[0] if '@' in username else username, division=division)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User created successfully', 'username': username}), 201

@auth_bp.route('/api/admin/users', methods=['GET'])
@secret_key_required
def list_users():
    users = Admin.query.all()
    # List all usernames (emails) but not passwords
    user_list = [{'username': user.email} for user in users]
    return jsonify(user_list), 200

@auth_bp.route('/api/admin/users', methods=['PUT'])
@secret_key_required
def update_user_password():
    data = request.get_json()
    if data is None:
        return jsonify({'message': 'Invalid JSON or empty body'}), 400
    username = data.get('username')
    new_password = data.get('password')

    if not username or not new_password:
        return jsonify({'message': 'Username and new password are required'}), 400

    user = Admin.query.filter_by(email=username).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    user.set_password(new_password)
    db.session.commit()

    return jsonify({'message': 'Password updated successfully'}), 200

@auth_bp.route('/api/admin/users', methods=['DELETE'])
@secret_key_required
def delete_user():
    data = request.get_json()
    if data is None:
        return jsonify({'message': 'Invalid JSON or empty body'}), 400
    username = data.get('username')

    if not username:
        return jsonify({'message': 'Username is required'}), 400

    user = Admin.query.filter_by(email=username).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': 'User deleted successfully'}), 200

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Could not verify'}), 401
        
    user = Admin.query.filter_by(email=data.get('email')).first()

    if not user:
        return jsonify({'message': 'Invalid credentials'}), 401

    if user.check_password(data.get('password')):
        token = jwt.encode({
            'id': user.id,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=current_app.config.get('JWT_EXPIRATION_HOURS', 24))
        }, current_app.config['SECRET_KEY'], algorithm="HS256")

        return jsonify({
            'token': token,
            'user': {
            'id': str(user.id),
            'name': user.name,
            'email': user.email,
            'division': user.division
            }
        })

    return jsonify({'message': 'Invalid credentials'}), 401

@auth_bp.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    if not current_user:
        return jsonify({'message': 'User not found'}), 404
        
    return jsonify({
        'id': str(current_user.id),
        'name': current_user.name,
        'email': current_user.email,
        'division': current_user.division
    })
