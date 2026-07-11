<template>
  <div class="base-pricing-page">
    <!-- =================== Page Header =================== -->
    <div class="page-header">
      <h2>🔧 KP价格库</h2>
      <a-radio-group v-model:value="viewMode" button-style="solid" size="small">
        <a-radio-button value="card">
          <template #icon><AppstoreOutlined /></template>
          卡片
        </a-radio-button>
        <a-radio-button value="table">
          <template #icon><UnorderedListOutlined /></template>
          表格
        </a-radio-button>
      </a-radio-group>
    </div>

    <!-- =================== KP Cards =================== -->
    <div v-if="viewMode === 'card'">
      <!-- Category Cards Row -->
      <div class="category-row">
        <div
          v-for="cat in categories"
          :key="cat.category"
          :class="['category-card', { active: selectedCategory === cat.category }]"
          @click="selectCategory(cat.category)"
        >
          <span class="cat-name">{{ cat.category }}</span>
          <span class="cat-count">{{ cat.count }}</span>
        </div>
      </div>

      <!-- Search Bar -->
      <div class="toolbar" v-if="selectedCategory">
        <a-input-search
          v-model:value="kpSearch"
          placeholder="搜索型号或备注..."
          style="width: 280px"
          @search="loadCategoryItems"
          allow-clear
        />
        <span class="item-count">共 {{ sortedItems.length }} 个型号</span>
        <a-select v-model:value="sortBy" style="width: 160px" @change="onSortChange">
          <a-select-option value="name-asc">名称 A→Z</a-select-option>
          <a-select-option value="name-desc">名称 Z→A</a-select-option>
          <a-select-option value="price-asc">价格 低→高</a-select-option>
          <a-select-option value="price-desc">价格 高→低</a-select-option>
          <a-select-option value="date-desc">日期 最新优先</a-select-option>
          <a-select-option value="date-asc">日期 最早优先</a-select-option>
          <a-select-option value="records-desc">记录数 多→少</a-select-option>
          <a-select-option value="records-asc">记录数 少→多</a-select-option>
        </a-select>
      </div>

      <!-- Model Cards Grid -->
      <div class="card-grid" v-if="selectedCategory && !kpLoading">
        <div
          v-for="item in sortedItems"
          :key="item.id"
          class="model-card"
        >
          <!-- Card Header -->
          <div class="card-header">
            <span class="model-name" :title="item.model">{{ item.model }}</span>
            <div class="card-actions">
              <a-button type="text" size="small" class="edit-btn" @click="openEditModal(item)">✏️</a-button>
              <a-button type="text" size="small" class="chart-btn" @click="toggleHistory(item)">📈</a-button>
            </div>
          </div>

          <!-- Price -->
          <div class="card-price">
            <span class="price-value">¥ {{ formatPrice(item.price) }}</span>
            <span class="price-currency">{{ item.currency || 'RMB' }}</span>
          </div>

          <!-- Meta -->
          <div class="card-meta">
            <span class="meta-date">📅 {{ item.date }} ({{ item.record_count }}条记录)</span>
            <span class="meta-note" v-if="item.note" :title="item.note">{{ item.note }}</span>
          </div>

          <!-- History Panel (expandable with chart) -->
          <div v-if="item._historyOpen" class="history-panel">
            <a-spin v-if="item._historyLoading" size="small" />
            <template v-else-if="item._history && item._history.length">
              <!-- Price Trend Chart -->
              <div class="chart-container" v-if="item._history.length > 1">
                <Line :data="item._chartData" :options="chartOptions" />
              </div>
              <!-- History List -->
              <div class="history-list">
                <div v-for="h in item._history" :key="h.id" class="history-item">
                  <span class="h-date">{{ h.date }}</span>
                  <span class="h-price">¥ {{ formatPrice(h.price) }}</span>
                  <span class="h-note">{{ h.note || '—' }}</span>
                </div>
              </div>
            </template>
            <span v-else class="no-history">暂无历史记录</span>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="kpLoading" class="loading-state">
        <a-spin tip="加载中..." />
      </div>

      <!-- Empty -->
      <div v-if="!kpLoading && selectedCategory && sortedItems.length === 0" class="empty-state">
        该分类暂无数据
      </div>

      <!-- No Category Selected -->
      <div v-if="!selectedCategory && !categoriesLoading" class="empty-state">
        👆 请选择一个分类查看
      </div>

      <div v-if="categoriesLoading" class="loading-state">
        <a-spin tip="加载分类..." />
      </div>
    </div>

      <!-- =================== Table View =================== -->
      <div v-if="viewMode === 'table'" class="table-view">
        <!-- Category Cards Row (shared filter) -->
        <div class="category-row">
          <div
            :class="['category-card', 'category-card-all', { active: !selectedCategory }]"
            @click="selectCategory('')"
          >
            <span class="cat-name">📋 全部</span>
            <span class="cat-count">{{ totalKpCount }}</span>
          </div>
          <div
            v-for="cat in categories"
            :key="cat.category"
            :class="['category-card', { active: selectedCategory === cat.category }]"
            @click="selectCategory(cat.category)"
          >
            <span class="cat-name">{{ cat.category }}</span>
            <span class="cat-count">{{ cat.count }}</span>
          </div>
        </div>

        <!-- Table Toolbar -->
        <div class="table-toolbar">
          <a-input-search
            v-model:value="tableSearch"
            placeholder="搜索型号、分类或备注..."
            style="width: 320px"
            @search="loadTableData"
            allow-clear
          />
          <a-select v-model:value="tableCategory" style="width: 160px" @change="loadTableData" placeholder="全部分类">
            <a-select-option value="">全部分类</a-select-option>
            <a-select-option v-for="cat in categories" :key="cat.category" :value="cat.category">
              {{ cat.category }} ({{ cat.count }})
            </a-select-option>
          </a-select>
          <a-select v-model:value="tableSort" style="width: 160px" @change="loadTableData">
            <a-select-option value="name-asc">名称 A→Z</a-select-option>
            <a-select-option value="name-desc">名称 Z→A</a-select-option>
            <a-select-option value="price-asc">价格 低→高</a-select-option>
            <a-select-option value="price-desc">价格 高→低</a-select-option>
            <a-select-option value="date-desc">日期 最新优先</a-select-option>
            <a-select-option value="date-asc">日期 最早优先</a-select-option>
            <a-select-option value="records-desc">记录数 多→少</a-select-option>
            <a-select-option value="records-asc">记录数 少→多</a-select-option>
          </a-select>
          <span class="table-count">共 {{ tableTotal }} 条</span>
        </div>

        <!-- Table -->
        <a-table
          :columns="tableColumns"
          :data-source="tableData"
          :loading="tableLoading"
          :pagination="tablePagination"
          @change="handleTableChange"
          row-key="id"
          size="small"
          :scroll="{ x: 1200 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'price'">
              <span class="table-price">¥ {{ formatPrice(record.price) }}</span>
            </template>
            <template v-if="column.key === 'date'">
              <span class="table-date">{{ record.date }}</span>
            </template>
            <template v-if="column.key === 'note'">
              <span class="table-note" :title="record.note">{{ record.note || '—' }}</span>
            </template>
            <template v-if="column.key === 'action'">
              <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
              <a-button type="link" size="small" @click="toggleHistory(record)">历史</a-button>
            </template>
          </template>

          <!-- Expanded Row for History -->
          <template #expandedRowRender="{ record }">
            <div v-if="record._historyOpen" class="table-history-panel">
              <a-spin v-if="record._historyLoading" size="small" />
              <template v-else-if="record._history && record._history.length">
                <div class="chart-container" v-if="record._history.length > 1">
                  <Line :data="record._chartData" :options="chartOptions" />
                </div>
                <div class="history-list">
                  <div v-for="h in record._history" :key="h.id" class="history-item">
                    <span class="h-date">{{ h.date }}</span>
                    <span class="h-price">¥ {{ formatPrice(h.price) }}</span>
                    <span class="h-note">{{ h.note || '—' }}</span>
                  </div>
                </div>
              </template>
              <span v-else class="no-history">暂无历史记录</span>
            </div>
          </template>
        </a-table>
      </div>

    <!-- =================== KP Edit Modal =================== -->
    <a-modal
      v-model:open="editModalVisible"
      title="编辑配件"
      @ok="saveEdit"
      :confirmLoading="editSaving"
      width="480px"
    >
      <div class="edit-form">
        <div class="form-row">
          <label>型号名称</label>
          <a-input v-model:value="editForm.model" placeholder="型号" />
        </div>
        <div class="form-row">
          <label>当前价格</label>
          <a-input-number v-model:value="editForm.price" :min="0" :step="0.01" style="width: 100%" />
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
import { ref, onMounted, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { AppstoreOutlined, UnorderedListOutlined } from '@ant-design/icons-vue'
import axios from 'axios'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

// =================== View Mode ===================
const viewMode = ref<'card' | 'table'>('card')

// =================== KP Categories ===================
const categories = ref<any[]>([])
const categoriesLoading = ref(false)
const selectedCategory = ref('')

const totalKpCount = computed(() => {
  return categories.value.reduce((sum, cat) => sum + (cat.count || 0), 0)
})

const loadCategories = async () => {
  categoriesLoading.value = true
  try {
    const res = await axios.get('/api/admin/kp/categories')
    categories.value = res.data.categories
  } catch (e: any) {
    message.error('加载分类失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    categoriesLoading.value = false
  }
}

const selectCategory = (cat: string) => {
  if (viewMode.value === 'table') {
    // Toggle category filter in table view
    const newCat = selectedCategory.value === cat ? '' : cat
    selectedCategory.value = newCat
    tableCategory.value = newCat
    tablePagination.value.current = 1
    loadTableData()
  } else {
    selectedCategory.value = cat
    kpSearch.value = ''
    loadCategoryItems()
  }
}

// =================== KP Items (by category) ===================
const categoryItems = ref<any[]>([])
const kpLoading = ref(false)
const kpSearch = ref('')

const loadCategoryItems = async () => {
  if (!selectedCategory.value) return
  kpLoading.value = true
  try {
    const res = await axios.get('/api/admin/kp/by-category', {
      params: { category: selectedCategory.value, search: kpSearch.value }
    })
    categoryItems.value = res.data.items.map((item: any) => ({
      ...item,
      _historyOpen: false,
      _historyLoading: false,
      _history: null,
      _chartData: null
    }))
  } catch (e: any) {
    message.error('加载配件数据失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    kpLoading.value = false
  }
}

// =================== Sort ===================
const sortBy = ref('name-asc')

const sortedItems = computed(() => {
  const items = [...categoryItems.value]
  const [field, direction] = sortBy.value.split('-')
  
  items.sort((a, b) => {
    let valA, valB
    if (field === 'name') {
      valA = a.model.toLowerCase()
      valB = b.model.toLowerCase()
    } else if (field === 'price') {
      valA = a.price
      valB = b.price
    } else if (field === 'date') {
      valA = new Date(a.date).getTime()
      valB = new Date(b.date).getTime()
    } else if (field === 'records') {
      valA = a.record_count
      valB = b.record_count
    }
    
    if (valA < valB) return direction === 'asc' ? -1 : 1
    if (valA > valB) return direction === 'asc' ? 1 : -1
    return 0
  })
  
  return items
})

const onSortChange = () => {
  // Computed will automatically re-sort
}

// =================== Table View ===================
const tableColumns = [
  { title: '分类', dataIndex: 'category', key: 'category', width: 120, sorter: true },
  { title: '型号', dataIndex: 'model', key: 'model', width: 300, ellipsis: true },
  { title: '价格', dataIndex: 'price', key: 'price', width: 120, sorter: true },
  { title: '币种', dataIndex: 'currency', key: 'currency', width: 80 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 100, sorter: true },
  { title: '记录数', dataIndex: 'record_count', key: 'record_count', width: 80, sorter: true },
  { title: '备注', dataIndex: 'note', key: 'note', width: 200, ellipsis: true },
  { title: '操作', key: 'action', width: 120, fixed: 'right' }
]

const tableData = ref<any[]>([])
const tableLoading = ref(false)
const tableTotal = ref(0)
const tableSearch = ref('')
const tableCategory = ref('')
const tableSort = ref<{ field: string; order: string }>({ field: 'date', order: 'desc' })
const tablePagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`
})

const loadTableData = async () => {
  tableLoading.value = true
  try {
    const res = await axios.get('/api/admin/kp/list', {
      params: {
        page: tablePagination.value.current,
        page_size: tablePagination.value.pageSize,
        search: tableSearch.value,
        category: tableCategory.value,
        sort_by: tableSort.value.field,
        sort_order: tableSort.value.order
      }
    })
    tableData.value = res.data.items
    tablePagination.value.total = res.data.total
  } catch (error) {
    console.error('加载表格数据失败:', error)
  } finally {
    tableLoading.value = false
  }
}

const handleTableChange = (pag: any, filters: any, sorter: any) => {
  tablePagination.value.current = pag.current
  tablePagination.value.pageSize = pag.pageSize
  
  // Handle sorting
  if (sorter && sorter.field) {
    tableSort.value = {
      field: sorter.field,
      order: sorter.order === 'ascend' ? 'asc' : 'desc'
    }
  }
  
  loadTableData()
}

// =================== History Toggle ===================
const toggleHistory = async (item: any) => {
  if (item._historyOpen) {
    item._historyOpen = false
    return
  }
  item._historyOpen = true
  if (item._history) return // already loaded
  item._historyLoading = true
  try {
    const res = await axios.get('/api/admin/kp/history', { params: { model: item.model } })
    item._history = res.data
    
    // Build chart data
    if (item._history.length > 1) {
      const sorted = [...item._history].reverse() // oldest first
      item._chartData = {
        labels: sorted.map(h => h.date),
        datasets: [
          {
            label: '价格趋势',
            data: sorted.map(h => h.price),
            borderColor: '#52c41a',
            backgroundColor: 'var(--cpq-overlay-success15)',
            tension: 0.3,
            fill: true,
            pointBackgroundColor: '#52c41a',
            pointBorderColor: '#fff',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: '#52c41a'
          }
        ]
      }
    }
  } catch (e: any) {
    message.error('获取历史价格失败')
  } finally {
    item._historyLoading = false
  }
}

// =================== Chart Options ===================
const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: false
    },
    tooltip: {
      backgroundColor: 'var(--cpq-overlay-b85)',
      titleColor: '#fff',
      bodyColor: '#52c41a',
      borderColor: '#52c41a',
      borderWidth: 1,
      callbacks: {
        label: (context: any) => `¥ ${context.parsed.y.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      }
    }
  },
  scales: {
    x: {
      grid: {
        color: 'var(--cpq-overlay-w5)'
      },
      ticks: {
        color: '#888',
        font: { size: 10 }
      }
    },
    y: {
      grid: {
        color: 'var(--cpq-overlay-w5)'
      },
      ticks: {
        color: '#888',
        callback: (value: any) => `¥${value}`
      }
    }
  }
}

