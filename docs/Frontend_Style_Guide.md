# 前端视觉风格指南

> 更新：2026-07-21 | 风格：**Soft Glassmorphism**（柔和玻璃拟态）| 默认主题：**浅色 light**，支持暗色 dark 一键切换

---

## 一句话定位

CPQ 前端 = **Soft Glassmorphism**：浅天蓝渐变背景 + 三级通透白玻璃容器 + 白边高光（hover/激活切蓝边）+ 极淡冷蓝投影 + 马卡龙语义色 + 工业蓝主色。氛围像**轻量 SaaS 仪表盘**，不是深空赛博。

> 历史背景：2026-07 从深空 Glass Console（纯暗色 + 亮青）转向浅色 SaaS 风格。本文件取代旧版"Cyberpunk Dark"规范。

## 两条铁律

1. **颜色只走 `--cpq-*` 变量**，绝不硬编码（`#fff` / `rgba()` / `white`）。半透明用 `--cpq-overlay-*`，不手写 rgba。
2. **容器外观走玻璃工具类**（`.glass` / `.glass-light` / `.glass-strong`），不要自己写实色背景 + border。

---

## 1 样式文件结构（`main.ts` 按序 import）

| 文件 | 职责 |
|------|------|
| `styles/tokens.css` | **所有设计变量唯一来源**，双主题 `:root[data-theme='dark' \| 'light']` |
| `styles/reset.css` | 基础重置 |
| `styles/glass.css` | 三级玻璃工具类（`.glass` / `.glass-light` / `.glass-strong`） |
| `styles/console.css` | 数字读数 / LED 徽章 / 流光 / 入场动效 |
| `styles/antd-overrides.css` | antd-vue 组件玻璃化覆盖（`#app .ant-*`） |
| `styles/utilities.css` | 通用工具类 |

> 新增颜色 / 玻璃 / 动效需求，一律加到 `tokens.css` 对应主题块，不在组件内私定义变量。

---

## 2 颜色系统

### 2.1 主色 & 语义色（`:root` 共享，双主题一致）

| 变量 | 值 | 用途 |
|------|------|------|
| `--cpq-accent-primary` | `#1677FF` | **主色（工业蓝）**，按钮 / 链接 / 激活态 |
| `--cpq-accent-primary-light` | `#4096ff` | 主色浅态 / hover |
| `--cpq-accent-cyan` | `#36CFCF` | **仅 signature 读数 / 流光**，极小面积，别滥用 |
| `--cpq-color-success` | `#52C9A0` | 成功（薄荷绿，马卡龙浅色系） |
| `--cpq-color-warning` | `#faad14` | 警告 |
| `--cpq-color-danger` | `#FF6B6B` | 危险（珊瑚红，马卡龙浅色系） |
| `--cpq-color-info` | `#1890ff` | 信息 |
| `--cpq-color-purple` | `#a855f7` | 紫 |
| `--cpq-accent-on-primary` | `#ffffff` | 主色按钮上的文字 |

> ⚠️ **禁用塑料荧光青 `#00F5D4`**（已全站清除）。青色只用 `#36CFCF` 且仅限 signature。

### 2.2 文字 / 背景 / 边框（按主题切换）

| 变量 | light | dark |
|------|-------|------|
| `--cpq-text-primary` | `#1d2129` | `#E8ECEF` |
| `--cpq-text-secondary` | `#4e5969` | `#9BA1AA` |
| `--cpq-text-muted` | `#86909c` | `#6E7582` |
| `--cpq-bg-primary` | `#F2F6FC` | `#08090B` |
| `--cpq-bg-secondary` | `#F0F4FA` | `#101217` |
| `--cpq-bg-tertiary` | `#E8EEF6` | `#171A21` |
| `--cpq-bg-card` | `#ffffff` | `#1e1e1e` |
| `--cpq-border-primary` | `rgba(22,119,255,0.10)` | `rgba(255,255,255,0.10)` |

> 表格单元格、输入框等**数据可读性优先区保实色**（`--cpq-bg-card` / `--cpq-bg-secondary`），不玻璃化。

---

## 3 玻璃系统（核心）

三级通透白玻璃：常态白边高光，hover / 激活切蓝边 + 蓝微光。

### 3.1 三级工具类

| 类 | 用途 | 圆角 | 磨砂(light) | 背景(light) |
|----|------|------|------------|------------|
| `.glass` | **主力面板 / 卡片** | xl `20px` | blur `10px` | 白 `0.40` |
| `.glass-light` | 次级 / 内嵌容器 / 小卡片 | lg `16px` | blur `12px` | 白 `0.55` |
| `.glass-strong` | 顶栏 / 弹窗 / 覆盖层（优先可读） | lg `16px` | blur `16px` | 白 `0.75` |

