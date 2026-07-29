<template>
  <div class="cockpit">
    <div class="cockpit-scan" aria-hidden="true"></div>

    <!-- 顶栏：标题 + LIVE + 周期 -->
    <header class="cockpit-header glass-strong">
      <div class="cockpit-brand">
        <h1 class="cockpit-title">商机驾驶舱</h1>
        <span class="cockpit-sub">数据区间：{{ summary.period_label || '—' }}</span>
      </div>
      <div class="cockpit-live">
        <span class="live-dot"></span>
        <span class="live-label">LIVE</span>
        <span class="live-clock">{{ clock }}</span>
      </div>
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
    </header>

    <div class="cockpit-body">
      <main class="main-area">
    <!-- KPI 精简行 -->
    <section class="kpi-deck">
      <div class="kpi-mini glass" v-for="k in kpiItems" :key="k.key">
        <span class="kpi-mini-label">{{ k.label }}</span>
        <span class="kpi-mini-val"><CountNumber :value="k.value" /></span>
      </div>
    </section>

    <!-- 业务排行 -->
    <section class="ai-deck">
      <div class="ai-card glass">
        <div class="ai-header">
          <div class="ai-title">业务排行</div>
          <span class="ai-period">{{ periodLabel }}</span>
        </div>
        <div class="rank-content" v-if="topSales.length">
          <div v-for="(s, idx) in topSales" :key="s.name" class="rank-row">
            <span class="rank-num" :class="{ 'rank-top': idx < 3 }">{{ idx + 1 }}</span>
            <span class="rank-name">{{ s.name }}</span>
            <div class="rank-bar-wrap">
              <div class="rank-bar" :style="{ width: s.rate * 100 + '%' }"></div>
            </div>
            <span class="rank-count">{{ s.count }} 个</span>
            <span class="rank-rate">{{ (s.rate * 100).toFixed(0) }}%</span>
          </div>
          <div class="rank-row rank-others" v-if="othersSales">
            <span class="rank-num">—</span>
            <span class="rank-name">其他 {{ othersSales.people }} 人</span>
            <span class="rank-count">{{ othersSales.count }} 个</span>
            <span class="rank-rate">{{ (othersSales.rate * 100).toFixed(0) }}%</span>
          </div>
        </div>
        <div class="ai-empty" v-else>暂无数据</div>
      </div>
    </section>

    <!-- 图表区（合并切换）-->
    <section class="chart-deck">
      <div class="chart-card glass">
        <div class="deck-header">
          <div class="deck-title"><span class="deck-num">01</span><span class="deck-line"></span>趋势分析</div>
          <a-segmented v-model:value="trendView" :options="trendOptions" size="small" />
        </div>
        <v-chart class="chart-inner" :option="currentTrendOpt" autoresize />
      </div>
      <div class="chart-card glass">
        <div class="deck-header">
          <div class="deck-title"><span class="deck-num">02</span><span class="deck-line"></span>结构分布</div>
          <a-segmented v-model:value="distView" :options="distOptions" size="small" />
        </div>
        <v-chart class="chart-inner chart-inner-pie" :option="currentDistOpt" autoresize @click="(p: any) => drillOn(distView === 'platform' ? 'platform' : 'chassis', p.name)" />
      </div>
    </section>
      </main>

      <aside class="list-panel" :class="{ collapsed: listCollapsed }">
        <button class="list-toggle" @click="listCollapsed = !listCollapsed">
          <span v-if="listCollapsed">商机列表 ◀</span>
          <span v-else>折叠 ▶</span>
        </button>
        <div class="list-panel-content" v-show="!listCollapsed">
          <div class="list-header">
            <div class="list-title">
              <h3>商机列表</h3>
          <span class="list-count">共 {{ tableTotal }} 条</span>
        </div>
        <div class="list-actions">
          <button class="action-btn" @click="goToRecycleBin"><span>🗑</span> 回收站</button>
          <button v-if="!selectMode" class="action-btn" @click="enterSelectMode"><span>☐</span> 批量选择</button>
          <button class="action-btn create-btn" @click="showCreateModal = true"><span>+</span> 新建商机</button>
        </div>
      </div>

      <div class="filter-toolbar glass">
        <a-select v-model:value="filters.status" size="small" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option value="all">全部</a-select-option>
          <a-select-option value="pending">进行中</a-select-option>
          <a-select-option value="won">已中标</a-select-option>
          <a-select-option value="lost">已丢标</a-select-option>
          <a-select-option value="archived">已归档</a-select-option>
        </a-select>
        <a-select v-model:value="filters.platform" size="small" mode="multiple" placeholder="平台类型" :maxTagCount="1" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option v-for="s in seriesStore.items" :key="s.value" :value="s.value">{{ s.label }}</a-select-option>
          <a-select-option value="其他">其他</a-select-option>
        </a-select>
        <a-select v-model:value="filters.chassis" size="small" mode="multiple" placeholder="机箱形态" :maxTagCount="1" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option value="2U">2U</a-select-option>
          <a-select-option value="4U">4U</a-select-option>
          <a-select-option value="5U">5U</a-select-option>
          <a-select-option value="4.5U">4.5U</a-select-option>
          <a-select-option value="8U">8U</a-select-option>
          <a-select-option value="工作站">工作站</a-select-option>
        </a-select>
        <a-select v-model:value="sortBy" size="small" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option value="created_at">创建时间 新→旧</a-select-option>
          <a-select-option value="updated_at">更新时间 新→旧</a-select-option>
        </a-select>
        <input v-model="filters.search" placeholder="搜索客户 / 销售人员 / 备注..." class="dark-input filter-input" @input="debounceFilter" />
        <button class="action-btn" @click="resetFilters">重置</button>
      </div>

      <div v-if="drill.active" class="drill-hint">
        <span>已筛选：{{ drill.label }}（点击图表可切换/清除）</span>
        <button @click="drillOff">清除筛选 ✕</button>
      </div>

      <div class="table-section glass">
        <div v-if="selectMode" class="batch-bar">
          <span class="batch-count">已选 {{ selectedRowKeys.length }} 项</span>
          <div class="batch-actions">
            <button class="action-btn danger-btn" :disabled="selectedRowKeys.length === 0 || batching" @click="handleBatchTrash">
              <span>🗑</span> 批量移至回收站
            </button>
            <button class="action-btn" @click="exitSelectMode">取消</button>
          </div>
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
          @change="onTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'info'">
              <div class="opp-cell">
                <div class="opp-cell-main">
                  <a class="opp-name" @click="goToDetail(record.opportunity_id)">{{ record.customer_name || '未命名客户' }}</a>
                  <a-tag :color="bizTagColor(record)" class="opp-status-tag">{{ bizStatusText(record) }}</a-tag>
                </div>
                <div class="opp-cell-meta">
                  <span class="meta" v-if="record.sales_person"><i>销售</i>{{ record.sales_person }}</span>
                  <span class="meta" v-if="record.platform_type"><i>平台</i>{{ record.platform_type }}</span>
                  <span class="meta" v-if="record.chassis_form"><i>机箱</i>{{ record.chassis_form }}</span>
                  <span class="meta" v-if="record.industry"><i>行业</i>{{ record.industry }}</span>
                  <span class="meta" v-if="record.purchase_qty"><i>数量</i>{{ record.purchase_qty }}</span>
                  <span class="meta"><i>配置</i>{{ record.config_count ?? 0 }}</span>
                  <span class="meta meta-date"><i>创建</i>{{ formatDate(record.created_at) }}</span>
                </div>
              </div>
            </template>
          </template>
        </a-table>
      </div>
        </div>
      </aside>
    </div>

    <!-- Create Modal -->
    <a-modal v-model:open="showCreateModal" title="新建商机" @ok="handleCreate" :confirmLoading="creating">
      <a-form layout="vertical">
        <a-form-item label="客户名称" required><a-input v-model:value="newProject.customer_name" placeholder="请输入客户名称" /></a-form-item>
        <a-form-item label="销售人员"><a-input v-model:value="newProject.sales_person" placeholder="销售人员（可选）" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import axios from 'axios'
