from pathlib import Path

# 1) requirement_rule_catalog.py: remove gpu_form_map function
p = Path(r"D:\CPQ_Platform_V1\backend\app\services\requirement_rule_catalog.py")
s = p.read_text(encoding="utf-8")
old = '''def gpu_form_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """GPU 数量 → 机箱形态（单卡→2U，多卡→4U）。"""
    return [dict(x) for x in active_bodies("gpu_form_map", enabled_types) if x]


'''
assert old in s
s = s.replace(old, "", 1)
p.write_text(s, encoding="utf-8")
print("ok catalog")

# 2) requirement_rule_repo.py: remove from _VALID_TYPE and seeds
p = Path(r"D:\CPQ_Platform_V1\backend\app\repository\requirement_rule_repo.py")
s = p.read_text(encoding="utf-8")
old = '    "platform_series_map", "cpu_vendor_map", "raid_level_map", "workload_map", "compliance_map", "gpu_form_map",\n'
new = '    "platform_series_map", "cpu_vendor_map", "raid_level_map", "workload_map", "compliance_map",\n'
assert old in s
s = s.replace(old, new, 1)

old2 = '''    {"type": "gpu_form_map", "name": "1-4卡 → 2U", "body": {"gpu_count_min": 1, "gpu_count_max": 4, "form": "2U"}},
    {"type": "gpu_form_map", "name": "5-16卡 → 4U", "body": {"gpu_count_min": 5, "gpu_count_max": 16, "form": "4U"}},

'''
assert old2 in s
s = s.replace(old2, "", 1)
p.write_text(s, encoding="utf-8")
print("ok repo")

# 3) requirement_rules.py: remove from API _VALID_TYPE
p = Path(r"D:\CPQ_Platform_V1\backend\app\api\requirement_rules.py")
s = p.read_text(encoding="utf-8")
old = '    "platform_series_map", "raid_level_map", "workload_map", "compliance_map", "gpu_form_map",\n'
new = '    "platform_series_map", "raid_level_map", "workload_map", "compliance_map",\n'
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok api")
