<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { confirmWithReason } from './confirmWithReason'
import { AuditOutlined, CalculatorOutlined, DownOutlined, FileDoneOutlined, UpOutlined } from '@ant-design/icons-vue'
import type { CostConfig, FlowCard, PortalBoard, PricingApproval, QuoteContext } from '@/api/portal'
import type { Quotation } from '@/types/opportunity'
import type { FeedAttachment } from '@/api/feed'
import { portalApi } from '@/api/portal'
import { useAuthStore } from '@/store/auth'
import { fmtTime, money } from '@/utils/quoteCommon'
import RecordTable from '@/components/opportunity/RecordTable.vue'
import GroupedConfigDetail from '@/components/opportunity/GroupedConfigDetail.vue'
import AttachmentUploadButton from '@/components/opportunity/AttachmentUploadButton.vue'
import OutboundApprovalModal from '@/components/quotation/OutboundApprovalModal.vue'
import ResponsiveModal from '@/components/common/ResponsiveModal.vue'
import { MODAL_WIDTH } from '@/constants/modalPresets'

const props = withDefaults(defineProps<{
  board: PortalBoard
  quoteContext: QuoteContext
  quotations: Quotation[]
  quotePriceVisible?: boolean
  quoteSelectMode?: boolean
  quoteSelectedIds?: string[] | Set<string>
  attachments?: FeedAttachment[]
  /** 两个面板的折叠状态由 board 统一管理（按节点待办规则给默认值） */
  upstreamOpen?: boolean
  quoteOpen?: boolean
  /** 弹出层（下拉菜单等）挂载容器：宿主是高层级弹窗（如聊天产物卡）时必须传入，
   *  否则菜单 teleport body 的默认层级被宿主弹窗压住，开了也看不见。 */
  popupContainer?: (triggerNode: HTMLElement) => HTMLElement
  /** 宿主弹窗层级：本组件内嵌的全部模态（分享/外发审批/转交/发送/配置明细）
   *  统一接这个 z-index——组件原生于低层级页面时缺省即可（antd 默认 1000）；
   *  被产物卡（z-2000）承载时不传的话内嵌弹窗全部被压住（2026-10-22 实测：
   *  更多→分享的窗口开了看不见）。与 popup-container 同构：一个 prop 修一类。 */
  hostZIndex?: number
}>(), {
  quotePriceVisible: false,
  quoteSelectMode: false,
  quoteSelectedIds: () => [],
  attachments: () => [],
  upstreamOpen: true,
  quoteOpen: true,
})

const emit = defineEmits<{
  (e: 'new-quotation'): void
  (e: 'view-quotation', quotation: Quotation): void
  (e: 'reparse-quotation', quotation: Quotation): void
  (e: 'unfreeze-quotation', quotation: Quotation): void
  (e: 'set-primary', quotation: Quotation): void
  (e: 'rename-quotation', quotation: Quotation): void
  (e: 'delete-quotation', quotationId: string): void
  (e: 'toggle-quote-select', quotationId: string): void
  (e: 'enter-quote-batch'): void
  (e: 'exit-quote-batch'): void
  (e: 'batch-delete-quotes'): void
  (e: 'convert-cost-to-quotation', quotationId: string): void
  (e: 'delete-cost-sheet', sheetId: number): void
  (e: 'open-archive', payload: { categories: string[]; title: string }): void
  (e: 'card-updated', card: FlowCard): void
  (e: 'refresh-quotations'): void
  (e: 'close'): void
  (e: 'update:upstreamOpen', value: boolean): void
  (e: 'update:quoteOpen', value: boolean): void
}>()

const opportunityId = computed(() => props.board.opportunity?.opportunity_id || '')

