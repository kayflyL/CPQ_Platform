<template>
  <nav class="process-rail glass" :class="{ 'is-collapsed': collapsed }">
    <div class="rail-expanded">
      <div class="rail-progress">
        <div class="rail-progress-head">
          <span>Overall Progress</span>
          <strong>{{ progressPercent }}%</strong>
        </div>
        <div class="rail-progress-track">
          <div class="rail-progress-fill" :style="{ width: `${progressPercent}%` }"></div>
        </div>
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

          <div v-if="node.key === activeNode" class="rail-stage">
            <div class="rail-stage-bar">
              <span class="rail-stage-count">{{ stageDone(node.key) }} / {{ stageTotal(node.key) }}</span>
              <span class="rail-stage-track">
                <i :style="{ width: `${stagePercentOf(node.key)}%` }"></i>
              </span>
              <span class="rail-stage-pct">{{ stagePercentOf(node.key) }}%</span>
            </div>
            <div class="rail-substeps">
              <button
                v-for="(sub, subIdx) in SUBSTEPS[node.key] || []"
                :key="sub"
                type="button"
                class="rail-substep"
                @click="emit('select-substep', node.key, subIdx)"
              >
                <span v-if="subDoneOf(node.key, subIdx)" class="rail-substep-check"><CheckCircleFilled /></span>
                <span v-else class="rail-substep-dot"></span>
                <span>{{ sub }}</span>
              </button>
            </div>
          </div>
        </li>
      </ol>

      <div v-if="ownerRows.length || updatedText" class="rail-foot">
        <div v-for="row in ownerRows" :key="row.label" class="rail-foot-row">
          <span>{{ row.label }}</span>
          <b :title="row.value">{{ row.value }}</b>
        </div>
        <div v-if="updatedText" class="rail-foot-time">最后更新 {{ updatedText }}</div>
      </div>
    </div>

    <div class="rail-icons">
      <button
        v-for="(node, idx) in nodes"
        :key="node.key"
        type="button"
        class="rail-icon"
        :class="[node.state, { viewing: node.key === activeNode }]"
        :disabled="disabled.has(node.key)"
        :title="`${node.title || node.label} · ${node.statusLabel}`"
        @click="emit('select', node.key)"
      >
        <CheckCircleFilled v-if="node.state === 'done'" />
        <template v-else>{{ String(idx + 1).padStart(2, '0') }}</template>
      </button>
    </div>
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
    collapsed?: boolean
    ownerRows?: { label: string; value: string }[]
    updatedText?: string
    // 每个节点各子步骤的完成标记；缺省时退回节点整体状态
    subDone?: Record<string, boolean[]>
  }>(),
  {
    disabledKeys: () => [],
    collapsed: false,
    ownerRows: () => [],
    updatedText: '',
    subDone: () => ({}),
  },
)

const emit = defineEmits<{
  (e: 'select', key: string): void
  (e: 'select-substep', key: string, index: number): void
}>()

// 小节点与中栏实体一一对应：第一段=工作卡，第二段=卡内「XX附件」抽屉
const SUBSTEPS: Record<string, string[]> = {
  requirement: ['商机信息', '需求单工作台'],
  boming: ['方案配置工作台', '方案附件'],
  costing: ['成本表工作台', '成本附件'],
  quoting: ['报价单工作区', '报价附件'],
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

function subList(key: string) {
  return SUBSTEPS[key] || []
}

function subDoneOf(key: string, index: number) {
  const flags = props.subDone[key]
  const total = subList(key).length
  if (flags && flags.length === total) return !!flags[index]
  const node = props.nodes.find((n) => n.key === key)
  return node?.state === 'done'
}

function stageTotal(key: string) {
  return subList(key).length
}

function stageDone(key: string) {
  return subList(key).filter((_, i) => subDoneOf(key, i)).length
}

function stagePercentOf(key: string) {
  const total = stageTotal(key)
  return total ? Math.round((stageDone(key) / total) * 100) : 0
}
</script>

<style scoped>
.process-rail {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg, 14px);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}

/* 展开态：进度头 + 可滚动步骤列表 + 底部信息区 */
.rail-expanded {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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

.rail-steps {
  list-style: none;
  margin: 0;
  padding: 8px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
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
.rail-step-index.current {
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
}
.rail-step-index.done {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}
.rail-step.done .rail-step-head {
  color: var(--cpq-text-primary);
}

/* 当前阶段：子步骤进度条 + 子步骤列表 */
.rail-stage {
  padding: 2px 10px 10px 42px;
}
.rail-stage-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: var(--cpq-text-muted);
  font-variant-numeric: tabular-nums;
}
.rail-stage-track {
  flex: 1;
  min-width: 0;
  height: 4px;
  border-radius: 999px;
  background: var(--cpq-overlay-w10);
  overflow: hidden;
}
.rail-stage-track i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--cpq-accent-primary);
  transition: width 0.35s ease;
}
.rail-stage-pct {
  font-weight: 700;
  color: var(--cpq-text-secondary);
}
.rail-substeps {
  padding: 6px 0 0;
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

/* 底部信息区 */
.rail-foot {
  padding: 10px 14px 12px;
  border-top: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.rail-foot-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.rail-foot-row + .rail-foot-row {
  margin-top: 5px;
}
.rail-foot-row b {
  font-weight: 600;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rail-foot-time {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--cpq-glass-border);
  font-size: 10px;
  color: var(--cpq-text-muted);
  font-variant-numeric: tabular-nums;
}

/* 折叠态：只留图标条 */
.rail-icons {
  display: none;
}
.process-rail.is-collapsed .rail-expanded {
  display: none;
}
.process-rail.is-collapsed .rail-icons {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex: 1;
  min-height: 0;
  padding: 12px 0;
}
.rail-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 9px;
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-muted);
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
.rail-icon:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
}
.rail-icon:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.rail-icon.done {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}
.rail-icon.current {
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
}
.rail-icon.viewing {
  border-color: var(--cpq-accent-primary);
}

/* 窄屏：看板已是单列堆叠，左栏强制展开 */
@media (max-width: 1080px) {
  .process-rail.is-collapsed .rail-expanded {
    display: flex;
  }
  .process-rail.is-collapsed .rail-icons {
    display: none;
  }
}
</style>
