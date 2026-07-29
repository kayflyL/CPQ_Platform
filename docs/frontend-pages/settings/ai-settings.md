# AI 设置 (AiSettings)

> 最后更新：2026-07-29

## 功能概述

配置 AI 趋势洞察和方案助手的行为，所有配置项存储在 `system_config` 表，拒绝硬编码。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/ai-settings` | `views/settings/AiSettings.vue` |

## 页面结构

页面使用 Tabs 切换三个配置模块：

---

## 趋势洞察 (Insights)

### 基础设置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| 生成方式 | 自动生成 / 手动刷新 | 自动生成 |
| 洞察数量 | 1-5 条 | 3 条 |
| 关注维度 | 增长信号、风险预警、行动建议 | 全选 |
| 数据范围 | 核心指标、平台分布、业务排行、趋势变化 | 全选 |
| 分析深度 | 简洁 / 详细 | 简洁 |

### 维度标签

可自定义洞察维度的显示名称：

| Key | 默认标签 |
|-----|----------|
| `growth` | 增长信号 |
| `risk` | 风险预警 |
| `suggestion` | 行动建议 |

### 提示词模板

自定义 AI 分析指令，支持变量：
- `{dimensions}` — 关注维度
- `{count}` — 洞察数量
- `{depth_desc}` — 深度描述

### 兜底文案

AI 调用失败时显示的内容：

| 场景 | 配置项 |
|------|--------|
| 无数据 | `fallback_templates.no_data` |
| 出错 | `fallback_templates.error` |

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
| GET | `/api/system-config/ai_insights_config/value` | 获取趋势洞察配置 |
| PUT | `/api/system-config/ai_insights_config` | 更新趋势洞察配置 |
| GET | `/api/system-config/ai_assistant_config/value` | 获取方案助手配置 |
| PUT | `/api/system-config/ai_assistant_config` | 更新方案助手配置 |
| GET | `/api/system-config/llm_config/value` | 获取 LLM 配置 |
| PUT | `/api/system-config/llm_config` | 更新 LLM 配置 |

---

## 数据库表

| Schema | 表 | Key | 用途 |
|--------|-----|-----|------|
| `rules` | `system_config` | `ai_insights_config` | 趋势洞察配置 |
| `rules` | `system_config` | `ai_assistant_config` | 方案助手配置 |
| `rules` | `system_config` | `llm_config` | LLM API 配置 |

---

## 关键文件

- `views/settings/AiSettings.vue` — AI 设置页面
- `composables/assistantContext.ts` — 上下文 Provider 管理
- `composables/assistantProviders.ts` — Provider 定义
- `services/llm_client.py` — LLM 客户端（从配置读取参数）
- `api/dashboard.py` — 趋势洞察 API（从配置读取参数）