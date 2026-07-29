# 方案助手(全局浮动 AI 聊天窗)

## 功能概述

全局浮动的「方案助手」入口,任意页面右下角常驻。点击展开聊天窗,接入 **Qwen(通义千问)**,流式输出回复。`DASHSCOPE_API_KEY` 未配或调用失败时自动回退规则占位,保证可用。上下文走**多域 provider**(当前商机/报价,可扩展策略中心等)。

## 入口与挂载

- **浮动按钮** `AssistantFloatingButton.vue`:挂在 `layouts/DefaultLayout.vue` 的 `</main>` 之后(全局常驻),z-index 1500。open 时图标变关闭。
- **聊天面板** `AssistantPanel.vue`:Teleport to body,右下角 380×560 glass 面板;流式气泡(逐字 + 光标)。

## 多域上下文 provider(`composables/assistantContext.ts` + `assistantProviders.ts`)

助手是全局 UI,上下文不写死商机/报价。每域注册一个 provider:
```
interface ContextProvider { key; label; match(ctx); summarize(ctx): Promise<string> }
```
- 发消息时,遍历激活 provider(`match=true`),收集 `summarize()` 拼成 `context_summary` → 后端塞 system prompt。
- **当前域**:`quoteProvider`(workspace 页:商机+报价配置)、`opportunityProvider`(商机详情页:商机概览+报价单数)。
- **加新城**(如策略中心):在 `assistantProviders.ts` 加 provider + 注册到 `contextProviders` 数组,助手核心不改。
- 徽标显示激活域 label(无激活→「无上下文」)。

## API 端点(`/api/assistant`)

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/assistant/threads` | 新建会话 |
| GET | `/api/assistant/threads` | 当前用户会话列表 |
| GET | `/api/assistant/threads/{id}/messages` | 会话历史 |
| POST | `/api/assistant/threads/{id}/messages` | 存 user 消息 + 后台启动 LLM 流式(立即返回 user_message;token 经 WS 推) |
| DELETE | `/api/assistant/threads/{id}` | 软删 |
| WS | `/api/assistant/ws/{thread_id}` | 订阅 token 流(chunk → done) |

身份复用 Feed 的 `X-User-Id`。

## LLM 接入(`backend/app/services/`)

- `llm_client.py`:`AsyncOpenAI`(OpenAI 兼容模式)调 Qwen,`stream_chat(messages)` 逐 delta yield。`SYSTEM_PROMPT`(CPQ 方案助手人设;不编造料号价格)。`LLMError`。
- `assistant_hub.py`:`AssistantHub`(照 `feed_hub.FeedHub`,room=thread_id),`broadcast(thread_id, payload)`。
- `api/assistant.py`:`post_message` 存 user + 拼 messages(system+历史+user)→ `asyncio.create_task(_stream_llm_reply)` → 立即返回。`_stream_llm_reply` 流式广播 chunk → 存 assistant → 广播 done;LLM 失败走 `_placeholder_reply` 兜底。
- 配置:`config.py` 的 `DASHSCOPE_API_KEY` / `LLM_MODEL`(默认 qwen-plus)/ `LLM_BASE_URL`(dashscope 兼容);`.env` 配 key。

## 数据库表(opportunities schema)

`assistant_threads` / `assistant_messages`(独立于 FeedMessage)。迁移 `create_assistant_tables.sql`。

## 关键组件

- `components/assistant/AssistantFloatingButton.vue` / `AssistantPanel.vue`
- `composables/useAssistant.ts`(会话状态 + WS 流式接收:chunk→streamingText,done→入 messages)
- `composables/assistantContext.ts` + `assistantProviders.ts`(多域上下文)
- `api/assistant.ts`(REST + `assistantWsUrl`)
- `services/llm_client.py` / `assistant_hub.py`(后端)

## 下一步(未做)

- **工具调用(function calling)**:AI 主动查料号库 / 算价 / 拆 BOM。provider 框架已为它留位。
- **上下文裁剪 / token 预算**:历史全塞,超长再裁。
- Feed(详情页协作抽屉)未动,等助手成型再定退役。
