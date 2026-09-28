# -*- coding: utf-8 -*-
"""同事记忆相关性检索（2026-09-13 P0-①）：本地向量召回替代「最新 N 条」注入。

- 复用 part_search_index 的 fastembed 单例（BAAI/bge-small-zh-v1.5，中文记忆适用），
  不另起模型；fastembed 不可用/嵌入失败 → 返回 None，调用方回退最新序（detect-and-degrade）。
- 进程内缓存按 (memory_id, content_hash) 漂移对账：内容没变的条目不重复嵌入；
  记忆每角色上限 100 条（enforce_cap），首_role 首次全量嵌入毫秒级，无需落库索引表。
"""
from __future__ import annotations

import hashlib
import logging
import math
import threading
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# role_key -> {memory_id: (content_hash, vec)}
_CACHE: Dict[str, Dict[int, Tuple[str, List[float]]]] = {}


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def rank_by_relevance(role_key: str, rows: List[dict], query: str,
                      top_k: int) -> Optional[List[dict]]:
    """非置顶记忆按与 query 的余弦相似度排序取 top_k。

    返回 None 表示语义通道不可用（调用方回退最新序）；rows 为空返回 []。
    """
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows or not str(query or "").strip() or top_k <= 0:
        return [] if rows else None
    try:
        from app.services.part_search_index import embed_query, embed_texts
        qvec = embed_query(str(query).strip())
        if qvec is None:
            return None
        with _LOCK:
            cached = dict(_CACHE.get(role_key) or {})
        missing, fresh = [], dict(cached)
        texts = []
        for r in rows:
            content = str(r.get("content") or "").strip()
            h = _content_hash(content)
            entry = cached.get(int(r["id"]))
            if entry and entry[0] == h:
                continue
            missing.append((int(r["id"]), content, h))
            texts.append(content)
        if missing:
            vecs = embed_texts(texts)
            if vecs is None:
                return None
            for (mid, _content, h), vec in zip(missing, vecs):
                fresh[mid] = (h, vec)
            with _LOCK:
                _CACHE[role_key] = fresh
        scored = []
        for r in rows:
            entry = fresh.get(int(r["id"]))
            if not entry:
                continue
            scored.append((_cosine(qvec, entry[1]), r))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [r for _score, r in scored[:top_k]]
    except Exception:
        logger.exception("记忆相关性排序失败 role=%s（回退最新序）", role_key)
        return None
