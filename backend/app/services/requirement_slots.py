# -*- coding: utf-8 -*-
"""需求槽位契约（RequirementSlots）—— 线索登记表（抽屉表）的动态槽位清单唯一来源。

只负责动态合成登记表的基本信息 + KP 部件大类槽位（combined_slot_spec），
以及前端映射下拉（slot_map_options）。
旧扁平键契约（build_catalog_context / LLM_UNDERSTAND_SCHEMA / validate_slots /
compute_coverage / apply_llm_merge / validate_pipeline_slots）已随「唯一登记表」重构删除。
"""

# 部件展示名/映射目标字段全部由 DB 同源派生：类别名 = kp_categories.name（即 Catalogue 下拉值），
# 归一 key = kp_slot_group_map[key]；不在此处写死任何词表/标签，避免第二套白名单。


def slot_map_options() -> list:
    """部件映射目标字段可选全集（含「不映射」哨兵），由 KP 大类 + kp_slot_group_map 动态合成。"""
    opts = [{"value": s.get("key"), "label": s.get("label")} for s in _load_kp_slots()]
    return opts + [{"value": "free", "label": "不映射（自由行）"}]


_BASIC_KEYS = {"server_type", "server_model", "platform_type", "chassis_form", "purchase_qty", "warranty_years"}

# catalog 字段 → 在售目录维度 key（catalog_whitelist 的 types/series/forms/models）。
# 这是「插座」契约：声明某目录字段取值来自哪一维，候选值仍由 catalog_search/catalog_whitelist 提供；
# 前端可在字段配置里显式配 catalog_dimension 覆盖，这里只是数据驱动兜底，不写业务规则。
_CATALOG_FIELD_DIMENSION: dict = {
    "server_type": "types",
    "platform_type": "series",
    "chassis_form": "forms",
    "server_model": "models",
}

# 非目录字段缺失时的兜底默认值（保证流程可通、允许填错，正确性后续由规则层扭转）。
# 前端可在字段配置里显式配 default_value 覆盖；这里只是数据驱动兜底，不写业务规则。
_SLOT_DEFAULT: dict = {
    "purchase_qty": 1,
}


def _load_kp_categories() -> list:
    """从 kp.kp_categories 读取大类名列表；失败返回空。"""
    try:
        from sqlalchemy import text
        from app.models.base import kp_engine
        with kp_engine.connect() as c:
            rows = c.execute(text("SELECT name FROM kp.kp_categories ORDER BY sort_order, id")).mappings().all()
        return [str(r["name"]).strip() for r in rows if r.get("name")]
    except Exception:
        return []


def _load_kp_slot_map() -> dict:
    """读 KP 大类→归一部件槽位映射（system_config.kp_slot_group_map）；失败用兜底常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            raw = repo.get_value("kp_slot_group_map", {})
        finally:
            repo.close()
        if isinstance(raw, dict) and raw:
            return raw
    except Exception:
        pass
    return {}


def _load_basic_slots() -> list:
    """读基本信息槽位（system_config.requirement_slots.slots，只保留基本信息 6 项）。

    字段顺序唯一权威 = 表单定义（requirement_sheet_form.config_fields）：引擎反问顺序、
    登记契约简报、进度卡与商机详情页真实表单共用一套序；表单未列的键排后面（保持原相对序）。
    """
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        from app.services.slot_contract import canonical_key
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("requirement_slots", {})
            form = repo.get_value("requirement_sheet_form", {})
        finally:
            repo.close()
        raw_slots = cfg.get("slots") if isinstance(cfg, dict) else None
        if not isinstance(raw_slots, list):
            return []
        out = []
        seen = set()
        for s in raw_slots:
            if not isinstance(s, dict):
                continue
            k = str(s.get("key") or s.get("name") or "").strip()
            k = canonical_key(k)
            if not k or k not in _BASIC_KEYS or k in seen:
                continue
            d = dict(s)
            d["key"] = k
            d["src_key"] = k
            d["src_type"] = "config"
            d.setdefault("group", "基本信息")
            d.setdefault("label", k)
            d.setdefault("level", "L2")
            d.setdefault("candidate_source",
                         "catalog" if k in ("server_type", "platform_type", "chassis_form", "server_model") else "free")
            if d.get("candidate_source") == "catalog":
                d.setdefault("catalog_dimension", _CATALOG_FIELD_DIMENSION.get(k))
            if d.get("candidate_source") != "catalog":
                d.setdefault("default_value", _SLOT_DEFAULT.get(k))
            out.append(d)
            seen.add(k)
        order_map: dict = {}
        fields = form.get("config_fields") if isinstance(form, dict) else None
        if isinstance(fields, list):
            for i, f in enumerate(fields):
                if isinstance(f, dict) and f.get("key"):
                    order_map[str(f["key"])] = i
        if order_map:
            out.sort(key=lambda d: order_map.get(str(d.get("key")), len(order_map)))
        return out
    except Exception:
        return []


def _load_kp_slots() -> list:
    """由 KP 大类动态生成部件槽位（按 kp_slot_group_map 归一映射）。

    已知归一部件槽位（cpu/memory/storage/gpu/nic/raid/psu）进入进度卡/反问统计；
    未映射的大类不生成进度槽位（作为表单自由行，由 KpPartsEditor 直接处理）。
    """
    cats = _load_kp_categories()
    if not cats:
        return []
    m = _load_kp_slot_map()
    out = []
    seen = set()
    order = 0
    for cat in cats:
        rule = m.get(cat)
        if not isinstance(rule, dict):
            continue
        key = str(rule.get("key") or "").strip()
        if not key or key in seen:
            continue
        d = dict(rule)
        d["category"] = cat
        d["key"] = key
        d["src_key"] = key
        d["src_type"] = "kp"
        d["group"] = str(rule.get("group") or "部件")
        d["label"] = cat
        d.setdefault("candidate_source", "catalog")
        for _k in ("level", "required", "ask", "default_ok"):
            d.pop(_k, None)
        d["order"] = 100 + order
        out.append(d)
        seen.add(key)
        order += 1
    return out


def combined_slot_spec() -> list:
    """合成完整槽位清单 = 基本信息(requirement_slots) + 部件(KP 大类动态)。

    唯一权威源：基本信息由管理员配置；部件不再写死在 requirement_slots，改由 KP 大类动态合成。
    供理解节点、反问节点、前端进度卡、编辑器统一读取。
    """
    basic = _load_basic_slots()
    kp = _load_kp_slots()
    out = []
    for i, b in enumerate(basic):
        b = dict(b)
        b.setdefault("order", i)
        out.append(b)
    for p in kp:
        p = dict(p)
        p.setdefault("order", 200 + (p.get("order") or 0))
        out.append(p)
    return out
