# -*- coding: utf-8 -*-
"""v2 流式对话协议（标签交错）单测：mock stream_agent_chat。

核心不变量：推给用户的全部 chunk 拼接 == 返回的 answer（落库与流式严格一致）；
围栏内容永不外推；断流时已有正文按终答保留。
"""
import asyncio
import json

import pytest

import app.services.agent_react as ar
import app.services.llm_client as llm
from app.services.agent_react import _InterleavedParser


# ── 解析器单元 ──────────────────────────────────────────────────────────────

def test_parser_prose_and_fence():
    p = _InterleavedParser()
    out = p.feed("我查一下目录。\n```tool\n")
    assert out == "我查一下目录。\n"
    out = p.feed('{"name": "catalog_se')
    assert out == ""
    p.feed('arch", "args": {}}\n```')
    p.close()
    assert p.prose == "我查一下目录。\n"
    assert json.loads(p.fence_text)["name"] == "catalog_search"


def test_parser_fence_marker_split_across_deltas():
    """围栏标记被 chunk 边界劈成两半：挂起尾部，绝不把半个标记泄给用户。"""
    p = _InterleavedParser()
    out1 = p.feed("正文A```to")
    assert out1 == "正文A"          # "```to" 挂起，不放行
    out2 = p.feed("ol\n{}")
    assert out2 == ""               # 证明是围栏，进入 fence 态
    p.feed("\n```尾部")
    p.close()
    assert p.prose == "正文A"       # 围栏闭合后进入 locked：其后内容按设计丢弃
    assert json.loads(p.fence_text) == {}


def test_parser_locked_drops_content_after_first_fence():
    """一轮双工具块：第一个之后的围栏与杂文全部丢弃，不外推。"""
    p = _InterleavedParser()
    p.feed("说明```tool\n{\"name\": \"a\"}\n```")
    out = p.feed("被锁定的杂文```tool\n{\"name\": \"b\"}\n```")
    assert out == ""
    p.close()
    assert json.loads(p.fence_text)["name"] == "a"
    assert "被锁定" not in p.prose


def test_parser_unterminated_fence():
    """流在围栏中间结束：内容照常参与 JSON 解析。"""
    p = _InterleavedParser()
    p.feed("说明\n```tool\n{\"name\": \"x\", \"args\": {}}")
    p.close()
    assert json.loads(p.fence_text)["name"] == "x"


def test_parser_plain_code_fence_is_prose():
    """非 tool 围栏（如 ```json）按正文放行，不误吞。"""
    p = _InterleavedParser()
    out = p.feed("看这个 ```json\n{\"a\": 1}\n``` 完")
    assert out == "看这个 ```json\n{\"a\": 1}\n``` 完"
    p.close()
    assert p.fence_text == ""


# ── 循环集成（mock LLM 流 + 假工具注册表）──────────────────────────────────

class _FakeRegistry:
    def __init__(self, fail_names=()):
        self.executed = []
        self.fail_names = set(fail_names)
        self._tools = {"fake_tool": {"name": "fake_tool", "description": "测试工具",
                                     "parameters": {"type": "object", "properties": {}}}}

    def names(self):
        return ["fake_tool"]

    async def execute(self, name, args):
        self.executed.append((name, args))
        if name in self.fail_names:
            raise RuntimeError("boom")
        return {"ok": True, "seen": name}


def _install(monkeypatch, rounds, calls=None):
    """rounds: 每轮的增量序列 list[list[dict|Exception]]；calls 收集每轮收到的 messages。"""
    it = iter(rounds)

    async def fake_stream(messages, tools=None, model=None, temperature=None,
                          max_tokens=None, timeout=180.0, first_token_timeout=None,
                          reasoning_effort=None):
        if calls is not None:
            calls.append(list(messages))
        try:
            deltas = next(it)
        except StopIteration:
            raise AssertionError("循环请求了比 rounds 提供更多的 LLM 调用（意外耗尽）")
        for delta in deltas:
            if isinstance(delta, Exception):
                raise delta
            yield delta

    monkeypatch.setattr(llm, "stream_agent_chat", fake_stream)


