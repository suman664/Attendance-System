import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

# Get database URL from environment (Neon connection string)
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Connect to Neon PostgreSQL database"""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not set!")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """Initialize PostgreSQL database schema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # USERS TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'teacher')),
            name TEXT NOT NULL,
            grade TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            activated_at TIMESTAMP
        )
    ''')
    
    # STUDENTS TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            section TEXT NOT NULL,
            parent_name TEXT,
            parent_contact TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # EMPLOYEE ATTENDANCE TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employee_attendance (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date DATE NOT NULL,
            check_in TIME,
            check_out TIME,
            status TEXT CHECK (status IN ('Present', 'Absent', 'Late', 'Early', 'Leave')),
            remarks TEXT,
            recorded_by INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE (user_id, date)
        )
    ''')
    
    # STUDENT ATTENDANCE TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_attendance (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL,
            date DATE NOT NULL,
            is_present BOOLEAN NOT NULL,
            recorded_by INTEGER NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (student_id, date)
        )
    ''')
    
    # Create default admin account if not exists
    cursor.execute("SELECT * FROM users WHERE user_id = 'ADMIN001'")
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123', method='pbkdf2:sha256')
        cursor.execute('''
            INSERT INTO users (user_id, password, role, name, email, phone, is_active, activated_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ''', (
            'ADMIN001', 
            hashed_pw, 
            'admin', 
            'System Administrator', 
            'admin@school.edu', 
            '+1 555 123 4567',
            True
        ))
        print("\n" + "="*70)
        print("✅ DEFAULT ADMIN CREATED")
        print("User ID: ADMIN001 | Password: admin123")
        print("⚠️  CHANGE PASSWORD IMMEDIATELY AFTER FIRST LOGIN!")
        print("="*70 + "\n")
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully with Neon PostgreSQL")
    print("🔒 Zero sample data - Admin must add all teachers/students\n")