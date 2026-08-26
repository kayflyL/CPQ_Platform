import os
os.environ.setdefault("PYTHONUTF8","1")
import sys
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
from app.models.base import engine
from sqlalchemy import text

with engine.begin() as c:
    # 1) requirement fields now live in opportunity_requirements.slots
    c.execute(text("""
        UPDATE rules.business_fields SET source_column='slots'
        WHERE key IN ('platform_type','chassis_form','purchase_qty','warranty_years')
    """))
    # 2) delete dead fields + orphan audit/stats/references
    dead = ('win_reason','lost_reason','quote_scenario')
    c.execute(text("DELETE FROM rules.business_fields WHERE key IN :k"), {"k": dead})
    for t in ("field_usage_stats","field_audit_logs","field_references"):
        c.execute(text(f"DELETE FROM rules.{t} WHERE field_key IN :k"), {"k": dead})

with engine.connect() as c:
    rows = c.execute(text("""
        SELECT key, source, source_column, enabled FROM rules.business_fields
        WHERE category='opportunity' ORDER BY id
    """)).mappings().all()
    print("=== opportunity business_fields after fix ===")
    for r in rows:
        print(f"{r['key']:20} | {r['source']}.{r['source_column']} | en={r['enabled']}")
