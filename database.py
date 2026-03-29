import mysql.connector
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "geoface_db")

def get_connection():
    """Establishes and returns a connection to the database."""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return connection
    except mysql.connector.Error as err:
        if err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
            # If database does not exist, connect without database context to create it
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD
            )
            return connection
        else:
            print(f"Error connecting to database: {err}")
            return None

def initialize_database():
    """Creates the database and necessary tables if they don't exist."""
    conn = get_connection()
    if conn is None:
        return
    
    cursor = conn.cursor(dictionary=True)
    
    # Create database if not exists
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    cursor.execute(f"USE {DB_NAME}")
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role ENUM('Admin', 'Teacher', 'Student') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create classes table [NEW]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            class_name VARCHAR(100) UNIQUE NOT NULL
        )
    ''')
    
    # Create courses table [NEW]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_name VARCHAR(100) UNIQUE NOT NULL
        )
    ''')
    
    # Create students table [UPDATED]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            student_id_code VARCHAR(50) UNIQUE NOT NULL,
            class_id INT,
            face_embedding JSON,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
        )
    ''')

    # Create teachers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            teacher_id_code VARCHAR(50) UNIQUE NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Create teacher_assignments table [NEW]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher_assignments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            teacher_id INT NOT NULL,
            class_id INT NOT NULL,
            course_id INT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            UNIQUE KEY unique_assignment (teacher_id, class_id, course_id)
        )
    ''')
    
    # Create student_courses table [NEW]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            course_id INT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            UNIQUE KEY unique_enrollment (student_id, course_id)
        )
    ''')

    # Create teacher_settings table [NEW]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            teacher_id INT NOT NULL,
            class_id INT NOT NULL,
            course_id INT NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            gps_lat DECIMAL(10, 8),
            gps_lon DECIMAL(11, 8),
            radius DECIMAL(5, 2) DEFAULT 0.5,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            UNIQUE KEY unique_setting (teacher_id, class_id, course_id)
        )
    ''')
    
    # Create notifications table [NEW]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Create attendance table [UPDATED]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id_code VARCHAR(50) NOT NULL,
            course_id INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status ENUM('Present', 'Late', 'Absent') DEFAULT 'Present',
            latitude DECIMAL(10, 8),
            longitude DECIMAL(11, 8),
            spoof_flag BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (student_id_code) REFERENCES students(student_id_code) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
        )
    ''')
    
    # Create attendance_logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id_code VARCHAR(50) NOT NULL,
            date DATE NOT NULL,
            entry_time TIME,
            exit_time TIME,
            FOREIGN KEY (student_id_code) REFERENCES students(student_id_code) ON DELETE CASCADE,
            UNIQUE KEY specific_date_log (student_id_code, date)
        )
    ''')
    
    # Ensure existing tables have new columns (Migration)
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN class_id INT AFTER student_id_code")
        cursor.execute("ALTER TABLE students ADD FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL")
    except:
        pass # Column might already exist
        
    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN course_id INT AFTER student_id_code")
        cursor.execute("ALTER TABLE attendance ADD FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL")
    except:
        pass # Column might already exist

    conn.commit()
    
    # Ensure Admin password is in sync with config.json
    cursor.execute("SELECT * FROM users WHERE email = 'admin@geoface.com'")
    admin = cursor.fetchone()
    
    import os
    import json
    
    # Load current expected password from config
    admin_password = "password"
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                admin_password = config.get("admin_password", "password")
        except:
            pass
    
    from werkzeug.security import generate_password_hash, check_password_hash
    if not admin:
        print("No Admin found. Creating default admin...")
        hashed_pw = generate_password_hash(admin_password)
        cursor.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)", 
                       ("System Admin", "admin@geoface.com", hashed_pw, "Admin"))
        conn.commit()
        print(f"DEBUG: Default admin created: admin@geoface.com / {admin_password}")
    else:
        # Check if password needs update (sync with config)
        if not check_password_hash(admin['password'], admin_password):
            print(f"DEBUG: Admin password mismatch. Syncing with config.json...")
            hashed_pw = generate_password_hash(admin_password)
            cursor.execute("UPDATE users SET password = %s WHERE email = 'admin@geoface.com'", (hashed_pw,))
            conn.commit()
            print(f"DEBUG: Admin password updated to match config.json ({admin_password})")
        else:
            print("DEBUG: Admin exists and password is in sync.")

    # Hash legacy passwords if any
    cursor.execute("SELECT id, password FROM users WHERE password = 'default_password'")
    legacy_users = cursor.fetchall()
    if legacy_users:
        from werkzeug.security import generate_password_hash
        hashed_pw = generate_password_hash("default_password")
        for user in legacy_users:
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, user['id']))
        conn.commit()
        print(f"Hashed {len(legacy_users)} legacy passwords.")

    cursor.close()
    conn.close()
    print("GeoFace Database and tables initialized successfully.")

