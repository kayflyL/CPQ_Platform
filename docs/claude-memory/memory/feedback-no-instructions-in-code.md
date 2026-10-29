---
name: feedback-no-instructions-in-code
description: 用户铁律（讲过无数次）：行为禁令/指令性文字不许硬编码进共享代码，要么放左栏节点说明(manual_rules)要么放节点抽屉目标层配置
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d9980c57-58ad-4257-bac2-907fd9408192
  modified: 2026-09-15T17:51:02.069Z
---

# 禁令文字不进黑盒代码

给大脑的**任何指令性/禁令性文字**（「禁止…」「不得…」「必须照抄…」类），不许写进共享代码（契约 formatter、引擎、闸门提示模板等）。唯一允许的两个住处：
1. **左栏节点说明**（flow `graph.manual_rules`，用户在 Skill Studio 左栏可编辑）；
2. **节点抽屉目标层**（`config.target` 配置，抽屉可编辑）。

**Why:** 代码里的指令=用户改不掉的第二指令源，违背「指令唯一出处=左栏」定调（见 [[skill-tree-trunk-architecture]]）。2026-09-16 用户原话「我讲过无数次，这种搭配文字『禁令』，不许往代码里黑盒写」——起因是我往 `format_document_contract` 里加了「逐字照抄/禁止改算」措辞。代码层只允许：**形状陈述**（首行=配置窗口、章节列表）与**确定性校验**（比对事实、不符打回——事实性 hint 不算禁令）。

**How to apply:** 写任何注入大脑提示的代码路径前自查：这段文字是「描述产物长什么样」（可留代码）还是「命令大脑怎么做」（去 manual_rules/target 配置）。测试反向断言可用 `assert "禁止" not in text`。
