# -*- coding: utf-8 -*-
"""配件落料层（part_selector 拆分，2026-09-11）：选型落地（ground / select / manual）。

把 AI 给的选型信号落到真实料号与价格；未命中一律白盒 unmatched，不静默回退规则。
"""
from __future__ import annotations

from typing import Optional

from app.services.part_recall import _category_index, _resolve_db_category
from app.services.part_row_identity import _pick, _placeholder
from app.services.part_specs import _SeriesScopedRepo, _drive_display, _drive_media_label, _gb_of, _norm_model, _num_of, kp_repository


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
        per = _gb_of(sig["per_stick_gb"])
        if per:
            bits.append(f"{int(per)}G")
    if sig.get("total_gb"):
        total = _gb_of(sig["total_gb"])
        if total:
            bits.append(f"共{int(total)}G")
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
    raw_repo = kp_repository()
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
    repo = kp_repository()
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
    repo = kp_repository()
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
