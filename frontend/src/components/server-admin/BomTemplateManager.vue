<script setup lang="ts">
/** BOM 模板管理（管理面独立卡片，挂在基准配置列表下方）— 列表 + 编辑弹窗。
 * 设计（2026-09-15 三轮定稿，09-19 可读行内 v3）：模板 rows = 骨架（type/label/slot/mode）+
 * 可选 rule（逐行完整覆盖类型默认——省略=跟随默认）。取值方式列**常显生效值为一句可读文字**
 * （零点击可见），点取值格展开该行编辑面板（同时只开一行）；任一格改动才物化整条 rule，
 * 物化后与类型默认深度相等 → 自动撤销回跟随（改回默认值=自动解除自定义）。
 * 求值引擎跑前端工作台 / 后端方案助手两套（同一口径）。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import axios from 'axios'
import { bomTemplateApi, partsApi, type BomTemplate, type BomTemplateRow, type BomRule } from '@/api/serverConfig'
import { evalBomContext, findBomPart, ruleForRow, VAR_ZH, defaultCableKinds, cableSegments } from '@/utils/bomRuleEngine'
import { loadBomCategoryAliases, getBomCategoryAliases, invalidateBomCategoryAliases } from '@/utils/bomCategoryAliases'
import { systemConfigApi } from '@/api/systemConfig'

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

/** 行类型 =「这行是什么」（部件身份）：决定默认算法（链路详情看「取值方式」列）；
 *  选项只写身份名，不写算法——算法语义统一归取值方式列，避免两列都在讲计算。
 *  分组（系统自动计算 / 需人工填写）提示哪类行零配置即合理。 */
interface RowTypeDef { value: string; label: string; short: string; group: 'auto' | 'manual' }
const ROW_TYPES: RowTypeDef[] = [
  { value: 'front_backplane', label: '前置背板', short: 'Front backplane', group: 'auto' },
  { value: 'io_slot', label: '后面板 IO 槽位', short: 'IO', group: 'auto' },
  { value: 'rear_summary', label: '后面板汇总行', short: 'Rear Summary', group: 'auto' },
  { value: 'heatsink', label: '散热器', short: 'Heatsink', group: 'auto' },
  { value: 'fan', label: '风扇', short: 'FAN', group: 'auto' },
  { value: 'psu_requirement', label: '电源需求', short: 'Power Supply Requirement', group: 'auto' },
  { value: 'gpu_power_cord', label: 'GPU 电源线', short: 'GPU Power cord', group: 'auto' },
  { value: 'power_cord', label: '电源线', short: 'Power cord', group: 'auto' },
  { value: 'rail_kit', label: '滑轨', short: 'Rail kit', group: 'auto' },
  { value: 'cable', label: '前面板线缆', short: 'Cable', group: 'auto' },
  { value: 'raid_slot', label: '手填行', short: 'Raid slot', group: 'manual' },
]
const autoTypes = ROW_TYPES.filter(t => t.group === 'auto')
const manualTypes = ROW_TYPES.filter(t => t.group === 'manual')
const SLOT_OPTIONS = ['IO1', 'IO2', 'IO3', 'IO4', 'OCP']

function addRow(type: string) {
  rows.value.push({ type, label: ROW_TYPES.find(t => t.value === type)!.short, uid: ++uidSeq })
}
function delRow(i: number) { rows.value.splice(i, 1) }
function onTypeChange(i: number) {
  const r = rows.value[i]
  if (r.type === 'io_slot') { if (!r.slot) r.slot = 'IO1' } else { delete r.slot }
  if (r.type === 'rear_summary') { if (!r.mode) r.mode = 'direct' } else { delete r.mode }
  // 换类型：丢弃旧自定义，直接跟随新类型默认（行内显示的就是生效值，无需物化）
  delete r.rule
  const def = ROW_TYPES.find(t => t.value === r.type)
  if (def && !r.label) r.label = def.short
}

// ---- 逐行规则编辑（能力=旧版完整规则；入口收进弹层，默认零配置走类型默认）----
type SrcSlot = 'desc' | 'desc_fallback' | 'qty' | 'qty_fallback'
const DESC_KINDS = [
  { value: 'part_field', label: '取料号字段' },
  { value: 'fixed', label: '固定文字' },
  { value: 'template', label: '变量拼接' },
  { value: 'struct_count', label: '结构汇总' },
  { value: 'config_value', label: '配置变量' },
  { value: 'manual', label: '手填留空' },
]
const QTY_KINDS = [
  { value: 'part_quantity', label: '取料件数量' },
  { value: 'fixed', label: '固定数量' },
  { value: 'config_calc', label: '跟配置算' },
  { value: 'manual', label: '手填留空' },
]
const SCOPES = [
  { value: 'io_slot', label: '该槽位实际插卡' },
  { value: 'rear_all', label: '汇总后面板' },
]
const VAR_KEYS = ['bays', 'form', 'bp_type_desc', 'psu_qty', 'psu_wattage', 'psu_name', 'gpu_qty',
  'gpu_cable_qty', 'gpu_power_cord_desc', 'nvme_count', 'raid_model', 'sata_count', 'sas_count', 'ocp_qty']
  .map(k => ({ value: k, label: VAR_ZH[k] || k }))
