<script setup lang="ts">
/**
 * 商机全生命周期流程看板（统一详情页中栏）。
 * 左栏：可点击流程时间线；中栏：每个节点一张工作卡；右栏：审批人/审批状态。
 * 需求单提交后进入 BOM 节点；BOM/成本/报价完成后由 board 接口自动带出到对应卡片。
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch, defineAsyncComponent } from 'vue'
import { message, Modal } from 'ant-design-vue'
import axios from 'axios'
import {
  CheckCircleFilled,
  IdcardOutlined,
  FileTextOutlined,
  ToolOutlined,
  CalculatorOutlined,
  UpOutlined,
  LeftOutlined,
  MenuOutlined,
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { portalApi } from '@/api/portal'
import { projectApi } from '@/api'
import type { FlowCard, PortalBoard, RequirementVersion, RequirementSlots } from '@/api/portal'
import type { Quotation } from '@/types/opportunity'
import type { FeedAttachment } from '@/api/feed'
import type { ProcessNodeDef } from '@/types/flow'
import RecordTable from '@/components/opportunity/RecordTable.vue'
// 弹窗为按需打开，懒加载避免进入详情页首屏就拉取该组件
const AssigneePickerModal = defineAsyncComponent(() => import('@/components/opportunity/AssigneePickerModal.vue'))
import { useDownstreamAssignee, ASSIGNEE_REQUIRED_DETAIL } from '@/composables/useDownstreamAssignee'
import { useAuthStore } from '@/store/auth'

const RequirementForm = defineAsyncComponent(() => import('@/components/flow/RequirementForm.vue'))
const ArchiveSection = defineAsyncComponent(() => import('@/components/opportunity/ArchiveSection.vue'))
const AttachmentUploadButton = defineAsyncComponent(() => import('@/components/opportunity/AttachmentUploadButton.vue'))
const BomSchemeWorkbench = defineAsyncComponent(() => import('@/components/opportunity/BomSchemeWorkbench.vue'))
const CostSheetWorkbench = defineAsyncComponent(() => import('@/components/opportunity/CostSheetWorkbench.vue'))
const QuoteWorkbench = defineAsyncComponent(() => import('@/components/opportunity/QuoteWorkbench.vue'))
const ApprovalFlowPanel = defineAsyncComponent(() => import('@/components/opportunity/ApprovalFlowPanel.vue'))
const OpportunityProcessRail = defineAsyncComponent(() => import('@/components/opportunity/OpportunityProcessRail.vue'))

interface RequirementFormExpose {
  toSlots(): RequirementSlots
  fromSlots(slots: RequirementSlots): void
  hasAnyPart: boolean
}

const props = defineProps<{
  opportunityId: string
  updatedAt?: string
  legacyRequirementText?: string
  attachments?: FeedAttachment[]
  quotations?: Quotation[]
  quotePriceVisible?: boolean
  quoteSelectMode?: boolean
  quoteSelectedIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'new-quotation'): void
  (e: 'upload-cost-sheet'): void
  (e: 'view-quotation', quotation: Quotation): void
  (e: 'unfreeze-quotation', quotation: Quotation): void
  (e: 'set-primary', quotation: Quotation): void
  (e: 'rename-quotation', quotation: Quotation): void
  (e: 'delete-quotation', quotationId: string): void
  (e: 'toggle-quote-select', quotationId: string): void
  (e: 'enter-quote-batch'): void
  (e: 'exit-quote-batch'): void
  (e: 'batch-delete-quotes'): void
  (e: 'preview-attachment', attachment: FeedAttachment): void
  (e: 'delete-attachment', attachment: FeedAttachment): void
  (e: 'refresh-meta'): void
  (e: 'refresh-quotations'): void
  /** 看板首次加载完成（成功或失败），通知父级收起全局骨架 */
  (e: 'board-settled'): void
}>()
const oppId = props.opportunityId
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.can('page.opportunities_all'))
const {
  pickerOpen, pickerTitle, pickerOptions, pickerChosen,
  promptAssignee, confirmPicker, cancelPicker,
} = useDownstreamAssignee()

const PROCESS_NODES = [
  { key: 'requirement', label: '业务', title: '线索登记', subtitle: '填写需求单并提交' },
  { key: 'boming', label: '技术支持', title: '方案配置', subtitle: '上传Excel/附件' },
  { key: 'costing', label: '成本核算', title: '成本核算', subtitle: '核价后生成' },
  { key: 'quoting', label: '市场报价', title: '报价单', subtitle: '报价定稿' },
] as const

const loading = ref(false)
const boardLoadError = ref('')
let boardLoadSeq = 0
const submitting = ref(false)
const editing = ref(false)
const draftSaving = ref(false)
const deletingDraft = ref(false)
const activeRequirementVersion = ref<number | null>(null)
const activeNode = ref<string>('requirement')
// 中栏工作卡默认折叠：只展开「当前待办」的卡，其余收起
type CardKey = 'reqInfo' | 'requirement' | 'boming' | 'costing' | 'quoteUpstream' | 'quoteEditor'
const cardOpen = reactive<Record<CardKey, boolean>>({
  reqInfo: false,
  requirement: false,
  boming: false,
  costing: false,
  quoteUpstream: false,
  quoteEditor: false,
})
const cardTouchedByUser = new Set<CardKey>()
function toggleCard(key: CardKey) {
  cardOpen[key] = !cardOpen[key]
  cardTouchedByUser.add(key)
}
// 供受控子组件（QuoteWorkbench 面板）回写折叠态，同样视为用户已手动操作
function setCardOpen(key: CardKey, value: boolean) {
  cardOpen[key] = value
  cardTouchedByUser.add(key)
}

// 左栏折叠：宽屏下的用户偏好（窄屏由 CSS 强制展开）
const railCollapsedKey = 'cpq:opportunity:rail-collapsed'
function readRailCollapsed() {
  try {
    return localStorage.getItem(railCollapsedKey) === '1'
  } catch {
    return false
  }
}
const railCollapsed = ref(readRailCollapsed())

// ── 手机端（≤768）：三栏 → 双抽屉。左抽屉=流程轨道（切节点导航），右抽屉=协作与动态，
//     工作台独占全屏；桌面三栏不受影响 ──
const isMobile = ref(false)
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null
const openDrawer = ref<null | 'rail' | 'dyn'>(null)
const railDrawerOpen = computed({
  get: () => openDrawer.value === 'rail',
  set: (v: boolean) => { openDrawer.value = v ? 'rail' : null },
})
const dynDrawerOpen = computed({
  get: () => openDrawer.value === 'dyn',
  set: (v: boolean) => { openDrawer.value = v ? 'dyn' : null },
})
// 抽屉内选节点：收抽屉 + 走现有滚动定位链路
function selectFromDrawer(key: string) {
  openDrawer.value = null
  scrollToNode(key)
}
function selectSubFromDrawer(key: string, index: number) {
  openDrawer.value = null
  scrollToSubstep(key, index)
}
// 阶段工具条：四步迷你进度（done/current 判定与 Rail 同源：approvals.state + flow.current_node）
const stageSteps = computed(() =>
  PROCESS_NODES.map((n, i) => ({
    key: n.key,
    short: ['业务', '技术', '成本', '报价'][i],
    state: nodeIsDone(n.key) ? 'done' : currentFlowNode.value === n.key ? 'cur' : 'todo',
  })),
)
// 动态未读：该商机未读通知数（notifications 表自带 opportunity_id；只读统计，不代用户标记已读）
const dynUnread = ref(0)
async function loadDynUnread() {
  try {
    const res = await axios.get('/api/notifications', { params: { unread_only: true, page_size: 100 } })
    const items: any[] = res.data?.notifications || []
    dynUnread.value = items.filter((n) => (n?.opportunity_id ?? n?.payload?.opportunity_id) === oppId).length
  } catch { /* 静默降级：红点不显示 */ }
}
watch(openDrawer, (v) => { if (v === 'dyn') loadDynUnread() })

