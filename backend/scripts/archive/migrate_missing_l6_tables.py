"""Migrate missing L6 tables data from SQLite to PostgreSQL"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from app.core.config import get_settings

# SQLite source
SQLITE_PATH = 'D:/Quotation_Automation/Reference/l6_data.db'

# PostgreSQL connection
settings = get_settings()
pg_conn = psycopg2.connect(
    host=settings.POSTGRES_HOST,
    port=settings.POSTGRES_PORT,
    dbname=settings.POSTGRES_DB,
    user=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    client_encoding='UTF8'
)

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row

# Tables to migrate (all in l6 schema)
tables = [
    'l6_base_configs',
    'l6_base_config_parts',
    'l6_front_panel_items',
    'l6_rear_panel_items',
    'l6_psu_options',
    'l6_bom_templates',
    'l6_bom_parts'
]

pg_cursor = pg_conn.cursor()

for table in tables:
    print(f"\n=== Migrating {table} ===")
    
    # Clear target table
    pg_cursor.execute(f"DELETE FROM l6.{table}")
    pg_conn.commit()
    
    # Read from SQLite
    sqlite_cursor = sqlite_conn.cursor()
    try:
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            print(f"  No data in SQLite")
            continue
        
        # Get column names
        columns = [desc[0] for desc in sqlite_cursor.description]
        print(f"  Columns: {columns}")
        print(f"  Rows: {len(rows)}")
        
        # Insert to PostgreSQL
        col_list = ", ".join(columns)
        insert_sql = f"INSERT INTO l6.{table} ({col_list}) VALUES %s"
        
        # Convert rows to list of tuples
        data = [tuple(row) for row in rows]
        
        execute_values(pg_cursor, insert_sql, data, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(data)} rows")
        
    except sqlite3.OperationalError as e:
        print(f"  ⚠ Table not found in SQLite: {e}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        pg_conn.rollback()

sqlite_conn.close()
pg_cursor.close()
pg_conn.close()

print("\n" + "=" * 60)
print("Migration complete!")
