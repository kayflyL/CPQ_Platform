"""给 l6.parts_master 加 section（一级部段）列 + 按 category→section 映射回填。

section 取代 sub_type 的「一级分类」职责，对应报价表 4 个 STEP：
  基准件 / 前面板件 / 后面板件 / 电源件

幂等：可重复执行。用法：python scripts/add_section_to_parts.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings

# category → section 默认映射（与前端 partSections.ts 同源）
CATEGORY_TO_SECTION = {
    # 基准件 —— STEP1 确定基准配置包含的料
    "机箱": "基准件", "托盘": "基准件", "主板": "基准件", "散热器": "基准件",
    "底盘件": "基准件", "后IO板": "基准件", "背板": "基准件", "滑轨": "基准件",
    "导风罩": "基准件", "标签": "基准件", "电源线": "基准件", "IO线缆": "基准件",
    # 前面板件 —— STEP2 配置前面板
    "前面板线缆": "前面板件",
    # 后面板件 —— STEP3 配置后面板
    "后面板Riser": "后面板件", "OCP": "后面板件", "GPU电源线": "后面板件",
    # 电源件 —— STEP4 选择PSU
    "电源": "电源件",
}

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor()

# 1. 加列（live 表在 l6 schema）
cur.execute("ALTER TABLE l6.parts_master ADD COLUMN IF NOT EXISTS section VARCHAR(20)")
print("✓ l6.parts_master.section")

cur.execute(
    "CREATE INDEX IF NOT EXISTS idx_parts_master_section ON l6.parts_master(section)")
print("✓ idx_parts_master_section")

# 2. 按 category 回填 section（仅填 NULL/空，已手改的不覆盖）
for cat, sec in CATEGORY_TO_SECTION.items():
    cur.execute(
        "UPDATE l6.parts_master SET section=%s "
        "WHERE category=%s AND (section IS NULL OR section='')",
        (sec, cat),
    )
    if cur.rowcount:
        print(f"  {sec:<6} ← {cat} ({cur.rowcount})")

conn.commit()

# 3. 核对分布
cur.execute(
    "SELECT COALESCE(NULLIF(section,''),'(空)') AS s, COUNT(*) "
    "FROM l6.parts_master GROUP BY s ORDER BY s")
print("\n分布核对：")
for sec, n in cur.fetchall():
    print(f"  {sec:<8} {n}")

# 4. 漏网之鱼（category 不在映射表 → section 仍空）
cur.execute(
    "SELECT pn, name, category FROM l6.parts_master "
    "WHERE section IS NULL OR section='' ORDER BY category")
missing = cur.fetchall()
if missing:
    print(f"\n⚠ {len(missing)} 条未归类（需在映射表补 category 或 UI 手改 section）：")
    for pn, name, cat in missing:
        print(f"  {cat:<12} {name[:30]:<30} {pn}")
else:
    print("\n✓ 全部料号已归类")

cur.close()
conn.close()
