---
name: office-behavior-v2
description: "行为配置页V2(09-16批准落地):daily_plans区间日程替代三套点状规则,引擎日程段驱动,LLM只产措辞,任务>作息>空闲;碰office_clock/office_brain/行为页前先看"
metadata: 
  node_type: memory
  type: project
  originSessionId: 574460d1-0de8-4a9c-b6cb-5fdc11556e7e
  modified: 2026-10-22T02:36:28.549Z
---

AI 办公室行为配置 V2（2026-09-16 用户批准原型后落地 P0）：

- **数据**：`behavior.autonomous.daily_plans=[{id,label,roles[],weekdays[],segments[{start,end,status,intent,zone,activity}]}]`；roles=[]全员段。旧 `schedule_rules`/`idle`/`life.fallback_actions` 已删：后端 `_migrate_behavior_daily_plans` 迁移（旧定时规则→「legacy_schedule」计划段，已对生产 DB 跑过，备份在 backend/tmp/ai_colleagues_backup_before_dailyplans.json）。
- **引擎**（office_clock.py）：`_tick_plans` 段开始 HH:MM 群发事件/天/段一次；`_tick_life` 按当前时刻段出动作（个人段覆盖全员段=取开始最晚），**无段时段=安静**（不再编造活动）；LLM 开时只改措辞+聊天对象，status/intent/zone 段锁定；确定性同事互动=冷却桶哈希 %6 触发。
- **铁律**：任务(看板mission) > 日程段 > 空闲；LLM 只产措辞与日程，执行走确定性时钟（守 [[agent-architecture-decision]]）。
- **页面**（OfficeBehaviorEditor.vue，原型 docs/AI_OFFICE_BEHAVIOR_EDITOR_PROTOTYPE.html）：**全员泳道**时间轴（每同事一行,标签列116px,无段=安静时段留白）+ 智能层卡 + 外观折叠。**09-17 二轮**：①子页签面板禁带页级大标题(行为toolbar/Skills/Workflows同名h3已删) ②行为页无自保存按钮,走管理页「保存当前」(defineExpose 曾丢已补) ③日志迁出到 OfficeEventLogPanel.vue,挂 GovernancePanel「日志与审批」tabs(3D区按钮改名日志审批) ④antd 化(星期=select multiple,徽标=a-tag) ⑤暗色=局部调色板变量+[data-theme='dark']整体覆盖。AiOfficeManagement 和 TeamManager 两处挂载都传了 `:colleagues`。
- ~~**待做 P1**：每晨 LLM 生成日程+人工确认卡；「预演一天」；行为 reason 落库。P2：needs 滑条。~~（⚠️2026-10-22 用户定调放弃，不再计划做）
- 坑：office_brain 曾误删 `_autonomous_current_clock` 函数头（Edit 错位），已修——动这文件时注意三个保留函数：`_normalized_behavior_profile`/`_autonomous_current_clock`/`_autonomous_clean_action`。

关联 [[office-3d-layout-seed]]（同一批办公室改造）[[munder-difflin-borrow-list]]。
