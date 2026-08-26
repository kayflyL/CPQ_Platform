import io
p = "backend/app/services/workflow_persona.txt"
s = io.open(p, encoding="utf-8").read()
old = "- 先接住用户的话，再回到正题。用户闲聊、问你的身份、问是不是用来打游戏、讲题外话时，用一两句友好回应，然后礼貌、简短地拉回服务器选型；不要生硬拒绝，也不要长篇说教。"
new = "- 先接住用户的话，再回到正题。用户闲聊、问你的身份、问是不是用来打游戏、讲题外话时，用一两句友好回应，然后在结尾温和地提一句“有服务器需求随时找我/现在想了解哪类服务器”，不要生硬拒绝，也不要长篇说教、不要机械复读。"
if old not in s:
    raise SystemExit("persona anchor not found")
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched persona")
