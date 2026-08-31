# -*- coding: utf-8 -*-
"""AI 角色（对话脑）与 Skill 引擎的接线层——两器官架构的「器官间神经」。

宪法（2026-08-28）：
- 全系统同一时刻只有一个会思考的脑袋：对话期是角色（本模块驱动的 ReAct 循环），执行期是引擎；
- 角色手里只有四样东西：登记表读写（update_requirement_slots）、提交开关（submit_registration）、
  目录查询（catalog_search）、数据边界内的只读查询原语（query_data）；
  引擎返回的缺口是纯数据，怎么问由角色组织语言；
- 本模块不含任何话术表/关键词清单；业务选项（kp_mode 两个值等）全部来自引擎缺口数据。
- query_data 的权限不在提示词里：物理强制在 data_boundary.execute_read（步骤1），
  角色提示词只描述怎么用，不承诺能读到什么。
"""
from __future__ import annotations

import contextvars
import json
import logging
from typing import Any, Callable, Optional

from app.repository.assistant_repo import AssistantRepository
from app.services.agent_react import run_stream_chat_loop
from app.services.assistant_hub import assistant_hub
from app.services.slot_contract import canonical_key, slot_label

logger = logging.getLogger(__name__)

MEMORY_KEY = "skill_chat"


def _mem_key(role_key: str) -> str:
    """技能流程记忆按「线程 + 角色」隔离：专家接手时是干净身份，不会接手别的角色没走完的流程。"""
    return f"{MEMORY_KEY}:{(role_key or 'assistant').strip() or 'assistant'}"

# 工具执行期的线程上下文（react 循环内 handler 读取；run 侧每轮注入）
_TOOL_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("skill_chat_tool_ctx", default={})


def _load_mem(thread_id: str, role_key: str = "assistant") -> dict:
    try:
        repo = AssistantRepository()
        try:
            raw = repo.get_reasoning_state(thread_id)
        finally:
            repo.close()
        data = json.loads(raw or "{}") if raw else {}
        mem = data.get(_mem_key(role_key))
        return dict(mem) if isinstance(mem, dict) else {}
    except Exception:
        logger.exception("读取 skill_chat 记忆失败 thread=%s", thread_id)
        return {}


def _save_mem(thread_id: str, role_key: str, mem: dict) -> None:
    try:
        repo = AssistantRepository()
        try:
            repo.update_reasoning_state(thread_id, {_mem_key(role_key): mem})
        finally:
            repo.close()
    except Exception:
        logger.exception("保存 skill_chat 记忆失败 thread=%s", thread_id)


def _slots_view(ext: dict) -> dict:
    """登记表可读视图（角色提示词里展示的当前状态）：即需求表（RequirementSlots 干净键）。

    与引擎 normalize 产出的 artifact 同构，让角色「看到的表 = 要填的表 = 下游读的表」。
    旧 ext 信号键名（cpu/…）不再作为写契约暴露给角色。
    """
    from app.services.portal_flow_adapter import requirement_slots_from_ext
    view = dict(requirement_slots_from_ext(ext or {}))
    kp_mode = (ext or {}).get("kp_mode")
    if kp_mode not in (None, "", [], {}):
        view["kp_mode"] = kp_mode
    return view


def clear_memory(thread_id: str, role_key: str = "assistant") -> None:
    _save_mem(thread_id, role_key, {})


def _match_card_signal(mem: dict, slot: str, value: str) -> Optional[dict]:
    """从最近一张选项卡的结构化载荷里按 (slot, value) 匹配 signal（发卡时持久化的原始数据）。"""
    for o in ((mem.get("last_card") or {}).get("options") or []):
        if str(o.get("slot") or "") == slot and str(o.get("value") or "") == value \
                and isinstance(o.get("signal"), dict) and o.get("signal"):
            return o.get("signal")
    return None


# 逐项配件卡可手动输入型号的槽（raid 无型号契约不开放）
_PART_PICK_SLOTS = {"gpu", "cpu", "memory", "drives"}


