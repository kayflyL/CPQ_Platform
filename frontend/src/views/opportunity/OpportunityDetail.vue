<template>
  <div class="opportunity-detail-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="router.push('/opportunities')">
          <ArrowLeftOutlined />
        </button>
        <h1>{{ opportunity?.opportunity_name || '加载中...' }}</h1>
        <span v-if="opportunity" class="status-indicator">
          <span class="status-dot" :class="`status-${opportunity.status}`"></span>
          <span class="status-label">{{ getStatusText(opportunity.status) }}</span>
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
        <a-button size="small" @click="showSidebar = !showSidebar">
          <template #icon><FolderOutlined /></template>
          文件/评论
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
        <span class="info-status-dot" :class="`status-${opportunity.status}`"></span>
        <span>商机状态：{{ getStatusText(opportunity.status) }}｜创建于 {{ formatDate(opportunity.created_at) }}｜更新于 {{ formatDate(opportunity.updated_at) }}</span>
      </div>

      <div
        v-for="field in infoFields"
        :key="field.key"
        class="info-row"
      >
        <span class="info-label">{{ field.label }}</span>
        <span class="info-value">
          <template v-if="editingField === field.key">
            <a-input-number
              v-if="(field as any).type === 'number'"
              v-model:value="editValue"
              size="small"
              style="width: 220px"
              @pressEnter="saveField(field.key)"
              :min="0"
            />
            <a-input
              v-else
              v-model:value="editValue"
              size="small"
              style="width: 220px"
              @pressEnter="saveField(field.key)"
            />
            <button class="inline-btn confirm" @click="saveField(field.key)">
              <CheckOutlined />
            </button>
            <button class="inline-btn cancel" @click="cancelEdit">
              <CloseOutlined />
            </button>
          </template>
          <template v-else>
            {{ (opportunity as any)[field.key] || '-' }}
            <button
              v-if="field.editable"
              class="edit-icon-btn"
              @click="startEdit(field.key, (opportunity as any)[field.key])"
            >
              <EditOutlined />
            </button>
          </template>
        </span>
      </div>
    </div>

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
              <span class="quo-name">{{ quo.quotation_name || '未命名报价单' }}</span>
              <span class="quo-price">¥{{ formatPrice(quo.total_price) }}</span>
              <span class="quo-margin-badge" :class="getMarginBadgeClass(quo.profit_margin)">
                {{ quo.profit_margin?.toFixed(2) || '0.00' }}%
              </span>
            </div>
            <div class="quo-bottom">
              {{ quo.platform_type || '未分类' }} · {{ quo.total_qty || 0 }}台 · {{ quo.config_count || 0 }}配置 · {{ formatDate(quo.created_at) }}
            </div>
          </div>
          <div v-if="!activeSelectMode" class="quo-actions" @click.stop>
            <button class="text-btn" @click="viewQuotation(quo)">
              <EyeOutlined /> 查看
            </button>
            <button class="text-btn" @click="editQuotation(quo)">
              <EditOutlined /> 编辑
            </button>
            <button class="text-btn" @click="startRenameQuotation(quo)">
              <FormOutlined /> 重命名
            </button>
            <a-popconfirm
              title="确定要删除这个报价单吗？"
              @confirm="deleteQuotation(quo.quotation_id)"
            >
              <button class="text-btn danger">
                <DeleteOutlined /> 删除
              </button>
            </a-popconfirm>
          </div>
          <span v-if="!activeSelectMode" class="quo-arrow">
            <RightOutlined />
          </span>
        </div>
      </div>
    </div>

    <!-- 已删除报价单区域 -->
    <div v-if="deletedQuotations.length > 0" class="quotation-section deleted-section">
      <div class="section-header">
        <h2>已删除报价单 <span class="count-badge deleted badge">{{ deletedQuotations.length }}</span></h2>
        <div class="section-actions">
          <a-button v-if="deletedSelectMode" size="small" type="primary" @click="handleBatchRestoreQuotations">恢复选中 ({{ deletedSelectedIds.size }})</a-button>
          <a-button v-if="deletedSelectMode" size="small" danger @click="handleBatchPermanentDeleteQuotations">删除选中 ({{ deletedSelectedIds.size }})</a-button>
          <a-button v-if="deletedSelectMode" size="small" @click="exitDeletedSelect">取消</a-button>
          <a-button v-if="!deletedSelectMode" size="small" @click="enterDeletedSelect">批量操作</a-button>
          <a-button size="small" @click="loadDeletedQuotations">
            🔄 刷新
          </a-button>
        </div>
      </div>

      <!-- 已删除报价单批量操作栏 -->
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

      <div class="quotation-list glass">
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
            </div>
            <div class="quo-bottom">
              {{ quo.platform_type || '未分类' }} · {{ quo.total_qty || 0 }}台 · {{ quo.config_count || 0 }}配置 · {{ formatDate(quo.created_at) }}
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
    </div>

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

    <!-- 右侧抽屉：商机文件 + 评论 -->
    <OpportunitySidebar :opportunity-id="opportunityId" :show-sidebar="showSidebar" />

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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined, EditOutlined, PlusOutlined, UploadOutlined,
  InboxOutlined, CheckOutlined, CloseOutlined, EyeOutlined,
  DeleteOutlined, RightOutlined, FolderOutlined, FormOutlined,
  UndoOutlined
} from '@ant-design/icons-vue'
import { uploadQuotationToProject } from '@/api/quote'
import { projectApi, quotationApi } from '@/api'
import OpportunitySidebar from '@/components/quote/OpportunitySidebar.vue'
import type { Opportunity, Quotation } from '@/types/opportunity'

const route = useRoute()
const router = useRouter()
const opportunityId = route.params.opportunityId as string

