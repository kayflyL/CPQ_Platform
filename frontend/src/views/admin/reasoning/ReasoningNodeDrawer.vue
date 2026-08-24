<script setup lang="ts">
/** 能力节点配置抽屉 —— 按通用节点类型渲染参数表单。
 *  通用类型：agent / ask / rule / branch / assemble / output / orchestrator。
 *  agent_fill 为需求分析能力的唯一能力级特例（对话+填表+数据来源可编辑）。
 *  runtime 仅用于兼容当前需求分析能力图，不再暴露业务专属硬编码表单。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningNodeKey } from '@/api/reasoningFlow'
import { assistantApi } from '@/api/assistant'
import { officeApi } from '@/api/office'
import type { RuleType } from '@/api/requirementRules'
import NodeResourceBindings from './NodeResourceBindings.vue'
import SlotListEditor from './SlotListEditor.vue'
import { REASONING_CFG_TYPES, NODE_DEFAULT_CONFIG, nodeArchetype, reasoningNodeMeta } from '@/utils/reasoningNodeMeta'

const MODEL_REASON_DEFAULTS = {
  selection_mode: 'recommend',
  grounding_tool: 'select_models',
  grounding_result_key: 'candidates',
  choice_id_pattern: 'id=(\\d+)',
  choice_fields: ['config_id', 'server_model_id', 'id'],
}
const KP_REASON_DEFAULTS = {
  proposal_enabled: true,
  temperature: 0.2,
  timeout: 60,
  max_attempts: 1,
  proposal_schema: {
    type: 'object',
    properties: {
      memory: { type: 'object', properties: {
        per_stick_gb: { type: 'integer' }, qty: { type: 'integer' },
        type: { type: 'string' }, speed_mt: { type: 'integer' },
        total_gb: { type: 'integer' }, reason: { type: 'string' },
      } },
      raid: { type: 'object', properties: {
        model: { type: 'string' }, qty: { type: 'integer' }, reason: { type: 'string' },
      } },
      nic: { type: 'array', items: { type: 'object', properties: {
        speed_g: { type: 'integer' }, ports: { type: 'integer' },
        qty: { type: 'integer' }, with_optical_module: { type: 'boolean' },
        reason: { type: 'string' },
      } } },
      psu: { type: 'object', properties: {
        wattage: { type: 'integer' }, qty: { type: 'integer' }, reason: { type: 'string' },
      } },
      notes: { type: 'array', items: { type: 'string' } },
    },
  },
  proposal_mapping: {
    memory: { fields: ['per_stick_gb', 'qty', 'type', 'speed_mt', 'comparison', 'total_gb'], required_any: ['per_stick_gb', 'total_gb'] },
    raid: { fields: ['model', 'qty'], required_any: ['model'] },
    nic: { fields: ['speed_g', 'ports', 'qty', 'with_optical_module'], required_any: ['speed_g', 'ports', 'qty'] },
  },
  reason_template: '配件规划：已确认 {{items}}',
}
const COMPOSE_DEFAULTS = {
  kp_source: 'per_baseline',
  psu_override_enabled: true,
  psu_wattage_source: 'ext.psu_signal.wattage',
  psu_qty_source: 'ext.psu_signal.qty',
}
const OUTPUT_KIND_OPTIONS = [
  { value: 'bom_scheme_draft', label: 'BOM 方案草稿' },
  { value: 'requirement_draft', label: '需求单草稿' },
  { value: 'plans', label: '方案 / BOM' },
  { value: 'data_answer', label: '数据结论' },
  { value: 'generic', label: '通用 JSON' },
]
function defaultOutputTarget(kind: string): string {
  if (kind === 'bom_scheme_draft') return 'bom_scheme'
  if (kind === 'requirement_draft') return 'requirement'
  if (kind === 'plans') return 'plan_draft'
  if (kind === 'data_answer') return 'conversation_reply'
  return 'artifact'
}

const CONFIGURABLE = REASONING_CFG_TYPES

const props = defineProps<{
  open: boolean
  nodeKey: string | null        // 节点 id（API 用）
  nodeType: string | null       // 节点 type（渲染表单用）
  nodeRuntime?: string | null   // 能力实例 handler（agent_fill/model_reason/…；通用节点可为空）
  nodeLabel?: string | null     // 画布节点实例名（可在抽屉内改名）
  initialConfig: Record<string, any> | null
  skillKey?: string | null      // 当前编辑的 Skill key（多技能共用一个画布时按技能写配置）
  skillOutputKind?: string | null // Skill 的输出类型，作为输出节点默认 output_kind
}>()
const emit = defineEmits<{ 'update:open': [boolean]; saved: []; remove: [string] }>()

const form = ref<any>({})

const scopeOptions = ref<{ data_sources: any[]; page_scopes: any[] }>({ data_sources: [], page_scopes: [] })

async function loadScopeOptions() {
  try {
    scopeOptions.value = await officeApi.scopeOptions()
  } catch {
    scopeOptions.value = { data_sources: [], page_scopes: [] }
  }
}
loadScopeOptions()

const saving = ref(false)

const title = computed(() => {
  const m = reasoningNodeMeta(props.nodeRuntime || props.nodeType || '')
  return m ? `配置节点 · ${m.name}` : (props.nodeType ? `配置节点 · ${props.nodeType}` : '配置')
})
const configurable = computed(() => Boolean(props.nodeType && CONFIGURABLE.includes(props.nodeType)) || Boolean(props.nodeRuntime && CONFIGURABLE.includes(props.nodeRuntime)))
const activeNodeType = computed(() => nodeArchetype(props.nodeType || props.nodeRuntime || ''))
const runtimeType = computed(() => props.nodeRuntime || props.nodeType || '')
const agentCapableRuntimes = new Set(['agent', 'model_reason', 'kp_reason', 'agent_fill'])
const ruleCatalogRuntimes = new Set(['rule', 'model_reason', 'kp_reason', 'agent_fill'])
const isAgentCapable = computed(() => activeNodeType.value === 'agent' && agentCapableRuntimes.has(runtimeType.value || 'agent'))
const fillRuleTypes = computed<RuleType[] | undefined>(() => {
  if (runtimeType.value !== 'agent_fill') return undefined
  return ['platform_series_map', 'category_alias']
})
const showRuleCatalog = computed(() => ruleCatalogRuntimes.has(runtimeType.value))
const dataSourcesEnabled = computed(() => ['agent_fill', 'model_reason', 'kp_reason', 'agent'].includes(runtimeType.value))
const toolsEnabled = computed(() => isAgentCapable.value)
const systemPromptValue = computed({
  get: () => runtimeType.value === 'agent_fill'
    ? (form.value?.prompt?.system_prompt ?? '')
    : (form.value?.system_prompt ?? ''),
  set: (v: string) => {
    if (runtimeType.value === 'agent_fill') {
      if (form.value?.prompt) form.value.prompt.system_prompt = v
    } else if (form.value) {
      form.value.system_prompt = v
    }
  },
})
const dataSourceOptions = computed(() => scopeOptions.value.data_sources.map((item: any) => ({
  key: item.key,
  description: item.description || item.key,
})))
function defaultDataSources(rt: string): string[] {
  const map: Record<string, string[]> = {
    agent_fill: ['server_catalog', 'demand_analysis_docs'],
    model_reason: ['candidate_search', 'server_catalog'],
    kp_reason: ['kp_price'],
    agent: ['server_catalog'],
  }
  return map[rt] || [...(NODE_DEFAULT_CONFIG[nodeArchetype(rt)]?.data_sources || [])]
}
const toolCatalog = ref<any[]>([])
const agentToolOptions = computed(() => toolCatalog.value.map((tool: any) => ({
  value: tool.name,
  label: `${tool.name} · ${tool.description || ''}`,
})))
async function loadToolCatalog() {
  try {
    toolCatalog.value = await assistantApi.tools.catalog()
  } catch {
    toolCatalog.value = []
  }
}

function safeJsonString(value: any): string {
  if (value === undefined || value === null) return ''
  try { return JSON.stringify(value, null, 2) } catch { return '' }
}

function parseJsonObject(text: string): Record<string, any> | null {
  if (!String(text || '').trim()) return {}
  try {
    const value = JSON.parse(String(text || ''))
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null
  } catch {
    return null
  }
}

function parseJsonArray(text: string): any[] | null {
  if (!String(text || '').trim()) return []
  try {
    const value = JSON.parse(String(text || ''))
    return Array.isArray(value) ? value : null
  } catch {
    return null
  }
}
watch(() => props.open, async (v) => {
  if (!v) return
  if (!props.nodeType && !props.nodeRuntime) return
  loadToolCatalog()
  const c = props.initialConfig || {}
  const outputKind = c.output_kind || props.skillOutputKind || (props.skillKey === 'requirement_analysis' ? 'bom_scheme_draft' : props.skillKey === 'trend_analysis' ? 'data_answer' : 'generic')
  form.value = {
    label: props.nodeLabel ?? '',
    enabled_tools: Array.isArray(c.enabled_tools)
      ? [...c.enabled_tools]
      : [...(runtimeType.value === 'model_reason'
            ? ['select_models']
            : runtimeType.value === 'kp_reason'
              ? ['select_parts', 'pick_kp_parts']
              : (NODE_DEFAULT_CONFIG[activeNodeType.value]?.enabled_tools || []))],
    max_iterations: c.max_iterations ?? (NODE_DEFAULT_CONFIG[activeNodeType.value]?.max_iterations ?? 6),
    mr_selection_mode: c.selection_mode ?? MODEL_REASON_DEFAULTS.selection_mode,
    mr_grounding_tool: c.grounding_tool ?? MODEL_REASON_DEFAULTS.grounding_tool,
    mr_grounding_result_key: c.grounding_result_key ?? MODEL_REASON_DEFAULTS.grounding_result_key,
    mr_choice_id_pattern: c.choice_id_pattern ?? MODEL_REASON_DEFAULTS.choice_id_pattern,
    mr_choice_fields: Array.isArray(c.choice_fields)
      ? [...c.choice_fields]
      : [...MODEL_REASON_DEFAULTS.choice_fields],
    kr_proposal_enabled: c.proposal_enabled ?? KP_REASON_DEFAULTS.proposal_enabled,
    kr_temperature: c.temperature ?? KP_REASON_DEFAULTS.temperature,
    kr_timeout: c.timeout ?? KP_REASON_DEFAULTS.timeout,
    kr_max_attempts: c.max_attempts ?? KP_REASON_DEFAULTS.max_attempts,
    kr_proposal_schema_text: safeJsonString(c.proposal_schema ?? KP_REASON_DEFAULTS.proposal_schema),
    kr_user_prompt_template: c.user_prompt_template ?? '',
    kr_proposal_mapping_text: safeJsonString(c.proposal_mapping ?? KP_REASON_DEFAULTS.proposal_mapping),
    kr_reason_template: c.reason_template ?? KP_REASON_DEFAULTS.reason_template,
    cp_kp_source: c.kp_source ?? COMPOSE_DEFAULTS.kp_source,
    cp_psu_override_enabled: c.psu_override_enabled ?? COMPOSE_DEFAULTS.psu_override_enabled,
    cp_psu_wattage_source: c.psu_wattage_source ?? COMPOSE_DEFAULTS.psu_wattage_source,
    cp_psu_qty_source: c.psu_qty_source ?? COMPOSE_DEFAULTS.psu_qty_source,
    system_prompt: c.system_prompt ?? '',
    data_sources: Array.isArray(c.data_sources)
      ? [...c.data_sources]
      : defaultDataSources(runtimeType.value),
    conflict_strategy: c.conflict_strategy || 'auto_resolve',
    rule_types: Array.isArray(c.rule_types)
      ? [...c.rule_types]
      : [...(NODE_DEFAULT_CONFIG[activeNodeType.value]?.rule_types || [])],
    rule_on_fail: c.on_fail || c.rule_on_fail || 'mark',
    expr: c.expr || '',
    template: c.template || '',
    output_kind: outputKind,
    output_target: c.target || defaultOutputTarget(outputKind),
    output_payload_map_text: safeJsonString(c.payload_map),
    output_actions_text: safeJsonString(c.actions),
    output_schema_text: safeJsonString(c.output_schema),
    oc_ai_budget: c.ai_budget || 'balanced',
    oc_memory_summary: c.memory?.summary_enabled ?? true,
    oc_memory_turns: c.memory?.turns ?? 12,
    oc_memory_fields: Array.isArray(c.memory?.fields) ? [...c.memory.fields] : ['slots', 'gap', 'scene', 'cands', 'done'],
    oc_parallel_enabled: c.parallel_enabled ?? false,
    oc_parallel_limit: c.parallel_limit ?? 2,
    oc_wall_clock_s: c.budgets?.wall_clock_s ?? 240,
    oc_max_steps: c.budgets?.max_steps ?? 30,
    oc_max_tool_calls: c.budgets?.max_tool_calls ?? 40,
    oc_max_ask_rounds: c.budgets?.max_ask_rounds ?? 6,
    prompt: (c.prompt && typeof c.prompt === 'object') ? {
      system_prompt: c.prompt.system_prompt || '',
    } : { system_prompt: '' },
  }
})


/** 组装当前表单 → 节点 config。JSON 解析失败已在此 toast 并返回 null。 */
function buildConfig(): Record<string, any> | null {
  if (!props.nodeKey || !configurable.value) return null
  const t = activeNodeType.value
  const rt = runtimeType.value
  const config: Record<string, any> = {}

  if (isAgentCapable.value) {
    config.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
    config.max_iterations = +form.value.max_iterations || 6
    config.system_prompt = form.value.system_prompt || ''
  }
  if (runtimeType.value === 'model_reason') {
    config.selection_mode = form.value.mr_selection_mode || MODEL_REASON_DEFAULTS.selection_mode
    config.grounding_tool = form.value.mr_grounding_tool || MODEL_REASON_DEFAULTS.grounding_tool
    config.grounding_result_key = form.value.mr_grounding_result_key || MODEL_REASON_DEFAULTS.grounding_result_key
    config.choice_id_pattern = form.value.mr_choice_id_pattern || MODEL_REASON_DEFAULTS.choice_id_pattern
    config.choice_fields = Array.isArray(form.value.mr_choice_fields) ? [...form.value.mr_choice_fields] : []
  }
  if (runtimeType.value === 'kp_reason') {
    const proposalSchema = parseJsonObject(form.value.kr_proposal_schema_text)
    if (proposalSchema === null) {
      message.error('配件提议输出 schema 不是合法 JSON 对象')
      return null
    }
    const proposalMapping = parseJsonObject(form.value.kr_proposal_mapping_text)
    if (proposalMapping === null) {
      message.error('配件提议合并映射不是合法 JSON 对象')
      return null
    }
    config.proposal_enabled = form.value.kr_proposal_enabled !== false
    config.temperature = +form.value.kr_temperature || KP_REASON_DEFAULTS.temperature
    config.timeout = +form.value.kr_timeout || KP_REASON_DEFAULTS.timeout
    config.max_attempts = +form.value.kr_max_attempts || KP_REASON_DEFAULTS.max_attempts
    config.proposal_schema = proposalSchema
    config.user_prompt_template = form.value.kr_user_prompt_template || ''
    config.proposal_mapping = proposalMapping
    config.reason_template = form.value.kr_reason_template || KP_REASON_DEFAULTS.reason_template
  }
  if (runtimeType.value === 'compose') {
    config.kp_source = form.value.cp_kp_source || COMPOSE_DEFAULTS.kp_source
    config.psu_override_enabled = form.value.cp_psu_override_enabled !== false
    config.psu_wattage_source = form.value.cp_psu_wattage_source || COMPOSE_DEFAULTS.psu_wattage_source
    config.psu_qty_source = form.value.cp_psu_qty_source || COMPOSE_DEFAULTS.psu_qty_source
  }
  if (showRuleCatalog.value) {
    config.rule_types = Array.isArray(form.value.rule_types) ? [...form.value.rule_types] : []
  }
  if (t === 'rule') config.on_fail = form.value.rule_on_fail || 'mark'
  if (t === 'branch') config.expr = form.value.expr || ''
  if (t === 'assemble') {
    config.template = form.value.template || ''
    const outputSchema = parseJsonObject(form.value.output_schema_text)
    if (outputSchema === null) {
      message.error('输出 schema 不是合法 JSON 对象')
      return null
    }
    config.output_schema = outputSchema
  }
  if (t === 'output') {
    config.template = form.value.template || ''
    const outputSchema = parseJsonObject(form.value.output_schema_text)
    if (outputSchema === null) {
      message.error('输出 schema 不是合法 JSON 对象')
      return null
    }
    config.output_schema = outputSchema
    const payloadMap = parseJsonObject(form.value.output_payload_map_text)
    if (payloadMap === null) {
      message.error('交接映射不是合法 JSON 对象')
      return null
    }
    const actions = parseJsonArray(form.value.output_actions_text)
    if (actions === null) {
      message.error('交接动作不是合法 JSON 数组')
      return null
    }
    config.output_kind = form.value.output_kind || 'generic'
    config.target = form.value.output_target || defaultOutputTarget(config.output_kind)
    config.payload_map = payloadMap
    config.actions = actions
  }
  if (t === 'orchestrator') {
    config.ai_budget = form.value.oc_ai_budget || 'balanced'
    config.system_prompt = form.value.system_prompt || ''
    config.memory = {
      summary_enabled: form.value.oc_memory_summary !== false,
      turns: +form.value.oc_memory_turns || 12,
      fields: Array.isArray(form.value.oc_memory_fields) && form.value.oc_memory_fields.length
        ? form.value.oc_memory_fields : ['slots', 'gap', 'scene', 'cands', 'done'],
    }
    config.parallel_enabled = !!form.value.oc_parallel_enabled
    config.parallel_limit = +form.value.oc_parallel_limit || 2
    config.budgets = {
      wall_clock_s: +form.value.oc_wall_clock_s || 0,
      max_steps: +form.value.oc_max_steps || 0,
      max_tool_calls: +form.value.oc_max_tool_calls || 0,
      max_ask_rounds: +form.value.oc_max_ask_rounds || 0,
    }
  }
  if (rt === 'agent_fill') {
    config.system_prompt = form.value.system_prompt || ''
    config.prompt = {
      system_prompt: (form.value.prompt?.system_prompt ?? '') || '',
    }
    config.data_sources = Array.isArray(form.value.data_sources) ? [...form.value.data_sources] : []
    config.rule_types = Array.isArray(form.value.rule_types) ? [...form.value.rule_types] : []
    config.conflict_strategy = form.value.conflict_strategy || 'auto_resolve'
  }
  return config
}

