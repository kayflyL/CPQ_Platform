import io, re
p=r"app\services\colleague_turn_service.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
pat=re.compile(r'(_card_msg = _add_assistant_message\(\s*thread_id, colleague,\s*)"按你需求，我从服务器目录筛出以下候选机型；点击卡片可进入详情页自行配置：",', re.S)
def repl(m):
    return m.group(1) + '_card_lede,'
assert pat.search(s), "pattern not found"
s=pat.sub(repl, s, count=1)
# insert lede computation before the _card_msg block
anchor='_card_msg = _add_assistant_message(\n                                thread_id, colleague,\n                                _card_lede,'
assert anchor in s, "card msg anchor missing after sub"
insb='''_card_lede = str(question or "").strip()
                            if not _card_lede:
                                _names = "、".join(str((c or {}).get("name") or "") for c in _cards if c)
                                _card_lede = (("候选机型：" + _names) if _names else "候选机型")
                            _card_msg = _add_assistant_message(
                                thread_id, colleague,
                                _card_lede,'''
s=s.replace(anchor, insb, 1)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok")
