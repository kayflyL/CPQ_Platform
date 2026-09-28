# -*- coding: utf-8 -*-
"""任务回合引擎：编排壳主循环、节点步进、闸门裁决、终检。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）；同日把 451 行的
run_skill_agent_turn 拆成 _SkillTurnRuntime（方法即回合阶段），对外签名与契约不变。
"""
from __future__ import annotations

import asyncio
import logging
import json
import time
from app.services.agent_react import run_stream_chat_loop
from app.services.skill_memory import _brain_note_summary, _slots_view
from app.services.skill_node_state import DOC_SNAPSHOT_KEY, NODE_STATE_KEY, doc_freeze_violation, freeze_snapshot, mark_doc_frozen
from app.services.skill_plan_runtime import effective_node_tools, steps_payload
from app.services.skill_step_runtime import _emit_brain_status, _emit_step_trace, _engine_begin_step, _node_done_payload, manual_rules_block
from app.services.skill_tool_context import TOOL_CTX
from typing import Optional


logger = logging.getLogger(__name__)


def _last_rejection(result) -> Optional[dict]:
    """本轮工具调用里最后一次「被工具拒绝」的真实返回（没有则 None）。"""
    last_bad = None
    for c in ((result or {}).get("tool_calls_log") or []):
        res = (c or {}).get("result")
        if isinstance(res, dict) and res.get("ok") is False:
            last_bad = res
    return last_bad


def _tool_findings_map(result: dict, *, per_entry: int = 500, into: Optional[dict] = None) -> dict:
    """把一次大脑尝试的工具战果收成「调用+参数 → 结论行」映射（去重，失败结果剔除）。

    重试/续跑把它渲染回上下文，大脑直接复用检索结论，不再从零重查——2026-09-12 实测：
    kp_reason 撞顶重试整步重来 3 次、每次全部重新检索，128s 由此而来。
    """
    seen = into if isinstance(into, dict) else {}
    for c in ((result or {}).get("tool_calls_log") or []):
        if not isinstance(c, dict):
            continue
        res = c.get("result")
        if isinstance(res, dict) and res.get("ok") is False:
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        args = c.get("args") if isinstance(c.get("args"), dict) else {}
        try:
            body = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)
        except Exception:
            body = str(res)
        key = name + "|" + json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)[:120]
        seen[key] = f"· {name}({json.dumps(args, ensure_ascii=False, default=str)[:80]}) → {body[:per_entry]}"
    return seen


def _render_findings(seen: dict, *, total: int = 6000) -> str:
    """战果映射 → 有总量上限的紧凑文本（先到先得，超总量截断）。"""
    out: list[str] = []
    used = 0
    for ln in (seen or {}).values():
        if used + len(ln) > total:
            break
        out.append(ln)
        used += len(ln)
    return "\n".join(out)


def step_gate_verdict(pending: list, step_key: str) -> str:
    """某步回喂收口后的走向（编排壳唯一的推进闸门，纯函数）。

    - advance：本步已落定 → 推进下一步
    - pause：本步既没写产物也没升格提问（回喂重试耗尽）→ 如实暂停交客户
    - deliver：所有大脑节点都已落定 → 才允许组装 + 交付
    """
    if pending and str((pending[0] or {}).get("step") or "") != str(step_key or ""):
        return "advance"
    if pending:
        return "pause"
    return "deliver"


async def run_brain_attempts(user_msg: str, *, loop_kwargs: dict, settle,
                             emit_status=None, deadline_s: float = 420.0,
                             max_attempts: int = 3,
                             round_timeout_s: float = 180.0,
                             findings_out: Optional[dict] = None) -> tuple:
    """大脑回合 + 收口校验的循环（编排壳本体，不知道任何节点）。

    每轮：跑一次大脑流式循环 → 工具被拒就把工具真实返回喂回重试 → 否则交 settle 判定
    （settle 返回 {"action": "done"|"retry"|"wait"}）。最后一轮不再因工具被拒而跳过 settle：
    本步是否完成由**产物**说了算，不由「工具参数是否被拒」说了算（否则选型已全部落地、
    只因一次多余调用被拒就跳过校验 → 步骤不标 done → 终检拿旧快照判缺 → 客户看到零选项死卡）。

    检索战果复用：每次尝试的工具结论（去重压缩）注入下一次尝试的消息里——重试不再从零
    重查；findings_out（可选 dict）带出本步全部尝试合并后的战果，供调用方跨回合持久化。

    返回 (最后一次大脑结果, 收口动作)：动作 "wait" = settle 已把引擎置为暂停态；
    "timeout" = 到点/单轮挂死被断，本步**未必**没产出（是否完成由调用方按产物判定，
    不由「有没有超时」判定——否则落地一半却报失败，等于把半成品当废品）。
    """
    result: dict = {}
    feedback = ""
    feedback_is_tool = True
    findings_map: dict = {}
    deadline = time.monotonic() + float(deadline_s)
    total = max(1, int(max_attempts))
    action = "retry"
    for attempt in range(total):
        budget = float(deadline_s)
        if attempt > 0:
            budget = deadline - time.monotonic()
            if budget <= 0:
                # 到点不再发起新尝试：状态对用户可见（不静默），未完成部分按现状交回。
                if emit_status:
                    await emit_status("耗时较长，未完成部分交系统按现状继续")
                action = "timeout"
                break
            if emit_status:
                await emit_status("工具校验未通过，附上工具真实返回重试中…" if feedback_is_tool
                                  else "引擎校验未通过，请补齐后再推进本步…")
        msg = user_msg
        if attempt > 0:
            msg += "\n\n【系统反馈（最近一次未通过校验）】\n" + feedback
            _rendered = _render_findings(findings_map)
            if _rendered:
                msg += ("\n\n【此前尝试已完成的检索/工具结果（结论直接复用，勿重复查询）】\n"
                        + _rendered)
        # 每次尝试的整体墙钟上限 = min(剩余预算, 单轮上限)：
        # 内层流式看门狗只管「两次输出之间的空隙」，管不住「一直在吐字却迟迟不收敛」的慢速
        # 生成（实测单轮静默 1605s）；内层到点抛 LLMError 走既有失败路径，wait_for 兜最后一道。
        attempt_kwargs = dict(loop_kwargs)
        attempt_kwargs["llm_overall_timeout"] = max(1.0, min(budget, float(round_timeout_s)))
        try:
            result = await asyncio.wait_for(
                run_stream_chat_loop(msg, **attempt_kwargs), timeout=budget)
        except asyncio.TimeoutError:
            if emit_status:
                await emit_status("耗时较长，未完成部分交系统按现状继续")
            action = "timeout"
            break
        _tool_findings_map(result, into=findings_map)
        if isinstance(findings_out, dict):
            findings_out["text"] = _render_findings(findings_map)
        bad = _last_rejection(result)
        # 工具拒绝只在「大脑没有收口正文」时才值得回喂重试：探索型步骤（query_data 试错→
        # 自我纠正）的日志里躺着失败调用是常态，若一律重开，一份已写完的报告会被整个丢弃
        # 重生成（2026-09-16 趋势分析实测三份连体报告+三倍耗时）。产物已出，收口交给 settle。
        if (bad is not None and attempt < total - 1
                and not str(result.get("answer") or "").strip()):
            feedback = json.dumps(bad, ensure_ascii=False)[:500]
            feedback_is_tool = True
            continue
        verdict = await settle(result) or {}
        action = str(verdict.get("action") or "retry")
        if action in ("done", "wait"):
            break
        feedback = str(verdict.get("feedback") or "")
        feedback_is_tool = False
    return result, action


