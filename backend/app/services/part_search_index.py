# -*- coding: utf-8 -*-
"""配件语义索引（2026-09-12 P1）：kp.kp_part_search_index 的构建与加载。

向量模型：BAAI/bge-small-zh-v1.5（中文小模型，本地 fastembed 推理，零外部依赖——
relay /embeddings 端点 400 坏、无 DashScope key，故走本地）。

新鲜度策略：不挂钩配件 CRUD（路径多、易漏），由 part_search 检索前对账
COUNT/MAX(updated_at)——料增改后首次检索自动触发重建（288 件全量重建秒级）。
fastembed 不可用（未装/模型下载失败）时优雅降级：返回空索引，检索退回纯词法（P0）。
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
# bge zh v1.5 检索用法：query 侧带指令前缀，文档侧裸文本（索引侧按裸文本嵌入）
_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
_REBUILD_LOCK = threading.Lock()

_model = None
_model_failed = False


def _get_model():
    """fastembed 模型懒加载单例；加载失败永久降级（不反复重试拖慢检索）。

    HF_HUB_OFFLINE=1 默认置位：模型缓存已就位时本地秒载；否则在 HF 不可达的环境里
    首次加载会挂在网络重试上几分钟才降级。要重新联网下载模型时清掉该环境变量。
    """
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    try:
        from fastembed import TextEmbedding
        _model = TextEmbedding(EMBED_MODEL)
    except Exception:
        _model_failed = True
        logger.exception("fastembed 不可用，语义检索通道降级为纯词法")
    return _model


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """批量嵌入；任何失败返回 None（调用方降级）。"""
    model = _get_model()
    if model is None or not texts:
        return None
    try:
        return [list(map(float, v)) for v in model.embed(texts)]
    except Exception:
        logger.exception("embed 失败 texts=%d", len(texts))
        return None


def embed_query(text: str) -> Optional[List[float]]:
    """检索侧单句嵌入：优先 fastembed 的 query_embed（模型自带 query 前缀），
    不支持则手工加 bge 指令前缀走 passage 嵌入。失败返回 None。"""
    model = _get_model()
    if model is None or not str(text or "").strip():
        return None
    try:
        qe = getattr(model, "query_embed", None)
        if callable(qe):
            return [list(map(float, v)) for v in qe([text])][0]
    except Exception:
        logger.exception("query_embed 失败，回退手工前缀")
    vecs = embed_texts([_QUERY_PREFIX + text]) or []
    return vecs[0] if vecs else None


def build_doc(row: dict, category: str = "") -> str:
    """料行 → 嵌入文档：类目 + 名 + 品牌 + 规格 K:V + 简介（中文模型，保留中文原文）。"""
    parts = [str(category or row.get("category") or "").strip(),
             str(row.get("model") or row.get("name") or "").strip()]
    brand = str(row.get("brand") or "").strip()
    if brand:
        parts.append(f"品牌 {brand}")
    specs = row.get("specs")
    if isinstance(specs, dict):
        parts.extend(f"{k} {v}" for k, v in specs.items()
                     if v is not None and str(v).strip())
    desc = str(row.get("short_desc") or "").strip()
    if desc:
        parts.append(desc)
    return " · ".join(p for p in parts if p)


def _content_hash(doc: str) -> str:
    return hashlib.sha256(doc.encode("utf-8")).hexdigest()[:32]


def _load_all_rows(repo) -> List[Tuple[str, dict]]:
    """全库行（类目, 行），复用检索同款取数口径。"""
    from app.services.part_selector import _category_index, _resolve_db_category, _dedupe_rows
    out: List[Tuple[str, dict]] = []
    for entry in (_category_index(repo).get("by_key") or {}).values():
        cat = str(entry.get("db_category") or "")
        if not cat:
            continue
        for r in _dedupe_rows(repo.get_by_category_with_specs(cat) or []):
            if str(r.get("model") or "").strip():
                out.append((cat, r))
    return out


def rebuild_index(repo=None, *, force: bool = False) -> dict:
    """全量重建索引（幂等）。返回统计；fastembed 不可用时 {ok: False, reason}。"""
    from app.models.kp import KPPartSearchIndex
    from app.models.base import KP_SessionLocal
    from app.repository.kp_repo import KPRepository

    owned = repo is None
    raw = repo or KPRepository()
    s = KP_SessionLocal()
    try:
        if not force:
            drift = freshness_drift(repo=raw)
            if not drift["stale"]:
                return {"ok": True, "reindexed": 0, "reason": "fresh", **drift}
        rows = _load_all_rows(raw)
        if not rows:
            return {"ok": False, "reason": "empty_library"}
        docs = [build_doc(r, cat) for cat, r in rows]
        if not force:
            # 文档没变的行不重嵌入
            existing = {i.part_id: (i.content_hash, i.embedding, i.category, i.doc_text,
                                    i.applicable, i.dim)
                        for i in s.query(KPPartSearchIndex).all()}
        else:
            existing = {}
        need_idx = [k for k, (cat, r) in enumerate(rows)
                    if str(r.get("id")) and existing.get(int(r["id"]), (None,))[0] != _content_hash(docs[k])]
        if need_idx:
            vecs = embed_texts([docs[k] for k in need_idx])
            if vecs is None:
                return {"ok": False, "reason": "embed_unavailable"}
        else:
            vecs = []
        import json
        import datetime as _dt
        now = _dt.datetime.utcnow()
        vi = 0
        seen_part_ids = set()
        for k, (cat, r) in enumerate(rows):
            pid = int(r["id"])
            seen_part_ids.add(pid)
            row = s.query(KPPartSearchIndex).filter(KPPartSearchIndex.part_id == pid).first()
            if k in need_idx:
                vec = vecs[vi]; vi += 1
                fields = dict(category=cat, doc_text=docs[k], embedding=vec,
                              applicable=r.get("applicable"), model_name=EMBED_MODEL,
                              dim=len(vec), content_hash=_content_hash(docs[k]), updated_at=now)
                if row:
                    for kk, vv in fields.items():
                        setattr(row, kk, vv)
                else:
                    s.add(KPPartSearchIndex(part_id=pid, **fields))
            elif row:
                row.category = cat
                row.updated_at = now
        # 配件已删 → 索引行清理
        for stale in s.query(KPPartSearchIndex).all():
            if stale.part_id not in seen_part_ids:
                s.delete(stale)
        s.commit()
        _cache["ts"] = 0.0  # 失效内存缓存
        return {"ok": True, "reindexed": len(need_idx), "total": len(rows)}
    finally:
        s.close()
        if owned:
            raw.close()


def freshness_drift(repo=None) -> dict:
    """对账：配件数 vs 索引数、配件 MAX(updated_at) vs 索引 MAX(updated_at)。"""
    from sqlalchemy import text
    from app.models.base import kp_engine
    with kp_engine.connect() as c:
        p_cnt, p_max = c.execute(text(
            "SELECT COUNT(*), COALESCE(MAX(updated_at), 'epoch') FROM kp.kp_parts")).one()
        i_cnt, i_max = c.execute(text(
            "SELECT COUNT(*), COALESCE(MAX(updated_at), 'epoch') FROM kp.kp_part_search_index")).one()
    stale = (p_cnt != i_cnt) or (p_max is not None and i_max is not None and p_max > i_max)
    return {"stale": bool(stale), "parts": p_cnt, "indexed": i_cnt,
            "parts_max": str(p_max), "index_max": str(i_max)}


# ── 内存缓存（进程内；TTL 秒级即可——重建由新鲜度对账触发，不靠 TTL 兜正确性） ──

_cache: Dict[str, object] = {"ts": 0.0, "rows": []}
_CACHE_TTL = 120.0


def load_vectors(*, force: bool = False) -> List[dict]:
    """[{part_id, category, embedding, applicable}]，带 TTL 缓存。"""
    now = time.time()
    if not force and _cache["rows"] and now - float(_cache["ts"]) < _CACHE_TTL:
        return _cache["rows"]
    from app.models.kp import KPPartSearchIndex
    from app.models.base import KP_SessionLocal
    s = KP_SessionLocal()
    try:
        rows = [{"part_id": i.part_id, "category": i.category,
                 "embedding": i.embedding, "applicable": i.applicable}
                for i in s.query(KPPartSearchIndex).all() if i.embedding]
        _cache["rows"] = rows
        _cache["ts"] = now
        return rows
    finally:
        s.close()


def semantic_available() -> bool:
    return _get_model() is not None


def ensure_index(repo=None) -> dict:
    """检索入口用：新鲜度对账 + 必要时重建（进程级互斥，防并发重复嵌入）。"""
    drift = freshness_drift()
    if not drift["stale"]:
        return {"ok": True, "reindexed": 0, **drift}
    with _REBUILD_LOCK:
        drift = freshness_drift()  # double-check：拿锁前别人可能已重建
        if not drift["stale"]:
            return {"ok": True, "reindexed": 0, **drift}
        return rebuild_index(repo=repo)
