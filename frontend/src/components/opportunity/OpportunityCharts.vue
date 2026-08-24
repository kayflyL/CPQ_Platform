<template>
  <section class="chart-deck" :class="{ 'personal-chart-deck': !canViewAll }">
    <div class="chart-card chart-card-trend glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>趋势分析</div>
        <a-segmented v-model:value="trendView" :options="trendOptions" size="small" />
      </div>
      <v-chart class="chart-inner" :key="'trend-' + trendView" :option="currentTrendOpt" autoresize />
    </div>
    <div class="chart-card chart-card-dist glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>结构分布</div>
        <a-segmented v-model:value="distView" :options="distOptions" size="small" />
      </div>
      <v-chart class="chart-inner chart-inner-pie" :option="currentDistOpt" autoresize @click="onDistClick" />
    </div>
    <button v-if="isMobile" class="list-tile glass" @click="$emit('open-list-drawer')">
      <span class="list-tile-title">商机列表 <span class="lt-count">{{ tableTotal }}</span></span>
      <span class="list-tile-preview">
        <span v-for="o in recentOpps" :key="o.id" class="lt-item">
          <span class="lt-name">{{ o.name }}</span>
          <span v-if="o.platform" class="lt-plat">{{ o.platform }}</span>
        </span>
        <span v-if="!recentOpps.length" class="lt-empty">暂无商机</span>
      </span>
    </button>
    <div v-if="canViewAll" class="chart-card chart-card-rank glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>业务排行</div>
        <button v-if="rankExpanded" class="rank-toggle" @click="rankExpanded = false">收起其他 ▲</button>
      </div>
      <div class="rank-body" :class="{ 'rank-body-scroll': rankExpanded }">
        <v-chart v-if="topSales.length" class="chart-inner" :style="rankExpanded ? { height: rankBodyHeight + 'px', flex: 'none' } : null" :option="rankOpt" autoresize @click="onRankClick" />
        <div v-else class="chart-empty">暂无排行数据</div>
      </div>
    </div>
    <div v-if="canViewAll" class="chart-card chart-card-won glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>线索转化</div>
        <a-segmented v-model:value="wonView" :options="wonOptions" size="small" />
      </div>
      <div v-if="wonView === 'won'" class="won-branch">
        <button v-if="wonExpanded" class="rank-toggle" @click="wonExpanded = false">收起 ▲</button>
        <div v-if="wonRows.length" class="won-list">
          <div class="won-row won-head">
            <span class="won-rank"></span>
            <span class="won-name">业务</span>
            <span class="won-num">线索</span>
            <span class="won-num">成交</span>
            <span class="won-rate-head">成交率</span>
          </div>
          <div v-for="(r, i) in wonRows" :key="r.name + i" class="won-row" :class="{ 'won-others': r.others, 'won-clickable': r.expandable }" @click="onWonRowClick(r)">
            <span class="won-rank">{{ r.others ? '·' : i + 1 }}</span>
            <span class="won-name">{{ r.name }}<span v-if="r.expandable" class="won-expand-hint"> ▸</span></span>
            <span class="won-num">{{ r.count }}</span>
            <span class="won-num won-won">{{ r.won }}</span>
            <span class="won-rate" :style="{ color: wonRateColor(r.rate) }">{{ r.rate }}%</span>
          </div>
        </div>
        <div v-else class="chart-empty">暂无转化数据</div>
      </div>
      <div v-else class="profit-box-wrap">
        <v-chart v-if="profitHasData" class="chart-inner" :key="'profit-box'" :option="profitBoxOpt" autoresize />
        <div v-else class="chart-empty">暂无机型利润数据（需报价单填机型型号+利润率）</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart, TreemapChart, BoxplotChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'
import { PLAT_COLOR, PLAT_COLOR_FALLBACK } from '@/constants/platform'

