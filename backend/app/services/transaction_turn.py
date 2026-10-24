# -*- coding: utf-8 -*-
"""transaction_turn —— 事务管道的聊天轮外壳 + 分发器（内核之上的进程加载器）。

与 plain（colleague_turn_runners._run_tool_turn）/ skill（_run_skill_chat）并列的
第三条回合路径：内核（transaction_engine）管步骤指针与案台，大脑带全现场工作。
本模块只做聊天管线（流式广播/落库/上下文注入），业务顺序与状态全部在内核与应用声明。

确认闸调和器（本文件迭代尾/_drive_steps 收尾处的 _emit_ready_queries / _replay_deferred /
闸步强制重调）执行一条定理的四条不变量——**卡的存在性不依赖大脑纪律**：
  R1 投影幂等：一份待确认记录至多一张卡（carded 标记，persist_confirm_card 内）；
  R2 投影完备：有记录必有卡，且落在本轮答案之后（defer_user_emission 闸口=R4 时序）；
  R3 记录完备：指针停闸步无记录 → (a) 推迟账本原参数重放 (b) 强制重调一轮，
     仍无则发机械话术（真报错，不撒谎）；
  R0 记录产生只在工具闸内（_confirm_gate）：写语义归工具，生命周期归调和器。
新出现的"卡不对"类 bug 先映射到条款，修条款而不是加第五个散点守卫。

布局守卫：独立成模块不挤占 colleague_turn_runners 的 700 行预算（2026-10-18）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from app.services.agent_react import run_stream_chat_loop
from app.services.assistant_hub import assistant_hub
from app.services.colleague_prompt import (
    _effective_tool_ids,
    _handoff_hint,
    _short_term_history,
    _style_hint,
    build_chat_config,
)
from app.services.colleague_turn_io import _persist_and_broadcast, _persist_artifact, _trace
from app.services.data_boundary import effective_price_ok
from app.services.office_events import publish_office_event
from app.services.skill_contracts import SKILL_SESSION_DONE
from app.services.skill_tool_context import TOOL_CTX
from app.services import transaction_engine as te

logger = logging.getLogger(__name__)


def _fact_bits(fact: dict) -> str:
    """单条工具事实 → 节点输出摘要一行。工具结果自带 note（人话事实，C1）直接用，
    再补一个业务标识；拼不出内容回退「<tool> 完成」。供画布节点卡实时显示输出物。"""
    result = fact.get("result")
    if not isinstance(result, dict) or not result.get("ok"):
        return ""
    tool = str(fact.get("tool") or "")
    note = str(result.get("note") or "").strip()
    ident = ""
    for key in ("sheet_name", "quotation_id", "bom_scheme_id", "customer_name", "sheet_id"):
        if result.get(key) not in (None, "", [], {}):
            ident = f"{key}={result[key]}"
            break
    bits = "；".join(x for x in (note, ident) if x)
    return f"{tool}：{bits}" if bits else f"{tool} 完成"


_NODE_NOTE_KEY = "node_notes"  # 状态槽里逐节点摘要的保留键（step_key → 摘要文本）


def _node_notes(view: dict) -> dict:
    """状态槽里的逐节点摘要（跑过的节点各自留了一句事实；没留过的=未单独执行）。"""
    notes = ((view or {}).get("flags") or {}).get(_NODE_NOTE_KEY)
    return notes if isinstance(notes, dict) else {}


def save_node_note(app, thread_id: str, role_key: str, step_key: str, summary: str) -> None:
    """节点完成时把本步自己的事实摘要存进状态槽：跨回合保留。回合开头各节点
    各念各的（不再整桌复述一遍——此前所有已完成节点一个模样就是这么来的）。"""
    if not step_key or not summary:
        return
    st = te.load_state(app, thread_id, role_key)
    notes = st.get(_NODE_NOTE_KEY) if isinstance(st.get(_NODE_NOTE_KEY), dict) else {}
    notes[step_key] = str(summary)
    st[_NODE_NOTE_KEY] = notes
    te.save_state(app, thread_id, role_key, st)


_SPEC_CARD_CACHE: dict = {}


def _tool_spec_card(tool: str):
    """工具规格自带的产物卡声明（卡=工具的属性：一次声明，所有挂此工具的工作流通用）。
    节点配置的 artifact_card 可覆盖；两者都没有就不发卡。"""
    if tool in _SPEC_CARD_CACHE:
        return _SPEC_CARD_CACHE[tool]
    card = None
    try:
        from app.services.agent_tool_specs import _TOOL_SPECS
        card = (_TOOL_SPECS.get(str(tool or "")) or {}).get("artifact_card")
    except Exception:
        logger.exception("tool spec card lookup failed tool=%s", tool)
    card = card if isinstance(card, (dict, list)) else None
    _SPEC_CARD_CACHE[str(tool or "")] = card
    return card


def _card_decls_for(step: dict, tool: str) -> list:
    """某步某工具的卡声明：节点覆盖优先（on_tool 匹配项），工具规格兜底。"""
    for d in te._norm_card_decls(step.get("artifact_card")):
        if d.get("on_tool") == tool:
            return [d]
    spec = _tool_spec_card(tool)
    return te._norm_card_decls(spec)


async def _run_transaction_turn(app, thread_id, user_text, context_summary, history,
                                colleague, memory_block, final_office_event=None,
                                trace_sink=None, user=None, opportunity_id=None,
                                option_slot=None, card_selections=None,
                                title: str = "") -> None:
    """事务工作流应用的一轮：内核现算案台 → 指针停哪步大脑带哪步工具白名单干活 →
    产物落了指针前移续跑（每回合≤4步），没落（反问/等确认/答疑）停在本步等用户。
    判断全在大脑，顺序在指针，状态在库；案台是事实块（C1），行为指令只住左栏规则。"""
    role_key = (colleague or {}).get("role_key") or "assistant"
    started = time.perf_counter()
    chat_cfg = build_chat_config(colleague)
    persona = "\n\n".join([chat_cfg["chat_system_prompt"], _style_hint(chat_cfg)])
    handoff = _handoff_hint(colleague)
    if handoff:
        persona += "\n\n" + handoff
    if memory_block:
        persona += "\n\n" + memory_block
    history = _short_term_history(colleague, history)

    flow = te.load_flow_rules(app.flow_key)
    if not flow["steps"]:
        # 流配置缺失：降级普通工具聊天（fail-open 到能力，不给用户死白屏）
        await publish_office_event(role_key, "thinking", "工作流配置缺失，切换普通对话",
                                   thread_id=thread_id)
        from app.services.colleague_turn_runners import _run_tool_turn  # 懒导入防环
        await _run_tool_turn(
            thread_id, user_text, context_summary, history, colleague, memory_block,
            _effective_tool_ids(colleague),
            final_office_event=final_office_event, trace_sink=trace_sink,
            user=user, opportunity_id=opportunity_id, option_slot=option_slot,
        )
        return

    # 会话落 ACTIVE：续跑回合即使客户端不带 workflow_key 也分发回本流
    # （此前只有 complete 时落 DONE——中途续跑一律回退 requirement_analysis，2026-10-22 实锤）
    try:
        from app.services.skill_memory import load_skill_session, save_skill_session, SKILL_SESSION_ACTIVE
        _sess0 = load_skill_session(thread_id, role_key)
        if _sess0.get("phase") != SKILL_SESSION_ACTIVE or _sess0.get("skill_key") != app.flow_key:
            save_skill_session(thread_id, role_key, {
                "phase": SKILL_SESSION_ACTIVE, "skill_key": app.flow_key,
                "entry_point": str(_sess0.get("entry_point") or "")})
    except Exception:
        logger.exception("skill session 持久化失败 thread=%s", thread_id)

    tool_steps_box = {"cur": []}  # 当前步的工具轨迹（event_sink 定义在外层，经盒子间接读写）

    async def event_sink(payload: dict) -> None:
        sub = (payload or {}).get("sub") or {}
        kind = sub.get("kind") or ""
        tool = sub.get("tool")
        steps = tool_steps_box["cur"]
        if kind == "thinking" and sub.get("text"):
            await assistant_hub.broadcast(thread_id, {"type": "thinking", "text": sub["text"]})
        elif kind == "chunk_reset":
            await assistant_hub.broadcast(thread_id, {"type": "chunk_reset"})
        elif kind == "chunk" and isinstance(sub.get("delta"), str):
            await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": sub["delta"]})
        if kind == "tool":
            if sub.get("phase") == "start":
                steps.append({"tool": str(tool or ""), "text": str(sub.get("text") or "")})
            elif sub.get("phase") == "done" and steps:
                steps[-1].update(detail=str(sub.get("detail") or ""),
                                 elapsed_ms=int(sub.get("elapsed_ms") or 0))
            if sub.get("text"):
                await assistant_hub.broadcast(thread_id, {"type": "chat_status", "text": str(sub["text"])})
            if sub.get("phase") in ("start", "done"):
                await assistant_hub.broadcast(thread_id, {
                    "type": "tool_trace", "tool": str(tool or ""), "phase": str(sub["phase"]),
                    "detail": str(sub.get("detail") or ""), "elapsed_ms": int(sub.get("elapsed_ms") or 0)})
            await publish_office_event(role_key, "working", str(sub.get("text") or "正在调用工具"),
                                       tool=tool, thread_id=thread_id)

    profile = chat_cfg.get("response_profile") or {}
    profile_temperature = profile.get("temperature")
    profile_max_tokens = profile.get("max_tokens")
    rules = flow["rules"]
    final_event_pending = final_office_event

    await publish_office_event(role_key, "working", "接收新任务", message=str(user_text or "")[:160],
                               thread_id=thread_id)

    # 过程事件对齐需求分析引擎（pipeline_start 骨架 + 每步 node_trace + 暂停事实）：
    # 画布节点高亮/任务条计步/试运行实时输出物走同一套前端机制，零前端改动复用。
    # 状态语义只在引擎算一次（te.state_events），本壳只搬运——不得在此二次推导
    # （2026-10-22 实锤：这里曾拿 skip_note 文案真假当跳过判定，没配文案的
    # 跳过节点被广播成 done 冒充完成绿）。
    steps_all = flow["steps"]
    try:
        view0 = te.state_view(app, thread_id, role_key, user if isinstance(user, dict) else {})
        states0 = te.node_states(steps_all, view0)
    except Exception:
        logger.exception("案台初始进度计算失败 flow=%s", app.flow_key)
        view0 = {}
        states0 = {}
    await assistant_hub.broadcast(thread_id, {
        "type": "pipeline_start", "title": str(title or "").strip() or app.label,
        "steps": [{"key": s["key"], "label": s["label"]} for s in steps_all],
        "thread_id": thread_id})
    emitted_done = {k for k, st in states0.items() if st != "pending"}
    for ev in te.state_events(steps_all, view0, thread_id, notes=_node_notes(view0)):
        await assistant_hub.broadcast(thread_id, ev)

    async def _emit_state_changes(view_now: dict) -> None:
        """指针移动后补发状态变化节点：引擎同一份 node_states 现算，本壳只搬运增量。
        一步的工具可能让后面几个节点同时过关/被分流跳过，任务条不能漏标不简写。"""
        fresh = {k for k, st in te.node_states(steps_all, view_now).items()
                 if st != "pending"} - emitted_done
        if not fresh:
            return
        emitted_done.update(fresh)
        for ev in te.state_events(steps_all, view_now, thread_id, only_keys=fresh):
            await assistant_hub.broadcast(thread_id, ev)

    async def _execute_pending(tool0: str, step: dict, facts: list) -> Optional[str]:
        """确认卡直达执行：按 staged 记录直接调工具 handler（confirm=true）——
        用户意图不经过大脑转述参数的概率通路（2026-10-22 实锤：重放参数漂移 +
        记录被进程重启抹掉，把用户拖进无限出卡循环）。结果并入本迭代 facts，
        旗标回写/节点产物/确认卡/摘要全部走驱动循环与大脑调用同一份记账。
        返回注入 turn_msg 的指令文本；None=不适用（无记录/无 handler/工具不在
        本步白名单/执行异常）→ 回退大脑带 confirm 重调通路。"""
        import json as _json

        from app.services import agent_tool_specs
        from app.services.agent_write_confirm import staged_args as _sargs
        spec = (agent_tool_specs._TOOL_SPECS or {}).get(tool0) or {}
        handler = spec.get("handler")
        sargs = _sargs(thread_id, tool0)
        if not callable(handler) or sargs is None or tool0 not in (step.get("tools") or []):
            return None
        token = TOOL_CTX.set({
            "role_key": role_key, "price_ok": effective_price_ok(colleague, user=user),
            "thread_id": thread_id, "opportunity_id": opportunity_id,
            "user_id": str((user or {}).get("user_id") or "").strip() or None,
            "user": user if isinstance(user, dict) else None,
            "step_key": str(step.get("key") or ""),
            "step_fields": [dict(f) for f in (step.get("fields") or [])],
            "defer_user_emission": True, "workflow_offers": []})
        try:
            result = await handler({**sargs, "confirm": True})
        except Exception:
            logger.exception("确认卡直达执行失败 tool=%s thread=%s", tool0, thread_id)
            return None
        finally:
            TOOL_CTX.reset(token)
        if not isinstance(result, dict):
            return None
        facts.append({"tool": tool0, "result": result})
        payload = _json.dumps(result, ensure_ascii=False, default=str)
        if result.get("ok"):
            return (f"\n\n【已执行】用户在确认卡上点「确认执行」，系统已直接执行 {tool0}，"
                    f"结果：{payload}。请一句话向用户陈述结果（办了什么、单号多少），"
                    "不要重调该工具、不要询问其他问题。")
        return (f"\n\n【执行未成功】用户点了「确认执行」，系统已按待确认记录重试执行 {tool0}，"
                f"但工具返回失败：{payload}。如实把失败原因告诉用户并提出修正建议；"
                "不要重调该工具、不要编造结果。")

    gate_nudged: set = set()
    gate_fallback = {"hit": False}  # R3(b)：强制重调后闸步仍无记录 → 回合末发机械话术
    pending_directives: list = []
    # 问答协议：取走本回合的结构化回答（取出即清；答案自带问题上下文）
    from app.services import human_query as _hq
    pending_answer = _hq.take_answer(thread_id)

    async def _emit_ready_queries(view_now: dict) -> int:
        """R2 投影完备（调和器）：有待确认记录而未发起授权问询 → 立 consent 型
        HumanQuery（问答协议）。存在性由 query_opened 标记幂等保证（R1：一份记录
        至多一次问询），发射时机由调用方控制——必须在本轮答案之后（R4 闸口）。
        吸收原「facts 循环落卡」与「回合末兜底网」两个散点。"""
        from app.services import human_query as hq
        from app.services.agent_write_confirm import pending_previews as _pp
        from app.services.agent_write_confirm import query_opened as _qo, mark_query_opened as _mqo
        n = 0
        for _t, _pv in (_pp(thread_id) or {}).items():
            if isinstance(_pv, dict) and _pv and not _qo(thread_id, _t):
                try:
                    await hq.open_query_and_announce(
                        thread_id, kind="consent",
                        title="待确认操作",
                        detail="\n".join(f"{k}：{v}" for k, v in _pv.items()
                                         if not isinstance(v, (list, dict))),
                        options=[{"label": "确认执行", "description": "按上述内容执行"},
                                 {"label": "取消", "description": "不执行，可继续调整"}],
                        action={"tool": _t}, role_key=(colleague or {}).get("role_key"))
                except hq.ContractError:
                    break  # 已有开放问题：一份问询在场时绝不挤第二个（协议不变量）
                _mqo(thread_id, _t)
                n += 1
        return n

    async def _replay_deferred(view_new: dict) -> None:
        """R3a 记录完备（跨步交接）：被步进纪律推迟的闸调用（deferred 账本），
        指针推进到写动作所属步后**原参数重放**——此刻 step_key 已是所属步，
        工具不再自降级，走自己的确认闸（stage+needs_confirmation），卡由 R2 在
        下一轮答案之后落库（先解释后弹卡）。重放一次即清账：失败也清，错误
        作为事实给大脑转述，不死循环。2026-10-22 实锤：识别步预览后指针静默
        推进，大脑对推进零感知、拿着旧结果承诺一张永远没人发的卡。"""
        import json as _json

        from app.services import agent_tool_specs
        from app.services.agent_write_confirm import deferred_calls as _d_calls, pop_deferred as _pop_d
        step_new = view_new.get("step") or {}
        tools_now = set(step_new.get("tools") or [])
        pend_now = set((view_new.get("pending") or {}).keys())
        for _dtool in sorted(_d_calls(thread_id) or {}):
            if _dtool not in tools_now or _dtool in pend_now:
                continue
            _dargs = _d_calls(thread_id).get(_dtool) or {}
            handler = ((agent_tool_specs._TOOL_SPECS or {}).get(_dtool) or {}).get("handler")
            _pop_d(thread_id, _dtool)  # 一次机会：成败都清账
            if not callable(handler):
                continue
            token = TOOL_CTX.set({
                "role_key": role_key, "price_ok": effective_price_ok(colleague, user=user),
                "thread_id": thread_id, "opportunity_id": opportunity_id,
                "user_id": str((user or {}).get("user_id") or "").strip() or None,
                "user": user if isinstance(user, dict) else None,
                "step_key": str(step_new.get("key") or ""),
                "step_fields": [dict(f) for f in (step_new.get("fields") or [])],
                "defer_user_emission": True, "workflow_offers": []})
            try:
                result = await handler(dict(_dargs))
            except Exception:
                logger.exception("推迟闸调用重放失败 tool=%s thread=%s", _dtool, thread_id)
                result = None
            finally:
                TOOL_CTX.reset(token)
            payload = _json.dumps(result if isinstance(result, dict) else {"error": "重放异常"},
                                  ensure_ascii=False, default=str)
            pending_directives.append(
                f"\n\n【闸调用已重放】{_dtool} 上一步因步进纪律被推迟（识别步只做解析预览），"
                f"系统已在当前步按原参数重放，返回：{payload}。确认卡会出现在下方"
                "（先解释后弹卡）。请基于此结果向用户陈述，不要重调该工具。")

    async def _drive_steps():
        nonlocal final_event_pending, pending_answer
        # 每回合最多推 4 步：正常一回合推到底（闸门暂停不算），封顶防失控循环
        for _iteration in range(4):
            view = te.state_view(app, thread_id, role_key, user if isinstance(user, dict) else {})
            step = view.get("step")
            if step is None:
                break
            tool_steps_box["cur"] = []
            facts: list = []
            step_t0 = time.perf_counter()
            await assistant_hub.broadcast(thread_id, {
                "type": "node_trace", "step": step["key"], "label": step["label"],
                "status": "running", "summary": "", "thread_id": thread_id})

            async def fact_guard(name: str, args: dict, result: Any) -> Any:
                # 工具真实返回的零侵入采集点：内核据此经应用旗标表回写（判断仍在大脑/工具内）。
                # args 随事实入账：R3a 推迟重放要按原参数重调（大脑做过的决定，壳只解封）。
                facts.append({"tool": str(name or ""), "result": result,
                              "args": args if isinstance(args, dict) else {}})
                return result

            step_tools = list(dict.fromkeys(list(step["tools"]) + ["query_data", "colleague_memory"]))
            system_prompt = persona
            if rules:
                system_prompt += "\n\n任务规则（配置者编写，全程遵守）：\n" + rules
            system_prompt += f"\n\n当前步骤：{step['label']}（本步登记的工具：{'、'.join(step_tools)}）"
            step_contract = te.format_step_contract(step)
            if step_contract:
                system_prompt += "\n" + step_contract
            turn_msg = f"【客户消息】\n{str(user_text or '').strip()}\n\n{te.digest(app, view)}"
            while pending_directives:
                turn_msg += pending_directives.pop(0)

            # 问答协议：结构化回答按 query_id 路由（choice/form）——答案自带问题上下文，
            # 大脑不重提问、不解析自然语言。
            if pending_answer and pending_answer["answer"].get("kind") in ("choice", "form"):
                import json as _json
                _q = (pending_answer.get("query") or {}).get("question") or {}
                _a = pending_answer["answer"]
                _ans_payload = {"selections": _a.get("selections"),
                                "values": _a.get("values"), "note": _a.get("note")}
                turn_msg += (f"\n\n【问题已回答】问：{_q.get('title') or ''}；答："
                             f"{_json.dumps(_ans_payload, ensure_ascii=False)}。"
                             "据此继续推进，不要重复提问、不要再次调用 ask_user。")
                pending_answer = None  # 一次性：答案消费掉，不污染后续迭代

            # 授权问询直达执行（consent）：用户点「确认执行」/手打确认词（兜底，匹配范围
            # 被开放问询收窄）→ 按 staged 记录直接调工具——用户意图不经过"大脑转述参数"
            # 这条概率通路。文本匹配只在"该线程有开放 consent 问"时才允许，全局串比对已废。
            _pend = view.get("pending") or {}
            _ans = (pending_answer or {}).get("answer") or {}
            _ans_sel = _ans.get("selections") or []
            _ans_text = str(user_text or "").strip()
            _confirm_clicked = _ans.get("kind") == "consent" and "确认执行" in _ans_sel
            _cancel_clicked = _ans.get("kind") == "consent" and "取消" in _ans_sel
            if _pend and (_confirm_clicked or _cancel_clicked
                          or _ans_text in ("确认执行", "确认", "取消")):
                _tool0 = sorted(_pend)[0]
                if _cancel_clicked or _ans_text == "取消":
                    from app.services.agent_write_confirm import discard as _discard
                    _discard(thread_id, _tool0)
                    pending_answer = None
                    turn_msg += (f"\n\n【取消确认】用户在授权问询上点了「取消」，{_tool0} 的待确认记录"
                                 "已清除。不要执行、不要重出预览，一句话确认取消即可。")
                else:
                    pending_answer = None
                    _directive = await _execute_pending(_tool0, step, facts)
                    if _directive is None:
                        from app.services.agent_write_confirm import staged_args as _staged_args
                        import json as _json
                        _sargs = _staged_args(thread_id, _tool0) or {}
                        turn_msg += (f"\n\n【确认执行】用户已在授权问询上点「确认执行」。待执行工具：{_tool0}，"
                                     f"执行参数：{_json.dumps(_sargs, ensure_ascii=False)}。"
                                     "立即带上述参数加 confirm=true 重调该工具执行，执行后一句话陈述结果；"
                                     "参数原样带上，不要自行修正任何值（0/空都是合法哨兵值）；"
                                     "不要询问其他问题。")
                    else:
                        turn_msg += _directive

            _ctx_token = TOOL_CTX.set({
                "role_key": role_key, "price_ok": effective_price_ok(colleague, user=user),
                "thread_id": thread_id, "opportunity_id": opportunity_id,
                "user_id": str((user or {}).get("user_id") or "").strip() or None,
                "user": user if isinstance(user, dict) else None,
                "step_key": str(step.get("key") or ""),
                "step_fields": [dict(f) for f in (step.get("fields") or [])],
                "defer_user_emission": True,  # 问询/授权由轮壳在答案落库后统一发射（先解释后问）
                "workflow_offers": []})
            try:
                result = await run_stream_chat_loop(
                    turn_msg, {"enabled_tools": step_tools},
                    system_prompt=system_prompt, allowed_tool_ids=step_tools,
                    model=(colleague or {}).get("model_override") or None,
                    event_sink=event_sink, history=history, tool_guard=fact_guard,
                    llm_temperature=profile_temperature if isinstance(profile_temperature, (int, float)) else None,
                    llm_max_tokens=profile_max_tokens if isinstance(profile_max_tokens, int) and profile_max_tokens > 0 else None,
                    context_block=context_summary or "", llm_overall_timeout=120.0,
                    emit_chunk_reset=True,
                )
            finally:
                TOOL_CTX.reset(_ctx_token)
            te.apply_facts(app, thread_id, role_key, facts)
            # R3a 记账：写工具因步进纪律自降级（deferred_by_step 声明）→ 入推迟账本
            from app.services.agent_write_confirm import defer_call as _defer_call
            for fact in facts:
                fr = fact.get("result")
                if isinstance(fr, dict) and fr.get("deferred_by_step"):
                    _defer_call(thread_id, str(fact.get("tool") or ""),
                                fact.get("args") if isinstance(fact.get("args"), dict) else {})
            new_view = te.state_view(app, thread_id, role_key, user if isinstance(user, dict) else {})
            # 产物卡：卡声明=节点覆盖 → 工具规格兜底（卡是工具的属性）；
            # 仅解析预览（analysis_only）静默不发卡——预览由大脑文本转述，落草稿才发卡。
            # 此处只装配不落库：先陈述后弹卡（卡在工具返回瞬间落库会跑到解释文本前面，
            # 2026-10-22 用户实测），落库在本步答案广播之后统一做
            built_cards = []
            for fact in facts:
                fr = fact.get("result")
                if not isinstance(fr, dict) or not fr.get("ok") or fr.get("analysis_only"):
                    continue
                for card_decl in _card_decls_for(step, str(fact.get("tool") or "")):
                    try:
                        card = te.build_card(card_decl, fr, new_view)
                        if card:
                            built_cards.append(card)
                    except Exception:
                        logger.exception("artifact card emit failed flow=%s", app.flow_key)
            # 步骤过程事实 → 节点卡实时输出（指针前移=本步完成；停在本步=保持运行中）；
            # 本步发过产物卡 → 节点「输出物」直接挂卡（画布点开=ArtifactCard 查看器）
            completed = bool(new_view.get("complete")) or \
                str(new_view.get("step_key") or "") != str(view.get("step_key") or "")
            step_summary = "；".join(x for x in (_fact_bits(f) for f in facts) if x)
            card0 = built_cards[0] if built_cards else None
            await assistant_hub.broadcast(thread_id, {
                "type": "node_trace", "step": step["key"], "label": step["label"],
                "status": "done" if completed else "running",
                "duration_ms": int((time.perf_counter() - step_t0) * 1000),
                "output": step_summary or None, "summary": step_summary,
                "input": None,
                "artifact": ({"kind": "artifact_card", "title": card0.get("title") or "",
                              "data": {"card": card0}} if card0 else None),
                "thread_id": thread_id})
            if completed:
                emitted_done.add(step["key"])
                if step_summary:
                    try:
                        save_node_note(app, thread_id, role_key, step["key"], step_summary)
                    except Exception:
                        logger.exception("node note save failed step=%s", step["key"])
                await _emit_state_changes(new_view)
            answer = str((result or {}).get("answer") or "").strip()
            if answer:
                await _persist_and_broadcast(thread_id, colleague, answer,
                                             final_office_event=final_event_pending,
                                             tool_steps=tool_steps_box["cur"])
                final_event_pending = None
            # 产物卡在答案之后落库（先陈述后弹卡）；确认卡随后（R2 调和发射）
            for card in built_cards:
                await _persist_artifact(thread_id, colleague, card)
            # R2 投影完备：有待确认记录而无卡 → 落卡（幂等，吸收原 facts 落卡循环）
            # R2 投影完备：有待确认记录而未发起授权问询 → 发 consent 问（幂等）
            await _emit_ready_queries(new_view)
            for fact in facts:
                fr = fact.get("result")
                if isinstance(fr, dict) and fr.get("user_query"):
                    # 问答协议：ask_user 的问题在答案落库后统一发射（先解释后问）
                    from app.services import human_query as hq
                    try:
                        await hq.open_query_and_announce(
                            thread_id, role_key=(colleague or {}).get("role_key"),
                            **fr["user_query"])
                    except Exception:
                        logger.exception("user query emit failed thread=%s", thread_id)
            # R3a 跨步记录完备：指针推进后，重放被步进纪律推迟的闸调用
            if str(new_view.get("step_key") or "") != str(view.get("step_key") or ""):
                await _replay_deferred(new_view)
            if new_view.get("step_key") == view.get("step_key"):
                # 指针未动：反问/等确认/答疑/失败——停在本步等用户，不空转。
                # R3(b) 记录完备（停在闸步）：闸步无待确认记录。合法反问不逼重调
                # （工具 needs_input / ask_user_card = 大脑在要参数，是闸步的正当停法）；
                # 其余情况强制重调一轮；重调后仍无记录 → 回合末发机械话术
                # （真报错，不让用户等一张被承诺了却没人发的卡）。
                if step.get("gated") and not (new_view.get("pending") or {}):
                    _legit_ask = any(
                        isinstance(f.get("result"), dict)
                        and (f["result"].get("needs_input") or f["result"].get("user_card"))
                        for f in facts)
                    if _legit_ask:
                        break
                    if step["key"] in gate_nudged:
                        gate_fallback["hit"] = True
                        break
                    gate_nudged.add(step["key"])
                    _gate_tools = [t for t in step.get("tools") or []
                                   if t not in ("query_data", "colleague_memory", "ask_user_card")]
                    if _gate_tools:
                        pending_directives.append(
                            f"\n\n【确认闸纪律】本步是确认闸，你还没有调用 {_gate_tools[0]} 出确认卡。"
                            f"现在先调用 {_gate_tools[0]}（不带 confirm）——系统会自动弹出确认卡——"
                            "然后只说一句'请在下方卡片确认'。")
                        continue
                break

    # 920s 硬闸（与 skill 路径同款）：中转半死连接会绕过 LLM 客户端单次超时，到点 cancel
    # 不等回收，落必达终态——案台在库里，用户重发一条消息即从当前进度续跑。
    timed_out = False
    try:
        await asyncio.wait_for(_drive_steps(), timeout=920.0)
    except asyncio.TimeoutError:
        timed_out = True
        logger.error("transaction turn 超时(920s，放弃式) thread=%s", thread_id)
        await _persist_and_broadcast(
            thread_id, colleague,
            "这一轮处理超时了（模型服务暂时无响应），已停在当前进度；请重发一次或稍后再试。")
    except asyncio.CancelledError:
        raise
    except Exception:
        # 步骤失败的兜底：不再无声死亡——落一条可见消息，回合照常收尾（兜底网/暂停态都还在）
        logger.exception("transaction turn 执行异常 flow=%s thread=%s", app.flow_key, thread_id)
        await _persist_and_broadcast(
            thread_id, colleague,
            "这一步处理出了点问题，已停在当前进度；你重发一条消息我们就从当前位置继续。")

    final_view = te.state_view(app, thread_id, role_key, user if isinstance(user, dict) else {})
    # R2 末扫（调和器）：中途超时/迭代耗尽没走到迭代尾时，这里保证"有记录必有问询"。
    # 幂等（query_opened 标记），吸收原兜底网；问询的存在从此不依赖大脑的叙述纪律。
    await _emit_ready_queries(final_view)
    if gate_fallback["hit"]:
        # R3(b) 终态：强制重调后闸步仍无记录——发机械话术（真报错），绝不静默
        await _persist_and_broadcast(
            thread_id, colleague,
            "这一步的确认操作没有生成成功（处理环节出了点问题）。请重新发一条消息，我会立即补上。")
    if final_view.get("complete"):
        from app.services.skill_memory import load_skill_session, save_skill_session
        session = load_skill_session(thread_id, role_key)
        session.update({"phase": SKILL_SESSION_DONE,
                        "skill_key": app.flow_key,
                        "entry_point": session.get("entry_point") or ""})
        save_skill_session(thread_id, role_key, session)
        await assistant_hub.broadcast(thread_id, {"type": "analysis_finished", "thread_id": thread_id})
    else:
        # 停在本步等用户（反问/答疑/确认闸/超时）：任务条给中断点事实，与需求分析的 pipeline_waiting 同语义
        reason = "turn_timeout" if timed_out else ("approval" if (final_view.get("pending") or {}) else "brain_ask")
        await assistant_hub.broadcast(thread_id, {
            "type": "pipeline_waiting", "thread_id": thread_id,
            "pause": {"kind": reason, "reason_code": reason,
                      "step": str(final_view.get("step_key") or ""),
                      "label": str((final_view.get("step") or {}).get("label") or ""),
                      "resumable": True}})
    await publish_office_event(role_key, "done", "回复完成", thread_id=thread_id)
    await assistant_hub.broadcast(thread_id, {"type": "turn_finished", "thread_id": thread_id})
    await _trace(
        trace_sink,
        tool_name="transaction_engine",
        status="ok",
        duration_ms=int((time.perf_counter() - started) * 1000),
        thread_id=thread_id,
        response_chars=0,
        error=None,
        model=(colleague or {}).get("model_override"),
        prompt_chars=0,
        node_type="transaction_turn",
        role_key=role_key,
    )


async def dispatch_flow_turn(manifest, *, flow_key: str, thread_id, user_text,
                             context_summary, history, colleague, memory_block,
                             final_office_event=None, trace_sink=None,
                             user=None, opportunity_id=None, option_slot=None,
                             card_selections=None, write_mode: str = "",
                             session_phase: Optional[str] = None,
                             fresh: bool = False) -> None:
    """按流形态分发回合：real_bound 且已安装应用 → 事务内核（干净重开可清状态槽）；
    real_bound 但未安装 → 降级普通工具聊天（绝不进需求分析机器）；其余 → 需求分析引擎。
    两台运行时、一套内核服务，互不掺旁路。"""
    from app.services.skill_registry import entity_binding_of

    if entity_binding_of(manifest) == "real_bound":
        app = te.resolve_app(flow_key)
        if app is None:
            logger.error("事务工作流未安装执行器 flow=%s thread=%s（降级普通工具聊天）",
                         flow_key, thread_id)
            from app.services.colleague_turn_runners import _run_tool_turn  # 懒导入防环
            await publish_office_event((colleague or {}).get("role_key") or "assistant",
                                       "thinking", "工作流执行器缺失，切换普通对话",
                                       thread_id=thread_id)
            await _run_tool_turn(
                thread_id, user_text, context_summary,
                _short_term_history(colleague, history), colleague, memory_block,
                _effective_tool_ids(colleague),
                final_office_event=final_office_event, trace_sink=trace_sink,
                user=user, opportunity_id=opportunity_id, option_slot=option_slot,
            )
            return
        # 开工单边界：显式装填(fresh)之外，案台已交割完毕（上一链全探针通过）→
        # 同线程再发=新开工单，干净重开（清状态槽+解绑线程商机）。
        # 链中（未 complete）绝不重开——反问/等确认的续跑不受影响。
        fresh = bool(fresh) or te.desk_complete(
            app, thread_id, (colleague or {}).get("role_key") or "assistant",
            user if isinstance(user, dict) else None)
        if fresh:
            te.clear_state(app, thread_id, (colleague or {}).get("role_key") or "assistant")
            te.clear_thread_binding(thread_id)  # 案台回到第一步：线程绑定一并清，新开工单从建档开始
        mf = manifest if isinstance(manifest, dict) else {}
        await _run_transaction_turn(
            app, thread_id, user_text, context_summary, history, colleague, memory_block,
            final_office_event=final_office_event, trace_sink=trace_sink,
            user=user, opportunity_id=opportunity_id, option_slot=option_slot,
            card_selections=card_selections,
            title=str(mf.get("name") or getattr(manifest, "name", "") or app.label),
        )
        return
    from app.services.colleague_turn_runners import _run_skill_chat  # 懒导入防环
    await _run_skill_chat(
        thread_id, user_text, context_summary, history, colleague, memory_block,
        final_office_event=final_office_event, trace_sink=trace_sink,
        user=user, opportunity_id=opportunity_id, option_slot=option_slot,
        card_selections=card_selections, force_submit=True,
        skill_manifest=manifest, session_phase=session_phase, write_mode=write_mode,
    )
