"""离线全链路验证：五列布局 + 单价/总价成对 + L6 合并 + F 列堆叠闭合 + 成本口径利润率 + 掩蔽档位。"""
import json
import sys

sys.path.insert(0, ".")

import sqlalchemy as sa

from app.services.preview_data_loader import load_preview_data
from app.services.template_filler import fill_snapshot

OPP = sys.argv[1] if len(sys.argv) > 2 else "OPP-20260908174913798077"
QUO = sys.argv[2] if len(sys.argv) > 2 else "QUO-20260908175316235775"

from scripts._localdb import db_url

ENG = sa.create_engine(db_url(), connect_args={"client_encoding": "UTF8"})


def load_template():
    with ENG.connect() as c:
        row = c.execute(sa.text(
            "SELECT workbook_snapshot, bindings, sheet_config FROM opportunities.univer_templates WHERE id=1"
        )).fetchone()
    snap = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    binds = row[1] if isinstance(row[1], list) else json.loads(row[1])
    cfg = row[2] if isinstance(row[2], dict) else json.loads(row[2])
    return snap, binds, cfg


def build_masks(reveal: list):
    """复刻 _resolve_masked_fields（无权限层：直接按 reveal 参数）"""
    mode_by_group = {"sell": "blank", "cost": "hide", "margin": "hide"}
    masked, region = {}, {}
    with ENG.connect() as c:
        rows = c.execute(sa.text(
            "SELECT source_key, field_key, sens_group, scope FROM rules.dynamic_source_fields"
        )).fetchall()
    for sk, fk, group, scope in rows:
        if scope == "region":
            region.setdefault(sk, set()).add(fk)
        if group and group not in reveal:
            masked.setdefault(sk, {})[fk] = mode_by_group.get(group, "hide")
    return masked, region


def cell(sheet, r, c):
    return (sheet.get("cellData", {}).get(str(r), {}).get(str(c)) or {}).get("v")


