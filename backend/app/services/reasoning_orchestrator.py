"""Graph Orchestrator —— 高 agent 程度的推理编排器（2026-08 重构·阶段2/6）。

形态：画布能力节点 = 主控 agent 的技能池；执行时由一个 LLM 编排 agent 持有完整对话上下文，
在「能力就绪约束」内自主决定下一步：调哪个能力 / 反问用户 / 收敛出方案。每个能力调用 =
一个智能节点（理解/缺口/场景/机型/配件/组装/校对），白盒展示思考与工具轨迹。

与纯自由 agent 的区别（保稳定）：
  - 能力就绪约束：只允许调用「前置能力已完成」的节点（图 DAG 派生），LLM 不能乱跳；
  - 确定性红线：LLM 只能触发，不能改数据（价格/兼容性规则保证）；
  - 任何 LLM 决策失败 → 退化为「按阶段顺序执行能力链」（确定性兜底）。

拓扑真源（2026-08-09 定稿）：能力链不再硬编码——由 active 流的画布图（nodes/edges）实时派生，
用户改图 = 改执行。本文件仅保留「兜底链」（图缺失/不合法时用），且兜底链也是由默认 v12 种子图
经同一套推导函数算出来的，不是第二份硬编码拓扑。

记忆：conversation（我问→你答→我做了什么）作为完整上下文喂给编排 agent 与能力节点，
不再用文本拼接（_merge_clarify_text 的"补充：xxx"）。
"""
import json
import logging
import time
from typing import Any, Optional

from app.services import llm_client

logger = logging.getLogger(__name__)

# ── 节点分类（画布节点 → 编排器角色）───────────────────────────────────
# 特殊节点不入能力池：llm_ask=反问动作（非 step）；extract=AI 失效兜底（非 step）；
# condition=透明桥（不执行，仅把入边源→出边目标直连参与依赖推导）。
_SPECIAL_TYPES = {"llm_ask", "extract", "condition", "orchestrator"}
# 确定性红线默认（存量默认值；画布抽屉可改，编排器只读节点配置、不写死行为）。
_DEFAULT_DETERMINISTIC = {"spec_compliance", "compose", "budget_check", "audit_fix", "review", "result_check"}
# 可执行节点类型（reasoning_executor._dispatch 有 handler，可作为能力 step）。
# 新节点类型 = 新代码（插件注册表）；拓扑/顺序/依赖不再硬编码，由画布图派生。
_DISPATCH_TYPES = {
    "understand", "gap_analyze", "scene_decide", "model_reason", "kp_reason",
    "spec_compliance", "compose", "budget_check", "llm_audit", "audit_fix", "review",
    "text_clean", "normalize_input", "llm_agent", "slot_validate", "scene_analysis",
    "select_baseline", "match_kp", "clarity_check", "ask_user", "confirm_series", "llm_confirm", "result_check",
}


def _topo_sort(caps: list, dep_map: dict) -> Optional[list]:
    """Kahn 拓扑排序（保持画布出现顺序稳定）；成环 → None。"""
    cap_order = [c["key"] for c in caps]
    indeg = {c["key"]: len(dep_map[c["key"]]) for c in caps}
    ready = [k for k, d in indeg.items() if d == 0]
    ready.sort(key=cap_order.index)
    order = []
    while ready:
        k = ready.pop(0)
        order.append(k)
        for c in caps:
            if k in dep_map[c["key"]]:
                indeg[c["key"]] -= 1
                if indeg[c["key"]] == 0:
                    ready.append(c["key"])
                    ready.sort(key=cap_order.index)
    return order if len(order) == len(caps) else None


def _derive_capabilities(flow: dict, node_configs: dict) -> Optional[list]:
    """从画布图派生能力链 [{key,label,deps,deterministic,type}]（拓扑序）。

    规则（2026-08-09 蓝图 §1，用户确认）：
    - 能力节点 = type 有后端 handler 且非特殊（llm_ask/extract/condition）
    - condition 透明桥：condition 的入边源 → 出边目标 直连后移除 condition 相关边
    - llm_ask / extract 相关边不参与能力依赖（反问分支/兜底分支不是能力链）
    - deps = 过滤后的直接前驱能力节点；边 source_handle/condition 不参与
      （本模型是「能力池全执行、LLM 选顺序」，不是分支语义）
    - 图缺能力节点 / 能力 DAG 成环 → 返回 None（上层兜底默认链）
    """
    graph = (flow or {}).get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    cond_ids = {n.get("id") for n in nodes if (n.get("type") or "") == "condition"}
    caps = []
    for n in nodes:
        nid, typ = n.get("id"), n.get("type")
        if not nid or not typ:
            continue
        if typ in _SPECIAL_TYPES or typ not in _DISPATCH_TYPES:
            continue
        caps.append({"key": nid, "label": n.get("label") or nid, "type": typ})
    if not caps:
        return None
    cap_keys = {c["key"] for c in caps}
    # 边过滤 + condition 透明桥
    derived = []
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if t in cond_ids:
            for e2 in edges:
                if e2.get("source") == t and e2.get("target") not in cond_ids:
                    derived.append((s, e2.get("target")))
        elif s in cond_ids or s in _SPECIAL_TYPES or t in _SPECIAL_TYPES:
            continue
        else:
            derived.append((s, t))
    dep_map = {c["key"]: [] for c in caps}
    for s, t in derived:
        if s in cap_keys and t in cap_keys and t != s and s not in dep_map[t]:
            dep_map[t].append(s)
    order = _topo_sort(caps, dep_map)
    if order is None:
        return None
    by_key = {c["key"]: c for c in caps}
    cfg = node_configs or {}
    out = []
    for k in order:
        c = by_key[k]
        c["deps"] = dep_map[k]
        # 确定性红线：节点配置优先（画布抽屉可改），缺省用默认红线集合
        c["deterministic"] = bool((cfg.get(k) or {}).get("deterministic", k in _DEFAULT_DETERMINISTIC))
        out.append(c)
    return out


