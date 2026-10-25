# 配件选配（kp_reason）工具设计：搜料与选定（2026-09-09 定稿）

> 最后更新：2026-09-12（P0 词法引擎 + P1 词法/语义混合检索落地，见文末）

> 记录本轮工具形态的定稿结论与依据，供改造 `choose_parts` / `part_query` 对照。核心分歧点：**AI 不该“傻傻全库检索”，但也不能被“提前算死的一小撮候选”卡死**。

## 一句话

**保留“AI 驱动检索/浏览”的工具面，但把每一次检索做成“定向 + 可收窄 + 可翻页 + 高信号”；同时把“检索真相 / 价格 / 政策 / 白名单”锁在引擎里，AI 只提议，不确定就交客户确认。**

## 调研依据（权威来源，2026-09）

- Anthropic《Writing tools for agents》：工具按**任务自然切分**写、只返回**高信号语义**信息、对吃算力的响应**用分页/范围/过滤/截断 + 合理默认值**，并明确**“多次小范围目标搜索，好过一次性宽泛大搜索”**。
  - https://www.anthropic.com/engineering/writing-tools-for-agents
- MCP 规范：**工具（模型主动调用的动作）与资源（宿主决定何时注入的数据，如 UI 卡片）是两层**。
  - https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- QuoteForge（同款 CPQ 配置器）：**LLM 只提议结构化意图（哪个 SKU/数量/折扣），确定性引擎重算每一分钱、执行政策、用白名单匹配；越权停在人工批准点，带幂等审计。**
  - https://github.com/ameydabhade/quoteforge

## 分工（谁干什么）

| 角色 | 干什么 |
| --- | --- |
| **AI（唯一大脑）** | 提出“要哪类、什么规格、选哪个 SKU、几个”；读需求→判断该配什么→挑料→填表；拿不定/替代料→交客户。 |
| **引擎 / 工具（确定性）** | 按「机箱系列适配 + 规格过滤 + 关键词」定向检索，只给高信号候选（语义名 + 规格 + 适配系列），带**分页/截断标记**；价格/政策由引擎算；**候选池 = 白名单**，库外料号一律拒绝。 |
| **客户（人工把关）** | 需求模糊、未写具体型号、只能替代料 → `ask_user` 升格选项卡，客户点选后落地。 |

## 工具契约（`choose_parts` 检索侧）

- `category`：必填（行类目）。
- `series`：**自动继承**已锁定机箱（AI 无需传）。
- `keywords` / `spec_filters`：**定向收窄**（AI 点型号/规格词，或结构化 `spec_key/op/value`）。
- `limit`：默认有界（如 8），超出给 `truncated` 标记。
- `offset`：**翻页**钻取，默认 0；`truncated=true` 时 AI 可翻页或加过滤，把第 13 个也捞上来。
- `response_format`：`concise` / `detailed`（默认 `concise`）——控制返回字段量与 specs 裁剪，Anthropic 推荐的 token 效率手段。
- 返回：`{rows:[{part_id,name,price,currency,specs,applicable_series}], total, truncated, next_offset, source}`，`name` 用库内语义名，不用 UUID。

> 参数名无歧义（`category`/`spec_filters` 明确），输入/输出用严格 schema，与 Anthropic“像给新人讲工具”一致。

## 两种用法（对应需求清晰度）

1. **具体行（客户点名型号/明确规格）**：AI 拿规格定向查 → 精确命中直接锁定；找不到完全一致 → 按性能取适配机箱平台的替代（`substitute` ⚠️）→ 锁定并说明；替代也含糊 → `ask_user`。
2. **模糊行（一句话/仅类目）**：AI **根据知识决定看哪个类目**（如 AI 服务器→重点 GPU）→ 调工具做**定向浏览**（系列适配+排序），挑一个或推荐 → 必填类目推荐后必须 `ask_user` 交客户确认（推荐作默认项）。

## 边界（不允许）

