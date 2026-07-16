<template>
  <div class="bom-table-container glass">
    <!-- L6 配置单 -->
    <div class="bom-section">
      <div class="bom-section-header">
        <span class="bom-section-title">L6 配置单</span>
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
          <tr v-for="row in l6Rows" :key="row.catalogue" class="bom-row">
            <td class="cell-catalogue">{{ row.catalogue }}</td>
            <td class="cell-desc">{{ row.description || '[空]' }}</td>
            <td class="cell-qty">{{ row.qty || '[空]' }}</td>
            <td class="cell-cost">{{ row.cost ? `¥${formatNumber(row.cost)}` : '[空]' }}</td>
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

// L6 Catalogue 固定骨架（11行）
const L6_CATALOGUES = [
  'Front backplane',
  'IO1',
  'IO2',
  'IO3',
  'IO4',
  'Heatsink',
  'FAN',
  'Power Supply',
  'Power cord',
  'Rail kit',
  'Cable'
]

// KP Catalogue 固定骨架（6行）
const KP_CATALOGUES = [
  'CPU',
  'Memory',
  'Raid card',
  'HDD/SSD',
  'NIC',
  'GPU'
]

// L6 BOM 行数据（响应式）
const l6Rows = computed(() => {
  const cfg = props.cfg
  const items = cfg.items || []
  const bomConfig = cfg.l6_bom_config || {}
  
  return L6_CATALOGUES.map(catalogue => {
    // 优先从 cfg.items 中查找（上传模式）
    const item = items.find((i: any) => {
      const partName = (i.part_name || '').toLowerCase()
      const cat = catalogue.toLowerCase()
      return partName.includes(cat) || cat.includes(partName)
    })
    
    if (item) {
      return {
        catalogue,
        description: item.spec || item.part_name,
        qty: item.qty,
        cost: item.base_price || item.final_price
      }
    }
    
    // 自选模式：从 l6_bom_config 中查找
    let description = ''
    let qty: number | null = null
    let cost: number | null = null
    
    // 根据 catalogue 映射到 bomConfig 的字段
    if (catalogue === 'Front backplane' && bomConfig.base_config) {
      description = bomConfig.base_config.name || bomConfig.base_config.model || ''
      qty = 1
      cost = bomConfig.base_config.price || null
    } else if (['IO1', 'IO2', 'IO3', 'IO4'].includes(catalogue) && bomConfig.front_panel_parts) {
      const idx = ['IO1', 'IO2', 'IO3', 'IO4'].indexOf(catalogue)
      const part = bomConfig.front_panel_parts[idx]
      if (part) {
        description = part.name || part.model || ''
        qty = part.qty || 1
        cost = part.price || null
      }
    } else if (catalogue === 'Heatsink' && bomConfig.rear_panel_parts) {
      const heatsink = bomConfig.rear_panel_parts.find((p: any) => p.type === 'heatsink')
      if (heatsink) {
        description = heatsink.name || heatsink.model || ''
        qty = heatsink.qty || 1
        cost = heatsink.price || null
      }
    } else if (catalogue === 'FAN' && bomConfig.rear_panel_parts) {
      const fan = bomConfig.rear_panel_parts.find((p: any) => p.type === 'fan')
      if (fan) {
        description = fan.name || fan.model || ''
        qty = fan.qty || 1
        cost = fan.price || null
      }
    } else if (catalogue === 'Power Supply' && bomConfig.psu_parts) {
      const psu = bomConfig.psu_parts[0]
      if (psu) {
        description = psu.name || psu.model || ''
        qty = psu.qty || 1
        cost = psu.price || null
      }
    } else if (['Power cord', 'Rail kit', 'Cable'].includes(catalogue) && bomConfig.psu_parts) {
      const type = catalogue.toLowerCase().replace(' ', '_')
      const part = bomConfig.psu_parts.find((p: any) => p.type === type)
      if (part) {
        description = part.name || part.model || ''
        qty = part.qty || 1
        cost = part.price || null
      }
    }
    
    return { catalogue, description, qty, cost }
  })
})

// KP BOM 行数据（响应式，动态显示实际配置的部件）
const kpRows = computed(() => {
  const cfg = props.cfg
  const items = cfg.items || []
  
  // 直接从 cfg.items 中获取所有 Key Parts 类别的项
  const kpItems = items.filter((i: any) => i.category === 'Key Parts')
  
  return kpItems.map((item: any, idx: number) => ({
    // 使用 part_name 作为 catalogue，支持同名多行（如两个 HDD/SSD）
    catalogue: item.part_name || 'Unknown',
    description: item.spec || '',
    qty: item.qty,
    cost: item.base_price || item.final_price,
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
