<script setup lang="ts">
/**
 * 兼容性规则引擎编辑器（取代旧 X6 选型画布 SelectionStrategyCanvas）。
 * 声明式 WHEN(条件)→THEN(动作) 规则：左栏 tab + 规则卡片（2 列网格）+ 规则试跑，右栏依赖拓扑图常驻联动；
 * 系统内置推导规则（功耗/电源/线缆/背板）收进顶部「内置推导规则」按钮的抽屉，不再平铺占位。
 * body: { when:{all?:[cond], any?:[cond]} | cond, then:{action,...}, desc }
 */
import { ref, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, EditOutlined, PoweroffOutlined, ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { compatibilityRulesApi, type CompatibilityRule, type RuleType } from '@/api/compatibilityRules'
import CompatibilityImpactGraph from './CompatibilityImpactGraph.vue'
import DerivationRulesPanel from './DerivationRulesPanel.vue'
import { useSelectionRulesStore } from '@/stores/selectionRules'
import { evaluateRules, type RuleContext } from '@/stores/selectionEngine'
import { partsApi } from '@/api/serverConfig'

// 改规则后让消费端（工作台 / 配置向导）缓存的规则失效重拉，做到「改完即时生效」
const selectionRulesStore = useSelectionRulesStore()

const TYPE_DEFS: { value: RuleType; label: string; color: string }[] = [
  { value: 'require', label: '必配/依赖', color: 'var(--cpq-accent-primary)' },
  { value: 'exclude', label: '互斥', color: 'var(--cpq-accent-danger)' },
  { value: 'derive', label: '派生', color: 'var(--cpq-accent-cyan)' },
  { value: 'filter', label: '过滤', color: 'var(--cpq-accent-warning)' },
  { value: 'recommend', label: '推荐', color: 'var(--cpq-color-success)' },
]
const OPS = [
  { value: '>=', label: '≥' }, { value: '<=', label: '≤' },
  { value: '>', label: '>' }, { value: '<', label: '<' },
  { value: '==', label: '=' }, { value: '!=', label: '≠' },
  { value: 'in', label: '属于' }, { value: 'contains', label: '包含' },
  { value: 'exists', label: '有值' },
]

const rules = ref<CompatibilityRule[]>([])
const loading = ref(false)
const activeType = ref<RuleType>('require')
const filtered = computed(() => rules.value.filter(r => r.type === activeType.value))
const deriveDrawerVisible = ref(false)

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

// 候选字段：KP 品类动态（qty + 常用 spec）+ config/opportunity 固定
const partCategories = ref<string[]>([])
async function loadCats() {
  try { const r = await partsApi.categories(); partCategories.value = r.categories || [] }
  catch { partCategories.value = [] }
}
onMounted(loadCats)
const fieldOpts = computed(() => {
  const kp: { value: string; label: string }[] = []
  for (const c of partCategories.value) {
    kp.push({ value: `kp.${c}.qty`, label: `kp.${c}.qty` })
    kp.push({ value: `kp.${c}.spec.interface`, label: `kp.${c}.spec.interface` })
    kp.push({ value: `kp.${c}.spec.kind`, label: `kp.${c}.spec.kind` })
  }
  for (const f of ['config.series', 'config.model', 'config.sata_qty', 'opportunity.platform_type']) {
    kp.push({ value: f, label: f })
  }
  return kp
})
const filterFn = (input: string, option: any) => {
  const opt = typeof option === 'string' ? option : String(option?.value ?? option?.label ?? '')
  return opt.toLowerCase().includes((input || '').toLowerCase())
}

// ── 编辑 modal ──
const modalVisible = ref(false)
const editing = ref<CompatibilityRule | null>(null)
const saving = ref(false)
const form = ref<any>({})

function blankForm(): any {
  return {
    name: '', type: activeType.value, status: 'active',
    whenAll: [{ field: '', op: '>=', value: '' }],
    target: '', min_qty: '', unique_field: 'pn', specKey: '', specVal: '',
    basis: '', per: 1, round: 'ceil',
    fScope: 'server_model', fField: 'series', fOp: '==', fValue: 'opportunity.platform_type',
    desc: '',
  }
}
function openNew() { editing.value = null; form.value = blankForm(); modalVisible.value = true }
function openEdit(r: CompatibilityRule) {
  editing.value = r
  const b = r.body || {}
  const w = b.when || {}
  const whenAll = Array.isArray(w.all) ? w.all.map((c: any) => ({ field: c.field || '', op: c.op || '>=', value: c.value ?? '' }))
    : (w.field ? [{ field: w.field, op: w.op || '>=', value: w.value ?? '' }] : [{ field: '', op: '>=', value: '' }])
  const t = b.then || {}
  form.value = {
    name: r.name, type: r.type, status: r.status, whenAll,
    target: t.target || '', min_qty: t.min_qty || '', unique_field: t.unique_field || 'pn',
    specKey: t.spec_constraint ? Object.keys(t.spec_constraint)[0] || '' : '',
    specVal: t.spec_constraint ? String(Object.values(t.spec_constraint)[0] ?? '') : '',
    basis: t.basis || '', per: t.per || 1, round: t.round || 'ceil',
    fScope: t.scope || 'server_model', fField: t.field || 'series', fOp: t.op || '==', fValue: t.value || 'opportunity.platform_type',
    desc: b.desc || r.description || '',
  }
  modalVisible.value = true
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
    case 'derive': then = { action: 'derive', target: f.target, basis: f.basis, per: Number(f.per) || 1, round: f.round }; break
    case 'filter': then = { action: 'filter', scope: f.fScope, field: f.fField, op: f.fOp, value: f.fValue }; break
    case 'recommend': then = { action: 'recommend', target: f.target }; break
  }
  return { when, then, desc: f.desc || form.value.name }
}

