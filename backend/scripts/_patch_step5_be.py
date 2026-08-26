import re
from pathlib import Path

# 1) system_config_repo.py: strip label from _DEFAULT_KP_SLOT_GROUP_MAP + _ensure strip list
p = Path(r"D:\CPQ_Platform_V1\backend\app\repository\system_config_repo.py")
s = p.read_text(encoding="utf-8")
n1 = s.count('"label": "')
s2 = re.sub(r'("key": "(?:cpu|memory|storage|gpu|nic|raid|psu)", )"label": "[^"]*", ', r'\1', s)
print("removed labels:", n1 - s2.count('"label": "'))

old_ensure = '''            for _k in ("level", "required", "ask", "default_ok"):
                if _k in v:
                    v.pop(_k, None)
                    changed = True
'''
new_ensure = '''            for _k in ("level", "required", "ask", "default_ok", "label"):
                if _k in v:
                    v.pop(_k, None)
                    changed = True
'''
assert old_ensure in s2
s2 = s2.replace(old_ensure, new_ensure, 1)
p.write_text(s2, encoding="utf-8")
print("ok system_config_repo")

# 2) requirement_slots.py: derive label from canonical key
p = Path(r"D:\CPQ_Platform_V1\backend\app\services\requirement_slots.py")
s = p.read_text(encoding="utf-8")

anchor = "_FALLBACK_SLOTS = [dict(x) for x in _FALLBACK_BASIC_SLOTS + _FALLBACK_KP_SLOTS]\n"
helper = anchor + '''
# 部件槽位唯一中文展示名来源（与前端 PART_OPTIONS 一致；kp_slot_group_map 不再存 label）
_PART_SLOT_LABELS = {x["key"]: x["label"] for x in _FALLBACK_KP_SLOTS}


def _part_slot_label(key: str) -> str:
    return _PART_SLOT_LABELS.get(key, key)


'''
assert anchor in s
s = s.replace(anchor, helper, 1)

old_label = '        d.setdefault("label", key)\n'
new_label = '        d["label"] = _part_slot_label(key)\n'
assert old_label in s
s = s.replace(old_label, new_label, 1)
p.write_text(s, encoding="utf-8")
print("ok requirement_slots")
