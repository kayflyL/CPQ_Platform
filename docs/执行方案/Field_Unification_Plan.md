# 字段统一方案
时间：2026.7.14 10:00

> 消除系统中各页面各自硬编码字段的问题，实现"一处定义，多处使用"。
> 创建日期：2026-07-14 | 状态：待实施

## 问题诊断

### 核心问题

同一个业务概念（如 `customer_name`、`platform_type`）在多个页面/模块中各自定义了一套，导致：
- **不一致**：`admin.py` 的 metadata-fields 有 13 个字段，`opportunity_repo.py` 有 14 个，两者不完全一样
- **重复维护**：改一个字段名要改 3-4 个文件
- **无法统一管理**：字段管理页面定义了 37 个字段，但没有一个页面用它

### 硬编码重复清单

| 硬编码内容 | 出现位置 | 重复次数 |
|---|---|---|
| **商机级字段**（customer_name 等 16 个） | `UniverTemplateEditor.vue:750`, `OpportunityDetail.vue:387`, `admin.py:19`, `opportunity_repo.py:152` | **4处** |
| **type_keywords**（cpu/memory/gpu 等 8 类关键词） | `template_filler.py:403`, `pricing_engine.py:1903` | **2处** |
| **KP 分类映射**（18 条 keyword→category） | `pricing_engine.py:142`, `startup.py:44`, `rules.py:319` | **3处** |
| **主板映射**（7 条 cpu→motherboard） | `pricing_engine.py:155`, `startup.py:70`, `rules.py:343` | **3处** |
| **L6/KP 区域配置**（field_mapping） | `pricing_engine.py:132`, `startup.py:24`, `rules.py:303` | **3处** |
| **L6 匹配维度**（chassis/model/drive_bays 等） | `pricing_engine.py:164`, `startup.py:86` | **2处** |
| **匹配维度**（5 个） | `MatchingRulesConfig.vue:84`, `MatchingRulesConfig.vue:170` | **2处** |
| **数据源子字段**（56 个） | `UniverTemplateEditor.vue:1088` | **1处**（但量大） |
| **组件映射**（10 个组件类型） | `template_filler.py:491` | **1处** |

### 已有但未使用的统一字段系统

`BusinessField` 表（`kp_data.db`）已有 **37 个字段**，覆盖所有业务实体：
- opportunity: 12 个 | item: 9 个 | l6: 8 个 | kp: 4 个 | system: 3 个 | config: 1 个
- 完整分类体系：category / source / group_name / display_type / permission
- 完善功能：审计、引用追踪、使用统计、导入导出、验证

**但没有任何页面调用它。**

## 处理方案

### 三层架构

```
┌─────────────────────────────────────────────────┐
│  各业务页面（解析模板 / 工作台 / 导出模板 / ...）  │  ← 消费方
│  统一调用 useBusinessFields(scope) 获取字段       │
├─────────────────────────────────────────────────┤
│  统一字段服务 API                                 │  ← 服务层
│  GET /api/fields?scope=export_template           │
│  GET /api/fields?scope=parse_template            │
│  GET /api/fields?scope=workbench                 │
│  GET /api/fields/dynamic-sources                 │
│  GET /api/fields/type-keywords                   │
├─────────────────────────────────────────────────┤
│  BusinessField 表（已有 37 个字段）               │  ← 数据层
│  + scope 字段实际赋值                             │
│  + dynamic_source 配置                            │
│  + type_keywords / component_mapping 入库         │
└─────────────────────────────────────────────────┘
```

### 分步实施计划

#### 第一步：扩展 BusinessField 系统

- 给 37 个字段设置正确的 `scope`（如 `export_template`, `parse_template`, `workbench`, `opportunity_detail`）
- 一个字段可属于多个 scope（如 `customer_name` 在所有页面都用）
- 新增 API：`GET /api/fields?scope=xxx` 按使用场景过滤

#### 第二步：动态数据源入库

- 将 `dataSourceFields`（56 个子字段）和 `dynamicSourceMap`（4 个数据源）存入数据库
- 方案选择：
  - **方案 A**：在 BusinessField 表中用 `category='dynamic_source'` + `group_name='l6_details'` 组织
  - **方案 B**：新建 `dynamic_source_fields` 表（待确认）

#### 第三步：后端硬编码入库

