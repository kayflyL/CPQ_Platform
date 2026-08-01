<script setup lang="ts">
/**
 * Markdown 渲染组件 —— marked 解析 + DOMPurify 防 XSS,Glass Console 排版。
 * 用于策略文档库阅读窗、编辑器实时预览。
 */
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: false })

const props = defineProps<{ content: string }>()

const html = computed(() => {
  if (!props.content?.trim()) return ''
  const raw = marked.parse(props.content, { async: false }) as string
  return DOMPurify.sanitize(raw, { ADD_ATTR: ['target'] })
})
</script>

<template>
  <div class="md-view" v-html="html" />
</template>

<style scoped>
.md-view {
  color: var(--cpq-text-primary);
  font-size: 14px;
  line-height: 1.75;
  word-break: break-word;
}
.md-view :deep(h1),
.md-view :deep(h2),
.md-view :deep(h3),
.md-view :deep(h4) {
  color: var(--cpq-text-primary);
  font-weight: 600;
  line-height: 1.4;
  margin: 1.4em 0 0.6em;
}
.md-view :deep(h1) { font-size: 20px; }
.md-view :deep(h2) { font-size: 17px; }
.md-view :deep(h3) { font-size: 15px; }
.md-view :deep(h4) { font-size: 14px; }
.md-view :deep(h1:first-child),
.md-view :deep(h2:first-child),
.md-view :deep(h3:first-child) { margin-top: 0; }
.md-view :deep(p) { margin: 0.6em 0; }
.md-view :deep(a) { color: var(--cpq-accent-primary); text-decoration: none; }
.md-view :deep(a:hover) { text-decoration: underline; }
.md-view :deep(strong) { color: var(--cpq-text-primary); font-weight: 600; }
.md-view :deep(ul),
.md-view :deep(ol) { padding-left: 1.4em; margin: 0.6em 0; }
.md-view :deep(li) { margin: 0.2em 0; }
.md-view :deep(li)::marker { color: var(--cpq-accent-primary); }

/* 引用块:左侧青色 accent 边 */
.md-view :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.4em 0.9em;
  border-left: 3px solid var(--cpq-accent-primary);
  background: var(--cpq-bg-tertiary);
  border-radius: 0 6px 6px 0;
  color: var(--cpq-text-secondary);
}
.md-view :deep(blockquote p) { margin: 0.2em 0; }

/* 代码:行内 + 块 */
.md-view :deep(code) {
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.9em;
  padding: 0.1em 0.4em;
  background: var(--cpq-bg-tertiary);
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 4px;
  color: var(--cpq-accent-primary);
}
.md-view :deep(pre) {
  margin: 0.8em 0;
  padding: 0.8em 1em;
  background: var(--cpq-bg-tertiary);
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 8px;
  overflow-x: auto;
}
.md-view :deep(pre code) {
  padding: 0;
  background: none;
  border: none;
  color: var(--cpq-text-primary);
}

/* 表格:细边框 + 表头底色 */
.md-view :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.9em 0;
  font-size: 13.5px;
}
.md-view :deep(th),
.md-view :deep(td) {
  border: 1px solid var(--cpq-border-secondary);
  padding: 6px 10px;
  text-align: left;
}
.md-view :deep(th) {
  background: var(--cpq-bg-secondary);
  color: var(--cpq-text-primary);
  font-weight: 600;
}
.md-view :deep(tr:nth-child(2n) td) {
  background: var(--cpq-bg-tertiary);
}
.md-view :deep(hr) {
  border: none;
  border-top: 1px solid var(--cpq-border-secondary);
  margin: 1.2em 0;
}
</style>
