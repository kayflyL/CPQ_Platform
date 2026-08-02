"""Candidate search — 聚合检索 + 整机方案组合。

search_candidates(): 关键词 → L6 料号 + KP 配件 + 基准配置 散件级聚合（一期，保留供 REST 用）。
compose_plans(): 关键词/品类/系列/形态 → 2-3 张整机 BOM 方案（baseline 底盘 + 配齐 KP），
                 供 requirement_intel_service 的 pipeline 和未来 REST 共用。
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Query

from app.repository.parts_master_repo import PartsMasterRepository
from app.repository.kp_repo import KPRepository
from app.repository.base_config_repo import BaseConfigRepository
from app.repository.server_catalog_repo import ServerCatalogRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidate-search", tags=["candidate-search"])

PER_KEYWORD_LIMIT = 30  # 每个关键词每个数据源最多取多少条，避免爆炸
MAX_PER_SOURCE = 100    # 单数据源去重后上限
MAX_PLANS = 3           # 整机方案组合最多产出几张
MODEL_TOKEN_RE = re.compile(r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$")  # 型号 token（必含数字）：字母开头混合/纯数字≥4/数字开头混合(960G/7.68T/9560-8i)


def _normalize_l6(row: dict) -> dict:
    return {
        "source": "l6",
        "id": row.get("pn"),
        "pn": row.get("pn"),
        "name": row.get("name") or "",
        "category": row.get("category") or "",
        "section": row.get("section") or "",
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

# 需求品类（CATEGORY_LEXICON key）→ KP DB 分类名候选；命中其一即用，对齐 KP 分类命名漂移
CATEGORY_KP_ALIASES: dict[str, list[str]] = {
    "CPU": ["CPU", "处理器"],
    "Memory": ["Memory", "内存", "内存条", "RAM"],
    "HDD/SSD": ["HDD", "SSD", "硬盘", "Storage", "存储"],
    "GPU": ["GPU", "显卡", "图形卡"],
    "NIC": ["NIC", "网卡", "Network"],
    "Raid card": ["RAID", "Raid", "阵列卡"],
    "Power": ["PSU", "电源", "Power"],
    "Fan": ["Fan", "风扇"],
    "Heatsink": ["Heatsink", "散热器", "散热"],
    "Cable": ["Cable", "线缆"],
    "Rail": ["Rail", "导轨"],
    "Backplane": ["Backplane", "背板"],
}


def _specs_str(specs) -> str:
    """specs dict → 短摘要串（取前 2 个 key=value），渲染用。"""
    if not specs or not isinstance(specs, dict):
        return ""
    try:
        items = [f"{k}={v}" for k, v in list(specs.items())[:2] if v not in (None, "")]
        return " · ".join(items)
    except Exception:
        return ""


def _match_kp_category(need_cat: str, db_cats: list[str],
                       aliases_map: Optional[dict] = None) -> Optional[str]:
    """需求品类 → 命中的 KP DB 分类名（先精确别名，再子串兜底）。无命中返回 None。
    aliases_map：自定义别名表（来自 reasoning_flow 配置）；默认 None 用模块 CATEGORY_KP_ALIASES。"""
    src = aliases_map if aliases_map is not None else CATEGORY_KP_ALIASES
    aliases = src.get(need_cat, [])
    db_low = {c: (c or "").lower() for c in db_cats}
    # 1. 别名精确（不区分大小写）
    for a in aliases:
        for c, cl in db_low.items():
            if cl == a.lower():
                return c
    # 2. 别名子串
    for a in aliases:
        for c, cl in db_low.items():
            if a.lower() in cl or cl in a.lower():
                return c
    # 3. 需求品类自身 token 兜底
    for tok in re.split(r"[/\s]+", (need_cat or "").lower()):
        if len(tok) < 2:
            continue
        for c, cl in db_low.items():
            if tok in cl:
                return c
    return None


def select_baselines(series: Optional[str], form: Optional[str],
                     limit: int = MAX_PLANS,
                     recommend_strategy_id: Optional[int] = None) -> list[dict]:
    """按系列/形态选 1-3 个 baseline 作整机骨架。

    策略：精确(series+form) → 补同系列不同形态 → 补同形态不同系列 → 兜底全量。
    保证尽量给到 limit 张供用户对比；repo.list 已聚合 parts_count + total_price。
    recommend_strategy_id：可选，只用指定的 model_recommend 策略标注；None=读全部 active。
    """
    repo = BaseConfigRepository()
    seen: dict[int, dict] = {}

    def _add(cfgs):
        for cfg in cfgs:
            cid = cfg.get("id")
            if cid is not None and cid not in seen:
                seen[cid] = cfg

    _add(repo.list(series=series, form=form))
    if len(seen) < limit and series:
        _add(repo.list(series=series))
    if len(seen) < limit and form:
        _add(repo.list(form=form))
    if len(seen) < limit:
        _add(repo.list())
    results = list(seen.values())[:limit]
    _annotate_recommend(results, recommend_strategy_id)
    return results


# ===== 机型类型 → 标准 KP 品类套餐（起步硬编码，后续可挪 system_config） =====
TYPE_KP_CATEGORIES: dict[str, list[str]] = {
    "AI": ["CPU", "GPU", "Memory", "HDD/SSD"],
    "存储": ["CPU", "Memory", "HDD/SSD", "Raid card"],
    "通用": ["CPU", "Memory", "HDD/SSD"],
}


def kp_categories_for_type(type_name: str, type_packages: Optional[list] = None,
                           requested_cats: Optional[list[str]] = None) -> list[str]:
    """按 server_type.name 关键词返回 KP 品类套餐。
    type_packages 来自 match_kp config（可配）：[{type_keyword, categories}]。
    None → 用模块常量 TYPE_KP_CATEGORIES 兜底（兼容老调用方）。
    requested_cats：需求 extract 出的品类；GPU 仅当需求明确要（含 GPU）才配，不随机型类型硬塞
    （AI 套餐默认含 GPU，但用户没要 GPU 时不该塞）。None = 不过滤（老调用方向后兼容）。"""
    if not type_name:
        return []
    pkgs = type_packages if type_packages is not None else [
        {"type_keyword": k, "categories": v} for k, v in TYPE_KP_CATEGORIES.items()
    ]
    cats: list[str] = []
    for pkg in pkgs:
        kw = pkg.get("type_keyword") or ""
        if kw and kw in type_name:
            cats = list(pkg.get("categories") or [])
            break
    # GPU 仅当需求明确要才配（requested_cats 非 None 且含 GPU；None=老调用方不过滤）
    if requested_cats is not None and "GPU" in cats and "GPU" not in requested_cats:
        cats = [c for c in cats if c != "GPU"]
    return cats


# usage 文本 → server_type 路由关键词（可配：未来接 system_config / reasoning config；当前集中常量，
# 拒绝散落在函数体里）。(usage 命中词, 要匹配的 server_type.name 关键词)；顺序即优先级（AI > 存储 > 通用兜底）。
USAGE_TYPE_ROUTING: list[tuple[str, str]] = [
    ("AI", "AI"),
    ("存储", "存储"),
]
USAGE_DEFAULT_TYPE_KEYWORD = "通用"  # usage 非空但未命中上面路由 → 通用计算类（默认大类）


def _match_type_by_usage(usage: Optional[str], types: list[dict]) -> Optional[int]:
    """usage → server_type_id（按 USAGE_TYPE_ROUTING 关键词路由）。
    AI类→AI训练/推理；存储类→存储；其他非空 usage→通用计算（默认大类）；usage 空→None（不限制）。"""
    if not usage:
        return None
    for usage_kw, type_kw in USAGE_TYPE_ROUTING:
        if usage_kw in usage:
            for t in types:
                if type_kw in (t.get("name") or ""):
                    return t["id"]
    # 虚拟化/数据库/通用计算/渲染 → 通用计算类（默认大类）
    for t in types:
        if USAGE_DEFAULT_TYPE_KEYWORD in (t.get("name") or ""):
            return t["id"]
    return None


def select_models(usage: Optional[str], server_type_name: Optional[str] = None,
                  series: Optional[str] = None, form: Optional[str] = None,
                  limit: int = MAX_PLANS,
                  recommend_strategy_id: Optional[int] = None,
                  no_signal_strategy: Optional[str] = "return_empty") -> list[dict]:
    """按机型类型 + series/form 从【机型层】选 1-N 个机型作整机骨架。

    类型匹配优先级：server_type_name 精确（词表配的真实类型名）> usage 关键词模糊 > 不限。
    与 select_baselines 的区别：选 server_models（机型，有 server_type/use）而非 base_configs
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
    if type_id is None:
        type_id = _match_type_by_usage(usage, types)
    # 无类型信号但有形态（如"2U"）→ 默认通用计算类型，避免 AI/存储机型混入结果
    if type_id is None and form:
        for t in types:
            if "通用" in (t.get("name") or ""):
                type_id = t["id"]
                break
    models = cat_repo.list_models(type_id=type_id, series=series, form=form)
    if not models and type_id is not None:
        # usage→type 过滤后为空：fallback 去掉 type 过滤再试（按 series/form），仍空才真返空
        models = cat_repo.list_models(series=series, form=form)
    type_name_by_id = {t["id"]: t.get("name") or "" for t in types}
    # 批量取 base_configs 聚合（parts_count/total_price/bom_template_id）
    bc_repo = BaseConfigRepository()
    bc_map = {bc["id"]: bc for bc in bc_repo.list()}
    out: list[dict] = []
    for m in models:
        bc_id = m.get("base_config_id")
        if not bc_id:
            continue  # 无主配置机型（新建未关联/未设主）跳过：选型需要可配置 baseline
        bc = bc_map.get(bc_id, {})
        bc_embed = m.get("base_config") or {}
        sid = m.get("server_type_id")
        out.append({
            # 机型顶层字段
            "server_model_id": m.get("id"),
            "name": m.get("name") or "",
            "use": m.get("use") or "",
            "product_content": m.get("product_content"),
            "server_type_id": sid,
            "server_type_name": type_name_by_id.get(sid, "") if sid is not None else "",
            # base_config 元信息（build_plan/下游按 baseline 字段消费，id = base_config_id）
            "id": bc_id,
            "series": bc_embed.get("series") or bc.get("series"),
            "form": bc_embed.get("form") or bc.get("form"),
            "bays": bc_embed.get("bays") if bc_embed.get("bays") is not None else bc.get("bays"),
            "model": bc.get("model") or "",
            "bom_template_id": bc.get("bom_template_id"),
            "parts_count": int(bc.get("parts_count") or 0),
            "total_price": float(bc.get("total_price") or 0),
        })
    results = out[:limit]
    _annotate_recommend(results, recommend_strategy_id)
    return results


