from pathlib import Path
B = Path(r"D:\CPQ_Platform_V1\backend\app\services")

def patch(rel, old, new, count=1):
    p = B / rel
    s = p.read_text(encoding="utf-8")
    assert old in s, f"NOT FOUND in {rel}:\n{old[:200]}"
    s = s.replace(old, new, count)
    p.write_text(s, encoding="utf-8")
    print("ok", rel)

# capabilities.py _enrich_agent_semantic
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

# slot_contract.py mapping
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

# slot_state.py mapping
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

print("ALL DONE")
