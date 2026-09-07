<template>
  <nav class="process-rail glass">
    <div class="rail-progress">
      <div class="rail-progress-head">
        <span>Overall Progress</span>
        <strong>{{ progressPercent }}%</strong>
      </div>
      <div class="rail-progress-track">
        <div class="rail-progress-fill" :style="{ width: `${progressPercent}%` }"></div>
      </div>
      <p class="rail-progress-step">{{ currentStepText }}</p>
      <p class="rail-progress-label">{{ activeLabel }}</p>
    </div>

    <ol class="rail-steps">
      <li
        v-for="(node, idx) in nodes"
        :key="node.key"
        class="rail-step"
        :class="[node.state, { active: node.key === activeNode, disabled: disabled.has(node.key) }]"
      >
        <button
          class="rail-step-head"
          type="button"
          :disabled="disabled.has(node.key)"
          @click="emit('select', node.key)"
        >
          <span class="rail-step-index" :class="node.state">
            <CheckCircleFilled v-if="node.state === 'done'" />
            <template v-else>{{ String(idx + 1).padStart(2, '0') }}</template>
          </span>
          <span class="rail-step-copy">
            <b>{{ node.title || node.label }}</b>
            <span>{{ node.subtitle || node.statusLabel }}</span>
          </span>
        </button>
        <div v-if="node.key === activeNode" class="rail-substeps">
          <button
            v-for="(sub, subIdx) in SUBSTEPS[node.key] || []"
            :key="sub"
            type="button"
            class="rail-substep"
            @click="emit('select-substep', node.key, subIdx)"
          >
            <span v-if="node.state === 'done'" class="rail-substep-check"><CheckCircleFilled /></span>
            <span v-else class="rail-substep-dot"></span>
            <span>{{ sub }}</span>
          </button>
        </div>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircleFilled } from '@ant-design/icons-vue'
import type { ProcessNodeDef } from '@/types/flow'

const props = withDefaults(
  defineProps<{
    nodes: ProcessNodeDef[]
    activeNode: string
    disabledKeys?: string[]
  }>(),
  { disabledKeys: () => [] },
)

const emit = defineEmits<{
  (e: 'select', key: string): void
  (e: 'select-substep', key: string, index: number): void
}>()

const SUBSTEPS: Record<string, string[]> = {
  requirement: ['商机信息', '需求单'],
  boming: ['方案工作台', '我的附件'],
  costing: ['成本表工作台', '核价结果 / 转报价'],
  quoting: ['报价单列表', '导出 / 成本快照'],
}

const disabled = computed(() => new Set(props.disabledKeys))
const doneCount = computed(() => props.nodes.filter((n) => n.state === 'done').length)
const progressPercent = computed(() =>
  props.nodes.length ? Math.round((doneCount.value / props.nodes.length) * 100) : 0,
)
const activeLabel = computed(() => {
  const node = props.nodes.find((n) => n.key === props.activeNode)
  return node ? `${node.title || node.label} · ${node.statusLabel}` : '待开始'
})
const currentStepText = computed(() => {
  const index = props.nodes.findIndex((n) => n.key === props.activeNode)
  const step = index < 0 ? 0 : index + 1
  return `Step ${step} of ${props.nodes.length}`
})
</script>

<style scoped>
.process-rail {
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg, 14px);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}

.rail-progress {
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.rail-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.rail-progress-head strong {
  font-size: 13px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  font-variant-numeric: tabular-nums;
}
.rail-progress-track {
  height: 6px;
  margin-top: 9px;
  border-radius: 999px;
  background: var(--cpq-overlay-w10);
  overflow: hidden;
}
.rail-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--cpq-accent-primary), #8b5cf6);
  transition: width 0.35s ease;
}
.rail-progress-label {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rail-progress-step {
  margin: 6px 0 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
}

.rail-steps {
  list-style: none;
  margin: 0;
  padding: 8px;
}
.rail-step {
  border-radius: 10px;
  margin-bottom: 4px;
}
.rail-step-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--cpq-text-muted);
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
.rail-step-head:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.rail-step-head:hover:not(:disabled) {
  background: var(--cpq-overlay-w3);
  color: var(--cpq-text-primary);
}
.rail-step-index {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: var(--cpq-overlay-w10);
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.rail-step-copy {
  flex: 1;
  min-width: 0;
}
.rail-step-copy b {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rail-step-copy span {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rail-step.active .rail-step-head {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
}
.rail-step.done .rail-step-index {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}
.rail-step-index.done {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}
.rail-step.done .rail-step-head {
  color: var(--cpq-text-primary);
}

.rail-substeps {
  padding: 2px 10px 10px 42px;
}
.rail-substep {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 5px 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--cpq-text-secondary);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.rail-substep:hover {
  background: var(--cpq-overlay-w3);
  color: var(--cpq-text-primary);
}
.rail-substep-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  border-radius: 999px;
  background: var(--cpq-accent-primary);
}
.rail-substep-check {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  color: var(--cpq-color-success);
  font-size: 12px;
}
</style>
