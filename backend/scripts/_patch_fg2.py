from pathlib import Path
p = Path(r"D:\CPQ_Platform_V1\backend\app\services\feasibility_guard.py")
s = p.read_text(encoding="utf-8")

start_marker = "    from app.services import semantic_contract as _sc\n"
end_marker = '            warnings.append(f"需求 {gc} 张 GPU 放在 {form} 机箱不太可行，通常需要 {expected} 机箱")\n'
i = s.index(start_marker)
j = s.index(end_marker) + len(end_marker)

new = '''    # GPU 卡数唯一真值源 = ext.gpu_groups（需求侧结构化事实）；不再读 semantic.workload.gpu_count，
    # 也不再用 gpu_form_map 死区间猜形态——真实槽位能力由下方 base_config.gpu_slots 判定。
    gc = 0
    _ggs = ext.get("gpu_groups") or []
    if isinstance(_ggs, list):
        gc = sum(int(g.get("qty") or 0) for g in _ggs if isinstance(g, dict))

'''
s = s[:i] + new + s[j:]
p.write_text(s, encoding="utf-8")
print("patched feasibility_guard block")