const bomConfigs = computed(() => props.quoteContext?.bom_configs || [])
const costConfigs = computed(() => props.quoteContext?.cost_configs || [])
const worktableQuotationId = computed(() => props.quoteContext?.worktable_quotation_id || '')
const convertedQuotation = computed(() =>
  props.quotations.find((q) => q.quotation_id === worktableQuotationId.value && (q as any).source !== 'worktable'),
)
const visibleQuotations = computed(() =>
  props.quotations.filter((q) => (q as any).source !== 'worktable'),
)
const canConvert = computed(() => !!worktableQuotationId.value && costConfigs.value.length > 0 && !convertedQuotation.value)
interface WorktableSheetView {
  sheet_id: number
  sheet_name: string
  quotation_id: string
  quotation_exported: boolean
  quotation_deleted: boolean
  converted: boolean
  canConvert: boolean
  created_by: string
  created_at: string
  configNames: string
  totalQty: number
  totalCost: number | null
  cost_configs: CostConfig[]
}
const worktableCostSheets = computed(() => props.quoteContext?.worktable_cost_sheets || [])
const worktableSheetViews = computed<WorktableSheetView[]>(() =>
  worktableCostSheets.value.map((s) => {
    const bom = s.bom_configs || []
    const cost = s.cost_configs || []
    const converted = props.quotations.some(
      (q) => q.quotation_id === s.quotation_id && (q as any).source !== 'worktable',
    )
    let totalCost: number | null = null
    if (cost.length) {
      totalCost = cost.reduce((sum, cfg) => sum + Number(cfg.totals?.totalCost || 0) * Number(cfg.qty || 0), 0)
    }
    return {
      sheet_id: s.sheet_id,
      sheet_name: s.sheet_name,
      quotation_id: s.quotation_id,
      quotation_exported: s.quotation_exported,
      quotation_deleted: s.quotation_deleted === true,
      converted,
      canConvert: !!s.quotation_id && cost.length > 0 && !converted && s.quotation_deleted !== true,
      created_by: s.created_by || '',
      created_at: s.created_at || '',
      configNames: bom.map((c) => c.name).filter(Boolean).join(' / ') || '—',
      totalQty: bom.reduce((sum, cfg) => sum + Number(cfg.qty || 0), 0),
      totalCost,
      cost_configs: cost,
    }
  }),
)
const sheetDetail = ref<{ name: string; configs: CostConfig[] } | null>(null)
function openSheetDetail(name: string, configs: CostConfig[]) {
  sheetDetail.value = { name, configs }
}
// 成本表明细 → 通用配置明细组件的归一化映射（成本视角：单价/小计/备注，无售价利润率）
const sheetDetailConfigs = computed(() => {
  if (!sheetDetail.value) return []
  return (sheetDetail.value.configs || []).map((cfg) => {
    const t = cfg.totals || {}
    const l6 = cfg.l6_items || []
    const kp = cfg.kp_items || []
    const rows: { group: string; groupSpan?: number; catalogue: string; description: string; qty: string; cells: [string, string, string] }[] = []
    if (l6.length) {
      l6.forEach((it: any, i: number) => rows.push({
        group: 'L6',
        groupSpan: i === 0 ? l6.length : undefined,
        catalogue: it.catalogue || '—',
        description: it.description || '',
        qty: String(it.qty ?? '—'),
        cells: ['—', '—', '—'],
      }))
    } else {
      rows.push({ group: 'L6', groupSpan: 1, catalogue: '机箱 (L6) 汇总', description: '—', qty: '—', cells: [money(t.l6Cost), '—', '—'] })
    }
    kp.forEach((it: any, i: number) => rows.push({
      group: 'KP',
      groupSpan: i === 0 ? kp.length : undefined,
      catalogue: it.cat || it.part_category || '—',
      description: it.name || it.catalogue || '',
      qty: String(it.qty ?? '—'),
      cells: [money(it.cost), money(Number(it.cost || 0) * Number(it.qty || 0)), it.note || '—'],
    }))
    return {
      key: String(cfg.name),
      tab: cfg.name,
      summary: [
        { label: '配置名', value: cfg.name },
        ...(cfg.server_model ? [{ label: '机型型号', value: cfg.server_model }] : []),
        { label: '描述', value: cfg.description || '—', wide: true },
        { label: '数量', value: `${cfg.qty || 0} 台` },
      ],
      metricHeaders: ['单价', '小计', '备注'] as [string, string, string],
      rows,
      totals: [
        { label: 'L6 成本合计', value: money(t.l6Cost) },
        { label: 'KP 成本合计', value: money(t.kpCost) },
        { label: '整机成本合计', value: money(t.totalCost) },
      ],
    }
  })
})
function sheetState(sheet: WorktableSheetView): string {
  if (sheet.quotation_deleted) return '报价单已删'
  if (sheet.quotation_exported) return '已正式报价'
  if (sheet.converted) return '已生成报价草稿'
  return '待转报价'
}
function sheetBadgeClass(sheet: WorktableSheetView): string {
  if (sheet.quotation_deleted || sheet.converted) return 'rt-badge-draft'
  if (sheet.quotation_exported) return 'rt-badge-exported'
  return 'rt-badge-current'
}
const costTableColumns: { label: string; width?: string; align?: 'left' | 'right' | 'center' }[] = [
  { label: '创建人 / 时间', width: '180px' },
  { label: '成本表', width: '190px' },
  { label: '配置' },
  { label: '台数', width: '70px', align: 'right' },
  { label: '整机成本', width: '110px', align: 'right' },
  { label: '状态', width: '120px' },
  { label: '操作', width: '200px', align: 'right' },
]
const costTotals = computed(() => {
  const snap = props.quoteContext?.cost_snapshot?.totals
  if (snap) return { totalCost: snap.totalCost || 0 }
  if (!costConfigs.value.length) return null
  let totalCost = 0
  for (const cfg of costConfigs.value) {
    totalCost += Number(cfg.totals?.totalCost || 0) * Number(cfg.qty || 0)
  }
  return { totalCost }
})
const totalQty = computed(() => bomConfigs.value.reduce((sum, cfg) => sum + Number(cfg.qty || 0), 0))
// 面板折叠态受控于 board（按节点待办规则给默认值），本地仅透传变更
const upstreamOpen = computed({
  get: () => props.upstreamOpen,
  set: (v) => emit('update:upstreamOpen', v),
})
const quoteOpen = computed({
  get: () => props.quoteOpen,
  set: (v) => emit('update:quoteOpen', v),
})
const selectedIds = computed<Set<string>>(() => new Set(props.quoteSelectedIds || []))

