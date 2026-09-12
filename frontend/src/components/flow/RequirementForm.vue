<script setup lang="ts">
/**
 * 线索登记需求单（共享组件）——需求原文 + 多配置 + 部件清单。
 *
 * 配置字段：机型型号 / 平台类型 / 服务器类型 / 机箱形态 / 数量 / 维保年限。
 * 机型从服务器库选中时，自动带出平台、服务器类型与机箱形态。
 * KP 部件清单保留：从配件库选择。
 */
import { ref, computed } from 'vue'
import { useSeriesStore } from '@/stores/series'
import axios from 'axios'
import { catalogApi, kpPartsApi, baseConfigApi, type ServerModel } from '@/api/serverConfig'
import type { RequirementSlots, PortalSheetRow } from '@/api/portal'
import KpPartsEditor from '@/components/opportunity/KpPartsEditor.vue'

const props = withDefaults(defineProps<{
  readonly?: boolean
}>(), { readonly: false })

const emit = defineEmits<{ change: [] }>()

const seriesStore = useSeriesStore()
seriesStore.ensureSeries()

const formOptions = ref<{ value: string; label: string }[]>([])

const defaultKpCategories = ref<string[]>([])
const seriesOptions = computed(() => seriesStore.items.map((s) => ({ value: s.value, label: s.label })))
const modelOptions = ref<{ value: string; label: string }[]>([])
const serverTypeOptions = ref<{ value: string; label: string }[]>([])
const modelRecords = ref<ServerModel[]>([])
const serverTypeMap: Record<string, string> = {}

