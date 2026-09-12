# -*- coding: utf-8 -*-
"""配件检索召回层（part_selector 拆分，2026-09-11）：类目解析 + 候选池 + 别名。

只做「从 KP 库按事实召回」，不预判选型结果；命中/未命中都白盒交回。
"""
from __future__ import annotations

from typing import Optional
import logging
logger = logging.getLogger(__name__)

from app.services.part_row_identity import _norm_cat_key, kp_row_key
from app.services.part_specs import _SeriesScopedRepo, kp_repository


def _row_search_hits(repo, db_cat: str, desc: str, search_terms: Optional[list] = None) -> list:
    """行检索：全描述优先；零命中 → 用结构化 need 里的 model/vendor 词检索。

    不再用正则从需求原文抠 token（中文规格/型号词抠不出）：客户点名的型号（如
    「兆芯50000」→ KH50000 96C）由模型在 need 里给出 model/vendor，引擎按该词去库检索，
    让精确件浮到候选池前部。"""
    try:
        hits = _dedupe_rows(repo.get_by_category(db_cat, search=desc) or []) if desc else []
    except Exception:
        hits = []
    if hits:
        return hits
    for term in (search_terms or []):
        t = str(term or "").strip()
        if not t:
            continue
        try:
            h = _dedupe_rows(repo.get_by_category(db_cat, search=t) or [])
        except Exception:
            h = []
        if h:
            return h
    return hits


def kp_candidate_pools(parts: list, series: str = "", limit: int = 20,
                       search_first: bool = True, series_adapt: bool = True) -> dict:
    """未匹配部件行 → 每行候选池（KP 库事实源；引擎只检索，AI 才做语义选型）。

    候选 = 该行类目下「系列适配」过滤后的在售件（名称检索命中的排前面），池满截断
    带 truncated 标记（白盒：不静默截断）。类目不在配件库 → 空池 + 原因，交 AI 如实
    向客户说明，绝不编造料号。
    search_first=False → 不做检索排序（类目全量直出）；series_adapt=False → 不按机型
    系列过滤（=kp_library_full 对照数据源，验证"换插头行为可观测"）。
    """
    raw_repo = kp_repository()
    repo = _SeriesScopedRepo(raw_repo, series) if series_adapt else raw_repo
    try:
        index = _category_index(repo)
        cache: dict = {}
        out: dict = {}
        for p in parts or []:
            if not isinstance(p, dict) or not p.get("unmatched"):
                continue
            cat = str(p.get("category") or "").strip()
            if not cat:
                continue
            desc = str(p.get("request_spec") or "").strip() or cat
            key = kp_row_key(cat, desc)
            if key in out:
                continue
            row_view = {"category": cat, "description": desc, "qty": p.get("qty") or 1}
            db_cat = _resolve_db_category(cat, index)
            if not db_cat:
                out[key] = {"row": row_view, "candidates": [], "reason": "类目不在配件库"}
                continue
            if db_cat not in cache:
                hits: list = []
                if search_first:
                    hits = _row_search_hits(repo, db_cat, desc, [])
                hit_ids = {str(r.get("id")) for r in hits}
                # 全量列表带 specs（性能/容量语义在规格里，大脑按需求语义选件靠它；
                # 只按名称猜是"半智能"的根因之一，2026-09-06 起 specs 下行）
                full = _dedupe_rows(repo.get_by_category_with_specs(db_cat) or [])
                spec_by_id = {str(r.get("id")): r.get("specs")
                              for r in full if isinstance(r.get("specs"), dict)}
                merged = []
                for r in hits + [x for x in full if str(x.get("id")) not in hit_ids]:
                    rr = dict(r)
                    if not isinstance(rr.get("specs"), dict):
                        rr["specs"] = spec_by_id.get(str(rr.get("id")))
                    merged.append(rr)
                cache[db_cat] = merged
            cands = []
            for r in cache[db_cat]:
                model = str(r.get("model") or "").strip()
                if not model:
                    continue
                item = {
                    "part_id": str(r.get("id") or ""),
                    "name": model,
                    "price": float(r.get("price") or 0),
                    "currency": str(r.get("currency") or "RMB"),
                }
                specs = r.get("specs")
                if isinstance(specs, dict):
                    trimmed = {str(k): str(v)[:40] for k, v in list(specs.items())[:12]
                               if str(v or "").strip()}
                    if trimmed:
                        item["specs"] = trimmed
                cands.append(item)
            out[key] = {
                "row": row_view,
                "candidates": cands[:limit],
                "truncated": len(cands) > limit,
            }
        return out
    finally:
        raw_repo.close()