/** 模板「＋变量」点选菜单：中文标签 + 实际占位符写法 */
const VAR_MENU = VAR_KEYS.map(o => ({ value: o.value, label: `${o.label}　${'$'}{${o.value}}` }))
const CALC_KEYS = ['psu_qty', 'gpu_cable_qty', 'gpu_qty', 'ocp_qty'].map(k => ({ value: k, label: VAR_ZH[k] || k }))
const CABLE_KIND_KEYS = ['SATA', 'SAS', 'NVMe'] as const
/** cable 行的盘型分组配置（显示用；自定义老形状缺键时用默认补齐防渲染崩） */
function dispKinds(r: EditableRow): Record<string, { size: number; template: string }> {
  const d = srcAt(r, 'desc') as any
  return { ...defaultCableKinds(), ...(d.kinds || {}) }
}

// ---- 可读行内（v3）：生效值常显为一句文字（零点击可见），点取值格展开编辑面板 ----
/** 当前展开编辑的行（uid）；同时只开一行，保持表格安静 */
const editUid = ref<number | null>(null)
function toggleEdit(r: EditableRow) { editUid.value = editUid.value === r.uid ? null : r.uid }

/** 生效规则 → 一句可读文字（词汇与文档一致：料号字段[cat]·name / 跟[cat]件数 / 固定 …） */
function srcLabel(s: any): string {
  if (!s) return '？'
  switch (s.kind) {
    case 'part_field': return `料号字段[${s.category || '？'}]·${s.field || '？'}`
    case 'part_quantity': return `跟[${s.category || '？'}]件数`
    case 'fixed': return `固定 ${s.value ?? '？'}`
    case 'template': return `拼接 ${s.template || '？'} → ${tplExample(s.template || '')}`
    case 'struct_count': return s.scope === 'rear_all' ? '结构汇总·汇总后面板' : '结构汇总·该槽位插卡'
    case 'config_value': return `配置变量·${VAR_ZH[s.key] || s.key || '？'}`
    case 'config_calc': return `跟算·${VAR_ZH[s.key] || s.key || '？'}`
    case 'manual': return '手填'
    default: return s.kind || '？'
  }
}
/** 兜底后缀（无兜底 = 空串；前缀「兜底」由模板统一给一次） */
function fbText(r: EditableRow, p: 'desc_fallback' | 'qty_fallback'): string {
  const fb = srcAt(r, p)
  return fb ? srcLabel(fb) : ''
}
/** cable 行可读摘要 + 演示机型实算示例（直接跑引擎 cableSegments，与真实求值同口径） */
function cableText(r: EditableRow): string {
  const k = dispKinds(r)
  return CABLE_KIND_KEYS.map(x => `${x} 每${k[x].size}盘1组`).join(' · ')
}
function cableExample(r: EditableRow): string {
  const segs = cableSegments(dispKinds(r), demoVars).split('\n').filter(Boolean)
  return segs.join('、') || '（演示机型没盘 → 整行隐藏）'
}

// ---- 行内直编机制：显示读生效规则，改动才物化，改回默认自动撤销 ----
/** 读「生效规则」的某槽（desc/qty/兜底）：未自定义 = 类型默认（只读，不可直接改） */
function srcAt(r: EditableRow, p: SrcSlot): any { return (ruleForRow(r, demoVars.form) as any)[p] }
/** 改动入口：先物化整条 rule（从生效值拷贝）再返回可变引用 */
function touch(r: EditableRow): BomRule {
  if (!r.rule) r.rule = clone(ruleForRow(r, demoVars.form)) as BomRule
  return r.rule!
}
/** 物化后与类型默认深度相等 → 撤销物化回「跟随类型默认」（含改回默认值即解除自定义） */
function commit(r: EditableRow) {
  if (!r.rule) return
  const dflt = ruleForRow({ ...r, rule: undefined } as EditableRow, demoVars.form)
  if (JSON.stringify(r.rule) === JSON.stringify(dflt)) delete r.rule
}
/** 通用字段写入（template/value/category/field/scope/key…） */
function setSrc(r: EditableRow, p: SrcSlot, key: string, v: any) {
  ;(touch(r) as any)[p][key] = v
  commit(r)
}
/** cable 分组参数写入（老形状缺键先补默认再改） */
function setCable(r: EditableRow, k: string, field: 'size' | 'template', v: any) {
  const d = touch(r).desc as any
  d.kinds = { ...defaultCableKinds(), ...(d.kinds || {}) }
  d.kinds[k][field] = v
  commit(r)
}

