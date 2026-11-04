<template>
  <v-chart class="trend-bar-line" :option="opt" autoresize @click="onPick" />
</template>

<script setup lang="ts">
// 商机趋势（柱=总量 + 折线系列）：商机线索页「趋势分析」与驾驶舱「月度趋势/新增vs成单」共用。
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

const props = defineProps<{
  labels: string[]
  total: number[]
  /** 附加折线系列（平台线/成单线），颜色由调用方给定 */
  lines?: { name: string; data: number[]; color: string }[]
}>()

const emit = defineEmits<{ (e: 'pickLabel', label: string): void }>()

const { chartColors } = useChartTheme()

const opt = computed(() => {
  if (!props.labels?.length) return {}
  const c = chartColors.value
  const lineSeries = (props.lines || []).map(l => ({
    name: l.name, type: 'line', smooth: true, symbol: 'circle', symbolSize: 4, showSymbol: false,
    lineStyle: { width: 2, color: l.color }, itemStyle: { color: l.color },
    emphasis: { focus: 'series' }, data: l.data,
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText }, borderColor: c.tooltipBorder, borderWidth: 1 },
    legend: { top: 0, textStyle: { color: c.axisLabel, fontSize: 10 }, padding: [0, 0, 8, 0], icon: 'roundRect', itemWidth: 12, itemHeight: 2 },
    grid: { left: 40, right: 16, bottom: 28, top: 32 },
    xAxis: { type: 'category', boundaryGap: false, data: props.labels, axisLine: { lineStyle: { color: c.grid } }, axisLabel: { color: c.axisLabel, fontSize: 10, rotate: (props.labels[0] || '').length === 7 ? 0 : 30 }, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: c.splitLine } }, axisLabel: { color: c.axisLabel, fontSize: 10 } },
    series: [
      { name: '商机总量', type: 'bar', barWidth: '46%', itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: c.barStart }, { offset: 1, color: c.barEnd }] }, borderRadius: [4, 4, 0, 0] }, data: props.total, animationDuration: 1000 },
      ...lineSeries,
    ],
  }
})

function onPick(p: any) {
  if (p?.componentSubType === 'bar' && typeof p.name === 'string') emit('pickLabel', p.name)
}
</script>

<style scoped>
.trend-bar-line { width: 100%; height: 100%; min-height: 0; }
</style>
