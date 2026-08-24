<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import type { PortalSheetConfig, PortalSheetRow } from '@/api/portal'
import { catalogApi, baseConfigApi, kpPartsApi, type KpPart, type ServerModel } from '@/api/serverConfig'
import { bomCaseApi, type BomKpLine } from '@/api/bomCases'

const props = defineProps<{
  configs: PortalSheetConfig[]
  stage: 'boming' | 'costing'
  saving?: boolean
  structureLocked?: boolean
  showToolbar?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: { configs: PortalSheetConfig[]; submit?: boolean }): void
}>()

const configs = ref<PortalSheetConfig[]>([])
const activeKey = ref<string>('')
const kpCategories = ref<{ id: number; name: string }[]>([])
const kpCatalog = ref<Record<string, KpPart[]>>({})
const kpCatalogLoading = ref(false)
let kpCatalogLoaded = false
const serverModels = ref<ServerModel[]>([])
const serverModelsLoading = ref(false)
const fillingConfig = ref('')

const rowKeys = new WeakMap<object, string>()
let rowKeySeq = 1
function rowKeyFor(row: PortalSheetRow) {
  let key = rowKeys.get(row)
  if (!key) {
    key = `row-${rowKeySeq++}`
    rowKeys.set(row, key)
  }
  return key
}

const DEFAULT_KP_CATEGORIES = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']

const canEditBom = computed(() => props.stage === 'boming' && !props.readonly)
const canEditStructure = computed(() => props.stage === 'boming' && !props.structureLocked && !props.readonly)
const kpCategoryOptions = computed(() => kpCategories.value.map((c) => ({ value: c.name, label: c.name })))
const kpAllParts = computed(() => kpCategories.value.flatMap((c) => kpCatalog.value[c.name] || []))
const serverModelOptions = computed(() =>
  serverModels.value.map((model) => ({
    value: model.name,
    label: `${model.name}${model.base_config?.form ? ` · ${model.base_config.form}` : ''}${model.use ? ` · ${model.use}` : ''}`,
  })),
)

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

async function loadKpCatalog() {
  if (kpCatalogLoaded) return
  kpCatalogLoading.value = true
  try {
    const cats = await kpPartsApi.categories()
    kpCategories.value = cats
    const results = await Promise.all(cats.map((c) => kpPartsApi.listByCategory(c.id)))
    const catalog: Record<string, KpPart[]> = {}
    cats.forEach((c, i) => { catalog[c.name] = results[i] || [] })
    kpCatalog.value = catalog
    kpCatalogLoaded = true
  } catch (error) {
    console.warn('加载配件库目录失败', error)
  } finally {
    kpCatalogLoading.value = false
  }
}

async function loadServerModels() {
  if (serverModels.value.length) return
  serverModelsLoading.value = true
  try {
    const res = await catalogApi.listModels()
    serverModels.value = res.models || []
  } catch (error) {
    console.warn('加载机型目录失败', error)
  } finally {
    serverModelsLoading.value = false
  }
}

function kpPartsFor(category?: string): KpPart[] {
  if (!category) return kpAllParts.value
  return kpCatalog.value[category] || []
}

function kpCatalogueOptions(category?: string) {
  return kpPartsFor(category).map((part) => ({
    label: category ? part.name : `${part.category} · ${part.name}`,
    value: part.name,
    part,
  }))
}

function kpCatalogueFilter(input: string, option: any) {
  const text = [option?.value, option?.part?.pn, option?.part?.category]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return text.includes((input || '').toLowerCase())
}

function kpLinesFromConfig(cfg: PortalSheetConfig): BomKpLine[] {
  return cfg.kp_rows
    .filter((row) => row.catalogue)
    .map((row) => ({
      part_id: null,
      category: row.part_category || '',
      name: row.catalogue || '',
      qty: Number(row.qty) || 1,
      hint: '',
    }))
}

function l6RowFromPreview(row: { catalogue: string; description: string; qty: number }): PortalSheetRow {
  return {
    category: 'L6',
    catalogue: row.catalogue || '',
    description: row.description || '',
    part_category: '',
    qty: Number(row.qty) || 0,
    base_price: 0,
    final_price: 0,
    profit_margin: 0,
    currency: 'RMB',
    note: '',
  }
}

