from pathlib import Path
B = Path(r"D:\CPQ_Platform_V1\backend\app\services")

def patch(rel, old, new, count=1):
    p = B / rel
    s = p.read_text(encoding="utf-8")
    assert old in s, f"NOT FOUND in {rel}:\n{old[:200]}"
    assert s.count(old) >= count, f"count mismatch {rel}"
    s = s.replace(old, new, count)
    p.write_text(s, encoding="utf-8")
    print("ok", rel)

# 1) semantic_contract.py: remove gpu_requirement
patch("semantic_contract.py", '''def gpu_requirement(ext: dict) -> dict:
    """workload → GPU 需求（显存/卡数），供模型形态/配件取舍；无则空。"""
    wl = workload(ext)
    return {k: wl[k] for k in ("total_vram_gb", "gpu_count", "model") if wl.get(k) is not None}


''', "")

# 2) feasibility_guard.py: docstring + read gpu_groups only, drop gpu_form_map
patch("feasibility_guard.py",
"数据来源：规则目录 gpu_form_map + 在售目录 base_config（form/gpu_slots/max_dimm）。",
"数据来源：在售目录 base_config（form/gpu_slots/max_dimm）。")

patch("feasibility_guard.py", '''    from app.services import semantic_contract as _sc
    gc = int((_sc.gpu_requirement(ext) or {}).get("gpu_count") or 0)
    # 语义容器可能被 LLM 以 free text 覆盖（丢了 gpu_count），但结构化 gpu_groups 仍在：
    # 护栏按结构化卡数为准，否则无法对"8卡放1U"这类不合理需求兜底。
    if gc <= 0:
        _ggs = ext.get("gpu_groups") or ext.get("gpu") or []
        if isinstance(_ggs, list):
            gc = sum(int(g.get("qty") or 0) for g in _ggs if isinstance(g, dict))

    if gc > 0:
        from app.services import requirement_rule_catalog as _rc
        expected = None
        for r in _rc.gpu_form_map(rule_types):
            lo = int(r.get("gpu_count_min") or 0)
            hi = int(r.get("gpu_count_max") or (1 << 31))
            if lo <= gc <= hi:
                expected = r.get("form")
                break
        if expected and form and form != expected:
            warnings.append(f"需求 {gc} 张 GPU 放在 {form} 机箱不太可行，通常需要 {expected} 机箱")
''', '''    # GPU 卡数唯一真值源 = ext.gpu_groups（需求侧结构化事实）；不再读 semantic.workload.gpu_count，
    # 也不再用 gpu_form_map 死区间猜形态——真实槽位能力由下方 base_config.gpu_slots 判定。
    gc = 0
    _ggs = ext.get("gpu_groups") or []
    if isinstance(_ggs, list):
        gc = sum(int(g.get("qty") or 0) for g in _ggs if isinstance(g, dict))
''')

# 3) capabilities.py _enrich_agent_semantic
patch("capabilities.py", '''    wl = dict(_sc.workload(ext))
    # 2) 规则库 workload_map：命中关键词即按规则补总显存/卡数/意图（规则赢模型的数值）。
    for r in _rc.workload_map(rule_types):
        kw = str(r.get("workload_keyword") or "").lower()
        if kw and kw in rtext:
            if r.get("intent"):
                wl["kind"] = str(r.get("intent"))
            if r.get("total_vram_gb") is not None and "total_vram_gb" not in wl:
                wl["total_vram_gb"] = r.get("total_vram_gb")
            if r.get("gpu_count") is not None and "gpu_count" not in wl:
                wl["gpu_count"] = r.get("gpu_count")
            break
''', '''    wl = dict(_sc.workload(ext))
    rule_gpu_count = int(wl.get("gpu_count") or 0)
    # 规则库 workload_map：命中关键词即按规则补意图/显存/卡数（规则赢模型的数值）。
    for r in _rc.workload_map(rule_types):
        kw = str(r.get("workload_keyword") or "").lower()
        if kw and kw in rtext:
            if r.get("intent"):
                wl["kind"] = str(r.get("intent"))
            if r.get("total_vram_gb") is not None and "total_vram_gb" not in wl:
                wl["total_vram_gb"] = r.get("total_vram_gb")
            if r.get("gpu_count") is not None and rule_gpu_count <= 0:
                rule_gpu_count = int(r.get("gpu_count"))
            break
    wl.pop("gpu_count", None)
''')

patch("capabilities.py", '''    # GPU 卡数保存到 gpu_groups：量化事实来自模型 semantic 与规则库 workload_map。
    gc = int(wl.get("gpu_count") or 0)
    if gc > 0 and not _sc.absent_confirmed(ext, "gpu") and not ext.get("gpu_groups") and not ext.get("gpu"):
        ext["gpu_groups"] = [{"qty": gc}]
''', '''    # GPU 卡数只落 gpu_groups（模型 semantic / 规则 workload_map 的卡数统一在此归一）。
    if rule_gpu_count > 0 and not _sc.absent_confirmed(ext, "gpu") and not ext.get("gpu_groups"):
        ext["gpu_groups"] = [{"qty": rule_gpu_count}]
''')

# 4) slot_contract.py mapping
patch("slot_contract.py", '''        "cpu": ["cpu_signal", "cpu"],
        "memory": ["mem_signal", "mem_groups", "memory"],
        "storage": ["drive_groups", "drives", "storage"],
        "gpu": ["gpu_groups", "gpu"],
        "nic": ["nic_groups", "nic_signal", "nic", "multi_spec_filters"],
        "raid": ["raid_groups", "raid_signal", "raid"],
        "psu": ["psu_signal", "psu"],
''', '''        "cpu": ["cpu_signal"],
        "memory": ["mem_signal", "mem_groups"],
        "storage": ["drive_groups"],
        "gpu": ["gpu_groups"],
        "nic": ["multi_spec_filters"],
        "raid": ["raid_groups", "raid_signal"],
        "psu": ["psu_signal"],
''')

# 5) slot_state.py mapping
patch("slot_state.py", '''    "cpu": ["cpu_signal", "cpu"],
    "memory": ["mem_signal", "mem_groups", "memory"],
    "storage": ["drive_groups", "drives", "storage"],
    "gpu": ["gpu_groups", "gpu"],
    "nic": ["nic_groups", "nic_signal", "nic", "multi_spec_filters"],
    "raid": ["raid_groups", "raid_signal", "raid"],
    "psu": ["psu_signal", "psu"],
''', '''    "cpu": ["cpu_signal"],
    "memory": ["mem_signal", "mem_groups"],
    "storage": ["drive_groups"],
    "gpu": ["gpu_groups"],
    "nic": ["multi_spec_filters"],
    "raid": ["raid_groups", "raid_signal"],
    "psu": ["psu_signal"],
''')

print("ALL PATCHES DONE")
