<template>
  <div class="l6-pricing-page">
    <!-- =================== Page Header =================== -->
    <div class="page-header">
      <div class="page-title">
        <h1>L6 整机价格库</h1>
        <p class="subtitle">按机型分组浏览和管理历史报价记录</p>
      </div>
      <div class="page-actions">
        <a-button type="primary" class="btn-accent" @click="openCreateModal">
          <template #icon><PlusOutlined /></template>
          新增记录
        </a-button>
      </div>
    </div>

    <!-- =================== Main Tabs =================== -->
    <div class="tabs-container glass">
      <a-tabs v-model:activeKey="activeTab" class="glass-pill-tabs">
        <a-tab-pane key="records">
          <template #tab>
            <span>价格记录 <a-badge :count="totalRecords" :number-style="{ backgroundColor: 'var(--cpq-accent-primary)', color: 'var(--cpq-bg-primary)' }" /></span>
          </template>
          
          <!-- =================== Toolbar =================== -->
          <div class="toolbar glass">
            <a-input
              v-model:value="searchText"
              placeholder="搜索机型、主板、机箱..."
              class="search-input"
              @pressEnter="loadData"
              allow-clear
            >
              <template #prefix><SearchOutlined style="color: var(--cpq-text-muted)" /></template>
            </a-input>
            
            <span class="item-count">共 {{ groups.length }} 个机型，{{ totalRecords }} 条记录</span>
            
            <a-select v-model:value="sortBy" class="sort-select">
              <a-select-option value="name-asc">机型 A→Z</a-select-option>
              <a-select-option value="name-desc">机型 Z→A</a-select-option>
              <a-select-option value="count-desc">配置数 多→少</a-select-option>
              <a-select-option value="count-asc">配置数 少→多</a-select-option>
              <a-select-option value="price-asc">价格 低→高</a-select-option>
              <a-select-option value="price-desc">价格 高→低</a-select-option>
            </a-select>
            
            <a-button 
              @click="showFilterPanel = !showFilterPanel" 
              :class="['filter-btn', { 'active-filter': showFilterPanel }]"
            >
              <template #icon><FilterOutlined /></template>
              规格匹配
            </a-button>
            
            <a-button type="primary" class="btn-accent" @click="openCreateModal">
              <template #icon><PlusOutlined /></template>
              新增记录
            </a-button>
          </div>

          <!-- =================== Shared Filter Panel =================== -->
          <div v-if="showFilterPanel" class="filter-wrapper glass">
            <L6SpecFilter :records="allRecords" @filter-change="onFilterChange" />
          </div>

          <!-- =================== Loading =================== -->
          <div v-if="loading" class="loading-state">
            <a-spin tip="加载中..." />
          </div>

          <!-- =================== Grouped Cards =================== -->
          <div v-if="!loading" class="group-list">
            <div
              v-for="group in sortedGroups"
              :key="group.model"
              class="model-group glass"
            >
              <!-- Parent Card (Model Header) -->
              <div class="group-header" @click="toggleGroup(group.model)">
                <div class="group-info">
                  <span class="expand-icon" :class="{ 'expanded': expandedModelss.has(group.model) }">▸</span>
                  <span class="model-title">{{ group.model }}</span>
                  <span class="count-pill">{{ group.count }} 个配置</span>
                </div>
                <div class="group-price-range">
                  <template v-if="group.price_min === group.price_max">
                    <span class="price-single">¥ {{ formatPrice(group.price_min) }}</span>
                  </template>
                  <template v-else>
                    <span class="price-min">¥ {{ formatPrice(group.price_min) }}</span>
                    <span class="price-separator">~</span>
                    <span class="price-max">¥ {{ formatPrice(group.price_max) }}</span>
                  </template>
                </div>
              </div>

              <!-- Child Cards (Records) -->
              <div class="records-wrapper" :class="{ 'expanded': expandedModelss.has(group.model) }">
                <div class="records-grid">
                  <draggable
                    v-model="group.records"
                    item-key="id"
                    class="drag-area"
                    ghost-class="ghost"
                    @end="onDragEnd(group.model)"
                  >
                    <template #item="{ element: record }">
                      <L6RecordCard 
                        :record="record" 
                        :show-actions="true" 
                        :matched="isRecordMatched(record)"
                        @edit="openEditModal(record)"
                        @delete="deleteRecord(record.id)"
                      />
                    </template>
                  </draggable>
                </div>
              </div>
            </div>
          </div>

          <!-- =================== Empty State =================== -->
          <div v-if="!loading && groups.length === 0" class="empty-state glass">
            <template v-if="searchText">未找到匹配的记录</template>
            <template v-else>暂无数据，点击"新增记录"添加</template>
          </div>
        </a-tab-pane>

        <a-tab-pane key="matching-rules">
          <template #tab>
            <span>匹配规则</span>
          </template>
          <MatchingRulesConfig />
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- =================== Edit/Create Modal =================== -->
    <a-modal
      v-model:open="modalVisible"
      :title="isEditing ? '编辑L6记录' : '新增L6记录'"
      @ok="saveRecord"
      :confirmLoading="saving"
      width="640px"
      ok-text="保存"
      cancel-text="取消"
    >
      <div class="edit-form">
        <div class="form-section-title">基础信息</div>
        <div class="form-row">
          <label>机型 <span class="required">*</span></label>
          <a-input v-model:value="editForm.model" placeholder="如：R4300" />
        </div>
        <div class="form-row">
          <label>机箱 <span class="required">*</span></label>
          <a-input v-model:value="editForm.chassis" placeholder="如：2U" />
        </div>
        <div class="form-row">
          <label>价格 <span class="required">*</span></label>
          <a-input-number v-model:value="editForm.price" :min="0" :step="0.01" style="width: 100%" placeholder="整机基准价" />
        </div>

        <div class="form-section-title">配置详情</div>
        <div class="form-row">
          <label>主板</label>
          <a-input v-model:value="editForm.motherboard" placeholder="主板型号" />
        </div>
        <div class="form-row">
          <label>背板</label>
          <a-input v-model:value="editForm.backplane" placeholder="背板型号" />
        </div>
        <div class="form-row">
          <label>盘位</label>
          <a-input v-model:value="editForm.drive_bays" placeholder="如：12" />
        </div>
        <div class="form-row">
          <label>电源</label>
          <a-input v-model:value="editForm.psu" placeholder="电源规格" />
        </div>
        <div class="form-row">
          <label>GPU扩展</label>
          <a-input v-model:value="editForm.gpu_expansion" placeholder="GPU扩展信息" />
        </div>
        <div class="form-row">
          <label>导轨</label>
          <a-input v-model:value="editForm.rail_kit" placeholder="导轨型号" />
        </div>
        <div class="form-row">
          <label>电源线</label>
          <a-input v-model:value="editForm.power_cord" placeholder="电源线规格" />
        </div>

        <div class="form-section-title">其他</div>
        <div class="form-row">
          <label>更新日期</label>
          <a-input v-model:value="editForm.update_date" placeholder="YYYY-MM-DD（留空自动填充）" />
        </div>
        <div class="form-row">
          <label>备注</label>
          <a-textarea v-model:value="editForm.note" :rows="2" placeholder="备注信息" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined, FilterOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import axios from 'axios'
