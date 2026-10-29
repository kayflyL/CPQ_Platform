---
name: antd-autocomplete-use-vmodel
description: antd-vue a-auto-complete 两坑——(1) 必须 v-model:value 或 :value+@update:value，:value+@change 会自发触发把值截成首字母；(2) options 只吃 {value,label}[]，纯 string[] 会崩
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f7f4af1b-ba8a-4378-8367-eb3d00c92424
  modified: 2026-07-26T09:55:01.992Z
---

antd-vue 的 `a-auto-complete`：**必须用 `v-model:value`，不要用 `:value` + `@change` 单向受控**。

**Why:** 2026-07-20 报价工作台 server_model 改下拉时踩坑——用 `:value="cfg.server_model"` + `@change="onInput"`，组件挂载后会**自发触发一次 @change，传入值被截成首字母**（"ES22V3-P" → "E"）。结果是 create 默认填好的完整型号被覆盖成 "E"，server_model_id 被清空（base_config_id 因 handler 不清它而侥幸保留）。换成 `v-model:value="cfg.server_model"`（双向）+ `@select` 补 id/base_config_id + `watch(server_model)` 兜底匹配，问题消失（双向绑定时 antd 不再自发 emit）。

**How to apply:** 报价工作台 server_model（[Workspace.vue](frontend/src/views/quote/Workspace.vue)）就是这个模式。今后任何 a-auto-complete 都默认 `v-model:value`；需要"选中后额外回填关联字段"用 `@select`，需要"自由输入匹配"用 `watch`。**server_model 空值约束已取消**（2026-07-21 改）：原 watch 在空串时强行回填目录首个机型，导致用户 backspace 删不干净+下拉只剩一项；现已改为允许清空，空值兜底交给保存层（saveProject 用 `server_model || ''`）。Related: [[l6-chassis-legacy-flow]]（server_model/base_config_id 走 config_l6_picks extra_fields 往返）。

---

**坑二（2026-07-26）：`options` 只吃 `{value,label}[]`，纯 `string[]` 会崩。** ConditionBuilder 把品类名 `string[]` 直接传 `:options`，antd-vue 内部 `flattenOptions` 对每个元素做 `'options' in element`，string 不是对象 → `Cannot use 'in' operator to search for 'options' in xxx` 整页崩。修法：`.map(s => ({ value: s, label: s }))` 转对象数组。另两点：(a) `:value` + `@update:value`（v-model 底层事件）是安全受控模式，不触发上述截首字母 bug（那是 `@change` 专属坑）；(b) `allow-clear` 在 auto-complete 上会触发 `Customize getInputElement...` warning，可去掉（用户手删输入清空即可）。
