# -*- coding: utf-8 -*-
"""AI 角色（对话脑）与 Skill 引擎的接线层——两器官架构的「器官间神经」。

宪法（2026-08-28 立法，2026-09-02 按唯一大脑模型修订）：
- 全系统同一时刻只有一个会思考的脑袋：AI 角色。普通聊天阶段只有说话/查目录/提交开关，
  不读 skill 节点内容、不碰登记表；用户确认后任务交给确定性引擎执行；
- 登记环节（agent_fill 节点）= 唯一大脑的显式回合：同一个人设、同一条流式循环，
  大脑亲自调 fill_requirement（需求分析流程工具）结构化落表；缺口判定由引擎确定性完成，
  没有第二次隐藏 LLM；
- 引擎返回的缺口是纯数据，怎么问由角色组织语言；
- 本模块不含任何话术表/关键词清单；业务选项（kp_mode 两个值等）全部来自引擎缺口数据。
- query_data 的权限不在提示词里：物理强制在 data_boundary.execute_read（步骤1），
  角色提示词只描述怎么用，不承诺能读到什么。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from app.services.agent_react import run_stream_chat_loop
from app.services.skill_memory import _load_mem, _save_mem
from app.services.skill_node_state import KP_NODE, KP_PICKS, NODE_STATE_KEY, fill_node, freeze_snapshot, mark_doc_frozen, node_state, unwrap_doc
from app.services.skill_signals import _apply_registration_signal, _brain_ask_manual_signal, _manual_model_signal, _match_card_signal, _signal_with_qty
from app.services.skill_tool_context import TOOL_CTX
from app.services.skill_tools_fill import requirement_prompt
from app.services.skill_turn_engine import _merged_narration, run_skill_agent_turn
from app.services.slot_contract import canonical_key, slot_label
from typing import Any, Callable, Optional


logger = logging.getLogger(__name__)


def _failure_reply(failure: dict) -> str:
    """本步零产出的客户可见说明（由结构化事实合成：节点标签 + 原因码）。

    只陈述引擎事实与可选动作，不含任何 AI 指令——它不是提示词，绝不进模型上下文。
    """
    f = failure if isinstance(failure, dict) else {}
    step = str(f.get("label") or f.get("step") or "").strip()
    # 只说引擎事实：原因码分「超时」与「反复尝试仍未收敛」，都不编造、不冒充成功。
    why = ("模型生成超时（长时间没有给出可采用的结论）"
           if str(f.get("reason_code") or "") == "llm_timeout"
           else "模型连续多次尝试后仍未给出可采用的产出")
    where = f"「{step}」这一步" if step else "这一步"
    return (f"{where}{why}，已如实停止，不会编造结果。"
            f"未落地的部分保持原样，你可以直接回复「继续」重试本步。")


def _gap_data_question(g: dict) -> str:
    """数据事实句兜底（非话术表）：告诉客户还缺什么，选项原样列出（label 优先）。"""
    # brain_ask 缺口（大脑 ask_user 升格的暂停）：问句=大脑原话，不经转述
    if g.get("reason_code") == "brain_ask":
        q = str(g.get("question") or "").strip()
        # 真正 ask_user 升格必带 ≥1 选项；空选项=引擎终检兜底，question 是机制 hint，
        # 不许直出客户——缺口转述（大脑）优先，这里只兜底为中性引导句。
        if not (g.get("options") or []):
            return "还有几项关键配置需要您确认，我梳理清楚再逐项和您对～"
        return q if q else ""
    if g.get("slot") == "kp_required":
        cats = "、".join(g.get("cats") or [])
        return f"还需要确认：{cats} 部件的需求（如某类不需要请说明）"

    def _opt_text(o):
        return str(o.get("label")) if isinstance(o, dict) else str(o)

    options_text = " / ".join(_opt_text(o) for o in (g.get("options") or [])[:6])
    return f"还需要确认：{slot_label(g.get('slot') or '')}" + (f"（{options_text}）" if options_text else "")


class _ChatTurnRuntime:
    """一次对话回合的运行时：原 handle_skill_chat_turn 的 586 行主体按阶段拆成方法。

    契约不变——对外仍是 handle_skill_chat_turn(...)（薄封装，见文件末），
    返回 chat / done / gaps / error 之一。方法顺序即执行顺序：
    _prepare → _apply_card_selections → _chat_phase → _run_task → _emit_done / _emit_gaps。
    """

    def __init__(self, *, thread_id, user_text, colleague, chat_system_prompt, history,
                 opportunity_id=None, option_slot=None, event_sink=None,
                 governance_guard=None, emit_input_card=None, card_selections=None,
                 force_submit=False, skill_phase_hint="", write_mode="",
                 skill_key="requirement_analysis", user_id=None):
        self.thread_id = thread_id
        self.user_text = user_text
        self.colleague = colleague
        # 记忆域：对话写入归属当前用户（多用户隔离）
        self.user_id = str(user_id or "").strip() or None
        self.chat_system_prompt = chat_system_prompt
        self.history = history
        self.skill_key = str(skill_key or "requirement_analysis").strip() or "requirement_analysis"
        self.opportunity_id = opportunity_id
        # 落库写模式（B1）：入口显式给定，向下透传给引擎回合（preview/draft/none）
        self.write_mode = str(write_mode or "").strip().lower()
        self.option_slot = option_slot
        self.event_sink = event_sink
        self.governance_guard = governance_guard
        self.emit_input_card = emit_input_card
        self.card_selections = card_selections
        self.force_submit = force_submit
        self.skill_phase_hint = skill_phase_hint
        # 回合内共享状态（原长函数的局部变量，跨方法要活同一份）
        self.role_key = "assistant"
        self.role_reasoning_effort = None
        self.role_temperature = None
        self.role_max_tokens = None
        self.task_reasoning_effort = "low"
        self.price_ok = True
        self.has_query_data = False
        self.mem: dict = {}
        self.ext: dict = {}
        self.flow: dict = {}
        self.flow_configs: dict = {}
        self.flow_title = ""
        self.click_note = ""
        self.click_labels: list = []
        self.ask_answers: list = []
        self.click_fast_path = False
        self.reply = ""
        self.result_ctx: dict = {}

    def _prepare(self) -> Optional[dict]:
        """角色配置档 + 会话记忆 + Skill 画布配置（回合共同的输入）。"""
        from app.services.data_boundary import colleague_price_ok
        colleague = self.colleague or {}
        self.role_key = colleague.get("role_key") or "assistant"
        response_profile = colleague.get("response_profile") \
            if isinstance(colleague.get("response_profile"), dict) else {}
        self.role_reasoning_effort = response_profile.get("reasoning_effort")
        self.role_temperature = response_profile.get("temperature")
        role_max_tokens = response_profile.get("max_tokens")
        if not isinstance(role_max_tokens, int) or role_max_tokens <= 0:
            role_max_tokens = None
        self.role_max_tokens = role_max_tokens
        # 任务大脑（登记/选型/配件/缺口转述/收尾）是接地工具任务：协议、候选池、登记表全在
        # prompt 里，深思考无增益只烧墙钟（2026-09-05 实测：同体量 prompt 默认档 19.4s vs
        # low 档 6.9s）。默认低档，员工 response_profile 显式配置仍可覆盖。
        self.task_reasoning_effort = self.role_reasoning_effort or "low"
        self.mem = _load_mem(self.thread_id, self.role_key)
        # 流程记忆盖章（跨流防污染）：steps_done/中断点/锁定基线都是「某张流」的状态，
        # 同名步骤键（agent/compose）在别的流里会被误跳过 → 记忆属于别的流时清空重开。
        _mem_skill = str(self.mem.get("skill_key") or "").strip()
        if _mem_skill and _mem_skill != self.skill_key:
            logger.info("skill flow memory switch %s -> %s：重置流程记忆 thread=%s",
                        _mem_skill, self.skill_key, self.thread_id)
            from app.services.skill_memory import SKILL_SESSION_KEY
            _kept_session = self.mem.get(SKILL_SESSION_KEY)
            _save_mem(self.thread_id, self.role_key,
                      {SKILL_SESSION_KEY: _kept_session} if isinstance(_kept_session, dict) else {})
            self.mem = _load_mem(self.thread_id, self.role_key)
        self.mem["skill_key"] = self.skill_key
        self.ext = dict(self.mem.get("ext") or {})
        # 价格可见性（同事级 price_access 布尔，唯一事实源）：
        # query_data 的可读表白名单由工具自管，不再有按同事的 data_boundary。
        self.price_ok = colleague_price_ok(colleague)
        # query_data 试点门控：角色 tool_ids 显式勾选才挂（试点只开方案助手）
        self.has_query_data = isinstance(colleague.get("tool_ids"), list) \
            and "query_data" in colleague.get("tool_ids")

        # Skill 画布配置提前加载：引擎执行与提议预告共用同一份 node_configs（数据驱动）。
        # 流按本回合的 skill_key 取（workflow 型 skill 各有各的图，不再默认需求分析）。
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        repo = ReasoningFlowRepository()
        try:
            flow = repo.ensure_skill_flow(self.skill_key)
        finally:
            repo.close()
        if not flow:
            return {"kind": "error", "reply": f"工作流 {self.skill_key} 未配置，请联系管理员。"}
        self.flow = flow
        self.flow_configs = dict(flow.get("node_configs") or {})
        self.flow_title = str(flow.get("name") or "") or "配置任务"
        return None

    def _apply_card_selections(self) -> None:
        """结构化选项点击落槽（含逐项卡提交/表单批量/打字答案追加路）。

        按 (slot,value) 匹配发卡时持久化的原始选项，带 signal 载荷的原样直传落槽
        （消灭「构造字符串→再解析」）；qty 为 stepper 数量参数，服务端按机箱能力
        clamp 后克隆 signal；留底未命中且为配件槽 → 自由型号走目录模糊匹配。
        委托/改口等语义仍由角色在对话里处理（不匹配留底卡时走旧路径）。
        """
        mem, ext = self.mem, self.ext
        raw_selections: list[tuple[str, str, int]] = []
        if isinstance(self.card_selections, list) and self.card_selections:
            for s in self.card_selections:
                if isinstance(s, dict) and str(s.get("slot") or "").strip() \
                        and str(s.get("value") or "").strip():
                    try:
                        q = int(s.get("qty") or 0)
                    except (TypeError, ValueError):
                        q = 0
                    raw_selections.append((str(s["slot"]).strip(), str(s["value"]).strip(), max(0, q)))
        elif str(self.option_slot or "").strip() not in ("", "general") and self.user_text.strip():
            raw_selections.append((str(self.option_slot).strip(), self.user_text.strip(), 0))
        elif self.user_text.strip() and "\n" not in self.user_text and len(self.user_text.strip()) <= 30 \
                and (mem.get("last_card") or {}).get("options"):
            # 打字答案追加路（Claude Code 式「答案只追加不重derive」）：pending 选项卡在场 +
            # 短文本精确命中唯一槽位的选项值/标签 → 视同点选确定性落槽。不命中/命中多个槽/
            # 长文本（可能是新需求而非答案）→ 照旧走 fill 大脑全量理解，绝不吞新信息。
            _t = self.user_text.strip()
            _hits: dict[str, tuple] = {}
            for o in ((mem.get("last_card") or {}).get("options") or []):
                if isinstance(o, dict) and _t in (str(o.get("value") or ""), str(o.get("label") or "")):
                    _hits.setdefault(str(o.get("slot") or ""), (str(o.get("slot") or ""), str(o.get("value") or ""), 0))
            if len(_hits) == 1:
                raw_selections.append(next(iter(_hits.values())))

        click_note = ""
        click_labels: list[str] = []
        ask_answers: list[str] = []
        had_pending_card = bool((mem.get("last_card") or {}).get("options"))
        for selected, value, want_qty in raw_selections:
            try:
                signal = _match_card_signal(mem, selected, value)
                if signal is None:
                    signal = _manual_model_signal(mem, selected, value)
                if signal is None and selected == "brain_ask":
                    signal = _brain_ask_manual_signal(mem, value)
                logger.info("卡片点击匹配 slot=%s value=%s signal=%s", selected, value[:40],
                            json.dumps(signal, ensure_ascii=False)[:200] if signal else None)
                if signal:
                    if want_qty:
                        signal = _signal_with_qty(
                            signal, want_qty, (mem.get("last_card") or {}).get("pick_meta") or {})
                    from app.services.slot_contract import apply_structured_slots
                    _notes = apply_structured_slots(ext, signal, value, kp_state=node_state(mem, KP_NODE))
                    # 信号里的登记表字段（server_type/platform_type/…）走登记通道落值——
                    # 结构化通道只认部件槽，两条通道共用一套字段契约。
                    _apply_registration_signal(ext, signal, node_state(mem, KP_NODE).get(KP_PICKS))
                    if isinstance(signal, dict) and signal.get("kp_accept_recommendations") \
                            and any(str(n).startswith("客户整单确认推荐") for n in _notes):
                        # 整单委托的确认收敛点：整体卡 desc 声明过类型/平台，点击=客户看见了
                        # 并确认——目录字段快照进 confirmed_slots（改值即失效重求证）
                        from app.services.slot_contract import (confirm_registration_on_bulk_click,
                                                                slot_label)
                        for _k in confirm_registration_on_bulk_click(ext):
                            _notes.append(f"{slot_label(_k)}已随整体确认")
                    _lbl = canonical_key(selected) + (f"×{want_qty}" if want_qty else "")
                    if _notes:
                        _lbl += "：" + "；".join(str(n) for n in _notes[:2])
                    click_labels.append(_lbl)
                    # 点选=客户亲口确认：写确认标记（凡推断必求证的求证侧），值被改写即失效
                    ext.setdefault("confirmed_slots", {})[canonical_key(selected)] = value
                elif selected == "brain_ask":
                    # 大脑提问卡的口头回答（未绑行）：不是槽位信号，落对话由角色语义消化，
                    # 不进 click_labels（不触发点选快速路——答案需要大脑理解而非确定性续跑）。
                    ask_answers.append(value)
                else:
                    from app.services.capabilities import _apply_extracted_slots
                    _apply_extracted_slots(ext, {selected: value}, allow_overwrite=True,
                                           picks=node_state(mem, KP_NODE).get(KP_PICKS))
                    click_labels.append(f"{canonical_key(selected)}={value}")
                    ext.setdefault("confirmed_slots", {})[canonical_key(selected)] = value
            except Exception as exc:
                # 点击失败必须留痕：历史上这里吞掉过整条点击通路（参数求值 NameError），
                # 表现只是「客户点了没反应、卡反复弹」，从日志上完全看不出来。
                logger.exception("选项落槽失败 slot=%s", selected)
                mem.setdefault("click_errors", []).append(
                    {"slot": selected, "value": value, "error": f"{type(exc).__name__}: {exc}"})
        if click_labels:
            click_note = "（用户点击了选项，已登记 " + "；".join(click_labels) + "）"
            # 登记表被改动的正当来源只有两个：属主节点自己写、客户自己点选确认。
            # 后者是客户在改**自己的**表，快照跟着前移，判红才不会把客户误判成越界节点。
            if freeze_snapshot(mem):
                try:
                    mark_doc_frozen(mem, fill_node(), ext)
                except Exception:
                    logger.exception("登记表快照重打点失败 thread=%s", self.thread_id)
        if ask_answers:
            ask_note = "（用户回答了确认卡：" + "、".join(ask_answers) + "）"
            click_note = (click_note + " " + ask_note).strip() if click_note else ask_note
        self.click_note = click_note
        self.click_labels = click_labels
        self.ask_answers = ask_answers
        # 点选快速路径：点击命中且有在途选项卡 → 客户意图无歧义（继续任务，规则2c），
        # 跳过「角色决定是否提交」的 ReAct 轮，系统直接续跑引擎——根治「已登记/正在处理」
        # 口头空转不推进（模型说了提交但没调工具）。
        self.click_fast_path = bool(click_labels or ask_answers) and had_pending_card

    async def _chat_phase(self) -> Optional[dict]:
        """提交前的一轮角色对话：不提交 → 返回聊天终稿；提交 → 返回 None 继续进引擎。"""
        mem, ext = self.mem, self.ext
        save = lambda: _save_mem(self.thread_id, self.role_key, {**mem, "ext": ext})  # noqa: E731
        state = {"submit": False}
        TOOL_CTX.set({"ext": ext, "user_text": self.user_text, "save": save, "price_ok": self.price_ok,
                      "role_key": self.role_key, "event_sink": self.event_sink,
                      "user_id": self.user_id,
                      # fill_requirement 是需求分析流程工具：普通对话回合恒不可用（登记回合内由 brain 置 True）
                      "task_active": False})

        # 大脑指令 = 人设 + 登记表视图/价格守卫 + 阶段提示（ACTIVE 任务态）。
        # 工作流显式发起（「+」/预览/续跑）是唯一入口：force_submit 直接进引擎，登记表与流程内容
        # 由激活后的引擎大脑（run_skill_agent_turn）下发；普通聊天不注入流程执行体。
        system_prompt = "\n\n".join(p for p in (
            self.chat_system_prompt,
            requirement_prompt(None, price_ok=self.price_ok),
        )).strip()
        if self.skill_phase_hint:
            system_prompt = system_prompt + "\n\n" + self.skill_phase_hint
        # 工作流显式发起：由入口（「+」/预览/续跑）force_submit 直接进引擎，模型不再有「提交」工具。
        loop_tools = ["catalog_search", "colleague_memory"]
        if self.has_query_data:
            loop_tools.append("query_data")

        reply = ""
        if self.force_submit or self.click_fast_path:
            # 已同意（试运行直启/任务续跑）或点选快速路：跳过聊天轮直接进引擎——
            # 输入即上下文，登记与说明由引擎的 agent_fill 大脑回合负责（流式可见）。
            # 旧实现在这里先跑一段自由聊天再进引擎：旁白提问会被缺口卡顶掉（09-03 实测 UX 事故），
            # 且每轮多烧一次 LLM（60s+）。
            state["submit"] = True
            logger.info("skill chat force/fast: 跳过聊天轮直接续跑引擎 thread=%s force=%s hits=%d",
                        self.thread_id, bool(self.force_submit), len(self.click_labels))
        else:
            # 聊天兜底（无提交工具）：仅保留对话回复，不再作为「确认轮」进入引擎。
            from app.services.llm_trace import reset_trace_ctx, set_trace_ctx
            _tk = set_trace_ctx(node_type="skill_propose", opportunity_id=self.thread_id, role_key=self.role_key)
            try:
                result = await run_stream_chat_loop(
                    (self.user_text + ("\n" + self.click_note if self.click_note else "")).strip(),
                    {"enabled_tools": loop_tools},
                    system_prompt=system_prompt,
                    allowed_tool_ids=loop_tools,
                    history=self.history,
                    model=(self.colleague or {}).get("model_override") or None,
                    event_sink=self.event_sink,
                    tool_guard=self.governance_guard,
                    max_iterations=6,
                    # 断连止损：中转半死连接最多烧 60s；推理档位/温度取员工 response_profile，不在这里硬编码
                    llm_timeout=60.0,
                    # 单轮整体墙钟上限：间隔看门狗管不住「一直在吐字却不收敛」的慢速生成
                    llm_overall_timeout=120.0,
                    llm_reasoning_effort=self.role_reasoning_effort,
                    llm_temperature=self.role_temperature if isinstance(self.role_temperature, (int, float)) else 0.2,
                    emit_chunk_reset=True,
                )
            finally:
                reset_trace_ctx(_tk)
            reply = str((result or {}).get("answer") or "").strip() if isinstance(result, dict) else str(result or "").strip()
            save()
            logger.info(
                "skill chat react 结束 thread=%s iterations=%s submit=%s reply_len=%s",
                self.thread_id, (result or {}).get("iterations") if isinstance(result, dict) else "?",
                state["submit"], len(reply),
            )

        self.reply = reply
        if not state["submit"]:
            logger.info("skill chat 返回 kind=chat thread=%s", self.thread_id)
            return {"kind": "chat", "reply": reply}
        return None

    async def _run_task(self) -> Optional[dict]:
        """引擎执行（登记表已提交）：装配回合参数 → 900s 放弃式超时 → 回存记忆与状态。"""
        mem, ext = self.mem, self.ext
        # 答案归路（点选/口答进引擎）：大脑提问卡的答案此前只在聊天兜底分支拼进文本，
        # 而试运行/续跑/点选快速路都是 force_submit 直进引擎 —— 答案被丢，大脑看不见，
        # 下一轮把同一个问题原样再问一遍（08-09 实测：同一张 CPU 选项卡连弹三轮）。
        # 客户对大脑提问的回答就是客户消息的一部分，必须随回合进引擎。
        user_text = self.user_text
        if self.ask_answers and self.click_note:
            user_text = (user_text + "\n" + self.click_note).strip()

        # 场景证据用累计文本判断：登记表草稿 + 本句
        from app.services.portal_flow_adapter import build_requirement_text
        full_text = build_requirement_text(self.opportunity_id, user_text) if self.opportunity_id else user_text
        # 冻结守卫（_freeze_requirement）按「机型名是否出现在需求文本」剥臆造机型；
        # 多轮对话里机型是早前轮次点选/口述的，本句（如"256G内存"）不会含机型名，
        # 只用本句会把已确认机型剥掉 → 机型问题无限重弹。近期用户原话并入比对基准。
        prior_user = [str((m or {}).get("content") or "").strip() for m in (self.history or [])
                      if (m or {}).get("role") == "user" and str((m or {}).get("content") or "").strip()]
        if prior_user:
            full_text = "\n".join(prior_user + [full_text])

        # 编排权移交（2026-09-07 P2）：大脑读说明书自己走步骤，不再有节点回合编排器。
        role_name = str((self.colleague or {}).get("name") or self.role_key)

        def _save_runtime() -> None:
            # 节点状态/步骤进度中途持久化（读最新 mem 再写，防覆盖其它键）
            _eng = TOOL_CTX.get().get("engine") or {}
            _sd = sorted(_eng.get("steps_done") or []) if isinstance(_eng.get("steps_done"), (set, list)) else []
            _sid = _load_mem(self.thread_id, self.role_key)
            _save_mem(self.thread_id, self.role_key, {
                **_sid,
                "ext": ext,
                "node_state": _eng.get(NODE_STATE_KEY) or _sid.get(NODE_STATE_KEY) or {},
                "steps_done": _sd,
                "frozen_docs": freeze_snapshot(_eng) or freeze_snapshot(_sid),
            })

        agent_kwargs = dict(
            thread_id=self.thread_id, role_key=self.role_key,
            persona=f"你是 AI 同事「{role_name}」，正在执行「{self.flow_title}」任务，对客户的说明保持专业简洁。",
            full_text=full_text, history=self.history, ext=ext, mem=mem, flow=self.flow,
            event_sink=self.event_sink, tool_guard=self.governance_guard,
            price_ok=self.price_ok, opportunity_id=self.opportunity_id,
            model=(self.colleague or {}).get("model_override") or None,
            reasoning_effort=self.task_reasoning_effort,
            temperature=self.role_temperature, max_tokens=self.role_max_tokens,
            save_mem=_save_runtime, write_mode=self.write_mode,
        )

        # 回合级放弃式超时（2026-09-06 语义保留）：relay 黑洞挂死时到点 cancel 不等待回收，
        # 宁可弃任务转入征询暂停，不可无限静默。P0-② 换 TurnBreaker 看护：900s 硬上限语义
        # 不变，中途加 steering/constrained 观察（observe-only，误报率验证后再武装）。
        from app.services.turn_breaker import TurnBreaker
        breaker = TurnBreaker(thread_id=self.thread_id)
        agent_kwargs["event_sink"] = breaker.wrap_sink(self.event_sink)
        _plan_task = asyncio.ensure_future(run_skill_agent_turn(**agent_kwargs))
        _done, _pending, _why = await breaker.supervise(_plan_task)
        if _pending:
            _plan_task.cancel()
            logger.error("需求分析回合被看护中止 reason=%s 观察记录=%s（relay 黑洞或死循环），放弃回合任务并转入缺配暂停",
                         _why, breaker.observations)
            from app.services.skill_plan_runtime import pause_payload
            result_ctx = {
                "ext": ext,
                "engine_pause": pause_payload(
                    kind="failure", reason_code="turn_timeout", resumable=True,
                    pending=[{"slot": "kp_unmatched", "reason_code": "kp_timeout",
                              "options": 1}],
                    steps_done=sorted(mem.get("steps_done") or [])),
                "engine_gaps": [{
                    "slot": "kp_unmatched", "reason_code": "kp_timeout",
                    "question": "需求分析流程耗时异常（引擎与模型服务之间的连接黑洞），已中止本轮。"
                                "请点击「重新继续分析」重试。",
                    "options": [{"label": "重新继续分析", "value": "重新继续分析",
                                 "group": "如何处理",
                                 "signal": {}}],
                }],
                "awaiting_input": True,
            }
        else:
            result_ctx = _plan_task.result()
        # 大脑就地完善登记表（对象身份保持），回存保证下一轮角色看到最新状态；
        # brain_notes / 步骤进度一并并入 mem——后续卡片分支的 save 都以 mem 为底，
        # 不并进来会被旧值抹掉
        mem = {**mem, "ext": unwrap_doc(result_ctx.get("ext")) or ext,
               "node_state": (result_ctx.get(NODE_STATE_KEY) or mem.get(NODE_STATE_KEY) or {}),
               "brain_notes": (result_ctx.get("brain_notes") or mem.get("brain_notes") or []),
               "steps_done": (result_ctx.get("steps_done_list")
                              or sorted(result_ctx.get("steps_done") or [])),
               # 引擎终态随回合回存：data_answer 型流没有 compose 步，flow_delivered
               # 只认 engine_result=done 的话，交付后下一条消息会误入旧流程记忆分支
               "engine_result": str(result_ctx.get("engine_result") or ""),
               "locked_baseline": (result_ctx.get("_locked_baseline") or None),
               "lock_reason": (result_ctx.get("lock_reason") or ""),
               "model_selection": (result_ctx.get("model_selection") or None),
               "frozen_docs": (freeze_snapshot(result_ctx) or freeze_snapshot(mem)),
               # 暂停载荷随回合终态回存（P4-1）：本回合没暂停则显式清空，不留上一轮的旧中断点
               "engine_pause": (result_ctx.get("engine_pause") or None)}
        _save_mem(self.thread_id, self.role_key, mem)
        self.mem = mem
        self.result_ctx = result_ctx
        if result_ctx.get("fatal_error"):
            return {"kind": "error", "reply": f"需求分析执行失败：{result_ctx.get('fatal_error')}"}
        return None

    async def _emit_ask_card(self, ask: dict) -> list:
        """大脑提问卡广播：问题文案=大脑原话，选项=大脑给的 label；返回留底载荷（点击匹配用）。"""
        if self.emit_input_card is None:
            return []
        ask_slot = str(ask.get("slot") or "brain_ask")
        cards, opts = [], []
        for o in (ask.get("options") or []):
            label = str(o.get("label") or "").strip()
            if not label:
                continue
            cards.append({"label": label, "value": label,
                          "desc": str(o.get("description") or ""), "slot": ask_slot,
                          "group": "需要您确认",
                          **({"recommended": True} if o.get("recommended") else {}),
                          **({"rule_match": True} if o.get("rule_match") else {}),
                          **({"rule_conflict": o["rule_conflict"]}
                             if isinstance(o.get("rule_conflict"), dict) else {})})
            entry = {"slot": ask_slot, "value": label}
            row_key = str(ask.get("row") or "").strip()
            # 信号派生唯一出口=ask_option_signal（与引擎缺口路同一口径）。两处各写一套
            # 解释已实际漂移过一次（pick_all 只加了本兜底路，引擎路点击信号全空，
            # 2026-09-13 A1 实测整段死循环）——这里只做行身份解析后转交，不再自带第二套。
            _row_cat = ""
            if row_key:
                from app.services.part_selector import row_ref_meta
                from app.services.skill_node_state import KP_ROW_IDS, kp_state
                _row_cat = str((row_ref_meta(row_key, (self.result_ctx or {}).get("kp_parts"),
                                            kp_state(self.result_ctx or {}).get(KP_ROW_IDS))
                                or {}).get("category") or "")
            from app.services.skill_plan_runtime import ask_option_signal
            sig = ask_option_signal(row_key, o, ask_slot, category=_row_cat)
            if sig:
                entry["signal"] = sig
            opts.append(entry)
        if not cards:
            return []
        try:
            await self.emit_input_card(str(ask.get("question") or ""),
                                       {"question": str(ask.get("question") or ""),
                                        "options": cards, "slot_options": {ask_slot: cards},
                                        "why": "", "missing_fields": [ask_slot],
                                        "narration": _merged_narration(self.result_ctx)})
        except Exception:
            logger.exception("大脑提问卡广播失败")
            return []
        return opts

    async def _emit_done(self, brain_asks: list) -> dict:
        """终态 done：交付物已就绪；大脑提问卡若有则广播并按载荷留底。"""
        logger.info("skill chat 返回 kind=done thread=%s", self.thread_id)
        if brain_asks:
            ask_opts = await self._emit_ask_card(brain_asks[0])
            if ask_opts:
                try:
                    _save_mem(self.thread_id, self.role_key,
                              {**self.mem, "ext": unwrap_doc(self.result_ctx.get("ext")) or self.ext,
                               "last_card": {"options": ask_opts}})
                except Exception:
                    logger.exception("大脑提问卡载荷持久化失败")
        return {"kind": "done", "reply": self.reply, "engine_ctx": self.result_ctx,
                "narration": _merged_narration(self.result_ctx)}

    def _annotate_gaps(self, gaps: list) -> tuple:
        """缺口下行前的事实标注（自选器上下文/已锁定机型）→ 返回 (pick_meta, skip_gap_ask)。"""
        # 自选器上下文弹出缺口（机器数据不进转述 JSON），随 last_card 留底给 card-pick 端点
        pick_meta = None
        for g in gaps:
            if isinstance(g.get("pick_meta"), dict):
                pick_meta = g.pop("pick_meta")
                break

        # 已锁定机型随缺口下行（纯数据）：转述模型可自然带到问句里，用户全程看得见选型进展
        locked_model = str(((self.result_ctx.get("model_selection") or {}).get("name")) or "")
        if locked_model:
            lock_reason = str(self.result_ctx.get("lock_reason") or "")
            for g in gaps:
                g.setdefault("context", {})["locked_model"] = locked_model
                if lock_reason:
                    g["context"]["lock_reason"] = lock_reason

        # S3 确认话+引问合一：登记大脑跑过的回合，旁白已按「确认已登记 + 引出还缺项」织入
        # （节点使命指令），卡问句直接用数据事实句，砍掉独立缺口转述 LLM 调用
        # （2026-09-05 实测 ~30s/次）。fill 大脑被跳过（点选/打字快速路，需要贴上下文的
        # ack 转述）或非 L0 缺口（机型/配件段）时保留转述调用——只对第一个缺口发一次。
        fill_nar = str(self.result_ctx.get("fill_narration") or "").strip()
        # 推荐制（2026-09-06 用户定调）：带选项的缺口必须过大脑话术——干巴巴列选项不需要
        # AI，大脑要给推断+推荐；只有开放回答缺口（无选项，如 kp_required）才退数据事实句
        skip_gap_ask = bool(fill_nar) and not any(g.get("options") for g in gaps)
        return pick_meta, skip_gap_ask

    def _fix_kp_mode(self, g: dict, q: str) -> str:
        """kp_mode 缺口补机器可点选项（话术里没提到选项时），问句原样返回。"""
        from app.services.skill_phases import KP_MODE_OPTIONS
        if g.get("slot") == "kp_mode" and not any(o in q for o in KP_MODE_OPTIONS):
            g["options"] = list(KP_MODE_OPTIONS)
            return q + "\n选项：" + " / ".join(KP_MODE_OPTIONS)
        return q

    async def _transcribe_gap(self, gaps: list, skip_gap_ask: bool) -> tuple:
        """缺口转述（同一颗大脑的续话）→ 返回 (问句, 推荐 label)；不该转述时返回 ("", "")。

        brain_ask 缺口：问句=大脑原话（_gap_data_question 直取），无需转述 LLM 再措辞。
        例外：brain_ask 且 options 为空 = 引擎终检兜底（engine_gate）——大脑已耗尽重试仍无法交付，
        此时 question 存的是机制 hint，不能直出客户，必须让同一颗大脑把它重述成自然客户问句。
        （真正 ask_user 升格的缺口强制 ≥1 个选项，故 brain_ask 空选项只可能来自这条引擎兜底。）
        """
        question = ""
        gap_recommend = ""
        _term_brain_ask = (str(gaps[0].get("reason_code") or "") == "brain_ask"
                           and not bool(gaps[0].get("options")))
        if ((not skip_gap_ask and str(gaps[0].get("reason_code") or "") != "brain_ask")
                or _term_brain_ask):
            # 缺口转述=同一颗大脑的续话：带人设+近期对话+本轮角色已说的话，让问句贴上下文。
            # 只喂缺口 JSON 的无上下文转述=固定数据进固定话术出，事实上的硬编码模板。
            hist_tail = [dict(m) for m in (self.history or [])[-6:]
                         if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                         and str(m.get("content") or "").strip()]
            ack_rule = ""
            if self.click_labels:
                ack_rule = "客户刚在选项卡上点选确认了：" + "、".join(self.click_labels)
            # 话术纪律（顾问口吻/label 文案/判断依据/一次一问）住在左栏「使用说明」，
            # 这里只摆事实 + JSON 契约——代码不再自带第二套提示词。
            from app.services.skill_step_runtime import manual_rules_block
            gap_prompt = ("（系统消息）配置引擎返回第一个缺口数据：\n"
                          "<<ACK_RULE>>\n<<GAP_DATA>>\n"
                          "只输出 JSON：{\"reply\":\"你要发给客户的那句话\","
                          "\"recommend\":\"你推荐的选项 label 原文，没有把握就留空\"}。")
            _manual = str(((self.flow.get("graph") or {}).get("manual_rules")) or "")
            _sys = "\n\n".join(p for p in (self.chat_system_prompt,
                                          manual_rules_block(_manual)) if p)
            ask_messages = [
                {"role": "system", "content": _sys},
                *hist_tail,
                {"role": "assistant", "content": self.reply or ""},
                {"role": "user", "content": (gap_prompt
                            .replace("<<ACK_RULE>>", ack_rule)
                            .replace("<<GAP_DATA>>", json.dumps(gaps[0], ensure_ascii=False)))},
            ]
            try:
                from app.services import llm_client
                from app.services.llm_trace import record_llm_trace
                ask = None
                # 失败可见 + 重试一次：话术调用挂了就退化成干巴巴数据句（2026-09-06 实测），
                # 不许静默吞——失败必须落 trace，且重试一次再降级
                for _ga_attempt in (1, 2):
                    _g_t0 = time.perf_counter()
                    _g_pr = sum(len(str((m or {}).get("content") or "")) for m in ask_messages)
                    try:
                        ask = await llm_client.chat_json(
                            ask_messages, model=(self.colleague or {}).get("model_override") or None,
                            temperature=self.role_temperature if isinstance(self.role_temperature, (int, float)) else 0.3,
                            timeout=30.0, max_attempts=1, reasoning_effort=self.task_reasoning_effort)
                        record_llm_trace(
                            node_type="skill_gap_ask", opportunity_id=self.thread_id, role_key=self.role_key,
                            duration_ms=int((time.perf_counter() - _g_t0) * 1000), prompt_chars=_g_pr,
                            response_chars=len(str(ask or "")), status="ok")
                        break
                    except Exception as exc:
                        record_llm_trace(
                            node_type="skill_gap_ask", opportunity_id=self.thread_id, role_key=self.role_key,
                            duration_ms=int((time.perf_counter() - _g_t0) * 1000), prompt_chars=_g_pr,
                            status="error", error=str(exc)[:200])
                        if _ga_attempt == 2:
                            raise
                        logger.warning("缺口转述第 1 次失败，重试: %s", exc)
                if isinstance(ask, dict):
                    question = str(ask.get("reply") or ask.get("question") or ask.get("content") or "").strip()
                    # 推荐制（2026-09-06 用户定调）：大脑给出倾向选项 → 卡上标「推荐」
                    gap_recommend = str(ask.get("recommend") or ask.get("recommend_value")
                                        or ask.get("recommend_label") or "").strip()
                if not question and isinstance(ask, str):
                    question = ask.strip()
            except Exception as exc:
                logger.warning("缺口转述生成失败，退回数据兜底: %s", exc)
                question = ""
        return question, gap_recommend

    async def _emit_gap_card(self, gaps: list, questions: list, gap_recommend: str,
                             pick_meta) -> tuple:
        """结构化选项卡广播 + 载荷留底 → 返回 (card_emitted, card_opts)。

        一缺口一卡（问题文本随卡落库，选项为空 = 开放回答）；旁白只随第一张卡落库
        （emit_input_card 每收一次 narration 都会持久化一次）。
        """
        card_emitted = False
        card_opts: list = []
        shared_narration = _merged_narration(self.result_ctx)
        if self.emit_input_card is not None:
            # 一轮只发第一张卡（逐条问）：card_opts/last_card 只留可见卡的选项，
            # 点击快速路径 (slot,value) 与屏幕上的卡严格一致
            for gi, g in enumerate(gaps[:1]):
                slot_key = str(g.get("slot") or "general")
                group = slot_label(slot_key)
                cards = []
                for o in (g.get("options") or []):
                    if isinstance(o, dict):
                        opt = {"label": str(o.get("label") or o.get("value") or ""),
                               "value": str(o.get("value") or o.get("label") or ""),
                               "desc": str(o.get("desc") or ""),
                               "slot": str(o.get("slot") or slot_key),
                               # 逃生项显式空组别（前端把非空组当卡头，逃生项不占组位）
                               "group": str(o.get("group") if o.get("group") is not None else group)}
                        # 推荐标记（推荐制）：大脑话术 JSON 的 recommend 命中 value/label
                        if gap_recommend and gap_recommend in (opt["value"], opt["label"]):
                            opt["recommended"] = True
                        if o.get("recommended"):
                            opt["recommended"] = True
                        # 词典卡影子校验标注透传（「规则推荐/与规则不符」徽标数据）
                        if o.get("rule_match"):
                            opt["rule_match"] = True
                        if isinstance(o.get("rule_conflict"), dict):
                            opt["rule_conflict"] = o["rule_conflict"]
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
                q = questions[gi]
                # B4 兜底：终检机制缺口（brain_ask 且零选项）不许渲染成「点不掉/答不进」的死卡，
                # 降级为普通文字问句（走聊天回复，不占 last_card 选项卡）。
                if not cards and str(g.get("reason_code") or "") == "brain_ask":
                    continue
                try:
                    _payload = {"question": q, "options": cards,
                                "slot_options": {slot_key: cards},
                                "why": "", "missing_fields": [slot_key],
                                "narration": (shared_narration if gi == 0 else "")}
                    # 卡能力声明（2026-09-06 插头化）：parts_card=True → 前端渲染表单卡
                    # （自选下拉+数量步进+手动型号+提交）；渲染器零业务词，能力全由数据声明
                    if g.get("parts_card"):
                        _payload.update({"parts_card": True, "row": str(g.get("row") or ""),
                                         "qty": g.get("qty"), "qty_max": g.get("qty_max"),
                                         "unit_label": str(g.get("unit_label") or "")})
                    await self.emit_input_card(q, _payload)
                    card_emitted = True
                except Exception:
                    logger.exception("选项卡广播失败 slot=%s", slot_key)
            # 结构化载荷随卡持久化到会话记忆：点击轮按 (slot,value) 匹配原样直传，
            # 服务端留底不信任客户端回传值。全量留底（含无 signal 的机型/逃生项）：
            # had_pending_card 是点击快速路径的判定条件，只留 signal 会让机型卡点击
            # 掉回 LLM 决策轮（点完又问「可以吗」）。ext 必须取引擎产物（补抽会替换
            # ext 对象），用本地旧对象会把引擎补好的信号从记忆里抹掉
            if card_opts:
                try:
                    _save_mem(self.thread_id, self.role_key,
                              {**self.mem, "ext": unwrap_doc(self.result_ctx.get("ext")) or self.ext,
                               "last_card": {"options": card_opts,
                                             **({"pick_meta": pick_meta} if pick_meta else {})}})
                except Exception:
                    logger.exception("选项卡结构化载荷持久化失败")
        return card_emitted, card_opts

    async def _emit_gaps(self, er: dict, brain_asks: list) -> dict:
        """缺口回合：一缺口一卡（逐条问）→ 结构化卡/大脑提问卡兜底 → 返回 gaps 终态。"""
        # ── 缺口：逐条问（Claude Code 式）+ 旁白织入（S3）──
        # 引擎产出全部缺口，但一轮只弹第一张卡（答完引擎恢复 → 下一缺口重新收敛再问），
        # 机型/配件段缺口天然后置单发。
        # 旧版（S1）同轮批量弹 N 卡：实测用户点一张后兄弟卡齐塌、几秒后又重发未答卡，
        # 观感=顺序错乱（2026-09-06 实机+落库取证），改回一轮一问。每张卡自带 slot，
        # 点击/打字按 (slot,value) 路由。
        gaps = [g for g in (er.get("gaps") or []) if isinstance(g, dict)]
        if not gaps:
            logger.info("skill chat 返回 kind=error(未知引擎状态) thread=%s", self.thread_id)
            return {"kind": "error", "reply": "引擎返回了未知状态"}
        pick_meta, skip_gap_ask = self._annotate_gaps(gaps)
        question, gap_recommend = await self._transcribe_gap(gaps, skip_gap_ask)
        questions = []
        for i, g in enumerate(gaps):
            q = (question if i == 0 else "").strip() or _gap_data_question(g)
            questions.append(self._fix_kp_mode(g, q))
        card_emitted, card_opts = await self._emit_gap_card(gaps, questions, gap_recommend, pick_meta)
        # 有结构化候选卡就发卡，丢弃大脑的开放式自由文本问（open-ask 抢跑根因，2026-09-08）。
        # 只有系统没产出任何结构化卡时，才把大脑 ask_user 升格的提问弹成卡兜底。
        if brain_asks and not card_emitted:
            ask_opts = await self._emit_ask_card(brain_asks[0])
            if ask_opts:
                merged = (list(card_opts) if card_emitted else []) + ask_opts
                try:
                    _save_mem(self.thread_id, self.role_key,
                              {**self.mem, "ext": unwrap_doc(self.result_ctx.get("ext")) or self.ext,
                               "last_card": {"options": merged,
                                             **({"pick_meta": pick_meta} if pick_meta else {})}})
                except Exception:
                    logger.exception("大脑提问卡载荷持久化失败")
        logger.info("skill chat 返回 kind=gaps slots=%s card=%s skip_ask=%s thread=%s",
                    [g.get("slot") for g in gaps], card_emitted, skip_gap_ask, self.thread_id)
        return {"kind": "gaps", "reply": (questions[0] if questions else ""), "gap": gaps[0],
                "gaps": gaps, "engine_ctx": self.result_ctx,
                "card_emitted": card_emitted,
                "narration": _merged_narration(self.result_ctx)}

    async def run(self) -> Optional[dict]:
        """对话回合主干：装配 → 点选落槽 → 对话/直进引擎 → done / gaps 分派。"""
        from app.services.skill_plan_runtime import engine_result_of
        _early = self._prepare()
        if _early is not None:
            return _early
        self._apply_card_selections()
        _chat = await self._chat_phase()
        if _chat is not None:
            return _chat
        _bad = await self._run_task()
        if _bad is not None:
            return _bad

        result_ctx = self.result_ctx
        er = engine_result_of(result_ctx)
        # 大脑提问卡（kp 大脑 ask_user 登记）：问题文案=大脑原话，选项=大脑给的 label。
        # row 绑定行键 → 选项带 kp_row_merge 信号（点击把客户回答记进该行的补充回答，
        # 行键取自登记原文不变，不会让已锁定的选型失配）；未绑行 → 纯口头回答，由角色在对话里消化。
        brain_asks = [a for a in (result_ctx.get("kp_asks") or [])
                      if isinstance(a, dict) and a.get("question")][:1]
        # 暂停缺口已携带同一提问（runtime 的 brain_ask gap）时不重复弹卡
        if any(str(g.get("reason_code") or "") == "brain_ask" for g in (er.get("gaps") or [])):
            brain_asks = []
        if er.get("status") == "done":
            return await self._emit_done(brain_asks)
        if er.get("status") == "failed":
            # 本步整轮零产出（超时/空产出）：如实报失败给客户与看板，不静默、不弹死卡。
            return {"kind": "error", "reply": _failure_reply(er.get("failure"))}
        return await self._emit_gaps(er, brain_asks)


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
    force_submit: bool = False,
    skill_phase_hint: str = "",
    write_mode: str = "",
    skill_key: str = "requirement_analysis",
) -> Optional[dict]:
    """角色对话脑主循环。返回引擎终态 dict（done 时含 artifact 供上层做落库收尾），无引擎时返回 None。

    emit_input_card(question_text, gap)：上层把它渲染成结构化选项卡（UI 数据=缺口，文案=角色）。
    skill_key：本回合执行的 workflow skill（决定引擎加载哪张图）。
    """
    return await _ChatTurnRuntime(
        thread_id=thread_id, user_text=user_text, colleague=colleague,
        chat_system_prompt=chat_system_prompt, history=history,
        opportunity_id=opportunity_id, option_slot=option_slot, event_sink=event_sink,
        governance_guard=governance_guard, emit_input_card=emit_input_card,
        card_selections=card_selections, force_submit=force_submit,
        skill_phase_hint=skill_phase_hint, write_mode=write_mode,
        skill_key=skill_key,
        user_id=str((user or {}).get("user_id") or "").strip() or None).run()
