# AI 设置 (AiSettings)

> 最后更新：2026-10-15（工具分类标签「数据查询」→「数据与案例」）

## 功能概述

配置方案助手的行为、数据查询与模型连接，所有配置项存储在 `system_config` 表，拒绝硬编码。

> 「趋势洞察」已下沉为方案助手的「📈 分析本期趋势」快捷指令（商机线索页助手面板内一键触发）：业务数据不再由前端注入，方案助手通过后端内置数据工具 `query_cpq_data` 按需查询（本周/上周/本月/近半年/自定义区间/重点商机），**提示词模板可在此页「快捷指令 · 趋势分析」tab 配置**（存 `ai_trend_analysis`，反对硬编码）。详见 [方案助手文档](../assistant/floating-assistant.md)。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/ai-settings` | `views/settings/AiSettings.vue` |

## 页面结构

页面使用 Tabs 切换四个配置模块（方案助手 / 快捷指令 · 趋势分析 / 模型与连接 / 会话记录）：

---

## 方案助手 (Assistant)

### 基础设置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| 自动上下文 | 打开时自动注入当前页面数据 | 开启 |
| 回复风格 | 简洁 / 详细 | 详细 |

### 上下文来源

选择哪些页面可以提供上下文给 AI：

| Provider | 默认名称 | 说明 |
|----------|----------|------|
| `quote` | 报价工作台 | `/workspace` 页面 |
| `opportunity` | 商机详情 | `/opportunities/:id` 页面 |
| `opportunity-list` | 商机线索 | `/opportunities` 页面 |

每个 Provider 可配置：
- **启用/禁用** — 是否在该页面提供上下文
- **显示名称** — 自定义标签
- **详细度** — 简要 / 详细

---

## AI 工具（全系统 LLM 工具目录）

工具文案分**三层**（2026-09-15 改造）：**人类展示层**（中文名 display_name / 一句话 one_liner / 人话详解 description）、**模型契约**（model_brief，即每回合注入大脑的 FC 描述）、**DB 权威层**（`rules.agent_tool_text`，**唯一权威源**：启动时种子回填缺失行（`seed_defaults`，ON CONFLICT DO NOTHING 不碰已有编辑），四字段 NOT NULL——清空某字段=写回种子值，不存在「删行」）。代码里的文案（`agent_tool_display.py` + `agent_tool_specs._TOOL_SPECS` summary）只是**迁移种子与 DB 故障降级**，运行时不参与合并。卡片面只显示人类层（中文名+一句话）；点卡开详情弹窗，分区块看 详解（给人看的）/ 模型契约（标注「编辑会改变 AI 行为」）/ 参数表（说明为模型契约原文）/ 被引用（弹窗内有「文案已自定义」橙色标签，自定义判定=与种子值比对）。

**文案可编辑（仅本目录页）**：详情弹窗「编辑文案」→ 改四字段保存（`PUT /api/assistant/tools/{name}/text`，admin 权限）；「恢复默认」= 把种子值整行写回（`DELETE .../text`，同样落 DB 不删行）。model_brief（模型契约）保存口跑**宪法 lint**（`constitution_lint.PROSE_MARKERS`，与 `tests/test_constitution.py` 共用同一词表）：命中祈使/流程词直接 400 拒——「怎么做」类规则属左栏任务规则，不进工具文案。改完的 model_brief 经 `build_tool_registry` 读取，下一回合即生效（大脑真实吃到）。节点抽屉里的工具卡**只读**（只挂载/移除），编辑入口只在目录页。本页「方案助手」tab 底部 / AI 办公室管理页「工具目录」tab 均为同一卡片目录（按类别分组，与节点抽屉工具层同一张卡）。每张卡带「被引用」徽标 = 哪些节点挂了该工具（聚合自活跃流生效工具集，与运行时同口径：默认契约+增量+机制保底）。数据源 `GET /api/assistant/tools`（返回 tools + usage）。

| 工具 | 分类 | 用途 | 默认启用 |
|------|------|------|:---:|
| `fill_requirement` | 选型决策 | 线索登记表填槽（登记协议） | ✅ |
| `choose_model` | 选型决策 | 锁定机型（落锁协议，池外拒绝） | ✅ |
| `query_parts` | 选型决策 | 配件检索（类目+规格 AND 过滤+翻页） | ✅ |
| `inspect_parts` | 选型决策 | 配件钻取/定向搜索（part/row/category/grep） | ✅ |
| `select_parts` | 选型决策 | 配件行落地（池内核对+数量上限闸） | ✅ |
| `ask_user` | 选型决策 | 客户决策卡（选项/缺口反问） | ✅ |
| `catalog_search` | 选型决策 | 目录接地检索（在售机型/基准配置） | ✅ |
| `search_cases` | 数据与案例 | 相似案例检索（只读） | 需勾选 |
| `query_data` | 数据与案例 | 只读原语查白名单表（工具即权限） | 需勾选 |

数据工具 `query_cpq_data` 参数：

| 参数 | 必填 | 取值 |
|------|:---:|------|
| `period` | ✅ | `week` / `last_week` / `month` / `half_year` / `year` / `custom` |
| `focus` | — | `all` / `kpi` / `platform` / `chassis` / `rank` / `trend` / `highlights`（默认 `all`） |
| `start` / `end` | `period=custom` | 自定义区间 `YYYY-MM-DD` |
| `limit` | `focus=highlights` | 重点商机条数（默认取「趋势分析」tab 的 `highlight_count`） |

> `query_cpq_data` 默认不进推理流节点全集（`default_enabled=False`），需要时由画布抽屉勾选或方案助手消费方显式启用，避免改变现有节点行为。

---

## 快捷指令 · 趋势分析 (Trend)

方案助手「📈 分析本期趋势」快捷指令的配置。业务数据由方案助手内置数据工具 `query_cpq_data` 按需查询（前端不再拼装注入），用户在此只调**提示词口径**与重点商机条数。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| 重点商机条数 | `highlight_count`（数据工具 focus=highlights 的默认条数，近半年按台数降序取 Top N） | 10 |
| 提示词模板 | `prompt_template`（引导 AI 输出 8 段结构化报告；归因须标注「推测」） | 见种子 |

> 默认 prompt 引导 AI 按周/月/半年趋势 / 平台格局 / 机箱形态 / TOP5 / 近期重点商机 / 关键洞察 分节输出；未提供的定性数据（如具体成交价）不允许编造，仅当 `lost_reason` 有值时摘要价格反馈。

---

## 模型与连接

兼容面 = **凡 OpenAI 兼容端点或 Anthropic 协议端点皆可用**（四条 LLM 链路按 `upstream_format` 协议分流，见 `llm_client._is_anthropic_upstream`）。贴入端点后自动识别协议（含 `/anthropic` → Anthropic；含 `/v1`·`/compatible-mode`·`/paas/v` → OpenAI），也可在「上游格式」手动改选。本页只放**连接参数与模型行为选择**（端点/密钥/模型/协议/温度/最大 Tokens/思考模式）；「这个模型能什么」看「模型能力档案」tab。

### LLM 配置

| 配置项 | 说明 | 配置优先级 |
|--------|------|------------|
| API 端点 | `base_url`（贴入后自动识别协议：含 `/anthropic` → Anthropic，含 `/v1`·`/compatible-mode`·`/paas/v` → OpenAI） | system_config > .env |
| API Key | `api_key`（write-only：读接口只回 `****尾4位`，回传掩码=保留原值，清空保存=改用 .env） | system_config > .env |
| 上游格式 | `upstream_format`：OpenAI Chat Completions / Anthropic Messages，**全部 LLM 链路（对话/JSON/流式/工具）的协议总闸** | system_config > .env |
| 模型 | `model`（可输入或从「拉取模型列表」下拉选 id） | system_config > .env |
| 温度 | `temperature` (0-2，低更稳准/高越发散) | 0.7 |
| 最大 Tokens | `max_tokens`（reasoning 模型如 step-3.x 的思考也占此预算，建议 ≥ 8000） | 8000 |
| 思考模式 | `thinking` 单选：跟随模型（不传该参数）/ 关闭（`{"type":"disabled"}`）/ 开启（`{"type":"enabled","budget_tokens":N}`，N≥1024）。**仅 Anthropic 协议端点生效**（anthropic_channel 透传；OpenAI 协议端点忽略）。2026-09-14 实测 glm-5.3-flash 在 z.ai `/api/anthropic` **默认开思考**——每个工具轮先吐 5k~20k 字符思考流（40~131s/轮），选「关闭」后恢复常速。开启时温度按 Anthropic 规范要求忽略 | 不传（跟随模型） |

> System Prompt 已迁至「方案助手」tab 的「聊天 System Prompt」（`ai_assistant_config.chat_system_prompt`），不再属于模型连接参数。

### 配置优先级

```
system_config.llm_config > .env 环境变量 > 默认值
```

### 模型能力档案（2026-09-15 定调：事实源=探测）

档案页只做两件事——**展示生效能力**与**端点实测**，设计定调（用户否掉过两版）：

- **档案 = 事实（只读），模型与连接 = 选择（可编辑）**。reasoning_model（会不会思考）是档案事实；`thinking` 思考模式（让不让它思考）是行为选择，两者分属两页不算重复。
- **事实源 = 探测，不是硬编码资料、不是手工修正**。曾试过「网络查的模型卡目录（价格/上下文窗口）+ 三态手工修正层」被否——厂商规格会过时、网上抄的数据不可信、手工修正层把例外当常规。探测出来什么档案就是什么。
- **能力合成链**（`get_model_capabilities`）：内置家族默认（BUILTIN_MODEL_CAPABILITIES，未探测时的保守假设）→ 协议修正（anthropic：原生工具天然可用抬 True、response_format 不存在降 False）→ **实测定论覆盖**（`probe_capabilities`）。
- **探测即生效**：`probe_model_capabilities` 结果落库（`system_config.llm_capability_probes`，键 `model@upstream_format`，含 `tested_at`/`base_url`/每项 `*_probed` 定论标记/`default_thinking` 默认开思考检测），`_get_llm_config` 每次注入匹配记录（base_url 不一致=换过端点则作废），有定论的项直接驱动生效能力。网络抖动导致的单项未定论（`*_probed=false`）不注入，保留默认——不会因一次网络错误关掉原生工具。
- 页面无任何「保存能力档案」按钮——没有手工修正层；档案不符就重新探测。
- `capabilities_override`（旧手工修正机制）已整体移除（代码+DB 键），测试锚 `test_agent_tools.test_model_supports_strict_tools_probed`。

### 实测模型清单（2026-09-15 新增 tab）

「模型能力档案」看**当前模型**一条，本 tab 横看**全系统实测过的所有模型**——含失败记录与历史端点（如换供应商前 cloudprime 中转的实测结论），只读事实、无任何编辑按钮。设计前调研过同类产品：One API/New API 渠道列表的「类型+响应时间+状态」列、LiteLLM health check（不自动轮询防烧钱，只手动探测）、OpenRouter 模型卡 capability 旗标——采纳其中「端点身份列」与「只收录实测」两条，耗时列用户拍板不要。

| 列 | 说明 |
|------|------|
| 模型 | model id；与当前 llm_config（模型@协议@端点 三对上）匹配的打「当前使用」 |
| API 端点 | base_url 原文 + 身份标签：**官方直连**（域名在内置官方表）/ **本地/内网自建**（localhost·内网 IP）/ **第三方中转/自建**（其余公网域名，cloudprime 等 new-api 系代理落这里）。域名归谁是路由元数据（稳定事实），不同于被否掉的「模型能力硬编码」 |
| 协议 | Anthropic Messages / OpenAI 兼容 |
| 原生工具 · JSON 输出 | ✅ / ❌ / ⚠️ 未定论（网络抖动，`*_probed` 定论标记） |
| 默认开思考 | 是 / 否 / 未测（GLM 默认开思考坑的档案化） |
| 结论 | 成功 / 失败（失败行淡化，tooltip 显示真实错误如 Unknown Model——「试过不行」也是事实） |
| 实测时间 | tested_at 倒序 |

- **留档键 = `model@协议@端点域名(含端口)`**：同一模型在不同端点各自留档，重测只覆盖同端点同模型那条——换端点不再冲掉历史（旧版 `model@协议` 键读取时自动迁移）。
- 只收录实测过的模型（「能力探测」按钮产生记录）；「拉取模型列表」拉到但没测过的不在此列。无 per-row 重新探测（api_key 不随记录存，只能对当前端点探测）。

### 密钥安全（2026-09-14 加固）

- `llm_config` 的所有读接口（`GET /`、`GET /{key}`、`GET /{key}/value`）一律**掩码出站**，明文只在写入时出现（write-only）；实测按钮带着掩码值时后端自动剥离该项并回落库内/.env 已配置值；
- system_config 读接口已挂登录鉴权（未登录 401），`test` / `models` / `probe` 实测面需管理员；
- AI 同事 `query_data` 白名单**硬排除** `system_config`（`data_boundary._EXCLUDED_TABLES`），即使手配白名单也拒——配置表（含密钥）永不进 LLM 上下文；
- 数据库密码 / JWT 密钥只存 `backend/.env`（.gitignore 兜底 `*.dump`/`*.pgdump`/`db_dumps/` 防备份入库），连接串零硬编码由宪法测试 `test_no_embedded_password_in_db_urls` 锚定。

### 排障工具（测试连接 / 拉取模型列表）

模型与连接 tab 提供三个排障按钮，用**表单当前值**（未保存也行，含未保存的 `upstream_format`，缺省字段回落 `llm_config` / `.env`）实测，避免再踩「模型名填了显示名 → 连不上但看不到原因」的坑。**三个按钮都按「上游格式」自动选协议**：OpenAI 兼容端点走 SDK（`{base_url}/models`、`/chat/completions`），Anthropic Messages 端点走 `{base_url}/v1/models`（`x-api-key` 头）与 `/v1/messages`；能力探测同样双协议。

| 按钮 | 行为 | 说明 |
|------|------|------|
| 拉取模型列表 | 按「上游格式」GET models 端点，列出该 key 下可用模型 id | 拉到后模型框变为可搜索下拉（a-auto-complete），也可继续手输；根治手敲模型名拼错 |
| 测试连接 | 实测一次小请求（max_tokens=8） | 成功提示模型已响应；失败直接展示 provider 真实错误（404 / 401 / 超时 / Unknown Model 等），不再被占位文案吞掉 |
| 能力探测 | 实测 JSON 输出 / 原生 tools 支持情况 | **两种协议都支持**：OpenAI 兼容走 SDK（JSON mode + tools）；Anthropic 走 `{base}/v1/messages` 真发一次 tool_use 请求 + 提示词 JSON 往返（glm 等 reasoning 模型给 1024 预算防思考耗尽假阴性）。探测通过 = 四条链路的工具/JSON 通道确实可用 |

> 三个按钮都用表单当前值（含未保存的 `upstream_format`），缺省字段回落 `llm_config` / `.env`。

> 历史坑：①模型字段曾只能手填，用户易把控制台显示名当 id，导致 404 `model_invalid`（现已可拉列表+透传真实错误）；②2026-09-14 换智谱 z.ai 官方端点（`https://api.z.ai/api/anthropic`）后拉模型列表报 `'NoneType' object is not iterable`——z.ai 把 404 包在 **HTTP 200** 里返回（`{"code":500,"msg":"404 NOT_FOUND"}`），OpenAI SDK 解析成 `data=None`；且 Anthropic 规范路径是 `{base}/v1/...`，base 不带 `/v1` 时由 `anthropic_channel.messages_base` 归一化补齐。现已按协议分流 + 200 包错误拆包报真错。

