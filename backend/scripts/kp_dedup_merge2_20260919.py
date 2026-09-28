# -*- coding: utf-8 -*-
"""KP 配件库去重补漏（2026-09-19 第二批）：匹配器同 token 集扫描发现的 7 组漏网重复。
356←[155,196] 5090涡轮卡 / 145←[415] / 74←[387] / 210←[338] / 400←[409,417] 昆仑芯P800
168←[179] 沐曦C500 / 398←[176,183,320,371] 智铠100DUO。默认 dry-run，--commit 写库。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from _localdb import db_password

GROUPS = {
    356: [155, 196],
    145: [415],
    74: [387],
    210: [338],
    400: [409, 417],
    168: [179],
    398: [176, 183, 320, 371],
}


def main():
    commit = '--commit' in sys.argv
    backup_path = Path(__file__).resolve().parents[1] / 'tmp_kp_merge_backup2_20260919.json'

    conn = psycopg2.connect(host="localhost", dbname="cpq_platform",
                            user="postgres", password=db_password())
    conn.autocommit = False
    cur = conn.cursor()

    alias2can = {a: c for c, aliases in GROUPS.items() for a in aliases}
    all_ids = set(alias2can) | set(GROUPS)

    cur.execute("select id, name, category_id, coalesce(oem_sku,''), coalesce(brand,''), coalesce(applicable::text,'') from kp.kp_parts")
    part_rows = cur.fetchall()
    parts = {r[0]: r for r in part_rows}
    missing = all_ids - set(parts)
    assert not missing, f'件不存在: {missing}'

    specs = defaultdict(dict)
    cur.execute("select id, part_id, spec_key, spec_value from kp.kp_part_specs")
    spec_rows = cur.fetchall()
    for _id, pid, k, v in spec_rows:
        specs[pid][k] = v

    cur.execute("select id, part_id, price, currency, price_date, coalesce(note,''), coalesce(source,''), created_at from kp.kp_price_history order by id")
    price_rows = cur.fetchall()
    cur.execute("select case_key, kp_lines from rules.bom_cases where kp_lines is not null")
    bom_rows = cur.fetchall()

    backup = {
        'groups': {str(k): v for k, v in GROUPS.items()},
        'kp_parts': [dict(zip(['id', 'name', 'category_id', 'oem_sku', 'brand', 'applicable'], r)) for r in part_rows if r[0] in all_ids],
        'kp_part_specs': [dict(zip(['id', 'part_id', 'spec_key', 'spec_value'], r)) for r in spec_rows if r[1] in all_ids],
        'kp_price_history': [dict(zip(['id', 'part_id', 'price', 'currency', 'price_date', 'note', 'source', 'created_at'], r)) for r in price_rows if r[1] in all_ids],
        'bom_cases_kp_lines': [dict(zip(['case_key', 'kp_lines'], r)) for r in bom_rows],
    }
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(f'备份 → {backup_path} ({backup_path.stat().st_size} bytes)')
    print(f'计划：合并 {len(GROUPS)} 组 / 删 {len(alias2can)} alias')

    if not commit:
        print('[dry-run] 未写库。加 --commit 执行。')
        return

    try:
        for can, aliases in GROUPS.items():
            have = set(specs.get(can, {}).keys())
            for a in aliases:
                for k, v in specs.get(a, {}).items():
                    if k not in have:
                        cur.execute("insert into kp.kp_part_specs (part_id, spec_key, spec_value) values (%s,%s,%s)", (can, k, v))
                        have.add(k)

        for a, can in alias2can.items():
            cur.execute("""delete from kp.kp_price_history where part_id=%s
                           and (price_date, currency) in (select price_date, currency from kp.kp_price_history where part_id=%s)""",
                        (a, can))
            cur.execute("update kp.kp_price_history set part_id=%s where part_id=%s", (can, a))
        cur.execute("""delete from kp.kp_price_history p
                       using kp.kp_price_history q
                       where p.part_id=q.part_id and p.price_date=q.price_date
                         and p.price=q.price and p.currency=q.currency and p.id>q.id""")

        n_bom = 0
        for case_key, lines in bom_rows:
            changed = False
            for ln in lines or []:
                pid = ln.get('part_id')
                if pid in alias2can:
                    ln['part_id'] = alias2can[pid]
                    changed = True
            if changed:
                cur.execute("update rules.bom_cases set kp_lines=%s where case_key=%s", (json.dumps(lines), case_key))
                n_bom += 1

        cur.execute("delete from kp.kp_part_search_index where part_id = any(%s)", (sorted(alias2can),))
        cur.execute("update kp.kp_parts set updated_at = now() where id = any(%s)", (sorted(GROUPS),))
        cur.execute("delete from kp.kp_parts where id = any(%s)", (sorted(alias2can),))
        print(f'价格史搬运+bom改指({n_bom}案例)+索引清理+删除 alias {cur.rowcount} 件')

        cur.execute('select count(*) from kp.kp_parts')
        n_parts = cur.fetchone()[0]
        cur.execute('select count(*) from kp.kp_price_history')
        n_price = cur.fetchone()[0]
        alive = {p[0] for p in part_rows} - set(alias2can)
        dead_before = {ln.get('part_id') for _ck, lines in bom_rows for ln in (lines or [])
                       if ln.get('part_id') and ln['part_id'] not in {p[0] for p in part_rows}}
        cur.execute('select kp_lines from rules.bom_cases where kp_lines is not null')
        for (lines,) in cur.fetchall():
            for ln in lines or []:
                pid = ln.get('part_id')
                assert not (pid and pid not in alive and pid not in dead_before), f"新死引用 {ln}"
        print(f'校验通过：parts→{n_parts} prices→{n_price}')
        conn.commit()
        print('已提交 ✓')
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
