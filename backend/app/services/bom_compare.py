# -*- coding: utf-8 -*-
"""BOM 对照引擎（compare_boms）—— 系统产出 BOM vs 案例 BOM 的规格级对照。

定位：BOM案例库训练闭环的核心纯函数（无页面、无 DB 依赖，可单测）。
- 重放脚本（scripts/replay_cases.py）用它验证"改规则后案例是否跑偏"；
- 后续在线防偏差（P2）复用它做相似案例规格对照。

对照分三层（2026-08-04 训练案例验证：category+qty 会漏掉内存速率差异，必须规格级）：
  1. 品类数量：各 KP 品类件数对得上吗
  2. 件级属性：同品类件的关键属性（CPU 平台/内存速率/盘接口/GPU 型号…）
  3. 需求信号交叉：需求里显式约束（国产/AMD/Intel、DDR 代际、速率、接口）对系统件

差异分类（沿用训练 taxonomy，report 里给 type 建议，最终判定由人/AI 做）：
  qty      数量差异（系统错或数据缺）
  part     件不同（系统错/技术员信息/格式差异——按属性比对判断）
  format   措辞/写法差异（归一后相同 → 不算真差异）
  requirement 需求显式信号被违反（重大偏差）
  missing  一侧缺件（数据缺或系统错）
"""
from __future__ import annotations

import re
from typing import Optional

# ── 属性抽取（从件名/描述文本抽关键属性，specs 有则优先用结构化，这里兜底正则） ──

_CPU_CN_RE = re.compile(r"兆芯|开胜|海光|龙芯|飞腾|鲲鹏|昇腾|国产|信创|KH|KX|KC|Hygon|Phytium|Loongson|Kunpeng", re.I)
_CPU_AMD_RE = re.compile(r"AMD|EPYC|霄龙", re.I)
_CPU_INTEL_RE = re.compile(r"Intel|Xeon|至强", re.I)

_MEM_GEN_RE = re.compile(r"DDR\s?([345])", re.I)
_MEM_SPEED_RE = re.compile(r"(?<![\d.])(\d{3,5})(?!\s*[GT]\b)(?:\s*(?:MT/s|MTs|MHz|MTS))?\b", re.I)
_MEM_CAP_RE = re.compile(r"(?<![\d.])(\d{1,3})\s*G\s*(?:B|b)?(?![\d.])", re.I)

_DRV_IF_RE = re.compile(r"SATA|SAS|NVMe|U\.2|U\.3|M\.2", re.I)
_DRV_CAP_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*([GT])\s*(?:B|b)?(?![\d.])", re.I)

_GPU_MODEL_RE = re.compile(r"\b(H100|H200|B200|A100|A800|L40S?|L20|RTX\s?\d{4}|W7900|910B|920)\b", re.I)
_NIC_SPEED_RE = re.compile(r"(?<![A-Za-z])(\d{2,4})\s*G\b|千兆|万兆|万M", re.I)
_PSU_W_RE = re.compile(r"(\d{3,4})\s*W\b", re.I)
_RAID_MODEL_RE = re.compile(r"\b(?:LSI|Broadcom)?\s*(\d{4,5}-[0-9iI]+)\b", re.I)

# L6 结构件关键词（用于 L6 层存在性/数量对照）
_L6_ITEMS = [
    ("backplane", r"背板|backplane", "背板"),
    ("riser", r"riser|IO\d|扩展卡|转接卡", "IO/Riser"),
    ("fan", r"风扇|fan", "风扇"),
    ("psu", r"(?:电源|psu|power supply)(?![\u4e00-\u9fa5]{0,3}(?:导风罩|挡风罩|导风板))", "电源"),
    ("rail", r"滑轨|rail", "滑轨"),
    ("cable", r"线缆|cable", "线缆"),
    ("heatsink", r"散热|heatsink", "散热器"),
]

# 需求侧显式信号词（国产/AMD/Intel/DDR/速率/接口/瓦数）


def _norm(s: str) -> str:
    """归一文本：去空白/标点/大小写，用于"措辞差异"判断。"""
    if not s:
        return ""
    return re.sub(r"[\s\-_·.()\[\]（）【】/:：,，;；+*×xX]", "", str(s)).lower()


