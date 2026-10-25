# Excel 解析器 (ExcelParser)

> 最后更新：2026-09-27

## 功能概述

Excel 报价单/成本表解析配置页面，管理解析模板、解析规则和区域映射。

### 核心功能
1. **解析模板层（2026-09-26 新增；2026-09-27 匹配链退役）** — 多模板隔离 + 标准文件：
   - 「解析模板」tabs：每个模板有独立区域定义+字段映射；存量规则迁入「通用」兜底模板
   - **模板归属=使用位置绑定（09-27 终版）**：哪个入口用哪套模板在此页「使用位置」行配置（当前唯一入口：成本核算 · 上传解析；入口注册表在后端 `PARSE_SCOPES`，新增上传入口时登记后此处自动出现绑定行）。上传弹窗**不再让用户选模板**、不记忆上次选择——只读显示后端按绑定裁决的结果；未绑定/模板已删除/已停用一律落「通用」兜底。早期「指纹→打分」匹配链与「下拉记住上次选择」两版均已退役（引擎文件与测试随删，DB 惰性列保留）
   - **标准文件（用户提供的配置表标准模板，v8 起为准）**：页签条「下载标准模板」下载当前模板的标准 xlsx（现内容=用户提供的 `配置表标准模板.xlsx`，LLW 族改良版式），发给外部照填；设置页中部 Excel 预览未上传文件时常驻显示该标准模板（切模板页签跟着切，用户上传后覆盖显示）；自检 failed/stale 时下载被 409 拦（确认可强制）。模板管理卡（启停/克隆/重命名/删除/重新生成/上传替换/跑自检/版本显示）已按用户定调整体删除——自检只在重新生成时自动跑，作为下发前回归闸门
   - **自检**：样例文件+期望快照逐格回归，跑完回写 passed/failed/stale；改规则后自动转 stale
   - 模板管理：克隆建新 / 重命名 / 启用停用 / 删除（兜底不可删）
2. **解析区域配置** — 定义 Excel 中不同区域的解析规则：
   - 区域名称（如 L6 / KP / server 静态区）
   - 起始关键词 + 结束关键词
   - 跳过行数（skip_header_rows）
3. **字段解析规则** — 定义每个字段的提取逻辑：
   - 字段名（如 l6_chassis, kp_model）
   - 提取方式（keyword / column）
   - 列提取：固定列字母 + 可选「表头关键词」——同模板不同 sheet 表格整体左右偏移时（表头前空列数不同），按表头行投票定位实际列，找不到时退回固定列字母
   - 关键词提取：关键词列表、值偏移量、值清洗正则
4. **预览解析** — 上传 Excel 测试解析效果（按当前 tabs 选中的模板解析）
5. **业务字段映射** — 将 Excel 字段映射到系统字段（全局，不分模板）；KP 分类映射同

> 页面现已瘦身：解析逻辑抽到 `useExcelParser` composable（模块级单例），热力图与规则编辑抽为 `ParseHeatmapPreview` / `ParseRulesEditor` 子组件。**这套规则与组件被商机详情页的上传解析预览复用**（`QuotationParsePreviewModal`，见 `opportunities/detail.md`）——商机上传报价单时弹预览窗、在窗内调规则即改此处的全局规则。

> 2026-09-22 深夜定调（end_mode 退役）：区域收口只剩一条法则——**配了结束关键词→首个命中行（不越过下一区域起点），没配→下一区域起点/表尾**。end_mode 曾是隐藏字段（配了关键词却 mode=eof 不生效 → 质保段整段吞进 KP），当天先把它补成弹窗下拉，再定调「暴露可见性不如消灭这个允许配了不用的开关」，同日连 UI、引擎分支、repo 契约一并退役（DB 列 NOT NULL 惰性保留，代码不再读写）。

> 2026-09-22 修复：L6/KP 区域边界相邻且 skip_header_rows 耗尽区域时，解析器曾把区域尾部静默扩到表尾（L6 行混入全部 KP 行与备注行、真身 L6 行反被 skip 丢掉）。现区域耗尽即为空；KP 区域 end_keywords 配「Warranty,售后服务,增值服务」双模板收口（LLW/ZSA 常用模板质保段头是英文 Warranty，NKY 模板是中文售后服务——只配一族会把另一族的质保段吞进 KP）；列规则加 header_keywords 表头定位（规格型号/产品描述/数量/单价（元））兼容同工作簿内两种列偏移布局。

