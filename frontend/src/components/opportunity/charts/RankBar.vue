<template>
  <div class="rank-bar-wrap">
    <button v-if="expanded" class="rank-collapse" @click="expanded = false">收起 ▲</button>
    <v-chart v-if="rows.length" class="rank-bar" :option="opt" autoresize @click="onPick" />
    <div v-else class="chart-empty">暂无排行数据</div>
  </div>
</template>

<script setup lang="ts">
// 业务排行横条（Top5 + 「其他」聚合可展开）：商机线索页与驾驶舱共用。
// 「其他」点击内部展开；具名业务点击对外发 pick 事件（线索页不用、驾驶舱用于下钻）。
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomInsideComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, DataZoomInsideComponent])

interface RankItem { name: string; count: number; won?: number }

const props = defineProps<{
  top: RankItem[]
  others?: { count: number; people: number } | null
  othersList?: RankItem[]
}>()

const emit = defineEmits<{ (e: 'pick', name: string): void }>()

const expanded = ref(false)
const { chartColors } = useChartTheme()

// 展开后超过一屏的行进内部滚动(窗口固定行数,滚轮/触摸平移),条宽不被压扁
const VISIBLE_ROWS = 10

const rows = computed(() => {
  const rows: (RankItem & { others?: boolean })[] = props.top.map(s => ({ ...s, others: false }))
  if (expanded.value) {
    (props.othersList || []).forEach(s => rows.push({ ...s, others: false }))
  } else if (props.others && props.others.count > 0) {
    rows.push({ name: `其他 ${props.others.people} 人`, count: props.others.count, others: true })
  }
  return rows
})

const opt = computed(() => {
  if (!rows.value.length) return {}
  const c = chartColors.value
  const top = rows.value[0]?.count || 1
  // dataZoom 滚动后序号/dataIndex 都是窗口内位置,标签一律按类别名反查行与名次,不依赖序号
  const rowByName = new Map(rows.value.map(r => [r.name, r]))
  const rankByName = new Map(rows.value.map((r, i) => [r.name, i]))
  return {
    backgroundColor: 'transparent',
    dataZoom: rows.value.length > VISIBLE_ROWS ? [{
      // zoomLock 会把 RoamController 切到 move 模式、整个禁掉滚轮监听,故用 zoomOnMouseWheel:false 只禁缩放
      type: 'inside', yAxisIndex: 0,
      startValue: 0, endValue: VISIBLE_ROWS - 1,
      zoomOnMouseWheel: false, moveOnMouseWheel: true,
    }] : undefined,
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText },
      borderColor: c.tooltipBorder, borderWidth: 1,
      formatter: (params: any) => {
        const r = rowByName.get(params[0].name) || rows.value[params[0].dataIndex]
        if (!r) return ''
        const won = r.won != null ? ` · 成单 <b>${r.won}</b>` : ''
        const hint = r.others
          ? '<br/><span style="color:var(--cpq-text-muted)">点击展开</span>'
          : (rows.value.length > VISIBLE_ROWS && params[0].dataIndex === 0 ? '<br/><span style="color:var(--cpq-text-muted)">滚轮/滑动查看更多</span>' : '')
        return `${r.name}<br/>商机数 <b>${r.count}</b>${won}${hint}`
      },
    },
    grid: { left: 4, right: 44, top: 8, bottom: 4, containLabel: true },
    xAxis: {
      type: 'value', max: Math.max(1, Math.ceil(top * 1.2)),
      splitLine: { lineStyle: { color: c.splitLine } },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: c.axisLabel, fontSize: 10 },
    },
    yAxis: {
      type: 'category', inverse: true, data: rows.value.map(r => r.name),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        margin: 12, color: c.axisLabel, fontSize: 12,
        formatter: (v: string) => {
          const i = rankByName.get(v) ?? 0
          return `{${i < 3 ? 'rt' : 'rm'}|${i + 1}}  {n|${v}}`
        },
        rich: {
          rt: { color: c.accent, fontWeight: 700, fontSize: 11, align: 'right' },
          rm: { color: c.tick, fontWeight: 600, fontSize: 11, align: 'right' },
          n: { color: c.tooltipText, fontSize: 12 },
        },
      },
    },
    series: [{
      type: 'bar', barMaxWidth: 14, itemStyle: { borderRadius: [0, 6, 6, 0] },
      data: rows.value.map(r => ({
        value: r.count,
        itemStyle: { color: r.others ? c.mutedBar : c.barStart },
      })),
      label: { show: true, position: 'right', color: c.tooltipText, fontSize: 11, fontWeight: 600,
        formatter: (p: any) => {
          const r = rowByName.get(p.name)
          return r?.others ? `${r.count}  ▸` : `${r?.count ?? ''}`
        } },
      animationDuration: 800,
    }],
  }
})

function onPick(params: any) {
  if (params?.componentType !== 'series' || typeof params.name !== 'string') return
  if (params.name.startsWith('其他')) { expanded.value = true; return }
  emit('pick', params.name)
}
</script>

<style scoped>
.rank-bar-wrap { flex: 1 1 0; height: 100%; min-height: 0; display: flex; flex-direction: column; }
.rank-collapse { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; margin-bottom: 4px; align-self: flex-end; border: 1px solid var(--cpq-overlay-a20); border-radius: var(--cpq-radius-full); background: var(--cpq-overlay-a8); color: var(--cpq-accent-primary); font-size: var(--cpq-font-size-xs); cursor: pointer; transition: color var(--cpq-dur-1) var(--cpq-ease-smooth), background-color var(--cpq-dur-1) var(--cpq-ease-smooth), border-color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.rank-collapse:hover { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary); }
.rank-bar { flex: 1 1 0; width: 100%; min-width: 0; min-height: 120px; }
.chart-empty { flex: 1 1 0; display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }
</style>