class _SkillTurnRuntime:
    """一次任务回合的运行时：原 run_skill_agent_turn 的 451 行主体按阶段拆成方法。

    契约不变——对外仍是 run_skill_agent_turn(...) -> engine_ctx（薄封装，见文件末）。
    方法顺序即执行顺序：_prepare → _emit_pipeline_start → _run_one_step（循环）→ _deliver。
    """

    def __init__(self, *, thread_id, role_key, persona, full_text, history, ext, mem, flow,
                 event_sink=None, tool_guard=None, price_ok=True, opportunity_id=None,
                 model=None, reasoning_effort=None, temperature=None, max_tokens=None,
                 save_mem=None, write_mode=None):
        self.thread_id = thread_id
        self.role_key = role_key
        self.persona = persona
        self.full_text = full_text
        self.history = history
        self.ext = ext
        self.mem = mem
        self.flow = flow
        self.event_sink = event_sink
        self.tool_guard = tool_guard
        self.price_ok = bool(price_ok)
        self.opportunity_id = opportunity_id
        # 落库写模式（B1）：由入口显式给定（preview 不落库 / draft 落草稿 / none 不落库）
        self.write_mode = str(write_mode or "").strip().lower()
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.save_mem = save_mem
        # 回合内共享状态（原长函数的局部变量，跨方法要活同一份）
        self.engine: dict = {}
        self.flow_configs: dict = {}
        self.steps: list = []
        self.manual_rules = ""
        self.narration: list = []
        self.node_narration: dict = {}
        self._cur_step: dict = {}
        self._cur_step_started = 0.0
        self._fill_emitted = False
        self._stuck: dict = {"hint": ""}
        self._brain_steps: list = []
        self._drift_reported: set = set()

    def _prepare(self) -> None:
        """引擎容器装配 + 跨轮状态恢复 + 工具上下文注入 + 大脑上下文三件套。"""
        flow = self.flow
        flow_configs = flow.get("node_configs") if isinstance(flow.get("node_configs"), dict) else {}

        node_labels = {str(nd.get("id") or ""): str(nd.get("label") or "")
                       for nd in (flow.get("graph") or {}).get("nodes") or [] if isinstance(nd, dict)}
        # 节点私有状态容器（节点隔离）：与 mem 共用同一块对象，回合内就地改、回合末回写 mem。
        _node_state = self.mem.get(NODE_STATE_KEY)
        if not isinstance(_node_state, dict):
            _node_state = {}
        # 断点唯一出处（P5-B1）：上一回合的暂停载荷 mem.engine_pause 说了「停在哪、进度是什么」。
        # 它与 mem.steps_done 不一致时以载荷为准（载荷是回合终态快照；mem 会被中途 save 覆盖），
        # 只把两侧差异记成事实（resume_mismatch），不猜、不进话术。
        _pause = self.mem.get("engine_pause") if isinstance(self.mem.get("engine_pause"), dict) else None
        _resume_steps = {str(s) for s in ((((_pause or {}).get("resume") or {}).get("steps_done")) or [])}
        _mem_steps = {str(s) for s in (self.mem.get("steps_done") or [])}
        engine: dict = {
            "requirement_text": self.full_text, "ext": self.ext, "flow_configs": flow_configs,
            "opportunity_id": self.opportunity_id or self.thread_id, "price_access": self.price_ok,
            "write_mode": self.write_mode,
            "node_labels": node_labels,
            "thread_id": self.thread_id,
            "node_state": _node_state,
            "steps_done": set(_resume_steps or _mem_steps),
            # 工作记忆跨轮承接：上一回合的工具轨迹本回合仍要可见（截 3 条，与 _note 同一窗口）。
            # 不承接的话 engine 每轮重建 → mem.brain_notes 只剩「本回合」一条，检索轨迹每轮归零。
            "brain_notes": list(self.mem.get("brain_notes") or [])[-3:],
        }
        # B2 读回：商机需求草稿是线索登记表的真相（对话期间每轮原地更新）。回合开始把它
        # 播种回本轮工作副本 ext；写模式非 draft（试运行/无商机）或库里还没有草稿时不动。
        if self.write_mode == "draft" and str(self.opportunity_id or "").strip():
            try:
                from app.services.portal_flow_adapter import seed_ext_from_requirement_draft
                seed_ext_from_requirement_draft(self.ext, str(self.opportunity_id).strip())
            except Exception:
                logger.exception("读取需求草稿播种 ext 失败 opp=%s", self.opportunity_id)
        if _pause:
            engine["resume_from"] = {"kind": str(_pause.get("kind") or ""),
                                     "step": str(_pause.get("step") or ""),
                                     "reason_code": str(_pause.get("reason_code") or ""),
                                     "resumable": bool(_pause.get("resumable", True))}
            if _resume_steps and _resume_steps != _mem_steps:
                engine["resume_mismatch"] = {"pause": sorted(_resume_steps), "mem": sorted(_mem_steps)}
        # 机型基准跨轮恢复：baselines/_locked_baseline 是引擎内存状态，上一轮锁定后仅持久化了
        # ext.server_model；若本轮 model_reason 已 done 被跳过，compose 会读不到整机基准
        # （base_config_id/bom_template_id）→ 报「整机基准缺失」。这里从 mem 回填。
        _lb = self.mem.get("locked_baseline") if isinstance(self.mem.get("locked_baseline"), dict) else None
        if _lb:
            engine["_locked_baseline"] = dict(_lb)
            engine["baselines"] = [dict(_lb)]
            engine["lock_reason"] = str(self.mem.get("lock_reason") or "")
            engine["model_selection"] = dict(self.mem.get("model_selection") or _lb)

        # 登记表冻结快照跨轮恢复：属主节点落定后打的快照随记忆存续，否则「下游回填上游」
        # 的判红只在当轮有效——下一轮回填就静默漏过去了（引擎内存对象每轮重建）。
        _fz = freeze_snapshot(self.mem)
        if _fz:
            engine[DOC_SNAPSHOT_KEY] = _fz

        TOOL_CTX.set({"ext": self.ext, "task_active": True, "engine": engine,
                      "event_sink": self.event_sink, "thread_id": self.thread_id,
                      "price_ok": bool(self.price_ok),
                      "brain_asks": list(self.mem.get("pending_asks") or []),
                      "save": (self.save_mem if callable(self.save_mem) else None)})

        # 大脑上下文三件套（无转译层）：persona + 公开协议 + 节点结构化清单（system）；
        # 客户任务规则原文 + 登记表 + 工作记忆（user 尾）。没有任何代码加工的业务文本。
        steps = steps_payload(flow)
        manual_rules = ""
        for nd in (flow.get("graph") or {}).get("nodes") or []:
            if isinstance(nd, dict) and nd.get("manual_rules"):
                manual_rules = str(nd["manual_rules"]).strip()
                break
        if not manual_rules:
            manual_rules = str((flow.get("graph") or {}).get("manual_rules") or "").strip()

        # 大脑节点与旁白键来自节点插件注册表（编排壳不认识任何节点名）。
        # 函数体内 import：插件注册表参与模块环（skill_node_plugins ↔ 本模块）——延后到调用时解析。
        from app.services.skill_node_plugins import (
            first_delivery_gap, first_stuck_gap, narration_key_of, plugin_for)
        self.plugin_for = plugin_for
        self.first_delivery_gap = first_delivery_gap
        self.first_stuck_gap = first_stuck_gap
        self.narration_key_of = narration_key_of

        self.flow_configs = flow_configs
        self.engine = engine
        self.steps = steps
        self.manual_rules = manual_rules
        # 大脑步 = steps_payload 全量（无工具节点已被剔除）：凡挂了工具的节点都由同一颗
        # 大脑按节点 prompt 执行一轮——新节点绑工具即获得大脑回合，无需注册插件或改引擎。
        # （input/extract/compose/output 无工具，天然不进； compose/output 是引擎确定性尾段。）
        self._brain_steps = list(steps)

    async def _capturing_sink(self, payload):
        """流式旁白捕获：既攒本次回合的旁白，也原样转发给上层事件槽。"""
        sub = (payload or {}).get("sub") or {}
        if sub.get("kind") == "chunk" and sub.get("delta"):
            self.narration.append(sub["delta"])
            self.node_narration.setdefault(self._cur_step.get("key") or "_", []).append(sub["delta"])
        if self.event_sink:
            await self.event_sink(payload)

    def _restore_ext(self) -> None:
        """回合结束把冻结文档视图换回原始 dict（落盘与下游都只认它）。"""
        raw = self.engine.get("_ext_raw")
        if isinstance(raw, dict):
            self.engine["ext"] = raw
            self.engine.pop("_ext_raw", None)
        cur = TOOL_CTX.get()
        if isinstance(cur, dict) and "ext" in cur:
            cur["ext"] = self.engine.get("ext")

    def _finalize_engine(self) -> None:
        engine = self.engine
        engine["agent_narration"] = "".join(self.narration).strip()
        for k, v in self.node_narration.items():
            engine[self.narration_key_of(k) or k] = "".join(v).strip()
        engine["steps_done_list"] = sorted(engine["steps_done"])

    def _ask_gap(self, a: dict) -> dict:
        """大脑升格的提问 → 缺口卡（选项补全与信号解释全走同一套，编排壳不认识节点名）。"""
        row = str(a.get("row") or "").strip()
        _row_cat = ""
        if row:
            # 行卡按行身份绑行（P3-3）：类目由身份解析，不再从 row 文本里切竖线
            from app.services.part_selector import row_ref_meta
            from app.services.skill_node_state import KP_ROW_IDS, kp_state
            _row_cat = str((row_ref_meta(row, self.engine.get("kp_parts"),
                                        kp_state(self.engine).get(KP_ROW_IDS))
                            or {}).get("category") or "")
        # 行卡的**结构性出路**由该节点插座补（如「库内无料→保持原需求」）：
        # 主循环不认识任何业务语义，补出来的选项与大脑给的走同一条信号解释。
        raw_opts = list(a.get("options") or [])
        try:
            raw_opts += [o for o in self.plugin_for(self._cur_step.get("key") or "")
                         .extra_ask_options(self.engine, a, row) if isinstance(o, dict)]
        except Exception:
            logger.exception("节点补全行卡选项失败 row=%s", row)
        opts = []
        for o in raw_opts:
            if not isinstance(o, dict):
                continue
            label = str(o.get("label") or "").strip()
            if not label:
                continue
            opt_slot = str(o.get("slot") or "").strip()
            opt_val = str(o.get("value") or "").strip()
            opt = {"label": label, "value": opt_val or label, "desc": str(o.get("description") or ""),
                   "slot": opt_slot or str(a.get("slot") or "") or "brain_ask", "group": "AI 推荐"}
            if o.get("recommended"):
                opt["recommended"] = True
            # 词典卡影子校验标注透传（tool_ask_user 标的「规则推荐/与规则不符」徽标数据）
            if o.get("rule_match"):
                opt["rule_match"] = True
            if isinstance(o.get("rule_conflict"), dict):
                opt["rule_conflict"] = o["rule_conflict"]
            # 数量元数据透传（前端 stepper 边界，纯展示参数非 signal）：大脑给的数量
            # 原样过，没给的由节点插座在 enrich_ask_gap 按行申报量+机型边界补
            for k in ("qty", "qty_max", "unit_gb"):
                v = o.get(k)
                if isinstance(v, int) and v > 0:
                    opt[k] = v
            # 点击信号统一解释（行卡三结局 / 字段确认），见 skill_plan_runtime.ask_option_signal
            from app.services.skill_plan_runtime import ask_option_signal
            sig = ask_option_signal(row, o, str(a.get("slot") or ""), category=_row_cat)
            if sig:
                opt["signal"] = sig
            opts.append(opt)
        gap = {"slot": str(a.get("slot") or "brain_ask"), "reason_code": "brain_ask",
               "question": str(a.get("question") or "").strip(), "options": opts}
        # 节点专属装饰（行级选件卡等）由该节点插件提供——编排壳不认识节点名
        return self.plugin_for(self._cur_step.get("key") or "").enrich_ask_gap(self.engine, gap, a)

    def _system_gap(self, node_key: str = "") -> Optional[dict]:
        """推进卡住时的**结构化**出路卡：由该节点插件提供（数据驱动，非话术）。

        编排壳不认识任何节点——哪个节点会弹什么卡是插头属性。
        """
        k = str(node_key or "").strip()
        return self.plugin_for(k).delivery_gap(self.engine) if k else self.first_delivery_gap(self.engine)

    async def _emit_pipeline_phase(self, kind: str, **extra) -> None:
        """编排相位广播（waiting/done 等）：事件槽缺席时静默跳过，广播失败不掀翻回合。"""
        if self.event_sink is None:
            return
        try:
            payload = {"type": kind, "thread_id": self.thread_id}
            payload.update(extra)
            await self.event_sink(payload)
        except Exception:
            logger.exception("pipeline phase emit failed kind=%s", kind)

    # ── 暂停载荷对象（P4-1）：中断点只此一份对象 ──────────────────────
    @staticmethod
    def _pending_facts(cards: list) -> list:
        """待办事实：卡身份（槽位/原因码/选项数），不复制卡上的话术。"""
        out = []
        for c in (cards or []):
            if isinstance(c, dict):
                out.append({"slot": str(c.get("slot") or ""),
                            "reason_code": str(c.get("reason_code") or ""),
                            "options": len(c.get("options") or [])})
        return out

    def _pause_payload(self, kind: str, *, step: str = "", reason_code: str = "",
                       pending: Optional[list] = None, resumable: bool = True) -> dict:
        """暂停载荷：把「为什么停、停在哪、恢复要什么」收成一份结构化事实。

        下游（办公室事件 / 恢复入口 / UI）只读这一份对象，不再从 reasoning_state +
        治理队列 + 广播里各拼一半。载荷里只有事实与原因码，没有任何话术。
        """
        from app.services.skill_plan_runtime import pause_payload
        engine = self.engine
        step_key = str(step or engine.get("current_step")
                       or self._cur_step.get("key") or "")
        label = str(self._cur_step.get("label") or "") or str(
            (engine.get("node_labels") or {}).get(step_key) or step_key)
        return pause_payload(kind=kind, step=step_key, label=label,
                             reason_code=reason_code, pending=pending,
                             resumable=resumable, steps_done=engine.get("steps_done") or [])

    async def _emit_pause(self, kind: str, *, step: str = "", reason_code: str = "",
                          pending: Optional[list] = None, resumable: bool = True,
                          event: str = "pipeline_waiting", **legacy) -> dict:
        """置暂停载荷（engine.engine_pause，随回合终态回存 mem）+ 广播（旧字段照发）。"""
        pause = self._pause_payload(kind, step=step, reason_code=reason_code,
                                    pending=pending, resumable=resumable)
        self.engine["engine_pause"] = pause
        await self._emit_pipeline_phase(event, pause=pause, **legacy)
        return pause

    async def _emit_pipeline_start(self) -> None:
        """试运行可视化：预置步骤骨架 + input 首步收口（2026-09-08 回归恢复）。"""
        if self.event_sink is None:
            return
        try:
            from app.services.skill_plan_runtime import skill_steps_view, _trace
            # 顺序与执行序同源：传 flow → 画布 graph 拓扑序（无 graph 老流回退 PHASE_TABLE）
            steps_meta = skill_steps_view(self.flow_configs, flow=self.flow)
            flow_title = str((self.flow or {}).get("name") or (self.flow or {}).get("title") or "配置任务")
            await self.event_sink({"type": "pipeline_start", "title": flow_title, "steps": steps_meta})
            input_step = next((s for s in steps_meta if s.get("step") == "input"), None)
            if input_step:
                lab = str(input_step.get("label") or "需求接收")
                await self.event_sink(_trace("input", lab, "running"))
                # input 无产物插槽，摘要直接给事实（需求原文字数）——
                # 留空会落进 done_summary 的「本节点未注册产物」裸键名文案
                _in_summary = f"需求原文 {len(str(self.full_text or ''))} 字"
                _in_payload = _node_done_payload(self.engine, "input", lab, _in_summary)
                _in_payload["input"] = self.full_text
                _in_payload["duration_ms"] = 0
                await self.event_sink(_in_payload)
                # 跨回合恢复进度：pipeline_start 会把前端步骤重置为 pending，
                # 之前回合已完成的步骤（steps_done）在此重新广播 done，避免进度倒退回第一步。
                done_steps = set(self.engine.get("steps_done") or [])
                for s in steps_meta:
                    _k = str(s.get("step") or "")
                    if _k not in done_steps:
                        continue
                    _lab = str(s.get("label") or _k)
                    # 摘要留空 → 由该节点产物生成（恢复进度时也不虚报）
                    await self.event_sink(_node_done_payload(self.engine, _k, _lab, ""))
        except Exception:
            logger.exception("pipeline_start emit failed thread=%s", self.thread_id)

    def _knowledge_for(self, step_key: str) -> str:
        """节点绑定的需求理解知识块（requirement_knowledge 渲染，字节稳定固定段）。
        回合内按节点缓存；读失败降级空串——不带知识继续，绝不阻塞回合。"""
        cache = getattr(self, "_knowledge_cache", None)
        if cache is None:
            cache = self._knowledge_cache = {}
        if step_key not in cache:
            try:
                from app.services.requirement_knowledge import knowledge_for_node
                cache[step_key] = knowledge_for_node(step_key)
            except Exception:
                logger.exception("知识块注入失败（降级：不带知识继续）step=%s", step_key)
                cache[step_key] = ""
        return cache[step_key]

    def _build_step_call(self, step_key: str, node_cfg: dict, b_res: dict) -> tuple:
        """本步一次大脑调用的全部入参：system（人设/任务规则/当前步骤）+ 上下文块 + 循环 kwargs。"""
        begin_note = ""
        b_hint = str(b_res.get("hint") or "").strip()
        if b_hint:
            begin_note = f"\n\n【步骤准备】{b_hint}。"
        tools = list(dict.fromkeys(effective_node_tools(step_key, node_cfg)))
        step_scope = json.dumps({"step": step_key,
                                 "label": self._cur_step.get("label") or step_key,
                                 "order": self._cur_step.get("order")}, ensure_ascii=False)
        sys_prompt = "\n\n".join([p for p in (
            self.persona,
            manual_rules_block(self.manual_rules),
            self._knowledge_for(step_key),
            "当前步骤（steps 清单里的这一条）：\n" + step_scope + begin_note,
            "steps 清单（原样来自节点抽屉）：\n"
            + json.dumps(self.steps, ensure_ascii=False),
        ) if p])
        done = sorted(self.engine["steps_done"])
        steps_line = "已完成步骤：" + "、".join(done) if done else ""
        # 节点输入数据视图（引擎事实摆上桌，零节点分支）：引擎把什么摆上桌由预处理决定，
        # 摆了什么就注入什么——新增节点无需改这里。
        _rows_ctx = [r for r in (TOOL_CTX.get().get("kp_rows_ctx") or []) if isinstance(r, dict)]
        _rows_all = [r for r in (TOOL_CTX.get().get("kp_rows_all") or []) if isinstance(r, dict)]
        _slots = _slots_view(self.ext)
        if _rows_ctx or _rows_all:
            # 行清单已完整下发 → 登记表视图里的行描述不再重复注入（同一事实只说一次）
            _slots.pop("kp_rows", None)
            _slots.pop("kp_mode", None)
        context_block = "\n\n".join([p for p in (
            "当前线索登记表：\n" + json.dumps(_slots, ensure_ascii=False),
            "近期回合工作记录（你已做过的检索/提交/问询，勿重复劳动）：\n"
            + "\n".join(str(n) for n in (self.mem.get("brain_notes") or [])[-2:]),
            steps_line,
        ) if p])
        if _rows_ctx or _rows_all:
            # 配件行清单（全量，含已了结行）：事实数据原样摆桌；行引用协议与拒收规则
            # 都住在工具契约/工具层，这里不写劝告句，也不点名任何工具。
            context_block += ("\n\n本节点配件行清单（全量，含已了结行）：\n"
                              + json.dumps(_rows_all or _rows_ctx, ensure_ascii=False))
            # 目标层候选类目（抽屉勾选）：事实数据原样摆桌，是否为必配由行清单的 specified 表达。
            _required_cats = [str(c) for c in (TOOL_CTX.get().get("kp_required_cats") or []) if str(c).strip()]
            if _required_cats:
                context_block += ("\n\n本节点目标表候选类目（抽屉勾选）：\n"
                                  + json.dumps(_required_cats, ensure_ascii=False))
            # 已锁定机型扩展能力（目录事实摆桌）：推荐数量时的物理上限——GPU 位/内存槽/
            # 盘位/CPU 路。大脑据此把「装多少」随型号一起推荐，而不是只报型号。
            _caps = TOOL_CTX.get().get("kp_baseline_caps")
            if isinstance(_caps, dict) and _caps:
                context_block += ("\n\n已锁定机型扩展能力（推荐配件数量别超物理上限）：\n"
                                  + json.dumps(_caps, ensure_ascii=False))
        # 跨回合检索战果（本步此前回合/尝试已拿到的工具结论）：续跑直接复用，不再从零重查。
        _sf_text = str(((self.mem.get("step_findings") or {}).get(step_key) or "")).strip()
        if _sf_text:
            context_block += ("\n\n本步此前已完成的检索/工具结果（结论直接复用，勿重复查询）：\n"
                              + _sf_text)

        user_msg = ("【客户消息】\n" + (self.full_text or "（无）"))
        # document 产物节点：历史里的旧报告是复读毒源（锚定效应，且统计数字已过期必须重查）。
        # 生成新报告的上下文里它们只有害没有用——组上下文时确定性剔除（「数据范围：」是
        # 契约规定的报告首行指纹）。这是该步插座属性驱动的输入卫生，非流类型特判；
        # 出口终检只作保险丝，不承担清洁上下文的责任。
        history = self.history or []
        _tgt = node_cfg.get("target")
        _arts = _tgt.get("artifacts") if isinstance(_tgt, dict) else None
        if any(isinstance(a, dict) and str(a.get("kind") or "") == "document" for a in (_arts or [])):
            history = [m for m in history
                       if not (isinstance(m, dict) and str(m.get("role") or "") == "assistant"
                               and "数据范围：" in str(m.get("content") or ""))]
        loop_kwargs = dict(
            config={"enabled_tools": tools},
            system_prompt=sys_prompt, allowed_tool_ids=tools,
            history=history, model=self.model, event_sink=self._capturing_sink,
            tool_guard=self.tool_guard, max_iterations=8,
            llm_timeout=120.0, llm_reasoning_effort=self.reasoning_effort,
            llm_max_tokens=self.max_tokens if isinstance(self.max_tokens, int) and self.max_tokens > 0 else None,
            llm_thinking_budget=12000,
            llm_temperature=self.temperature if isinstance(self.temperature, (int, float)) else 0.0,
            context_block=context_block,
        )
        return user_msg, loop_kwargs

    async def _settle(self, result: dict, step_key: str) -> dict:
        """一轮大脑结束后的收口（与节点无关）：产物接线 → 提问卡/缺口卡 → 步骤校验。

        返回 {"action": "done"|"retry"|"wait"}；wait = 引擎已置暂停态，调用方直接交回。
        """
        engine = self.engine
        # 大脑本轮的工具结果接进引擎产物（哪个节点接什么是插头属性，主循环不认识节点）
        try:
            self.plugin_for(step_key).wire_result(engine, result, step_key)
        except Exception:
            logger.exception("节点产物接线失败 step=%s", step_key)
        # 通用答复快照：最后一个非空大脑回合的结论，最后写入者胜。
        # data_answer 型流（趋势分析等）经 payload_map 的 ctx.agent_result.answer 取值；
        # 需求分析流不读此键，行为不变。
        if str(result.get("answer") or "").strip():
            engine["agent_result"] = {"answer": str(result["answer"]),
                                      "tool_calls_log": result.get("tool_calls_log") or []}

        if not self._fill_emitted:
            # 节点回合内的实时产物广播由产物注册表声明（skill_node_artifacts）：
            # 哪个节点会边想边亮产物是它的插头属性，不是主循环的知识。
            try:
                from app.services.skill_node_artifacts import emit_live_artifact
                self._fill_emitted = bool(await emit_live_artifact(
                    step_key, engine, self.event_sink,
                    self._cur_step.get("label") or step_key, self._cur_step_started, self.full_text))
            except Exception:
                logger.exception("live artifact emit failed step=%s", step_key)

        def _note() -> None:
            engine["brain_notes"] = list(engine.get("brain_notes") or [])[-3:]
            if result.get("tool_calls_log"):
                engine["brain_notes"] = (engine["brain_notes"]
                                         + [_brain_note_summary(step_key, result)])[-3:]

        async def _pause(gaps: list, asks: list) -> dict:
            self._finalize_engine()
            _note()
            engine["engine_result"] = "gaps"
            engine["awaiting_input"] = True
            engine["engine_gaps"] = gaps[:1]
            engine["kp_asks"] = asks
            _g0 = gaps[0] if gaps and isinstance(gaps[0], dict) else {}
            await self._emit_pause(
                "brain_ask" if asks else "delivery_gap", step=step_key,
                reason_code=str(_g0.get("reason_code") or ""),
                pending=self._pending_facts(engine["engine_gaps"]),
                gaps=engine.get("engine_gaps") or [])
            return {"action": "wait"}

        asks = [a for a in (TOOL_CTX.get().get("brain_asks") or [])
                if isinstance(a, dict) and a.get("question")]
        if asks:
            return await _pause([self._ask_gap(a) for a in asks[:1]], asks)

        # 目录字段由 AI 自己判值/提问（唯一大脑），引擎不再硬发目录缺口卡；
        # 仅保留机型候选未锁定 → 结构化候选卡（数据驱动，非话术）。
        _mg = self._system_gap(step_key)
        if _mg is not None:
            return await _pause([_mg], [])

        from app.services.skill_plan_runtime import validate_step_end
        try:
            vres = await validate_step_end(engine, step_key)
        except Exception:
            logger.exception("end_step 兜底校验失败 step=%s", step_key)
            vres = {}
        if vres.get("ok"):
            engine.setdefault("steps_done", set()).add(step_key)
            # 上游产物落定即冻结：属主节点这一步过了校验，之后谁都不许再改它。
            mark_doc_frozen(engine, step_key, engine.get("ext"))
            if self.event_sink is not None:
                try:
                    # 完成摘要由产物生成（skill_node_artifacts.done_summary）：
                    # 主循环不为任何节点准备文案，也就不可能再虚报完成内容。
                    await _emit_step_trace({"engine": engine, "event_sink": self.event_sink,
                                            "thread_id": self.thread_id},
                                           str(step_key), "done", "", vres)
                except Exception:
                    logger.exception("fallback step done trace emit failed step=%s", step_key)
            return {"action": "done"}
        # 引擎校验失败：回喂 hint 逼大脑补做（调工具或 ask_user），不标 done、不把机制文案抛给客户。
        _hint = str(vres.get("hint") or "本步未完成")
        self._stuck["hint"] = _hint
        return {"action": "retry",
                "feedback": json.dumps({"engine_validate": _hint},
                                       ensure_ascii=False)[:500]}

    def _keep_step_findings(self, step_key: str, action: str, text: str) -> None:
        """检索战果跨回合落 mem：步骤落定即清（战果已沉淀进产物表），未落定则带着续跑。

        与登记表同一哲学（交接靠表）：检索结论不该随失败尝试/回合边界蒸发。
        任何失败只记日志，绝不影响主流程。
        """
        try:
            sf = self.mem.get("step_findings")
            if not isinstance(sf, dict):
                sf = {}
            if action == "done":
                sf.pop(step_key, None)
            elif text:
                sf[step_key] = text
            # 防堆积：只留最近两个未落定步骤的战果
            stale = [k for k in sf if k != step_key][:-1]
            for k in stale:
                sf.pop(k, None)
            self.mem["step_findings"] = sf
        except Exception:
            logger.exception("step_findings 维护失败 step=%s", step_key)

    @staticmethod
    def _brain_dead(result) -> bool:
        """本步大脑是否「整轮零产出」：既没有正文，也没有任何成功的工具调用。

        纯事实判定（不看节点、不看话术）：零产出 = 这一轮什么都没落地，不可能有产物可收口。
        """
        if not isinstance(result, dict):
            return True
        if str(result.get("answer") or "").strip():
            return False
        for c in (result.get("tool_calls_log") or []):
            res = (c or {}).get("result")
            if isinstance(res, dict) and res.get("ok"):
                return False
            if isinstance(res, str) and res.strip():
                return False
        return True

    async def _abort_step(self, step_key: str, reason_code: str) -> str:
        """本步大脑整轮零产出（超时/空产出重试耗尽/回合异常）：如实置失败终态交回。

        不静默留 last_step（客户会对着一个永远转圈的看板干等），也不弹零选项死卡
        （那是把机制 hint 漏成客户话术）。失败只带结构化事实，面向客户的那句话由下游
        按事实合成——编排壳里不写任何话术模板。
        """
        self._finalize_engine()
        engine = self.engine
        engine["engine_result"] = "failed"
        engine["awaiting_input"] = False
        engine["engine_failure"] = {"step": step_key, "reason_code": str(reason_code or "brain_empty"),
                                    "label": str(self._cur_step.get("label") or step_key)}
        logger.error("大脑本步零产出，置失败终态 thread=%s step=%s reason=%s",
                     self.thread_id, step_key, reason_code)
        await self._emit_pause("failure", step=step_key,
                               reason_code=engine["engine_failure"]["reason_code"],
                               event="pipeline_paused", failure=engine["engine_failure"])
        return "failed"

    async def _run_one_step(self, step_info: dict) -> str:
        """推进一个大脑节点步：自动 begin → 大脑回合（含回喂重试）→ 收口 → 闸门裁决。

        返回 "advance"（本步落定，推进下一步）/ "pause"（本步没落定且重试耗尽 → 如实暂停）/
        "wait"（大脑已升格提问，引擎置暂停态）/ "deliver"（所有大脑节点已落定 → 可交付）。
        """
        engine = self.engine
        step_key = str(step_info.get("step") or "")
        self._stuck["hint"] = ""
        self._cur_step = {"key": step_key, "label": str(step_info.get("label") or step_key)}
        self._cur_step_started = time.perf_counter()
        if self.event_sink is not None:
            try:
                from app.services.skill_plan_runtime import _trace
                lab = self._cur_step.get("label") or step_key
                await self.event_sink(_trace(step_key, lab, "running"))
            except Exception:
                logger.exception("step running trace emit failed step=%s", step_key)
        node_cfg = self.flow_configs.get(step_key) if isinstance(self.flow_configs.get(step_key), dict) else {}
        # 配置漂移可见化（方案四）：机制工具缺失的保底补回已在 effective_node_tools 发生，
        # 这里把「DB 丢了什么」升格为 node_trace + contract_warnings——试运行面板看得见，
        # 不再只进日志。每步每回合只报一次，防多轮刷屏。
        try:
            from app.services.skill_plan_runtime import node_tool_drift
            _drift = node_tool_drift(step_key, node_cfg)
        except Exception:
            logger.exception("机制工具漂移检测失败 step=%s", step_key)
            _drift = []
        if _drift and step_key not in self._drift_reported:
            self._drift_reported.add(step_key)
            _warn = {"step": step_key, "reason_code": "tool_drift",
                     "message": f"配置漂移：机制工具 {'、'.join(_drift)} 已保底补回"}
            engine.setdefault("contract_warnings", []).append(_warn)
            if self.event_sink is not None:
                try:
                    from app.services.skill_plan_runtime import _trace
                    await self.event_sink(_trace(step_key, self._cur_step.get("label") or step_key,
                                                 "running", summary=_warn["message"]))
                except Exception:
                    logger.exception("drift trace emit failed step=%s", step_key)
        # 引擎自动 begin：确定性预处理（候选池/行就绪）+ 上下文桥接，模型无需（也不允许）调 begin。
        b_res = await _engine_begin_step({"step": step_key})
        user_msg, loop_kwargs = self._build_step_call(step_key, node_cfg, b_res)

        self._fill_emitted = False
        _final_result: dict = {}
        _act = "retry"
        _findings: dict = {}
        try:
            _final_result, _act = await run_brain_attempts(
                user_msg, loop_kwargs=loop_kwargs,
                settle=lambda r: self._settle(r, step_key),
                emit_status=lambda _t: _emit_brain_status(self._capturing_sink, _t),
                findings_out=_findings)
            self._restore_ext()
            # 检索战果落 mem（步骤落定即清、未落定带着续跑），必须在 wait 早退之前
            self._keep_step_findings(step_key, _act, _findings.get("text") or "")
            if _act == "wait":
                return "wait"
        except Exception:
            logger.exception("skill 大脑回合失败 thread=%s step=%s", self.thread_id, step_key)
            _final_result = {}
            self._restore_ext()

        # 节点契约护栏（下游永不回填上游）：属主落定后的登记表被任何下游节点改写 → 判红可见。
        _viol = doc_freeze_violation(engine, step_key, engine.get("ext"))
        if _viol:
            logger.error("节点契约越界 thread=%s step=%s %s", self.thread_id, step_key, _viol)
            engine.setdefault("contract_warnings", []).append(_viol)

        if self._brain_dead(_final_result):
            # 整轮零产出（超时/空产出/回合异常）：这一轮没有可收口的对话，但**产物未必没落地**
            # ——超时前成功调用的工具已经写进引擎了。先按产物收口一次，仍不成立才如实报失败：
            # 既不静默留 last_step，也不弹零选项死卡（那等于把机制 hint 漏成客户话术）。
            _dead_verdict: dict = {}
            try:
                _dead_verdict = await self._settle(_final_result, step_key) or {}
            except Exception:
                logger.exception("零产出收口失败 thread=%s step=%s", self.thread_id, step_key)
            _dead_act = str(_dead_verdict.get("action") or "")
            if _dead_act == "done":
                return "advance"
            if _dead_act == "wait":
                return "wait"
            return await self._abort_step(
                step_key, "llm_timeout" if _act == "timeout" else "brain_no_output")

        pending = [s for s in self._brain_steps if str(s.get("step") or "") not in engine["steps_done"]]
        _verdict = step_gate_verdict(pending, step_key)
        if _verdict == "advance":
            return "advance"
        if _verdict == "pause":
            # 本步既没写出产物、也没升格提问（回喂重试已耗尽）→ 它的表没落地。
            # 下游节点的输入契约未满足，**绝不允许落穿到组装/交付**：否则就是把半成品
            # 当方案推给客户（历史事故：配件表 0 行也交付了「BOM 方案草稿」并报完成）。
            # 如实置暂停态交回客户；机制提示由同一颗大脑重述成自然问句（零选项不落卡）。
            self._finalize_engine()
            engine["engine_result"] = "gaps"
            engine["awaiting_input"] = True
            # 卡住时优先问**节点自己的结构化出路卡**（插座兜底：配件行拍板卡等）——
            # 有卡才有活儿给客户干，机制文案也就没有机会被转述成客户话术。
            # 节点确实没有可给的出路时，才退回「机制提示交同一颗大脑重述」的零选项暂停。
            _sg = self.first_stuck_gap(engine)
            engine["engine_gaps"] = [_sg] if isinstance(_sg, dict) and _sg else \
                [{"slot": "brain_ask", "reason_code": "brain_ask",
                  "question": self._stuck["hint"] or "本步尚未完成",
                  "options": []}]
            _g0 = engine["engine_gaps"][0] if isinstance(engine["engine_gaps"][0], dict) else {}
            await self._emit_pause("stuck", step=step_key,
                                   reason_code=str(_g0.get("reason_code") or "stuck"),
                                   pending=self._pending_facts(engine["engine_gaps"]),
                                   gaps=engine.get("engine_gaps") or [])
            return "pause"
        return "deliver"

    async def _deliver(self) -> dict:
        """全部 brain 节点推进完毕 → 终检 + 组装 + 交付（不合格则回落成暂停缺口卡）。"""
        from app.services.skill_plan_runtime import delivery_gate, run_compose
        engine = self.engine
        self._finalize_engine()
        engine["brain_notes"] = list(engine.get("brain_notes") or [])[-3:]
        out_cfg = self.flow_configs.get("output") if isinstance(self.flow_configs.get("output"), dict) else {}
        output_kind = str(out_cfg.get("output_kind") or "")
        # 终检按流的 output_kind 分派：data_answer 只看结论是否产出，其余走既有 final_gate
        gate = delivery_gate(engine, output_kind)
        # data_answer 不组装 BOM plans，过闸即交付
        needs_finalize = output_kind == "data_answer"
        if gate.get("ok") and not engine.get("plans") and not needs_finalize:
            composed = await run_compose(engine, self.event_sink)
            if composed.get("ok"):
                engine["current_step"] = "compose"
                engine.setdefault("steps_done", set()).add("compose")
                engine["steps_done_list"] = sorted(engine["steps_done"])
                if self.event_sink is not None:
                    try:
                        await _emit_step_trace({"engine": engine, "event_sink": self.event_sink,
                                                "thread_id": self.thread_id},
                                               "compose", "done", "")
                    except Exception:
                        logger.exception("compose trace emit failed")
                needs_finalize = True
            else:
                gate = composed
        if gate.get("ok") and needs_finalize:
            from app.services.skill_node_runtime import finalize_output
            try:
                # finalize_output 内部自写 ctx["output_kind"/"output_payload"]（真 payload）；
                # 其返回值是 handoff 信封（payload 嵌在 .payload 里），绝不能再拿回来覆盖 ctx
                await finalize_output(engine, out_cfg, self.event_sink)
            except Exception:
                logger.exception("finalize_output 失败 thread=%s", self.thread_id)
            if self.event_sink is not None:
                try:
                    from app.services.skill_plan_runtime import skill_steps_view
                    out_lab = next((s.get("label") for s in skill_steps_view(self.flow_configs,
                                                                            flow=self.flow)
                                    if s.get("step") == "output"), "output")
                    # 交付节点同样按插头打包产物（bom_scheme）：画布上「输出」节点下也要有输出物
                    _out_payload = _node_done_payload(engine, "output", out_lab, "")
                    _out_payload["thread_id"] = self.thread_id
                    await self.event_sink(_out_payload)
                except Exception:
                    logger.exception("output trace emit failed")
        if not gate.get("ok"):
            # 终检打回且指定 reopen（如数据范围不符）：把该节点从已完成里摘出，
            # 暂停后下一回合大脑重跑该步——否则 steps_done 已含 agent，续跑无步可跑，
            # gap 会永远循环（同「answer 空时重开 agent」未根治的近亲，这里先修 data_answer 版）。
            _reopen = str(gate.get("reopen") or "").strip()
            if _reopen and isinstance(engine.get("steps_done"), set):
                engine["steps_done"].discard(_reopen)
                engine["steps_done_list"] = sorted(engine["steps_done"])
            # reopen 打回时暂停问题必须是终检原因本身（窗口不符），不被系统缺口抢文本
            _mg = None if _reopen else (self._system_gap() or self.first_stuck_gap(engine))
            if _mg is not None:
                engine["engine_result"] = "gaps"
                engine["awaiting_input"] = True
                engine["engine_gaps"] = [_mg]
                await self._emit_pause("delivery_gap",
                                       step=str(engine.get("current_step") or ""),
                                       reason_code=str(_mg.get("reason_code") or ""),
                                       pending=self._pending_facts(engine["engine_gaps"]),
                                       gaps=engine.get("engine_gaps") or [])
                return engine
            engine["engine_result"] = "gaps"
            engine["awaiting_input"] = True
            engine["engine_gaps"] = [{"slot": "brain_ask", "reason_code": "brain_ask",
                                      "question": str(gate.get("hint") or "任务未完成"),
                                      "options": []}]
            await self._emit_pause("final_gate",
                                   step=str(engine.get("current_step") or ""),
                                   reason_code=str(gate.get("reason_code") or "final_gate"),
                                   pending=self._pending_facts(engine["engine_gaps"]),
                                   gaps=engine.get("engine_gaps") or [])
            return engine
        engine["engine_result"] = "done"
        engine["awaiting_input"] = False
        await self._emit_pipeline_phase("pipeline_done")
        return engine

    async def run(self) -> dict:
        """回合主干：装配 → 预置画布 → 逐步推进（每步自动 begin/校验/闸门）→ 终检交付。"""
        self._prepare()
        await self._emit_pipeline_start()
        engine = self.engine
        pending = [s for s in self._brain_steps if str(s.get("step") or "") not in engine["steps_done"]]
        while pending:
            _act = await self._run_one_step(pending[0])
            if _act in ("wait", "pause", "failed"):
                return engine
            if _act == "deliver":
                break
            pending = [s for s in self._brain_steps if str(s.get("step") or "") not in engine["steps_done"]]
        return await self._deliver()


