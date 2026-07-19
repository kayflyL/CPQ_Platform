<template>
  <div class="base-pricing-page">
    <!-- =================== Page Header =================== -->
    <div class="page-header">
      <div class="page-title-group">
        <h1><DatabaseOutlined class="page-title-icon" />配件管理</h1>
        <p class="page-subtitle">共 <span class="num">{{ partsTotal }}</span> 个配件 · <span class="num">{{ categories.length }}</span> 个分类</p>
      </div>
      <div class="header-actions">
        <div class="seg-nav">
          <button :class="['seg-item', { active: viewMode === 'card' }]" @click="viewMode = 'card'">
            <AppstoreOutlined />卡片
          </button>
          <button :class="['seg-item', { active: viewMode === 'table' }]" @click="viewMode = 'table'">
            <UnorderedListOutlined />表格
          </button>
        </div>
        <a-button type="primary" size="small" @click="openCreatePartModal">
          <template #icon><PlusOutlined /></template>
          新增配件
        </a-button>
      </div>
    </div>

    <!-- =================== Category Chip Nav =================== -->
    <div class="category-nav-bar glass-light">
      <div class="cat-chip-scroll">
        <button :class="['cat-chip', { active: !selectedCategoryId }]" @click="selectCategory(null)">
          <UnorderedListOutlined class="cat-chip-ico" />
          <span>全部</span>
          <span class="cat-chip-count">{{ totalPartCount }}</span>
        </button>
        <button
          v-for="cat in categories"
          :key="cat.id"
          :class="['cat-chip', { active: selectedCategoryId === cat.id }]"
          @click="selectCategory(cat.id)"
        >
          <span class="cat-chip-dot"></span>
          <span>{{ cat.name }}</span>
          <span class="cat-chip-count">{{ cat.count }}</span>
        </button>
      </div>
      <button class="cat-manage-btn" title="管理分类" @click="categoryManageVisible = true">
        <SettingOutlined />
      </button>
    </div>

    <div class="main-layout">
      <!-- =================== Left Sidebar: Category Nav =================== -->
      <aside class="category-sidebar glass">
        <div class="sidebar-title">筛选</div>

        <div class="filter-group" v-if="brandsList.length">
          <div class="filter-title">品牌</div>
          <label class="filter-opt" v-for="b in brandsList" :key="b.brand">
            <input type="checkbox" :value="b.brand" v-model="selectedBrands" @change="applyFilters">
            <span class="opt-name">{{ b.brand }}</span>
            <span class="opt-count">{{ b.count }}</span>
          </label>
        </div>

        <div class="filter-group">
          <div class="filter-title">价格记录</div>
          <label class="filter-opt">
            <input type="radio" value="" v-model="priceFilter" @change="applyFilters">
            <span class="opt-name">全部</span>
          </label>
          <label class="filter-opt">
            <input type="radio" value="has_price" v-model="priceFilter" @change="applyFilters">
            <span class="opt-name">有报价</span>
          </label>
          <label class="filter-opt">
            <input type="radio" value="multi" v-model="priceFilter" @change="applyFilters">
            <span class="opt-name">≥3 条记录</span>
          </label>
          <label class="filter-opt">
            <input type="radio" value="no_price" v-model="priceFilter" @change="applyFilters">
            <span class="opt-name">暂无报价</span>
          </label>
        </div>

        <template v-if="hasSelectedCategory">
          <div class="filter-group" v-for="(values, key) in specFacets" :key="key">
            <div class="filter-title">{{ key }}</div>
            <div class="chip-row">
              <span
                v-for="fv in values"
                :key="fv.value"
                :class="['chip', { active: (selectedSpecs[key] || []).includes(fv.value) }]"
                @click="toggleSpec(key, fv.value)"
              >{{ fv.value }}<span class="chip-count">{{ fv.count }}</span></span>
            </div>
          </div>
        </template>
        <div class="filter-hint" v-else>
          选择具体类别查看精准规格维度
        </div>

        <button
          class="clear-filter"
          v-if="selectedBrands.length || priceFilter || Object.keys(selectedSpecs).length"
          @click="clearFilters"
        >清除筛选</button>
      </aside>

      <!-- =================== Main Content =================== -->
      <div class="content-area">
        <!-- Toolbar -->
        <div class="toolbar glass-light">
          <a-input-search
            v-model:value="searchText"
            placeholder="搜索配件名称、SKU、品牌..."
            class="toolbar-search"
            @search="loadParts"
            allow-clear
          >
            <template #prefix>
              <SearchOutlined style="color: var(--cpq-text-muted)" />
            </template>
          </a-input-search>
          <a-select v-model:value="sortBy" class="toolbar-sort" @change="loadParts">
            <a-select-option value="name-asc">名称 A→Z</a-select-option>
            <a-select-option value="name-desc">名称 Z→A</a-select-option>
            <a-select-option value="price-asc">价格 低→高</a-select-option>
            <a-select-option value="price-desc">价格 高→低</a-select-option>
          </a-select>
          <span class="toolbar-count">共 <b>{{ partsTotal }}</b> 个配件</span>
        </div>

        <!-- Card View -->
        <div v-if="viewMode === 'card'" class="card-grid">
          <div
            v-for="(part, idx) in parts"
            :key="part.id"
            :class="['model-card', 'glass-light', { 'no-price-card': part.latest_price == null }]"
            :style="{ animationDelay: (idx % 20) * 30 + 'ms' }"
            @click="openPartDetail(part.id)"
          >
            <div class="card-accent-bar"></div>
            <div class="card-header">
              <span class="card-category-tag">{{ part.category_name || '未分类' }}</span>
              <button class="card-edit-btn" @click.stop="openEditPartModal(part)"><EditOutlined /></button>
            </div>
            <div class="card-name" :title="part.name">{{ part.name }}</div>
            <div class="card-sku" v-if="part.oem_sku">
              <span class="sku-label">SKU</span>
              <span class="sku-value" @click.stop="copyText(part.oem_sku)">{{ part.oem_sku }}</span>
            </div>
            <div class="card-price">
              <span class="price-value" v-if="part.latest_price != null"><span class="price-sym">{{ currencySymbol(part.latest_currency) }}</span> {{ formatPrice(part.latest_price) }}</span>
              <span class="price-value no-price" v-else>暂无报价</span>
              <span class="price-date" v-if="part.latest_date">{{ part.latest_date }}</span>
            </div>
            <div class="card-meta" v-if="part.brand || part.condition">
              <a-tag size="small" v-if="part.brand">{{ part.brand }}</a-tag>
              <span v-if="part.condition" :class="['cond-badge', conditionClass(part.condition)]">{{ part.condition }}</span>
            </div>
          </div>
        </div>

        <!-- Card Pagination -->
        <div v-if="viewMode === 'card' && partsTotal > 0" class="card-pagination">
          <a-pagination
            v-model:current="pagination.current"
            :total="partsTotal"
            :page-size="pagination.pageSize"
            :page-size-options="['20', '40', '60']"
            show-size-changer
            size="small"
            @change="onCardPageChange"
          />
        </div>

        <!-- Table View -->
        <div v-if="viewMode === 'table'" class="glass-light table-wrap">
          <a-table
            :columns="tableColumns"
            :data-source="parts"
            :loading="partsLoading"
            :pagination="tablePagination"
            @change="handleTableChange"
            row-key="id"
            size="small"
            :scroll="{ x: 1200 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <a @click="openPartDetail(record.id)">{{ record.name }}</a>
              </template>
              <template v-if="column.key === 'latest_price'">
                <span class="table-price" v-if="record.latest_price != null">{{ currencySymbol(record.latest_currency) }} {{ formatPrice(record.latest_price) }}</span>
                <span v-else class="no-price">—</span>
              </template>
              <template v-if="column.key === 'action'">
                <a-button type="link" size="small" @click="openPartDetail(record.id)">详情</a-button>
                <a-button type="link" size="small" @click="openEditPartModal(record)">编辑</a-button>
              </template>
            </template>
          </a-table>
        </div>

        <!-- Loading / Empty -->
        <div v-if="partsLoading" class="loading-state">
          <a-spin tip="加载中..." />
        </div>
        <div v-if="!partsLoading && parts.length === 0" class="empty-state">
          <InboxOutlined class="empty-icon" v-if="!searchText" />
          <SearchOutlined class="empty-icon" v-else />
          <div class="empty-text">{{ searchText ? '未找到匹配的配件' : '暂无配件数据' }}</div>
          <a-button v-if="!searchText" type="primary" size="small" @click="openCreatePartModal">
            <template #icon><PlusOutlined /></template>新增第一个配件
          </a-button>
          <a-button v-else size="small" @click="clearSearch">清除搜索</a-button>
        </div>
      </div>
    </div>

    <!-- =================== Part Detail Drawer =================== -->
    <a-drawer
      v-model:open="detailDrawerVisible"
      width="640"
      :destroyOnClose="true"
    >
      <template #title>
        <div class="drawer-title" v-if="detailPart">
          <span class="drawer-title-name">{{ detailPart.name }}</span>
          <a-tag size="small" v-if="detailPart.brand">{{ detailPart.brand }}</a-tag>
          <a-tag size="small" v-if="detailPart.category_name">{{ detailPart.category_name }}</a-tag>
        </div>
        <span v-else>配件详情</span>
      </template>
      <template v-if="detailPart">
        <!-- Basic Info -->
        <div class="detail-section">
          <h4>基础信息</h4>
          <div class="detail-grid">
            <div class="detail-field">
              <span class="field-label">分类</span>
              <span class="field-value">{{ detailPart.category_name || '未分类' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">OEM SKU</span>
              <span class="field-value" @click="copyText(detailPart.oem_sku)">{{ detailPart.oem_sku || '—' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">替代料号</span>
              <span class="field-value">{{ detailPart.alt_sku || '—' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">品牌</span>
              <span class="field-value">{{ detailPart.brand || '—' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">成色</span>
              <span class="field-value">{{ detailPart.condition || '全新' }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">货期</span>
              <span class="field-value">{{ detailPart.lead_time || '—' }}</span>
            </div>
          </div>
          <div class="detail-field full" v-if="detailPart.short_desc">
            <span class="field-label">简述</span>
            <span class="field-value">{{ detailPart.short_desc }}</span>
          </div>
        </div>

        <!-- Specs -->
        <div class="detail-section">
          <h4>规格参数</h4>
          <div v-if="detailPart.specs && detailPart.specs.length" class="specs-table">
            <div v-for="spec in detailPart.specs" :key="spec.id" class="spec-row">
              <span class="spec-key">{{ spec.spec_key }}</span>
              <span class="spec-val">{{ spec.spec_value || '—' }}</span>
            </div>
          </div>
          <span v-else class="no-data">暂无规格参数</span>
        </div>

        <!-- Price History -->
        <div class="detail-section">
          <div class="section-header">
            <h4>价格历史</h4>
            <a-button type="link" size="small" @click="openAddPriceModal">+ 新增报价</a-button>
          </div>
          <!-- Chart -->
          <div class="chart-container" v-if="detailPart.price_history && detailPart.price_history.length > 1">
            <Line :data="detailChartData" :options="chartOptions" />
          </div>
          <!-- List -->
          <div v-if="detailPart.price_history && detailPart.price_history.length" class="price-list">
            <div v-for="h in detailPart.price_history" :key="h.id" class="price-item">
              <span class="price-date">{{ h.price_date || '—' }}</span>
              <span class="price-amount">{{ currencySymbol(h.currency) }} {{ formatPrice(h.price) }}</span>
              <span class="price-note">{{ h.note || '—' }}</span>
            </div>
          </div>
          <span v-else class="no-data">暂无价格记录</span>
        </div>

        <!-- Compat Servers -->
        <div class="detail-section">
          <h4>兼容机型</h4>
          <div v-if="detailPart.compat_servers && detailPart.compat_servers.length" class="compat-tags">
            <a-tag
              v-for="c in detailPart.compat_servers"
              :key="c.id"
              class="compat-tag"
              @click="copyText(c.server_model)"
            >{{ c.server_model }}</a-tag>
          </div>
          <span v-else class="no-data">暂无兼容机型</span>
        </div>

        <!-- Actions -->
        <div class="detail-actions">
          <a-button @click="openEditPartModal(detailPart)">编辑配件</a-button>
          <a-popconfirm title="确定删除该配件？" @confirm="deletePart(detailPart.id)">
            <a-button danger>删除</a-button>
          </a-popconfirm>
        </div>
      </template>
      <div v-else class="loading-state">
        <a-spin tip="加载详情..." />
      </div>
    </a-drawer>

    <!-- =================== Create/Edit Part Modal =================== -->
    <a-modal
      v-model:open="partModalVisible"
      :title="partForm.id ? '编辑配件' : '新增配件'"
      @ok="savePart"
      :confirmLoading="partSaving"
      width="600px"
    >
      <div class="edit-form">
        <div class="form-row">
          <label>配件名称 <span class="required">*</span></label>
          <a-input v-model:value="partForm.name" placeholder="如: NVIDIA RTX4090 24G 涡轮卡" />
        </div>
        <div class="form-row-2col">
          <div class="form-row">
            <label>分类</label>
            <a-select v-model:value="partForm.category_id" placeholder="选择分类" allowClear>
              <a-select-option v-for="cat in categories" :key="cat.id" :value="cat.id">
                {{ cat.name }}
              </a-select-option>
            </a-select>
          </div>
          <div class="form-row">
            <label>品牌</label>
            <a-input v-model:value="partForm.brand" placeholder="如: NVIDIA" />
          </div>
        </div>
        <div class="form-row-2col">
          <div class="form-row">
            <label>OEM SKU (原厂料号)</label>
            <a-input v-model:value="partForm.oem_sku" placeholder="如: PG506-230" />
          </div>
          <div class="form-row">
            <label>替代料号</label>
            <a-input v-model:value="partForm.alt_sku" placeholder="兼容备件号" />
          </div>
        </div>
        <div class="form-row">
          <label>简述</label>
          <a-input v-model:value="partForm.short_desc" placeholder="一句话规格摘要" />
        </div>
        <div class="form-row-2col">
          <div class="form-row">
            <label>成色</label>
            <a-select v-model:value="partForm.condition">
              <a-select-option value="全新">全新</a-select-option>
              <a-select-option value="翻新">翻新</a-select-option>
              <a-select-option value="拆机">拆机</a-select-option>
            </a-select>
          </div>
          <div class="form-row">
            <label>货期</label>
            <a-input v-model:value="partForm.lead_time" placeholder="如: 2-4周" />
          </div>
        </div>
        <div class="form-row">
          <label>规格参数</label>
          <div class="specs-editor">
            <div v-for="(spec, idx) in partForm.specs" :key="idx" class="spec-editor-row">
              <a-auto-complete
                v-model:value="spec.key"
                :options="specKeyOptions"
                :filter-option="filterSpecKey"
                placeholder="参数名"
                style="width: 40%"
                allow-clear
              />
              <a-input v-model:value="spec.value" placeholder="参数值" style="width: 45%" />
              <a-button type="text" size="small" danger @click="removeSpec(idx)">✕</a-button>
            </div>
            <a-button type="dashed" size="small" block @click="addSpec">+ 添加参数</a-button>
          </div>
        </div>
        <div class="form-row">
          <label>适用系列（不选=全系列通用）</label>
          <a-select v-model:value="partForm.applicable_series" mode="multiple" placeholder="不选=全通用" allowClear>
            <a-select-option value="Orion">Orion</a-select-option>
            <a-select-option value="Polaris">Polaris</a-select-option>
          </a-select>
        </div>
        <div class="form-row">
          <label>兼容机型（输入后按回车添加）</label>
          <a-select
            v-model:value="partForm.compat_servers"
            mode="tags"
            placeholder="输入机型后按回车，如: DL380 Gen11"
            style="width: 100%"
            :token-separators="[',']"
          />
        </div>
      </div>
    </a-modal>

    <!-- =================== Add Price Modal =================== -->
    <a-modal
      v-model:open="priceModalVisible"
      title="新增报价"
      @ok="savePrice"
      :confirmLoading="priceSaving"
      width="400px"
    >
      <div class="edit-form">
        <div class="form-row">
          <label>价格 <span class="required">*</span></label>
          <a-input-number v-model:value="priceForm.price" :min="0" :step="0.01" style="width: 100%" />
        </div>
        <div class="form-row">
          <label>日期</label>
          <a-date-picker
            v-model:value="priceForm.price_date"
            value-format="YYYY-MM-DD"
            placeholder="留空为今天"
            style="width: 100%"
          />
        </div>
        <div class="form-row">
          <label>备注</label>
          <a-textarea v-model:value="priceForm.note" :rows="2" placeholder="供应商、来源等" />
        </div>
      </div>
    </a-modal>

    <!-- =================== Category Manage Modal =================== -->
    <a-modal
      v-model:open="categoryManageVisible"
      title="分类管理"
      :footer="null"
      width="500px"
    >
      <div class="category-manage">
        <div v-for="cat in categories" :key="cat.id" class="category-manage-item">
          <template v-if="editingCategory?.id === cat.id">
            <a-input v-model:value="editingCategoryName" placeholder="分类名称" style="width: 200px" @pressEnter="saveCategoryEdit" />
            <div class="category-edit-actions">
              <a-button type="primary" size="small" @click="saveCategoryEdit">保存</a-button>
              <a-button size="small" @click="cancelCategoryEdit">取消</a-button>
            </div>
          </template>
          <template v-else>
            <span>{{ cat.name }} ({{ cat.count }})</span>
            <div>
              <a-button type="link" size="small" @click="editCategory(cat)">编辑</a-button>
              <a-popconfirm
                v-if="!cat.count"
                title="确定删除该分类？"
                @confirm="deleteCategory(cat.id)"
              >
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
              <a-button
                v-else
                type="link"
                size="small"
                danger
                disabled
                :title="`分类下还有 ${cat.count} 个配件，需先清空才能删除`"
              >删除</a-button>
            </div>
          </template>
        </div>
        <a-divider />
        <div class="category-add-row">
          <a-input v-model:value="newCategoryName" placeholder="新分类名称" style="width: 200px" />
          <a-button type="primary" size="small" @click="createCategory">添加</a-button>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import {
  AppstoreOutlined, UnorderedListOutlined, PlusOutlined, EditOutlined,
  SearchOutlined, InboxOutlined, SettingOutlined, DatabaseOutlined
} from '@ant-design/icons-vue'
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
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler
)

// 图表配色集中管理（chart.js 读不到 CSS 变量，故用 JS 常量；取值与 tokens.css 青色主调一致）
const CHART_COLORS = {
  accent: '#00F5D4',                     // = --cpq-accent-primary
  accentFill: 'rgba(0, 245, 212, 0.10)', // = --cpq-overlay-a10
  grid: 'rgba(255, 255, 255, 0.05)',     // = --cpq-overlay-w5
  tick: '#6E7582',                       // = --cpq-text-muted
  tooltipBg: 'rgba(8, 9, 11, 0.85)',     // = --cpq-overlay-b85
  tooltipTitle: '#E8ECEF',               // = --cpq-text-primary
  pointEdge: '#08090B',                  // = --cpq-bg-primary
}

// =================== View Mode ===================
const viewMode = ref<'card' | 'table'>('card')

// =================== Categories ===================
const categories = ref<any[]>([])
const selectedCategoryId = ref<number | null>(null)
const totalPartCount = computed(() => categories.value.reduce((sum, c) => sum + (c.count || 0), 0))

const loadCategories = async () => {
  try {
    const res = await axios.get('/api/admin/kp/categories')
    // 旧接口返回 { category, count }，需要映射到新接口获取 id
    const resAll = await axios.get('/api/admin/kp/categories/all')
    const fullCats = resAll.data.categories || []
    // 合并 count 信息
    categories.value = fullCats.map((fc: any) => {
      const old = res.data.categories.find((c: any) => c.category === fc.name)
      return { ...fc, count: old?.count || 0 }
    })
  } catch (e: any) {
    message.error('加载分类失败: ' + (e.response?.data?.detail || e.message))
  }
}

const selectCategory = (catId: number | null) => {
  selectedCategoryId.value = catId
  pagination.value.current = 1
  // 切换分类时重置筛选并重新加载品牌 / 规格维度（随分类变化）
  selectedBrands.value = []
  priceFilter.value = ''
  selectedSpecs.value = {}
  loadBrands()
  loadSpecFacets()
  loadParts()
}

// =================== Filters ===================
const brandsList = ref<any[]>([])
const specFacets = ref<Record<string, any[]>>({})
const selectedBrands = ref<string[]>([])
const priceFilter = ref('')
const selectedSpecs = ref<Record<string, string[]>>({})

const loadBrands = async () => {
  try {
    const res = await axios.get('/api/admin/kp/brands', { params: { category_id: selectedCategoryId.value } })
    brandsList.value = res.data.brands || []
  } catch (e: any) {
    brandsList.value = []
  }
}

const loadSpecFacets = async () => {
  try {
    const res = await axios.get('/api/admin/kp/spec-facets', { params: { category_id: selectedCategoryId.value } })
    specFacets.value = res.data.facets || {}
  } catch (e: any) {
    specFacets.value = {}
  }
}

const hasSelectedCategory = computed(() => selectedCategoryId.value != null)

// spec_key 录入候选：来自当前类别已聚合的维度名，允许自由输入兜底
const specKeyOptions = computed(() => Object.keys(specFacets.value).map(k => ({ value: k })))
const filterSpecKey = (input: string, option: any) => {
  const v = (option.value || '').toLowerCase()
  return v.includes((input || '').toLowerCase())
}

const applyFilters = () => {
  pagination.value.current = 1
  loadParts()
}

const toggleSpec = (key: string, value: string) => {
  const cur = selectedSpecs.value[key] ? [...selectedSpecs.value[key]] : []
  const idx = cur.indexOf(value)
  if (idx >= 0) cur.splice(idx, 1)
  else cur.push(value)
  if (cur.length) {
    selectedSpecs.value = { ...selectedSpecs.value, [key]: cur }
  } else {
    const next = { ...selectedSpecs.value }
    delete next[key]
    selectedSpecs.value = next
  }
  applyFilters()
}

const clearFilters = () => {
  selectedBrands.value = []
  priceFilter.value = ''
  selectedSpecs.value = {}
  applyFilters()
}

// =================== Parts List ===================
const parts = ref<any[]>([])
const partsLoading = ref(false)
const partsTotal = ref(0)
const searchText = ref('')
const sortBy = ref('name-asc')
const pagination = ref({ current: 1, pageSize: 20 })

const loadParts = async () => {
  partsLoading.value = true
  try {
    // sortBy 形如 'name-asc' / 'price-desc'，拆成 sort_by / sort_order 两个字段传后端
    const [sb, so] = sortBy.value.split('-')
    const specsParam = Object.keys(selectedSpecs.value).length ? JSON.stringify(selectedSpecs.value) : null
    const res = await axios.get('/api/admin/kp/parts', {
      params: {
        category_id: selectedCategoryId.value,
        search: searchText.value,
        page: pagination.value.current,
        page_size: pagination.value.pageSize,
        sort_by: sb,
        sort_order: so,
        brands: selectedBrands.value.length ? selectedBrands.value.join(',') : null,
        price_filter: priceFilter.value || null,
        specs: specsParam,
      }
    })
    parts.value = res.data.items || []
    partsTotal.value = res.data.total || 0
  } catch (e: any) {
    message.error('加载配件失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    partsLoading.value = false
  }
}

const handleTableChange = (pag: any) => {
  pagination.value.current = pag.current
  pagination.value.pageSize = pag.pageSize
  loadParts()
}

const onCardPageChange = (page: number, pageSize: number) => {
  pagination.value.current = page
  pagination.value.pageSize = pageSize
  loadParts()
}

// =================== Table Columns ===================
const tablePagination = computed(() => ({
  current: pagination.value.current,
  pageSize: pagination.value.pageSize,
  total: partsTotal.value,
  showSizeChanger: true,
  pageSizeOptions: ['20', '40', '60'],
}))

const tableColumns = [
  { title: '配件名称', dataIndex: 'name', key: 'name', width: 300, ellipsis: true },
  { title: '分类', dataIndex: 'category_name', key: 'category_name', width: 100 },
  { title: 'OEM SKU', dataIndex: 'oem_sku', key: 'oem_sku', width: 150, ellipsis: true },
  { title: '品牌', dataIndex: 'brand', key: 'brand', width: 100 },
  { title: '最新价格', dataIndex: 'latest_price', key: 'latest_price', width: 120 },
  { title: '更新日期', dataIndex: 'latest_date', key: 'latest_date', width: 100 },
  { title: '操作', key: 'action', width: 120, fixed: 'right' as const },
]

// =================== Part Detail Drawer ===================
const detailDrawerVisible = ref(false)
const detailPart = ref<any>(null)

const openPartDetail = async (partId: number) => {
  detailDrawerVisible.value = true
  detailPart.value = null
  try {
    const res = await axios.get(`/api/admin/kp/parts/${partId}`)
    detailPart.value = res.data
  } catch (e: any) {
    message.error('加载详情失败')
    detailDrawerVisible.value = false
  }
}

const detailChartData = computed(() => {
  if (!detailPart.value?.price_history || detailPart.value.price_history.length < 2) return null
  const sorted = [...detailPart.value.price_history].reverse()
  return {
    labels: sorted.map(h => h.price_date),
    datasets: [{
      label: '价格趋势',
      data: sorted.map(h => h.price),
      borderColor: CHART_COLORS.accent,
      backgroundColor: CHART_COLORS.accentFill,
      tension: 0.3,
      fill: true,
      pointBackgroundColor: CHART_COLORS.accent,
      pointBorderColor: CHART_COLORS.pointEdge,
    }]
  }
})

// =================== Part Create/Edit Modal ===================
const partModalVisible = ref(false)
const partSaving = ref(false)
const partForm = ref<any>({
  id: null, name: '', category_id: null, brand: '', oem_sku: '', alt_sku: '',
  short_desc: '', condition: '全新', lead_time: '',
  specs: [], compat_servers: [], applicable_series: [],
})

const openCreatePartModal = () => {
  partForm.value = {
    id: null, name: '', category_id: selectedCategoryId.value, brand: '', oem_sku: '', alt_sku: '',
    short_desc: '', condition: '全新', lead_time: '',
    specs: [], compat_servers: [], applicable_series: [],
  }
  partModalVisible.value = true
}

const openEditPartModal = (part: any) => {
  partForm.value = {
    id: part.id,
    name: part.name,
    category_id: part.category_id,
    brand: part.brand || '',
    oem_sku: part.oem_sku || '',
    alt_sku: part.alt_sku || '',
    short_desc: part.short_desc || '',
    condition: part.condition || '全新',
    lead_time: part.lead_time || '',
    specs: (part.specs || []).map((s: any) => ({ key: s.spec_key, value: s.spec_value || '' })),
    compat_servers: (part.compat_servers || []).map((c: any) => c.server_model),
    applicable_series: part.applicable?.series || [],
  }
  partModalVisible.value = true
}

const addSpec = () => {
  partForm.value.specs.push({ key: '', value: '' })
}

const removeSpec = (idx: number) => {
  partForm.value.specs.splice(idx, 1)
}

const savePart = async () => {
  if (!partForm.value.name) {
    message.error('配件名称不能为空')
    return
  }
  partSaving.value = true
  try {
    const payload = {
      ...partForm.value,
      specs: partForm.value.specs.filter((s: any) => s.key),
      compat_servers: partForm.value.compat_servers || [],
      applicable: partForm.value.applicable_series && partForm.value.applicable_series.length
        ? { series: partForm.value.applicable_series } : null,
    }

    if (partForm.value.id) {
      await axios.put(`/api/admin/kp/parts/${partForm.value.id}`, payload)
      message.success('更新成功')
    } else {
      await axios.post('/api/admin/kp/parts', payload)
      message.success('创建成功')
    }
    partModalVisible.value = false
    loadParts()
    loadCategories()
    // 如果详情打开，刷新详情
    if (detailDrawerVisible.value && partForm.value.id) {
      openPartDetail(partForm.value.id)
    }
  } catch (e: any) {
    message.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    partSaving.value = false
  }
}

const deletePart = async (partId: number) => {
  try {
    await axios.delete(`/api/admin/kp/parts/${partId}`)
    message.success('删除成功')
    detailDrawerVisible.value = false
    loadParts()
    loadCategories()
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// =================== Add Price ===================
const priceModalVisible = ref(false)
const priceSaving = ref(false)
const priceForm = ref<any>({ price: 0, price_date: null, note: '' })

const openAddPriceModal = () => {
  priceForm.value = { price: 0, price_date: null, note: '' }
  priceModalVisible.value = true
}

const savePrice = async () => {
  if (!priceForm.value.price) {
    message.error('价格不能为空')
    return
  }
  priceSaving.value = true
  try {
    await axios.post(`/api/admin/kp/parts/${detailPart.value.id}/prices`, priceForm.value)
    message.success('报价添加成功')
    priceModalVisible.value = false
    openPartDetail(detailPart.value.id)
    loadParts()
  } catch (e: any) {
    message.error('添加失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    priceSaving.value = false
  }
}

// =================== Category Manage ===================
const categoryManageVisible = ref(false)
const newCategoryName = ref('')

const createCategory = async () => {
  if (!newCategoryName.value) return
  try {
    await axios.post('/api/admin/kp/categories', { name: newCategoryName.value })
    newCategoryName.value = ''
    loadCategories()
    message.success('分类创建成功')
  } catch (e: any) {
    message.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
}

const editingCategory = ref<any>(null)
const editingCategoryName = ref('')

const editCategory = (cat: any) => {
  editingCategory.value = cat
  editingCategoryName.value = cat.name
}

const cancelCategoryEdit = () => {
  editingCategory.value = null
  editingCategoryName.value = ''
}

const saveCategoryEdit = async () => {
  const newName = editingCategoryName.value.trim()
  if (!newName) {
    message.error('分类名称不能为空')
    return
  }
  if (newName === editingCategory.value.name) {
    cancelCategoryEdit()
    return
  }
  try {
    await axios.put(`/api/admin/kp/categories/${editingCategory.value.id}`, { name: newName })
    message.success('更新成功')
    cancelCategoryEdit()
    loadCategories()
  } catch (e: any) {
    message.error('更新失败: ' + (e.response?.data?.detail || e.message))
  }
}

const deleteCategory = async (catId: number) => {
  try {
    await axios.delete(`/api/admin/kp/categories/${catId}`)
    loadCategories()
    message.success('删除成功')
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// =================== Chart Options ===================
const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: CHART_COLORS.tooltipBg,
      titleColor: CHART_COLORS.tooltipTitle,
      bodyColor: CHART_COLORS.accent,
      callbacks: {
        label: (ctx: any) => `${ctx.parsed.y.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      }
    }
  },
  scales: {
    x: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.tick, font: { size: 10 } } },
    y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.tick, callback: (v: any) => v } }
  }
}

// =================== Utils ===================
const CURRENCY_SYMBOLS: Record<string, string> = { RMB: '¥', CNY: '¥', USD: '$', EUR: '€' }
const currencySymbol = (currency: string | null | undefined) => {
  if (!currency) return '¥'
  return CURRENCY_SYMBOLS[currency.toUpperCase()] || currency
}
const formatPrice = (val: any) => {
  if (val == null) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const copyText = (text: string) => {
  if (!text) return
  navigator.clipboard.writeText(text).then(() => message.success('已复制'))
}

const conditionClass = (cond: string) => {
  if (cond === '翻新') return 'cond-refurb'
  if (cond === '拆机') return 'cond-used'
  return 'cond-new'
}

const clearSearch = () => {
  searchText.value = ''
  pagination.value.current = 1
  loadParts()
}

// =================== Init ===================
onMounted(() => {
  loadCategories()
  loadBrands()
  loadSpecFacets()
  loadParts()
})
</script>

<style scoped>
/* ============ 页面骨架 ============ */
.base-pricing-page {
  position: relative;
  padding: 24px;
  background: var(--cpq-bg-primary);
  min-height: 100vh;
  color: var(--cpq-text-primary);
}
/* 顶部签名光条 */
.base-pricing-page::before {
  content: '';
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 2px;
  z-index: 100;
  background: linear-gradient(90deg, transparent, var(--cpq-accent-primary), transparent);
}

/* 入场动画 */
@keyframes fadeInUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }

/* ============ 页头 ============ */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 22px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
}
.page-title-group h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.3px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.page-title-icon { color: var(--cpq-accent-primary); font-size: 20px; }
.page-subtitle { margin: 4px 0 0; font-size: 13px; color: var(--cpq-text-secondary); }
.page-subtitle .num { color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.header-actions { display: flex; gap: 10px; align-items: center; }

/* 分段视图切换 */
.seg-nav {
  display: flex; gap: 4px; padding: 4px; border-radius: 10px;
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
}
.seg-item {
  display: flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 7px;
  font-size: 13px; color: var(--cpq-text-secondary); cursor: pointer;
  transition: all var(--cpq-transition-fast); border: none; background: transparent;
  font-family: inherit;
}
.seg-item:hover { color: var(--cpq-text-primary); background: var(--cpq-overlay-a6); }
.seg-item.active { color: #06090E; background: var(--cpq-accent-primary); font-weight: 600; }
.seg-item :deep(svg) { width: 15px; height: 15px; }

/* ============ 顶部分类胶囊条 ============ */
.category-nav-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 12px; margin-bottom: 18px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; animation-delay: 0.08s;
}
.cat-chip-scroll {
  flex: 1; display: flex; flex-wrap: wrap; gap: 6px; padding: 2px 0;
}
.cat-chip {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 14px; border-radius: 999px; white-space: nowrap;
  font-size: 13px; color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
  cursor: pointer; font-family: inherit;
  transition: all var(--cpq-transition-fast);
}
.cat-chip:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); background: var(--cpq-overlay-a6); }
.cat-chip.active { color: #06090E; background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); font-weight: 600; }
.cat-chip.active .cat-chip-count { background: rgba(6,9,14,0.25); color: #06090E; }
.cat-chip-ico { width: 14px; height: 14px; opacity: 0.85; }
.cat-chip-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cpq-text-muted); opacity: 0.6; }
.cat-chip.active .cat-chip-dot { background: #06090E; opacity: 1; }
.cat-chip-count {
  font-size: 11px; padding: 0 7px; line-height: 16px; border-radius: 10px;
  background: var(--cpq-overlay-w6); color: var(--cpq-text-muted);
  font-variant-numeric: tabular-nums;
}
.cat-manage-btn {
  flex-shrink: 0; display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 9px;
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary); cursor: pointer; font-family: inherit;
  transition: all var(--cpq-transition-fast);
}
.cat-manage-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }
.cat-manage-btn :deep(svg) { width: 15px; height: 15px; }

/* sidebar 规格折叠提示 */
.filter-hint {
  font-size: 12px; color: var(--cpq-text-muted); line-height: 1.6;
  padding: 12px 10px; border: 1px dashed var(--cpq-border-primary); border-radius: 8px; text-align: center;
}

/* ============ 主体布局 ============ */
.main-layout { display: flex; gap: 20px; align-items: flex-start; }

/* ============ 分类栏 ============ */
.category-sidebar {
  width: 220px;
  flex-shrink: 0;
  padding: 16px 12px;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  position: sticky;
  top: 24px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
  animation-delay: 0.05s;
}
.sidebar-title {
  font-size: 11px; font-weight: 600; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: 0.8px; padding: 0 8px 10px;
}
.sidebar-item {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 12px; border-radius: 9px; cursor: pointer; font-size: 13px;
  color: var(--cpq-text-secondary);
  transition: all var(--cpq-transition-fast);
  position: relative; margin-bottom: 2px;
}
.sidebar-ico { width: 15px; height: 15px; opacity: 0.8; }
.sidebar-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cpq-text-muted); opacity: 0.5; flex-shrink: 0; }
.sidebar-item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sidebar-item:hover { background: var(--cpq-overlay-a6); color: var(--cpq-text-primary); }
.sidebar-item.active {
  background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); font-weight: 500;
  box-shadow: inset 3px 0 0 var(--cpq-accent-primary);
}
.sidebar-item.active .sidebar-dot { background: var(--cpq-accent-primary); opacity: 1; }
.sidebar-item-count {
  font-size: 11px; color: var(--cpq-text-muted); background: var(--cpq-overlay-w6);
  padding: 1px 8px; border-radius: 10px; min-width: 26px; text-align: center;
  font-variant-numeric: tabular-nums;
}
.sidebar-item.active .sidebar-item-count { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary); }
.sidebar-footer { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--cpq-border-primary); }
.sidebar-manage-btn {
  display: flex; align-items: center; gap: 6px; width: 100%; padding: 7px 10px; border-radius: 8px;
  background: transparent; border: none; color: var(--cpq-text-secondary); font-size: 12px;
  cursor: pointer; font-family: inherit; transition: all var(--cpq-transition-fast);
}
.sidebar-manage-btn:hover { background: var(--cpq-overlay-a6); color: var(--cpq-accent-primary); }
.sidebar-manage-btn :deep(svg) { width: 14px; height: 14px; }

/* 筛选区 */
.filter-divider { height: 1px; background: var(--cpq-border-primary); margin: 14px 6px; }
.filter-group { padding: 0 6px; margin-bottom: 16px; }
.filter-title {
  font-size: 11px; font-weight: 600; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px;
}
.filter-opt {
  display: flex; align-items: center; gap: 9px; padding: 5px 8px; border-radius: 7px;
  font-size: 12.5px; color: var(--cpq-text-secondary); cursor: pointer;
  transition: all var(--cpq-transition-fast);
}
.filter-opt:hover { background: var(--cpq-overlay-a6); color: var(--cpq-text-primary); }
.filter-opt input { accent-color: var(--cpq-accent-primary); width: 14px; height: 14px; cursor: pointer; }
.filter-opt .opt-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.filter-opt .opt-count { font-size: 11px; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 6px 4px; }
.chip {
  font-size: 11.5px; padding: 3px 10px; border-radius: 10px;
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary); cursor: pointer;
  transition: all var(--cpq-transition-fast); user-select: none;
}
.chip:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-overlay-a20); }
.chip.active { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border-color: var(--cpq-overlay-a20); }
.chip-count { font-size: 10px; opacity: 0.7; margin-left: 3px; }
.clear-filter {
  width: calc(100% - 12px); margin: 2px 6px; padding: 8px; border-radius: 8px;
  background: transparent; border: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-secondary); font-size: 12px; cursor: pointer;
  font-family: inherit; transition: all var(--cpq-transition-fast);
}
.clear-filter:hover { color: var(--cpq-accent-danger); border-color: var(--cpq-accent-danger); }

/* ============ 内容区 ============ */
.content-area { flex: 1; min-width: 0; }

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; gap: 14px; padding: 12px 16px;
  border-radius: 14px; margin-bottom: 18px;
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; animation-delay: 0.1s;
}
.toolbar-search { width: 320px; }
.toolbar-sort { width: 160px; }
.toolbar-count { margin-left: auto; font-size: 13px; color: var(--cpq-text-muted); }
.toolbar-count b { color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }

.card-pagination { margin-top: 18px; display: flex; justify-content: flex-end; }

/* ============ 卡片网格 ============ */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 14px;
}
.model-card {
  position: relative;
  overflow: hidden;
  padding: 16px;
  border-radius: 14px;
  cursor: pointer;
  transition: transform 0.25s var(--cpq-ease-out-expo), box-shadow 0.25s var(--cpq-ease-out-expo);
  animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards;
}
.model-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 16px 40px rgba(0,0,0,0.45), 0 0 26px rgba(0,245,212,0.16), inset 0 1px 0 rgba(255,255,255,0.12);
}
.card-accent-bar {
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--cpq-accent-primary);
  transform: scaleX(0); transform-origin: left center;
  transition: transform 0.3s var(--cpq-ease-out-expo);
}
.model-card:hover .card-accent-bar { transform: scaleX(1); }
.model-card.no-price-card { opacity: 0.58; }

.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-category-tag {
  font-size: 11px; font-weight: 500; color: var(--cpq-accent-primary); letter-spacing: 0.2px;
  padding: 2px 10px; border-radius: 10px;
  background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a20);
}
.card-edit-btn {
  display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 8px;
  background: transparent; border: none; color: var(--cpq-text-muted); cursor: pointer;
  transition: all var(--cpq-transition-fast);
}
.card-edit-btn:hover { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.card-edit-btn :deep(svg) { width: 15px; height: 15px; }
.card-name { font-size: 14.5px; font-weight: 600; line-height: 1.35; margin-bottom: 7px; word-break: break-all; }
.card-sku { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; font-size: 11.5px; }
.sku-label { color: var(--cpq-text-muted); font-weight: 500; }
.sku-value { color: var(--cpq-text-secondary); cursor: pointer; font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.sku-value:hover { color: var(--cpq-accent-primary); text-decoration: underline; }
.card-price { display: flex; align-items: baseline; gap: 9px; margin-bottom: 12px; }
.price-value {
  font-size: 14px; font-weight: 600; color: var(--cpq-text-primary);
  font-variant-numeric: tabular-nums;
}
.price-sym { font-size: 12px; font-weight: 500; color: var(--cpq-text-secondary); }
.price-value.no-price { font-size: 13px; font-weight: 400; color: var(--cpq-text-muted); }
.price-date { font-size: 11px; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.card-meta {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  padding-top: 10px; border-top: 1px solid var(--cpq-border-primary);
}
.cond-badge { font-size: 11px; line-height: 18px; padding: 1px 9px; border-radius: 10px; border: 1px solid transparent; font-weight: 500; }
.cond-new { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border-color: var(--cpq-overlay-a20); }
.cond-refurb { color: var(--cpq-accent-warning); background: var(--cpq-overlay-warn30); border-color: var(--cpq-overlay-warn30); }
.cond-used { color: var(--cpq-text-muted); background: var(--cpq-overlay-w6); border-color: var(--cpq-border-light); }

/* 表格视图 */
.table-wrap { padding: 4px 8px; border-radius: 14px; }
.table-price { color: var(--cpq-accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.no-price { color: var(--cpq-text-muted); }

/* ============ 详情抽屉 ============ */
.detail-section { margin-bottom: 24px; }
.detail-section h4 {
  font-size: 14px; font-weight: 600; color: var(--cpq-text-primary);
  margin: 0 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-border-primary);
}
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-border-primary);
}
.section-header h4 { margin: 0; padding: 0; border: none; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.detail-field { display: flex; flex-direction: column; gap: 2px; }
.detail-field.full { margin-top: 12px; }
.field-label {
  font-size: 11px; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.field-value { font-size: 13px; color: var(--cpq-text-primary); }

.specs-table { border: 1px solid var(--cpq-border-primary); border-radius: 8px; overflow: hidden; }
.spec-row { display: flex; border-bottom: 1px solid var(--cpq-border-primary); }
.spec-row:last-child { border-bottom: none; }
.spec-key { width: 40%; padding: 8px 12px; background: var(--cpq-overlay-w6); font-size: 12px; font-weight: 500; color: var(--cpq-text-secondary); }
.spec-val { flex: 1; padding: 8px 12px; font-size: 13px; color: var(--cpq-text-primary); }

.chart-container { height: 150px; margin-bottom: 12px; padding: 12px; background: var(--cpq-overlay-w6); border-radius: 8px; }
.price-list { display: flex; flex-direction: column; gap: 4px; }
.price-item { display: flex; align-items: center; gap: 16px; padding: 6px 0; font-size: 12px; border-bottom: 1px solid var(--cpq-border-primary); }
.price-item:last-child { border-bottom: none; }
.price-date { color: var(--cpq-text-muted); min-width: 80px; font-variant-numeric: tabular-nums; }
.price-amount { color: var(--cpq-accent-primary); font-weight: 600; min-width: 80px; font-variant-numeric: tabular-nums; }
.price-note { color: var(--cpq-text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.compat-tags { display: flex; flex-wrap: wrap; gap: 6px; }
:deep(.compat-tag) { cursor: pointer; transition: all var(--cpq-transition-fast); }
:deep(.compat-tag:hover) { color: var(--cpq-accent-primary) !important; border-color: var(--cpq-accent-primary) !important; }

.drawer-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.drawer-title-name { font-size: 16px; font-weight: 600; color: var(--cpq-text-primary); }

.detail-actions { display: flex; gap: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--cpq-border-primary); }
.no-data { font-size: 12px; color: var(--cpq-text-muted); }

/* ============ 表单 ============ */
.edit-form { display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label { font-size: 13px; color: var(--cpq-text-secondary); font-weight: 500; }
.form-row-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.required { color: var(--cpq-accent-danger); }
.specs-editor { display: flex; flex-direction: column; gap: 6px; }
.spec-editor-row { display: flex; gap: 6px; align-items: center; }
.category-manage-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--cpq-border-primary); }
.category-edit-actions { display: flex; gap: 6px; }
.category-add-row { display: flex; gap: 8px; align-items: center; }

/* ============ 状态 ============ */
.loading-state { display: flex; justify-content: center; align-items: center; padding: 60px 0; color: var(--cpq-text-muted); font-size: 14px; }
.empty-state { display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 12px; padding: 60px 0; color: var(--cpq-text-muted); font-size: 14px; }
.empty-icon { font-size: 36px; line-height: 1; color: var(--cpq-text-muted); }
.empty-text { color: var(--cpq-text-muted); }

/* ============ Antd 暗色覆盖 ============ */
:deep(.ant-input), :deep(.ant-input-number), :deep(.ant-input-number-input),
:deep(.ant-input-affix-wrapper), :deep(.ant-input-search .ant-input) {
  background: var(--cpq-overlay-w6) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-input-affix-wrapper:focus),
:deep(.ant-input-affix-wrapper-focused) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a10) !important;
}
:deep(.ant-select-selector) {
  background: var(--cpq-overlay-w6) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-select-dropdown) { background: var(--cpq-bg-secondary) !important; }
:deep(.ant-select-item) { color: var(--cpq-text-primary) !important; }
:deep(.ant-select-item-option-active) { background: var(--cpq-overlay-a8) !important; }
:deep(.ant-picker) {
  background: var(--cpq-overlay-w6) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}
:deep(.ant-picker-input > input) { color: var(--cpq-text-primary) !important; }
:deep(.ant-modal-content) { background: var(--cpq-bg-secondary) !important; color: var(--cpq-text-primary) !important; }
:deep(.ant-modal-header) { background: var(--cpq-bg-secondary) !important; }
:deep(.ant-modal-title) { color: var(--cpq-text-primary) !important; }
:deep(.ant-drawer-content) { background: var(--cpq-bg-secondary) !important; }
:deep(.ant-drawer-header) { background: var(--cpq-bg-secondary) !important; border-bottom-color: var(--cpq-border-primary) !important; }
:deep(.ant-drawer-title) { color: var(--cpq-text-primary) !important; }
:deep(.ant-spin-text) { color: var(--cpq-text-muted) !important; }
:deep(.ant-tag) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); color: var(--cpq-text-secondary); }
:deep(.ant-table) { background: transparent !important; }
:deep(.ant-table-thead > tr > th) {
  background: var(--cpq-overlay-w6) !important;
  color: var(--cpq-text-secondary) !important;
  border-bottom-color: var(--cpq-border-primary) !important;
  font-weight: 600;
}
:deep(.ant-table-tbody > tr > td) { border-bottom-color: var(--cpq-border-primary) !important; color: var(--cpq-text-primary) !important; }
:deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-a4) !important; }
:deep(.ant-pagination .ant-pagination-item) { background: var(--cpq-overlay-w6); border-color: var(--cpq-border-primary); }
:deep(.ant-pagination .ant-pagination-item a) { color: var(--cpq-text-secondary); }
:deep(.ant-pagination .ant-pagination-item-active) { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
:deep(.ant-pagination .ant-pagination-item-active a) { color: #06090E; }
:deep(.ant-divider) { border-color: var(--cpq-border-primary); }
</style>
