"""AI 同事配置服务。

所有角色、工具、入口、分派规则都从 system_config.ai_colleagues 读取。
业务代码只依赖 role_key / entry_point / tool name 这些配置语义，
不在代码里写死某个同事或某份工具清单。
"""
import logging
from typing import Any, Optional

_CONFIG_KEY = "ai_colleagues"

DATA_SOURCE_CATALOG = [
    {"key": "opportunities", "label": "opportunities", "description": "商机线索与商机详情数据"},
    {"key": "dashboard", "label": "dashboard", "description": "商机/配置统计、分布、排行与趋势"},
    {"key": "kp_price", "label": "kp_price", "description": "KP 配件价格与料号"},
    {"key": "bom", "label": "bom", "description": "整机方案与 BOM 配置"},
    {"key": "cost", "label": "cost", "description": "方案成本与利润分析"},
    {"key": "requirement", "label": "requirement", "description": "需求理解与需求分析流程"},
    {"key": "candidate_search", "label": "candidate_search", "description": "候选机型检索与选型"},
    {"key": "quotation", "label": "quotation", "description": "报价单与报价策略"},
    {"key": "server_catalog", "label": "server_catalog", "description": "服务器类型与机型目录"},
    {"key": "server_product_content", "label": "server_product_content", "description": "服务器介绍页与机型详情内容"},
]

PAGE_SCOPE_CATALOG = [
    {"key": "Opportunities", "label": "商机线索", "description": "维护商机线索列表与经营数据", "data_sources": ["opportunities", "dashboard"]},
    {"key": "OpportunityDetail", "label": "商机详情", "description": "维护商机详情中的 BOM/报价/交付信息", "data_sources": ["opportunities", "quotation"]},
    {"key": "Workspace", "label": "报价工作台", "description": "维护报价工作台并生成 BOM 与报价", "data_sources": ["quotation", "opportunities", "bom", "kp_price", "cost"]},
    {"key": "StrategySelection", "label": "选型配置", "description": "维护策略中心的选型配置流程", "data_sources": ["bom", "kp_price", "cost", "candidate_search"]},
    {"key": "Parts", "label": "配件", "description": "维护配件页与料号库", "data_sources": ["kp_price"]},
    {"key": "Servers", "label": "服务器配置", "description": "维护服务器类型与配置展示", "data_sources": ["server_catalog"]},
    {"key": "ServersAdmin", "label": "服务器管理", "description": "维护服务器管理页与产品系列展示", "data_sources": ["server_catalog", "server_product_content"]},
    {"key": "ServerModels", "label": "机型目录", "description": "维护机型目录列表", "data_sources": ["server_catalog", "server_product_content"]},
    {"key": "ServerModelDetail", "label": "机型详情", "description": "维护机型详情与产品介绍", "data_sources": ["server_catalog", "server_product_content"]},
    {"key": "ServerModelEdit", "label": "编辑机型", "description": "维护机型编辑页的产品内容与介绍", "data_sources": ["server_catalog", "server_product_content"]},
    {"key": "AiOffice", "label": "AI 办公室", "description": "AI 办公室办公区与角色管理", "data_sources": []},
]
_DATA_SOURCE_ALIASES = {"opportunity": "opportunities"}


def get_scope_catalog() -> dict:
    """返回数据来源与页面职责注册表。"""
    return {"data_sources": DATA_SOURCE_CATALOG, "page_scopes": PAGE_SCOPE_CATALOG}


def _canonical_data_source(key: Any) -> str:
    return _DATA_SOURCE_ALIASES.get(str(key or "").strip(), str(key or "").strip())


def effective_data_sources(colleague: Optional[dict]) -> list:
    """实际数据权限 = 负责页面派生的数据域 + 额外配置的数据域。"""
    sources: set = set()
    if isinstance(colleague, dict):
        raw = colleague.get("data_sources")
        if isinstance(raw, list):
            sources.update(_canonical_data_source(item) for item in raw if str(item or "").strip())
        entry_points = colleague.get("entry_points")
        if isinstance(entry_points, list):
            page_keys = {str(item or "").strip() for item in entry_points if str(item or "").strip()}
            for page in PAGE_SCOPE_CATALOG:
                if page["key"] in page_keys:
                    sources.update(page.get("data_sources") or [])
    return sorted(item for item in sources if item)

