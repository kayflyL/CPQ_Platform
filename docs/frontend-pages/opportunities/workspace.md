# 报价工作台 (Workspace)

> 最后更新：2026-10-15（报价外发审批门：客户版导出/规格书 PDF 出门前须总监批准——无有效许可弹「导出需总监审批」发起窗（毛利/红线/内容指纹/路由预览），pending 锁定条常驻（禁改价/禁导出/禁发送），批准绑定内容指纹改价失效重批；对内版豁免。2026-10-12 配置 Tab 防挤压等历史见 git）

## 功能概述

报价配置的核心工作区，三栏布局，支持多配置 Tab 切换。

### 核心功能
1. **配置 Tab 栏** — 多配置管理：
   - 添加/删除/重命名配置
   - 右键菜单操作
   - Tab 切换
   - **防挤压（2026-10-12）**：pills `flex: none` + 单行 `nowrap`，配置多/名字长时 `.cfg-pills` 收缩为横向滚动（`min-width: 0` + `overflow-x: auto`，细滚动条），不再出现中文逐字换行成竖排/撑破页面横向溢出；watch `activeCfg` 在切换/新增后把激活页签 `scrollIntoView`（inline nearest），新增页签不会藏在滚动区外。手机端行为不变（原来就是横滑，重复声明已收拢进基础样式）。
2. **左栏：BOM 表格** — 纯展示（固化快照）：
   - 展示当前配置的 BOM 清单
   - 分两个区域：L6 配置（机箱部件，无成本）+ KP 配置（关键部件，有成本）
   - 从 Excel 上传时为固化快照，新建模式跟随中栏
   - 读取 `cfg.bom_template`, `cfg.bom_context`, `cfg.items`, `cfg.bom_excel_rows`
3. **中栏：服务器配置** — 核心编辑区：
   - 服务器型号选择（自动完成）
   - 数量设置
   - 配置描述
   - 各部件配置（CPU、内存、硬盘、GPU、网卡、电源、散热器等）
   - 推导引擎联动（功耗/PSU/GPU线缆/背板自动推导）
   - 手填兜底（推导不可用时手动填写）
4. **右栏：定价与利润** — 实时计算：
   - 成本合计
   - 售价计算
   - 利润率显示
   - **利润率告警**：综合毛利率低于门槛时弹一次性 Modal 提示线下特价审批。告警走**独立策略 `pricing.margin_alert`**（开关 `enabled` + 门槛 `threshold` + 标题 `title` + 正文 `content` 模板，正文支持 `${margin}`/`${threshold}` 占位符），经 `pricingRulesStore.getMarginAlert()` 读取；**阈值与文案都在策略中心「利润率告警」编辑器（`MarginAlertEditor.vue`，挂在定价画布）配，不再硬编码**。策略中心定价只作建议，告警**只警告不锁价、不自动改价**，与保底封顶（引擎 clamp）解耦。默认门槛 7%（`DEFAULT_MARGIN_ALERT`，seed 进 DB 可见可改）。（历史：曾借 `guardrail.floor` + 硬编码文案，2026-07-31 重构为独立 `margin_alert` 策略；早期 `system_config.profit_margin_alert_threshold` 阈值已于 2026-08-10 作为死码清除）
   - 价格参数调整

### 预览与导出模板

底部操作栏「预览」按钮的模板选择器合并了两套模板体系（`<a-select-opt-group>` 分组）：

- **Excel 模板**（`/api/univer-templates`）— Univer workbook 快照 + 单元格绑定。预览调 `univerTemplateApi.preview` 返回填充后的 `workbook_snapshot`，模态框内用 `UniverSheet` 渲染；确认按钮「下载 Excel」从 live Univer 实例读样式经 exceljs 写出 xlsx。
- **规格书模板**（`/api/spec-templates`）— 品牌 + 显示开关/标签。预览调 `specTemplateApi.getPreviewData` 拿 `configs`，模态框内用 `SpecSheet` 渲染（branding/display_options 取自选中模板）；确认按钮「打印为 PDF」走 `window.print` + Teleport overlay（复用 SpecSheet 的 `@media print` 规则）。

