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
            SELECT s.student_id_code as `Student ID`, u.name as Name, 
                   c.class_name as Class, co.course_name as Course,
                   a.status as Status, l.entry_time as Entry, l.exit_time as `Exit`,
                   (a.latitude IS NOT NULL) as `Location Valid`
            FROM attendance a
            JOIN students s ON a.student_id_code = s.student_id_code
            JOIN users u ON s.user_id = u.id
            LEFT JOIN classes c ON s.class_id = c.id
            LEFT JOIN courses co ON a.course_id = co.id
            LEFT JOIN attendance_logs l ON a.student_id_code = l.student_id_code 
                                       AND DATE(a.timestamp) = l.date 
                                       AND a.course_id = l.course_id
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

def generate_pdf_report(report_type=None, course_id=None, class_id=None, start_date=None, end_date=None):
    """
    Generates a PDF report for attendance marks.
    Supports optional course-specific filtering and optional date range.
    """
    conn = database.get_connection()
    if not conn:
        print("[Error] DB connection failed for PDF reporting.")
        return None
        
    today = datetime.now().date()
    if start_date and end_date:
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid start_date or end_date format. Expected YYYY-MM-DD.")
            conn.close()
            return None
        if start_date > end_date:
            start_date, end_date = end_date, start_date
    else:
        if report_type == 'daily':
            start_date = today
            end_date = today
        elif report_type == 'weekly':
            start_date = today - timedelta(days=7)
            end_date = today
        elif report_type == 'monthly':
            start_date = today - timedelta(days=30)
            end_date = today
        else:
            conn.close()
            return None
        
    try:
        # Get course and class names if applicable
        course_name = ""
        class_name = ""
        if course_id:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT course_name FROM courses WHERE id = %s", (course_id,))
            row = cursor.fetchone()
            course_name = row['course_name'] if row else f"Course ID: {course_id}"
            cursor.close()
            
        if class_id:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT class_name FROM classes WHERE id = %s", (class_id,))
            row = cursor.fetchone()
            class_name = row['class_name'] if row else f"Class ID: {class_id}"
            cursor.close()

        query = '''
            SELECT 
                s.student_id_code AS `Student ID`,
                u.name AS Name,
                co.course_name AS Course,
                c.class_name AS Class,
                COUNT(DISTINCT DATE(a.timestamp)) AS total_sessions,
                SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) AS attended,
                ROUND(
                    CASE 
                        WHEN COUNT(DISTINCT DATE(a.timestamp)) = 0 THEN 0
                        ELSE SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(DISTINCT DATE(a.timestamp)) * 100
                    END, 1
                ) AS percentage
            FROM attendance a
            JOIN students s ON a.student_id_code = s.student_id_code
            JOIN users u ON s.user_id = u.id
            LEFT JOIN classes c ON s.class_id = c.id
            LEFT JOIN courses co ON a.course_id = co.id
            WHERE DATE(a.timestamp) >= %s AND DATE(a.timestamp) <= %s
        '''
        params = [start_date, end_date]
        if course_id:
            query += " AND a.course_id = %s"
            params.append(course_id)
        if class_id:
            query += " AND s.class_id = %s"
            params.append(class_id)
        query += " GROUP BY s.student_id_code, u.name, co.course_name, c.class_name"
        query += " ORDER BY u.name ASC"
        
        df = pd.read_sql(query, conn, params=tuple(params))
        
        if df.empty:
            print(f"No records found for {report_type} report.")
            return None
            
        if not os.path.exists(EXPORT_DIR):
            os.makedirs(EXPORT_DIR)
            
        # Unique filename to avoid browser caching
        if start_date == end_date:
            date_label = start_date.strftime('%Y-%m-%d')
        else:
            date_label = f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}"
        filename_parts = [f"Attendance_{date_label}"]
        if course_name:
            clean_name = "".join(x for x in course_name if x.isalnum() or x in " _-").strip()
            filename_parts.insert(1, clean_name)
        filename = "_".join(filename_parts) + ".pdf"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        from reportlab.lib.pagesizes import landscape
        doc = SimpleDocTemplate(filepath, pagesize=landscape(letter))
        elements = []
        
        styles = getSampleStyleSheet()
        
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
            fontSize=14,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Bold'
        )
        date_style = ParagraphStyle(
            name='CenterDate',
            alignment=TA_CENTER,
            fontSize=12,
            leading=heading_leading,
            textColor=colors.black,
            fontName='Helvetica-Oblique',
            spaceAfter=20
        )
        
        elements.append(Paragraph("Attendance Summary Report", title_style))
        header_text = ""
        if class_name and course_name:
            header_text = f"Class: {class_name} | Course: {course_name}"
        elif course_name:
            header_text = f"Course: {course_name}"
        elif class_name:
            header_text = f"Class: {class_name}"
        else:
            header_text = "Attendance Summary"
        elements.append(Paragraph(header_text, course_style))
        elements.append(Paragraph(f"({start_date} to {end_date})", date_style))
        
        def attendance_mark(percentage):
            if percentage >= 90:
                return 10
            if percentage >= 80:
                return 8
            if percentage >= 70:
                return 6
            if percentage >= 60:
                return 4
            return 0
        
        df['Attendance %'] = df['percentage']
        df['Attendance Mark'] = df['percentage'].apply(attendance_mark)
        df = df.rename(columns={
            'total_sessions': 'Total Sessions',
            'attended': 'Attended'
        })
        df = df[['Student ID', 'Name', 'Course', 'Class', 'Total Sessions', 'Attended', 'Attendance %', 'Attendance Mark']]
        df = df.fillna('')
        
        data = [df.columns.tolist()] + df.values.tolist()
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
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

