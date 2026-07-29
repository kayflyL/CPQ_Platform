"""apply_lookup: 用型号对照表 + 增强 name 规则补 CPU/GPU 的 spec。

来源：
  1. 增强 name 规则（CPU 的 "48 cores"/"32 core" 单词写法）
  2. 型号对照表（NVIDIA 显存 / AMD EPYC 核数，凭公开规格，仅高置信型号）

策略：逐 key 补缺（已有 Cores/Capacity 的不覆盖）；不确定的型号一律跳过留手填。
事务写入，输出新回滚锚点。
"""
import re
import sys
from sqlalchemy import create_engine, text

APPLY = "--apply" in sys.argv

e = create_engine(
    "postgresql://postgres:961216@localhost:5432/cpq_platform?client_encoding=UTF8",
    connect_args={"options": "-c search_path=kp"},
)

# 型号关键词 → (key, value, 来源备注)
GPU_VRAM = {
    "4090": ("Capacity", "24 GB", "RTX 4090 公开规格"),
    "5090": ("Capacity", "32 GB", "RTX 5090 公开规格"),
    "L40":  ("Capacity", "48 GB", "L40 公开规格"),
    "H100": ("Capacity", "80 GB", "H100 公开规格"),
    "A800": ("Capacity", "80 GB", "A800 公开规格"),
    "W7900":("Capacity", "48 GB", "Radeon Pro W7900 公开规格"),
}

# AMD EPYC 型号（仅 name 其他变体印证过核数的，高置信）
CPU_CORES_TABLE = {
    "9334": ("Cores", "32", "EPYC 9334（32C，与 9354 同核）"),
    "9354": ("Cores", "32", "EPYC 9354（name [112] 自带 32C 印证）"),
    "9554": ("Cores", "64", "EPYC 9554（name [114] 自带 64C 印证）"),
    "9654": ("Cores", "96", "EPYC 9654（name [116] 自带 96C 印证）"),
}


def extract_cores_from_name(name: str):
    """增强：匹配 48C / 48 cores / 48 core / 48核（原规则漏了 cores 单词）"""
    n = name.lower()
    # 先排除 "cores" 单词里误匹配（直接匹配 N cores/core/C）
    m = re.search(r"(?<!\d)(\d{1,3})\s*(?:cores?|核)", n)
    if m and int(m.group(1)) <= 256:
        return m.group(1)
    return None


def gpu_lookup(name: str):
    up = name.upper()
    for kw, (k, v, _) in GPU_VRAM.items():
        if kw.upper() in up:
            return k, v
    return None


def cpu_lookup(name: str):
    up = name.upper()
    for kw, (k, v, _) in CPU_CORES_TABLE.items():
        # 型号边界：kw 前后不能是数字（避免 9334 匹配到 93344 之类）
        if re.search(rf"(?<!\d){kw}(?!\d)", up):
            return k, v
    return None


def fetch_pending(conn):
    """拉 CPU(无 Cores) + GPU(无 Capacity) 待补件"""
    cpu = conn.execute(text("""
        SELECT p.id, p.name FROM kp_parts p
        WHERE p.category_id=(SELECT id FROM kp_categories WHERE name='CPU')
          AND p.id NOT IN (SELECT part_id FROM kp_part_specs WHERE spec_key='Cores')
        ORDER BY p.id
    """)).fetchall()
    gpu = conn.execute(text("""
        SELECT p.id, p.name FROM kp_parts p
        WHERE p.category_id=(SELECT id FROM kp_categories WHERE name='GPU')
          AND p.id NOT IN (SELECT part_id FROM kp_part_specs WHERE spec_key='Capacity')
        ORDER BY p.id
    """)).fetchall()
    return cpu, gpu


def main():
    with e.connect() as conn:
        cpu, gpu = fetch_pending(conn)
        plan = []  # (id, name, key, value, source)
        for pid, name in cpu:
            v = extract_cores_from_name(name)
            if v:
                plan.append((pid, name, "Cores", v, "name 自带（cores 单词）"))
                continue
            lk = cpu_lookup(name)
            if lk:
                plan.append((pid, name, lk[0], lk[1], CPU_CORES_TABLE[next(k for k in CPU_CORES_TABLE if k in name.upper())][2]))
        for pid, name in gpu:
            lk = gpu_lookup(name)
            if lk:
                kw = next(k for k in GPU_VRAM if k.upper() in name.upper())
                plan.append((pid, name, lk[0], lk[1], GPU_VRAM[kw][2]))

        print(f"模式: {'WRITE 写库' if APPLY else 'DRY-RUN 预览（不写库）'}")
        print(f"待补 CPU: {len(cpu)} 件, 待补 GPU: {len(gpu)} 件")
        print(f"本次可填: {len(plan)} 件\n")
        print("将填入:")
        for pid, name, k, v, src in plan:
            print(f"  ✓ [{pid}] {name[:34]:<36} {k:<10} = {v:<6}  ({src})")

        filled_ids = {p[0] for p in plan}
        skipped = [(pid, name) for pid, name in cpu + gpu if pid not in filled_ids]
        print(f"\n跳过留手填 ({len(skipped)} 件，国产卡/不确定型号/Intel未确认):")
        for pid, name in skipped:
            print(f"  ✗ [{pid}] {name}")

        if not APPLY:
            print("\n(dry-run 结束。确认无误加 --apply 写库)")
            return

        # 写库
        with e.begin() as w:
            max_before = w.execute(text("SELECT COALESCE(MAX(id),0) FROM kp_part_specs")).scalar()
            for pid, name, k, v, src in plan:
                w.execute(text(
                    "INSERT INTO kp_part_specs (part_id, spec_key, spec_value, sort_order) "
                    "VALUES (:p,:k,:v,0)"),
                    {"p": pid, "k": k, "v": v})
            print(f"\n写入完成。回滚: DELETE FROM kp_part_specs WHERE id > {max_before};")


main()
