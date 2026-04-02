from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from functools import wraps
import os
import cv2
import numpy as np
import base64
from datetime import datetime, timedelta
import json
from geopy.distance import geodesic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import database
from ai import recognize_engine
from ai import train_model as trainer
import reports.auto_report as auto_report
from reports.auto_report import generate_pdf_report
import traceback
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secret_attendance_key")
CONFIG_FILE = "config.json"

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "admin_password": "password",
        "campus_coords": [40.7128, -74.0060],
        "allowable_radius_km": 0.5,
        "class_start_time": "09:00:00",
        "class_stop_time": "11:00:00"
    }

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "message": "Login required."}), 401
                return redirect(url_for('login', next=request.url))
            
            if session.get('role') not in roles:
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "message": f"Access denied for {session.get('role')}."}), 403
                
                flash(f"Access denied for {session.get('role')}.", "danger")
                # Redirect to role-appropriate home
                if session.get('role') == 'Student':
                    return redirect(url_for('student_portal'))
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    # Log the full traceback to terminal for debugging
    print("--- SERVER ERROR TRACEBACK ---")
    traceback.print_exc() 
    print("-------------------------------")
    return jsonify({
        "success": False, 
        "message": f"Server Exception: {str(e)}", 
        "traceback": traceback.format_exc()
    }), 500


