# -*- coding: utf-8 -*-
"""P0a: KP GPU spec 补数(源=用户 Excel v10 GPU型号库 + 公开硬参数)。
- 只补缺失项,不覆盖已有值;对不上/没把握的留空进「待核」清单,不猜。
- Interconnect 为新增维度;GPU 类内 'tdp' → 'TDP' 规范化(前置检查 rules/system_config 无引用才执行)。
- 默认 dry_run 只打印;--apply 先备份 _backup_gpu_specs_<date>.json 再写库。
用法: python -X utf8 scripts/fill_gpu_specs_v10.py [--apply]
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
for line in open(Path(__file__).resolve().parent.parent / ".env", encoding="utf-8"):
    line = line.strip()
    if line.startswith("POSTGRES_") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v

from sqlalchemy import create_engine, text  # noqa: E402

# 受控映射 part_id → 待补 spec。空 dict = 该卡缺项无把握,进待核清单。
FILLS = {
    149: {"Interconnect": "PCIe"},
    150: {"Memory Bandwidth": "1008 GB/s", "Interconnect": "PCIe"},
    151: {"Memory Bandwidth": "1008 GB/s", "Interconnect": "PCIe"},
    152: {"Interconnect": "PCIe"},
    153: {"Interconnect": "PCIe"},
    154: {"Memory Bandwidth": "576 GB/s", "Interconnect": "PCIe"},
    156: {"Interconnect": "PCIe"},
    157: {"Interconnect": "PCIe"},
    158: {"Interconnect": "PCIe"},
    159: {"Memory Bandwidth": "1008 GB/s", "Interconnect": "PCIe"},
    160: {"Interconnect": "PCIe"},
    162: {"Interconnect": "PCIe"},
    164: {"Interconnect": "PCIe"},
    165: {"Capacity": "64 GB", "Interconnect": "BLink"},
    166: {"Capacity": "64 GB", "Interconnect": "BLink"},
    168: {"Capacity": "64 GB", "Memory Bandwidth": "1800 GB/s", "Interconnect": "MetaXLink"},
    169: {},
    175: {},
    177: {},
    178: {},
    181: {},
    189: {"Interconnect": "NVLink"},
    190: {"Interconnect": "NVLink"},
    201: {"Interconnect": "PCIe"},
    232: {"Memory Bandwidth": "2039 GB/s", "Interconnect": "NVLink"},
    250: {"Interconnect": "NVLink"},
    254: {"Interconnect": "PCIe"},
    270: {"Interconnect": "片间互联"},
    280: {"Interconnect": "PCIe"},
    312: {"Interconnect": "PCIe"},
    343: {"Interconnect": "PCIe"},
    356: {"Interconnect": "PCIe"},
    364: {"Memory Bandwidth": "960 GB/s", "TDP": "360 W", "Interconnect": "PCIe"},
    372: {"Interconnect": "PCIe"},
    398: {},
    400: {"Interconnect": "PCIe"},
}


def main(apply: bool):
    eng = create_engine(
        f"postgresql+psycopg2://postgres:{os.environ['POSTGRES_PASSWORD']}@localhost:5432/cpq_platform",
        connect_args={"client_encoding": "UTF8"})
    with eng.connect() as c:
        parts = dict(c.execute(text(
            "select p.id, p.name from kp.kp_parts p "
            "join kp.kp_categories t on t.id = p.category_id where t.name = 'GPU'")).fetchall())
        cur: dict = {}
        for pid, k, v in c.execute(text(
                "select part_id, spec_key, spec_value from kp.kp_part_specs where part_id = any(:ids)"),
                {"ids": sorted(FILLS)}):
            cur.setdefault(pid, {})[k] = v

        inserts, renames, skipped = [], [], []
        CANON = {"Capacity", "Memory Bandwidth", "TDP", "Interconnect"}
        for pid in sorted(FILLS):
            name, have = parts.get(pid, "?"), cur.get(pid, {})
            for k, v in FILLS[pid].items():
                assert k in CANON, f"键名不在规范集: id={pid} {k!r}"
                if k in have:
                    skipped.append(f"id={pid} {name[:32]} {k} 已有 {have[k]!r},不覆盖")
                else:
                    inserts.append((pid, name, k, v))
        for pid, have in cur.items():
            if "tdp" in have:
                renames.append((pid, have["tdp"]))

        print(("== dry_run(不写库) ==" if not apply else "== apply =="))
        for pid, name, k, v in inserts:
            print(f"  + id={pid:<4d} {name[:34]:36s} {k} = {v}")
        if renames:
            print(f"  ~ 规范化 {len(renames)} 行 'tdp'→'TDP'(仅 GPU 类)")
        for s in skipped:
            print(f"  · 跳过 {s}")

        if renames:
            n_rules = c.execute(text(
                "select count(*) from rules.compatibility_rules where body::text ilike '%tdp%'")).scalar()
            n_cfg = c.execute(text(
                "select count(*) from rules.system_config where value::text ilike '%tdp%'")).scalar()
            if n_rules or n_cfg:
                print(f"  ! 检测到外部引用 tdp(rules={n_rules}/config={n_cfg}),跳过规范化")
                renames = []
        print(f"\n合计:新增 {len(inserts)},改名 {len(renames)},跳过 {len(skipped)}")

        if not apply:
            print("(dry_run 结束;加 --apply 执行)")
            return
        bak = Path(__file__).parent / f"_backup_gpu_specs_{date.today():%Y%m%d}.json"
        bak.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已备份现有 spec → {bak.name}")
        for pid, _name, k, v in inserts:
            c.execute(text(
                "insert into kp.kp_part_specs (part_id, spec_key, spec_value) values (:p, :k, :v)"),
                {"p": pid, "k": k, "v": v})
        for pid, _v in renames:
            c.execute(text(
                "update kp.kp_part_specs set spec_key = 'TDP' where part_id = :p and spec_key = 'tdp'"),
                {"p": pid})
        c.commit()
        print(f"完成:写入 {len(inserts)} 项,改名 {len(renames)} 行。")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