onMounted(() => {
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
  const mq = window.matchMedia('(max-width: 768px)')
  _mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', _mqListener)
  loadDynUnread()
})
onBeforeUnmount(() => {
  if (_mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', _mqListener)
})
function toggleRail() {
  railCollapsed.value = !railCollapsed.value
  try {
    localStorage.setItem(railCollapsedKey, railCollapsed.value ? '1' : '0')
  } catch {
    /* ignore storage errors */
  }
}
const activeNodeKey = 'cpq:opportunity:active-node:' + oppId
let nodeInitialized = false
watch(activeNode, (node) => {
  try {
    sessionStorage.setItem(activeNodeKey, node)
  } catch {
    /* ignore storage errors */
  }
  applyCardDefaults(node)
})
const detailOpen = ref(false)
const detailKey = ref<string>('')
const board = ref<PortalBoard | null>(null)
const reqText = ref('')
const formRef = ref<RequirementFormExpose | null>(null)
const pendingRequirementSlots = ref<RequirementSlots | null>(null)

function setRequirementSlots(slots: RequirementSlots) {
  pendingRequirementSlots.value = slots || {}
  nextTick(() => {
    const pending = pendingRequirementSlots.value
    if (!formRef.value || !pending) return
    formRef.value.fromSlots(pending)
    pendingRequirementSlots.value = null
  })
}

watch(formRef, (form) => {
  if (form && pendingRequirementSlots.value) {
    form.fromSlots(pendingRequirementSlots.value)
    pendingRequirementSlots.value = null
  }
})
const basicEditing = ref(false)
const basicSaving = ref(false)
const fieldHistory = ref<Record<string, string[]>>({})
const businessOptions = ref<{ value: string; label: string }[]>([])
// 商机级角色字段锁定：对应角色登录时该字段强制为当前登录人，不可修改。
const roleLock = computed<Record<string, string>>(() => {
  const role = auth.user?.role
  const name = auth.user?.name || ''
  const map: Record<string, string> = {}
  if (role === 'business') map.sales_person = name
  else if (role === 'te') map.fae = name
  else if (role === 'quote') map.quotation_person = name
  return map
})
const basicForm = reactive({
  customer_name: '',
  sales_person: '',
  fae: '',
  quotation_person: '',
  industry: '',
  delivery_region: '',
  delivery_cycle: '',
  order_type: '',
})

const opp = computed(() => board.value?.opportunity || null)
const approvals = computed(() => board.value?.approvals || [])
const requirements = computed(() => board.value?.requirements || [])
const currentReq = computed(() => board.value?.requirement || null)
const flowCards = computed(() => board.value?.flow_cards || [])
const draftReq = computed(
  () => board.value?.draft_requirement || requirements.value.find((r) => r.status === 'draft') || null,
)
function normalizeFlowNode(raw?: string) {
  return !raw || raw === 'assign' ? 'requirement' : raw
}
function displayReqText(text?: string | null) {
  return text || props.legacyRequirementText || ''
}
const currentFlowNode = computed(() => {
  return normalizeFlowNode(board.value?.flow?.current_node)
})
function cardFor(type: FlowCard['entities'][number]['entity_type'], entityId: number | string | null | undefined): FlowCard | undefined {
  if (entityId === null || entityId === undefined || entityId === '') return undefined
  return flowCards.value.find((card) => card.entities.some((e) => e.entity_type === type && e.entity_id === String(entityId)))
}
function upsertFlowCard(card: FlowCard) {
  if (!board.value) return
  const cards = [...(board.value.flow_cards || [])]
  const index = cards.findIndex((item) => item.id === card.id)
  if (index >= 0) cards[index] = card
  else cards.unshift(card)
  board.value = { ...board.value, flow_cards: cards }
}
const selectedRequirement = computed(() => {
  if (activeRequirementVersion.value) {
    return requirements.value.find((r) => r.version === activeRequirementVersion.value) || null
  }
  return currentReq.value
})
const infoRows = computed(() => {
  const o = opp.value
  if (!o) return []
  return [
    ['业务', o.sales_person || '—'],
    ['客户名称', o.customer_name || '—'],
    ['FAE', o.fae || '—'],
    ['报价人', o.quotation_person || '—'],
    ['行业', o.industry || '—'],
    ['交付地区', o.delivery_region || '—'],
    ['交付周期', o.delivery_cycle || '—'],
    ['订单类型', o.order_type || '—'],
  ]
})

const processNodes = computed<ProcessNodeDef[]>(() =>
  PROCESS_NODES.map((node) => {
    const ap = approvals.value.find((a) => a.key === node.key)
    return {
      key: node.key,
      label: node.label,
      title: node.title,
      subtitle: node.subtitle,
      state: ap?.state || 'pending',
      statusLabel: ap?.status_label || '待处理',
    }
  }),
)

// 左栏底部信息区
const railOwnerRows = computed(() => {
  const o = opp.value
  if (!o) return []
  return [
    { label: '业务', value: o.sales_person || '—' },
    { label: 'FAE', value: o.fae || '—' },
    { label: '报价人', value: o.quotation_person || '—' },
  ]
})

const railUpdatedText = computed(() => {
  const ts = props.updatedAt
  return ts ? dayjs(ts).format('MM-DD HH:mm') : ''
})

function nodeIsDone(key: string) {
  return approvals.value.find((a) => a.key === key)?.state === 'done'
}

// 子步骤完成标记：需求阶段按数据判断，其余阶段跟随节点状态
const subDoneMap = computed<Record<string, boolean[]>>(() => ({
  requirement: [!!opp.value?.customer_name, !!currentReq.value],
  boming: [nodeIsDone('boming'), nodeIsDone('boming')],
  costing: [nodeIsDone('costing'), nodeIsDone('costing')],
  quoting: [nodeIsDone('quoting'), nodeIsDone('quoting')],
}))

// 中栏默认只展开当前待办卡；用户手动折叠过的卡不再被重置
function applyCardDefaults(nodeKey: string) {
  const next: Partial<Record<CardKey, boolean>> = {}
  if (nodeKey === 'requirement') {
    if (!opp.value?.customer_name) {
      next.reqInfo = true
      next.requirement = false
    } else if (!currentReq.value) {
      next.reqInfo = false
      next.requirement = true
    } else {
      next.reqInfo = false
      next.requirement = false
    }
  } else if (nodeKey === 'boming') {
    next.boming = !nodeIsDone('boming')
  } else if (nodeKey === 'costing') {
    next.costing = !nodeIsDone('costing')
  } else if (nodeKey === 'quoting') {
    // 报价单节点：上游成本摘要 + 报价单工作区两面板同规则（未完成→展开，已完成→收起）
    const open = !nodeIsDone('quoting')
    next.quoteUpstream = open
    next.quoteEditor = open
  }
  for (const key of Object.keys(next) as CardKey[]) {
    if (!cardTouchedByUser.has(key)) cardOpen[key] = next[key] as boolean
  }
}

const stepperNodes = computed(() =>
  processNodes.value.map((node) => {
    const isDone = node.state === 'done'
    const isCurrent = node.key === activeNode.value
    let subtitle = '待处理'
    if (node.key === 'requirement') {
      const version = currentReq.value?.version
      subtitle = version ? `需求单 v${version} · ${isDone ? '已完成' : node.statusLabel}` : node.statusLabel
    } else if (isDone || isCurrent) {
      subtitle = `${node.label} · ${node.statusLabel}`
    }
    return { ...node, subtitle }
  }),
)

const bomLocked = computed(() => board.value?.bom?.locked ?? true)
const costLocked = computed(() => board.value?.cost?.locked ?? true)
const canWriteRequirement = computed(() => auth.can('action.flow.submit.requirement'))
const canWriteBom = computed(() => auth.can('action.flow.submit.boming'))
const canWriteCost = computed(() => auth.can('action.flow.submit.costing'))
// 卡头的「新建方案/新建成本表」按钮经 expose 远调工作区（编辑器状态在工作区内部）
interface WorkbenchExpose { openNew(): void }
const bomWorkbenchRef = ref<WorkbenchExpose | null>(null)
const costWorkbenchRef = ref<WorkbenchExpose | null>(null)
const bomSchemes = computed(() => board.value?.bom_schemes || [])
const costSheets = computed(() => board.value?.cost_sheets || [])
const NODE_ORDER = ['requirement', 'boming', 'costing', 'quoting'] as const
const currentFlowIndex = computed(() => {
  const index = NODE_ORDER.indexOf(currentFlowNode.value as (typeof NODE_ORDER)[number])
  return index < 0 ? 0 : index
})
const lockedNodeKeys = computed(() => new Set((board.value?.nodes || []).filter((n) => n.locked).map((n) => n.node_key)))
const disabledNodeKeys = computed(() => [...new Set(PROCESS_NODES.filter((n) => nodeDisabled(n.key)).map((n) => n.key))] as string[])
function nodeReached(key: string) {
  const index = NODE_ORDER.indexOf(key as (typeof NODE_ORDER)[number])
  return index >= 0 && index <= currentFlowIndex.value
}
function nodePermissionDenied(key: string) {
  return lockedNodeKeys.value.has(key)
}
function nodeDisabled(key: string) {
  return !isAdmin.value && nodePermissionDenied(key)
}
const activeNodeEmptyText = computed(() => {
  const key = activeNode.value
  if (!nodeReached(key)) return '等待上游提交'
  if (nodePermissionDenied(key)) return '当前角色无权查看该节点工作区'
  if (key === 'boming') return '暂无方案数据'
  if (key === 'costing') return '暂无成本数据'
  return '暂无数据'
})
function applyRoleLock() {
  for (const [k, v] of Object.entries(roleLock.value)) {
    ;(basicForm as any)[k] = v || ''
  }
}

async function fillAssignedRoles() {
  if (auth.user?.role !== 'business') return
  const uid = auth.user?.user_id
  if (!uid) return
  try {
    const res = await portalApi.assignmentRules(uid)
    const rules = (res.rules || [])
    const boming = rules.find((r) => r.node_key === 'boming')?.assignee_name || ''
    const quoting = rules.find((r) => r.node_key === 'quoting')?.assignee_name || ''
    if (!basicForm.fae && boming) basicForm.fae = boming
    if (!basicForm.quotation_person && quoting) basicForm.quotation_person = quoting
  } catch {
    /* ignore */
  }
}

function syncBasicForm() {
  const o = board.value?.opportunity
  if (!o) return
  basicForm.customer_name = o.customer_name || ''
  basicForm.sales_person = o.sales_person || ''
  basicForm.fae = o.fae || ''
  basicForm.quotation_person = o.quotation_person || ''
  basicForm.industry = o.industry || ''
  basicForm.delivery_region = o.delivery_region || ''
  basicForm.delivery_cycle = o.delivery_cycle || ''
  basicForm.order_type = o.order_type || ''
  applyRoleLock()
  void fillAssignedRoles()
}

async function loadFieldHistory(fieldKey: string) {
  if (fieldHistory.value[fieldKey]) return
  try {
    fieldHistory.value[fieldKey] = await projectApi.fieldHistory(fieldKey)
  } catch (err) {
    console.error('加载字段历史失败:', err)
    fieldHistory.value[fieldKey] = []
  }
}

async function loadBusinessOptions() {
  if (!isAdmin.value) return
  if (businessOptions.value.length) return
  try {
    businessOptions.value = (await projectApi.businessOptions()).map((u: any) => ({
      value: u.name,
      label: u.name,
    }))
  } catch (err) {
    console.error('加载业务账户失败:', err)
    businessOptions.value = []
  }
}

function filterBusinessOption(input: string, option: any) {
  return String(option?.value || '').toLowerCase().includes(String(input || '').toLowerCase())
}

function getFilteredOptions(fieldKey: string) {
  const history = fieldHistory.value[fieldKey] || []
  const keyword = ((basicForm as any)[fieldKey]?.toString() || '').toLowerCase()
  const filtered = keyword
    ? history.filter(v => v.toLowerCase().includes(keyword))
    : history
  return filtered.map(v => ({ value: v, label: v }))
}


function basicPayload() {
  return {
    customer_name: basicForm.customer_name.trim(),
    sales_person: basicForm.sales_person.trim(),
    fae: basicForm.fae.trim(),
    quotation_person: basicForm.quotation_person.trim(),
    industry: basicForm.industry.trim(),
    delivery_region: basicForm.delivery_region.trim(),
    delivery_cycle: basicForm.delivery_cycle.trim(),
    order_type: basicForm.order_type.trim(),
  }
}

function startBasicEdit() {
  syncBasicForm()
  // 编辑表单渲染在折叠区内：点编辑即展开，否则看不见表单
  setCardOpen('reqInfo', true)
  basicEditing.value = true
}

function cancelBasicEdit() {
  basicEditing.value = false
}

async function saveBasic() {
  if (!basicForm.customer_name.trim()) {
    message.warning('请填写客户名称')
    return
  }
  basicSaving.value = true
  try {
    await projectApi.update(oppId, basicPayload())
    message.success('商机基本信息已保存')
    basicEditing.value = false
    await loadBoard()
    emit('refresh-meta')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    basicSaving.value = false
  }
}

async function handleQuoteRefresh() {
  await loadBoard()
  emit('refresh-quotations')
}

async function loadBoard() {
  const requestSeq = ++boardLoadSeq
  loading.value = true
  boardLoadError.value = ''
  try {
    const res = await portalApi.board(oppId)
    if (requestSeq !== boardLoadSeq) return
    board.value = res
    syncBasicForm()
    activeRequirementVersion.value = null
    reqText.value = displayReqText(res.requirement?.requirement_text)
    if (!nodeInitialized) {
      let saved = ''
      try { saved = sessionStorage.getItem(activeNodeKey) || '' } catch { saved = '' }
      activeNode.value = saved && PROCESS_NODES.some((n) => n.key === saved) ? saved : normalizeFlowNode(res.flow?.current_node)
      nodeInitialized = true
    }
    applyCardDefaults(activeNode.value)
    if (res.requirement) {
      setRequirementSlots(res.requirement?.slots || {})
    }
  } catch (e: any) {
    if (requestSeq === boardLoadSeq) {
      boardLoadError.value = e.response?.data?.detail || '加载商机详情失败'
      message.error(e.response?.data?.detail || '加载商机详情失败')
    }
  } finally {
    if (requestSeq === boardLoadSeq) {
      loading.value = false
      emit('board-settled')
    }
  }
}

function scrollToNode(key: string) {
  const sameNode = activeNode.value === key
  activeNode.value = key
  const doScroll = () => {
    document.querySelector('.process-workbench')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  nextTick(() => {
    if (sameNode) doScroll()
    else setTimeout(doScroll, 200)
  })
}

// 小节点 → 中栏实体映射：第一段=工作卡，第二段=附件抽屉（与卡内「XX附件」按钮同源）
const SUBSTEP_CARDS: Record<string, CardKey> = {
  'requirement.0': 'reqInfo',
  'requirement.1': 'requirement',
  'boming.0': 'boming',
  'boming.1': 'boming',
  'costing.0': 'costing',
  'costing.1': 'costing',
  'quoting.0': 'quoteEditor',
  'quoting.1': 'quoteEditor',
}
const SUBSTEP_ARCHIVES: Record<string, { categories: string[]; title: string }> = {
  'boming.1': { categories: ['technical'], title: '方案附件' },
  'costing.1': { categories: ['requirement'], title: '成本附件' },
  'quoting.1': { categories: ['sent_quote'], title: '报价附件' },
}
function scrollToSubstep(key: string, index: number) {
  const sameNode = activeNode.value === key
  const anchor = `${key}.${index}`
  // 点小节点先展开对应工作卡（并记为用户已操作，避免 applyCardDefaults 折回去）
  const cardKey = SUBSTEP_CARDS[anchor]
  if (cardKey && !cardOpen[cardKey]) setCardOpen(cardKey, true)
  // 附件类小节点：展开卡后直接打开对应附件抽屉
  const archive = SUBSTEP_ARCHIVES[anchor]
  if (archive) openArchive(archive.categories, archive.title)
  activeNode.value = key
  const doScroll = () => {
    const target = document.querySelector(`[data-substep~="${anchor}"]`)
    const el = target || document.querySelector('.process-workbench')
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  nextTick(() => {
    if (sameNode) doScroll()
    else setTimeout(doScroll, 200)
  })
}

function startEditDraft() {
  editing.value = true
  activeRequirementVersion.value = null
  detailKey.value = 'requirement'
  detailOpen.value = true
  reqText.value = displayReqText(draftReq.value?.requirement_text)
  setRequirementSlots(draftReq.value?.slots || {})
}

function startNewDraft() {
  editing.value = true
  activeRequirementVersion.value = null
  detailKey.value = 'requirement'
  detailOpen.value = true
  reqText.value = displayReqText(null)
  setRequirementSlots({})
}

async function deleteDraft(version: number) {
  Modal.confirm({
    title: `确认删除需求草稿 v${version}？`,
    content: '删除后不可恢复。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      deletingDraft.value = true
      try {
        await portalApi.deleteRequirementDraft(oppId, version)
        message.success('草稿已删除')
        if (activeRequirementVersion.value === version) {
          activeRequirementVersion.value = null
          editing.value = false
        }
        await loadBoard()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除草稿失败')
      } finally {
        deletingDraft.value = false
      }
    },
  })
}

function cardForRequirement(req: RequirementVersion) {
  return cardFor('requirement', req.version)
}

const CARD_NODE_LABELS: Record<string, string> = {
  requirement: '线索登记',
  boming: '方案配置',
  costing: '成本核算',
  quoting: '报价单',
}
const CARD_FLOW_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  submitted: '待处理',
  processing: '处理中',
  returned: '已退回',
  withdraw_requested: '申请撤回中',
  withdrawn: '已撤回',
  completed: '报价单已出',
}

function requirementCardStatus(req: RequirementVersion): string {
  const card = cardForRequirement(req)
  if (!card) return '已发起'
  if (card.flow_status === 'draft' || card.current_node === 'requirement') return '线索登记 · 已发起'
  return `${CARD_NODE_LABELS[card.current_node] || card.current_node} · ${CARD_FLOW_STATUS_LABELS[card.flow_status] || card.flow_status}`
}

function requestWithdrawRequirement(req: RequirementVersion) {
  const card = cardForRequirement(req)
  if (!card) return
  Modal.confirm({
    title: `申请撤回需求单 v${req.version}？`,
    content: '仅当下游尚未保存、评论、传附件或继续流转时才能撤回。',
    okText: '申请撤回',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await portalApi.requestWithdrawCard(oppId, card.id)
        message.success('撤回申请已提交')
        upsertFlowCard(res.card)
      } catch (e: any) {
        message.error(e.response?.data?.detail || '撤回申请失败')
      }
    },
  })
}

