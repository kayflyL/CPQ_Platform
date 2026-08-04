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
from app.repository.kp_repo import KPRepository
from app.repository.base_config_repo import BaseConfigRepository
from app.repository.server_catalog_repo import ServerCatalogRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidate-search", tags=["candidate-search"])

PER_KEYWORD_LIMIT = 30  # 每个关键词每个数据源最多取多少条，避免爆炸
MAX_PER_SOURCE = 100    # 单数据源去重后上限
MAX_PLANS = 6           # 整机方案组合最多产出几张（R20：多机型都推荐让用户选，含 ESA/ZSA 各变体）
MODEL_TOKEN_RE = re.compile(r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$")  # 型号 token（必含数字）：字母开头混合/单字母+3位数字(H100/A100/B200)/纯数字≥4/数字开头混合(960G/7.68T/9560-8i)


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
    # GPU/HDD/SSD 仅当需求明确要才配（requested_cats 非 None 且含对应品类；None=老调用方不过滤）
    # HDD/SSD 同 GPU 原则（R4 修）："12/24 bays HDDSupport of NVMe" 是机箱能力不是硬盘配置，
    # 套餐默认含 HDD/SSD 但需求没提硬盘时不硬塞（避免凭空配一块 480G）。
    if requested_cats is not None:
        if "GPU" in cats and "GPU" not in requested_cats:
            cats = [c for c in cats if c != "GPU"]
        if "HDD/SSD" in cats and "HDD/SSD" not in requested_cats:
            cats = [c for c in cats if c != "HDD/SSD"]
    return cats


def build_variant_signals(ext: dict, requirement_text: str = "") -> dict:
    """从 extract 结果 + 需求文本构建机型变体选择信号（R7）。

    - gpu_qty：qty_map.GPU（"8个GPU卡" → 8）
    - has_raid：需求含 Raid card 品类或 raid 字样
    - storage_kinds：文本含 SATA/SAS/NVMe 盘类型词（含盘位能力描述如"前置8*SATA"）
    - form：需求形态（尺寸推断出的 4U 等）
    """
    ext = ext or {}
    qty_map = ext.get("qty_map") or {}
    cats = ext.get("categories") or []
    low = (requirement_text or "").lower()
    kinds: set = set()
    if "sata" in low:
        kinds.add("SATA")
    if "sas" in low:
        kinds.add("SAS")
    if "nvme" in low or "nvme" in " ".join(str(c) for c in cats).lower():
        kinds.add("NVMe")
    # 直通/直连（R8/I39 修复）：需求显式写"直通机型/直连" → 偏好直连模板（2）。
    # 典型场景：4U 8卡 GPU 直通 + RAID/SATA 盘（技术员用直连模板而非 Switch）。
    direct = bool(re.search(r"直通|直连|direct|pass-?thru", low))
    # Switch 字样（R9/I46 防御）：需求显式写 Switch/交换 → 偏好 Switch 模板（3），
    # 压过"8卡具体配置单默认直连"。
    switch = bool(re.search(r"\bswitch\b|交换", low))
    # 配置单特征（R9/I46）：需求含 ≥2 处 "*N/×N" 购买数量 → 具体配置单（非能力描述）。
    # 8 卡具体配置单默认直连（技术员 Direct connected）；能力描述（如 R7 典型报价单）走 RAID/存储偏好。
    cfg_qty = len(re.findall(r"[*×]\s*\d+", low)) >= 2
    # GPU 数量：qty_map 可能缺 GPU（"显卡:AMD R9700*8" 只在 gpu_groups）→ 用 gpu_groups 兜底
    gpu_qty = int(qty_map.get("GPU") or 0)
    for _g in ext.get("gpu_groups") or []:
        gpu_qty = max(gpu_qty, int(_g.get("qty") or 0))
    return {
        "gpu_qty": gpu_qty,
        "has_raid": bool("Raid card" in cats or "raid" in low or "阵列" in low),
        "storage_kinds": kinds,
        "form": ext.get("form"),
        "series": ext.get("series"),
        "has_cpu": "CPU" in cats,
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
                  limit: int = MAX_PLANS,
                  recommend_strategy_id: Optional[int] = None,
                  no_signal_strategy: Optional[str] = "return_empty",
                  variant_signals: Optional[dict] = None) -> list[dict]:
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
        sid = m.get("server_type_id")
        # 机型多基准配置变体（R7）：一个机型挂多个 base_config（model_id 反向关联，各绑不同
        # BOM 模板），按需求信号排序全部给出；单变体机型行为不变（只有主配置）。
        # 按机型分组而非全局排序：跨机型竞争会让 ZSA(4U AI) 混入存储需求并靠 storage+50 反超（R13 回归）
        mid = m.get("id")
        variants = [bc for bc in bc_map.values() if bc.get("model_id") == mid] or [bc_map.get(bc_id, {})]
        variants = [v for v in variants if v]
        variants.sort(key=lambda v: (-_rank_base_config_variant(v, variant_signals, bc_id), v.get("id") or 0))
        for bc in variants:
            if len(out) >= limit:
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
    "cores": r"(?:cores?|核|c)", "核": r"(?:cores?|核|c)",  # 规则 unit=核 也能匹配 "32 core"/"48C"（R4/R12）
    "mhz": r"m(?:hz)?", "ghz": r"g(?:hz)?",
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
        # CPU 裸核数："AMD EPYC 9254 24 2.9 GHz" —— 型号后裸整数 + 频率上下文 = 核数
        # （AMD 型号后缀≠核数，客户常补写 "9254 24"；只在无 "24核/32 core" 单位写法时兜底，2026-08-03 训练）
        if extracted is None and str(rule.get("category") or "").upper() == "CPU" and rule.get("spec_key") == "Cores":
            m = re.search(r"\b[A-Za-z]*\d{3,4}\s+(\d{1,3})\s+\d+(?:\.\d+)?\s*GHz", text, re.IGNORECASE)
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


# ── 盘件规格属性替代（2026-08-03）────────────────────────────────────────
# 需求容量在库里没有同名件时（如 1.6T 库无、库有 1.92T），不再直接 unmatched，
# 而是按「接口 Type + 容量 Capacity 数值」选替代件：同容量等级 → 容量≥需求的最小件
# → 容量≤需求且不低于 80% 的最大件 → 仍无才 unmatched（诚实提示）。替代件在
# matched_spec 标注「容量 X（替代 Y）」，BOM 透明可追溯。

def _cap_to_gb(text) -> Optional[int]:
    """容量串 → GB 整数（单位换算：1T=1024G）。'960G'/'960 GB'→960；'1.92T'/'1.92 TB'→1966。"""
    if text is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*([GT])?(?:B)?", str(text), re.I)
    if not m:
        return None
    v = float(m.group(1))
    unit = (m.group(2) or "G").upper()  # 无单位按 GB（库规格规范带单位，兜底约定）
    return int(v * 1024) if unit == "T" else int(v)


def _part_capacity_gb(part: dict) -> Optional[int]:
    """件容量（GB）：优先规格 Capacity，其次从型号名解析（部分盘件没录规格）。"""
    v = (part.get("specs") or {}).get("Capacity")
    g = _cap_to_gb(str(v)) if v is not None else None
    if g:
        return g
    return _cap_to_gb(part.get("model") or "")


def _gb_label(gb: int) -> str:
    """GB → 展示标签：>=1024 → '1.92T'（去尾 0），否则 '960G'。"""
    if gb >= 1024:
        s = f"{gb / 1024:.2f}".rstrip("0").rstrip(".")
        return f"{s}T"
    return f"{gb}G"


def _part_type_matches(part: dict, kind: Optional[str]) -> bool:
    """接口是否匹配：有 Type 规格以规格为准；无规格回落到型号名含接口词。"""
    if not kind:
        return True
    t = (part.get("specs") or {}).get("Type")
    if t is not None:
        return str(t).strip().lower() == str(kind).strip().lower()
    blob = ((part.get("model") or "") + " " + (part.get("name") or "")).lower()
    return str(kind).lower() in blob


def _drive_spec_substitute(kp_repo, db_cat: str, term: str, kind: Optional[str]) -> list:
    """规格属性替代：按【接口 + 容量数值】选 1 件最合适替代（2026-08-03）。

    优先级：同容量等级（±10% 容差）→ 容量≥需求的最小件（够用）→ 容量≤需求且
    不低于 80% 的最大件（最接近）→ 空（交回 unmatched，诚实提示）。
    """
    need_gb = _cap_to_gb(term)
    if need_gb is None:
        return []
    try:
        parts = kp_repo.get_by_category_with_specs(db_cat) or []
    except Exception:
        return []
    typed = [p for p in parts if _part_type_matches(p, kind)]
    cands = [(p, c) for p in typed if (c := _part_capacity_gb(p))]
    if not cands:
        return []
    same = [t for t in cands if abs(t[1] - need_gb) <= max(64, need_gb * 0.1)]
    if same:
        return [min(same, key=lambda t: t[1])[0]]
    over = [t for t in cands if t[1] >= need_gb]
    if over:
        return [min(over, key=lambda t: t[1])[0]]
    under = [t for t in cands if t[1] >= need_gb * 0.8]
    if under:
        return [max(under, key=lambda t: t[1])[0]]
    return []


def _pick_drive_groups(drive_groups: list, db_cat: str, kp_repo, _pick_rep, out: list,
                       spec_substitute: bool = True) -> int:
    """按盘组逐件匹配 KP 盘（容量 + 接口 → 每盘组 1 件，同件累计数量）。

    解决"一品类只出一个代表件"：2×7.68T NVMe + 2×960G SATA 应出两件，各带各自数量。
    匹配链：名字精确命中（容量 token，接口必须一致）→ 规格属性替代（Capacity/Type 数值）
    → 仍无 → 标 unmatched 提示手填（不进 BOM）。
    """
    produced = 0
    for g in drive_groups or []:
        term = (g.get("term") or "").strip()
        if not term:
            continue
        kind = g.get("kind")
        media = g.get("media")  # HDD/SSD 介质（R12/I58）：需求 "SATAHDD" → 只匹配 HDD 件，不跨介质替代
        qty = int(g.get("qty") or 1)
        try:
            rows = kp_repo.get_by_category(db_cat, search=term) or []
        except Exception:
            rows = []
        tl = term.lower()
        cands = [r for r in rows if tl in ((r.get("model") or "") + " " + (r.get("name") or "")).lower()]
        if kind:
            cands = [r for r in cands
                     if kind.lower() in ((r.get("model") or "") + " " + (r.get("name") or "")).lower()]
        if media:
            _m_low = media.lower()
            _media_cands = [r for r in cands if _m_low in ((r.get("model") or "") + " " + (r.get("name") or "")).lower()]
            if _media_cands:
                cands = _media_cands
        substituted = False
        if not cands and spec_substitute and not media:
            # 介质明确时不做跨介质替代（8T HDD 不能用 8T SSD 顶替，用途/价格差异大）
            cands = _drive_spec_substitute(kp_repo, db_cat, term, kind)
            substituted = bool(cands)
        if cands:
            rep = _pick_rep(cands)
            pn = rep.get("model") or ""
            existing = next((o for o in out if o.get("pn") == pn and not o.get("unmatched")), None)
            if existing:
                existing["qty"] = int(existing.get("qty") or 1) + qty
            else:
                _ms = f"容量 {term}" + (f" · {kind}" if kind else "")
                if substituted:
                    _cap = _part_capacity_gb(rep)
                    _ms = f"容量 {term}（替代 {_gb_label(_cap) if _cap else rep.get('model') or ''} · {kind or '同接口'}）"
                out.append({
                    "pn": pn, "name": rep.get("model") or "",
                    "category": db_cat,
                    "unit_price": rep.get("price"),
                    "currency": rep.get("currency") or "RMB",
                    "matched_spec": _ms,
                    "qty": qty,
                })
            produced += 1
        else:
            out.append({
                "pn": "", "name": "", "category": db_cat,
                "unit_price": 0, "currency": "RMB",
                "unmatched": True,
                "unmatched_reason": f"容量 {term} 的{kind + ' ' if kind else ''}盘在 KP 库未命中（含规格属性替代），需手填",
                "qty": qty,
            })
            produced += 1
    return produced


# 国产 CPU 家族（按厂商分家，防跨厂商替代）：Polaris 只配兆芯，海光/飞腾/鲲鹏/龙芯不是 Polaris。
# - _XINCHUANG_RE（需求信号）：需求出现任一国产词 → 走国产过滤（防回退 AMD/Intel）；
# - _ZHAOXIN_CPU_RE 等（件侧家族）：按厂商匹配 CPU 件。需求显式点名厂商 → 只留该厂商家族
#   （海光需求绝不落兆芯 KH/KX）；只写"信创/国产"或平台= Polaris → 留兆芯家族（Polaris=兆芯）。
_XINCHUANG_RE = re.compile(r"信创|国产|鲲鹏|飞腾|海光|兆芯|龙芯|麒麟|开先|开胜|hygon|phytium|kunpeng|loongson|zhaoxin", re.I)
_ZHAOXIN_CPU_RE = re.compile(r"(?:^|[^A-Za-z0-9])(?:KH|KX|ZX)|兆芯|zhaoxin|开胜|开先", re.I)
_HYGON_CPU_RE = re.compile(r"海光|hygon|\bC86", re.I)
_PHYTIUM_CPU_RE = re.compile(r"飞腾|phytium|腾锐|腾云", re.I)
_KUNPENG_CPU_RE = re.compile(r"鲲鹏|kunpeng|\b920\b", re.I)
_LOONGSON_CPU_RE = re.compile(r"龙芯|loongson", re.I)
_VENDOR_CPU_RULES = [
    ("zhaoxin", _ZHAOXIN_CPU_RE), ("hygon", _HYGON_CPU_RE),
    ("phytium", _PHYTIUM_CPU_RE), ("kunpeng", _KUNPENG_CPU_RE),
    ("loongson", _LOONGSON_CPU_RE),
]


def _filter_cpu_parts_for_platform(parts: list, requirement_text: str = "",
                                   platform_series: Optional[str] = None) -> Optional[list]:
    """CPU 候选件按平台过滤（R20）：需求显式点名厂商 → 只留该厂商家族；需求只写信创/国产
    或已选机型为 Polaris（=兆芯）→ 只留兆芯家族（KH/KX/ZX）；Orion → AMD/EPYC；Intel → Intel。
    无匹配 → None（调用方标 unmatched，防跨平台/跨厂商错误）。"""
    if not parts:
        return parts
    up = (platform_series or "").upper()
    req = requirement_text or ""
    for _name, _rx in _VENDOR_CPU_RULES:
        if _rx.search(req):
            _v = [p for p in parts if _rx.search(str(p.get("model") or "") + " " + str(p.get("name") or ""))]
            return _v or None
    if _XINCHUANG_RE.search(req) or up == "POLARIS":
        _xc = [p for p in parts if _ZHAOXIN_CPU_RE.search(
            str(p.get("model") or "") + " " + str(p.get("name") or ""))]
        return _xc or None
    if up == "ORION":
        _am = [p for p in parts if re.search(r"AMD|EPYC", str(p.get("model") or "") + " " + str(p.get("name") or ""), re.I)]
        return _am or None
    if up == "INTEL":
        _int = [p for p in parts if re.search(r"INTEL|XEON", str(p.get("model") or "") + " " + str(p.get("name") or ""), re.I)]
        return _int or None
    return parts


def _default_mem_type_for_cpu(rows: list) -> Optional[str]:
    """CPU 代际 → 内存代际默认（R16）：需求未写 DDR 代际时，按已选 CPU 件型号推断，
    避免给 KH50000（DDR5 平台）配到 DDR4 件（正确性问题）。
    KH50000/KH-50000/KH5000、EPYC 9004/9005、Xeon 6 → DDR5；KH40000/KX/老代 → DDR4。
    CPU 未命中（unmatched 无件号）→ None（交回原逻辑）。"""
    cpu_pn = ""
    for r in rows or []:
        if str(r.get("category") or "").strip().lower() == "cpu" and r.get("pn"):
            cpu_pn = str(r["pn"])
            break
    if not cpu_pn:
        return None
    up = cpu_pn.upper()
    if re.search(r"KH50000|KH-50000|KH5000|EPYC 90(0[45])|EPYC 9J|XEON 6", up):
        return "DDR5"
    if re.search(r"KH40000|KH4000|KX|EPYC 70|XEON [1234]", up):
        return "DDR4"
    return None


def _cpu_cores_need(effective_rules: list) -> Optional[int]:
    """需求实际提取的 CPU 核数（source=extracted；默认 16 不用，避免误过滤）。
    "KH5000 48C" → 48（R12/I59，spec unit 支持 c 简写）。"""
    for r in effective_rules or []:
        if (str(r.get("category") or "").strip().lower() == "cpu"
                and r.get("spec_key") == "Cores" and r.get("source") == "extracted"):
            try:
                return int(r.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def _cpu_model_cores(model: str) -> Optional[int]:
    """CPU 件型号的核数（"KH50000 48C" → 48）；无 "N C" 后缀 → None（AMD EPYC 9654 等）。"""
    m = re.search(r"(\d+)\s*[Cc]\b", str(model or ""))
    return int(m.group(1)) if m else None


def _gpu_cap_gb(part: dict) -> Optional[int]:
    """GPU 件显存容量（GB）：优先规格 Capacity（"72 GB"→72），否则件名容量（"RTX PRO 5000 48G"→48）。"""
    v = (part.get("specs") or {}).get("Capacity")
    if v is not None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*GB?", str(v), re.I)
        if m:
            return int(float(m.group(1)))
    m = re.search(r"(\d{1,3})\s*GB?\b", str(part.get("model") or ""), re.I)
    return int(m.group(1)) if m else None


def _pick_gpu_groups(gpu_groups: list, db_cat: str, kp_repo, _pick_rep, out: list) -> int:
    """按 GPU 组逐件匹配（型号 token → 库件），同件累计数量。
    "8×RTX 5090 + 4×AMD R9700" → 两件各带数量；未命中标 unmatched 提示手填。"""
    produced = 0
    for g in gpu_groups or []:
        toks = [t for t in (g.get("tokens") or []) if t]
        qty = int(g.get("qty") or 1)
        if not toks:
            continue
        hit = None
        _cap = g.get("cap")  # 显存容量（R10/I50）：需求 "RTX PRO 5000 72G" → 优先选 72G 件，不落 48G
        for t in toks:
            try:
                rows = kp_repo.get_latest_prices(search=t)
            except Exception:
                rows = []
            # 只认「GPU 品类 + 件名含型号 token」的命中——get_latest_prices 会搜价格备注，
            # "4500" 曾命中备注含 4500 的天数智芯 智铠100（2026-08-03 训练：RTX PRO 4500 被配成智铠100）
            _tl = t.lower()
            cands = [r for r in rows
                     if ("gpu" in (r.get("category") or "").lower() or "显卡" in (r.get("category") or ""))
                     and _tl in ((r.get("model") or "").lower())]
            if _cap:
                cap_cands = [r for r in cands if _gpu_cap_gb(r) == _cap]
                if cap_cands:
                    cands = cap_cands
            if cands:
                hit = _pick_rep(cands)
                break
        if hit:
            pn = hit.get("model") or ""
            existing = next((o for o in out if o.get("pn") == pn and not o.get("unmatched")), None)
            if existing:
                existing["qty"] = int(existing.get("qty") or 1) + qty
            else:
                out.append({
                    "pn": pn, "name": hit.get("model") or "",
                    "category": db_cat,
                    "unit_price": hit.get("price"),
                    "currency": hit.get("currency") or "RMB",
                    "matched_spec": f"型号 {toks[0]}",
                    "qty": qty,
                })
            produced += 1
        else:
            # I30：需求型号库里无 → 不补料，按「显存容量」找同性能替代件（透明标注，仍可手改）
            sub = None
            if _cap:
                try:
                    _gpu_all = kp_repo.get_by_category(db_cat) or []
                except Exception:
                    _gpu_all = []
                _cap_m = [r for r in _gpu_all if _gpu_cap_gb(r) == _cap]
                if _cap_m:
                    sub = _pick_rep(_cap_m)
            if sub:
                out.append({
                    "pn": sub.get("model") or "", "name": sub.get("model") or "",
                    "category": db_cat,
                    "unit_price": sub.get("price"), "currency": sub.get("currency") or "RMB",
                    "matched_spec": f"型号 {toks[0]}（替代 {sub.get('model')}）",
                    "qty": qty,
                })
            else:
                out.append({
                    "pn": "", "name": "", "category": db_cat,
                    "unit_price": 0, "currency": "RMB",
                    "unmatched": True,
                    "unmatched_reason": f"GPU 型号 {toks[0]} 在 KP 库未命中，需手填",
                    "qty": qty,
                })
            produced += 1
    return produced



def _pick_raid_groups(raid_groups: list, db_cat: str, kp_repo, _pick_rep, out: list) -> int:
    """按 RAID 组逐件匹配（显式型号 → 库件），同件累计数量。

    "RAID卡：LSI 9560 16i 8G缓存 *1 / LSI 9364 8i 2G缓存 *1" → 两件各带数量（R28 ESA24V3-P）。
    型号归一（'9560-16i'）后按件名子串匹配；命中缓存标注；未命中标 unmatched 提示手填。
    """
    produced = 0
    for g in raid_groups or []:
        model = (g.get("model") or "").strip().lower()
        qty = int(g.get("qty") or 1)
        if not model:
            continue

        def _norm(s: str) -> str:
            return re.sub(r"[\s\-_]+", "", str(s or "").lower())

        hit = None
        try:
            rows = kp_repo.get_by_category(db_cat, search=model) or []
        except Exception:
            rows = []
        cands = [r for r in rows if _norm(model) in _norm(r.get("model") or "")]
        if cands:
            hit = _pick_rep(cands)
        if hit:
            pn = hit.get("model") or ""
            existing = next((o for o in out if o.get("pn") == pn and not o.get("unmatched")), None)
            _cache_note = f"缓存 {g['cache']}G" if g.get("cache") else ""
            _ms = f"型号 {model}"
            if _cache_note:
                _ms = f"{_ms} · {_cache_note}"
            if existing:
                existing["qty"] = int(existing.get("qty") or 1) + qty
            else:
                out.append({
                    "pn": pn, "name": hit.get("model") or "",
                    "category": db_cat,
                    "unit_price": hit.get("price"),
                    "currency": hit.get("currency") or "RMB",
                    "matched_spec": _ms,
                    "qty": qty,
                })
            produced += 1
        else:
            out.append({
                "pn": "", "name": "", "category": db_cat,
                "unit_price": 0, "currency": "RMB",
                "unmatched": True,
                "unmatched_reason": f"RAID 型号 {model} 在 KP 库未命中，需手填",
                "qty": qty,
            })
            produced += 1
    return produced


def _pick_mem_groups(mem_groups: list, db_cat: str, kp_repo, _pick_rep, out: list,
                     mem_signal: Optional[dict], default_mem_speed: Optional[int] = None) -> int:
    """按内存组逐件匹配（容量 term → 库件，代际/速率偏好），同件累计数量。
    "内存：64G ×8，32G ×8" → 两件各带数量。
    I47：需求未指定速率 → 用机型标准速率（default_mem_speed）精确过滤，避免低价选到 5600。"""
    produced = 0
    ms = mem_signal or {}
    _speed = ms.get("speed") or default_mem_speed
    for g in mem_groups or []:
        term = (g.get("term") or "").strip()
        qty = int(g.get("qty") or 1)
        if not term:
            continue
        try:
            rows = kp_repo.get_by_category(db_cat, search=term) or []
        except Exception:
            rows = []
        tl = term.lower()
        cands = [r for r in rows if tl in ((r.get("model") or "") + " " + (r.get("name") or "")).lower()] or rows
        if ms.get("type"):
            tc = [r for r in cands if ms["type"].lower() in (r.get("model") or "").lower()]
            if tc:
                cands = tc
        if _speed:
            sc = [r for r in cands if str(_speed) in (r.get("model") or "")]
            if sc:
                cands = sc
        if cands:
            rep = _pick_rep(cands)
            pn = rep.get("model") or ""
            existing = next((o for o in out if o.get("pn") == pn and not o.get("unmatched")), None)
            if existing:
                existing["qty"] = int(existing.get("qty") or 1) + qty
            else:
                out.append({
                    "pn": pn, "name": rep.get("model") or "",
                    "category": db_cat,
                    "unit_price": rep.get("price"),
                    "currency": rep.get("currency") or "RMB",
                    "matched_spec": f"容量 {term}",
                    "qty": qty,
                })
            produced += 1
        else:
            out.append({
                "pn": "", "name": "", "category": db_cat,
                "unit_price": 0, "currency": "RMB",
                "unmatched": True,
                "unmatched_reason": f"容量 {term} 的内存未命中，需手填",
                "qty": qty,
            })
            produced += 1
    return produced


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
                  multi_spec_filters: Optional[dict] = None,
                  drive_groups: Optional[list] = None,
                  raid_groups: Optional[list] = None,
                  gpu_groups: Optional[list] = None,
                  mem_groups: Optional[list] = None,
                  drive_spec_substitute: bool = True,
                  platform_series: Optional[str] = None,
                  default_mem_speed: Optional[int] = None) -> list[dict]:
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
            # R-8: 跳过规格碎片——容量(480G/7.68T)、瓦数(360W)、内存速率(5600B/DDR5-5600B)、
            # 缓存(256MB)、频率(3.1GHz) 等非用户指定型号，放行会各命中一件→过匹配/报 unmatched 噪音。
            # 让它们落 stage-2/3 代表件。保留真型号(9654/P5510/H100/9560-8i)。
            # RAID 卡缓存后缀归一（R8/I44）："9560-8i4G"(4G缓存) → "9560-8i"，"9364-8i8G" → "9364-8i"；
            # 缓存容量不是型号，去掉后落 stage-1 精确命中（不再报 unmatched）。
            _raid_norm = re.match(r"^(.*\di)\d+[GT]?B?$", kw, re.I)
            if _raid_norm:
                kw = _raid_norm.group(1)
            # Mellanox ConnectX 别名（R9/I46）："MCX5" → "CX5"（100G双口MCX5 → 100G CX5 2port）
            kw = re.sub(r"^mcx(\d+)$", r"cx\1", kw, flags=re.I)
            if re.match(
                    r"^\d+(?:\.\d+)?(?:[GTW]B?|MB|MHz|GHz)$"   # 480G/64GB/360W/256MB/3.1GHz
                    r"|^\d+[A-Z]{1,2}$"                            # 5600B
                    r"|^DDR[345]-?\d*[A-Z]*$"                     # DDR5-5600B
                    r"|^\d+[A-Za-z]*series$"                     # 9005series（R4 修）
                    r"|^(?:SATA|SAS|NVME?|U\.?2|SSD|HDD)[A-Za-z]*\d+(?:\.\d+)?[GT]B?$"  # SATASSD480G/U.2NVME7.68T（R5）
                    r"|^\d+\.\d+$"                                # 7.68/1.92/3.0 纯小数碎片（R5 防重复出盘）
                    r"|^\d+[A-Za-z]{2,}$"                            # 8GPU/6400MT/822mm 数字+单词连写（R7）
                    r"|^\d+-\d+(?:度|℃|°C)?$"                          # 5-35 环境温度范围（R17 招标）
                    r"|^\d+[xX]\d+$"                                   # 7x24 服务响应时间（R19，非型号）
                    r"|^Gen[345]$"                                      # NVMe Gen3/4/5 代际（R18，非型号）
                    r"|^Gen[345][xX]\d+$"                              # PCIe Gen4x4 代际×通道（R20，非型号）
                    r"|^\d+[GT]?B?(?:SATA|SAS|NVME?|GB?)[A-Za-z0-9.]*$"  # 6GSATA2.5in 接口速率+尺寸（R20）
                    r"|^\d+\.\d+[A-Za-z]+$"                         # 2.5in/3.5in 盘尺寸（R20，非型号）
                    r"|^PCIe\d*(?:\.\d+)?$"                          # PCIe4/PCIe4.0/PCIe5.0 槽位规格（R7）
                    r"|^RAID\d+$"                                      # RAID1/5/10 级别注释（I38，R2）
                    r"|^GX\d+$"                                        # GX16/GX8 PCIe 槽位标记（I41，R8）
                    r"|^\dU\d+$"                                       # 2U12/2U25 机箱盘位数（R12/I60）
                    r"|^\d+i\d+[GT]?B?$",                             # 8i4G：RAID 缓存后缀碎片（R8/I44，随归一后丢弃）
                    kw, re.I):
                continue
            # GPU 组相关 token 跳过 stage-1（R10/I50）：GPU 由 gpu_groups 精确处理，
            # 防 "RTX PRO 5000" 的裸数字 "5000" 泛命中其他品类件（如 CPU 库的 KH50000 96C）
            _gpu_toks = [str(t).lower() for _g in (gpu_groups or []) for t in (_g.get("tokens") or [])]
            if any(kw.lower() == t or kw.lower() in t for t in _gpu_toks):
                continue
            # RAID 组相关 token 跳过 stage-1（R28 2026-08-04）：raid_groups 存在时阵列卡由组精确处理，
            # 防 "9560"/"16i"/"9364" 等型号碎片、以及完整型号串 "9560-8i" 各自泛命中、
            # 与组匹配打架（ESA24V3-P 训练；回归：BI/LLW "9560-8I" 曾 stage-1 + 组各出一件）。
            _raid_toks: set = set()
            for _g in (raid_groups or []):
                _rm = str(_g.get("model") or "").lower()
                _raid_toks.add(_rm)
                for _rt in re.split(r"[^0-9a-z]+", _rm):
                    if _rt:
                        _raid_toks.add(_rt)
            if _raid_toks and kw.lower() in _raid_toks:
                continue
            # 板载管理口（IPMI/BMC RJ45）不是独立网卡件（R4 修）
            if kw.lower() in ("rj45", "ipmi", "bmc", "mgmt", "management"):
                continue
            # "9004/9005系列" —— 系列号不是具体型号，不报 unmatched 噪音（R7）
            if re.search(re.escape(kw) + r"[^，。\n]{0,6}(?:系列|series)", requirement_text or "", re.I):
                continue
            # 纯数字后跟 风扇/fan（"6组6056风扇"）→ 风扇规格，不当型号（I41，R8）
            if re.match(r"^\d{4,5}$", kw) and re.search(re.escape(kw) + r"[^，。\n]{0,4}(?:风扇|fan)", requirement_text or "", re.I):
                continue
            # 电源瓦数纯数字（"2700瓦"/"电源配1300"/"2700 白金 热插拔"）→ 电源规格，不当型号（R10/I53）
            # 2026-08-04：上下文双向检查——"电源配1300" 的电源词在数字【前】（原只查后 0-6 字符漏检）
            if re.match(r"^\d{3,4}$", kw):
                _psu_ctx_after = re.escape(kw) + r"[^，。\n]{0,6}(?:瓦|白金|热插拔|电源|psu|redundant|platinum)"
                _psu_ctx_before = r"(?:瓦|白金|热插拔|电源|psu|redundant|platinum)[^，。\n]{0,6}" + re.escape(kw)
                if re.search(_psu_ctx_after, requirement_text or "", re.I) or \
                   re.search(_psu_ctx_before, requirement_text or "", re.I):
                    continue
            # 内存速率纯数字（"DDR5 5200"/"5200 MT/s"）→ 内存规格，不当型号（R21）
            if re.match(r"^\d{3,4}$", kw) and re.search(
                    r"DDR[345]?\s*-?\s*" + kw + r"|" + kw + r"\s*(?:MT/?s?|MHz)",
                    requirement_text or "", re.I):
                continue
            # CPU/主板型号连字符归一（R14）："KH-50000" 库中存为 "KH50000" → 去连字符再搜，
            # 消除 spurious unmatched；matched_token 仍用原 kw（qty_per_token 同源）。
            _search_kw = kw
            if re.match(r"^[A-Za-z]{1,4}-?\d{3,6}$", kw, re.I):
                _search_kw = re.sub(r"-", "", kw)
            elif re.match(r"^(?:KH|KX|ZX|P)-?\d+-\d+$", kw, re.I):
                # "KH50000-72"（兆芯，-72 是核数后缀）→ "KH50000"（R21）
                _search_kw = re.split(r"-\d+$", kw, maxsplit=1)[0]
            try:
                rows = kp_repo.get_latest_prices(search=_search_kw)
            except Exception:
                rows = []
            if rows:
                # 精确命中须件名含 token：get_latest_prices 会搜价格备注/描述，
                # "PM893" 曾命中描述含 PM893 的 3.84T SATA SSD（R20）——件名不含 → 非用户指定型号
                rows = [r for r in rows if _search_kw.lower() in (r.get("model") or "").lower()]
            if rows:
                cat = rows[0].get("category") or ""
                # CPU 核数需求（R12/I59）："KH5000 48C" → 优先 Cores 精确件，次选 >= 最小
                # （否则 "kh5000" 泛命中 rows[0]=96C）
                if cat == "CPU":
                    _cores_need = _cpu_cores_need(effective_rules)
                    if _cores_need:
                        _exact = [x for x in rows if _cpu_model_cores(x.get("model")) == _cores_need]
                        if _exact:
                            rows = _exact
                        else:
                            _over = [x for x in rows if (_cpu_model_cores(x.get("model")) or 0) >= _cores_need]
                            if _over:
                                rows = sorted(_over, key=lambda x: (_cpu_model_cores(x.get("model")) or 0))
                r = rows[0]
                _pn = r.get("model") or ""
                # 跳过已命中的同型号（避免 7.68/7.68T 等子串 token 重复命中同件）
                if any(o.get("pn") == _pn and not o.get("unmatched") for o in out):
                    continue
                cat = r.get("category") or ""
                # Memory 由 stage-2 的 mem_signal 容量反推专门处理；stage-1 别用碎片键(ddr5/5600 等)
                # 抢先匹配——会挡住 stage-2(stage 命中即跳同品类)，导致选错容量/速率。
                if mem_signal and cat.lower() in ("memory", "内存"):
                    continue
                # GPU 由 gpu_groups 分组处理（多卡各出一件）；stage-1 不抢先，避免只出一件代表
                if gpu_groups and ("gpu" in cat.lower() or "显卡" in cat):
                    continue
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

        def _alias_group_matched(need_cat: str, matched: set) -> bool:
            """need_cat 是否已被【同品类别名组】命中过——KP 库里 GPU 与 GPU card 是同一需求品类，
            stage-1 在 "GPU card" 命中后，stage-2 按 "GPU" 查会重复加一件（如 5090 + 曦云 8GPU 模组）。"""
            if not need_cat:
                return False
            db_cat = _match_kp_category(need_cat, db_cats, aliases_map=category_aliases)
            if db_cat in matched:
                return True
            aliases = [(a or "").lower() for a in
                       (category_aliases or CATEGORY_KP_ALIASES).get(need_cat, []) if (a or "").strip()]
            ncl = need_cat.lower()
            for c in matched:
                cl = (c or "").lower()
                if cl == ncl or cl in aliases or ncl in cl or any(a and (a in cl or cl in a) for a in aliases):
                    return True
            return False

        # 2. 按需求品类：先试规格匹配，未命中按 fallback_strategy / 代表件兜底
        for need_cat in categories or []:
            db_cat = _match_kp_category(need_cat, db_cats, aliases_map=category_aliases)
            if not db_cat:
                continue
            # CPU：用户指定具体型号但库无（stage-1 unmatched）且无核数约束 → 不做代表件回退（R13/I65）。
            # 防跨平台错误：KX40000（兆芯）库无时不能回退到 AMD EPYC 9124；R6 9254 有核数约束仍走 spec 回退。
            if db_cat == "CPU":
                _cpu_line = re.search(r"(?:cpu|处理器)[:：]?\s*([^\n，,。]+)", requirement_text or "", re.I)
                if _cpu_line and any(o.get("unmatched") for o in out) and not _cpu_cores_need(effective_rules):
                    matched_categories.add(db_cat)
                    continue
            _is_multi = bool(multi_spec_filters and db_cat in multi_spec_filters)
            # 内存代际默认跟 CPU（R16/R17）：mem_groups 与 mem_signal 两条路径共用同源代际，
            # 避免 "4*32GB 内存"（无 DDR 字样）在 mem_groups 路径选到 DDR4
            if db_cat.lower() == "memory" and not (mem_signal or {}).get("type"):
                _cpu_mt = _default_mem_type_for_cpu(out)
                if _cpu_mt:
                    mem_signal = {**(mem_signal or {}), "type": _cpu_mt}
            # ── 规格分组多件匹配（优先于"一品类一件"；GPU/内存/盘按组逐件出，同件累计数量）──
            if not _is_multi:
                if gpu_groups and ("gpu" in db_cat.lower() or "显卡" in db_cat):
                    if _pick_gpu_groups(gpu_groups, db_cat, kp_repo, _pick_rep, out):
                        matched_categories.add(db_cat)
                        continue
                if mem_groups and db_cat.lower() in ("memory", "内存"):
                    if _pick_mem_groups(mem_groups, db_cat, kp_repo, _pick_rep, out, mem_signal,
                                     default_mem_speed=default_mem_speed):
                        matched_categories.add(db_cat)
                        continue
                if drive_groups and any(k in db_cat.lower() for k in ("hdd", "ssd", "硬盘", "存储", "盘")):
                    if _pick_drive_groups(drive_groups, db_cat, kp_repo, _pick_rep, out,
                                          spec_substitute=drive_spec_substitute):
                        matched_categories.add(db_cat)
                        continue
                # RAID 显式型号分组（R28 2026-08-04）：需求逐行给阵列卡型号 → 按组精确匹配
                if raid_groups and ("raid" in db_cat.lower() or "阵列" in db_cat or "hba" in db_cat.lower()):
                    if _pick_raid_groups(raid_groups, db_cat, kp_repo, _pick_rep, out):
                        matched_categories.add(db_cat)
                        continue
            if not _is_multi and (db_cat in matched_categories or _alias_group_matched(need_cat, matched_categories)):
                continue
            # Memory 容量反推（有 mem_signal 时优先：按代际/速率过滤 + 总量反推条数）
            if mem_signal and db_cat.lower() == "memory":
                mfilters = []
                _mem_type = mem_signal.get("type") or _default_mem_type_for_cpu(out)
                if _mem_type:
                    mfilters.append({"spec_key": "Type", "op": "=", "value": _mem_type})
                if mem_signal.get("speed"):
                    mfilters.append({"spec_key": "Speed", "op": ">=", "value": mem_signal["speed"]})
                elif default_mem_speed:
                    # I47：需求未指定速率 → 按机型标准速率精确选（Speed == 4800），
                    # 不再按低价选到 5600（技术员惯例 4800/机型标准）。
                    mfilters.append({"spec_key": "Speed", "op": "=", "value": default_mem_speed})
                try:
                    if mfilters:
                        mem_parts = kp_repo.get_by_category_with_spec_filter(db_cat, mfilters)
                    else:
                        # 无代际/速率信号（"内存：256"）→ 用全部内存件按总量反推（R13/I64）
                        mem_parts = kp_repo.get_by_category(db_cat) or []
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
                    # 行式过滤组（R5 多网卡）：{filters:[{spec_key..}..], qty?, name_contains?}
                    # 兼容旧式单条件 dict {spec_key, op, value}。
                    _conds = (sf or {}).get("filters") if isinstance(sf, dict) else None
                    if not _conds:
                        _conds = [sf]
                    _nq = (sf or {}).get("qty") if isinstance(sf, dict) else None
                    _ncontains = (sf or {}).get("name_contains") if isinstance(sf, dict) else ""
                    try:
                        sparts = kp_repo.get_by_category_with_spec_filter(db_cat, _conds)
                    except Exception:
                        sparts = []
                    if sparts and _ncontains:
                        # name_contains 可多词（具体型号 + 光模块）：优先同时含全部词的件；
                        # 无全中时退回第一个词（型号比"光模块"更具体，排在前）。
                        _terms = _ncontains if isinstance(_ncontains, list) else [_ncontains]
                        _terms = [t for t in _terms if (t or "").strip()]
                        _pref = None
                        if _terms:
                            def _norm_nic_name(s: str) -> str:
                                # 与 extract 侧同一套归一：去连字符/下划线（X710-DA2 → x710da2）
                                return re.sub(r"[-_]", "", ((s or "").replace("\u2011", "-")).lower())

                            def _has_all(p):
                                n = _norm_nic_name(p.get("model") or "")
                                return all(_norm_nic_name(t) in n for t in _terms)
                            _pref = [p for p in sparts if _has_all(p)]
                            if not _pref:
                                _first = _norm_nic_name(_terms[0])
                                _pref = [p for p in sparts if _first in _norm_nic_name(p.get("model") or "")]
                        if _pref:
                            # 同满足条件时优先通用光模块件（不带 10G光模块/单模光模块 等速率前缀的歧义件）
                            _plain = [p for p in _pref
                                      if not re.search(r"\d+\s*g?\s*光模块", p.get("model") or "", re.I)]
                            sparts = _plain or _pref
                    if sparts:
                        srep = _pick_rep(sparts)
                        if srep:
                            _row = {
                                "pn": srep.get("model") or "",
                                "name": srep.get("model") or "",
                                "category": db_cat,
                                "unit_price": srep.get("price"),
                                "currency": srep.get("currency") or "RMB",
                                "matched_spec": srep.get("matched_spec") or "",
                            }
                            if _nq:
                                _row["qty"] = int(_nq)
                            out.append(_row)
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
                # CPU 平台过滤（R17/R20）：需求含信创词 或 已选机型为 Polaris → 只限信创家族；
                # Orion → 只限 AMD；Intel → 只限 Intel。防跨平台错误（"32核" 曾 spec 命中 AMD EPYC）
                if spec_parts and db_cat == "CPU":
                    _cp = _filter_cpu_parts_for_platform(spec_parts, requirement_text or "", platform_series)
                    spec_parts = _cp or []
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
            # 3. 品类代表件兜底（无规则，或 fallback_representative）：
            #    有非容量关键字时先按关键字搜该品类，命中才用——避免 "25G 网卡" 需求选到 400G 最低价代表件。
            #    关键字用【非容量碎片】（容量/速度如 25G/960G 是规格不是型号，见 stage-1 跳过逻辑；
            #    但这里 25G 恰恰是网卡速度关键字，需要保留）→ 直接对品类内件名做子串匹配。
            try:
                parts = kp_repo.get_by_category(db_cat)
            except Exception:
                parts = []
            _kws = [k for k in (keywords or []) if k]
            _kw_hit = False
            if parts and _kws:
                _hit = None
                for k in _kws:
                    kl = k.lower()
                    _hit = next((pt for pt in parts if kl in (pt.get("name") or "").lower()
                                 or kl in (pt.get("model") or "").lower()), None)
                    if _hit:
                        break
                if _hit:
                    _kw_hit = True
                    parts = [_hit]
            # CPU 平台过滤（R17/R20）：需求要求信创平台 或 已选机型为 Polaris/Orion/Intel 时，
            # 代表件兜底只允许对应平台家族件，不得跨平台回退（I65 同族）；库无匹配 → 标 unmatched 诚实提示。
            if db_cat == "CPU":
                _cp = _filter_cpu_parts_for_platform(parts, requirement_text or "", platform_series)
                if _cp is None:
                    out.append({
                        "pn": "", "name": "", "category": db_cat,
                        "unit_price": 0, "currency": "RMB",
                        "unmatched": True,
                        "unmatched_reason": f"CPU 需求匹配 {platform_series or '信创'} 平台：KP 库无对应家族件，需补料或手填",
                    })
                    matched_categories.add(db_cat)
                    continue
                parts = _cp
            # I22：需求未指定 RAID 型号（如只写 "RAID 0,1,10"）→ 按配件库 applicable.series 兼容机型选件。
            # 配件库标了兼容系列的件优先（ES22V3-P/Orion 默认 LSI 9540-8i），未标不排除；
            # 需求给了具体型号（keyword 命中）不适用——显式型号优先。
            if not _kw_hit and db_cat in ("Raid card", "阵列卡") and platform_series:
                _compat = [pt for pt in parts
                           if platform_series in ((pt.get("applicable") or {}).get("series") or [])]
                if _compat:
                    parts = _compat
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


# ── 电源瓦数推断（数据驱动：system_config.psu_inference；以下仅为读失败时的兜底常量）──
_PSU_FALLBACK = {
    "high_tdp_gpus": ["H100", "A100", "H200", "B200", "B100", "L40", "MI300",
                      "RTX PRO", "RTX 6000", "RTX 5090"],
    "tiers": [
        {"min_gpu": 8, "high_tdp": True, "wattage": "2700"},
        {"min_gpu": 1, "high_tdp": False, "wattage": "2000"},
    ],
    "no_gpu_wattage": "1600",
}


def _load_psu_inference() -> dict:
    """读电源推断配置（system_config.psu_inference），缺失/异常回退常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("psu_inference")
        finally:
            repo.close()
        if isinstance(cfg, dict) and cfg:
            return {**_PSU_FALLBACK, **cfg}
    except Exception:
        pass
    return dict(_PSU_FALLBACK)


def _kp_signals(kp_parts: list[dict]) -> tuple:
    """从 KP 结果提信号：GPU 数 + 是否含高功耗 GPU + 盘类型集合(NVMe/SAS/SATA)。"""
    _psu_cfg = _load_psu_inference()
    # 高功耗 GPU 词表去空白归一（R8/I43 修）：词表 "RTX 5090"，件名 "RTX5090" 无空格
    # → 直接子串匹配 miss，8×RTX5090 掉到 2000W。归一后两端都去空白再比。
    _high_tdp_words = [re.sub(r"\s+", "", str(k)).upper() for k in (_psu_cfg.get("high_tdp_gpus") or []) if k]
    gpu_qty = 0
    high_tdp = False
    drive_kinds: set = set()
    has_drive = False
    for kp in kp_parts or []:
        cat = (kp.get("category") or kp.get("part_category") or "")
        cat_u = cat.upper()
        qty = int(kp.get("qty") or 1)
        name_u = (kp.get("name") or "").upper()
        if "GPU" in cat_u or "显卡" in cat:
            gpu_qty += qty
            _name_compact = re.sub(r"\s+", "", name_u)  # I43：件名去空白（RTX5090 ↔ RTX 5090）
            if any(k in _name_compact for k in _high_tdp_words):
                high_tdp = True
        blob = f"{cat} {kp.get('name') or ''} {kp.get('matched_spec') or ''}".upper()
        if (any(k in cat_u for k in ("硬盘", "DRIVE", "SSD", "HDD", "DISK", "盘"))
                or any(k in blob for k in ("NVME", "SATA", "SAS"))):
            has_drive = True
            if "NVME" in blob:
                drive_kinds.add("NVMe")
            if "SAS" in blob:
                drive_kinds.add("SAS")
            if "SATA" in blob:
                drive_kinds.add("SATA")
    if has_drive and not drive_kinds:
        drive_kinds.add("SATA")  # 协议不明默认 SATA（2U 最常见）
    return gpu_qty, drive_kinds, high_tdp


# 无 GPU 整机负载粗估（CPU TDP + 常项）→ 取 ≥负载的最小标准 PSU 瓦数（1+1 冗余）
_CPU_TDP_MAP = {"9654": 360, "9554": 360, "9754": 360, "9745": 360, "9174f": 320,
                "9454": 290, "9354": 280, "9534": 280, "9334": 280, "8434": 290,
                "9124": 200}  # AMD EPYC 9124 200W（R5）
_DEFAULT_CPU_TDP = 280
_SYS_BASE_W = 260          # 主板/风扇/背板/导风罩等常项
_MEM_STICK_W = 10
_MEM_STICK_W_BY_CAP = [(16, 8), (32, 10), (64, 15), (512, 20)]  # 单条容量G → 功耗W（I15/I61 R24：64G 条实际功耗更高）
_SATA_DRIVE_W = 8
_NVME_DRIVE_W = 15
_NIC_W = 10
_RAID_W = 15
_PSU_STANDARD_W = (1300, 1600, 2000, 2700, 3200)


def _estimate_system_load(kp_parts: list[dict]) -> int:
    """按 KP 件粗估整机负载（W）。CPU 查 TDP 表，其余按件均摊常量——纯估算用于电源建议，
    不是精确功耗计算（2026-08-03 第一轮训练：修"根据功耗选择"无脑出 1600W 默认）。"""
    load = _SYS_BASE_W
    for kp in kp_parts or []:
        cat = kp.get("category") or ""
        name = f"{kp.get('name') or ''} {kp.get('matched_spec') or ''}"
        qty = int(kp.get("qty") or 1)
        cu = cat.upper()
        nu = name.upper()
        if "CPU" in cu:
            m = re.search(r"(\d{4})", name)
            tdp = _CPU_TDP_MAP.get(m.group(1).lower(), _DEFAULT_CPU_TDP) if m else _DEFAULT_CPU_TDP
            load += tdp * qty
        elif "MEM" in cu or "内存" in cat:
            # 内存功耗按单条容量分级（I15/I61 R24）：64G 条 ≈15W，32G ≈10W——原统一 10W 低估高配内存
            _m = re.search(r"(\d{1,3})\s*G\s*B?\b", name, re.I)
            _cap = int(_m.group(1)) if _m else 0
            _w = _MEM_STICK_W
            for _cm, _cw in _MEM_STICK_W_BY_CAP:
                if _cap <= _cm:
                    _w = _cw
                    break
            load += _w * qty
        elif "NVME" in nu:
            load += _NVME_DRIVE_W * qty
        elif any(k in cat for k in ("硬盘", "SSD", "HDD", "DISK")):
            load += _SATA_DRIVE_W * qty
        elif "NIC" in cu or "NETWORK" in cu or "网卡" in cat:
            load += _NIC_W * qty
        elif "RAID" in cu or "阵列" in cat or "HBA" in cu:
            load += _RAID_W
    return load


def _base_config_std_mem_speed(config_id) -> Optional[int]:
    """机型标准内存速率（I47）：base_configs.config_content.standard_mem_speed（如 ES22V3-P=4800），无则 None。
    需求未指定速率时，按机型标准精确选，避免低价选到 5600（技术员惯例 4800）。"""
    if not config_id:
        return None
    try:
        from app.repository.base_config_repo import BaseConfigRepository
        repo = BaseConfigRepository()  # 无 close（stateless，每调用独立引擎连接）
        cfg = repo.get(int(config_id))
        cc = (cfg or {}).get("config_content") or {}
        v = cc.get("standard_mem_speed")
        return int(v) if v not in (None, "") else None
    except Exception:
        return None


def _suggest_psu_wattage(load: int) -> str:
    """1+1 冗余电源：单 PSU ≥ 估算负载 → 取 ≥负载的最小标准瓦数。"""
    for w in _PSU_STANDARD_W:
        if w >= load:
            return str(w)
    return str(_PSU_STANDARD_W[-1])


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


def _infer_psu_wattage(gpu_qty: int, high_tdp: bool = False, kp_parts: Optional[list] = None) -> str:
    """电源瓦数推断（配置驱动：system_config.psu_inference 的 tiers 档位，逐条匹配取首个；
    无 GPU 按 KP 件功耗估算（CPU TDP + 常项）取 ≥负载的最小标准瓦数，替代无脑 1600W 默认）。
    喂前端模板电源行 chassis_signals.psu_wattage；需求文本若显式写了功率，由调用方覆盖。"""
    _cfg = _load_psu_inference()
    for t in _cfg.get("tiers") or []:
        if gpu_qty >= int(t.get("min_gpu") or 0) and bool(t.get("high_tdp")) == high_tdp:
            w = t.get("wattage")
            if w is not None:
                return str(w)
    if not gpu_qty:
        return _suggest_psu_wattage(_estimate_system_load(kp_parts))
    return str(_cfg.get("no_gpu_wattage") or "1600")


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

    # 电源瓦数推断（纯性能推算：CPU TDP + 内存按容量计功耗 + 常项 → ≥负载最小标准档）。
    # I15/I61 2026-08-04 R24：不再用静态"机型标准"字段——改进负载模型（内存按容量计功耗），
    # 让 64G×24 这类高内存配置自然推断出 1600W（原 10W/条 低估 → 1300W）。
    _gpu_qty, _, _high_tdp = _kp_signals(matched_kp)
    chassis_signals = {"psu_wattage": _infer_psu_wattage(_gpu_qty, _high_tdp, matched_kp)}

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

    # 选型配置规则打通：背板类型/线缆根数派生 + require/exclude 校验告警。
    # 规则本体在选型配置页管理（WHEN→THEN），这里执行同一套引擎，让需求分析自动出方案
    # 与工作台人工选配共用一套约束（失败只降级：方案不带派生/校验，不阻塞出方案）。
    try:
        from app.services.plan_rule_apply import apply_plan_selection_rules
        apply_plan_selection_rules(plan, matched_kp, baseline)
    except Exception:
        logger.exception("apply_plan_selection_rules failed; plan continues without rule-derived signals")

    # 背板件与派生 bp_type 对齐：excel 平铺 BOM 行换料号库同 bt 件并补价差
    # （live 模板行已按 ${bp_type_desc} 渲染，此处保证平铺快照与 live 一致——2026-08-03 训练发现）
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
