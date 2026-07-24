"""Create missing L6 tables in PostgreSQL"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings

settings = get_settings()
conn = psycopg2.connect(
    host=settings.POSTGRES_HOST,
    port=settings.POSTGRES_PORT,
    dbname=settings.POSTGRES_DB,
    user=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    client_encoding='UTF8'
)
cursor = conn.cursor()

# Create missing tables in l6 schema
tables = [
    """CREATE TABLE IF NOT EXISTS l6.l6_base_configs (
        config_id SERIAL PRIMARY KEY,
        chassis_series VARCHAR(255),
        description TEXT,
        excludes TEXT,
        base_price DECIMAL(15,2),
        sort_order INTEGER,
        drive_bays VARCHAR(255),
        backplane_type VARCHAR(255),
        chassis VARCHAR(255)
    )""",
    """CREATE TABLE IF NOT EXISTS l6.l6_base_config_parts (
        part_id SERIAL PRIMARY KEY,
        config_id INTEGER,
        pn VARCHAR(255),
        part_name VARCHAR(255),
        description TEXT,
        unit_price DECIMAL(15,2),
        quantity INTEGER,
        note TEXT,
        sort_order INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS l6.l6_front_panel_items (
        item_id SERIAL PRIMARY KEY,
        cable_type VARCHAR(255),
        pn VARCHAR(255),
        part_name VARCHAR(255),
        description TEXT,
        unit_price DECIMAL(15,2),
        group_size INTEGER,
        applicable_config_ids TEXT,
        note TEXT,
        sort_order INTEGER,
        applicable_drive_bays TEXT,
        applicable_backplane TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS l6.l6_rear_panel_items (
        item_id SERIAL PRIMARY KEY,
        io_slot VARCHAR(255),
        option_type VARCHAR(255),
        pn VARCHAR(255),
        part_name VARCHAR(255),
        description TEXT,
        unit_price DECIMAL(15,2),
        quantity INTEGER,
        applicable_config_ids TEXT,
        note TEXT,
        sort_order INTEGER,
        applicable_backplane TEXT,
        applicable_chassis TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS l6.l6_psu_options (
        psu_id SERIAL PRIMARY KEY,
        wattage VARCHAR(255),
        pn VARCHAR(255),
        part_name VARCHAR(255),
        description TEXT,
        unit_price DECIMAL(15,2),
        applicable_chassis TEXT,
        note TEXT,
        sort_order INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS l6.l6_bom_templates (
        template_id SERIAL PRIMARY KEY,
        l6_id INTEGER,
        step INTEGER,
        template_name VARCHAR(255),
        description TEXT,
        base_price DECIMAL(15,2),
        is_default BOOLEAN DEFAULT FALSE,
        sort_order INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS l6.l6_bom_parts (
        part_id SERIAL PRIMARY KEY,
        template_id INTEGER,
        step INTEGER,
        pn VARCHAR(255),
        part_name VARCHAR(255),
        description TEXT,
        unit_price DECIMAL(15,2),
        quantity_default INTEGER,
        note TEXT,
        sort_order INTEGER
    )"""
]

for sql in tables:
    cursor.execute(sql)
    print(f"✓ Created table")

conn.commit()
print("\nAll 7 tables created successfully!")

cursor.close()
conn.close()