use([CanvasRenderer, LineChart, BarChart, PieChart, TreemapChart, BoxplotChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

interface SalesRank { name: string; count: number; won: number; rate: number }
interface ChartSummary {
  period_label: string
  kpi: Record<string, any>
  charts: Record<string, any>
  structure: any
  dates: any[]
}

const props = defineProps<{
  summary: ChartSummary
  canViewAll: boolean
  tableTotal: number
  recentOpps: Array<{ id: string; name: string; platform: string }>
  isMobile: boolean
}>()

const emit = defineEmits<{
  (e: 'drill-on', type: string, name: string): void
  (e: 'open-list-drawer'): void
}>()

const { chartColors } = useChartTheme()
const structure = computed(() => props.summary.structure || { platforms: [], chassis: [] })

const trendView = ref<'opp' | 'model'>('opp')
const distView = ref<'platform' | 'chassis'>('platform')
const wonView = ref<'won' | 'profit'>('won')
const wonOptions = [
  { value: 'won', label: '线索转化' },
  { value: 'profit', label: '机型利润' },
]
const trendOptions = [
  { value: 'opp', label: '商机趋势' },
  { value: 'model', label: '机型趋势' },
]
const distOptions = [
  { value: 'platform', label: '平台' },
  { value: 'chassis', label: '机箱' },
]

const topSales = ref<SalesRank[]>([])
const othersSales = ref<{ count: number; rate: number; people: number } | null>(null)
const othersList = ref<SalesRank[]>([])
const rankExpanded = ref(false)
const wonExpanded = ref(false)
const RANK_ROW_H = 30
const rankBodyHeight = computed(() => Math.max((topSales.value.length + othersList.value.length) * RANK_ROW_H, 120))

function computeSalesRank() {
  const data = (props.summary as any).sales_rank
  rankExpanded.value = false
  wonExpanded.value = false
  if (!data || !data.top) {
    topSales.value = []
    othersSales.value = null
    othersList.value = []
    return
  }

  const total = data.total || 1
  topSales.value = data.top.map((s: any) => ({
    name: s.name,
    count: s.count,
    won: s.won || 0,
    rate: s.count / total,
  }))
  othersList.value = (data.others_list || []).map((s: any) => ({
    name: s.name,
    count: s.count,
    won: s.won || 0,
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

watch(() => props.summary, computeSalesRank, { deep: true })

const PIE_COLORS = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#6B7280']

const chart1Opt = computed(() => {
  const c = props.summary.charts?.chart1
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

const MODEL_COLORS = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#FA8C16', '#52C41A', '#6B7280']
const chart2Opt = computed(() => {
  const c = props.summary.charts?.chart2
  const data = c?.data
  if (!Array.isArray(data) || data.length === 0) return {}
  const totals: Record<string, number> = {}
  for (const row of data) {
    const pn = row[2], cnt = Number(row[1]) || 0
    totals[pn] = (totals[pn] || 0) + cnt
  }
  const items = Object.entries(totals)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
  if (items.length === 0) return {}
  const total = items.reduce((s, d) => s + d.value, 0)
  return {
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText },
      borderColor: chartColors.value.tooltipBorder, borderWidth: 1,
      formatter: (p: any) => `${p.name}<br/>报价 <b>${p.value}</b> 次 · 占比 <b>${total ? (p.value / total * 100).toFixed(1) : 0}%</b>`,
    },
    series: [{
      type: 'treemap',
      roam: false, nodeClick: false, breadcrumb: { show: false },
      left: 0, right: 0, top: 4, bottom: 0,
      label: {
        show: true, position: 'inside', fontWeight: 600,
        formatter: (p: any) => {
          const pct = total ? (p.value / total * 100).toFixed(0) : '0'
          return `{n|${p.name}}\n{v|${p.value}次 · ${pct}%}`
        },
        rich: {
          n: { fontSize: 12, fontWeight: 700, color: '#fff', lineHeight: 18, textShadowBlur: 4, textShadowColor: 'rgba(0,0,0,0.3)' },
          v: { fontSize: 10, color: 'rgba(255,255,255,0.9)', lineHeight: 14 },
        },
      },
      upperLabel: { show: false },
      itemStyle: { borderColor: chartColors.value.segmentBorder, borderWidth: 2, gapWidth: 3 },
      levels: [{ itemStyle: { borderColor: chartColors.value.segmentBorder, borderWidth: 2, gapWidth: 3 } }],
      data: items.map((d, i) => ({
        name: d.name, value: d.value,
        itemStyle: { color: MODEL_COLORS[i % MODEL_COLORS.length] },
      })),
      animationDuration: 700,
    }],
  }
})

const profitBoxOpt = computed(() => {
  const c = props.summary.charts?.chart5
  const boxes = c?.boxes
  if (!Array.isArray(boxes) || boxes.length === 0) return {}
  const names = boxes.map((b: any) => b.name)
  const boxData = boxes.map((b: any) => [b.min, b.q1, b.median, b.q3, b.max])
  const scatterData: any[] = []
  boxes.forEach((b: any, i: number) => {
    (b.scatter || []).forEach((v: number) => scatterData.push([i, v]))
  })
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText },
      borderColor: chartColors.value.tooltipBorder, borderWidth: 1,
      formatter: (p: any) => {
        if (p.componentSubType === 'boxplot') {
          const v = p.value
          return `${names[v[0] || p.dataIndex]}<br/>` +
            `最大 <b>${v[5] ?? v[4]}%</b><br/>Q3 <b>${v[4] ?? '-'}%</b><br/>` +
            `中位 <b>${v[3] ?? '-'}%</b><br/>Q1 <b>${v[2] ?? '-'}%</b><br/>最小 <b>${v[1] ?? '-'}%</b>`
        }
        return `${names[p.value[0]]}<br/>利润率 <b>${p.value[1]}%</b>`
      },
    },
    grid: { left: 44, right: 16, top: 12, bottom: 30 },
    xAxis: {
      type: 'category', data: names, boundaryGap: true,
      axisLine: { lineStyle: { color: chartColors.value.grid } },
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 10, rotate: names.length > 4 ? 20 : 0, interval: 0 },
      axisTick: { show: false }, splitLine: { show: false },
    },
    yAxis: {
      type: 'value', name: '利润率%', nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      splitLine: { lineStyle: { color: chartColors.value.splitLine } },
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 10, formatter: '{value}%' },
    },
    series: [
      {
        name: '利润分布', type: 'boxplot', data: boxData,
        itemStyle: { color: chartColors.value.barStart + '55', borderColor: chartColors.value.accent, borderWidth: 1.5 },
        animationDuration: 800,
      },
      {
        name: '利润点', type: 'scatter', data: scatterData, symbolSize: 5,
        itemStyle: { color: chartColors.value.accent, opacity: 0.55 },
        animationDuration: 600,
      },
    ],
  }
})
const profitHasData = computed(() => {
  const boxes = props.summary.charts?.chart5?.boxes
  return Array.isArray(boxes) && boxes.length > 0
})

const pieOpt = computed(() => {
  const data = (structure.value.platforms || []).map((p: any) => ({ name: p.name || '未分类', value: p.count, itemStyle: { color: PLAT_COLOR[p.name] || PLAT_COLOR_FALLBACK } }))
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
      data,
      animationType: 'expansion', animationDuration: 900,
    }],
  }
})

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

