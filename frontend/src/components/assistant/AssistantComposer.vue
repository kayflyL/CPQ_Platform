<template>
  <div class="ac-composer">
    <a-textarea
      :value="modelValue"
      :auto-size="{ minRows: 1, maxRows: 4 }"
      :placeholder="placeholder"
      :disabled="disabled"
      @update:value="$emit('update:modelValue', $event)"
      @press-enter="onEnter"
    />
    <a-button
      type="primary"
      :disabled="disabled || (!busy && !modelValue.trim())"
      @click="busy ? $emit('stop') : $emit('send')"
    >
      {{ busy ? '停止' : buttonText }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
  sending?: boolean
  running?: boolean
  buttonText?: string
}>(), {
  placeholder: '输入消息…',
  disabled: false,
  sending: false,
  running: false,
  buttonText: '发送',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
}>()

const busy = computed(() => props.sending || props.running)

function onEnter(event: KeyboardEvent) {
  if (event.shiftKey) return
  event.preventDefault()
  emit('send')
}
</script>

<style scoped>
.ac-composer {
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  display: flex;
  gap: 8px;
  align-items: flex-end;
  background: var(--cpq-overlay-w3, rgba(255, 255, 255, 0.04));
}

.ac-composer :deep(.ant-input) {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  border-color: var(--cpq-overlay-w8, rgba(255, 255, 255, 0.12));
  color: var(--cpq-text-primary, #f5f7fa);
}

.ac-composer :deep(.ant-input::placeholder) {
  color: var(--cpq-text-muted, #9aa4b2);
}
</style>
