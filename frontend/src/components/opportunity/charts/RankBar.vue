<template>
  <div class="rank-bar-wrap">
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
import { GridComponent, TooltipComponent } from 'echarts/components'
import { useChartTheme } from '@/composables/useChartTheme'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent])

interface RankItem { name: string; count: number; won?: number }

const props = defineProps<{
  top: RankItem[]
  others?: { count: number; people: number } | null
  othersList?: RankItem[]
}>()

const emit = defineEmits<{ (e: 'pick', name: string): void }>()

const expanded = ref(false)
const { chartColors } = useChartTheme()

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
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText },
      borderColor: c.tooltipBorder, borderWidth: 1,
      formatter: (params: any) => {
        const r = rows.value[params[0].dataIndex]
        const won = r.won != null ? ` · 成单 <b>${r.won}</b>` : ''
        const hint = r.others ? '<br/><span style="color:#86909c">点击展开</span>' : ''
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
        formatter: (_v: string, i: number) => `{${i < 3 ? 'rt' : 'rm'}|${i + 1}}  {n|${rows.value[i].name}}`,
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
        itemStyle: { color: r.others
          ? c.mutedBar
          : { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: c.barEnd }, { offset: 1, color: c.barStart }] } },
      })),
      label: { show: true, position: 'right', color: c.tooltipText, fontSize: 11, fontWeight: 600,
        formatter: (p: any) => {
          const r = rows.value[p.dataIndex]
          return r.others ? `${r.count}  ▸` : `${r.count}`
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
.rank-bar-wrap { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.rank-bar { flex: 1 1 0; width: 100%; min-width: 0; min-height: 120px; }
.chart-empty { flex: 1 1 0; display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }
</style>
