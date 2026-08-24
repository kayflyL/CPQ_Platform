<template>
  <a-drawer
    :open="open"
    :title="editing ? '编辑规则' : '新建规则'"
    width="720"
    placement="right"
    @close="close"
  >
    <a-spin :spinning="saving">
      <a-form layout="vertical" class="red-form">
        <div class="red-grid">
          <a-form-item label="规则类型">
            <a-select
              :value="form.type"
              :options="RULE_TYPE_OPTIONS"
              :disabled="!!editing"
              @update:value="(v: any) => form.type = v"
            />
          </a-form-item>
          <a-form-item label="状态">
            <a-select v-model:value="form.status" :options="STATUS_OPTIONS" />
          </a-form-item>
        </div>

        <a-form-item label="规则名称">
          <a-input v-model:value="form.name" placeholder="给规则起一个可读的名称" />
        </a-form-item>

        <template v-if="form.type === 'clarity'">
          <div class="red-grid red-grid-3">
            <a-form-item label="判定等级">
              <a-select v-model:value="form.clarity.level" :options="CLARITY_LEVEL_OPTIONS" />
            </a-form-item>
            <a-form-item label="权重">
              <a-input-number v-model:value="form.clarity.weight" :min="0" :max="100" style="width: 100%" />
            </a-form-item>
            <a-form-item label="缺失字段">
              <a-select v-model:value="form.clarity.missing" mode="tags" placeholder="如：具体型号" />
            </a-form-item>
          </div>
          <a-form-item label="说明">
            <a-input v-model:value="form.clarity.explain" placeholder="例如：CPU 和 GPU 型号同时命中" />
          </a-form-item>
          <div class="red-section-title">命中条件（多条件为 AND）</div>
          <div v-for="(cond, idx) in form.clarity.conditions" :key="idx" class="red-cond-row">
            <a-select v-model:value="cond.type" :options="CLARITY_SIGNAL_OPTIONS" />
            <a-select v-if="condNeedsCategory(cond.type)" v-model:value="cond.category" :options="CATEGORY_OPTIONS" placeholder="品类" />
            <a-input-number v-if="condNeedsMin(cond.type)" v-model:value="cond.min" :min="0" style="width: 88px" />
            <template v-if="condNeedsOp(cond.type)">
              <a-select v-model:value="cond.op" :options="OP_OPTIONS" style="width: 72px" />
              <a-input-number v-model:value="cond.value" :min="0" style="width: 88px" />
            </template>
            <a-button type="text" danger size="small" @click="removeCondition(Number(idx))">删除</a-button>
          </div>
          <a-button size="small" block @click="addCondition">+ 添加条件</a-button>
        </template>

        <template v-else-if="form.type === 'budget'">
          <div class="red-grid red-grid-3">
            <a-form-item label="最低金额">
              <a-input-number v-model:value="form.budget.min" :min="0" style="width: 100%" placeholder="空 = 不限" />
            </a-form-item>
            <a-form-item label="最高金额">
              <a-input-number v-model:value="form.budget.max" :min="0" style="width: 100%" placeholder="空 = 不限" />
            </a-form-item>
            <a-form-item label="币种">
              <a-input v-model:value="form.budget.currency" />
            </a-form-item>
          </div>
          <div class="red-grid">
            <a-form-item label="代表件选择">
              <a-select v-model:value="form.budget.representative_pick" :options="REP_PICK_OPTIONS" />
            </a-form-item>
            <a-form-item label="策略标签">
              <a-input v-model:value="form.budget.label" />
            </a-form-item>
          </div>
        </template>

        <template v-else-if="form.type === 'cpu_mem_generation'">
          <div class="red-grid">
            <a-form-item label="CPU 匹配规则">
              <a-input v-model:value="form.cpuMem.pattern" placeholder="如：EPYC 9" />
            </a-form-item>
            <a-form-item label="内存代际">
              <a-select v-model:value="form.cpuMem.mem_type" :options="MEM_TYPE_OPTIONS" />
            </a-form-item>
          </div>
        </template>

        <template v-else-if="form.type === 'category_alias'">
          <a-form-item label="KP 品类键">
            <a-select v-model:value="form.categoryAlias.category" :options="CATEGORY_OPTIONS" />
          </a-form-item>
          <a-form-item label="别名">
            <a-select v-model:value="form.categoryAlias.aliases" mode="tags" placeholder="输入后回车" />
          </a-form-item>
        </template>

        <template v-else-if="form.type === 'platform_series_map'">
          <a-form-item label="产品系列">
            <a-input v-model:value="form.platform.series" placeholder="如：Orion / Polaris / Intel" />
          </a-form-item>
          <a-form-item label="关键词">
            <a-select v-model:value="form.platform.keywords" mode="tags" placeholder="如：epyc、amd" />
          </a-form-item>
          <a-form-item label="命中依据">
            <a-input v-model:value="form.platform.evidence" placeholder="例如：AMD/EPYC 平台" />
          </a-form-item>
        </template>

        <template v-else-if="form.type === 'type_package'">
          <div class="red-grid">
            <a-form-item label="机型关键词">
              <a-input v-model:value="form.typePackage.type_keyword" placeholder="如：AI / 存储 / 通用" />
            </a-form-item>
            <a-form-item label="标准品类">
              <a-select v-model:value="form.typePackage.categories" mode="multiple" :options="CATEGORY_OPTIONS" />
            </a-form-item>
          </div>
          <div class="red-grid">
            <a-form-item label="必须包含 GPU">
              <a-switch v-model:checked="form.typePackage.mandatory_gpu" />
            </a-form-item>
            <a-form-item label="必须包含存储">
              <a-switch v-model:checked="form.typePackage.mandatory_storage" />
            </a-form-item>
          </div>
        </template>

        <template v-else-if="form.type === 'spec_rule'">
          <div class="red-grid red-grid-3">
            <a-form-item label="品类">
              <a-select v-model:value="form.spec.category" :options="CATEGORY_OPTIONS" />
            </a-form-item>
            <a-form-item label="规格键">
              <a-input v-model:value="form.spec.spec_key" placeholder="Cores / Capacity" />
            </a-form-item>
            <a-form-item label="单位">
              <a-input v-model:value="form.spec.unit" placeholder="核 / GB" />
            </a-form-item>
          </div>
          <div class="red-grid">
            <a-form-item label="运算符">
              <a-select v-model:value="form.spec.op" :options="OP_OPTIONS" />
            </a-form-item>
            <a-form-item label="默认值">
              <a-input-number v-model:value="form.spec.value" :min="0" style="width: 100%" />
            </a-form-item>
          </div>
        </template>

        <template v-else-if="form.type === 'raid_level_map'">
          <div class="red-grid">
            <a-form-item label="RAID 级别">
              <a-input v-model:value="form.raid.level" placeholder="如：RAID 0,1,10" />
            </a-form-item>
            <a-form-item label="对应品类">
              <a-input v-model:value="form.raid.category" placeholder="如：Raid card" />
            </a-form-item>
          </div>
          <a-form-item label="优选型号">
            <a-select v-model:value="form.raid.prefer_models" mode="tags" placeholder="如：9560" />
          </a-form-item>
          <a-form-item label="依据">
            <a-input v-model:value="form.raid.evidence" />
          </a-form-item>
        </template>

        <template v-else-if="form.type === 'capacity_match'">
          <div class="red-grid">
            <a-form-item label="匹配策略">
              <a-input v-model:value="form.capacity.strategy" placeholder="如：tolerance" />
            </a-form-item>
            <a-form-item label="容差">
              <a-input-number v-model:value="form.capacity.tolerance" :min="0" style="width: 100%" />
            </a-form-item>
          </div>
          <a-form-item label="默认接口">
            <a-input v-model:value="form.capacity.default_interface" placeholder="如：SATA" />
          </a-form-item>
        </template>

        <template v-else-if="form.type === 'fallback_order'">
          <a-form-item label="放宽顺序（拖拽排序）">
            <draggable v-model="form.fallback.order" :item-key="orderKey" class="red-order-list">
              <template #item="{ element }">
                <div class="red-order-item">
                  <span>⠿ {{ element }}</span>
                </div>
              </template>
            </draggable>
          </a-form-item>
          <a-form-item label="无信号策略">
            <a-input v-model:value="form.fallback.no_signal_strategy" />
          </a-form-item>
        </template>

        <template v-else-if="form.type === 'check_rule'">
          <a-form-item label="自检项">
            <div class="red-check-list">
              <div v-for="c in CHECK_OPTIONS" :key="c.value" class="red-check-row">
                <span>{{ c.label }}</span>
                <a-switch v-model:checked="form.check.checks[c.value]" />
              </div>
            </div>
          </a-form-item>
          <a-form-item label="失败处理">
            <a-input v-model:value="form.check.on_fail" placeholder="如：mark" />
          </a-form-item>
        </template>

        <a-collapse ghost>
          <a-collapse-panel key="meta" header="备注与修改原因">
            <a-form-item label="规则说明">
              <a-textarea v-model:value="form.description" :rows="2" />
            </a-form-item>
            <a-form-item label="修改原因">
              <a-input v-model:value="form.change_reason" placeholder="本次变更说明" />
            </a-form-item>
          </a-collapse-panel>
          <a-collapse-panel key="json" header="高级 JSON 模式">
            <a-switch v-model:checked="advancedMode" checked-children="开" un-checked-children="关" size="small" />
            <a-textarea v-if="advancedMode" v-model:value="advancedJson" :rows="16" class="red-json" />
          </a-collapse-panel>
        </a-collapse>
      </a-form>
    </a-spin>

    <template #footer>
      <a-space>
        <a-button @click="close">取消</a-button>
        <a-button type="primary" :loading="saving" @click="submit">保存</a-button>
      </a-space>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import type { RequirementRule, RuleStatus, RuleType } from '@/api/requirementRules'
