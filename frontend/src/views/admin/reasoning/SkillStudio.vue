<script setup lang="ts">
/** 推理流可视化编排画布（策略中心·需求分析域）—— 两栏布局：
 *  中 vue flow 画布（编排+连线）/ 右试运行 playground。
 *  P2 vue flow 编排（连线/删节点/配置抽屉）+ 图驱动 executor（后端）。
 *  试运行：右栏由内嵌 AssistantPanel 对话驱动，节点逐步高亮 + 步骤明细 + 候选方案。
 *  画布吃滚轮缩放，放下方时下滑找入口会误缩放，故画布与试运行左右并列。 */
import { ref, shallowRef, onMounted, onUnmounted, markRaw, watch, computed, provide } from 'vue'
import { VueFlow, useVueFlow, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { message } from 'ant-design-vue'
import { UndoOutlined, RedoOutlined } from '@ant-design/icons-vue'
import { reasoningFlowApi, type ReasoningFlow as RFlow } from '@/api/reasoningFlow'
import ReasoningNodeVf from './ReasoningNodeVf.vue'
import ReasoningNodeDrawer from './ReasoningNodeDrawer.vue'
import NodeArtifactModal from './NodeArtifactModal.vue'
import AssistantPanel from '@/components/assistant/AssistantPanel.vue'
import { systemConfigApi } from '@/api/systemConfig'
import { REASONING_CFG_TYPES, reasoningNodeKind, nodeArchetype } from '@/utils/reasoningNodeMeta'

const props = defineProps<{ skill?: any }>()
const skillKey = computed(() => String(props.skill?.workflow_key || props.skill?.key || '').trim())

// ── 左栏：大脑视角单框（浏览=实际说明书；编辑=使用说明全文，保存即 AI 下一回合读到）──
const manualRules = ref('')
const manualSaving = ref(false)
const manualEditing = ref(false)

async function loadManual() {
  try {
    const r = await reasoningFlowApi.getManual(skillKey.value)
    if (!manualEditing.value) manualRules.value = r.rules || ''
  } catch {
    message.warning('使用说明加载失败，请稍后重试')
  }
}

function onEditManual() {
  manualEditing.value = true
}

function onCancelManualEdit() {
  manualEditing.value = false
  loadManual()
}

async function onSaveManualRules() {
  manualSaving.value = true
  try {
    await reasoningFlowApi.saveManualRules(manualRules.value, skillKey.value)
    message.success('已保存：大脑下一回合读到新规则')
    manualEditing.value = false
    await loadManual()
  } catch {
    message.error('保存失败，请重试')
  } finally {
    manualSaving.value = false
  }
}
const outputKind = computed(() => {
  const raw = String(props.skill?.output_kind || '').trim()
  if (raw) return raw
  return props.skill?.key === 'requirement_analysis' ? 'bom_scheme_draft' : 'generic'
})

/** 节点元数据统一读 utils/reasoningNodeMeta（节点卡 / 抽屉 / 时间线共用真源） */
const CFG_TYPES = REASONING_CFG_TYPES
const GENERIC_NODE_TYPES = new Set(['agent', 'output'])
function runtimeForType(type: string): string | undefined {
  return GENERIC_NODE_TYPES.has(type) ? undefined : type
}

// ── 连线染色（2026-08 通用能力编辑器：由节点 kind 派生，不再维护逐节点路由表）──
// agent=蓝（LLM 决策 / 工具调用）/ output=灰绿（组装 / 最终产出）
const ROUTE_META: Record<string, { label: string; sub: string; cls: string }> = {
  ai: { label: '智能体节点', sub: 'LLM 决策 / 工具调用', cls: 'rf-edge--ai' },
  shared: { label: '输出节点', sub: '组装 / 最终产出', cls: 'rf-edge--shared' },
}
function routeOf(stepType?: string): 'ai' | 'shared' {
  const kind = reasoningNodeKind(stepType)
  if (kind === 'agent') return 'ai'
  return 'shared'
}
/** 边 route：任一端 ai→ai；否则 shared */
function edgeRoute(e: { source: string; target: string }): 'ai' | 'shared' {
  const sn = nodes.value.find((n) => n.id === e.source)
  const tn = nodes.value.find((n) => n.id === e.target)
  const sr = routeOf(sn?.data?.stepType)
  const tr = routeOf(tn?.data?.stepType)
  if (sr === 'ai' || tr === 'ai') return 'ai'
  return 'shared'
}
function routeClass(e: { source: string; target: string }): string {
  return `rf-edge--${edgeRoute(e)}`
}

const nodes = ref<any[]>([])
const edges = shallowRef<Edge[]>([])
const flow = ref<RFlow | null>(null)
const loading = ref(false)
const nodeTypes = markRaw({ rf: ReasoningNodeVf }) as any

const drawerOpen = ref(false)
const drawerNodeKey = ref<string | null>(null)
const drawerNodeType = ref<string | null>(null)
const drawerNodeRuntime = ref<string | null>(null)
const drawerNodeLabel = ref<string | null>(null)
const drawerConfig = ref<Record<string, any> | null>(null)

const { onConnect, onNodeDragStop, onNodeClick, onEdgeClick, getSelectedNodes, getSelectedEdges } = useVueFlow()

// ── 试运行 playground（右栏）──
// 试运行输入默认清空（历史曾预填演示需求，2026-08-05 移除：避免误以为是系统内置需求）
const reqText = ref('')
provide('studioReqText', reqText)
/** 把对话 node_trace 的执行状态/产出写回画布 nodes（按 node id 精确匹配，id=null 清全部） */
function applyNodeState(id: string | null, state: any) {
  nodes.value = nodes.value.map((n) => (id === null || n.id === id
    ? {
        ...n,
        data: {
          ...n.data,
          execState: id === null ? null : state.execState,
          badge: id === null ? undefined : state.badge,
          input: id === null ? undefined : (state.input ?? n.data?.input),
          output: id === null ? undefined : (state.output ?? n.data?.output),
          summary: id === null ? undefined : (state.summary ?? n.data?.summary),
          artifact: id === null ? undefined : (state.artifact ?? n.data?.artifact),
        },
      }
    : n))
}

  // ── 画布运行状态：由内嵌 AssistantPanel 的对话 node_trace 驱动（不再走 test-run WS）──
  const running = ref(false)
  const missingFields = ref<string[]>([])
  const bomScheme = ref<any>(null)
  const assistantRef = ref<InstanceType<typeof AssistantPanel> | null>(null)

  // ── 产出物窗口（需求理解节点）：捕获 requirement_slots，逐字段展示填充状态 ──
  const reqFormSlots = ref<any>(null)
  function normalizeRequirementSlots(data: any) {
    const d = data && typeof data === 'object' ? data : {}
    return {
      ...d,
      server_type: d.server_type_name || d.server_type || '',
      platform_type: d.series || d.platform_type || '',
      chassis_form: d.form || d.chassis_form || '',
      server_model: d.server_model || d.model || d.baseline_model || '',
      purchase_qty: d.purchase_qty,
      warranty_years: d.warranty_years || '',
    }
  }

  // 对话 node_trace → 画布节点产出/下游交接 + 线索登记表进度
  watch(() => assistantRef.value?.nodeTraces, (traces) => {
    if (!Array.isArray(traces)) return
    for (const t of traces) {
      if (!t?.step) continue
      applyNodeState(t.step, {
        execState: t.status === 'running' ? 'running' : (t.status === 'done' ? 'done' : null),
        badge: typeof t.duration_ms === 'number' ? `${(t.duration_ms / 1000).toFixed(1)}s` : undefined,
        input: t.input,
        output: t.output,
        summary: t.summary,
        artifact: t.artifact,
      })
    }
    const latest = (kind: string) => [...traces].reverse().find((x) => x?.artifact?.kind === kind)
    const slots = latest('requirement_slots')
    const miss = latest('requirement_missing')
    if (slots || miss) {
      if (slots?.artifact?.data) reqFormSlots.value = normalizeRequirementSlots(slots.artifact.data)
      // 合并后的智能对话填表 Agent 不再有独立 requirement_missing 步：缺失字段从 agent 节点 output.missing_critical 兜底取
      const missFromSlots = Array.isArray(slots?.output?.missing_critical) ? slots.output.missing_critical : []
      missingFields.value = Array.isArray(miss?.artifact?.data?.missing_fields)
        ? miss.artifact.data.missing_fields
        : missFromSlots
    }
    const bom = latest('bom_scheme')
    if (bom?.artifact?.data) bomScheme.value = bom.artifact.data
  }, { deep: true })

  // `运行中` 状态：跟随后端对话 busy（waitingAI / statusText / streamingText）
  watch(() => assistantRef.value?.busy, (v) => {
    running.value = !!v
  }, { immediate: true })
onUnmounted(() => { document.body.style.cursor = ''; document.body.style.userSelect = '' })

// ── 右栏：复用真实 AI 角色对话（AssistantPanel 内嵌·预览），input 节点「运行」发送文本到对话 ──
async function onRun() {
  const text = reqText.value.trim()
  if (!text || running.value) return
  // 不清空上一轮节点产物：新一轮的 node_trace 会逐节点覆盖；运行中旧产物保留可对照。
  const inputNode = nodes.value.find((n) => String(n.data?.stepType) === 'input')
  if (inputNode) {
    applyNodeState(inputNode.id, { execState: 'done', badge: undefined, input: text, output: text })
  }
  await assistantRef.value?.sendText?.(text)
}

/** 重置测试：purge 预览线程 + 清聊天/节点轨迹/画布运行态/输入框（显式重置才全清）。 */
async function onResetTest() {
  if (running.value) return
  await assistantRef.value?.resetPreview?.()
  nodes.value = nodes.value.map((n) => ({
    ...n,
    data: {
      ...n.data,
      execState: null,
      badge: undefined,
      input: undefined,
      output: undefined,
      summary: undefined,
      artifact: undefined,
      askQuestion: undefined,
    },
  }))
  reqFormSlots.value = null
  bomScheme.value = null
  missingFields.value = []
  reqText.value = ''
}

// ── 画布节点注入：运行按钮（input 节点）──
provide('studioRun', onRun)
provide('studioRunning', running)

// ── 线索登记表：字段契约（RequirementSlots 同构）→ 逐字段填充状态 ──
const reqGroups = ref<{ title: string; fields: { key: string; label: string; srcType: string; category: string }[] }[]>([])
async function loadReqGroups() {
  try {
    // 线索登记表字段契约 = 基本信息(requirement_slots 配置) + 部件(KP 大类动态合成)
    const cfg = await systemConfigApi.getRequirementSlotsSpec()
    const slots = Array.isArray(cfg?.slots)
      ? cfg.slots.filter((s: any) => s?.key && s?.free_row !== true)
      : []
    const map = new Map<string, { title: string; fields: { key: string; label: string; srcType: string; category: string }[] }>()
    for (const s of slots) {
      const title = String(s.group || '其他')
      const g = map.get(title) || { title, fields: [] }
      g.fields.push({
        key: String(s.key),
        label: String(s.label || s.key),
        srcType: String(s.src_type || s.srcType || ''),
        category: String(s.category || ''),
      })
      map.set(title, g)
    }
    reqGroups.value = Array.from(map.values())
  } catch (e) {
    console.error('加载字段配置失败:', e)
    reqGroups.value = []
  }
}
function hasContent(v: any): boolean {
  if (v === null || v === undefined) return false
  if (typeof v === 'string') return v.trim() !== ''
  if (typeof v === 'number') return v > 0
  if (Array.isArray(v)) return v.some(hasContent)
  if (typeof v === 'object') return Object.values(v).some(hasContent)
  return Boolean(v)
}
// 部件「已填」判定 = 目标登记表（kp_rows）是否真落了该大类的非空行。
// 不做任何别名/正则映射：AI 填的就是目标表大类（填表契约已约束），前端只读落库结果。
function kpFieldFilled(s: any, f: { category: string }): boolean {
  const rows = Array.isArray(s?.kp_rows) ? s.kp_rows : []
  const cat = String(f.category || '').trim()
  if (!cat) return false
  return rows.some((r: any) => {
    const pc = String(r?.part_category || r?.category || '').trim()
    return pc === cat && String(r?.description || r?.catalogue || '').trim() !== ''
  })
}
type FieldStatus = 'filled' | 'optional' | 'asked'
const reqTotal = computed(() => reqGroups.value.reduce((n, g) => n + g.fields.length, 0))
const reqFieldRows = computed(() => {
  const s = reqFormSlots.value || {}
  const missing = new Set(missingFields.value || [])
  return reqGroups.value.map((group) => ({
    title: group.title,
    fields: group.fields.map((f) => {
      const filled = f.srcType === 'kp' ? kpFieldFilled(s, f) : hasContent(s[f.key])
      const status: FieldStatus = filled ? 'filled' : (missing.has(f.key) ? 'asked' : 'optional')
      return { key: f.key, label: f.label, status }
    }),
  }))
})
const reqFilled = computed(() => reqFieldRows.value.flatMap((g) => g.fields).filter((f) => f.status === 'filled').length)
const reqSlotsEmpty = computed(() => !reqFormSlots.value)
const reqCold = computed(() => !reqFormSlots.value && !running.value && !(missingFields.value || []).length)
const reqBadgeText = computed(() => {
  if (!reqGroups.value.length) return reqCold.value ? '待生成' : '配置为空'
  if (reqCold.value) return '待生成'
  if (reqSlotsEmpty.value || reqFilled.value < reqTotal.value) return '填充中'
  return '已填满'
})
const reqBadgeClass = computed(() => {
  if (!reqGroups.value.length || reqCold.value) return 'idle'
  if (reqFilled.value >= reqTotal.value) return 'done'
  return 'fill'
})

// 给「需求理解」节点卡内嵌线索登记表进度卡的数据（单出一份视图，节点/右栏不再重复维护）
const reqSlotsView = computed(() => ({
  cold: reqCold.value,
  badgeText: reqBadgeText.value,
  badgeClass: reqBadgeClass.value,
  filled: reqFilled.value,
  total: reqTotal.value,
  pctText: pct(reqFilled.value, reqTotal.value),
  missingCount: (missingFields.value || []).length,
  rows: reqFieldRows.value,
  followLabel: followLabel.value,
  running: running.value,
}))
provide('studioReqSlotsView', reqSlotsView)

function pct(v: number, t: number) { return (t ? Math.round((v / t) * 100) : 0) + '%' }
const followLabel = computed(() => {
  const flat = reqFieldRows.value.flatMap((g) => g.fields)
  const asked = flat.find((f) => f.status === 'asked')
  return asked?.label || flat.filter((f) => f.status === 'filled').slice(-1)[0]?.label || ''
})

let _firstLoad = true
async function load() {
  loading.value = true
  try {
    const r = await reasoningFlowApi.get(skillKey.value)
    flow.value = r.flow
    const fl = r.flow
    if (!fl) { message.warning('无 active 推理流'); return }
    nodes.value = fl.graph.nodes.map((n: any) => {
      const rawType = n.type || ''
      const runtime = n.runtime || runtimeForType(rawType)
      return {
        id: n.id,
        type: 'rf',
        position: n.position,
        data: {
          stepType: rawType,
          runtime,
          label: n.label,
          configurable: CFG_TYPES.includes(rawType) || CFG_TYPES.includes(runtime || ''),
        },
      }
    })
    edges.value = fl.graph.edges.map((e: any): Edge => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle ?? null,
      targetHandle: e.target_handle ?? null,
      label: e.label ?? undefined,
      type: 'smoothstep',
      animated: e.animated !== false,
      class: routeClass(e),
    }))
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
    if (_firstLoad) {
      resetHistory()  // 首次加载：无历史可撤
      _firstLoad = false
    }
  }
}