/** 模板串实时示例：按演示机型 vars 渲染，缺变量显示 ？（编辑时立即看到拼出来什么样） */
function tplExample(tpl: string): string {
  return String(tpl || '').replace(/\$\{(\w+)\}/g, (_, k) => {
    const v = (demoVars as any)[k]
    return v == null || v === '' ? '？' : String(v)
  })
}
/** 点选中文变量 → 追加进模板串（不用记 ${} 拼写） */
function insertTplVar(r: EditableRow, key: string) {
  const d = touch(r).desc as any
  d.template = `${d.template || ''}\${${key}}`
  commit(r)
}
/** 换来源种类 → 重建该槽参数（带合理起步值） */
function blankSrc(kind: string, mode: 'desc' | 'qty'): any {
  switch (kind) {
    case 'part_field': return { kind, category: '', field: 'name' }
    case 'part_quantity': return { kind, category: '' }
    case 'fixed': return mode === 'desc' ? { kind, value: '' } : { kind, value: 1 }
    case 'template': return { kind, template: '' }
    case 'struct_count': return { kind, scope: 'io_slot' }
    case 'config_value': return { kind, key: '' }
    case 'config_calc': return { kind, key: '' }
    default: return { kind: 'manual' }
  }
}
function onKindChange(r: EditableRow, p: SrcSlot, v: string) {
  const mode = p.startsWith('qty') ? 'qty' : 'desc'
  ;(touch(r) as any)[p] = blankSrc(v, mode)
  commit(r)
}
/** 加兜底：从主源拷贝起步改（最常见的兜底=主源的简化版） */
function addFb(r: EditableRow, p: 'desc_fallback' | 'qty_fallback') {
  const rule: any = touch(r)
  const mode = p.startsWith('qty') ? 'qty' : 'desc'
  const main = rule[p.replace('_fallback', '')]
  rule[p] = main ? clone(main) : blankSrc('fixed', mode)
  commit(r)
}
function clearFb(r: EditableRow, p: 'desc_fallback' | 'qty_fallback') {
  delete (touch(r) as any)[p]
  commit(r)
}
function canFb(kind: string) { return kind !== 'manual' && kind !== 'fixed' }
/** 恢复类型默认 = 直接撤销自定义（行内显示回类型默认值） */
function resetRule(r: EditableRow) { delete r.rule }

// ---- 从现有模板复制（新建时可选）----
const copyFromId = ref<number | undefined>(undefined)
async function onCopyFrom(id: number) {
  if (!id) return
  try {
    const full = await bomTemplateApi.get(id)
    rows.value = (full.rows || []).map(r => ({ ...clone(r), uid: ++uidSeq }))
    message.success(`已带入「${full.name}」的 ${rows.value.length} 行骨架，可直接改名保存`)
  } catch { message.error('复制失败') }
}

// ---- 实时预览：机型上下文用演示 vars，零件名从料号库拉真件（拉不到退回演示值） ----
const demoVars: Record<string, any> = {
  bays: '24', form: '2U', series: 'R760', bp_type: 'tri', bp_type_desc: 'NVMe/SATA/SAS',
  psu_qty: 2, psu_wattage: '2000', psu_name: '2000W', gpu_qty: 2, gpu_cable_qty: 2,
  gpu_power_cord_desc: 'GPU power cable', nvme_count: 4,
  raid_model: '9361', sata_count: 8, sas_count: 0,
  standard_riser: 'X8 Riser', riser_x16: 'X16 Riser', high_bw_nic: false,
}
const DEMO_PARTS = [
  { category: 'heatsink', name: 'CPU 散热器', quantity: 2, specs: {} },
  { category: 'fan', name: '6056高性能热插拔风扇', quantity: 6, specs: {} },
  { category: 'rail', name: '标准滑轨', quantity: 1, specs: {} },
  { category: 'backplane', name: '24 盘位背板', quantity: 1, specs: { bt: 'tri' } },
  { category: 'psu', name: '2000W 电源', quantity: 2, specs: {} },
  { category: 'cable', name: '线缆包', quantity: 1, specs: {} },
]
const previewParts = ref<any[]>(DEMO_PARTS)
/** 预览零件名换成料号库真件：按分级匹配（category 优先于 name）每类取一件，
 *  让「自动取料号」行预览即真实（fan → 6056高性能热插拔风扇）。 */
