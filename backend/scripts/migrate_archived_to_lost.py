"""A2 — 策略中心：archived 商机历史数据 → opportunity_result='失标'。

用户定调：archived 大部分可视为失标，且"后期可改"。
本脚本把所有 archived 商机的 extra_fields.opportunity_result 标为"失标"
（已标过其他值的跳过，幂等）。active 商机不动（让用户自己判断标）。

默认 dry_run（只打印将改多少）；加 --apply 才真提交。可逆：再改 extra_fields.opportunity_result 即可。

用法（backend 目录）：
  python -X utf8 scripts/migrate_archived_to_lost.py          # dry_run
  python -X utf8 scripts/migrate_archived_to_lost.py --apply   # 真改
"""
import sys
import os
import json

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.models.base import Opportunity_SessionLocal
from app.models.opportunity import Opportunity


def main():
    apply = '--apply' in sys.argv
    s = Opportunity_SessionLocal()
    try:
        archs = s.query(Opportunity).filter(Opportunity.status == 'archived').all()
        total = len(archs)
        will_mark, already = 0, 0
        already_values = {}
        samples = []
        for opp in archs:
            extra = {}
            if opp.extra_fields:
                try:
                    extra = json.loads(opp.extra_fields)
                except (json.JSONDecodeError, TypeError):
                    extra = {}
            cur = extra.get('opportunity_result')
            if cur:  # 已标过，跳过（幂等，不覆盖）
                already += 1
                already_values[cur] = already_values.get(cur, 0) + 1
                continue
            extra['opportunity_result'] = '失标'
            opp.extra_fields = json.dumps(extra, ensure_ascii=False)
            will_mark += 1
            if len(samples) < 3:
                samples.append(opp.opportunity_id)

        tag = '[APPLY] ' if apply else '[DRY RUN] '
        print(f"{tag}archived 商机共 {total} 条")
        print(f"{tag}将标为失标：{will_mark} 条")
        print(f"{tag}已标（跳过）：{already} 条 {dict(already_values) if already_values else ''}".rstrip())
        if samples:
            print(f"{tag}样例 ID：{samples}")
        if apply:
            s.commit()
            print(f"{tag}已提交。可逆：改 opportunity.extra_fields.opportunity_result 即可。")
        else:
            print(f"{tag}未提交。加 --apply 真改。")
    finally:
        s.close()


if __name__ == '__main__':
    main()
