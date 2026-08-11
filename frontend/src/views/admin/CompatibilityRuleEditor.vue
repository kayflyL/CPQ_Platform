<script setup lang="ts">
/**
 * 兼容性规则引擎编辑器（取代旧 X6 选型画布 SelectionStrategyCanvas）。
 * 声明式 WHEN(条件)→THEN(动作) 规则：列表态（卡片网格）+ 编辑弹窗（规则构建器）。
 * body: { when:{all?:[cond], any?:[cond]} | cond, then:{action,...}, desc }
 */
import { ref, computed, onMounted, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, EditOutlined, PoweroffOutlined,
  SaveOutlined, CloseOutlined,
} from '@ant-design/icons-vue'
import { compatibilityRulesApi, type CompatibilityRule } from '@/api/compatibilityRules'
import { useSelectionRulesStore } from '@/stores/selectionRules'
import { kpPartsApi } from '@/api/serverConfig'
import {
  RULE_TYPE_MAP, RULE_TYPE_OPTIONS, RULE_OP_OPTIONS, RULE_OP_MAP,
  RULE_CATEGORY_SEED, humanizeFieldPath,
} from '@/constants/ruleMeta'
import { SERVER_ANATOMY, type AnatomyForm, regionFromDrawing, ruleTouchesRegion } from '@/constants/serverAnatomy'
import ServerAnatomyMap from '@/components/selection-map/ServerAnatomyMap.vue'
import { ServerAnatomyViewer } from '@/components/server-visualization'
import { serverDrawingApi, type DrawingView } from '@/api/serverDrawing'
import { catalogApi, type ServerModel } from '@/api/serverConfig'

// 改规则后让消费端（工作台 / 配置向导）缓存的规则失效重拉，做到「改完即时生效」
const selectionRulesStore = useSelectionRulesStore()
// 规则类型 / 操作符 / 字段 / 卡片文案 均来自 @/constants/ruleMeta（SSOT）

const rules = ref<CompatibilityRule[]>([])
const loading = ref(false)

// ── 业务分类（开放标签，DISTINCT 驱动不锁枚举）：顶部过滤条 + 卡片按分类分组 ──
const catFilter = ref<string>('__all__')   // '__all__' | '__none__' | 具体分类名
// 分类名排序：seed 预置项排前（按 RULE_CATEGORY_SEED 顺序），其余按中文排序
const seedFirstSort = (a: string, b: string) => {
  const sa = RULE_CATEGORY_SEED.indexOf(a), sb = RULE_CATEGORY_SEED.indexOf(b)
  if (sa >= 0 || sb >= 0) { if (sa < 0) return 1; if (sb < 0) return -1; return sa - sb }
  return a.localeCompare(b, 'zh')
}
const categoryChips = computed(() => {
  const counts = new Map<string, number>()
  for (const r of rules.value) {
    if (!r.category) continue
    counts.set(r.category, (counts.get(r.category) || 0) + 1)
  }
  return [...counts.entries()]
    .sort(([a], [b]) => seedFirstSort(a, b))
    .map(([name, count]) => ({ name, count }))
})
const uncategorizedCount = computed(() => rules.value.filter(r => !r.category).length)
// 编辑表单分类下拉候选（已有分类 + 可自由输入新分类）
const categoryOpts = computed(() =>
  [...new Set(rules.value.map(r => r.category).filter(Boolean) as string[])]
    .sort(seedFirstSort).map(c => ({ value: c, label: c }))
)

const filtered = computed(() => {
  const f = catFilter.value
  if (!f || f === '__all__') return rules.value
  if (f === '__none__') return rules.value.filter(r => !r.category)
  return rules.value.filter(r => r.category === f)
})
// 按 category 分组渲染（seed 顺序优先 → 其余按名 → 未分类最后）
const groupedFiltered = computed(() => {
  const map = new Map<string, CompatibilityRule[]>()
  for (const r of regionFiltered.value) {
    const key = r.category || '__none__'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(r)
  }
  return [...map.entries()]
    .map(([key, rs]) => ({ key, category: key === '__none__' ? '' : key, rules: rs }))
    .sort((a, b) => {
      if (a.key === '__none__') return 1
      if (b.key === '__none__') return -1
      return seedFirstSort(a.category, b.category)
    })
})

