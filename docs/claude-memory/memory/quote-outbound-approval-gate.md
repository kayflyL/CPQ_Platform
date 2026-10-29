---
name: quote-outbound-approval-gate
description: "报价外发审批门M1:三口一闸(导出冻结/发送/规格书),批准=对content_hash的外发许可改价重批,路由=调度面板approval伪节点按业务指派总监"
metadata:
  node_type: memory
  type: project
  originSessionId: 53a1d8a0-346c-442f-b135-ac766a37d3e0
  modified: 2026-10-15T09:01:42.434Z
---

报价外发审批门（2026-10-15 M1 落地,原型 docs/prototypes/报价外发审批-原型.html 定稿）:

- **三口一闸**:客户版导出冻结(`/quotations/{id}/export` 后端硬闸)、平台内发送(portal submit)、规格书 PDF(**仅前端前置**——服务端 print-pdf 是通用渲染器不分内外,不挂闸);对内版导出前端不调冻结端点天然豁免
- **批准=对内容指纹的许可**:`content_hash`=报价行+单头 sha256 前 16 位(services/quote_outbound_gate.compute_content_hash);approved 但 hash 失配=stale 须重批;pending 期间 `/quotations/{id}/items` 保存端点同锁禁改价
- **路由**:调度面板伪节点 `approval`(FlowAssignmentRule.node_key 自由字符串无需迁移,_ASSIGN_ROLE_BY_NODE 加 approval→director);`resolve_node_assignee(opp_id,'approval')` 按业务→唯一总监,无规则降级广播先到先批;upsert/delete/remove-handler 三个规则端点放行 approval,assign_portal_task 不放行(非流程节点)
- **闸门/路由/通知统一在 services/quote_outbound_gate.py**(portal 与 quotations 两 API 共用,避免互 import);旧 _margin_gate_config 等四函数已删
- 超时=懒提醒(读队列/状态时触发 maybe_escalate,remind_hours 配在 margin_alert 策略,默认24h),只提醒不自动批/拒;催办 1h 限速;转交链存 transfers JSON 改责任重置计时
- **免审批权限** `action.quote.export_bypass_approval`(admin 恒有,director 种子自带,角色设置可勾):ensure_outbound_approved(quotation, user) 持权直通;items 保存锁/分享闸/workspace 锁定条与保存锁同样放行;status 端点回 bypass 标志给前端直通
- 审批卡/裁决条在 QuoteWorkbench;待审批队列在 PortalDispatchPanel;发起窗在 Workspace 导出

**Why:** 用户定调"报价单出门必过总监"+多总监要单一责任人;批 A 发 B 由 hash 语义结构性堵死。
**How to apply:** 碰报价导出/发送/审批先看;旧审批单(无指纹)升级后视为 stale 会要求重批(fail-closed 有意为之);二期自动报价=同一闸门换触发方式。相关 [[strategy-center]] [[portal-flow-perms-audit]]
