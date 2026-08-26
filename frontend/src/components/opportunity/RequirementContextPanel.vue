<script setup lang="ts">
import { computed } from 'vue'
import type { RequirementVersion } from '@/api/portal'

const props = defineProps<{
  requirement: RequirementVersion | null
}>()

const meta = computed(() => {
  const r = props.requirement
  return [
    ['版本', r ? `需求单 v${r.version}` : '—'],
    ['提交人', r?.created_by || '—'],
    ['提交时间', r?.created_at && r.created_at.length >= 16 ? r.created_at.slice(5, 16) : '—'],
    ['状态', r ? (r.status === 'draft' ? '草稿' : r.status === 'archived' ? '历史版本' : '已发起') : '—'],
  ]
})

const basicRows = computed(() => {
  const s = props.requirement?.slots || {}
  const rows: [string, string][] = [
    ['服务器型号', s.server_model || '—'],
    ['平台类型', s.platform_type || '—'],
    ['机箱形态', s.chassis_form || '—'],
    ['服务器类型', s.server_type || '—'],
    ['数量', s.purchase_qty != null ? `${s.purchase_qty} 台` : '—'],
    ['维保年限', s.warranty_years || '—'],
  ]
  return rows
})

const partRows = computed(() => {
  const s = props.requirement?.slots || {}
  const rows: Array<{ category: string; spec: string; qty: string | number; brand: string }> = []

  if (s.cpu?.model || s.cpu?.brand || s.cpu?.qty) {
    rows.push({
      category: 'CPU',
      spec: [s.cpu.model, s.cpu.cores ? `${s.cpu.cores}核` : '', s.cpu.tdp_w ? `${s.cpu.tdp_w}W` : ''].filter(Boolean).join(' / '),
      qty: s.cpu.qty ?? '',
      brand: s.cpu.brand || '',
    })
  }
  if (s.memory?.per_stick_gb || s.memory?.type || s.memory?.qty) {
    rows.push({
      category: '内存',
      spec: [s.memory.per_stick_gb ? `${s.memory.per_stick_gb}GB` : '', s.memory.type, s.memory.speed_mt ? `${s.memory.speed_mt}MT/s` : ''].filter(Boolean).join(' / '),
      qty: s.memory.qty ?? '',
      brand: s.memory.brand || '',
    })
  }
  for (const r of s.storage || []) {
    rows.push({
      category: '硬盘',
      spec: [r.capacity, r.interface].filter(Boolean).join(' / '),
      qty: r.qty ?? '',
      brand: r.brand || '',
    })
  }
  for (const r of s.nic || []) {
    rows.push({
      category: '网卡',
      spec: [r.model, r.speed_g ? `${r.speed_g}G` : '', r.ports ? `${r.ports}口` : ''].filter(Boolean).join(' / '),
      qty: r.qty ?? '',
      brand: r.brand || '',
    })
  }
  for (const r of s.gpu || []) {
    rows.push({
      category: 'GPU',
      spec: r.model || '',
      qty: r.qty ?? '',
      brand: r.brand || '',
    })
  }
  return rows
})

const requirementText = computed(() => props.requirement?.requirement_text || '')
</script>

<template>
  <div class="context-panel">
    <div class="panel-head">
      <b>上游需求单</b>
      <span class="chip green">只读参考</span>
    </div>
    <div v-if="requirement" class="panel-body">
      <div class="snapshot">
        <div v-for="[k, v] in meta" :key="k" class="snap">
          <small>{{ k }}</small>
          <span>{{ v }}</span>
        </div>
      </div>

      <section class="ctx-sec">
        <h5>需求明细</h5>
        <div class="ctx-grid">
          <div v-for="[k, v] in basicRows" :key="k" class="ctx-item">
            <span>{{ k }}</span>
            <b>{{ v }}</b>
          </div>
        </div>
      </section>

      <section v-if="requirementText" class="ctx-sec">
        <h5>需求描述</h5>
        <p class="ctx-text">{{ requirementText }}</p>
      </section>

      <section v-if="partRows.length" class="ctx-sec">
        <h5>部件清单</h5>
        <table class="ctx-table">
          <thead>
            <tr><th>类别</th><th>规格</th><th>数量</th><th>品牌</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in partRows" :key="`${row.category}-${idx}`">
              <td>{{ row.category }}</td>
              <td>{{ row.spec || '—' }}</td>
              <td>{{ row.qty || '—' }}</td>
              <td>{{ row.brand || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
    <div v-else class="panel-empty">暂无需求单</div>
  </div>
</template>

<style scoped>
.context-panel {
  position: relative;
  align-self: start;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 230px);
  border: 1px solid var(--cpq-border-primary);
  border-radius: 14px;
  overflow: hidden;
  background: var(--cpq-bg-card);
  box-shadow: var(--cpq-shadow-md);
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-border-primary);
  background: var(--cpq-bg-secondary);
}
.panel-head b {
  font-size: 14px;
  color: var(--cpq-text-primary);
}
.chip {
  border-radius: 999px;
  padding: 5px 11px;
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
  font-size: 12px;
  font-weight: 600;
}
.chip.green {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}
.panel-body {
  padding: 12px 14px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.snapshot {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 0;
}
.snap {
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 10px;
  padding: 6px 8px;
  background: var(--cpq-bg-secondary);
  min-width: 0;
}
.snap small {
  display: block;
  color: var(--cpq-text-muted);
  font-size: 11px;
  margin-bottom: 4px;
}
.snap span {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.panel-empty {
  padding: 20px 14px;
  color: var(--cpq-text-muted);
  font-size: 13px;
  text-align: center;
}
.ctx-sec h5 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--cpq-text-secondary);
}
.ctx-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}
.ctx-item {
  min-width: 0;
  padding: 5px 8px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 9px;
  background: var(--cpq-bg-secondary);
}
.ctx-item span {
  display: block;
  color: var(--cpq-text-muted);
  font-size: 10px;
  margin-bottom: 2px;
}
.ctx-item b {
  display: block;
  color: var(--cpq-text-primary);
  font-size: 12px;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ctx-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.ctx-table th,
.ctx-table td {
  border: 1px solid var(--cpq-border-secondary);
  padding: 6px 7px;
  text-align: left;
}
.ctx-table th {
  background: var(--cpq-bg-tertiary);
  color: var(--cpq-text-muted);
  font-weight: 600;
}
.ctx-table td {
  color: var(--cpq-text-secondary);
}
.ctx-text {
  margin: 0;
  padding: 7px 10px;
  border: 1px dashed var(--cpq-border-primary);
  border-radius: 10px;
  background: var(--cpq-bg-secondary);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
}

@media (max-width: 640px) {
  .snapshot,
  .ctx-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
