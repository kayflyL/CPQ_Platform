# 商机详情页 (OpportunityDetail)

> 最后更新：2026-07-29

## 功能概述

单个商情的详情管理页面，以「证据链 + 智能化生成」为主线。**双栏布局**：顶部商机信息卡（全宽）→ 下方左右两栏，**左栏=客户需求 + 「生成报价」入口 + 推理过程面板**，**右栏=报价单列表（上） + 存档区（下）**；右侧抽屉为协作动态。窄屏（<1100px）自动回落单栏。

**智能化生成主线（整机方案级 · 本地）**：客户需求原文 → 点「生成报价」→ 后端本地 pipeline（jieba 分词 → 选基准机型 → 配 KP → 组合整机方案）→ 推理面板实时展示步骤 + **2-3 张整机 BOM 方案卡** → 人工选一张「确认转为报价单」→ 草稿进右栏 → 跳工作台调价。一期纯本地、不调 LLM（"最合适"语义判断留待 LLM 增强层）；二期模块（LLM 择优/向量相似度/自动调参/历史报价/线上审批/驳回回流）在面板内灰显占位。

### 核心功能
以「证据链」为主线：客户需求 → 技术BOM/已发报价存档 → 报价单。

1. **商机信息卡片** — 行内编辑模式（商务信息：谁/条款）：
   - 页面标题取**客户名称**（无则显示「未命名客户」）
   - 字段：客户名称、销售人员、FAE、报价人员、平台类型、机箱形态、采购数量（备注统一到活动流；原 `opportunity_name` 字段已移除，历史值已迁入活动流）
   - 自动完成（读字段历史值，`:default-active-first-option="false"` —— 回车保留用户输入文本、不抢选下拉项）；支持动态字段（business_fields 表）；内联输入透明底融入卡片（聚焦才蓝边），消除多字段密集感
2. **客户需求卡** — 贴入客户需求原文（表格/文字均可），blur 保存到 `extra_fields.customer_requirement_text`，纯参考不约束配置。卡内底部「**生成报价**」按钮触发智能化 pipeline（见下「推理过程面板」）。
3. **推理过程面板**（`ReasoningPanel.vue`，生成后出现）— **对话式消息流** UI（Glass Console 原生）：
   - 头部一个克制 `RobotOutlined` + 状态条（跑哪步显哪步名 / "N 张方案" / "失败"）
   - **逐步推送**：pipeline 每步完成 → 弹一条自然语言 AI 消息（extract→"抓到关键信息…"、select_baseline→"挑了 N 个整机骨架…"、match_kp→"配了 N 件 KP…"、compose→"组合出 N 张方案…"）；运行中显三点打字指示
   - **整机方案卡**（2-3 张，作为消息推入流）：左渐变 signature 描边 + 阴影的"主角"卡，显整机摘要（型号 / 系列·形态·盘位 / 底盘件数 + KP 件数 / 合计成本）+「查看 BOM 详情」（抽屉复用工作台 `BomTable`；L6 按基准配置的 **BOM 模板格式** 渲染，经 `usePlanBom.buildPlanCfg` 跑 `evalBomContext` 求值，无模板回落平铺）+「确认转为报价单」
   - 二期脚注（一条 muted 消息："接入 LLM 后还能…"，替代原灰显列表）
   - 面板**粘顶 + 高度跟随视口**（`clamp(260px, calc(100vh - 400px), 600px)`），feed 子项 `flex-shrink:0` 保固有高度、靠内部滚动（避免 overflow:hidden 把方案卡压扁裁字）
   - 确认转为报价单：所选方案 → 创/换草稿（一商机一草稿，已有则 `Modal.confirm` 替换）→ KP 行存 quotation items、整机 L6（`bom_source:'live'`+`bom_template`+`bom_context`+`base_config_id`+`l6_custom_price`，无模板时回落 `bom_excel_rows`）存 `config_l6_picks` → 跳工作台 `mode=edit`