def _run(monkeypatch, rounds, calls=None, fail_names=()):
    reg = _FakeRegistry(fail_names=fail_names)
    monkeypatch.setattr(ar, "build_tool_registry", lambda *a, **k: reg)
    _install(monkeypatch, rounds, calls)
    events = []

    async def sink(payload):
        events.append(payload)

    out = asyncio.run(ar.run_stream_chat_loop(
        "你好", {"enabled_tools": ["fake_tool"]}, system_prompt="测试人设",
        allowed_tool_ids=["fake_tool"], event_sink=sink, max_iterations=4))
    return out, events, reg


def _chunks(events):
    return "".join(e["sub"]["delta"] for e in events
                   if e["type"] == "step_progress" and e["sub"].get("kind") == "chunk")


def test_prose_only(monkeypatch):
    rounds = [[{"type": "reasoning", "delta": "想一想"},
               {"type": "content", "delta": "你好，"},
               {"type": "content", "delta": "我是方案助手。"}]]
    out, events, reg = _run(monkeypatch, rounds)
    assert out["ok"] is True
    assert out["answer"] == "你好，我是方案助手。"
    assert _chunks(events) == out["answer"]          # 流式与落库严格一致
    assert reg.executed == []
    kinds = [e["sub"]["kind"] for e in events if e["type"] == "step_progress"]
    assert "thinking" in kinds                        # reasoning 边收边推


def test_tool_round_then_final(monkeypatch):
    rounds = [
        [{"type": "content", "delta": "我查一下。\n```tool\n"},
         {"type": "content", "delta": '{"name": "fake_tool", "args": {"q": "x"}}'},
         {"type": "content", "delta": "\n```"}],
        [{"type": "content", "delta": "查到了：结果在这里。"}],
    ]
    calls = []
    out, events, reg = _run(monkeypatch, rounds, calls=calls)
    assert out["ok"] is True
    assert reg.executed == [("fake_tool", {"q": "x"})]
    assert _chunks(events) == "我查一下。\n查到了：结果在这里。"
    assert out["answer"] == _chunks(events)    # 不变量：落库=流式（跨轮累积）
    assert out["answer"].startswith("我查一下。")  # 工具轮的 narration 不丢
    # 工具状态事件两段（调用中/完成）
    tool_texts = [e["sub"]["text"] for e in events
                  if e["type"] == "step_progress" and e["sub"].get("kind") == "tool"]
    assert any("正在调用" in t for t in tool_texts) and any("完成" in t for t in tool_texts)
    # 第二轮 prompt 含工具回传
    assert any("工具 fake_tool 返回" in m["content"] for m in calls[1])
    # 第一轮的 assistant 消息含围栏（历史自洽）
    assert any("```tool" in m["content"] for m in calls[1] if m["role"] == "assistant")


def test_midstream_break_keeps_partial(monkeypatch):
    """断流降级：正文流出后中转断死，保留半截答案为终答。"""
    rounds = [[{"type": "content", "delta": "已经流出的半截"},
               llm.LLMError("connection reset")]]
    out, events, reg = _run(monkeypatch, rounds)
    assert out["ok"] is True
    assert out["answer"] == "已经流出的半截"


def test_empty_failure_not_ok(monkeypatch):
    # 每个条目是一次完整的 stream 调用：首试 + 重试都空手失败 → ok=False
    rounds = [[llm.LLMError("down")], [llm.LLMError("down")]]
    out, events, reg = _run(monkeypatch, rounds)
    assert out["ok"] is False


