# -*- coding: utf-8 -*-
"""一次性迁移：把「产物槽 slot」写进节点抽屉的目标层插头（唯一真源搬到配置里）。

背景：产物分发原先靠代码里的「节点 → 产物」兜底表（已删）。现在分发**只认抽屉声明的
slot**，所以必须把已有抽屉配置补齐——否则该节点产物为空（白盒不装懂，不猜）。

覆盖两处配置源：
  rules.reasoning_node_default   节点默认契约（skill_key 维度）
  rules.reasoning_node_config    各流的增量覆盖（flow_id 维度）

用法（backend 目录）：python -X utf8 scripts/migrate_node_artifact_slots.py [--apply]
默认 dry-run，只打印将改动的行；加 --apply 才写库。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.base import Rules_SessionLocal
from app.models.reasoning_flow import ReasoningNodeConfig
from app.models.skill_config import ReasoningNodeDefault
from app.services.skill_config_bootstrap import plug_with_slot

# 产物槽针脚方言唯一来源 = 节点默认契约（skill_config_bootstrap.NODE_PLUGS）


def _plug(cfg: dict, node_key: str, *, only_if_declared: bool) -> tuple:
    """把 slot 并进该节点的目标层插头（保留既有 name/kind/columns，只补针脚）。

    only_if_declared=True（用于增量行）：只补**该增量自己声明了 target** 的节点。
    因为合并语义里列表是「整体替换」——给没声明 target 的增量凭空写一个 target，
    会把默认契约里的 artifacts（列契约/字段）整条盖掉。
    """
    if only_if_declared and not isinstance((cfg or {}).get("target"), dict):
        return dict(cfg or {}), False
    out = plug_with_slot(str(node_key or ""), cfg)
    return out, out != (cfg or {})


def _run(rows, label: str, apply: bool, only_if_declared: bool = False) -> int:
    changed = 0
    for row in rows:
        try:
            cfg = json.loads(row.config) if row.config else {}
        except (TypeError, ValueError):
            continue
        new, hit = _plug(cfg, row.node_key, only_if_declared=only_if_declared)
        if not hit:
            continue
        changed += 1
        print(f"  {label} {getattr(row, 'skill_key', '') or row.flow_id} / {row.node_key}: "
              f"slot={new['target']['artifacts'][0]['slot']}")
        if apply:
            row.config = json.dumps(new, ensure_ascii=False)
    return changed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    args = ap.parse_args()
    s = Rules_SessionLocal()
    try:
        print("== rules.reasoning_node_default ==")
        n1 = _run(s.query(ReasoningNodeDefault).all(), "default", args.apply)
        print("== rules.reasoning_node_config ==")
        n2 = _run(s.query(ReasoningNodeConfig).all(), "delta", args.apply,
                  only_if_declared=True)
        if args.apply:
            s.commit()
        print(f"待迁移 {n1 + n2} 行（{'已写入' if args.apply else 'dry-run，未写库'}）")
    finally:
        s.close()


if __name__ == "__main__":
    main()