def _token_set(texts) -> set:
    """多行文本 → 归一 token 集合（去重），用于"措辞是否实质相同"判断。
    系统行 catalogue/description 常重复同一型号（如 'AMD 9654 AMD 9654'），
    用集合比对避免误报。"""
    s: set = set()
    for t in texts or []:
        for tok in re.split(r"[\s\-_·.()\[\]（）【】/:：,，;；+*×xX]+", str(t).lower()):
            if tok:
                s.add(tok)
    return s


def _aggregate_attrs(rows: list) -> dict:
    """多行件 → 每属性取值集合（跨行并集；多行品类如盘/网卡取并集，避免叉积假差异）。"""
    agg: dict = {}
    for r in rows or []:
        a = _row_attrs(r)
        for k, v in a.items():
            if k == "text" or v is None:
                continue
            vals = v if isinstance(v, (list, set, tuple)) else [v]
            agg.setdefault(k, set()).update(vals)
    return agg


def _text(row: dict) -> str:
    return " ".join(x for x in (row.get("catalogue") or "", row.get("description") or "") if x)


def _cpu_platform(text: str) -> Optional[str]:
    if _CPU_CN_RE.search(text):
        return "国产"
    if _CPU_AMD_RE.search(text):
        return "AMD"
    if _CPU_INTEL_RE.search(text):
        return "Intel"
    return None


def _mem_attrs(text: str) -> dict:
    m = _MEM_GEN_RE.search(text)
    sp = _MEM_SPEED_RE.search(text)
    cap = _MEM_CAP_RE.search(text)
    return {
        "gen": ("DDR" + m.group(1)) if m else None,
        "speed": int(sp.group(1)) if sp else None,
        "cap_gb": int(float(cap.group(1))) if cap else None,
    }


def _drive_attrs(text: str) -> dict:
    ifs = [x.lower() for x in _DRV_IF_RE.findall(text)]
    # U.2/U.3 是盘形态不是独立接口（U.2 盘即 NVMe）→ 归一，避免系统"7.68T NVMe U.2" vs 技术员"7.68T NVMe"假差异
    if "u.2" in ifs or "u.3" in ifs:
        ifs = [i for i in ifs if i not in ("u.2", "u.3")]
        if "nvme" not in ifs:
            ifs.append("nvme")
    m = _DRV_CAP_RE.search(text)
    return {"iface": list(dict.fromkeys(ifs)) or None, "cap": (m.group(1) + m.group(2)) if m else None}


def _row_attrs(row: dict) -> dict:
    """单行件 → 关键属性（按品类）。specs 结构化字段优先，无则文本正则兜底。"""
    t = _text(row)
    cat = row.get("part_category") or row.get("category") or ""
    cat_u = cat.upper()
    attrs: dict = {"text": _norm(t)}
    if "CPU" in cat_u:
        attrs["platform"] = _cpu_platform(t)
    elif "MEMOR" in cat_u or "内存" in cat:
        attrs.update(_mem_attrs(t))
    elif "HDD" in cat_u or "SSD" in cat_u or "盘" in cat:
        attrs.update(_drive_attrs(t))
    elif "GPU" in cat_u or "显卡" in cat:
        m = _GPU_MODEL_RE.search(t)
        attrs["model"] = m.group(0).replace(" ", "").lower() if m else None
    elif "RAID" in cat_u or "HBA" in cat_u or "阵列" in cat:
        m = _RAID_MODEL_RE.search(t)
        attrs["model"] = m.group(1).lower() if m else None
    elif "NIC" in cat_u or "网卡" in cat or "网络" in cat:
        m = _NIC_SPEED_RE.search(t)
        attrs["speed"] = _nic_speed(m.group(0)) if m else None
        attrs["has_opt"] = bool(re.search(r"光模块|光模|SFP|optical", t, re.I))
    elif "POWER" in cat_u or "电源" in cat:
        m = _PSU_W_RE.search(t)
        attrs["wattage"] = int(m.group(1)) if m else None
    return attrs


def _nic_speed(s: Optional[str]) -> Optional[str]:
    s = (s or "").lower()
    if s in ("千兆",):
        return "1G"
    if s in ("万兆", "万m"):
        return "10G"
    m = re.match(r"(\d+)", s)
    return (m.group(1) + "G") if m else None


