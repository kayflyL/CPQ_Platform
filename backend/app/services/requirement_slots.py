# -*- coding: utf-8 -*-
"""需求槽位契约（RequirementSlots）—— LLM 主理解节点 llm_understand 的输入/输出契约。

背景（2026-08 需求分析 LLM 重构，P1）：
  - 旧「extract/scene/review 三处散装 LLM 增强」默认关闭、规则赢、只补缺 → 典型需求
    规则已抽全 → LLM 永不改变结果（用户实测"接了和没接一样"）。
  - 新方案：LLM 收拢为单一主理解节点，输出统一 RequirementSlots 契约（槽位 + 置信度 +
    证据 + 预算 + 意图摘要 + 缺失项 + 追问），配合目录上下文（在售类型/机型/系列/型号家族
    词表，实时 DB 检索）做语义校验，只许从白名单选、选不出写 null、禁编料号。

本模块职责（纯函数为主，全部可单测）：
  1) build_catalog_context() —— 目录白名单（在售类型/机型/系列/形态/型号家族词/期望槽位）；
  2) LLM_UNDERSTAND_SCHEMA —— 槽位契约 JSON-schema（llm_client.chat_json 收口用）；
  3) validate_slots() —— 语义校验（白名单 + 数量合理 + 覆盖度/置信度矛盾检测）；
  4) apply_llm_merge() —— 契约确定性合并进 ext（规则赢、只补缺，复用 merge_into_ext）；
  5) compute_coverage() —— 槽位覆盖度（clarity_check 主判据，P2 正式接入，P1 先产出）；
  6) validate_pipeline_slots() —— slot_validate 节点：最终业务语义闸门 + 冲突/低置信度收集。

铁律（对齐 llm_extract_enhance）：LLM 输出绝不裸进 match_kp/compose；任何失败静默降级。
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 机箱形态白名单（与 extract 形态词表一致）
FORM_WHITELIST = ["1U", "2U", "4U", "5U", "6U", "8U"]

# 期望槽位兜底（权威源 = system_config.requirement_slots；读失败用，与 seed 一致）
_FALLBACK_SLOTS = [
    {"key": "scene", "label": "应用场景", "level": "L0"},
    {"key": "series", "label": "所属系列", "level": "L0"},
    {"key": "cpu", "label": "CPU", "level": "L0"},
    {"key": "memory", "label": "内存", "level": "L0"},
    {"key": "storage", "label": "存储", "level": "L0", "default_ok": True},
    {"key": "form", "label": "机箱形态", "level": "L1"},
    {"key": "gpu", "label": "GPU", "level": "L1"},
    {"key": "nic", "label": "网卡", "level": "L1"},
    {"key": "raid", "label": "阵列卡", "level": "L2"},
    {"key": "psu", "label": "电源", "level": "L2"},
]

# 数量合理性范围（与 llm_extract_enhance.merge_into_ext 的确定性闸门一致）
_QTY_RANGES = {
    "cpu.qty": (1, 64),
    "memory.qty": (1, 64),
    "memory.per_stick_gb": (4, 1024),
    "storage.qty": (1, 64),
    "gpu.qty": (1, 64),
    "nic.speed_g": (1, 400),
    "nic.ports": (1, 64),
    "nic.qty": (1, 64),
    "psu.wattage": (200, 3000),
    "psu.qty": (1, 8),
    "raid.qty": (1, 64),
}


# ── 1. 目录上下文（实时 DB 检索 → 白名单）────────────────────────────────
def build_catalog_context() -> dict:
    """构建目录白名单上下文：在售类型/机型/系列/形态/型号家族词/期望槽位。

    任何 DB 读取失败都降级（绝不阻塞）：类型/机型为空、系列/槽位用兜底常量。
    """
    ctx: dict = {
        "server_types": [],
        "models_by_type": {},
        "series": [],
        "forms": list(FORM_WHITELIST),
        "family_words": {},
        "slots_spec": [],
        "source": "db",
    }
    try:
        from app.services.catalog_guide import load_catalog
        types, models_by_type = load_catalog()
        ctx["server_types"] = [str(t.get("name") or "") for t in (types or []) if t.get("name")]
        ctx["models_by_type"] = {
            str(tn): [str(m.get("name") or "") for m in (ms or []) if m.get("name")]
            for tn, ms in (models_by_type or {}).items()
        }
    except Exception as e:
        logger.warning("读目录上下文失败（类型/机型），降级: %s", e)
        ctx["source"] = "fallback"
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            series = repo.get_value("server_series", [])
            if isinstance(series, list):
                vals = [str(s.get("value")) for s in series
                        if isinstance(s, dict) and s.get("value")]
                if vals:
                    ctx["series"] = vals
            fw = repo.get_value("model_family_words", {})
            if isinstance(fw, dict) and fw:
                ctx["family_words"] = fw
            slots_cfg = repo.get_value("requirement_slots", {})
            if isinstance(slots_cfg, dict) and slots_cfg.get("slots"):
                ctx["slots_spec"] = slots_cfg["slots"]
        finally:
            repo.close()
    except Exception as e:
        logger.warning("读目录上下文失败（系列/词表/槽位），降级: %s", e)
    if not ctx["series"]:
        ctx["series"] = ["Orion", "Polaris", "Intel", "工作站"]
    if not ctx["slots_spec"]:
        ctx["slots_spec"] = list(_FALLBACK_SLOTS)
    return ctx


def _catalog_summary(catalog: dict) -> dict:
    """payload 展示用的精简目录摘要（不全量塞机型）。"""
    return {
        "type_count": len(catalog.get("server_types") or []),
        "model_count": sum(len(v) for v in (catalog.get("models_by_type") or {}).values()),
        "types": catalog.get("server_types") or [],
        "series": catalog.get("series") or [],
        "forms": catalog.get("forms") or [],
    }


# ── 2. 槽位契约 schema（chat_json 收口用）────────────────────────────────
# 每个槽位对象带 value/confidence/source/evidence（白盒：来源与证据可解释）。
_SLOT_VALUE: dict = {
    "type": "object",
    "properties": {
        "value": {"type": ["string", "integer", "number"]},
        "confidence": {"type": "number"},
        "source": {"type": "string", "enum": ["text", "catalog", "infer"]},
        "evidence": {"type": "string"},
    },
}

LLM_UNDERSTAND_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "server_type": _SLOT_VALUE,   # value = 在售类型名（目录白名单）
        "series": _SLOT_VALUE,        # value = 系列（Orion/Polaris/Intel/工作站）
        "form": _SLOT_VALUE,          # value = 1U/2U/4U/5U/6U/8U
        "cpu": {"type": "object", "properties": {
            "model": {"type": "string"}, "qty": {"type": "integer"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }},
        "memory": {"type": "object", "properties": {
            "per_stick_gb": {"type": "integer"}, "qty": {"type": "integer"},
            "type": {"type": "string"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }},
        "storage": {"type": "array", "items": {"type": "object", "properties": {
            "capacity": {"type": "string"}, "capacity_gb": {"type": "integer"},
            "interface": {"type": "string", "enum": ["SATA", "SAS", "NVMe", "U.2", "U.3"]},
            "qty": {"type": "integer"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }}},
        "gpu": {"type": "array", "items": {"type": "object", "properties": {
            "model": {"type": "string"}, "qty": {"type": "integer"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }}},
        "nic": {"type": "array", "items": {"type": "object", "properties": {
            "model": {"type": "string"}, "speed_g": {"type": "integer"},
            "ports": {"type": "integer"}, "qty": {"type": "integer"},
            "with_optical_module": {"type": "boolean"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }}},
        "psu": {"type": "object", "properties": {
            "wattage": {"type": "integer"}, "qty": {"type": "integer"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }},
        "raid": {"type": "object", "properties": {
            "model": {"type": "string"}, "qty": {"type": "integer"},
            "confidence": {"type": "number"}, "source": {"type": "string"},
            "evidence": {"type": "string"},
        }},
        "budget": _SLOT_VALUE,        # value = 预算金额（元，数字）
        "intent_summary": {"type": "string"},
        "missing": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
}

# 槽位 key（不含 intent_summary/missing/questions 元信息）
SLOT_KEYS = ["server_type", "series", "form", "cpu", "memory", "storage",
             "gpu", "nic", "psu", "raid", "budget"]


def _slot_value(data: dict, key: str):
    """取槽位对象里的 value（字符串型槽位用）。"""
    slot = data.get(key) if isinstance(data, dict) else None
    if isinstance(slot, dict):
        return slot.get("value")
    return slot


# ── 3. 语义校验（白名单 + 数量合理 + 覆盖度/置信度矛盾）──────────────────
def _iter_models(data: dict):
    """遍历契约里的型号字段：(path, model)。"""
    cpu = data.get("cpu") if isinstance(data, dict) else None
    if isinstance(cpu, dict) and cpu.get("model"):
        yield "cpu.model", str(cpu["model"]).strip()
    for i, g in enumerate(data.get("gpu") or []):
        if isinstance(g, dict) and g.get("model"):
            yield f"gpu[{i}].model", str(g["model"]).strip()
    for i, n in enumerate(data.get("nic") or []):
        if isinstance(n, dict) and n.get("model"):
            yield f"nic[{i}].model", str(n["model"]).strip()
    raid = data.get("raid") if isinstance(data, dict) else None
    if isinstance(raid, dict) and raid.get("model"):
        yield "raid.model", str(raid["model"]).strip()


def _model_grounded(model: str, requirement_text: str, catalog: dict) -> bool:
    """型号接地判定：命中型号家族词 / 型号 token 出现在需求原文 / 出现在目录机型名。
    三者都不沾 → 疑似编造料号（禁）。
    """
    low = (model or "").strip().lower()
    if not low:
        return True
    for kws in (catalog.get("family_words") or {}).values():
        for kw in (kws or []):
            if kw and kw.lower() in low:
                return True
    from app.services.llm_extract_enhance import _model_tokens_of
    text_low = (requirement_text or "").lower()
    for tok in _model_tokens_of(model):
        if tok.lower() in text_low:
            return True
    for ms in (catalog.get("models_by_type") or {}).values():
        for m in (ms or []):
            mn = str(m or "").lower()
            if mn and (low == mn or low in mn):
                return True
    return False


def _check_qty_ranges(data: dict, errors: list) -> None:
    """数量合理性（硬性越界 → 校验错误，喂回 LLM 重试）。"""
    def _check(path: str, val) -> None:
        if val is None:
            return
        lo, hi = _QTY_RANGES[path]
        try:
            v = int(val)
        except (TypeError, ValueError):
            errors.append(f"{path} 必须是整数（当前 {val}）")
            return
        if not (lo <= v <= hi):
            errors.append(f"{path} 超出合理范围（{lo}~{hi}，当前 {v}）")

    cpu = data.get("cpu") if isinstance(data, dict) else {}
    if isinstance(cpu, dict):
        _check("cpu.qty", cpu.get("qty"))
    mem = data.get("memory") if isinstance(data, dict) else {}
    if isinstance(mem, dict):
        _check("memory.qty", mem.get("qty"))
        _check("memory.per_stick_gb", mem.get("per_stick_gb"))
    for i, d in enumerate(data.get("storage") or []):
        if isinstance(d, dict):
            _check(f"storage[{i}].qty", d.get("qty"))
    for i, g in enumerate(data.get("gpu") or []):
        if isinstance(g, dict):
            _check(f"gpu[{i}].qty", g.get("qty"))
    for i, n in enumerate(data.get("nic") or []):
        if isinstance(n, dict):
            _check(f"nic[{i}].speed_g", n.get("speed_g"))
            _check(f"nic[{i}].ports", n.get("ports"))
            _check(f"nic[{i}].qty", n.get("qty"))
    psu = data.get("psu") if isinstance(data, dict) else {}
    if isinstance(psu, dict):
        _check("psu.wattage", psu.get("wattage"))
        _check("psu.qty", psu.get("qty"))
    raid = data.get("raid") if isinstance(data, dict) else {}
    if isinstance(raid, dict):
        _check("raid.qty", raid.get("qty"))


def validate_slots(data: dict, catalog: dict, requirement_text: str = "") -> tuple:
    """语义校验（schema 收口之后的第二道闸门）。

    返回 (errors, warnings)：
      errors —— 硬错误（白名单外/编造型号/数量越界）：带具体错误喂回 LLM 重试；
      warnings —— 软告警（覆盖度 vs 置信度矛盾等）：记录不重试。
    """
    errors: list = []
    warnings: list = []
    if not isinstance(data, dict):
        return ["LLM 输出不是 JSON 对象"], []
    catalog = catalog or {}

    # 白名单校验：系列 / 形态 / 服务器类型
    series = _slot_value(data, "series")
    if series:
        known = {str(s).lower() for s in (catalog.get("series") or [])}
        if str(series).lower() not in known:
            errors.append(
                f"系列「{series}」不在在售系列白名单（{'/'.join(catalog.get('series') or []) or '无'}），"
                f"请只从白名单选或留 null")
    form = _slot_value(data, "form")
    if form:
        f = str(form).strip().upper()
        if f not in (catalog.get("forms") or []):
            errors.append(
                f"形态「{form}」不在机箱形态白名单（{'/'.join(catalog.get('forms') or [])}），"
                f"请只从白名单选或留 null")
    server_type = _slot_value(data, "server_type")
    if server_type:
        known_types = {str(t) for t in (catalog.get("server_types") or [])}
        if str(server_type) not in known_types:
            errors.append(
                f"服务器类型「{server_type}」不在在售类型白名单（{'/'.join(sorted(known_types)) or '无'}），"
                f"请只从白名单选或留 null")

    # 型号接地：禁编料号
    for path, model in _iter_models(data):
        if not _model_grounded(model, requirement_text, catalog):
            errors.append(
                f"{path}=「{model}」未在需求原文出现、也未命中目录型号家族词表，"
                f"疑似编造料号，请改为需求中出现的型号或留 null")

    # 数量合理性
    _check_qty_ranges(data, errors)

    # 覆盖度 vs 置信度矛盾（软告警）
    cov = compute_coverage(data, catalog)
    confs = _collect_confidences(data)
    if cov.get("total") and confs:
        ratio = cov.get("filled", 0) / cov["total"]
        avg = sum(confs) / len(confs)
        if ratio >= 0.6 and avg < 0.5:
            warnings.append("槽位覆盖度高但平均置信度低（矛盾），建议人工确认后再出方案")
        elif ratio <= 0.3 and avg >= 0.9:
            warnings.append("槽位覆盖度低但置信度普遍很高（矛盾），可能存在过度自信，建议核对")

    return errors, warnings


def _collect_confidences(data: dict) -> list:
    out: list = []
    for key in SLOT_KEYS:
        v = data.get(key)
        if isinstance(v, dict) and v.get("confidence") is not None:
            try:
                out.append(float(v["confidence"]))
            except (TypeError, ValueError):
                pass
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and it.get("confidence") is not None:
                    try:
                        out.append(float(it["confidence"]))
                    except (TypeError, ValueError):
                        pass
    return out


# ── 4. 覆盖度（clarity 主判据，P2 正式接入；P1 先产出给 llm_understand 展示）──
def _slot_filled(data: dict, key: str) -> bool:
    """槽位是否已填：_SLOT_VALUE 对象看 value；扁平对象（cpu/memory/psu/raid）看业务字段。"""
    k = "server_type" if key == "scene" else key
    v = data.get(k)
    if isinstance(v, dict):
        if "value" in v:
            val = v["value"]
            if isinstance(val, str):
                return bool(val.strip())
            return val is not None
        # 扁平槽位：任一业务字段有值即视为已填
        return any(v.get(f) is not None for f in ("model", "qty", "per_stick_gb", "type", "wattage"))
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, str):
        return bool(v.strip())
    return v is not None


def compute_coverage(data: dict, catalog: Optional[dict] = None) -> dict:
    """期望槽位清单（system_config.requirement_slots）上的覆盖度明细。"""
    spec = (catalog or {}).get("slots_spec") or list(_FALLBACK_SLOTS)
    data = data or {}
    detail = []
    missing_l0 = []
    for s in spec:
        key = s.get("key")
        filled = _slot_filled(data, key)
        label = s.get("label") or key
        detail.append({"key": key, "label": label, "level": s.get("level"), "filled": filled})
        if not filled and not s.get("default_ok") and s.get("level") == "L0":
            missing_l0.append(label)
    filled = sum(1 for d in detail if d["filled"])
    total = len(detail)
    missing = [d["label"] for d in detail if not d["filled"]]
    by_level: dict = {}
    for d in detail:
        lv = d.get("level") or "?"
        by_level.setdefault(lv, {"filled": 0, "total": 0})
        by_level[lv]["total"] += 1
        if d["filled"]:
            by_level[lv]["filled"] += 1
    return {
        "filled": filled,
        "total": total,
        "coverage_ratio": round(filled / total, 2) if total else 0.0,
        "missing": missing,
        "missing_l0": missing_l0,
        "by_level": by_level,
        "slots": detail,
    }


# ── 5. 契约 → EXTRACT_ENHANCE_SCHEMA 形状 + 确定性合并 ───────────────────
def slots_to_enhance(data: dict) -> dict:
    """把 RequirementSlots 契约翻译成 llm_extract_enhance.EXTRACT_ENHANCE_SCHEMA 形状。

    只带业务值（去 confidence/source/evidence 元数据），交给 merge_into_ext 合并。
    """
    data = data or {}
    out: dict = {}
    form = _slot_value(data, "form")
    if form:
        out["form"] = str(form).strip().upper()
    series = _slot_value(data, "series")
    if series:
        out["series"] = str(series).strip()

    cpu = data.get("cpu") if isinstance(data, dict) else None
    if isinstance(cpu, dict):
        c = {k: cpu[k] for k in ("model", "qty", "cores", "tdp_w") if cpu.get(k) is not None}
        if c:
            out["cpu"] = c
    mem = data.get("memory") if isinstance(data, dict) else None
    if isinstance(mem, dict):
        m = {k: mem[k] for k in ("per_stick_gb", "qty", "type", "speed_mt") if mem.get(k) is not None}
        if m:
            out["memory"] = m
    drives = []
    for d in (data.get("storage") or [])[:16]:
        if not isinstance(d, dict):
            continue
        row = {k: d[k] for k in ("capacity", "capacity_gb", "interface", "qty") if d.get(k) is not None}
        if row:
            drives.append(row)
    if drives:
        out["drives"] = drives
    gpus = []
    for g in (data.get("gpu") or [])[:8]:
        if not isinstance(g, dict):
            continue
        row = {k: g[k] for k in ("model", "qty") if g.get(k) is not None}
        if row:
            gpus.append(row)
    if gpus:
        out["gpu"] = gpus
    nics = []
    for n in (data.get("nic") or [])[:8]:
        if not isinstance(n, dict):
            continue
        row = {k: n[k] for k in ("model", "speed_g", "ports", "qty", "with_optical_module") if n.get(k) is not None}
        if row:
            nics.append(row)
    if nics:
        out["nic"] = nics
    psu = data.get("psu") if isinstance(data, dict) else None
    if isinstance(psu, dict):
        p = {k: psu[k] for k in ("wattage", "qty") if psu.get(k) is not None}
        if p:
            out["psu"] = p
    raid = data.get("raid") if isinstance(data, dict) else None
    if isinstance(raid, dict):
        r = {k: raid[k] for k in ("model", "qty") if raid.get(k) is not None}
        if r:
            out["raid"] = r
    return out


def apply_llm_merge(ext: dict, data: dict, requirement_text: str = "", catalog: Optional[dict] = None) -> list:
    """把 LLM 契约确定性合并进 ext（就地修改，规则赢、只补缺）。

    返回变更说明列表（payload/日志用）。任何异常都不抛：合并失败静默（规则兜底）。
    """
    changes: list = []
    try:
        from app.services.llm_extract_enhance import merge_into_ext
        enhance = slots_to_enhance(data)
        changes += merge_into_ext(ext, enhance, requirement_text or "")
    except Exception as e:
        logger.warning("LLM 槽位合并失败（保持规则结果）: %s", e)
        return changes
    # server_type（在售类型白名单）——规则没抽到才补
    try:
        st = _slot_value(data, "server_type")
        if st and not ext.get("server_type_name"):
            known = {str(t) for t in (catalog or {}).get("server_types") or []}
            if str(st) in known:
                ext["server_type_name"] = str(st)
                changes.append(f"server_type={st}")
    except Exception as e:
        logger.warning("server_type 合并失败: %s", e)
    # budget（数值 > 0）——规则/上下文没给才补
    try:
        bv = _slot_value(data, "budget")
        if bv is not None and not ext.get("budget"):
            b = float(bv)
            if b > 0:
                ext["budget"] = b
                changes.append(f"budget={b:g}")
    except (TypeError, ValueError):
        pass
    return list(dict.fromkeys(changes))


def apply_confirm_decisions(ext: dict, items: list, decisions: dict) -> list:
    """按用户决策应用 LLM 确认项（confirm 节点，P2）。

    策略：默认采纳 LLM 补充项（accept）；用户可改为 ignore → 回规则值或清空。
    返回实际应用明细（写 requirement_samples 反馈闭环用）。
    """
    ext = ext or {}
    applied: list = []
    for it in items or []:
        iid = it.get("id")
        dec = (decisions or {}).get(iid, it.get("default") or "accept")
        slot = it.get("slot")
        llm_v = it.get("llm")
        rule_v = it.get("rule")
        ext_key = {"server_type": "server_type_name"}.get(slot, slot)
        if dec == "ignore":
            # 忽略 LLM 补充：回规则值（冲突项）或清空（纯 LLM 推断项）
            if rule_v is not None:
                ext[ext_key] = rule_v
            else:
                ext[ext_key] = None
            applied.append({"id": iid, "slot": slot, "label": it.get("label"),
                            "decision": "ignore", "value": rule_v})
        else:
            if llm_v is not None:
                ext[ext_key] = llm_v
                applied.append({"id": iid, "slot": slot, "label": it.get("label"),
                                "decision": "accept", "value": llm_v})
            elif rule_v is not None:
                ext[ext_key] = rule_v
                applied.append({"id": iid, "slot": slot, "label": it.get("label"),
                                "decision": "accept", "value": rule_v})
    return applied


# ── 6. slot_validate 节点：最终业务语义闸门 ──────────────────────────────
def validate_pipeline_slots(ext: dict, llm_slots: dict, requirement_text: str = "",
                            config: Optional[dict] = None) -> dict:
    """slot_validate 节点：结构 + 业务语义的最终确定性闸门。

    - 规则抽出的系列/形态/类型若不在在售白名单 → 丢弃并记 issues（防脏值进选型）；
    - LLM 与规则同槽位不一致 / LLM 低置信度项 → confirm_items（P2 confirm 面板消费）；
    - 覆盖度明细（clarity_check P2 主判据的输入）。
    """
    catalog = build_catalog_context()
    ext = ext or {}
    llm_slots = llm_slots or {}
    issues: list = []
    confirm_items: list = []

    # 白名单闸门（规则值也可能抽错，比如 CPU 系列号被误当机型系列）
    series = ext.get("series")
    if series and str(series) not in {str(s) for s in catalog.get("series") or []}:
        issues.append(f"规则抽取系列「{series}」不在在售白名单，已丢弃")
        ext["series"] = None
    form = ext.get("form")
    if form and str(form).strip().upper() not in (catalog.get("forms") or []):
        issues.append(f"规则抽取形态「{form}」不在白名单，已丢弃")
        ext["form"] = None
    server_type = ext.get("server_type_name")
    if server_type and str(server_type) not in {str(t) for t in catalog.get("server_types") or []}:
        issues.append(f"规则抽取类型「{server_type}」不在在售白名单，已丢弃")
        ext["server_type_name"] = None

    # LLM vs 规则冲突 / 低置信度 → 人工确认项（P2 confirm 面板）
    for key, label, ext_key in (("series", "系列", "series"),
                                ("form", "形态", "form"),
                                ("server_type", "服务器类型", "server_type_name")):
        rule_v = ext.get(ext_key)
        llm_v = _slot_value(llm_slots, key)
        if rule_v and llm_v and str(rule_v) != str(llm_v):
            confirm_items.append({"id": f"cf_{key}", "slot": key, "label": label,
                                  "rule": str(rule_v), "llm": str(llm_v), "level": "conflict",
                                  "default": "accept"})
        slot = llm_slots.get(key) if isinstance(llm_slots, dict) else None
        if isinstance(slot, dict) and slot.get("value") and slot.get("confidence") is not None:
            try:
                if float(slot["confidence"]) < 0.5:
                    confirm_items.append({"id": f"cf_{key}", "slot": key, "label": label,
                                          "rule": None, "llm": str(slot["value"]),
                                          "level": "low_confidence", "confidence": float(slot["confidence"]),
                                          "default": "accept"})
            except (TypeError, ValueError):
                pass

    coverage = compute_coverage(llm_slots, catalog) if llm_slots else compute_coverage(ext, None)
    hard_conflicts = [it for it in confirm_items if it.get("level") == "conflict"]
    return {
        "ok": not issues and not hard_conflicts,
        "issues": issues,
        "confirm_items": confirm_items[:10],
        "coverage": coverage,
        "catalog_count": {"types": len(catalog.get("server_types") or []),
                          "models": sum(len(v) for v in (catalog.get("models_by_type") or {}).values())},
        "catalog": _catalog_summary(catalog),
    }
