---
name: promo-landing-page
description: "对外宣传页已落地 frontend/public/promo/index.html(霄擎品牌/GSAP滚动叙事/独立单文件),碰宣传页/对外页先看"
metadata:
  node_type: memory
  type: project
  originSessionId: bcaaacef-ca5e-46d1-babf-83bf7b037675
  modified: 2026-09-29T10:57:45.584Z
---

2026-09-29 落地对外宣传页:`frontend/public/promo/index.html`,单文件零构建(GSAP 3.13 走 jsdelivr CDN)。

- **品牌**:霄擎算力科技(取自 [[galaxy-mirror-baseline]] 星河页对外品牌,非 CPQ Platform 后台标题);设计 token 全部承自星河页:深空 #050B18 / 面板 #0B1020 / 工业蓝 #4676F0 / 星紫 #6D48FF(蓝→紫渐变只用于字标与 hero 合计两处)/ Avenir Next 栈;等宽字体 IBM Plex Mono 做「编目声部」(单号/规格)。
- **叙事**:hero 唯一大胆元素=自演配置单(打字机需求→7 行 BOM 逐行点亮→合计揭价);流水线 6 站滚动描线;能力区交替行(反问气泡/DAG/揭示档位/PDF 四个 CSS 切片);产品线=猎户座跨列+三砖;全程不发明业务数字、不编客户 logo,示例金额标注「示意数据」。
- **坑①**:CDN script 用 defer 时,内联脚本立即执行拿不到 window.gsap——动画启动必须包 DOMContentLoaded(startMotion 守卫),否则静默不跑、零报错。
- **坑②**:预览验证时 [[preview-pane-raf-starvation]] 会让人误判动画没跑——gsap.globalTimeline.progress(1) 可直接 seek 终态验证;ScrollTrigger 的 scrub 渲染靠 rAF 会假死但 onUpdate/onClass 逻辑正常,别为假环境改代码。
- **遗留**:预约演示按钮是 mailto:demo@example.com 占位;产品线四系列描述是保守句式(星河目录在售·四步配置下单),等真实定位文案。