interface RequirementConfig {
  name: string
  server_model: string
  platform_type: string
  server_type: string
  chassis_form: string
  qty: number
  warranty_years: number
  kp_rows: PortalSheetRow[]
  /** 表单定义驱动的动态字段绑定（schema 渲染按 key 写入） */
  [field: string]: any
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

function blankConfig(name: string): RequirementConfig {
  return {
    name,
    server_model: '',
    platform_type: '',
    server_type: '',
    chassis_form: '',
    qty: 1,
    warranty_years: 1,
    kp_rows: defaultKpCategories.value.map((cat) => blankKpRow(cat)),
  }
}

const configs = ref<RequirementConfig[]>([])
const activeKey = ref('')
const reqText = defineModel<string>('reqText', { default: '' })

// 配置关系：compose=组合拆分（默认，多配置数量求和）/ alternative=方案备选对比（不求和，同一需求多方案）
const configRelation = ref<'compose' | 'alternative'>('compose')
const primaryConfig = ref<string>('')

function onConfigRelationChange(mode: 'compose' | 'alternative') {
  configRelation.value = mode
  if (mode === 'alternative') {
    const first = activeConfig.value?.name || configs.value[0]?.name || ''
    if (first && !primaryConfig.value) primaryConfig.value = first
    // 方案备选：每个方案台数默认为需求台数（取第一个配置），同一批需求多方案
    const demand = Number(configs.value[0]?.qty) || 1
    for (const cfg of configs.value) {
      if (!cfg.qty || cfg.qty <= 0) cfg.qty = demand
    }
  }
  emit('change')
}

function markPrimary(name: string) {
  primaryConfig.value = name
  emit('change')
}

async function loadModelOptions() {
  try {
    const res = await catalogApi.listModels()
    modelRecords.value = res.models || []
    modelOptions.value = modelRecords.value
      .filter((m) => m && m.name)
      .map((m) => ({ value: m.name, label: m.name }))
  } catch {
    modelOptions.value = []
  }
}

async function loadServerTypes() {
  try {
    const res = await catalogApi.listTypes()
    const types = res.types || []
    serverTypeOptions.value = types
      .filter((t) => t && t.name)
      .map((t) => ({ value: t.name, label: t.name }))
    for (const type of types) {
      if (type?.id != null && type.name) serverTypeMap[String(type.id)] = type.name
    }
  } catch {
    serverTypeOptions.value = []
  }
}

async function loadFormOptions() {
  try {
    const res = await baseConfigApi.listForms()
    formOptions.value = (res.forms || []).map((f) => ({ value: f, label: f }))
  } catch {
    formOptions.value = []
  }
}

async function loadDefaultKpCategories() {
  try {
    const cats = await kpPartsApi.categories()
    defaultKpCategories.value = (cats || []).map((c) => String(c.name || '')).filter(Boolean)
  } catch (e) {
    console.warn('加载默认 KP 大类失败', e)
    defaultKpCategories.value = []
  }
  if (!props.readonly && !configs.value.length) {
    configs.value = [blankConfig('CFG1')]
    activeKey.value = 'CFG1'
  }
}

// 表单定义（DB requirement_sheet_form）：字段/中文名/顺序/控件的唯一权威。
// 商机详情页这张表与 agent_fill 目标层预览消费同一份定义——改定义，两处同步变。
interface FormFieldDef {
  key: string
  label: string
  control: string
  placeholder?: string
  min?: number
  unit?: string
  /** 定义 key 与配置对象属性名不一致时的绑定桥（如 purchase_qty → qty） */
  bind?: string
}
const configFields = ref<FormFieldDef[]>([])

async function loadFormDefinition() {
  try {
    const { data } = await axios.get('/api/system-config/requirement_sheet_form/value')
    const fields = data?.value?.config_fields
    configFields.value = Array.isArray(fields) ? fields : []
  } catch {
    configFields.value = []
  }
}

loadModelOptions()
loadServerTypes()
loadDefaultKpCategories()
loadFormOptions()
loadFormDefinition()

function nextConfigName() {
  const nums = configs.value.map((c) => {
    const m = /^CFG(\d+)$/.exec(c.name)
    return m ? Number(m[1]) : 0
  })
  const max = nums.length ? Math.max(...nums) : 0
  return `CFG${max + 1}`
}

const activeConfig = computed(() => configs.value.find((c) => c.name === activeKey.value) || configs.value[0] || null)
const isAlternative = computed(() => configRelation.value === 'alternative')

const activeKpRows = computed<PortalSheetRow[]>({
  get: () => activeConfig.value?.kp_rows ?? [],
  set: (v) => {
    if (activeConfig.value) activeConfig.value.kp_rows = v
  },
})

function addConfig() {
  const cfg = blankConfig(nextConfigName())
  if (configRelation.value === 'alternative') {
    const demand = Number(configs.value[0]?.qty) || 1
    cfg.qty = demand
    if (!primaryConfig.value) primaryConfig.value = cfg.name
  }
  configs.value.push(cfg)
  activeKey.value = cfg.name
}

function removeConfig(cfg: RequirementConfig) {
  if (configs.value.length <= 1) return
  const idx = configs.value.findIndex((c) => c.name === cfg.name)
  configs.value = configs.value.filter((c) => c.name !== cfg.name)
  if (configRelation.value === 'alternative' && primaryConfig.value === cfg.name) {
    primaryConfig.value = configs.value[0]?.name || ''
  }
  activeKey.value = (configs.value[Math.min(idx, configs.value.length - 1)] || configs.value[0])?.name || ''
}

function addKpRow() {
  if (!activeConfig.value) return
  activeConfig.value.kp_rows.push(blankKpRow())
}

function onModelSelect(value: string) {
  const model = modelRecords.value.find((m) => m.name === value)
  const cfg = activeConfig.value
  if (!model || !cfg) return
  if (model.base_config?.series) cfg.platform_type = model.base_config.series
  if (model.base_config?.form) cfg.chassis_form = model.base_config.form
  if (model.server_type_id != null) {
    const typeName = serverTypeMap[String(model.server_type_id)]
    if (typeName) cfg.server_type = typeName
  }
  emit('change')
}

function warrantyNumber(value: unknown): number {
  const parsed = Number.parseInt(String(value ?? ''), 10)
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1
}

// ── RequirementSlots 组装/回填 ──
function toSlots(): RequirementSlots {
  const slots: RequirementSlots = {}
  const cfgList = configs.value.map((c) => ({
    name: c.name,
    server_model: c.server_model || '',
    platform_type: c.platform_type || '',
    server_type: c.server_type || '',
    chassis_form: c.chassis_form || '',
    qty: Number(c.qty) || 1,
    warranty_years: String(Number(c.warranty_years) || 1),
    kp_rows: (c.kp_rows || []).filter((r) => (r.catalogue || '').trim() || (r.description || '').trim()).map((r) => ({
      category: r.category || 'Key Parts',
      part_category: r.part_category || '',
      catalogue: r.catalogue || '',
      description: r.description || '',
      qty: Number(r.qty) || 1,
      note: r.note || '',
    })),
  }))
  slots.configs = cfgList

  // 配置关系透传：compose 数量 = Σ配置数量；alternative 数量 = 需求台数（取首配置，不求和）
  slots.config_relation = configRelation.value || 'compose'
  if (configRelation.value === 'alternative') {
    const demand = Number(cfgList[0]?.qty) || 1
    slots.purchase_qty = demand
    slots.primary_config = primaryConfig.value || (cfgList[0]?.name || '')
  } else {
    const totalQty = cfgList.reduce((sum, c) => sum + (Number(c.qty) || 0), 0)
    if (totalQty) slots.purchase_qty = totalQty
  }

  const first = cfgList[0]
  if (first) {
    if (first.server_model) slots.server_model = first.server_model
    if (first.platform_type) slots.platform_type = first.platform_type
    if (first.server_type) slots.server_type = first.server_type
    if (first.chassis_form) slots.chassis_form = first.chassis_form
    if (first.warranty_years) slots.warranty_years = first.warranty_years
    if (first.kp_rows.length) slots.kp_rows = first.kp_rows
  }
  return slots
}

function rowsFromConfig(cfg: any): PortalSheetRow[] {
  return (cfg.kp_rows || []).map((r: any) => ({ ...blankKpRow(r.part_category || ''), ...r }))
}

function fromSlots(slots: RequirementSlots) {
  configRelation.value = slots.config_relation === 'alternative' ? 'alternative' : 'compose'
  primaryConfig.value = slots.primary_config || ''
  const rawConfigs = Array.isArray(slots.configs) && slots.configs.length ? slots.configs : null
  if (rawConfigs) {
    configs.value = rawConfigs.map((c: any, i: number) => ({
      name: (c.name || '').trim() || `CFG${i + 1}`,
      server_model: c.server_model || '',
      platform_type: c.platform_type || '',
      server_type: c.server_type || '',
      chassis_form: c.chassis_form || '',
      qty: Number(c.qty) || 1,
      warranty_years: warrantyNumber(c.warranty_years ?? slots.warranty_years),
      kp_rows: rowsFromConfig(c),
    }))
    // 方案备选：主推默认第一个配置
    if (configRelation.value === 'alternative' && !primaryConfig.value) {
      primaryConfig.value = configs.value[0]?.name || ''
    }
  } else {
    const legacyKp = Array.isArray(slots.kp_rows) && slots.kp_rows.length
      ? slots.kp_rows.map((r: any) => ({ ...blankKpRow(r.part_category || ''), ...r }))
      : defaultKpCategories.value.map((cat) => blankKpRow(cat))
    configs.value = [{
      name: 'CFG1',
      server_model: slots.server_model || '',
      platform_type: slots.platform_type || '',
      server_type: slots.server_type || '',
      chassis_form: slots.chassis_form || '',
      qty: Number(slots.purchase_qty) || 1,
      warranty_years: warrantyNumber(slots.warranty_years),
      kp_rows: legacyKp,
    }]
  }
  activeKey.value = configs.value[0]?.name || 'CFG1'
}

const hasAnyPart = computed(() =>
  configs.value.some((c) => !!(
    (c.server_model || '').trim()
    || (c.platform_type || '').trim()
    || (c.server_type || '').trim()
    || (c.chassis_form || '').trim()
    || (c.kp_rows || []).some((r) => (r.catalogue || '').trim() || (r.description || '').trim())
  )),
)

defineExpose({ toSlots, fromSlots, hasAnyPart })
</script>

<template>
  <div class="req-form" :class="{ readonly }">
    <section class="rf-sec">
      <h4 class="rf-sec-title">需求原文<span class="rf-hint">客户原话，保留自由文本（后端仅辅助交叉校验）</span></h4>
      <a-textarea
        v-model:value="reqText"
        :disabled="readonly"
        :rows="3"
        placeholder="客户做超融合，要求 256G 内存，有 4 块 4TB NVMe 做缓存盘，双电源…"
      />
    </section>

