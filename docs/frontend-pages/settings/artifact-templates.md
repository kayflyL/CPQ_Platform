# 产出物模板中心（ArtifactTemplateCenter）

> 最后更新：2026-10-03（**AI 生成重做：依据=契约全文（含每章内容要求 requires），六步过程可见**——此前生成只喂章节标题+资产菜单让 AI 挑，契约外口径（全量 KPI 卡）因此混入，已推翻。现流程：读契约 → 逐章解析内容要求 → 匹配资产货架（每图带出处"满足第 N 章〔要求短语〕"）→ 编排骨架 → 确定性校验（章节覆盖/资产存在/无契约外口径/每章图表≤2/自动配图兜底）→ 进画布；后端一次调用返回 trace+blocks，前端面板逐步揭晓。**KPI 窗口化**：四原子收敛为 总商机数/总配置数 两卡、全部跟随数据范围（原"周期新增×2"与窗口化总量重复退场）。⚠️ /contracts 须注册在 /{template_id} 之前。三层权威模型见下）

> 上一轮（同日第二批）：①**契约=种子**：workflow agent 节点目标层文档卡（kind=document+sections）是模板生成的一次性输入；②**模板=用户所有**：生成后自包含（章节映射/资产/窗口全在 blocks），用户可改任何字段，**渲染只看模板**，契约漂移不自动传播；③**对账=显式动作**：「按契约校验」补缺用契约值、失效 key 只报不删。曾提的「绑定层外移/输出节点绑定视图/AI 双产物」方案**作废**——模板自包含+运行时零判断才是终态。统计窗口/资产/指标构成编辑分区**保留**（模板=规格，含取数配置；默认跟随数据范围，固定窗口仅用于结构语义如半年章 183 天，勿与数据范围抢权）。同日落地：编辑器 2B 重做（画布直接编辑/统一指示条/拖拽幽灵/右栏折叠摘要面板）、heading/callout/divider/image 渲染、GET /contracts 契约聚合（**必须注册在 GET /{template_id} 之前**）、POST /reconcile 对账、POST /generate AI 生成（chat_json+_validate_repair_blocks 确定性修复，实测抓到 LLM 塞错资产）、title 块 accent 品牌色+色板。交互蓝图 `docs/执行方案/产出物编辑器通用化与AI生成模板-调研报告.md` §7.8）

## 三层权威模型（2026-10-03 定调，模板语义的最高解释）

```
契约（agent 节点目标层文档卡）     模板（自包含 · 用户所有）         运行时
章节 key/标题/数据范围 ──生成──▶ 结构+标题+章节映射+资产+窗口 ──▶ 模板 + 当期数据 → PDF
   种子（一次性输入）            可随意改，改了按模板          零 AI、零绑定、纯确定
```

- **契约=种子**：生成模板的一次性输入；生成时 AI 把契约章节标题写进模板作为回退值。契约漂移**不自动传播**——用户改过就按用户；要同步就显式点「按契约校验」（补缺用契约值、失效 key 只报）。
- **模板=用户所有**：自包含报告规格（结构/标题/章节映射/资产/窗口），渲染端只读 blocks。模板管**规格**（每期不变），workflow 管**每期变量**（当期数据范围/文字/数字）。
- **AI 自由度**：硬约束仅两类（合法性：资产存在/kind 匹配/span 合法；契约覆盖：章节不缺不并）。排版/选资产/并用几图/洞察卡——设计期 AI 全权，校验器只删不可能、不改不好看；运行时大脑在固定章节内自由填写。
- **作废声明**：绑定层外移/输出节点绑定视图/AI 双产物 {blocks,bindings} 方案作废（2026-10-03），勿再提议。

## 定位

