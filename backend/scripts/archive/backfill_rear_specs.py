"""一次性回填：以 l6_rear_panel_items 为权威源，把后面板语义重写进 parts_master.specs。

背景：migrate_to_parts_master.py 当年把 rear 表写进 specs 时降级了——
  - io_slot 存成单字符串（S.E.E.0002346 只剩 "IO1"，丢了 IO2/IO3）
  - option_type 用了中文标签（"Riser"/"SATA模组"），和前端代号（x8/sata）对不上
  - chassis 混进了 2U（形态），且大多为空
旧表 l6_rear_panel_items 本身数据干净（option_type 用代号、io_slot/chassis/qty 齐全），
故以它为准重写 specs 的 io_slot（数组）/option_type（代号）/chassis（机型系列数组），
并丢弃过时的 specs.quantity 键（数量改由配置时定，见计划 Phase 1）。

冲突价处理：S.E.E.0001561 / S.E.E.0002346 在旧表里 Orion 与 Polaris 两个价。
按用户定调（PN 唯一即价格唯一，Polaris 变体应另起 PN），本脚本：
  - 不擅自造 PN；
  - chassis 写完整并集（不切断 Polaris，避免现有 Polaris 配置暂时无料可选）；
  - 价格沿用 parts_master 现值（=Orion 价），只在报告里 prominently 标记冲突，等用户拆 PN。

安全：默认 dry-run（只打印），--commit 才写库。仅写 parts_master.specs，不动旧表结构。
用法：
  python -X utf8 scripts/backfill_rear_specs.py            # dry-run
  python -X utf8 scripts/backfill_rear_specs.py --commit   # 实际写
"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="真正写入数据库（默认 dry-run）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor(cursor_factory=DictCursor)


def load_specs(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except Exception:
        return {}


def safe_json_list(raw):
    """旧表 applicable_chassis 是 TEXT 存的 JSON 数组（如 '["Orion"]'）；容错解析成 list。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [raw]
    return []


# 仅认机型系列，剔除 2U 之类误值
VALID_SERIES = {"Orion", "Polaris"}

# 1) 从旧表聚合每个 PN 的 io_slot / option_type / chassis + 检测价格冲突
cur.execute(
    "SELECT pn, part_name, io_slot, option_type, unit_price, applicable_chassis "
    "FROM l6.l6_rear_panel_items "
    "WHERE option_type IS NOT NULL AND option_type <> 'blank' "
    "  AND pn IS NOT NULL AND pn <> ''"
)
agg = {}  # pn → {name, slots:set, option_types:set, chassis:set, prices:set}
for r in cur.fetchall():
    pn = r["pn"]
    a = agg.setdefault(pn, {"name": r["part_name"], "slots": set(), "ots": set(),
                            "chassis": set(), "prices": set()})
    if r["io_slot"]:
        a["slots"].add(r["io_slot"])
    if r["option_type"]:
        a["ots"].add(r["option_type"])
    for ch in safe_json_list(r["applicable_chassis"]):
        if ch in VALID_SERIES:
            a["chassis"].add(ch)
    if r["unit_price"] is not None:
        a["prices"].add(float(r["unit_price"]))

print(f"=== 旧表聚合：{len(agg)} 颗 rear 料 ===\n")
conflicts = []
updates = []
for pn, a in agg.items():
    slots = sorted(a["slots"])
    chassis = sorted(a["chassis"])
    ots = sorted(a["ots"])
    if len(ots) > 1:
        print(f"  ⚠ {pn}: option_type 不一致 {ots}（应一料一代号，请人工核对）")
    ot = ots[0] if ots else None
    price_conflict = len(a["prices"]) > 1
    if price_conflict:
        conflicts.append((pn, a["name"], sorted(a["prices"]), chassis))
    updates.append({"pn": pn, "name": a["name"], "slots": slots, "ot": ot,
                    "chassis": chassis, "conflict": price_conflict})
    flag = " ⚠冲突价" if price_conflict else ""
    print(f"  {pn:16} | slots={slots} | ot={ot} | chassis={chassis or '(空)'}{flag}")

# 2) 写回 parts_master.specs（合并：覆写 io_slot/option_type/chassis，丢 quantity，保其余键）
print("\n=== 写回 parts_master.specs ===")
written = 0
missing = []
for u in updates:
    cur.execute("SELECT specs FROM l6.parts_master WHERE pn = %s", (u["pn"],))
    row = cur.fetchone()
    if not row:
        missing.append(u["pn"])
        print(f"  ✗ {u['pn']}: parts_master 无此料（先在编辑表单新增）")
        continue
    specs = load_specs(row["specs"])
    if u["slots"]:
        specs["io_slot"] = u["slots"]
    else:
        specs.pop("io_slot", None)
    if u["ot"]:
        specs["option_type"] = u["ot"]
    else:
        specs.pop("option_type", None)
    if u["chassis"]:
        specs["chassis"] = u["chassis"]
    else:
        specs.pop("chassis", None)
    specs.pop("quantity", None)  # 过时键，数量改由配置时定
    if args.commit:
        cur.execute(
            "UPDATE l6.parts_master SET specs = CAST(%s AS jsonb) WHERE pn = %s",
            (json.dumps(specs, ensure_ascii=False), u["pn"]),
        )
    written += 1

# 3) 捆绑预览（验证分组正确：IO3/sata 应聚合 3 颗）
print("\n=== 捆绑预览（按 io_slot × option_type 分组）===")
groups = {}
for u in updates:
    for slot in u["slots"]:
        groups.setdefault((slot, u["ot"]), []).append(u["pn"])
for (slot, ot), pns in sorted(groups.items()):
    tag = f"  ⭐ {len(pns)} 件捆绑" if len(pns) > 1 else f"  单料"
    print(f"  {slot:5} / {ot:7} → {tag}: {pns}")

# 4) 冲突价报告
print("\n=== ⚠ 价格冲突 PN（Polaris 变体待你拆成独立 PN）===")
if not conflicts:
    print("  (无)")
for pn, name, prices, chassis in conflicts:
    print(f"  {pn} ({name}): 旧表价 {prices} | 适用 {chassis} → 现挂单值，Polaris 价待拆 PN")

if missing:
    print(f"\n⚠ {len(missing)} 颗料在 parts_master 缺失：{missing}")

if args.commit:
    conn.commit()
    print(f"\n已提交：写回 {written} 颗料的 specs")
else:
    print(f"\nDRY-RUN（未写入）: 将写回 {written} 颗料的 specs  确认无误后加 --commit")
conn.close()
