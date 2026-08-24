# -*- coding: utf-8 -*-
"""LLM trace 记录 + 指标汇总（P3）。

- record_llm_trace()：落一条 rules.llm_trace（任何失败只记日志，不影响主流程）；
- llm_metrics()：指标 = 生成时长 / 人工干预率 / LLM 采纳率 / 修订率（llm_feedback 样本）。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TRACE_FIELDS = {
    "node_type", "opportunity_id", "pipeline_id", "model", "status", "called",
    "merged", "duration_ms", "prompt_chars", "response_chars", "plans_checked",
    "issue_count", "retried", "error", "user_id", "role_key", "tool_name",
}


def record_llm_trace(**fields) -> None:
    """落一条 LLM 调用 trace。任何失败只记日志（绝不阻塞主流程）。"""
    try:
        from app.models.base import Rules_SessionLocal
        from app.models.llm_trace import LLMTrace
        data = {k: v for k, v in fields.items() if k in _TRACE_FIELDS and v is not None}
        if not data.get("node_type"):
            return
        session = Rules_SessionLocal()
        try:
            session.add(LLMTrace(**data))
            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.warning("写 llm_trace 失败: %s", e)


def llm_metrics(limit: int = 100) -> dict:
    """LLM 指标汇总（策略中心/诊断用）。

    - 调用：次数 / 平均耗时 / 成功率 / 平均检查方案数 / 平均问题方案数；
    - 反馈：llm_feedback 样本数 / 采纳率(accept) / 修订率(ignore)。
    """
    out = {
        "calls": 0, "avg_duration_ms": 0, "success_rate": 0,
        "avg_plans_checked": 0, "avg_issue_plans": 0,
        "feedback_samples": 0, "accept_rate": 0, "revise_rate": 0,
        "last_calls": [],
    }
    try:
        from sqlalchemy import func as sa_func
        from app.models.base import Rules_SessionLocal
        from app.models.llm_trace import LLMTrace
        from app.models.requirement_rule import RequirementSample
        session = Rules_SessionLocal()
        try:
            total = session.query(sa_func.count(LLMTrace.id)).scalar() or 0
            out["calls"] = total
            if total:
                avg_dur = session.query(sa_func.avg(LLMTrace.duration_ms)).scalar() or 0
                ok = session.query(sa_func.count(LLMTrace.id)).filter(LLMTrace.status == "ok").scalar() or 0
                avg_plans = session.query(sa_func.avg(LLMTrace.plans_checked)).scalar() or 0
                avg_issue = session.query(sa_func.avg(LLMTrace.issue_count)).scalar() or 0
                out["avg_duration_ms"] = round(float(avg_dur))
                out["success_rate"] = round(ok / total, 3)
                out["avg_plans_checked"] = round(float(avg_plans), 2)
                out["avg_issue_plans"] = round(float(avg_issue), 2)
            rows = session.query(LLMTrace).order_by(LLMTrace.id.desc()).limit(limit).all()
            out["last_calls"] = [
                {"id": r.id, "node_type": r.node_type, "status": r.status,
                 "duration_ms": r.duration_ms or 0, "merged": bool(r.merged),
                 "plans_checked": r.plans_checked or 0, "issue_count": r.issue_count or 0,
                 "created_at": str(r.created_at) if r.created_at else None}
                for r in rows
            ]
            # 反馈采纳率：llm_feedback 样本 expected_result.confirm 决策分布
            samples = session.query(RequirementSample).filter(
                RequirementSample.source == "llm_feedback").all()
            decisions = []
            for s in samples:
                try:
                    import json
                    exp = json.loads(s.expected_result) if s.expected_result else {}
                    decisions += [(d.get("decision")) for d in (exp.get("confirm") or []) if d.get("decision")]
                except Exception:
                    continue
            if decisions:
                acc = sum(1 for d in decisions if d == "accept")
                out["feedback_samples"] = len(samples)
                out["accept_rate"] = round(acc / len(decisions), 3)
                out["revise_rate"] = round(1 - acc / len(decisions), 3)
        finally:
            session.close()
    except Exception as e:
        logger.warning("llm_metrics 汇总失败: %s", e)
    return out


def assistant_metrics(limit: int = 100) -> dict:
    """方案助手 / AI 同事的 LLM 调用与工具调用审计指标。"""
    out = {
        "calls": 0,
        "tool_calls": 0,
        "avg_duration_ms": 0,
        "success_rate": 0,
        "by_node": [],
        "by_role": [],
        "by_tool": [],
        "last_calls": [],
    }
    try:
        from sqlalchemy import func as sa_func, or_
        from app.models.base import Rules_SessionLocal
        from app.models.llm_trace import LLMTrace
        session = Rules_SessionLocal()
        try:
            assistant_nodes = or_(
                LLMTrace.node_type.like("assistant_%"),
                LLMTrace.node_type.like("colleague_%"),
            )
            q = session.query(LLMTrace).filter(assistant_nodes)
            total = q.count() or 0
            out["calls"] = total
            if total:
                avg_dur = session.query(sa_func.avg(LLMTrace.duration_ms)).filter(
                    assistant_nodes).scalar() or 0
                ok = session.query(sa_func.count(LLMTrace.id)).filter(
                    assistant_nodes,
                    LLMTrace.status == "ok").scalar() or 0
                out["avg_duration_ms"] = round(float(avg_dur))
                out["success_rate"] = round(ok / total, 3)
                out["tool_calls"] = session.query(sa_func.count(LLMTrace.id)).filter(
                    LLMTrace.node_type.like("assistant_tool:%")).scalar() or 0
            grouped = session.query(LLMTrace.node_type, sa_func.count(LLMTrace.id)).filter(
                assistant_nodes).group_by(LLMTrace.node_type).all()
            out["by_node"] = [{"node_type": k, "count": v} for k, v in grouped]
            role_rows = session.query(LLMTrace.role_key, sa_func.count(LLMTrace.id)).filter(
                assistant_nodes).group_by(LLMTrace.role_key).all()
            out["by_role"] = [{"role_key": k or "", "count": v} for k, v in role_rows]
            tool_rows = session.query(LLMTrace.tool_name, sa_func.count(LLMTrace.id)).filter(
                assistant_nodes).group_by(LLMTrace.tool_name).all()
            out["by_tool"] = [{"tool_name": k or "", "count": v} for k, v in tool_rows]
            rows = session.query(LLMTrace).filter(assistant_nodes) \
                .order_by(LLMTrace.id.desc()).limit(limit).all()
            out["last_calls"] = [
                {"id": r.id, "node_type": r.node_type, "status": r.status,
                 "duration_ms": r.duration_ms or 0, "error": r.error or "",
                 "model": r.model or "", "thread_id": r.opportunity_id or "",
                 "user_id": r.user_id or "", "role_key": r.role_key or "",
                 "tool_name": r.tool_name or "",
                 "created_at": str(r.created_at) if r.created_at else None}
                for r in rows
            ]
        finally:
            session.close()
    except Exception as e:
        logger.warning("assistant_metrics 汇总失败: %s", e)
    return out
