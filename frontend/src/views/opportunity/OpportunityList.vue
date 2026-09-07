<template>
  <div class="opp-page">
    <!-- 顶栏：标题 + 宽搜索 + 图标按钮 + 新建 -->
    <header class="page-head glass-strong">
      <div class="page-title">
        <h1>商机驾驶舱</h1>
        <span class="page-sub">数据区间：{{ summary.period_label || '—' }}</span>
      </div>
      <div class="head-icons">
        <a-tooltip title="图表栏">
          <button class="icon-btn" :class="{ active: chartsPanelOpen }" @click="chartsPanelOpen = !chartsPanelOpen"><BarChartOutlined /></button>
        </a-tooltip>
        <a-tooltip title="AI 线索">
          <button class="icon-btn" @click="router.push('/ai-leads')"><RobotOutlined /></button>
        </a-tooltip>
        <a-tooltip title="回收站">
          <button class="icon-btn" @click="goToRecycleBin"><RestOutlined /></button>
        </a-tooltip>
        <button class="create-btn" @click="showCreateModal = true"><PlusOutlined /> 新建商机</button>
      </div>
    </header>

    <div class="main-split">
      <!-- 左栏：KPI + 周期 + 图表单列上下滑 -->
      <aside v-show="chartsPanelOpen" class="charts-panel glass">
        <div class="charts-tools">
          <div class="period-toggle">
            <label v-for="p in periods" :key="p.value" class="period-option" :class="{ active: period === p.value && !customRange }" @click="setPeriod(p.value)">
              <span class="period-dot" :class="{ active: period === p.value && !customRange }"></span>
              {{ p.label }}
            </label>
            <a-popover v-model:open="customOpen" trigger="click" placement="bottomRight" overlay-class-name="period-custom-pop">
              <template #content>
                <div class="custom-panel">
                  <div class="custom-sec">
                    <div class="custom-sec-title">快捷区间</div>
                    <div class="preset-grid">
                      <button v-for="ps in presets" :key="ps.key" class="preset-btn" :class="{ active: customRange?.key === ps.key }" @click="applyPreset(ps)">{{ ps.label }}</button>
                    </div>
                  </div>
                  <div class="custom-sec">
                    <div class="custom-sec-title">指定月份</div>
                    <a-date-picker v-model:value="monthValue" picker="month" size="small" placeholder="选择月份" @change="onMonthChange" />
                  </div>
                  <div class="custom-sec">
                    <div class="custom-sec-title">自定义区间</div>
                    <a-range-picker v-model:value="rangeValue" size="small" @change="onRangeChange" />
                  </div>
                  <div v-if="customRange" class="custom-foot">
                    <span class="custom-cur">当前：{{ customRange.shortLabel }}</span>
                    <button class="preset-btn ghost" @click="clearCustom">重置</button>
                  </div>
                </div>
              </template>
              <label class="period-option custom-entry" :class="{ active: !!customRange }">
                <span class="period-dot" :class="{ active: !!customRange }"></span>
                <span class="custom-text">{{ customRange ? customRange.shortLabel : '自定义' }}</span>
                <span class="custom-caret">▾</span>
              </label>
            </a-popover>
          </div>
        </div>
        <div class="charts-body">
          <OpportunityCharts
            v-if="chartsReady"
            :summary="summary"
            :can-view-all="canViewAll"
            :table-total="tableTotal"
            :recent-opps="recentOpps"
            :is-mobile="isMobile"
            @drill-on="drillOn"
            @open-list-drawer="scrollToTable"
          />
          <div v-else class="charts-loading">图表加载中…</div>
        </div>
      </aside>

      <!-- 右栏：筛选 + 宽表 -->
      <section class="table-side">
        <div class="kpi-strip">
          <div class="kpi-card" v-for="k in kpiItems" :key="k.key">
            <span class="kpi-label">{{ k.label }}</span>
            <span class="kpi-num">{{ k.value }}</span>
          </div>
        </div>
        <div v-if="drill.active" class="drill-hint">
          <span>已筛选：{{ drill.label }}（点击图表可切换/清除）</span>
          <button @click="drillOff">清除筛选 ✕</button>
        </div>

        <div class="table-card glass">
          <div class="filter-row">
            <input v-model="filters.search" class="search-input dark-input" placeholder="搜索客户 / 业务 / 商机号" @input="debounceFilter" />
            <a-select v-model:value="filters.status" size="small" class="dark-select" style="width: 104px" @change="onFilterChange">
              <a-select-option value="all">全部状态</a-select-option>
              <a-select-option value="pending">进行中</a-select-option>
              <a-select-option value="won">已中标</a-select-option>
              <a-select-option value="lost">已丢标</a-select-option>
              <a-select-option value="expired">已过期</a-select-option>
            </a-select>
            <a-select v-model:value="filters.platform" size="small" mode="multiple" placeholder="平台" :maxTagCount="1" class="dark-select" style="min-width: 128px" @change="onFilterChange">
              <a-select-option v-for="s in seriesStore.items" :key="s.value" :value="s.value">{{ s.label }}</a-select-option>
              <a-select-option value="其他">其他</a-select-option>
            </a-select>
            <a-select v-model:value="filters.chassis" size="small" mode="multiple" placeholder="形态" :maxTagCount="1" class="dark-select" style="min-width: 112px" @change="onFilterChange">
              <a-select-option value="2U">2U</a-select-option>
              <a-select-option value="4U">4U</a-select-option>
              <a-select-option value="5U">5U</a-select-option>
              <a-select-option value="4.5U">4.5U</a-select-option>
              <a-select-option value="8U">8U</a-select-option>
              <a-select-option value="工作站">工作站</a-select-option>
            </a-select>
            <a-select
              v-if="canViewAll"
              v-model:value="filters.sales_person"
              size="small"
              class="dark-select"
              style="min-width: 120px"
              placeholder="业务"
              allow-clear
              show-search
              option-filter-prop="label"
              :options="salesOptions"
              @change="onFilterChange"
            />
            <button class="reset-btn" @click="resetFilters">重置</button>
            <span class="filter-count">共 {{ tableTotal }} 条</span>
          </div>

          <a-table
            :dataSource="tableData"
            :columns="tableColumns"
            :pagination="tablePagination"
            :loading="tableLoading"
            size="small"
            class="opp-table"
            rowKey="opportunity_id"
            :rowSelection="rowSelectionCfg"
            :scroll="{ x: 860 }"
            @change="onTableChange"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'customer_name'">
                <div class="cell-customer">
                  <div class="name-row">
                    <a class="opp-name" @click="goToDetail(record.opportunity_id)">{{ record.customer_name || '未命名客户' }}</a>
                    <a-dropdown :trigger="['click']" placement="bottomLeft">
                      <a-tag :color="bizTagColor(record)" class="opp-status-pick">{{ bizStatusText(record) }}<span class="opp-caret">▾</span></a-tag>
                      <template #overlay>
                        <a-menu @click="(e: any) => changeResult(record, e.key)">
                          <a-menu-item v-for="o in RESULT_OPTIONS" :key="o.value">
                            <span :style="{ display:'inline-block', width:'7px', height:'7px', borderRadius:'50%', marginRight:'7px', verticalAlign:'middle', background: o.dot }"></span><span :style="{ fontWeight: o.value === record.result ? 600 : 400 }">{{ o.label }}</span>
                          </a-menu-item>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </div>
                  <div v-if="oppMetaLine(record)" class="opp-meta">{{ oppMetaLine(record) }}</div>
                </div>
              </template>
              <template v-else-if="column.key === 'platform'">
                <span class="cell-plat">{{ record.platform_type || '—' }}</span>
              </template>
              <template v-else-if="column.key === 'chassis'">
                <span class="cell-plat">{{ record.chassis_form || '—' }}</span>
              </template>
              <template v-else-if="column.dataIndex === 'purchase_qty'">
                <span class="cell-num"><b>{{ record.purchase_qty || 0 }}</b><i>台</i></span>
              </template>
              <template v-else-if="column.dataIndex === 'config_count'">
                <span class="cell-num"><b>{{ record.config_count ?? 0 }}</b><i>套</i></span>
              </template>
              <template v-else-if="column.dataIndex === 'created_at'">
                <div class="cell-dt">
                  <span class="dt-main">{{ fmtDateTime(record.created_at) }}</span>
                  <span class="dt-rel">{{ relTime(record.created_at) }}</span>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'updated_at'">
                <div class="cell-dt">
                  <span class="dt-main">{{ fmtDateTime(record.updated_at) }}</span>
                  <span class="dt-rel">{{ relTime(record.updated_at) }}</span>
                </div>
              </template>
              <template v-else-if="column.key === 'actions'">
                <a-dropdown :trigger="['click']" placement="bottomRight">
                  <button class="row-more"><MoreOutlined /></button>
                  <template #overlay>
                    <a-menu @click="(e: any) => onRowMenu(e.key, record)">
                      <a-menu-item key="open">打开</a-menu-item>
                      <a-menu-item key="rename">重命名</a-menu-item>
                      <a-menu-divider />
                      <a-menu-item key="trash" danger>移至回收站</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </template>
            </template>
          </a-table>
        </div>
      </section>
    </div>

    <!-- 悬浮批量操作条 -->
    <Transition name="batch-fade">
      <div v-if="selectedRowKeys.length" class="batch-float glass-strong">
        <span class="batch-count">已选 <b>{{ selectedRowKeys.length }}</b> 项</span>
        <button class="batch-btn danger" :disabled="batching" @click="handleBatchTrash">移至回收站</button>
        <button class="batch-btn" @click="selectedRowKeys = []">取消</button>
      </div>
    </Transition>

    <!-- 重命名 modal -->
    <a-modal v-model:open="renameOpen" title="重命名商机" ok-text="保存" cancel-text="取消" :confirm-loading="renaming" @ok="confirmRename">
      <a-input v-model:value="renameValue" placeholder="客户名称" :maxlength="60" @pressEnter="confirmRename" />
    </a-modal>

    <CreateOpportunityModal v-model:open="showCreateModal" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onActivated, watch, nextTick, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { BarChartOutlined, RobotOutlined, RestOutlined, PlusOutlined, MoreOutlined } from '@ant-design/icons-vue'
