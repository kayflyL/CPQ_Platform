<script setup lang="ts">
/**
 * 结构化需求表单（共享组件）——基本信息 + 部件清单 + 需求原文。
 *
 * 双形态：桌面表格（≥769px，类别/规格/数量/匹配横向铺开）/ 手机卡片列表（≤768px，
 * 每部件一张小卡）——同一数据两套渲染，CSS 断点切换。
 *
 * 数据模型 = RequirementSlots 契约（后端可直接消费）：
 * - 单值：platform_type/chassis_form/server_type/purchase_qty（基本信息）；cpu/memory（部件清单各一行锁定）
 * - 数组：storage/gpu/nic（多行可删，「+添加」加行）
 * - 平台类型/机箱形态下拉允许手输自由值（a-auto-complete，库外值不拦截——见 memory: requirement-gap-match-grading）
 * - 匹配度为提交后后端回填（编辑态不显示）
 */
import { ref, computed, reactive } from 'vue'
import { useSeries } from '@/composables/useSeries'
import { catalogApi, kpPartsApi } from '@/api/serverConfig'
import type { RequirementSlots, PortalSheetRow } from '@/api/portal'
import KpPartsEditor from '@/components/opportunity/KpPartsEditor.vue'

const props = withDefaults(defineProps<{
  readonly?: boolean
}>(), { readonly: false })

const emit = defineEmits<{ change: [] }>()

const { items: seriesItems, ensureSeries } = useSeries()
ensureSeries()

const FORMS = ['1U', '2U', '4U', '5U', '6U', '8U']
// 部件行的默认大类不再写死：从 KP 配件库读取真实大类，与 KpPartsEditor 子类目录同源。
const defaultKpCategories = ref<string[]>([])
const seriesOptions = computed(() => seriesItems.value.map(s => ({ value: s.value, label: s.label })))
const modelOptions = ref<{ value: string; label: string }[]>([])

async function loadModelOptions() {
  try {
    const res = await catalogApi.listModels()
    modelOptions.value = (res.models || [])
      .filter(m => m && m.name)
      .map(m => ({ value: m.name, label: m.name }))
  } catch {
    modelOptions.value = []
  }
}
loadModelOptions()

async function loadDefaultKpCategories() {
  try {
    const cats = await kpPartsApi.categories()
    defaultKpCategories.value = (cats || []).map(c => String(c.name || '')).filter(Boolean)
  } catch (e) {
    console.warn('加载默认 KP 大类失败', e)
    defaultKpCategories.value = []
  }
  // 目录异步到位后补一次播种（KpPartsEditor 挂载时 defaultCategories 仍为空，不会自动播种）
  if (!props.readonly && !kpRows.value.length) seedKpRows()
}
loadDefaultKpCategories()

// ── 表单状态（v-model 式：父组件经 ref 取 formState 组装 slots）──
const basic = reactive({ server_model: '', platform_type: '', chassis_form: '', server_type: '', purchase_qty: undefined as number | undefined, warranty_years: '' })
const kpRows = ref<PortalSheetRow[]>([])
const reqText = defineModel<string>('reqText', { default: '' })

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

function seedKpRows() {
  kpRows.value = defaultKpCategories.value.map((cat) => blankKpRow(cat))
}

function addKpRow() {
  kpRows.value.push(blankKpRow())
}

// ── RequirementSlots 组装/回填 ──

/** 表单 → RequirementSlots（平台类型/机箱形态/数量归需求单基本信息） */
function toSlots(): RequirementSlots {
  const slots: RequirementSlots = {}
  if (basic.server_model) slots.server_model = basic.server_model
  if (basic.platform_type) slots.platform_type = basic.platform_type
  if (basic.chassis_form) slots.chassis_form = basic.chassis_form
  if (basic.server_type) slots.server_type = basic.server_type
  if (basic.purchase_qty) slots.purchase_qty = basic.purchase_qty
  if (basic.warranty_years) slots.warranty_years = basic.warranty_years
  const kp = kpRows.value
    .filter(r => (r.catalogue || '').trim())
    .map(r => ({
      category: r.category || 'Key Parts',
      part_category: r.part_category || '',
      catalogue: r.catalogue || '',
      description: r.description || '',
      qty: Number(r.qty) || 1,
      note: r.note || '',
    }))
  if (kp.length) slots.kp_rows = kp
  return slots
}