def _group_by_cat(rows: list) -> dict:
    """bom_excel_rows → {part_category: [rows]}（KP 段）。"""
    out: dict = {}
    for r in rows or []:
        if (r.get("category") or "") != "Key Parts":
            continue
        cat = r.get("part_category") or "其他"
        out.setdefault(cat, []).append(r)
    return out


def _l6_index(rows: list) -> dict:
    """L6 段 → {item_key: {qty, sample_text}}（按关键词归类，未知行进 other）。"""
    idx: dict = {}
    for r in rows or []:
        if (r.get("category") or "") != "L6":
            continue
        t = _text(r)
        qty = int(r.get("qty") or 1)
        hit = False
        for key, pat, _label in _L6_ITEMS:
            if re.search(pat, t, re.I):
                e = idx.setdefault(key, {"qty": 0, "text": ""})
                e["qty"] += qty
                e["text"] = t[:80]
                hit = True
        if not hit:
            e = idx.setdefault("other", {"qty": 0, "text": ""})
            e["qty"] += qty
            e["text"] = t[:80]
    return idx


# ── riser 内容级对照（2026-08-04 R27：行数相同但规格不同也要抓，如 IO2=2*X8 vs 1*X16+1*X8） ──
_RISER_LINE_RE = re.compile(r"riser|IO\d|扩展卡|转接卡", re.I)
_RISER_SLOT_RE = re.compile(r"(\d+)\s*\*\s*X(\d+)", re.I)


def _riser_signature(text: str) -> str:
    """riser 描述 → 槽位规格签名：'1*X16+1*X8 FHFL' → '1*X16+1*X8'。

    忽略 FHFL/FHHL 等形态词（同一规格写法差异不算真差异）；槽位按宽度倒序拼，顺序无关。
    无法解析出槽位 → 空串（不参与内容比对，避免把未知/空行误报成差异）。
    """
    slots = [(int(n), int(w)) for n, w in _RISER_SLOT_RE.findall(text or "")]
    if not slots:
        return ""
    agg: dict = {}
    for n, w in slots:
        agg[w] = agg.get(w, 0) + n
    return "+".join(f"{agg[w]}*X{w}" for w in sorted(agg, reverse=True))


def _riser_slots(rows: list) -> dict:
    """L6 riser 行按槽位（IO1/IO2/OCP，取 catalogue 前缀）→ {slot: set(签名)}。"""
    out: dict = {}
    for r in rows or []:
        if (r.get("category") or "") != "L6":
            continue
        t = _text(r)
        if not _RISER_LINE_RE.search(t):
            continue
        m = re.match(r"\s*(IO\d+|OCP)", str(r.get("catalogue") or ""), re.I)
        key = m.group(1).upper() if m else "?"
        sig = _riser_signature(t)
        if sig:
            out.setdefault(key, set()).add(sig)
    return out


# ── 需求信号抽取（requirement 文本显式约束 → 交叉核对系统件） ──
_CN_WORDS_RE = re.compile(r"兆芯|开胜|海光|龙芯|飞腾|鲲鹏|信创|国产|KH-?50000|KX-?7000|KH|KX|KC", re.I)
_AMD_WORDS_RE = re.compile(r"AMD|EPYC|霄龙", re.I)
_INTEL_WORDS_RE = re.compile(r"Intel|Xeon|至强", re.I)
_DDR_REQ_RE = re.compile(r"DDR\s?([345])", re.I)
_SPEED_REQ_RE = re.compile(r"(?<![\d])(\d{3,5})\s*(?:MT/s|MHz|MTS)", re.I)
_IF_REQ_RE = re.compile(r"SATA|SAS|NVMe|U\.2|U\.3|M\.2", re.I)
_PSU_REQ_RE = re.compile(r"(\d{3,4})\s*W\b", re.I)
# 盘相关行判据：必须含盘名词才算盘行（接口词 SAS/NVMe 不是判据——
# RAID 卡 "8 个 SAS 口" 被 、 切段后不能误当盘行；"盘" 覆盖 硬盘/固态盘/系统盘/数据盘/存储盘）
_DRIVE_LINE_RE = re.compile(r"硬盘|SSD|HDD|固态|磁盘|存储|盘", re.I)
_RAID_LINE_RE = re.compile(r"RAID|阵列|控制器|HBA|raid", re.I)


