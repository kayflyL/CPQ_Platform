<template>
  <v-chart class="model-treemap" :option="opt" autoresize @click="onPick" />
</template>

<script setup lang="ts">
// 机型热度树图（矩形面积=报价次数）：商机线索页「机型趋势」与驾驶舱「机型热度」共用。
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { TreemapChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, TreemapChart, TooltipComponent])

const MODEL_COLORS = ['#1677FF', '#36CFCF', '#5B8FF9', '#722ED1', '#a855f7', '#FF3B5C', '#FA8C16', '#52C41A', '#6B7280']

const props = defineProps<{
  /** [机型PN, 次数] 降序 */
  items: [string, number][]
}>()

const emit = defineEmits<{ (e: 'pick', name: string): void }>()

const { chartColors } = useChartTheme()

const opt = computed(() => {
  const data = props.items
  if (!Array.isArray(data) || data.length === 0) return {}
  const total = data.reduce((s, d) => s + d[1], 0)
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText },
      borderColor: c.tooltipBorder, borderWidth: 1,
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
      itemStyle: { borderColor: c.segmentBorder, borderWidth: 2, gapWidth: 3 },
      levels: [{ itemStyle: { borderColor: c.segmentBorder, borderWidth: 2, gapWidth: 3 } }],
      data: data.map((d, i) => ({
        name: d[0], value: d[1],
        itemStyle: { color: MODEL_COLORS[i % MODEL_COLORS.length] },
      })),
      animationDuration: 700,
    }],
  }
})

function onPick(p: any) {
  if (p?.componentSubType === 'treemap' && typeof p.name === 'string') emit('pick', p.name)
}
</script>

<style scoped>
.model-treemap { width: 100%; height: 100%; min-height: 0; }
</style>
