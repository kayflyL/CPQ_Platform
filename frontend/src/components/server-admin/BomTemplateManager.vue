<script setup lang="ts">
/** BOM 模板管理（管理面独立卡片，挂在基准配置列表下方）— 列表 + 编辑弹窗。
 *  设计：从现有模板复制起步、新行自动带默认规则、行列表表格化 + 规则摘要、实时预览。
 *  规则跟模板存 JSONB、求值跑前端工作台 / 后端方案助手两套引擎（同一口径）。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import { bomTemplateApi, type BomTemplate, type BomTemplateRow, type BomRule } from '@/api/serverConfig'
import { policyDocApi } from '@/api/strategies'
import { readDocBody } from '@/constants/policyMeta'
import { evalBomContext } from '@/utils/bomRuleEngine'
import { loadBomCategoryAliases, getBomCategoryAliases, invalidateBomCategoryAliases } from '@/utils/bomCategoryAliases'
import { systemConfigApi } from '@/api/systemConfig'
import MarkdownView from '@/components/common/MarkdownView.vue'
import BomRuleSourceEditor from './BomRuleSourceEditor.vue'

type EditableRow = BomTemplateRow & { uid: number }
let uidSeq = 1
const clone = (x: any) => JSON.parse(JSON.stringify(x))

const templates = ref<(BomTemplate & { _usage?: number })[]>([])
const loading = ref(false)
const modalVisible = ref(false)
const editingId = ref<number | null>(null)
const name = ref('')
const rows = ref<EditableRow[]>([])
const saving = ref(false)

const aliasModalOpen = ref(false)
const aliasText = ref('')
const aliasSaving = ref(false)

/** 行类型：中文说明 + 分组（自动计算 / 人工填写） */
interface RowTypeDef { value: string; label: string; short: string; group: 'auto' | 'manual' }
const ROW_TYPES: RowTypeDef[] = [
  { value: 'front_backplane', label: '前面背板 · 盘位/背板描述', short: 'Front backplane', group: 'auto' },
  { value: 'io_slot', label: 'IO 槽位 · 该槽位 riser 规格', short: 'IO', group: 'auto' },
  { value: 'rear_summary', label: '后面板汇总 · Direct/Switch', short: 'Rear Summary', group: 'auto' },
  { value: 'heatsink', label: '散热器 · 自动取料号', short: 'Heatsink', group: 'auto' },
  { value: 'fan', label: '风扇 · 自动取料号', short: 'FAN', group: 'auto' },
  { value: 'psu_requirement', label: '电源需求 · 自动取配置', short: 'Power Supply Requirement', group: 'auto' },
  { value: 'gpu_power_cord', label: 'GPU 电源线 · 自动推导', short: 'GPU Power cord', group: 'auto' },
  { value: 'power_cord', label: '电源线 · 自动推导', short: 'Power cord', group: 'auto' },
  { value: 'rail_kit', label: '滑轨 · 自动取料号', short: 'Rail kit', group: 'auto' },
  { value: 'cable', label: '线缆 · 自动推导', short: 'Cable', group: 'auto' },
  { value: 'raid_slot', label: 'RAID 槽位 · 人工填写', short: 'Raid slot', group: 'manual' },
]
const autoTypes = ROW_TYPES.filter(t => t.group === 'auto')
const manualTypes = ROW_TYPES.filter(t => t.group === 'manual')
const SLOT_OPTIONS = ['IO1', 'IO2', 'IO3', 'IO4', 'OCP']