let persistTimer: ReturnType<typeof setTimeout> | null = null
async function persistGraph() {
  if (!flow.value) return
  // 防 active flow 漂移：若 active 被外部切换（升级脚本/版本切换/他人编辑），画布内存已过期，
  // 直接写回会污染新 active —— 先比对 id，不一致则放弃回写并刷新画布。
  try {
    const cur = await reasoningFlowApi.get(skillKey.value)
    if (cur.flow && String(cur.flow.id) !== String(flow.value.id)) {
      message.warning('推理流 active 版本已被切换，已停止回写，正在刷新画布…')
      load()
      return
    }
  } catch { /* GET 失败降级为原行为（仍 persist） */ }
  const g = {
    nodes: nodes.value.map(n => {
      const rawType = n.data?.stepType || 'unknown'
      const runtime = n.data?.runtime || runtimeForType(rawType)
      return {
        id: n.id,
        type: nodeArchetype(rawType || runtime || ''),
        runtime: runtime || undefined,
        label: n.data?.label || n.id,
        position: n.position,
      }
    }),
    edges: edges.value.map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      source_handle: e.sourceHandle ?? null,
      target_handle: e.targetHandle ?? null,
      label: e.label ?? null,
      animated: e.animated !== false,
    })),
  }
  try {
    await reasoningFlowApi.updateGraph(g, skillKey.value)
  } catch (e: any) {
    message.error('持久化失败：' + (e.response?.data?.detail || e.message))
  }
}
function debouncePersist() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(persistGraph, 600)
}

