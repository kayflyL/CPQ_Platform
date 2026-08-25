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

参照 ReAct（Reason+Act+Observe）；与单次结构化抽取互补——后者一次出 JSON，
本循环多轮调工具，server_type 等关键槽位由工具（select_models）保证，不再靠 LLM 空抽。
"""
import json
import logging
from typing import Any, Awaitable, Callable, Optional

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

REACT_JSON_CONTRACT = (
    "\n\n【本轮输出必须且只能是一个 JSON 对象，不要输出 Markdown 代码块。】\n"
    '二选一：{"action":"call_tool","tool":"工具名","args":{},"thought":"一句推理"} '
    '或 {"action":"final","answer":"给用户的中文最终回复"}。'
)

FINAL_ONLY_CONTRACT = (
    "\n\n【今日任务：只输出一个 JSON 对象，不要 Markdown 代码块，不调用工具、不分步。本节点已给你元字段/标主/规则参考，直接给结论。】\n"
    '必须是：{"action":"final","answer": {"fill":{...},"ask":"...","done":true,"edit":false,"semantic":{...}}}'
    '或者直接顶层：{"fill":{...},"ask":"...","done":true,"edit":false,"semantic":{...}}'    "\n- fill只填客户已明确表达的字段；信息不足用 ask 反问一个最关键问题（不要逐项问）；客户委托/模糊就留空交下游。"
    "\n- semantic 只趟刚式结构字段（workload必须是对象，含 kind/gpu_count/total_vram_gb）；，不要写成字符串。"
)

REACT_AGENT_HINT = (
    "\n\n【工作方式】\n"
    "- 先在心里完整思考：本次需求已知什么、缺什么、该先做什么，再决定动作。\n"
    "- 信息不足时，用 final 反问一个最关键问题（一次只问一个），不要编造。\n"
    "- 需要查目录/配件时，先调工具，工具结果才可用于结论；禁止编造型号/料号/价格。\n"
    "- 每轮只输出一个 JSON 对象；不要只复述需求原文，不要输出 Markdown 代码块。\n"
)

REACT_CONVERGENCE_HINT = (
    "\n\n【收敛规则（必须遵守）】\n"
    "- 数据不足时先问一个最关键的问题，不要为凑数据连续换关键词调工具。\n"
    "- 同一工具+同一类目最多调用一次；如需换词最多再试一次，仍无命中就用 final 说明，并如实报告已取到的工具事实。\n"
    "- 配件数据齐后，立即用 build_plan 组完整方案，然后 final 给用户完整中文方案；禁止反复调工具拖延。\n"
)

NATIVE_TOOL_SYSTEM_HINT = (
    "\n\n【工具调用说明】\n"
    "- 需要查询/计算/生成方案时才调用工具；普通对话直接回复用户。\n"
    "- 信息不足时先向用户追问最关键的问题，不要机械调用工具。\n"
    "- 工具返回的型号、料号、价格、兼容性才可用于回答；禁止编造工具未返回的数据。\n"
    "- 同一工具和同一参数不要重复调用。"
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


async def _run_text_react_loop(
    requirement_text: str,
    config: dict,
    extra_context: str = "",
    max_iterations: int = 5,
    system_prompt: Optional[str] = None,
    allowed_tool_ids: Optional[list] = None,
    allowed_data_sources: Optional[list] = None,
    model: Optional[str] = None,
    event_sink: Optional[Any] = None,
    history: Optional[list] = None,
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]] = None,
) -> dict:
    """文本式 ReAct 主循环。

    参数：
      requirement_text —— 用户需求原文
      config           —— 节点 config（enabled_tools 选工具、system_prompt 覆盖等）
      extra_context    —— 额外上下文（CBR 案例摘要等，拼进首条 user 消息）
      max_iterations   —— 工具循环上限（兜底防爆）
      system_prompt    —— 覆盖默认 REACT system prompt
      event_sink       —— 可选异步事件出口，用于把工具调用生命周期广播到上层（如办公室）

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
    registry = build_tool_registry(cfg if enabled else {}, allowed_tool_ids=allowed_tool_ids, allowed_data_sources=allowed_data_sources)
    if not registry.names():
        base["answer"] = "未启用任何工具"
        return base

    sys_prompt = (system_prompt or cfg.get("system_prompt") or REACT_SYSTEM_PROMPT) \
        + REACT_JSON_CONTRACT \
        + "\n\n" + _format_catalog(registry) \
        + f"\n\n最多 {max_iterations} 轮，尽快收敛。"

    messages: list = [{"role": "system", "content": sys_prompt}]
    if history:
        for m in history[-12:]:
            role = (m or {}).get("role") if isinstance(m, dict) else None
            content = (m or {}).get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    user_content = f"需求：{requirement_text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})

    try:
        max_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        max_iter = 5

    async def _emit(kind: str, text: str = "", tool: Optional[str] = None) -> None:
        if not event_sink:
            return
        try:
            await event_sink({
                "type": "step_progress",
                "step": "react",
                "sub": {"kind": kind, "text": text, "tool": tool},
            })
        except Exception:
            pass

    for i in range(max_iter):
        base["iterations"] = i + 1
        try:
            # 不传 schema：clean_by_schema 会按 schema.properties 收口，args 是自由对象（无
            # 声明属性）会被清成 {}。ReAct 契约简单（action∈{call_tool,final}），下面手验。
            if model:
                data = await llm_client.chat_json(messages, model=model)
            else:
                data = await llm_client.chat_json(messages)
        except llm_client.LLMError as e:
            logger.warning("react loop LLM 失败（降级）: %s", e)
            await _emit("error", f"ReAct LLM 失败：{e}")
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
            raw_ans = data.get("answer") or ""
            if isinstance(raw_ans, (dict, list)):
                base["answer"] = json.dumps(raw_ans, ensure_ascii=False)
            else:
                base["answer"] = str(raw_ans).strip()
            return base

        if action == "call_tool":
            name = (data.get("tool") or "").strip()
            args = data.get("args") if isinstance(data.get("args"), dict) else {}
            # 记录 assistant 的调用意图（让多轮历史自洽）
            messages.append({"role": "assistant",
                             "content": json.dumps({"action": "call_tool", "tool": name, "args": args},
                                                   ensure_ascii=False)})
            await _emit("tool", f"正在调用工具 {name}", name)
            result = await registry.execute(name, args)
            if tool_guard is not None:
                result = await tool_guard(name, args, result)
            try:
                result_str = result if isinstance(result, str) else \
                    json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                result_str = str(result)
            # 压缩工具回传：只保留关键信息，防止上下文随轮次滚大（不塞全文）。
            _MAX_TOOL_RESULT = 1500
            if len(result_str) > _MAX_TOOL_RESULT:
                result_str = result_str[:_MAX_TOOL_RESULT] + "…(截断)"
            await _emit("tool", f"工具 {name} 已完成", name)
            base["tool_calls_log"].append({"name": name, "args": args, "result": result})
            messages.append({"role": "user",
                             "content": f"工具 {name} 返回：{result_str}\n请据此继续（调工具或给结论）。"})
            continue

        # 容错：模型直接回了 final 负载（无 action 包装）→ 视作 final
        # （agent_fill 的 final.answer 本身就是 {fill,ask,done,edit}，模型易把该 JSON 当顶层输出）
        if any(k in data for k in ("fill", "ask", "done", "edit")):
            base["ok"] = True
            base["answer"] = json.dumps(data, ensure_ascii=False)
            return base

        # 既非 call_tool 也非 final：纠正一次
        messages.append({"role": "user",
                         "content": "上一轮输出 action 不合法（需为 call_tool 或 final），请重出。"})

    # 超轮未收敛：返回 ok=False，上层降级
    base["answer"] = ""
    return base

