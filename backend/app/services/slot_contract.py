# -*- coding: utf-8 -*-
"""线索登记表 slot 契约与填充判定工具（agent_fill / model_reason / kp_reason 共用）。

slot_spec / slot_label / _missing_critical 是全链路字段契约的唯一来源：
理解(agent_fill)、选型(model_reason/kp_reason)、前端进度卡都按它对齐。
历史需求理解/反问节点已合并为 agent_fill，相关实现已删除。
"""

import logging
from typing import Optional


logger = logging.getLogger(__name__)




def _default_candidate_source(key: str) -> str:
    """默认候选来源：类型/系列/形态/机型走目录白名单，其余自由输入。"""
    return "catalog" if key in ("server_type", "platform_type", "chassis_form", "server_model") else "free"


def _default_group(key: str) -> str:
    """默认分组：基本信息/部件（进度卡按此分组，配置可覆盖）。"""
    return "基本信息" if key in ("server_type", "server_model", "platform_type", "chassis_form",
                                 "purchase_qty", "warranty_years") else "部件"

# 规范标签兜底：覆盖后端 slot key 与前端线索登记字段键的别名，防反问文案/进度卡标签裸 key。
_CANONICAL_SLOT_LABELS = {
    "scene": "服务器类型",
    "server_type": "服务器类型",
    "server_type_name": "服务器类型",
    "platform_type": "平台/系列",
    "series": "平台/系列",
    "chassis_form": "机箱形态",
    "form": "机箱形态",
    "purchase_qty": "数量",
    "server_model": "机型",
    "warranty_years": "保修年限",
    "cpu": "CPU",
    "memory": "内存",
    "storage": "存储",
    "gpu": "GPU",
    "nic": "网卡",
    "raid": "阵列卡",
    "psu": "电源",
}


def slot_spec() -> list:
    """线索登记表字段契约（唯一权威源 = system_config.requirement_slots 基本信息 + KP 大类动态部件）。

    这是全链路「要填哪些字段 / 反问问哪些」的唯一来源：理解节点、反问节点、前端进度卡都按它对齐。
    每项含 key/label/level/group/candidate_source/src_type/order（部件槽位无 level，按 L2 系统推导处理）。
    部件字段不再写死在 requirement_slots，改由 KP 大类动态合成（见 requirement_slots.combined_slot_spec）。
    """
    try:
        from app.services.requirement_slots import combined_slot_spec
        spec = combined_slot_spec()
        if spec:
            return spec
    except Exception:
        pass
    out = []
    for idx, item in enumerate(_FALLBACK_SLOT_SPEC):
        d = dict(item)
        d["src_key"] = d["key"]
        d["src_type"] = d.get("src_type") or ("config" if d.get("group") == "基本信息" else "kp")
        d["order"] = idx
        out.append(d)
    return out


def slot_label(key: str) -> str:
    """按 slot key 取中文标签（前端进度卡/反问文案共用）。"""
    key = (key or "").strip()
    for s in slot_spec():
        if s.get("key") == key:
            return str(s.get("label") or key)
    return _CANONICAL_SLOT_LABELS.get(key, key)


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
    mapping = {
        "server_type": ["server_type_name", "server_type"],
        "platform_type": ["series", "platform_type"],
        "chassis_form": ["form", "chassis_form"],
        "purchase_qty": ["purchase_qty", "n"],
        "n": ["n", "purchase_qty"],
        "server_model": ["server_model", "model", "baseline_model"],
        "cpu": ["cpu_signal"],
        "memory": ["mem_signal", "mem_groups"],
        "storage": ["drive_groups"],
        "gpu": ["gpu_groups"],
        "nic": ["multi_spec_filters"],
        "raid": ["raid_groups", "raid_signal"],
        "psu": ["psu_signal"],
    }
    return any(_has(ext.get(k)) for k in mapping.get(key, []))


def _missing_critical(ext: dict) -> list:
    """缺哪些关键字段（供反问/进度卡用）——返回线索登记契约的 slot key，与前端字段一致。

    按字段契约的 level 驱动：L0 缺了必问；L1 提示可补；L2 系统推导；
    类型或「系列+形态」至少要有一个（否则无法选型）。
    """
    spec = slot_spec()
    has_type = bool(ext.get("server_type_name") or ext.get("server_type"))
    has_series_form = bool((ext.get("series") or ext.get("platform_type"))
                           and (ext.get("form") or ext.get("chassis_form")))
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


# 平台系列别名：规则只读规则目录 platform_series_map，不内嵌厂商正则