import axios from 'axios'
import CreateOpportunityModal from '@/components/opportunity/CreateOpportunityModal.vue'
import dayjs from 'dayjs'
import { useSeriesStore } from '@/stores/series'
import { useAuthStore } from '@/store/auth'

const OpportunityCharts = defineAsyncComponent(() => import('@/components/opportunity/OpportunityCharts.vue'))

defineOptions({ name: 'OpportunityList' })

const router = useRouter()
const auth = useAuthStore()
const canViewAll = computed(() => auth.can('page.opportunities_all'))
// 全平台系列权威源（l6.server_types（设置-服务器管理-产品系列））：筛选下拉读这里，不再硬编码 Orion/Polaris
const seriesStore = useSeriesStore()

// 图表延迟挂载：左栏默认展开，空闲时再挂载 ECharts
const chartsPanelOpen = ref(true)
const chartsReady = ref(false)
let chartsScheduled = false
function scheduleCharts() {
  if (chartsScheduled) return
  chartsScheduled = true
  const show = () => { chartsReady.value = true }
  const idleWindow = window as any
  if (typeof idleWindow.requestIdleCallback === 'function') {
    idleWindow.requestIdleCallback(show, { timeout: 250 })
  } else {
    setTimeout(show, 0)
  }
}
watch(chartsPanelOpen, (v) => {
  if (v) scheduleCharts()
  nextTick(() => onViewportResize())
})

