"""只读分析：找出 KP 配件库中的疑似近似重复，供人工确认，不做任何写入。"""
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

UNIT_RE = re.compile(r"(?:gb|g|tb|t|mb|mhz|mt/s|mts|ghz|gbe|ge|gbit)", re.I)
SPACE_RE = re.compile(r"[\s,，+（）()\[\]{}:：;；_\/\-]+")


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = SPACE_RE.sub(" ", value)
    value = UNIT_RE.sub(" ", value)
    value = re.sub(r"\d+(?:\.\d+)?", " ", value)
    tokens = [t for t in value.split() if t not in STOPWORDS]
    return " ".join(tokens)


STOPWORDS = {
    "涡轮", "涡轮卡", "显卡", "网卡", "network", "card", "企业级", "国产品牌", "国产",
    "含模块", "光模块", "多模光模块", "单模光模块", "不含", "含", "带", "超级电容", "超级",
    "电容", "掉电保护", "模块", "cache", "缓存", "电池", "bbu", "supercap", "cachevault",
    "for", "sata", "nvme", "ssd", "hdd", "rdimm", "ecc", "pcie", "pci", "半高", "全高",
    "low", "profile", "ocp", "ocp3", "server", "edition", "duo", "单卡", "支持", "可选",
    "及", "and", "with", "support", "ib", "roce", "optical", "copper", "电口", "光口",
    "双口", "四口", "单口", "二口", "端口", "port", "ports", "adapter", "en",
}


def extract_raid_model(name: str) -> str:
    m = re.search(r"(\d{4})\s*[- ]?\s*(\d+)\s*i", norm(name))
    if m:
        return f"{m.group(1)}-{m.group(2)}i"
    return ""


def extract_cpu_model(name: str, brand: str) -> str:
    n = norm(name)
    if "epyc" in n:
        m = re.search(r"(?:epyc\s+)?(?:embedded\s+)?([a-z0-9]+\d{3,4}[a-z0-9]*)", n)
        if m:
            return m.group(1)
    if "xeon" in n or brand == "intel":
        m = re.search(r"xeon\s+(?:gold\s+|silver\s+|platinum\s+)?([a-z0-9]+\d{3,4}[a-z0-9]*)", n)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4,5}[a-z]?)", n)
        if m:
            return m.group(1)
    m = re.search(r"([a-z]*\d{3,5}[a-z0-9]*)", n)
    return m.group(1) if m else n


def extract_gpu_model(name: str) -> str:
    n = norm(name)
    # 去掉品牌词，保留型号主干。
    for brand in ["nvidia", "amd", "geforce", "rtx", "pro", "mellanox", "华为", "天数智芯", "沐曦", "壁仞", "昆仑芯", "智铠", "智凯", "影驰", "燧原", "武桐树", "昇腾"]:
        n = re.sub(rf"{re.escape(brand)}", " ", n)
    return " ".join(n.split())


def extract_memory_spec(name: str) -> str:
    n = norm(name)
    cap = re.search(r"(\d+(?:\.\d+)?)", n)
    speed = re.search(r"(\d{4,5})", n)
    ddr = "ddr5" if "ddr5" in n else ("ddr4" if "ddr4" in n else "")
    typ = "rdimm" if "rdimm" in n else ""
    return f"{cap.group(1) if cap else ''}|{ddr}|{speed.group(1) if speed else ''}|{typ}"


def extract_storage_spec(name: str) -> str:
    n = norm(name)
    cap = re.search(r"(\d+(?:\.\d+)?)", n)
    media = "nvme" if "nvme" in n else ("sas" if "sas" in n else ("sata" if "sata" in n else ""))
    typ = "ssd" if ("ssd" in n or "sdd" in n) else ("hdd" if "hdd" in n else "")
    form = "u.2" if "u.2" in n else ("2.5" if "2.5" in n else ("m.2" if "m.2" in n else ""))
    return f"{cap.group(1) if cap else ''}|{media}|{typ}|{form}"


def extract_nic_spec(name: str) -> str:
    n = norm(name)
    speed = re.search(r"(\d+(?:\.\d+)?)", n)
    ports = "4" if ("四口" in name or "4port" in n) else ("2" if ("双口" in name or "2port" in n or "二口" in name) else "")
    model = ""
    for token in ["x710", "i350", "cx4", "cx5", "cx6", "cx7", "e810", "x520", "x550"]:
        if token in n:
            model = token
            break
    return f"{speed.group(1) if speed else ''}|{ports}|{model}"


def fetch_parts(cur) -> list[dict]:
    cur.execute(
        """
        select p.id, c.name as category, p.name, coalesce(p.brand, '') as brand,
               (select count(*) from kp.kp_part_specs s where s.part_id = p.id) as spec_count,
               (select count(*) from kp.kp_price_history h where h.part_id = p.id) as price_count
        from kp.kp_parts p
        left join kp.kp_categories c on c.id = p.category_id
        order by c.name, p.id
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def group_parts(parts: list[dict], key_func) -> list[dict]:
    groups = defaultdict(list)
    for p in parts:
        key = key_func(p)
        if key:
            groups[key].append(p)
    return groups


def main() -> int:
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

    candidates: list[dict] = []

    key_defs = {
        "GPU-型号": lambda p: (f"gpu|{norm(p['brand'])}|{extract_gpu_model(p['name'])}" if p["category"] == "GPU" else ""),
        "CPU-型号": lambda p: (f"cpu|{norm(p['brand'])}|{extract_cpu_model(p['name'], p['brand'])}" if p["category"] == "CPU" else ""),
        "RAID/HBA-型号": lambda p: (f"raid|{norm(p['brand'])}|{extract_raid_model(p['name'])}" if p["category"] in ("Raid card", "HBA") else ""),
        "内存-规格": lambda p: (f"memory|{extract_memory_spec(p['name'])}" if p["category"] == "Memory" else ""),
        "HDD/SSD-规格": lambda p: (f"storage|{extract_storage_spec(p['name'])}" if p["category"] == "HDD/SSD" else ""),
        "NIC-规格": lambda p: (f"nic|{extract_nic_spec(p['name'])}" if p["category"] == "NIC" else ""),
    }

    seen_sets: set[tuple[int, ...]] = set()
    for label, key_func in key_defs.items():
        for key, group in group_parts(parts, key_func).items():
            if len(group) < 2:
                continue
            ids = tuple(sorted(p["id"] for p in group))
            if ids in seen_sets:
                continue
            seen_sets.add(ids)
            candidates.append({
                "dimension": label,
                "key": key,
                "ids": ids,
                "group": group,
            })

    candidates.sort(key=lambda c: (c["dimension"], min(c["ids"])))

    print(f"共发现疑似近似重复组: {len(candidates)} 组，涉及配件 {sum(len(c['group']) for c in candidates)} 条")
    print("=" * 100)
    for c in candidates:
        print(f"[{c['dimension']}] key={c['key']}")
        for p in sorted(c["group"], key=lambda x: x["id"]):
            print(f"  {p['id']:>4} | {p['brand'] or '-':<12} | {p['name']:<52} | specs={p['spec_count']} prices={p['price_count']}")
        print("-" * 100)

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["dimension", "key", "part_id", "category", "brand", "name", "spec_count", "price_count"])
            for c in candidates:
                for p in sorted(c["group"], key=lambda x: x["id"]):
                    writer.writerow([c["dimension"], c["key"], p["id"], p["category"], p["brand"], p["name"], p["spec_count"], p["price_count"]])
        print(f"\n已写出: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
