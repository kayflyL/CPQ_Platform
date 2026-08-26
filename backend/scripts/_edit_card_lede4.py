import io, re
p=r"app\services\colleague_turn_service.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()

# 1) replace the fixed sentence with _card_lede
fixed='"按你需求，我从服务器目录筛出以下候选机型；点击卡片可进入详情页自行配置："'
assert fixed in s
s=s.replace(fixed, '_card_lede,', 1)

# 2) locate the _card_msg = _add_assistant_message( block start line index
lines=s.split("\n")
idx=None
for i,l in enumerate(lines):
    if l.strip().startswith("_card_msg = _add_assistant_message("):
        idx=i; break
assert idx is not None, "_card_msg call not found"
indent=lines[idx][:len(lines[idx])-len(lines[idx].lstrip())]
inner=indent+"    "
lede='''{i}_card_lede = str(question or "").strip()
{i}if not _card_lede:
{i}    _names = "、".join(str((c or {}).get("name") or "") for c in _cards if c)
{i}    _card_lede = (("候选机型：" + _names) if _names else "候选机型")
'''.format(i=indent)
lines.insert(idx, lede)
s="\n".join(lines)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok inserted at line", idx)
