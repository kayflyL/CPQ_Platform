# Excel 解析引擎独立化方案
时间：2026.7.14 23:28

## 一、核心思路

**解析 = 区域定位 + 字段映射**

```
Excel 文件
  ├── Header 区域（前N行）──→ 静态字段（opportunity/config 类）
  ├── L6 区域 ──────────────→ 动态字段（l6 类 + item 类）
  ├── KP 区域 ──────────────→ 动态字段（kp 类 + item 类）
  └── Warranty 区域 ────────→ 动态字段（item 类）
```

每条解析规则回答一个问题：**"Excel 哪个位置的什么值 → 对应哪个业务字段"**

所有字段 key 必须来自 `business_fields` 表，不创造新字段。

---

## 二、数据模型（rules.db 新增两张表）

### 表1：`parse_regions` — 定义 Excel 中的逻辑区域

| 列 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| name | string | 区域名：header / L6 / KP / Warranty |
| start_keywords | string | 起始关键词（逗号分隔），header 可为空 |
| end_keywords | string | 结束关键词（逗号分隔），header 必填下一个区域名 |
| skip_header_rows | int | 区域内跳过几行（通常 1，跳过列标题行） |
| sort_order | int | 区域排列顺序 |

### 表2：`parse_field_rules` — 定义字段从哪个区域哪一列取值

| 列 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| field_key | string | 关联 business_fields.key |
| region | string | 所属区域：header / L6 / KP / Warranty |
| source_type | string | `keyword`（静态，按关键词找值）/ `column`（动态，按列取值） |
| source_config | text(JSON) | 提取参数，见下方示例 |
| fallback_config | text(JSON) | 兜底方案（关键词找不到时的固定位置） |
| enabled | bool | 是否启用 |
| sort_order | int | 排序 |

### source_config 示例

```jsonc
// 静态字段（source_type = keyword）
{"keywords": ["Project Name", "商机名称"], "value_offset": 1}
// → 在 header 区域扫描关键词，找到后取右侧第1列的值

// 动态字段（source_type = column）
{"col": "D"}
// → 在 L6 区域逐行读取 D 列的值
```

### 默认数据（对应现有硬编码逻辑）

```
parse_regions:
  header  | start=""            | end="L6"              | skip=0
  L6      | start="L6"          | end="Keyparts,KP"     | skip=1
  KP      | start="Keyparts,KP" | end="Warranty,Total"  | skip=1
  Warranty| start="Warranty"    | end="Total"            | skip=1

parse_field_rules:
  project_name   | header   | keyword | {"keywords":["Project Name","商机名称"],"value_offset":1}
  model_name     | header   | keyword | {"keywords":["Model","型号"],"value_offset":1}
  fae            | header   | keyword | {"keywords":["FAE"],"value_offset":1}
  quotation_date | header   | keyword | {"keywords":["Date","日期"],"value_offset":1}
  description    | header   | keyword | {"keywords":["L6 Description","PRODUCT SPEC","产品规格"],"value_offset":1}
  l6_chassis     | L6       | column  | {"col":"D"}
  spec           | L6       | column  | {"col":"E"}
  qty            | L6       | column  | {"col":"F"}
  kp_category    | KP       | column  | {"col":"D"}
  kp_model       | KP       | column  | {"col":"E"}
  qty            | KP       | column  | {"col":"F"}
  kp_price       | KP       | column  | {"col":"G"}
```

---

## 三、后端拆分

### 新建 `backend/app/engine/excel_parser.py`（~400行）

```
ExcelParser 类
├── __init__(rules_repo, business_field_repo)
├── load_rules()              # 从 DB 加载区域+字段映射规则
├── parse(sheet_dict) → dict  # 完整解析：返回 {static_fields, dynamic_rows}
├── preview(df) → dict        # 热力图预览：返回 {grid, cell_marks, parsed_fields}
├── _locate_regions(df)       # 根据 parse_regions 定位各区域行号
├── _extract_static(df, header_bounds)  # 按 parse_field_rules(static) 提取
├── _extract_dynamic(df, region_bounds) # 按 parse_field_rules(dynamic) 提取
├── _find_region_row(df, keywords, start_row)  # 关键词定位（迁移自 pricing_engine）
└── _safe_eval_math(expr)     # 安全公式计算（迁移）
```

### 返回结构

```python
{
    "static_fields": {
        "project_name": {
            "value": "xxx",
            "source": {"row": 1, "col": 4, "keyword": "Project Name"}
        },
        "fae": {
            "value": "John",
            "source": {"row": 3, "col": 2, "keyword": "FAE"}
        },
        ...
    },
    "dynamic_regions": {
        "L6": [
            {"l6_chassis": "xxx", "spec": "yyy", "qty": 2, "_row": 5},
            ...
        ],
        "KP": [
            {"kp_category": "CPU", "kp_model": "xxx", "kp_price": 1000, "_row": 20},
            ...
        ]
    },
    "unmapped_rows": [...]  # 未匹配到任何区域的行
}
```

每个值都带 `source`（从哪来的），前端可以展示溯源信息。

### pricing_engine.py 瘦身后（~1200行）

```python
class PricingEngine:
    def __init__(self, kp_repo, l6_repo, opportunity_repo, excel_parser, ...):
        self.parser = excel_parser  # 注入，不再自己解析

    def process_upload(self, file_content, filename):
        # 调用 self.parser.parse() 获取结构化数据
        # 然后做价格匹配、商机保存等后续逻辑
```

---

## 四、前端页面

### 路由

`/excel-parser`（替换现有废弃页面）

### 布局

