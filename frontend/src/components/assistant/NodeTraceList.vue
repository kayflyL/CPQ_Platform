<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NodeTrace } from '@/composables/assistantChatWs'

const props = defineProps<{ traces: NodeTrace[] }>()

const expanded = ref<Record<string, boolean>>({})

const visible = computed(() => (props.traces || []).filter((t) => t?.status !== 'done' || t?.output || t?.input || t?.summary || t?.artifact))

function toggle(step: string) {
  expanded.value = { ...expanded.value, [step]: !expanded.value[step] }
}

function fmtVal(v: any): string {
  if (v === undefined || v === null || v === '') return '—'
  if (Array.isArray(v)) return v.length ? `${v.length} 项` : '[]'
  if (typeof v === 'object') {
    try { return JSON.stringify(v).slice(0, 200) } catch { return String(v) }
  }
  return String(v).slice(0, 200)
}

function rowsOf(v: any): [string, any][] {
  if (v && typeof v === 'object' && !Array.isArray(v)) return Object.entries(v)
  return v === undefined || v === null ? [] : [['result', v]]
}
</script>

<template>
  <div v-if="visible.length" class="node-trace-list">
    <div v-for="trace in visible" :key="trace.step" class="node-trace-card">
      <button type="button" class="node-trace-head" @click="toggle(trace.step)">
        <span class="node-trace-dot" :class="{ done: trace.status === 'done' }"></span>
        <span class="node-trace-label">{{ trace.label }}</span>
        <span class="node-trace-chevron" :class="{ open: expanded[trace.step] }">▾</span>
      </button>
      <div v-if="expanded[trace.step]" class="node-trace-body">
        <div v-if="rowsOf(trace.input).length" class="node-trace-block in">
          <div class="node-trace-block-title">← 上游输入</div>
          <div v-for="[k, v] in rowsOf(trace.input)" :key="k" class="node-trace-row">
            <span class="node-trace-k">{{ k }}</span><span class="node-trace-v">{{ fmtVal(v) }}</span>
          </div>
        </div>
        <div v-if="trace.summary" class="node-trace-block summary">
          <div class="node-trace-block-title">⚙ 处理摘要</div>
          <div class="node-trace-summary-text">{{ trace.summary }}</div>
        </div>
        <div v-if="rowsOf(trace.output).length" class="node-trace-block out">
          <div class="node-trace-block-title">→ 产出 / 下游交接</div>
          <div v-for="[k, v] in rowsOf(trace.output)" :key="k" class="node-trace-row">
            <span class="node-trace-k">{{ k }}</span><span class="node-trace-v">{{ fmtVal(v) }}</span>
          </div>
        </div>
        <div v-if="trace.artifact" class="node-trace-artifact">
          <span class="node-trace-artifact-title">{{ trace.artifact.title }}</span>
          <span class="node-trace-artifact-kind">{{ trace.artifact.kind }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.node-trace-list { display: flex; flex-direction: column; gap: 6px; margin: 6px 0; }
.node-trace-card { border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,.12)); border-radius: 10px; overflow: hidden; background: var(--cpq-glass-card-bg, rgba(255,255,255,.03)); }
.node-trace-head { display: flex; align-items: center; gap: 7px; width: 100%; padding: 7px 9px; border: 0; background: transparent; color: var(--cpq-text-primary); cursor: pointer; font-size: 12px; text-align: left; }
.node-trace-head:hover { background: var(--cpq-overlay-w6, rgba(255,255,255,.05)); }
.node-trace-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--cpq-accent-warning, #fa8c16); flex: none; }
.node-trace-dot.done { background: var(--cpq-color-success, #52C9A0); }
.node-trace-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-trace-chevron { color: var(--cpq-text-muted); transition: transform .15s ease; font-size: 10px; }
.node-trace-chevron.open { transform: rotate(180deg); }
.node-trace-body { padding: 0 9px 9px; border-top: 1px solid var(--cpq-border-secondary, rgba(255,255,255,.08)); }
.node-trace-block { margin-top: 8px; padding: 6px 7px; border-radius: 7px; font-size: 10px; }
.node-trace-block.in { background: rgba(22,119,255,.05); border: 1px solid rgba(22,119,255,.18); }
.node-trace-block.summary { background: rgba(250,140,22,.05); border: 1px solid rgba(250,140,22,.18); }
.node-trace-block.out { background: rgba(82,201,160,.05); border: 1px solid rgba(82,201,160,.16); }
.node-trace-block-title { color: var(--cpq-text-muted); font-weight: 600; margin-bottom: 4px; }
.node-trace-summary-text { color: var(--cpq-text-primary); line-height: 1.5; font-size: 11px; }
.node-trace-row { display: flex; justify-content: space-between; gap: 8px; margin-top: 3px; }
.node-trace-k { color: var(--cpq-text-secondary); flex: none; }
.node-trace-v { color: var(--cpq-text-primary); text-align: right; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-trace-artifact { margin-top: 8px; display: flex; align-items: center; gap: 6px; font-size: 10px; }
.node-trace-artifact-title { color: #9ec5ff; background: var(--cpq-overlay-a10); border: 1px solid rgba(22,119,255,.18); padding: 2px 7px; border-radius: 999px; }
.node-trace-artifact-kind { color: var(--cpq-text-muted); }
</style>
