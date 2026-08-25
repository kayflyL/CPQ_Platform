<script setup lang="ts">
/** 能力节点配置抽屉 —— 按通用节点类型渲染参数表单。
 *  通用类型：agent / output；需求分析能力节点（agent_fill/model_reason/kp_reason/compose）按类型白盒展示可编辑参数。
 *  runtime 仅用于兼容当前需求分析能力图，不再暴露业务专属硬编码表单。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningNodeKey } from '@/api/reasoningFlow'
import { assistantApi } from '@/api/assistant'
import type { RuleType } from '@/api/requirementRules'
import NodeResourceBindings from './NodeResourceBindings.vue'
import SlotListEditor from './SlotListEditor.vue'
import { REASONING_CFG_TYPES, NODE_DEFAULT_CONFIG, nodeArchetype, reasoningNodeMeta } from '@/utils/reasoningNodeMeta'

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

const saving = ref(false)

const title = computed(() => {
  const m = reasoningNodeMeta(props.nodeRuntime || props.nodeType || '')
  return m ? `配置节点 · ${m.name}` : (props.nodeType ? `配置节点 · ${props.nodeType}` : '配置')
})
const configurable = computed(() => Boolean(props.nodeType && CONFIGURABLE.includes(props.nodeType)) || Boolean(props.nodeRuntime && CONFIGURABLE.includes(props.nodeRuntime)))
const activeNodeType = computed(() => nodeArchetype(props.nodeType || props.nodeRuntime || ''))
const runtimeType = computed(() => props.nodeRuntime || props.nodeType || '')
const showSystemPrompt = computed(() => ['agent', 'agent_fill', 'kp_reason'].includes(runtimeType.value))
const ruleCatalogRuntimes = new Set(['model_reason', 'kp_reason', 'agent_fill'])
const fillRuleTypes = computed<RuleType[] | undefined>(() => {
  if (runtimeType.value !== 'agent_fill') return undefined
  return ['platform_series_map', 'category_alias']
})
const showRuleCatalog = computed(() => ruleCatalogRuntimes.has(runtimeType.value))
const toolsEnabled = computed(() => runtimeType.value === 'agent')
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
      : [...(NODE_DEFAULT_CONFIG[activeNodeType.value]?.enabled_tools || [])],
    max_iterations: c.max_iterations ?? (NODE_DEFAULT_CONFIG[activeNodeType.value]?.max_iterations ?? 6),
    mr_group_by_series: c.group_by_series ?? true,
    mr_per_series_limit: c.per_series_limit ?? 2,
    mr_max_plans: c.max_plans ?? null,
    mr_recommend_strategy_id: c.recommend_strategy_id ?? '',
    mr_candidate_lede: c.candidate_lede ?? '',
    mr_choice_lede: c.choice_lede ?? '',
    mr_no_exact_lede: c.no_exact_lede ?? '',
    mr_no_match_question: c.no_match_question ?? '',
    kr_proposal_enabled: c.proposal_enabled ?? true,
    kr_proposal_schema_text: safeJsonString(c.proposal_schema ?? {}),
    kr_user_prompt_template: c.user_prompt_template ?? '',
    kr_proposal_mapping_text: safeJsonString(c.proposal_mapping ?? {}),
    kr_reason_template: c.reason_template ?? '',
    kr_representative_pick: c.representative_pick ?? 'auto',
    kr_fallback_strategy: c.fallback_strategy ?? 'fallback_representative',
    kr_drive_spec_substitute: c.drive_spec_substitute ?? true,
    cp_kp_source: c.kp_source ?? 'per_baseline',
    cp_psu_override_enabled: c.psu_override_enabled ?? true,
    cp_psu_wattage_source: c.psu_wattage_source ?? 'ext.psu_signal.wattage',
    cp_psu_qty_source: c.psu_qty_source ?? 'ext.psu_signal.qty',
    system_prompt: c.system_prompt ?? '',
    rule_types: Array.isArray(c.rule_types)
      ? [...c.rule_types]
      : [...(NODE_DEFAULT_CONFIG[activeNodeType.value]?.rule_types || [])],
    output_name: c.name ?? '',
    output_kind: outputKind,
    output_target: c.target || defaultOutputTarget(outputKind),
    output_payload_map_text: safeJsonString(c.payload_map),
    output_actions_text: safeJsonString(c.actions),
    output_template: c.template || '',
    output_schema_text: safeJsonString(c.output_schema),
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

  if (runtimeType.value === 'agent') {
    config.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
    config.max_iterations = +form.value.max_iterations || 6
    config.system_prompt = form.value.system_prompt || ''
  }
  if (runtimeType.value === 'model_reason') {
    config.group_by_series = form.value.mr_group_by_series ?? true
    config.per_series_limit = +form.value.mr_per_series_limit || 2
    config.max_plans = form.value.mr_max_plans ? +form.value.mr_max_plans : null
    config.recommend_strategy_id = form.value.mr_recommend_strategy_id || ''
    config.candidate_lede = form.value.mr_candidate_lede || ''
    config.choice_lede = form.value.mr_choice_lede || ''
    config.no_exact_lede = form.value.mr_no_exact_lede || ''
    config.no_match_question = form.value.mr_no_match_question || ''
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
    config.proposal_schema = proposalSchema
    config.user_prompt_template = form.value.kr_user_prompt_template || ''
    config.proposal_mapping = proposalMapping
    config.system_prompt = form.value.system_prompt || ''
    config.reason_template = form.value.kr_reason_template || ''
    config.representative_pick = form.value.kr_representative_pick || 'auto'
    config.fallback_strategy = form.value.kr_fallback_strategy || 'fallback_representative'
    config.drive_spec_substitute = form.value.kr_drive_spec_substitute !== false
  }
  if (runtimeType.value === 'compose') {
    config.kp_source = form.value.cp_kp_source || 'per_baseline'
    config.psu_override_enabled = form.value.cp_psu_override_enabled !== false
    config.psu_wattage_source = form.value.cp_psu_wattage_source || 'ext.psu_signal.wattage'
    config.psu_qty_source = form.value.cp_psu_qty_source || 'ext.psu_signal.qty'
  }
  if (showRuleCatalog.value) {
    config.rule_types = Array.isArray(form.value.rule_types) ? [...form.value.rule_types] : []
  }
  if (t === 'output') {
    config.name = form.value.output_name || ''
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
    if (form.value.output_kind === 'generic') {
      config.template = form.value.output_template || ''
      const outputSchema = parseJsonObject(form.value.output_schema_text)
      if (outputSchema === null) {
        message.error('输出 schema 不是合法 JSON 对象')
        return null
      }
      config.output_schema = outputSchema
    }
  }
  if (rt === 'agent_fill') {
    config.prompt = {
      system_prompt: (form.value.prompt?.system_prompt ?? '') || '',
    }
    config.rule_types = Array.isArray(form.value.rule_types) ? [...form.value.rule_types] : []
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
    if (runtimeType.value === 'agent') {
      merged.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
      merged.max_iterations = +form.value.max_iterations || (NODE_DEFAULT_CONFIG[activeNodeType.value]?.max_iterations ?? 5)
      merged.system_prompt = form.value.system_prompt || ''
    } else {
      delete merged.enabled_tools
      delete merged.max_iterations
      delete merged.max_rounds
      if (runtimeType.value !== 'kp_reason') {
        delete merged.system_prompt
      }
    }
    if (runtimeType.value === 'compose') {
      delete merged.template
      delete merged.output_schema
    }
    if (activeNodeType.value === 'output') {
      delete merged.bom_output
      delete merged.recommendation
      if (form.value.output_kind !== 'generic') {
        delete merged.template
        delete merged.output_schema
      }
    }
    if (runtimeType.value !== 'agent') {
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
              <a-form-item v-if="showSystemPrompt" label="System Prompt">
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
          <!-- 输出节点：交接契约 -->
          <a-form v-else-if="activeNodeType === 'output'" layout="vertical">
            <p class="rf-hint">输出节点只负责把上游结果交给下游业务实体或对话文本；不负责 BOM 展示样式和推荐语。</p>
            <a-form-item label="方案名称">
              <a-input v-model:value="form.output_name" placeholder="留空使用系统默认名称" />
              <p class="rf-hint">用于生成 BOM 方案草稿名称；仅业务实体输出会读取。</p>
            </a-form-item>
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
            <template v-if="form.output_kind === 'generic'">
              <a-divider orientation="left" class="rf-sec">通用格式</a-divider>
              <a-form-item label="输出模板">
                <a-textarea v-model:value="form.output_template" :rows="6" placeholder="可留空；例如 Markdown/文本模板" />
              </a-form-item>
              <a-form-item label="输出 schema（JSON 对象）">
                <a-textarea v-model:value="form.output_schema_text" :rows="10" placeholder="{}" style="font-family: ui-monospace, monospace;" />
                <p class="rf-hint">定义该节点产出结构；留空 = {}。执行器只透传 schema，不内嵌业务字段。</p>
              </a-form-item>
            </template>
          </a-form>


          <!-- 机型决策节点：确定性候选 + 展示文案，全部白盒可配 -->
          <a-form v-else-if="runtimeType === 'model_reason'" layout="vertical">
            <a-form-item label="按系列分组">
              <a-switch v-model:checked="form.mr_group_by_series" />
              <p class="rf-hint">开启后候选按系列分组展示，每组限量。</p>
            </a-form-item>
            <a-form-item label="每组机型数（上限）">
              <a-input-number v-model:value="form.mr_per_series_limit" :min="1" :max="10" style="width:100%" />
            </a-form-item>
            <a-form-item label="候选数量上限">
              <a-input-number v-model:value="form.mr_max_plans" :min="0" :max="50" placeholder="留空使用系统默认" style="width:100%" />
            </a-form-item>
            <a-form-item label="推荐策略 ID">
              <a-input v-model:value="form.mr_recommend_strategy_id" placeholder="留空使用默认策略" />
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">候选文案</a-divider>
            <a-form-item label="候选引言">
              <a-textarea v-model:value="form.mr_candidate_lede" :rows="2" placeholder="留空使用系统默认" />
            </a-form-item>
            <a-form-item label="选择引言">
              <a-textarea v-model:value="form.mr_choice_lede" :rows="2" placeholder="留空使用系统默认" />
            </a-form-item>
            <a-form-item label="无精确命中引言">
              <a-textarea v-model:value="form.mr_no_exact_lede" :rows="2" placeholder="留空使用系统默认" />
            </a-form-item>
            <a-form-item label="无匹配提问">
              <a-textarea v-model:value="form.mr_no_match_question" :rows="2" placeholder="留空使用系统默认" />
            </a-form-item>
          </a-form>

          <!-- 配件决策节点：LLM 结构化提议的 schema、提示词模板、合并映射全部可配 -->
          <a-form v-else-if="runtimeType === 'kp_reason'" layout="vertical">
            <p class="rf-hint">配件方案由 AI 按需求提议，规则库校验兜底；关闭 LLM 提议后只走规则库。</p>
            <a-form-item label="启用 LLM 提议">
              <a-switch v-model:checked="form.kr_proposal_enabled" />
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
            <a-form-item label="白盒说明模板">
              <a-input v-model:value="form.kr_reason_template" placeholder="配件规划：已确认 {{items}}" />
            </a-form-item>
            <a-divider orientation="left" class="rf-sec">规则匹配</a-divider>
            <a-form-item label="代表件策略">
              <a-select v-model:value="form.kr_representative_pick" style="width:100%">
                <a-select-option value="auto">按预算规则自动</a-select-option>
                <a-select-option value="min_price">最低价</a-select-option>
                <a-select-option value="max_price">最高价</a-select-option>
                <a-select-option value="first">第一件</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="未命中兜底策略">
              <a-select v-model:value="form.kr_fallback_strategy" style="width:100%">
                <a-select-option value="fallback_representative">回退代表件</a-select-option>
                <a-select-option value="mark_unmatched">标记未匹配</a-select-option>
                <a-select-option value="raise">中断报错</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="盘规格可替代">
              <a-switch v-model:checked="form.kr_drive_spec_substitute" />
              <p class="rf-hint">未精确命中时，允许用同规格替代盘；关闭则严格按规格匹配。</p>
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
            v-model:rule-types="form.rule_types"
            v-model:tools="form.enabled_tools"
            v-model:max-iterations="form.max_iterations"
            :tool-options="agentToolOptions"
            :rules-enabled="showRuleCatalog"
            :tools-enabled="toolsEnabled"
            :show-max-iterations="toolsEnabled"
            :rule-available="fillRuleTypes"
            :rule-defaults="fillRuleTypes"
          />
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
.node-behavior-chip.ghost { background: var(--cpq-glass-1-bg); color: var(--cpq-text-secondary); border: 1px dashed var(--cpq-border-primary); }
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
