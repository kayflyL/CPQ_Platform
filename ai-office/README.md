# ai-office —— AI 办公室引擎

工作流引擎本体（操作系统层）：大脑循环(loop)、状态运行时(state)、机制层(harness)、
服务层(server)。CPQ 是它上面的第一个应用（backend/app），以后的人事系统等是第二个。

- **边界法律**：`ai_office/engine_boundary.py`——严格区不得 import 宿主
  （backend/app/services、backend/app/api）；融合区带基线快照，新增宿主边=测试红；
  冻结内核 `app.core` / `app.models` / `app.repository`（数据库与配置基建）允许，
  进程拆分时它逐条变成「宿主提供的存储接口」。
- **宿主接入靠注册**：产物 builder（`cpq_artifact_builders` 自注册）、工具清单
  （`tool_manifests/`，住宿主侧）、办公室档案（`system_config.ai_colleagues.offices`）。
- **拿出去**：拷走本目录 + 自建入口（挂引擎路由）+ 实现内核清单里的存储接口 +
  按接入五步声明工具/流/角色。真流演练参照 `backend/tests/test_stub_host_drill.py`。
- 路线图与欠账：`docs/AI办公室引擎化方案.md` §6 v4、`docs/引擎独立欠账台账.md`。