import CountNumber from '@/components/common/CountNumber.vue'
import { useChartTheme } from '@/composables/useChartTheme'
import { PLAT_COLOR } from '@/constants/platform'
import dayjs from 'dayjs'
import { useSeriesStore } from '@/stores/series'

use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const router = useRouter()
const { chartColors } = useChartTheme()
// 全平台系列权威源（system_config.server_series）：筛选下拉读这里，不再硬编码 Orion/Polaris
const seriesStore = useSeriesStore()

const periods = [
  { label: '本周', value: 'week' },
  { label: '本月', value: 'month' },
  { label: '本年', value: 'year' },
]
const period = ref('week')

// 周期显示文本
const periodLabel = computed(() => {
  if (customRange.value) return customRange.value.shortLabel
  const p = periods.find(p => p.value === period.value)
  return p?.label || ''
})

// 图表切换状态
const trendView = ref<'opp' | 'platform'>('opp')
const distView = ref<'platform' | 'chassis'>('platform')
const trendOptions = [
  { value: 'opp', label: '商机趋势' },
  { value: 'platform', label: '平台趋势' },
]
const distOptions = [
  { value: 'platform', label: '平台' },
  { value: 'chassis', label: '机箱' },
]

// 业务排行（从 summary 数据读取）
interface SalesRank { name: string; count: number; rate: number }
const topSales = ref<SalesRank[]>([])
const othersSales = ref<{ count: number; rate: number; people: number } | null>(null)