# ── 兜底能力链（图缺失/不合法时用）────────────────────────────────────
# 由默认 v12 种子图经同一套 _derive_capabilities 算出——不是第二份硬编码拓扑。
from app.repository.reasoning_flow_repo import DEFAULT_GRAPH_V11  # noqa: E402

CAPABILITIES = _derive_capabilities(
    {"graph": {"nodes": DEFAULT_GRAPH_V11.get("nodes") or [],
               "edges": DEFAULT_GRAPH_V11.get("edges") or []}},
    {}) or []

# ---- 编排配置（画布「编排配置」节点抽屉；未画节点时用默认，全部可配不黑盒）------------
_ORCH_CFG_DEFAULT = {
    "memory": {"summary_enabled": True, "turns": 12, "fields": ["slots", "gap", "scene", "cands", "done"]},
    "plan_preview": True,
    "parallel_enabled": False,
    "parallel_limit": 2,
    "ai_budget": "balanced",
    # 四类预算（原则5，前端抽屉可配；0=不限制）：
    # wall_clock_s 墙钟秒数 / max_steps 能力步数 / max_tool_calls 工具调用次数 / max_ask_rounds 反问轮数
    "budgets": {"wall_clock_s": 240, "max_steps": 30, "max_tool_calls": 40, "max_ask_rounds": 6},
}
_AI_BUDGET = {
    "fast":     {"model_iter": 3, "kp_iter": 3, "audit_llm": False},
    "balanced": {"model_iter": 4, "kp_iter": 4, "audit_llm": True},
    "quality":  {"model_iter": 6, "kp_iter": 6, "audit_llm": True},
}


def _load_orch_cfg(node_configs: dict) -> dict:
    """读编排配置：画布「编排配置」节点配置优先，缺省用默认；ai_budget 展开为节点参数。"""
    cfg = node_configs.get("orchestrator") or {}
    out = {**_ORCH_CFG_DEFAULT, **(cfg if isinstance(cfg, dict) else {})}
    if isinstance(cfg.get("memory"), dict):
        out["memory"] = {**_ORCH_CFG_DEFAULT["memory"], **cfg["memory"]}
    out["_budget"] = _AI_BUDGET.get(out.get("ai_budget") or "balanced", _AI_BUDGET["balanced"])
    return out


def _budget_state(box: dict, orch_cfg: dict, t0: float, ask_rounds: int) -> dict:
    """当前预算用量（原则5·计划可观测）：墙钟/步数/工具调用/反问轮数。"""
    b = (orch_cfg.get("budgets") or {})
    return {
        "elapsed_s": round(time.monotonic() - t0, 1),
        "wall_clock_s": int(b.get("wall_clock_s") or 0),
        "steps": int(box.get("steps") or 0),
        "max_steps": int(b.get("max_steps") or 0),
        "tool_calls": int(box.get("tools") or 0),
        "max_tool_calls": int(b.get("max_tool_calls") or 0),
        "ask_rounds": int(ask_rounds or 0),
        "max_ask_rounds": int(b.get("max_ask_rounds") or 0),
    }


def _budget_exhausted(bs: dict) -> bool:
    """预算是否耗尽（原则5：超预算不再反问、不再等 LLM 决策，线性跑完确定性链）。"""
    if bs["wall_clock_s"] and bs["elapsed_s"] >= bs["wall_clock_s"]:
        return True
    if bs["max_steps"] and bs["steps"] >= bs["max_steps"]:
        return True
    if bs["max_tool_calls"] and bs["tool_calls"] >= bs["max_tool_calls"]:
        return True
    return False


