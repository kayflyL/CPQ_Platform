<script setup lang="ts">
/** JsonRowEditor — 通用行式编辑器：把「对象数组」JSON（如 char_fixes / noise_patterns / cpu_mem_type_rules）
 *  结构化成表格行，替代手写 JSON 文本框（P2a：业务用户不用再写 JSON）。
 *  v-model = Record<string, any>[]（行对象数组）；列由 columns 声明。
 *  复杂结构（嵌套/自由 JSON）仍保留 JSON 兜底折叠项。 */
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'

export interface RowColumn {
  key: string
  label?: string
  placeholder?: string
  type?: 'text' | 'select'
  options?: { value: string; label: string }[]
  width?: number
}

const props = withDefaults(defineProps<{
  modelValue: Record<string, any>[]
  columns: RowColumn[]
  addLabel?: string
  hint?: string
}>(), {
  addLabel: '＋ 添加一行',
  hint: '',
})

const emit = defineEmits<{ 'update:modelValue': [Record<string, any>[]] }>()

function patch(idx: number, k: string, v: any) {
  emit('update:modelValue', props.modelValue.map((r, i) => (i === idx ? { ...r, [k]: v } : r)))
}
function addRow() {
  const row: Record<string, any> = {}
  props.columns.forEach((c) => { row[c.key] = '' })
  emit('update:modelValue', [...props.modelValue, row])
}
function removeRow(idx: number) {
  emit('update:modelValue', props.modelValue.filter((_, i) => i !== idx))
}
</script>

<template>
  <div class="jr-editor">
    <p v-if="hint" class="jr-hint">{{ hint }}</p>
    <div v-for="(row, idx) in modelValue" :key="idx" class="jr-row">
      <template v-for="c in columns" :key="c.key">
        <a-input
          v-if="c.type !== 'select'"
          :value="row[c.key] ?? ''"
          :placeholder="c.placeholder || c.label || c.key"
          size="small"
          class="jr-field"
          :style="c.width ? `width:${c.width}px` : ''"
          @update:value="patch(idx, c.key, $event)"
        />
        <a-select
          v-else
          :value="row[c.key] || undefined"
          :options="c.options"
          :placeholder="c.placeholder || c.label || c.key"
          size="small"
          allow-clear
          class="jr-field jr-select"
          @update:value="patch(idx, c.key, ($event as string) || '')"
        />
      </template>
      <a-button type="text" size="small" danger class="jr-del" @click="removeRow(idx)">
        <DeleteOutlined />
      </a-button>
    </div>
    <a-button type="dashed" size="small" block @click="addRow">
      <PlusOutlined /> {{ addLabel }}
    </a-button>
  </div>
</template>

<style scoped>
.jr-editor { display: flex; flex-direction: column; gap: 8px; }
.jr-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 0 0 2px; }
.jr-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px; border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w3, transparent);
  border: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.11));
}
.jr-field { flex: 1; min-width: 90px; }
.jr-select { flex: 0 0 130px; }
.jr-del { flex: 0 0 auto; }
</style>
