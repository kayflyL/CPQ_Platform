# 定价引擎（Pricing Engine）算法说明

> 版本：v0.1.11 | 最后基于代码核对日期：2026-07-11
> 源文件：`backend/app/engine/pricing_engine.py`（2198 行，全项目最大文件）
> 关联文件：`backend/app/services/quote_service.py`、`backend/app/repository/*.py`、`backend/app/models/rules.py`

---

## 1 概述与定位

`PricingEngine` 是 CPQ Platform 的**核心业务逻辑层**，承担以下职责：

1. **Excel 报价单解析**——把上传的原始 Excel 拆成多配置(CFG)的 L6/KP/质保条目；
2. **L6 整机基准价匹配**——基于五个维度从 L6 价格库找到最接近的整机价；
3. **KP 零件价格比对**——把 Excel 里的 KP 价格与数据库最新价做一致性校验；
4. **KP 价格回写同步**——保存报价时把新价格写回 KP 库；
5. **项目/报价单 CRUD**——通过 Repository 读写业务库；
6. **模板驱动的 Excel 导出**——按导出模板生成正式报价单。

### 1.1 "纯算法、不碰 DB"的项目约束

引擎的设计原则（见文件头 docstring，第 1–7 行）：

> Pricing Engine — pure business logic layer.
> Replaces the DB-coupled parts of legacy data_processor.py.
> All data access goes through injected Repository instances.
> No sqlite3, no direct DB connections.

落地方式：

- 构造函数（`__init__`，L102–112）**只接收 Repository 实例**，从不自己 `import sqlite3` 或创建连接；
- 所有数据库读写都走 `self.kp_repo` / `self.l6_repo` / `self.opportunity_repo` / `self.rules_repo` 等注入的 Repository；
- 规则（区域关键词、匹配维度、阈值等）从 `rules.db` 读取，**带硬编码兜底默认值**（L132–223）；
- 引擎本身可被单元测试时注入 mock Repository，无需真实数据库。

> 注意：**利润率/最终价的乘法核算并不在引擎里**，而在 `QuoteService.process_upload` 中完成（见 §3.8）。引擎负责"取价/匹配"，Service 负责"算价"。这是本系统的一条重要边界。

---

## 2 输入输出

### 2.1 引擎主要公开方法的输入输出

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `parse_file(sheet_dict)` | `pd.read_excel(sheet_name=None)` 得到的 `{sheet名: DataFrame}` | `(configs, first_meta)` | configs 是 `{sheet名: {meta, items}}` |
| `preview_parse(df, ...)` | 单 sheet 的 DataFrame | `{grid, max_row, max_col, cell_marks, meta}` | 供前端热力图预览 |
| `enrich_config(items_df, meta)` | 单配置条目 DataFrame | 带 `match_status / db_price / base_price / is_usd_cpu / profit_margin` 的 DataFrame | 只标注、不自动填价 |
| `match_l6_total(meta)` | 单配置 meta dict | `(price, matched_record)` | 五维匹配 L6 整机价 |
| `preview_l6_match(dim_values)` | `{chassis, model, drive_bays, psu, motherboard}` | `{steps, final_match}` | 逐步骤预览匹配过程 |
| `sync_kp_prices_to_db(configs_data)` | `{cfg名: items_df}` | `int`（新增条数） | 比对后批量写入 KP 新价 |
| `generate_excel(opportunity_id, template_id)` | 项目 ID + 模板 ID | `(BytesIO, filename)` | 模板驱动的 Excel 导出 |

### 2.2 解析产出的条目（item）字段

`_parse_items` 产出的每个 item（L663–724）：

| 字段 | 含义 |
|------|------|
| `category` | `'L6'` / `'Key Parts'` / `'Warranty'` |
| `part_name` | 目录号（catalogue，通常 D 列） |
| `spec` | 描述/型号（L6→E列描述；KP→E列型号） |
| `qty` | 数量（F 列），解析失败默认 1 |
| `confirmed_price` | Excel 原始价格（KP 取 G 列；L6/Warranty 为 None） |
| `currency` | `'RMB'` 或 `'USD'`（CPU/Processor 且型号含 USD/$ 时为 USD） |
| `warranty_years` | 仅 Warranty 类：从描述 `质保(\d+)年` 提取的年限 |

---

## 3 核心算法

### 3.1 Excel 区域定位 `_find_region_row`（L528–598）

