import mysql.connector
from datetime import datetime

# Database Configuration
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "attendance_system"

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
    
    # Create students table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create attendance table (daily status)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id VARCHAR(50) NOT NULL,
            date DATE NOT NULL,
            status ENUM('Present', 'Late', 'Absent') DEFAULT 'Absent',
            location_valid BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            UNIQUE KEY specific_date_attendance (student_id, date)
        )
    ''')
    
    # Create attendance_logs table (exact entry/exit times)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id VARCHAR(50) NOT NULL,
            date DATE NOT NULL,
            entry_time TIME,
            exit_time TIME,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            UNIQUE KEY specific_date_log (student_id, date)
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database and tables initialized successfully.")

def register_student(student_id, name, email):
    """Registers a new student into the database."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    cursor = conn.cursor()
    try:
        query = "INSERT INTO students (student_id, name, email) VALUES (%s, %s, %s)"
        cursor.execute(query, (student_id, name, email))
        conn.commit()
        return True, "Student registered successfully."
    except mysql.connector.IntegrityError:
        return False, "Student ID already exists."
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_student(student_id):
    """Retrieves student information."""
    conn = get_connection()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM students WHERE student_id = %s"
        cursor.execute(query, (student_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching student: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def log_attendance(student_id, current_time, class_start_time, location_valid=True):
    """Logs or updates attendance entry/exit for a student."""
    conn = get_connection()
    if not conn:
        return False, "Database connection failed"
    
    current_date = current_time.date()
    current_time_str = current_time.time()
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch the student name for personalized logging
        cursor.execute("SELECT name FROM students WHERE student_id = %s", (student_id,))
        student_record = cursor.fetchone()
        student_name = student_record['name'] if student_record else "Unknown Name"

        # Check if log exists for today
        cursor.execute("SELECT * FROM attendance_logs WHERE student_id = %s AND date = %s", (student_id, current_date))
        log = cursor.fetchone()
        
        status = 'Present'
        # Determine status (Late if current time is after class_start_time)
        if current_time_str > class_start_time.time():
            status = 'Late'

        if not log:
            # First time scanning today: Log ENTRY
            cursor.execute('''
                INSERT INTO attendance_logs (student_id, date, entry_time)
                VALUES (%s, %s, %s)
            ''', (student_id, current_date, current_time_str))
            
            # Also insert into daily attendance overview
            cursor.execute('''
                INSERT INTO attendance (student_id, date, status, location_valid)
                VALUES (%s, %s, %s, %s)
            ''', (student_id, current_date, status, location_valid))
            
            conn.commit()
            msg = f"Attendance logged for {student_name} ({status})."
            return True, {"status": status, "message": msg}
        else:
            # Scanned again later in the day: Log EXIT
            cursor.execute('''
                UPDATE attendance_logs SET exit_time = %s
                WHERE student_id = %s AND date = %s
            ''', (current_time_str, student_id, current_date))
            conn.commit()
            
            msg = f"Exit logged for {student_name} at {current_time_str.strftime('%H:%M')}."
            return True, {"status": "Exit", "message": msg}
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def get_all_students():
    """Returns a list of all students."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return students

def get_attendance_stats(date):
    """Gets stats for a specific date."""
    conn = get_connection()
    if not conn:
        return {"present": 0, "late": 0, "absent": 0}
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE date = %s AND status = 'Present'", (date,))
    present = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE date = %s AND status = 'Late'", (date,))
    late = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE date = %s AND status = 'Absent'", (date,))
    absent = cursor.fetchone()['count']
    
    cursor.close()
    conn.close()
    
    return {"present": present, "late": late, "absent": absent}

def get_student_attendance_history(student_id):
    """Yields attendance records for a student."""
    conn = get_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT a.date, a.status, l.entry_time, l.exit_time, a.location_valid
        FROM attendance a
        LEFT JOIN attendance_logs l ON a.student_id = l.student_id AND a.date = l.date
        WHERE a.student_id = %s
        ORDER BY a.date DESC
    ''', (student_id,))
    history = cursor.fetchall()
    
    # Convert timedelta to string since strict time type isn't globally json serializable
    for entry in history:
        if entry['entry_time']:
            entry['entry_time'] = str(entry['entry_time'])
        if entry['exit_time']:
            entry['exit_time'] = str(entry['exit_time'])
    
    cursor.close()
    conn.close()
    
    return history

if __name__ == "__main__":
    initialize_database()
