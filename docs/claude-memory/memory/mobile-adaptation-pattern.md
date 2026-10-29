---
name: mobile-adaptation-pattern
description: 全站手机适配既定模式与经验（≤768 isMobile 分支、双抽屉/磁贴、抽屉 portal 全局样式、tabbar-inset 让位、触屏无 hover、隐藏页签动画冻结）
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 67032332-865f-46e7-80ea-4fa31be82ba9
  modified: 2026-09-20T02:15:43.951Z
---

2026-09-19 起全站手机适配既定模式（线索页/详情页/配置向导/报价台/AI办公室/配件页已落地，Portal 等轻适配）：

1. **布局范式**：`isMobile`（matchMedia ≤768，个别页 ≤860/960）+ `onBeforeUnmount` 移除监听；主内容独占 + 旁路 a-drawer（左=导航/对照，右=结果/旁路）+ 底部 sticky 摘要条（关键值+高频动作常驻拇指区）。列表型页面用「两级磁贴」（配件页 V2：首页搜索+统计+分类磁贴，点贴进二级列表，具体条目不上首页——用户定调）。
2. **抽屉三件套**：`root-class-name="xxx-drawer"` + 组件内**全局 style 块**（portal 挂 body，scoped 够不到；固定暗色链路如配置向导用 literal 色值不接主题）+ slot 内容可正常命中 scoped。宽表/面板复刻进抽屉时两侧 v-if 互斥保单实例，共享同一 computed/state。
3. **让位**：固定/sticky 元素 `bottom: var(--cpq-tabbar-inset)`（=58px+safe-area，DefaultLayout 全局定义）；页面底部让位靠布局层 `.scroll-clearance-bottom`，页内不再写死 padding-bottom。flex 收尾的壳层（如 ai-office-shell）用 `padding-bottom: var(--cpq-tabbar-inset)`。
4. **坑**：触屏无 hover——hover 显隐的操作按钮手机端必须常显（通知中心 nc-acts 曾中招）；**隐藏页签里 Vue Transition/CSS transition/rAF 全部冻结**（enter-from/leave-active 挂着不走），实测判断画布动画要强制置终态或查 class 而非量 rect；浏览器返回键不响应组件内两级视图（配件页 mobileView），页内返回键承担；**真机 100vh 陷阱**（09-19 实机复现）：`.app-layout height:100vh` 是「地址栏收起时」的最大视口，地址栏弹出即把底部内容压进浏览器 UI 后面——表现为固定元素「时好时坏」，模拟器测不出。已修：`.app-layout`/`.login-page` 双声明 `height:100vh; height:100dvh`（iOS 15.4+/Chrome 108+）；**新页面锚定视口一律写 dvh 双声明**。
5. **验证**：`backend-verify`(8010 免登录)+`frontend-verify`(5174, VITE_API_TARGET=8010) 只读浏览；preview_resize 模拟切换不触发 MQ 监听，**切视口后必须 reload**；服务器链路为固定暗色且原型 HTML 是视觉权威（勿动 memory），只做容器级冒烟不深改；**模拟视口测不出地址栏效应，fixed/sticky 底部元素必须真机过一遍**。

**How to apply:** 新页面适配直接套以上范式；磁贴/卡片样式见 [[no-card-color-strips]]；涉及业务页面改动后同步 docs/frontend-pages 对应文档 + 最后更新行。
