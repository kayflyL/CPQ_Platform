<template>
  <header class="ot-bar">
    <div class="ot-brand"><span class="ot-mark"></span>AI 办公室</div>
    <div class="ot-right"><slot /></div>
  </header>
</template>

<script setup lang="ts">
/* 办公室门面的薄顶栏（桌面/设置页共用）：品牌 + 右侧插槽。
   应用工作区不挂它——工作区自带工具栏（现状整体迁入，见 office-router）。 */
</script>

<style scoped>
.ot-bar {
  position: sticky; top: 0; z-index: 40;
  height: 56px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 var(--cpq-space-5);
  background: var(--cpq-glass-2-bg);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--cpq-glass-border);
}
.ot-brand { display: flex; align-items: center; gap: 10px; font-size: var(--cpq-font-size-lg); font-weight: 700; letter-spacing: .5px; color: var(--cpq-text-primary); }
.ot-mark {
  width: 22px; height: 22px; border-radius: var(--cpq-radius-md);
  background: var(--cpq-accent-gradient); position: relative; flex: none;
  box-shadow: 0 2px 8px var(--cpq-shadow-color-soft);
}
.ot-mark::after {
  content: ""; position: absolute; inset: 7px; border-radius: var(--cpq-radius-xs);
  border: 2px solid rgba(255, 255, 255, .92); border-right-color: transparent;
}
.ot-right { display: flex; align-items: center; gap: var(--cpq-space-3); }
</style>
