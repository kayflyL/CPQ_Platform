# -*- coding: utf-8 -*-
"""统一数据访问层（数据域工具化，2026 架构收口）。

原则：
- 模型只做"语义决定"；本层只做"检索 + 接地"。绝不排序/打分/推荐（那是 AI 的活）。
- 每个 query 返回带 id 的真实行 + 完整 specs，供模型语义比对；绝不编造。
- select/grounding 只认 query 返回过的 id（服务端真相），防幻觉。
- 所有领域读经此层收口，散落 skill 逻辑不再各自 repo 直调；统一过系列适配与行数上限。
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _scope_blocked(retry, series: str) -> dict:
    """作用域内零命中时的**真话**：去掉系列作用域再查一次，把被平台适配挡在门外的料如实报出来。

    「库里没有这个料」与「库里有、但不适配当前机型平台」是两回事：静默返回空会把后者
    说成前者，AI 于是拿着错误前提去问客户（实测：兆芯 KH50000 只适配 Polaris，机型平台
    被推断成 Orion 后，每一轮都在问「要不要换成 AMD」）。这里只回事实，不替 AI 决策。
    """
    if not str(series or "").strip():
        return {}
    try:
        wide = retry()
    except Exception:
        logger.exception("作用域外复查失败 series=%s", series)
        return {}
    rows = [r for r in ((wide or {}).get("rows") or []) if isinstance(r, dict)]
    if not rows:
        return {}
    items = [{"name": r.get("name"), "applicable_series": r.get("applicable_series")}
             for r in rows]
    detail = "；".join(
        f"{it['name']}（适配 {'/'.join(str(s) for s in (it['applicable_series'] or [])) or '未标注'}）"
        for it in items)
    return {
        "out_of_scope": items,
        "scope_note": (f"当前机型平台是 {series}，库内匹配关键词的料都不适配它：{detail}。"
                       "这些料在库内存在、只是不适配当前平台——不是「库里没有」。"),
    }


def _load_aliases(repo) -> list:
    """检索别名（kp.kp_search_aliases）：repo 有该方法（真库）就取，stub/异常一律空表降级。"""
    fn = getattr(repo, "list_search_aliases", None)
    if not callable(fn):
        return []
    try:
        return fn() or []
    except Exception:
        logger.exception("检索别名加载失败，按空别名降级")
        return []


def part_query(category, *, spec_filters=None, keywords: str = "", series: str = "",
               limit: int = 50, offset: int = 0, price_ok: bool = True, _repo=None) -> dict:
    """确定性配件检索（AI=配置器的"去库找"）。

    spec_filters=[{spec_key, op, value}, ...] AND 组合；op 支持 >= <= > < = in。
    返回 {ok, category, db_category, source, rows, truncated, total}；rows 每项
    {part_id, name, price, currency, specs, applicable_series}——specs 全量下行。
    关键词命中走 part_lexicon 加权引擎（2026-09-12 P0）：中文名段 > 数字/混合词 > 别名扩展 >
    blob 外围（brand/spec 值/简介），同轴判别（sata/nvme/sas、ssd/hdd、ddr4/ddr5）互斥过滤；
    命中行按词法相关度降序——这是检索排序不是推荐，最终选料仍是 AI 的活。
    """
    from app.repository.kp_repo import KPRepository, _spec_match_all
    from app.services.part_selector import (_category_index, _resolve_db_category,
                                            _dedupe_rows, _SeriesScopedRepo)
    from app.services.part_lexicon import (extract_query_tokens, build_row_blob,
                                           score_row, passes_discriminators)
    cat = str(category or "").strip()
    if not cat:
        return {"ok": False, "error": "invalid_args", "message": "category 必填"}
    price_ok = bool(price_ok)
    try:
        limit = max(1, min(200, int(limit or 50)))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    raw = _repo or KPRepository()
    owned = _repo is None
    try:
        repo = _SeriesScopedRepo(raw, series) if series else raw
        index = _category_index(repo)
        db_cat = _resolve_db_category(cat, index)
        if not db_cat:
            return {"ok": False, "error": "unknown_category",
                    "message": f"类目 {cat} 不在配件库（可用 list_kp_categories 查真实类目）"}
        keys = _dedupe_rows(repo.get_by_category_with_specs(db_cat) or [])
        _spec_key_set: set = set()
        for _r in keys:
            _sp = _r.get("specs")
            if isinstance(_sp, dict):
                _spec_key_set.update(str(_k) for _k in _sp)
        spec_keys = sorted(_spec_key_set)
        # 规格过滤（确定性 AND，数值/等值/in 与 repo 同语义）。spec_key 先精确后归一解析
        # （大小写/空格差异：'link speed' → 'Link Speed'），解析不到才判该 spec 不存在。
        parsed: list = []
        for f in spec_filters or []:
            f = f if isinstance(f, dict) else {}
            sk = str(f.get("spec_key") or "").strip()
            if sk:
                parsed.append((sk, str(f.get("op") or "=").strip(), f.get("value")))
        if parsed:
            import re as _re
            _norm_key = lambda k: _re.sub(r"\s+", "", str(k)).lower()
            _norm_map = {_norm_key(k): k for k in _spec_key_set}
            parsed = [((_norm_map.get(_norm_key(sk), sk)), op, val) for sk, op, val in parsed]
            keep = []
            for r in keys:
                if _spec_match_all(r.get("specs") or {}, parsed):
                    keep.append(r)
            keys = keep
        # 关键词：词法引擎加权召回（中文名段/数字段/混合词/纯字母词/别名扩展 + 容量等值 +
        # 同轴判别互斥），命中行按分值降序。
        kw = str(keywords or "").strip()
        if kw:
            tokens = extract_query_tokens(kw, _load_aliases(raw))
            scored_rows: list = []
            for r in keys:
                _name, _blob = build_row_blob(r)
                if not passes_discriminators(tokens, _blob):
                    continue
                sc, _kinds = score_row(tokens, r, row_name=_name, row_blob=_blob)
                if sc > 0:
                    scored_rows.append((sc, r))
            scored_rows.sort(key=lambda x: -x[0])
            keys = [r for _, r in scored_rows]
        out: list = []
        for r in keys[offset:offset + limit]:
            specs = r.get("specs") if isinstance(r.get("specs"), dict) else {}
            item: dict = {"part_id": str(r.get("id") or ""),
                          "name": str(r.get("model") or ""),
                          "price": float(r.get("price") or 0),
                          "currency": str(r.get("currency") or "RMB")}
            if specs:
                item["specs"] = dict(specs)
            app = r.get("applicable") or {}
            if isinstance(app, dict):
                item["applicable_series"] = app.get("series")
            if not price_ok:
                item.pop("price", None)
            if item["name"]:
                out.append(item)
        tot = len(keys)
        note = None
        if tot == 0 and (kw or parsed):
            note = (f"未命中候选（关键词「{keywords or '(无)'}」或规格过滤过严）。"
                    "库内该类目 specs 字段：" + ("、".join(spec_keys[:10]) if spec_keys else "无") +
                    "。可用的数值/型号词形如 1G/10G/DDR5/6T。")
        res = {"ok": True, "category": cat, "db_category": db_cat,
               "source": "kp_library/part_query", "rows": out,
               "truncated": tot > offset + len(out), "total": tot,
               "spec_keys": spec_keys, "note": note,
               "offset": offset, "next_offset": (offset + len(out) if tot > offset + len(out) else None)}
        if not out:
            res.update(_scope_blocked(
                lambda: part_query(cat, spec_filters=spec_filters, keywords=keywords,
                                   series="", limit=5, offset=0, price_ok=price_ok, _repo=raw),
                series))
        return res
    finally:
        if owned:
            raw.close()


def part_recall(category, *, desc: str, series: str = "", limit: int = 30,
                price_ok: bool = True, _repo=None) -> dict:
    """行描述 → 候选召回（OR 语义，与 part_query 的 AND 收窄互补）。

    走 part_lexicon 加权引擎（2026-09-12 P0）：从行描述提取拉丁 token（≥3 位数字段/
    含数字混合词/纯字母词）+ 中文连续段 + 别名扩展（万兆→10G），对料 blob（名+brand+
    spec 值+简介）加权命中——中文名段 > 数字/混合词 > 别名 > blob 外围；容量等值 ±1%；
    同轴判别（sata/nvme/sas、ssd/hdd、ddr4/ddr5）互斥过滤。按分值降序取前 N。
    兆芯行推出 AMD 池 / DDR4 混进 DDR5 池 / 万兆千兆零召回由此根治。纯确定性提取，
    不做语义打分/推荐（那是 AI 的活）。返回形状与 part_query 一致（source=part_recall）。
    """
    from app.repository.kp_repo import KPRepository
    from app.services.part_selector import (_category_index, _resolve_db_category,
                                            _dedupe_rows, _SeriesScopedRepo)
    from app.services.part_lexicon import (extract_query_tokens, build_row_blob,
                                           score_row, passes_discriminators)
    cat = str(category or "").strip()
    if not cat:
        return {"ok": False, "error": "invalid_args", "message": "category 必填"}
    text = str(desc or "").strip().lower()
    raw = _repo or KPRepository()
    owned = _repo is None
    try:
        repo = _SeriesScopedRepo(raw, series) if series else raw
        index = _category_index(repo)
        db_cat = _resolve_db_category(cat, index)
        if not db_cat:
            return {"ok": False, "error": "unknown_category",
                    "message": f"类目 {cat} 不在配件库"}
        keys = _dedupe_rows(repo.get_by_category_with_specs(db_cat) or [])
        _spec_key_set: set = set()
        for _r in keys:
            _sp = _r.get("specs")
            if isinstance(_sp, dict):
                _spec_key_set.update(str(_k) for _k in _sp)
        spec_keys = sorted(_spec_key_set)
        tokens = extract_query_tokens(text, _load_aliases(raw))
        probes = sorted(tokens["num_tokens"] | tokens["mixed_tokens"]
                        | tokens["alpha_tokens"] | tokens["alias_tokens"]
                        | tokens["cjk_runs"])
        scored: list = []
        for r in keys:
            _name, _blob = build_row_blob(r)
            if not _name:
                continue
            if not passes_discriminators(tokens, _blob):
                continue
            sc, _kinds = score_row(tokens, r, row_name=_name, row_blob=_blob)
            if sc > 0:
                scored.append((sc, r))
        scored.sort(key=lambda x: -x[0])
        out: list = []
        for _, r in scored[:limit]:
            specs = r.get("specs") if isinstance(r.get("specs"), dict) else {}
            item = {"part_id": str(r.get("id") or ""),
                    "name": str(r.get("model") or ""),
                    "price": float(r.get("price") or 0),
                    "currency": str(r.get("currency") or "RMB")}
            if specs:
                item["specs"] = dict(specs)
            app = r.get("applicable") or {}
            if isinstance(app, dict):
                item["applicable_series"] = app.get("series")
            if not price_ok:
                item.pop("price", None)
            if item["name"]:
                out.append(item)
        note = None
        if not out:
            note = ("行描述未召回库内候选；库内该类目 specs 字段：" + ("、".join(spec_keys[:10]) if spec_keys else "无") +
                    "。请改用更短的数值/型号词（如 1G/10G/DDR5/6T）或 required_specs 的库内字段收窄。")
        res = {"ok": True, "category": cat, "db_category": db_cat,
               "source": "part_recall", "rows": out, "probes": probes,
               "truncated": len(scored) > limit, "total": len(out),
               "spec_keys": spec_keys, "note": note}
        if not out:
            res.update(_scope_blocked(
                lambda: part_recall(cat, desc=desc, series="", limit=5, price_ok=price_ok,
                                    _repo=raw),
                series))
        return res
    finally:
        if owned:
            raw.close()


def lookup_parts_by_name(category, name, *, series: str = "", price_ok: bool = True,
                         _repo=None) -> dict:
    """按「类目 + 料号名」在库里精确找回料号（忽略大小写与空格差异）。

    库里没有业务料号（part_id 只是自增行号），落料能对上的唯一凭据就是料号名。
    rows 形状与 part_query 一致（part_id/name/price/specs）；库内同名多行时原样全回，
    由 AI 确认，不猜、不合并。
    """
    from app.repository.kp_repo import KPRepository
    from app.services.part_selector import (_category_index, _resolve_db_category,
                                            _dedupe_rows, _SeriesScopedRepo)
    cat = str(category or "").strip()
    want = re.sub(r"\s+", "", str(name or "")).lower()
    if not cat:
        return {"ok": False, "error": "invalid_args", "message": "category 必填"}
    if not want:
        return {"ok": False, "error": "invalid_args", "message": "name 必填（料号名）"}
    raw = _repo or KPRepository()
    owned = _repo is None
    try:
        repo = _SeriesScopedRepo(raw, series) if series else raw
        db_cat = _resolve_db_category(cat, _category_index(repo))
        if not db_cat:
            return {"ok": False, "error": "unknown_category",
                    "message": f"类目 {cat} 不在配件库"}

        def _match(rows) -> list:
            out: list = []
            for r in _dedupe_rows(rows or []):
                if re.sub(r"\s+", "", str(r.get("model") or "")).lower() != want:
                    continue
                item = {"part_id": str(r.get("id") or ""),
                        "name": str(r.get("model") or ""),
                        "price": float(r.get("price") or 0),
                        "currency": str(r.get("currency") or "RMB")}
                specs = r.get("specs")
                if isinstance(specs, dict) and specs:
                    item["specs"] = dict(specs)
                app = r.get("applicable") or {}
                if isinstance(app, dict):
                    item["applicable_series"] = app.get("series")
                if not price_ok:
                    item.pop("price", None)
                out.append(item)
            return out

        out = _match(repo.get_by_category_with_specs(db_cat))
        res = {"ok": True, "category": cat, "db_category": db_cat,
               "source": "kp_library/name_lookup", "rows": out, "total": len(out)}
        if not out:
            res.update(_scope_blocked(
                lambda: {"rows": _match(raw.get_by_category_with_specs(db_cat))}, series))
        return res
    finally:
        if owned:
            raw.close()


def lookup_part_by_id(part_id, *, price_ok: bool = True, _repo=None) -> dict:
    """按库内行号（kp.kp_parts.id）取回一颗料——兼容通道。

    库里没有业务料号，id 只是自增行号：新落料一律按料号名（lookup_parts_by_name），
    这里只服务「历史 pick 里存的是 id」的场景。rows 取 0/1 条，形状同名称通道。
    """
    from app.repository.kp_repo import KPRepository
    from app.services.part_selector import _category_index
    pid = str(part_id or "").strip()
    if not pid:
        return {"ok": False, "error": "invalid_args", "message": "part_id 必填"}
    raw = _repo or KPRepository()
    owned = _repo is None
    try:
        for e in _category_index(raw)["by_key"].values():
            db_cat = str(e["db_category"])
            for r in raw.get_by_category_with_specs(db_cat) or []:
                if str(r.get("id") or "") != pid:
                    continue
                item = {"part_id": str(r.get("id") or ""), "name": str(r.get("model") or ""),
                        "category": db_cat, "price": float(r.get("price") or 0),
                        "currency": str(r.get("currency") or "RMB")}
                specs = r.get("specs")
                if isinstance(specs, dict) and specs:
                    item["specs"] = dict(specs)
                app = r.get("applicable") or {}
                if isinstance(app, dict):
                    item["applicable_series"] = app.get("series")
                if not price_ok:
                    item.pop("price", None)
                return {"ok": True, "source": "kp_library/id_lookup",
                        "rows": [item], "total": 1}
        return {"ok": True, "source": "kp_library/id_lookup", "rows": [], "total": 0}
    finally:
        if owned:
            raw.close()