def register_user(name, email, password_hash, role):
    """Registers a new user into the database."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor()
    try:
        query = "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (name, email, password_hash, role))
        user_id = cursor.lastrowid
        conn.commit()
        return True, user_id
    except mysql.connector.IntegrityError:
        return False, "Email already exists."
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def update_user_role(user_id, role):
    """Updates a user's role."""
    conn = get_connection()
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating role: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def update_user(user_id, name, email, role):
    """Updates user information including name, email, and role."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    cursor = conn.cursor()
    try:
        query = "UPDATE users SET name = %s, email = %s, role = %s WHERE id = %s"
        cursor.execute(query, (name, email, role, user_id))
        conn.commit()
        return True, "User updated successfully"
    except mysql.connector.IntegrityError:
        return False, "Email already exists."
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def update_user_password(user_id, password_hash):
    """Updates a user's password."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (password_hash, user_id))
        conn.commit()
        return True, "Password updated successfully"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def delete_user(user_id):
    """Deletes a user from the database."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    cursor = conn.cursor()
    try:
        # Note: Foreign key constraints with ON DELETE CASCADE will handle students/teachers/courses/etc.
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return True, "User deleted successfully"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_user_by_id(user_id):
    """Retrieves user information by ID."""
    conn = get_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_user_by_email(email):
    """Retrieves user information by email."""
    conn = get_connection()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM users WHERE email = %s"
        cursor.execute(query, (email,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching user: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def register_student(student_id_code, user_id, class_id=None, face_embedding=None):
    """Links a user to a student record with an embedding and class assignment."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor()
    try:
        import json
        embedding_json = json.dumps(face_embedding) if face_embedding is not None else None
        query = "INSERT INTO students (user_id, student_id_code, class_id, face_embedding) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (user_id, student_id_code, class_id, embedding_json))
        conn.commit()
        return True, "Student registered successfully."
    except mysql.connector.IntegrityError as e:
        if e.errno == 1062:
            return False, f"Duplicate entry error: {e}"
        return False, f"IntegrityError: {e}"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def register_teacher(teacher_id_code, user_id):
    """Links a user to a teacher record."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor()
    try:
        query = "INSERT INTO teachers (user_id, teacher_id_code) VALUES (%s, %s)"
        cursor.execute(query, (user_id, teacher_id_code))
        conn.commit()
        return True, "Teacher registered successfully."
    except mysql.connector.IntegrityError as e:
        return False, f"IntegrityError: {e}"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_teacher(teacher_id_code):
    """Retrieves teacher information by their ID code."""
    conn = get_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT t.*, u.name, u.email 
            FROM teachers t 
            JOIN users u ON t.user_id = u.id 
            WHERE t.teacher_id_code = %s
        """
        cursor.execute(query, (teacher_id_code,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_student(student_id_code):
    """Retrieves student information by their ID code."""
    conn = get_connection()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT s.*, u.name, u.email 
            FROM students s 
            JOIN users u ON s.user_id = u.id 
            WHERE s.student_id_code = %s
        """
        cursor.execute(query, (student_id_code,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching student: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def log_attendance(student_id_code, course_id, current_time, class_start_time, class_stop_time, lat=None, lon=None):
    """
    Logs attendance for a specific student for a specific course.
    Handles 'Present' vs 'Late' and tracks entry/exit in attendance_logs.
    """
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        from datetime import datetime, timedelta
        
        # 1. Check student existence
        cursor.execute("SELECT users.name FROM users JOIN students ON users.id = students.user_id WHERE students.student_id_code = %s", (student_id_code,))
        student = cursor.fetchone()
        if not student:
            return False, f"Student {student_id_code} not found."
            
        student_name = student['name']
        current_date = current_time.date()
        current_time_str = current_time.time()

        # 2. Prevent duplicate main attendance record for this student/course/day
        check_query = "SELECT id, status FROM attendance WHERE student_id_code = %s AND DATE(timestamp) = %s AND course_id = %s"
        cursor.execute(check_query, (student_id_code, current_date, course_id))
        existing_attendance = cursor.fetchone()

        # 3. Calculate status (15 min grace period)
        start_dt = datetime.combine(current_date, class_start_time)
        status = 'Present'
        if current_time > start_dt + timedelta(minutes=15):
            status = 'Late'

        if not existing_attendance:
            # 4. First scan for this course today - Create record (Entrance)
            query = """
                INSERT INTO attendance (student_id_code, course_id, timestamp, status, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (student_id_code, course_id, current_time, status, lat, lon))
            
            # Simple daily log for general presence (legacy support/overall report)
            cursor.execute('''
                INSERT IGNORE INTO attendance_logs (student_id_code, date, entry_time)
                VALUES (%s, %s, %s)
            ''', (student_id_code, current_date, current_time_str))
            
            conn.commit()
            return True, f"Entrance Recorded Successfully for {student_name} ({status})."
        else:
            # 5. Already has a record - treat as "Exit" scan
            # Check if this is a "late" exit (prevent immediate exit logs after entrance)
            # Minimum 1 minute between entry and exit to avoid accidental double scans.
            cursor.execute("SELECT entry_time FROM attendance_logs WHERE student_id_code = %s AND date = %s", (student_id_code, current_date))
            log_row = cursor.fetchone()
            
            if log_row and log_row['entry_time']:
                entry_dt = datetime.combine(current_date, (datetime.min + log_row['entry_time']).time())
                if current_time < entry_dt + timedelta(minutes=1):
                    return True, f"Entrance already confirmed at {entry_dt.strftime('%H:%M')}."

            cursor.execute('''
                UPDATE attendance_logs SET exit_time = %s
                WHERE student_id_code = %s AND date = %s
            ''', (current_time_str, student_id_code, current_date))
            
            conn.commit()
            return True, f"Exit Recorded Successfully for {student_name} at {current_time_str.strftime('%H:%M')}."

    except Exception as e:
        conn.rollback()
        return False, f"Log Error: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def get_all_students():
    """Returns a list of all students with their user details."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.*, u.name, u.email, u.created_at 
        FROM students s 
        JOIN users u ON s.user_id = u.id
    """)
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return students

def get_teacher_stats(teacher_id, date):
    """Gets attendance stats for students assigned to a specific teacher's classes/courses."""
    conn = get_connection()
    if not conn:
        return {"present": 0, "late": 0, "absent": 0, "total": 0}
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get all students assigned to this teacher's classes/courses
    query = """
        SELECT DISTINCT s.id, s.student_id_code
        FROM students s
        JOIN student_courses sc ON s.id = sc.student_id
        JOIN teacher_assignments ta ON s.class_id = ta.class_id AND sc.course_id = ta.course_id
        WHERE ta.teacher_id = %s
    """
    cursor.execute(query, (teacher_id,))
    assigned_students = cursor.fetchall()
    student_codes = [s['student_id_code'] for s in assigned_students]
    total_count = len(student_codes)
    
    if total_count == 0:
        cursor.close()
        conn.close()
        return {"present": 0, "late": 0, "absent": 0, "total": 0}
        
    # 2. Get attendance records for these students today
    placeholders = ', '.join(['%s'] * len(student_codes))
    query_base = f"SELECT COUNT(*) as count FROM attendance WHERE DATE(timestamp) = %s AND student_id_code IN ({placeholders}) AND status = %s"
    
    cursor.execute(query_base, (date, *student_codes, 'Present'))
    present = cursor.fetchone()['count']
    
    cursor.execute(query_base, (date, *student_codes, 'Late'))
    late = cursor.fetchone()['count']
    
    absent = total_count - (present + late)
    
    cursor.close()
    conn.close()
    
    return {"present": present, "late": late, "absent": max(0, absent), "total": total_count}

def get_teacher_students(teacher_id):
    """Returns a list of all students assigned to a teacher's classes/courses."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT DISTINCT s.*, u.name, u.email, u.created_at, c.class_name
        FROM students s
        JOIN users u ON s.user_id = u.id
        JOIN classes c ON s.class_id = c.id
        JOIN student_courses sc ON s.id = sc.student_id
        JOIN teacher_assignments ta ON s.class_id = ta.class_id AND sc.course_id = ta.course_id
        WHERE ta.teacher_id = %s
    """
    cursor.execute(query, (teacher_id,))
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return students

def get_attendance_stats(date):
    """Gets stats for a specific date from the attendance table."""
    conn = get_connection()
    if not conn:
        return {"present": 0, "late": 0, "absent": 0}
    cursor = conn.cursor(dictionary=True)
    
    # In the new schema, we check status directly
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE DATE(timestamp) = %s AND status = 'Present'", (date,))
    present = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE DATE(timestamp) = %s AND status = 'Late'", (date,))
    late = cursor.fetchone()['count']
    
    # Absent calculation might need logic based on total students - present/late
    # For now, if we don't have a record, they are absent.
    cursor.execute("SELECT COUNT(*) as count FROM students")
    total_students = cursor.fetchone()['count']
    absent = total_students - (present + late)
    
    cursor.close()
    conn.close()
    
    return {"present": present, "late": late, "absent": max(0, absent)}

def get_student_attendance_history(student_id_code):
    """Retrieves attendance history for a specific student code."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT DATE(a.timestamp) as date, a.status, l.entry_time, l.exit_time, 
               CASE WHEN a.latitude IS NOT NULL THEN TRUE ELSE TRUE END as location_valid,
               c.course_name
        FROM attendance a
        LEFT JOIN courses c ON a.course_id = c.id
        LEFT JOIN attendance_logs l ON a.student_id_code = l.student_id_code AND DATE(a.timestamp) = l.date
        WHERE a.student_id_code = %s
        ORDER BY a.timestamp DESC
    ''', (student_id_code,))
    history = cursor.fetchall()
    
    # Format dates/times for frontend
    # MySQL returns TIME columns as timedelta objects, convert to HH:MM strings
    for entry in history:
        entry['date_str'] = entry['date'].strftime("%Y-%m-%d")
        
        def fmt_time(td):
            if td is None:
                return None
            total_secs = int(td.total_seconds())
            h = total_secs // 3600
            m = (total_secs % 3600) // 60
            return f"{h:02d}:{m:02d}"
        
        entry['entry_time'] = fmt_time(entry.get('entry_time'))
        entry['exit_time'] = fmt_time(entry.get('exit_time'))
    
    cursor.close()
    conn.close()
    
    return history

def check_user_credentials(email, password):
    """Checks user credentials using secure hashing."""
    from werkzeug.security import check_password_hash
    user = get_user_by_email(email)
    if user and check_password_hash(user['password'], password):
        return user
    return None

def get_all_users():
    """Returns a list of all users."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.role, u.created_at, s.student_id_code 
        FROM users u 
        LEFT JOIN students s ON u.id = s.user_id
    """)
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

# --- RBAC Helper Functions ---

def add_class(class_name):
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO classes (class_name) VALUES (%s)", (class_name,))
        conn.commit()
        return True, "Class added"
    except Exception as e:
        return False, f"Database Error: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def get_all_classes():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM classes")
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def get_class_stats():
    """Returns total student counts for each class."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT c.class_name, COUNT(s.id) as student_count
        FROM classes c
        LEFT JOIN students s ON c.id = s.class_id
        GROUP BY c.id, c.class_name
    """
    cursor.execute(query)
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def add_course(course_name):
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO courses (course_name) VALUES (%s)", (course_name,))
        conn.commit()
        return True, "Course added"
    except Exception as e:
        return False, f"Database Error: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def get_all_courses():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM courses")
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def assign_teacher(teacher_id, class_id, course_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO teacher_assignments (teacher_id, class_id, course_id) VALUES (%s, %s, %s)", 
                       (teacher_id, class_id, course_id))
        conn.commit()
        return True, "Assignment created"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_teacher_assignments(teacher_id=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if teacher_id:
        query = """
            SELECT ta.*, c.class_name, co.course_name, u.name as teacher_name
            FROM teacher_assignments ta
            JOIN classes c ON ta.class_id = c.id
            JOIN courses co ON ta.course_id = co.id
            JOIN users u ON ta.teacher_id = u.id
            WHERE ta.teacher_id = %s
        """
        cursor.execute(query, (teacher_id,))
    else:
        query = """
            SELECT ta.*, c.class_name, co.course_name, u.name as teacher_name
            FROM teacher_assignments ta
            JOIN classes c ON ta.class_id = c.id
            JOIN courses co ON ta.course_id = co.id
            JOIN users u ON ta.teacher_id = u.id
        """
        cursor.execute(query)
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def enroll_student_in_course(student_id, course_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO student_courses (student_id, course_id) VALUES (%s, %s)", (student_id, course_id))
        conn.commit()
        return True, "Enrolled"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_student_courses(student_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT sc.*, c.course_name 
        FROM student_courses sc 
        JOIN courses c ON sc.course_id = c.id 
        WHERE sc.student_id = %s
    """
    cursor.execute(query, (student_id,))
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def save_teacher_settings(teacher_id, class_id, course_id, start_time, end_time, lat, lon, radius):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO teacher_settings (teacher_id, class_id, course_id, start_time, end_time, gps_lat, gps_lon, radius)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            start_time = VALUES(start_time), end_time = VALUES(end_time), 
            gps_lat = VALUES(gps_lat), gps_lon = VALUES(gps_lon), radius = VALUES(radius)
        """
        cursor.execute(query, (teacher_id, class_id, course_id, start_time, end_time, lat, lon, radius))
        conn.commit()
        return True, "Settings saved"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_assignment_settings(class_id, course_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = "SELECT * FROM teacher_settings WHERE class_id = %s AND course_id = %s"
    cursor.execute(query, (class_id, course_id))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    return res

def get_active_settings_for_class(class_id, current_time_str):
    """
    Finds active teacher settings for a given class at a specific time.
    current_time_str should be in 'HH:MM:SS' format.
    """
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    
    # Handle midnight wrap logic in SQL if possible, or just fetch all and filter in Python
    # For simplicity and reliability with MySQL time formats, we'll fetch all and filter.
    query = "SELECT * FROM teacher_settings WHERE class_id = %s"
    cursor.execute(query, (class_id,))
    settings = cursor.fetchall()
    cursor.close()
    conn.close()
    
    active = []
    from datetime import datetime
    now_time = datetime.strptime(current_time_str, "%H:%M:%S").time()
    
    for s in settings:
        start_time = datetime.strptime(str(s['start_time']), "%H:%M:%S").time()
        end_time = datetime.strptime(str(s['end_time']), "%H:%M:%S").time()
        
        if start_time <= end_time:
            if start_time <= now_time <= end_time:
                active.append(s)
        else:
            # Cross-midnight
            if now_time >= start_time or now_time <= end_time:
                active.append(s)
    return active

def update_user_password(user_id, new_password_hash):
    """Updates a user's password in the database."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    cursor = conn.cursor()
    try:
        query = "UPDATE users SET password = %s WHERE id = %s"
        cursor.execute(query, (new_password_hash, user_id))
        conn.commit()
        return True, "Password updated successfully."
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def update_class(class_id, new_name):
    conn = get_connection()
    if not conn: return False, "DB Error"
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE classes SET class_name = %s WHERE id = %s", (new_name, class_id))
        conn.commit()
        return True, "Class updated"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def delete_class(class_id):
    conn = get_connection()
    if not conn: return False, "DB Error"
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        conn.commit()
        return True, "Class deleted"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def update_course(course_id, new_name):
    conn = get_connection()
    if not conn: return False, "DB Error"
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE courses SET course_name = %s WHERE id = %s", (new_name, course_id))
        conn.commit()
        return True, "Course updated"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def delete_course(course_id):
    conn = get_connection()
    if not conn: return False, "DB Error"
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
        conn.commit()
        return True, "Course deleted"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_students_by_assignment(class_id, course_id):
    """Returns students in a specific class who are enrolled in a specific course."""
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT s.*, u.name, u.email 
        FROM students s
        JOIN users u ON s.user_id = u.id
        JOIN student_courses sc ON s.id = sc.student_id
        WHERE s.class_id = %s AND sc.course_id = %s
    """
    cursor.execute(query, (class_id, course_id))
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def get_student_id_by_user_id(user_id):
    conn = get_connection()
    if not conn: return None
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT student_id_code FROM students WHERE user_id = %s", (user_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    return res['student_id_code'] if res else None

def get_attendance_history_by_course(course_id):
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT a.*, s.student_id_code, u.name, a.timestamp, a.status
        FROM attendance a
        JOIN students s ON a.student_id_code = s.student_id_code
        JOIN users u ON s.user_id = u.id
        WHERE a.course_id = %s
        ORDER BY a.timestamp DESC
    """
    cursor.execute(query, (course_id,))
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def is_student_enrolled(student_id, course_id):
    """Checks if a student is enrolled in a specific course."""
    conn = get_connection()
    if not conn: return False
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM student_courses WHERE student_id = %s AND course_id = %s", (student_id, course_id))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()

# --- NOTIFICATION SYSTEM FUNCTIONS ---

def create_notification(user_id, message):
    conn = get_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (user_id, message))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating notification: {e}")
        return False
    finally:
        conn.close()