> 2026-09-26 第三方审计修复（P0×2 + P1 全量）：① `region_ends` 补丁作用在首个区域时 UnboundLocalError、`apply_patches` 用未装规则的裸解析器定位边界（带跳过行/收口的存回模板全 500）——两处崩溃已修；② 短拉丁关键词（L6/KP）子串轮会命中 ML600 之类型号劫持区域起点，已跳过短词；③ 数值格整值化（2 不再变 "2.0"）；④ 非法列字母（"1A"）的会话绑定被忽略；⑤ 关键词扫描窗口 10→30 行；⑥ `apply_patches` 收口翻译曾写**前一区域**的 end_keywords（差一错误），改写被收口区域自身；⑦ 存回译文新增**核验门**（`verify`：新规则在干净引擎上重解析 vs 用户确认视图，不等价时逐条报 diff）；⑧ 补丁/另存写回后期望快照带 `_provenance` 溯源（generator / user_confirmed），规则自证基线自检失败时首条注明；⑨ 模板指纹 tag 撞车返回 409；⑩ 散行排除词与保留行同值时不写入（防误杀）并如实报核验不等价。

> 2026-09-27 实测修复（ZHY 客户表被误路由）→ 同日匹配链整体退役：兜底模板原本不参与打分，而方案部模板的区域词（L6/Keypats/Warranty）全是客户表通用词汇——客户表凭这些词独占鳌头被路由到方案部模板，用其 skip/列规则解析客户版式全错。先修为「兜底参与同表打分竞争」，随后定调**打分/指纹这套「猜文件是谁」的机制本身就不该有**：匹配引擎 `parse_template_matcher.py` 与其测试整文件删除，标准文件不再埋 docProps 指纹，`fingerprint_tag` 字段停止读写（DB 列惰性保留）；数值格浮点尾差同步收敛（24520.999999999996 → 24521）。当日晚再定调**「下拉记住上次选择」也退役，改为使用位置绑定**（`rules.parse_scope_bindings`）：下拉记忆版踩到真实事故——方案部模板被删后浏览器 localStorage 仍记住其 id，带回死 id 且手动路径不验证存在性 → 解析静默 0 行（用户实测「L6和KP啥都解析不出来」的根因）。终版裁决链 `ParseTemplateService.resolve_scope_template`：显式 template_id（设置页预览）> scope 绑定 > 通用兜底，死 id/已停用/未绑定全落兜底；`另存新模板` 不再就地切换，改为指引到本页换绑（保「预览=确认」）。同日再修两处解析正确性：① ZHY 表 KP 区表头残留行（标记行独占一行且 A 列带序号，`2|Keypats|Component Description|单价|总价` 被当数据吞入）——通用模板 kp 区域 `exclude_keywords` 补 `Component Description,单价,总价,Keypats`（排除词按**已提取字段值整词**命中，备份 `backend/_backups/parse_regions_backup_20260927_pre_zhy_header_fix.json`）；② `_find_region_row` 第三轮模糊匹配自引入起就是死代码——`_edit_distance` 的替换项误用当前行左邻 `curr_row[j]`（应为上一行对角 `prev_row[j]`），任意两词距离被虚高到≈词长，'Keypats'↔'Keyparts' 算出 8，模糊轮从未命中过；修正后距离=1 正常命中（此前全靠 DB 关键词手工收录错拼在撑）。

> 2026-09-26 边界收口：上传链路全面只收 `.xlsx`（旧版 `.xls` 提示先另存为 `.xlsx`，`pd.read_excel` 本就缺 xlrd 支撑）；`/api/rules` 整组加鉴权——读接口（含报价弹窗运行时 GET/预览/补丁写回）登录即可，设置页结构写操作（模板 CRUD·克隆·标准文件·自检·区域/字段规则·KP 映射·精度·导出分类）需 `page.settings.excel` 权限（与前端路由 perm 一致；`AUTH_ENABLED=false` 灰度期恒放行）。前端 `useExcelParser` / `store/settings` 从裸 axios 切到带 Bearer 拦截的实例。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/excel-parser` | `views/ExcelParser.vue` |

## API 端点

### 解析模板（2026-09-26 新增）
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/rules/parse-templates` | 模板列表（含自检状态/版本） |
| POST | `/api/rules/parse-templates` | 新建模板 |
| PUT / DELETE | `/api/rules/parse-templates/{id}` | 改名/备注/启停；删除（兜底 403） |
| POST | `/api/rules/parse-templates/{id}/clone` | 克隆建新（区域带 `_tpl{新id}` 后缀键） |
| POST | `/api/rules/parse-templates/{id}/std-file/generate` | 重新生成标准文件（版本+1，自检转 stale） |
| POST | `/api/rules/parse-templates/{id}/std-file/replace` | 上传替换标准文件（校验落盘，版本+1；样例/期望快照不动） |
| GET | `/api/rules/parse-templates/{id}/std-file/download?force=` | 下载标准文件；自检 failed/stale 且未 force 时 409 |
| POST | `/api/rules/parse-templates/{id}/selfcheck/run` | 跑自检（样例 vs 期望快照逐格回归） |
| GET | `/api/rules/parse-scope-bindings` | 使用位置绑定列表（登录即可读，上传弹窗显示当前模板用） |
| PUT | `/api/rules/parse-scope-bindings/{scope_key}` | 配置某使用位置绑定哪个模板（body `{template_id}`；需 `page.settings.excel`） |

