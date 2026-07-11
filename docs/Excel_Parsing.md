# Excel 解析逻辑说明

> 版本：v0.1.11 | 更新日期：2026-07-11
> 本文档基于 `D:\CPQ_Platform_V1` 实际源码梳理，目的是让新会话**不读源码就能理解上传解析环节并修改解析规则**。
> 所有结论均标注了来源文件与函数名，可直接跳转核对。

---

## 0. 一句话结论

项目里存在**两套互不相干的 Excel 解析机制**，必须先分清：

| 机制 | 解析发生位置 | 是否真正参与"上传报价单→创建报价单"链路 | 入口 |
|------|------------|--------------------------------------|------|
| **A. 后端生产解析（pandas）** | 后端 `backend/app` | **是**，这是生产链路 | `/api/quote/parse-preview`、`/api/quote/confirm-upload`、`/api/quote/upload-to-opportunity` |
| **B. 前端独立模板解析（exceljs）** | 前端 `frontend/src` | **否**，只是一个独立的离线工具页 | 路由 `/excel-parser`（`ExcelParser.vue`） |

代码搜索确认：`useParseTemplateStore` / `parseExcelByTemplate` 仅被 `ExcelParser.vue`、`ParseTemplateEditor.vue`、`TemplateEditor.vue` 引用，**没有被上传组件 `UploadPreviewDrawer.vue` 或任何上传 API 调用**。因此修改"上传报价单的解析规则"应改后端（机制 A）；前端那套模板（机制 B）只服务于 `/excel-parser` 这个工具页本身。

下面以机制 A 为主线展开，机制 B 单列一章。

---

## 1. 生产上传链路整体流程（机制 A）

涉及文件：
- 前端：`frontend/src/components/UploadPreviewDrawer.vue`、`frontend/src/api/quote.ts`
- 后端：`backend/app/api/quote.py`、`backend/app/services/quote_service.py`、`backend/app/engine/pricing_engine.py`

### 1.1 前后端职责划分

```
浏览器                          后端 FastAPI
──────                          ───────────
UploadPreviewDrawer.vue
  │ 1. 用户选 .xlsx 文件
  │ 2. parseQuotationPreview(file)  ──►  POST /api/quote/parse-preview
  │                                       quote.py: parse_preview()
  │                                         ├─ 校验扩展名/落临时文件
  │                                         └─ QuoteService.process_upload()
  │                                              ├─ pd.read_excel(sheet_name=None)
  │                                              ├─ PricingEngine.parse_file()      ← 拆 CFG + 抽 meta + 抽 items
  │                                              ├─ PricingEngine.enrich_config()   ← KP 价格库匹配
  │                                              ├─ PricingEngine.match_l6_total()  ← L6 五维匹配
  │                                              └─ 价格计算 + 汇总
  │ 3. 收到 { configs: { CFG名: {items, summary, l6_meta, ...} } }
  │ 4. 抽屉里展示多配置 Tab、L6 候选 Top3、KP 清单
  │
  │ 5. 用户确认 → confirmQuotationUpload(file, projectId) ──► POST /api/quote/confirm-upload
  │                                                              再次 process_upload + 落 DB
  │                                                              (QuotationRepository.create / save_items)
  ▼
```

要点：
- **前端不做任何 Excel 解析**（机制 A 中）。前端只负责文件上传、展示解析结果、让用户选 L6 候选、最终确认。
- 真正的解析、字段抽取、价格富化、L6 匹配**全部在后端**用 `pandas` + 正则完成。
- 同一个文件会被解析**两次**：`parse-preview` 一次（预览），`confirm-upload` 一次（落库）。两次都调用 `QuoteService.process_upload`，是幂等的纯解析。

### 1.2 三个上传端点的差异（`backend/app/api/quote.py`）

| 端点 | 函数 | 是否落库 | 用途 |
|------|------|---------|------|
| `POST /api/quote/parse-preview` | `parse_preview` | 否 | 抽屉预览用，只返回结构化 JSON |
| `POST /api/quote/confirm-upload` | `confirm_upload` | 是（创建 quotation + save_items） | 抽屉"确认创建报价单"按钮 |
| `POST /api/quote/upload-to-opportunity` | `upload_to_opportunity` | 是 | 直接上传到指定商机并建报价单 |
| `POST /api/quote/upload` | `upload_and_parse` | 否（旧版） | 旧入口，仅解析不入库 |

