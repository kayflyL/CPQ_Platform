from pathlib import Path
p = Path(r"D:\CPQ_Platform_V1\backend\app\services\portal_flow_adapter.py")
s = p.read_text(encoding="utf-8")

old = '''    gpus = []
    raw_gpu = (ext.get("llm_enhanced") or {}).get("gpu") if isinstance(ext.get("llm_enhanced"), dict) else None
    for group in raw_gpu or []:
        if not isinstance(group, dict):
            continue
        model = group.get("model") or ""
        qty = group.get("qty")
        if model or qty:
            gpus.append({"model": str(model), "qty": _as_int(qty, 1) or 1})
    if not gpus:
        for group in ext.get("gpu_groups") or []:
            if not isinstance(group, dict):
                continue
            tokens = group.get("tokens") or []
            qty = group.get("qty")
            if not tokens and not qty:
                continue
            model = " ".join(str(t) for t in tokens[:2]).strip()
            gpus.append({"model": model, "qty": _as_int(qty, 1) or 1})
'''
new = '''    gpus = []
    for group in ext.get("gpu_groups") or []:
        if not isinstance(group, dict):
            continue
        tokens = group.get("tokens") or []
        qty = group.get("qty")
        if not tokens and not qty:
            continue
        model = " ".join(str(t) for t in tokens[:2]).strip()
        gpus.append({"model": model, "qty": _as_int(qty, 1) or 1})
'''
assert old in s, "portal_flow_adapter gpu block not found"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok portal_flow_adapter")
