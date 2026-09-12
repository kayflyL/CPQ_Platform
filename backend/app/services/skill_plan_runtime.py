# -*- coding: utf-8 -*-
"""需求分析 Skill 的硬编排引擎（skill plan runtime）。

两器官架构（2026-08-28 宪法；2026-09-02 修订登记环节）：
- 引擎没有对话能力。它接收登记表（大脑节点回合落表或调用方结构化直填），产出**产物**（BOM 方案）或
  **缺口数据**（{slot, options, reason_code} 列表）；"怎么向用户要"属于 AI 角色，不属于这里。
- 阶段顺序由代码固定：normalize → model → kp_gate → kp → compose → output；
- 本模块不 import agent_react / llm_client；引擎本体任何位置都不发起 LLM。
  agent_fill 登记节点是唯一例外形态：通过注入的 brain 回调执行唯一大脑的显式回合
  （同一条流式循环、同一个人设、调 fill_requirement 落表），没有第二次隐藏推理；
  点选/脚本直填的场合传 skip_fill_round/slots_provided 跳过，登记完全确定性；
- 对前端广播 pipeline_start / node_trace(真实产物+真实耗时) / pipeline_paused。
"""
from __future__ import annotations

import logging
import time
import asyncio
from typing import Any, Awaitable, Callable, Optional

from app.services.capability_spec import mechanism_tools_map
from app.services.skill_node_runtime import compose_plans, finalize_output
from app.services.skill_node_state import KP_ABSENT, kp_state, waived_categories

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]

PHASE_TABLE = [
    {"key": "input", "label": "需求接收"},
    {"key": "agent_fill", "label": "需求理解填表"},
    {"key": "model_reason", "label": "机型选型"},
    {"key": "kp_reason", "label": "配件选型"},
    {"key": "compose", "label": "BOM 组装"},
    {"key": "output", "label": "产出交接"},
]

# 对客户有意义的里程碑阶段（input/agent_fill 在对话里自然发生，不出现在流程预告里）
USER_FACING_PHASES = {"model_reason", "kp_reason", "compose", "output"}


def skill_steps_view(flow_configs: dict, user_facing_only: bool = False) -> list[dict]:
    """步骤清单单源：角色提议话术与 pipeline_start 共用，画布改 label/description 两处同步变。"""
    steps = []
    for ph in PHASE_TABLE:
        if user_facing_only and ph["key"] not in USER_FACING_PHASES:
            continue
        cfg = flow_configs.get(ph["key"]) if isinstance(flow_configs.get(ph["key"]), dict) else {}
        item = {"step": ph["key"], "label": str((cfg or {}).get("label") or ph["label"])}
        desc = str((cfg or {}).get("description") or "").strip()
        if desc:
            item["description"] = desc
        steps.append(item)
    return steps


