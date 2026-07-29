"""apply: 从 kp_parts.name 提取 spec 并写入 kp_part_specs。

策略：逐 key 补缺（已有该 key 的配件不覆盖），格式对齐现有手填数据（带空格）。
事务写入，输出插入前 max(id) 作为回滚锚点。
"""
import re
from sqlalchemy import create_engine, text

e = create_engine(
    "postgresql://postgres:961216@localhost:5432/cpq_platform?client_encoding=UTF8",
    connect_args={"options": "-c search_path=kp"},
)


def norm_cap(num: str, unit: str) -> str:
    n = float(num)
    n = int(n) if n == int(n) else n
    return f"{n} TB" if unit.upper() in ("T", "TB") else f"{n} GB"


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
        m = re.search(r"(?<!\d)(\d{1,3})\s*GB?(?![0-9])", n)
        if m and int(m.group(1)) <= 200:
            s["Capacity"] = norm_cap(m.group(1), "G")

    elif cat.startswith("Network"):
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
        m = re.search(r"(?<!\d)(\d)\s*G(?:\s*cache|\s*\+|(?![A-Za-z]))", n)
        if m:
            s["Cache"] = f"{m.group(1)} GB"
        m = re.search(r"-(\d+)i\b", n, re.I)
        if m:
            s["Ports"] = m.group(1)

    return s


with e.begin() as conn:
    max_id_before = conn.execute(text("SELECT COALESCE(MAX(id),0) FROM kp_part_specs")).scalar()
    total_before = conn.execute(text("SELECT COUNT(*) FROM kp_part_specs")).scalar()

    parts = conn.execute(
        text(
            """SELECT p.id, p.name, cat.name as cat
               FROM kp_parts p JOIN kp_categories cat ON cat.id=p.category_id
               ORDER BY p.id"""
        )
    ).fetchall()

    inserted = []
    skipped_existing = 0
    for pid, name, cat in parts:
        existing = set(
            conn.execute(
                text("SELECT spec_key FROM kp_part_specs WHERE part_id=:p"),
                {"p": pid},
            ).scalars()
        )
        specs = extract(cat, name)
        for k, v in specs.items():
            if k in existing:
                skipped_existing += 1
                continue
            conn.execute(
                text(
                    "INSERT INTO kp_part_specs (part_id, spec_key, spec_value, sort_order) "
                    "VALUES (:p,:k,:v,0)"
                ),
                {"p": pid, "k": k, "v": v},
            )
            inserted.append((pid, name, k, v))

    max_id_after = conn.execute(text("SELECT MAX(id) FROM kp_part_specs")).scalar()
    total_after = conn.execute(text("SELECT COUNT(*) FROM kp_part_specs")).scalar()

print(f"插入前 kp_part_specs 总行数: {total_before}, max(id)={max_id_before}")
print(f"本次新增: {len(inserted)} 条（跳过已存在的 key {skipped_existing} 次）")
print(f"插入后总行数: {total_after}, max(id)={max_id_after}")
print()
print("样本（前 15 条新增）:")
for pid, name, k, v in inserted[:15]:
    print(f"  [{pid}] {name[:30]:<32} {k:<12} = {v}")
print()
print("=" * 60)
print(f"⚠️ 回滚 SQL（撤销本次所有插入）:")
print(f"   DELETE FROM kp_part_specs WHERE id > {max_id_before};")
print("=" * 60)
