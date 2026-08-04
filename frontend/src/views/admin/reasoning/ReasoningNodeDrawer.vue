<script setup lang="ts">
/** 推理流节点配置抽屉 —— 按 node.type 渲染参数表单。
 *  extract（P1 词表 + P2 关键词→系列映射）/ select_baseline / match_kp / review（P6 产出形态）/
 *  condition（expr）/ llm（prompt/model）。width=640 + 分区（基础/高级）。
 *  nodeKey=节点 id（API key），nodeType=节点 type（渲染表单）。保存调 updateNode（立即生效）。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningNodeKey, type LexiconEntry } from '@/api/reasoningFlow'
import { strategyApi } from '@/api/strategies'
import { kpPartsApi, catalogApi } from '@/api/serverConfig'
import ConditionBuilder, { type SpecRule } from './ConditionBuilder.vue'
import RequirementRuleList from './RequirementRuleList.vue'
import SlotListEditor from './SlotListEditor.vue'
import LexiconEditor from './LexiconEditor.vue'
import SpecAliasEditor from './SpecAliasEditor.vue'
import TypePackageEditor from './TypePackageEditor.vue'
import QtyUnitEditor from './QtyUnitEditor.vue'
import ChipListInput from './ChipListInput.vue'

const NODE_META: Record<string, string> = {
  normalize_input: '需求输入规范化：extract 前的格式归一（表格行/字符修正/噪音过滤/空白折叠），规则可配、白盒报告',
  extract: '需求理解与关键词提取：分词 + 词表/系列映射（纯数据加工层，不做判定/分支）',
  clarity_check: '需求明确度判定：按期望槽位清单算「已填 vs 期望」差距 → L0 缺≥阈值触发反问（清单在本节点抽屉配）',
  ask_user: '反问补全（目录驱动引导）：选服务器类型 → 选机型 → 按格式填 KP 规格，选项 100% 来自产品目录（引导配置在本节点抽屉配）',
  budget_check: '预算校验：按「预算映射」驱动选件 + 给方案注超预算标注（映射在本节点抽屉配）',
  select_baseline: '机型选型：四级兜底 + model_recommend 标注',
  match_kp: '配件匹配：型号/规格/品类代表件三级匹配（P3 规格范围过滤）',
  compose: '组合整机方案（每 baseline × 同组 KP → 一张整机 BOM）',
  review: '产出形态：字段勾选 + 预设档位（BOM 模板不在此节点）',
  condition: '条件分支：按表达式求值选真/假分支',
  scene_analysis: '场景分析：需求信号 + 商机上下文 → AI/存储/通用 × 系列 × 形态，输出带证据（映射数据在 system_config.scene_mapping，可编辑）',
  llm_understand: 'LLM 主理解：需求原文 + 在售目录白名单 → 统一槽位契约（槽位/置信度/证据/预算/意图摘要/缺失项/追问）。开启后 LLM 结果才真正进选型（默认关，不拖慢流程）',
  slot_validate: '槽位语义校验：白名单外值丢弃 + LLM 与规则冲突/低置信度收集（P2 确认面板消费），是 LLM 进选型前的确定性闸门',
  confirm: 'LLM 确认面板：冲突/低置信度项默认采纳 LLM 补充、高亮可改；决策写入 requirement_samples 反馈闭环。无确认项自动跳过',
  llm_ask: 'LLM 反问：复用目录驱动状态机（类型→机型→KP 格式），问题文案由 LLM 生成（一次列全缺失项）；LLM 未开时回落纯目录问题',
  llm_audit: 'LLM 方案校对：bom_cases 同平台 few-shot + 一次调用校对全部方案（意图级问题：GPU/存储/平台是否满足）；规则硬校验仍在 review 兜底，默认关',
}
const CONFIGURABLE = ['extract', 'select_baseline', 'match_kp', 'review', 'condition', 'llm', 'budget_check', 'ask_user', 'scene_analysis', 'normalize_input', 'confirm_series', 'llm_understand', 'slot_validate', 'confirm', 'llm_ask', 'llm_audit']

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
// scene_analysis 场景映射（JSON，权威数据源 system_config.scene_mapping；此处仅节点级兜底）
const sceneMappingJson = ref('')
// normalize_input 归一配置（JSON：char_fixes / noise_patterns / 开关）
const normalizeJson = ref('')
// ask_user 目录驱动引导配置（推荐类型 / 代表性机型 / 回复格式模板）
const catalogTypes = ref<any[]>([])          // 服务器类型（l6.server_types）
const modelsByType = ref<Record<number, any[]>>({})  // 类型 id → 在售机型
const enabledTypes = ref<string[]>([])
const recommendedType = ref('')
const recommendedModels = ref<Record<string, string>>({})
const typeQuestion = ref('')
const modelQuestion = ref('')
const kpIntro = ref('')
const replyFormat = ref('')
const defaultHint = ref('')
const maxRounds = ref(6)

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
    mode: c.mode || 'catalog',
    enable_llm: !!c.enable_llm,
    decide_threshold: c.decide_threshold ?? 30,
    fallback_scene: c.fallback_scene || '通用计算服务器',
    enabled_types: Array.isArray(c.enabled_types) ? c.enabled_types : [],
    recommended_type: c.recommended_type || '',
    recommended_models: c.recommended_models || {},
    type_question: c.type_question || '',
    model_question: c.model_question || '',
    kp_intro: c.kp_intro || '',
    reply_format: c.reply_format || '',
    default_hint: c.default_hint || '',
    max_rounds: c.max_rounds ?? 6,
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
  sceneMappingJson.value = c.mapping ? JSON.stringify(c.mapping, null, 2) : ''
  normalizeJson.value = JSON.stringify({ char_fixes: c.char_fixes, enable_table_rows: c.enable_table_rows, noise_patterns: c.noise_patterns, collapse_whitespace: c.collapse_whitespace }, null, 2)
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
  typeQuestion.value = form.value.type_question || ''
  modelQuestion.value = form.value.model_question || ''
  kpIntro.value = form.value.kp_intro || ''
  replyFormat.value = form.value.reply_format || ''
  defaultHint.value = form.value.default_hint || ''
  maxRounds.value = form.value.max_rounds ?? 6
  if (props.nodeType === 'ask_user') {
    // 目录数据源（l6.server_types / l6.server_models）——引导配置的内容都从这里选，不硬编码
    catalogApi.listTypes().then((r: any) => {
      const types = r.types || []
      catalogTypes.value = types
      enabledTypes.value = Array.isArray(c.enabled_types) ? c.enabled_types : []
      recommendedType.value = c.recommended_type || ''
      const rec: Record<string, string> = c.recommended_models || {}
      recommendedModels.value = { ...rec }
      return Promise.all(types.map((t: any) =>
        catalogApi.listModels(t.id)
          .then((m: any) => { modelsByType.value[t.id] = m.models || [] })
          .catch(() => { modelsByType.value[t.id] = [] })
      ))
    }).catch(() => { catalogTypes.value = [] })
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

/** 组装当前表单 → 节点 config。JSON 解析失败已在此 toast 并返回 null。 */
function buildConfig(): Record<string, any> | null {
  if (!props.nodeKey || !configurable.value) return null
  const t = props.nodeType
  if (t === 'extract') {
    const mk = (id: string, name: string, kind: string, entries: LexiconEntry[]) => ({
      id, name, kind, entries: entries.filter(e => e.key && e.triggers.length),
    })
    return {
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
    return { max_plans: +form.value.max_plans, recommend_strategy_id: form.value.recommend_strategy_id || null, no_signal_strategy: form.value.no_signal_strategy || 'return_empty' }
  } else if (t === 'match_kp') {
    let aliases: any = null
    try { aliases = JSON.parse(aliasesJson.value || '{}') } catch { message.error('别名表 JSON 解析失败'); return null }
    return {
      representative_pick: form.value.representative_pick,
      fallback_strategy: form.value.fallback_strategy || 'fallback_representative',
      spec_rules: specRules.value.filter(r => r.category && r.spec_key && r.value != null),
      type_packages: typePackages.value.filter(p => p.type_keyword),
      category_aliases: aliases,
    }
  } else if (t === 'ask_user') {
    return {
      mode: 'catalog',
      enabled_types: enabledTypes.value,
      recommended_type: recommendedType.value,
      recommended_models: recommendedModels.value,
      type_question: typeQuestion.value || undefined,
      model_question: modelQuestion.value || undefined,
      kp_intro: kpIntro.value || undefined,
      reply_format: replyFormat.value || undefined,
      default_hint: defaultHint.value || undefined,
      max_rounds: +maxRounds.value || 6,
    }
  } else if (t === 'budget_check') {
    return { underspend_threshold: +form.value.underspend_threshold }
  } else if (t === 'review') {
    return { output_preset: outputPreset.value, output_fields: outputFields.value }
  } else if (t === 'condition') {
    return { expr: form.value.expr || '' }
  } else if (t === 'normalize_input') {
    try {
      const norm = JSON.parse(normalizeJson.value || '{}')
      return {
        char_fixes: Array.isArray(norm.char_fixes) ? norm.char_fixes : [],
        enable_table_rows: norm.enable_table_rows !== false,
        noise_patterns: Array.isArray(norm.noise_patterns) ? norm.noise_patterns : [],
        collapse_whitespace: norm.collapse_whitespace !== false,
      }
    } catch { message.error('归一配置 JSON 解析失败'); return null }
  } else if (t === 'scene_analysis') {
    let mapping: any = null
    if (sceneMappingJson.value.trim()) {
      try { mapping = JSON.parse(sceneMappingJson.value) } catch { message.error('场景映射 JSON 解析失败'); return null }
    }
    return {
      decide_threshold: +form.value.decide_threshold || 30,
      fallback_scene: form.value.fallback_scene || '通用计算服务器',
      mapping: mapping,
    }
  } else if (t === 'llm_understand') {
    return { enable_llm: !!form.value.enable_llm, max_retry: +form.value.max_retry || 1 }
  } else if (t === 'slot_validate') {
    return { strict: form.value.strict !== false }
  } else if (t === 'confirm') {
    return { default_decision: form.value.default_decision || 'accept' }
  } else if (t === 'llm_ask') {
    return { use_llm_questions: form.value.use_llm_questions !== false }
  } else if (t === 'llm_audit') {
    return { enable_llm: !!form.value.enable_llm, reference_limit: +form.value.reference_limit || 2 }
  } else if (t === 'llm') {
    return { prompt: form.value.prompt || '', model: form.value.model || 'qwen' }
  }
  // 未单列的类型（如 confirm_series）保持旧行为：存空 config
  return {}
}

async function persist(config: Record<string, any>): Promise<boolean> {
  saving.value = true
  try {
    await reasoningFlowApi.updateNode(props.nodeKey as ReasoningNodeKey, config)
    emit('saved')
    return true
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
    return false
  } finally {
    saving.value = false
  }
}

async function save() {
  if (!props.nodeKey || !configurable.value) { emit('update:open', false); return }
  const config = buildConfig()
  if (config === null) return
  if (await persist(config)) {
    message.success('已保存（下次推理生效）')
    emit('update:open', false)
  }
}

/** 「启用 LLM 增强」开关拨动即立即保存（不再要求点「保存」，避免关抽屉后以为开了实际没开）。 */
async function toggleLlm() {
  if (!props.nodeKey || !configurable.value) return
  const config = buildConfig()
  if (config === null) return
  if (await persist(config)) {
    message.success(form.value.enable_llm ? 'LLM 增强已开启（下次推理生效）' : 'LLM 增强已关闭')
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
      <a-alert type="info" show-icon banner message="LLM 已收拢到独立「LLM 主理解」节点：本节点保持 100% 规则抽取，不再挂大模型" style="margin-bottom: 12px" />
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

    <!-- clarity_check：期望槽位清单（明确度 = 槽位覆盖度，L0/L1/L2 可配置） -->
    <div v-else-if="nodeType === 'clarity_check'">
      <SlotListEditor />
    </div>

    <!-- ask_user：目录驱动引导（选项 100% 来自产品目录，拒绝臆造） -->
    <div v-else-if="nodeType === 'ask_user'">
      <a-alert type="info" show-icon banner message="选项全部来自产品目录（服务器类型/在售机型），保存即生效" style="margin-bottom: 12px" />
      <p class="rf-hint">流程：选类型 → 选机型 → 按格式填 KP 规格。客户答「不确定/你推荐」走下面的推荐项；「跳过」强制出方案。</p>
      <a-divider orientation="left" class="rf-sec">引导内容</a-divider>
      <a-form-item label="启用类型（空 = 全部有货在售类型）">
        <a-select v-model:value="enabledTypes" mode="multiple" allow-clear placeholder="全部类型" style="width: 100%">
          <a-select-option v-for="t in catalogTypes" :key="t.name" :value="t.name">{{ t.name }}</a-select-option>
        </a-select>
        <p class="rf-hint">只推有在售机型的类型；这里可剔除不想推的类型。</p>
      </a-form-item>
      <a-form-item label="推荐类型（客户答「你推荐/不确定」时的默认）">
        <a-select v-model:value="recommendedType" allow-clear placeholder="第一个类型" style="width: 100%">
          <a-select-option v-for="t in catalogTypes" :key="t.name" :value="t.name">{{ t.name }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="代表性机型（每类型一个，客户不选机型时用）">
        <div class="rf-rec-models">
          <div v-for="t in catalogTypes" :key="t.id" class="rf-rec-row">
            <span class="rf-rec-label">{{ t.name }}</span>
            <a-select v-model:value="recommendedModels[t.name]" allow-clear placeholder="第一个在售机型" style="flex: 1">
              <a-select-option v-for="m in (modelsByType[t.id] || [])" :key="m.id" :value="m.name">{{ m.name }}</a-select-option>
            </a-select>
          </div>
        </div>
        <p class="rf-hint">机型数据源：l6.server_models（按类型过滤，仅展示在售）。</p>
      </a-form-item>
      <a-divider orientation="left" class="rf-sec">话术与格式</a-divider>
      <a-form-item label="类型选择问句"><a-textarea v-model:value="typeQuestion" :rows="1" placeholder="请选择服务器类型（以下均为有货在售类型）：" /></a-form-item>
      <a-form-item label="机型选择问句"><a-textarea v-model:value="modelQuestion" :rows="1" placeholder="请选择该类型下的在售机型：" /></a-form-item>
      <a-form-item label="KP 填写引导语"><a-textarea v-model:value="kpIntro" :rows="1" placeholder="请按以下格式填写需要的配件，没有的项可省略：" /></a-form-item>
      <a-form-item label="回复格式模板（引导客户按格式填写）">
        <a-textarea v-model:value="replyFormat" :rows="5" placeholder="CPU：型号 ×数量&#10;内存：容量 ×条数&#10;GPU：型号 ×数量&#10;硬盘：容量 ×数量&#10;预算：金额" />
        <p class="rf-hint">客户回复按此格式解析（型号/数量/容量/预算信号均由 extract 拾取）；格式越规范识别率越高。</p>
      </a-form-item>
      <a-form-item label="默认提示语"><a-input v-model:value="defaultHint" placeholder="不确定可回复「你推荐」，或点「跳过」让我推荐" /></a-form-item>
      <a-form-item label="最大反问轮数"><a-input-number v-model:value="maxRounds" :min="1" :max="10" style="width: 100%" /></a-form-item>
      <a-divider orientation="left" class="rf-sec">KP 品类套餐</a-divider>
      <p class="rf-hint">该类型支持哪些选配件品类，在下方「配件匹配」节点的「机型类型套餐」里配（两处共用同一数据源，避免重复维护）。</p>
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
      <a-alert type="info" show-icon banner message="LLM 语义校对已收拢到独立「LLM 方案校对」节点（bom_cases few-shot，默认关）；本节点只做规则硬校验（缺件/平台/超预算）+ 合并 LLM 校对结果" style="margin-bottom: 12px" />
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
        <p class="rf-hint">可用变量：series / form / categories（列表）/ keywords（列表）/ <b>clarity</b>（explicit·partial·unclear）/ <b>clarity_capped</b>（bool）/ <b>budget</b>（数值）/ <b>has_budget</b>（bool）/ <b>missing_fields</b>（列表）。空列表判断用 <code>not missing_fields</code>（simpleeval 不支持 len()）。求值 true 走真分支（sourceHandle='true'），false 走假分支。</p>
      </a-form-item>
    </a-form>

    <!-- normalize_input：需求输入规范化（extract 前） -->
    <a-form v-else-if="nodeType === 'normalize_input'" layout="vertical">
      <a-alert type="info" show-icon banner message="白盒：每次归一会输出 report（改了什么）。规则数据驱动，改这里立即生效" style="margin-bottom: 12px" />
      <p class="rf-hint">把千变万化的用户写法归一成 extract 能识别的统一格式：字符修正（拼写颠倒/全角）、Markdown 表格行（数量列→*N）、噪音过滤（时间戳/问候语）、空白折叠。</p>
      <a-collapse :bordered="false">
        <a-collapse-panel key="norm" header="归一规则（JSON）">
          <p class="rf-hint">结构：char_fixes（[from,to] 有序替换）、enable_table_rows（bool）、noise_patterns（[{pattern,flags,note}]）、collapse_whitespace（bool）。</p>
          <a-textarea v-model:value="normalizeJson" :rows="14" class="rf-json" />
        </a-collapse-panel>
      </a-collapse>
    </a-form>

    <!-- scene_analysis：场景分析（AI/存储/通用 × 系列 × 形态） -->
    <a-form v-else-if="nodeType === 'scene_analysis'" layout="vertical">
      <a-alert type="info" show-icon banner message="LLM 已收拢到独立「LLM 主理解」节点：本节点保持规则兜底确定性" style="margin-bottom: 12px" />
      <a-alert type="info" show-icon banner message="白盒：输出带证据（为什么选这个场景/系列/形态）。映射权威数据源 = system_config.scene_mapping（平台配置），此处仅节点级兜底" style="margin-bottom: 12px" />
      <a-divider orientation="left" class="rf-sec">判定参数</a-divider>
      <a-form-item label="判定阈值（decide_threshold）">
        <a-input-number v-model:value="form.decide_threshold" :min="0" :max="100" style="width:100%" />
        <p class="rf-hint">场景分≥此值才判定；低于回退默认场景（避免过度反问）。</p>
      </a-form-item>
      <a-form-item label="默认场景（fallback_scene）">
        <a-input v-model:value="form.fallback_scene" placeholder="通用计算服务器" />
        <p class="rf-hint">无强场景信号时回退的类型（需与 l6.server_types 名称一致）。</p>
      </a-form-item>
      <a-collapse :bordered="false">
        <a-collapse-panel key="mapping" header="场景映射（高级 · JSON · 权威在 system_config.scene_mapping）">
          <p class="rf-hint">结构：scene_rules（场景→信号权重+证据）、series_hints、form_infer、opportunity_hints、thresholds、fallback_scene。留空=用系统配置/内置默认。</p>
          <a-textarea v-model:value="sceneMappingJson" :rows="14" class="rf-json" />
        </a-collapse-panel>
      </a-collapse>
    </a-form>

    <!-- llm_understand：LLM 主理解（需求原文 + 目录白名单 → 槽位契约） -->
    <a-form v-else-if="nodeType === 'llm_understand'" layout="vertical">
      <a-form-item label="启用 LLM 主理解">
        <a-switch v-model:checked="form.enable_llm" @change="toggleLlm" />
        <span class="rf-hint" style="display:block;margin-top:4px">开启后本节点调用大模型（受「设置→AI 设置→启用 AI」总开关约束）；LLM 输出经 schema 收口 + 语义校验（白名单/型号接地/数量）+ 失败喂回重试 1 次，再失败自动降级规则，绝不阻塞流程。默认关 = 纯规则透传，零成本</span>
      </a-form-item>
      <a-alert type="info" show-icon banner message="这是 LLM 唯一主入口：需求原文 + 在售目录白名单 → 统一槽位契约（槽位/置信度/证据/预算/意图摘要/缺失项/追问），只许从白名单选、选不出写 null、禁编料号" style="margin-bottom: 12px" />
      <a-divider orientation="left" class="rf-sec">行为参数</a-divider>
      <a-form-item label="校验失败重试次数（max_retry）">
        <a-input-number v-model:value="form.max_retry" :min="0" :max="3" style="width:100%" />
        <p class="rf-hint">语义校验不通过时，把具体错误喂回大模型修正；0 = 不重试（失败即降级）。每次 LLM 调用约 30~60s，重试会翻倍耗时。</p>
      </a-form-item>
    </a-form>

    <!-- slot_validate：槽位语义校验（确定性闸门） -->
    <a-form v-else-if="nodeType === 'slot_validate'" layout="vertical">
      <a-form-item label="严格模式">
        <a-switch v-model:checked="form.strict" />
        <span class="rf-hint" style="display:block;margin-top:4px">开：白名单外系列/形态/类型直接丢弃并记 issues（推荐）；关：仅提示不丢弃。LLM 与规则冲突/低置信度项会进 confirm_items，供 P2 确认面板消费</span>
      </a-form-item>
      <a-alert type="info" show-icon banner message="确定性闸门：LLM 结果进选型前的最后一道语义校验（不调大模型，零成本）。覆盖度明细也会在这里产出，是 P2 明确度判定的输入" style="margin-bottom: 12px" />
    </a-form>

    <!-- confirm：LLM 确认面板（默认采纳、高亮可改） -->
    <a-form v-else-if="nodeType === 'confirm'" layout="vertical">
      <a-form-item label="默认决策">
        <a-radio-group v-model:value="form.default_decision">
          <a-radio value="accept">默认采纳 LLM 补充项（推荐）</a-radio>
          <a-radio value="ignore">默认忽略，需用户手动采纳</a-radio>
        </a-radio-group>
        <p class="rf-hint">前端面板默认按此决策预勾选并高亮，用户可逐项改。无确认项时本节点自动跳过（零成本）。</p>
      </a-form-item>
      <a-alert type="info" show-icon banner message="确认面板展示「LLM 与规则冲突 / 低置信度」项；决策（采纳/忽略）写入 requirement_samples 反馈闭环（source=llm_feedback），供未来 LLM 语料/评测" style="margin-bottom: 12px" />
    </a-form>

    <!-- llm_ask：LLM 反问（复用目录状态机 + LLM 一次性追问） -->
    <a-form v-else-if="nodeType === 'llm_ask'" layout="vertical">
      <a-form-item label="注入 LLM 缺失项追问">
        <a-switch v-model:checked="form.use_llm_questions" />
        <p class="rf-hint">开：把 LLM 主理解产出的一次性缺失项追问（如「请确认：CPU型号；内存容量…」）并入反问文案；关：纯目录问题（与 ask_user 一致）。</p>
      </a-form-item>
      <a-alert type="info" show-icon banner message="本节点复用 ask_user 的目录驱动状态机（类型→机型→KP 格式），选项 100% 来自产品目录；LLM 未开启时自动回落纯目录问题" style="margin-bottom: 12px" />
    </a-form>

    <!-- llm_audit：LLM 方案校对（bom_cases few-shot，一次调用校对全部方案） -->
    <a-form v-else-if="nodeType === 'llm_audit'" layout="vertical">
      <a-form-item label="启用 LLM 方案校对">
        <a-switch v-model:checked="form.enable_llm" @change="toggleLlm" />
        <span class="rf-hint" style="display:block;margin-top:4px">开启后对全部方案一次调用大模型（受「设置→AI 设置→启用 AI」总开关约束）；规则硬校验（缺件/平台/超预算）仍在 review 节点 100% 兜底，失败自动降级规则，绝不阻塞流程。默认关 = 纯规则校对，零成本</span>
      </a-form-item>
      <a-divider orientation="left" class="rf-sec">行为参数</a-divider>
      <a-form-item label="few-shot 参考案例数（reference_limit）">
        <a-input-number v-model:value="form.reference_limit" :min="0" :max="5" style="width:100%" />
        <p class="rf-hint">取同系列（平台）的 bom_cases 当「这类需求该长什么样」的参考样本；平台不同不会硬套。0 = 不带参考。</p>
      </a-form-item>
      <a-alert type="info" show-icon banner message="只报意图级硬问题（GPU/存储/平台是否满足需求意图），禁止逐行 diff——吸取 2026-08-04「案例库规格级对照全误报」教训。每次调用记 trace，指标可在 /api/reasoning/llm-metrics 查看" style="margin-bottom: 12px" />
    </a-form>

    <a-empty v-else description="该节点无可配置参数" />
  </a-drawer>
</template>

<style scoped>
.rf-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 4px 0 0; }
.rf-json { font-family: ui-monospace, monospace; font-size: 12px; }
.rf-sec { font-size: 13px; margin-top: 8px; }
.rf-checks { display: flex; flex-wrap: wrap; gap: 12px 16px; padding: 4px 0; }
.rf-rec-models { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.rf-rec-row { display: flex; align-items: center; gap: 10px; }
.rf-rec-label { min-width: 150px; font-size: 12px; color: var(--cpq-text-secondary); }
</style>
