"""建 bom_templates 表 + base_configs.bom_template_id 列 + seed 3 个机型族模板。

bom_templates：左栏 L6 配置单的"行骨架"（catalogue/desc/qty 摘要），按机型族区分。
  - 2U12标准：IO1-4 + FAN 行（无 GPU）
  - 4U8-GPU直连：rear_summary(Direct) + gpu_power_cord（无 IO/FAN）
  - 4U8-Switch：rear_summary(Switch) + raid_slot + gpu_power_cord

幂等：可重复执行。用法：python scripts/create_bom_templates.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor()

# 1. 建表
cur.execute("""
    CREATE TABLE IF NOT EXISTS l6.bom_templates (
        id         SERIAL PRIMARY KEY,
        name       VARCHAR(100) NOT NULL UNIQUE,
        rows       JSONB NOT NULL DEFAULT '[]'::jsonb,
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")
print("✓ l6.bom_templates")

# 2. base_configs 加 bom_template_id 列（nullable FK 风格，不加 PG FK 约束以免数据迁移麻烦）
cur.execute("""
    ALTER TABLE l6.base_configs
    ADD COLUMN IF NOT EXISTS bom_template_id INTEGER
""")
print("✓ l6.base_configs.bom_template_id")

# 3. seed 3 模板（rows = 有序行 + 每行 rule，rule 跟模板存 JSONB、前端求值）
# ---- 规则 source 快捷构造 ----
def _fixed_v(s): return {"kind": "fixed", "value": s}
def _fixed_n(n): return {"kind": "fixed", "value": n}
def _pf(cat, field): return {"kind": "part_field", "category": cat, "field": field}
def _tpl(s): return {"kind": "template", "template": s}
def _sc(scope): return {"kind": "struct_count", "scope": scope}
def _cv(k): return {"kind": "config_value", "key": k}
def _pq(cat): return {"kind": "part_quantity", "category": cat}
def _cc(k): return {"kind": "config_calc", "key": k}
_MANUAL = {"kind": "manual"}

def _row(type_, label, desc, qty, desc_fb=None, qty_fb=None, slot=None, mode=None):
    r = {"type": type_, "label": label, "rule": {"desc": desc, "qty": qty}}
    if desc_fb: r["rule"]["desc_fallback"] = desc_fb
    if qty_fb: r["rule"]["qty_fallback"] = qty_fb
    if slot: r["slot"] = slot
    if mode: r["mode"] = mode
    return r

# 背板行升级:模板字符串优先(bays 推 12*3.5 SATA/SAS),无 bays 回落背板 sub_type
TPL_BP = _tpl("${bays}*3.5 SATA/SAS")
FB_BP = _pf("背板", "sub_type")

TEMPLATES = [
    ("2U12标准", 1, [
        _row("front_backplane", "Front backplane", TPL_BP, _fixed_n(1), desc_fb=FB_BP),
        _row("io_slot", "IO1", _sc("io_slot"), _fixed_n(1), slot="IO1"),
        _row("io_slot", "IO2", _sc("io_slot"), _fixed_n(1), slot="IO2"),
        _row("io_slot", "IO3", _sc("io_slot"), _fixed_n(1), slot="IO3"),
        _row("io_slot", "IO4", _sc("io_slot"), _fixed_n(1), slot="IO4"),
        _row("heatsink", "Heatsink", _pf("heatsink", "name"), _pq("heatsink"), qty_fb=_fixed_n(2)),
        _row("fan", "FAN", _pf("fan", "name"), _pq("fan")),
        _row("psu_requirement", "Power Supply Requirement",
             _tpl("${psu_wattage}W"), _cc("psu_qty"), desc_fb=_cv("psu_name")),
        _row("power_cord", "Power cord", _fixed_v("国标电源线"), _cc("psu_qty")),
        _row("rail_kit", "Rail kit", _pf("rail", "name"), _pq("rail"), qty_fb=_fixed_n(1)),
        _row("cable", "Cable", _sc("front_cables"), _MANUAL),
    ]),
    ("4U8-GPU直连", 2, [
        _row("front_backplane", "Front backplane", TPL_BP, _fixed_n(1), desc_fb=FB_BP),
        _row("rear_summary", "Direct connection", _sc("rear_all"), _fixed_n(1), mode="direct"),
        _row("heatsink", "Heatsink", _pf("heatsink", "name"), _pq("heatsink"), qty_fb=_fixed_n(2)),
        _row("psu_requirement", "Power Supply Requirement",
             _tpl("${psu_wattage}W"), _cc("psu_qty"), desc_fb=_cv("psu_name")),
        _row("gpu_power_cord", "GPU Power cord", _pf("GPU电源线", "name"), _cc("gpu_cable_qty")),
        _row("power_cord", "Power cord", _fixed_v("国标电源线"), _cc("psu_qty")),
        _row("rail_kit", "Rail kit", _pf("rail", "name"), _pq("rail"), qty_fb=_fixed_n(1)),
        _row("cable", "Cable", _sc("front_cables"), _MANUAL),
    ]),
    ("4U8-Switch", 3, [
        _row("front_backplane", "Backplane", TPL_BP, _fixed_n(1), desc_fb=FB_BP),
        _row("rear_summary", "Switch", _sc("rear_all"), _fixed_n(1), mode="switch"),
        _row("raid_slot", "Raid slot", _MANUAL, _MANUAL),
        _row("heatsink", "Heatsink", _pf("heatsink", "name"), _pq("heatsink"), qty_fb=_fixed_n(2)),
        _row("psu_requirement", "Power Supply Requirement",
             _tpl("${psu_wattage}W"), _cc("psu_qty"), desc_fb=_cv("psu_name")),
        _row("gpu_power_cord", "GPU Power cord", _pf("GPU电源线", "name"), _cc("gpu_cable_qty")),
        _row("power_cord", "Power cord", _fixed_v("国标电源线"), _cc("psu_qty")),
        _row("rail_kit", "Rail kit", _pf("rail", "name"), _pq("rail"), qty_fb=_fixed_n(1)),
        _row("cable", "Cable", _sc("front_cables"), _MANUAL),
    ]),
]

for name, order, rows in TEMPLATES:
    cur.execute("""
        INSERT INTO l6.bom_templates (name, rows, sort_order)
        VALUES (%s, %s::jsonb, %s)
        ON CONFLICT (name) DO UPDATE SET rows = EXCLUDED.rows, sort_order = EXCLUDED.sort_order
    """, (name, json.dumps(rows, ensure_ascii=False), order))
    print(f"✓ seed template: {name} ({len(rows)} rows)")

# 4. 回填现有 base_configs 的 bom_template_id（现有都是 2U12 Orion → 2U12标准）
cur.execute("SELECT id FROM l6.bom_templates WHERE name='2U12标准'")
t2u = cur.fetchone()
if t2u:
    cur.execute("""
        UPDATE l6.base_configs SET bom_template_id = %s WHERE bom_template_id IS NULL
    """, (t2u[0],))
    print(f"✓ backfilled base_configs.bom_template_id → 2U12标准(id={t2u[0]}) for {cur.rowcount} rows")

conn.commit()
cur.close()
conn.close()
print("\n完成。bom_templates 就绪。")
