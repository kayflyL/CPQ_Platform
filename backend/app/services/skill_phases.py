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
from typing import Awaitable, Callable, Optional

from app.services.skill_node_state import KP_CONFIG, KP_PICKS, kp_state, waived_row_keys
from app.services.slot_contract import canonical_get

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]

_UNSET = object()

# 配件意向的两个业务选项（唯一合法值；角色问完后必须用其中一个值落 kp_mode 槽）。
KP_MODE_NEED_PARTS = "需要配配件"
KP_MODE_L6_ONLY = "只要整机底座（L6）"
KP_MODE_OPTIONS = [KP_MODE_NEED_PARTS, KP_MODE_L6_ONLY]


def model_signals_ready(ext: dict) -> bool:
    """机型选型的信号门槛：必须给了类型，或「系列+形态」齐备。

    类型只认 server_type/server_type_name（历史上都存目录类型名）；usage/scene
    是自由文本语义，不当作结构化信号（否则「跑数据库」会被当类型查目录）。
    """
    has_type = bool(str((ext.get("server_type_name") or ext.get("server_type") or "") or "").strip())
    series = str(canonical_get(ext, "platform_type") or "").strip()
    form = str(canonical_get(ext, "chassis_form") or "").strip()
    return bool(has_type) or bool(series and form)


# ── 必填类目（AI=配置器：该类目必须落在最终方案；客户已明确登记→直接锁定，
#    未登记/仅类目名→AI 推荐并调 ask_user 交客户确认）────────────────────────────────

def kp_required_categories(cfg: dict) -> list:
    """目标层字段策略：必填类目（键 `kp_parts:<类目>` 且 ask=true/must_ask=true）。

    语义（2026-09-09 定调）：必填=该行必须落在最终方案，不能跳/不能静默丢。
    是否反问是运行时判定，不是字段静态开关：客户已明确登记具体规格且库内有精确料→直接锁定不反问；
    客户已明确登记具体规格但库内无精确料（只能替代）→必须反问客户（替代/缺失处理）；
    客户未写明（仅用途/类目名）→AI 代为选料，记入推荐并反问客户选哪颗。
    无目标层配置 → 回退登记表契约里 `src_type=kp` 的类目（与登记表同源，不再写死词表）；
    有配置则只认配置勾选的类目。
    """
    try:
        from app.services.skill_target_contract import target_artifacts
        arts = target_artifacts(cfg)
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
    from app.services.slot_contract import slot_spec
    return [str(s.get("category") or "").strip()
            for s in slot_spec()
            if str(s.get("src_type") or "") == "kp" and str(s.get("category") or "").strip()]


# ── 缺口数据（引擎唯一的"反问"形态）──────────────────────────────────────

def _gap(slot: str, reason_code: str, options: Optional[list] = None) -> dict:
    return {"slot": slot, "reason_code": reason_code, "options": options or []}


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


def baseline_qty_cap(category: str, baseline: dict) -> int:
    """类目 → 锁定机型的物理数量上限（0 = 未登记/类目无物理边界，调用方自兜底）。

    GPU→GPU 位、Memory→内存槽、HDD/SSD→盘位、CPU→路数；网卡/RAID 等无单机
    物理边界的类目返回 0。基准未登记该能力同样返回 0——上限是「装得下多少」的
    目录事实，缺数据不编数。行卡数量步进与点击数量收口（skill_signals）共用。
    """
    c = str(category or "").strip().lower()
    try:
        if "gpu" in c:
            return int((baseline or {}).get("gpu_slots") or 0)
        if "memory" in c or "dimm" in c or "内存" in c:
            return int((baseline or {}).get("max_dimm") or 0)
        if "hdd" in c or "ssd" in c or "storage" in c or "盘" in c:
            return int((baseline or {}).get("bays") or 0)
        if c == "cpu":
            return int((baseline or {}).get("max_cpu") or 0)
    except (TypeError, ValueError):
        pass
    return 0


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


