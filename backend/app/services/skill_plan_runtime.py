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
from typing import Any, Awaitable, Callable

from app.services.skill_node_runtime import compose_plans, finalize_output

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


def _node_cfg(ctx: dict, key: str) -> dict:
    cfg = (ctx.get("flow_configs") or {}).get(key)
    return dict(cfg) if isinstance(cfg, dict) else {}


def _artifact_field_ask(node_cfg: dict, field_key: str) -> bool:
    """目标层字段策略：字段「AI 反问」开关。

    读取位置（2026-09-06 起）：contract.columns[].ask（插头契约针脚，权威）；
    兼容旧 fields[].ask。ask=true → 大脑不代选，选择权直接交给客户
    （引擎弹机型选项卡/保持占位行）；缺省/未配置 → 大脑可从候选池自行选定。
    """
    try:
        arts = ((node_cfg or {}).get("target") or {}).get("artifacts") or []
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
    """机型选配目标层字段策略：server_model 的「AI 反问」开关（见 _artifact_field_ask）。"""
    return _artifact_field_ask(node_cfg, "server_model")


def _ask_option_signal(row_key: str, o: dict) -> dict:
    """大脑确认卡选项 → 点击信号。

    推荐/候选选项带 pick（服务端候选料号）→ 直接写 kp_manual_pick 落地真实料号；
    absent=True → 该行类目按「不配」登记 kp_absent（GPU 逃生）；否则文本并入该行描述
    （kp_row_merge，下一轮大脑再消化）。一律不出现「按缺配继续」。"""
    pk = o.get("pick")
    if isinstance(pk, dict) and str(pk.get("name") or "").strip():
        return {"kp_manual_pick": {"row": row_key, **{k: v for k, v in pk.items()
                                                     if k in ("part_id", "name", "price", "currency",
                                                              "qty", "substitute")}}}
    if o.get("absent"):
        cat = str(o.get("absent") or "").strip()
        if not cat and row_key and "|" in row_key:
            cat = row_key.split("|", 1)[0].strip()
        return {"kp_absent": [cat] if cat else []}
    if row_key:
        return {"kp_row_merge": {"row": row_key, "answer": str(o.get("label") or "")}}
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


async def brain_with_cap(key_: str, coro):
    """大脑回合硬上限（2026-09-06）：relay 流式连接可能黑洞（有连接、无数据、也不断开）。

    放弃式（abandon）而非 wait_for：黑洞连接上连"取消完成"都可能被 httpx 清理拖死
    （wait_for 要等任务响应取消才能返回）。这里到点 cancel 后【不等待回收】直接返回，
    僵尸任务自生自灭；大脑的全部效果都是对 ctx/ext 的原地变异，主流程立刻继续
    （未选定行白盒呈现/硬门征询），绝不无限静默。"""
    task = asyncio.ensure_future(coro)
    done, pending = await asyncio.wait({task}, timeout=420.0)
    if pending:
        task.cancel()
        logger.error("大脑回合 %s 超过 300s 硬上限，弃置任务（不等待回收），"
                     "未完成部分白盒呈现", key_)


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
            "agent_fill", label, "done",
            output={"missing_critical": list(ctx.get("blockers") or [])},
            summary=("线索登记表已更新" if is_last else "登记" + group),
            artifact={"kind": "requirement_slots", "title": "线索登记表", "data": data},
            duration_ms=(round((time.perf_counter() - started) * 1000) if is_last else None)))
        if not is_last and broadcast is not None:
            await asyncio.sleep(0.04)


def engine_result_of(ctx: dict) -> dict:
    """引擎终态协议：done（含产物）或 gaps（结构化缺口数据，无话术）。"""
    gaps = list(ctx.get("engine_gaps") or [])
    if gaps:
        return {"status": "gaps", "gaps": gaps, "assumptions": list(ctx.get("assumptions") or [])}
    return {"status": "done",
            "artifact": (ctx.get("business_entity") or {}).get("entity"),
            "payload": ctx.get("output_payload") or {},
            "assumptions": list(ctx.get("assumptions") or [])}