// ── 服务器图视图（地图/列表切换；点击区域联动过滤规则）──
const viewMode = ref<'list' | 'map'>('list')
const mapModelId = ref<number | null>(null)
const models = ref<ServerModel[]>([])
const drawing = ref<DrawingView | null>(null)
const drawingLoading = ref(false)
const anatomyForm = ref<AnatomyForm>('4U')
const regionFilter = ref<string | null>(null)

async function loadModels() {
  try {
    const res = await catalogApi.listModels()
    models.value = res.models || []
    if (!mapModelId.value && models.value.length) mapModelId.value = models.value[0].id
  } catch { models.value = [] }
}
async function loadDrawing() {
  if (!mapModelId.value) { drawing.value = null; return }
  drawingLoading.value = true
  try { drawing.value = await serverDrawingApi.get(mapModelId.value, 'top') }
  catch { drawing.value = null }
  finally { drawingLoading.value = false }
}
watch(viewMode, (m) => {
  if (m === 'map' && models.value.length && !drawing.value) loadDrawing()
  if (m === 'list') regionFilter.value = null
})
watch(mapModelId, () => { regionFilter.value = null; loadDrawing() })

// 上传配置区域 → AnatomyRegion（字段按区域类型继承），并统计各区域命中规则数
const mapRegions = computed(() => drawing.value?.regions || [])
const regionCounts = computed<Record<string, number>>(() => {
  const c: Record<string, number> = {}
  for (const r of mapRegions.value) {
    const ar = regionFromDrawing(r)
    c[r.uid] = rules.value.filter(x => ruleTouchesRegion(x, ar)).length
  }
  return c
})
// 无上传配置时回退默认手绘图（SERVER_ANATOMY 预置）
const fallbackAnatomy = computed(() => SERVER_ANATOMY[anatomyForm.value].map(r => ({ ...r, id: `fb-${r.id}` })))
const fallbackCounts = computed<Record<string, number>>(() => {
  const c: Record<string, number> = {}
  for (const r of fallbackAnatomy.value) c[r.id] = rules.value.filter(x => ruleTouchesRegion(x, r)).length
  return c
})
// 分类 + 区域 交集过滤
const regionFiltered = computed(() => {
  if (!regionFilter.value) return filtered.value
  const ar = drawing.value?.svg_url
    ? mapRegions.value.map(regionFromDrawing).find(a => a.id === regionFilter.value)
    : fallbackAnatomy.value.find(a => a.id === regionFilter.value)
  if (!ar) return filtered.value
  return filtered.value.filter(r => ruleTouchesRegion(r, ar))
})
onMounted(loadModels)

async function load() {
  loading.value = true
  try {
    const r = await compatibilityRulesApi.list()
    rules.value = r.rules || []
  } catch { rules.value = [] } finally { loading.value = false }
}
onMounted(load)

// 规则增删改后：刷新本列表 + 让消费端缓存失效重拉（实时生效）
async function afterChange() {
  await load()
  await selectionRulesStore.invalidateRules()
}

// 候选字段：KP 品类动态（qty + 该品类实际存在的 spec 键）+ config/opportunity 固定。
// ⚠️ 必须取 KP 配件库(kp.kp_categories)，不是料号库(parts_master)——CRE 的 ctx.kp 按 KP 分类聚合，
//    取料号库会让候选全是 ctx 里不存在的死字段（线缆/背板/电源等机箱组成件不进 CRE 寻址空间）。
const kpCats = ref<string[]>([])
const kpSpecKeys = ref<Record<string, string[]>>({})
async function loadKpMeta() {
  try {
    const [cats, sk] = await Promise.all([kpPartsApi.categories(), kpPartsApi.specKeys()])
    kpCats.value = (cats || []).map(c => c.name).filter(Boolean)
    kpSpecKeys.value = sk || {}
  } catch {
    kpCats.value = []
    kpSpecKeys.value = {}
  }
}
onMounted(loadKpMeta)

const fieldOpts = computed(() => {
  const kp: { value: string; label: string }[] = []
  for (const c of kpCats.value) {
    kp.push({ value: `kp.${c}.qty`, label: `kp.${c}.qty` })
    // spec 键按该品类实际数据出（CPU 的 socket/cores、GPU 的 model…），不再写死 interface/kind
    for (const k of (kpSpecKeys.value[c] || [])) {
      kp.push({ value: `kp.${c}.spec.${k}`, label: `kp.${c}.spec.${k}` })
    }
  }
  for (const f of ['config.series', 'config.model', 'config.form', 'config.bays', 'config.sata_qty', 'config.sas_qty', 'config.nvme_qty', 'config.drive_kinds', 'config.bp_type', 'opportunity.platform_type']) {
    kp.push({ value: f, label: f })
  }
  return kp
})
const filterFn = (input: string, option: any) => {
  const opt = typeof option === 'string' ? option : String(option?.value ?? option?.label ?? '')
  return opt.toLowerCase().includes((input || '').toLowerCase())
}

