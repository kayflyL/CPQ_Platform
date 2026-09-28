"""从 KP 配件名称提取品牌与常见规格，并写回 kp_parts / kp_part_specs。

仅处理名称中可稳定识别的字段；不确定的字段不写，避免伪造规格。
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import datetime

import psycopg2
from _localdb import db_password  # 2026-09-14 安全加固：密码不再硬编码


DSN = {
    "host": "localhost",
    "dbname": "cpq_platform",
    "user": "postgres",
    "password": db_password(),
}


BRAND_PATTERNS = [
    (r"mellanox|mallanox", "Mellanox"),
    (r"\bintel\b|英特尔", "Intel"),
    (r"\bamd\b", "AMD"),
    (r"\bnvidia\b", "NVIDIA"),
    (r"\blsi\b", "LSI"),
    (r"\bbroadcom\b", "Broadcom"),
    (r"\bsamsung\b|三星", "Samsung"),
    (r"\bsk\s*hynix\b|hynix", "SK hynix"),
    (r"\bmicron\b", "Micron"),
    (r"\bkioxia\b", "Kioxia"),
    (r"western\s*digital|\bwd\b", "Western Digital"),
    (r"\bseagate\b", "Seagate"),
    (r"\btoshiba\b", "Toshiba"),
    (r"\bkingston\b", "Kingston"),
    (r"\bcrucial\b", "Crucial"),
    (r"\bsupermicro\b", "Supermicro"),
    (r"\bgospower\b", "Gospower"),
    (r"华为", "华为"),
    (r"天数智芯|天数", "天数智芯"),
    (r"智铠|智凯", "天数智芯"),
    (r"昆仑芯", "昆仑芯"),
    (r"影驰", "影驰"),
    (r"(?:\brtx\b|geforce|\b5090\b)", "NVIDIA"),
    (r"\b(?:i350|x710|x520|x550|e810)\b", "Intel"),
    (r"\b(?:cx[4-7]|connectx)\b", "Mellanox"),
    (r"\b(?:9361|9364|9400|9440|9460|9540|9560|9580)\b", "LSI"),
    (r"\bwus\d+\b", "Western Digital"),
    (r"(?:atlas|昇腾)", "华为"),
    (r"燧原", "燧原"),
    (r"沐曦", "沐曦"),
    (r"壁仞", "壁仞"),
    (r"武桐树", "武桐树"),
    (r"兆芯", "兆芯"),
    (r"昇腾|华为", "华为"),
]


CHINESE_NUM = {"单": 1, "双": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def norm_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return value.casefold()


def extract_capacity(text: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(TB|T|GB|G)\b", norm_text(text), re.I)
    if not m:
        return None
    num, unit = m.groups()
    unit = unit.upper()
    if unit == "T":
        unit = "TB"
    elif unit == "G":
        unit = "GB"
    return f"{num} {unit}"


def extract_memory_speed(text: str) -> str | None:
    lower = norm_text(text)
    m = re.search(r"(\d{4,5})\s*(?:MT/?S|MTS|MHZ)", lower, re.I)
    if not m:
        # 例如 "32G 4800 DDR5"，名称里没有显式单位时，四位数通常就是速率。
        m = re.search(r"\b(\d{4})\b", lower)
    if not m:
        return None
    return f"{m.group(1)} MT/s"


def extract_link_speed(text: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:G(?:BE)?|GE?)(?![A-Za-z])", norm_text(text), re.I)
    if not m:
        return None
    return f"{m.group(1)}G"


def extract_ports(text: str) -> str | None:
    m = re.search(r"(\d+)\s*(?:光口|port|口|端口)", norm_text(text), re.I)
    if m:
        return str(int(m.group(1)))
    for word, num in CHINESE_NUM.items():
        if word in text and ("口" in text or "端口" in text or "port" in text):
            return str(num)
    return None


def infer_specs(category: str, name: str, brand: str) -> dict[str, str]:
    cat = norm_text(category)
    lower = norm_text(name)
    specs: dict[str, str] = {}

    # Raid/HBA 卡先判断，避免把 LSI 95xx 的 "4G cache" 误判成链路速率。
    is_raid_card = "raid" in cat or (
        "hba" in cat and re.search(r"\b(?:lsi|broadcom|9361|9560|9580|9460|9440|9360)\b", lower)
    )
    if is_raid_card:
        if "hba" in cat and "raid" not in cat:
            specs["Type"] = "HBA"
        else:
            specs["Type"] = "RAID"
        m = re.search(r"(\d+(?:\.\d+)?)\s*g(?:\s*(?:cache|缓存|含|超级|电池|掉电|cachevault)|$)", lower)
        if m:
            specs["Cache"] = f"{m.group(1)}G"
        m = re.search(r"(\d+)\s*i\b", lower)
        if m:
            specs["Ports"] = m.group(1)
        if "nvme" in lower:
            specs["Interface"] = "NVMe/SAS/SATA"
        elif "sata" in lower:
            specs["Interface"] = "SATA"
        elif "sas" in lower:
            specs["Interface"] = "SAS"

    elif "hdd/ssd" in cat or "ssd" in cat or "hdd" in cat or "nvme" in cat:
        cap = extract_capacity(name)
        if cap:
            specs["Capacity"] = cap
        if "nvme" in lower:
            specs["Media"] = "NVMe"
        elif "sas" in lower:
            specs["Media"] = "SAS"
        elif "sata" in lower:
            specs["Media"] = "SATA"
        if "ssd" in lower or "sdd" in lower:
            specs["Type"] = "SSD"
        elif "hdd" in lower or re.search(r"\b\d+(?:\.\d+)?\s*k\b", lower):
            specs["Type"] = "HDD"
        if "u.2" in lower:
            specs["Form Factor"] = "U.2"
        elif "2.5" in lower or "2.5寸" in lower:
            specs["Form Factor"] = "2.5 inch"
        m = re.search(r"(\d+(?:\.\d+)?)\s*k", lower)
        if m:
            specs["RPM"] = f"{m.group(1)}K"
        m = re.search(r"dwpd\s*>=\s*(\d+(?:\.\d+)?)", lower)
        if m:
            specs["DWPD"] = m.group(1)

    elif "memory" in cat or "内存" in cat:
        cap = extract_capacity(name)
        if cap:
            specs["Capacity"] = cap
        if "ddr5" in lower:
            specs["DIMM Type"] = "DDR5"
        elif "ddr4" in lower:
            specs["DIMM Type"] = "DDR4"
        speed = extract_memory_speed(name)
        if speed:
            specs["Speed"] = speed
        if "ecc" in lower:
            specs["ECC"] = "Yes"
        if "rdimm" in lower:
            specs["Type"] = "RDIMM"

    elif "nic" in cat or "网卡" in cat or "hba" in cat:
        speed = extract_link_speed(name)
        if not speed and "千兆" in name:
            speed = "1G"
        if not speed and "百兆" in name:
            speed = "100M"
        if speed:
            specs["Link Speed"] = speed
        ports = extract_ports(name)
        if ports:
            specs["Ports"] = ports
        if "ocp" in lower:
            specs["Form Factor"] = "OCP"
        elif "半高" in name:
            specs["Form Factor"] = "Low Profile"
        if "fc" in lower:
            specs["Interface"] = "FC"
        elif "光" in name or "sfp" in lower or "光纤" in name:
            specs["Interface"] = "Optical"
        elif "电口" in name or "copper" in lower:
            specs["Interface"] = "Copper"

    elif "gpu" in cat or "显卡" in cat:
        specs["Type"] = "GPU"
        cap = extract_capacity(name)
        if cap:
            specs["Capacity"] = cap
        if "涡轮" in name:
            specs["Cooling"] = "Blower"
        if "被动" in name:
            specs["Cooling"] = "Passive"

    elif "bridge" in cat:
        specs["Type"] = "Bridge"

    elif "nvswitch" in cat:
        specs["Type"] = "NVSwitch"

    elif "cpu" in cat or "处理器" in cat:
        specs["Type"] = "CPU"
        m = re.search(r"(\d+)\s*(?:cores?|c)(?![a-z])", lower)
        if m:
            specs["Cores"] = m.group(1)
        m = re.search(r"(\d+(?:\.\d+)?)\s*mb", lower)
        if m:
            specs["L3 Cache"] = f"{m.group(1)} MB"
        m = re.search(r"(?:boost|turbo)[^0-9]{0,8}(\d+(?:\.\d+)?)\s*g(?:hz)?", lower)
        if m:
            specs["Boost Clock"] = f"{m.group(1)} GHz"
        m = re.search(r"(\d+(?:\.\d+)?)\s*g(?:hz)?\b", lower)
        if m:
            specs["Base Clock"] = f"{m.group(1)} GHz"

    return specs

def backup_enrich(cur) -> None:
    """写库前为本次 enrichment 创建独立备份表。"""
    for backup_table, source_table in [
        ("kp.kp_parts_bak_enrich_20260912", "kp.kp_parts"),
        ("kp.kp_part_specs_bak_enrich_20260912", "kp.kp_part_specs"),
    ]:
        cur.execute(f"drop table if exists {backup_table}")
        cur.execute(f"create table {backup_table} as select * from {source_table}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(**DSN)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            select p.id, c.name as category, p.name as part_name, coalesce(p.brand, '') as brand
            from kp.kp_parts p
            left join kp.kp_categories c on c.id = p.category_id
            where coalesce(p.brand, '') = ''
            order by p.id
            """
        )
        brand_rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

        brand_updates = []
        for row in brand_rows:
            name = row["part_name"] or ""
            for pattern, brand in BRAND_PATTERNS:
                if re.search(pattern, name, re.I):
                    brand_updates.append((row["id"], name, brand))
                    break

        cur.execute(
            """
            select p.id, c.name as category, p.name as part_name, coalesce(p.brand, '') as brand
            from kp.kp_parts p
            left join kp.kp_categories c on c.id = p.category_id
            where not exists (select 1 from kp.kp_part_specs s where s.part_id = p.id)
            order by p.id
            """
        )
        spec_rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

        spec_updates = []
        brand_by_id = {pid: brand for pid, _name, brand in brand_updates}
        for row in spec_rows:
            brand = brand_by_id.get(row["id"], row["brand"])
            specs = infer_specs(row["category"] or "", row["part_name"] or "", brand)
            if specs:
                spec_updates.append((row["id"], row["part_name"] or "", specs))

        print(f"品牌可提取: {len(brand_updates)}")
        for pid, name, brand in brand_updates:
            print(f"  {pid}\t{brand}\t{name}")
        print(f"规格可推断: {len(spec_updates)}")
        for pid, name, specs in spec_updates:
            print(f"  {pid}\t{specs}\t{name}")

        if not args.apply:
            print("DRY-RUN，未写库。")
            conn.rollback()
            return 0

        backup_enrich(cur)
        print("已创建备份表: kp.kp_parts_bak_enrich_20260912 / kp.kp_part_specs_bak_enrich_20260912")

        for pid, _name, brand in brand_updates:
            cur.execute("update kp.kp_parts set brand = %s, updated_at = %s where id = %s", (brand, datetime.now(), pid))
        for pid, _name, specs in spec_updates:
            for key, value in specs.items():
                cur.execute(
                    """
                    insert into kp.kp_part_specs (part_id, spec_key, spec_value, sort_order)
                    values (%s, %s, %s, 0)
                    on conflict (part_id, spec_key) do update set spec_value = excluded.spec_value
                    """,
                    (pid, key, value),
                )
        conn.commit()
        print("已提交。")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
