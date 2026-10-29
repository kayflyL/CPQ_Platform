---
name: no-card-color-strips
description: 全局设计铁律：一切设计产出禁止左侧竖向彩色装饰条（AI味设计）；层级靠字号字重留白；彩色只做小圆点/小徽标（deck-line 仅标题级水平线）
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 67032332-865f-46e7-80ea-4fa31be82ba9
  modified: 2026-10-15T07:52:11.510Z
---

**所有设计产出（页面/卡片/磁贴/弹窗/KPI 卡/callout/图表/原型 HTML）一律禁止左侧竖向彩色装饰条**——用户 2026-10-03 升格定调：「所有的设计，不准出现左侧彩色装饰条这种明显 AI 的设计」。此前 2026-09-19 已因配件页磁贴左色条被批过一次，10-03 在 2B 编辑器原型里再犯（KPI 卡 ::before 左蓝条 + callout border-left 粗彩边），两案并案成全局铁律。

**Why:** 左侧竖彩条是最典型的 AI 生成味装饰，用户两次点名；全站真正的竖线语言只有标题级 `deck-line`（3×12px，OpportunityCharts 磁贴标题在用），不能放大成卡片级。

**How to apply:**
- 层级=字号+字重+透明度+留白，不加装饰条；
- 彩色只允许：卡片内**小圆点**识别（固定调色板轮换）、小徽标 chip、语义色角标（如涨幅 ↑）；
- callout/提示卡=整圈细边框+浅色底+图标，**不搞左边粗彩边**；
- 标题级水平 deck-line 保留，但不得竖置、不得下放到卡片级；
- 写任何 CSS 前自查：`::before`/`border-left` 造竖向色条的写法一律否掉。
- **存量清理（2026-10-15）**：聊天面板族三处旧彩条已删——AssistantPanel `.ap-quote-bar`（composer 引用条+工作流装填条共用）、AssistantMessageItem `.am-quote-card`（消息内引用卡）、AiSettingsPanel `.thread-msg.role-user/role-assistant`（消息角色 3px 条，角色区分靠 head 文本）。复用既有组件样式前先看它有没有带彩条，别把旧违规一起复制。
相关：[[glass-console-system]]、[[wp-tile-no-bullets-typography-hierarchy]]。
