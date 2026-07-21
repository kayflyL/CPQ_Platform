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

    <!-- 图表区（左：趋势折线 右：分布环形）-->
    <section class="chart-deck">
      <div class="chart-col chart-col-main">
        <div class="chart-card glass">
          <div class="deck-title"><span class="deck-num">01</span><span class="deck-line"></span>商机总量趋势</div>
          <v-chart class="chart-inner" :option="chart1Opt" autoresize />
        </div>
        <div class="chart-card glass">
          <div class="deck-title"><span class="deck-num">02</span><span class="deck-line"></span>配置平台趋势</div>
          <v-chart class="chart-inner" :option="chart2Opt" autoresize />
        </div>
      </div>
      <div class="chart-col chart-col-side">
        <div class="chart-card glass">
          <div class="deck-title"><span class="deck-num">03</span><span class="deck-line"></span>平台分布</div>
          <v-chart class="chart-inner chart-inner-pie" :option="pieOpt" autoresize @click="(p: any) => drillOn('platform', p.name)" />
        </div>
        <div class="chart-card glass">
          <div class="deck-title"><span class="deck-num">04</span><span class="deck-line"></span>机箱分布</div>
          <v-chart class="chart-inner chart-inner-pie" :option="roseOpt" autoresize @click="(p: any) => drillOn('chassis', p.name)" />
        </div>
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
          <a-select-option value="all">全部状态</a-select-option>
          <a-select-option value="active">进行中</a-select-option>
          <a-select-option value="archived">已归档</a-select-option>
        </a-select>
        <a-select v-model:value="filters.platform" size="small" mode="multiple" placeholder="平台类型" :maxTagCount="1" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option value="Polaris">Polaris</a-select-option>
          <a-select-option value="Orion">Orion</a-select-option>
          <a-select-option value="Intel">Intel</a-select-option>
          <a-select-option value="其他">其他</a-select-option>
          <a-select-option value="工作站">工作站</a-select-option>
        </a-select>
        <a-select v-model:value="filters.chassis" size="small" mode="multiple" placeholder="机箱形态" :maxTagCount="1" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option value="2U">2U</a-select-option>
          <a-select-option value="4U">4U</a-select-option>
          <a-select-option value="5U">5U</a-select-option>
          <a-select-option value="4.5U">4.5U</a-select-option>
          <a-select-option value="8U">8U</a-select-option>
          <a-select-option value="工作站">工作站</a-select-option>
        </a-select>
        <a-select v-model:value="sortOrder" size="small" class="dark-select filter-fixed" @change="onFilterChange">
          <a-select-option value="desc">更新时间 新→旧</a-select-option>
          <a-select-option value="asc">更新时间 旧→新</a-select-option>
        </a-select>
        <input v-model="filters.search" placeholder="搜索客户 / 销售人员 / 商机名..." class="dark-input filter-input" @input="debounceFilter" />
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
                  <a class="opp-name" @click="goToDetail(record.opportunity_id)">{{ record.opportunity_name || '未命名' }}</a>
                  <span class="cpq-led" :class="ledClass(record.status)">{{ statusText(record.status) }}</span>
                </div>
                <div class="opp-cell-meta">
                  <span class="meta" v-if="record.customer_name"><i>客户</i>{{ record.customer_name }}</span>
                  <span class="meta" v-if="record.sales_person"><i>销售</i>{{ record.sales_person }}</span>
                  <span class="meta" v-if="record.platform_type"><i>平台</i>{{ record.platform_type }}</span>
                  <span class="meta" v-if="record.chassis_form"><i>机箱</i>{{ record.chassis_form }}</span>
                  <span class="meta" v-if="record.purchase_qty"><i>采购</i>{{ record.purchase_qty }}</span>
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
        <a-form-item label="商机名称" required><a-input v-model:value="newProject.opportunity_name" placeholder="请输入商机名称" /></a-form-item>
        <a-form-item label="客户名称"><a-input v-model:value="newProject.customer_name" placeholder="客户名称（可选）" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
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
import dayjs from 'dayjs'

use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const router = useRouter()
const { chartColors } = useChartTheme()

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
const summary = ref({ period_label: '', kpi: {}, charts: {}, structure: { platforms: [], chassis: [] }, dates: [] })
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
const sortOrder = ref('desc')
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
function pct(count: number, items: any[]) {
  const total = items.reduce((s, i) => s + i.count, 0)
  return total > 0 ? Math.round((count / total) * 100) : 0
}

