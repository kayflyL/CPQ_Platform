# 业务商机详情页（Business Opportunity Detail）⚠️ 已下线

> 最后更新：2026-09-15

> **本页已下线（2026-09-15）**：`/portal/:oppId` 路由与 `BusinessOpportunityDetail.vue` 已移除，业务/销售角色现与各角色共用统一审批流详情页 `/opportunities/:opportunityId`（OpportunityProcessBoard，按角色后端裁剪）。见 [opportunities/detail.md](../opportunities/detail.md)。以下为历史记录。

## 功能概述

业务/销售角色（business）的**审批式商机视图**（`/portal/:oppId`，从门户点进）——不是技术配置页，只做三件事：**读**商机信息、**改**需求单（结构化部件清单，提交生成新版本重新流转）、**看**最终报价单（定稿后）。中间 BOM/成本/技术选型不可见（后端按角色裁剪，时间线中间节点显示 🔒）。

设计文档：[docs/协作流程方案/02-business-detail.md](../../协作流程方案/02-business-detail.md)（页面结构图/可见性矩阵的权威源）。

## 路由

| 路由 | 组件 |
|------|------|
| `/portal/:oppId` | `views/portal/BusinessOpportunityDetail.vue` |

## 组件

| 组件 | 位置 | 用途 |
|------|------|------|
| `RequirementForm.vue` | `components/flow/` | 结构化需求表单：基本信息 + 部件清单（桌面表格/手机卡片双形态）+ 需求原文；数据模型 = RequirementSlots 契约（`toSlots()/fromSlots()`） |
| `FlowTimeline.vue` | `components/flow/` | 审批流时间线（需求→指派→配BOM→核价→报价），交付物被裁剪时 🔒 |
| `FinalQuoteCard.vue` | `components/flow/` | 最终报价单卡片（价格由后端 `mask_price_fields` 遮罩） |

## 布局

- **桌面（≥769px）**：双栏——左栏商机信息卡（只读）+ 需求单卡（版本 tab + 部件清单表格）；右栏流程时间线 + 最终报价单。
- **手机（≤768px）**：单栏纵向堆叠；部件清单从表格降级为卡片列表（每部件一张小卡）；「更新需求再提交」sticky 底部全宽。
- 玻璃系统：`.glass` 容器 + `--cpq-glass-*` token。

## 需求单机制

- **结构化录入**：业务按部件填（CPU 单行锁定/内存单行/硬盘·网卡·GPU 多行可删加行），不嵌 Excel/Univer。
- **RequirementSlots 契约**：前端组装 slots POST，后端无需反向抽取（与 `LLM_UNDERSTAND_SCHEMA` 同构）。
- **库外不拦截**：平台系列/机箱形态用 `a-auto-complete` 下拉 + 允许手输自由值（见 memory: requirement-gap-match-grading）。
- **版本化**：提交 → 后端写新版本（旧版 archived 留档）→ 流程拉回 requirement 节点重跑；版本 tab 切换纯前端。

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/portal/opp/{oppId}` | 商机信息 + 流程状态 |
| GET | `/api/portal/opp/{oppId}/requirements` | 需求单全部版本（v1/v2… + 当前标记） |
| GET | `/api/portal/opp/{oppId}/requirements/{version}` | 单版本详情 |
| POST | `/api/portal/opp/{oppId}/requirements` | 提交新版本（slots + requirement_text） |
| GET | `/api/portal/opp/{oppId}/flow-timeline` | 时间线（中间交付物按 `field.flow.bom`/`field.flow.cost` 权限裁剪） |
| GET | `/api/portal/opp/{oppId}/final-quote` | 最终报价单（`exported_at` 非空才返回；价格按 `field.opportunity.quote_price` 遮罩） |

前端客户端：`frontend/src/api/portal.ts`（`portalApi`）。

## 数据库表（opportunities schema）

| 表 | 用途 |
|----|------|
| `opportunity_flows` | 一商机一流程（current_node + assignees） |
| `opportunity_flow_nodes` | 时间线节点记录（submit/assign/complete/return + artifacts） |
| `opportunity_requirements` | 需求单版本（slots JSON + status current/archived） |

模型：`backend/app/models/flow.py`；仓库：`backend/app/repository/flow_repo.py`（`FlowRepository`，`Opportunity_SessionLocal`）。