def _apply_ai_budget(config, orch: dict, ntype: str) -> dict:
    """把 AI 增强预算注入节点配置：model/kp 的 ReAct 轮数、llm_audit 是否走 LLM。
    预算优先于节点种子默认（用户设了 fast 就全局快）。"""
    cfg = dict(config or {})
    b = orch.get("_budget") or _AI_BUDGET["balanced"]
    if ntype == "model_reason":
        cfg["max_iterations"] = b["model_iter"]
    elif ntype == "kp_reason":
        cfg["max_iterations"] = b["kp_iter"]
    elif ntype == "llm_audit":
        cfg["enable_llm"] = b["audit_llm"]
    return cfg

# 编排 agent 的决策契约（chat_json schema）
ORCH_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},        # call / ask / final
        "capability": {"type": "string"},    # action=call 时的能力 key
        "question": {"type": "string"},      # action=ask 时的问题
        "options": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},        # 决策理由（白盒展示）
        "summary": {"type": "string"},       # 给用户的阶段性说明
    },
    "required": ["action"],
}

ORCH_SYSTEM_PROMPT = (
    "你是 CPQ 平台的服务器需求分析编排器。你负责决定下一步动作，把客户需求推进到整机方案。\n"
    "【可用动作】\n"
    "1. call：调用一个能力节点（capability 必须是可用的能力之一）。每个能力最多调一次。\n"
    "2. ask：信息不足时反问客户（question + options）。反问后等客户补充，下一轮继续。\n"
    "3. final：方案已就绪（review 完成），给最终总结（summary）。\n"
    "【规则】\n"
    "- 只能调用「已就绪」（前置能力已完成）的能力；compose/budget_check/review 是确定性红线，触发即可。\n"
    "- 客户需求很模糊、缺关键信息时优先 ask（一次问最关键的一个问题，带选项）。\n"
    "- 每个动作给 reason（一句话，白盒展示给客户看）。\n"
    "- 不要重复调用已完成的能力。\n"
    "只输出 json（JSON 格式）：{action, capability?, question?, options?, reason, summary?}"
)


def _state_summary(ctx: dict, done: set, fields: Optional[list] = None) -> str:
    """当前推理状态摘要（喂给编排 agent 决策）。fields 控制包含哪些段（编排配置 memory.fields 可配）。"""
    fields = fields or []
    def want(k: str) -> bool:
        return (not fields) or (k in fields)
    parts = []
    if want("slots"):
        ext = ctx.get("ext") or {}
        if ext:
            s = []
            if ext.get("server_type_name"): s.append(f"类型={ext['server_type_name']}")
            if ext.get("series"): s.append(f"系列={ext['series']}")
            if ext.get("form"): s.append(f"形态={ext['form']}")
            if ext.get("budget"): s.append(f"预算={ext['budget']}")
            cats = ext.get("categories") or []
            if cats: s.append(f"品类={','.join(cats)}")
            parts.append("已理解：" + ("；".join(s) if s else "（空）"))
    if want("gap"):
        gap = ctx.get("missing_fields") or []
        if gap:
            parts.append(f"缺口：{'、'.join(gap)}")
    if want("scene") and ctx.get("scene"):
        parts.append(f"场景：{ctx['scene'].get('scene_name')}")
    if want("cands"):
        baselines = ctx.get("baselines") or []
        if baselines:
            parts.append(f"候选机型：{','.join((b.get('name') or '') for b in baselines[:3])}")
        kps = ctx.get("kp_parts") or []
        if kps:
            parts.append(f"配件已配 {len(kps)} 件")
        plans = ctx.get("plans") or []
        if plans:
            parts.append(f"方案 {len(plans)} 张")
    if want("done"):
        parts.append(f"已完成能力：{'、'.join(sorted(done)) if done else '（无）'}")
    return "\n".join(parts)


def _needs_llm_decision(ctx: dict, ready: list) -> bool:
    """混合脊柱门控（2026-08）：是否该让 LLM 决策，而不是确定性跑下一步。
    - 无就绪能力 → 收尾总结（LLM 1 次）；
    - clarity 未算（首步前）→ 确定性跑首个能力（understand 自身就是 LLM，无需编排层再问）；
    - clarity != explicit（信息不足）→ LLM 决策反问/继续（保留判断力）；
    - 选型落空（baselines 空且无方案）→ LLM 决策；
    - 其余 → False：按拓扑序确定性执行，不为「下一步」这种确定的事反复调 LLM。
    """
    if not ready:
        return True
    clarity = ctx.get("clarity")
    if clarity is None:
        return False
    if clarity != "explicit":
        return True
    if ctx.get("baselines") is not None and not ctx.get("baselines") and not ctx.get("plans"):
        return True
    return False


def _ready_capabilities(done: set, capabilities: Optional[list] = None) -> list:
    """可调用的能力（前置依赖已完成且自身未完成）。capabilities 缺省=兜底链。"""
    caps = capabilities if capabilities is not None else CAPABILITIES
    ready = []
    for c in caps:
        if c["key"] in done:
            continue
        if all(d in done for d in (c.get("deps") or [])):
            ready.append(c["key"])
    return ready


