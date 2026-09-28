<template>
  <div class="opp-page">
    <!-- 顶栏：标题 + 周期切换 + 图标按钮 + 新建 -->
    <header class="page-head">
      <div class="page-title">
        <h1>商机驾驶舱</h1>
        <span class="page-sub">数据区间：{{ summary.period_label || '—' }}</span>
      </div>
      <div class="period-toggle">
        <label v-for="p in periods" :key="p.value" class="period-option" :class="{ active: period === p.value && !customRange }" @click="setPeriod(p.value)">
          <span class="period-dot" :class="{ active: period === p.value && !customRange }"></span>
          {{ p.label }}
        </label>
        <a-popover v-model:open="customOpen" trigger="click" placement="bottomLeft" overlay-class-name="period-custom-pop">
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
      <div class="head-icons">
        <a-tooltip v-if="!isMobile" title="图表栏">
          <button class="icon-btn" :class="{ active: chartsPanelOpen }" @click="chartsPanelOpen = !chartsPanelOpen"><BarChartOutlined /></button>
        </a-tooltip>
        <a-tooltip title="AI 线索">
          <button class="icon-btn" @click="router.push('/ai-leads')"><RobotOutlined /></button>
        </a-tooltip>
        <a-tooltip title="导出 Excel">
          <button class="icon-btn" :disabled="exporting" @click="exportList"><ExportOutlined /></button>
        </a-tooltip>
        <a-tooltip v-if="!isMobile" title="回收站">
          <button class="icon-btn" @click="goToRecycleBin"><RestOutlined /></button>
        </a-tooltip>
        <button class="create-btn" @click="showCreateModal = true"><PlusOutlined /> 新建商机</button>
      </div>
    </header>

    <!-- 手机端 KPI 条：单独渲染在图表区上方（桌面 KPI 仍在右栏，数据同源 summary.kpi） -->
    <section v-if="isMobile" class="kpi-strip kpi-strip-mobile">
      <div class="kpi-card glass-light" v-for="k in kpiItems" :key="k.key">
        <span class="kpi-label">{{ k.label }}</span>
        <span class="kpi-num">{{ k.value }}</span>
      </div>
    </section>

    <div class="main-split">
      <!-- 左栏：图表卡单列上下滑（周期切换已上移页头，桌面/移动共用） -->
      <aside v-show="chartsPanelOpen" class="charts-panel">
        <div v-if="partApplied.length" class="part-time-note">
          <b>配件筛选生效</b>：报价时间 · <b>{{ partTimeLabel }}</b>（按命中报价的创建时间过滤，点上方周期可限定）。
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
            @open-list-drawer="openListDrawer"
          />
          <div v-else class="charts-loading">图表加载中…</div>
        </div>
      </aside>

      <!-- 右栏：筛选 + 宽表 -->
      <section class="table-side">
        <div class="kpi-strip">
          <div class="kpi-card glass-light" v-for="k in kpiItems" :key="k.key">
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
            <a-select v-model:value="filters.status" style="width: 104px" @change="onFilterChange">
              <a-select-option value="all">全部状态</a-select-option>
              <a-select-option value="pending">进行中</a-select-option>
              <a-select-option value="won">已中标</a-select-option>
              <a-select-option value="lost">已丢标</a-select-option>
              <a-select-option value="expired">已过期</a-select-option>
            </a-select>
            <a-select v-model:value="filters.platform" mode="multiple" placeholder="平台" :maxTagCount="1" style="min-width: 128px" @change="onFilterChange">
              <a-select-option v-for="s in seriesStore.items" :key="s.value" :value="s.value">{{ s.label }}</a-select-option>
              <a-select-option value="其他">其他</a-select-option>
            </a-select>
            <a-select v-model:value="filters.chassis" mode="multiple" placeholder="形态" :maxTagCount="1" style="min-width: 112px" @change="onFilterChange">
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
              style="min-width: 120px"
              placeholder="业务"
              allow-clear
              show-search
              option-filter-prop="label"
              :options="salesOptions"
              @change="onFilterChange"
            />
            <OpportunityPartFilter :applied="partAppliedRows" @apply="onPartApply" @clear="onPartClear" />
            <button class="reset-btn" @click="resetFilters">重置</button>
            <span class="filter-count">共 {{ tableTotal }} 条</span>
          </div>

          <div v-if="partApplied.length" class="part-chip-row">
            <span v-for="(row, i) in partApplied" :key="i" class="part-chip">
              <b>{{ row.category || '配件' }}</b>{{ row.keywords.join(' / ') }}<template v-if="row.qtyMin"> ≥{{ row.qtyMin }}</template>
              <i @click="removePartRow(i)">✕</i>
            </span>
            <span class="part-chip-tip">报价时间 · {{ partTimeLabel }}</span>
            <button class="part-chip-clear" @click="onPartClear">清空</button>
          </div>

          <div class="table-scroll">
            <OpportunityTable
              :rows="tableData"
              :loading="tableLoading"
              :pagination="tablePagination"
              :status-editable="canEditResult"
              :show-part-hits="partApplied.length > 0"
              selectable
              @change="onTableChange"
              @result-change="changeResult"
              @row-menu="onRowMenu"
              @batch-trashed="onBatchTrashed"
            />
          </div>
        </div>
      </section>
    </div>

    <!-- 重命名 modal -->
    <a-modal v-model:open="renameOpen" title="重命名商机" ok-text="保存" cancel-text="取消" :confirm-loading="renaming" @ok="confirmRename">
      <a-input v-model:value="renameValue" placeholder="客户名称" :maxlength="60" @pressEnter="confirmRename" />
    </a-modal>

    <CreateOpportunityModal v-model:open="showCreateModal" />

    <!-- 手机端商机列表抽屉：右侧滑出、卡式行、粘性筛选、分页吸底（桌面无此入口） -->
    <a-drawer
      v-model:open="listDrawerOpen"
      placement="right"
      width="92%"
      root-class-name="opp-list-drawer"
      :closable="false"
      :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    >
      <div class="ld-head">
        <h3>商机列表</h3>
        <span class="ld-count">{{ tableTotal }} 条</span>
        <span class="ld-sp"></span>
        <button class="ld-close" @click="listDrawerOpen = false">✕</button>
      </div>
      <div class="ld-filters">
        <input v-model="filters.search" class="ld-search" placeholder="搜索客户 / 业务 / 商机号" @input="debounceFilter" />
        <a-select v-model:value="filters.status" class="ld-select" @change="onFilterChange">
          <a-select-option value="all">全部状态</a-select-option>
          <a-select-option value="pending">进行中</a-select-option>
          <a-select-option value="won">已中标</a-select-option>
          <a-select-option value="lost">已丢标</a-select-option>
          <a-select-option value="expired">已过期</a-select-option>
        </a-select>
        <a-select v-model:value="filters.platform" mode="multiple" placeholder="平台" :maxTagCount="1" class="ld-select" @change="onFilterChange">
          <a-select-option v-for="s in seriesStore.items" :key="s.value" :value="s.value">{{ s.label }}</a-select-option>
          <a-select-option value="其他">其他</a-select-option>
        </a-select>
        <a-select v-model:value="filters.chassis" mode="multiple" placeholder="形态" :maxTagCount="1" class="ld-select" @change="onFilterChange">
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
          class="ld-select ld-select-sales"
          placeholder="业务"
          allow-clear
          show-search
          option-filter-prop="label"
          :options="salesOptions"
          @change="onFilterChange"
        />
        <OpportunityPartFilter :applied="partAppliedRows" @apply="onPartApply" @clear="onPartClear" />
        <button class="ld-reset" @click="resetFilters">重置</button>
      </div>
      <div v-if="partApplied.length" class="part-chip-row ld-part-chips">
        <span v-for="(row, i) in partApplied" :key="i" class="part-chip">
          <b>{{ row.category || '配件' }}</b>{{ row.keywords.join(' / ') }}<template v-if="row.qtyMin"> ≥{{ row.qtyMin }}</template>
          <i @click="removePartRow(i)">✕</i>
        </span>
        <button class="part-chip-clear" @click="onPartClear">清空</button>
      </div>
      <div v-if="drill.active" class="drill-hint ld-drill">
        <span>已筛选：{{ drill.label }}</span>
        <button @click="drillOff">清除 ✕</button>
      </div>
      <div class="ld-table">
        <OpportunityTable
          :rows="tableData"
          :loading="tableLoading"
          :pagination="tablePagination"
          :status-editable="canEditResult"
          :show-part-hits="partApplied.length > 0"
          selectable
          @change="onTableChange"
          @result-change="changeResult"
          @row-menu="onRowMenu"
          @batch-trashed="onBatchTrashed"
        />
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onActivated, watch, nextTick, defineAsyncComponent } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { BarChartOutlined, RobotOutlined, RestOutlined, PlusOutlined, ExportOutlined } from '@ant-design/icons-vue'
import axios from 'axios'
import ExcelJS from 'exceljs'
import CreateOpportunityModal from '@/components/opportunity/CreateOpportunityModal.vue'
import OpportunityTable from '@/components/opportunity/OpportunityTable.vue'
import OpportunityPartFilter, { type PartFilterRow } from '@/components/opportunity/OpportunityPartFilter.vue'
import { resultLabel } from '@/constants/opportunityResult'
import { downloadBlob } from '@/utils/download'
import dayjs from 'dayjs'
import { useSeriesStore } from '@/stores/series'
import { useAuthStore } from '@/store/auth'