/** 新行推荐默认规则：按行类型自动填充，保存即合理（依据现有真实模板整理，可自行调整） */
const RECOMMENDED_RULES: Record<string, BomRule> = {
  front_backplane: { desc: { kind: 'template', template: '${bays}*3.5 ${bp_type_desc}' }, qty: { kind: 'fixed', value: 1 } },
  io_slot: { desc: { kind: 'struct_count', scope: 'io_slot' }, qty: { kind: 'fixed', value: 1 } },
  rear_summary: { desc: { kind: 'struct_count', scope: 'rear_all' }, qty: { kind: 'fixed', value: 1 } },
  heatsink: { desc: { kind: 'part_field', category: 'heatsink', field: 'name' }, qty: { kind: 'part_quantity', category: 'heatsink' } },
  fan: { desc: { kind: 'part_field', category: 'fan', field: 'name' }, qty: { kind: 'part_quantity', category: 'fan' } },
  psu_requirement: { desc: { kind: 'template', template: '${psu_wattage}W' }, qty: { kind: 'config_calc', key: 'psu_qty' } },
  gpu_power_cord: { desc: { kind: 'config_value', key: 'gpu_power_cord_desc' }, qty: { kind: 'config_calc', key: 'gpu_cable_qty' } },
  power_cord: { desc: { kind: 'fixed', value: '国标电源线' }, qty: { kind: 'config_calc', key: 'psu_qty' } },
  rail_kit: { desc: { kind: 'part_field', category: 'rail', field: 'name' }, qty: { kind: 'part_quantity', category: 'rail' } },
  cable: { desc: { kind: 'config_value', key: 'cable_desc' }, qty: { kind: 'fixed', value: 1 } },
  raid_slot: { desc: { kind: 'manual' }, qty: { kind: 'manual' } },
}

// ---- 模板说明（抽屉）：内容以文档库《BOM 模板配置指南》为唯一数据源，实时拉取渲染 ----
const helpOpen = ref(false)
const helpMarkdown = ref('')
const helpLoading = ref(false)
const helpMissing = ref(false)
const HELP_DOC_NAME = 'BOM 模板配置指南'
async function openHelp() {
  helpOpen.value = true
  helpMarkdown.value = ''
  helpMissing.value = false
  helpLoading.value = true
  try {
    const res = await policyDocApi.list('selection')
    const doc = (res.docs || []).find(d => d.name === HELP_DOC_NAME)
    if (doc) helpMarkdown.value = readDocBody(doc.body).content_markdown
    else helpMissing.value = true
  } catch {
    helpMissing.value = true
  } finally {
    helpLoading.value = false
  }
}

// ---- 行规则编辑(primary + 可选 fallback)----
const expanded = ref<Set<number>>(new Set())
function toggleRule(i: number) {
  ensureRule(rows.value[i])
  const s = new Set(expanded.value); s.has(i) ? s.delete(i) : s.add(i); expanded.value = s
}
function defaultRuleFor(type: string): BomRule {
  return clone(RECOMMENDED_RULES[type] || { desc: { kind: 'manual' }, qty: { kind: 'manual' } })
}
function ensureRule(r: BomTemplateRow) {
  if (!r.rule) r.rule = defaultRuleFor(r.type)
  else {
    if (!r.rule.desc) r.rule.desc = clone(RECOMMENDED_RULES[r.type]?.desc || { kind: 'manual' })
    if (!r.rule.qty) r.rule.qty = clone(RECOMMENDED_RULES[r.type]?.qty || { kind: 'manual' })
  }
}
function onDescChange(r: BomTemplateRow, v: any) { ensureRule(r); r.rule!.desc = v }
function onQtyChange(r: BomTemplateRow, v: any) { ensureRule(r); r.rule!.qty = v }
function toggleDescFb(r: BomTemplateRow, on: boolean) {
  ensureRule(r); r.rule!.desc_fallback = on ? clone(RECOMMENDED_RULES[r.type]?.desc || { kind: 'manual' }) : undefined
}
function toggleQtyFb(r: BomTemplateRow, on: boolean) {
  ensureRule(r); r.rule!.qty_fallback = on ? clone(RECOMMENDED_RULES[r.type]?.qty || { kind: 'manual' }) : undefined
}
function canFallback(kind: string) { return kind !== 'manual' && kind !== 'fixed' }