```
┌──────────────────────────────────────────────────────────────────┐
│  Excel 解析服务                                                   │
│  [上传 Excel]  [保存规则]  [重置]                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ 解析规则（上）──────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │  区域配置                                                     │  │
│  │  ┌────────────────────────────────────────────────────────┐  │  │
│  │  │ 区域    │ 起始关键词    │ 结束关键词     │ 跳过行数     │  │  │
│  │  │ header  │              │ L6            │ 0            │  │  │
│  │  │ L6      │ L6           │ Keyparts,KP   │ 1            │  │  │
│  │  │ KP      │ Keyparts,KP  │ Warranty,Total│ 1            │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  │                                                              │  │
│  │  字段映射                                                     │  │
│  │  ┌─ 静态字段 ──────────────────────────────────────────────┐ │  │
│  │  │ 业务字段      │ 区域   │ 提取方式 │ 关键词/列   │ 启用   │ │  │
│  │  │ 项目名称      │ header │ 关键词   │ Project Name│ ✓     │ │  │
│  │  │ FAE          │ header │ 关键词   │ FAE         │ ✓     │ │  │
│  │  │ 报价日期      │ header │ 关键词   │ Date,日期   │ ✓     │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  │  ┌─ 动态字段 ──────────────────────────────────────────────┐ │  │
│  │  │ 业务字段      │ 区域   │ 提取方式 │ 关键词/列   │ 启用   │ │  │
│  │  │ L6-机箱       │ L6     │ 列      │ D           │ ✓     │ │  │
│  │  │ L6-型号       │ L6     │ 列      │ E           │ ✓     │ │  │
│  │  │ 数量          │ L6     │ 列      │ F           │ ✓     │ │  │
│  │  │ KP-型号       │ KP     │ 列      │ E           │ ✓     │ │  │
│  │  │ KP-价格       │ KP     │ 列      │ G           │ ✓     │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ 解析预览（下）──────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │  ┌─ 热力图（左）──────────┐  ┌─ 解析结果（右）────────────┐  │  │
│  │  │                        │  │                            │  │  │
│  │  │  Excel 原始内容         │  │  📋 静态字段               │  │  │
│  │  │  每个被读取的单元格      │  │  项目名称: xxx ← D3       │  │  │
│  │  │  都标注映射到哪个字段    │  │  FAE: John ← C5           │  │  │
│  │  │                        │  │                            │  │  │
│  │  │  颜色区分：             │  │  📦 L6 区域 (3行)          │  │  │
│  │  │  绿=静态字段来源        │  │  机箱  │ 型号 │ 数量        │  │  │
│  │  │  蓝=L6区域             │  │  xxx   │ yyy  │ 2           │  │  │
│  │  │  橙=KP区域             │  │  ...                       │  │  │
│  │  │  灰=未识别              │  │                            │  │  │
│  │  │                        │  │  🔧 KP 区域 (8行)          │  │  │
│  │  │  点击单元格 →           │  │  分类  │ 型号 │ 价格        │  │  │
│  │  │  "绑定到字段..."        │  │  CPU   │ xxx  │ 1000        │  │  │
│  │  │                        │  │  ...                       │  │  │
│  │  └────────────────────────┘  └────────────────────────────┘  │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 交互

1. **修改规则** → 防抖 500ms 自动重新解析 → 热力图和结果同步刷新
2. **点击热力图单元格** → 弹出菜单：「绑定到字段...」→ 从 business_fields 列表中选择
3. **解析结果中每个值可溯源**：鼠标悬停显示"来自 Sheet1 D5 单元格，关键词 'Project Name' 匹配"
4. **字段下拉框直接关联 business_fields**：不创造新字段，选什么就是什么

---

## 五、与现有系统的关系

```
                    ┌─────────────────────┐
                    │   business_fields   │ ← 字段定义中心
                    │   (kp_data.db)      │
                    └────────┬────────────┘
                             │ field_key
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ excel_parser│  │ pricing     │  │ export      │
    │ (解析规则)   │  │ engine      │  │ templates   │
    │             │  │ (价格匹配)   │  │ (导出绑定)   │
    │ 读 Excel →  │  │             │  │             │
    │ 结构化数据   │  │ 结构化数据 → │  │ 结构化数据 → │
    │             │  │ 报价计算     │  │ Excel 输出   │
    └─────────────┘  └─────────────┘  └─────────────┘
```

三个消费者共用同一套字段定义，解析引擎是**数据入口**。

---

## 六、改动清单

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `backend/app/models/rules.py` | 新增 ParseRegion、ParseFieldRule 模型 |
| 2 | `backend/app/repository/rules_repo.py` | 新增两张表的 CRUD |
| 3 | `backend/app/engine/excel_parser.py` | **新建**，从 pricing_engine 迁移解析逻辑 + 改造为规则驱动 |
| 4 | `backend/app/engine/pricing_engine.py` | 删除解析方法，注入 ExcelParser |
| 5 | `backend/app/services/quote_service.py` | 适配新结构 |
| 6 | `backend/app/api/rules.py` | 新增 parse_regions / parse_field_rules CRUD API |
| 7 | `frontend/src/views/ExcelParser.vue` | **重写**为解析调试页面 |
| 8 | `frontend/src/router/index.ts` | 路由标题改为「Excel 解析」 |
| 9 | `frontend/src/api/rules.ts` | 新增区域/字段映射 API 调用 |

---

## 七、实施顺序

1. **数据层**：建表 + Repository（步骤 1-2）
2. **引擎层**：新建 excel_parser.py，迁移解析代码，改造为规则驱动（步骤 3）
3. **适配层**：pricing_engine + quote_service 改为注入调用（步骤 4-5）
4. **API 层**：暴露规则 CRUD + 解析预览接口（步骤 6）
5. **前端**：重写 ExcelParser.vue（步骤 7-9）