// =================== KP Edit Modal ===================
const editModalVisible = ref(false)
const editSaving = ref(false)
const editForm = ref({ model: '', price: 0, note: '', _originalModel: '' })

const openEditModal = (item: any) => {
  editForm.value = {
    model: item.model,
    price: item.price,
    note: item.note || '',
    _originalModel: item.model
  }
  editModalVisible.value = true
}

const saveEdit = async () => {
  editSaving.value = true
  try {
    // If model name changed, rename first
    if (editForm.value.model !== editForm.value._originalModel) {
      await axios.post('/api/admin/kp/rename', {
        old_model: editForm.value._originalModel,
        new_model: editForm.value.model
      })
    }
    // Update price (inserts new record)
    await axios.post('/api/admin/kp/update', {
      model: editForm.value.model,
      price: editForm.value.price,
      category: selectedCategory.value,
      note: editForm.value.note || '手动更新'
    })
    message.success('保存成功')
    editModalVisible.value = false
    // Refresh both views
    if (viewMode.value === 'card' && selectedCategory.value) {
      loadCategoryItems()
    } else if (viewMode.value === 'table') {
      loadTableData()
    }
    loadCategories()
  } catch (e: any) {
    message.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    editSaving.value = false
  }
}

// =================== Utils ===================
const formatPrice = (val: any) => {
  if (val == null) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// =================== Init ===================
onMounted(() => {
  loadCategories()
})

// Watch view mode changes
watch(viewMode, (newMode) => {
  if (newMode === 'table' && tableData.value.length === 0) {
    loadTableData()
  }
})
</script>

<style scoped>
.base-pricing-page {
  padding: 20px;
  background: var(--cpq-bg-primary);
  min-height: 100vh;
  color: var(--cpq-text-primary);
}

/* ===== Page Header ===== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

/* ===== Category Row ===== */
.category-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.category-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 20px;
  background: var(--cpq-bg-secondary);
  border: 1px solid var(--cpq-border-primary);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 90px;
}
.category-card:hover {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-bg-tertiary);
}
.category-card.active {
  border-color: var(--cpq-accent-primary);
  background: rgba(24, 144, 255, 0.1);
  box-shadow: 0 0 0 1px var(--cpq-accent-primary);
}
.category-card-all {
  border-color: var(--cpq-accent-success, #52c41a);
  background: var(--cpq-overlay-success15);
}
.category-card-all:hover {
  background: var(--cpq-overlay-success15);
}
.category-card-all.active {
  border-color: var(--cpq-accent-success, #52c41a);
  background: var(--cpq-overlay-success15);
  box-shadow: 0 0 0 1px var(--cpq-accent-success, #52c41a);
}
.cat-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-primary);
  margin-bottom: 4px;
}
.cat-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--cpq-accent-primary-light);
}

