---
name: derive-must-have-manual-fallback
description: CPQ 配置面所有推导(功耗/PSU/GPU线缆/背板等)都必须带手填兜底——料号库数据大量不全，不能依赖推导
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db335c99-9381-4ff1-8378-7a858352c358
---

servers/config 配置面（`frontend/src/components/server-config/ConfigWizard.vue`）里**凡是依赖数据推导的环节，必须能让用户手动填写**：推导结果只作默认/参考，数据缺失时不阻塞、不崩。

**Why:** 用户原话——"现在很多配件功耗数据压根不全，不能依赖"、"很多数据都是不全的，需要用户手动输入，所以各种推导规则一定要考虑到数据缺失，让人填的情况"。实测确认：`/api/rear-io/psu-options` 和 `GPU供电线` 料号在库里**都是空的**，推导根本无米下锅。

**How to apply:**
- **首选范式 = 从料号库按类目选**（同 CPU/KP）：PSU 用 `partsApi.list('电源')`，GPU 供电线用 `partsApi.list('GPU电源线')`，下拉选型号、单价自动带出、只改数量。**不要**用 `/api/rear-io/psu-options` 那张专用表（实测为空）；也不要让用户手填单价。料号库里若某类目暂时为空，出手填/空状态提示去管理面加（GPU 电源线就是先在料号库建了 `GPU-PWR-L20 / NVIDIA L20 power cord / GPU电源线 / ¥62.5` 才能下拉）。
- 已落地的范式（照此推广）：前面板线缆 = 根数手改；PSU = 料号库下拉 + 数量；GPU 线 = 料号库下拉 + 数量。统一用 `overrides` 存手填值，显示值 = 手填优先 ?? 推导 ?? 默认/0。徽章用 `isManual(key)` 区分「手动/推导」。
- 推导展示（如功耗分解）用 `v-if="result?.power?.total"` 这类守卫，缺数据时隐藏并出手填/选择提示，绝不崩。
- 单价×数量的小计要在 UI 上直接算给用户看（如 62.5×8=500）。
- 别引入"推导开关/强制兜底"之类的额外开关（早期 psuForce 已删）——所有字段常态化可编辑，徽章标来源就够。
- 适用范围不止 PSU/GPU 线：碰 [[kp-parts-unification-roadmap]] 的 derive、背板类型、任何后续加的推导项，都按此套路：先查料号库按类目选，类目为空再手填。
