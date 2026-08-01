"""Requirement intelligence pipeline — 客户需求 → 关键词提取 → 聚合检索 → 候选清单。

一期纯本地：jieba 分词 + DB ILIKE 检索，不调 LLM。每步通过 reasoning_hub 实时广播到
商机详情页的推理面板。失败兜底广播 error，不阻塞。
"""
import logging
import re
import json
import uuid
from typing import Optional

from app.services.reasoning_hub import reasoning_hub
from app.api.candidate_search import select_baselines, select_models, pick_kp_parts, build_plan, kp_categories_for_type

logger = logging.getLogger(__name__)

# ── 关键词词表：品类 → 触发词（中英）──
CATEGORY_LEXICON: dict[str, list[str]] = {
    "CPU": ["cpu", "processor", "处理器", "epyc", "xeon", "至强", "intel", "amd"],
    "Memory": ["memory", "ram", "内存", "ddr", "rdimm"],
    "HDD/SSD": ["hdd", "ssd", "nvme", "硬盘", "磁盘", "sata", "u.2", "u.3"],
    "GPU": ["gpu", "显卡", "图形卡", "rtx", "l40", "w7900", "a100", "h100"],
    "NIC": ["nic", "网络", "网卡", "ethernet", "e810", "mlx", "connectx"],
    "Raid card": ["raid", "阵列卡", "mega", "brocade"],
    "Power": ["psu", "电源", "power", "风扇模块"],
    "Fan": ["fan", "风扇"],
    "Heatsink": ["heatsink", "散热器", "散热"],
    "Cable": ["cable", "线缆", "电源线", "数据线"],
    "Rail": ["rail", "导轨"],
    "Backplane": ["backplane", "背板"],
}
SERIES_KEYWORDS = ["Orion", "Polaris", "Intel", "工作站"]
FORM_PATTERN = re.compile(r"(?<![0-9])([12468]U)(?![A-Za-z])", re.IGNORECASE)
# 型号 token（必含数字，避免 nvme/sata 纯字母品类词误命中）：字母开头混合/纯数字≥4/数字开头混合(960G/7.68T/9560-8i)
MODEL_TOKEN_PATTERN = re.compile(r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$")

# 用途词表（独立维度，不依赖 config，让"AI训练/存储/虚拟化"等回复能闭环反问）
USAGE_LEXICON: dict[str, list[str]] = {
    "AI训练": ["ai训练", "ai 推理", "深度学习", "训练", "大模型", "llm", "gpu 算力"],
    "AI推理": ["推理", "infer", "部署模型", "serving"],
    "存储": ["存储", "对象存储", "分布式存储", "nas", "存储节点", "冷存储"],
    "虚拟化": ["虚拟化", "云主机", "容器", "k8s", "虚拟机", "openstack"],
    "数据库": ["数据库", "mysql", "olap", "oltp", "oracle", "postgres"],
    "渲染": ["渲染", "视觉", "特效", "影视后期"],
    "通用计算": ["通用", "办公", "web 服务", "业务系统"],
}
# 预算抽取：预算/budget 前缀 或 带万/w/k 单位的裸数字
_BUDGET_PREFIX = re.compile(r"(?:预算|budget|价位|价格|大概)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(万|w|k|元|块)?", re.IGNORECASE)
_BUDGET_UNIT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(万|w|k)\b")  # 前非数字/点 + 1-3位：避免 3000W 子串匹配 0w

# 数量抽取："N卡"→GPU, "N条"→Memory, "N颗/N块"→CPU（给 pick_kp_parts 按数量配）
QTY_UNIT_PATTERN = re.compile(r"(\d+)\s*(卡|条|颗|块)")
QTY_UNIT_TO_CAT: dict[str, str] = {"卡": "GPU", "条": "Memory", "颗": "CPU", "块": "CPU"}

# 中文停用词（粗表）
_CN_STOPWORDS = set("的了和与及或是在为对我你他这那有无疑也都很还再又个把被让使给向从到上下进出过")


def _is_stopword(tok: str) -> bool:
    if not tok:
        return True
    if len(tok) == 1:
        return True
    if all(ch in _CN_STOPWORDS for ch in tok):
        return True
    return False


def _extract_budget(text: str) -> Optional[float]:
    """从需求文本抽预算（元）。支持「预算20万 / 20w / 200k / 预算200000 / 20万」。"""
    low = (text or "").lower()
    m = _BUDGET_PREFIX.search(low)
    if not m:
        m = _BUDGET_UNIT.search(low)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except (TypeError, ValueError):
        return None
    unit = (m.group(2) or "").lower()
    if unit in ("万", "w"):
        num *= 10000
    elif unit == "k":
        num *= 1000
    return num


# 内存代际/速率/容量正则（_extract_mem_signal 用）
_MEM_GEN_RE = re.compile(r"DDR?([345])", re.IGNORECASE)
_MEM_SPEED_RE = re.compile(r"(?<![\d])(3200|4400|4800|5200|5600|6400)(?:\s*MT/s?\b|MHz)?", re.IGNORECASE)
_MEM_SIGNAL_RE = re.compile(r"DDR?([345])|\bD[345]\b|内存|memory|\bram\b|rdimm", re.IGNORECASE)
_NUM_GB_RE = re.compile(r"(\d+)\s*GB?\b", re.IGNORECASE)


def _extract_mem_signal(text: str) -> Optional[dict]:
    """从需求文本提取内存语义 {total_gb, type(DDR4/DDR5), speed}。
    total_gb 取「含内存信号(DDR/D5/内存)的段」里的 G 值，避免误抓 SSD/硬盘容量（如 480G启动盘）。
    无任何内存信号 → None（交回主流程按 spec_rules/代表件处理）。"""
    if not text:
        return None
    gen = _MEM_GEN_RE.search(text)
    mem_type = f"DDR{gen.group(1)}" if gen else (
        "DDR5" if re.search(r"\bD5\b", text, re.IGNORECASE) else
        "DDR4" if re.search(r"\bD4\b", text, re.IGNORECASE) else None
    )
    has_mem_word = bool(_MEM_SIGNAL_RE.search(text))
    if not mem_type and not has_mem_word:
        return None
    speed_m = _MEM_SPEED_RE.search(text)
    speed = int(speed_m.group(1)) if speed_m else None
    # 容量：按段切，只取含内存信号的段；无内存段则全文兜底
    segs = re.split(r"[\n,，;；、]+", text)
    mem_segs = [s for s in segs if _MEM_SIGNAL_RE.search(s)]
    scope = " ".join(mem_segs) if mem_segs else text
    caps = [int(m.group(1)) for m in _NUM_GB_RE.finditer(scope)]
    caps = [c for c in caps if c <= 1024]  # 单条内存不 >1024G，超的当硬盘忽略
    total = max(caps) if caps else None
    if not mem_type and not speed and not total:
        return None
    return {"type": mem_type, "speed": speed, "total_gb": total}


# CPU 双路信号（全套/满配/双路/2颗 → 双 CPU）
_DUAL_CPU_RE = re.compile(r"全套|满配|双路|双\s*CPU|2\s*颗|两颗|2\s*cpu", re.IGNORECASE)


def _extract_cpu_signal(text: str) -> Optional[dict]:
    """从需求文本提取 CPU 信号 {duality}。全套配置/双路/满配/2颗 → duality=True。"""
    if not text:
        return None
    return {"duality": True} if _DUAL_CPU_RE.search(text) else None


# 电源功率（W）：'电源配1300' / '1300W电源' / '1300W' → 1300
_PSU_WATT_RE = re.compile(r"(?:电源|psu|power)[^\d]{0,6}(\d{3,4})|(\d{3,4})\s*[Ww](?:att)?(?:\s*电源)?")


def _extract_psu_signal(text: str) -> Optional[dict]:
    """从需求文本提电源功率 {wattage}。合理服务器 PSU 范围 200-3000W，超范围忽略。"""
    if not text:
        return None
    m = _PSU_WATT_RE.search(text)
    if not m:
        return None
    w = m.group(1) or m.group(2)
    try:
        wattage = int(w)
    except (TypeError, ValueError):
        return None
    if 200 <= wattage <= 3000:
        return {"wattage": wattage}
    return None


def _fold_lexicons(lexicons: Optional[list]) -> tuple:
    """把多张词表折叠成 5 个 dict，喂给 extract_keywords。
    - kind=kp          → category_lexicon {品类: [triggers]}（喂 pick_kp_parts）
    - kind=chassis     → chassis_lexicon {底盘件品类: [triggers]}（单独，不喂 pick）
    - kind=server_type → usage_keyword_map {trigger: 类型名}
    - kind=series      → series_keyword_map {trigger: 系列}
    - kind=form        → form_keyword_map {trigger: 形态}
    返回 (cat_lex, chassis_lex, usage_map, series_map, form_map)，均可能为空 dict。"""
    cat_lex, chassis_lex, usage_map, series_map, form_map = {}, {}, {}, {}, {}
    for lex in (lexicons or []):
        kind = lex.get("kind")
        for e in lex.get("entries") or []:
            key = e.get("key")
            triggers = e.get("triggers") or []
            if not key:
                continue
            if kind == "kp":
                cat_lex.setdefault(key, []).extend(triggers)
            elif kind == "chassis":
                chassis_lex.setdefault(key, []).extend(triggers)
            elif kind == "server_type":
                for t in triggers:
                    usage_map[t] = key
            elif kind == "series":
                for t in triggers:
                    series_map[t] = key
            elif kind == "form":
                for t in triggers:
                    form_map[t] = key
    return cat_lex, chassis_lex, usage_map, series_map, form_map


def extract_keywords(text: str, lexicon: Optional[dict] = None, keyword_limit: int = 12,
                     series_keyword_map: Optional[dict] = None,
                     usage_keyword_map: Optional[dict] = None,
                     form_keyword_map: Optional[dict] = None,
                     chassis_lexicon: Optional[dict] = None,
                     spec_aliases: Optional[list] = None,
                     qty_units: Optional[list] = None,
                     qty_multipliers: Optional[list] = None,
                     model_token_regex: Optional[str] = None) -> dict:
    """从需求文本提取关键词、品类、系列、形态。

    Returns: {keywords:[...], categories:[...], series, form}
    """
    text = (text or "").strip()
    series: Optional[str] = None
    form: Optional[str] = None
    categories: list[str] = []
    keywords: list[str] = []

    if not text:
        return {"keywords": [], "categories": [], "series": None, "form": None,
                "usage": None, "server_type_name": None, "chassis_categories": [],
                "qty_map": {}, "qty_per_token": {}, "spec_search_terms": set(), "budget": None,
                "mem_signal": None, "cpu_signal": None, "multi_spec_filters": {}, "psu_signal": None}

    low = text.lower()

    # 型号 token 正则（model_token_regex 可配，None→模块常量 MODEL_TOKEN_PATTERN 兜底；和 pick_kp_parts 同源）
    _mt_pattern = MODEL_TOKEN_PATTERN
    if model_token_regex:
        try:
            _mt_pattern = re.compile(model_token_regex)
        except Exception as e:
            logger.warning("model_token_regex 编译失败，用默认: %s", e)

    # 品类命中（lexicon 可来自 reasoning_flow 配置；None=用模块 CATEGORY_LEXICON）
    for cat, toks in (lexicon if lexicon is not None else CATEGORY_LEXICON).items():
        if any(t in low for t in toks):
            categories.append(cat)
            keywords.extend(t for t in toks if t in low)

    # 机箱底盘件命中（单独存 chassis_categories，不进 pick_kp_parts 的 categories——KP 库无底盘件，进了只制造 unmatched）
    chassis_categories: list[str] = []
    if chassis_lexicon:
        for cat, toks in chassis_lexicon.items():
            if any(t in low for t in toks):
                chassis_categories.append(cat)

    # 规格别名（千兆/万兆等规格描述 → 品类 + 搜索词；救 ILIKE 命不中的规格词，库 model 是英文不含"千兆"）
    spec_search_terms: set[str] = set()
    multi_spec_filters: dict[str, list[dict]] = {}
    if spec_aliases:
        for _alias in spec_aliases:
            _trig = (_alias.get("trigger") or "").lower()
            if _trig and _trig in low:
                _cat = _alias.get("category") or ""
                if _cat and _cat not in categories:
                    categories.append(_cat)
                for _term in (_alias.get("search_terms") or []):
                    if _term and _term.lower() not in {k.lower() for k in keywords}:
                        keywords.append(_term)
                        spec_search_terms.add(_term.lower())
                # 同品类多规格（如千兆+万兆网卡）：收集 spec_filter，pick stage2 按速率各产出一件
                _sf = _alias.get("spec_filter")
                if _cat and isinstance(_sf, dict) and _sf.get("spec_key"):
                    multi_spec_filters.setdefault(_cat, []).append(_sf)

    # 按品类触发词分段解析数量（结构化清单"品类：型号 * N"，每段独立，避免跨行乱关联）
    _multis = "".join(re.escape(_m) for _m in (qty_multipliers or ["*", "×"]))
    qty_map: dict[str, int] = {}
    qty_per_token: dict[str, int] = {}  # 型号 token → 其所在段的 qty（精确到每个件）
    if lexicon:
        _trigger_to_cat = {t.lower(): c for c, toks in lexicon.items() for t in toks}
        _hits: list[tuple[int, int, str]] = []
        for _trig, _cat in _trigger_to_cat.items():
            for _m in re.finditer(re.escape(_trig), low):
                _hits.append((_m.start(), _m.end(), _cat))
        _hits.sort()
        for i, (_s, _e, _cat) in enumerate(_hits):
            _seg_end = _hits[i + 1][0] if i + 1 < len(_hits) else len(low)
            _seg = low[_e:_seg_end]
            _mq = re.search(rf"[{_multis}]\s*(\d+)", _seg)
            if not _mq:
                continue
            _qty = int(_mq.group(1))
            if _cat not in qty_map:
                qty_map[_cat] = _qty
            # 该段内型号 token 关联此 qty（pick stage 1 命中时用，精确到件）
            for _tm in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", _seg):
                _t = _tm.group().lower()
                if _mt_pattern.match(_t) and _t not in qty_per_token:
                    qty_per_token[_t] = _qty
    # N卡/N条 兜底（口语化数量；qty_units 可配，None→模块常量 QTY_UNIT_TO_CAT 兜底）
    _unit_to_cat = {(u.get("unit") or ""): (u.get("category") or "")
                    for u in (qty_units or [{"unit": k, "category": v} for k, v in QTY_UNIT_TO_CAT.items()])}
    if _unit_to_cat:
        _unit_re = re.compile(r"(\d+)\s*(" + "|".join(re.escape(u) for u in _unit_to_cat if u) + ")")
        for m in _unit_re.finditer(text):
            n = int(m.group(1))
            cat = _unit_to_cat.get(m.group(2))
            if cat and cat not in qty_map:
                qty_map[cat] = n

    # 系列：先查关键词→系列映射表（reasoning_flow 可配，如 amd→Orion），未命中再字面命中 SERIES_KEYWORDS
    if series_keyword_map:
        for kw, mapped in series_keyword_map.items():
            if kw and kw.lower() in low and mapped:
                series = mapped
                break
    if not series:
        for s in SERIES_KEYWORDS:
            if s.lower() in low:
                series = s
                break

    # 形态：优先走配置的 form_keyword_map（trigger→form，带数字边界避免"44u"误命中"4u"），未命中走 FORM_PATTERN 兜底
    if form_keyword_map:
        for trig, f_val in form_keyword_map.items():
            if trig and f_val and re.search(rf"(?<![0-9]){re.escape(trig.lower())}(?![A-Za-z])", low):
                form = f_val
                break
    if not form:
        m = FORM_PATTERN.search(text)
        if m:
            form = m.group(1).upper()

    # 用途/服务器类型：优先走配置的 usage_keyword_map（trigger→server_type_name 精确），
    # 未命中走 USAGE_LEXICON 兜底（usage 文本，给 select_models 模糊匹配）
    usage: Optional[str] = None
    server_type_name: Optional[str] = None
    if usage_keyword_map:
        for trig, type_name in usage_keyword_map.items():
            if trig and trig.lower() in low and type_name:
                server_type_name = type_name
                usage = type_name
                break
    if not usage:
        for u, toks in USAGE_LEXICON.items():
            if any(t in low for t in toks):
                usage = u
                break

    # 预算（元）
    budget = _extract_budget(text)
    mem_signal = _extract_mem_signal(text)
    cpu_signal = _extract_cpu_signal(text)
    psu_signal = _extract_psu_signal(text)

    # jieba 分词补充关键词（型号 token + 有意义词）
    tokens: list[str] = []
    try:
        import jieba
        tokens = list(jieba.cut(text, cut_all=False))
    except Exception as e:
        logger.warning("jieba 不可用，退化到空格切分: %s", e)
        tokens = re.split(r"[\s,，、;；]+", text)

    for tok in tokens:
        tok = tok.strip()
        if not tok or _is_stopword(tok):
            continue
        # 型号样 token 直接收
        if _mt_pattern.match(tok) and tok not in keywords:
            keywords.append(tok)
        # 数字+单位（如 32G / 1.92T / 2U）作检索补充
        elif re.match(r"^[0-9]+\.?[0-9]*[GT]\b", tok, re.IGNORECASE) and tok not in keywords:
            keywords.append(tok)

    # 从原文直接补抓型号 token（jieba 会切碎数字+字母组合如 960G/7.68T/9560-8i）
    _model_tokens: list[str] = []
    _existing = {k.lower() for k in keywords}
    for _m in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", text):
        _tok = _m.group()
        if _mt_pattern.match(_tok) and _tok.lower() not in _existing:
            _model_tokens.append(_tok)
            _existing.add(_tok.lower())
    keywords[0:0] = _model_tokens  # 型号 token 插入开头（优先，不被 keyword_limit 截断）

    # 去重保序、限长（型号 token 优先保留——精确匹配价值最高，不被品类词挤掉）
    seen = set()
    deduped = []
    _model_first = [k for k in keywords if _mt_pattern.match(k)]
    _others = [k for k in keywords if not _mt_pattern.match(k)]
    for k in _model_first + _others:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            deduped.append(k)
        if len(deduped) >= keyword_limit:
            break

    return {"keywords": deduped, "categories": categories, "series": series, "form": form,
            "usage": usage, "server_type_name": server_type_name,
            "chassis_categories": chassis_categories,
            "qty_map": qty_map, "qty_per_token": qty_per_token,
            "spec_search_terms": spec_search_terms, "budget": budget,
            "mem_signal": mem_signal, "cpu_signal": cpu_signal,
            "multi_spec_filters": multi_spec_filters, "psu_signal": psu_signal}


PIPELINE_STEPS = [
    {"key": "extract", "label": "需求理解与关键词提取"},
    {"key": "select_baseline", "label": "机型选型（基准配置）"},
    {"key": "match_kp", "label": "配件匹配"},
    {"key": "compose", "label": "组合整机方案"},
    {"key": "review", "label": "方案就绪"},
]


# 反问最多 N 轮（与 reasoning_executor.MAX_CLARIFY_ROUNDS 同步）
MAX_CLARIFY_ROUNDS = 3


def apply_budget_check(plans: list, budget: Optional[float], underspend_threshold: float = 0.5) -> int:
    """给 plans 注 over_budget / underspend 字段（在 summary.total_cost 上算）。
    - over_budget: 方案价 > 预算（超了多少）
    - underspend: 方案价/预算 < underspend_threshold（默认 0.5，预算没用足一半 → 可升级配置）
    返回超预算方案数。budget=None 时跳过。图 executor + 线性 fallback 共用。"""
    if budget is None or not plans:
        return 0
    over = 0
    for p in plans:
        total = (p.get("summary") or {}).get("total_cost") or 0
        if total and total > budget:
            p["over_budget"] = {
                "amount": round(total - budget, 2),
                "ratio": round((total - budget) / budget, 2),
            }
            p["underspend"] = None
            over += 1
        else:
            p["over_budget"] = None
            ratio = round(total / budget, 2) if budget else 0
            if ratio < underspend_threshold:
                p["underspend"] = {"ratio": ratio, "amount": round(budget - total, 2)}
            else:
                p["underspend"] = None
    return over


def _read_opportunity_extra(opportunity_id: str) -> dict:
    """读商机 extra_fields（JSON）。失败返回 {}。直查模式，不依赖 repo.get。"""
    try:
        from app.models.opportunity import Opportunity
        from app.models.base import Opportunity_SessionLocal
        with Opportunity_SessionLocal() as session:
            opp = session.query(Opportunity).filter(
                Opportunity.opportunity_id == opportunity_id
            ).first()
            if not opp or not opp.extra_fields:
                return {}
            return json.loads(opp.extra_fields) if isinstance(opp.extra_fields, str) else (opp.extra_fields or {})
    except Exception as e:
        logger.warning("读商机 extra_fields 失败 opp=%s err=%s", opportunity_id, e)
        return {}


def _read_opportunity_budget(opportunity_id: str) -> Optional[float]:
    extra = _read_opportunity_extra(opportunity_id)
    b = extra.get("budget")
    try:
        return float(b) if b is not None else None
    except (TypeError, ValueError):
        return None


def _read_clarify_round(opportunity_id: str) -> int:
    extra = _read_opportunity_extra(opportunity_id)
    try:
        return int(extra.get("requirement_clarity_round", 0))
    except (TypeError, ValueError):
        return 0


def _write_clarify_round(opportunity_id: str, round_num: int) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {"requirement_clarity_round": round_num})
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 clarify_round 失败 opp=%s err=%s", opportunity_id, e)


