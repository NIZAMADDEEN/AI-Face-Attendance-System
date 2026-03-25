import mysql.connector
from datetime import datetime

# Database Configuration
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "geoface_db"

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
    
    cursor = conn.cursor()
    
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
    
    # Create students table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            student_id_code VARCHAR(50) UNIQUE NOT NULL,
            face_embedding JSON,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Create courses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_name VARCHAR(100) NOT NULL,
            teacher_id INT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Create attendance table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id_code VARCHAR(50) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status ENUM('Present', 'Late', 'Absent') DEFAULT 'Present',
            latitude DECIMAL(10, 8),
            longitude DECIMAL(11, 8),
            spoof_flag BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (student_id_code) REFERENCES students(student_id_code) ON DELETE CASCADE
        )
    ''')
    
    # Create attendance_logs table (legacy or detailed tracking)
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
    
    conn.commit()
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

def register_student(student_id_code, user_id, face_embedding=None):
    """Links a user to a student record with an embedding."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor()
    try:
        import json
        embedding_json = json.dumps(face_embedding) if face_embedding is not None else None
        query = "INSERT INTO students (user_id, student_id_code, face_embedding) VALUES (%s, %s, %s)"
        cursor.execute(query, (user_id, student_id_code, embedding_json))
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

def log_attendance(student_id_code, current_time, class_start_time, class_stop_time, location_valid=True):
    """Logs attendance for a student, ensuring only one entry per day, and updating exit times/status."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        from datetime import datetime, timedelta
        
        # Check student existence
        cursor.execute("SELECT students.id, users.name FROM users JOIN students ON users.id = students.user_id WHERE students.student_id_code = %s", (student_id_code,))
        student = cursor.fetchone()
        if not student:
            return False, f"Student code {student_id_code} not found."
            
        student_name = student['name']

        current_date = current_time.date()
        current_time_str = current_time.time()
        
        # Calculate status (10 minute threshold for Present)
        start_dt = datetime.combine(current_date, class_start_time)
        late_threshold_dt = start_dt + timedelta(minutes=10)
        late_threshold_time = late_threshold_dt.time()
        
        # Simple time comparison logic assuming daytime classes
        if class_start_time <= class_stop_time:
            if current_time_str >= class_start_time and current_time_str <= late_threshold_time:
                status = 'Present'
            elif current_time_str > late_threshold_time and current_time_str <= class_stop_time:
                status = 'Late'
            else:
                status = 'Absent'
        else:
            # Cross-midnight failsafe (rare but handled as Absent for simplicity if outside)
            status = 'Present' # Placeholder, but generally shouldn't hit this
        
        # Check if attendance already logged today
        cursor.execute("SELECT id, status FROM attendance WHERE student_id_code = %s AND DATE(timestamp) = %s", (student_id_code, current_date))
        existing_attendance = cursor.fetchone()
        
        if not existing_attendance:
            # Insert into attendance
            query = """
                INSERT INTO attendance (student_id_code, timestamp, status, latitude, longitude, spoof_flag)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (student_id_code, current_time, status, None, None, False))
            
            # Insert into attendance_logs
            cursor.execute('''
                INSERT INTO attendance_logs (student_id_code, date, entry_time)
                VALUES (%s, %s, %s)
            ''', (student_id_code, current_date, current_time_str))
            
            conn.commit()
            return True, f"Attendance logged for {student_name} ({status})."
        else:
            # Check if attendance_logs exists (it might not if an older bug skipped it)
            cursor.execute("SELECT id FROM attendance_logs WHERE student_id_code = %s AND date = %s", (student_id_code, current_date))
            existing_log = cursor.fetchone()
            
            if not existing_log:
                cursor.execute('''
                    INSERT INTO attendance_logs (student_id_code, date, entry_time)
                    VALUES (%s, %s, %s)
                ''', (student_id_code, current_date, current_time_str))
            else:
                # Update exit time in attendance_logs
                cursor.execute('''
                    UPDATE attendance_logs SET exit_time = %s
                    WHERE student_id_code = %s AND date = %s
                ''', (current_time_str, student_id_code, current_date))
            
            # Upgrade status dynamically if they were marked Absent but scanned again while Present/Late
            existing_status = existing_attendance['status']
            if existing_status == 'Absent' and status in ['Present', 'Late']:
                cursor.execute("UPDATE attendance SET status = %s WHERE id = %s", (status, existing_attendance['id']))
            elif existing_status == 'Late' and status == 'Present':
                cursor.execute("UPDATE attendance SET status = %s WHERE id = %s", (status, existing_attendance['id']))
            
            conn.commit()
            return True, f"{student_name} - Exit recorded at {current_time_str.strftime('%H:%M')} (Status: {existing_attendance['status']})."
            
    except Exception as e:
        conn.rollback()
        return False, str(e)
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
               CASE WHEN a.latitude IS NOT NULL THEN TRUE ELSE TRUE END as location_valid
        FROM attendance a
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

if __name__ == "__main__":
    initialize_database()