function addRow() {
  const type = 'cable'
  rows.value.push({ type, label: ROW_TYPES.find(t => t.value === type)!.short, rule: defaultRuleFor(type), uid: ++uidSeq })
}
function delRow(i: number) { rows.value.splice(i, 1) }
function onTypeChange(i: number) {
  const r = rows.value[i]
  if (r.type === 'io_slot') { if (!r.slot) r.slot = 'IO1' } else { delete r.slot }
  if (r.type === 'rear_summary') { if (!r.mode) r.mode = 'direct' } else { delete r.mode }
  const def = ROW_TYPES.find(t => t.value === r.type)
  if (def && !r.label) r.label = def.short
  r.rule = defaultRuleFor(r.type)   // 切换类型 → 重置为该类型推荐规则，避免残留不匹配规则
}

/** OCP 槽防呆：slot 切到 OCP 且 qty 还是默认 fixed 1 时，自动切成 config_calc ocp_qty
 * （否则没选 OCP 时 qty=1，OCP 行不会随「未选」隐藏）。 */
function onSlotChange(r: BomTemplateRow) {
  if ((r.slot || '').toUpperCase() !== 'OCP') return
  const q = r.rule?.qty as any
  if (q?.kind === 'fixed' && Number(q.value) === 1) r.rule!.qty = { kind: 'config_calc', key: 'ocp_qty' }
}

/** 规则摘要：不开 ⚙ 也知道这行怎么算 */
function describeSource(src: any, mode: 'desc' | 'qty'): string {
  if (!src) return '手动填写'
  switch (src.kind) {
    case 'fixed': return mode === 'desc' ? `固定文字「${src.value || ''}」` : `固定数量 ${src.value ?? ''}`
    case 'part_field': return `料号 ${src.category}.${src.field}`
    case 'part_quantity': return `料号数量 ${src.category}`
    case 'template': return `模板「${src.template || ''}」`
    case 'struct_count': {
      const m: Record<string, string> = { io_slot: '该槽位 riser', rear_all: '后面板汇总', gpu_direct: 'GPU 直连', front_cables: '前面板线缆' }
      return `结构(${m[src.scope] || src.scope})`
    }
    case 'config_value': return `配置 ${src.key}`
    case 'config_calc': return `配置数量 ${src.key}`
    default: return '手动填写'
  }
}
function describeRule(r: BomTemplateRow): string {
  if (!r.rule) return '手动填写'
  const bothManual = r.rule.desc?.kind === 'manual' && r.rule.qty?.kind === 'manual'
  if (bothManual) return '手动填写'
  return `${describeSource(r.rule.desc, 'desc')} / ${describeSource(r.rule.qty, 'qty')}`
}

// ---- 从现有模板复制（新建时可选）----
const copyFromId = ref<number | undefined>(undefined)
async function onCopyFrom(id: number) {
  if (!id) return
  try {
    const full = await bomTemplateApi.get(id)
    rows.value = (full.rows || []).map(r => ({ ...clone(r), uid: ++uidSeq }))
    expanded.value = new Set()
    message.success(`已带入「${full.name}」的 ${rows.value.length} 行骨架，可直接改名保存`)
  } catch { message.error('复制失败') }
}

