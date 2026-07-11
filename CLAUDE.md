# CLAUDE.md

> 新会话自动入口，每次会话启动自动加载。这里是"项目是什么 + 去哪查什么"——详细内容均在 `docs/` 各专题文档，本文不重复。
> 最后更新：2026-07-11 | v0.1.11

## 项目定位

CPQ Platform——面向服务器硬件的单人报价工具（Vue 3 + FastAPI），替代 Excel 手工报价。

核心流程：上传 Excel → 自动解析匹配 L6/KP 基准价 → 工作台精算 → 落库 → 导出报价单。

## 新会话启动流程

每个新 session 开始时，按此顺序对齐再动手：

1. **读 memory 索引**：`MEMORY.md`（自动加载）里列有项目背景记忆，相关的深读——了解已知事实与踩过的坑，避免重复摸索。
2. **确认红线**：本文件「必须先知道的」+ [Design_Principles.md](docs/Design_Principles.md)（改文件前确认、不硬编码、DB 变更先备份等）。
3. **判断任务类型**：涉及前后端运行 / 接口联调 / UI 调试 → 按下文「运行 / 调试」节拉起服务；纯文档 / 查询 / 代码阅读 → 直接开始，不白白起服务。
4. **动手前对齐**：改 / 删文件前向用户说明意图与影响范围、获确认再执行（红线③）；需求不清先问，不臆测。

## 文档索引（按需查阅，均在 `docs/`）

| 查什么 / 做什么 | 文档 |
|------|------|
| 功能模块、技术栈、分层、前端路由 | [System_Architecture.md](docs/System_Architecture.md) |
| 数据表结构、6 个库归属 | [数据库.md](docs/数据库.md) |
| 后端接口（8 模块 119 端点） | [API 路由.md](docs/API%20路由.md) |
| 定价 / 匹配 / 导出算法 | [Pricing_Engine.md](docs/Pricing_Engine.md) |
| Excel 解析、区域锚点、field_mapping | [Excel_Parsing.md](docs/Excel_Parsing.md) |
| 搭环境、首次初始化、跑测试、部署、排错 | [Engineering_Guide.md](docs/Engineering_Guide.md) |
| 业务流程、报价策略 | [业务流程.md](docs/业务流程.md) |
| 前端样式（`--cpq-*` 变量、Ant Design 覆盖） | [Frontend_Style_Guide.md](docs/Frontend_Style_Guide.md) |
| 公共组件清单 | [Component_Inventory.md](docs/Component_Inventory.md) |
| 设计原则 / 红线规则（9 条） | [Design_Principles.md](docs/Design_Principles.md) |
| 版本历史 | [CHANGELOG.md](docs/CHANGELOG.md) |

## 必须先知道的（违反必出错）

- **改后端**：Engine 层不碰 DB（统一走 Repository）；路径不硬编码（`Path(__file__).parent` 或 `DATA_PATH`）；改完 `python -m py_compile` 验证。红线全条见 [Design_Principles.md](docs/Design_Principles.md)。
- **改前端样式**：颜色必须用 `tokens.css` 的 `--cpq-*` 变量，禁止硬编码。见 [Frontend_Style_Guide.md](docs/Frontend_Style_Guide.md)。
- **启动**：`pip install -r requirements.txt`（项目无 pyproject.toml，不能用 `uv sync`）。完整搭建见 [Engineering_Guide.md](docs/Engineering_Guide.md)。
- **VM 读取滞后**：bash/VM 读项目文件可能看到旧内容，以 Read 工具为准。
- **已知代码问题**：引擎 `_load_rules()` 死代码、测试命名脱节、首次启动 3 个库不自动建表等——动手前先看 [Pricing_Engine.md](docs/Pricing_Engine.md)「已知边界」和 [Engineering_Guide.md](docs/Engineering_Guide.md)「排错」。

## 运行 / 调试：先拉起前后端

**当任务涉及前后端运行、接口联调或 UI 调试时，开始前先用 preview 工具拉起服务**（纯文档 / 查询 / 代码阅读类任务跳过，避免无谓起服务）：

- `preview_start("backend")` → uvicorn @ :8000
- `preview_start("frontend")` → vite @ :5173（`vite.config.ts` 已配 `/api` 代理 → 8000，浏览器只开 5173 即可端到端）
- 配置在 `.claude/launch.json`，按名字启动。看页面用 `preview_snapshot` / `preview_eval`，看后端用 `preview_logs`。
- 已知坑：`preview_screenshot` 在含 echarts 图表的页面会超时——改用 `preview_snapshot`；会话结束前不再需要时用 `preview_stop` 停止 server。