async def _run_thinking_loop(
    requirement_text: str,
    config: dict,
    extra_context: str = "",
    max_iterations: int = 5,
    system_prompt: Optional[str] = None,
    allowed_tool_ids: Optional[list] = None,
    allowed_data_sources: Optional[list] = None,
    model: Optional[str] = None,
    event_sink: Optional[Any] = None,
    history: Optional[list] = None,
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]] = None,
    final_only: bool = False,
    final_only_contract: Optional[str] = None,
    llm_timeout: float = 90.0,
    llm_max_attempts: int = 2,
) -> dict:
    """智能体主循环（ChatGPT 式）：流式思考 + 工具调用 + 必反问。

    与 _run_text_react_loop 的差异：
      - 用 stream_agent_chat 逐段吐 reasoning（思考）与 content（正文），思考经 event_sink 推前端；
      - 模型必须给出可解析的结构化 JSON（含 action，或 fill/ask/done/edit 顶层）；
        若模型只复述需求/给自然语言，则追加纠正重试，绝不静默当成功；
      - 返回含 thinking 字段，供前端实时展示。

    返回 {ok, answer, tool_calls_log, thought_log, thinking, iterations}。
    """
    base: dict = {
        "ok": False, "answer": "", "tool_calls_log": [],
        "thought_log": [], "thinking": [], "iterations": 0,
    }
    cfg = config or {}
    try:
        if not llm_client.is_llm_enabled():
            base["answer"] = "AI 未启用"
            return base
    except Exception:
        pass

    registry = build_tool_registry(cfg, allowed_tool_ids=allowed_tool_ids,
                                   allowed_data_sources=allowed_data_sources)
    if not final_only and not registry.names():
        base["answer"] = "未启用任何工具"
        return base

    if final_only:
        # 单次流式：不挂工具目录，模型只须一次输出最终 JSON。契约由调用方覆盖（agent_fill 用默认 fill/ask/done/edit，kp_reason 用配件提议契约）。
        _final_contract = final_only_contract or FINAL_ONLY_CONTRACT
        sys_prompt = (system_prompt or cfg.get("system_prompt") or REACT_SYSTEM_PROMPT) \
            + _final_contract \
            + f"\n\n一次输出，尽快收敛。"
    else:
        sys_prompt = (system_prompt or cfg.get("system_prompt") or REACT_SYSTEM_PROMPT) \
            + REACT_JSON_CONTRACT \
            + REACT_AGENT_HINT \
            + REACT_CONVERGENCE_HINT \
            + "\n\n" + _format_catalog(registry) \
            + f"\n\n最多 {max_iterations} 轮，尽快收敛。"

    messages: list = [{"role": "system", "content": sys_prompt}]
    if history:
        for m in history[-12:]:
            role = (m or {}).get("role") if isinstance(m, dict) else None
            content = (m or {}).get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    user_content = f"需求：{requirement_text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})

    try:
        max_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        max_iter = 5

    async def _emit(kind: str, text: str = "", tool: Optional[str] = None) -> None:
        if not event_sink:
            return
        try:
            await event_sink({"type": "step_progress", "step": "react",
                              "sub": {"kind": kind, "text": text, "tool": tool}})
        except Exception:
            pass

    async def _once() -> tuple[str, str, Optional[dict]]:
        """单轮取模型输出。
        final_only（单次收敛）走一次非流式 chat_json：只拿最终 JSON，不逐段广播思考，
        既省时也避免 step_progress 刷屏。工具 ReAct（final_only=False）仍走流式聚合，
        让前端能看到思考与工具调用过程。"""
        parts: list[str] = []
        thinks: list[str] = []
        if final_only:
            try:
                data = await llm_client.chat_json(messages, model=model,
                                                  timeout=llm_timeout, max_attempts=llm_max_attempts)
            except llm_client.LLMError as e:
                logger.warning("agent final_only LLM 失败（降级）: %s", e)
                return "", "", None
            if isinstance(data, dict):
                return json.dumps(data, ensure_ascii=False), "", data
            return "", "", None
        try:
            async for item in llm_client.stream_agent_chat(
                    llm_client._ensure_json_instruction(messages), model=model):
                t = item.get("type")
                d = item.get("delta") or ""
                if t == "reasoning":
                    thinks.append(d)
                    await _emit("thinking", d)
                elif t == "content":
                    parts.append(d)
        except llm_client.LLMError as e:
            logger.warning("agent stream LLM 失败（降级）: %s", e)
            return "", "", None
        text = "".join(parts).strip()
        think = "".join(thinks)
        if think:
            base["thinking"].append(think)
        data: Optional[dict] = None
        if text:
            try:
                candidate = llm_client._parse_json_content(text)
                if isinstance(candidate, dict):
                    data = candidate
            except Exception:
                data = None
        # 流式正文不是 JSON 时不再切非流式 chat_json（避免同一超长 prompt 再喂一遍、延迟翻倍），
        # 直接返回 data=None，由主循环追加一条矫正消息后继续流式重试。
        return text, think, data

    for i in range(max_iter):
        base["iterations"] = i + 1
        text, _think, data = await _once()
        if data is None:
            raw = (text or "").strip()
            messages.append({"role": "user",
                             "content": "上一轮输出不是 JSON 对象。请只输出一个 JSON 对象；"
                                        "若信息不足，用 {\"action\":\"final\",\"answer\":{...}} 反问；"
                                        "不要只复述需求原文。"})
            continue
        if not isinstance(data, dict):
            messages.append({"role": "user", "content": "上一轮输出非 JSON 对象，请重出。"})
            continue

        action = (data.get("action") or "").strip()
        thought = (data.get("thought") or "").strip()
        if thought:
            base["thought_log"].append(thought)

        # final_only（单次流式）：模型可直接给结果对象（无 action），或经 action:"final" 包裹。
        # 仅当调用方显式传了自定义契约（如 kp_reason 的配件提议）才接受裸对象；
        # agent_fill 用默认契约时仍必须含 fill/ask/done/edit 或 action:final，避免误收垃圾 dict。
        _bare_ok = final_only and final_only_contract is not None
        if action == "final" or any(k in data for k in ("fill", "ask", "done", "edit")) \
                or (_bare_ok and not action):
            if any(k in data for k in ("fill", "ask", "done", "edit")) or (_bare_ok and not action):
                base["ok"] = True
                base["answer"] = json.dumps(data, ensure_ascii=False)
                return base
            raw_ans = data.get("answer") or ""
            if isinstance(raw_ans, (dict, list)):
                base["ok"] = True
                base["answer"] = json.dumps(raw_ans, ensure_ascii=False)
                return base
            ans_str = str(raw_ans).strip()
            if not ans_str:
                base["ok"] = True
                base["answer"] = ""
                return base
            # 工具 ReAct 路径：模型给自然语言最终回答，直接收敛（final_only=False）。
            # 单次抽取（agent_fill）路径仍严格要求 JSON，避免误收“只复述需求”的垃圾。
            if not final_only:
                base["ok"] = True
                base["answer"] = ans_str
                return base
            # 防御：final 只复述需求/不可解析 → 纠正重试，不静默当成功
            if ans_str:
                try:
                    obj = llm_client._parse_json_content(ans_str)
                    if isinstance(obj, dict) and (any(k in obj for k in ("fill", "ask", "done", "edit")) or final_only):
                        base["ok"] = True
                        base["answer"] = ans_str
                        return base
                except Exception:
                    pass
                messages.append({"role": "user",
                                 "content": "最终回复请只输出一个 JSON 对象；"
                                            "若信息不足则说明缺什么，不要只复述需求原文。"})
                continue
            base["ok"] = True
            base["answer"] = ans_str
            return base
        if action == "call_tool":
            if final_only:
                messages.append({"role": "user", "content": "本节点无需工具，请直接输出最终 JSON 对象。"})
                continue
            name = (data.get("tool") or "").strip()
            args = data.get("args") if isinstance(data.get("args"), dict) else {}
            messages.append({"role": "assistant",
                             "content": json.dumps({"action": "call_tool", "tool": name, "args": args},
                                                   ensure_ascii=False)})
            await _emit("tool", f"正在调用工具 {name}", name)
            result = await registry.execute(name, args)
            if tool_guard is not None:
                result = await tool_guard(name, args, result)
            try:
                result_str = result if isinstance(result, str) else \
                    json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                result_str = str(result)
            await _emit("tool", f"工具 {name} 已完成", name)
            base["tool_calls_log"].append({"name": name, "args": args, "result": result})
            messages.append({"role": "user",
                             "content": f"工具 {name} 返回：{result_str}\n请据此继续（调工具或给结论）。"})
            continue

        messages.append({"role": "user",
                         "content": "上一轮输出 action 不合法（需为 call_tool 或 final），请重出。"})

    base["answer"] = ""
    return base