async function save() {
  const f = form.value
  if (!f.name?.trim()) { message.warning('请填规则名称'); return }
  if ((f.type === 'require' || f.type === 'exclude' || f.type === 'derive' || f.type === 'recommend') && !f.target?.trim()) {
    message.warning('请填目标（如 kp.GPU）'); return
  }
  const body = buildBody()
  saving.value = true
  try {
    if (editing.value) await compatibilityRulesApi.update(editing.value.id, { name: f.name, body, status: f.status })
    else await compatibilityRulesApi.create({ type: f.type, name: f.name, body, status: f.status })
    message.success('已保存，已即时生效')
    modalVisible.value = false
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

const typeColor = (t: string) => TYPE_DEFS.find(x => x.value === t)?.color
function whenText(b: any): string {
  const w = b?.when
  if (!w || (!w.all && !w.field)) return '总是生效'
  const conds: any[] = Array.isArray(w.all) ? w.all : (w.field ? [w] : [])
  return conds.map(c => `${c.field} ${c.op} ${c.value}`).join(' 且 ')
}
function thenText(b: any): string {
  const t = b?.then
  if (!t) return ''
  if (t.action === 'require') return `必配 ${t.target}${t.min_qty ? `（≥${t.min_qty}）` : ''}${t.spec_constraint ? ` 规格${Object.entries(t.spec_constraint).map(([k,v])=>`${k}=${v}`).join(',')}` : ''}`
  if (t.action === 'exclude') return `${t.target} 同${t.unique_field || 'pn'}不混搭`
  if (t.action === 'derive') return `派生 ${t.target} = ${t.basis}÷${t.per}（${t.round === 'ceil' ? '向上' : '向下'}）`
  if (t.action === 'filter') return `${t.scope}.${t.field} ${t.op} ${t.value}`
  if (t.action === 'recommend') return `推荐 ${t.target}`
  return ''
}

// ── 规则试跑：点规则卡片的 ⚡，按该规则 WHEN 条件自动还原触发场景，跑引擎看命中 ──
const trialRuleId = ref<number | null>(null)
function isFieldPath(v: any): boolean {
  return typeof v === 'string' && /^(kp|config|opportunity)\./.test(v)
}
// 按操作符算一个能让条件成立的值（字段间比较 / 不等 跳过）
function satisfyValue(op: string, value: any): any {
  if (isFieldPath(value)) return undefined
  const n = Number(value)
  switch (op) {
    case '>=': return Number.isFinite(n) ? n : value
    case '>': return Number.isFinite(n) ? n + 1 : value
    case '<=': return Number.isFinite(n) ? n : value
    case '<': return Number.isFinite(n) ? Math.max(0, n - 1) : value
    case '==': return value
    case '!=': return undefined
    case 'in': return Array.isArray(value) ? value[0] : value
    case 'contains': return value
    case 'exists': return Number.isFinite(n) ? n : 'x'
    default: return value
  }
}
function setCtxField(ctx: RuleContext, field: string, val: any) {
  const parts = field.split('.')
  if (parts[0] === 'kp') {
    const cat = parts[1]
    if (!ctx.kp[cat]) ctx.kp[cat] = { qty: 0, items: [], spec: {} }
    if (parts[2] === 'qty') ctx.kp[cat].qty = Number(val) || 0
    else if (parts[2] === 'spec') (ctx.kp[cat].spec as any)[parts[3]] = val
  } else if (parts[0] === 'config') {
    (ctx.config as any)[parts[1]] = val
  } else if (parts[0] === 'opportunity') {
    (ctx.opportunity as any)[parts[1]] = val
  }
}
// 从规则 WHEN 条件反向构造一个能触发它的 context
function buildCtxFromRule(rule: CompatibilityRule): { ctx: RuleContext; scenario: { text: string; ok: boolean }[] } {
  const ctx: RuleContext = { kp: {}, config: {}, opportunity: {} }
  const scenario: { text: string; ok: boolean }[] = []
  const w = rule.body?.when as any
  const conds: any[] = []
  if (Array.isArray(w?.all)) conds.push(...w.all)
  else if (Array.isArray(w?.any)) conds.push(...w.any)
  else if (w?.field) conds.push(w)
  for (const c of conds) {
    if (!c?.field) continue
    const val = satisfyValue(c.op, c.value)
    if (val === undefined) { scenario.push({ text: `${c.field} ${c.op} ${c.value}`, ok: false }); continue }
    setCtxField(ctx, c.field, val)
    scenario.push({ text: `${c.field} ${c.op} ${c.value} → ${val}`, ok: true })
  }
  return { ctx, scenario }
}
const trialResult = computed(() => {
  if (trialRuleId.value == null) return null
  const rule = rules.value.find(r => r.id === trialRuleId.value)
  if (!rule) return null
  const { ctx, scenario } = buildCtxFromRule(rule)
  return { rule, scenario, actions: evaluateRules(rules.value, ctx) }
})
function toggleTrial(r: CompatibilityRule) {
  trialRuleId.value = trialRuleId.value === r.id ? null : r.id
}
</script>

<template>
  <div class="cre">
    <!-- 左栏：操作栏 + tab + 规则卡片网格 + 规则试跑 -->
    <div class="cre-main">
      <div class="cre-head">
        <span class="cre-hint">声明式兼容性规则 · WHEN 条件 → THEN 动作 · 选配时实时校验</span>
        <a-space>
          <a-button size="small" @click="deriveDrawerVisible = true">内置推导规则</a-button>
          <a-button size="small" @click="resetDefaults">重置默认</a-button>
          <a-button type="primary" size="small" @click="openNew">+ 新建规则</a-button>
        </a-space>
      </div>

      <a-tabs v-model:activeKey="activeType" size="small">
        <a-tab-pane v-for="t in TYPE_DEFS" :key="t.value" :tab="`${t.label}（${rules.filter(r => r.type === t.value).length}）`" />
      </a-tabs>

      <a-spin :spinning="loading">
        <div v-if="filtered.length" class="cre-list">
          <div v-for="r in filtered" :key="r.id" class="cre-card glass-light" :class="{ archived: r.status !== 'active', active: trialRuleId === r.id }">
            <div class="cre-card-head">
              <span class="cre-dot" :style="{ background: typeColor(r.type) }"></span>
              <span class="cre-name">{{ r.name }}</span>
              <a-tag :color="r.status === 'active' ? 'green' : 'default'" style="margin: 0">{{ r.status === 'active' ? '生效' : '停用' }}</a-tag>
            </div>
            <div class="cre-card-body">
              <div class="cre-line"><span class="cre-lbl" style="color: var(--cpq-accent-primary)">当</span> {{ whenText(r.body) }}</div>
              <div class="cre-line"><span class="cre-lbl" :style="{ color: typeColor(r.type) }">则</span> {{ thenText(r.body) }}</div>
              <div v-if="r.body?.desc" class="cre-desc">{{ r.body.desc }}</div>
            </div>
            <div class="cre-card-foot">
              <a-tooltip title="试跑此规则"><a-button size="small" type="text" @click="toggleTrial(r)"><ThunderboltOutlined /></a-button></a-tooltip>
              <a-tooltip :title="r.status === 'active' ? '停用' : '启用'"><a-button size="small" type="text" @click="toggleStatus(r)"><PoweroffOutlined /></a-button></a-tooltip>
              <a-tooltip title="编辑"><a-button size="small" type="text" @click="openEdit(r)"><EditOutlined /></a-button></a-tooltip>
              <a-tooltip title="删除"><a-button size="small" type="text" danger @click="remove(r)"><DeleteOutlined /></a-button></a-tooltip>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无此类规则，点「新建规则」添加" />
      </a-spin>

      <!-- 规则试跑：点规则 ⚡，按其 WHEN 条件自动还原场景并查看命中 -->
      <section v-if="trialResult" class="cre-trial">
        <div class="cre-trial-head">
          <ThunderboltOutlined class="cre-trial-icon" />
          <span class="cre-trial-title">试跑：{{ trialResult.rule.name }}</span>
          <a-button size="small" type="text" @click="trialRuleId = null">收起</a-button>
        </div>
        <div class="cre-trial-sec">触发场景（按规则条件自动生成）</div>
        <div v-if="trialResult.scenario.length" class="cre-trial-scen">
          <div v-for="(s, i) in trialResult.scenario" :key="i" class="cre-trial-scenitem" :class="{ skip: !s.ok }">
            {{ s.ok ? s.text : `${s.text}（字段比较，跳过）` }}
          </div>
        </div>
        <div v-else class="cre-trial-empty">该规则无显式触发条件（总是生效）</div>
        <div class="cre-trial-sec">命中动作</div>
        <div class="cre-trial-result">
          <div v-if="!trialResult.actions.length" class="cre-trial-empty">未命中——条件可能含字段间比较，自动场景覆盖不了</div>
          <div v-for="(a, idx) in trialResult.actions" :key="idx" class="cre-trial-act" :class="`sev-${a.severity}`">
            <span class="cre-trial-actdesc">{{ a.desc }}</span>
            <span class="cre-trial-actrule">{{ a.ruleName }}</span>
          </div>
        </div>
        <p class="cre-trial-note">场景由规则 WHEN 反推生成；互斥（同 PN）、规格约束类需真实零件 pn/spec，工作台真实验证。</p>
      </section>
      <section v-else class="cre-trial cre-trial-idle">
        <ThunderboltOutlined class="cre-trial-icon" />
        <span>点上方任意规则卡片的 ⚡ 试跑，自动按规则条件还原场景并查看命中</span>
      </section>
    </div>

    <!-- 右栏：依赖拓扑图（常驻 sticky，随左侧规则实时联动）-->
    <aside class="cre-aside">
      <div class="cre-aside-head">
        <span class="cre-aside-title">影响拓扑</span>
        <span class="cre-aside-sub">规则间的依赖 / 互斥 / 过滤 · 只读</span>
      </div>
      <div class="cre-aside-body">
        <CompatibilityImpactGraph :rules="rules" />
      </div>
      <p class="cre-aside-hint">改左侧规则，此图实时刷新；编辑请用左侧卡片。</p>
    </aside>

    <a-modal v-model:open="modalVisible" :title="editing ? '编辑规则' : '新建规则'" width="660px" @ok="save" :confirm-loading="saving" okText="保存" cancelText="取消">
      <a-form layout="vertical" size="small">
        <a-form-item label="规则名称"><a-input v-model:value="form.name" placeholder="如：选 GPU 需配 GPU 线缆" /></a-form-item>
        <a-form-item label="规则类型">
          <a-select v-model:value="form.type" :options="TYPE_DEFS.map(t => ({ value: t.value, label: t.label }))" />
        </a-form-item>

        <a-form-item label="触发条件 WHEN（全部满足）">
          <div v-for="(c, i) in form.whenAll" :key="i" class="cre-cond-row">
            <a-auto-complete :value="c.field" :options="fieldOpts" placeholder="字段 kp.GPU.qty" style="width: 210px" :filter-option="filterFn" @update:value="(v: any) => c.field = String(v || '')" />
            <a-select :value="c.op" style="width: 88px" :options="OPS" @change="(v: any) => c.op = v" />
            <a-input :value="String(c.value ?? '')" placeholder="值（Polaris / 1 / NVMe）" style="flex: 1; min-width: 140px" @change="(e: any) => c.value = e.target.value" />
            <a-button type="text" danger size="small" @click="delCond(i)"><DeleteOutlined /></a-button>
          </div>
          <a-button type="dashed" size="small" block @click="addCond"><PlusOutlined /> 增加条件</a-button>
        </a-form-item>

        <a-form-item label="执行动作 THEN">
          <template v-if="form.type === 'require'">
            <div class="cre-cond-row">
              <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="目标 kp.GPU供电线" style="width: 230px" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
              <a-input :value="form.min_qty" placeholder="最少数量（字段或数字，如 kp.GPU.qty）" style="flex: 1" @change="(e: any) => form.min_qty = e.target.value" />
            </div>
            <div class="cre-cond-row">
              <a-input :value="form.specKey" placeholder="规格约束键（可选 support）" style="flex: 1" @change="(e: any) => form.specKey = e.target.value" />
              <a-input :value="form.specVal" placeholder="规格值（tri-mode）" style="flex: 1" @change="(e: any) => form.specVal = e.target.value" />
            </div>
          </template>
          <template v-else-if="form.type === 'exclude'">
            <div class="cre-cond-row">
              <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="目标 kp.Memory" style="width: 230px" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
              <a-input :value="form.unique_field" placeholder="唯一字段（默认 pn）" style="flex: 1" @change="(e: any) => form.unique_field = e.target.value" />
            </div>
          </template>
          <template v-else-if="form.type === 'derive'">
            <div class="cre-cond-row">
              <a-auto-complete :value="form.basis" :options="fieldOpts" placeholder="依据 config.sata_qty" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.basis = String(v || '')" />
              <a-input-number :value="form.per" :min="1" placeholder="每 N" style="width: 120px" @change="(v: any) => form.per = v" />
              <a-select :value="form.round" style="width: 110px" :options="[{ value: 'ceil', label: '向上取整' }, { value: 'floor', label: '向下取整' }]" @change="(v: any) => form.round = v" />
            </div>
            <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="派生目标 kp.HDD BP to MB cable" style="width: 100%" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
          </template>
          <template v-else-if="form.type === 'filter'">
            <div class="cre-cond-row">
              <a-select :value="form.fScope" style="width: 130px" :options="[{ value: 'server_model', label: '候选机型' }, { value: 'kp', label: 'KP 配件' }]" @change="(v: any) => form.fScope = v" />
              <a-input :value="form.fField" placeholder="字段 series" style="flex: 1" @change="(e: any) => form.fField = e.target.value" />
              <a-select :value="form.fOp" style="width: 88px" :options="OPS" @change="(v: any) => form.fOp = v" />
              <a-input :value="form.fValue" placeholder="值（字段或字面）" style="flex: 1" @change="(e: any) => form.fValue = e.target.value" />
            </div>
          </template>
          <template v-else-if="form.type === 'recommend'">
            <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="推荐目标 kp.GPU" style="width: 100%" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
          </template>
        </a-form-item>

        <a-form-item label="说明（可选）"><a-input v-model:value="form.desc" placeholder="规则描述" /></a-form-item>
      </a-form>
    </a-modal>

    <!-- 系统内置推导规则抽屉（原底部折叠区抽出，按需打开）-->
    <a-drawer
      v-model:open="deriveDrawerVisible"
      title="系统内置推导规则"
      placement="right"
      :width="520"
    >
      <p class="cre-drawer-hint">配置时机箱功耗 / 电源数量 / 线缆根数 / 背板类型等自动推导所用规则——可查看可调整，改完立即生效。</p>
      <DerivationRulesPanel />
    </a-drawer>
  </div>
</template>

<style scoped>
/* 两栏：左规则 flex:1，右拓扑固定宽 sticky 常驻 */
.cre { display: flex; gap: 16px; align-items: flex-start; }
.cre-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.cre-aside {
  flex: none; width: 500px; position: sticky; top: 16px;
  display: flex; flex-direction: column; gap: 8px;
}
.cre-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cre-hint { color: var(--cpq-text-secondary); font-size: 12px; }

/* 规则卡片：2 列网格 */
.cre-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.cre-card { padding: 10px 12px; border-radius: var(--cpq-radius-md, 12px); display: flex; flex-direction: column; }
.cre-card.archived { opacity: .55; }
.cre-card.active { box-shadow: 0 0 0 2px var(--cpq-accent-cyan); }
.cre-card-head { display: flex; align-items: center; gap: 6px; }
.cre-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.cre-name { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cre-card-body { margin-top: 6px; display: flex; flex-direction: column; gap: 3px; }
.cre-line { font-size: 12.5px; color: var(--cpq-text-primary); line-height: 1.4; }
.cre-lbl { font-weight: 600; margin-right: 6px; }
.cre-desc { font-size: 12px; color: var(--cpq-text-muted); margin-top: 2px; }
.cre-card-foot { display: flex; justify-content: flex-end; gap: 2px; margin-top: 6px; }
.cre-card.active .cre-card-foot .ant-btn:first-child { color: var(--cpq-accent-cyan); }
.cre-cond-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }

/* 规则试跑 */
.cre-trial {
  margin-top: 4px; padding: 12px 14px; border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, .4));
  border: 1px solid var(--cpq-overlay-a15, rgba(0, 0, 0, .08));
}
.cre-trial-idle { display: flex; align-items: center; gap: 8px; color: var(--cpq-text-muted); font-size: 12px; }
.cre-trial-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.cre-trial-icon { color: var(--cpq-accent-cyan); flex: none; }
.cre-trial-title { font-weight: 600; color: var(--cpq-text-primary); font-size: 14px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cre-trial-sec { font-size: 12px; color: var(--cpq-text-secondary); margin: 8px 0 4px; }
.cre-trial-scen { display: flex; flex-direction: column; gap: 3px; }
.cre-trial-scenitem { font-size: 12px; color: var(--cpq-text-primary); font-family: monospace; }
.cre-trial-scenitem.skip { color: var(--cpq-text-muted); }
.cre-trial-empty { font-size: 12px; color: var(--cpq-text-muted); }
.cre-trial-result { display: flex; flex-direction: column; gap: 6px; }
.cre-trial-act { display: flex; flex-direction: column; padding: 6px 10px; border-radius: 8px; background: var(--cpq-overlay-w8, rgba(255, 255, 255, .6)); }
.cre-trial-act.sev-conflict { border-left: 3px solid var(--cpq-accent-danger); }
.cre-trial-act.sev-require { border-left: 3px solid var(--cpq-accent-primary); }
.cre-trial-act.sev-info { border-left: 3px solid var(--cpq-accent-cyan); }
.cre-trial-actdesc { font-size: 13px; color: var(--cpq-text-primary); }
.cre-trial-actrule { font-size: 11px; color: var(--cpq-text-muted); }
.cre-trial-note { font-size: 11px; color: var(--cpq-text-muted); margin-top: 8px; line-height: 1.5; }

/* 右栏拓扑 */
.cre-aside-head { display: flex; align-items: baseline; gap: 8px; padding: 0 2px; }
.cre-aside-title { font-weight: 600; color: var(--cpq-text-primary); font-size: 14px; }
.cre-aside-sub { font-size: 12px; color: var(--cpq-text-muted); }
.cre-aside-body { height: calc(100vh - 180px); min-height: 440px; }
.cre-aside-hint { font-size: 12px; color: var(--cpq-text-muted); padding: 0 2px; }
.cre-drawer-hint { font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.6; margin-bottom: 12px; }

/* 窄屏：右栏拓扑退到下方，卡片网格改单列 */
@media (max-width: 1260px) {
  .cre { flex-direction: column; }
  .cre-aside { position: static; width: 100%; }
  .cre-aside-body { height: 420px; }
}
@media (max-width: 720px) {
  .cre-list { grid-template-columns: 1fr; }
}
</style>
