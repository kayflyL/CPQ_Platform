<template>
  <div class="opportunity-detail-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="router.push('/opportunities')">
          <ArrowLeftOutlined />
        </button>
        <h1>{{ opportunity ? (opportunity.customer_name || '未命名客户') : '加载中...' }}</h1>
        <span v-if="opportunity" class="status-indicator">
          <span class="status-dot" :class="`status-${opportunity.result || 'pending'}`"></span>
          <a-select
            :value="opportunity.result || 'pending'"
            size="small"
            class="header-result-select"
            :options="resultOptions"
            @change="onResultChange"
          />
        </span>
      </div>
      <div class="header-right" v-if="opportunity">
        <a-button 
          v-if="opportunity.status === 'active'" 
          size="small" 
          @click="handleArchive"
        >
          <template #icon><InboxOutlined /></template>
          归档
        </a-button>
        <a-button 
          v-if="opportunity.status === 'archived'" 
          size="small" 
          @click="handleUnarchive"
        >
          <template #icon><UndoOutlined /></template>
          取消归档
        </a-button>
        <a-button size="small" @click="showRecycleBin = true" v-if="deletedQuotations.length > 0">
          <template #icon><DeleteOutlined /></template>
          回收站 ({{ deletedQuotations.length }})
        </a-button>
        <a-button size="small" @click="showSidebar = !showSidebar">
          <template #icon><MessageOutlined /></template>
          评论
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

    <!-- 信息卡片 -->
    <div v-if="opportunity" class="info-card glass">
      <div class="info-status-bar">
        <span class="status-meta">
          创建于
          <a-date-picker
            :value="createdDateValue"
            size="small"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 120px"
            @change="onCreatedDateChange"
          />
          ｜更新于 {{ formatDate(opportunity.updated_at) }}
        </span>
      </div>

      <div
        v-for="field in infoFields"
        :key="field.key"
        class="info-row"
      >
        <span class="info-label">{{ field.label }}</span>
        <span class="info-value">
          <!-- 机箱形态：标签式多值输入 -->
          <template v-if="field.key === 'chassis_form'">
            <template v-if="!field.editable">{{ (opportunity as any)[field.key] || '-' }}</template>
            <a-select
              v-else
              v-model:value="chassisFormTags"
              mode="tags"
              size="small"
              style="width: 220px"
              placeholder="输入后回车添加"
              :options="chassisFormOptions"
              @change="onChassisFormChange"
              @dropdownVisibleChange="(open: boolean) => open && loadFieldHistory('chassis_form')"
            />
          </template>
          <!-- 普通字段 -->
          <template v-else-if="!field.editable">{{ (opportunity as any)[field.key] || '-' }}</template>
          <a-input-number
            v-else-if="(field as any).type === 'number'"
            v-model:value="(opportunity as any)[field.key]"
            size="small"
            style="width: 220px"
            :min="0"
            @focus="onFieldFocus(field.key)"
            @blur="onFieldBlur(field.key)"
            @pressEnter="saveField(field.key)"
          />
          <a-auto-complete
            v-else
            v-model:value="(opportunity as any)[field.key]"
            :options="getFilteredOptions(field.key)"
            :default-active-first-option="false"
            size="small"
            style="width: 220px"
            @keydown.enter="saveField(field.key)"
            @focus="onFieldFocus(field.key)"
            @blur="onFieldBlur(field.key)"
            @select="saveField(field.key)"
          />
        </span>
      </div>
    </div>

    <!-- 双栏:左侧证据链(需求/存档/活动) · 右侧报价单 -->
    <div v-if="opportunity" class="detail-grid">
      <div class="detail-left">
    <!-- 客户需求 -->
    <div v-if="opportunity" class="requirement-card glass">
      <div class="card-head">
        <h3>客户需求</h3>
        <span class="card-hint">贴入需求原文（表格或文字均可），作为配置参考，不约束</span>
      </div>
      <a-textarea
        v-model:value="requirementText"
        :auto-size="{ minRows: 3, maxRows: 12 }"
        placeholder="客户原始需求、FAE 邮件要点、关键约束… 可直接贴表格或文字"
        @blur="saveRequirement"
      />
      <div class="requirement-actions">
        <a-button type="primary" :loading="generating" @click="generateQuote">
          <template #icon><ThunderboltOutlined /></template>
          生成报价
        </a-button>
        <span class="requirement-actions-hint">本地组合整机方案（选基准机型 + 配 KP），人工确认后转为草稿（一期不调 AI）</span>
      </div>
    </div>

    <!-- 推理过程面板（生成报价后出现） -->
    <ReasoningPanel
      v-if="showReasoning"
      ref="reasoningPanelRef"
      :steps="reasonSteps"
      :plans="reasonPlans"
      :running="reasonRunning"
      :error="reasonError"
      :keywords="reasonKeywords"
      :pending-prompt="reasonPendingPrompt"
      @confirm-plan="confirmPlan"
      @user-reply="onUserReply"
      @user-skip="onUserSkip"
    />
      </div>

      <div class="detail-right">
    <!-- 报价单区域 -->
    <div class="quotation-section">
      <div class="section-header">
        <h2>报价单 <span class="count-badge">{{ quotations.length }}</span></h2>
        <div class="section-actions">
          <a-button v-if="activeSelectMode" size="small" type="primary" @click="handleBatchQuotationDelete">
            <template #icon><DeleteOutlined /></template>
            删除选中 ({{ activeSelectedIds.size }})
          </a-button>
          <a-button v-if="activeSelectMode" size="small" @click="exitActiveSelect">取消</a-button>
          <a-button v-if="!activeSelectMode && quotations.length > 0" size="small" @click="enterActiveSelect">批量操作</a-button>
          <a-button size="small" @click="showUploadModal = true">
            <template #icon><UploadOutlined /></template>
            上传报价
          </a-button>
          <a-button type="primary" size="small" @click="createNewQuotation">
            <template #icon><PlusOutlined /></template>
            新增报价
          </a-button>
        </div>
      </div>

      <!-- 活跃报价单批量操作栏 -->
      <div v-if="activeSelectMode && activeSelectedIds.size > 0" class="batch-bar glass">
        <div class="batch-left">
          <a-checkbox
            :checked="activeSelectedIds.size === quotations.length && quotations.length > 0"
            :indeterminate="activeSelectedIds.size > 0 && activeSelectedIds.size < quotations.length"
            @change="toggleActiveSelectAll"
          >
            全选
          </a-checkbox>
          <span class="batch-count">已选 {{ activeSelectedIds.size }} 项</span>
        </div>
        <div class="batch-actions">
          <a-button danger size="small" @click="handleBatchQuotationDelete">
            <template #icon><DeleteOutlined /></template>
            删除选中
          </a-button>
          <a-button size="small" @click="exitActiveSelect">取消</a-button>
        </div>
      </div>

      <div v-if="quotations.length === 0 && !loading" class="empty-state glass">
        <p>暂无报价单，点击上方按钮创建</p>
      </div>

      <div v-else class="quotation-list glass">
        <div
          v-for="(quo, index) in quotations"
          :key="quo.quotation_id"
          class="quotation-row"
          :class="{ 'selecting': activeSelectMode }"
          :style="{ animationDelay: `${index * 50}ms` }"
          @click="activeSelectMode ? toggleActiveSelect(quo.quotation_id) : viewQuotation(quo)"
        >
          <div v-if="activeSelectMode" class="row-checkbox" @click.stop>
            <a-checkbox
              :checked="activeSelectedIds.has(quo.quotation_id)"
              @change="toggleActiveSelect(quo.quotation_id)"
            />
          </div>
          <div
            class="quo-status-bar"
            :class="getMarginBarClass(quo.profit_margin)"
          ></div>
          <div class="quo-content">
            <div class="quo-top">
              <span v-if="quo.is_primary" class="cpq-led cpq-led--warning">主推</span>
              <span v-if="quo.exported_at" class="quo-state quo-state--exported">已导出</span>
              <span v-else class="quo-state quo-state--draft">草稿</span>
              <span class="quo-name">{{ quo.quotation_name || '未命名报价单' }}</span>
              <span class="quo-price">¥{{ formatPrice(quo.total_price) }}</span>
              <span class="quo-margin-badge" :class="getMarginBadgeClass(quo.profit_margin)">
                {{ quo.profit_margin?.toFixed(2) || '0.00' }}%
              </span>
              <span v-if="(quo.config_count || 0) > 1" class="multi-cfg-tag">综合</span>
            </div>
            <div class="quo-bottom">
              {{ quo.config_count || 0 }}配置 · {{ formatDate(quo.created_at) }}
            </div>
          </div>
          <div v-if="!activeSelectMode" class="quo-actions" @click.stop>
            <button v-if="!quo.is_primary" class="icon-btn" title="设为主推" @click="setAsPrimary(quo)">
              <StarOutlined />
            </button>
            <button v-else class="icon-btn" title="取消主推" @click="setAsPrimary(quo)">
              <StarFilled style="color:var(--cpq-color-warning)" />
            </button>
            <button class="icon-btn" :title="quo.exported_at ? '查看成本' : '编辑'" @click="viewQuotation(quo)">
              <component :is="quo.exported_at ? EyeOutlined : EditOutlined" />
            </button>
            <button
              v-if="!quo.has_cost_snapshot || quo.has_manual_cost"
              class="icon-btn"
              :title="quo.has_manual_cost ? '编辑成本' : '补录成本'"
              @click="openCostForBackfill(quo)"
            >
              <CalculatorOutlined />
            </button>
            <button class="icon-btn" title="重命名" @click="startRenameQuotation(quo)">
              <FormOutlined />
            </button>
            <a-popconfirm
              title="确定要删除这个报价单吗？"
              @confirm="deleteQuotation(quo.quotation_id)"
            >
              <button class="icon-btn danger" title="删除">
                <DeleteOutlined />
              </button>
            </a-popconfirm>
          </div>
          <span v-if="!activeSelectMode" class="quo-arrow">
            <RightOutlined />
          </span>
        </div>
      </div>
    </div>
      <!-- 存档区（移至右栏报价单下方） -->
      <ArchiveSection v-if="opportunity" :opportunity-id="opportunityId" :attachments="feedAttachments" @preview="openAttachmentPreview" @delete="onAttachmentDelete" />
      </div><!-- /detail-right -->
    </div><!-- /detail-grid -->

    <!-- 回收站抽屉 -->
    <a-drawer
      v-model:open="showRecycleBin"
      title="回收站"
      placement="right"
      width="600"
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
              <span class="quo-price">¥{{ formatPrice(quo.total_price) }}</span>
              <span class="quo-margin-badge" :class="getMarginBadgeClass(quo.profit_margin)">
                {{ quo.profit_margin?.toFixed(2) || '0.00' }}%
              </span>
              <span v-if="(quo.config_count || 0) > 1" class="multi-cfg-tag">综合</span>
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

    <!-- 右侧抽屉：商机协作流（消息 + 文件 + 在线状态） -->
    <OpportunitySidebar :opportunity-id="opportunityId" v-model:show-sidebar="showSidebar" />

    <!-- 文件在线预览（图片 / PDF / Excel 在线编辑）-->
    <AttachmentPreviewModal v-model:open="previewOpen" :attachment="previewAttachment" @saved="onPreviewSaved" />

    <!-- 上传报价单 Modal -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传报价单"
      :footer="null"
      :destroyOnClose="true"
      width="500px"
    >
      <p style="color: var(--cpq-text-secondary); font-size: 13px; margin-bottom: 16px;">
        上传后将自动解析并创建报价单，归属到此商机。
      </p>
      <a-upload-dragger
        name="file"
        :custom-request="handleUploadToProject"
        :show-upload-list="false"
        accept=".xlsx, .xls"
      >
        <p class="ant-upload-drag-icon"><inbox-outlined /></p>
        <p class="ant-upload-text">点击或拖拽 Excel 报价单到此区域</p>
        <p class="ant-upload-hint">支持 .xlsx / .xls 格式文件</p>
      </a-upload-dragger>
      <a-spin v-if="uploadStatus === 'loading'" tip="正在解析报价单..." style="display: block; text-align: center; margin: 20px 0;" />
      <a-result v-if="uploadStatus === 'error'" status="error" :title="uploadError" />
    </a-modal>

    <!-- 已导出报价单：成本快照抽屉 -->
    <QuotationCostDrawer
      v-model:open="costDrawerOpen"
      :quotation="costDrawerQuotation"
      :excel-loading="excelLoading"
      :reparse-loading="reparseLoading"
      :save-loading="saveLoading"
      @view-excel="handleViewExcel"
      @reparse="handleReparse"
      @save-cost="handleSaveCost"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import {
  ArrowLeftOutlined, EditOutlined, PlusOutlined, UploadOutlined,
  InboxOutlined, EyeOutlined,
  DeleteOutlined, RightOutlined, MessageOutlined, FormOutlined,
  UndoOutlined, StarOutlined, StarFilled, CalculatorOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue'
import { uploadQuotationToProject } from '@/api/quote'
import { projectApi, quotationApi } from '@/api'
import { feedApi } from '@/api/feed'
import { getFieldsByPage } from '@/api/fields'
import OpportunitySidebar from '@/components/quote/OpportunitySidebar.vue'
import QuotationCostDrawer from '@/components/quote/QuotationCostDrawer.vue'
import ArchiveSection from '@/components/opportunity/ArchiveSection.vue'
import ReasoningPanel from '@/components/opportunity/ReasoningPanel.vue'
import AttachmentPreviewModal from '@/components/feed/AttachmentPreviewModal.vue'
import { reasoningApi } from '@/api/reasoning'
import type { Plan } from '@/api/reasoning'
import { buildPlanCfg } from '@/composables/usePlanBom'
import { useReasoningStream } from '@/composables/useReasoningStream'
import { useFeedSocket } from '@/composables/useFeedSocket'
import type { Opportunity, Quotation } from '@/types/opportunity'
import type { FeedAttachment } from '@/api/feed'

const route = useRoute()
const router = useRouter()
const opportunityId = route.params.opportunityId as string
const opportunityIdRef = computed(() => opportunityId)
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
const requirementText = ref('')

// 推理流（生成报价）：步骤时间线 + 整机方案清单，独立 WS 通道
const {
  steps: reasonSteps, plans: reasonPlans, running: reasonRunning,
  error: reasonError, keywords: reasonKeywords, pendingPrompt: reasonPendingPrompt,
  connect: connectReasoning, disconnect: disconnectReasoning,
} = useReasoningStream()
const reasoningPanelRef = ref<InstanceType<typeof ReasoningPanel> | null>(null)
const showReasoning = ref(false)
const generating = ref(false)

const opportunity = ref<Opportunity | null>(null)
const quotations = ref<Quotation[]>([])
const deletedQuotations = ref<Quotation[]>([])
const loading = ref(false)
const showSidebar = ref(false)
const showRecycleBin = ref(false)

// Active quotation selection
const activeSelectMode = ref(false)
const activeSelectedIds = ref<Set<string>>(new Set())

// Deleted quotation selection
const deletedSelectMode = ref(false)
const deletedSelectedIds = ref<Set<string>>(new Set())

// Rename quotation
const showRenameModal = ref(false)
const renameLoading = ref(false)
const renameValue = ref('')
const renameTargetId = ref<string | null>(null)

// 行内编辑状态
const focusField = ref<string | null>(null)
const focusSnapshot = ref<string | number>('')

// 字段历史值（用于自动完成）
const fieldHistory = ref<Record<string, string[]>>({})

// 从 API 加载字段定义
const infoFields = ref<Array<{ key: string; label: string; editable: boolean; type?: string }>>([])

// 日期格式化：直接取字符串前 10 位，避免 Date 对象的时区转换问题
const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  // 直接取 YYYY-MM-DD 部分，不经过 Date 对象转换（防止 UTC 偏移）
  const slice = dateStr.slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(slice) ? slice : dateStr
}

