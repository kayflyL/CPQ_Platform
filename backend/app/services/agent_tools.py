# -*- coding: utf-8 -*-
"""agent_tools —— 智能体节点的工具注册表（ToolRegistry）。

把推理流后半段的确定性能力包成 OpenAI function tools，让 llm_agent 节点（ReAct 循环）
经 llm_client.chat_with_tools 调用。LLM 负责推理/编排，精确性交给工具。

设计原则（用户定调「拒绝硬编码」）：
  - 工具是数据：name/description/parameters 存节点 config，画布抽屉可勾选启用、改描述。
  - 工具只读/确定性：select_models 选机型、pick_kp_parts 配件、build_plan 组方案……
    复用现有实现，不重造；handler 把工具结果压成 LLM 友好的 digest（防上下文爆炸）。

工具只读、不落库、不改系统状态（案例库同理只读，见 case_provider.py）。
"""
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# 单工具 digest 最大字符数（防 LLM 上下文爆炸）
_MAX_DIGEST_CHARS = 4000


def _truncate(s: str, limit: int = _MAX_DIGEST_CHARS) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + "\n…(截断)"


class ToolRegistry:
    """工具注册表：schemas() 给 LLM 看、execute() 执行工具。

    registry.schemas() → OpenAI tools 格式（喂 chat_with_tools）。
    registry.execute(name, args) → 工具结果（dict/str，喂回 LLM 作 role:tool 消息）。
    """

    def __init__(self):
        self._tools: Dict[str, dict] = {}

    def register(self, name: str, description: str, parameters: dict,
                 handler: Callable[[dict], Any]):
        self._tools[name] = {"name": name, "description": description,
                             "parameters": parameters, "handler": handler}

    def schemas(self) -> List[dict]:
        return [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["parameters"]}} for t in self._tools.values()]

    def names(self) -> List[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, args: dict) -> Any:
        spec = self._tools.get(name)
        if not spec:
            return {"error": f"未知工具: {name}"}
        try:
            return await spec["handler"](args or {})
        except Exception as e:
            logger.exception("工具 %s 执行失败", name)
            return {"error": f"工具 {name} 执行失败: {e}"}


# ── 工具 handler：把现有确定性函数包成 agent 工具（结果压成 digest） ──────

async def _tool_select_models(args: dict) -> Any:
    """select_models → 候选机型 digest（名称/系列/形态/盘位/卖点，给 LLM 推理）。"""
    from app.api.candidate_search import select_models
    baselines = select_models(
        usage=args.get("usage") or "",
        server_type_name=args.get("server_type_name"),
        series=args.get("series"),
        form=args.get("form"),
        limit=int(args.get("limit") or 6),
        fallback_order=args.get("fallback_order") or ["exact", "same_series", "same_form", "all"],
    )
    if not baselines:
        return {"count": 0, "candidates": [],
                "note": "无匹配机型；建议放宽 server_type/form，或补 usage 关键词"}
    note = (baselines[0].get("fallback_note") or "")
    digest = [{
        "config_id": b.get("id"),
        "server_model_id": b.get("server_model_id"),
        "name": b.get("name") or "",
        "series": b.get("series") or "",
        "form": b.get("form") or "",
        "bays": b.get("bays"),
        "recommend_level": b.get("recommend_level") or "",
        "selling_points": _truncate(b.get("selling_points") or "", 300),
        "match_stage": b.get("match_stage"),
        "fallback_note": b.get("fallback_note") or "",
    } for b in baselines]
    return {"count": len(digest), "candidates": digest, "note": note}


async def _tool_pick_kp_parts(args: dict) -> Any:
    """pick_kp_parts → 配件匹配 digest（pn/name/category/qty/matched_spec）。"""
    from app.api.candidate_search import pick_kp_parts, kp_categories_for_type
    cats = args.get("categories")
    server_type = args.get("server_type_name")
    if not cats and server_type:
        cats = kp_categories_for_type(server_type)
    if not cats:
        return {"error": "缺 categories，且 server_type_name 无法推断标准配件类目"}
    picks = pick_kp_parts(
        categories=cats,
        keywords=args.get("keywords") or [],
        requirement_text=args.get("requirement_text") or "",
        representative_pick=args.get("representative_pick") or "min_price",
    )
    digest = [{
        "category": p.get("category") or "",
        "pn": p.get("pn") or "",
        "name": p.get("name") or "",
        "qty": p.get("qty") or 1,
        "matched_spec": p.get("matched_spec") or "",
        "unmatched": bool(p.get("unmatched")),
        "unmatched_reason": p.get("unmatched_reason") or "",
    } for p in picks]
    return {"count": len(digest), "parts": digest}


