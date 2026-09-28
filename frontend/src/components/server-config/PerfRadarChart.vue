<script setup lang="ts">
/** 性能六维雷达（配置页右栏）— echarts radar，形状承原型 docs/原型/配置页-性能六维雷达-原型.html。
 *  缺数据维度顶点缩到圆心 + 灰标「未维护」（不编造）；配色走 useChartTheme 真实色值
 *  （canvas 读不到 CSS 变量）；维度 chip hover 出打分明细 popover（echarts 轴名不可交互，chip 代替）。 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartTheme } from '@/composables/useChartTheme'
import type { PerfDimResult } from '@/utils/performanceScore'

echarts.use([RadarChart, CanvasRenderer])

const props = defineProps<{ dims: PerfDimResult[] }>()
const { chartColors } = useChartTheme()

const el = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null

function render() {
  if (!el.value || !chart) return
  const c = chartColors.value
  const dims = props.dims
  chart.setOption({
    radar: {
      center: ['50%', '52%'],
      radius: '58%',
      splitNumber: 5,
      indicator: dims.map(d => ({
        // 轴名 rich 文本：维度名 + 得分；缺数据灰标「未维护」
        name: d.score == null ? `{n|${d.label}} {m|未维护}` : `{n|${d.label}} {s|${d.score}}`,
        max: 100,
      })),
      axisName: {
        rich: {
          n: { color: c.axisLabel, fontSize: 11.5, padding: [0, 2, 0, 0] },
          s: { color: c.accent, fontSize: 11.5, fontWeight: 700 },
          m: { color: c.tick, fontSize: 10, fontStyle: 'italic' },
        },
      },
      axisLine: { lineStyle: { color: c.splitLine } },
      splitLine: { lineStyle: { color: c.splitLine } },
      splitArea: { show: false },
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 4,
      data: [{
        value: dims.map(d => d.score ?? 0),
        lineStyle: { color: c.accent, width: 2 },
        areaStyle: { color: c.accentFill },
        itemStyle: { color: c.accent },
      }],
    }],
  })
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  ro = new ResizeObserver(() => chart?.resize())
  ro.observe(el.value)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.dims, render, { deep: true })
watch(chartColors, render)
</script>

<template>
  <div class="perf-radar">
    <div ref="el" class="radar-canvas"></div>
    <div class="radar-chips">
      <a-popover v-for="d in dims" :key="d.key" placement="top" trigger="hover">
        <template #content>
          <div class="chip-pop">
            <div class="chip-pop-raw" v-if="d.rawText">{{ d.rawText }}</div>
            <div class="chip-pop-detail">{{ d.detail }}</div>
          </div>
        </template>
        <button type="button" class="chip" :class="{ miss: d.score == null }">
          {{ d.label }}<b>{{ d.score == null ? '—' : d.score }}</b>
        </button>
      </a-popover>
    </div>
  </div>
</template>

<style scoped>
.perf-radar { display: flex; flex-direction: column; gap: 8px; }
.radar-canvas { width: 100%; height: 240px; }

.radar-chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 9px; font-size: 11px; cursor: default;
  color: var(--cpq-text-secondary, #9BA1AA);
  background: var(--cpq-overlay-b20);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 999px;
}
.chip b { font-size: 12px; font-weight: 800; color: var(--cpq-accent-primary, #1677ff); }
.chip.miss b { color: var(--cpq-text-muted, #6E7582); font-weight: 400; }

.chip-pop { max-width: 240px; font-size: 12px; line-height: 1.7; }
.chip-pop-raw { font-weight: 700; margin-bottom: 2px; }
.chip-pop-detail { color: var(--cpq-text-secondary, #9BA1AA); font-size: 11px; }
</style>
