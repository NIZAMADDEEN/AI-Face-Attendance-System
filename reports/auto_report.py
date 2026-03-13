import pandas as pd
import os
import database
from datetime import datetime

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
            SELECT s.student_id, s.name, a.status, l.entry_time, l.exit_time, a.location_valid
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            LEFT JOIN attendance_logs l ON a.student_id = l.student_id AND a.date = l.date
            WHERE a.date = %s
        '''
        
        df = pd.read_sql(query, conn, params=(date_str,))
        
        if df.empty:
            print(f"No records found for {date_str}")
            return None
            
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

if __name__ == "__main__":
    export_today_csv()
