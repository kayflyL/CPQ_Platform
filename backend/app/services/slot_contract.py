# -*- coding: utf-8 -*-
"""线索登记表 slot 契约与填充判定工具（agent_fill / model_reason / kp_reason 共用）。

slot_spec / slot_label / _missing_critical 是全链路字段契约的唯一来源：
理解(agent_fill)、选型(model_reason/kp_reason)、前端进度卡都按它对齐。
历史需求理解/反问节点已合并为 agent_fill，相关实现已删除。
"""

import logging
from typing import Any, Optional

from app.services.skill_node_state import (KP_ABSENT, KP_NODE, KP_PICKS, KP_ROW_IDS,
                                           add_row_answer, add_waived_rows)


logger = logging.getLogger(__name__)




def _row_identity_by_ref(kp_state: dict, ref: str) -> dict:
    """行引用（row_id）→ 身份字段 {origin,row_id,category,description,rev}。

    权威来源 = kp_reason 分区里的身份铸造台账（KP_ROW_IDS，P3-1 由引擎发布）。
    解析不到 → 空 dict（调用方退回旧键文本语义，兼容旧线程里未铸造的引用）。
    """
    r = str(ref or "").strip()
    if not r or not isinstance(kp_state, dict):
        return {}
    ids = kp_state.get(KP_ROW_IDS)
    if not isinstance(ids, dict):
        return {}
    for origin, rec in ids.items():
        if isinstance(rec, dict) and str(rec.get("row_id") or "") == r:
            return {"origin": str(origin), "row_id": r,
                    "category": str(rec.get("category") or ""),
                    "description": str(rec.get("description") or ""),
                    "rev": str(rec.get("rev") or "")}
    return {}


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

_REGISTRATION_CATS_CACHE: dict = {"at": 0.0, "cats": frozenset()}


def registration_owned_categories() -> frozenset:
    """「由线索登记表申报」的类目名集合（属主 = agent_fill）。

    事实来源 = 登记表部件槽（`slot_spec()` 里 `src_type == "kp"` 的 category），由
    `kp_slot_group_map` 配置合成：CPU / Memory / HDD/SSD / GPU / Raid card / NIC。
    未映射进登记表的大类（Bridge / HBA / NVSwitch）不在其中——它们才是「客户原话未覆盖、
    AI 判断要配」的类目，可以走 kp_reason 的 `cfg:` 声明行。

    用途（2026-09-12 归属收口）：kp_reason 的声明行（`skill_node_state.KP_CONFIG`）
    按定义只承载「客户原话未覆盖」的类目；已被登记表申报的类目若再声明一行，同一需求
    会拿到两条身份（`reg:CPU` 与 `cfg:CPU`），客户后补型号时旧行仍在 → 多一行、多问一轮。
    带 5 秒进程内缓存：`phase_kp_reason` 是热路径。
    """
    import time
    now = time.monotonic()
    cached = _REGISTRATION_CATS_CACHE.get("cats")
    if cached and now - float(_REGISTRATION_CATS_CACHE.get("at") or 0.0) < 5.0:
        return cached
    cats = frozenset(
        str(s.get("category") or "").strip()
        for s in slot_spec()
        if str(s.get("src_type") or "") == "kp" and str(s.get("category") or "").strip()
    )
    _REGISTRATION_CATS_CACHE["at"] = now
    _REGISTRATION_CATS_CACHE["cats"] = cats
    return cats



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


# 前提字段的目录维度：这些字段决定「库里有没有料」——配件适用性按系列过滤
# （part_selector._SeriesScopedRepo）。维度名取自字段契约的 catalog_dimension（字段配置可改），
# 这里不写任何字段名，也不写取值词表。要加宽/收窄前提面，改字段配置而不是改这个元组。
PREMISE_CATALOG_DIMENSIONS = ("series",)


def catalog_field_keys() -> set:
    """登记表里的目录字段 key 集合（candidate_source=catalog）——供「客户原话申报」校验。"""
    try:
        return {str(s.get("key") or "") for s in slot_spec()
                if str(s.get("candidate_source") or "") == "catalog"}
    except Exception:
        logger.exception("登记表字段契约读取失败")
        return set()