async function onServerModelSelect(cfg: PortalSheetConfig, value: string | undefined) {
  const name = value || ''
  const model = serverModels.value.find((item) => item.name === name)
  if (!model) return
  if (!model.base_config_id) {
    message.warning('该机型未配置基准配置')
    return
  }

  fillingConfig.value = cfg.name
  try {
    const base = await baseConfigApi.get(model.base_config_id)
    const templateId = (base as any).bom_template_id
    if (!templateId) {
      message.warning('该机型未绑定 BOM 模板')
      return
    }
    const res = await bomCaseApi.l6Preview({
      base_config_id: model.base_config_id,
      bom_template_id: templateId,
      kp_lines: kpLinesFromConfig(cfg),
      chassis_signals: {},
    })
    cfg.l6_rows = (res.rows || []).map(l6RowFromPreview)
    message.success('已按机型 BOM 模板填充 L6')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '填充 L6 失败')
  } finally {
    fillingConfig.value = ''
  }
}

function kpPartByName(category: string | undefined, name: string) {
  return kpPartsFor(category).find((part) => part.name === name)
}

function onKpCatalogueChange(row: PortalSheetRow, value: string | undefined) {
  const name = value || ''
  row.catalogue = name
  if (!name) return
  const part = kpPartByName(row.part_category, name) || kpPartByName(undefined, name)
  if (!part) return
  row.part_category = part.category
  if (part.unit_price != null) row.base_price = part.unit_price
}

function onKpCategoryChange(row: PortalSheetRow, value: string | undefined) {
  row.part_category = value || ''
  const parts = kpPartsFor(row.part_category)
  if (row.catalogue && parts.length && !parts.some((part) => part.name === row.catalogue)) {
    row.catalogue = ''
    row.base_price = 0
  }
}

