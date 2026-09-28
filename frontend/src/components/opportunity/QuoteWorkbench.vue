<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { confirmWithReason } from './confirmWithReason'
import { AuditOutlined, CalculatorOutlined, DownOutlined, FileDoneOutlined, UpOutlined } from '@ant-design/icons-vue'
import type { BomConfig, CostConfig, FlowCard, PortalBoard, PricingApproval, QuoteContext } from '@/api/portal'
import type { Quotation } from '@/types/opportunity'
import type { FeedAttachment } from '@/api/feed'
import { portalApi } from '@/api/portal'
import { useAuthStore } from '@/store/auth'
import { fmtTime, formatDate as formatQuoteDate, money } from '@/utils/quoteCommon'
import RecordTable from '@/components/opportunity/RecordTable.vue'
import AttachmentUploadButton from '@/components/opportunity/AttachmentUploadButton.vue'

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
  configNames: string
  totalQty: number
  totalCost: number | null
  bom_configs: BomConfig[]
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
      configNames: bom.map((c) => c.name).filter(Boolean).join(' / ') || '—',
      totalQty: bom.reduce((sum, cfg) => sum + Number(cfg.qty || 0), 0),
      totalCost,
      bom_configs: bom,
      cost_configs: cost,
    }
  }),
)
const configDetail = ref<CostConfig | null>(null)
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
  if (key === 'unfreeze') { emit('unfreeze-quotation', q); return }
  if (key === 'primary') { emit('set-primary', q); return }
  if (key === 'rename') { emit('rename-quotation', q); return }
  if (key === 'delete') { emit('delete-quotation', q.quotation_id); return }
}
function quoteState(q: Quotation): string {
  if (q.submitted_at) return '报价单已出'
  if (q.exported_at) {
    const ap = latestApprovalFor(q.quotation_id)
    if (ap?.status === 'pending') return '低毛利审批中'
    if (ap?.status === 'rejected') return '审批被驳回'
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
    title: `驳回低毛利审批（${a.opportunity_id}）？`,
    hint: `当前毛利率 ${Number(a.margin_pct).toFixed(2)}%，红线 ${a.threshold}%。`,
    okText: '驳回',
    placeholder: '请填写驳回意见（必填），让报价员知道如何调整',
    async onOk(reason: string) {
      await portalApi.decidePricingApproval(opportunityId.value, a.id, { decision: 'reject', comment: reason })
      message.success('已驳回并通知报价员')
      await loadPricingApprovals()
    },
  })
}
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
      // 低毛利审批门：审批单已建，刷新徽标并收起发送弹窗
      message.warning(detail)
      sendTarget.value = null
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
function openConfigDetail(cfg: CostConfig) {
  configDetail.value = cfg
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
            <a-button
              v-if="canSubmitQuote && !worktableSheetViews.length && worktableQuotationId"
              size="small"
              type="primary"
              :disabled="!canConvert"
              @click="emit('convert-cost-to-quotation', worktableQuotationId)"
            >
              {{ convertedQuotation ? '已生成报价草稿' : '转为报价草稿' }}
            </a-button>
            <a-button
              v-if="!worktableSheetViews.length && worktableQuotationId && !convertedQuotation && cardFor('quote', worktableQuotationId)?.current_node === 'quoting'"
              size="small"
              @click="returnQuoteToCost(worktableQuotationId, '当前成本表')"
            >
              退回成本表
            </a-button>
            <button class="card-chevron" :class="{ collapsed: !upstreamOpen }" type="button" @click.stop="upstreamOpen = !upstreamOpen">
              <UpOutlined />
            </button>
          </div>
        </header>
        <div class="card-collapse" :class="{ collapsed: !upstreamOpen }">
          <div class="card-collapse-inner">

        <!-- 多张已提交成本表：每张独立渲染，逐张可转正式报价 -->
        <template v-if="worktableSheetViews.length">
          <div v-for="sheet in worktableSheetViews" :key="sheet.sheet_id" class="qw-sheet-block">
            <div class="qw-sheet-head">
              <span class="qw-sheet-title">{{ sheet.sheet_name }}</span>
              <a-button
                v-if="sheet.quotation_deleted"
                size="small"
                disabled
              >
                报价单已删
              </a-button>
              <a-button
                v-else-if="canSubmitQuote"
                size="small"
                type="primary"
                :disabled="!sheet.canConvert"
                @click="emit('convert-cost-to-quotation', sheet.quotation_id)"
              >
                {{ sheet.quotation_exported ? '已正式报价' : (sheet.converted ? '已生成报价草稿' : '转为报价草稿') }}
              </a-button>
              <a-button
                v-if="!sheet.converted && cardFor('quote', sheet.quotation_id)?.current_node === 'quoting'"
                size="small"
                @click="returnQuoteToCost(sheet.quotation_id, sheet.sheet_name)"
              >
                退回成本表
              </a-button>
              <span v-if="sheet.quotation_deleted" class="qw-delete-link" @click="emit('delete-cost-sheet', sheet.sheet_id)">删除成本表</span>
            </div>
            <table v-if="sheet.cost_configs.length" class="qw-cost-table">
              <thead>
                <tr><th>Config</th><th>Quantity</th><th>Total Cost</th><th>Details</th></tr>
              </thead>
              <tbody>
                <tr v-for="cfg in sheet.cost_configs" :key="cfg.name" class="qw-config-row" @click="openConfigDetail(cfg)">
                  <td>{{ cfg.name }}</td>
                  <td>{{ cfg.qty }}</td>
                  <td>{{ money(cfg.totals?.totalCost) }}</td>
                  <td><a-button size="small" type="link" @click.stop="openConfigDetail(cfg)">查看明细</a-button></td>
                </tr>
              </tbody>
              <tfoot v-if="sheet.cost_configs.length > 1">
                <tr class="qw-total-row">
                  <td colspan="2">合计 {{ sheet.totalQty }} 台</td>
                  <td>{{ sheet.totalCost != null ? money(sheet.totalCost) : '—' }}</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </template>

        <!-- 旧版兜底：无 worktable 成本表时展示单一当前成本摘要 -->
        <template v-else>
          <div class="qw-summary">
            <div><small>配置</small><b>{{ bomConfigs.map((c) => c.name).join(' / ') || '—' }}</b></div>
            <div><small>总台数</small><b>{{ totalQty }}</b></div>
            <div><small>整机成本</small><b>{{ costTotals ? money(costTotals.totalCost) : '—' }}</b></div>
          </div>
          <table v-if="costConfigs.length" class="qw-cost-table">
            <thead>
              <tr><th>Config</th><th>Quantity</th><th>Total Cost</th><th>Details</th></tr>
            </thead>
            <tbody>
              <tr v-for="cfg in costConfigs" :key="cfg.name" class="qw-config-row" @click="openConfigDetail(cfg)">
                <td>{{ cfg.name }}</td>
                <td>{{ cfg.qty }}</td>
                <td>{{ money(cfg.totals?.totalCost) }}</td>
                <td><a-button size="small" type="link" @click.stop="openConfigDetail(cfg)">查看明细</a-button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="panel-empty">成本核算尚未完成，暂无可用于报价的成本表。</div>
        </template>
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
            <span class="qw-approval-title">待我审批的低毛利报价</span>
            <span class="qw-approval-count">{{ pendingApprovals.length }} 单</span>
          </div>
          <div class="qw-approval-list">
            <div v-for="a in pendingApprovals" :key="a.id" class="qw-approval-item">
              <span class="qw-approval-quotation" :title="a.quotation_id">{{ a.quotation_id }}</span>
              <span class="qw-approval-margin">毛利率 {{ Number(a.margin_pct).toFixed(2) }}% &lt; 红线 {{ a.threshold }}%</span>
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

        <RecordTable
          title="报价单"
          :empty="!visibleQuotations.length"
          empty-text="暂无报价单，请上传或新增报价。"
          :columns="[
            { label: '报价单', width: '240px' },
            { label: '单号', width: '160px' },
            { label: '状态', width: '110px' },
            { label: '总价', width: '110px', align: 'right' },
            { label: '利润率', width: '90px', align: 'right' },
            { label: '配置', width: '80px', align: 'right' },
            { label: '创建日期', width: '120px' },
            { label: '操作', width: '90px', align: 'right' },
          ]"
        >
          <tr
            v-for="q in visibleQuotations"
            :key="q.quotation_id"
            @click="quoteSelectMode ? emit('toggle-quote-select', q.quotation_id) : openQuotation(q)"
          >
            <td>
              <span class="rt-strong rt-q-title" :title="q.quotation_name || '未命名报价单'">{{ q.quotation_name || '未命名报价单' }}</span>
              <span v-if="q.is_primary" class="rt-sub">当前为主推报价单</span>
            </td>
            <td class="rt-dim"><span class="rt-q-id" :title="q.quotation_id">{{ q.quotation_id }}</span></td>
            <td><span class="rt-badge" :class="`rt-badge-${quoteStateClass(q)}`">{{ quoteState(q) }}</span></td>
            <td class="rt-num">{{ quotePriceVisible ? money(q.total_price) : '***' }}</td>
            <td class="rt-num">{{ quotePriceVisible ? Number(q.profit_margin || 0).toFixed(2) + '%' : '***' }}</td>
            <td class="rt-num">{{ q.config_count || 0 }} 配置</td>
            <td class="rt-dim">{{ formatQuoteDate(q.created_at) }}</td>
            <td>
              <div class="rt-actions">
                <a-checkbox
                  v-if="quoteSelectMode"
                  :checked="selectedIds.has(q.quotation_id)"
                  @click.stop
                  @change="emit('toggle-quote-select', q.quotation_id)"
                />
                <a-dropdown v-if="!quoteSelectMode" @click.stop>
                  <a-button size="small" type="link" class="qw-more">更多<DownOutlined /></a-button>
                  <template #overlay>
                    <a-menu @click="({ key }: { key: string }) => onQuoteMore(key, q)">
                      <a-menu-item v-if="canSubmitQuote && q.exported_at && !q.submitted_at" key="send">发送</a-menu-item>
                      <a-menu-item key="view">{{ q.submitted_at ? '查看已发送' : (q.exported_at ? '查看成本' : '编辑') }}</a-menu-item>
                      <a-menu-item v-if="canUnfreezeQuote && q.exported_at && !q.submitted_at" key="unfreeze">解冻并编辑</a-menu-item>
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
      :width="560"
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

    <a-modal
      :open="!!configDetail"
      :title="`配置明细 · ${configDetail?.name || ''}`"
      :footer="null"
      :width="760"
      @cancel="configDetail = null"
    >
      <div v-if="configDetail" class="qw-detail">
        <div class="qw-detail-grid">
          <div><small>Config</small><b>{{ configDetail.name }}</b></div>
          <div><small>Quantity</small><b>{{ configDetail.qty }}</b></div>
          <div><small>L6 Cost</small><b>{{ money(configDetail.totals?.l6Cost) }}</b></div>
          <div><small>Total Cost</small><b>{{ money(configDetail.totals?.totalCost) }}</b></div>
        </div>
        <p class="qw-detail-desc">{{ configDetail.description || '暂无描述' }}</p>

        <h4>L6</h4>
        <table v-if="configDetail.l6_items?.length" class="qw-detail-table">
          <thead>
            <tr><th>Catalogue</th><th>Configuration Description</th><th>Quantity</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in configDetail.l6_items" :key="idx">
              <td>{{ row.catalogue || '—' }}</td>
              <td>{{ row.description || '—' }}</td>
              <td>{{ row.qty }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="panel-empty">暂无 L6</div>

        <h4>KP</h4>
        <table v-if="configDetail.kp_items?.length" class="qw-detail-table">
          <thead>
            <tr><th>Catalogue</th><th>Configuration Description</th><th>Quantity</th><th>Unit Cost</th><th>Total Cost</th><th>Note</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in configDetail.kp_items" :key="idx">
              <td>{{ row.cat || row.part_category || '—' }}</td>
              <td>{{ row.name || row.catalogue || '—' }}</td>
              <td>{{ row.qty }}</td>
              <td>{{ money(row.cost) }}</td>
              <td>{{ money(Number(row.cost || 0) * Number(row.qty || 0)) }}</td>
              <td>{{ row.note || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="panel-empty">暂无 KP</div>
      </div>
    </a-modal>
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
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
/* 整条卡头横条可点击展开/收起；头部操作区 @click.stop 隔离按钮 */
.card-head-toggle {
  cursor: pointer;
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
.qw-shell-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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
.qw-snapshot-body { padding: 12px 13px; }
.qw-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 12px 13px;
  border-bottom: 1px solid var(--cpq-glass-border);
}
.qw-summary > div {
  min-width: 0;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 9px;
  padding: 8px 9px;
  background: var(--cpq-overlay-w4);
}
.qw-summary small { display: block; color: var(--cpq-text-muted); font-size: 10px; margin-bottom: 3px; }
.qw-summary b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--cpq-text-primary); font-size: 12px; }
.qw-sheet-block { border-bottom: 1px solid var(--cpq-glass-border); }
.qw-sheet-block:last-child { border-bottom: none; }
.qw-sheet-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 13px; border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.qw-delete-link {
  color: var(--cpq-color-danger, #ff4d4f); font-size: 12px; cursor: pointer; white-space: nowrap;
}
.qw-delete-link:hover { text-decoration: underline; }
.qw-sheet-title {
  font-size: 13px; font-weight: 600; color: var(--cpq-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.qw-cost-table { width: calc(100% - 26px); margin: 12px 13px; border-collapse: collapse; font-size: 12px; }
.qw-cost-table th, .qw-cost-table td { border: 1px solid var(--cpq-glass-border); padding: 7px 8px; text-align: left; }
.qw-cost-table th { background: var(--cpq-overlay-w4); color: var(--cpq-text-muted); font-weight: 600; }
.qw-config-row { cursor: pointer; }
.qw-config-row:hover { background: var(--cpq-overlay-w4); }
.qw-total-row td { background: var(--cpq-overlay-w4); color: var(--cpq-text-secondary); font-weight: 600; }
.panel-empty { padding: 22px 13px; text-align: center; color: var(--cpq-text-muted); font-size: 12px; }
.qw-actions { display: flex; align-items: center; gap: 6px; }
.qw-batch { padding: 10px 13px; border-bottom: 1px solid var(--cpq-glass-border); }

.qw-approval-bar {
  margin: 0 0 12px;
  padding: 10px 14px;
  border-radius: 12px;
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
  font-size: 11.5px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--cpq-notif-amber-bg);
  color: var(--cpq-notif-amber);
}
.qw-approval-list { display: flex; flex-direction: column; gap: 6px; }
.qw-approval-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: 8px;
  background: var(--cpq-bg-card);
  border: 1px solid var(--cpq-border-secondary);
}
.qw-approval-quotation {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.qw-approval-margin {
  flex: 1;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.qw-empty { padding: 26px 13px; text-align: center; color: var(--cpq-text-muted); font-size: 12px; }
.qw-list { display: flex; flex-direction: column; }
.qw-doc-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  padding: 12px;
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
.quote-doc-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}
.quote-doc-meta > div {
  min-width: 0;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--cpq-glass-border);
}
.quote-doc-meta small {
  display: block;
  color: var(--cpq-text-muted);
  font-size: 10px;
  margin-bottom: 3px;
}
.quote-doc-meta b {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--cpq-text-primary);
  font-size: 12px;
}
.qw-row-actions { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 2px; }
.qw-send { color: #2563eb; font-weight: 600; }
.qw-send-modal { display: flex; flex-direction: column; gap: 14px; }
.qw-send-tip { margin: 0; color: var(--cpq-text-muted); font-size: 13px; line-height: 1.6; }
.qw-send-field { display: flex; flex-direction: column; gap: 7px; }
.qw-send-field label { color: var(--cpq-text-primary); font-size: 12px; font-weight: 600; }
.qw-send-actions { display: flex; justify-content: flex-end; gap: 8px; }
.qw-timeline {
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.qw-timeline .tl-head {
  padding: 11px 14px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
  font-weight: 700;
  font-size: 14px;
  color: var(--cpq-text-primary);
}
.qw-detail-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 10px;
}
.qw-detail-grid > div {
  border: 1px solid var(--cpq-glass-border);
  border-radius: 9px;
  padding: 8px 9px;
  background: var(--cpq-overlay-w4);
}
.qw-detail-grid small { display: block; color: var(--cpq-text-muted); font-size: 10px; margin-bottom: 3px; }
.qw-detail-grid b { color: var(--cpq-text-primary); font-size: 12px; }
.qw-detail-desc { margin: 0 0 12px; color: var(--cpq-text-secondary); font-size: 12px; line-height: 1.6; }
.qw-detail h4 { margin: 12px 0 6px; color: var(--cpq-text-primary); font-size: 13px; }
.qw-detail-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.qw-detail-table th, .qw-detail-table td { border: 1px solid var(--cpq-glass-border); padding: 7px 8px; text-align: left; }
.qw-detail-table th { background: var(--cpq-overlay-w4); color: var(--cpq-text-muted); font-weight: 600; }

.rt-num { text-align: right; }
.rt-q-title, .rt-q-id { display: block; word-break: break-word; white-space: normal; min-width: 0; }

@media (max-width: 900px) {
  .qw-body { grid-template-columns: 1fr; }
  .qw-row-actions { width: 100%; justify-content: flex-start; }
}
</style>
