# -*- coding: utf-8 -*-
"""线索登记表 slot 契约与填充判定工具（agent_fill / model_reason / kp_reason 共用）。

slot_spec / slot_label / _missing_critical 是全链路字段契约的唯一来源：
理解(agent_fill)、选型(model_reason/kp_reason)、前端进度卡都按它对齐。
历史需求理解/反问节点已合并为 agent_fill，相关实现已删除。
"""

import logging
from typing import Any, Optional


logger = logging.getLogger(__name__)




def _default_candidate_source(key: str) -> str:
    """默认候选来源：类型/系列/形态/机型走目录白名单，其余自由输入。"""
    return "catalog" if key in ("server_type", "platform_type", "chassis_form", "server_model") else "free"


def _default_group(key: str) -> str:
    """默认分组：基本信息/部件（进度卡按此分组，配置可覆盖）。"""
    return "基本信息" if key in ("server_type", "server_model", "platform_type", "chassis_form",
                                 "purchase_qty", "warranty_years") else "部件"


# ── 唯一真值源：canonical ext 字段 → 历史别名（只在此处维护，禁止散落双写）────────
# 规则：AI 角色只读写 canonical 字段；旧别名仅在过渡期读取时兜底，写入时一律清除别名。
CANONICAL_ALIASES: dict[str, list[str]] = {
    "server_type": ["server_type_name", "usage", "scene"],
    "platform_type": ["series"],
    "chassis_form": ["form"],
    "server_model": ["model", "baseline_model"],
    "purchase_qty": ["n", "qty", "quantity"],
}


def canonical_key(key: str) -> str:
    """把任意槽位 key 归一为 canonical ext 字段名。"""
    key = (key or "").strip()
    if not key:
        return key
    if key in CANONICAL_ALIASES:
        return key
    for canon, aliases in CANONICAL_ALIASES.items():
        if key in aliases:
            return canon
    return key


def _canonical_present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    if isinstance(v, (list, dict)) and not v:
        return False
    return True


def canonical_get(ext: dict, key: str):
    """按 canonical 口径读取：先读 canonical，再退历史别名（过渡期兼容）。"""
    if not isinstance(ext, dict):
        return None
    canon = canonical_key(key)
    v = ext.get(canon)
    if _canonical_present(v):
        return v
    for alias in CANONICAL_ALIASES.get(canon, []):
        v = ext.get(alias)
        if _canonical_present(v):
            return v
    return None


def canonical_set(ext: dict, key: str, value) -> None:
    """写 canonical 字段，不再投影历史别名（消除口径双写）。

    读取走 canonical_get（保留别名兜底读旧数据）；写入统一只落 canonical。
    """
    if not isinstance(ext, dict):
        return
    canon = canonical_key(key)
    ext[canon] = value


_FORM_LABEL_CACHE: dict = {"at": 0.0, "map": {}}


def _form_field_labels() -> dict:
    """表单定义（requirement_sheet_form）是字段中文名的唯一权威：商机详情页真实表单与
    agent_fill 目标层都消费它。缺失/为空返回空 dict（不回退任何代码词表）。
    带 5 秒进程内缓存：slot_spec 是热路径，避免每轮多次查库。"""
    import time
    now = time.monotonic()
    if now - _FORM_LABEL_CACHE["at"] < 5.0:
        return _FORM_LABEL_CACHE["map"]
    labels: dict = {}
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        cfg = SystemConfigRepository().get_value("requirement_sheet_form") or {}
        for f in (cfg.get("config_fields") or []):
            if isinstance(f, dict) and f.get("key") and f.get("label"):
                labels[str(f["key"])] = str(f["label"])
    except Exception:
        logger.exception("读取表单定义标签失败")
    _FORM_LABEL_CACHE["at"] = now
    _FORM_LABEL_CACHE["map"] = labels
    return labels


def slot_spec() -> list:
    """线索登记表字段契约（唯一权威源 = system_config.requirement_slots 基本信息 + KP 大类动态部件）。

    这是全链路「要填哪些字段 / 反问问哪些」的唯一来源：理解节点、反问节点、前端进度卡都按它对齐。
    每项含 key/label/level/group/candidate_source/src_type/order（部件槽位无 level，按 L2 系统推导处理）。
    部件字段不再写死在 requirement_slots，改由 KP 大类动态合成（见 requirement_slots.combined_slot_spec）。
    字段中文名以表单定义（requirement_sheet_form）为权威：商机详情页真实表单与 AI 契约共用一套词。
    """
    try:
        from app.services.requirement_slots import combined_slot_spec
        out = combined_slot_spec() or []
    except Exception:
        return []
    labels = _form_field_labels()
    if labels:
        for s in out:
            k = str(s.get("key") or "")
            if k in labels:
                s["label"] = labels[k]
    return out


def slot_label(key: str) -> str:
    """按 slot key 取中文标签（前端进度卡/反问文案共用）。"""
    key = (key or "").strip()
    for s in slot_spec():
        if s.get("key") == key:
            return str(s.get("label") or key)
    return key


