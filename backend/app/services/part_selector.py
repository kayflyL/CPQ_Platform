# -*- coding: utf-8 -*-
"""part_selector —— 需求分析 skill 的唯一配件选型工具（AI 决策，工具落地）。

AI-first 原则：
- AI 决定“要什么/怎么配”：cpu/memory/storage/gpu/raid/
  nic 是唯一真值源（llm_extract_enhance 产出，slot_contract 对齐）。
  AI 在调用 select_parts 前补全模糊项（内存拆条、硬盘接口、GPU 型号等）。
- 工具只做“检索 + 落地”：料号/价格/规格全部来自 KP 库真实返回；未命中白盒 unmatched，
  绝不静默回退固定规则。
- 类目直接取 KP 库真实类目，规则词不再来自规则目录；场景包等规则驱动项已移除。
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)
from typing import Optional

from app.repository.kp_repo import KPRepository

def _placeholder(db_cat, qty, want):
    """确定性占位缺口行：把客户登记的需求原样呈现给 AI 选型，引擎不做预测。"""
    return _row(db_cat, None, int(qty or 1), unmatched=True,
                reason="交由 AI 语义选型（引擎仅检索候选、不预判）",
                request_spec=str(want or ""))


def kp_rows_present(ext) -> bool:
    """登记表是否已登记部件（kp_rows 里有带类别或描述的部件行）。"""
    kp = (ext or {}).get("kp_rows")
    return isinstance(kp, list) and any(
        isinstance(r, dict) and (
            str(r.get("part_category") or r.get("category") or "").strip()
            or str(r.get("description") or "").strip())
        for r in kp)


def kp_rows_slot_keys(ext) -> set:
    """登记表 kp_rows 已覆盖的归一部件槽位（cpu/memory/storage/...），按 kp_slot_group_map 映射。"""
    try:
        from app.services.requirement_slots import _load_kp_slot_map
        m = _load_kp_slot_map()
    except Exception:
        m = {}
    rev: dict[str, set] = {}
    for cat, rule in (m or {}).items():
        if not isinstance(rule, dict):
            continue
        key = str(rule.get("key") or "").strip()
        if key:
            rev.setdefault(key, set()).add(str(cat))
    out: set = set()
    kp = (ext or {}).get("kp_rows")
    for r in kp or []:
        if not isinstance(r, dict):
            continue
        cat = str(r.get("part_category") or r.get("category") or "").strip()
        if not cat:
            continue
        for key, cats in rev.items():
            if cat in cats:
                out.add(key)
    return out


def requirement_rows_to_parts(kp_rows) -> list:
    """登记表部件行 → 待选型占位部件行（category/description/qty，交由下游 AI 落真实 SKU）。"""
    out = []
    for r in kp_rows or []:
        if not isinstance(r, dict):
            continue
        cat = str(r.get("part_category") or r.get("category") or "").strip()
        desc = str(r.get("description") or r.get("catalogue") or "").strip()
        try:
            qty = int(float(r.get("qty", 1) or 1))
        except (TypeError, ValueError):
            qty = 1
        if not cat:
            continue
        out.append(_placeholder(cat, qty, desc or cat))
    return out


def config_rows_to_parts(kp_config) -> list:
    """AI 声明的配置行（ext.kp_config：[{category, spec|description, qty}]）→ 待选型占位行。

    这是「AI=配置器 自己决定配什么」的落地载体：大脑决定要配某个类目（如 HBA/Bridge）
    就把行登记进 kp_config，下游按占位行走 search/select 或 ask_user，绝不静默丢类目。
    """
    out = []
    for r in kp_config or []:
        if not isinstance(r, dict):
            continue
        cat = str(r.get("category") or "").strip()
        if not cat:
            continue
        desc = str(r.get("spec") or r.get("description") or "").strip()
        try:
            qty = int(float(r.get("qty", 1) or 1))
        except (TypeError, ValueError):
            qty = 1
        out.append(_placeholder(cat, qty, desc or cat))
    return out


def ensure_pick_rows(parts: list, picks: dict, dup_ok: bool = False) -> list:
    """给 ext.kp_picks 里尚不存在的行键补占位行（按 类目|描述 解析），确保 apply 能落地。"""
    have = {kp_row_key(str(p.get("category") or ""), str(p.get("request_spec") or "").strip() or str(p.get("category") or ""))
            for p in parts if isinstance(p, dict)}
    for key in (picks or {}):
        k = str(key or "")
        if k in have:
            continue
        if "|" in k:
            cat, desc = (k.split("|", 1) + [""])[:2]
        else:
            cat, desc = k, k
        cat = str(cat).strip()
        if cat:
            parts.append(_placeholder(cat, 1, str(desc).strip() or cat))
    return parts


def kp_row_key(category: str, request_spec: str) -> str:
    """部件行键 = 类目|描述。ext.kp_picks 与候选池共用：客户改过该行（类目/描述变了）
    键即失配，旧 pick 自动作废，下一回合重新选型。"""
    cat = str(category or "").strip()
    desc = str(request_spec or "").strip() or cat
    return f"{cat}|{desc}"


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
    raw_repo = KPRepository()
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


def apply_kp_picks(parts: list, picks: dict) -> tuple:
    """把 AI 选定（ext.kp_picks：行键 → {name, price, currency, reason[, qty][, substitute]}）应用到占位行。

    快照语义：选定时的名称/价格随 pick 落行（价格随行市波动，跨轮以 pick 时的库内
    价为准，同 BOM 快照）。行键失配（客户改行）自动跳过。返回 (新列表, 应用行数)。
    qty：大脑组合申报（如 768G=64G×12）覆盖行数量；substitute：近替代申报 → 行打
    spec_mismatch ⚠️ 白盒标记，grounded_spec 前缀替代说明。
    """
    out, applied = [], 0
    for p in parts or []:
        if not (isinstance(p, dict) and p.get("unmatched")):
            out.append(p)
            continue
        cat = str(p.get("category") or "").strip()
        desc = str(p.get("request_spec") or "").strip() or cat
        pick = (picks or {}).get(kp_row_key(cat, desc))
        if not isinstance(pick, dict) or not str(pick.get("name") or "").strip():
            out.append(p)
            continue
        reason = str(pick.get("reason") or "").strip()
        try:
            pick_qty = int(pick.get("qty"))
        except (TypeError, ValueError):
            pick_qty = 0
        substitute = bool(pick.get("substitute"))
        grounded = ("AI 从候选池选定：" + reason) if reason else "AI 从候选池选定"
        if substitute:
            grounded = ("⚠️ 替代申报：" + (reason or "近替代") + "；" + grounded) if reason \
                else "⚠️ 替代申报（近替代，无精确匹配）"
        out.append(_row(
            cat,
            {"model": pick.get("name"), "price": pick.get("price"), "currency": pick.get("currency")},
            pick_qty if pick_qty >= 1 else (p.get("qty") or 1),
            matched_spec="AI 选定",
            request_spec=p.get("request_spec") or "",
            grounded_spec=grounded,
            spec_mismatch=substitute,
        ))
        applied += 1
    return out, applied

def _capacity_mismatch(grounded_cap: Optional[float], need_cap: Optional[float],
                       cmp: str, tolerance_ratio: float) -> bool:
    """容量是否符合请求；None 表示不校验。"""
    if grounded_cap is None or need_cap is None:
        return False
    if cmp == "gte":
        return grounded_cap < need_cap
    if cmp == "lte":
        return grounded_cap > need_cap
    return abs(grounded_cap - need_cap) > max(1.0, need_cap * tolerance_ratio)

def _norm_model(value) -> str:
    """料号/型号文本归一：忽略大小写、空格、连字符，便于 LLM 输出与库内料号对齐。"""
    return re.sub(r"[\s\-_]+", "", str(value or "")).lower()

def _num_of(value) -> Optional[float]:

    if value is None:
        return None
    m = re.search(r"[\d.]+", str(value))
    return float(m.group()) if m else None

def _gb_of(value) -> Optional[float]:
    """容量词 → GB：'960G'/'32 GB'→960/32；'1.92T'/'1.92 TB'→1966.08。"""
    s = str(value or "").strip().upper()
    m = re.search(r"([\d.]+)\s*(T|G|M)?\s*B?", s)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "")
    if unit == "T":
        n *= 1024
    elif unit == "M":
        n /= 1024
    return n


def _series_ok(applicable, series: str) -> bool:
    """机型适配判定（与 kp_config API 同一语义）：applicable 缺省/无 series 键=通用件；
    series 列表含目标系列=适配；空列表=对全部系列隐藏。"""
    if not series or not isinstance(applicable, dict):
        return True
    lst = applicable.get("series")
    if lst is None:
        return True
    if isinstance(lst, list):
        return any(str(x).strip() == series for x in lst)
    return True

class _SeriesScopedRepo:
    """系列作用域包装：机型锁定后，配件候选池只剩适配件（含通用件）。
    过滤发生在取数边界，_ground_* 各 grounding 无需各自感知兼容性。"""

    def __init__(self, repo, series: str):
        self._repo = repo
        self._series = (series or "").strip()

    def __getattr__(self, name):
        return getattr(self._repo, name)

    def _f(self, rows):
        if not self._series:
            return rows
        return [r for r in rows if _series_ok(r.get("applicable"), self._series)]

    def get_by_category(self, category, search=""):
        return self._f(self._repo.get_by_category(category, search))

    def get_by_category_with_specs(self, category):
        return self._f(self._repo.get_by_category_with_specs(category))

    def get_by_category_with_spec_filter(self, category, spec_filters):
        return self._f(self._repo.get_by_category_with_spec_filter(category, spec_filters))

    def get_latest_prices(self, **kw):
        return self._f(self._repo.get_latest_prices(**kw))

def _cap_disp(gb: float) -> str:
    g = int(round(gb))
    if g % 1024 == 0:
        return f"{g // 1024}T"
    if g >= 1024:
        t = g / 1024
        s = f"{t:.2f}".rstrip("0").rstrip(".")
        return f"{s}T"
    return f"{g}G"

def _drive_media_label(row: dict) -> str:
    """盘介质标签：优先取目录规格 Type+Media（如 'SATA SSD'/'NVMe HDD'），
    无规格时按型号关键词兜底 SSD/HDD，保证展示与目录事实一致、不丢子类型。"""
    specs = row.get("specs") or {}
    bits = [str(specs.get("Type") or "").strip(), str(specs.get("Media") or "").strip()]
    label = " ".join(b for b in bits if b).upper()
    if label:
        return label
    hay = str(row.get("model") or "").upper()
    if "SSD" in hay:
        return "SSD"
    return "HDD"

def _drive_display(row: dict) -> str:
    """硬盘展示名：目录真实型号 + 介质子类型（如 '8T SATA SSD'），绝不改成 '2x 8T SSD'。"""
    model = str(row.get("model") or "").strip()
    media = _drive_media_label(row)
    if model and media.lower() not in model.lower():
        return f"{model} {media}"
    return model or media

def _spec_hit(specs: dict, filters: list) -> str:
    """规格 AND 过滤；全中返回标签串，否则 ''。"""
    hits = []
    for f in filters or []:
        sk = (f.get("spec_key") or "").strip()
        op = (f.get("op") or "=").strip()
        val = f.get("value")
        if not sk:
            continue
        sv = specs.get(sk)
        if sv is None:
            return ""
        svn = _num_of(sv)
        vn = _num_of(val) if not isinstance(val, list) else None
        if op in (">=", "<=", ">", "<") and svn is not None and vn is not None:
            ok = (svn >= vn if op == ">=" else svn <= vn if op == "<="
                  else svn > vn if op == ">" else svn < vn)
            if not ok:
                return ""
            hits.append(f"{sk}{op}{vn:g}")
        elif isinstance(val, list) or op == "in":
            vals = val if isinstance(val, list) else [val]
            if not any(str(sv).strip() == str(v).strip() for v in vals):
                return ""
            hits.append(f"{sk}∈{{{','.join(str(v) for v in vals)}}}")
        else:
            if str(sv).strip() != str(val).strip() and (svn is None or vn is None or abs(svn - vn) > 1e-9):
                return ""
            hits.append(f"{sk}={sv}")
    return " · ".join(hits)

def _pick(rows, mode):
    if not rows:
        return None
    if mode == "max_price":
        return max(rows, key=lambda r: float(r.get("price") or 0))
    if mode == "first":
        return rows[0]
    return min(rows, key=lambda r: float(r.get("price") or 0))

def _row(db_cat, rep, qty, matched_spec="", unmatched=False, reason="",
         request_spec="", grounded_spec="", spec_mismatch=False):
    return {
        "category": db_cat,
        "pn": str(rep.get("model") or "") if rep else "",
        "name": str(rep.get("model") or "") if rep else "",
        "unit_price": float(rep.get("price") or 0) if rep else 0.0,
        "currency": str(rep.get("currency") or "RMB") if rep else "RMB",
        "qty": int(qty or 1),
        "matched_spec": matched_spec or "",
        "unmatched": unmatched,
        "unmatched_reason": reason,
        "request_spec": request_spec or "",
        "grounded_spec": grounded_spec or "",
        "spec_mismatch": bool(spec_mismatch),
    }

def _unmatched(db_cat, qty, reason):
    return _row(db_cat, None, qty, unmatched=True, reason=reason)

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
    repo = KPRepository()
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
    repo = KPRepository()
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

def compose_memory(total_gb, slots=None):
    """内存容量组合求解：total_gb → 库内可行单条容量组合（如 128G → 64G×2 / 32G×4）。"""
    repo = KPRepository()
    try:
        rows = repo.get_by_category_with_specs("Memory")
        caps = set()
        for r in rows:
            cap = _gb_of((r.get("specs") or {}).get("Capacity"))
            if cap and cap >= 4:
                caps.add(int(cap))
        comps = []
        for c in sorted(caps, reverse=True):
            qty = int(total_gb // c)
            if qty >= 1 and total_gb % c == 0:
                comps.append({"per_stick_gb": c, "qty": qty, "total_gb": int(total_gb)})
        note = ""
        if slots is not None and comps:
            comps = [c for c in comps if c["qty"] <= int(slots)]
            note = f"已按 {slots} 槽位过滤"
        return {"total_gb": int(total_gb), "compositions": comps[:5], "note": note}
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
    raw = KPRepository()
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

def _ground_cpu(repo, db_cat, sig, pick):
    """CPU：不做型号/别名/规格匹配（旧解析器已删除），只把登记信号转成「交由 AI 选型」缺口行。"""
    if not isinstance(sig, dict) or not sig:
        return []
    qty = int((sig or {}).get("qty") or 1)
    model = str((sig or {}).get("model") or "").strip()
    cores = sig.get("cores")
    tdp = sig.get("tdp_w")
    bits = [model] if model else ["未指定型号"]
    if cores:
        bits.append(f"{int(cores)}C")
    if tdp:
        bits.append(f"{int(tdp)}W")
    return [_placeholder(db_cat, qty, " ".join(bits))]

def _ground_memory(repo, db_cat, sig, pick):
    """内存：只把登记信号（容量/类型/速度）转成缺口行，由 AI 从候选选条。"""
    if not isinstance(sig, dict) or not sig:
        return []
    qty = int(sig.get("qty") or 1)
    bits = []
    if sig.get("per_stick_gb"):
        bits.append(f"{int(sig['per_stick_gb'])}G")
    if sig.get("total_gb"):
        bits.append(f"共{int(sig['total_gb'])}G")
    if sig.get("type"):
        bits.append(str(sig["type"]))
    if sig.get("speed"):
        bits.append(str(sig["speed"]))
    return [_placeholder(db_cat, qty, " ".join(bits) or "内存")]

def _ground_storage(repo, db_cat, groups, pick):
    """硬盘：每个盘组 → 一行缺口（容量/接口/介质），由 AI 从候选按需求语义选型。"""
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        capacity = str(g.get("capacity") or g.get("term") or "").strip()
        interface = str(g.get("interface") or g.get("kind") or "").strip()
        media = str(g.get("media") or "").strip()
        want = " ".join(b for b in (capacity, interface, media) if b) or "硬盘"
        out.append(_placeholder(db_cat, qty, want))
    return out

def _ground_gpu(repo, db_cat, groups, pick):
    """GPU：每个 GPU 组 → 一行缺口（型号 token/显存），由 AI 从候选按需求语义选型。"""
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        tokens = [str(t) for t in (g.get("tokens") or []) if str(t).strip()]
        cap = g.get("cap") if g.get("cap") is not None else g.get("capacity_gb")
        want = " ".join(tokens) or "未指定型号"
        if cap is not None:
            want = f"{want} {cap}G显存"
        out.append(_placeholder(db_cat, qty, want))
    return out

def _ground_raid(repo, db_cat, groups, pick):
    """RAID：只登记卡需求（型号/缓存/级别），由 AI 从阵列卡候选选型；不做 RAID Level 词表匹配。"""
    out = []
    for g in groups or []:
        qty = int(g.get("qty") or 1)
        model = str(g.get("model") or "").strip()
        cache = g.get("cache")
        levels = g.get("raid_levels") or []
        bits = [model] if model else ["RAID 阵列卡"]
        if cache:
            bits.append(f"{cache}缓存")
        if levels:
            bits.append("支持" + "/".join(str(x) for x in levels))
        out.append(_placeholder(db_cat, qty, " ".join(bits)))
    return out

def _ground_nic(repo, db_cat, msf, pick):
    """网卡：把多规格需求转成缺口行（含修饰词），由 AI 从候选选型。"""
    if isinstance(msf, dict):
        lines = msf.get("NIC") or msf.get(db_cat) or []
    elif isinstance(msf, list):
        lines = msf
    else:
        lines = []
    if isinstance(lines, dict):
        lines = [lines]
    if not isinstance(lines, list):
        lines = []
    out = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        qty = int(line.get("qty") or 1)
        terms = line.get("name_contains") or []
        if not isinstance(terms, list):
            terms = [terms]
        want = " ".join(str(t) for t in terms if str(t).strip()) or "网卡"
        out.append(_placeholder(db_cat, qty, want))
    return out

def _ground_generic(repo, db_cat, search, qty_map, search_map, pick):
    """通用类（电源等）：把关键词/数量转成缺口行，由 AI 从候选选型。"""
    qty = int((qty_map or {}).get(db_cat) or 1)
    kw = str((search_map or {}).get(db_cat) or search or "").strip()
    return [_placeholder(db_cat, qty, kw or str(db_cat))]

def select_parts(categories=None, server_type_name=None, search=None, qty_map=None, search_map=None,
                 representative_pick="min_price",
                 cpu=None, memory=None, storage=None,
                 gpu=None, raid=None, psu=None, nic=None,
                 series: str = ""):
    """按结构化信号落地真实料号；AI 补全信号（怎么配），工具只检索落地。

    series：机型平台系列——已锁机型时传入，候选池过滤到适配件（applicable 语义），
    不兼容件进 BOM 是硬错误；未锁机型/未知系列传空。
    """
    pick = lambda rows: _pick(rows, representative_pick)
    raw_repo = KPRepository()
    repo = _SeriesScopedRepo(raw_repo, series)
    try:
        index = _category_index(repo)
        db_cats = []

        def _add_cat(raw_cat: str) -> None:
            dbc = _resolve_db_category(str(raw_cat), index)
            if dbc and dbc not in db_cats:
                db_cats.append(dbc)

        for c in (categories or []):
            _add_cat(c)
        # 信号字段是唯一真值源：categories 只是编排辅助，漏了某项也不能把该类配件丢掉。
        if isinstance(cpu, dict) and cpu:
            _add_cat("CPU")
        if memory:
            _add_cat("Memory")
        if storage:
            _add_cat("HDD/SSD")
        if gpu:
            _add_cat("GPU")
        if raid:
            _add_cat("Raid card")
        if nic:
            _add_cat("NIC")
        db_cats = [c for c in dict.fromkeys(db_cats) if c]

        parts = []
        for db_cat in db_cats:
            low = db_cat.lower()
            if low == "cpu":
                parts.extend(_ground_cpu(repo, db_cat, cpu, pick))
            elif low == "memory":
                parts.extend(_ground_memory(repo, db_cat, memory, pick))
            elif low in ("hdd/ssd", "ssd", "storage hdd/ssd"):
                parts.extend(_ground_storage(repo, db_cat, storage, pick))
            elif low in ("gpu", "gpu card"):
                parts.extend(_ground_gpu(repo, db_cat, gpu, pick))
            elif "raid" in low or "hba" in low:
                parts.extend(_ground_raid(repo, db_cat, raid, pick))
            elif "nic" in low or "network" in low:
                parts.extend(_ground_nic(repo, db_cat, nic, pick))
            else:
                parts.extend(_ground_generic(repo, db_cat, search, qty_map, search_map, pick))
        return parts
    finally:
        raw_repo.close()

# ── 场景化配件推荐（要了配件但零信号时的缺口选项；全部目录事实）──────────────────

def _scenario_slot_for(db_cat: str) -> tuple[str, str]:
    """DB 大类 → (归一部件槽位, 类别展示名)：全部来自 kp_slot_group_map，不再内嵌词表。"""
    try:
        from app.services.requirement_slots import _load_kp_slot_map
        m = _load_kp_slot_map()
    except Exception:
        m = {}
    rule = (m or {}).get(str(db_cat)) if isinstance(m, dict) else None
    if isinstance(rule, dict):
        key = str(rule.get("key") or "").strip()
        if key:
            return key, str(db_cat)
    return "", ""


def _slot_db_cats(slot: str) -> list:
    """归一部件槽位 → 所属 DB 大类名列表（kp_slot_group_map 的 key==slot 的类别）。"""
    try:
        from app.services.requirement_slots import _load_kp_slot_map
        m = _load_kp_slot_map()
    except Exception:
        m = {}
    out = []
    for cat, rule in (m or {}).items():
        if isinstance(rule, dict) and str(rule.get("key") or "").strip() == slot:
            out.append(str(cat))
    return out

# 场景化配件推荐（type_package 固定配方）已随「策略中心-需求分析」移除：
# AI=配置器 由大脑决定配什么、去库找、落地真实/替代料号；不再用固定配方兜底。

def manual_pick_options(slot: str, server_type_name: str, baseline=None,
                        include_price: bool = True, limit: int = 40) -> list:
    """配件库自选候选：槽位品类在平台系列适配内的全部件（带 signal 载荷）。

    场景推荐只出 top-N 启发式候选（客户没得挑）；自选=全目录平铺按容量/核数
    降序，客户按型号/价格自己定。候选由服务端生成并登记进 last_card（与发卡
    选项同源同格式），后续点击仍走 (slot,value) 留底匹配，客户端不携带 signal。
    内存/硬盘按容量去重（信号就是容量），同容量取最便宜型号做代表。
    """
    baseline = baseline or {}
    series = str(baseline.get("series") or "").strip()
    slot_db_cats = _slot_db_cats(slot)
    if slot == "raid" or not slot_db_cats:
        return []
    label = slot_db_cats[0]
    repo = KPRepository()
    try:
        srepo = _SeriesScopedRepo(repo, series)
        index = _category_index(srepo)
        db_cats = []
        for c in (repo.get_categories() or []):
            name = str(c.get("category") or "").strip()
            if name and name in slot_db_cats:
                dbc = _resolve_db_category(name, index)
                if dbc and dbc not in db_cats:
                    db_cats.append(dbc)
        compat = f"{series} 适配" if series else ""

        def _price_note(row, qty=1):
            if not include_price or not row:
                return ""
            try:
                v = float(row.get("price") or 0) * qty
            except (TypeError, ValueError):
                return ""
            return f"¥{v:,.0f}" if v > 0 else ""

        def specs_of(r):
            return r.get("specs") or {}

        out: list[dict] = []
        for dbc in db_cats:
            rows = srepo.get_by_category_with_specs(dbc)
            if slot == "gpu":
                slots_n = int(baseline.get("gpu_slots") or 0)
                tiers = sorted({q for q in (slots_n, slots_n // 2, 1) if q >= 1})[-2:] if slots_n else [1]
                ranked = sorted(rows, key=lambda r: -(_gb_of(specs_of(r).get("Capacity")) or 0))
                seen: set = set()
                for r in ranked:
                    m = str(r.get("model") or "")
                    if not m or m in seen:
                        continue
                    seen.add(m)
                    cap = _gb_of(specs_of(r).get("Capacity"))
                    for q in tiers:
                        note = " ".join(b for b in (
                            f"{int(cap)}G 显存" if cap else "", compat, _price_note(r, q)) if b)
                        out.append({"label": f"{q}× {m}", "value": f"{q}×{m}",
                                    "desc": note, "slot": slot, "group": label,
                                    "signal": {"gpu": [{"model": m, "qty": int(q)}]}})
            elif slot == "cpu":
                q = int(baseline.get("max_cpu") or 1)
                ranked = sorted(rows, key=lambda r: -(_num_of(specs_of(r).get("Cores")) or 0))
                seen = set()
                for r in ranked:
                    m = str(r.get("model") or "")
                    if not m or m in seen:
                        continue
                    seen.add(m)
                    cores_v = _num_of(specs_of(r).get("Cores"))
                    note = " ".join(b for b in (
                        f"{int(cores_v)} 核" if cores_v else "", compat, _price_note(r, q)) if b)
                    out.append({"label": f"{q}× {m}", "value": f"{q}×{m}",
                                "desc": note, "slot": slot, "group": label,
                                "signal": {"cpu": {"model": m, "qty": int(q)}}})
            elif slot == "memory":
                dimm = int(baseline.get("max_dimm") or 0) or 8
                by_cap: dict[int, dict] = {}
                for r in rows:
                    c = _gb_of(specs_of(r).get("Capacity"))
                    if not c:
                        continue
                    k = int(c)
                    if k not in by_cap or float(r.get("price") or 1e9) < float(by_cap[k].get("price") or 1e9):
                        by_cap[k] = r
                for c, r in sorted(by_cap.items(), key=lambda kv: -kv[0]):
                    note = " ".join(b for b in (
                        f"插满 {dimm} 槽" if int(baseline.get("max_dimm") or 0) else "按 8 条估（机型未登记内存槽数）",
                        str(specs_of(r).get("Type") or "").strip(),
                        str(specs_of(r).get("Speed") or "").strip(), compat,
                        _price_note(r, dimm)) if b)
                    out.append({"label": f"{dimm}× {c}G（共 {dimm * c}G）", "value": f"{dimm}×{c}G",
                                "desc": note, "slot": slot, "group": label,
                                "signal": {"memory": {"per_stick_gb": int(c), "qty": int(dimm)}}})
            elif slot == "storage":
                by_cap: dict[tuple, dict] = {}
                for r in rows:
                    c = _gb_of(specs_of(r).get("Capacity"))
                    if not c:
                        continue
                    media = "SSD" if "SSD" in (str(specs_of(r).get("Media") or "") +
                                              str(specs_of(r).get("Type") or "")).upper() else "HDD"
                    k = (int(c), media)
                    if k not in by_cap or float(r.get("price") or 1e9) < float(by_cap[k].get("price") or 1e9):
                        by_cap[k] = r
                for (c, _mk), r in sorted(by_cap.items(), key=lambda kv: -kv[0][0]):
                    disp = _drive_display(r)
                    media = _drive_media_label(r)
                    note = " ".join(b for b in (media, compat, _price_note(r, 1)) if b)
                    out.append({"label": disp, "value": disp,
                                "desc": note, "slot": slot, "group": label,
                                "qty": 1, "qty_max": 16, "unit_gb": int(c),
                                "signal": {"storage": [{"capacity_gb": int(c), "qty": 1,
                                                       "media": media}]}})
        return out[:limit]
    finally:
        repo.close()

def manual_signal_for_text(slot: str, text: str, server_type_name: str,
                           baseline=None) -> Optional[dict]:
    """自由输入型号 → 目录匹配构造 signal（逐项卡「手动输入型号」入口）。

    系列适配内全目录按 归一化型号检索 对**型号原文**匹配（型号级命中，不经容量去重代表）；
    数量取该槽默认档（GPU=满配 / CPU=路数 / 内存=插满 / 硬盘=1，前端 stepper 可再调）。
    未命中返回 None——调用方走登记表路径白盒处理（库外项不拦截）。
    """
    text = str(text or "").strip()
    slot_db_cats = _slot_db_cats(slot)
    if not text or not slot_db_cats or slot not in ("gpu", "cpu", "memory", "storage"):
        return None
    baseline = baseline or {}
    series = str(baseline.get("series") or "").strip()
    repo = KPRepository()
    try:
        srepo = _SeriesScopedRepo(repo, series)
        index = _category_index(srepo)
        for c in (repo.get_categories() or []):
            name = str(c.get("category") or "").strip()
            if not name or name not in slot_db_cats:
                continue
            dbc = _resolve_db_category(name, index)
            if not dbc:
                continue
            for r in (srepo.get_by_category_with_specs(dbc) or []):
                m = str(r.get("model") or "")
                nm = _norm_model(m)
                nt = _norm_model(text)
                if not (nt and (nt in nm or nm in nt)):
                    continue
                specs = r.get("specs") or {}
                if slot == "gpu":
                    return {"gpu": [{"model": m, "qty": int(baseline.get("gpu_slots") or 0) or 1}]}
                if slot == "cpu":
                    return {"cpu": {"model": m, "qty": int(baseline.get("max_cpu") or 0) or 1}}
                cap = _gb_of(specs.get("Capacity"))
                if not cap:
                    continue
                if slot == "memory":
                    return {"memory": {"per_stick_gb": int(cap),
                                       "qty": int(baseline.get("max_dimm") or 0) or 8}}
                media = _drive_media_label({"specs": specs, "model": m})
                item = {"capacity_gb": int(cap), "qty": 1, "media": media or "SSD"}
                return {"storage": [item]}
        return None
    finally:
        repo.close()
