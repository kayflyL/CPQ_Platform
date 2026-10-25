---
name: gsap-skills-installed
description: "GSAP 动画 skill 已装(8个)在 ~/.claude/skills/gsap-*,碰前端动画/UI 美化前先看"
metadata: 
  node_type: memory
  type: project
  originSessionId: 497c6db2-8e84-4406-8ad9-5e83bf858ead
  modified: 2026-07-31T17:00:58.775Z
---

GreenSock 官方 [gsap-skills](https://github.com/greensock/gsap-skills) 已装(2026-08-01,手动 git clone+复制,非 npx)。8 个 skill:`gsap-core`/`gsap-timeline`/`gsap-scrolltrigger`/`gsap-plugins`/`gsap-utils`/`gsap-react`/`gsap-performance`/`gsap-frameworks`(含 Vue 生命周期/清理)。位置:`~/.claude/skills/gsap-*/SKILL.md`。

**生效**:skill 列表在会话启动时扫描,本会话调不到,**新开会话**才进 available skills。但 Claude 本身懂 GSAP,没 skill 也能写,skill 只是版本精确 API + 最佳实践 + 坑提醒(如 Vue 里 gsap.context cleanup、ScrollTrigger.refresh)。

**CPQ 前端已装 `gsap` npm 包**(2026-08-01 装于 frontend/,试水用;曾误装根目录已清理)。GSAP 现含全部插件(SplitText/Flip 等)全免费,public npm 即可。

**试水结论(2026-08-01)**:在商机驾驶舱 OpportunityList.vue 试过首屏入场动画(淡入上浮 → 3D 翻转 rotateX)。两个坑:① 淡入+小幅 y(14-20px)在玻璃卡片上不明显;② 3D 翻转够炫但**卡顿**——根因是 glass 卡片的 `backdrop-filter`(磨砂玻璃)在 transform 动画时每帧重绘模糊,9 张卡同翻掉帧(加 will-change 也救不回 paint 层开销)。用户定调**不要这个动画**,代码已撤回原状。GSAP 在 CPQ 暂未落地。

**再用的注意**(避免重复踩坑):若将来要在 CPQ 做 GSAP 动画——① 避开带 backdrop-filter 的元素,或动画期间临时关磨砂(onStart 加 class 关 backdrop-filter,onComplete 恢复);② CPQ 是 B2B 工具,入场/滚动大动画用户不感冒,数字滚动那种微交互(count-up 已有 useCountUp)更对路。碰动画/美化前先看。链接 [[glass-console-system]] [[frontend-typecheck-env]]。