通用校验：扩展名必须 `.xlsx`/`.xls`；大小上限 **50MB**（`quote.py:56`）；中文文件名会尝试 `gbk/gb2312/latin1` 重编码修复（`quote.py:34-50`）。

---

## 2. 后端解析的核心：`PricingEngine`

`QuoteService.process_upload`（`quote_service.py:44`）的骨架：

```python
with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
    tmp.write(file_content)
    sheet_dict = pd.read_excel(tmp_path, sheet_name=None, header=None)  # 关键：无表头、全单元格读入
    configs, first_meta = self.engine.parse_file(sheet_dict)            # 拆 CFG + 解析
    for cfg_name, cfg_data in configs.items():
        enriched_df = self.engine.enrich_config(items_df, cfg_data['meta'])     # KP 价格匹配
        l6_price, l6_record = self.engine.match_l6_total(cfg_data['meta'])      # L6 五维匹配
        ... # 价格计算、汇总、质保信息解析
    return {"status": "success", "configs": result_configs}
```

注意 `pd.read_excel(..., header=None)`：DataFrame 不把任何行当表头，**所有定位都靠关键词锚点 + 列字母**，不靠列名。

---

## 3. 多配置（CFG）拆分逻辑

**结论：一个工作表（Sheet）= 一个配置（CFG）。** 拆分发生在 `PricingEngine.parse_file`（`pricing_engine.py:227`）：

```python
def parse_file(self, sheet_dict: dict) -> tuple:
    for sheet_name, df in sheet_dict.items():
        if '原始需求' in sheet_name or 'Reference' in sheet_name or df.empty:
            continue                       # 跳过参考表/空表
        meta = self._extract_meta(df)
        items = self._parse_items(df)
        if items.empty:
            continue
        configs[sheet_name] = {'meta': meta, 'items': items}   # sheet 名即 CFG 名
```

要点：
- **CFG 名 = 工作表名**。前端 `UploadPreviewDrawer.vue` 的多配置 Tab（`configKeys`）直接来自返回的 `configs` 键，也就是 sheet 名。
- 名字里含 `原始需求` 或 `Reference` 的表会被当参考表跳过。
- 某个 sheet 解析不出任何 item（`items.empty`）会被丢弃。
- 因此"多配置"完全由 Excel 自身有几个有效 sheet 决定，没有额外配置项控制拆分。

---

## 4. 区域识别锚点机制（核心算法）

文件：`backend/app/engine/pricing_engine.py`

### 4.1 表头区域（meta）识别：`_extract_meta`（行 344）

策略是"**关键词扫描 + 取右侧首个非空值**"，不依赖固定单元格坐标：

- 内嵌函数 `find_keyword_value(keyword, max_rows=10)`：
  - 在**前 10 行 × 前 10 列**范围内逐格找包含 `keyword`（小写包含匹配）的单元格；
  - 找到后，从该格**向右扫描**，取第一个非空、非 `nan/none` 的值作为该字段值。
- 抽取的表头字段（多语言关键词回退）：
  - `opportunity_name` ← `Project Name` 或 `商机名称`
  - `model_name` / `model_qty` ← `Model` 或 `型号`（用正则 `\((\d+)` 提取括号内数量）
  - `fae` ← `FAE`
  - `l6_desc` ← `L6 Description` / `PRODUCT SPEC` / `产品规格`（长度需 >10）
  - `date` ← `Date` / `日期`

**L6 五维匹配信息**（chassis / model_type / drive_bays / psu / motherboard）从正文行扫描，而非表头：
- `chassis_form`：从 `l6_desc` 里正则 `(\d+(?:\.\d+)?)\s*U` 提取，如 `2U`。
- `l6_model_type`：`l6_desc` 含 `switch`（忽略大小写）→ `Switch机型`。
- `drive_bays`：从第 4 行起扫 D 列，找含 `backplane` 的行，E 列值用 `^(\d+)\*` 提取盘位数。
- `psu`：找 D 列含 `power supply` 的行，E 列取 `\d+W`、F 列取数量，拼成 `650W * 2`。
- `motherboard`：找 D 列等于 `cpu` 的行，E 列 CPU 型号，再用 `_mb_mappings`（CPU 特征→主板型号，可配置）匹配，如 `AMD/EPYC/INTEL/XEON → TTY TG658V3`。

兜底：若 `opportunity_name`/`model_name` 没抽到，回退到硬编码坐标 `df.iloc[1,3]`、`df.iloc[2,3]`（行 503-522）。