/** RequirementSlots → 表单（加载历史版本） */
function fromSlots(slots: RequirementSlots) {
  basic.server_model = slots.server_model || ''
  basic.platform_type = slots.platform_type || ''
  basic.chassis_form = slots.chassis_form || ''
  basic.server_type = slots.server_type || ''
  basic.purchase_qty = slots.purchase_qty
  basic.warranty_years = slots.warranty_years || ''
  if (Array.isArray(slots.kp_rows) && slots.kp_rows.length) {
    kpRows.value = slots.kp_rows.map((r: any) => ({ ...blankKpRow(r.part_category || ''), ...r }))
    return
  }

  const rows: PortalSheetRow[] = []
  if (slots.cpu?.model || slots.cpu?.brand || slots.cpu?.qty) {
    rows.push({ ...blankKpRow('CPU'), catalogue: [slots.cpu.model, slots.cpu.brand].filter(Boolean).join(' '), qty: slots.cpu.qty || 1 })
  }
  if (slots.memory?.per_stick_gb || slots.memory?.qty || slots.memory?.type || slots.memory?.brand) {
    rows.push({
      ...blankKpRow('Memory'),
      catalogue: [slots.memory.per_stick_gb ? `${slots.memory.per_stick_gb}GB` : '', slots.memory.type, slots.memory.brand].filter(Boolean).join(' '),
      qty: slots.memory.qty || 1,
    })
  }
  for (const s of slots.storage || []) {
    rows.push({
      ...blankKpRow('HDD/SSD'),
      catalogue: [s.capacity, s.interface, s.brand].filter(Boolean).join(' '),
      qty: s.qty || 1,
    })
  }
  for (const g of slots.gpu || []) {
    rows.push({ ...blankKpRow('GPU'), catalogue: [g.model, g.brand].filter(Boolean).join(' '), qty: g.qty || 1 })
  }
  for (const n of slots.nic || []) {
    rows.push({
      ...blankKpRow('NIC'),
      catalogue: [n.model, n.speed_g ? `${n.speed_g}G` : '', n.ports ? `${n.ports}口` : '', n.brand].filter(Boolean).join(' '),
      qty: n.qty || 1,
    })
  }
  const raids = Array.isArray(slots.raid) ? slots.raid : (slots.raid ? [slots.raid] : [])
  for (const r of raids) {
    rows.push({ ...blankKpRow('Raid card'), catalogue: [r.model, r.cache ? `${r.cache}缓存` : ''].filter(Boolean).join(' '), qty: r.qty || 1 })
  }
  if (slots.psu?.wattage || slots.psu?.qty) {
    rows.push({
      ...blankKpRow('Power Supply'),
      catalogue: [slots.psu.wattage ? `${slots.psu.wattage}W` : '', slots.psu.redundancy].filter(Boolean).join(' '),
      qty: slots.psu.qty || 1,
    })
  }
  kpRows.value = rows.length ? rows : defaultKpCategories.value.map((cat) => blankKpRow(cat))
}

/** 是否填了任何部件（空表单禁止提交由父组件判断） */
const hasAnyPart = computed(() =>
  !!(basic.server_model || basic.platform_type || basic.chassis_form || basic.server_type || basic.purchase_qty || basic.warranty_years ||
     kpRows.value.some(r => (r.catalogue || '').trim())))

defineExpose({ toSlots, fromSlots, hasAnyPart, basic, seedKpRows, addKpRow })
</script>

