# 前端开发规范

> 适用版本：v0.1.11 | 更新日期：2026-07-11 | 主题：Cyberpunk Dark

---

## 1 CSS 变量色板（唯一合法颜色来源）

本项目采用 **CSS 变量** 实现主题。所有合法颜色、阴影、字体、动效均定义在 `frontend/src/styles/tokens.css`，统一使用 `--cpq-*` 命名空间。所有组件只用 `var(--cpq-*)` 引用，**绝不硬编码颜色值**（设计原则④：硬编码零容忍）。

当前为**纯暗色单主题**（Cyberpunk Dark：接近纯黑 + 亮青强调），未实现亮色主题、未实现运行时主题切换。

### 1.1 样式文件结构

样式拆分为 5 个文件，在 `main.ts` 中按序 import：

| 文件 | 职责 |
|------|------|
| `styles/tokens.css` | **所有设计变量的唯一定义处**（颜色、阴影、字体、动效、半透明叠加） |
| `styles/reset.css` | 基础重置 |
| `styles/glass.css` | 毛玻璃 / 玻璃拟态效果 |
| `styles/antd-overrides.css` | Ant Design Vue 组件样式覆盖（见 §3） |
| `styles/utilities.css` | 工具类 |

> 新增颜色需求一律加到 `tokens.css` 的 `:root`，不要在其他文件或组件内私自定义变量。

### 1.2 完整色板

以下为 `tokens.css` 中定义的全部变量，按分类列出。

#### 背景色（接近纯黑）

| 变量 | 值 | 用途 |
|------|------|------|
| `--cpq-bg-primary` | `#08090B` | 主背景 |
| `--cpq-bg-secondary` | `#101217` | 次要背景 |
| `--cpq-bg-tertiary` | `#171A21` | 三级背景 |
| `--cpq-bg-sidebar` | `#08090B` | 侧边栏 |
| `--cpq-bg-sidebar-header` | `#101217` | 侧边栏头部 |

#### 文字色（浅灰白）

| 变量 | 值 | 用途 |
|------|------|------|
| `--cpq-text-primary` | `#E8ECEF` | 主文字 |
| `--cpq-text-secondary` | `#9BA1AA` | 次要文字 |
| `--cpq-text-muted` | `#6E7582` | 弱化文字 |
| `--cpq-text-disabled` | `#3D424D` | 禁用文字 |

#### 边框色（半透明白）

| 变量 | 值 | 用途 |
|------|------|------|
| `--cpq-border-primary` | `rgba(255,255,255,0.10)` | 主边框 |
| `--cpq-border-secondary` | `rgba(255,255,255,0.06)` | 次要边框 |
| `--cpq-border-light` | `rgba(255,255,255,0.15)` | 浅边框 |

#### 强调色（亮青）

| 变量 | 值 | 用途 |
|------|------|------|
| `--cpq-accent-primary` | `#00F5D4` | 主强调色（亮青） |
| `--cpq-accent-primary-light` | `#00F5D4` | 浅强调色 |
| `--cpq-accent-success` | `#00F5D4` | 成功（同青色） |
| `--cpq-accent-warning` | `#F4D28A` | 警告 |
| `--cpq-accent-danger` | `#ff4d4f` | 危险/错误 |

#### 背景层级（卡片 / 面板）

| 变量 | 值 | 用途 |
|------|------|------|
| `--cpq-bg-card` | `#1E1E1E` | 卡片 |
| `--cpq-bg-elevated` | `#252525` | 提升层 |
| `--cpq-bg-input` | `#2A2A2A` | 输入框 |
| `--cpq-bg-selected` | `#1A3A1A` | 选中态 |
| `--cpq-bg-highlight` | `#FFFBE6` | 高亮 |
| `--cpq-bg-dark` | `#1A1A1A` | 极暗 |

#### 边框层级 / 功能色 / 文字补充

| 变量 | 值 |
|------|------|
| `--cpq-border-dark` | `#303030` |
| `--cpq-color-success` | `#52C41A` |
| `--cpq-color-warning` | `#FAAD14` |
| `--cpq-color-info` | `#1890FF` |
| `--cpq-color-purple` / `--cpq-color-purple-dark` | `#A855F7` / `#722ED1` |
| `--cpq-color-orange` / `--cpq-color-gold` | `#FA8C16` / `#D4A853` |
| `--cpq-text-light` / `--cpq-text-inverse` | `#E0E0E0` / `#1F1F1F` |
| `--cpq-text-tertiary` / `quaternary` / `quinary` | `#999` / `#666` / `#555` |

#### 阴影 / 字体 / 动效

| 类别 | 变量 |
|------|------|
| 阴影 | `--cpq-shadow-sm` / `-md` / `-lg`（深黑外投影，0.6~0.85 不透明度） |
| 字体 | `--cpq-font-family`（系统字体栈含 PingFang/微软雅黑）、`--cpq-font-size-sm` `12px` / `-base` `14px` / `-lg` `16px` |
| 动效 | `--cpq-ease-out-expo`（cubic-bezier）、`--cpq-transition-fast` `0.2s` / `-normal` `0.3s` / `-slow` `0.5s` |

#### 半透明叠加色（替换组件中的硬编码 rgba）

`tokens.css` 提供成体系的半透明变量，**凡需要 `rgba()` 的地方优先用这些**，不要手写 rgba：

