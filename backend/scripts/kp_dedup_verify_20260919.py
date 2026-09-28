# -*- coding: utf-8 -*-
"""只读核验：打印候选合并组成员的完整价格史/最新价比/品类/spec差异，供最终定夺。不写库。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from _localdb import db_password

from app.repository.kp_repo import part_identity_key

GROUPS = {
    'G01 1.92T NVMe': [1, 414, 422, 316],
    'G02 3.84T NVMe': [56, 341, 412, 423, 429],
    'G03 3.84T SATA': [59, 430],
    'G04 8T SATA HDD': [329, 388, 304],
    'G05 960G NVMe': [103, 428],
    'G06 960G SATA': [210, 297, 265],
    'G07 32G DDR5-4800': [268, 277, 311, 378, 386],
    'G08 EPYC 9654': [115, 234],
    'G09 RTX5090 32G': [291, 335, 356, 380],
    'G10 AMD R9700': [254, 274],
    'G11 Pro6000D 84G': [157, 427],
    'G12 Pro6000 96G': [237, 280, 332],
    'G13 智铠100': [175, 184],
    'G14 1.92T SATA': [4, 362],
    'G15 480G SATA': [74, 77, 247],
    'G16 100G 2port': [5, 279, 355, 377],
    'G17 10G X710 2p': [276, 327],
    'G18 10G 2port+光': [13, 7, 369, 391, 406],
    'G19 10G 4port': [15, 361, 425],
    'G20 1G 2port I350': [23, 26, 275, 281, 321, 344, 411],
    'G21 1G 4port I350': [28, 213, 317, 360, 358, 366, 395],
    'G22 25G CX6': [290, 305, 309],
    'G23 25G 2port+光': [44, 43, 41, 246, 302, 313, 367, 381, 396, 408, 46],
    'G24 25G CX4': [267, 278],
    'G25 9361-8i 基础+1G': [136, 324, 410, 137, 192, 389],
    'G26 9361-8i 2G': [138, 139, 140, 248, 273, 330, 346, 394],
    'G27 9540-8i': [143, 289, 294],
    'G28 9560-8i 基础+4G': [145, 148, 146, 147, 236, 245, 295, 300, 399],
    'G29 9361-16i': [132, 134, 135, 334, 351],
    'G30 9560-16i': [230, 144, 314, 359, 424],
    'G31 FC HBA 16G': [384, 119],
    'G32 64G DDR5-4800': [87, 206, 286, 328],
    'G33 64G DDR5-5600': [88, 393, 337],
    'G34 32G DDR5-5600': [63, 326],
    'G35 16G DDR4-3200': [18, 340],
    'G36 4T SATA HDD': [80, 363, 269],
    'G37 6T SATA HDD': [91, 345],
    'G38 7.68T NVMe': [93, 379],
    'G39 600G SAS': [260, 348],
}


def main():
    conn = psycopg2.connect(host="localhost", dbname="cpq_platform",
                            user="postgres", password=db_password())
    cur = conn.cursor()
    cur.execute("""select p.id, p.name, coalesce(p.oem_sku,''), c.name
                   from kp.kp_parts p left join kp.kp_categories c on c.id=p.category_id""")
    parts = {pid: dict(name=n, sku=s, cat=c) for pid, n, s, c in cur.fetchall()}
    specs = {}
    cur.execute("select part_id, spec_key, spec_value from kp.kp_part_specs")
    sp = {}
    for pid, k, v in cur.fetchall():
        sp.setdefault(pid, {})[k] = v
    prices = {}
    cur.execute("select part_id, price, price_date, note from kp.kp_price_history order by price_date")
    for pid, price, d, note in cur.fetchall():
        prices.setdefault(pid, []).append((str(d), float(price), note or ''))
    cur.close(); conn.close()

    for title, ids in GROUPS.items():
        cats = {parts[i]['cat'] for i in ids}
        idents = {part_identity_key(parts[i]['name'], parts[i]['cat'], sp.get(i)) for i in ids}
        latest = {}
        for i in ids:
            if prices.get(i):
                latest[i] = sorted(prices[i])[-1]
        vals = [v[1] for v in latest.values()]
        lr = (max(vals) / min(vals)) if len(vals) > 1 and min(vals) > 0 else 1.0
        print(f"\n### {title} | 品类{'一致' if len(cats)==1 else cats} | identity{'一致' if len(idents)==1 else '不同'} | 最新价比={lr:.2f}")
        for i in ids:
            p = parts[i]
            hist = ' | '.join(f"{d[5:]}:{pr:.0f}" for d, pr, _ in sorted(prices.get(i, [])))
            lat = latest.get(i)
            print(f"  {i:>4} [{p['cat'][:9]:<9}] {p['name'][:44]:<44} spec={sp.get(i, {})}")
            print(f"       史: {hist or '无'}   最新={lat[1] if lat else '-'}@{lat[0] if lat else '-'}")


if __name__ == '__main__':
    main()
