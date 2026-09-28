<template>
  <div class="opportunity-detail-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack()">
          <ArrowLeftOutlined />
        </button>
        <h1>{{ opportunity ? (opportunity.customer_name || '未命名客户') : '加载中...' }}</h1>
        <span v-if="opportunity" class="status-indicator">
          <span class="status-dot" :class="`status-${opportunity.result || 'pending'}`"></span>
          <a-select
            v-if="canEditResult"
            :value="opportunity.result || 'pending'"
            size="small"
            class="header-result-select"
            :options="resultOptions"
            @change="onResultChange"
          />
          <span v-else class="status-text">{{ resultLabel(opportunity.result) }}</span>
        </span>
        <span v-if="opportunity && canViewAll" class="header-created-date">
          创建于
          <a-date-picker
            :value="createdDateValue"
            size="small"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 120px"
            @change="onCreatedDateChange"
          />
        </span>
      </div>
      <div class="header-right" v-if="opportunity">
        <a-button size="small" @click="showRecycleBin = true" v-if="deletedQuotations.length > 0">
          <template #icon><DeleteOutlined /></template>
          回收站 ({{ deletedQuotations.length }})
        </a-button>
        <a-popconfirm
          title="确定要删除此商机吗？"
          @confirm="handleDeleteProject"
          ok-text="确定"
          cancel-text="取消"
          ok-type="danger"
        >
          <a-button danger size="small">
            <template #icon><DeleteOutlined /></template>
            删除
          </a-button>
        </a-popconfirm>
      </div>
    </div>

    <!-- 加载骨架：按流程看板三栏布局（左时间线/中工作台/右审批）占位，避免与真实布局跳变；主数据或看板任一未就绪都显示 -->
    <div v-if="!projectLoadError && (!boardSettled || !opportunity)" class="detail-skeleton">
      <div class="sk-board">
        <div class="sk-card sk-rail glass"><a-skeleton active :paragraph="{ rows: 6 }" /></div>
        <div class="sk-main">
          <div class="sk-card glass"><a-skeleton active :paragraph="{ rows: 3 }" /></div>
          <div class="sk-card glass"><a-skeleton active :paragraph="{ rows: 10 }" /></div>
        </div>
        <div class="sk-card sk-aside glass"><a-skeleton active :paragraph="{ rows: 8 }" /></div>
      </div>
    </div>

    <div v-else-if="projectLoadError && !opportunity" class="detail-load-error">
      <span>{{ projectLoadError }}</span>
      <a-button type="primary" size="small" @click="loadProject">重试</a-button>
    </div>

    <!-- 商机全生命周期流程看板：与详情主数据(loadProject)并行加载，去掉串行等待 -->
    <OpportunityProcessBoard
      ref="boardRef"
      v-if="!projectLoadError"
      :opportunity-id="opportunityId"
      :updated-at="opportunity?.updated_at"
      :legacy-requirement-text="legacyRequirementText"
      :attachments="feedAttachments"
      :quotations="quotations"
      :quote-price-visible="quotePriceVisible"
      :quote-select-mode="activeSelectMode"
      :quote-selected-ids="activeSelectedIdsArray"
      @preview-attachment="openAttachmentPreview"
      @delete-attachment="onAttachmentDelete"
      @new-quotation="createNewQuotation"
      @upload-cost-sheet="showUploadModal = true"
      @view-quotation="viewQuotation"
      @unfreeze-quotation="handleUnfreeze"
      @set-primary="setAsPrimary"
      @rename-quotation="startRenameQuotation"
      @delete-quotation="deleteQuotation"
      @toggle-quote-select="toggleActiveSelect"
      @enter-quote-batch="enterActiveSelect"
      @exit-quote-batch="exitActiveSelect"
      @batch-delete-quotes="handleBatchQuotationDelete"
      @refresh-meta="loadProject"
      @refresh-quotations="loadProject"
      @board-settled="boardSettled = true"
    />

    <!-- 回收站抽屉 -->
    <a-drawer
      v-model:open="showRecycleBin"
      title="回收站"
      placement="right"
      :width="'min(600px, 100vw)'"
      :destroyOnClose="false"
    >
      <div class="recycle-header">
        <span class="recycle-count">{{ deletedQuotations.length }} 个已删除报价单</span>
        <div class="recycle-actions">
          <a-button v-if="deletedSelectMode" size="small" type="primary" @click="handleBatchRestoreQuotations">恢复选中 ({{ deletedSelectedIds.size }})</a-button>
          <a-button v-if="deletedSelectMode" size="small" danger @click="handleBatchPermanentDeleteQuotations">删除选中 ({{ deletedSelectedIds.size }})</a-button>
          <a-button v-if="deletedSelectMode" size="small" @click="exitDeletedSelect">取消</a-button>
          <a-button v-if="!deletedSelectMode" size="small" @click="enterDeletedSelect">批量操作</a-button>
        </div>
      </div>

      <!-- 批量操作栏 -->
      <div v-if="deletedSelectMode && deletedSelectedIds.size > 0" class="batch-bar glass">
        <div class="batch-left">
          <a-checkbox
            :checked="deletedSelectedIds.size === deletedQuotations.length && deletedQuotations.length > 0"
            :indeterminate="deletedSelectedIds.size > 0 && deletedSelectedIds.size < deletedQuotations.length"
            @change="toggleDeletedSelectAll"
          >
            全选
          </a-checkbox>
          <span class="batch-count">已选 {{ deletedSelectedIds.size }} 项</span>
        </div>
        <div class="batch-actions">
          <a-button size="small" @click="handleBatchRestoreQuotations">恢复选中</a-button>
          <a-button danger size="small" @click="handleBatchPermanentDeleteQuotations">永久删除选中</a-button>
          <a-button size="small" @click="exitDeletedSelect">取消</a-button>
        </div>
      </div>

      <div v-if="deletedQuotations.length === 0" class="empty-state glass">
        <p>回收站为空</p>
      </div>

      <div v-else class="quotation-list glass">
        <div
          v-for="(quo, index) in deletedQuotations"
          :key="quo.quotation_id"
          class="quotation-row deleted-row"
          :class="{ 'selecting': deletedSelectMode }"
          :style="{ animationDelay: `${index * 50}ms` }"
          @click="deletedSelectMode ? toggleDeletedSelect(quo.quotation_id) : null"
        >
          <div v-if="deletedSelectMode" class="row-checkbox" @click.stop>
            <a-checkbox
              :checked="deletedSelectedIds.has(quo.quotation_id)"
              @change="toggleDeletedSelect(quo.quotation_id)"
            />
          </div>
          <div class="quo-status-bar margin-neutral"></div>
          <div class="quo-content">
            <div class="quo-top">
              <span class="quo-name">{{ quo.quotation_name || '未命名报价单' }}</span>
              <span class="quo-price"><template v-if="quotePriceVisible">¥{{ formatPrice(quo.total_price) }}</template><span v-else class="price-hidden">***</span></span>
              <span v-if="quotePriceVisible" class="quo-margin-badge" :class="getMarginBadgeClass(quo.profit_margin)">
                {{ quo.profit_margin?.toFixed(2) || '0.00' }}%
              </span>
              <span v-if="(quo.config_count || 0) > 1" class="multi-cfg-tag">首个/共{{ quo.config_count }}</span>
            </div>
            <div class="quo-bottom">
              {{ quo.config_count || 0 }}配置 · {{ formatDate(quo.created_at) }}
            </div>
          </div>
          <div v-if="!deletedSelectMode" class="quo-actions" @click.stop>
            <a-popconfirm
              title="确定要恢复这个报价单吗？"
              @confirm="restoreQuotation(quo.quotation_id)"
            >
              <button class="text-btn">
                <UndoOutlined /> 恢复
              </button>
            </a-popconfirm>
            <a-popconfirm
              title="确定要永久删除这个报价单吗？此操作不可恢复！"
              @confirm="permanentDeleteQuotation(quo.quotation_id)"
            >
              <button class="text-btn danger">
                <DeleteOutlined /> 永久删除
              </button>
            </a-popconfirm>
          </div>
          <span v-if="!deletedSelectMode" class="quo-arrow">
            <RightOutlined />
          </span>
        </div>
      </div>
    </a-drawer>

    <!-- 重命名弹窗 -->
    <a-modal
      v-model:open="showRenameModal"
      title="重命名报价单"
      @ok="saveRenameQuotation"
      :confirm-loading="renameLoading"
      ok-text="保存"
      cancel-text="取消"
    >
      <a-form layout="vertical">
        <a-form-item label="报价单名称">
          <a-input
            v-model:value="renameValue"
            placeholder="请输入报价单名称"
            :maxlength="50"
            @pressEnter="saveRenameQuotation"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 文件在线预览（图片 / PDF / Excel 在线编辑）-->
    <AttachmentPreviewModal v-model:open="previewOpen" :attachment="previewAttachment" @saved="onPreviewSaved" />

    <!-- 上传报价单 Modal -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传成本表"
      :footer="null"
      :destroyOnClose="true"
      width="500px"
    >
      <p style="color: var(--cpq-text-secondary); font-size: 13px; margin-bottom: 16px;">
        上传后先解析预览，可调整解析规则，确认无误后再生成成本表。
      </p>
      <a-upload-dragger
        name="file"
        :custom-request="handleUploadToProject"
        :show-upload-list="false"
        accept=".xlsx"
      >
        <p class="ant-upload-drag-icon"><inbox-outlined /></p>
        <p class="ant-upload-text">点击或拖拽 Excel 成本表到此区域</p>
        <p class="ant-upload-hint">支持 .xlsx 格式（旧版 .xls 请先另存为 .xlsx）</p>
      </a-upload-dragger>
    </a-modal>

    <!-- 解析预览：核对取值位置/调区域与列规则后再生成成本表 -->
    <QuotationParsePreviewModal
      :open="parsePreviewOpen"
      :file="parsePreviewFile"
      :opportunity-id="opportunityId"
      :confirming="parseConfirming"
      @confirm="onParseConfirm"
      @cancel="onParseCancel"
    />

    <!-- 已导出报价单：成本快照抽屉 -->
    <QuotationCostDrawer
      v-model:open="costDrawerOpen"
      :quotation="costDrawerQuotation"
      :excel-loading="excelLoading"
      :reparse-loading="reparseLoading"
      @view-excel="handleViewExcel"
      @reparse="handleReparse"
      @unfreeze="handleUnfreeze()"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  DeleteOutlined, RightOutlined,
  UndoOutlined
} from '@ant-design/icons-vue'
import { portalApi } from '@/api/portal'
import { projectApi, quotationApi } from '@/api'
import { feedApi } from '@/api/feed'
import { downloadOfficeFile } from '@/utils/fileDownload'
import { useAuthStore } from '@/store/auth'
import QuotationCostDrawer from '@/components/quote/QuotationCostDrawer.vue'
import QuotationParsePreviewModal from '@/components/quotation/QuotationParsePreviewModal.vue'
import OpportunityProcessBoard from '@/components/opportunity/OpportunityProcessBoard.vue'
import AttachmentPreviewModal from '@/components/feed/AttachmentPreviewModal.vue'
import { useFeedSocket } from '@/composables/useFeedSocket'
import type { Opportunity, Quotation } from '@/types/opportunity'
import type { FeedAttachment } from '@/api/feed'
import { formatDate, formatPrice, marginBadgeClass as getMarginBadgeClass } from '@/utils/quoteCommon'
import { RESULT_OPTIONS, resultLabel } from '@/constants/opportunityResult'
import dayjs from 'dayjs'

