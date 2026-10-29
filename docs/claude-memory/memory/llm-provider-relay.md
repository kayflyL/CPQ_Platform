---
name: llm-provider-relay
description: LLM 上游现状=智谱z.ai官方Anthropic兼容端点(09-14起,200包404+/v1路径/GLM默认开思考三坑已修)；旧cloudprime中转怪状史料在案；skill链路原生FC+分层看门狗；碰LLM/agent/推理流前先看
metadata: 
  node_type: memory
  type: reference
  originSessionId: 351c2cea-bcbd-4c60-b025-08db1d053dab
  modified: 2026-10-01T17:19:18.452Z
---

**当前上游（2026-09-14 起）：智谱 z.ai 官方 Anthropic 兼容端点** `https://api.z.ai/api/anthropic`（DB llm_config，upstream_format=anthropic，模型 glm-5.3-flash 实测可用）。**10-02 用户确认：官方直连运行良好，无 429/限流问题——别再把「中转限流防护」当痛点提**。**全链路按协议分流**：`llm_client._is_anthropic_upstream()` 是唯一判据，stream_chat/stream_agent_chat/chat_json/chat_with_tools 四条链路（带不带 tools 都）路由到 anthropic_channel——旧代码只给带 tools 的调用分流（cloudprime 混合代理时代的局部补丁），换 z.ai 后纯文本走 OpenAI SDK 打错路径拿到 200 包 404 →「(空回复)」事故（09-14 已根修，测试钉死）。三个实测坑：
- **HTTP 200 包错误**：z.ai 对 404 等返回 HTTP 200 + `{"code":500,"msg":"404 NOT_FOUND","success":false}`——OpenAI SDK 解析成 data=None 曾报 `'NoneType' object is not iterable`；anthropic_channel 有 `_wrapped_error` 拆包（chat 非流式 + stream 非 SSE 守卫），排障三件套（test/models/probe）同样按协议分流（`_list_models_anthropic` 走 `{base}/v1/models` x-api-key 头，实测拉到 glm 全家桶）。
- **路径必须带 /v1**：Anthropic 规范路径 `{base}/v1/messages`、`{base}/v1/models`；`anthropic_channel.messages_base()` 归一化（base 不带 /v1 自动补）。**换 provider 时 DB 里 model 字段要同步换**（z.ai 报 [1211] Unknown Model——测试连接会如实透出）。glm 系是 reasoning 模型：thinking 吃 max_tokens 预算，小预算=只有思考没有正文；anthropic_channel.stream 收尾 yield `{type:meta,stop_reason,usage}`，stop_reason=max_tokens+零正文 → TRUNCATED_NOTICE 兜底（防线同 OpenAI 通道）。
- **GLM 默认开思考（09-14 晚实测，第三坑）**：glm-5.3-flash 在 /api/anthropic **不带 thinking 参数也吐 thinking 块**，且每次工具调用前都思考——llm_trace agent_round 实测工具轮 thinking 5k~20k 字符=40~131s/轮（纯文本轮 8~25s），e2e 单轮 142~323s 撞 240s 预算，体感「换模型跑不通」（引擎其实在后台跑完了，链路逻辑全通）。**修法=llm_config JSON 配 `"thinking":{"type":"disabled"}`**：`_get_llm_config()` 透传 → anthropic_channel chat()/stream() 挂 payload（仅配置了非空 dict 才发，不配=请求体与旧版逐字节一致，换模型零影响）；llm_client 四条 anthropic 链路全部接齐。附带守卫：thinking.type=enabled 时自动丢 temperature（Anthropic 规范要求 temp=1/缺省，否则 400——以后想开思考的模型不至于再翻车）。
- **多模型支持设计（09-14 定稿；09-15 档案定调覆盖）**：前端「上游格式」贴端点自动识别（/anthropic→anthropic；/compatible-mode|/paas/v|/v1→openai）；chat_json 在 anthropic 分支不用 response_format。**llm_profiles 多连接档案 + 供应商预设 09-14 被用户否掉删除**；**09-15 用户两连否**：①硬编码「模型卡目录」（网上查的价格/上下文窗口）——厂商规格会过时、网抄数据不可信；②「端点差异修正」三态手工 override 层——把例外当常规。**现行定调：模型能力档案事实源=探测**。两层原则：档案=事实（只读，模型能什么）/ 模型与连接=选择（可编辑，怎么用它）；reasoning_model 是档案事实、thinking 思考模式是行为选择，分属两页不算重复。机制：`probe_model_capabilities` 结果落库 `system_config.llm_capability_probes`（键 model@upstream_format，含 tested_at/base_url/每项 `*_probed` 定论标记/default_thinking 检测）→ `_get_llm_config` 注入 `probe_capabilities`（base_url 不匹配=换端点作废；单项未定论不注入防网络抖动误伤）→ `get_model_capabilities` 合成链=内置家族默认→协议修正（anthropic 抬 native_tools/降 json_mode）→实测覆盖。`capabilities_override` 已整体移除（代码+DB 键+测试改名 test_model_supports_strict_tools_probed）。**透明性铁律（09-15 用户点破）**：模型行为的任何新键必须随改随配「模型与连接」页可见控件，不留 DB 黑盒键——thinking 落地当天就被追问「是不是又在其他地方黑盒写了东西」。探测测试锚 tests/test_anthropic_channel.py。**实测模型清单 tab（09-15 二轮，调研 One API/New API·LiteLLM·OpenRouter 后落地）**：留档键改 `model@协议@端点域名含端口`（同模型各端点并存，换端点不冲历史，旧键读时自动迁移）；清单只读含失败记录与历史端点，列=模型/端点+身份标签（官方直连/本地自建/第三方中转，域名→身份小表是路由元数据非能力断言）/协议/原生工具/JSON/默认开思考/结论/时间；`GET llm_config/probe-history` 管理员；耗时列用户否掉、per-row 重探测不做（api_key 不随档存）。

