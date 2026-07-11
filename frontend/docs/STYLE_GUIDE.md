# CPQ Platform Style Guide

> **版本**: 1.0  
> **最后更新**: 2026-07-07  
> **维护者**: 开发团队

---

## 目录

1. [设计原则](#1-设计原则)
2. [色彩系统](#2-色彩系统)
3. [字体规范](#3-字体规范)
4. [间距与圆角](#4-间距与圆角)
5. [毛玻璃层级](#5-毛玻璃层级)
6. [阴影系统](#6-阴影系统)
7. [动效规范](#7-动效规范)
8. [背景氛围](#8-背景氛围)
9. [交互反馈](#9-交互反馈)
10. [组件规范](#10-组件规范)
11. [可访问性](#11-可访问性)
12. [文件位置](#12-文件位置)
13. [更新日志](#13-更新日志)

---

## 1. 设计原则

- **Dark B-End**: 面向专业用户的深色后台界面
- **高对比度**: 文字与背景对比度 ≥ 4.5:1，确保可读性
- **轻量毛玻璃**: 半透明层叠营造空间感，避免厚重实体感
- **克制用色**: 主色调为黑灰，仅用 cyan 强调交互焦点
- **动效自然**: 使用 ease-out-expo 曲线，模拟物理惯性

---

## 2. 色彩系统

### 2.1 背景色阶

| Token | Value | 用途 |
|-------|-------|------|
| `--cpq-bg-primary` | `#08090B` | 页面基底、侧边栏 |
| `--cpq-bg-secondary` | `#101217` | 卡片、表格、次级面板 |
| `--cpq-bg-tertiary` | `#171A21` | 表头、输入框、三级容器 |
| `--cpq-bg-sidebar` | `#08090B` | 侧边栏背景 |
| `--cpq-bg-sidebar-header` | `#101217` | 侧边栏头部 |

**原则**: 背景色阶从深到浅递增，层级越深颜色越亮，形成视觉纵深。

### 2.2 文字色阶

| Token | Value | 用途 | 对比度 (vs #08090B) |
|-------|-------|------|---------------------|
| `--cpq-text-primary` | `#E8ECEF` | 主标题、正文 | 13.2:1 ✓ |
| `--cpq-text-secondary` | `#9BA1AA` | 副标题、标签 | 7.8:1 ✓ |
| `--cpq-text-muted` | `#6E7582` | 辅助说明、占位符 | 4.6:1 ✓ |
| `--cpq-text-disabled` | `#3D424D` | 禁用态文字 | 2.1:1 ✗ |

**原则**: 禁用态文字对比度低于 WCAG AA 标准，仅用于不可交互元素。

### 2.3 强调色

| Token | Value | 用途 |
|-------|-------|------|
| `--cpq-accent-primary` | `#00F5D4` | 主按钮、激活态、聚焦边框 |
| `--cpq-accent-primary-light` | `#00F5D4` | Hover 态、链接 |
| `--cpq-accent-success` | `#00F5D4` | 成功状态 |
| `--cpq-accent-warning` | `#F4D28A` | 警告状态 |
| `--cpq-accent-danger` | `#ff4d4f` | 错误状态、删除操作 |

**原则**: Cyan (#00F5D4) 是唯一高饱和色，仅用于交互焦点，避免大面积使用。

### 2.4 边框色

| Token | Value | 用途 |
|-------|-------|------|
| `--cpq-border-primary` | `rgba(255, 255, 255, 0.10)` | 卡片边框、分割线 |
| `--cpq-border-secondary` | `rgba(255, 255, 255, 0.06)` | 次级分割线、表格边框 |
| `--cpq-border-light` | `rgba(255, 255, 255, 0.15)` | 输入框边框、强调边框 |

**原则**: 边框使用半透明白色，与背景融合度更高，避免硬边。

---

## 3. 字体规范

### 3.1 字体族

```css
--cpq-font-family: 
  -apple-system,              /* macOS/iOS 系统字体 */
  BlinkMacSystemFont,         /* macOS Safari */
  'Segoe UI',                 /* Windows */
  Roboto,                     /* Android */
  'Helvetica Neue',           /* macOS 备用 */
  Arial,                      /* 通用 sans-serif */
  'PingFang SC',              /* 简体中文 macOS */
  'Microsoft YaHei',          /* 简体中文 Windows */
  sans-serif;
```

**原则**: 优先使用系统字体，保证原生渲染性能；中文回退到苹方/微软雅黑。

### 3.2 字号层级

| Token | Value | 用途 |
|-------|-------|------|
| `--cpq-font-size-sm` | `12px` | 辅助文字、标签、时间戳 |
| `--cpq-font-size-base` | `14px` | 正文、表单输入、表格内容 |
| `--cpq-font-size-lg` | `16px` | 小标题、卡片标题 |

**原则**: 基准字号 14px，适合高密度后台界面；避免使用 13px 等非标准字号。

---

## 4. 间距与圆角

### 4.1 圆角

| 元素类型 | 圆角值 | 示例 |
|---------|--------|------|
| 普通卡片 | `18px` | `.glass` 卡片 |
| 弹窗/覆盖层 | `16px` | `.glass-strong`、Modal |
| 输入框/按钮 | `4px` | Ant Design 默认 |
| 滚动条 | `4px` | `::-webkit-scrollbar-thumb` |

**原则**: 卡片使用大圆角（16-18px）营造柔和感；表单组件保持小圆角（4px）保证紧凑。

### 4.2 间距（参考 Ant Design 8px 栅格）

- **组件内边距**: 8px / 12px / 16px / 24px
- **组件间距**: 16px（紧凑）/ 24px（标准）/ 32px（宽松）
- **页面边距**: 24px

---

## 5. 毛玻璃层级

### 5.1 `.glass` — 轻量毛玻璃

**用途**: 普通卡片、KPI 面板、配置卡片

```css
background: linear-gradient(135deg, 
  rgba(255, 255, 255, 0.07) 0%, 
  rgba(255, 255, 255, 0.03) 40%, 
  rgba(8, 12, 16, 0.25) 100%);
backdrop-filter: blur(16px) saturate(1.4);
border: 1px solid rgba(0, 245, 212, 0.12);
border-radius: 18px;
box-shadow: 
  0 22px 64px rgba(0, 0, 0, 0.30),
  0 0 34px rgba(0, 245, 212, 0.04),
  inset 0 1px 0 rgba(255, 255, 255, 0.13),
  inset 0 -18px 48px rgba(0, 0, 0, 0.14);
```

**特点**: 
- 半透明渐变（白→灰→黑），营造光影层次
- 16px 模糊 + 1.4 饱和度，保留背景纹理
- Cyan 边框（12% 不透明度），提供微妙发光感
- 内阴影模拟玻璃厚度

### 5.2 `.glass-light` — 轻透毛玻璃

**用途**: 次级面板、内嵌容器、折叠面板内容区

```css
background: linear-gradient(135deg, 
  rgba(255, 255, 255, 0.08), 
  rgba(255, 255, 255, 0.02) 50%, 
  rgba(0, 0, 0, 0.10));
backdrop-filter: blur(12px) saturate(1.3);
border: 1px solid rgba(0, 245, 212, 0.12);
box-shadow: 
  0 14px 40px rgba(0, 0, 0, 0.22),
  0 0 20px rgba(0, 245, 212, 0.03),
  inset 0 1px 0 rgba(255, 255, 255, 0.10),
  inset 0 -12px 32px rgba(0, 0, 0, 0.10);
```

**特点**: 
- 比 `.glass` 更透亮（白色起点 8%）
- 12px 模糊，背景更清晰
- 无圆角（继承父容器）

### 5.3 `.glass-strong` — 加强毛玻璃

**用途**: 弹窗（Modal）、抽屉（Drawer）、覆盖层

```css
background: linear-gradient(135deg, 
  rgba(20, 22, 28, 0.65), 
  rgba(12, 14, 20, 0.55));
backdrop-filter: blur(24px) saturate(1.6);
border: 1px solid rgba(255, 255, 255, 0.12);
border-radius: 16px;
box-shadow: 
  0 12px 48px rgba(0, 0, 0, 0.8),
  inset 0 1px 0 rgba(255, 255, 255, 0.08),
  inset 0 -1px 0 rgba(0, 0, 0, 0.20);
```

**特点**: 
- 深色渐变（65% → 55% 不透明度），遮挡背景内容
- 24px 模糊 + 1.6 饱和度，背景高度模糊
- 白色边框（12%），与深色背景形成对比
- 强阴影（80% 不透明度），突出层级

---

## 6. 阴影系统

| Token | Value | 用途 |
|-------|-------|------|
| `--cpq-shadow-sm` | `0 2px 8px rgba(0, 0, 0, 0.6)` | 小型卡片、按钮 |
| `--cpq-shadow-md` | `0 4px 16px rgba(0, 0, 0, 0.7)` | 中型卡片、下拉菜单 |
| `--cpq-shadow-lg` | `0 8px 32px rgba(0, 0, 0, 0.85)` | 弹窗、抽屉、悬浮层 |

**原则**: 阴影使用纯黑（rgba(0,0,0)），不透明度 60%-85%，营造深空感。

---

## 7. 动效规范

### 7.1 缓动曲线

```css
--cpq-ease-out-expo: cubic-bezier(.16, 1, .3, 1);
```

**特点**: 指数衰减曲线，起始快、结束慢，模拟物理惯性。

### 7.2 过渡时长

| Token | Value | 用途 |
|-------|-------|------|
| `--cpq-transition-fast` | `0.2s` | Hover 态、按钮点击 |
| `--cpq-transition-normal` | `0.3s` | 卡片展开、Tab 切换 |
| `--cpq-transition-slow` | `0.5s` | 页面过渡、模态框淡入 |

### 7.3 交互动效

**卡片 Hover**:
```css
transform: translateY(-2px);
border-color: var(--cpq-accent-primary);
transition: all var(--cpq-transition-fast);
```

**按钮 Hover**:
```css
transform: translateY(-1px);
box-shadow: 0 0 16px rgba(0, 245, 212, 0.3);
```

**输入框 Focus**:
```css
border-color: var(--cpq-accent-primary);
box-shadow: 0 0 0 2px rgba(0, 245, 212, 0.15);
```

**原则**: 
- 所有交互元素使用 `translateY` 微上移（1-2px），模拟浮起
- 聚焦/激活态添加 cyan 发光（box-shadow），强化反馈
- 避免使用 `scale` 缩放，防止布局抖动

---

## 8. 背景氛围

### 8.1 主内容区背景（`.main-scroll`）

```css
background:
  /* 左上 cyan 光晕 */
  radial-gradient(ellipse 60% 40% at 15% 5%, 
    rgba(0, 245, 212, 0.12), transparent),
  /* 右下 blue 光晕 */
  radial-gradient(ellipse 50% 35% at 85% 70%, 
    rgba(80, 80, 255, 0.08), transparent),
  /* 中间 white 微光 */
  radial-gradient(ellipse 40% 30% at 50% 40%, 
    rgba(255, 255, 255, 0.04), transparent),
  var(--cpq-bg-primary);
```

**特点**: 
- 三层径向渐变叠加，营造空间深度
- 左上 cyan（12% 不透明度）与品牌色呼应
- 右下 blue（80,80,255）增加色彩层次
- 中间 white 微光（4%）提亮视觉中心

### 8.2 粒子点阵（`.main-scroll::before`）

```css
background-image:
  radial-gradient(circle 1px at 50px 50px, 
    rgba(255,255,255,0.20) 1px, transparent 1px),
  radial-gradient(circle 1px at 150px 100px, 
    rgba(255,255,255,0.12) 1px, transparent 1px),
  radial-gradient(circle 1px at 250px 50px, 
    rgba(255,255,255,0.16) 1px, transparent 1px),
  radial-gradient(circle 1px at 100px 200px, 
    rgba(255,255,255,0.14) 1px, transparent 1px);
background-size: 300px 300px;
animation: particleDrift 60s linear infinite;
```

**特点**: 
- 4 层粒子点，不透明度 12%-20%
- 300px × 300px 平铺，形成星点效果
- 60 秒缓慢漂移动画，增加生动感

### 8.3 边缘暗角（`.main-scroll::after`）

```css
background: radial-gradient(ellipse at center, 
  transparent 50%, 
  rgba(0, 0, 0, 0.4) 100%);
```

**特点**: 四周压暗（40% 不透明度），聚焦视觉中心。

---

## 9. 交互反馈

### 9.1 Hover 态

| 元素 | 效果 |
|------|------|
| 卡片（`.action-card`, `.kpi-card` 等） | `translateY(-2px)` + 边框变 cyan |
| 默认按钮 | `translateY(-1px)` + 边框/文字变 cyan + 发光阴影 |
| 主按钮 | `translateY(-1px)` + 强发光阴影 |
| 表格行 | 背景变为 `--cpq-bg-tertiary` |

### 9.2 Focus 态

| 元素 | 效果 |
|------|------|
| 输入框 | 边框变 cyan + 2px cyan 发光环 |
| 数字输入框 | 同上 |
| 下拉选择器 | 同上 |

### 9.3 Active 态

| 元素 | 效果 |
|------|------|
| 分页页码 | 背景/边框变为 `--cpq-accent-primary` |
| Tab 标签 | 文字变为 cyan，底部指示器变 cyan |
| Checkbox | 背景/边框变为 `--cpq-accent-primary` |

---

## 10. 组件规范（Ant Design Vue 覆盖）

### 10.1 表格

- 表头背景: `--cpq-bg-tertiary`
- 表头文字: `--cpq-text-secondary`
- 单元格背景: `--cpq-bg-secondary`
- 单元格文字: `--cpq-text-primary`
- 行 Hover: 背景变为 `--cpq-bg-tertiary`
- 边框: `--cpq-border-secondary`

### 10.2 输入框

- 背景: `--cpq-bg-tertiary`
- 边框: `--cpq-border-light`
- 文字: `--cpq-text-primary`
- Focus: 边框变 cyan + 发光环

### 10.3 按钮

**默认按钮**:
- 背景: `--cpq-bg-tertiary`
- 边框: `--cpq-border-primary`
- 文字: `--cpq-text-primary`
- Hover: 边框/文字变 cyan + 微上移 + 发光

**主按钮**:
- 背景/边框: `--cpq-accent-primary`
- 文字: `--cpq-bg-primary`（黑色，保证对比度）
- Hover: 保持 cyan + 强发光

### 10.4 Modal / Drawer

- 背景: `rgba(16, 18, 23, 0.85)` + `blur(20px) saturate(1.6)`
- 边框: `--cpq-border-secondary`
- 标题: `--cpq-text-primary`
- 关闭图标: `--cpq-text-secondary`

### 10.5 Tabs

**Card 样式**:
- 默认标签: 背景 `--cpq-bg-tertiary`，边框 `--cpq-border-primary`
- 激活标签: 背景/边框 `--cpq-accent-primary`

**Line 样式**:
- 默认标签: 文字 `--cpq-text-secondary`
- 激活标签: 文字 cyan，底部指示器 cyan

---

## 11. 可访问性检查清单

- [ ] 文字对比度 ≥ 4.5:1（WCAG AA）
- [ ] 交互元素有明确的 Focus 态
- [ ] 不仅用颜色区分状态（辅以图标/文字）
- [ ] 禁用态元素不可交互（cursor: not-allowed）
- [ ] 动画可关闭（`prefers-reduced-motion`）

---

## 12. 文件位置

- **CSS 架构**: `frontend/src/styles/`
  - `tokens.css` — 所有 CSS 变量（`--cpq-*` 命名空间）
  - `reset.css` — 全局重置 + 滚动条
  - `glass.css` — 玻璃拟态工具类
  - `antd-overrides.css` — Ant Design 覆盖（用 `#app` 提高优先级）
  - `utilities.css` — 微交互工具类
- **布局样式**: `frontend/src/layouts/DefaultLayout.vue`
- **组件样式**: `frontend/src/components/*.vue`（`<style scoped>`）

---

## 13. 更新日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-07-07 | 1.0 | 初始版本，基于 style.css 提取规范 |

---

**维护说明**: 
- 修改 CSS 变量时同步更新本文档
- 新增毛玻璃层级/阴影层级时补充到对应章节
- 交互模式变更时更新第 9 章
