<template>
  <div class="opportunity-list-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>商机线索</h1>
        <p class="subtitle">共 {{ pagination.total }} 个商机 · {{ activeCount }} 个进行中</p>
      </div>
      <div class="header-actions">
        <a-button @click="enterSelectMode" v-if="!selectMode" class="batch-btn">
          <template #icon><CheckSquareOutlined /></template>
          批量选择
        </a-button>
        <a-button @click="goToRecycleBin" class="recycle-btn">
          <template #icon><DeleteOutlined /></template>
          回收站
        </a-button>
        <a-button @click="showCreateModal = true" type="primary" class="create-btn">
          <template #icon><PlusOutlined /></template>
          新建商机
        </a-button>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="selectMode && selectedIds.size > 0" class="batch-bar glass">
      <div class="batch-left">
        <a-checkbox
          :checked="selectedIds.size === opportunities.length && opportunities.length > 0"
          :indeterminate="selectedIds.size > 0 && selectedIds.size < opportunities.length"
          @change="toggleSelectAll"
        >
          全选
        </a-checkbox>
        <span class="batch-count">已选 {{ selectedIds.size }} 项</span>
      </div>
      <div class="batch-actions">
        <a-button danger size="small" @click="handleBatchTrash">
          <template #icon><DeleteOutlined /></template>
          移至回收站
        </a-button>
        <a-button size="small" @click="exitSelectMode">取消</a-button>
      </div>
    </div>

    <!-- 玻璃搜索栏 -->
    <div class="search-bar glass">
      <SearchOutlined class="search-icon" />
      <input
        v-model="searchText"
        type="text"
        placeholder="搜索商机名称、客户..."
        class="search-input"
      />
      <div class="search-actions">
        <button
          v-if="searchText"
          class="clear-btn"
          @click="searchText = ''; handleSearch()"
        >
          <CloseCircleOutlined />
        </button>
        <button
          class="refresh-btn"
          :class="{ spinning: isRefreshing }"
          @click="handleRefresh"
        >
          <ReloadOutlined />
        </button>
      </div>
    </div>

    <!-- 列表容器 -->
    <div class="list-container glass">
      <div
        v-for="(opportunity, index) in opportunities"
        :key="opportunity.opportunity_id"
        class="opportunity-row"
        :class="{ 'status-active': opportunity.status === 'active', 'selecting': selectMode }"
        :style="{ animationDelay: `${index * 50}ms` }"
        @click="selectMode ? toggleSelect(opportunity.opportunity_id) : goToDetail(opportunity.opportunity_id)"
      >
        <div v-if="selectMode" class="row-checkbox" @click.stop>
          <a-checkbox
            :checked="selectedIds.has(opportunity.opportunity_id)"
            @change="toggleSelect(opportunity.opportunity_id)"
          />
        </div>
        <div class="status-bar"></div>
        <div class="row-content">
          <div class="row-top">
            <span class="opportunity-name">{{ opportunity.opportunity_name || '未命名商机' }}</span>
            <span class="quotation-badge">{{ opportunity.quotation_count }} 报价</span>
          </div>
          <div class="row-bottom">
            <span>{{ opportunity.customer_name || '—' }}</span>
            <span class="separator">·</span>
            <span>{{ opportunity.platform_type || '—' }} {{ opportunity.chassis_form || '' }}</span>
            <span class="separator">·</span>
            <span>{{ opportunity.purchase_qty || 0 }}台</span>
            <span class="separator">·</span>
            <span>{{ opportunity.config_count || 0 }}配置</span>
            <span class="separator">·</span>
            <span>{{ formatDate(opportunity.created_at) }}</span>
          </div>
        </div>
        <div class="row-right">
          <span class="status-dot" :class="`status-${opportunity.status}`"></span>
          <span class="status-text">{{ getStatusText(opportunity.status) }}</span>
        </div>
        <div v-if="!selectMode" class="row-actions">
          <a-popconfirm
            title="确定要删除这个商机吗？"
            description="删除后可在回收站恢复"
            @confirm.stop="handleDelete(opportunity.opportunity_id)"
            ok-text="确定"
            cancel-text="取消"
          >
            <button class="action-btn delete-btn" @click.stop>
              <DeleteOutlined />
            </button>
          </a-popconfirm>
        </div>
        <div v-if="!selectMode" class="row-arrow">
          <RightOutlined />
        </div>
      </div>

      <div v-if="!loading && opportunities.length === 0" class="empty-state">
        <p>暂无商机</p>
      </div>
    </div>

    <!-- 分页条 -->
    <div v-if="pagination.total > pagination.pageSize" class="pagination-wrapper glass">
      <a-pagination
        v-model:current="pagination.current"
        :total="pagination.total"
        :page-size="pagination.pageSize"
        show-size-changer
        @change="handlePageChange"
      />
    </div>

    <!-- 新建商机弹窗 -->
    <a-modal
      v-model:open="showCreateModal"
      title="新建商机"
      @ok="handleCreate"
      :confirm-loading="creating"
    >
      <a-form layout="vertical">
        <a-form-item label="商机名称" required>
          <a-input v-model:value="newProject.opportunity_name" placeholder="请输入商机名称" />
        </a-form-item>
        <a-form-item label="客户名称">
          <a-input v-model:value="newProject.customer_name" placeholder="请输入客户名称" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, SearchOutlined, CloseCircleOutlined, RightOutlined, DeleteOutlined, CheckSquareOutlined } from '@ant-design/icons-vue'
