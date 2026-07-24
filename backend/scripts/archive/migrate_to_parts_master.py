"""阶段①（数据层）· 把旧散落料号迁移进 parts_master，并重建基准配置

数据流向：
  旧 l6.l6_base_config_parts  ┐
  旧 l6.l6_front_panel_items  ├─→ parts.parts_master（去重 by pn，合并 specs）
  旧 l6.l6_rear_panel_items   │
  旧 l6.l6_psu_options        │
  旧 kp.kp_parts(+specs+price)┘
  旧 l6.l6_base_configs       ─→ l6.base_configs_new（背板件提取填 bp_tri/bp_dc_pn）
  旧 l6.l6_base_config_parts  ─→ l6.base_config_parts_new（排除背板，余为公共底盘件）
  种子                          l6.server_types / l6.server_models / rules.derivation_rules

安全：
  默认 dry-run（只打印统计，不写库）。确认无误后加 --commit 真正写入。
  废弃旧表需显式 --drop（且要求 --commit）。运行前请先 pg_dump 全库备份。

用法：
  python scripts/migrate_to_parts_master.py            # dry-run，只看统计
  python scripts/migrate_to_parts_master.py --commit   # 执行迁移（不删旧表）
  python scripts/migrate_to_parts_master.py --commit --drop  # 迁移后废弃旧表并 RENAME _new
"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="真正写入数据库（默认 dry-run）")
parser.add_argument("--drop", action="store_true", help="迁移后废弃旧表并 RENAME _new→正式（需 --commit）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor(cursor_factory=DictCursor)


def t(name):
    return f"table_exists:{name}"


def fetch(q, params=None):
    try:
        cur.execute(q, params or {})
        return [dict(r) for r in cur.fetchall()]
    except psycopg2.Error:
        return []  # 表不存在等，视为空


# ---------- category 启发式推断 ----------
def guess_category(name, hint=None):
    nm = name or ""
    low = nm.lower()
    rules = [
        (["机箱", "chassis"], "机箱"),
        (["主板", "motherboard", "orion mb"], "主板"),
        (["托盘", "tray"], "托盘"),
        (["散热", "heatsink", "hsink"], "散热器"),
        (["三模背板", "直连背板", "背板", "backplane"], "背板"),
        (["电源线", "power cord", "powercord"], "电源线"),
        (["sgpio"], "SGPIO线"),
        (["滑轨", "slide rail", "rail"], "滑轨"),
        (["导风"], "导风罩"),
        (["标签"], "标签"),
        (["线", "cable"], "IO线缆"),
    ]
    for keys, cat in rules:
        if any(k in nm or k in low for k in keys):
            return cat
    return hint or "底盘件"


def map_kp_category(cat_name):
    c = (cat_name or "").lower()
    m = [("cpu", "CPU"), ("处理器", "CPU"), ("gpu", "GPU"), ("显卡", "GPU"),
         ("内存", "内存"), ("memory", "内存"), ("硬盘", "硬盘"), ("存储", "硬盘"),
         ("ssd", "硬盘"), ("hdd", "硬盘"), ("m.2", "M.2"), ("m2", "M.2"),
         ("raid", "RAID卡"), ("阵列", "RAID卡"), ("网卡", "NIC"), ("nic", "NIC"),
         ("网络", "NIC"), ("fc", "FC"), ("光纤", "FC")]
    for k, v in m:
        if k in c:
            return v
    return cat_name or "KP配件"


def safe_json(v):
    if v is None or v == "":
        return None
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return v


# ---------- 1. 收集所有料号 → parts_master ----------
parts = {}  # pn -> dict

def upsert_part(pn, name, category, sub_type=None, specs=None, unit_price=0, supplier=None, applicable=None, sort_order=0):
    if not pn:
        return
    if pn in parts:
        # 合并 specs/applicable（后到的不覆盖已有键）
        old = parts[pn]
        old_specs = old.get("specs") or {}
        if specs:
            for k, v in specs.items():
                old_specs.setdefault(k, v)
            old["specs"] = old_specs
        old_app = old.get("applicable") or {}
        if applicable:
            for k, v in applicable.items():
                old_app.setdefault(k, v)
            old["applicable"] = old_app
        if not old.get("name") and name:
            old["name"] = name
    else:
        parts[pn] = dict(pn=pn, name=name or pn, category=category, sub_type=sub_type,
                         specs=specs or {}, unit_price=unit_price or 0, supplier=supplier,
                         applicable=applicable or {}, sort_order=sort_order)


# (a) l6_base_config_parts（底盘件，无 category 字段，按名猜）
for r in fetch("SELECT pn, part_name, description, unit_price, quantity, note FROM l6.l6_base_config_parts"):
    upsert_part(r["pn"], r["part_name"], guess_category(r["part_name"]),
                specs={"description": r["description"], "note": r["note"]},
                unit_price=r["unit_price"] or 0)

# (b) l6_front_panel_items（前面板线缆，含 group_size + applicable_*）
for r in fetch("SELECT * FROM l6.l6_front_panel_items"):
    upsert_part(r["pn"], r["part_name"], "前面板线缆", sub_type=r.get("cable_type"),
                specs={"kind": r.get("cable_type"), "group_size": r.get("group_size"),
                       "description": r.get("description")},
                unit_price=r.get("unit_price") or 0,
                applicable={"drive_bays": safe_json(r.get("applicable_drive_bays")),
                            "backplane": safe_json(r.get("applicable_backplane"))})

# (c) l6_rear_panel_items（后面板，按 option_type 分）
for r in fetch("SELECT * FROM l6.l6_rear_panel_items"):
    ot = r.get("option_type") or ""
    cat = {"riser": "后面板Riser", "nvme": "后面板模组", "sata": "后面板模组",
           "ocp": "OCP"}.get(ot.lower(), "后面板Riser")
    sub = "NVMe" if "nvme" in ot.lower() else ("SATA" if "sata" in ot.lower() else None)
    upsert_part(r["pn"], r["part_name"], cat, sub_type=sub,
                specs={"io_slot": r.get("io_slot"), "option_type": ot, "quantity": r.get("quantity")},
                unit_price=r.get("unit_price") or 0,
                applicable={"chassis": safe_json(r.get("applicable_chassis")),
                            "backplane": safe_json(r.get("applicable_backplane"))})

# (d) l6_psu_options（电源）
for r in fetch("SELECT * FROM l6.l6_psu_options"):
    w = r.get("wattage") or ""
    wnum = int("".join(ch for ch in str(w) if ch.isdigit()) or 0)
    upsert_part(r["pn"], r["part_name"], "电源", sub_type=str(w),
                specs={"wattage": wnum, "description": r.get("description")},
                unit_price=r.get("unit_price") or 0,
                applicable={"chassis": safe_json(r.get("applicable_chassis"))})

# (e) kp_parts + specs + 最新价格 + category 名
kp_cat = {r["id"]: r["name"] for r in fetch("SELECT id, name FROM kp.kp_categories")}
kp_specs = {}
for r in fetch("SELECT part_id, spec_key, spec_value FROM kp.kp_part_specs"):
    kp_specs.setdefault(r["part_id"], {})[r["spec_key"]] = r["spec_value"]
kp_price = {}
for r in fetch("""SELECT DISTINCT ON (part_id) part_id, price FROM kp.kp_price_history
                  WHERE price IS NOT NULL ORDER BY part_id, price_date DESC NULLS LAST"""):
    kp_price[r["part_id"]] = r["price"]
for r in fetch("SELECT * FROM kp.kp_parts"):
    pn = r.get("oem_sku") or r.get("alt_sku") or f"KP-{r['id']}"
    cat_name = kp_cat.get(r.get("category_id"))
    sp = dict(kp_specs.get(r["id"], {}))
    if r.get("condition"):
        sp["condition"] = r["condition"]
    upsert_part(pn, r["name"], map_kp_category(cat_name),
                specs=sp, unit_price=kp_price.get(r["id"]) or 0,
                supplier=r.get("brand"))

print(f"[统计] 去重后料号 {len(parts)} 条")

# ---------- 2. 基准配置（背板件提取）----------
old_configs = fetch("SELECT * FROM l6.l6_base_configs")
old_parts_by_cfg = {}
for r in fetch("SELECT * FROM l6.l6_base_config_parts"):
    old_parts_by_cfg.setdefault(r["config_id"], []).append(r)

new_configs = []  # (fields..., bp_tri_pn, bp_dc_pn)
new_parts = []    # (config_idx, pn, qty, locked)
for ci, cfg in enumerate(old_configs):
    bp_tri = bp_dc = None
    chassis_common = []
    for p in old_parts_by_cfg.get(cfg["config_id"], []):
        cat = guess_category(p["part_name"])
        if cat == "背板":
            nm = p["part_name"] or ""
            if "三模" in nm or "tri" in nm.lower():
                bp_tri = bp_tri or p["pn"]
            elif "直连" in nm or "dc" in nm.lower() or "direct" in nm.lower():
                bp_dc = bp_dc or p["pn"]
            else:
                bp_tri = bp_tri or p["pn"]  # 兜底归三模
        elif cat == "SGPIO线":
            pass  # SGPIO 随三模，配置时由背板 tri 自动带
        else:
            chassis_common.append(p)
    new_configs.append((cfg, bp_tri, bp_dc))
    for p in chassis_common:
        new_parts.append((ci, p["pn"], p.get("quantity") or 1, True))
print(f"[统计] 基准配置 {len(new_configs)} 条，公共底盘件 {len(new_parts)} 条")

# ---------- 3. 推导规则种子 ----------
RULE_SEEDS = [
    ("base_power", {"watts": 500}, "机箱基础功耗"),
    ("psu_qty_threshold", {"watts": 4800, "qty_low": 2, "qty_high": 4}, "电源数量：>阈值→4(2+2)，≤→2(1+1)"),
    ("psu_wattage", {"mode": "per_branch_full"}, "瓦数取 ≥功耗/路数 的最小档"),
    ("cable_group", {"SATA": 8, "SAS": 8, "NVMe": 2}, "前面板线缆每组盘数"),
    ("gpu_cable_per", {"per_model": {"RTX5090": 1, "A100": 2, "H100": 2}}, "GPU 供电线单卡根数"),
    ("bp_type", {"mech_kinds": ["SATA", "SAS"], "tri": "tri", "dc": "dc"}, "背板类型：含机械盘→三模，纯NVMe→直连"),
    ("gpu_arch_recommend", {"training": "switch", "inference": "pt"}, "GPU 架构用途推荐"),
    ("switch_constraint", {"gpu_required": 8}, "Switch 必 8 卡全互联"),
    ("switch_extra_parts", {"add_pn_category": ["NVSwitch", "NVLink"]}, "Switch 架构额外料号"),
]
SERVER_TYPE_SEEDS = [
    ("通用计算服务器", "企业应用、虚拟化、常规业务", 1),
    ("AI / 加速计算服务器", "模型训练与推理，多 GPU", 2),
    ("存储服务器", "大容量、高盘位密度", 3),
]

# ---------- 写库 ----------
if not args.commit:
    print("\n[dry-run] 未写库。确认统计无误后加 --commit 执行。")
else:
    # parts_master
    for p in parts.values():
        cur.execute("""INSERT INTO parts.parts_master
            (pn,name,category,sub_type,specs,unit_price,supplier,applicable,sort_order)
            VALUES (%(pn)s,%(name)s,%(category)s,%(sub_type)s,%(specs)s,%(unit_price)s,%(supplier)s,%(applicable)s,%(sort_order)s)
            ON CONFLICT (pn) DO UPDATE SET
              name=EXCLUDED.name, specs=parts.parts_master.specs||EXCLUDED.specs,
              applicable=parts.parts_master.applicable||EXCLUDED.applicable""",
                    {**p, "specs": json.dumps(p["specs"], ensure_ascii=False),
                     "applicable": json.dumps(p["applicable"], ensure_ascii=False)})
    print(f"✓ parts_master 写入 {len(parts)} 条")

    # server_types
    for name, desc, so in SERVER_TYPE_SEEDS:
        cur.execute("INSERT INTO l6.server_types(name,description,sort_order) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING", (name, desc, so))
    print("✓ server_types 种子")
    # 清空 _new 表（幂等，避免重跑累积重复）
    cur.execute("DELETE FROM l6.base_config_parts_new")
    cur.execute("DELETE FROM l6.base_configs_new")

    # base_configs_new + base_config_parts_new
    type_id = {r["name"]: r["id"] for r in fetch("SELECT id,name FROM l6.server_types")}
    default_type = list(type_id.values())[0] if type_id else None
    for idx, (cfg, bp_tri, bp_dc) in enumerate(new_configs):
        cur.execute("""INSERT INTO l6.base_configs_new
            (name,server_type_id,series,model,form,bays,bp_tri_pn,bp_dc_pn,gpu_arch_default,sort_order)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cfg.get("description") or f"config-{cfg['config_id']}", default_type,
             cfg.get("chassis_series"), cfg.get("chassis"), cfg.get("chassis"),
             int("".join(c for c in str(cfg.get("drive_bays") or "0") if c.isdigit()) or 0),
             bp_tri, bp_dc, "none", cfg.get("sort_order") or 0))
        new_cfg_id = cur.fetchone()[0]
        # 该 config(idx) 的底盘件
        for (ci, pn, qty, locked) in new_parts:
            if ci == idx:
                cur.execute("""INSERT INTO l6.base_config_parts_new(config_id,pn,quantity,locked,sort_order)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (new_cfg_id, pn, qty, locked, 0))
    print(f"✓ base_configs_new {len(new_configs)} 条 + 底盘件")

    # derivation_rules 种子
    for key, params, note in RULE_SEEDS:
        cur.execute("""INSERT INTO rules.derivation_rules(rule_key,params,note)
            VALUES(%s,%s,%s) ON CONFLICT (rule_key) DO UPDATE SET params=EXCLUDED.params, note=EXCLUDED.note""",
            (key, json.dumps(params, ensure_ascii=False), note))
    print(f"✓ derivation_rules 种子 {len(RULE_SEEDS)} 条")

    conn.commit()
    print("\n迁移写入完成。")

    if args.drop:
        for tname in ["l6_front_panel_items", "l6_rear_panel_items", "l6_psu_options",
                      "l6_bom_templates", "l6_bom_parts"]:
            cur.execute(f"DROP TABLE IF EXISTS l6.{tname} CASCADE")
        cur.execute("ALTER TABLE IF EXISTS l6.l6_base_configs RENAME TO l6_base_configs_old")
        cur.execute("ALTER TABLE IF EXISTS l6.l6_base_config_parts RENAME TO l6_base_config_parts_old")
        cur.execute("ALTER TABLE l6.base_configs_new RENAME TO base_configs")
        cur.execute("ALTER TABLE l6.base_config_parts_new RENAME TO base_config_parts")
        conn.commit()
        print("✓ 旧表已废弃/重命名（base_configs_old/base_config_parts_old 保留备份，旧库表已 DROP）。")

cur.close()
conn.close()
