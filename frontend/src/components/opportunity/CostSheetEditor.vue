<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import type { PortalSheetConfig, PortalSheetRow } from '@/api/portal'
import { formatPrice as money } from '@/utils/quoteCommon'

const props = defineProps<{
  configs: PortalSheetConfig[]
  saving?: boolean
  showToolbar?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: { configs: PortalSheetConfig[]; submit?: boolean }): void
}>()

const configs = ref<PortalSheetConfig[]>([])
const activeKey = ref<string>('')

const DEFAULT_KP_CATEGORIES = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']

const canEditStructure = computed(() => false)
const showCostColumns = computed(() => true)
const canEditCost = computed(() => !props.readonly)

watch(
  () => props.configs,
  (rows) => {
    configs.value = JSON.parse(JSON.stringify(rows || [])) as PortalSheetConfig[]
    if (configs.value.length && !configs.value.some((c) => c.name === activeKey.value)) {
      activeKey.value = configs.value[0].name
    }
  },
  { immediate: true, deep: true },
)

function kpCost(cfg: PortalSheetConfig) {
  return cfg.kp_rows.reduce(
    (sum, row) => sum + Number(row.base_price || 0) * Number(row.qty || 0),
    0,
  )
}

function configCost(cfg: PortalSheetConfig) {
  return Number(cfg.l6_cost || 0) + kpCost(cfg)
}

function rowCost(row: PortalSheetRow) {
  return Number(row.base_price || 0) * Number(row.qty || 0)
}

function blankKpRow(partCategory = ''): PortalSheetRow {
  return {
    category: 'Key Parts',
    part_category: partCategory,
    catalogue: '',
    description: '',
    qty: 1,
    base_price: 0,
    final_price: 0,
    profit_margin: 10,
    currency: 'RMB',
    note: '',
  }
}

function seedKpRows(): PortalSheetRow[] {
  return DEFAULT_KP_CATEGORIES.map((cat) => blankKpRow(cat))
}

function nextConfigName() {
  let max = 0
  for (const cfg of configs.value) {
    const match = /^CFG(\d+)$/.exec(cfg.name)
    if (match) max = Math.max(max, Number(match[1]))
  }
  return `CFG${max + 1}`
}

function blankConfig(name: string): PortalSheetConfig {
  return {
    name,
    server_model: '',
    description: '',
    qty: 1,
    l6_cost: 0,
    l6_margin: 0,
    l6_rows: [],
    kp_rows: seedKpRows(),
    totals: {},
  }
}

function addConfig() {
  const cfg = blankConfig(nextConfigName())
  configs.value.push(cfg)
  activeKey.value = cfg.name
}

function removeConfig(cfg: PortalSheetConfig) {
  if (configs.value.length <= 1) {
    message.warning('至少保留一个配置')
    return
  }
  Modal.confirm({
    title: `删除配置 ${cfg.name}？`,
    content: '该配置下的 L6 / KP 行会一并删除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk() {
      const idx = configs.value.findIndex((c) => c.name === cfg.name)
      configs.value = configs.value.filter((c) => c.name !== cfg.name)
      activeKey.value = (configs.value[Math.min(idx, configs.value.length - 1)] || configs.value[0])?.name || ''
    },
  })
}

function buildPayload() {
  return {
    configs: JSON.parse(JSON.stringify(configs.value)),
  }
}

function saveDraft() {
  emit('save', { ...buildPayload(), submit: false })
}

function submit() {
  emit('save', { ...buildPayload(), submit: true })
}

function getConfigs() {
  return JSON.parse(JSON.stringify(configs.value)) as PortalSheetConfig[]
}

defineExpose({ saveDraft, submit, getConfigs })
</script>