// ---- 实时预览：用演示数据跑求值引擎，让用户改完立刻看到效果 ----
const demoVars: Record<string, any> = {
  bays: '24', form: '2U', series: 'R760', bp_type: 'tri', bp_type_desc: 'SATA/SAS/NVMe',
  psu_qty: 2, psu_wattage: '2000', psu_name: '2000W', gpu_qty: 2, gpu_cable_qty: 2,
  gpu_power_cord_desc: 'GPU power cable', nvme_count: 4, cable_desc: '9560 8SAS Cable，2NVMe Cable',
  standard_riser: 'X8 Riser', riser_x16: 'X16 Riser', high_bw_nic: false,
}
const demoParts = [
  { category: 'heatsink', name: '2U 风冷散热器', quantity: 2, specs: { model: 'HR3000' } },
  { category: 'fan', name: '高风压风扇', quantity: 4, specs: { model: 'FAN-A' } },
  { category: 'rail', name: '标准滑轨', quantity: 1, specs: {} },
  { category: 'backplane', name: '24 盘位背板', quantity: 1, specs: { bt: 'tri' } },
  { category: 'psu', name: '2000W 电源', quantity: 2, specs: {} },
  { category: 'cable', name: '线缆包', quantity: 1, specs: {} },
]
const preview = computed(() => {
  const ctx = {
    vars: demoVars,
    parts: demoParts,
    rear: {},
    frontCableQty: () => 0,
    frontCableInfo: () => ({ pn: '', n: 0, group: '-' as const, price: 0, name: '' }),
    categoryAliases: getBomCategoryAliases(),
  }
  const evaled = evalBomContext(rows.value, ctx)
  return rows.value.map((r, i) => {
    const key = r.slot || r.type
    const v = evaled[key] || { desc: '', qty: '' }
    const manual = !r.rule || (r.rule.desc?.kind === 'manual' && r.rule.qty?.kind === 'manual')
    // 与 BomTable 空行隐藏一致：desc 与 qty 都空 → 整行不显示（manual/算不出同理）
    const descEmpty = !v.desc
    const qtyEmpty = v.qty === '' || v.qty == null || v.qty === 0
    const hidden = descEmpty && qtyEmpty
    return {
      key: `${i}-${key}`,
      label: r.label || key,
      desc: v.desc || '',
      qty: String(v.qty ?? ''),
      summary: describeRule(r),
      manual,
      hidden,
    }
  })
})
const previewVisible = computed(() => preview.value.filter(p => !p.hidden))