async def _tool_build_plan(args: dict) -> Any:
    """build_plan → 整机方案 digest（机型/成本/未匹配件，给 LLM 推荐理由用）。"""
    from app.api.candidate_search import build_plan
    baseline = args.get("baseline")
    kp_parts = args.get("kp_parts")
    if not baseline or kp_parts is None:
        return {"error": "缺 baseline 或 kp_parts"}
    plan = build_plan(baseline, kp_parts)
    return {
        "name": plan.get("name") or "",
        "model": plan.get("model") or "",
        "series": plan.get("series") or "",
        "form": plan.get("form") or "",
        "summary": plan.get("summary") or {},
        "unmatched": plan.get("unmatched") or [],
        "selling_points": _truncate(plan.get("selling_points") or "", 400),
    }


def _search_cases_handler(case_cfg: dict):
    """构造 search_cases 工具 handler（闭包捕获用户可配的 case_source/top_k/match）。

    底层复用 CaseProvider（InternalBomCaseProvider 查 rules.bom_cases，只读不入库）。
    case_cfg 来自 llm_agent 节点 config（画布抽屉可改）：case_source / case_top_k / case_match。
    """
    top_k_default = int(case_cfg.get("case_top_k") or 2)
    provider_cfg = {
        "case_source": case_cfg.get("case_source", "internal"),
        "case_match": case_cfg.get("case_match", "tags_keyword"),
    }

    async def _h(args: dict) -> Any:
        from app.services.case_provider import get_case_provider
        provider = get_case_provider(provider_cfg)
        query = args.get("query") or args.get("requirement") or ""
        tags = args.get("tags") if isinstance(args.get("tags"), list) else None
        try:
            top_k = int(args.get("top_k") or top_k_default)
        except (TypeError, ValueError):
            top_k = top_k_default
        cases = provider.retrieve(query, tags=tags, top_k=top_k)
        return {"count": len(cases), "cases": cases}
    return _h


# ── 工具元数据全集（name/description/parameters + handler）—— 画布可勾选启用 ──
_TOOL_SPECS = {
    "select_models": {
        "description": ("根据服务器需求挑选在售机型基准配置候选，返回候选清单"
                        "（名称/系列/形态/盘位数/卖点）。当能确定服务器类型(通用/AI/存储)、"
                        "形态(1U/2U/4U)或系列时调用，用于锁定机型。"),
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_name": {"type": "string", "description": "服务器类型全名，如 通用服务器/AI服务器/存储服务器；不确定可省略"},
                "form": {"type": "string", "description": "机箱形态 1U/2U/4U；不确定可省略"},
                "series": {"type": "string", "description": "产品系列 Orion/Polaris/Intel；不确定可省略"},
                "usage": {"type": "string", "description": "用途/场景关键词，如 web/数据库/虚拟化"},
            },
        },
        "handler": _tool_select_models,
    },
    "pick_kp_parts": {
        "description": ("为指定机型类型匹配合适的 CPU/内存/硬盘/GPU/网卡等关键配件，"
                        "返回每类一件代表件的料号/规格/数量。需先确定服务器类型或类目。"),
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_name": {"type": "string", "description": "服务器类型全名（据此推断标准配件类目）"},
                "categories": {"type": "array", "items": {"type": "string"}, "description": "要匹配的配件类目，如 CPU/GPU/Memory/HDD/NIC"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "需求里的型号/规格关键词"},
                "requirement_text": {"type": "string", "description": "原始需求文本（用于规格/数量解析）"},
            },
        },
        "handler": _tool_pick_kp_parts,
    },
    "build_plan": {
        "description": ("把一个机型基准配置 + 配件清单组合成整机方案，返回机型名/总成本/未匹配件清单。"
                        "用于预估方案成本与完整性。"),
        "parameters": {
            "type": "object",
            "properties": {
                "baseline": {"type": "object", "description": "select_models 返回的某个候选机型（含 id/name/series/form 等）"},
                "kp_parts": {"type": "array", "items": {"type": "object"}, "description": "pick_kp_parts 返回的配件清单"},
            },
            "required": ["baseline", "kp_parts"],
        },
        "handler": _tool_build_plan,
    },
    "search_cases": {
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
}

# 全部可用工具名（给画布抽屉候选 + 默认值用）
ALL_TOOL_NAMES = list(_TOOL_SPECS.keys())


def build_tool_registry(config: dict) -> ToolRegistry:
    """按节点 config 启用的工具集建 registry。

    config.enabled_tools: list[str] —— 启用的工具名（画布抽屉勾选）；
    未配置或空 → 默认启用全集（向后兼容）。
    """
    cfg = config or {}
    enabled = cfg.get("enabled_tools") or list(_TOOL_SPECS.keys())
    reg = ToolRegistry()
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
        reg.register(name, spec["description"], spec["parameters"], handler)
    return reg
