# -*- coding: utf-8 -*-
"""KP 配件库 spec 补齐（2026-09-19，合并后第二轮）。
19 件：name 铁证 + 惯例默认(NVMe→U.2/HDD→3.5"/SATA·SAS SSD→2.5") + 联网核实参数(CPU×3/昆仑芯)。
逐 key 补缺不覆盖手填；348 修复违反词表脏值；418 修 name 笔误；415 归类 Raid card。
默认 dry-run，--commit 写库。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from _localdb import db_password

BACKUP = Path(__file__).resolve().parents[1] / 'tmp_kp_spec_backfill_backup_20260919.json'

# part_id → {name修正(可选), category名(可选), specs补缺}
PLAN = {
    322: {'specs': {'Type': 'SATA', 'Form Factor': '2.5"'}},
    333: {'specs': {'Form Factor': '3.5"'}},
    338: {'specs': {'Form Factor': '2.5"'}},
    339: {'specs': {'Form Factor': '3.5"'}},
    # 348: Media='SAS'/Type='HDD' 是词表错位（Media∈SSD/HDD, Type∈NVMe/SATA/SAS），按 name 铁证正过来
    348: {'specs': {'Form Factor': '3.5"', 'Media': 'HDD', 'Type': 'SAS'}},
    349: {'specs': {'Form Factor': '3.5"'}},
    350: {'specs': {'Form Factor': 'U.2'}},
    353: {'specs': {'Form Factor': 'U.2'}},
    387: {'specs': {'Form Factor': '2.5"'}},
    401: {'specs': {'Form Factor': '2.5"'}},
    413: {'specs': {'Capacity': '2 TB', 'Type': 'NVMe', 'Media': 'SSD', 'Form Factor': 'M.2'}},
    415: {'category': 'Raid card',
          'specs': {'Type': 'RAID', 'Cache': '4 GB', 'Ports': '8', '电容': '有'}},
    416: {'specs': {'Link Speed': '100G', 'Ports': '1', '接口': '光口'}},
    417: {'specs': {'Capacity': '96 GB', 'Architecture': 'XPU-P',
                    'Interface': 'PCIe 4.0', 'Memory Bandwidth': '2.4 TB/s'}},
    418: {'name': 'AMD EPYC 9455', 'specs': {'Cores': '48', 'tdp': '300'}},
    419: {'specs': {'Cores': '48', 'tdp': '330'}},
    420: {'specs': {'Cores': '32', 'tdp': '225'}},
    421: {'specs': {'Capacity': '64 GB', 'Type': 'DDR5', 'Speed': '6400 MT/s'}},
    426: {'specs': {'Link Speed': '200G', 'Ports': '1', '接口': '光口'}},
}


def main():
    commit = '--commit' in sys.argv
    conn = psycopg2.connect(host="localhost", dbname="cpq_platform",
                            user="postgres", password=db_password())
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("select id, name, category_id from kp.kp_parts")
    parts = {r[0]: r for r in cur.fetchall()}
    missing = set(PLAN) - set(parts)
    assert not missing, f'件不存在: {missing}'

    cur.execute("select id, name from kp.kp_categories")
    cats = {name: cid for cid, name in cur.fetchall()}

    specs = {}
    cur.execute("select part_id, spec_key, spec_value from kp.kp_part_specs")
    for pid, k, v in cur.fetchall():
        specs.setdefault(pid, {})[k] = v

    backup = {'parts': {}, 'categories': {}}
    for pid, plan in PLAN.items():
        backup['parts'][str(pid)] = {'name': parts[pid][1], 'category_id': parts[pid][2],
                                     'specs': specs.get(pid, {})}
    backup['categories'] = {name: cid for name, cid in cats.items()}
    BACKUP.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'备份 → {BACKUP}')

    try:
        for pid, plan in PLAN.items():
            name, cat_id = parts[pid][1], parts[pid][2]
            if plan.get('name') and plan['name'] != name:
                print(f'{pid} name: {name!r} -> {plan["name"]!r}')
                if commit:
                    cur.execute("update kp.kp_parts set name=%s, updated_at=now() where id=%s", (plan['name'], pid))
            if plan.get('category'):
                tgt = cats.get(plan['category'])
                assert tgt, f'目标分类不存在: {plan["category"]}'
                cur.execute("select count(*) from kp.kp_parts where category_id=%s and id<>%s", (cat_id, pid))
                others = cur.fetchone()[0]
                print(f'{pid} category: {cat_id} -> {tgt} ({plan["category"]})，原分类其余 {others} 件')
                if commit:
                    cur.execute("update kp.kp_parts set category_id=%s, updated_at=now() where id=%s", (tgt, pid))
                    if others == 0:
                        cur.execute("delete from kp.kp_categories where id=%s", (cat_id,))
                        print(f'  空分类 {cat_id} 已删除')
            have = set(specs.get(pid, {}).keys())
            for k, v in plan.get('specs', {}).items():
                tag = 'fill' if k not in have else ('fix' if specs[pid][k] != v else 'keep')
                if tag in ('fill', 'fix'):
                    print(f'  {pid} spec {k}: {specs.get(pid, {}).get(k)!r} -> {v!r} ({tag})')
                    if commit:
                        if tag == 'fill':
                            cur.execute("insert into kp.kp_part_specs (part_id, spec_key, spec_value) values (%s,%s,%s)", (pid, k, v))
                        else:
                            cur.execute("update kp.kp_part_specs set spec_value=%s where part_id=%s and spec_key=%s", (v, pid, k))
        if not commit:
            print('\n[dry-run] 未写库。加 --commit 执行。')
            return

        # 写后校验：五维/内存关键维零缺口
        cur.execute("""select p.id, c.name, coalesce(jsonb_object_agg(s.spec_key, s.spec_value) filter (where s.spec_key is not null), '{}'::jsonb)
                       from kp.kp_parts p
                       left join kp.kp_categories c on c.id=p.category_id
                       left join kp.kp_part_specs s on s.part_id=p.id
                       group by p.id, c.name""")
        bad = []
        for pid, cat, sp in cur.fetchall():
            need = None
            if cat == 'HDD/SSD':
                need = [k for k in ('Capacity', 'Type', 'Media', 'Form Factor') if k not in sp]
            elif cat == 'Memory':
                need = [k for k in ('Capacity', 'Type', 'Speed') if k not in sp]
            if need:
                bad.append((pid, cat, need))
        assert not bad, f'仍有缺口: {bad}'
        conn.commit()
        print('已提交 ✓  存储/内存关键维零缺口')
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
