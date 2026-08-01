<script setup lang="ts">
/** 定价流水线节点（vue-flow 自定义节点）。
 *  kind：input(商机属性/成本) / dim(维度) / output(目标毛利率)。
 *  dim 节点按 opKind(base/add/mult/clamp) 取强调色，显示维度名 + 当前系数摘要。 */
import { computed } from 'vue'
import type { OpKind } from '@/constants/pricingMeta'

const props = defineProps<{
  id?: string
  data?: { kind?: 'input' | 'dim' | 'output'; dimKey?: string; label?: string; opKind?: OpKind; sign?: string; summary?: string }
}>()

const ACCENT: Record<OpKind, string> = { base: '#1677ff', add: '#52c9a0', mult: '#fa8c16', clamp: '#8b5cf6' }
const accent = computed(() => (props.data?.opKind ? ACCENT[props.data.opKind] : '#1677ff'))
const kind = computed(() => props.data?.kind || 'dim')
</script>

<template>
  <div class="dim-node" :class="`kind-${kind}`" :style="{ '--accent': accent }">
    <template v-if="kind === 'dim'">
      <div class="dn-head">
        <span class="dn-sign" :style="{ background: accent }">{{ data?.sign }}</span>
        <span class="dn-title">{{ data?.label }}</span>
        <span class="dn-edit">⚙</span>
      </div>
      <div v-if="data?.summary" class="dn-summary">{{ data.summary }}</div>
    </template>
    <div v-else class="dn-io">
      <span class="dn-io-icon">{{ kind === 'input' ? '📥' : '🎯' }}</span>
      {{ data?.label }}
    </div>
  </div>
</template>

<style scoped>
.dim-node {
  min-width: 168px; max-width: 200px; text-align: left;
  padding: 8px 12px; border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-overlay-w8, rgba(255, 255, 255, .72));
  border: 1px solid var(--cpq-glass-border, rgba(0, 0, 0, .1));
  box-shadow: 0 1px 4px rgba(0, 0, 0, .05);
  cursor: pointer;
  transition: box-shadow .15s, border-color .15s;
}
.dim-node:hover { border-color: var(--accent); box-shadow: 0 2px 10px color-mix(in srgb, var(--accent) 25%, transparent); }

.dn-head { display: flex; align-items: center; gap: 6px; }
.dn-sign { flex: none; width: 18px; height: 18px; border-radius: 6px; color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.dn-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.dn-edit { margin-left: auto; font-size: 12px; color: var(--cpq-text-muted); opacity: .6; }
.dn-summary {
  margin-top: 5px; font-size: 11px; line-height: 1.5; color: var(--cpq-text-secondary);
  font-family: ui-monospace, monospace; word-break: break-all;
}

/* input/output 节点：胶囊形 */
.kind-input, .kind-output {
  min-width: 120px; display: inline-flex; align-items: center; justify-content: center;
  border-radius: 999px; padding: 8px 16px;
  background: color-mix(in srgb, var(--accent) 14%, var(--cpq-overlay-w8, rgba(255, 255, 255, .85)));
  border-color: var(--accent);
}
.dn-io { font-size: 12px; font-weight: 600; color: var(--accent); white-space: nowrap; display: flex; align-items: center; gap: 4px; }
.kind-output .dn-io { font-size: 13px; }
</style>
