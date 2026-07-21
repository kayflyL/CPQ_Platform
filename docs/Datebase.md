# 数据库

> 更新：2026-07-20 | 引擎：**PostgreSQL**（0.1.12 从 SQLite 迁来，单库多 schema）

## 总览

CPQ 后端用**单个 PostgreSQL 数据库**，按业务域拆成 **7 个 schema** 做逻辑隔离（取代旧版的多个 SQLite `.db` 文件，项目里已无 `.db`）。

- 连接串：`backend/app/core/config.py` 的 `DATABASE_URL`（由 `POSTGRES_HOST/PORT/USER/PASSWORD/DB` 环境变量拼接）
- Engine + 各 schema SessionLocal 工厂：`backend/app/models/base.py`
  - 单 `engine = create_engine(DATABASE_URL, pool_size=20, pool_pre_ping=True)`
  - 每个 schema 派生 `engine.execution_options(schema_translate_map={None: "<schema>"})` + 独立 `sessionmaker`
- Model 显式写 `__table_args__ = {"schema": "..."}`，各 schema 相互独立、不混用

## schema 与表

### `kp` — KP 零件库
规范化 6 表（活跃）：`kp_categories` / `kp_parts` / `kp_part_specs` / `kp_price_history` / `kp_part_compat` / `kp_part_related`；旧表 `kp_records` 保留作备份不再使用。
访问：`KP_SessionLocal`（`kp_repo.py`）

### `l6` — L6 整机 + server-config（最复杂）
- ORM：`l6_records`
- Legacy L6 BOM：`l6_bom_templates` / `l6_bom_parts`
- Legacy L6 机箱库（过渡态，读 `_old` 备份表）：`l6_base_configs_old` / `l6_base_config_parts_old` / `l6_front_panel_items` / `l6_rear_panel_items` / `l6_psu_options`
- 新 server-config 流程：`parts_master` / `base_configs` / `base_config_parts` / `bom_templates` / `config_schemes` / `server_types` / `server_models`
- 大多数 repo 走 `l6_engine` 原生 SQL + `l6.` 前缀

### `opportunities` — 商机线索
`opportunities` / `quotations` / `opportunity_items` / `opportunity_files` / `univer_templates`
访问：`Opportunity_SessionLocal`

### `rules` — 业务规则 + 字段体系
- 解析与匹配规则：`l6_region_config` / `kp_region_config` / `kp_category_mapping` / `matching_rules` / `parse_regions` / `parse_field_rules`
- 字段体系：`business_fields` / `dynamic_source_fields` / `field_references` / `field_audit_logs` / `field_usage_stats`
- 系统：`system_config`
访问：`Rules_SessionLocal`

### `l6_history` — 价格变更历史
`l6_price_history`
访问：`l6_history_engine`（裸连接，见末尾「已知遗留」）

### `public` — 批注
`comments`（商机批注）
访问：`public_engine`（`comment_repo.py` 原生 SQL）

### `parts` — 闲置（迁移中废弃）
`Parts_SessionLocal` 已定义但无 repo 使用。活表 `parts_master` 实际在 `l6` schema。

## 访问方式（两条路径）

| 路径 | 用法 | 适用 repo |
|------|------|----------|
| ORM | repo 绑定对应 `*_SessionLocal`，操作 model | rules / opportunities / kp / business_field / system_config / dynamic_source_field / opportunity_file / univer_template / quotation |
| 原生 SQL | repo 用 `l6_engine` / `l6_history_engine` / `public_engine`，SQL 写 `schema.table` 前缀 | 所有 L6 相关 repo、`comment_repo` |

## 启动建表（`core/startup.init_rules_db`）

FastAPI lifespan 启动时跑：
1. `Base.metadata.create_all(bind=rules_engine)` + `bind=l6_history_engine` 自动建表
2. 空库时种子默认 L6/KP region config、KP category mappings、`system_config` 默认值
3. 清理 24h 以上的临时上传文件

## 已知遗留 / 待修

- **`l6_price_history` schema 矛盾（✅ 已修 2026-07-20）**：原 ORM model 声明 `l6_history` 但 `l6_repo.py` SQL 写 `l6.`（`schema_translate_map` 对显式前缀不生效），`l6.l6_price_history` 实际不存在，导致 `save_history_snapshot` 一直失败、2026-07-04 之后的价格快照全丢。已统一 SQL 到 `l6_history.l6_price_history`，并 `setval` 同步序列（迁移插带 id 数据后序列未 advance）。
- **迁移后序列未同步（✅ 已修 2026-07-20）**：迁移脚本插入带 id 数据后，各表 SERIAL 序列未 advance 到 max(id)，新 INSERT 会撞主键。已用 `scripts/sync_sequences.py` 批量 `setval` 全部 34 个序列到 max+1（幂等，未来再迁数据可重跑）。
- **`Parts_SessionLocal` / `L6History_SessionLocal` 闲置**：`base.py` 定义了 sessionmaker 但无 repo 使用（l6_history 走裸 engine 连接）。
- **Legacy `_old` 表过渡态**：L6 机箱库流程读 `_old` 备份表，与 server-config 新流程（`base_configs` 等）并存。用户定调维持止血、等新流程完整再切，别擅自动。