dark 下背景更透（`0.06` / `0.09` / `0.75`）、磨砂略强（`12` / `16` / `22px`）。

### 3.2 用法（容器挂工具类，scoped 只管布局）

```html
<div class="panel glass">...</div>
<div class="part-card glass-light">...</div>
```

```css
/* scoped 里只留布局，外观交给玻璃工具类 */
.panel { padding: 16px; margin-bottom: 16px; }
```

### 3.3 antd 容器玻璃化（`antd-overrides.css`）

- `card` → glass-2，`modal` / `drawer` / `tooltip` / `select-dropdown` → glass-3，`input` → glass-2
- **表格单元格保实色**（数据可读性）

### 3.4 ⚠️ 避免玻璃层叠（玻璃套玻璃 = 发灰）

玻璃卡的通透感来自 `backdrop-filter: blur()` 模糊**背后的真实背景**。两层玻璃嵌套时，内层的 `backdrop-filter` 模糊到的是**外层那层已经模糊过的半透明白**，不是页面背景的纹理/色彩 → 两层 blur 叠加成死灰糊状，丢失通透、整体泛白发灰。

**规则：卡片是唯一玻璃层，直坐页面背景。** 需要把多张玻璃卡分组时，外层用**透明布局容器**（只管 `padding` / `margin` / 分隔线，无 bg / blur / border），别再套 `.glass`。

```html
<!-- ✅ 对：外层透明，卡片是唯一玻璃层 -->
<div class="kp-section">           <!-- 透明：padding + border-top 分隔，无 glass -->
  <div class="kp-card glass">…</div>
  <div class="kp-card glass">…</div>
</div>

<!-- ❌ 错：外层又套 .glass → 内层卡 blur 到外层白雾，发灰 -->
<div class="kp-section glass">
  <div class="kp-card glass">…</div>
</div>
```

> 实例：报价工作台 Key Parts 区曾用 `.glass.card-kp` 包 `.kp-card`（玻璃），dark 下两层 0.06 白玻璃叠在 body 上发灰；摘掉外层 `.glass` 后 KP 卡与机型目录页 `.sc-type-card`（单层玻璃直坐 body）观感统一。见 CHANGELOG `[未发布]`。

---

## 4 圆角 / 投影 / overlay

### 4.1 圆角阶梯（统一大圆角，弱化棱角）

`--cpq-radius-sm 8` / `md 12` / `lg 16` / `xl 20` —— 用 `var(--cpq-radius-md)` 等引用。

### 4.2 投影（极淡冷蓝）

| 变量 | light | dark |
|------|-------|------|
| `--cpq-shadow-sm` | `0 2px 8px rgba(22,119,255,0.06)` | `0 2px 8px rgba(0,0,0,0.40)` |
| `--cpq-shadow-md` | `0 4px 16px rgba(22,119,255,0.08)` | `0 4px 16px rgba(0,0,0,0.50)` |
| `--cpq-shadow-lg` | `0 8px 24px rgba(22,119,255,0.10)` | `0 8px 32px rgba(0,0,0,0.60)` |

> ⚠️ **投影色用 `--cpq-shadow-color-soft` / `strong`，别用 `--cpq-overlay-b`**。overlay-b 在浅色已改白玻璃，当投影色会失悬浮感变白雾。

### 4.3 overlay 语义（关键，别混用）

| 系列 | 浅色下是 | 用途 |
|------|---------|------|
| `--cpq-overlay-w*`（w3~w20） | 白玻璃 | 卡片 / 面板底色、分隔线 |
| `--cpq-overlay-b*`（b15~b40） | 白玻璃（浅色也改白） | 卡片底；**`b85` 全屏遮罩保暗** |
| `--cpq-overlay-a*`（a4~a40） | 主色蓝半透明 | 强调 / 高亮 / 激活态 |
| 功能色 overlay | 各语义色半透明 | `danger10` / `success15` / `info20` / `warn30` |

---

## 5 排版 & 动效

### 5.1 排版

- 字体：`--cpq-font-family`（系统栈含 PingFang SC / 微软雅黑）
- 字号：`sm 12` / `base 14` / `lg 16`
- **数字读数**：用 `.cpq-reading`（tabular-nums + lining，等宽对齐；dark 蓝发光，light 干净无发光）

### 5.2 动效

- 时长：`--cpq-dur-1 160ms` / `dur-2 280ms` / `dur-3 480ms`
- 缓动：`--cpq-ease-smooth`（主力）/ `ease-spring`（回弹）/ `ease-out-expo`
- 入场：`.cpq-rise`（上浮淡入）/ `.cpq-fade`
- **尊重 `prefers-reduced-motion`**（已配，工具类自动禁用动画）

