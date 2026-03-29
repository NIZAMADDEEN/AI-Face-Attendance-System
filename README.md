# 🤖 GeoFace AI Attendance Management System

A complete, production-grade attendance management system powered by Modern AI, featuring high-accuracy facial recognition, geolocation validation, real-time teacher notifications, and professional administrative reporting. Built with Python, Flask, DeepFace (RetinaFace/ArcFace), and MySQL.

## ✨ Core Features

*   **Modern AI Recognition:** Powered by **RetinaFace** for high-accuracy detection and **ArcFace** for state-of-the-art facial recognition via the `DeepFace` pipeline.
*   **Visual Feedback Outlines:** Real-time **Blue (Recognized)** and **Red (Unknown)** rectangles drawn around faces with the **Student's Full Name** displayed for instant verification.
*   **Advanced Anti-Spoofing:** Built-in liveness detection to prevent photo and screen spoofing during attendance logging.
*   **Real-time Notifications:** Teachers are instantly notified on their dashboard when new students register for their assigned classes.
*   **Dynamic Geolocation Fencing:** Enforces physical attendance by cross-checking browser coordinates against configurable campus boundaries.
*   **Unified Attendance Analytics:** Teachers can view a consolidated report showing attendance percentages, automatic grading, and performance recommendations for every student.
*   **Administrative System Reports:** Dedicated Admin reports for **Overall System Users**, **Student Enrollments**, and **Teacher Assignments**.
*   **Entry & Exit Tracking:** Marks both arrival and departure timestamps natively in the SQL database, automatically preventing duplicate logs!
*   **Student Portal:** A private portal for students to register their faces and view their personal attendance history.

## 🛠 Technology Stack

*   **Backend Framework:** Python Flask, Jinja2
*   **Database:** MySQL Server
*   **AI / Vision Engine:** DeepFace (RetinaFace detection + ArcFace recognition), OpenCV (`cv2`)
*   **Frontend UI:** Bootstrap 5, FontAwesome, Chart.js, HTML5 Canvas
*   **Reporting:** `pandas` (Data processing), `reportlab` (Dynamic PDF Generation)

---

## 🚀 Setup & Installation Guide

### 1. Prerequisites
Ensure you have the following installed:
*   Python 3.9+ 
*   MySQL Server (Locally or Remote)
*   Visual Studio C++ Build Tools (Required for AI library dependencies on Windows).

### 2. Setup Virtual Environment
```bash
# Create and activate venv
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example environment file and update it with your actual credentials:
```bash
cp .env.example .env
```
Edit `.env` and provide:
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `EMAIL_ADDRESS`, `EMAIL_PASSWORD` (Gmail App Password)
- `SECRET_KEY`

### 5. System Configuration
Copy the example config file:
```bash
cp config.example.json config.json
```
The system will automatically generate the required MySQL schema upon first run.

### 6. Start the Application
```bash
python app.py
```
> The server will be deployed on **http://127.0.0.1:5000**

---

## 📖 System Walkthrough

### ⚙️ Administrative Overview
1.  **Dashboard**: Monitor school-wide stats and export system reports (**User Directory**, **Enrollments**, **Assignments**) in professional PDF format.
2.  **Settings**: Configure your **Campus GPS Coordinates**, **Allowable Radius**, and **Session Timing** directly from the UI.
3.  **Teacher Assignments**: Link teachers to specific classes and subjects to enable targeted reporting and notifications.

### 👥 Student Registration & Notifications
1.  Access the **Register Student** portal.
2.  Capture 10 high-quality face samples. The system automatically detects duplicates and identifies existing users by name.
3.  **Instant Notifications**: As soon as a student registers, the assigned teachers receive an alert on their dashboard.

### 📸 Attendance Lifecycle
1.  Go to **Live Scanner** (Student Portal).
2.  The AI cross-verifies the student's face, enforces Anti-Spoofing, and validates GPS coordinates.
3.  **Logging**: Marks "Present" on entry. If the student scans again during the session, it logs their strict **Exit** time.

## 📁 Repository Architecture
```text
/AI-Face-Attendance-System/
│
├── app.py                   # Main Flask Controller & Routes
├── database.py              # MySQL Logic & Notification System
├── config.json              # System configuration (shared)
├── .env                     # Private environment variables
│
├── /ai/                     # Computer Vision Module
│   ├── recognize_engine.py  # DeepFace Recognition Pipeline
│   ├── train_model.py       # Model training engine
│   └── anti_spoofing.py     # Liveness detection logic
│
├── /reports/                # Reporting Module
│   ├── auto_report.py       # PDF & CSV Generation Engine
│   └── exports/             # Generated report files (ignored)
│
├── /templates/              # UI Components (Jinja2 Templates)
├── /static/                 # CSS, JS, and Images
├── /dataset/                # Facial embeddings & student images (ignored)
└── /model/                  # Trained AI models (ignored)
```

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
