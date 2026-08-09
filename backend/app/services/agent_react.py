# -*- coding: utf-8 -*-
"""agent_react —— 文本式 ReAct 智能体循环（provider/代理通道无关）。

为什么是「文本式 ReAct」而不是原生 function-calling：经 cloudprime 代理实测，原生 tools=
会被负载均衡到异质后端通道——有的接受 type:function，有的只认内置 web_search_* 工具，
【同 payload 同模型背靠背成败各半】（2026-08-07 诊断）。生产不能依赖五五开。

文本式 ReAct：每轮让 LLM 输出【一个 JSON 对象】（走现有 chat_json 的 json_object 模式，
保证可解析），二选一：
  • {"action":"call_tool","tool":"<名>","args":{...},"thought":"..."} → 执行工具，结果回传，继续
  • {"action":"final","answer":"..."} → 收敛，给最终回复
完全不走 tools= 参数 → 不碰通道轮盘。LLM 负责推理/编排，精确性交给确定性工具（见 agent_tools）。

参照 ReAct（Reason+Act+Observe）；与 llm_understand（单次结构化抽取）互补——后者一次出 JSON，
本循环多轮调工具，server_type 等关键槽位由工具（select_models）保证，不再靠 LLM 空抽。
"""
import json
import logging
from typing import Any, Optional

from app.services import llm_client
from app.services.agent_tools import ToolRegistry, build_tool_registry

logger = logging.getLogger(__name__)

# 每轮 LLM 输出的 JSON 契约（chat_json schema 收口）
REACT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},  # "call_tool" | "final"
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "thought": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["action"],
}

REACT_SYSTEM_PROMPT = (
    "你是 CPQ 平台的服务器配置智能体（ReAct：推理→行动→观察）。\n"
    "目标：把用户的服务器需求落地成机型/配件选择。但型号/料号/价格/兼容性【必须由工具给出】，"
    "你不得编造——你只负责推理与编排。\n\n"
    "【每轮只输出一个 json 对象（JSON 格式），二选一】：\n"
    '  1. 调工具：{"action":"call_tool","tool":"工具名","args":{...},"thought":"一句推理：为何调它"}\n'
    '  2. 给结论：{"action":"final","answer":"给用户的中文最终回复"}\n\n'
    "【规则】：\n"
    "- 推荐理由只能引用工具返回的字段（如 selling_points），禁编型号/规格/数字/价格。\n"
    "- 工具结果会以「工具 X 返回: {...}」回传；据此继续推理或给结论。\n"
    "- 先想清 server_type(通用/AI/存储)/形态(1U/2U/4U)/系列 再调 select_models 锁机型。\n"
    "- 信息不足以选机型时，用 final.answer 说明缺什么、并问用户一个最关键的问题（不要逐项问）。\n"
    "- 别绕圈：同样的工具+同样的 args 不要重复调。"
)


def _format_catalog(registry: ToolRegistry) -> str:
    """把 registry 的工具渲染成 system prompt 里的「可用工具」清单。"""
    lines = []
    for t in registry._tools.values():  # noqa: SLF001 —— 同模块，借 _tools 渲染目录
        params = t.get("parameters") or {}
        props = params.get("properties") or {}
        req = params.get("required") or []
        pstr = ", ".join(
            f'{k}{"?" if k not in req else ""}: {(v or {}).get("type", "any")}'
            for k, v in props.items()
        )
        lines.append(f"- {t['name']}({pstr})：{t['description']}")
    return "【可用工具】\n" + "\n".join(lines)


async def run_react_loop(
    requirement_text: str,
    config: dict,
    extra_context: str = "",
    max_iterations: int = 5,
    system_prompt: Optional[str] = None,
) -> dict:
    """文本式 ReAct 主循环。

    参数：
      requirement_text —— 用户需求原文
      config           —— 节点 config（enabled_tools 选工具、system_prompt 覆盖等）
      extra_context    —— 额外上下文（CBR 案例摘要等，拼进首条 user 消息）
      max_iterations   —— 工具循环上限（兜底防爆）
      system_prompt    —— 覆盖默认 REACT system prompt

    返回 {ok:bool, answer:str, tool_calls_log:[{name,args,result}], thought_log:[str], iterations:int}。
    任何失败（LLM 不可用/超轮）返回 ok=False + 空 answer，上层降级到确定性抽取/选型（绝不阻塞）。
    """
    base: dict = {
        "ok": False, "answer": "", "tool_calls_log": [],
        "thought_log": [], "iterations": 0,
    }
    cfg = config or {}
    try:
        if not llm_client.is_llm_enabled():
            base["answer"] = "AI 未启用"
            return base
    except Exception:
        pass

    enabled = cfg.get("enabled_tools")
    # 传完整 cfg（不只是 enabled_tools）：search_cases 需要 case_source/top_k/match 配置注入
    registry = build_tool_registry(cfg if enabled else {})
    if not registry.names():
        base["answer"] = "未启用任何工具"
        return base

    sys_prompt = (system_prompt or cfg.get("system_prompt") or REACT_SYSTEM_PROMPT) \
        + "\n\n" + _format_catalog(registry) \
        + f"\n\n最多 {max_iterations} 轮，尽快收敛。"

    messages: list = [{"role": "system", "content": sys_prompt}]
    user_content = f"需求：{requirement_text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})

    try:
        max_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        max_iter = 5

    for i in range(max_iter):
        base["iterations"] = i + 1
        try:
            # 不传 schema：clean_by_schema 会按 schema.properties 收口，args 是自由对象（无
            # 声明属性）会被清成 {}。ReAct 契约简单（action∈{call_tool,final}），下面手验。
            data = await llm_client.chat_json(messages)
        except llm_client.LLMError as e:
            logger.warning("react loop LLM 失败（降级）: %s", e)
            base["answer"] = ""
            return base
        if not isinstance(data, dict):
            messages.append({"role": "user", "content": "上一轮输出非 JSON 对象，请重出。"})
            continue

        action = (data.get("action") or "").strip()
        thought = (data.get("thought") or "").strip()
        if thought:
            base["thought_log"].append(thought)

        if action == "final":
            base["ok"] = True
            base["answer"] = (data.get("answer") or "").strip()
            return base

        if action == "call_tool":
            name = (data.get("tool") or "").strip()
            args = data.get("args") if isinstance(data.get("args"), dict) else {}
            # 记录 assistant 的调用意图（让多轮历史自洽）
            messages.append({"role": "assistant",
                             "content": json.dumps({"action": "call_tool", "tool": name, "args": args},
                                                   ensure_ascii=False)})
            result = await registry.execute(name, args)
            try:
                result_str = result if isinstance(result, str) else \
                    json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                result_str = str(result)
            base["tool_calls_log"].append({"name": name, "args": args, "result": result})
            messages.append({"role": "user",
                             "content": f"工具 {name} 返回：{result_str}\n请据此继续（调工具或给结论）。"})
            continue

        # 既非 call_tool 也非 final：纠正一次
        messages.append({"role": "user",
                         "content": "上一轮输出 action 不合法（需为 call_tool 或 final），请重出。"})

    # 超轮未收敛：返回 ok=False，上层降级
    base["answer"] = ""
    return base
