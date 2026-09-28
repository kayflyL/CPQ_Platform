"""Read-only fuzzy duplicate candidate analysis for KP parts.

Groups only near-duplicates within a category and only when the extracted
technical signature matches (capacity, speed, model, port count, media, etc).
No writes are made to the database.
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict

import psycopg2
from _localdb import db_password  # 2026-09-14 安全加固：密码不再硬编码

DSN = {
    "host": "localhost",
    "dbname": "cpq_platform",
    "user": "postgres",
    "password": db_password(),
}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = value.replace("\u2011", "-").replace("\u2010", "-")
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def first_num(value: str) -> str:
    m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return m.group(0) if m else ""


def fetch_parts(cur):
    cur.execute(
        """
        select p.id, p.category_id, c.name as category, p.name,
               coalesce(p.brand, '') as brand,
               coalesce(p.oem_sku, '') as oem_sku,
               coalesce(p.alt_sku, '') as alt_sku,
               (select count(*) from kp.kp_part_specs s where s.part_id = p.id) as spec_count,
               (select count(*) from kp.kp_price_history h where h.part_id = p.id) as price_count,
               coalesce((select string_agg(s.spec_key || '=' || left(s.spec_value, 40), '; ' order by s.sort_order)
                         from kp.kp_part_specs s where s.part_id = p.id), '') as specs
        from kp.kp_parts p
        left join kp.kp_categories c on c.id = p.category_id
        order by c.name, p.id
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------- CPU ----------------
def cpu_key(part):
    n = norm(part["name"])
    b = norm(part["brand"])
    name_wo_brand = re.sub(r"\b(amd|epyc|intel|xeon)\b", " ", n)
    if b == "amd" or "epyc" in n or "amd" in n:
        m = re.search(r"\b(7a23|9j14|[0-9]{4}[a-z0-9]?)\b", name_wo_brand)
        if m:
            return f"cpu|amd|{m.group(1)}"
    if b == "intel" or "xeon" in n:
        m = re.search(r"\b([0-9]{4,5}[a-z]?\+?)\b", name_wo_brand)
        if m:
            return f"cpu|intel|{m.group(1)}"
    if "kh" in n:
        m = re.search(r"\b(kh[0-9]{4,6})\b", n)
        core = re.search(r"\b([0-9]{2,3})\s*c\b", n)
        if m:
            return f"cpu|zhaoxin|{m.group(1)}|{core.group(1) if core else '?'}"
    return ""


# ---------------- GPU ----------------
GPU_BRAND_ALIASES = {
    "nvidia": "nvidia", "amd": "amd", "影驰": "影驰", "昆仑芯": "昆仑芯",
    "沐曦": "沐曦", "天数智芯": "天数智芯", "华为": "华为", "壁仞": "壁仞",
    "武桐树": "武桐树",
}


def normalize_gpu_brand(part):
    b = norm(part["brand"])
    n = norm(part["name"])
    for token, canon in GPU_BRAND_ALIASES.items():
        if token in b or token in n:
            return canon
    return b or "unknown"


