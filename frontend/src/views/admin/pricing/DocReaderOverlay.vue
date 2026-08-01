<script setup lang="ts">
/** 文档阅读浮窗 —— 点文档卡居中弹出,磨砂玻璃遮罩 + scale/fade 柔和入场(呼吸感)。
 *  不用 a-modal 以精确控制呼吸动画;Esc / 点遮罩 / ✕ 关闭。尊重 prefers-reduced-motion。 */
import { computed, watch, onBeforeUnmount } from 'vue'
import type { Strategy } from '@/api/strategies'
import { readDocBody } from '@/constants/policyMeta'
import MarkdownView from '@/components/common/MarkdownView.vue'

const props = defineProps<{ doc: Strategy | null }>()
const emit = defineEmits<{ close: [] }>()

const body = computed(() => (props.doc ? readDocBody(props.doc.body) : null))

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
watch(
  () => props.doc,
  (d) => {
    if (d) document.addEventListener('keydown', onKey)
    else document.removeEventListener('keydown', onKey)
  },
)
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

function fmtDate(s: string | null) {
  return s ? s.replace('T', ' ').slice(0, 16) : '—'
}
</script>

<template>
  <Teleport to="body">
    <transition name="doc">
      <div v-if="doc && body" class="doc-overlay" @click.self="emit('close')">
        <div class="doc-window glass-strong" role="dialog" aria-modal="true">
          <header class="dw-head">
            <h2 class="dw-title">{{ doc.name }}</h2>
            <button class="dw-close" aria-label="关闭" @click="emit('close')">✕</button>
          </header>
          <div class="dw-sub">
            <span class="dw-cat">{{ body.category }}</span>
            <span>v{{ doc.version }}</span>
            <span>{{ fmtDate(doc.updated_at) }}</span>
            <span>by {{ doc.updated_by }}</span>
            <span v-if="doc.status !== 'active'" class="dw-status" :data-status="doc.status">{{ doc.status }}</span>
          </div>
          <div v-if="doc.description" class="dw-desc">{{ doc.description }}</div>
          <div class="dw-body">
            <MarkdownView :content="body.content_markdown" />
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.doc-overlay {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  background: color-mix(in srgb, var(--cpq-bg-primary, #1a1d24) 55%, transparent);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.doc-window {
  width: min(880px, 100%);
  max-height: min(86vh, 920px);
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  border: 1px solid var(--cpq-glass-border);
  box-shadow: var(--cpq-shadow-lg, 0 20px 60px rgba(0, 0, 0, 0.3)), inset 0 1px 0 var(--cpq-glass-highlight, rgba(255, 255, 255, 0.08));
  overflow: hidden;
}

/* 呼吸入场:遮罩 fade + 窗口 scale(.96→1) */
.doc-enter-active, .doc-leave-active { transition: opacity 0.22s ease; }
.doc-enter-from, .doc-leave-to { opacity: 0; }
.doc-enter-active .doc-window, .doc-leave-active .doc-window {
  transition: transform 0.24s cubic-bezier(0.2, 0.8, 0.3, 1), opacity 0.22s ease;
}
.doc-enter-from .doc-window, .doc-leave-to .doc-window { transform: scale(0.96); opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .doc-enter-active, .doc-leave-active, .doc-enter-active .doc-window, .doc-leave-active .doc-window { transition-duration: 0.01ms; }
  .doc-enter-from .doc-window, .doc-leave-to .doc-window { transform: none; }
}

.dw-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 10px;
}
.dw-title { font-size: 19px; font-weight: 600; color: var(--cpq-text-primary); margin: 0; line-height: 1.4; }
.dw-close {
  flex-shrink: 0;
  width: 28px; height: 28px;
  border: none;
  border-radius: 8px;
  background: var(--cpq-bg-tertiary);
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}
.dw-close:hover { background: var(--cpq-bg-secondary); color: var(--cpq-text-primary); }
.dw-sub {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 0 24px 8px;
  font-size: 12px;
  color: var(--cpq-text-muted);
  border-bottom: 1px solid var(--cpq-border-secondary);
  padding-bottom: 12px;
}
.dw-cat {
  font-weight: 600;
  color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w6);
  padding: 1px 9px;
  border-radius: 8px;
  font-size: 11px;
}
.dw-status { padding: 1px 6px; border-radius: 4px; background: var(--cpq-bg-tertiary); }
.dw-status[data-status='archived'] { text-decoration: line-through; }
.dw-desc { padding: 12px 24px 0; font-size: 12.5px; color: var(--cpq-text-secondary); }
.dw-body {
  padding: 16px 24px 28px;
  overflow-y: auto;
  flex: 1;
}
</style>