---

## 6 Signature（呼应"实时计算"的设备感）

- **总价条 / L6 合计条**：挂 `.cpq-stream-edge`（青色流光边，2.4s）+ `CountNumber`
- **KPI / 价格数字**：`.cpq-reading` 或 `CountNumber`（补间滚动，`composables/useCountUp.ts`）
- **设备状态徽章**：`.cpq-led--active / info / warning / danger / muted`

---

## 7 主题切换

- `store/theme.ts`：light（默认）/ dark，跟随系统 + `localStorage` 持久化，顶栏灯泡按钮切换
- 切换靠 `document.documentElement[data-theme]`，`tokens.css` 双主题块自动生效
- antd 走 `--cpq-*` 变量自动跟随；**图表需单独处理**（见 §9）

---

## 8 antd 覆盖原则

- 选择器 `#app .ant-*`（`#app` 提优先级，**不用 `!important`**）
- 改 antd 组件外观改 `antd-overrides.css`，**不在业务组件 scoped 里覆盖 antd**
- popover / dropdown 等挂 `body` 的组件，scoped 样式不生效，写在 `antd-overrides.css` 全局（用 `overlay-class-name` 作选择器前缀，不带 `#app`）

---

## 9 图表（ECharts / Chart.js）

canvas 渲染读不到 CSS 变量。**图表色走 `composables/useChartTheme.ts` 给真实值**，不写 `var()`。图表外层文字仍用变量。

---

## 10 Do / Don't

✅ **Do**
- 容器挂 `.glass` / `.glass-light` / `.glass-strong`，scoped 只管布局
- 颜色 / 半透明 / 圆角 / 投影全用 `--cpq-*` 变量
- 数字用 `.cpq-reading` 或 `CountNumber`
- 改 antd 走 `antd-overrides.css`

❌ **Don't**
- 硬编码颜色（`#fff` / `rgba()` / `white`）
- 用塑料荧光青 `#00F5D4`（已清除）
- 把 `--cpq-overlay-b` 当 `box-shadow` 色
- **玻璃层嵌套**（`.glass` 套 `.glass` / 玻璃卡外面再套玻璃容器）——内层 backdrop-filter 模糊到外层白雾、发灰；分组用透明布局容器（见 §3.4）
- 在 scoped 里用 `:global()` 混后代选择器（会抽裸 `[data-theme]` 贴到 html）
- 给图表色写 `var()`（canvas 读不到）
- 在 scoped 里覆盖 popover / dropdown 等挂 body 的组件（不生效）

---

## 11 新页面 / 组件 checklist

- [ ] 容器用 `.glass` / `.glass-light` / `.glass-strong`，scoped 只留布局
- [ ] **玻璃层不嵌套**（玻璃卡外层是透明布局容器，不是又一个 `.glass`）
- [ ] color / bg / border 用 `--cpq-*` 变量，无硬编码
- [ ] 半透明用 `--cpq-overlay-*`，无手写 rgba
- [ ] 圆角用 `--cpq-radius-*`，投影用 `--cpq-shadow-*` 或 `shadow-color-*`
- [ ] 数字 / 价格用 `.cpq-reading` 或 `CountNumber`
- [ ] 改 antd 走 `antd-overrides.css`，不在业务组件覆盖
- [ ] 图表色走 `useChartTheme`
- [ ] 挂 body 的浮层（popover / dropdown）样式写全局非 scoped
- [ ] 动效尊重 reduced-motion（用 `.cpq-rise` / `.cpq-fade` 工具类即自动）

---

## 12 FAQ

**Q: 需要色板没有的颜色？**
A: 加到 `tokens.css` 对应主题块，再引用。不在组件私定义。

**Q: 浮层（popover / 下拉）样式不生效？**
A: 它挂 body，scoped 够不着。写到 `antd-overrides.css`，用 `overlay-class-name` 作选择器前缀（不带 `#app`）。

**Q: 图表颜色怎么办？**
A: 走 `composables/useChartTheme.ts`，真实色值，不写 `var()`。

**Q: 玻璃卡看起来泛白 / 发灰、不通透？**
A: 多半是**玻璃层嵌套**了（外层 `.glass` 容器里又放了 `.glass` 卡片）。内层卡的 `backdrop-filter` 模糊到的是外层那层已模糊的白，不是页面背景，两层 blur 叠成死灰。把外层改成透明布局容器（只留 padding/分隔线），让卡片成为唯一玻璃层直坐背景（见 §3.4）。

**Q: stylelint 拦截硬编码？**
A: 项目当前未配 stylelint，人工按本指南自查。
