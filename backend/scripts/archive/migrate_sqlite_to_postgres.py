"""
SQLite to PostgreSQL Migration Script
Migrates data from 5 SQLite databases to PostgreSQL with 6 schemas
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from app.core.config import get_settings


# Source SQLite databases
SQLITE_PATHS = {
    "kp": "D:/Quotation_Automation/Reference/kp_data.db",
    "l6": "D:/Quotation_Automation/Reference/l6_data.db",
    "opportunities": "D:/Quotation_Automation/Reference/opportunities.db",
    "rules": "D:/Quotation_Automation/Reference/rules.db",
    "l6_history": "D:/Quotation_Automation/Reference/l6_history.db",
}


def get_sqlite_connection(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_connection():
    settings = get_settings()
    return psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )


def migrate_table(sqlite_conn, pg_conn, sqlite_table, pg_schema, pg_table=None, add_id_column=False):
    """Migrate a single table from SQLite to PostgreSQL"""
    if pg_table is None:
        pg_table = sqlite_table

    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()

    # Get SQLite columns
    sqlite_cursor.execute(f"PRAGMA table_info({sqlite_table})")
    sqlite_columns = [row[1] for row in sqlite_cursor.fetchall()]

    # Get PostgreSQL columns
    pg_cursor.execute(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = '{pg_schema}' AND table_name = '{pg_table}'
        ORDER BY ordinal_position
    """)
    pg_columns = [row[0] for row in pg_cursor.fetchall()]

    # Find common columns
    common_columns = [col for col in sqlite_columns if col in pg_columns]
    
    if add_id_column and "id" not in common_columns:
        if "id" in pg_columns:
            common_columns.insert(0, "id")

    if not common_columns:
        print(f"  No matching columns for {sqlite_table}")
        return 0

    # Read data from SQLite
    if add_id_column and "id" not in sqlite_columns:
        sqlite_cursor.execute(f"SELECT rowid as id, {', '.join(sqlite_columns)} FROM {sqlite_table}")
    else:
        sqlite_cursor.execute(f"SELECT * FROM {sqlite_table}")

    rows = sqlite_cursor.fetchall()

    if not rows:
        print(f"  No data in {sqlite_table}")
        return 0

    # Filter to only common columns
    col_indices = []
    for col in common_columns:
        if col == "id" and add_id_column and "id" not in sqlite_columns:
            col_indices.append(0)  # rowid is first column
        else:
            col_indices.append(sqlite_columns.index(col) + (1 if add_id_column and "id" not in sqlite_columns else 0))

    data = []
    for row in rows:
        data.append(tuple(row[i] for i in col_indices))

    # Get PG column types for conversion
    pg_cursor.execute(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = '{pg_schema}' AND table_name = '{pg_table}'
    """)
    pg_col_types = {row[0]: row[1] for row in pg_cursor.fetchall()}

    # Convert data types (SQLite int -> PG boolean)
    converted_data = []
    for row in data:
        converted_row = []
        for i, col in enumerate(common_columns):
            val = row[i]
            if col in pg_col_types:
                col_type = pg_col_types[col]
                if col_type == 'boolean' and val is not None:
                    # Convert SQLite integer to PostgreSQL boolean
                    val = bool(val)
            converted_row.append(val)
        converted_data.append(tuple(converted_row))

    # Clear target table first (avoid duplicate key errors on re-run)
    pg_cursor.execute(f"DELETE FROM {pg_schema}.{pg_table}")
    pg_conn.commit()

    col_list = ", ".join(common_columns)
    insert_sql = f"INSERT INTO {pg_schema}.{pg_table} ({col_list}) VALUES %s"

    execute_values(pg_cursor, insert_sql, converted_data, page_size=1000)
    pg_conn.commit()

    print(f"  Migrated {len(data)} rows: {sqlite_table} -> {pg_schema}.{pg_table}")
    return len(data)


def migrate_all():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)

    # KP
    print("\n=== KP Schema ===")
    sqlite_conn = get_sqlite_connection(SQLITE_PATHS["kp"])
    pg_conn = get_pg_connection()
    try:
        migrate_table(sqlite_conn, pg_conn, "kp_records", "kp", add_id_column=True)
    finally:
        sqlite_conn.close()
        pg_conn.close()

    # L6
    print("\n=== L6 Schema ===")
    sqlite_conn = get_sqlite_connection(SQLITE_PATHS["l6"])
    pg_conn = get_pg_connection()
    try:
        # Only migrate tables that have models defined
        migrate_table(sqlite_conn, pg_conn, "l6_records", "l6", add_id_column=True)
        # Note: l6_base_configs, l6_base_config_parts, etc. are not in models, skip them
    finally:
        sqlite_conn.close()
        pg_conn.close()

    # Opportunities
    print("\n=== Opportunities Schema ===")
    sqlite_conn = get_sqlite_connection(SQLITE_PATHS["opportunities"])
    pg_conn = get_pg_connection()
    try:
        tables = ["opportunities", "quotations", "opportunity_items", "opportunity_files"]
        for table in tables:
            migrate_table(sqlite_conn, pg_conn, table, "opportunities")
        # Note: export_templates is not in models (univer_templates is different), skip it
    finally:
        sqlite_conn.close()
        pg_conn.close()

    # Rules
    print("\n=== Rules Schema ===")
    sqlite_conn = get_sqlite_connection(SQLITE_PATHS["rules"])
    pg_conn = get_pg_connection()
    try:
        # Use correct table names from models
        tables = [
            "l6_region_config",  # not l6_region_configs
            "business_fields",
            "dynamic_source_fields",
            "field_references",
            "field_audit_logs",
            "field_usage_stats",
            "system_config",
        ]
        for table in tables:
            migrate_table(sqlite_conn, pg_conn, table, "rules")
    finally:
        sqlite_conn.close()
        pg_conn.close()

    # L6 History
    print("\n=== L6 History Schema ===")
    sqlite_conn = get_sqlite_connection(SQLITE_PATHS["l6_history"])
    pg_conn = get_pg_connection()
    try:
        migrate_table(sqlite_conn, pg_conn, "l6_price_history", "l6_history")
    finally:
        sqlite_conn.close()
        pg_conn.close()

    # Verify
    print("\n=== Verification ===")
    pg_conn = get_pg_connection()
    try:
        pg_cursor = pg_conn.cursor()
        schemas = {
            "kp": ["kp_records"],
            "l6": ["l6_records"],
            "opportunities": ["opportunities", "quotations", "opportunity_items", "opportunity_files"],
            "rules": ["l6_region_config", "business_fields", "dynamic_source_fields",
                     "field_references", "field_audit_logs", "field_usage_stats", "system_config"],
            "l6_history": ["l6_price_history"],
        }
        total = 0
        for schema, tables in schemas.items():
            for table in tables:
                pg_cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
                count = pg_cursor.fetchone()[0]
                total += count
                if count > 0:
                    print(f"  {schema}.{table}: {count} rows")
        print(f"\nTotal: {total} rows migrated")
    finally:
        pg_conn.close()

    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)


if __name__ == "__main__":
    migrate_all()
