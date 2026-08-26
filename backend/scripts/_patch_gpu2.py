from pathlib import Path
p = Path(r"D:\CPQ_Platform_V1\backend\app\services\capabilities.py")
s = p.read_text(encoding="utf-8")

# 1) helper before run_select_baseline_rule
anchor = "def run_select_baseline_rule(ctx: dict, config: dict) -> dict:\n"
helper = '''def _gpu_qty_from_ext(ext: dict) -> int:
    """GPU 卡数唯一真值源：汇总 ext.gpu_groups 的 qty。不读 semantic.workload.gpu_count（已收口删除）。"""
    total = 0
    for g in (ext.get("gpu_groups") or []):
        if isinstance(g, dict):
            try:
                total += int(g.get("qty") or 0)
            except (TypeError, ValueError):
                pass
    return total


'''
assert anchor in s
s = s.replace(anchor, helper + anchor, 1)

# 2) import: drop gpu_form_map
old_imp = "from app.services.requirement_rule_catalog import compliance_map as _compliance_map, gpu_form_map as _gpu_form_map\n"
new_imp = "from app.services.requirement_rule_catalog import compliance_map as _compliance_map\n"
assert old_imp in s
s = s.replace(old_imp, new_imp, 1)

# 3) replace GPU count/form block
old_block = '''    # GPU 数量（来自 workload/exclusion 卡数）→ 机箱形态约束
    _gpu_count = int((_sc.gpu_requirement(ext) or {}).get("gpu_count") or 0)
    if _gpu_count > 0:
        for _rule in _gpu_form_map(enabled_types=cfg.get("rule_types")):
            _lo = int(_rule.get("gpu_count_min") or 0)
            _hi = int(_rule.get("gpu_count_max") or (1 << 31))
            if _lo <= _gpu_count <= _hi and _rule.get("form"):
                _form = str(_rule.get("form") or _form)
                break
'''
new_block = '''    # GPU 卡数：唯一真值源 = ext.gpu_groups（需求侧结构化事实）。不再读 semantic.workload.gpu_count，
    # 也不再按 gpu_form_map 死区间猜形态；真实槽位能力由 base_config.gpu_slots 在选型后过滤。
    _gpu_count = _gpu_qty_from_ext(ext)
'''
assert old_block in s, "gpu block not found"
s = s.replace(old_block, new_block, 1)

# 4) post-filter by gpu_slots, before _cat_model_id handling
old_cat = "    _cat_model_id = ctx.get(\"catalog_model_id\")\n"
new_cat = '''    # 真实 GPU 槽位能力过滤（事实源 = base_config.gpu_slots，非死区间）：卡数需求>0 时只保留能装下的机型；
    # 一个能装的都没有则保留原候选并白盒标注槽位不足，交下游说明，不静默丢卡。
    if _gpu_count > 0:
        _capable = [b for b in baselines
                    if int((b.get("base_config") or {}).get("gpu_slots") or 0) >= _gpu_count]
        if _capable:
            baselines = _capable
        else:
            for b in baselines:
                b["gpu_capacity_note"] = f"当前候选机型 GPU 槽位不足 {_gpu_count} 卡"

    _cat_model_id = ctx.get("catalog_model_id")\n'''
assert old_cat in s
s = s.replace(old_cat, new_cat, 1)

p.write_text(s, encoding="utf-8")
print("patched run_select_baseline_rule")
