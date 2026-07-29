# AI 设置 (AiSettings)

> 最后更新：2026-07-30

## 功能概述

配置方案助手的行为与模型 API，所有配置项存储在 `system_config` 表，拒绝硬编码。

> 「趋势洞察」已下沉为方案助手的「📈 分析本期趋势」快捷指令（商机线索页助手面板内一键触发）：业务数据上下文（周/月/近半年聚合 + 近期重点商机）由 `/api/dashboard/trend-overview` 自动注入，**提示词模板可在此页「趋势分析」tab 配置**（存 `ai_trend_analysis`，反对硬编码）。详见 [方案助手文档](../assistant/floating-assistant.md)。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/ai-settings` | `views/settings/AiSettings.vue` |

## 页面结构

页面使用 Tabs 切换三个配置模块（方案助手 / 趋势分析 / API 设置）：

---

## 方案助手 (Assistant)

### 基础设置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| 自动上下文 | 打开时自动注入当前页面数据 | 开启 |
| 回复风格 | 简洁 / 详细 | 详细 |

### 上下文来源

选择哪些页面可以提供上下文给 AI：

| Provider | 默认名称 | 说明 |
|----------|----------|------|
| `quote` | 报价工作台 | `/workspace` 页面 |
| `opportunity` | 商机详情 | `/opportunities/:id` 页面 |
| `opportunity-list` | 商机线索 | `/opportunities` 页面 |

每个 Provider 可配置：
- **启用/禁用** — 是否在该页面提供上下文
- **显示名称** — 自定义标签
- **详细度** — 简要 / 详细

---

## 趋势分析 (Trend)

方案助手「📈 分析本期趋势」快捷指令的配置。指令的**业务数据上下文**（周/月/近半年聚合 + 近期重点商机）由后端 `/api/dashboard/trend-overview` 自动注入，用户在此只调**提示词口径**与重点商机条数。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| 重点商机条数 | `highlight_count`（近半年按台数降序取 Top N，传给 trend-overview 的 limit） | 10 |
| 提示词模板 | `prompt_template`（引导 AI 输出 8 段结构化报告；归因须标注「推测」） | 见种子 |

> 默认 prompt 引导 AI 按周/月/半年趋势 / 平台格局 / 机箱形态 / TOP5 / 近期重点商机 / 关键洞察 分节输出；未提供的定性数据（如具体成交价）不允许编造，仅当 `lost_reason` 有值时摘要价格反馈。

---

## API 设置

### LLM 配置

| 配置项 | 说明 | 配置优先级 |
|--------|------|------------|
| API 端点 | `base_url` | system_config > .env |
| API Key | `api_key`（密码形式显示） | system_config > .env |
| 模型 | `model` | system_config > .env |
| 温度 | `temperature` (0-2) | 0.7 |
| 最大 Tokens | `max_tokens` | 2000 |
| System Prompt | 系统提示词 | 见默认值 |

### 配置优先级

```
system_config.llm_config > .env 环境变量 > 默认值
```

---

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/system-config/ai_assistant_config/value` | 获取方案助手配置 |
| PUT | `/api/system-config/ai_assistant_config` | 更新方案助手配置 |
| GET | `/api/system-config/ai_trend_analysis/value` | 获取趋势分析配置 |
| PUT | `/api/system-config/ai_trend_analysis` | 更新趋势分析配置 |
| GET | `/api/system-config/llm_config/value` | 获取 LLM 配置 |
| PUT | `/api/system-config/llm_config` | 更新 LLM 配置 |
| GET | `/api/dashboard/trend-overview?limit=N` | 趋势分析富数据（周/月/近半年聚合 + 重点商机，快捷指令注入用） |

---

## 数据库表

| Schema | 表 | Key | 用途 |
|--------|-----|-----|------|
| `rules` | `system_config` | `ai_assistant_config` | 方案助手配置 |
| `rules` | `system_config` | `ai_trend_analysis` | 趋势分析配置（提示词模板 + 重点商机条数） |
| `rules` | `system_config` | `llm_config` | LLM API 配置 |

---

## 关键文件

- `views/settings/AiSettings.vue` — AI 设置页面
- `composables/assistantContext.ts` — 上下文 Provider 管理
- `composables/assistantProviders.ts` — Provider 定义 + 趋势分析快捷指令（`loadTrendConfig` / `buildTrendContext`）
- `api/dashboard.py` — `/summary` 单周期统计 + `/trend-overview` 趋势分析富数据
- `services/llm_client.py` — LLM 客户端（从配置读取参数）