# ── 候选池数据源注册表（2026-09-06 插头化）：契约最小集 = 每行
# {row, candidates:[{part_id, name, …自由字段}], truncated}——part_id+name 是
# select_kp_parts 接地必需，其余字段自由透传（新数据源多给交期/库存即自动下行）。
def _kp_candidate_pools_full(parts: list, series: str = "", limit: int = 20) -> dict:
    """对照数据源：KP 库类目全量——无系列适配、无检索排序（验证换源行为可观测）。"""
    return kp_candidate_pools(parts, series="", limit=limit, search_first=False,
                              series_adapt=False)


def _kp_row_recall_pools(parts: list, series: str = "", limit: int = 30) -> dict:
    """行描述召回数据源：每行按 request_spec 的型号数字段/容量/混合词（DDR5/9361）OR 召回。

    零召回=空池+如实原因，绝不退化类目全量（全量池曾把兆芯行推成 AMD 池、
    DDR4 混进 DDR5 池——2026-09-07 实测）。候选形状与 kp_candidate_pools 对齐。"""
    from app.services.data_tools import part_recall
    out: dict = {}
    for p in parts or []:
        if not (isinstance(p, dict) and p.get("unmatched")):
            continue
        cat = str(p.get("category") or "").strip()
        desc = str(p.get("request_spec") or "").strip() or cat
        key = kp_row_key(cat, desc)
        if key in out:
            continue
        row_view = {"category": cat, "description": desc, "qty": p.get("qty") or 1}
        q = part_recall(cat, desc=desc, series=series, limit=limit)
        cands: list = []
        for c in (q.get("rows") or []) if q.get("ok") else []:
            if not isinstance(c, dict) or not str(c.get("name") or "").strip():
                continue
            item = dict(c)
            item["pn"] = str(c.get("name") or "")
            item["unit_price"] = c.get("price")
            item["desc"] = " · ".join(f"{k}:{v}" for k, v in (c.get("specs") or {}).items())
            cands.append(item)
        out[key] = {"row": row_view, "candidates": cands,
                    "reason": "" if cands else "库内无精确匹配（按行描述召回零命中）"}
    return out


CANDIDATE_RESOLVERS = {
    "row_recall": {
        "fn": _kp_row_recall_pools,
        "description": "KP 库 · 行描述召回（型号/容量/混合词 OR，零召回=空池明示）",
    },
    "category_series_search": {
        "fn": kp_candidate_pools,
        "description": "KP 库 · 类目×系列适配×检索排序（旧行为）",
    },
    "kp_library_full": {
        "fn": _kp_candidate_pools_full,
        "description": "KP 库 · 类目全量（无系列适配、无检索排序，对照用）",
    },
}
DEFAULT_RESOLVER = "row_recall"


def resolve_kp_pools(binding: dict, parts: list, series: str = "",
                     default_limit: int = 20) -> tuple:
    """按节点 data_bindings 解析候选池。返回 (pools, source_label)。

    契约：binding={source, resolver, params{limit}}；未知 resolver 白盒回落默认并提示。
    """
    b = binding if isinstance(binding, dict) else {}
    resolver = str(b.get("resolver") or DEFAULT_RESOLVER)
    params = b.get("params") if isinstance(b.get("params"), dict) else {}
    try:
        limit = max(1, min(80, int(params.get("limit") or default_limit)))
    except (TypeError, ValueError):
        limit = default_limit
    entry = CANDIDATE_RESOLVERS.get(resolver)
    if entry is None:
        logger.warning("未知候选池 resolver=%s，回落 %s", resolver, DEFAULT_RESOLVER)
        resolver = DEFAULT_RESOLVER
        entry = CANDIDATE_RESOLVERS[DEFAULT_RESOLVER]
    return entry["fn"](parts, series=series, limit=limit), f"kp_library/{resolver}"


