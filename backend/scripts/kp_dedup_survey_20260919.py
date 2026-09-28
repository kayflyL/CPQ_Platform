# -*- coding: utf-8 -*-
"""只读调查：KP 配件库重复候选（identity + 去噪模糊键）+ 价格簇 + bom_cases 引用 + specs 缺失。
2026-09-19 第二轮去重前哨探，不写库。用法: python -X utf8 scripts/kp_dedup_survey_20260919.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from _localdb import db_password

from app.repository.kp_repo import part_identity_key


def connect():
    return psycopg2.connect(host="localhost", dbname="cpq_platform",
                            user="postgres", password=db_password())


# ---------- 去噪：候选生成用（真差异词保留与否由价格簇裁决） ----------
NOISE = [
    r'（国产品牌）', r'\(含模块\)', r'含光模块', r'带光模块', r'含模块', r'含超级电容', r'含电容',
    r'超级电容', r'super[- ]?capacitor', r'supercap', r'cachevault', r'掉电保护', r'含电池',
    r'\+?\s*支架', r'for\s+nvme', r'for\s+sata\s+ssd', r'涡轮卡', r'涡轮', r'server\s+edition',
    r'network\s*card', r'adapter\s*card', r'网卡', r'读取密集型', r'读密集型', r'写密集型', r'混合型',
    r'企业级', r'raid\s*1', r'raid需求', r'dwpd\s*>=?\s*\d', r'dwpd\s*\*\s*\d', r'ocp\s*3?\.?0?',
    r'支持rdma', r'（raid1）', r'ib/roce可选', r'支持ib/roce', r'\(pcie半高\)', r'pcie半高',
]


def strip_noise(name: str) -> str:
    s = (name or '').lower()
    s = s.replace('‑', '-').replace('’', "'")
    s = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', s)          # 3 .84 → 3.84
    s = s.replace('nvme', 'nvme').replace('sdd', 'ssd').replace('nvme', 'nvme')
    s = re.sub(r'2\'5|2＂', '2.5', s)
    for pat in NOISE:
        s = re.sub(pat, ' ', s)
    s = re.sub(r'[\s,，+()（）\[\]/\\-]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def num_tokens(s: str):
    return sorted(re.findall(r'\d+(?:\.\d+)?[a-z]*', s))


def fuzzy_key(name: str, category: str, brand: str):
    s = strip_noise(name)
    cat = (category or '')
    if cat == 'NIC':
        speed = ''
        m = re.search(r'(200|100|50|40|25|10|1)\s*g', s)
        if m:
            speed = m.group(1) + 'g'
        if '千兆' in (name or ''):
            speed = '1g'
        ports = ''
        m = re.search(r'(双口|四口|单口|2\s*port|4\s*port|1\s*port|2口|4口)', (name or '').lower())
        if m:
            t = m.group(1)
            ports = {'双口': '2', '2port': '2', '2口': '2', '四口': '4', '4port': '4', '4口': '4',
                     '单口': '1', '1port': '1'}.get(re.sub(r'\s', '', t), '')
        chip = ''
        for c in ('cx7', 'cx6', 'cx5', 'cx4', 'x710', 'i350', 'e810', 'x550', 'x520'):
            if c in s:
                chip = c
                break
        medium = 'copper' if ('电口' in (name or '')) else ('fiber' if ('光口' in (name or '') or 'sfp' in s or '光' in (name or '')) else '')
        return f'{speed}|{ports}|{chip}|{medium}'
    if cat in ('Raid card', 'HBA'):
        m = re.search(r'(\d{4})\s*-?\s*(\d)\s*i', s)
        model = f'{m.group(1)}-{m.group(2)}i' if m else s
        cache = ''
        m2 = re.search(r'(\d)\s*g', s)
        if m2:
            cache = m2.group(1) + 'g'
        return f'{model}|{cache}'
    if cat == 'GPU':
        s2 = re.sub(r'\b(nvidia|amd|geforce|卡)\b', ' ', s)
        s2 = re.sub(r'rtx\s*pro', 'rtxpro', s2)
        toks = [t for t in s2.split() if re.search(r'\d', t)]
        return 'gpu|' + ' '.join(sorted(toks))
    if cat == 'CPU':
        vendor = 'amd' if 'amd' in s or 'epyc' in s else ('intel' if 'xeon' in s or 'intel' in s else ('zhaoxin' if 'kh' in s or '兆芯' in (name or '') else ''))
        m = re.search(r'(\d{4,5}[a-z]?)', s)
        model = m.group(1) if m else ''
        cores = ''
        mc = re.search(r'(\d+)\s*c\b', s)
        if mc:
            cores = mc.group(1) + 'c'
        return f'cpu|{vendor}|{model}|{cores}'
    # 其余（HDD/SSD、Memory、杂项）直接用去噪归一名
    return f'{cat}|{s}'


def main():
    conn = connect()
    cur = conn.cursor()

    # 表结构自省
    cur.execute("""select column_name from information_schema.columns
                   where table_schema='kp' and table_name='kp_price_history' order by ordinal_position""")
    price_cols = [r[0] for r in cur.fetchall()]
    print('kp_price_history columns:', price_cols)

    cur.execute("""select p.id, p.name, coalesce(p.brand,''), coalesce(p.oem_sku,''), c.name,
                          p.created_at::date
                   from kp.kp_parts p left join kp.kp_categories c on c.id=p.category_id
                   order by p.id""")
    parts = {}
    for pid, name, brand, sku, cat, created in cur.fetchall():
        parts[pid] = dict(id=pid, name=name, brand=brand, sku=sku, cat=cat or '', created=str(created))

    specs = defaultdict(dict)
    cur.execute("select part_id, spec_key, spec_value from kp.kp_part_specs")
    for pid, k, v in cur.fetchall():
        specs[pid][k] = v

    prices = defaultdict(list)
    cur.execute(f"select part_id, price, price_date, note from kp.kp_price_history "
                f"order by part_id, price_date")
    for pid, price, d, note in cur.fetchall():
        prices[pid].append((float(price), str(d), note or ''))

    # bom_cases 引用计数
    bom_refs = defaultdict(int)
    cur.execute("select case_key, kp_lines from rules.bom_cases where kp_lines is not null")
    for case_key, lines in cur.fetchall():
        try:
            for ln in (lines or []):
                pid = ln.get('part_id')
                if pid:
                    bom_refs[pid] += 1
        except Exception:
            pass

    cur.close(); conn.close()

    def price_summary(pid):
        ps = prices.get(pid, [])
        if not ps:
            return 'no-price'
        vals = [p[0] for p in ps]
        ds = sorted(p[1] for p in ps)
        ratio = (max(vals) / min(vals)) if min(vals) > 0 else 999
        return f'n={len(ps)} min={min(vals):.0f} max={max(vals):.0f} r={ratio:.2f} {ds[0]}~{ds[-1]}'

    def show_group(title, ids):
        ids = sorted(ids)
        vals = []
        for pid in ids:
            ps = prices.get(pid, [])
            vals += [p[0] for p in ps]
        ratio = (max(vals) / min(vals)) if vals and min(vals) > 0 else None
        hint = 'MERGE?' if (ratio and ratio < 1.3) else ('SPLIT?' if ratio else 'NOPRICE')
        print(f'\n[{title}] {hint} 组内价比={ratio:.2f}' if ratio else f'\n[{title}] {hint}')
        for pid in ids:
            p = parts[pid]
            refs = bom_refs.get(pid, 0)
            print(f"  {pid:>4} | {p['name'][:56]:<56} | sku={p['sku'] or '-':<14} | sp={len(specs.get(pid,{}))} | bom引={refs} | {price_summary(pid)}")

    print(f'\n配件总数={len(parts)} 价格史总行={sum(len(v) for v in prices.values())}')

    # A. identity 完全相同组
    idg = defaultdict(list)
    for pid, p in parts.items():
        idg[part_identity_key(p['name'], p['cat'], specs.get(pid))].append(pid)
    print('\n' + '=' * 110)
    print('A. identity 完全相同组')
    n = 0
    for key, ids in sorted(idg.items(), key=lambda kv: repr(kv[0])):
        if len(ids) > 1:
            n += 1
            show_group(str(key[:5]), ids)
    print(f'\n>>> identity 同键组: {n}')

    # B. 去噪模糊键组（排除已在 A 组的）
    fg = defaultdict(list)
    for pid, p in parts.items():
        fg[(p['cat'], fuzzy_key(p['name'], p['cat'], p['brand']))].append(pid)
    a_ids = {frozenset(ids) for ids in idg.values() if len(ids) > 1}
    print('\n' + '=' * 110)
    print('B. 去噪模糊键组（A 之外的增量）')
    n = 0
    for key, ids in sorted(fg.items()):
        if len(ids) > 1 and frozenset(ids) not in a_ids:
            n += 1
            show_group(f'{key[0]}:{key[1]}', ids)
    print(f'\n>>> 模糊增量组: {n}')

    # C. specs 缺失清单
    print('\n' + '=' * 110)
    print('C. specs 缺失件（0 条，或存储缺 5 维 / 内存缺关键维）')
    missing = []
    for pid, p in sorted(parts.items()):
        sp = specs.get(pid, {})
        cat = p['cat']
        need = None
        if cat == 'HDD/SSD':
            need = [k for k in ('Capacity', 'Type', 'Media', 'Form Factor') if k not in sp]
        elif cat == 'Memory':
            need = [k for k in ('Capacity', 'Type', 'Speed') if k not in sp]
        elif not sp:
            need = ['(all)']
        if need:
            missing.append((pid, p, need, len(prices.get(pid, []))))
    for pid, p, need, np_ in missing:
        print(f"  {pid:>4} | {p['cat']:<10} | {p['name'][:52]:<52} | 缺{need} | prices={np_}")
    print(f'\n>>> 缺 spec 件数: {len(missing)}')


if __name__ == '__main__':
    main()
