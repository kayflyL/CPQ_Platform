# -*- coding: utf-8 -*-
"""需求分析 Skill 的引擎阶段函数（纯执行，无对话能力）。

两器官架构（2026-08-28 宪法；2026-09-02 修订：登记环节=唯一大脑的显式节点回合，本引擎仍零 LLM）：
1. 全系统同一时刻只有一个会思考的脑袋：AI 角色；本引擎是纯确定性执行器，不调用 LLM，不做模型决策；
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
    """机型选型的信号门槛：必须给了类型，或「系列+形态」齐备。

    类型只认 server_type/server_type_name（历史上都存目录类型名）；usage/scene
    是自由文本语义，不当作结构化信号（否则「跑数据库」会被当类型查目录）。
    """
    has_type = bool(str((ext.get("server_type_name") or ext.get("server_type") or "") or "").strip())
    series = str(canonical_get(ext, "platform_type") or "").strip()
    form = str(canonical_get(ext, "chassis_form") or "").strip()
    return bool(has_type) or bool(series and form)


def requirement_sheet_view(ext: dict) -> dict:
    """给 AI 选型的唯一需求表视图：基本配置 + kp_rows（part_category/description/qty）。

    登记表是唯一需求表；不再把 ext.cpu/memory/storage 等窄字段当作「登记表」喂给 AI，
    避免 AI 看到的是第二套空壳。窄字段如果存在（点选卡直传信号），只作为附加事实附带。
    """
    out: dict = {}
    for k in ("server_type_name", "server_type", "series", "platform_type", "form", "chassis_form",
              "server_model", "purchase_qty", "warranty_years", "kp_mode"):
        v = (ext or {}).get(k)
        if v not in (None, "", [], {}):
            out[k] = v
    kp = (ext or {}).get("kp_rows")
    if isinstance(kp, list) and kp:
        rows = []
        for r in kp:
            if not isinstance(r, dict):
                continue
            row = {"part_category": str(r.get("part_category") or r.get("category") or ""),
                   "description": str(r.get("description") or "").strip(),
                   "catalogue": str(r.get("catalogue") or "").strip(),
                   "note": str(r.get("note") or "").strip()}
            try:
                row["qty"] = int(float(r.get("qty", 1) or 1))
            except (TypeError, ValueError):
                row["qty"] = 1
            if row["part_category"] or row["description"]:
                rows.append(row)
        if rows:
            out["kp_rows"] = rows
            # 登记表已有部件内容；窄字段不再呈现为登记表（避免两套）
        return out
    # 无 kp_rows 时兜底：附上窄字段作为「已登记的结构化信号」事实（点选卡直传情形），
    # 仅当不存在 kp_rows 才出现，绝不与 kp_rows 并列成第二套表。
    for key in ("cpu", "memory", "storage", "gpu", "nic", "raid", "psu"):
        v = (ext or {}).get(key)
        if isinstance(v, (list, dict)) and v:
            out[key] = v
    return out


def kp_args_from_ext(ext: dict, server_type_name: str = "") -> dict:
    """从结构化槽位确定性构造 select_parts 参数：有什么信号配什么件，绝不发明。"""
    args: dict[str, Any] = {}
    if server_type_name:
        args["server_type_name"] = server_type_name
    kp = (ext or {}).get("kp_rows")
    if isinstance(kp, list) and kp:
        cats = [str(r.get("part_category") or r.get("category") or "").strip()
                for r in kp if isinstance(r, dict)]
        cats = [c for c in cats if c]
        if cats:
            args["categories"] = cats
    for key in ("cpu", "memory", "storage", "gpu", "raid", "psu"):
        val = ext.get(key)
        if isinstance(val, (list, dict)) and val:
            args[key] = val
    nic = ext.get("nic")
    if isinstance(nic, dict) and nic:
        args["nic"] = nic
    return args


# ── 必须反问类目（AI=配置器：这些类目由客户确认，AI 给候选+推荐+自选）────────────

# 服务器配置默认必问类目（目标层未配置 must_ask 字段策略时回退；可在抽屉目标层逐类配）
DEFAULT_KP_MUST_ASK = ["CPU", "Memory", "HDD/SSD", "Raid card", "NIC", "GPU"]


def kp_must_ask_categories(cfg: dict) -> list:
    """目标层字段策略：必须反问类目（键 `kp_parts:<类目>` 且 must_ask/ask=true）。

    无目标层配置 → 回退 DEFAULT_KP_MUST_ASK；有配置则只认配置勾选的类目。
    """
    try:
        arts = ((cfg or {}).get("target") or {}).get("artifacts") or []
        fields = ((arts[0] if arts else {}) or {}).get("fields") or []
        cats: list[str] = []
        for f in fields:
            if isinstance(f, dict) and (bool(f.get("must_ask")) or bool(f.get("ask"))):
                key = str(f.get("key") or "")
                if key.startswith("kp_parts:"):
                    c = key.split(":", 1)[1].strip()
                    if c:
                        cats.append(c)
        if cats:
            return cats
    except Exception:
        pass
    return list(DEFAULT_KP_MUST_ASK)


# ── 缺口数据（引擎唯一的"反问"形态）──────────────────────────────────────

def _gap(slot: str, reason_code: str, options: Optional[list] = None) -> dict:
    return {"slot": slot, "reason_code": reason_code, "options": options or []}


def scene_gap(ext: dict) -> dict:
    return _gap("server_type", "server_type_missing", catalog_whitelist_options(ext, only_key="server_type").get("server_type") or [])


def kp_mode_gap() -> dict:
    return _gap("kp_mode", "kp_mode_undecided", list(KP_MODE_OPTIONS))


def catalog_whitelist_options(ext: dict, only_key: Optional[str] = None) -> dict:
    """缺口选项：按 slot_spec.candidate_source 决定来源；
    catalog 槽位取在售目录真实值（业务数据，非话术），
    数量/保修等自由项不产候选，返回空 options（纯自由输入，不写死词表）。"""
    try:
        from app.services.catalog_options import catalog_whitelist
        wl = catalog_whitelist({}, {}, "")  # 全量词汇表（传已确认值会按确认值收窄）
    except Exception:
        logger.exception("读取目录白名单失败")
        wl = {}
    from app.services.slot_contract import slot_spec
    candidate_source = {str(s.get("key") or ""): str(s.get("candidate_source") or "")
                        for s in slot_spec() if isinstance(s, dict)}
    keys = [only_key] if only_key else ["server_type", "platform_type", "chassis_form", "purchase_qty"]
    options: dict[str, list] = {}
    bucket = {"server_type": "types", "platform_type": "series", "chassis_form": "forms"}
    for key in keys:
        src = bucket.get(key)
        if not src or candidate_source.get(key) != "catalog":
            continue
        values = [str(v) for v in (wl.get(src) or []) if str(v).strip()]
        if values:
            options[key] = [{"label": v, "value": v, "slot": key, "group": slot_label(key)} for v in values]
    return options




def target_layer_gap(ext: dict, blockers: list) -> Optional[dict]:
    """agent_fill 目标层反问题目：缺的必填(L0) 配置字段 → 数据缺口（选项来自目标层配置/目录）。

    反问项就是抽屉「目标层」配置的字段；选项按该字段 candidate_source 取在售目录真实值，
    无候选类型（如保修年限/数量自由项）则空 options = 纯自由输入。绝不写死词表。
    """
    if not blockers:
        return None
    slot = str(blockers[0])
    opts = catalog_whitelist_options(ext, only_key=slot).get(slot) or []
    return _gap(slot, "target_incomplete", opts)


def target_layer_gaps(ext: dict, blockers: list, cap: int = 4) -> list[dict]:
    """一次问全（S1）：全部 L0 缺口一起产出，上限 4 个（对齐 Claude Code AskUserQuestion
    的批量提问形态）——N 个缺口从 N 轮往返压成 1 轮，答案侧由点选/打字快速路各自落槽。
    单个缺口的形状与 target_layer_gap 完全一致（同一 _gap 构造）。"""
    out: list[dict] = []
    for slot in [str(s) for s in (blockers or [])][:max(1, cap)]:
        opts = catalog_whitelist_options(ext, only_key=slot).get(slot) or []
        out.append(_gap(slot, "target_incomplete", opts))
    return out


def inferred_confirm_gaps(ext: dict, corpus: str, cap: int = 2) -> list[dict]:
    """推断求证缺口（凡推断必让客户确认）：槽位已有值，但值在累计客户原话里找不到、
    也未曾经点选/打字确认过 → 弹确认卡（reason_code=inferred_confirm，current=当前推断值）。

    判定全确定性：语料/值去空白后做包含比对；skill_chat 在点选/打字落槽时写
    ext.confirmed_slots[slot]=值（值再被大脑改写即自然失效重新求证）。
    purchase_qty 是引擎白盒默认（终报呈现），server_model 走机型确认环节，均不在此列。
    """
    import re as _re

    from app.services.slot_contract import canonical_get, slot_spec
    text = _re.sub(r"\s+", "", str(corpus or ""))
    if not text:
        return []
    confirmed = ext.get("confirmed_slots") if isinstance(ext.get("confirmed_slots"), dict) else {}
    out: list[dict] = []
    for spec in slot_spec():
        if not isinstance(spec, dict):
            continue
        key = str(spec.get("key") or "")
        if not key or spec.get("src_type") == "kp" or key in ("server_model", "purchase_qty"):
            continue
        val = canonical_get(ext, key)
        if not isinstance(val, str) or not val.strip():
            continue
        v = val.strip()
        if confirmed.get(key) == v or _re.sub(r"\s+", "", v) in text:
            continue
        opts = catalog_whitelist_options(ext, only_key=key).get(key) or []
        if not any(str(o.get("value") or "") == v for o in opts):
            opts = [{"label": v, "value": v, "slot": key, "group": slot_label(key)}] + opts
        out.append({"slot": key, "reason_code": "inferred_confirm",
                    "options": opts, "current": v})
        if len(out) >= max(1, cap):
            break
    return out

# ── 词汇/守卫（全部数据驱动）────────────────────────────────────────────

def _normalize_to_catalog(ext: dict) -> None:
    """把系列/形态自由文本归一到在售目录词汇表（仅词汇对齐，不做业务决定）。

    读写都走 canonical 键（platform_type/chassis_form）：canonical_set 已不投影
    遗留别名（series/form），再按别名读会永远读空值，导致「2U 机架式」这类
    自由写法归不了「2U」、机型查询空候选。"""
    try:
        from app.services.catalog_options import catalog_whitelist
        wl = catalog_whitelist({}, {}, "")
    except Exception:
        logger.exception("读目录词汇表失败")
        return
    for key, src in (("platform_type", "series"), ("chassis_form", "forms")):
        val = str(canonical_get(ext, key) or "").strip()
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


# ── 阶段 1：槽位规范化（登记表落表后的确定性校验；大脑回合已在引擎完成）────────

async def phase_normalize_slots(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> list[dict]:
    """确定性规范化：校验/补默认/固化登记表快照。本阶段不发起任何 LLM。

    登记表来源（run_skill_plan_core 已裁决）：大脑节点回合（fill_requirement）或
    调用方结构化直填（点选/脚本）。这里只做：默认值 → L0 缺口数据。
    平台推导等规则内容一律不在代码里——等策略中心-需求分析规则页单独设计后以
    配置接入（当前初级阶段允许候选多平台混合，由用户/AI 选定）。

    返回缺口列表（S1 一次问全）：空列表=无缺口放行；非空=全部 L0 缺口（≤4），
    上层一次性弹出而非逐轮挤牙膏。
    """
    from app.services.slot_contract import _missing_critical

    from app.services.requirement_slots import combined_slot_spec
    _filled = sum(1 for s in combined_slot_spec() if _slot_live(s, dict(ctx.get("ext") or {})))
    ctx.setdefault("timings", {})["agent_fill_extract"] = {
        "calls": 0, "ms": 0.0, "filled_signals": _filled,
        "source": str(ctx.get("fill_source") or "unknown"),
    }
    logger.info("agent_fill extract calls=%s ms=%s filled_signals=%s source=%s",
                0, 0.0, _filled, ctx.get("fill_source"))

    # ext 全程原地改（绝不复制重赋）：工具上下文（_TOOL_CTX["ext"]）与引擎共享同一
    # 对象，任何一次 dict(ext) 换新都会让工具写入落进弃用副本（E2E 实测丢锁定的根因）。
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    _default_qty(ctx, ext)
    ctx["blockers"] = list(_missing_critical(ext))
    try:
        from app.services.capabilities import _freeze_requirement
        _freeze_requirement(ctx, ext, str(ctx.get("requirement_text") or ""))
    except Exception as _e:
        logger.warning("_freeze_requirement 失败: %s", _e, exc_info=True)
    if not ctx.get("force_complete"):
        # 推断求证优先于缺失反问：推断值先被客户确认，下游语义（机型过滤/平台规则）才可靠
        gaps = inferred_confirm_gaps(ext, str(ctx.get("requirement_text") or ""))
        if ctx.get("blockers"):
            gaps = gaps + target_layer_gaps(ext, list(ctx.get("blockers") or []))
        if gaps:
            return gaps[:4]
    return []



def _slot_live(spec: dict, ext: dict) -> bool:
    """目标层 slot 是否已有登记内容（供 agent_fill 统计）。"""
    if not isinstance(spec, dict):
        return False
    key = str(spec.get("key") or "")
    if not key:
        return False
    from app.services.slot_contract import _slot_filled
    return _slot_filled(ext, key)


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
    ctx["model_selection"] = {
        "id": baseline.get("server_model_id") or baseline.get("id"),
        "name": baseline.get("name") or "",
        "server_type_name": baseline.get("server_type_name") or "",
        "series": baseline.get("series") or "",
        "form": baseline.get("form") or "",
    }


def _has_hw_signal(ctx: dict) -> bool:
    """需求是否含硬件选件信号（登记表部件行或窄字段），用于决定是否强制 AI 语义选型。"""
    ext = dict(ctx.get("ext") or {})
    kp = ext.get("kp_rows")
    if isinstance(kp, list) and any(isinstance(r, dict) and (r.get("part_category") or r.get("description")) for r in kp):
        return True
    for k in ("cpu", "memory", "storage", "gpu", "raid", "psu", "nic"):
        v = ext.get(k)
        if isinstance(v, (list, dict)) and len(v):
            return True
    return False


async def phase_model_reason(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> Optional[dict]:
    """机型阶段：纯结构化信号查目录；选择只来自候选集。返回缺口（数据）或 None。"""
    from app.services.model_candidates import select_models
    # ext 原地改（同 normalize 阶段）：复制重赋会断开工具上下文与引擎的对象身份
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    _normalize_to_catalog(ext)
    signals_ready = model_signals_ready(ext)
    # 价格权限：聊天入口按角色传入（ctx.price_access）；试运行等未设置的入口默认可见
    include_price = bool(ctx.get("price_access", True))

    # 类型词表校验：登记的类型必须是目录真实类型，否则 select_models 的
    # type 词表失配会退化成全量查询（= 无关机型被 AI 乱配）。失配 → 场景缺口。
    filled_type = str((ext.get("server_type_name") or ext.get("server_type") or "") or "").strip()
    if filled_type:
        try:
            from app.repository.server_catalog_repo import ServerCatalogRepository
            catalog_types = {str(t.get("name") or "").strip() for t in ServerCatalogRepository().list_types()}
        except Exception:
            logger.exception("读目录类型失败")
            catalog_types = set()
        if catalog_types and filled_type not in catalog_types:
            # 允许「系列+形态」齐备的路径继续（类型只是偏好）；纯类型信号失配 → 场景缺口
            series = str(canonical_get(ext, "platform_type") or "").strip()
            form = str(canonical_get(ext, "chassis_form") or "").strip()
            if not (series and form):
                ctx.setdefault("assumptions", []).append({"code": "invalid_scene", "slot": "server_type", "dropped": filled_type})
                ext.pop("server_type", None)
                for alias in ("server_type_name", "usage", "scene"):
                    ext.pop(alias, None)
                return scene_gap(ext)
    def _query(series=_UNSET, form=_UNSET) -> list[dict]:
        if not signals_ready:
            return []
        return select_models(
            usage=None,  # 原文永不进引擎
            server_type_name=str((ext.get("server_type_name") or ext.get("server_type") or "") or "").strip() or None,
            series=str(canonical_get(ext, "platform_type") or "").strip() or None if series is _UNSET else (series or None),
            form=str(canonical_get(ext, "chassis_form") or "").strip() or None if form is _UNSET else (form or None),
        )

    candidates = _query()
    if not candidates and signals_ready:
        # 非目录词汇的 series（如把 CPU 厂商语当系列）会让查询落空：去 series 重查，白盒放宽。
        series_val = str(canonical_get(ext, "platform_type") or "").strip()
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
    # 语义判断交回 AI 角色（默认路径）：引擎只提供候选事实与 id 校验，不做第二次 LLM 选型。
    if locked is None and not candidates and _has_hw_signal(ctx):
        from app.services.model_candidates import select_models as _sm
        _stn = str((ext.get("server_type_name") or ext.get("server_type") or "") or "").strip()
        # 放宽候选池同样受已推导平台约束：兆芯→Polaris 推导后绝不把 Orion 机型混进候选
        _series = str(canonical_get(ext, "platform_type") or "").strip() or None
        try:
            candidates = (_sm(usage=None, server_type_name=_stn or None, series=_series,
                              no_signal_strategy="fallback_all", limit=12)
                          if _stn else _sm(usage=None, series=_series,
                                           no_signal_strategy="fallback_all", limit=12)) or []
        except Exception:
            logger.exception("AI 选型候选池构建失败")
            candidates = []
        if candidates:
            ctx["baselines_pool"] = candidates
            ctx["model_options"] = catalog_models_option_data(candidates, include_price=include_price)
            ctx.setdefault("assumptions", []).append({
                "code": "model_pool_broadened",
                "reason": "需求含硬件信号但未指定机型，按库内候选交由用户/AI 角色选定"
                          + (f"（已按平台 {_series} 收窄）" if _series else "")})
        # 放宽池构建后必须再对一次显式指定：登记表里已登记的机型（如用户点选）不能因为
        # 首轮 candidates 为空就丢——否则机型无限重弹（08-30 同族 bug 的真正根因）。
        if locked is None and explicit and candidates:
            low = explicit.lower()
            for cand in candidates:
                name = str(cand.get("name") or "").strip().lower()
                if name and (name == low or name in low or low in name):
                    locked, reason = cand, "客户明确指定该机型"
                    break

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


# ── 阶段 3：配件（AI=配置器；brain 决定配什么，工具落地，必须反问类目交客户确认）──


def kp_required_missing(ctx: dict) -> list[str]:
    """必登记部件策略（目标层 kp_required）：客户原话未覆盖、且未明确放弃的必填大类。

    权威源 = system_config.requirement_slots.kp_required（目标层弹窗勾选）；
    已登记（kp_rows.part_category）或已明确放弃（ext.kp_absent）的大类不算缺。
    """
    ext = dict(ctx.get("ext") or {})
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            pol = repo.get_value("requirement_slots") or {}
        finally:
            repo.close()
        required = [str(c).strip() for c in (pol.get("kp_required") or []) if str(c).strip()]
    except Exception:
        logger.exception("读取必登记部件策略失败")
        return []
    if not required:
        return []
    have = {str(r.get("part_category") or "").strip() for r in (ext.get("kp_rows") or []) if isinstance(r, dict)}
    absent = {str(c).strip() for c in (ext.get("kp_absent") or [])}
    return [c for c in required if c not in have and c not in absent]

def kp_gate_gap(ctx: dict) -> Optional[dict]:
    """配件闸门（AI=配置器）：模型锁死后由大脑生成配置、必须反问类目弹卡确认。

    客户明确「只出整机底座」(`kp_mode=l6_only`) → 不放配件；其余一律放行交给大脑，
    不再用固定场景配方/缺配旁路去追问或拦截。
    """
    if ctx.get("kp_parts"):
        return None
    ext = dict(ctx.get("ext") or {})
    if parse_kp_mode(str(ext.get("kp_mode") or "")) == "l6_only":
        return None
    return None


async def phase_kp_reason(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> None:
    from app.services.part_selector import (
        apply_kp_picks, config_rows_to_parts, ensure_pick_rows, requirement_rows_to_parts)
    ext = dict(ctx.get("ext") or {})
    baselines = ctx.get("baselines") or ([ctx["_locked_baseline"]] if ctx.get("_locked_baseline") else [])
    baseline = baselines[0] if baselines else {}
    stn = str(baseline.get("server_type_name") or ext.get("server_type_name") or ext.get("server_type") or "")
    # AI=配置器：声明行（kp_config）+ 登记行（kp_rows）共同构成「要配什么」的骨架；
    # 空/模糊配置进一步用「必须反问类目」兜底为占位行，交给大脑逐类生成或下单页确认。
    parts = []
    parts.extend(config_rows_to_parts(ext.get("kp_config") or []))
    parts.extend(requirement_rows_to_parts(ext.get("kp_rows") or []))
    present = {str(p.get("category") or "").strip() for p in parts if isinstance(p, dict)}
    absent = {str(c).strip() for c in (ext.get("kp_absent") or []) if str(c).strip()}
    for cat in kp_must_ask_categories(cfg):
        if cat in present or cat in absent:
            continue
        parts.extend(config_rows_to_parts([{"category": cat, "spec": cat, "qty": 1}]))
    # 同类目聚合为一行（保留描述最具体的一条），避免「CPU|CPU」与「CPU|兆芯…」重复占位
    by_cat: dict[str, dict] = {}
    order: list[str] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").strip()
        if not cat:
            continue
        desc = str(p.get("request_spec") or "").strip()
        if cat not in by_cat:
            by_cat[cat] = p
            order.append(cat)
        elif desc and not str(by_cat[cat].get("request_spec") or "").strip():
            by_cat[cat] = p
    parts = [by_cat[cat] for cat in order]
    # 已锁定行（ext.kp_picks 按行键持久）补占位后落地为真实料号行
    parts = ensure_pick_rows(parts, ext.get("kp_picks") or {})
    parts, _applied = apply_kp_picks(parts, ext.get("kp_picks") or {})
    mid = baseline.get("server_model_id") or baseline.get("id")
    ctx["kp_parts"] = parts
    if mid is not None:
        ctx["kp_by_model"] = {str(mid): parts}
    # 落地计数只含真实件：未匹配是占位白盒（request_spec=客户原话），不算「落地配件」，
    # 由 unmatched_count / unmatched 字段单独呈现——否则「落地 X 项」把客户原话也当成料号。
    landed = [p for p in parts if isinstance(p, dict) and not p.get("unmatched")]
    by_category: dict[str, int] = {}
    for p in landed:
        cat = str(p.get("category") or "其他")
        by_category[cat] = by_category.get(cat, 0) + 1
    ctx["kp_summary"] = {
        "kp_count": len(landed), "by_category": by_category,
        "unmatched_count": sum(1 for p in parts if p.get("unmatched")),
        "spec_mismatch_count": sum(1 for p in parts if p.get("spec_mismatch")),
    }
