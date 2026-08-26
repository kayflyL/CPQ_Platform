import io
p=r"app\services\capability_executor.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
old="    intent = str((idata or {}).get(\"intent\") or \"\").strip().lower()\n\n    if intent == \"cancel\":"
new="    intent = str((idata or {}).get(\"intent\") or \"\").strip().lower()\n    ctx[\"plan_intent\"] = intent\n\n    if intent == \"cancel\":"
assert old in s, "anchor not found"
s=s.replace(old,new,1)
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("ok")