// 创建日期的可编辑绑定（dayjs 格式用于 a-date-picker）
const createdDateValue = computed(() => {
  const dateStr = opportunity.value?.created_at
  if (!dateStr) return null
  // 直接取日期部分，不经过 formatDate 的时区转换
  const slice = dateStr.slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(slice)) return null
  return dayjs(slice)
})

// 创建日期变更时保存到后端
const onCreatedDateChange = async (date: dayjs.Dayjs | null) => {
  if (!date) return

  // a-date-picker 的 value-format 会把 date 转成字符串
  const newDateStr = typeof date === 'string' ? date : date.format('YYYY-MM-DD')
  const oldDateStr = formatDate(opportunity.value?.created_at || '')

  if (newDateStr === oldDateStr) return

  try {
    // 简化：直接用新日期 + 00:00:00
    const newFull = `${newDateStr} 00:00:00`
    await projectApi.update(opportunityId, { created_at: newFull })

    if (opportunity.value) {
      opportunity.value.created_at = newFull
    }
    message.success('创建日期已更新')
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
  }
}

const formatPrice = (price: number) => {
  if (!price) return '0.00'
  return price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const getMarginBarClass = (margin: number | undefined) => {
  if (margin == null) return 'margin-neutral'
  if (margin >= 10) return 'margin-high'
  if (margin >= 0) return 'margin-mid'
  return 'margin-low'
}

const getMarginBadgeClass = (margin: number | undefined) => {
  if (margin == null) return 'badge-neutral'
  if (margin >= 10) return 'badge-high'
  if (margin >= 0) return 'badge-mid'
  return 'badge-low'
}

// Active quotation selection helpers
const toggleActiveSelect = (id: string) => {
  const s = new Set(activeSelectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  activeSelectedIds.value = s
}

const toggleActiveSelectAll = (checked: boolean) => {
  if (checked) {
    activeSelectedIds.value = new Set(quotations.value.map(q => q.quotation_id))
  } else {
    activeSelectedIds.value = new Set()
  }
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
  try {
    const result = await quotationApi.batchDelete([...activeSelectedIds.value])
    const ok = result.success?.length || 0
    const fail = result.failed?.length || 0
    message.success(`已删除 ${ok} 个报价单` + (fail > 0 ? `，${fail} 个失败` : ''))
    exitActiveSelect()
    await loadProject()
  } catch (err: any) {
    message.error('批量删除失败: ' + (err.message || err))
  }
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
  } catch (err: any) {
    message.error('批量永久删除失败: ' + (err.message || err))
  }
}

const loadProject = async () => {
  loading.value = true
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
    requirementText.value = (meta as any).customer_requirement_text || ''
    quotations.value = quotationsData
  } catch (err: any) {
    message.error('加载商机详情失败')
    router.push('/opportunities')
  } finally {
    loading.value = false
  }
}

