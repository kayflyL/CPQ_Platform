<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PortalSheetConfig, PortalSheetRow } from '@/api/portal'
import type { KpPart } from '@/api/serverConfig'
import { calcUnitCost, formatPrice as money } from '@/utils/quoteCommon'
import { matchKpPart, suggestKpParts } from '@/utils/partNameMatch'

const props = defineProps<{
  configs: PortalSheetConfig[]
  saving?: boolean
  showToolbar?: boolean
  readonly?: boolean
  parts?: KpPart[]
  exchangeRate?: number
  taxRate?: number
}>()

const emit = defineEmits<{
  (e: 'save', payload: { configs: PortalSheetConfig[]; submit?: boolean }): void
}>()

const configs = ref<PortalSheetConfig[]>([])
const activeKey = ref<string>('')

const showCostColumns = computed(() => true)
const canEditCost = computed(() => !props.readonly)
const partsList = computed(() => props.parts || [])

function computeMatchInfo(row: PortalSheetRow) {
  if (!partsList.value.length) {
    return { kind: 'none' as const, part: undefined, candidates: [] as KpPart[], pending: true }
  }
  const match = matchKpPart(row, partsList.value)
  if (match.part) return { ...match, candidates: [] as KpPart[], pending: false }
  return { ...match, candidates: suggestKpParts(row, partsList.value, 3), pending: false }
}

let matchCache: WeakMap<object, ReturnType<typeof computeMatchInfo>> = new WeakMap()

function matchInfo(row: PortalSheetRow) {
  const cached = matchCache.get(row)
  if (cached) return cached
  const result = computeMatchInfo(row)
  matchCache.set(row, result)
  return result
}

watch(partsList, () => {
  matchCache = new WeakMap()
})

function adoptPart(row: PortalSheetRow, part: KpPart) {
  if (part.id != null) row.item_id = part.id
  row.part_category = part.category
  row.catalogue = part.name
  const price = Number(part.unit_price)
  if (Number.isFinite(price) && price > 0) {
    row.base_price = Math.round(calcUnitCost(price, part.unit_currency || row.currency || 'RMB', props.exchangeRate ?? 7, props.taxRate ?? 0.13) * 100) / 100
    row.currency = 'RMB'
  }
  matchCache.delete(row)
}

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
        </button>
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
                <th class="sheet-col-match"></th>
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
                <td class="sheet-cell sheet-match">
                  <span class="sheet-plain sheet-match-blank">—</span>
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
                <td class="sheet-cell sheet-match">
                  <template v-if="matchInfo(row).part">
                    <a-tooltip placement="topLeft">
                      <template #title>
                        <div class="match-tip">用户输入：{{ row.catalogue || row.description || '—' }}</div>
                        <div class="match-tip">匹配库件：{{ matchInfo(row).part?.name }}</div>
                        <div class="match-tip">最新价格：{{ matchInfo(row).part?.latest_price_date || '无' }}</div>
                      </template>
                      <div class="match-pill">
                        <a-tag :color="matchInfo(row).kind === 'fuzzy' ? 'blue' : 'green'" class="match-tag">
                          {{ matchInfo(row).kind === 'fuzzy' ? '模糊' : (matchInfo(row).kind === 'item_id' ? '料号' : '名称') }}
                        </a-tag>
                      </div>
                    </a-tooltip>
                  </template>
                  <template v-else>
                    <div v-if="matchInfo(row).pending" class="match-pill">
                      <span class="match-hint">未取价</span>
                    </div>
                    <a-popover v-else trigger="click" placement="bottomLeft">
                      <template #content>
                        <div class="match-candidates">
                          <div class="match-candidates-title">未匹配，可点击候选采用</div>
                          <div v-if="matchInfo(row).candidates.length" class="match-candidate-list">
                            <button
                              v-for="candidate in matchInfo(row).candidates"
                              :key="`${candidate.id || candidate.pn}-${candidate.name}`"
                              type="button"
                              class="match-candidate"
                              @click="adoptPart(row, candidate)"
                            >
                              <span class="match-candidate-name">{{ candidate.name }}</span>
                              <span class="match-candidate-meta">{{ candidate.category }}{{ candidate.brand ? ' · ' + candidate.brand : '' }}</span>
                              <span class="match-candidate-date">{{ candidate.latest_price_date || '无日期' }}</span>
                            </button>
                          </div>
                          <div v-else class="match-candidates-empty">配件库无可用候选</div>
                        </div>
                      </template>
                      <div class="match-pill match-miss">
                        <a-tag color="orange" class="match-tag">未匹配</a-tag>
                      </div>
                    </a-popover>
                  </template>
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
  min-width: 900px;
  border-collapse: collapse;
  table-layout: auto;
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
  width: 60px;
  text-align: center;
}
.sheet-col-cat {
  width: auto;
  min-width: 140px;
  max-width: 200px;
}
.sheet-col-match {
  width: auto;
  min-width: 72px;
}
.sheet-col-desc {
  width: auto;
  min-width: 220px;
}
.sheet-col-qty {
  width: 64px;
  text-align: right;
}
.sheet-col-cost {
  width: 110px;
  text-align: right;
}
.sheet-col-note {
  width: auto;
  min-width: 120px;
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
.sheet-match {
  padding: 0 6px;
}
.sheet-match-blank {
  text-align: center;
  color: var(--cpq-text-muted);
}
.match-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.match-tag {
  flex-shrink: 0;
  margin: 0;
  font-size: 11px;
}
.match-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.match-date {
  flex-shrink: 0;
  color: var(--cpq-text-muted);
  font-size: 11px;
}
.match-hint {
  color: var(--cpq-accent-warning, #d46b08);
  font-size: 12px;
  white-space: nowrap;
}
.match-miss {
  cursor: pointer;
}
.match-tip {
  line-height: 1.5;
  white-space: nowrap;
}
.match-candidates {
  width: 320px;
  max-width: 80vw;
}
.match-candidates-title {
  margin-bottom: 8px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}
.match-candidate-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.match-candidate {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  width: 100%;
  padding: 7px 8px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 8px;
  background: var(--cpq-bg-secondary);
  text-align: left;
  cursor: pointer;
}
.match-candidate:hover {
  border-color: var(--cpq-accent-primary);
}
.match-candidate-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.match-candidate-meta {
  color: var(--cpq-text-secondary);
  font-size: 11px;
}
.match-candidate-date {
  grid-column: 1 / -1;
  color: var(--cpq-text-muted);
  font-size: 11px;
}
.match-candidates-empty {
  color: var(--cpq-text-muted);
  font-size: 12px;
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
