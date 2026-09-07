# -*- coding: utf-8 -*-
"""统一数据访问层（数据域工具化，2026 架构收口）。

原则：
- 模型只做"语义决定"；本层只做"检索 + 接地"。绝不排序/打分/推荐（那是 AI 的活）。
- 每个 query 返回带 id 的真实行 + 完整 specs，供模型语义比对；绝不编造。
- select/grounding 只认 query 返回过的 id（服务端真相），防幻觉。
- 所有领域读经此层收口，散落 skill 逻辑不再各自 repo 直调；统一过系列适配与行数上限。
"""
from __future__ import annotations

import re
from typing import Optional


def part_query(category, *, spec_filters=None, keywords: str = "", series: str = "",
               limit: int = 50, price_ok: bool = True, _repo=None) -> dict:
    """确定性配件检索（AI=配置器的"去库找"）。

    spec_filters=[{spec_key, op, value}, ...] AND 组合；op 支持 >= <= > < = in。
    返回 {ok, category, db_category, source, rows, truncated, total}；rows 每项
    {part_id, name, price, currency, specs, applicable_series}——specs 全量下行。
    不做任何打分/排序/推荐；数大时模型用 spec_filters 收窄，不做盲目截断。
    """
    from app.repository.kp_repo import KPRepository, _spec_match_all
    from app.services.part_selector import (_category_index, _resolve_db_category,
                                            _dedupe_rows, _SeriesScopedRepo, _gb_of)
    cat = str(category or "").strip()
    if not cat:
        return {"ok": False, "error": "invalid_args", "message": "category 必填"}
    price_ok = bool(price_ok)
    try:
        limit = max(1, min(200, int(limit or 50)))
    except (TypeError, ValueError):
        limit = 50
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
        # 关键词（名称归一检索）：模型点出型号/厂商/容量时收窄，避免把整个类目当候选。
        # 中文别名（兆芯50000）→ 库内拉丁型号（KH50000 96C）的桥接：整体子串命中优先，
        # 再退到「数字段（>=3 位）」命中，最后做「容量等值」（480G/6T/1.92T/1G 缓存 vs
        # 库件名容量），让中文容量/厂商标注在库内拉丁料号上也能召回；不做语义打分/推荐。
        kw = str(keywords or "").strip().lower()
        if kw:
            runs = re.findall(r"[a-z0-9]+", kw)
            num = {r for r in runs if r.isdigit() and len(r) >= 3}
            qcap = _gb_of(kw)
            keep: list = []
            for r in keys:
                m = str(r.get("model") or "").lower()
                if kw in m or any(t in m for t in num):
                    keep.append(r)
                elif qcap is not None and qcap > 0:
                    mcap = _gb_of(m)
                    if mcap is not None and abs(mcap - qcap) <= max(1.0, qcap * 0.01):
                        keep.append(r)
            keys = keep
        # 规格过滤（确定性 AND，数值/等值/in 与 repo 同语义）。
        parsed: list = []
        for f in spec_filters or []:
            f = f if isinstance(f, dict) else {}
            sk = str(f.get("spec_key") or "").strip()
            if sk:
                parsed.append((sk, str(f.get("op") or "=").strip(), f.get("value")))
        if parsed:
            keep = []
            for r in keys:
                if _spec_match_all(r.get("specs") or {}, parsed):
                    keep.append(r)
            keys = keep
        out: list = []
        for r in keys[:limit]:
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
        return {"ok": True, "category": cat, "db_category": db_cat,
                "source": "kp_library/part_query", "rows": out,
                "truncated": len(keys) > limit, "total": len(out)}
    finally:
        if owned:
            raw.close()


def part_recall(category, *, desc: str, series: str = "", limit: int = 30,
                price_ok: bool = True, _repo=None) -> dict:
    """行描述 → 候选召回（OR 语义，与 part_query 的 AND 收窄互补）。

    从客户行原文提取可检索 token 做「任一命中即召回」：≥3 位数字段（型号 50000）、
    容量词（480G/1.92T → GB 等值匹配库件名容量）、含数字的混合词（DDR5/9361/X8）。
    按 token 命中数降序——兆芯行推出 AMD 池 / DDR4 混进 DDR5 池这类「类目全量」
    质量事故由此根治。纯确定性提取，不做语义打分/推荐（那是 AI 的活）。
    返回形状与 part_query 一致（source=part_recall）。
    """
    from app.repository.kp_repo import KPRepository
    from app.services.part_selector import (_category_index, _resolve_db_category,
                                            _dedupe_rows, _SeriesScopedRepo, _gb_of)
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
        tokens = [t for t in re.findall(r"[a-z0-9.]+", text)]
        num_tokens = {t for t in tokens if t.replace(".", "").isdigit() and len(t) >= 3}
        # 「6t/8g/96c/1gb」这类数字+单位短探针是行描述最硬的检索词，len>=2 就收；
        # ghz（2.2ghz）是全员都有的规格噪音，排除。
        mixed_tokens = {t for t in tokens if any(c.isalpha() for c in t) and any(c.isdigit() for c in t)
                        and len(t) >= 2 and not t.endswith("ghz")}
        # 容量等值只在行描述真带容量写法（480G/1.92T/768GB）时启用——裸数字（"4个千兆"
        # 的 4）不算容量，否则 _gb_of 宽松解析会拿 4 去等值匹配，召出一堆 4 口/4x 件。
        qcap = None
        if re.search(r"\d+(?:\.\d+)?\s*(?:gb|tb)", text):
            qcap = _gb_of(text)
        # 「2.2ghz/96c」这类规格噪音不参与召回；容量词走下方 GB 等值分支（子串匹配无意义，
        # 且 768GB 总量 ≠ 单条容量，等值 ±1% 才是正确语义）。recalled=0 说明行描述在库内
        # 无对应词，调用方应明示「库内无精确匹配」而不是退化成类目全量。
        probes = list(num_tokens) + list(mixed_tokens)
        scored: list = []
        for r in keys:
            m = str(r.get("model") or "").lower()
            if not m:
                continue
            # 边界匹配：探针前不能是数字/小数点（「6t」不得命中「1.6t」的内嵌 6t）
            hits = [t for t in probes if re.search(rf"(?<![0-9.]){re.escape(t)}", m)]
            if not hits and qcap:
                mcap = _gb_of(m)
                if mcap is not None and abs(mcap - qcap) <= max(1.0, qcap * 0.01):
                    hits = [str(qcap)]
            if hits:
                scored.append((len(hits), r))
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
            if not price_ok:
                item.pop("price", None)
            if item["name"]:
                out.append(item)
        return {"ok": True, "category": cat, "db_category": db_cat,
                "source": "part_recall", "rows": out, "probes": probes,
                "truncated": len(scored) > limit, "total": len(out)}
    finally:
        if owned:
            raw.close()


def part_index_rows(rows: list) -> dict:
    """把 part_query 的 rows 归一成接地索引桶 {part_id: ent, name.lower(): ent}。

    select_kp_parts 只认此桶内的料号/名称（服务端真相），防模型提名库外料号。
    """
    bucket: dict = {}
    for c in rows or []:
        if not isinstance(c, dict):
            continue
        pid = str(c.get("part_id") or "").strip()
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        ent = {"part_id": pid, "name": name,
               "price": c.get("price"), "currency": str(c.get("currency") or "RMB")}
        if isinstance(c.get("specs"), dict) and c["specs"]:
            ent["specs"] = c["specs"]
        if pid:
            bucket[pid] = ent
        bucket[name.lower()] = ent
    return bucket