const auth = useAuthStore()
const canSubmitQuote = computed(() => auth.can('action.flow.submit.quoting'))
// 解冻已导出报价单（「用户与权限」页可分配 action.quote.unfreeze）；已发送的单需先退回审批节点
const canUnfreezeQuote = computed(() => auth.can('action.quote.unfreeze'))
const flowCards = computed(() => props.board.flow_cards || [])

function cardFor(type: FlowCard['entities'][number]['entity_type'], entityId: string | null | undefined): FlowCard | undefined {
  if (!entityId) return undefined
  return flowCards.value.find((card) => card.entities.some((e) => e.entity_type === type && e.entity_id === String(entityId)))
}
function onQuoteMore(key: string, q: Quotation) {
  if (key === 'send') { openSend(q); return }
  if (key === 'view') { openQuotation(q); return }
  if (key === 'share') { shareTarget.value = q; shareOpen.value = true; return }
  if (key === 'unfreeze') { emit('unfreeze-quotation', q); return }
  if (key === 'reparse') { emit('reparse-quotation', q); return }
  if (key === 'primary') { emit('set-primary', q); return }
  if (key === 'rename') { emit('rename-quotation', q); return }
  if (key === 'delete') { emit('delete-quotation', q.quotation_id); return }
}
function quoteState(q: Quotation): string {
  if (q.submitted_at) return '报价单已出'
  if (q.exported_at) {
    const ap = latestApprovalFor(q.quotation_id)
    if (ap?.status === 'pending') return '外发审批中'
    if (ap?.status === 'rejected') return '外发审批被驳回'
    return '已导出'
  }
  return '草稿'
}
function quoteStateClass(q: Quotation): 'draft' | 'exported' | 'released' | 'approving' {
  if (q.submitted_at) return 'released'
  if (q.exported_at) {
    const ap = latestApprovalFor(q.quotation_id)
    if (ap?.status === 'pending') return 'approving'
    return 'exported'
  }
  return 'draft'
}

const sendTarget = ref<Quotation | null>(null)
const sendComment = ref('')
const sendAttachmentId = ref('')
const sendSaving = ref(false)
// 低毛利审批：per-quotation 最新审批单状态（pending=审批中拦截发送 / rejected=驳回 / approved=放行）
const pricingApprovals = ref<PricingApproval[]>([])
async function loadPricingApprovals() {
  if (!opportunityId.value) return
  try {
    const res = await portalApi.oppPricingApprovals(opportunityId.value)
    pricingApprovals.value = res.approvals || []
  } catch {
    pricingApprovals.value = []
  }
}
onMounted(loadPricingApprovals)
watch(opportunityId, loadPricingApprovals)
function latestApprovalFor(quotationId: string): PricingApproval | undefined {
  return pricingApprovals.value.find((a) => a.quotation_id === quotationId)
}
// 审批裁决（总监/管理员）：通知直达详情页后在此批准/驳回
const canApprovePricing = computed(() => auth.can('action.flow.approve.pricing'))
const pendingApprovals = computed(() => pricingApprovals.value.filter((a) => a.status === 'pending'))
const decidingId = ref<number | null>(null)
async function decidePricing(a: PricingApproval, decision: 'approve' | 'reject') {
  decidingId.value = a.id
  try {
    await portalApi.decidePricingApproval(opportunityId.value, a.id, { decision })
    message.success(decision === 'approve' ? '已批准，报价员可发送该报价单' : '已驳回并通知报价员')
    await loadPricingApprovals()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '操作失败')
  } finally {
    decidingId.value = null
  }
}
function rejectPricing(a: PricingApproval) {
  confirmWithReason({
    title: `驳回外发审批（${a.opportunity_id}）？`,
    hint: `当前毛利率 ${Number(a.margin_pct).toFixed(2)}%${a.trigger_reason === 'low_margin' ? `，红线 ${a.threshold}%。` : '。'}`,
    okText: '驳回',
    placeholder: '请填写驳回意见（必填），让报价员知道如何调整',
    async onOk(reason: string) {
      await portalApi.decidePricingApproval(opportunityId.value, a.id, { decision: 'reject', comment: reason })
      message.success('已驳回并通知报价员')
      await loadPricingApprovals()
    },
  })
}

