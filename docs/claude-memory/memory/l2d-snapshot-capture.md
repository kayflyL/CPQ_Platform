---
name: l2d-snapshot-capture
description: Live2D 形象全身快照导出方法：l2dSnapshot 工具有 rAF 时机 bug 读到全透明，修复=同帧 rAF 同步读 WebGL 画布；size:900 高清；izumi/shizuku 模型只有上半身
metadata: 
  node_type: memory
  type: project
  originSessionId: 4a387e17-033e-4dc9-a5aa-adbeb2fd6e4d
  modified: 2026-09-28T08:44:13.256Z
---

Live2D 形象快照导出（2026-09-28 为 VRM 生成备料时验证）：

- `src/utils/l2dSnapshot.ts` 的 `getLive2dSnapshot()` **离屏抓帧有 bug**：探针用 setTimeout 隔帧 `drawImage` 读 WebGL 画布，默认帧缓冲已清空 → 永远读到全透明 → 15s 超时返回 null（办公室页/门户页均复现）。
- **修复法（实测有效）**：自己 `L2D_WIDGET.createWidget({model:{path,tips:false,scale:1.15}, position:'top-left', size:900, menus:{items:[]}})`，然后**在 requestAnimationFrame 回调里同步** drawImage 探测（widget 的 rAF 先注册先执行，同一帧内 WebGL 缓冲未失效），读到一个不透明像素就整帧 `toDataURL`。widget 忽略 parent 参数直接挂 body>div（position:fixed），用「canvas 集合差集」找它的画布；destroy 后可能有残留 div，按特征清理。
- **rAF 饿死坑叠加**：预览窗格被遮挡时 rAF 停发 → 抓取队列整个冻结（连超时都不触发）；`preview_screenshot` 强制出帧即可推进。
- widget 的 `size` 即画布像素：300 抓的人物高约 278px（放大糊），**900 抓的人物高约 830-900px**，配 Pillow 裁 alpha bbox + 方图垫边 → 1024 输入图正合适。
- 大图回传别走 eval 返回值（有长负载掺毒风险）：本地起 python http.server POST 接收器（CORS 头 Access-Control-Allow-Origin:*），浏览器 `fetch('http://127.0.0.1:PORT/save?key=x', {method:'POST', body: dataURL})` 直落盘。
- 产物：`tmp/vrm-src/{key}_1024.png`。**形象盘点**：hibiki/koharu/nico 全身完美；**izumi/shizuku 的 Live2D 模型本身只有上半身**（izumi 肩上大半身、shizuku 趴桌），做不了全身 3D。这 5 个均为 Live2D 官方示例角色，正式对外需换授权干净素材。关联 [[office3d-refactor-plan]]（VRM 管线）。

**Why:** VRM 生成、同事形象相关需求都要先过「Live2D→全身 PNG」这一步，工具自带的现成方法是坏的，不知道这个坑会原地打转。
**How to apply:** 碰 Live2D 形象导出/快照/VRM 备料先看本文档；直接抄上面 rAF 同步读法，别用 getLive2dSnapshot。