AI 办公室管理面「产出物」tab（`AiOfficeManagement` nav `artifacts`，需 `ai.office.manage`）。工作流产出表格/Excel/PDF/PPT 的格式不再随机：**模板 = 确定性格式契约（区块序列 + 图表资产引用），AI 只填内容，渲染走确定性管线**（HTML→Playwright PDF），模板层零 AI——与「AI=唯一大脑、workflow=指引」「禁令不进黑盒代码」同一架构心智。

调研映射：PDF=jsreport 模式（HTML 模板自绘+实时数据预览+数据契约分离）；Excel=carbone 模式、PPT=PPTAgent 模式（**门控为下期**，格式 chips 置灰）。编辑交互借鉴 Notion（区块+类型菜单）/ Figma（三栏+点选同步）/ Canva（素材库标签页）。

## 两个视图

### 模板库

- 卡片网格（名称/key mono/描述/区块统计/更新时间）+ **尾卡虚线「＋ 新建」**（新增入口尾卡范式）
- 格式筛选 chips：PDF（可用）/ Excel、PPT（置灰「下期」）
- 卡片 hover 出删除（popconfirm：删除后输出节点引用回退默认渲染）

### PDF 编辑器（三栏 · 画布直接编辑，2026-10-03 2B 重做）

- **内核**：`components/artifact/useArtifactKernel.ts`——craft.js 四件套的 Vue3 镜像（BLOCK_DEFS 类型注册表≈resolver / blocks 扁平树 / 结构动作 / 快照撤销栈）；blocks JSON 与渲染契约逐字段兼容，**存量模板无损往返**。画布上的图表/KPI/正文为客户端样例渲染（`renderBlockHtml`，house 视觉镜像），真实取数渲染看「真实数据预览」。
- **顶栏**：返回 / 模板名 / key（编辑态锁定）/ 页数·区块数 chips / 撤销重做（Ctrl+Z·Y）/ 真实数据预览（抽屉，后端渲染真库数据）/ 导出样例 PDF / 保存
- **左栏组件库**：分组（基础/数据槽/媒体/版式 + 图表资产组）——拖到画布任意位置（插入指示线，0.15s 缓动）或点击追加；绿底=数据槽
- **中栏画布**：A4 纸（794px）流式 12 列栅格；**hover/选中共用一条品牌色指示条**（组件名+宽度切换+复制+上下移+删除，压块左上沿，随悬停移动——craft.js RenderNode 同款）；**整块可拖拽排序**（拖拽幽灵=块 DOM 克隆——createShadow 同款）；**右缘手柄拖宽**吸附 4/6/8/12 栅格；标题/文案 **contenteditable 直接改字**（blur 提交）；超一页自动画页界参考线（估算值，paged.js 真分页待下期）；Ctrl+D 复制 / Del 删除
- **右栏单面板**（折叠分区+收起态实时摘要，无 tab——craft.js ToolbarSection 同款）：选中态=版式（宽度 seg）/ 内容（title 抬头四字段+Logo 上传、heading 文本、callout 色调+标题+正文、literal 文案）/ 绑定（text 槽 source=answer|payload + 章节键）/ 资产（kpi/chart/table 下拉）/ 指标构成（kpi 勾选+改名+排序）/ 统计窗口（跟随数据范围 | 固定 N 天=params.days）/ 高度（chart）；未选中态=页面设置（首个 title 块的品牌/副题/Logo）+ 数据契约（三色语义，点击定位区块）+ 渲染配方说明；图层折叠区常驻底部
- **真实数据预览**：抽屉内 iframe srcdoc（后端 `POST /preview`，真库取数+echarts SSR+interactive 占位框）；样例 PDF 走 `render-sample-pdf` blob 下载

## 区块 schema（blocks 不透明 blob，后端只校验 type）

所有非 title 区块支持 `span`：12 列栅格宽（4/6/8/12，缺省整行），同宽区块自动并排（body 为 CSS grid，`grid-column: span var(--span)`）。

