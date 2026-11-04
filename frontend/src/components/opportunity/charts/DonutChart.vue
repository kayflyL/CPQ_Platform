<template>
  <v-chart class="donut-chart" :option="opt" autoresize @click="onPick" />
</template>

<script setup lang="ts">
// 环形占比图（可带中心总数）：平台结构/订单类型/新老客户等共用。
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent, TitleComponent])

const FALLBACK_PALETTE = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#6B7280']

const props = defineProps<{
  items: { name: string; count: number }[]
  /** name→色 映射（如 PLAT_COLOR）；未命中的按调色板顺序取色 */
  colors?: Record<string, string>
  centerTotal?: boolean
  clickable?: boolean
}>()

const emit = defineEmits<{ (e: 'pick', name: string): void }>()

const { chartColors } = useChartTheme()

const opt = computed(() => {
  const data = (props.items || []).map(p => ({ name: p.name || '未分类', value: p.count }))
  if (data.length === 0) return {}
  const total = data.reduce((s, d) => s + d.value, 0)
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText }, borderColor: c.tooltipBorder, borderWidth: 1 },
    legend: { bottom: 2, type: 'scroll', textStyle: { color: c.axisLabel, fontSize: 10 }, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    ...(props.centerTotal ? { title: { text: total + '', subtext: '总数', left: 'center', top: '34%', textStyle: { fontSize: 26, fontWeight: 700, color: c.tooltipText }, subtextStyle: { fontSize: 10, color: c.axisLabel } } } : {}),
    series: [{
      type: 'pie', radius: ['52%', '72%'], center: ['50%', props.centerTotal ? '44%' : '42%'],
      avoidLabelOverlap: false, label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: c.segmentBorder, borderWidth: 2 },
      data: data.map((d, i) => ({ ...d, itemStyle: { color: (props.colors && props.colors[d.name]) || FALLBACK_PALETTE[i % FALLBACK_PALETTE.length] } })),
      animationType: 'expansion', animationDuration: 900,
    }],
  }
})

function onPick(p: any) {
  if (props.clickable !== false && p?.name) emit('pick', p.name)
}
</script>

<style scoped>
.donut-chart { width: 100%; height: 100%; min-height: 0; cursor: pointer; }
</style>