// ── 画布撤销/重做（结构编辑：加/删节点、连线/删线、拖拽位置；config 抽屉保存立即入库不在此列）──
const undoStack = ref<Array<{ nodes: any[]; edges: any[] }>>([])
const redoStack = ref<Array<{ nodes: any[]; edges: any[] }>>([])
function snapshotState() {
  return {
    nodes: JSON.parse(JSON.stringify(nodes.value)),
    edges: JSON.parse(JSON.stringify(edges.value)),
  }
}
function historyEqual(a: any, b: any) {
  return JSON.stringify(a) === JSON.stringify(b)
}
/** 每次结构变更前调用：快照当前状态入撤销栈（连续相同变更去重） */
function recordHistory() {
  const snap = snapshotState()
  const last = undoStack.value[undoStack.value.length - 1]
  if (last && historyEqual(last, snap)) return
  undoStack.value.push(snap)
  if (undoStack.value.length > 50) undoStack.value.shift()  // 上限 50 步，防内存膨胀
  redoStack.value = []
}
function undo() {
  const prev = undoStack.value.pop()
  if (!prev) return
  redoStack.value.push(snapshotState())
  nodes.value = prev.nodes
  edges.value = prev.edges
  debouncePersist()
  message.success('已撤销')
}
function redo() {
  const next = redoStack.value.pop()
  if (!next) return
  undoStack.value.push(snapshotState())
  nodes.value = next.nodes
  edges.value = next.edges
  debouncePersist()
  message.success('已重做')
}
function resetHistory() {
  undoStack.value = []
  redoStack.value = []
}
// Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y / Backspace（输入框内不拦截）
function onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) return
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault()
    if (e.shiftKey) redo()
    else undo()
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
    e.preventDefault()
    redo()
  } else if (e.key === 'Backspace' || e.key === 'Delete') {
    // 删除所选节点/边（自管：进撤销历史，替代 vue flow 内置 delete-key-code）
    const selNodes = (getSelectedNodes.value || []) as any[]
    const selEdges = (getSelectedEdges.value || []) as any[]
    if (!selNodes.length && !selEdges.length) return
    e.preventDefault()
    recordHistory()
    const nodeIds = new Set(selNodes.map((n) => n.id))
    const edgeIds = new Set(selEdges.map((e) => e.id))
    nodes.value = nodes.value.filter((n) => !nodeIds.has(n.id))
    edges.value = edges.value.filter((e) => !edgeIds.has(e.id) && !nodeIds.has(e.source) && !nodeIds.has(e.target))
    debouncePersist()
    message.success('已删除所选节点/连线')
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

onConnect(params => {
  recordHistory()
  edges.value = [...edges.value, {
    id: `e${edges.value.length + 1}_${params.source}_${params.target}`,
    source: params.source,
    target: params.target,
    sourceHandle: params.sourceHandle,
    targetHandle: params.targetHandle,
    type: 'smoothstep',
    animated: true,
    class: routeClass(params),
  } as Edge]
  debouncePersist()
})
onNodeDragStop(() => { recordHistory(); debouncePersist() })
onNodeClick(({ node }) => {
  drawerNodeKey.value = node.id
  const rawType = node.data?.stepType || node.data?.type || ''
  const runtime = node.data?.runtime || runtimeForType(rawType)
  drawerNodeType.value = nodeArchetype(rawType || runtime || '')
  drawerNodeRuntime.value = runtime || null
  drawerNodeLabel.value = node.data?.label || null
  drawerConfig.value = (flow.value?.node_configs as Record<string, any> | undefined)?.[node.id] || null
  drawerOpen.value = true
})
onEdgeClick(({ edge }) => {
  recordHistory()
  edges.value = edges.value.filter(e => e.id !== edge.id)
  debouncePersist()
  message.success('已删除连线')
})
function onRemove(nodeKey: string) {
  recordHistory()
  nodes.value = nodes.value.filter(n => n.id !== nodeKey)
  edges.value = edges.value.filter(e => e.source !== nodeKey && e.target !== nodeKey)
  drawerOpen.value = false
  debouncePersist()
  message.success('已删除节点')
}

watch(() => nodes.value.length, () => debouncePersist())
watch(() => edges.value.length, () => debouncePersist())

onMounted(() => { load(); loadReqGroups(); loadManual() })
function onSaved() { load() }

</script>

<template>
  <div class="rf-canvas">
    <div class="rf-toolbar">
      <span class="rf-tip">画布连线（点边删线）· 单击节点开配置 · 右栏试运行验证</span>
      <div class="rf-actions">
        <a-button size="small" :disabled="!undoStack.length" @click="undo" title="撤销（Ctrl+Z）">
          <template #icon><UndoOutlined /></template>撤销
        </a-button>
        <a-button size="small" :disabled="!redoStack.length" @click="redo" title="重做（Ctrl+Shift+Z / Ctrl+Y）">
          <template #icon><RedoOutlined /></template>重做
        </a-button>
        <span v-if="flow" class="rf-version">v{{ flow.version }} · {{ flow.status }}</span>
      </div>
    </div>

    <div class="main-content">
      <!-- 左栏：使用说明——单框单内容（浏览/编辑同一份文本），随会话自动下发大脑 -->
      <aside class="left-panel">
        <div class="lp-block lp-grow">
          <div class="lp-head">
            <span class="lp-title">使用说明<span class="lp-readonly-tag">{{ manualEditing ? '编辑中' : '已生效' }}</span></span>
            <span class="lp-actions">
              <template v-if="manualEditing">
                <a-button size="small" @click="onCancelManualEdit">取消</a-button>
                <a-button size="small" type="primary" :loading="manualSaving" @click="onSaveManualRules">保存</a-button>
              </template>
              <a-button v-else size="small" type="primary" @click="onEditManual">编辑</a-button>
            </span>
          </div>
          <textarea
            v-if="manualEditing"
            v-model="manualRules"
            class="lp-preview lp-editing"
            :rows="16"
            placeholder="编写全程遵循的使用说明。各步骤的工具与产物契约在中间画布的节点抽屉里配置，系统会自动随说明一并发给大脑。"
          />
          <pre v-else class="lp-preview">{{ manualRules || '暂无使用说明，点「编辑」编写。' }}</pre>
          <div class="lp-hint">此规则随每轮会话自动下发大脑；节点抽屉改的工具/契约无需在这里重复维护。</div>
        </div>
      </aside>

      <!-- 中栏：vue flow 画布（编排 + 试运行时节点逐步高亮） -->
      <main class="center-panel">
        <!-- 能力节点图例：连线颜色由节点 kind 派生（智能体 / 规则 / 输出） -->
        <div class="rf-legend">
          <span v-for="r in (['ai','shared'] as const)" :key="r" class="rf-leg-item">
            <i class="rf-leg-dot" :class="ROUTE_META[r].cls"></i>{{ ROUTE_META[r].label }}<span class="rf-leg-sub">{{ ROUTE_META[r].sub }}</span>
          </span>
        </div>
        <a-spin :spinning="loading" class="center-spin">
          <div class="rf-flow-wrap">
            <VueFlow
              v-model:nodes="nodes"
              v-model:edges="edges"
              :node-types="nodeTypes"
              fit-view-on-init
              :min-zoom="0.3"
              :max-zoom="2"
              snap-to-grid
              :snap-grid="[16, 16]"
            >
              <Background :gap="20" :size="1" pattern-color="rgba(127,127,127,0.18)" />
              <Controls />
              <MiniMap pannable zoomable />
            </VueFlow>
            <div v-if="!loading && !nodes.length" class="rf-empty-state">
              <div class="rf-empty-title">画布还是空的</div>
              <p>当前推理流没有节点，请检查 active 版本。</p>
            </div>
          </div>
        </a-spin>
      </main>

      <!-- 右栏：复用真实 AI 角色对话（内嵌·预览·默认支持工程师） -->
      <aside class="right-panel">
        <div class="rp-head">
          <span class="rp-title">试运行</span>
          <a-button size="small" :disabled="running" @click="onResetTest">重置测试</a-button>
        </div>
        <AssistantPanel
          ref="assistantRef"
          embedded
          preview
          entry-point="skill_studio_preview"
          initial-role-key="support_engineer"
          :workflow-key="skillKey"
          :open="true"
        />
      </aside>

    </div>

    <ReasoningNodeDrawer v-model:open="drawerOpen" :node-key="drawerNodeKey" :node-type="drawerNodeType" :node-runtime="drawerNodeRuntime" :node-label="drawerNodeLabel" :initial-config="drawerConfig" :skill-key="skillKey" :skill-output-kind="outputKind" @saved="onSaved" @remove="onRemove" />

    <NodeArtifactModal :bom-scheme="bomScheme" />

    

  </div>
</template>

<style scoped>
.rf-canvas { display: flex; flex-direction: column; gap: 8px; height: 100%; min-height: 0; }
.rf-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0 2px; gap: 12px; }
.rf-tip { font-size: 12px; color: var(--cpq-text-muted); flex: 1; }
.rf-actions { display: flex; align-items: center; gap: 10px; }
.rf-version {
  font-size: 11px; color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-w8); padding: 1px 8px; border-radius: 8px;
  font-variant-numeric: tabular-nums;
}