_ALIAS_CACHE: dict = {"at": 0.0, "map": {}}


def _category_aliases() -> dict:
    """类目别名词表（DB：rules.system_config.kp_category_aliases，alias→库内真实类目）。

    词表属业务内容归 DB（铁律③），读侧 60s 进程缓存；键缺失/读失败 = 无别名，行为同旧版。
    """
    import time as _time
    now = _time.monotonic()
    if now - _ALIAS_CACHE["at"] < 60:
        return _ALIAS_CACHE["map"]
    mp: dict = {}
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            val = repo.get_value("kp_category_aliases")
        finally:
            repo.close()
        if isinstance(val, dict):
            mp = {str(k).strip().lower(): str(v).strip()
                  for k, v in val.items() if str(k).strip() and str(v).strip()}
    except Exception:
        mp = {}
    _ALIAS_CACHE["at"] = now
    _ALIAS_CACHE["map"] = mp
    return mp


def resolve_kp_category(raw: str) -> Optional[str]:
    """把任意写法（中文/分隔符差异）解析为配件库现行 canonical 类目名；无法唯一解析返回 None。

    数据驱动：库类目 = kp_categories（live），别名词表 = system_config.kp_category_aliases（live）。
    只做「对齐到库名」，不新增/幻造类目；分隔符 / - _ 空格 等价。改库/改别名此处自动跟随。
    """
    name = (raw or '').strip()
    if not name:
        return None
    nk = _norm_cat_key(name)
    try:
        from app.services.requirement_slots import _load_kp_categories
        cats = [str(c).strip() for c in (_load_kp_categories() or []) if str(c).strip()]
    except Exception:
        cats = []
    cats_norm = {_norm_cat_key(c): c for c in cats}
    # 1) 库名精确（含分隔符等价）：HDD SSD → HDD/SSD
    if nk in cats_norm:
        return cats_norm[nk]
    # 2) 别名精确：网卡 → NIC、内存 → Memory、RAID卡 → Raid card
    for alias, dbcat in _category_aliases().items():
        if _norm_cat_key(alias) == nk:
            return dbcat
    # 3) 唯一子串命中（库名/别名），避免乱猜：Raid 卡/千兆卡 等带后缀写法
    matches: list = []
    for c in cats:
        ck = _norm_cat_key(c)
        if ck and (ck in nk or nk in ck) and c not in matches:
            matches.append(c)
    if len(matches) == 1:
        return matches[0]
    return None


def _category_index(repo):
    """构建真实配件类目索引（键=库内真实类目；别名来自 DB 词表 kp_category_aliases）。"""
    db = {}
    for r in repo.get_categories():
        c = str(r.get("category") or "").strip()
        if c:
            db[c.lower()] = {"db_category": c, "count": int(r.get("count") or 0)}
    by_key = {}
    for c in db.values():
        by_key[c["db_category"]] = {
            "key": c["db_category"],
            "db_category": c["db_category"],
            "count": c["count"],
            "aliases": [],
        }
    # DB 别名词表挂到索引（登记类目词如 网卡/硬盘/内存 → NIC/HDD-SSD/Memory）
    cat_lower = {k.lower(): k for k in by_key}
    for alias_low, dbcat in _category_aliases().items():
        real = cat_lower.get(str(dbcat).lower())
        if real and alias_low not in [a.lower() for a in by_key[real]["aliases"]]:
            by_key[real]["aliases"].append(alias_low)
    return {"by_key": by_key, "db_lower": set(db.keys())}

def list_kp_categories():
    """返回真实配件类目（规则键 + 库类目 + 数量），供 AI 查真实类目而非猜词。"""
    repo = kp_repository()
    try:
        index = _category_index(repo)
        return [dict(e) for e in index["by_key"].values()]
    finally:
        repo.close()

def _search_category_names(repo, index):
    return [info["db_category"] for info in index["by_key"].values() if info.get("db_category")]

