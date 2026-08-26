import io
p = "backend/app/services/workflow_intent_classifier.txt"
s = io.open(p, encoding="utf-8").read()
old_cancel = "- cancel: 用户要取消本次配置。例：取消/不配了/算了。"
new_cancel = "- cancel: 用户明确结束本次方案配置。例：取消/不配了/算了/结束配置/不要了。"
old_noise = "- noise: 与需求无关的闲聊、客套、表情、无意义内容。"
new_noise = "- noise: 与需求无关的闲聊、客套、表情、社交话，以及“我想聊天/不想要服务器只想聊天/谢谢/哈哈”这类话，绝不是业务取消。"
s = s.replace(old_cancel, new_cancel, 1).replace(old_noise, new_noise, 1)
s += "\n注意：“只想聊天/不想要服务器、只想陪你聊”属于 noise（无关闲聊），不要判成 cancel；只有明确结束方案配置才判 cancel。"
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched classifier")
