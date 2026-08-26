import io
p=r"app\services\colleague_turn_service.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
fixed='"按你需求，我从服务器目录筛出以下候选机型；点击卡片可进入详情页自行配置："'
assert fixed in s
s=s.replace(fixed, '_card_lede,', 1)
lines=s.split("\n")
idx=None
for i,l in enumerate(lines):
    if l.strip().startswith("_card_msg = _add_assistant_message("):
        idx=i; break
assert idx is not None
indent=lines[idx][:len(lines[idx])-len(lines[idx].lstrip())]
lede = (indent + "_card_lede = str(question or \"\").strip()\n"
      + indent + "if not _card_lede:\n"
      + indent + "    _names = \"、\".join(str((c or {}).get(\"name\") or \"\") for c in _cards if c)\n"
      + indent + "    _card_lede = ((\"候选机型：\" + _names) if _names else \"候选机型\")\n")
lines.insert(idx, lede)
s="\n".join(lines)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok line", idx)