const rankOpt = computed(() => {
  if (!topSales.value.length) return {}
  const rows = topSales.value.map((s) => ({ name: s.name, count: s.count, rate: s.rate, others: false }))
  if (rankExpanded.value && othersList.value.length) {
    othersList.value.forEach((s) => rows.push({ name: s.name, count: s.count, rate: s.rate, others: false }))
  } else if (othersSales.value && othersSales.value.count > 0) {
    rows.push({ name: `其他 ${othersSales.value.people} 人`, count: othersSales.value.count, rate: othersSales.value.rate, others: true })
  }
  const top = rows[0]?.count || 1
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: chartColors.value.tooltipBg, textStyle: { color: chartColors.value.tooltipText },
      borderColor: chartColors.value.tooltipBorder, borderWidth: 1,
      formatter: (params: any) => {
        const r = rows[params[0].dataIndex]
        return `${r.name}<br/>商机数 <b>${r.count}</b> · 占比 ${(r.rate * 100).toFixed(1)}%`
      },
    },
    grid: { left: 4, right: 44, top: 8, bottom: 4, containLabel: true },
    xAxis: {
      type: 'value', max: Math.max(1, Math.ceil(top * 1.2)),
      splitLine: { lineStyle: { color: chartColors.value.splitLine } },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 10 },
    },
    yAxis: {
      type: 'category', inverse: true, data: rows.map((r) => r.name),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        margin: 12, color: chartColors.value.axisLabel, fontSize: 12,
        formatter: (_v: string, i: number) => `{${i < 3 ? 'rt' : 'rm'}|${i + 1}}  {n|${rows[i].name}}`,
        rich: {
          rt: { color: chartColors.value.accent, fontWeight: 700, fontSize: 11, align: 'right' },
          rm: { color: chartColors.value.tick, fontWeight: 600, fontSize: 11, align: 'right' },
          n: { color: chartColors.value.tooltipText, fontSize: 12 },
        },
      },
    },
    series: [{
      type: 'bar', barMaxWidth: 14, itemStyle: { borderRadius: [0, 6, 6, 0] },
      data: rows.map((r) => ({
        value: r.count,
        itemStyle: { color: r.others
          ? chartColors.value.mutedBar
          : { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: chartColors.value.barEnd }, { offset: 1, color: chartColors.value.barStart }] } },
      })),
      label: { show: true, position: 'right', color: chartColors.value.tooltipText, fontSize: 11, fontWeight: 600,
        formatter: (p: any) => {
          const r = rows[p.dataIndex]
          return r.others ? `${r.count}  ▸` : `${r.count}`
        } },
      animationDuration: 800,
    }],
  }
})

