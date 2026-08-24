#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性迁移/清理商机 extra_fields.customer_requirement_text。

迁移规则（幂等，默认 dry-run）：
- 仅处理 status != deleted 且 extra_fields 里有非空 customer_requirement_text 的商机。
- 若该商机已有任意需求版本（draft/current/archived）的 requirement_text 非空，跳过（不覆盖）。
- 否则若已有草稿且 requirement_text 为空，把旧原文写进该草稿。
- 否则新建一条 draft：slots={}, version=当前最大 version+1（无则 1）。

清理规则（--clean-legacy，幂等）：
- 仅处理 status != deleted 且 extra_fields 里仍含 customer_requirement_text 的商机。
- 若旧值非空但该商机需求版本里没有非空 requirement_text，跳过（防止丢失原文）。
- 否则删除 extra_fields.customer_requirement_text；extra_fields 删空后置 NULL。

用法（backend 目录）：
  ./.venv/Scripts/python.exe -X utf8 scripts/migrate_legacy_requirement_text.py                      # 迁移 dry-run
  ./.venv/Scripts/python.exe -X utf8 scripts/migrate_legacy_requirement_text.py --commit             # 迁移写库
  ./.venv/Scripts/python.exe -X utf8 scripts/migrate_legacy_requirement_text.py --clean-legacy        # 清理 dry-run
  ./.venv/Scripts/python.exe -X utf8 scripts/migrate_legacy_requirement_text.py --clean-legacy --commit  # 清理写库
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.models.base import Opportunity_SessionLocal
from app.models.opportunity import Opportunity
from app.models.flow import OpportunityRequirement


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _extra(opp):
    if not opp.extra_fields:
        return {}
    try:
        extra = json.loads(opp.extra_fields or '{}')
        return extra if isinstance(extra, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def migrate(session, commit):
    opps = session.query(Opportunity).filter(Opportunity.status != 'deleted').all()
    todo, skipped = [], 0
    for opp in opps:
        legacy = (_extra(opp).get('customer_requirement_text') or '').strip()
        if not legacy:
            continue
        rows = session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opp.opportunity_id
        ).order_by(OpportunityRequirement.version.desc()).all()
        if any((r.requirement_text or '').strip() for r in rows):
            skipped += 1
            continue
        todo.append((opp, legacy, rows))

    print(f'待迁移商机: {len(todo)}；已有需求原文、跳过: {skipped}')
    for opp, legacy, rows in todo:
        draft = next((r for r in rows if r.status == 'draft'), None)
        if draft and not (draft.requirement_text or '').strip():
            action = f'更新草稿 v{draft.version}'
            if commit:
                draft.requirement_text = legacy
        else:
            version = (rows[0].version + 1) if rows else 1
            action = f'新建草稿 v{version}'
            if commit:
                session.add(OpportunityRequirement(
                    opportunity_id=opp.opportunity_id,
                    version=version,
                    slots={},
                    requirement_text=legacy,
                    status='draft',
                    created_by='migration',
                    created_at=_now(),
                ))
        print(f'  {opp.opportunity_id}  {opp.customer_name or ""}  ->  {action}  | {legacy[:60]!r}')

    if commit and todo:
        session.commit()
        print('\n已写库。')
    elif not commit:
        print('\nDRY RUN：未写库。确认后加 --commit 执行。')


def clean(session, commit):
    opps = session.query(Opportunity).filter(Opportunity.status != 'deleted').all()
    todo, skipped = [], 0
    for opp in opps:
        extra = _extra(opp)
        if 'customer_requirement_text' not in extra:
            continue
        legacy = (extra.get('customer_requirement_text') or '').strip()
        if legacy:
            rows = session.query(OpportunityRequirement).filter(
                OpportunityRequirement.opportunity_id == opp.opportunity_id
            ).all()
            if not any((r.requirement_text or '').strip() for r in rows):
                skipped += 1
                continue
        todo.append((opp, extra, legacy))

    print(f'待清理商机: {len(todo)}；需求无原文、跳过: {skipped}')
    for opp, extra, legacy in todo:
        del extra['customer_requirement_text']
        if commit:
            opp.extra_fields = json.dumps(extra, ensure_ascii=False) if extra else None
        print(f'  {opp.opportunity_id}  {opp.customer_name or ""}  ->  删除旧字段  | {legacy[:60]!r}')

    if commit and todo:
        session.commit()
        print('\n已写库。')
    elif not commit:
        print('\nDRY RUN：未写库。确认后加 --commit 执行。')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--commit', action='store_true', help='实际写库(默认 dry-run)')
    ap.add_argument('--clean-legacy', action='store_true', help='清理 extra_fields.customer_requirement_text')
    args = ap.parse_args()

    session = Opportunity_SessionLocal()
    try:
        if args.clean_legacy:
            clean(session, args.commit)
        else:
            migrate(session, args.commit)
    finally:
        session.close()


if __name__ == '__main__':
    main()