function showRequirement(version: number) {
  const req = requirements.value.find((r) => r.version === version)
  if (!req) return
  activeRequirementVersion.value = req.status === 'current' ? null : version
  editing.value = false
  reqText.value = req.requirement_text || ''
  setRequirementSlots(req.slots || {})
}

function cancelEdit() {
  editing.value = false
  activeRequirementVersion.value = null
}

async function saveDraft() {
  if (!formRef.value) return
  if (!basicForm.customer_name.trim()) {
    message.warning('请先填写客户名称')
    return
  }
  const slots = formRef.value.toSlots()
  if (!formRef.value.hasAnyPart) {
    message.warning('请至少填写机型型号、平台类型、服务器类型或机箱形态')
    return
  }
  draftSaving.value = true
  try {
    await projectApi.update(oppId, basicPayload())
    const res = await portalApi.saveRequirementDraft(oppId, slots, reqText.value)
    message.success(`需求草稿 v${res.requirement.version} 已保存`)
    await loadBoard()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存草稿失败')
  } finally {
    draftSaving.value = false
  }
}

async function submitDraft() {
  if (!formRef.value) return
  if (!basicForm.customer_name.trim()) {
    message.warning('请先填写客户名称')
    return
  }
  const slots = formRef.value.toSlots()
  if (!formRef.value.hasAnyPart) {
    message.warning('请至少填写机型型号、平台类型、服务器类型或机箱形态')
    return
  }
  async function doSubmit(assigneeName: string) {
    if (draftReq.value) {
      await projectApi.update(oppId, basicPayload())
      await portalApi.saveRequirementDraft(oppId, slots, reqText.value)
      return portalApi.submitRequirementDraft(oppId, draftReq.value.version, assigneeName)
    }
    return portalApi.initiate(oppId, basicPayload(), slots, reqText.value, assigneeName)
  }
  async function runSubmit(assigneeName: string) {
    submitting.value = true
    try {
      const res = await doSubmit(assigneeName)
      message.success(`需求单 v${res.requirement.version} 已提交，流程进入 BOM 环节`)
      editing.value = false
      basicEditing.value = false
      activeRequirementVersion.value = null
      await loadBoard()
      activeNode.value = 'boming'
      scrollToNode('boming')
    } catch (e: any) {
      if (e?.response?.data?.detail === ASSIGNEE_REQUIRED_DETAIL) {
        promptAssignee('boming', '选择技术支持处理人', (name) => { runSubmit(name) })
        return
      }
      message.error(e.response?.data?.detail || '提交失败')
    } finally {
      submitting.value = false
    }
  }
  await runSubmit('')
}

