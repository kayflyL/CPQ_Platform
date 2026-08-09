# -*- coding: utf-8 -*-
"""CaseProvider —— 智能体 search_cases 工具的案例检索抽象（CBR-RAG 案例源）。

llm_agent 的 search_cases 工具通过 CaseProvider 取相似历史案例（需求→配置 对照），
让智能体接地时有「这种需求该怎么配」的参照，不再零样本瞎抽（参照 CBR-RAG，arXiv 2404.04302）。

接入解耦（用户定调：当前内部表，以后可接专门 RAG API）：
- CaseProvider 接口：retrieve(query, tags, top_k) → [案例 digest]
- InternalBomCaseProvider：查 rules.bom_cases（scenario_tags + 需求字符 n-gram TF-IDF 相似，零依赖）
- ExternalRagProvider（以后）：调外部 RAG/向量库 API（向量检索，海量 case）

检索方案（2026-08 定稿，A 方案）：
案例库为用户手动管理、规模小 → CJK 免分词的轻量可靠方案 = 字符 2+3-gram + TF-IDF 加权余弦。
不引 jieba / rank_bm25 / Whoosh / 向量库；若案例库未来增长到 n-gram 精度不够，走
ExternalRagProvider（向量检索），而不是再加本地分词依赖。

⚠️ 案例库纯用户手动管理（选型配置·BOM 案例库 页面增删），本模块只读，绝不自动入库
（用户明确：需求分析结果不进案例库）。
"""
import logging
import math
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)


class CaseProvider:
    """案例检索抽象。retrieve 返回相似案例 digest 列表（供 llm_extract 拼 few-shot）。"""
    def retrieve(self, query: str, tags: Optional[list] = None, top_k: int = 2) -> list:
        return []


# 需求关键词 → 场景标签（轻量推断，给检索用；无向量）
_TAG_KEYWORDS = {
    "AI": ["gpu", "ai", "训练", "推理", "深度学习", "加速计算", "5090", "4090", "a100", "h100", "h800", "l40", "w7900", "涡轮"],
    "存储": ["存储", "对象存储", "nas", "大容量", "冷存储", "分布式存储"],
    "通用": ["虚拟化", "数据库", "web", "容器", "k8s", "通用", "办公", "业务", "mysql", "oracle"],
    "2U": ["2u"],
    "4U": ["4u"],
    "8卡GPU": ["8卡", "8 gpu", "8gpu", "8块gpu", "8×gpu", "8*gpu", "8 ×gpu"],
    "Orion": ["orion", "amd", "epyc", "猎户", "genoa"],
    "Polaris": ["polaris", "兆芯", "kh5000", "kh-5000", "kh50000", "开胜"],
    "Intel": ["intel", "xeon"],
}


def _infer_tags(query: str) -> list:
    """需求关键词 → 场景标签（检索用，轻量；非精确分类，只为匹配 BomCase.scenario_tags）。"""
    low = (query or "").lower()
    return [tag for tag, kws in _TAG_KEYWORDS.items() if any(kw in low for kw in kws)]


# ── 零依赖字符 n-gram + TF-IDF 检索（A 方案）──────────────────────────
# 查询/案例需求先归一化（小写、去空白标点，只留 CJK+字母数字），再取字符 2+3-gram：
# 2-gram 覆盖中文相邻字；3-gram 保英文词（如 gpu）与中文短语；IDF 自动给罕见 gram 加权，
# 让「深度学习/训练」这类有区分度的词主导，而不是被每条案例都有的「服务器」淹没。
_GRAM_SIZES = (2, 3)
_KEEP_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]+")


def _normalize(text: str) -> str:
    """小写 + 只留 CJK/字母数字（去掉空白、标点、× 等噪声，避免产生垃圾 gram）。"""
    return "".join(_KEEP_RE.findall(text or "")).lower()


def _ngrams(text: str, n: int) -> list:
    return [text[i:i + n] for i in range(max(0, len(text) - n + 1))]


def _tokenize(text: str) -> Counter:
    """字符 2+3-gram 计数（TF）。零依赖、免分词；供 TF-IDF 加权余弦。"""
    norm = _normalize(text)
    grams = []
    for n in _GRAM_SIZES:
        grams.extend(_ngrams(norm, n))
    return Counter(grams)