const OpportunityCharts = defineAsyncComponent(() => import('@/components/opportunity/OpportunityCharts.vue'))

defineOptions({ name: 'OpportunityList' })

const router = useRouter()
const auth = useAuthStore()
const canViewAll = computed(() => auth.can('page.opportunities_all'))
// 商机状态（进行中/已中标…）可改性：后端 update_meta 对 result 键同权限门控
const canEditResult = computed(() => auth.can('action.opportunity.result'))
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
// 用户是否动过周期控件：没动过时配件筛选不叠加默认「本周」（默认不限报价时间）
const periodTouched = ref(false)
// 配件筛选当前生效的报价时间范围文案
const partTimeLabel = computed(() => {
  if (customRange.value) return customRange.value.shortLabel
  if (!periodTouched.value) return '不限'
  return periods.find((p) => p.value === period.value)?.label || period.value
})

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
  periodTouched.value = true
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
  periodTouched.value = false
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
// 配件筛选（按报价单明细）：应用态在父页面，桌面筛选行与手机抽屉共用
const partRows = ref<PartFilterRow[]>([])
const partApplied = computed(() => partRows.value.filter((r) => r.keywords.length > 0))
const partAppliedRows = computed<PartFilterRow[]>(() =>
  partApplied.value.map((r) => ({ category: r.category || '', keywords: [...r.keywords], qtyMin: r.qtyMin ?? null }))
)
function onPartApply(rows: PartFilterRow[]) {
  partRows.value = rows
  tablePage.value = 1
  loadSummary()
  loadTable()
}
function onPartClear() {
  if (!partRows.value.length) return
  partRows.value = []
  tablePage.value = 1
  loadSummary()
  loadTable()
}
function removePartRow(i: number) {
  partRows.value.splice(i, 1)
  tablePage.value = 1
  loadSummary()
  loadTable()
}
const salesOptions = ref<{ value: string; label: string }[]>([])
const sortBy = ref('updated_at')
const sortOrder = ref('desc')
let filterTimer: ReturnType<typeof setTimeout> | null = null
const drill = ref({ active: false, platform: '', chassis: '', label: '' })
const isMobile = ref(false)
function syncMobile() { isMobile.value = window.matchMedia('(max-width: 768px)').matches }
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null

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
  partRows.value = []
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
  // 手机端表格隐藏（列表走抽屉），容器高度恒为 0，跳过自适应保持固定每页 10 条
  if (isMobile.value) return tablePageSize.value
  const box = document.querySelector('.table-scroll') as HTMLElement | null
  if (!box || !box.clientHeight) return tablePageSize.value
  const usable = box.clientHeight - ADAPTIVE_RESERVED_H
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
function goToDetail(id: string) { router.push(`/opportunities/${id}`) }
function goToRecycleBin() { router.push('/recycle-bin') }
// 手机端商机列表抽屉：图表磁贴点击 → 右侧滑出（内联表格在手机端已隐藏，抽屉即唯一列表）
const listDrawerOpen = ref(false)
function openListDrawer() { listDrawerOpen.value = true }
// 离开本页（点行进详情等）时收起抽屉：抽屉是 KeepAlived 页面级状态，不收会盖住详情页；
// 此关闭是导航性的，不回写 LIST_STATE（保留 list_drawer=true 供返回时恢复，见 onActivated）
const route = useRoute()
let _drawerNavClose = false
watch(() => route.path, (p) => {
  if (p !== '/opportunities' && listDrawerOpen.value) {
    _drawerNavClose = true
    listDrawerOpen.value = false
  }
})
watch(listDrawerOpen, () => {
  if (_drawerNavClose) { _drawerNavClose = false; return }
  syncListState()
})