const archivedRequirementCards = computed(() =>
  requirements.value.filter((r) => r.status === 'archived').sort((a, b) => b.version - a.version),
)

const quotations = computed(() => props.quotations || [])
const quotePriceVisible = computed(() => props.quotePriceVisible ?? false)
const quoteSelectMode = computed(() => props.quoteSelectMode ?? false)
const quoteSelectedIds = computed(() => new Set(props.quoteSelectedIds || []))

const detailModalWidth = computed(() =>
  ['boming', 'costing', 'quoting'].includes(detailKey.value) ? 'min(1480px, 98vw)' : 'min(1200px, 96vw)',
)

const detailTitle = computed(() => {
  if (detailKey.value === 'requirement') return '需求单'
  const node = (PROCESS_NODES as readonly { key: string; label: string; title?: string }[]).find(
    (item) => item.key === detailKey.value,
  )
  return node?.title ? `${node.title}工作台` : node?.label || '详情'
})
function openRequirementDetail(version: number) {
  const req = requirements.value.find((item) => item.version === version)
  if (!req) return
  if (req.status === 'draft') startEditDraft()
  else showRequirement(version)
  detailKey.value = 'requirement'
  detailOpen.value = true
}

function closeDetail() {
  detailOpen.value = false
}

async function convertCosting(quotationId: string) {
  try {
    await portalApi.convertCostToQuotation(oppId, quotationId)
    message.success('已转为报价单')
    await loadBoard()
    emit('refresh-quotations')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '转为报价单失败')
  }
}

async function deleteCostSheet(sheetId: number) {
  Modal.confirm({
    title: '删除对应成本表？',
    content: '删除后不可恢复；仅当对应报价单已删除时允许删除该成本表。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await portalApi.deleteCostSheet(oppId, sheetId)
        message.success('成本表已删除')
        await loadBoard()
        emit('refresh-quotations')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除成本表失败')
      }
    },
  })
}

const archiveOpen = ref(false)
const archiveCategories = ref<string[]>([])
const archiveTitle = ref('附件')
const archiveAttachments = computed(() => {
  const set = new Set(archiveCategories.value)
  return (props.attachments || []).filter((a) => set.has(a.category || ''))
})
function openArchive(categories: string[], title: string) {
  archiveCategories.value = categories
  archiveTitle.value = title
  archiveOpen.value = true
}

function openArchiveFromNode(payload: { categories: string[]; title: string }) {
  openArchive(payload.categories, payload.title)
}
onMounted(loadBoard)
defineExpose({ reload: loadBoard })
</script>

<template>
  <div class="bod-page">

    <!-- 手机端阶段工具条：☰流程 → 左抽屉；①-④ 迷你进度（点击同开左抽屉）；动态 → 右抽屉 -->
    <div v-if="isMobile && board" class="stagebar">
      <button class="sb-btn" type="button" @click="railDrawerOpen = true"><MenuOutlined />流程</button>
      <div class="sb-steps" @click="railDrawerOpen = true">
        <template v-for="(s, i) in stageSteps" :key="s.key">
          <span v-if="i > 0" class="sb-line" :class="{ done: stageSteps[i - 1].state === 'done' }"></span>
          <span class="sb-step" :class="s.state">
            <i>{{ s.state === 'done' ? '✓' : i + 1 }}</i>
            <span>{{ s.short }}</span>
          </span>
        </template>
      </div>
      <button class="sb-btn" type="button" @click="dynDrawerOpen = true">
        动态<span v-if="dynUnread" class="sb-badge">{{ dynUnread > 99 ? '99+' : dynUnread }}</span>
      </button>
    </div>

    <div v-if="board" class="board-body" :class="{ 'rail-collapsed': railCollapsed }">
      <OpportunityProcessRail
        v-if="!isMobile"
        class="board-rail"
        :nodes="stepperNodes"
        :active-node="activeNode"
        :disabled-keys="disabledNodeKeys"
        :collapsed="railCollapsed"
        :owner-rows="railOwnerRows"
        :updated-text="railUpdatedText"
        :sub-done="subDoneMap"
        @select="scrollToNode"
        @select-substep="scrollToSubstep"
      />
      <button
        v-if="!isMobile"
        class="rail-toggle"
        type="button"
        :title="railCollapsed ? '展开左栏' : '收起左栏'"
        @click="toggleRail"
      >
        <LeftOutlined />
      </button>

      <a-spin :spinning="loading" class="board-spin">
        <Transition name="node-fade" mode="out-in">
          <div :key="activeNode" class="process-workbench">
            <template v-if="activeNode === 'requirement'">

