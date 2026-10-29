---
name: infobar-editable-input-style
description: 商机信息栏可编辑字段用带边框+固定宽度的输入框；别用 :bordered=false 隐框，a-auto-complete 不给定宽会塌缩消失
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5330d479-181e-4510-8800-cc3647a2a9af
  modified: 2026-07-25T02:47:51.226Z
---

商机详情信息栏的可编辑字段，用 **默认带边框 + `style="width: 220px"`** 的 `a-input-number` / `a-auto-complete`，常驻可编辑（回车/失焦自动存，focus 快照去重）。**别用 `:bordered="false"` 的"看起来像文本"隐框样式。**

**Why:** 实测隐框版 `a-auto-complete`（Select 内核）不给定 width 会塌缩到接近 0、字段整排"消失"；`a-input-number` 隐框用户觉得丑，明确反馈"还不如之前的效果"（之前=带边框 220px）。用户原本在 preview 里勾选了"整行直接可编辑(像文本)"，但看到真机效果后否掉了隐框，要回带边框外观——常驻可编辑的诉求保留，只是输入框样式要带边框。

**How to apply:** 信息栏字段做成常驻可编辑时，每个 `a-auto-complete` 必须带显式 `style="width: ..."`（否则塌缩），保留默认边框；`a-input-number` 同理给固定宽度。值绑定用 `v-model:value="(opportunity as any)[field.key]"`（见 [[antd-autocomplete-use-vmodel]]，别用 :value+事件）。失焦保存配 focus 快照去重，避免无改动也发 PUT/弹 toast。
