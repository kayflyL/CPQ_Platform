---
name: relay-error-misclassified-unsupported
description: z.ai anthropic 通道错误曾被盲降级成「不支持tools」→整轮静默丢弃零trace→引擎判零产出失败;已修=按报错形状判别;碰LLM通道错误/流式中断先看
metadata:
  node_type: memory
  type: project
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T08:55:04.874Z
---

**2026-10-15 实测根因（需求分析「中断在 Agent fill·本步执行失败」）**：`llm_client` 的 anthropic 分支曾把 `AnthropicChannelError` **一律**包成 `LLMNativeToolsUnsupported`（带 tools 时）——relay 瞬态 429/502 也被当成「上游不认 tools」。后果链：`run_stream_chat_loop` 收到 unsupported → 静默返回 `ok=False` 空结果、**零 trace**（unsupported 路径不落 llm_trace）→ `run_brain_attempts` 三次尝试全灭 → 引擎 `_abort_step("brain_no_output")` → 前端「本步执行失败」，且事后查 llm_trace 无任何线索。

**修复（已落地+回归测试）**：anthropic 两处（`chat_with_tools` 非流式 + `stream_agent_chat` 流式）改走 `_is_native_tools_unsupported(e)` 形状判别——报错含 tools/tool_choice/not support 等标记才降级 Unsupported，限流/5xx/断流如实 `LLMError`（会落 llm_error trace）。另 `_abort_step` 增加 `detail` 参数：`engine_failure.detail` 带最后一次 `result.error`（前端 pause 载荷可诊断）。

**Why:** z.ai relay（cloudprime）间歇 429/502 是常态（见 [[cc-switch-502-root-causes]]）；「不支持 tools」降级假设只在报错形状真是 tools 拒绝时成立，盲降级把可重试错误变成无声丢弃。

**How to apply:** ①诊断同类问题先查 `rules.llm_trace`：连续轮次后「零 trace 断流」≈ unsupported 盲降级或通道前异常；`status=llm_error` = 已如实记录的 LLM 失败；②引擎侧 `engine_pause.failure.detail` 现在带真实错误摘要；③测试锚 `tests/test_llm_wallclock_guard.py`（502→LLMError / tools拒绝→Unsupported 两例）。附带发现：点选续跑回路本身正常——settle 会因「前提字段无客户确认记录：平台类型=Polaris」回喂重试（推断值必须确认机制的正常行为）。关联 [[skill-current-state-2026-09-12]] [[llm-provider-relay]] [[workflow-entry-arming-suggest]]。
