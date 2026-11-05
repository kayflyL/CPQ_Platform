# -*- coding: utf-8 -*-
"""agent_tool_specs —— 工具元数据 + registry 构建。声明 schema，不含业务实现。"""
from typing import List, Optional
from ai_office.agent_tool_registry import ToolRegistry
from app.services.agent_tool_handlers import (
    _search_cases_handler, _tool_ask_user)

# ── 工具元数据全集（name/description/parameters + handler）—— 画布可勾选启用 ──
_TOOL_SPECS = {
   "ask_user": {
        "summary": "把需要客户决策的问题升格为结构化选项卡（question 一句话 + options 2-4 个）。一回合一卡；需求分析流程内的客户拍板场景使用。",
       "description": ("【需求分析·大脑回合】把需要客户决策的问题升格为结构化选项卡"
                        "（question 一句话 + options 2-4 个 label）。问题绑定某一部件行时带 row=行键原文，"
                        "客户点击后：选项带 pick 即锁定该料号，带 pick_all 即批量锁定全部推荐行，否则答案记进该行的补充回答；"
                        "确认目录字段（服务器类型/平台类型/机箱形态）时绑定 slot=字段 key（如 server_type），"
                        "选项带 value=规范值 时按 value 落库（label 只作展示）。"
                        "question 会作为卡片表头完整展示——旁白里不要再复述这个问题"
                        "（旁白只给背景与依据，提问以卡为准，两处同文=客户看两遍同一问）。"
                        "行卡（带 row）的出路选项由引擎补齐：「换近替代」（pick=库内候选料）与"
                        "「保持原需求」（waived=true：行保留 + 标注「库内无料、客户已知悉」，终检放行）；"
                        "客户不需要这个类目时用 absent。"
                        "row 取行清单给出的 row_id 原文（等价别名会被归一）：解析不到回 row_unknown，"
                        "已锁定/已了结的行也会被拒收（确需重开该行再问时带 reopen=true）。"
                        "需求分析流程外不可用。"),
        "default_enabled": False,
        "handler": _tool_ask_user,
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向客户确认的问题（一句话，用客户的语言）"},
                "options": {
                    "type": "array",
                    "description": "2-4 个互斥选项；某选项就是库内候选料时把该料带上 pick（并把推荐数量带上 qty），客户点选即落地",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "选项文案（客户点选的值）"},
                            "description": {"type": "string", "description": "选项补充说明（可选）"},
                            "recommended": {"type": "boolean", "description": "该选项是否是你的推荐项（客户界面上会标「推荐」）"},
                            "qty": {"type": "integer", "description": "该选项推荐数量（客户可在卡上步进调整）。按已锁定机型扩展能力的物理上限与需求总量推荐（如 768GB÷64G=12 条），别只报型号不报数量"},
                            "qty_max": {"type": "integer", "description": "数量上限（可选；不填则取行申报量与机型物理边界的较大值）"},
                            "pick": {"type": "object",
                                     "description": "该选项对应的库内候选料（取 query_parts 返回的 part_id/name/price）。带上后客户点选即锁定该料号；不带则点击只作该行的补充说明、不会落地。",
                                     "properties": {"part_id": {"type": "string"}, "name": {"type": "string"},
                                                    "price": {"type": "number"}, "qty": {"type": "integer"}}},
                            "absent": {"type": "string", "description": "类目级逃生选项：客户不需要这个类目（如 GPU 不配/自备）时填类目名"},
                            "pick_all": {"type": "boolean", "description": "套装整体接受项：该选项=接受当前全部推荐态行（≥2 行 AI 推荐待确认时用）；点选后所有推荐行一次性批量锁定"},
                            "waived": {"type": "boolean", "description": "行的第三结局选项：库内确实没有该行要的料，客户已知悉并保持原需求（行保留 + 标注，终检放行）。与 row 一起用"},
                            "slot": {"type": "string", "description": "该选项写入的登记表字段 key（目录字段确认用，如 platform_type）"},
                            "value": {"type": "string", "description": "该选项对应的规范值（目录字段确认用；label 是给客户看的文案，value 是落库值）"},
                        },
                        "required": ["label"],
                    },
                },
                "row": {"type": "string", "description": "该问题绑定的部件行（可选）：行清单里的 row_id 原文"},
                "reopen": {"type": "boolean", "description": "该行已锁定/已了结时是否仍然发问（默认 false：拒收，避免把同一行反复问客户）。仅当你确实要重开这一行时置 true"},
                "slot": {"type": "string", "description": "该问题绑定的登记表字段 key（可选）。目录字段（server_type/platform_type/chassis_form）必须绑定，客户点选后系统自动登记确认值"},
            },
            "required": ["question", "options"],
        },
    },
   "ask_user": {
        "summary": "向用户提问（反问的一种结构化形式）：描述问题的形状，系统渲染成选择卡或表单卡并等待回答。",
        "category": "business",
        "default_enabled": False,
        "description": (
            "「向人提问」动作：需要用户给信息或做选择时调用。载荷即问题的形状："
            "有 options（2~4 个 {label,description?,recommended?}）渲染成单选卡（系统自动追加"
            "「Other」自由输入，recommended 的排首位带推荐标记）；有 fields（1~8 个 "
            "{key,label,type?,placeholder?}）渲染成表单卡；二者只能给一个。一次只问一个问题——"
            "已有未回答的问题时本工具会报错。用户回答后内容结构化回流对话，据此调用后续工具。"
            "有明确候选且说得出名字就用 options，开放信息才用 fields；都不合适直接文本反问，不必调本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "问题正文（如：CF1 的 L6 整机价是多少？）"},
                "hint": {"type": "string", "description": "给用户的补充说明（一句话）"},
                "options": {"type": "array", "items": {"type": "object",
                            "properties": {"label": {"type": "string"},
                                           "description": {"type": "string"},
                                           "recommended": {"type": "boolean"}},
                            "required": ["label"]},
                            "description": "候选项，2~4 个；recommended=true 的排首位带推荐标记"},
                "fields": {"type": "array", "items": {"type": "object",
                            "properties": {"key": {"type": "string"},
                                           "label": {"type": "string"},
                                           "placeholder": {"type": "string"},
                                           "type": {"type": "string", "enum": ["text", "number"]}},
                            "required": ["key", "label"]},
                            "description": "输入字段清单，1~8 个；与 options 二选一"},
            },
            "required": ["title"],
        },
        "handler": _tool_ask_user,
    },
}