async def run_pipeline(opportunity_id: str, requirement_text: str,
                       supplement: dict = None, force_complete: bool = False) -> None:
    """跑推理 pipeline。有 active flow → 图驱动 executor；异常或无 flow → 线性 5 步 fallback。

    supplement: 反答回填 {"text":..., "budget":...}；force_complete: 用户点跳过，强制走选型。
    三层兜底：DB 异常 → linear fallback；graph executor 异常 → linear fallback。"""
    # 拼接完整需求文本（原文 + 反问补充）
    full_text = requirement_text or ""
    if supplement and supplement.get("text"):
        full_text = f"{full_text}\n---\n补充：{supplement['text']}" if full_text else supplement["text"]

    # 预算优先级：反问明确给 > 商机 extra_fields > 无
    if supplement and supplement.get("budget") is not None:
        budget = supplement["budget"]
    else:
        budget = _read_opportunity_budget(opportunity_id)

    # 反问轮次（死循环防护，存 extra_fields 跨重启/多用户）
    round_num = _read_clarify_round(opportunity_id)
    if supplement:
        round_num = min(round_num + 1, MAX_CLARIFY_ROUNDS + 1)
        _write_clarify_round(opportunity_id, round_num)

    pipeline_id = f"pl_{uuid.uuid4().hex[:12]}"
    initial_ctx = {
        "budget": budget,
        "clarify_round": round_num,
        "pipeline_id": pipeline_id,
        "force_complete": force_complete,
    }

    async def _broadcast(payload: dict):
        payload.setdefault("opportunity_id", opportunity_id)
        payload.setdefault("pipeline_id", pipeline_id)
        payload.setdefault("round", round_num)
        await reasoning_hub.broadcast(opportunity_id, payload)

    flow = None
    try:
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        _rf = ReasoningFlowRepository()
        try:
            flow = _rf.get_active_flow()
        finally:
            _rf.close()
    except Exception as e:
        logger.warning("读 reasoning flow 失败: %s", e)

    graph_nodes = (flow or {}).get("graph", {}).get("nodes") or []
    if flow and graph_nodes:
        try:
            from app.services.reasoning_executor import run_graph_executor
            steps = [{"key": n.get("id"), "label": n.get("label") or n.get("id")} for n in graph_nodes]
            await _broadcast({"type": "pipeline_start", "steps": steps, "is_rerun": round_num > 0})
            ctx = await run_graph_executor(opportunity_id, full_text, flow, _broadcast, initial_ctx=initial_ctx)
            # ask_user 叶子节点置 awaiting_input → 发 paused（等用户补）；否则 done
            if ctx.get("awaiting_input") and not force_complete:
                await _broadcast({"type": "pipeline_paused", "reply_id": ctx.get("last_reply_id")})
            else:
                await _broadcast({"type": "pipeline_done"})
            return
        except Exception as e:
            logger.exception("graph executor 失败，回退 linear fallback: %s", e)

    await _run_linear_fallback(opportunity_id, full_text, _broadcast, flow, budget=budget)


