---
name: assistant-skeleton
description: "全局浮动「方案助手」已接 Qwen(流式) — 右下角入口+独立 assistant 表+多域上下文 provider"
metadata: 
  node_type: memory
  type: project
  originSessionId: ab996efd-7394-43be-b643-dc843fe4f337
  modified: 2026-07-29T16:50:58.990Z
---

2026-07-24 第二期落地:全局浮动「方案助手」AI 聊天窗,**已接 Qwen(通义千问)**。挂 `DefaultLayout.vue`(全局常驻),右下角浮动按钮 + 聊天面板;会话存独立表 `opportunities.assistant_threads` / `assistant_messages`(**不复用 FeedMessage**);身份复用 Feed `X-User-Id`。

**当前状态:已接 Qwen 流式**。`POST /api/assistant/threads/{id}/messages` 存 user + 后台 `_stream_llm_reply`(调 Qwen + 广播 chunk → 存 assistant → done)。`DASHSCOPE_API_KEY` 未配/失败时回退 `_placeholder_reply` 占位(保证可用)。WS `/api/assistant/ws/{id}` 推 token 流。

**Why:** 用户定调全局 AI 助手入口(非 Feed 协作);助手是全局多域 UI,上下文用**多域 provider**(商机/报价现在,策略中心等以后加 provider 即可,核心不改)。

**How to apply:**
- 配置:`backend/.env` 加 `DASHSCOPE_API_KEY`;`config.py` 的 `LLM_MODEL`(默认 qwen-plus)/ `LLM_BASE_URL`(dashscope OpenAI 兼容)
- LLM 客户端:`app/services/llm_client.py`(`AsyncOpenAI` + `stream_chat` + `SYSTEM_PROMPT`);换模型改 base_url/model 即可
- 上下文:`composables/assistantContext.ts`(provider 注册)+ `assistantProviders.ts`(quote/opportunity/opportunity-list);加新城在 assistantProviders 加 provider
- 快捷指令:`assistantProviders.ts` 的 `assistantQuickActions` 数组,按 providerKey 条件渲染 chip(面板输入框上方);加指令只追加数组,AssistantPanel 不改。`QuickAction.prompt`/`context` 都可为函数(动态读配置/自定义富上下文,缺省走通用 summarize)。商机线索页「📈 分析本期趋势」=原趋势洞察卡片下沉(2026-07-30 删卡片+`/api/dashboard/ai-insights`+ai_insights_config);增强版:prompt 读 `ai_trend_analysis.prompt_template`(AI 设置「趋势分析」tab 可配,反对硬编码),context 调 `/api/dashboard/trend-overview`(周/月/近半年聚合+近期重点商机含 lost_reason),LLM 输出 8 段富报告;归因允许但标注「推测」
- 流式:`useAssistant` WS 收 chunk→`streamingText`,done→入 messages;后端 `_stream_llm_reply` 广播 via `assistant_hub`
- 下一步(未做):工具调用(function calling 查料号/算价);上下文 token 裁剪;Feed 退役

关联 [[opportunity-identity]]、[[docs-code-drift]]。
