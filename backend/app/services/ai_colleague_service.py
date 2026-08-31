"""AI 同事配置服务。

所有角色、工具、入口、分派规则都从 system_config.ai_colleagues 读取。
业务代码只依赖 role_key / entry_point / tool name 这些配置语义，
不在代码里写死某个同事或某份工具清单。
"""
import logging
from typing import Any, Optional

_CONFIG_KEY = "ai_colleagues"

DATA_SOURCE_CATALOG = [
    {"key": "opportunities", "label": "商机数据", "description": "商机线索与商机详情数据"},
    {"key": "dashboard", "label": "经营看板", "description": "商机/配置统计、分布、排行与趋势"},
    {"key": "kp_price", "label": "配件价格库", "description": "KP 配件价格与料号"},
    {"key": "bom", "label": "整机方案/BOM", "description": "整机方案与 BOM 配置"},
    {"key": "cost", "label": "成本利润", "description": "方案成本与利润分析"},
    {"key": "requirement", "label": "需求分析", "description": "需求理解与需求分析流程"},
    {"key": "candidate_search", "label": "机型选型", "description": "候选机型检索与选型"},
    {"key": "quotation", "label": "报价单", "description": "报价单与报价策略"},
    {"key": "server_catalog", "label": "机型目录", "description": "服务器类型与机型目录"},
    {"key": "server_product_content", "label": "产品内容", "description": "服务器介绍页与机型详情内容"},
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
    """实际数据权限 = 配置的数据域。"""
    sources: set = set()
    if isinstance(colleague, dict):
        raw = colleague.get("data_sources")
        if isinstance(raw, list):
            sources.update(_canonical_data_source(item) for item in raw if str(item or "").strip())
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
        from app.services.data_boundary import normalize_colleague
        cfg["colleagues"] = [normalize_colleague(c) for c in cfg.get("colleagues") or [] if isinstance(c, dict)]
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
    from app.services.agent_tool_specs import build_tool_registry
    allowed = colleague_tool_ids(colleague_or_role_key)
    config = {"enabled_tools": allowed} if allowed is not None else {}
    return build_tool_registry(config, allowed_tool_ids=allowed)


# ── 智能转接（LLM 判官，2026-08-29 取代关键词规则）────────────────────────
# 宪法：判断依据 = 员工名册（职责/技能，业务数据）；判断本身 = 模型理解。
# 任何关键词清单都是旧世界的遗产，禁止回来。

_DISPATCH_SYSTEM_PROMPT = (
    "你是 CPQ AI 办公室的转接判官。根据用户消息，从在册 AI 同事名册中选出最合适的一位接手；"
    "没有合适的专业同事、或消息只是闲聊/问候/与业务无关时，colleague_role_key 留空字符串（由总助自己回复）。"
    "用户明确点名某位同事（姓名）时，直接选那位。判断依据只能是名册中的职责描述与技能清单。"
    "只能输出 JSON：{\"colleague_role_key\": \"名册中的 role_key 或空字符串\", \"reason\": \"一句话中文理由\"}"
)


def _skill_names(colleague: dict) -> list:
    names = []
    for item in colleague.get("skills") or []:
        name = item if isinstance(item, str) else str((item or {}).get("name") or "")
        if name.strip():
            names.append(name.strip())
    return names


def _dispatch_roster(config: dict) -> list:
    """可转派同事名册：名字/职责/技能，转接判断的唯一事实来源。"""
    roster = []
    for c in (config.get("colleagues") or []):
        if not c.get("enabled", True) or not c.get("dispatchable", True):
            continue
        duty = str(c.get("system_prompt") or c.get("opening_message") or "").strip()
        roster.append({
            "role_key": c.get("role_key"),
            "name": c.get("name") or c.get("role_key"),
            "skills": _skill_names(c),
            "职责": duty[:120],
        })
    return roster


_DISPATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "colleague_role_key": {"type": "string", "description": "名册中的 role_key，无合适人选时留空"},
        "reason": {"type": "string", "description": "一句话中文理由"},
    },
}