// ── 转交（责任人/管理员把审批单转给其他总监，内容指纹不变） ──
const transferFor = ref<PricingApproval | null>(null)
const transferTarget = ref('')
const transferReason = ref('')
const transferSaving = ref(false)
const approverOptions = ref<Array<{ label: string; value: string }>>([])
async function openTransfer(a: PricingApproval) {
  transferFor.value = a
  transferTarget.value = ''
  transferReason.value = ''
  if (!approverOptions.value.length) {
    try {
      const res = await portalApi.pricingApprovalApprovers()
      approverOptions.value = (res.approvers || [])
        .filter((x) => x.user_id)
        .map((x) => ({ label: x.name, value: x.name }))
    } catch { /* 拉不到候选时保留空选，提交时后端兜底校验 */ }
  }
}
async function submitTransfer() {
  if (!transferFor.value) return
  if (!transferTarget.value) {
    message.warning('请选择转交目标总监')
    return
  }
  transferSaving.value = true
  try {
    await portalApi.reassignPricingApproval(opportunityId.value, transferFor.value.id, {
      to_name: transferTarget.value,
      reason: transferReason.value.trim() || undefined,
    })
    message.success('已转交')
    transferFor.value = null
    await loadPricingApprovals()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '转交失败')
  } finally {
    transferSaving.value = false
  }
}
function waitedText(a: PricingApproval): string {
  const ms = Date.now() - new Date(a.created_at).getTime()
  if (!isFinite(ms) || ms < 0) return ''
  const hours = ms / 3600000
  return hours < 1 ? `${Math.max(1, Math.round(ms / 60000))} 分钟`
    : hours < 48 ? `${Math.floor(hours)} 小时` : `${Math.floor(hours / 24)} 天`
}

// ── 发送撞外发审批闸 → 原地弹发起窗（公共组件） ──
const gateModalOpen = ref(false)
const gateModalQuotation = ref<Quotation | null>(null)

// ── 产出物分享（报价单行菜单） ──
import ShareDialog from '@/components/opportunity/ShareDialog.vue'
const shareOpen = ref(false)
const shareTarget = ref<Quotation | null>(null)
const sendAttachments = computed(() =>
  (props.attachments || []).filter(
    (a) => a.category === 'sent_quote' && a.quotation_id === sendTarget.value?.quotation_id && a.kind === 'export',
  ),
)
function openSend(q: Quotation) {
  sendTarget.value = q
  sendComment.value = ''
  const atts = (props.attachments || []).filter(
    (a) => a.category === 'sent_quote' && a.quotation_id === q.quotation_id && a.kind === 'export',
  )
  sendAttachmentId.value = atts[0]?.attachment_id || ''
}
async function submitSend() {
  if (!sendTarget.value) return
  if (!sendAttachmentId.value) {
    message.warning('请先选择要发送的 Excel 报价附件')
    return
  }
  sendSaving.value = true
  try {
    await portalApi.submitQuote(opportunityId.value, sendTarget.value.quotation_id, {
      attachment_id: sendAttachmentId.value,
      comment: sendComment.value.trim() || undefined,
    })
    message.success('报价单已发送')
    sendTarget.value = null
    emit('refresh-quotations')
  } catch (e: any) {
    const detail: string = e?.response?.data?.detail || '发送失败'
    if (e?.response?.status === 409) {
      // 外发审批闸：无有效许可 → 直接弹发起窗（与导出口同一公共弹窗），不再让用户自己去工作台找入口
      const target = sendTarget.value
      message.info(detail)
      sendTarget.value = null
      gateModalQuotation.value = target
      gateModalOpen.value = true
      loadPricingApprovals()
    } else {
      message.error(detail)
    }
  } finally {
    sendSaving.value = false
  }
}
function openQuotation(q: Quotation) {
  emit('view-quotation', q)
}
function returnQuoteToCost(quotationId: string, label: string) {
  const card = cardFor('quote', quotationId)
  if (!card) return
  confirmWithReason({
    title: `退回「${label}」？`,
    hint: '退回后这张卡会回到成本核算节点，需要重新核价后再提交。',
    okText: '退回',
    placeholder: '请填写退回原因（必填），让对方知道需要修改什么',
    async onOk(reason) {
      await portalApi.returnCard(opportunityId.value, card.id, reason)
      message.success('已退回成本核算')
      emit('refresh-quotations')
    },
  })
}
</script>

