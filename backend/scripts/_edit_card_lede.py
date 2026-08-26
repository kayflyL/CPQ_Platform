import io
p=r"app\services\colleague_turn_service.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
old='''                            _card_msg = _add_assistant_message(
                                thread_id, colleague,
                                "按你需求，我从服务器目录筛出以下候选机型；点击卡片可进入详情页自行配置：",
                                kind="business_artifact",
                                data=json.dumps(_card_data, ensure_ascii=False, default=str),
                            )'''
new='''                            _card_lede = str(question or "").strip()
                            if not _card_lede:
                                _names = "、".join(str((c or {}).get("name") or "") for c in _cards if c)
                                _card_lede = (("候选机型：" + _names) if _names else "候选机型")
                            _card_msg = _add_assistant_message(
                                thread_id, colleague,
                                _card_lede,
                                kind="business_artifact",
                                data=json.dumps(_card_data, ensure_ascii=False, default=str),
                            )'''
assert old in s, "card title anchor missing"
s=s.replace(old,new,1)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok")
