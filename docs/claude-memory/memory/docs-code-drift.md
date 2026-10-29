---
name: docs-code-drift
description: Docs lag behind code — a project→opportunity (商机) rename + SQLite→PostgreSQL 迁移(0.1.12) 未写入 docs
metadata: 
  node_type: memory
  type: project
  originSessionId: 87da06b3-ff0a-4e80-9ed8-88a272a942b6
  modified: 2026-07-24T07:20:22.732Z
---

项目经历过一次 **"project → opportunity（商机）" 大规模重命名重构**，前后端代码已全部迁移，但 `docs/` 全面滞后：

- 后端：`api/projects.py`→`opportunities.py`、`repository/project_repo.py`→`opportunity_repo.py`、`models/project*.py`→`opportunity*.py`。前端侧边栏已是"商机线索/新建商机/总商机数"。
- **数据库已迁 PostgreSQL**（0.1.12，单库多 schema：`kp`/`l6`/`opportunities`/`rules`/`l6_history`，`backend/app/core/config.py` 的 `DATABASE_URL` 读 `POSTGRES_*`），但 `数据库.md`/`System_Architecture.md` 仍写"SQLite / 5 个独立 .db 库"——双重过时。项目里已无 .db 文件。
- 新增字段管理模块：`models/business_field.py`、`field_reference.py`、`field_audit_log.py`、`field_usage_stats.py`，文档未提。
- `docs/API 路由.md`、`Component_Inventory.md` 仍按旧 projects 体系描述。
- `api/rules.py:150` 有个重命名漏改的局部变量 `project_repo = OpportunityRepository()`（行为正确，仅命名不一致）。

文档同步是独立的较大任务。**2026-07-20 已同步**：`Database.md` + `System_Architecture.md`（PG 单库 7 schema 表清单 + 分层 + 路由 + 请求流，核实自代码）。**仍滞后**：`docs/功能块/Component_Inventory.md`、API 路由文档仍按旧 projects 体系描述。启动相关见 [[app-startup]]。

**2026-07-24 核实**：商机文件物理存储实际在 `backend/storage/{folder_name}/(uploads|exports)`，非 docs 旧写的 `D:\CPQ_Data`。商机文件官方表是 `FeedAttachment`（`opportunities.opportunity_attachments`，UUID storage_key + kind/version/quotation_id），取代旧 `opportunity_files` 扫盘表；两套 API 并存是 tech debt。详情页改造第一期已同步 `docs/frontend-pages/opportunities/detail.md`。**第二期前清理（2026-07-24）**：旧文件系统代码层全删——`/api/opportunities/{id}/files/*` 路由族 + `folder-path`、`OpportunityFile` model + `opportunity_file_repo`、`OpportunityFiles.vue` 组件；`/save` 路由保留数据保存但剥离 temp 文件挪移 + `add_file` 副作用（前端 store 仍传 temp_file，后端忽略）；`FileStorage` 保留（quote/server_catalog/system_config 仍用 save_upload_temp 等）。DB 表 `opportunity_files` 留为死数据，DROP 见 `backend/migrations/drop_opportunity_files.sql`（未执行）。
