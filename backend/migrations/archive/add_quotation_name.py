"""Add quotation_name column to quotations table"""
import sqlite3
import sys
import os

DB_PATH = r"D:\Quotation_Automation\Reference\projects.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(quotations)")
    columns = [row[1] for row in cursor.fetchall()]

    if "quotation_name" in columns:
        print("quotation_name column already exists, skipping.")
        return

    cursor.execute("ALTER TABLE quotations ADD COLUMN quotation_name TEXT DEFAULT ''")
    conn.commit()
    print("Added quotation_name column to quotations table.")
    conn.close()

if __name__ == "__main__":
    migrate()