const periods = [
  { label: '本周', value: 'week' },
  { label: '本月', value: 'month' },
  { label: '本年', value: 'year' },
]
const period = ref('week')

// 自定义区间：上周/上月/去年/近30/近90/指定月/任意区间
type CustomRange = { key: string; start: string; end: string; shortLabel: string }
const customRange = ref<CustomRange | null>(null)
const customOpen = ref(false)
const monthValue = ref<any>(null)
const rangeValue = ref<any>(null)

const presets = [
  { key: 'lastWeek', label: '上周' },
  { key: 'lastMonth', label: '上月' },
  { key: 'lastYear', label: '去年' },
  { key: 'last30', label: '近30天' },
  { key: 'last90', label: '近90天' },
]

function fmt(d: dayjs.Dayjs) { return d.format('YYYY-MM-DD') }
function rangeShortLabel(s: string, e: string) {
  const sd = dayjs(s), ed = dayjs(e)
  return sd.year() === ed.year() ? `${sd.format('M.DD')}-${ed.format('M.DD')}` : `${sd.format('YYYY.M.D')}-${ed.format('YYYY.M.D')}`
}
function applyRange(key: string, start: dayjs.Dayjs, end: dayjs.Dayjs, shortLabel: string) {
  customRange.value = { key, start: fmt(start), end: fmt(end), shortLabel }
  monthValue.value = null
  rangeValue.value = null
  customOpen.value = false
}
function applyPreset(p: { key: string; label: string }) {
  const today = dayjs()
  let s: dayjs.Dayjs, e: dayjs.Dayjs
  if (p.key === 'lastWeek') {
    const dow = (today.day() + 6) % 7
    s = today.subtract(dow + 7, 'day')
    e = s.add(6, 'day')
  } else if (p.key === 'lastMonth') {
    s = today.subtract(1, 'month').startOf('month')
    e = today.subtract(1, 'month').endOf('month')
  } else if (p.key === 'lastYear') {
    s = today.subtract(1, 'year').startOf('year')
    e = today.subtract(1, 'year').endOf('year')
  } else if (p.key === 'last30') {
    s = today.subtract(29, 'day'); e = today
  } else {
    s = today.subtract(89, 'day'); e = today
  }
  applyRange(p.key, s, e, p.label)
}
function onMonthChange(d: any) {
  if (!d) return
  applyRange(`month:${d.format('YYYY-MM')}`, d.startOf('month'), d.endOf('month'), d.format('YYYY-MM'))
}
function onRangeChange(dates: any) {
  if (!dates || dates.length !== 2) return
  const [s, e] = dates
  applyRange(`range:${s.format('YYYY-MM-DD')}~${e.format('YYYY-MM-DD')}`, s.startOf('day'), e.endOf('day'), rangeShortLabel(s.format('YYYY-MM-DD'), e.format('YYYY-MM-DD')))
}
function clearCustom() {
  customRange.value = null
  monthValue.value = null
  rangeValue.value = null
  period.value = 'week'
  customOpen.value = false
}

const dataLoading = ref(false)
const summary = ref<{ period_label: string; kpi: Record<string, any>; charts: Record<string, any>; structure: any; dates: any[] }>({ period_label: '', kpi: {}, charts: {}, structure: { platforms: [], chassis: [] }, dates: [] })

const kpiItems = computed(() => {
  const k: any = summary.value.kpi || {}
  return [
    { key: 'opp', label: '总商机数', value: k.total_opportunities ?? 0 },
    { key: 'cfg', label: '总配置数', value: k.total_configs ?? 0 },
    { key: 'newOpp', label: '周期新增商机', value: k.new_opportunities ?? 0 },
    { key: 'newCfg', label: '周期新增配置', value: k.new_configs ?? 0 },
  ]
})

// Filters / drill / batch select
const filters = ref({ status: 'all', platform: [] as string[], chassis: [] as string[], sales_person: '', search: '' })
const salesOptions = ref<{ value: string; label: string }[]>([])
const sortBy = ref('updated_at')
const sortOrder = ref('desc')
let filterTimer: ReturnType<typeof setTimeout> | null = null
const drill = ref({ active: false, platform: '', chassis: '', label: '' })
const isMobile = ref(false)
function syncMobile() { isMobile.value = window.matchMedia('(max-width: 768px)').matches }
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null
const selectedRowKeys = ref<string[]>([])
const batching = ref(false)

