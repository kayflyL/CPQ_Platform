---
name: api-key-security-hardening
description: 2026-09-14 API密钥安全加固落地：system_config读接口鉴权+llm_config掩码write-only+AI白名单硬排除system_config+仓库零密码；碰密钥/鉴权/AI数据面或GitHub公开前先看
metadata: 
  node_type: memory
  type: project
  originSessionId: 885285c4-dbe9-4d08-a3bd-11a03fc93366
  modified: 2026-09-17T10:03:03.265Z
---

2026-09-14 用户问「AI 办公室模型连接的 API 密钥如何防泄露、AI 会不会暴露给大模型厂商」，审计后获批「一起落地，确保安全」，六件全部完成：

1. **system_config 读接口鉴权**：`GET /`、`GET /{key}`、`GET /{key}/value`、`GET /llm_config/capabilities` 挂 `get_current_user`（未登录 401）；`POST /llm_config/test|models|probe` 挂 `require_admin`。全靠端点级 Depends，前端全局 axios 已挂 Bearer 拦截器（api/index.ts attachAuthInterceptors(axios)）所以零前端适配。
2. **llm_config 掩码 write-only**（system_config.py `_mask_value/_mask_row/_write_only_api_key/_drop_masked_key`）：GET 永不返回明文（`****尾4位`+`api_key_configured` 标志）；PUT 回传含 `****`=保留库内原值、显式空串=清除（回退 .env）；test/models/probe 带掩码实测时剥离该项回落已配置值。**llm_client 直读 repo 不受影响**（掩码只在 API 层）。
3. **AI 白名单硬排除**：`data_boundary._EXCLUDED_TABLES={"system_config"}`，缺省与手配 `query_data_tables_allow` 都拒——配置表（含密钥）永不进 LLM 上下文。
4. **仓库零密码**：config.py 的 POSTGRES_PASSWORD/JWT_SECRET 弱默认改空（.env 已补真实值，JWT_SECRET 原本就有；security.create_access_token 空值大声报错）；12 个迁移/备份脚本 + 7 个未跟踪脚本共 19 个全部改读 `scripts/_localdb.py`（密码只从 env/backend/.env 读）；宪法测试 `test_no_embedded_password_in_db_urls` 正则扫描 app/+scripts/（密码段排除 `{…}` 防 f-string 误报）。
5. **gitignore 兜底**：`*.dump`/`*.pgdump`/`db_dumps/`/`.claude/tmp_skill_run/`（已 git rm --cached 出跟踪）；**别加 `*.sql`**——23 个正常迁移 SQL 已被跟踪。
6. 新测试 `test_system_config_security.py`（9 例）+ data_boundary 硬排除 2 例；真机验证 harness `scripts/_verify_security.py`（401/掩码/PUT保留/列表无泄漏/POST 收权，ALL GREEN）。

**审计结论（回答用户的问题）**：GitHub 干净（.env 从未进历史、真 key 指纹零命中——SHA 比对法不读明文）；真实风险排序=无鉴权 GET（已修）≫ DB 备份误入库（已 gitignore 兜底）> 代码本身。AI 同事默认接触不到 key；中转商（cloudprime）必然看得到（Authorization 头，用中转的固有代价）；Claude Code 会话刻意不把明文读进上下文（读进=过 Anthropic 服务器）。

**遗留（用户侧决定）**：① DB 密码 961216 已在 GitHub 历史（远程仓库 kayflyL/CPQ_Platform 存在，本地领先 65 提交），公开仓库前建议 rotate Postgres 密码 + 同步 .env；② .claude/launch.json 仍被跟踪（无密钥仅本机路径，未动）。

**加固后遗症（09-16 修）**：feed 附件下载端点 `/api/feed/attachments/{id}/download` 挂 `current_user` 后，前端所有**绕过全局 axios 的直链**全部 401——AttachmentPreviewModal 裸 fetch（Excel 预览报「加载 Excel 失败」，实为 401 JSON 被当 xlsx 上传）+ img/iframe 直链 + `window.open` 下载（OpportunityDetail 查看导出/ArchiveSection/ApprovalFlowPanel `<a :href>`）。已全部改走 `utils/fileDownload.ts`（axios blob + attachAuthInterceptors，image/pdf 用 objectURL）。**铁律：任何要 Authorization 的 GET 产物（下载/预览）必须走 axios blob 或 fileDownload helper，不许 `window.open`/`<a href>`/裸 fetch 直链**。鉴权链验证法：无 token→401「未登录」、member token→403「无权访问该商机」（data_boundary）、admin token→200 `PK` 魔数。

**加固后遗症·第二波（09-17 修）**：裸 `fetch('/api/...')` 不走 axios 拦截器同样 401 静默失败——报价工作台质保描述默认值空（用户报障）、税率/汇率默认值+保存、助手 Provider 配置/商机摘要/驾驶舱摘要、BOM 模板使用计数共 6 文件 10 处，全部改走全局 axios。**铁律：前端任何 API 调用必须走 axios（全局实例已挂 attachAuthInterceptors），禁止裸 fetch 直连 /api**。grep `fetch\([`'"]/?api/` 可复查回归。

关联 [[auth-rbac-system]]（端点级鉴权体系）、[[query-data-primitive]]（工具即权限白名单）、[[llm-provider-relay]]（中转链路）。