抽不到的关键维度会写进 `meta['warnings']`（如 `CHASSIS_FORM`、`PSU`、`MOTHERBOARD`），供前端提示。

### 4.2 数据区域识别：`_find_region_row`（行 528）——三遍匹配

定位 L6 / KP / Warranty 三个数据段都用这个函数。给定逗号分隔的关键词串，**三遍（pass）逐步放宽**：

1. **第一遍 词边界匹配**：`re.search(r'\b' + 关键词 + r'\b', 单元格文本小写)`。例如 `L6` 不会误命中 `L6XXX` 之外的词。
2. **第二遍 子串匹配**：直接 `关键词 in 单元格文本`。
3. **第三遍 模糊匹配（容错）**：对**长度 ≥4 字符**的关键词，按单元格里的每个英文单词计算与关键词的**莱文斯坦编辑距离 ≤2** 即命中。用于容忍拼写错误（如 `Keypart`/`Keyparts`）。短关键词（≤3 字符）跳过此遍，避免误报。

扫描范围：从 `start_row` 到表末，每行**前 10 列**。返回首个命中行号，未命中返回 `-1`。

### 4.3 数据项抽取：`_parse_items`（行 608）

按顺序识别三段，**前一段的 end 即下一段的 start**，避免重复扫全表：

```
L6 区:   start = find(L6)                      end = find(Keyparts,KP, start+1)
KP 区:   start = L6的end (若≥0，否则再find)     end = find(Warranty,Total, start+1)
Warranty 区: start = find(Warranty, kp_start+1) end = find(Total,Total Price, start+1)
```

每个区域确定 `[start+1, end-1]` 为数据行范围（跳过关键词/表头行），按 `field_mapping` 指定的列字母逐行抽取。若 `end == -1`（没找到结束关键词），数据行延伸到表末。

---

## 5. `field_mapping` 配置（列映射）

### 5.1 数据结构

`field_mapping` 是一个 **"字段名 → 列字母"** 的 JSON 对象，与 `region_start_keywords` / `region_end_keywords` 一起组成一个区域配置：

```json
// L6 区域（默认）
{
  "region_start_keywords": "L6",
  "region_end_keywords": "Keyparts,KP",
  "field_mapping": { "catalogue": "D", "description": "E", "quantity": "F" }
}

// KP 区域（默认）
{
  "region_start_keywords": "Keyparts,KP",
  "region_end_keywords": "Warranty,Total",
  "field_mapping": { "catalogue": "D", "model": "E", "quantity": "F", "price": "G" }
}
```

字段含义（以 KP 为例）：
- `catalogue`（D 列）：配件类别名，如 `CPU`、`Memory`，写入结果的 `part_name`。
- `model`（E 列）：型号/规格描述，写入 `spec`。
- `quantity`（F 列）：数量，写入 `qty`（解析失败默认 1）。
- `price`（G 列）：单价。**支持 Excel 公式**：若值以 `=` 开头，用 `_safe_eval_math`（行 45，基于 AST 的安全算术求值，仅允许 `+ - * /` 和括号、不支持 `**`，防 DoS）计算结果。

列字母 → 列下标由 `_col_letter_to_index`（行 600，**0-based**：A=0, B=1, …, Z=25, AA=26）转换。

> 注意：导出（写 Excel）阶段用的是另一个 `_col_letter_to_idx`（行 1610，**1-based**），两者别混淆。

### 5.2 存储位置与加载链路

- 物理存储：**SQLite**，路径 `{DATA_PATH}/Reference/rules.db`（`backend/app/models/base.py:34`）。
  - 默认 `DATA_PATH = D:\Quotation_Automation`（`backend/app/core/config.py:15`），即 `D:\Quotation_Automation\Reference\rules.db`。
- 表结构（`backend/app/models/rules.py`）：
  - `l6_region_config`：`id, region_start_keywords, field_mapping(JSON 文本), region_end_keywords`
  - `kp_region_config`：结构同上
  - `kp_category_mapping`：`keyword → category`（KP 配件归类）
  - `motherboard_mapping`：`cpu_feature → motherboard_model`
  - `matching_rules`：通用键值对（L6 匹配维度、阈值、模糊规则、数字精度等）
- 加载：`PricingEngine._load_rules()`（行 132）在构造时读取上述表，**读不到则用硬编码默认值**（行 135-157）。`field_mapping` 在 DB 里是 JSON 字符串，读取时 `json.loads`；解析失败再退回硬编码（`_parse_items` 行 619-632 有二次兜底）。
- 初始化默认值：`POST /api/rules/init-defaults`（`rules.py:294`）可一键写入默认区域配置与 KP 分类映射。

