<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{ source?: string }>()

const html = computed(() => {
  const src = props.source || ''
  const raw = marked.parse(src, { breaks: true, gfm: true }) as string
  return DOMPurify.sanitize(raw)
})
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md { color: var(--cpq-text-primary); font-size: 14px; line-height: 1.9; }
.md :deep(h1) { font-size: 22px; font-weight: 800; letter-spacing: -.4px; margin: 26px 0 14px; }
.md :deep(h2) { font-size: 20px; font-weight: 800; letter-spacing: -.4px; margin: 30px 0 14px; color: var(--cpq-text-primary); }
.md :deep(h3) { font-size: 16px; font-weight: 700; margin: 20px 0 10px; }
.md :deep(p) { color: var(--cpq-text-secondary); margin: 0 0 14px; }
.md :deep(ul), .md :deep(ol) { margin: 0 0 16px; padding-left: 22px; }
.md :deep(li) { color: var(--cpq-text-secondary); margin: 7px 0; }
.md :deep(li::marker) { color: var(--cpq-accent-primary); }
.md :deep(strong) { color: var(--cpq-text-primary); font-weight: 700; }
.md :deep(em) { color: var(--cpq-text-secondary); }
.md :deep(code) { background: var(--cpq-overlay-w6); padding: 1px 6px; border-radius: 6px; font-size: 12.5px; color: var(--cpq-accent-primary); }
.md :deep(pre) { background: var(--cpq-overlay-w8); padding: 14px; border-radius: 12px; overflow: auto; }
.md :deep(a) { color: var(--cpq-accent-primary); }
.md :deep(blockquote) { border-left: 3px solid var(--cpq-accent-primary); margin: 16px 0; padding: 6px 16px; color: var(--cpq-text-secondary); background: var(--cpq-overlay-a10); border-radius: 0 10px 10px 0; }
.md :deep(hr) { border: none; border-top: 1px solid var(--cpq-glass-border); margin: 24px 0; }
</style>