import L6SpecFilter from '@/components/L6SpecFilter.vue'
import L6RecordCard from '@/components/L6RecordCard.vue'
import MatchingRulesConfig from './MatchingRulesConfig.vue'
import type { L6Record } from '@/types/l6'

// =================== Tabs ===================
const activeTab = ref('records')

// =================== Data ===================
const groups = ref<any[]>([])
const loading = ref(false)
const searchText = ref('')
const sortBy = ref('name-asc')
const expandedModelss = ref(new Set<string>())

// =================== Filter Panel ===================
const showFilterPanel = ref(false)
const matchedIds = ref(new Set<number>())

const allRecords = computed(() => {
  return groups.value.flatMap(g => g.records)
})

const isRecordMatched = (record: any) => {
  if (!showFilterPanel.value) return false
  return matchedIds.value.has(record.id)
}

const onFilterChange = (matched: any[], hasFilter: boolean) => {
  matchedIds.value = new Set(hasFilter ? matched.map(r => r.id) : [])
  showFilterPanel.value = true
}

const totalRecords = computed(() => {
  return groups.value.reduce((sum, g) => sum + g.count, 0)
})

const sortedGroups = computed(() => {
  const items = [...groups.value]
  const [field, direction] = sortBy.value.split('-')

  items.sort((a, b) => {
    let valA, valB
    if (field === 'name') {
      valA = a.model.toLowerCase()
      valB = b.model.toLowerCase()
    } else if (field === 'count') {
      valA = a.count
      valB = b.count
    } else if (field === 'price') {
      valA = a.price_min
      valB = b.price_min
    }
    if (valA < valB) return direction === 'asc' ? -1 : 1
    if (valA > valB) return direction === 'asc' ? 1 : -1
    return 0
  })

  return items
})

