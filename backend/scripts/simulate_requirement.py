"""端到端模拟推理流：需求文本 → extract → select_models → pick_kp_parts → build_plan。
用法：python -X utf8 simulate_requirement.py "客户需求文本"
作为调试工具长期保留，反复用。"""
import sys
sys.path.insert(0, r'D:\CPQ_Platform_V1\backend')

from app.services.requirement_intel_service import extract_keywords, _fold_lexicons, apply_budget_check
from app.repository.reasoning_flow_repo import _default_node_configs
from app.api.candidate_search import (select_models, pick_kp_parts, build_plan,
                                 kp_categories_for_type, build_variant_signals)
from app.services.reasoning_executor import _resolve_budget_strategy

text = sys.argv[1] if len(sys.argv) > 1 else "AI训练/推理服务器"

# 用默认 seed 词表（5 张）跑 extract
cfg = _default_node_configs()["extract"]
cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
ext = extract_keywords(text, lexicon=cat_lex, series_keyword_map=series_map,
                       usage_keyword_map=usage_map, form_keyword_map=form_map,
                       chassis_lexicon=chassis_lex,
                       spec_aliases=cfg.get("spec_aliases"),
                       qty_units=cfg.get("qty_units"),
                       qty_multipliers=cfg.get("qty_multipliers"),
                       model_token_regex=cfg.get("model_token_regex"))

print("=" * 72)
print(f"📞 客户需求：{text}")
print("=" * 72)

print("\n【1️⃣  需求理解 extract】")
print(f"  关键词       : {ext['keywords']}")
print(f"  服务器类型   : {ext.get('server_type_name')!r}  (usage={ext.get('usage')!r})")
print(f"  系列 / 形态  : {ext.get('series')!r} / {ext.get('form')!r}")
print(f"  预算         : {ext.get('budget')}")
print(f"  KP 品类      : {ext.get('categories')}")
print(f"  底盘件品类   : {ext.get('chassis_categories')}")

print("\n【2️⃣  机型选型 select_models】")
models = select_models(ext.get("usage"), ext.get("server_type_name"),
                       ext.get("series"), ext.get("form"), limit=3,
                       no_signal_strategy=_default_node_configs()["select_baseline"].get("no_signal_strategy"),
                       variant_signals=build_variant_signals(ext, text))
print(f"  命中 {len(models)} 个机型" + ("  ⚠ 空！" if not models else ""))
for m in models:
    print(f"    • {m['name']} | type={m.get('server_type_name')} | series={m.get('series')} | form={m.get('form')} | 底盘{m.get('parts_count')}件 ¥{m.get('total_price'):.0f}")
if not models:
    print("\n  ❌ 无机型 → 流程中止（方案空）")
    sys.exit(0)

print("\n【3️⃣  KP 配件匹配 match_kp（per-机型，对齐线上 executor）】")
_mk_cfg = _default_node_configs()["match_kp"]
plans = []
for bl in models:
    type_name = bl.get("server_type_name") or ""
    type_cats = kp_categories_for_type(type_name, _mk_cfg.get("type_packages"), ext.get("categories"))
    eff_cats = list(dict.fromkeys(type_cats + (ext.get("categories") or [])))
    bl_kp = pick_kp_parts(eff_cats, ext.get("keywords", []),
                          representative_pick=_resolve_budget_strategy(ext.get("budget")),
                          spec_rules=_mk_cfg.get("spec_rules"),
                          fallback_strategy="fallback_representative",
                          requirement_text=text,
                          qty_map=ext.get("qty_map"),
                          qty_per_token=ext.get("qty_per_token"),
                          spec_search_terms=ext.get("spec_search_terms"),
                          model_token_regex=cfg.get("model_token_regex"),
                          mem_signal=ext.get("mem_signal"),
                          cpu_signal=ext.get("cpu_signal"),
                          multi_spec_filters=ext.get("multi_spec_filters"),
                          drive_groups=ext.get("drive_groups"),
                          gpu_groups=ext.get("gpu_groups"),
                          mem_groups=ext.get("mem_groups"))
    plans.append((_p := build_plan(bl, bl_kp)))
    _sig_w = (ext.get("psu_signal") or {}).get("wattage")
    _sig_q = (ext.get("psu_signal") or {}).get("qty")
    if _sig_w or _sig_q:  # 需求文本功率/数量优先覆盖 build_plan 推断（合并保留 bp_type/cable 派生）
        _cs = _p.get("chassis_signals") or {}
        if _sig_w:
            _cs = {**_cs, "psu_wattage": _sig_w}
        if _sig_q:
            _cs = {**_cs, "psu_qty": int(_sig_q)}
        _p["chassis_signals"] = _cs
    unmatched = [kp for kp in bl_kp if kp.get("unmatched")]
    print(f"  • {bl.get('name')} ({type_name or '-'}) 套餐={type_cats} 配 {len(bl_kp)} 件" + (f" ⚠{len(unmatched)} unmatched" if unmatched else ""))
    for kp in bl_kp:
        flag = " ⚠unmatched" if kp.get("unmatched") else ""
        qty = kp.get("qty") or 1
        qty_str = f" ×{qty}" if qty > 1 else ""
        print(f"    [{kp.get('category','?'):22}] {kp.get('pn','?')[:22]:22} ¥{kp.get('unit_price') or 0}{qty_str}{flag}")

print("\n【4️⃣  组合整机方案 build_plan】")
apply_budget_check(plans, ext.get("budget"))
for i, p in enumerate(plans, 1):
    s = p.get("summary", {})
    print(f"  方案{i}: {p.get('name')} | 底盘{s.get('parts_count')}件 + KP{s.get('kp_count')}件 | 总价 ¥{s.get('total_cost',0):.2f}")
    if p.get("over_budget"):
        print(f"    ⚠ 超预算 ¥{p['over_budget']['amount']:.2f}（超 {p['over_budget']['ratio']*100:.0f}%）")
    if p.get("underspend"):
        print(f"    💡 仅用预算 {p['underspend']['ratio']*100:.0f}%，可升级配置（还剩 ¥{p['underspend']['amount']:.2f}）")
    if p.get("selling_points"):
        print(f"    卖点: {p['selling_points']}")
print("\n" + "=" * 72)