const route = useRoute()
const auth = useAuthStore()
/** 商机详情报价单价格可见性（字段级权限，配置驱动） */
const quotePriceVisible = computed(() => auth.can('field.opportunity.quote_price'))
const canViewAll = computed(() => auth.can('page.opportunities_all'))
const router = useRouter()
const opportunityId = route.params.opportunityId as string
const opportunityIdRef = computed(() => opportunityId)
const boardRef = ref<{ reload: () => Promise<void> } | null>(null)

async function reloadBoard() {
  await boardRef.value?.reload()
}
function goBack() {
  const from = route.query.from as string
  const portalMap: Record<string, string> = {
    'portal-business': '/portal/workstation/business',
    'portal-te': '/portal/workstation/te',
    'portal-cost': '/portal/workstation/cost',
    'portal-quote': '/portal/workstation/quote',
    'portal-admin': '/portal/workstation/dispatch',
  }
  router.push(portalMap[from] || '/opportunities')
}
const feed = useFeedSocket(opportunityIdRef)
const { attachments: feedAttachments } = feed
const previewOpen = ref(false)
const previewAttachment = ref<FeedAttachment | null>(null)
function openAttachmentPreview(a: FeedAttachment) {
  previewAttachment.value = a
  previewOpen.value = true
}
function onAttachmentDelete(a: FeedAttachment) {
  feed.deleteAttachment(a.attachment_id)
}
function onPreviewSaved() {
  feed.load()
}
const legacyRequirementText = ref('')