<template>
  <div class="quote-workbench">
    <div class="qw-body">
      <section class="qw-context panel">
        <header class="card-shell-head card-head-toggle" @click="upstreamOpen = !upstreamOpen">
          <div class="card-shell-title">
            <span class="rich-icon-badge"><CalculatorOutlined /></span>
            <div>
              <span class="card-shell-eyebrow">成本引用</span>
              <h3>上游成本与 BOM 摘要</h3>
            </div>
          </div>
          <div class="qw-shell-actions" @click.stop>
            <button class="card-chevron" :class="{ collapsed: !upstreamOpen }" type="button" @click.stop="upstreamOpen = !upstreamOpen">
              <UpOutlined />
            </button>
          </div>
        </header>
        <div class="card-collapse" :class="{ collapsed: !upstreamOpen }">
          <div class="card-collapse-inner">

        <!-- 已提交成本表逐张一行：名称/配置/台数/整机成本/状态进表，与报价单列表同形 -->
        <RecordTable
          v-if="worktableSheetViews.length"
          :empty="!worktableSheetViews.length"
          empty-text="成本核算尚未完成，暂无可用于报价的成本表。"
          :columns="costTableColumns"
        >
          <tr
            v-for="sheet in worktableSheetViews"
            :key="sheet.sheet_id"
            @click="openSheetDetail(sheet.sheet_name, sheet.cost_configs)"
          >
            <td class="rt-dim" data-label="创建人 / 时间">{{ sheet.created_by || '—' }} · {{ (sheet.created_at || '').slice(5, 16) }}</td>
            <td><span class="rt-strong" :title="sheet.sheet_name">{{ sheet.sheet_name }}</span></td>
            <td class="rt-dim" data-label="配置">{{ sheet.configNames }}</td>
            <td class="rt-num" data-label="台数">{{ sheet.totalQty }}</td>
            <td class="rt-num" data-label="整机成本">{{ sheet.totalCost != null ? money(sheet.totalCost) : '—' }}</td>
            <td data-label="状态"><span class="rt-badge" :class="sheetBadgeClass(sheet)">{{ sheetState(sheet) }}</span></td>
            <td>
              <div class="rt-actions">
                <span class="rt-link" @click.stop="openSheetDetail(sheet.sheet_name, sheet.cost_configs)">查看明细</span>
                <span
                  v-if="canSubmitQuote && !sheet.converted && !sheet.quotation_exported && !sheet.quotation_deleted"
                  class="rt-link"
                  :class="{ muted: !sheet.canConvert }"
                  @click.stop="sheet.canConvert && emit('convert-cost-to-quotation', sheet.quotation_id)"
                >转为报价草稿</span>
                <span
                  v-if="!sheet.converted && cardFor('quote', sheet.quotation_id)?.current_node === 'quoting'"
                  class="rt-link"
                  @click.stop="returnQuoteToCost(sheet.quotation_id, sheet.sheet_name)"
                >退回成本表</span>
                <span v-if="sheet.quotation_deleted" class="rt-link danger" @click.stop="emit('delete-cost-sheet', sheet.sheet_id)">删除成本表</span>
              </div>
            </td>
          </tr>
        </RecordTable>

        <!-- 旧版兜底：无 worktable 成本表时，worktable 快照同样收敛为单行成本表 -->
        <RecordTable
          v-else
          :empty="!costConfigs.length && !worktableQuotationId"
          empty-text="成本核算尚未完成，暂无可用于报价的成本表。"
          :columns="costTableColumns"
        >
          <tr v-if="costConfigs.length || worktableQuotationId" @click="costConfigs.length && openSheetDetail('当前成本表', costConfigs)">
            <td class="rt-dim" data-label="创建人 / 时间">—</td>
            <td><span class="rt-strong">当前成本表</span></td>
            <td class="rt-dim" data-label="配置">{{ bomConfigs.map((c) => c.name).filter(Boolean).join(' / ') || '—' }}</td>
            <td class="rt-num" data-label="台数">{{ totalQty }}</td>
            <td class="rt-num" data-label="整机成本">{{ costTotals ? money(costTotals.totalCost) : '—' }}</td>
            <td data-label="状态">
              <span class="rt-badge" :class="convertedQuotation ? 'rt-badge-draft' : 'rt-badge-current'">{{ convertedQuotation ? '已生成报价草稿' : '待转报价' }}</span>
            </td>
            <td>
              <div class="rt-actions">
                <span v-if="costConfigs.length" class="rt-link" @click.stop="openSheetDetail('当前成本表', costConfigs)">查看明细</span>
                <span
                  v-if="canSubmitQuote && worktableQuotationId && !convertedQuotation"
                  class="rt-link"
                  :class="{ muted: !canConvert }"
                  @click.stop="worktableQuotationId && canConvert && emit('convert-cost-to-quotation', worktableQuotationId)"
                >转为报价草稿</span>
                <span
                  v-if="worktableQuotationId && !convertedQuotation && cardFor('quote', worktableQuotationId)?.current_node === 'quoting'"
                  class="rt-link"
                  @click.stop="returnQuoteToCost(worktableQuotationId, '当前成本表')"
                >退回成本表</span>
              </div>
            </td>
          </tr>
        </RecordTable>
          </div>
        </div>
      </section>

      <!-- 左栏小节点锚点：quoting.0=报价单工作区 / quoting.1=报价附件（抽屉） -->
      <section class="qw-editor panel" data-substep="quoting.0 quoting.1">
        <header class="card-shell-head card-head-toggle" @click="quoteOpen = !quoteOpen">
          <div class="card-shell-title">
            <span class="rich-icon-badge"><FileDoneOutlined /></span>
            <div>
              <span class="card-shell-eyebrow">市场报价</span>
              <h3>报价单工作区</h3>
            </div>
          </div>
          <div class="qw-shell-actions" @click.stop>
            <div class="qw-actions">
              <a-button size="small" @click="quoteSelectMode ? emit('exit-quote-batch') : emit('enter-quote-batch')">
                {{ quoteSelectMode ? '取消' : '批量操作' }}
              </a-button>
              <AttachmentUploadButton :opportunity-id="opportunityId" category="sent_quote" label="上传报价" />
              <a-button size="small" @click="emit('open-archive', { categories: ['sent_quote'], title: '报价附件' })">报价附件</a-button>
              <a-button size="small" type="primary" @click="emit('new-quotation')">新增报价</a-button>
            </div>
            <button class="card-chevron" :class="{ collapsed: !quoteOpen }" type="button" @click.stop="quoteOpen = !quoteOpen">
              <UpOutlined />
            </button>
          </div>
        </header>
        <div class="card-collapse" :class="{ collapsed: !quoteOpen }">
          <div class="card-collapse-inner">

        <div v-if="quoteSelectMode" class="qw-batch">
          <a-button danger size="small" @click="emit('batch-delete-quotes')">
            删除选中 ({{ selectedIds.size }})
          </a-button>
        </div>

        <div v-if="canApprovePricing && pendingApprovals.length" class="qw-approval-bar">
          <div class="qw-approval-info">
            <AuditOutlined class="qw-approval-icon" />
            <span class="qw-approval-title">报价外发审批</span>
            <span class="qw-approval-count">{{ pendingApprovals.length }} 单</span>
          </div>
          <div class="qw-approval-list">
            <div v-for="a in pendingApprovals" :key="a.id" class="qw-approval-item">
              <span class="qw-approval-quotation" :title="a.quotation_id">{{ a.quotation_id }}</span>
              <span class="qw-approval-margin">毛利率 {{ Number(a.margin_pct).toFixed(2) }}%<template v-if="a.trigger_reason === 'low_margin'"> &lt; 红线 {{ a.threshold }}%</template></span>
              <span class="qw-approval-assignee">责任人 {{ a.assigned_name || '全体审批人（先到先批）' }} · 已等待 {{ waitedText(a) }}</span>
              <a-button size="small" @click="openTransfer(a)">转交</a-button>
              <a-button
                size="small"
                type="primary"
                :loading="decidingId === a.id"
                @click="decidePricing(a, 'approve')"
              >批准</a-button>
              <a-button
                size="small"
                danger
                :disabled="decidingId === a.id"
                @click="rejectPricing(a)"
              >驳回</a-button>
            </div>
          </div>
        </div>

        <!-- 转交审批弹窗：选目标总监 + 理由（转交链留痕，内容指纹不变） -->
        <a-modal
          :open="!!transferFor"
          title="转交审批"
          centered
          :width="MODAL_WIDTH.action"
          wrap-class-name="portal-sheet-modal"
          :z-index="hostZIndex"
          @cancel="transferFor = null"
        >
          <div style="display: flex; flex-direction: column; gap: 10px; padding-top: 8px;">
            <div class="qw-transfer-hint">将审批单 #{{ transferFor?.id }}（{{ transferFor?.quotation_id }}）转交给其他总监，内容指纹不变；转交记录全程留痕。</div>
            <a-select
              v-model:value="transferTarget"
              :options="approverOptions"
              placeholder="选择目标总监"
              style="width: 100%"
            />
            <a-input v-model:value="transferReason" placeholder="转交理由（可选）" />
          </div>
          <template #footer>
            <a-button @click="transferFor = null">取消</a-button>
            <a-button type="primary" :loading="transferSaving" @click="submitTransfer">确认转交</a-button>
          </template>
        </a-modal>

        <!-- 发送撞外发审批闸：原地发起审批（与工作台导出口同一公共弹窗） -->
        <OutboundApprovalModal
          v-model:open="gateModalOpen"
          :opportunity-id="opportunityId"
          :quotation-id="gateModalQuotation?.quotation_id || ''"
          :quotation-label="gateModalQuotation?.quotation_name || gateModalQuotation?.quotation_id || ''"
          :z-index="hostZIndex"
          @submitted="loadPricingApprovals"
        />

        <!-- 产出物分享（网盘式链接） -->
        <ShareDialog
          v-model:open="shareOpen"
          :opportunity-id="opportunityId"
          source-type="quote"
          :source-id="shareTarget?.quotation_id || ''"
          :title="shareTarget?.quotation_name || shareTarget?.quotation_id || ''"
          default-view="customer"
          :z-index="hostZIndex"
        />

        <RecordTable
          :empty="!visibleQuotations.length"
          empty-text="暂无报价单，请上传或新增报价。"
          :columns="[
            { label: '创建人 / 时间', width: '180px' },
            { label: '报价单', width: '240px' },
            { label: '单号', width: '160px' },
            { label: '状态', width: '110px' },
            { label: '总价', width: '110px', align: 'right' },
            { label: '利润率', width: '90px', align: 'right' },
            { label: '配置', width: '80px', align: 'right' },
            { label: '操作', width: '90px', align: 'right' },
          ]"
        >
          <tr
            v-for="q in visibleQuotations"
            :key="q.quotation_id"
            @click="quoteSelectMode ? emit('toggle-quote-select', q.quotation_id) : openQuotation(q)"
          >
            <td class="rt-dim" data-label="创建人 / 时间">{{ q.created_by || '—' }} · {{ (q.created_at || '').slice(5, 16) }}</td>
            <td>
              <span class="rt-strong rt-q-title" :title="q.quotation_name || '未命名报价单'">{{ q.quotation_name || '未命名报价单' }}</span>
              <span v-if="q.is_primary" class="rt-sub">当前为主推报价单</span>
            </td>
            <td class="rt-dim" data-label="单号"><span class="rt-q-id" :title="q.quotation_id">{{ q.quotation_id }}</span></td>
            <td data-label="状态"><span class="rt-badge" :class="`rt-badge-${quoteStateClass(q)}`">{{ quoteState(q) }}</span></td>
            <td class="rt-num" data-label="总价">{{ quotePriceVisible ? money(q.total_price) : '***' }}</td>
            <td class="rt-num" data-label="利润率">{{ quotePriceVisible ? Number(q.profit_margin || 0).toFixed(2) + '%' : '***' }}</td>
            <td class="rt-num" data-label="配置">{{ q.config_count || 0 }} 配置</td>
            <td>
              <div class="rt-actions">
                <a-checkbox
                  v-if="quoteSelectMode"
                  :checked="selectedIds.has(q.quotation_id)"
                  @click.stop
                  @change="emit('toggle-quote-select', q.quotation_id)"
                />
                <a-dropdown v-if="!quoteSelectMode" :get-popup-container="popupContainer || undefined" @click.stop>
                  <a-button size="small" type="link" class="qw-more">更多<DownOutlined /></a-button>
                  <template #overlay>
                    <a-menu @click="({ key }: { key: string }) => onQuoteMore(key, q)">
                      <a-menu-item v-if="canSubmitQuote && q.exported_at && !q.submitted_at" key="send">发送</a-menu-item>
                      <a-menu-item key="view">{{ q.submitted_at ? '查看已发送' : (q.exported_at ? '查看成本' : '编辑') }}</a-menu-item>
                      <a-menu-item key="share">分享</a-menu-item>
                      <a-menu-item v-if="canUnfreezeQuote && q.exported_at && !q.submitted_at" key="unfreeze">解冻并编辑</a-menu-item>
                      <a-menu-item v-if="q.exported_at" key="reparse">复制为草稿</a-menu-item>
                      <a-menu-item key="primary">{{ q.is_primary ? '取消主推' : '设为主推' }}</a-menu-item>
                      <a-menu-item key="rename">重命名</a-menu-item>
                      <a-menu-item key="delete" danger>删除</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
            </td>
          </tr>
        </RecordTable>
          </div>
        </div>
      </section>
    </div>

    <a-modal
      :open="!!sendTarget"
      :title="`发送报价单 · ${sendTarget?.quotation_name || ''}`"
      :footer="null"
      centered
      :width="MODAL_WIDTH.action"
      wrap-class-name="portal-sheet-modal"
      :z-index="hostZIndex"
      @cancel="sendTarget = null"
    >
      <div class="qw-send-modal">
        <p class="qw-send-tip">选择要推送到报价单审批节点的 Excel 文件，并填写发送评论。</p>
        <div class="qw-send-field">
          <label>Excel 报价附件</label>
          <a-select v-model:value="sendAttachmentId" placeholder="请选择已导出的 Excel" style="width: 100%">
            <a-select-option v-for="att in sendAttachments" :key="att.attachment_id" :value="att.attachment_id">
              {{ att.original_filename }} · {{ fmtTime(att.created_at) }}
            </a-select-option>
          </a-select>
        </div>
        <div class="qw-send-field">
          <label>发送评论</label>
          <a-textarea v-model:value="sendComment" :rows="3" placeholder="例如：请业务确认此版本报价，本周五前回复。" />
        </div>
        <div class="qw-send-actions">
          <a-button @click="sendTarget = null">取消</a-button>
          <a-button type="primary" :loading="sendSaving" @click="submitSend">确认发送</a-button>
        </div>
      </div>
    </a-modal>

    <ResponsiveModal
      :open="!!sheetDetail"
      :title="`成本表明细 · ${sheetDetail?.name || ''}`"
      tier="sheet"
      :footer="null"
      centered
      wrap-class-name="portal-sheet-modal"
      :z-index="hostZIndex"
      @cancel="sheetDetail = null"
    >
      <GroupedConfigDetail v-if="sheetDetail && sheetDetailConfigs.length" :configs="sheetDetailConfigs" />
      <div v-else-if="sheetDetail" class="panel-empty">该成本表暂无配置明细。</div>
    </ResponsiveModal>
  </div>
