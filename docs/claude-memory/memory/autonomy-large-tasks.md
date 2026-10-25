---
name: autonomy-large-tasks
description: 大块实现任务用户偏好一次授权推进到结果再批量汇报，中途别频繁求确认
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d6914bb9-bf83-4f78-8ded-f248c24bc219
  modified: 2026-07-23T05:02:05.717Z
---

对自包含的大块实现任务，用户偏好"一次性授权、推进到有结果再通知"，中途不要每步求同意/求确认。

**Why:** 用户原话"做的过程中能不能不要老是让我点同意，你做完到结果了再通知我，中间权限都给你"。与既有偏好 [[systematic-cleanup-not-whackamole]]、[[feedback-verify-yourself-dont-bounce-user]] 一脉相承——一贯要我自行决策、自行用 dev server 验证、批量汇报。

**How to apply:** 接到大任务后先建 TaskList 让他看到进度；遇到分叉自己拍合理默认（仅记录+事后说明，不阻塞）；用 preview/dev server 自验证到可观测结果；在有意义的里程碑（如某阶段跑通、整块完成）给一次合并汇报，而非每步都问。**例外**：自治授权不等于可静默做高危/不可逆动作（drop 表、删生产数据、force push、改 CI）——这类仍用"新建+回填+保留旧备份+git 增量提交"的可逆方式兜底，或在动作前一句话提示。完成时主动说明"改动未提交 git，要你点头再 commit"。
