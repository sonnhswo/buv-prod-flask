from flask import Blueprint, request, jsonify, current_app
from app.db_models.raw_db import User
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
            current_user = User.query.filter_by(id=data['id']).first()
        except Exception:
            return jsonify({'message': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
    return decorated

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Could not verify'}), 401
        
    user = User.query.filter_by(email=data.get('email')).first()
    
    if not user:
        return jsonify({'message': 'User does not exist'}), 401
        
    if user.check_password(data.get('password')):
        token = jwt.encode({
            'id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, current_app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'token': token,
            'user': {
                'id': str(user.id),
                'name': user.name,
                'email': user.email
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
        'email': current_user.email
    })