async def _decide_next(state: str, ready: list, conversation: list, ask_rounds: int,
                     force_complete: bool = False, max_rounds: int = 6,
                     ctx: Optional[dict] = None, capabilities: Optional[list] = None) -> dict:
    """编排 agent 决策下一步。失败返回 None（上层退化线性链）。"""
    if not llm_client.is_llm_enabled():
        return None
    fc_note = "【重要】客户已选择「跳过反问」，你必须直接出方案：不要 ask，按顺序调用能力直到 final。" if force_complete else ""
    cap_note = (f"【重要】反问已达上限（{ask_rounds}/{max_rounds}），禁止再 ask，必须 call 能力直到 final。" if ask_rounds >= max_rounds else "")
    del_note = "【重要】客户已委托你推荐（说了你推荐/不确定/随便），不要再 ask，直接按推荐默认调用能力直到 final。" if ctx.get("delegated") else ""
    det_note = ""
    dets = [c["key"] for c in (capabilities or CAPABILITIES) if c.get("deterministic")]
    if dets:
        det_note = f"【确定性红线（LLM 只能触发、不能改数据，直接调用即可）】：{', '.join(dets)}\n"
    user = (
        f"当前推理状态：\n{state}\n\n"
        f"可用能力：{', '.join(ready) if ready else '（无，应 final）'}\n"
        f"反问轮次：{ask_rounds}/{max_rounds}\n"
        + (f"{fc_note}\n" if fc_note else "")
        + (f"{cap_note}\n" if cap_note else "")
        + (f"{del_note}\n" if del_note else "")
        + (f"{det_note}" if det_note else "")
        + (f"对话历史（最近 6 条）：\n" + "\n".join(f"{m.get('role')}: {str(m.get('content'))[:200]}" for m in conversation[-6:]) if conversation else "")
        + "\n\n请决策下一步动作。"
    )
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": ORCH_SYSTEM_PROMPT}, {"role": "user", "content": user}],
            schema=ORCH_SCHEMA, temperature=0.2,
        )
        return data or {}
    except Exception as e:
        logger.warning("编排 agent 决策失败（退化线性链）: %s", e)
        return None


# C（2026-08-09）：自纠重跑目标由 LLM 决策——重建脊梁强制保留，LLM 只决定可选重跑项。
# 脊梁 = 修复（补 GPU/抬内存等）后重建方案的确定性后果，不可省（retry_scope 的子集，配置驱动）。
_RETRY_SPINE = ("kp_reason", "spec_compliance", "compose", "budget_check")