def prepare_model_step(ctx: dict) -> dict:
    """model 节点预处理（确定性事实，编排权移交后由引擎在步骤开始时自动调用）。

    候选池构建（含放宽重查/显式指定直锁/唯一命中直锁）——全是事实判定不是决策；
    多候选不定锁（那是大脑/客户的决策）交回调用方。返回摘要供大脑上下文。"""
    from app.services.model_candidates import select_models
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    signals_ready = model_signals_ready(ext)
    include_price = bool(ctx.get("price_access", True))

    filled_type = str(canonical_get(ext, "server_type") or "").strip()
    if filled_type:
        try:
            from app.repository.server_catalog_repo import ServerCatalogRepository
            catalog_types = {str(t.get("name") or "").strip() for t in ServerCatalogRepository().list_types()}
        except Exception:
            logger.exception("读目录类型失败")
            catalog_types = set()
        if catalog_types and filled_type not in catalog_types:
            series = str(canonical_get(ext, "platform_type") or "").strip()
            form = str(canonical_get(ext, "chassis_form") or "").strip()
            if not series:
                ctx.setdefault("assumptions", []).append({"code": "invalid_scene", "slot": "server_type", "dropped": filled_type})
                ext.pop("server_type", None)
                for alias in ("server_type_name", "usage", "scene"):
                    ext.pop(alias, None)
                return {"pool": 0, "auto_locked": None, "invalid_scene": True}

    def _query(series=_UNSET, form=_UNSET) -> list[dict]:
        if not signals_ready:
            return []
        return select_models(
            usage=None,
            server_type_name=str(canonical_get(ext, "server_type") or "").strip() or None,
            series=str(canonical_get(ext, "platform_type") or "").strip() or None if series is _UNSET else (series or None),
            form=str(canonical_get(ext, "chassis_form") or "").strip() or None if form is _UNSET else (form or None),
        )

    candidates = _query()
    if not candidates and signals_ready:
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
    if locked is None and not candidates and _has_hw_signal(ctx):
        from app.services.model_candidates import select_models as _sm
        _stn = str(canonical_get(ext, "server_type") or "").strip()
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
                "reason": "需求含硬件信号但未指定机型，机型候选池已放宽到库内候选"
                          + (f"（已按平台 {_series} 收窄）" if _series else "")})
        if locked is None and explicit and candidates:
            low = explicit.lower()
            for cand in candidates:
                name = str(cand.get("name") or "").strip().lower()
                if name and (name == low or name in low or low in name):
                    locked, reason = cand, "客户明确指定该机型"
                    break

    if locked is not None:
        _lock_baseline(ctx, locked, reason)
    return {"pool": len(candidates),
            "auto_locked": (locked or {}).get("name") if locked else None,
            "explicit": explicit}


