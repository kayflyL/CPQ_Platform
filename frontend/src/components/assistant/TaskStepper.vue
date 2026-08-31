<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NodeTrace } from '@/composables/assistantChatWs'

/**
 * Claude Code 式任务计步器：聊天底部收起胶囊（标题 + 进度计数 + 当前步骤），
 * 点击展开完整步骤列表（状态 + 耗时）。替代旧的顶部横排进度条。
 */
const props = defineProps<{
  traces: NodeTrace[]
  title?: string
  phase?: '' | 'running' | 'paused' | 'done'
}>()

const open = ref(false)

const doneCount = computed(() => props.traces.filter((t) => t.status === 'done').length)
const currentStep = computed(() => props.traces.find((t) => t.status === 'running'))
const state = computed(() => props.phase || (currentStep.value ? 'running' : 'done'))

const headline = computed(() => {
  if (state.value === 'paused') return '等待你补充信息'
  if (state.value === 'running') return currentStep.value?.label || '执行中'
  return '已完成'
})

function fmtDuration(ms?: number) {
  if (!ms || ms <= 0) return ''
  return `${(ms / 1000).toFixed(1)}s`
}
</script>

<template>
  <div v-if="traces.length" class="task-stepper" :class="`task-stepper--${state}`">
    <button type="button" class="ts-pill" @click="open = !open">
      <span class="ts-icon">
        <span v-if="state === 'running'" class="ts-spin" />
        <span v-else-if="state === 'paused'" class="ts-pause" />
        <span v-else class="ts-check">✓</span>
      </span>
      <span class="ts-title">{{ title || '配置任务' }}</span>
      <span class="ts-count">{{ doneCount }}/{{ traces.length }}</span>
      <span class="ts-headline">{{ headline }}</span>
      <span class="ts-caret" :class="{ 'is-open': open }">▾</span>
    </button>
    <transition name="ts-pop">
      <div v-if="open" class="ts-pop">
        <div
          v-for="t in traces"
          :key="t.step"
          class="ts-step"
          :class="`ts-step--${t.status}`"
        >
          <span class="ts-step-icon" />
          <span class="ts-step-label">{{ t.label }}</span>
          <span v-if="t.summary" class="ts-step-summary">{{ t.summary }}</span>
          <span class="ts-step-dur">{{ fmtDuration(t.duration_ms) }}</span>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.task-stepper {
  position: relative;
  display: flex;
  justify-content: center;
  padding: 6px 12px 2px;
}
.ts-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, .12));
  background: var(--cpq-overlay-w06, rgba(255, 255, 255, .06));
  backdrop-filter: blur(8px);
  color: var(--cpq-text-secondary, #a6adb4);
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
  transition: border-color .2s ease, color .2s ease;
}
.ts-pill:hover { border-color: var(--cpq-accent-primary, #1677ff); }
.ts-icon { display: inline-flex; width: 14px; height: 14px; align-items: center; justify-content: center; font-size: 11px; }
.ts-spin {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-top-color: transparent;
  animation: ts-rotate .8s linear infinite;
}
.ts-pause {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: currentColor;
}
.ts-check { color: #16a34a; }
.ts-title { color: var(--cpq-text-primary, inherit); font-weight: 600; white-space: nowrap; }
.ts-count {
  padding: 0 6px;
  border-radius: 8px;
  background: var(--cpq-overlay-w10, rgba(255, 255, 255, .1));
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.ts-headline {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-stepper--running .ts-headline { color: var(--cpq-accent-primary, #1677ff); }
.task-stepper--paused { color: #b45309; }
.task-stepper--paused .ts-pill { border-color: #b4530955; }
.task-stepper--done .ts-pill { border-color: #16a34a44; }
.ts-caret { font-size: 10px; transition: transform .2s ease; }
.ts-caret.is-open { transform: rotate(180deg); }

.ts-pop {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 12px;
  right: 12px;
  max-height: 260px;
  overflow-y: auto;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, .12));
  background: var(--cpq-overlay-w10, rgba(22, 26, 32, .92));
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .25);
  z-index: 30;
}
.ts-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 8px;
  font-size: 12px;
  color: var(--cpq-text-secondary, #a6adb4);
}
.ts-step-icon { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid currentColor; flex: none; }
.ts-step--done { color: #4ade80; }
.ts-step--done .ts-step-icon { background: currentColor; border-color: currentColor; }
.ts-step--running { color: var(--cpq-accent-primary, #1677ff); }
.ts-step--running .ts-step-icon { animation: ts-pulse 1s ease-in-out infinite; }
.ts-step--running .ts-step-label { font-weight: 600; }
.ts-step--failed { color: #ef4444; }
.ts-step-label { white-space: nowrap; }
.ts-step-summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: .7;
  font-size: 11px;
}
.ts-step-dur {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  opacity: .8;
}

.ts-pop-enter-active, .ts-pop-leave-active { transition: opacity .15s ease, transform .15s ease; }
.ts-pop-enter-from, .ts-pop-leave-to { opacity: 0; transform: translateY(6px); }

@keyframes ts-rotate { to { transform: rotate(360deg); } }
@keyframes ts-pulse { 0%, 100% { transform: scale(.8); opacity: .6; } 50% { transform: scale(1.2); opacity: 1; } }
</style>