---

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/system-config/ai_assistant_config/value` | 获取方案助手配置 |
| PUT | `/api/system-config/ai_assistant_config` | 更新方案助手配置 |
| GET | `/api/system-config/ai_trend_analysis/value` | 获取趋势分析配置 |
| PUT | `/api/system-config/ai_trend_analysis` | 更新趋势分析配置 |
| GET | `/api/system-config/llm_config/value` | 获取 LLM 配置 |
| PUT | `/api/system-config/llm_config` | 更新 LLM 配置 |
| POST | `/api/system-config/llm_config/test` | 测试连接（body: base_url/api_key/model/upstream_format，缺省回落 DB/.env） |
| POST | `/api/system-config/llm_config/models` | 拉取可用模型 id 列表（body 同上） |
| POST | `/api/system-config/llm_config/probe` | 能力探测（JSON 输出 + 原生 tools，双协议） |
| GET | `/api/system-config/llm_config/probe-history` | 实测模型清单（全部探测留档含失败与历史端点，管理员） |
| GET | `/api/assistant/tools` | AI 工具目录（DB 权威行 + 种子默认合并；tools=卡片目录数据含 display_name/one_liner/custom，usage=工具→引用节点映射，供「被引用」徽标） |
| PUT | `/api/assistant/tools/{name}/text` | 编辑工具文案（admin；model_brief 保存跑宪法 lint，命中祈使/流程词 400 拒） |
| DELETE | `/api/assistant/tools/{name}/text` | 整工具恢复默认文案（=种子值整行写回 `rules.agent_tool_text`，不删行；admin） |
| — | `/api/dashboard/trend-overview`（已下线） | 趋势分析富数据路由已删除，数据改由方案助手数据工具链路提供：LLM 提参 → `query_cpq_data` 查数 → 注入作答（见 `api/assistant.py`） |

---

## 数据库表

| Schema | 表 | Key | 用途 |
|--------|-----|-----|------|
| `rules` | `system_config` | `ai_assistant_config` | 方案助手配置 |
| `rules` | `system_config` | `ai_trend_analysis` | 趋势分析配置（提示词模板 + 重点商机条数） |
| `rules` | `system_config` | `llm_config` | LLM API 配置 |

---

## 关键文件

- `views/settings/AiSettings.vue` — AI 设置页面
- `composables/assistantContext.ts` — 上下文 Provider 管理
- `composables/assistantProviders.ts` — Provider 定义 + 趋势分析快捷指令（`loadTrendConfig` / `loadTrendPrompt`，数据走数据工具、不再拼 context）
- `api/dashboard.py` — `/summary` 单周期统计 + `get_highlights`（重点商机查询，供数据工具复用）
- `services/agent_tools.py` — 全系统 LLM 工具唯一注册表（`_TOOL_SPECS` / `tool_catalog` / `query_cpq_data` handler）
- `api/assistant.py` — 数据工具链路（LLM 提参 → `query_cpq_data` 查数 → 注入作答）
- `services/llm_client.py` — LLM 客户端（stream_chat 流式 + test_connection / list_models 排障）