# 方案助手(全局浮动 AI 聊天窗)

> 最后更新：2026-10-15（工作流「+」改装填模式不发占位消息；新增 suggest_workflow 一键发起确认卡）

## 功能概述

全局浮动的「方案助手」入口,任意页面右下角常驻。点击展开聊天窗,接入 **Qwen(通义千问)**,流式输出回复。`DASHSCOPE_API_KEY` 未配或调用失败时自动回退规则占位,保证可用。上下文走**多域 provider**(当前商机/报价,可扩展策略中心等)。

## 入口与挂载

- **浮动桌宠** `AssistantFloatingButton.vue`:挂在 `layouts/DefaultLayout.vue` 的 `</main>` 之后(全局常驻),z-index 1550。Live2D 形象(形象随当前活跃 AI 同事的 `pet_model`,见 `store/petModel.ts`),加载失败回落「助」字圆钮。
- **聊天面板** `AssistantPanel.vue`:Teleport to body,680×680 glass 面板;流式气泡(逐字 + 光标)。
- **入口开关单例** `composables/useAssistantShell.ts`(2026-09-28):模块级 `open` ref,DefaultLayout 持有渲染,任意页面(如工作台「方案助手」磁贴)经它唤起面板;可见性仍受 `auth.chatRolesAllowed` 门控。
- **桌面全屏形态**(2026-09-28):面板右栏新增全屏按钮(嵌入/内嵌/预览/手机态隐藏——手机本就自动全屏),全屏时铺满视口、禁拖拽缩放,Esc 或关闭面板退出;会话状态不丢。
- **手机端**(2026-10-11):≤760 全屏聊天窗,背景换 `--cpq-glass-3-bg-solid` 近实底档(原 75% 玻璃叠页面底色文字发虚,团队/历史抽屉同换);高度取实时 `innerHeight`(地址栏伸缩不顶飞输入区);右竖条(ap-right)手机端不渲染,新对话/历史/收起收进**顶栏动作组**(桌面竖条不变);桌宠点按切换挂 `pointerup` 不依赖合成 click(手机浏览器手势接管会丢 click),拖拽阈值触屏 12px/鼠标 4px(`FAB_DRAG_THRESHOLD_TOUCH`),canvas `:deep` 穿透设 `touch-action:none`。

## 桌宠交互(2026-09-14)

| 能力 | 说明 |
|------|------|
| 尺寸三档 | 小 160 / 中 200(默认) / 大 280;**右键桌宠**弹菜单切换;`localStorage cpq:assistant-pet-size` 记忆 |
| 贴边收起 | 拖到屏幕边缘(28px 吸附区,拖拽中显示虚线落位预览)松手 → 滑出 62% 只留 1/3 身子,hover 弹回;拖开即恢复;`localStorage cpq:assistant-pet-dock` 记忆;四边(left/right/top/bottom)都支持 |
| 流式摘录气泡 | 面板关着时,回复生成中桌宠头顶实时显示流式文本尾部(80 码点),turn 结束自动消失。链路:`AssistantPanel` watch(streamingText) → `petModel.setStreamTail()` → 桌宠渲染;**关面板不断在途回合的 WS**(延迟断连,回合跑完自动断),保证气泡持续更新 |
| 常驻细节 | 呼吸浮动动画(`prefers-reduced-motion` 时关闭);位置/尺寸/dock 均经 `useAssistantFab` 模块级单例持久化;右键菜单 Teleport 到 body(容器带 transform 时 fixed 会失真) |

涉及文件:`AssistantFloatingButton.vue`(桌宠容器/拖拽/贴边/菜单)、`composables/useAssistantFab.ts`(PET_SIZE_TIERS / PET_DOCK_* / setPetSize / setDockEdge)、`store/petModel.ts`(activeStreamTail 通道)、`AssistantPanel.vue`(流式喂给 + 延迟断连收口)。

## 多域上下文 provider(`composables/assistantContext.ts` + `assistantProviders.ts`)

助手是全局 UI,上下文不写死商机/报价。每域注册一个 provider:
```
interface ContextProvider { key; label; match(ctx); summarize(ctx): Promise<string> }
```
- 发消息时,遍历激活 provider(`match=true`),收集 `summarize()` 拼成 `context_summary` → 后端塞 system prompt。
- **当前域**:`quoteProvider`(workspace 页:商机+报价配置)、`opportunityProvider`(商机详情页:商机概览+报价单数)、`opportunityListProvider`(商机线索页:驾驶舱当前周期 KPI/平台/排行摘要;统计口径由后端 `query_cpq_data` 数据工具按需查询)。
- **加新城**(如策略中心):在 `assistantProviders.ts` 加 provider + 注册到 `contextProviders` 数组,助手核心不改。
- 徽标显示激活域 label(无激活→「无上下文」)。

## 快捷指令(`assistantQuickActions`)

