import io, os
p = os.path.join(r"D:\CPQ_Platform_V1", "backend", "app", "services", "capabilities.py")
with io.open(p, "r", encoding="utf-8") as f:
    s = f.read()
old = '''    elif missing and not done:
        ctx["clarity"] = "unclear"
    elif missing:
        # 模型自评 done=true：即使还有非硬性缺口（如未给系列），也视为可下沉，交下游得出候选。
        ctx["clarity"] = "partial"
    else:
        ctx["clarity"] = "explicit" if has_model else "partial"'''
new = '''    elif has_model:
        # 客户点名机型是强信号：不再因缺类型/系列/形态把它打成 unclear，交给下游按名称确认/找最近似。
        ctx["clarity"] = "explicit"
    elif missing and not done:
        ctx["clarity"] = "unclear"
    elif missing:
        # 模型自评 done=true：即使还有非硬性缺口（如未给系列），也视为可下沉，交下游得出候选。
        ctx["clarity"] = "partial"
    else:
        ctx["clarity"] = "explicit" if has_model else "partial"'''
assert old in s, "clarity block not found"
s = s.replace(old, new)
with io.open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)
print("patched has_model clarity")