从 DataFrame 中找到"含任意关键词的第一行"。用于定位 L6 区、KP 区、质保区、合计区的起止行。

**输入**：`keywords_str`（逗号分隔，如 `"Keyparts,KP"`）、`start_row`。

**三趟匹配**（依次尝试，命中即返回行号；全部失败返回 -1）：

1. **词边界匹配**：对每个单元格小写化后用 `\b<kw>\b` 正则，避免 `L6` 误命中 `L60`；
2. **子串匹配**：直接 `kw in cell`；
3. **模糊匹配**：Levenshtein 编辑距离 ≤ 2，**仅对长度 ≥4 的关键词生效**（L589 跳过 ≤3 字符的词，防止短词误匹配）。先按长度差 ≤2 快筛，再算编辑距离。

> 编辑距离实现为标准 Levenshtein 动态规划（L563–578）。

### 3.2 元数据提取 `_extract_meta`（L344–526）

从表头（前 10 行）+ 正文行扫描提取商机元数据，并构造五维匹配所需的输入。

**表头关键词扫描**（`find_keyword_value`，L362–389）：在前 10 行、前 10 列找到关键词后，向右扫描第一个非空单元格作为值。多关键词回退：

- 商机名：`Project Name` → `商机名称`
- 型号：`Model` → `型号`；用正则 `\((\d+)` 提取 `model_qty`（括号内数字），`(` 前为 `model_name`
- FAE、L6 描述（`L6 Description`/`PRODUCT SPEC`/`产品规格`，长度需 >10）、日期

**五维匹配输入构造**（这些值直接喂给 `match_l6_total`）：

| 维度 | meta 字段 | 提取规则 | 源代码行 |
|------|-----------|----------|----------|
| chassis | `chassis_form` | 从 `l6_desc` 正则 `(\d+(?:\.\d+)?)\s*[Uu]\b`，如 `2U` | L426–428 |
| model | `l6_model_type` | `l6_desc` 含 `switch`(忽略大小写) → `'Switch机型'`；否则**留空**（不硬编码默认） | L432–436 |
| drive_bays | `drive_bays` | 扫描 D 列(索引3)含 `backplane` 的行，E 列(索引4)正则 `^(\d+)\*` 取盘位数 | L439–449 |
| psu | `psu` | 扫描 D 列含 `power supply` 的行，E 列正则 `(\d+W)` 取功率，F 列(索引5)取数量，拼成 `"650W * 2"` | L455–474 |
| motherboard | `motherboard` | 扫描 D 列 **完全等于** `cpu` 的行取 CPU 规格，再与 `_mb_mappings` 做**子串包含**匹配（大写） | L480–494 |

**主板映射**（CPU 特征 → 主板型号，硬编码默认 L158–166）：

| CPU 特征（子串，大写匹配） | 主板型号 |
|---|---|
| KH50000 | Polaris MB |
| KH30000 | Orion MB |
| KH20000 | Orion MB |
| AMD / EPYC / INTEL / XEON | TTY TG658V3 |

匹配按列表顺序，**第一个命中即停**（注意：`KH30000` 在 `KH20000` 前）。

未提取到的字段会写入 `meta['warnings']`（如 `PRODUCT_SPEC`/`CHASSIS_FORM`/`DRIVE_BAYS`/`PSU`/`MOTHERBOARD`/`MODEL_TYPE`），供前端提示。

**兜底**（L502–522）：若表头没解析到商机名/型号，尝试 `df.iloc[1,3]` 和 `df.iloc[2,3]` 硬编码位置。

### 3.3 L6 五维匹配 `match_l6_total`（L825–945）★核心

> 这是全引擎最关键的算法，决定每台整机的基准价。

**输入**：单配置 `meta`（含 `chassis_form`/`l6_model_type`/`drive_bays`/`psu`/`motherboard`）。

**数据源**：`l6_repo.get_all_for_matching()`（L830）→ 返回所有 L6 记录，字段：`chassis, model, motherboard, backplane, drive_bays, psu, price, update_date, note`（按 `update_date DESC` 排序）。

**维度映射**（L837–843）：meta 字段名 → 匹配维度名：

```
chassis_form → chassis
l6_model_type → model
drive_bays → drive_bays
psu → psu
motherboard → motherboard
```

**单维匹配 `_match_dim`（L847–875）**返回 `(过滤后df, 是否命中, 是否模糊, 是否跳过)`：

