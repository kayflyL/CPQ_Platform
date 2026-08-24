<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{ id: string; data: any; selected?: boolean }>()

const isUser = computed(() => props.data?.kind === 'user')
const isLead = computed(() => !!props.data?.isLead)
const isRoot = computed(() => !!props.data?.isRoot)
const isLeaf = computed(() => !!props.data?.isLeaf)
const color = computed(() => props.data?.color || '#1677ff')
const label = computed(() => props.data?.label || props.id)
const sublabel = computed(() => props.data?.sublabel || '')
</script>

<template>
  <div
    class="office-flow-node"
    :class="{ selected, 'is-user': isUser, 'is-lead': isLead }"
    :style="{ '--node-color': color }"
  >
    <Handle v-if="!isRoot" type="target" :position="Position.Top" class="office-flow-handle" />
    <Handle v-if="!isLeaf" type="source" :position="Position.Bottom" class="office-flow-handle" />

    <div class="flow-avatar" :style="{ background: color }">
      <span v-if="isUser">U</span>
      <span v-else>{{ Array.from(label)[0] || 'AI' }}</span>
    </div>
    <div class="flow-main">
      <div class="flow-label">{{ label }}</div>
      <div class="flow-sublabel">{{ sublabel }}</div>
      <div class="flow-tags">
        <span v-if="isUser" class="flow-tag">Human</span>
        <span v-else-if="isLead" class="flow-tag flow-tag--lead">Lead</span>
        <span v-else class="flow-tag">AI Colleague</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.office-flow-node {
  min-width: 220px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border: 2px solid var(--node-color, #1677ff);
  border-radius: 14px;
  background: var(--cpq-bg-elevated, #101722);
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.14);
  transition: transform .18s ease, box-shadow .18s ease, opacity .18s ease;
}

.office-flow-node.selected {
  box-shadow: 0 12px 28px rgba(0,0,0,0.22), 0 0 0 4px color-mix(in srgb, var(--node-color, #1677ff) 22%, transparent);
}

.office-flow-node.is-user {
  border-style: dashed;
}

.flow-avatar {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 800;
  flex-shrink: 0;
}

.flow-main {
  min-width: 0;
  flex: 1;
}

.flow-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.flow-sublabel {
  margin-top: 2px;
  font-size: 10px;
  color: var(--cpq-text-muted);
  font-family: ui-monospace, monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.flow-tags {
  margin-top: 7px;
  display: flex;
  gap: 4px;
}

.flow-tag {
  display: inline-flex;
  height: 18px;
  padding: 0 7px;
  align-items: center;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 800;
  text-transform: uppercase;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w8, rgba(255,255,255,0.08));
}

.flow-tag--lead {
  color: var(--node-color, #1677ff);
  background: color-mix(in srgb, var(--node-color, #1677ff) 14%, transparent);
}

.office-flow-handle {
  width: 10px !important;
  height: 10px !important;
  background: var(--cpq-accent-primary, #1677ff) !important;
  border: 2px solid var(--cpq-bg-elevated, #101722) !important;
}
</style>