    <section class="rf-sec">
      <div class="rf-config-head">
        <h4 class="rf-sec-title">配置<span class="rf-hint">每个配置独立机型/类型/数量/维保年限/部件清单</span></h4>
        <div class="rf-config-head-actions">
          <a-radio-group
            :value="configRelation"
            size="small"
            :disabled="readonly"
            @change="(e: any) => onConfigRelationChange(e.target.value)"
          >
            <a-radio-button value="compose">组合拆分</a-radio-button>
            <a-radio-button value="alternative">方案备选</a-radio-button>
          </a-radio-group>
          <a-button v-if="!readonly" size="small" @click="addConfig">+ 配置</a-button>
        </div>
      </div>

      <div v-if="configs.length" class="rf-config-tabs">
        <button
          v-for="(cfg, idx) in configs"
          :key="cfg.name"
          type="button"
          class="rf-config-tab"
          :class="{ active: cfg.name === activeConfig?.name }"
          @click="activeKey = cfg.name"
        >
          <span>{{ cfg.server_model || `配置 ${idx + 1}` }}</span>
          <span v-if="!readonly" class="rf-config-tab-close" @click.stop="removeConfig(cfg)">×</span>
        </button>
      </div>

      <div v-if="activeConfig" class="rf-config">
        <button
          v-if="isAlternative && !readonly"
          type="button"
          class="rf-primary-btn"
          :class="{ active: primaryConfig === activeConfig.name }"
          @click="markPrimary(activeConfig.name)"
        >{{ primaryConfig === activeConfig.name ? '☆ 主推方案' : '设为主推方案' }}</button>
        <div class="rf-config-grid">
          <div v-for="f in configFields" :key="f.key" class="rf-field">
            <label>{{ f.label }}</label>
            <a-auto-complete
              v-if="f.control === 'model_select'"
              v-model:value="activeConfig.server_model"
              :options="modelOptions"
              :disabled="readonly"
              :placeholder="f.placeholder"
              :allow-clear="false"
              :default-active-first-option="false"
              :backfill="false"
              style="width: 100%"
              @select="onModelSelect"
              @change="emit('change')"
            />
            <a-auto-complete
              v-else-if="f.control === 'series_select'"
              v-model:value="activeConfig.platform_type"
              :options="seriesOptions"
              :disabled="readonly"
              :placeholder="f.placeholder"
              :allow-clear="false"
              style="width: 100%"
              @change="emit('change')"
            />
            <a-auto-complete
              v-else-if="f.control === 'type_select'"
              v-model:value="activeConfig.server_type"
              :options="serverTypeOptions"
              :disabled="readonly"
              :placeholder="f.placeholder"
              :allow-clear="false"
              style="width: 100%"
              @change="emit('change')"
            />
            <a-auto-complete
              v-else-if="f.control === 'form_select'"
              v-model:value="activeConfig.chassis_form"
              :options="formOptions"
              :disabled="readonly"
              :placeholder="f.placeholder"
              :allow-clear="false"
              style="width: 100%"
              @change="emit('change')"
            />
            <div v-else-if="f.control === 'number'" class="rf-number-unit">
              <a-input-number
                v-model:value="activeConfig[f.bind || f.key]"
                :min="f.min || 1"
                :precision="0"
                :disabled="readonly"
                style="width: 100%"
                :placeholder="f.placeholder"
                @change="emit('change')"
              />
              <span v-if="f.unit" class="rf-unit">{{ f.unit }}</span>
            </div>
            <a-input
              v-else
              v-model:value="activeConfig[f.bind || f.key]"
              :disabled="readonly"
              :placeholder="f.placeholder"
              style="width: 100%"
              @change="emit('change')"
            />
          </div>
        </div>