function computeSalesRank() {
  const data = (summary.value as any).sales_rank
  if (!data || !data.top) {
    topSales.value = []
    othersSales.value = null
    return
  }

  const total = data.total || 1
  topSales.value = data.top.map((s: any) => ({
    name: s.name,
    count: s.count,
    rate: s.count / total,
  }))

  if (data.others && data.others.count > 0) {
    othersSales.value = {
      count: data.others.count,
      rate: data.others.count / total,
      people: data.others.people,
    }
  } else {
    othersSales.value = null
  }
}

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
const structure = computed(() => summary.value.structure || { platforms: [], chassis: [] })

// 实时时钟
const clock = ref('--:--:--')
let clockTimer: ReturnType<typeof setInterval> | null = null
function tick() {
  const d = new Date()
  const pad = (n: number) => n.toString().padStart(2, '0')
  clock.value = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// sparkline 构造（纯 SVG path）
function buildSpark(values: number[]) {
  if (!values || values.length < 2) return { d: '', area: '', trendUp: true, trendPct: 0 }
  const max = Math.max(...values), min = Math.min(...values)
  const range = max - min || 1
  const pts = values.map((v, i) => [i / (values.length - 1) * 100, 22 - (v - min) / range * 18])
  const d = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ')
  const area = d + ' L100,24 L0,24 Z'
  const first = values[0], last = values[values.length - 1]
  const trendUp = last >= first
  const trendPct = first > 0 ? Math.round(Math.abs((last - first) / first) * 100) : 0
  return { d, area, trendUp, trendPct }
}
function sparkFromOpp() {
  return (summary.value.charts as any)?.chart1?.total_series?.map((d: any) => d.value) || []
}
function sparkFromConfig() {
  const c = (summary.value.charts as any)?.chart2 || {}
  const keys = Object.keys(c)
  if (keys.length === 0) return []
  const len = (c[keys[0]] as any[]).length
  return Array.from({ length: len }, (_, i) => keys.reduce((s, k) => s + ((c[k] as any[])[i]?.value || 0), 0))
}

const kpiItems = computed(() => {
  const k: any = summary.value.kpi || {}
  const oppSpark = buildSpark(sparkFromOpp())
  const cfgSpark = buildSpark(sparkFromConfig())
  return [
    { key: 'opp', label: '总商机数', en: 'OPPORTUNITIES', value: k.total_opportunities ?? 0, spark: oppSpark },
    { key: 'cfg', label: '总配置数', en: 'CONFIGURATIONS', value: k.total_configs ?? 0, spark: cfgSpark },
    { key: 'newOpp', label: '周期新增商机', en: 'NEW OPPS', value: k.new_opportunities ?? 0, spark: oppSpark },
    { key: 'newCfg', label: '周期新增配置', en: 'NEW CONFIGS', value: k.new_configs ?? 0, spark: cfgSpark },
  ]
})

// Filters / drill / batch select（保留原逻辑）
const filters = ref({ status: 'all', platform: [] as string[], chassis: [] as string[], search: '' })
const sortBy = ref('created_at')
let filterTimer: ReturnType<typeof setTimeout> | null = null
const drill = ref({ active: false, platform: '', chassis: '', label: '' })
const listCollapsed = ref(false)
const selectMode = ref(false)
const selectedRowKeys = ref<string[]>([])
const batching = ref(false)

function debounceFilter() {
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(() => loadTable(), 300)
}
function onFilterChange() { loadTable() }
function resetFilters() {
  filters.value = { status: 'all', platform: [], chassis: [], search: '' }
  drill.value = { active: false, platform: '', chassis: '', label: '' }
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
  loadTable()
}
function drillOff() { drill.value = { active: false, platform: '', chassis: '', label: '' }; loadTable() }

// PLAT_COLOR 移至 @/constants/platform（系列枚举统一改造）
const PIE_COLORS = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#6B7280']

// 01 商机趋势：总量渐变面积 + 各平台分线
const chart1Opt = computed(() => {
  const c = (summary.value.charts as any)?.chart1
  if (!c?.total_series) return {}
  const labels = c.total_series.map((d: any) => (d.date.length === 7 ? d.date : d.date.slice(5)))
  const platDs = (Object.entries(c.platform_series || {}) as [string, any[]][]).map(([name, vals]) => ({
    name, type: 'line', smooth: true, symbol: 'circle', symbolSize: 4, showSymbol: false,
    lineStyle: { width: 2, color: PLAT_COLOR[name] || '#6B7280' },
    itemStyle: { color: PLAT_COLOR[name] || '#6B7280' },
    emphasis: { focus: 'series' },
    data: vals.map((d: any) => d.value),
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText }, borderColor: chartColors.value.tooltipBorder, borderWidth: 1 },
    legend: { top: 0, textStyle: { color: chartColors.value.axisLabel, fontSize: 10 }, padding: [0, 0, 8, 0], icon: 'roundRect', itemWidth: 12, itemHeight: 2 },
    grid: { left: 40, right: 16, bottom: 28, top: 32 },
    xAxis: { type: 'category', boundaryGap: false, data: labels, axisLine: { lineStyle: { color: chartColors.value.grid } }, axisLabel: { color: chartColors.value.axisLabel, fontSize: 10, rotate: ((labels[0] || '').length === 7 ? 0 : 30) }, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: chartColors.value.splitLine } }, axisLabel: { color: chartColors.value.axisLabel, fontSize: 10 } },
    series: [
      { name: '商机总量', type: 'bar', barWidth: '46%', itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: chartColors.value.barStart }, { offset: 1, color: chartColors.value.barEnd }] }, borderRadius: [4, 4, 0, 0] }, data: c.total_series.map((d: any) => d.value), animationDuration: 1000 },
      ...platDs,
    ],
  }
})

