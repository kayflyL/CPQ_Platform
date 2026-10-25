---
name: model-detail-capability-showcase
description: 机型详情页「产品能力」带重构为 n8n 式左选右显点选展示（CapabilityShowcase），v1 节点图/v2 空面板/v3 小图标放大三轮原型教训
metadata: 
  node_type: memory
  type: project
  originSessionId: 0f877a95-e1b9-462a-b512-03259da1d64c
  modified: 2026-09-27T16:40:31.716Z
---

2026-09-28 拍板并落地：机型详情页「产品能力」= **左选维度 → 右介绍+硬件插画**（参考 n8n 首页左人格右画布的交互骨架，但不要节点流程图——用户明确："服务器没有可演示的链路，机器示意图所有机型都一样"）。

**落地**：`frontend/src/components/server-config/CapabilityShowcase.vue`（ModelDetailPage 整替换旧 cap-grid 两列卡）。左栏=维度 logo（capIcons 图标）+标题；右侧=内容列（kicker/大标题/介绍/metrics 大数字）+取景框舞台（点阵+主题辉光+暗角）内参数化硬件特写插画。数据全部来自 `product_content.capabilities` 现有字段，**编辑器零改动**；插画按 icon key 映射（chip/slots/net/drive/term/fan，未知回落 chip）是展示层常量，不进业务数据（守 [[no-invented-seed-values]]）。自动轮播 4.5s+悬停暂停+reduced-motion 静止。

**原型演进教训（审美翻车史）**：v1 节点流程画布——形不对（装饰画不带机型差异）；v2 纯文字面板——空，用户评"好丑"；v3 把 54px 小线稿图标硬放大 3.6 倍当大图——线条粗细节碎，用户评"丑爆了"。**教训：深色展示带的视觉区必须"框满物密"——统一取景框 + 参数化重复结构（晶格阵列/盘位阵列/插槽列）才有 v1 那种技术密度**；小图标只配小尺寸，大画布要么真截图要么参数化场景。调研依据：saaspo/screenhance 特性区范式（左 tab 右大图、六 tab 同框规格防跳动）。

权威原型：docs/prototypes/机型详情-产品能力点选介绍-原型v4.html（v1~v3 留档同目录）。页面文档：docs/frontend-pages/servers/model-detail.md 第 6 条。