### 5.3 修改入口（API）

`backend/app/api/rules.py`：
- `GET/POST /api/rules/l6-region-config`
- `PUT /api/rules/l6-region-config/{id}`
- `GET/POST /api/rules/kp-region-config`
- `PUT /api/rules/kp-region-config/{id}`
- KP 分类映射、主板映射、通用 `matching_rules` 均有对应增删改查端点。

> 说明：前端 `MatchingRulesConfig.vue` 主要配置 **L6 五维匹配维度、主板降级、机箱模糊**（即 `matching_rules` 表），而 `field_mapping` / 区域关键词的编辑界面在当前路由树里没有单独入口（旧 `/rules` 已重定向到 `/parse-template`，但 `/parse-template`（`ParseTemplateEditor.vue`）编辑的是**前端 localStorage 模板**，见第 8 章，二者不要混淆）。要改后端 `field_mapping`，目前最直接的方式是调上述 `/api/rules/*-region-config` 接口或直接改 `rules.db`。

---

## 6. 识别出的字段 → 内部数据结构

### 6.1 单个 item 的形状

`_parse_items` 把每一行抽成如下 dict（`pricing_engine.py:663 / 717 / 752`）：

```python
# L6 行
{ "category": "L6",
  "part_name": <catalogue>, "spec": <description>, "qty": <int>,
  "confirmed_price": None, "currency": "RMB" }

# KP 行
{ "category": "Key Parts",
  "part_name": <catalogue>, "spec": <model>, "qty": <int>,
  "confirmed_price": <price 或公式结果>, "currency": "USD"|"RMB" }   # USD 判定：cpu/processor 且型号含 usd/$

# Warranty 行（列写死：C 列类型、D 列描述）
{ "category": "Warranty",
  "part_name": <C列类型>, "spec": <D列描述>, "qty": 1,
  "confirmed_price": None, "currency": "RMB",
  "warranty_years": <从描述正则 "质保(\d+)年" 提取，可为 None> }
```

### 6.2 富化与价格计算（`quote_service.py:56-168`）

每个 item 经 `enrich_config`（`pricing_engine.py:768`）补上：
- `db_price`：KP 行用 `part_name` 在 KP 价格库精确查；查不到再用 `spec` 模糊匹配。
- `match_status`：与库价比对——`✅ 一致` / `⚠️ 差异` / `⚠️ 待填入` / `❌ 缺失` / `🆕 新部件`。差异阈值 `_price_diff_threshold` 默认 0.01，可配。
- `base_price`、`is_usd_cpu`、`profit_margin`（默认取 `config.json` 的 `profit_margin*100`）。

随后计算 `final_price`（`quote_service.py:105-116`）：
- RMB：`base * (1 + margin/100)`
- USD CPU：`base * usd_to_rmb * (1 + tax_rate) * (1 + margin/100)`
- 税率、汇率、利润率取自 `{DATA_PATH}/config.json`（默认 `tax_rate=0.13, usd_to_rmb=7.0, profit_margin=0.1`）。

L6 整机价由 `match_l6_total`（行 825）按五维（`chassis/model/drive_bays/psu/motherboard`，可配）匹配 L6 价格库，命中后把整机价赋给**第一条 L6 行**的 `base_price`，其余 L6 子项标记"已包含在整机价格中"。

### 6.3 最终返回结构

`process_upload` 返回（`quote_service.py:170`）：

```json
{
  "status": "success",
  "configs": {
    "<sheet名>": {
      "items": [ ...上面每个 item 的 dict... ],
      "summary": { "l6_total", "kp_total", "warranty_total", "grand_total" },
      "l6_matched_record": { ...含 match_score/matched_dims/match_type... },
      "l6_meta": { ..._extract_meta 抽出的维度与 warnings... },
      "warranty_info": { "l6": {...}, "kp": {...} }
    }
  }
}
```

落库时（`confirm-upload` / `upload-to-opportunity`），所有 config 的 items 被拍平，每条加上 `config_name = sheet名`，一次性 `QuotationRepository.save_items` 写入（`quote.py:124-133`）。

---

## 7. 已知边界情况与容错处理

