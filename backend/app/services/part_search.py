# -*- coding: utf-8 -*-
"""平台级混合配件检索（2026-09-12 P1）：词法（P0 加权引擎）+ 语义（本地向量）→ RRF 融合。

行业对齐：OpenAI File Search / 2025-26 RAG 共识形态 = 关键词 + 向量混合 + 融合排序，
纯向量在精确标识符（料号/型号）上系统性弱——所以词法通道保持强（P0），语义只补
「词形对不上」的长尾（口语/同义改写）。每条候选带 match 溯源（lexical/semantic:sim），
AI 能看见「为什么命中」；fastembed 不可用或索引空时整体退化为纯词法（行为=P0）。

入口：hybrid_search（mode=query 给 query_parts 工具；mode=recall 给行批量召回）。
part_query/part_recall 公共契约不变——assistant 等直连调用方继续走纯词法。
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List

from app.services.data_tools import _load_aliases
from app.services.part_lexicon import (_gb_of, build_row_blob, extract_query_tokens,
                                       passes_discriminators, score_row)

logger = logging.getLogger(__name__)

_RRF_K = 60
_LEX_CAP = 50        # 词法通道参与融合的候选上限
_SEM_CAP = 30        # 语义通道候选上限
_SEM_MIN_SIM = 0.45  # 语义召回下限（bge-small-zh 类内余弦；低于它视为弱相关噪音）
_CAP_TOL = 0.01      # 容量等值容差 ±1%（与词法通道同标准）


def hybrid_search(category, *, text: str = "", spec_filters=None, series: str = "",
                  limit: int = 8, offset: int = 0, price_ok: bool = True,
                  mode: str = "query", _repo=None) -> dict:
    """词法+语义混合检索。返回形状兼容 part_query（rows/total/truncated/spec_keys/
    note/next_offset/scope 真话），rows 每项多一个 match 列表（命中通道溯源）。

    mode=query：text 作关键词（AND 收窄语义，配 spec_filters）；mode=recall：text 作
    行描述（OR 召回语义）。两者现共用同一词法引擎，mode 只影响返回 note 的措辞来源。
    """
    from app.repository.kp_repo import KPRepository, _spec_match_all
    from app.services.part_selector import (_category_index, _resolve_db_category,
                                            _dedupe_rows, _SeriesScopedRepo)
    from app.services import part_search_index as psi
    from app.services.part_specs import _series_ok

    cat = str(category or "").strip()
    if not cat:
        return {"ok": False, "error": "invalid_args", "message": "category 必填"}
    text = str(text or "").strip()
    try:
        limit = max(1, min(50, int(limit or 8)))
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        limit, offset = 8, 0
    raw = _repo or KPRepository()
    owned = _repo is None
    try:
        repo = _SeriesScopedRepo(raw, series) if series else raw
        db_cat = _resolve_db_category(cat, _category_index(repo))
        if not db_cat:
            return {"ok": False, "error": "unknown_category",
                    "message": f"类目 {cat} 不在配件库（可用 list_kp_categories 查真实类目）"}
        rows = _dedupe_rows(repo.get_by_category_with_specs(db_cat) or [])
        spec_key_set: set = set()
        for r in rows:
            sp = r.get("specs")
            if isinstance(sp, dict):
                spec_key_set.update(str(k) for k in sp)
        spec_keys = sorted(spec_key_set)

        # 规格过滤（与 part_query 同语义：确定性 AND + 键归一解析）
        import re as _re
        parsed: list = []
        for f in spec_filters or []:
            f = f if isinstance(f, dict) else {}
            sk = str(f.get("spec_key") or "").strip()
            if sk:
                parsed.append((sk, str(f.get("op") or "=").strip(), f.get("value")))
        if parsed:
            _norm = lambda k: _re.sub(r"\s+", "", str(k)).lower()
            _nmap = {_norm(k): k for k in spec_key_set}
            parsed = [(_nmap.get(_norm(sk), sk), op, val) for sk, op, val in parsed]
            rows = [r for r in rows if _spec_match_all(r.get("specs") or {}, parsed)]

        # ── 通道 1：词法（P0 引擎） ──
        aliases = _load_aliases(raw)
        tokens = extract_query_tokens(text, aliases) if text else None
        lex_ranked: List[dict] = []  # [{row, kinds}]
        rows_by_id: Dict[int, dict] = {}
        for r in rows:
            name, blob = build_row_blob(r)
            pid = str(r.get("id") or "")
            if pid:
                rows_by_id[int(pid)] = r
            if not text or not name:
                continue
            if not passes_discriminators(tokens, blob):
                continue
            sc, kinds = score_row(tokens, r, row_name=name, row_blob=blob)
            if sc > 0:
                lex_ranked.append({"row": r, "kinds": kinds, "score": sc})
        lex_ranked.sort(key=lambda x: -x["score"])
        lex_ranked = lex_ranked[:_LEX_CAP]

        # ── 通道 2：语义（本地向量；不可用/无文本即跳过） ──
        sem_ids: List[int] = []
        sem_sims: Dict[int, float] = {}
        if text and psi.semantic_available():
            try:
                ensure = psi.ensure_index(repo=raw)
                if ensure.get("ok"):
                    pool = [v for v in psi.load_vectors()
                            if v.get("category") == db_cat
                            and _series_ok(v.get("applicable"), series)]
                    if pool:
                        q = psi.embed_query(text)
                        if q:
                            qn = math.sqrt(sum(x * x for x in q)) or 1.0
                            # 容量是硬信号：查询点名容量、行声明容量且差超 ±1% → 语义不许
                            # 压过它（实测病灶：「2T固态」被语义把 480G 排到第一、
                            # 「HBM3e 141G」无料场景被误报成 72G 显卡）。行未声明容量 → 不臆造过滤。
                            q_cap = tokens["capacity_gb"] if tokens else None
                            sims = []
                            for v in pool:
                                e = v["embedding"] or []
                                if not e or len(e) != len(q):
                                    continue
                                dot = sum(a * b for a, b in zip(q, e))
                                en = math.sqrt(sum(x * x for x in e)) or 1.0
                                s = dot / (qn * en)
                                if s < _SEM_MIN_SIM:
                                    continue
                                if q_cap is not None:
                                    r = rows_by_id.get(int(v["part_id"]))
                                    if r is not None:
                                        _n, _b = build_row_blob(r)
                                        row_cap = _gb_of(_n + " " + _b)
                                        if row_cap is not None and abs(row_cap - q_cap) > q_cap * _CAP_TOL:
                                            continue
                                sims.append((int(v["part_id"]), s))
                            sims.sort(key=lambda x: -x[1])
                            sem_ids = [pid for pid, _ in sims[:_SEM_CAP]]
                            sem_sims = {pid: s for pid, s in sims[:_SEM_CAP]}
            except Exception:
                logger.exception("语义通道异常，降级纯词法 category=%s", cat)

        # ── RRF 融合（无关键词 = 浏览模式：仅规格过滤后的全量行，与 part_query 同语义） ──
        fused: Dict[int, float] = {}
        match_of: Dict[int, List[str]] = {}
        for rank, item in enumerate(lex_ranked):
            pid = int(item["row"]["id"])
            fused[pid] = fused.get(pid, 0.0) + 1.0 / (_RRF_K + rank + 1)
            match_of.setdefault(pid, []).append("lexical")
        for rank, pid in enumerate(sem_ids):
            fused[pid] = fused.get(pid, 0.0) + 1.0 / (_RRF_K + rank + 1)
            match_of.setdefault(pid, []).append(f"semantic:{sem_sims[pid]:.2f}")
        # 只在词法通道的行集或语义池内取料；语义独有行须在当前类目行集里找得到
        if text:
            ordered = sorted(fused.items(), key=lambda x: -x[1])
        else:
            ordered = [(int(r["id"]), 0.0) for r in rows
                       if str(r.get("id") or "").strip()]
        out: List[dict] = []
        for pid, f in ordered:
            r = rows_by_id.get(pid)
            if r is None:
                continue  # 语义池命中但行不在当前作用域（系列过滤后）——跳过
            item = {"part_id": str(pid),
                    "name": str(r.get("model") or ""),
                    "price": float(r.get("price") or 0),
                    "currency": str(r.get("currency") or "RMB"),
                    "match": match_of.get(pid, [])}
            specs = r.get("specs") if isinstance(r.get("specs"), dict) else {}
            if specs:
                item["specs"] = dict(specs)
            app = r.get("applicable") or {}
            if isinstance(app, dict):
                item["applicable_series"] = app.get("series")
            if not price_ok:
                item.pop("price", None)
            if item["name"]:
                out.append(item)
        total = len(out)
        page = out[offset:offset + limit]
        note = None
        if total == 0 and (text or parsed):
            note = (f"未命中候选（关键词「{text or '(无)'}」或规格过滤过严）。"
                    "库内该类目 specs 字段：" + ("、".join(spec_keys[:10]) if spec_keys else "无") +
                    "。可用数值/型号词（1G/10G/DDR5/6T）、口语词（万兆/千兆/固态）或 required_specs 收窄重查。")
        res = {"ok": True, "category": cat, "db_category": db_cat,
               "source": "part_search/hybrid", "mode": mode,
               "rows": page, "total": total,
               "truncated": total > offset + len(page),
               "spec_keys": spec_keys, "note": note,
               "offset": offset,
               "next_offset": (offset + len(page) if total > offset + len(page) else None),
               "channels": {"lexical": len(lex_ranked), "semantic": len(sem_ids)}}
        if not out:
            from app.services.data_tools import _scope_blocked
            res.update(_scope_blocked(
                lambda: hybrid_search(cat, text=text, spec_filters=spec_filters, series="",
                                      limit=5, offset=0, price_ok=price_ok, mode=mode,
                                      _repo=raw),
                series))
        return res
    finally:
        if owned:
            raw.close()