const wonRows = computed(() => {
  const rows = topSales.value.map((s) => ({ name: s.name, count: s.count, won: s.won, others: false, expandable: false }))
  if (wonExpanded.value) {
    othersList.value.forEach((s) => rows.push({ name: s.name, count: s.count, won: s.won, others: false, expandable: false }))
  } else if (othersSales.value && othersSales.value.count > 0) {
    const othersWon = othersList.value.reduce((a, s) => a + (s.won || 0), 0)
    rows.push({ name: `其他 ${othersSales.value.people} 人`, count: othersSales.value.count, won: othersWon, others: true, expandable: true })
  }
  return rows.map((r) => ({ ...r, rate: r.count > 0 ? Math.round((r.won / r.count) * 100) : 0 }))
})

function onWonRowClick(row: any) {
  if (row.expandable) wonExpanded.value = true
}

function wonRateColor(rate: number) {
  if (rate >= 50) return '#52C9A0'
  if (rate >= 30) return '#1677FF'
  return '#86909c'
}

function onRankClick(params: any) {
  if (rankExpanded.value) return
  if (params?.componentType === 'series' && typeof params.name === 'string' && params.name.startsWith('其他')) {
    rankExpanded.value = true
  }
}

function onDistClick(p: any) {
  emit('drill-on', distView.value === 'platform' ? 'platform' : 'chassis', p.name)
}

const currentTrendOpt = computed(() => trendView.value === 'opp' ? chart1Opt.value : chart2Opt.value)
const currentDistOpt = computed(() => distView.value === 'platform' ? pieOpt.value : roseOpt.value)
</script>