logger = logging.getLogger(__name__)


def _as_config(value: Any) -> dict:
    if isinstance(value, list):
        return {"version": 1, "colleagues": value}
    if isinstance(value, dict):
        cfg = dict(value)
        if not isinstance(cfg.get("colleagues"), list):
            cfg["colleagues"] = []
        return cfg
    return {"version": 1, "colleagues": []}


def _migrate_runtime_office_layout(config: dict) -> None:
    """Ensure spatial-intent parsing sees the same migrated office layout as the admin API."""
    layout = config.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        config["layout"] = layout
    office = layout.get("office")
    if not isinstance(office, dict):
        office = {}
        layout["office"] = office
    try:
        from app.api.ai_colleagues import _migrate_office_layout
        _migrate_office_layout(office)
    except Exception:
        logger.exception("迁移 AI 办公室布局失败")


def _load_config() -> dict:
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            value = repo.get_value(_CONFIG_KEY, {})
        finally:
            repo.close()
        cfg = _as_config(value)
        _migrate_runtime_office_layout(cfg)
        return cfg
    except Exception:
        logger.exception("读取 AI 同事配置失败")
        return {"version": 1, "colleagues": []}


def get_ai_colleague_config() -> dict:
    """返回完整 AI 同事配置（含行为、分派规则、布局），供任务规划器复用。"""
    return _load_config()


def get_ai_colleagues(include_disabled: bool = True) -> list:
    colleagues = _load_config().get("colleagues") or []
    if include_disabled:
        return list(colleagues)
    return [c for c in colleagues if c.get("enabled", True)]


def get_colleague(role_key: Optional[str]) -> Optional[dict]:
    if not role_key:
        return None
    for c in _load_config().get("colleagues") or []:
        if c.get("role_key") == role_key:
            return c
    return None


def get_team_lead_role_key() -> Optional[str]:
    """返回当前团队 Lead 的 role_key；未显式配置时回退到第一个启用同事。"""
    config = _load_config()
    colleagues = config.get("colleagues") or []
    enabled = [c for c in colleagues if isinstance(c, dict) and c.get("enabled", True)]
    if not enabled:
        return None
    graph = (config.get("layout") or {}).get("team_graph")
    if isinstance(graph, dict) and graph.get("lead_role_key"):
        lead = str(graph.get("lead_role_key"))
        if any(c.get("role_key") == lead for c in enabled):
            return lead
    for colleague in enabled:
        relations = colleague.get("relations") or {}
        if relations.get("team_role") == "lead":
            return str(colleague.get("role_key") or "")
    return str(enabled[0].get("role_key") or "")


def is_colleague_enabled(role_key: Optional[str]) -> bool:
    c = get_colleague(role_key)
    return bool(c and c.get("enabled", True))


def colleague_tool_ids(colleague_or_role_key: Any) -> Optional[list]:
    """返回同事允许的工具名；配置里没有 tool_ids 字段时返回 None（= 不限制，兼容旧配置）。"""
    c = colleague_or_role_key if isinstance(colleague_or_role_key, dict) else get_colleague(colleague_or_role_key)
    if not isinstance(c, dict):
        return None
    tool_ids = c.get("tool_ids")
    if not isinstance(tool_ids, list):
        return None
    return list(tool_ids)


def colleague_allows_tool(colleague_or_role_key: Any, tool_name: str) -> bool:
    allowed = colleague_tool_ids(colleague_or_role_key)
    if allowed is None:
        return True
    return tool_name in allowed


def filter_tool_ids_by_colleague(colleague_or_role_key: Any, tool_ids: list) -> list:
    allowed = colleague_tool_ids(colleague_or_role_key)
    if allowed is None:
        return list(tool_ids or [])
    allowed_set = set(allowed)
    return [t for t in (tool_ids or []) if t in allowed_set]


def build_colleague_tool_registry(colleague_or_role_key: Any):
    from app.services.agent_tools import build_tool_registry
    allowed = colleague_tool_ids(colleague_or_role_key)
    config = {"enabled_tools": allowed} if allowed is not None else {}
    return build_tool_registry(config, allowed_tool_ids=allowed)


def _dispatch_rules(config: dict) -> list:
    rules = (config or {}).get("dispatch_rules")
    return rules if isinstance(rules, list) else []