def unconfirmed_premise_fields(ext: dict) -> list:
    """「已填、但客户没说过」的前提字段（目录维度 = PREMISE_CATALOG_DIMENSIONS）。

    客户确认的口径只有两条，都留痕在 ext.confirmed_slots（值被改写即失效）：
      * 客户点选确认卡（含打字精确命中同一选项）→ 点击通道写入；
      * 大脑申报「这是客户原话」→ fill_requirement(customer_stated=[...]) 走同一把权威源。
    返回 [{key,label,value}]（按字段契约顺序）；空列表 = 没有未确认前提，可直接放行。
    """
    out: list = []
    spec = slot_spec()
    confirmed = ext.get("confirmed_slots") if isinstance(ext, dict) else None
    confirmed = confirmed if isinstance(confirmed, dict) else {}
    for s in spec:
        if str(s.get("catalog_dimension") or "").strip() not in PREMISE_CATALOG_DIMENSIONS:
            continue
        key = str(s.get("key") or "").strip()
        if not key:
            continue
        cur = canonical_get(ext, key)
        cur_s = "" if cur is None else str(cur).strip()
        if not cur_s:
            continue  # 还没填：属于「缺字段」，由缺字段闸门负责，不算前提未确认
        if str(confirmed.get(key) or "").strip() == cur_s:
            continue  # 客户确认过，且确认之后没被改写
        out.append({"key": key, "label": str(s.get("label") or key), "value": cur_s})
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
                           rules: Optional[dict] = None,
                           kp_state: Optional[dict] = None) -> list:
    """把结构化配件槽位（agent_fill LLM 契约输出 / 选项结构化直传载荷）合并进 ext，返回变更说明。

    与理解节点共用 llm_extract_enhance.merge_into_ext，保证「一句话能抽多槽」口径一致。
    本函数只做类型守卫与槽位合并——**不做任何自然语言解析**：语义理解归理解通道（LLM），
    选项点击归结构化直传（option.signal）。字符串形态的信号槽由理解通道负责结构化。
    kp_state：kp_reason 节点私有状态分区（节点隔离）；客户自选料/放弃类目/行补充回答
    都写在这里。**ext 是上游「线索登记表」冻结文档，本函数对它只读、绝不回填**。
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
        if row_key and answer and isinstance(kp_state, dict):
            # 客户回答只落本节点私有状态（行键 → 回答），登记表保持冻结：行键取自登记原文，
            # 所以补一句话不会让该行已锁定的选型失配作废（旧实现改描述=改键=丢选型）。
            known = {kp_row_key(r.get("part_category"), r.get("description"))
                     for r in (ext.get("kp_rows") or []) if isinstance(r, dict)}
            # P3-2：行引用可能是 row_id（引擎铸造身份）；身份台账就是权威的「这行存在」凭证。
            ident = _row_identity_by_ref(kp_state, row_key)
            if row_key in known or ident or not known:
                _bind = str(ident.get("row_id") or row_key)
                if add_row_answer({"node_state": {"kp_reason": kp_state}}, _bind, answer):
                    notes.append("部件行已按客户回答补充：" + answer)
    # 客户自选料（表单卡自选下拉/候选点选）：等价一次"客户手动 select_kp_parts"——
    # 直接写 ext.kp_picks（行键），引擎重跑时 apply_kp_picks 落行（同一通路+白盒断言）。
    pick = slots.get("kp_manual_pick")
    if isinstance(pick, dict):
        from app.services.part_selector import kp_row_key
        row_key = str(pick.get("row") or "").strip()
        name = str(pick.get("name") or "").strip()
        if row_key and name and isinstance(kp_state, dict):
            picks = dict(kp_state.get(KP_PICKS) or {})
            ident = _row_identity_by_ref(kp_state, row_key)
            entry = {**ident, "name": name,
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
            picks[str(ident.get("row_id") or row_key)] = entry
            kp_state[KP_PICKS] = picks
            notes.append("配件已登记：" + name + (f" ×{entry['qty']}" if entry.get("qty") else ""))
    # 必填类目的「不配/自备」逃生（如 GPU）：把该类目登记为缺席，不再兜底占位。
    absent = slots.get("kp_absent")
    if absent and isinstance(kp_state, dict):
        cur = [str(c).strip() for c in (kp_state.get(KP_ABSENT) or []) if str(c).strip()]
        for c in (absent if isinstance(absent, list) else [absent]):
            v = str(c or "").strip()
            if v and v not in cur:
                cur.append(v)
        kp_state[KP_ABSENT] = cur
        notes.append("客户放弃配置：" + "、".join(cur))
    # 客户已知悉「库内无料」仍选择保持原需求（kp_waived，行键）：行保留 + 标注，不再要求落地
    # 真实料号（终检放行）。与 kp_absent 的区别见 skill_node_state.KP_WAIVED。
    waived = slots.get("kp_waived")
    if waived and isinstance(kp_state, dict):
        ks = [str(k).strip() for k in (waived if isinstance(waived, list) else [waived]) if str(k).strip()]
        if add_waived_rows({"node_state": {KP_NODE: kp_state}}, ks):
            notes.append("客户已知悉库内无料、保持原需求：" + "、".join(ks))
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