| type | 字段 | 说明 |
|------|------|------ |
| `title` | `title`/`subtitle`/`brand_name`/`brand_tag`（钉固定文案，**留空回落 meta**）/`logo_url`（上传抬头公司 Logo，`POST /logo` 端点返回 URL） | 抬头+标题块（无封面）：正文标题与 PDF 页眉同源（`_effective_head_texts`）；Logo 渲染时读盘转 data URI 内嵌（预览 iframe 与 Playwright 通用），读盘失败自动跳过不挡报告 |
| `text` | `source`=`answer`\|`payload`\|`literal`, `key`, `text`, `title` | answer=整段 markdown 答复；payload=章节槽（漏槽隐藏）；literal=模板自写静态文案（放免责声明/固定说明） |
| `heading` | `title` | 独立编号小节题（只出标题不接正文，占 sec_no 编号流——2026-10-03 新增） |
| `callout` | `tone`=`blue`\|`green`\|`amber`, `co_title`, `text`（markdown 子集） | 提示卡（整圈细边框+图标，无左边色条——设计铁律）；洞察/口径/风险（2026-10-03 新增） |
| `divider` | — | 分割线（2026-10-03 新增） |
| `image` | `src` | 图片（上传端点产物路径或外链；2026-10-03 新增） |
| `fields` | `key` | 结构化字段表（payload.{key} 字典扁平化两列表；需求分析结构化流用） |
| `kpi` | `asset`, `metrics`=[{key,label}], `params.days` | 指标卡网格；metrics=勾选目录原子+显示名覆盖，数组序=渲染序，缺省=全目录 |
| `chart` | `asset`, `height`, `span`, `params.days` | echarts 图（option 服务端构建） |
| `table` | `asset`, `span`, `params.days` | 明细表 |

kpi/chart/table 的 `params.days` 在编辑器里由「统计窗口」分区表达：**跟随数据范围**（params 不写 days，渲染时 setdefault 推入）或**固定 N 天**（显式 params.days，如半年章节 183）。

## 图表资产注册表（backend/app/services/chart_assets.py）

资产 = 取数查询 + option 构建器，**后端单一权威源**；编辑器预览与 PDF SSR 消费同一份，驾驶舱改口径报告自动跟。option 构建器镜像前端 OpportunityCharts.vue 视觉（PLAT_COLOR 色值、环形中心总数）。

P0 注册九个（覆盖商机线索页左图表栏全部四卡，含各卡副视图；口径：`status NOT IN ('ai_office','deleted')`，`_normalize_pn`/`_pct_quartiles` 直接 import 驾驶舱同一份助手）：

- `cockpit.kpi`：指标原子目录=商机线索页右上四卡同源（总商机数/总配置数/周期新增商机/周期新增配置；配置数=每商机当前版本 config_count，同 opp_stats._window_kpis 口径；周期新增=近 days 天，days 跟随报告数据范围）；kpi 区块按 `blk.metrics` 勾选/改名/排序（`metrics` 随资产元数据下发编辑器）
- `cockpit.trend`：近 8 周按天柱状+分平台折线（params.days 可调）
- `cockpit.dist`：平台占比环形
- `cockpit.platform_monthly`：月度×平台明细表（月份 / 各平台新增数按累计量降序列 / 当月合计；rows+columns+keys 显式列序），半年趋势章节专用
- `cockpit.model_trend`：机型(PN)报价次数矩形树图，Top8+其他（quotations.config_server_models，params.days 可调）
- `cockpit.chassis_dist`：机箱形态玫瑰图（slot chassis_form 多值拆分，params.days 可调）
- `cockpit.sales_rank`：销售商机数 Top5 横条+其他人聚合（params.top_n 可调）
- `cockpit.profit`：机型利润率箱线+散点（样本≥4 成箱，不限周期——样本本就稀疏）
- `cockpit.top_opps`：最新 5 条商机明细（params.limit 可调）

驾驶舱前端 option 代码暂未反向接入 registry（P1 统一）。