def _signal_with_qty(signal: dict, qty: int, pick_meta: dict) -> dict:
    """数量覆盖（前端 stepper 参数）：克隆留底 signal 改数量，按机箱能力 clamp。
    数量是参数不是信号语义——服务端单点收口，客户端只传数字。"""
    import copy
    qty = max(1, int(qty or 1))
    meta = pick_meta if isinstance(pick_meta, dict) else {}
    gpu_cap = int(meta.get("gpu_slots") or 0) or 8
    dimm_cap = int(meta.get("max_dimm") or 0) or 8
    cpu_cap = int(meta.get("max_cpu") or 0) or 2
    sig = copy.deepcopy(signal)
    try:
        if isinstance(sig.get("gpu"), list) and sig["gpu"]:
            sig["gpu"][0]["qty"] = min(qty, gpu_cap)
        elif isinstance(sig.get("cpu"), dict):
            sig["cpu"]["qty"] = min(qty, cpu_cap)
        elif isinstance(sig.get("memory"), dict):
            sig["memory"]["qty"] = min(qty, dimm_cap)
        elif isinstance(sig.get("drives"), list) and sig["drives"]:
            sig["drives"][0]["qty"] = min(qty, 16)
        else:
            return signal
    except Exception:
        logger.exception("数量覆盖失败，回退原 signal")
        return signal
    return sig


def _manual_model_signal(mem: dict, slot: str, text: str) -> Optional[dict]:
    """自由输入型号 → 目录模糊匹配构造 signal（未命中返回 None，走登记表白盒路径）。"""
    meta = (mem.get("last_card") or {}).get("pick_meta") or {}
    if not isinstance(meta, dict) or not meta:
        return None
    from app.services.part_selector import manual_signal_for_text
    try:
        return manual_signal_for_text(slot, text, str(meta.get("server_type_name") or ""),
                                       baseline=meta)
    except Exception:
        logger.exception("手动型号目录匹配失败 slot=%s", slot)
        return None


# ── 三个角色动作（注册进全局工具表，经 _TOOL_CTX 取线程状态）────────────────

def _emit_slots_sync(sink, slots: dict, requirement_text: str = "") -> None:
    """登记表被角色更新后，异步广播一次「线索登记表」卡片（与引擎 normalize 同格式）。
    放在同步工具里用 create_task 派发，绝不阻塞 ReAct 循环；sink 不可用则静默降级。"""
    if not callable(sink):
        return
    payload = {"type": "node_trace", "step": "agent_fill", "label": "需求理解填表",
               "status": "running",
               "artifact": {"kind": "requirement_slots", "title": "线索登记表", "data": {**slots, "requirement_text": requirement_text}}}
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        loop.create_task(sink(payload))
    except Exception:
        logger.exception("广播需求槽失败")


def tool_update_requirement_slots(args: dict) -> dict:
    ctx = _TOOL_CTX.get()
    ext = ctx.get("ext")
    if ext is None:
        return {"ok": False, "error": "会话上下文缺失"}
    fill = args.get("fill") if isinstance(args.get("fill"), dict) else (args or {})
    # 类型契约：信号槽只收结构（对象/数组）。字符串填入=违约，当场退回并给正确形状，
    # 让模型 ReAct 当轮自纠——语义理解归模型，引擎不做字符串解析。
    _fill_obj_keys = {"cpu", "memory", "drives", "storage", "gpu", "nic", "raid", "psu"}
    bad = [k for k, v in (fill or {}).items()
           if k in _fill_obj_keys and isinstance(v, str) and str(v).strip()]
    if bad:
        return {"ok": False, "error": "signal_slots_require_objects",
                "hint": "配件槽必须用结构化值（对象/数组），不能是一句话文本。"
                        "正确形状示例：gpu=[{\"model\":\"智铠100\",\"qty\":4}]；"
                        "cpu={\"model\":\"EPYC 9745\",\"qty\":2}；"
                        "memory={\"total_gb\":256} 或 {\"per_stick_gb\":64,\"qty\":8}；"
                        "drives=[{\"capacity\":\"2048G\",\"qty\":2,\"type\":\"SSD\"}]；"
                        "raid=[{\"model\":\"9460-8i\",\"qty\":1}]；"
                        "psu={\"wattage\":1200,\"qty\":2}。"
                        f"请把 {'、'.join(bad)} 按上述形状重新登记。"}
    from app.services.capabilities import _apply_extracted_slots
    from app.services.slot_extractor import apply_structured_slots
    changed = _apply_extracted_slots(ext, fill or {}, allow_overwrite=True)
    _slot_notes: list = []
    try:
        _slot_notes = apply_structured_slots(ext, fill or {}, str(ctx.get("user_text") or "")) or []
    except Exception:
        logger.exception("结构化槽位补充失败")
    ctx.get("save")()
    _emit_slots_sync(ctx.get("event_sink"), _slots_view(ext), str(ctx.get("user_text") or ""))
    return {"ok": True, "changed": changed, "slots": _slots_view(ext), "audit": _slot_notes}