def _requirement_signals(requirement: str) -> dict:
    t = requirement or ""
    sig = {}
    if _CN_WORDS_RE.search(t):
        sig["cpu_platform"] = "国产"
    elif _AMD_WORDS_RE.search(t):
        sig["cpu_platform"] = "AMD"
    elif _INTEL_WORDS_RE.search(t):
        sig["cpu_platform"] = "Intel"
    m = _DDR_REQ_RE.search(t)
    if m:
        sig["mem_gen"] = "DDR" + m.group(1)
    m = _SPEED_REQ_RE.search(t)
    if m:
        sig["mem_speed"] = int(m.group(1))
    # 盘接口只从盘相关行提取：RAID/阵列/控制器行的 "12Gb SAS" 不算盘接口（R23 修误报）
    ifs = []
    for _seg in re.split(r"[\n\r，,、;；]+", t):
        if _RAID_LINE_RE.search(_seg):
            continue  # RAID 行整行跳过（SAS 口是 RAID 卡属性，不是盘接口）
        if not _DRIVE_LINE_RE.search(_seg):
            continue
        ifs += [x.lower() for x in _IF_REQ_RE.findall(_seg)]
    if ifs:
        sig["drive_iface"] = list(dict.fromkeys(ifs))
    m = _PSU_REQ_RE.search(t)
    if m:
        sig["psu_wattage"] = int(m.group(1))
    return sig


def plan_system_rows(plan: dict) -> list:
    """系统侧 BOM 行（对比用）：L6 走模板求值（eval_l6_rows，与报价工作台左栏同源），KP 用方案 KP 行。

    2026-08-04 R23 修：plan.cfg.bom_excel_rows 的 L6 是基准配置底盘件（Chassis/MB/…），
    而技术员 L6 是模板结构（Front backplane/IO1/IO2/…）——直接比是两套口径，IO1/IO2 整行误报缺失。
    """
    rows: list = []
    try:
        from app.services.bom_template_eval import eval_l6_rows
        tid = plan.get("bom_template_id")
        cid = plan.get("config_id")
        if tid and cid:
            kp_lines = [
                {"category": r.get("part_category") or "", "qty": r.get("qty") or 1,
                 "hint": r.get("catalogue") or r.get("description") or ""}
                for r in (plan.get("cfg") or {}).get("bom_excel_rows") or []
                if (r.get("category") or "") == "Key Parts"
            ]
            l6 = eval_l6_rows(int(tid), int(cid), kp_lines, plan.get("chassis_signals"))
            rows += [{"category": "L6", "catalogue": r.get("catalogue") or "",
                      "description": r.get("description") or "", "qty": r.get("qty") or 1} for r in l6]
    except Exception:
        pass
    if not rows:
        rows += [r for r in (plan.get("cfg") or {}).get("bom_excel_rows") or []
                 if (r.get("category") or "") == "L6"]
    rows += [r for r in (plan.get("cfg") or {}).get("bom_excel_rows") or []
             if (r.get("category") or "") == "Key Parts"]
    return rows