// 02 配置平台趋势：各平台渐变面积
const chart2Opt = computed(() => {
  const c = (summary.value.charts as any)?.chart2
  if (!c) return {}
  const entries = Object.entries(c)
  if (entries.length === 0) return {}
  const labels = (c[entries[0][0]] as any[]).map((d: any) => (d.date.length === 7 ? d.date : d.date.slice(5)))
  const ds = (entries as [string, any[]][]).map(([name, vals]) => {
    const col = PLAT_COLOR[name] || '#6B7280'
    return {
      name, type: 'line', smooth: true, symbol: 'circle', symbolSize: 4, showSymbol: false,
      lineStyle: { width: 2, color: col },
      itemStyle: { color: col },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: col + '40' }, { offset: 1, color: col + '05' }] } },
      emphasis: { focus: 'series' },
      data: vals.map((d: any) => d.value),
    }
  })
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText }, borderColor: chartColors.value.tooltipBorder, borderWidth: 1 },
    legend: { top: 0, textStyle: { color: chartColors.value.axisLabel, fontSize: 10 }, padding: [0, 0, 8, 0], icon: 'roundRect', itemWidth: 12, itemHeight: 2 },
    grid: { left: 40, right: 16, bottom: 28, top: 32 },
    xAxis: { type: 'category', boundaryGap: false, data: labels, axisLine: { lineStyle: { color: chartColors.value.grid } }, axisLabel: { color: chartColors.value.axisLabel, fontSize: 10, rotate: ((labels[0] || '').length === 7 ? 0 : 30) }, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: chartColors.value.splitLine } }, axisLabel: { color: chartColors.value.axisLabel, fontSize: 10 } },
    series: ds,
  }
})

// 02 平台分布：环形图（中心总数）
const pieOpt = computed(() => {
  const data = (structure.value.platforms || []).map((p: any) => ({ name: p.name || '未分类', value: p.count }))
  if (data.length === 0) return {}
  const total = data.reduce((s: number, d: any) => s + d.value, 0)
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText }, borderColor: chartColors.value.tooltipBorder, borderWidth: 1 },
    legend: { bottom: 2, textStyle: { color: chartColors.value.axisLabel, fontSize: 10 }, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    title: { text: total + '', subtext: '总数', left: 'center', top: '34%', textStyle: { fontSize: 26, fontWeight: 700, color: chartColors.value.tooltipText }, subtextStyle: { fontSize: 10, color: chartColors.value.axisLabel } },
    series: [{
      type: 'pie', radius: ['52%', '72%'], center: ['50%', '44%'],
      avoidLabelOverlap: false, label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: chartColors.value.segmentBorder, borderWidth: 2 },
      data, color: PIE_COLORS,
      animationType: 'expansion', animationDuration: 900,
    }],
  }
})

// 03 机箱分布：玫瑰图
const roseOpt = computed(() => {
  const data = (structure.value.chassis || []).map((c: any) => ({ name: c.name || '未分类', value: c.count }))
  if (data.length === 0) return {}
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText }, borderColor: chartColors.value.tooltipBorder, borderWidth: 1 },
    legend: { bottom: 2, type: 'scroll', textStyle: { color: chartColors.value.axisLabel, fontSize: 10 }, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    series: [{
      type: 'pie', roseType: 'radius', radius: ['18%', '72%'], center: ['50%', '44%'],
      label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: chartColors.value.segmentBorder, borderWidth: 2, borderRadius: 3 },
      data, color: PIE_COLORS,
      animationDuration: 900,
    }],
  }
})