def _build_index(req_texts: list):
    """req_texts: 启用案例的需求原文 → (doc_vecs, idf, max_idf, doc_norms)。

    idf = log((N+1)/(df+1)) + 1（平滑，罕见 gram 权重大）；doc 向量 = (1+log tf) × idf。
    """
    n = len(req_texts)
    df = Counter()
    doc_grams = []
    for t in req_texts:
        grams = _tokenize(t)
        doc_grams.append(grams)
        df.update(grams.keys())
    idf = {g: math.log((n + 1) / (df[g] + 1)) + 1.0 for g in df}
    max_idf = max(idf.values()) if idf else 1.0
    vecs, norms = [], []
    for grams in doc_grams:
        vec = {g: (1.0 + math.log(tf)) * idf[g] for g, tf in grams.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vecs.append(vec)
        norms.append(norm)
    return vecs, idf, max_idf, norms


def _kw_score(q_grams: Counter, doc_vec: dict, doc_norm: float, idf: dict, max_idf: float) -> float:
    """查询 × 案例 的 TF-IDF 余弦相似度 [0,1]（查询侧同样 TF-IDF 加权）。"""
    qvec = {g: (1.0 + math.log(tf)) * idf.get(g, max_idf) for g, tf in q_grams.items()}
    qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
    dot = sum(w * doc_vec.get(g, 0.0) for g, w in qvec.items())
    return dot / (qnorm * doc_norm)


class InternalBomCaseProvider(CaseProvider):
    """查 rules.bom_cases（启用案例）做 CBR 检索。

    检索方式（零依赖）：scenario_tags 交集 + 需求字符 2+3-gram TF-IDF 余弦相似，
    加权排序取 top_k。case 少或无命中 → 返回空（llm_extract 退零样本），不阻塞、不变差。

    match:
      - "tags": 只按场景标签交集（旧 tags 模式）
      - "keyword": 只按需求 TF-IDF 余弦相似
      - "tags_keyword"（默认）: TF-IDF 余弦 + 每个命中标签 +0.3 加权
    """

    def __init__(self, match: str = "tags_keyword"):
        self.match = match  # tags / keyword / tags_keyword（默认）

    def retrieve(self, query: str, tags: Optional[list] = None, top_k: int = 2) -> list:
        tags = tags or _infer_tags(query)
        q_grams = _tokenize(query)
        scored = []
        try:
            from app.models.bom_case import BomCase
            from app.models.base import Rules_SessionLocal
            s = Rules_SessionLocal()
            try:
                cases = s.query(BomCase).filter(BomCase.enabled == True).all()
                vecs, idf, max_idf, norms = _build_index([(c.requirement or "") for c in cases])
                for i, c in enumerate(cases):
                    ctags = set(c.scenario_tags or [])
                    tag_score = len(ctags & set(tags))
                    kw_score = _kw_score(q_grams, vecs[i], norms[i], idf, max_idf)
                    if self.match == "tags":
                        score = float(tag_score)
                    elif self.match == "keyword":
                        score = kw_score
                    else:  # tags_keyword（默认）
                        score = kw_score + 0.3 * tag_score
                    if score > 0:
                        scored.append((score, c))
            finally:
                s.close()
        except Exception as e:
            logger.warning("InternalBomCaseProvider 查询失败（退零样本）: %s", e)
            return []
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._digest(c) for _, c in scored[:max(0, int(top_k))]]

    def _digest(self, c) -> dict:
        """case → few-shot digest：原始需求 + 场景标签 + 真实配置（底盘 l6 + 关键件 kp）。

        关键件（CPU/GPU/内存/盘/网卡）解析自 kp_lines（join kp.kp_parts 取品类/件名），让 LLM 看到相似
        案例实际选了什么——不只底盘件 + 需求原文（旧 digest 丢 kp_lines，grounding 信号弱）。
        """
        l6 = []
        for r in (c.l6_rows or [])[:10]:
            if isinstance(r, dict):
                cat = (r.get("catalogue") or "").strip()
                if cat:
                    l6.append(f"{cat} ×{r.get('qty', 1)}")
        # 关键件解析成 {category, name, qty}（CPU/GPU/内存…，真实选件，给 LLM 配置模式参照）
        kp_lines = c.kp_lines or []
        kp_summary: list = []
        if kp_lines:
            try:
                from app.repository.bom_case_repo import _resolve_parts
                resolved = _resolve_parts([ln.get("part_id") for ln in kp_lines if ln.get("part_id")])
            except Exception as e:
                logger.warning("digest 解析 kp_parts 失败（退 part_id 兜底）: %s", e)
                resolved = {}
            for ln in kp_lines:
                pid = ln.get("part_id")
                r = (resolved.get(int(pid)) if pid is not None else None) or {}
                cat = (r.get("category") or "").strip()
                name = (r.get("name") or r.get("pn") or "").strip()
                qty = ln.get("qty") or 1
                if cat or name:
                    kp_summary.append({"category": cat, "name": name, "qty": qty})
        return {
            "requirement": (c.requirement or "").strip()[:300],
            "scenario_tags": c.scenario_tags or [],
            "l6_config": l6,
            "kp_parts": kp_summary,
        }


def get_case_provider(config: dict) -> CaseProvider:
    """按 llm_agent config 取 CaseProvider（search_cases 工具用）。

    case_source:
      - "internal"（默认）：InternalBomCaseProvider（查 BomCase 表）
      - "external"（以后）：ExternalRagProvider（调 RAG/向量库 API）—— 暂未实现，退空
      - "off"：关闭 CBR，退零样本
    """
    cfg = config or {}
    src = cfg.get("case_source", "internal")
    if src == "off":
        return CaseProvider()  # 空，retrieve 返回 []
    if src == "external":
        # 以后：return ExternalRagProvider(cfg.get("case_api_url"), cfg.get("case_api_key"))
        logger.info("external RAG provider 暂未实现，退 internal")
        return InternalBomCaseProvider(match=cfg.get("case_match", "tags_keyword"))
    return InternalBomCaseProvider(match=cfg.get("case_match", "tags_keyword"))