1. **值为空 → 跳过**（`skipped=True`，不参与过滤、不计入已评估维度）；
2. **精确匹配**：`candidates_df[dim].str.strip() == val`，命中则过滤并返回；
3. **机箱模糊**（仅 `dim=='chassis'` 且 `_allow_chassis_fuzzy`，见 §3.4）；
4. **主板降级**（仅 `dim=='motherboard'` 且 `_allow_motherboard_fallback`，见 §3.5）；
5. 都不中 → 返回空 df，本维未命中。

**完整匹配流程**：

- **第一步：全维匹配**（L877–912）。按 `_l6_match_dims`（默认 5 维）顺序逐维过滤。统计 `matched_count`（命中维数）/`evaluated_dims`（跳过空值后实际评估的维数）。只要中间某维未命中且候选清空就提前 break。
  - 若最终候选非空 → 取第一条（`iloc[0]`，即最新日期），返回 `(price, matched)`。
  - `match_type` 判定：用了任意模糊 → `'模糊匹配(m/e)'`；全中 → `'精确匹配'`；否则 `'部分匹配(m/e)'`。
  - `match_score = int(matched_count / evaluated_dims * 100)`。

- **第二步：降级匹配**（L914–945）。仅当第一步候选为空时触发。用 `_l6_fallback_dims`（默认 `["chassis","model","drive_bays"]`）重跑一遍过滤。命中则 `match_type='降级匹配'`，`match_score` 以 fallback 维数为分母。

- **第三步：未匹配兜底**（L931–936）。降级仍空则调 `_find_best_partial_match`：遍历全库按 5 维逐条计分，取 **得分最高的前 3 条**返回，`match_type='未匹配'`，价格返回 `None`。

> 关键细节：**空值维度被跳过而非视为不匹配**。例如只解析到 chassis 和 model 两个维度，则 `evaluated_dims=2`，全中即 100 分精确匹配。这意味着解析质量直接决定匹配质量。

### 3.4 机箱模糊匹配（chassis fuzzy）

**开关**：`_allow_chassis_fuzzy`（默认 `False`，由规则 `allow_chassis_fuzzy` 控制，L211–213）。

**规则**：`_chassis_fuzzy_rules`（默认空列表，由规则 `chassis_fuzzy_rules` 控制，L215–217），形如 `[{"from":"2U","to":"2.5U"}]`。

**逻辑**（L858–864）：当 chassis 精确匹配失败时，若当前值 `val` 等于某规则的 `from`，则改用规则的 `to` 值再过滤一次。本质是"找不到 2U 时退而求其次找 2.5U"。

### 3.5 主板降级匹配（motherboard fallback）

**开关**：`_allow_motherboard_fallback`（默认 `False`，由规则 `allow_motherboard_fallback` 控制，L219–221）。

**逻辑**（L866–874）：当目标主板精确匹配失败时，若该主板是 `_mb_mappings` 里的已知型号，则放宽为"**任意其他已知主板**"（`isin([其他所有主板型号])`）。即允许 Polaris MB、Orion MB、TTY TG658V3 之间互相替代。

在 `preview_l6_match`（Step 2，L1033–1074）中，主板过滤被替换为 `candidates['motherboard'].isin(alt_motherboards)`，其余维度仍按原值精确匹配。

### 3.6 KP 价格比对 `enrich_config`（L768–823）

只标注、不自动填价（"NO auto-fill"，docstring L770）。

**流程**：

1. 一次性批量取 KP 库最新价（`kp_repo.get_latest_prices()`，L776），构造 `{model.lower().strip(): price}` 字典——避免 N+1 查询；
2. 新增列：`match_status`、`db_price`、`base_price(=confirmed_price)`、`is_usd_cpu`、`profit_margin`(默认 10.0)；
3. 仅对 `category=='Key Parts'`：
   - **精确匹配**：`part_name.lower()` 在字典中 → 取 db_price；
   - **模糊匹配**：精确未中且 `spec` 长度 >2 → `kp_repo.fuzzy_match_price(spec)`（SQL `LIKE %spec%`，取最新一条，L796–798）；
4. `match_status` 判定（L802–814，阈值 `_price_diff_threshold` 默认 0.01）：