// 图表切换
const currentTrendOpt = computed(() => trendView.value === 'opp' ? chart1Opt.value : chart2Opt.value)
const currentDistOpt = computed(() => distView.value === 'platform' ? pieOpt.value : roseOpt.value)

// Table（保留）
const tableData = ref<any[]>([])
const tableLoading = ref(false)
const tablePage = ref(1)
const tablePageSize = ref(8)
const tableTotal = ref(0)
const tableColumns = [{ title: '商机', dataIndex: 'info' }]

// 监听 summary 变化，重新计算业务排行
watch(() => summary.value, computeSalesRank, { deep: true })
// 用户手选过 pageSize 后，停止自适应（尊重用户选择，resize 不再覆盖）
const userPickedPageSize = ref(false)
const tablePagination = computed(() => ({
  current: tablePage.value, pageSize: tablePageSize.value, total: tableTotal.value,
  showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['5', '8', '10', '15', '20', '30', '50'],
}))
function onTableChange(pag: any) {
  tablePage.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== tablePageSize.value) {
    tablePageSize.value = pag.pageSize
    userPickedPageSize.value = true
  }
  loadTable()
}

// 列表 pageSize 自适应容器高度：高屏多显示、矮屏少显示。
// 行高/预留高度为估算值（a-table small + 两行 cell）；用户手选 pageSize 后停止自适应。
const ADAPTIVE_ROW_H = 58
const ADAPTIVE_RESERVED_H = 120
const ADAPTIVE_MIN = 5
const ADAPTIVE_MAX = 50
function computeAdaptivePageSize(): number {
  const el = document.querySelector('.table-section') as HTMLElement | null
  if (!el) return tablePageSize.value
  const usable = el.clientHeight - ADAPTIVE_RESERVED_H
  if (usable <= 0) return ADAPTIVE_MIN
  return Math.min(ADAPTIVE_MAX, Math.max(ADAPTIVE_MIN, Math.floor(usable / ADAPTIVE_ROW_H)))
}
let resizeTimer: ReturnType<typeof setTimeout> | undefined
function onListResize() {
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
function bizStatusText(r: any) {
  if (r?.status === 'archived') return '已归档'
  return ({ pending: '进行中', won: '已中标', lost: '已丢标' } as any)[r?.result] || '进行中'
}
function bizTagColor(r: any) {
  if (r?.status === 'archived') return 'default'
  return ({ pending: 'processing', won: 'success', lost: 'error' } as any)[r?.result] || 'default'
}
function formatDate(s: string) { return s ? s.slice(0, 10) : '-' }
function goToDetail(id: string) { router.push(`/opportunities/${id}`) }
function goToRecycleBin() { router.push('/recycle-bin') }
const rowSelectionCfg = computed(() => selectMode.value ? {
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: string[]) => { selectedRowKeys.value = keys as string[] },
} : undefined)
function enterSelectMode() { selectMode.value = true; selectedRowKeys.value = [] }
function exitSelectMode() { selectMode.value = false; selectedRowKeys.value = [] }
async function handleBatchTrash() {
  if (selectedRowKeys.value.length === 0) return
  batching.value = true
  try {
    await axios.post('/api/opportunities/batch-trash', { opportunity_ids: selectedRowKeys.value })
    message.success(`已将 ${selectedRowKeys.value.length} 项移至回收站`)
    exitSelectMode()
    reloadAll()
  } finally { batching.value = false }
}
async function loadTable() {
  selectedRowKeys.value = []
  tableLoading.value = true
  try {
    const params: any = { page: tablePage.value, page_size: tablePageSize.value }
    if (filters.value.search) params.search = filters.value.search
    if (filters.value.status !== 'all') {
      if (filters.value.status === 'archived') params.status = 'archived'
      else params.result = filters.value.status
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
    params.sort_by = sortBy.value
    params.sort_order = 'desc'
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
  if (s.status) filters.value.status = String(s.status)
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

// Create modal（保留）
const showCreateModal = ref(false)
const creating = ref(false)
const newProject = ref({ customer_name: '', sales_person: '' })
async function handleCreate() {
  if (!newProject.value.customer_name.trim()) {
    message.warning('请输入客户名称')
    return
  }
  creating.value = true
  try {
    await axios.post('/api/opportunities/', newProject.value)
    message.success('创建成功')
    showCreateModal.value = false
    newProject.value = { customer_name: '', sales_person: '' }
    reloadAll()
  } finally { creating.value = false }
}

// Data loading（保留）
async function loadSummary() {
  dataLoading.value = true
  try {
    const params: any = {}
    if (customRange.value) { params.start = customRange.value.start; params.end = customRange.value.end }
    else { params.period = period.value }
    const res = await axios.get('/api/dashboard/summary', { params })
    summary.value = res.data
  } finally { dataLoading.value = false }
}
async function reloadAll() {
  await loadSummary()
  tablePage.value = 1
  await loadTable() // tableData 加载后会自动触发 computeSalesRank
}
function setPeriod(p: string) { customRange.value = null; period.value = p }

onMounted(async () => {
  tick()
  clockTimer = setInterval(tick, 1000)
  seriesStore.ensureSeries()
  restoreListState()
  // 首屏自适应 pageSize（等布局稳定），再加载全部数据
  nextTick(() => {
    if (!userPickedPageSize.value) {
      const adapt = computeAdaptivePageSize()
      if (adapt !== tablePageSize.value) tablePageSize.value = adapt
    }
    reloadAll()
  })
  window.addEventListener('resize', onListResize)
})
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (resizeTimer) clearTimeout(resizeTimer)
  window.removeEventListener('resize', onListResize)
})
watch([() => period.value, () => customRange.value], () => reloadAll())
// 折叠/展开侧栏会改变列表容器高度，展开后重算
watch(listCollapsed, async (v) => {
  if (v) return
  await nextTick()
  onListResize()
})
</script>

<style scoped>
.cockpit { position: relative; display: flex; flex-direction: column; gap: 14px; padding: 16px 24px 24px; min-height: calc(100vh - 56px); }

/* 扫描线背景 */
.cockpit-scan { position: fixed; left: 0; right: 0; top: 56px; bottom: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.cockpit-scan::before { content: ''; position: absolute; left: 0; right: 0; top: -240px; height: 240px; background: linear-gradient(180deg, transparent, var(--cpq-overlay-a8), transparent); animation: cpq-scan-move 9s linear infinite; }
@keyframes cpq-scan-move { 0% { transform: translateY(0); } 100% { transform: translateY(calc(100vh - 56px + 240px)); } }
.cockpit > * { position: relative; z-index: 1; }

/* 顶栏 */
.cockpit-header { display: flex; align-items: center; gap: 20px; padding: 12px 20px; border-radius: var(--cpq-radius-lg); }
.cockpit-brand { display: flex; flex-direction: column; gap: 1px; }
.cockpit-title { margin: 0; font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); letter-spacing: 1px; }
.cockpit-sub { font-size: 11px; color: var(--cpq-text-muted); letter-spacing: 0.5px; }
.cockpit-live { display: flex; align-items: center; gap: 8px; margin-left: auto; padding: 5px 12px; border: 1px solid var(--cpq-overlay-danger15); border-radius: 999px; background: var(--cpq-overlay-danger10); }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--cpq-accent-danger); box-shadow: 0 0 8px var(--cpq-accent-danger); animation: cpq-pulse 1.6s ease-in-out infinite; }
.live-label { font-size: 10px; font-weight: 700; color: var(--cpq-accent-danger); letter-spacing: 1.5px; }
.live-clock { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); font-variant-numeric: tabular-nums; letter-spacing: 1px; }

