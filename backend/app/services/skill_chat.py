# -*- coding: utf-8 -*-
"""AI 角色（对话脑）与 Skill 引擎的接线层——两器官架构的「器官间神经」。

宪法（2026-08-28 立法，2026-09-02 按唯一大脑模型修订）：
- 全系统同一时刻只有一个会思考的脑袋：AI 角色。普通聊天阶段只有说话/查目录/提交开关，
  不读 skill 节点内容、不碰登记表；用户确认后任务交给确定性引擎执行；
- 登记环节（agent_fill 节点）= 唯一大脑的显式回合：同一个人设、同一条流式循环，
  大脑亲自调 fill_requirement（任务期工具）结构化落表；落表后的缺口判定/规范化
  由引擎确定性完成（phase_normalize_slots），没有第二次隐藏 LLM；
- 引擎返回的缺口是纯数据，怎么问由角色组织语言；
- 本模块不含任何话术表/关键词清单；业务选项（kp_mode 两个值等）全部来自引擎缺口数据。
- query_data 的权限不在提示词里：物理强制在 data_boundary.execute_read（步骤1），
  角色提示词只描述怎么用，不承诺能读到什么。
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
from typing import Any, Callable, Optional

from app.repository.assistant_repo import AssistantRepository
from app.services.agent_react import run_stream_chat_loop
from app.services.assistant_hub import assistant_hub
from app.services.slot_contract import canonical_key, slot_label, slot_spec

logger = logging.getLogger(__name__)

MEMORY_KEY = "skill_chat"


def _mem_key(role_key: str) -> str:
    """技能流程记忆按「线程 + 角色」隔离：专家接手时是干净身份，不会接手别的角色没走完的流程。"""
    return f"{MEMORY_KEY}:{(role_key or 'assistant').strip() or 'assistant'}"

# 工具执行期的线程上下文（react 循环内 handler 读取；run 侧每轮注入）
_TOOL_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("skill_chat_tool_ctx", default={})

# 机制工具白名单（2026-09-06 资源层真源化配套）：节点机制必需的工具，不可配置移除。
# enabled_tools（DB）是工具集唯一真源，这里只在配置漂移缺机制工具时保底补回并告警。
MECHANISM_TOOLS = {
    "agent_fill": ["fill_requirement"],
    "kp_reason": ["select_kp_parts", "search_kp_parts", "ask_user"],
    "model_reason": ["select_model"],
}


def kp_ask_categories(node_cfg: dict) -> list:
    """目标层字段策略：配件行级「AI 反问」类目清单（kp_reason 专属）。

    来源=target.artifacts[0].fields 里 key 为 `kp_parts:<类目>` 且 ask=true 的行
    （抽屉字段清单：kp_reason 左栏=配件行字段）。ask=true / must_ask=true → 该类行
    AI 不代选，引擎/工具硬执行：select_kp_parts 拒绝代选提交，大脑须调 ask_user 交客户决策。
    全局开关（key='kp_parts' 的 ask）在 skill_plan_runtime 的 kp gate 消费（不进大脑）。
    """
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    arts = ((cfg.get("target") or {}).get("artifacts") or [])
    fields = ((arts[0] if arts else {}) or {}).get("fields") or []
    out = []
    for f in fields:
        if isinstance(f, dict) and (bool(f.get("ask")) or bool(f.get("must_ask"))):
            key = str(f.get("key") or "")
            if key.startswith("kp_parts:"):
                cat = key.split(":", 1)[1].strip()
                if cat:
                    out.append(cat)
    return out


def _brain_note_summary(node_key: str, result: dict) -> str:
    """把本回合工具轨迹压成一条工作记录（跨回合注入，治「每轮从登记表快照从零开始」）。"""
    bits: list = []
    for c in (result or {}).get("tool_calls_log") or []:
        name = str((c or {}).get("name") or "")
        if not name:
            continue
        args = (c or {}).get("args") if isinstance((c or {}).get("args"), dict) else {}
        res = (c or {}).get("result")
        res = res if isinstance(res, dict) else {}
        if name == "search_kp_parts":
            detail = (f"category={args.get('category')} keywords={args.get('keywords') or '∅'}"
                      f" → {res.get('total', '?')}条")
        elif name == "select_kp_parts":
            picks = args.get("picks") if isinstance(args.get("picks"), list) else []
            detail = f"提交{len(picks)}行 ok={res.get('ok')}"
            if res.get("ok") is False:
                detail += f" err={str(res.get('error') or '')[:60]}"
        elif name == "fill_requirement":
            detail = f"落表 ok={res.get('ok')}"
        elif name == "select_model":
            detail = f"选定 {args.get('model') or args.get('model_id')} ok={res.get('ok')}"
        elif name == "ask_user":
            detail = f"问客户：{str(args.get('question') or '')[:40]}"
        else:
            detail = str(args)[:60]
        bits.append(f"{name}({detail})")
    answer = str((result or {}).get("answer") or "").strip()
    if answer:
        bits.append(f"对客户说:{answer[:60]}")
    return f"[{node_key}] " + "；".join(bits)[:400]


async def _emit_brain_status(sink, text: str) -> None:
    """大脑回合过程状态（重试中/预算到点）：只走事件流给前端看板，kind=tool 不进旁白落库。"""
    if not sink:
        return
    try:
        await sink({"type": "step_progress", "step": "react",
                    "sub": {"kind": "tool", "text": text}})
    except Exception:
        pass


def _load_mem(thread_id: str, role_key: str = "assistant") -> dict:
    try:
        repo = AssistantRepository()
        try:
            raw = repo.get_reasoning_state(thread_id)
        finally:
            repo.close()
        data = json.loads(raw or "{}") if raw else {}
        mem = data.get(_mem_key(role_key))
        return dict(mem) if isinstance(mem, dict) else {}
    except Exception:
        logger.exception("读取 skill_chat 记忆失败 thread=%s", thread_id)
        return {}


def _save_mem(thread_id: str, role_key: str, mem: dict) -> None:
    try:
        repo = AssistantRepository()
        try:
            repo.update_reasoning_state(thread_id, {_mem_key(role_key): mem})
        finally:
            repo.close()
    except Exception:
        logger.exception("保存 skill_chat 记忆失败 thread=%s", thread_id)


SKILL_SESSION_KEY = "skill_session"


def load_skill_session(thread_id: str, role_key: str = "assistant") -> dict:
    """读取技能会话状态（idle/proposing/active），与 ext/last_card 同存一份 skill_chat 记忆。"""
    mem = _load_mem(thread_id, role_key)
    session = mem.get(SKILL_SESSION_KEY)
    return dict(session) if isinstance(session, dict) else {}


def save_skill_session(thread_id: str, role_key: str, session: dict) -> None:
    """写技能会话状态，保留同线程已有的 ext/last_card 等记忆。"""
    mem = _load_mem(thread_id, role_key)
    mem[SKILL_SESSION_KEY] = session if isinstance(session, dict) else {}
    _save_mem(thread_id, role_key, mem)


def _slots_view(ext: dict) -> dict:
    """登记表可读视图（角色提示词里展示的当前状态）：即需求表（RequirementSlots 干净键）。

    与引擎 normalize 产出的 artifact 同构，让角色「看到的表 = 要填的表 = 下游读的表」。
    旧 ext 信号键名（cpu/…）不再作为写契约暴露给角色。
    """
    from app.services.portal_flow_adapter import requirement_slots_from_ext
    view = dict(requirement_slots_from_ext(ext or {}))
    kp_mode = (ext or {}).get("kp_mode")
    if kp_mode not in (None, "", [], {}):
        view["kp_mode"] = kp_mode
    return view


def clear_memory(thread_id: str, role_key: str = "assistant") -> None:
    _save_mem(thread_id, role_key, {})


def _match_card_signal(mem: dict, slot: str, value: str) -> Optional[dict]:
    """从最近一张选项卡的结构化载荷里按 (slot, value) 匹配 signal（发卡时持久化的原始数据）。"""
    for o in ((mem.get("last_card") or {}).get("options") or []):
        if str(o.get("slot") or "") == slot and str(o.get("value") or "") == value \
                and isinstance(o.get("signal"), dict) and o.get("signal"):
            return o.get("signal")
    return None


def _signal_with_qty(signal: dict, qty: int, pick_meta: dict) -> dict:
    """数量覆盖（前端 stepper 参数）：克隆留底 signal 改数量，按机箱能力 clamp。
    数量是参数不是信号语义——服务端单点收口，客户端只传数字。"""
    import copy
    qty = max(1, int(qty or 1))
    meta = pick_meta if isinstance(pick_meta, dict) else {}
    gpu_cap = int(meta.get("gpu_slots") or 0) or 8
    dimm_cap = int(meta.get("max_dimm") or 0) or 8
    cpu_cap = int(meta.get("max_cpu") or 0) or 2
    sig = copy.deepcopy(signal)
    try:
        if isinstance(sig.get("kp_manual_pick"), dict):
            # 客户自选（kp 行卡）：数量直接覆盖申报，上限 clamp
            sig["kp_manual_pick"]["qty"] = min(qty, 999)
        elif isinstance(sig.get("gpu"), list) and sig["gpu"]:
            sig["gpu"][0]["qty"] = min(qty, gpu_cap)
        elif isinstance(sig.get("cpu"), dict):
            sig["cpu"]["qty"] = min(qty, cpu_cap)
        elif isinstance(sig.get("memory"), dict):
            sig["memory"]["qty"] = min(qty, dimm_cap)
        elif isinstance(sig.get("storage"), list) and sig["storage"]:
            sig["storage"][0]["qty"] = min(qty, 16)
        else:
            return signal
    except Exception:
        logger.exception("数量覆盖失败，回退原 signal")
        return signal
    return sig


def _brain_ask_manual_signal(mem: dict, text: str) -> Optional[dict]:
    """brain_ask 行卡的手动型号（2026-09-06 自选料接线）：pick_meta 留底池内匹配 →
    kp_manual_pick（价格用服务端留底值，客户端不可携带）；未命中 → kp_row_merge 文本
    并入行描述（白盒，下一轮大脑消化），绝不编造料号。"""
    meta = (mem.get("last_card") or {}).get("pick_meta") or {}
    row = str(meta.get("row") or "").strip()
    if not row:
        return None
    pool = [p for p in (meta.get("pool") or []) if isinstance(p, dict)]
    t = text.strip().lower()
    if not t:
        return None
    for c in pool:
        name = str(c.get("name") or "")
        if name.lower() == t or t in name.lower():
            return {"kp_manual_pick": {"row": row, "part_id": str(c.get("part_id") or ""),
                                        "name": name, "price": c.get("price"),
                                        "currency": str(c.get("currency") or "RMB")}}
    return {"kp_row_merge": {"row": row, "answer": text.strip()}}


def _manual_model_signal(mem: dict, slot: str, text: str) -> Optional[dict]:
    """自由输入型号 → 目录模糊匹配构造 signal（未命中返回 None，走登记表白盒路径）。"""
    meta = (mem.get("last_card") or {}).get("pick_meta") or {}
    if not isinstance(meta, dict) or not meta:
        return None
    from app.services.part_selector import manual_signal_for_text
    try:
        return manual_signal_for_text(slot, text, str(meta.get("server_type_name") or ""),
                                       baseline=meta)
    except Exception:
        logger.exception("手动型号目录匹配失败 slot=%s", slot)
        return None


# ── 角色动作（注册进全局工具表，经 _TOOL_CTX 取线程状态）────────────────
def tool_submit_registration(args: dict) -> dict:
    ctx = _TOOL_CTX.get()
    ext = ctx.get("ext") or {}
    if ctx.get("allow_submit") is False:
        return {"ok": False, "error": "phase_guard",
                "hint": "用户尚未确认开始流程。请先总结需求并等待用户确认，确认后再提交登记表。"}
    # 不再在提交口硬拦 scene_missing：信息可能不齐，交给 AI 角色 agent_fill 后的
    # 目标层缺口统一弹卡反问（反问项=抽屉目标层配置，选项=目录，保留自由输入）。
    # 目录词表校验仍前置：非目录类型提交后引擎必拒（词表失配→场景缺口），会形成
    # 「问→答→再问」循环；在这里拒绝并列出目录选项，模型当轮即可纠正或向客户确认。
    filled = str(ext.get("server_type_name") or ext.get("server_type") or "").strip()
    if filled:
        from app.repository.server_catalog_repo import ServerCatalogRepository
        catalog = [str(t.get("name") or "").strip() for t in ServerCatalogRepository().list_types() if t.get("name")]
        if catalog and filled not in catalog:
            return {"ok": False, "error": "invalid_scene",
                    "hint": f"「{filled}」不是在售目录里的服务器类型，不能提交。在售目录类型：{'、'.join(catalog)}。"}
    on_submit = ctx.get("on_submit")
    if callable(on_submit):
        on_submit()
    return {"ok": True, "note": "登记表已提交，配置引擎开始执行，请等待结果后向用户汇报"}


def tool_catalog_search(args: dict) -> dict:
    """在售目录查询（推荐的事实来源）：types=类型清单；models=按类型/系列/形态查机型（含价格）。

    无任何过滤条件的 models 查询=浏览全目录（角色推荐场景的合法动作），
    按类型逐个取再合并；引擎的「无信号返空」守卫只属于选型，不拦目录浏览。
    """
    kind = str((args or {}).get("kind") or "models").strip()
    limit = int((args or {}).get("limit") or 8)
    try:
        if kind == "types":
            from app.repository.server_catalog_repo import ServerCatalogRepository
            return {"ok": True, "types": [t.get("name") for t in ServerCatalogRepository().list_types() if t.get("name")]}
        if kind == "parts":
            # 配件目录（角色「有什么配件可选」的事实来源）：按品类+系列适配过滤，
            # 与引擎落地同一 applicable 语义，推荐给客户的件必然装得上。
            cat = str((args or {}).get("category") or "").strip()
            p_series = str((args or {}).get("series") or "").strip()
            if not cat:
                from app.services.part_selector import list_kp_categories
                return {"ok": True, "categories": list_kp_categories(),
                        "hint": "先按 category=品类 查询，可选 series 过滤适配平台"}
            from app.repository.kp_repo import KPRepository
            from app.services.part_selector import _series_ok
            _repo = KPRepository()
            try:
                rows = _repo.get_by_category_with_specs(cat)
            finally:
                _repo.close()
            if p_series:
                rows = [r for r in rows if _series_ok(r.get("applicable"), p_series)]
            pout = []
            price_ok = bool(_TOOL_CTX.get().get("price_ok", True))
            for r in rows[:max(1, min(limit, 12))]:
                item = {"name": r.get("model"), "category": cat,
                        "applicable_series": (r.get("applicable") or {}).get("series")
                        if isinstance(r.get("applicable"), dict) else None}
                if price_ok:
                    try:
                        if float(r.get("price") or 0) > 0:
                            item["price"] = float(r.get("price"))
                    except (TypeError, ValueError):
                        pass
                pout.append(item)
            return {"ok": True, "parts": pout}
        from app.services.model_candidates import select_models
        type_name = str((args or {}).get("type_name") or "").strip() or None
        series = str((args or {}).get("series") or "").strip() or None
        form = str((args or {}).get("form") or "").strip() or None
        rows: list = []
        if not any([type_name, series, form]):
            from app.repository.server_catalog_repo import ServerCatalogRepository
            for t in ServerCatalogRepository().list_types():
                if len(rows) >= limit:
                    break
                rows.extend(select_models(usage=None, server_type_name=str(t.get("name") or "").strip() or None, limit=limit) or [])
        else:
            rows = select_models(usage=None, server_type_name=type_name, series=series, form=form, limit=limit) or []
        out = []
        price_ok = bool(_TOOL_CTX.get().get("price_ok", True))
        for r in rows[:max(1, min(limit, 12))]:
            item = {"name": r.get("name"), "type": r.get("server_type_name"), "series": r.get("series"),
                    "form": r.get("form")}
            if price_ok:
                item["price"] = r.get("total_price")
            out.append(item)
        return {"ok": True, "models": out}
    except Exception as exc:
        logger.exception("catalog_search 失败")
        return {"ok": False, "error": str(exc)}


def tool_query_data(args: dict) -> dict:
    """query_data：数据边界内的只读 SELECT 原语（2026-08-29 步骤2）。

    权限全部在 execute_read（物理校验+只读事务+超时+行数上限+列脱敏）；
    这里只做上下文接线与审计。SQL 报错原样回传，模型据此自纠。
    """
    ctx = _TOOL_CTX.get()
    boundary = ctx.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("mode") != "allow_read":
        return {"ok": False, "error": "数据边界为拒绝模式（deny_all），无读取权限"}
    sql = str((args or {}).get("sql") or "").strip()
    if not sql:
        return {"ok": False, "error": "缺 sql 参数（单条只读 SELECT）"}
    try:
        limit = int((args or {}).get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    from app.services.data_boundary import execute_read
    out = execute_read(sql, boundary, limit=limit)
    logger.info("query_data role=%s ok=%s rows=%s truncated=%s sql=%s",
                ctx.get("role_key") or "?", bool(out.get("ok")),
                out.get("row_count") or 0, bool(out.get("truncated")),
                " ".join(sql.split())[:300])
    return out


# ── 角色的需求收集提示词（对脑的指令，非话术表）────────────────────────────

def requirement_prompt(slots: Optional[dict] = None, price_ok: bool = True, query_data_ok: bool = False,
                       flow_steps: Optional[list] = None) -> str:
    """角色的需求收集提示词。slots=None = 任务未开始：不暴露登记表（进任务前不碰目标表）。"""
    from app.services.skill_prompts import load_skill_prompts
    prompts = load_skill_prompts()
    price_rule = str(prompts.get("price_rule_ok") or "") if price_ok else str(prompts.get("price_rule_no") or "")
    data_rule = str(prompts.get("data_rule") or "") if query_data_ok else ""
    if slots is None:
        slots_block = "（配置任务未开始：现在没有登记表，禁止提前登记或填表；客户确认开始后由引擎建立）"
    else:
        slots_block = json.dumps(slots, ensure_ascii=False)
    # 流程步骤块（可配置：来自 Skill 画布里节点的 label/description，可编辑支配）。
    # 只在明确传入时注入（PROPOSING 提议预告 / 任务回合）；普通聊天不给流程内容。
    plan_rule = ""
    if flow_steps:
        step_lines = []
        for s in flow_steps:
            label = str(s.get("label") or "").strip()
            desc = str(s.get("description") or "").strip()
            step_lines.append(f"- {label}：{desc}" if desc else f"- {label}")
        plan_rule = str(prompts.get("plan_rule") or "").replace("<<STEPS>>", "\n".join(step_lines))
    role_prompt = str(prompts.get("role_prompt") or "")
    return (role_prompt
            .replace("<<SLOTS>>", slots_block)
            .replace("<<PRICE_RULE>>", price_rule)
            .replace("<<DATA_RULE>>", data_rule)
            .replace("<<PLAN_RULE>>", plan_rule))


def _normalize_fill_keys(slots: dict) -> dict:
    """把大脑给的登记键归一为 canonical 字段（数据驱动，不写死词表）。

    归一顺序：别名表（canonical_key）→ 登记表中文标签 → 大小写对齐。
    模型偶发用「服务器类型」等中文标签或「CPU」等大写键登记——落错槽的登记等于没登记。
    """
    spec = slot_spec()
    label_map: dict = {}
    lower_map: dict = {}
    valid_keys: set = set()
    for s in spec:
        key = str(s.get("key") or "").strip()
        if not key:
            continue
        valid_keys.add(key)
        label = str(s.get("label") or "").strip()
        if label and label not in label_map:
            label_map[label] = key
        lower_map.setdefault(key.lower(), key)
    norm: dict = {}
    for k, v in (slots or {}).items():
        key = str(k).strip()
        canon = canonical_key(key)
        if canon not in valid_keys:
            if key in label_map:
                canon = label_map[key]
            elif canon.lower() in lower_map:
                canon = lower_map[canon.lower()]
        norm[canon] = v
    return norm


def tool_fill_requirement(args: dict) -> dict:
    """【任务期工具】把客户已明确表达的需求逐项登记到线索登记表（结构化落表）。

    只在 agent_fill 节点的大脑回合挂载；普通对话永远没有这个工具——
    进任务前角色只引导和复述，绝不提前填表。落表本身是确定性的
    （_apply_extracted_slots：默认只填空槽；replace=True 客户改口才覆盖）。
    """
    ctx = _TOOL_CTX.get()
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "hint": "配置任务未开始，禁止登记。先与客户对话澄清，客户确认开始后再登记。"}
    slots = (args or {}).get("slots")
    if not isinstance(slots, dict) or not slots:
        return {"ok": False, "error": "invalid_args",
                "hint": "slots 必须是对象（键=登记表字段，值=客户原话信息）"}
    replace = bool((args or {}).get("replace"))
    slots = _normalize_fill_keys(slots)
    # 值规范化（机制级，非业务词表）：数字字段接受「3年」「2台」等自然语言写法，
    # 否则会被整数守卫静默丢弃（实测：大脑原样转写"3年"→字段丢失）。
    import re as _re
    for num_key in ("purchase_qty", "warranty_years"):
        v = slots.get(num_key)
        if isinstance(v, str):
            m = _re.search(r"\d+", v)
            if m:
                slots[num_key] = int(m.group(0))
    # 对象身份必须保持（空 dict falsy 会换成 detached 副本，落表全丢——09-02 实测坑）。
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    # 明确放弃部件（kp_absent）：客户答复"不需要某类部件"时登记放弃，
    # 必登记部件策略（kp_required）据此放行，不再追问该大类。
    kp_absent = slots.pop("kp_absent", None)
    kp_absent_changed = False
    if isinstance(kp_absent, list) and kp_absent:
        merged = {str(c).strip() for c in kp_absent if str(c).strip()} | set(ext.get("kp_absent") or [])
        ext["kp_absent"] = sorted(c for c in merged if c)
        kp_absent_changed = True
    from app.services.capabilities import _apply_extracted_slots, _slot_now_filled
    changed = _apply_extracted_slots(ext, slots, allow_overwrite=replace)
    save = ctx.get("save")
    if callable(save):
        save()
    from app.services.slot_contract import _missing_critical
    spec = slot_spec()
    valid_keys = {str(s.get("key") or "").strip() for s in spec if str(s.get("key") or "").strip()}
    valid_keys.add("kp_rows")  # 部件行是登记表的真实存储键（不在 slot_spec 清单里）
    req_keys = {s.get("key") for s in spec if s.get("src_type") != "kp"}
    missing = [slot_label(m) for m in _missing_critical(ext)
               if m in req_keys and not _slot_now_filled(ext, m)]
    unknown = sorted(k for k in slots if k not in valid_keys)
    return {"ok": True, "changed": bool(changed or kp_absent_changed),
            "registered": sorted(str(k) for k in slots.keys() if k in valid_keys)
                          + (["kp_absent"] if kp_absent_changed else []),
            "unrecognized_keys": unknown,
            "hint": ("部件信息请改用 kp_rows 数组登记：每项 {part_category, description, qty}，"
                     "part_category 用配件大类名，description 按客户原话原样写") if unknown else "",
            "missing_critical": missing,
            "current": _slots_view(ext)}


def fill_tool_parameters() -> dict:
    """fill_requirement 的参数 schema：从登记表字段契约生成（system_config.requirement_slots + KP 大类）。

    字段清单/标签全部数据驱动——前端改登记表字段配置，工具契约自动跟随，不写死字段词表。
    """
    props: dict = {}
    for s in slot_spec():
        key = str(s.get("key") or "").strip()
        if not key or s.get("src_type") == "kp":
            continue
        props[key] = {"type": "string", "description": str(s.get("label") or key)}
    props["kp_rows"] = {
        "type": "array", "items": {"type": "object"},
        "description": "部件清单，每项 {part_category, description, qty}；description 按客户原话原样写，不拆规格",
    }
    props["kp_absent"] = {
        "type": "array", "items": {"type": "string"},
        "description": "客户明确表示不需要的必登记部件大类（如 ['GPU']）；登记后不再追问该类",
    }
    return {"type": "object", "properties": {
        "slots": {"type": "object", "properties": props,
                  "description": "登记表字段 → 客户已明确表达的原话信息"},
        "replace": {"type": "boolean",
                    "description": "客户改口/修正时 true（允许覆盖已登记值）；默认 false 只填空槽"},
    }}


def tool_select_model(args: dict) -> dict:
    """【任务期工具】机型选配节点的大脑回合：从引擎候选池锁定一个机型（接地）。

    候选池由引擎确定性构建（登记表信号 × 在售目录，engine_ctx.baselines_pool 经
    _TOOL_CTX 下发），这里只做池内校验 + 落槽：id 精确或名称忽略大小写精确命中，
    池外型号一律拒绝（B2：LLM 只在事实源给定的取值域内决策）。锁定后由引擎重跑
    确定性阶段校验（显式命中候选池）并携带 AI 理由；大脑不调用 → 引擎弹机型选项卡。
    """
    ctx = _TOOL_CTX.get()
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "hint": "配置任务未开始，禁止锁定机型。"}
    pool = ctx.get("model_pool")
    if not isinstance(pool, list) or not pool:
        return {"ok": False, "error": "empty_pool",
                "hint": "当前没有候选机型池（引擎未给出候选），请向客户澄清需求信号"}
    name = str((args or {}).get("model") or "").strip()
    mid = str((args or {}).get("model_id") or "").strip()
    reason = str((args or {}).get("reason") or "").strip()
    if not name and not mid:
        return {"ok": False, "error": "invalid_args",
                "hint": "model（机型名）或 model_id 至少提供一个，取值必须来自候选池"}
    hit = None
    for c in pool:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("server_model_id") or c.get("id") or "").strip()
        cname = str(c.get("name") or "").strip()
        if (mid and cid and cid == mid) or (name and cname and cname.lower() == name.lower()):
            hit = c
            break
    if hit is None:
        return {"ok": False, "error": "not_in_pool",
                "hint": "所选机型不在候选池内，只能从候选池里选",
                "candidates": [str(c.get("name") or "") for c in pool if isinstance(c, dict)][:8]}
    from app.services.slot_contract import canonical_set
    # 与引擎/工具共享同一 ext 对象（副本会丢落表——同 fill_requirement 的 09-02 实测坑）
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    canonical_set(ext, "server_model", str(hit.get("name") or ""))
    save = ctx.get("save")
    if callable(save):
        save()
    return {"ok": True,
            "selected": {"model_id": str(hit.get("server_model_id") or hit.get("id") or ""),
                         "name": str(hit.get("name") or "")},
            "reason": reason,
            "message": f"已锁定机型 {hit.get('name')}",
            "current": _slots_view(ext)}


def _index_bucket_rows(bucket: dict) -> list:
    """把接地索引桶（part_id/name 双键）归一成去重 row 列表。"""
    seen: dict = {}
    for v in (bucket or {}).values():
        if not isinstance(v, dict):
            continue
        pid = str(v.get("part_id") or "")
        if not pid or pid in seen:
            continue
        seen[pid] = v
    return list(seen.values())


def tool_search_kp_parts(args: dict) -> dict:
    """【任务期工具】kp_reason 配件选配回合专用：按类目+关键词/规格检索配件库真实候选。

    progressive disclosure（2026-09-06）+ 统一数据层：大脑不再吃候选池快照，逐行按需
    query。支持 spec_filters（结构化规格过滤，AND）与 keywords；结果（服务端真相）登记
    进 kp_search_index 按类目累积，select_kp_parts 只认索引内料号。同一类目已检索过且无
    refresh 时直接复用索引（不再去库，避免逐轮重复检索）。数据源走节点 data_bindings。
    """
    ctx = _TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "search_kp_parts 仅在任务期的配件选配环节可用"}
    category = str((args or {}).get("category") or "").strip()
    if not category:
        return {"ok": False, "error": "invalid_args",
                "message": "category 必填（库内类目，如 Memory/NIC/CPU；可用 search 前先看行清单）"}
    keywords = str((args or {}).get("keywords") or "").strip()
    spec_filters = (args or {}).get("spec_filters")
    if not isinstance(spec_filters, list):
        spec_filters = []
    try:
        limit = max(1, min(20, int((args or {}).get("limit") or 8)))
    except (TypeError, ValueError):
        limit = 8
    idx = dict(ctx.get("kp_search_index") or {})
    cat_key = category.lower()
    from app.services.data_tools import part_query, part_index_rows
    q = part_query(category, spec_filters=spec_filters, keywords=keywords,
                   series=str(ctx.get("kp_series") or ""), limit=limit,
                   price_ok=bool(ctx.get("price_ok")))
    if not q.get("ok"):
        return q
    rows = q.get("rows") or []
    price_ok = bool(ctx.get("price_ok"))
    # 接地索引 = 累加升级：同一类目下不同需求行（480G SSD / 6T HDD / 1.92T SSD）会多次
    # 搜索，旧实现「首查命中旧桶即复用」会让后者看不到本行候选（2026-09-07 实测根因）。
    # 每次检索都把本次结果并入桶（只增不减），返回给模型的仍是「本次过滤后」的结果。
    bucket = dict(idx.get(cat_key) or {})
    bucket.update(part_index_rows(rows))
    idx[cat_key] = bucket
    ctx["kp_search_index"] = idx
    save = ctx.get("save")
    if callable(save):
        save()
    out = []
    for c in rows:
        o = {"part_id": c.get("part_id"), "name": c.get("name")}
        if price_ok and c.get("price") is not None:
            o["price"] = c.get("price")
        if isinstance(c.get("specs"), dict) and c["specs"]:
            o["specs"] = c["specs"]
        out.append(o)
    return {"ok": True, "category": category, "keywords": keywords,
            "total": len(out), "truncated": bool(q.get("truncated")),
            "source": str(q.get("source") or "kp_library/part_query"),
            "results": out,
            "message": f"检索到 {len(out)} 条候选" + ("（已截断，可用 spec_filters 收窄）" if q.get("truncated") else "")}


def tool_select_kp_parts(args: dict) -> dict:
    """【任务期工具】kp_reason 配件选配回合专用：把未匹配的登记部件行批量锁定为库内真实料号。

    接地（B2，2026-09-06 按需检索版）：大脑先 search_kp_parts 按类目检索真实候选
    （结果由服务端登记进 kp_search_index），select 只认索引内料号、价格取服务端
    留底值——大脑无权凭空指定料号，客户端更不能。选定按行键（类目|描述）写入
    ext.kp_picks 跨轮持久；客户改过该行则键失配自动作废。
    """
    ctx = _TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "select_kp_parts 仅在任务期的配件选配环节可用"}
    rows_ctx = {str(r.get("row_key") or ""): r
                for r in (ctx.get("kp_rows_ctx") or []) if isinstance(r, dict)}
    if not rows_ctx:
        return {"ok": False, "error": "no_unmatched_rows",
                "message": "当前没有待选定的部件行"}
    picks = (args or {}).get("picks")
    if not isinstance(picks, list) or not picks:
        return {"ok": False, "error": "invalid_args",
                "message": "参数 picks 必须是数组：[{row, part_id|name, reason}]，row 用行清单里的行键"}
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        return {"ok": False, "error": "invalid_args", "message": "登记表上下文缺失"}
    index = ctx.get("kp_search_index") or {}
    kp_picks = dict(ext.get("kp_picks") or {})
    results = []
    declared = False
    for p in picks:
        if not isinstance(p, dict):
            continue
        row_key = str(p.get("row") or "").strip()
        row_info = rows_ctx.get(row_key)
        pid = str(p.get("part_id") or "").strip()
        name = str(p.get("name") or "").strip()
        if row_info is None:
            # AI=配置器：大脑决定新增类目（如 HBA/Bridge/NVSwitch）时可带 category/spec
            # 声明一个尚不在清单里的行，行键=类目|描述；声明进 kp_config 跨轮持久。
            cat = str(p.get("category") or "").strip()
            spec = str(p.get("spec") or p.get("description") or "").strip()
            if "|" in row_key:
                cat = cat or (row_key.split("|", 1)[0].strip())
                spec = spec or (row_key.split("|", 1)[1].strip())
            if not cat:
                results.append({"row": row_key, "ok": False, "error": "row_not_found",
                                "message": "行键不在待选行清单内，且未提供类目无法新增"})
                continue
            row_info = {"row_key": row_key, "category": cat,
                        "description": spec or cat, "qty": 1}
            config = list(ext.get("kp_config") or [])
            if not any((str(r.get("category") or "").strip() == cat
                        and str(r.get("spec") or r.get("description") or "").strip() == (spec or cat))
                       for r in config):
                config.append({"category": cat, "spec": spec or cat, "qty": 1})
                ext["kp_config"] = config
                declared = True
        cat_key = str(row_info.get("category") or "").strip().lower()
        bucket = index.get(cat_key) or {}
        if not bucket:
            results.append({"row": row_key, "ok": False, "error": "not_searched",
                            "message": f"类目 {cat_key} 尚未检索——先调 search_kp_parts 查询该类目候选"})
            continue
        hit = None
        if pid:
            hit = bucket.get(pid)
        if hit is None and name:
            hit = bucket.get(name.lower())
        if hit is None:
            results.append({"row": row_key, "ok": False, "error": "not_in_search_results",
                            "candidates": [v.get("name") for v in list(bucket.values())[:8]
                                           if isinstance(v, dict) and isinstance(v.get("name"), str)],
                            "message": "料号不在已检索结果内——只能从 search_kp_parts 的结果中选取"
                                       "（可换关键词再检索）"})
            continue
        # 组合申报（qty）与替代申报（substitute）：白盒落 pick，落行时生效（apply_kp_picks）
        qty_raw = p.get("qty")
        qty = None
        if qty_raw is not None:
            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                qty = 0
            if qty < 1:
                results.append({"row": row_key, "ok": False, "error": "invalid_qty",
                                "message": "qty 必须是 ≥1 的整数（组合需求件数）"})
                continue
            if qty > 999:
                results.append({"row": row_key, "ok": False, "error": "invalid_qty",
                                "message": "qty 超出合理范围（>999），请核对组合方式"})
                continue
        substitute = bool(p.get("substitute"))
        # 目标层字段策略：ask/must_ask 类目（AI 反问）不落地锁定，登记为「AI 推荐」供确认卡
        # 标推荐——大脑仍可表达选型意图，但确定性落地=客户点选确认（候选取服务端留底）。
        ask_cats = set(ctx.get("kp_ask_cats") or [])
        row_cat = str(row_info.get("category") or "")
        if row_cat and row_cat in ask_cats:
            _rec = dict(ext.get("kp_recommend") or {})
            _rec_entry = {"part_id": str(hit.get("part_id") or ""),
                          "name": str(hit.get("name") or ""),
                          "price": hit.get("price"),
                          "currency": str(hit.get("currency") or "RMB"),
                          "reason": str(p.get("reason") or "").strip()}
            if qty is not None:
                _rec_entry["qty"] = qty
            _rec[row_key] = _rec_entry
            ext["kp_recommend"] = _rec
            results.append({"row": row_key, "ok": True, "recommended": {
                "part_id": str(hit.get("part_id") or ""), "name": str(hit.get("name") or "")}})
            continue
        pick_entry = {
            "part_id": str(hit.get("part_id") or ""),
            "name": str(hit.get("name") or ""),
            "price": hit.get("price"),
            "currency": str(hit.get("currency") or "RMB"),
            "reason": str(p.get("reason") or "").strip(),
        }
        if qty is not None:
            pick_entry["qty"] = qty
        if substitute:
            pick_entry["substitute"] = True
        kp_picks[row_key] = pick_entry
        results.append({"row": row_key, "ok": True,
                        "selected": {"part_id": str(hit.get("part_id") or ""),
                                     "name": str(hit.get("name") or "")}})
    ok_rows = [r for r in results if r.get("ok")]
    if ok_rows or declared:
        ext["kp_picks"] = kp_picks
        save = ctx.get("save")
        if callable(save):
            save()
    recs = [r for r in results if r.get("recommended")]
    locked = [r for r in results if r.get("selected")]
    if recs and locked:
        msg = (f"已锁定 {len(locked)}/{len(results)} 行真实料号；另有 {len(recs)} 行为 AI 建议"
               "（待客户确认，未落地为锁定）")
    elif recs:
        msg = f"已登记 {len(recs)} 行 AI 建议（待客户确认，未落地为锁定）"
    else:
        msg = f"已锁定 {len(ok_rows)}/{len(results)} 行真实料号"
    return {"ok": bool(ok_rows) and len(ok_rows) == len(results),
            "results": results,
            "message": msg,
            "current": _slots_view(ext)}


def tool_ask_user(args: dict) -> dict:
    """【任务期工具】大脑回合专用：把需要客户决策的问题升格为结构化选项卡。

    大脑的自由文本提问只能到达聊天区、没有交互通道（2026-09-05 用户实测：锁 4 行后
    问「1.92T 需确认接口」但没有任何可点的卡）。此工具把问题+选项登记进回合上下文，
    由 skill_chat 在引擎结束后统一弹卡；点击走 (slot,value) 留底匹配。row 绑定行键时，
    点击答案会合入该行描述（行键失配 → 旧 pick 自动作废 → 引擎重跑重选）。
    一回合一卡（与缺口卡的单焦点序列同口径）：已有待答问题再调即拒绝。
    """
    ctx = _TOOL_CTX.get() or {}
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "message": "ask_user 仅在任务期大脑回合可用"}
    q = str((args or {}).get("question") or "").strip()
    opts_in = (args or {}).get("options")
    if not q or not isinstance(opts_in, list) or not opts_in:
        return {"ok": False, "error": "invalid_args",
                "message": "参数必须是 {question, options:[{label,description?}], row?}，options 至少一项"}
    opts = []
    for o in opts_in[:4]:
        if isinstance(o, dict) and str(o.get("label") or "").strip():
            item = {"label": str(o.get("label")).strip()}
            if str(o.get("description") or "").strip():
                item["description"] = str(o.get("description")).strip()
            if o.get("recommended"):
                item["recommended"] = True
            if isinstance(o.get("pick"), dict):
                _pick = {k: v for k, v in o["pick"].items() if k in
                         ("part_id", "name", "price", "currency", "qty")}
                if _pick.get("name"):
                    item["pick"] = _pick
            opts.append(item)
        elif isinstance(o, str) and o.strip():
            opts.append({"label": o.strip()})
    if not opts:
        return {"ok": False, "error": "invalid_args", "message": "options 里没有有效的 label"}
    asks = ctx.get("brain_asks")
    if not isinstance(asks, list) or asks:
        return {"ok": False, "error": "one_ask_per_turn",
                "message": "本轮已登记待答问题；请把补充确认并进那个问题的选项或说明里"}
    asks.append({"question": q, "options": opts,
                 "row": str((args or {}).get("row") or "").strip()})
    return {"ok": True, "message": "问题已登记，本轮结束后会向客户弹出选项卡"}


def _fill_contract_brief() -> str:
    """登记契约简报：全部由目标层生成（登记表字段契约 + KP 大类 + 在售目录），零业务内容硬编码。

    换目标层（改登记表字段 / KP 大类 / 在售目录）此处自动跟随——这是 agent_fill 可复用
    到其他 skill 的接口要求：树干只描述形状，业务内容全部来自配置与数据。
    """
    spec = slot_spec()
    basic = [f"{str(s.get('key'))}({str(s.get('label') or s.get('key'))})"
             for s in spec if s.get("src_type") != "kp" and str(s.get("key") or "").strip()]
    kp_cats: list = []
    try:
        from app.services.requirement_slots import _load_kp_categories
        kp_cats = [str(c).strip() for c in (_load_kp_categories() or []) if str(c).strip()]
    except Exception:
        logger.exception("读取 KP 大类失败")
    example_slot, example_value = "", ""
    vocab_lines: list = []
    try:
        from app.services.catalog_options import catalog_whitelist
        wl = catalog_whitelist({}, {}, "")
        bucket_by_key = {"server_type": "types", "platform_type": "series", "chassis_form": "forms"}
        for s in spec:
            key = str(s.get("key") or "")
            if s.get("src_type") != "kp" and s.get("candidate_source") == "catalog":
                vals = [str(v) for v in (wl.get(bucket_by_key.get(key) or "") or []) if str(v).strip()]
                if not vals:
                    continue
                vocab_lines.append(f"{key}({str(s.get('label') or key)})：{' / '.join(vals)}")
                if not example_slot:
                    example_slot, example_value = key, vals[0]
    except Exception:
        logger.exception("读取目录词表失败")
    # 目录字段值域随契约下发：AI 直接写规范值（「2U 机架式」→「2U」），下游
    # _normalize_to_catalog 降级为兜底——不给词表，再强的模型也只能写客户原话。
    vocab = ""
    if vocab_lines:
        vocab = ("目录字段值域（客户说法能对应上时一律按这里的规范值登记，"
                 "对应不上就保留客户原话，由引擎判定是否反问）：\n" + "\n".join(vocab_lines))
    example_slots: dict = {}
    if example_slot:
        example_slots[example_slot] = example_value
    example = (
        "调用形状示例（仅示意调用形状，值按值域规则与客户原话填写）：\n```tool\n"
        + json.dumps({"name": "fill_requirement",
                      "args": {"slots": {**example_slots, "kp_rows": [
                          {"part_category": kp_cats[0] if kp_cats else "CPU",
                           "description": "<客户原话部件描述，原样保留型号/数量/规格>",
                           "qty": 2}]}}}, ensure_ascii=False)
        + "\n```")
    rules = (
        "登记规则：字段键用工具 schema 里的英文字段（" + "、".join(basic) + "）；"
        "部件一律登记进 kp_rows 数组，每项 {part_category, description, qty}，part_category 用配件大类名（"
        + ("、".join(kp_cats) if kp_cats else "见工具 schema")
        + "），description 按客户原话原样写，禁止拆改规格；客户没提的字段留空，"
        "禁止编造或默认填充；客户改口过的项带 replace=true。")
    return "\n\n".join(p for p in (vocab, rules, example) if p)


def make_agent_brain(*, persona: str = "", history: Optional[list] = None,
                     price_ok: bool = True, query_data_ok: bool = False,
                     model: Optional[str] = None, reasoning_effort: Optional[str] = None,
                     temperature: Optional[float] = None,
                     max_tokens: Optional[int] = None,
                     event_sink=None, tool_guard=None):
    """唯一大脑的节点回合执行器——一个 AI 角色 + 一条循环，零节点策略硬编码。

    引擎按节点回调 brain(node_key, node_cfg, ctx)。角色在本回合读到的全部「怎么干活」
    都来自该节点抽屉（DB node_configs）：使命=description、输出契约=target.artifacts
    （登记表契约由目标层生成）、工具=enabled_tools∪机制保底。本函数只做机制：
    ext 身份重绑、工具挂载、薄守卫（工具被拒→把真实返回喂回，不逼动作）、统一预算、
    旁白采集、跨回合工作记忆（brain_notes）、引擎产物键接线。
    （2026-09-07 取代 make_agent_brain/make_agent_brain/make_agent_brain 三份各自硬编码
    prompt/预算/守卫强度的策略包——09-02「唯一大脑」只合并了登记节点的隐藏 LLM，
    三个闭包当时只是被兼容进同一条循环，本体从未合并。）
    """
    # 引擎下游消费的旁白键（产物接线契约，非策略）
    NARR_KEYS = {"agent_fill": "fill_narration",
                 "model_reason": "model_narration",
                 "kp_reason": "kp_narration"}

    async def brain(node_key: str, node_cfg: dict, engine_ctx: dict) -> None:
        cfg = node_cfg if isinstance(node_cfg, dict) else {}
        # ── 抽屉三件套：使命 / 输出契约 / 工具（全部 DB 权威源）──
        node_prompt = str(cfg.get("description") or "").strip()
        if not node_prompt:
            from app.services import reasoning_node_contract
            node_prompt = str((reasoning_node_contract.node_defaults().get(node_key) or {})
                              .get("description") or "").strip()
        from app.services.skill_target_contract import first_artifact, format_contract
        if node_key == "agent_fill":
            # 登记表契约由目标层生成（字段/KP大类/目录值域全来自配置与数据）
            target_contract = _fill_contract_brief()
        else:
            target_contract = format_contract(first_artifact(cfg))
        bound = [str(t).strip() for t in (cfg.get("enabled_tools") or []) if str(t).strip()]
        mechs = MECHANISM_TOOLS.get(node_key) or []
        missing_mech = [m for m in mechs if m not in bound]
        if missing_mech:
            logger.warning("%s enabled_tools 缺机制工具 %s（DB 配置漂移，保底补回）",
                           node_key, missing_mech)
        tools = list(dict.fromkeys(bound + mechs))

        ext = engine_ctx.get("ext") if isinstance(engine_ctx.get("ext"), dict) else {}
        engine_ctx["ext"] = ext
        req_text = str(engine_ctx.get("requirement_text") or "").strip()

        # ── 节点输入数据视图（引擎事实摆上桌，零指令文案）──
        node_view: dict = {}
        if node_key == "agent_fill":
            try:
                from app.services.slot_contract import _missing_critical
                from app.services.capabilities import _slot_now_filled
                req_keys = {s.get("key") for s in slot_spec()
                            if s.get("src_type") != "kp" and s.get("key") != "server_model"}
                missing = [slot_label(m) for m in _missing_critical(ext)
                           if m in req_keys and not _slot_now_filled(ext, m)]
            except Exception:
                logger.exception("fill 回合缺口回读失败")
                missing = []
            node_view["还缺字段"] = missing
            try:
                from app.repository.system_config_repo import SystemConfigRepository
                _pol_repo = SystemConfigRepository()
                try:
                    _pol = _pol_repo.get_value("requirement_slots") or {}
                finally:
                    _pol_repo.close()
                have_kp = {str(r.get("part_category") or "").strip()
                           for r in (ext.get("kp_rows") or []) if isinstance(r, dict)}
                node_view["必登记部件未覆盖"] = [c for c in (_pol.get("kp_required") or [])
                                                if str(c).strip() and str(c).strip() not in have_kp]
            except Exception:
                logger.exception("必登记部件策略回读失败")
        elif node_key == "model_reason":
            pool = [c for c in (engine_ctx.get("baselines_pool") or []) if isinstance(c, dict)][:12]
            cand_view = []
            for c in pool:
                item = {
                    "model_id": str(c.get("server_model_id") or c.get("id") or ""),
                    "name": str(c.get("name") or ""),
                    "type": str(c.get("server_type_name") or ""),
                    "series": str(c.get("series") or ""),
                    "form": str(c.get("form") or ""),
                    "use": str(c.get("use") or ""),
                }
                if c.get("recommend_level") and c.get("recommend_level") != "neutral":
                    item["recommend"] = f"{c.get('recommend_level')}：{c.get('selling_points') or ''}"
                if price_ok and c.get("total_price") is not None:
                    item["price"] = c.get("total_price")
                for cap in ("gpu_slots", "max_dimm", "max_cpu"):
                    if c.get(cap) is not None:
                        item[cap] = c[cap]
                cand_view.append(item)
            node_view["候选机型池（唯一合法取值域）"] = cand_view
        elif node_key == "kp_reason":
            from app.services.part_selector import kp_row_key
            # 目标层字段策略：配件行级 AI 反问类目（抽屉 fields ask=true；试运行一键模式跳过）
            ask_cats = kp_ask_categories(cfg)
            if engine_ctx.get("force_complete"):
                ask_cats = []
            rows_ctx = []
            for p in (engine_ctx.get("kp_parts") or []):
                if isinstance(p, dict) and p.get("unmatched"):
                    cat = str(p.get("category") or "").strip()
                    desc = str(p.get("request_spec") or "").strip() or cat
                    if cat:
                        rows_ctx.append({"row_key": kp_row_key(cat, desc), "category": cat,
                                         "description": desc, "qty": p.get("qty") or 1})
            # 已锁定行随行清单下发（纯数据）：不给这份，大脑会把看不见的已锁行说成
            # 「候选池为空/无匹配」（2026-09-05 实测幻觉）
            locked_rows = [{
                "category": str(p.get("category") or ""),
                "description": str(p.get("request_spec") or "").strip() or str(p.get("category") or ""),
                "qty": p.get("qty") or 1,
                "selected": str(p.get("name") or ""),
            } for p in (engine_ctx.get("kp_parts") or [])
              if isinstance(p, dict) and not p.get("unmatched") and str(p.get("category") or "").strip()]
            node_view["已锁定的部件行（已落地，无需再处理）"] = locked_rows
            node_view["待选型行清单（row 即行键）"] = rows_ctx
            if ask_cats:
                node_view["AI 反问类目（客户决策，不要代选锁定，调 ask_user 升格选项卡）"] = ask_cats

        # ── 上下文：登记表现状 + 跨回合工作记忆（动态数据进 user 尾，system 逐字节稳定）──
        context_block = "\n\n".join([p for p in (
            "当前线索登记表：\n" + json.dumps(_slots_view(ext), ensure_ascii=False),
            "近期回合工作记录（你已做过的检索/提交/问询，勿重复劳动）：\n"
            + "\n".join(str(n) for n in (engine_ctx.get("brain_notes") or [])),
        ) if p])
        user_msg = ("【客户需求原文】\n" + (req_text or "（无）")
                    + ("\n\n【本节点输入数据】\n" + json.dumps(node_view, ensure_ascii=False)
                       if node_view else ""))

        sys_prompt = "\n\n".join([p for p in (
            persona,
            node_prompt,
            target_contract,
        ) if p])

        narration: list = []
        async def _capturing_sink(payload):
            sub = (payload or {}).get("sub") or {}
            if sub.get("kind") == "chunk" and sub.get("delta"):
                narration.append(sub["delta"])
            if event_sink:
                await event_sink(payload)

        # ── 工具上下文挂载：通用键 + 节点机制键 ──
        tool_ctx = {**_TOOL_CTX.get(), "ext": ext, "task_active": True, "price_ok": bool(price_ok)}
        kp_search_index: dict = {}
        series = str(((engine_ctx.get("_locked_baseline") or {}).get("series")) or "")
        if node_key == "model_reason":
            tool_ctx["model_pool"] = [c for c in (engine_ctx.get("baselines_pool") or [])
                                      if isinstance(c, dict)]
        elif node_key == "kp_reason":
            # 检索接地索引：回合内由 search_kp_parts 累积（服务端真相）；跨回合经
            # engine_ctx 续传——上回合检索过的类目下回合直接复用，不再重复查库
            kp_search_index = dict(engine_ctx.get("kp_search_index") or {})
            tool_ctx.update(kp_rows_ctx=node_view.get("待选型行清单（row 即行键）") or [],
                            kp_series=series,
                            kp_search_index=kp_search_index,
                            kp_ask_cats=node_view.get(
                                "AI 反问类目（客户决策，不要代选锁定，调 ask_user 升格选项卡）") or [],
                            brain_asks=[a for a in (_TOOL_CTX.get().get("brain_asks") or [])
                                        if isinstance(a, dict) and a.get("question")])
        _TOOL_CTX.set(tool_ctx)
        if _TOOL_CTX.get().get("ext") is not ext:
            logger.error("%s 回合工具上下文与引擎 ext 身份不一致：工具写入将丢失"
                         "（阶段函数不得复制重赋 ext）", node_key)

        # ── 统一预算：一套数字，不再三份各写各的 ──
        loop_kwargs = dict(
            config={"enabled_tools": tools},
            system_prompt=sys_prompt, allowed_tool_ids=tools,
            history=history or [], model=model, event_sink=_capturing_sink,
            tool_guard=tool_guard, max_iterations=10,
            llm_timeout=120.0, llm_reasoning_effort=reasoning_effort,
            llm_max_tokens=max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else None,
            # 健康思考常达数千字符（deepseek reasoning 偶发 8-10k），只拦 >12k 且零正文
            # 的病态深思考轮；配合下方墙钟兜底。
            llm_thinking_budget=12000,
            llm_temperature=temperature if isinstance(temperature, (int, float)) else 0.0,
            context_block=context_block,
        )

        # ── 薄守卫：工具被拒 → 把工具真实返回喂回让大脑自行修正（≤2 次重试）；
        # 无工具调用/全部通过 → 收敛。不逼动作、不纠偏散文——模型交回什么引擎接什么。
        # 墙钟 300s：到点不再发起新尝试，未完成部分交引擎白盒呈现。
        def _last_rejection(r) -> Optional[dict]:
            last_bad = None
            for c in ((r or {}).get("tool_calls_log") or []):
                res = (c or {}).get("result")
                if isinstance(res, dict) and res.get("ok") is False:
                    last_bad = res
            return last_bad

        result: dict = {}
        try:
            feedback = ""
            deadline = time.monotonic() + 300.0
            for attempt in range(3):
                if attempt > 0:
                    if time.monotonic() >= deadline:
                        await _emit_brain_status(_capturing_sink,
                                                 "耗时较长，未完成部分交系统按现状继续")
                        break
                    await _emit_brain_status(_capturing_sink,
                                             "工具校验未通过，附上工具真实返回重试中…")
                msg = user_msg if attempt == 0 else \
                    user_msg + "\n\n【工具返回（最近一次未通过校验，可据其修正参数重试或换路径）】\n" + feedback
                result = await run_stream_chat_loop(msg, **loop_kwargs)
                bad = _last_rejection(result)
                if bad is None:
                    break
                feedback = json.dumps(bad, ensure_ascii=False)[:500]
        except Exception:
            logger.exception("%s 大脑回合失败，未完成部分保持白盒呈现", node_key)

        # ── 产物接线（引擎契约键）+ 跨回合工作记忆追加 ──
        narr_key = NARR_KEYS.get(node_key)
        if narr_key:
            engine_ctx[narr_key] = "".join(narration).strip()
        if node_key == "model_reason":
            for c in reversed((result or {}).get("tool_calls_log") or []):
                if (c or {}).get("name") != "select_model":
                    continue
                res = c.get("result")
                if isinstance(res, dict) and res.get("ok"):
                    engine_ctx["model_pick"] = dict(res.get("selected") or {})
                    engine_ctx["model_pick_reason"] = str(res.get("reason") or "")
                break
        elif node_key == "kp_reason":
            engine_ctx["kp_asks"] = [a for a in (_TOOL_CTX.get().get("brain_asks") or [])
                                     if isinstance(a, dict) and a.get("question")]
            engine_ctx["kp_search_index"] = kp_search_index
        else:
            from app.services.capabilities import _enrich_agent_semantic
            _enrich_agent_semantic(ext, cfg, req_text)
            engine_ctx["ext"] = ext
        if (result or {}).get("tool_calls_log"):
            note = _brain_note_summary(node_key, result)
            engine_ctx["brain_notes"] = list(engine_ctx.get("brain_notes") or [])[-2:] + [note]
    return brain


def _merged_narration(result_ctx: dict) -> str:
    """回合旁白合流：登记 + 机型选定 + 配件选定旁白按发生顺序拼接（都经引擎产物回传）。"""
    parts = [str((result_ctx or {}).get(k) or "").strip()
             for k in ("fill_narration", "model_narration", "kp_narration")]
    return "\n\n".join(p for p in parts if p)


# ── 主入口：一条用户消息 → 角色 ReAct 循环（→ 引擎 → 缺口转述/产物汇报）──────

async def handle_skill_chat_turn(
    thread_id: str,
    user_text: str,
    colleague: Optional[dict],
    chat_system_prompt: str,
    history: list,
    user: Optional[dict] = None,
    opportunity_id: Optional[str] = None,
    option_slot: Optional[str] = None,
    event_sink: Optional[Callable[[dict], Any]] = None,
    governance_guard: Optional[Callable[[str, dict, Any], Any]] = None,
    emit_input_card: Optional[Callable[[str, dict], Any]] = None,
    card_selections: Optional[list] = None,
    force_submit: bool = False,
    skill_phase_hint: str = "",
    allow_submit: bool = True,
    enable_clarity: Optional[bool] = None,
) -> Optional[dict]:
    """角色对话脑主循环。返回引擎终态 dict（done 时含 artifact 供上层做落库收尾），无引擎时返回 None。

    emit_input_card(question_text, gap)：上层把它渲染成结构化选项卡（UI 数据=缺口，文案=角色）。
    """
    from app.services.skill_phases import KP_MODE_OPTIONS
    from app.services.skill_plan_runtime import engine_result_of, run_skill_plan_core

    role_key = (colleague or {}).get("role_key") or "assistant"
    response_profile = (colleague or {}).get("response_profile") \
        if isinstance((colleague or {}).get("response_profile"), dict) else {}
    role_reasoning_effort = response_profile.get("reasoning_effort")
    role_temperature = response_profile.get("temperature")
    role_max_tokens = response_profile.get("max_tokens")
    if not isinstance(role_max_tokens, int) or role_max_tokens <= 0:
        role_max_tokens = None
    # 任务大脑（登记/选型/配件/缺口转述/收尾）是接地工具任务：协议、候选池、登记表全在
    # prompt 里，深思考无增益只烧墙钟（2026-09-05 实测：同体量 prompt 默认档 19.4s vs
    # low 档 6.9s）。默认低档，员工 response_profile 显式配置仍可覆盖；PROPOSING 确认轮
    # 保持 role_reasoning_effort 不动（提交决策不吃默认降档）。
    task_reasoning_effort = role_reasoning_effort or "low"
    mem = _load_mem(thread_id, role_key)
    ext = dict(mem.get("ext") or {})
    # 数据边界（步骤1）：query_data 的物理权限源；缺省时 normalize 出 deny_all
    from app.services.data_boundary import colleague_price_ok, normalize_boundary
    price_ok = colleague_price_ok(colleague or {})
    boundary = normalize_boundary(colleague or {})
    # query_data 试点门控：角色 tool_ids 显式勾选才挂（试点只开方案助手）
    has_query_data = isinstance((colleague or {}).get("tool_ids"), list) \
        and "query_data" in (colleague or {}).get("tool_ids")

    # Skill 画布配置提前加载：引擎执行与提议预告共用同一份 node_configs（数据驱动）
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="需求分析")
    finally:
        repo.close()
    if not flow:
        return {"kind": "error", "reply": "需求分析流程未配置，请联系管理员。"}
    flow_configs = dict(flow.get("node_configs") or {})
    flow_title = str(flow.get("name") or "") or "配置任务"

    # 结构化选项点击（含逐项卡提交/表单批量）：按 (slot,value) 匹配发卡时持久化的原始选项，
    # 带 signal 载荷的原样直传落槽（消灭「构造字符串→再解析」）；qty 为 stepper 数量参数，
    # 服务端按机箱能力 clamp 后克隆 signal；留底未命中且为配件槽 → 自由型号走目录模糊匹配。
    # 委托/改口等语义仍由角色在对话里处理（不匹配留底卡时走旧路径）。
    raw_selections: list[tuple[str, str, int]] = []
    if isinstance(card_selections, list) and card_selections:
        for s in card_selections:
            if isinstance(s, dict) and str(s.get("slot") or "").strip() \
                    and str(s.get("value") or "").strip():
                try:
                    q = int(s.get("qty") or 0)
                except (TypeError, ValueError):
                    q = 0
                raw_selections.append((str(s["slot"]).strip(), str(s["value"]).strip(), max(0, q)))
    elif str(option_slot or "").strip() not in ("", "general") and user_text.strip():
        raw_selections.append((str(option_slot).strip(), user_text.strip(), 0))
    elif user_text.strip() and "\n" not in user_text and len(user_text.strip()) <= 30 \
            and (mem.get("last_card") or {}).get("options"):
        # 打字答案追加路（Claude Code 式「答案只追加不重derive」）：pending 选项卡在场 +
        # 短文本精确命中唯一槽位的选项值/标签 → 视同点选确定性落槽。不命中/命中多个槽/
        # 长文本（可能是新需求而非答案）→ 照旧走 fill 大脑全量理解，绝不吞新信息。
        _t = user_text.strip()
        _hits: dict[str, tuple] = {}
        for o in ((mem.get("last_card") or {}).get("options") or []):
            if isinstance(o, dict) and _t in (str(o.get("value") or ""), str(o.get("label") or "")):
                _hits.setdefault(str(o.get("slot") or ""), (str(o.get("slot") or ""), str(o.get("value") or ""), 0))
        if len(_hits) == 1:
            raw_selections.append(next(iter(_hits.values())))

    click_note = ""
    click_labels: list[str] = []
    ask_answers: list[str] = []
    had_pending_card = bool((mem.get("last_card") or {}).get("options"))
    for selected, value, want_qty in raw_selections:
        try:
            signal = _match_card_signal(mem, selected, value)
            if signal is None:
                signal = _manual_model_signal(mem, selected, value)
            if signal is None and selected == "brain_ask":
                signal = _brain_ask_manual_signal(mem, value)
            if signal:
                if want_qty:
                    signal = _signal_with_qty(
                        signal, want_qty, (mem.get("last_card") or {}).get("pick_meta") or {})
                from app.services.slot_contract import apply_structured_slots
                apply_structured_slots(ext, signal, value)
                click_labels.append(canonical_key(selected) + (f"×{want_qty}" if want_qty else ""))
                # 点选=客户亲口确认：写确认标记（凡推断必求证的求证侧），值被改写即失效
                ext.setdefault("confirmed_slots", {})[canonical_key(selected)] = value
            elif selected == "brain_ask":
                # 大脑提问卡的口头回答（未绑行）：不是槽位信号，落对话由角色语义消化，
                # 不进 click_labels（不触发点选快速路——答案需要大脑理解而非确定性续跑）。
                ask_answers.append(value)
            else:
                from app.services.capabilities import _apply_extracted_slots
                _apply_extracted_slots(ext, {selected: value}, allow_overwrite=True)
                click_labels.append(f"{canonical_key(selected)}={value}")
                ext.setdefault("confirmed_slots", {})[canonical_key(selected)] = value
        except Exception:
            logger.exception("选项落槽失败 slot=%s", selected)
    if click_labels:
        click_note = "（用户点击了选项，已登记 " + "；".join(click_labels) + "）"
    if ask_answers:
        ask_note = "（用户回答了确认卡：" + "、".join(ask_answers) + "）"
        click_note = (click_note + " " + ask_note).strip() if click_note else ask_note
    # 点选快速路径：点击命中且有在途选项卡 → 客户意图无歧义（继续任务，规则2c），
    # 跳过「角色决定是否提交」的 ReAct 轮，系统直接续跑引擎——根治「已登记/正在处理」
    # 口头空转不推进（模型说了提交但没调工具）。
    click_fast_path = bool(click_labels) and had_pending_card

    save = lambda: _save_mem(thread_id, role_key, {**mem, "ext": ext})  # noqa: E731
    state = {"submit": False}
    _TOOL_CTX.set({"ext": ext, "user_text": user_text, "save": save, "price_ok": price_ok,
                   "boundary": boundary, "role_key": role_key, "event_sink": event_sink,
                   "on_submit": lambda: state.__setitem__("submit", True),
                   "allow_submit": bool(allow_submit),
                   # fill_requirement 是任务期工具：普通对话回合恒不可用（登记回合内由 brain 置 True）
                   "task_active": False})

    # 提示词分态：普通聊天/提议回合不给登记表视图、不给流程内容（进任务前不碰目标表）。
    # 流程预告只在 PROPOSING 阶段指令里（colleague_turn_service 注入）；登记表只在登记回合（make_agent_brain）。
    system_prompt = "\n\n".join([
        chat_system_prompt,
        requirement_prompt(None, price_ok=price_ok, query_data_ok=has_query_data),
    ]).strip()
    if skill_phase_hint:
        system_prompt = system_prompt + "\n\n" + skill_phase_hint
    loop_tools = ["submit_registration", "catalog_search"]
    if has_query_data:
        loop_tools.append("query_data")

    reply = ""
    if force_submit or click_fast_path:
        # 已同意（试运行直启/任务续跑）或点选快速路：跳过聊天轮直接进引擎——
        # 输入即上下文，登记与说明由引擎的 agent_fill 大脑回合负责（流式可见）。
        # 旧实现在这里先跑一段自由聊天再进引擎：旁白提问会被缺口卡顶掉（09-03 实测 UX 事故），
        # 且每轮多烧一次 LLM（60s+）。
        state["submit"] = True
        logger.info("skill chat force/fast: 跳过聊天轮直接续跑引擎 thread=%s force=%s hits=%d",
                    thread_id, bool(force_submit), len(click_labels))
    else:
        # 确认轮（PROPOSING）：大脑正常对话决定是否提交（同意制）
        from app.services.llm_trace import reset_trace_ctx, set_trace_ctx
        _tk = set_trace_ctx(node_type="skill_propose", opportunity_id=thread_id, role_key=role_key)
        try:
            result = await run_stream_chat_loop(
                (user_text + ("\n" + click_note if click_note else "")).strip(),
                {"enabled_tools": loop_tools},
                system_prompt=system_prompt,
                allowed_tool_ids=loop_tools,
                history=history,
                model=(colleague or {}).get("model_override") or None,
                event_sink=event_sink,
                tool_guard=governance_guard,
                max_iterations=6,
                # 断连止损：中转半死连接最多烧 60s；推理档位/温度取员工 response_profile，不在这里硬编码
                llm_timeout=60.0,
                llm_reasoning_effort=role_reasoning_effort,
                llm_temperature=role_temperature if isinstance(role_temperature, (int, float)) else 0.2,
            )
        finally:
            reset_trace_ctx(_tk)
        reply = str((result or {}).get("answer") or "").strip() if isinstance(result, dict) else str(result or "").strip()
        save()
        logger.info(
            "skill chat react 结束 thread=%s iterations=%s submit=%s reply_len=%s",
            thread_id, (result or {}).get("iterations") if isinstance(result, dict) else "?",
            state["submit"], len(reply),
        )

    if not state["submit"]:
        logger.info("skill chat 返回 kind=chat thread=%s", thread_id)
        return {"kind": "chat", "reply": reply}

    # ── 引擎执行（登记表已提交；任务启动的可视化交给 pipeline_start/任务胶囊）──
    from app.services.slot_contract import canonical_get

    # 场景证据用累计文本判断：登记表草稿 + 本句
    from app.services.portal_flow_adapter import build_requirement_text
    full_text = build_requirement_text(opportunity_id, user_text) if opportunity_id else user_text
    # 冻结守卫（_freeze_requirement）按「机型名是否出现在需求文本」剥臆造机型；
    # 多轮对话里机型是早前轮次点选/口述的，本句（如"256G内存"）不会含机型名，
    # 只用本句会把已确认机型剥掉 → 机型问题无限重弹。近期用户原话并入比对基准。
    prior_user = [str((m or {}).get("content") or "").strip() for m in (history or [])
                  if (m or {}).get("role") == "user" and str((m or {}).get("content") or "").strip()]
    if prior_user:
        full_text = "\n".join(prior_user + [full_text])

    # 唯一大脑（一个 AI 角色 + 一条循环）：构造一次，跨节点连续服务。
    # 节点差异全部由抽屉（node_cfg：description/enabled_tools/target.artifacts）驱动，
    # 本处不再存在任何按节点分装的策略包。
    role_name = str((colleague or {}).get("name") or role_key)
    agent_brain = make_agent_brain(
        persona=f"你是 AI 同事「{role_name}」，正在执行「{flow_title}」任务，对客户的说明保持专业简洁。",
        history=history,
        price_ok=price_ok, query_data_ok=has_query_data,
        model=(colleague or {}).get("model_override") or None,
        reasoning_effort=task_reasoning_effort,
        temperature=role_temperature,
        max_tokens=role_max_tokens,
        event_sink=event_sink, tool_guard=governance_guard,
    )

    async def node_brain(node_key: str, node_cfg: dict, engine_ctx: dict) -> None:
        from app.services.llm_trace import reset_trace_ctx, set_trace_ctx
        token = set_trace_ctx(node_type=f"skill_{node_key}", opportunity_id=thread_id, role_key=role_key)
        try:
            await agent_brain(node_key, node_cfg, engine_ctx)
        finally:
            reset_trace_ctx(token)

    engine_ctx = {
        "requirement_text": full_text,
        "ext": ext,
        "history": history,
        "business_mode": "opportunity_flow" if opportunity_id else "conversation",
        "opportunity_id": opportunity_id or thread_id,
        "operator_name": (user or {}).get("name") or (user or {}).get("user_id") or "",
        "output_kind": "bom_scheme_draft",
        # 试运行反问开关（输入节点 enableClarity）：开关关 → 跳过策略反问一键出方案；
        # 开/未传（正常聊天恒未传）→ 按目标层策略反问。策略=目标层弹窗勾选的必填项与缺口。
        "force_complete": (enable_clarity is False),
        "llm_model": (colleague or {}).get("model_override") or None,
        "price_access": price_ok,
        # 点选轮结构化信号已落槽：引擎跳过登记回合，纯确定性续跑（点选 ack 延迟 ~2s）
        "skip_fill_round": bool(click_fast_path),
        # 跨回合工作记忆：近几个大脑回合的检索/提交/问询轨迹。治回合失忆——模型每轮
        # 原来只看登记表快照，自己上轮检索过什么、哪次提交被拒全不知道，于是重复检索、
        # 重复试错（2026-09-07 实测：每轮 KP 6~14k thinking token 大半在重想全表）。
        "brain_notes": list(mem.get("brain_notes") or [])[-3:],
    }
    # 回合级放弃式超时（2026-09-06）：relay 黑洞挂死时，内层 wait_for 的"取消完成"
    # 本身也可能被黑洞拖住（httpx 清理在无响应连接上无法收尾）。放弃式=到点后
    # cancel 但【不等待】取消完成，任务成为弃置任务（abandoned），主流程立刻
    # 走缺配征询暂停——宁可弃任务，不可无限静默。正常完成时任务已 done，零开销。
    _plan_task = asyncio.ensure_future(run_skill_plan_core(
        engine_ctx, flow_configs, event_sink, title=flow_title, brain=node_brain))
    _done, _pending = await asyncio.wait({_plan_task}, timeout=900.0)
    if _pending:
        _plan_task.cancel()
        logger.error("需求分析回合超过 900s 硬上限（relay 黑洞），放弃回合任务并转入缺配暂停")
        engine_ctx["engine_gaps"] = [{
            "slot": "kp_unmatched", "reason_code": "kp_timeout",
            "question": "需求分析流程耗时异常（引擎与模型服务之间的连接黑洞），已中止本轮。"
                        "请点击「重新继续分析」重试。",
            "options": [{"label": "重新继续分析", "value": "重新继续分析",
                         "group": "如何处理",
                         "signal": {}}],
        }]
        engine_ctx["awaiting_input"] = True
        result_ctx = engine_ctx
    else:
        result_ctx = _plan_task.result()
    # 引擎会就地完善登记表（信号补抽/归一会替换 ext 对象），回存保证下一轮角色看到最新状态；
    # brain_notes（跨回合工作记忆）一并并入 mem——后续缺口卡分支的 save 都以 mem 为底，
    # 不并进来会被旧值抹掉
    mem = {**mem, "ext": result_ctx.get("ext") or ext,
           "brain_notes": engine_ctx.get("brain_notes") or []}
    _save_mem(thread_id, role_key, mem)
    if result_ctx.get("fatal_error"):
        return {"kind": "error", "reply": f"需求分析执行失败：{result_ctx.get('fatal_error')}"}

    er = engine_result_of(result_ctx)
    engine_ctx["engine_result"] = er

    # 大脑提问卡（kp 大脑 ask_user 登记）：问题文案=大脑原话，选项=大脑给的 label。
    # row 绑定行键 → 选项带 kp_row_merge 信号（点击确定性更新该行描述→键失配→旧 pick
    # 作废→引擎重跑重选）；未绑行 → 纯口头回答，由角色在对话里消化。
    brain_asks = [a for a in (result_ctx.get("kp_asks") or [])
                  if isinstance(a, dict) and a.get("question")][:1]
    # 暂停缺口已携带同一提问（runtime 的 brain_ask gap）时不重复弹卡
    if any(str(g.get("reason_code") or "") == "brain_ask" for g in (er.get("gaps") or [])):
        brain_asks = []

    async def _emit_ask_card(ask: dict) -> list:
        if emit_input_card is None:
            return []
        ask_slot = "brain_ask"
        cards, opts = [], []
        for o in (ask.get("options") or []):
            label = str(o.get("label") or "").strip()
            if not label:
                continue
            cards.append({"label": label, "value": label,
                          "desc": str(o.get("description") or ""), "slot": ask_slot,
                          "group": "需要您确认",
                          **({"recommended": True} if o.get("recommended") else {})})
            entry = {"slot": ask_slot, "value": label}
            if str(ask.get("row") or "").strip():
                row_key = str(ask["row"]).strip()
                pk = o.get("pick")
                if isinstance(pk, dict) and str(pk.get("name") or "").strip():
                    entry["signal"] = {"kp_manual_pick": {"row": row_key, **{k: v for k, v in pk.items()
                                                                              if k in ("part_id", "name", "price", "currency", "qty")}}}
                elif o.get("absent"):
                    cat = str(o.get("absent") or "").strip() or (row_key.split("|", 1)[0].strip() if "|" in row_key else "")
                    entry["signal"] = {"kp_absent": [cat] if cat else []}
                else:
                    entry["signal"] = {"kp_row_merge": {"row": row_key, "answer": label}}
            opts.append(entry)
        if not cards:
            return []
        try:
            await emit_input_card(str(ask.get("question") or ""),
                                  {"question": str(ask.get("question") or ""),
                                   "options": cards, "slot_options": {ask_slot: cards},
                                   "why": "", "missing_fields": [ask_slot],
                                   "narration": _merged_narration(result_ctx)})
        except Exception:
            logger.exception("大脑提问卡广播失败")
            return []
        return opts

    if er.get("status") == "done":
        logger.info("skill chat 返回 kind=done thread=%s", thread_id)
        if brain_asks:
            ask_opts = await _emit_ask_card(brain_asks[0])
            if ask_opts:
                try:
                    _save_mem(thread_id, role_key, {**mem, "ext": result_ctx.get("ext") or ext,
                                                    "last_card": {"options": ask_opts}})
                except Exception:
                    logger.exception("大脑提问卡载荷持久化失败")
        return {"kind": "done", "reply": reply, "engine_ctx": result_ctx,
                "narration": _merged_narration(result_ctx)}

    # ── 缺口：逐条问（Claude Code 式）+ 旁白织入（S3）──
    # 引擎一次产出全部 L0 缺口（≤4，skill_phases.target_layer_gaps），但一轮只弹
    # 第一张卡；答完引擎恢复 → 下一缺口重新收敛再问（机型/配件段缺口天然后置单发）。
    # 旧版（S1）同轮批量弹 N 卡：实测用户点一张后兄弟卡齐塌、几秒后又重发未答卡，
    # 观感=顺序错乱（2026-09-06 实机+落库取证），改回一轮一问。每张卡自带 slot，
    # 点击/打字按 (slot,value) 路由。
    gaps = [g for g in (er.get("gaps") or []) if isinstance(g, dict)]
    if not gaps:
        logger.info("skill chat 返回 kind=error(未知引擎状态) thread=%s", thread_id)
        return {"kind": "error", "reply": "引擎返回了未知状态"}
    # 自选器上下文弹出缺口（机器数据不进转述 JSON），随 last_card 留底给 card-pick 端点
    pick_meta = None
    for g in gaps:
        if isinstance(g.get("pick_meta"), dict):
            pick_meta = g.pop("pick_meta")
            break

    # 已锁定机型随缺口下行（纯数据）：转述模型可自然带到问句里，用户全程看得见选型进展
    locked_model = str(((result_ctx.get("model_selection") or {}).get("name")) or "")
    if locked_model:
        lock_reason = str(result_ctx.get("lock_reason") or "")
        for g in gaps:
            g.setdefault("context", {})["locked_model"] = locked_model
            if lock_reason:
                g["context"]["lock_reason"] = lock_reason

    # S3 确认话+引问合一：登记大脑跑过的回合，旁白已按「确认已登记 + 引出还缺项」织入
    # （make_agent_brain 指令），卡问句直接用数据事实句，砍掉独立缺口转述 LLM 调用
    # （2026-09-05 实测 ~30s/次）。fill 大脑被跳过（点选/打字快速路，需要贴上下文的
    # ack 转述）或非 L0 缺口（机型/配件段）时保留转述调用——只对第一个缺口发一次。
    fill_nar = str(result_ctx.get("fill_narration") or "").strip()
    # 推荐制（2026-09-06 用户定调）：带选项的缺口必须过大脑话术——干巴巴列选项不需要
    # AI，大脑要给推断+推荐；只有开放回答缺口（无选项，如 kp_required）才退数据事实句
    skip_gap_ask = bool(fill_nar) and not any(g.get("options") for g in gaps)

    def _data_question(g: dict) -> str:
        """数据事实句兜底（非话术表）：告诉客户还缺什么，选项原样列出（label 优先）。"""
        # brain_ask 缺口（大脑 ask_user 升格的暂停）：问句=大脑原话，不经转述
        if g.get("reason_code") == "brain_ask" and str(g.get("question") or "").strip():
            return str(g["question"]).strip()
        if g.get("reason_code") == "inferred_confirm":
            cur = str(g.get("current") or "").strip()
            return f"已按需求推断：{slot_label(g.get('slot') or '')} = {cur or '（空）'}，请确认或改选"
        if g.get("slot") == "kp_required":
            cats = "、".join(g.get("cats") or [])
            return f"还需要确认：{cats} 部件的需求（如某类不需要请说明）"
        def _opt_text(o):
            return str(o.get("label")) if isinstance(o, dict) else str(o)
        options_text = " / ".join(_opt_text(o) for o in (g.get("options") or [])[:6])
        return f"还需要确认：{slot_label(g.get('slot') or '')}" + (f"（{options_text}）" if options_text else "")

    def _fix_kp_mode(g: dict, q: str) -> str:
        if g.get("slot") == "kp_mode" and not any(o in q for o in KP_MODE_OPTIONS):
            g["options"] = list(KP_MODE_OPTIONS)
            return q + "\n选项：" + " / ".join(KP_MODE_OPTIONS)
        return q

    question = ""
    gap_recommend = ""
    # brain_ask 缺口：问句=大脑原话（_data_question 直取），无需转述 LLM 再措辞
    if not skip_gap_ask and str(gaps[0].get("reason_code") or "") != "brain_ask":
        # 缺口转述=同一颗大脑的续话：带人设+近期对话+本轮角色已说的话，让问句贴上下文。
        # 只喂缺口 JSON 的无上下文转述=固定数据进固定话术出，事实上的硬编码模板。
        hist_tail = [dict(m) for m in (history or [])[-6:]
                     if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                     and str(m.get("content") or "").strip()]
        from app.services.skill_prompts import load_skill_prompts
        prompts = load_skill_prompts()
        ack_rule = ""
        if click_labels:
            ack_rule = str(prompts.get("gap_ack_template") or "").replace("<<CLICKS>>", "、".join(click_labels))
        gap_prompt = str(prompts.get("gap_ask_prompt") or "")
        ask_messages = [
            {"role": "system", "content": chat_system_prompt},
            *hist_tail,
            {"role": "assistant", "content": reply or ""},
            {"role": "user", "content": (gap_prompt
                        .replace("<<ACK_RULE>>", ack_rule)
                        .replace("<<GAP_DATA>>", json.dumps(gaps[0], ensure_ascii=False)))},
        ]
        try:
            from app.services import llm_client
            from app.services.llm_trace import record_llm_trace
            ask = None
            # 失败可见 + 重试一次：话术调用挂了就退化成干巴巴数据句（2026-09-06 实测），
            # 不许静默吞——失败必须落 trace，且重试一次再降级
            for _ga_attempt in (1, 2):
                _g_t0 = time.perf_counter()
                _g_pr = sum(len(str((m or {}).get("content") or "")) for m in ask_messages)
                try:
                    ask = await llm_client.chat_json(
                        ask_messages, model=(colleague or {}).get("model_override") or None,
                        temperature=role_temperature if isinstance(role_temperature, (int, float)) else 0.3,
                        timeout=30.0, max_attempts=1, reasoning_effort=task_reasoning_effort)
                    record_llm_trace(
                        node_type="skill_gap_ask", opportunity_id=thread_id, role_key=role_key,
                        duration_ms=int((time.perf_counter() - _g_t0) * 1000), prompt_chars=_g_pr,
                        response_chars=len(str(ask or "")), status="ok")
                    break
                except Exception as exc:
                    record_llm_trace(
                        node_type="skill_gap_ask", opportunity_id=thread_id, role_key=role_key,
                        duration_ms=int((time.perf_counter() - _g_t0) * 1000), prompt_chars=_g_pr,
                        status="error", error=str(exc)[:200])
                    if _ga_attempt == 2:
                        raise
                    logger.warning("缺口转述第 1 次失败，重试: %s", exc)
            if isinstance(ask, dict):
                question = str(ask.get("reply") or ask.get("question") or ask.get("content") or "").strip()
                # 推荐制（2026-09-06 用户定调）：大脑给出倾向选项 → 卡上标「推荐」
                gap_recommend = str(ask.get("recommend") or ask.get("recommend_value")
                                    or ask.get("recommend_label") or "").strip()
            if not question and isinstance(ask, str):
                question = ask.strip()
        except Exception as exc:
            logger.warning("缺口转述生成失败，退回数据兜底: %s", exc)
            question = ""
    questions = []
    for i, g in enumerate(gaps):
        q = (question if i == 0 else "").strip() or _data_question(g)
        questions.append(_fix_kp_mode(g, q))

    # 所有缺口都发结构化选项卡：一缺口一卡（问题文本随卡落库，选项为空 = 开放回答）；
    # 旁白只随第一张卡落库（emit_input_card 每收一次 narration 都会持久化一次）
    card_emitted = False
    card_opts: list = []
    shared_narration = _merged_narration(result_ctx)
    if emit_input_card is not None:
        # 一轮只发第一张卡（逐条问）：card_opts/last_card 只留可见卡的选项，
        # 点击快速路径 (slot,value) 与屏幕上的卡严格一致
        for gi, g in enumerate(gaps[:1]):
            slot_key = str(g.get("slot") or "general")
            group = slot_label(slot_key)
            cards = []
            for o in (g.get("options") or []):
                if isinstance(o, dict):
                    opt = {"label": str(o.get("label") or o.get("value") or ""),
                           "value": str(o.get("value") or o.get("label") or ""),
                           "desc": str(o.get("desc") or ""),
                           "slot": str(o.get("slot") or slot_key),
                           # 逃生项显式空组别（前端把非空组当卡头，逃生项不占组位）
                           "group": str(o.get("group") if o.get("group") is not None else group)}
                    # 推荐标记（推荐制）：大脑话术 JSON 的 recommend 命中 value/label
                    if gap_recommend and gap_recommend in (opt["value"], opt["label"]):
                        opt["recommended"] = True
                    if o.get("recommended"):
                        opt["recommended"] = True
                    # 数量元数据透传（前端 stepper 边界+实时总量显示，纯展示参数非 signal）
                    for k in ("qty", "qty_max", "unit_gb"):
                        v = o.get(k)
                        if isinstance(v, int) and v > 0:
                            opt[k] = v
                    cards.append(opt)
                    entry = {"slot": str(o.get("slot") or slot_key),
                             "value": str(o.get("value") or o.get("label") or "")}
                    sig = o.get("signal")
                    if isinstance(sig, dict) and sig:
                        entry["signal"] = sig
                    card_opts.append(entry)
                else:
                    cards.append({"label": str(o), "value": str(o), "desc": "",
                                  "slot": slot_key, "group": group})
                    card_opts.append({"slot": slot_key, "value": str(o)})
            q = questions[gi]
            try:
                _payload = {"question": q, "options": cards,
                            "slot_options": {slot_key: cards},
                            "why": "", "missing_fields": [slot_key],
                            "narration": (shared_narration if gi == 0 else "")}
                # 卡能力声明（2026-09-06 插头化）：parts_card=True → 前端渲染表单卡
                # （自选下拉+数量步进+手动型号+提交）；渲染器零业务词，能力全由数据声明
                if g.get("parts_card"):
                    _payload.update({"parts_card": True, "row": str(g.get("row") or ""),
                                     "qty": g.get("qty"), "qty_max": g.get("qty_max"),
                                     "unit_label": str(g.get("unit_label") or "")})
                await emit_input_card(q, _payload)
                card_emitted = True
            except Exception:
                logger.exception("选项卡广播失败 slot=%s", slot_key)
        # 结构化载荷随卡持久化到会话记忆：点击轮按 (slot,value) 匹配原样直传，
        # 服务端留底不信任客户端回传值。全量留底（含无 signal 的机型/逃生项）：
        # had_pending_card 是点击快速路径的判定条件，只留 signal 会让机型卡点击
        # 掉回 LLM 决策轮（点完又问「可以吗」）。ext 必须取引擎产物（补抽会替换
        # ext 对象），用本地旧对象会把引擎补好的信号从记忆里抹掉
        if card_opts:
            try:
                _save_mem(thread_id, role_key, {**mem, "ext": result_ctx.get("ext") or ext,
                                                "last_card": {"options": card_opts,
                                                              **({"pick_meta": pick_meta} if pick_meta else {})}})
            except Exception:
                logger.exception("选项卡结构化载荷持久化失败")
    # 缺口卡之外大脑还有提问（罕见并存）：并入同一份留底（(slot,value) 同域匹配）
    if brain_asks:
        ask_opts = await _emit_ask_card(brain_asks[0])
        if ask_opts:
            merged = (list(card_opts) if card_emitted else []) + ask_opts
            try:
                _save_mem(thread_id, role_key, {**mem, "ext": result_ctx.get("ext") or ext,
                                                "last_card": {"options": merged,
                                                              **({"pick_meta": pick_meta} if pick_meta else {})}})
            except Exception:
                logger.exception("大脑提问卡载荷持久化失败")
    logger.info("skill chat 返回 kind=gaps slots=%s card=%s skip_ask=%s thread=%s",
                [g.get("slot") for g in gaps], card_emitted, skip_gap_ask, thread_id)
    return {"kind": "gaps", "reply": (questions[0] if questions else ""), "gap": gaps[0],
            "gaps": gaps, "engine_ctx": result_ctx,
            "card_emitted": card_emitted,
            "narration": shared_narration}