每资产带 `params` schema（key/label/default/min/max/step/unit），`resolve_asset_data` 按 schema 通用解析并 clamp（右栏参数区同源渲染）：trend/dist=days(56)、model_trend=days(56,max365)、chassis_dist=days(56)、top_opps=limit(5)、sales_rank=top_n(5)；kpi/profit 无参数。

## 渲染管线（backend/app/services/artifact_render.py）

`render_report_html(blocks, payload, theme, interactive)`：blocks+payload → 完整 HTML。文本块复用 `report_pdf._parse_markdown_blocks` 的 markdown 子集（标题/列表/表格/加粗/分隔线）。图表 option 序列化进 `window.__CHARTS__`，echarts 加载后逐块 init/setOption 置 `__CHARTS_DONE__`（图表块 `height` 字段以每块内联 style 生效）。

- **主题（theme，单一 house，历史取值回落）**：「规格书同源」主题——视觉 token 镜像导出模板 SpecSheet（`DEFAULT_SPEC_STYLES`）：品牌蓝 `#1668C0` 抬头细线（左品牌名/右统计区间）、标题块左 4px 蓝杠、蓝色小节题+底部发丝线、KPI 浅灰圆角卡（`#F7F8FA`+8px）+蓝色大数字、表头灰底大写字距+行发丝线 `#EEF0F3`。**无封面**直接进正文（用户定调封面没用）；带 title 的区块自动编号（01/02…）。曾做六套候选（business/github/softened/editorial/consulting/minimal）全被否决——「换汤不换药」教训：版式差异必须结构级，且自创风格不如贴自家导出模板。
- **布局栅格、抬头 Logo 与数据范围口径**：body 为 12 列 CSS grid，区块 `span` 4/6/8/12 缺省整行、同宽自动并排（`sec_open` 注入 `--span`）——**编号大标题区块应独占整行**，图表块才用半行并排；抬头左侧品牌区支持 Logo（`.rpt-brand`，镜像 SpecSheet `.ss-brand` 左图右名）。**数据范围口径只补缺省**：`asset_params`（运行时 range_days）对 kpi/chart/table 块 `params.setdefault`——区块显式 params 优先（章节固定窗口如半年图表 days=183 不被顶掉），留空才跟随报告数据范围（概览双图不写 days=跟随）；kpi 块按 `metrics` 过滤/改名，**缺省=全目录四项（线索页右上四卡同源）**；编辑器预览（interactive）对空 payload 槽位画占位框（章节标题与编号照排——模板骨架在编辑器可见，运行时只往槽里填数），PDF 恒隐藏漏节。
- **interactive（仅编辑器预览）**：区块标 `data-atc-idx`（=blocks 下标，与左栏 selectedIdx 对齐）+ 注入 postMessage 协议脚本（atc-select/atc-highlight/atc-height）+ 选中高亮/分页参考线/预览态页边距。PDF 路径恒 False。

`render_report_pdf`：echarts.min.js 从磁盘内联（`app/static/vendor/`，来源 frontend node_modules 拷贝）→ Playwright chromium `set_content` → `wait_for_function(__CHARTS_DONE__)` → `page.pdf(A4, print_background, display_header_footer=True)`：**页眉**=报告名+日期+细线，**页脚**=「CPQ Platform · 内部资料」+「第X页/共Y页」（chromium header/footer template 不认外链 CSS，字号必须显式 px）；页边距走 pdf margin（top 20mm/bottom 16mm/左右 18mm）。**两个已修病灶**：①主题 CSS 里 `@page { margin: 0 }` 会顶掉 page.pdf 的 margin 参数（chromium 中 CSS @page 优先）→ 全出血贴边打印，已删 @page 规则；②echarts setOption 默认带动画，`__CHARTS_DONE__` 同步置位后 page.pdf 抢在动画完成前快照 → 折线只画首段/环形图环体缺失，已在图表 init 时强制 `animation=false`。asyncio.Semaphore(1) 串行锁。**playwright 不可用抛 RuntimeError，调用方回退 legacy reportlab，不挡交付**。