.period-toggle { display: flex; gap: 6px; }
.period-option { display: flex; align-items: center; gap: 5px; padding: 5px 11px; border: 1px solid var(--cpq-overlay-w10); border-radius: 999px; cursor: pointer; font-size: 12px; color: var(--cpq-text-secondary); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.period-option.active { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); border-color: var(--cpq-accent-primary); }
.period-dot { width: 7px; height: 7px; border-radius: 50%; border: 1.5px solid var(--cpq-text-muted); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.period-dot.active { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); box-shadow: 0 0 6px var(--cpq-overlay-a40); }

/* 自定义区间入口 */
.period-option.custom-entry { padding-right: 9px; }
.custom-text { max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.custom-caret { font-size: 9px; opacity: .55; margin-left: 1px; }

/* KPI 精简行 */
.kpi-deck { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.kpi-mini { display: flex; flex-direction: column; gap: 2px; padding: 10px 16px; border-radius: var(--cpq-radius-md); }
.kpi-mini-label { font-size: 11px; color: var(--cpq-text-secondary); }
.kpi-mini-val {
  font-size: 26px; font-weight: 700; color: var(--cpq-accent-primary); line-height: 1;
  font-feature-settings: var(--cpq-num-feature); font-variant-numeric: tabular-nums lining-nums;
  letter-spacing: -0.02em; text-shadow: var(--cpq-reading-glow);
}

/* AI 分析区 */
.ai-deck { display: grid; grid-template-columns: 1fr; gap: 14px; flex: none; }
.ai-card { padding: 14px 16px; border-radius: var(--cpq-radius-lg); display: flex; flex-direction: column; gap: 10px; }
.ai-header { display: flex; justify-content: space-between; align-items: center; }
.ai-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); display: flex; align-items: center; gap: 6px; letter-spacing: 0.5px; }
.ai-period { font-size: 11px; color: var(--cpq-text-muted); background: var(--cpq-overlay-w5); padding: 2px 8px; border-radius: 4px; }
.ai-empty { text-align: center; padding: 16px; color: var(--cpq-text-muted); font-size: 12px; }

