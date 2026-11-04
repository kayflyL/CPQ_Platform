<template>
  <v-chart class="rose-chart" :option="opt" autoresize @click="onPick" />
</template>

<script setup lang="ts">
// 玫瑰图（半径=条数）：机箱形态/未成单原因共用。
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent])

const PIE_COLORS = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#FA8C16', '#52C41A', '#86909c']

const props = defineProps<{
  items: { name: string; count: number }[]
  /** 首项高亮色（如丢标首因红），其余按调色板 */
  highlightFirst?: boolean
  clickable?: boolean
}>()

const emit = defineEmits<{ (e: 'pick', name: string): void }>()

const { chartColors } = useChartTheme()

const opt = computed(() => {
  const data = props.items || []
  if (data.length === 0) return {}
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText }, borderColor: c.tooltipBorder, borderWidth: 1 },
    legend: { bottom: 2, type: 'scroll', textStyle: { color: c.axisLabel, fontSize: 10 }, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    series: [{
      type: 'pie', roseType: 'radius', radius: ['18%', '72%'], center: ['50%', '42%'],
      label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: c.segmentBorder, borderWidth: 2, borderRadius: 3 },
      data: data.map((d, i) => ({
        name: d.name || '未分类', value: d.count,
        itemStyle: { color: props.highlightFirst && i === 0 ? '#FF6B6B' : PIE_COLORS[i % PIE_COLORS.length] },
      })),
      animationDuration: 900,
    }],
  }
})

function onPick(p: any) {
  if (props.clickable !== false && p?.name) emit('pick', p.name)
}
</script>

<style scoped>
.rose-chart { width: 100%; height: 100%; min-height: 0; cursor: pointer; }
</style>
