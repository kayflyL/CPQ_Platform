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
    "issue_count", "retried", "error",
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
