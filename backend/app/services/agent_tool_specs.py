# -*- coding: utf-8 -*-
"""agent_tool_specs —— 工具元数据 + registry 构建。声明 schema，不含业务实现。"""
from typing import List, Optional
from app.services.agent_tool_registry import ToolRegistry
from app.services.agent_tool_handlers import _search_cases_handler, _tool_build_plan, _tool_catalog_search, _tool_compose_memory, _tool_cost_breakdown, _tool_list_kp_categories, _tool_query_data, _tool_quote_draft, _tool_resolve_part_alias, _tool_select_models, _tool_select_parts, _tool_submit_registration, _tool_update_requirement_slots, _tool_update_server_model, _tool_update_server_type

# ── 工具元数据全集（name/description/parameters + handler）—— 画布可勾选启用 ──
_TOOL_SPECS = {
    "update_requirement_slots": {
        "description": "把客户明确表达的需求当轮逐项写进线索登记表（只登记客户说过的话，禁止臆测；一句话里点名的每个配件型号/数量/容量都不能漏）",
        "default_enabled": False,
        "handler": _tool_update_requirement_slots,
        "parameters": {
            "type": "object",
            "properties": {
                "fill": {"type": "object", "description": ("要登记的字段（键名：server_type_name/series/form/purchase_qty/cpu/memory/drives/gpu/raid/kp_mode）。"
                                                           "配件信号槽必须给结构化对象/数组（如 gpu=[{\"tokens\":[\"智铠100\"],\"qty\":4}]、"
                                                           "memory={\"total_gb\":256}、drives=[{\"term\":\"2048G\",\"qty\":2,\"kind\":\"SSD\"}]），禁止一句话文本")},
            },
            "required": ["fill"],
        },
    },
    "submit_registration": {
        "description": "线索登记表信息足够（场景已明确）时提交，触发配置引擎自动出方案",
        "default_enabled": False,
        "handler": _tool_submit_registration,
        "parameters": {"type": "object", "properties": {}},
    },
    "catalog_search": {
        "description": ("查询在售目录：kind=types 查类型清单；kind=models 按类型/系列/形态查机型（含价格）；"
                        "kind=parts 按品类查配件清单（可带 series 过滤适配平台）——推荐的事实来源"),
        "default_enabled": False,
        "handler": _tool_catalog_search,
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["types", "models", "parts"], "description": "查询种类"},
                "type_name": {"type": "string", "description": "服务器类型全名（kind=models 时可选）"},
                "category": {"type": "string", "description": "配件品类（kind=parts 时必填，如 CPU/Memory/GPU/HDD SSD/Raid card）"},
                "series": {"type": "string", "description": "平台系列（可选；kind=parts 时按适配过滤）"},
                "form": {"type": "string", "description": "机箱形态如 2U/4U（可选）"},
                "limit": {"type": "integer", "description": "返回条数上限，默认 8"},
            },
            "required": ["kind"],
        },
    },
    "select_models": {
        "category": "selection",
        "data_sources": ["candidate_search"],
        "default_enabled": True,
        "description": ("根据服务器需求挑选在售机型基准配置候选，返回候选清单"
                        "（名称/系列/形态/盘位数/卖点）。当能确定服务器类型/形态或系列时调用。"
                        "形态(1U/2U/4U)或系列时调用，用于锁定机型。"),
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_name": {"type": "string", "description": "服务器类型全名（从在售类型清单选，不确定可省略）"},
                "form": {"type": "string", "description": "机箱形态 1U/2U/4U；不确定可省略"},
                "series": {"type": "string", "description": "产品系列 Orion/Polaris/Intel；不确定可省略"},
                "usage": {"type": "string", "description": "用途/场景关键词，如 web/数据库/虚拟化"},
            },
        },
        "handler": _tool_select_models,
    },
    "select_parts": {
        "category": "selection",
        "data_sources": ["kp_price"],
        "default_enabled": True,
        "description": ("按结构化信号从配件库落地真实料号。信号字段（cpu/memory/drives/"
                        "gpu/raid/nic）由 AI 依据客户需求原文补全，登记表只作缓存；"
                        "AI 负责把原文中每类配件转为信号，工具只检索落地，料号/价格/规格由工具返回，禁止编造。"),
        "parameters": {
            "type": "object",
            "properties": {
                "categories": {"type": "array", "items": {"type": "string"}, "description": "要匹配的配件类目（可选；不给则按信号自动推导）"},
                "server_type_name": {"type": "string", "description": "服务器类型全名（可选，用于推断标准类目）"},
                "cpu": {"type": "object", "description": "CPU 信号 {qty, model?, cores?, tdp_w?}"},
                "memory": {"type": "object", "description": "内存信号 {type?, speed?, total_gb?: '总容量，如 128G；优先填 total_gb，工具会按库存自动拆条', per_stick_gb?: '仅客户明确单条容量时填', qty?}"},
                "drives": {"type": "array", "items": {"type": "object"}, "description": "盘组 [{term:'容量+接口+介质，如 16T SATA HDD / 960G SATA SSD', qty, kind?:'可选接口/介质，如 SATA/NVMe/SAS/SSD/HDD', comparison?}]"},
                "gpu": {"type": "array", "items": {"type": "object"}, "description": "GPU 组 [{tokens: ['GPU 型号，如 RTX PRO 4500'], qty, cap?: '显存，如 32G'}]；tokens 必填，禁止只传 cap"},
                "raid": {"type": "array", "items": {"type": "object"}, "description": "阵列卡组 [{model?, raid_levels?, qty}]"},
                "psu": {"type": "object", "description": "电源信号 {wattage?, qty?}（电源由整机底盘推断，此处可省略）"},
                "nic": {"type": "object", "description": "网卡等多规格过滤；key 固定用 \"Network(NIC) requirement\"，每项 {filters?, name_contains?: ['客户原文关键修饰词，如 10G/双口/光模块'], qty}"},
                "representative_pick": {"type": "string", "description": "min_price/max_price/first，默认 min_price"},
            },
        },
        "handler": _tool_select_parts,
    },
    "resolve_part_alias": {
        "category": "selection",
        "data_sources": ["kp_price"],
        "default_enabled": True,
        "description": ("把用户语义术语/别名解析成库内真实料号候选（如「兆芯」→ KH40000/KH50000）。"
                        "规则库未命中时按名称检索兜底；只返回候选与命中原因，不静默顶替。"),
        "parameters": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "用户原话中的配件语义术语，如「兆芯」「128G内存」"},
                "category": {"type": "string", "description": "配件类目（CPU/Memory/GPU/HDD-SSD/Raid card/NIC…），不确定可省略"},
            },
            "required": ["term"],
        },
        "handler": _tool_resolve_part_alias,
    },
    "compose_memory": {
        "category": "selection",
        "data_sources": ["kp_price"],
        "default_enabled": True,
        "description": ("内存容量组合求解：给定总容量，返回库内可行的单条容量×数量组合（128G → 64G×2 / 32G×4），"
                        "并按 DIMM 槽位校验可行性。用于用户只给总容量时的智能拆分。"),
        "parameters": {
            "type": "object",
            "properties": {
                "total_gb": {"type": "integer", "description": "内存总容量 GB"},
                "slots": {"type": "integer", "description": "可用内存槽位（可选，用于可行性过滤）"},
            },
            "required": ["total_gb"],
        },
        "handler": _tool_compose_memory,
    },
    "list_kp_categories": {
        "category": "data",
        "data_sources": ["kp_price"],
        "default_enabled": True,
        "description": "查询真实配件类目目录，返回规则键/真实库类目/数量/别名。选配件前先调它，避免猜错类目名。",
        "parameters": {"type": "object", "properties": {}},
        "handler": _tool_list_kp_categories,
    },
    "build_plan": {
        "category": "selection",
        "data_sources": ["bom", "kp_price"],
        "default_enabled": True,
        "description": ("把一个机型基准配置 + 配件清单组合成整机方案，返回机型名/总成本/未匹配件清单。"
                        "用于预估方案成本与完整性。"),
        "parameters": {
            "type": "object",
            "properties": {
                "baseline": {"type": "object", "description": "select_models 返回的某个候选机型（含 id/name/series/form 等）"},
                "kp_parts": {"type": "array", "items": {"type": "object"}, "description": "select_parts 返回的配件清单"},
            },
            "required": ["baseline", "kp_parts"],
        },
        "handler": _tool_build_plan,
    },
    "cost_breakdown": {
        "category": "cost",
        "data_sources": ["bom", "kp_price", "cost"],
        "default_enabled": False,
        "description": ("拆解一个整机方案的成本结构，返回 L6 底盘成本、KP 关键件成本、总成本、"
                        "数量与未匹配件。回答成本/成本明细/成本差异问题时调用；plan 必须是 build_plan 输出的方案对象。"),
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "object", "description": "build_plan 返回的方案对象，需包含 summary.l6_cost / kp_cost / total_cost"},
            },
            "required": ["plan"],
        },
        "handler": _tool_cost_breakdown,
    },
    "quote_draft": {
        "category": "quote",
        "approval_required": True,
        "data_sources": ["quotation", "opportunities", "bom", "kp_price", "cost"],
        "default_enabled": False,
        "description": ("根据一个整机方案生成报价单草稿，返回基准成本、建议毛利率、含税报价和草稿状态。"
                        "报价/生成报价单草稿/解释价格构成时调用；plan 必须是 build_plan 输出的方案对象。"),
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "object", "description": "build_plan 返回的方案对象，需包含 summary.total_cost"},
            },
            "required": ["plan"],
        },
        "handler": _tool_quote_draft,
    },
    "search_cases": {
        "category": "data",
        "data_sources": ["candidate_search", "bom"],
        "default_enabled": True,
        "description": ("检索【选型配置案例库】里与当前需求相似的历史案例（需求→机型/底盘配置 对照），"
                        "作为接地参考。需求模糊、或想参照同类已验证配置（如「8卡GPU AI服务器一般配什么底盘/电源」）时调用。"
                        "只读，绝不改案例库。"),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用于检索的需求/场景文本"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "场景标签过滤（可选），如 ['AI','8卡GPU','Polaris','4U']"},
            },
        },
        # handler 由 build_tool_registry 按 case 配置（case_source/top_k/match）注入
        "handler": None,
    },
    "query_data": {
        "category": "data",
        "default_enabled": False,
        "description": (
            "在数据边界内执行只读 SELECT，返回列名与行数据。规则：只写单条 SELECT（支持 WITH/CTE，"
            "禁止任何写操作与注释）；先用 information_schema.tables / information_schema.columns "
            "查看可读表与列结构；表不在白名单会返回错误（可用 information_schema 自查可读范围）；"
            "SQL 报错信息原样返回，据此修正重试；价格等敏感列可能被自动脱敏（该列不返回）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "单条只读 SELECT 语句（PostgreSQL 方言）"},
                "limit": {"type": "integer", "description": "返回行数上限，默认 50（硬上限 200）"},
            },
            "required": ["sql"],
        },
        "handler": _tool_query_data,
    },
    "update_server_type": {
        "category": "content",
        "approval_required": True,
        "data_sources": ["server_catalog"],
        "default_enabled": False,
        "description": "生成服务器类型/产品系列内容修改草稿，可改名称、描述、排序、3D 展示配置；不直接落库，需审批。",
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_id": {"type": "integer", "description": "服务器类型/产品系列 id（必填）"},
                "name": {"type": "string", "description": "产品系列名称"},
                "description": {"type": "string", "description": "产品系列描述"},
                "sort_order": {"type": "integer", "description": "排序值"},
                "showcase_config": {"type": "object", "description": "3D 展示配置（glb_path/title/description/bullets/render）"},
            },
            "required": ["server_type_id"],
        },
        "handler": _tool_update_server_type,
    },
    "update_server_model": {
        "category": "content",
        "approval_required": True,
        "data_sources": ["server_catalog", "server_product_content"],
        "default_enabled": False,
        "description": "生成机型内容修改草稿，可改机型名、类型、生命周期、上架状态、图片、产品内容等；不直接落库，需审批。",
        "parameters": {
            "type": "object",
            "properties": {
                "server_model_id": {"type": "integer", "description": "机型 id（必填）"},
                "name": {"type": "string", "description": "机型名"},
                "server_type_id": {"type": "integer", "description": "服务器类型 id"},
                "base_config_id": {"type": "integer", "description": "主配置 id"},
                "sort_order": {"type": "integer", "description": "排序值"},
                "description": {"type": "string", "description": "机型简介"},
                "image_url": {"type": "string", "description": "产品主图 URL"},
                "lifecycle_status": {"type": "string", "enum": ["new", "active", "eol", "discontinued"], "description": "生命周期：new/active/eol/discontinued"},
                "is_published": {"type": "boolean", "description": "是否上架"},
                "product_content": {"type": "object", "description": "产品内容：tagline/overview/highlights/capabilities/specs/scenarios"},
            },
            "required": ["server_model_id"],
        },
        "handler": _tool_update_server_model,
    },
}