def gpu_model_key(part):
    n = norm(part["name"])
    brand = normalize_gpu_brand(part)
    if brand == "nvidia":
        if "a800" in n:
            model = "a800"
        elif "h100" in n:
            model = "h100"
        elif "a100" in n:
            model = "a100"
        elif "l20" in n:
            model = "l20"
        elif "l40" in n:
            model = "l40"
        elif re.search(r"\bl4\b", n):
            model = "l4"
        elif re.search(r"pro\s*6000|pro6000", n):
            model = "rtx_pro_6000" if "6000d" not in n else "rtx_pro_6000d"
        elif "pro 5000" in n or "pro5000" in n:
            model = "rtx_pro_5000"
        elif "5000 ada" in n:
            model = "rtx_5000_ada"
        elif "6000 ada" in n:
            model = "rtx_6000_ada"
        elif "5090" in n:
            model = "rtx_5090"
        elif "4090d" in n or "4090 d" in n:
            model = "rtx_4090d"
        elif "4090" in n:
            model = "rtx_4090"
        elif "5080" in n:
            model = "rtx_5080"
        else:
            model = n
        return f"gpu|{brand}|{model}"
    if brand == "amd":
        if "w7900ds" in n or "w7900 ds" in n:
            model = "w7900ds"
        elif "w7900" in n:
            model = "w7900"
        elif "r9700" in n:
            model = "r9700"
        else:
            model = n
        return f"gpu|{brand}|{model}"
    if brand == "昆仑芯" and "p800" in n:
        return f"gpu|{brand}|p800"
    if brand in {"天数智芯", "unknown"}:
        if "c550" in n:
            return f"gpu|{brand}|c550"
        if "c500" in n:
            return f"gpu|{brand}|c500"
        if "150" in n and ("天垓" in n or "150s" in n):
            return f"gpu|{brand}|tianzhi_150"
        if "智铠100" in n or "智凯100" in n or "天数100" in n or "100duo" in n or "100 duo" in n:
            duo = "duo" if ("duo" in n or "duo" in part["name"].casefold()) else "base"
            return f"gpu|{brand}|zhikai100|{duo}"
    if brand == "沐曦":
        if "c550" in n:
            return f"gpu|{brand}|c550"
        if "c500" in n:
            return f"gpu|{brand}|c500"
    if brand == "壁仞" and "166c" in n:
        return f"gpu|{brand}|166c"
    if brand == "华为" and "atlas" in n:
        return f"gpu|{brand}|atlas300i"
    return f"gpu|{brand}|{n}"


# ---------------- NIC ----------------
def nic_signature(part):
    n = norm(part["name"])
    raw = unicodedata.normalize("NFKC", str(part["name"] or "")).casefold().replace("\u2011", "-").replace("\u2010", "-")
    speed = ""
    if "400g" in n or "ndr400" in n or "ndr 400" in n:
        speed = "400g"
    elif "200g" in n or "hdr" in n:
        speed = "200g"
    elif "25g" in n or "sfp28" in n:
        speed = "25g"
    elif "100g" in n:
        speed = "100g"
    elif "10g" in n or "10gbe" in n or "4x10" in n or "10 gb" in n or "10gbe" in raw or "4x10" in raw:
        speed = "10g"
    elif "16gfc" in n or "16g fc" in n or "fc hba" in n:
        speed = "16gfc"
    elif "1g" in n or "千兆" in n:
        speed = "1g"
    else:
        speed = ""

    if "mcx75310aas" in n or "mcx75310aas" in raw:
        model = "cx7"
    elif "cx7" in n:
        model = "cx7"
    elif "cx6" in n or "connectx 6" in n or "connectx‑6" in n or "connectx-6" in raw:
        model = "cx6"
    elif "cx5" in n:
        model = "cx5"
    elif "cx4" in n:
        model = "cx4"
    elif "xl710" in n or "x710" in n:
        model = "x710"
    elif "i350" in n:
        model = "i350"
    elif "e810" in n:
        model = "e810"
    elif "bf3" in n:
        model = "bf3"
    elif "fc hba" in n:
        model = "fc_hba"
    else:
        model = ""

    m_ports = re.search(r"(?:^|[\s,，])([124])\s*(?:光口|电口|端口|口|port)", n)
    if m_ports:
        ports = m_ports.group(1)
    elif "4口" in n or "四口" in n or "4port" in n or "4 port" in n or "quad" in n or "4x" in n:
        ports = "4"
    elif "2口" in n or "双口" in n or "2port" in n or "2 port" in n or "dual" in n:
        ports = "2"
    elif "1口" in n or "单口" in n or "1port" in n or "1 port" in n:
        ports = "1"
    else:
        ports = "?"

    form = "ocp" if "ocp" in n else ("pcie" if ("pcie" in n or "半高" in n or "全高" in n) else "")
    media = ""
    if any(t in n for t in ("光口", "光模块", "光卡", "sfp+", "sfp28", "optical", "含模块")):
        media = "光"
    elif any(t in n for t in ("电口", "rj45", "rj 45", "copper")):
        media = "电"
    return f"nic|{model or 'generic'}|{speed}|{ports}|{form}|{media}"


