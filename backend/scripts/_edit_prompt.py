import io
p = "app/services/workflow_intent.py"
s = io.open(p, encoding="utf-8").read()

old = '''        "- refine: 用户在补充/改口需求（场景、类型、系列、形态、预算、用途），能让下一步推荐更准。\\n"
        "- auto_recommend: 用户把决定权交给系统。例：你推荐/都行/随便/帮我配/最合适的。\\n"
        "- self_config: 用户要自己配置。例：我自己配/我来自配/我去详情页。\\n"
        "- cancel: 用户要取消本次配置。例：取消/不配了/算了。\\n"
        "- confirm_choice: 用户在候选里确认一个。例：选第1个/就这个/选XX型号。\\n"
        "- reselect: 用户要重新选机型。例：重选/换一个/重新选。\\n"
        "- grasp: 用户正常回答/给出需求信息，继续走流程。\\n"
        "- noise: 与需求无关的闲聊、客套、表情、无意义内容。\\n"
        "规则：只有 explain/noise 需要用 reply 给一句自然中文回应；其余 reply 留空。"'''

new = '''        "- refine: 用户在**给出或改口需求**（场景、类型、系列、形态、预算、用途、规格）。例：我要一台通用计算服务器，2U。\\n"
        "- ask: 用户在**提问**，想了解候选/目录/价格/配置/区别/流程/原因，而不是在给需求。例：这个多少钱/这台什么配置/这两种有什么区别/怎么选/为什么推荐这个/有XX吗。\\n"
        "- auto_recommend: 用户把决定权交给系统。例：你推荐/都行/随便/帮我配/最合适的。\\n"
        "- self_config: 用户要自己配置。例：我自己配/我来自配/我去详情页。\\n"
        "- cancel: 用户要取消本次配置。例：取消/不配了/算了。\\n"
        "- confirm_choice: 用户在候选里确认一个。例：选第1个/就这个/选XX型号。\\n"
        "- reselect: 用户要重新选机型。例：重选/换一个/重新选。\\n"
        "- grasp: 用户在正常回答一个封闭问题/给出简短确认，应继续走流程。例：通用计算（回答上一句的类型询问）。\\n"
        "- noise: 与需求无关的闲聊、客套、表情、无意义内容。\\n"
        "关键区分：**给需求/回答封闭问题 → refine/grasp；想了解信息/提问 → ask/explain/list_catalog；决定权（推荐/自配/取消）→ auto_recommend/self_config/cancel。**\\n"
        "规则：只有 explain/noise/ask 需要用 reply 给一句自然中文回应（ask 的 reply 说明你理解的问题、或提示需要选型后确认数据）；其余 reply 留空。"'''

if old not in s:
    raise SystemExit("prompt anchor not found")
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched resolve_intent prompt")
