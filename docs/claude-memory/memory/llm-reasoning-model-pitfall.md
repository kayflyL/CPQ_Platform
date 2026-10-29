---
name: llm-reasoning-model-pitfall
description: 方案助手模型是 step-3.7-flash(reasoning)，max_tokens 太小会让趋势分析等重任务空回复
metadata: 
  node_type: memory
  type: project
  originSessionId: 497c6db2-8e84-4406-8ad9-5e83bf858ead
  modified: 2026-07-31T15:13:29.080Z
---

方案助手当前 LLM 配置(DB `rules.system_config.llm_config`)：阶跃星辰 `step-3.7-flash`，走 `https://api.stepfun.com/v1` 的 OpenAI 兼容接口。step-3.x 是 **reasoning 模型**：思考过程输出在流式 chunk 的 `delta.reasoning_content`，正式回复才在 `delta.content`。

**坑**：该模型 `max_tokens` 是 reasoning+output 共享预算。趋势分析(8段结构化报告 + 大量数据计算)的 reasoning 固定烧 ~6000 字符；若 max_tokens < ~8000，思考阶段就 `finish_reason=length` 截断、正文 `content` 一个 token 都没产出 → 后端 `llm_client.stream_chat` 只读 `delta.content` → 全程 None → `"".join(full) or "(空回复)"`。简单问答 reasoning 短不触顶，所以**只有趋势分析这类重任务中招**，别的对话正常，极具迷惑性。

**已修(2026-07-31)**：
1. DB `llm_config.max_tokens` 2000→8000（`stream_chat` 每次实时查 DB，即时生效，重试即可，无需重启）
2. `llm_client.stream_chat` 加兜底：流结束但 content 为空时，按 `finish_reason` 给可操作诊断（`length` → 提示调大 max_tokens），不再闷成无意义的"(空回复)"
3. 代码默认 2000→8000（`_get_llm_config` 回退默认 + `system_config_repo.init_defaults` 种子，新部署不踩坑）

**注意**：趋势分析因 reasoning 重，单次响应 ~50-100s 属正常（不是卡死）。换模型后又空回复，先排查是不是 reasoning 类 + max_tokens 不够。碰方案助手/LLM/趋势分析空回复前先看。链接 [[assistant-skeleton]]。
