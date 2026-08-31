"""Candidate search — 聚合检索 + 整机方案组合。

search_candidates(): 关键词 → L6 料号 + KP 配件 + 基准配置 散件级聚合（一期，保留供 REST 用）。
机型选型走 select_models（server_type_name 精确匹配，目录驱动引导的权威类型）；旧 compose_plans /
usage→类型关键词路由（USAGE_TYPE_ROUTING）已删——usage 现只来自配置词表且与 server_type_name 同源。
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Query

from app.repository.parts_master_repo import PartsMasterRepository
from app.repository.kp_repo import KPRepository, category_family, category_family_members
from app.repository.base_config_repo import BaseConfigRepository
from app.repository.server_catalog_repo import ServerCatalogRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidate-search", tags=["candidate-search"])

PER_KEYWORD_LIMIT = 30  # 每个关键词每个数据源最多取多少条，避免爆炸
MAX_PER_SOURCE = 100    # 单数据源去重后上限
MODEL_TOKEN_RE = re.compile(r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$")  # 型号 token（必含数字）：字母开头混合/单字母+3位数字(H100/A100/B200)/纯数字≥4/数字开头混合(960G/7.68T/9560-8i)


def _normalize_l6(row: dict) -> dict:
    return {
        "source": "l6",
        "id": row.get("pn"),
        "pn": row.get("pn"),
        "name": row.get("name") or "",
        "category": row.get("category") or "",
        "unit_price": row.get("unit_price"),
        "currency": "RMB",
        "specs": row.get("specs") or {},
    }


def _normalize_kp(item: dict) -> dict:
    pn = item.get("oem_sku") or item.get("alt_sku") or item.get("name")
    return {
        "source": "kp",
        "id": f"kp-{item.get('id')}",
        "pn": pn or "",
        "name": item.get("name") or "",
        "category": item.get("category_name") or "Key Parts",
        "brand": item.get("brand") or "",
        "unit_price": item.get("latest_price"),
        "currency": item.get("latest_currency") or "RMB",
        "specs": {},
    }


def _normalize_baseline(cfg: dict) -> dict:
    return {
        "source": "baseline",
        "id": f"base-{cfg.get('id')}",
        "config_id": cfg.get("id"),
        "name": cfg.get("name") or "",
        "model": cfg.get("model") or "",
        "series": cfg.get("series") or "",
        "form": cfg.get("form") or "",
        "parts_count": cfg.get("parts_count") or 0,
        "unit_price": cfg.get("total_price"),
        "currency": "RMB",
    }


def search_candidates(
    keywords: list[str],
    series: Optional[str] = None,
    form: Optional[str] = None,
) -> dict:
    """关键词列表 → 聚合候选。每个关键词在 L6/KP 各做一次 ILIKE，去重合并；baseline 按 series/form。

    Returns: {candidates: [...], counts: {l6, kp, baseline}}
    """
    keywords = [k.strip() for k in (keywords or []) if k and k.strip()]

    l6_seen: dict[str, dict] = {}
    kp_seen: dict[str, dict] = {}
    baseline_seen: dict[str, dict] = {}

    # ── L6 料号库 ──
    if keywords:
        repo = PartsMasterRepository()
        try:
            for kw in keywords:
                for row in repo.list(search=kw)[:PER_KEYWORD_LIMIT]:
                    pn = row.get("pn")
                    if pn and pn not in l6_seen:
                        l6_seen[pn] = _normalize_l6(row)
        finally:
            pass  # PartsMasterRepository 无 session 句柄需关闭

    # ── KP 配件库 ──
    if keywords:
        kp_repo = KPRepository()
        try:
            for kw in keywords:
                res = kp_repo.list_parts(search=kw, page=1, page_size=PER_KEYWORD_LIMIT)
                for item in res.get("items", []):
                    kid = item.get("id")
                    key = f"kp-{kid}"
                    if kid and key not in kp_seen:
                        kp_seen[key] = _normalize_kp(item)
        finally:
            kp_repo.close()

    # ── 基准配置（整机候选，按 series/form 过滤）──
    if series or form:
        bc_repo = BaseConfigRepository()
        try:
            for cfg in bc_repo.list(series=series, form=form):
                cid = cfg.get("id")
                if cid and cid not in baseline_seen:
                    baseline_seen[cid] = _normalize_baseline(cfg)
        finally:
            pass

    l6_list = list(l6_seen.values())[:MAX_PER_SOURCE]
    kp_list = list(kp_seen.values())[:MAX_PER_SOURCE]
    baseline_list = list(baseline_seen.values())[:MAX_PER_SOURCE]

    return {
        "candidates": l6_list + kp_list + baseline_list,
        "counts": {
            "l6": len(l6_list),
            "kp": len(kp_list),
            "baseline": len(baseline_list),
        },
    }


# ──────────────────────────────────────────────────────────────────
# 整机方案组合（Path A · 本地）
# 选 baseline（机箱骨架）+ 配 KP（按需求品类）→ 组装成 ConfigData 形状的 excel 快照
# ──────────────────────────────────────────────────────────────────

def _specs_str(specs) -> str:
    """specs dict → 短摘要串（取前 2 个 key=value），渲染用。"""
    if not specs or not isinstance(specs, dict):
        return ""
    try:
        items = [f"{k}={v}" for k, v in list(specs.items())[:2] if v not in (None, "")]
        return " · ".join(items)
    except Exception:
        return ""


def build_variant_signals(ext: dict, requirement_text: str = "") -> dict:
    """从 extract 结果 + 需求文本构建机型变体选择信号（R7）。

    词表/正则全部来自规则库 variant_signal_rules（默认值 + 规则覆盖），
    此处只做组合读取，不内联业务词；缺省回退默认值保证行为不变。
    """
    ext = ext or {}
    cats = ext.get("categories") or []
    low = (requirement_text or "").lower()

    from app.services.requirement_rule_catalog import variant_signal_rules
    rules = variant_signal_rules() or {}

    def _lst(v):
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return list(v)
        return [v]

    # 盘类型：SATA/SAS/NVMe；NVMe 还看需求品类别名（能力描述如"前置8*SATA"）
    kinds: set = set()
    for dk in _lst(rules.get("disk_kinds")):
        if not isinstance(dk, dict):
            continue
        token = str(dk.get("token") or "").lower()
        kind = dk.get("kind")
        if not token:
            continue
        hit = token in low
        if dk.get("check_cats") and not hit:
            hit = token in " ".join(str(c) for c in cats).lower()
        if hit and kind:
            kinds.add(kind)

    # 直通/直连：需求显式写"直通机型/直连" → 偏好直连模板（2）
    direct = any(re.search(p, low) for p in _lst(rules.get("direct_patterns")))
    # Switch 字样：需求显式写 Switch/交换 → 偏好 Switch 模板（3）
    switch = any(re.search(p, low) for p in _lst(rules.get("switch_patterns")))
    # 配置单特征：需求含 ≥2 处 "*N/×N" 购买数量 → 具体配置单（非能力描述）
    cfg_qty = len(re.findall(str(rules.get("config_qty_pattern") or r"[*\u00d7]\s*\d+"), low)) >= 2
    # RAID：需求含 Raid card 品类或 raid/阵列 字样
    raid_cats = _lst(rules.get("raid_cats"))
    raid_words = _lst(rules.get("raid_words"))
    has_raid = bool(any(c in cats for c in raid_cats) or any(w in low for w in raid_words))
    # CPU 品类名（默认 CPU）
    cpu_cats = _lst(rules.get("cpu_cats"))
    # GPU 数量唯一真值源：gpu_groups（不再读 qty_map.GPU）
    gpu_gq = str(rules.get("gpu_group_qty_key") or "qty")
    gpu_qty = 0
    for _g in ext.get("gpu_groups") or []:
        gpu_qty = max(gpu_qty, int(_g.get(gpu_gq) or 0))

    return {
        "gpu_qty": gpu_qty,
        "has_raid": has_raid,
        "storage_kinds": kinds,
        "form": ext.get("form"),
        "series": ext.get("series"),
        "has_cpu": bool(any(c in cats for c in cpu_cats)),
        "direct": direct,
        "switch": switch,
        "has_config_quantities": cfg_qty,
    }
def _rank_base_config_variant(bc: dict, signals: Optional[dict], main_config_id: Optional[int]) -> int:
    """机型多基准配置变体排序分（越大越优，2026-08-03 R7）。

    设计：一个机型（server_models）可挂多个 base_config 变体（model_id 反向关联），
    每个变体绑定不同 BOM 模板（直连模板2 / Switch模板3…）。需求分析按需求信号自动选变体：
    - 形态精确匹配 +100（需求"4U" → 只认 form=4U 的变体）；
    - 需求含 RAID/存储盘（SATA/SAS）→ 偏好带 raid_slot 的 Switch 模板（3）；
    - 纯 GPU+NVMe → 偏好直连模板（2）；
    - 主配置（base_config_id）+5 作默认保底。
    """
    score = 0
    s = signals or {}
    req_form = s.get("form")
    if req_form and str(bc.get("form") or "") == str(req_form):
        score += 100
    storage = bool((s.get("storage_kinds") or set()) & {"SATA", "SAS"}) or bool(s.get("has_raid"))
    gpu = int(s.get("gpu_qty") or 0)
    tpl = bc.get("bom_template_id")
    # 直通/直连信号（R8/I39）：显式要求直通 → 直连模板（2）大额加分，压过 RAID/SATA 的 Switch 偏好
    if s.get("direct") and tpl == 2:
        score += 120
    elif s.get("direct") and tpl == 3:
        score -= 60
    # Switch 字样（R9/I46）：显式 Switch/交换 → Switch 模板（3）大额加分
    if s.get("switch") and tpl == 3:
        score += 120
    elif s.get("switch") and tpl == 2:
        score -= 60
    # 8 卡直连默认（R9/I46、R10/I49）：≥8 GPU + 具体配置单（有 *N 数量）→ 直连模板（2）。
    # 技术员对"8 卡 GPU 具体配置单"用 Direct connected（PXJ-2026-0715 / Ruby-2026-0623，
    # 后者未写 4U 也按直连）；能力描述（R7 典型报价单，无 *N）仍按 RAID/存储盘 → Switch 模板（3）。
    gpu8_direct = gpu >= 8 and bool(s.get("has_config_quantities"))
    if gpu8_direct and s.get("has_cpu"):
        # 需求提到 CPU（平台可辨，如 AMD/Intel/兆芯）→ 8卡具体配置单默认直连（R9/R10 技术员 Direct connected）
        if tpl == 2:
            score += 60
    elif not gpu8_direct:
        # 能力描述（非具体配置单）走 RAID/存储偏好
        if storage and tpl == 3:
            score += 50
        elif storage and tpl in (None, 1):
            score += 40
        elif gpu and not storage and tpl == 2:
            score += 50
        elif gpu and storage and tpl == 3:
            score += 30
    # gpu8_direct 且需求未提 CPU（裸 8卡 AI，平台不可辨）：不加任何平台偏向，
    # ESA24V3-P(Orion) 与 ZSA24V2-P(Polaris) 都作为候选推荐，让用户选（R20 业务决策）
    if bc.get("id") == main_config_id:
        score += 5
    return score


def _variant_short_name(cfg_name: str) -> str:
    """变体名 → 短标签："4U-Orion-Switch机型" → "Switch"；"Orion 2U12 直连版…" → "直连版"。”"""
    n = (cfg_name or "").replace("机型", "").strip()
    for pre in ("4.5U-", "4U-", "2U25-", "2U12-", "Orion ", "Polaris ", "ES22V3-P", "ESA24V3-P"):
        n = n.replace(pre, "").strip()
    return n or (cfg_name or "")


def select_models(usage: Optional[str], server_type_name: Optional[str] = None,
                  series: Optional[str] = None, form: Optional[str] = None,
                  limit: Optional[int] = None,
                  no_signal_strategy: Optional[str] = "return_empty",
                  variant_signals: Optional[dict] = None,
                  fallback_order: Optional[list] = None) -> list[dict]:
    """按机型类型 + series/form 从【机型层】选 1-N 个机型作整机骨架。

    类型匹配：server_type_name 精确（词表/目录引导配的真实类型名）；无类型信号但有形态 → 默认通用计算；
    无任何信号 → 返空（交给 clarity_check 反问）。
    （旧 usage→类型关键词路由 USAGE_TYPE_ROUTING 已删：usage 现只来自配置词表、与 server_type_name 同源，
    模糊路由是死代码。）
    选 server_models（机型，有 server_type/use）而非旧 base_configs 直选
    （基准配置，无 type）；**匹配多少给多少，不硬塞全量凑数**。

    返回每条 dict 兼容 build_plan 原 baseline 字段（id/series/form/bays/parts_count/total_price/
    bom_template_id）+ 机型顶层字段（server_model_id/name/use/product_content/server_type_*）。
    其中 id = base_config_id（下游 confirmPlan/buildPlanCfg 靠它，语义不变）。
    无任何信号（usage/type/series/form 都空）→ 返空，不硬推全量（交给 clarity_check 反问）。
    """
    if not any([usage, server_type_name, series, form]):
        if no_signal_strategy != "fallback_all":
            return []  # return_empty（默认）/ prompt 都返空让反问；fallback_all 才继续查全量
    cat_repo = ServerCatalogRepository()
    types = cat_repo.list_types()
    # 优先按 server_type_name 精确匹配（词表配的就是真实类型名），未给走 usage 关键词模糊
    type_id = None
    if server_type_name:
        for t in types:
            if t.get("name") == server_type_name:
                type_id = t["id"]
                break
    # 无类型信号但有形态（如"2U"）→ 取目录排序首个类型作默认（admin 配 sort_order），
    # 避免 AI/存储机型混入结果；不在代码里写死"通用计算服务器"。
    if type_id is None and form and types:
        type_id = types[0]["id"]
    # 多级放宽选型（可配 fallback_order，见 model_reason 节点抽屉；默认 exact→same_series→
    # same_form→all）：严格条件命中不了时，按用户配置的顺序逐级放宽（先保系列、再保形态、最后保类型）。
    # 类型始终保留：某类型 0 机型就返空反问，禁止去掉 type 混入其他类型。命中级记 match_stage/
    # fallback_note 供白盒展示「为什么给了这个替代」，绝不静默。
    _stage_fn = {
        "exact": lambda: (type_id, series, form),
        "same_series": lambda: (type_id, series, None),
        "same_form": lambda: (type_id, None, form),
        "all": lambda: (type_id, None, None),
    }
    stages = [st for st in (fallback_order or ["exact", "same_series", "same_form", "all"]) if st in _stage_fn]
    models: list = []
    match_stage = None
    relaxed_dims: list = []
    for st in stages:
        _t, _s, _f = _stage_fn[st]()
        _cands = cat_repo.list_models(type_id=_t, series=_s, form=_f, published_only=True)
        if _cands:
            models = _cands
            match_stage = st
            # 记录相对原始请求放宽了哪些维度（数据驱动，非硬编码话术）
            if series and _s is None:
                relaxed_dims.append("平台系列")
            if form and _f is None:
                relaxed_dims.append("机箱形态")
            if server_type_name and _t is None:
                relaxed_dims.append("服务器类型")
            break
    if not models:
        # 全级放宽仍空 → 返空（交反问），与旧行为一致
        models = []
    type_name_by_id = {t["id"]: t.get("name") or "" for t in types}
    # 批量取 base_configs 聚合（parts_count/total_price/bom_template_id）
    bc_repo = BaseConfigRepository()
    bc_map = {bc["id"]: bc for bc in bc_repo.list()}
    out: list[dict] = []
    for m in models:
        bc_id = m.get("base_config_id")
        if not bc_id:
            continue  # 无主配置机型（新建未关联/未设主）跳过：选型需要可配置 baseline
        sid = m.get("server_type_id")
        # 机型多基准配置变体（R7）：一个机型挂多个 base_config（model_id 反向关联，各绑不同
        # BOM 模板），按需求信号排序全部给出；单变体机型行为不变（只有主配置）。
        # 按机型分组而非全局排序：跨机型竞争会让 ZSA(4U AI) 混入存储需求并靠 storage+50 反超（R13 回归）
        mid = m.get("id")
        variants = [bc for bc in bc_map.values() if bc.get("model_id") == mid] or [bc_map.get(bc_id, {})]
        variants = [v for v in variants if v]
        variants.sort(key=lambda v: (-_rank_base_config_variant(v, variant_signals, bc_id), v.get("id") or 0))
        for bc in variants:
            if limit is not None and len(out) >= limit:
                break
            bc_embed = m.get("base_config") or {}
            _name = m.get("name") or ""
            if len(variants) > 1:
                _name = f"{_name}（{_variant_short_name(bc.get('name') or '')}）"
            out.append({
                # 机型顶层字段
                "server_model_id": m.get("id"),
                "name": _name,
                "use": m.get("use") or "",
                "product_content": m.get("product_content"),
                "server_type_id": sid,
                "server_type_name": type_name_by_id.get(sid, "") if sid is not None else "",
                # base_config 元信息（build_plan/下游按 baseline 字段消费，id = base_config_id）
                "id": bc.get("id"),
                "series": bc_embed.get("series") or bc.get("series"),
                "form": bc_embed.get("form") or bc.get("form"),
                "bays": bc_embed.get("bays") if bc_embed.get("bays") is not None else bc.get("bays"),
                "model": m.get("name") or bc.get("model") or "",
                "bom_template_id": bc.get("bom_template_id"),
                # 白盒标注：命中级 + 放宽说明（"库内无 X，已按最接近给出"——分析可见，非黑盒）
                "match_stage": match_stage,
                "fallback_note": _fallback_note(match_stage, relaxed_dims, series, form),
                # 机箱能力约束（基准配置页「机箱能力」可配）：PSU 档位 / CPU 上限 / 内存条数上限 / 每路通道数
                # 缺省 None → 消费端用全局兜底（不把物理边界硬编码在推理链路）
                "psu_wattages": bc.get("psu_wattages") or None,
                "max_cpu": bc.get("max_cpu") or None,
                "max_dimm": bc.get("max_dimm") or None,
                "mem_channels": bc.get("mem_channels") or None,
                "gpu_slots": bc.get("gpu_slots") or None,
                "max_tdp": bc.get("max_tdp") or None,
                "parts_count": int(bc.get("parts_count") or 0),
                "total_price": float(bc.get("total_price") or 0),
                # 机型卡片渲染所需顶层字段（候选卡/详情页自配入口用；下游仍按 id/series/form 消费，不破坏）
                "image_url": m.get("image_url"),
                "description": m.get("description"),
                "lifecycle_status": m.get("lifecycle_status"),
                "is_published": m.get("is_published"),
                "base_config": m.get("base_config"),
            })
    results = out if limit is None else out[:limit]
    _annotate_recommend(results)
    return results


_STAGE_LABEL = {"exact": "精确匹配", "same_series": "放宽形态", "same_form": "放宽系列", "all": "放宽系列+形态"}


def _fallback_note(stage: Optional[str], relaxed: list, series: Optional[str], form: Optional[str]) -> str:
    """命中级的白盒说明：精确命中 → "精确匹配"；放宽命中 → 说明放宽了什么维度。
    纯数据驱动（由实际放宽维度生成），不硬编码具体机型/系列。"""
    if not stage or stage == "exact":
        return "精确匹配"
    parts = []
    if relaxed:
        parts.append("、".join(relaxed))
    req = []
    if series:
        req.append(f"{series} 平台")
    if form:
        req.append(form)
    if req and relaxed:
        return f"库内无「{' '.join(req)}」全匹配机型，已放宽【{ '、'.join(relaxed) }】，按最接近给出候选（如需精确请调整需求）"
    return f"按{'/'.join(relaxed) or '最接近'}给出候选"


def _annotate_recommend(baselines: list[dict]) -> None:
    """S1: 读 selection.model_recommend 策略，按 scope.series 给 baseline 附加
    recommend_level（recommend/avoid/neutral）+ selling_points（包装点）。仅标注，不改检索。
    series 维度与 KP 配件适用系列、base_config.series 同源（system_config.server_series）。
    自动读取全部 active 规则，不做单策略筛选。"""
    try:
        from app.repository.strategy_repo import StrategyRepository
        repo = StrategyRepository()
        rules = [r for r in repo.list(domain='selection', status='active') if r.get('type') == 'model_recommend']
        repo.close()
    except Exception:
        return
    if not rules:
        return
    for b in baselines:
        for r in rules:
            sc = r.get('scope') or {}
            if sc.get('series') and b.get("series") != sc['series']:
                continue
            body = r.get('body') or {}
            b['recommend_level'] = body.get('level', 'neutral')
            b['selling_points'] = body.get('selling_points', '')
            break


def _load_power_calibration() -> dict:
    """功耗/电源推断校准：规则库 power_calibration 为基准，system_config.psu_inference 可覆盖其中的键。
    都缺失返回 {}（不内置词表/档位；未配置则不臆断，由调用方安全降级）。"""
    calib: dict = {}
    try:
        from app.services.requirement_rule_catalog import power_calibration as _pc
        calib = _pc()
    except Exception:
        calib = {}
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("psu_inference")
        finally:
            repo.close()
        if isinstance(cfg, dict) and cfg:
            calib = {**(calib or {}), **cfg}
    except Exception:
        pass
    return calib or {}


def _load_psu_inference() -> dict:
    """兼容旧调用名：电源推断配置 = 功率校准字典。"""
    return _load_power_calibration()


def _kp_signals(kp_parts: list[dict]) -> tuple:
    """从 KP 结果提信号：GPU 数 + 是否含高功耗 GPU + 盘类型集合(NVMe/SAS/SATA)。"""
    _psu_cfg = _load_psu_inference()
    from app.services.requirement_rule_catalog import kp_signal_rules
    rules = kp_signal_rules() or {}
    _gpu_cats = [str(x) for x in (rules.get("gpu_cats") or [])]
    _drive_cats = [str(x) for x in (rules.get("drive_cat_keywords") or [])]
    _drive_protos = rules.get("drive_protocol_kinds") or []
    _drive_default_kind = rules.get("drive_default_kind") or "SATA"
    # 高功耗 GPU 词表去空白归一（R8/I43 修）：词表 "RTX 5090"，件名 "RTX5090" 无空格
    # → 直接子串匹配 miss，8×RTX5090 掉到 2000W。归一后两端都去空白再比。
    _high_tdp_words = [re.sub(r"\s+", "", str(k)).upper() for k in (_psu_cfg.get("high_tdp_gpus") or []) if k]
    _tdp_threshold_raw = _psu_cfg.get("high_tdp_threshold_w")
    try:
        _tdp_threshold = float(_tdp_threshold_raw) if _tdp_threshold_raw not in (None, "") else None
    except (TypeError, ValueError):
        _tdp_threshold = None
    _tdp_by_model = {re.sub(r"\s+", "", str(k)).upper(): float(v)
                     for k, v in (_psu_cfg.get("gpu_tdp_by_model") or {}).items() if k and v}
    gpu_qty = 0
    gpu_tdp_max = 0.0
    drive_kinds: set = set()
    has_drive = False
    for kp in kp_parts or []:
        cat = (kp.get("category") or kp.get("part_category") or "")
        cat_u = cat.upper()
        qty = int(kp.get("qty") or 1)
        name_u = (kp.get("name") or "").upper()
        if any(k.upper() in cat_u for k in _gpu_cats):
            gpu_qty += qty
            # 数据驱动 TDP：配件库 specs.tdp 优先（如 "AMD AI Pro R9700 32G" tdp=300）
            _gpu_tdp = None
            _sp = kp.get("specs") or {}
            if isinstance(_sp, dict):
                _gpu_tdp = _sp.get("tdp") or _sp.get("TDP") or _sp.get("Power")
            if _gpu_tdp is None:
                # 配置表兜底（用户可维护 gpu_tdp_by_model）
                for _mk, _tv in _tdp_by_model.items():
                    if _mk in re.sub(r"\s+", "", name_u):
                        _gpu_tdp = _tv
                        break
            if _gpu_tdp is not None:
                try:
                    gpu_tdp_max = max(gpu_tdp_max, float(_gpu_tdp))
                except (TypeError, ValueError):
                    pass
            # 词表兜底（无 TDP 数据时）
            _name_compact = re.sub(r"\s+", "", name_u)  # I43：件名去空白（RTX5090 ↔ RTX 5090）
            if _tdp_threshold is not None and any(k in _name_compact for k in _high_tdp_words):
                gpu_tdp_max = max(gpu_tdp_max, float(_tdp_threshold))
        blob = f"{cat} {kp.get('name') or ''} {kp.get('matched_spec') or ''}".upper()
        _cat_hit = any(k in cat_u for k in _drive_cats)
        _proto_hit = False
        for _pr in _drive_protos:
            if isinstance(_pr, dict):
                _tok = str(_pr.get("token") or "").upper()
                _kind = _pr.get("kind")
            else:
                _tok = str(_pr or "").upper()
                _kind = None
            if _tok and _tok in blob:
                _proto_hit = True
                if _kind:
                    drive_kinds.add(_kind)
        if _cat_hit or _proto_hit:
            has_drive = True
    if has_drive and not drive_kinds:
        drive_kinds.add(_drive_default_kind)  # 协议不明默认（规则库 drive_default_kind）
    high_tdp = bool(_tdp_threshold is not None and gpu_tdp_max >= _tdp_threshold)
    return gpu_qty, drive_kinds, high_tdp, gpu_tdp_max


# 无 GPU 整机负载粗估（CPU TDP + 常项）→ 取 ≥负载的最小标准 PSU 瓦数（1+1 冗余）
# 各项由规则库 power_calibration 驱动；未配置则不臆断（按 0/空处理，由调用方安全降级）。
def _estimate_system_load(kp_parts: list[dict]) -> int:
    """按 KP 件粗估整机负载（W）。CPU 查 TDP 表，其余按件均摊——纯估算用于电源建议，
    不是精确功耗计算。数值与品类关键词均来自规则库（power_calibration / part_family_keywords）。"""
    from app.services.requirement_rule_catalog import part_family_keywords
    calib = _load_power_calibration()
    _pfk = part_family_keywords()

    def _match(fam: str, cu: str, cat: str, nu: str) -> bool:
        kws = _pfk.get(fam) or {}
        return (any(k in cu for k in kws.get("cat_upper", []))
                or any(k in cat for k in kws.get("cat", []))
                or any(k in nu for k in kws.get("name_upper", [])))

    load = int(calib.get("sys_base_w") or 0)
    tdp_map = calib.get("cpu_tdp_map") or {}
    default_cpu_tdp = calib.get("default_cpu_tdp") or 0
    mem_default_w = calib.get("mem_stick_w") or 0
    mem_by_cap = calib.get("mem_stick_w_by_cap") or []
    sata_w = calib.get("sata_drive_w") or 0
    nvme_w = calib.get("nvme_drive_w") or 0
    nic_w = calib.get("nic_w") or 0
    raid_w = calib.get("raid_w") or 0
    for kp in kp_parts or []:
        cat = kp.get("category") or ""
        name = f"{kp.get('name') or ''} {kp.get('matched_spec') or ''}"
        qty = int(kp.get("qty") or 1)
        cu = cat.upper()
        nu = name.upper()
        if _match("cpu", cu, cat, nu):
            _tdp = None
            try:
                _tdp = float((kp.get("specs") or {}).get("tdp") or 0) or None
            except (TypeError, ValueError):
                _tdp = None
            if _tdp:
                load += _tdp * qty
            else:
                m = re.search(r"(\d{4})", name)
                tdp = float(tdp_map.get(m.group(1).lower(), default_cpu_tdp) if m else default_cpu_tdp)
                load += tdp * qty
        elif _match("memory", cu, cat, nu):
            _m = re.search(r"(\d{1,3})\s*G\s*B?\b", name, re.I)
            _cap = int(_m.group(1)) if _m else 0
            _w = mem_default_w
            for _cm, _cw in mem_by_cap:
                if _cap <= _cm:
                    _w = _cw
                    break
            load += _w * qty
        elif _match("nvme", cu, cat, nu):
            load += nvme_w * qty
        elif _match("disk", cu, cat, nu):
            load += sata_w * qty
        elif _match("nic", cu, cat, nu):
            load += nic_w * qty
        elif _match("raid", cu, cat, nu):
            load += raid_w
    return int(load)


def _suggest_psu_wattage(load: int) -> str:
    """1+1 冗余电源：单 PSU ≥ 估算负载 → 取 ≥负载的最小标准瓦数。未配置标准档位 → ""（不臆断）。"""
    std = _load_power_calibration().get("psu_standard_w") or []
    for w in std:
        if w >= load:
            return str(w)
    return str(std[-1]) if std else ""


def _find_backplane_part(bt: str) -> Optional[dict]:
    """料号库找目标背板件（category=前置硬盘背板 + specs.bt == bt），找不到返回 None。"""
    try:
        repo = PartsMasterRepository()
        parts = repo.list(category="前置硬盘背板")
    except Exception as e:
        logger.warning("读取背板料号失败 bt=%s: %s", bt, e)
        return None
    for p in parts or []:
        if (p.get("specs") or {}).get("bt") == bt:
            return p
    return None


def _sync_plan_backplane(plan: dict, base_parts: list) -> None:
    """方案 BOM 背板件与派生 bp_type 对齐（2026-08-03 第一轮训练发现）：
    bp_type=tri 但基线 BOM 行是直连背板（如 ES22V3-P 基线为 Orion 2U12 直连版）时，
    把 bom_excel_rows 背板行换成料号库同 bt 的件并补价差（l6_cost/total_cost）。
    无目标件/解析失败 → 保留原行不阻塞（方案照常出）。"""
    bp_type = (plan.get("chassis_signals") or {}).get("bp_type")
    if bp_type not in ("tri", "dc"):
        return
    rows = (plan.get("cfg") or {}).get("bom_excel_rows") or []
    if not rows:
        return

    def _bt_of(blob: str) -> Optional[str]:
        if re.search(r"\bbt\s*=\s*tri|tri-?mode", blob, re.I):
            return "tri"
        if re.search(r"\bbt\s*=\s*dc|pass-?thru|直连", blob, re.I):
            return "dc"
        return None

    bp_rows = [r for r in rows if re.search(r"背板|backplane|pass-?thru|tri-?mode", f"{r.get('catalogue') or ''} {r.get('description') or ''}", re.I)]
    changed = False
    for r in bp_rows:
        blob = f"{r.get('catalogue') or ''} {r.get('description') or ''}"
        if _bt_of(blob) != bp_type:
            changed = True
            break
    if not changed:
        return  # 已对齐（或无 bt 标注——不动，避免误判）

    new_part = _find_backplane_part(bp_type)
    if not new_part:
        return
    old_price = None
    for p in base_parts or []:
        if re.search(r"背板|backplane", p.get("category") or "", re.I):
            try:
                old_price = float(p.get("unit_price") or 0)
            except (TypeError, ValueError):
                old_price = None
            break
    _bt = (new_part.get("specs") or {}).get("bt") or bp_type
    for r in bp_rows:
        blob = f"{r.get('catalogue') or ''} {r.get('description') or ''}"
        if _bt_of(blob) == bp_type:
            continue
        r["catalogue"] = new_part.get("name") or new_part.get("pn") or r.get("catalogue")
        r["description"] = (new_part.get("pn") or "") + f" · bt={_bt}"
    if old_price is not None:
        try:
            delta = float(new_part.get("unit_price") or 0) - old_price
        except (TypeError, ValueError):
            delta = 0.0
        summary = plan.setdefault("summary", {})
        summary["l6_cost"] = round(float(summary.get("l6_cost") or 0) + delta, 2)
        summary["total_cost"] = round(float(summary.get("total_cost") or 0) + delta, 2)


def _clamp_psu_wattage(w: str, allowed_wattages=None) -> str:
    """把推断瓦数收敛到机型允许档位（基准配置 psu_wattages，如 ES22V3-P=[1300,1600,2000]）。
    未配置/非法档位列表 → 原样返回（沿用全局档位）；推断值不在档内 →
    取 ≥推断值的最小档，无更高档则取最大档（机型物理上限，宁高勿低）。"""
    try:
        w_int = int(float(w))
    except (TypeError, ValueError):
        return w
    if not allowed_wattages:
        return w
    try:
        allowed = sorted({int(float(x)) for x in allowed_wattages if x not in (None, "")})
    except (TypeError, ValueError):
        return w
    if not allowed:
        return w
    if w_int in allowed:
        return str(w_int)
    for a in allowed:
        if a >= w_int:
            return str(a)
    return str(allowed[-1])


def _infer_psu_wattage(gpu_qty: int, high_tdp: bool = False, kp_parts: Optional[list] = None,
                       allowed_wattages=None) -> str:
    """电源瓦数推断（配置驱动：system_config.psu_inference 的 tiers 档位，逐条匹配取首个；
    无 GPU 按 KP 件功耗估算（CPU TDP + 常项）取 ≥负载的最小标准瓦数，替代无脑 1600W 默认）。
    allowed_wattages=机型允许档位（基准配置 psu_wattages）→ 结果收敛到机型物理支持范围。
    喂前端模板电源行 chassis_signals.psu_wattage；需求文本若显式写了功率，由调用方覆盖。"""
    _cfg = _load_psu_inference()
    for t in _cfg.get("tiers") or []:
        if gpu_qty >= int(t.get("min_gpu") or 0) and bool(t.get("high_tdp")) == high_tdp:
            w = t.get("wattage")
            if w is not None:
                return _clamp_psu_wattage(str(w), allowed_wattages)
    if not gpu_qty:
        return _clamp_psu_wattage(_suggest_psu_wattage(_estimate_system_load(kp_parts)), allowed_wattages)
    _no_gpu_w = _cfg.get("no_gpu_wattage")
    if _no_gpu_w in (None, ""):
        return ""
    return _clamp_psu_wattage(str(_no_gpu_w), allowed_wattages)


def build_plan(baseline: dict, kp_parts: list[dict], psu_wattage: Optional[str] = None,
               psu_qty: Optional[int] = None) -> dict:
    """单 baseline + KP 列表 → 整机方案（含喂给 BomTable 的 excel 快照 cfg）。
    unmatched 件（spec 未命中、fallback=mark_unmatched）不入 bom_excel_rows，单独塞 plan.unmatched
    让前端方案卡标"需手填"badge（保持 BOM 干净）。"""
    bc_repo = BaseConfigRepository()
    full = bc_repo.get_with_parts(baseline.get("id")) or {}
    parts = full.get("parts") or []

    matched_kp = [kp for kp in kp_parts if not kp.get("unmatched")]
    unmatched_items = [{
        "category": kp.get("category") or "",
        "reason": kp.get("unmatched_reason") or "规格未命中，需手填",
    } for kp in kp_parts if kp.get("unmatched")]

    # 电源瓦数推断（纯性能推算：CPU TDP + 内存按容量计功耗 + 常项 → ≥负载最小标准档）。
    # I15/I61 2026-08-04 R24：不再用静态"机型标准"字段——改进负载模型（内存按容量计功耗），
    # 让 64G×24 这类高内存配置自然推断出 1600W（原 10W/条 低估 → 1300W）。
    _gpu_qty, _, _high_tdp, _gpu_tdp = _kp_signals(matched_kp)
    # PSU 档位按机型物理支持收敛（基准配置 psu_wattages；未配 → 全局档位）
    chassis_signals = {"psu_wattage": _infer_psu_wattage(
        _gpu_qty, _high_tdp, matched_kp,
        allowed_wattages=baseline.get("psu_wattages"),
    )}
    # 需求显式瓦数/数量优先覆盖推断值；必须在求值 L6 模板之前套用，否则模板行仍显示默认瓦数。
    if psu_wattage not in (None, ""):
        chassis_signals["psu_wattage"] = psu_wattage
    if psu_qty is not None:
        chassis_signals["psu_qty"] = int(psu_qty)

    # 先执行选型配置规则，补出 bp_type / cable_qty_by_kind，再求值 L6 模板。
    # 这里不能沿用内部料号平铺；必须与人工方案配置共用同一套 BOM 模板。
    selection_alerts: list = []
    try:
        from app.services.plan_rule_apply import apply_plan_selection_rules
        signal_plan = {"chassis_signals": chassis_signals}
        apply_plan_selection_rules(signal_plan, matched_kp, baseline)
        chassis_signals = signal_plan.get("chassis_signals") or chassis_signals
        selection_alerts = signal_plan.get("selection_alerts") or []
    except Exception:
        logger.exception("apply_plan_selection_rules failed; plan continues without rule-derived signals")

    template_id = baseline.get("bom_template_id")
    used_template_l6 = False
    if template_id and baseline.get("id"):
        try:
            from app.services.bom_template_eval import eval_l6_rows
            raw_l6 = eval_l6_rows(
                int(template_id), int(baseline.get("id")), matched_kp, chassis_signals
            )
            l6_rows = [{"category": "L6", **dict(row)} for row in raw_l6]
            used_template_l6 = True
        except Exception:
            logger.exception("eval_l6_rows failed; fallback to base-config L6 rows template_id=%s", template_id)
            used_template_l6 = False

    if not used_template_l6:
        l6_rows = [{
            "category": "L6",
            "catalogue": p.get("name") or p.get("pn") or "",
            "description": (p.get("pn") or "") + (f" · {_specs_str(p.get('specs'))}" if _specs_str(p.get('specs')) else ""),
            "qty": p.get("quantity") or 1,
        } for p in parts]

    kp_rows = [{
        "category": "Key Parts",
        "catalogue": kp.get("pn") or "",
        "description": (kp.get("name") or "") + (f" · {kp['matched_spec']}" if kp.get("matched_spec") else "")
                      + (f" · {kp['replacement_note']}" if kp.get("replacement_note") else ""),
        "part_category": kp.get("category") or "",
        "qty": kp.get("qty") or 1,
        "base_price": kp.get("unit_price") or 0,
        "currency": kp.get("currency") or "RMB",
    } for kp in matched_kp]

    # 货币折算（口径对齐报价工作台 store/quote.ts:194）：USD 件 base 不含税 → ×汇率×(1+增值税率) 折成含税 RMB；
    # RMB 件已含税直用；baseline（底盘）currency=RMB 已含税。total_cost 统一为含税 RMB，避免美元数值当人民币混加。
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        _cfg = SystemConfigRepository()
        try:
            tax_rate = float(_cfg.get_value("tax_rate", 0.13))
            usd_to_rmb = float(_cfg.get_value("usd_to_rmb", 7.0))
        finally:
            _cfg.close()
    except Exception:
        tax_rate, usd_to_rmb = 0.13, 7.0

    def _rmb(price, currency):
        p = float(price or 0)
        return p * usd_to_rmb * (1 + tax_rate) if str(currency or "RMB").upper() == "USD" else p

    l6_cost = float(baseline.get("total_price") or 0)
    kp_cost = sum(_rmb(kp.get("unit_price"), kp.get("currency")) * (kp.get("qty") or 1) for kp in matched_kp)
    total_cost = l6_cost + kp_cost

    plan = {
        "config_id": baseline.get("id"),
        "server_model_id": baseline.get("server_model_id"),
        "name": baseline.get("name") or "",
        "use": baseline.get("use") or "",
        "product_content": baseline.get("product_content"),
        "model": baseline.get("model") or "",
        "series": baseline.get("series") or "",
        "form": baseline.get("form") or "",
        "bays": baseline.get("bays"),
        "bom_template_id": baseline.get("bom_template_id"),
        "chassis_signals": chassis_signals,
        "recommend_level": baseline.get("recommend_level") or "",
        "selling_points": baseline.get("selling_points") or "",
        "selection_alerts": selection_alerts,
        "unmatched": unmatched_items,
        "summary": {
            "parts_count": int(baseline.get("parts_count") or 0),
            "kp_count": len(kp_rows),
            "unmatched_count": len(unmatched_items),
            "l6_cost": round(l6_cost, 2),
            "kp_cost": round(kp_cost, 2),
            "total_cost": round(total_cost, 2),
            "currency": "RMB",  # total_cost 已折算统一为含税 RMB（USD 件 ×usd_to_rmb×(1+tax_rate)）
            "rates": {"usd_to_rmb": usd_to_rmb, "tax_rate": tax_rate},
        },
        "cfg": {
            "bom_source": "excel",
            "bom_excel_rows": l6_rows + kp_rows,
        },
    }

    # 背板件与派生 bp_type 对齐只用于旧的内部料号平铺降级路径；BOM 模板求值已按 bp_type 渲染。
    if not used_template_l6:
        try:
            _sync_plan_backplane(plan, parts)
        except Exception:
            logger.exception("sync plan backplane failed; plan keeps original rows")

    return plan


@router.get("")
def search(
    q: str = Query("", description="关键词，空格或逗号分隔多个"),
    series: Optional[str] = Query(None),
    form: Optional[str] = Query(None),
):
    """聚合候选检索端点。q 切分为关键词列表后调 search_candidates。"""
    raw = (q or "").strip()
    if not raw:
        return {"candidates": [], "counts": {"l6": 0, "kp": 0, "baseline": 0}}
    # 按逗号/空白切分（中英文逗号都支持）
    keywords = [k for k in re.split(r"[,\s，、]+", raw) if k]
    return search_candidates(keywords, series=series, form=form)