// 行内编辑
const onFieldFocus = (field: string) => {
  focusField.value = field
  focusSnapshot.value = (opportunity.value as any)?.[field] ?? ''
  loadFieldHistory(field)
}
const onFieldBlur = (field: string) => {
  if (focusField.value !== field) return
  focusField.value = null
  const cur = ((opportunity.value as any)?.[field] ?? '') as string | number
  if (String(cur) === String(focusSnapshot.value)) return
  saveField(field)
}

// 加载字段历史值（用于自动完成）
const loadFieldHistory = async (fieldKey: string) => {
  if (fieldHistory.value[fieldKey]) return // 已加载
  try {
    const response = await fetch(`/api/opportunities/field-history/${fieldKey}`)
    const result = await response.json()
    fieldHistory.value[fieldKey] = result.values || []
  } catch (err) {
    console.error('加载字段历史失败:', err)
    fieldHistory.value[fieldKey] = []
  }
}

// 获取过滤后的选项（用于 a-auto-complete）
const getFilteredOptions = (fieldKey: string) => {
  const history = fieldHistory.value[fieldKey] || []
  const keyword = ((opportunity.value as any)?.[fieldKey] ?? '').toString().toLowerCase()
  const filtered = keyword
    ? history.filter(v => v.toLowerCase().includes(keyword))
    : history
  return filtered.map(v => ({ value: v, label: v }))
}

