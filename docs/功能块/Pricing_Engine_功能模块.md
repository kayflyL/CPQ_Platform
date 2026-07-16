# Pricing Engine 功能模块

核心文件：`backend/app/engine/pricing_engine.py`（1783行）

## 1. Excel 解析

从上传的 Excel 中提取商机数据：

| 功能 | 方法 | 说明 |
|------|------|------|
| 文件解析 | `parse_file()` | 解析多 sheet，提取配置项和元数据 |
| 热力图预览 | `preview_parse()` | 可视化标注 L6/KP 区域和分类关键词 |
| 元数据提取 | `_extract_meta()` | 客户、日期、币种等 |
| 配置项解析 | `_parse_items()` | L6 区域的 catalogue/description/quantity |
| 区域定位 | `_find_region_row()` | 根据关键词定位数据起始行 |

## 2. 价格匹配与同步

| 功能 | 方法 | 说明 |
|------|------|------|
| 配置增强 | `enrich_config()` | 为 L6 项匹配 KP 价格 |
| 价格历史 | `get_kp_price_history()` | 查询 KP 零件历史价格 |
| 价格同步 | `sync_kp_prices_to_db()` | 将 Excel 中的 KP 价格写入价格库 |

## 3. 商机管理

| 功能 | 方法 | 说明 |
|------|------|------|
| 保存商机 | `save_opportunity()` | 持久化配置、描述、数量、机型 |
| 商机详情 | `get_opportunity_details()` | 返回完整商机数据 |
| 更新元数据 | `update_project_meta()` | 修改项目级信息 |

## 4. Excel 导出（报价单生成）

| 功能 | 方法 | 说明 |
|------|------|------|
| 生成报价单 | `generate_excel()` | 按模板填充生成最终 Excel |
| 单元格填充 | `_fill_from_bindings()` | 根据绑定规则写入数据 |
| 配置摘要 | `_build_config_summary()` | 生成配置汇总描述 |
| 描述拼装 | `_build_description_from_parts()` | 按选中零件拼装描述文本 |
| 导出描述 | `_build_export_description()` | 支持循环替换的描述生成 |

## 5. 辅助工具

| 功能 | 方法 | 说明 |
|------|------|------|
| 安全计算 | `_safe_eval_math()` | 防注入的公式计算 |
| 字段映射 | `_map_field_to_value()` | 字段名到值的动态映射 |
| 动态解析 | `_resolve_field_dynamically()` | 含区域数据的字段解析 |
| 区域数据 | `_get_region_data()` | 多配置场景下的数据获取 |

## 数据流

```
上传Excel
    ↓
parse_file() → 提取 L6/KP 数据
    ↓
enrich_config() → 匹配 KP 价格库
    ↓
save_opportunity() → 持久化到 projects.db
    ↓
generate_excel() → 按模板生成报价单
```

## 依赖注入

引擎通过构造函数接收 5 个 Repository，不直接操作数据库：

- `KPRepository` — KP 价格库
- `L6Repository` — L6 配置数据
- `OpportunityRepository` — 商机数据
- `RulesRepository` — 解析规则（可选）
- `UniverTemplateRepo` — 导出模板（可选）
