# -*- coding: utf-8 -*-
"""KP specs 回填（GPU FP16 dense / CPU Cores / NIC Ports）。

默认 dry-run：打印预览 + 生成 markdown 报告，不写库；--commit 先备份受影响行再落库。
只补「键缺失或值为空」的件，绝不覆盖已有非空值（人工维护的数据优先）。

口径（2026-09-19 联网调研，六维雷达 GPU 维度）：
- FP16 Tensor/BF16 dense（非稀疏）TFLOPS，整卡口径（双芯卡/模组按整卡合计）。
- NVIDIA 官网常标 2:4 稀疏值，取 dense = sparse / 2。
- 推导值（无官方 FP16、由更高精度 TOPS 换算）在备注标注「推导」。
- 公开资料无确证值的国产卡/非官方 SKU 一律留空不编造。
"""
import sys, os, json, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from app.models.base import KP_SessionLocal

# ---- 回填表：pn → (值, 来源备注)；键名必须与 kp.kp_parts.pn 完全一致 ----
_SRC_NVIDIA_WHITEPAPER = "NVIDIA 白皮书稀疏值÷2"
_SRC_NVIDIA_PAGE = "NVIDIA 官网标称稀疏÷2"
_SRC_VENDOR = "厂商官方"
_SRC_PRESS = "多源媒体报道"

FP16 = {
    "AMD AI Pro R9700 32G":                 ("95.7",  _SRC_VENDOR + "（RDNA4 peak）"),
    "AMD R9700":                            ("95.7",  _SRC_VENDOR + "（同上，同芯片）"),
    "AMD W7900DS 48G":                      ("122.8", _SRC_VENDOR + "（WMMA）"),
    "W7900":                                ("122.8", _SRC_VENDOR + "（同上，同芯片）"),
    "GeForce 40系列影驰RTX5080 OC16G":       ("225",   "推导：1801 TOPS(FP4 sparse)÷8，官方未标 FP16"),
    "NVIDIA 4090涡轮卡":                     ("165.2", _SRC_NVIDIA_WHITEPAPER + " 330.3"),
    "NVIDIA RTX4090 24G 涡轮卡":             ("165.2", "同 RTX 4090"),
    "NVIDIA RTX4090 48G 涡轮卡":             ("165.2", "改装显存版，算力同 RTX 4090"),
    "NVIDIA GeForce RTX4090D 24GB":         ("156.6", "约 4090×95%（中国版），中置信"),
    "NVIDIA A800 80G":                      ("312",   _SRC_VENDOR + "（A100 同源 dense）"),
    "NVIDIA H100 80G":                      ("989",   _SRC_VENDOR + " SXM 口径（PCIe 版 835，按实际进货形态确认）"),
    "NVIDIA L20":                           ("119.5", _SRC_VENDOR + " dense"),
    "NVIDIA L20 48G":                       ("119.5", "同 L20"),
    "NVIDIA L4 24G":                        ("60.5",  _SRC_NVIDIA_WHITEPAPER + " 121"),
    "NVIDIA L40":                           ("181",   _SRC_NVIDIA_WHITEPAPER + " 362"),
    "NVIDIA RTX 5000 Ada 32G":              ("54.3",  _SRC_NVIDIA_WHITEPAPER + " 108.6"),
    "NVIDIA RTX 6000 Ada-48G":              ("72.9",  _SRC_NVIDIA_WHITEPAPER + " 145.7"),
    "NVIDIA RTX 5090 32G":                  ("419.2", _SRC_NVIDIA_PAGE + " 838.4"),
    "NVIDIA RTX 5090 涡轮卡":                ("419.2", "同 RTX 5090"),
    "NVIDIA RTX5090 32G 涡轮卡":             ("419.2", "同 RTX 5090"),
    "NVIDIA RTX Pro6000 96G":               ("504",   "RTX PRO Blackwell 白皮书 FP16acc dense 503.8"),
    "RTX PRO 5000 48G":                     ("364",   "RTX PRO Blackwell 白皮书 FP16acc dense 364.2"),
    "NVIDIA RTX PRO5000 48G":               ("364",   "同 RTX PRO 5000 Blackwell"),
    "昆仑芯 P800":                           ("345",   _SRC_PRESS + "（另有旧口径 128，存疑）"),
    "昆仑芯 P800 96G pcie":                  ("345",   "同昆仑芯 P800"),
    "昆仑芯P800":                            ("345",   "同昆仑芯 P800"),
    "沐曦 C500":                             ("240",   _SRC_VENDOR + "（INT8 480 TOPS → FP16 240）"),
    "曦云C500":                              ("240",   "同沐曦 C500"),
    "昇腾Atlas 300I Duo 96G GPU AI大模型推理卡": ("280", _SRC_VENDOR + "（310P×2 官方）"),
    "天数智芯 天垓150":                       ("192",   _SRC_PRESS),
    "天数智芯150S 64G":                      ("192",   "同天垓150 系，中置信"),
}