async def _decide_retry_targets(ctx: dict, retry_caps: list) -> Optional[list]:
    """C：把审计意见喂回编排 agent，由它决定可选重跑项（再审/再自纠 要不要）。

    审计（llm_audit / spec_compliance）检出问题后，audit_fix 已确定性改信号（补 GPU/抬内存），
    需重跑能力链重建方案。重建脊梁（kp_reason→spec_compliance→compose→budget_check）是
    修复的确定性后果，强制保留；LLM 只能从 retry_caps 里选可选重跑项（受确定性红线约束：
    不能改数据、不能跳过脊梁、不能提前 final）。
    AI 关 / LLM 失败 → None（上层全量重跑，现状兜底）。
    """
    if not llm_client.is_llm_enabled():
        return None
    mandatory = [c for c in retry_caps if c in _RETRY_SPINE]
    optional = [c for c in retry_caps if c not in _RETRY_SPINE]
    if not optional:
        return retry_caps  # 无可选重跑项 → 全量（=脊梁）
    from app.services.capabilities import _collect_audit_issues
    findings = _collect_audit_issues(ctx) or []
    user = (
        "审计发现的问题：\n" + ("\n".join(f"- {i}" for i in findings) if findings else "（无明确问题，按全量重跑）")
        + "\n\n已执行确定性修复（补 GPU / 抬内存等），以下能力需要重跑以重建方案：\n"
        + f"必跑（修复的确定性后果，不可省）：{', '.join(mandatory) or '（无）'}\n"
        + f"可选（决定是否要）：{', '.join(optional) or '（无）'}\n"
        + "请决定可选能力中哪些要重跑（最小集：修复已确认生效就不再审；拿不准就加）。"
        + "\n只输出一个 json 对象（JSON 格式）：{targets: [...], reason: \"\"}"
    )
    schema = {
        "type": "object",
        "properties": {
            "targets": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["targets"],
    }
    try:
        data = await llm_client.chat_json(
            [{"role": "system",
              "content": "你是 CPQ 平台的方案校对编排助手。审计发现问题并已执行确定性修复，你需要决定哪些可选能力要重跑（只能从给出的可选里选，不要编造）。"},
             {"role": "user", "content": user}],
            schema=schema, temperature=0.1,
        )
    except Exception as e:
        logger.warning("自纠重跑目标决策失败，全量重跑: %s", e)
        return None
    chosen = [str(x) for x in ((data or {}).get("targets") or []) if str(x) in optional]
    targets = list(dict.fromkeys(mandatory + chosen))
    return targets or retry_caps


async def run_orchestrator(opportunity_id: str, requirement_text: str, flow: dict,
                           broadcast, initial_ctx: Optional[dict] = None,
                           session=None) -> dict:
    """Graph Orchestrator 主循环：LLM 自主编排（能力就绪约束内）→ 反问循环 → 收敛。

    返回 ctx（调用方检查 awaiting_input 决定发 pipeline_paused/done）。
    编排 agent 决策失败 → 按 CAPABILITIES 顺序退化线性链（确定性兜底）。
    记忆：conversation 持久化到会话（ReasoningSession），跨轮恢复"我问→你答→我做了什么"。
    """
    _MEM_KEY = "orchestrator_conversation"
    _MEM_SUMMARY_KEY = "orchestrator_memory_summary"
    from app.services.reasoning_executor import _dispatch
    node_configs = (flow or {}).get("node_configs") or {}
    orch_cfg = _load_orch_cfg(node_configs)
    _t0 = time.monotonic()
    _budget_box: dict = {"steps": 0, "tools": 0}
    ctx: dict[str, Any] = {
        "requirement_text": requirement_text,
        "opportunity_id": opportunity_id,
        "flow_configs": node_configs,
        "llm_enabled": llm_client.is_llm_enabled(),
    }
    if initial_ctx:
        ctx.update(initial_ctx)
    ai_off = not bool(ctx.get("llm_enabled", True))
    # 目录引导持久化需要与会话读端同一 store（thread 会话/商机）；不传则回落旧行为
    if session is not None:
        ctx["_session"] = session

    capabilities = _derive_capabilities(flow, node_configs) or CAPABILITIES  # 图派生；缺失/不合法→兜底默认链
    cap_by_key = {c["key"]: c for c in capabilities}
    steps = [{"key": c["key"], "label": c["label"]} for c in capabilities]
    await broadcast({"type": "pipeline_start", "steps": steps})

    done: set = set()
    # 记忆恢复：读会话历史对话（跨轮续接）；无 supplement 且非 force_complete = 全新对话 → 清空
    prev_conversation: list = []
    prev_summary: str = ""
    if session is not None:
        try:
            raw = (session.get_extra() or {}).get(_MEM_KEY)
            if raw:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, list):
                    prev_conversation = [m for m in parsed if isinstance(m, dict) and m.get("role")][-12:]
            _ms = (session.get_extra() or {}).get(_MEM_SUMMARY_KEY)
            if _ms:
                prev_summary = str(_ms)
        except Exception as e:
            logger.warning("orchestrator 记忆恢复失败: %s", e)
    is_new_conversation = not (initial_ctx or {}).get("supplement_text") and not bool(ctx.get("force_complete"))
    if is_new_conversation:
        prev_conversation = []
        prev_summary = ""
    # 结构化记忆（编排配置 memory.fields 可配）：续接轮把上一轮推理摘要作为 system 上下文喂回，
    # 解决"多轮反问后忘记早期确认"——对话文本只作补充，摘要保关键事实。
    mem_cfg = orch_cfg.get("memory") or {}
    if prev_summary and bool(mem_cfg.get("summary_enabled", True)):
        prev_conversation.insert(0, {"role": "system", "content": f"历史推理摘要（上一轮，供续接参考）：\n{prev_summary}"})
    # 续接时原始需求可能已存于历史（assistant 通道每轮从会话取回同一原文）→ 去重，避免"你好"重复
    base_msg = {"role": "user", "content": f"客户需求：{requirement_text}"}
    conversation = list(prev_conversation)
    if not any(isinstance(m, dict) and m.get("content") == base_msg["content"] for m in conversation):
        conversation.append(base_msg)
    ask_rounds = int(ctx.get("clarify_round") or 0)

    # 反答回填（supplement）追加进对话
    if initial_ctx and initial_ctx.get("supplement_text"):
        conversation.append({"role": "user", "content": f"客户补充：{initial_ctx['supplement_text']}"})

    for i in range(40):  # 总循环上限兜底
        # 原则5·计划可观测：每步广播剩余计划 + 预算用量（plan_preview 可配开关）
        bs = _budget_state(_budget_box, orch_cfg, _t0, ask_rounds)
        if bool(orch_cfg.get("plan_preview", True)):
            remaining = [c["key"] for c in capabilities if c["key"] not in done]
            try:
                await broadcast({"type": "plan_progress",
                                 "remaining": remaining,
                                 "remaining_labels": [cap_by_key[c["key"]]["label"] for c in capabilities if c["key"] not in done],
                                 "elapsed_s": bs["elapsed_s"], "budget": bs,
                                 "exhausted": _budget_exhausted(bs)})
            except Exception:
                pass
        if _budget_exhausted(bs) and not ctx.get("_budget_exhausted"):
            ctx["_budget_exhausted"] = True
            try:
                await broadcast({"type": "step_progress", "step": "orchestrator",
                                 "sub": {"kind": "budget",
                                         "text": f"⏱ 已超预算（{bs['elapsed_s']}s/{bs['steps']}步），停止反问与 LLM 决策，按确定性链收敛方案"}})
            except Exception:
                pass
        # 反问后（awaiting_input）暂停等用户补充
        if ctx.get("awaiting_input"):
            await broadcast({"type": "pipeline_paused", "reply_id": ctx.get("last_reply_id")})
            return ctx
        # AI 关 → 目录引导对话（诚实问类型→机型→KP 格式，选项 100% 来自产品目录，不静默猜）。
        # 目录引导走完（stage=done）或用户点跳过（force_complete）才进确定性能力链出方案。
        if ai_off and not bool(ctx.get("force_complete")) and not ctx.get("_retry_mode") \
                and (ctx.get("catalog_stage") or "") != "done":
            # Phase3·诚实降级：AI 不可用 → 明确告知 + 目录手动选型（选项 100% 来自在售目录，零幻觉），
            # 绝不用正则假装理解自由文本。
            try:
                await broadcast({"type": "step_progress", "step": "orchestrator",
                                 "sub": {"kind": "degraded",
                                         "text": "⚠️ AI 引擎暂不可用（网络/额度），以下按手动选型引导，选项均来自在售目录"}})
            except Exception:
                pass
            from app.services.reasoning_executor import _ask_catalog_question
            _la_cfg = node_configs.get("llm_ask") or {}
            if isinstance(_la_cfg.get("ask_user"), dict) and _la_cfg["ask_user"]:
                from app.services.catalog_guide import load_ask_config
                ctx.setdefault("flow_configs", {})["ask_user"] = {
                    **load_ask_config(ctx.get("flow_configs")), **_la_cfg["ask_user"]}
            await _ask_catalog_question(ctx, broadcast, extra_questions=[])
            _persist_conversation(session, _MEM_KEY, conversation)
            _persist_memory_summary(session, _MEM_SUMMARY_KEY, ctx)
            await broadcast({"type": "pipeline_paused", "reply_id": ctx.get("last_reply_id")})
            return ctx
        ready = _ready_capabilities(done, capabilities)
        state = _state_summary(ctx, done, mem_cfg.get("fields"))
        ctx["_memory_summary"] = state if bool(mem_cfg.get("summary_enabled", True)) else ""
        force_complete = bool(ctx.get("force_complete"))
        max_rounds = int((node_configs.get("llm_ask") or {}).get("max_rounds") or 6)
        _b_ask = int((orch_cfg.get("budgets") or {}).get("max_ask_rounds") or 0)
        if _b_ask > 0:
            max_rounds = min(max_rounds, _b_ask)
        if ctx.get("_budget_exhausted"):
            # 超预算：不再问 LLM 决策，直接按就绪顺序线性调能力（确定性收敛，防无限等）
            decision = {"action": "call", "capability": ready[0] if ready else "final"}
            if not ready:
                decision = {"action": "final"}
        elif ctx.get("_retry_mode"):
            _targets = ctx.get("_retry_targets") or set()
            if _targets and _targets <= done:
                # 重跑目标完成 → 退出重跑模式，恢复正常 LLM 编排（审计/修复过程已在对话，可总结/继续）
                ctx["_retry_mode"] = False
                ctx["_retry_targets"] = None
                decision = await _decide_next(state, ready, conversation, ask_rounds,
                                              force_complete=force_complete, max_rounds=max_rounds,
                                              ctx=ctx, capabilities=capabilities)
            else:
                # 重跑链只跑目标能力（LLM 选子集 / 默认全量），跑完即退出，不提前 final
                pending = [k for k in ready if k in _targets] or list(ready)
                decision = {"action": "call", "capability": pending[0] if pending else "final"}
        elif not _needs_llm_decision(ctx, ready):
            # 混合脊柱：信息明确（clarity=explicit）且无异常 → 按拓扑序确定性执行下一步。
            # 不为「下一步」这种确定的事反复调 LLM（省 ~10 次决策 × ~8s）；LLM 只在
            # 信息不足/选型落空/收尾总结 这些真正需要判断的点介入。
            decision = {"action": "call", "capability": ready[0] if ready else "final"}
            if not ready:
                decision = {"action": "final"}
        else:
            decision = await _decide_next(state, ready, conversation, ask_rounds,
                                          force_complete=force_complete, max_rounds=max_rounds,
                                          ctx=ctx, capabilities=capabilities)
        if not decision or not ready:
            # 退化：按顺序调下一个就绪能力（线性链兜底）
            decision = {"action": "call", "capability": ready[0] if ready else "final"}
            if not ready:
                decision = {"action": "final"}

        action = (decision.get("action") or "").strip()

        if action == "ask" and not bool(ctx.get("force_complete")) and ask_rounds < max_rounds \
                and not bool(ctx.get("delegated")) and not bool(ctx.get("_budget_exhausted")):
            # 策略反问：统一走 llm_ask 节点能力（workload 首问 / 分档 / 目录白名单 / why 全部可配），
            # 与 llm_ask 节点一套逻辑，避免编排 agent 与节点两套反问不一致。
            # AI 关或 LLM 生成失败 → 目录引导兜底（选项 100% 来自产品目录，与 llm_ask 节点一致）。
            # 反问轮次达 llm_ask.max_rounds（默认 6）→ 不再反问，直接 call 能力收敛（死循环防护）。
            import uuid
            from app.services.capabilities import run_llm_ask
            # 多轮记忆修正：反问前若理解节点还没跑（续接轮 ctx 是新的，ext/missing 为空），
            # 先跑 understand 把「已理解/缺口」填实——否则 run_llm_ask 看到空 ext，
            # 每轮都会重复问「工作负载」（场景2实测复现）。首问工作负载体验不受影响：
            # "你好/我要买服务器"这类模糊输入理解后 ext 仍为空 → need_workload=True → 仍首问工作负载。
            if "understand" in cap_by_key and "understand" not in done:
                await broadcast({"type": "step_start", "step": "understand",
                                 "label": cap_by_key["understand"]["label"]})
                _u_payload = await _dispatch("understand", ctx, node_configs.get("understand") or {}, broadcast)
                await broadcast({"type": "step_done", "step": "understand", "payload": _u_payload})
                done.add("understand")
                conversation.append({"role": "assistant",
                                     "content": f"完成能力[需求理解]：{json.dumps(_u_payload, ensure_ascii=False)[:400]}"})
            res = await run_llm_ask(ctx, node_configs.get("llm_ask") or {}, broadcast)
            rid = f"orch_{uuid.uuid4().hex[:12]}"
            if res.get("ok"):
                q = res["question"]
                opts = res.get("options") or []
                why = res.get("why") or ""
                await broadcast({"type": "need_input", "reply_id": rid, "question": q,
                                 "options": opts, "why": why,
                                 "missing_fields": ctx.get("missing_fields") or [],
                                 "source": "orchestrator"})
            else:
                # 目录驱动引导兜底（自带 need_input 广播，选项/文案来自产品目录 + ask_user 配置）
                # 先合并 llm_ask 节点抽屉里的 ask_user 子配置（与 llm_ask 节点 dispatch 一致），
                # 否则 load_ask_config 只读到全局默认，用户改的文案/推荐不生效。
                _la_cfg = node_configs.get("llm_ask") or {}
                if isinstance(_la_cfg.get("ask_user"), dict) and _la_cfg["ask_user"]:
                    from app.services.catalog_guide import load_ask_config
                    ctx.setdefault("flow_configs", {})["ask_user"] = {
                        **load_ask_config(ctx.get("flow_configs")), **_la_cfg["ask_user"]}
                from app.services.reasoning_executor import _ask_catalog_question
                fb = await _ask_catalog_question(ctx, broadcast, extra_questions=[])
                rid = ctx.get("last_reply_id") or rid
                q = (fb or {}).get("question") or "请补充更多配置信息"
                opts = []
                why = ""
            ctx["awaiting_input"] = True
            ctx["last_reply_id"] = rid
            ctx["orchestrator"] = {"action": "ask", "reason": decision.get("reason") or ""}
            conversation.append({"role": "assistant", "content": f"反问：{q}"})
            _persist_conversation(session, _MEM_KEY, conversation)
            _persist_memory_summary(session, _MEM_SUMMARY_KEY, ctx)
            await broadcast({"type": "pipeline_paused", "reply_id": rid})
            return ctx

        if action == "final":
            ctx["orchestrator"] = {"action": "final", "summary": decision.get("summary") or ""}
            _persist_conversation(session, _MEM_KEY, conversation)
            _persist_memory_summary(session, _MEM_SUMMARY_KEY, ctx)
            await broadcast({"type": "pipeline_done"})
            return ctx

        # action = call
        cap = (decision.get("capability") or "").strip()
        if cap not in ready:
            cap = ready[0] if ready else None
        if not cap:
            await broadcast({"type": "pipeline_done"})
            return ctx
        # 延迟优化（编排配置 parallel_enabled，默认关）：ready 中其余「确定性」能力与该步并行执行。
        # 安全前提：DAG 保证同时 ready 的确定性能力互不依赖（compose 未完成时 budget 不会 ready）；
        # 链式图一次只一个 ready → 并行零影响；用户自定义分叉图才有收益。
        parallel_caps = [cap]
        if bool(orch_cfg.get("parallel_enabled")) and not ctx.get("_retry_mode"):
            for _c in capabilities:
                if _c["key"] in ready and _c["key"] != cap and _c.get("deterministic"):
                    parallel_caps.append(_c["key"])
            parallel_caps = parallel_caps[: max(1, int(orch_cfg.get("parallel_limit") or 2))]

        import asyncio as _ai

        async def _run_one(k: str) -> tuple:
            lbl = cap_by_key[k]["label"]
            await broadcast({"type": "step_start", "step": k, "label": lbl})
            cfg = _apply_ai_budget(node_configs.get(k) or {}, orch_cfg, cap_by_key[k]["type"])
            pl = await _dispatch(cap_by_key[k]["type"], ctx, cfg, broadcast)
            await broadcast({"type": "step_done", "step": k, "payload": pl})
            _budget_box["steps"] = int(_budget_box.get("steps") or 0) + 1
            if cap_by_key[k]["type"] in ("model_reason", "kp_reason"):
                _budget_box["tools"] = int(_budget_box.get("tools") or 0) + len(pl.get("trace") or [])
            return k, pl

        _results = await _ai.gather(*[_run_one(k) for k in parallel_caps])
        for k, pl in _results:
            done.add(k)
            conversation.append({"role": "assistant",
                                 "content": f"完成能力[{cap_by_key[k]['label']}]：{json.dumps(pl, ensure_ascii=False)[:400]}"})
        cap, payload = _results[0]
        # Phase1（2026-08 改革）：不再路由 extract 规则理解兜底——"AI 失效用正则假装理解"是历史包袱
        # （错误答案比没有答案更糟）。理解失败 → 缺口分析/反问补（诚实降级）；extract 仅画布兼容保留。
        # 方案自检（result_check）失败且配置「自动重跑」→ 触发确定性重跑（compose→budget_check→自检），
        # 复用 v12 自纠回边机制（retry_caps → 下轮确定性重跑，LLM 不可跳过脊梁）。
        if cap_by_key[cap]["type"] == "result_check" and payload.get("failed") and payload.get("on_fail") == "retry":
            ctx["retry_caps"] = ["compose", "budget_check", cap]
        # v12 自纠回边：节点请求重跑链（spec_compliance 补卡 / budget_check 降配 / audit_fix 自纠）。
        # 把对应能力从 done 移除，并进入确定性重跑模式（下轮起按就绪顺序跑完重试目标，不再问 LLM，
        # 防编排 agent 在重跑链未走完时提前 final；每次重跑都有计数上限，不会死循环）。
        if ctx.get("retry_caps"):
            retry_caps = list(ctx.get("retry_caps") or [])
            for _rc in retry_caps:
                done.discard(_rc)
            # C：审计意见喂回编排 agent——LLM 决定可选重跑项（再审/再自纠 要不要），
            # 重建脊梁强制保留；AI 关/LLM 失败 → 全量重跑（现状兜底）。防提前 final 的
            # 确定性保证由 _retry_mode「只跑目标、跑完才退」守住，不受 LLM 影响。
            targets = await _decide_retry_targets(ctx, retry_caps)
            ctx["_retry_mode"] = True
            ctx["_retry_targets"] = set(targets or retry_caps)
            ctx["retry_caps"] = None
        # 反问（understand/llm_ask 设了 awaiting_input）→ 暂停
        if ctx.get("awaiting_input"):
            await broadcast({"type": "pipeline_paused", "reply_id": ctx.get("last_reply_id")})
            return ctx

    # 超限兜底
    _persist_conversation(session, _MEM_KEY, conversation)
    _persist_memory_summary(session, _MEM_SUMMARY_KEY, ctx)
    await broadcast({"type": "pipeline_done"})
    return ctx


def _persist_memory_summary(session, key: str, ctx: dict) -> None:
    """持久化结构化记忆摘要（跨轮续接用）。失败静默。"""
    if session is None:
        return
    try:
        summary = ctx.get("_memory_summary") or ""
        if summary:
            session.update_meta({key: summary})
    except Exception as e:
        logger.warning("orchestrator 记忆摘要保存失败: %s", e)


def _persist_conversation(session, key: str, conversation: list) -> None:
    """保存对话记忆到会话。失败静默。

    优先保留用户消息（需求/补充——编排 agent 决策依据），能力完成记录只留最近 4 条；
    总上限 24 条防 DB 膨胀。避免"完成能力"刷屏把用户说的话挤出窗口。
    """
    if session is None:
        return
    try:
        items = [m for m in conversation if isinstance(m, dict)]
        users = [m for m in items if m.get("role") == "user"]
        assts = [m for m in items if m.get("role") != "user"][-4:]
        recent = (users + assts)[-24:]
        session.update_meta({key: json.dumps(recent, ensure_ascii=False)})
    except Exception as e:
        logger.warning("orchestrator 记忆保存失败: %s", e)
