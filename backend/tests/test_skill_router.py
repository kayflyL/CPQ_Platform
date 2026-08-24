# -*- coding: utf-8 -*-
"""skill_router LLM Skill 路由单测。"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.services.skill_router import conversation_text, route_skill_llm


def _requirement_skill():
    return {
        "key": "requirement_analysis",
        "workflow_key": "requirement_analysis",
        "type": "workflow",
        "description": "用户需要配置服务器、理解硬件需求或生成 BOM/方案时调用。",
    }


def test_conversation_text_keeps_user_messages_only():
    text = conversation_text([
        {"role": "user", "content": "我要一台服务器"},
        {"role": "assistant", "content": "请补充用途"},
    ])
    assert "我要一台服务器" in text
    assert "请补充用途" not in text


def test_llm_route_selects_workflow_skill():
    with patch("app.services.skill_router.llm_client.chat_json", AsyncMock(return_value={"skill_key": "requirement_analysis", "reason": "服务器配置"})):
        routed = asyncio.run(route_skill_llm([_requirement_skill()], "我要一台Orion服务器", ""))
    assert routed is not None
    assert routed["source"] == "llm"
    assert routed["skill"]["key"] == "requirement_analysis"


def test_llm_route_none_stays_none():
    with patch("app.services.skill_router.llm_client.chat_json", AsyncMock(return_value={"skill_key": "", "reason": "不需要技能"})):
        routed = asyncio.run(route_skill_llm([_requirement_skill()], "你好", ""))
    assert routed is None


def test_llm_failure_returns_none_without_fallback():
    with patch("app.services.skill_router.llm_client.chat_json", AsyncMock(side_effect=Exception("boom"))):
        routed = asyncio.run(route_skill_llm([_requirement_skill()], "我要一台服务器", ""))
    assert routed is None