const opportunity = ref<Opportunity | null>(null)
const quotations = ref<Quotation[]>([])
const deletedQuotations = ref<Quotation[]>([])
const loading = ref(false)
const showSidebar = ref(false)

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
const editingField = ref<string | null>(null)
const editValue = ref('')

const infoFields = [
  { key: 'opportunity_name', label: '商机名称', editable: true },
  { key: 'customer_name', label: '客户名称', editable: true },
  { key: 'total_qty', label: '台数', editable: true, type: 'number' },
  { key: 'platform_type', label: '平台类型', editable: true },
  { key: 'chassis_form', label: '机箱形态', editable: true },
  { key: 'sales_person', label: '业务/销售', editable: true },
  { key: 'fae', label: 'FAE', editable: true },
  { key: 'opportunity_id', label: '商机ID', editable: false },
]

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toISOString().slice(0, 10)
}

const formatPrice = (price: number) => {
  if (!price) return '0.00'
  return price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = { active: '进行中', deleted: '已删除', archived: '已归档' }
  return map[status] || status
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
      opportunity_id: meta.opportunity_id,
      folder_name: meta.folder_name || '',
      opportunity_name: meta.opportunity_name,
      customer_name: meta.customer_name,
      sales_person: meta.sales_person || '',
      fae: meta.fae || '',
      total_qty: meta.total_qty || 0,
      platform_type: meta.platform_type || '',
      chassis_form: meta.chassis_form || '',
      status: meta.status || 'active',
      created_at: meta.created_at || '',
      updated_at: meta.updated_at || '',
      quotation_count: quotationCount,
      config_count: configCount,
    }
    quotations.value = quotationsData
  } catch (err: any) {
    message.error('加载商机详情失败')
    router.push('/opportunities')
  } finally {
    loading.value = false
  }
}

// 行内编辑
const startEdit = (field: string, currentValue: any) => {
  editingField.value = field
  editValue.value = currentValue ?? ''
}

const cancelEdit = () => {
  editingField.value = null
  editValue.value = ''
}

const saveField = async (field: string) => {
  const fieldDef = infoFields.find(f => f.key === field)
  let saveValue = editValue.value
  if ((fieldDef as any)?.type === 'number') {
    saveValue = editValue.value != null ? Number(editValue.value) : 0
  } else if (!editValue.value.trim()) {
    message.warning('字段不能为空')
    return
  }
  try {
    await projectApi.update(opportunityId, { [field]: saveValue })
    if (opportunity.value) {
      (opportunity.value as any)[field] = saveValue
    }
    message.success('更新成功')
    cancelEdit()
  } catch (err: any) {
    message.error('更新失败: ' + (err.message || err))
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

// 报价单操作
const createNewQuotation = () => {
  router.push(`/workspace?opportunityId=${opportunityId}&mode=create&from=opportunities`)
}

const editQuotation = (quotation: Quotation) => {
  router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${quotation.quotation_id}&mode=edit&from=opportunities`)
}

const viewQuotation = (quotation: Quotation) => {
  router.push(`/workspace?opportunityId=${opportunityId}&quotationId=${quotation.quotation_id}&mode=view&from=opportunities`)
}

const loadDeletedQuotations = async () => {
  try {
    const response = await quotationApi.list(opportunityId, { include_deleted: true })
    deletedQuotations.value = response.filter(q => q.status === 'deleted')
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
    await quotationApi.delete(quotationId)
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

onMounted(() => {
  loadProject()
  loadDeletedQuotations()
})
</script>

<style scoped>
.opportunity-detail-page {
  padding: 0;
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
  border-color: rgba(255, 255, 255, 0.14);
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

.status-dot.status-active {
  background: var(--cpq-accent-primary);
  box-shadow: 0 0 6px var(--cpq-overlay-a40);
}

.status-dot.status-deleted {
  background: var(--cpq-accent-danger, var(--cpq-accent-danger));
}

.status-dot.status-archived {
  background: var(--cpq-text-muted);
}

.status-label {
  font-size: 13px;
  color: var(--cpq-text-muted);
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
  grid-template-columns: 1fr 1fr;
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

.info-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.info-status-dot.status-active {
  background: var(--cpq-accent-primary);
}

.info-status-dot.status-deleted {
  background: var(--cpq-accent-danger, var(--cpq-accent-danger));
}

.info-status-dot.status-archived {
  background: var(--cpq-text-muted);
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

.edit-icon-btn {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  opacity: 0;
  transition: all var(--cpq-transition-fast);
}

.info-row:hover .edit-icon-btn {
  opacity: 1;
}

.edit-icon-btn:hover {
  background: var(--cpq-overlay-a8);
  color: var(--cpq-accent-primary);
}

.inline-btn {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  transition: all var(--cpq-transition-fast);
}

.inline-btn.confirm {
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-primary);
}

.inline-btn.confirm:hover {
  background: var(--cpq-overlay-a20);
}

.inline-btn.cancel {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-muted);
}

.inline-btn.cancel:hover {
  background: var(--cpq-overlay-w10);
  color: var(--cpq-text-primary);
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
  border-radius: 10px;
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
  background: var(--cpq-accent-danger, var(--cpq-accent-danger));
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

.quo-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.quo-price {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-accent-primary);
}

.quo-margin-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid;
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
  color: var(--cpq-accent-danger, var(--cpq-accent-danger));
  background: rgba(255, 77, 79, 0.08);
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
}

.quotation-row:hover .quo-actions {
  opacity: 1;
}

.text-btn {
  padding: 4px 8px;
  border-radius: 6px;
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
  color: var(--cpq-accent-danger, var(--cpq-accent-danger)) !important;
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
