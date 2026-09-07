<script setup lang="ts">
/**
 * 商机全生命周期流程看板（统一详情页中栏）。
 * 左栏：可点击流程时间线；中栏：每个节点一张工作卡；右栏：审批人/审批状态。
 * 需求单提交后进入 BOM 节点；BOM/成本/报价完成后由 board 接口自动带出到对应卡片。
 */
import { ref, reactive, computed, onMounted, nextTick, watch, defineAsyncComponent } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  CheckCircleFilled,
  IdcardOutlined,
  FileTextOutlined,
  ToolOutlined,
  CalculatorOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
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
const reqInfoOpen = ref(true)
const requirementOpen = ref(true)
const bomingOpen = ref(true)
const costingOpen = ref(true)
const activeNodeKey = 'cpq:opportunity:active-node:' + oppId
let nodeInitialized = false
watch(activeNode, (node) => {
  try {
    sessionStorage.setItem(activeNodeKey, node)
  } catch {
    /* ignore storage errors */
  }
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

function scrollToSubstep(key: string, index: number) {
  const sameNode = activeNode.value === key
  activeNode.value = key
  const doScroll = () => {
    const target = document.querySelector(`[data-substep~="${key}.${index}"]`)
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
    

    <div v-if="board" class="board-body">
      <OpportunityProcessRail
        class="board-rail"
        :nodes="stepperNodes"
        :active-node="activeNode"
        :disabled-keys="disabledNodeKeys"
        @select="scrollToNode"
        @select-substep="scrollToSubstep"
      />

      <a-spin :spinning="loading" class="board-spin">
        <Transition name="node-fade" mode="out-in">
          <div :key="activeNode" class="process-workbench">
            <template v-if="activeNode === 'requirement'">

<section v-if="opp" class="opp-info-panel rich-card" data-substep="requirement.0">
      <header class="opp-info-head">
        <div class="opp-info-title">
          <span class="rich-icon-badge"><IdcardOutlined /></span>
          <div class="opp-info-title-text">
            <span class="opp-info-eyebrow">商机信息</span>
            <h4>{{ opp.customer_name || '未命名商机' }}</h4>
          </div>
        </div>
        <div class="opp-info-tools">
          <span v-if="!basicEditing" class="rich-status-check"><CheckCircleFilled /> 已填写</span>
          <template v-if="basicEditing">
            <a-button size="small" @click="cancelBasicEdit">取消</a-button>
            <a-button size="small" type="primary" :loading="basicSaving" @click="saveBasic">保存</a-button>
          </template>
          <a-button v-else size="small" @click="startBasicEdit">编辑商机信息</a-button>
          <button class="card-chevron" :class="{ collapsed: !reqInfoOpen }" type="button" @click="reqInfoOpen = !reqInfoOpen">
            <UpOutlined />
          </button>
        </div>
      </header>
      <div class="card-collapse" :class="{ collapsed: !reqInfoOpen }">
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
            <header class="rw-head">
              <div class="rw-head-title">
                <span class="rich-icon-badge"><FileTextOutlined /></span>
                <div>
                  <span class="rw-eyebrow">线索登记</span>
                  <h3>需求单工作台</h3>
                </div>
              </div>
              <div class="rw-head-actions">
                <span v-if="currentReq" class="rich-status-check"><CheckCircleFilled /> 已发起</span>
                <AttachmentUploadButton :opportunity-id="oppId" category="lead_requirement" label="上传附件" />
                <a-button size="small" @click="openArchive(['lead_requirement'], '我的附件')">我的附件</a-button>
                <a-button type="primary" size="small" @click="startNewDraft">新建需求</a-button>
                <button class="card-chevron" :class="{ collapsed: !requirementOpen }" type="button" @click="requirementOpen = !requirementOpen">
                  <UpOutlined />
                </button>
              </div>
            </header>

            <div class="card-collapse" :class="{ collapsed: !requirementOpen }">
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
          <header class="card-shell-head">
            <div class="card-shell-title">
              <span class="rich-icon-badge"><ToolOutlined /></span>
              <div>
                <span class="card-shell-eyebrow">技术支持</span>
                <h3>方案配置</h3>
              </div>
            </div>
            <button class="card-chevron" :class="{ collapsed: !bomingOpen }" type="button" @click="bomingOpen = !bomingOpen">
              <UpOutlined />
            </button>
          </header>
          <div class="card-collapse" :class="{ collapsed: !bomingOpen }">
            <div class="card-collapse-inner">
              <BomSchemeWorkbench
                :board="board"
                :readonly="isAdmin ? false : bomLocked"
                @card-updated="upsertFlowCard"
                @changed="loadBoard"
                @open-archive="openArchiveFromNode"
              />
            </div>
          </div>
        </section>
        <section
          v-else-if="activeNode === 'costing' && board && (isAdmin || !costLocked || costSheets.length)"
          class="rich-card card-collapsible"
          data-substep="costing.0 costing.1"
        >
          <header class="card-shell-head">
            <div class="card-shell-title">
              <span class="rich-icon-badge"><CalculatorOutlined /></span>
              <div>
                <span class="card-shell-eyebrow">成本核算</span>
                <h3>成本核算</h3>
              </div>
            </div>
            <button class="card-chevron" :class="{ collapsed: !costingOpen }" type="button" @click="costingOpen = !costingOpen">
              <UpOutlined />
            </button>
          </header>
          <div class="card-collapse" :class="{ collapsed: !costingOpen }">
            <div class="card-collapse-inner">
              <CostSheetWorkbench
                :board="board"
                :readonly="isAdmin ? false : costLocked"
                @card-updated="upsertFlowCard"
                @changed="loadBoard"
                @open-archive="openArchiveFromNode"
                @upload-cost-sheet="emit('upload-cost-sheet')"
              />
            </div>
          </div>
        </section>
        <div
          v-else-if="activeNode === 'quoting' && board"
          class="node-quote-shell"
          data-substep="quoting.0 quoting.1"
        >
          <QuoteWorkbench
                :board="board"
                :quote-context="board.quote_context"
                :quotations="quotations"
                :quote-price-visible="quotePriceVisible"
                :quote-select-mode="quoteSelectMode"
                :quote-selected-ids="quoteSelectedIds"
                :attachments="attachments"
                @new-quotation="emit('new-quotation')"
                @view-quotation="emit('view-quotation', $event)"
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

      <aside class="board-aside">
        <section class="timeline">
          <div class="tl-head">审批与流转记录</div>
          <ApprovalFlowPanel :opportunity-id="oppId" :nodes="board?.nodes || []" :current-node="currentFlowNode" :flow-cards="board?.flow_cards || []" />
        </section>
      </aside>
    </div>

    <section v-else-if="boardLoadError" class="node-empty board-load-error">
      <span>看板加载失败，请重试</span>
      <a-button size="small" @click="loadBoard">重试</a-button>
    </section>

    <a-modal
      :open="detailOpen"
      :title="detailTitle"
      :width="detailModalWidth"
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
                  <a-button type="primary" @click="startNewDraft">新增需求</a-button>
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
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 76px;
}

.bod-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px 0;
}

.board-body {
  display: grid;
  grid-template-columns: minmax(200px, 240px) minmax(0, 1fr) minmax(280px, 320px);
  gap: 14px;
  align-items: stretch;
  padding: 14px 20px 24px;
  min-height: calc(100vh - 200px);
  min-width: 0;
}
.board-rail {
  min-width: 0;
}
.board-spin {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.board-spin :deep(.ant-spin-container) {
  width: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.board-aside {
  min-width: 0;
  display: flex;
}
.board-aside .timeline {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.board-aside .timeline > :last-child {
  flex: 1;
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
  padding: 0;
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
    grid-template-columns: 1fr;
    min-height: auto;
  }
}

@media (max-width: 768px) {
  .bod-page {
    padding-bottom: 72px;
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
  :deep(.stage-column) {
    display: none;
  }
  :deep(.stage-column.active) {
    display: flex;
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
    bottom: 0;
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