- **白色半透明**（边框/分隔/微背景）：`--cpq-overlay-w3` ~ `--cpq-overlay-w20`（数字 = 不透明度 ×100）
- **黑色半透明**（遮罩/凹陷/阴影）：`--cpq-overlay-b15` / `b20` / `b30` / `b40` / `b85`
- **青色半透明**（强调/高亮/光晕）：`--cpq-overlay-a4` ~ `--cpq-overlay-a40`
- **功能色半透明**：`--cpq-overlay-danger10` / `danger15` / `success15` / `info20` / `warn30`

---

## 2 硬编码颜色禁令

### 2.1 禁止写法

```css
/* 禁止 */
color: #333;
background: white;
background: rgba(0, 0, 0, 0.8);
border: 1px solid rgba(255, 255, 255, 0.1);
```

### 2.2 正确写法

```css
/* 正确 */
color: var(--cpq-text-primary);
background: var(--cpq-bg-secondary);
border: 1px solid var(--cpq-border-primary);
background: var(--cpq-overlay-b40);   /* 半透明用 overlay 系列 */
```

### 2.3 例外白名单

| 场景 | 原因 |
|------|------|
| Chart.js / ECharts 图表配置 | 库 API 不支持 CSS 变量读取 |
| SVG 图标内联 fill（优先用 `currentColor`） | — |

---

## 3 Ant Design 主题覆盖

Ant Design Vue 组件的暗色适配**不走 ConfigProvider 的 JS token**，而是通过 `styles/antd-overrides.css` 用 CSS 覆盖：

- 选择器统一用 `#app .ant-*`（靠 `#app` 提升优先级，**不使用 `!important`**）
- 颜色全部引用 `var(--cpq-*)`
- 需要调整某个 Ant Design 组件外观时，**改 `antd-overrides.css`，不要在业务组件里覆盖 Ant Design 样式**

示例（antd-overrides.css 节选）：
```css
#app .ant-table {
  background: var(--cpq-bg-secondary);
  color: var(--cpq-text-primary);
}
#app .ant-pagination-item-active {
  background: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
}
```

---

## 4 stylelint（当前未配置）

> 项目当前**未安装 stylelint**（`package.json` 无相关依赖与脚本）。下方为推荐配置——若要启用硬编码颜色的自动拦截，按此添加即可。

推荐做法：在 `frontend/` 下安装 stylelint，新增 `.stylelintrc.json`：

```json
{
  "extends": "stylelint-config-standard-vue",
  "rules": {
    "color-no-hex": [true, { "severity": "error" }],
    "color-named": "never",
    "function-disallowed-list": ["rgb", "rgba", "hsl", "hsla"]
  }
}
```

并在 `package.json` 的 `scripts` 加入 `{ "lint:style": "stylelint 'src/**/*.{vue,css}' --fix" }`。规则要点：禁止 hex 色值、禁止命名颜色、禁用 `rgb/rgba/hsl/hsla` 函数（半透明统一走 `--cpq-overlay-*` 变量）。

---

## 5 主题切换（当前未实现）

当前为**纯暗色单主题**，代码中：
- 没有 `data-theme` 切换逻辑
- 没有 ConfigProvider 的 dark/light token 对象
- `tokens.css` 仅定义 `:root`（无 `[data-theme="light"]` 块）

若未来要加亮色主题，推荐方向（供参考）：
1. 在 `tokens.css` 新增 `[data-theme="light"]` 块，填入对调后的变量值
2. 切换时 `document.documentElement.setAttribute('data-theme', 'light')`
3. Ant Design 组件因走 `--cpq-*` 变量，会自动跟随；图表需单独处理（见 §6 FAQ）
4. 持久化到 `localStorage`

---

## 6 新建页面自检清单

每新建一个页面或组件，提交前逐项确认：

- [ ] color / background / border-color 使用 `--cpq-*` 变量（例外见 §2.3）
- [ ] 半透明效果用 `--cpq-overlay-*` 系列，不手写 `rgba()`
- [ ] 无裸色值（`#000`、`#fff`、`white`、`black` 等）
- [ ] 新颜色需求已加入 `tokens.css` 的 `:root`
- [ ] Ant Design 组件未在业务代码里手动覆盖样式（统一走 `antd-overrides.css`）
- [ ] 无硬编码颜色（项目当前未配 stylelint，人工自查）

---

## 7 常见问题

**Q: 新页面需要一种色板里没有的颜色怎么办？**
A: 先在 `tokens.css` 的 `:root` 定义一个 `--cpq-*` 变量，再在页面中使用。不私自在组件内定义颜色。

**Q: 需要 `rgba()` 半透明效果怎么办？**
A: 优先用 `--cpq-overlay-*` 系列（w/b/a 三色 + 功能色，覆盖常用不透明度）。若没有合适档位，在 `tokens.css` 新增一个 `--cpq-overlay-*` 变量，不要在组件里手写 `rgba()`。

**Q: ECharts / Chart.js 图表颜色怎么办？**
A: 图表库不读取 CSS 变量，允许在图表 JS 配置里硬编码色值（属 §2.3 例外）。但图表外层文字仍用变量。

**Q: 旧页面的硬编码颜色要不要一起改？**
A: 遵循渐进式重构——旧代码暂不强制改，但新增和修改代码必须用 `--cpq-*` 变量。
