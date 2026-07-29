#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""旧 strategies.selection 域规则 → compatibility_rule 迁移脚本（幂等 + dry_run）。

P1 已把选型配置重构为声明式兼容性规则引擎（rules.compatibility_rules 表）。旧的
rules.strategies 表里 domain='selection' 的规则（conflict/require/bom_spec/model_recommend）
不再有消费方（Workspace 已切 evaluateRules，validateSelection 仅作过渡兼容包装）。
本脚本把仍有价值的旧规则转换成 compatibility_rule 语义，统一到一张表。

用法：
  python -X utf8 scripts/migrate_selection_to_compatibility.py                 # dry_run（默认，只打印）
  python -X utf8 scripts/migrate_selection_to_compatibility.py --apply          # 实际写入
  python -X utf8 scripts/migrate_selection_to_compatibility.py --apply --archive # 写入 + 旧规则归档

转换映射：
  conflict {check:unique, where:{part_category}, by}        → exclude（同 by 字段不混搭）
  require  {if:{part_category, specs...}, need:{part_category, specs...}} → require（need 为数组则拆多条）
  bom_spec {required:[...]}                                  → 多条 require（机型必配）
  model_recommend {level, selling_points}                    → recommend（整机推荐，scope.series 限定）
幂等：按 name 去重，compatibility_rules 已有同名规则则跳过。
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.models.base import rules_engine
from app.repository.compatibility_rule_repo import CompatibilityRuleRepository


def _body(x):
    if x is None:
        return {}
    return json.loads(x) if isinstance(x, str) else x


def conv_conflict(body, scope):
    cat = (body.get('where') or {}).get('part_category', '')
    by = body.get('by', 'catalogue') or 'catalogue'
    desc = body.get('desc', '')
    return [({
        'when': {'field': f'kp.{cat}.qty', 'op': '>=', 'value': 2},
        'then': {'action': 'exclude', 'target': f'kp.{cat}', 'unique_field': by, 'desc': desc},
        'desc': desc,
    }, 'exclude')]


def conv_require(body, scope):
    iff = body.get('if') or {}
    need = body.get('need') or {}
    if_cat = iff.get('part_category', '')
    desc = body.get('desc', '')
    # WHEN 条件：if 的 specs.* → kp.<cat>.spec.<key>；无 specs 则 qty>=1
    conds = []
    for k, v in iff.items():
        if k.startswith('specs.'):
            sk = k[len('specs.'):]
            conds.append({'field': f'kp.{if_cat}.spec.{sk}',
                          'op': 'in' if isinstance(v, list) else '==', 'value': v})
    if not conds:
        conds.append({'field': f'kp.{if_cat}.qty', 'op': '>=', 'value': 1})
    when = conds[0] if len(conds) == 1 else {'all': conds}
    # THEN target：need.part_category 可能是单个或数组（数组拆多条）
    need_cats = need.get('part_category', '')
    if isinstance(need_cats, str):
        need_cats = [need_cats]
    need_spec = {k[len('specs.'):]: v for k, v in need.items() if k.startswith('specs.')}
    out = []
    for nc in need_cats:
        then = {'action': 'require', 'target': f'kp.{nc}', 'desc': desc}
        if need_spec:
            then['spec_constraint'] = need_spec
        out.append(({'when': when, 'then': then, 'desc': desc}, 'require'))
    return out


def conv_bom_spec(body, scope):
    series = (scope or {}).get('series', '')
    desc_base = body.get('desc', '')
    out = []
    for cat in body.get('required', []):
        when = {'field': 'config.series', 'op': '==', 'value': series} if series else {}
        then = {'action': 'require', 'target': f'kp.{cat}', 'desc': f'机型必配 {cat}'}
        out.append(({'when': when, 'then': then, 'desc': desc_base or then['desc']}, 'require'))
    return out


def conv_model_recommend(body, scope):
    series = (scope or {}).get('series', '')
    level = body.get('level', '')
    sp = body.get('selling_points', '')
    desc = f"整机推荐({level})：{sp}" if sp else f"整机推荐({level})"
    when = {'field': 'config.series', 'op': '==', 'value': series} if series else {}
    then = {'action': 'recommend', 'target': 'server_model', 'desc': desc}
    return [({'when': when, 'then': then, 'desc': desc}, 'recommend')]


CONV = {
    'conflict': conv_conflict,
    'require': conv_require,
    'bom_spec': conv_bom_spec,
    'model_recommend': conv_model_recommend,
}


def main():
    ap = argparse.ArgumentParser(description='迁移旧 selection 规则到 compatibility_rule')
    ap.add_argument('--apply', action='store_true', help='实际写入 compatibility_rules（默认 dry_run 只打印）')
    ap.add_argument('--archive', action='store_true', help='迁移后把旧 selection 规则 status 设为 archived（需配合 --apply）')
    args = ap.parse_args()

    with rules_engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, type, name, body, scope FROM rules.strategies "
            "WHERE domain='selection' AND status='active' ORDER BY id"
        )).all()

    repo = CompatibilityRuleRepository()
    existing = {r['name'] for r in repo.list()}

    created, skipped, unknown = 0, 0, 0
    archived_ids = []
    for rid, rtype, name, body_raw, scope_raw in rows:
        body = _body(body_raw)
        scope = _body(scope_raw)
        conv = CONV.get(rtype)
        if not conv:
            print(f"[跳过] id={rid} 「{name}」未知 type={rtype}，无转换规则")
            unknown += 1
            continue
        produced = conv(body, scope)
        archived_ids.append(rid)
        for cre_body, cre_type in produced:
            if name in existing:
                print(f"[去重] id={rid} 「{name}」({cre_type}) 已存在于 compatibility_rules，跳过")
                skipped += 1
                continue
            when_s = json.dumps(cre_body.get('when'), ensure_ascii=False)
            print(f"[{'写入' if args.apply else '预览'}] id={rid}→{cre_type} 「{name}」  when={when_s}  target={cre_body['then'].get('target')}")
            if args.apply:
                repo.create({
                    'domain': 'selection', 'type': cre_type, 'name': name,
                    'body': cre_body, 'status': 'active', 'description': cre_body.get('desc', ''),
                })
                existing.add(name)
            created += 1

    if args.apply and args.archive and archived_ids:
        with rules_engine.begin() as c:
            c.execute(text("UPDATE rules.strategies SET status='archived' WHERE id = ANY(:ids)"),
                      {'ids': archived_ids})
        print(f"\n已归档旧 selection 规则 {len(archived_ids)} 条（id={archived_ids}）")

    repo.close()
    print(f"\n完成：{'写入' if args.apply else '预览(dry_run)'} {created} 条 · 去重跳过 {skipped} 条 · 未知跳过 {unknown} 条")
    if not args.apply:
        print("确认无误后加 --apply 实际写入；再加 --archive 归档旧规则。")


if __name__ == '__main__':
    main()
