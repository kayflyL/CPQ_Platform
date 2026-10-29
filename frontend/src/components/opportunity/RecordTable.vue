<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  emptyText?: string
  empty?: boolean
  columns?: Array<{ label: string; width?: string; align?: 'left' | 'center' | 'right' }>
}>(), {
  title: '',
  emptyText: '',
  empty: false,
  columns: () => [],
})
</script>

<template>
  <section class="record-table">
    <header v-if="title" class="rt-head">
      <span class="rt-title">{{ title }}</span>
      <slot name="head-actions" />
    </header>
    <div class="rt-scroll">
      <table class="rt-table">
        <colgroup v-if="columns.some((c) => c.width)">
          <col v-for="(c, i) in columns" :key="i" :style="{ width: c.width }" />
        </colgroup>
        <thead>
          <tr>
            <th
              v-for="(c, i) in columns"
              :key="i"
              :class="c.align ? `rt-align-${c.align}` : ''"
            >{{ c.label }}</th>
          </tr>
        </thead>
        <tbody>
          <slot />
        </tbody>
      </table>
      <div v-if="empty && emptyText" class="rt-empty">{{ emptyText }}</div>
    </div>
  </section>
</template>

<style scoped>
.record-table {
  overflow: hidden;
}
.rt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 13px 10px;
}
.rt-title {
  font-size: var(--cpq-font-size-base);
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.rt-scroll {
  overflow-x: auto;
  padding: 2px 13px 12px;
}
.rt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--cpq-font-size-sm);
}
.rt-table th,
.rt-table :deep(td) {
  border: 1px solid var(--cpq-glass-border);
  padding: 10px 12px;
  text-align: left;
  vertical-align: middle;
}
.rt-table th {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-muted);
  font-weight: 600;
  white-space: nowrap;
}
.rt-table :deep(tbody tr) {
  transition: background .18s ease;
}
.rt-table :deep(tbody tr:hover) {
  background: var(--cpq-overlay-w3);
}
.rt-align-center { text-align: center; }
.rt-align-right { text-align: right; }
.rt-empty {
  padding: 22px 14px;
  text-align: center;
  color: var(--cpq-text-muted);
  font-size: var(--cpq-font-size-sm);
}
/* 行内内容全部来自调用方插槽（带调用方 scope），必须走 :deep 才命中 */
:deep(.rt-badge) {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid;
  border-radius: var(--cpq-radius-full);
  padding: 2px 8px;
  font-size: var(--cpq-font-size-xs);
  font-weight: 700;
  white-space: nowrap;
}
:deep(.rt-badge)::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
:deep(.rt-badge.rt-badge-current) { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); }
:deep(.rt-badge.rt-badge-draft) { color: #b45309; border-color: #f59e0b; background: rgba(245,158,11,.10); }
:deep(.rt-badge.rt-badge-done),
:deep(.rt-badge.rt-badge-exported),
:deep(.rt-badge.rt-badge-released) { color: #166534; border-color: #22c55e; background: rgba(34,197,94,.10); }
:deep(.rt-badge.rt-badge-pending) { color: #7c3aed; border-color: #8b5cf6; background: rgba(139,92,246,.10); }
:deep(.rt-badge.rt-badge-approving) { color: #b91c1c; border-color: #ef4444; background: rgba(239,68,68,.10); }
:deep(.rt-actions) { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 6px; }
:deep(.rt-link) { color: var(--cpq-accent-primary); cursor: pointer; font-size: var(--cpq-font-size-sm); white-space: nowrap; }
:deep(.rt-link:hover) { opacity: .8; }
:deep(.rt-link.danger) { color: #ef4444; }
:deep(.rt-link.muted) { color: var(--cpq-text-muted); }
:deep(.rt-strong) { font-weight: 400; color: var(--cpq-text-primary); }
:deep(.rt-sub) { display: block; margin-top: 3px; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }
:deep(.rt-dim) { color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }

/* ── 手机端：表格 → 卡片列表。每行一张卡，td 靠 data-label 显示字段名 ── */
@media (max-width: 768px) {
  .rt-scroll {
    overflow-x: visible;
    padding: 2px 2px 12px;
  }
  .rt-table,
  .rt-table tbody {
    display: block;
    width: 100%;
  }
  .rt-table thead {
    display: none;
  }
  .rt-table :deep(tbody tr) {
    display: block;
    margin: 0 0 10px;
    padding: 2px 12px;
    border: 1px solid var(--cpq-glass-border);
    border-radius: var(--cpq-radius-md);
    background: var(--cpq-overlay-w2, transparent);
  }
  .rt-table :deep(tbody tr:last-child) {
    margin-bottom: 0;
  }
  .rt-table :deep(tbody td) {
    display: block;
    border: 0;
    border-bottom: 1px dashed var(--cpq-overlay-w8);
    padding: 8px 0;
  }
  .rt-table :deep(tbody td:last-child) {
    border-bottom: 0;
    padding-bottom: 10px;
  }
  .rt-table :deep(tbody td[data-label])::before {
    content: attr(data-label);
    display: block;
    margin-bottom: 3px;
    font-size: var(--cpq-font-size-xs);
    color: var(--cpq-text-muted);
  }
  .rt-table :deep(.rt-actions) {
    justify-content: flex-start;
  }
}
</style>