/* 业务排行 */
.rank-content { display: flex; flex-direction: column; gap: 8px; }
.rank-row { display: grid; grid-template-columns: 20px 70px 1fr 45px 36px; align-items: center; gap: 8px; font-size: 12px; }
.rank-num { font-weight: 600; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.rank-num.rank-top { color: var(--cpq-accent-primary); }
.rank-name { color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-bar-wrap { height: 6px; background: var(--cpq-overlay-w10); border-radius: 3px; overflow: hidden; }
.rank-bar { height: 100%; background: linear-gradient(90deg, var(--cpq-accent-primary), var(--cpq-accent-success)); border-radius: 3px; transition: width var(--cpq-dur-2) var(--cpq-ease-smooth); }
.rank-count { color: var(--cpq-text-secondary); font-variant-numeric: tabular-nums; }
.rank-rate { color: var(--cpq-text-muted); font-size: 11px; font-variant-numeric: tabular-nums; text-align: right; }
.rank-others { border-top: 1px dashed var(--cpq-overlay-w10); padding-top: 8px; margin-top: 4px; }
.rank-others .rank-bar-wrap { display: none; }

/* 图表区 */
.chart-deck { display: grid; grid-template-columns: 1.5fr 1fr; gap: 14px; flex: 1 1 0; min-height: 200px; }
.chart-card { padding: 14px 16px; border-radius: var(--cpq-radius-lg); display: flex; flex-direction: column; min-height: 0; }
.deck-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex: none; }
.deck-title { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); letter-spacing: 0.5px; }
.deck-num { font-size: 11px; font-weight: 700; color: var(--cpq-accent-primary); font-variant-numeric: tabular-nums; padding: 1px 6px; border: 1px solid var(--cpq-overlay-a20); border-radius: 4px; background: var(--cpq-overlay-a8); }
.deck-line { flex: 1; height: 1px; background: linear-gradient(90deg, var(--cpq-overlay-a15), transparent); }
.chart-inner { flex: 1 1 0; min-height: 120px; }
.chart-inner-pie { cursor: pointer; }

/* 列表 */
.cockpit-body { display: flex; gap: 14px; align-items: stretch; flex: 1 1 auto; min-height: 0; }
.main-area { flex: 1 1 1px; min-width: 500px; min-height: 0; display: flex; flex-direction: column; gap: 14px; }
.list-panel { position: relative; flex: 0 0 420px; min-width: 420px; max-width: 560px; overflow: hidden; transition: flex-basis var(--cpq-dur-2) var(--cpq-ease-smooth), width var(--cpq-dur-2) var(--cpq-ease-smooth); }
.list-panel.collapsed { flex: 0 0 48px; min-width: 48px; max-width: 48px; }
.list-toggle { position: absolute; top: 0; right: 0; z-index: 2; padding: 5px 12px; border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w6); color: var(--cpq-text-secondary); border-radius: 6px; cursor: pointer; font-size: 12px; white-space: nowrap; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.list-toggle:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.list-panel.collapsed .list-toggle { left: 0; right: 0; text-align: center; }
.list-panel-content { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 10px; padding: 36px 4px 0 0; overflow: hidden; }
.list-header { display: flex; justify-content: space-between; align-items: center; padding: 0 2px; }
.list-title { display: flex; align-items: center; gap: 12px; }
.list-title h3 { margin: 0; font-size: 16px; font-weight: 600; color: var(--cpq-text-primary); }
.list-count { font-size: 12px; color: var(--cpq-text-muted); }
.list-actions { display: flex; gap: 8px; }

