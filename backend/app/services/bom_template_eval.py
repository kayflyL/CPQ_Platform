# -*- coding: utf-8 -*-
"""BOM 模板 L6 求值器 —— BOM案例库的 L6 配置单按模板结构生成。

规则语义移植自前端 bomRuleEngine.ts：fixed / template / part_field / part_quantity /
struct_count(io_slot, rear_all, gpu_direct, front_cables) / config_calc / config_value + 一层 fallback。
数据源：l6.bom_templates.rows + l6.base_configs（parts/bays/psu_bays/config_content/背板 bt）+ kp_lines。
L6 描述式原则（2026-08-04 R25）：desc 全部是描述/能力文本，不找料号——io_slot riser 用机型标准
（config_content.standard_riser，装 GPU 升级 x16），rear_all/gpu_direct 按 GPU/NVMe 数量派生。
算不出的行（如 IO 槽位 option 类型未存、PSU 瓦数未给）→ 留空，交给用户在 L6 编辑器里手填。
"""
import json
import re
from typing import Optional

from sqlalchemy import text

from app.models.base import l6_engine, kp_engine

# 品类中英别名（对齐前端 bomRuleEngine.CATEGORY_CN_EN）
_CAT_ALIASES = {
    "heatsink": ["散热器", "散热"],
    "fan": ["风扇"],
    "rail": ["滑轨", "导轨", "rail"],
    "chassis": ["机箱"],
    "backplane": ["背板"],
    "cable": ["线缆", "cable"],
    "psu": ["电源", "psu", "power supply"],
}
_IO_SLOT_NAMES = {"io1", "io2", "io3", "io4", "ocp"}


def _norm(s: str) -> str:
    return re.sub(r"[\s\-]", "", (s or "")).lower()


def _find_part(parts: list, category: str) -> Optional[dict]:
    """按品类找基准配置底盘件（类别/别名/名称宽松匹配，取首个）。"""
    cl = _norm(category)
    aliases = [_norm(a) for a in _CAT_ALIASES.get(cl, [])]
    for p in parts:
        cat = _norm(p.get("category") or "")
        name = _norm(p.get("name") or "")
        if cat == cl or (aliases and (cat in aliases or any(a and (a in cat or a in name) for a in aliases))):
            return p
    return None


def _spec_str(specs, key: str) -> str:
    if not specs:
        return ""
    if isinstance(specs, str):
        try:
            specs = json.loads(specs)
        except Exception:
            return ""
    if not isinstance(specs, dict):
        return ""
    v = specs.get(key)
    return "" if v is None else str(v)


def _render_tpl(tpl: str, vars_: dict) -> Optional[str]:
    missing = False
    def _rep(m):
        nonlocal missing
        k = m.group(1)
        v = vars_.get(k)
        if v in (None, ""):
            missing = True
            return ""
        return str(v)
    out = re.sub(r"\$\{(\w+)\}", _rep, tpl)
    return None if missing else out


def _read_part_field(part: Optional[dict], field: str) -> Optional[str]:
    if not part:
        return None
    if field.startswith("specs."):
        v = _spec_str(part.get("specs"), field[len("specs."):])
        return v or None
    v = part.get(field)
    return None if v in (None, "") else str(v)


def _load_template_rows(template_id: int) -> list:
    with l6_engine.connect() as c:
        r = c.execute(text("SELECT rows FROM l6.bom_templates WHERE id=:id"), {"id": template_id}).mappings().first()
    if not r:
        return []
    rows = r["rows"]
    return rows if isinstance(rows, list) else []


def _load_base_config(base_config_id: int) -> Optional[dict]:
    with l6_engine.connect() as c:
        bc = c.execute(text(
            "SELECT id, name, bays, psu_bays, rear_slots, config_content FROM l6.base_configs WHERE id=:id"
        ), {"id": base_config_id}).mappings().first()
        if not bc:
            return None
        parts = c.execute(text("""
            SELECT p.pn, p.quantity, m.name, m.category, m.specs
            FROM l6.base_config_parts p JOIN l6.parts_master m ON p.pn = m.pn
            WHERE p.config_id=:cid ORDER BY p.sort_order
        """), {"cid": base_config_id}).mappings().all()
    bc = dict(bc)
    cc = bc.get("config_content")
    if isinstance(cc, str):
        try:
            bc["config_content"] = json.loads(cc)
        except Exception:
            bc["config_content"] = None
    bc["parts"] = [dict(p) for p in parts]
    return bc


def _hydrate_kp(kp_lines: list) -> list:
    """按 part_id 补件名（前端表单只带 part_id/hint，盘介质判定需要真实件名）。"""
    ids = [int(l["part_id"]) for l in kp_lines if l.get("part_id")]
    names = {}
    if ids:
        with kp_engine.connect() as c:
            rows = c.execute(text("SELECT id, name FROM kp.kp_parts WHERE id = ANY(:ids)"),
                             {"ids": ids}).mappings().all()
        for r in rows:
            names[r["id"]] = r["name"]
    out = []
    for l in kp_lines or []:
        nl = dict(l)
        if not nl.get("name") and l.get("part_id") and int(l["part_id"]) in names:
            nl["name"] = names[int(l["part_id"])]
        out.append(nl)
    return out


