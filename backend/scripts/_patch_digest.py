# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "agent_tools.py")
text = io.open(path, encoding="utf-8").read()

old = '''    digest = [{
        "config_id": b.get("id"),
        "server_model_id": b.get("server_model_id"),
        "name": b.get("name") or "",
        "series": b.get("series") or "",
        "form": b.get("form") or "",
        "bays": b.get("bays"),
        "recommend_level": b.get("recommend_level") or "",
        "selling_points": _truncate(b.get("selling_points") or "", 300),
        "match_stage": b.get("match_stage"),
        "fallback_note": b.get("fallback_note") or "",
    } for b in baselines]'''

new = '''    digest = []
    for b in baselines:
        _bc = b.get("base_config") if isinstance(b.get("base_config"), dict) else {}
        _cap_v = lambda k: b.get(k) if b.get(k) is not None else _bc.get(k)
        _base = {
            "config_id": b.get("id"),
            "id": b.get("id"),
            "server_model_id": b.get("server_model_id"),
            "name": b.get("name") or "",
            "model": b.get("model") or b.get("name") or "",
            "series": b.get("series") or "",
            "form": b.get("form") or "",
            "bays": _cap_v("bays"),
            "max_cpu": _cap_v("max_cpu"),
            "max_dimm": _cap_v("max_dimm"),
            "gpu_slots": _bc.get("gpu_slots"),
            "psu_bays": _bc.get("psu_bays"),
            "total_price": float(b.get("total_price") or 0),
            "bom_template_id": b.get("bom_template_id"),
            "base_config": _bc,
        }
        digest.append({
            "config_id": b.get("id"),
            "server_model_id": b.get("server_model_id"),
            "name": b.get("name") or "",
            "series": b.get("series") or "",
            "form": b.get("form") or "",
            "bays": b.get("bays"),
            "recommend_level": b.get("recommend_level") or "",
            "selling_points": _truncate(b.get("selling_points") or "", 300),
            "match_stage": b.get("match_stage"),
            "fallback_note": b.get("fallback_note") or "",
            "baseline": _base,
        })'''

assert old in text, "select_models digest anchor missing"
text = text.replace(old, new, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("select_models digest patched OK")