const opportunity = ref<Opportunity | null>(null)
const quotations = ref<Quotation[]>([])
const deletedQuotations = ref<Quotation[]>([])
const boardSettled = ref(false)
const projectLoadError = ref('')
const showRecycleBin = ref(false)

// Active quotation selection
const activeSelectMode = ref(false)
const activeSelectedIds = ref<Set<string>>(new Set())
const activeSelectedIdsArray = computed(() => [...activeSelectedIds.value])

// Deleted quotation selection
const deletedSelectMode = ref(false)
const deletedSelectedIds = ref<Set<string>>(new Set())

// Rename quotation
const showRenameModal = ref(false)
const renameLoading = ref(false)
const renameValue = ref('')
const renameTargetId = ref<string | null>(null)

// Active quotation selection helpers
const toggleActiveSelect = (id: string) => {
  const s = new Set(activeSelectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  activeSelectedIds.value = s
}

const enterActiveSelect = () => {
  activeSelectMode.value = true
  activeSelectedIds.value = new Set()
}

const exitActiveSelect = () => {
  activeSelectMode.value = false
  activeSelectedIds.value = new Set()
}

const handleBatchQuotationDelete = async () => {
  if (activeSelectedIds.value.size === 0) return
  Modal.confirm({
    title: `删除选中的 ${activeSelectedIds.value.size} 个报价单？`,
    content: '删除后不可恢复；关联的成本表仍会保留，可在报价节点或成本节点删除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const result = await quotationApi.batchDelete([...activeSelectedIds.value])
        const ok = result.success?.length || 0
        const fail = result.failed?.length || 0
        message.success(`已删除 ${ok} 个报价单` + (fail > 0 ? `，${fail} 个失败` : ''))
        exitActiveSelect()
        await loadProject()
        await reloadBoard()
      } catch (err: any) {
        message.error('批量删除失败: ' + (err.message || err))
      }
    },
  })
}