选择器 value 编码为 `excel:{id}` / `spec:{id}`（两套表 id 序列独立、可能重叠，前缀消歧），由 `selectedTemplate` computed 解析出 `{ type, id }` 驱动分流。默认选 Excel 默认模板；无 Excel 才回落规格书默认。


- 中栏 → 左栏单向联动
- Excel 模式：左栏 = 固化快照（不随中栏变化）
- 新建模式：左栏跟随中栏

## 移动端双抽屉（≤768px，2026-09-19）

改动集中在 `Workspace.vue` 手机分支（`isMobile` matchMedia ≤768），桌面三栏零改动：

- **主屏**：cfg-bar 横滑瘦身（返回按钮 `‹` 并入行首、配置 pills 横滑、关系切换保留、隐藏「配置关系」标签）+ 中栏编辑区独占（型号/数量/描述/三段 seg/KP 行内编辑表横向滚动）。
- **左抽屉**（placement=left，宽 90%）：`<BomTable :cfg="activeConfig">` 整体复用（固化快照只读对照）。
- **右抽屉**（placement=right，宽 88%）：fin-card 全量复刻（含税总价 hero / 成本 / 利润 / 毛利率 / 备选模式方案对比 / 税率汇率）+ 选型建议卡 + 「预览与导出」卡（导出模板 select + 预览按钮，v-model 同 `selectedTemplateValue`）。**与桌面 col-right 复刻自两份 markup，改动需两处同步**（源码有注释标记）。
- **底部 sticky 摘要条** `.sumbar`（fixed，`bottom: var(--cpq-tabbar-inset)` 避让全局底栏）：📄 BOM 入口 + 含税总价/毛利率（无 `priceVisible` 显示 *** 并提示权限受限）+ 💾保存商机（走现有 `handleSave`）。
- **互斥**：`openDrawer: null | 'bom' | 'fin'` 单状态；action-bar 手机端隐藏（返回/模板/预览/保存分流至顶栏、右抽屉、摘要条）。
- 外壳 `.opp-quote-drawer` 走主题 token 玻璃（组件内全局 style 块，portal 够不到 scoped）。
- 原型：[docs/prototypes/quote-workspace-mobile.html](../prototypes/quote-workspace-mobile.html)

## 前端路由

| 路由 | 组件 |
|------|------|
| `/quote/:opportunityId/:quotationId` | `views/quote/Workspace.vue` |

## API 端点

### 报价数据
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/quotations/{id}` | `quotationApi.getById` | 加载报价单数据 |
| GET | `/api/quotations/{id}/items` | — | 获取报价单配置项 |
| POST | `/api/quotations/{id}/items` | `quotationApi.saveItems` | 保存配置项 + 配置级字段 |
| POST | `/api/quotations/{id}/export` | `quotationApi.export` | 导出动作：冻结为已导出（盖 exported_at + 落 cost_snapshot） |
| POST | `/api/opportunities/save` | `projectApi.save` | 保存报价（含配置+文件） |

### 导出模板（预览用）
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/univer-templates` | `univerTemplateApi.list` | Excel 模板列表（选择器） |
| POST | `/api/univer-templates/{id}/preview` | `univerTemplateApi.preview` | Excel 预览：填数据返回 workbook_snapshot |
| GET | `/api/spec-templates` | `specTemplateApi.list` | 规格书模板列表（选择器） |
| GET | `/api/spec-templates/preview-data` | `specTemplateApi.getPreviewData` | 规格书预览：按商机/报价单返回 configs（喂 SpecSheet） |

### 配件查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表（选择部件） |
| GET | `/api/parts/sections` | `partsApi.sections` | 配件段列表 |
| GET | `/api/parts/categories` | `partsApi.categories` | 配件分类 |
| GET | `/api/parts/{pn}` | `partsApi.get` | 单个配件详情 |

