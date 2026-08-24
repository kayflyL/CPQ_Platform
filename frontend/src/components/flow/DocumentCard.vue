<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  docNo?: string
  status?: string
  statusTone?: 'current' | 'draft' | 'done' | 'pending' | 'exported' | 'released'
  docType?: 'requirement' | 'bom' | 'cost' | 'quote'
  active?: boolean
}>(), {
  docNo: '',
  status: '',
  statusTone: 'current',
  docType: 'requirement',
  active: false,
})

const emit = defineEmits<{ (e: 'click'): void }>()

const toneClass = computed(() => `doc-${props.statusTone || 'current'}`)
</script>

<template>
  <article
    class="doc-card"
    :class="[`doc-type-${docType}`, { active }]"
    role="button"
    tabindex="0"
    @click="emit('click')"
    @keydown.enter.prevent="emit('click')"
    @keydown.space.prevent="emit('click')"
  >
    <div class="doc-sheet">
      <header class="doc-head">
        <div class="doc-title">
          <h3>{{ title }}</h3>
          <p v-if="docNo">{{ docNo }}</p>
        </div>
        <span v-if="status" class="doc-stamp" :class="toneClass">{{ status }}</span>
      </header>

      <div v-if="$slots.meta || $slots.summary" class="doc-body">
        <div v-if="$slots.meta" class="doc-meta"><slot name="meta" /></div>
        <div v-if="$slots.summary" class="doc-summary"><slot name="summary" /></div>
      </div>

      <footer v-if="$slots.footer" class="doc-footer"><slot name="footer" /></footer>
    </div>
  </article>
</template>

<style scoped>
.doc-card {
  position: relative;
  z-index: 1;
  height: 100%;
  outline: none;
  background: transparent;
  transition: transform .2s ease;
}

.doc-card:hover {
  transform: translateY(-2px);
}

.doc-card::before,
.doc-card::after {
  content: "";
  position: absolute;
  left: 8px;
  right: 8px;
  height: 10px;
  border: 1px solid var(--cpq-glass-border);
  z-index: -1;
}

.doc-card::before {
  bottom: -6px;
  background: var(--cpq-overlay-w6);
  opacity: .7;
}

.doc-card::after {
  bottom: -3px;
  background: var(--cpq-glass-card-bg);
  opacity: .85;
}

.doc-sheet {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 300px;
  overflow: hidden;
  border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-card-bg);
  box-shadow: var(--cpq-glass-card-shadow);
  transition: border-color .2s ease, box-shadow .2s ease;
}

.doc-card:hover .doc-sheet,
.doc-card.active .doc-sheet {
  border-color: var(--cpq-accent-primary);
  box-shadow: 0 0 0 2px var(--cpq-overlay-a16), var(--cpq-glass-card-shadow);
}

.doc-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 16px 16px 13px;
  border-bottom: 1px solid var(--cpq-glass-border);
}

.doc-title {
  min-width: 0;
  flex: 1;
}

.doc-title h3 {
  margin: 0 0 5px;
  color: var(--cpq-text-primary);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.4;
}

.doc-title p {
  margin: 0;
  color: var(--cpq-text-muted);
  font-size: 11px;
  letter-spacing: .4px;
  word-break: break-all;
}

.doc-stamp {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.doc-stamp::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.doc-stamp.doc-current { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); }
.doc-stamp.doc-draft { color: #b45309; border-color: #f59e0b; background: rgba(245,158,11,.10); }
.doc-stamp.doc-done,
.doc-stamp.doc-exported,
.doc-stamp.doc-released { color: #166534; border-color: #22c55e; background: rgba(34,197,94,.10); }
.doc-stamp.doc-pending { color: #7c3aed; border-color: #8b5cf6; background: rgba(139,92,246,.10); }

.doc-body {
  flex: 1;
  min-height: 0;
  padding: 0 16px;
}

.doc-meta {
  padding: 12px 0;
}

.doc-summary {
  margin: 12px 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.doc-summary :deep(b) {
  color: var(--cpq-text-primary);
}

.doc-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
  padding: 11px 16px;
  border-top: 1px solid var(--cpq-glass-border);
}
</style>