import { RULE_TYPE_OPTIONS, STATUS_OPTIONS } from './requirement-rule-meta'

const props = defineProps<{
  open: boolean
  editing: RequirementRule | null
  defaultType: RuleType
  saving: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
  (e: 'save', payload: Record<string, any>): void
}>()

const CLARITY_LEVEL_OPTIONS = [
  { value: 'explicit', label: 'explicit' },
  { value: 'partial', label: 'partial' },
  { value: 'unclear', label: 'unclear' },
]
const CLARITY_SIGNAL_OPTIONS = [
  { value: 'series_and_form', label: '已给系列+形态' },
  { value: 'no_series_no_form', label: '无系列无形态' },
  { value: 'has_budget', label: '已给预算' },
  { value: 'no_budget', label: '无预算' },
  { value: 'category_count', label: '品类数量' },
  { value: 'model_token_count', label: '型号 token 数量' },
  { value: 'model_token_in_category', label: '品类中有型号' },
  { value: 'no_model_in_category', label: '品类缺型号' },
  { value: 'has_memory_capacity', label: '已给内存容量' },
  { value: 'no_memory_capacity', label: '缺内存容量' },
  { value: 'has_usage', label: '已给用途' },
]
const CATEGORY_OPTIONS = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC', 'Raid card', 'Power', 'Fan', 'Heatsink', 'Cable', 'Rail', 'Backplane'].map(c => ({ value: c, label: c }))
const OP_OPTIONS = ['>=', '<=', '==', '>', '<'].map(v => ({ value: v, label: v }))
const MEM_TYPE_OPTIONS = ['DDR4', 'DDR5'].map(v => ({ value: v, label: v }))
const REP_PICK_OPTIONS = [
  { value: 'min_price', label: 'min_price' },
  { value: 'max_price', label: 'max_price' },
]
const CHECK_OPTIONS = [
  { value: 'plan_not_empty', label: '方案不能为空' },
  { value: 'required_fields', label: '必填字段完整' },
  { value: 'qty_reasonable', label: '数量合理' },
]