async function loadPreviewParts() {
  try {
    const res = await partsApi.list({ page_size: 1000 })
    const real = (res.parts || []).map((p: any) => ({
      category: p.category, name: p.name, quantity: 0, specs: p.specs || {},
    }))
    previewParts.value = DEMO_PARTS.map(d => {
      const hit = findBomPart(real, d.category, getBomCategoryAliases())
      return hit && hit.name ? { ...d, name: hit.name, specs: hit.specs } : d
    })
  } catch { /* 料号库拉不到时保留演示值 */ }
}
const preview = computed(() => {
  const ctx = {
    vars: demoVars,
    parts: previewParts.value,
    rear: {},
    categoryAliases: getBomCategoryAliases(),
  }
  const evaled = evalBomContext(rows.value, ctx)
  return rows.value.map((r, i) => {
    const key = r.slot || r.type
    const v = evaled[key] || { desc: '', qty: '', descSrc: 'empty', qtySrc: 'empty' }
    // 与 BomTable 空行隐藏一致：desc 与 qty 都空 → 整行不显示（算不出同理）
    const descEmpty = !v.desc
    const qtyEmpty = v.qty === '' || v.qty == null || v.qty === 0
    const hidden = descEmpty && qtyEmpty
    // 取值来源（所见即所算）：取两字段最差状态 —— 命中不出胶囊（全是计算无信息量），兜底/留空才是异常信号
    const worst = (a: string, b: string) =>
      (a === 'empty' || b === 'empty') ? 'empty' : (a === 'fb' || b === 'fb') ? 'fb' : 'hit'
    const s = worst(v.descSrc, v.qtySrc)
    return {
      key: `${i}-${key}`,
      label: r.label || key,
      desc: v.desc || '',
      qty: String(v.qty ?? ''),
      src: s,
      srcText: s === 'fb' ? '兜底' : s === 'empty' ? '留空' : '',
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
      axios.get(`/api/bom-templates/${t.id}/usage`).then(r => r.data).catch(() => ({ count: 0 })))
    )
    templates.value = list.map((t, i) => ({ ...t, _usage: usages[i]?.count || 0 }))
  } finally { loading.value = false }
}
function openNew() {
  editingId.value = null; name.value = ''; rows.value = []; copyFromId.value = undefined; editUid.value = null
  modalVisible.value = true
}
async function openEdit(t: BomTemplate) {
  editingId.value = t.id
  const full = await bomTemplateApi.get(t.id)
  name.value = full.name
  rows.value = (full.rows || []).map(r => ({ ...clone(r), uid: ++uidSeq }))
  editUid.value = null
  modalVisible.value = true
}
async function save() {
  if (!name.value.trim()) return message.warning('请填模板名')
  for (const r of rows.value) {
    if (r.type === 'io_slot' && !r.slot) return message.warning('IO 槽位行需选 slot（IO1~IO4/OCP）')
  }
  saving.value = true
  try {
    const payload = {
      name: name.value.trim(),
      // 存骨架 + 行上自定义规则（rule 可选：省略=类型默认）；剥运行态 uid 与废弃的 ov 键
      rows: rows.value.map(({ uid: _uid, ov: _ov, ...rest }: any) => rest),
    }
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
  await loadPreviewParts()
})
defineExpose({ load })
</script>

<template>
  <div class="panel glass">
    <div class="lib-head">
      <h3>BOM 模板</h3>
      <span class="lib-actions">
        <a-button size="small" @click="openAliasModal()">⚙️ 品别名</a-button>
        <a-button type="primary" size="small" @click="openNew">+ 新建模板</a-button>
      </span>
    </div>
    <div class="tpl-hint">左栏 L6 配置单的机型族行骨架。标签=行名，类型=行的算法身份；取值方式列常显每行生效值（未自定义=类型默认），点击取值文字展开编辑——改动即自定义，改回默认自动撤销。料件挂基准配置底盘件、riser 在 config_content，基准配置下拉关联模板。</div>
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

    <a-modal :open="modalVisible" :title="editingId ? '编辑 BOM 模板' : '新建 BOM 模板'" width="1180px"
             :okText="saving ? '保存中…' : '保存'" @ok="save" @cancel="modalVisible = false" :destroyOnClose="true">
      <a-form layout="vertical">
        <a-form-item label="模板名" required>
          <a-input v-model:value="name" placeholder="如：2U12标准、4U8-GPU直连" />
        </a-form-item>
        <a-form-item v-if="!editingId" label="从现有模板复制（可选）">
          <a-select v-model:value="copyFromId" placeholder="选择模板，整份带入行骨架，改名即可用" allow-clear
            @change="(v: number) => v && onCopyFrom(v)">
            <a-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}（{{ t.rows?.length || 0 }} 行）</a-select-option>
          </a-select>
        </a-form-item>

        <div class="editor-split">
          <div class="editor-left">
            <div class="sec-label">行骨架（顺序即左栏显示顺序）</div>
            <div class="tpl-table">
          <div class="tpl-thead">
            <span class="c-drag"></span>
            <span class="c-idx">#</span>
            <span class="c-label">左栏标签</span>
            <span class="c-type">类型</span>
            <span class="c-rule-h">取值方式<em class="th-hint">生效值常显 · 点行内文字编辑</em></span>
            <span class="c-op">操作</span>
          </div>
          <draggable v-model="rows" item-key="uid" handle=".tpl-drag" :animation="180" class="tpl-tbody">
            <template #item="{ element: r, index: i }">
              <div class="tpl-tr" :class="{ 'is-custom': !!r.rule, 'is-open': editUid === r.uid }">
                <div class="tr-line">
                  <span class="c-drag"><span class="tpl-drag" title="拖拽排序">⠿</span></span>
                  <span class="c-idx row-idx">{{ i + 1 }}</span>
                  <span class="c-label"><a-input v-model:value="r.label" size="small" placeholder="左栏标签" /></span>
                  <span class="c-type">
                    <a-select size="small" style="width:100%" :value="r.type" title="换类型将重置取值为新类型默认" @change="(v: any) => { r.type = v; onTypeChange(i) }">
                      <a-select-opt-group label="系统自动计算">
                        <a-select-option v-for="t in autoTypes" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                      </a-select-opt-group>
                      <a-select-opt-group label="需人工填写">
                        <a-select-option v-for="t in manualTypes" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                      </a-select-opt-group>
                    </a-select>
                    <a-select v-if="r.type === 'io_slot'" v-model:value="r.slot" size="small" class="type-sub-sel">
                      <a-select-option v-for="s in SLOT_OPTIONS" :key="s" :value="s">{{ s }}</a-select-option>
                    </a-select>
                    <a-select v-else-if="r.type === 'rear_summary'" v-model:value="r.mode" size="small" class="type-sub-sel">
                      <a-select-option value="direct">direct</a-select-option>
                      <a-select-option value="switch">switch</a-select-option>
                    </a-select>
                  </span>
                  <!-- 取值方式：生效值常显为一句可读文字（零点击可见）；点这格展开下方编辑 -->
                  <span class="c-rule" title="点击展开编辑取值方式" @click="toggleEdit(r)">
                    <template v-if="r.type === 'cable'">
                      <span class="rule-main">{{ cableText(r) }}</span>
                      <span class="rule-sub">恒 1 组｜{{ cableExample(r) }}</span>
                    </template>
                    <template v-else>
                      <span class="rule-main">{{ srcLabel(srcAt(r, 'desc')) }}</span>
                      <span class="rule-sep">｜数量</span>
                      <span class="rule-qty">{{ srcLabel(srcAt(r, 'qty')) }}</span>
                      <span v-if="fbText(r, 'desc_fallback') || fbText(r, 'qty_fallback')" class="rule-sub">｜兜底 {{ [fbText(r, 'desc_fallback'), fbText(r, 'qty_fallback')].filter(Boolean).join(' / ') }}</span>
                    </template>
                    <span class="rule-pen" :class="{ on: editUid === r.uid }">✎</span>
                  </span>
                  <span class="c-op">
                    <a-button v-if="r.rule" size="small" link class="op-reset" title="恢复类型默认" @click="resetRule(r)">↺</a-button>
                    <a-button size="small" link danger @click="delRow(i)">删</a-button>
                  </span>
                </div>
                <!-- 展开编辑：描述/数量并排两栏（cable=盘型分组三件套通栏）；机制不变（改动才物化） -->
                <div v-if="editUid === r.uid" class="tr-edit">
                  <template v-if="r.type === 'cable'">
                    <div class="edit-cell ec-cable">
                      <div class="ec-head">盘型分组（描述按盘型分段写组数，数量恒 1）</div>
                      <div class="cable-line" v-for="k in CABLE_KIND_KEYS" :key="k">
                        <span class="cable-k">{{ k }}</span>
                        <span class="cable-per">每</span>
                        <a-input-number size="small" style="width:52px" :min="1" :value="dispKinds(r)[k].size" @update:value="(v: any) => setCable(r, k, 'size', v)" />
                        <span class="cable-per">盘 1 组</span>
                        <a-input size="small" class="cable-tpl" :value="dispKinds(r)[k].template" @update:value="(v: any) => setCable(r, k, 'template', v)" placeholder="如 ${raid_model} SATA cable*${n}" />
                      </div>
                      <div class="tpl-example">示例：{{ cableExample(r) }}（演示机型实时算）｜占位符：${raid_model}＝RAID 型号（没配 RAID 自动去前缀）、${n}＝组数、${count}＝盘数；没配该类盘自动不出现</div>
                    </div>
                  </template>
                  <template v-else>
                    <div class="edit-cell ec-desc">
                      <div class="ec-head">描述</div>
                      <div class="src-line">
                        <a-select size="small" class="src-kind" :value="srcAt(r, 'desc').kind" :options="DESC_KINDS" @change="(v: string) => onKindChange(r, 'desc', v)" />
                        <a-input v-if="srcAt(r, 'desc').kind === 'part_field'" size="small" style="width:72px" placeholder="品类" :value="srcAt(r, 'desc').category" @update:value="(v: any) => setSrc(r, 'desc', 'category', v)" />
                        <a-input v-if="srcAt(r, 'desc').kind === 'part_field'" size="small" style="width:56px" placeholder="字段" :value="srcAt(r, 'desc').field" @update:value="(v: any) => setSrc(r, 'desc', 'field', v)" />
                        <a-input v-if="srcAt(r, 'desc').kind === 'fixed'" size="small" class="src-in" placeholder="固定文案" :value="srcAt(r, 'desc').value" @update:value="(v: any) => setSrc(r, 'desc', 'value', v)" />
                        <template v-if="srcAt(r, 'desc').kind === 'template'">
                          <a-input size="small" class="src-in" placeholder="如 ${bays}*3.5 ${bp_type_desc}" :value="srcAt(r, 'desc').template" @update:value="(v: any) => setSrc(r, 'desc', 'template', v)" />
                          <a-dropdown :trigger="['click']">
                            <a-button size="small" title="点选插入变量占位符">＋变量</a-button>
                            <template #overlay>
                              <a-menu @click="({ key }: any) => insertTplVar(r, String(key))">
                                <a-menu-item v-for="o in VAR_MENU" :key="o.value">{{ o.label }}</a-menu-item>
                              </a-menu>
                            </template>
                          </a-dropdown>
                        </template>
                        <a-select v-if="srcAt(r, 'desc').kind === 'struct_count'" size="small" style="width:104px" :value="srcAt(r, 'desc').scope" :options="SCOPES" @change="(v: any) => setSrc(r, 'desc', 'scope', v)" />
                        <a-select v-if="srcAt(r, 'desc').kind === 'config_value'" size="small" style="width:104px" placeholder="变量" :value="srcAt(r, 'desc').key" :options="VAR_KEYS" @change="(v: any) => setSrc(r, 'desc', 'key', v)" />
                      </div>
                      <div v-if="srcAt(r, 'desc').kind === 'template'" class="tpl-example">示例：{{ tplExample(srcAt(r, 'desc').template || '') }}（随输入实时变，？＝真实场景留空手填<template v-if="(srcAt(r, 'desc').template || '').includes('${bp_type_desc}')">；背板类型跟盘走：配了 NVMe 盘 → NVMe/SATA/SAS（三模），否则 SATA/SAS</template>）</div>
                      <div v-if="canFb(srcAt(r, 'desc').kind)" class="src-line sub">
                        <span class="fb-lab">兜底</span>
                        <template v-if="srcAt(r, 'desc_fallback')">
                          <a-select size="small" class="src-kind" :value="srcAt(r, 'desc_fallback').kind" :options="DESC_KINDS" @change="(v: string) => onKindChange(r, 'desc_fallback', v)" />
                          <a-input v-if="srcAt(r, 'desc_fallback').kind === 'part_field'" size="small" style="width:72px" placeholder="品类" :value="srcAt(r, 'desc_fallback').category" @update:value="(v: any) => setSrc(r, 'desc_fallback', 'category', v)" />
                          <a-input v-if="srcAt(r, 'desc_fallback').kind === 'fixed'" size="small" class="fb-in" placeholder="兜底文案" :value="srcAt(r, 'desc_fallback').value" @update:value="(v: any) => setSrc(r, 'desc_fallback', 'value', v)" />
                          <a-input v-if="srcAt(r, 'desc_fallback').kind === 'template'" size="small" class="fb-in" placeholder="模板串" :value="srcAt(r, 'desc_fallback').template" @update:value="(v: any) => setSrc(r, 'desc_fallback', 'template', v)" />
                          <a-select v-if="srcAt(r, 'desc_fallback').kind === 'struct_count'" size="small" style="width:104px" :value="srcAt(r, 'desc_fallback').scope" :options="SCOPES" @change="(v: any) => setSrc(r, 'desc_fallback', 'scope', v)" />
                          <a-select v-if="srcAt(r, 'desc_fallback').kind === 'config_value'" size="small" style="width:104px" placeholder="变量" :value="srcAt(r, 'desc_fallback').key" :options="VAR_KEYS" @change="(v: any) => setSrc(r, 'desc_fallback', 'key', v)" />
                          <button class="fb-x" title="删掉兜底" @click="clearFb(r, 'desc_fallback')">✕</button>
                        </template>
                        <button v-else class="fb-add" @click="addFb(r, 'desc_fallback')">＋算不出时</button>
                      </div>
                    </div>
                    <div class="edit-cell ec-qty">
                      <div class="ec-head">数量</div>
                      <div class="src-line">
                        <a-select size="small" class="src-kind" :value="srcAt(r, 'qty').kind" :options="QTY_KINDS" @change="(v: string) => onKindChange(r, 'qty', v)" />
                        <a-input v-if="srcAt(r, 'qty').kind === 'part_quantity'" size="small" style="width:72px" placeholder="品类" :value="srcAt(r, 'qty').category" @update:value="(v: any) => setSrc(r, 'qty', 'category', v)" />
                        <a-input-number v-if="srcAt(r, 'qty').kind === 'fixed'" size="small" style="width:70px" :min="0" :value="srcAt(r, 'qty').value" @update:value="(v: any) => setSrc(r, 'qty', 'value', v)" />
                        <a-select v-if="srcAt(r, 'qty').kind === 'config_calc'" size="small" style="width:104px" placeholder="变量" :value="srcAt(r, 'qty').key" :options="CALC_KEYS" @change="(v: any) => setSrc(r, 'qty', 'key', v)" />
                      </div>
                      <div v-if="canFb(srcAt(r, 'qty').kind)" class="src-line sub">
                        <span class="fb-lab">兜底</span>
                        <template v-if="srcAt(r, 'qty_fallback')">
                          <a-select size="small" class="src-kind" :value="srcAt(r, 'qty_fallback').kind" :options="QTY_KINDS" @change="(v: string) => onKindChange(r, 'qty_fallback', v)" />
                          <a-input v-if="srcAt(r, 'qty_fallback').kind === 'part_quantity'" size="small" style="width:72px" placeholder="品类" :value="srcAt(r, 'qty_fallback').category" @update:value="(v: any) => setSrc(r, 'qty_fallback', 'category', v)" />
                          <a-input-number v-if="srcAt(r, 'qty_fallback').kind === 'fixed'" size="small" style="width:70px" :min="0" :value="srcAt(r, 'qty_fallback').value" @update:value="(v: any) => setSrc(r, 'qty_fallback', 'value', v)" />
                          <a-select v-if="srcAt(r, 'qty_fallback').kind === 'config_calc'" size="small" style="width:104px" placeholder="变量" :value="srcAt(r, 'qty_fallback').key" :options="CALC_KEYS" @change="(v: any) => setSrc(r, 'qty_fallback', 'key', v)" />
                          <button class="fb-x" title="删掉兜底" @click="clearFb(r, 'qty_fallback')">✕</button>
                        </template>
                        <button v-else class="fb-add" @click="addFb(r, 'qty_fallback')">＋算不出时</button>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </template>
            </draggable>
            <div class="tpl-tail">
              <a-select size="small" placeholder="＋ 选类型添加行" :value="undefined" style="width:220px" @change="(v: any) => addRow(String(v))">
                <a-select-opt-group label="系统自动计算">
                  <a-select-option v-for="t in autoTypes" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                </a-select-opt-group>
                <a-select-opt-group label="需人工填写">
                  <a-select-option v-for="t in manualTypes" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                </a-select-opt-group>
              </a-select>
            </div>
            </div>
          </div>
          <div class="editor-right">
            <div class="preview-sec">
          <div class="preview-head">实时预览 <em>零件名取料号库真件 · 机型上下文为演示值（2U/24盘位），真实值以工作台 / 方案助手为准</em></div>
          <div class="preview-body">
            <div v-if="previewVisible.length" class="pv-table-wrap">
              <div class="pv-table-head">
                <span class="pv-title">L6 配置单</span>
                <span class="pv-sub">预览 · 真件名 + 演示机型</span>
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
                    <td class="cell-desc">{{ p.desc || '[空]' }}<span v-if="p.src !== 'hit'" class="pv-src" :class="`src-${p.src}`" :title="p.src === 'fb' ? '主规则没算出来，走了兜底' : '有留空字段，报价时手填'">{{ p.srcText }}</span></td>
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