def compare_boms(system_rows: list, case_rows: list, requirement: str = "",
                 system_unmatched: Optional[list] = None,
                 system_chassis_signals: Optional[dict] = None) -> dict:
    """系统 BOM vs 案例 BOM 规格级对照。

    Args:
        system_rows: 系统产出 bom_excel_rows（plan.cfg.bom_excel_rows）
        case_rows:   案例 bom_excel_rows（repo _to_dict with_parts=True）
        requirement: 原始需求文本（显式信号交叉核对）
        system_unmatched: plan.unmatched（需求品类库里无料，诚实标注）

    Returns:
        {category_level, part_level, l6_level, requirement_checks, summary}
    """
    sys_kp = _group_by_cat(system_rows)
    case_kp = _group_by_cat(case_rows)
    part_level: list = []
    summary = {"category_diff": 0, "part_diff": 0, "l6_diff": 0, "requirement_diff": 0, "major": 0, "format": 0}

    # 1) 品类数量层
    all_cats = sorted(set(sys_kp) | set(case_kp))
    category_level = []
    for cat in all_cats:
        sys_qty = sum(int(r.get("qty") or 1) for r in sys_kp.get(cat, []))
        case_qty = sum(int(r.get("qty") or 1) for r in case_kp.get(cat, []))
        status = "ok" if sys_qty == case_qty else ("missing" if sys_qty == 0 else "diff")
        if status != "ok":
            summary["category_diff"] += 1
        category_level.append({"category": cat, "system_qty": sys_qty, "case_qty": case_qty, "status": status})

    # 2) 件级属性层（按属性取值集合比对，多行品类取并集，避免叉积假差异）
    for cat in all_cats:
        sys_rows = sys_kp.get(cat, [])
        case_rows_ = case_kp.get(cat, [])
        sys_agg = _aggregate_attrs(sys_rows)
        case_agg = _aggregate_attrs(case_rows_)
        diffs = []
        all_keys = sorted(set(sys_agg) | set(case_agg))
        for key in all_keys:
            sv = sys_agg.get(key, set())
            cv = case_agg.get(key, set())
            if not sv or not cv:
                continue  # 一侧属性缺失不报（避免"未知"误报成差异）
            if sv == cv:
                continue
            overlap = bool(sv & cv)
            diffs.append({
                "category": cat, "field": key,
                "system": sorted(str(x) for x in sv), "case": sorted(str(x) for x in cv),
                "type": "part",
                "note": "部分一致" if overlap else "完全不同",
            })
        if not diffs:
            # 无属性级差异但文本不同 → 措辞/格式差异（非真差异）
            sys_tok = _token_set([_text(r) for r in sys_rows])
            case_tok = _token_set([_text(r) for r in case_rows_])
            if sys_tok != case_tok:
                summary["format"] += 1
                diffs.append({"category": cat, "field": "wording",
                              "system": _text(sys_rows[0])[:60] if sys_rows else "",
                              "case": _text(case_rows_[0])[:60] if case_rows_ else "",
                              "type": "format", "note": "归一后属性一致，疑为措辞/格式差异"})
        else:
            summary["part_diff"] += 1
        part_level.append({"category": cat, "diffs": diffs})

    # 3) L6 结构层
    sys_l6 = _l6_index(system_rows)
    # 系统电源不在 L6 行（由 chassis_signals.psu_qty/wattage 渲染）→ 用信号补系统侧电源
    _w = (system_chassis_signals or {}).get("psu_wattage")
    sig_psu_q = (system_chassis_signals or {}).get("psu_qty")
    if _w or sig_psu_q:
        e = sys_l6.setdefault("psu", {"qty": 0, "text": ""})
        e["qty"] += int(sig_psu_q) if sig_psu_q else 1  # 只有瓦数时置 1 作"有电源"标记
        if _w:
            e["text"] = f"{_w}W"
    case_l6 = _l6_index(case_rows)
    l6_level = []
    for key in _L6_ITEMS:
        sk = sys_l6.get(key[0], {}).get("qty", 0)
        ck = case_l6.get(key[0], {}).get("qty", 0)
        if sk == ck:
            continue
        if key[0] in ("psu", "cable") and sk and ck:
            continue  # 电源/线缆两侧都有即视为匹配（系统按信号渲染/拆行，数量口径不同不硬比）
        summary["l6_diff"] += 1
        if sk == 0 or ck == 0:
            summary["major"] += 1  # 结构件整件缺失/多余
        l6_level.append({
            "item": key[2], "system_qty": sk, "case_qty": ck,
            "system_text": sys_l6.get(key[0], {}).get("text", ""),
            "case_text": case_l6.get(key[0], {}).get("text", ""),
        })

    # 3.5) riser 内容级对照：行数一致时规格也要一致（IO2=2*X8 vs 1*X16+1*X8 要抓）；
    # 行数不一致由上面 qty 层报（major），这里只在两侧都有且行数相同时比对内容。
    sk_riser = sys_l6.get("riser", {}).get("qty", 0)
    ck_riser = case_l6.get("riser", {}).get("qty", 0)
    if sk_riser and sk_riser == ck_riser:
        sys_riser = _riser_slots(system_rows)
        case_riser = _riser_slots(case_rows)
        for key in sorted(set(sys_riser) | set(case_riser)):
            ss = sys_riser.get(key, set())
            cs = case_riser.get(key, set())
            if not ss or not cs or ss == cs:
                continue  # 一侧缺 / 规格一致 → 不报
            summary["l6_diff"] += 1
            l6_level.append({
                "category": "IO/Riser", "field": f"{key} 规格",
                "system": sorted(ss), "case": sorted(cs),
                "type": "part", "note": "riser 槽位规格不一致（行数相同但内容不同）",
            })

    # 4) 需求信号交叉核对（系统件是否满足需求显式约束）
    sig = _requirement_signals(requirement)
    req_checks = []
    cpu_platforms = [a.get("platform") for a in [_row_attrs(r) for r in sys_kp.get("CPU", [])] if a.get("platform")]
    mem_attrs_all = [_mem_attrs(_text(r)) for r in sys_kp.get("Memory", [])]
    drv_ifaces = set()
    for r in sys_kp.get("HDD/SSD", []):
        drv_ifaces.update((_drive_attrs(_text(r)).get("iface") or []))
    psu_w = None
    for r in sys_kp.get("Power", []) + sys_kp.get("电源", []):
        m = _PSU_W_RE.search(_text(r))
        if m:
            psu_w = int(m.group(1))

    if "cpu_platform" in sig:
        want = sig["cpu_platform"]
        got = cpu_platforms[0] if cpu_platforms else None
        if got and got != want:
            summary["requirement_diff"] += 1
            summary["major"] += 1
            req_checks.append({"signal": "cpu_platform", "requirement": want, "system": got,
                               "status": "violated", "note": f"需求明确 {want} CPU，系统推 {got}"})
        elif not got:
            summary["requirement_diff"] += 1
            summary["major"] += 1
            req_checks.append({"signal": "cpu_platform", "requirement": want, "system": None,
                               "status": "unknown", "note": "需求明确 CPU 平台但系统 CPU 平台无法识别"})
    if "mem_gen" in sig:
        got = mem_attrs_all[0].get("gen") if mem_attrs_all else None
        if got and got != sig["mem_gen"]:
            summary["requirement_diff"] += 1
            summary["major"] += 1
            req_checks.append({"signal": "mem_gen", "requirement": sig["mem_gen"], "system": got,
                               "status": "violated", "note": f"需求 {sig['mem_gen']}，系统 {got}"})
    if "mem_speed" in sig:
        got = mem_attrs_all[0].get("speed") if mem_attrs_all else None
        if got and abs(got - sig["mem_speed"]) > 100:
            summary["requirement_diff"] += 1
            req_checks.append({"signal": "mem_speed", "requirement": sig["mem_speed"], "system": got,
                               "status": "violated", "note": f"需求速率 {sig['mem_speed']}，系统 {got}"})
    if "drive_iface" in sig and drv_ifaces:
        want_if = set(sig["drive_iface"])
        got_if = set(drv_ifaces)
        if not (want_if & got_if):
            summary["requirement_diff"] += 1
            summary["major"] += 1
            req_checks.append({"signal": "drive_iface", "requirement": sorted(want_if), "system": sorted(got_if),
                               "status": "violated", "note": "需求指定盘接口系统完全未配"})
    if "psu_wattage" in sig and psu_w and psu_w != sig["psu_wattage"]:
        summary["requirement_diff"] += 1
        summary["major"] += 1
        req_checks.append({"signal": "psu_wattage", "requirement": sig["psu_wattage"], "system": psu_w,
                           "status": "violated", "note": f"需求电源 {sig['psu_wattage']}W，系统 {psu_w}W"})

    # 需求品类系统库无料（plan.unmatched）→ 数据缺，诚实标注
    for u in system_unmatched or []:
        req_checks.append({"signal": "unmatched", "requirement": u.get("category"), "system": None,
                           "status": "data_gap", "note": u.get("reason") or "需求品类库中无料"})
        summary["requirement_diff"] += 1

    summary["total"] = (summary["category_diff"] + summary["part_diff"] + summary["l6_diff"]
                        + summary["requirement_diff"])
    return {
        "category_level": category_level,
        "part_level": part_level,
        "l6_level": l6_level,
        "requirement_checks": req_checks,
        "summary": summary,
    }