# ── 工具声明清单（第 7 步工具声明面，ABI 工具契约分册）：域清单住宿主侧 ──
# tool_manifests/ 按域声明（操作+契约+参数 schema），引擎只做合并消费。
_MANIFEST_MODULES = ('app.services.tool_manifests.delivery_quotation', 'app.services.tool_manifests.requirement', 'app.services.tool_manifests.opportunity', 'app.services.tool_manifests.office', 'app.services.tool_manifests.data')
_MANIFEST_TOOLS = {}
for _m in _MANIFEST_MODULES:
    import importlib
    for _name, _spec in (getattr(importlib.import_module(_m), 'TOOLS') or {}).items():
        if _name in _TOOL_SPECS or _name in _MANIFEST_TOOLS:
            raise ValueError(f'工具跨域重复声明：{_name}')
        _MANIFEST_TOOLS[_name] = _spec
_TOOL_SPECS.update(_MANIFEST_TOOLS)

# 全部可用工具名（给画布抽屉候选 + 默认值用）
ALL_TOOL_NAMES = list(_TOOL_SPECS.keys())


def _default_tool_text(name: str, spec: dict) -> dict:
    """某工具的四字段默认文本（= agent_tool_text 的种子值）。"""
    from ai_office.agent_tool_display import default_display
    d = default_display(name)
    return {
        "display_name": d["display_name"],
        "one_liner": d["one_liner"],
        "description": d["description"] or spec["description"],
        "model_brief": spec.get("summary") or spec["description"],
    }


def tool_text_seed_rows() -> List[dict]:
    """agent_tool_text 的启动种子（DB 唯一权威源的迁移种子，运行时不读这里）：
    人类层默认值（agent_tool_display）+ 模型契约默认值（summary）。"""
    return [dict({"name": name}, **_default_tool_text(name, spec))
            for name, spec in _TOOL_SPECS.items()]


