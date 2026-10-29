---
name: llm-stack-notes
description: LLM栈三合一——provider真相(z.ai anthropic端点)/reasoning模型坑/接入策略(全面在线化只留降级);碰LLM链路先看
metadata:
  node_type: memory
  type: project
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T08:57:10.965Z
---

LLM 栈三合一（原独立条目：llm-provider-relay / llm-reasoning-model-pitfall / llm-integration-strategy，原文件仍在磁盘可深查）：

1. **provider 真相**：z.ai 官方 anthropic 端点（`_is_anthropic_upstream` 分流）；能力档案=探测+实测清单 tab。⚠️通道错误分类已修（2026-10-15）：瞬态 relay 错误必须 LLMError 留 trace，见 [[relay-error-misclassified-unsupported]]。
2. **reasoning 模型坑**：思考走 reasoning_content；max_tokens 太小会空回复（已修）。
3. **接入策略**：「离线可跑」已过时，全面 LLM 在线化，只留降级。

关联 [[cc-switch-502-root-causes]] [[relay-error-misclassified-unsupported]]。