- 不让 AI “全库灌进来”：引擎只在**目标类目**内、按**系列适配**筛完后给一页，不加过滤绝不给几百条原样堆。
- 不做“提前算死每行一小撮”的静态候选：模糊行无召回目标时不能依赖“行描述召回”，必须让 AI 带意图来浏览/挑选。
- 不做硬编码/正则判定：`specified`（客户写没写）仍以线索登记表 `kp_rows` 为唯一权威（见 `kp选型-必填与反问语义.md`）。
- 价格/政策/白名单属引擎，AI 不碰；库外料号 `select_kp_parts` 拒绝。

## 检索引擎落地（2026-09-12 P0 词法 + P1 混合检索）

工具契约（上文）不变；检索内核两层升级，对工具调用方透明。

### P0 词法引擎（`app/services/part_lexicon.py`）

- **库件 blob 扩展**：检索面 = 名 + brand + spec 值 + 简介（纯函数，无 DB）。
- **别名表 `kp.kp_search_aliases`**（DB 唯一权威源，startup 空表种子 11 条：万兆→10G、千兆→1G、智凯→智铠、固态硬盘→SSD…；CRUD：`/api/kp/search-aliases`）。
- **加权分级治误报**：原始中文段 +6 > 3-gram 滑窗 +5 > 2-gram +3（跨字伪词降权）> 混合词/数字段（查询带中文时数字裸串降档，治「智铠100→H100」）；容量 ±1% 等值加分；长词命中吸收子词。
- **判别轴互斥**：{sata,nvme,sas,u.2} / {ssd,hdd} / {ddr3,4,5}——查询点名 A、料声明同轴 B → 过滤；料未声明 → 不臆造。

### P1 混合检索（`app/services/part_search.py` + `part_search_index.py`）

- **语义通道**：BAAI/bge-small-zh-v1.5（512 维）本地 fastembed 推理（relay /embeddings 端点 400 坏、无 DashScope key，故走本地）；向量落 `kp.kp_part_search_index`（embedding JSON、content_hash 增量防重嵌入）；新鲜度 = 检索前 COUNT/MAX(updated_at) 对账，料增改后首次检索自动重建（288 件全量约 28s），不挂钩件 CRUD。模型缓存就位后 `_get_model` 默认 `HF_HUB_OFFLINE=1` 本地秒载（防 HF 不可达时首查挂网络重试）。
- **融合**：词法/语义双通道并行 → RRF（k=60）融合排序；**每条候选带 `match` 溯源**（`lexical` / `semantic:0.xx`），AI 看得见「为什么命中」。
- **硬信号守卫**：语义候选照样过确定性规格过滤、判别轴、**容量 ±1% 守卫**——向量分不清 480G/2T/141G，但容量是硬约束，语义不许压过它（实测病灶：「2T固态」被语义把 480G 排到第一、「HBM3e 141G」库外被误报成 72G 显卡）。
- **降级链**：fastembed 不可用 / 索引空 / 嵌入失败 → 整体退化为纯词法（行为=P0），检索永不因语义通道挂死。
- **接线**：`query_parts`（keywords 模式 + rows 行批量模式）内部切 `hybrid_search`；`part_query`/`part_recall` 契约不动（assistant 等直连方继续纯词法）。

### 实测（scripts/hybrid_battery.py，13 口径对照）

混合 13/13 vs 词法 11/13：口语长句（两张万兆光口网卡）、型号（9361 1G缓存→精确 LSI 9361-8i 第一）、品牌（沐曦）、错写（智凯100→智铠行、零 H100 污染）、规格组合（1.92T SATA→SATA 第一零 NVMe）、规格过滤（DDR5）、**语义长尾（「训练加速卡」词法零召回→语义补位 GPU 涡轮卡）**、系列作用域（Polaris 得 KH50000 / Orion 给 scope 真话）、容量口语（2T→2T 居首）。库外项（HBM3e 141G）按「库外不拦截、匹配度分级」定调回近邻+溯源，交 AI 比对规格后如实告诉客户。单测 9+15 新增，全量回归 623 绿。
