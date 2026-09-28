# -*- coding: utf-8 -*-
"""BOM 模板 L6 求值器 —— BOM案例库的 L6 配置单按模板结构生成。

规则语义（2026-09-15 重构，与前端 bomRuleEngine.TYPE_RULES 同口径）：
模板 rows 只存骨架（type/label/slot/mode），取值语义 = 行类型固定属性，
不再逐行读规则 JSONB。数据源：l6.bom_templates.rows + l6.base_configs
（form/parts/bays/psu_bays/config_content/背板 bt）+ kp_lines。
L6 描述式原则（2026-08-04 R25）：desc 全部是描述/能力文本，不找料号——io_slot riser 用机型标准
（config_content.standard_riser，装 GPU 升级 x16），rear_all 按 GPU/NVMe 数量派生。
算不出的行（如 IO 槽位 option 类型未存、PSU 瓦数未给）→ 留空，交给用户在 L6 编辑器里手填。
"""
import json
import re
from typing import Optional

from sqlalchemy import text

from app.models.base import l6_engine, kp_engine

_IO_SLOT_NAMES = {"io1", "io2", "io3", "io4", "ocp"}


def _pf(category: str) -> dict:
    return {"kind": "part_field", "category": category, "field": "name"}


def _pq(category: str) -> dict:
    return {"kind": "part_quantity", "category": category}


# 行类型 → 取值规则（唯一权威定义的前端镜像：frontend/src/utils/bomRuleEngine.ts TYPE_RULES）
_TYPE_RULES = {
    "front_backplane": {"desc": {"kind": "template", "template": "${bays}*3.5 ${bp_type_desc}"},
                        "qty": {"kind": "fixed", "value": 1}},
    "io_slot": {"desc": {"kind": "struct_count", "scope": "io_slot"}, "qty": {"kind": "fixed", "value": 1}},
    "rear_summary": {"desc": {"kind": "struct_count", "scope": "rear_all"}, "qty": {"kind": "fixed", "value": 1}},
    "heatsink": {"desc": _pf("heatsink"), "qty": _pq("heatsink"),
                 "desc_fallback": {"kind": "fixed", "value": "CPU 散热器"},
                 "qty_fallback": {"kind": "fixed", "value": 2}},
    "fan": {"desc": _pf("fan"), "qty": _pq("fan"),
            "desc_fallback": {"kind": "fixed", "value": "系统风扇"}},
    "psu_requirement": {"desc": {"kind": "template", "template": "${psu_wattage}W"},
                        "desc_fallback": {"kind": "config_value", "key": "psu_name"},
                        "qty": {"kind": "config_calc", "key": "psu_qty"}},
    "gpu_power_cord": {"desc": {"kind": "config_value", "key": "gpu_power_cord_desc"},
                       "qty": {"kind": "config_calc", "key": "gpu_cable_qty"}},
    "power_cord": {"desc": {"kind": "fixed", "value": "国标电源线"},
                   "qty": {"kind": "config_calc", "key": "psu_qty"}},
    "rail_kit": {"desc": _pf("rail"), "qty": _pq("rail"),
                 "qty_fallback": {"kind": "fixed", "value": 1}},
    "raid_slot": {"desc": {"kind": "manual"}, "qty": {"kind": "manual"}},
}
# cable 行不走 _TYPE_RULES（见 _rule_for_row cable 分支）：单行汇总、qty 恒 1、描述按盘型分段。


def _default_cable_kinds() -> dict:
    """Cable 行按盘型分组默认（前端 bomRuleEngine.defaultCableKinds 镜像，用户定调 2026-09-17）：
    SATA/SAS 每 8 盘 1 组且文案带 RAID 型号前缀；NVMe 每 2 盘 1 组直接写。"""
    return {
        "SATA": {"size": 8, "template": "${raid_model} SATA cable*${n}"},
        "SAS": {"size": 8, "template": "${raid_model} SAS cable*${n}"},
        "NVMe": {"size": 2, "template": "NVMe cable*${n}"},
    }


