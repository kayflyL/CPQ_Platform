<script setup lang="ts">
/** 推理流节点配置抽屉 —— 按 node.type 渲染参数表单。
 *  extract（P1 词表 + P2 关键词→系列映射）/ select_baseline / match_kp / review（P6 产出形态）/
 *  condition（expr）/ llm（prompt/model）。width=640 + 分区（基础/高级）。
 *  nodeKey=节点 id（API key），nodeType=节点 type（渲染表单）。保存调 updateNode（立即生效）。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningNodeKey, type LexiconEntry } from '@/api/reasoningFlow'
import { strategyApi } from '@/api/strategies'
import { kpPartsApi } from '@/api/serverConfig'
import ConditionBuilder, { type SpecRule } from './ConditionBuilder.vue'
import RequirementRuleList from './RequirementRuleList.vue'
import LexiconEditor from './LexiconEditor.vue'
import SpecAliasEditor from './SpecAliasEditor.vue'
import TypePackageEditor from './TypePackageEditor.vue'
import QtyUnitEditor from './QtyUnitEditor.vue'
import ChipListInput from './ChipListInput.vue'

const NODE_META: Record<string, string> = {
  extract: '需求理解与关键词提取：分词 + 词表/系列映射（纯数据加工层，不做判定/分支）',
  clarity_check: '需求明确度判定：读「明确度规则」库评估 → 不明确触发反问（规则在本节点抽屉配）',
  ask_user: '反问补全：按缺失字段挑「反问话术」生成追问，暂停 pipeline 等用户回复（话术在本节点抽屉配）',
  budget_check: '预算校验：按「预算映射」驱动选件 + 给方案注超预算标注（映射在本节点抽屉配）',
  select_baseline: '机型选型：四级兜底 + model_recommend 标注',
  match_kp: '配件匹配：型号/规格/品类代表件三级匹配（P3 规格范围过滤）',
  compose: '组合整机方案（每 baseline × 同组 KP → 一张整机 BOM）',
  review: '产出形态：字段勾选 + 预设档位（BOM 模板不在此节点）',
  condition: '条件分支：按表达式求值选真/假分支',
  llm: 'LLM 节点（P2.3 接入，预留）',
}
const CONFIGURABLE = ['extract', 'select_baseline', 'match_kp', 'review', 'condition', 'llm', 'budget_check']

const props = defineProps<{
  open: boolean
  nodeKey: string | null        // 节点 id（API 用）
  nodeType: string | null       // 节点 type（渲染表单用）
  initialConfig: Record<string, any> | null
}>()
const emit = defineEmits<{ 'update:open': [boolean]; saved: []; remove: [string] }>()

const form = ref<any>({})
// extract 词表（5 张：KP / 机箱底盘件 / 服务器类型 / 系列 / 形态，结构统一左品类右触发词）
const kpEntries = ref<LexiconEntry[]>([])
const chassisEntries = ref<LexiconEntry[]>([])
const serverTypeEntries = ref<LexiconEntry[]>([])
const seriesEntries = ref<LexiconEntry[]>([])
const formEntries = ref<LexiconEntry[]>([])
// extract 规格别名（千兆→NIC+1G/1000M，救 ILIKE 命不中的规格词）
const specAliases = ref<Array<{ trigger: string; category: string; search_terms: string[] }>>([])
// match_kp 机型类型套餐（AI→CPU/GPU/Memory/HDD 等，可配）
const typePackages = ref<Array<{ type_keyword: string; categories: string[] }>>([])
// extract 数量解析（口语化单位 N卡→GPU + 结构化乘号 *N/×N，可配）
const qtyUnits = ref<Array<{ unit: string; category: string }>>([])
const qtyMultipliers = ref<string[]>([])
// extract 型号 token 正则（extract 抽 + pick 过滤同源，可配）
const modelTokenRegex = ref('')
// match_kp 规格匹配（P3）：品类+spec_key 都从 KP 库现有数据拉
const specRules = ref<SpecRule[]>([])       // 规格匹配规则
const kpCategoryNames = ref<string[]>([])   // KP 库品类名（/api/kp/categories）
const specKeysMap = ref<Record<string, string[]>>({})  // 品类→现有 spec_key（/api/kp/spec-keys）
// match_kp 别名表（低频，保留 JSON；批次 2 再结构化）
const aliasesJson = ref('')
// review 产出形态
const outputPreset = ref<'detailed' | 'standard' | 'concise'>('standard')
const outputFields = ref<Record<string, any>>({})
const presetReady = ref(false)  // 防 open 初始化时 preset watch 覆盖已存 output_fields

const saving = ref(false)
const recommendStrategies = ref<any[]>([])

const metaDesc = computed(() => (props.nodeType ? NODE_META[props.nodeType] || '' : ''))
const title = computed(() => props.nodeType ? `配置节点 · ${props.nodeType}` : '配置')
const configurable = computed(() => (props.nodeType ? CONFIGURABLE.includes(props.nodeType) : false))

function applyPreset(p: 'detailed' | 'standard' | 'concise') {
  if (p === 'detailed') {
    outputFields.value = { show_price: true, merge_chassis_kp: true, currency: 'RMB', show_recommend_reason: true, show_missing_hint: true }
  } else if (p === 'standard') {
    outputFields.value = { show_price: true, merge_chassis_kp: true, currency: 'RMB', show_recommend_reason: false, show_missing_hint: true }
  } else {
    outputFields.value = { show_price: true, merge_chassis_kp: false, currency: 'RMB', show_recommend_reason: false, show_missing_hint: false }
  }
}

watch(() => props.open, async (v) => {
  if (!v) { presetReady.value = false; return }
  if (!props.nodeType) return
  const c = props.initialConfig || {}
  form.value = {
    keyword_limit: c.keyword_limit ?? 12,
    max_plans: c.max_plans ?? 3,
    recommend_strategy_id: c.recommend_strategy_id ?? undefined,
    no_signal_strategy: c.no_signal_strategy || 'return_empty',
    representative_pick: c.representative_pick || 'auto',
    fallback_strategy: c.fallback_strategy || 'fallback_representative',
    underspend_threshold: c.underspend_threshold ?? 0.5,
    expr: c.expr || '',
    prompt: c.prompt || '',
    model: c.model || 'qwen',
  }
  // extract 词表：优先读新 lexicons（5 张）；旧结构（category_lexicon/series_keyword_map）自动转新
  if (Array.isArray(c.lexicons) && c.lexicons.length) {
    const find = (k: string) => c.lexicons.find((l: any) => l.kind === k)?.entries || []
    kpEntries.value = find('kp')
    chassisEntries.value = find('chassis')
    serverTypeEntries.value = find('server_type')
    seriesEntries.value = find('series')
    formEntries.value = find('form')
  } else {
    kpEntries.value = Object.entries(c.category_lexicon || {}).map(([cat, toks]) => ({ key: cat, triggers: Array.isArray(toks) ? toks : [] }))
    const se: LexiconEntry[] = []
    for (const [trig, ser] of Object.entries(c.series_keyword_map || {})) {
      const ex = se.find(e => e.key === ser)
      if (ex) ex.triggers.push(trig)
      else se.push({ key: ser as string, triggers: [trig] })
    }
    seriesEntries.value = se
    chassisEntries.value = []
    serverTypeEntries.value = []
    formEntries.value = []
  }
  specAliases.value = Array.isArray(c.spec_aliases) ? c.spec_aliases : []
  typePackages.value = Array.isArray(c.type_packages) ? c.type_packages : []
  qtyUnits.value = Array.isArray(c.qty_units) ? c.qty_units : []
  qtyMultipliers.value = Array.isArray(c.qty_multipliers) ? c.qty_multipliers : []
  modelTokenRegex.value = c.model_token_regex || ''
  // review 产出形态
  outputPreset.value = c.output_preset || 'standard'
  const hasFields = c.output_fields && Object.keys(c.output_fields).length
  outputFields.value = hasFields ? { ...c.output_fields } : (applyPreset(outputPreset.value), outputFields.value)
  presetReady.value = true
  // match_kp 别名
  aliasesJson.value = JSON.stringify(c.category_aliases ?? {}, null, 2)
  // match_kp 规格匹配（P3）
  specRules.value = Array.isArray(c.spec_rules) ? c.spec_rules.map((r: any) => ({
    category: r.category || '', spec_key: r.spec_key || '',
    op: r.op || '>=', value: r.value ?? null, unit: r.unit || '',
  })) : []
  if (props.nodeType === 'select_baseline') {
    try {
      const r = await strategyApi.list({ domain: 'selection', status: 'active', type: 'model_recommend' })
      recommendStrategies.value = r.strategies || []
    } catch { recommendStrategies.value = [] }
  }
  if (props.nodeType === 'match_kp') {
    // 分开调：spec-keys 失败不能拖累 categories（品类下拉必须可用）
    kpPartsApi.categories()
      .then(cats => { kpCategoryNames.value = (cats || []).map(c => c.name) })
      .catch(() => { kpCategoryNames.value = [] })
    kpPartsApi.specKeys()
      .then(sk => { specKeysMap.value = sk || {} })
      .catch(() => { specKeysMap.value = {} })
  }
})

watch(outputPreset, (p) => { if (presetReady.value) applyPreset(p) })

async function save() {
  if (!props.nodeKey || !configurable.value) { emit('update:open', false); return }
  const t = props.nodeType
  let config: Record<string, any> = {}
  if (t === 'extract') {
    const mk = (id: string, name: string, kind: string, entries: LexiconEntry[]) => ({
      id, name, kind, entries: entries.filter(e => e.key && e.triggers.length),
    })
    config = {
      keyword_limit: +form.value.keyword_limit,
      lexicons: [
        mk('lex_kp', 'KP 配件词表', 'kp', kpEntries.value),
        mk('lex_chassis', '机箱底盘件词表', 'chassis', chassisEntries.value),
        mk('lex_server_type', '服务器类型词表', 'server_type', serverTypeEntries.value),
        mk('lex_series', '系列词表', 'series', seriesEntries.value),
        mk('lex_form', '机箱形态词表', 'form', formEntries.value),
      ],
      spec_aliases: specAliases.value.filter(a => a.trigger && a.category),
      qty_units: qtyUnits.value.filter(u => u.unit && u.category),
      qty_multipliers: qtyMultipliers.value.filter(m => m),
      model_token_regex: modelTokenRegex.value,
    }
  } else if (t === 'select_baseline') {
    config = { max_plans: +form.value.max_plans, recommend_strategy_id: form.value.recommend_strategy_id || null, no_signal_strategy: form.value.no_signal_strategy || 'return_empty' }
  } else if (t === 'match_kp') {
    let aliases: any = null
    try { aliases = JSON.parse(aliasesJson.value || '{}') } catch { message.error('别名表 JSON 解析失败'); return }
    config = {
      representative_pick: form.value.representative_pick,
      fallback_strategy: form.value.fallback_strategy || 'fallback_representative',
      spec_rules: specRules.value.filter(r => r.category && r.spec_key && r.value != null),
      type_packages: typePackages.value.filter(p => p.type_keyword),
      category_aliases: aliases,
    }
  } else if (t === 'budget_check') {
    config = { underspend_threshold: +form.value.underspend_threshold }
  } else if (t === 'review') {
    config = { output_preset: outputPreset.value, output_fields: outputFields.value }
  } else if (t === 'condition') {
    config = { expr: form.value.expr || '' }
  } else if (t === 'llm') {
    config = { prompt: form.value.prompt || '', model: form.value.model || 'qwen' }
  }
  saving.value = true
  try {
    await reasoningFlowApi.updateNode(props.nodeKey as ReasoningNodeKey, config)
    message.success('已保存（下次推理生效）')
    emit('saved')
    emit('update:open', false)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-drawer :open="open" :title="title" width="640" @close="$emit('update:open', false)" :footer-style="{ textAlign: 'right' }">
    <template #footer>
      <div style="display:flex; align-items:center;">
        <a-button v-if="nodeKey" danger @click="$emit('remove', nodeKey as string)">删除节点</a-button>
        <span style="flex:1"></span>
        <a-button style="margin-right: 8px" @click="$emit('update:open', false)">取消</a-button>
        <a-button v-if="configurable" type="primary" :loading="saving" @click="save">保存</a-button>
      </div>
    </template>

    <a-alert v-if="nodeType" :message="metaDesc" type="info" show-icon style="margin-bottom: 16px" />

    <!-- extract：需求理解与关键词提取（5 张词表，结构统一：左品类下拉 + 右触发词） -->
    <a-form v-if="nodeType === 'extract'" layout="vertical">
      <a-divider orientation="left" class="rf-sec">提取参数</a-divider>
      <p class="rf-hint">本节点只做分词 + 词表命中。明确度规则→clarity_check 节点；反问话术→ask_user 节点；预算映射→budget_check 节点。</p>
      <a-form-item label="关键词上限（keyword_limit）"><a-input-number v-model:value="form.keyword_limit" :min="1" :max="50" style="width:100%" /></a-form-item>

      <a-divider orientation="left" class="rf-sec">KP 配件词表</a-divider>
      <p class="rf-hint">左侧从 KP 配件库下拉（CPU/GPU/Memory…）。命中 → 该品类进 KP 匹配。</p>
      <LexiconEditor v-model="kpEntries" kind="kp" />

      <a-divider orientation="left" class="rf-sec">机箱底盘件词表</a-divider>
      <p class="rf-hint">左侧从配件库分类下拉（背板/散热器/滑轨/电源…）。命中单独标注，不进 KP 匹配。</p>
      <LexiconEditor v-model="chassisEntries" kind="chassis" />

      <a-divider orientation="left" class="rf-sec">服务器类型词表</a-divider>
      <p class="rf-hint">左侧从服务器类型下拉。命中 → 机型选型精确匹配类型。</p>
      <LexiconEditor v-model="serverTypeEntries" kind="server_type" />

      <a-divider orientation="left" class="rf-sec">系列词表</a-divider>
      <p class="rf-hint">左侧从系列下拉（SSOT）。命中 → 机型选型按系列过滤。</p>
      <LexiconEditor v-model="seriesEntries" kind="series" />

      <a-divider orientation="left" class="rf-sec">机箱形态词表</a-divider>
      <p class="rf-hint">左侧从形态下拉（DISTINCT）。命中 → 机型选型按形态过滤。</p>
      <LexiconEditor v-model="formEntries" kind="form" />

      <a-divider orientation="left" class="rf-sec">规格别名表</a-divider>
      <p class="rf-hint">救 ILIKE 命不中的规格描述：用户写"千兆"但库 model 是英文（1G/1000M）→ 配触发词映射到品类 + 搜索词。仅配命不中的，不用全量。</p>
      <SpecAliasEditor v-model="specAliases" />

      <a-divider orientation="left" class="rf-sec">数量解析</a-divider>
      <a-form-item label="数量单位 → 品类">
        <p class="rf-hint">口语化数量（N卡→GPU, N条→Memory）。加新单位（如 pcs）这里配。</p>
        <QtyUnitEditor v-model="qtyUnits" />
      </a-form-item>
      <a-form-item label="结构化乘号">
        <p class="rf-hint">结构化清单"N * 2"里的乘号符号。默认 * / ×。</p>
        <ChipListInput v-model="qtyMultipliers" placeholder="乘号，如 * / ×" />
      </a-form-item>
      <a-form-item label="型号 token 正则（model_token_regex）">
        <p class="rf-hint">识别型号 token 的正则（extract 抽取 + pick 过滤<b>同源</b>）。默认必含数字，避免 nvme/sata 品类词误命中。改它要懂正则。</p>
        <a-input v-model:value="modelTokenRegex" placeholder="如 ^(?=.*[0-9])(...)$" />
      </a-form-item>
    </a-form>

    <!-- clarity_check：A 明确度规则库（实时 CRUD，立即生效） -->
    <div v-else-if="nodeType === 'clarity_check'">
      <a-alert type="info" show-icon banner message="规则实时保存、立即生效；运行中越积越准，为未来 LLM 喂语料" style="margin-bottom: 12px" />
      <p class="rf-hint">评估需求明确度（明确/部分/不明确）→ 不明确自动触发 ask_user 反问。</p>
      <RequirementRuleList rule-type="clarity" />
    </div>

    <!-- ask_user：B 反问话术库（实时 CRUD，立即生效） -->
    <div v-else-if="nodeType === 'ask_user'">
      <a-alert type="info" show-icon banner message="话术实时保存、立即生效" style="margin-bottom: 12px" />
      <p class="rf-hint">缺某字段时如何引导用户补齐（按优先级问，像 AI 客服多轮对话）。</p>
      <RequirementRuleList rule-type="rebuttal" />
    </div>

    <!-- budget_check：C 预算映射库（实时 CRUD，立即生效） + underspend 阈值 -->
    <div v-else-if="nodeType === 'budget_check'">
      <a-alert type="info" show-icon banner message="映射实时保存、立即生效" style="margin-bottom: 12px" />
      <a-form layout="inline" style="margin-bottom: 12px">
        <a-form-item label="underspend 阈值">
          <a-input-number v-model:value="form.underspend_threshold" :min="0" :max="1" :step="0.1" style="width: 100px" />
        </a-form-item>
        <span class="rf-hint">方案价/预算 低于此值提示"可升级"（0.5 = 用不足一半预算时提示）</span>
      </a-form>
      <p class="rf-hint">预算区间 → 配件选配策略（取低价/高价）。match_kp 按此动态选代表件；无预算走默认。</p>
      <RequirementRuleList rule-type="budget" />
    </div>

    <!-- select_baseline：保留 -->
    <a-form v-else-if="nodeType === 'select_baseline'" layout="vertical">
      <a-divider orientation="left" class="rf-sec">基础参数</a-divider>
      <a-form-item label="候选方案数（max_plans）"><a-input-number v-model:value="form.max_plans" :min="1" :max="5" style="width:100%" /></a-form-item>
      <a-form-item label="推荐策略（model_recommend）">
        <a-select v-model:value="form.recommend_strategy_id" allow-clear placeholder="不限（读全部 active）" style="width:100%">
          <a-select-option v-for="r in recommendStrategies" :key="r.id" :value="r.id">{{ r.name }}（{{ r.scope?.series || '通用' }}）</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="无信号策略（no_signal_strategy）">
        <a-radio-group v-model:value="form.no_signal_strategy">
          <a-radio value="return_empty">返空（让反问）</a-radio>
          <a-radio value="fallback_all">硬推全量</a-radio>
        </a-radio-group>
        <p class="rf-hint">需求没指定类型/系列/形态时：返空=触发反问（默认）；硬推全量=给所有机型（旧行为）。</p>
      </a-form-item>
    </a-form>

    <!-- match_kp：P3 三级匹配（型号/规格/代表件） -->
    <a-form v-else-if="nodeType === 'match_kp'" layout="vertical">
      <a-divider orientation="left" class="rf-sec">基础参数</a-divider>
      <a-form-item label="代表件选取（representative_pick）">
        <a-radio-group v-model:value="form.representative_pick">
          <a-radio value="auto">按预算自动</a-radio>
          <a-radio value="min_price">最低价</a-radio>
          <a-radio value="max_price">最高价</a-radio>
          <a-radio value="first">首个</a-radio>
        </a-radio-group>
      </a-form-item>
      <a-form-item label="规格匹配规则">
        <p class="rf-hint">品类/字段从配件库下拉。数值是<b>默认值</b>——用户在需求里写了规格（如"16G 内存"）就按用户的匹配，没写才用此默认值；库无命中按下方兜底策略。</p>
        <ConditionBuilder v-model="specRules" :category-options="kpCategoryNames" :spec-keys-map="specKeysMap" />
      </a-form-item>
      <a-form-item label="机型类型套餐（type_packages）">
        <p class="rf-hint">机型类型（关键词匹配 server_type.name）→ 标准 KP 品类套餐。如 AI 机型配 CPU/GPU/Memory/HDD。加新机型类型这里配套餐，不用改代码。</p>
        <TypePackageEditor v-model="typePackages" />
      </a-form-item>
      <a-form-item label="缺货兜底策略（fallback_strategy）">
        <a-radio-group v-model:value="form.fallback_strategy">
          <a-radio value="fallback_representative">回退代表件</a-radio>
          <a-radio value="mark_unmatched">标记需手填</a-radio>
          <a-radio value="raise">中断报错</a-radio>
        </a-radio-group>
        <p class="rf-hint">回退=按原逻辑取品类代表件（不阻塞）；标记=方案卡标"需手填"且不入 BOM；中断=pipeline 报错（慎用）。</p>
      </a-form-item>
      <a-collapse :bordered="false">
        <a-collapse-panel key="alias" header="品类别名表（高级 · JSON）"><a-textarea v-model:value="aliasesJson" :rows="10" class="rf-json" /></a-collapse-panel>
      </a-collapse>
    </a-form>

    <!-- review：产出形态（P6） -->
    <a-form v-else-if="nodeType === 'review'" layout="vertical">
      <a-divider orientation="left" class="rf-sec">基础参数</a-divider>
      <a-form-item label="产出预设">
        <a-radio-group v-model:value="outputPreset">
          <a-radio-button value="detailed">详细</a-radio-button>
          <a-radio-button value="standard">标准</a-radio-button>
          <a-radio-button value="concise">精简</a-radio-button>
        </a-radio-group>
        <p class="rf-hint">选档位会一键切换下方勾选；也可手动细调。</p>
      </a-form-item>
      <a-form-item label="方案卡展示字段">
        <div class="rf-checks">
          <a-checkbox v-model:checked="outputFields.show_price">显示价格</a-checkbox>
          <a-checkbox v-model:checked="outputFields.merge_chassis_kp">合并机箱+配件</a-checkbox>
          <a-checkbox v-model:checked="outputFields.show_recommend_reason">附推荐理由</a-checkbox>
          <a-checkbox v-model:checked="outputFields.show_missing_hint">附缺失项提示</a-checkbox>
        </div>
      </a-form-item>
      <a-form-item label="币种"><a-input v-model:value="outputFields.currency" placeholder="RMB" /></a-form-item>
      <p class="rf-hint">BOM 模板选择不在本节点（留工作台/报价模板）。</p>
    </a-form>

    <!-- condition：保留 -->
    <a-form v-else-if="nodeType === 'condition'" layout="vertical">
      <a-form-item label="条件表达式（simpleeval 安全求值）">
        <a-input v-model:value="form.expr" placeholder="如：series == 'Polaris'" />
        <p class="rf-hint">可用变量：series / form / categories（列表）/ keywords（列表）/ <b>clarity</b>（explicit·partial·unclear）/ <b>clarity_capped</b>（bool）/ <b>budget</b>（数值）/ <b>has_budget</b>（bool）/ <b>missing_fields</b>（列表）。求值 true 走真分支（sourceHandle='true'），false 走假分支。</p>
      </a-form-item>
    </a-form>

    <!-- llm：保留 -->
    <a-form v-else-if="nodeType === 'llm'" layout="vertical">
      <a-form-item label="Prompt"><a-textarea v-model:value="form.prompt" :rows="4" placeholder="（P2.3 接入 LLM 调用）" /></a-form-item>
      <a-form-item label="模型"><a-input v-model:value="form.model" /></a-form-item>
    </a-form>

    <a-empty v-else description="该节点无可配置参数" />
  </a-drawer>
</template>

<style scoped>
.rf-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 4px 0 0; }
.rf-json { font-family: ui-monospace, monospace; font-size: 12px; }
.rf-sec { font-size: 13px; margin-top: 8px; }
.rf-checks { display: flex; flex-wrap: wrap; gap: 12px 16px; padding: 4px 0; }
</style>