/* ── 两栏主区（中画布 + 右试运行）── */
.main-content { flex: 1; display: flex; overflow: hidden; min-height: 0; border: 1px solid var(--cpq-overlay-w10); border-radius: var(--cpq-radius-md, 12px); background: var(--cpq-overlay-w3, transparent); }
.left-panel { width: 300px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; padding: 10px; overflow-y: auto; border-right: 1px solid var(--cpq-glass-border); background: var(--cpq-overlay-w3, transparent); }
.lp-block { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.lp-grow { flex: 1; }
.lp-head { display: flex; align-items: center; justify-content: space-between; }
.lp-title { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); }
.lp-actions { display: inline-flex; gap: 6px; }
.lp-readonly-tag { display: inline-block; margin-left: 6px; padding: 0 6px; font-size: 10px; font-weight: 500; border: 1px solid var(--cpq-glass-border); border-radius: 999px; color: var(--cpq-text-secondary); }
.lp-rules { font-size: 12px; line-height: 1.6; resize: vertical; }
.lp-editing { width: 100%; font-family: inherit; }
.lp-hint { font-size: 11px; opacity: 0.6; line-height: 1.5; color: var(--cpq-text-secondary); }
.lp-preview { flex: 1; overflow: auto; margin: 0; padding: 8px; font-size: 11px; line-height: 1.7; white-space: pre-wrap; word-break: break-all; border: 1px solid var(--cpq-glass-border); border-radius: 8px; background: var(--cpq-overlay-w3, transparent); color: var(--cpq-text-secondary); font-family: inherit; }
.center-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
.center-panel :deep(.ant-spin-nested-loading) { flex: 1; display: flex; }
.center-panel :deep(.ant-spin-container) { flex: 1; display: flex; }
.rf-flow-wrap { flex: 1; min-width: 0; min-height: 0; overflow: hidden; position: relative; }
.rf-empty-state {
  position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 6px; pointer-events: none; text-align: center; color: var(--cpq-text-muted);
}
.rf-empty-title { font-size: 16px; font-weight: 600; color: var(--cpq-text-secondary); }
.rf-empty-state p { font-size: 12px; line-height: 1.7; margin: 0; }