# 全部可用工具名（给画布抽屉候选 + 默认值用）
ALL_TOOL_NAMES = list(_TOOL_SPECS.keys())


def tool_required_data_sources(tool_ids: Optional[list] = None) -> list:
    """返回一组工具运行所需的数据域，用于 AI 同事绑定 Skill 时自动授权。"""
    sources: set = set()
    for tool_id in tool_ids or []:
        spec = _TOOL_SPECS.get(str(tool_id or "").strip())
        if not spec:
            continue
        sources.update(str(item) for item in (spec.get("data_sources") or []) if str(item))
    return sorted(sources)


def tool_requires_approval(tool_name: str) -> bool:
    """工具级审批开关：只有真实写库/出报价类工具才需要审批。

    Skill 内部的选择、匹配、BOM 组装、案例检索等草稿计算不在此列。
    """
    spec = _TOOL_SPECS.get(str(tool_name or "").strip())
    return bool(spec and spec.get("approval_required"))


def tool_catalog() -> List[dict]:
    """全量工具目录（无 handler），供前端「AI 工具」目录页与方案助手提参提示渲染。

    每个条目：name / category(selection|data) / description / parameters / default_enabled。
    """
    return [{
        "name": name,
        "category": spec.get("category") or "selection",
        "description": spec["description"],
        "parameters": spec["parameters"],
        "default_enabled": bool(spec.get("default_enabled", True)),
        "data_sources": [str(item) for item in (spec.get("data_sources") or []) if str(item)],
    } for name, spec in _TOOL_SPECS.items()]


