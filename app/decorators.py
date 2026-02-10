from functools import wraps
from flask import request, jsonify
import jwt
from config import Config
from app.db_models.raw_db import Admin

config = Config()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            # Add 60 seconds of leeway to account for clock skew between Auth server and API server
            data = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], leeway=60)
            current_user = Admin.query.get(data['userId'])
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401

        return f(current_user, *args, **kwargs)
    return decorated