def _slot_filled(ext: dict, key: str) -> bool:
    """按 ext 结构判断某个 slot 是否已被理解/确认填上。"""
    from app.services import semantic_contract as _sc
    if _sc.absent_confirmed(ext, key):
        return True
    def _has(v) -> bool:
        if v is None or v is False:
            return False
        if isinstance(v, str):
            return v.strip() != ""
        if isinstance(v, (int, float)):
            return v > 0
        if isinstance(v, dict):
            return any(_has(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return any(_has(x) for x in v)
        return bool(v)
    if key in CANONICAL_ALIASES or any(key in aliases for aliases in CANONICAL_ALIASES.values()):
        return _has(canonical_get(ext, key))
    mapping = {
        "cpu": ["cpu"],
        "memory": ["memory"],
        "storage": ["storage"],
        "gpu": ["gpu"],
        "nic": ["nic"],
        "raid": ["raid"],
        "psu": ["psu"],
    }
    return any(_has(ext.get(k)) for k in mapping.get(key, []))


def _missing_critical(ext: dict) -> list:
    """缺哪些关键字段（供反问/进度卡用）——返回线索登记契约的 slot key，与前端字段一致。

    按字段契约的 level 驱动：L0 缺了必问；L1 提示可补；L2 系统推导；
    类型或「系列+形态」至少要有一个（否则无法选型）。
    """
    spec = slot_spec()
    has_type = bool(canonical_get(ext, "server_type"))
    has_series_form = bool(canonical_get(ext, "platform_type") and canonical_get(ext, "chassis_form"))
    from app.services import semantic_contract as _sc
    miss = []
    for s in spec:
        key = s["key"]
        if key == "server_type" and has_series_form and not has_type:
            continue
        if _slot_filled(ext, key):
            continue
        if _sc.absent_confirmed(ext, key):
            continue
        if s.get("level", "L2") != "L0":
            continue
        miss.append(key)
    return miss


# ── 配件结构化槽位落位（2026-09-07 自 slot_extractor 并入，避免单一 slot 契约散落成多文件）──
_STRUCTURED_KEYS = {"cpu", "memory", "storage", "gpu", "nic", "raid", "psu"}


def _as_dicts(value: Any) -> list[dict]:
    """类型守卫：只收对象形态；字符串/标量不解析（语义归 LLM/选项直传），直接丢弃。"""
    if isinstance(value, list):
        return [x for x in value[:16] if isinstance(x, dict)]
    return [value] if isinstance(value, dict) else []


def apply_structured_slots(ext: dict, slots: dict, requirement_text: str = "",
                           rules: Optional[dict] = None) -> list:
    """把结构化配件槽位（agent_fill LLM 契约输出 / 选项结构化直传载荷）合并进 ext，返回变更说明。

    与理解节点共用 llm_extract_enhance.merge_into_ext，保证「一句话能抽多槽」口径一致。
    本函数只做类型守卫与槽位合并——**不做任何自然语言解析**：语义理解归理解通道（LLM），
    选项点击归结构化直传（option.signal）。字符串形态的信号槽由理解通道负责结构化。
    """
    if not isinstance(slots, dict):
        return []
    from app.services.llm_extract_enhance import merge_into_ext

    notes: list = []
    # 大脑提问卡的行绑定答案（ask_user row + 点击直传）：把答案合入该行描述。
    # 行键=类目|描述，描述变了键即失配 → 该行旧 pick 自动作废，引擎重跑重选。
    merge = slots.get("kp_row_merge")
    if isinstance(merge, dict):
        from app.services.part_selector import kp_row_key
        row_key = str(merge.get("row") or "").strip()
        answer = str(merge.get("answer") or "").strip()
        if row_key and answer:
            for r in (ext.get("kp_rows") or []):
                if not isinstance(r, dict):
                    continue
                if kp_row_key(r.get("part_category"), r.get("description")) == row_key:
                    new_desc = f"{str(r.get('description') or '').strip()} {answer}".strip()
                    if new_desc != str(r.get("description") or ""):
                        r["description"] = new_desc
                        notes.append("部件行已按客户回答更新：" + new_desc)
                    break
    # 客户自选料（表单卡自选下拉/候选点选）：等价一次"客户手动 select_kp_parts"——
    # 直接写 ext.kp_picks（行键），引擎重跑时 apply_kp_picks 落行（同一通路+白盒断言）。
    pick = slots.get("kp_manual_pick")
    if isinstance(pick, dict):
        from app.services.part_selector import kp_row_key
        row_key = str(pick.get("row") or "").strip()
        name = str(pick.get("name") or "").strip()
        if row_key and name:
            picks = dict(ext.get("kp_picks") or {})
            entry = {"name": name,
                     "part_id": str(pick.get("part_id") or ""),
                     "price": pick.get("price"),
                     "currency": str(pick.get("currency") or "RMB"),
                     "reason": str(pick.get("reason") or "客户自选")}
            try:
                q = int(pick.get("qty"))
                if q >= 1:
                    entry["qty"] = q
            except (TypeError, ValueError):
                pass
            picks[row_key] = entry
            ext["kp_picks"] = picks
            notes.append("配件已登记：" + name + (f" ×{entry['qty']}" if entry.get("qty") else ""))
    # 必须反问类目的「不配/自备」逃生（如 GPU）：把该类目登记为缺席，不再兜底占位。
    absent = slots.get("kp_absent")
    if absent:
        cur = [str(c).strip() for c in (ext.get("kp_absent") or []) if str(c).strip()]
        for c in (absent if isinstance(absent, list) else [absent]):
            v = str(c or "").strip()
            if v and v not in cur:
                cur.append(v)
        ext["kp_absent"] = cur
        notes.append("客户放弃配置：" + "、".join(cur))
    cleaned: dict[str, Any] = {}
    for key in _STRUCTURED_KEYS:
        if key not in slots:
            continue
        val = _as_dicts(slots[key])
        if not val:
            continue
        cleaned[key] = val if key in ("storage", "gpu", "nic", "raid") else val[0]
    if not cleaned:
        return notes
    return notes + merge_into_ext(ext, cleaned, requirement_text or "", rules=rules)
