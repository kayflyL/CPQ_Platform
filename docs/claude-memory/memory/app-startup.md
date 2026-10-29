---
name: app-startup
description: "How to actually launch CPQ Platform: backend/.venv (NOT bare python — hermes hijacks it to its own venv); Windows GBK + IPv6 gotchas"
metadata: 
  node_type: memory
  type: project
  originSessionId: 87da06b3-ff0a-4e80-9ed8-88a272a942b6
  modified: 2026-08-10T09:18:27.341Z
---

CPQ Platform 的真实启动方式（README 写的 `uv sync` / `uv run uvicorn` **不适用**）：

- **后端环境 = `backend/.venv`**（不是裸 `python`！）。第三方客户端 hermes 会把自己的 venv 注入 PATH，`python` 解析到 `hermes-agent\venv`——那只有 hermes 自带依赖（fastapi/uvicorn/openai），**缺 pandas/sqlalchemy/psycopg2 等 CPQ 依赖**，且 hermes 按 generation 重置 venv 时会冲掉项目装进去的包（曾导致 `main.py` 加载 `quote_service` 时 `ModuleNotFoundError: pandas` 崩溃）。正确做法：用 `backend/.venv/Scripts/python.exe`（uv 创建的精简 venv，**无 pip**，装包用 `uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements.txt`）。**跑测试同样必须用这个 venv**：`backend/.venv/Scripts/python.exe -X utf8 -m pytest tests/ -k <kw> -q`——裸 `python -m pytest` 会解析到 hermes venv，报 `No module named pytest`（2026-08-10 实测：hermes venv 现在有 sqlalchemy/psycopg2 能跑 DB 查询，但缺 pytest，别被"能连库"骗了）。手动启动：`backend/.venv/Scripts/python.exe -X utf8 -m uvicorn app.main:app --app-dir D:/CPQ_Platform_V1/backend --reload --port 8000`。依赖清单见 `backend/requirements.txt`。
- **Windows GBK（已修）**：`startup.py` 的 emoji print 曾在 GBK 终端 `UnicodeEncodeError` 崩 lifespan。已在 `backend/app/main.py` 顶部 `sys.stdout/stderr.reconfigure(encoding="utf-8")` 修复，任意启动方式（uvicorn / .bat）均不再崩。
- **前端**：`cd frontend && npm run dev`（node_modules 已就绪），端口 5173，vite 已配 `/api` 代理 → 8000，浏览器只开 5173 即可端到端。
- **Windows localhost IPv6 坑（已修）**：uvicorn 默认只绑 `127.0.0.1`（IPv4），但 Windows 上 `localhost` 优先解析到 `[::1]`（IPv6），导致 vite 代理 target 写 `http://localhost:8000` 时报 `ECONNREFUSED`（`internalConnectMultiple`）。已在 `frontend/vite.config.ts` 把 proxy target 改成 `http://127.0.0.1:8000`。若再遇到 vite 代理 ECONNREFUSED，先 `curl http://127.0.0.1:8000` vs `http://[::1]:8000` 验证是否同坑；不要改回 localhost。
- `.claude/launch.json`：backend port 8000 / frontend port 5173；后端用 `--app-dir` 绝对路径绕开 cwd。**backend 的 `runtimeExecutable` 已改为 `backend/.venv/Scripts/python.exe` 绝对路径**（写裸 `"python"` 会被 hermes 劫持到 hermes venv → 缺依赖崩）。preview 工具 screenshot 在 dashboard 页会超时（echarts canvas 渲染），用 preview_snapshot/eval 调试更可靠；另 preview_start 在 Windows 上对 8000 端口有误判（报"被占"但 netstat 无监听），可改用 Bash 后台跑 .venv uvicorn + curl 验证。

数据库是 **PostgreSQL**（0.1.12 从 SQLite 迁来，**未迁回**）：单库，连接串在 `backend/app/core/config.py` 的 `DATABASE_URL`（读 `POSTGRES_*` 环境变量），分 `kp` / `l6` / `opportunities` / `rules` / `l6_history` 等 schema。项目里**没有 .db 文件**；`backend/migrations/` 和 `backend/scripts/` 里的 `sqlite3` 引用是历史迁移脚本，不再运行。文档滞后见 [[docs-code-drift]]。


## 后端重启正确姿势(2026-10-18 三次事故教训)

uvicorn --reload 在此机不可靠两次实锤(不热载/半死连接)。重启必须全家族清场:
1. 杀进程**不能只按命令行含 "uvicorn" 过滤**——reload 的 worker 是 multiprocessing spawn,
   命令行只有 `python -c "from multiprocessing..."`;且父进程强杀后监听句柄被活着的
   子进程继承,netstat 显示死 PID 的 LISTENING 幽灵条目,多个世代可同时共听 8000。
2. 正确步骤:列出全部 python 进程(看父子关系)→ taskkill /F /T 逐个杀(含 worker)→
   **netstat 确认 8000 监听条目清零** → 单代拉起 → 再查 netstat 恰好一条且 PID 是新代际。
3. **HTTP 200 不能作为重启成功依据**——旧世代也会回 200(本次"重启成功"假象致 M3 徽标
   全显示推理型:前端新/后端幽灵 16:30 worker 无 entity_binding 字段)。
4. Windows 下 Stop-Process 可能静默失败,用 `cmd //c "taskkill /F /T /PID x"`(Git Bash 双斜杠)。

5. **重启参数必须复刻真实进程**:实际运行的后端是无 --host(默认绑 127.0.0.1,IPv4);
   start_backend.bat 里的 `--host ::` 是 v6-only,照 bat 重启会断 vite 代理(它指向 127.0.0.1)。
   正确拉起:`python -X utf8 -m uvicorn app.main:app --reload --port 8000`(无 --host),验证
   127.0.0.1:8000 LISTENING。