async function persist(config: Record<string, any>): Promise<boolean> {
  saving.value = true
  try {
    const isLegacyRuntime = Boolean(props.nodeRuntime && props.nodeRuntime !== props.nodeType)
    const base = isLegacyRuntime ? { ...(props.initialConfig || {}) } : {}
    const merged = { ...base, ...config }
    if (showRuleCatalog.value) {
      merged.rule_types = Array.isArray(form.value.rule_types) ? [...form.value.rule_types] : []
    } else {
      delete merged.rule_types
    }
    if (isAgentCapable.value) {
      merged.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
      merged.max_iterations = +form.value.max_iterations || (NODE_DEFAULT_CONFIG[activeNodeType.value]?.max_iterations ?? 5)
      merged.system_prompt = form.value.system_prompt || ''
    } else {
      delete merged.enabled_tools
      delete merged.max_iterations
      delete merged.system_prompt
      delete merged.max_rounds
    }
    if (runtimeType.value === 'kp_reason') {
      delete merged.enabled_tools
      delete merged.max_iterations
    }
    if (runtimeType.value === 'compose') {
      delete merged.template
      delete merged.output_schema
    }
    if (activeNodeType.value === 'output') {
      delete merged.bom_output
      delete merged.recommendation
    }
    if (!isAgentCapable.value) {
      delete merged.max_rounds
    }
    const label = (form.value.label ?? '').trim() || props.nodeLabel || ''
    await reasoningFlowApi.updateNode(props.nodeKey as ReasoningNodeKey, merged, label, props.skillKey || undefined)
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


        <template v-if="configurable">
            

      <div class="node-zone">
        <div class="node-zone-head">
          <span class="node-zone-index">1</span>
          <span class="node-zone-title">AI 层</span>
          <span class="node-zone-note">Agent 怎么思考与回答</span>
        </div>
        <div class="node-zone-body">
          <a-form layout="vertical" class="node-config-form node-common-form">
            <div class="rf-inline-fields">
              <a-form-item label="节点名称">
                <a-input v-model:value="form.label" placeholder="填写该节点在当前能力中的名称" maxlength="40" />
                <p class="rf-hint">节点名称属于实例属性，可随能力复用而改名；不影响节点类型与执行逻辑。</p>
              </a-form-item>
              <a-form-item v-if="isAgentCapable" label="System Prompt">
                <a-textarea v-model:value="systemPromptValue" :rows="4" placeholder="留空使用该节点类型默认提示词" />
              </a-form-item>
            </div>
          </a-form>




        </div>
      </div>

      <div class="node-zone">
        <div class="node-zone-head">
          <span class="node-zone-index">2</span>
          <span class="node-zone-title">目标层</span>
          <span class="node-zone-note">要输出的目标（字段表 / 输出物）</span>
        </div>
        <div class="node-zone-body">
          <template v-if="runtimeType === 'agent_fill'">
            <div class="node-section-title">字段配置 <span class="node-behavior-chip">对齐线索登记表 schema</span></div>
            <SlotListEditor embedded />
            <p class="rf-hint">线索登记字段和部件映射在此维护；部件字段由 AI 填写，这里只保留映射关系。Agent 一边对话一边据此填表；机型与配件的最终选型交给下游「机型选型」「配件选型」节点。</p>
          </template>
          <!-- 组装节点：模板 + 输出 schema -->
          <a-form v-else-if="activeNodeType === 'assemble' && runtimeType !== 'compose'" layout="vertical">
            <p class="rf-hint">模板与 schema 为通用配置；当前能力若由后端确定性规则生成，可留空。</p>
            <a-form-item label="输出模板">
              <a-textarea v-model:value="form.template" :rows="6" placeholder="可留空；例如 Markdown/文本模板" />
            </a-form-item>
            <a-form-item label="输出 schema（JSON 对象）">
              <a-textarea v-model:value="form.output_schema_text" :rows="10" placeholder="{}" style="font-family: ui-monospace, monospace;" />
              <p class="rf-hint">定义该节点产出结构；留空 = {}。执行器只透传 schema，不内嵌业务字段。</p>
            </a-form-item>
          </a-form>

          <!-- 输出节点：交接契约 -->
          <a-form v-else-if="activeNodeType === 'output'" layout="vertical">
            <p class="rf-hint">输出节点只负责把上游结果交给下游业务实体或对话文本；不负责 BOM 展示样式和推荐语。</p>
            <a-form-item label="输出类型">
              <a-select v-model:value="form.output_kind" :options="OUTPUT_KIND_OPTIONS" style="width:100%" />
            </a-form-item>
            <a-form-item label="交接目标">
              <a-input v-model:value="form.output_target" placeholder="plan_draft / conversation_reply / artifact" />
              <p class="rf-hint">目标为业务实体键或对话回执键，由后端据此落草稿/转审批/回显。</p>
            </a-form-item>
            <a-form-item label="交接映射（JSON 对象）">
              <a-textarea v-model:value="form.output_payload_map_text" :rows="8" placeholder='{"plans":"ctx.plans","keywords":"ctx.ext.keywords"}' style="font-family: ui-monospace, monospace;" />
              <p class="rf-hint">把 ctx 点分路径映射到交接 payload；未配置时使用 output_kind 的默认字段。</p>
            </a-form-item>
            <a-form-item label="交接动作（JSON 数组）">
              <a-textarea v-model:value="form.output_actions_text" :rows="8" placeholder='[{"action":"submit_approval","target":"cost_bom"}]' style="font-family: ui-monospace, monospace;" />
              <p class="rf-hint">产出后的下游动作，例如转审批；留空表示交回当前对话。</p>
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">通用格式</a-divider>
            <a-form-item label="输出模板">
              <a-textarea v-model:value="form.template" :rows="6" placeholder="可留空；例如 Markdown/文本模板" />
            </a-form-item>
            <a-form-item label="输出 schema（JSON 对象）">
              <a-textarea v-model:value="form.output_schema_text" :rows="10" placeholder="{}" style="font-family: ui-monospace, monospace;" />
              <p class="rf-hint">定义该节点产出结构；留空 = {}。执行器只透传 schema，不内嵌业务字段。</p>
            </a-form-item>
          </a-form>


<!-- 条件分支 -->
          <a-form v-if="activeNodeType === 'branch'" layout="vertical">
            <a-form-item label="条件表达式（simpleeval 安全求值）">
              <a-input v-model:value="form.expr" placeholder="如：series == 'Polaris'" />
              <p class="rf-hint">真分支走 sourceHandle='true'，假分支走 sourceHandle='false'；空表达式不参与分支。</p>
            </a-form-item>
          </a-form>

          <!-- 机型决策节点：把 grounding 工具、结果字段、选择正则和库外机型短路全部暴露为配置 -->
          <a-form v-else-if="runtimeType === 'model_reason'" layout="vertical">
            <a-form-item label="选型模式">
              <a-radio-group v-model:value="form.mr_selection_mode" button-style="solid">
                <a-radio-button value="recommend">目录推荐</a-radio-button>
                <a-radio-button value="ai_config">AI 智能选配</a-radio-button>
                <a-radio-button value="self_config">用户自己配置</a-radio-button>
              </a-radio-group>
              <p class="rf-hint">这里是「默认偏好」：AI 会先按用户意图判断该推荐/智能选配/自配，只有 AI 拿不准时才回退到这里的默认值。</p>
            </a-form-item>
          </a-form>

          <!-- 配件决策节点：LLM 结构化提议的 schema、提示词模板、合并映射全部可配 -->
          <a-form v-else-if="runtimeType === 'kp_reason'" layout="vertical">
            <a-form-item label="启用 LLM 配件提议">
              <a-switch v-model:checked="form.kr_proposal_enabled" />
              <p class="rf-hint">关闭后跳过 LLM 结构化提议，只走规则库校验；提议失败时也会自动降级到规则。</p>
            </a-form-item>
            <a-form-item label="提议提示词模板">
              <a-textarea v-model:value="form.kr_user_prompt_template" :rows="10" placeholder="留空使用后端默认模板" style="font-family: ui-monospace, monospace;" />
              <p class="rf-hint">可用占位符：<code v-pre>{{requirement_text}}</code>、<code v-pre>{{understood}}</code>、<code v-pre>{{baseline_capability}}</code>。</p>
            </a-form-item>
            <a-form-item label="提议输出 schema（JSON 对象）">
              <a-textarea v-model:value="form.kr_proposal_schema_text" :rows="12" placeholder="{}" style="font-family: ui-monospace, monospace;" />
            </a-form-item>
            <a-form-item label="提议合并映射（JSON 对象）">
              <a-textarea v-model:value="form.kr_proposal_mapping_text" :rows="12" placeholder="{}" style="font-family: ui-monospace, monospace;" />
              <p class="rf-hint">描述 LLM 输出字段如何确定性合入需求理解槽位；规则已有内容不覆盖。</p>
            </a-form-item>
            <div class="rf-inline-fields">
              <a-form-item label="温度"><a-input-number v-model:value="form.kr_temperature" :min="0" :max="1" :step="0.1" style="width:100%" /></a-form-item>
              <a-form-item label="超时（秒）"><a-input-number v-model:value="form.kr_timeout" :min="5" :max="180" style="width:100%" /></a-form-item>
              <a-form-item label="最大尝试"><a-input-number v-model:value="form.kr_max_attempts" :min="1" :max="3" style="width:100%" /></a-form-item>
            </div>
            <a-form-item label="白盒说明模板">
              <a-input v-model:value="form.kr_reason_template" placeholder="配件规划：已确认 {{items}}" />
            </a-form-item>
          </a-form>

          <!-- 方案组装节点：配件来源与电源信号覆盖策略可配 -->
          <a-form v-else-if="runtimeType === 'compose'" layout="vertical">
            <a-form-item label="配件来源">
              <a-radio-group v-model:value="form.cp_kp_source" button-style="solid">
                <a-radio-button value="per_baseline">按机型取配件（无则用全局）</a-radio-button>
                <a-radio-button value="global">统一使用全局配件</a-radio-button>
              </a-radio-group>
            </a-form-item>
            <a-form-item label="需求电源信号覆盖">
              <a-switch v-model:checked="form.cp_psu_override_enabled" />
              <p class="rf-hint">开启时，需求中明确给出的电源瓦数/数量会覆盖 build_plan 的负载推断结果。</p>
            </a-form-item>
            <a-form-item label="电源瓦数读取路径">
              <a-input v-model:value="form.cp_psu_wattage_source" placeholder="ext.psu_signal.wattage" />
            </a-form-item>
            <a-form-item label="电源数量读取路径">
              <a-input v-model:value="form.cp_psu_qty_source" placeholder="ext.psu_signal.qty" />
            </a-form-item>
          </a-form>

          <!-- 规则节点：只引用规则目录，失败策略可配 -->
          <a-form v-else-if="activeNodeType === 'rule'" layout="vertical">
            <a-form-item label="规则失败处理">
              <a-radio-group v-model:value="form.rule_on_fail" button-style="solid">
                <a-radio-button value="mark">标记后继续</a-radio-button>
                <a-radio-button value="block">阻断</a-radio-button>
                <a-radio-button value="retry">重跑相关节点</a-radio-button>
              </a-radio-group>
              <p class="rf-hint">规则内容统一在选型配置维护，节点只保存上方勾选的规则类型引用。</p>
            </a-form-item>
          </a-form>

          <!-- 编排节点：预算/记忆/并行 -->
          <a-form v-else-if="activeNodeType === 'orchestrator'" layout="vertical">
            <a-form-item label="编排 System Prompt 模板">
              <a-textarea v-model:value="form.system_prompt" :rows="4" placeholder="留空使用默认编排提示词；控制编排决策语气与规则" />
              <p class="rf-hint">编排器决定下一步动作（call/ask/final）的提示词，可按需改写。</p>
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">AI 增强预算（延迟 vs 质量）</a-divider>
            <a-form-item label="预算档位">
              <a-radio-group v-model:value="form.oc_ai_budget" button-style="solid">
                <a-radio-button value="fast">省时间（快）</a-radio-button>
                <a-radio-button value="balanced">均衡（默认）</a-radio-button>
                <a-radio-button value="quality">最优（慢）</a-radio-button>
              </a-radio-group>
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">结构化记忆</a-divider>
            <a-form-item label="记忆摘要">
              <a-switch v-model:checked="form.oc_memory_summary" />
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
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">执行预算（超限自动收敛）</a-divider>
            <a-form-item label="墙钟时间上限（秒，0=不限制）">
              <a-input-number v-model:value="form.oc_wall_clock_s" :min="0" :max="3600" :step="10" style="width:100%" />
            </a-form-item>
            <a-form-item label="能力步数上限（0=不限制）">
              <a-input-number v-model:value="form.oc_max_steps" :min="0" :max="100" style="width:100%" />
            </a-form-item>
            <a-form-item label="工具调用上限（0=不限制）">
              <a-input-number v-model:value="form.oc_max_tool_calls" :min="0" :max="200" style="width:100%" />
            </a-form-item>
            <a-form-item label="反问轮数上限（0=不限制）">
              <a-input-number v-model:value="form.oc_max_ask_rounds" :min="0" :max="20" style="width:100%" />
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">推进策略</a-divider>
            <a-form-item label="确定性能力并行">
              <a-switch v-model:checked="form.oc_parallel_enabled" />
            </a-form-item>
            <a-form-item label="并行上限">
              <a-input-number v-model:value="form.oc_parallel_limit" :min="1" :max="4" style="width:100%" />
            </a-form-item>
          </a-form>

          <a-form v-else layout="vertical">
            <p class="rf-hint">该节点暂无额外节点专属设置；其执行行为由节点元数据与后端默认配置决定。</p>
          </a-form>
        </div>
      </div>

      <div class="node-zone">
        <div class="node-zone-head">
          <span class="node-zone-index">3</span>
          <span class="node-zone-title">资源与权限</span>
          <span class="node-zone-note">能读什么、能调什么</span>
        </div>
        <div class="node-zone-body">
          <NodeResourceBindings
            v-model:data-sources="form.data_sources"
            v-model:rule-types="form.rule_types"
            v-model:tools="form.enabled_tools"
            v-model:max-iterations="form.max_iterations"
            :data-source-options="dataSourceOptions"
            :tool-options="agentToolOptions"
            :data-sources-enabled="dataSourcesEnabled"
            :rules-enabled="showRuleCatalog"
            :tools-enabled="toolsEnabled"
            :show-max-iterations="toolsEnabled"
            :rule-available="fillRuleTypes"
            :rule-defaults="fillRuleTypes"
          />
          <a-form v-if="runtimeType === 'model_reason'" layout="vertical" class="node-section nrb-card">
            <div class="node-section-title">机型候选来源（AI 选型读取候选清单）</div>
            <a-form-item label="候选来源工具">
              <a-select v-model:value="form.mr_grounding_tool" :options="agentToolOptions" placeholder="选择提供候选清单的工具" style="width:100%" />
              <p class="rf-hint">节点会从该工具的调用结果中读取候选清单，再由 LLM 选择。</p>
            </a-form-item>
            <a-form-item label="候选结果字段">
              <a-input v-model:value="form.mr_grounding_result_key" placeholder="candidates" />
            </a-form-item>
            <a-form-item label="选择 ID 正则">
              <a-input v-model:value="form.mr_choice_id_pattern" placeholder="id=(\d+)" />
              <p class="rf-hint">从 final.answer 中提取候选 id；第一捕获组用于匹配候选字段。</p>
            </a-form-item>
            <a-form-item label="候选匹配字段">
              <a-select v-model:value="form.mr_choice_fields" mode="tags" :options="[
                { value: 'config_id', label: 'config_id' },
                { value: 'server_model_id', label: 'server_model_id' },
                { value: 'id', label: 'id' },
              ]" placeholder="config_id, server_model_id, id" style="width:100%" />
            </a-form-item>
          </a-form>


        </div>
      </div>




        </template>
    <a-empty v-else description="该节点无可配置参数" />
  </a-drawer>
</template>

<style scoped>
.node-config-form { padding: 2px 0; }
.node-common-form { margin-bottom: 12px; }
.node-advanced-fields { margin-top: 12px; }
.node-section {
  margin: 14px 0;
  padding: 12px 14px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-glass-2-bg);
  box-shadow: var(--cpq-shadow-sm);
}
.node-section-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.node-behavior-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 11px 12px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 10px;
  background: var(--cpq-glass-1-bg);
}
.node-behavior-row { display: flex; align-items: baseline; gap: 8px; font-size: 12.5px; line-height: 1.6; }
.node-behavior-k { width: 70px; flex-shrink: 0; color: var(--cpq-text-secondary); }
.node-behavior-v { color: var(--cpq-text-primary); }
.node-behavior-chip,
.node-behavior-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  vertical-align: middle;
}
.node-behavior-chip { background: rgba(22, 119, 255, 0.14); color: #6ea8ff; }
.node-behavior-badge { background: rgba(250, 173, 20, 0.14); color: #ffc53d; }
.node-behavior-config { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
.node-behavior-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.node-io-contract { display: flex; flex-direction: column; gap: 8px; }
.node-io-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.node-io-tag {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  margin-right: 2px;
}
.node-io-var {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--cpq-glass-1-bg);
  color: var(--cpq-text-primary);
}
.node-io-var small { font-size: 10px; color: var(--cpq-text-muted); }
.node-io-var.in { border: 1px solid #d6e4ff; }
.node-io-var.out { border: 1px solid #d9f0e4; }
.node-io-empty { font-size: 12px; color: var(--cpq-text-muted); }
.rf-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 4px 0 0; }
.rf-inline-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; }
.rc-check-list { display: flex; flex-direction: column; gap: 8px; padding-top: 2px; }
.rf-wl-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.rf-json { font-family: ui-monospace, monospace; font-size: 12px; }
.rf-sec { font-size: 13px; margin-top: 8px; }
.rf-checks { display: flex; flex-wrap: wrap; gap: 12px 16px; padding: 4px 0; }
.rf-rec-models { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.rf-rec-row { display: flex; align-items: center; gap: 10px; }
.rf-rec-label { min-width: 150px; font-size: 12px; color: var(--cpq-text-secondary); }

.node-zone {
  margin-bottom: 14px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-glass-1-bg);
  overflow: hidden;
}
.node-zone-head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 14px;
  border-bottom: 1px solid var(--cpq-border-primary);
  background: var(--cpq-glass-2-bg);
}
.node-zone-index {
  width: 22px;
  height: 22px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: rgba(22, 119, 255, 0.14);
  color: #6ea8ff;
  border: 1px solid rgba(22, 119, 255, 0.35);
  font-size: 12px;
  font-weight: 700;
}
.node-zone-title { font-size: 13px; font-weight: 700; color: var(--cpq-text-primary); }
.node-zone-note { margin-left: auto; font-size: 11px; color: var(--cpq-text-muted); }
.node-zone-body { padding: 13px 14px; }
</style>