// 批量回收站在 OpportunityTable 组件内完成，这里只负责刷新
function onBatchTrashed() { reloadAll({ resetPage: true }) }

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

// 列表查询参数唯一出处：表格分页加载与 Excel 导出共用，保证导出口径 = 页面所见（筛选与权限范围都在后端 list 接口收口）
function buildListParams(): Record<string, any> {
  const params: any = {}
  // 周期时间窗：图表下钻或「用户动过周期」的配件筛选才传给列表（配件筛选下后端改落报价创建时间）；
  // 周期没动过时不叠加默认「本周」，配件筛选默认不限报价时间
  if (drill.value.active || (partApplied.value.length && periodTouched.value)) {
    if (customRange.value) {
      params.start = customRange.value.start
      params.end = customRange.value.end
    } else {
      params.period = period.value
    }
  } else if (partApplied.value.length) {
    params.period = 'all'
  }
  if (filters.value.search) params.search = filters.value.search
  if (partApplied.value.length) params.part_filters = JSON.stringify(partAppliedRows.value)
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
  return params
}

async function loadTable() {
  tableLoading.value = true
  try {
    const params = { ...buildListParams(), page: tablePage.value, page_size: tablePageSize.value }
    const res = await axios.get('/api/opportunities/list', { params })
    tableData.value = res.data.items || []
    tableTotal.value = res.data.total || 0
  } finally {
    tableLoading.value = false
  }
  syncListState()
}

