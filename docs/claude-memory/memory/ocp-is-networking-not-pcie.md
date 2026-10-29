---
name: ocp-is-networking-not-pcie
description: OCP 网卡属网络子系统，在 server-config 配置面必须独立成「网络」卡，不能和后置 PCIe IO 槽(IO1~IO4)混在一起
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db335c99-9381-4ff1-8378-7a858352c358
---

OCP 网卡在 servers/config 配置面（`frontend/src/components/server-config/ConfigWizard.vue`）必须与 PCIe IO 槽**视觉区分**：作为「后面板 · IO 与网络」卡（`#panel-rear`）内的独立「网络 · OCP 网卡」**分段**呈现，**不能**和 IO1~IO4 混在同一组 PCIe 槽位网格里。

**Why:** 用户定调的行业配置器规范——OCP 走独立接口，属于 Networking 网络子系统。和 PCIe IO 槽混在一起，会让用户误以为 OCP 占用 PCIe 槽位、产生通道冲突误解。

**How to apply:**
- `#panel-rear` 一张卡含两个 `.sc-section-head` 分段：「PCIe IO 槽位」(渲染 `ioSlots` = rearSlots 过滤掉 'OCP') + 「网络 · OCP 网卡」(OCP 单选卡)。不要把 OCP 单独再开一张面板/一个导航步骤——用户明确说导航步骤要少（NET 步骤已撤）。
- 数据层不要拆：`rear['OCP']` 仍保留在 `rear` reactive 里（存档格式、BOM、`slotPrice` 都兼容）。`rearTotal` 只累加 IO 槽，`ocpTotal` 单独算，两者都计入 `l6Total`，卡头显示 `rearTotal + ocpTotal`。
- 判断 OCP 用槽位名 `=== 'OCP'`；单选写入用 composable 的 `setRearSingle('OCP', type|null)`。
- BOM 里 OCP 显示为「网络 OCP：…」而非「后面板 OCP」。
- 演进：先做成了独立 `#panel-net` 卡 + NET 步骤，用户后嫌步骤太多，改回同卡分段。别再拆出去。
- 碰 L6 机箱那套流程（见 [[l6-chassis-legacy-flow]]）里的 OCP 也应遵循同一领域划分。
- 相关总原则见 [[derive-must-have-manual-fallback]]。