def registered_tool_ids() -> List[str]:
    """返回 agent_tools 注册表里所有工具 ID（供能力 spec 校验 / 默认工具取用）。"""
    return list(_TOOL_SPECS.keys())


def build_tool_registry(config: dict, allowed_tool_ids: list = None, allowed_data_sources: list = None) -> ToolRegistry:
    """按节点 config 启用的工具集建 registry。

    config.enabled_tools: list[str] —— 启用的工具名（画布抽屉勾选）；
    未配置或空 → 默认启用全集（向后兼容）。
    allowed_tool_ids: list[str] —— AI 同事的 tool_ids 白名单；传 None 不限制，
    传 [] 表示同事不允许任何工具。
    """
    cfg = config or {}
    # 默认全集 = default_enabled=True 的工具；default_enabled=False（如 query_data）
    # 不进任何节点默认配置，需要时由调用方显式启用（避免改变现有推理流行为）
    enabled = cfg.get("enabled_tools") or [
        name for name, spec in _TOOL_SPECS.items() if spec.get("default_enabled", True)
    ]
    if allowed_tool_ids is not None:
        allowed_set = set(allowed_tool_ids)
        enabled = [name for name in enabled if name in allowed_set]
    reg = ToolRegistry(allowed_data_sources=allowed_data_sources)
    for name in enabled:
        spec = _TOOL_SPECS.get(name)
        if not spec:
            continue
        handler = spec["handler"]
        # search_cases 需要用户可配的 case 参数（case_source/top_k/match）→ 闭包注入
        if name == "search_cases":
            handler = _search_cases_handler(cfg)
        if handler is None:
            continue
        reg.register(name, spec["description"], spec["parameters"], handler, data_sources=spec.get("data_sources"))
    return reg