const advancedMode = ref(false)
const advancedJson = ref('{}')
const form = reactive<Record<string, any>>({
  type: props.defaultType,
  name: '',
  status: 'active' as RuleStatus,
  description: '',
  change_reason: '',
  clarity: { level: 'partial', weight: 50, explain: '', missing: [], conditions: [emptyCondition()] },
  budget: { min: null, max: null, currency: 'CNY', representative_pick: 'min_price', label: '' },
  cpuMem: { pattern: '', mem_type: 'DDR5' },
  categoryAlias: { category: 'CPU', aliases: [] },
  platform: { series: '', keywords: [], evidence: '' },
  typePackage: { type_keyword: '', categories: [], mandatory_gpu: false, mandatory_storage: false },
  spec: { category: 'CPU', spec_key: '', op: '>=', value: 0, unit: '' },
  raid: { level: '', category: 'Raid card', prefer_models: [], evidence: '' },
  capacity: { strategy: 'tolerance', tolerance: 10, default_interface: '' },
  fallback: { order: ['exact', 'same_series', 'same_form', 'all'], no_signal_strategy: 'return_empty' },
  check: { checks: { plan_not_empty: true, required_fields: true, qty_reasonable: true }, on_fail: 'mark' },
})

function emptyCondition() {
  return { type: 'series_and_form', category: 'CPU', op: '>=', value: 1, min: 1 }
}