def _rule_matches(rule: dict, text: Optional[str], context_summary: Optional[str]) -> bool:
    keywords = rule.get("keywords")
    if not isinstance(keywords, list):
        return False
    if not keywords:
        return False
    hay = f"{(text or '')}\n{(context_summary or '')}".lower()
    return any(str(k).strip().lower() in hay for k in keywords if str(k).strip())


def _mentions_colleague(colleague: dict, haystack: str) -> bool:
    if not haystack:
        return False
    for field in ("name", "role_key"):
        value = colleague.get(field)
        if value and str(value).strip().lower() in haystack:
            return True
    return False


def _resolve_team_graph_target(config: dict, text: Optional[str], context_summary: Optional[str]) -> Optional[dict]:
    """画布团队拓扑兜底：自然语言点名 Lead/Subagent 时优先转给该同事。"""
    layout = config.get("layout") or {}
    graph = layout.get("team_graph")
    if not isinstance(graph, dict):
        return None
    haystack = f"{(text or '')}\n{(context_summary or '')}".lower()
    if not haystack:
        return None
    role_keys = list(graph.get("subagent_role_keys") or [])
    lead_role_key = graph.get("lead_role_key")
    if lead_role_key:
        role_keys.append(lead_role_key)
    colleagues = config.get("colleagues") or []
    for role_key in role_keys:
        for colleague in colleagues:
            if colleague.get("role_key") != role_key:
                continue
            if not colleague.get("enabled", True) or not colleague.get("dispatchable", True):
                continue
            if _mentions_colleague(colleague, haystack):
                return colleague
    return None


def resolve_dispatch_target(
    role_key: Optional[str] = None,
    text: Optional[str] = None,
    context_summary: Optional[str] = None,
    entry_point: Optional[str] = None,
) -> Optional[dict]:
    """按配置解析要分派到的 AI 同事。

    优先级：显式 role_key > dispatch_rules 命中 > entry_point 兜底。
    只返回 enabled 且 dispatchable 的同事；找不到返回 None（调用方按总助原行为处理）。
    """
    config = _load_config()
    colleagues = config.get("colleagues") or []

    if role_key:
        for c in colleagues:
            if c.get("role_key") == role_key and c.get("enabled", True) and c.get("dispatchable", True):
                return c
        return None

    if (text or context_summary) and bool(config.get("dispatch_enabled", True)):
        for rule in _dispatch_rules(config):
            if rule.get("enabled", True) is False:
                continue
            if not _rule_matches(rule, text, context_summary):
                continue
            if entry_point and entry_point not in (rule.get("entry_points") or []):
                continue
            target_key = rule.get("role_key")
            for c in colleagues:
                if c.get("role_key") == target_key and c.get("enabled", True) and c.get("dispatchable", True):
                    return c

    team_graph_target = _resolve_team_graph_target(config, text, context_summary)
    if team_graph_target:
        return team_graph_target

    # entry_point 兜底：用于没有自然语言、但明确属于某类入口的调用。
    if entry_point:
        for c in colleagues:
            if c.get("enabled", True) and c.get("dispatchable", True):
                if entry_point in (c.get("entry_points") or []):
                    return c
    return None


def resolve_assistant_message_dispatch(text: str, context_summary: Optional[str] = None) -> dict:
    """解析总助消息应转接的同事，并同时返回命中的规则（供前端展示“由谁接管”）。"""
    config = _load_config()
    colleagues = config.get("colleagues") or []
    if (text or context_summary) and bool(config.get("dispatch_enabled", True)):
        for rule in _dispatch_rules(config):
            if rule.get("enabled", True) is False:
                continue
            if not _rule_matches(rule, text, context_summary):
                continue
            target_key = rule.get("role_key")
            for c in colleagues:
                if c.get("role_key") == target_key and c.get("enabled", True) and c.get("dispatchable", True):
                    return {"colleague": c, "matched_rule": rule}
        team_graph_colleague = _resolve_team_graph_target(config, text, context_summary)
        if team_graph_colleague:
            return {"colleague": team_graph_colleague, "matched_rule": None}
    return {"colleague": None, "matched_rule": None}


def resolve_assistant_message_target(text: str, context_summary: Optional[str] = None) -> Optional[dict]:
    """总助收到自然语言消息后，按 dispatch_rules 解析要转派的同事。"""
    return resolve_assistant_message_dispatch(text, context_summary).get("colleague")