async def _run_linear_fallback(opportunity_id: str, requirement_text: str, _broadcast, flow,
                              budget: Optional[float] = None) -> None:
    """线性 5 步 fallback（原 run_pipeline 体）。flow.node_configs 透传参数；三层兜底。"""
    cfg: dict = {}
    if flow:
        cfg = flow.get("node_configs") or {}
    try:
        await _broadcast({"type": "pipeline_start", "steps": PIPELINE_STEPS})

        # 1. 提取
        await _broadcast({"type": "step_start", "step": "extract"})
        _ext_cfg = cfg.get("extract") or {}
        if _ext_cfg.get("lexicons"):
            _cat_lex, _chassis_lex, _usage_map, _series_map, _form_map = _fold_lexicons(_ext_cfg["lexicons"])
        else:
            _cat_lex = _ext_cfg.get("category_lexicon")
            _chassis_lex, _usage_map, _series_map, _form_map = None, None, None, None
        ext = extract_keywords(
            requirement_text,
            lexicon=_cat_lex,
            keyword_limit=_ext_cfg.get("keyword_limit") or 12,
            series_keyword_map=_series_map,
            usage_keyword_map=_usage_map,
            form_keyword_map=_form_map,
            chassis_lexicon=_chassis_lex,
            spec_aliases=_ext_cfg.get("spec_aliases"),
            qty_units=_ext_cfg.get("qty_units"),
            qty_multipliers=_ext_cfg.get("qty_multipliers"),
            model_token_regex=_ext_cfg.get("model_token_regex"),
        )
        await _broadcast({
            "type": "step_done", "step": "extract",
            "payload": {
                "keywords": ext["keywords"],
                "categories": ext["categories"],
                "series": ext["series"],
                "form": ext["form"],
            },
        })

        # 2. 机型选型（usage→机型类型 + 系列/形态，只推命中的不硬塞）
        await _broadcast({"type": "step_start", "step": "select_baseline"})
        _sb_cfg = cfg.get("select_baseline") or {}
        baselines = select_models(
            ext.get("usage"),
            ext.get("server_type_name"),
            ext["series"], ext["form"],
            limit=_sb_cfg.get("max_plans") or 3,
            recommend_strategy_id=_sb_cfg.get("recommend_strategy_id"),
            no_signal_strategy=_sb_cfg.get("no_signal_strategy"),
        )
        await _broadcast({
            "type": "step_done", "step": "select_baseline",
            "payload": {
                "count": len(baselines),
                "matches": [{
                    "config_id": b.get("id"),
                    "name": b.get("name") or "",
                    "series": b.get("series") or "",
                    "form": b.get("form") or "",
                } for b in baselines],
            },
        })

        # 3. 配件匹配（per-机型：每个机型按自己的 server_type 套餐 ∪ 需求品类）
        await _broadcast({"type": "step_start", "step": "match_kp"})
        _mk_cfg = cfg.get("match_kp") or {}
        _cfg_pick = _mk_cfg.get("representative_pick")
        if _cfg_pick and _cfg_pick != "auto":
            _pick = _cfg_pick
        else:
            from app.services.reasoning_executor import _resolve_budget_strategy
            _pick = _resolve_budget_strategy(budget)
        _kp_by_model: dict = {}
        _all_kp: list = []
        for _bl in baselines:
            _type_cats = kp_categories_for_type(_bl.get("server_type_name") or "", _mk_cfg.get("type_packages"), ext["categories"])
            _eff_cats = list(dict.fromkeys(_type_cats + (ext["categories"] or [])))
            _bl_kp = pick_kp_parts(
                _eff_cats, ext["keywords"],
                category_aliases=_mk_cfg.get("category_aliases"),
                representative_pick=_pick,
                spec_rules=_mk_cfg.get("spec_rules"),
                fallback_strategy=_mk_cfg.get("fallback_strategy") or "fallback_representative",
                requirement_text=requirement_text,
                qty_map=ext.get("qty_map"),
                qty_per_token=ext.get("qty_per_token"),
                spec_search_terms=ext.get("spec_search_terms"),
                model_token_regex=_ext_cfg.get("model_token_regex"),
                mem_signal=ext.get("mem_signal"),
                cpu_signal=ext.get("cpu_signal"),
                multi_spec_filters=ext.get("multi_spec_filters"),
            )
            _kp_by_model[_bl.get("server_model_id") or _bl.get("id")] = _bl_kp
            _all_kp.extend(_bl_kp)
        by_category: dict[str, int] = {}
        for kp in _all_kp:
            c = kp.get("category") or "其他"
            by_category[c] = by_category.get(c, 0) + 1
        unmatched_count = sum(1 for kp in _all_kp if kp.get("unmatched"))
        await _broadcast({
            "type": "step_done", "step": "match_kp",
            "payload": {"kp_count": len(_all_kp), "by_category": by_category, "unmatched_count": unmatched_count},
        })

        # 4. 组合整机方案（每 baseline 取自己 per-机型配的 KP）
        await _broadcast({"type": "step_start", "step": "compose"})
        if not baselines:
            await _broadcast({
                "type": "step_done", "step": "compose",
                "payload": {"plans_count": 0, "warning": "未找到匹配的基准配置，请手填或调整需求"},
            })
            await _broadcast({"type": "pipeline_done"})
            return
        plans = []
        for _bl in baselines:
            _bl_kp = _kp_by_model.get(_bl.get("server_model_id") or _bl.get("id")) or []
            plans.append(build_plan(_bl, _bl_kp))
        # 底盘件信号注入 plan（前端 usePlanBom.deriveVars 读 psu_wattage 显示电源功率）
        _sig = {"psu_wattage": (ext.get("psu_signal") or {}).get("wattage")}
        for p in plans:
            p["chassis_signals"] = _sig
        apply_budget_check(plans, budget)  # 注 over_budget / underspend 字段
        await _broadcast({
            "type": "step_done", "step": "compose",
            "payload": {"plans_count": len(plans)},
        })

        # 5. 方案就绪 → 下发整机方案清单
        await _broadcast({"type": "step_start", "step": "review"})
        await _broadcast({
            "type": "candidates_ready",
            "plans": plans,
            "keywords": ext["keywords"],
            "series": ext["series"],
            "form": ext["form"],
        })
        await _broadcast({"type": "step_done", "step": "review"})

        await _broadcast({"type": "pipeline_done"})
    except Exception as e:
        logger.exception("requirement pipeline failed for %s", opportunity_id)
        await _broadcast({"type": "error", "message": f"推理流程异常: {e}"})
