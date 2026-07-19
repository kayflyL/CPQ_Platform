"""种子数据：基于 Orion / Polaris STEP BY STEP 表，建几个机型 + 基准配置 + 底盘件。

跑完后配置面（/servers → 配置）就能选到机型、进入四步配置。
幂等：可重复跑，不会重复建。

用法：python scripts/seed_demo_data.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

s = get_settings()
conn = psycopg2.connect(host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
                        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8")
cur = conn.cursor(cursor_factory=DictCursor)


def ensure_part(pn, name, category, price, specs=None, sub_type=None):
    """确保料号在 parts_master（缺则建）"""
    cur.execute("SELECT 1 FROM parts.parts_master WHERE pn=%s", (pn,))
    if not cur.fetchone():
        cur.execute("""INSERT INTO parts.parts_master(pn,name,category,sub_type,specs,unit_price)
                       VALUES(%s,%s,%s,%s,%s,%s)""",
                    (pn, name, category, sub_type, json.dumps(specs or {}), price))
        print(f"  + 料号 {pn} ({name})")


def ensure_base(name, series, form, bays, tri_pn, dc_pn, common_parts):
    """建基准配置 + 底盘件清单，返回 id。common_parts: [(pn, qty)]"""
    cur.execute("SELECT id FROM l6.base_configs WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        cid = row["id"]
        print(f"  · 基准「{name}」已存在 id={cid}")
    else:
        cur.execute("""INSERT INTO l6.base_configs(name,server_type_id,series,model,form,bays,bp_tri_pn,bp_dc_pn,gpu_arch_default,sort_order)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'none',0) RETURNING id""",
                    (name, _type_id("通用计算服务器"), series, name, form, bays, tri_pn, dc_pn))
        cid = cur.fetchone()["id"]
        for pn, qty in common_parts:
            cur.execute("""INSERT INTO l6.base_config_parts(config_id,pn,quantity,locked,sort_order)
                           VALUES(%s,%s,%s,TRUE,0) ON CONFLICT DO NOTHING""", (cid, pn, qty))
        print(f"  + 基准「{name}」id={cid}，底盘件 {len(common_parts)} 项")
    return cid


def _type_id(name):
    cur.execute("SELECT id FROM l6.server_types WHERE name=%s", (name,))
    r = cur.fetchone()
    return r["id"] if r else None


def ensure_model(name, form, bays, use, base_cid, type_name):
    cur.execute("SELECT 1 FROM l6.server_models WHERE name=%s", (name,))
    if cur.fetchone():
        print(f"  · 机型「{name}」已存在")
        return
    cur.execute("""INSERT INTO l6.server_models(name,server_type_id,form,bays,use,base_config_id,sort_order)
                   VALUES(%s,%s,%s,%s,%s,%s,0)""",
                (name, _type_id(type_name), form, bays, use, base_cid))
    print(f"  + 机型「{name}」({use}) → 基准 {base_cid}")


# ============ 1. 确保料号（STEP 真实 PN）============
print("① 确保料号")
PARTS = [
    # 公共 / 机箱
    ("S.E.M.0000351", "机箱 2U12(含硬盘笼)", "机箱", 4178, {"bays": 12, "form": "2U"}),
    ("S.E.M.0000186", "滑轨 Slide Rail", "滑轨", 340, {}),
    ("S.E.E.0001559", "三模背板(12盘)", "背板", 1260, {"bays": 12, "bt": "tri"}, "tri"),
    ("S.E.E.0001558", "直连背板(12盘)", "背板", 1050, {"bays": 12, "bt": "dc"}, "dc"),
    # Orion 平台
    ("S.E.M.0000272", "主板托盘(Orion)", "托盘", 175, {}),
    ("S.E.E.0003275", "Orion 主板", "主板", 5300, {}),
    ("S.E.M.0000189", "CPU 散热器(Orion)", "散热器", 121, {}),
    ("S.E.E.0003242", "SCMIO 后IO板", "后IO板", 75, {}),
    ("S.E.E.0002303", "后IO信号线 Slimsas", "IO线缆", 60.33, {}),
    ("S.E.E.0001675", "后IO电源线 1x4PIN", "IO线缆", 4, {}),
    ("S.E.E.0003041", "电源线 Power Cord", "电源线", 9.25, {}),
    ("S.E.M.0000355", "后置电源导风罩(Orion)", "导风罩", 60.5, {}),
    ("S.E.M.0000452", "外购霄擎标签", "标签", 0.5, {}),
    # Polaris 平台
    ("S.E.M.0000321", "主板托盘(Polaris)", "托盘", 175, {}),
    ("S.E.E.0003146", "Polaris 主板", "主板", 6700, {}),
    ("S.E.E.0003148", "Polaris BMC 板", "后IO板", 1000, {}),
    ("S.E.M.0000299", "CPU 散热器(Polaris)", "散热器", 550, {}),
    ("S.E.M.0000265", "CPU Carrier 载具", "散热器", 185, {}),
    ("S.E.M.0000354", "后置导风罩(Polaris)", "导风罩", 53, {}),
    ("S.E.E.0000771", "电源线(Polaris)", "电源线", 9, {}),
    ("S.E.M.0000191", "机箱 2U25(含硬盘笼+背板)", "机箱", 6905, {"bays": 25, "form": "2U"}),
    ("S.E.E.0001952", "HBA Cable(后RAID到扩展背板)", "IO线缆", 64.22, {}),
]
for p in PARTS:
    ensure_part(p[0], p[1], p[2], p[3], p[4], p[5] if len(p) > 5 else None)

# ============ 2. 基准配置 ============
print("② 基准配置")
ORION_COMMON = [("S.E.M.0000351", 1), ("S.E.M.0000272", 1), ("S.E.E.0003275", 1),
                ("S.E.M.0000189", 2), ("S.E.E.0003242", 1), ("S.E.E.0002303", 1),
                ("S.E.E.0001675", 1), ("S.E.E.0003041", 2), ("S.E.M.0000186", 1),
                ("S.E.M.0000355", 1), ("S.E.M.0000452", 1)]
POLARIS_COMMON = [("S.E.M.0000351", 1), ("S.E.M.0000321", 1), ("S.E.E.0003146", 1),
                  ("S.E.E.0003148", 1), ("S.E.E.0003242", 1), ("S.E.M.0000299", 2),
                  ("S.E.M.0000265", 2), ("S.E.M.0000354", 1), ("S.E.M.0000186", 1),
                  ("S.E.E.0000771", 2)]
orion_cid = ensure_base("ES22V3-P 基准(Orion 2U12)", "Orion", "2U", 12,
                        "S.E.E.0001559", "S.E.E.0001558", ORION_COMMON)
polaris_cid = ensure_base("ZS22V2-P 基准(Polaris 2U12)", "Polaris", "2U", 12,
                          "S.E.E.0001559", "S.E.E.0001558", POLARIS_COMMON)

# 2U25 基准（机箱 S.E.M.0000191 已含背板，bp_tri/bp_dc 留空）
ORION_25_COMMON = [("S.E.M.0000191",1),("S.E.M.0000272",1),("S.E.E.0003275",1),
                   ("S.E.M.0000189",2),("S.E.E.0003242",1),("S.E.E.0002303",1),
                   ("S.E.E.0001675",1),("S.E.E.0003041",2),("S.E.M.0000186",1),
                   ("S.E.E.0001952",1),("S.E.M.0000355",1),("S.E.M.0000452",1)]
POLARIS_25_COMMON = [("S.E.M.0000191",1),("S.E.M.0000321",1),("S.E.E.0003146",1),
                     ("S.E.E.0003148",1),("S.E.E.0003242",1),("S.E.M.0000299",2),
                     ("S.E.M.0000265",2),("S.E.M.0000354",1),("S.E.M.0000186",1),
                     ("S.E.E.0002303",1),("S.E.E.0001675",1),("S.E.E.0000771",2)]
orion25_cid = ensure_base("ES25V3-P 基准(Orion 2U25)", "Orion", "2U", 25, None, None, ORION_25_COMMON)
polaris25_cid = ensure_base("ZS25V2-P 基准(Polaris 2U25)", "Polaris", "2U", 25, None, None, POLARIS_25_COMMON)

# ============ 3. 机型 ============
print("③ 机型目录")
ensure_model("ES22V3-P", "2U", 12, "通用计算", orion_cid, "通用计算服务器")
ensure_model("ES24V3-P", "2U", 12, "AI加速计算", orion_cid, "AI / 加速计算服务器")
ensure_model("ZS22V2-P", "2U", 12, "通用计算", polaris_cid, "通用计算服务器")
ensure_model("ES25V3-P", "2U", 25, "存储", orion25_cid, "存储服务器")
ensure_model("ZS25V2-P", "2U", 25, "存储", polaris25_cid, "存储服务器")

conn.commit()
cur.close()
conn.close()
print("\n✅ 种子完成。去 /servers → 配置，应能看到 3 个机型。")