<template>
  <div class="flow-sheet">
    <a-empty v-if="!configs.length" description="暂无工作表数据" />

    <template v-else>
      <div class="fs-tabs">
        <button
          v-for="cfg in configs"
          :key="cfg.name"
          type="button"
          class="fs-tab"
          :class="{ active: cfg.name === activeKey }"
          @click="activeKey = cfg.name"
        >
          <span>{{ cfg.name }}</span>
          <a-button
            v-if="canEditStructure"
            type="text"
            size="small"
            class="fs-tab-close"
            @click.stop="removeConfig(cfg)"
          >
            ×
          </a-button>
        </button>
        <a-button v-if="canEditStructure" size="small" class="fs-add-config" @click="addConfig">
          + 配置
        </a-button>
      </div>

      <div v-for="cfg in configs" v-show="cfg.name === activeKey" :key="cfg.name" class="fs-config">
        <div class="fs-config-bar">
          <div class="fs-config-grid">
            <label class="fs-grid-cell fs-grid-name">
              <span>配置名</span>
              <strong>{{ cfg.name }}</strong>
            </label>
            <label class="fs-grid-cell fs-grid-model">
              <span>机型型号</span>
              <strong>{{ cfg.server_model || '未填写机型型号' }}</strong>
            </label>
            <label class="fs-grid-cell fs-grid-desc">
              <span>描述</span>
              <span class="fs-desc-text">{{ cfg.description || '—' }}</span>
            </label>
            <label class="fs-grid-cell fs-grid-qty">
              <span>数量</span>
              <strong>{{ cfg.qty }} 台</strong>
            </label>
          </div>
        </div>

        <div class="sheet-scroll">
          <table class="sheet-table unified-sheet">
            <thead>
              <tr>
                <th class="sheet-col-group">分组</th>
                <th class="sheet-col-cat">Catalogue</th>
                <th class="sheet-col-desc">Configuration Description</th>
                <th class="sheet-col-qty">Quantity</th>
                <th class="sheet-col-cost">Unit Cost</th>
                <th class="sheet-col-cost">Total Cost</th>
                <th class="sheet-col-note">Note</th>
              </tr>
            </thead>
            <tbody v-if="cfg.l6_rows.length">
              <tr v-for="(row, idx) in cfg.l6_rows" :key="`l6-${cfg.name}-${idx}`" class="sheet-row" :class="{ 'sheet-group-start-row': idx === 0 }">
                <td class="sheet-group">{{ idx === 0 ? 'L6' : '' }}</td>
                <td class="sheet-cell">
                  <span class="sheet-plain">{{ row.catalogue || '—' }}</span>
                </td>
                <td class="sheet-cell">
                  <span class="sheet-plain sheet-wrap">{{ row.description || '—' }}</span>
                </td>
                <td class="sheet-cell sheet-qty">
                  <span class="sheet-plain sheet-num">{{ row.qty || 0 }}</span>
                </td>
                <td class="sheet-cell sheet-cost sheet-blank">—</td>
                <td class="sheet-cell sheet-cost sheet-derived">—</td>
                <td class="sheet-cell">
                  <span class="sheet-plain sheet-wrap">{{ row.note || '—' }}</span>
                </td>
              </tr>
            </tbody>
            <tbody v-if="cfg.kp_rows.length">
              <tr v-for="(row, idx) in cfg.kp_rows" :key="`kp-${cfg.name}-${idx}`" class="sheet-row" :class="{ 'sheet-group-start-row': idx === 0 }">
                <td class="sheet-group">{{ idx === 0 ? 'KP' : '' }}</td>
                <td class="sheet-cell">
                  <span class="sheet-plain">{{ row.part_category || '—' }}</span>
                </td>
                <td class="sheet-cell">
                  <span class="sheet-plain sheet-wrap">{{ row.catalogue || '—' }}</span>
                </td>
                <td class="sheet-cell sheet-qty">
                  <span class="sheet-plain sheet-num">{{ row.qty || 0 }}</span>
                </td>
                <td class="sheet-cell sheet-cost">
                  <a-input-number :controls="false" v-if="canEditCost" v-model:value="row.base_price" :min="0" :precision="2" class="sheet-input" />
                  <span v-else class="sheet-plain sheet-num">{{ money(row.base_price) }}</span>
                </td>
                <td class="sheet-cell sheet-cost sheet-derived">¥{{ money(rowCost(row)) }}</td>
                <td class="sheet-cell">
                  <a-input v-if="canEditCost" v-model:value="row.note" class="sheet-input" placeholder="备注" />
                  <span v-else class="sheet-plain sheet-wrap">{{ row.note || '—' }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="showCostColumns" class="fs-cost-total">
          <div class="fs-cost-item">
            <span>L6成本合计</span>
            <a-input-number :controls="false" v-if="canEditCost" v-model:value="cfg.l6_cost" :min="0" :precision="2" class="fs-cost-input" />
            <strong v-else>¥{{ money(cfg.l6_cost) }}</strong>
          </div>
          <div class="fs-cost-item">
            <span>KP成本合计</span>
            <strong>¥{{ money(kpCost(cfg)) }}</strong>
          </div>
          <div class="fs-cost-item fs-cost-item-main">
            <span>整机成本合计</span>
            <strong>¥{{ money(configCost(cfg)) }}</strong>
          </div>
        </div>
      </div>
      <div v-if="showToolbar !== false" class="fs-toolbar">
        <a-button :loading="saving" @click="saveDraft">保存成本表</a-button>
        <a-button type="primary" :loading="saving" @click="submit">提交成本核算</a-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.flow-sheet {
  display: flex;
  flex-direction: column;
  gap: 14px;
  --sheet-panel: var(--cpq-bg-secondary);
  --sheet-surface: var(--cpq-bg-secondary);
  --sheet-head: var(--cpq-bg-tertiary);
  --sheet-line: var(--cpq-border-secondary);
  --sheet-line-strong: var(--cpq-border-primary);
  --sheet-hover: var(--cpq-overlay-w4);
  --sheet-focus: var(--cpq-overlay-a10);
  --sheet-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
}
:root[data-theme='light'] .flow-sheet {
  --sheet-panel: #ffffff;
  --sheet-surface: #ffffff;
  --sheet-head: #f5f8fd;
  --sheet-line: #e7eef7;
  --sheet-line-strong: #dce6f3;
  --sheet-hover: #f5f9ff;
  --sheet-focus: #eaf3ff;
  --sheet-shadow: 0 6px 18px rgba(22, 119, 255, 0.06);
}
.fs-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.fs-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 96px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--sheet-line-strong);
  background: var(--sheet-panel);
  color: var(--cpq-text-secondary);
  cursor: pointer;
  transition: border-color 0.16s ease, color 0.16s ease, background 0.16s ease;
}
.fs-tab:hover {
  border-color: var(--cpq-accent-primary-light);
  background: var(--sheet-hover);
}
.fs-tab.active {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--sheet-focus);
}
.fs-tab-close {
  color: var(--cpq-text-muted);
  padding: 0 2px;
}
.fs-add-config {
  flex-shrink: 0;
}
.fs-config {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fs-config-bar {
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--sheet-line-strong);
  border-radius: 12px;
  background: var(--sheet-panel);
  box-shadow: var(--sheet-shadow);
}
.fs-config-grid {
  display: grid;
  grid-template-columns: 110px 180px minmax(240px, 1fr) 82px;
  gap: 12px;
  align-items: start;
  justify-content: start;
}
.fs-grid-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.fs-desc-text {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.sheet-scroll {
  overflow-x: auto;
  width: 100%;
  border: 1px solid var(--sheet-line-strong);
  border-radius: 12px;
  background: var(--sheet-surface);
  box-shadow: var(--sheet-shadow);
}
.sheet-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 12px;
}
.sheet-table th,
.sheet-table td {
  border-right: 1px solid var(--sheet-line);
  border-bottom: 1px solid var(--sheet-line);
  text-align: left;
  vertical-align: middle;
}
.sheet-table th:last-child,
.sheet-table td:last-child {
  border-right: 0;
}
.sheet-table tbody tr:last-child td {
  border-bottom: 0;
}
.sheet-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 34px;
  padding: 6px 8px;
  color: var(--cpq-text-secondary);
  background: var(--sheet-head);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 1px solid var(--sheet-line-strong);
}
.sheet-col-group {
  width: 76px;
  text-align: center;
}
.sheet-col-cat {
  width: 150px;
}
.sheet-col-desc {
  width: auto;
}
.sheet-col-qty {
  width: 80px;
  text-align: right;
}
.sheet-col-cost {
  width: 120px;
  text-align: right;
}
.sheet-col-note {
  width: 150px;
}
.sheet-group {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--sheet-head);
  color: var(--cpq-accent-primary);
  text-align: center;
  font-size: 11px;
  font-weight: 650;
  vertical-align: middle;
  border-bottom: 0;
}
.sheet-row.sheet-group-start-row .sheet-group {
  box-shadow: inset 0 1px 0 var(--sheet-line-strong);
}
.sheet-blank {
  color: var(--cpq-text-muted);
  text-align: right;
}
.sheet-cell {
  height: 36px;
  padding: 0;
  transition: background 0.15s ease;
}
.sheet-row:hover td {
  background: var(--sheet-hover);
}
.sheet-cell:focus-within {
  background: var(--sheet-hover);
  box-shadow: inset 0 -1px 0 var(--cpq-accent-primary);
}
.sheet-drag {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  cursor: grab;
  color: var(--cpq-text-muted);
  font-size: 14px;
  user-select: none;
}
.sheet-drag:active {
  cursor: grabbing;
}
.sheet-cell-inline {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.sheet-cell-main {
  flex: 1;
  min-width: 0;
}
.sheet-row-del {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.sheet-row:hover .sheet-row-del,
.sheet-cell:focus-within .sheet-row-del {
  opacity: 1;
}
.sheet-input {
  width: 100%;
}
.sheet-table :deep(.ant-input),
.sheet-table :deep(.ant-input-number),
.sheet-table :deep(.ant-select-selector) {
  border: 0 !important;
  box-shadow: none !important;
  background: transparent;
}
.sheet-table :deep(input.ant-input) {
  height: 36px;
  padding: 0 8px;
  border-radius: 0;
}
.sheet-table :deep(textarea.ant-input) {
  min-height: 36px;
  height: auto;
  padding: 8px;
  line-height: 1.45;
  resize: none;
}
.sheet-table :deep(.ant-input-number) {
  width: 100%;
  height: 36px;
  border-radius: 0;
}
.sheet-table :deep(.ant-input-number-input) {
  height: 36px;
  padding: 0 10px;
  text-align: right;
}
.sheet-table :deep(.ant-select) {
  width: 100%;
  height: 36px;
}
.sheet-table :deep(.ant-select-selector) {
  height: 36px !important;
  padding: 0 8px !important;
  border-radius: 0;
}
.sheet-table :deep(.ant-select-selection-search-input) {
  height: 36px !important;
}
.sheet-plain {
  display: block;
  padding: 0 8px;
  line-height: 36px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sheet-wrap {
  padding: 8px;
  line-height: 1.45;
  white-space: normal;
}
.sheet-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.sheet-qty,
.sheet-cost {
  text-align: right;
}
.sheet-derived {
  padding: 0 8px;
  color: var(--cpq-accent-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}
.fs-toolbar {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
}
.fs-cost-total {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 22px;
  width: 100%;
  margin-top: 4px;
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--sheet-panel);
  border: 1px solid var(--sheet-line-strong);
  box-shadow: var(--sheet-shadow);
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.fs-cost-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fs-cost-item strong {
  color: var(--cpq-text-primary);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.fs-cost-item-main strong {
  color: var(--cpq-accent-primary);
}
.fs-cost-input {
  width: 140px;
}

@media (max-width: 900px) {
  .fs-config-grid {
    grid-template-columns: 1fr 1fr;
  }
  .fs-grid-desc {
    grid-column: 1 / -1;
  }
}
</style>
