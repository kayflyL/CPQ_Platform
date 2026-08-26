import io, os
# 1) fix requirement_rule_catalog.py: remove 盘 from disk default to preserve behavior
p1 = os.path.join(r"D:\CPQ_Platform_V1", "backend", "app", "services", "requirement_rule_catalog.py")
with io.open(p1, "r", encoding="utf-8") as f:
    s = f.read()
old_line = '    "disk": {"cat": ["硬盘", "SSD", "HDD", "DISK", "盘"]},\n'
new_line = '    "disk": {"cat": ["硬盘", "SSD", "HDD", "DISK"]},\n'
assert old_line in s, "disk line not found"
s = s.replace(old_line, new_line, 1)
with io.open(p1, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)

# 2) refactor _estimate_system_load in candidate_search.py
p2 = os.path.join(r"D:\CPQ_Platform_V1", "backend", "app", "api", "candidate_search.py")
with io.open(p2, "r", encoding="utf-8") as f:
    lines = f.readlines()
# Find function start and body; replace classification block
start = next(i for i,l in enumerate(lines) if l.strip() == "def _estimate_system_load(kp_parts: list[dict]) -> int:")
# read until the function ends at dedent (line starting with def at same indent or blank then def)
end = None
for i in range(start+1, len(lines)):
    if lines[i].startswith("def ") and not lines[i].startswith("    def "):
        end = i
        break
if end is None:
    # find first non-indented def after start
    for i in range(start+1, len(lines)):
        if lines[i].startswith("def "):
            end = i; break
body = "".join(lines[start:end])
# Replace the classification chain inside the for loop
new_body = '''def _estimate_system_load(kp_parts: list[dict]) -> int:
    """按 KP 件粗估整机负载（W）。CPU 查 TDP 表，其余按件均摊——纯估算用于电源建议，
    不是精确功耗计算。数值与品类关键词均来自规则库（power_calibration / part_family_keywords）。"""
    from app.services.requirement_rule_catalog import part_family_keywords
    calib = _load_power_calibration()
    _pfk = part_family_keywords()

    def _match(fam: str, cu: str, cat: str, nu: str) -> bool:
        kws = _pfk.get(fam) or {}
        return (any(k in cu for k in kws.get("cat_upper", []))
                or any(k in cat for k in kws.get("cat", []))
                or any(k in nu for k in kws.get("name_upper", [])))

    load = int(calib.get("sys_base_w") or 0)
    tdp_map = calib.get("cpu_tdp_map") or {}
    default_cpu_tdp = calib.get("default_cpu_tdp") or 0
    mem_default_w = calib.get("mem_stick_w") or 0
    mem_by_cap = calib.get("mem_stick_w_by_cap") or []
    sata_w = calib.get("sata_drive_w") or 0
    nvme_w = calib.get("nvme_drive_w") or 0
    nic_w = calib.get("nic_w") or 0
    raid_w = calib.get("raid_w") or 0
    for kp in kp_parts or []:
        cat = kp.get("category") or ""
        name = f"{kp.get('name') or ''} {kp.get('matched_spec') or ''}"
        qty = int(kp.get("qty") or 1)
        cu = cat.upper()
        nu = name.upper()
        if _match("cpu", cu, cat, nu):
            _tdp = None
            try:
                _tdp = float((kp.get("specs") or {}).get("tdp") or 0) or None
            except (TypeError, ValueError):
                _tdp = None
            if _tdp:
                load += _tdp * qty
            else:
                m = re.search(r"(\\d{4})", name)
                tdp = float(tdp_map.get(m.group(1).lower(), default_cpu_tdp) if m else default_cpu_tdp)
                load += tdp * qty
        elif _match("memory", cu, cat, nu):
            _m = re.search(r"(\\d{1,3})\\s*G\\s*B?\\b", name, re.I)
            _cap = int(_m.group(1)) if _m else 0
            _w = mem_default_w
            for _cm, _cw in mem_by_cap:
                if _cap <= _cm:
                    _w = _cw
                    break
            load += _w * qty
        elif _match("nvme", cu, cat, nu):
            load += nvme_w * qty
        elif _match("disk", cu, cat, nu):
            load += sata_w * qty
        elif _match("nic", cu, cat, nu):
            load += nic_w * qty
        elif _match("raid", cu, cat, nu):
            load += raid_w
    return int(load)


'''
with io.open(p2, "w", encoding="utf-8", newline="\n") as f:
    f.writelines(lines[:start] + [new_body] + lines[end:])
print("refactored _estimate_system_load; body_old_len=", len(body))