# ---------------- Storage ----------------
def storage_key(part):
    raw = unicodedata.normalize("NFKC", str(part["name"] or "")).casefold().replace("\u2011", "-").replace("\u2010", "-")
    n = norm(part["name"])
    cap_gb = ""
    m = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(tb|t|gb|g)\b", raw)
    if m:
        num = float(m.group(1))
        cap_gb = f"{num * 1000:.0f}" if m.group(2) in ("tb", "t") else f"{num:.0f}"
    media = "nvme" if "nvme" in n else ("sas" if "sas" in n else ("sata" if "sata" in n else ""))
    typ = "hdd" if "hdd" in n else ("ssd" if ("ssd" in n or "sdd" in n or media == "nvme") else "")
    if typ == "hdd" and not media:
        media = "sata"
    if not typ and media == "sata" and cap_gb:
        try:
            if float(cap_gb) <= 8000:
                typ = "ssd"
        except ValueError:
            pass
    form = ""
    if "u 2" in n or "u.2" in part["name"].casefold():
        form = "u2"
    elif "m 2" in n or "m.2" in part["name"].casefold():
        form = "m2"
    elif "2 5" in n or "2.5" in part["name"].casefold():
        form = "2.5"
    rpm = ""
    if "15k" in n or "15 k" in n:
        rpm = "15k"
    elif "10k" in n or "10 k" in n:
        rpm = "10k"
    elif "7 2k" in n or "7.2k" in part["name"].casefold():
        rpm = "7.2k"
    gen = ""
    if "gen5" in n:
        gen = "gen5"
    elif "gen4" in n:
        gen = "gen4"
    return f"storage|{cap_gb}|{media}|{typ}|{form}|{rpm}|{gen}"


# ---------------- Memory ----------------
def memory_key(part):
    n = norm(part["name"])
    cap = ""
    m = re.search(r"\b(16|32|48|64)\s*(?:gb|g)\b", n)
    if m:
        cap = m.group(1)
    ddr = "ddr5" if "ddr5" in n else ("ddr4" if "ddr4" in n else "")
    speed = ""
    ms = re.search(r"\b(3200|4800|5600|6400)", n)
    if ms:
        speed = ms.group(1)
    typ = "rdimm" if "rdimm" in n else ""
    rank = "single_rank" if "single rank" in n else ""
    # RDIMM/ECC/rank are treated as review-level qualifiers, not part of the merge key.
    return f"memory|{cap}|{ddr}|{speed}"


# ---------------- RAID/HBA ----------------
def raid_hba_key(part):
    n = norm(part["name"])
    m = re.search(r"\b(\d{4})\s*[- ]?\s*(\d+)\s*i\b", n)
    model = f"{m.group(1)}-{m.group(2)}i" if m else ""
    if not model:
        m2 = re.search(r"\b(\d{4})\s*[- ]?\s*(\d+)\s*i\b", n)
        model = f"{m2.group(1)}-{m2.group(2)}i" if m2 else ""
    if not model and "fc hba" in n:
        model = "fc_hba"
    cache = "base"
    if re.search(r"[≥>]?\s*4\s*g", n):
        cache = "4g"
    elif re.search(r"[≥>]?\s*2\s*g", n):
        cache = "2g"
    elif re.search(r"[≥>]?\s*1\s*g", n):
        cache = "1g"
    return f"raidhba|{model}|{cache}" if model else ""