<section v-if="opp" class="opp-info-panel rich-card" data-substep="requirement.0">
      <header class="opp-info-head card-head-toggle" @click="toggleCard('reqInfo')">
        <div class="opp-info-title">
          <span class="rich-icon-badge"><IdcardOutlined /></span>
          <div class="opp-info-title-text">
            <span class="opp-info-eyebrow">商机信息</span>
            <h4>{{ opp.customer_name || '未命名商机' }}</h4>
          </div>
        </div>
        <div class="opp-info-tools" @click.stop>
          <span v-if="!basicEditing" class="rich-status-check"><CheckCircleFilled /> 已填写</span>
          <template v-if="basicEditing">
            <a-button size="small" @click="cancelBasicEdit">取消</a-button>
            <a-button size="small" type="primary" :loading="basicSaving" @click="saveBasic">保存</a-button>
          </template>
          <a-button v-else size="small" @click="startBasicEdit">编辑商机信息</a-button>
          <button class="card-chevron" :class="{ collapsed: !cardOpen.reqInfo }" type="button" @click.stop="toggleCard('reqInfo')">
            <UpOutlined />
          </button>
        </div>
      </header>
      <div class="card-collapse" :class="{ collapsed: !cardOpen.reqInfo }">
        <div class="card-collapse-inner">
            <a-form v-if="basicEditing" layout="vertical" class="basic-form-grid">
                      <a-form-item label="业务">
                        <a-input v-if="roleLock.sales_person" v-model:value="basicForm.sales_person" disabled />
                        <a-auto-complete v-else v-model:value="basicForm.sales_person" :options="businessOptions" :filter-option="filterBusinessOption" allow-clear :default-active-first-option="false" placeholder="输入或搜索业务名（可自由输入）" @focus="loadBusinessOptions" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="客户名称" required>
                        <a-auto-complete v-model:value="basicForm.customer_name" :options="getFilteredOptions('customer_name')" :default-active-first-option="false" placeholder="请输入客户名称" @focus="loadFieldHistory('customer_name')" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="FAE">
                        <a-input v-if="roleLock.fae" v-model:value="basicForm.fae" disabled />
                        <a-auto-complete v-else v-model:value="basicForm.fae" :options="getFilteredOptions('fae')" :default-active-first-option="false" placeholder="请输入 FAE" @focus="loadFieldHistory('fae')" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="报价人">
                        <a-input v-if="roleLock.quotation_person" v-model:value="basicForm.quotation_person" disabled />
                        <a-auto-complete v-else v-model:value="basicForm.quotation_person" :options="getFilteredOptions('quotation_person')" :default-active-first-option="false" placeholder="请输入报价人" @focus="loadFieldHistory('quotation_person')" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="行业">
                        <a-auto-complete v-model:value="basicForm.industry" :options="getFilteredOptions('industry')" :default-active-first-option="false" placeholder="如 教育/政府/金融/制造" @focus="loadFieldHistory('industry')" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="交付地区">
                        <a-auto-complete v-model:value="basicForm.delivery_region" :options="getFilteredOptions('delivery_region')" :default-active-first-option="false" placeholder="如 国内/海外/偏远" @focus="loadFieldHistory('delivery_region')" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="交付周期">
                        <a-auto-complete v-model:value="basicForm.delivery_cycle" :options="getFilteredOptions('delivery_cycle')" :default-active-first-option="false" placeholder="如 4周" @focus="loadFieldHistory('delivery_cycle')" @keydown.enter="saveBasic" />
                      </a-form-item>
                      <a-form-item label="订单类型">
                        <a-auto-complete v-model:value="basicForm.order_type" :options="getFilteredOptions('order_type')" :default-active-first-option="false" placeholder="如 直销/渠道/集成商/最终用户" @focus="loadFieldHistory('order_type')" @keydown.enter="saveBasic" />
                      </a-form-item>
                    </a-form>
      <dl v-else class="opp-info-grid">
        <div v-for="[k, v] in infoRows" :key="k" class="opp-info-item">
          <dt>{{ k }}</dt>
          <dd :title="String(v)">{{ v }}</dd>
        </div>
      </dl>
        </div>
      </div>
    </section>
          <section class="requirement-workbench" data-substep="requirement.1">
            <header class="rw-head card-head-toggle" @click="toggleCard('requirement')">
              <div class="rw-head-title">
                <span class="rich-icon-badge"><FileTextOutlined /></span>
                <div>
                  <span class="rw-eyebrow">线索登记</span>
                  <h3>需求单工作台</h3>
                </div>
              </div>
              <div class="rw-head-actions" @click.stop>
                <span v-if="currentReq" class="rich-status-check"><CheckCircleFilled /> 已发起</span>
                <AttachmentUploadButton :opportunity-id="oppId" category="lead_requirement" label="上传附件" />
                <a-button size="small" @click="openArchive(['lead_requirement'], '我的附件')">我的附件</a-button>
                <a-button v-if="canWriteRequirement" type="primary" size="small" @click="startNewDraft">新建需求</a-button>
                <button class="card-chevron" :class="{ collapsed: !cardOpen.requirement }" type="button" @click.stop="toggleCard('requirement')">
                  <UpOutlined />
                </button>
              </div>
            </header>

            <div class="card-collapse" :class="{ collapsed: !cardOpen.requirement }">
              <div class="card-collapse-inner">
              <RecordTable
                title="需求单"
                :empty="!currentReq && !draftReq && !archivedRequirementCards.length"
                empty-text="尚无需求单，点击“新建需求”开始填写。"
                :columns="[
                  { label: '版本', width: '150px' },
                  { label: '状态', width: '120px' },
                  { label: '服务器型号' },
                  { label: '平台类型' },
                  { label: '数量', width: '90px' },
                  { label: '维保年限', width: '100px' },
                  { label: '创建人 / 时间', width: '180px' },
                  { label: '操作', width: '130px', align: 'right' },
                ]"
              >
              <tr
                v-if="currentReq"
                @click="openRequirementDetail(currentReq.version)"
              >
                <td>
                  <span class="rt-strong">需求单 v{{ currentReq.version }}</span>
                  <span class="rt-sub">线索登记</span>
                </td>
                <td><span class="rt-badge rt-badge-current">{{ requirementCardStatus(currentReq) }}</span></td>
                <td>{{ currentReq.slots?.server_model || '—' }}</td>
                <td>{{ currentReq.slots?.platform_type || '—' }}</td>
                <td>{{ currentReq.slots?.purchase_qty ? `${currentReq.slots.purchase_qty} 台` : '—' }}</td>
                <td>{{ currentReq.slots?.warranty_years || '—' }}</td>
                <td class="rt-dim">{{ currentReq.created_by || '—' }} · {{ (currentReq.created_at || '').slice(5, 16) }}</td>
                <td>
                  <div class="rt-actions">
                    <span
                      v-if="cardForRequirement(currentReq)?.current_node === 'boming' && cardForRequirement(currentReq)?.flow_status === 'submitted'"
                      class="rt-link"
                      @click.stop="requestWithdrawRequirement(currentReq)"
                    >申请撤回</span>
                  </div>
                </td>
              </tr>

              <tr
                v-if="draftReq && draftReq.version !== currentReq?.version"
                @click="openRequirementDetail(draftReq.version)"
              >
                <td>
                  <span class="rt-strong">需求草稿 v{{ draftReq.version }}</span>
                  <span class="rt-sub">未提交</span>
                </td>
                <td><span class="rt-badge rt-badge-draft">草稿</span></td>
                <td>{{ draftReq.slots?.server_model || '—' }}</td>
                <td>{{ draftReq.slots?.platform_type || '—' }}</td>
                <td>{{ draftReq.slots?.purchase_qty ? `${draftReq.slots.purchase_qty} 台` : '—' }}</td>
                <td>{{ draftReq.slots?.warranty_years || '—' }}</td>
                <td class="rt-dim">{{ draftReq.created_by || '—' }} · {{ (draftReq.created_at || '').slice(5, 16) }}</td>
                <td>
                  <div class="rt-actions">
                    <span class="rt-link danger" @click.stop="deleteDraft(draftReq.version)">
                      {{ deletingDraft ? '删除中...' : '删除草稿' }}
                    </span>
                  </div>
                </td>
              </tr>

              <tr
                v-for="req in archivedRequirementCards"
                :key="req.version"
                @click="openRequirementDetail(req.version)"
              >
                <td>
                  <span class="rt-strong">需求单 v{{ req.version }}</span>
                  <span class="rt-sub">REQ-{{ req.version }}</span>
                </td>
                <td><span class="rt-badge rt-badge-done">{{ requirementCardStatus(req) }}</span></td>
                <td>{{ req.slots?.server_model || '—' }}</td>
                <td>{{ req.slots?.platform_type || '—' }}</td>
                <td>{{ req.slots?.purchase_qty ? `${req.slots.purchase_qty} 台` : '—' }}</td>
                <td>{{ req.slots?.warranty_years || '—' }}</td>
                <td class="rt-dim">{{ req.created_by || '—' }} · {{ (req.created_at || '').slice(5, 16) }}</td>
                <td>
                  <div class="rt-actions">
                    <span
                      v-if="cardForRequirement(req)?.flow_status === 'submitted' && cardForRequirement(req)?.current_node !== 'requirement'"
                      class="rt-link"
                      @click.stop="requestWithdrawRequirement(req)"
                    >申请撤回</span>
                  </div>
                </td>
              </tr>

            </RecordTable>
              </div>
            </div>
          </section>

        </template>

        <section
          v-else-if="activeNode === 'boming' && board && (isAdmin || !bomLocked || bomSchemes.length)"
          class="rich-card card-collapsible"
          data-substep="boming.0 boming.1"
        >
          <header class="card-shell-head card-head-toggle" @click="toggleCard('boming')">
            <div class="card-shell-title">
              <span class="rich-icon-badge"><ToolOutlined /></span>
              <div>
                <span class="card-shell-eyebrow">技术支持</span>
                <h3>方案配置</h3>
              </div>
            </div>
            <div class="card-shell-actions" @click.stop>
              <AttachmentUploadButton :opportunity-id="oppId" category="technical" label="上传附件" />
              <a-button size="small" @click="openArchiveFromNode({ categories: ['technical'], title: '方案附件' })">方案附件</a-button>
              <a-button v-if="canWriteBom" type="primary" size="small" @click="bomWorkbenchRef?.openNew()">新建方案</a-button>
              <button class="card-chevron" :class="{ collapsed: !cardOpen.boming }" type="button" @click.stop="toggleCard('boming')">
                <UpOutlined />
              </button>
            </div>
          </header>
          <div class="card-collapse" :class="{ collapsed: !cardOpen.boming }">
            <div class="card-collapse-inner">
              <BomSchemeWorkbench
                ref="bomWorkbenchRef"
                :board="board"
                :readonly="!canWriteBom"
                @card-updated="upsertFlowCard"
                @changed="loadBoard"
              />
            </div>
          </div>
        </section>
        <section
          v-else-if="activeNode === 'costing' && board && (isAdmin || !costLocked || costSheets.length)"
          class="rich-card card-collapsible"
          data-substep="costing.0 costing.1"
        >
          <header class="card-shell-head card-head-toggle" @click="toggleCard('costing')">
            <div class="card-shell-title">
              <span class="rich-icon-badge"><CalculatorOutlined /></span>
              <div>
                <h3>成本核算</h3>
              </div>
            </div>
            <div class="card-shell-actions" @click.stop>
              <a-button size="small" @click="openArchiveFromNode({ categories: ['requirement'], title: '成本附件' })">成本附件</a-button>
              <a-button v-if="canWriteCost" type="primary" size="small" @click="emit('upload-cost-sheet')">上传成本表</a-button>
              <a-button v-if="canWriteCost" type="primary" size="small" @click="costWorkbenchRef?.openNew()">新建成本表</a-button>
              <button class="card-chevron" :class="{ collapsed: !cardOpen.costing }" type="button" @click.stop="toggleCard('costing')">
                <UpOutlined />
              </button>
            </div>
          </header>
          <div class="card-collapse" :class="{ collapsed: !cardOpen.costing }">
            <div class="card-collapse-inner">
              <CostSheetWorkbench
                ref="costWorkbenchRef"
                :board="board"
                :readonly="!canWriteCost"
                @card-updated="upsertFlowCard"
                @changed="loadBoard"
              />
            </div>
          </div>
        </section>
        <div
          v-else-if="activeNode === 'quoting' && board"
          class="node-quote-shell"
        >
          <QuoteWorkbench
                :board="board"
                :quote-context="board.quote_context"
                :quotations="quotations"
                :quote-price-visible="quotePriceVisible"
                :quote-select-mode="quoteSelectMode"
                :quote-selected-ids="quoteSelectedIds"
                :attachments="attachments"
                :upstream-open="cardOpen.quoteUpstream"
                @update:upstream-open="setCardOpen('quoteUpstream', $event)"
                :quote-open="cardOpen.quoteEditor"
                @update:quote-open="setCardOpen('quoteEditor', $event)"
                @new-quotation="emit('new-quotation')"
                @view-quotation="emit('view-quotation', $event)"
                @unfreeze-quotation="emit('unfreeze-quotation', $event)"
                @set-primary="emit('set-primary', $event)"
                @rename-quotation="emit('rename-quotation', $event)"
                @delete-quotation="emit('delete-quotation', $event)"
                @toggle-quote-select="emit('toggle-quote-select', $event)"
                @enter-quote-batch="emit('enter-quote-batch')"
                @exit-quote-batch="emit('exit-quote-batch')"
                @batch-delete-quotes="emit('batch-delete-quotes')"
                @convert-cost-to-quotation="convertCosting"
                @delete-cost-sheet="deleteCostSheet"
                @card-updated="upsertFlowCard"
                @open-archive="openArchiveFromNode"
                @refresh-quotations="handleQuoteRefresh"
                @close="activeNode = 'costing'"
              />
        </div>
        <div v-else class="node-empty">{{ activeNodeEmptyText }}</div>
          </div>
        </Transition>
      </a-spin>

      <aside v-if="!isMobile" class="board-aside">
        <section class="timeline">
          <div class="tl-head">协作与动态</div>
          <ApprovalFlowPanel
            :opportunity-id="oppId"
            :nodes="board?.nodes || []"
            :current-node="currentFlowNode"
            :active-node="activeNode"
            :flow-cards="board?.flow_cards || []"
            :approvals="board?.approvals || []"
            :flow="board?.flow || null"
            :opportunity="board?.opportunity || null"
          />
        </section>
      </aside>

      <!-- 手机端左抽屉：流程轨道（选节点即切换工作台并收起） -->
      <a-drawer
        v-model:open="railDrawerOpen"
        placement="left"
        width="82%"
        root-class-name="opp-detail-drawer"
        :closable="false"
        :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
      >
        <div class="pd-head-row">
          <h3>流程轨道</h3><span class="pd-chip">4 步审批流</span><span class="pd-sp"></span>
          <button class="pd-x" type="button" @click="railDrawerOpen = false">✕</button>
        </div>
        <div class="pd-scroll">
          <OpportunityProcessRail
            v-if="isMobile"
            :nodes="stepperNodes"
            :active-node="activeNode"
            :disabled-keys="disabledNodeKeys"
            :collapsed="false"
            :owner-rows="railOwnerRows"
            :updated-text="railUpdatedText"
            :sub-done="subDoneMap"
            @select="selectFromDrawer"
            @select-substep="selectSubFromDrawer"
          />
        </div>
      </a-drawer>

      <!-- 手机端右抽屉：协作与动态（ApprovalFlowPanel 复用，pending 审批直达） -->
      <a-drawer
        v-model:open="dynDrawerOpen"
        placement="right"
        width="88%"
        root-class-name="opp-detail-drawer"
        :closable="false"
        :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
      >
        <div class="pd-head-row">
          <h3>协作与动态</h3><span class="pd-chip">本商机</span><span class="pd-sp"></span>
          <button class="pd-x" type="button" @click="dynDrawerOpen = false">✕</button>
        </div>
        <div class="pd-scroll">
          <ApprovalFlowPanel
            v-if="isMobile"
            :opportunity-id="oppId"
            :nodes="board?.nodes || []"
            :current-node="currentFlowNode"
            :active-node="activeNode"
            :flow-cards="board?.flow_cards || []"
            :approvals="board?.approvals || []"
            :flow="board?.flow || null"
            :opportunity="board?.opportunity || null"
          />
        </div>
      </a-drawer>
    </div>

    <section v-else-if="boardLoadError" class="node-empty board-load-error">
      <span>看板加载失败，请重试</span>
      <a-button size="small" @click="loadBoard">重试</a-button>
    </section>

    <a-modal
      :open="detailOpen"
      :title="detailTitle"
      :width="detailModalWidth"
      wrap-class-name="portal-sheet-modal"
      :footer="null"
      :body-style="{ padding: '16px', maxHeight: 'calc(100vh - 180px)', overflow: 'auto' }"
      @cancel="closeDetail"
    >
      <div class="drawer-body">
                                <template v-if="detailKey === 'requirement'">
          <section class="node-card glass">
            <div class="node-head">
              <span class="node-num">1</span>
              <div class="node-title-wrap">
                <h3>需求单 <span v-if="selectedRequirement" class="node-version">v{{ selectedRequirement.version }}</span></h3>
                <p>当前需求、草稿与历史版本</p>
              </div>
              <span v-if="editing || selectedRequirement?.status === 'draft'" class="node-state current">草稿</span>
              <span v-else-if="selectedRequirement || currentReq" class="node-state done">已发起</span>
            </div>
            <div class="node-body">
              <div v-if="editing">
                <p class="node-edit-tip">编辑中的需求为草稿，提交后生成新版本快照并进入 BOM 环节。</p>
                <RequirementForm ref="formRef" v-model:req-text="reqText" />
                <div class="node-actions">
                  <a-button @click="cancelEdit">取消</a-button>
                  <a-button :loading="draftSaving" @click="saveDraft">保存草稿</a-button>
                  <a-button type="primary" :loading="submitting" @click="submitDraft">提交发起</a-button>
                </div>
              </div>

              <div v-else-if="selectedRequirement">
                <div v-if="selectedRequirement.created_by" class="req-snapshot-bar">
                  <span class="req-snapshot-meta">
                    {{ selectedRequirement.created_by }} · {{ (selectedRequirement.created_at || '').slice(5, 16) }}
                  </span>
                </div>
                <RequirementForm
                  ref="formRef"
                  v-model:req-text="reqText"
                  :readonly="true"
                />
                <div v-if="draftReq && draftReq.version !== selectedRequirement.version" class="node-actions">
                  <a-button @click="startEditDraft">继续编辑草稿</a-button>
                </div>
              </div>

              <div v-else>
                <a-empty description="尚无需求快照">
                  <a-button v-if="canWriteRequirement" type="primary" @click="startNewDraft">新增需求</a-button>
                </a-empty>
              </div>
            </div>
          </section>
        </template>

      </div>
    </a-modal>

    <div v-if="editing" class="bod-sticky-bar">
      <a-button type="primary" size="large" :loading="submitting" block @click="submitDraft">提交需求单</a-button>
    </div>

    <a-modal
      v-model:open="archiveOpen"
      :title="archiveTitle"
      width="min(1100px, 96vw)"
      :footer="null"
      :body-style="{ padding: '12px', maxHeight: 'calc(100vh - 140px)', overflow: 'auto' }"
      @cancel="archiveOpen = false"
    >
      <ArchiveSection
        :opportunity-id="oppId"
        :attachments="archiveAttachments"
        :categories="archiveCategories"
        @preview="(a: FeedAttachment) => emit('preview-attachment', a)"
        @delete="(a: FeedAttachment) => emit('delete-attachment', a)"
      />
    </a-modal>
    <AssigneePickerModal
      v-model:value="pickerChosen"
      :open="pickerOpen"
      :title="pickerTitle"
      :options="pickerOptions"
      @confirm="confirmPicker()"
      @cancel="cancelPicker()"
    />
  </div>
