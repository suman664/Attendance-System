import jwt
import datetime
from functools import wraps
from flask import request, jsonify
from werkzeug.security import check_password_hash
from database import get_db_connection
import os

SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production-with-environment-variable')

def generate_token(user_id, role):
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=8),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'Authentication token required'}), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = request.current_user.get('role')
            if user_role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

def authenticate_user(user_id, password, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, password, role, name, grade, is_active 
        FROM users 
        WHERE user_id = %s AND role = %s
    ''', (user_id, role))
    
    user = cursor.fetchone()
    conn.close()
    
    if user and not user['is_active']:
        return {'error': 'Account not activated. Contact administrator.'}
    
    if user and check_password_hash(user['password'], password):
        return {
            'id': user['id'],
            'user_id': user['user_id'],
            'role': user['role'],
            'name': user['name'],
            'grade': user['grade']
        }
    
    return None