# -*- coding: utf-8 -*-
"""风扇行修复迁移（2026-09-15，幂等，可重复执行）：

背景：4U 基准配置（ZSA24V3-P/ESA24V3-P/ESA25V3-P）没挂风扇件，BOM 模板 fan 行的
宽松匹配（name 子串含"风扇"即命中）蹭上了「风扇背板转接线」，L6 输出
「FAN 风扇背板转接线（2x6pin→2x3pinX2 550mm）/ qty 1」。用户定调：
风扇 = 料号库 S.E.M.0000501「6056高性能热插拔风扇」，2U=6 个 / 4U=12 个。

动作：
  A. parts_master：S.E.M.0000501 名称去首尾空格（曾带尾空格，输出会带脏字符）。
  B. 4U 三个基准配置补挂 6056 风扇 qty=12；ZSA24V3-P 另补 Polaris CPU 散热器 qty=2
     （与 2U 的 ZS 系列同款；已存在则跳过）。
  C. 模板 #2/#3（4U8-GPU直连 / 4U8-Switch）fan 行 qty_fallback 6→12。
  D. 模板 #1（2U12标准）fan 行 desc 从 specs.model（只输出"6056"）改为
     part_field(name)（输出完整名称），与 #2/#3 统一；原 desc_fallback 与新主规则
     重复，删除。
"""
import json
import sys

import sqlalchemy as sa
from _localdb import db_url

ENG = sa.create_engine(db_url(), connect_args={"client_encoding": "UTF8"})

FAN_PN = "S.E.M.0000501"
HEATSINK_POLARIS_PN = "S.E.M.0000299"
# 4U 基准配置 → 补挂清单 {config_id: [(pn, quantity)]}
ATTACH = {
    22: [(FAN_PN, 12), (HEATSINK_POLARIS_PN, 2)],   # ZSA24V3-P：风扇+散热器全缺
    25: [(FAN_PN, 12)],                              # ESA24V3-P：只缺风扇
    26: [(FAN_PN, 12)],                              # ESA25V3-P：只缺风扇
}


def main() -> int:
    with ENG.begin() as c:
        # A. 名称 trim（幂等：无首尾空格则 0 行更新）
        r = c.execute(sa.text(
            "UPDATE l6.parts_master SET name = TRIM(name) WHERE pn = :pn AND name <> TRIM(name)"
        ), {"pn": FAN_PN})
        print(f"[A] trim 6056 名称：更新 {r.rowcount} 行")

        # B. 补挂底盘件（幂等：按 config_id+pn 查重）
        for cfg_id, items in ATTACH.items():
            name = c.execute(sa.text(
                "SELECT name FROM l6.base_configs WHERE id=:i"), {"i": cfg_id}).scalar()
            for pn, qty in items:
                exists = c.execute(sa.text(
                    "SELECT 1 FROM l6.base_config_parts WHERE config_id=:c AND pn=:p"
                ), {"c": cfg_id, "p": pn}).first()
                if exists:
                    print(f"[B] cfg#{cfg_id} {name}：{pn} 已挂载，跳过")
                    continue
                next_so = c.execute(sa.text(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM l6.base_config_parts WHERE config_id=:c"
                ), {"c": cfg_id}).scalar()
                c.execute(sa.text(
                    "INSERT INTO l6.base_config_parts (config_id, pn, quantity, locked, sort_order) "
                    "VALUES (:c, :p, :q, FALSE, :s)"
                ), {"c": cfg_id, "p": pn, "q": qty, "s": next_so})
                print(f"[B] cfg#{cfg_id} {name}：挂载 {pn} qty={qty} sort_order={next_so}")

        # C+D. 模板规则修正（幂等：已是目标形态则跳过）
        for tid in (1, 2, 3):
            row = c.execute(sa.text(
                "SELECT name, rows FROM l6.bom_templates WHERE id=:i"
            ), {"i": tid}).mappings().first()
            tpl_name, raw_rows = row["name"], row["rows"]
            rows = raw_rows if isinstance(raw_rows, list) else json.loads(raw_rows or "[]")
            changed = False
            for r in rows:
                if r.get("type") != "fan":
                    continue
                rule = r.get("rule") or {}
                # C. 4U 模板 fallback 6→12
                fb = rule.get("qty_fallback")
                if tid in (2, 3) and isinstance(fb, dict) and fb.get("kind") == "fixed" and fb.get("value") == 6:
                    fb["value"] = 12
                    changed = True
                    print(f"[C] 模板#{tid} {tpl_name}：fan qty_fallback 6→12")
                # D. 模板#1 desc 统一取 name
                if tid == 1 and isinstance(rule.get("desc"), dict) and rule["desc"].get("field") != "name":
                    rule["desc"] = {"kind": "part_field", "field": "name", "category": "fan"}
                    if rule.get("desc_fallback") and rule["desc_fallback"].get("field") == "name":
                        del rule["desc_fallback"]   # 与主规则重复，不留两段同义代码
                    changed = True
                    print(f"[D] 模板#{tid} {tpl_name}：fan desc → part_field(name)")
            if changed:
                c.execute(sa.text(
                    "UPDATE l6.bom_templates SET rows = :rows WHERE id = :i"
                ), {"rows": json.dumps(rows, ensure_ascii=False), "i": tid})

    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
