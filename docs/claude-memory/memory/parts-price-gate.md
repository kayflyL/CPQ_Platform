---
name: parts-price-gate
description: 配件库价门：field.parts.price(看)复活+action.parts.price.manage(写)拆出；quote看/te-business无价；价格键族fail-closed灰度也不豁免；新价格端点必须接线否则扫描测试挂；碰配件价格/权限/匿名可见先看
metadata:
  node_type: memory
  type: project
  originSessionId: cdc6ba92-f70a-4dfe-bc98-a9218dcb353e
  modified: 2026-10-16T12:01:08.632Z
---

2026-10-16 用户拍板（此前 perm-gap-audit 遗留「价格写要不要收紧待拍板」）：配件价格双键落地。

**键**：`field.parts.price`（看库价，曾因从未接线被回收，本次复活并全链路接线）+ `action.parts.price.manage`（写价，从 page.parts 拆出——**看价≠写价，quote 只看不写**）。持有：quote/cost/director 看价（quote 2026-10-16 补授，报价拼 KP 行价靠库价）；cost/director/admin 写价；**business/te 有意不给任何价键**（查件看参数不受限）。

**后端强制**（全走 field_visible + `mask_part_price_fields`，price_mask.py 新函数——与报价域 _PRICE_KEYS 分开，刻意不含 total/amount 防误伤分页信封）：admin.py 全 /kp/* 读遮价、stats/movers/duplicates/l6(list|grouped|history) 无键 403；parts.py 料号读遮价；kp_config.py /api/kp/parts 剥 unit_price/unit_currency/latest_price_date（specs 照常——技术查件口子）；bom_cases.py 案例 kp_lines/price_snapshot 遮价；价格排序与「有报价」筛选对无键者静默失效（**顺序也是价格信息**）；配件 create/update 载荷无 manage 键剥价格键（防借编辑覆写库价）；KP/料号价格导入导出=manage 键。

**前端降级=同页查型号模式**（不加并列页面）：Parts.vue/PartsLibrary.vue 按两键 v-if 隐藏价格面；PartPicker 下拉随数据层自然无价；TaskBoard 的 BomTable 接 `:hide-cost="!can('field.quote.price')"`（hideCost 此前全站无人传=商机域漏价口）。te 选件带出的方案行不含价，成本/报价侧用既有「同步库价」拉平。

**防复发（上次失败的根因是键建了没人接线）**：`tests/test_parts_price_gate.py` 三层网——掩码单测/函数级遮罩断言（mock 仓储直调端点）/路由源码扫描（配件价格前缀下每个 GET 必须有门标记或在白名单，新端点忘接线直接挂）。

**价格 fail-closed（2026-10-17 定调补充）**：价格键族 `field.quote.price`/`field.opportunity.quote_price`/`field.parts.price` **灰度期（AUTH_ENABLED=false）也不豁免**——匿名/无授权一律不可见（「被授权的账户可以看，其他都看不了」）。收口三处同源：deps.field_visible、deps.user_has_permission（AI 链路 effective_price_ok 经此自动跟随）、前端 store can()（否则灰度下 UI 照渲染而数据被剥，体验割裂）。其余权限键灰度恒放行不变。

**排查实录（2026-10-17「匿名还能看到价格」）**：三层叠加——①浏览器持灰度期残留的「匿名」有效 JWT（账号在库且 active，_user_from_token 不查角色）②8000 后端 --reload 的 worker 是孤儿（reloader 死后 socket 被继承，netstat 显示已死 PID，命令行无 uvicorn 字样要按 python.exe 全量搜）跑着旧代码 ③旧代码灰度恒可见语义。杀孤儿 worker + 重启后消失。`.env` 无 AUTH_ENABLED 覆盖、配置默认 true；8011 另有一个显式 `AUTH_ENABLED=false` 的常驻灰度实例（别与 8000 混淆）。

**Why:** 技术/业务需查配件参数但理论无权见价；10-01 审计确认全链路裸奔且 business/te 当时能改价（比看价更糟）；10-17 匿名可见价格坐实灰度豁免口也要堵。

**How to apply:** 新增任何返回配件/KP/BOM 案例价格的端点必须接两键之一，否则扫描测试挂；新价格字段进 `_PART_PRICE_KEYS`；角色给价只动 role_repo 种子+管理面勾选（seed_missing_defaults 只追加自动生效）。AI 侧 price_access×发起人 RBAC 与此并行不冲突。关联 [[price-access-role-control]] [[perm-gap-audit-2026-10]] [[auth-rbac-system]] [[parts-vs-kp-distinction]]。