def _annotate_recommend(baselines: list[dict], strategy_id: Optional[int] = None) -> None:
    """S1: 读 selection.model_recommend 策略，按 scope.series 给 baseline 附加
    recommend_level（recommend/avoid/neutral）+ selling_points（包装点）。仅标注，不改检索。
    series 维度与 KP 配件适用系列、base_config.series 同源（system_config.server_series）。
    strategy_id：可选，只用指定策略；None=读全部 active。"""
    try:
        from app.repository.strategy_repo import StrategyRepository
        repo = StrategyRepository()
        rules = [r for r in repo.list(domain='selection', status='active') if r.get('type') == 'model_recommend']
        repo.close()
    except Exception:
        return
    if strategy_id:
        rules = [r for r in rules if r.get('id') == strategy_id]
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


_SPEC_UNIT_PATTERNS = {
    "gb": r"g(?:b)?", "tb": r"t(?:b)?", "mb": r"m(?:b)?",
    "pcs": r"(?:pcs?|颗|个)", "w": r"w(?:att)?", "rpm": r"rpm",
    "cores": r"(?:cores?|核)", "mhz": r"m(?:hz)?", "ghz": r"g(?:hz)?",
}


def _unit_regex(unit: str) -> Optional[str]:
    """规格单位 → 正则（GB→g/b 可选；未知单位原样转义）。None 表示无法构造。"""
    if not unit:
        return None
    key = unit.strip().lower()
    return _SPEC_UNIT_PATTERNS.get(key) or re.escape(unit)