// Deleted quotation selection helpers
const toggleDeletedSelect = (id: string) => {
  const s = new Set(deletedSelectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  deletedSelectedIds.value = s
}

const toggleDeletedSelectAll = (checked: boolean) => {
  if (checked) {
    deletedSelectedIds.value = new Set(deletedQuotations.value.map(q => q.quotation_id))
  } else {
    deletedSelectedIds.value = new Set()
  }
}

const enterDeletedSelect = () => {
  deletedSelectMode.value = true
  deletedSelectedIds.value = new Set()
}

const exitDeletedSelect = () => {
  deletedSelectMode.value = false
  deletedSelectedIds.value = new Set()
}

const handleBatchRestoreQuotations = async () => {
  if (deletedSelectedIds.value.size === 0) return
  try {
    const result = await quotationApi.batchRestore([...deletedSelectedIds.value])
    const ok = result.success?.length || 0
    const fail = result.failed?.length || 0
    message.success(`已恢复 ${ok} 个报价单` + (fail > 0 ? `，${fail} 个失败` : ''))
    exitDeletedSelect()
    await loadProject()
    await loadDeletedQuotations()
    await reloadBoard()
  } catch (err: any) {
    message.error('批量恢复失败: ' + (err.message || err))
  }
}

const handleBatchPermanentDeleteQuotations = async () => {
  if (deletedSelectedIds.value.size === 0) return
  try {
    const result = await quotationApi.batchPermanentDelete([...deletedSelectedIds.value])
    const ok = result.success?.length || 0
    const fail = result.failed?.length || 0
    message.success(`已永久删除 ${ok} 个报价单` + (fail > 0 ? `，${fail} 个失败` : ''))
    exitDeletedSelect()
    await loadDeletedQuotations()
    await reloadBoard()
  } catch (err: any) {
    message.error('批量永久删除失败: ' + (err.message || err))
  }
}

const loadProject = async () => {
  projectLoadError.value = ''
  try {
    const data = await projectApi.getById(opportunityId)
    // API 返回结构: {meta: {...}, configs: {...}, quotations: [...]}
    const meta = data.meta || {}
    const quotationsData = data.quotations || []
    
    // 计算统计数据
    const activeQuotations = quotationsData.filter((q: any) => q.status === 'active')
    const quotationCount = activeQuotations.length
    const configCount = activeQuotations.reduce((sum: number, q: any) => sum + (q.config_count || 0), 0)
    
    opportunity.value = {
      ...meta,  // 展开所有字段（包括 extra_fields 中的动态字段）
      quotation_count: quotationCount,
      config_count: configCount,
    }
    legacyRequirementText.value = (meta as any).customer_requirement_text || ''
    quotations.value = quotationsData
  } catch (err: any) {
    if (err?.response?.status === 404) {
      message.error('商机不存在或已删除')
      goBack()
      return
    }
    projectLoadError.value = '加载商机详情失败，请重试'
    message.error('加载商机详情失败')
  }
}

// 删除商机
const handleDeleteProject = async () => {
  try {
    await projectApi.trash(opportunityId)
    message.success('商机已移至回收站')
    goBack()
  } catch (err: any) {
    message.error('删除失败: ' + (err.message || err))
  }
}

// 归档语义已并入 result（已过期）；以下两个 handler 已移除。

const resultOptions = RESULT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))
const canEditResult = computed(() => auth.can('action.opportunity.result'))
async function onResultChange(val: string) {
  const prev = (opportunity.value as any)?.result
  if (val === prev) return
  try {
    await projectApi.updateMeta(opportunityId, { result: val })
    await loadProject()
    message.success('已更新商机状态')
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
  }
}

// 创建日期的可编辑绑定（dayjs 格式用于 a-date-picker，仅管理员可见）
const createdDateValue = computed(() => {
  const dateStr = opportunity.value?.created_at
  if (!dateStr) return null
  const slice = dateStr.slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(slice)) return null
  return dayjs(slice)
})

async function onCreatedDateChange(date: dayjs.Dayjs | string | null) {
  if (!date) return
  const newDateStr = typeof date === 'string' ? date : date.format('YYYY-MM-DD')
  const oldDateStr = formatDate(opportunity.value?.created_at || '')
  if (newDateStr === oldDateStr) return
  try {
    const newFull = `${newDateStr} 00:00:00`
    await projectApi.update(opportunityId, { created_at: newFull })
    if (opportunity.value) opportunity.value.created_at = newFull
    message.success('创建日期已更新')
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
  }
}