/* ===== Toolbar ===== */
.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.item-count {
  color: var(--cpq-text-muted);
  font-size: 13px;
}

/* ===== Card Grid (Auto-fill) ===== */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

/* ===== Model Card ===== */
.model-card {
  background: var(--cpq-bg-secondary);
  border: 1px solid var(--cpq-border-primary);
  border-radius: 10px;
  padding: 12px;
  transition: border-color 0.2s;
}
.model-card:hover {
  border-color: var(--cpq-border-light);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.model-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  word-break: break-all;
  flex: 1;
  margin-right: 8px;
  line-height: 1.3;
}
.card-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
.edit-btn, .chart-btn {
  color: var(--cpq-text-muted);
  padding: 2px 6px;
}
.edit-btn:hover {
  color: var(--cpq-accent-primary-light);
}
.chart-btn:hover {
  color: var(--cpq-accent-success);
}

/* ===== Price ===== */
.card-price {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
}
.price-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--cpq-accent-success);
}
.price-currency {
  font-size: 11px;
  color: var(--cpq-text-muted);
}

/* ===== Meta ===== */
.card-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.meta-date {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.meta-note {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== History Panel ===== */
.history-panel {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--cpq-border-primary);
}
.chart-container {
  height: 120px;
  margin-bottom: 12px;
  padding: 8px;
  background: var(--cpq-bg-tertiary);
  border-radius: 6px;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  padding: 4px 0;
}
.h-date {
  color: var(--cpq-text-muted);
  min-width: 70px;
}
.h-price {
  color: var(--cpq-accent-success);
  font-weight: 600;
  min-width: 70px;
}
.h-note {
  color: var(--cpq-text-secondary);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.no-history {
  font-size: 11px;
  color: var(--cpq-text-muted);
}

/* ===== States ===== */
.loading-state, .empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 60px 0;
  color: var(--cpq-text-muted);
  font-size: 14px;
}

/* ===== Table View ===== */
.table-view {
  margin-top: 20px;
}

.table-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.table-count {
  color: var(--cpq-text-secondary);
  font-size: 13px;
  margin-left: auto;
}

.table-price {
  color: var(--cpq-accent-success);
  font-weight: 600;
}

.table-date {
  color: var(--cpq-text-secondary);
  font-size: 13px;
}

.table-note {
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.table-history-panel {
  padding: 16px;
  background: var(--cpq-bg-secondary);
  border-radius: 8px;
}

/* ===== Edit Form ===== */
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-row label {
  font-size: 13px;
  color: var(--cpq-text-secondary);
  font-weight: 500;
}

/* ===== Dark theme overrides ===== */
:deep(.ant-input), :deep(.ant-input-number), :deep(.ant-input-number-input),
:deep(.ant-input-affix-wrapper), :deep(.ant-input-search .ant-input) {
  background: var(--cpq-bg-tertiary) !important;
  border-color: var(--cpq-border-light) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-select-selector) {
  background: var(--cpq-bg-tertiary) !important;
  border-color: var(--cpq-border-light) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-select-dropdown) {
  background: var(--cpq-bg-secondary) !important;
}
:deep(.ant-select-item) {
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-select-item-option-active) {
  background: var(--cpq-bg-tertiary) !important;
}
:deep(.ant-modal-content) {
  background: var(--cpq-bg-secondary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-modal-header) {
  background: var(--cpq-bg-secondary) !important;
}
:deep(.ant-modal-title) {
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-spin-text) {
  color: var(--cpq-text-muted) !important;
}
</style>