def test_tool_exception_becomes_result(monkeypatch):
    """工具执行抛异常：转成错误结果回传模型，不炸整轮（正文已流出，不能 error 终态）。"""
    rounds = [
        [{"type": "content", "delta": "试试。\n```tool\n"},
         {"type": "content", "delta": '{"name": "fake_tool", "args": {}}'},
         {"type": "content", "delta": "\n```"}],
        [{"type": "content", "delta": "工具坏了，我直接回答。"}],
    ]
    calls = []
    out, events, reg = _run(monkeypatch, rounds, calls=calls, fail_names={"fake_tool"})
    assert out["ok"] is True
    assert out["answer"] == "试试。\n工具坏了，我直接回答。"
    assert any("工具执行异常" in m["content"] for m in calls[1])


def test_bad_fence_gets_correction(monkeypatch):
    """围栏内容不是合法 JSON：纠正重试，narration 不被误当终答。"""
    rounds = [
        [{"type": "content", "delta": "我查一下。\n```tool\n"},
         {"type": "content", "delta": "不是json"},
         {"type": "content", "delta": "\n```"}],
        [{"type": "content", "delta": "重新来。\n```tool\n"},
         {"type": "content", "delta": '{"name": "fake_tool", "args": {}}'},
         {"type": "content", "delta": "\n```"}],
        [{"type": "content", "delta": "最终答案。"}],
    ]
    calls = []
    out, events, reg = _run(monkeypatch, rounds, calls=calls)
    assert out["ok"] is True
    assert reg.executed == [("fake_tool", {})]
    assert any("不是合法 JSON" in m["content"] for m in calls[1])


def test_max_iterations_forces_final(monkeypatch):
    """超轮：每轮都调工具 → 追加禁工具指令，收尾轮正文作为答案。"""
    tool_round = [{"type": "content", "delta": "再查。\n```tool\n"},
                  {"type": "content", "delta": '{"name": "fake_tool", "args": {}}'},
                  {"type": "content", "delta": "\n```"}]
    final_round = [{"type": "content", "delta": "被强制收尾的回答。"}]
    calls = []
    out, events, reg = _run(monkeypatch, [tool_round] * 4 + [final_round], calls=calls)
    assert out["ok"] is True
    # 不变量：answer=全部已推正文（4 轮 narration + 强制收尾），与 chunk 流一致
    assert out["answer"] == "再查。\n" * 4 + "被强制收尾的回答。"
    assert out["answer"] == _chunks(events)
    assert len(reg.executed) == 4
    assert any("次数上限" in m["content"] for m in calls[-1])


def test_truncated_marker_never_reaches_user(monkeypatch):
    """length 截断：⚠️ 假正文不外推不落库，标记触发纠正重试。"""
    rounds = [
        [{"type": "reasoning", "delta": "思考烧完了"},
         {"type": "content", "delta": "⚠️ 本轮输出因 token 上限被截断", "truncated": True}],
        [{"type": "content", "delta": "精简思考后的正式回答。"}],
    ]
    calls = []
    out, events, reg = _run(monkeypatch, rounds, calls=calls)
    assert out["ok"] is True
    assert out["answer"] == "精简思考后的正式回答。"
    assert out["answer"] == _chunks(events)                 # ⚠️ 假正文没进 chunk 流
    assert "⚠️" not in out["answer"]
    tool_texts = [e["sub"]["text"] for e in events
                  if e["type"] == "step_progress" and e["sub"].get("kind") == "tool"]
    assert any("token 预算耗尽" in t for t in tool_texts)    # 截断状态对用户可见
    assert any("预算耗尽" in m["content"] for m in calls[1])  # 纠正提示喂回模型（措辞覆盖 token/思考两种触发源）


def test_retry_emits_visible_status(monkeypatch):
    """空手失败重试：第二次尝试前先推「连接中断，正在重试」状态。"""
    rounds = [
        [llm.LLMError("proxy stall")],
        [{"type": "content", "delta": "重试成功的回答。"}],
    ]
    out, events, reg = _run(monkeypatch, rounds)
    assert out["ok"] is True
    assert out["answer"] == "重试成功的回答。"
    tool_texts = [e["sub"]["text"] for e in events
                  if e["type"] == "step_progress" and e["sub"].get("kind") == "tool"]
    assert any("连接中断" in t and "重试" in t for t in tool_texts)
