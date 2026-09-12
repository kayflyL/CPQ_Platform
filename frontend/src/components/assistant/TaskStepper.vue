<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { NodeTrace, PauseFacts } from '@/composables/assistantChatWs'

/**
 * Claude Code 式任务计步器：聊天底部收起胶囊（标题 + 进度计数 + 当前步骤 + 已运行时长），
 * 点击展开完整步骤列表（状态 + 耗时）。替代旧的顶部横排进度条。
 * 展示口径（2026-09-02）：登记环节的两半（input 需求接收 / agent_fill 需求理解填表）
 * 合并显示为一步「需求分析」——用户视角五步：需求分析→机型→配件→BOM→输出；
 * 画布试运行回放仍按节点逐个显示，不受此影响。
 * 计时（2026-09-05）：running 期间本地每秒 tick（pipeline_start 到终态持续可见，
 * 杜绝「像卡住了」的体感），paused/done 冻结；时长不依赖节点事件——引擎静默期也一直在走。
 */
const props = defineProps<{
  traces: NodeTrace[]
  title?: string
  phase?: '' | 'running' | 'paused' | 'done'
  /** 中断点事实（P5-B2）：来自后端 pause 载荷，只按事实显示，不加工文案 */
  pause?: PauseFacts | null
}>()

const open = ref(false)

const FILL_STEPS = new Set(['input', 'agent_fill'])
interface DisplayStep {
  key: string
  label: string
  status: string
  summary: string
  duration_ms?: number
}

const displaySteps = computed<DisplayStep[]>(() => {
  const fill = props.traces.filter((t) => FILL_STEPS.has(t.step))
  const out: DisplayStep[] = []
  if (fill.length) {
    const status = fill.some((t) => t.status === 'failed') ? 'failed'
      : fill.some((t) => t.status === 'running') ? 'running' : 'done'
    out.push({
      key: 'agent_fill',
      label: fill.find((t) => t.step === 'agent_fill')?.label || '需求分析',
      status,
      summary: fill.map((t) => t.summary || '').filter(Boolean).slice(-1)[0] || '',
      duration_ms: fill.reduce((n, t) => n + (t.duration_ms || 0), 0),
    })
  }
  for (const t of props.traces) {
    if (FILL_STEPS.has(t.step)) continue
    out.push({ key: t.step, label: t.label, status: t.status, summary: t.summary || '', duration_ms: t.duration_ms })
  }
  return out
})

const doneCount = computed(() => displaySteps.value.filter((s) => s.status === 'done').length)
const totalCount = computed(() => displaySteps.value.length)
const currentStep = computed(() => displaySteps.value.find((s) => s.status === 'running'))
const state = computed(() => props.phase || (currentStep.value ? 'running' : 'done'))

/** 原因码 → 界面文案（UI 层本地映射，不复制后端任何话术；未登记的码回退到 kind） */
const REASON_LABEL: Record<string, string> = {
  brain_ask: '需要你补充信息',
  delivery_gap: '交付信息不完整',
  final_gate: '终检未通过',
  stuck: '本步没有产出',
  failure: '本步执行失败',
  turn_timeout: '响应超时',
  llm_timeout: '模型响应超时',
  kp_timeout: '选型查询超时',
  kp_pick: '需要你挑一行',
  approval: '等待你审批',
}

const pauseHeadline = computed(() => {
  const p = props.pause
  const why = p ? (REASON_LABEL[p.reason_code] || REASON_LABEL[p.kind] || '') : ''
  const where = p ? (p.label || p.step || '') : ''
  if (where && why) return `中断在 ${where} · ${why}`
  if (where) return `中断在 ${where}`
  if (why) return `已中断 · ${why}`
  return '等待你补充信息'
})

const headline = computed(() => {
  if (state.value === 'paused') return pauseHeadline.value
  if (state.value === 'running') return currentStep.value?.label || '执行中'
  return '已完成'
})

function fmtDuration(ms?: number) {
  if (!ms || ms <= 0) return ''
  return `${(ms / 1000).toFixed(1)}s`
}

// ── 活计时（Claude Code 体感核心）：running 每秒走字，静默等待也有生命感 ──
const startedAt = ref<number | null>(null)
const elapsedMs = ref(0)
let tickTimer: number | null = null

function stopTick() {
  if (tickTimer !== null) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

watch(state, (s) => {
  if (s === 'running') {
    if (startedAt.value === null) startedAt.value = Date.now()
    if (tickTimer === null) {
      elapsedMs.value = Date.now() - startedAt.value
      tickTimer = window.setInterval(() => {
        elapsedMs.value = Date.now() - (startedAt.value ?? Date.now())
      }, 1000)
    }
  } else {
    stopTick()
  }
}, { immediate: true })

onBeforeUnmount(stopTick)

function fmtElapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`
  const h = Math.floor(m / 60)
  return `${h}h ${String(m % 60).padStart(2, '0')}m`
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
      <span class="ts-count">{{ doneCount }}/{{ totalCount }}</span>
      <span v-if="elapsedMs > 0" class="ts-elapsed">{{ fmtElapsed(elapsedMs) }}</span>
      <span class="ts-headline">{{ headline }}</span>
      <span class="ts-caret" :class="{ 'is-open': open }">▾</span>
    </button>
    <transition name="ts-pop">
      <div v-if="open" class="ts-pop">
        <div
          v-for="s in displaySteps"
          :key="s.key"
          class="ts-step"
          :class="`ts-step--${s.status}`"
        >
          <span class="ts-step-icon" />
          <span class="ts-step-label">{{ s.label }}</span>
          <span v-if="s.summary" class="ts-step-summary">{{ s.summary }}</span>
          <span class="ts-step-dur">{{ fmtDuration(s.duration_ms) }}</span>
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
.ts-elapsed {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  opacity: .85;
}
.task-stepper--running .ts-elapsed { color: var(--cpq-accent-primary, #1677ff); }
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
