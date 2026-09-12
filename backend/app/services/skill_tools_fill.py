# -*- coding: utf-8 -*-
"""登记环节工具（fill_requirement）：把客户已明确表达的需求逐项落进线索登记表。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

import logging
import json
from app.services.skill_memory import _kp_node_state, _slots_view
from app.services.skill_node_state import KP_ABSENT, KP_PICKS
from app.services.skill_tool_context import TOOL_CTX
from app.services.slot_contract import canonical_key, catalog_field_keys, slot_label, slot_spec
from typing import Optional


logger = logging.getLogger(__name__)


def requirement_prompt(slots: Optional[dict] = None, price_ok: bool = True) -> str:
    """角色的需求收集提示词（任务态）。slots=None = 任务未开始：不暴露登记表（进任务前不碰目标表）。

    此处只带登记表视图与价格守卫；技能纪律（提交时机/复述确认/工具说到做到/目录查询门等）
    统一由 Skill Studio 左栏「使用说明」（graph.manual_rules）承载，与节点大脑同源。
    data_rule 已下沉到 query_data 工具描述，不再在此注入。
    """
    # 只摆事实：登记表视图 + 价格权限事实。禁价话术与推荐纪律住在左栏（任务规则 20），
    # 代码里再写一遍就是第二套提示词。
    price_fact = "" if price_ok else "（本角色无价格查看权限 price_access=false）"
    if slots is None:
        slots_block = "（配置任务未开始：本轮没有登记表）"
    else:
        slots_block = json.dumps(slots, ensure_ascii=False)
    return "\n\n".join(p for p in (slots_block, price_fact) if p)


def _normalize_fill_keys(slots: dict) -> dict:
    """把大脑给的登记键归一为 canonical 字段（数据驱动，不写死词表）。

    归一顺序：别名表（canonical_key）→ 登记表中文标签 → 大小写对齐。
    模型偶发用「服务器类型」等中文标签或「CPU」等大写键登记——落错槽的登记等于没登记。
    """
    spec = slot_spec()
    label_map: dict = {}
    lower_map: dict = {}
    valid_keys: set = set()
    for s in spec:
        key = str(s.get("key") or "").strip()
        if not key:
            continue
        valid_keys.add(key)
        label = str(s.get("label") or "").strip()
        if label and label not in label_map:
            label_map[label] = key
        lower_map.setdefault(key.lower(), key)
    norm: dict = {}
    for k, v in (slots or {}).items():
        key = str(k).strip()
        canon = canonical_key(key)
        if canon not in valid_keys:
            if key in label_map:
                canon = label_map[key]
            elif canon.lower() in lower_map:
                canon = lower_map[canon.lower()]
        norm[canon] = v
    return norm


def tool_fill_requirement(args: dict) -> dict:
    """【任务期工具】把客户已明确表达的需求逐项登记到线索登记表（结构化落表）。

    只在 agent_fill 节点的大脑回合挂载；普通对话永远没有这个工具——
    进任务前角色只引导和复述，绝不提前填表。落表本身是确定性的
    （_apply_extracted_slots：默认只填空槽；replace=True 客户改口才覆盖）。
    """
    ctx = TOOL_CTX.get()
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "hint": "配置任务未开始（fill_requirement 仅在任务期可用）"}
    args = args or {}
    replace = bool(args.get("replace"))
    # 扁平契约：登记表字段即顶层键（与线索登记表/目标层同构）；兼容旧 slots 包裹。
    slots = dict(args)
    slots.pop("replace", None)
    nested = slots.pop("slots", None)
    if isinstance(nested, dict) and nested:
        merged = dict(nested)
        merged.update(slots)  # 顶层为准（kp_rows 等顶层键优先生效）
        slots = merged
    if not slots:
        return {"ok": False, "error": "invalid_args",
                "hint": "请提供要登记的字段（顶层键=登记表字段/部件清单 kp_rows）"}
    slots = _normalize_fill_keys(slots)
    # 值规范化（机制级，非业务词表）：数字字段接受「3年」「2台」等自然语言写法，
    # 否则会被整数守卫静默丢弃（实测：大脑原样转写"3年"→字段丢失）。
    import re as _re
    for num_key in ("purchase_qty", "warranty_years"):
        v = slots.get(num_key)
        if isinstance(v, str):
            m = _re.search(r"\d+", v)
            if m:
                slots[num_key] = int(m.group(0))
    # 对象身份必须保持（空 dict falsy 会换成 detached 副本，落表全丢——09-02 实测坑）。
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    # 明确放弃部件（kp_absent）：客户答复"不需要某类部件"时登记放弃，
    # 必登记部件策略（kp_required）据此放行，不再追问该大类。
    kp_absent = slots.pop("kp_absent", None)
    kp_absent_changed = False
    kp_st = _kp_node_state()
    if isinstance(kp_absent, list) and kp_absent:
        merged = {str(c).strip() for c in kp_absent if str(c).strip()} | set(kp_st.get(KP_ABSENT) or [])
        kp_st[KP_ABSENT] = sorted(c for c in merged if c)
        kp_absent_changed = True
    from app.services.capabilities import _apply_extracted_slots, _slot_now_filled
    changed = _apply_extracted_slots(ext, slots, allow_overwrite=replace,
                                     picks=kp_st.get(KP_PICKS))
    # 客户原话申报（customer_stated）：大脑声明这些目录字段是客户**自己说过的**，不是它推断的。
    # 与点选同源记为「客户已确认」（凡推断必求证的求证侧）——申报只对已填的目录字段生效，
    # 字段集来自登记表契约，不认别的键。
    stated_marks: list = []
    stated = slots.pop("customer_stated", None) if isinstance(slots, dict) else None
    if isinstance(stated, list) and stated:
        from app.services.slot_contract import canonical_get, catalog_field_keys
        allowed = catalog_field_keys()
        conf = ext.get("confirmed_slots")
        if not isinstance(conf, dict):
            conf = {}
            ext["confirmed_slots"] = conf
        for k in stated:
            kk = canonical_key(str(k or "").strip())
            if kk not in allowed:
                continue
            v = canonical_get(ext, kk)
            vs = "" if v is None else str(v).strip()
            if not vs:
                continue
            conf[kk] = vs
            stated_marks.append(kk)
    save = ctx.get("save")
    if callable(save):
        save()
    from app.services.slot_contract import _missing_critical
    spec = slot_spec()
    valid_keys = {str(s.get("key") or "").strip() for s in spec if str(s.get("key") or "").strip()}
    valid_keys.add("kp_rows")  # 部件行是登记表的真实存储键（不在 slot_spec 清单里）
    req_keys = {s.get("key") for s in spec if s.get("src_type") != "kp"}
    missing = [slot_label(m) for m in _missing_critical(ext)
               if m in req_keys and not _slot_now_filled(ext, m)]
    unknown = sorted(k for k in slots if k not in valid_keys)
    frozen = int(ext.get("_kp_rows_frozen") or 0)
    ext.pop("_kp_rows_frozen", None)
    return {"ok": True, "changed": bool(changed or kp_absent_changed or stated_marks),
            "registered": sorted(str(k) for k in slots.keys() if k in valid_keys)
                          + (["kp_absent"] if kp_absent_changed else []),
            "customer_stated": stated_marks,
            "unrecognized_keys": unknown,
            "locked_rows_kept": frozen,
            "hint": ("部件信息请改用 kp_rows 数组登记：每项 {part_category, description, qty}，"
                     "part_category 用配件大类名，description 按客户原话原样写") if unknown else "",
            "missing_critical": missing,
            "current": _slots_view(ext)}


def fill_tool_parameters() -> dict:
    """fill_requirement 的参数 schema：从登记表字段契约生成（system_config.requirement_slots + KP 大类）。

    字段清单/标签全部数据驱动——前端改登记表字段配置，工具契约自动跟随，不写死字段词表。
    """
    props: dict = {}
    for s in slot_spec():
        key = str(s.get("key") or "").strip()
        if not key or s.get("src_type") == "kp":
            continue
        label = str(s.get("label") or key)
        cand = str(s.get("candidate_source") or "free")
        dim = str(s.get("catalog_dimension") or "").strip()
        _enum: list = []
        if cand == "catalog":
            if dim == "models":
                desc = (f"{label}：取值来自在售目录机型；客户明确给出型号时登记原样型号，"
                        f"未给则留待机型选型步骤锁定")
            else:
                desc = (f"{label}：从下拉选项结合实际需求选一个规范值登记；客户明确说了就按客户原意直接选")
                try:
                    from app.services.catalog_options import catalog_whitelist
                    _dl = catalog_whitelist({}, {}, "")
                    _enum = [str(v).strip() for v in (_dl.get(dim) or []) if str(v).strip()]
                except Exception:
                    logger.exception("读取目录选项失败")
                    _enum = []
        else:
            dv = s.get("default_value")
            if dv is not None:
                desc = f"{label}：客户原话/确认过的信息；客户未提时默认 {dv}（可错、可后续修正）"
            else:
                desc = f"{label}：客户原话/确认过的信息；缺失时按契约默认值处理"
        props[key] = {"type": "string", "description": desc}
        if _enum:
            props[key]["enum"] = _enum
    try:
        from app.services.requirement_slots import _load_kp_categories
        _kp_cats = [str(c).strip() for c in (_load_kp_categories() or []) if str(c).strip()]
    except Exception:
        logger.exception("读取 KP 大类失败")
        _kp_cats = []
    _kp_cat_desc = "配件大类；必须从本参数的 enum 中选择，description 保留客户原话"
    _part_category_prop: dict = {"type": "string", "description": _kp_cat_desc}
    if _kp_cats:
        _part_category_prop["enum"] = list(_kp_cats)
    props["kp_rows"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "part_category": _part_category_prop,
                "description": {"type": "string", "description": "客户原话规格，原样保留型号/数量/单位"},
                "catalogue": {"type": "string", "description": "匹配到的目录部件型号；登记阶段留空由选型节点填"},
                "note": {"type": "string", "description": "备注，可空"},
                "qty": {"type": "integer", "description": "数量"},
            },
            "required": ["part_category", "description"],
        },
        "description": ("部件清单，每项 {part_category, description, qty}；description 按客户原话原样写，不拆规格。"
                         "part_category 必须从上面的 enum 中选择；多件组合仍逐条登记。"),
    }
    props["kp_absent"] = {
        "type": "array", "items": {"type": "string"},
        "description": "客户明确表示不需要的必登记部件大类（如 ['GPU']）；登记后不再追问该类",
    }
    props["replace"] = {
        "type": "boolean",
        "description": "客户改口/修正时 true（允许覆盖已登记值）；默认 false 只填空槽",
    }
    # 客户原话申报：目录字段「客户明说 / 你推断」的溯源自报——引擎只认这一份申报，
    # 推断值带着进下游会让「库里有没有料」的判据失真（见 §前提闸门）。
    _cat_keys = sorted(k for k in catalog_field_keys() if k in props)
    if _cat_keys:
        props["customer_stated"] = {
            "type": "array", "items": {"type": "string", "enum": _cat_keys},
            "description": ("客户原话里明确说出的目录字段 key（只列客户自己说过的；"
                            "推断/按默认值填的不列）。申报后系统记为「客户已确认」，"
                            "不再对该字段反问；漏报会导致下游节点要求客户再确认一次"),
        }
    # 扁平契约：参数直接对齐线索登记表（目标层）的顶层键，不包一层 slots。
    # 之前用 slots 包裹导致大脑自然把 kp_rows 放顶层而被拒，流程卡死——契约应=目标层结构。
    return {"type": "object", "properties": props}


def _fill_contract_brief() -> str:
    """（兼容别名）登记契约简报；实现已迁到节点插件注册表。"""
    from app.services.skill_node_plugins import fill_contract_brief
    return fill_contract_brief()