| Excel 有价 | DB 有价 | 价格差 | match_status |
|---|---|---|---|
| 否 | 是 | — | `⚠️ 待填入 [DB=x]` |
| 是 | 是 | > 0.01 | `⚠️ 差异 (Excel: a, DB: b)` |
| 是 | 是 | ≤ 0.01 | `✅ 一致 [DB=x]` |
| 否 | 否 | — | `❌ 缺失 (请填写)` |
| 是 | 否 | — | `🆕 新部件` |

5. NaN 清洗：object 列填 `""`，数值列填 `0`（L817–821，防 JSON 序列化出错）。

### 3.7 KP 价格同步 `sync_kp_prices_to_db`（L1136–1201）

保存报价时把 KP 新价写回 `kp_data.db`。

**流程**：

1. 取今天日期，批量加载所有最新价到内存字典（L1146–1152）；
2. 仅处理 `category=='Key Parts'` 条目；
3. **分类映射**（L1171–1181）：用 `_kp_cat_map` 把 `part_name` 关键词映射成标准分类（如 `cpu/processor→CPU`，`memory/ram→Memory`，`hdd/ssd→HDD/SSD` 等，完整默认见下表）；`model = spec 或 part_name`；
4. `new_price = base_price`，为 0/NaN 则跳过；
5. **去重**：内存字典查同 model 最新价，若 `abs(new_price - db_price) < 0.01` 则跳过（L1190–1192）；
6. 收集到 `pending_inserts` 后**批量插入**（L1197–1199）。

**KP 分类映射默认值**（`_kp_cat_map`，L145–157，关键词小写匹配）：

| 关键词 | 标准分类 |
|---|---|
| cpu / processor | CPU |
| memory / ram | Memory |
| hdd / ssd | HDD/SSD |
| raid | Raid card |
| network / nic | NIC |
| gpu | GPU |
| power / psu | Power |
| fan | Fan |
| heatsink / cooler | Heatsink |
| cable / wire | Cable |
| rail | Rail |

### 3.8 利润率与最终价格核算（QuoteService，非引擎）

> 此算法在 `quote_service.py` 的 `process_upload`（L102–116）中，不在 `pricing_engine.py`。但它是定价的最终一环，必须一并说明。

**配置来源**：`config.json`（路径 `DATA_PATH/config.json`），代码兜底默认（L42）：`{tax_rate: 0.13, usd_to_rmb: 7.0, profit_margin: 0.1, warranty_fee_rate: 0.02}`。

**默认利润率**（L77）：`default_margin = config.profit_margin(0.1) * 100 = 10.0`（百分比）。

**逐条核算**（L105–116）：

```
margin_dec = margin_pct / 100   若 margin_pct > 1
           = margin_pct          若 margin_pct ≤ 1     ← 注意边界

RMB:    final_price = base * (1 + margin_dec)
USD:    final_price = base * usd_to_rmb * (1 + tax_rate) * (1 + margin_dec)
```

USD 路径触发条件：`item.is_usd_cpu == True` 或 `item.currency == 'USD'`（L111）。

> ⚠️ **边界陷阱**：`margin_pct == 1` 时走 `else` 分支，`margin_dec = 1.0`（即 100% 利润率）。这是因为 `1 > 1` 为 False。实际使用中 margin 通常为 10.0 这种百分比值（>1），所以正常路径是 `10/100=0.1`，但若有人传入恰好为 1 的值会异常放大。

`final_price` 四舍五入到 2 位小数（L116）。

**分类汇总**（L119–164）：

- `line_total = final_price * qty`
- `L6` 类累加到 `l6_total`；`Warranty` 类累加到 `warranty_total`；其余（KP）累加到 `kp_total`
- `grand_total = l6_total + kp_total + warranty_total`

### 3.9 质保处理（warranty）

**解析**（引擎 `_parse_items` L728–762）：定位 `Warranty` 区域行（C 列类型 `L6`/`KP`，D 列描述），从描述正则 `质保(\d+)年` 提取年限到 `warranty_years`。

**核算**（QuoteService L90–151）：

- 初始化 `warranty_info = {l6:{detected,years,rate:0.02,...}, kp:{...}}`；
- 遍历 Warranty 条目，按 `part_name` 含 `l6` 或 `kp`/`key part` 分类；未明确分类且 L6 未占用则默认归 L6；
- 检测到质保后 **`rate` 被置为 0**（L136/141/148）；
- `warranty_total` = 各 Warranty 条目 `final_price * qty` 之和。