## 运行时接线（skill_node_runtime.py / skill_turn_engine.py）

**内容与形式分家**（2026-09-29 定调，原型 `_prototypes/output-artifact-selector.html`）：

- **内容唯一权威 = 目标层文档卡**（agent 节点 `target.artifacts[0]`，须带非空 `sections` 才算报告文档卡——input 节点的「需求原文」document 插头没有 sections，前后端同款过滤，防误认）：报告名 / 章节 / 数据范围。
- **呈现方式唯一权威 = 输出节点 `config.render`**（`{enabled, format, template_key}`，仅选 PDF 才写；无 render = 随流程呈现不出文件）。目标层弹窗已回纯内容，存量 render 由迁移脚本 `scripts/fix_output_render_20260929.py`（幂等，--apply）反向搬家到输出节点。

**输出节点抽屉「呈现方式」四卡**（ReasoningNodeDrawer）：随流程呈现（默认，零配置不出文件，nativeDesc 按 output_kind 给「落库后在哪儿看」文案）/ PDF（选中展开模板下拉「默认排版（系统排版引擎）」+ 数据对接提示）/ Excel（置灰下期，副文案「复用『设置·导出模板』商务导出管线」）/ PPT（置灰下期）。输出节点即使自带产物插头（如需求分析的方案配置卡 table）也走输出表单分支，抽屉只呈现交接表单。

**对接提示三态**（ok 绿 / warn 黄不拦截 / info 灰）：有模板且流有报告文档卡 → 章节 key × 模板文本槽对比（7/7 绿，「模板未对接章节：X」黄）；无文档卡的结构化场景（ext+plans）→「落库数据自动排版：需求单字段（ext）→ 字段表，BOM 配置行（plans）→ 明细表（Catalogue / Configuration Description / Quantity）」绿；报告模板配给结构化流 → 黄「承接不了结构化输出数据」。无模板时 → 动态 info（按文档卡前两章节标题示例「（一、X / 二、Y …）」）。

三桥（skill_turn_engine `_deliver` 组装 `ctx["document_target"]` = 文档卡内容 + 输出节点 render 合并，`_render_file_artifacts` 消费）：

- **章节 → 槽位**：`split_answer_sections` 按「一、{title}」契约头把 AI 整段 answer 确定性拆段进 render_payload；模板 text 块 `source=payload key={章节key}` 各取各段，漏节槽空该块自动隐藏
- **数据范围 → 封面**：`_report_window` 单源计算窗口文本（首行 AI 复述的「数据范围：…」不进任何槽）
- **数据范围 → 图表**：`range_days` → `asset_params`（含头含尾 N 天 → N-1 对齐资产桶语义 start=today-days），**只补区块未显式指定的 params**（显式=章节固定窗口），按资产 schema clamp，不认 days 的资产（kpi/profit）自动忽略

两条**内容**路线：① answer 文本（章节拆段进文本槽，无模板时 legacy reportlab 兜底）；② 结构化 payload（无文档卡的流，如需求分析 bom_scheme_draft）：`_render_structured_default` 按值形状自动组 blocks——dict → `fields` 区块（payload 嵌套扁平化两列表）、list[dict] → `table` 区块 `source=payload`（行键并集动态列）；`_CELL_LABELS` 镜像 compose 列契约（part_category→Catalogue / catalogue→Configuration Description / qty→Quantity），ext 字段键不发明中文标签。渲染闸门：`render.enabled is not True`（必须显式选 PDF）或无内容 → 不出文件。`files[]` 产物留痕 `template_key`（默认 `default_layout`）+ `rendered_by=output_node`。

## API（backend/app/api/artifact_templates.py）

