---
name: perm-gap-audit-2026-10
description: 10-01权限体系差距审计：业务链路扎实但管理面174端点匿名裸奔(admin.py最重)+三层权限缺第二层(数据范围)+认证基线零防护(无限流/锁定/审计)；修复时按P0清单来
metadata:
  node_type: memory
  type: project
  originSessionId: c0f7a6a2-58e3-4720-b03a-1f1a8510b0f1
  modified: 2026-10-22T02:36:04.856Z
---

2026-10-01 对比业界（OWASP/NIST 800-63B、Salesforce 数据模型、用友/金蝶/纷享销客三层权限、Zanzibar/Keycloak 等）做的完整差距审计。

**已有的底子（对标不算差，别推翻）**：后端强制价格遮罩(=Salesforce FLS)、商机行级 owner/指派访问(`deps.user_can_access_opportunity`)、AI 查询物理边界(data_boundary.py)、权限目录治理、111 断言权限矩阵测试。核心报价链路(quotations.py 每端点有 Depends)保护到位。

**P0 硬伤**：
1. ~~管理面 174 端点零鉴权裸奔~~ **✅10-01 已修**：收口范式=整文件读操作挂路由级 `APIRouter(dependencies=[Depends(get_current_user)])`+写操作 decorator 级 `dependencies=[Depends(require_perms("<页面key>"))]`；key 按消费页面路由 meta 归属（server_catalog/l6_chassis/base_configs/bom_templates → page.settings.admin；admin.py /kp/*+parts.py → page.parts；/l6/* → page.settings.admin；business-fields+spec/univer 模板 → page.settings.templates；strategies/solutions/compatibility_rules/bom_cases/reasoning_flow/gpu_sizing admin → page.strategies；feed POST /users+search-aliases → require_admin；base cost-analysis 读 → page.settings.admin）。**公开白名单勿动**：/api/auth/config、/api/auth/permissions（登录页）、server_catalog 四个文件服务端点（showcase-models/model-image/model-docs/drawing-svg——`<img>`/GLB 加载器不带 Authorization 头，挂了就碎图）、artifact_templates echarts/logo、system_config branding/logo+requirement_slots_spec。reasoning_flow /_debug/asyncio-tasks 已删（全仓零调用方）。坑：admin.py 曾漏 import Depends（py_compile 不报 NameError，必须 `python -c "from app.main import app"` 冒烟）。验证=匿名 curl 全 401+白名单 200+111 矩阵过。
2. ~~AI 价格绕行缝隙~~ **✅10-01 已修**：`data_boundary.effective_price_ok(colleague, user=, user_id=)` = 同事 price_access × 发起用户 `field.quote.price`（`user_has_permission` 语义，灰度恒真/admin 天然过）；无发起人回合（定时/主动播报）维持同事单门控；**id 在但人已删/停用 → 拒**（宁可错杀）。接线四处：colleague_turn_runners._run_tool_turn（user dict）、skill_chat._prepare（self.user_id，引擎 price_ok 由它传导）、assistant.card_pick 两处（发卡自选 include_price/price_ok——用户 RBAC 同样传导）。群聊按发起人放行是已知残留（收件人级过滤需产品拍板）。测试 test_price_access.py 14 过（5 新增）。

**仍开放（10-01 用户拍板暂缓；⚠️其中登录防护/密码策略/审计三项 2026-10-22 用户定调放弃不做，别再当待办翻出来）：** 登录防护为零（无失败限流/锁定/验证码）；密码仅≥6位（无 blocklist）；审计空白（无登录/操作/权限变更日志，等保要留 6 个月）；token 原始（localStorage+12h 无 refresh/吊销/踢人）；数据范围只有全量-or-无权两态（缺本人/本部门档）；无组织结构；密码策略以上按业界（OWASP/NIST 800-63B）基线补。KP 价格写/导出收在 page.parts（business/te 持有）是**行为保持**选择——要不要把价格写收紧到更强 key 待拍板。**10-01 晚二轮修复（🟡）**：feed GET /users 收 require_admin（前端零调用的遗留目录接口）+ system_config requirement_slots_spec 收 get_current_user（唯一消费方 SkillStudio 登录页）；**公开白名单只剩 auth/config、auth/permissions、branding/logo、artifact echarts/logo、server_catalog 四文件端点**。复查确认：run_graph_executor 无独立 HTTP 入口（无试运行旁路）；cost 角色种子含死键 field.parts.price 待顺手清。

**用户删除/合并（10-01 落地）：** roles.py 新增 `GET /api/admin/users/{id}/references` + `DELETE /api/admin/users/{id}`(body.transfer_to)，核心=services/user_transfer_service.py：**功能性引用必转接**（opportunities.owner_user_id+sales_person名、opportunity_flows.assignees JSON(uid或legacy姓名,CAST AS json)、notifications.user_id、rules.colleague_memories.user_id），**历史留痕刻意不转**（created_by/operator 姓名、uploader_user_id、llm_trace、*_bak 表——改写破坏审计语义）。守卫：admin 角色账号 403 不可删（先于 self 判断，admin 自删也是 403）、self 400、有引用无 transfer_to 409。前端 UserRoleManagement 用户行「删除」+转接人弹窗（refLabel 中文映射）。**lena→王瑞 已合并**（lena 是 admin 角色，API 守卫会拒，走 service 直调；9+9+1 条全部转王瑞，王瑞现 21 归属；备份 backend/_backup_user_lena_merged_20261001.json）；全库引用盘点报告 backend/_user_refs_report.txt（~50 账号，演示型 1 单账号一大排、权限测试-×6 停用可删、codex_test 是 admin 角色不可删待定）。⚠️SQLAlchemy 2.0 坑（本日两烧）：`engine.connect()` 里 DELETE 不 commit=回滚假象，写操作必须 `engine.begin()`。

**P1 模型缺口**：数据范围只有「全量(page.opportunities_all) or 无权」两态，缺业界「本人/本部门/本部门及以下/全部」档位（ruoyi-vue-pro 五档+SQL scope 注入可参考）；无部门树/org 表（user_can_access_opportunity 扩展的前置）；无 SoD 角色互斥；无并发登录限制；**AI 绕行缝隙**=services 层不查 user_has_permission，低权用户可经开 price_access 的 AI 同事拿价格（chat_roles_allowed 与价格无关）。

**P2 路线图**：MFA(管理员+价格角色强制)、SSO/OIDC+SCIM(B2B 成交入场券,Keycloak/Casdoor 前置)、多租户(tenant_id 是死列恒"default",SaaS 化时 tenant 进 claim+PG RLS)、对象级共享(先 sharing 表勿上 OpenFGA)、HTTPS/全局限流(现裸 HTTP uvicorn)。

**Why:** 用户问「权限系统是不是不完善」；审计确认核心链路好、管理面和基线差。

**How to apply:** 按此清单补权限时逐项对照；新增 API 默认挂 require_perms 别再造裸端点；修 admin.py 时先读 [[auth-rbac-system]] 的权限目录约定；数据范围档位落地要动 user_can_access_opportunity+列表查询 SQL 两处。关联 [[price-access-role-control]] [[portal-flow-perms-audit]]。
