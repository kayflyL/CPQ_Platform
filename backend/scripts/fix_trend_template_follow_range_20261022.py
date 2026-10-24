# -*- coding: utf-8 -*-
"""商机趋势报告模板解钉 days=183（2026-10-22，一次性幂等迁移）。

背景：目标层数据范围已支持 mode=auto 跟随用户输入（data_range_follow），报告
全区块应统一吃同一个窗口。platform_monthly / chassis_dist 两块还显式钉着
days=183（半年时代的固定口径），窗口改成"今年/自定义"时会和封面、KPI、大脑
正文打架（2026-10-22 实测：同一份报告 03 章两张某 месяц表、窗口各不同）。
本脚本把这两块的 params.days 清空（区块留空=跟随报告数据范围）。

幂等：两块都已无 params.days 即零改动。
运行：cd backend && python -X utf8 scripts/fix_trend_template_follow_range_20261022.py [--apply]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.artifact_template_repo import ArtifactTemplateRepo  # noqa: E402

TEMPLATE_KEY = "weekly_opportunity_report"
UNPIN_ASSETS = {"cockpit.platform_monthly", "cockpit.chassis_dist"}
OPERATOR = "fix_trend_template_follow_range_20261022"


def main() -> int:
    repo = ArtifactTemplateRepo()
    try:
        tpl = repo.get_by_key(TEMPLATE_KEY)
        if not tpl:
            print(f"FAIL: 模板 {TEMPLATE_KEY} 不存在")
            return 1
        blocks = tpl.get("blocks") or []
        changed = False
        new_blocks: list = []
        for b in blocks:
            if (isinstance(b, dict) and b.get("asset") in UNPIN_ASSETS
                    and isinstance(b.get("params"), dict) and "days" in b["params"]):
                params = {k: v for k, v in b["params"].items() if k != "days"}
                b = {**b, "params": params}
                changed = True
                print(f"解钉 {b.get('asset')}: days 已移除（跟随报告数据范围）")
            new_blocks.append(b)
        if not changed:
            print("模板已解钉（幂等通过，零改动）")
            return 0
        print("blocks 变更预览：")
        for b in new_blocks:
            if isinstance(b, dict) and b.get("asset") in UNPIN_ASSETS:
                print(" ", b.get("asset"), "params =", json.dumps(b.get("params"), ensure_ascii=False))
        if "--apply" not in sys.argv:
            print("（dry-run，未写库；加 --apply 执行）")
            return 0
        repo.update(tpl["id"], {"blocks": new_blocks}, operator=OPERATOR)
        print(f"模板 {TEMPLATE_KEY} 更新完成")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
