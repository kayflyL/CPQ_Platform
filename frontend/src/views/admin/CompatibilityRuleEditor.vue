<script setup lang="ts">
/**
 * 兼容性规则引擎编辑器（取代旧 X6 选型画布 SelectionStrategyCanvas）。
 * 声明式 WHEN(条件)→THEN(动作) 规则：两态切换——列表态（卡片网格）↔ 展开态（左构建器右拓扑）。
 * body: { when:{all?:[cond], any?:[cond]} | cond, then:{action,...}, desc }
 */
import { ref, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, EditOutlined, PoweroffOutlined, ThunderboltOutlined,
  SaveOutlined, CloseOutlined,
} from '@ant-design/icons-vue'
import { compatibilityRulesApi, type CompatibilityRule } from '@/api/compatibilityRules'
import CompatibilityImpactGraph from './CompatibilityImpactGraph.vue'
import { useSelectionRulesStore } from '@/stores/selectionRules'
import { evaluateRules, type RuleContext } from '@/stores/selectionEngine'
import { kpPartsApi } from '@/api/serverConfig'
import {
  RULE_TYPE_MAP, RULE_TYPE_OPTIONS, RULE_OP_OPTIONS, RULE_OP_MAP,
  RULE_GRAPH_TEXT as T, excludeText,
} from '@/constants/ruleMeta'

// 改规则后让消费端（工作台 / 配置向导）缓存的规则失效重拉，做到「改完即时生效」
const selectionRulesStore = useSelectionRulesStore()
// 规则类型 / 操作符 / 字段 / 拓扑文案 均来自 @/constants/ruleMeta（SSOT，与拓扑图共用）