const PLAT_COLOR: Record<string, string> = { Polaris: '#FF3B5C', Orion: '#0EA5E9', Intel: '#8A94A8', 其他: '#6B7280', 工作站: '#A855F7', INTEL: '#8A94A8', 'INTEL&Orion': '#8A94A8', 兆芯: '#3B82F6', 未分类: '#6B7280' }
const PIE_COLORS = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#6B7280']

// 01 商机趋势：总量渐变面积 + 各平台分线
const chart1Opt = computed(() => {
  const c = (summary.value.charts as any)?.chart1
  if (!c?.total_series) return {}
  const labels = c.total_series.map((d: any) => (d.date.length === 7 ? d.date : d.date.slice(5)))
  const platDs = Object.entries(c.platform_series || {}).map(([name, vals]: [string, any[]]) => ({
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
  const ds = entries.map(([name, vals]: [string, any[]]) => {
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

// Table（保留）
const tableData = ref<any[]>([])
const tableLoading = ref(false)
const tablePage = ref(1)
const tablePageSize = ref(8)
const tableTotal = ref(0)
const tableColumns = [{ title: '商机', dataIndex: 'info' }]
const tablePagination = computed(() => ({
  current: tablePage.value, pageSize: tablePageSize.value, total: tableTotal.value,
  showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['8', '10', '20', '50'],
}))
function onTableChange(pag: any) {
  tablePage.value = pag.current || 1
  tablePageSize.value = pag.pageSize || 20
  loadTable()
}
function statusText(s: string) { return ({ active: '进行中', archived: '已归档', deleted: '已删除' } as any)[s] || s }
function ledClass(s: string) { return ({ active: 'cpq-led--active', archived: 'cpq-led--muted', deleted: 'cpq-led--danger' } as any)[s] || 'cpq-led--muted' }
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
    if (filters.value.status !== 'all') params.status = filters.value.status
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
    params.sort_by = 'updated_at'
    params.sort_order = sortOrder.value
    const res = await axios.get('/api/opportunities/list', { params })
    tableData.value = res.data.items || []
    tableTotal.value = res.data.total || 0
  } finally {
    tableLoading.value = false
  }
}

// Create modal（保留）
const showCreateModal = ref(false)
const creating = ref(false)
const newProject = ref({ opportunity_name: '', customer_name: '' })
async function handleCreate() {
  if (!newProject.value.opportunity_name.trim()) return
  creating.value = true
  try {
    await axios.post('/api/opportunities/', newProject.value)
    message.success('创建成功')
    showCreateModal.value = false
    newProject.value = { opportunity_name: '', customer_name: '' }
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
  loadTable()
}
function setPeriod(p: string) { customRange.value = null; period.value = p }

onMounted(() => {
  tick()
  clockTimer = setInterval(tick, 1000)
  reloadAll()
})
onBeforeUnmount(() => { if (clockTimer) clearInterval(clockTimer) })
watch([() => period.value, () => customRange.value], () => reloadAll())
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

/* 图表区 */
.chart-deck { display: grid; grid-template-columns: 1.85fr 1fr; gap: 14px; align-items: start; }
.chart-col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.chart-card { padding: 14px 16px; border-radius: var(--cpq-radius-lg); }
.deck-title { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); margin-bottom: 8px; letter-spacing: 0.5px; }
.deck-num { font-size: 11px; font-weight: 700; color: var(--cpq-accent-primary); font-variant-numeric: tabular-nums; padding: 1px 6px; border: 1px solid var(--cpq-overlay-a20); border-radius: 4px; background: var(--cpq-overlay-a8); }
.deck-line { flex: 1; height: 1px; background: linear-gradient(90deg, var(--cpq-overlay-a15), transparent); }
.chart-inner { height: 220px; }
.chart-inner-pie { height: 220px; cursor: pointer; }

/* 列表 */
.cockpit-body { display: flex; gap: 14px; align-items: stretch; }
.main-area { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.list-panel { position: relative; width: 380px; flex-shrink: 0; overflow: hidden; transition: width var(--cpq-dur-2) var(--cpq-ease-smooth); }
.list-panel.collapsed { width: 48px; }
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
}
@media (max-width: 768px) {
  .chart-deck { grid-template-columns: 1fr; }
  .kpi-deck { grid-template-columns: 1fr; }
  .cockpit-header { flex-wrap: wrap; }
  .cockpit-live { margin-left: 0; }
}
</style>