// ── 一键导出 Excel：拉当前筛选全量 → exceljs 前端生成 → 浏览器下载（服务端不落盘）──
const exporting = ref(false)
async function exportList() {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await axios.get('/api/opportunities/list', {
      params: { ...buildListParams(), page: 1, page_size: Math.max(tableTotal.value, 1) },
    })
    const rows: any[] = res.data.items || []
    if (!rows.length) { message.warning('当前筛选下没有可导出的商机'); return }
    await writeOppsXlsx(rows)
    message.success(`已导出 ${rows.length} 条商机`)
  } catch {
    message.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

async function writeOppsXlsx(rows: any[]) {
  const wb = new ExcelJS.Workbook()
  const ws = wb.addWorksheet('商机列表')
  const withHits = partApplied.value.length > 0
  ws.columns = [
    { header: '商机号', key: 'id', width: 20 },
    { header: '客户名称', key: 'customer', width: 26 },
    { header: '状态', key: 'status', width: 10 },
    { header: '业务', key: 'sales', width: 10 },
    { header: '平台', key: 'platform', width: 10 },
    { header: '形态', key: 'chassis', width: 9 },
    { header: '数量', key: 'qty', width: 8 },
    { header: '配置数', key: 'configs', width: 8 },
    { header: '报价份数', key: 'quotes', width: 10 },
    { header: '行业', key: 'industry', width: 14 },
    { header: '订单类型', key: 'orderType', width: 12 },
    { header: '创建时间', key: 'created', width: 20 },
    { header: '更新时间', key: 'updated', width: 20 },
    ...(withHits ? [{ header: '命中配件', key: 'hits', width: 46 }] : []),
  ]
  ws.getRow(1).font = { bold: true }
  ws.views = [{ state: 'frozen', ySplit: 1 }]
  for (const r of rows) {
    const row: Record<string, any> = {
      id: r.opportunity_id,
      customer: r.customer_name,
      status: resultLabel(r.result),
      sales: r.sales_person,
      platform: r.platform_type,
      chassis: r.chassis_form,
      qty: Number(r.purchase_qty) || 0,
      configs: Number(r.config_count) || 0,
      quotes: Number(r.quotation_count) || 0,
      industry: r.industry || '',
      orderType: r.order_type || '',
      created: r.created_at,
      updated: r.updated_at,
    }
    if (withHits) {
      row.hits = (r.part_hits || [])
        .map((h: any) => `${h.date}${h.cfg ? ' · ' + h.cfg : ''}：${(h.parts || []).map((p: any) => `${p.name}×${p.qty}`).join('、')}`)
        .join('\n')
    }
    ws.addRow(row)
  }
  const buf = await wb.xlsx.writeBuffer()
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  downloadBlob(blob, `商机列表_${dayjs().format('YYYYMMDD')}.xlsx`)
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
  if (Array.isArray(s.part_rows)) {
    partRows.value = (s.part_rows as any[])
      .filter((r) => r && Array.isArray(r.keywords) && r.keywords.length)
      .map((r) => ({ category: String(r.category || ''), keywords: r.keywords.map(String), qtyMin: Number(r.qtyMin) || null }))
  }
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
  // 手机端抽屉开合态随状态一起恢复（详情页返回后仍在列表抽屉里）
  if (s.list_drawer && isMobile.value) listDrawerOpen.value = true
}

function syncListState() {
  try {
    sessionStorage.setItem(LIST_STATE_KEY, JSON.stringify({
      page: tablePage.value,
      status: filters.value.status,
      platform: filters.value.platform,
      chassis: filters.value.chassis,
      search: filters.value.search,
      part_rows: partAppliedRows.value,
      drill_platform: drill.value.platform,
      drill_chassis: drill.value.chassis,
      sort: sortBy.value,
      list_drawer: listDrawerOpen.value,
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
    else if (partApplied.value.length && !periodTouched.value) { params.period = 'all' }
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
    if (partApplied.value.length) params.part_filters = JSON.stringify(partAppliedRows.value)
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
function setPeriod(p: string) { customRange.value = null; period.value = p; periodTouched.value = true }

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
  // 从详情页返回：离开时抽屉若开着则恢复（KeepAlive 重激活不走 onMounted 的 restoreListState）
  if (isMobile.value) {
    try {
      const s = JSON.parse(sessionStorage.getItem(LIST_STATE_KEY) || '')
      if (s && s.list_drawer) listDrawerOpen.value = true
    } catch { /* sessionStorage 不可用时静默降级 */ }
  }
})
watch([() => period.value, () => customRange.value], () => reloadAll({ resetPage: true }))
</script>

<style scoped>
.opp-page { display: flex; flex-direction: column; gap: 12px; padding: 14px 20px 16px; height: calc(100vh - var(--cpq-header-clearance, 56px)); overflow: hidden; }

/* 顶栏 */
.page-head { display: flex; align-items: center; gap: 14px; padding: 2px 4px 0; flex: none; }
.page-title { display: flex; flex-direction: column; gap: 1px; flex: none; }
.page-title h1 { margin: 0; font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); letter-spacing: 1px; }
.page-sub { font-size: 12px; color: var(--cpq-text-muted); letter-spacing: 0.5px; }
.search-input { flex: 1 1 150px; min-width: 130px; max-width: 300px; height: 32px; }
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

/* 左栏：透明布局容器（分组不套玻璃，图表卡单层玻璃直坐画布）；宽度随视口比例自适应（约 1/3 屏，窄屏收窄宽屏封顶） */
.charts-panel { flex: 0 0 clamp(360px, 34vw, 660px); display: flex; flex-direction: column; gap: 12px; min-height: 0; }

.kpi-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; flex: none; }
.kpi-card { padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.kpi-label { font-size: 12px; color: var(--cpq-text-secondary); white-space: nowrap; }
.kpi-num { font-size: 28px; font-weight: 700; color: var(--cpq-text-primary); font-variant-numeric: tabular-nums lining-nums; line-height: 1.1; }

.period-toggle { display: flex; gap: 6px; flex-wrap: wrap; }
.part-time-note {
  font-size: 11px; line-height: 1.6; color: var(--cpq-text-secondary);
  background: rgba(22, 119, 255, 0.08); border: 1px dashed rgba(22, 119, 255, 0.45);
  border-radius: 8px; padding: 7px 10px;
}
.part-time-note b { color: var(--cpq-accent-primary); }
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
.table-side { flex: 1 1 1px; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.filter-row { display: flex; align-items: center; gap: 10px; padding: 10px 16px; flex-wrap: wrap; flex: none; border-bottom: 1px solid var(--cpq-overlay-w3); }
.reset-btn {
  height: 32px; padding: 0 14px; display: inline-flex; align-items: center;
  border: 1px solid var(--cpq-glass-border); background: transparent; color: var(--cpq-text-secondary);
  border-radius: var(--cpq-radius-sm); cursor: pointer; font-size: 12px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.reset-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.filter-count { font-size: 12px; color: var(--cpq-text-muted); margin-left: auto; }

.dark-input { background: var(--cpq-glass-2-bg); border: 1px solid var(--cpq-glass-border); color: var(--cpq-text-primary); padding: 0 12px; border-radius: var(--cpq-radius-sm); font-size: 13px; outline: none; transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.dark-input:focus { border-color: var(--cpq-accent-primary); box-shadow: 0 0 0 2px var(--cpq-overlay-a15); }
.dark-input::placeholder { color: var(--cpq-text-muted); }

.drill-hint { display: flex; align-items: center; gap: 8px; padding: 7px 14px; background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a15); border-radius: 8px; font-size: 12px; color: var(--cpq-accent-primary); flex: none; }
.drill-hint button { background: transparent; border: none; color: var(--cpq-text-muted); cursor: pointer; font-size: 12px; margin-left: auto; }
.drill-hint button:hover { color: var(--cpq-text-primary); }

/* 配件筛选 chips 行：条件回显为可删胶囊（桌面筛选行下 / 手机抽屉内共用） */
.part-chip-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: none;
  padding: 8px 16px; border-bottom: 1px solid var(--cpq-overlay-w3);
}
.part-chip {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--cpq-text-primary);
  background: rgba(22, 119, 255, 0.08); border: 1px solid rgba(22, 119, 255, 0.45);
  border-radius: 999px; padding: 2px 6px 2px 10px; max-width: 100%;
}
.part-chip b { color: var(--cpq-accent-primary); font-weight: 600; }
.part-chip i { font-style: normal; font-size: 10px; color: var(--cpq-text-muted); width: 16px; height: 16px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.part-chip i:hover { background: rgba(22, 119, 255, 0.15); color: var(--cpq-accent-primary); }
.part-chip-tip { font-size: 11px; color: var(--cpq-text-muted); }
.part-chip-clear { background: transparent; border: none; color: var(--cpq-text-muted); cursor: pointer; font-size: 12px; }
.part-chip-clear:hover { color: var(--cpq-accent-danger); }

.table-card { border-radius: var(--cpq-radius-lg); display: flex; flex-direction: column; overflow: hidden; flex: 1 1 0; min-height: 0; }
.table-scroll { flex: 1 1 0; min-height: 0; overflow: auto; }

/* Table dark overrides */
/* 表格视觉规范（主题感知 token，勿用白色叠加写死——浅色主题下 w4/w6/w8 不可辨） */
.opp-page :deep(.ant-table-wrapper .ant-table) { background: transparent; color: var(--cpq-text-primary); }
.opp-page :deep(.ant-table-thead > tr > th) { background: var(--cpq-bg-secondary) !important; color: var(--cpq-text-secondary) !important; font-size: 12px; font-weight: 500; border-bottom: 1px solid var(--cpq-border-secondary) !important; white-space: nowrap; }
.opp-page :deep(.ant-table-tbody > tr > td) { border-bottom: 1px solid var(--cpq-border-secondary) !important; color: var(--cpq-text-primary); }
.opp-page :deep(.ant-table-tbody > tr:last-child > td) { border-bottom: none !important; }
.opp-page :deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-a8) !important; }
.opp-page :deep(.ant-table-cell) { padding: 9px 12px; }
.opp-page :deep(.ant-table-thead > tr > th.ant-table-column-sort) { background: var(--cpq-bg-elevated) !important; }
.opp-page :deep(.ant-pagination) { padding: 12px 16px; border-top: 1px solid var(--cpq-overlay-w4); }
.opp-page :deep(.ant-pagination-item), .opp-page :deep(.ant-pagination-prev), .opp-page :deep(.ant-pagination-next) { background: transparent !important; border-color: var(--cpq-overlay-w10) !important; }
.opp-page :deep(.ant-pagination-item a), .opp-page :deep(.ant-pagination-item-link) { color: var(--cpq-text-secondary) !important; background: transparent !important; border: none !important; }
.opp-page :deep(.ant-pagination-item-active) { border-color: var(--cpq-accent-primary) !important; }
.opp-page :deep(.ant-pagination-item-active a) { color: var(--cpq-accent-primary) !important; }

@media (max-width: 768px) {
  .opp-page { height: auto; min-height: calc(100vh - var(--cpq-header-clearance, 56px)); overflow: visible; padding: 10px 12px 16px; }
  .page-head { flex-wrap: wrap; gap: 10px; padding: 10px 14px; border-radius: 8px; }
  .head-icons { margin-left: 0; }
  .main-split { flex-direction: column; }
  .kpi-strip { grid-template-columns: repeat(2, 1fr); }
  .kpi-strip-mobile .kpi-num { font-size: 22px; }
  /* 手机端纯驾驶舱：KPI 移到页首（上方独立渲染），筛选+宽表整体让位给「商机列表」抽屉 */
  .table-side { display: none; }
  .charts-panel { flex: none; min-width: 0; max-width: none; }
  .charts-body { flex: none; overflow: visible; }
  .opp-meta { max-width: 200px; }
}

/* ── 手机端商机列表抽屉内部（slot 内容带本组件 scope，可正常命中） ── */
.ld-head { display: flex; align-items: center; gap: 8px; padding: 14px 16px 10px; flex: none; }
.ld-head h3 { margin: 0; font-size: 16px; font-weight: 700; color: var(--cpq-text-primary); }
.ld-count { font-size: 11px; color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); padding: 2px 9px; border-radius: 999px; font-weight: 700; white-space: nowrap; }
.ld-sp { flex: 1; }
.ld-close { width: 30px; height: 30px; border-radius: 10px; border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary); cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }
.ld-filters { display: flex; align-items: center; gap: 6px; padding: 0 14px 10px; border-bottom: 1px solid var(--cpq-overlay-w6); flex-wrap: wrap; flex: none; }
.ld-part-chips { padding: 0 14px 8px; }
.ld-search { flex: 1 1 150px; min-width: 130px; height: 30px; background: var(--cpq-glass-2-bg); border: 1px solid var(--cpq-glass-border); color: var(--cpq-text-primary); padding: 0 10px; border-radius: var(--cpq-radius-sm); font-size: 12.5px; outline: none; }
.ld-search:focus { border-color: var(--cpq-accent-primary); }
.ld-search::placeholder { color: var(--cpq-text-muted); }
.ld-select { flex: none; }
.ld-select.ant-select-single { width: 96px; }
.ld-select.ant-select-multiple { min-width: 104px; max-width: 140px; }
.ld-select-sales { min-width: 110px; max-width: 150px; }
.ld-reset { height: 30px; padding: 0 12px; border: 1px solid var(--cpq-glass-border); background: transparent; color: var(--cpq-text-secondary); border-radius: var(--cpq-radius-sm); font-size: 12px; cursor: pointer; flex: none; }
.ld-drill { margin: 8px 14px 0; flex: none; }
/* 表格容器：与桌面同一张 OpportunityTable（排序/状态内联改/批量回收站全量可用），窄容器内横向滚动 */
.ld-table { flex: 1 1 0; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 0 2px 6px; }
</style>