async def _run_native_tool_loop(
    requirement_text: str,
    config: dict,
    extra_context: str,
    max_iterations: int,
    system_prompt: Optional[str],
    allowed_tool_ids: Optional[list],
    allowed_data_sources: Optional[list],
    model: Optional[str],
    event_sink: Optional[Any],
    history: Optional[list],
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]],
) -> dict:
    """Prefer native function calling; raise LLMError when the provider is unavailable."""
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

    registry = build_tool_registry(cfg, allowed_tool_ids=allowed_tool_ids, allowed_data_sources=allowed_data_sources)
    if not registry.names():
        base["answer"] = "未启用任何工具"
        return base

    sys_prompt = (system_prompt or cfg.get("system_prompt") or REACT_SYSTEM_PROMPT) \
        + NATIVE_TOOL_SYSTEM_HINT
    messages: list = [{"role": "system", "content": sys_prompt}]
    if history:
        for m in history[-12:]:
            role = (m or {}).get("role") if isinstance(m, dict) else None
            content = (m or {}).get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    user_content = f"需求：{requirement_text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})

    try:
        max_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        max_iter = 5

    async def _emit(kind: str, text: str = "", tool: Optional[str] = None) -> None:
        if not event_sink:
            return
        try:
            await event_sink({
                "type": "step_progress",
                "step": "react",
                "sub": {"kind": kind, "text": text, "tool": tool},
            })
        except Exception:
            pass

    try:
        for i in range(max_iter):
            base["iterations"] = i + 1
            response = await llm_client.chat_with_tools(messages, tools=registry.schemas(), model=model)
            tool_calls = response.get("tool_calls") or []
            if tool_calls:
                base["tool_attempted"] = True
                messages.append(response["message"])
                for call in tool_calls:
                    name = str(call.get("name") or "").strip()
                    args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                    await _emit("tool", f"正在调用工具 {name}", name)
                    result = await registry.execute(name, args)
                    if tool_guard is not None:
                        result = await tool_guard(name, args, result)
                    try:
                        result_str = result if isinstance(result, str) else \
                            json.dumps(result, ensure_ascii=False, default=str)
                    except Exception:
                        result_str = str(result)
                    await _emit("tool", f"工具 {name} 已完成", name)
                    base["tool_calls_log"].append({"name": name, "args": args, "result": result})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": str(call.get("id") or ""),
                        "content": result_str,
                    })
                continue

            answer = str((response.get("message") or {}).get("content") or "").strip()
            base["ok"] = bool(answer)
            base["answer"] = answer
            return base
    except llm_client.LLMNativeToolsUnsupported as e:
        base["unsupported"] = True
        base["error"] = f"native_unsupported:{e}"[:300]
        return base
    except llm_client.LLMError as e:
        base["error"] = f"llm_error:{e}"[:300]
        return base
    except Exception as e:
        logger.exception("native tool loop unexpected error")
        base["error"] = f"exception:{e}"[:300]
        return base

    base["answer"] = ""
    return base