面板输入框上方的 chip 横条,**按当前页激活的 provider 条件渲染**——仅当命中 `providerKey` 的 provider 处于激活态时对应指令才出现。点击即将指令文本作为用户消息发出,回复走 WS 流式。`QuickAction` 的 `prompt` 与 `context` 都可为函数:`prompt` 动态读取配置(反对硬编码),`context` 自定义富上下文(缺省走通用 provider 摘要)。扩展只需往 `assistantProviders.ts` 的 `assistantQuickActions` 数组追加一条,`AssistantPanel.onQuickAction` 通用、不改。

| 指令 | providerKey | 说明 |
|------|-------------|------|
| 📈 分析本期趋势 | `opportunity-list` | 原「趋势洞察」卡片下沉而来。`prompt` 读 `ai_trend_analysis.prompt_template`(AI 设置「快捷指令 · 趋势分析」tab 可改)并追加四组数据提示;数据不再由前端注入,后端数据工具链路(LLM 提参→`query_cpq_data` 查数→注入)按需取本周/本月/近半年/重点商机,LLM 输出 8 段结构化报告 |

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

- `llm_client.py`:`AsyncOpenAI`(OpenAI 兼容模式)调 Qwen,`stream_chat(messages)` 逐 delta yield。方案助手人设统一读 `ai_assistant_config.chat_system_prompt`（可在「AI 设置 → 方案助手」编辑；不编造料号价格）。`LLMError`。
- `assistant_hub.py`:`AssistantHub`(照 `feed_hub.FeedHub`,room=thread_id),`broadcast(thread_id, payload)`。
- `api/assistant.py`:`post_message` 存 user + 拼 messages(system+历史+user)→ `asyncio.create_task(_stream_llm_reply)` → 立即返回。`_stream_llm_reply` 流式广播 chunk → 存 assistant → 广播 done;LLM 失败走 `_placeholder_reply` 兜底。
- 配置:`config.py` 的 `DASHSCOPE_API_KEY` / `LLM_MODEL`(默认 qwen-plus)/ `LLM_BASE_URL`(dashscope 兼容);`.env` 配 key。

## 数据库表(opportunities schema)

`assistant_threads` / `assistant_messages`(独立于 FeedMessage)。迁移 `create_assistant_tables.sql`。

## 关键组件

- `components/assistant/AssistantFloatingButton.vue` / `AssistantPanel.vue`
  - `AssistantPanel` 新增可选 prop `workflowKey`(2026-09-15):透传进 `useAssistant.send` → 消息体 `workflow_key`,后端据此选流(工作流画布预览传画布当前 `skillKey`)
  - **工作流「+」装填模式**(2026-10-15):「+」选工作流不再自动发「请开始【xx】工作流。」占位消息(旧路径白烧一整个引擎回合问需求),改为 composer 上方亮装填条(`armedWorkflow`),placeholder 变「描述需求，发送后开始【xx】…」;下一条发送即携带 `entry_point=workflow_launcher` + 真实需求原文直进引擎(force_submit)。群聊装填记录技能归属同事(`ownerRoleKey`),发送钉住该角色防判官改道;换会话自动卸下装填态
  - **工作流发起确认卡**(2026-10-15):`kind='workflow_suggestion'` 消息渲染一键发起卡(标题/理由/需求原文/按钮)。来源=绑定 workflow 的同事在聊天里调 `suggest_workflow` 工具(数据随消息 `data.workflow_suggestion` 落库+广播);点击即以需求原文 `workflow_launcher` 发起,已点的卡置灰。装填/确认卡两入口收敛到同一后端分支,引擎首回合拿到的都是真需求
  - **文件产物卡**(2026-09-15):`kind='file'` 消息渲染 PDF 文件卡(标题/文件名/大小 + 下载/预览)。来源=输出节点 `artifacts` 插槽(后端 `report_pdf.py` 确定性渲染 markdown→PDF,落 `storage/office/reports/`);下载/预览共用 `utils/fileDownload.ts`(axios blob 带 Authorization → `downloadBlob` / objectURL iframe modal),预览 modal 内浏览器自带打印/另存
- `composables/useAssistant.ts`(会话状态 + WS 流式接收:chunk→streamingText,done→入 messages;`send` 消费装填态 `armedWorkflow`,`launchWorkflowNow(key, text, roleKey)` 供确认卡一键发起,`armWorkflow`/`cancelArmedWorkflow` 管装填态;旧 `launchWorkflow` 占位消息版已删)
- `composables/assistantContext.ts` + `assistantProviders.ts`(多域上下文)
- `api/assistant.ts`(REST + `assistantWsUrl`)
- `services/llm_client.py` / `assistant_hub.py`(后端)
- 报告下载端点:`GET /api/office/reports/{object_id}/download`(鉴权双通道:Authorization 头或 `?token=` 查询参数,后者供 iframe/直链)

## 下一步(未做)

- **工具调用(function calling)**:AI 主动查料号库 / 算价 / 拆 BOM。provider 框架已为它留位。
- **上下文裁剪 / token 预算**:历史全塞,超长再裁。
- Feed(详情页协作抽屉)未动,等助手成型再定退役。