function orderKey(item: string) {
  return item
}

function condNeedsCategory(type: string) {
  return type === 'no_model_in_category' || type === 'model_token_in_category'
}

function condNeedsOp(type: string) {
  return type === 'category_count' || type === 'model_token_count'
}

function condNeedsMin(type: string) {
  return type === 'model_token_in_category'
}

function addCondition() {
  form.clarity.conditions.push(emptyCondition())
}

function removeCondition(idx: number) {
  if (form.clarity.conditions.length === 1) return
  form.clarity.conditions.splice(idx, 1)
}

function resetForm() {
  Object.assign(form, {
    type: props.defaultType,
    name: '',
    status: 'active',
    description: '',
    change_reason: '',
    clarity: { level: 'partial', weight: 50, explain: '', missing: [], conditions: [emptyCondition()] },
    budget: { min: null, max: null, currency: 'CNY', representative_pick: 'min_price', label: '' },
    cpuMem: { pattern: '', mem_type: 'DDR5' },
    categoryAlias: { category: 'CPU', aliases: [] },
    platform: { series: '', keywords: [], evidence: '' },
    typePackage: { type_keyword: '', categories: [], mandatory_gpu: false, mandatory_storage: false },
    spec: { category: 'CPU', spec_key: '', op: '>=', value: 0, unit: '' },
    raid: { level: '', category: 'Raid card', prefer_models: [], evidence: '' },
    capacity: { strategy: 'tolerance', tolerance: 10, default_interface: '' },
    fallback: { order: ['exact', 'same_series', 'same_form', 'all'], no_signal_strategy: 'return_empty' },
    check: { checks: { plan_not_empty: true, required_fields: true, qty_reasonable: true }, on_fail: 'mark' },
  })
}

function signalToConditions(signal: any) {
  const rules = signal?.type === 'combined' && Array.isArray(signal.rules) ? signal.rules : [signal]
  return rules.map((c: any) => ({
    type: c?.type || 'series_and_form',
    category: c?.category || 'CPU',
    op: c?.op || '>=',
    value: c?.value ?? 1,
    min: c?.min ?? 1,
  }))
}

function applyEditing() {
  const r = props.editing
  if (!r) return
  const b = r.body || {}
  form.type = r.type
  form.name = r.name
  form.status = r.status
  form.description = r.description || ''
  form.change_reason = r.change_reason || ''
  form.clarity = {
    level: b.level || 'partial',
    weight: b.weight ?? 50,
    explain: b.explain || '',
    missing: Array.isArray(b.missing_if_not) ? b.missing_if_not : [],
    conditions: signalToConditions(b.signal),
  }
  form.budget = {
    min: b.range?.min ?? null,
    max: b.range?.max ?? null,
    currency: b.range?.currency || 'CNY',
    representative_pick: b.strategy?.representative_pick || 'min_price',
    label: b.strategy?.label || '',
  }
  form.cpuMem = { pattern: b.pattern || '', mem_type: b.mem_type || 'DDR5' }
  form.categoryAlias = { category: b.category || 'CPU', aliases: Array.isArray(b.aliases) ? b.aliases : [] }
  form.platform = { series: b.series || '', keywords: Array.isArray(b.keywords) ? b.keywords : [], evidence: b.evidence || '' }
  form.typePackage = {
    type_keyword: b.type_keyword || '',
    categories: Array.isArray(b.categories) ? b.categories : [],
    mandatory_gpu: !!b.mandatory_gpu,
    mandatory_storage: !!b.mandatory_storage,
  }
  form.spec = { category: b.category || 'CPU', spec_key: b.spec_key || '', op: b.op || '>=', value: b.value ?? 0, unit: b.unit || '' }
  form.raid = { level: b.level || '', category: b.category || 'Raid card', prefer_models: Array.isArray(b.prefer_models) ? b.prefer_models : [], evidence: b.evidence || '' }
  form.capacity = { strategy: b.strategy || 'tolerance', tolerance: b.tolerance ?? 10, default_interface: b.default_interface || '' }
  form.fallback = { order: Array.isArray(b.order) ? b.order : ['exact', 'same_series', 'same_form', 'all'], no_signal_strategy: b.no_signal_strategy || 'return_empty' }
  form.check = { checks: { ...(b.checks || {}) }, on_fail: b.on_fail || 'mark' }
}