### KP 配件同步/入库
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/quote/kp/history?model=` | `getKpHistory` | 按型号查 KP 价格历史；前端取首条作 db_price（含日期 db_price_date），定按钮显隐与 同步/采纳/入库 三分流 |
| POST | `/api/quote/kp/sync-price` | `syncKpPrice` | 同步价格 / 入库新配件（同一接口，后端按型号是否存在分流） |

### 推导引擎
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/derive` | `deriveApi.derive` | 传当前配置状态，返回推导结果 + 约束校验 |

### 系统配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/system-config/{key}/value` | `systemConfigApi.getValue` | 系统配置参数（税率/汇率等） |

### 规则
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/rules/export-categories` | `getExportCategories` | 导出分类规则 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `quotations` | 报价单主表（template_json 存配置） |
| `opportunities` | `quotation_items` | 报价配置项 |
| `l6` | `parts_master` | 配件主数据（查价） |
| `l6` | `base_configs` | 基准配置 |
| `rules` | `system_config` | 税率/汇率/利润率等参数 |
| `rules` | `matching_rules` | 匹配规则 |
| `kp` | `kp_parts` | KP 配件主数据（报价工作台同步/入库目标） |
| `kp` | `kp_categories` | KP 配件分类（入库时按名查/建） |
| `kp` | `kp_price_history` | KP 配件价格历史（同步/入库都追加一条） |

## 关键组件

- `BomTable.vue` — 左栏 BOM 展示表格（L6 区 + KP 区）
- `UniverSheet.vue` — Excel 模板预览渲染（Univer 实例，非编辑模式）
- `SpecSheet.vue` — 规格书模板预览/打印渲染（白纸文档，多配置一页一配置；复用其 `@media print` 规则做 PDF 导出）
- Pinia store — 配置状态管理（store.configs）

## 注意事项

- `template_json` 是不透明 blob，前端加字段无需改后端
- 推导必须带手填兜底，缺失不阻塞不崩
- 所有业务参数（税率、汇率等）从 system_config 读取，代码不硬编码
- **导出即冻结**：点「下载 Excel」后，前端从 store（`getConfigTotals` + `l6_section_totals` + 汇率/税率）组装 cost_snapshot 并 POST `/quotations/{id}/export`，后端盖 `exported_at` + 落库。冻结后该报价单不再进工作台（在详情页点开只看成本快照 + Excel），编辑需「重新解析」生成新报价单。冻结比实时重算更准——反映导出当时的价格。
- **报价外发审批门（2026-10-15）**：三口一闸——客户版导出冻结（`/quotations/{id}/export` 后端硬闸）、平台内发送（portal submit 端点）、规格书 PDF（前端前置检查；服务端 print-pdf 是通用渲染器不区分内外，不挂闸），出门前须持有效外发许可。**批准 = 对 content_hash（报价行+单头 sha256 前 16 位）的许可**，改价失配自动失效重批；pending 期间 `/quotations/{id}/items` 保存端点同锁（禁改价）。工作台：预览弹窗点确认 → `outboundApprovalStatus` 查状态 → approved 放行 / pending 提示等待条 / 其余弹「导出需总监审批」发起窗（毛利 vs 红线、内容指纹、指派预览=调度面板 approval 规则）。对内版导出豁免（前端不调冻结端点）。闸门逻辑统一在 `services/quote_outbound_gate.py`；原型 docs/prototypes/报价外发审批-原型.html。

- **KP 行价方向感知（2026-10-09）**：KP 行与库最新价不一致时**按「谁更新」分流按钮**，不再一律提示同步。判定 = 行价锚点 vs 库最新价日期：锚点 = 行级 `price_set_at`（行价最近一次被人为改动的时间）→ 回落单据 `exported_at`（解冻后为空）→ `created_at`；库侧日期来自 `getKpHistory` 首条的 `date`。库新 → 状态「⏬ 库价已更新」+ 按钮**「采纳库价」**（库→行回填，折算本行币种重算，不写库；同单同型号旧行可勾选一并采纳）；行新或日期判不了 →「📈 行价新」/「⚠️ 差异」+「同步价格」（原行为）。行价锚点由后端落库：`quotation_items.price_set_at` 列（boot 自愈 `ensure_quotation_item_price_set_at`），`save_items` 全删全插前逐行 diff `base_price`——变了盖 now、没变沿用旧锚、新行盖 now；门户 `patch_items` 改 KP 行价同样盖。解冻旧单没动过的旧行因此不再诱导把历史价写回库盖新价（原「只要数值不等就亮同步按钮」的缺陷）；`quoteCommon.kpSyncable` 已删除，由 `kpPriceAction` 取代。
- **KP 配件同步/入库**：型号有历史 →「同步价格」，完全不在库 →「入库新配件」。两者走同一接口 `syncKpPrice`，后端 `kp_repo.insert_price` 按型号查 `kp_parts`：已存在只追加一条价格历史（同步，连 `category` 都不读），不存在才按分类名查/建 `kp_categories` 并新建 part（入库）。**入库分类 = 该 KP 行的 `part_category`**（CPU/GPU/硬盘…，非系统推断，沿用配置里所属的配件分组），为空兜底 `'Key Parts'`。入库落裸记录（仅 name + category_id + 一条价格），品牌/OEM SKU/specs 为空，需事后去管理面补。
- **同步弹窗可改价（2026-09-14）**：弹窗内「价格」行 = 可编辑的 `a-input-number` + 币种下拉（RMB/USD，受 `priceVisible` 门控）。确认时**先写回报价行（`item.base_price/currency` + `recalculateAll`）再调 `syncKpPrice`**——改价即改行，保证行价 = 入库价一致，不会出现「库里改了行上没改」导致的同型号码价劈叉与「同步价格」误提示。
- **改历史最新价（2026-09-14）**：录错价/选错币种的就近修正入口 = 「历史价格」弹窗内**最新一条的「修改」按钮**（原地编辑价/币种/备注，仅最新条可编辑，历史条目只读；无价格权限不显示按钮）。后端 `PUT /quote/kp/price-history/{id}` 带**乐观锁**（该 id 必须仍是排序 `price_date DESC, id DESC` 的第一条，否则 409）；历史 append-only 不删条目，改值留 note 说明。保存后弹窗列表 + 全配置页同型号行的库参考价（db_price/db_currency/match_status）就地刷新，**不动各行报价**——若行价与新库价有差异，行上自然出现「同步价格」按钮，是否对齐由用户决定。三个 KP 端点（history/sync-price/normalize-category）此轮一并挂上 `current_user` 鉴权。
- **KP 行原始单价可手改（2026-09-29）**：Excel 模式 KP 表与新建模式 KP 卡的「原始单价」从只读改为可编辑输入框（受 `priceVisible` 门控，无权限显 `***`）。编辑口径 = **所见即所改的 RMB 含税价**（与该列显示一致；USD 行经 `quoteCommon.rmbToBasePrice` 反解回原币种 `base_price`，不取整保证回显不漂）。此前解析不出价/库价为 0 的行是死路：原始单价只读、利润率乘 0 仍 0、同步弹窗拒开（"价格为空"）、历史弹窗只改库价不动行——现在行内直接补价后 `match_status` 重算（❌ 缺失 → 🆕 新部件），同步/入库按钮随之可用，可顺手把补的价入库。
- **KP 卡数量上限 + 能力规则注入（2026-10-02）**：新建模式 KP 卡数量控件按基准配置能力档案夹紧（KpCategoryCard `maxQty` prop，`maxQtyFor(cfg, cat)` 映射 CPU→max_cpu / Memory→max_dimm / GPU→gpu_slots / HDD-SSD→bays，未配置→不限；上限按类别总数算，多行分摊；机箱弹窗电源夹 `psu_bays`）。`buildRuleContext` 此前只注 series/盘类计数——**max_cpu/max_dimm 等能力字段缺失导致「CPU/内存超上限」规则在工作台从不触发**，现已补注全套能力字段 + `psu_qty`（取 `cfg.bom_context.psu_qty`），配合规则库五条上限规则（CPU id25/内存 id26/GPU id35/盘位 id36/电源 id37，category=机箱能力校验）在右栏提醒列表正常出黄条。