def _raid_model_from_kp(kp_lines: list) -> str:
    """RAID 卡型号（Cable 行用，对齐前端 cableDescFrom）："LSI 9540-8i 4G" → "9540"。"""
    for l in kp_lines or []:
        cat = _norm(l.get("category") or "")
        if "raid" not in cat and "阵列" not in cat and "hba" not in cat:
            continue
        # _norm 已删连字符（"9540-8i"→"95408i"），正则容忍可选分隔符
        m = re.search(r"(\d{3,4})[-\s]?(\d{1,2})\s*[iI]", _norm((l.get("hint") or "") + " " + (l.get("name") or "")))
        return m.group(1) if m else ""
    return ""


def _has_high_bw_nic(kp_lines: list) -> bool:
    """是否含高带宽网卡（100G/200G/400G，x16 卡）——io_slot riser 需升级 x16（YC-2026-0722 样本）。"""
    for l in kp_lines or []:
        cat = _norm(l.get("category") or "")
        if "nic" not in cat and "网卡" not in cat and "网络" not in cat:
            continue
        blob = _norm((l.get("hint") or "") + " " + (l.get("name") or ""))
        if re.search(r"(100|200|400)\s*g", blob):
            return True
    return False


def _std_riser_for(std, slot: str) -> Optional[str]:
    """机型标准 riser：支持 {slot: desc} 按槽位（IO1/IO2 可不同，键大小写不敏感）或字符串（全槽同规格）。
    未配置返回 None → 行留空手填（系统原则：拒绝硬编码，riser 规格数据驱动）。"""
    if isinstance(std, dict):
        v = std.get(slot)
        if v is None:
            for _k, _v in std.items():
                if _norm(str(_k)) == slot:
                    v = _v
                    break
        if v is None:
            v = std.get("default")
    else:
        v = std
    return str(v) if v else None


def _drive_counts(kp_lines: list) -> dict:
    """从 KP 行统计盘介质数量：{SATA, SAS, NVMe, HDD}。"""
    out = {"SATA": 0, "SAS": 0, "NVMe": 0}
    for l in kp_lines:
        cat = _norm(l.get("category") or "")
        if "hdd" not in cat and "ssd" not in cat and "disk" not in cat and "盘" not in cat:
            continue
        qty = int(l.get("qty") or 0)
        blob = _norm((l.get("hint") or "") + " " + (l.get("name") or ""))
        if "nvme" in blob or "u.2" in blob or "u2" in blob:
            out["NVMe"] += qty
        elif "sas" in blob:
            out["SAS"] += qty
        else:
            out["SATA"] += qty
    return out


def eval_l6_rows(template_id: int, base_config_id: int,
                 kp_lines: list, chassis_signals: Optional[dict] = None) -> list:
    """按 BOM 模板求值 L6 配置单行 [{catalogue, description, qty}]，空行隐藏。"""
    rows = _load_template_rows(template_id)
    bc = _load_base_config(base_config_id)
    if not bc:
        return []

    # 底盘件按品类索引
    part_idx = {cat: _find_part(bc["parts"], cat) for cat in ("backplane", "heatsink", "fan", "rail", "psu", "cable")}
    # 背板 bt → bp_type_desc
    bt = _spec_str(part_idx["backplane"].get("specs") if part_idx["backplane"] else {}, "bt") if part_idx["backplane"] else ""
    bp_type = (chassis_signals or {}).get("bp_type") or bt or ""
    bp_type_desc = {"tri": "SATA/SAS/NVMe", "dc": "SATA/SAS"}.get(str(bp_type).lower(), "")

    kp = _hydrate_kp(kp_lines or [])
    drives = _drive_counts(kp)
    gpu_qty = sum(int(l.get("qty") or 0) for l in kp if "gpu" in _norm(l.get("category") or "") or "显卡" in (l.get("category") or ""))
    nvme_count = drives["NVMe"]
    psu_qty = (chassis_signals or {}).get("psu_qty") or bc.get("psu_bays") or ""
    psu_wattage = (chassis_signals or {}).get("psu_wattage") or ""
    psu_name = (part_idx["psu"].get("name") if part_idx["psu"] else "") or ""
    gpu_cord_desc = "GPU power cable" if gpu_qty > 0 else ""
    # 线缆描述：RAID SAS 线（跟 RAID 卡型号走，SAS/SATA 盘按 4 向上取整）+ NVMe 线（按 2 向上取整）。
    # 2026-08-04 R27 用户确认：Cable 行算上 RAID SAS 线（对齐前端 cableDescFrom）。
    cable_parts = []
    _raid_model = _raid_model_from_kp(kp)
    _sas_total = drives["SAS"] + drives["SATA"]
    if _sas_total > 0 and _raid_model:
        cable_parts.append(f"{_raid_model} {(-(-_sas_total // 4)) * 4} SAS Cable")
    if drives["NVMe"]:
        cable_parts.append(f"{(-(-drives['NVMe'] // 2)) * 2} NVMe Cable")
    cable_desc = "，".join(cable_parts)

    _cc = bc.get("config_content") or {}
    vars_ = {
        "bays": bc.get("bays") or "",
        # I6 R25 + R27：L6 描述式——io_slot riser 不找料号、不硬编码。
        # standard_riser（默认，可按槽位）+ riser_x16（GPU/100G 升级规格）均数据驱动，未配置留空手填。
        "standard_riser": _cc.get("standard_riser"),
        "riser_x16": _cc.get("riser_x16"),
        # R26：高带宽网卡（100G+，x16 卡）→ IO1 riser 升级 x16
        "high_bw_nic": _has_high_bw_nic(kp),
        "bp_type_desc": bp_type_desc,
        "psu_qty": psu_qty,
        "psu_wattage": psu_wattage,
        "psu_name": psu_name,
        "gpu_qty": gpu_qty,
        "gpu_cable_qty": gpu_qty,
        "gpu_power_cord_desc": gpu_cord_desc,
        "nvme_count": nvme_count,
        "cable_desc": cable_desc,
    }

    out = []
    for row in rows:
        rule = row.get("rule") or {}
        label = row.get("label") or row.get("type") or ""
        desc = _eval_desc(rule, vars_, part_idx, row, gpu_qty, nvme_count, drives)
        qty = _eval_qty(rule, vars_, part_idx, gpu_qty)
        if desc is None and qty is None:
            continue  # 全空行隐藏
        out.append({"catalogue": label, "description": desc or "", "qty": qty})
    return out


