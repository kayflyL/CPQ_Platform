---
name: prototype-is-the-spec
description: 用户铁律：原型经确认后就是规格书，落地不许自砍范围；砍功能=偏离验收基准
metadata:
  node_type: memory
  type: feedback
  originSessionId: fcb42c79-ac71-489d-802d-96912f5bcdc0
  modified: 2026-10-01T21:13:19.096Z
---

2026-10-02 用户在 office-room-chat 原型落地时发火："做原型的目的就是照着原型做呀，你不做啥意思"——我把原型里的引用回复/小声聊/窗口级历史全屏自行归入"不做"挂账，用户视为交付不符。

**Why:** 本项目惯例是 原型 → 用户确认 → 照做，原型一旦被确认就是验收基准；实现方擅自缩小范围=替用户做了产品决策。

**How to apply:** 落地前对着原型逐条清点功能，全量实现；确实做不了的（缺数据源/需产品决策的，如 whisper 需要 AI↔AI 私聊通道），在动手前说清原因并让用户拍板，不要先斩后奏地写进"不做"清单。真做不了的和"觉得可以缓"的要分开汇报。**交互接线也要照原型**：原型的 JS 里藏着交互语义（如消息发送人 span 带 data-persona=点消息头像弹名片），别只照视觉不看接线；挂错位置（点侧栏头像弹名片）比少做更招火。相关：[[visual-changes-let-user-confirm-first]] [[autonomy-large-tasks]]
