<script setup lang="ts">
/** 能力节点配置抽屉 —— 按通用节点类型渲染参数表单。
 *  通用类型：agent / output；需求分析能力节点（agent_fill/model_reason/kp_reason/compose）按类型白盒展示可编辑参数。
 *  runtime 仅用于兼容当前需求分析能力图，不再暴露业务专属硬编码表单。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningNodeKey } from '@/api/reasoningFlow'
import { assistantApi } from '@/api/assistant'
import NodeResourceBindings from './NodeResourceBindings.vue'
import TargetLayerModal from './TargetLayerModal.vue'
import axios from 'axios'
import { REASONING_CFG_TYPES, nodeArchetype } from '@/utils/reasoningNodeMeta'

const OUTPUT_KIND_OPTIONS = [
  { value: 'bom_scheme_draft', label: 'BOM 方案草稿' },
  { value: 'requirement_draft', label: '需求单草稿' },
  { value: 'plans', label: '方案 / BOM' },
  { value: 'data_answer', label: '数据结论' },
  { value: 'generic', label: '通用 JSON' },
]
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
  return '配置节点'
})
const configurable = computed(() => Boolean(props.nodeType && CONFIGURABLE.includes(props.nodeType)) || Boolean(props.nodeRuntime && CONFIGURABLE.includes(props.nodeRuntime)))
const activeNodeType = computed(() => nodeArchetype(props.nodeType || props.nodeRuntime || ''))
const runtimeType = computed(() => props.nodeRuntime || props.nodeType || '')
const showSystemPrompt = computed(() => ['agent'].includes(runtimeType.value))
const toolsEnabled = computed(() => ['agent', 'agent_fill', 'model_reason', 'kp_reason'].includes(runtimeType.value))
const systemPromptValue = computed({
  get: () => (form.value?.system_prompt ?? ''),
  set: (v: string) => { if (form.value) form.value.system_prompt = v },
})
const PSU_SOURCE_OPTIONS = [
  { value: 'ext.psu.wattage', label: '需求电源信号 · 瓦数' },
  { value: 'ext.psu.wattage', label: '配件槽位 · 瓦数' },
  { value: 'auto', label: '自动推断（引擎）' },
]
const toolCatalog = ref<any[]>([])
const agentToolOptions = computed(() => toolCatalog.value.map((tool: any) => ({
  value: tool.name,
  label: tool.name,
  desc: tool.summary || tool.description || '',
  detail: tool.description || '',
  dataSources: Array.isArray(tool.data_sources) ? tool.data_sources.map((s: any) => String(s)) : [],
})))

// 机制工具（节点机制必需，锁定勾选不可取消）：唯一真源 = 后端 capability_spec，
// 由 /api/reasoning-flow/capabilities 下发；此处不自存副本。
const capabilityCatalog = ref<any[]>([])
const mechanismTools = computed(() => {
  // 画布新增节点可能是 agent_fill_2 这类后缀 id：回退到基础类型取声明（与后端同口径）
  const rt = String(runtimeType.value || "")
  const base = rt.includes("_") ? rt.slice(0, rt.lastIndexOf("_")) : rt
  const spec = capabilityCatalog.value.find((c: any) => c?.key === rt)
    || capabilityCatalog.value.find((c: any) => c?.key === base)
  return Array.isArray(spec?.mechanism_tools) ? spec.mechanism_tools.map((t: any) => String(t)) : []
})
async function loadCapabilities() {
  try {
    const { data } = await axios.get('/api/reasoning-flow/capabilities')
    capabilityCatalog.value = Array.isArray(data?.capabilities) ? data.capabilities : []
  } catch {
    capabilityCatalog.value = []
  }
}

// 候选池数据源（kp_reason 资源层"插头"）：换源 → 大脑候选上下文/确认卡自选候选/问句倾向
// 随之变化（白盒标注 pool_source）。选项来自注册表端点；params.limit 可调。
const poolResolvers = ref<Array<{ name: string; description: string; is_default?: boolean }>>([])
const cpPoolResolver = ref('')
const cpPoolLimit = ref<number | null>(20)
async function loadPoolResolvers() {
  try {
    const { data } = await axios.get('/api/reasoning-flow/candidate-resolvers')
    poolResolvers.value = Array.isArray(data?.resolvers) ? data.resolvers : []
    if (!cpPoolResolver.value) {
      const d = poolResolvers.value.find(r => r.is_default)
      const cfg0: any = props.initialConfig || {}
      cpPoolResolver.value = cfg0?.data_bindings?.kp_pool?.resolver || d?.name || ''
      cpPoolLimit.value = Number(cfg0?.data_bindings?.kp_pool?.params?.limit) || 20
    }
  } catch {
    poolResolvers.value = []
  }
}
async function loadToolCatalog() {
  try {
    toolCatalog.value = await assistantApi.tools.catalog()
  } catch {
    toolCatalog.value = []
  }
}

// ── 目标层输出物卡片（agent_fill 样板）：读节点配置的 target 描述符（DB node_configs）──
// 字段数/必填数从 requirement_slots schema 实时统计（同源，不双写）；大表不塞抽屉，点卡片进弹窗。
const tlOpen = ref(false)
const slotStats = ref({ fields: 0, required: 0 })
const targetArtifacts = computed<any[]>(() => {
  const t = (props.initialConfig as any)?.target?.artifacts
  return Array.isArray(t) ? t : []
})
const kindLabel = (k: string) => ({ form: '表单', document: '文档', media: '媒体', table: '表格', sheet_section: '配置表切片' }[k] || k)

async function onSaveTarget(arts: any[]) {
  if (!props.nodeKey) return
  try {
    const cfg = { ...(props.initialConfig || {}), target: { ...(props.initialConfig?.target || {}), artifacts: arts } }
    await reasoningFlowApi.updateNode(props.nodeKey as any, cfg, props.nodeLabel || undefined, props.skillKey || undefined)
    message.success('目标层已保存（下次推理生效）')
    emit('saved')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '目标层保存失败')
  }
}
async function loadSlotStats() {
  try {
    const { data } = await axios.get('/api/system-config/requirement_slots/value')
    const list = Array.isArray(data?.value?.slots) ? data.value.slots : []
    slotStats.value = {
      fields: list.length,
      required: list.filter((s: any) => String(s.level || '') === 'L0').length,
    }
  } catch {
    slotStats.value = { fields: 0, required: 0 }
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
  loadCapabilities()
  if (runtimeType.value === 'agent_fill') loadSlotStats()
  if (runtimeType.value === 'kp_reason') loadPoolResolvers()
  const c = props.initialConfig || {}
  const outputKind = c.output_kind || props.skillOutputKind || (props.skillKey === 'requirement_analysis' ? 'bom_scheme_draft' : props.skillKey === 'trend_analysis' ? 'data_answer' : 'generic')
  form.value = {
    label: props.nodeLabel ?? '',
    enabled_tools: Array.isArray(c.enabled_tools) ? [...c.enabled_tools] : [],
    cp_kp_source: c.kp_source ?? 'per_baseline',
    cp_psu_override_enabled: c.psu_override_enabled ?? true,
    cp_psu_wattage_source: c.psu_wattage_source ?? 'ext.psu.wattage',
    cp_psu_qty_source: c.psu_qty_source ?? 'ext.psu.qty',
    cp_pool_resolver: c.data_bindings?.kp_pool?.resolver || '',
    cp_pool_limit: Number(c.data_bindings?.kp_pool?.params?.limit) || 20,
    system_prompt: c.system_prompt ?? '',
    output_name: c.name ?? '',
    output_kind: outputKind,
    output_payload_map_text: safeJsonString(c.payload_map),
    output_actions_text: safeJsonString(c.actions),
    output_template: c.template || '',
    output_schema_text: safeJsonString(c.output_schema),
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
    config.system_prompt = form.value.system_prompt || ''
  }
  if (runtimeType.value === 'compose') {
    config.kp_source = form.value.cp_kp_source || 'per_baseline'
    config.psu_override_enabled = form.value.cp_psu_override_enabled !== false
    config.psu_wattage_source = form.value.cp_psu_wattage_source || 'ext.psu.wattage'
    config.psu_qty_source = form.value.cp_psu_qty_source || 'ext.psu.qty'
  }
  if (runtimeType.value === 'model_reason' || runtimeType.value === 'kp_reason') {
    config.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
  }
  if (runtimeType.value === 'kp_reason') {
    // 数据绑定插头（资源与权限层"数据源"）：换源 → 大脑候选上下文/确认卡自选候选/
    // 问句倾向随之变化（node_trace 白盒标注 pool_source 验证）
    config.data_bindings = {
      kp_pool: {
        source: 'kp_library',
        resolver: String(form.value.cp_pool_resolver || 'category_series_search'),
        params: { limit: Number(form.value.cp_pool_limit) || 20 },
      },
    }
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
    // 交接去向由 output_kind 决定；target 是产物槽（插头），不在这里写。
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
    config.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
    // 目标层输出物描述符（卡片数据源）：随节点配置持久化（DB node_configs）
    config.target = { artifacts: targetArtifacts.value }
  }
  return config
}

async function persist(config: Record<string, any>): Promise<boolean> {
  saving.value = true
  try {
    const isLegacyRuntime = Boolean(props.nodeRuntime && props.nodeRuntime !== props.nodeType)
    const base = isLegacyRuntime ? { ...(props.initialConfig || {}) } : {}
    const merged = { ...base, ...config }
    delete merged.prompt
    if (runtimeType.value === 'agent') {
      merged.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
      merged.system_prompt = form.value.system_prompt || ''
    } else if (runtimeType.value === 'model_reason' || runtimeType.value === 'kp_reason') {
      merged.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
      delete merged.max_iterations
      delete merged.max_rounds
      delete merged.system_prompt
    } else if (runtimeType.value === 'agent_fill') {
      // 登记节点：AI 层=节点任务说明，工具=资源层勾选（fill_requirement 由登记回合按需挂载）
      merged.enabled_tools = Array.isArray(form.value.enabled_tools) ? [...form.value.enabled_tools] : []
      delete merged.max_iterations
      delete merged.max_rounds
      delete merged.system_prompt
      delete merged.signal_backfill   // 2026-09-02 死配置清理：后端已无消费者
    } else {
      delete merged.enabled_tools
      delete merged.max_iterations
      delete merged.max_rounds
      delete merged.system_prompt
    }
    if (runtimeType.value === 'kp_reason' || runtimeType.value === 'model_reason') {
      // 清理旧内核遗留字段：新阶段机不读这些键，留着会误导"配置已生效"。
      delete merged.confirm_mode
      delete merged.reason_template
      delete merged.representative_pick
      delete merged.fallback_strategy
      delete merged.drive_spec_substitute
      delete merged.series_limit
      delete merged.detail_link_enabled
      delete merged.intro_length
      delete merged.sort_by
      delete merged.system_prompt
    }
    if (runtimeType.value === 'kp_reason') {
      delete merged.proposal_enabled
      delete merged.proposal_schema
      delete merged.proposal_mapping
      delete merged.user_prompt_template
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
      // config.target 旧语义是「交接目标字符串」，现语义是产物槽（target.artifacts，插头）。
      // 名字相同含义不同：一旦被写成字符串，resolve_kind 就找不到槽 → 节点下产物消失。
      // 这里直接剔除非物件 target，交回节点默认产物槽（同时自愈历史写坏的数据）。
      if (!(merged.target && typeof merged.target === 'object')) delete merged.target
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
            

      <!-- 节点名称：独立字段（AI 指令唯一入口 = Skill Studio 左栏「使用说明」；抽屉只留机制配置） -->
      <div class="node-zone node-zone--name">
        <div class="node-zone-body">
          <a-form layout="vertical" class="node-config-form node-common-form">
            <a-form-item label="节点名称">
              <a-input v-model:value="form.label" placeholder="填写该节点在当前能力中的名称" maxlength="40" />
              <p class="rf-hint">节点名称属于实例属性，可随能力复用而改名；不影响节点类型与执行逻辑。</p>
            </a-form-item>
            <a-collapse v-if="showSystemPrompt" :bordered="false" class="node-advanced-fields">
              <a-collapse-panel key="sys" header="节点提示（System Prompt，可选）">
                <a-textarea v-model:value="systemPromptValue" :rows="4" placeholder="留空使用该节点类型默认任务说明" />
                <p class="rf-hint">只描述本节点要完成什么、输入输出是什么；角色性格与说话语气由 AI 角色层统一负责。</p>
              </a-collapse-panel>
            </a-collapse>
          </a-form>
        </div>
      </div>

      <div class="node-zone">
        <div class="node-zone-head">
          <span class="node-zone-index">1</span>
          <span class="node-zone-title">目标层</span>
          <span class="node-zone-note">要输出的目标（字段表 / 输出物）</span>
        </div>
        <div class="node-zone-body">
          <template v-if="targetArtifacts.length">
            <div class="node-section-title">输出物 <span class="node-behavior-chip">要产出的目标</span></div>
            <div class="tl-card-list">
              <div v-for="art in targetArtifacts" :key="art.view || art.name" class="tl-card" @click="tlOpen = true">
                <div class="tl-card-head">
                  <span class="tl-card-icon">📋</span>
                  <span class="tl-card-name">{{ art.name }}</span>
                  <span class="tl-card-kind">{{ kindLabel(art.kind) }}</span>
                </div>
                <div class="tl-card-meta">
                  <template v-if="runtimeType === 'agent_fill'">
                    <span>字段 {{ slotStats.fields }}</span>
                    <span>必填 {{ slotStats.required }}</span>
                  </template>
                  <template v-else-if="(art.columns || []).length">
                    <span>列：{{ (art.columns || []).map((c: any) => c.label || c.key).join(' / ') }}</span>
                  </template>
                  <span v-if="art.view">视图 {{ art.view }}</span>
                </div>
              </div>
              <div v-if="runtimeType === 'agent_fill'" class="tl-card tl-card--add" title="更多输出物类型后续版本开放"
                   @click.stop="message.info('方案配置表 / 文档 / 媒体类输出物将在后续版本开放')">
                ＋ 添加输出物
              </div>
            </div>
            <p class="rf-hint">点卡片查看输出物详情；字段/中文名/顺序的权威是下游页面表单定义，此处自动跟随。</p>
            <TargetLayerModal v-model:open="tlOpen" :artifact="targetArtifacts[0] || null"
                              :node-key="nodeKey" :skill-key="skillKey" @save-target="onSaveTarget" />
          </template>
          <template v-else-if="runtimeType === 'agent_fill'">
            <p class="rf-hint">目标层未配置输出物描述符（target.artifacts）。</p>
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
            <a-collapse :bordered="false" class="node-advanced-fields">
              <a-collapse-panel key="advanced" header="高级交接配置（可选，一般不手写 JSON）">
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
              </a-collapse-panel>
            </a-collapse>
          </a-form>


          <!-- 机型选配节点：目标 = 方案配置表 L6 配置单（与商机详情页一致） -->
          <a-form v-else-if="runtimeType === 'model_reason'" layout="vertical">
            <div class="node-section-title">目标表 <span class="node-behavior-chip">对齐商机详情页 · 方案配置表 L6 部分</span></div>
            <table class="l6-target-table">
              <thead>
                <tr><th>Catalogue</th><th>Description</th><th>Qty</th><th>Cost</th></tr>
              </thead>
              <tbody>
                <tr><td colspan="4" class="l6-target-empty">行内容由所机型族 BOM 模板 + 选配结果生成</td></tr>
              </tbody>
            </table>
            <p class="rf-hint">本节点要填的是商机详情页「方案配置表」的 L6 部分：选定机型后，按该机型族的 BOM 模板（骨架行）与选配结果生成 Catalogue / Description / Qty。行骨架与取值来自「工具层」的在售机型、基准配置与规则目录（工具：choose_model → 数据源 candidate_search），不在此处硬编码。</p>
          </a-form>

          <!-- 配件选配节点：目标 = 方案配置表 KP 配置单（与商机详情页一致） -->
          <a-form v-else-if="runtimeType === 'kp_reason'" layout="vertical">
            <div class="node-section-title">目标表 <span class="node-behavior-chip">对齐商机详情页 · 方案配置表 KP 部分</span></div>
            <table class="l6-target-table">
              <thead>
                <tr><th>Catalogue</th><th>Configuration Description</th><th>Qty</th></tr>
              </thead>
              <tbody>
                <tr><td colspan="3" class="l6-target-empty">行内容由需求摘要 + 已选机型选配方案生成</td></tr>
              </tbody>
            </table>
            <p class="rf-hint">本节点要填的是商机详情页「方案配置表」的 KP 部分：按需求摘要与已锁定机型，从配件库逐类匹配配件（CPU/内存/盘/GPU/RAID/网卡/电源），生成 Catalogue / Configuration Description / Qty，并落地真实 SKU。行骨架与取值来自「工具层」的配件库、规格规则与需求摘要（工具：query_parts 检索、select_parts 锁定），不在此处硬编码。</p>
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
              <p class="rf-hint">开启时，需求中明确给出的电源瓦数/数量会覆盖 引擎的负载推断结果。</p>
            </a-form-item>
            <a-form-item label="电源瓦数读取路径">
              <a-select v-model:value="form.cp_psu_wattage_source" :options="PSU_SOURCE_OPTIONS" style="width:100%" />
            </a-form-item>
            <a-form-item label="电源数量读取路径">
              <a-select v-model:value="form.cp_psu_qty_source" :options="PSU_SOURCE_OPTIONS" style="width:100%" />
            </a-form-item>
          </a-form>

          <a-form v-else layout="vertical">
            <p class="rf-hint">该节点暂无额外节点专属设置；其执行行为由节点元数据与后端默认配置决定。</p>
          </a-form>
        </div>
      </div>

      <div class="node-zone">
        <div class="node-zone-head">
          <span class="node-zone-index">2</span>
          <span class="node-zone-title">工具层</span>
          <span class="node-zone-note">能调什么（数据随工具派生）</span>
        </div>
        <div class="node-zone-body">
          <NodeResourceBindings
            v-model:tools="form.enabled_tools"
            :tool-options="agentToolOptions"
            :tools-enabled="toolsEnabled"
            :tools-readonly="false"
            :locked-tools="mechanismTools"
          />
          <!-- 候选池数据源（kp_reason 资源层"数据源"插头）：换源可观测（pool_source 白盒） -->
          <div v-if="runtimeType === 'kp_reason'" class="node-section">
            <div class="node-section-title">候选池数据源</div>
            <a-select
              v-model:value="form.cp_pool_resolver"
              :options="poolResolvers.map(r => ({ value: r.name, label: `${r.name} · ${r.description}` }))"
              placeholder="选择候选池数据源"
              style="width:100%"
            />
            <div class="node-section" style="margin-top: 8px; padding: 8px 10px;">
              <span class="rf-hint">检索候选上限</span>
              <a-input-number v-model:value="form.cp_pool_limit" :min="1" :max="80" size="small" style="width: 100%; margin-top: 4px;" />
            </div>
            <p class="rf-hint">换源后下一轮推理生效：大脑候选上下文、确认卡自选候选、node_trace 标注的数据源随之变化。</p>
          </div>
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
.l6-target-table { width: 100%; border-collapse: collapse; font-size: 12px; margin: 2px 0 10px; }
.l6-target-table th, .l6-target-table td { border: 1px solid var(--cpq-border-primary); padding: 6px 8px; text-align: left; }
.l6-target-table th { background: var(--cpq-glass-2-bg); font-weight: 600; color: var(--cpq-text-secondary); }
.l6-target-table td { color: var(--cpq-text-primary); }
.l6-target-empty { text-align: center; color: var(--cpq-text-muted); }
.rf-output-list { margin: 4px 0 0 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--cpq-text-primary); line-height: 1.6; }
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
.node-zone--name {
  margin-bottom: 10px;
  border: none;
  background: transparent;
  box-shadow: none;
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

/* ── 目标层输出物卡片（大表不塞抽屉：点卡片进弹窗看全表）── */
.tl-card-list { display: flex; flex-direction: column; gap: 8px; }
.tl-card {
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, .12));
  border-radius: 10px; padding: 10px 12px; cursor: pointer;
  background: var(--cpq-overlay-w06, rgba(255, 255, 255, .04));
  transition: border-color .18s ease, transform .18s ease;
}
.tl-card:hover { border-color: var(--cpq-accent-primary, #1677ff); transform: translateY(-1px); }
.tl-card--add {
  border-style: dashed; color: var(--cpq-text-secondary, #a6adb4);
  text-align: center; font-size: 12px; padding: 8px;
  background: transparent; cursor: pointer;
}
.tl-card--add:hover { color: var(--cpq-accent-primary, #1677ff); transform: none; }
.tl-card-head { display: flex; align-items: center; gap: 8px; }
.tl-card-name { font-weight: 600; color: var(--cpq-text-primary); font-size: 13px; }
.tl-card-kind { margin-left: auto; font-size: 11px; color: var(--cpq-text-secondary); }
.tl-card-meta { display: flex; gap: 10px; margin-top: 6px; font-size: 11px; color: var(--cpq-text-muted); }
</style>