# 留空不编造：公开资料无确证值
SKIP = {
    "Nvida RTX PRO 5000 72G 涡轮显卡":  "无此官方 SKU（PRO 5000 Blackwell=48G），72G 存疑",
    "NVIDIA RTX Pro 6000D 84G":        "非官方 SKU（6000 Blackwell=96G），84G 存疑；若确认为 6000 Blackwell 则 504",
    "壁仞166C":                        "官方未公布 FP16 峰值（BR100=1024/BR104≈256 仅作参考）",
    "壁仞BR166C及bridge":               "同上",
    "曦云C550 8GPU模组":                "C550 各源口径混乱（22.4 vs 240）且 8GPU 模组需×8",
    "天数100duo  64G":                 "智铠100 官方未公布统一 FP16 峰值",
    "天数智芯 智铠100":                  "官方未公布统一 FP16 峰值",
    "天数智芯 智铠100DUO":               "同上",
    "天数智芯100DUO 单卡64G":            "同上",
    "智凯100duo":                      "同上",
    "智铠100DUO 64G":                  "同上",
    "S.E.E.0005001":                   "OEM 编码无法对应型号",
    "S.E.E.0005002":                   "OEM 编码无法对应型号",
    "武桐树X201及2个bridge":             "公开资料查无此件",
}

CPU_CORES = {
    "AMD 9J14": ("96", "PassMark 确认（Zen4 定制渠道型号）"),
}
NIC_PORTS = {
    "400G多模模块": ("1", "单口模块"),
    "4x10GbE NIC, Intel XL710, Quad Port RJ-45": ("4", "名字含 Quad Port"),
    "ConnectX‑6 Dx dual 25G SFP28 + optical module (supportJumbo Frame (MTU) t No less than 9,000 bytes Input/Output Virtualization (SR-IOV)": ("2", "名字含 dual"),
}

GROUPS = [
    ("FP16 TFLOPS", FP16), ("FP16 TFLOPS", {}),  # SKIP 单独展示
    ("Cores", CPU_CORES), ("Ports", NIC_PORTS),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="写库（先备份）")
    args = ap.parse_args()

    s = KP_SessionLocal()
    rows = s.execute(text("SELECT name, id FROM kp.kp_parts")).fetchall()
    by_pn = {r[0]: r[1] for r in rows}

    plan = []   # (pn, part_id, key, value, note)
    missing = []  # 表里有但库里找不到的 pn
    empty_skip = []  # (pn, key, 现值) 已有非空值, 不覆盖

    for key, table in [("FP16 TFLOPS", FP16), ("Cores", CPU_CORES), ("Ports", NIC_PORTS)]:
        for pn, (val, note) in table.items():
            pid = by_pn.get(pn)
            if pid is None:
                missing.append((pn, key))
                continue
            cur = s.execute(text(
                "SELECT spec_value FROM kp.kp_part_specs WHERE part_id=:p AND spec_key=:k"),
                {"p": pid, "k": key}).scalar()
            if cur is not None and str(cur).strip():
                empty_skip.append((pn, key, cur))
                continue
            plan.append((pn, pid, key, val, note))

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    lines = [f"# KP specs 回填预览（{ts}）", "",
             f"口径：GPU=FP16/BF16 dense TFLOPS（整卡）；公开资料无确证值的一律留空。", "",
             f"## 将写入 {len(plan)} 件", "",
             "| pn | spec_key | 值 | 来源 |", "|---|---|---|---|"]
    for pn, pid, key, val, note in plan:
        lines.append(f"| {pn} | {key} | {val} | {note} |")
    lines += ["", f"## 留空不编造 {len(SKIP)} 件", "", "| pn | 原因 |", "|---|---|"]
    for pn, why in SKIP.items():
        lines.append(f"| {pn} | {why} |")
    if empty_skip:
        lines += ["", f"## 已有值不覆盖 {len(empty_skip)} 条", "", "| pn | key | 现值 |", "|---|---|---|"]
        for pn, key, cur in empty_skip:
            lines.append(f"| {pn} | {key} | {cur} |")
    if missing:
        lines += ["", f"## 库中未找到 {len(missing)} 条（表过期？）", ""]
        for pn, key in missing:
            lines.append(f"- {pn} ({key})")

    report = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_kp_spec_backfill_preview.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"plan={len(plan)} skip_unverified={len(SKIP)} protected={len(empty_skip)} missing={len(missing)}")
    print(f"report → {report}")

    if not args.commit:
        s.close()
        return

    # 备份受影响 part 的相关 spec 行
    bak_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_backups")
    os.makedirs(bak_dir, exist_ok=True)
    bak_path = os.path.join(bak_dir, f"kp_spec_backfill_{ts}.json")
    backup = []
    for _, pid, key, _, _ in plan:
        r = s.execute(text(
            "SELECT id, part_id, spec_key, spec_value FROM kp.kp_part_specs WHERE part_id=:p AND spec_key=:k"),
            {"p": pid, "k": key}).fetchone()
        backup.append({"id": r[0] if r else None, "part_id": pid, "spec_key": key,
                       "spec_value": r[3] if r else None, "pn":
                       next(pn for pn, p2, _, _, _ in plan if p2 == pid)})
    with open(bak_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=1)

    n = 0
    for pn, pid, key, val, _ in plan:
        s.execute(text("""
            INSERT INTO kp.kp_part_specs (part_id, spec_key, spec_value, sort_order)
            VALUES (:p, :k, :v, 999)
            ON CONFLICT (part_id, spec_key) DO UPDATE SET spec_value = EXCLUDED.spec_value
        """), {"p": pid, "k": key, "v": val})
        n += 1
    s.commit()
    print(f"COMMITTED {n} rows; backup → {bak_path}")
    s.close()


if __name__ == "__main__":
    main()