def tool_submit_registration(args: dict) -> dict:
    ctx = _TOOL_CTX.get()
    ext = ctx.get("ext") or {}
    from app.services.skill_phases import model_signals_ready
    if not model_signals_ready(ext):
        return {"ok": False, "error": "scene_missing",
                "hint": "场景（服务器类型）还不明确，先弄清客户业务场景再提交"}
    # 目录词表校验前置到提交口：非目录类型提交后引擎必拒（词表失配→场景缺口），会形成
    # 「问→答→再问」循环；在这里拒绝并列出目录选项，模型当轮即可纠正或向客户确认。
    filled = str(ext.get("server_type_name") or ext.get("server_type") or "").strip()
    if filled:
        from app.repository.server_catalog_repo import ServerCatalogRepository
        catalog = [str(t.get("name") or "").strip() for t in ServerCatalogRepository().list_types() if t.get("name")]
        if catalog and filled not in catalog:
            return {"ok": False, "error": "invalid_scene",
                    "hint": f"「{filled}」不是在售目录里的服务器类型，不能提交。向客户确认后改用目录类型登记"
                            f"（目录类型：{'、'.join(catalog)}），或把该表述登记到对应信号槽位。"}
    on_submit = ctx.get("on_submit")
    if callable(on_submit):
        on_submit()
    return {"ok": True, "note": "登记表已提交，配置引擎开始执行，请等待结果后向用户汇报"}


def tool_catalog_search(args: dict) -> dict:
    """在售目录查询（推荐的事实来源）：types=类型清单；models=按类型/系列/形态查机型（含价格）。

    无任何过滤条件的 models 查询=浏览全目录（角色推荐场景的合法动作），
    按类型逐个取再合并；引擎的「无信号返空」守卫只属于选型，不拦目录浏览。
    """
    kind = str((args or {}).get("kind") or "models").strip()
    limit = int((args or {}).get("limit") or 8)
    try:
        if kind == "types":
            from app.repository.server_catalog_repo import ServerCatalogRepository
            return {"ok": True, "types": [t.get("name") for t in ServerCatalogRepository().list_types() if t.get("name")]}
        if kind == "parts":
            # 配件目录（角色「有什么配件可选」的事实来源）：按品类+系列适配过滤，
            # 与引擎落地同一 applicable 语义，推荐给客户的件必然装得上。
            cat = str((args or {}).get("category") or "").strip()
            p_series = str((args or {}).get("series") or "").strip()
            if not cat:
                from app.services.part_selector import list_kp_categories
                return {"ok": True, "categories": list_kp_categories(),
                        "hint": "先按 category=品类 查询，可选 series 过滤适配平台"}
            from app.repository.kp_repo import KPRepository
            from app.services.part_selector import _series_ok
            _repo = KPRepository()
            try:
                rows = _repo.get_by_category_with_specs(cat)
            finally:
                _repo.close()
            if p_series:
                rows = [r for r in rows if _series_ok(r.get("applicable"), p_series)]
            pout = []
            price_ok = bool(_TOOL_CTX.get().get("price_ok", True))
            for r in rows[:max(1, min(limit, 12))]:
                item = {"name": r.get("model"), "category": cat,
                        "applicable_series": (r.get("applicable") or {}).get("series")
                        if isinstance(r.get("applicable"), dict) else None}
                if price_ok:
                    try:
                        if float(r.get("price") or 0) > 0:
                            item["price"] = float(r.get("price"))
                    except (TypeError, ValueError):
                        pass
                pout.append(item)
            return {"ok": True, "parts": pout}
        from app.api.candidate_search import select_models
        type_name = str((args or {}).get("type_name") or "").strip() or None
        series = str((args or {}).get("series") or "").strip() or None
        form = str((args or {}).get("form") or "").strip() or None
        rows: list = []
        if not any([type_name, series, form]):
            from app.repository.server_catalog_repo import ServerCatalogRepository
            for t in ServerCatalogRepository().list_types():
                if len(rows) >= limit:
                    break
                rows.extend(select_models(usage=None, server_type_name=str(t.get("name") or "").strip() or None, limit=limit) or [])
        else:
            rows = select_models(usage=None, server_type_name=type_name, series=series, form=form, limit=limit) or []
        out = []
        price_ok = bool(_TOOL_CTX.get().get("price_ok", True))
        for r in rows[:max(1, min(limit, 12))]:
            item = {"name": r.get("name"), "type": r.get("server_type_name"), "series": r.get("series"),
                    "form": r.get("form")}
            if price_ok:
                item["price"] = r.get("total_price")
            out.append(item)
        return {"ok": True, "models": out}
    except Exception as exc:
        logger.exception("catalog_search 失败")
        return {"ok": False, "error": str(exc)}