<style scoped>
.chart-deck { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); grid-template-rows: minmax(0, 0.8fr) minmax(0, 1.2fr); grid-template-areas: "rank won" "trend dist"; gap: 14px; flex: 1 1 0; min-height: 380px; }
.chart-deck.personal-chart-deck { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); grid-template-areas: "trend dist"; }
.chart-card { padding: 14px 16px; border-radius: var(--cpq-radius-lg); display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
.chart-card-won { grid-area: won; }
.chart-card-rank { grid-area: rank; }
.chart-card-trend { grid-area: trend; }
.chart-card-dist { grid-area: dist; }
.won-list { flex: 1 1 0; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; }
.won-branch { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.profit-box-wrap { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.won-list::-webkit-scrollbar { width: 6px; }
.won-list::-webkit-scrollbar-thumb { background: var(--cpq-overlay-a20); border-radius: 3px; }
.won-list::-webkit-scrollbar-track { background: transparent; }
.won-row { display: grid; grid-template-columns: 20px 1fr 34px 34px 46px; align-items: center; gap: 8px; padding: 6px 2px; flex: 1 1 0; min-height: 16px; border-bottom: 1px solid var(--cpq-overlay-w4); }
.won-row:last-child { border-bottom: none; }
.won-head { flex: 0 0 auto; min-height: 0; font-size: 11px; color: var(--cpq-text-muted); font-weight: 500; border-bottom-color: var(--cpq-overlay-w8); }
.won-clickable { cursor: pointer; transition: background var(--cpq-dur-1) var(--cpq-ease-smooth); }
.won-clickable:hover { background: var(--cpq-overlay-a8); }
.won-expand-hint { color: var(--cpq-accent-primary); font-size: 10px; }
.won-rank { font-size: 11px; font-weight: 700; color: var(--cpq-accent-primary); text-align: center; font-variant-numeric: tabular-nums; }
.won-name { font-size: 12.5px; color: var(--cpq-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.won-num { font-size: 12.5px; color: var(--cpq-text-secondary); text-align: right; font-variant-numeric: tabular-nums; }
.won-won { color: #52C9A0; font-weight: 600; }
.won-rate-head { font-size: 11px; color: var(--cpq-text-muted); text-align: right; }
.won-rate { font-size: 12.5px; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.won-others .won-name, .won-others .won-num { color: var(--cpq-text-muted); }
.deck-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex: none; }
.deck-title { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); letter-spacing: 0.5px; }
.deck-line { flex: 1; height: 1px; background: linear-gradient(90deg, var(--cpq-overlay-a15), transparent); }
.rank-toggle { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border: 1px solid var(--cpq-overlay-a20); border-radius: 999px; background: var(--cpq-overlay-a8); color: var(--cpq-accent-primary); font-size: 11px; cursor: pointer; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.rank-toggle:hover { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary); }
.chart-inner { flex: 1 1 0; width: 100%; min-width: 0; min-height: 120px; }
.chart-inner-pie { cursor: pointer; }
.chart-empty { flex: 1 1 0; display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted); font-size: 12px; }
.rank-body { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.rank-body-scroll { overflow-y: auto; }
.rank-body-scroll::-webkit-scrollbar { width: 6px; }
.rank-body-scroll::-webkit-scrollbar-thumb { background: var(--cpq-overlay-a20); border-radius: 3px; }
.rank-body-scroll::-webkit-scrollbar-track { background: transparent; }

@media (max-width: 1200px) {
  .chart-deck { grid-template-columns: 1fr 1fr; grid-template-areas: "trend trend" "rank won" "dist dist"; }
  .chart-deck.personal-chart-deck { grid-template-columns: 1fr; grid-template-areas: "trend" "dist"; }
}

@media (max-width: 768px) {
  .chart-deck {
    display: grid; gap: 8px; min-height: 0;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-rows: 220px 240px 200px 220px;
    grid-template-areas: "dist listtile" "trend trend" "rank rank" "won won";
  }
  .chart-deck.personal-chart-deck {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-rows: 220px 240px;
    grid-template-areas: "dist listtile" "trend trend";
  }
  .chart-card { min-height: 0; border-radius: 8px; padding: 12px 14px; }
  .chart-card-trend { grid-area: trend; }
  .chart-card-dist { grid-area: dist; }
  .chart-card-rank { grid-area: rank; }
  .chart-card-won { grid-area: won; }
  .chart-card-dist .deck-line { display: none; }
  .chart-card-dist .deck-title { gap: 0; }
  .chart-card-dist .deck-header :deep(.ant-segmented) { transform: scale(0.85); transform-origin: right center; flex-shrink: 0; }
  .chart-card-dist .chart-inner-pie { width: 100%; }
  .chart-card-dist .chart-inner-pie canvas { width: 100% !important; }
  .list-tile {
    grid-area: listtile; width: 100%; box-sizing: border-box; font: inherit;
    border: none; cursor: pointer;
    display: flex; flex-direction: column; gap: 8px;
    padding: 12px 14px; border-radius: 8px;
    color: var(--cpq-text-primary); text-align: left;
  }
  .list-tile-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--cpq-text-secondary); flex: none; }
  .lt-count { font-size: 10px; font-weight: 600; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10); padding: 0 6px; border-radius: 999px; }
  .list-tile-preview { display: flex; flex-direction: column; gap: 5px; min-height: 0; overflow: hidden; }
  .lt-item { display: flex; align-items: baseline; gap: 6px; line-height: 1.3; }
  .lt-name { flex: 1 1 0; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
  .lt-plat { flex: none; font-size: 11px; color: var(--cpq-text-secondary); opacity: 0.6; }
  .lt-empty { font-size: 12px; color: var(--cpq-text-muted); font-style: italic; }
}
</style>