.filter-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 12px; }
.dark-select.filter-fixed { flex: 1 1 110px; min-width: 100px; }
.filter-input { flex: 1 1 180px; min-width: 140px; }
.dark-select :deep(.ant-select-selector) { background: var(--cpq-overlay-w5) !important; border-color: var(--cpq-overlay-w10) !important; color: var(--cpq-text-primary) !important; border-radius: 6px !important; }
.dark-select :deep(.ant-select-selection-item) { color: var(--cpq-text-primary) !important; }
.dark-select :deep(.ant-select-arrow) { color: var(--cpq-text-muted) !important; }
.dark-input { background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-overlay-w10); color: var(--cpq-text-primary); padding: 5px 10px; border-radius: 6px; font-size: 13px; outline: none; transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.dark-input:focus { border-color: var(--cpq-accent-primary); box-shadow: 0 0 0 2px var(--cpq-overlay-a10); }
.dark-input::placeholder { color: var(--cpq-text-muted); }

.drill-hint { display: flex; align-items: center; gap: 8px; padding: 7px 14px; background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a15); border-radius: 8px; font-size: 12px; color: var(--cpq-accent-primary); }
.drill-hint button { background: transparent; border: none; color: var(--cpq-text-muted); cursor: pointer; font-size: 12px; margin-left: auto; }
.drill-hint button:hover { color: var(--cpq-text-primary); }

/* 表格 */
.table-section { padding: 0; border-radius: var(--cpq-radius-lg); overflow: auto; flex: 1 1 0; min-height: 0; }
.batch-bar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid var(--cpq-overlay-w6); }
.batch-count { font-size: 13px; color: var(--cpq-text-secondary); }
.batch-actions { display: flex; gap: 8px; }

.opp-cell { display: flex; flex-direction: column; gap: 3px; padding: 2px 0; }
.opp-cell-main { display: flex; align-items: center; gap: 10px; }
.opp-name { color: var(--cpq-text-primary); font-size: 14px; font-weight: 500; cursor: pointer; text-decoration: none; }
.opp-name:hover { color: var(--cpq-accent-primary); }
.opp-cell-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.opp-cell-meta .meta { font-size: 11px; color: var(--cpq-text-secondary); }
.opp-cell-meta .meta i { font-style: normal; color: var(--cpq-text-muted); margin-right: 4px; }
.opp-cell-meta .meta-date i { margin-right: 4px; }

/* Buttons */
.action-btn { display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary); border-radius: 6px; cursor: pointer; font-size: 13px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.action-btn:hover:not(:disabled) { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.action-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.action-btn.create-btn { background: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); border-color: var(--cpq-accent-primary); font-weight: 500; }
.action-btn.create-btn:hover:not(:disabled) { opacity: 0.9; color: var(--cpq-accent-on-primary); }
.action-btn.danger-btn { color: var(--cpq-accent-danger); }
.action-btn.danger-btn:hover:not(:disabled) { color: var(--cpq-accent-danger); border-color: var(--cpq-accent-danger); }

/* Table dark overrides */
.cockpit :deep(.ant-table-wrapper .ant-table) { background: transparent; color: var(--cpq-text-primary); }
.cockpit :deep(.ant-table-thead > tr > th) { background: var(--cpq-overlay-w4) !important; color: var(--cpq-text-secondary) !important; font-size: 12px; font-weight: 500; border-bottom: 1px solid var(--cpq-overlay-w6) !important; }
.cockpit :deep(.ant-table-tbody > tr > td) { border-bottom: 1px solid var(--cpq-overlay-w4) !important; color: var(--cpq-text-primary); }
.cockpit :deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-a5) !important; }
.cockpit :deep(.ant-table-cell) { padding: 10px 14px; }
.cockpit :deep(.ant-pagination) { padding: 12px 16px; border-top: 1px solid var(--cpq-overlay-w4); }
.cockpit :deep(.ant-pagination-item), .cockpit :deep(.ant-pagination-prev), .cockpit :deep(.ant-pagination-next) { background: transparent !important; border-color: var(--cpq-overlay-w10) !important; }
.cockpit :deep(.ant-pagination-item a), .cockpit :deep(.ant-pagination-item-link) { color: var(--cpq-text-secondary) !important; background: transparent !important; border: none !important; }
.cockpit :deep(.ant-pagination-item-active) { border-color: var(--cpq-accent-primary) !important; }
.cockpit :deep(.ant-pagination-item-active a) { color: var(--cpq-accent-primary) !important; }

@media (prefers-reduced-motion: reduce) {
  .cockpit-scan::before { animation: none; display: none; }
  .live-dot { animation: none; }
}
@media (max-width: 1200px) {
  .kpi-deck { grid-template-columns: repeat(2, 1fr); }
  .ai-deck { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .chart-deck { grid-template-columns: 1fr; }
  .kpi-deck { grid-template-columns: 1fr; }
  .cockpit-header { flex-wrap: wrap; }
  .cockpit-live { margin-left: 0; }
  .ai-deck { grid-template-columns: 1fr; }
}
</style>