4. **存档区**（`ArchiveSection.vue`，**位于右栏报价单下方**）— 三分类文件管理，基于 `FeedAttachment` 表 + `category` 列：
   - 需求文档（requirement）/ 方案·详细报价（technical）/ 已发报价（sent_quote）
   - 每栏独立上传（带 category）、下载、删除；支持拖拽上传
   - 文件可在三分类间**移动**（每行下拉切 category → PATCH `/api/feed/attachments/{id}/category`，WS 广播后自动挪栏）
   - 报价单导出时自动归档一份到 sent_quote（见 Workspace 导出钩子）
5. **活动流**（新增，`ActivityStream.vue`）— 极轻活动/备注，复用 `FeedMessage`（kind=system 自动事件 + kind=comment 手动备注），按时间倒序，底部加备注。
6. **报价单列表** — 展示所有报价单：
   - 状态指示灯（利润率色条：高/中/低/负）、主推标记（is_primary）
   - **草稿/已导出状态标**（`exported_at`）：草稿=可进工作台编辑；已导出=冻结，点击只开成本快照抽屉（不再进工作台）
   - 一商机**至多一个草稿**：点「新增报价」若已有草稿则直接打开；编辑已导出报价单需「复制为草稿」生成新草稿
   - 操作：设为主推、查看/编辑（同一按钮按状态：草稿→进工作台 / 已导出→开成本抽屉）、重命名、删除；批量选择删除
   - **成本快照抽屉**（`QuotationCostDrawer.vue`）：多配置时**每个配置一个独立整机汇总**（单台 成本/售价/利润率 + L6/KP/质保分段表 + KP 逐项利润率，各配置利润率独立、不跨配置混算），顶部全局费率（汇率/税率/冻结时间）；项目总计（Σ 单台×台数）存 `cost_snapshot.totals` 备列表反写。底部「查看 Excel」（下 sent_quote 归档件）+「复制为草稿」（克隆源的 DB items+配置字段 → 新建草稿并跳工作台）。
   - **手工补录成本**：历史导入报价单无快照时（`!has_cost_snapshot`），列表行显「补录成本」按钮 → 开抽屉录整机级成本/售价（利润额/率自动算），保存落 `cost_snapshot`（`manual:true` 标记，**不动 `exported_at`**）。两种 schema 共存：完整快照（导出冻结，含 configs/kp_items/rates）vs 手工补录（仅 totals）；抽屉按数据形态分流渲染。
   - **列表数字来源**：`total_price` / `profit_margin` / `total_qty` 在导出冻结 / 手工补录时由 `cost_snapshot.totals` **反写**（项目总价 = Σ 单台×台数、综合利润率 = 按成本加权、总台数 = Σ config_qty），与抽屉口径一致；草稿态仍走 `calculate_totals`（Σ items.final×qty，不含机箱、不按台数加权，值偏旧）。多配置（`config_count>1`）时利润率 badge 旁显「综合」角标。
7. **回收站抽屉** — 已删除报价单：恢复 / 永久删除、批量
8. **上传报价单** — 拖拽上传 Excel → **先弹解析预览**（左热力图核对取值位置 / 右调区域边界与取值列规则，保存后用原文件自动重算）→ 确认后才生成报价单。解析规则与「设置-解析规则」页共用同一套（`useExcelParser` 单例 + `ParseHeatmapPreview`/`ParseRulesEditor` 子组件），弹窗内调规则即改全局规则；预览走 `/api/rules/excel-parser-preview`（纯解析不落库），确认落库走 `/api/quote/upload-to-opportunity`。
9. **协作动态** — 右侧抽屉（OpportunitySidebar → OpportunityFeed），仅留**消息 + 在线状态**（文件 Tab 已移除，文件统一走存档区）。
10. **商机操作** — 归档/取消归档、删除

## 前端路由

| 路由 | 组件 |
|------|------|
| `/opportunities/:opportunityId` | `views/opportunity/OpportunityDetail.vue` |

