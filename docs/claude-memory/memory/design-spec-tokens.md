---
name: design-spec-tokens
description: 前端设计规范三层体系落地——间距/字阶/圆角 token + docs/设计规范.md + HTML 活样张，存量绞杀式迁移
metadata:
  node_type: memory
  type: project
  originSessionId: 55facdc8-a66a-47be-ad81-4a5256b3f1b9
  modified: 2026-10-15T13:20:41.411Z
---

2026-10-08 定调并落地（用户看了中移 OnePower 规范图后批准）：本项目设计规范 = 三层权威，改前端必看。

- **值唯一来源**：`frontend/src/styles/tokens.css` 新增 `--cpq-space-1..6`（4/8/12/16/24/32，4px 栅格封闭六档）+ 字阶标题档 `--cpq-font-size-xl/2xl/3xl`（20/24/30）+ 字重三档 + 行高两档。改值只改这一处。
- **圆角阶梯 v3（2026-10-15 用户两轮反馈「太圆」后定稿）**：`xs 2 / sm 4 / md 6 / lg 8 / xl 12 / full 999`，按角色选档（xs 微件/sm 控件/md 卡片主力/lg 窗口/xl 特大浮层/full 药丸）；v1 8/12/16/20 作废。当天全站清扫：127 文件 1060 处硬编码 border-radius 归档 token，此后 border-radius 禁止写 px 字面值（50%/0 除外）；antd 主题 token `borderRadius: 4` 已同步（App.vue）；漏网方角卡已补齐（KP 配件 .sc-panel、料号库 stat-card/recent-panel → md；全屏态/表格输入框/贴边抽屉的 0 是功能性直角保留）。档表在 Style Guide §4.1。
- **用法与理由**：`docs/设计规范.md`——antd 之上的增量（间距/字阶/卡片节奏/骨架/组件用法决策/铁律清单§6 收编散落规矩），规范语言 必须/应/可。
- **材质层**：`docs/Frontend_Style_Guide.md`（2026-07-21 现行，用户 Obsidian 在读）——玻璃三级工具类与禁嵌套、overlay 三系语义、投影色、antd 覆盖原则、signature。⚠️ `frontend/docs/STYLE_GUIDE.md`（7-07 赛博暗色死规范，主色 #00F5D4 已全站清除）10-08 已删，勿再引用或重建。
- **可视样张**：`docs/prototypes/设计规范.html`——全部 var() 引用真 token（相对路径链 ../../frontend/src/styles/tokens.css），带标注芯片/骨架图/Do-Don't 违例对照/按钮四态，可切深浅主题。
- **执行**：CLAUDE.md「前端设计规范(硬性)」节=新代码布局间距/标题必须用 token，≤4px 光学校正例外；存量不专项清洗，改哪页迁哪页，共享面（BomTable/磁贴墙/布局壳）优先。
- 参考图（OnePower 规范）学的是方法（封闭尺度/状态矩阵/决策带理由），不是数值——他们的 18px 卡片内距不在自己宣称的 8/16/24 栅格上，勿照搬。

**Why**：全站 3300 处间距硬编码分散在 135/144 个 vue 文件（1~14px 每个整数都有人用，仅 48% 落 4px 栅格），唯一「改一处生效多处」的机制只有共享组件；token 化后才有全局生效能力。

**How to apply**：写/改前端页面前先读 [[prototype-is-the-spec]] 同级的 docs/设计规范.md；新间距一律 var(--cpq-space-*)；发现档外值布局间距当场迁；新铁律进规范 §6。碰宣传物料拟真复刻也走这套 token（[[promo-realistic-replica]]）。
