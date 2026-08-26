import io, os
p = os.path.join(r"D:\CPQ_Platform_V1", "backend", "app", "services", "capabilities.py")
with io.open(p, "r", encoding="utf-8") as f:
    s = f.read()
old_need = "need_ask = bool(missing) and not ctx.get(\"force_complete\") and not ctx.get(\"delegated\") and not _no_progress"
new_need = "need_ask = bool(missing) and not done and not ctx.get(\"force_complete\") and not ctx.get(\"delegated\") and not _no_progress"
assert old_need in s, "need_ask not found"
s = s.replace(old_need, new_need)

old_clarity = '''    elif missing:
        ctx["clarity"] = "unclear"
    else:
        ctx["clarity"] = "explicit" if has_model else "partial"'''
new_clarity = '''    elif missing and not done:
        ctx["clarity"] = "unclear"
    elif missing:
        # 模型自评 done=true：即使还有非硬性缺口（如未给系列），也视为可下沉，交下游得出候选。
        ctx["clarity"] = "partial"
    else:
        ctx["clarity"] = "explicit" if has_model else "partial"'''
assert old_clarity in s, "clarity block not found"
s = s.replace(old_clarity, new_clarity)
with io.open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)
print("patched need_ask + clarity")
