<script lang="ts">
/** EditableKVTable — 行式键值表。value 支持 chips（多 tag）或 select（单选）。
 *  P1 品类词表（value=chips）、P2 关键词→系列映射（value=select）用。
 *  v-model:modelValue 绑定 KVRow[]。 */
export interface KVRow {
  key: string
  value: string | string[]
}
export type KVValueMode = 'chips' | 'select'
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import ChipListInput from './ChipListInput.vue'

const props = withDefaults(
  defineProps<{
    modelValue: KVRow[]
    valueMode?: KVValueMode
    selectOptions?: { value: string; label: string }[]
    keyPlaceholder?: string
    valuePlaceholder?: string
  }>(),
  {
    valueMode: 'chips',
    keyPlaceholder: '键',
    valuePlaceholder: '值',
  },
)
const emit = defineEmits<{ 'update:modelValue': [KVRow[]] }>()

const rows = computed(() => props.modelValue || [])

function patch(idx: number, kv: Partial<KVRow>) {
  const next = rows.value.map((r, i) => (i === idx ? { ...r, ...kv } : r))
  emit('update:modelValue', next)
}
function updateKey(idx: number, key: string) {
  patch(idx, { key })
}
function updateValue(idx: number, value: string | string[]) {
  patch(idx, { value })
}
function addRow() {
  const value: string | string[] = props.valueMode === 'select' ? '' : []
  emit('update:modelValue', [...rows.value, { key: '', value }])
}
function removeRow(idx: number) {
  const next = [...rows.value]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="kv-table">
    <div v-for="(row, idx) in rows" :key="idx" class="kv-row">
      <a-input
        :value="row.key"
        :placeholder="keyPlaceholder"
        size="small"
        class="kv-key"
        @update:value="updateKey(idx, $event)"
      />
      <div class="kv-value">
        <ChipListInput
          v-if="valueMode !== 'select'"
          :model-value="(Array.isArray(row.value) ? row.value : []) as string[]"
          :placeholder="valuePlaceholder"
          @update:model-value="updateValue(idx, $event)"
        />
        <a-select
          v-else
          :value="(row.value as string) || undefined"
          :options="selectOptions"
          :placeholder="valuePlaceholder"
          size="small"
          allow-clear
          class="kv-select"
          @update:value="updateValue(idx, ($event as string) || '')"
        />
      </div>
      <a-button type="text" size="small" danger class="kv-del" @click="removeRow(idx)">
        <DeleteOutlined />
      </a-button>
    </div>
    <a-button type="dashed" size="small" block class="kv-add" @click="addRow">
      <PlusOutlined /> 增加一行
    </a-button>
  </div>
</template>

<style scoped>
.kv-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kv-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w3, transparent);
  border: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.11));
}
.kv-key {
  flex: 0 0 150px;
}
.kv-value {
  flex: 1;
  min-width: 0;
}
.kv-select {
  width: 100%;
}
.kv-del {
  flex: 0 0 auto;
  margin-top: 2px;
}
.kv-add {
  margin-top: 2px;
}
</style>