def find_mentioned_colleague(text: str, config: Optional[dict] = None) -> Optional[dict]:
    """解析消息里的 @点名（@名字 / @role_key），确定性路由，优先于 AI 判断。

    用户自己点的名就是路由结果，不再走 LLM 判官；点名不匹配任何在册同事时返回 None
    （消息按普通文本处理）。
    """
    import re
    config = config or _load_config()
    match = re.search(r"@([^\s@，。,；;：:！!？?·…\"'（）()]+)", str(text or ""))
    if not match:
        return None
    token = match.group(1).strip()
    if not token:
        return None
    low = token.lower()
    for c in (config.get("colleagues") or []):
        if not c.get("enabled", True) or not c.get("dispatchable", True):
            continue
        name = str(c.get("name") or "").strip()
        rk = str(c.get("role_key") or "").strip()
        if (name and (name == token or name in token or token in name)) or (rk and rk.lower() == low):
            return c
    return None


def get_team_lead_role_key() -> str:
    """团队 leader 的 role_key（画布 team_graph 设置，默认方案助手）。调度权只属于 leader。"""
    config = _load_config()
    graph = (config.get("layout") or {}).get("team_graph") or {}
    return str(graph.get("lead_role_key") or "assistant").strip() or "assistant"


def colleague_roster_digest() -> list:
    """在册同事名册摘要（名字/职责/技能）。转接判官与私聊转接建议提示共用的单源（DB 业务数据）。"""
    return _dispatch_roster(_load_config())


async def resolve_assistant_message_target_async(
    text: Optional[str],
    context_summary: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[dict]:
    """总助消息转接：LLM 按名册判断该谁接手；失败/超时/无合适人选一律 None（总助自己接）。"""
    config = _load_config()
    if not (text or context_summary) or not bool(config.get("dispatch_enabled", True)):
        return None
    roster = _dispatch_roster(config)
    if not roster:
        return None
    import json as _json
    from app.services import llm_client
    messages = [
        {"role": "system", "content": _DISPATCH_SYSTEM_PROMPT},
        {"role": "user", "content": (
            "在册同事名册：\n" + _json.dumps(roster, ensure_ascii=False) +
            "\n\n上下文摘要：" + (str(context_summary or "") or "无")[:400] +
            "\n\n用户消息：" + str(text or "")[:800]
        )},
    ]
    try:
        data = await llm_client.chat_json(
            messages,
            schema=_DISPATCH_SCHEMA,
            model=model or None,
            temperature=0.0,
            timeout=8.0,
            max_attempts=1,
            reasoning_effort="low",
        )
    except Exception as exc:
        logger.debug("dispatch LLM 判断失败（总助自己接）: %s", exc)
        return None
    role_key = str((data or {}).get("colleague_role_key") or "").strip()
    if not role_key:
        return None
    for c in (config.get("colleagues") or []):
        if c.get("role_key") == role_key and c.get("enabled", True) and c.get("dispatchable", True):
            out = dict(c)
            out["_dispatch_reason"] = str((data or {}).get("reason") or "")
            return out
    return None


def resolve_dispatch_target(
    role_key: Optional[str] = None,
) -> Optional[dict]:
    """显式指定 role_key 时解析同事；自然语言转接走 resolve_assistant_message_target_async（AI 判断）。"""
    if not role_key:
        return None
    config = _load_config()
    for c in (config.get("colleagues") or []):
        if c.get("role_key") == role_key and c.get("enabled", True) and c.get("dispatchable", True):
            return c
    return None


async def resolve_chat_target(
    bound_role_key: Optional[str],
    text: str,
    context_summary: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[Optional[dict], Optional[dict]]:
    """回合路由（2026-08-30 定调：转接只在群里）。

    - 绑定会话（thread.colleague_role_key 有值，含方案助手自己）→ 锁定身份，永不转接；
      自己能办的事自己办，超出能力范围由角色在对话里口头建议找谁（提示词规则，不走本机制）。
    - 未绑定线程 = 团队群 → @点名确定性路由；无 @ 时 LLM 判官按名册判断（仅 leader=方案助手时启用）。
    返回 (colleague, dispatch_target)；dispatch_target 非 None 表示群内转接（调用方落可见标记）。
    """
    if bound_role_key:
        return get_colleague(bound_role_key), None
    mentioned = find_mentioned_colleague(text)
    if mentioned is not None:
        return mentioned, None
    colleague = None
    if get_team_lead_role_key() == "assistant":
        colleague = await resolve_assistant_message_target_async(text, context_summary, model=model)
    if colleague is not None:
        return colleague, colleague
    return get_colleague("assistant"), None