function blankL6Row(): PortalSheetRow {
  return {
    category: 'L6',
    catalogue: '',
    description: '',
    part_category: '',
    qty: 1,
    base_price: 0,
    final_price: 0,
    profit_margin: 0,
    currency: 'RMB',
    note: '',
  }
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

function addL6Row(cfg: PortalSheetConfig) {
  cfg.l6_rows.push(blankL6Row())
}

function removeL6Row(cfg: PortalSheetConfig, idx: number) {
  cfg.l6_rows.splice(idx, 1)
}

function addKpRow(cfg: PortalSheetConfig) {
  cfg.kp_rows.push(blankKpRow())
}

function removeKpRow(cfg: PortalSheetConfig, idx: number) {
  cfg.kp_rows.splice(idx, 1)
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

onMounted(() => {
  loadKpCatalog()
  loadServerModels()
})

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
              <a-input v-if="canEditStructure" v-model:value="cfg.name" />
              <strong v-else>{{ cfg.name }}</strong>
            </label>
            <label class="fs-grid-cell fs-grid-model">
              <span>机型型号</span>
              <a-auto-complete
                v-if="canEditStructure"
                v-model:value="cfg.server_model"
                :options="serverModelOptions"
                :disabled="serverModelsLoading"
                :default-active-first-option="false"
                placeholder="选择或输入机型"
                style="width: 100%"
                @select="(value: string) => onServerModelSelect(cfg, value)"
              />
              <strong v-else>{{ cfg.server_model || '未填写机型型号' }}</strong>
            </label>
            <label class="fs-grid-cell fs-grid-desc">
              <span>描述</span>
              <a-textarea v-if="canEditStructure" v-model:value="cfg.description" :auto-size="{ minRows: 1, maxRows: 2 }" placeholder="配置说明/需求摘要" />
              <span v-else class="fs-desc-text">{{ cfg.description || '—' }}</span>
            </label>
            <label class="fs-grid-cell fs-grid-qty">
              <span>数量</span>
              <a-input-number :controls="false" v-if="canEditStructure" v-model:value="cfg.qty" :min="1" :precision="0" :style="{ width: '100%' }" />
              <strong v-else>{{ cfg.qty }} 台</strong>
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
              </tr>
            </thead>
            <draggable
              v-if="cfg.l6_rows.length"
              v-model="cfg.l6_rows"
              tag="tbody"
              :item-key="rowKeyFor"
              handle=".sheet-drag"
              :animation="180"
              :disabled="!canEditStructure"
              class="sheet-tbody"
            >
              <template #item="{ element: row, index: idx }">
                <tr class="sheet-row" :class="{ 'sheet-group-start-row': idx === 0 }">
                  <td class="sheet-group">{{ idx === 0 ? 'L6' : '' }}</td>
                  <td class="sheet-cell">
                    <div class="sheet-cell-inline">
                      <span v-if="canEditStructure" class="sheet-drag" title="拖拽排序">⠿</span>
                      <div class="sheet-cell-main">
                        <a-input v-if="canEditStructure" v-model:value="row.catalogue" class="sheet-input" placeholder="输入类别" />
                        <span v-else class="sheet-plain">{{ row.catalogue || '—' }}</span>
                      </div>
                      <a-button v-if="canEditStructure" type="text" danger size="small" class="sheet-row-del" @click="removeL6Row(cfg, idx)">×</a-button>
                    </div>
                  </td>
                  <td class="sheet-cell">
                    <a-textarea v-if="canEditStructure" v-model:value="row.description" class="sheet-input sheet-textarea" :auto-size="{ minRows: 1, maxRows: 4 }" placeholder="配置说明" />
                    <span v-else class="sheet-plain sheet-wrap">{{ row.description || '—' }}</span>
                  </td>
                  <td class="sheet-cell sheet-qty">
                    <a-input-number :controls="false" v-if="canEditStructure" v-model:value="row.qty" :min="0" :precision="0" class="sheet-input" />
                    <span v-else class="sheet-plain sheet-num">{{ row.qty || 0 }}</span>
                  </td>
                </tr>
              </template>
            </draggable>
            <draggable
              v-if="cfg.kp_rows.length"
              v-model="cfg.kp_rows"
              tag="tbody"
              :item-key="rowKeyFor"
              handle=".sheet-drag"
              :animation="180"
              :disabled="!canEditStructure"
              class="sheet-tbody"
            >
              <template #item="{ element: row, index: idx }">
                <tr class="sheet-row" :class="{ 'sheet-group-start-row': idx === 0 }">
                  <td class="sheet-group">{{ idx === 0 ? 'KP' : '' }}</td>
                  <td class="sheet-cell">
                    <div class="sheet-cell-inline">
                      <span v-if="canEditStructure" class="sheet-drag" title="拖拽排序">⠿</span>
                      <div class="sheet-cell-main">
                        <a-auto-complete
                          v-if="canEditStructure"
                          v-model:value="row.part_category"
                          :options="kpCategoryOptions"
                          :default-active-first-option="false"
                          :allow-clear="false"
                          placeholder="选择或输入类别"
                          style="width: 100%"
                          @select="(value: string) => onKpCategoryChange(row, value)"
                        />
                        <span v-else class="sheet-plain">{{ row.part_category || '—' }}</span>
                      </div>
                      <a-button v-if="canEditStructure" type="text" danger size="small" class="sheet-row-del" @click="removeKpRow(cfg, idx)">×</a-button>
                    </div>
                  </td>
                  <td class="sheet-cell">
                    <a-auto-complete
                      v-if="canEditStructure"
                      v-model:value="row.catalogue"
                      :options="kpCatalogueOptions(row.part_category)"
                      :filter-option="kpCatalogueFilter"
                      :default-active-first-option="false"
                      :allow-clear="false"
                      placeholder="选择或输入配件"
                      style="width: 100%"
                      @select="(value: string) => onKpCatalogueChange(row, value)"
                    />
                    <span v-else class="sheet-plain sheet-wrap">{{ row.catalogue || '—' }}</span>
                  </td>
                  <td class="sheet-cell sheet-qty">
                    <a-input-number :controls="false" v-if="canEditStructure" v-model:value="row.qty" :min="0" :precision="0" class="sheet-input" />
                    <span v-else class="sheet-plain sheet-num">{{ row.qty || 0 }}</span>
                  </td>
                </tr>
              </template>
            </draggable>
          </table>
        </div>

        <div class="sheet-actions">
          <a-button v-if="canEditStructure" size="small" type="link" @click="addL6Row(cfg)">+ 添加 L6 行</a-button>
          <a-button v-if="canEditStructure" size="small" type="link" @click="addKpRow(cfg)">+ 添加 KP 行</a-button>
        </div>

      </div>
      <div v-if="showToolbar !== false" class="fs-toolbar">
        <a-button v-if="canEditBom" :loading="saving" @click="saveDraft">保存方案配置</a-button>
        <a-button type="primary" :loading="saving" @click="submit">
          {{ canEditBom ? '提交方案配置' : '保存成本表' }}
        </a-button>
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
.sheet-actions {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
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
.sheet-qty {
  text-align: right;
}
.fs-toolbar {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
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