<template>
  <div class="req-form" :class="{ readonly }">
    <!-- ── 基本信息 ── -->
    <section class="rf-sec">
      <h4 class="rf-sec-title">基本信息</h4>
      <div class="rf-grid">
        <div class="rf-field">
          <label>服务器型号</label>
          <a-auto-complete
            v-model:value="basic.server_model"
            :options="modelOptions"
            :disabled="readonly"
            placeholder="可输入或选择"
            :allow-clear="false"
            :default-active-first-option="false"
            :backfill="false"
            @keydown.enter.prevent
            @change="emit('change')"
            style="width: 100%"
          />
        </div>
        <div class="rf-field">
          <label>平台类型</label>
          <a-auto-complete
            v-model:value="basic.platform_type"
            :options="seriesOptions"
            :disabled="readonly"
            placeholder="如 Orion（可手输）"
            :allow-clear="false"
            style="width: 100%"
            @change="emit('change')"
          />
        </div>
        <div class="rf-field">
          <label>机箱形态</label>
          <a-auto-complete
            v-model:value="basic.chassis_form"
            :options="FORMS.map(f => ({ value: f, label: f }))"
            :disabled="readonly"
            placeholder="如 2U"
            :allow-clear="false"
            style="width: 100%"
            @change="emit('change')"
          />
        </div>
        <div class="rf-field">
          <label>服务器类型</label>
          <a-input v-model:value="basic.server_type" :disabled="readonly" placeholder="如 通用计算服务器" @change="emit('change')" />
        </div>
        <div class="rf-field">
          <label>数量（台）</label>
          <a-input-number v-model:value="basic.purchase_qty" :min="1" :disabled="readonly" style="width: 100%" placeholder="整机台数" />
        </div>
        <div class="rf-field">
          <label>维保年限</label>
          <a-input v-model:value="basic.warranty_years" :disabled="readonly" placeholder="如 3年" @change="emit('change')" />
        </div>
      </div>
    </section>

    <!-- ── 部件清单：KP 共享编辑器 ── -->
    <section class="rf-sec">
      <h4 class="rf-sec-title">部件清单<span class="rf-hint">从配件库选择，类别/配件与方案配置一致</span></h4>
      <div class="rf-kp-editor">
        <div class="sheet-scroll">
          <table class="rf-table">
            <thead>
              <tr>
                <th class="col-group">分组</th>
                <th class="col-cat">类别</th>
                <th>配件</th>
                <th class="col-qty">数量</th>
              </tr>
            </thead>
            <KpPartsEditor
              v-model:rows="kpRows"
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
    </section>

    <!-- ── 需求原文 ── -->
    <section class="rf-sec">
      <h4 class="rf-sec-title">需求原文<span class="rf-hint">客户原话，保留自由文本（后端仅辅助交叉校验）</span></h4>
      <a-textarea v-model:value="reqText" :disabled="readonly" :rows="3" placeholder="客户做超融合，要求 256G 内存，有 4 块 4TB NVMe 做缓存盘，双电源…" />
    </section>
  </div>
</template>

<style scoped>
.req-form { display: flex; flex-direction: column; gap: 18px; }
.rf-sec-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
}
.rf-hint { margin-left: 8px; font-size: 11px; font-weight: 400; color: var(--cpq-text-muted); }

.req-form { container-type: inline-size; }

/* 基本信息：桌面两列、手机一列 */
.rf-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 14px;
}
.rf-field { display: flex; flex-direction: column; gap: 4px; }
.rf-field > label { font-size: 12px; color: var(--cpq-text-muted); }

/* 桌面表格 */
.rf-table { width: 100%; border-collapse: collapse; }
.rf-table th {
  text-align: left; font-size: 12px; font-weight: 500;
  color: var(--cpq-text-muted); padding: 4px 6px;
  border-bottom: 1px solid var(--cpq-glass-border);
}
.rf-table td { padding: 6px; border-bottom: 1px solid var(--cpq-glass-border); vertical-align: middle; }
.col-group { width: 56px; font-size: 12px; color: var(--cpq-text-secondary); }
.col-cat {
  width: 150px;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.col-qty { width: 90px; }
.col-brand { width: 130px; }
.col-op { width: 44px; text-align: center; }
.cell-spec { display: flex; gap: 6px; align-items: center; }
.muted { font-size: 11px; color: var(--cpq-text-muted); }
.rf-del { color: var(--cpq-text-muted); cursor: pointer; font-size: 14px; }
.rf-del:hover { color: var(--cpq-color-danger, #ff4d4f); }
.rf-adds { display: flex; gap: 8px; margin-top: 10px; }

/* 形态切换：容器查询，≤559 紧凑态 —— 隐藏「分组」列，保留 类别/配件/数量 */
@container (max-width: 559px) {
  /* 基本信息保持 2 列（窄态可读，不闪单列） */
  .rf-grid { grid-template-columns: repeat(2, 1fr); }
  /* 分组表头 + KpPartsEditor 分组单元格同步隐藏，避免表头/表体错位 */
  .col-group { display: none; }
  :deep(.sheet-group) { display: none; }
  .col-qty { width: 60px; }
  .rf-adds { flex-wrap: wrap; }
  .rf-adds :deep(.ant-btn) { min-height: 44px; flex: 1; }
  .rf-field :deep(.ant-input) { min-height: 36px; }
}
</style>
