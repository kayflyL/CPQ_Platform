---
name: colleague-structured-memory
description: 09-27重构(工具自管+双时间轴+整理+治理面)+09-28两级分域(对话写私有域仅本人注入,治理面管公共域,user_id列定域);碰员工页/记忆/同事配置前先看
metadata: 
  node_type: memory
  type: project
  originSessionId: 103415a3-4b46-42b1-a04c-db5d6194e356
  modified: 2026-09-27T16:25:27.141Z
---

# 同事结构化记忆（2026-09-27 重构 + 09-28 域隔离后的当前态）

08-30 落地分型记忆 + Mem0 式抽取；09-27 按调研四机制整体重构（用户批语「你这是打补丁」后重做）：**注入层不变，写入层换轨，数据模型加时间轴，治理面上员工页**。

**Why:** Mem0 式事后抽取管线 ≤ 代理自管（Letta LoCoMo 实验 filesystem 基线 74% 胜 Mem0）；fire-and-forget 抽取不可观测、易产生一次性任务垃圾（实测 23 条里 13 条是垃圾）；无时间轴则矛盾只能硬覆盖。
**How to apply:** 碰员工页记忆抽屉、colleague_memory_service、记忆注入/工具链时按下述契约，别复活抽取器旧路径。

## 当前架构（四层）

1. **注入层（不变）**：`memory_block(role_key, limit, user_text, user_id)`——durable 集（pinned∪manual）恒注入 + 非置顶 fastembed 相关性召回（降级最近N）；命中刷 `last_accessed_at`。**域过滤：user_id 给定=公共∪该用户私有；缺失=只公共（fail-safe 不串）**。colleague_prompt `_memory_block(colleague, user_text, user)` 经 asyncio.to_thread 调。
2. **写入层（新）**：`colleague_memory` 工具（agent_tool_specs，default_enabled=False 不进画布），四动作 list/view/write/retire；**恒挂**在 `_run_tool_turn`（`tools_with_memory` 注入，不占同事工具白名单；`if not allowed_tool_ids` 的纯聊路径不动）与 skill_chat `loop_tools`。role_key/user_id 从 TOOL_CTX 取（runners 与 skill_chat 两处 set 都带 user_id），跨角色拒绝。确定性守卫：类型枚举、可见集精确去重、钉死集禁 retire、100/**域**封顶（打戳不删）。六步 skill 引擎不挂（受控管道）。**write 一律落当前用户私有域（TOOL_CTX.user_id 缺失直接拒绝）；retire 仅本人私有条目，公共域对话内无权失效**。
3. **整理层（新）**：`consolidate_role(role_key)` async——同事用自己的 system_prompt 全量复查**公共域**提 merge/retype/retire 案，确定性校验后落库（merge=新条目+旧条目 superseded_by 链）；员工页「整理」按钮触发（POST /memories/consolidate，ai.office.manage）。私有域不进整理。
4. **数据模型**：rules.colleague_memories 加 valid_from/retired_at/superseded_by/last_accessed_at/provenance/**user_id**（startup 幂等 ALTER+回填；user_id NULL=公共域，非空=该用户私有域）。失效不物理删；管理面「删除」=force retire；仅「清空」物理删。

## 两级分域（2026-09-28，多用户隔离，用户拍板）

背景：系统将多用户使用，角色级共享记忆会让 A 教给角色的事实漏进 B 的对话。定调**对话私有+治理面公共**：对话写入的归属当前用户仅本人注入；公共域（全员共享的产品常识/平台约定）只由员工管理治理面维护，**不让 LLM 判断某条该不该共享**（判断错一次就是泄密）。治理面 `GET /memories` 默认只列公共域，传 `user_id` 可查指定用户私有域排查；管理面手工 add=公共域。真库 e2e 验证过：owner 见探针 / 他人不见 / 无用户上下文不见。

## 关键事实

- 旧抽取器（extract_and_reconcile/_apply_ops/schedule_extraction/_schedule_memory_extraction/EXTRACT_RECENT_WINDOW/memory_policy.save_after_turn/auto_memory）**已全删**，别再引用。
- 员工页抽屉：来源标签（手动/对话记忆/整理归并/历史 ← provenance.via）、「含已失效」开关（划线置灰+superseded_by 标注）、「整理」按钮。
- 09-27 首次清洗：23→10 活跃（support 6/analyst 3/assistant 1），16 条失效留痕；备份在 backend/_colleague_memories_backup_0927.json。
- 测试 tests/test_colleague_memory.py（23 用例：注入6+工具守卫7+域隔离6+整理4+其他，FakeRepo 打桩含域过滤）+ tests/test_office_events_message.py（message 截断 40 字）。
- 端点：/api/ai-colleagues/{role_key}/memories CRUD + consolidate；office_memory.py 只剩 3D 可观测态。

## 坑

- consolidate 的 LLM 失败要兜 ok:False 别抛（chat_json 是 async，max_attempts=1）。
- backend --reload 多进程杀不净会占 8000（wmic 连子进程）；E2E 建会话用 POST /threads/resolve；token 键名是 `token`。
- 线程/消息表在 opportunities.assistant_threads/messages（非 rules schema）。

相关：[[munder-difflin-borrow-list]] [[skill-current-state-2026-09-12]] [[assistant-skeleton]] [[chat-session-runtime]]

另：多用户防串的三件套定调（2026-09-28）——①记忆两级分域（本文）②办公室事件 message 截断 40 字（office_events.publish_office_event 唯一出口，看板全局房间原文不出线程）③AUTH_ENABLED=true 是多用户硬前提（关=全员共享匿名身份必串）。线程/短期记忆/回合锁本就 thread 级按 user 归属校验，不串。