def tool_query_data(args: dict) -> dict:
    """query_data：数据边界内的只读 SELECT 原语（2026-08-29 步骤2）。

    权限全部在 execute_read（物理校验+只读事务+超时+行数上限+列脱敏）；
    这里只做上下文接线与审计。SQL 报错原样回传，模型据此自纠。
    """
    ctx = _TOOL_CTX.get()
    boundary = ctx.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("mode") != "allow_read":
        return {"ok": False, "error": "数据边界为拒绝模式（deny_all），无读取权限"}
    sql = str((args or {}).get("sql") or "").strip()
    if not sql:
        return {"ok": False, "error": "缺 sql 参数（单条只读 SELECT）"}
    try:
        limit = int((args or {}).get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    from app.services.data_boundary import execute_read
    out = execute_read(sql, boundary, limit=limit)
    logger.info("query_data role=%s ok=%s rows=%s truncated=%s sql=%s",
                ctx.get("role_key") or "?", bool(out.get("ok")),
                out.get("row_count") or 0, bool(out.get("truncated")),
                " ".join(sql.split())[:300])
    return out


# ── 角色的需求收集提示词（对脑的指令，非话术表）────────────────────────────

def requirement_prompt(slots: dict, price_ok: bool = True, query_data_ok: bool = False,
                       flow_steps: Optional[list] = None) -> str:
    price_rule = (
        "推荐必须带理由（价格/形态/场景匹配），不知道就查，禁止编造型号价格。"
        if price_ok else
        "你没有价格查看权限：目录查询结果不含价格，回复中禁止出现任何价格、金额、报价数字（凭记忆编造也不行）；"
        "推荐理由基于产品定位/形态/场景匹配。客户主动问价时，引导其联系成本核算或方案助手。"
    )
    data_rule = (
        "\n7. 需要业务数据（商机/报价/目录明细）时，用 query_data 执行只读 SELECT："
        "先查 information_schema.tables / information_schema.columns 看清可读表与列，再写查询；"
        "工具返回的报错信息是修正提示，改 SQL 重试；被数据边界拒绝的表不要反复尝试。"
        if query_data_ok else ""
    )
    # 流程步骤块（数据驱动：来自 Skill 画布节点的 label/description，画布编辑即变）
    plan_rule = ""
    if flow_steps:
        step_lines = []
        for s in flow_steps:
            label = str(s.get("label") or "").strip()
            desc = str(s.get("description") or "").strip()
            step_lines.append(f"- {label}：{desc}" if desc else f"- {label}")
        plan_rule = ("\n8. 【配置流程步骤】客户确认开始后引擎按固定流程执行：\n" +
                     "\n".join(step_lines) +
                     "\n提议时用一两句自然预告这个流程（画布描述是你的素材，不必逐字罗列），"
                     "让客户知道接下来会发生什么。\n")
    return (
        "\n\n【需求收集模式】当前线索登记表：\n" + json.dumps(slots, ensure_ascii=False) +
        "\n你是客户的服务器配置顾问。规则：\n"
        "1. 客户表达服务器配置需求时，把**客户明确表达的**信息当轮逐项用 update_requirement_slots 登记"
        "（fill 键名：server_type_name/series/form/server_model/purchase_qty/cpu/memory/drives/gpu/nic/raid/psu/kp_mode）。"
        "**一句话里点名的每个配件（型号/数量/容量）都不能漏登**——漏登会被引擎当成没说过，推荐会背离客户原话。"
        "首次提交前自检：客户原话点名的每个配件是否都已登成结构化信号；有漏登先补登再提交，"
        "绝不留到引擎逐组反问（引擎只对『确实没登记』的组发选项卡）。"
        "配件信号必须用结构化值，禁止一句话字符串："
        "gpu=[{\"model\":\"智铠100\",\"qty\":4}]、cpu={\"model\":\"EPYC 9745\",\"qty\":2}、"
        "memory={\"total_gb\":256}（只知总量）或 {\"per_stick_gb\":64,\"qty\":8}（知单条）、"
        "drives=[{\"capacity\":\"2048G\",\"qty\":2,\"type\":\"SSD\"}]、raid=[{\"model\":\"9460-8i\",\"qty\":1}]。"
        "禁止臆测：客户只说「服务器」没提场景时，server_type_name 必须留空。"
        "server_type_name 只能是在售目录里的类型名；客户用口语描述场景（如某类计算任务）时，"
        "不要硬填类型，登记到 cpu 等对应配件槽，或向客户确认对应哪个目录类型。\n"
        "2. 提交时机（submit_registration）= 客户已同意开始配置流程：\n"
        "   a) 客户明确要求出方案/配置（如「帮我配一台」「出个方案」）——当轮登记完就提交，"
        "同意已经给出，不要再追问，缺口由引擎判定并以选项卡让客户点选；\n"
        "   b) 咨询式对话中信息渐齐——场景（服务器类型）明确后**主动提议**：一两句复述你已理解的需求"
        "（以登记表为准，只引用客户真实说过的内容）+ 自然预告配置流程步骤 + 问客户是否现在开始；"
        "客户回复确认（确认的同时又补充了新信息 → 先登记补充再提交）后提交。"
        "客户只补充不确认 → 照常登记，下一轮再提议。\n"
        "   c) 任务已在进行中（你上一轮转述过引擎缺口、或引擎正在等答案）——客户的回答（点选或文字）"
        "就是继续任务：先把新信息登记进表，再直接 submit_registration。**禁止此时重新提议流程**——"
        "同意在任务开始时已经给过，再次询问等于把客户当外人。\n"
        "   禁止客户未同意就提交；禁止「没问题吧/如果没问题我就开始了」式无信息空轮——"
        "提议轮本身必须带需求复述和流程预告。提交后等引擎结果，按结果汇报，不要自己编造配置。\n"
        "2a. 工具纪律=说到做到：回复里说出「已登记/已提交/我查一下/稍等」就必须在**同一轮**真的调用对应工具；"
        "没有调用工具就不得声称做过，更不许只口头宣布「已提交，稍等结果」然后结束回合。"
        "每轮结束前自检：这轮说过要做的事，工具调用做了吗？\n"
        "3. 引擎返回缺口（gaps）时，用一两句自然中文向客户要**第一个缺口**的信息，选项值原样引用 gap 的 options，"
        "不要一次问多件事，不要编造选项。\n"
        "4. 客户问「有什么/推荐/该配什么」时，先用 catalog_search 查在售目录，再基于返回数据回答；"
        "问机型用 kind=models，问配件/选件用 kind=parts（可带 series 只看适配当前平台的件）；" + price_rule + "\n"
        "4b. 引擎以『库无某规格/容量偏差』白盒提示时（说明库里没有恰好型号），先把提示原样转给客户，"
        "再用 catalog_search(kind=parts) 找最接近的合法替代组合（如 8T→2×4T），说明替代方案、影响与价差，"
        "客户确认后才用 update_requirement_slots 登记；禁止悄悄换型号、禁止背过引擎替你编造。\n"
        "5. 客户闲聊或跑题：正常回应，一两句内自然拉回服务器配置话题。\n"
        "6. 客户改口/纠正时，用 update_requirement_slots 覆盖登记（fill 允许覆盖）。" + data_rule + plan_rule
    )


# ── 主入口：一条用户消息 → 角色 ReAct 循环（→ 引擎 → 缺口转述/产物汇报）──────

async def handle_skill_chat_turn(
    thread_id: str,
    user_text: str,
    colleague: Optional[dict],
    chat_system_prompt: str,
    history: list,
    user: Optional[dict] = None,
    opportunity_id: Optional[str] = None,
    option_slot: Optional[str] = None,
    event_sink: Optional[Callable[[dict], Any]] = None,
    governance_guard: Optional[Callable[[str, dict, Any], Any]] = None,
    emit_input_card: Optional[Callable[[str, dict], Any]] = None,
    card_selections: Optional[list] = None,
) -> Optional[dict]:
    """角色对话脑主循环。返回引擎终态 dict（done 时含 artifact 供上层做落库收尾），无引擎时返回 None。

    emit_input_card(question_text, gap)：上层把它渲染成结构化选项卡（UI 数据=缺口，文案=角色）。
    """
    from app.services.skill_phases import KP_MODE_OPTIONS
    from app.services.skill_plan_runtime import engine_result_of, run_skill_plan_core

    role_key = (colleague or {}).get("role_key") or "assistant"
    mem = _load_mem(thread_id, role_key)
    ext = dict(mem.get("ext") or {})
    # 数据边界（步骤1）：query_data 的物理权限源；缺省时 normalize 出 deny_all
    from app.services.data_boundary import colleague_price_ok, normalize_boundary
    price_ok = colleague_price_ok(colleague or {})
    boundary = normalize_boundary(colleague or {})
    # query_data 试点门控：角色 tool_ids 显式勾选才挂（试点只开方案助手）
    has_query_data = isinstance((colleague or {}).get("tool_ids"), list) \
        and "query_data" in (colleague or {}).get("tool_ids")

    # Skill 画布配置提前加载：提议话术的流程步骤（数据驱动）与引擎执行共用同一份 node_configs
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services.skill_plan_runtime import skill_steps_view
    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="需求分析")
    finally:
        repo.close()
    if not flow:
        return {"kind": "error", "reply": "需求分析流程未配置，请联系管理员。"}
    flow_configs = dict(flow.get("node_configs") or {})
    flow_title = str(flow.get("name") or "") or "配置任务"

    # 结构化选项点击（含逐项卡提交/表单批量）：按 (slot,value) 匹配发卡时持久化的原始选项，
    # 带 signal 载荷的原样直传落槽（消灭「构造字符串→再解析」）；qty 为 stepper 数量参数，
    # 服务端按机箱能力 clamp 后克隆 signal；留底未命中且为配件槽 → 自由型号走目录模糊匹配。
    # 委托/改口等语义仍由角色在对话里处理（不匹配留底卡时走旧路径）。
    raw_selections: list[tuple[str, str, int]] = []
    if isinstance(card_selections, list) and card_selections:
        for s in card_selections:
            if isinstance(s, dict) and str(s.get("slot") or "").strip() \
                    and str(s.get("value") or "").strip():
                try:
                    q = int(s.get("qty") or 0)
                except (TypeError, ValueError):
                    q = 0
                raw_selections.append((str(s["slot"]).strip(), str(s["value"]).strip(), max(0, q)))
    elif str(option_slot or "").strip() not in ("", "general") and user_text.strip():
        raw_selections.append((str(option_slot).strip(), user_text.strip(), 0))

    click_note = ""
    click_labels: list[str] = []
    had_pending_card = bool((mem.get("last_card") or {}).get("options"))
    for selected, value, want_qty in raw_selections:
        try:
            signal = _match_card_signal(mem, selected, value)
            if signal is None and selected in _PART_PICK_SLOTS:
                signal = _manual_model_signal(mem, selected, value)
            if signal:
                if want_qty:
                    signal = _signal_with_qty(
                        signal, want_qty, (mem.get("last_card") or {}).get("pick_meta") or {})
                from app.services.slot_extractor import apply_structured_slots
                apply_structured_slots(ext, signal, value)
                click_labels.append(canonical_key(selected) + (f"×{want_qty}" if want_qty else ""))
            else:
                from app.services.capabilities import _apply_extracted_slots
                _apply_extracted_slots(ext, {selected: value}, allow_overwrite=True)
                click_labels.append(f"{canonical_key(selected)}={value}")
        except Exception:
            logger.exception("选项落槽失败 slot=%s", selected)
    if click_labels:
        click_note = "（用户点击了选项，已登记 " + "；".join(click_labels) + "）"
    # 点选快速路径：点击命中且有在途选项卡 → 客户意图无歧义（继续任务，规则2c），
    # 跳过「角色决定是否提交」的 ReAct 轮，系统直接续跑引擎——根治「已登记/正在处理」
    # 口头空转不推进（模型说了提交但没调工具）。
    click_fast_path = bool(click_labels) and had_pending_card

    save = lambda: _save_mem(thread_id, role_key, {**mem, "ext": ext})  # noqa: E731
    state = {"submit": False}
    _TOOL_CTX.set({"ext": ext, "user_text": user_text, "save": save, "price_ok": price_ok,
                   "boundary": boundary, "role_key": role_key, "event_sink": event_sink,
                   "on_submit": lambda: state.__setitem__("submit", True)})

    system_prompt = "\n\n".join([
        chat_system_prompt,
        requirement_prompt(_slots_view(ext), price_ok=price_ok, query_data_ok=has_query_data,
                           flow_steps=skill_steps_view(flow_configs, user_facing_only=True)),
    ]).strip()
    loop_tools = ["update_requirement_slots", "submit_registration", "catalog_search"]
    if has_query_data:
        loop_tools.append("query_data")

    if click_fast_path:
        # 系统驱动续跑：无角色对话轮（点选不需要口头决策，转述通道补确认句）
        result = None
        reply = ""
        state["submit"] = True
        logger.info("click fast path: 跳过角色决策直接续跑引擎 thread=%s hits=%d",
                    thread_id, len(click_labels))
    else:
        result = await run_stream_chat_loop(
            (user_text + ("\n" + click_note if click_note else "")).strip(),
            {"enabled_tools": loop_tools},
            system_prompt=system_prompt,
            allowed_tool_ids=loop_tools,
            history=history,
            model=(colleague or {}).get("model_override") or None,
            event_sink=event_sink,
            tool_guard=governance_guard,
            max_iterations=6,
            # 断连止损：中转半死连接最多烧 60s；low 档给对话路由提速
            llm_timeout=60.0,
            llm_reasoning_effort="low",
            llm_temperature=0.2,
        )
        reply = str((result or {}).get("answer") or "").strip() if isinstance(result, dict) else str(result or "").strip()
        save()
        logger.info(
            "skill chat react 结束 thread=%s iterations=%s submit=%s reply_len=%s",
            thread_id, (result or {}).get("iterations") if isinstance(result, dict) else "?",
            state["submit"], len(reply),
        )

    if not state["submit"]:
        logger.info("skill chat 返回 kind=chat thread=%s", thread_id)
        return {"kind": "chat", "reply": reply}

    # ── 引擎执行（登记表已提交；任务启动的可视化交给 pipeline_start/任务胶囊）──
    from app.services.slot_contract import canonical_get

    # 场景证据用累计文本判断：登记表草稿 + 本句
    from app.services.portal_flow_adapter import build_requirement_text
    full_text = build_requirement_text(opportunity_id, user_text) if opportunity_id else user_text
    # 冻结守卫（_freeze_requirement）按「机型名是否出现在需求文本」剥臆造机型；
    # 多轮对话里机型是早前轮次点选/口述的，本句（如"256G内存"）不会含机型名，
    # 只用本句会把已确认机型剥掉 → 机型问题无限重弹。近期用户原话并入比对基准。
    prior_user = [str((m or {}).get("content") or "").strip() for m in (history or [])
                  if (m or {}).get("role") == "user" and str((m or {}).get("content") or "").strip()]
    if prior_user:
        full_text = "\n".join(prior_user + [full_text])
    engine_ctx = {
        "requirement_text": full_text,
        "ext": ext,
        "slots_provided": True,
        "history": history,
        "business_mode": "opportunity_flow" if opportunity_id else "conversation",
        "opportunity_id": opportunity_id or thread_id,
        "operator_name": (user or {}).get("name") or (user or {}).get("user_id") or "",
        "output_kind": "bom_scheme_draft",
        "force_complete": False,
        "llm_model": (colleague or {}).get("model_override") or None,
        "price_access": price_ok,
    }
    result_ctx = await run_skill_plan_core(engine_ctx, flow_configs, event_sink, title=flow_title)
    # 引擎会就地完善登记表（信号补抽/归一会替换 ext 对象），回存保证下一轮角色看到最新状态
    _save_mem(thread_id, role_key, {**mem, "ext": result_ctx.get("ext") or ext})
    if result_ctx.get("fatal_error"):
        return {"kind": "error", "reply": f"需求分析执行失败：{result_ctx.get('fatal_error')}"}

    er = engine_result_of(result_ctx)
    engine_ctx["engine_result"] = er
    if er.get("status") == "done":
        logger.info("skill chat 返回 kind=done thread=%s", thread_id)
        return {"kind": "done", "reply": reply, "engine_ctx": result_ctx}

    # ── 缺口：角色用自己的话问第一个缺口（结构=数据，文案=模型）──
    gaps = list(er.get("gaps") or [])
    gap = gaps[0] if gaps else None
    if gap is None:
        logger.info("skill chat 返回 kind=error(未知引擎状态) thread=%s", thread_id)
        return {"kind": "error", "reply": "引擎返回了未知状态"}
    # 自选器上下文弹出缺口（机器数据不进转述 JSON），随 last_card 留底给 card-pick 端点
    pick_meta = gap.pop("pick_meta", None) if isinstance(gap, dict) else None

    # 已锁定机型随缺口下行（纯数据）：转述模型可自然带到问句里，用户全程看得见选型进展
    locked_model = str(((result_ctx.get("model_selection") or {}).get("name")) or "")
    if locked_model:
        gap.setdefault("context", {})["locked_model"] = locked_model
        lock_reason = str(result_ctx.get("lock_reason") or "")
        if lock_reason:
            gap["context"]["lock_reason"] = lock_reason

    # 缺口转述=同一颗大脑的续话：带人设+近期对话+本轮角色已说的话，让问句贴上下文。
    # 只喂缺口 JSON 的无上下文转述=固定数据进固定话术出，事实上的硬编码模板。
    hist_tail = [dict(m) for m in (history or [])[-6:]
                 if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                 and str(m.get("content") or "").strip()]
    ack_rule = ""
    if click_labels:
        ack_rule = ("客户刚在选项卡上点选确认了：" + "、".join(click_labels) +
                    "。请先用一句话自然确认收到（像「收到，GPU 就定 10× 曙云C550」），"
                    "然后再转入下面的缺口确认，两段话合成一次回复。")
    ask_messages = [
        {"role": "system", "content": chat_system_prompt},
        *hist_tail,
        {"role": "assistant", "content": reply or ""},
        {"role": "user", "content": ("（系统消息）配置引擎返回缺口数据，请以你的顾问口吻用一两句自然中文向客户确认第一个缺口，"
                    + ack_rule +
                    "结合对话上下文自然措辞（例如客户做的是什么场景、已锁定什么机型），不要模板腔。"
                    "只引用客户真实说过的场景/用途，禁止从历史闲聊里抓别的场景安到客户头上。"
                    "转述选项一律用 label 文案（用户要点的就是它）；value 是机器代号"
                    "（如 scenario_complete），禁止出现在话术里。不要一次问多件事。"
                    "只能输出 JSON：{\"reply\": \"你要发给客户的那句话\"}。缺口数据：\n"
                    + json.dumps(gap, ensure_ascii=False))},
    ]
    try:
        from app.services import llm_client
        ask = await llm_client.chat_json(
            ask_messages, model=(colleague or {}).get("model_override") or None,
            temperature=0.3, timeout=30.0, max_attempts=1, reasoning_effort="low")
        question = ""
        if isinstance(ask, dict):
            question = str(ask.get("reply") or ask.get("question") or ask.get("content") or "").strip()
        if not question and isinstance(ask, str):
            question = ask.strip()
    except Exception as exc:
        logger.warning("缺口转述生成失败，退回数据兜底: %s", exc)
        question = ""
    if not question:
        # 兜底是最小事实句（非话术表）：告诉客户还缺什么，选项原样列出（label 优先）。
        def _opt_text(o):
            return str(o.get("label")) if isinstance(o, dict) else str(o)
        options_text = " / ".join(_opt_text(o) for o in (gap.get("options") or [])[:6])
        question = f"还需要确认：{slot_label(gap.get('slot') or '')}" + (f"（{options_text}）" if options_text else "")
    if gap.get("slot") == "kp_mode" and not any(o in question for o in KP_MODE_OPTIONS):
        question = question + "\n选项：" + " / ".join(KP_MODE_OPTIONS)
        gap["options"] = list(KP_MODE_OPTIONS)

    # 所有缺口都发结构化选项卡：问题文本随卡落库，选项为空 = 开放回答（面板降级为纯问题）
    card_emitted = False
    if emit_input_card is not None:
        slot_key = str(gap.get("slot") or "general")
        group = slot_label(slot_key)
        cards = []
        card_opts = []
        for o in (gap.get("options") or []):
            if isinstance(o, dict):
                opt = {"label": str(o.get("label") or o.get("value") or ""),
                       "value": str(o.get("value") or o.get("label") or ""),
                       "desc": str(o.get("desc") or ""),
                       "slot": str(o.get("slot") or slot_key),
                       # 逃生项显式空组别（前端把非空组当卡头，逃生项不占组位）
                       "group": str(o.get("group") if o.get("group") is not None else group)}
                # 数量元数据透传（前端 stepper 边界+实时总量显示，纯展示参数非 signal）
                for k in ("qty", "qty_max", "unit_gb"):
                    v = o.get(k)
                    if isinstance(v, int) and v > 0:
                        opt[k] = v
                cards.append(opt)
                entry = {"slot": str(o.get("slot") or slot_key),
                         "value": str(o.get("value") or o.get("label") or "")}
                sig = o.get("signal")
                if isinstance(sig, dict) and sig:
                    entry["signal"] = sig
                card_opts.append(entry)
            else:
                cards.append({"label": str(o), "value": str(o), "desc": "",
                              "slot": slot_key, "group": group})
                card_opts.append({"slot": slot_key, "value": str(o)})
        try:
            await emit_input_card(question, {"question": question, "options": cards,
                                             "slot_options": {slot_key: cards},
                                             "why": "", "missing_fields": [slot_key]})
            card_emitted = True
            # 结构化载荷随卡持久化到会话记忆：点击轮按 (slot,value) 匹配原样直传，
            # 服务端留底不信任客户端回传值。全量留底（含无 signal 的机型/逃生项）：
            # had_pending_card 是点击快速路径的判定条件，只留 signal 会让机型卡点击
            # 掉回 LLM 决策轮（点完又问「可以吗」）。ext 必须取引擎产物（补抽会替换
            # ext 对象），用本地旧对象会把引擎补好的信号从记忆里抹掉
            if card_opts:
                try:
                    _save_mem(thread_id, role_key, {**mem, "ext": result_ctx.get("ext") or ext,
                                                    "last_card": {"options": card_opts,
                                                                  **({"pick_meta": pick_meta} if pick_meta else {})}})
                except Exception:
                    logger.exception("选项卡结构化载荷持久化失败")
        except Exception:
            logger.exception("选项卡广播失败")
    logger.info("skill chat 返回 kind=gaps slot=%s card=%s thread=%s",
                gap.get("slot"), card_emitted, thread_id)
    return {"kind": "gaps", "reply": question, "gap": gap, "engine_ctx": result_ctx,
            "card_emitted": card_emitted}