| 场景 | 代码处理 | 位置 |
|------|---------|------|
| 中文文件名在 Windows multipart 下乱码 | 尝试 `gbk/gb2312/latin1` 重解码 | `quote.py:34-50` |
| 文件 >50MB | 413 拒绝 | `quote.py:56` |
| 非 `.xlsx/.xls` | 400 拒绝 | `quote.py:52` |
| sheet 名含 `原始需求`/`Reference` 或空表 | 跳过，不当 CFG | `pricing_engine.py:232` |
| 某 sheet 解析不到任何 item | 丢弃该 config；全部为空则返回 `{"status":"error","message":"No valid configs found"}` | `pricing_engine.py:236`, `quote_service.py:53` |
| 区域起始关键词找不到 | 该区域整体跳过（`l6_start<0` 则不抽 L6） | `pricing_engine.py:643` |
| 区域结束关键词找不到 | 数据行延伸到表末（`end==-1` 时 `end_row=len(df)`） | `pricing_engine.py:644` |
| 关键词拼写误差 ≤2（≥4 字符） | 第三遍模糊匹配兜底 | `pricing_engine.py:580-596` |
| `field_mapping` 在 DB 里非法 JSON | `json.loads` 失败回退硬编码默认列 | `pricing_engine.py:619-632` |
| 数量列解析失败 | `qty` 默认 1 | `pricing_engine.py:656-658` |
| KP 价格是 Excel 公式（`=...`） | `_safe_eval_math` 安全求值（禁 `**`） | `pricing_engine.py:696-699`, 行 45 |
| L6 五维全空 / 部分缺失 | 先按配置维度精确→主板降级→机箱模糊→降级维度→最终返回最佳部分匹配（Top3）供前端选 | `pricing_engine.py:825-977` |
| meta 关键维度抽不到 | 写入 `meta['warnings']`；表头字段兜底硬编码坐标 `iloc[1,3]/iloc[2,3]` | `pricing_engine.py:419-500`, 行 503 |
| DataFrame 列数不足访问列字母 | 越界保护 `if col < df.shape[1]` | `pricing_engine.py:651` |
| `pd.isna` / NaN 进 JSON | `enrich_config` 末尾统一 `fillna`（对象列→空串，数值列→0） | `pricing_engine.py:816-821` |
| 临时文件清理 | `finally: os.remove(tmp_path)` | `quote_service.py:181` |

---

## 8. 前端独立模板解析器（机制 B，与上传链路无关）

仅服务 `/excel-parser` 路由（`ExcelParser.vue`），是一个"选模板→传文件→看结果/导出 JSON"的离线工具。

涉及文件：
- `frontend/src/utils/excel-parser.ts` —— 解析引擎（exceljs）
- `frontend/src/types/parseTemplate.ts` —— 类型定义
- `frontend/src/store/parseTemplate.ts` —— Pinia store，模板持久化在 **`localStorage` 键 `parseTemplates`**
- `frontend/src/views/ExcelParser.vue` —— 工具页
- `frontend/src/views/ParseTemplateEditor.vue` —— 模板编辑页（`/parse-template`）

### 8.1 模板结构（`ParseTemplate`）

```ts
{
  id, name, description, createdAt,
  staticBindings: CellBinding[],     // 精确单元格绑定
  dynamicRegions: DynamicRegion[],   // 关键词定位的区域
  kpCategoryMappings: [...]
}
```

- **静态字段 `CellBinding`**（`types/template.ts:70`）：`{ sheetName, cellAddress(如"D2"), fieldKey, dataType }`，直接按坐标读单格。
- **动态区域 `DynamicRegion`**：`{ name, startKeywords, endKeywords, fieldMapping: {字段:列字母} }`。

默认模板（`store/parseTemplate.ts:109` `seedDefaultTemplate`，基于 `CFG详细表-7.xlsx`）：静态字段绑定 `CFG2` 表的 `A1/D2/D3/I2/I3/I4/E4/H26`；两个动态区域 `L6明细`（start `Catalogue`/end `Keyparts`）和 `Keyparts明细`（start `Component Description`/end `Warranty`）。

### 8.2 解析算法（`excel-parser.ts`）

- `parseExcelByTemplate(buffer, template)`（行 168）主入口：先 `parseStaticBindings` 按坐标读静态字段，再对每个 `dynamicRegions` 调 `parseDynamicRegion`。
- 区域定位 `findRegionBounds`（行 51）：逐行把整行单元格文本拼接，用 `matchesKeywords`（逗号关键词、小写子串匹配）判定起止行。**比后端简单：无词边界、无模糊匹配**。
- 数据行范围 `[startRow+1, endRow-1]`，按 `fieldMapping` 列字母读值；全空行跳过。
- `parseExcelRawData`（行 192）：仅用于原始预览，按单元格全部读出。