// ── 编辑状态：editing 持有被编辑规则对象，editModalVisible 控制弹窗 ──
const editing = ref<CompatibilityRule | null>(null)
const isNew = ref(false)
const saving = ref(false)
const form = ref<any>({})
const editModalVisible = ref(false)

function blankForm(): any {
  return {
    name: '', type: 'derive', status: 'active', category: '',
    whenAll: [{ field: '', op: '>=', value: '' }],
    target: '', min_qty: '', unique_field: 'pn', specKey: '', specVal: '',
    basis: '', per: 1, round: 'ceil', deriveMode: 'calc', assignField: 'config.bp_type', assignValue: '',
    fScope: 'server_model', fField: 'series', fOp: '==', fValue: 'opportunity.platform_type',
    desc: '',
  }
}
function openNew() {
  isNew.value = true
  editing.value = { id: 0, domain: 'selection', type: 'derive', name: '', scope: null, body: {}, status: 'active', version: 1, hit_count: 0, last_hit_at: null }
  form.value = blankForm()
  editModalVisible.value = true
}
function openEdit(r: CompatibilityRule) {
  isNew.value = false
  editing.value = r
  const b = r.body || {}
  const w = b.when || {}
  const whenAll = Array.isArray(w.all) ? w.all.map((c: any) => ({ field: c.field || '', op: c.op || '>=', value: c.value ?? '' }))
    : (w.field ? [{ field: w.field, op: w.op || '>=', value: w.value ?? '' }] : [{ field: '', op: '>=', value: '' }])
  const t = b.then || {}
  form.value = {
    name: r.name, type: r.type, status: r.status, category: r.category || '', whenAll,
    target: t.target || '', min_qty: t.min_qty || '', unique_field: t.unique_field || 'pn',
    specKey: t.spec_constraint ? Object.keys(t.spec_constraint)[0] || '' : '',
    specVal: t.spec_constraint ? String(Object.values(t.spec_constraint)[0] ?? '') : '',
    basis: t.basis || '', per: t.per || 1, round: t.round || 'ceil',
    deriveMode: (t.field && 'value' in t) ? 'assign' : 'calc', assignField: t.field || 'config.bp_type', assignValue: t.value ?? '',
    fScope: t.scope || 'server_model', fField: t.field || 'series', fOp: t.op || '==', fValue: t.value || 'opportunity.platform_type',
    desc: b.desc || r.description || '',
  }
  editModalVisible.value = true
}
function closeEdit() {
  editModalVisible.value = false
  editing.value = null
  isNew.value = false
  form.value = blankForm()
}

function buildBody(): any {
  const f = form.value
  const whenAll = (f.whenAll || []).filter((c: any) => c.field).map((c: any) => ({ field: c.field, op: c.op, value: c.value }))
  const when = whenAll.length === 0 ? {} : (whenAll.length === 1 ? whenAll[0] : { all: whenAll })
  let then: any
  switch (f.type) {
    case 'require':
      then = { action: 'require', target: f.target }
      if (f.min_qty) then.min_qty = f.min_qty
      if (f.specKey && f.specVal) then.spec_constraint = { [f.specKey]: f.specVal }
      break
    case 'exclude': then = { action: 'exclude', target: f.target, unique_field: f.unique_field || 'pn' }; break
    case 'derive':
      then = f.deriveMode === 'assign'
        ? { action: 'derive', field: f.assignField, value: f.assignValue }
        : { action: 'derive', target: f.target, basis: f.basis, per: Number(f.per) || 1, round: f.round }
      break
    case 'filter': then = { action: 'filter', scope: f.fScope, field: f.fField, op: f.fOp, value: f.fValue }; break
    case 'recommend': then = { action: 'recommend', target: f.target }; break
  }
  return { when, then, desc: f.desc || form.value.name }
}

