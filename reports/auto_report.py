import pandas as pd
import os
import database
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

EXPORT_DIR = "reports/exports"

def export_today_csv(date_str=None):
    """
    Queries the database for attendance on a specific date,
    converts it to a pandas DataFrame, and exports it to CSV.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)
        
    conn = database.get_connection()
    if not conn:
        print("[Error] DB connection failed for reporting.")
        return None
        
    try:
        # Fetch detailed log data
        query = '''
            SELECT s.student_id_code, u.name, a.status, l.entry_time, l.exit_time,
                   (a.latitude IS NOT NULL) as location_valid
            FROM attendance a
            JOIN students s ON a.student_id_code = s.student_id_code
            JOIN users u ON s.user_id = u.id
            LEFT JOIN attendance_logs l ON a.student_id_code = l.student_id_code AND DATE(a.timestamp) = l.date
            WHERE DATE(a.timestamp) = %s
        '''
        
        df = pd.read_sql(query, conn, params=(date_str,))
        
        if df.empty:
            print(f"No records found for {date_str}")
            return None
            
        def calc_time(row):
            if pd.notnull(row['entry_time']) and pd.notnull(row['exit_time']):
                diff = row['exit_time'] - row['entry_time']
                secs = diff.total_seconds()
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                return f"{h}h {m}m"
            return ""
            
        df['Time Spent'] = df.apply(calc_time, axis=1)
            
        filename = f"Attendance_Report_{date_str}.csv"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # We can also use pandas to export to excel directly.
        # df.to_excel(filepath.replace('.csv', '.xlsx'), index=False)
        df.to_csv(filepath, index=False)
        
        print(f"Successfully generated report at {filepath}")
        return filepath
        
    except Exception as e:
        print(f"Error generating report: {e}")
        return None
    finally:
        conn.close()

def generate_pdf_report(report_type, course_id=None):
    """
    Generates a PDF report for daily, weekly, or monthly attendance.
    Supports optional course-specific filtering.
    """
    conn = database.get_connection()
    if not conn:
        print("[Error] DB connection failed for PDF reporting.")
        return None
        
    today = datetime.now().date()
    if report_type == 'daily':
        start_date = today
    elif report_type == 'weekly':
        start_date = today - timedelta(days=7)
    elif report_type == 'monthly':
        start_date = today - timedelta(days=30)
    else:
        conn.close()
        return None
        
    try:
        # Get course name if applicable
        course_name = ""
        if course_id:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT course_name FROM courses WHERE id = %s", (course_id,))
            row = cursor.fetchone()
            course_name = row['course_name'] if row else f"Course ID: {course_id}"
            cursor.close()

        query = '''
            SELECT DATE(a.timestamp) as Date, s.student_id_code as `Student ID`, u.name as Name,
                   a.status as Status, l.entry_time as Entry, l.exit_time as `Exit`
            FROM attendance a
            JOIN students s ON a.student_id_code = s.student_id_code
            JOIN users u ON s.user_id = u.id
            LEFT JOIN attendance_logs l ON a.student_id_code = l.student_id_code AND DATE(a.timestamp) = l.date
            WHERE DATE(a.timestamp) >= %s AND DATE(a.timestamp) <= %s
        '''
        params = [start_date, today]
        if course_id:
            query += " AND a.course_id = %s"
            params.append(course_id)
            
        query += " ORDER BY a.timestamp DESC, u.name ASC"
        
        df = pd.read_sql(query, conn, params=tuple(params))
        
        if df.empty:
            print(f"No records found for {report_type} report.")
            return None
            
        if not os.path.exists(EXPORT_DIR):
            os.makedirs(EXPORT_DIR)
            
        # Unique filename to avoid browser caching
        if course_name:
            clean_name = "".join(x for x in course_name if x.isalnum() or x in " _-").strip()
            filename = f"Attendance_{clean_name}_{report_type.capitalize()}_{today}.pdf"
        else:
            filename = f"Attendance_{report_type.capitalize()}_{today}.pdf"
            
        filepath = os.path.join(EXPORT_DIR, filename)
        
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        
        # Heading Styles with Equal Spacing (Leading)
        heading_leading = 22
        
        title_style = ParagraphStyle(
            name='ReportTitle',
            alignment=TA_CENTER,
            fontSize=18,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Bold'
        )
        
        course_style = ParagraphStyle(
            name='CenterCourse',
            alignment=TA_CENTER,
            fontSize=18,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Bold'
        )
        
        date_style = ParagraphStyle(
            name='CenterDate',
            alignment=TA_CENTER,
            fontSize=13,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Oblique', # Italic in ReportLab
            spaceAfter=25
        )
        
        # 1. Main Title
        elements.append(Paragraph("Attendance Report", title_style))
        
        # 2. Course Name
        display_course = course_name if course_name else "Detailed Summary"
        elements.append(Paragraph(f"{display_course}", course_style))
            
        # 3. Date Range (Italic)
        date_subtitle = f"({start_date} to {today})"
        elements.append(Paragraph(date_subtitle, date_style))
        
        # Format DataFrame
        def calc_time(row):
            if pd.notnull(row['Entry']) and pd.notnull(row['Exit']):
                diff = row['Exit'] - row['Entry']
                secs = diff.total_seconds()
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                return f"{h}h {m}m"
            return ""
            
        df['Time Spent'] = df.apply(calc_time, axis=1)
        
        df = df.fillna('')
        if 'Entry' in df.columns:
            df['Entry'] = df['Entry'].astype(str).str.replace('0 days ', '')
        if 'Exit' in df.columns:
            df['Exit'] = df['Exit'].astype(str).str.replace('0 days ', '')
        df['Date'] = df['Date'].astype(str)
        
        data = [df.columns.tolist()] + df.values.tolist()
        
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        print(f"Successfully generated PDF report at {filepath}")
        return os.path.abspath(filepath)
        
    except Exception as e:
        import traceback
        print(f"Error generating PDF report: {e}\n{traceback.format_exc()}")
        return None
def generate_system_report(report_type):
    """
    Generates administrative system reports (Users, Student Enrollments, or Teacher Assignments) in PDF format.
    """
    conn = database.get_connection()
    if not conn:
        print("[Error] DB connection failed for system report.")
        return None
        
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        if report_type == 'users':
            title = "Overall System Users"
            query = "SELECT id as 'ID', name as 'Name', email as 'Email', role as 'Role', created_at as 'Created' FROM users ORDER BY role ASC, name ASC"
            filename_prefix = "User_Directory"
        elif report_type == 'enrollments':
            title = "Student Enrollment Report"
            query = """
                SELECT s.student_id_code as 'Student ID', u.name as 'Name', c.class_name as 'Class',
                       GROUP_CONCAT(co.course_name SEPARATOR ', ') as 'Courses'
                FROM students s
                JOIN users u ON s.user_id = u.id
                LEFT JOIN classes c ON s.class_id = c.id
                LEFT JOIN student_courses sc ON s.id = sc.student_id
                LEFT JOIN courses co ON sc.course_id = co.id
                GROUP BY s.id
                ORDER BY c.class_name, u.name
            """
            filename_prefix = "Student_Enrollments"
        elif report_type == 'assignments':
            title = "Teacher Assignment Report"
            query = """
                SELECT u.name as 'Teacher', u.email as 'Email', c.class_name as 'Class', co.course_name as 'Course'
                FROM teacher_assignments ta
                JOIN users u ON ta.teacher_id = u.id
                JOIN classes c ON ta.class_id = c.id
                JOIN courses co ON ta.course_id = co.id
                ORDER BY u.name, c.class_name
            """
            filename_prefix = "Teacher_Assignments"
        else:
            print(f"[Error] Invalid system report type: {report_type}")
            return None

        df = pd.read_sql(query, conn)
        
        if df.empty:
            print(f"No records found for system report: {report_type}")
            return None
            
        if not os.path.exists(EXPORT_DIR):
            os.makedirs(EXPORT_DIR)
            
        filename = f"{filename_prefix}_{today}.pdf"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Heading Styles with Equal Spacing (Leading)
        heading_leading = 22
        
        # 1. Main Title (Bold Black)
        title_style = ParagraphStyle(
            name='ReportTitle',
            alignment=TA_CENTER,
            fontSize=18,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Bold'
        )
        
        # 2. Administrative Indicator (Bold Black)
        admin_style = ParagraphStyle(
            name='AdminTitle',
            alignment=TA_CENTER,
            fontSize=14,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Bold'
        )
            
        # 3. Date Generated (Italic)
        date_style = ParagraphStyle(
            name='DateSubtitle',
            alignment=TA_CENTER,
            fontSize=12,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Oblique', # Italic
            spaceAfter=25
        )
        
        elements.append(Paragraph(title, title_style))
        elements.append(Paragraph("Administrative System Report", admin_style))
        elements.append(Paragraph(f"Generated on {today}", date_style))
        
        # Format DataFrame
        df = df.fillna('N/A')
        
        data = [df.columns.tolist()] + df.values.tolist()
        
        # Table Styling
        table = Table(data, repeatRows=1)
        # Adjust column widths based on the number of columns
        num_cols = len(df.columns)
        col_width = 540 / num_cols
        table._argW = [col_width] * num_cols
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        print(f"Successfully generated System PDF report at {filepath}")
        return os.path.abspath(filepath)
        
    except Exception as e:
        import traceback
        print(f"Error generating system report: {e}\n{traceback.format_exc()}")
        return None
    finally:
        conn.close()

if __name__ == "__main__":
    export_today_csv()