async function load() {
  loading.value = true
  try {
    const r = await bomTemplateApi.list()
    const list = r.templates || []
    const usages = await Promise.all(list.map(t =>
      fetch(`/api/bom-templates/${t.id}/usage`).then(x => x.json()).catch(() => ({ count: 0 })))
    )
    templates.value = list.map((t, i) => ({ ...t, _usage: usages[i]?.count || 0 }))
  } finally { loading.value = false }
}
function openNew() {
  editingId.value = null; name.value = ''; rows.value = []; copyFromId.value = undefined
  expanded.value = new Set(); modalVisible.value = true
}
async function openEdit(t: BomTemplate) {
  editingId.value = t.id
  const full = await bomTemplateApi.get(t.id)
  name.value = full.name
  rows.value = (full.rows || []).map(r => ({ ...clone(r), uid: ++uidSeq }))
  expanded.value = new Set()
  modalVisible.value = true
}
async function save() {
  if (!name.value.trim()) return message.warning('请填模板名')
  for (const r of rows.value) {
    if (r.type === 'io_slot' && !r.slot) return message.warning('IO 槽位行需选 slot（IO1~IO4/OCP）')
  }
  saving.value = true
  try {
    const payload = { name: name.value.trim(), rows: rows.value.map(({ uid: _uid, ...rest }) => rest) }
    if (editingId.value) await bomTemplateApi.update(editingId.value, payload)
    else editingId.value = (await bomTemplateApi.create(payload)).id
    message.success('模板已保存（所有用此模板的基准配置立即生效）')
    modalVisible.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
async function remove(t: BomTemplate) {
  try {
    const r = await bomTemplateApi.delete(t.id)
    message.success(`已删除${r.detached_base_configs ? `（${r.detached_base_configs} 个基准配置被解绑）` : ''}`)
    await load()
  } catch { message.error('删除失败') }
}


async function openAliasModal() {
  try {
    const v = await systemConfigApi.getValue<any>('bom_category_aliases')
    aliasText.value = JSON.stringify((v && typeof v === 'object') ? v : {}, null, 2)
  } catch { aliasText.value = '{}' }
  aliasModalOpen.value = true
}
async function saveAliasModal() {
  let parsed: any
  try { parsed = JSON.parse(aliasText.value) }
  catch { return message.error('JSON 解析失败，请检查格式') }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return message.error('请输入对象：{ category: [别名...] }')
  aliasSaving.value = true
  try {
    await systemConfigApi.set('bom_category_aliases', parsed)
    invalidateBomCategoryAliases()
    await loadBomCategoryAliases()
    message.success('品类别名已保存')
    aliasModalOpen.value = false
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { aliasSaving.value = false }
}
const columns = [
  { title: '模板名', dataIndex: 'name', key: 'name' },
  { title: '行数', key: 'rows', width: 80 },
  { title: '用途', key: 'usage', width: 100 },
  { title: '操作', key: 'op', width: 120 },
]
onMounted(async () => {
  load()
  await loadBomCategoryAliases()
})
defineExpose({ load })
</script>

<template>
  <div class="panel glass">
    <div class="lib-head">
      <h3>BOM 模板</h3>
      <span class="lib-actions">
        <a-button size="small" @click="openAliasModal()">⚙️ 品别名</a-button>
        <a-button size="small" @click="openHelp()">📖 模板说明</a-button>
        <a-button type="primary" size="small" @click="openNew">+ 新建模板</a-button>
      </span>
    </div>
    <div class="tpl-hint">左栏 L6 配置单的机型族行骨架 + 每行解析规则(desc/qty 怎么算)。基准配置通过下拉关联此处的模板。</div>
    <a-table :data-source="templates" :columns="columns" :loading="loading" row-key="id" size="small" :pagination="false">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'rows'">{{ record.rows?.length || 0 }} 行</template>
        <template v-else-if="column.key === 'usage'">{{ record._usage ?? 0 }} 个基准</template>
        <template v-else-if="column.key === 'op'">
          <a-button size="small" link @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="删除该模板？关联的基准配置会变为无模板。" @confirm="remove(record)">
            <a-button size="small" link danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <a-modal :open="modalVisible" :title="editingId ? '编辑 BOM 模板' : '新建 BOM 模板'" width="1120px"
             :okText="saving ? '保存中…' : '保存'" @ok="save" @cancel="modalVisible = false" :destroyOnClose="true">
      <a-form layout="vertical">
        <a-form-item label="模板名" required>
          <a-input v-model:value="name" placeholder="如：2U12标准、4U8-GPU直连" />
        </a-form-item>
        <a-form-item v-if="!editingId" label="从现有模板复制（可选）">
          <a-select v-model:value="copyFromId" placeholder="选择模板，整份带入行骨架与规则，改名即可用" allow-clear
            @change="(v: number) => v && onCopyFrom(v)">
            <a-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}（{{ t.rows?.length || 0 }} 行）</a-select-option>
          </a-select>
        </a-form-item>

        <div class="editor-split">
          <div class="editor-left">
            <div class="sec-label">行骨架（顺序即左栏显示顺序）· 点规则摘要可展开精细编辑</div>
            <div class="tpl-table">
          <div class="tpl-thead">
            <span class="c-drag"></span>
            <span class="c-idx">#</span>
            <span class="c-type">行类型</span>
            <span class="c-label">左栏标签</span>
            <span class="c-slot">槽位/形态</span>
            <span class="c-rule">解析规则</span>
            <span class="c-op">操作</span>
          </div>
          <draggable v-model="rows" item-key="uid" handle=".tpl-drag" :animation="180" class="tpl-tbody">
            <template #item="{ element: r, index: i }">
              <div class="tpl-tr-wrap" :class="{ expanded: expanded.has(i) }">
                <div class="tpl-tr">
                  <span class="c-drag"><span class="tpl-drag" title="拖拽排序">⠿</span></span>
                  <span class="c-idx row-idx">{{ i + 1 }}</span>
                  <span class="c-type">
                    <a-select :value="r.type" size="small" style="width: 100%" @change="(v: string) => { r.type = v; onTypeChange(i) }">
                      <a-select-opt-group label="系统自动计算">
                        <a-select-option v-for="t in autoTypes" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                      </a-select-opt-group>
                      <a-select-opt-group label="需人工填写">
                        <a-select-option v-for="t in manualTypes" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                      </a-select-opt-group>
                    </a-select>
                  </span>
                  <span class="c-label"><a-input v-model:value="r.label" size="small" placeholder="左栏标签" /></span>
                  <span class="c-slot">
                    <a-select v-if="r.type === 'io_slot'" v-model:value="r.slot" size="small" style="width: 100%" @change="onSlotChange(r)">
                      <a-select-option v-for="s in SLOT_OPTIONS" :key="s" :value="s">{{ s }}</a-select-option>
                    </a-select>
                    <a-select v-else-if="r.type === 'rear_summary'" v-model:value="r.mode" size="small" style="width: 100%">
                      <a-select-option value="direct">direct</a-select-option>
                      <a-select-option value="switch">switch</a-select-option>
                    </a-select>
                    <span v-else class="c-slot-empty">—</span>
                  </span>
                  <span class="c-rule">
                    <button class="rule-chip" :class="{ active: expanded.has(i) }" @click="toggleRule(i)" :title="expanded.has(i) ? '收起' : '展开精细编辑'">
                      {{ describeRule(r) }}
                    </button>
                  </span>
                  <span class="c-op"><a-button size="small" link danger @click="delRow(i)">删除</a-button></span>
                </div>
                <div v-if="expanded.has(i) && r.rule" class="tpl-rule">
                  <div class="rule-line">
                    <span class="rule-lab">描述</span>
                    <BomRuleSourceEditor :model-value="r.rule.desc" mode="desc" :row-type="r.type" @update:model-value="(v: any) => onDescChange(r, v)" />
                  </div>
                  <div class="rule-line" v-if="canFallback(r.rule.desc.kind)">
                    <span class="rule-lab sub">└ 兜底</span>
                    <a-checkbox :checked="!!r.rule.desc_fallback" @change="(e: any) => toggleDescFb(r, e.target.checked)">算不出时启用</a-checkbox>
                    <BomRuleSourceEditor v-if="r.rule.desc_fallback" :model-value="r.rule.desc_fallback" mode="desc" :row-type="r.type"
                      @update:model-value="(v: any) => { r.rule!.desc_fallback = v }" />
                  </div>
                  <div class="rule-line">
                    <span class="rule-lab">数量</span>
                    <BomRuleSourceEditor :model-value="r.rule.qty" mode="qty" :row-type="r.type" @update:model-value="(v: any) => onQtyChange(r, v)" />
                  </div>
                  <div class="rule-line" v-if="canFallback(r.rule.qty.kind)">
                    <span class="rule-lab sub">└ 兜底</span>
                    <a-checkbox :checked="!!r.rule.qty_fallback" @change="(e: any) => toggleQtyFb(r, e.target.checked)">算不出时启用</a-checkbox>
                    <BomRuleSourceEditor v-if="r.rule.qty_fallback" :model-value="r.rule.qty_fallback" mode="qty" :row-type="r.type"
                      @update:model-value="(v: any) => { r.rule!.qty_fallback = v }" />
                  </div>
                </div>
              </div>
            </template>
            </draggable>
            </div>
            <a-button size="small" dashed style="margin-top:6px" @click="addRow">+ 添加行</a-button>
          </div>
          <div class="editor-right">
            <div class="preview-sec">
          <div class="preview-head">实时预览 <em>演示数据 · 真实值以保存后的工作台 / 方案助手为准</em></div>
          <div class="preview-body">
            <div v-if="previewVisible.length" class="pv-table-wrap">
              <div class="pv-table-head">
                <span class="pv-title">L6 配置单</span>
                <span class="pv-sub">预览 · 演示数据</span>
              </div>
              <table class="pv-table no-cost">
                <thead>
                  <tr>
                    <th class="col-catalogue">Catalogue</th>
                    <th class="col-desc">Description</th>
                    <th class="col-qty">Qty</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in previewVisible" :key="p.key" class="pv-row">
                    <td class="cell-catalogue">{{ p.label }}</td>
                    <td class="cell-desc">{{ p.desc || '[空]' }}</td>
                    <td class="cell-qty">{{ p.qty || '[空]' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
              <a-empty v-else description="暂无行，先添加或从模板复制" :image-simple="true" />
            </div>
            </div>
          </div>
        </div>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="helpOpen" title="BOM 模板说明" width="880" :destroy-on-close="true">
      <div class="bh">
        <p class="bh-lead">内容以「策略中心 → 选型配置 → 📄 文档库」的《BOM 模板配置指南》为唯一数据源（文档库中可编辑，此处每次打开实时同步展示）。</p>
        <a-spin :spinning="helpLoading">
          <MarkdownView v-if="!helpLoading && helpMarkdown" :content="helpMarkdown" />
          <a-empty v-else-if="!helpLoading && helpMissing" description="文档库暂无《BOM 模板配置指南》，请到 策略中心 → 选型配置 → 📄 文档库 新建" />
        </a-spin>
      </div>
    </a-drawer>
    <a-modal v-model:open="aliasModalOpen" title="BOM 品类别名（system_config.bom_category_aliases）" width="720" :confirm-loading="aliasSaving" @ok="saveAliasModal()">
      <p class="tpl-hint">模板 row 常填英文 category（heatsink/fan/rail/chassis/backplane/cable/psu），底盘件 parts_master category 多为中文；此处维护中英别名用于跨语言匹配零件。格式：{ "heatsink": ["散热器"] }。</p>
      <a-textarea v-model:value="aliasText" :rows="12" spellcheck="false" />
    </a-modal>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.lib-actions { display: inline-flex; gap: 8px; }
.tpl-hint { font-size: 11px; color: var(--cpq-text-muted, #6E7582); margin-bottom: 10px; line-height: 1.5; }
.sec-label { font-size: 12px; color: var(--cpq-text-muted, #6E7582); margin: 4px 0 8px; }

/* 行骨架表格：列头 + 行 + 规则摘要 chip */
.tpl-table { border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.08)); border-radius: 10px; overflow: hidden; }
.tpl-thead, .tpl-tr {
  display: grid;
  grid-template-columns: 22px 26px minmax(200px, 1.35fr) minmax(130px, 1fr) 96px minmax(210px, 1.6fr) 52px;
  gap: 6px; align-items: center; padding: 6px 10px;
}
.tpl-thead { font-size: 11px; font-weight: 600; color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w6, rgba(255,255,255,0.04)); }
.tpl-tbody { display: flex; flex-direction: column; }
.tpl-tr-wrap { border-top: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.05)); }
.tpl-tr-wrap:first-child { border-top: none; }
.tpl-tr { transition: background 0.15s; }
.tpl-tr:hover { background: var(--cpq-overlay-w4, rgba(255,255,255,0.03)); }
.tpl-tr-wrap.expanded .tpl-tr { background: var(--cpq-overlay-a8, rgba(22,119,255,0.06)); }
.c-drag { display: flex; align-items: center; }
.c-idx, .c-slot-empty { font-size: 11px; color: var(--cpq-text-muted, #6E7582); text-align: center; }
.c-rule { min-width: 0; }
.c-op { text-align: right; }
.tpl-drag { cursor: grab; color: var(--cpq-text-muted, #6E7582); user-select: none; font-size: 14px; line-height: 1; }
.tpl-drag:active { cursor: grabbing; }

.rule-chip {
  display: block; width: 100%; text-align: left; cursor: pointer;
  font-size: 11px; line-height: 1.45; color: var(--cpq-text-secondary, #4E5560);
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.04));
  border: 1px solid transparent; border-radius: 6px; padding: 3px 8px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: all 0.15s;
}
.rule-chip:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.rule-chip.active { border-color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10, rgba(22,119,255,0.1)); color: var(--cpq-accent-primary, #1677FF); }

.tpl-rule { padding: 8px 10px 8px 16px; background: var(--cpq-overlay-w3, rgba(255,255,255,0.03)); border-top: 1px dashed var(--cpq-glass-border, rgba(255,255,255,0.07)); display: flex; flex-direction: column; gap: 5px; }
.rule-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rule-lab { font-size: 11px; color: var(--cpq-text-muted, #6E7582); width: 62px; flex-shrink: 0; }
.rule-lab.sub { padding-left: 10px; }

/* 实时预览 */
.editor-split { display: flex; gap: 12px; align-items: stretch; }
.editor-left { flex: 1; min-width: 0; }
.editor-right { width: 340px; flex-shrink: 0; display: flex; }
.preview-sec { flex: 1; display: flex; flex-direction: column; border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.08)); border-radius: 10px; overflow: hidden; }
.preview-head { padding: 8px 12px; font-size: 12px; font-weight: 600; color: var(--cpq-text-primary, #1F2329); background: var(--cpq-overlay-w6, rgba(255,255,255,0.04)); display: flex; align-items: baseline; gap: 8px; }
.preview-head em { font-weight: 400; font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.preview-body { padding: 8px 12px; overflow: auto; max-height: 600px; flex: 1; }
.pv-table-wrap { border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.08)); border-radius: 10px; overflow: hidden; }
.pv-table-head { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--cpq-overlay-w4, rgba(255,255,255,0.04)); border-bottom: 1px solid var(--cpq-overlay-w8, rgba(255,255,255,0.08)); }
.pv-title { font-size: 12px; font-weight: 600; color: var(--cpq-text-primary, #1F2329); }
.pv-sub { margin-left: auto; font-size: 10px; font-weight: 500; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10, rgba(22,119,255,0.1)); padding: 1px 6px; border-radius: 4px; }
.pv-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.pv-table thead { background: var(--cpq-overlay-w6, rgba(255,255,255,0.06)); position: sticky; top: 0; z-index: 1; }
.pv-table th { padding: 6px 10px; text-align: left; font-weight: 600; color: var(--cpq-text-secondary, #4E5560); border-bottom: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,0.1)); font-size: 10px; text-transform: uppercase; letter-spacing: 0.3px; }
.pv-table td { padding: 6px 10px; border-bottom: 1px solid var(--cpq-overlay-w5, rgba(255,255,255,0.05)); color: var(--cpq-text-primary, #1F2329); line-height: 1.3; }
.pv-table.no-cost .col-catalogue { width: 30%; font-weight: 500; }
.pv-table.no-cost .col-desc { width: 58%; }
.pv-table.no-cost .col-qty { width: 12%; text-align: center; }
.pv-table .cell-catalogue { font-weight: 500; color: var(--cpq-text-primary, #1F2329); word-break: break-word; }
.pv-table .cell-desc { color: var(--cpq-text-secondary, #4E5560); word-break: break-word; }
.pv-table .cell-qty { text-align: center; color: var(--cpq-text-muted, #6E7582); }
.pv-row:hover { background: var(--cpq-overlay-w4, rgba(255,255,255,0.04)); }

/* 抽屉 */
.bh { display: flex; flex-direction: column; gap: 12px; }
.bh-lead { font-size: 13px; line-height: 1.7; color: var(--cpq-text-secondary, #6E7582); margin: 0; }
</style>
