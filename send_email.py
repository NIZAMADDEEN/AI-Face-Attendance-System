import yagmail
import os

# Configuration (Use environment variables for robust security)
# Make sure "Less secure app access" or an App Password is setup for Gmail
EMAIL_ADDRESS = "nizamscomputers9@gmail.com"
EMAIL_PASSWORD = "Musawa@1234"

def send_late_alert(student_email, student_name, entry_time):
    """
    Sends an email to a student when their attendance is marked as Late.
    """
    if EMAIL_ADDRESS == "nizamscomputers9@gmail.com":
        print(f"[SendGrid/Yagmail Stub] Late email would be sent to: {student_email} for arriving at {entry_time}")
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