def _eval_desc(rule: dict, vars_: dict, part_idx: dict,
               row: dict, gpu_qty: int, nvme_count: int, drives: dict) -> Optional[str]:
    src = rule.get("desc") or {}
    val = _desc_from(src, vars_, part_idx, row, gpu_qty, nvme_count, drives)
    if val not in (None, ""):
        return val
    fb = rule.get("desc_fallback")
    if fb:
        return _desc_from(fb, vars_, part_idx, row, gpu_qty, nvme_count, drives) or None
    return None


def _desc_from(src, vars_, part_idx, row, gpu_qty, nvme_count, drives) -> Optional[str]:
    kind = src.get("kind")
    if kind == "fixed":
        return src.get("value")
    if kind == "template":
        return _render_tpl(src.get("template") or "", vars_)
    if kind == "part_field":
        part = part_idx.get(_norm(src.get("category") or ""))
        return _read_part_field(part, src.get("field") or "")
    if kind == "config_value":
        v = vars_.get(src.get("key"))
        return None if v in (None, "") else str(v)
    if kind == "struct_count":
        scope = src.get("scope")
        if scope == "io_slot":
            # I6 R25 + R26 + R27：riser 规格全数据驱动（standard_riser 默认 / riser_x16 升级），
            # 不硬编码任何 riser 文案。装 GPU → 全槽 riser_x16；高带宽网卡(100G+) → IO1 riser_x16；
            # 否则按槽位 standard_riser；无数据 → None 留空手填。
            slot = _norm((row or {}).get("slot") or "")
            _x16 = vars_.get("riser_x16")
            if gpu_qty > 0:
                return str(_x16) if _x16 else None
            if vars_.get("high_bw_nic") and slot == "io1":
                return str(_x16) if _x16 else None
            return _std_riser_for(vars_.get("standard_riser"), slot)
        if scope == "gpu_direct":
            return f"{gpu_qty}*GPU" if gpu_qty > 0 else None
        if scope == "rear_all":
            parts = []
            if gpu_qty > 0:
                parts.append(f"{gpu_qty}*GPU")
            if nvme_count > 0:
                parts.append(f"{nvme_count}NVME")
            return "+".join(parts) or None
        if scope == "front_cables":
            seg = []
            if drives["NVMe"]:
                seg.append(f"{drives['NVMe']}*NVMe")
            if drives["SAS"]:
                seg.append(f"{drives['SAS']}*SAS")
            if drives["SATA"]:
                seg.append(f"{drives['SATA']}*SATA")
            return "，".join(seg) or None
    return None


def _eval_qty(rule: dict, vars_: dict, part_idx: dict, gpu_qty: int) -> Optional[int]:
    src = rule.get("qty") or {}
    val = _qty_from(src, vars_, part_idx, gpu_qty)
    if val is not None:
        return val
    fb = rule.get("qty_fallback")
    if fb:
        return _qty_from(fb, vars_, part_idx, gpu_qty)
    return None


def _qty_from(src, vars_, part_idx, gpu_qty) -> Optional[int]:
    kind = src.get("kind")
    if kind == "fixed":
        return int(src.get("value") or 0)
    if kind == "part_quantity":
        part = part_idx.get(_norm(src.get("category") or ""))
        if not part:
            return None
        q = part.get("quantity")
        return int(q) if q else None
    if kind == "config_calc":
        v = vars_.get(src.get("key"))
        try:
            n = int(v)
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None
    return None