async def run_skill_agent_turn(*, thread_id: str, role_key: str, persona: str,
                               full_text: str, history: Optional[list],
                               ext: dict, mem: dict, flow: dict, event_sink=None,
                               tool_guard=None, price_ok: bool = True,
                               opportunity_id: Optional[str] = None,
                               model: Optional[str] = None,
                               reasoning_effort: Optional[str] = None,
                               temperature=None, max_tokens=None,
                               save_mem=None, write_mode: Optional[str] = None) -> dict:
    """编排权移交后的回合执行器：大脑读说明书自己走步骤（2026-09-07 P2）。

    引擎残余只有四件确定性的事：每步自动 begin（预处理挂载）、每步自动 end（校验）、
    ask_user 卡片数据、终检+组装。模型不再调用 begin/end/submit/compose（控制原语从
    工具面撤下）。返回 engine_ctx，契约与旧 run_skill_plan_core
    兼容（engine_result/awaiting_input/engine_gaps/business_entity/kp_summary/
    narration/brain_notes）——下游渲染与落库链路原样复用。"""
    return await _SkillTurnRuntime(
        thread_id=thread_id, role_key=role_key, persona=persona, full_text=full_text,
        history=history, ext=ext, mem=mem, flow=flow, event_sink=event_sink,
        tool_guard=tool_guard, price_ok=price_ok, opportunity_id=opportunity_id,
        model=model, reasoning_effort=reasoning_effort, temperature=temperature,
        max_tokens=max_tokens, save_mem=save_mem, write_mode=write_mode).run()


def _merged_narration(result_ctx: dict) -> str:
    """回合旁白合流：登记 + 机型选定 + 配件选定旁白按发生顺序拼接（都经引擎产物回传）。"""
    parts = [str((result_ctx or {}).get(k) or "").strip()
             for k in ("fill_narration", "model_narration", "kp_narration")]
    return "\n\n".join(p for p in parts if p)