def _tool_text_overrides() -> dict:
    """rules.agent_tool_text 覆盖行（fail-safe：DB 异常时回代码默认，不影响回合）。"""
    try:
        from app.repository.agent_tool_text_repo import AgentToolTextRepository
        repo = AgentToolTextRepository()
        try:
            return repo.get_overrides()
        finally:
            repo.close()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("tool text overrides 读取失败，回代码默认", exc_info=True)
        return {}


def _spec_parameters(spec: dict) -> dict:
    """取工具参数 schema：带 parameters_factory 的惰性解析（如 fill_requirement 的 schema
    从登记表字段契约实时生成——导入期不读 DB，每次取用拿最新配置），否则用静态声明。"""
    factory_path = str(spec.get("parameters_factory") or "").strip()
    if factory_path:
        try:
            import importlib
            module_name, _, func_name = factory_path.rpartition(".")
            return getattr(importlib.import_module(module_name), func_name)()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("工具参数工厂解析失败 %s", factory_path)
    return spec.get("parameters") or {"type": "object", "properties": {}}


# ── 工具轨迹记录（通用渲染，不认任何工具名）─────────────────────────────
# 大脑跨回合注入的工作记录由这里生成：只从调用实参/结果里抽事实（标量保留、
# 长串截断、列表只报条数），不写任何按工具名分支的文案。新增工具零改动即可被记录。
_TRACE_STR_MAX = 60
_TRACE_LIST_MAX = 8
_TRACE_DEPTH_MAX = 2
_TRACE_SKIP_KEYS = frozenset({"ok", "error", "current", "rows", "results", "message", "answer"})


def _trace_trim(value, depth: int = 0):
    """把一次调用的实参压到可读体量：长串截断、长列表只留前几项、深对象折叠。"""
    if isinstance(value, str):
        return value if len(value) <= _TRACE_STR_MAX else value[:_TRACE_STR_MAX] + "…"
    if isinstance(value, dict):
        if depth >= _TRACE_DEPTH_MAX:
            return "{…}"
        return {str(k): _trace_trim(v, depth + 1) for k, v in list(value.items())[:12]}
    if isinstance(value, (list, tuple)):
        if depth >= _TRACE_DEPTH_MAX:
            return len(value)
        return [_trace_trim(v, depth + 1) for v in list(value)[:_TRACE_LIST_MAX]]
    return value


def trace_note(call: dict) -> Optional[dict]:
    """一次工具调用的工作记录（通用；引擎侧不认识工具名）。

    形状：{"tool": 名, "args": 截断实参, "ok": …, "error": …, "result": 标量/条数摘要}。
    用途：跨回合注入「你已做过什么」，避免大脑每轮从零开始重复检索/重复提问。
    """
    c = call if isinstance(call, dict) else {}
    name = str(c.get("name") or "").strip()
    if not name:
        return None
    args = c.get("args") if isinstance(c.get("args"), dict) else {}
    res = c.get("result") if isinstance(c.get("result"), dict) else {}
    note: dict = {"tool": name}
    trimmed = {k: v for k, v in args.items() if v not in (None, "", [], {})}
    if trimmed:
        note["args"] = _trace_trim(trimmed)
    if "ok" in res:
        note["ok"] = bool(res.get("ok"))
    if res.get("error"):
        note["error"] = str(res["error"])[:80]
    extra = {}
    for key, value in res.items():
        if str(key) in _TRACE_SKIP_KEYS:
            continue
        if isinstance(value, (int, float, bool)) or (isinstance(value, str) and len(value) <= _TRACE_STR_MAX):
            extra[str(key)] = value
        elif isinstance(value, (list, tuple)):
            extra[str(key)] = len(value)
    if extra:
        note["result"] = extra
    message = str(res.get("message") or "").strip()
    if message:
        note["message"] = message[:80]
    return note


# ── 工具契约（P3 上安全带，命名对齐 MCP 注解）：写语义工具逐个声明 ──────────
# confirm_policy ∈ none（现状无卡：用户输入即信号/低影响幂等）| stage+consent（预览+确认卡）
# 缺省（未登记）= effects:read + stage+consent——保守默认对齐 MCP"未声明按最坏假设"。
# verify = 写后回读函数（"模块.函数"，registry 惰性解析；回读不符=error 事实）。
_TOOL_CONTRACTS: dict = {
}

