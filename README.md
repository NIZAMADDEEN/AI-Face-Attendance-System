# 🤖 AI Face Recognition Attendance Management System

A complete, production-ready attendance management system powered by Artificial Intelligence, featuring live facial recognition, geolocation validation, and a dynamic Admin Dashboard. Built with Python, Flask, OpenCV, face_recognition, and MySQL.

## ✨ Core Features

*   **Live Facial Recognition:** Uses deep learning algorithms to match camera feeds instantly against an automated dataset generator.
*   **Anti-Spoofing Protocols:** Checks for blink landmarks using dlib and Eye Aspect Ratio (EAR) mathematics to prevent users from presenting static photos.
*   **Dynamic Geolocation Fencing:** Enforces physical attendance by cross-checking browser coordinates against configurable campus boundaries.
*   **Secure Admin Dashboard:** A locked-down layout for administrators to monitor daily analytics, view registered students, and export CSV reports.
*   **Interactive Settings Portal:** Change system GPS configuration, allowable radus limits, class start times, and admin passwords directly from the web browser! (No code restarts required).
*   **Entry & Exit Tracking:** Gracefully marks both arrival and departure timestamps natively in the SQL database, automatically preventing duplicate logs!
*   **Student Portal:** A public, read-only interface allowing students to enter their ID and check their historical attendance records independently.
*   **Automated Email Warnings:** Asynchronous scripts ready to dispatch SMTP emails for chronic absentees or late arrivals via `yagmail`.

## 🛠 Technology Stack

*   **Backend Framework:** Python Flask, Jinja2
*   **Database:** MySQL Server (`mysql.connector`)
*   **AI / Vision:** OpenCV (`cv2`), `face_recognition`, `dlib`, `mediapipe`
*   **Frontend UI:** Bootstrap 5, FontAwesome, Chart.js, HTML5 Canvas, Navigator Geolocation
*   **Utility & Data:** `geopy` (Distance calculations), `pandas` (CSV Reporting)

---

## 🚀 Setup & Installation Guide

### 1. Prerequisites
Ensure you have the following installed on your machine:
*   Python 3.9+ 
*   MySQL Server (Locally or Remote)
*   Visual Studio C++ Build Tools (Required on Windows to compile `dlib` & `CMake`).

### 2. Install Dependencies
Clone the repository and install the standard python libraries:
```bash
pip install -r requirements.txt
```

### 3. Initialize the Database
The script will automatically generate the required database tables `students`, `attendance`, and `attendance_logs`. 
Ensure your MySQL server is running. If your MySQL credentials are not `root` and `password`, open `database.py` and update the constants:
```python
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "your_password_here"
```

### 4. Start the Application
Boot up the Flask application. It automatically sets up the environment:
```bash
python app.py
```
> The server will be deployed on **http://127.0.0.1:5000**

---

## 📖 Walkthrough & Usage

### ⚙️ System Configuration
1. Navigate to `http://127.0.0.1:5000/dashboard`.
2. You will be redirected to the secure portal. Log in using the default password: `password`.
3. Go to **Settings** and update your **Campus Coordinates**, **Class Start Time**, and change the Admin Password.

### 👥 Registering a Student
1. Access the public **Register Student** tab.
2. Provide the Student ID, Name, and Email Address.
3. Allow the browser to access the webcam, and click **Capture Face** until 10 pictures are processed into the `dataset/` directory.
4. Click **Train AI Model** to convert these photos into mathematical face encodings!
*(Note: Admins have a hidden option to bypass the webcam if a student's webcam data must be manually managed).*

### 📸 Live Scanning
1. Go to **Live Scanner** and hit Start.
2. Step in front of the camera.
3. The AI will cross-verify your face, enforce Anti-Spoofing checks, and validate your HTML5 GPS coordinates!
4. It will return a green **"Attendance logged for [Name] (Present)"**. If you scan again later, it will log your strict **Exit** time!

### 📊 Reviewing Data
*   **Admin Dashboard:** Log in to see Chart.js visual statistics outlining precise Late, Absent, and Present configurations. Click "Export Today's Report" to immediately save a CSV data dump!
*   **Student Portal:** Students can search their ID to pull a real-time table of their personal history.

## 📁 Repository Architecture
```text
/AI_Attendance_System/
│
├── app.py                   # Main Flask REST API & Routers
├── database.py              # MySQL connector functions and initializers
├── config.json              # Dynamic user-settings 
│
├── /ai/                     # Core Artificial Intelligence Module
│   ├── recognize_engine.py  # Image-to-Encoding matching algorithm
│   ├── train_model.py       # Encodes dataset/ directory images to encodings.pickle
│   └── anti_spoofing.py     # dlib blink detection logic
│
├── /reports/                # Logging & Mailing Modules
│   ├── auto_report.py       # Pandas CSV Exporter
│   └── send_email.py        # SMTP email alerts
│
├── /templates/              # Jinja2 / HTML5 Views
│   ├── base.html            # Core UI layout and Navigational logic
│   ├── dashboard.html       # Chart.js and Data tables
│   ├── settings.html        # Interactive Python configuration variables
│   ├── live_feed.html       # WebRTC video capture and HTML5 canvas streaming
│   ├── register.html        # Registration workflows
│   ├── login.html           # Admin Session authenticator
│   └── student_portal.html  # Read-only student historical feeds
│
└── /dataset/                # Captured face arrays segregated by Student IDs
```

## 🤝 Contribution & License
This full-stack tool is fully modularized and documented. Feel free to extend the SQL triggers, implement specialized `face_recognition` threshold tweaks, or connect the system directly to wider organization networking rules!