def _cable_segments(kinds: Optional[dict], vars_: dict) -> Optional[str]:
    """Cable 行描述：按盘型分段——数量 = ceil(盘数/分组)；占位符 ${raid_model}(缺省去前缀)/${n}=组数/${count}=盘数。
    没盘的类型不出现；全没盘 → None（整行隐藏）。"""
    conf = kinds or _default_cable_kinds()
    raid = str(vars_.get("raid_model") or "").strip()
    seg = []
    for k in ("SATA", "SAS", "NVMe"):
        c = conf.get(k)
        if not c:
            continue
        count = int(vars_.get(f"{k.lower()}_count") or 0)
        if count <= 0:
            continue
        n = -(-count // max(1, int(c.get("size") or 1)))
        line = str(c.get("template") or "")
        for key, val in (("n", n), ("count", count), ("raid_model", raid)):
            line = line.replace("${%s}" % key, str(val))
        line = line.lstrip()
        if line:
            seg.append(line)
    return "\n".join(seg) or None


def _rule_for_row(row: dict, form) -> dict:
    """行 → 规则（前端 ruleForRow 镜像）：**逐行 rule 优先**（行上带完整 rule 就按它求值，
    编辑页从类型默认拷贝改出的自定义）；省略 = 类型默认——OCP 槽位行 qty 跟实际选配走
    （未选 → 0 → 整行隐藏）；fan 兜底数量跟形态走（2U=6 / 4U=12）；
    未知类型 → manual 留空手填。"""
    if row.get("rule"):
        return row["rule"]
    t = row.get("type") or ""
    if t == "io_slot" and str(row.get("slot") or "").upper() == "OCP":
        return {"desc": {"kind": "struct_count", "scope": "io_slot"},
                "qty": {"kind": "config_calc", "key": "ocp_qty"}}
    if t == "fan":
        r = dict(_TYPE_RULES["fan"])
        r["qty_fallback"] = {"kind": "fixed", "value": 12 if form == "4U" else 6}
        return r
    if t == "cable":
        return {"desc": {"kind": "cable_groups", "kinds": _default_cable_kinds()},
                "qty": {"kind": "fixed", "value": 1}}
    return _TYPE_RULES.get(t) or _TYPE_RULES["raid_slot"]


def _norm(s: str) -> str:
    return re.sub(r"[\s\-]", "", (s or "")).lower()


def _find_part(parts: list, category: str, category_aliases: Optional[dict] = None) -> Optional[dict]:
    """分级匹配基准配置底盘件（与前端 bomRuleEngine.findBomPart 同口径）：
    ① category 命中（精确/子串/别名）优先 ② 找不到才退 name 子串。
    防「线缆蹭类」：「风扇背板转接线」（name 含"风扇"）不得抢先于「机箱风扇」类真件。
    category_aliases 来自 system_config.bom_category_aliases（可配置，拒绝硬编码）；
    未配置返回空别名，仅按品类精确匹配，不臆断中文别名。"""
    cl = _norm(category)
    alias_src = (category_aliases or {}).get(cl, []) or []
    aliases = [_norm(a) for a in alias_src]

    def _cat_hit(p: dict) -> bool:
        cat = _norm(p.get("category") or "")
        return cat == cl or cl in cat or any(a and a in cat for a in aliases)

    def _name_hit(p: dict) -> bool:
        name = _norm(p.get("name") or "")
        return cl in name or any(a and a in name for a in aliases)

    for p in parts:
        if _cat_hit(p):
            return p
    for p in parts:
        if _name_hit(p):
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
            "SELECT id, name, form, bays, psu_bays, rear_slots, config_content FROM l6.base_configs WHERE id=:id"
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
    """RAID 卡型号（Cable 行 SATA/SAS 文案前缀，对齐前端 raidModelFrom）："LSI 9540-8i 4G" → "9540"。"""
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

    # 底盘件按品类索引；别名取自 system_config.bom_category_aliases（可配置，拒绝硬编码）
    _category_aliases: dict = {}
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        _repo = SystemConfigRepository()
        try:
            _category_aliases = _repo.get_value("bom_category_aliases") or {}
        finally:
            _repo.close()
    except Exception:
        _category_aliases = {}
    part_idx = {cat: _find_part(bc["parts"], cat, _category_aliases) for cat in ("backplane", "heatsink", "fan", "rail", "psu", "cable")}
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
    _raid_model = _raid_model_from_kp(kp)

    # OCP 网络槽（与前端 defaultRearFrom 同口径）：rear_slots 含 OCP 槽 → 默认 ocp_x8 适配板
    _rear_slots = bc.get("rear_slots") or []
    if isinstance(_rear_slots, str):
        try:
            _rear_slots = json.loads(_rear_slots)
        except Exception:
            _rear_slots = []
    # OCP 行只在该基准配置真的装了 OCP 转接适配板（base parts 含 OCP 件）或 OCP 槽带 defaults 时输出；
    # 仅“有 OCP 槽位”不算（ES220 V3 有 OCP 槽但未装板，历史回归多出 OCP 3.0 X8 行）。
    def _slot_has_defaults(slot: dict) -> bool:
        try:
            return bool((slot or {}).get("defaults"))
        except Exception:
            return False
    _has_ocp_part = any(
        "ocp" in _norm(f"{p.get('category') or ''} {p.get('name') or ''}")
        for p in (bc.get("parts") or [])
    )
    _has_ocp = _has_ocp_part or any(
        isinstance(s, dict) and _norm(str(s.get("name") or "")) == "ocp" and _slot_has_defaults(s)
        for s in _rear_slots
    )

    _cc = bc.get("config_content") or {}
    vars_ = {
        "form": bc.get("form") or "",
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
        # Cable 行按盘型分组（_cable_segments，用户定调 2026-09-17）
        "raid_model": _raid_model,
        "sata_count": drives["SATA"],
        "sas_count": drives["SAS"],
        "ocp_qty": 1 if _has_ocp else 0,
    }

    out = []
    for row in rows:
        rule = _rule_for_row(row, vars_.get("form"))
        label = row.get("label") or row.get("type") or ""
        desc = _eval_desc(rule, vars_, part_idx, row, gpu_qty, nvme_count)
        qty = _eval_qty(rule, vars_, part_idx, gpu_qty)
        # Cable 行：qty 恒 1，但没盘（描述空）→ 连 qty 一起清空整行隐藏（前端 evalBomContext 同口径）
        if (row.get("type") or "") == "cable" and not desc:
            qty = None
        if desc is None and qty is None:
            continue  # 全空行隐藏
        out.append({"catalogue": label, "description": desc or "", "qty": qty})
    return out


def _eval_desc(rule: dict, vars_: dict, part_idx: dict,
               row: dict, gpu_qty: int, nvme_count: int) -> Optional[str]:
    src = rule.get("desc") or {}
    val = _desc_from(src, vars_, part_idx, row, gpu_qty, nvme_count)
    if val not in (None, ""):
        return val
    fb = rule.get("desc_fallback")
    if fb:
        return _desc_from(fb, vars_, part_idx, row, gpu_qty, nvme_count) or None
    return None


def _desc_from(src, vars_, part_idx, row, gpu_qty, nvme_count) -> Optional[str]:
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
            # OCP 网络槽（独立分段，不占 PCIe）：desc 跟适配板默认（ocp_x8）走，与前端 defaultRearFrom 同口径；
            # 无 OCP 槽 → None（配合 qty ocp_qty=0 → 整行隐藏）
            if slot == "ocp":
                return "OCP 3.0 X8" if vars_.get("ocp_qty") else None
            _x16 = vars_.get("riser_x16")
            if gpu_qty > 0:
                return str(_x16) if _x16 else None
            if vars_.get("high_bw_nic") and slot == "io1":
                return str(_x16) if _x16 else None
            return _std_riser_for(vars_.get("standard_riser"), slot)
        if scope == "rear_all":
            parts = []
            if gpu_qty > 0:
                parts.append(f"{gpu_qty}*GPU")
            if nvme_count > 0:
                parts.append(f"{nvme_count}NVME")
            return "+".join(parts) or None
    if kind == "cable_groups":
        return _cable_segments(src.get("kinds"), vars_)
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
