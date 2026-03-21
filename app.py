from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from functools import wraps
import os
import cv2
import numpy as np
import base64
from datetime import datetime
import json
from geopy.distance import geodesic

import database
from ai import recognize_engine
from ai import train_model as trainer
import reports.auto_report as auto_report
from reports.auto_report import generate_pdf_report
import traceback
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
app.secret_key = "super_secret_attendance_key"
CONFIG_FILE = "config.json"

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "admin_password": "password",
        "campus_coords": [40.7128, -74.0060],
        "allowable_radius_km": 0.5,
        "class_start_time": "09:00:00"
    }

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    return jsonify({
        "success": False, 
        "message": f"Server Exception: {str(e)}", 
        "traceback": traceback.format_exc()
    }), 500


@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        config = load_config()
        if request.form.get('password') == config['admin_password']:
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    config = load_config()
    if request.method == 'POST':
        try:
            config['campus_coords'] = [float(request.form.get('lat')), float(request.form.get('lon'))]
            config['allowable_radius_km'] = float(request.form.get('radius'))
            config['class_start_time'] = request.form.get('time')
            
            new_password = request.form.get('password')
            if new_password and new_password.strip():
                config['admin_password'] = new_password.strip()
                
            save_config(config)
            flash("Settings updated successfully!", "success")
        except ValueError:
            flash("Invalid format provided.", "danger")
            
    return render_template('settings.html', config=config)

@app.route('/dashboard')
@login_required
def dashboard():
    students = database.get_all_students()
    today_stats = database.get_attendance_stats(datetime.now().date())
    return render_template('dashboard.html', students=students, stats=today_stats)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        student_id = data.get('student_id')
        
        student = database.get_student(student_id)
        if student:
            return jsonify({"success": False, "message": "Student ID already exists in the database."})
            
        return jsonify({"success": True, "message": "Details clear. Proceed to Face Capture."})
        
    return render_template('register.html', is_admin=('admin_logged_in' in session))

@app.route('/api/finalize_registration', methods=['POST'])
def finalize_registration():
    data = request.json
    student_id = data.get('student_id')
    name = data.get('name')
    email = data.get('email')
    
    success, msg = database.register_student(student_id, name, email)
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
            matched_student = database.get_student(matched_id)
            matched_name = matched_student['name'] if matched_student else "Unknown Name"
            
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
def train():
    """Triggers model retraining from dataset folder"""
    success = trainer.train_model()
    recognize_engine.reload_model()
    message = "Model trained successfully." if success else "Failed to train model."
    return jsonify({"success": success, "message": message})

@app.route('/live_feed')
def live_feed_page():
    config = load_config()
    return render_template('live_feed.html', config=config)

@app.route('/api/recognize', methods=['POST'])
def recognize():
    """
    Receives base64 image from web-cam, decode it, find heads, 
    mark attendance, check geo-location and time.
    """
    data = request.json
    image_b64 = data.get('image')
    lat = data.get('lat')
    lon = data.get('lon')
    
    if not image_b64:
        return jsonify({"success": False, "message": "No image provided."})
        
    config = load_config()
    current_time = datetime.now()
        
    # Geo location validation
    location_valid = True
    if lat is not None and lon is not None:
        user_coords = (float(lat), float(lon))
        distance = geodesic(tuple(config['campus_coords']), user_coords).km
        if distance > config['allowable_radius_km']:
            location_valid = False
    
    # Decode base64 to numpy array for OpenCV
    try:
        header, encoded = image_b64.split(",", 1)
        img_data = base64.b64decode(encoded)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
             return jsonify({"success": False, "message": "Failed to decode image. Frame is empty."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Invalid image data: {str(e)}"})
    
    results = recognize_engine.recognize_faces_in_frame(frame, enforce_anti_spoofing=True)
    
    logs = []
    
    for face in results:
        student_id = face['name']
        if student_id != "Unknown" and not face['spoof']:
            # Log attendance using dynamic class start time
            class_start = datetime.strptime(config['class_start_time'], "%H:%M:%S")
            success, msg_data = database.log_attendance(student_id, current_time, class_start, location_valid)
            
            # msg_data now potentially comes back as a dict with status and message
            msg_text = msg_data['message'] if isinstance(msg_data, dict) else msg_data
            
            logs.append({"student_id": student_id, "success": success, "message": msg_text, "location_valid": location_valid})
        elif face['spoof']:
            logs.append({"student_id": student_id, "success": False, "message": "Spoof verification failed. Try again.", "location_valid": location_valid})
        else:
            logs.append({"name": "Unknown", "success": False, "message": "Face not recognized."})
            
    return jsonify({"success": True, "logs": logs, "count": len(results)})

@app.route('/analytics')
@login_required
def analytics():
    today = datetime.now().date()
    stats = database.get_attendance_stats(today)
    return render_template('analytics.html', stats=stats)

@app.route('/student_portal', methods=['GET', 'POST'])
def student_portal():
    student_id = request.form.get('student_id', '') if request.method == 'POST' else request.args.get('student_id', '')
    history = []
    student_name = ""
    
    if student_id:
        student = database.get_student(student_id)
        if student:
            student_name = student['name']
            history = database.get_student_attendance_history(student_id)
            
    return render_template('student_portal.html', history=history, student_id=student_id, student_name=student_name)

@app.route('/api/export_report')
@login_required
def export_report():
    """Generates and returns export path for attendance CSV"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    filepath = auto_report.export_today_csv(today_str)
    if filepath:
        return jsonify({"success": True, "file": filepath})
    return jsonify({"success": False, "message": "No data or export failed."})

@app.route('/api/export_pdf/<report_type>')
@login_required
def export_pdf(report_type):
    """Generates and returns export path for attendance PDF (daily/weekly/monthly)"""
    if report_type not in ['daily', 'weekly', 'monthly']:
        return jsonify({"success": False, "message": "Invalid report type."}), 400
        
    filepath = generate_pdf_report(report_type)
    if filepath:
        return send_file(filepath, as_attachment=True)
    return jsonify({"success": False, "message": f"No data found for {report_type} report, or export failed."})

if __name__ == '__main__':
    database.initialize_database()
    app.run(debug=True, port=5000)
