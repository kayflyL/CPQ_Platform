import io, re
files=["app/services/reasoning_executor.py","app/services/capability_executor.py","app/services/colleague_turn_service.py","app/services/capabilities.py"]
kws=["按你需求","点击卡片","暂未找到","我自己配置","已取消本次","请描述","这些是在售","来自服务器目录","整理了几个","从服务器目录筛出","候选机型","NaturalPreamble"]
for f in files:
    try:
        txt=io.open(f,encoding="utf-8").read()
    except Exception as e:
        print(f,"ERR",e); continue
    lines=txt.split("\n")
    for i,l in enumerate(lines,1):
        if any(k in l for k in kws):
            print(f, i, l.strip()[:110])