// 机箱形态标签式输入：逗号分隔字符串 ↔ 数组互转
const chassisFormTags = computed({
  get: () => {
    const raw = (opportunity.value as any)?.chassis_form || ''
    if (!raw) return []
    return raw.split(',').map((s: string) => s.trim()).filter(Boolean)
  },
  set: (val: string[]) => {
    if (opportunity.value) {
      (opportunity.value as any).chassis_form = val.join(',')
    }
  }
})

// 机箱形态历史选项（用于下拉提示）
const chassisFormOptions = computed(() => {
  const history = fieldHistory.value['chassis_form'] || []
  return history.map(v => ({ value: v, label: v }))
})

// 机箱形态变更时保存
const onChassisFormChange = async (tags: string[]) => {
  const newValue = tags.join(',')
  const oldValue = (opportunity.value as any)?.chassis_form || ''
  if (newValue === oldValue) return
  try {
    await projectApi.update(opportunityId, { chassis_form: newValue })
    if (opportunity.value) {
      (opportunity.value as any).chassis_form = newValue
    }
    message.success('机箱形态已更新')
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
  }
}

const saveField = async (field: string) => {
  const fieldDef = infoFields.value.find(f => f.key === field)
  const raw = (opportunity.value as any)?.[field]
  if (raw == null) return
  let saveValue: string | number = raw
  if ((fieldDef as any)?.type === 'number') {
    saveValue = raw !== '' && raw != null ? Number(raw) : 0
  } else if (!String(raw).trim()) {
    message.warning('字段不能为空')
    return
  }
  try {
    await projectApi.update(opportunityId, { [field]: saveValue })
    focusSnapshot.value = saveValue
    message.success('更新成功')
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
  }
}

