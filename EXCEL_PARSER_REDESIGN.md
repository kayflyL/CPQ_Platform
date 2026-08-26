# Excel 解析规则系统化重构

> 状态：已批准，待实施。目标不是修补“新区域无法绑定/预览不显示”，而是消除当前按区域名硬编码和全表重建带来的结构性缺陷。

## 1. 背景与问题

当前实现把 Excel 解析拆成 `parse_regions`（区域定义）和 `parse_field_rules`（字段规则），但两者之间只靠显示名字符串连接，没有稳定 ID 外键，也没有区域类型字段。

### 1.1 用户可见问题
- 左侧新建区域后，字段映射下拉无法绑定到新区域，往往只剩 `header/L6/KP`。
- 即使把新区域命名为 `header`，字段规则看似绑定成功，右侧预览仍不显示新区域。
- 新增区域保存逻辑是“把当前列表整体提交 + 后端删除全表后重建”，容易丢区域或覆盖已有区域。
- 预览图例和区域着色部分写死 `Header/L6/KP/Warranty`。

### 1.2 根因
- 字段规则存的是区域名字符串：`parse_field_rules.region`。
- 解析器按字符串匹配：`r["region"] == region_name`。
- 区域边界以区域名为 key，重名会互相覆盖：`bounds[region_name]`。
- 静态/动态由名字是否等于 `header` 决定，而不是数据字段。
- 前端下拉用 `region.name` 作为 `value`，无法区分同名区域。
- 前端保存新增区域时，打开弹窗未清空编辑态，且使用批量重建接口。

## 2. 设计目标

- 区域是“有身份的对象”，字段规则通过稳定 ID/key 关联区域，改名、重名不断链。
- 静态/动态是区域显式属性，不靠名字猜。
- 区域边界显式、可组合，避免无结束关键词时吞掉后续区域。
- 写接口走标准 CRUD，不再以 UI 写操作为名做全表删除重建。
- 解析、热力图预览、右栏结果三者消费同一份引擎输出，避免各写一套过滤规则。
- 保留当前 `header/L6/KP` 既有配置，迁移可回滚、可验证。

## 3. 目标数据模型

### 3.1 parse_regions
保留：`id`, `name`, `start_keywords`, `end_keywords`, `skip_header_rows`, `sort_order`。
新增：
- `region_key`：稳定唯一标识，前端和字段规则用它引用区域。
- `region_type`：`static` 或 `dynamic`。
- `start_mode`：`keyword` / `row` / `after_previous`，当前先只实现 `keyword`，保留扩展位。
- `end_mode`：`keyword` / `next_region` / `eof` / `row`，当前先实现 `keyword` / `next_region` / `eof`。
- `start_config` / `end_config`：JSON，按 mode 存具体参数。
- `enabled`：区域是否参与解析，默认启用。

约束：
- `region_key` 唯一。
- 同名区域不再依赖 `name` 唯一，但 UI 仍建议显示名唯一，减少误读。

### 3.2 parse_field_rules
保留：`id`, `field_key`, `source_type`, `source_config`, `fallback_config`, `enabled`, `sort_order`。
调整：
- 新增 `region_id`，外键指向 `parse_regions.id`。
- 保留旧 `region` 字符串作为过渡兼容字段，新代码读写 `region_id`。
- 后续稳定后再决定是否删除旧 `region` 字段。

## 4. 解析引擎设计

- 加载区域与字段规则后，按 `sort_order` 排序区域，按 `id` 建立字段规则索引。
- 边界解析统一为：
  1. 计算本区域 start。
  2. 按 `end_mode` 计算 end。
  3. `next_region` 用下一个区域的 start 作为本区域 end；`eof` 用文件末尾；`keyword` 用关键词定位。
  4. `static` 区域只提取静态字段，`dynamic` 区域按字段规则逐行提取。
- 无论区域是否有字段规则，预览模型都要返回区域边界和起止行，供热力图显示。
- 解析结果与预览共用同一份 `RegionBound` 中间结构，避免两套过滤逻辑。
- 取消 `region_name == "header"` 这类硬编码判断，改为 `region_type == "static"`。

## 5. API 设计

- `GET /api/rules/parse-regions`：返回区域，含 `id/name/region_key/region_type/...`。
- `POST /api/rules/parse-regions`：创建单条区域，不再接收全量列表。
- `PUT /api/rules/parse-regions/{id}`：更新单条区域。
- `DELETE /api/rules/parse-regions/{id}`：删除单条区域；若有关联字段规则，按配置阻止或级联。
- `GET /api/rules/parse-field-rules`：返回字段规则，含 `region_id` 和兼容字段 `region`。
- `POST /api/rules/parse-field-rules`：创建单条字段规则。
- `PUT /api/rules/parse-field-rules/{id}`：更新单条字段规则。
- `DELETE /api/rules/parse-field-rules/{id}`：删除单条字段规则。
- 保留 `POST /api/rules/excel-parser-preview`，但返回结构统一为 `preview + parse_result + region_bounds`。

## 6. 前端状态与交互

- 将 `useExcelParser` 的模块级单例改为 Pinia store，或至少保留单例但明确状态所有权。
- 区域下拉使用 `region_id` 作为 value，显示 `region.name`。
- 打开新增弹窗前清空 `editingRegion` 并重置表单。
- 新增区域改为调用单条创建接口，保存成功后重新拉取聚合数据。
- 字段映射表显示区域名，编辑时按 `region_id` 回填。
- 热力图图例根据 `region_bounds` 动态渲染，不再写死。
- 预览右侧的“动态区域”按 `region_type` 和字段规则结果渲染。

## 7. 数据迁移

启动迁移函数在 `backend/app/core/startup.py` 增加幂等 SQL：
- `parse_regions` 增加 `region_key`、`region_type`、`enabled`、边界 mode/config 列。
- 现有 `header` 回填为 `static`，其余回填为 `dynamic`。
- 为现有区域生成稳定 `region_key`（如 `header/l6/kp/warranty`）。
- `parse_field_rules` 增加 `region_id`，按旧 `region` 名称 join 到区域 id。
- 新增唯一索引 `parse_regions(region_key)`。
- 保留旧 `region` 字段，供过渡期兼容读取。

## 8. 实施顺序

1. 设计文档定稿与数据模型确认。
2. 后端模型 + 启动迁移。
3. Repository CRUD 改为按 ID，保留兼容读取。
4. 解析器改为按 `region_type`/`region_id` 解析，统一预览模型。
5. API 改为标准 CRUD，新增 Pydantic 校验。
6. 前端状态、下拉、保存、图例和预览联动。
7. 单测：边界解析、无 end 关键词、字段规则关联、CRUD API、预览结构。
8. 回归：后端测试 + `vue-tsc -b` + 手工上传 Excel 验证。

## 9. 风险与回滚

- 迁移采用幂等 `ADD COLUMN IF NOT EXISTS`，可重复启动。
- 旧字段保留，失败可继续用旧字符串兼容路径。
- 全量重建逻辑移除前先保留旧接口作为兼容层，前端切完后清理。