"""dry-run: 从 kp_parts.name 提取规格参数，不写库，仅预览。"""
import re
from sqlalchemy import create_engine, text

e = create_engine(
    "postgresql://postgres:961216@localhost:5432/cpq_platform?client_encoding=UTF8",
    connect_args={"options": "-c search_path=kp"},
)


def norm_cap(num: str, unit: str) -> str:
    n = float(num)
    n = int(n) if n == int(n) else n
    return f"{n}TB" if unit.upper() in ("T", "TB") else f"{n}GB"


def extract(cat: str, name: str) -> dict:
    s = {}
    n = name.strip()

    if cat == "Memory":
        m = re.search(r"(\d+(?:\.\d+)?)\s*([GT])B?(?!\w)", n)
        if m:
            s["Capacity"] = norm_cap(m.group(1), m.group(2))
        m = re.search(r"(DDR[345])", n, re.I)
        if m:
            s["Type"] = m.group(1).upper()
        m = re.search(r"(?<!\d)(\d{4})(?:\s*MT/?s|\s*MHz)?", n)
        if m:
            s["Speed"] = f"{m.group(1)} MT/s"

    elif cat == "HDD/SSD":
        m = re.search(r"(\d+(?:\.\d+)?)\s*([GT])B?(?!\w)", n)
        if m:
            s["Capacity"] = norm_cap(m.group(1), m.group(2))
        if re.search(r"NVME", n, re.I):
            s["Type"] = "NVMe"
        elif re.search(r"\bSAS\b", n):
            s["Type"] = "SAS"
        elif re.search(r"SATA", n, re.I):
            s["Type"] = "SATA"

    elif cat == "GPU":
        # 显存：1-3 位数字紧跟 G/GB，排除型号数字(4090/5090 等后面不接 G)
        m = re.search(r"(?<!\d)(\d{1,3})\s*GB?(?![0-9])", n)
        if m and int(m.group(1)) <= 200:
            s["Capacity"] = norm_cap(m.group(1), "G")

    elif cat.startswith("Network"):
        # 链路速率：10G / 25G / 100G / 200G / 1G / 10GE
        m = re.search(r"(?<!\d)(\d{1,3})\s*GE?(?![A-Z])", n)
        if m:
            s["Link Speed"] = f"{m.group(1)}G"
        m = re.search(r"(\d+)\s*[Pp]ort", n)
        if m:
            s["Ports"] = m.group(1)
        elif re.search(r"双|2口|2端", n):
            s["Ports"] = "2"
        elif re.search(r"四|4口", n):
            s["Ports"] = "4"
        elif re.search(r"单|1口", n):
            s["Ports"] = "1"

    elif cat == "CPU":
        m = re.search(r"(?<!\d)(\d{1,3})\s*C\b", n)
        if m and int(m.group(1)) <= 256:
            s["Cores"] = m.group(1)

    elif cat == "Raid card":
        # 缓存大小：1G/2G/4G（紧跟 G，后面是 cache/+/电容/结尾）
        m = re.search(r"(?<!\d)(\d)\s*G(?:\s*cache|\s*\+|(?![A-Za-z]))", n)
        if m:
            s["Cache"] = f"{m.group(1)}GB"
        # 端口数：型号里的 -8i / -16i
        m = re.search(r"-(\d+)i\b", n, re.I)
        if m:
            s["Ports"] = m.group(1)

    return s


with e.connect() as c:
    rows = c.execute(
        text(
            """SELECT p.id, p.name, cat.name as cat
               FROM kp_parts p JOIN kp_categories cat ON cat.id=p.category_id
               ORDER BY cat.name, p.id"""
        )
    ).fetchall()

    from collections import defaultdict

    by_cat = defaultdict(list)
    for pid, name, cat in rows:
        sp = extract(cat, name)
        by_cat[cat].append((pid, name, sp))

    print("=" * 70)
    print("DRY-RUN: spec 提取预览（不写库）")
    print("=" * 70)
    total, total_ok = 0, 0
    for cat in sorted(by_cat):
        items = by_cat[cat]
        ok = [it for it in items if it[2]]
        total += len(items)
        total_ok += len(ok)
        print(f"\n### {cat}  ({len(ok)}/{len(items)} 件可提取)")
        # 展示前若干样本 + 标注提取失败的
        shown = 0
        for pid, name, sp in items:
            if sp:
                if shown < 8:
                    print(f"  ✓ [{pid}] {name}")
                    print(f"      → {sp}")
                    shown += 1
        failed = [(pid, name) for pid, name, sp in items if not sp]
        if failed:
            print(f"  ✗ 未提取 ({len(failed)} 件):")
            for pid, name in failed[:8]:
                print(f"      [{pid}] {name}")
            if len(failed) > 8:
                print(f"      ... 还有 {len(failed) - 8} 件")

    print("\n" + "=" * 70)
    print(f"总计：{total_ok}/{total} 件可提取规格 ({total_ok * 100 // total}%)")
    print("=" * 70)