async function save() {
  const f = form.value
  if (!f.name?.trim()) { message.warning('请填规则名称'); return }
  const needTarget = f.type === 'require' || f.type === 'exclude' || f.type === 'recommend' || (f.type === 'derive' && f.deriveMode !== 'assign')
  if (needTarget && !f.target?.trim()) {
    message.warning('请填目标（如 kp.GPU）'); return
  }
  if (f.type === 'derive' && f.deriveMode === 'assign' && !String(f.assignValue ?? '').trim()) {
    message.warning('请填赋值的值（如 tri）'); return
  }
  const body = buildBody()
  const category = f.category?.trim() || null
  saving.value = true
  try {
    if (!isNew.value && editing.value?.id) {
      await compatibilityRulesApi.update(editing.value.id, { name: f.name, body, status: f.status, category })
    } else {
      await compatibilityRulesApi.create({ type: f.type, name: f.name, body, status: f.status, category })
    }
    message.success('已保存，已即时生效')
    closeEdit()
    await afterChange()
  } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}
function remove(r: CompatibilityRule) {
  Modal.confirm({
    title: '删除规则？', content: r.name, okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => { try { await compatibilityRulesApi.remove(r.id); message.success('已删除'); await afterChange() } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') } },
  })
}
async function toggleStatus(r: CompatibilityRule) {
  const next = r.status === 'active' ? 'archived' : 'active'
  try { await compatibilityRulesApi.setStatus(r.id, next as any); await afterChange() } catch (e: any) { message.error('操作失败') }
}
function resetDefaults() {
  Modal.confirm({
    title: '重置为默认规则？', content: '清空全部兼容性规则，恢复系统 seed。', okText: '重置', okType: 'danger', cancelText: '取消',
    onOk: async () => { try { await compatibilityRulesApi.reset(); message.success('已重置'); await afterChange() } catch (e: any) { message.error(e.response?.data?.detail || '重置失败') } },
  })
}
function addCond() { form.value.whenAll.push({ field: '', op: '>=', value: '' }) }
function delCond(i: number | string) { form.value.whenAll.splice(Number(i), 1) }

/** 卡片一行触发条件（中文化）：始终生效 / <字段中文> <op符号> <值> [且/或 …] 时 */
function whenSummary(b: any): string {
  const w = b?.when
  if (!w || (!w.all && !w.any && !w.field)) return '始终生效'
  const conds: any[] = w.field ? [w] : (w.all || w.any || [])
  const joiner = Array.isArray(w.any) ? ' 或 ' : ' 且 '
  const parts = conds.map((c: any) => {
    const field = humanizeFieldPath(c.field)
    const op = RULE_OP_MAP[c.op] || c.op
    let val: any = c.value
    if (typeof val === 'string' && /^(kp|config|opportunity)\./.test(val)) val = humanizeFieldPath(val)
    return `${field} ${op} ${val}`
  })
  return parts.join(joiner) + ' 时'
}

</script>

<template>
  <div class="cre">
    <!-- ═══════════ 列表态：规则卡片网格 ═══════════ -->
    <div class="cre-main">
        <div class="cre-head">
          <span class="cre-hint">声明式兼容性规则 · WHEN 条件 → THEN 动作 · 选配时实时校验</span>
          <a-space>
            <a-button size="small" @click="resetDefaults">重置默认</a-button>
            <a-button type="primary" size="small" @click="openNew">+ 新建规则</a-button>
          </a-space>
        </div>

        <div class="cre-viewbar">
          <a-radio-group v-model:value="viewMode" size="small" button-style="solid">
            <a-radio-button value="list">列表</a-radio-button>
            <a-radio-button value="map">服务器图</a-radio-button>
          </a-radio-group>
          <template v-if="viewMode === 'map'">
            <a-select v-model:value="mapModelId" :options="models.map(m => ({ value: m.id, label: m.name }))"
              placeholder="选择机型" style="width: 210px" size="small" show-search option-filter-prop="label" allow-clear />
            <a-radio-group v-if="!drawing?.svg_url" v-model:value="anatomyForm" size="small">
              <a-radio-button value="2U">2U</a-radio-button>
              <a-radio-button value="4U">4U</a-radio-button>
            </a-radio-group>
            <span class="cre-map-hint">{{ regionFilter ? '已按区域过滤，点区域或列表模式恢复' : '点击服务器上的区域，下方只显示相关规则' }}</span>
          </template>
        </div>

        <div v-if="viewMode === 'map'" class="cre-map glass-light">
          <a-spin :spinning="drawingLoading">
            <ServerAnatomyViewer
              v-if="drawing?.svg_url"
              :svg-url="drawing.svg_url"
              :view-box="drawing.viewBox"
              :regions="drawing.regions"
              :counts="regionCounts"
              :active-id="regionFilter"
              @select="regionFilter = $event"
            />
            <ServerAnatomyMap
              v-else
              :regions="fallbackAnatomy"
              :counts="fallbackCounts"
              :active-id="regionFilter"
              @select="regionFilter = $event"
            />
          </a-spin>
        </div>

        <div class="cre-cats">
          <button class="cre-cat" :class="{ on: catFilter === '__all__' }" @click="catFilter = '__all__'">
            全部<em>{{ rules.length }}</em>
          </button>
          <button v-for="c in categoryChips" :key="c.name" class="cre-cat"
            :class="{ on: catFilter === c.name }"
            @click="catFilter = c.name">
            {{ c.name }}<em>{{ c.count }}</em>
          </button>
          <button v-if="uncategorizedCount" class="cre-cat"
            :class="{ on: catFilter === '__none__' }" @click="catFilter = '__none__'">
            未分类<em>{{ uncategorizedCount }}</em>
          </button>
        </div>

        <a-spin :spinning="loading">
          <div v-if="groupedFiltered.length">
            <div v-for="grp in groupedFiltered" :key="grp.key" class="cre-group">
              <div class="cre-group-head">
                <span class="cre-group-bar"></span>
                <span class="cre-group-name">{{ grp.category || '未分类' }}</span>
                <span class="cre-group-count">{{ grp.rules.length }}</span>
              </div>
              <div class="cre-list">
                <div v-for="r in grp.rules" :key="r.id"
                  class="cre-card glass-light"
                  :class="{ archived: r.status !== 'active' }"
                  @click="openEdit(r)">
                  <div class="cre-card-head">
                    <span class="cre-dot" :class="r.status === 'active' ? 'on' : 'off'"
                      :title="r.status === 'active' ? '生效中' : '已停用'"></span>
                    <span class="cre-name">{{ r.name }}</span>
                    <span class="cre-type-label">{{ RULE_TYPE_MAP[r.type]?.label }}</span>
                    <span v-if="r.hit_count" class="cre-hit" title="WHEN 条件命中累计次数（工作台选配 + 需求分析自动出方案都会记）">命中 {{ r.hit_count }} 次</span>
                  </div>
                  <p class="cre-trigger">{{ whenSummary(r.body) }}</p>
                  <div class="cre-card-foot" @click.stop>
                    <a-tooltip :title="r.status === 'active' ? '停用' : '启用'"><a-button size="small" type="text" @click="toggleStatus(r)"><PoweroffOutlined /></a-button></a-tooltip>
                    <a-tooltip title="编辑"><a-button size="small" type="text" @click="openEdit(r)"><EditOutlined /></a-button></a-tooltip>
                    <a-tooltip title="删除"><a-button size="small" type="text" danger @click="remove(r)"><DeleteOutlined /></a-button></a-tooltip>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <a-empty v-else description="暂无此类规则，点「新建规则」添加" />
        </a-spin>
      </div>

    <!-- ═══════════ 编辑弹窗：规则构建器 ═══════════ -->
    <a-modal v-model:open="editModalVisible" :title="isNew ? '新建规则' : '编辑规则'"
      width="1180px" :footer="null" :mask-closable="false" wrap-class-name="cre-edit-modal" @cancel="closeEdit">
      <div class="cre-edit-grid">
        <div class="cre-edit-form glass-light">
          <a-form layout="vertical" size="small">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="规则名称">
                  <a-input v-model:value="form.name" placeholder="如：选 GPU 需配 GPU 线缆" />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="规则类型">
                  <a-select v-model:value="form.type" :options="RULE_TYPE_OPTIONS" />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="业务分类">
                  <a-auto-complete :value="form.category" :options="categoryOpts"
                    placeholder="如：背板与线缆" :filter-option="filterFn"
                    @update:value="(v: any) => form.category = String(v || '')" />
                </a-form-item>
              </a-col>
            </a-row>

            <a-divider orientation="left">触发条件 WHEN</a-divider>
            <a-form-item label="全部满足">
              <div v-for="(c, i) in form.whenAll" :key="i" class="cre-cond-row">
                <a-auto-complete :value="c.field" :options="fieldOpts" placeholder="字段 kp.GPU.qty" style="width: 210px" :filter-option="filterFn" @update:value="(v: any) => c.field = String(v || '')" />
                <a-select :value="c.op" style="width: 88px" :options="RULE_OP_OPTIONS" @change="(v: any) => c.op = v" />
                <a-input :value="String(c.value ?? '')" placeholder="值（Polaris / 1 / NVMe）" style="flex: 1; min-width: 140px" @change="(e: any) => c.value = e.target.value" />
                <a-button type="text" danger size="small" @click="delCond(i)"><DeleteOutlined /></a-button>
              </div>
              <a-button type="dashed" size="small" block @click="addCond"><PlusOutlined /> 增加条件</a-button>
            </a-form-item>

            <a-divider orientation="left">执行动作 THEN</a-divider>
            <a-form-item>
              <template v-if="form.type === 'require'">
                <div class="cre-cond-row">
                  <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="目标 kp.GPU供电线" style="width: 230px" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
                  <a-input :value="form.min_qty" placeholder="最少数量（字段或数字）" style="flex: 1" @change="(e: any) => form.min_qty = e.target.value" />
                </div>
                <div class="cre-cond-row">
                  <a-input :value="form.specKey" placeholder="规格约束键（可选）" style="flex: 1" @change="(e: any) => form.specKey = e.target.value" />
                  <a-input :value="form.specVal" placeholder="规格值" style="flex: 1" @change="(e: any) => form.specVal = e.target.value" />
                </div>
              </template>
              <template v-else-if="form.type === 'exclude'">
                <div class="cre-cond-row">
                  <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="目标 kp.Memory" style="width: 230px" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
                  <a-input :value="form.unique_field" placeholder="唯一字段（默认 pn）" style="flex: 1" @change="(e: any) => form.unique_field = e.target.value" />
                </div>
              </template>
              <template v-else-if="form.type === 'derive'">
                <a-radio-group :value="form.deriveMode" @change="(e: any) => form.deriveMode = e.target.value" style="margin-bottom: 8px">
                  <a-radio value="assign">赋值（条件→固定值）</a-radio>
                  <a-radio value="calc">算术（basis÷per→数量）</a-radio>
                </a-radio-group>
                <template v-if="form.deriveMode === 'assign'">
                  <div class="cre-cond-row">
                    <a-auto-complete :value="form.assignField" :options="fieldOpts" placeholder="赋值字段 config.bp_type" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.assignField = String(v || '')" />
                    <a-input :value="String(form.assignValue ?? '')" placeholder="值（如 tri / dc）" style="width: 160px" @change="(e: any) => form.assignValue = e.target.value" />
                  </div>
                </template>
                <template v-else>
                  <div class="cre-cond-row">
                    <a-auto-complete :value="form.basis" :options="fieldOpts" placeholder="依据 config.sata_qty" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.basis = String(v || '')" />
                    <a-input-number :value="form.per" :min="1" placeholder="每 N" style="width: 120px" @change="(v: any) => form.per = v" />
                    <a-select :value="form.round" style="width: 110px" :options="[{ value: 'ceil', label: '向上取整' }, { value: 'floor', label: '向下取整' }]" @change="(v: any) => form.round = v" />
                  </div>
                  <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="派生目标" style="width: 100%" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
                </template>
              </template>
              <template v-else-if="form.type === 'filter'">
                <div class="cre-cond-row">
                  <a-select :value="form.fScope" style="width: 130px" :options="[{ value: 'server_model', label: '候选机型' }, { value: 'kp', label: 'KP 配件' }]" @change="(v: any) => form.fScope = v" />
                  <a-input :value="form.fField" placeholder="字段 series" style="flex: 1" @change="(e: any) => form.fField = e.target.value" />
                  <a-select :value="form.fOp" style="width: 88px" :options="RULE_OP_OPTIONS" @change="(v: any) => form.fOp = v" />
                  <a-input :value="form.fValue" placeholder="值（字段或字面）" style="flex: 1" @change="(e: any) => form.fValue = e.target.value" />
                </div>
              </template>
              <template v-else-if="form.type === 'recommend'">
                <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="推荐目标 kp.GPU" style="width: 100%" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
              </template>
            </a-form-item>

            <a-divider orientation="left">说明</a-divider>
            <a-form-item><a-input v-model:value="form.desc" placeholder="规则描述（可选）" /></a-form-item>
          </a-form>
        </div>
      </div>
      <div class="cre-edit-foot">
        <a-button @click="closeEdit"><CloseOutlined /> 取消</a-button>
        <a-button type="primary" :loading="saving" @click="save"><SaveOutlined /> 保存</a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
/* 单栏：操作栏 + 卡片网格（编辑走弹窗） */
.cre { display: flex; flex-direction: column; gap: 12px; }
.cre-main { display: flex; flex-direction: column; gap: 12px; }
.cre-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cre-hint { color: var(--cpq-text-secondary); font-size: 12px; }

/* 视图切换条 + 服务器图 */
.cre-viewbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.cre-map-hint { color: var(--cpq-text-secondary); font-size: 12px; }
.cre-map { padding: 12px; border-radius: 12px; }

/* 分类过滤条：开放标签；选中态蓝边（Glass Console 白玻璃 + 蓝边激活） */
.cre-cats { display: flex; flex-wrap: wrap; gap: 8px; }
.cre-cat {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-2-bg);
  color: var(--cpq-text-secondary); font-size: 12.5px;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), background var(--cpq-dur-1) var(--cpq-ease-smooth), color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.cre-cat em { font-style: normal; font-size: 11px; padding: 0 6px; border-radius: 8px;
  background: var(--cpq-overlay-a8); color: var(--cpq-text-muted); }