| 端点 | 权限 | 说明 |
|------|------|------|
| `GET /api/artifact-templates` | 登录 | 列表（含 blocks） |
| `GET …/chart-assets` | 登录 | 资产元数据 |
| `GET …/echarts.js` | 公开 | vendor echarts（iframe 预览用） |
| `POST …/preview` | 登录 | blocks → 预览 HTML（真实库数据，interactive 模式含点击反选/分页线协议） |
| `POST …/render-sample-pdf` | 登录 | blocks → 样例 PDF |
| `POST …/logo` | 登录 | 上传抬头 Logo（png/jpg/svg ≤2MB，uuid 重命名存 `app/static/artifact_logos/`）→ `{url}` |
| `GET …/logo/{filename}` | 公开 | Logo 读取（编辑器 iframe 预览引用，与 echarts.js 同款理由；文件名白名单防穿越） |
| `POST/PUT/DELETE …` | `ai.office.manage` | CRUD（key 唯一 409；format 仅 pdf） |

表：`rules.artifact_template`（ORM 注册 metadata，startup create_all 建表；空表守卫种子 `weekly_opportunity_report` 商机经营周报 6 区块模板）。前端客户端 [artifactTemplates.ts](../../../frontend/src/api/artifactTemplates.ts)。

## 验证记录

- 2026-09-26（P0）：后端导入自检全过；TestClient 建表+种子+list/chart-assets/preview/echarts.js 全 200；资产取数连真库（active 182 条，排除 ai_office 316/deleted）；`cd frontend && npm run build` 通过
- 2026-09-27（右栏可交互化+主题）：npm build ✓；直调断言（data-atc-idx 编号对齐/postMessage 协议/图表高度内联/章节编号/PDF 模式零 interactive 残留）✓；TestClient preview 200 含协议脚本 ✓；浏览器端到端（backend-verify 8010 + frontend-verify 5174，Pinia 直改 auth 过守卫）：参数 days=30 写入 block.params、预览刷新（seq 递增）、iframe 点击 data-atc-idx=4 → selectedIdx=4+左栏选中+预览内高亮、契约行点击 → selectedIdx=2+参数区可见、高度自适应 1494px+1 条分页线 全部通过
- 2026-09-29（架构收敛）：后端直调断言全过（拆段器七节全中/漏节容错/range_days 桶对齐/asset_params 覆盖/封面口径单源）；端到端 `_render_file_artifacts` 出 PDF（pypdf 断言：封面 2026.08.31~2026.09.29 近30天、七节槽位全落、3 图表 XObject、旧「近 8 周」「AI 分析结论」消失）；`cd frontend && npm run build` 通过；浏览器端到端（backend-verify 8010 + frontend-verify，管理面→工作流→趋势分析→agent 目标层呈现区「章节与模板文本槽全部对接」→输出节点只读卡「交付时将生成 PDF · 商机趋势分析报告（模板：商机趋势报告）」）通过
- 2026-09-29（呈现方式归输出节点）：后端三场景断言（趋势模板 PDF `rendered_by=output_node` / 无 render 不出文件 / 结构化默认排版 87418 bytes `template_key=default_layout`）+ pypdf 内容断言（方案配置卡/需求单字段/BOM 配置行/customer_name/Catalogue/Configuration Description/Quantity/Intel 6430/2U 机箱）全过；迁移脚本 `fix_output_render_20260929.py --apply`（flow 126 迁移、flow 125 幂等）；`cd frontend && npm run build` 通过；浏览器逐态自查与原型 `_prototypes/output-artifact-selector.html` 一致（趋势流四卡/PDF 选中态/7/7 绿/动态 info/切原生收起 + 需求分析流 nativeDesc/默认排版 ok/报告模板 warn + agent 目标层呈现区已删 + 保存回写 DB：`output.render` 落库、agent 卡无残留、「已保存（下次推理生效）」）
- 踩坑：f-string 模板变量注入 JS 片段必须自带 `<script>` 包裹——裸 JS 文本会被浏览器当 body 文本渲染（预览里出现一段代码文字、协议静默失效，症状=srcdoc 属性有而 iframe DOM 无第三段 script）