> 说明：`warranty_fee_rate=0.02` 与 `rate=0.02` 仅作为初始占位，**一旦从 Excel 检测到质保行就被清零，且从不参与任何乘法运算**。质保金额完全由 Warranty 条目自身价格决定。该 0.02 目前是冗余常量。

### 3.10 Excel 公式安全求值 `_safe_eval_math`（L45–64）

KP 价格单元格（G 列）可能是 Excel 公式（以 `=` 开头）。引擎用 AST 安全求值替代 `eval()`：

- 支持运算符：`+ - * /` 及一元 `+/-`（`_SAFE_BIN_OPS`/`_SAFE_UNARY_OPS`，L33–42）；
- **不支持 `**`（幂运算）**，防止 `9**9**9` 类 DoS；
- 非法表达式抛 `ValueError`。

调用点：`_parse_items` 中 KP 价格为 `=...` 字符串时（L697–700）。

### 3.11 模板驱动导出 `generate_excel`（L1387–1499）+ `_fill_from_bindings`（L1621–1785）

**模板来源**：`export_template_repo`，含 `template_json`（cover/config_sheet 的 bindings）和 `fileBuffer`（base64 编码的真实 Excel 文件）。

**生成流程**：

1. 取项目详情 + 加载模板 + 解码 cover/config 两个 Excel 文件为 `BytesIO`（L1501–1522，避免写临时文件）；
2. 合并 cover 和 config 的工作簿（`_copy_worksheet` 逐单元格复制值+样式+合并区+列宽+行高，L1524–1556）；
3. 计算 meta 派生字段：`model_name`（首个 L6 条目的 spec/part_name）、`l6_desc`（前 5 个 L6 part_name 拼接）、`model_name_with_qty`；
4. **封面**：按 `cover.bindings` 静态绑定填 meta 字段；
5. **配置页**：保留原始模板页不动，**每个配置复制一份新页**再填充（避免配置间串数据），最后删除原始模板页（L1475–1485）；
6. sheet 命名（`_generate_sheet_name` L1558–1598）：支持模板变量 `{cfg_name}/{chassis_form}/{cpu_model}`，清洗非法字符 `\ / ? * [ ]`，截断 31 字符，重名加 `(n)` 后缀。

**绑定填充 `_fill_from_bindings`**：

- **静态绑定**（`dataType=='static'`）：单格 → meta 字段（经 `_get_meta_value` / `_resolve_field_dynamically` 动态解析，支持 business_fields 配置）；
- **动态绑定**（`dataType=='dynamic'`）：区域 → 按 `regionFieldKey`（`l6_details/kp_details/warranty_details/all_items/config_summary`）取数据列表，在起始行插入物理行（`ws.insert_rows`），继承模板行样式。**从下往上处理**（L1685–1688），避免上层插入挤乱下层绑定；
- 字段映射 `_map_field_to_value`（L1787–1819）：`catalogue→spec`、`description→part_name`、`quantity→qty`、`quotation→final_price`、`total_price→final_price*qty` 等。

**配置汇总 `_build_config_summary`**（L1956–2018）：封面每配置一行，`unit_price = Σ(L6 final_price*qty) + Σ(KP ...) + Σ(Warranty ...)`，`total_price = unit_price * config_quantities[cfg]`。

**数字精度**：`_get_number_format`（L1615–1619）按 `rules_repo.get_number_precision()`（默认 2）映射 Excel 格式：`0→'#,##0'`、`2→'#,##0.00'`、`4→'#,##0.0000'`。

### 3.12 描述模板渲染 `_render_description_template`（L2020–2051）

把 `{kp_list}` / `{l6_list}` / `{warranty_list}` / `{all_list}` 展开为 `part_name × qty` 用分隔符拼接的字符串。`_build_export_description`（L2054–2131）则支持更复杂的循环块语法 `[${cat_model}*${cat_qty}; 分隔符]`，**但见 §7 已知问题：该方法及其依赖 `_extract_categories` 当前为死代码且有 NameError**。

---

## 4 关键数据结构

### 4.1 L6 匹配记录（`l6_repo.get_all_for_matching()` 返回）

```
chassis, model, motherboard, backplane, drive_bays, psu, price, update_date, note
```

匹配只用到 `chassis / model / drive_bays / psu / motherboard` 五列 + `price`（取值）。`backplane` 列存在但不参与五维匹配。

### 4.2 KP 最新价记录（`kp_repo.get_latest_prices()` 返回）

```
id, category, model, price, currency, date, note, record_count
```

