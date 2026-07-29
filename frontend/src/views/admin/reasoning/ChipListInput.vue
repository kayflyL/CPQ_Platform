<script setup lang="ts">
/** ChipListInput — 多 tag 输入（回车/逗号添加、× 删除、blur 落入）。
 *  extract 节点品类触发词、系列触发词用。Glass Console 风格。
 *  v-model:modelValue 绑定 string[]。 */
import { ref, computed } from 'vue'

const props = defineProps<{
  modelValue: string[]
  placeholder?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [string[]] }>()

const input = ref('')
const items = computed(() => props.modelValue || [])

function add() {
  const v = input.value.trim()
  if (!v) return
  if (!items.value.includes(v)) {
    emit('update:modelValue', [...items.value, v])
  }
  input.value = ''
}
function remove(idx: number) {
  const next = [...items.value]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    add()
  }
}
</script>

<template>
  <div class="chip-list-input">
    <span v-for="(t, i) in items" :key="`${t}-${i}`" class="chip-tag">
      <span class="chip-label">{{ t }}</span>
      <button type="button" class="chip-x" aria-label="删除" @click="remove(i)">×</button>
    </span>
    <input
      v-model="input"
      :placeholder="placeholder || '输入后回车添加'"
      class="chip-box"
      @keydown="onKeydown"
      @blur="add"
    />
  </div>
</template>

<style scoped>
.chip-list-input {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 6px 8px;
  border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w3, transparent);
  border: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.11));
}
.chip-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  padding: 1px 4px 1px 8px;
  border-radius: 6px;
  background: var(--cpq-overlay-w8, rgba(22, 119, 255, 0.08));
  color: var(--cpq-accent-primary, #1677ff);
}
.chip-label { line-height: 20px; }
.chip-x {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  line-height: 18px;
  width: 16px;
  color: var(--cpq-text-muted);
  padding: 0;
}
.chip-x:hover { color: var(--cpq-accent-danger, #ff6b6b); }
.chip-box {
  flex: 1;
  min-width: 120px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12px;
  color: var(--cpq-text-primary);
}
.chip-box::placeholder { color: var(--cpq-text-muted); }
</style>
