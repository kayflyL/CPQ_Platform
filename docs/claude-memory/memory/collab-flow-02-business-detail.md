---
name: collab-flow-02-business-detail
description: 协作报价流程页面进度：01门户+02业务详情已落地（三表+匹配引擎+六端点），03~06已于2026-10-22定调放弃不做
metadata: 
  node_type: memory
  type: project
  originSessionId: bdbd3ef7-3e87-4cee-b654-7d89edb64f7e
  modified: 2026-10-22T02:36:15.857Z
---

# 协作报价流程（审批流形态）实施进度

设计文档 SSOT：`docs/协作流程方案/01~06-*.md`（页面级）+ `docs/执行方案/多用户协作报价流程.md`（总纲/数据模型）。2026-08-14 完成页面 01（门户，另有会话）+ 页面 02（业务商机详情）。

**页面 02 已落地**（上个会话被 502 打断在实现计划验证，本会话续完）：
- 三张新表（opportunities schema）：`opportunity_flows` / `opportunity_flow_nodes` / `opportunity_requirements`（模型 `models/flow.py`，仓库 `flow_repo.py` 用 `Opportunity_SessionLocal`）
- 匹配度三态引擎 `services/match_engine.py`：复用 candidate_search 纯函数（`_cap_to_gb`/`_filter_cpu_parts_for_platform` 等），NIC 从零建（specs 键 `Link Speed`/`Ports`）；只标注不拦截，异常降级 unknown
- API `api/portal.py` 六端点；中间交付物按 `field.flow.bom/cost` 权限裁剪；final-quote 以 `exported_at` 为定稿标志
- 前端 `/portal/:oppId` + `components/flow/`（RequirementForm 双形态：桌面表格/手机卡片；MatchBadge/FlowTimeline/FinalQuoteCard）；需求单=RequirementSlots 契约（见 [[requirement-gap-match-grading]]）
- 注意：KP 网卡品类名是 `Network(NIC) requirement`（不是 NIC card）；网卡件名兜底解析速率/口数

**未做（⚠️2026-10-22 用户定调放弃，03~06 不再计划做）**：03 执行工作台 `/flow/:oppId`（te/cost/quote/director）、04 核价页、05 调度看板、06 报价工作台增强；流程表 assign/complete/return 动作已有 repo 方法但无 API 入口。

**502 教训**：2026-08-13~14 频繁 502 来自本机推理网关（127.0.0.1:15721）上游断连，并发子代理探索易触发；大任务改为单会话顺序推进 + codegraph_explore 替代多 Read。