</template>

<style scoped>
.bod-page {
  display: flex;
  flex-direction: column;
  height: auto;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.bod-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px 0;
}

.board-body {
  /* 左栏宽度由变量驱动：折叠时 230px → 64px */
  --rail-w: 230px;
  position: relative;
  flex: 1;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) clamp(280px, 22vw, 360px);
  gap: 14px;
  align-items: stretch;
  height: 100%;
  min-height: 0;
  padding: 14px 20px 16px;
  min-width: 0;
}
.board-body.rail-collapsed {
  --rail-w: 64px;
}
.board-rail {
  width: var(--rail-w);
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  transition: width var(--cpq-dur-2, 280ms) var(--cpq-ease-smooth, cubic-bezier(0.4, 0, 0.2, 1));
}

/* 折叠按钮：跨在左栏右缘，不占布局 */
.rail-toggle {
  position: absolute;
  top: 50%;
  left: calc(var(--rail-w) + 8px);
  z-index: 3;
  width: 24px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid var(--cpq-glass-border);
  border-left: 0;
  border-radius: 0 var(--cpq-radius-sm, 8px) var(--cpq-radius-sm, 8px) 0;
  background: var(--cpq-bg-card);
  color: var(--cpq-text-muted);
  font-size: 12px;
  cursor: pointer;
  transform: translateY(-50%);
  box-shadow: var(--cpq-shadow-sm);
  transition: left var(--cpq-dur-2, 280ms) var(--cpq-ease-smooth, cubic-bezier(0.4, 0, 0.2, 1)),
    transform var(--cpq-dur-2, 280ms) var(--cpq-ease-smooth, cubic-bezier(0.4, 0, 0.2, 1)),
    color var(--cpq-dur-1, 160ms) ease, box-shadow var(--cpq-dur-1, 160ms) ease;
}
.rail-toggle:hover {
  color: var(--cpq-accent-primary);
  box-shadow: var(--cpq-shadow-md);
}
.board-body.rail-collapsed .rail-toggle {
  transform: translateY(-50%) rotate(180deg);
}
.board-spin {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.board-spin :deep(.ant-spin-container) {
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.board-aside {
  min-width: 0;
  min-height: 0;
  display: flex;
  align-self: stretch;
}
.board-aside .timeline {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: auto;
}
.board-aside .timeline > :last-child {
  flex: 1;
  min-height: 0;
}
.board-rail :deep(.process-rail) {
  height: 100%;
}

.board-workbench {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 20px 20px;
}

.process-workbench {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding: 0 2px 12px 0;
  flex: 1;
}
.node-fade-enter-active,
.node-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.node-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.node-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
.requirement-workbench {
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
  padding: 0;
}
.rw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  margin-bottom: 0;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.rw-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rw-head-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.rw-eyebrow {
  display: none;
}
.rw-head h3 {
  margin: 0;
  color: var(--cpq-text-primary);
  font-size: 14px;
}
.rw-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 12px 14px;
}
.rw-empty {
  grid-column: 1 / -1;
  padding: 40px 16px;
  text-align: center;
  color: var(--cpq-text-muted);
  font-size: 13px;
  border: 1px dashed var(--cpq-glass-border);
  border-radius: 12px;
}
.timeline {
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.tl-head {
  padding: 11px 14px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
  font-weight: 700;
  font-size: 14px;
  color: var(--cpq-text-primary);
}
.board-workbench-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 2px 0;
  color: var(--cpq-text-secondary);
  font-size: 13px;
}
.bod-stage-wrap {
  flex: 1;
  min-width: 0;
  padding: 0;
}
.board-canvas {
  display: grid;
  grid-template-columns: repeat(4, minmax(248px, 1fr));
  gap: 14px;
  align-items: start;
  padding: 14px 20px 24px;
  min-width: 0;
  overflow-x: auto;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.summary-row b {
  flex-shrink: 0;
  font-weight: 500;
  color: var(--cpq-text-muted);
}
.summary-row span {
  min-width: 0;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.summary-row.muted {
  color: var(--cpq-text-muted);
  font-size: 11px;
}

.opp-info-panel {
  margin: 0;
  padding: 0;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  overflow: hidden;
}
.opp-info-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--cpq-overlay-w10);
}
.opp-info-panel .card-collapse-inner {
  padding: 0 16px 16px;
}
.opp-info-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.opp-info-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.opp-info-title-text {
  min-width: 0;
}
.rich-icon-badge {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.92), rgba(139, 92, 246, 0.88));
  color: #fff;
  font-size: 18px;
  box-shadow: 0 6px 18px rgba(99, 102, 241, 0.28);
}
.rich-status-check {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-color-success, #52c41a);
  white-space: nowrap;
}
.rich-card {
  box-shadow: var(--cpq-glass-card-shadow);
}
.card-collapsible {
  overflow: hidden;
}
.card-shell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.card-shell-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.card-shell-title > div {
  min-width: 0;
}
.card-shell-eyebrow {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--cpq-text-muted);
}
.card-shell-title h3 {
  margin: 3px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.card-shell-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
/* 整条卡头横条可点击展开/收起；头部操作区 @click.stop 隔离按钮 */
.card-head-toggle {
  cursor: pointer;
}
.card-chevron {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 8px;
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.15s ease, color 0.15s ease;
}
.card-chevron:hover {
  background: var(--cpq-overlay-w8);
  color: var(--cpq-text-primary);
}
.card-chevron.collapsed {
  transform: rotate(180deg);
}
.card-collapse {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 0.22s ease;
}
.card-collapse.collapsed {
  grid-template-rows: 0fr;
}
/* 折叠态必须彻底为 0 高：内层 padding 会撑起网格最小行高，露出内容残影 */
.card-collapse.collapsed > .card-collapse-inner {
  padding-top: 0;
  padding-bottom: 0;
}
.card-collapse-inner {
  min-height: 0;
  overflow: hidden;
}
.opp-info-eyebrow {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--cpq-text-muted);
}
.opp-info-title h4 {
  margin: 3px 0 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.opp-info-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
  border: 1px solid var(--cpq-glass-border);
  border-radius: 999px;
  padding: 2px 9px;
}
.opp-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 24px;
  margin: 0;
}
.opp-info-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--cpq-overlay-w5);
  min-width: 0;
}
.opp-info-item dt {
  flex-shrink: 0;
  min-width: 72px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.opp-info-item dd {
  flex: 1;
  margin: 0;
  font-size: 13px;
  color: var(--cpq-text-primary);
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.req-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px 10px;
}
.req-info-grid .summary-cell {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.req-info-grid .summary-cell b {
  flex-shrink: 0;
  font-weight: 500;
  color: var(--cpq-text-muted);
}
.req-info-grid .summary-cell span {
  min-width: 0;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.row-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-glass-border);
  color: var(--cpq-text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.row-meta-item b {
  font-weight: 500;
  color: var(--cpq-text-muted);
}
.row-meta-item.muted {
  color: var(--cpq-text-muted);
  background: transparent;
  border: none;
  padding: 0 2px;
}
.draft-delete-link {
  font-size: 12px;
  color: #ff4d4f;
  cursor: pointer;
}
.draft-delete-link:hover {
  text-decoration: underline;
}
.requirement-return-link {
  font-size: 12px;
  color: var(--cpq-color-warning, #faad14);
  cursor: pointer;
}
.requirement-return-link:hover {
  text-decoration: underline;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.node-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.node-edit-tip {
  margin: 0;
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.node-empty {
  padding: 18px;
  color: var(--cpq-text-muted);
  font-size: 13px;
}
.board-load-error {
  display: flex;
  align-items: center;
  gap: 12px;
}
.node-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.node-card {
  padding: 0;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  overflow: hidden;
}
.node-card > :not(.node-head) {
  padding: 16px;
}
.node-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--cpq-overlay-w10);
  background: var(--cpq-overlay-w4);
}
.node-num {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: var(--cpq-overlay-a15);
  color: var(--cpq-accent-primary);
  font-size: 12px;
  font-weight: 600;
}
.node-title-wrap {
  flex: 1;
  min-width: 0;
}
.node-title-wrap h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.node-title-wrap p {
  margin: 3px 0 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.node-version {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  border: 1px solid var(--cpq-glass-border);
  border-radius: 4px;
  padding: 0 5px;
}
.node-state {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
  border: 1px solid var(--cpq-glass-border);
  border-radius: 999px;
  padding: 1px 8px;
  white-space: nowrap;
}
.node-state.done {
  color: var(--cpq-color-success, #52c41a);
  border-color: var(--cpq-color-success, #52c41a);
}
.node-state.current {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
}
.node-state.pending {
  color: var(--cpq-text-muted);
}

.req-snapshot-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--cpq-glass-border);
}
.req-version-tag {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.req-snapshot-meta {
  margin-left: auto;
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.basic-body {
  display: flex;
  flex-direction: column;
}
.basic-form-grid,
.basic-view-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 14px;
}
.basic-view-grid {
  gap: 8px 20px;
  margin: 0;
}
.basic-view-grid dt {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.basic-view-grid dd {
  margin: 0;
  font-size: 13px;
  color: var(--cpq-text-primary);
}
.basic-form-grid :deep(.ant-form-item) {
  margin-bottom: 0;
}

.bom-table {
  margin-top: 0;
}
.cost-kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.cost-kpi {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 12px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w4);
}
.cost-kpi span {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.cost-kpi strong {
  font-size: 17px;
  color: var(--cpq-text-primary);
}
.cost-kpi.accent strong {
  color: var(--cpq-accent-primary);
}

.bod-card {
  border-radius: var(--cpq-radius-lg);
  border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  padding: 14px;
}
.bod-card-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.bod-sticky-bar {
  display: none;
}

@media (max-width: 1080px) {
  .bod-page {
    overflow-y: auto;
  }
  .board-canvas {
    grid-template-columns: repeat(2, minmax(248px, 1fr));
  }
  .basic-form-grid,
  .basic-view-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .opp-info-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .board-body {
    flex: none;
    height: auto;
    grid-template-columns: 1fr;
    min-height: auto;
  }
  /* 窄屏单列堆叠时，左栏不折叠、占满整行 */
  .rail-toggle {
    display: none;
  }
  .board-rail {
    width: 100%;
  }
  .board-rail {
    overflow: visible;
  }
  .board-spin,
  .board-spin :deep(.ant-spin-container) {
    overflow: visible;
  }
  .process-workbench {
    min-height: auto;
    overflow: visible;
  }
  .board-aside {
    position: static;
    height: auto;
  }
  .board-aside .timeline {
    height: auto;
  }
}

@media (max-width: 768px) {
  .bod-page {
    padding-bottom: calc(72px + var(--cpq-tabbar-inset, 0px));
  }
  .bod-toolbar {
    flex-direction: column;
    align-items: stretch;
    padding: 10px 12px 0;
  }
  .board-canvas {
    display: block;
    padding: 12px;
  }
  /* 三栏 → 双抽屉：rail / aside 移入抽屉，工作台独占全屏 */
  .board-rail,
  .board-aside,
  .rail-toggle {
    display: none !important;
  }
  .opp-info-panel {
    margin: 12px 12px 0;
    padding: 14px;
  }
  .opp-info-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .basic-form-grid,
  .basic-view-grid,
  .cost-kpis {
    grid-template-columns: 1fr;
  }
  .node-actions {
    flex-wrap: wrap;
  }
  .bod-sticky-bar {
    display: block;
    position: sticky;
    bottom: var(--cpq-tabbar-inset, 0px);
    z-index: 10;
    padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
    background: var(--cpq-glass-card-bg);
    backdrop-filter: blur(var(--cpq-glass-card-blur));
    border-top: 1px solid var(--cpq-glass-border);
  }
  .bod-sticky-bar :deep(.ant-btn) {
    min-height: 44px;
  }
}

/* ── 手机端阶段工具条（仅 isMobile 渲染，样式放顶层避免断点耦合） ── */
.stagebar {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 12px 9px;
  padding: 7px 9px;
  background: var(--cpq-glass-card-bg, var(--cpq-overlay-w5));
  border: 1px solid var(--cpq-glass-border);
  border-radius: 13px;
  box-shadow: 0 6px 18px var(--cpq-shadow-color, rgba(31, 42, 61, 0.06));
}
.sb-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-2-bg, transparent);
  border-radius: 9px;
  padding: 5px 9px;
  flex: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.sb-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 15px;
  height: 15px;
  border-radius: 999px;
  background: var(--cpq-accent-danger);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}
.sb-steps {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  cursor: pointer;
}
.sb-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  flex: none;
}
.sb-step i {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9.5px;
  font-style: normal;
  font-weight: 700;
  border: 1.6px solid var(--cpq-border-secondary);
  color: var(--cpq-text-muted);
  background: var(--cpq-glass-2-bg, transparent);
}
.sb-step span {
  font-size: 9px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
}
.sb-step.done i {
  background: var(--cpq-accent-success);
  border-color: var(--cpq-accent-success);
  color: var(--cpq-accent-on-primary, #fff);
}
.sb-step.done span { color: var(--cpq-accent-success); }
.sb-step.cur i {
  background: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-on-primary, #fff);
  box-shadow: 0 0 0 3px var(--cpq-overlay-a15);
}
.sb-step.cur span { color: var(--cpq-accent-primary); font-weight: 700; }
.sb-line {
  width: 12px;
  height: 1.6px;
  background: var(--cpq-border-secondary);
  margin: 0 2px 12px;
  flex: none;
}
.sb-line.done { background: var(--cpq-accent-success); }

/* 抽屉头与滚动体（slot 内容带本组件 scope） */
.pd-head-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 15px 10px;
  flex: none;
}
.pd-head-row h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}
.pd-chip {
  font-size: 10px;
  color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w6);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
}
.pd-sp { flex: 1; }
.pd-x {
  width: 29px;
  height: 29px;
  border-radius: 10px;
  border: 1px solid var(--cpq-overlay-w10);
  background: var(--cpq-overlay-w5);
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.pd-scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: 0 6px 12px;
}
.bom-config-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.bom-config-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.bom-subsection {
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w3);
  overflow: hidden;
}
.bom-subsection-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w5);
}
.bom-subsection-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.bom-subsection-head span {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.bom-subsection-empty {
  padding: 14px 12px;
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.bom-detail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.bom-detail-table th,
.bom-detail-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--cpq-overlay-w5);
  text-align: left;
  color: var(--cpq-text-primary);
}
.bom-detail-table th {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-muted);
  font-weight: 600;
}
.bom-detail-table td:last-child {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  :deep(.ant-modal) {
    max-width: 100vw;
    margin: 0;
    padding-bottom: env(safe-area-inset-bottom);
  }
  :deep(.ant-modal-content) {
    border-radius: 0;
  }
}