@app.route('/')
def index():
    if 'role' in session:
        if session['role'] == 'Student':
            return redirect(url_for('student_portal'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = database.check_user_credentials(email, password)
        if user:
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            flash(f"Welcome, {user['name']}!", "success")
            
            # Redirect based on role
            if user['role'] == 'Student':
                return redirect(url_for('student_portal', student_id=user['id'])) # Temporary, students don't have dashboard
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/settings', methods=['GET', 'POST'])
@role_required(['Admin'])
def settings():
    config = load_config()
    if request.method == 'POST':
        try:
            config['campus_coords'] = [float(request.form.get('lat')), float(request.form.get('lon'))]
            config['allowable_radius_km'] = float(request.form.get('radius'))
            config['class_start_time'] = request.form.get('time_start')
            config['class_stop_time'] = request.form.get('time_stop')
            
            new_password = request.form.get('password')
            if new_password and new_password.strip():
                config['admin_password'] = new_password.strip()
                
            save_config(config)
            flash("Settings updated successfully!", "success")
        except ValueError:
            flash("Invalid format provided.", "danger")
            
    return render_template('settings.html', config=config)

@app.route('/dashboard')
@role_required(['Admin', 'Teacher'])
def dashboard():
    role = session.get('role')
    if role == 'Admin':
        students = database.get_all_students()
        class_stats = database.get_class_stats()
        return render_template('dashboard.html', students=students, class_stats=class_stats)
    elif role == 'Teacher':
        teacher_id = session.get('user_id')
        assignments = database.get_teacher_assignments(teacher_id)
        
        # Add status to each assignment
        current_time_str = datetime.now().strftime("%H:%M:%S")
        for assgn in assignments:
            settings = database.get_assignment_settings(assgn['class_id'], assgn['course_id'])
            assgn['settings'] = settings
            
            is_active = False
            if settings:
                now_time = datetime.now().time()
                # Use string conversion as a safer way to handle MySQL TIME objects
                s_time = str(settings['start_time'])
                e_time = str(settings['end_time'])
                
                # Ensure HH:MM:SS format (MySQL might return H:MM:SS)
                if len(s_time.split(':')[0]) == 1: s_time = '0' + s_time
                if len(e_time.split(':')[0]) == 1: e_time = '0' + e_time
                
                start_time = datetime.strptime(s_time, "%H:%M:%S").time()
                end_time = datetime.strptime(e_time, "%H:%M:%S").time()
                
                if start_time <= end_time:
                    is_active = (start_time <= now_time <= end_time)
                else:
                    is_active = (now_time >= start_time or now_time <= end_time)
            
            assgn['is_active'] = is_active
            
        # Teacher Dashboard Overview Data
        stats = database.get_teacher_stats(teacher_id, datetime.now().date())
        students = database.get_teacher_students(teacher_id)
        
        return render_template('teacher_dashboard.html', 
                               assignments=assignments, 
                               stats=stats, 
                               students=students,
                               notifications=database.get_unread_notifications(session['user_id']))
    return redirect(url_for('index'))

@app.route('/api/update_session', methods=['POST'])
@role_required(['Admin', 'Teacher'])
def update_session():
    """Allows Teachers/Admins to update the current attendance session times."""
    data = request.json
    config = load_config()
    try:
        if 'start_time' in data:
            config['class_start_time'] = data['start_time']
        if 'stop_time' in data:
            config['class_stop_time'] = data['stop_time']
        save_config(config)
        return jsonify({"success": True, "message": "Session updated successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/start_session', methods=['POST'])
@role_required(['Teacher', 'Admin'])
def start_attendance_session():
    data = request.json
    class_id = data.get('class_id')
    course_id = data.get('course_id')
    teacher_id = session.get('user_id')
    
    now = datetime.now()
    start_time = now.strftime("%H:%M:%S")
    end_time = (now + timedelta(hours=2)).strftime("%H:%M:%S")
    
    # Get current GPS if provided, else use last settings
    settings = database.get_assignment_settings(class_id, course_id)
    lat = data.get('lat', settings['gps_lat'] if settings else 0.0)
    lon = data.get('lon', settings['gps_lon'] if settings else 0.0)
    radius = settings['radius'] if settings else 0.5
    
    success, msg = database.save_teacher_settings(teacher_id, class_id, course_id, start_time, end_time, lat, lon, radius)
    return jsonify({"success": success, "message": "Session started until " + end_time if success else msg})

@app.route('/api/stop_session', methods=['POST'])
@role_required(['Teacher', 'Admin'])
def stop_attendance_session():
    data = request.json
    class_id = data.get('class_id')
    course_id = data.get('course_id')
    teacher_id = session.get('user_id')
    
    settings = database.get_assignment_settings(class_id, course_id)
    if not settings:
        return jsonify({"success": False, "message": "No settings found."})
        
    # Set end_time to now
    now = datetime.now().strftime("%H:%M:%S")
    success, msg = database.save_teacher_settings(teacher_id, class_id, course_id, settings['start_time'], now, 
                                                   settings['gps_lat'], settings['gps_lon'], settings['radius'])
    return jsonify({"success": success, "message": "Session stopped." if success else msg})

@app.route('/users')
@role_required(['Admin'])
def users():
    all_users = database.get_all_users()
    return render_template('users.html', users=all_users)

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@role_required(['Admin'])
def edit_user(user_id):
    user = database.get_user_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('users'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        password = request.form.get('password')
        
        success, message = database.update_user(user_id, name, email, role)
        if success:
            if password and password.strip():
                from werkzeug.security import generate_password_hash
                hashed_pw = generate_password_hash(password.strip())
                database.update_user_password(user_id, hashed_pw)
                message += " and password reset"
            flash(message, "success")
            return redirect(url_for('users'))
        else:
            flash(message, "danger")
            
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>')
@role_required(['Admin'])
def delete_user(user_id):
    # Prevent admin from deleting themselves
    if user_id == session.get('user_id'):
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for('users'))
        
    success, message = database.delete_user(user_id)
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")
    return redirect(url_for('users'))

@app.route('/classes', methods=['GET', 'POST'])
@role_required(['Admin'])
def manage_classes():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        if class_name:
            success, msg = database.add_class(class_name)
            flash(msg, "success" if success else "danger")
    
    classes = database.get_all_classes()
    return render_template('classes.html', classes=classes)

@app.route('/courses', methods=['GET', 'POST'])
@role_required(['Admin'])
def manage_courses():
    if request.method == 'POST':
        course_name = request.form.get('course_name')
        if course_name:
            success, msg = database.add_course(course_name)
            flash(msg, "success" if success else "danger")
            
    courses = database.get_all_courses()
    return render_template('courses.html', courses=courses)

@app.route('/edit_class/<int:class_id>', methods=['GET', 'POST'])
@role_required(['Admin'])
def edit_class(class_id):
    if request.method == 'POST':
        new_name = request.form.get('class_name')
        if new_name:
            success, msg = database.update_class(class_id, new_name)
            flash(msg, "success" if success else "danger")
            return redirect(url_for('manage_classes'))
    
    # Simple edit page or just redirect back? We'll need a way to show current name
    # For now, let's assume classes.html handles the modal/form
    return redirect(url_for('manage_classes'))

@app.route('/delete_class/<int:class_id>')
@role_required(['Admin'])
def delete_class(class_id):
    success, msg = database.delete_class(class_id)
    flash(msg, "success" if success else "danger")
    return redirect(url_for('manage_classes'))

@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
@role_required(['Admin'])
def edit_course(course_id):
    if request.method == 'POST':
        new_name = request.form.get('course_name')
        if new_name:
            success, msg = database.update_course(course_id, new_name)
            flash(msg, "success" if success else "danger")
            return redirect(url_for('manage_courses'))
    return redirect(url_for('manage_courses'))

@app.route('/delete_course/<int:course_id>')
@role_required(['Admin'])
def delete_course(course_id):
    success, msg = database.delete_course(course_id)
    flash(msg, "success" if success else "danger")
    return redirect(url_for('manage_courses'))

@app.route('/assignments', methods=['GET', 'POST'])
@role_required(['Admin'])
def manage_assignments():
    if request.method == 'POST':
        teacher_id = request.form.get('teacher_id')
        class_id = request.form.get('class_id')
        course_id = request.form.get('course_id')
        if teacher_id and class_id and course_id:
            success, msg = database.assign_teacher(teacher_id, class_id, course_id)
            flash(msg, "success" if success else "danger")
            
    assignments = database.get_teacher_assignments()
    teachers = [u for u in database.get_all_users() if u['role'] == 'Teacher']
    classes = database.get_all_classes()
    courses = database.get_all_courses()
    
    return render_template('assignments.html', 
                           assignments=assignments, 
                           teachers=teachers, 
                           classes=classes, 
                           courses=courses)

@app.route('/teacher_settings/<int:class_id>/<int:course_id>', methods=['GET', 'POST'])
@role_required(['Teacher', 'Admin'])
def teacher_settings(class_id, course_id):
    teacher_id = session.get('user_id')
    if request.method == 'POST':
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        radius = request.form.get('radius', 0.5)
        
        success, msg = database.save_teacher_settings(teacher_id, class_id, course_id, start_time, end_time, lat, lon, radius)
        flash(msg, "success" if success else "danger")
        
    settings = database.get_assignment_settings(class_id, course_id)
    return render_template('teacher_settings.html', settings=settings, class_id=class_id, course_id=course_id)

@app.route('/view_attendance/<int:class_id>/<int:course_id>')
@role_required(['Teacher', 'Admin'])
def view_attendance(class_id, course_id):
    # Fetch detailed historical logs
    history = database.get_attendance_history_by_course(course_id)
    # Fetch consolidated analytics and marks
    analytics = database.get_attendance_analytics(class_id, course_id)
    
    # Get course name for display
    conn = database.get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT course_name FROM courses WHERE id = %s", (course_id,))
    course_row = cursor.fetchone()
    course_name = course_row['course_name'] if course_row else f"ID: {course_id}"
    cursor.close()
    conn.close()
    
    # Date range for heading
    today = datetime.now().strftime("%Y-%m-%d")
    
    return render_template('attendance_view.html', 
                           attendance=history, 
                           analytics=analytics,
                           class_id=class_id, 
                           course_id=course_id,
                           course_name=course_name,
                           start_date=today,
                           end_date=today)

@app.route('/view_students/<int:class_id>/<int:course_id>')
@role_required(['Teacher', 'Admin'])
def view_students(class_id, course_id):
    students = database.get_students_by_assignment(class_id, course_id)
    
    # Get class/course names for display
    conn = database.get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT class_name FROM classes WHERE id = %s", (class_id,))
    class_name = cursor.fetchone()['class_name']
    cursor.execute("SELECT course_name FROM courses WHERE id = %s", (course_id,))
    course_name = cursor.fetchone()['course_name']
    cursor.close()
    conn.close()
    
    return render_template('view_students.html', 
                           students=students, 
                           class_id=class_id, 
                           course_id=course_id,
                           class_name=class_name,
                           course_name=course_name)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        student_id = data.get('student_id')
        
        student = database.get_student(student_id)
        if student:
            return jsonify({"success": False, "message": "Student ID already exists in the database."})
            
        return jsonify({"success": True, "message": "Details clear. Proceed to Face Capture."})
        
    is_admin = (session.get('role') == 'Admin')
    return render_template('register.html', classes=database.get_all_classes(), is_admin=is_admin) # Pass classes to template

@app.route('/api/finalize_registration', methods=['POST'])
def finalize_registration():
    data = request.json
    registration_id = data.get('student_id')
    name = data.get('name')
    email = data.get('email')
    password = data.get('password', 'default_password')
    
    # Security Check: Only Admin can set roles other than 'Student'
    role = data.get('role', 'Student')
    if session.get('role') != 'Admin':
        role = 'Student'
    
    class_id = data.get('class_id') # New field
    
    from werkzeug.security import generate_password_hash
    hashed_pw = generate_password_hash(password)
    
    user = database.get_user_by_email(email)
    if user:
        return jsonify({"success": False, "message": "Email already registered."})
    
    user_success, user_msg = database.register_user(name, email, hashed_pw, role)
    if not user_success:
        return jsonify({"success": False, "message": f"User Registration Error: {user_msg}"})
    
    user_id = user_msg
    
    if role == 'Student':
        success, msg = database.register_student(registration_id, user_id, class_id)
        if success:
            if class_id:
                # Notify teachers of this class
                teachers = database.get_teachers_by_class(class_id)
                for t in teachers:
                    database.create_notification(t['teacher_id'], f"New student '{name}' (ID: {registration_id}) has registered for your class.")
            
            # Automatically train the model with the newly captured images
            try:
                trainer.train_model()
                recognize_engine.reload_model()
                msg += " AI Model automatically trained with new faces."
            except Exception as e:
                msg += f" (Model training failed: {str(e)})"
                
    elif role == 'Teacher':
        success, msg = database.register_teacher(registration_id, user_id)
    elif role == 'Admin':
        success, msg = True, "Admin created."
    else:
        success, msg = False, "Invalid role selected."

    return jsonify({"success": success, "message": msg})

@app.route('/api/save_image', methods=['POST'])
def save_image():
    """Saves a base64 image string to the dataset folder for a student, checking for duplicates first"""
    data = request.json
    student_id = data.get('student_id')
    image_b64 = data.get('image')
    
    if not student_id or not image_b64:
        return jsonify({"success": False, "message": "Missing data"}), 400
        
    # Extract base64 part
    try:
        header, encoded = image_b64.split(",", 1)
        img_data = base64.b64decode(encoded)
        
        # Check for duplicate face before saving
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"success": False, "message": "Failed to decode image. Frame is empty."}), 400
            
    except Exception as e:
        return jsonify({"success": False, "message": f"Invalid image data: {str(e)}"}), 400
    
    # recognize faces does not need anti spoofing during reg capture
    results = recognize_engine.recognize_faces_in_frame(frame, enforce_anti_spoofing=False)
    
    for face in results:
        matched_id = face['name']
        if matched_id != "Unknown" and matched_id != student_id:
            # Face already exists under a different ID!
            matched_user = database.get_student(matched_id)
            if not matched_user:
                matched_user = database.get_teacher(matched_id)
                
            matched_name = matched_user['name'] if matched_user else "Unknown Name"
            
            return jsonify({
                "success": False, 
                "message": f"Face already registered under ID: {matched_id} (Name: {matched_name})", 
                "duplicate": True
            })
            
    folder_path = os.path.join("dataset", student_id)
    os.makedirs(folder_path, exist_ok=True)
    
    # Count existing images
    img_count = len(os.listdir(folder_path))
    filename = os.path.join(folder_path, f"img_{img_count}.jpg")
    
    with open(filename, "wb") as f:
        f.write(img_data)
        
    return jsonify({"success": True, "message": "Image saved.", "count": img_count + 1})

@app.route('/api/train', methods=['POST'])
@role_required(['Admin', 'Teacher'])
def train():
    """Triggers model retraining from dataset folder"""
    success = trainer.train_model()
    recognize_engine.reload_model()
    message = "Model trained successfully." if success else "Failed to train model."
    return jsonify({"success": success, "message": message})

@app.route('/live_feed')
@role_required(['Admin', 'Teacher', 'Student'])
def live_feed_page():
    config = load_config()
    return render_template('live_feed.html', config=config)

@app.route('/api/recognize', methods=['POST'])
@role_required(['Admin', 'Teacher', 'Student'])
def recognize():
    """
    RBAC-Aware Recognition: Validates students against their assigned class and 
    currently active courses (teacher settings).
    """
    data = request.json
    image_b64 = data.get('image')
    lat = data.get('lat')
    lon = data.get('lon')
    
    if not image_b64:
        return jsonify({"success": False, "message": "No image provided."})
        
    current_time = datetime.now()
    current_time_str = current_time.strftime("%H:%M:%S")
         
    # Decode base64 
    try:
        header, encoded = image_b64.split(",", 1)
        img_data = base64.b64decode(encoded)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
             return jsonify({"success": False, "message": "Failed to decode image."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Invalid image data: {str(e)}"})
    
    # Recognize faces
    results = recognize_engine.recognize_faces_in_frame(frame, enforce_anti_spoofing=True)
    
    logs = []
    for face in results:
        student_id_code = face['name']
        box = face.get('box')
        confidence = face.get('confidence', 0)
        
        if face.get('spoof'):
            msg = face.get('spoof_message', "Liveness check failed. Please blink.")
            logs.append({
                "student_id": "Spoof", 
                "student_name": "Spoof Detected",
                "success": False, 
                "message": msg, 
                "box": box,
                "confidence": confidence
            })
            continue
            
        if student_id_code == "Unknown":
            logs.append({
                "student_id": "Unknown", 
                "student_name": "Unrecognized Face",
                "success": False, 
                "message": "Face not recognized.", 
                "box": box,
                "confidence": confidence
            })
            continue

        # 1. Get Student & their Class
        student = database.get_student(student_id_code)
        if not student:
            # Stale pickle ID — silently skip, no UI spam
            print(f"[WARN] Stale model: matched ID '{student_id_code}' not in DB. Retrain the model.")
            continue
            
        student_name = student['name']
        class_id = student.get('class_id')
        
        # 2. Find active courses for this class
        active_settings = database.get_active_settings_for_class(class_id, current_time_str)
        
        if not active_settings:
            logs.append({
                "student_id": student_id_code, 
                "student_name": student_name,
                "success": False, 
                "message": "No active class session at this time.", 
                "box": box,
                "confidence": confidence
            })
            continue
            
        # 3. Log for each active course
        for setting in active_settings:
            course_id = setting['course_id']
            
            # Location Validation
            location_valid = True
            gps_message = ""
            if setting.get('gps_lat') and setting.get('gps_lon'):
                if lat is not None and lon is not None:
                    user_coords = (float(lat), float(lon))
                    target_coords = (setting['gps_lat'], setting['gps_lon'])
                    distance = geodesic(target_coords, user_coords).km
                    if distance > setting['radius']:
                        location_valid = False
                        gps_message = f"Out of range ({distance:.2f}km)"
                else:
                    location_valid = False
                    gps_message = "GPS location required"
            
            # Time Formatting Fix for MySQL timedelta/string objects
            s_time = str(setting['start_time'])
            e_time = str(setting['end_time'])
            if len(s_time.split(':')[0]) == 1: s_time = '0' + s_time
            if len(e_time.split(':')[0]) == 1: e_time = '0' + e_time

            # Log Attendance (only if location is valid)
            if location_valid:
                success, msg = database.log_attendance(
                    student_id_code, 
                    course_id, 
                    current_time, 
                    datetime.strptime(s_time, "%H:%M:%S").time(),
                    datetime.strptime(e_time, "%H:%M:%S").time(),
                    lat, lon
                )
            else:
                success, msg = False, gps_message

            logs.append({
                "student_id": student_id_code, 
                "student_name": student_name,
                "course_id": course_id, 
                "success": success, 
                "location_valid": location_valid,
                "message": msg, 
                "box": box,
                "confidence": confidence
            })
    
    # If no faces detected at all, return an empty logs array (frontend shows nothing)
    if not results:
        return jsonify({"success": True, "logs": [], "count": 0, "status": "no_face_detected"})
    
    return jsonify({"success": True, "logs": logs, "count": len(results)})

@app.route('/analytics')
@role_required(['Admin', 'Teacher'])
def analytics():
    today = datetime.now().date()
    stats = database.get_attendance_stats(today)
    return render_template('analytics.html', stats=stats)

@app.route('/student_portal', methods=['GET', 'POST'])
@role_required(['Admin', 'Teacher', 'Student'])
def student_portal():
    # If logged in as student, they can only see their own ID
    if session.get('role') == 'Student':
        user = database.get_user_by_id(session['user_id'])
        # We need to find the student_id_code for this user
        conn = database.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT student_id_code FROM students WHERE user_id = %s", (session['user_id'],))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row:
            flash("Student record not found for this user.", "danger")
            return redirect(url_for('index'))
        
        student_id = row['student_id_code']
    else:
        # Admin/Teacher can specify student_id
        student_id = request.form.get('student_id', '') if request.method == 'POST' else request.args.get('student_id', '')
    
    history = []
    student_name = ""
    
    if student_id:
        student = database.get_student(student_id)
        if student:
            student_name = student['name']
            history = database.get_student_attendance_history(student_id)
            
    # For enrollment, we need all courses
    all_courses = database.get_all_courses()
    enrolled_courses = database.get_student_courses(session['user_id']) if session.get('role') == 'Student' else []
    enrolled_ids = [c['course_id'] for c in enrolled_courses]
    
    return render_template('student_portal.html', 
                           history=history, 
                           student_id=student_id, 
                           student_name=student_name,
                           all_courses=all_courses,
                           enrolled_ids=enrolled_ids)

@app.route('/enroll_course', methods=['POST'])
@role_required(['Student'])
def enroll_course():
    course_id = request.form.get('course_id')
    user_id = session.get('user_id')
    
    # Get student internal ID
    student_id_code = database.get_student_id_by_user_id(user_id)
    student = database.get_student(student_id_code)
    
    if student and course_id:
        success, msg = database.enroll_student_in_course(student['id'], course_id)
        flash(msg, "success" if success else "danger")
    return redirect(url_for('student_portal'))

@app.route('/re_capture_face')
@role_required(['Student', 'Admin'])
def re_capture_face():
    # If Admin, they can specify a student_id in the URL
    student_id_code = request.args.get('student_id')
    
    # If Student, or no student_id provided for Admin, use own ID
    if session.get('role') == 'Student' or not student_id_code:
        user_id = session.get('user_id')
        student_id_code = database.get_student_id_by_user_id(user_id)
        
    return render_template('re_capture.html', student_id=student_id_code)

@app.route('/api/update_face_data', methods=['POST'])
@role_required(['Student', 'Admin'])
def update_face_data():
    # This will be called after capturing new images
    # Students can only update their own, Admins can update any (implicit in current design)
    success = trainer.train_model()
    recognize_engine.reload_model()
    return jsonify({"success": success, "message": "Face data updated and model retrained."})

@app.route('/api/export_report')
@role_required(['Admin', 'Teacher'])
def export_report():
    """Generates and returns export path for attendance CSV"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    filepath = auto_report.export_today_csv(today_str)
    if filepath:
        return jsonify({"success": True, "file": filepath})
    return jsonify({"success": False, "message": "No data or export failed."})

@app.route('/api/export_pdf/<report_type>')
@app.route('/api/export_pdf/<report_type>/<int:course_id>')
@role_required(['Admin', 'Teacher'])
def export_pdf(report_type, course_id=None):
    """Generates and returns export path for attendance PDF (daily/weekly/monthly)"""
    if report_type not in ['daily', 'weekly', 'monthly']:
        return jsonify({"success": False, "message": "Invalid report type."}), 400
        
    filepath = generate_pdf_report(report_type, course_id=course_id)
    if filepath:
        return send_file(filepath, as_attachment=True)
    return jsonify({"success": False, "message": f"No data found for {report_type} report, or export failed."})

@app.route('/profile')
@role_required(['Admin', 'Teacher', 'Student'])
def profile():
    user = database.get_user_by_id(session['user_id'])
    student_id_code = None
    if user['role'] == 'Student':
        # Get student ID code for display
        conn = database.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT student_id_code FROM students WHERE user_id = %s", (user['id'],))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            student_id_code = row['student_id_code']
            
    return render_template('profile.html', user=user, student_id_code=student_id_code)

@app.route('/profile/change_password', methods=['POST'])
@role_required(['Admin', 'Teacher', 'Student'])
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        flash("All fields are required.", "danger")
        return redirect(url_for('profile'))
        
    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for('profile'))
        
    user = database.get_user_by_id(session['user_id'])
    if not check_password_hash(user['password'], current_password):
        flash("Incorrect current password.", "danger")
        return redirect(url_for('profile'))
        
    # Update password
    new_hash = generate_password_hash(new_password)
    success, msg = database.update_user_password(user['id'], new_hash)
    if success:
        flash("Password updated successfully.", "success")
    else:
        flash(f"Error updating password: {msg}", "danger")
        
    return redirect(url_for('profile'))


@app.route('/api/system_report/<report_type>')
@role_required(['Admin'])
def system_report(report_type):
    """Generates and serves system administrative reports for Admins."""
    from reports import auto_report
    filepath = auto_report.generate_system_report(report_type)
    if filepath and os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    flash("Error generating system report or no data found.", "warning")
    return redirect(url_for('dashboard'))


@app.route('/api/dismiss_notification/<int:notification_id>', methods=['POST'])
@role_required(['Teacher', 'Admin'])
def dismiss_notification(notification_id):
    success = database.mark_notification_read(notification_id)
    return jsonify({"success": success})

if __name__ == '__main__':
    database.initialize_database()
    app.run(debug=True, port=5000)