// 有专属表单编辑器的类型（buildBody 支持）；其余类型（厂商映射/单位正则/功耗校准/意图词等）
// 走「高级 JSON」模式编辑，避免把已有 body 覆盖成空对象。
const FORM_EDITABLE_TYPES = new Set<RuleType>([
  'clarity', 'budget', 'cpu_mem_generation', 'category_alias', 'platform_series_map',
  'type_package', 'spec_rule', 'raid_level_map', 'capacity_match', 'fallback_order', 'check_rule',
])

watch(() => props.open, (open) => {
  if (!open) return
  advancedMode.value = false
  if (props.editing) applyEditing()
  else resetForm()
  const t = (props.editing?.type || form.type) as RuleType
  if (!FORM_EDITABLE_TYPES.has(t)) {
    advancedMode.value = true
    advancedJson.value = JSON.stringify(props.editing?.body || {}, null, 2)
  } else {
    advancedJson.value = JSON.stringify(buildBody(), null, 2)
  }
})

watch(advancedMode, (on) => {
  if (on) advancedJson.value = JSON.stringify(buildBody(), null, 2)
})

function conditionToBody(c: any) {
  const out: Record<string, any> = { type: c.type }
  if (condNeedsCategory(c.type) && c.category) out.category = c.category
  if (condNeedsMin(c.type)) out.min = Number(c.min) || 1
  if (condNeedsOp(c.type)) {
    out.op = c.op
    out.value = Number(c.value) || 0
  }
  if (['has_budget', 'has_memory_capacity', 'has_usage'].includes(c.type)) out.value = true
  return out
}

function buildBody() {
  const t = form.type as RuleType
  if (t === 'clarity') {
    const conditions = form.clarity.conditions.map(conditionToBody)
    return {
      level: form.clarity.level,
      weight: Number(form.clarity.weight) || 0,
      explain: form.clarity.explain,
      missing_if_not: form.clarity.missing,
      signal: conditions.length === 1 ? conditions[0] : { type: 'combined', rules: conditions },
    }
  }
  if (t === 'budget') {
    return {
      range: { min: form.budget.min, max: form.budget.max, currency: form.budget.currency },
      strategy: { representative_pick: form.budget.representative_pick, label: form.budget.label },
    }
  }
  if (t === 'cpu_mem_generation') return form.cpuMem
  if (t === 'category_alias') return form.categoryAlias
  if (t === 'platform_series_map') return form.platform
  if (t === 'type_package') return form.typePackage
  if (t === 'spec_rule') return form.spec
  if (t === 'raid_level_map') return form.raid
  if (t === 'capacity_match') return form.capacity
  if (t === 'fallback_order') return form.fallback
  if (t === 'check_rule') return form.check
  return {}
}

function submit() {
  if (!form.name.trim()) {
    emit('save', { error: '请填写规则名称' })
    return
  }
  let body: any
  if (advancedMode.value) {
    try {
      body = JSON.parse(advancedJson.value || '{}')
    } catch (e: any) {
      emit('save', { error: `高级 JSON 无效：${e.message}` })
      return
    }
  } else {
    body = buildBody()
  }
  emit('save', {
    id: props.editing?.id,
    type: form.type,
    name: form.name.trim(),
    status: form.status,
    description: form.description || undefined,
    change_reason: form.change_reason || undefined,
    body,
  })
}

function close() {
  emit('update:open', false)
  emit('close')
}
</script>

<style scoped>
.red-form { min-height: 60vh; }
.red-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.red-grid-3 { grid-template-columns: repeat(3, 1fr); }
.red-section-title { margin: 14px 0 6px; font-size: 12px; font-weight: 600; color: var(--cpq-text-secondary); }
.red-cond-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.red-order-list { display: flex; flex-direction: column; gap: 6px; }
.red-order-item { padding: 8px 10px; border: 1px solid var(--cpq-border-primary); border-radius: 8px; background: var(--cpq-glass-1-bg); cursor: move; }
.red-check-list { display: flex; flex-direction: column; gap: 8px; }
.red-check-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border: 1px solid var(--cpq-border-primary); border-radius: 8px; background: var(--cpq-glass-1-bg); }
.red-json { font-family: ui-monospace, monospace; font-size: 12px; }
</style>
