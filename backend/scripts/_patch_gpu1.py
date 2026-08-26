from pathlib import Path
p = Path(r"D:\CPQ_Platform_V1\backend\app\services\capabilities.py")
s = p.read_text(encoding="utf-8")

old_doc = '    """把语义契约参考（workload_map/compliance_map/gpu_form_map）注入 agent 上下文，供它按规则推断。"""'
new_doc = '    """把语义契约参考（workload_map/compliance_map）注入 agent 上下文，供它按规则推断。"""'
assert old_doc in s
s = s.replace(old_doc, new_doc, 1)

old_block = '''    gm = _rc.gpu_form_map(rule_types)
    if gm:
        lines = ["  %s-%s卡 → %s" % (r.get("gpu_count_min"), r.get("gpu_count_max"), r.get("form")) for r in gm]
        chunks.append("GPU卡数→机箱形态：\\n" + "\\n".join(lines))
'''
assert old_block in s, "gpu_form_map block not found"
s = s.replace(old_block, "", 1)

p.write_text(s, encoding="utf-8")
print("patched _semantic_ref_text")
