<script setup lang="ts">
/** 兼容性影响图的节点（vue-flow 自定义节点）。配色复用 selectionConfig 品类色。 */
import { computed } from 'vue'
import { getCategoryStyle } from './selection/selectionConfig'

const props = defineProps<{ id?: string; data?: { label?: string; note?: string } }>()

const label = computed(() => props.data?.label || '')
const st = computed(() => getCategoryStyle(label.value))
const isCtx = computed(() => props.data?.note === 'ctx')
</script>

<template>
  <div
    class="impact-node"
    :class="{ ctx: isCtx }"
    :style="{ background: st.bg, borderColor: st.border, color: st.text }"
  >
    <span class="im-dot" :style="{ background: st.border }"></span>
    <span class="im-label">{{ label }}</span>
  </div>
</template>

<style scoped>
.impact-node {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; border: 1.5px solid; border-radius: 10px;
  min-width: 120px; font-size: 13px; font-weight: 600;
}
.impact-node.ctx { border-style: dashed; font-weight: 500; }
.im-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.im-label { white-space: nowrap; }
</style>
