<template>
  <button
    class="assistant-fab"
    :class="{ open }"
    @click="$emit('update:open', !open)"
    :title="open ? '收起方案助手' : '方案助手'"
  >
    <CloseOutlined v-if="open" />
    <RobotOutlined v-else />
    <span v-if="!open" class="fab-label">方案助手</span>
  </button>
</template>

<script setup lang="ts">
import { RobotOutlined, CloseOutlined } from '@ant-design/icons-vue'
defineProps<{ open: boolean }>()
defineEmits<{ (e: 'update:open', v: boolean): void }>()
</script>

<style scoped>
.assistant-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  height: 52px;
  min-width: 52px;
  padding: 0 20px;
  border-radius: 26px;
  border: 1px solid var(--cpq-overlay-a30, transparent);
  background: var(--cpq-accent-primary);
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  z-index: 1500;
  box-shadow: 0 8px 24px var(--cpq-shadow-color-strong, rgba(0, 0, 0, 0.25));
  transition: transform var(--cpq-transition-fast, 0.2s), box-shadow var(--cpq-transition-fast, 0.2s);
}
.assistant-fab:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3), 0 0 24px var(--cpq-overlay-a40, transparent);
}
.assistant-fab.open {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
  border-color: var(--cpq-glass-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.fab-label {
  font-size: 14px;
  font-weight: 600;
}
</style>
