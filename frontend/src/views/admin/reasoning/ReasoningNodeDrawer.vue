<script setup lang="ts">
/** 推理流节点配置抽屉 —— 按 node.type 渲染参数表单。
 *  understand（领域知识词表 + 分步 AI 理解）/ model_reason / kp_reason / review（产出形态）/
 *  condition（expr）/ llm（prompt/model）。width=640 + 分区（基础/高级）。
 *  nodeKey=节点 id（API key），nodeType=节点 type（渲染表单）。保存调 updateNode（立即生效）。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningNodeKey, type LexiconEntry } from '@/api/reasoningFlow'
import { strategyApi } from '@/api/strategies'
import { kpPartsApi } from '@/api/serverConfig'
import ConditionBuilder, { type SpecRule } from './ConditionBuilder.vue'
import RequirementRuleList from './RequirementRuleList.vue'
import SlotListEditor from './SlotListEditor.vue'
import LexiconEditor from './LexiconEditor.vue'
import SpecAliasEditor from './SpecAliasEditor.vue'
import TypePackageEditor from './TypePackageEditor.vue'
import QtyUnitEditor from './QtyUnitEditor.vue'
import ChipListInput from './ChipListInput.vue'
import JsonRowEditor from './JsonRowEditor.vue'
import EditableKVTable, { type KVRow } from './EditableKVTable.vue'
import { DEFAULT_CONFIG_INTENT_WORDS } from '@/utils/configIntent'
import { reasoningNodeMeta } from '@/utils/reasoningNodeMeta'

/** llm_ask 默认提示词（AI 生成反问话术的规则；与后端 capabilities._LLM_ASK_PROMPT 同步）。
 * system_prompt 留空 = 用这份默认；填了则覆盖。 */
const DEFAULT_LLM_ASK_PROMPT = [
  '你是 CPQ 平台的服务器需求分析师，负责向客户提一个关键问题。',
  '输入包含：客户需求原文、已理解到的信息、还缺的关键信息、在售目录选项。',
  '任务：判断【哪个缺失信息对选型影响最大】，生成 1 个问题。',
  '要求：',
  '1) 问题要具体、带可选项（从目录里给 2-6 个选项，让客户好回答）；',
  '2) options 里的值必须来自输入给出的在售目录，禁止编造；',
  '3) why 一句话解释「为什么问这个」（对选型的影响）；',
  '4) 只输出 json（JSON 格式）：{question, options, why}。',
].join('\n')

const NODE_META: Record<string, string> = {
  understand: '需求理解（AI 主节点）：LLM 填表理解需求 + 领域知识(词表)注入 + 目录白名单锚定；抽不全→反问；AI 失效→诚实降级（目录手动选型 + 明确告知）',
  gap_analyze: '缺口分析：已填槽位 vs 期望清单 → 明确度 + 缺失项（LLM 可选解释缺什么、为什么关键）',
  llm_ask: '智能反问：LLM 基于完整上下文生成策略性问题（带选项/理由，一次问最关键的一个）；AI 关→目录引导兜底',
  scene_decide: '场景判定：需求信号 → AI/存储/通用 × 系列 × 形态，带证据白盒（AI 增强 + 规则本体）',
  model_reason: '机型推理：LLM ReAct 调 select_models 工具选机型 + 理由；失败→规则四级兜底（型号/料号精确性规则保证）',
  kp_reason: '配件推理：LLM ReAct 调 pick_kp_parts 工具确认配件 + 理由；失败→规则三级匹配',
  compose: '方案组装（确定性红线）：把选型决策组装成整机 BOM（价格/兼容性/PSU/线缆派生），LLM 不可碰',
  budget_check: '预算校验：超预算/欠预算标注',
  llm_audit: '方案校对：LLM 意图级审查（few-shot 案例）+ 规则硬校验兜底',
  llm_confirm: '决策确认（可选）：汇总机型/配件推荐 + 理由，给用户确认/调整后重跑',
  review: '方案就绪：产出方案清单',
  condition: '条件分支：按表达式求值选真/假分支',
  orchestrator: '编排配置（不执行）：结构化记忆（摘要/轮数/字段）+ 白盒计划 + 确定性能力并行 + AI 增强预算（快/均衡/最优）',
  result_check: '方案自检（确定性）：结果完整性 + 必填核心件 + 数量合理性；失败可自动触发重跑',
  text_clean: '文本清洗（可选）：去噪音/全角归一/表格行归一（AI 与规则共用前置，可删）',
}
const CONFIGURABLE = ['understand', 'gap_analyze', 'llm_ask', 'orchestrator', 'scene_decide', 'model_reason', 'kp_reason', 'spec_compliance', 'result_check', 'compose', 'budget_check', 'llm_audit', 'audit_fix', 'llm_confirm', 'review', 'condition', 'text_clean']

const props = defineProps<{
  open: boolean
  nodeKey: string | null        // 节点 id（API 用）
  nodeType: string | null       // 节点 type（渲染表单用）
  initialConfig: Record<string, any> | null
}>()
const emit = defineEmits<{ 'update:open': [boolean]; saved: []; remove: [string] }>()

const form = ref<any>({})
// 领域知识词表（5 张：KP / 机箱底盘件 / 服务器类型 / 系列 / 形态，understand 节点注入给 LLM）
const kpEntries = ref<LexiconEntry[]>([])
const chassisEntries = ref<LexiconEntry[]>([])
const serverTypeEntries = ref<LexiconEntry[]>([])
const seriesEntries = ref<LexiconEntry[]>([])
const formEntries = ref<LexiconEntry[]>([])
// 规格别名（千兆→NIC+1G/1000M，救 ILIKE 命不中的规格词）
const specAliases = ref<Array<{ trigger: string; category: string; search_terms: string[] }>>([])
// match_kp 机型类型套餐（AI→CPU/GPU/Memory/HDD 等，可配）
const typePackages = ref<Array<{ type_keyword: string; categories: string[] }>>([])
// 数量解析（口语化单位 N卡→GPU + 结构化乘号 *N/×N，可配）
const qtyUnits = ref<Array<{ unit: string; category: string }>>([])
const qtyMultipliers = ref<string[]>([])
// 型号 token 正则（understand 理解 + pick 过滤同源，可配）
const modelTokenRegex = ref('')
// match_kp 规格匹配（P3）：品类+spec_key 都从 KP 库现有数据拉
const specRules = ref<SpecRule[]>([])       // 规格匹配规则
const kpCategoryNames = ref<string[]>([])   // KP 库品类名（/api/kp/categories）
const specKeysMap = ref<Record<string, string[]>>({})  // 品类→现有 spec_key（/api/kp/spec-keys）
// match_kp / kp_reason 品类别名表（结构化行编辑器，P2a 替代 JSON）
// CPU 型号 → 内存代际默认规则（match_kp，可配）。展示用默认值（与后端 _DEFAULT_CPU_MEM_TYPE_RULES 同源）。
// 需求没写 DDR 代际时按已选 CPU 推断，避免 DDR5 平台（EPYC 9xx4/KH50000/Xeon 6）配到 DDR4。
const DEFAULT_CPU_MEM_TYPE_RULES = [
  { pattern: 'KH50000|KH-50000|KH5000', mem_type: 'DDR5' },
  { pattern: 'KH40000|KH4000|KX', mem_type: 'DDR4' },
  { pattern: 'EPYC 9', mem_type: 'DDR5' },
  { pattern: 'EPYC 7', mem_type: 'DDR4' },
  { pattern: 'XEON 6', mem_type: 'DDR5' },
  { pattern: 'XEON [1-4]', mem_type: 'DDR4' },
]
// CPU→内存代际规则行（kp_reason / spec_compliance 共用，P2a 替代 JSON）
// P2a 结构化行编辑器（替代 JSON 文本框：char_fixes / noise_patterns / cpu_mem / category_aliases）
const charFixRows = ref<Record<string, any>[]>([])
const noiseRows = ref<Record<string, any>[]>([])
const cpuMemRows = ref<Record<string, any>[]>([])
const categoryAliasRows = ref<KVRow[]>([])
// review 产出形态
const outputPreset = ref<'detailed' | 'standard' | 'concise'>('standard')
const outputFields = ref<Record<string, any>>({})
const presetReady = ref(false)  // 防 open 初始化时 preset watch 覆盖已存 output_fields

const saving = ref(false)
const recommendStrategies = ref<any[]>([])

