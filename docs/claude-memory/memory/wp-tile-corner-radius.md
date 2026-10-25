---
name: wp-tile-corner-radius
description: WP Live Tile 圆角规范(原教旨0px/Win11 Fluent 4-8px) + 磁贴间距8-10px + 内容左对齐
metadata: 
  node_type: memory
  type: reference
  originSessionId: 76f365ec-b764-4bde-89ea-375b665fc794
  modified: 2026-10-15T13:05:15.758Z
---

Windows Live Tile / Metro 磁贴的几何规范(查证自 Microsoft Learn + tile-design skill):

- **圆角**:WP/Win10 Live Tile 原教旨 = **0px(直角)**,这是 Metro"真实数字感"的硬朗标志;Windows 11 Fluent 取代 Live Tile 后用 **4px(控件)/8px(窗口/对话框大容器)/0px(贴靠)**;Fluent 2 默认矩形 4px,大/XL 组件 8-12px。M3 卡片默认 12dp;iOS 大卡片 10-16pt(连续曲线)。
- **磁贴间距(gutter)**:WP8 = **10px**,tile-design 实现参考 8px。
- **内容对齐**:图标**左上角**,标签**左下角**,两者都**左对齐不居中**。
- **背景**:**纯色扁平填充**(无渐变/纹理/阴影),高饱和强调色;原生无玻璃/磨砂。深色背景纯黑。

**How to apply**:本项目驾驶舱手机端磁贴用 **var(--cpq-radius-md)=8px**（用户定的 8px，圆角阶梯 v2 后落 md 卡片档；2026-10-15 已把 .m-ctile/.m-add-tile 从误档 lg 归位 md）、8px 间距、玻璃 token(glass-3-bg)而非死色块(和 Glass Console 体系共存)。多色相实心平涂色复用 PIE_COLORS,边色用 segmentBorder 主题感知。磁贴列表内容设计见 [[wp-tile-no-bullets-typographic-hierarchy]]。圆角阶梯全貌见 [[design-spec-tokens]]。
