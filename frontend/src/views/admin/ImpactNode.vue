<script setup lang="ts">
/** 兼容性影响图的节点（vue-flow 自定义节点）。
 *  单条规则因果流：kind 决定样式变体（when 条件 / action 动作枢纽 / then 结果）。
 *  accent 为强调色（动作类型色），badge 为动作徽章文字，title/subtitle 展示具体字段与算式。 */
import { computed } from 'vue'
import { RULE_GRAPH_TEXT as T } from '@/constants/ruleMeta'

const props = defineProps<{ id?: string; data?: { kind?: string; title?: string; subtitle?: string; accent?: string; badge?: string } }>()

const accent = computed(() => props.data?.accent || '#1677ff')
const kind = computed(() => props.data?.kind || 'when')
</script>

<template>
  <div class="impact-node" :class="`kind-${kind}`" :style="{ '--accent': accent }">
    <span v-if="kind === 'when'" class="in-pill">{{ T.whenPill }}</span>
    <span v-else-if="kind === 'then'" class="in-pill">{{ T.thenPill }}</span>
    <span v-else class="in-pill in-pill-action">{{ data?.badge }}</span>
    <div class="in-main">
      <div class="in-title">{{ data?.title }}</div>
      <div v-if="data?.subtitle" class="in-sub">{{ data.subtitle }}</div>
    </div>
  </div>
</template>

<style scoped>
.impact-node {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border: 1.5px solid; border-radius: 10px;
  min-width: 128px; text-align: left;
  background: var(--cpq-overlay-w8, rgba(255,255,255,.7));
  border-color: var(--cpq-overlay-a15, rgba(0,0,0,.12));
  color: var(--cpq-text-primary, #1f2329);
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.in-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.in-title { font-size: 13px; font-weight: 600; white-space: nowrap; }
.in-sub { font-size: 11px; font-weight: 500; color: var(--cpq-text-secondary, #6b7280); white-space: nowrap; font-family: ui-monospace, monospace; }
.in-pill {
  flex: none; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 6px;
  background: var(--cpq-overlay-a10, rgba(0,0,0,.06)); color: var(--cpq-text-muted, #86909c);
  white-space: nowrap;
}

/* when 条件节点：中性左边框 */
.impact-node.kind-when { border-left: 3px solid var(--cpq-text-secondary, #8a909a); }

/* action 动作枢纽节点：动作色强调 */
.impact-node.kind-action {
  border-color: var(--accent); border-width: 2px;
  background: color-mix(in srgb, var(--accent) 12%, var(--cpq-overlay-w8, rgba(255,255,255,.85)));
}
.impact-node.kind-action .in-pill-action { background: var(--accent); color: #fff; }
.impact-node.kind-action .in-title { color: var(--accent); }

/* then 结果节点：动作色左边框 */
.impact-node.kind-then { border-left: 3px solid var(--accent); }
</style>