        <h5 class="rf-kp-title">部件清单<span class="rf-hint">按 Catalogue 分类登记客户需求，可直接选择或输入配件</span></h5>
        <div class="rf-kp-editor">
          <div class="sheet-scroll">
            <table class="sheet-table unified-sheet">
              <thead>
                <tr>
                  <th class="sheet-col-group">分组</th>
                  <th class="sheet-col-cat">Catalogue</th>
                  <th class="sheet-col-desc">Configuration Description</th>
                  <th class="sheet-col-qty">Quantity</th>
                  <th class="sheet-col-note">Note</th>
                </tr>
              </thead>
              <KpPartsEditor
                v-model:rows="activeKpRows"
                :can-edit="!readonly"
                :show-drag="!readonly"
                :default-categories="defaultKpCategories"
              />
            </table>
          </div>
          <div v-if="!readonly" class="rf-adds">
            <a-button size="small" @click="addKpRow">+ 添加 KP 行</a-button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.req-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
  --sheet-panel: var(--cpq-bg-secondary);
  --sheet-surface: var(--cpq-bg-secondary);
  --sheet-head: var(--cpq-bg-tertiary);
  --sheet-line: var(--cpq-border-secondary);
  --sheet-line-strong: var(--cpq-border-primary);
  --sheet-hover: var(--cpq-overlay-w4);
  --sheet-focus: var(--cpq-overlay-a10);
  --sheet-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
}
.rf-sec-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
}
.rf-hint {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  color: var(--cpq-text-muted);
}
.rf-config-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.rf-config-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rf-config-head-actions .ant-radio-button-wrapper {
  font-size: 12px;
  padding: 0 12px;
}
.rf-primary-btn {
  border: 1px dashed var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: transparent;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  margin: 0 0 12px;
  transition: all 0.2s;
}
.rf-primary-btn.active {
  background: var(--cpq-accent-primary);
  color: #fff;
  border-style: solid;
}
.rf-config-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 12px;
}
.rf-config-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 999px;
  background: var(--cpq-bg-secondary);
  color: var(--cpq-text-secondary);
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.rf-config-tab.active {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
}
.rf-config-tab-close {
  color: var(--cpq-text-muted);
  font-size: 14px;
  line-height: 1;
}
.rf-config-tab-close:hover {
  color: var(--cpq-color-danger, #ff4d4f);
}
.rf-config-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 14px;
  margin-bottom: 14px;
}
.rf-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rf-field > label {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.rf-number-unit {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rf-unit {
  flex-shrink: 0;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}
.rf-kp-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
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
  border-right: 1px solid var(--sheet-line);
  border-bottom: 1px solid var(--sheet-line-strong);
}
.sheet-table thead th:last-child {
  border-right: 0;
}
.sheet-col-cat {
  width: 150px;
}
.sheet-col-group {
  width: 76px;
  text-align: center;
}
.sheet-col-desc {
  width: auto;
}
.sheet-col-qty {
  width: 80px;
  text-align: right;
}
.sheet-col-note {
  width: 150px;
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
.rf-adds {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
</style>
