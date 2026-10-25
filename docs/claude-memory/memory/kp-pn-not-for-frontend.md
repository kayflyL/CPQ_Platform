---
name: kp-pn-not-for-frontend
description: "用户定调(2026-09-05):料号(PN/库内编码)只归后端库用,前端/给AI的叙事素材只展示类别、描述、数量之类的业务字段"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 73d41dbd-6e82-4e59-afee-65666db128df
  modified: 2026-09-05T12:09:09.561Z
---

料号（PN / 库内编码如 part_id）属于后端库内使用，前端不展示；前端只展示类别、描述、数量之类的业务字段。

**Why:** 2026-09-05 修 kp 大脑「已锁定行」上下文时用户明确纠正——我原方案写的是"已锁定 N 行+各自料号"，用户驳回：料号不出前端。此前 KP表 artifact 也已定调 3 列（Catalogue=类目 / Configuration Description=名称或客户原话 / Quantity）。

**How to apply:** 凡是会流到前端或进 AI 叙事素材（提示词里供转述用的数据视图）的 KP 数据，只带 category/description/qty/name（描述性名称）等业务字段；part_id/pn 只留在后端工具接地（如 select_kp_parts 的池内校验）与库表里。给大脑的候选池仍可带 part_id 供工具调用取值，但锁定行上下文与 artifact 不带。碰 KP 展示/提示词数据视图前先看 [[skill-takeover-diagnosis]]。