> **鉴权**：`/api/rules` 整组需登录；上表所有写操作（POST/PUT/DELETE）及标准文件下载需 `page.settings.excel` 权限。GET / 预览 / patches / save-as 登录即可（报价弹窗运行时使用）。

区域/字段规则端点同下，均支持 `?template_id=` 过滤；preview 端点支持 Form 字段 `template_id`（设置页预览，显式指定）或 `scope`（上传弹窗，按使用位置绑定裁决）+ `parse_overrides`（JSON：skip_rows / col_binds / region_ends，仅本次生效不落库）；商机的成本表上传端点不再收 template_id，模板一律按 `cost_sheet_upload` 绑定裁决。

### 解析区域
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/rules/parse-regions` | — | 获取所有解析区域配置 |
| POST | `/api/rules/parse-regions` | — | 批量保存解析区域 |
| PUT | `/api/rules/parse-regions/{region_id}` | — | 更新单个解析区域 |
| DELETE | `/api/rules/parse-regions/{region_id}` | — | 删除解析区域 |

### 字段规则
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/rules/parse-field-rules` | — | 获取所有字段解析规则 |
| POST | `/api/rules/parse-field-rules` | — | 批量保存字段规则 |
| PUT | `/api/rules/parse-field-rules/{rule_id}` | — | 更新单个字段规则 |
| DELETE | `/api/rules/parse-field-rules/{rule_id}` | — | 删除字段规则 |

### 预览与测试
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/rules/excel-parser-preview` | — | 使用新 ExcelParser 引擎预览解析 |
| POST | `/api/rules/parse-preview` | — | 解析 Excel 用于热力图预览 |

### 业务字段
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/admin/business-fields` | — | 列出所有业务字段 |
| POST | `/api/admin/business-fields` | — | 新增业务字段 |
| PUT | `/api/admin/business-fields/{field_key}` | — | 更新业务字段 |
| DELETE | `/api/admin/business-fields/{field_key}` | — | 删除业务字段 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `rules` | `parse_templates` | 解析模板（名称/启停/自检状态/版本/样例·标准文件键；`fingerprint_tag` 列已退役惰性保留） |
| `rules` | `parse_scope_bindings` | 使用位置绑定（scope_key→template_id；scope 注册表在后端 `PARSE_SCOPES`，startup 种子缺位补绑通用） |
| `rules` | `parse_regions` | 解析区域定义（带 template_id） |
| `rules` | `parse_field_rules` | 字段解析规则（带 template_id） |
| `rules` | `business_fields` | 业务字段定义（全局） |
| `rules` | `dynamic_source_fields` | 动态数据源字段 |
| `rules` | `field_references` | 字段引用关系 |
| `rules` | `field_audit_logs` | 字段审计日志 |
| `rules` | `field_usage_stats` | 字段使用统计 |

## 关键组件

- `useExcelParser.ts` — 解析逻辑单例 composable（模板/规则加载 / 文件预览带 template_id+overrides / 模板 CRUD·标准文件·自检·补丁写回）
- `ParseHeatmapPreview.vue` — 热力图预览（取值着色 + 来源 tooltip，纯展示，设置页用）
- `ParseInteractiveGrid.vue` — 交互网格（弹窗 v3 用：行号列拖选/列头点选绑定/点格档案）
- `ParseRulesEditor.vue` — 区域边界 + 字段取值列 + KP 分类映射编辑器（含编辑弹窗）
- `ParseResultPanel.vue` — 解析结果面板（共享）：静态字段+动态区域带溯源，设置页右栏与商机上传弹窗右栏复用（解析追踪时间线只归设置页）
- `QuotationParsePreviewModal.vue` — 商机上传解析弹窗（见 `opportunities/detail.md`）。布局：左=格子档案+字段映射（列绑定），中=交互网格，右=解析结果（复用 `ParseResultPanel`）。弹窗内修正只以 session overrides 对本文件生效——「存回模板/另存新模板」已整体退役（2026-09-27 用户定调：上传页不承担规则维护，规则只归设置页）

## 注意事项

- 解析规则修改后需要重新测试预览
- 业务字段定义影响整个系统（报价单、导出模板等）
- 解析引擎支持多种模式：cell_ref（单元格引用）、column_search（列搜索）、formula（公式）
