"""Reasoning session state abstraction — 让需求分析 pipeline 既能绑商机（现状），
也能绑「方案助手」会话 / 未来企微会话（thread），而不改动执行器核心。

两个后端：
- kind='opportunity' → opportunities.opportunities.extra_fields（现状，零迁移）；
- kind='thread'     → opportunities.assistant_threads.reasoning_state（方案助手会话，
                      随会话持久化，重启不丢；WeChat 适配层将来也以 thread 为会话）。

说明：本模块刻意不依赖 requirement_intel_service（避免循环 import），
opportunity 后端用轻量直查实现；thread 后端复用 AssistantRepository 的列读写。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _thread_extra(thread_id: str) -> dict:
    """读 assistant_threads.reasoning_state（JSON 文本列）。失败返回 {}。"""
    try:
        from app.repository.assistant_repo import AssistantRepository
        repo = AssistantRepository()
        try:
            state = repo.get_reasoning_state(thread_id)
        finally:
            repo.close()
        if not state:
            return {}
        if isinstance(state, dict):
            return state
        try:
            parsed = json.loads(state)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    except Exception as e:
        logger.warning("读 thread reasoning_state 失败 thread=%s err=%s", thread_id, e)
        return {}


def _thread_update(thread_id: str, patch: dict) -> None:
    try:
        from app.repository.assistant_repo import AssistantRepository
        repo = AssistantRepository()
        try:
            repo.update_reasoning_state(thread_id, patch)
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 thread reasoning_state 失败 thread=%s err=%s", thread_id, e)


def _opportunity_extra(opportunity_id: str) -> dict:
    try:
        from app.models.opportunity import Opportunity
        from app.models.base import Opportunity_SessionLocal
        with Opportunity_SessionLocal() as session:
            opp = session.query(Opportunity).filter(
                Opportunity.opportunity_id == opportunity_id
            ).first()
            if not opp or not opp.extra_fields:
                return {}
            return json.loads(opp.extra_fields) if isinstance(opp.extra_fields, str) else (opp.extra_fields or {})
    except Exception as e:
        logger.warning("读商机 extra_fields 失败 opp=%s err=%s", opportunity_id, e)
        return {}


def _opportunity_update(opportunity_id: str, patch: dict) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, patch)
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写商机 extra_fields 失败 opp=%s err=%s", opportunity_id, e)


class ReasoningSession:
    """需求分析会话状态句柄。session_id 即房间/会话键；kind 决定状态存哪。"""

    def __init__(self, session_id: str, kind: str = "opportunity"):
        self.session_id = session_id
        self.kind = kind

    def get_extra(self) -> dict:
        if self.kind == "thread":
            return _thread_extra(self.session_id)
        return _opportunity_extra(self.session_id)

    def update_meta(self, patch: dict) -> None:
        if self.kind == "thread":
            _thread_update(self.session_id, patch)
        else:
            _opportunity_update(self.session_id, patch)