KEY_DEFS = [
    ("CPU-型号", {"CPU"}, cpu_key),
    ("GPU-型号", {"GPU"}, gpu_model_key),
    ("NIC-规格", {"NIC"}, nic_signature),
    ("HDD/SSD-规格", {"HDD/SSD"}, storage_key),
    ("Memory-规格", {"Memory"}, memory_key),
    ("RAID/HBA-型号", {"Raid card", "HBA"}, raid_hba_key),
]


def group_parts(parts, categories, key_func):
    groups = defaultdict(list)
    for p in parts:
        if p["category"] not in categories:
            continue
        key = key_func(p)
        if key:
            groups[key].append(p)
    return groups


def keep_score(p):
    return (p["spec_count"] * 3 + p["price_count"] * 2 + (1 if p["brand"] else 0) +
            (1 if p["oem_sku"] else 0) + (1 if p["alt_sku"] else 0), -p["id"])


def choose_keep(group):
    return max(group, key=keep_score)


def group_note(dimension, group):
    cats = sorted({p["category"] for p in group})
    if len(cats) > 1:
        return "跨分类: " + ",".join(cats)
    if dimension == "GPU-型号":
        caps = sorted({m.group(1) for p in group if (m := re.search(r"(\d{2,3})\s*g", norm(p["name"])))})
        if len(caps) > 1:
            return "容量不同: " + ",".join(caps)
        if not caps:
            return "容量未标注"
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="backend/fuzzy_duplicate_candidates_20260913.csv")
    args = parser.parse_args()

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    try:
        parts = fetch_parts(cur)
    finally:
        cur.close()
        conn.close()

    candidates = []
    seen = set()
    for label, categories, key_func in KEY_DEFS:
        for key, group in group_parts(parts, categories, key_func).items():
            if len(group) < 2:
                continue
            ids = tuple(sorted(p["id"] for p in group))
            if ids in seen:
                continue
            seen.add(ids)
            keep = choose_keep(group)
            candidates.append({
                "dimension": label,
                "key": key,
                "group": sorted(group, key=lambda p: p["id"]),
                "keep_id": keep["id"],
                "note": group_note(label, group),
            })

    fc_group = [p for p in parts if p["category"] in {"NIC", "HBA"} and "fc hba" in norm(p["name"])]
    if len(fc_group) >= 2:
        ids = tuple(sorted(p["id"] for p in fc_group))
        if ids not in seen:
            seen.add(ids)
            keep = choose_keep(fc_group)
            candidates.append({
                "dimension": "跨分类-FC HBA",
                "key": "fc_hba|16gfc|2port",
                "group": sorted(fc_group, key=lambda p: p["id"]),
                "keep_id": keep["id"],
                "note": "跨分类: NIC,HBA",
            })

    candidates.sort(key=lambda c: (c["dimension"], min(p["id"] for p in c["group"])))

    print(f"候选组数: {len(candidates)}，涉及配件: {sum(len(c['group']) for c in candidates)} 条")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["dimension", "key", "part_id", "category", "brand", "name",
                        "spec_count", "price_count", "specs", "suggested_keep", "note"])
            for c in candidates:
                for p in c["group"]:
                    w.writerow([c["dimension"], c["key"], p["id"], p["category"], p["brand"],
                                p["name"], p["spec_count"], p["price_count"], p["specs"],
                                "YES" if p["id"] == c["keep_id"] else "", c["note"]])
        print("CSV:", args.out)

    for c in candidates:
        print("=" * 96)
        print(f"[{c['dimension']}] key={c['key']}  keep={c['keep_id']}  {c['note']}")
        for p in c["group"]:
            mark = " *" if p["id"] == c["keep_id"] else "  "
            print(f"{mark} {p['id']:>4} | {p['brand'] or '-':<10} | {p['name']:<48} | s={p['spec_count']} p={p['price_count']}")


if __name__ == "__main__":
    raise SystemExit(main())