</template>

<style scoped>
.quote-workbench {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: calc(100vh - 260px);
}


.qw-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  min-height: 0;
}
.panel {
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
/* 卡头公共配方（card-head-toggle / card-shell-* / card-chevron / card-collapse / rich-icon-badge）
   由文件底部的 <style scoped src="./card-shell.css"> 提供，此处只留报价工作台私有样式 */
.qw-shell-actions {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}
.panel-empty { padding: 22px 13px; text-align: center; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }
.qw-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.qw-batch { padding: 10px 13px; border-bottom: 1px solid var(--cpq-glass-border); }

.qw-approval-bar {
  margin: 0 0 12px;
  padding: 10px 14px;
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-warn-surface);
  border: 1px solid var(--cpq-warn-border);
}
.qw-approval-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.qw-approval-icon { color: var(--cpq-notif-amber); font-size: 15px; }
.qw-approval-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.qw-approval-count {
  font-size: var(--cpq-font-size-xs);
  padding: 1px 8px;
  border-radius: var(--cpq-radius-full);
  background: var(--cpq-notif-amber-bg);
  color: var(--cpq-notif-amber);
}
.qw-approval-list { display: flex; flex-direction: column; gap: 6px; }
.qw-approval-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;          /* 手机端：单号/毛利/责任人换行不挤出屏 */
  gap: 6px 10px;
  padding: 7px 10px;
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-bg-card);
  border: 1px solid var(--cpq-border-secondary);
}
.qw-approval-assignee {
  flex-basis: 100%;         /* 责任人/等待信息独占一行（窄屏不与按钮抢位） */
  font-size: var(--cpq-font-size-xs);
  color: var(--cpq-text-muted);
}
.qw-approval-item :deep(.ant-btn) {
  flex-shrink: 0;
}
.qw-approval-quotation {
  font-size: var(--cpq-font-size-sm);
  font-weight: 600;
  color: var(--cpq-text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.qw-approval-margin {
  flex: 1;
  font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-secondary);
}
.qw-transfer-hint {
  font-size: var(--cpq-font-size-sm);
  line-height: 1.6;
  color: var(--cpq-text-muted);
}
.qw-send-modal { display: flex; flex-direction: column; gap: 14px; }
.qw-send-tip { margin: 0; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); line-height: 1.6; }
.qw-send-field { display: flex; flex-direction: column; gap: 7px; }
.qw-send-field label { color: var(--cpq-text-primary); font-size: var(--cpq-font-size-sm); font-weight: 600; }
.qw-send-actions { display: flex; justify-content: flex-end; gap: 8px; }

