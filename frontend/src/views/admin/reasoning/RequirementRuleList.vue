<script setup lang="ts">
/** RequirementRuleList — 需求分析规则库统一编辑器（抽屉 A/B/C 分区共用）。
 *  按 ruleType 渲染列表 + 编辑 modal：
 *  - clarity：明确度判定（signal JSON + level/weight/missing）
 *  - budget：预算映射（min/max/representative_pick/label）
 *  （旧 rebuttal/workload 已随目录驱动引导删除）
 *  规则存 requirement_rules 表（独立 CRUD，实时生效，非 node_config）。 */
import { ref, watch, computed } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import ChipListInput from './ChipListInput.vue'
import { requirementRulesApi, type RequirementRule, type RuleType } from '@/api/requirementRules'

const props = defineProps<{ ruleType: RuleType }>()
const emit = defineEmits<{ changed: [] }>()

const rules = ref<RequirementRule[]>([])
const loading = ref(false)
const showEditor = ref(false)
const editing = ref<RequirementRule | null>(null)  // null=新增
const saving = ref(false)
const form = ref<any>({})
// clarity signal 结构化编辑（替代裸 JSON textarea，用户友好）
const SIGNAL_TYPES: { value: string; label: string; hint?: string }[] = [
  { value: 'series_and_form', label: '有系列且有形态' },
  { value: 'no_series_no_form', label: '无系列且无形态' },
  { value: 'has_usage', label: '有用途' },
  { value: 'no_usage', label: '无用途' },
  { value: 'has_budget', label: '有预算' },
  { value: 'no_budget', label: '无预算' },
  { value: 'category_count', label: '配件品类数 ≥/≤ N', hint: '用户提到了几类配件，如 CPU+GPU = 2 类' },
  { value: 'model_token_count', label: '具体型号数 ≥/≤ N', hint: '用户提到了几个具体型号，如 EPYC9354、RTX4090' },
  { value: 'model_token_in_category', label: '提到了某品类的具体型号', hint: '如 CPU 的 EPYC9354、GPU 的 RTX4090。下方填该品类 + 至少几个' },
  { value: 'no_model_in_category', label: '提到某品类却无该品类型号', hint: '如说了"CPU/GPU"但没给具体型号，适合追问型号。下方填品类' },
  { value: 'has_memory_capacity', label: '有内存容量' },
  { value: 'no_memory_capacity', label: '无内存容量' },
  { value: 'combined', label: '组合条件（全部满足）' },
]
const SUB_SIGNAL_TYPES = SIGNAL_TYPES.filter((t) => t.value !== 'combined')
const curSignalHint = computed(() => SIGNAL_TYPES.find((x) => x.value === signalForm.value.type)?.hint || '')
const signalForm = ref<any>({
  type: 'series_and_form', op: '>=', value: 1, category: 'CPU', min: 1, rules: [],
})
function parseSignal(sig: any) {
  const s = sig || {}
  signalForm.value = {
    type: s.type || 'series_and_form',
    op: s.op || '>=', value: s.value ?? 1,
    category: s.category || 'CPU', min: s.min ?? 1,
    rules: Array.isArray(s.rules) ? s.rules.map((r: any) => ({
      type: r.type || 'series_and_form', op: r.op || '>=',
      value: r.value ?? 1, category: r.category || 'CPU', min: r.min ?? 1,
    })) : [],
  }
}
function _buildLeaf(s: any): any {
  if (s.type === 'category_count' || s.type === 'model_token_count') return { type: s.type, op: s.op || '>=', value: +s.value || 0 }
  if (s.type === 'model_token_in_category') return { type: s.type, category: s.category || 'CPU', min: +s.min || 1 }
  if (s.type === 'no_model_in_category') return { type: s.type, category: s.category || 'CPU' }
  return { type: s.type }
}
function buildSignal(): any {
  const s = signalForm.value
  if (s.type === 'combined') return { type: 'combined', rules: s.rules.map((r: any) => _buildLeaf(r)) }
  return _buildLeaf(s)
}
function addSubRule() {
  signalForm.value.rules.push({ type: 'series_and_form', op: '>=', value: 1, category: 'CPU', min: 1 })
}
async function resetDefaults() {
  Modal.confirm({
    title: '重置为默认规则？',
    content: '将清空当前所有规则（含命中计数），恢复到系统默认 seed。',
    okText: '重置', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      try {
        await requirementRulesApi.reset()
        message.success('已重置为默认规则')
        emit('changed')
        load()
      } catch (e: any) { message.error(e.response?.data?.detail || '重置失败') }
    },
  })
}

const typeLabel = computed(() => ({ clarity: '明确度判定', budget: '预算映射' }[props.ruleType]))

async function load() {
  loading.value = true
  try {
    const r = await requirementRulesApi.list({ type: props.ruleType, status: 'active' })
    rules.value = r.rules || []
  } catch {
    rules.value = []
  } finally {
    loading.value = false
  }
}
watch(() => props.ruleType, load, { immediate: true })