.cre-cat:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-text-primary); }
.cre-cat.on { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8); }
.cre-cat.on em { background: var(--cpq-accent-primary); color: #fff; }

/* 分类分组标题 */
.cre-group { margin-bottom: 16px; }
.cre-group-head { display: flex; align-items: center; gap: 8px; margin: 2px 0 8px; }
.cre-group-bar { width: 3px; height: 14px; border-radius: 2px; flex: none;
  background: var(--cpq-text-disabled); }
.cre-group-name { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); }
.cre-group-count { font-size: 11px; color: var(--cpq-text-muted); padding: 0 7px; border-radius: 8px;
  background: var(--cpq-overlay-a10, rgba(0,0,0,.06)); }

/* 规则卡片：自适应紧凑网格，类型色左边条 + 右上角类型标签 */
.cre-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }
.cre-card {
  position: relative; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 8px; cursor: pointer;
  transition: transform var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.cre-card:hover { transform: translateY(-1px); }
.cre-card.archived { opacity: .55; }
.cre-card.active { box-shadow: 0 0 0 2px var(--cpq-accent-primary); }
.cre-card-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cre-dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.cre-dot.on { background: var(--cpq-color-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cpq-color-success) 22%, transparent); }
.cre-dot.off { background: var(--cpq-text-muted); }
.cre-name { font-weight: 600; font-size: 14px; color: var(--cpq-text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cre-hit { font-size: 11px; color: var(--cpq-text-muted); background: var(--cpq-overlay-a10); padding: 1px 8px; border-radius: 8px; white-space: nowrap; flex-shrink: 0; }
.cre-type-label { font-size: 11px; font-weight: 600; color: var(--cpq-text-muted); flex: none; padding: 1px 6px; border-radius: 5px; background: var(--cpq-overlay-a8); }
.cre-trigger { margin: 0; font-size: 12.5px; line-height: 1.45; color: var(--cpq-text-secondary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.cre-card-foot { display: flex; justify-content: flex-end; gap: 2px; margin-top: 2px; padding-top: 6px; border-top: 1px dashed var(--cpq-overlay-a15); opacity: 0; transition: opacity var(--cpq-dur-1) var(--cpq-ease-smooth); }
.cre-card:hover .cre-card-foot { opacity: 1; }
.cre-card.active .cre-card-foot .ant-btn:first-child { color: var(--cpq-accent-primary); }
.cre-cond-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }

/* ── 编辑弹窗：构建器（单栏） ── */
.cre-edit-grid { display: grid; grid-template-columns: 1fr; gap: 16px; height: min(620px, 66vh); }
.cre-edit-form { padding: 18px 22px; border-radius: 12px; overflow-y: auto; }
.cre-edit-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

@media (max-width: 980px) {
  .cre-edit-grid { grid-template-columns: 1fr; height: auto; }
}
@media (max-width: 560px) {
  .cre-list { grid-template-columns: 1fr; }
}
</style>
