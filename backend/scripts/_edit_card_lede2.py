import io
p=r"app\services\colleague_turn_service.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
old='''"按你需求，我从服务器目录筛出以下候选机型；点击卡片可进入详情页自行配置："'''
assert old in s, "sentence not found"
# replace the literal sentence with a placeholder call to question data
s=s.replace(old, '''_card_lede''', 1)
# now insert the lede computation before the _add_assistant_message call that uses _card_lede
anchor='''_card_msg = _add_assistant_message(
                                thread_id, colleague,
                                _card_lede,'''
assert anchor in s, "card msg anchor missing"
new_anchor='''_card_lede = str(question or "").strip()
                            if not _card_lede:
                                _names = "、".join(str((c or {}).get("name") or "") for c in _cards if c)
                                _card_lede = (("候选机型：" + _names) if _names else "候选机型")
                            _card_msg = _add_assistant_message(
                                thread_id, colleague,
                                _card_lede,'''
s=s.replace(anchor,new_anchor,1)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok")