def get_unread_notifications(user_id):
    conn = get_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM notifications WHERE user_id = %s AND is_read = FALSE ORDER BY created_at DESC", (user_id,))
        return cursor.fetchall()
    finally:
        conn.close()

def mark_notification_read(notification_id):
    conn = get_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (notification_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def get_teachers_by_class(class_id):
    conn = get_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch teachers assigned to this class
        cursor.execute("SELECT teacher_id FROM teacher_assignments WHERE class_id = %s", (class_id,))
        return cursor.fetchall()
    finally:
        conn.close()
    """
    Calculates comprehensive attendance analytics, marks, and recommendations
    for all students in a specific class and course.
    """
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Get the list of all students assigned to this class+course
        query_students = """
            SELECT s.id, s.student_id_code, u.name, u.email
            FROM students s
            JOIN users u ON s.user_id = u.id
            JOIN student_courses sc ON s.id = sc.student_id
            WHERE s.class_id = %s AND sc.course_id = %s
        """
        cursor.execute(query_students, (class_id, course_id))
        students = cursor.fetchall()
        
        if not students: return []

        # 2. Get the total number of sessions held for this class+course so far
        query_sessions = """
            SELECT COUNT(DISTINCT DATE(timestamp)) as total_sessions
            FROM attendance
            WHERE course_id = %s AND student_id_code IN (
                SELECT student_id_code FROM students WHERE class_id = %s
            )
        """
        cursor.execute(query_sessions, (course_id, class_id))
        row = cursor.fetchone()
        total_sessions = row['total_sessions'] if row and row['total_sessions'] else 0
        
        # 3. For each student, calculate their stats
        results = []
        for student in students:
            sid_code = student['student_id_code']
            
            # Count Present and Late
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_count,
                    COUNT(CASE WHEN status = 'Late' THEN 1 END) as late_count
                FROM attendance
                WHERE student_id_code = %s AND course_id = %s
            """, (sid_code, course_id))
            stats = cursor.fetchone()
            
            p_count = stats['present_count']
            l_count = stats['late_count']
            attended = p_count + l_count
            
            # Calculate Percentage
            percentage = (attended / total_sessions * 100) if total_sessions > 0 else 0
            
            # Calculate Marks (out of 10)
            marks = 0
            if percentage >= 90: marks = 10
            elif percentage >= 80: marks = 8
            elif percentage >= 70: marks = 6
            elif percentage >= 60: marks = 4
            else: marks = 0
            
            # Assign Status and Recommendation
            status_text = "Excellent"
            recommendation = "Maintain current progress."
            color = "success"
            
            if percentage < 60:
                status_text = "Critical"
                recommendation = "Urgent meeting required."
                color = "danger"
            elif percentage < 75:
                status_text = "At Risk"
                recommendation = "Intervention recommended."
                color = "warning"
            elif percentage < 90:
                status_text = "Good"
                recommendation = "Aim for 100% attendance."
                color = "primary"
                
            # Extra Check: Lateness
            lateness_rate = (l_count / attended * 100) if attended > 0 else 0
            if lateness_rate > 30:
                recommendation += " High lateness noted."

            results.append({
                "student_id": sid_code,
                "name": student['name'],
                "email": student['email'],
                "attended": attended,
                "total_sessions": total_sessions,
                "percentage": round(percentage, 1),
                "marks": marks,
                "status": status_text,
                "color": color,
                "recommendation": recommendation
            })
            
        return results
        
    except Exception as e:
        print(f"Analytics Error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    initialize_database()
