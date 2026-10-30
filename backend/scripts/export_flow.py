# -*- coding: utf-8 -*-
"""流定义导出（种子通道·出）：flow_key → backend/seeds/flows/<flow_key>.json。

工作流定义（reasoning_flow 行 + reasoning_node_config 行 + skill_catalog 条目）是
"图纸"不是"产品"——必须进 git，环境间搬运走种子文件，不靠库对库拷贝。
2026-10-24 切库合并漏带交付流数据的根治手段：任何环境缺流，import_flow 灌种子即回。

用法：python scripts/export_flow.py <flow_key> [更多flow_key...]
导出内容：该 skill_key 的 active 流行（含 graph/launch_form）+ 其全部节点配置行
+ skill_catalog 里 workflow_key 命中的条目。只读不写库。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.models.base import engine  # noqa: E402

SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds", "flows")


def export_one(flow_key: str) -> str:
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, name, skill_key, version, status, graph, launch_form, is_active, "
            "description, created_by, updated_by FROM rules.reasoning_flow "
            "WHERE skill_key = :k AND is_active"), {"k": flow_key}).mappings().fetchall()
        if not rows:
            print(f"✗ {flow_key}：库里没有 active 流，无法导出")
            return None
        flow = dict(rows[0])
        cfgs = c.execute(text(
            "SELECT node_key, config FROM rules.reasoning_node_config "
            "WHERE flow_id = :fid ORDER BY id"), {"fid": flow["id"]}).mappings().fetchall()
        # config 列直出为 JSON 字符串——种子统一解析成对象（import 侧再遇字符串会兜底解析）
        norm_cfgs = []
        for r in cfgs:
            d = dict(r)
            if isinstance(d.get("config"), str):
                try:
                    d["config"] = json.loads(d["config"])
                except (ValueError, TypeError):
                    pass
            norm_cfgs.append(d)
        cat = c.execute(text(
            "SELECT key, name, type, workflow_key, description, prompt, tool_ids, "
            "input_contract, output_contract, output_kind FROM rules.skill_catalog "
            "WHERE workflow_key = :k AND COALESCE(is_deleted, false) = false "
            "ORDER BY id DESC LIMIT 1"), {"k": flow_key}).mappings().fetchall()
    seed = {
        "seed_version": 1,
        "flow_key": flow_key,
        "exported_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "flow": flow,
        "node_configs": norm_cfgs,
        "catalog": dict(cat[0]) if cat else None,
    }
    os.makedirs(SEED_DIR, exist_ok=True)
    path = os.path.join(SEED_DIR, f"{flow_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=2, default=str)
    size = os.path.getsize(path)
    print(f"✓ {flow_key} → {path}（{size} 字节，v{flow['version']}，{len(seed['node_configs'])} 条节点配置，"
          f"目录条目{'有' if seed['catalog'] else '无'}）")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="流定义导出为种子文件（进 git）")
    ap.add_argument("flow_keys", nargs="+", help="skill_key（flow_key），可多个")
    args = ap.parse_args()
    ok = [p for k in args.flow_keys if (p := export_one(k))]
    sys.exit(0 if ok else 1)