`enrich_config` 只用 `model` 和 `price`。

### 4.3 matched_record（匹配结果附加字段）

`match_l6_total` 命中后给记录 dict 追加：

- `match_score`：int，`matched/evaluated * 100`
- `matched_dims`：命中的维度数
- `total_dims`：实际评估的维度数
- `match_type`：`'精确匹配'` / `'模糊匹配(m/e)'` / `'部分匹配(m/e)'` / `'降级匹配'` / `'未匹配'`
- `candidates`：仅未匹配兜底时存在，前 3 条候选

### 4.4 rules.db 规则表（`models/rules.py`）

| 表 | 用途 |
|----|------|
| `l6_region_config` | L6 区起止关键词 + 字段列映射 |
| `kp_region_config` | KP 区起止关键词 + 字段列映射 |
| `kp_category_mapping` | KP 关键词→标准分类 |
| `motherboard_mapping` | CPU 特征→主板型号 |
| `matching_rules` | 通用规则（`rule_name`+`rule_value` JSON/数值） |

---

## 5 调用关系

### 5.1 上传解析主链路（`QuoteService.process_upload`，quote_service.py L44–179）

```
API api/quote.py 上传
  → QuoteService.process_upload(file_content, filename)
      ├─ pd.read_excel → sheet_dict
      ├─ engine.parse_file(sheet_dict)           [§3.1/3.2  解析]
      │     → engine._extract_meta / _parse_items
      ├─ 逐配置:
      │   ├─ engine.enrich_config(items, meta)    [§3.6  KP 比对]
      │   ├─ engine.match_l6_total(meta)          [§3.3  五维匹配]
      │   ├─ 把 L6 价赋给首条 L6 行，其余标"已包含"
      │   ├─ 逐条算 final_price（margin/USD/税）  [§3.8  在 Service]
      │   └─ 汇总 l6/kp/warranty/grand_total       [§3.9]
      → 返回 {configs, ...} 给前端
```

### 5.2 保存报价链路（`QuoteService.save_opportunity`，L204–243）

```
→ engine.save_opportunity(...)   [写 opportunities + quotations + items]
→ engine.sync_kp_prices_to_db(cleaned)   [§3.7  KP 回写，失败非致命]
```

### 5.3 导出链路（`QuoteService.export_opportunity`，L245–246）

```
→ engine.generate_excel(opportunity_id, template_id)   [§3.11 模板导出]
    → engine.get_opportunity_details / _load_template / _fill_from_bindings
```

### 5.4 L6 匹配预览（独立链路，`api/rules.py` L48–58）

```
POST /l6/preview-match
  → engine.preview_l6_match(dim_values)   [§3.3 逐步骤预览]
```

> ⚠️ 见 §7：该端点的引擎构造方式存在 bug。

### 5.5 引擎依赖的 Repository

| Repository | 数据库 | 引擎用途 |
|---|---|---|
| `KPRepository` | kp_data.db | KP 最新价、历史价、模糊匹配、插入新价 |
| `L6Repository` | l6_data.db | L6 全量记录（匹配）、增删改、历史 |
| `OpportunityRepository` | opportunities.db | 商机/项目元数据 |
| `RulesRepository` | rules.db | 区域配置、映射、匹配规则、精度 |
| `ExportTemplateRepository` | rules.db | 导出模板 |
| `QuotationRepository`（懒加载） | opportunities.db | 报价单及明细 |
| `BusinessFieldRepository`（懒加载） | kp_data.db | 动态字段解析 |

---

## 6 关键阈值与常量

> 以下数值均为代码中的真实默认值；多数可通过 `rules.db` 覆盖。