function debounceFilter() {
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(() => {
    loadSummary()
    loadTable()
  }, 300)
}
function onFilterChange() {
  loadSummary()
  loadTable()
}
function resetFilters() {
  filters.value = { status: 'all', platform: [], chassis: [], sales_person: '', search: '' }
  drill.value = { active: false, platform: '', chassis: '', label: '' }
  loadSummary()
  loadTable()
}
function drillOn(type: string, name: string) {
  if (!name) return
  if (type === 'platform') {
    drill.value.platform = drill.value.platform === name ? '' : name
  } else {
    drill.value.chassis = drill.value.chassis === name ? '' : name
  }
  drill.value.active = !!(drill.value.platform || drill.value.chassis)
  const parts: string[] = []
  if (drill.value.platform) parts.push(`平台: ${drill.value.platform}`)
  if (drill.value.chassis) parts.push(`机箱: ${drill.value.chassis}`)
  drill.value.label = parts.join(' + ')
  loadSummary()
  loadTable()
}
function drillOff() {
  drill.value = { active: false, platform: '', chassis: '', label: '' }
  loadSummary()
  loadTable()
}

// Table
const tableData = ref<any[]>([])
const tableLoading = ref(false)
const tablePage = ref(1)
const tablePageSize = ref(10)
const tableTotal = ref(0)
// 商机磁贴预览（移动端图表区的列表卡）：取当前页前 5 条
const recentOpps = computed(() =>
  tableData.value.slice(0, 5).map((r: any) => ({
    id: r.opportunity_id,
    name: r.customer_name || '未命名客户',
    platform: r.platform_type || '',
  }))
)
const tableColumns = [
  { title: '客户 / 状态', dataIndex: 'customer_name', key: 'customer' },
  { title: '业务', dataIndex: 'sales_person', width: 100, ellipsis: true },
  { title: '平台', dataIndex: 'platform_type', key: 'platform', width: 96 },
  { title: '形态', dataIndex: 'chassis_form', key: 'chassis', width: 84 },
  { title: '数量', dataIndex: 'purchase_qty', width: 80 },
  { title: '配置', dataIndex: 'config_count', width: 72 },
  { title: '创建时间', dataIndex: 'created_at', width: 116 },
  { title: '更新时间', dataIndex: 'updated_at', width: 116, sorter: true, defaultSortOrder: 'descend' as const },
  { title: '', key: 'actions', width: 60, align: 'center' as const },
]
const tablePagination = computed(() => ({
  current: tablePage.value, pageSize: tablePageSize.value, total: tableTotal.value,
  showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['6', '8', '10', '15', '20', '30', '50'],
}))
function onTableChange(pag: any, _f: any, sorter: any) {
  tablePage.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== tablePageSize.value) {
    tablePageSize.value = pag.pageSize
    userPickedPageSize.value = true
  }
  if (sorter && (sorter.field === 'updated_at' || sorter.field === 'created_at') && sorter.order) {
    sortBy.value = sorter.field
    sortOrder.value = sorter.order === 'ascend' ? 'asc' : 'desc'
  } else {
    sortBy.value = 'updated_at'
    sortOrder.value = 'desc'
  }
  loadTable()
}

// 列表 pageSize 自适应容器高度：按表格卡片可用高度 ÷ 行高计算每页行数，
// 窗口缩放 / 左栏收展实时重算始终填满；用户手选 pageSize 后停止自适应。
const userPickedPageSize = ref(false)
const ADAPTIVE_ROW_H = 60
const ADAPTIVE_RESERVED_H = 88 // 表头 + 分页条
const ADAPTIVE_MIN = 6
const ADAPTIVE_MAX = 50
function computeAdaptivePageSize(): number {
  const card = document.querySelector('.table-card') as HTMLElement | null
  if (!card || !card.clientHeight) return tablePageSize.value
  const usable = card.clientHeight - ADAPTIVE_RESERVED_H
  if (usable <= 0) return ADAPTIVE_MIN
  return Math.min(ADAPTIVE_MAX, Math.max(ADAPTIVE_MIN, Math.floor(usable / ADAPTIVE_ROW_H)))
}
let resizeTimer: ReturnType<typeof setTimeout> | undefined
function onViewportResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(async () => {
    if (userPickedPageSize.value) return
    const next = computeAdaptivePageSize()
    if (next !== tablePageSize.value) {
      tablePageSize.value = next
      tablePage.value = 1
      await loadTable()
    }
  }, 200)
}