/* 行骨架表格：单行可读（生效值=一句文字）+ 点行展开编辑面板 */
.tpl-table { border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.08)); border-radius: 10px; overflow: hidden; }
.tpl-thead, .tr-line {
  display: grid;
  grid-template-columns: 22px 26px minmax(110px, 1fr) 132px minmax(0, 2.4fr) 56px;
  gap: 6px; align-items: center; padding: 6px 10px;
}
.tpl-thead { font-size: 11px; font-weight: 600; color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w6, rgba(255,255,255,0.04)); }
.th-hint { margin-left: 6px; font-weight: 400; font-size: 10px; color: var(--cpq-text-muted, #6E7582); opacity: 0.85; }
.tpl-tbody { display: flex; flex-direction: column; }
.tpl-tr { display: flex; flex-direction: column; transition: background 0.15s; border-top: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.05)); }
.tpl-tr:first-child { border-top: none; }
.tpl-tr:hover { background: var(--cpq-overlay-w4, rgba(255,255,255,0.03)); }
.tpl-tr.is-custom { box-shadow: inset 2px 0 0 var(--cpq-accent-primary, #1677FF); }
.tpl-tr.is-open { background: var(--cpq-overlay-w4, rgba(255,255,255,0.03)); }
.c-drag { display: flex; align-items: center; }
.c-idx { font-size: 11px; color: var(--cpq-text-muted, #6E7582); text-align: center; }
.c-type, .c-label, .c-rule { min-width: 0; }
.c-op { text-align: right; white-space: nowrap; }
.op-reset { color: var(--cpq-accent-primary, #1677FF); padding: 0 2px; }
.type-sub-sel { width: 100%; margin-top: 4px; }
.tpl-drag { cursor: grab; color: var(--cpq-text-muted, #6E7582); user-select: none; font-size: 14px; line-height: 1; }
.tpl-drag:active { cursor: grabbing; }

/* 取值方式可读格：主值+数量+兜底后缀一句排开，悬停显笔尖 */
.c-rule { display: flex; align-items: baseline; gap: 4px; cursor: pointer; overflow: hidden; font-size: 12px; line-height: 1.4; }
.rule-main { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--cpq-text-primary, #1F2329); font-weight: 500; }
.rule-sep { flex-shrink: 0; font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.rule-qty { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--cpq-text-secondary, #4E5560); }
.rule-sub { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 10px; color: var(--cpq-text-muted, #6E7582); }
.rule-pen { margin-left: auto; flex-shrink: 0; font-size: 11px; color: var(--cpq-text-muted, #6E7582); opacity: 0.45; }
.tpl-tr:hover .rule-pen, .rule-pen.on { opacity: 1; }
.rule-pen.on { color: var(--cpq-accent-primary, #1677FF); }

/* 展开编辑面板：描述/数量并排（cable 通栏），控件同旧版 */
.tr-edit { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); gap: 8px 18px; padding: 10px 10px 10px 54px; border-top: 1px dashed var(--cpq-glass-border, rgba(140,150,165,0.25)); background: var(--cpq-overlay-w4, rgba(255,255,255,0.03)); }
.edit-cell { min-width: 0; }
.ec-head { margin-bottom: 5px; font-size: 10px; font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase; color: var(--cpq-text-muted, #6E7582); }
.ec-cable { grid-column: 1 / -1; }

/* 取值编辑控件：来源+参数一行；兜底次行小字 */
.src-line { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; min-width: 0; }
.src-line.sub { margin-top: 3px; }
.src-kind { width: 88px; flex-shrink: 0; }
.src-in { flex: 1; min-width: 90px; }
.fb-lab { font-size: 10px; color: var(--cpq-text-muted, #6E7582); flex-shrink: 0; }
.fb-in { flex: 1; min-width: 80px; }
.fb-add { border: none; background: none; cursor: pointer; padding: 0; font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.fb-add:hover { color: var(--cpq-accent-primary, #1677FF); }
.fb-x { border: none; background: none; cursor: pointer; padding: 0 2px; font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.fb-x:hover { color: #ff4d4f; }
.tpl-example { margin-top: 2px; font-size: 10px; line-height: 1.5; color: var(--cpq-text-muted, #6E7582); }
.cable-line { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-bottom: 3px; min-width: 0; }
.cable-k { width: 32px; font-size: 10px; font-weight: 600; color: var(--cpq-text-secondary, #4E5560); flex-shrink: 0; }
.cable-per { font-size: 11px; color: var(--cpq-text-secondary, #4E5560); flex-shrink: 0; }
.cable-tpl { flex: 1; min-width: 110px; }
.tpl-tail { display: flex; align-items: center; padding: 8px 10px; border-top: 1px dashed var(--cpq-glass-border, rgba(140,150,165,0.35)); }

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
.pv-src { float: right; margin-left: 8px; font-size: 10px; font-weight: 500; padding: 0 5px; border-radius: 4px; flex-shrink: 0; }
.pv-src.src-hit { color: #1677FF; background: rgba(22,119,255,0.1); }
.pv-src.src-fb { color: #D46B08; background: rgba(210,137,29,0.12); }
.pv-src.src-empty { color: #8C8C8C; background: rgba(140,140,140,0.12); }

/* 抽屉 */
.bh { display: flex; flex-direction: column; gap: 12px; }
.bh-lead { font-size: 13px; line-height: 1.7; color: var(--cpq-text-secondary, #6E7582); margin: 0; }
</style>
