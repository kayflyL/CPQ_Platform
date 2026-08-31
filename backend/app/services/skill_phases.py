# -*- coding: utf-8 -*-
"""需求分析 Skill 的引擎阶段函数（纯执行，无对话能力）。

两器官架构（2026-08-28 宪法）：
1. 全系统同一时刻只有一个会思考的脑袋——对话期是 AI 角色，执行期是本引擎；
2. 引擎只产出**数据**（产物或缺口 {slot, options, reason_code}），绝不产出话术；
   "问什么"由业务数据决定，"怎么问"由角色决定——任何位置都不允许话术表/关键词清单；
3. 数据表只允许存业务事实（目录/案例/规格/规则），语言补丁一律禁止。

阶段顺序（代码强制）：normalize → model → kp_gate → kp → compose → output。
compose/output 在 skill_node_runtime（纯确定性）。
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from app.services.slot_contract import canonical_get, canonical_set, slot_label

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]

_UNSET = object()

# 配件意向的两个业务选项（唯一合法值；角色问完后必须用其中一个值落 kp_mode 槽）。
KP_MODE_NEED_PARTS = "需要配配件"
KP_MODE_L6_ONLY = "只要整机底座（L6）"
KP_MODE_OPTIONS = [KP_MODE_NEED_PARTS, KP_MODE_L6_ONLY]


def parse_kp_mode(raw: str) -> str:
    """kp_mode 槽 → 机器值：精确匹配业务选项；匹配不上返回空（引擎再次报缺口）。"""
    text = str(raw or "").strip()
    if text == KP_MODE_L6_ONLY or "底座" in text or "L6" in text.upper():
        return "l6_only"
    if text == KP_MODE_NEED_PARTS:
        return "need_parts"
    return ""


def model_signals_ready(ext: dict) -> bool:
    """机型选型的信号门槛：必须给了类型，或「系列+形态」齐备。"""
    has_type = bool(str(ext.get("server_type_name") or ext.get("server_type") or "").strip())
    series = str(ext.get("series") or ext.get("platform_type") or "").strip()
    form = str(ext.get("form") or ext.get("chassis_form") or "").strip()
    return bool(has_type) or bool(series and form)


def kp_args_from_ext(ext: dict, server_type_name: str = "") -> dict:
    """从结构化槽位确定性构造 select_parts 参数：有什么信号配什么件，绝不发明。"""
    args: dict[str, Any] = {}
    if server_type_name:
        args["server_type_name"] = server_type_name
    for key in ("cpu", "memory", "drives", "gpu", "raid", "psu"):
        val = ext.get(key)
        if isinstance(val, (list, dict)) and val:
            args[key] = val
    nic = ext.get("nic")
    if isinstance(nic, dict) and nic:
        args["nic"] = nic
    return args


# ── 缺口数据（引擎唯一的"反问"形态）──────────────────────────────────────

def _gap(slot: str, reason_code: str, options: Optional[list] = None) -> dict:
    return {"slot": slot, "reason_code": reason_code, "options": options or []}


def scene_gap(ext: dict) -> dict:
    return _gap("server_type", "scene_missing", catalog_whitelist_options(ext, only_key="server_type").get("server_type") or [])


def kp_mode_gap() -> dict:
    return _gap("kp_mode", "kp_mode_undecided", list(KP_MODE_OPTIONS))


def catalog_whitelist_options(ext: dict, only_key: Optional[str] = None) -> dict:
    """缺口选项：类型/系列/形态/数量取在售目录真实值（业务数据，非话术）。"""
    try:
        from app.services.capabilities import _catalog_whitelist
        wl = _catalog_whitelist({}, {}, "")  # 全量词汇表（传已确认值会按确认值收窄）
    except Exception:
        logger.exception("读取目录白名单失败")
        wl = {}
    keys = [only_key] if only_key else ["server_type", "platform_type", "chassis_form", "purchase_qty"]
    options: dict[str, list] = {}
    bucket = {"server_type": "types", "platform_type": "series", "chassis_form": "forms"}
    for key in keys:
        if key == "purchase_qty":
            options[key] = [{"label": str(n), "value": str(n), "slot": key, "group": slot_label(key)}
                            for n in (1, 2, 3, 5, 10)]
            continue
        src = bucket.get(key)
        if not src:
            continue
        values = [str(v) for v in (wl.get(src) or []) if str(v).strip()]
        if values:
            options[key] = [{"label": v, "value": v, "slot": key, "group": slot_label(key)} for v in values]
    return options


# ── 词汇/守卫（全部数据驱动）────────────────────────────────────────────

def _normalize_to_catalog(ext: dict) -> None:
    """把 series/form 自由文本归一到在售目录词汇表（仅词汇对齐，不做业务决定）。"""
    try:
        from app.services.capabilities import _catalog_whitelist
        wl = _catalog_whitelist({}, {}, "")
    except Exception:
        logger.exception("读目录词汇表失败")
        return
    for key, src in (("series", "series"), ("form", "forms")):
        val = str(ext.get(key) or "").strip()
        values = [str(v) for v in (wl.get(src) or []) if str(v).strip()]
        if not val or not values or val in values:
            continue
        low = val.lower()
        hits = [v for v in values if v.lower() in low or low in v.lower()]
        if len(hits) == 1:
            canonical_set(ext, key, hits[0])

def _default_qty(ctx: dict, ext: dict) -> None:
    """数量未指定默认 1 台（白盒假设，非阻塞）。"""
    if not canonical_get(ext, "purchase_qty"):
        canonical_set(ext, "purchase_qty", 1)
        ctx.setdefault("assumptions", []).append({"code": "qty_default", "slot": "purchase_qty", "value": 1})


# ── 阶段 1：槽位规范化（对话路径跳过 LLM；试运行路径才抽取）────────

async def phase_normalize_slots(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> None:
    """把 ctx.ext 规范化为引擎可执行的结构化槽位。

    对话路径（slots_provided=True）：角色已填表，守卫/归一/默认值不依赖 LLM；
    不再二次抽取（唯一大脑原则：填表是角色职责，引擎不抢跑）。
    试运行路径（无角色）：调 extract_requirement_slots 一次抽槽。
    """
    from app.services.slot_contract import _missing_critical

    _extract_calls = 0
    _extract_ms = 0.0

    async def _extract_once() -> dict:
        nonlocal _extract_calls, _extract_ms
        import time as _t
        _t0 = _t.perf_counter()
        from app.services.capabilities import extract_requirement_slots
        try:
            return await extract_requirement_slots(ctx, cfg or {}, broadcast)
        finally:
            _extract_calls += 1
            _extract_ms += (_t.perf_counter() - _t0) * 1000

    if not ctx.get("slots_provided"):
        res = await _extract_once()
        if not res.get("ok"):
            raise RuntimeError(f"需求抽取不可用：{res.get('error') or 'LLM 无响应'}")
    _filled = sum(1 for s in _PART_SIGNAL_SLOT.values() if (ctx.get("ext") or {}).get(s))
    ctx.setdefault("timings", {})["agent_fill_extract"] = {
        "calls": _extract_calls, "ms": round(_extract_ms, 1), "filled_signals": _filled,
    }
    logger.info("agent_fill extract calls=%s ms=%s filled_signals=%s",
                _extract_calls, round(_extract_ms, 1), _filled)

    ext = dict(ctx.get("ext") or {})
    _default_qty(ctx, ext)
    ctx["ext"] = ext
    ctx["blockers"] = list(_missing_critical(ext))
    try:
        from app.services.capabilities import _freeze_requirement
        _freeze_requirement(ctx, ext, str(ctx.get("requirement_text") or ""))
    except Exception as _e:
        logger.warning("_freeze_requirement 失败: %s", _e, exc_info=True)
_PART_SIGNAL_SLOT = {
    "CPU": "cpu", "Memory": "memory", "HDD/SSD": "drives",
    "GPU": "gpu", "NIC": "nic", "Raid card": "raid",
    "Power": "psu",
}



# ── 阶段 2：机型选型（目录查询 + 受约束选择，产出缺口而非提问）──────────────

def model_option_desc(c: dict, include_price: bool = True) -> str:
    bits = [str(c.get(key) or "").strip() for key in ("form", "series")]
    bits = [b for b in bits if b]
    # 机箱能力（目录事实）：选项卡上直接给出扩展上限，用户选机型时看得见「装得下多少」
    try:
        gs = int(c.get("gpu_slots") or 0)
        if gs > 0:
            bits.append(f"{gs}×GPU位")
    except (TypeError, ValueError):
        pass
    try:
        md = int(c.get("max_dimm") or 0)
        if md > 0:
            bits.append(f"{md}内存槽")
    except (TypeError, ValueError):
        pass
    try:
        mc = int(c.get("max_cpu") or 0)
        if mc > 1:
            bits.append(f"双路" if mc == 2 else f"{mc}路CPU")
    except (TypeError, ValueError):
        pass
    if include_price:
        try:
            if c.get("total_price"):
                bits.append(f"¥{float(c['total_price']):,.0f}")
        except (TypeError, ValueError):
            pass
    return " · ".join(bits)


def catalog_models_option_data(candidates: list[dict], limit: int = 6, include_price: bool = True) -> list[dict]:
    """候选机型 → 结构化选项数据（desc=形态/系列/价格，价格按权限），供选项面板与角色话术。"""
    out = []
    for c in candidates[:limit]:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        out.append({"label": name, "value": name, "desc": model_option_desc(c, include_price=include_price),
                    "slot": "server_model", "group": "机型"})
    return out


def model_gap(candidates: list[dict], include_price: bool = True) -> dict:
    """机型缺口：多候选且用户未指定 → 把选择权交给用户（机型选配是交互节点）。"""
    return _gap("server_model", "model_candidates",
                catalog_models_option_data(candidates, include_price=include_price))



def _lock_baseline(ctx: dict, baseline: dict, reason: str) -> None:
    ctx["baselines"] = [baseline]
    ctx["_locked_baseline"] = baseline
    ctx["lock_reason"] = reason
    ext = dict(ctx.get("ext") or {})
    for field in ("server_type_name", "series", "form"):
        val = str(baseline.get(field) or "").strip()
        if val:
            ext[field] = val
    if baseline.get("name"):
        canonical_set(ext, "server_model", str(baseline["name"]))
    ctx["model_selection"] = {
        "id": baseline.get("server_model_id") or baseline.get("id"),
        "name": baseline.get("name") or "",
        "server_type_name": baseline.get("server_type_name") or "",
        "series": baseline.get("series") or "",
        "form": baseline.get("form") or "",
    }
    req = dict(ctx.get("requirement") or {})
    for field in ("server_type_name", "series", "form"):
        val = str(baseline.get(field) or "").strip()
        if val:
            req[field] = val
    ctx["requirement"] = req
    ctx["ext"] = ext


def _model_cpu_hint(candidate: dict) -> str:
    """从机型 product_content 抽取处理器品牌/系列描述，供 AI 按需求 CPU 语义配对（非词表穷举）。"""
    try:
        pc = candidate.get("product_content")
        if isinstance(pc, dict):
            for s in (pc.get("specs") or []):
                if isinstance(s, dict) and str(s.get("key") or "").strip() in ("处理器", "CPU", "处理器型号"):
                    return str(s.get("value") or "").strip()
            tagline = str(pc.get("tagline") or "")
            if tagline:
                return tagline
    except Exception:
        pass
    return str(candidate.get("use") or "")


def _has_hw_signal(ctx: dict) -> bool:
    """需求是否含硬件选件信号（CPU/内存/盘/GPU/RAID/电源/网卡），用于决定是否强制 AI 语义选型。"""
    ext = dict(ctx.get("ext") or {})
    for k in ("cpu", "memory", "drives", "gpu", "raid", "psu", "nic"):
        v = ext.get(k)
        if isinstance(v, (list, dict)) and len(v):
            return True
    return False


async def _llm_pick_model(ctx: dict, candidates: list[dict], include_price: bool = True) -> Optional[tuple[int, str]]:
    """单次受约束选型：只许从候选里挑 id 并给理由；非法输出重试一次后放弃。"""
    import json as _json
    from app.services import llm_client
    short = [{"id": str(c.get("server_model_id") or c.get("id") or ""), "name": str(c.get("name") or ""),
              "type": str(c.get("server_type_name") or ""), "series": str(c.get("series") or ""),
              "form": str(c.get("form") or ""), "use": str(c.get("use") or ""),
              "cpu": _model_cpu_hint(c)} for c in candidates]
    if include_price:
        for item, c in zip(short, candidates):
            item["price"] = c.get("total_price")
    id_set = {c["id"] for c in short}
    messages = [
        {"role": "system", "content": ("你是服务器选型助手。根据需求从候选整机中选择最合适的一台，"
                                       "只能输出 JSON：{\"server_model_id\":\"候选中的id\",\"reason\":\"简短中文理由\"}。禁止编造 id。")},
        {"role": "user", "content": ("需求原文：\n" + str(ctx.get("requirement_text") or "") +
                                     "\n\n线索登记表：\n" + _json.dumps(
                                         {k: (ctx.get("ext") or {}).get(k) for k in
                                          ("server_type_name", "series", "form", "purchase_qty",
                                           "cpu", "memory", "drives", "gpu", "raid")},
                                         ensure_ascii=False, default=str) +
                                     "\n\n候选整机：\n" + _json.dumps(short, ensure_ascii=False))},
    ]
    for _attempt in range(2):
        try:
            data = await llm_client.chat_json(messages, model=ctx.get("llm_model") or None,
                                              temperature=0, timeout=60.0, max_attempts=1)
        except Exception as exc:
            logger.warning("model pick LLM failed: %s", exc)
            return None
        if not isinstance(data, dict):
            continue
        pid = str(data.get("server_model_id") or "").strip()
        if pid in id_set:
            return next(i for i, c in enumerate(short) if c["id"] == pid), str(data.get("reason") or "")
    return None



async def phase_model_reason(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> Optional[dict]:
    """机型阶段：纯结构化信号查目录；选择只来自候选集。返回缺口（数据）或 None。"""
    from app.api.candidate_search import select_models
    ext = dict(ctx.get("ext") or {})
    _normalize_to_catalog(ext)
    ctx["ext"] = ext
    signals_ready = model_signals_ready(ext)
    # 价格权限：聊天入口按角色传入（ctx.price_access）；试运行等未设置的入口默认可见
    include_price = bool(ctx.get("price_access", True))

    # 类型词表校验：登记的类型必须是目录真实类型，否则 select_models 的
    # type 词表失配会退化成全量查询（= 无关机型被 AI 乱配）。失配 → 场景缺口。
    filled_type = str(ext.get("server_type_name") or ext.get("server_type") or "").strip()
    if filled_type:
        try:
            from app.repository.server_catalog_repo import ServerCatalogRepository
            catalog_types = {str(t.get("name") or "").strip() for t in ServerCatalogRepository().list_types()}
        except Exception:
            logger.exception("读目录类型失败")
            catalog_types = set()
        if catalog_types and filled_type not in catalog_types:
            # 允许「系列+形态」齐备的路径继续（类型只是偏好）；纯类型信号失配 → 场景缺口
            series = str(ext.get("series") or ext.get("platform_type") or "").strip()
            form = str(ext.get("form") or ext.get("chassis_form") or "").strip()
            if not (series and form):
                ctx.setdefault("assumptions", []).append({"code": "invalid_scene", "slot": "server_type", "dropped": filled_type})
                ext.pop("server_type", None)
                for alias in ("server_type_name", "usage", "scene"):
                    ext.pop(alias, None)
                ctx["ext"] = ext
                return scene_gap(ext)
    configured_order = [s for s in (cfg.get("fallback_order") or ["exact", "same_series", "same_form"]) if s and s != "all"]

    def _query(series=_UNSET, form=_UNSET) -> list[dict]:
        if not signals_ready:
            return []
        return select_models(
            usage=None,  # 原文永不进引擎
            server_type_name=str(ext.get("server_type_name") or ext.get("server_type") or "").strip() or None,
            series=str(ext.get("series") or ext.get("platform_type") or "").strip() or None if series is _UNSET else (series or None),
            form=str(ext.get("form") or ext.get("chassis_form") or "").strip() or None if form is _UNSET else (form or None),
            fallback_order=configured_order,
        )

    candidates = _query()
    if not candidates and signals_ready:
        # 非目录词汇的 series（如把 CPU 厂商语当系列）会让查询落空：去 series 重查，白盒放宽。
        series_val = str(ext.get("series") or ext.get("platform_type") or "").strip()
        if series_val:
            candidates = _query(series="", form=None)
            if candidates:
                ctx.setdefault("assumptions", []).append({"code": "series_dropped", "slot": "series", "dropped": series_val})
    ctx["baselines_pool"] = candidates
    ctx["model_options"] = catalog_models_option_data(candidates, include_price=include_price)

    explicit = str(canonical_get(ext, "server_model") or "").strip()
    locked, reason = None, ""
    if explicit and candidates:
        low = explicit.lower()
        for cand in candidates:
            name = str(cand.get("name") or "").strip().lower()
            mid = str(cand.get("server_model_id") or cand.get("id") or "").strip()
            if (name and (name == low or name in low or low in name)) or (mid and mid.lower() == low):
                locked, reason = cand, "客户明确指定该机型"
                break
    if locked is None and len(candidates) == 1:
        locked, reason = candidates[0], "目录唯一命中"
    # 语义判断交回 AI 角色（默认路径）：引擎只提供候选事实与 id 校验；多候选默认 AI 语义选型。
    if locked is None:
        pool = candidates
        if not pool and _has_hw_signal(ctx):
            from app.api.candidate_search import select_models as _sm
            _stn = str(ext.get("server_type_name") or ext.get("server_type") or "").strip()
            try:
                pool = (_sm(usage=None, server_type_name=_stn or None, no_signal_strategy="fallback_all", limit=12)
                        if _stn else _sm(usage=None, no_signal_strategy="fallback_all", limit=12)) or []
            except Exception:
                logger.exception("AI 选型候选池构建失败")
                pool = []
            if pool:
                ctx.setdefault("assumptions", []).append({
                    "code": "model_pool_broadened",
                    "reason": "需求含硬件信号但未指定机型，按库内候选交由 AI 语义选型"})
        if pool:
            picked = await _llm_pick_model(ctx, pool, include_price=include_price)
            if picked is not None:
                idx, why = picked
                locked, reason = pool[idx], why or "AI 依需求与候选选定"

    if locked is None:
        has_sig = _has_hw_signal(ctx) or model_signals_ready(ext)
        if not candidates and not has_sig:
            return scene_gap(ext)
        if candidates:
            # 多候选且 AI 无法确定 → 交还角色/用户决策，绝不静默
            return model_gap(candidates, include_price=include_price)
        return _gap("server_type", "no_models_for_signals", catalog_whitelist_options(ext, only_key="server_type").get("server_type") or [])

    _lock_baseline(ctx, locked, reason)
    return None


# ── 阶段 3：配件（纯确定性落地）──────────────────────────────────────────

def _scenario_gap(ctx: dict, only_unfilled: bool) -> Optional[dict]:
    """场景化配件推荐缺口：选项=目录事实（场景包品类×系列适配×机箱能力），无则 None。"""
    ext = dict(ctx.get("ext") or {})
    baselines = ctx.get("baselines") or ([ctx["_locked_baseline"]] if ctx.get("_locked_baseline") else [])
    baseline = baselines[0] if baselines else {}
    stn = str(baseline.get("server_type_name") or ext.get("server_type_name") or "")
    from app.services.part_selector import scenario_parts_gap_data
    code, opts = scenario_parts_gap_data(
        stn, baseline=baseline, ext=ext,
        include_price=bool(ctx.get("price_access", True)), only_unfilled=only_unfilled)
    if not opts:
        return None
    gap = _gap("parts", code, opts)
    # 自选器上下文随缺口下行（skill_chat 弹出后存进 last_card，card-pick 端点按它取目录）
    gap["pick_meta"] = {
        "server_type_name": stn,
        "series": str(baseline.get("series") or ""),
        "gpu_slots": int(baseline.get("gpu_slots") or 0),
        "max_cpu": int(baseline.get("max_cpu") or 0),
        "max_dimm": int(baseline.get("max_dimm") or 0),
    }
    return gap


def kp_gate_gap(ctx: dict) -> Optional[dict]:
    """配件闸门（业务决定点，产出缺口数据）：
    - 零配件信号且意向未定 → 问意向；
    - 要了配件但零信号 → 场景化推荐（场景包+机型系列/能力），无场景包退开放反问；
    - 有部分信号但场景包还有整组未配 → 逐步补齐（防半截 BOM 静默出），「就这些」可终止；
    - 要了配件且信号齐（或用户叫停补齐）→ 放行落地。
    """
    if ctx.get("kp_parts"):
        return None
    ext = dict(ctx.get("ext") or {})
    args = kp_args_from_ext(ext, server_type_name=str(
        ext.get("server_type_name") or ext.get("server_type") or ""))
    mode = parse_kp_mode(str(ext.get("kp_mode") or ""))
    if not args:
        if mode == "l6_only":
            return None
        if mode == "need_parts":
            scenario = _scenario_gap(ctx, only_unfilled=False)
            if scenario:
                return scenario
            return _gap("parts", "need_parts_but_no_signals", [])
        return kp_mode_gap()
    if not ext.get("kp_scenario_done"):
        partial = _scenario_gap(ctx, only_unfilled=True)
        if partial:
            return partial
    return None


def _kp_gap_rows(parts: list[dict]) -> dict[str, list[dict]]:
    """未命中 / 规格偏差行（需 AI 接地的缺口），按品类分组。"""
    out: dict[str, list[dict]] = {}
    for p in parts:
        if p.get("unmatched") or p.get("spec_mismatch"):
            out.setdefault(str(p.get("category") or "其他"), []).append(p)
    return out


def _kp_candidates_for(gap_rows: dict[str, list[dict]], series: str) -> dict[str, list[dict]]:
    """按缺口品类从库内拉在售候选（含规格字典），与 select_parts 同一 series 适配池。"""
    from app.repository.kp_repo import KPRepository
    from app.services.part_selector import _SeriesScopedRepo
    out: dict[str, list[dict]] = {}
    if not gap_rows:
        return out
    raw = KPRepository()
    try:
        repo = _SeriesScopedRepo(raw, series)
        for cat in gap_rows:
            rows = repo.get_by_category_with_specs(cat) or []
            if rows:
                out[cat] = [dict(r) for r in rows]
    finally:
        raw.close()
    return out


def _kp_candidate_desc(c: dict) -> str:
    """把候选的规格字典压成一行可读能力描述，供 AI 做语义匹配（非词表穷举）。"""
    model = str(c.get("model") or c.get("pn") or "").strip()
    specs = c.get("specs")
    bits = [model]
    if isinstance(specs, dict):
        for k, v in specs.items():
            if v in (None, "", []):
                continue
            bits.append(f"{k}:{v}")
    elif isinstance(specs, list):
        for item in specs:
            if isinstance(item, dict):
                for k, v in item.items():
                    if v not in (None, "", []):
                        bits.append(f"{k}:{v}")
    return "；".join(b for b in bits if b)


async def _llm_pick_kp(ctx: dict, baseline: dict, gap_rows: dict[str, list[dict]],
                       cands_by_cat: dict[str, list[dict]]) -> list[dict]:
    """单次受约束配件选型：为每个 gap 各挑一个候选 id；非法输出重试一次后放弃。"""
    import json as _json
    from app.services import llm_client
    per_cat = {}
    for cat, rows in gap_rows.items():
        cands = cands_by_cat.get(cat) or []
        per_cat[cat] = {
            "gaps": [{"gap_id": f"{cat}#{i}", "qty": r.get("qty"),
                      "want": str(r.get("request_spec") or r.get("unmatched_reason") or "").strip()}
                     for i, r in enumerate(rows)],
            "candidates": [{"id": str(c.get("id") or ""), "model": str(c.get("model") or c.get("pn") or ""),
                            "specs": c.get("specs") or {}, "price": c.get("price"),
                            "desc": _kp_candidate_desc(c)} for c in cands[:40]],
            "note": (f"库内该品类共 {len(cands)} 件，此处列出排名靠前的 {min(len(cands), 40)} 件；"
                     f"如上方候选都不合适，请将 selected_id 留空并说明") if len(cands) > 40 else "",
        }
    if not per_cat:
        return []
    cap = {
        "server_type_name": str(baseline.get("server_type_name") or ""),
        "series": str(baseline.get("series") or ""),
        "form": str(baseline.get("form") or ""),
        "gpu_slots": int(baseline.get("gpu_slots") or 0),
        "max_dimm": int(baseline.get("max_dimm") or 0),
        "bays": str(baseline.get("bays") or ""),
        "psu_wattages": [str(x) for x in (baseline.get("psu_wattages") or [])],
    }
    ext = dict(ctx.get("ext") or {})
    ext_facts = {k: v for k, v in ext.items() if k in (
        "server_type_name", "series", "form", "purchase_qty", "cpu", "memory",
        "drives", "gpu", "raid", "psu", "nic", "kp_mode")}
    messages = [
        {"role": "system", "content": ("你是配件选型助手。只能输出 JSON：" +
            '{"selections":[{"gap_id":"品类#序号","category":"品类","selected_id":"候选中的id或空","qty":1,"reason":"简短理由"}]}。' +
            "必须为每个 gap 各返回一条 selection；gap_id 必须原样使用给定值；" +
            "selected_id 必须取自对应品类的候选 id，确实无法命中则留空；禁止编造 id。")},
        {"role": "user", "content": ("需求原文：\n" + str(ctx.get("requirement_text") or "") +
            "\n\n线索登记表：\n" + _json.dumps(ext_facts, ensure_ascii=False, default=str) +
            "\n\n已锁机型能力：\n" + _json.dumps(cap, ensure_ascii=False) +
            "\n\n待选配件缺口及候选：\n" + _json.dumps(per_cat, ensure_ascii=False, default=str))},
    ]
    for _attempt in range(2):
        try:
            data = await llm_client.chat_json(messages, model=ctx.get("llm_model") or None,
                                              temperature=0, timeout=60.0, max_attempts=1)
        except Exception as exc:
            logger.warning("kp AI 接地失败: %s", exc)
            return []
        if isinstance(data, dict) and isinstance(data.get("selections"), list):
            return [s for s in data["selections"] if isinstance(s, dict)]
    return []



def _apply_kp_ground(parts: list[dict], gap_rows: dict[str, list[dict]],
                     cands_by_cat: dict[str, list[dict]], selections: list[dict]) -> int:
    """校验 AI 选择（id 须属候选；数量/价格取库值）→ 替换缺口行；非法/未选保持缺口。"""
    grounded = 0
    sel_by_id = {}
    sel_by_cat_order: dict[str, list[dict]] = {}
    for s in selections:
        if not isinstance(s, dict):
            continue
        gid = str(s.get("gap_id") or "").strip()
        if gid:
            sel_by_id[gid] = s
        cat = str(s.get("category") or "").strip()
        sel_by_cat_order.setdefault(cat, []).append(s)
    for cat, rows in gap_rows.items():
        ordered = sel_by_cat_order.get(cat) or []
        for i, target in enumerate(rows):
            gid = f"{cat}#{i}"
            sel = sel_by_id.get(gid) or (ordered[i] if i < len(ordered) else None)
            if not sel:
                continue
            pid = str(sel.get("selected_id") or "").strip()
            if not pid:
                continue
            cand = next((c for c in (cands_by_cat.get(cat) or []) if str(c.get("id") or "") == pid), None)
            if cand is None:
                continue
            qty = int(sel.get("qty") or target.get("qty") or 1)
            if qty <= 0:
                qty = int(target.get("qty") or 1)
            model = str(cand.get("model") or cand.get("pn") or "")
            note = str(sel.get("reason") or "").strip()
            new_row = {
                "category": cat, "pn": model, "name": model,
                "unit_price": float(cand.get("price") or 0),
                "currency": str(cand.get("currency") or "RMB"),
                "qty": qty,
                "matched_spec": str(target.get("request_spec") or ""),
                "unmatched": False, "unmatched_reason": "",
                "request_spec": str(target.get("request_spec") or ""),
                "grounded_spec": model, "spec_mismatch": False,
                "replacement_note": f"{note}（由候选 {model} 接地）".strip(),
            }
            for j, p in enumerate(parts):
                if p is target:
                    parts[j] = new_row
                    grounded += 1
                    break
    return grounded



async def _kp_ai_ground(ctx: dict, baseline: dict, parts: list[dict], series: str = "") -> int:
    """配件 AI 接地：未命中/规格偏差 → 库内候选 → 受约束选型 → 校验落地；失败/无候选保守留缺口。"""
    gap_rows = _kp_gap_rows(parts)
    if not gap_rows:
        return 0
    cands = _kp_candidates_for(gap_rows, series)
    if not cands:
        return 0
    selections = await _llm_pick_kp(ctx, baseline, gap_rows, cands)
    if not selections:
        return 0
    return _apply_kp_ground(parts, gap_rows, cands, selections)


async def phase_kp_reason(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> None:
    from app.services.part_selector import select_parts
    ext = dict(ctx.get("ext") or {})
    baselines = ctx.get("baselines") or ([ctx["_locked_baseline"]] if ctx.get("_locked_baseline") else [])
    baseline = baselines[0] if baselines else {}
    stn = str(baseline.get("server_type_name") or ext.get("server_type_name") or "")
    args = kp_args_from_ext(ext, server_type_name=stn)
    # 机型已锁 → 配件候选池过滤到该平台适配件（applicable 语义，含通用件）
    series = str(baseline.get("series") or ext.get("series") or "").strip()
    parts = list(select_parts(**args, series=series) or [])
    # 阶段3 AI 接地：默认路径下，未命中/规格偏差行交由 AI 从库内候选接地（语义判断交回 AI 角色），
    # 真无法命中绝不硬顶（保持缺口让角色/用户决策）。
    grounded = await _kp_ai_ground(ctx, baseline, parts, series=series)
    if grounded:
        ctx.setdefault("assumptions", []).append({
            "code": "kp_ai_grounded", "slot": "parts", "count": grounded,
            "reason": "未命中/规格偏差配件已由 AI 从库内候选接地"})
    mid = baseline.get("server_model_id") or baseline.get("id")
    ctx["kp_parts"] = parts
    if mid is not None:
        ctx["kp_by_model"] = {str(mid): parts}
    by_category: dict[str, int] = {}
    for p in parts:
        cat = str(p.get("category") or "其他")
        by_category[cat] = by_category.get(cat, 0) + 1
    ctx["kp_summary"] = {
        "kp_count": len(parts), "by_category": by_category,
        "unmatched_count": sum(1 for p in parts if p.get("unmatched")),
        "spec_mismatch_count": sum(1 for p in parts if p.get("spec_mismatch")),
    }