// 业务结果枚举（列表标签 + 内联切换菜单 + 详情页共用口径）
const RESULT_OPTIONS = [
  { value: 'pending', label: '进行中', color: 'processing', dot: '#1677FF' },
  { value: 'won', label: '已中标', color: 'success', dot: '#52C9A0' },
  { value: 'lost', label: '已丢标', color: 'error', dot: '#FF6B6B' },
  { value: 'expired', label: '已过期', color: 'warning', dot: '#F4D28A' },
] as const
function bizStatusText(r: any) {
  return RESULT_OPTIONS.find((o) => o.value === r?.result)?.label ?? '进行中'
}
function bizTagColor(r: any) {
  return RESULT_OPTIONS.find((o) => o.value === r?.result)?.color ?? 'default'
}
function resultLabel(val: string) {
  return RESULT_OPTIONS.find((o) => o.value === val)?.label ?? val
}
// 列表内联改业务结果：乐观更新标签 → 存库 → 离筛选行本地移除 + 刷新图表（不刷表避免行跳动）
async function changeResult(record: any, val: string) {
  if (val === record.result) return
  const idx = tableData.value.findIndex((r: any) => r.opportunity_id === record.opportunity_id)
  if (idx < 0) return
  const prev = tableData.value[idx].result
  tableData.value[idx] = { ...tableData.value[idx], result: val }
  try {
    await axios.put(`/api/opportunities/${record.opportunity_id}/meta`, { result: val })
    message.success(`状态已改为「${resultLabel(val)}」`)
    if (filters.value.status !== 'all' && filters.value.status !== val) {
      tableData.value = tableData.value.filter((r: any) => r.opportunity_id !== record.opportunity_id)
      tableTotal.value = Math.max(0, tableTotal.value - 1)
    }
    loadSummary()
  } catch {
    tableData.value[idx] = { ...tableData.value[idx], result: prev }
    message.error('状态更新失败')
  }
}
// 客户单元格第二行元信息：行业 · 订单类型 · 报价份数
function oppMetaLine(r: any) {
  const parts: string[] = []
  if (r.industry) parts.push(r.industry)
  if (r.order_type) parts.push(r.order_type)
  if (r.quotation_count > 0) parts.push(`${r.quotation_count} 份报价`)
  return parts.join(' · ')
}
// 时间：同年显示 MM-DD HH:mm，跨年带年份；第二行相对时间
function fmtDateTime(s: string) {
  if (!s) return '-'
  const now = new Date()
  const sameYear = Number(s.slice(0, 4)) === now.getFullYear()
  return sameYear ? s.slice(5, 16) : s.slice(0, 10)
}
function relTime(s: string) {
  if (!s) return ''
  const t = new Date(s.replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  const m = Math.floor(diff / 60_000)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d} 天前`
  if (d < 30) return `${Math.floor(d / 7)} 周前`
  return `${Math.floor(d / 30)} 个月前`
}
function goToDetail(id: string) { router.push(`/opportunities/${id}`) }
function goToRecycleBin() { router.push('/recycle-bin') }
// 移动端图表区「商机列表」磁贴：平滑滚到右栏（下方）表格
function scrollToTable() {
  document.querySelector('.table-side')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const rowSelectionCfg = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: any[]) => { selectedRowKeys.value = keys as string[] },
}))
async function handleBatchTrash() {
  if (selectedRowKeys.value.length === 0) return
  batching.value = true
  try {
    await axios.post('/api/opportunities/batch-trash', { opportunity_ids: selectedRowKeys.value })
    message.success(`已将 ${selectedRowKeys.value.length} 项移至回收站`)
    selectedRowKeys.value = []
    reloadAll({ resetPage: true })
  } finally { batching.value = false }
}

// 行菜单：打开 / 重命名 / 移至回收站
function onRowMenu(key: string, record: any) {
  if (key === 'open') goToDetail(record.opportunity_id)
  else if (key === 'rename') openRename(record)
  else if (key === 'trash') trashOne(record)
}
function trashOne(record: any) {
  Modal.confirm({
    title: '移至回收站',
    content: `将「${record.customer_name || '未命名客户'}」移至回收站？可在回收站恢复。`,
    okText: '移至回收站', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      await axios.post(`/api/opportunities/${record.opportunity_id}/trash`)
      message.success('已移至回收站')
      reloadAll({ resetPage: tableData.value.length <= 1 && tablePage.value > 1 })
    },
  })
}

// 重命名
const renameOpen = ref(false)
const renameValue = ref('')
const renameTarget = ref<any>(null)
const renaming = ref(false)
function openRename(record: any) {
  renameTarget.value = record
  renameValue.value = record.customer_name || ''
  renameOpen.value = true
}
async function confirmRename() {
  const name = renameValue.value.trim()
  if (!name) { message.warning('请输入客户名称'); return }
  if (!renameTarget.value) return
  renaming.value = true
  try {
    await axios.put(`/api/opportunities/${renameTarget.value.opportunity_id}/meta`, { customer_name: name })
    const idx = tableData.value.findIndex((r: any) => r.opportunity_id === renameTarget.value.opportunity_id)
    if (idx >= 0) tableData.value[idx] = { ...tableData.value[idx], customer_name: name }
    message.success('已重命名')
    renameOpen.value = false
    loadSummary()
  } catch {
    message.error('重命名失败')
  } finally { renaming.value = false }
}

async function loadTable() {
  selectedRowKeys.value = []
  tableLoading.value = true
  try {
    const params: any = { page: tablePage.value, page_size: tablePageSize.value }
    if (filters.value.search) params.search = filters.value.search
    if (filters.value.status !== 'all') {
      params.result = filters.value.status
    }
    if (drill.value.platform) {
      params.platform = drill.value.platform
    } else if (Array.isArray(filters.value.platform) && filters.value.platform.length > 0) {
      params.platform = filters.value.platform.join(',')
    }
    if (drill.value.chassis) {
      params.chassis = drill.value.chassis
    } else if (Array.isArray(filters.value.chassis) && filters.value.chassis.length > 0) {
      params.chassis = filters.value.chassis.join(',')
    }
    if (canViewAll.value && filters.value.sales_person) params.sales_person = filters.value.sales_person
    params.sort_by = sortBy.value
    params.sort_order = sortOrder.value
    const res = await axios.get('/api/opportunities/list', { params })
    tableData.value = res.data.items || []
    tableTotal.value = res.data.total || 0
  } finally {
    tableLoading.value = false
  }
  syncListState()
}

// 列表分页/筛选状态持久化到 sessionStorage，跳详情再回来可恢复
// （不依赖 URL query —— 详情页返回按钮用 router.push('/opportunities') 不带 query，URL 方案会被击穿）
const LIST_STATE_KEY = 'opp_list_state'
function restoreListState() {
  let s: any = null
  try { s = JSON.parse(sessionStorage.getItem(LIST_STATE_KEY) || '') } catch { return }
  if (!s) return
  if (s.page) tablePage.value = Number(s.page) || 1
  if (s.status) filters.value.status = String(s.status) === 'archived' ? 'expired' : String(s.status)
  if (Array.isArray(s.platform)) filters.value.platform = s.platform
  if (Array.isArray(s.chassis)) filters.value.chassis = s.chassis
  if (typeof s.search === 'string') filters.value.search = s.search
  if (s.drill_platform) drill.value.platform = String(s.drill_platform)
  if (s.drill_chassis) drill.value.chassis = String(s.drill_chassis)
  if (drill.value.platform || drill.value.chassis) {
    drill.value.active = true
    const parts: string[] = []
    if (drill.value.platform) parts.push(`平台: ${drill.value.platform}`)
    if (drill.value.chassis) parts.push(`机箱: ${drill.value.chassis}`)
    drill.value.label = parts.join(' + ')
  }
  if (s.sort) sortBy.value = String(s.sort)
}

function syncListState() {
  try {
    sessionStorage.setItem(LIST_STATE_KEY, JSON.stringify({
      page: tablePage.value,
      status: filters.value.status,
      platform: filters.value.platform,
      chassis: filters.value.chassis,
      search: filters.value.search,
      drill_platform: drill.value.platform,
      drill_chassis: drill.value.chassis,
      sort: sortBy.value,
    }))
  } catch { /* sessionStorage 不可用时静默降级 */ }
}

// Create modal
const showCreateModal = ref(false)

// Data loading
async function loadSummary() {
  dataLoading.value = true
  try {
    const params: any = {}
    if (customRange.value) { params.start = customRange.value.start; params.end = customRange.value.end }
    else { params.period = period.value }
    if (filters.value.status !== 'all') params.result = filters.value.status
    if (drill.value.platform) {
      params.platform = drill.value.platform
    } else if (Array.isArray(filters.value.platform) && filters.value.platform.length > 0) {
      params.platform = filters.value.platform.join(',')
    }
    if (drill.value.chassis) {
      params.chassis = drill.value.chassis
    } else if (Array.isArray(filters.value.chassis) && filters.value.chassis.length > 0) {
      params.chassis = filters.value.chassis.join(',')
    }
    if (filters.value.search) params.search = filters.value.search
    if (canViewAll.value && filters.value.sales_person) params.sales_person = filters.value.sales_person
    const res = await axios.get('/api/dashboard/summary', { params })
    summary.value = res.data
  } finally { dataLoading.value = false }
}
async function reloadAll({ resetPage = false }: { resetPage?: boolean } = {}) {
  await loadSummary()
  // 首屏恢复页码时不能重置；切周期 / 新建 / 批量删除 等显式传 resetPage:true 才回到第 1 页
  if (resetPage) tablePage.value = 1
  await loadTable()
  if (chartsPanelOpen.value) scheduleCharts()
}
function setPeriod(p: string) { customRange.value = null; period.value = p }

onMounted(async () => {
  seriesStore.ensureSeries()
  if (canViewAll.value) {
    try {
      const res = await axios.get('/api/opportunities/sales-options')
      salesOptions.value = (res.data.items || []).map((name: string) => ({ value: name, label: name }))
    } catch { /* 销售筛选选项加载失败不阻塞列表 */ }
  }
  restoreListState()
  // 首屏自适应 pageSize（等布局稳定），再加载全部数据
  nextTick(() => {
    if (!userPickedPageSize.value) {
      const adapt = computeAdaptivePageSize()
      if (adapt !== tablePageSize.value) tablePageSize.value = adapt
    }
    reloadAll()
  })
  window.addEventListener('resize', onViewportResize)
  // 窄屏监听：图表磁贴 / 布局分支共用 isMobile
  syncMobile()
  const mq = window.matchMedia('(max-width: 768px)')
  _mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', _mqListener)
})
onBeforeUnmount(() => {
  if (filterTimer) clearTimeout(filterTimer)
  if (resizeTimer) clearTimeout(resizeTimer)
  window.removeEventListener('resize', onViewportResize)
  if (_mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', _mqListener)
})
// KeepAlive：切回时刷新数据（首次挂载由 onMounted 加载，避免重复请求）
let _oppActivated = false
onActivated(() => {
  if (!_oppActivated) {
    _oppActivated = true
    return
  }
  reloadAll()
})
watch([() => period.value, () => customRange.value], () => reloadAll({ resetPage: true }))
</script>

<style scoped>
.opp-page { display: flex; flex-direction: column; gap: 12px; padding: 14px 20px 16px; height: calc(100vh - 56px); overflow: hidden; }

/* 顶栏 */
.page-head { display: flex; align-items: center; gap: 14px; padding: 12px 18px; border-radius: var(--cpq-radius-lg); flex: none; }
.page-title { display: flex; flex-direction: column; gap: 1px; flex: none; }
.page-title h1 { margin: 0; font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); letter-spacing: 1px; }
.page-sub { font-size: 11px; color: var(--cpq-text-muted); letter-spacing: 0.5px; }
.search-input { flex: 1 1 150px; min-width: 130px; max-width: 300px; height: 28px; border-radius: 6px; font-size: 12.5px; padding: 0 10px; }
.head-icons { display: flex; align-items: center; gap: 8px; margin-left: auto; flex: none; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
  border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary);
  border-radius: 8px; cursor: pointer; font-size: 15px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.icon-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.icon-btn.active { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); border-color: var(--cpq-accent-primary); }
.create-btn {
  display: inline-flex; align-items: center; gap: 5px; height: 34px; padding: 0 16px;
  background: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); border: 1px solid var(--cpq-accent-primary);
  border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; transition: opacity var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.create-btn:hover { opacity: 0.9; }

/* 左右两栏 */
.main-split { flex: 1 1 0; min-height: 0; display: flex; gap: 12px; }

/* 左栏：图表单列上下滑；宽度随视口比例自适应（约 1/3 屏，窄屏收窄宽屏封顶） */
.charts-panel {
  flex: 0 0 clamp(360px, 34vw, 660px);
  display: flex; flex-direction: column; gap: 10px;
  padding: 12px 12px 14px; border-radius: var(--cpq-radius-lg);
  overflow: hidden; overscroll-behavior: contain;
}
.charts-panel::-webkit-scrollbar { width: 6px; }
.charts-panel::-webkit-scrollbar-thumb { background: var(--cpq-overlay-a20); border-radius: 3px; }
.charts-panel::-webkit-scrollbar-track { background: transparent; }

.kpi-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; flex: none; }
.kpi-card {
  padding: 14px 16px;
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-overlay-w5);
  border: 1px solid var(--cpq-overlay-w8);
  display: flex; flex-direction: column; gap: 6px;
  transition: transform var(--cpq-dur-1) var(--cpq-ease-smooth), box-shadow var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: var(--cpq-shadow-lg, 0 8px 24px rgba(0,0,0,0.18)); }
.kpi-label { font-size: 12px; color: var(--cpq-text-secondary); white-space: nowrap; }
.kpi-num { font-size: 28px; font-weight: 700; color: var(--cpq-text-primary); font-variant-numeric: tabular-nums lining-nums; line-height: 1.1; }

.charts-tools { flex: none; display: flex; align-items: center; }
.period-toggle { display: flex; gap: 6px; flex-wrap: wrap; }
.period-option { display: flex; align-items: center; gap: 5px; padding: 5px 11px; border: 1px solid var(--cpq-overlay-w10); border-radius: 999px; cursor: pointer; font-size: 12px; color: var(--cpq-text-secondary); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.period-option.active { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); border-color: var(--cpq-accent-primary); }
.period-dot { width: 7px; height: 7px; border-radius: 50%; border: 1.5px solid var(--cpq-text-muted); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.period-dot.active { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); box-shadow: 0 0 6px var(--cpq-overlay-a40); }
.period-option.custom-entry { padding-right: 9px; }
.custom-text { max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.custom-caret { font-size: 9px; opacity: .55; margin-left: 1px; }

.charts-body { flex: 1 1 0; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
.charts-body::-webkit-scrollbar { width: 6px; }
.charts-body::-webkit-scrollbar-thumb { background: var(--cpq-overlay-a20); border-radius: 3px; }
.charts-body::-webkit-scrollbar-track { background: transparent; }
.charts-loading { display: flex; align-items: center; justify-content: center; height: 260px; font-size: 13px; color: var(--cpq-text-muted); }

/* 右栏：筛选 + 表格 */
.table-side { flex: 1 1 1px; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.filter-row { position: sticky; top: 0; z-index: 3; display: flex; align-items: center; gap: 8px; padding: 10px 14px; flex-wrap: wrap; flex: none; background: var(--cpq-glass-3-bg); backdrop-filter: blur(var(--cpq-glass-blur-3)); -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)); border-bottom: 1px solid var(--cpq-overlay-w3); }
.reset-btn {
  padding: 4px 12px; border: 1px solid var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-secondary);
  border-radius: 6px; cursor: pointer; font-size: 12px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.reset-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.filter-count { font-size: 12px; color: var(--cpq-text-muted); margin-left: auto; }

.dark-select :deep(.ant-select-selector) { background: var(--cpq-overlay-w5) !important; border-color: var(--cpq-overlay-w10) !important; color: var(--cpq-text-primary) !important; border-radius: 6px !important; }
.dark-select :deep(.ant-select-selection-item) { color: var(--cpq-text-primary) !important; }
.dark-select :deep(.ant-select-arrow) { color: var(--cpq-text-muted) !important; }
.dark-input { background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-overlay-w10); color: var(--cpq-text-primary); padding: 6px 12px; border-radius: 6px; font-size: 13px; outline: none; transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.dark-input:focus { border-color: var(--cpq-accent-primary); box-shadow: 0 0 0 2px var(--cpq-overlay-a10); }
.dark-input::placeholder { color: var(--cpq-text-muted); }

.drill-hint { display: flex; align-items: center; gap: 8px; padding: 7px 14px; background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a15); border-radius: 8px; font-size: 12px; color: var(--cpq-accent-primary); flex: none; }
.drill-hint button { background: transparent; border: none; color: var(--cpq-text-muted); cursor: pointer; font-size: 12px; margin-left: auto; }
.drill-hint button:hover { color: var(--cpq-text-primary); }

.table-card { border-radius: var(--cpq-radius-lg); overflow: auto; flex: 1 1 0; min-height: 0; }

.cell-customer { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name-row { display: flex; align-items: center; gap: 10px; min-width: 0; flex-wrap: wrap; }
.opp-name { color: var(--cpq-text-primary); font-size: 13.5px; font-weight: 500; cursor: pointer; text-decoration: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.opp-name:hover { color: var(--cpq-accent-primary); }
.opp-meta { font-size: 11px; color: var(--cpq-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 380px; }
.opp-status-pick { cursor: pointer; user-select: none; margin-right: 0 !important; transition: filter var(--cpq-dur-1) var(--cpq-ease-smooth); }
.opp-status-pick:hover { filter: brightness(1.06); }
.opp-caret { font-size: 9px; margin-left: 3px; opacity: 0.7; }
.cell-plat { font-size: 12.5px; color: var(--cpq-text-primary); white-space: nowrap; }
.cell-num { display: inline-flex; align-items: baseline; gap: 3px; }
.cell-num b { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); font-variant-numeric: tabular-nums; }
.cell-num i { font-style: normal; font-size: 11px; color: var(--cpq-text-muted); }
.cell-dt { display: flex; flex-direction: column; gap: 1px; }
.dt-main { font-size: 12px; color: var(--cpq-text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.dt-rel { font-size: 10.5px; color: var(--cpq-text-muted); white-space: nowrap; }
.row-more {
  display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
  border: none; background: transparent; color: var(--cpq-text-muted); border-radius: 6px; cursor: pointer; font-size: 14px;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.row-more:hover { background: var(--cpq-overlay-w8); color: var(--cpq-text-primary); }

/* 悬浮批量条 */
.batch-float {
  position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 1000;
  display: flex; align-items: center; gap: 12px; padding: 10px 18px; border-radius: 999px;
  box-shadow: var(--cpq-shadow-lg, 0 8px 24px rgba(0,0,0,0.18));
}
.batch-count { font-size: 13px; color: var(--cpq-text-secondary); }
.batch-count b { color: var(--cpq-accent-primary); }
.batch-btn {
  padding: 5px 14px; border: 1px solid var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-secondary);
  border-radius: 999px; cursor: pointer; font-size: 12.5px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.batch-btn:hover { color: var(--cpq-text-primary); border-color: var(--cpq-text-secondary); }
.batch-btn.danger { color: var(--cpq-accent-danger); border-color: var(--cpq-overlay-danger30, rgba(255,107,107,0.35)); }
.batch-btn.danger:hover:not(:disabled) { border-color: var(--cpq-accent-danger); }
.batch-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.batch-fade-enter-active, .batch-fade-leave-active { transition: opacity var(--cpq-dur-2) var(--cpq-ease-smooth), transform var(--cpq-dur-2) var(--cpq-ease-smooth); }
.batch-fade-enter-from, .batch-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(12px); }

/* Table dark overrides */
.opp-page :deep(.ant-table-wrapper .ant-table) { background: transparent; color: var(--cpq-text-primary); }
.opp-page :deep(.ant-table-thead > tr > th) { background: var(--cpq-overlay-w4) !important; color: var(--cpq-text-secondary) !important; font-size: 12px; font-weight: 500; border-bottom: 1px solid var(--cpq-overlay-w6) !important; white-space: nowrap; }
.opp-page :deep(.ant-table-tbody > tr > td) { border-bottom: 1px solid var(--cpq-overlay-w4) !important; color: var(--cpq-text-primary); }
.opp-page :deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-a5) !important; }
.opp-page :deep(.ant-table-cell) { padding: 9px 12px; }
.opp-page :deep(.ant-table-thead > tr > th.ant-table-column-sort) { background: var(--cpq-overlay-w6) !important; }
.opp-page :deep(.ant-pagination) { padding: 12px 16px; border-top: 1px solid var(--cpq-overlay-w4); }
.opp-page :deep(.ant-pagination-item), .opp-page :deep(.ant-pagination-prev), .opp-page :deep(.ant-pagination-next) { background: transparent !important; border-color: var(--cpq-overlay-w10) !important; }
.opp-page :deep(.ant-pagination-item a), .opp-page :deep(.ant-pagination-item-link) { color: var(--cpq-text-secondary) !important; background: transparent !important; border: none !important; }
.opp-page :deep(.ant-pagination-item-active) { border-color: var(--cpq-accent-primary) !important; }
.opp-page :deep(.ant-pagination-item-active a) { color: var(--cpq-accent-primary) !important; }

@media (max-width: 768px) {
  .opp-page { height: auto; min-height: calc(100vh - 56px); overflow: visible; padding: 10px 12px 96px; }
  .page-head { flex-wrap: wrap; gap: 10px; padding: 10px 14px; border-radius: 8px; }
  .head-icons { margin-left: 0; }
  .main-split { flex-direction: column; }
  .kpi-strip { grid-template-columns: repeat(2, 1fr); }
  .charts-panel { flex: none; min-width: 0; max-width: none; overflow: visible; padding: 10px; }
  .charts-body { flex: none; overflow: visible; }
  .filter-row .search-input { flex-basis: 100%; max-width: none; order: -1; }
  .filter-count { margin-left: 0; width: 100%; }
  .opp-meta { max-width: 200px; }
}
</style>
