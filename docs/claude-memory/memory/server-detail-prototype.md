---
name: server-detail-prototype
description: 服务器产品链路（详情页/机型目录页/门户货架）整链固定暗色不受主题开关影响；原型 HTML 已删（落地后清理），视觉权威=线上 Vue 页面+本记忆定调；Hero 四主题与工业蓝 CTA 勿动
metadata:
  node_type: memory
  type: project
  originSessionId: 994e05f8-a224-4107-bbd7-0a911a9f6240
  modified: 2026-10-08T06:42:00.736Z
---

服务器详情页经 R1→R5.3 多轮原型迭代（原型 HTML 已在早前清理中删除，10-08 目录合并时核实），**2026-08-16 已落地为 Vue 页面**（用户拍板「可以了，落地吧」）：

**2026-09-18 目录链路整链固定暗色**（用户定调：主题色不受主题切换开关影响，与详情页一致）
- `/servers` 门户 ModelCatalog：banner 本就固定暗，货架区 `.sc-portal` 补固定深海蓝渐变底+固定文字 token
- `/servers/types/:id` 机型目录 ServerModelsPage：整页固定暗（负 margin 垫顶栏下+hero-dark 标记）
- `ServerModelCard` 加 `dark` prop 变体（目录两处传 dark；**管理面 ModelManager 不传仍走主题玻璃**，别全局改）
- `ModelShowcase` 去 `.glass`（!important 主题玻璃盖不掉）改自带固定暗面板；只此一处用，直接改安全
- 配方：固定深海蓝 `linear-gradient(#02050f,#071226,#030814)` + 文字 #eef3fa/#f2f8ff/白系 alpha，零 `--cpq-*` 引用=免疫主题切换

**已落地（npm build 通过，待用户浏览器验收视觉）**
- `frontend/src/views/server-config/ModelDetailPage.vue`：根 div `:style="stageVars"` 挂 `--sun-*/--page-bg/--band-bg` 四主题整页联动；内容区 = 铭牌卡(-34px 叠 Hero+天幕光线) → 概述 → 为什么选它(ruled list) → 产品能力(全幅 band-dark 两列横向卡+右侧 mono 数字列) → 场景适配(四列照片卡) → 可选配置 → 完整技术规格(details 折叠)；本地 token 定义在 `.detail-page`
- `frontend/src/views/server-admin/ModelEditorPage.vue`：产品内容与详情页顺序镜像（一句话定位/概述/价值亮点/能力板块/场景/规格）；能力卡含图标选择条(capIcons 9 键)+关键数字行；场景行缩略图上传(复用 /models/image)+auto-complete 联想；**加载迁移** features→highlights、scenarios string→对象，保存不再写旧结构（JSONB 整块替换，旧键消失）
- `frontend/src/constants/capIcons.ts`：图标注册表 SSOT（currentColor 线稿+每图一个 --sun-color 指示灯，管理页回落酒红）；详情页/编辑器共用
- 类型在 `api/serverConfig.ts` 的 `ModelProductContent`（backend 不透明透传，零后端改动）
- 演示图 4 张曾放 docs/prototypes/_img/（已随清理删除）；生产场景配图由用户后台上传

**视觉定调（勿违反）**
- Hero 是用户本人设计，**任何改动先过用户**；CTA 工业蓝 #1677FF；四主题（酒红/深蓝/纯黑/暗紫）联动是核心气质
- 能力卡**保持一行两卡**（固定 repeat(2,1fr)，760px 才 1 列），用户明确否过一行一卡
- cap-grid 别改 auto-fill（曾塌成一行一卡被用户当场纠正）
- torra token 权威源 _ref/torra1.css 已删，torra 色值以线上 ModelDetailPage.vue 源码为准，别凭印象写

**教训**：R3 曾整页固定夜蓝+暖橙、R3.1 又误删四主题（把"色彩乱"理解成砍主题），都被否——用户嫌乱指内容区与 Hero 气质脱节；用户原话"你是专家，要整体考虑"，改视觉要整页系统性排查同类问题。

**How to apply:** 改详情页/机型编辑器视觉时，以线上 Vue 页面与本记忆定调清单为准；先看本记忆再动手。