.rt-num { text-align: right; }
.rt-q-title, .rt-q-id { display: block; word-break: break-word; white-space: normal; min-width: 0; }

@media (max-width: 768px) {
  /* ── 卡头紧凑双行：card-shell-* 公共部分在 card-shell.css 同断点里；
     这里只放报价工作台私有部分。上传报价是 AttachmentUploadButton 壳
     （span.attachment-upload-btn），order/分宽落直接子项，壳转 flex 内层按钮撑满 ── */
  .qw-shell-actions,
  .qw-actions {
    display: contents;
  }
  .qw-shell-actions .card-chevron,
  .qw-actions .card-chevron {
    order: 4;
    flex: 0 0 auto;
  }
  .qw-shell-actions > *,
  .qw-actions > * {
    order: 3;
    flex: 1 1 0;
    min-width: 0;
    min-height: 24px;
  }
  .qw-shell-actions .ant-btn {
    padding: 0 8px;
    font-size: var(--cpq-font-size-xs);
  }
  .qw-actions > .attachment-upload-btn {
    display: flex;
  }
  .qw-actions > .attachment-upload-btn .ant-btn {
    flex: 1 1 auto;
    width: auto;
  }
  /* 长单号不再逐字竖排：溢出省略，全量见详情 */
  .rt-q-id {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .card-collapse-inner {
    overflow-x: auto;
  }
}

@media (max-width: 900px) {
  .qw-body { grid-template-columns: 1fr; }
}
</style>

<style scoped src="./card-shell.css"></style>
