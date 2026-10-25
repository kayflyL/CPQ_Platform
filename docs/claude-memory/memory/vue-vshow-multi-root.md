---
name: vue-vshow-multi-root
description: v-show 挂多根组件静默失效（只报 dev warning，构建不报错）——面板会常显泄漏到兄弟 tab；改 Vue 模板结构后必查单根
metadata:
  node_type: memory
  type: project
  originSessionId: ecc31071-a3ab-415f-864c-abc848962601
  modified: 2026-10-03T20:59:51.358Z
---

2026-10-04 服务器管理六 tab 视觉升级踩坑：改 SeriesManager 模板（表格→卡片）时，python 块级替换把根 div 提前闭合、`<a-modal>` 留在了根外 → 组件变**多根（fragment）**。宿主 ServerAdminPage 用 `v-show="adminTab === 'series'"` 挂载——**v-show 对多根组件不继承、静默失效**（仅 dev 模式 warning，vue-tsc/vite build 全都不报错），症状是产品系列面板在其余所有 tab 上常显，用户在「基准配置」里看到「产品系列」第一反应是数据串了。

**Why:** v-show 落在组件根元素上，fragment 根没有唯一落点；编译期不报错，只有运行时 console warning。

**How to apply:** ① 动过组件 `<template>` 结构后，收尾必查「`<template>` 直下只有一个根元素」（弹窗/teleport 类节点必须在根内）；② 多 tab 容器页（v-show 挂子组件）里新增/重构子组件尤其致命；③ 症状识别：某面板"出现在不该出现的 tab"= 先查该组件是不是多根，再怀疑数据。相关：[[edit-long-payload-corruption]]（本次模板手术是因 Edit 通道污染改走 python 替换才引入的）。