import { projectApi } from '@/api'
import type { Opportunity } from '@/types/opportunity'

const router = useRouter()

const loading = ref(false)
const creating = ref(false)
const isRefreshing = ref(false)
const opportunities = ref<Opportunity[]>([])
const showCreateModal = ref(false)
const searchText = ref('')

// Selection mode
const selectMode = ref(false)
const selectedIds = ref<Set<string>>(new Set())

const newProject = reactive({
  opportunity_name: '',
  customer_name: ''
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 个商机`
})

const activeCount = computed(() => {
  // Use pagination.total which reflects all active opportunities from backend
  // (backend filters out deleted by default)
  return pagination.total
})

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  return dateStr.substring(0, 10)
}

const getStatusText = (status: string) => {
  const textMap: Record<string, string> = {
    active: '进行中',
    deleted: '已删除',
    archived: '已归档'
  }
  return textMap[status] || status
}

// Selection helpers
const toggleSelect = (opportunityId: string) => {
  const s = new Set(selectedIds.value)
  if (s.has(opportunityId)) s.delete(opportunityId)
  else s.add(opportunityId)
  selectedIds.value = s
}

const toggleSelectAll = (checked: boolean) => {
  if (checked) {
    selectedIds.value = new Set(opportunities.value.map(p => p.opportunity_id))
  } else {
    selectedIds.value = new Set()
  }
}

const exitSelectMode = () => {
  selectMode.value = false
  selectedIds.value = new Set()
}

const handleBatchTrash = async () => {
  if (selectedIds.value.size === 0) return
  try {
    const result = await projectApi.batchTrash([...selectedIds.value])
    const ok = result.success?.length || 0
    const fail = result.failed?.length || 0
    message.success(`已将 ${ok} 个商机移至回收站` + (fail > 0 ? `，${fail} 个失败` : ''))
    exitSelectMode()
    loadProjects()
  } catch (err: any) {
    message.error('批量删除失败: ' + (err.message || err))
  }
}

// Enable select mode from outside (e.g., long press or toolbar button)
const enterSelectMode = () => {
  selectMode.value = true
  selectedIds.value = new Set()
}

// Expose for potential toolbar usage
defineExpose({ enterSelectMode })

// 防抖搜索
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchText, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    handleSearch()
  }, 300)
})

const handleSearch = () => {
  pagination.current = 1
  loadProjects()
}

const handleRefresh = () => {
  isRefreshing.value = true
  loadProjects().finally(() => {
    setTimeout(() => {
      isRefreshing.value = false
    }, 600)
  })
}

const handlePageChange = (page: number, pageSize: number) => {
  pagination.current = page
  pagination.pageSize = pageSize
  loadProjects()
}

const loadProjects = async () => {
  loading.value = true
  try {
    const res = await projectApi.list({
      page: pagination.current,
      page_size: pagination.pageSize,
      search: searchText.value || undefined
    })
    opportunities.value = res.items
    pagination.total = res.total
  } catch (err: any) {
    message.error('加载商机列表失败: ' + (err.message || err))
  } finally {
    loading.value = false
  }
}

const goToDetail = (opportunityId: string) => {
  router.push(`/opportunities/${opportunityId}`)
}

const goToRecycleBin = () => {
  router.push('/recycle-bin')
}

const handleDelete = async (opportunityId: string) => {
  try {
    await projectApi.trash(opportunityId)
    message.success('商机已移至回收站')
    loadProjects()
  } catch (error) {
    message.error('删除失败')
  }
}

const handleCreate = async () => {
  if (!newProject.opportunity_name.trim()) {
    message.warning('请输入商机名称')
    return
  }
  creating.value = true
  try {
    await projectApi.create({
      opportunity_name: newProject.opportunity_name,
      customer_name: newProject.customer_name
    })
    message.success('商机创建成功')
    showCreateModal.value = false
    newProject.opportunity_name = ''
    newProject.customer_name = ''
    loadProjects()
  } catch (err: any) {
    message.error('创建失败: ' + (err.message || err))
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadProjects()
})
</script>

<style scoped>
.opportunity-list-page {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 页面头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left h1 {
  margin: 0 0 4px 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

.create-btn {
  height: 38px;
  padding: 0 20px;
  border-radius: 10px;
  font-weight: 500;
}

/* 批量操作栏 */
.batch-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
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

/* 玻璃搜索栏 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  transition: all var(--cpq-transition-fast);
}

.search-bar:focus-within {
  transform: translateY(-1px);
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a10);
}

.search-icon {
  color: var(--cpq-text-muted);
  font-size: 16px;
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--cpq-text-primary);
  font-size: 14px;
}

.search-input::placeholder {
  color: var(--cpq-text-muted);
}

.search-actions {
  display: flex;
  gap: 8px;
}

.clear-btn,
.refresh-btn {
  background: transparent;
  border: none;
  color: var(--cpq-text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--cpq-transition-fast);
}

.clear-btn:hover,
.refresh-btn:hover {
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}

.refresh-btn.spinning {
  animation: spin 0.6s var(--cpq-ease-out-expo);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 列表容器 */
.list-container {
  padding: 0;
  overflow: hidden;
}

/* 商机行 */
.opportunity-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--cpq-overlay-w4);
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
}

.opportunity-row:last-child {
  border-bottom: none;
}

.opportunity-row:hover {
  background: var(--cpq-overlay-a4);
}

.opportunity-row:hover .status-bar {
  background: var(--cpq-accent-primary);
}

.opportunity-row:hover .row-arrow {
  color: var(--cpq-accent-primary);
  transform: translateX(4px);
}

.opportunity-row:active {
  transform: scale(0.996);
}

.opportunity-row.status-active .status-bar {
  box-shadow: 0 0 8px var(--cpq-overlay-a30);
}

/* 选择模式下点击不缩放 */
.opportunity-row.selecting:active {
  transform: none;
}

/* 复选框列 */
.row-checkbox {
  display: flex;
  align-items: center;
  padding-right: 4px;
}

/* 状态色条 */
.status-bar {
  width: 3px;
  height: 100%;
  min-height: 48px;
  background: transparent;
  border-radius: 2px;
  transition: all var(--cpq-transition-fast);
}

.opportunity-row.status-active .status-bar {
  background: var(--cpq-accent-primary);
}

/* 主内容区 */
.row-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.opportunity-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.quotation-badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
  border: 1px solid var(--cpq-overlay-a20);
  border-radius: 10px;
  padding: 2px 8px;
}

.row-bottom {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

.separator {
  color: var(--cpq-text-muted);
}

/* 右侧状态区 */
.row-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* 操作按钮区 */
.row-actions {
  display: flex;
  align-items: center;
  margin-right: 12px;
  opacity: 0;
  transition: opacity var(--cpq-transition-fast);
}

.opportunity-row:hover .row-actions {
  opacity: 1;
}

.action-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--cpq-transition-fast);
}

.action-btn:hover {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
}

.delete-btn:hover {
  background: var(--cpq-overlay-danger10);
  color: var(--cpq-accent-danger);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
}

.status-dot.status-active {
  background: var(--cpq-accent-primary);
  box-shadow: 0 0 6px var(--cpq-overlay-a40);
}

.status-dot.status-deleted {
  background: var(--cpq-accent-danger);
}

.status-dot.status-archived {
  background: var(--cpq-text-muted);
}

.status-text {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

/* 箭头 */
.row-arrow {
  color: var(--cpq-text-muted);
  font-size: 12px;
  transition: all var(--cpq-transition-fast);
}

/* 空状态 */
.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--cpq-text-muted);
}

/* 分页条 */
.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 16px;
}

/* 动画 */
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
</style>