- `type_keywords` → 存入 rules 表或新建 `field_config` 表
- `component_mapping` → 同上
- KP 分类映射、主板映射 → **已在 rules 表中**，只需让 `pricing_engine.py` 从 rules 读取而非用硬编码 fallback
- L6 匹配维度 → 同上

#### 第四步：前端页面改造

| 页面 | 改动 | 文件 |
|---|---|---|
| UniverTemplateEditor | 删除 21 个硬编码字段 + 56 个子字段，改为调用 `useBusinessFields('export_template')` | `views/univer/UniverTemplateEditor.vue` |
| OpportunityDetail | 删除 `infoFields`，改为调用 `useBusinessFields('opportunity_detail')` | `views/opportunity/OpportunityDetail.vue` |
| TemplateEditor | 已在用 store 动态字段，确认一致性即可 | `views/TemplateEditor.vue` |
| MatchingRulesConfig | 从 rules API 获取匹配维度 | `views/admin/MatchingRulesConfig.vue` |

#### 第五步：后端引擎改造

| 模块 | 改动 | 文件 |
|---|---|---|
| pricing_engine | 删除硬编码 fallback，从 rules 表读取配置 | `engine/pricing_engine.py` |
| template_filler | `type_keywords` 和 `component_mapping` 从 DB 读取 | `services/template_filler.py` |
| admin API | `metadata-fields` 改为从 BusinessField 表查询 | `api/admin.py` |

### 实施优先级

| 优先级 | 改什么 | 原因 |
|---|---|---|
| 🔴 P0 | UniverTemplateEditor 的 21+56 个硬编码字段 | 量最大，且已有字段管理系统不用 |
| 🔴 P0 | pricing_engine.py 的 3 处重复 fallback | 核心引擎，改一处等于清理三处 |
| 🟡 P1 | template_filler.py 的 type_keywords + component_mapping | 导出功能的核心 |
| 🟡 P1 | OpportunityDetail 的 infoFields | 与 UniverTemplateEditor 大量重复 |
| 🟢 P2 | admin.py 的 metadata-fields | 改为从 BusinessField 查询即可 |
| 🟢 P2 | MatchingRulesConfig 的 matchDimensions | 量小，影响有限 |

## 设计决策（已确认）

### 决策 1：动态数据源子字段 → 新建表

新建 `dynamic_source_fields` 表，独立于 BusinessField。

```sql
CREATE TABLE dynamic_source_fields (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key  TEXT NOT NULL,        -- 数据源标识：l6_details / kp_details / config_summary
    field_key   TEXT NOT NULL,        -- 子字段 key：item_no / part_name / spec / qty ...
    field_label TEXT NOT NULL,        -- 显示名称：序号 / 零件名称 / 规格 / 数量 ...
    sort_order  INTEGER DEFAULT 0,
    enabled     BOOLEAN DEFAULT 1,
    UNIQUE(source_key, field_key)
);
```

初始数据（42 条，来自 `UniverTemplateEditor.vue:1088-1146`）：
- `l6_details`：14 个子字段（item_no, part_name, spec, qty, base_price, confirmed_price, final_price, unit_price, profit_margin, description, config_name, model_name, server_model, category）
- `kp_details`：14 个子字段（同上）
- `config_summary`：7 个子字段（seq, config_name, server_model, description, unit_price, qty, total_price）

### 决策 2：scope 按业务域分 + 页面标注

BusinessField 表的 `scope` 字段按**业务域**划分：

| scope 值 | 含义 | 涉及的页面/功能 |
|---|---|---|
| `opportunity` | 商机域 | 商机列表、商机详情、回收站 |
| `config` | 配置域 | 报价工作台（配置明细） |
| `pricing` | 定价域 | L6 定价、KP 定价、匹配规则 |
| `export` | 导出域 | 导出模板编辑器（Univer） |
| `parse` | 解析域 | 解析模板编辑器 |
| `system` | 系统域 | 系统设置、导出日期等 |

同时新增 `used_in_pages` 字段（TEXT，JSON 数组），标注该字段具体用在哪些页面：

```sql
ALTER TABLE business_fields ADD COLUMN used_in_pages TEXT DEFAULT '[]';
-- 示例值：'["opportunity_detail","export_template","workbench"]'
```

这样既能按业务域筛选，又能精确知道每个字段在哪些页面使用。
