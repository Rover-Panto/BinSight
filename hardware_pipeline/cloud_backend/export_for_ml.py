import sqlite3
import csv

# Connect to your SQLite database
conn = sqlite3.connect('binsight.db')
cursor = conn.cursor()

try:
    # Query all records from the 'readings' table
    cursor.execute("SELECT * FROM readings")
    rows = cursor.fetchall()
    
    # Get the column names
    column_names = [description[0] for description in cursor.description]
    
    # Write to a CSV file
    with open('bin_telemetry_for_ml.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(column_names) # Write header
        writer.writerows(rows)        # Write data rows
        
    print("Success! Created 'bin_telemetry_for_ml.csv'")
except Exception as e:
    print(f"Error exporting data: {e}")
finally:
    conn.close()