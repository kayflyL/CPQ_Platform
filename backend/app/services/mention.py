"""评论 @提及解析 — 把正文里的 @名字 解析成 user_id 列表。

定调（2026-10-15）：解析只对照真实名册做最长名字优先匹配；@后面拼不出名册
名字的一律是纯文本，不猜、不模糊。权威解析点在 feed 发评论的唯一入口
（feed.post_message → _notify_mentions），前端 @ 浮层只是输入辅助。
"""
from typing import Dict, List

# 名册名字 -> user_id 列表（同名多人时一个名字挂多个 id）


def parse_mentions(body: str, name_to_ids: Dict[str, List[str]]) -> List[str]:
    """扫描 body 中的 @<名字>，返回去重后的 user_id 列表（保持首次出现顺序）。

    规则：
    - 每个 "@" 位置按名字长度降序尝试匹配，命中即消费整段（"@张三丰" 不会
      误伤同册的 "张三"）；
    - 名册里只有 "张三" 而正文是 "@张三丰" 时会命中 "张三"（中文无词边界，
      最长匹配只对名册内互为前缀的名字生效）；
    - 匹配不到名册的 @（含邮箱 a@b.com）原样放过。
    """
    if not body or "@" not in body or not name_to_ids:
        return []
    names = sorted((n for n in name_to_ids if n), key=len, reverse=True)
    if not names:
        return []
    mentioned: List[str] = []
    i = 0
    while i < len(body):
        if body[i] != "@":
            i += 1
            continue
        rest = body[i + 1:]
        hit = next((name for name in names if rest.startswith(name)), None)
        if hit:
            for uid in name_to_ids[hit]:
                if uid and uid not in mentioned:
                    mentioned.append(uid)
            i += 1 + len(hit)
        else:
            i += 1
    return mentioned
