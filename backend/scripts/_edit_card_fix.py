import io
p=r"app\services\colleague_turn_service.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
assert "_card_lede,," in s
s=s.replace("_card_lede,,", "_card_lede,", 1)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok")
