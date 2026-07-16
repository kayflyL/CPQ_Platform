"""Create all tables in PostgreSQL"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.base import engine, Base
from app.models import (
    kp, l6, opportunity, quotation, opportunity_item, opportunity_file,
    rules, business_field, dynamic_source_field, field_reference,
    field_audit_log, field_usage_stats, system_config, univer_template
)

print("Creating tables in PostgreSQL...")
Base.metadata.create_all(bind=engine)
print("✓ All tables created successfully!")

# Verify schemas
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT schema_name 
        FROM information_schema.schemata 
        WHERE schema_name IN ('kp', 'l6', 'opportunities', 'rules', 'l6_history', 'public')
        ORDER BY schema_name
    """))
    schemas = [row[0] for row in result]
    print(f"\n✓ Schemas verified: {', '.join(schemas)}")
    
    # Count tables
    result = conn.execute(text("""
        SELECT table_schema, COUNT(*) as table_count
        FROM information_schema.tables
        WHERE table_schema IN ('kp', 'l6', 'opportunities', 'rules', 'l6_history', 'public')
        GROUP BY table_schema
        ORDER BY table_schema
    """))
    print("\n✓ Tables per schema:")
    for schema, count in result:
        print(f"  - {schema}: {count} tables")