// 保存客户需求原文(blur 触发,存 extra_fields)
const saveRequirement = async () => {
  const current = (opportunity.value as any)?.customer_requirement_text || ''
  if (requirementText.value === current) return
  try {
    await projectApi.update(opportunityId, { customer_requirement_text: requirementText.value })
    if (opportunity.value) {
      (opportunity.value as any).customer_requirement_text = requirementText.value
    }
    message.success('客户需求已保存')
  } catch (err: any) {
    message.error('保存失败: ' + (err.message || err))
  }
}

// 删除商机
const handleDeleteProject = async () => {
  try {
    await projectApi.trash(opportunityId)
    message.success('商机已移至回收站')
    router.push('/opportunities')
  } catch (err: any) {
    message.error('删除失败: ' + (err.message || err))
  }
}

// 归档商机
const handleArchive = async () => {
  try {
    await projectApi.updateMeta(opportunityId, { status: 'archived' })
    if (opportunity.value) {
      opportunity.value.status = 'archived'
    }
    message.success('商机已归档')
  } catch (err: any) {
    message.error('归档失败: ' + (err.message || err))
  }
}

// 取消归档
const handleUnarchive = async () => {
  try {
    await projectApi.updateMeta(opportunityId, { status: 'active' })
    if (opportunity.value) {
      opportunity.value.status = 'active'
    }
    message.success('商机已取消归档')
  } catch (err: any) {
    message.error('取消归档失败: ' + (err.message || err))
  }
}