const rules = ref<CompatibilityRule[]>([])
const loading = ref(false)
const filtered = computed(() => rules.value)

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
    name: '', type: 'derive', status: 'active',
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
    name: r.name, type: r.type, status: r.status, whenAll,
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
  saving.value = true
  try {
    if (!isNew.value && editing.value?.id) {
      await compatibilityRulesApi.update(editing.value.id, { name: f.name, body, status: f.status })
    } else {
      await compatibilityRulesApi.create({ type: f.type, name: f.name, body, status: f.status })
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

function whenText(b: any): string {
  const w = b?.when
  if (!w || (!w.all && !w.any && !w.field)) return T.alwaysActive
  if (w.field) return `${w.field} ${w.op} ${w.value}`
  if (Array.isArray(w.all)) return w.all.map((c: any) => `${c.field} ${c.op} ${c.value}`).join(` ${T.logicAll} `)
  if (Array.isArray(w.any)) return w.any.map((c: any) => `${c.field} ${c.op} ${c.value}`).join(` ${T.logicAny} `)
  return T.alwaysActive
}
function thenText(b: any): string {
  const t = b?.then
  if (!t) return ''
  if (t.action === 'require') return `${T.requirePrefix} ${t.target}${t.min_qty ? `（${RULE_OP_MAP['>=']}${t.min_qty}）` : ''}${t.spec_constraint ? ` ${T.specLabel}${Object.entries(t.spec_constraint).map(([k,v])=>`${k}${T.eq}${v}`).join(',')}` : ''}`
  if (t.action === 'exclude') return `${t.target} ${excludeText(t.unique_field)}`
  if (t.action === 'derive') {
    if (t.field && 'value' in t) return `${T.assignLabel} ${t.field} ${T.eq} ${t.value}`
    return `${T.deriveLabel} ${t.target} ${T.eq} ${t.basis}${T.divideBy}${t.per}（${T.round[t.round] || ''}）`
  }
  if (t.action === 'filter') return `${t.scope}.${t.field} ${t.op} ${t.value}`
  if (t.action === 'recommend') return `${T.recommendLabel} ${t.target}`
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
    <!-- ═══════════ 列表态：规则卡片网格 + 规则试跑（常驻） ═══════════ -->
    <div class="cre-main">
        <div class="cre-head">
          <span class="cre-hint">声明式兼容性规则 · WHEN 条件 → THEN 动作 · 选配时实时校验</span>
          <a-space>
            <a-button size="small" @click="resetDefaults">重置默认</a-button>
            <a-button type="primary" size="small" @click="openNew">+ 新建规则</a-button>
          </a-space>
        </div>

        <a-spin :spinning="loading">
          <div v-if="filtered.length" class="cre-list">
            <div v-for="r in filtered" :key="r.id"
              class="cre-card glass-light"
              :class="{ archived: r.status !== 'active', active: trialRuleId === r.id }"
              :style="{ '--ctype': RULE_TYPE_MAP[r.type]?.cssVar || RULE_TYPE_MAP.require.cssVar }"
              @click="openEdit(r)">
              <div class="cre-card-head">
                <span class="cre-dot" :class="r.status === 'active' ? 'on' : 'off'"
                  :title="r.status === 'active' ? '生效中' : '已停用'"></span>
                <span class="cre-name">{{ r.name }}</span>
                <a-tag class="cre-type-tag" :color="RULE_TYPE_MAP[r.type]?.cssVar" size="small">{{ RULE_TYPE_MAP[r.type]?.label }}</a-tag>
              </div>
              <div class="cre-card-logic">
                <p class="cre-line"><em class="ck when">当</em><span>{{ whenText(r.body) }}</span></p>
                <p class="cre-line"><em class="ck then">则</em><span>{{ thenText(r.body) }}</span></p>
              </div>
              <div v-if="r.body?.desc" class="cre-desc" :title="r.body.desc">{{ r.body.desc }}</div>
              <div class="cre-card-foot" @click.stop>
                <a-tooltip title="试跑此规则"><a-button size="small" type="text" @click="toggleTrial(r)"><ThunderboltOutlined /></a-button></a-tooltip>
                <a-tooltip :title="r.status === 'active' ? '停用' : '启用'"><a-button size="small" type="text" @click="toggleStatus(r)"><PoweroffOutlined /></a-button></a-tooltip>
                <a-tooltip title="编辑"><a-button size="small" type="text" @click="openEdit(r)"><EditOutlined /></a-button></a-tooltip>
                <a-tooltip title="删除"><a-button size="small" type="text" danger @click="remove(r)"><DeleteOutlined /></a-button></a-tooltip>
              </div>
            </div>
          </div>
          <a-empty v-else description="暂无此类规则，点「新建规则」添加" />
        </a-spin>

        <!-- 规则试跑 -->
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

    <!-- ═══════════ 编辑弹窗：左构建器 + 右单规则拓扑 ═══════════ -->
    <a-modal v-model:open="editModalVisible" :title="isNew ? '新建规则' : '编辑规则'"
      width="1180px" :footer="null" :mask-closable="false" wrap-class-name="cre-edit-modal" @cancel="closeEdit">
      <div class="cre-edit-grid">
        <div class="cre-edit-form glass-light">
          <a-form layout="vertical" size="small">
            <a-row :gutter="16">
              <a-col :span="16">
                <a-form-item label="规则名称">
                  <a-input v-model:value="form.name" placeholder="如：选 GPU 需配 GPU 线缆" />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="规则类型">
                  <a-select v-model:value="form.type" :options="RULE_TYPE_OPTIONS" />
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
        <div class="cre-edit-graph">
          <div class="cre-edit-graph-title"><span class="ceg-name">规则拓扑</span><span class="ceg-sub">{{ form.name || '新规则' }}</span></div>
          <div class="cre-edit-graph-body"><CompatibilityImpactGraph :rules="editing ? [editing] : []" /></div>
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
/* 单栏：操作栏 + 卡片网格 + 试跑（编辑走弹窗） */
.cre { display: flex; flex-direction: column; gap: 12px; }
.cre-main { display: flex; flex-direction: column; gap: 12px; }
.cre-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cre-hint { color: var(--cpq-text-secondary); font-size: 12px; }

/* 规则卡片：自适应紧凑网格，类型色左边条 + 右上角类型标签 */
.cre-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }
.cre-card {
  position: relative; padding: 12px 14px; border-radius: var(--cpq-radius-md, 14px);
  display: flex; flex-direction: column; gap: 8px; cursor: pointer;
  border-left: 3px solid var(--ctype);
  transition: transform .15s ease, box-shadow .15s ease;
}
.cre-card:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(0,0,0,.09); }
.cre-card.archived { opacity: .55; }
.cre-card.active { box-shadow: 0 0 0 2px var(--cpq-accent-cyan); }
.cre-card-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cre-dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.cre-dot.on { background: var(--cpq-color-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cpq-color-success) 22%, transparent); }
.cre-dot.off { background: var(--cpq-text-muted); }
.cre-name { font-weight: 600; font-size: 14px; color: var(--cpq-text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cre-type-tag { margin: 0; flex: none; }
.cre-card-logic { display: flex; flex-direction: column; gap: 4px; }
.cre-line { display: flex; align-items: flex-start; gap: 6px; margin: 0; font-size: 12.5px; line-height: 1.45; color: var(--cpq-text-primary); }
.cre-line .ck { font-style: normal; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 5px; flex: none; margin-top: 2px; }
.cre-line .ck.when { color: var(--cpq-accent-primary); background: color-mix(in srgb, var(--cpq-accent-primary) 14%, transparent); }
.cre-line .ck.then { color: var(--cpq-accent-cyan); background: color-mix(in srgb, var(--cpq-accent-cyan) 16%, transparent); }
.cre-line span { min-width: 0; word-break: break-word; }
.cre-desc { font-size: 11.5px; color: var(--cpq-text-muted); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.cre-card-foot { display: flex; justify-content: flex-end; gap: 2px; margin-top: 2px; padding-top: 6px; border-top: 1px dashed var(--cpq-overlay-a15, rgba(0,0,0,.08)); opacity: .65; transition: opacity .15s; }
.cre-card:hover .cre-card-foot { opacity: 1; }
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

/* ── 编辑弹窗：左构建器 + 右单规则拓扑 ── */
.cre-edit-grid { display: grid; grid-template-columns: minmax(0, 1fr) 470px; gap: 16px; height: min(620px, 66vh); }
.cre-edit-form { padding: 18px 22px; border-radius: 12px; overflow-y: auto; }
.cre-edit-graph { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.cre-edit-graph-title { display: flex; align-items: baseline; gap: 8px; padding: 0 2px; }
.ceg-name { font-weight: 600; font-size: 14px; color: var(--cpq-text-primary); }
.ceg-sub { font-size: 12px; color: var(--cpq-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cre-edit-graph-body { flex: 1; min-height: 0; }
.cre-edit-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

@media (max-width: 980px) {
  .cre-edit-grid { grid-template-columns: 1fr; height: auto; }
  .cre-edit-graph-body { height: 380px; }
}
@media (max-width: 560px) {
  .cre-list { grid-template-columns: 1fr; }
}
</style>