.bom-config-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 0 14px;
  padding: 10px 12px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w4);
}
.bom-config-head div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.bom-config-head strong {
  font-size: 14px;
  color: var(--cpq-text-primary);
}
.bom-config-head span {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.bom-config-qty {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.cost-kpis.single {
  margin: 4px 0 14px;
}

.quote-stage-actions {
  display: flex;
  gap: 8px;
}
.quote-stage-actions .ant-btn {
  flex: 1;
}
.quote-stage-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 16px 0 12px;
}
.quote-stage-head h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.quote-stage-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.quote-stage-head-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.quote-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.quote-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.quote-row:hover {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-w3);
}
.quote-row.selecting {
  cursor: pointer;
}
.quote-check {
  display: inline-flex;
  align-items: center;
}
.quote-state-badge {
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 18px;
  white-space: nowrap;
}
.quote-state-badge.draft {
  color: #d48806;
  border: 1px solid #d48806;
}
.quote-state-badge.exported {
  color: var(--cpq-color-success, #52c41a);
  border: 1px solid var(--cpq-color-success, #52c41a);
}
.quote-name {
  min-width: 140px;
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.quote-price,
.quote-margin {
  flex-shrink: 0;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--cpq-text-primary);
}
.quote-margin {
  color: var(--cpq-text-muted);
}
.quote-meta {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
}
.quote-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 2px;
}
.quote-stage-batch {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.quote-stage-empty {
  padding: 14px 12px;
  border: 1px dashed var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.stage-list {
  gap: 6px;
}
.stage-row {
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px;
}
.stage-row .quote-name {
  min-width: 0;
  width: 100%;
}
.stage-row .quote-price {
  margin-left: auto;
}
.stage-row .quote-meta {
  display: none;
}
.stage-row .quote-actions {
  width: 100%;
  justify-content: flex-end;
  flex-wrap: wrap;
}
@media (max-width: 768px) {
  .quote-stage-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .quote-stage-head-actions {
    justify-content: flex-start;
    width: 100%;
  }
  .quote-row {
    flex-wrap: wrap;
  }
  .quote-name {
    min-width: 0;
    width: 100%;
  }
  .quote-meta {
    display: none;
  }
  .quote-actions {
    width: 100%;
    justify-content: flex-end;
    flex-wrap: wrap;
  }
}
</style>

<style>
/* 详情页手机抽屉外壳：a-drawer portal 到 body，scoped 够不到，走全局（玻璃化对齐全站） */
.opp-detail-drawer .ant-drawer-content {
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  overflow: hidden;
}
.opp-detail-drawer .ant-drawer-left .ant-drawer-content { border-radius: 0 18px 18px 0; }
.opp-detail-drawer .ant-drawer-right .ant-drawer-content { border-radius: 18px 0 0 18px; }
.opp-detail-drawer .ant-drawer-header { display: none; }
</style>