def extract_spec_values(text: str, spec_rules: list[dict]) -> list[dict]:
    """从 requirement_text 提取每条 spec_rule 的实际数值（动态匹配用户需求）。
    按 rule.unit 构造正则找"数字+单位"，命中取第一个值（source=extracted）；未命中用 rule.value 默认（source=default）。
    返回 [{category, spec_key, op, value, unit, source}]。
    """
    text = text or ""
    out: list[dict] = []
    for rule in spec_rules or []:
        unit = rule.get("unit") or ""
        unit_re = _unit_regex(unit)
        extracted = None
        if unit_re:
            m = re.search(rf"(\d+(?:\.\d+)?)\s*{unit_re}(?![a-z])", text, re.IGNORECASE)
            if m:
                try:
                    extracted = float(m.group(1))
                except ValueError:
                    extracted = None
        out.append({
            "category": rule.get("category") or "",
            "spec_key": rule.get("spec_key") or "",
            "op": rule.get("op") or ">=",
            "value": extracted if extracted is not None else rule.get("value"),
            "unit": unit,
            "source": "extracted" if extracted is not None else "default",
        })
    return out


def _memory_kp_row(rep: dict, qty: int, extra: str) -> dict:
    """构造 Memory KP 行（容量反推专用），合并 matched_spec 标签。"""
    spec = rep.get("matched_spec") or ""
    if extra:
        spec = f"{spec} · {extra}" if spec else extra
    return {
        "pn": rep.get("model") or "",
        "name": rep.get("model") or "",
        "category": "Memory",
        "unit_price": rep.get("price"),
        "currency": rep.get("currency") or "RMB",
        "matched_spec": spec,
        "qty": qty,
    }