async def run_skill_plan_core(ctx: dict, flow_configs: dict, broadcast: BroadcastFn, title: str = "",
                              brain=None) -> dict:
    """引擎唯一入口。ctx 契约：requirement_text/ext/history/force_complete/llm_model/business_mode/output_kind/flow_configs。
    返回 ctx：engine_result=done|gaps；awaiting_input=True 表示有缺口待角色补齐。
    title：任务名（前端任务胶囊展示），缺省「配置任务」。
    brain：可选大脑回调 brain(node_key, node_cfg, ctx)——agent_fill 登记节点用它执行
    唯一大脑回合（显式落表，无隐藏 LLM）。调用方已结构化落槽时可传 skip_fill_round=True
    或 slots_provided=True 跳过登记回合；两者皆无且缺 brain → 白盒报错，绝不静默兜底。
    """
    from app.services.skill_phases import (
        kp_args_from_ext,
        kp_gate_gap,
        kp_mode_gap,
        kp_required_missing,
        phase_kp_reason,
        phase_model_reason,
        phase_normalize_slots,
    )

    ctx["flow_configs"] = flow_configs
    steps_meta = skill_steps_view(flow_configs)
    labels = {s["step"]: s["label"] for s in steps_meta}
    await _emit(broadcast, {"type": "pipeline_start", "title": str(title or "配置任务"), "steps": steps_meta})

    timings = ctx.setdefault("timings", {})
    t0 = time.perf_counter()

    def _fail(step: str, message: str) -> dict:
        ctx["fatal_error"] = message[:200]
        _emit_sync(broadcast, _trace(step, labels.get(step, step), "failed", summary=str(message)[:120]))
        _emit_sync(broadcast, {"type": "error", "message": ctx["fatal_error"]})
        return ctx

    def _pause_with_gaps(step: str, gaps) -> dict:
        items = list(gaps) if isinstance(gaps, list) else [gaps]
        ctx["engine_gaps"] = items
        ctx["awaiting_input"] = True
        timings["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
        # 节点终态：暂停路径也要把当前 step 置为 paused，否则前端节点永远停在 running 转圈
        _emit_sync(broadcast, _trace(step, labels.get(step, step), "paused", summary="等待补充信息"))
        _emit_sync(broadcast, {"type": "pipeline_paused", "gaps": items})
        return ctx

    def _emit_sync(broadcast_, payload):
        # 同步包装：失败/暂停路径里也要发事件（异常仅记日志）。
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_emit(broadcast_, payload))
        except RuntimeError:
            pass

    # ── input ──
    text = str(ctx.get("requirement_text") or "").strip()
    await _emit(broadcast, _trace("input", labels["input"], "running"))
    if not text:
        return _fail("input", "缺少需求文本")
    await _emit(broadcast, _trace("input", labels["input"], "done", input=text, output=text,
                                  summary="已接收需求原文", duration_ms=0))

    # ── agent_fill（登记节点：唯一大脑显式回合落表 → 确定性规范化校验）──
    key = "agent_fill"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    try:
        started = time.perf_counter()
        fill_cfg = _node_cfg(ctx, key)
        if ctx.get("slots_provided") or ctx.get("skip_fill_round"):
            # 调用方已结构化落槽（点选快速路/脚本直填）：跳过登记回合，纯确定性规范化
            ctx["fill_source"] = "structured_direct"
        elif brain is not None:
            # 唯一大脑在登记节点显式落表（同一条流式循环，无隐藏二次 LLM）
            ctx["fill_source"] = "brain_node_round"
            await brain_with_cap(key, brain(key, fill_cfg, ctx))
        else:
            raise RuntimeError("登记节点缺少大脑回调（brain）：拒绝隐身 LLM，也不接受空槽直跑")
        gaps_l0 = await phase_normalize_slots(ctx, fill_cfg, broadcast)
        # 逐项填充体感：分段把登记表推给前端（不增加 LLM 调用）
        await _emit_requirement_fill(ctx, broadcast, labels[key], started, text)
        if gaps_l0:
            # 目标层反问（缺 L0 字段 → 缺口数据）：必须显式暂停，缺口曾被静默丢弃（09-03 修复）。
            # S1 一次问全：全部 L0 缺口同轮交上层批量弹卡。
            return _pause_with_gaps("agent_fill", gaps_l0)
    except Exception as exc:
        logger.exception("normalize 阶段失败")
        return _fail(key, f"需求理解阶段失败：{exc}")

    # ── model（机型选型）──
    key = "model_reason"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    try:
        started = time.perf_counter()
        m_cfg = _node_cfg(ctx, key)
        gap = await phase_model_reason(ctx, m_cfg, broadcast)
        # 机型大脑回合（统一大脑按节点执行）：多候选未锁定 → AI 角色从引擎候选池
        # 选定（select_model 任务期工具接地，池外型号一律拒绝），选定后重跑确定性
        # 阶段校验锁定并携带 AI 理由。目标层策略 server_model.ask=true 时不进大脑——
        # 选择权直接交给客户（弹机型选项卡）；大脑不调用工具（无法决断）→ 同样弹卡。
        if (gap is not None and str(gap.get("reason_code") or "") == "model_candidates"
                and brain is not None and not _model_field_ask(m_cfg)):
            await brain_with_cap(key, brain(key, m_cfg, ctx))
            if ctx.get("model_pick"):
                # 白盒断言：工具声称选定 → 表里必须真有（任何静默丢失在这里响亮报错）
                from app.services.slot_contract import canonical_get
                pick_name = str((ctx.get("model_pick") or {}).get("name") or "").strip()
                got_name = str(canonical_get(ctx.get("ext") or {}, "server_model") or "").strip()
                if pick_name and got_name != pick_name:
                    logger.error("机型大脑已选定 %s 但 ext.server_model=%r（写入丢失，检查 _TOOL_CTX ext 绑定）",
                                 pick_name, got_name)
                gap = await phase_model_reason(ctx, m_cfg, broadcast)
                pick_reason = str(ctx.get("model_pick_reason") or "").strip()
                if pick_reason:
                    ctx["lock_reason"] = pick_reason
        chosen = str(((ctx.get("_locked_baseline") or {}).get("name")) or "")
        pool = [compact_candidate(b) for b in (ctx.get("baselines_pool") or [])][:10]
        from app.repository.bom_case_repo import _l6_rows_from_base_config
        _base = dict(ctx.get("_locked_baseline") or {})
        base_id = _base.get("id")
        # 目标层定义（节点配置 target.artifacts）驱动产物形状：列 = 定义可见列，行来源 = 模板求值
        _t = (m_cfg.get("target") or {})
        _art = ((_t.get("artifacts") or []) or [{}])[0]
        cols_spec = [c for c in (_art.get("columns") or []) if c.get("visible", True)]
        col_keys = [str(c.get("key") or "") for c in cols_spec] or ["catalogue", "description", "qty"]
        # 机箱表 = 基础机箱 L6（该机型 BOM 模板空信号求值，与方案配置页 L6 同源同形状）。
        # 领域规则（切记）：配件选配 + 策略中心选型规则在 BOM 组装阶段会调整 L6——
        # 这里只是骨架预览，最终 L6 以组装节点（apply_plan_selection_rules + eval）为准。
        l6_rows: list = []
        l6_source = "基准配置行"
        if _base.get("bom_template_id") and base_id:
            try:
                from app.services.bom_template_eval import eval_l6_rows
                l6_rows = eval_l6_rows(int(_base["bom_template_id"]), int(base_id), [], {}) or []
                l6_source = "BOM 模板求值 · 基础机箱"
            except Exception:
                logger.exception("机箱表模板求值失败，回退基准配置行")
        if not l6_rows:
            l6_rows = _l6_rows_from_base_config(base_id) if base_id else []
        l6_rows = [{k: r.get(k) for k in col_keys} for r in l6_rows]
        await _emit(broadcast, _trace(
            key, labels[key], "done",
            output={"chosen": chosen, "reason": ctx.get("lock_reason") or "",
                    "matches": ([{"name": chosen}] if chosen else []),
                    **({"source": "llm"} if ctx.get("model_pick") else {})},
            summary=(f"锁定机型 {chosen}" if chosen else "未锁定机型"),
            artifact={"kind": "l6_chassis", "title": "机箱表（基础配置）",
                      "data": {"rows": l6_rows, "chosen": chosen, "reason": ctx.get("lock_reason") or "",
                               "candidates": pool, "source": l6_source,
                               "note": "基础机箱：配件选配与选型规则调整后，L6 配置在 BOM 组装阶段会随之变化"}},
            duration_ms=round((time.perf_counter() - started) * 1000)))
    except Exception as exc:
        logger.exception("model 阶段失败")
        return _fail(key, f"机型选型阶段失败：{exc}")
    if gap is not None:
        return _pause_with_gaps("model_reason", gap)

    # ── kp gate（配件意向缺口，业务选项数据）──
    key = "kp_reason"
    if not bool(ctx.get("force_complete")):
        gate_gap = kp_gate_gap(ctx)
        if gate_gap is not None:
            return _pause_with_gaps("kp_reason", gate_gap)
        # 必登记部件（must_ask）不再在此前置闸门拦截：phase_kp_reason 已把 must_ask 类目
        # 落为未匹配占位行，由集成在 kp 落地后的确定性确认卡逐类向客户确认（B 项修复：
        # 旧版开放回答空选项卡会在大脑前就拦截，缺一类就卡一类且无限循环）。
    else:
        # 直启（试运行）不反问，但缺了必填部件必须留痕（拒绝黑盒）。
        missing_kp = kp_required_missing(ctx)
        if missing_kp:
            ctx.setdefault("assumptions", []).append({
                "code": "required_kp_skipped", "slot": "kp_required",
                "reason": "必登记部件未登记：" + "、".join(missing_kp)})
        if not (ctx.get("kp_parts") or (ctx.get("ext") or {}).get("kp_mode")) and \
                not kp_args_from_ext(dict(ctx.get("ext") or {})):
            ctx.setdefault("assumptions", []).append({
                "code": "kp_skipped", "slot": "kp_mode",
                "reason": "需求未指定配件：仅按整机底座出方案，可在配置页添加配件"})

    # ── kp（确定性落地 + 未匹配行交唯一大脑锁定）──
    started = time.perf_counter()
    await _emit(broadcast, _trace(key, labels[key], "running"))
    k_cfg = _node_cfg(ctx, key)
    await phase_kp_reason(ctx, k_cfg, broadcast)
    # 配件大脑回合（同机型回合语义）：存在未匹配占位行 → 大脑按需调 search_kp_parts
    # 逐行检索库内真实候选（数据源走节点 data_bindings 注册表，白盒标注 pool_source），
    # 调 select_kp_parts 批量锁定（只认检索索引内料号），选定写入 ext.kp_picks 持久 →
    # 重跑确定性阶段落地为真实行并做写回断言。目标层 kp_reason 配了「AI 反问」策略时
    # 不进大脑——选择权交客户（占位行白盒呈现）。
    unmatched_before = int((ctx.get("kp_summary") or {}).get("unmatched_count") or 0)
    if unmatched_before > 0 and brain is not None and not _artifact_field_ask(k_cfg, "kp_parts"):
        from app.services.slot_contract import canonical_get
        # 数据绑定插头：换数据源 → 检索结果随之变化（白盒标注 pool_source）
        _bind = k_cfg.get("data_bindings") if isinstance(k_cfg.get("data_bindings"), dict) else {}
        _pool_bind = (_bind or {}).get("kp_pool") or {}
        ctx["kp_pool_source"] = "kp_library/" + str(_pool_bind.get("resolver") or "category_series_search")
        ext_now = ctx.get("ext") if isinstance(ctx.get("ext"), dict) else {}
        picks_before = len(ext_now.get("kp_picks") or {})
        await brain_with_cap(key, brain(key, k_cfg, ctx))
        ext_now = ctx.get("ext") if isinstance(ctx.get("ext"), dict) else {}
        new_picks = len(ext_now.get("kp_picks") or {}) - picks_before
        if new_picks > 0:
            await phase_kp_reason(ctx, k_cfg, broadcast)
            # 白盒断言：工具声称选定的行必须真落地（任何静默丢失在这里响亮报错）
            unmatched_after = int((ctx.get("kp_summary") or {}).get("unmatched_count") or 0)
            expected_left = max(0, unmatched_before - new_picks)
            if unmatched_after > expected_left:
                logger.error(
                    "配件大脑已选定 %d 行但未全部落地（剩 %d 未匹配，应剩 ≤%d；"
                    "检查行键失配 / _TOOL_CTX ext 绑定 / apply_kp_picks）",
                    new_picks, unmatched_after, expected_left)
    # ── 未匹配行硬门（AI=配置器）：仍未落真实/替代料号的必须反问类目 → 弹确认卡交客户。
    # 大脑 ask_user 走富化确认卡（AI 建议+推荐标 + 自选下拉 + 数量步进器 + 手动型号）；
    # 客户点选推荐项/自选 → 写 ext.kp_picks 落地；GPU 可「不配」→ 写 kp_absent。不再有
    # 「按缺配继续」逃生（用户已明确删除）；force_complete 一键模式不在此门停留。
    unmatched_now = int((ctx.get("kp_summary") or {}).get("unmatched_count") or 0)
    kp_asks = [a for a in (ctx.get("kp_asks") or [])
               if isinstance(a, dict) and a.get("question")]
    # 未匹配行硬门（AI=配置器）：仍未落真实/替代料号的必须反问类目 → 引擎确定性弹确认卡。
    # 大脑 ask_user 若已登记问题（kp_asks）优先复用其问句与带料号的选项；无论大脑是否调用
    # ask_user，引擎都用 part_query 从配件库拉真实候选做自选下拉/手动型号（2026-09-07
    # 实测根因：确认卡依赖模型自愿调 ask_user，模型偏好散文 → 只剩一句问话、无可点选项）。
    # 客户点选推荐/自选 → kp_manual_pick 写 ext.kp_picks；GPU 可「不配」→ kp_absent。
    # 不再有 kp_unmatched 空信号卡（被模型散文误导，点了「由 AI 补齐」却无任何效果）。
    if unmatched_now > 0 and not ctx.get("force_complete"):
        from app.services.part_selector import kp_row_key as _kp_row_key
        _unmatched = [p for p in (ctx.get("kp_parts") or [])
                      if isinstance(p, dict) and p.get("unmatched")]
        p0 = _unmatched[0] if _unmatched else None
        if p0 is not None:
            row_key = _kp_row_key(str(p0.get("category") or ""),
                                  str(p0.get("request_spec") or "").strip()
                                  or str(p0.get("category") or ""))
            _cat, _desc = (row_key.split("|", 1) + [""])[:2]
            # 问句：大脑对该行的登记优先；否则引擎按行规格给数据事实句
            q = f"{str(p0.get('category') or '')} 选型待确认：{str(p0.get('request_spec') or '').strip() or '规格未明确'}"
            for a in kp_asks:
                if str(a.get("row") or "").strip() == row_key and str(a.get("question") or "").strip():
                    q = str(a["question"]).strip()
                    break
            # 候选真相：按行描述做确定性召回（型号数字段/容量/DDR5 类混合词 OR 命中），
            # 不再类目全量——兆芯行推出 AMD 池（2026-09-07 实测）就是无词全量的产物。
            # 零召回 = 库内无精确匹配，照实下行明示；自选下拉/手动型号由 /card-pick 同口径填充。
            from app.services.data_tools import part_recall
            _psrc = ""
            cands: list = []
            _probes: list = []
            try:
                _qres = part_recall(_cat, desc=_desc,
                                    series=str(((ctx.get("_locked_baseline") or {}).get("series")) or ""),
                                    limit=30)
                _psrc = str(_qres.get("source") or "part_recall")
                if _qres.get("ok"):
                    cands = _qres.get("rows") or []
                    _probes = list(_qres.get("probes") or [])
            except Exception:
                logger.exception("确认卡候选召回失败 row=%s", row_key)
            hint = {"qty": int(p0.get("qty") or 1), "qty_max": max(1, int(p0.get("qty") or 1)),
                    "suggested_qty": 0}
            if cands:
                hint = _row_qty_hint(_cat, _desc, int(p0.get("qty") or 1), cands)
            # AI 建议按钮：只放可落地的（带真实料号）——大脑 ask_user 带 pick 的选项 +
            # select_kp_parts 在反向类目登记的推荐（ext.kp_recommend）；候选全量进自选下拉。
            rec = ((dict(ctx.get("ext") or {})).get("kp_recommend") or {}).get(row_key)
            brain_opts: list = []
            seen: set = set()
            for a in kp_asks:
                if str(a.get("row") or "").strip() not in ("", row_key):
                    continue
                for o in (a.get("options") or []):
                    if not isinstance(o, dict):
                        continue
                    label = str(o.get("label") or "").strip()
                    pk = o.get("pick")
                    if not label or (not (isinstance(pk, dict) and str(pk.get("name") or "").strip())
                                     and not o.get("absent")):
                        continue
                    if label in seen:
                        continue
                    seen.add(label)
                    _wq = hint["qty"]
                    if isinstance(pk, dict):
                        try:
                            _wq = int(pk.get("qty") or hint["qty"])
                        except (TypeError, ValueError):
                            _wq = hint["qty"]
                    brain_opts.append({"label": label, "value": label,
                                       "desc": str(o.get("description") or ""),
                                       "group": "AI 建议", "qty": _wq, "qty_max": hint["qty_max"],
                                       "recommended": bool(o.get("recommended")),
                                       "signal": _ask_option_signal(row_key, o)})
            if isinstance(rec, dict) and str(rec.get("name") or "").strip() and rec.get("name") not in seen:
                seen.add(str(rec["name"]))
                _wq2 = hint["qty"]
                try:
                    _wq2 = int(rec.get("qty") or hint["qty"])
                except (TypeError, ValueError):
                    _wq2 = hint["qty"]
                brain_opts.append({"label": str(rec["name"]), "value": str(rec["name"]),
                                   "desc": "AI 推荐 · " + str(rec.get("reason") or ""),
                                   "group": "AI 建议", "qty": _wq2, "qty_max": hint["qty_max"],
                                   "recommended": True,
                                   "signal": _ask_option_signal(row_key, {"pick": {
                                       "part_id": str(rec.get("part_id") or ""),
                                       "name": str(rec.get("name") or ""),
                                       "price": rec.get("price"),
                                       "currency": str(rec.get("currency") or "RMB"),
                                       "qty": _wq2}})})
            # GPU「不配」逃生（必须反问类目可选放弃）
            if str(_cat).lower().startswith("gpu"):
                brain_opts.append({"label": "本机不配 GPU", "value": "本机不配 GPU",
                                   "group": "如何处理", "recommended": False,
                                   "signal": _ask_option_signal(row_key, {"absent": str(_cat)})})
            # 兜底（AI 建议空缺时）：把库内真实候选以「候选」组给客户自选（事实非推荐），
            # 保证确认卡 options 非空可渲染；不再硬编码取某件标推荐——那必须由 AI 产出。
            if not brain_opts and cands:
                _wq3 = int(hint["qty"])
                for c in cands[:20]:
                    cnm = str(c.get("name") or "").strip()
                    if not cnm or cnm in seen:
                        continue
                    seen.add(cnm)
                    brain_opts.append({"label": cnm, "value": cnm,
                                       "desc": " · ".join(
                                           f"{k}:{v}" for k, v in (c.get("specs") or {}).items())[:60],
                                       "group": "候选", "qty": _wq3, "qty_max": hint["qty_max"],
                                       "recommended": False,
                                       "signal": _ask_option_signal(row_key, {"pick": {
                                           "part_id": str(c.get("part_id") or ""),
                                           "name": cnm,
                                           "price": c.get("price"),
                                           "currency": str(c.get("currency") or "RMB"),
                                           "qty": _wq3}})})
            gap: dict = {"slot": "brain_ask", "reason_code": "brain_ask",
                         "question": q, "options": brain_opts}
            # 行卡表单（自选下拉 + 数量步进 + 手动型号）：候选由 /card-pick 按留底 pick_meta
            # 重跑 part_query 填充；这里也留候选供手动型号匹配。
            gap["parts_card"] = True
            gap["row"] = row_key
            gap["qty"] = hint["qty"]
            gap["qty_max"] = hint["qty_max"]
            gap["unit_label"] = "内存" if str(_cat).lower().startswith("mem") else ""
            gap["pick_meta"] = {"row": row_key,
                                "category": str(_cat),
                                "request_spec": str(_desc),
                                "row_qty": hint["qty"],
                                "series": str(((ctx.get("_locked_baseline") or {}).get("series")) or ""),
                                "pool_source": str(ctx.get("kp_pool_source") or _psrc),
                                "probes": _probes,
                                "pool": [{"part_id": str(c.get("part_id") or ""),
                                          "name": str(c.get("name") or ""),
                                          "price": c.get("price"),
                                          "currency": c.get("currency"),
                                          "specs": c.get("specs") or {}} for c in cands[:8]]}
            if _probes and not cands:
                # 行描述的词在库内零召回：照实告诉客户/大脑「无精确匹配」，别拿全量池冒充
                gap["no_library_match"] = True
            return _pause_with_gaps("kp_reason", gap)
    summary_map = dict(ctx.get("kp_summary") or {})
    unmatched_rows = [{"category": p.get("category"),
                       "description": str(p.get("request_spec") or p.get("description") or "").strip(),
                       "qty": p.get("qty") or 1,
                       "reason": p.get("unmatched_reason")}
                      for p in (ctx.get("kp_parts") or []) if p.get("unmatched")]
    # 配件表形状由目标层插头驱动（2026-09-06 通电）：列=描述符 visible 列，
    # 单元格=from/fallback 产源映射抽取（改抽屉列定义，产物跟变；行键不再硬编码）。
    # 白盒状态键（unmatched/spec_mismatch）随行透传，不参与列契约。
    from app.services.skill_target_contract import (
        STATUS_KEYS, first_artifact, shape_rows, visible_columns)
    _art = first_artifact(_node_cfg(ctx, key))
    # 表格行只含真实料号：未匹配占位行（unmatched=True）进 artifact.unmatched 白盒区，
    # 不作为表格行——KP 配置表必须是配件库真实存在的配件（2026-09-06 拿客户原话当行）。
    _table_parts = [p for p in (ctx.get("kp_parts") or [])
                    if isinstance(p, dict) and not p.get("unmatched")]
    kp_art_rows = shape_rows(_art, _table_parts,
                             extra_keys=STATUS_KEYS)
    cols_spec = visible_columns(_art)
    await _emit(broadcast, _trace(
        key, labels[key], "done", output=dict(summary_map, pool_source=str(ctx.get("kp_pool_source") or "")),
        summary=f"落地配件 {summary_map.get('kp_count', 0)} 项"
                + (f"（未命中 {summary_map.get('unmatched_count')}）" if summary_map.get("unmatched_count") else "")
                + (f" · 候选池数据源 {ctx.get('kp_pool_source')}" if ctx.get("kp_pool_source") else ""),
        artifact={"kind": "kp_table", "title": "KP表",
                  "data": {"rows": kp_art_rows,
                           "columns": cols_spec, "summary": summary_map, "unmatched": unmatched_rows}},
        duration_ms=round((time.perf_counter() - started) * 1000)))

    # ── compose ──
    key = "compose"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    started = time.perf_counter()
    await compose_plans(ctx, _node_cfg(ctx, key), broadcast)
    plans = ctx.get("plans") or []
    await _emit(broadcast, _trace(
        key, labels[key], "done", output={"plans_count": len(plans)},
        summary=f"组装 {len(plans)} 个整机配置" if plans else "无可组装的整机基准",
        artifact={"kind": "compose", "title": "BOM 组装结果",
                  "data": [{"model": (p.get("model") or ""), "total_cost": ((p.get("summary") or {}).get("total_cost"))} for p in plans]},
        duration_ms=round((time.perf_counter() - started) * 1000)))

    # ── output ──
    key = "output"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    started = time.perf_counter()
    out_payload = await finalize_output(ctx, _node_cfg(ctx, key), broadcast)
    bom_entity = (ctx.get("business_entity") or {}).get("entity")
    await _emit(broadcast, _trace(
        key, labels[key], "done", output=out_payload if isinstance(out_payload, dict) else {},
        summary="已生成交接产物" if bom_entity is not None else "会话模式产出预览",
        artifact=None, duration_ms=round((time.perf_counter() - started) * 1000)))
    timings["plan_total_ms"] = round((time.perf_counter() - t0) * 1000)
    ctx["awaiting_input"] = False
    return ctx


def compact_candidate(candidate: dict) -> dict:
    return {
        "id": str(candidate.get("server_model_id") or candidate.get("id") or ""),
        "name": str(candidate.get("name") or ""),
        "type": str(candidate.get("server_type_name") or ""),
        "series": str(candidate.get("series") or ""),
        "form": str(candidate.get("form") or ""),
        "price": candidate.get("total_price"),
    }


# scene_gap/kp_mode_gap 从 skill_phases 引用（re-export 供旧调用兼容）
from app.services.skill_phases import kp_mode_gap, scene_gap  # noqa: E402,F401