// 报价单操作
const createNewQuotation = () => {
  // 始终新建空白工作台。每张报价单独立（只有已导出/未导出之别），
  // 新建 / 推理流转单 / 复制 各建各的、互不覆盖（曾因「一商机一草稿」复用导致回归，6d6be6b）。
  router.push(`/workspace?opportunityId=${opportunityId}&mode=create&from=opportunities`)
}

// 成本快照抽屉
const costDrawerOpen = ref(false)
const costDrawerQuotation = ref<any>(null)
const excelLoading = ref(false)
const reparseLoading = ref(false)

// 找该报价单在 feed 里归档的 sent_quote 导出件
const findExportAttachment = (quotationId: string) => {
  return (feedAttachments.value || []).find(
    a => a.category === 'sent_quote' && a.quotation_id === quotationId && a.kind === 'export'
  )
}

const viewQuotation = async (quotation: Quotation) => {
  if (quotation.exported_at) {
    // 已导出 → 开抽屉看成本快照（拉全量含 cost_snapshot）
    costDrawerQuotation.value = quotation
    costDrawerOpen.value = true
    try {
      const full = await quotationApi.getById(quotation.quotation_id)
      costDrawerQuotation.value = full
    } catch (e) {
      // 保留列表数据兜底
    }
    return
  }
  // 未导出 → 进工作台编辑
  router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${quotation.quotation_id}&mode=edit&from=opportunities`)
}

const handleViewExcel = async () => {
  const quo = costDrawerQuotation.value
  if (!quo) return
  const att = findExportAttachment(quo.quotation_id)
  if (!att) {
    message.warning('未找到已导出的 Excel 归档')
    return
  }
  // 下载端点需鉴权，window.open 直链 401 → 走带 Authorization 的 blob 下载
  try {
    await downloadOfficeFile(feedApi.attachments.downloadUrl(att.attachment_id), att.original_filename)
  } catch {
    message.error('下载失败')
  }
}

const handleReparse = async () => {  const quo = costDrawerQuotation.value
  if (!quo) return
  reparseLoading.value = true
  try {
    // 克隆源的 DB items + 配置字段成新报价单（不解析导出件）
    const result = await quotationApi.reparse(quo.quotation_id)
    message.success('已复制为新报价单，正在打开')
    costDrawerOpen.value = false
    await loadProject()
    router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${result.quotation_id}&mode=edit&from=opportunities`)
  } catch (e: any) {
    message.error('复制失败：' + (e?.message || e))
  } finally {
    reparseLoading.value = false
  }
}