def _dedupe_rows(rows):
    out = []
    seen = set()
    for r in rows or []:
        key = (str(r.get("category") or ""), str(r.get("model") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def resolve_part_alias(term, category=None):
    """自由术语 → 目录候选（仅名称检索；别名/模型 token 等语义判断一律交由 AI 角色）。
    返回库内真实候选，不做静默顶替，不编造料号。"""
    repo = kp_repository()
    try:
        index = _category_index(repo)
        db_cat = _resolve_db_category(category, index) if category else None
        term = str(term or "").strip()
        rows = []
        if db_cat:
            rows = repo.get_by_category(db_cat, search=term)
        else:
            for c in _search_category_names(repo, index):
                rows.extend(repo.get_by_category(c, search=term))
        rows = _dedupe_rows(rows)
        out = []
        for r in rows:
            out.append({
                "category": r.get("category") or "",
                "pn": r.get("model") or "",
                "name": r.get("model") or "",
                "unit_price": float(r.get("price") or 0),
                "currency": r.get("currency") or "RMB",
                "reason": "名称检索",
            })
        return {"count": len(out), "candidates": out[:10], "reason": "名称检索"}
    finally:
        repo.close()

def _candidate_desc(c: dict) -> str:
    """把候选的规格字典压成一行可读能力描述，供 AI 做语义匹配（非词表穷举）。"""
    model = str(c.get("model") or c.get("pn") or "").strip()
    specs = c.get("specs")
    bits = [model]
    if isinstance(specs, dict):
        for k, v in specs.items():
            if v in (None, "", []):
                continue
            bits.append(f"{k}:{v}")
    elif isinstance(specs, list):
        for item in specs:
            if isinstance(item, dict):
                for k, v in item.items():
                    if v not in (None, "", []):
                        bits.append(f"{k}:{v}")
    return "；".join(b for b in bits if b)

def retrieve_part_candidates(categories=None, server_type_name: str = "", series: str = "",
                             signals: Optional[dict] = None) -> dict:
    """按类目从 KP 库检索候选配件（只检索、不做语义/别名/规格匹配）。

    候选=库内真实件：id/model/desc(可读能力)/specs/price/applicable。series 只在候选池过滤，
    不参与型号/规格匹配。返回 {db_category: [candidate, ...]}；类目来自 categories 或
    signals（cpu/memory/storage/gpu/raid/nic）。
    """
    raw = kp_repository()
    try:
        repo = _SeriesScopedRepo(raw, series)
        index = _category_index(repo)
        db_cats: list = []

        def _add(raw_cat: str) -> None:
            dbc = _resolve_db_category(str(raw_cat), index)
            if dbc and dbc not in db_cats:
                db_cats.append(dbc)

        for c in (categories or []):
            _add(c)
        sig = signals or {}
        _exists = lambda v: isinstance(v, (list, dict)) and len(v) > 0
        if _exists(sig.get("cpu")):
            _add("CPU")
        if _exists(sig.get("memory")):
            _add("Memory")
        if _exists(sig.get("storage")):
            _add("HDD/SSD")
        if _exists(sig.get("gpu")):
            _add("GPU")
        if _exists(sig.get("raid")):
            _add("Raid card")
        if _exists(sig.get("nic")):
            _add("NIC")
        out: dict = {}
        for dbc in db_cats:
            rows = repo.get_by_category_with_specs(dbc) or []
            cands = []
            for r in rows:
                cand = dict(r)
                cand["pn"] = str(cand.get("model") or "")
                cand["name"] = str(cand.get("model") or "")
                cand["unit_price"] = float(cand.get("price") or 0)
                cand["desc"] = _candidate_desc(cand)
                cands.append(cand)
            out[dbc] = cands
        return out
    finally:
        raw.close()

def _resolve_db_category(need_cat, index):
    n = str(need_cat or "").strip()
    if not n:
        return None
    nl = n.lower()
    if nl in index["db_lower"]:
        return n
    if nl in index["by_key"]:
        return index["by_key"][nl]["db_category"]
    for e in index["by_key"].values():
        if any(a.lower() == nl for a in e["aliases"]):
            return e["db_category"]
    for e in index["by_key"].values():
        kl = e["key"].lower()
        if kl and (kl in nl or nl in kl):
            return e["db_category"]
        if any(a.lower() and (a.lower() in nl or nl in a.lower()) for a in e["aliases"]):
            return e["db_category"]
    return None