| 常量 | 默认值 | 来源 | 含义 |
|------|--------|------|------|
| `_price_diff_threshold` | `0.01` | L169 / 规则 `price_diff_threshold` | KP 价格一致判定阈值（元） |
| `_l6_match_dims` | `["chassis","model","drive_bays","psu","motherboard"]` | L167 / 规则 `l6_match_dimensions` | 五维匹配维度及顺序 |
| `_l6_fallback_dims` | `["chassis","model","drive_bays"]` | L168 / 规则 `l6_fallback_dimensions` | 降级匹配维度 |
| `_allow_chassis_fuzzy` | `False` | L171 / 规则 `allow_chassis_fuzzy` | 机箱模糊匹配总开关 |
| `_allow_motherboard_fallback` | `False` | L173 / 规则 `allow_motherboard_fallback` | 主板降级匹配总开关 |
| 编辑距离阈值 | `≤ 2` | L595 | `_find_region_row` 模糊匹配阈值 |
| 模糊关键词最小长度 | `≥ 4` | L589 | 短词不参与模糊匹配 |
| 表头扫描行数 | 前 `10` 行 | L364 | `_extract_meta` |
| 表头扫描列数 | 前 `10` 列 | L365 | `_extract_meta` |
| `config.tax_rate` | `0.13` | quote_service L42/108 | USD CPU 加税税率（13%） |
| `config.usd_to_rmb` | `7.0` | quote_service L42/109 | USD→RMB 汇率 |
| `config.profit_margin` | `0.1` | quote_service L42/77 | 默认利润率（×100=10%） |
| `config.warranty_fee_rate` | `0.02` | quote_service L42 | 冗余，检测到质保后置零（见 §3.9） |
| `profit_margin` 列默认 | `10.0` | 引擎 L783 | enrich 时填充 |
| L6 描述最小长度 | `> 10` | L411 | 短于此不采信为 l6_desc |
| L6 区域默认关键词 | 起始 `L6`，结束 `Keyparts,KP` | L136–139 | |
| KP 区域默认关键词 | 起始 `Keyparts,KP`，结束 `Warranty,Total` | L140–143 | |
| L6 默认字段映射 | catalogue=D, description=E, quantity=F | L137 | |
| KP 默认字段映射 | catalogue=D, model=E, quantity=F, price=G | L142 | |
| 历史查询默认 limit | `10`（引擎）/ `20`（repo） | L1133 / kp_repo L73 | |
| 数字精度默认 | `2` | rules_repo L409 | 导出小数位 |
| Excel sheet 名长度上限 | `31` | L1592 | Excel 限制 |
| L6 描述拼接上限 | 前 `5` 个 part_name | L1451 | meta.l6_desc |
| partial_match 候选数 | 前 `3` 条 | L972 | 未匹配时返回 |

---

## 7 已知边界与限制

> 以下是阅读源码时发现的、修改定价逻辑前必须知晓的问题。**准确性优先，以下均基于代码实际状态**。

### 7.1 【严重】`_load_rules()` 当前不可达，规则属性不会被初始化

`__init__`（L102–112）**没有调用 `self._load_rules()`**。唯一的调用（L130 `self._load_rules()`）位于 `_get_business_field_repo` 方法内 `return` 语句（L126）**之后**，属于不可达死代码。

后果：一旦调用 `parse_file` / `match_l6_total` / `enrich_config` 等任何依赖 `self._l6_region_config`、`self._mb_mappings`、`self._l6_match_dims`、`self._kp_cat_map`、`self._price_diff_threshold` 的方法，会抛 `AttributeError`。

这些属性**仅在 `_load_rules()`（L132–223）中被赋值**（含硬编码默认与 DB 覆盖）。全文检索确认 `_load_rules` 仅出现在定义处（L132）和该不可达调用处（L130）。

> 修复方向：在 `__init__` 末尾（L112 之后）补一行 `self._load_rules()`。本文档第 3、6 章描述的所有默认值/逻辑均为 `_load_rules` 的**设计意图**，按此修复后即可生效。

### 7.2 【严重】`api/rules.py` 预览端点构造引擎方式有误

`preview_l6_match`（rules.py L50–57）执行 `engine = PricingEngine()`——**无参构造**，但 `__init__` 的 `kp_repo/l6_repo/opportunity_repo` 是必填位置参数，会抛 `TypeError`。随后又调用 `engine.close()`，而 `PricingEngine` **没有 `close` 方法**。叠加 §7.1，即便构造成功，`preview_l6_match` 内访问 `self._l6_match_dims` 也会 `AttributeError`。

> 该端点（`POST /l6/preview-match`）当前不可用。

### 7.3 `_build_export_description` / `_extract_categories` 为死代码且含 NameError

`_extract_categories`（L2133–2198）：

- 第 2192 行使用 `export_categories.setdefault(...)`，但该变量**从未定义**（函数内定义的是 `categories`，L2148）→ 一旦调用即 `NameError`；
- 加载的 `mappings`（L2154）从 DB 取来后**未用于实际分类**——后半段按 `part_name` 文本判断，与 mappings 无关；
- 调用方 `_build_export_description`（L2054）本身**全文无任何外部调用**（grep 确认），属遗留死代码。