# 清单内契约并入（域清单条目自带 contract，见 tool_manifests/）
for _mname, _mspec in _MANIFEST_TOOLS.items():
    if _mspec.get('contract'):
        _TOOL_CONTRACTS[_mname] = _mspec['contract']
for _n, _c in _TOOL_CONTRACTS.items():
    if _n in _TOOL_SPECS:
        _TOOL_SPECS[_n]["contract"] = _c
for _s in _TOOL_SPECS.values():
    _s.setdefault("contract", {"effects": "read", "confirm_policy": "none"})


def confirm_policy_for(tool: str) -> str:
    """工具确认策略（P3 确认分级）：从工具契约读声明。住声明表（第 5 步画边界：
    确认策略=声明数据，跟契约表同住；agent_write_confirm 只管存证不再反向依赖本表）。

    ∈ none（免卡：幂等白名单，用户输入即信号）| stage（预览卡）| stage+consent（确认卡）。
    **缺省 = stage+consent**——保守默认对齐 MCP"未声明按最坏假设"：没声明确认策略的
    写工具一律按最高档处理，绝不因契约缺失静默免卡。"""
    try:
        return str((_TOOL_SPECS.get(tool) or {}).get("contract", {}).get("confirm_policy")
                   or "stage+consent")
    except Exception:
        return "stage+consent"


def tool_catalog() -> List[dict]:
    """全量工具目录（无 handler），供前端「AI 工具」目录页与节点抽屉渲染。

    每个条目：name / category(selection|data) / display_name / one_liner（人类层）/
    summary（模型 FC 契约，DB 行说了算）/ description（人话详解）/ parameters / default_enabled /
    custom（与种子值不同的字段名，供前端标「已自定义」与恢复默认）。
    """
    overrides = _tool_text_overrides()
    out: List[dict] = []
    for name, spec in _TOOL_SPECS.items():
        defaults = _default_tool_text(name, spec)
        entry = {
            "name": name,
            "category": spec.get("category") or "workflow",
            "display_name": defaults["display_name"],
            "one_liner": defaults["one_liner"],
            "summary": defaults["model_brief"],
            "description": defaults["description"],
            "parameters": _spec_parameters(spec),
            "default_enabled": bool(spec.get("default_enabled", True)),
            "contract": spec.get("contract") or {"effects": "read", "confirm_policy": "none"},
            "custom": [],
        }
        row = overrides.get(name) or {}
        for field in ("display_name", "one_liner", "description", "model_brief"):
            value = row.get(field)
            if not value:
                continue
            if field == "model_brief":
                entry["summary"] = value
            else:
                entry[field] = value
            if value != defaults[field]:
                entry["custom"].append(field)
        out.append(entry)
    return out


def registered_tool_ids() -> List[str]:
    """返回 agent_tools 注册表里所有工具 ID（供能力 spec 校验 / 默认工具取用）。"""
    return list(_TOOL_SPECS.keys())


def build_tool_registry(config: dict, allowed_tool_ids: list = None) -> ToolRegistry:
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
    reg = ToolRegistry()
    overrides = _tool_text_overrides()
    for name in enabled:
        spec = _TOOL_SPECS.get(name)
        if not spec:
            continue
        handler = spec["handler"]
        if isinstance(handler, str):
            # 声明清单条目用点串引用 handler——清单零 import，注册时惰性解析
            import importlib
            _mod, _fn = handler.rsplit(".", 1)
            handler = getattr(importlib.import_module(_mod), _fn)
        # search_cases 需要用户可配的 case 参数（case_source/top_k/match）→ 闭包注入
        if name == "search_cases":
            handler = _search_cases_handler(cfg)
        if handler is None:
            continue
        # 模型 FC 契约文本（原 summary）：DB 覆盖行优先，无覆盖用代码默认
        brief = (overrides.get(name) or {}).get("model_brief") or spec.get("summary")
        if name == "query_data":
            # schemas() 只暴露 summary——白名单必须挂进 brief 模型才看得见；
            # 模型看不到清单会裸写表名/猜表名，白名单外一律报错。
            from ai_office.data_boundary import query_tables_allow
            tables = query_tables_allow()
            if tables:
                brief += "可读表（仅这些）：" + "、".join(tables) + "。"
        reg.register(name, spec["description"], _spec_parameters(spec), handler, summary=brief,
                     contract=spec.get("contract") or {})
    return reg