const resultOptions = [
  { value: 'pending', label: '进行中' },
  { value: 'won', label: '已中标' },
  { value: 'lost', label: '已丢标' },
]
async function onResultChange(val: string) {
  const prev = (opportunity.value as any)?.result
  if (val === prev) return
  try {
    await projectApi.updateMeta(opportunityId, { result: val })
    if (opportunity.value) (opportunity.value as any).result = val
    message.success('已更新商机状态')
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
  }
}

// 报价单操作
const createNewQuotation = () => {
  // 一商机一草稿：已有草稿时直接打开，不另建
  const draft = quotations.value.find(q => !q.exported_at && q.status === 'active')
  if (draft) {
    message.info('已有草稿报价单，已为你打开')
    router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${draft.quotation_id}&mode=edit&from=opportunities`)
    return
  }
  router.push(`/workspace?opportunityId=${opportunityId}&mode=create&from=opportunities`)
}

// 生成报价：客户需求 → 本地推理 pipeline（分词 + 检索）→ 推理面板
async function generateQuote() {
  const text = (requirementText.value || '').trim()
  if (!text) {
    message.warning('请先填写客户需求')
    return
  }
  showReasoning.value = true
  generating.value = true
  connectReasoning(opportunityId)
  try {
    await reasoningApi.generate(opportunityId, text)
  } catch (e: any) {
    message.error('启动推理失败：' + (e?.message || e))
    showReasoning.value = false
  } finally {
    generating.value = false
  }
}

// 反答回复：拼到原需求后重跑 pipeline（新一轮，pipeline_id 变化前端自动切）
async function onUserReply(reply: string) {
  const text = (requirementText.value || '').trim()
  generating.value = true
  try {
    await reasoningApi.generate(opportunityId, text, { supplement_text: reply })
  } catch (e: any) {
    message.error('提交补充失败：' + (e?.message || e))
  } finally {
    generating.value = false
  }
}

// 跳过反问：强制走选型（force_complete）
async function onUserSkip() {
  const text = (requirementText.value || '').trim()
  generating.value = true
  try {
    await reasoningApi.generate(opportunityId, text, { force_complete: true })
  } catch (e: any) {
    message.error('启动失败：' + (e?.message || e))
  } finally {
    generating.value = false
  }
}

// 整机方案 → 转为报价单草稿：buildPlanCfg 把 L6 转成基准配置的 BOM 模板格式（live），
// 种进 config_l6_picks（bom_source/bom_template/bom_context/base_config_id/l6_custom_price），
// KP 走 items；工作台载入时左栏 BomTable 按模板格式渲染整机 L6、中栏 KP 卡可编辑调价。
// 无模板时 buildPlanCfg 自动回落 excel 平铺。
async function confirmPlan(plan: Plan) {
  try {
    // 一商机一草稿：已有草稿确认后替换其配置，否则新建（先做这步，避免取消时白跑 buildPlanCfg）
    const draft = quotations.value.find((q) => !q.exported_at && q.status === 'active')
    let quotationId: string
    if (draft) {
      quotationId = draft.quotation_id
      const ok = await new Promise<boolean>((resolve) => {
        Modal.confirm({
          title: '已有草稿',
          content: `商机已存在草稿「${draft.quotation_name || draft.quotation_id}」，是否用本方案替换其配置？`,
          okText: '替换',
          cancelText: '取消',
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
      if (!ok) {
        reasoningPanelRef.value?.stopConfirming()
        return
      }
    } else {
      const res = await quotationApi.create({
        opportunity_id: opportunityId,
        quotation_name: `方案-${plan.name || plan.model}`,
      })
      quotationId = res.quotation_id
    }

    // 转 BOM 模板格式（live）+ 组 seeding payload
    const liveCfg = await buildPlanCfg(plan)
    const picks: Record<string, any> = {
      base_config_id: plan.config_id,
      bom_source: liveCfg.bom_source,
      l6_custom_price: plan.summary.l6_cost ?? 0,
      l6_profit_margin: 10,
    }
    if (liveCfg.bom_source === 'live') {
      picks.bom_template = liveCfg.bom_template
      picks.bom_context = liveCfg.bom_context
    } else {
      picks.bom_excel_rows = liveCfg.bom_excel_rows
    }
    const payload = {
      items: liveCfg.items,
      config_quantities: { CFG1: 1 },
      config_server_models: { CFG1: plan.model || '' },
      config_l6_picks: { CFG1: picks },
    }
    await quotationApi.saveItems(quotationId, payload as any)
    // L3 统一标记来源为推理流（不管新建还是替换已有草稿；失败不阻塞）
    quotationApi.update(quotationId, { source: 'reasoning' }).catch(() => {})
    message.success(`已转为报价单：${plan.name || plan.model}`)
    disconnectReasoning()
    router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${quotationId}&mode=edit&from=opportunities`)
  } catch (e: any) {
    message.error('转为报价单失败：' + (e?.message || e))
    reasoningPanelRef.value?.stopConfirming()
  }
}

