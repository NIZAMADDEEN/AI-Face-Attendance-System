import os
import yagmail
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration (Use environment variables for robust security)
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "admin@example.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

def send_late_alert(student_email, student_name, entry_time):
    """
    Sends an email to a student when their attendance is marked as Late.
    """
    # Configuration (Use environment variables for robust security)
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("[Email Configuration Missing] Late notification not sent.")
        return False
        
    try:
        yag = yagmail.SMTP(EMAIL_ADDRESS, EMAIL_PASSWORD)
        subject = "Attendance Alert: Late Arrival"
        
        body = f"""
        Hello {student_name},
        
        This is an automated notification from the AI Attendance System.
        Your attendance for today was recorded at {entry_time}, which is past the defined start time.
        Your status for today has been marked as Late.
        
        Please visit the student portal for your full attendance history.
        
        Regards,
        Admin Team
        """
        
        yag.send(
            to=student_email,
            subject=subject,
            contents=body
        )
        print(f"Sent late alert to {student_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {student_email}: {e}")
        return False