def _pick_memory_part(parts: list[dict], mem_signal: dict, pick_rep) -> Optional[dict]:
    """Memory 容量反推：从已按 Type/Speed 过滤的候选件里选单条容量 + 算 qty。
    选使条数最接近 8（双路 8 内存通道）的容量；qty=ceil(total/cap)。
    返回标准 KP 行（含 qty / matched_spec），或 None 交回主流程兜底。"""
    if not parts:
        return None
    total = mem_signal.get("total_gb")
    cap_re = re.compile(r"(\d+)\s*GB?\b", re.IGNORECASE)

    def cap_of(p):
        m = cap_re.search(p.get("model") or "")
        return int(m.group(1)) if m else None

    if not total:  # 无总容量：代表件 qty=1
        rep = pick_rep(parts)
        return _memory_kp_row(rep, 1, "") if rep else None
    caps = sorted({c for c in (cap_of(p) for p in parts) if c and c <= total}, reverse=True)
    if not caps:
        rep = pick_rep(parts)
        return _memory_kp_row(rep, 1, "") if rep else None
    best_cap, best_qty = None, None
    for c in caps:
        q = -(-total // c)  # ceil(total/c)
        if q < 1 or q > 32:
            continue
        if best_cap is None or abs(q - 8) < abs(best_qty - 8):
            best_cap, best_qty = c, q
    if best_cap is None:
        best_cap, best_qty = caps[0], max(1, -(-total // caps[0]))
    candidates = [p for p in parts if cap_of(p) == best_cap] or parts
    rep = pick_rep(candidates)
    if not rep:
        return None
    return _memory_kp_row(rep, best_qty, f"{total}GB→{best_qty}×{best_cap}G")


def pick_kp_parts(categories: list[str], keywords: list[str],
                  category_aliases: Optional[dict] = None,
                  representative_pick: str = "min_price",
                  spec_rules: Optional[list[dict]] = None,
                  fallback_strategy: str = "fallback_representative",
                  requirement_text: Optional[str] = None,
                  qty_map: Optional[dict] = None,
                  qty_per_token: Optional[dict] = None,
                  spec_search_terms: Optional[set] = None,
                  model_token_regex: Optional[str] = None,
                  mem_signal: Optional[dict] = None,
                  cpu_signal: Optional[dict] = None,
                  multi_spec_filters: Optional[dict] = None) -> list[dict]:
    """对每个需求品类从 KP 库挑 1 个代表件。三级匹配：
       1) 型号 token 精确命中  2) 规格范围匹配（spec_rules）  3) 品类代表件。

    category_aliases：自定义别名表（来自 reasoning_flow 配置）；None=用模块 CATEGORY_KP_ALIASES。
    representative_pick：min_price/max_price/first，默认 min_price（=原行为）。
    spec_rules：[{category, spec_key, op, value, unit}, ...]；按 db_cat（再退 need_cat）匹配规则。
    fallback_strategy：spec 未命中时——fallback_representative(回退代表件,默认)/
                       mark_unmatched(标 unmatched 让前端提示需手填)/raise(抛错中断 pipeline)。

    Returns: [{pn, name, category, unit_price, currency, matched_spec?, unmatched?}]
    KP spec 稀疏（[kp-spec-coverage-sparse]），某品类无命中则跳过/标注，不阻塞（除非 raise）。
    """
    # 型号 token 正则（model_token_regex 可配，None→模块常量 MODEL_TOKEN_RE 兜底；和 extract 同源）
    _mt_re = MODEL_TOKEN_RE
    if model_token_regex:
        try:
            _mt_re = re.compile(model_token_regex)
        except Exception:
            pass  # 配置错误，用模块常量

    # 动态匹配：从需求文本提取规格实际值（用户写了用用户的，没写用规则默认值）
    if requirement_text and spec_rules:
        effective_rules = extract_spec_values(requirement_text, spec_rules)
    else:
        effective_rules = spec_rules or []

    def _rules_for(cat_target: str) -> list[dict]:
        """该品类命中的 spec 规则（rule.category 不区分大小写匹配 cat_target）。"""
        if not cat_target:
            return []
        tgt = cat_target.lower()
        return [r for r in effective_rules if (r.get("category") or "").strip().lower() == tgt]

    def _pick_rep(parts: list[dict]):
        if not parts:
            return None
        with_price = [p for p in parts if p.get("price")]
        if representative_pick == "max_price" and with_price:
            return max(with_price, key=lambda p: p["price"])
        if representative_pick == "first":
            return parts[0]
        return min(with_price, key=lambda p: p["price"]) if with_price else parts[0]

    # CPU 双路（全套/双路/满配 → 2 颗）：写入 qty_map 供末尾注入
    if cpu_signal and cpu_signal.get("duality"):
        qty_map = {**(qty_map or {}), "CPU": max(2, (qty_map or {}).get("CPU", 1))}

    out: list[dict] = []
    kp_repo = KPRepository()
    try:
        db_cats = [c.get("category") for c in kp_repo.get_categories() if c.get("category")]
        matched_categories: set[str] = set()

        # 1. 型号 token 精确命中（用户写明具体型号时优先用）；未命中标 unmatched 提示替换
        for kw in keywords or []:
            if not kw or not _mt_re.match(kw):
                continue
            try:
                rows = kp_repo.get_latest_prices(search=kw)
            except Exception:
                rows = []
            if rows:
                r = rows[0]
                _pn = r.get("model") or ""
                # 跳过已命中的同型号（避免 7.68/7.68T 等子串 token 重复命中同件）
                if any(o.get("pn") == _pn and not o.get("unmatched") for o in out):
                    continue
                cat = r.get("category") or ""
                # multi_spec 品类（如网卡多速率）交给 stage2 按 spec_filter 各产出一件，stage1 不抢先
                if cat and multi_spec_filters and cat in multi_spec_filters:
                    continue
                out.append({
                    "pn": r.get("model") or "",
                    "name": r.get("model") or "",
                    "category": cat or "Key Parts",
                    "unit_price": r.get("price"),
                    "currency": r.get("currency") or "RMB",
                    "matched_token": kw,
                })
                if cat:
                    matched_categories.add(cat)
            else:
                # spec_aliases 搜索词库无 → 静默（非用户指定，不提示 unmatched）
                if kw.lower() in (spec_search_terms or set()):
                    continue
                # 用户指定型号但库无 → unmatched（仅像真型号的长 token，避免短词噪音）
                if len(kw) >= 4:
                    out.append({
                        "pn": "", "name": "", "category": "型号未命中",
                        "unit_price": 0, "currency": "RMB",
                        "unmatched": True,
                        "unmatched_reason": f"用户指定 {kw}，KP 库无此型号，需手填或替换代表件",
                        "requested_token": kw,
                    })

        # 2. 按需求品类：先试规格匹配，未命中按 fallback_strategy / 代表件兜底
        for need_cat in categories or []:
            db_cat = _match_kp_category(need_cat, db_cats, aliases_map=category_aliases)
            if not db_cat:
                continue
            _is_multi = bool(multi_spec_filters and db_cat in multi_spec_filters)
            if db_cat in matched_categories and not _is_multi:
                continue
            # Memory 容量反推（有 mem_signal 时优先：按代际/速率过滤 + 总量反推条数）
            if mem_signal and db_cat.lower() == "memory":
                mfilters = []
                if mem_signal.get("type"):
                    mfilters.append({"spec_key": "Type", "op": "=", "value": mem_signal["type"]})
                if mem_signal.get("speed"):
                    mfilters.append({"spec_key": "Speed", "op": ">=", "value": mem_signal["speed"]})
                if mfilters:
                    try:
                        mem_parts = kp_repo.get_by_category_with_spec_filter(db_cat, mfilters)
                    except Exception:
                        mem_parts = []
                    if mem_parts:
                        mem_row = _pick_memory_part(mem_parts, mem_signal, _pick_rep)
                        if mem_row:
                            out.append(mem_row)
                            matched_categories.add(db_cat)
                            continue
            # 同品类多规格（如网卡千兆+万兆）：按每个 spec_filter 各产出一件，不被品类级 matched 跳过
            if _is_multi:
                _produced = 0
                for sf in multi_spec_filters[db_cat]:
                    try:
                        sparts = kp_repo.get_by_category_with_spec_filter(db_cat, [sf])
                    except Exception:
                        sparts = []
                    if sparts:
                        srep = _pick_rep(sparts)
                        if srep:
                            out.append({
                                "pn": srep.get("model") or "",
                                "name": srep.get("model") or "",
                                "category": db_cat,
                                "unit_price": srep.get("price"),
                                "currency": srep.get("currency") or "RMB",
                                "matched_spec": srep.get("matched_spec") or "",
                            })
                            _produced += 1
                if _produced:
                    matched_categories.add(db_cat)
                    continue
                # 全 sf 未命中（spec 稀疏）→ 落回下方通用 spec_rules / 代表件兜底
            rules = _rules_for(db_cat) or _rules_for(need_cat)
            spec_hit = None
            if rules:
                try:
                    spec_parts = kp_repo.get_by_category_with_spec_filter(db_cat, rules)
                except Exception:
                    spec_parts = []
                if spec_parts:
                    spec_hit = _pick_rep(spec_parts)
                    if spec_hit:
                        out.append({
                            "pn": spec_hit.get("model") or "",
                            "name": spec_hit.get("model") or "",
                            "category": db_cat,
                            "unit_price": spec_hit.get("price"),
                            "currency": spec_hit.get("currency") or "RMB",
                            "matched_spec": spec_hit.get("matched_spec") or "",
                        })
                        matched_categories.add(db_cat)
                        continue
            # spec 未命中（有规则无结果）→ fallback_strategy
            if rules and not spec_hit:
                r0 = rules[0]
                reason = f"规格未命中：{r0.get('spec_key','')} {r0.get('op','>=')} {r0.get('value','')}{r0.get('unit','')}"
                if fallback_strategy == "mark_unmatched":
                    out.append({
                        "pn": "",
                        "name": "",
                        "category": db_cat,
                        "unit_price": 0,
                        "currency": "RMB",
                        "unmatched": True,
                        "unmatched_reason": reason,
                    })
                    matched_categories.add(db_cat)
                    continue
                if fallback_strategy == "raise":
                    raise ValueError(f"KP 规格匹配未命中：{db_cat} {reason}")
                # fallback_representative → 落到下面的品类代表件兜底
            # 3. 品类代表件兜底（无规则，或 fallback_representative）
            try:
                parts = kp_repo.get_by_category(db_cat)
            except Exception:
                parts = []
            if not parts:
                continue
            rep = _pick_rep(parts)
            if not rep:
                continue
            out.append({
                "pn": rep.get("model") or "",
                "name": rep.get("model") or "",
                "category": db_cat,
                "unit_price": rep.get("price"),
                "currency": rep.get("currency") or "RMB",
            })
            matched_categories.add(db_cat)
    finally:
        kp_repo.close()
    # 注入数量：型号 token 命中件用 qty_per_token（精确到件），代表件用 qty_map（品类级），默认 1
    # 已显式设 qty 的（如 Memory 容量反推）保留，不被 qty_map 覆盖。
    for kp in out:
        if kp.get("qty"):
            continue
        _tok = (kp.get("matched_token") or "").lower()
        if _tok and (qty_per_token or {}).get(_tok):
            kp["qty"] = qty_per_token[_tok]
        else:
            kp["qty"] = (qty_map or {}).get(kp.get("category") or "", 1)
    return out


def build_plan(baseline: dict, kp_parts: list[dict]) -> dict:
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

    l6_rows = [{
        "category": "L6",
        "catalogue": p.get("name") or p.get("pn") or "",
        "description": (p.get("pn") or "") + (f" · {_specs_str(p.get('specs'))}" if _specs_str(p.get('specs')) else ""),
        "qty": p.get("quantity") or 1,
    } for p in parts]

    kp_rows = [{
        "category": "Key Parts",
        "catalogue": kp.get("pn") or "",
        "description": (kp.get("name") or "") + (f" · {kp['matched_spec']}" if kp.get("matched_spec") else ""),
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

    return {
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
        "recommend_level": baseline.get("recommend_level") or "",
        "selling_points": baseline.get("selling_points") or "",
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


def compose_plans(keywords: list[str], categories: list[str],
                  series: Optional[str] = None, form: Optional[str] = None,
                  usage: Optional[str] = None) -> dict:
    """整机方案组合入口：选机型 + 配 KP → 组方案。供 pipeline fallback 和 REST 共用。

    从机型层选（usage→server_type 匹配，不硬塞）；KP 品类 = 机型类型套餐 ∪ 需求品类。
    Returns: {plans: [plan...], counts: {baseline, kp}}
    """
    baselines = select_models(usage, series, form)
    if not baselines:
        logger.info("compose_plans: 无机型命中 (usage=%s series=%s form=%s)", usage, series, form)
        return {"plans": [], "counts": {"baseline": 0, "kp": 0}}

    type_name = (baselines[0] or {}).get("server_type_name") or ""
    effective_cats = list(dict.fromkeys(
        (kp_categories_for_type(type_name) or []) + (categories or [])
    ))
    kp_parts = pick_kp_parts(effective_cats, keywords)
    plans = [build_plan(bl, kp_parts) for bl in baselines]
    return {"plans": plans, "counts": {"baseline": len(baselines), "kp": len(kp_parts)}}


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
