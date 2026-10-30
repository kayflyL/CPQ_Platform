# -*- coding: utf-8 -*-
"""新流脚手架（种子通道·模板）：从模板流种子复制 → 改 key/name → 生成新种子文件。

"搭一条新流"的第一步 = 跑本命令生成种子，再灌入：
  python scripts/new_flow.py --key demo_flow --name "演练流" [--from trend_analysis]
  python scripts/import_flow.py seeds/flows/demo_flow.json
之后在画布上逐节点填空（改标签/目标层/规则/工具白名单），发布闸把关。

处理规则：
- flow：skill_key/name 换新、version=1、is_active=true、description 占位；
  graph 拓扑与节点配置沿用模板（含产物槽声明——模板自带合规声明），
  manual_rules 清空（模板的业务规则不属于新流，配置者在画布左栏重写）；
- catalog：生成最小条目（key/name/type/workflow_key），不复制模板的
  prompt/tool_ids 等业务内容（那些属于旧域）；output_kind 沿用模板（交付语义参考）；
- 节点配置整体沿用模板（含决策点/产物声明——新流从合规骨架起步）。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "..", "seeds", "flows")


def main():
    ap = argparse.ArgumentParser(description="新流脚手架：模板种子 → 新流种子")
    ap.add_argument("--key", required=True, help="新流 skill_key（kebab-case）")
    ap.add_argument("--name", required=True, help="新流显示名")
    ap.add_argument("--from", dest="template", default="trend_analysis",
                    help="模板 flow_key（默认 trend_analysis：最简三节点骨架）")
    args = ap.parse_args()

    src = os.path.join(SEED_DIR, f"{args.template}.json")
    if not os.path.exists(src):
        print(f"✗ 模板种子不存在：{src}（先 export_flow 导出或选其他模板）")
        sys.exit(1)
    seed = json.load(open(src, encoding="utf-8"))

    seed["flow_key"] = args.key
    seed["exported_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    flow = seed["flow"]
    flow["name"] = args.name
    flow["skill_key"] = args.key
    flow["version"] = 1
    flow["is_active"] = True
    flow["description"] = "（脚手架生成，待填描述）"
    graph = flow.get("graph")
    if isinstance(graph, dict):
        graph["manual_rules"] = ""
    # 目录条目换新（只留结构字段，业务内容不继承旧域）；NOT NULL 列给安全占位
    cat = seed.get("catalog")
    if isinstance(cat, dict):
        seed["catalog"] = {"key": args.key, "name": args.name, "type": "workflow",
                           "workflow_key": args.key,
                           "description": "（脚手架生成，待填描述）",
                           "prompt": "", "tool_ids": "", "input_contract": "",
                           "output_contract": "", "is_deleted": False,
                           "created_by": "scaffold", "updated_by": "scaffold",
                           "hit_count": 0,
                           **{k: cat.get(k) for k in ("type", "output_kind") if cat.get(k) is not None}}

    dst = os.path.join(SEED_DIR, f"{args.key}.json")
    if os.path.exists(dst):
        print(f"✗ 种子已存在：{dst}（换 --key，或手工删除旧文件）")
        sys.exit(1)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=2, default=str)
    print(f"✓ 新流种子已生成：{dst}")
    print("下一步：")
    print(f"  1. python scripts/import_flow.py seeds/flows/{args.key}.json   # 灌入（空缺才灌）")
    print("  2. 画布打开该流：改节点标签/目标层/规则/工具白名单 → 保存（发布闸把关）")
    print("  3. 试运行冒烟 → 上线")


if __name__ == "__main__":
    main()