> 现行导出实际走 §3.11 的 `_render_description_template`（L2020）+ `_build_config_summary`，不经过这两个方法。

### 7.4 利润率边界值 `1` 的歧义

见 §3.8：`margin_pct == 1` 时 `1 > 1` 为 False，走 `margin_dec = margin_pct = 1.0`（100% 利润率）。正常使用 margin 为 10.0 等百分比值不受影响，但 API 传入恰好 1 会异常。

### 7.5 五维匹配对解析质量高度敏感

空值维度被"跳过"而非"判负"（L851–852）。若 `meta` 只解析出 chassis，则匹配退化为单维，可能误命中高分记录。`meta['warnings']` 是否在前端充分展示直接影响匹配可信度。

### 7.6 主板映射顺序敏感

`_mb_mappings` 按**列表顺序**子串匹配、首中即停（L491–494）。默认顺序 `KH50000→KH30000→KH20000→AMD→...`。若 CPU 规格同时含多个特征（罕见），靠前的优先。修改映射需注意顺序。

### 7.7 `motherboard` 降级范围是"所有其他已知主板"

降级匹配（§3.5）放宽到 `_mb_mappings` 中**除当前值外的全部型号**，不区分 Polaris/Orion/TTY 是否真的兼容。属业务上较粗的近似。

### 7.8 KP 模糊匹配为 SQL `LIKE`，非编辑距离

`fuzzy_match_price`（kp_repo L61–71）用 `WHERE model LIKE %fragment%`，含子串即命中，取最新一条。短 fragment（如 `ssd`）可能命中大量记录。

### 7.9 导出依赖模板必须含 `fileBuffer`

`generate_excel` 在 cover 和 config 都无 fileBuffer 时直接报错（L1403–1404）。模板纯 JSON 配置无法导出。

---

## 8 附：PricingEngine 方法索引

> 行号基于核对时源文件。按代码内分节顺序。

| 行号 | 方法 | 章节参考 |
|------|------|----------|
| L102 | `__init__` | §1.1 / §7.1 |
| L114 / L121 | `_get_quotation_repo` / `_get_business_field_repo`（懒加载） | — |
| L132 | `_load_rules`（**当前不可达，见 §7.1**） | §6 |
| L227 | `parse_file` | §2.1 |
| L243 | `preview_parse` | §2.1 |
| L344 | `_extract_meta` | §3.2 |
| L528 | `_find_region_row`（三趟匹配） | §3.1 |
| L600 / L1610 | `_col_letter_to_index` / `_col_letter_to_idx` | — |
| L608 | `_parse_items` | §2.2 / §3.9 / §3.10 |
| L768 | `enrich_config` | §3.6 |
| L825 | `match_l6_total`（五维匹配 ★） | §3.3 |
| L947 | `_find_best_partial_match` | §3.3 |
| L979 | `preview_l6_match` | §3.3 / §3.4 / §3.5 |
| L1133 / L1136 | `get_kp_price_history` / `sync_kp_prices_to_db` | §3.7 |
| L1205 / L1287 / L1351 | `save_opportunity` / `get_opportunity_details` / `update_project_meta` | §5 |
| L1356 / L1372 / L1387 | `_load_config` / `_load_template` / `generate_excel` | §3.11 |
| L1501 / L1524 / L1558 | `_get_template_files` / `_copy_worksheet` / `_generate_sheet_name` | §3.11 |
| L1621 | `_fill_from_bindings` | §3.11 |
| L1787 / L1821 / L1857 | `_map_field_to_value` / `_get_meta_value` / `_resolve_field_dynamically` | §3.11 |
| L1921 / L1956 / L2020 | `_get_region_data` / `_build_config_summary` / `_render_description_template` | §3.11 / §3.12 |
| L2054 / L2133 | `_build_export_description` / `_extract_categories`（**死代码 + NameError，见 §7.3**） | §7.3 |
| L45 | `_safe_eval_math`（模块级函数） | §3.10 |

---

> 版本：v0.1.11 | 最后基于代码核对日期：2026-07-11
> 源文件：`backend/app/engine/pricing_engine.py`（2198 行）
> 关联：`backend/app/services/quote_service.py`、`backend/app/repository/{kp,l6,opportunity,rules,export_template}_repo.py`、`backend/app/models/rules.py`、`backend/app/core/startup.py`
