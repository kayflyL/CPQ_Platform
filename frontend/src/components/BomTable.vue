<template>
  <div class="bom-table-container glass">
    <div v-if="isExcel" class="excel-ref-badge">📋 Excel 参考（不随选配变动）</div>
    <!-- L6 配置单 -->
    <div class="bom-section">
      <div class="bom-section-header">
        <span class="bom-section-title">L6 配置单</span>
        <span class="bom-section-sub" v-if="l6TemplateName">{{ l6TemplateName }}</span>
      </div>
      <table class="bom-table no-cost">
        <thead>
          <tr>
            <th class="col-catalogue">Catalogue</th>
            <th class="col-desc">Description</th>
            <th class="col-qty">Qty</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in l6Rows" :key="'l6-' + row._idx" class="bom-row">
            <td class="cell-catalogue">{{ row.catalogue }}</td>
            <td class="cell-desc">{{ row.description || '[空]' }}</td>
            <td class="cell-qty">{{ row.qty === '' || row.qty == null ? '[空]' : row.qty }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- KP 配置单 -->
    <div class="bom-section">
      <div class="bom-section-header">
        <span class="bom-section-title">KP 配置单</span>
      </div>
      <table class="bom-table">
        <thead>
          <tr>
            <th class="col-catalogue">Catalogue</th>
            <th class="col-desc">Description</th>
            <th class="col-qty">Qty</th>
            <th class="col-cost">Cost</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in kpRows" :key="'kp-' + row._idx" class="bom-row">
            <td class="cell-catalogue">{{ row.catalogue }}</td>
            <td class="cell-desc">{{ row.description || '[空]' }}</td>
            <td class="cell-qty">{{ row.qty || '[空]' }}</td>
            <td class="cell-cost">{{ row.cost ? `¥${formatNumber(row.cost)}` : '[空]' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/store/settings'

const props = defineProps<{
  cfg: any
}>()

const settingsStore = useSettingsStore()

const formatNumber = (num: number) => {
  return settingsStore.formatNumber(num)
}

// L6 配置单：优先按机型族模板（bom_template.rows + bom_context）渲染摘要（catalogue/desc/qty，无价）；
// 无模板时回落 cfg.items 的 L6 行（legacy/未选基准配置）。
// Excel 报价单:左栏渲染加载时固化的快照,不随中栏选配变动;新建报价单跟随实时变动。
const isExcel = computed(() => props.cfg.bom_source === 'excel')
const l6HasTemplate = computed(() => {
  const tpl = props.cfg.bom_template
  return !!(tpl && tpl.rows && tpl.rows.length)
})
const l6TemplateName = computed(() => props.cfg.bom_template?.name || '')

const l6Rows = computed(() => {
  const cfg = props.cfg
  // Excel 报价单:渲染加载时固化的快照(不随中栏选配变动)
  if (isExcel.value) {
    return (cfg.bom_excel_rows || [])
      .filter((i: any) => i.category === 'L6' || i.category === '整机')
      .map((item: any, idx: number) => ({
        catalogue: item.part_name || '',
        description: item.spec || '',
        qty: item.qty,
        _idx: idx,
      }))
  }
  const tpl = cfg.bom_template
  const ctx = cfg.bom_context || {}
  if (l6HasTemplate.value) {
    return tpl.rows.map((r: any, idx: number) => {
      const key = r.slot || r.type
      const v = ctx[key] || { desc: '', qty: '' }
      return { catalogue: r.label, description: v.desc || '', qty: v.qty, _idx: idx }
    })
  }
  // 回落：cfg.items 的 L6 行
  const items = cfg.items || []
  return items
    .filter((i: any) => i.category === 'L6' || i.category === '整机')
    .map((item: any, idx: number) => ({
      catalogue: item.part_name || '',
      description: item.spec || '',
      qty: item.qty,
      _idx: idx,
    }))
})

// KP BOM 行数据（响应式，动态显示实际配置的部件）
// cost 显示「原始单价」base_price：Excel 上传用 excel 原值；新建跟随中栏 KP 卡片填写的原始单价实时变动
const kpRows = computed(() => {
  const cfg = props.cfg
  // Excel 报价单:渲染快照(不随中栏变动);否则实时读 cfg.items
  const items = isExcel.value ? (cfg.bom_excel_rows || []) : (cfg.items || [])

  // 直接从 cfg.items 中获取所有 Key Parts 类别的项
  const kpItems = items.filter((i: any) => i.category === 'Key Parts')

  return kpItems.map((item: any, idx: number) => ({
    // 使用 part_name 作为 catalogue，支持同名多行（如两个 HDD/SSD）
    catalogue: item.part_name || 'Unknown',
    description: item.spec || '',
    qty: item.qty,
    cost: Number(item.base_price) || 0,
    _idx: idx // 用于 v-for key 去重
  }))
})
</script>

<style scoped>
.bom-table-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow-y: auto;
}

.excel-ref-badge {
  margin: 0 12px 8px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--cpq-accent-primary, #00f5d4);
  background: rgba(0, 245, 212, 0.08);
  border: 1px solid rgba(0, 245, 212, 0.2);
  border-radius: 6px;
}
.bom-section {
  background: transparent;
  border: none;
  border-radius: 0;
  overflow: hidden;
}

.bom-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.04);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.bom-section-icon {
  font-size: 12px;
}

.bom-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.bom-section-sub {
  margin-left: auto;
  font-size: 10px;
  font-weight: 500;
  color: var(--cpq-accent-primary);
  background: rgba(0, 245, 212, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.bom-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.bom-table thead {
  background: rgba(255, 255, 255, 0.06);
  position: sticky;
  top: 0;
  z-index: 1;
}

.bom-table th {
  padding: 6px 10px;
  text-align: left;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.bom-table td {
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  color: var(--cpq-text-primary);
  line-height: 1.3;
}

.bom-row:last-child td {
  border-bottom: none;
}

.bom-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.col-catalogue {
  width: 28%;
  font-weight: 500;
}

.col-desc {
  width: 37%;
}

.col-qty {
  width: 12%;
  text-align: center;
}

.col-cost {
  width: 23%;
  text-align: right;
}

/* L6 表无 Cost 列：3 列重新分配占满 */
.bom-table.no-cost .col-catalogue {
  width: 30%;
}

.bom-table.no-cost .col-desc {
  width: 58%;
}

.cell-catalogue {
  font-weight: 500;
  color: var(--cpq-text-primary);
  word-break: break-word;
}

.cell-desc {
  color: var(--cpq-text-secondary);
  word-break: break-word;
}

.cell-qty {
  text-align: center;
  color: var(--cpq-text-muted);
}

.cell-cost {
  text-align: right;
  color: var(--cpq-accent-primary);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 空值样式 */
.cell-desc:empty::before,
.cell-qty:empty::before,
.cell-cost:empty::before {
  content: '[空]';
  color: var(--cpq-text-disabled);
  font-style: italic;
}
</style>