## API 端点

### 商机操作
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/opportunities/{id}` | `projectApi.getById` | 获取商机详情（含报价单列表） |
| PUT | `/api/opportunities/{id}` | `projectApi.update` | 更新商机信息（支持动态字段） |
| PUT | `/api/opportunities/{id}/meta` | `projectApi.updateMeta` | 更新元数据 |
| POST | `/api/opportunities/{id}/trash` | `projectApi.trash` | 删除商机（移至回收站） |
| POST | `/api/opportunities/{id}/restore` | `projectApi.restore` | 恢复商机 |
| GET | `/api/opportunities/field-history/{field_key}` | — | 字段历史值（自动完成） |

### 文件 / 存档（FeedAttachment）
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/feed/{opp_id}/attachments` | `feedApi.attachments.list` | 存档区文件列表 |
| POST | `/api/feed/{opp_id}/attachments` | `feedApi.attachments.upload` | 上传（带 category/quotation_id/kind） |
| PATCH | `/api/feed/attachments/{id}/category` | `feedApi.attachments.updateCategory` | 文件在分类间移动 |
| GET | `/api/feed/attachments/{id}/download` | `feedApi.attachments.downloadUrl` | 下载 |
| DELETE | `/api/feed/attachments/{id}` | `feedApi.attachments.remove` | 删除（软删） |

> 旧的 `/api/opportunities/{id}/files/*` 扫盘 API + `folder-path` 已移除（路由、`OpportunityFile` model/repo、`OpportunityFiles.vue` 组件全部删除；DB 表保留，DROP 见 `backend/migrations/drop_opportunity_files.sql`）。

### 报价单操作
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/quotations` | `quotationApi.getByOpportunity` | 获取商机下所有报价单 |
| GET | `/api/quotations/{id}` | `quotationApi.getById` | 获取报价单详情 |
| POST | `/api/quotations` | `quotationApi.create` | 创建报价单 |
| PUT | `/api/quotations/{id}` | `quotationApi.update` | 更新报价单 |
| DELETE | `/api/quotations/{id}` | `quotationApi.delete` | 删除报价单 |
| POST | `/api/quotations/{id}/restore` | `quotationApi.restore` | 恢复报价单 |
| POST | `/api/quotations/{id}/set-primary` | `quotationApi.setPrimary` | 设为主推 |
| POST | `/api/quotations/{id}/export` | `quotationApi.export` | 冻结草稿为已导出（盖 exported_at + 落 cost_snapshot） |
| POST | `/api/quotations/{id}/reparse` | `quotationApi.reparse` | 复制已导出报价单为草稿（克隆 DB items+配置字段，不解析导出件；一商机一草稿，冲突 409） |
| PUT | `/api/quotations/{id}/cost-snapshot` | `quotationApi.saveCostSnapshot` | 手工补录历史报价单成本（只写 cost_snapshot，不动 exported_at） |
| POST | `/api/quotations/{id}/items` | `quotationApi.saveItems` | 保存报价配置项 |
| POST | `/api/quotations/batch-delete` | `quotationApi.batchDelete` | 批量删除报价单 |
| POST | `/api/quotations/batch-restore` | `quotationApi.batchRestore` | 批量恢复报价单 |
| POST | `/api/quotations/batch-permanent-delete` | `quotationApi.batchPermanentDelete` | 批量永久删除 |

### 报价上传解析
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/rules/excel-parser-preview` | `useExcelParser.handleFileUpload` | 解析预览（热力图+结构化结果，纯解析不落库；商机上传预览与设置页共用） |
| POST | `/api/quote/upload-to-opportunity` | `uploadQuotationToProject` | 确认后落库：解析 + 创建报价单 + 归档源文件 |
| GET | `/api/quote/kp/history` | `getKpHistory` | 获取 KP 价格历史 |
| POST | `/api/quote/kp/sync-price` | `syncKpPrice` | 手动同步 KP 配件价格 |