// 解冻已导出报价单并直接进工作台编辑（需 action.quote.unfreeze 权限，后端二次校验）
const handleUnfreeze = async (quotation?: Quotation) => {
  const quo: any = quotation || costDrawerQuotation.value
  if (!quo) return
  Modal.confirm({
    title: `解冻「${quo.quotation_name || '未命名报价单'}」？`,
    content: '解冻后该报价单回到草稿状态，可重新进入工作台编辑；再次导出会重新冻结并覆盖成本快照。',
    okText: '解冻并编辑',
    cancelText: '取消',
    async onOk() {
      try {
        await quotationApi.unfreeze(quo.quotation_id)
        message.success('已解冻，正在打开工作台')
        costDrawerOpen.value = false
        await loadProject()
        router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${quo.quotation_id}&mode=edit&from=opportunities`)
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '解冻失败')
      }
    },
  })
}


const loadDeletedQuotations = async () => {
  try {
    const response = await quotationApi.list(opportunityId, { include_deleted: true })
    deletedQuotations.value = response.filter((q: Quotation) => q.status === 'deleted')
  } catch (error) {
    console.error('加载已删除报价单失败:', error)
  }
}

const restoreQuotation = async (quotationId: string) => {
  try {
    await quotationApi.restore(quotationId)
    message.success('报价单已恢复')
    await loadProject()
    await loadDeletedQuotations()
    await reloadBoard()
  } catch (error: any) {
    message.error('恢复失败: ' + (error.message || error))
  }
}

const permanentDeleteQuotation = async (quotationId: string) => {
  try {
    const result = await quotationApi.batchPermanentDelete([quotationId])
    const fail = result.failed?.length || 0
    if (fail > 0) {
      message.error('删除失败: ' + (result.failed[0].error || '未知原因'))
      return
    }
    message.success('报价单已永久删除')
    await loadDeletedQuotations()
    await reloadBoard()
  } catch (error: any) {
    message.error('删除失败: ' + (error.message || error))
  }
}

const deleteQuotation = async (quotationId: string) => {
  Modal.confirm({
    title: '删除报价单？',
    content: '删除后不可恢复；关联的成本表仍会保留，可在报价节点或成本节点删除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await quotationApi.delete(quotationId)
        message.success('报价单已删除')
        await loadProject()
        await loadDeletedQuotations()
        await reloadBoard()
      } catch (err: any) {
        message.error('删除失败: ' + (err.message || err))
      }
    },
  })
}

// 重命名报价单
const startRenameQuotation = (quotation: Quotation) => {
  renameTargetId.value = quotation.quotation_id
  renameValue.value = quotation.quotation_name || ''
  showRenameModal.value = true
}

// 设置为主推方案
const setAsPrimary = async (quotation: Quotation) => {
  try {
    await quotationApi.setPrimary(quotation.quotation_id)
    message.success('已设置为主推方案')
    // 刷新报价单列表
    await loadProject()
    await reloadBoard()
  } catch (err: any) {
    message.error('设置失败: ' + (err.message || err))
  }
}

const saveRenameQuotation = async () => {
  if (!renameTargetId.value) return
  if (!renameValue.value.trim()) {
    message.warning('报价单名称不能为空')
    return
  }
  
  renameLoading.value = true
  try {
    await quotationApi.rename(renameTargetId.value, renameValue.value.trim())
    message.success('重命名成功')
    showRenameModal.value = false
    await loadProject()
    await reloadBoard()
  } catch (err: any) {
    message.error('重命名失败: ' + (err.message || err))
  } finally {
    renameLoading.value = false
  }
}

// =================== Upload Quotation ===================
const showUploadModal = ref(false)
const parsePreviewOpen = ref(false)
const parsePreviewFile = ref<File | null>(null)
// 生成成本表中：防重复点击导致重复创建（后端解析期间可连点）
const parseConfirming = ref(false)

// 上传成本表：先存文件并打开解析预览弹窗，用户核对/调规则后再确认生成
const handleUploadToProject = async (options: any) => {
  const file = options.file as File
  options.onSuccess?.() // 结束 dragger 的 uploading 态
  parsePreviewFile.value = file
  parsePreviewOpen.value = true
  showUploadModal.value = false
}

// 解析预览确认：落库生成成本表草稿（防重入：生成期间按钮 loading/禁用，函数开头二次拦截）
// 模板由「成本核算·上传解析」使用位置绑定决定（设置页配置）；payload 只带回会话补丁——
// 预览看到的=确认生成的
const onParseConfirm = async (payload?: { parseOverrides?: Record<string, any> }) => {
  if (!parsePreviewFile.value || parseConfirming.value) return
  parseConfirming.value = true
  const hide = message.loading('正在生成成本表...', 0)
  try {
    const result = await portalApi.uploadCostSheet(
      opportunityId,
      parsePreviewFile.value,
      payload?.parseOverrides
    )
    if (result.sheet?.id) {
      message.success('成本表已创建！')
      parsePreviewOpen.value = false
      parsePreviewFile.value = null
      await loadProject()
      await reloadBoard()
    } else {
      message.error('成本表创建失败，请稍后重试')
    }
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    message.error(detail || err?.message || '生成成本表失败')
  } finally {
    hide()
    parseConfirming.value = false
  }
}

const onParseCancel = () => {
  parsePreviewOpen.value = false
  parsePreviewFile.value = null
}

onMounted(async () => {
  loadDeletedQuotations()
  // 详情主数据与 feed（消息/附件）并行加载，互不阻塞；主内容仍等 loadProject 返回后填充
  const projectP = loadProject()
  const feedP = feed.load().then(() => feed.connect()).catch(() => {})
  await Promise.all([projectP, feedP])
})

onBeforeUnmount(() => {
  feed.disconnect()
})
</script>

<style scoped>
.opportunity-detail-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--cpq-header-clearance, 56px));
  min-height: 0;
  overflow: hidden;
  padding: 12px 0 0;
}
.opportunity-detail-page :deep(.bod-page) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── Page Header ── */
.page-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 0 20px;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.back-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--cpq-overlay-w8);
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all var(--cpq-transition-fast);
}

.back-btn:hover {
  background: var(--cpq-overlay-w8);
  color: var(--cpq-text-primary);
  border-color: var(--cpq-overlay-w15);
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 4px;
}

.header-created-date {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.status-pending {
  background: var(--cpq-accent-primary);
  box-shadow: 0 0 6px var(--cpq-overlay-a40);
}

.status-dot.status-won {
  background: var(--cpq-accent-success);
  box-shadow: 0 0 6px var(--cpq-accent-success);
}

.status-dot.status-lost {
  background: var(--cpq-accent-danger);
  box-shadow: 0 0 6px var(--cpq-accent-danger);
}

.status-dot.status-expired {
  background: var(--cpq-accent-warning);
  box-shadow: 0 0 6px var(--cpq-accent-warning);
}

.header-result-select {
  width: 108px;
}

.status-text {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

.header-right {
  display: flex;
  gap: 8px;
}

/* ── Info Card ── */
.info-card {
  padding: 0;
  margin-bottom: 24px;
  overflow: hidden;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
}

.info-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  font-size: 13px;
  color: var(--cpq-text-muted);
  border-bottom: 1px solid var(--cpq-overlay-w4);
  grid-column: 1 / -1;
}

.status-meta {
  flex-shrink: 0;
  color: var(--cpq-text-muted);
}

.info-row {
  display: flex;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid var(--cpq-overlay-w3);
  transition: background var(--cpq-transition-fast);
}

.info-row:last-child {
  border-bottom: none;
}

.info-row:hover {
  background: var(--cpq-overlay-w3);
}

.info-label {
  width: 120px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--cpq-text-muted);
  text-align: right;
  padding-right: 16px;
}

.info-value {
  flex: 1;
  font-size: 14px;
  color: var(--cpq-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 信息栏内联输入：透明底融入卡片、压淡边框、聚焦才蓝边 —— 消除"网格盒子"密集感
   保留边框（不走 :bordered=false）避免 auto-complete 塌缩（见 memory infobar-editable-input-style） */
.info-value :deep(.ant-select-selector),
.info-value :deep(.ant-input),
.info-value :deep(.ant-input-number-input) {
  background: transparent !important;
  border-color: var(--cpq-overlay-w8) !important;
  border-radius: var(--cpq-radius-sm) !important;
  box-shadow: none !important;
  color: var(--cpq-text-primary) !important;
}
.info-value :deep(.ant-select:hover .ant-select-selector),
.info-value :deep(.ant-input:hover),
.info-value :deep(.ant-input-number:hover .ant-input-number-input) {
  border-color: var(--cpq-overlay-w15) !important;
}
.info-value :deep(.ant-select-focused .ant-select-selector),
.info-value :deep(.ant-input:focus),
.info-value :deep(.ant-input-number-focused .ant-input-number-input) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a15) !important;
}
.info-value :deep(.ant-select-selection-item) {
  color: var(--cpq-text-primary) !important;
}

/* ── Batch Bar ── */
.batch-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--cpq-overlay-danger10);
  border: 1px solid var(--cpq-overlay-danger15);
  border-radius: var(--cpq-radius-md);
  animation: fadeInUp 0.3s var(--cpq-ease-out-expo) backwards;
}

.batch-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-count {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

.batch-actions {
  display: flex;
  gap: 8px;
}

/* ── Quotation Section ── */
.quotation-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6);
  padding: 2px 8px;
  border-radius: 10px;
}

.section-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Empty State ── */
.empty-state {
  padding: 48px;
  text-align: center;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
  color: var(--cpq-text-muted);
}

/* ── Quotation List ── */
.quotation-list {
  padding: 0;
  overflow: hidden;
}

.quotation-row {
  display: flex;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--cpq-overlay-w4);
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) both;
}

.quotation-row:last-child {
  border-bottom: none;
}

.quotation-row:hover {
  background: var(--cpq-overlay-a4);
  transform: translateY(-2px);
}

.quotation-row:active {
  transform: scale(0.996);
}

/* 选择模式下点击不缩放 */
.quotation-row.selecting:active {
  transform: none;
}

/* 复选框列 */
.row-checkbox {
  display: flex;
  align-items: center;
  padding-right: 12px;
}

/* ── Quotation Status Bar ── */
.quo-status-bar {
  width: 3px;
  align-self: stretch;
  border-radius: 2px;
  margin-right: 16px;
  flex-shrink: 0;
  background: transparent;
  transition: all var(--cpq-transition-fast);
}

.quo-status-bar.margin-high {
  background: var(--cpq-accent-primary);
  box-shadow: 0 0 8px var(--cpq-overlay-a30);
}

.quo-status-bar.margin-mid {
  background: var(--cpq-color-gold);
}

.quo-status-bar.margin-low {
  background: var(--cpq-accent-danger);
}

.quo-status-bar.margin-neutral {
  background: var(--cpq-overlay-w10);
}

.quotation-row:hover .quo-status-bar.margin-neutral {
  background: var(--cpq-accent-primary);
}

/* ── Quotation Content ── */
.quo-content {
  flex: 1;
  min-width: 0;
}

.quo-top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.quo-primary-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-accent-primary);
  color: var(--cpq-accent-on-primary);
  letter-spacing: 0.5px;
  flex-shrink: 0;
}

.quo-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 草稿/已导出 状态标 */
.quo-state {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 9px;
  border: 1px solid;
  white-space: nowrap;
  flex-shrink: 0;
}
.quo-state--draft {
  color: var(--cpq-color-gold, #D4A853);
  background: rgba(212, 168, 83, 0.08);
  border-color: rgba(212, 168, 83, 0.25);
}
.quo-state--exported {
  color: var(--cpq-accent-primary, #1677FF);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.08));
  border-color: var(--cpq-overlay-a20, rgba(22, 119, 255, 0.2));
}

.price-hidden {
  color: var(--cpq-text-muted, #6E7582);
  letter-spacing: 1px;
}
.quo-price {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-accent-primary);
  flex-shrink: 0;
  white-space: nowrap;
}

.multi-cfg-tag {
  font-size: 10px;
  color: var(--cpq-text-muted, #6E7582);
  padding: 1px 5px;
  border: 1px solid var(--cpq-divider, rgba(0,0,0,0.08));
  border-radius: 4px;
  flex-shrink: 0;
  white-space: nowrap;
}

.quo-margin-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid;
  flex-shrink: 0;
  white-space: nowrap;
}

.quo-margin-badge.badge-high {
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
  border-color: var(--cpq-overlay-a20);
}

.quo-margin-badge.badge-mid {
  color: var(--cpq-color-gold);
  background: rgba(212, 168, 83, 0.08);
  border-color: rgba(212, 168, 83, 0.2);
}

.quo-margin-badge.badge-low {
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10);
  border-color: var(--cpq-overlay-danger15);
}

.quo-margin-badge.badge-neutral {
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
  border-color: var(--cpq-overlay-w8);
}

.quo-bottom {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

/* ── Quotation Actions ── */
.quo-actions {
  display: flex;
  gap: 4px;
  margin-right: 12px;
  opacity: 0;
  transition: opacity var(--cpq-transition-fast);
  flex-shrink: 0;
}

.quotation-row:hover .quo-actions {
  opacity: 1;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: var(--cpq-radius-sm);
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
}
.icon-btn:hover {
  background: var(--cpq-overlay-a8);
  color: var(--cpq-accent-primary);
}
.icon-btn.danger:hover {
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10);
}

.text-btn {
  padding: 4px 8px;
  border-radius: var(--cpq-radius-sm);
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  font-size: 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all var(--cpq-transition-fast);
}

.text-btn:hover {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
}

.text-btn.danger:hover {
  background: var(--cpq-overlay-danger10);
  color: var(--cpq-accent-danger);
}

/* ── Quotation Arrow ── */
.quo-arrow {
  color: var(--cpq-text-muted);
  font-size: 12px;
  transition: all var(--cpq-transition-fast);
  flex-shrink: 0;
}

.quotation-row:hover .quo-arrow {
  color: var(--cpq-accent-primary);
  transform: translateX(4px);
}

/* ── Animations ── */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── Deleted Quotations Section ── */
.deleted-section {
  margin-top: 32px;
}

.deleted-badge {
  color: var(--cpq-accent-danger) !important;
  background: var(--cpq-overlay-danger10) !important;
}

.deleted-row {
  opacity: 0.7;
}

.deleted-row:hover {
  opacity: 1;
}

.text-btn.restore {
  color: var(--cpq-accent-primary);
}

.text-btn.restore:hover {
  background: var(--cpq-overlay-a10);
}
.detail-skeleton {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.detail-load-error { display: flex; align-items: center; gap: 12px; padding: 24px 0; color: var(--cpq-text-muted); }
/* 骨架镜像流程看板三栏布局，避免加载完成后的跳变 */
.sk-board {
  display: grid;
  grid-template-columns: minmax(190px, 230px) minmax(0, 1fr) clamp(280px, 22vw, 360px);
  gap: 14px;
  align-items: stretch;
  height: 100%;
  min-height: 0;
  padding: 0 20px 12px;
  min-width: 0;
}
.sk-main { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.sk-card { min-width: 0; padding: 16px; border-radius: 12px; }
@media (max-width: 1080px) {
  .sk-board { grid-template-columns: 1fr; }
  .sk-rail, .sk-aside { display: none; }
}
/* ── 窄屏适配：信息卡列数收窄，避免行内输入被裁切；头部/操作区允许换行 ── */
@media (max-width: 1100px) {
  .info-card { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 860px) {
  .info-card { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .opportunity-detail-page {
    height: auto;
    min-height: calc(100vh - var(--cpq-header-clearance, 56px));
    overflow: visible;
    padding: 0 12px;
  }
  .opportunity-detail-page :deep(.bod-page) {
    flex: none;
    min-height: auto;
    overflow: visible;
  }
  .header-right { flex-wrap: wrap; }
  .section-header { flex-wrap: wrap; gap: 8px; }
  .quo-top { flex-wrap: wrap; row-gap: 4px; }
  .batch-bar { flex-wrap: wrap; gap: 8px; }
  .info-status-bar { flex-wrap: wrap; }
}
@media (max-width: 600px) {
  .info-row { flex-direction: column; align-items: stretch; gap: 6px; }
  .info-label { width: auto; text-align: left; padding-right: 0; }
  .info-value { flex: none; flex-wrap: wrap; }
}

</style>
