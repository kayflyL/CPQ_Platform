# 系统架构

> 更新：2026-07-20

## 概述

CPQ Platform = **Vue3 + FastAPI 前后端分离**。后端按 `api → services → repository → models` 分层，外加 `engine`（领域算法）与 `core`（启动/配置）。数据存单库 PostgreSQL（7 schema，见 [数据库.md](Datebase.md)）。

## 后端分层（`backend/app/`）

| 层 | 职责 |
|----|------|
| `api/` | FastAPI 路由 + 内联 Pydantic 请求/响应模型，参数校验与 HTTP 适配 |
| `services/` | 业务编排，组合多个 repo + engine；不直接碰 SQL |
| `repository/` | 数据访问，ORM session 或原生 SQL，按 schema 隔离 |
| `models/` | SQLAlchemy ORM 定义 + 7 个 schema 专属 engine/sessionmaker 工厂（`base.py`） |
| `engine/` | 纯领域算法（定价 / 推导 / Excel 解析），无或仅通过注入 repo 访问 DB |
| `core/` | 启动骨架：`config` / `startup` / `exception_handlers` / `database`（旧 shim） |
| `utils/` | `file_storage.py`（上传/导出文件落盘 + 临时清理） |
| `schemas/` | 空（Pydantic 模型内联在 api 层） |

## 路由模块（`main.py` 注册 20+ router）

- **商机 / 报价**：`quote` / `opportunities` / `quotations` / `dashboard` / `comments`
- **配置 / 料号**：`parts` / `base_configs` / `bom_templates` / `config_schemes` / `server_catalog` / `l6_chassis` / `rear_io` / `derive` / `kp_config`
- **模板 / 字段 / 系统**：`univer_templates` / `fields` / `system_config` / `rules` / `admin`

## 关键模块

**engine/**
- `pricing_engine`（~1060 行）：核心业务逻辑，Excel 生成 + 价格 enrichment，所有数据访问经注入的 repo
- `derivation_engine`：纯算法，按配置状态 + 注入规则推导（盘位种类、GPU 线缆数等），阈值全从规则读、不写死
- `excel_parser`：规则驱动解析，经 `RulesRepository` 读 `parse_regions` / `parse_field_rules`，输出带溯源的白盒结果

**services/**
- `quote_service.QuoteService.process_upload()`：上传报价单主入口，组合 `PricingEngine` + KP / L6Chassis / Rules repo
- `unified_field_service`：统一字段定义中心，读 `business_fields` + `dynamic_source_fields`，消除前端硬编码字段
- `template_filler`：在 Univer `cellData` 上按 bindings 填数据，预览/导出共用
- `snapshot_converter`：`excel_to_snapshot()` 把上传 Excel 转 Univer 格式
- `preview_data_loader`：聚合 opportunity + quotation + items 三层数据供模板预览

**core/**
- `startup.init_rules_db`：lifespan 启动时建表（rules + l6_history engine）+ 空库种子默认规则 + 清理临时文件
- `config.Settings`：`DATABASE_URL`（POSTGRES_* 拼接）/ `DATA_PATH` / `CORS_ORIGINS` / `APP_VERSION` / `DEBUG`（控制 SQLAlchemy echo）
- `database`：兼容旧导入的 shim，`get_db()` 主动 raise，强制用各 schema 专属 SessionLocal
- `exception_handlers`：`BusinessError` → JSON、`RequestValidationError` → 422、未捕获 → 500

## 请求流（上传报价单为例）

`POST /api/quote/upload`：
1. `api/quote.py` 校验扩展名 + 50MB 上限，`FileStorage.save_upload_temp` 落临时文件；无 `opportunity_id` 则生成 `OPP_<hex>`
2. `QuoteService.process_upload` 实例化 `PricingEngine`，注入 KP / L6Chassis / Rules repo
3. `PricingEngine` 调 `excel_parser`（读 rules 规则定位区域/提字段）→ 调 KP/L6 repo enrichment 每行
4. 各 repo 用专属 SessionLocal / engine 命中对应 schema 表，结果沿栈返回；后续保存商机时才把临时文件移入正式目录并落 `opportunity_files`

## 前端（`frontend/`）

Vue3 + TypeScript + Vite + Ant Design Vue + Pinia。视觉走 **Soft Glassmorphism** 玻璃系统（详见 [Frontend_Style_Guide.md](Frontend_Style_Guide.md)）。图表用 ECharts，色值经 `composables/useChartTheme.ts` 给真实值（canvas 读不到 CSS 变量）。Vite 配 `/api` 代理 → 后端 8000。

## 启动

- 后端：`cd backend && python -m uvicorn app.main:app --reload --port 8000`（全局 Python + `requirements.txt`，非 uv；Windows 终端需 UTF-8）
- 前端：`cd frontend && npm run dev`（5173）
- `.claude/launch.json` 已配两个服务

## 路线图（按需推进）

| 阶段 | 目标 |
|------|------|
| 平台化 | 多用户、RBAC 权限（PostgreSQL 迁移已完成） |
| 知识平台 | 硬件兼容知识库、可视化规则引擎 |
| AI 原生 | 向量检索、相似配置推荐、AI 问答 |

> 当前为单人单机工具，上述功能按需推进。
