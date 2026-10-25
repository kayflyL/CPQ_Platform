---
name: wp-tile-no-bullets-typographic-hierarchy
description: WP/Metro 磁贴列表预览从不用圆点/项目符号，靠字号+字重+透明度做层级
metadata: 
  node_type: memory
  type: reference
  originSessionId: 76f365ec-b764-4bde-89ea-375b665fc794
  modified: 2026-08-11T16:36:20.642Z
---

WP / Win10 Live Tile 的多条目预览磁贴(邮件/消息/最新商机这类)**从不用圆点、项目符号、前缀图标**——这是 Metro 设计语言的核心原则,有 Microsoft 官方 TileTemplateType 枚举佐证(每个模板都是"N strings of regular text on N lines",N 行裸文本逐行堆叠)。

"列表感"靠**排版层级**实现,不是符号装饰:
1. **字号 + 字重 + 透明度层级**:主体 subtitle(20epx)/条目 caption(12epx),辅助信息用 captionSubtle(opacity 60%)
2. **行间距分隔**:必要时插空 `<text/>` 撑留白,无分隔线、无缩进
3. **分组语义**:group/subgroup,列间自动 8px

磁贴背景纯色(flat solid,无玻璃/磨砂),文字白字。但我们 Glass Console 体系用玻璃 token + 主题文字色。

**How to apply**:做磁贴式列表/卡片预览时,每条 = 裸文本(主体粗 + 辅助信息小字降透明度同行),不要加圆点/图标前缀。曾因为加色点圆点被用户嫌丑——那就是反规范。来源:Microsoft Learn TileTemplateType / Create adaptive tiles。

WP 磁贴其他规范见 [[wp-tile-corner-radius]](圆角 0-8px)。
