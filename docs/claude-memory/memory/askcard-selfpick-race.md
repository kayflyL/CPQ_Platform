---
name: askcard-selfpick-race
description: 配件卡自选空下拉根因=发卡先广播后落last_card的竞态(秒点409)+失败只显示一行小字;已修=先落库再广播+重试一次+错误行进下拉;碰自选/AskCard/card-pick先看
metadata:
  node_type: memory
  type: project
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T10:48:45.552Z
---

**2026-10-15 定案（用户报「自选下拉没内容」）**：自选通道服务端与前端渲染本身都是好的——实测端点对该 RAID 行返回 5 个真实候选、带成功数据的下拉渲染 5 行整整齐齐。空下拉的真因是**取数失败被吞**：`_emit_gap_card` 旧序「先 WS 广播、后落 last_card」，用户秒点自选下拉时 `card-pick` 端点读到的还是旧 last_card（无 pick_meta）→ 409「当前选项卡不支持自选」；而 `AskCard.loadPick` 失败只写卡下一行小字（am-q-pick-err），下拉本身空着 → 观感即「下拉没内容」。

**修复（已落地+回归测试）**：
1. `skill_chat._emit_gap_card` 改「**先落留底、再广播**」（last_card 与 pick_meta 先 `_save_mem`，再 emit WS）——顺序锚定在 `tests/test_gap_card_race.py`；
2. `AskCard.loadPick` 失败**自动重试一次**（发卡瞬间的竞态/抖动重试即愈），仍失败把错误以禁用占位行渲染**进下拉**（`⚠ <detail>`），`onPickSelect` 跳过 disabled 行；重开下拉对纯错误缓存会重新取数。

**Why:** 「数据管道正常+UI 空白」九成是取数失败被弱化展示；诊断时先分「请求发出没有/返回什么/渲染什么」三段取证（本次用 Vite 动态 import 挂真组件+桩 API 逐段验证，未动仓库文件）。

**How to apply:** ①诊断自选空下拉：先查该线程 mem.last_card.pick_meta 是否在位（在位=渲染层问题，不在位=竞态/发卡路径问题）；②无 slot_options 的卡数据走 AskCard fallback（slot=general、group 清空）→ 自选框根本不渲染——发卡端永远带 slot_options；③验证环境限匿名单同事（allowed_chat_role_keys），全流程 UI 复现需真实登录身份。关联 [[skill-current-state-2026-09-12]] [[relay-error-misclassified-unsupported]] [[frontend-dev-gotchas]]。
