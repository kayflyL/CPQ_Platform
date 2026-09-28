<script setup lang="ts">
/** 机型目录页 3D 展示区：左侧分类介绍 + 右侧 Three.js 渲染的 .glb 模型。 */
import { ref, computed } from 'vue'
import { useServerModel3D } from '@/composables/useServerModel3D'
import type { ShowcaseConfig } from './showcase-config'

const props = defineProps<{ config: ShowcaseConfig }>()

const stageRef = ref<HTMLElement | null>(null)

// 创建响应式的渲染选项
const renderOptions = computed(() => ({
  src: props.config.glb_path || '',
  renderConfig: props.config.render,
}))

const { loading, error } = useServerModel3D(stageRef, renderOptions)
</script>

<template>
  <section class="showcase">
    <div class="showcase-grid">
      <div class="showcase-intro">
        <span class="intro-eyebrow">机型总览</span>
        <h3 class="intro-title">{{ config.title }}</h3>
        <p class="intro-desc">{{ config.description }}</p>
        <ul class="intro-bullets">
          <li v-for="b in config.bullets" :key="b">{{ b }}</li>
        </ul>
      </div>

      <div class="showcase-stage">
        <div ref="stageRef" class="stage-canvas"></div>
        <div v-if="loading" class="stage-status">加载中…</div>
        <div v-else-if="error" class="stage-status is-error">{{ error }}</div>
        <div v-else class="stage-hint">拖拽旋转 · 滚轮缩放</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 固定暗色面板（只在机型目录页使用；不引用 --cpq-* 主题变量，不受主题切换影响） */
.showcase {
  padding: 28px;
  margin-bottom: 28px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
}

.showcase-grid {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 6fr);
  gap: 32px;
  align-items: center;
}
@media (max-width: 860px) {
  .showcase-grid {
    grid-template-columns: 1fr;
  }
  .showcase-stage { order: -1; }
}

/* 左：介绍 */
.showcase-intro {
  min-width: 0;
}
.intro-eyebrow {
  display: inline-block;
  font-size: 12px;
  letter-spacing: 0.08em;
  padding: 3px 10px;
  border-radius: 6px;
  color: #36CFCF;
  background: rgba(54, 207, 207, 0.15);
  border: 1px solid rgba(54, 207, 207, 0.3);
  margin-bottom: 14px;
}
.intro-title {
  font-size: 22px;
  font-weight: 600;
  color: #f2f8ff;
  margin: 0 0 10px;
}
.intro-desc {
  font-size: 14px;
  line-height: 1.7;
  color: rgba(238, 243, 250, 0.72);
  margin: 0 0 18px;
}
.intro-bullets {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.intro-bullets li {
  position: relative;
  padding-left: 18px;
  font-size: 13.5px;
  color: rgba(238, 243, 250, 0.72);
  line-height: 1.5;
}
.intro-bullets li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #5BB8FF;
  box-shadow: 0 0 8px rgba(91, 184, 255, 0.3);
}

/* 右：3D 舞台 */
.showcase-stage {
  position: relative;
  min-height: 380px;
  border-radius: 16px;
  overflow: hidden;
  background: linear-gradient(to bottom, #061225, #030b18);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.stage-canvas {
  position: absolute;
  inset: 0;
}
.stage-canvas :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
}

/* 底部提示 / 状态药丸 */
.stage-hint,
.stage-status {
  position: absolute;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 999px;
  color: rgba(238, 243, 250, 0.72);
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  pointer-events: none;
  white-space: nowrap;
}
.stage-status.is-error {
  color: #FF6B6B;
}
</style>
