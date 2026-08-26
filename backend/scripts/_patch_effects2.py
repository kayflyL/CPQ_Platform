# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "reasoning_executor.py")
text = io.open(path, encoding="utf-8").read()
old = '        "structured": structured,\n    }'
new = '        "structured": structured,\n        "effects": effects,\n    }'
assert old in text
text = text.replace(old, new, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("return effects patched OK")
