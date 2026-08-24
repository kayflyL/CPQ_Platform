# -*- coding: utf-8 -*-
"""一次性迁移：清理旧输出节点展示配置，改为 output_kind 交接契约。

清理 keys：bom_output / recommendation / 顶层 review（如存在）。
review 节点只保留可配置的输出交接字段；其确定性校对参数回退后端默认值。
"""
from __future__ import annotations

import json
from datetime import datetime

from app.models.base import Rules_SessionLocal
from app.models.reasoning_flow import ReasoningFlow, ReasoningNodeConfig


LEGACY_KEYS = {"bom_output", "recommendation", "review"}
REVIEW_AUDIT_KEYS = {
    "enabled",
    "merge_llm_audit",
    "max_audit_issues_per_plan",
    "budget_over_ratio",
    "llm_doubt_status",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _output_defaults(skill_key: str | None, node_key: str) -> dict:
    if node_key == "review" or skill_key == "requirement_analysis":
        return {
            "output_kind": "plans",
            "target": "plan_draft",
            "payload_map": {
                "plans": "ctx.plans",
                "ext": "ctx.ext",
                "keywords": "ctx.ext.keywords",
                "series": "ctx.ext.series",
                "form": "ctx.ext.form",
                "kp_by_model": "ctx.kp_by_model",
            },
            "actions": [],
        }
    if skill_key == "trend_analysis":
        return {
            "output_kind": "data_answer",
            "target": "conversation_reply",
            "payload_map": {"answer": "ctx.agent_result.answer"},
            "actions": [],
        }
    return {
        "output_kind": "generic",
        "target": "artifact",
        "payload_map": {},
        "actions": [],
    }


def main() -> None:
    session = Rules_SessionLocal()
    changed = 0
    try:
        flows = {f.id: (f.skill_key or f.name) for f in session.query(ReasoningFlow).all()}
        rows = session.query(ReasoningNodeConfig).all()
        for row in rows:
            try:
                cfg = json.loads(row.config) if row.config else {}
            except Exception:
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}

            original = dict(cfg)
            for key in LEGACY_KEYS:
                cfg.pop(key, None)

            if row.node_key == "review":
                for key in REVIEW_AUDIT_KEYS:
                    cfg.pop(key, None)
                defaults = _output_defaults(flows.get(row.flow_id), "review")
                for key, value in defaults.items():
                    cfg.setdefault(key, value)
            elif row.node_key == "output":
                defaults = _output_defaults(flows.get(row.flow_id), "output")
                for key, value in defaults.items():
                    cfg.setdefault(key, value)

            if cfg != original:
                row.config = json.dumps(cfg, ensure_ascii=False)
                row.updated_at = _now()
                row.updated_by = "migration"
                changed += 1

        session.commit()
        print(f"updated {changed} node configs")
    finally:
        session.close()


if __name__ == "__main__":
    main()
