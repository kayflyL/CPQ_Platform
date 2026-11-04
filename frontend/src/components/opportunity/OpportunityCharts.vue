<template>
  <section class="chart-deck" :class="{ 'personal-chart-deck': !canViewAll }">
    <div v-if="show('trend')" class="chart-card chart-card-trend glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>趋势分析</div>
        <a-segmented v-model:value="trendView" :options="trendOptions" size="small" />
      </div>
      <TrendBarLine
        v-if="trendView === 'opp'"
        class="chart-inner"
        :labels="trendLabels"
        :total="trendTotal"
        :lines="platformLines"
      />
      <ModelTreemap v-else class="chart-inner" :items="modelItems" />
    </div>
    <div v-if="show('dist')" class="chart-card chart-card-dist glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>结构分布</div>
        <a-segmented v-model:value="distView" :options="distOptions" size="small" />
      </div>
      <DonutChart
        v-if="distView === 'platform'"
        class="chart-inner chart-inner-pie"
        :items="structure.platforms"
        :colors="PLAT_COLOR"
        center-total
        @pick="emitDrill('platform', $event)"
      />
      <RoseChart
        v-else
        class="chart-inner chart-inner-pie"
        :items="structure.chassis"
        @pick="emitDrill('chassis', $event)"
      />
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
    <div v-if="canViewAll && show('rank')" class="chart-card chart-card-rank glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>业务排行</div>
      </div>
      <RankBar class="rank-body" :top="rankTop" :others="rankOthers" :others-list="rankOthersList" />
    </div>
    <div v-if="canViewAll && show('won')" class="chart-card chart-card-won glass">
      <div class="deck-header">
        <div class="deck-title"><span class="deck-line"></span>线索转化</div>
        <a-segmented v-model:value="wonView" :options="wonOptions" size="small" />
      </div>
      <div class="won-branch">
        <ConversionTable
          v-if="wonView === 'won'"
          :top="rankTop"
          :others="rankOthers"
          :others-list="rankOthersList"
        />
        <MarkupBoxplot
          v-else
          class="profit-box-wrap"
          :boxes="profitBoxes"
          empty-text="暂无机型利润数据（需报价单填机型型号+利润率）"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 商机线索页左栏图表组：组合层（布局/卡片头/切换）。
// 图表本体在 components/opportunity/charts/ 下为共享组件，商机驾驶舱同源复用；
// 「线索转化」卡头带管理员齿轮：配置哪些图表在本栏展示（system_config opportunity.leads_charts）。
import { computed, ref } from 'vue'
import TrendBarLine from '@/components/opportunity/charts/TrendBarLine.vue'
import ModelTreemap from '@/components/opportunity/charts/ModelTreemap.vue'
import DonutChart from '@/components/opportunity/charts/DonutChart.vue'
import RoseChart from '@/components/opportunity/charts/RoseChart.vue'
import RankBar from '@/components/opportunity/charts/RankBar.vue'
import ConversionTable from '@/components/opportunity/charts/ConversionTable.vue'
import MarkupBoxplot from '@/components/opportunity/charts/MarkupBoxplot.vue'
import { PLAT_COLOR } from '@/constants/platform'

interface ChartSummary {
  period_label: string
  kpi: Record<string, any>
  charts: Record<string, any>
  structure: any
  dates: any[]
}

const props = withDefaults(defineProps<{
  summary: ChartSummary
  canViewAll: boolean
  tableTotal: number
  recentOpps: Array<{ id: string; name: string; platform: string }>
  isMobile: boolean
  /** 展示哪些卡：trend/dist/rank/won（管理员经齿轮配置，system_config 持久化） */
  visibleCharts?: string[]
}>(), { visibleCharts: () => ['trend', 'dist', 'rank', 'won'] })

const emit = defineEmits<{
  (e: 'drill-on', type: string, name: string): void
  (e: 'open-list-drawer'): void
}>()

const show = (id: string) => props.visibleCharts.includes(id)

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

/* 趋势卡数据 */
const trendLabels = computed(() => (props.summary.charts?.chart1?.total_series || [])
  .map((d: any) => (d.date.length === 7 ? d.date : d.date.slice(5))))
const trendTotal = computed(() => (props.summary.charts?.chart1?.total_series || []).map((d: any) => d.value))
const platformLines = computed(() =>
  Object.entries(props.summary.charts?.chart1?.platform_series || {}).map(([name, vals]) => ({
    name,
    data: (vals as any[]).map((d: any) => d.value),
    color: PLAT_COLOR[name] || '#6B7280',
  }))
)
const modelItems = computed(() => {
  const rows = props.summary.charts?.chart2?.data || []
  const totals: Record<string, number> = {}
  for (const row of rows) {
    const pn = row[2], cnt = Number(row[1]) || 0
    totals[pn] = (totals[pn] || 0) + cnt
  }
  return Object.entries(totals)
    .map(([name, value]) => [name, value] as [string, number])
    .sort((a, b) => b[1] - a[1])
})

/* 排行/转化卡数据 */
const rankTop = computed(() => (props.summary as any)?.sales_rank?.top || [])
const rankOthers = computed(() => (props.summary as any)?.sales_rank?.others || null)
const rankOthersList = computed(() => (props.summary as any)?.sales_rank?.others_list || [])
const profitBoxes = computed(() => props.summary.charts?.chart5?.boxes || [])

function emitDrill(type: string, name: string) {
  emit('drill-on', type, name)
}
</script>

<style scoped>
/* 左栏单列堆叠：每张卡占满栏宽、纵向排列，整栏上下滑动（移动端保留网格） */
.chart-deck { display: flex; flex-direction: column; gap: 12px; padding: 2px 2px 6px; }
.chart-card { flex: none; width: 100%; height: 276px; padding: 14px 16px; border-radius: var(--cpq-radius-lg); display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
.won-branch { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.profit-box-wrap { flex: 1 1 0; min-height: 0; }
.deck-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex: none; }
.deck-title { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); letter-spacing: 0.5px; }
.deck-line { flex: 1; height: 1px; background: linear-gradient(90deg, var(--cpq-overlay-a15), transparent); }
.rank-toggle { display: inline-flex; align-items: center; padding: 2px 8px; border: 1px solid var(--cpq-overlay-a20); border-radius: var(--cpq-radius-full); background: var(--cpq-overlay-a8); color: var(--cpq-accent-primary); font-size: var(--cpq-font-size-xs); cursor: pointer; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.rank-toggle:hover { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary); }
.chart-inner { flex: 1 1 0; width: 100%; min-width: 0; min-height: 120px; }
.chart-inner-pie { cursor: pointer; }
.rank-body { flex: 1 1 0; min-height: 0; }

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
  .chart-card { height: auto; min-height: 0; border-radius: var(--cpq-radius-sm); padding: 12px 14px; }
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
    padding: 12px 14px; border-radius: var(--cpq-radius-sm);
    color: var(--cpq-text-primary); text-align: left;
  }
  .list-tile-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--cpq-text-secondary); flex: none; }
  .lt-count { font-size: 10px; font-weight: 600; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a10); padding: 0 6px; border-radius: var(--cpq-radius-full); }
  .list-tile-preview { display: flex; flex-direction: column; gap: 5px; min-height: 0; overflow: hidden; }
  .lt-item { display: flex; align-items: baseline; gap: 6px; line-height: 1.3; }
  .lt-name { flex: 1 1 0; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
  .lt-plat { flex: none; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary); opacity: 0.6; }
  .lt-empty { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); font-style: italic; }
}
</style>