// =================== Load Data ===================
const loadData = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/admin/l6/grouped', {
      params: { search: searchText.value }
    })
    groups.value = res.data.groups || []
  } catch (e: any) {
    message.error('加载数据失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

// =================== Toggle Group ===================
const toggleGroup = (model: string) => {
  const newSet = new Set(expandedModelss.value)
  if (newSet.has(model)) {
    newSet.delete(model)
  } else {
    newSet.add(model)
  }
  expandedModelss.value = newSet
}

// =================== Edit/Create Modal ===================
const modalVisible = ref(false)
const isEditing = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)

const emptyForm = () => ({
  model: '',
  chassis: '',
  motherboard: '',
  backplane: '',
  gpu_expansion: '',
  psu: '',
  drive_bays: '',
  rail_kit: '',
  power_cord: '',
  price: 0,
  update_date: '',
  note: ''
})

const editForm = ref(emptyForm())

const openCreateModal = () => {
  isEditing.value = false
  editingId.value = null
  editForm.value = emptyForm()
  modalVisible.value = true
}

const openEditModal = (record: any) => {
  isEditing.value = true
  editingId.value = record.id
  editForm.value = {
    model: record.model || '',
    chassis: record.chassis || '',
    motherboard: record.motherboard || '',
    backplane: record.backplane || '',
    gpu_expansion: record.gpu_expansion || '',
    psu: record.psu || '',
    drive_bays: record.drive_bays || '',
    rail_kit: record.rail_kit || '',
    power_cord: record.power_cord || '',
    price: record.price || 0,
    update_date: record.update_date || '',
    note: record.note || ''
  }
  modalVisible.value = true
}

const saveRecord = async () => {
  // 验证必填字段
  if (!editForm.value.model) {
    message.warning('请填写机型')
    return
  }
  if (!editForm.value.chassis) {
    message.warning('请填写机箱')
    return
  }
  if (!editForm.value.price || editForm.value.price <= 0) {
    message.warning('请填写有效价格')
    return
  }

  saving.value = true
  try {
    if (isEditing.value && editingId.value) {
      // 更新
      await axios.post('/api/admin/l6/update', {
        id: editingId.value,
        ...editForm.value
      })
      message.success('更新成功')
    } else {
      // 新增
      await axios.post('/api/admin/l6/create', editForm.value)
      message.success('新增成功')
    }
    modalVisible.value = false
    loadData()
  } catch (e: any) {
    message.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

// =================== Delete ===================
const deleteRecord = async (id: number) => {
  try {
    await axios.delete(`/api/admin/l6/${id}`)
    message.success('删除成功')
    loadData()
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// =================== Drag & Drop ===================
const onDragEnd = async (model: string) => {
  const group = groups.value.find(g => g.model === model)
  if (!group) return

  const items = group.records.map((record: any, index: number) => ({
    id: record.id,
    sort_order: index
  }))

  try {
    await axios.put('/api/admin/l6/sort-order', { items })
    message.success('排序已保存')
  } catch (e: any) {
    message.error('保存排序失败: ' + (e.response?.data?.detail || e.message))
    loadData() // Reload to revert changes
  }
}

// =================== Utils ===================
const formatPrice = (val: any) => {
  if (val == null) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// =================== Init ===================
onMounted(() => {
  loadData()
})
</script>

<style scoped>
/* ===== Page Container ===== */
.l6-pricing-page {
  padding: 24px 32px;
  background: var(--cpq-bg-primary);
  min-height: 100vh;
  color: var(--cpq-text-primary);
}

/* ===== Glass Effect Base ===== */
.glass {
  background: var(--cpq-overlay-w3);
  backdrop-filter: blur(24px);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 12px;
}

.glass-deep {
  background: var(--cpq-overlay-b20);
  backdrop-filter: blur(24px);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 8px;
}

/* ===== Page Header ===== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-title h1 {
  margin: 0 0 4px 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.page-title .subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--cpq-text-muted);
}

.page-actions {
  display: flex;
  gap: 12px;
}

/* ===== Buttons ===== */
.btn-accent {
  background: var(--cpq-accent-primary) !important;
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-bg-primary) !important;
  font-weight: 500;
}

.btn-accent:hover {
  background: color-mix(in srgb, var(--cpq-accent-primary) 85%, white) !important;
  border-color: color-mix(in srgb, var(--cpq-accent-primary) 85%, white) !important;
}

.btn-outline {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
}

.btn-outline:hover {
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
}

/* ===== Tabs Container ===== */
.tabs-container {
  padding: 20px;
  margin-bottom: 20px;
}

/* ===== Glass Pill Tabs ===== */
.glass-pill-tabs :deep(.ant-tabs-nav) {
  margin: 0 0 20px 0;
  padding: 4px;
  background: var(--cpq-overlay-b20);
  border-radius: 8px;
  border: 1px solid var(--cpq-overlay-w6);
}

.glass-pill-tabs :deep(.ant-tabs-tab) {
  padding: 8px 20px;
  margin: 0;
  border-radius: 6px;
  transition: all var(--cpq-transition-fast, 0.2s);
  color: var(--cpq-text-secondary);
}

.glass-pill-tabs :deep(.ant-tabs-tab:hover) {
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w5);
}

.glass-pill-tabs :deep(.ant-tabs-tab-active) {
  background: var(--cpq-overlay-a10) !important;
  border-bottom: 2px solid var(--cpq-accent-primary);
}

.glass-pill-tabs :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--cpq-accent-primary) !important;
}

.glass-pill-tabs :deep(.ant-tabs-ink-bar) {
  display: none;
}

/* ===== Toolbar ===== */
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

/* ===== Search Input ===== */
.search-input {
  width: 280px;
}

.search-input :deep(.ant-input) {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
}

.search-input :deep(.ant-input:focus),
.search-input :deep(.ant-input-focused) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a10) !important;
}

