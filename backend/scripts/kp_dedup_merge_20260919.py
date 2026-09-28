# -*- coding: utf-8 -*-
"""KP 配件库第二轮去重合并（2026-09-19）。
38 组合并，102 个 alias 并入 canonical：spec 逐 key 补缺(脏值归一后) + 价格史并 canonical
(同日期同币种撞车保 canonical) + bom_cases.kp_lines 引用改指 + compat/related 搬运 + 删 alias。
默认 dry-run，--commit 才写库。备份 JSON 落 backend/tmp_kp_merge_backup_20260919.json。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from _localdb import db_password

from app.repository.kp_repo import part_identity_key

# canonical ← [aliases]（2026-09-19 逐组定夺，判据：同规格 + 最新价比<1.3；时间漂移按同件处理）
GROUPS = {
    1: [414, 422],
    56: [341, 412, 423, 429],
    59: [430],
    329: [388, 304],
    103: [428],
    210: [297, 265],
    268: [277, 311, 378, 386],
    115: [234],
    356: [291, 335, 380],
    254: [274],
    157: [427],
    280: [237, 332],
    175: [184],
    4: [362],
    355: [5, 279, 377],
    276: [327],
    13: [7, 369, 391, 406],
    361: [15, 425],
    23: [26, 275, 281, 321, 344, 411],
    28: [213, 317, 360, 358, 366, 395],
    309: [290, 305],
    44: [43, 41, 246, 302, 313, 367, 381, 396, 408, 46],
    136: [324, 410, 137, 192, 389],
    138: [139, 140, 248, 273, 330, 346, 394],
    143: [289, 294],
    145: [148, 146, 147, 236, 245, 295, 300, 399],
    132: [134, 135, 334, 351],
    230: [144, 314],
    359: [424],
    384: [119],
    87: [206, 286, 328],
    88: [393, 337],
    326: [63],
    340: [18],
    80: [363, 269],
    91: [345],
    93: [379],
}

# alias spec 常见脏值（Media/Type 填反、DIMM Type/Type 填反、接口塞了芯片型号）——补缺前先归一
_DISK_MEDIA = {'NVMe', 'SATA', 'SAS'}
_DISK_TYPE = {'SSD', 'HDD'}
_MEM_GEN = {'DDR3', 'DDR4', 'DDR5', 'DDR6', 'LPDDR4', 'LPDDR5', 'LPDDR5X'}
_MEM_DIMM = {'RDIMM', 'LRDIMM', 'UDIMM', 'SODIMM', 'DIMM'}
_CHIP_WORDS = {'CX4', 'CX5', 'CX6', 'CX7', 'I350', 'X710', 'X722', 'E810', 'X540', 'X550', 'X520'}


def norm_alias_spec(sp: dict) -> dict:
    sp = dict(sp)
    m, t = sp.get('Media'), sp.get('Type')
    if m in _DISK_MEDIA and t in _DISK_TYPE:
        sp['Media'], sp['Type'] = t, m
    dt, t2 = sp.get('DIMM Type'), sp.get('Type')
    if dt in _MEM_GEN and t2 in _MEM_DIMM:
        sp['DIMM Type'], sp['Type'] = t2, dt
    if sp.get('接口') in _CHIP_WORDS:
        sp.pop('接口')
    return sp


def main():
    commit = '--commit' in sys.argv
    backup_path = Path(__file__).resolve().parents[1] / 'tmp_kp_merge_backup_20260919.json'

    conn = psycopg2.connect(host="localhost", dbname="cpq_platform",
                            user="postgres", password=db_password())
    conn.autocommit = False
    cur = conn.cursor()

    alias2can = {}
    for can, aliases in GROUPS.items():
        for a in aliases:
            assert a not in alias2can, f'{a} 重复出现'
            alias2can[a] = can
    all_ids = set(alias2can) | set(GROUPS)

    # ---------- 读全部相关表 ----------
    cur.execute("select id, name, category_id, coalesce(oem_sku,''), coalesce(brand,''), coalesce(applicable::text,'') from kp.kp_parts")
    part_rows = cur.fetchall()
    parts = {r[0]: r for r in part_rows}
    missing = all_ids - set(parts)
    assert not missing, f'这些 id 不在库里: {missing}'

    specs = defaultdict(dict)
    cur.execute("select id, part_id, spec_key, spec_value, sort_order from kp.kp_part_specs")
    spec_rows = cur.fetchall()
    for _id, pid, k, v, so in spec_rows:
        specs[pid][k] = (v, so)

    price_rows = []
    cur.execute("select id, part_id, price, currency, price_date, coalesce(note,''), coalesce(source,''), created_at from kp.kp_price_history order by id")
    price_rows = cur.fetchall()

    cur.execute("select case_key, kp_lines from rules.bom_cases where kp_lines is not null")
    bom_rows = cur.fetchall()

    # 其它可能引用 part_id 的表（防遗漏）
    cur.execute("""select table_schema, table_name, column_name from information_schema.columns
                   where column_name in ('part_id','kp_part_id') and table_schema not in ('pg_catalog','information_schema')""")
    ref_cols = [r for r in cur.fetchall() if r[1] not in ('kp_parts', 'kp_part_specs', 'kp_price_history')]

    # compat / related
    compat_rows, related_rows = [], []
    for schema, table, col in ref_cols:
        if table in ('kp_part_compat', 'kp_part_related'):
            cur.execute(f'select * from {schema}.{table}')
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            (compat_rows if table == 'kp_part_compat' else related_rows).extend([(cols, r) for r in rows])

    print(f'parts={len(parts)} specs={len(spec_rows)} prices={len(price_rows)} bom_cases={len(bom_rows)} '
          f'compat={len(compat_rows)} related={len(related_rows)} 其他part_id引用列={ref_cols}')

    # ---------- 备份 ----------
    backup = {
        'created_at': str(cur.execute('select now()') and cur.fetchone()[0]),
        'groups': {str(k): v for k, v in GROUPS.items()},
        'kp_parts': [dict(zip(['id', 'name', 'category_id', 'oem_sku', 'brand', 'applicable'], r)) for r in part_rows if r[0] in all_ids],
        'kp_part_specs': [dict(zip(['id', 'part_id', 'spec_key', 'spec_value', 'sort_order'], r)) for r in spec_rows if r[1] in all_ids],
        'kp_price_history': [dict(zip(['id', 'part_id', 'price', 'currency', 'price_date', 'note', 'source', 'created_at'], r)) for r in price_rows if r[1] in all_ids],
        'bom_cases_kp_lines': [dict(zip(['case_key', 'kp_lines'], r)) for r in bom_rows],
    }
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(f'备份已写 {backup_path} ({backup_path.stat().st_size} bytes)')

    # ---------- dry-run 统计 ----------
    alias_ids = set(alias2can)
    n_price_moved = sum(1 for r in price_rows if r[1] in alias_ids)
    canon_dates = defaultdict(set)
    for _id, pid, price, cur_, d, *_ in price_rows:
        if pid in GROUPS:
            canon_dates[pid].add((str(d), cur_))
    n_price_dup_drop = 0
    for _id, pid, price, cur_, d, *_ in price_rows:
        if pid in alias2can and (str(d), cur_) in canon_dates[alias2can[pid]]:
            n_price_dup_drop += 1
    bom_hits = []
    for case_key, lines in bom_rows:
        for i, ln in enumerate(lines or []):
            if ln.get('part_id') in alias2can:
                bom_hits.append((case_key, i, ln['part_id'], alias2can[ln['part_id']]))
    print(f'计划：合并 {len(GROUPS)} 组 / 删 {len(alias_ids)} alias / 搬价格行 {n_price_moved} '
          f'(其中同日期撞车丢弃 {n_price_dup_drop}) / bom_cases 引用改指 {len(bom_hits)} 处')
    for case_key, i, old, new in bom_hits:
        print(f'  bom {case_key}[{i}]: {old} -> {new}')

    if not commit:
        print('\n[dry-run] 未写库。加 --commit 执行。')
        return

    # ---------- 事务执行 ----------
    try:
        # 1) spec 逐 key 补缺
        n_spec_fill = 0
        for can, aliases in GROUPS.items():
            have = set(specs.get(can, {}).keys())
            for a in aliases:
                for k, v in norm_alias_spec({k: v for k, (v, _so) in specs.get(a, {}).items()}).items():
                    if k not in have:
                        cur.execute("insert into kp.kp_part_specs (part_id, spec_key, spec_value) values (%s,%s,%s)",
                                    (can, k, v))
                        have.add(k)
                        n_spec_fill += 1
        print(f'spec 补缺 {n_spec_fill} 条')

        # 2) 价格史搬运 + 同日期撞车丢弃（保 canonical 已有行）
        for a, can in alias2can.items():
            cur.execute("""delete from kp.kp_price_history where part_id=%s
                           and (price_date, currency) in (select price_date, currency from kp.kp_price_history where part_id=%s)""",
                        (a, can))
            cur.execute("update kp.kp_price_history set part_id=%s where part_id=%s", (can, a))

        # 2b) canonical 内部同日期同价同币种精确重复去重（保留最小 id）
        cur.execute("""delete from kp.kp_price_history p
                       using kp.kp_price_history q
                       where p.part_id=q.part_id and p.price_date=q.price_date
                         and p.price=q.price and p.currency=q.currency and p.id>q.id""")
        print('价格史搬运+去重完成')

        # 3) bom_cases.kp_lines 改指
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
        print(f'bom_cases 改指 {n_bom} 个案例')

        # 4) compat / related 搬运
        for cols, row in compat_rows:
            d = dict(zip(cols, row))
            fa = [c for c in cols if c in ('part_id', 'kp_part_id')]
            fb = [c for c in cols if c in ('compat_part_id', 'related_part_id', 'target_part_id')]
            if not fb:
                continue
            src, dst = fa[0], fb[0]
            s, t = d.get(src), d.get(dst)
            ns = alias2can.get(s, s)
            nt = alias2can.get(t, t)
            if ns == nt:
                cur.execute(f'delete from kp.kp_part_compat where id=%s', (d['id'],))
            elif s != ns or t != nt:
                cur.execute('update kp.kp_part_compat set %s=%%s, %s=%%s where id=%%s' % (src, dst), (ns, nt, d['id']))
        print('compat 处理完成')

        # 5) 搜索索引：删 alias 行；bump canonical updated_at 让新鲜度对账触发重建（spec 变了要重嵌）
        cur.execute("delete from kp.kp_part_search_index where part_id = any(%s)", (sorted(alias_ids),))
        cur.execute("update kp.kp_parts set updated_at = now() where id = any(%s)", (sorted(GROUPS),))
        print('搜索索引 alias 行清理 + canonical updated_at 已 bump')

        # 6) 删 alias（specs/prices 已搬空，剩余级联清）
        cur.execute("delete from kp.kp_parts where id = any(%s)", (sorted(alias_ids),))
        print(f'删除 alias {cur.rowcount} 件')

        # ---------- 事务内校验 ----------
        cur.execute('select count(*) from kp.kp_parts')
        n_parts = cur.fetchone()[0]
        cur.execute('select count(*) from kp.kp_parts where id = any(%s)', (sorted(alias_ids),))
        assert cur.fetchone()[0] == 0, 'alias 未删干净'
        cur.execute('select count(*) from kp.kp_price_history')
        n_price_after = cur.fetchone()[0]
        # bom 引用完整性：不新增死引用（历史死引用如实报告）
        alive_ids = {p[0] for p in part_rows} - alias_ids
        cur.execute('select kp_lines from rules.bom_cases where kp_lines is not null')
        dead_after = set()
        for (lines,) in cur.fetchall():
            for ln in lines or []:
                if ln.get('part_id') and ln['part_id'] not in alive_ids:
                    dead_after.add(ln['part_id'])
        dead_before = set()
        for _ck, lines in bom_rows:
            for ln in lines or []:
                if ln.get('part_id') and ln['part_id'] not in alive_ids:
                    dead_before.add(ln['part_id'])
        assert dead_after <= dead_before, f'新增死引用: {dead_after - dead_before}'
        if dead_before:
            print(f'注意：历史遗留死引用 part_id={sorted(dead_before)}（本次不处理）')
        # 合并键唯一性：canonical 的 identity 不再与其他件撞
        cur.execute('select p.id, p.name, c.name from kp.kp_parts p left join kp.kp_categories c on c.id=p.category_id')
        all_parts = cur.fetchall()
        spec_map = defaultdict(dict)
        cur.execute('select part_id, spec_key, spec_value from kp.kp_part_specs')
        for pid, k, v in cur.fetchall():
            spec_map[pid][k] = v
        groups = defaultdict(list)
        for pid, name, cat in all_parts:
            groups[part_identity_key(name, cat, spec_map.get(pid))].append(pid)
        dup_groups = {k: v for k, v in groups.items() if len(v) > 1 and k[0] in ('HDD/SSD', 'Memory')}
        print(f'校验通过：parts {len(parts)}→{n_parts}，prices {len(price_rows)}→{n_price_after}；'
              f'HDD/Memory identity 残余重复组={len(dup_groups)} {list(dup_groups.values())[:3]}')

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