// 成本快照抽屉
const costDrawerOpen = ref(false)
const costDrawerQuotation = ref<any>(null)
const excelLoading = ref(false)
const reparseLoading = ref(false)
const saveLoading = ref(false)

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
  // 草稿 → 进工作台编辑
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
  window.open(feedApi.attachments.downloadUrl(att.attachment_id), '_blank')
}

const handleReparse = async () => {
  const quo = costDrawerQuotation.value
  if (!quo) return
  reparseLoading.value = true
  try {
    // 克隆源的 DB items + 配置字段成新草稿（不解析导出件）
    const result = await quotationApi.reparse(quo.quotation_id)
    message.success('已复制为新草稿，正在打开')
    costDrawerOpen.value = false
    await loadProject()
    router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${result.quotation_id}&mode=edit&from=opportunities`)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail && detail.existing_draft_id) {
      message.warning('已有草稿报价单，请先导出或删除当前草稿')
    } else {
      message.error('复制失败：' + (e?.message || e))
    }
  } finally {
    reparseLoading.value = false
  }
}

// 补录成本入口：无快照的历史报价单，开抽屉录整机级成本
const openCostForBackfill = async (quotation: Quotation) => {
  costDrawerQuotation.value = quotation
  costDrawerOpen.value = true
  try {
    const full = await quotationApi.getById(quotation.quotation_id)
    costDrawerQuotation.value = full
  } catch (e) {
    // 保留列表数据兜底
  }
}

const handleSaveCost = async (snapshot: Record<string, any>) => {
  const quo = costDrawerQuotation.value
  if (!quo) return
  saveLoading.value = true
  try {
    const res = await quotationApi.saveCostSnapshot(quo.quotation_id, snapshot)
    message.success('成本已保存')
    costDrawerQuotation.value = res.quotation
    await loadProject()
  } catch (e: any) {
    message.error('保存失败：' + (e?.message || e))
  } finally {
    saveLoading.value = false
  }
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
  } catch (error: any) {
    message.error('恢复失败: ' + (error.message || error))
  }
}

const permanentDeleteQuotation = async (quotationId: string) => {
  try {
    await quotationApi.batchPermanentDelete([quotationId])
    message.success('报价单已永久删除')
    await loadDeletedQuotations()
  } catch (error: any) {
    message.error('删除失败: ' + (error.message || error))
  }
}

const deleteQuotation = async (quotationId: string) => {
  try {
    await quotationApi.delete(quotationId)
    message.success('报价单已删除')
    quotations.value = quotations.value.filter(q => q.quotation_id !== quotationId)
    // 刷新已删除报价单列表
    await loadDeletedQuotations()
  } catch (err: any) {
    message.error('删除失败: ' + (err.message || err))
  }
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
  } catch (err: any) {
    message.error('重命名失败: ' + (err.message || err))
  } finally {
    renameLoading.value = false
  }
}

// =================== Upload Quotation ===================
const showUploadModal = ref(false)
const uploadStatus = ref<'idle' | 'loading' | 'error'>('idle')
const uploadError = ref('')

const handleUploadToProject = async (options: any) => {
  uploadStatus.value = 'loading'
  try {
    const result = await uploadQuotationToProject(options.file, opportunityId)
    if (result.quotation_id) {
      message.success(`报价单已创建！`)
      showUploadModal.value = false
      uploadStatus.value = 'idle'
      uploadError.value = ''
      await loadProject()
    } else {
      throw new Error(result.message || '解析失败')
    }
  } catch (err: any) {
    uploadError.value = err.message || '上传失败'
    uploadStatus.value = 'error'
  }
}

// 加载字段定义
const loadInfoFields = async () => {
  try {
    const fields = await getFieldsByPage('opportunity_detail')
    infoFields.value = fields
      .filter((f: any) => f.enabled)
      .map((f: any) => ({
        key: f.key,
        label: f.label,
        editable: f.permission !== 'readonly',
        type: f.type === 'number' ? 'number' : undefined
      }))
  } catch (err) {
    console.error('加载字段定义失败:', err)
    // 使用默认字段作为 fallback
    infoFields.value = [
      { key: 'customer_name', label: '客户名称', editable: true },
      { key: 'purchase_qty', label: '采购数量', editable: true, type: 'number' },
      { key: 'sales_person', label: '业务/销售', editable: true },
      { key: 'fae', label: 'FAE', editable: true },
      { key: 'quotation_person', label: '报价人', editable: true },
      { key: 'delivery_region', label: '交付地区', editable: true },
      { key: 'delivery_cycle', label: '交付周期', editable: true },
      { key: 'warranty_years', label: '维保年限', editable: true },
    ]
  }
}

onMounted(async () => {
  loadInfoFields()
  loadDeletedQuotations()
  await loadProject()
  feed.load().then(() => feed.connect()).catch(() => {})
})

onBeforeUnmount(() => {
  feed.disconnect()
  disconnectReasoning()
})
</script>

<style scoped>
.opportunity-detail-page {
  padding: 0;
}

/* ── 双栏布局:左证据链(需求+推理) / 右报价单+存档 —— 四六开，右栏优先 ── */
.detail-grid {
  display: grid;
  grid-template-columns: minmax(360px, 2fr) 3fr;
  gap: 24px;
  align-items: start;
}
.detail-left,
.detail-right {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.detail-left > :last-child {
  margin-bottom: 0;
}
@media (max-width: 1100px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}

/* ── Page Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
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
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 4px;
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

.header-result-select {
  width: 108px;
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

.requirement-card {
  padding: 16px 20px;
  margin-bottom: 24px;
}
.requirement-card .card-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}
.requirement-card .card-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.requirement-card .card-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.requirement-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.requirement-actions-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
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
</style>