def main() -> int:
    snap, binds, cfg = load_template()
    data = load_preview_data(OPP, QUO, binds)
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        mark = "✓" if cond else "✗"
        if not cond:
            ok = False
        print(f"  [{mark}] {label} {detail}")

    # ── 对内版（全揭示）──
    masked, region = build_masks(["sell", "cost", "margin"])
    filled = fill_snapshot(snap, binds, data, cfg, masked_fields=masked, region_fields=region)
    sheets = filled["sheets"]
    cs = next(s for s in sheets.values() if s.get("_config_name"))  # 第一个配置页

    print("== 对内版 ==")
    # 1) 表头五列（L6 表头 idx4 / KP 表头 = Keypats banner+1，均随插行下移）
    hdr_l6 = [cell(cs, 4, i) for i in range(4, 9)]
    kp_hdr_row = None
    banners, total_row = {}, None
    for ridx, row in cs["cellData"].items():
        v0 = (row.get("0") or {}).get("v")
        if v0 in ("L6", "Keypats", "Warranty"):
            r = int(ridx)
            if v0 not in banners or r < banners[v0]:  # 取最靠前的（warranty 行也有 'L6'/'KP' 标签）
                banners[v0] = r
        if v0 == "Total Price":
            total_row = int(ridx)
    kp_hdr_row = banners["Keypats"] + 1
    hdr_kp = [cell(cs, kp_hdr_row, i) for i in range(4, 9)]
    check("表头五列", hdr_l6 == ["Unit Price", "Total Price", "Unit Cost", "Cost Total", "Margin %"]
          and hdr_kp == hdr_l6, f"L6@4={hdr_l6} KP@{kp_hdr_row}={hdr_kp}")

    # 2) 区块定位
    check("区块定位", len(banners) == 3 and total_row is not None,
          f"{banners} total@{total_row}")

    kp_start = banners["Keypats"] + 2
    kp_end = banners["Warranty"] - 1
    l6_start, l6_end = 5, banners["Keypats"] - 1

    # 3) KP 行：单价/总价成对（qty=2 行总价=2×单价）
    pairs = 0
    for r in range(kp_start, kp_end + 1):
        e, f_ = cell(cs, r, 4), cell(cs, r, 5)
        g, h = cell(cs, r, 6), cell(cs, r, 7)
        if e not in (None, "") and f_ not in (None, ""):
            if abs(float(f_) - float(e) * 2) < 0.01 and (h in (None, "") or abs(float(h) - float(g) * 2) < 0.01):
                pairs += 1
    check("KP 单价/总价成对(×2 行)", pairs >= 1, f"{pairs} 对")

    # 4) L6 区域：E/G 空 + F/H/I 有值 + 纵向合并覆盖 F/H/I
    l6_f = cell(cs, l6_start, 5)
    check("L6 合并值", l6_f not in (None, ""), f"F={l6_f}")
    check("L6 E/G 留空", cell(cs, l6_start, 4) in (None, "") and cell(cs, l6_start, 6) in (None, ""))
    merges = cs.get("mergeData", [])
    region_merges = [m for m in merges
                     if m["startColumn"] == m["endColumn"] and m["startColumn"] in (5, 7, 8)
                     and l6_start <= m["startRow"] <= l6_end]
    check("L6 纵向合并 F/H/I", len(region_merges) == 3,
          f"{[(m['startColumn'], m['startRow'], m['endRow']) for m in region_merges]}")

    # 5) 维保费行：Warranty banner 下两行 F 值 = warranty_l6/kp
    w1, w2 = cell(cs, banners["Warranty"] + 1, 5), cell(cs, banners["Warranty"] + 2, 5)
    cfg_row = data["config_summary"][0]
    check("维保费归位 F 列", w1 == cfg_row.get("warranty_l6") and w2 == cfg_row.get("warranty_kp"),
          f"F={w1}/{w2} 期望={cfg_row.get('warranty_l6')}/{cfg_row.get('warranty_kp')}")

    # 5b) 头部信息 Sales/FAE/DATE：值在 F1-F3（任何档位不隐藏），G 列无残留
    hdr_vals = [cell(cs, r, 5) for r in range(3)]
    hdr_g = [cell(cs, r, 6) for r in range(3)]
    check("头部信息归位F1-F3", all(v not in (None, "") for v in hdr_vals) and all(g in (None, "") for g in hdr_g),
          f"F={hdr_vals} G残留={hdr_g}")

    # 6) F 列堆叠 = Total Price = unit_price
    f_total = cell(cs, total_row, 5)
    stack = 0.0
    for r in range(l6_start, kp_end + 1):
        v = cell(cs, r, 5)
        if isinstance(v, (int, float)):
            stack += v
    stack += float(w1 or 0) + float(w2 or 0)
    check("F 列堆叠闭合", abs(stack - float(f_total)) < 0.01 and abs(float(f_total) - cfg_row["unit_price"]) < 0.01,
          f"stack={round(stack,2)} total={f_total} unit_price={cfg_row['unit_price']}")

    # 7) 成本口径利润率：封面=loader；融合值落在行费率区间内
    #    （销售口径融合会低于最低行费率——live 单 15% 行费率销售口径得 13.0，是回归信号）
    row_margins = ({r.get("l6_margin_rate") for r in data["l6_details"]} |
                   {r.get("profit_margin") for r in data["kp_details"]}) - {None}
    cover = sheets["sheet-1"]
    cover_margins = [cell(cover, r, 6) for r in range(5, 12)
                     if isinstance(cell(cover, r, 6), (int, float))]
    lo, hi = min(row_margins), max(row_margins)
    check("利润率成本口径", lo - 0.1 <= cfg_row["margin"] <= hi + 0.1
          and (not cover_margins or all(abs(float(m) - cfg_row["margin"]) < 0.05 for m in cover_margins)),
          f"行费率[{lo},{hi}] loader={cfg_row['margin']} 封面={cover_margins}")

    # 8) 通用：填充输出无残留 {{ 标记（对内版）
    leftovers = [f"{sid}:{r}:{c}"
                 for sid, sh in sheets.items()
                 for r, rowd in sh.get("cellData", {}).items()
                 for c, cell in rowd.items()
                 if isinstance(cell.get("v"), str) and "{{" in cell["v"]]
    check("无残留绑定标记", not leftovers, str(leftovers[:5]))

    # ── 客户版（零揭示）──
    masked, region = build_masks([])
    filled2 = fill_snapshot(snap, binds, data, cfg, masked_fields=masked, region_fields=region)
    cs2 = next(s for s in filled2["sheets"].values() if s.get("_config_name"))
    print("== 客户版 ==")
    hd = {int(k) for k, v in cs2.get("columnData", {}).items() if v.get("hd") == 1}
    check("G/H/I 整列隐藏", hd == {6, 7, 8}, f"hd={sorted(hd)}")
    hdr_rows = {4, kp_hdr_row}
    blank_ok = all(cell(cs2, r, c) in (None, "")
                   for r in range(l6_start, kp_end + 1) for c in (4, 5) if r not in hdr_rows)
    check("E/F 明细清空(表头保留)", blank_ok)
    check("Total Price 恒显", cell(cs2, total_row, 5) == f_total, f"F={cell(cs2, total_row, 5)}")
    # 头部信息静态绑定无 sens_group，客户版不得随 cost 列陪葬
    hdr_vals2 = [cell(cs2, r, 5) for r in range(3)]
    check("头部信息客户版恒显", all(v not in (None, "") for v in hdr_vals2), f"F={hdr_vals2}")

    print("\n" + ("✅ 全部通过" if ok else "❌ 存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