> 这套模板与后端 `rules.db` 的区域配置是**两套独立数据**：前端模板存浏览器 `localStorage`，后端规则存 SQLite。修改其中一个不会影响另一个。机制 B 不参与生产上传链路，仅当你在 `/excel-parser` 页手动解析时才被使用。

---

## 9. 热力图预览（前后端桥接，调试用）

`POST /api/rules/parse-preview`（`rules.py:109`）→ `PricingEngine.preview_parse`（`pricing_engine.py:243`）：
- 输入：单个 Excel 文件 + 可选 `template_config`。
- 输出：`{ grid: 二维数组, max_row, max_col, cell_marks: [...], meta }`。
- `cell_marks` 标注每个单元格被识别成了什么——`meta`（表头抽取）、`l6_region`/`kp_region`（区域及其字段）、`kp_category`（KP 分类关键词命中）、`extracted`（实际取值）。
- 用途：在管理页可视化"后端规则会把哪些单元格当成什么"，便于调试 `field_mapping` 与关键词配置。

---

## 10. 关键文件速查表

| 关注点 | 文件 | 关键符号 |
|--------|------|---------|
| 上传 API | `backend/app/api/quote.py` | `parse_preview` / `confirm_upload` / `upload_to_opportunity` |
| 解析编排 | `backend/app/services/quote_service.py` | `QuoteService.process_upload` |
| **解析核心算法** | `backend/app/engine/pricing_engine.py` | `parse_file` / `_extract_meta` / `_find_region_row` / `_parse_items` / `enrich_config` / `match_l6_total` / `preview_parse` |
| 区域/字段配置模型 | `backend/app/models/rules.py` | `L6RegionConfig` / `KPRegionConfig` / `KPCategoryMapping` / `MotherboardMapping` / `MatchingRule` |
| 配置存取 | `backend/app/repository/rules_repo.py` | `get_l6_region_config` / `get_kp_region_config` / ... |
| 规则 API | `backend/app/api/rules.py` | `/l6-region-config` / `/kp-region-config` / `/init-defaults` / `/parse-preview` |
| 数据库路径 | `backend/app/models/base.py` | `RULES_DB_PATH = {DATA_PATH}/Reference/rules.db` |
| 全局参数 | `{DATA_PATH}/config.json` | `tax_rate` / `usd_to_rmb` / `profit_margin` |
| 前端上传组件 | `frontend/src/components/UploadPreviewDrawer.vue` | `loadPreview` / `handleConfirm` |
| 前端 API 客户端 | `frontend/src/api/quote.ts` | `parseQuotationPreview` / `confirmQuotationUpload` |
| 前端独立解析器 | `frontend/src/utils/excel-parser.ts` | `parseExcelByTemplate` / `parseExcelRawData` |
| 前端模板类型/store | `frontend/src/types/parseTemplate.ts`、`frontend/src/store/parseTemplate.ts` | `ParseTemplate` / `seedDefaultTemplate` |

---

## 11. 修改解析规则的速查指南

**想改"上传报价单"的解析行为（生产链路）：**
1. 改区域关键词或列映射 → 调 `PUT /api/rules/l6-region-config/{id}` 或 `/kp-region-config/{id}`，或直接改 `rules.db` 的 `l6_region_config`/`kp_region_config` 表，或调 `POST /api/rules/init-defaults` 重置。
2. 改 KP 配件归类 → `kp_category_mapping` 表 / 对应 API。
3. 改 CPU→主板映射 → `motherboard_mapping` 表 / `MatchingRulesConfig.vue`。
4. 改 L6 匹配维度/模糊/降级 → `matching_rules` 表（`l6_match_dimensions`、`allow_chassis_fuzzy`、`chassis_fuzzy_rules`、`allow_motherboard_fallback` 等）。
5. 改税率/汇率/利润率 → `{DATA_PATH}/config.json`。
6. 改硬编码兜底（如表头关键词、坐标兜底、维度抽取正则）→ 改 `pricing_engine.py` 的 `_extract_meta` 与 `_load_rules` 默认值。

**想改 `/excel-parser` 工具页的解析：**
- 改前端 `localStorage` 里的模板（在 `/parse-template` 页编辑），或改 `store/parseTemplate.ts` 的 `seedDefaultTemplate`、`utils/excel-parser.ts` 的算法。**与后端无关。**