const metaDesc = computed(() => (props.nodeType ? NODE_META[props.nodeType] || '' : ''))
const title = computed(() => {
  const m = reasoningNodeMeta(props.nodeType || '')
  return m ? `配置节点 · ${m.name}` : (props.nodeType ? `配置节点 · ${props.nodeType}` : '配置')
})
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
    fallback_order: Array.isArray(c.fallback_order) ? [...c.fallback_order] : ['exact', 'same_series', 'same_form', 'all'],
    mr_skip_react_model_missing: c.skip_react_when_model_missing ?? true,
    representative_pick: c.representative_pick || 'auto',
    fallback_strategy: c.fallback_strategy || 'fallback_representative',
    underspend_threshold: c.underspend_threshold ?? 0.5,
    expr: c.expr || '',
    prompt: c.prompt || '',
    model: c.model || 'qwen',
    mode: c.mode || 'catalog',
    model_token_regex: c.model_token_regex ?? '',
    case_source: c.case_source ?? 'internal',
    case_top_k: c.case_top_k ?? 2,
    case_match: c.case_match ?? 'tags_keyword',
    intentWords: Array.isArray(c.intent_words) ? [...c.intent_words] : [...DEFAULT_CONFIG_INTENT_WORDS],
    // 分步子任务（agent 化·拆细）：总开关 + 每步启用 + 并行 + 每步重试次数
    us_split: c.split_steps ?? true,
    us_parallel: c.parallel_sub_steps ?? true,
    us_step_retries: c.sub_step_retries ?? 1,
    us_step_type_form: c.steps?.type_form?.enabled ?? true,
    us_step_cpu_mem: c.steps?.cpu_mem?.enabled ?? true,
    us_step_drive_gpu: c.steps?.drive_gpu?.enabled ?? true,
    us_step_net_psu_raid: c.steps?.net_psu_raid?.enabled ?? true,
    ask_threshold: c.ask_threshold ?? 0,
    system_prompt: c.system_prompt ?? '',
    recommend_limit: c.recommend_limit ?? 3,
    enable_config_stage: c.enable_config_stage ?? false,
    enabled_tools: Array.isArray(c.enabled_tools) ? c.enabled_tools : ['select_models'],
    max_iterations: c.max_iterations ?? 5,
    escalate_grounding: c.escalate_grounding ?? false,
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
    strategy: c.strategy || 'one',
    llm_explain: c.llm_explain ?? true,
    confirm_scope: c.confirm_scope || '',
    default: c.default || 'accept',
    drive_spec_substitute: c.drive_spec_substitute ?? true,
    capacity_match_strategy: c.capacity_match?.strategy || 'tolerance',
    capacity_match_tolerance: c.capacity_match?.tolerance ?? 10,
    // char_fixes / noise_patterns 走结构化行编辑器（charFixRows / noiseRows），不再存 JSON 字符串
    enable_table_rows: c.enable_table_rows ?? true,
    collapse_whitespace: c.collapse_whitespace ?? true,
    parse_rules: c.parse_rules || {},
    parse_psu_min_w: c.parse_rules?.psu_min_w ?? 200,
    parse_psu_max_w: c.parse_rules?.psu_max_w ?? 3000,
    parse_mem_stick_gb: c.parse_rules?.mem_max_stick_gb ?? 1024,
    parse_mem_qty: c.parse_rules?.mem_max_qty ?? 64,
    parse_mem_total_gb: c.parse_rules?.mem_max_total_gb ?? 8192,
    parse_drive_sata_gb: c.parse_rules?.drive_default_ssd_sata_max_gb ?? 960,
    parse_drive_iface: c.parse_rules?.drive_iface_rate_max ?? 16,
    askEnabledTypes: Array.isArray(c.ask_user?.enabled_types) ? [...c.ask_user.enabled_types] : [],
    ask_recommended_type: c.ask_user?.recommended_type || '',
    askRecommendedModels: Object.entries(c.ask_user?.recommended_models ?? {}).map(([type, model]) => ({ type, model: String(model ?? '') })),
    ask_type_question: c.ask_user?.type_question || '请选择服务器类型（以下均为有货在售类型）：',
    ask_model_question: c.ask_user?.model_question || '请选择该类型下的在售机型：',
    ask_kp_intro: c.ask_user?.kp_intro || '请按以下格式填写需要的配件，没有的项可省略：',
    ask_reply_format: c.ask_user?.reply_format || 'CPU：型号 ×数量\n内存：容量 ×条数\nGPU：型号 ×数量\n硬盘：容量 ×数量\n预算：金额',
    ask_default_hint: c.ask_user?.default_hint || '不确定可回复「你推荐」，或点「跳过」让我推荐',
    bom_output_enabled: c.bom_output?.enabled ?? true,
    bom_output_mode: c.bom_output?.mode || 'live',
    bom_output_show_price: c.bom_output?.show_price ?? true,
    bom_output_show_summary: c.bom_output?.show_summary ?? true,
    bom_output_include_l6: c.bom_output?.include_l6 ?? true,
    bom_output_include_kp: c.bom_output?.include_kp ?? true,
    rec_enabled: c.recommendation?.enabled ?? true,
    rec_style: c.recommendation?.style || 'concise',
    rec_include_next_steps: c.recommendation?.include_next_steps ?? true,
    rec_next_steps: Array.isArray(c.recommendation?.next_steps) ? [...c.recommendation.next_steps] : ['CPU', '内存', '存储', '网络'],
    workloadCats: Array.isArray(c.workload_categories) ? c.workload_categories.map((x: any) => ({ ...x })) : [],
    scaleTiers: (() => {
      const st = c.scale_tiers || {}
      return { CPU: Array.isArray(st.CPU) ? st.CPU.map((x: any) => ({ ...x })) : [], 内存: Array.isArray(st['内存']) ? st['内存'].map((x: any) => ({ ...x })) : [], 存储: Array.isArray(st['存储']) ? st['存储'].map((x: any) => ({ ...x })) : [] }
    })(),
    show_why: c.show_why ?? true,
    // spec_compliance（v12）
    sc_enabled: c.enabled ?? true,
    sc_mode: c.mode || 'auto_fix',
    sc_strict_model_match: c.strict_model_match ?? true,
    sc_gpu_required_for_ai: c.gpu_required_for_ai ?? true,
    sc_max_fix_rounds: c.max_fix_rounds ?? 2,
    // cpu_mem_generation 走结构化行编辑器（cpuMemRows）
    // audit_fix（v12）
    af_enabled: c.enabled ?? true,
    af_max_retry: c.max_retry ?? 1,
    af_only_critical: c.only_critical ?? true,
    // budget_check auto_downgrade
    bc_auto_downgrade: c.auto_downgrade ?? true,
    // orchestrator（编排配置，画布「编排配置」节点）
    oc_ai_budget: c.ai_budget || 'balanced',
    oc_memory_summary: c.memory?.summary_enabled ?? true,
    oc_memory_turns: c.memory?.turns ?? 12,
    oc_memory_fields: Array.isArray(c.memory?.fields) ? [...c.memory.fields] : ['slots', 'gap', 'scene', 'cands', 'done'],
    oc_plan_preview: c.plan_preview ?? true,
    oc_parallel_enabled: c.parallel_enabled ?? false,
    oc_parallel_limit: c.parallel_limit ?? 2,
    // orchestrator 四类预算（原则5：墙钟/步数/工具调用/反问轮数；0=不限制）
    oc_wall_clock_s: c.budgets?.wall_clock_s ?? 240,
    oc_max_steps: c.budgets?.max_steps ?? 30,
    oc_max_tool_calls: c.budgets?.max_tool_calls ?? 40,
    oc_max_ask_rounds: c.budgets?.max_ask_rounds ?? 6,
    // result_check（方案自检）
    rc_plan_not_empty: c.checks?.plan_not_empty ?? true,
    rc_required_fields: c.checks?.required_fields ?? true,
    rc_qty_reasonable: c.checks?.qty_reasonable ?? true,
    rc_on_fail: c.on_fail || 'mark',
  }
  // 词表：优先读新 lexicons（5 张）；旧结构（category_lexicon/series_keyword_map）自动转新
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
  // P2a 结构化行编辑器种子（char_fixes / noise / cpu_mem / category_aliases）
  charFixRows.value = (Array.isArray(c.char_fixes) ? c.char_fixes : []).map((p: any) => ({ from: String(p?.[0] || ''), to: String(p?.[1] || '') }))
  noiseRows.value = (Array.isArray(c.noise_patterns) ? c.noise_patterns : []).map((n: any) => ({ pattern: String(n.pattern || ''), flags: String(n.flags || ''), note: String(n.note || '') }))
  const cpuMemSrc = c.cpu_mem_type_rules ?? c.cpu_mem_generation ?? DEFAULT_CPU_MEM_TYPE_RULES
  cpuMemRows.value = (Array.isArray(cpuMemSrc) ? cpuMemSrc : []).map((r: any) => ({ pattern: String(r.pattern || ''), mem_type: String(r.mem_type || '') }))
  categoryAliasRows.value = Object.entries(c.category_aliases ?? {}).map(([k, v]) => ({ key: String(k), value: Array.isArray(v) ? v.map((x: any) => String(x)) : [] }))
  // match_kp 规格匹配（P3）
  specRules.value = Array.isArray(c.spec_rules) ? c.spec_rules.map((r: any) => ({
    category: r.category || '', spec_key: r.spec_key || '',
    op: r.op || '>=', value: r.value ?? null, unit: r.unit || '',
  })) : []
  if (props.nodeType === 'select_baseline' || props.nodeType === 'model_reason') {
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

/** P2a 行编辑器 → 后端结构 */
function rowsToAliases(rows: KVRow[]): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  rows.forEach((r) => {
    const k = String(r.key || '').trim()
    if (k && Array.isArray(r.value)) out[k] = r.value.map((x) => String(x)).filter(Boolean)
  })
  return out
}
function rowsToCpuMem(rows: Record<string, any>[]): Array<{ pattern: string; mem_type: string }> {
  return rows.filter((r) => String(r.pattern || '').trim()).map((r) => ({ pattern: String(r.pattern || ''), mem_type: String(r.mem_type || '') }))
}