以下为旧 cloudprime 中转时代实测史料（换回中转/同类 new-api 代理时再读）：

LLM 接入真相（2026-08-07 smoke 实测）：
- **生效模型是 `deepseek-v4-flash`**（2026-08-20 实测 DB llm_config；08-07 时还是 deepseek-v4-pro，中途切换过），经 `http://api.cloudprime.com.cn:5567/v1`（new-api 风格代理，疑似异质后端负载均衡：503 model_not_found / 400 AnthropicToolChoice / 400 web_search enum 交替出现）。`system_config.llm_config`（DB，AI 设置页）**优先于 .env**；**.env 的 LLM_MODEL=qwen3.7-plus 已 stale、app 根本没用**——看到 model_not_found 别据此判断能力。改模型/端点去 AI 设置页（写 DB）。**flash 是 reasoning 模型且延迟方差极大**：同 prompt 单次 4~20s 波动、坏时 80s+（08-20 实测），体感"机器缓慢"先怀疑这里+SDK 静默重试。
- **原生 function-calling：skill 链路已切（2026-09-10~12）**。早期实测同 payload 通道轮盘（有的认 `type:function`、有的只认内置 web_search 报 400）曾迫使全走文本 ReAct；现状=skill 大脑循环走原生 tools（`llm_client.py` `supports_native_tools` 能力探测 + auto/native 通道 + `_is_native_tools_unsupported` 自动降级文本式），文本 ReAct 通道已从 skill 链路删除（禁回归）。`agent_react.py`/`agent_tools.py` 只剩 AI 同事 ReAct 执行器在用。
- **tool_choice 必省略**：OpenAI 串 "auto" / Anthropic 对象 {"type":"auto"} 都被代理转码 BadRequest。
- **文本式 ReAct（agent_react.py）= 同事链路专用**：每轮 LLM 出一个 JSON（chat_json 的 json_object 模式，**不传 schema**：clean_by_schema 只保留 schema.properties 声明的键，会把无声明属性的 args 自由对象清成 {}），action∈{call_tool,final}，工具结果作 user 消息回传循环。skill 链路别再走这条。
- **embeddings 端点是坏的（2026-09-12 实测）**：`/models` 列出 qwen3.7-text-embedding-flash 但 `/embeddings` 返回 400；DashScope 官方 key 401 无配置。要向量/语义能力走本地 fastembed（bge-small-zh），别指望 relay。
- **代理会挂死（2026-09-05 定位）**：cloudprime 偶发建连后 90s+ 零字节（trace 615 实测 157s 空转，重试才成功）。已落地分层防御：stream_agent_chat 带 `first_token_timeout`（建连+首 chunk 各一层 asyncio.wait_for 看门狗，默认 30s；timeout=字节间隔 45~60s）、SDK max_retries=0（无静默重试）、大脑回合 llm_timeout=45 + 墙钟 180s 到点不再发起尝试（skill_chat 三大脑）、length 截断 yield 带 truncated 标记由 agent 循环拦下重试（⚠️ 不落库）。改超时/重试语义先看这套分层，别单点调。
- **流式模式 reasoning_effort 不可靠（2026-09-06 A/B 实测）**：同 prompt 背靠背，`reasoning_effort=low` 一次 6.2s/245 字符思考、一次 41.7s/10739 字符思考（与默认档无异）≈ 一半请求被代理忽略该参数；非流式 chat_json 的 effort 可靠。skill 大脑轮次方差大的主因。对策已挂 max_tokens=8000 护栏（run_stream_chat_loop.llm_max_tokens）把跑飞轮封顶 ~13.5k 字符/~70s；根治要靠代理修复或任务大脑换非 reasoning 模型。另实测模型偶发单轮生成循环直到供应商上限（52k 字符/120s+），护栏同款止血。

碰 LLM/agent/推理流 AI 节点前先看。关联 [[llm-integration-strategy]] [[assistant-skeleton]] [[reasoning-flow-viz]] [[skill-latency-program]]。
