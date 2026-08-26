import io, os
p = os.path.join(r"D:\CPQ_Platform_V1", "backend", "app", "services", "capabilities.py")
with io.open(p, "r", encoding="utf-8") as f:
    lines = f.readlines()
out = []
i = 0
while i < len(lines):
    if lines[i].strip() == "sys_prompt = (sys_prompt +":
        i += 1
        while i < len(lines) and not lines[i].strip().endswith('")'):
            i += 1
        i += 1
        continue
    if '可按此抽槽（只填用户明确表达的）：' in lines[i]:
        lines[i] = lines[i].replace('可按此抽槽（只填用户明确表达的）：', '请按此映射本次确认的字段：')
    out.append(lines[i])
    i += 1
with io.open(p, "w", encoding="utf-8", newline="\n") as f:
    f.writelines(out)
print("patched capabilities.py; new len", len(out))
