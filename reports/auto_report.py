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

def generate_pdf_report(report_type):
    """
    Generates a PDF report for daily, weekly, or monthly attendance.
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
        return None
        
    try:
        query = '''
            SELECT DATE(a.timestamp) as Date, s.student_id_code as `Student ID`, u.name as Name,
                   a.status as Status, l.entry_time as Entry, l.exit_time as `Exit`
            FROM attendance a
            JOIN students s ON a.student_id_code = s.student_id_code
            JOIN users u ON s.user_id = u.id
            LEFT JOIN attendance_logs l ON a.student_id_code = l.student_id_code AND DATE(a.timestamp) = l.date
            WHERE DATE(a.timestamp) >= %s AND DATE(a.timestamp) <= %s
            ORDER BY a.timestamp DESC, u.name ASC
        '''
        
        df = pd.read_sql(query, conn, params=(start_date, today))
        
        if df.empty:
            print(f"No records found for {report_type} report.")
            return None
            
        if not os.path.exists(EXPORT_DIR):
            os.makedirs(EXPORT_DIR)
            
        filename = f"Attendance_{report_type.capitalize()}_{today}.pdf"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        date_style = ParagraphStyle(
            name='CenterDate',
            parent=styles['Normal'],
            alignment=TA_CENTER,
            fontSize=12,
            spaceAfter=20
        )
        
        main_title = f"{report_type.capitalize()} Attendance Report"
        date_subtitle = f"({start_date} to {today})"
        
        elements.append(Paragraph(main_title, styles['Title']))
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
        # Return absolute path
        return os.path.abspath(filepath)
        
    except Exception as e:
        import traceback
        print(f"Error generating PDF report: {e}\n{traceback.format_exc()}")
        return None
    finally:
        conn.close()

if __name__ == "__main__":
    export_today_csv()

