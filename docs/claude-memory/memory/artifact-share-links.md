---
name: artifact-share-links
description: 产出物分享(网盘式):ShareDialog公共组件+三视角全走模板管线(scheme/cost/customer)+免登录token下载;customer视角quote来源挂外发审批闸
metadata:
  node_type: memory
  type: project
  originSessionId: 53a1d8a0-346c-442f-b135-ac766a37d3e0
  modified: 2026-10-15T07:31:36.159Z
---

产出物分享（2026-10-15 落地，原型 docs/prototypes/产出物分享-原型.html 定稿；同日用户反馈迭代：内部视角删除、三视角全走模板管线、预览窗口放大）：

- **ShareDialog 公共组件**（components/opportunity/ShareDialog.vue）：方案卡/成本表行/报价单行「分享」入口，传 sourceType+sourceId 即复用；API=api/artifactShare.ts；弹窗 960 宽+预览 56vh
- **三视角全走导出模板管线**（用户定调"内部的不要，仅在报价工作台导出用"）：scheme=价格列全 hide / cost=只显成本（需 field.quote.export_internal——链接接收方免登录，创建者权限是唯一闸门）/ **customer=完整报价：quote 来源的创建/预览/下载须过 ensure_outbound_approved（与导出/发送同闸）；cost/scheme 来源属内部传阅不闸**
- **方案/成本投影**：`quasi_source_from_configs`（configs JSON → Quotation 同构 SimpleNamespace + items；L6 走 live 模板路径= bom_template 单行 + config_l6_picks 一口价）→ preview_data_loader 新增 source/source_items 入口；三节点同一条 fill_snapshot 管线，服务端 snapshot_to_grid→openpyxl 出 xlsx（数值+列宽）
- **基建**：`opportunities.artifact_share_tokens`（token=urlsafe(32) 即凭证，过期/撤销/可选提取码/下载计数）+ **免登录端点 /api/share/{token}(/*download)**（无 Depends，部署层若有统一鉴权需放行）；生成即归档附件桶（kind=export，category 按 quote→sent_quote/cost→requirement/scheme→technical）
- 发起弹窗公共组件 OutboundApprovalModal（导出口+发送口共用，发送 409 原地弹）；需求单分享 fast-follow（表单形状需自己的版式）

**Why:** 系统内无聊天，转发=网盘式链接；模板 reveal 机制使"三表=三个视角"零新模板；方案/成本与报价单 configs 结构同构使投影成本低。
**How to apply:** 碰分享/导出/转发先看；新节点接入=ShareDialog 传参+service SOURCE_CATEGORY 加映射；给 quote 来源加新出口时记得接 ensure_outbound_approved。相关 [[quote-outbound-approval-gate]] [[strategy-center]]
