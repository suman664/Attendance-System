from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import os
from database import init_db, get_db_connection
from auth import (
    authenticate_user, 
    generate_token, 
    token_required, 
    role_required,
    verify_token
)
from models import (
    record_employee_attendance, 
    get_employee_attendance, 
    get_attendance_stats,
    record_student_attendance, 
    get_students_by_grade_section,
    generate_qr_code, 
    get_employees, 
    add_employee, 
    activate_employee,
    add_student
)

# Initialize database on startup
try:
    init_db()
except Exception as e:
    print(f"⚠️  Database initialization warning: {e}")

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ======================
# AUTHENTICATION
# ======================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'password' not in data or 'role' not in data:
        return jsonify({'error': 'Missing required fields (user_id, password, role)'}), 400
    
    result = authenticate_user(data['user_id'], data['password'], data['role'])
    
    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 403
    
    if not result:
        return jsonify({'error': 'Invalid credentials or account not activated'}), 401
    
    token = generate_token(result['id'], result['role'])
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': result['id'],
            'user_id': result['user_id'],
            'name': result['name'],
            'role': result['role'],
            'grade': result['grade']
        }
    }), 200

# ======================
# EMPLOYEE MANAGEMENT
# ======================

@app.route('/api/employees', methods=['GET'])
@token_required
@role_required(['admin'])
def get_employees_route():
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    employees = get_employees(include_inactive=include_inactive)
    return jsonify({'employees': employees}), 200

@app.route('/api/employees', methods=['POST'])
@token_required
@role_required(['admin'])
def add_employee_route():
    data = request.get_json()
    
    required = ['user_id', 'password', 'name', 'grade', 'email', 'phone']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    result = add_employee(data, request.current_user['user_id'])
    return jsonify(result), 201 if result['success'] else 400

@app.route('/api/employees/<int:emp_id>/activate', methods=['POST'])
@token_required
@role_required(['admin'])
def activate_employee_route(emp_id):
    result = activate_employee(emp_id, request.current_user['user_id'])
    return jsonify(result), 200 if result['success'] else 400

@app.route('/api/employees/<int:emp_id>', methods=['DELETE'])
@token_required
@role_required(['admin'])
def delete_employee(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = FALSE WHERE id = %s AND role = %s', (emp_id, 'teacher'))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Teacher account deactivated'}), 200

# ======================
# STUDENT MANAGEMENT
# ======================

@app.route('/api/students', methods=['GET'])
@token_required
def get_students_route():
    grade = request.args.get('grade')
    section = request.args.get('section')
    
    if not grade or not section:
        return jsonify({'error': 'Grade and section are required'}), 400
    
    teacher_id = request.current_user['user_id'] if request.current_user['role'] == 'teacher' else None
    students = get_students_by_grade_section(grade, section, teacher_id)
    return jsonify({'students': students}), 200

@app.route('/api/students', methods=['POST'])
@token_required
def add_student_route():
    data = request.get_json()
    
    required = ['student_id', 'name', 'grade', 'section', 'parent_contact']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    result = add_student(data, request.current_user['user_id'], request.current_user['role'])
    return jsonify(result), 201 if result['success'] else 400

# ======================
# ATTENDANCE
# ======================

@app.route('/api/attendance/employees', methods=['GET'])
@token_required
def get_employee_attendance_route():
    date = request.args.get('date')
    grade = request.args.get('grade')
    
    user_id = request.current_user['user_id'] if request.current_user['role'] == 'teacher' else None
    
    records = get_employee_attendance(
        user_id=user_id,
        date=date,
        grade=grade,
        role=request.current_user['role']
    )
    
    return jsonify({'attendance': records}), 200

@app.route('/api/attendance/employees/stats', methods=['GET'])
@token_required
def get_employee_stats():
    user_id = request.current_user['user_id'] if request.current_user['role'] == 'teacher' else None
    stats = get_attendance_stats(user_id=user_id, role=request.current_user['role'])
    return jsonify({'stats': stats}), 200

@app.route('/api/attendance/scan', methods=['POST'])
def scan_qr_code():
    data = request.get_json()
    
    if not data or 'qr_data' not in data:
        return jsonify({'error': 'QR data required'}), 400
    
    try:
        parts = data['qr_data'].split(':')
        if len(parts) != 3 or parts[0] != 'ATTENDANCE':
            return jsonify({'error': 'Invalid QR format'}), 400
        
        user_id = int(parts[1])
        token = parts[2]
        
        payload = verify_token(token)
        if not payload or payload['user_id'] != user_id:
            return jsonify({'error': 'Invalid QR token'}), 401
        
        attendance_record = record_employee_attendance(user_id, action='auto')
        
        return jsonify({
            'success': True,
            'message': 'Attendance recorded successfully',
            'attendance': attendance_record
        }), 200
    except Exception as e:
        return jsonify({'error': f'QR processing failed: {str(e)}'}), 400

@app.route('/api/attendance/students', methods=['POST'])
@token_required
@role_required(['teacher'])
def record_student_attendance_route():
    data = request.get_json()
    
    if not data or 'attendance' not in data or not isinstance(data['attendance'], list):
        return jsonify({'error': 'Attendance data required as array'}), 400
    
    success_count = record_student_attendance(data['attendance'], request.current_user['user_id'])
    
    return jsonify({
        'success': True,
        'message': f'Attendance recorded for {success_count} students',
        'count': success_count
    }), 200

# ======================
# QR CODES (IN-MEMORY)
# ======================

@app.route('/api/qr/generate/<int:user_id>', methods=['GET'])
@token_required
def generate_qr_route(user_id):
    if request.current_user['role'] == 'teacher' and request.current_user['user_id'] != user_id:
        return jsonify({'error': 'You can only generate your own QR code'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, user_id, name, is_active FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if not user['is_active']:
        return jsonify({'error': 'Cannot generate QR for inactive account'}), 403
    
    qr_token = generate_token(user['id'], 'qr_scan')
    qr_base64 = generate_qr_code(user['user_id'], user['name'], qr_token)
    
    return jsonify({
        'success': True,
        'qr_code': qr_base64,
        'expires_at': (datetime.now() + datetime.timedelta(hours=24)).isoformat()
    }), 200

# ======================
# FRONTEND SERVING
# ======================

@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# ======================
# ERROR HANDLING
# ======================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ======================
# START APPLICATION
# ======================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)