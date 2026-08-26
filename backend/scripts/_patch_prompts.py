# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "repository", "reasoning_flow_repo.py")
text = io.open(path, encoding="utf-8").read()

# 明确 final 契约，避免模型不带 action 导致循环
text = text.replace("最终只输出一个 JSON 对象", "最终必须用 final 动作，且 answer 字段是如下 JSON 对象")
# 收敛轮数 6 -> 4, 5 -> 4（只针对新节点）
text = text.replace('"max_iterations": 6,', '"max_iterations": 4,')
text = text.replace('"max_iterations": 5,', '"max_iterations": 4,')
io.open(path, "w", encoding="utf-8").write(text)
print("prompts+iter patched OK")