async def run_react_loop(
    requirement_text: str,
    config: dict,
    extra_context: str = "",
    max_iterations: int = 5,
    system_prompt: Optional[str] = None,
    allowed_tool_ids: Optional[list] = None,
    allowed_data_sources: Optional[list] = None,
    model: Optional[str] = None,
    event_sink: Optional[Any] = None,
    history: Optional[list] = None,
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]] = None,
    final_only: bool = False,
    final_only_contract: Optional[str] = None,
    llm_timeout: float = 90.0,
    llm_max_attempts: int = 2,
) -> dict:
    """Agent loop: native tools first, text-ReAct fallback only before side effects."""
    # final_only = 单次流式（无工具）：不进入 native tool 循环，也不走多轮工具回退，
    # 直接走流式单次 JSON 输出，避免模型支持原生工具时被错误挂上工具目录。
    if final_only or not llm_client.model_supports_native_tools(model):
        return await _run_thinking_loop(
            requirement_text=requirement_text,
            config=config,
            extra_context=extra_context,
            max_iterations=max_iterations,
            system_prompt=system_prompt,
            allowed_tool_ids=allowed_tool_ids,
            allowed_data_sources=allowed_data_sources,
            model=model,
            event_sink=event_sink,
            history=history,
            tool_guard=tool_guard,
            final_only=final_only,
            final_only_contract=final_only_contract,
            llm_timeout=llm_timeout,
            llm_max_attempts=llm_max_attempts,
        )

    native = await _run_native_tool_loop(
        requirement_text=requirement_text,
        config=config,
        extra_context=extra_context,
        max_iterations=max_iterations,
        system_prompt=system_prompt,
        allowed_tool_ids=allowed_tool_ids,
        allowed_data_sources=allowed_data_sources,
        model=model,
        event_sink=event_sink,
        history=history,
        tool_guard=tool_guard,
    )
    if native.get("ok"):
        return native
    if native.get("unsupported"):
        logger.info("native tools unsupported, fallback to text ReAct")
    elif not native.get("tool_attempted"):
        logger.warning("native tool loop failed before tool execution (%s), fallback to text ReAct", native.get("error"))
    else:
        logger.warning("native tool loop failed after tool execution; skip text fallback to avoid rerunning side effects")
        return native
    return await _run_thinking_loop(
        requirement_text=requirement_text,
        config=config,
        extra_context=extra_context,
        max_iterations=max_iterations,
        system_prompt=system_prompt,
        allowed_tool_ids=allowed_tool_ids,
        allowed_data_sources=allowed_data_sources,
        model=model,
        event_sink=event_sink,
        history=history,
        tool_guard=tool_guard,
        final_only=final_only,
        final_only_contract=final_only_contract,
        llm_timeout=llm_timeout,
        llm_max_attempts=llm_max_attempts,
    )
