<script setup lang="ts">
/** 配置明细通用组件（成本表查看器同构语言）：配置 tab + 摘要条 + 分组行级表 + 合计条。
 * 数据由调用方归一化（summary/行单元格/合计的取值串已格式化好），本组件只管形态与样式。
 * 使用方：报价单详情弹窗（快照：成本/售价/利润率）、成本引用「查看明细」（成本表：单价/小计/备注）。 */
import { ref, watch } from 'vue'

const props = defineProps<{
  configs: {
    key: string
    tab: string
    summary: { label: string; value: string; wide?: boolean }[]
    note?: string
    metricHeaders: [string, string, string]
    rows: {
      group: string
      groupSpan?: number
      catalogue: string
      description: string
      qty: string
      cells: [string, string, string]
    }[]
    totals: { label: string; value: string; accent?: boolean }[]
  }[]
}>()

const activeKey = ref('')
watch(
  () => props.configs,
  (v) => {
    if (!v.some((c) => c.key === activeKey.value)) activeKey.value = v[0]?.key || ''
  },
  { immediate: true },
)
</script>

<template>
  <a-tabs v-if="configs.length" v-model:activeKey="activeKey" size="small" class="gcd-tabs">
    <a-tab-pane v-for="cfg in configs" :key="cfg.key" :tab="cfg.tab">
      <div class="gcd-summary glass">
        <div v-for="s in cfg.summary" :key="s.label" class="gcd-qh" :class="{ 'gcd-qh-wide': s.wide }">
          <small>{{ s.label }}</small>
          <b :title="s.value">{{ s.value || '—' }}</b>
        </div>
      </div>
      <p v-if="cfg.note" class="gcd-note">{{ cfg.note }}</p>

      <div class="gcd-scroll">
        <table class="gcd-table">
        <thead>
          <tr>
            <th class="gcd-col-group">分组</th>
            <th>品类 / 部件</th>
            <th>配置描述</th>
            <th>数量</th>
            <th v-for="h in cfg.metricHeaders" :key="h">{{ h }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in cfg.rows" :key="`${cfg.key}-${i}`">
            <td v-if="row.groupSpan" :rowspan="row.groupSpan" class="gcd-group" :class="row.group === 'KP' ? 'gcd-group-kp' : ''">{{ row.group }}</td>
            <td>{{ row.catalogue }}</td>
            <td class="gcd-desc" :title="row.description">{{ row.description || '—' }}</td>
            <td class="gcd-num">{{ row.qty }}</td>
            <td v-for="(cell, ci) in row.cells" :key="ci" class="gcd-num">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
      </div>

      <div class="gcd-total glass">
        <span v-for="t in cfg.totals" :key="t.label">
          {{ t.label }} <b :class="{ 'gcd-accent': t.accent }">{{ t.value }}</b>
        </span>
      </div>
    </a-tab-pane>
  </a-tabs>
</template>

<style scoped>
.glass {
  background: var(--cpq-glass-bg, rgba(255,255,255,0.6));
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.5));
  border-radius: var(--cpq-radius-md);
  box-shadow: 0 1px 3px var(--cpq-shadow-color, rgba(0,0,0,0.06));
}

/* 配置摘要条：字段由调用方给（配置名/机型型号/描述/数量…），wide 项吃掉剩余宽度 */
.gcd-summary { display: flex; gap: 18px; padding: 12px 14px; margin-bottom: 4px; align-items: flex-start; }
.gcd-qh { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.gcd-qh-wide { flex: 1 1 auto; }
.gcd-qh small { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.gcd-qh b { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }
.gcd-note { font-size: 11.5px; color: var(--cpq-text-muted); line-height: 1.5; margin: 4px 0 10px; }

/* 分组行级表：分组列 rowspan，数字右对齐等宽 */
.gcd-table { width: 100%; border-collapse: collapse; font-size: var(--cpq-font-size-sm); margin-bottom: 10px; }
.gcd-table th {
  text-align: left; font-weight: 600; color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
  padding: 7px 9px; border: 1px solid var(--cpq-glass-border); white-space: nowrap;
}
.gcd-table td { padding: 7px 9px; border: 1px solid var(--cpq-glass-border); color: var(--cpq-text-secondary); vertical-align: top; }
.gcd-desc { color: var(--cpq-text-primary); }
.gcd-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.gcd-col-group { width: 56px; }
.gcd-group { font-weight: 600; color: var(--cpq-accent-primary); background: var(--cpq-overlay-w4); }
.gcd-group-kp { color: #7c3aed; }

/* 合计条 */
.gcd-total {
  display: flex; align-items: baseline; justify-content: flex-end; gap: 18px; flex-wrap: wrap;
  padding: 9px 14px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted);
}
.gcd-total b { color: var(--cpq-text-primary); font-variant-numeric: tabular-nums; margin-left: 4px; }
.gcd-accent { color: var(--cpq-accent-primary) !important; }

/* 手机端：表格窄屏横向滑动（明细网格手机口径），摘要条可换行 */
@media (max-width: 768px) {
  .gcd-summary { flex-wrap: wrap; gap: 10px 16px; }
  .gcd-scroll { overflow-x: auto; }
  .gcd-table { min-width: 620px; }
}
</style>
