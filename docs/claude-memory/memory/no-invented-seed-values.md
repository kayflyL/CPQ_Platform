---
name: no-invented-seed-values
description: "用户批评'喜欢加种子':业务事实数据不发明种子值,DB唯一权威,导入须dry_run+确认"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2d41732d-b140-4fe8-8a0d-974c339ac13e
  modified: 2026-09-27T10:26:38.707Z
---

用户定调(2026-09-27,AI推理配置器方案讨论时):别动不动提议"预置种子数据"。业务事实(机型默认卡配置、真实出货配置等)只有用户知道,模型/框架/场景这类初始数据来自真实文件。

**Why:** 项目里种子已两次出事——init_defaults 被删(铁律:DB 是唯一来源,代码不留默认值层);l6 底座 seed 写误导数据(seed 说只有 2U,实际 DB 有 15 套配置)。AI 配置器方案里我又提议"gpu_default 种子值",被用户当面质疑「为啥这么喜欢加存储之外的种子」。编造业务默认值 = 猜对无功劳、猜错污染数据还要迁移。

**How to apply:**
- 新字段/新表交付时默认为空,管理面给录入入口,不预填;
- 有真实来源的初始数据(Excel/官方 config.json)叫「首版导入」不叫种子:转换 → dry_run 给用户过目 → 确认 → 导入,导入完代码零种子逻辑(参照 [[kp-import-merge-playbook]]);
- 可以给「推断候选清单」供用户参考,但候选只出现在对话/文档里,不进代码不进启动脚本;
- 提方案时自查:这个数是业务事实还是技术常量?业务事实永远留给用户。

关联:[[skill-tree-trunk-architecture]] [[l6-baseconfig-capability-state]] [[office-3d-layout-seed]]
