# -*- coding: utf-8 -*-
"""技能流程记忆与状态视图：按「线程 + 角色」隔离的记忆读写、会话读写、登记表/配件行视图。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

import logging
import json
from app.repository.assistant_repo import AssistantRepository
from app.services.skill_node_state import KP_PICKS, KP_RECOMMEND, kp_state
from app.services.skill_tool_context import TOOL_CTX


logger = logging.getLogger(__name__)


MEMORY_KEY = "skill_chat"


def _mem_key(role_key: str) -> str:
    """技能流程记忆按「线程 + 角色」隔离：专家接手时是干净身份，不会接手别的角色没走完的流程。"""
    return f"{MEMORY_KEY}:{(role_key or 'assistant').strip() or 'assistant'}"


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


SKILL_SESSION_KEY = "skill_session"


def load_skill_session(thread_id: str, role_key: str = "assistant") -> dict:
    """读取技能会话状态，与 ext/last_card 同存一份 skill_chat 记忆。"""
    mem = _load_mem(thread_id, role_key)
    session = mem.get(SKILL_SESSION_KEY)
    return dict(session) if isinstance(session, dict) else {}


def save_skill_session(thread_id: str, role_key: str, session: dict) -> None:
    """写技能会话状态，保留同线程已有的 ext/last_card 等记忆。"""
    mem = _load_mem(thread_id, role_key)
    mem[SKILL_SESSION_KEY] = session if isinstance(session, dict) else {}
    _save_mem(thread_id, role_key, mem)


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


def _kp_node_state() -> dict:
    """kp_reason 节点私有状态（唯一权威 = engine.node_state.kp_reason）。

    节点隔离：本节点的选型/推荐/声明行/放弃类目一律放这里，不写共享 ext
    （ext 只保留上游「线索登记表」冻结文档）。
    """
    ctx = TOOL_CTX.get() or {}
    engine = ctx.get("engine") if isinstance(ctx.get("engine"), dict) else {}
    return kp_state(engine)


def _kp_status_rows() -> list:
    """配件选配工作文档的可读状态：每行的 row_id/类目/结局（已锁定/推荐待确认/已了结/待处理）。

    AI 只报 row_id，引擎解析行键；每次 search/select/ask 后回传这份状态，让 AI 看得到
    自己改了什么，不靠猜。已锁定行给出真实料号名，推荐待确认给出 AI 建议料（未落地）。
    """
    ctx = TOOL_CTX.get() or {}
    st = _kp_node_state()
    # 优先用节点下发的**全量**行清单（含已了结行，自带 status）：工具每次回传都能看见
    # 「哪几行已经处理完」，才不会把同一行换个措辞再问一遍（2026-09-11 P2）。
    rows_ctx = [r for r in (ctx.get("kp_rows_all") or ctx.get("kp_rows_ctx") or [])
                if isinstance(r, dict)]
    picks = st.get(KP_PICKS) if isinstance(st.get(KP_PICKS), dict) else {}
    recs = st.get(KP_RECOMMEND) if isinstance(st.get(KP_RECOMMEND), dict) else {}
    out = []
    from app.services.part_selector import pick_for_row
    for r in rows_ctx:
        rk = str(r.get("row_key") or "")
        # 工作记忆只回传紧凑状态（row_id/类目/结局），不再重复整段 description/qty——
        # 完整规格已在待选型行清单（context_block）里，每次 search/select 都重发会让上下文膨胀。
        row: dict = {"row_id": r.get("row_id"), "category": r.get("category")}
        if r.get("status"):
            # 全量行清单自带结局 → 原样透传（已锁定/已了结/推荐待确认/待处理）
            row["status"] = str(r.get("status") or "")
            if r.get("part"):
                row["part"] = str(r.get("part") or "")
            if r.get("qty") not in (None, ""):
                row["qty"] = r.get("qty")
            out.append(row)
            continue
        pk = pick_for_row(picks, str(r.get("category") or ""), str(r.get("description") or ""), row=r)
        if pk:
            items = pk if isinstance(pk, list) else [pk]
            items = [i for i in items if isinstance(i, dict)]
            names = [str(i.get("name") or "") for i in items]
            qtys = [i.get("qty") for i in items]
            row["status"] = "已锁定"
            row["part"] = "+".join(n for n in names if n) if names else "已锁定"
            _q = sum(int(q) for q in qtys if isinstance(q, (int, float)))
            if _q > 1:
                row["qty"] = _q
        elif pick_for_row(recs, str(r.get("category") or ""), str(r.get("description") or ""), row=r):
            rec = pick_for_row(recs, str(r.get("category") or ""), str(r.get("description") or ""), row=r)
            rec = rec if isinstance(rec, list) else [rec]
            rec = rec[0] if rec and isinstance(rec[0], dict) else {}
            row["status"] = "推荐待确认"
            row["part"] = str(rec.get("name") or "")
        else:
            row["status"] = "待处理"
        out.append(row)
    return out


def kp_required_categories(node_cfg: dict) -> list:
    """目标层字段策略：配件行级「必填」类目清单（kp_reason 专属）。

    来源=target.artifacts[0].fields 里 key 为 `kp_parts:<类目>` 且 ask=true 的行
    （抽屉字段清单：kp_reason 左栏=配件行字段，字段标签=必填）。必填=该行必须落在最终方案，
    不决定是否反问——反问由运行时判定（需求明确+库有料→锁定；明确但库无料/未写明→推荐并 ask_user）。
    全局开关（key='kp_parts' 的 ask）在 skill_plan_runtime 的 kp gate 消费（不进大脑）。
    """
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    from app.services.skill_target_contract import target_artifacts
    arts = target_artifacts(cfg)
    fields = ((arts[0] if arts else {}) or {}).get("fields") or []
    out = []
    for f in fields:
        if isinstance(f, dict) and (bool(f.get("ask")) or bool(f.get("must_ask"))):
            key = str(f.get("key") or "")
            if key.startswith("kp_parts:"):
                cat = key.split(":", 1)[1].strip()
                if cat:
                    out.append(cat)
    return out


def _brain_note_summary(node_key: str, result: dict) -> str:
    """把本回合工具轨迹压成一条工作记录（跨回合注入，治「每轮从登记表快照从零开始」）。

    通用渲染：记忆层不认识任何工具名——每条记录由 agent_tool_specs.trace_note 从
    调用实参/结果里抽事实。新增工具零改动即可被记录。
    """
    from app.services.agent_tool_specs import trace_note
    notes = [n for n in (trace_note(c) for c in ((result or {}).get("tool_calls_log") or [])) if n]
    payload: dict = {"step": str(node_key or ""), "tool_calls": notes}
    answer = str((result or {}).get("answer") or "").strip()
    if answer:
        payload["reply"] = answer[:80]
    return json.dumps(payload, ensure_ascii=False)[:600]