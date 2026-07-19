"""重置服务器类型目录：去重 server_types（每个名字只留 id 最小的一条），
把 base_configs 的 server_type_id 修正到保留 id，清空机型（由 seed 重建）。

用法：python scripts/reset_catalog.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from app.core.config import get_settings

s = get_settings()
conn = psycopg2.connect(host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
                        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8")
cur = conn.cursor()

# 1. 每个类型名保留 id 最小的一条
cur.execute("SELECT name, MIN(id) FROM l6.server_types GROUP BY name")
keep = {r[0]: r[1] for r in cur.fetchall()}
print(f"现有类型去重：{len(keep)} 种")

# 2. 清空机型（稍后 seed 重建）
cur.execute("DELETE FROM l6.server_models")

# 3. 把 base_configs.server_type_id 统一指向「该名字的保留 id」
for name, kid in keep.items():
    cur.execute("""UPDATE l6.base_configs SET server_type_id = %s
                   WHERE server_type_id IN (SELECT id FROM l6.server_types WHERE name = %s)""",
                (kid, name))

# 4. 删除非保留的重复类型行
if keep:
    cur.execute("DELETE FROM l6.server_types WHERE id NOT IN %s", (tuple(keep.values()),))

# 5. 兜底：确保三个标准类型齐全
STANDARD = [
    ('通用计算服务器', '企业应用、虚拟化、常规业务', 1),
    ('AI / 加速计算服务器', '模型训练与推理，多 GPU', 2),
    ('存储服务器', '大容量、高盘位密度', 3),
]
for name, desc, so in STANDARD:
    cur.execute("SELECT 1 FROM l6.server_types WHERE name=%s", (name,))
    if not cur.fetchone():
        cur.execute("INSERT INTO l6.server_types(name,description,sort_order) VALUES(%s,%s,%s)", (name, desc, so))

conn.commit()
cur.execute("SELECT id, name FROM l6.server_types ORDER BY sort_order, id")
print("✓ 类型清单：")
for r in cur.fetchall():
    print(f"  {r[0]} · {r[1]}")
cur.close()
conn.close()
print("\n下一步：python scripts/seed_demo_data.py 重建机型")