function blankForm(): any {
  if (props.ruleType === 'clarity') return { name: '', level: 'partial', weight: 50, missing_if_not: [] }
  return { name: '', min: null, max: null, representative_pick: 'min_price', label: '' }
}

function startAdd() {
  editing.value = null
  form.value = blankForm()
  if (props.ruleType === 'clarity') parseSignal({ type: 'series_and_form' })
  showEditor.value = true
}

function startEdit(r: RequirementRule) {
  editing.value = r
  const b = r.body || {}
  if (props.ruleType === 'clarity') {
    form.value = { name: r.name, level: b.level || 'partial', weight: b.weight ?? 50, missing_if_not: b.missing_if_not || [] }
    parseSignal(b.signal)
  } else {
    const rng = b.range || {}
    const st = b.strategy || {}
    form.value = { name: r.name, min: rng.min ?? null, max: rng.max ?? null, representative_pick: st.representative_pick || 'min_price', label: st.label || '' }
  }
  showEditor.value = true
}

async function saveRule() {
  const f = form.value
  if (!f.name?.trim()) { message.warning('请填规则名称'); return }
  let body: any
  if (props.ruleType === 'clarity') {
    const signal = buildSignal()
    body = { signal, level: f.level, weight: +f.weight || 0, missing_if_not: f.missing_if_not || [], explain: f.name }
  } else {
    body = {
      range: { min: f.min != null && f.min !== '' ? +f.min : null, max: f.max != null && f.max !== '' ? +f.max : null, currency: 'CNY' },
      strategy: { representative_pick: f.representative_pick, label: f.label || f.name },
    }
  }
  saving.value = true
  try {
    if (editing.value) {
      await requirementRulesApi.update(editing.value.id, { name: f.name, body })
    } else {
      await requirementRulesApi.create({ type: props.ruleType, name: f.name, body, status: 'active' })
    }
    message.success('已保存（下次推理生效）')
    showEditor.value = false
    emit('changed')
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function removeRule(r: RequirementRule) {
  Modal.confirm({
    title: '删除规则？', content: r.name, okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      try {
        await requirementRulesApi.remove(r.id)
        message.success('已删除')
        emit('changed')
        load()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}
</script>

<template>
  <div class="rl-wrap">
    <div v-if="loading" class="rl-empty">加载中…</div>
    <div v-else-if="!rules.length" class="rl-empty">暂无{{ typeLabel }}规则，点下方添加</div>
    <div v-for="r in rules" :key="r.id" class="rl-row glass-light">
      <div class="rl-main">
        <div class="rl-head">
          <span class="rl-name">{{ r.name }}</span>
          <span v-if="ruleType === 'clarity'" class="rl-lvl" :class="`lvl-${r.body?.level}`">{{ r.body?.level }}</span>
          <span v-if="ruleType === 'budget'" class="rl-pick">{{ r.body?.strategy?.representative_pick }}</span>
          <span v-if="r.hit_count" class="rl-hit">命中 {{ r.hit_count }} 次</span>
        </div>
        <div class="rl-desc">
          <template v-if="ruleType === 'clarity'">权重 {{ r.body?.weight }} · 缺：{{ (r.body?.missing_if_not || []).join('、') || '—' }}</template>
          <template v-else>{{ r.body?.range?.min ?? '−' }} ~ {{ r.body?.range?.max ?? '∞' }} · {{ r.body?.strategy?.label }}</template>
        </div>
      </div>
      <div class="rl-actions">
        <a-button type="text" size="small" @click="startEdit(r)"><EditOutlined /></a-button>
        <a-button type="text" size="small" danger @click="removeRule(r)"><DeleteOutlined /></a-button>
      </div>
    </div>
    <div class="rl-bar">
      <a-button type="dashed" size="small" class="rl-add" @click="startAdd">
        <PlusOutlined /> 添加{{ typeLabel }}规则
      </a-button>
      <a-button size="small" type="text" danger @click="resetDefaults"><ReloadOutlined /> 重置默认</a-button>
    </div>

    <a-modal
      :open="showEditor"
      :title="(editing ? '编辑' : '新增') + typeLabel + '规则'"
      width="560"
      @cancel="showEditor = false"
      :footer="null"
    >
      <a-form layout="vertical">
        <a-form-item label="规则名称"><a-input v-model:value="form.name" placeholder="如：CPU+GPU 型号双命中" /></a-form-item>

        <template v-if="ruleType === 'clarity'">
          <a-form-item label="明确度等级（命中时判定为）">
            <a-radio-group v-model:value="form.level">
              <a-radio value="explicit">明确</a-radio>
              <a-radio value="partial">部分明确</a-radio>
              <a-radio value="unclear">不明确</a-radio>
            </a-radio-group>
          </a-form-item>
          <a-form-item label="权重（多条命中时排序用）"><a-input-number v-model:value="form.weight" :min="0" :max="200" style="width:100%" /></a-form-item>
          <a-form-item label="命中条件">
            <p class="rl-hint">选一个条件类型，需求满足时这条规则命中。</p>
            <a-select v-model:value="signalForm.type" style="width:100%">
              <a-select-option v-for="t in SIGNAL_TYPES" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
            </a-select>
            <p v-if="curSignalHint" class="rl-hint" style="margin-top:4px">{{ curSignalHint }}</p>
            <a-input-group v-if="['category_count','model_token_count'].includes(signalForm.type)" compact style="margin-top:8px">
              <a-select v-model:value="signalForm.op" style="width:30%">
                <a-select-option value=">=">≥</a-select-option>
                <a-select-option value=">">＞</a-select-option>
                <a-select-option value="<=">≤</a-select-option>
                <a-select-option value="<">＜</a-select-option>
              </a-select>
              <a-input-number v-model:value="signalForm.value" :min="0" style="width:70%" />
            </a-input-group>
            <div v-if="signalForm.type === 'model_token_in_category'" style="display:flex; gap:8px; margin-top:8px">
              <a-input v-model:value="signalForm.category" placeholder="品类如 CPU" style="flex:1" />
              <a-input-number v-model:value="signalForm.min" :min="1" style="width:140px"><template #addonBefore>≥</template></a-input-number>
            </div>
            <template v-if="signalForm.type === 'combined'">
              <p class="rl-hint" style="margin-top:8px">以下条件<b>全部满足</b>时命中：</p>
              <div v-for="(r, i) in signalForm.rules" :key="i" class="rl-sub">
                <a-select v-model:value="r.type" size="small" style="flex:1">
                  <a-select-option v-for="t in SUB_SIGNAL_TYPES" :key="t.value" :value="t.value">{{ t.label }}</a-select-option>
                </a-select>
                <template v-if="['category_count','model_token_count'].includes(r.type)">
                  <a-select v-model:value="r.op" size="small" style="width:50px">
                    <a-select-option value=">=">≥</a-select-option>
                    <a-select-option value="<=">≤</a-select-option>
                  </a-select>
                  <a-input-number v-model:value="r.value" :min="0" size="small" style="width:70px" />
                </template>
                <a-input v-if="r.type === 'model_token_in_category'" v-model:value="r.category" size="small" placeholder="CPU" style="width:90px" />
                <a-button type="text" size="small" danger @click="signalForm.rules.splice(i, 1)"><DeleteOutlined /></a-button>
              </div>
              <a-button size="small" type="dashed" block @click="addSubRule"><PlusOutlined /> 添加子条件</a-button>
            </template>
          </a-form-item>
          <a-form-item label="缺失字段（命中时计入 missing_fields，供反问）">
            <ChipListInput v-model="form.missing_if_not" placeholder="如 具体型号、预算" />
          </a-form-item>
        </template>

        <template v-else>
          <a-form-item label="预算区间（元，留空=开区间）">
            <a-input-group compact>
              <a-input-number v-model:value="form.min" placeholder="min" style="width:45%" />
              <a-input style="width:10%; text-align:center" placeholder="~" disabled />
              <a-input-number v-model:value="form.max" placeholder="max" style="width:45%" />
            </a-input-group>
          </a-form-item>
          <a-form-item label="选件策略">
            <a-radio-group v-model:value="form.representative_pick">
              <a-radio value="min_price">取低价</a-radio>
              <a-radio value="max_price">取高价</a-radio>
            </a-radio-group>
          </a-form-item>
          <a-form-item label="档次标签"><a-input v-model:value="form.label" placeholder="如：高性能" /></a-form-item>
        </template>
      </a-form>
      <div class="rl-modal-footer">
        <a-button style="margin-right:8px" @click="showEditor = false">取消</a-button>
        <a-button type="primary" :loading="saving" @click="saveRule">保存</a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.rl-wrap { display: flex; flex-direction: column; gap: 8px; }
.rl-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 12px; text-align: center; }
.rl-row {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: var(--cpq-radius-sm, 8px);
}
.rl-main { flex: 1; min-width: 0; }
.rl-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rl-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.rl-lvl, .rl-pick {
  font-size: 11px; padding: 0 6px; border-radius: 6px;
  background: var(--cpq-overlay-w8); color: var(--cpq-accent-primary);
}
.rl-lvl.lvl-explicit { color: var(--cpq-accent-success, #52c41a); }
.rl-lvl.lvl-unclear { color: var(--cpq-accent-warning, #faad14); }
.rl-hit { font-size: 11px; color: var(--cpq-text-muted); margin-left: auto; }
.rl-desc { font-size: 12px; color: var(--cpq-text-secondary); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rl-actions { flex: 0 0 auto; display: flex; gap: 2px; }
.rl-bar { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.rl-bar .rl-add { flex: 1; }
.rl-sub { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
.rl-hint { font-size: 11px; color: var(--cpq-text-muted); margin: 2px 0 6px; }
.rl-json { font-family: ui-monospace, monospace; font-size: 12px; }
.rl-modal-footer { text-align: right; margin-top: 16px; }
</style>