async def phase_kp_reason(ctx: dict, cfg: dict, broadcast: BroadcastFn) -> None:
    from app.services.part_selector import (
        apply_kp_picks, apply_kp_waived, config_rows_to_parts, ensure_pick_rows,
        kp_row_key, pick_for_row, pick_is_stale, requirement_rows_to_parts, row_key_norm,
        stamp_row_identity)
    ext = dict(ctx.get("ext") or {})
    kp_st = kp_state(ctx)
    baselines = ctx.get("baselines") or ([ctx["_locked_baseline"]] if ctx.get("_locked_baseline") else [])
    baseline = baselines[0] if baselines else {}
    stn = str(baseline.get("server_type_name") or ext.get("server_type_name") or ext.get("server_type") or "")
    # AI=配置器：声明行（kp_config）+ 登记行（kp_rows）共同构成「要配什么」的骨架。
    # 只认这两类行，不再用目标层「必填类目」自动补占位——那会让未被需求/大脑声明的
    # 类目（如这条需求没要 GPU）变成幽灵行，选型不配又被终检拦，等于系统替 AI 做判断。
    # 需求是否要该类目由 AI 看着目标表自己定：要配就用 query_parts/select_parts/ask_user 声明进
    # kp_config 或登记行，明确不要就纳入 kp_absent；引擎只兜底，不预判。
    # 归属收口（2026-09-12）：KP_CONFIG 按定义只承载「客户原话未覆盖、AI 判断要配」的类目
    # （skill_node_state.KP_CONFIG）。已被线索登记表申报的类目——登记行里已有的类目——
    # 不许再声明一行，否则同一需求会拿到两条身份（`reg:CPU` 与 `cfg:CPU`），客户后补型号时
    # 旧行仍在 → 多一行、多问一轮。判定依据是**类目归属**（登记行事实），不猜措辞。
    # 2026-09-13 放宽：属主类目**登记表没有该类目行时**保留 cfg: 声明行——此前按
    # registration_owned_categories 全量过滤，AI 铸的属主类目推荐行（客户没提 CPU/内存等）
    # 下一轮即被丢弃：自选流没有 pick_all 晋升，行就此消失，大脑下轮重铸循环（实测根因）。
    # 登记表后来出现同类目行时 cfg: 行仍让位（防双身份），其 pick 由 ensure_pick_rows 兜底。
    # 登记表没有的大类（Bridge / HBA / NVSwitch）不受影响。
    _reg_cats = {str(r.get("part_category") or r.get("category") or "").strip()
                 for r in (ext.get("kp_rows") or []) if isinstance(r, dict)}
    _declared: list = []
    for _r in (kp_st.get(KP_CONFIG) or []):
        if not isinstance(_r, dict):
            continue
        _c = str(_r.get("category") or "").strip()
        if _c and _c in _reg_cats:
            continue
        _declared.append(_r)
    parts = []
    parts.extend(config_rows_to_parts(_declared))
    parts.extend(requirement_rows_to_parts(ext.get("kp_rows") or []))
    # 同类目多行：客户可明确登记多个同名类目（如「4个千兆网口」+「2个万兆网口」都是 NIC）。
    # 只要每行都有具体描述就各保留一行，禁止合并把不同规格吸收掉；仅「仅类目名/空描述」的
    # 兜底占位才按类目去重（保留一个占位，避免「CPU|CPU」与「CPU|兆芯…」重复）。
    seen: set = set()
    kept: list = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").strip()
        if not cat:
            continue
        desc = str(p.get("request_spec") or "").strip()
        key = (cat, desc)
        if key in seen:
            continue
        seen.add(key)
        if desc and desc != cat:
            kept.append(p)
            continue
        dup = any(str(q.get("category") or "").strip() == cat and
                  str(q.get("request_spec") or "").strip() in ("", cat)
                  for q in kept)
        if not dup:
            kept.append(p)
    parts = kept
    _picks = kp_st.get(KP_PICKS) or {}
    # 归一化去重（2026-09-11 P2）：措辞只差排版/数量词的两个行键是**同一行**
    # （「系统盘 2块480G SSD」/「系统盘 480G SSD ×2」/「系统盘480G SSD」），同类目多行只在
    # 描述确实不同时才合法（「4个千兆网口」与「2个万兆网口」）。保留顺序：客户登记原文 >
    # 持有 pick 的行 > 先声明者——否则同一需求会以两行进 BOM（实测：11 行里有 2 行 RAID 卡、
    # 2 行系统盘）。被丢弃行的 pick 不会丢：apply_kp_picks 按归一化找行。
    _reg_keys = {kp_row_key(str(r.get("part_category") or r.get("category") or ""),
                            str(r.get("description") or "").strip()
                            or str(r.get("part_category") or r.get("category") or ""))
                for r in (ext.get("kp_rows") or []) if isinstance(r, dict)}
    _idx: dict = {}
    _dedup: list = []
    _score: list = []
    for p in parts:
        _cat = str(p.get("category") or "").strip()
        _desc = str(p.get("request_spec") or "").strip()
        # 去重键优先用铸造身份（P3-1/P3-3）：同一 origin 的行必须合成一行，否则会出现
        # 两行同 row_id；没有身份的行才退回「类目+描述」归一（旧数据/历史通路）。
        _k = str(p.get("row_id") or "").strip() or row_key_norm(_cat, _desc or _cat)
        _pk = pick_for_row(_picks, _cat, _desc, row=p)
        _pk = _pk[0] if isinstance(_pk, list) and _pk else _pk
        _sc = (1 if kp_row_key(_cat, _desc or _cat) in _reg_keys else 0,
               0 if not isinstance(_pk, dict) or pick_is_stale(_pk, _cat, _desc) else 1)
        _at = _idx.get(_k)
        if _at is None:
            _idx[_k] = len(_dedup)
            _dedup.append(p)
            _score.append(_sc)
        elif _sc > _score[_at]:
            _dedup[_at] = p
            _score[_at] = _sc
    parts = _dedup
    # 已锁定行（本节点私有状态 kp_reason.picks 按行键持久）补占位后落地为真实料号行
    parts = ensure_pick_rows(parts, _picks)
    parts, _applied = apply_kp_picks(parts, _picks)
    # 行的第三个结局（客户已知悉库内无料、保持原需求）：行保留 + 标注，不再算未落地。
    # 豁免行键只可能来自客户点选（ask_user 选项带 waived）——引擎不替客户认这个账。
    parts, _waived = apply_kp_waived(parts, waived_row_keys(ctx))
    # 行身份盖章（P3-1）：登记行/声明行已在_placeholder 铸造；此处只给仍缺身份的行
    # （历史通路留下的真实料号行等）按来源补，幂等、不按文本猜。
    parts = stamp_row_identity(parts, kind="row")
    mid = baseline.get("server_model_id") or baseline.get("id")
    ctx["kp_parts"] = parts
    if mid is not None:
        ctx["kp_by_model"] = {str(mid): parts}
    # 落地计数只含真实件：未匹配是占位白盒（request_spec=客户原话）、豁免行是「客户已知悉
    # 库内无料」的白盒结论，两者都不算「落地配件」，由 unmatched_count / waived_count
    # 单独呈现——否则「落地 X 项」把客户原话或留白行也当成料号（虚报）。
    landed = [p for p in parts if isinstance(p, dict)
              and not p.get("unmatched") and not p.get("waived")]
    by_category: dict[str, int] = {}
    for p in landed:
        cat = str(p.get("category") or "其他")
        by_category[cat] = by_category.get(cat, 0) + 1
    ctx["kp_summary"] = {
        "kp_count": len(landed), "by_category": by_category,
        "unmatched_count": sum(1 for p in parts if p.get("unmatched")),
        "waived_count": sum(1 for p in parts if p.get("waived")),
        "spec_mismatch_count": sum(1 for p in parts if p.get("spec_mismatch")),
    }