def _graph_maps(flow: dict) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, int], dict[str, int]]:
    """画布 graph JSON → (nodes, adj, indeg, order)；extract 节点不进执行序。"""
    graph = flow.get("graph") or {}
    nodes: dict[str, dict] = {}
    order: dict[str, int] = {}
    for index, node in enumerate(graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        runtime = node.get("runtime") or node.get("type")
        if not nid or runtime == "extract":
            continue
        nodes[str(nid)] = node
        order[str(nid)] = index
    adj: dict[str, list[dict]] = {nid: [] for nid in nodes}
    indeg: dict[str, int] = {nid: 0 for nid in nodes}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in nodes and target in nodes:
            adj[source].append(edge)
            indeg[target] = indeg.get(target, 0) + 1
    return nodes, adj, indeg, order


async def _emit(broadcast: BroadcastFn, payload: dict) -> None:
    if broadcast is None:
        return
    try:
        await broadcast(payload)
    except Exception:
        logger.exception("skill engine broadcast failed type=%s", payload.get("type"))


# 节点机制工具白名单：唯一真源 = capability_spec（节点能力声明），此处只做投影，
# 不另存一份清单。enabled_tools（DB）是工具集真源，这里只在配置漂移缺机制工具时
# 保底补回并告警。
MECHANISM_TOOLS = mechanism_tools_map()


def effective_node_tools(node_key: str, node_cfg: dict) -> list:
    """节点实际可用工具 = DB enabled_tools ∪ 机制保底（单一口径，渲染器与执行器共用）。"""
    from app.services.tool_names import normalize_tool_ids
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    bound = normalize_tool_ids(cfg.get("enabled_tools") or [])
    mechs = MECHANISM_TOOLS.get(node_key) or []
    missing = [m for m in mechs if m not in bound]
    if missing:
        logger.warning("%s enabled_tools 缺机制工具 %s（DB 配置漂移，保底补回）", node_key, missing)
    return list(dict.fromkeys(bound + mechs))


def steps_payload(flow: dict) -> list[dict]:
    """节点抽屉 → 结构化步骤清单（原样数据，无文本加工；顺序=图拓扑序号）。

    编排权移交后大脑的任务卡就是这份清单：AI 角色直接读节点配置。
    曾有 render_skill_manual 把它转译成散文说明书——被定调为黑盒转译层删除：
    模型读结构化清单毫无障碍，转译只会引入用户看不见的加工逻辑。"""
    flow_configs = flow.get("node_configs") if isinstance(flow.get("node_configs"), dict) else {}
    nodes, adj, indeg, order = _graph_maps(flow)
    topo: list[str] = []
    ready = sorted([k for k, d in indeg.items() if d == 0], key=lambda k: order.get(k, 0))
    indeg_work = dict(indeg)
    while ready:
        k = ready.pop(0)
        topo.append(k)
        for edge in adj.get(k) or []:
            t = str(edge.get("target") or "")
            if t in indeg_work:
                indeg_work[t] -= 1
                if indeg_work[t] == 0:
                    ready.append(t)
        ready.sort(key=lambda k: order.get(k, 0))
    for k in indeg_work:
        if indeg_work[k] > 0 and k not in topo:
            topo.append(k)
    node_label = {str(nd.get("id") or ""): str(nd.get("label") or "")
                  for nd in (flow.get("graph") or {}).get("nodes") or [] if isinstance(nd, dict)}
    from app.services.skill_node_plugins import plugin_for
    steps: list[dict] = []
    for key in topo:
        cfg = flow_configs.get(key) if isinstance(flow_configs.get(key), dict) else {}
        tools = effective_node_tools(key, cfg)
        if not tools:
            continue
        # 产物输出契约由该节点插件声明（默认取抽屉 target.artifacts；登记节点由目标层生成）——
        # 编排壳不再按节点 key 分支。
        contract = plugin_for(key).artifact_contract(cfg)
        steps.append({
            "step": key,
            "label": node_label.get(key) or str((cfg or {}).get("label") or key),
            "order": len(steps) + 1,
            "tools": tools,
            "artifact": contract or "",
        })
    return steps


def _node_cfg(ctx: dict, key: str) -> dict:
    cfg = (ctx.get("flow_configs") or {}).get(key)
    return dict(cfg) if isinstance(cfg, dict) else {}


def _artifact_field_ask(node_cfg: dict, field_key: str) -> bool:
    """目标层字段策略：字段「必填」开关（是否反问由运行时判定，见节点说明）。

    读取位置（2026-09-06 起）：contract.columns[].ask（插头契约针脚，权威）；
    兼容旧 fields[].ask。ask=true → 大脑不代选，选择权直接交给客户
    （引擎弹机型选项卡/保持占位行）；缺省/未配置 → 大脑可从候选池自行选定。
    """
    try:
        from app.services.skill_target_contract import target_artifacts
        arts = target_artifacts(node_cfg)
        art = (arts[0] if arts else {}) or {}
        for coll in (art.get("contract", {}).get("columns") if isinstance(art.get("contract"), dict) else None,
                     art.get("columns"), art.get("fields")):
            for f in (coll or []):
                if isinstance(f, dict) and str(f.get("key") or "") == field_key and bool(f.get("ask")):
                    return True
        return False
    except Exception:
        return False


def _model_field_ask(node_cfg: dict) -> bool:
    """机型选配目标层字段策略：server_model 的「必填」开关（见 _artifact_field_ask）。"""
    return _artifact_field_ask(node_cfg, "server_model")


def _ask_option_signal(row_key: str, o: dict, category: str = "") -> dict:
    """大脑确认卡选项 → 点击信号。

    推荐/候选选项带 pick（服务端候选料号）→ 直接写 kp_manual_pick 落地真实料号；
    absent=True → 该行类目按「不配」登记 kp_absent（GPU 逃生）；waived=True → 该行按
    「库内无料、客户已知悉仍保持原需求」登记 kp_waived（行保留 + 标注，终检放行）；
    否则文本并入该行描述（kp_row_merge，下一轮大脑再消化）。一律不出现「按缺配继续」。"""
    pk = o.get("pick")
    if isinstance(pk, dict) and str(pk.get("name") or "").strip():
        return {"kp_manual_pick": {"row": row_key, **{k: v for k, v in pk.items()
                                                     if k in ("part_id", "name", "price", "currency",
                                                              "qty", "substitute")}}}
    if o.get("absent"):
        _ab = o.get("absent")
        cat = _ab.strip() if isinstance(_ab, str) else ""
        if not cat:
            # 行引用是引擎铸造的身份（row_id）时文本里没有类目：由调用方按身份给出（不猜文本）
            cat = str(category or "").strip()
        if not cat and "|" in str(row_key or ""):
            cat = str(row_key).split("|", 1)[0].strip()  # 旧数据兼容：复合行键
        return {"kp_absent": [cat]} if cat else {}
    if o.get("waived"):
        wv = o.get("waived")
        rk = row_key or (wv.strip() if isinstance(wv, str) else "")
        return {"kp_waived": [rk]} if rk else {}
    if row_key:
        return {"kp_row_merge": {"row": row_key, "answer": str(o.get("label") or "")}}
    return {}


def ask_option_signal(row_key: str, o: dict, ask_slot: str = "", category: str = "") -> dict:
    """选项卡选项 → 点击信号（唯一出口：卡怎么发射，信号就怎么解释）。

    两种卡共用这一条口径：
      * 行卡（row_key 非空）：pick=落地料号 / absent=类目不配 / waived=行豁免 / 否则并入行回答；
      * 登记表字段确认卡（选项声明 slot+value）：点选即把该字段登记为 value，并记为「客户已确认」
        （value 是落库值，label 只是给客户看的文案——没给 value 就不绑字段，答案走对话）。
    """
    if row_key:
        return _ask_option_signal(row_key, o, category=category)
    slot = str(o.get("slot") or ask_slot or "").strip()
    val = str(o.get("value") or "").strip()
    if slot and val:
        from app.services.slot_contract import canonical_key, slot_spec
        try:
            # 只认**线索登记表字段**（非部件槽）：点选确认的是登记字段，不是部件行。
            keys = {str(s.get("key") or "") for s in slot_spec()
                    if str(s.get("src_type") or "") != "kp"}
        except Exception:
            keys = set()
        if slot in keys:
            return {canonical_key(slot): val}
    # slot 不是登记表字段（如大脑提问卡兜底的 slot brain_ask）＝客户的一次口头回答，
    # 不是字段信号：绝不凭它往登记表里写一个不存在的键。
    return {}


def _row_qty_hint(category: str, row_desc: str, row_qty: int, pool_candidates: list) -> dict:
    """数量建议（纯算术）：从候选 specs 的 Capacity（库内字段）找最大单条容量，若行描述
    含总容量则反推建议件数（如 768GB ÷ 32G = 24）；算不出 → 行数量。不做语义判断。"""
    from app.services.part_selector import _gb_of
    total = float(_gb_of(row_desc) or 0)
    unit = 0
    for c in pool_candidates or []:
        specs = c.get("specs") if isinstance(c.get("specs"), dict) else {}
        u = _gb_of(specs.get("Capacity"))
        if u:
            unit = max(unit, u)
    if total > 0 and unit > 0:
        suggest = max(1, -(-int(total) // int(unit)))
        return {"qty": max(1, row_qty), "qty_max": suggest * 2, "suggested_qty": suggest}
    return {"qty": max(1, row_qty), "qty_max": max(1, row_qty), "suggested_qty": 0}



def _trace(key: str, label: str, status: str, **extra) -> dict:
    payload = {"type": "node_trace", "step": key, "label": label, "status": status,
               "input": extra.get("input"), "output": extra.get("output"),
               "summary": extra.get("summary") or "", "artifact": extra.get("artifact")}
    if extra.get("duration_ms") is not None:
        payload["duration_ms"] = extra["duration_ms"]
    return payload


async def _emit_requirement_fill(ctx: dict, broadcast: BroadcastFn, label: str, started: float, text: str = "") -> None:
    """把已理解的线索登记表按「一个字段 → 一个事件」推给前端，实现逐项填充体感。

    仍是一次抽取（不增加 LLM 调用），只是把结果拆成多条 node_trace 增量广播：
    基本信息逐字段亮起，随后部件逐件累加，最后一条保留原「线索登记表已更新」终态，
    供画布节点徽标/摘要收口。缺口路径同样先推送已填字段，再交 gap 转述。
    """
    from app.services.portal_flow_adapter import requirement_slots_from_ext
    from app.services.slot_contract import slot_label
    slots = requirement_slots_from_ext(dict(ctx.get("ext") or {}))
    basic_order = ("server_type", "platform_type", "chassis_form", "server_model",
                   "purchase_qty", "warranty_years")
    rows = list(slots.get("kp_rows") or [])

    def snapshot(base: dict, rows_part: list) -> dict:
        data: dict = dict(base)
        if rows_part:
            data["kp_rows"] = list(rows_part)
        data["requirement_text"] = str(text or "")
        return data

    seq: list[tuple[str, dict]] = []
    seen: dict = {}
    for k in basic_order:
        v = slots.get(k)
        if v is None or v == "" or v == [] or v == {}:
            continue
        seen[k] = v
        seq.append(("基本信息·" + slot_label(k), snapshot(dict(seen), [])))
    acc: list = []
    for i, r in enumerate(rows):
        acc.append(r)
        seq.append(("部件 " + str(i + 1), snapshot(dict(seen), list(acc))))
    if not seq:
        seq.append(("线索登记表", snapshot(dict(seen), [])))

    total = len(seq)
    for idx, (group, data) in enumerate(seq):
        is_last = idx == total - 1
        await _emit(broadcast, _trace(
            "agent_fill", label, "running",
            output={"missing_critical": list(ctx.get("blockers") or [])},
            summary=("线索登记表已更新" if is_last else "登记" + group),
            artifact={"kind": "requirement_slots", "title": "线索登记表", "data": data},
            duration_ms=(round((time.perf_counter() - started) * 1000) if is_last else None)))
        if not is_last and broadcast is not None:
            await asyncio.sleep(0.04)


def pause_payload(*, kind: str, step: str = "", label: str = "", reason_code: str = "",
                  pending: Optional[list] = None, resumable: bool = True,
                  steps_done: Optional[list] = None) -> dict:
    """暂停载荷对象（P4-1 唯一工厂）：为什么停 / 停在哪 / 待办是什么 / 恢复要什么。

    只有事实与原因码，没有话术；所有暂停点（缺配提问、待办卡、终检不过、本步零产出、
    回合硬超时）都用这一份形状，下游不需要再各拼一半。
    """
    return {
        "kind": str(kind or ""),
        "step": str(step or ""),
        "label": str(label or ""),
        "reason_code": str(reason_code or kind or ""),
        "pending": [dict(p) for p in (pending or []) if isinstance(p, dict)],
        "resumable": bool(resumable),
        "at": time.time(),
        "resume": {"steps_done": sorted(str(s) for s in (steps_done or [])),
                   "awaiting": "user_input" if resumable else "aborted"},
    }


def engine_result_of(ctx: dict) -> dict:
    """引擎终态协议：done（含产物）/ gaps（结构化缺口数据，无话术）/ failed（本步零产出）。

    pause：暂停载荷对象（P4-1，engine.engine_pause）——中断点/原因码/待办/恢复所需最小状态，
    有暂停才有此键，随终态一起交回上层与看板。
    """
    _pause = dict(ctx.get("engine_pause") or {}) or None
    if ctx.get("engine_failure"):
        return {"status": "failed", "failure": dict(ctx.get("engine_failure") or {}),
                "pause": _pause}
    gaps = list(ctx.get("engine_gaps") or [])
    if gaps:
        return {"status": "gaps", "gaps": gaps, "pause": _pause,
                "assumptions": list(ctx.get("assumptions") or [])}
    return {"status": "done",
            "artifact": (ctx.get("business_entity") or {}).get("entity"),
            "payload": ctx.get("output_payload") or {},
            "assumptions": list(ctx.get("assumptions") or [])}


def compact_candidate(candidate: dict) -> dict:
    return {
        "id": str(candidate.get("server_model_id") or candidate.get("id") or ""),
        "name": str(candidate.get("name") or ""),
        "type": str(candidate.get("server_type_name") or ""),
        "series": str(candidate.get("series") or ""),
        "form": str(candidate.get("form") or ""),
        "price": candidate.get("total_price"),
    }


# ── 编排权移交支撑（2026-09-07）：大脑读说明书自己走步骤，引擎只做
# 每步自动预处理挂载 / 自动完成校验 / 终检 + 组装。不决策、不编排。──

async def prepare_step(ctx: dict, key: str, broadcast: BroadcastFn = None) -> dict:
    """每步开始前的确定性预处理：由该节点插件提供（skill_node_plugins）。

    编排壳不认识任何节点——新增节点 = 注册一个插件（换插头），本函数零改动。
    """
    from app.services.skill_node_plugins import plugin_for
    flow_configs = ctx.get("flow_configs") or {}
    cfg = flow_configs.get(key) if isinstance(flow_configs.get(key), dict) else {}
    return await plugin_for(key).prepare(ctx, cfg, broadcast)


async def validate_step_end(ctx: dict, key: str) -> dict:
    """每步完成前的确定性校验：该步产物在不在。由节点插件提供（未注册节点默认通过）。

    校验失败 = 该步没干完：引擎回喂 hint 逼大脑补做（调工具或 ask_user），不标 done，
    绝不把机制文案直接抛给客户。
    """
    from app.services.skill_node_plugins import plugin_for
    return await plugin_for(key).validate(ctx)


async def _refresh_kp_state(ctx: dict) -> None:
    """（兼容别名）刷新 kp 占位/落地行表；实现已迁到节点插件注册表。"""
    from app.services.skill_node_plugins import refresh_kp_state
    await refresh_kp_state(ctx)


def final_gate(ctx: dict, composing: bool = False) -> dict:
    """终检（P3）：没干完不许报完成。确定性核对，任一失败 → 拦截 + 如实原因。"""
    ext = ctx.get("ext") or {}
    locked = (ctx.get("_locked_baseline") or {}).get("name")
    if not locked and not str((ext.get("server_model") or "")).strip():
        return {"ok": False, "hint": "机型未锁定，不能交付——先完成机型选型"}
    summary = dict(ctx.get("kp_summary") or {})
    if composing:
        unmatched = int(summary.get("unmatched_count") or 0)
        if unmatched > 0:
            # 点名列（不点名的话大脑不知道该补哪一行，也学不到「保持原需求」这条出路）。
            rows = [f"{str(r.get('category') or '')}"
                    + (f"（{str(r.get('request_spec') or '').strip()}）" if str(r.get("request_spec") or "").strip() else "")
                    for r in (ctx.get("kp_parts") or [])
                    if isinstance(r, dict) and r.get("unmatched")]
            return {"ok": False,
                    "hint": f"仍有 {unmatched} 行配件未落地（{'、'.join(rows[:6])}）：组装被挡住，该行还没有终局（已锁定／客户放弃 absent／客户已知悉库内无料仍保持原需求 waived=true）"}
    # 登记行 vs 落地行核对（丢行拦截）：登记的每个部件大类都要有对应落地行。
    # 一条登记行的终局只有三种（见 skill_node_state.KP_WAIVED），三种都算已了结：
    # 已锁定真实料号 / 客户明确放弃（absent）/ 客户已知悉库内无料仍保持原需求（waived）。
    reg_cats = {str(r.get("part_category") or "").strip()
                for r in (ext.get("kp_rows") or []) if isinstance(r, dict) and str(r.get("part_category") or "").strip()}
    absent = {str(c).strip() for c in (kp_state(ctx).get(KP_ABSENT) or []) if str(c).strip()}
    settled = absent | waived_categories(ctx)
    landed_cats = {str(r.get("category") or "").strip()
                   for r in (ctx.get("kp_parts") or [])
                   if isinstance(r, dict) and not r.get("unmatched") and not r.get("waived")}
    missing = sorted(c for c in reg_cats - landed_cats - settled if c)
    if missing:
        return {"ok": False, "hint": f"登记的部件大类 [{'、'.join(missing)}] 没有对应落地行：该行还没有终局（已锁定／客户放弃 absent／客户已知悉库内无料仍保持原需求 waived=true）"}
    return {"ok": True}


async def run_compose(ctx: dict, broadcast: BroadcastFn = None) -> dict:
    """组装（compose 步骤的确定性执行）：刷新 kp 状态 → 终检 → compose_plans。"""
    await _refresh_kp_state(ctx)  # 先把大脑提交的 kp_picks 落进行表，再做终检
    gate = final_gate(ctx, composing=True)
    if not gate.get("ok"):
        return gate
    flow_configs = ctx.get("flow_configs") or {}
    cfg = flow_configs.get("compose") if isinstance(flow_configs.get("compose"), dict) else {}
    await compose_plans(ctx, cfg, broadcast)
    if not ctx.get("plans"):
        return {"ok": False, "hint": "无可组装的整机基准（机型基准数据缺失）"}
    return {"ok": True, "plans": len(ctx.get("plans") or [])}