<style>
/* 商机列表抽屉外壳：a-drawer portal 到 body，scoped 够不到，走全局（玻璃化对齐全站） */
.opp-list-drawer .ant-drawer-content {
  background: var(--cpq-glass-3-bg);
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  backdrop-filter: blur(var(--cpq-glass-blur-3)) saturate(1.35);
  border-radius: 18px 0 0 18px;
  overflow: hidden;
}
.opp-list-drawer .ant-drawer-header { display: none; }
.opp-list-drawer .ant-select-selector { background: var(--cpq-glass-2-bg) !important; border: 1px solid var(--cpq-glass-border) !important; }

/* 抽屉内 OpportunityTable 的视觉规范覆盖：桌面那套走 .opp-page :deep() 命不中 portal，这里同口径补一份（主题感知 token） */
.opp-list-drawer .ant-table { background: transparent; color: var(--cpq-text-primary); }
.opp-list-drawer .ant-table-thead > tr > th { background: var(--cpq-bg-secondary) !important; color: var(--cpq-text-secondary) !important; font-size: 12px; font-weight: 500; border-bottom: 1px solid var(--cpq-border-secondary) !important; white-space: nowrap; }
.opp-list-drawer .ant-table-tbody > tr > td { border-bottom: 1px solid var(--cpq-border-secondary) !important; color: var(--cpq-text-primary); }
.opp-list-drawer .ant-table-tbody > tr:last-child > td { border-bottom: none !important; }
.opp-list-drawer .ant-table-tbody > tr:hover > td { background: var(--cpq-overlay-a8) !important; }
.opp-list-drawer .ant-table-cell { padding: 9px 12px; }
.opp-list-drawer .ant-table-thead > tr > th.ant-table-column-sort { background: var(--cpq-bg-elevated) !important; }
.opp-list-drawer .ant-pagination { padding: 12px 16px; border-top: 1px solid var(--cpq-border-secondary); }
.opp-list-drawer .ant-pagination-item, .opp-list-drawer .ant-pagination-prev, .opp-list-drawer .ant-pagination-next { background: transparent !important; border-color: var(--cpq-overlay-w10) !important; }
.opp-list-drawer .ant-pagination-item a, .opp-list-drawer .ant-pagination-item-link { color: var(--cpq-text-secondary) !important; background: transparent !important; border: none !important; }
.opp-list-drawer .ant-pagination-item-active { border-color: var(--cpq-accent-primary) !important; }
.opp-list-drawer .ant-pagination-item-active a { color: var(--cpq-accent-primary) !important; }
</style>
