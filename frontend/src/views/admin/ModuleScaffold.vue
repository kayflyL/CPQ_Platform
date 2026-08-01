<script setup lang="ts">
/** 模块轻壳 —— 选型/推理等暂未升级成工作台的模块用:顶部一条「← 策略中心 + 模块名」回门户条,编辑器本体走默认插槽(零改)。 */
import { useRouter } from 'vue-router'
defineProps<{ title: string; subtitle?: string }>()
const router = useRouter()
</script>

<template>
  <div class="mod-scaffold">
    <div class="ms-bar glass-light">
      <a class="ms-back" @click="router.push('/strategies')">
        <span class="ms-arrow">←</span> 策略中心
      </a>
      <span class="ms-sep">/</span>
      <span class="ms-title">{{ title }}</span>
      <span v-if="subtitle" class="ms-sub">{{ subtitle }}</span>
      <div class="ms-extra"><slot name="extra" /></div>
    </div>
    <div class="ms-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.mod-scaffold { display: flex; flex-direction: column; padding: 8px 24px 40px; }
.ms-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border-radius: 12px;
  border: 1px solid var(--cpq-glass-border);
  margin-bottom: 14px;
  position: sticky;
  top: 12px;
  z-index: 5;
}
.ms-back {
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: color 0.15s;
  user-select: none;
}
.ms-back:hover { color: var(--cpq-accent-primary); }
.ms-arrow { margin-right: 2px; }
.ms-sep { color: var(--cpq-text-disabled); }
.ms-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); }
.ms-sub { font-size: 12px; color: var(--cpq-text-muted); }
.ms-extra { margin-left: auto; }
.ms-body { flex: 1; }
</style>
