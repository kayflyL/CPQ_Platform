# -*- coding: utf-8 -*-
"""可行性护栏 —— 数据驱动，不硬编码业务。

在机型/配件选配前检查“客户约束是否可行”，输出 warnings / hints。
数据来源：在售目录 base_config（form/gpu_slots/max_dimm）。
读库失败一律不拦截，仅静默返回空。
"""
from __future__ import annotations


def check_feasibility(ext: dict, config: dict = None) -> dict:
    rule_types = (config or {}).get("rule_types")
    warnings: list = []
    hints: list = []
    form = str((ext or {}).get("form") or (ext or {}).get("chassis_form") or "").strip()

    # GPU 卡数唯一真值源 = ext.gpu_groups（需求侧结构化事实）；不再读 semantic.workload.gpu_count，
    # 也不再用 gpu_form_map 死区间猜形态——真实槽位能力由下方 base_config.gpu_slots 判定。
    gc = 0
    _ggs = ext.get("gpu_groups") or []
    if isinstance(_ggs, list):
        gc = sum(int(g.get("qty") or 0) for g in _ggs if isinstance(g, dict))


    from app.services.catalog_guide import load_catalog
    try:
        types, mbt = load_catalog()
    except Exception:
        mbt = {}
    type_name = str((ext or {}).get("server_type_name") or (ext or {}).get("server_type") or "").strip()
    series = str((ext or {}).get("series") or "").strip()
    cands = []
    for tn, ms in mbt.items():
        if type_name and tn != type_name:
            continue
        for m in ms:
            b = m.get("base_config") or {}
            if series and (b.get("series") or "") != series:
                continue
            if form and (b.get("form") or "") != form:
                continue
            cands.append((m, b))

    if gc > 0 and cands:
        best = max(int(b.get("gpu_slots") or 0) for _, b in cands)
        if best < gc:
            warnings.append(f"目录内匹配机型单机最多 {best} 卡，无法满足 {gc} 卡需求，建议改更高卡位机箱或拆分多台")
    if not cands and (form or type_name or series):
        hints.append("当前 类型/系列/形态 组合在目录内暂无在售候选，建议放宽系列或形态")

    return {"warnings": warnings, "hints": hints}