.search-input :deep(.ant-input-clear-icon) {
  color: var(--cpq-text-muted) !important;
}

/* ===== Sort Select ===== */
.sort-select {
  width: 160px;
}

.sort-select :deep(.ant-select-selector) {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
}

.sort-select :deep(.ant-select-selector:hover) {
  border-color: var(--cpq-accent-primary) !important;
}

.sort-select :deep(.ant-select-arrow) {
  color: var(--cpq-text-muted) !important;
}

/* ===== Filter Button ===== */
.filter-btn {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
}

.filter-btn:hover {
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
}

.filter-btn.active-filter {
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: var(--cpq-overlay-a10) !important;
}

/* ===== Item Count ===== */
.item-count {
  color: var(--cpq-text-muted);
  font-size: 13px;
  margin-left: auto;
}

/* ===== Filter Wrapper ===== */
.filter-wrapper {
  padding: 16px;
  margin-bottom: 20px;
}

/* ===== Loading / Empty ===== */
.loading-state, .empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--cpq-text-muted);
  font-size: 14px;
}

.empty-state {
  padding: 40px 20px;
}

/* ===== Group List ===== */
.group-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Model Group ===== */
.model-group {
  padding: 0;
  overflow: hidden;
}

/* ===== Group Header ===== */
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  transition: background var(--cpq-transition-fast, 0.2s);
}

.group-header:hover {
  background: var(--cpq-overlay-w3);
}

.group-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.expand-icon {
  font-size: 12px;
  color: var(--cpq-text-muted);
  transition: transform var(--cpq-transition-fast, 0.2s);
  display: inline-block;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.model-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.count-pill {
  padding: 2px 10px;
  background: var(--cpq-overlay-a15);
  color: var(--cpq-accent-primary);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

/* ===== Price Range ===== */
.group-price-range {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.price-single, .price-min, .price-max {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-accent-primary);
  font-variant-numeric: tabular-nums;
}

.price-separator {
  color: var(--cpq-text-muted);
  font-size: 12px;
}

/* ===== Records Wrapper (for animation) ===== */
.records-wrapper {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-height 0.3s ease, opacity 0.3s ease;
}

.records-wrapper.expanded {
  max-height: 5000px;
  opacity: 1;
}

/* ===== Records Grid ===== */
.records-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  padding: 0 20px 20px;
}

/* ===== Drag Area ===== */
.drag-area {
  display: contents;
}

/* ===== Record Card Ghost (for drag-and-drop) ===== */
.record-card.ghost {
  opacity: 0.4;
  border: 2px dashed var(--cpq-accent-primary);
}

/* ===== Edit Form ===== */
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  margin-top: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--cpq-overlay-w10);
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-row label {
  width: 80px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--cpq-text-secondary);
  text-align: right;
}

.form-row .required {
  color: var(--cpq-accent-danger, var(--cpq-accent-danger));
}

.form-row > :not(label) {
  flex: 1;
}
</style>
