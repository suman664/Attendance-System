import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash
from database import get_db_connection
import qrcode
from PIL import Image, ImageDraw
import io
import base64

def get_current_date():
    return datetime.now().strftime('%Y-%m-%d')

def get_current_time():
    return datetime.now().strftime('%H:%M')

def calculate_status(check_in_time, check_out_time=None):
    LATE_THRESHOLD = datetime.strptime("09:05", "%H:%M").time()
    EARLY_THRESHOLD = datetime.strptime("16:55", "%H:%M").time()
    
    try:
        check_in = datetime.strptime(check_in_time, '%H:%M').time()
    except:
        return 'Absent'
    
    if check_in > LATE_THRESHOLD:
        status = 'Late'
    else:
        status = 'Present'
    
    if check_out_time and status == 'Present':
        try:
            check_out = datetime.strptime(check_out_time, '%H:%M').time()
            if check_out < EARLY_THRESHOLD:
                status = 'Early'
        except:
            pass
    
    return status

def record_employee_attendance(user_id, action='auto'):
    conn = get_db_connection()
    cursor = conn.cursor()
    today = get_current_date()
    current_time = get_current_time()
    
    cursor.execute('''
        SELECT id, check_in, check_out 
        FROM employee_attendance 
        WHERE user_id = %s AND date = %s
    ''', (user_id, today))
    
    record = cursor.fetchone()
    
    if action == 'auto':
        action = 'checkout' if (record and record['check_in'] and not record['check_out']) else 'checkin'
    
    if action == 'checkin':
        if record:
            if not record['check_in']:
                status = calculate_status(current_time)
                cursor.execute('''
                    UPDATE employee_attendance 
                    SET check_in = %s, status = %s, remarks = %s
                    WHERE id = %s
                ''', (current_time, status, 'Recorded via system', record['id']))
        else:
            status = calculate_status(current_time)
            cursor.execute('''
                INSERT INTO employee_attendance (user_id, date, check_in, status, recorded_by)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, today, current_time, status, user_id))
    
    elif action == 'checkout' and record and record['check_in']:
        status = calculate_status(record['check_in'], current_time)
        cursor.execute('''
            UPDATE employee_attendance 
            SET check_out = %s, status = %s
            WHERE id = %s
        ''', (current_time, status, record['id']))
    
    conn.commit()
    
    cursor.execute('''
        SELECT ea.*, u.name 
        FROM employee_attendance ea
        JOIN users u ON ea.user_id = u.id
        WHERE ea.user_id = %s AND ea.date = %s
    ''', (user_id, today))
    
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None

def get_employee_attendance(user_id=None, date=None, grade=None, role='admin'):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT ea.*, u.name, u.grade as teacher_grade 
        FROM employee_attendance ea
        JOIN users u ON ea.user_id = u.id
        WHERE u.role = 'teacher'
    '''
    params = []
    
    if date:
        query += ' AND ea.date = %s'
        params.append(date)
    
    if grade and grade != 'All':
        query += ' AND u.grade = %s'
        params.append(grade)
    
    if role == 'teacher' and user_id:
        query += ' AND ea.user_id = %s'
        params.append(user_id)
    
    query += ' ORDER BY ea.date DESC, ea.check_in DESC LIMIT 100'
    
    cursor.execute(query, params)
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return records

def get_attendance_stats(user_id=None, role='admin'):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT status, COUNT(*) as count
        FROM employee_attendance ea
        JOIN users u ON ea.user_id = u.id
        WHERE u.role = 'teacher'
    '''
    params = []
    
    if role == 'teacher' and user_id:
        query += ' AND ea.user_id = %s'
        params.append(user_id)
    
    query += ' GROUP BY status'
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    stats = {'Present': 0, 'Absent': 0, 'Late': 0, 'Early': 0, 'Leave': 0}
    for row in results:
        if row['status'] in stats:
            stats[row['status']] = row['count']
    
    if role == 'teacher' and user_id:
        cursor.execute('SELECT COUNT(DISTINCT date) as days FROM employee_attendance WHERE user_id = %s', (user_id,))
        total_days = cursor.fetchone()['days']
        stats['Absent'] = max(0, 30 - sum(stats.values()))
    else:
        stats['Absent'] = max(0, 50 - sum(stats.values()))
    
    conn.close()
    return stats

def record_student_attendance(attendance_data, teacher_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    today = get_current_date()
    
    cursor.execute('SELECT grade FROM users WHERE id = %s', (teacher_id,))
    teacher_grade = cursor.fetchone()
    if not teacher_grade:
        conn.close()
        return 0
    
    success_count = 0
    for entry in attendance_data:
        cursor.execute('SELECT grade FROM students WHERE id = %s', (entry['student_id'],))
        student = cursor.fetchone()
        if not student or student['grade'] != teacher_grade['grade']:
            continue
        
        try:
            cursor.execute('''
                INSERT INTO student_attendance (student_id, date, is_present, recorded_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (student_id, date) 
                DO UPDATE SET is_present = EXCLUDED.is_present, recorded_at = CURRENT_TIMESTAMP
            ''', (entry['student_id'], today, entry['present'], teacher_id))
            success_count += 1
        except Exception as e:
            print(f"Error: {e}")
            continue
    
    conn.commit()
    conn.close()
    return success_count

def get_students_by_grade_section(grade, section, teacher_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if teacher_id:
        cursor.execute('SELECT grade FROM users WHERE id = %s AND role = %s', (teacher_id, 'teacher'))
        teacher = cursor.fetchone()
        if not teacher or teacher['grade'] != grade:
            conn.close()
            return []
    
    cursor.execute('''
        SELECT id, student_id, name, grade, section, parent_contact
        FROM students
        WHERE is_active = TRUE AND grade = %s AND section = %s
        ORDER BY name
    ''', (grade, section))
    
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return students

def generate_qr_code(user_id, name, token):
    """Generate QR code as base64 string (NO FILESYSTEM - SAFE FOR RENDER)"""
    qr_data = f"ATTENDANCE:{user_id}:{token}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#4338ca", back_color="white").convert('RGB')
    width, height = img.size
    draw = ImageDraw.Draw(img)
    
    # Add header bar
    draw.rectangle([(0, 0), (width, 60)], fill="#4338ca")
    draw.text((width//2, 20), "SCHOOL ATTENDANCE", fill="white", anchor="mt", font_size=20)
    
    # Add footer with name
    draw.rectangle([(0, height-60), (width, height)], fill="#4338ca")
    draw.text((width//2, height-30), name, fill="white", anchor="mt", font_size=18)
    
    # Save to in-memory buffer (NO FILESYSTEM)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    # Return base64 data URL
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{qr_base64}"

def get_employees(include_inactive=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = 'SELECT id, user_id, name, role, grade, email, phone, is_active FROM users WHERE role = %s'
    params = ['teacher']
    
    if not include_inactive:
        query += ' AND is_active = TRUE'
    
    query += ' ORDER BY name'
    
    cursor.execute(query, params)
    employees = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return employees

def add_employee(data, created_by_admin_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        hashed_pw = generate_password_hash(data['password'], method='pbkdf2:sha256')
        
        cursor.execute('''
            INSERT INTO users (user_id, password, role, name, grade, email, phone, address, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            RETURNING id
        ''', (
            data['user_id'],
            hashed_pw,
            'teacher',
            data['name'],
            data['grade'],
            data['email'],
            data['phone'],
            data.get('address', '')
        ))
        
        new_id = cursor.fetchone()['id']
        conn.commit()
        
        return {
            'success': True, 
            'message': 'Teacher account created. Account is inactive until activated by admin.',
            'user_id': new_id,
            'requires_activation': True
        }
    except psycopg2.IntegrityError as e:
        conn.rollback()
        if 'user_id' in str(e):
            return {'success': False, 'error': 'User ID already exists'}
        return {'success': False, 'error': 'Database integrity error'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def activate_employee(user_id, admin_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE users 
            SET is_active = TRUE, activated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND role = 'teacher'
        ''', (user_id,))
        
        if cursor.rowcount == 0:
            return {'success': False, 'error': 'Teacher not found'}
        
        conn.commit()
        return {'success': True, 'message': 'Teacher account activated successfully'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def add_student(data, created_by_user_id, user_role):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if user_role == 'teacher':
            cursor.execute('SELECT grade FROM users WHERE id = %s', (created_by_user_id,))
            teacher = cursor.fetchone()
            if not teacher or teacher['grade'] != data['grade']:
                return {'success': False, 'error': 'You can only add students to your assigned grade'}
        
        cursor.execute('''
            INSERT INTO students (student_id, name, grade, section, parent_name, parent_contact, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['student_id'],
            data['name'],
            data['grade'],
            data['section'],
            data.get('parent_name', ''),
            data['parent_contact'],
            created_by_user_id
        ))
        
        conn.commit()
        return {'success': True, 'message': 'Student added successfully'}
    except psycopg2.IntegrityError as e:
        conn.rollback()
        if 'student_id' in str(e):
            return {'success': False, 'error': 'Student ID already exists'}
        return {'success': False, 'error': 'Database integrity error'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()