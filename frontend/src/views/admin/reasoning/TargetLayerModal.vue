<script setup lang="ts">
/** 目标层弹窗 v5：左字段契约 · 右真实预览（TargetTwoPane 公共双栏）。
 * 目标层 = 节点输出给下游的字段契约 + 该契约的可视化实例：
 *  - form（agent_fill）：左 = 登记策略（字段只读 · AI 反问开关 · 候选来源 + KP 大类），右 = 需求登记表预览
 *    （RequirementForm 商机详情页同款组件，schema 同源）。字段/中文名/顺序权威 = requirement_sheet_form。
 *  - table（机型选配等）：左 = 输出字段契约（存节点配置 target.artifacts[].fields，经 save-target 持久化），
 *    右 = 该节点输出物实时预览（机箱下拉 → L6 配置表真实求值）。
 * 统一大脑：每个节点的执行者都是 AI 角色（节点 prompt 驱动），「必填」是所有节点字段的策略位。 */
import { computed, nextTick, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import TargetTwoPane from './TargetTwoPane.vue'
import type { TargetFieldRow } from './TargetTwoPane.vue'
import RequirementForm from '@/components/flow/RequirementForm.vue'

const props = defineProps<{
  open: boolean
  artifact: { name: string; kind: string; schema_ref: string; view?: string; note?: string; rows_from?: string; fields?: TargetFieldRow[] } | null
  nodeKey?: string | null
  skillKey?: string | null
}>()
const emit = defineEmits<{ 'update:open': [boolean]; 'save-target': [any[]] }>()

interface FieldRow { key: string; label: string; control: string; level: string; candidate_source: string }
interface KpRow { name: string; required: boolean }
const KIND_LABELS: Record<string, string> = { form: '表单', document: '文档', media: '媒体', table: '表格', sheet_section: '配置表切片' }
const targetArtifacts = computed(() => props.artifact ? [props.artifact] : [])
const loading = ref(false)
const saving = ref(false)
const fieldRows = ref<FieldRow[]>([])
const kpRows = ref<KpRow[]>([])
const askThreshold = ref(2)

// 右栏登记表预览：readonly 组件不自播配置，用已加载的 KP 大类显式播种一行空配置
const formPreviewRef = ref<InstanceType<typeof RequirementForm> | null>(null)
async function seedFormPreview() {
  await nextTick()
  formPreviewRef.value?.fromSlots({
    kp_rows: kpRows.value.map(r => ({ part_category: r.name })),
  } as any)
}

const SRC_OPTIONS = [
  { value: 'catalog', label: '目录白名单' },
  { value: 'free', label: '自由输入' },
]
const CONTROL_HINTS: Record<string, string> = {
  model_select: '机型选择 · 自动带出平台/类型/形态',
  series_select: '平台系列候选',
  type_select: '在售类型候选',
  form_select: '形态候选',
  number: '整数输入',
}

/** 登记策略字段 + KP 大类 → 统一字段行（必填=L0 ⇔ AI 反问；大类必填 ⇔ 登记时追问） */
const fillFields = computed<TargetFieldRow[]>(() => [
  ...fieldRows.value.map(r => ({
    key: r.key,
    label: r.label,
    group: '配置字段 · 商机详情页表单定义（只读）',
    hint: CONTROL_HINTS[r.control] || '文本输入',
    ask: r.level === 'L0',
    source: { value: r.candidate_source, options: SRC_OPTIONS },
  })),
  ...kpRows.value.map(r => ({
    key: `kp:${r.name}`,
    label: r.name,
    group: '部件清单 · KP 大类',
    hint: '按客户原话逐行登记',
    ask: r.required,
  })),
])

function onFillAskChange(key: string, val: boolean) {
  if (key.startsWith('kp:')) {
    const row = kpRows.value.find(r => `kp:${r.name}` === key)
    if (row) row.required = val
    return
  }
  const row = fieldRows.value.find(r => r.key === key)
  if (row) row.level = val ? 'L0' : 'L1'
}

function onFillSourceChange(key: string, val: string) {
  const row = fieldRows.value.find(r => r.key === key)
  if (row) row.candidate_source = val
}

async function load() {
  loading.value = true
  try {
    const [defRes, polRes, kpRes] = await Promise.all([
      axios.get('/api/system-config/requirement_sheet_form/value'),
      axios.get('/api/system-config/requirement_slots/value'),
      axios.get('/api/kp/categories'),
    ])
    const defFields = (defRes.data?.value?.config_fields || []).filter((f: any) => f?.key)
    const pol = polRes.data?.value || {}
    const polByKey = new Map<string, any>()
    for (const s of (Array.isArray(pol.slots) ? pol.slots : [])) if (s?.key) polByKey.set(String(s.key), s)
    const defaultSrc = (key: string) => (['server_type', 'platform_type', 'chassis_form', 'server_model'].includes(key) ? 'catalog' : 'free')
    fieldRows.value = defFields.map((f: any) => {
      const p = polByKey.get(String(f.key))
      return {
        key: String(f.key),
        label: String(f.label || f.key),
        control: String(f.control || 'text'),
        level: p?.level === 'L0' ? 'L0' : 'L1',
        candidate_source: p?.candidate_source || defaultSrc(String(f.key)),
      }
    })
    const kpRequired = new Set((pol.kp_required || []).map((c: any) => String(c)))
    kpRows.value = (kpRes.data || [])
      .map((c: any) => String(c.name || c))
      .filter(Boolean)
      .map((name: string) => ({ name, required: kpRequired.has(name) }))
    askThreshold.value = pol.ask_threshold ?? 2
  } catch (e) {
    console.error('加载目标层定义/策略失败:', e)
    message.error('读取表单定义或登记策略失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const slots = fieldRows.value.map(r => ({ key: r.key, label: r.label, level: r.level, candidate_source: r.candidate_source }))
    const kp_required = kpRows.value.filter(r => r.required).map(r => r.name)
    await axios.put('/api/system-config/requirement_slots', {
      value: { version: 1, ask_threshold: Number(askThreshold.value) || 2, slots, kp_required },
      type: 'json',
    })
    message.success('已保存（下次推理生效）')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// ── table 分支：字段契约（本节点要填什么）+ 真实预览（按 view 分流）────────────
// 2026-09-06 定调（对齐 agent_fill/机箱选配）：三个节点左栏一律 TargetTwoPane 同一套，
// 放「本节点要填入的业务字段 + AI 反问策略位」；表格列形状（Catalogue/…）归 plan_config
// 共享 schema，只读展示、不随节点编辑。
// kp_reason 的字段 = 配件行（CPU/GPU/内存…，来自 KP 库真实类目）——
// ask=true → 该类行 AI 不代选（引擎/工具硬消费：拒绝代选提交、交客户决策）。
const tableFieldRows = ref<TargetFieldRow[]>([])
const tableSaving = ref(false)

const artifactView = computed(() => String((props.artifact as any)?.view || ''))
const isKpView = computed(() => artifactView.value === 'plan_kp')

// 服务器配置默认必须反问类目（目标层未配置时回退；可在本弹窗逐类改）
const DEFAULT_MUST_ASK = ['CPU', 'Memory', 'HDD/SSD', 'Raid card', 'NIC', 'GPU']

// 表格式（plan_config 共享，只读）：执行器产物列与预览列都消费这一份
const sharedColumns = computed<any[]>(() =>
  (((props.artifact as any)?.columns || []) as any[]).filter((c: any) => c.visible !== false))
const sharedColumnLabels = computed(() =>
  sharedColumns.value.map((c: any) => String(c.label || c.key)).join(' / '))

// 预览行整形（与后端 skill_target_contract._cell 同语义的 JS 镜像）
function dig(row: any, path: string): any {
  let cur = row
  for (const seg of String(path || '').split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = cur[seg]
  }
  return cur
}
function cellOf(row: any, col: any) {
  const nonEmpty = (x: any) => x !== undefined && x !== null && String(x).trim() !== ''
  let v = dig(row, col.from || col.key)
  if (nonEmpty(v)) return v
  for (const fb of String(col.fallback || '').split('|')) {
    const f = fb.trim()
    if (!f) continue
    if (/^\d+$/.test(f)) return Number(f)
    v = dig(row, f)
    if (nonEmpty(v)) return v
  }
  return ''
}

// KP 样例行（KP 库真实料号，标注非运行数据）
const kpPreviewRows = ref<any[]>([])
const kpPreviewSource = ref('')
const kpPreviewLoading = ref(false)
async function loadKpPreview() {
  kpPreviewLoading.value = true
  try {
    const { data } = await axios.get('/api/reasoning-flow/kp-preview')
    kpPreviewRows.value = Array.isArray(data?.rows) ? data.rows : []
    kpPreviewSource.value = String(data?.source || '')
  } catch (e) {
    console.error('KP 预览加载失败:', e)
    kpPreviewRows.value = []
  } finally {
    kpPreviewLoading.value = false
  }
}
const kpShapedRows = computed(() => kpPreviewRows.value.map((r: any) => {
  const out: any = {}
  for (const c of sharedColumns.value) out[String(c.key)] = cellOf(r, c)
  out.spec_mismatch = !!r.spec_mismatch
  return out
}))
const previewColumns = computed(() => sharedColumns.value.map((c: any) => ({
  title: String(c.label || c.key),
  dataIndex: String(c.key),
  key: String(c.key),
})))
const previewDataRows = computed(() => (isKpView.value ? kpShapedRows.value : previewRows.value))

function onFieldAskChange(key: string, val: boolean) {
  const row = tableFieldRows.value.find(f => f.key === key)
  if (row) row.ask = val
}

async function seedFieldRows() {
  const existing = ((props.artifact as any)?.fields || []) as TargetFieldRow[]
  if (existing.length) {
    tableFieldRows.value = existing.map(f => ({ ...f }))
    return
  }
  if (isKpView.value) {
    // kp_reason 字段 = 配件行（KP 库真实类目，每类一行；ask=该类是否交客户决策）
    try {
      const { data } = await axios.get('/api/kp/categories')
      const cats = (Array.isArray(data) ? data : []).map((c: any) => String(c.name || c)).filter(Boolean)
      tableFieldRows.value = cats.map(name => ({
        key: `kp_parts:${name}`,
        label: name,
        hint: '配件行 · 必填=该行必须落在最终方案；客户已明确登记具体型号且库内有精确料→AI 直接锁定；已登记但库无精确料/仅类目名（模糊）→AI 推荐并调 ask_user 确认（含自选/数量）；关=非必填，AI 可选配',
        group: '部件行 · 本节点要填的配件',
        ask: DEFAULT_MUST_ASK.includes(name),
      }))
    } catch {
      tableFieldRows.value = []
    }
    return
  }
  // model_reason 字段 = 服务器型号（本节点唯一要填的业务字段）
  tableFieldRows.value = [{
    key: 'server_model',
    label: '服务器型号',
    hint: '在售目录候选 · 按系列/类型过滤后锁定',
    group: '机型选配 · 本节点要填的字段',
    ask: false,
  }]
}

function saveFields() {
  if (!props.nodeKey) { message.info('未挂接节点，仅预览'); return }
  tableSaving.value = true
  try {
    emit('save-target', [{ ...(props.artifact || {}), fields: tableFieldRows.value.map(f => ({ ...f })) }])
  } finally {
    tableSaving.value = false
  }
}

// 输出物预览（真实求值链路）：机箱下拉 → 该机型 BOM 模板求值的基础机箱 L6 配置行
const machines = ref<string[]>([])
const selectedModel = ref('')
const previewRows = ref<any[]>([])
const previewSource = ref('')
const previewLoading = ref(false)

async function loadMachines() {
  try {
    const { catalogApi } = await import('@/api/serverConfig')
    const res = await catalogApi.listModels()
    machines.value = (res.models || []).map((m: any) => String(m.name || '')).filter(Boolean)
  } catch {
    machines.value = []
  }
}

async function loadPreview(model: string) {
  if (!model) return
  previewLoading.value = true
  try {
    const { data } = await axios.get('/api/reasoning-flow/l6-preview', { params: { model } })
    previewRows.value = Array.isArray(data?.rows) ? data.rows : []
    previewSource.value = String(data?.source || '')
  } catch (e) {
    console.error('L6 预览失败:', e)
    previewRows.value = []
    previewSource.value = ''
  } finally {
    previewLoading.value = false
  }
}

function onSelectModel(name: string) {
  selectedModel.value = name
  loadPreview(name)
}

// ── document 分支：报告结构契约（章节可增删排序），大脑按此逐节产出 markdown ─────────
// 章节行编辑借 BOM 模板编辑器（BomTemplateManager）的设计：拖拽手柄 + grid 表行 + 表头，拖动换行。
import draggable from 'vuedraggable'
interface DocSection { key: string; title: string; requires: string }
const docName = ref('')
const docSections = ref<DocSection[]>([])
const docSaving = ref(false)
let docSeq = 0

const CN_NUM = '一二三四五六七八九十'
const DOC_RANGE_OPTIONS = [
  { value: 'auto', label: '自动（按数据实际边界）' },
  { value: 'last_30', label: '近30天' },
  { value: 'last_90', label: '近90天' },
  { value: 'half_year', label: '近半年' },
  { value: 'this_year', label: '今年' },
  { value: 'custom', label: '自定义区间' },
]
const docRangeMode = ref('auto')
const docRangeStart = ref('')
const docRangeEnd = ref('')

/** 与后端 _report_window 同语义的 JS 镜像：右栏预览用，契约权威在后端 */
function rangeWindowPreview(): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  const fmt = (s: string) => s.replace(/-/g, '.')
  const today = new Date()
  if (docRangeMode.value === 'custom')
    return (docRangeStart.value && docRangeEnd.value)
      ? `${fmt(docRangeStart.value)} ~ ${fmt(docRangeEnd.value)}（自定义区间）` : ''
  if (docRangeMode.value === 'auto') return ''
  let start = ''
  if (docRangeMode.value === 'last_30' || docRangeMode.value === 'last_90' || docRangeMode.value === 'half_year') {
    const days = docRangeMode.value === 'last_30' ? 30 : docRangeMode.value === 'last_90' ? 90 : 183
    const s = new Date(today); s.setDate(s.getDate() - (days - 1)); start = iso(s)
  } else if (docRangeMode.value === 'this_year') {
    start = `${today.getFullYear()}-01-01`
  }
  return `${fmt(start)} ~ ${fmt(iso(today))}`
}

function seedDocument() {
  const art = (props.artifact as any) || {}
  docName.value = String(art.name || '数据报告')
  docSections.value = (Array.isArray(art.sections) ? art.sections : [])
    .filter((s: any) => s && typeof s === 'object')
    .map((s: any) => ({ key: String(s.key || `s${++docSeq}`), title: String(s.title || ''), requires: String(s.requires || '') }))
  const dr = (art.data_range && typeof art.data_range === 'object') ? art.data_range : {}
  docRangeMode.value = DOC_RANGE_OPTIONS.some(o => o.value === dr.mode) ? String(dr.mode) : 'auto'
  docRangeStart.value = String(dr.start || '')
  docRangeEnd.value = String(dr.end || '')
}

function addDocSection() {
  docSections.value.push({ key: `s${++docSeq}`, title: '', requires: '' })
}

function removeDocSection(i: number) {
  docSections.value.splice(i, 1)
}

function saveDocument() {
  if (!props.nodeKey) { message.info('未挂接节点，仅预览'); return }
  const sections = docSections.value.filter(s => String(s.title || '').trim())
  if (!sections.length) { message.warning('至少保留一个有标题的章节'); return }
  if (docRangeMode.value === 'custom' && (!docRangeStart.value || !docRangeEnd.value)) {
    message.warning('自定义区间需要起止日期'); return
  }
  docSaving.value = true
  try {
    const data_range = docRangeMode.value === 'custom'
      ? { mode: 'custom', start: docRangeStart.value, end: docRangeEnd.value }
      : { mode: docRangeMode.value }
    // 呈现（render）已归输出节点，保存时把旧存量一并剥掉
    const { render: _staleRender, ...rest } = (props.artifact as any) || {}
    emit('save-target', [{ ...rest, kind: 'document', name: docName.value || '数据报告', data_range, sections }])
  } finally {
    docSaving.value = false
  }
}

watch(() => props.open, async (v) => {
  if (!v) return
  if (props.artifact?.kind === 'form') { await load(); await seedFormPreview(); return }
  if (props.artifact?.kind === 'document') { seedDocument(); return }
  if (props.artifact?.kind === 'table') {
    await seedFieldRows()
    if (isKpView.value) {
      await loadKpPreview()
    } else {
      await loadMachines()
      if (machines.value.length) onSelectModel(machines.value[0])
    }
  }
})
defineExpose({ load })
</script>

<template>
  <a-modal :open="open" :title="`目标层 · ${artifact?.name || '输出物'}`" width="min(1060px, calc(100vw - 32px))" :footer="null"
           wrap-class-name="portal-modal" @cancel="emit('update:open', false)">
    <a-spin :spinning="loading">
      <div class="tlm-meta">
        <a-tag color="blue">{{ KIND_LABELS[artifact?.kind || 'form'] || artifact?.kind }}</a-tag>
        <a-tag>schema：{{ artifact?.schema_ref }}</a-tag>
        <a-tag v-if="artifact?.view">view：{{ artifact?.view }}</a-tag>
        <a-tag v-if="artifact?.rows_from">rows_from：{{ artifact?.rows_from }}</a-tag>
        <span class="tlm-auth">统一大脑：AI 角色按各节点提示执行——「必填」是每个输出字段的策略位</span>
      </div>

      <!-- form：左=登记策略字段契约，右=需求登记表真实预览 -->
      <TargetTwoPane v-if="artifact?.kind === 'form'"
                     :fields="fillFields"
                     left-title="登记策略 · 输出字段"
                     left-hint="字段/顺序权威 = 商机详情页表单定义，此处只配策略"
                     right-title="需求登记表预览"
                     right-hint="商机详情页同款组件 · schema 同源"
                     @ask-change="onFillAskChange" @source-change="onFillSourceChange">
        <template #left-foot>
          <div class="tl-ask-row">
            <span>反问阈值</span>
            <a-input-number v-model:value="askThreshold" :min="1" :max="8" size="small" />
            <span class="tl-sec-hint">必填字段缺 ≥ 此数 → 引擎弹卡反问补全</span>
          </div>
          <div class="tlm-foot">
            <a-button type="primary" :loading="saving" @click="save">保存登记策略</a-button>
          </div>
        </template>
        <template #preview>
          <RequirementForm ref="formPreviewRef" readonly class="tl-preview-form" />
        </template>
      </TargetTwoPane>

      <!-- table：左=字段契约（本节点要填什么，TargetTwoPane 同一套），右=按 view 分流的真实预览 -->
      <TargetTwoPane v-else-if="artifact?.kind === 'table'"
                     :fields="tableFieldRows"
                     :left-title="isKpView ? '配件行 · 本节点要填的配件' : '字段 · 本节点要填什么'"
                     left-hint="必填=该行必须落在最终方案；客户已明确登记且库内有精确料→AI 直接锁定；已登记但库无精确料/模糊→AI 推荐并问客户确认（含自选配方/数量）；关=非必填，AI 可选配"
                     :right-title="isKpView ? 'KP 配件真实预览' : 'L6 配置表预览'"
                     :right-hint="isKpView ? 'KP 库真实料号样例（非运行数据）· 按共享表格式整形' : '真实求值结果 · 与商机详情页方案配置 L6 部分同源'"
                     @ask-change="onFieldAskChange">
        <template #left-foot>
          <div class="tlm-foot tlm-foot-left">
            <a-button type="primary" size="small" :loading="tableSaving" :disabled="!nodeKey" @click="saveFields">保存字段策略</a-button>
          </div>
          <p class="tl-dim">表格式（plan_config 共享，节点不改）：{{ sharedColumnLabels || '—' }}</p>
        </template>
        <template #preview>
          <div class="tl-sec" v-if="!isKpView">
            <a-select v-model:value="selectedModel" size="small" style="width: 100%"
                      :options="machines.map(m => ({ value: m, label: m }))"
                      placeholder="选择机型" @change="onSelectModel" />
          </div>
          <div class="tl-sec">
            <a-spin :spinning="isKpView ? kpPreviewLoading : previewLoading">
              <a-table v-if="previewDataRows.length" :data-source="previewDataRows"
                       :columns="previewColumns" size="small" :pagination="false"
                       :row-key="(_: any, i: number) => i" />
              <div v-else class="tl-empty">暂无预览行。</div>
            </a-spin>
            <p v-if="isKpView && kpPreviewSource" class="tl-sec-hint" style="margin-top: 6px">来源：{{ kpPreviewSource }}</p>
            <p v-if="!isKpView && previewSource" class="tl-sec-hint" style="margin-top: 6px">来源：{{ previewSource }}</p>
            <p v-if="!isKpView" class="tl-sec-hint">基础机箱：配件选配与选型规则调整后，L6 配置在 BOM 组装阶段会随之变化。</p>
          </div>
        </template>
      </TargetTwoPane>

      <!-- document：左=报告名称+数据范围+章节契约编辑（BOM 模板编辑器同款拖拽行），右=结构预览 -->
      <div v-else-if="artifact?.kind === 'document'" class="tlm-doc">
        <div class="tlm-doc-pane">
          <h4 class="tl-sec-title">报告结构契约</h4>
          <div class="tl-doc-basics">
            <div class="tl-doc-basic">
              <span class="tl-dim">报告名称</span>
              <a-input v-model:value="docName" size="small" placeholder="数据报告" />
            </div>
            <div class="tl-doc-basic">
              <span class="tl-dim">数据范围</span>
              <div class="tl-doc-range">
                <a-select v-model:value="docRangeMode" size="small" style="width: 172px" :options="DOC_RANGE_OPTIONS" />
                <template v-if="docRangeMode === 'custom'">
                  <a-date-picker v-model:value="docRangeStart" size="small" value-format="YYYY-MM-DD" placeholder="起" />
                  <span class="tl-dim">~</span>
                  <a-date-picker v-model:value="docRangeEnd" size="small" value-format="YYYY-MM-DD" placeholder="止" />
                </template>
              </div>
            </div>
          </div>

          <div class="tl-thead">
            <span class="c-drag"></span><span>#</span><span>章节标题</span><span>内容要求</span><span></span>
          </div>
          <draggable v-model="docSections" item-key="key" handle=".tl-drag" :animation="180" class="tl-tbody">
            <template #item="{ element: s, index: i }">
              <div class="tl-tr">
                <span class="c-drag"><span class="tl-drag" title="拖拽排序">⠿</span></span>
                <span class="tl-idx">{{ i + 1 }}</span>
                <a-input v-model:value="s.title" size="small" placeholder="如：周数据" />
                <a-textarea v-model:value="s.requires" size="small" :rows="2" placeholder="该节内容要求（如：本周新增商机数、平台分布、机箱分布）" />
                <a-button size="small" type="text" danger @click="removeDocSection(i)">删</a-button>
              </div>
            </template>
          </draggable>
          <div class="tlm-doc-add" @click="addDocSection">＋ 添加章节</div>
          <div class="tlm-foot tlm-foot-left">
            <a-button type="primary" size="small" :loading="docSaving" :disabled="!nodeKey" @click="saveDocument">保存结构契约</a-button>
          </div>
        </div>
        <div class="tlm-doc-pane tlm-doc-pane--preview">
          <h4 class="tl-sec-title">结构预览</h4>
          <div class="tl-sec">
            <b>{{ docName || '数据报告' }}</b>
            <p class="tl-dim">数据范围：{{ rangeWindowPreview() || 'YYYY.MM.DD ~ YYYY.MM.DD（按数据实际边界）' }}</p>
          </div>
          <ol class="tlm-doc-outline">
            <li v-for="(s, i) in docSections.filter(x => String(x.title || '').trim())" :key="s.key">
              <b>{{ CN_NUM[Math.min(i, 9)] }}、{{ s.title }}</b>
              <div class="tl-dim tl-note">{{ s.requires || '（未写内容要求）' }}</div>
            </li>
          </ol>
          <p class="tl-dim">大脑按此结构逐节产出 markdown 结论；数据范围与章节改动下一回合即生效。以什么形式交付（PDF 等）在输出节点配置。</p>
        </div>
      </div>

      <!-- sheet_section：配置表切片的说明视图（机箱表/配件表） -->
      <template v-else>
        <div class="tl-sec">
          <h4 class="tl-sec-title">输出物说明</h4>
          <div class="tl-info">
            <p>该输出物是<b>方案配置表</b>的对应部分，与商机详情页方案配置共用同一数据与渲染来源：</p>
            <ul class="tl-info-list">
              <li v-for="a in targetArtifacts" :key="a.name || a.view">
                <b>{{ a.name }}</b>（{{ KIND_LABELS[a.kind] || a.kind }}）
                <span class="tl-dim">— 视图 {{ a.view }}</span>
                <div class="tl-dim tl-note">{{ a.note }}</div>
              </li>
            </ul>
          </div>
          <div class="tl-info">
            <p class="tl-dim">生成机制：机型选型 → BOM 模板求值出基础机箱 L6；配件落地与选型规则调整后，BOM 组装阶段求值出最终 L6 + 配件部分。规则与模板可在策略中心 / 机型管理处配置。</p>
          </div>
        </div>
      </template>
    </a-spin>
  </a-modal>
</template>

<style scoped>
.tlm-meta { display: flex; gap: 6px; margin-bottom: 12px; align-items: center; }
.tlm-auth { font-size: 11px; color: var(--cpq-text-muted); }
.tl-sec { margin-bottom: 14px; }
.tl-sec-title { margin: 0 0 8px; font-size: 13px; font-weight: 700; color: var(--cpq-text-primary); }
.tl-sec-hint { margin-left: 8px; font-size: 11px; font-weight: 400; color: var(--cpq-text-muted); }
.tl-dim { color: var(--cpq-text-secondary); }
.tl-ask-row { display: flex; gap: 10px; align-items: center; margin-top: 16px; font-size: 12px; color: var(--cpq-text-secondary); }
.tlm-foot { margin-top: 12px; text-align: right; }
.tlm-foot-left { text-align: left; }
.tl-info { margin-bottom: 12px; font-size: 12px; color: var(--cpq-text-secondary); }
.tl-info p { margin: 0 0 6px; }
.tl-info-list { margin: 0; padding-left: 18px; }
.tl-note { margin-top: 2px; }
.tl-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 16px 0; text-align: center; }
.tlm-doc { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
.tlm-doc-pane { min-width: 0; }
.tlm-doc-pane--preview { border-left: 1px solid var(--cpq-overlay-w06, rgba(255,255,255,.06)); padding-left: 16px; }
.tl-doc-basics { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.tl-doc-basic { display: flex; flex-direction: column; gap: 4px; font-size: 11px; min-width: 180px; flex: 1; }
.tl-doc-range { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
/* 章节行：BOM 模板编辑器同款 grid 表行（拖拽手柄 | 序号 | 标题 | 内容要求 | 操作） */
.tl-thead, .tl-tr { display: grid; grid-template-columns: 22px 26px minmax(150px, 1fr) minmax(220px, 1.6fr) 40px;
  gap: 6px; align-items: start; padding: 6px 8px; }
.tl-thead { position: sticky; z-index: 1; font-size: 11px; font-weight: 600; color: var(--cpq-text-muted);
  border-bottom: 1px solid var(--cpq-overlay-w10, rgba(128,128,128,.18)); }
.tl-thead span, .tl-idx { align-self: center; }
.tl-tbody { display: flex; flex-direction: column; }
.tl-tr:hover { background: var(--cpq-overlay-w06, rgba(128,128,128,.06)); border-radius: 8px; }
.tl-tr .ant-input, .tl-tr .ant-input:focus, .tl-tr textarea.ant-input { align-self: stretch; }
.tl-idx { font-size: 12px; color: var(--cpq-text-muted); text-align: center; }
.tl-drag { cursor: grab; display: inline-block; width: 100%; text-align: center; color: var(--cpq-text-muted);
  font-size: 13px; line-height: 1; padding-top: 8px; border-radius: 4px; }
.tl-drag:hover { color: var(--cpq-accent, #3b82f6); }
.tlm-doc-add { border: 1px dashed var(--cpq-overlay-w20, rgba(128,128,128,.35)); border-radius: 8px;
  padding: 8px; text-align: center; font-size: 12px; color: var(--cpq-text-secondary); cursor: pointer; margin: 10px 0; }
.tlm-doc-add:hover { color: var(--cpq-accent, #3b82f6); }
.tlm-doc-outline { margin: 0; padding-left: 20px; font-size: 12px; }
.tlm-doc-outline li { margin-bottom: 6px; }
.tl-preview-form { border: 1px solid var(--cpq-overlay-w06, rgba(255,255,255,.06)); border-radius: 8px; padding: 4px 12px; }
</style>