### 推理流（智能化生成 · 一期）
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/reasoning/{opp_id}/generate` | `reasoningApi.generate` | 触发推理 pipeline（jieba 分词 → 选 baseline → 配 KP → 组合整机方案），后台异步跑 |
| WS | `/api/reasoning/ws/{opp_id}` | `reasoningWsUrl` + `useReasoningStream` | 推理步骤流（step_start / step_done / candidates_ready{plans} / pipeline_done / error） |
| GET | `/api/candidate-search?q=&series=&form=` | — | 散件级聚合检索（L6 料号 + KP 配件 + 基准配置），ILIKE，保留供调试；pipeline 走 `compose_plans` 出整机方案 |

> pipeline 实现在 `backend/app/services/requirement_intel_service.py`，聚合检索逻辑在 `backend/app/api/candidate_search.py`（`search_candidates()` 供 pipeline 和 REST 共用）。WS hub `reasoning_hub.py` 与聊天助手通道物理隔离（按 opportunity_id 分房间）。利润率告警在工作台（见 `workspace.md`），阈值读 `system_config.profit_margin_alert_threshold`，不写死。

### 动态字段
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/fields/page/{page}` | `getFieldsByPage` | 获取页面字段定义 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `opportunities` | 商机主表 |
| `opportunities` | `quotations` | 报价单列表（template_json 存配置） |
| `opportunities` | `opportunity_files` | *已废弃*（代码层移除，DROP sql 待执行） |
| `rules` | `business_fields` | 动态字段定义 |
| `rules` | `system_config` | 全局可配置项（key-value）：`profit_margin_alert_threshold` 利润率告警阈值、`default_markup_coefficient` 加成系数（未来统筹配置页遍历此表） |
| `public` | `comments` | 商机评论/批注 |

## 关键组件

- `ArchiveSection.vue` — 存档区（三分类文件管理，基于 FeedAttachment + category，支持分类间移动）
- `ActivityStream.vue` — 极轻活动流（FeedMessage system/comment），也是详情页唯一的「备注」入口
- `OpportunitySidebar.vue` — 协作动态抽屉壳（内渲染 OpportunityFeed）
- `OpportunityFeed.vue` — 实时消息 + 在线状态（WebSocket；文件 Tab 已移除）
- `QuotationCostDrawer.vue` — 已导出报价单的成本快照抽屉（只读展示冻结成本 + 查看 Excel / 重新解析入口）
- `QuotationParsePreviewModal.vue` — 上传报价单的解析预览弹窗（左热力图 / 右规则编辑器，调规则自动重算、确认后落库）；复用设置页的 `useExcelParser` + `ParseHeatmapPreview` + `ParseRulesEditor`（见 `settings/excel-parser.md`）
- `ReasoningPanel.vue` — 推理过程面板（步骤时间线 + 整机方案卡列表 + BOM 详情抽屉复用 `BomTable` + 确认转为报价单；二期步骤灰显占位）
- `useReasoningStream.ts` — 推理流 WS composable（步骤 / 整机方案 plans 状态，独立于 feed / assistant WS）
- `usePlanBom.ts` — 方案→BomTable 可渲染 cfg：`buildPlanCfg(plan)` 取模板+底盘件跑 `evalBomContext` 出 bom_context（live 模板格式 L6），无模板回落 excel 平铺
- `usePricingRules.ts` — 定价规则 composable（读 system_config 的利润率阈值 / 加成系数，不写死）
- `getFieldsByPage()` — 动态字段加载

## 文件存储

存档区文件由 `FeedAttachment` 表（`opportunities.opportunity_attachments`）索引，物理落盘在 `backend/storage/...`（`storage_key` 为 UUID，不依赖 folder_name）。文件元数据走 DB 查询，非扫盘。详见 `backend/app/models/feed_attachment.py`。

旧的 `/api/opportunities/{id}/files` 扫盘 API + `OpportunityFiles.vue` 已废弃（孤儿组件，未清理）。