/** 组装当前表单 → 节点 config。JSON 解析失败已在此 toast 并返回 null。 */
function buildConfig(): Record<string, any> | null {
  if (!props.nodeKey || !configurable.value) return null
  const t = props.nodeType
  if (t === 'select_baseline') {
    return { max_plans: +form.value.max_plans, recommend_strategy_id: form.value.recommend_strategy_id || null, no_signal_strategy: form.value.no_signal_strategy || 'return_empty' }
  } else if (t === 'match_kp') {
    return {
      representative_pick: form.value.representative_pick,
      fallback_strategy: form.value.fallback_strategy || 'fallback_representative',
      spec_rules: specRules.value.filter(r => r.category && r.spec_key && r.value != null),
      type_packages: typePackages.value.filter(p => p.type_keyword),
      category_aliases: rowsToAliases(categoryAliasRows.value),
      cpu_mem_type_rules: rowsToCpuMem(cpuMemRows.value),
      capacity_match: {
        strategy: form.value.capacity_match_strategy || 'tolerance',
        tolerance: +form.value.capacity_match_tolerance || 10,
      },
    }
  } else if (t === 'budget_check') {
    return {
      underspend_threshold: +form.value.underspend_threshold,
      auto_downgrade: form.value.bc_auto_downgrade !== false,
      downgrade_axis: ['representative_pick', 'model'],
    }
  } else if (t === 'spec_compliance') {
    return {
      enabled: form.value.sc_enabled !== false,
      mode: form.value.sc_mode || 'auto_fix',
      strict_model_match: form.value.sc_strict_model_match !== false,
      gpu_required_for_ai: form.value.sc_gpu_required_for_ai !== false,
      max_fix_rounds: +form.value.sc_max_fix_rounds || 2,
      cpu_mem_generation: rowsToCpuMem(cpuMemRows.value),
    }
  } else if (t === 'audit_fix') {
    return {
      enabled: form.value.af_enabled !== false,
      max_retry: +form.value.af_max_retry || 1,
      only_critical: form.value.af_only_critical !== false,
      retry_scope: ['kp_reason', 'spec_compliance', 'compose', 'budget_check', 'llm_audit', 'audit_fix'],
    }
  } else if (t === 'review') {
    return {
      output_preset: outputPreset.value,
      output_fields: outputFields.value,
      bom_output: {
        enabled: form.value.bom_output_enabled !== false,
        mode: form.value.bom_output_mode || 'live',
        show_price: form.value.bom_output_show_price !== false,
        show_summary: form.value.bom_output_show_summary !== false,
        include_l6: form.value.bom_output_include_l6 !== false,
        include_kp: form.value.bom_output_include_kp !== false,
      },
      recommendation: {
        enabled: form.value.rec_enabled !== false,
        style: form.value.rec_style || 'concise',
        include_next_steps: form.value.rec_include_next_steps !== false,
        next_steps: Array.isArray(form.value.rec_next_steps) ? form.value.rec_next_steps.filter((s: string) => s.trim()) : [],
      },
    }
  } else if (t === 'condition') {
    return { expr: form.value.expr || '' }
  } else if (t === 'llm_ask') {
    // 反问策略 + 目录引导兜底（AI 关时用）
    const enabledTypes = (form.value.askEnabledTypes || []).filter((x: any) => String(x || '').trim())
    const recommendedModels: any = {}
    for (const r of (form.value.askRecommendedModels || [])) {
      if (r?.type?.trim() && r?.model?.trim()) recommendedModels[r.type.trim()] = r.model.trim()
    }
    return {
      strategy: form.value.strategy || 'one',
      show_why: form.value.show_why !== false,
      max_rounds: +form.value.max_rounds || 6,
      system_prompt: form.value.system_prompt || '',
      workload_categories: form.value.workloadCats.filter((x: any) => x?.label?.trim()),
      scale_tiers: {
        CPU: form.value.scaleTiers.CPU.filter((x: any) => x?.label?.trim()),
        内存: form.value.scaleTiers['内存'].filter((x: any) => x?.label?.trim()),
        存储: form.value.scaleTiers['存储'].filter((x: any) => x?.label?.trim()),
      },
      ask_user: {
        enabled_types: enabledTypes,
        recommended_type: form.value.ask_recommended_type || '',
        recommended_models: recommendedModels,
        max_rounds: +form.value.max_rounds || 6,
        type_question: form.value.ask_type_question || '',
        model_question: form.value.ask_model_question || '',
        kp_intro: form.value.ask_kp_intro || '',
        reply_format: form.value.ask_reply_format || '',
        default_hint: form.value.ask_default_hint || '',
      },
    }
  } else if (t === 'understand') {
    // 领域知识（词表/别名/数量/正则，AI 与规则兜底共用）+ AI 配置
    const mk = (id: string, name: string, kind: string, entries: LexiconEntry[]) => ({
      id, name, kind, entries: entries.filter(e => e.key && e.triggers.length),
    })
    return {
      system_prompt: form.value.system_prompt || '',
      case_source: form.value.case_source || 'internal',
      case_top_k: +form.value.case_top_k || 2,
      case_match: form.value.case_match || 'tags_keyword',
      keyword_limit: +form.value.keyword_limit || 12,
      split_steps: form.value.us_split !== false,
      parallel_sub_steps: form.value.us_parallel !== false,
      sub_step_retries: +form.value.us_step_retries || 1,
      steps: {
        type_form: { enabled: form.value.us_step_type_form !== false },
        cpu_mem: { enabled: form.value.us_step_cpu_mem !== false },
        drive_gpu: { enabled: form.value.us_step_drive_gpu !== false },
        net_psu_raid: { enabled: form.value.us_step_net_psu_raid !== false },
      },
      intent_words: form.value.intentWords.filter((w: string) => String(w || '').trim()),
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
      parse_rules: {
        psu_min_w: +form.value.parse_psu_min_w || 200,
        psu_max_w: +form.value.parse_psu_max_w || 3000,
        mem_max_stick_gb: +form.value.parse_mem_stick_gb || 1024,
        mem_max_qty: +form.value.parse_mem_qty || 64,
        mem_max_total_gb: +form.value.parse_mem_total_gb || 8192,
        drive_default_ssd_sata_max_gb: +form.value.parse_drive_sata_gb || 960,
        drive_iface_rate_max: +form.value.parse_drive_iface || 16,
      },
    }
  } else if (t === 'gap_analyze') {
    return { llm_explain: form.value.llm_explain !== false }
  } else if (t === 'scene_decide') {
    return { fallback_scene: form.value.fallback_scene || '通用计算服务器', decide_threshold: +form.value.decide_threshold || 30 }
  } else if (t === 'model_reason') {
    // AI 推理 + 选型规则（与 select_baseline 同源，避免保存丢失）
    return {
      enabled_tools: Array.isArray(form.value.enabled_tools) ? form.value.enabled_tools : ['select_models'],
      max_iterations: +form.value.max_iterations || 6,
      max_plans: +form.value.max_plans || 6,
      system_prompt: form.value.system_prompt || '',
      recommend_strategy_id: form.value.recommend_strategy_id ?? null,
      no_signal_strategy: form.value.no_signal_strategy || 'return_empty',
      fallback_order: form.value.fallback_order || ['exact', 'same_series', 'same_form', 'all'],
      skip_react_when_model_missing: form.value.mr_skip_react_model_missing !== false,
    }
  } else if (t === 'kp_reason') {
    // AI 推理 + 匹配规则（与 match_kp 同源，含别名/内存代际，避免保存丢失）
    return {
      enabled_tools: Array.isArray(form.value.enabled_tools) ? form.value.enabled_tools : ['pick_kp_parts'],
      max_iterations: +form.value.max_iterations || 6,
      system_prompt: form.value.system_prompt || '',
      drive_spec_substitute: form.value.drive_spec_substitute !== false,
      representative_pick: form.value.representative_pick || 'auto',
      fallback_strategy: form.value.fallback_strategy || 'fallback_representative',
      spec_rules: specRules.value.filter(r => r.category && r.spec_key && r.value != null),
      type_packages: typePackages.value.filter(p => p.type_keyword),
      category_aliases: rowsToAliases(categoryAliasRows.value),
      cpu_mem_type_rules: rowsToCpuMem(cpuMemRows.value),
      capacity_match: {
        strategy: form.value.capacity_match_strategy || 'tolerance',
        tolerance: +form.value.capacity_match_tolerance || 10,
      },
    }
  } else if (t === 'llm_confirm') {
    return { confirm_scope: form.value.confirm_scope || '', default: form.value.default || 'accept' }
  } else if (t === 'llm_audit') {
    return { reference_limit: +form.value.reference_limit || 2, system_prompt: form.value.system_prompt || '' }
  } else if (t === 'llm') {
    return { prompt: form.value.prompt || '', model: form.value.model || 'qwen' }
  } else if (t === 'text_clean') {
    return {
      char_fixes: charFixRows.value.filter((r) => String(r.from || '').trim() || String(r.to || '').trim())
        .map((r) => [String(r.from || ''), String(r.to || '')]),
      noise_patterns: noiseRows.value.filter((r) => String(r.pattern || '').trim())
        .map((r) => ({ pattern: String(r.pattern || ''), flags: String(r.flags || ''), note: String(r.note || '') })),
      enable_table_rows: form.value.enable_table_rows !== false,
      collapse_whitespace: form.value.collapse_whitespace !== false,
    }
  } else if (t === 'orchestrator') {
    // 编排配置（不执行，只提供全局策略；后端 orchestrator._load_orch_cfg 读取）
    return {
      ai_budget: form.value.oc_ai_budget || 'balanced',
      memory: {
        summary_enabled: form.value.oc_memory_summary !== false,
        turns: +form.value.oc_memory_turns || 12,
        fields: Array.isArray(form.value.oc_memory_fields) && form.value.oc_memory_fields.length
          ? form.value.oc_memory_fields : ['slots', 'gap', 'scene', 'cands', 'done'],
      },
      plan_preview: form.value.oc_plan_preview !== false,
      parallel_enabled: !!form.value.oc_parallel_enabled,
      parallel_limit: +form.value.oc_parallel_limit || 2,
      budgets: {
        wall_clock_s: +form.value.oc_wall_clock_s || 0,
        max_steps: +form.value.oc_max_steps || 0,
        max_tool_calls: +form.value.oc_max_tool_calls || 0,
        max_ask_rounds: +form.value.oc_max_ask_rounds || 0,
      },
    }
  } else if (t === 'result_check') {
    // 方案自检（确定性）：检查项 + 失败处理
    return {
      checks: {
        plan_not_empty: form.value.rc_plan_not_empty !== false,
        required_fields: form.value.rc_required_fields !== false,
        qty_reasonable: form.value.rc_qty_reasonable !== false,
      },
      on_fail: form.value.rc_on_fail || 'mark',
    }
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

    <!-- understand：领域知识（5 张词表/规格别名/数量解析）+ AI 分步理解配置 -->
    <a-form v-if="nodeType === 'understand'" layout="vertical">
      <template v-if="nodeType === 'understand'">
        <a-alert type="info" show-icon banner message="领域知识库：词表/规格别名/数量解析由 AI 理解与规则兜底【共用】——LLM 理解时自动注入这些映射（如 兆芯→Polaris），understand 节点统一管理" style="margin-bottom: 12px" />
        <a-divider orientation="left" class="rf-sec">理解方式（分步子任务·agent 化）</a-divider>
        <a-form-item label="分步理解">
          <a-switch v-model:checked="form.us_split" />
          <p class="rf-hint">把理解拆成 4 个聚焦子任务并行执行（类型/系列/形态、CPU/内存、硬盘/GPU、网卡/电源/RAID）：每个子任务字段少、模型思考短，比一次性大填表更快更稳（实测空回率从 ~50% 降到 ~0%）。关掉则退回单次大填表。</p>
        </a-form-item>
        <a-form-item label="并行执行">
          <a-switch v-model:checked="form.us_parallel" />
          <p class="rf-hint">4 个子任务互相独立，默认并行（总墙钟 ~7-10s）。关掉则串行。</p>
        </a-form-item>
        <a-form-item label="每步失败重试次数">
          <a-input-number v-model:value="form.us_step_retries" :min="0" :max="3" style="width:100%" />
          <p class="rf-hint">单个子任务失败后便宜重试（每次 2-8s，默认 1）。仍失败只丢该子字段，交给反问补齐，不再整表失败。</p>
        </a-form-item>
        <a-form-item label="启用的子任务">
          <a-checkbox v-model:checked="form.us_step_type_form">类型/系列/形态</a-checkbox>
          <a-checkbox v-model:checked="form.us_step_cpu_mem">CPU/内存</a-checkbox>
          <a-checkbox v-model:checked="form.us_step_drive_gpu">硬盘/GPU</a-checkbox>
          <a-checkbox v-model:checked="form.us_step_net_psu_raid">网卡/电源/RAID</a-checkbox>
          <p class="rf-hint">关掉某一步 = 该字段不 AI 提取，交给缺口分析反问补齐（如只配 CPU/内存的最小需求可关掉 GPU 步）。</p>
        </a-form-item>
        <a-form-item label="相似案例检索（few-shot grounding）">
          <a-space wrap>
            <a-select v-model:value="form.case_source" style="width:110px">
              <a-select-option value="internal">案例库</a-select-option>
              <a-select-option value="off">关</a-select-option>
            </a-select>
            <a-input-number v-model:value="form.case_top_k" :min="0" :max="5" placeholder="top_k" style="width:80px" />
            <a-select v-model:value="form.case_match" style="width:150px">
              <a-select-option value="tags_keyword">标签+关键词</a-select-option>
              <a-select-option value="keyword">关键词</a-select-option>
              <a-select-option value="tags">标签</a-select-option>
            </a-select>
          </a-space>
        </a-form-item>
        <a-form-item label="System Prompt（可覆盖默认）">
          <a-textarea v-model:value="form.system_prompt" :rows="3" placeholder="留空用默认提示词" />
        </a-form-item>
        <a-divider orientation="left" class="rf-sec">领域知识（AI 与规则共用）</a-divider>
        <a-form-item label="自然进入选配·意图词（intent_words）">
          <ChipListInput v-model="form.intentWords" placeholder="输入说法后回车，如：帮我配台服务器" />
          <p class="rf-hint">方案助手里用户聊到这些说法时，自动进入需求分析（命中任一子串即触发；不命中则正常聊天，弱意图会给「开始选配」按钮）。改这里全局生效。</p>
        </a-form-item>
        <a-divider orientation="left" class="rf-sec">解析规则（AI 兜底·阈值可调）</a-divider>
        <p class="rf-hint">以下阈值控制规则解析引擎（AI 关/失败时的兜底 + 数量/容量校验）：超出范围的信号会被忽略。</p>
        <a-form-item label="电源功率范围（W）">
          <a-space>
            <a-input-number v-model:value="form.parse_psu_min_w" :min="0" :max="5000" placeholder="min" style="width:110px" />
            <span>—</span>
            <a-input-number v-model:value="form.parse_psu_max_w" :min="0" :max="10000" placeholder="max" style="width:110px" />
          </a-space>
          <p class="rf-hint">默认 200–3000W；CPU TDP（如 360W）不在此判定范围</p>
        </a-form-item>
        <a-form-item label="内存单条/条数/总量上限（G/条/G）">
          <a-space>
            <a-input-number v-model:value="form.parse_mem_stick_gb" :min="16" :max="2048" placeholder="单条" style="width:100px" />
            <a-input-number v-model:value="form.parse_mem_qty" :min="1" :max="128" placeholder="条数" style="width:100px" />
            <a-input-number v-model:value="form.parse_mem_total_gb" :min="1024" :max="32768" placeholder="总量" style="width:110px" />
          </a-space>
          <p class="rf-hint">默认 1024G / 64 条 / 8TB；超出视为识别异常忽略</p>
        </a-form-item>
        <a-form-item label="盘件：无接口 SSD 默认 SATA 阈值（G）">
          <a-input-number v-model:value="form.parse_drive_sata_gb" :min="0" :max="8192" style="width:120px" />
          <p class="rf-hint">默认 ≤960G（系统盘/启动盘档）SSD 按 SATA 出；大容量数据盘不强制</p>
        </a-form-item>
        <a-form-item label="盘件：接口速率过滤阈值（G）">
          <a-input-number v-model:value="form.parse_drive_iface" :min="0" :max="100" style="width:120px" />
          <p class="rf-hint">默认 ≤16G 且后跟 SATA/SAS → 视为接口速率（如 6G SATA）而非盘容量</p>
        </a-form-item>
      </template>
      <a-alert v-else type="info" show-icon banner message="规则理解兜底（AI 失效才走）：requirement_parser 正则解析需求的单点节点；领域知识/解析规则默认共用「需求理解」节点配置" style="margin-bottom: 12px" />
      <a-divider orientation="left" class="rf-sec">提取参数</a-divider>
      <p class="rf-hint">AI 失效兜底节点：只做分词 + 词表命中（requirement_parser 正则）。明确度规则→clarity_check 节点；反问话术→ask_user 节点；预算映射→budget_check 节点。</p>
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
        <p class="rf-hint">识别型号 token 的正则（understand 理解 + pick 过滤<b>同源</b>）。默认必含数字，避免 nvme/sata 品类词误命中。改它要懂正则。</p>
        <a-input v-model:value="modelTokenRegex" placeholder="如 ^(?=.*[0-9])(...)$" />
      </a-form-item>
    </a-form>

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
      <a-form-item label="超预算自动降配（auto_downgrade）">
        <a-switch v-model:checked="form.bc_auto_downgrade" />
        <p class="rf-hint">开：超预算时确定性降配一轮（代表件换最低价→重组装→重校验），不依赖 LLM；仍超则照常标超预算</p>
      </a-form-item>
      <RequirementRuleList rule-type="budget" />
    </div>

    <!-- select_baseline：保留 -->
    <a-form v-else-if="nodeType === 'select_baseline' || nodeType === 'model_reason'" layout="vertical">
      <template v-if="nodeType === 'model_reason'">
        <a-alert type="info" show-icon banner message="AI 机型推理：LLM 用 select_models 工具查真实在售机型后决策 + 给理由；型号/料号精确性由工具保证，失败自动降级下方规则" style="margin-bottom: 12px" />
        <a-divider orientation="left" class="rf-sec">AI 推理</a-divider>
        <a-form-item label="ReAct 工具（enabled_tools）">
          <a-select v-model:value="form.enabled_tools" mode="multiple" style="width:100%">
            <a-select-option value="select_models">select_models 机型查询</a-select-option>
            <a-select-option value="search_cases">search_cases 案例检索</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="ReAct 循环上限（max_iterations）">
          <a-input-number v-model:value="form.max_iterations" :min="1" :max="10" style="width:100%" />
        </a-form-item>
        <a-form-item label="System Prompt（可覆盖默认）">
          <a-textarea v-model:value="form.system_prompt" :rows="3" placeholder="留空用默认提示词" />
        </a-form-item>
        <a-divider orientation="left" class="rf-sec">选型参数（AI 与规则共用）</a-divider>
      </template>
      <template v-else>
        <a-divider orientation="left" class="rf-sec">基础参数</a-divider>
      </template>
      <a-form-item label="候选方案数（max_plans）"><a-input-number v-model:value="form.max_plans" :min="1" :max="5" style="width:100%" /></a-form-item>
      <a-form-item label="推荐策略（model_recommend）">
        <a-select v-model:value="form.recommend_strategy_id" allow-clear placeholder="不限（读全部 active）" style="width:100%">
          <a-select-option v-for="r in recommendStrategies" :key="r.id" :value="r.id">{{ r.name }}（{{ r.scope?.series || '通用' }}）</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="点名机型不在目录时跳过 AI 推理（推荐开）">
        <a-switch v-model:checked="form.mr_skip_react_model_missing" />
        <p class="rf-hint">需求点名了具体品牌机型（如 联想 WA5480 G3）但目录没有 → ReAct 反复确认「没有」只会烧 30s，直接按规则降级选最接近在售机型（配 fallback_order 放宽 + 白盒说明）。关掉则强制走 AI 推理。</p>
      </a-form-item>
      <a-form-item label="选型放宽顺序（fallback_order）">
        <a-checkbox-group v-model:value="form.fallback_order" style="width:100%">
          <a-checkbox value="exact">精确（类型+系列+形态）</a-checkbox>
          <a-checkbox value="same_series">放宽形态（保系列）</a-checkbox>
          <a-checkbox value="same_form">放宽系列（保形态）</a-checkbox>
          <a-checkbox value="all">只保类型（全放宽）</a-checkbox>
        </a-checkbox-group>
        <p class="rf-hint">严格条件无机型时按此顺序逐级放宽，并把「放宽了平台系列/机箱形态」白盒标注在方案上（如：库内无 Intel 平台 AI 机型 → 按同类型最接近给出）。只勾「精确」= 严格匹配、无则返空反问。</p>
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
    <a-form v-else-if="nodeType === 'match_kp' || nodeType === 'kp_reason'" layout="vertical">
      <template v-if="nodeType === 'kp_reason'">
        <a-alert type="info" show-icon banner message="AI 配件推理：LLM 用 pick_kp_parts 工具查真实配件库、确认数量/规格后给理由；精确匹配仍由下方规则执行（compose 需要完整数据），失败自动降级" style="margin-bottom: 12px" />
        <a-divider orientation="left" class="rf-sec">AI 推理</a-divider>
        <a-form-item label="ReAct 工具（enabled_tools）">
          <a-select v-model:value="form.enabled_tools" mode="multiple" style="width:100%">
            <a-select-option value="pick_kp_parts">pick_kp_parts 配件查询</a-select-option>
            <a-select-option value="search_cases">search_cases 案例检索</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="ReAct 循环上限（max_iterations）">
          <a-input-number v-model:value="form.max_iterations" :min="1" :max="10" style="width:100%" />
        </a-form-item>
        <a-form-item label="System Prompt（可覆盖默认）">
          <a-textarea v-model:value="form.system_prompt" :rows="3" placeholder="留空用默认提示词" />
        </a-form-item>
        <a-divider orientation="left" class="rf-sec">匹配参数（AI 与规则共用）</a-divider>
      </template>
      <template v-else>
        <a-divider orientation="left" class="rf-sec">基础参数</a-divider>
      </template>
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
      <a-form-item label="盘件规格替代（drive_spec_substitute）">
        <a-switch v-model:checked="form.drive_spec_substitute" />
        <p class="rf-hint">开：需求容量库无同名件时按容量/类型数值选替代件（BOM 标"替代"）；关：严格 unmatched 需手填</p>
      </a-form-item>
      <a-form-item label="容量匹配策略（capacity_match.strategy）">
        <a-radio-group v-model:value="form.capacity_match_strategy" button-style="solid">
          <a-radio-button value="tolerance">容差近似（默认）</a-radio-button>
          <a-radio-button value="strict_min">严格下限（≥需求）</a-radio-button>
        </a-radio-group>
        <p class="rf-hint">容差近似=±容差% 内就近选件（可能略低于需求，如 1T 需求选 960G）；严格下限=只选容量≥需求的件。AI 识别出"1T以上/至少"（gte）、"以下/最多"（lte）时自动按严格语义执行，不受此默认策略影响。</p>
      </a-form-item>
      <a-form-item v-if="form.capacity_match_strategy === 'tolerance'" label="容量容差 %（capacity_match.tolerance）">
        <a-input-number v-model:value="form.capacity_match_tolerance" :min="0" :max="50" :step="1" style="width:120px" />
        <p class="rf-hint">默认 10（±10% 内视为同容量档，可能略低于需求）。</p>
      </a-form-item>
      <a-form-item label="品类别名表（category_aliases）">
        <p class="rf-hint">需求里的品类词 ≠ 库内品类名时在这配「品类 → 别名」，匹配时先按别名归一到品类（如 记忆体 → 内存）。</p>
        <EditableKVTable v-model="categoryAliasRows" key-placeholder="品类名（如 内存 / 网卡）" value-placeholder="别名（回车添加）" />
      </a-form-item>
      <a-form-item label="CPU→内存代际规则（cpu_mem_type_rules）">
        <JsonRowEditor
          v-model="cpuMemRows"
          :columns="[
            { key: 'pattern', label: 'CPU 型号正则', placeholder: '如 EPYC 9 / KH50000' },
            { key: 'mem_type', label: '内存代际', type: 'select', options: [{ value: 'DDR4', label: 'DDR4' }, { value: 'DDR5', label: 'DDR5' }] },
          ]"
          add-label="＋ 添加规则"
          hint="需求没写 DDR 代际时按 CPU 型号推断（顺序敏感，首个正则命中即定）。加新 CPU 型号 / 改代际在这配，不用动代码。"
        />
      </a-form-item>
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
      <a-divider orientation="left" class="rf-sec">BOM 明细输出（方案助手/企微分析结果）</a-divider>
      <a-form-item label="在分析结果里附 BOM 明细">
        <a-switch v-model:checked="form.bom_output_enabled" />
        <p class="rf-hint">关 = 分析结果只给方案清单，不附 BOM 明细文本</p>
      </a-form-item>
      <a-form-item label="生成方式（mode）">
        <a-radio-group v-model:value="form.bom_output_mode" button-style="solid">
          <a-radio-button value="live">走 BOM 模板（与前端查看一致）</a-radio-button>
          <a-radio-button value="excel">配置单平铺</a-radio-button>
        </a-radio-group>
        <p class="rf-hint">live = 按该机型绑定的 BOM 模板求值（模板行+变量）；excel = bom_excel_rows 原始配置单。推荐 live，和用户点开看的 BOM 一致</p>
      </a-form-item>
      <a-form-item label="显示内容">
        <div class="rf-checks">
          <a-checkbox v-model:checked="form.bom_output_show_summary">顶部摘要（总价/件数）</a-checkbox>
          <a-checkbox v-model:checked="form.bom_output_show_price">KP 含单价</a-checkbox>
          <a-checkbox v-model:checked="form.bom_output_include_l6">L6 配置单</a-checkbox>
          <a-checkbox v-model:checked="form.bom_output_include_kp">KP 配置单</a-checkbox>
        </div>
      </a-form-item>
      <a-divider orientation="left" class="rf-sec">推荐输出（方案助手·对话式推荐）</a-divider>
      <a-form-item label="附推荐语（推荐最优方案 + 理由 + 下一步引导）">
        <a-switch v-model:checked="form.rec_enabled" />
        <p class="rf-hint">开 = 分析结果先给对话式推荐（LLM 生成，带理由），BOM 明细附后；关/失败 = 方案清单 + BOM</p>
      </a-form-item>
      <a-form-item label="推荐风格">
        <a-radio-group v-model:value="form.rec_style" button-style="solid">
          <a-radio-button value="concise">简洁</a-radio-button>
          <a-radio-button value="detailed">详细</a-radio-button>
        </a-radio-group>
      </a-form-item>
      <a-form-item label="下一步引导">
        <a-switch v-model:checked="form.rec_include_next_steps" />
      </a-form-item>
      <a-form-item v-if="form.rec_include_next_steps" label="引导项（next_steps）">
        <ChipListInput v-model="form.rec_next_steps" placeholder="如 CPU / 内存 / 存储 / 网络" />
        <p class="rf-hint">推荐语结尾会问"从哪开始"，选项即这些引导项</p>
      </a-form-item>
    </a-form>

    <!-- condition：保留 -->
    <a-form v-else-if="nodeType === 'condition'" layout="vertical">
      <a-form-item label="条件表达式（simpleeval 安全求值）">
        <a-input v-model:value="form.expr" placeholder="如：series == 'Polaris'" />
        <p class="rf-hint">可用变量：series / form / categories（列表）/ keywords（列表）/ <b>clarity</b>（explicit·partial·unclear）/ <b>clarity_capped</b>（bool）/ <b>budget</b>（数值）/ <b>has_budget</b>（bool）/ <b>missing_fields</b>（列表）/ <b>llm_enabled</b>（bool，全局 AI 开关，route_fork/cond_audit 双路线分叉用）。空列表判断用 <code>not missing_fields</code>（simpleeval 不支持 len()）。求值 true 走真分支（sourceHandle='true'），false 走假分支。</p>
      </a-form-item>
    </a-form>

    <!-- scene_decide：场景判定（AI/存储/通用 × 系列 × 形态） -->
    <a-form v-else-if="nodeType === 'scene_decide'" layout="vertical">
      <a-alert type="info" show-icon banner message="场景判定：规则判定（带证据白盒）为确定性本体；AI 增强在后续机型/配件推理阶段体现" style="margin-bottom: 12px" />
      <a-alert type="info" show-icon banner message="白盒：输出带证据（为什么选这个场景/系列/形态）。映射权威数据源 = system_config.scene_mapping（平台配置）" style="margin-bottom: 12px" />
      <a-divider orientation="left" class="rf-sec">判定参数</a-divider>
      <a-form-item label="判定阈值（decide_threshold）">
        <a-input-number v-model:value="form.decide_threshold" :min="0" :max="100" style="width:100%" />
        <p class="rf-hint">场景分≥此值才判定；低于回退默认场景（避免过度反问）。</p>
      </a-form-item>
      <a-form-item label="默认场景（fallback_scene）">
        <a-input v-model:value="form.fallback_scene" placeholder="通用计算服务器" />
        <p class="rf-hint">无强场景信号时回退的类型（需与 l6.server_types 名称一致）。</p>
      </a-form-item>
    </a-form>

    <!-- 新能力节点通用 AI 配置（2026-08 重构：合并单路后；understand/scene/model/kp 各自表单分支） -->
    <a-form v-else-if="['llm_ask','gap_analyze','llm_confirm','text_clean'].includes(nodeType || '')" layout="vertical">
      <template v-if="nodeType === 'llm_ask'">
        <a-divider orientation="left" class="rf-sec">反问策略</a-divider>
        <a-form-item label="追问策略">
          <a-radio-group v-model:value="form.strategy" button-style="solid">
            <a-radio-button value="one">问最关键 1 个</a-radio-button>
            <a-radio-button value="all">列全缺失项</a-radio-button>
          </a-radio-group>
          <p class="rf-hint">LLM 基于完整上下文（需求+已理解+缺口+在售目录）生成问题，带选项与理由</p>
        </a-form-item>
        <a-form-item label="问题带理由（show_why）">
          <a-switch v-model:checked="form.show_why" />
          <p class="rf-hint">开：反问带"为什么问这个"（小字，LLM 生成）；关：只问不带理由</p>
        </a-form-item>
        <a-form-item label="工作负载分类（首问缺场景/用途时用）">
          <div v-for="(w, wi) in form.workloadCats" :key="wi" class="rf-wl-row">
            <a-input v-model:value="w.label" placeholder="名称（如 虚拟化 / 云主机）" style="width:170px" />
            <a-input v-model:value="w.desc" placeholder="说明（如 运行多少台虚拟机？）" style="flex:1" />
            <a-input v-model:value="w.type" placeholder="映射类型（如 通用计算服务器）" style="width:190px" />
            <a-button type="text" danger size="small" @click="form.workloadCats.splice(wi, 1)">删</a-button>
          </div>
          <a-button size="small" type="dashed" block @click="form.workloadCats.push({ label: '', desc: '', type: '' })">＋ 添加工作负载</a-button>
          <p class="rf-hint">缺场景/用途时反问"工作负载"，用户选后映射到对应类型；type 需与在售类型名一致（如 通用计算服务器 / AI / 加速计算服务器 / 存储服务器）</p>
        </a-form-item>
        <a-form-item label="分档引导（scale_tiers）">
          <div v-for="sk in ['CPU', '内存', '存储']" :key="sk" style="margin-bottom:10px">
            <div class="rf-sec" style="font-weight:600;margin-bottom:4px">{{ sk }}</div>
            <div v-for="(t, ti) in form.scaleTiers[sk]" :key="ti" class="rf-wl-row">
              <a-input v-model:value="t.label" placeholder="档位名（如 小型）" style="width:90px" />
              <a-input v-model:value="t.desc" placeholder="描述（如 访问量较低）" style="flex:1" />
              <a-input v-model:value="t.recommend" placeholder="推荐（如 16-24 核）" style="width:160px" />
              <a-button type="text" danger size="small" @click="form.scaleTiers[sk].splice(ti, 1)">删</a-button>
            </div>
            <a-button size="small" type="dashed" block @click="form.scaleTiers[sk].push({ label: '', desc: '', recommend: '' })">＋ 添加{{ sk }}档位</a-button>
          </div>
          <p class="rf-hint">缺 CPU/内存/存储 规格时，按规模给档位（选项/推荐参考），降低回答门槛</p>
        </a-form-item>
        <a-form-item label="反问轮次上限（max_rounds）">
          <a-input-number v-model:value="form.max_rounds" :min="1" :max="10" style="width:100%" />
        </a-form-item>
        <a-form-item label="System Prompt（AI 生成话术的规则）">
          <a-textarea v-model:value="form.system_prompt" :rows="4" placeholder="留空 = 用下面的默认提示词" />
          <p class="rf-hint">AI 开时反问话术由 LLM 按此规则【动态生成】（每次按需求/缺口/目录现场生成，无固定话术）；留空用默认，填写则覆盖。</p>
          <a-collapse :bordered="false">
            <a-collapse-panel key="default-prompt" header="查看/恢复默认提示词">
              <pre class="rf-json" style="white-space:pre-wrap;margin:0">{{ DEFAULT_LLM_ASK_PROMPT }}</pre>
              <a-button size="small" style="margin-top:8px" @click="form.system_prompt = ''">清空以使用默认</a-button>
            </a-collapse-panel>
          </a-collapse>
        </a-form-item>
        <a-collapse :bordered="false">
          <a-collapse-panel key="catalog" header="目录引导兜底（AI 关时 · 引导文案/选项）">
            <p class="rf-hint">AI 关闭/失败时走目录引导（类型→机型→KP 格式）；这里配引导文案与推荐。AI 开时 LLM 自动生成问题，不读这些。</p>
            <a-form-item label="启用类型（enabled_types）">
              <ChipListInput v-model="form.askEnabledTypes" placeholder="输入在售类型名后回车，如 AI / 加速计算服务器" />
              <p class="rf-hint">空 = 全部有货在售类型；配了只推这些类型（选项 100% 来自产品目录，禁编）</p>
            </a-form-item>
            <a-form-item label="推荐类型（客户答「不确定」时）">
              <a-input v-model:value="form.ask_recommended_type" placeholder="如 AI / 加速计算服务器" />
            </a-form-item>
            <a-form-item label="推荐机型映射（recommended_models）">
              <div v-for="(r, ri) in form.askRecommendedModels" :key="ri" class="rf-wl-row">
                <a-input v-model:value="r.type" placeholder="类型（如 AI / 加速计算服务器）" style="width:210px" />
                <a-input v-model:value="r.model" placeholder="默认机型名（如 ESA24V3-P）" style="flex:1" />
                <a-button type="text" danger size="small" @click="form.askRecommendedModels.splice(ri, 1)">删</a-button>
              </div>
              <a-button size="small" type="dashed" block @click="form.askRecommendedModels.push({ type: '', model: '' })">＋ 添加类型→机型映射</a-button>
              <p class="rf-hint">客户没选机型时按此映射给默认机型；机型名需与在售机型一致（空映射不保存）</p>
            </a-form-item>
            <a-form-item label="类型问题文案（type_question）">
              <a-input v-model:value="form.ask_type_question" />
            </a-form-item>
            <a-form-item label="机型问题文案（model_question）">
              <a-input v-model:value="form.ask_model_question" />
            </a-form-item>
            <a-form-item label="配件引导语（kp_intro）">
              <a-input v-model:value="form.ask_kp_intro" />
            </a-form-item>
            <a-form-item label="回复格式模板（reply_format）">
              <a-textarea v-model:value="form.ask_reply_format" :rows="5" class="rf-json" />
            </a-form-item>
            <a-form-item label="默认提示（default_hint）">
              <a-input v-model:value="form.ask_default_hint" />
            </a-form-item>
          </a-collapse-panel>
        </a-collapse>
      </template>

      <template v-if="nodeType === 'gap_analyze'">
        <a-divider orientation="left" class="rf-sec">明确度判定</a-divider>
        <a-form-item label="LLM 解释缺失原因（llm_explain）">
          <a-switch v-model:checked="form.llm_explain" />
          <p class="rf-hint">开：LLM 说明缺什么、哪个对选型最关键；关：纯槽位覆盖度判定</p>
        </a-form-item>
        <a-divider orientation="left" class="rf-sec">期望槽位清单（L0/L1/L2）</a-divider>
        <p class="rf-hint">明确度 = 已填槽位 vs 期望清单：L0 缺≥阈值反问 / L1 提示可补 / L2 系统推导不问。此处编辑系统配置（全局生效）。</p>
        <SlotListEditor />
      </template>

      <template v-if="nodeType === 'llm_confirm'">
        <a-divider orientation="left" class="rf-sec">确认策略</a-divider>
        <a-form-item label="确认范围（confirm_scope）">
          <a-input v-model:value="form.confirm_scope" placeholder="如：机型/配件" />
        </a-form-item>
        <a-form-item label="默认决策">
          <a-select v-model:value="form.default" style="width:100%">
            <a-select-option value="accept">默认采纳</a-select-option>
            <a-select-option value="ignore">默认忽略</a-select-option>
          </a-select>
        </a-form-item>
      </template>

      <template v-if="nodeType === 'text_clean'">
        <a-divider orientation="left" class="rf-sec">清洗规则</a-divider>
        <a-form-item label="字符修正（char_fixes）">
          <JsonRowEditor
            v-model="charFixRows"
            :columns="[
              { key: 'from', label: '原字符', placeholder: '如 NMVE' },
              { key: 'to', label: '替换为', placeholder: '如 NVMe' },
            ]"
            add-label="＋ 添加字符修正"
            hint="有序字符修正对：拼写颠倒（NMVE→NVMe）、全角加号→半角、×→*"
          />
        </a-form-item>
        <a-form-item label="噪音过滤（noise_patterns）">
          <JsonRowEditor
            v-model="noiseRows"
            :columns="[
              { key: 'pattern', label: '正则', placeholder: '如时间戳正则' },
              { key: 'flags', label: '修饰符', placeholder: '如 i（可留空）' },
              { key: 'note', label: '说明', placeholder: '如 时间戳 / 问候语' },
            ]"
            add-label="＋ 添加噪音规则"
            hint="正则逐个从文本删除（如时间戳/问候语），删了不影响规格解析；flags 为 re 修饰符（i=忽略大小写），可留空"
          />
        </a-form-item>
        <a-form-item label="表格行归一（enable_table_rows）">
          <a-switch v-model:checked="form.enable_table_rows" />
          <p class="rf-hint">Markdown/管道表格行 → "内容 *N"（数量列转乘号后缀）</p>
        </a-form-item>
        <a-form-item label="空白折叠（collapse_whitespace）">
          <a-switch v-model:checked="form.collapse_whitespace" />
        </a-form-item>
      </template>

    </a-form>

    <!-- spec_compliance：规格合规校验（v12，确定性红线前） -->
    <a-form v-else-if="nodeType === 'spec_compliance'" layout="vertical">
      <a-alert type="info" show-icon banner message="规格合规校验（确定性）：kp_reason 之后、compose 之前，检查需求规格 vs 实配 —— AI 缺卡自动补、型号降级/内存代际不符标 issue；不依赖 LLM" style="margin-bottom: 12px" />
      <a-form-item label="启用">
        <a-switch v-model:checked="form.sc_enabled" />
      </a-form-item>
      <a-form-item label="模式（mode）">
        <a-radio-group v-model:value="form.sc_mode" button-style="solid">
          <a-radio-button value="auto_fix">自动修复</a-radio-button>
          <a-radio-button value="flag_only">仅标记</a-radio-button>
        </a-radio-group>
        <p class="rf-hint">auto_fix=能确定性补的（缺卡/缺盘/内存代际）自动补并重跑链；flag_only=只标 issue 交审计</p>
      </a-form-item>
      <a-form-item label="AI 类型强制 GPU（gpu_required_for_ai）">
        <a-switch v-model:checked="form.sc_gpu_required_for_ai" />
        <p class="rf-hint">开：AI/加速计算服务器即使需求没提显卡也配代表 GPU（配件库有卡）</p>
      </a-form-item>
      <a-form-item label="型号严格匹配（strict_model_match）">
        <a-switch v-model:checked="form.sc_strict_model_match" />
        <p class="rf-hint">开：需求明确 CPU 型号（如 EPYC 9654）时，实配不一致标 issue（不自动造件）</p>
      </a-form-item>
      <a-form-item label="修复重跑上限（max_fix_rounds）">
        <a-input-number v-model:value="form.sc_max_fix_rounds" :min="1" :max="5" style="width:100%" />
      </a-form-item>
      <a-form-item label="CPU→内存代际规则（cpu_mem_generation，同 kp_reason）">
        <JsonRowEditor
          v-model="cpuMemRows"
          :columns="[
            { key: 'pattern', label: 'CPU 型号正则', placeholder: '如 EPYC 9 / KH50000' },
            { key: 'mem_type', label: '内存代际', type: 'select', options: [{ value: 'DDR4', label: 'DDR4' }, { value: 'DDR5', label: 'DDR5' }] },
          ]"
          add-label="＋ 添加规则"
          hint="CPU 型号正则 → 期望内存代际；实配内存代际不符时 auto_fix 重设并重跑"
        />
      </a-form-item>
    </a-form>

    <!-- audit_fix：审计自纠（v12，执行中自我修正闭环） -->
    <a-form v-else-if="nodeType === 'audit_fix'" layout="vertical">
      <a-alert type="info" show-icon banner message="审计自纠（确定性）：llm_audit 检出问题 → 补 GPU/抬内存目标 → 重跑 kp_reason→spec_compliance→compose→budget_check→llm_audit 再审计一次；仍不过才 review 标人工复核（把 llm_audit 从「事后审计」升级为「执行中自纠」）" style="margin-bottom: 12px" />
      <a-form-item label="启用">
        <a-switch v-model:checked="form.af_enabled" />
      </a-form-item>
      <a-form-item label="重跑上限（max_retry）">
        <a-input-number v-model:value="form.af_max_retry" :min="0" :max="3" style="width:100%" />
        <p class="rf-hint">0 = 关闭自纠（等价旧行为：只标记）；1 = 默认，自纠一轮再审计</p>
      </a-form-item>
      <a-form-item label="仅处理关键问题（only_critical）">
        <a-switch v-model:checked="form.af_only_critical" />
        <p class="rf-hint">开：只对缺卡/内存严重不足这类关键问题重跑；一般提示不触发</p>
      </a-form-item>
    </a-form>

    <!-- compose：确定性红线，无可配参数（2026-08 从可配置列表移除） -->
    <a-form v-else-if="nodeType === 'compose'" layout="vertical">
      <a-alert type="info" show-icon banner message="方案组装（确定性红线）：把选型决策组装成整机 BOM（价格/兼容性/PSU/线缆派生）。本节点无可配参数——电源功率由系统按负载推断（需求显式写时优先），价格/兼容性永远确定性计算，LLM 不可碰。" />
    </a-form>

    <!-- llm_audit：AI 方案校对（bom_cases few-shot + 规则硬校验兜底） -->
    <a-form v-else-if="nodeType === 'llm_audit'" layout="vertical">
      <a-divider orientation="left" class="rf-sec">行为参数</a-divider>
      <a-form-item label="few-shot 参考案例数（reference_limit）">
        <a-input-number v-model:value="form.reference_limit" :min="0" :max="5" style="width:100%" />
        <p class="rf-hint">取同系列（平台）的 bom_cases 当「这类需求该长什么样」的参考样本；平台不同不会硬套。0 = 不带参考。</p>
      </a-form-item>
      <a-form-item label="System Prompt（可覆盖默认）">
        <a-textarea v-model:value="form.system_prompt" :rows="3" placeholder="留空用默认提示词" />
      </a-form-item>
      <a-alert type="info" show-icon banner message="只报意图级硬问题（GPU/存储/平台是否满足需求意图），禁止逐行 diff——吸取 2026-08-04「案例库规格级对照全误报」教训。每次调用记 trace" style="margin-bottom: 12px" />
    </a-form>

    <!-- orchestrator：编排配置（不执行，只提供全局策略；后端 orchestrator._load_orch_cfg 读取） -->
    <a-form v-else-if="nodeType === 'orchestrator'" layout="vertical">
      <a-alert type="info" show-icon banner message="编排配置（不执行，只提供全局策略）：结构化记忆 + AI 增强预算 + 确定性能力并行。没画本节点时用默认值（均衡）。" style="margin-bottom: 12px" />
      <a-divider orientation="left" class="rf-sec">AI 增强预算（延迟 vs 质量）</a-divider>
      <a-form-item label="预算档位">
        <a-radio-group v-model:value="form.oc_ai_budget" button-style="solid">
          <a-radio-button value="fast">省时间（快）</a-radio-button>
          <a-radio-button value="balanced">均衡（默认）</a-radio-button>
          <a-radio-button value="quality">最优（慢）</a-radio-button>
        </a-radio-group>
        <p class="rf-hint">控制机型/配件推理的 ReAct 轮数 + 方案校对是否走 LLM：快=3 轮+校对纯规则；均衡=4 轮+LLM 校对；最优=6 轮+LLM 校对。预算优先于节点种子默认轮数。</p>
      </a-form-item>
      <a-divider orientation="left" class="rf-sec">结构化记忆</a-divider>
      <a-form-item label="记忆摘要">
        <a-switch v-model:checked="form.oc_memory_summary" />
        <p class="rf-hint">跨轮续接时把「已确认槽位/缺口/场景/已完成」摘要喂回编排 agent，避免多轮反问后忘记早期确认（对话文本只作补充）。</p>
      </a-form-item>
      <a-form-item label="摘要包含字段">
        <a-checkbox-group v-model:value="form.oc_memory_fields">
          <a-checkbox value="slots">已理解槽位</a-checkbox>
          <a-checkbox value="gap">缺口</a-checkbox>
          <a-checkbox value="scene">场景</a-checkbox>
          <a-checkbox value="cands">候选/配件/方案</a-checkbox>
          <a-checkbox value="done">已完成能力</a-checkbox>
        </a-checkbox-group>
      </a-form-item>
      <a-form-item label="对话保留轮数">
        <a-input-number v-model:value="form.oc_memory_turns" :min="4" :max="40" style="width:100%" />
        <p class="rf-hint">编排 agent 决策用的最近对话条数（默认 12）。</p>
      </a-form-item>
      <a-divider orientation="left" class="rf-sec">执行预算（超限自动收敛，防干等）</a-divider>
      <a-form-item label="墙钟时间上限（秒，0=不限制）">
        <a-input-number v-model:value="form.oc_wall_clock_s" :min="0" :max="3600" :step="10" style="width:100%" />
        <p class="rf-hint">整个需求分析最多跑多久。超时后停止反问与 LLM 决策，按确定性链跑完剩余节点出方案（默认 240s）。</p>
      </a-form-item>
      <a-form-item label="能力步数上限（0=不限制）">
        <a-input-number v-model:value="form.oc_max_steps" :min="0" :max="100" style="width:100%" />
        <p class="rf-hint">最多执行多少个能力节点（含重跑；默认 30）。</p>
      </a-form-item>
      <a-form-item label="工具调用上限（0=不限制）">
        <a-input-number v-model:value="form.oc_max_tool_calls" :min="0" :max="200" style="width:100%" />
        <p class="rf-hint">机型/配件推理的 ReAct 工具调用总次数（默认 40）。</p>
      </a-form-item>
      <a-form-item label="反问轮数上限（0=不限制）">
        <a-input-number v-model:value="form.oc_max_ask_rounds" :min="0" :max="20" style="width:100%" />
        <p class="rf-hint">最多反问客户几轮（默认 6，不高于「智能反问」节点的轮数上限）。</p>
      </a-form-item>
      <a-divider orientation="left" class="rf-sec">推进策略</a-divider>
      <a-form-item label="确定性能力并行">
        <a-switch v-model:checked="form.oc_parallel_enabled" />
        <p class="rf-hint">链式图一次只就绪一个能力，无收益；你画了分叉图时多个确定性能力可并行执行（默认关）。</p>
      </a-form-item>
      <a-form-item label="并行上限">
        <a-input-number v-model:value="form.oc_parallel_limit" :min="1" :max="4" style="width:100%" />
      </a-form-item>
    </a-form>

    <!-- result_check：方案自检（确定性，画布可见可配） -->
    <a-form v-else-if="nodeType === 'result_check'" layout="vertical">
      <a-alert type="info" show-icon banner message="方案自检（确定性）：结果完整性 + 必填核心件 + 数量合理性。与「规格合规校验」分工——前者查配置是否符合目录/兼容规则，本节点查方案有没有缺漏/自洽。" style="margin-bottom: 12px" />
      <a-form-item label="检查项">
        <div class="rc-check-list">
          <a-checkbox v-model:checked="form.rc_plan_not_empty">方案非空（有方案/机型/配件）</a-checkbox>
          <a-checkbox v-model:checked="form.rc_required_fields">核心件齐全（CPU/内存/盘）</a-checkbox>
          <a-checkbox v-model:checked="form.rc_qty_reasonable">数量合理性（配 GPU 有供电线、有内存条）</a-checkbox>
        </div>
      </a-form-item>
      <a-form-item label="失败处理">
        <a-radio-group v-model:value="form.rc_on_fail" button-style="solid">
          <a-radio-button value="mark">仅标记需修改</a-radio-button>
          <a-radio-button value="retry">自动触发重跑</a-radio-button>
        </a-radio-group>
        <p class="rf-hint">retry = 自检不过时确定性重跑 compose→预算校验→自检（重建脊梁强制保留，LLM 不可跳过）。</p>
      </a-form-item>
    </a-form>

    <a-empty v-else description="该节点无可配置参数" />
  </a-drawer>
</template>

<style scoped>
.rf-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 4px 0 0; }
.rc-check-list { display: flex; flex-direction: column; gap: 8px; padding-top: 2px; }
.rf-wl-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.rf-json { font-family: ui-monospace, monospace; font-size: 12px; }
.rf-sec { font-size: 13px; margin-top: 8px; }
.rf-checks { display: flex; flex-wrap: wrap; gap: 12px 16px; padding: 4px 0; }
.rf-rec-models { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.rf-rec-row { display: flex; align-items: center; gap: 10px; }
.rf-rec-label { min-width: 150px; font-size: 12px; color: var(--cpq-text-secondary); }
</style>