/* MiniMap 默认白底（@vue-flow/minimap style.css 写死 #fff），深色模式很突兀；
   用面板背景 token 跟随主题（深色 #101217 / 浅色 #F0F4FA），节点用主色醒目 */
.center-panel :deep(.vue-flow__minimap) { background-color: var(--cpq-bg-secondary); }
/* 边语义标签（缺口/足够/AI 失效→兜底 等）：小字 + 半透明底，避免盖住连线 */
.center-panel :deep(.vue-flow__minimap-node) { fill: var(--cpq-accent-primary, #1677FF); opacity: 0.75; }
/* minimap 视口遮罩默认浅灰 rgba(240,240,240,.6)，深色 minimap 上显白雾 → 深色模式改黑半透 */
[data-theme="dark"] .center-panel :deep(.vue-flow__minimap-mask) { fill: rgba(0, 0, 0, 0.45); }
/* 回溯连线：生成链边高亮（蓝粗），其余变淡 */
/* 双路线连线染色：route 由节点 stepType 派生（运行时算）；定义在 trace 之前以让 trace 高亮优先 */
.center-panel :deep(.rf-edge--ai .vue-flow__edge-path) { stroke: var(--cpq-accent-primary); stroke-width: 2; }
.center-panel :deep(.rf-edge--local .vue-flow__edge-path) { stroke: var(--cpq-accent-warning, #fa8c16); stroke-width: 2; }
.center-panel :deep(.rf-edge--shared .vue-flow__edge-path) { stroke: var(--cpq-text-muted); stroke-width: 1.5; }
/* 双路线图例 */
.rf-legend { display: flex; gap: 14px; padding: 5px 12px; font-size: 12px; color: var(--cpq-text-secondary); border-bottom: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.11)); flex-shrink: 0; }
.rf-leg-item { display: inline-flex; align-items: center; gap: 5px; }
.rf-leg-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.rf-leg-dot.rf-edge--ai { background: var(--cpq-accent-primary); }
.rf-leg-dot.rf-edge--local { background: var(--cpq-accent-warning, #fa8c16); }
.rf-leg-dot.rf-edge--shared { background: var(--cpq-text-muted); }
.rf-leg-sub { color: var(--cpq-text-muted); margin-left: 2px; }
.center-panel :deep(.rf-edge--trace .vue-flow__edge-path) { stroke: var(--cpq-accent-primary); stroke-width: 2.5; }
.center-panel :deep(.rf-edge--dim) { opacity: 0.12; }

/* Controls 按钮组默认白底（#fefefe）+ hover 浅灰，深色突兀；跟随主题 + svg 用主题文字色 */
.center-panel :deep(.vue-flow__controls) { box-shadow: 0 0 2px 1px var(--cpq-overlay-w15, rgba(0, 0, 0, 0.08)); }
.center-panel :deep(.vue-flow__controls-button) {
  background: var(--cpq-bg-secondary);
  border-bottom: 1px solid var(--cpq-overlay-w10);
}
.center-panel :deep(.vue-flow__controls-button:hover) { background: var(--cpq-overlay-a8); }
.center-panel :deep(.vue-flow__controls-button svg) { fill: var(--cpq-text-primary); }
.right-panel { width: 380px; position: relative; background: var(--cpq-overlay-w4); border-left: 1px solid var(--cpq-overlay-w10); display: flex; flex-direction: column; overflow: hidden; border-radius: 0 var(--cpq-radius-md, 12px) var(--cpq-radius-md, 12px) 0; }
.rp-head { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--cpq-overlay-w8); flex-shrink: 0; }
.rp-title { font-size: 12px; font-weight: 600; color: var(--cpq-text-secondary); letter-spacing: 1px; }
.rf-tr-slots { border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-md, 10px); overflow: hidden; }
.rf-tr-slots-head { display: flex; align-items: center; gap: 8px; padding: 8px 10px; font-size: 12px; font-weight: 600; color: var(--cpq-text-primary); border-bottom: 1px solid var(--cpq-glass-border); }
.rf-tr-slots-badge { font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 999px; background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.rf-tr-slots :deep(.req-form) { padding: 10px; }

/* ── 右栏试运行 ── */
.rf-testrun { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.rf-tr-generic { justify-content: center; }
.rf-tr-input { display: flex; flex-direction: column; gap: 8px; }
.rf-tr-input-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rf-tr-textarea { border-radius: var(--cpq-radius-sm, 8px); }
.rf-tr-hint { font-size: 11px; color: var(--cpq-text-muted); }
.rf-tr-opts { justify-content: space-between; }
.rf-tr-ask {
  margin: 8px 0 0; padding: 10px 12px; border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-glass-bg, rgba(255,255,255,0.6));
  border: 1px solid var(--cpq-accent-info, #3b82f6);
}
.rf-tr-ask-q { font-size: 13px; color: var(--cpq-text, #1f2937); line-height: 1.5; }
.rf-tr-ask-opts { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
.rf-tr-ask-opts .ant-btn { font-size: 12px; }
.rf-tr-ask-reply { margin-top: 8px; display: flex; gap: 8px; }
.rf-tr-ask-reply .ant-input { flex: 1; min-width: 0; }
.rf-tr-ask-hint { margin-top: 6px; font-size: 11px; color: var(--cpq-text-muted); }
.rf-tr-error {
  margin: 0; font-size: 12px; color: var(--cpq-accent-danger);
  display: flex; align-items: center; gap: 6px;
}

/* ── 专家分析（问题清单）── */
.rf-tr-issues { margin-top: 6px; padding: 8px 10px; border-radius: 8px; background: var(--cpq-overlay-w6, rgba(120,90,255,.06)); border: 1px solid var(--cpq-overlay-w10, rgba(120,90,255,.18)); }
.rf-tr-issues-title { font-size: 12px; font-weight: 600; color: var(--cpq-accent-primary, #7c6cff); margin-bottom: 6px; }
.rf-tr-issue { padding: 5px 0; border-top: 1px dashed var(--cpq-overlay-w10, rgba(0,0,0,.08)); }
.rf-tr-issue:first-of-type { border-top: none; }
.rf-tr-issue-text { font-size: 13px; color: var(--cpq-text-primary, #1f2329); }
.rf-tr-issue-ev { font-size: 12px; color: var(--cpq-text-muted, #8a919f); margin-top: 2px; }
.rf-tr-issue-sg { font-size: 12px; color: var(--cpq-color-success, #3f9e5f); margin-top: 2px; }

.rf-tr-plan { display: flex; align-items: center; gap: 8px; padding: 8px 12px; margin-bottom: 8px; background: var(--cpq-bg-elevated, #f6f8fa); border-radius: 8px; font-size: 12px; color: var(--cpq-text-secondary, #888); }
.rf-tr-steps { display: flex; flex-direction: column; gap: 6px; }
.rf-tr-step {
  display: flex; gap: 10px; padding: 8px 10px;
  border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w10);
  transition: border-color var(--cpq-transition-fast);
}
.rf-tr-step.is-done { cursor: pointer; }
.rf-tr-step:hover { border-color: var(--cpq-glass-border-strong); }
.rf-tr-dot {
  width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; flex-shrink: 0;
  background: var(--cpq-overlay-w15);
}
.rf-tr-step.is-running .rf-tr-dot { background: var(--cpq-accent-primary); animation: rf-tr-pulse 1s infinite; }
.rf-tr-step.is-done .rf-tr-dot { background: var(--cpq-color-success); }
.rf-tr-step.is-error .rf-tr-dot { background: var(--cpq-accent-danger); }
@keyframes rf-tr-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.rf-tr-step-body { flex: 1; min-width: 0; }
.rf-tr-step-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rf-tr-step-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.rf-tr-step-status { font-size: 11px; color: var(--cpq-text-muted); }
.rf-tr-step.is-running .rf-tr-step-status { color: var(--cpq-accent-primary); }
.rf-tr-step.is-done .rf-tr-step-status { color: var(--cpq-color-success); }
.rf-tr-step-summary { margin: 3px 0 0; font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.5; }
.rf-tr-substeps { margin: 4px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 2px; }
.rf-tr-substeps li { font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.5; padding-left: 12px; position: relative; }
.rf-tr-substeps li::before { content: '·'; position: absolute; left: 2px; color: var(--cpq-text-muted); }
.rf-tr-substeps li.rf-tr-sub--understood { color: var(--cpq-color-success); }

.rf-tr-detail {
  margin-top: 8px; padding-top: 8px;
  border-top: 1px dashed var(--cpq-overlay-w10);
  display: flex; flex-direction: column; gap: 4px;
}
/* 变量流转 IO 展示（输入←上游 / 输出→下游） */
.rf-tr-io { display: flex; flex-direction: column; gap: 3px; margin-bottom: 6px; padding: 5px 8px; background: var(--cpq-overlay-w4); border-radius: 6px; }
.rf-tr-io-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; }
.rf-tr-io-tag { font-size: 10px; font-weight: 600; color: var(--cpq-text-muted); flex-shrink: 0; }
.rf-tr-io-var { font-size: 10px; padding: 1px 5px; border-radius: 4px; font-family: ui-monospace, monospace; word-break: break-all; }
.rf-tr-io-var.in { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.rf-tr-io-var.out { background: rgba(82, 201, 160, 0.15); color: var(--cpq-color-success); }
.rf-tr-io-var small { font-family: inherit; opacity: 0.7; font-size: 9px; }
.rf-tr-kv { font-size: 12px; color: var(--cpq-text-secondary); display: flex; gap: 8px; }
.rf-tr-kv span { color: var(--cpq-text-muted); min-width: 56px; }
.rf-tr-kv b { font-weight: 500; }
.rf-tr-model { padding: 4px 0; }
.rf-tr-model-name { font-size: 12px; font-weight: 600; color: var(--cpq-accent-primary); margin-bottom: 3px; }
.rf-tr-kp {
  display: grid; grid-template-columns: 80px 1fr 32px 72px; gap: 6px;
  font-size: 11px; padding: 2px 0; color: var(--cpq-text-secondary); align-items: baseline;
}
.rf-tr-kp.unmatched { color: var(--cpq-accent-danger); }
.rf-tr-kp-pn { font-family: ui-monospace, monospace; word-break: break-all; }
.rf-tr-kp-price { font-variant-numeric: tabular-nums; text-align: right; }
.rf-tr-kp-spec { grid-column: 1 / -1; font-size: 10px; color: var(--cpq-text-muted); }
.rf-tr-raw {
  margin: 0; font-size: 11px; white-space: pre-wrap; word-break: break-all;
  color: var(--cpq-text-muted); font-family: ui-monospace, monospace;
}

.rf-tr-artifact { margin-top: 8px; }
.rf-tr-trace-hint { font-size: 11px; color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); padding: 6px 10px; border-radius: 6px; }
.rf-tr-empty { font-size: 12px; color: var(--cpq-text-muted); text-align: center; padding: 12px 0; margin: 0; }

/* ── 产出物仪表盘（右栏瘦身后）── */
.rf-artifacts { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 12px; }
.rf-art-card { background: var(--cpq-bg-card, #ffffff); border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.14)); border-radius: var(--cpq-radius-md, 10px); overflow: hidden; }
.rf-art-slots { border-color: rgba(79,140,255,.5); }
.rf-art-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px 8px; font-size: 13px; }
.rf-art-name { font-weight: 600; color: var(--cpq-text-primary); }
.rf-art-badge { margin-left: auto; font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 999px; }
.rf-art-badge.fill { background: rgba(79,140,255,.16); color: #4f8cff; }
.rf-art-badge.done { background: rgba(63,191,143,.16); color: #3fbf8f; }
.rf-art-badge.idle { background: rgba(128,128,128,.14); color: var(--cpq-text-muted); }
.rf-art-card--idle { border-style: dashed; border-color: rgba(128,128,128,.28); }
.rf-art-prog { padding: 0 12px 10px; }
.rf-art-prog-row { display: flex; justify-content: space-between; font-size: 12px; color: var(--cpq-text-secondary); }
.rf-art-bar { height: 5px; border-radius: 3px; background: rgba(128,128,128,.18); margin-top: 6px; overflow: hidden; }
.rf-art-bar i { display: block; height: 100%; border-radius: 3px; background: #4f8cff; transition: width .3s; }
.rf-art-fields { max-height: 210px; overflow-y: auto; border-top: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.12)); padding: 6px 12px 10px; scroll-behavior: smooth; }
.rf-art-fields--idle { opacity: .62; }
.rf-art-fields-hint { margin: 0 0 4px; font-size: 11px; color: var(--cpq-text-muted); }
.rf-fg { margin-top: 8px; }
.rf-fg-title { font-size: 11px; color: var(--cpq-text-muted); letter-spacing: .04em; margin-bottom: 4px; }
.rf-fld { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--cpq-text-secondary); padding: 3px 0; }
.rf-fld--ask { color: var(--cpq-text-primary); }
.rf-fld-dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px; }
.rf-fld-dot--filled { background: #3fbf8f; }
.rf-fld-dot--optional { background: #a0a6b1; }
.rf-fld-dot--asked { background: #a855f7; box-shadow: 0 0 0 3px rgba(168,85,247,.18); }
.rf-fld-lb { flex: 1; }
.rf-fld-st { font-size: 11px; }
.rf-fld-st--filled { color: #3fbf8f; }
.rf-fld-st--optional { color: var(--cpq-text-muted); }
.rf-fld-st--asked { color: #a855f7; }
.rf-art-follow { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: #4f8cff; margin-top: 6px; }
.rf-art-follow-car { animation: rfFollow 1.2s ease-in-out infinite; }
@keyframes rfFollow { 0%,100% { transform: translateY(0); } 50% { transform: translateY(2px); } }
.rf-art-bom-chips { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 12px 10px; font-size: 11px; color: var(--cpq-text-secondary); }
.rf-art-bom-chips span { background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.12)); padding: 2px 7px; border-radius: 6px; }
.rf-art-bom-chips .rf-art-chip-idle { color: var(--cpq-text-muted); border-style: dashed; }
.rf-art-foot { padding: 10px 12px; display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.12)); }
.rf-art-dim { font-size: 11px; color: var(--cpq-text-muted); }
.rf-art-view { font-size: 12px; color: var(--cpq-accent-primary); cursor: pointer; }
.rf-art-view.is-disabled { color: var(--cpq-text-muted); cursor: default; opacity: .6; }
.rf-art-warn { margin: 0; padding: 7px 11px; font-size: 11px; line-height: 1.5; color: #d97706; background: rgba(217,119,6,.1); border-radius: 8px; }
.rf-tr-slots-badge.done { background: var(--cpq-overlay-success15); color: var(--cpq-color-success, #52C9A0); }

/* ── 右栏「对话」面板（真实用户 ↔ AI 角色）── */
.rf-chat { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 12px; scroll-behavior: smooth; }
.rf-chat-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--cpq-text-muted); text-align: center; padding: 24px 18px; }
.rf-chat-empty-ic { font-size: 24px; }
.rf-chat-empty p { margin: 0; font-size: 12px; line-height: 1.7; }
.rf-msg { display: flex; gap: 8px; align-items: flex-start; }
.rf-msg--user { flex-direction: row-reverse; }
.rf-msg-avatar { flex: 0 0 30px; width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; font-size: 11px; font-weight: 600; background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-overlay-w10); color: var(--cpq-text-secondary); }
.rf-msg--user .rf-msg-avatar { background: rgba(79,140,255,.18); color: #4f8cff; border-color: rgba(79,140,255,.4); }
.rf-msg--ai .rf-msg-avatar { background: rgba(168,85,247,.18); color: #a855f7; border-color: rgba(168,85,247,.4); }
.rf-msg-bubble { max-width: 78%; background: var(--cpq-bg-card, #ffffff); border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.14)); border-radius: 12px; padding: 8px 11px; font-size: 13px; color: var(--cpq-text-primary); }
.rf-msg--user .rf-msg-bubble { background: rgba(79,140,255,.14); border-color: rgba(79,140,255,.3); }
.rf-msg-bubble--art { padding: 6px; }
.rf-chat-q { color: #a855f7; font-weight: 600; }
.rf-chat-opts { display: flex; gap: 6px; margin-top: 7px; flex-wrap: wrap; }
.rf-chat-opts span { font-size: 11px; color: var(--cpq-text-secondary); border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.16)); border-radius: 14px; padding: 2px 9px; cursor: pointer; background: var(--cpq-overlay-w4); }
.rf-chat-opts span:hover { color: #4f8cff; border-color: rgba(79,140,255,.5); }
.rf-chat-input { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--cpq-overlay-w10); }
.rf-chat-input input { flex: 1; min-width: 0; background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.14)); border-radius: 10px; color: var(--cpq-text-primary); font-size: 13px; padding: 7px 11px; outline: none; }
.rf-chat-input input:focus { border-color: rgba(79,140,255,.5); }
.rf-chat-input button { flex: 0 0 auto; background: #4f8cff; color: #fff; border: none; border-radius: 10px; font-size: 12px; font-weight: 600; padding: 0 14px; cursor: pointer; }
.rf-chat-input button:disabled { background: var(--cpq-overlay-w6); color: var(--cpq-text-muted); cursor: not-allowed; }
.rf-chat-note { padding: 8px 14px; border-top: 1px solid var(--cpq-overlay-w10); font-size: 11px; color: var(--cpq-text-muted); text-align: center; }

.rf-llm-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.rf-llm-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.rf-llm-type { font-size: 10px; color: var(--cpq-text-muted); font-family: ui-monospace, monospace; }
.rf-llm-actions { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.rf-llm-hint { font-size: 11px; color: var(--cpq-text-muted); }


</style>
