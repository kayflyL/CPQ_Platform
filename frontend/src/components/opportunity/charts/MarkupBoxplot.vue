<template>
  <v-chart v-if="boxes.length" class="markup-boxplot" :option="opt" autoresize />
  <div v-else class="chart-empty">{{ emptyText }}</div>
</template>

<script setup lang="ts">
// 加点/利润箱线图（四分位+散点）：线索页「机型利润」与驾驶舱「机型加点分布」共用。
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BoxplotChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, BoxplotChart, ScatterChart, GridComponent, TooltipComponent])

const props = defineProps<{
  boxes: { name: string; min: number; q1: number; median: number; q3: number; max: number; scatter?: number[] }[]
  emptyText?: string
}>()

const { chartColors } = useChartTheme()

const opt = computed(() => {
  const boxes = props.boxes || []
  if (!boxes.length) return {}
  const names = boxes.map(b => b.name)
  const boxData = boxes.map(b => [b.min, b.q1, b.median, b.q3, b.max])
  const scatterData: any[] = []
  boxes.forEach((b, i) => {
    (b.scatter || []).forEach(v => scatterData.push([i, v]))
  })
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText },
      borderColor: c.tooltipBorder, borderWidth: 1,
      formatter: (p: any) => {
        if (p.componentSubType === 'boxplot') {
          const v = p.value
          return `${names[v[0] ?? p.dataIndex]}<br/>最大 <b>${v[5] ?? v[4]}%</b><br/>Q3 <b>${v[4] ?? '-'}%</b><br/>中位 <b>${v[3] ?? '-'}%</b><br/>Q1 <b>${v[2] ?? '-'}%</b><br/>最小 <b>${v[1] ?? '-'}%</b>`
        }
        return `${names[p.value[0]]}<br/>利润率 <b>${p.value[1]}%</b>`
      },
    },
    grid: { left: 44, right: 16, top: 12, bottom: 30 },
    xAxis: {
      type: 'category', data: names, boundaryGap: true,
      axisLine: { lineStyle: { color: c.grid } },
      axisLabel: { color: c.axisLabel, fontSize: 10, rotate: names.length > 4 ? 20 : 0, interval: 0 },
      axisTick: { show: false }, splitLine: { show: false },
    },
    yAxis: {
      type: 'value', name: '利润率%', nameTextStyle: { color: c.axisLabel, fontSize: 10 },
      splitLine: { lineStyle: { color: c.splitLine } },
      axisLabel: { color: c.axisLabel, fontSize: 10, formatter: '{value}%' },
    },
    series: [
      {
        name: '分布', type: 'boxplot', data: boxData,
        itemStyle: { color: c.barStart + '55', borderColor: c.accent, borderWidth: 1.5 },
        animationDuration: 800,
      },
      {
        name: '样本', type: 'scatter', data: scatterData, symbolSize: 5,
        itemStyle: { color: c.accent, opacity: 0.55 },
        animationDuration: 600,
      },
    ],
  }
})
</script>

<style scoped>
.markup-boxplot { width: 100%; height: 100%; min-height: 0; }
.chart-empty { flex: 1 1 0; display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }
</style>
