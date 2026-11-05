<template>
  <div class="cockpit-page">
    <!-- 吸顶单条：标题 + 周期/自定义区间 + 维度筛选（滑动常驻）+ 下钻片 -->
    <div class="ck-top">
      <div class="glass-strong ck-bar">
        <h1 class="ck-title">商机驾驶舱</h1>
        <span class="ck-sub">{{ rangeLabel }}<template v-if="data?.generated_at"> · 生成于 {{ data.generated_at }}</template></span>
        <div class="period-toggle">
          <span v-for="p in PERIODS" :key="p.value" class="period-option" :class="{ active: isPeriodActive(p.value) }" @click="setPeriod(p.value)">
            <span class="period-dot" />{{ p.label }}
          </span>
        </div>
        <a-popover v-model:open="rangeOpen" trigger="click" placement="bottomRight" overlay-class-name="cockpit-range-pop">
          <template #content>
            <div class="range-pop">
              <div class="range-sec">快捷区间</div>
              <div class="preset-grid">
                <button v-for="ps in PRESETS" :key="ps.key" class="preset-btn" :class="{ active: custom?.key === ps.key }" @click="applyPreset(ps)">{{ ps.label }}</button>
              </div>
              <div class="range-sec">指定月份</div>
              <a-date-picker v-model:value="monthValue" picker="month" size="small" placeholder="选择月份" value-format="YYYY-MM" @change="onMonthChange" />
              <div class="range-sec">自定义区间</div>
              <div class="range-inputs">
                <a-range-picker v-model:value="rangeValue" size="small" value-format="YYYY-MM-DD" @change="onRangeChange" />
              </div>
            </div>
          </template>
          <button class="range-btn" :class="{ on: !!custom }">{{ custom ? custom.label : '自定义' }} ▾</button>
        </a-popover>
        <span class="bar-divider" />
        <a-select v-model:value="filters.result" style="width: 104px" size="small" @change="load">
          <a-select-option value="">全部状态</a-select-option>
          <a-select-option value="pending">进行中</a-select-option>
          <a-select-option value="won">已中标</a-select-option>
          <a-select-option value="lost">已丢标</a-select-option>
          <a-select-option value="expired">已过期</a-select-option>
        </a-select>
        <a-select v-model:value="filters.platform" mode="multiple" placeholder="平台" :max-tag-count="1" style="min-width: 120px" size="small" :options="platformOptions" @change="load" />
        <a-select v-model:value="filters.chassis" mode="multiple" placeholder="形态" :max-tag-count="1" style="min-width: 104px" size="small" :options="chassisOptions" @change="load" />
        <a-select v-if="canViewAll" v-model:value="filters.sales" mode="multiple" placeholder="业务" :max-tag-count="1" style="min-width: 112px" size="small" :options="salesOptions" @change="load" />
        <a-input v-model:value="filters.customer" class="cust-search" placeholder="搜索客户" size="small" allow-clear @input="debounceLoad" />
        <button class="f-reset" @click="resetAll">重置</button>
      </div>
      <div class="ck-chips">
        <span v-if="!chipList.length" class="ck-hint">点击任意图表元素也可下钻，与上方筛选叠加生效</span>
        <span v-for="c in chipList" :key="c.dim + c.val" class="f-chip" @click="removeChip(c)">
          <i class="dim">{{ DIM_LABEL[c.dim] || c.dim }}</i>{{ c.val }}<b>✕</b>
        </span>
      </div>
    </div>

    <!-- 常态区：环形 Hero + 两侧卡（切 Tab 不动，仅随筛选刷新） -->
    <div class="hero-grid">
      <div class="kpi-col">
        <div v-for="k in heroKpisLeft" :key="k.label" class="kpi glass-light">
          <div class="kpi-l">{{ k.label }}</div>
          <div class="kpi-v">{{ k.v }}<small>{{ k.unit }}</small></div>
          <div class="kpi-stats">
            <div v-for="st in k.stats" :key="st.label" class="kpi-stat">
              <span class="ks-l">{{ st.label }}</span>
              <span class="ks-v">{{ st.value }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="glass hero">
        <div class="hchips">
          <div v-for="c in resultChips" :key="c.label" class="hchip">
            <span class="hicon" :style="{ background: c.tint, color: c.color }">{{ c.glyph }}</span>
            <span class="ht"><span class="hl">{{ c.label }}</span><span class="hv">{{ c.value }}</span></span>
            <span class="hp">{{ c.pct }}</span>
          </div>
        </div>
        <div class="hero-ring">
          <svg viewBox="0 0 200 200">
            <defs>
              <linearGradient id="ckRingGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#1677FF" /><stop offset="1" stop-color="#36CFCF" />
              </linearGradient>
            </defs>
            <circle cx="100" cy="100" r="84" fill="none" stroke="rgba(22,119,255,.10)" stroke-width="13" />
            <circle cx="100" cy="100" r="84" fill="none" stroke="rgba(22,119,255,.10)" stroke-width="13" stroke-dasharray="2 10" stroke-linecap="round" />
            <circle cx="100" cy="100" r="84" fill="none" stroke="url(#ckRingGrad)" stroke-width="13" stroke-linecap="round"
              :stroke-dasharray="RING_C" :stroke-dashoffset="ringOffset" transform="rotate(-90 100 100)" />
          </svg>
          <div class="ring-center">
            <div class="rc-lab">商机总量</div>
            <div class="rc-big">{{ kpi.total_opportunities }}</div>
            <div class="rc-sub">成单 <b>{{ kpi.won }}</b> · 成单率 <b>{{ kpi.win_rate }}%</b></div>
          </div>
        </div>
        <div class="hchips">
          <div v-for="c in assetChips" :key="c.label" class="hchip">
            <span class="hicon" :style="{ background: c.tint, color: c.color }">{{ c.glyph }}</span>
            <span class="ht"><span class="hl">{{ c.label }}</span><span class="hv">{{ c.value }}</span></span>
            <span class="hp">{{ c.pct }}</span>
          </div>
        </div>
      </div>
      <div class="kpi-col">
        <div v-for="k in heroKpisRight" :key="k.label" class="kpi glass-light">
          <div class="kpi-l">{{ k.label }}</div>
          <div class="kpi-v">{{ k.v }}<small>{{ k.unit }}</small></div>
          <div class="kpi-stats">
            <div v-for="st in k.stats" :key="st.label" class="kpi-stat">
              <span class="ks-l">{{ st.label }}</span>
              <span class="ks-v">{{ st.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 内容区板块切换 -->
    <nav class="tabs glass-strong">
      <button v-for="t in TABS" :key="t.key" class="tab" :class="{ active: activeTab === t.key }" @click="switchTab(t.key)">
        <span class="tdot" />{{ t.label }}
      </button>
    </nav>

    <!-- 加载失败：明示错误与重试，绝不静默渲染全 0（多为后端未重启/网络问题） -->
    <div v-if="loadError && !data" class="load-error glass-strong">
      <div class="le-text">⚠️ {{ loadError }}</div>
      <button class="f-reset" @click="load">重试</button>
    </div>
    <a-spin v-else :spinning="loading">
      <!-- 总览：月度趋势 + 机型热度 -->
      <section v-if="visited.kpi" v-show="activeTab === 'kpi'" class="panel">
        <div class="conclusion" v-html="conKpi" />
        <div class="glass card-block">
          <div class="card-head">月度趋势<span class="note">近12月 · 柱=商机总量 · 线=主力平台 · 点柱=切到该月</span></div>
          <div class="chart-wide"><TrendBarLine :labels="monthLabels" :total="monthTotals" :lines="monthPlatformLines" @pick-label="onMonthLabelPick" /></div>
        </div>
        <div class="glass card-block">
          <div class="card-head">机型热度<span class="note">矩形面积=报价次数 · 独占整行 · 点击下钻</span></div>
          <div class="chart-big"><ModelTreemap :items="modelItems" @pick="(n: string) => setFilter('pn', n)" /></div>
        </div>
      </section>

      <!-- 产品结构 -->
      <section v-if="visited.product" v-show="activeTab === 'product'" class="panel">
        <div class="stats">
          <div v-for="s in productStats" :key="s.label" class="glass stat" :class="'tint-' + s.tint">
            <span class="sicon">{{ s.glyph }}</span>
            <span class="st"><span class="sl">{{ s.label }}</span><span class="sv">{{ s.cur }}<small>{{ s.unit }}</small></span></span>
            <span class="sp">同期 <b>{{ s.prev }}</b><br><i v-if="s.delta" class="delta2" :class="s.delta.cls">{{ s.delta.text }}</i></span>
          </div>
        </div>
        <div class="conclusion" v-html="conProduct" />
        <div class="grid4" style="margin-bottom: var(--cpq-space-4)">
          <div class="glass card-block"><div class="card-head">平台结构<span class="note">点击下钻</span></div>
            <div class="chart-mini"><DonutChart :items="structure.platforms" :colors="PLAT_COLOR" center-total @pick="(n: string) => setFilter('platform', n)" /></div></div>
          <div class="glass card-block"><div class="card-head">机箱形态<span class="note">点击下钻</span></div>
            <div class="chart-mini"><RoseChart :items="structure.chassis" :colors="CHAS_COLORS" @pick="(n: string) => setFilter('chassis', n)" /></div></div>
          <div class="glass card-block"><div class="card-head">行业分布<span class="note">点击下钻</span></div>
            <v-chart class="chart-mini" :option="industryOpt" autoresize @click="(p: any) => onDimClick('industry', p)" /></div>
          <div class="glass card-block"><div class="card-head">订单类型<span class="note">点击下钻</span></div>
            <div class="chart-mini"><DonutChart :items="structure.otype" clickable @pick="(n: string) => setFilter('otype', n)" /></div></div>
        </div>
        <div class="glass card-block">
          <div class="card-head">机型加点分布<span class="note">报价加点%（非成单利润） · 箱线=四分位 · 与成单率关系见「成单与输单」</span></div>
          <div class="chart-tall"><MarkupBoxplot :boxes="markupBoxes" /></div>
        </div>
      </section>

      <!-- 人员与转化 -->
      <section v-if="canViewAll && visited.people" v-show="activeTab === 'people'" class="panel">
        <div class="stats">
          <div v-for="s in peopleStats" :key="s.label" class="glass stat" :class="'tint-' + s.tint">
            <span class="sicon">{{ s.glyph }}</span>
            <span class="st"><span class="sl">{{ s.label }}</span><span class="sv">{{ s.cur }}<small>{{ s.unit }}</small></span></span>
            <span class="sp">同期 <b>{{ s.prev }}</b><br><i v-if="s.delta" class="delta2" :class="s.delta.cls">{{ s.delta.text }}</i></span>
          </div>
        </div>
        <div class="conclusion" v-html="conPeople" />
        <div class="grid2">
          <div class="glass card-block"><div class="card-head">业务排行<span class="note">按商机数 · 点「其他」展开 · 点人名下钻</span></div>
            <div class="chart-tall"><RankBar :top="rankTop" :others="rankOthers" :others-list="rankOthersList" @pick="(n: string) => setFilter('sales', n)" /></div></div>
          <div class="glass card-block">
            <div class="card-head">线索转化<span class="note">当前筛选 · 成交率着色</span></div>
            <div class="chart-tall"><ConversionTable :top="rankTop" :others="rankOthers" :others-list="rankOthersList" /></div>
          </div>
        </div>
      </section>

      <!-- 成单与输单 -->
      <section v-if="visited.win" v-show="activeTab === 'win'" class="panel">
        <div class="stats">
          <div v-for="s in winStats" :key="s.label" class="glass stat" :class="'tint-' + s.tint">
            <span class="sicon">{{ s.glyph }}</span>
            <span class="st"><span class="sl">{{ s.label }}</span><span class="sv">{{ s.cur }}<small>{{ s.unit }}</small></span></span>
            <span class="sp">同期 <b>{{ s.prev }}</b><br><i v-if="s.delta" class="delta2" :class="s.delta.cls">{{ s.delta.text }}</i></span>
          </div>
        </div>
        <div class="conclusion" v-html="conWin" />
        <div class="glass card-block" style="margin-bottom: var(--cpq-space-4)">
          <div class="card-head">新增 vs 成单<span class="note">近12月 · 柱=新增商机 · 线=当月成单 · 点柱=切到该月</span></div>
          <div class="chart-wide"><TrendBarLine :labels="monthLabels" :total="monthTotals" :lines="wonLine" @pick-label="onMonthLabelPick" /></div>
        </div>
        <div class="grid2" style="margin-bottom: var(--cpq-space-4)">
          <div class="glass card-block">
            <div class="card-head">制胜因子<span class="note">成单归因 · 横条=单数 · 字典与状态变更弹窗共用</span></div>
            <v-chart v-if="winReasonOpt.series" class="chart" :option="winReasonOpt" autoresize />
            <div v-else class="chart-empty">暂无制胜因子数据——中标时在状态变更弹窗选填「制胜因子」后此处开始积累</div>
          </div>
          <div class="glass card-block">
            <div class="card-head">加点 × 成单率<span class="note">报价加点分箱 · 柱=报价次数 · 线=成单率 · 回答「加几个点成单率高」</span></div>
            <v-chart class="chart" :option="markupWinOpt" autoresize />
          </div>
        </div>
        <div class="grid3" style="margin-bottom: var(--cpq-space-4)">
          <div class="glass card-block"><div class="card-head">成单机型<span class="note">柱=成单数 · 线=成单平均加点%</span></div>
            <v-chart class="chart" :option="wonModelOpt" autoresize /></div>
          <div class="glass card-block"><div class="card-head">成单时效<span class="note">建档→成单天数 · 中位/P90 见提示</span></div>
            <v-chart class="chart" :option="cycleOpt" autoresize /></div>
          <div class="glass card-block"><div class="card-head">新老客户构成<span class="note">成单客户首单月=成单月记「新客户」</span></div>
            <div class="chart"><DonutChart :items="wonCustItems" :colors="WON_CUST_COLORS" center-total :clickable="false" /></div></div>
        </div>
        <div class="glass card-block">
          <div class="card-head">未成单原因<span class="note">丢标+过期 · 玫瑰半径=条数 · 动态关联状态变更归因字典</span></div>
          <div class="chart-tall"><RoseChart v-if="lossReasonItems.length" :items="lossReasonItems" highlight-first :clickable="false" />
            <div v-else class="chart-empty">暂无丢标/过期归因数据</div></div>
        </div>
      </section>

      <!-- 客户与地区 -->
      <section v-if="visited.region" v-show="activeTab === 'region'" class="panel">
        <div class="stats">
          <div v-for="s in regionStats" :key="s.label" class="glass stat" :class="'tint-' + s.tint">
            <span class="sicon">{{ s.glyph }}</span>
            <span class="st"><span class="sl">{{ s.label }}</span><span class="sv">{{ s.cur }}<small>{{ s.unit }}</small></span></span>
            <span class="sp">同期 <b>{{ s.prev }}</b><br><i v-if="s.delta" class="delta2" :class="s.delta.cls">{{ s.delta.text }}</i></span>
          </div>
        </div>
        <div class="conclusion" v-html="conRegion" />
        <div class="glass card-block" style="margin-bottom: var(--cpq-space-4)">
          <div class="card-head">地区分布
            <span style="flex: 1" />
            <span class="map-toggle">
              <button :class="{ active: mapMode === 'world' }" @click="switchMapMode('world')">世界</button>
              <button :class="{ active: mapMode === 'china' }" @click="switchMapMode('china')">国内</button>
            </span>
          </div>
          <div class="card-head-sub" style="margin: calc(-1 * var(--cpq-space-2)) 0 var(--cpq-space-3); font-weight: 400">
            {{ mapMode === 'china' ? '按客户名关键词推断的省份口径 · 点省份下钻 · 未识别地区不在图上（客户排行仍可见）' : '按客户名关键词识别国家 · 库中无国家字段，仅客户名含国名时上图；海外未定位的不计入' }}
          </div>
          <div v-if="mapReady" class="chart-big">
            <v-chart :option="mapOpt" autoresize @click="(p: any) => onMapClick(p)" />
          </div>
          <div v-else class="chart-empty">地图加载中…</div>
        </div>
        <div class="glass card-block">
          <div class="card-head">客户排行<span class="note">Top15 · 按商机数 · 绿条=含成单 · 点客户名下钻</span></div>
          <v-chart class="chart-tall" :option="custOpt" autoresize @click="(p: any) => onDimClick('customer', p)" />
        </div>
      </section>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
// 商机驾驶舱正式页 —— 原型 docs/prototypes/商机驾驶舱-原型.html 的实装。
// 数据源 /api/dashboard/cockpit（同 opp_stats 口径）；常态区 Hero 切 Tab 不动；全维度点击下钻走服务端筛选。
import { computed, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts/core'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, MapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import dayjs from 'dayjs'
import axios from 'axios'
import { useChartTheme } from '@/composables/useChartTheme'
import { useAuthStore } from '@/store/auth'
import { PLAT_COLOR } from '@/constants/platform'
import TrendBarLine from '@/components/opportunity/charts/TrendBarLine.vue'
import ModelTreemap from '@/components/opportunity/charts/ModelTreemap.vue'
import DonutChart from '@/components/opportunity/charts/DonutChart.vue'
import RoseChart from '@/components/opportunity/charts/RoseChart.vue'
import RankBar from '@/components/opportunity/charts/RankBar.vue'
import ConversionTable from '@/components/opportunity/charts/ConversionTable.vue'
import MarkupBoxplot from '@/components/opportunity/charts/MarkupBoxplot.vue'

use([CanvasRenderer, LineChart, BarChart, MapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent])

defineOptions({ name: 'OpportunityCockpit' })

const auth = useAuthStore()
const canViewAll = computed(() => auth.can('page.opportunities_all'))
const { chartColors } = useChartTheme()

const RING_C = 527.8
const PERIODS = [
  { value: 'week', label: '本周' },
  { value: 'month', label: '本月' },
  { value: 'year', label: '本年' },
  { value: 'all', label: '全部' },
]
const PRESETS = [
  { key: 'lastWeek', label: '上周' },
  { key: 'lastMonth', label: '上月' },
  { key: 'lastYear', label: '去年' },
  { key: 'last30', label: '近30天' },
  { key: 'last90', label: '近90天' },
]
const TABS = computed(() => [
  { key: 'kpi', label: '总览' },
  { key: 'product', label: '产品结构' },
  ...(canViewAll.value ? [{ key: 'people', label: '人员与转化' }] : []),
  { key: 'win', label: '成单与输单' },
  { key: 'region', label: '客户与地区' },
])
const DIM_LABEL: Record<string, string> = {
  platform: '平台', chassis: '形态', industry: '行业', otype: '订单类型',
  pn: '机型', sales: '业务', customer: '客户', province: '省份',
}
// 机箱形态着色（与后端 CHAS_COLORS 一致；JS 图表读不到 CSS 变量，用真实色值）
const CHAS_COLORS: Record<string, string> = { '2U': '#26E2D1', '4U': '#FA8C16', '4.5U': '#1890FF', '5U': '#A855F7', '8U': '#8A94A8', '工作站': '#A855F7' }
const RESULT_META = [
  { key: 'pending', label: '进行中', glyph: '进', color: '#1677FF' },
  { key: 'won', label: '已中标', glyph: '成', color: '#52C9A0' },
  { key: 'lost', label: '已丢标', glyph: '丢', color: '#FF6B6B' },
  { key: 'expired', label: '已过期', glyph: '期', color: '#8A94A8' },
]

/* ── 状态 ── */
const loading = ref(false)
const data = ref<any>(null)
const activeTab = ref('kpi')
const visited = reactive<Record<string, boolean>>({ kpi: true })
const period = ref('year')
const custom = ref<{ key: string; start: string; end: string; label: string } | null>(null)
const rangeOpen = ref(false)
const monthValue = ref<any>(null)
const rangeValue = ref<any>(null)
const filters = reactive({
  result: '', platform: [] as string[], chassis: [] as string[], sales: [] as string[],
  industry: [] as string[], otype: [] as string[], pn: [] as string[], customer: '',
  province: [] as string[],
})

const kpi = computed(() => data.value?.kpi || {})
const prevKpi = computed(() => data.value?.prev || {})
const opts = computed(() => data.value?.options || {})
const platformOptions = computed(() => (opts.value.platform || []).map((v: string) => ({ value: v, label: v })))
const chassisOptions = computed(() => (opts.value.chassis || []).map((v: string) => ({ value: v, label: v })))
const salesOptions = computed(() => (opts.value.sales || []).map((v: string) => ({ value: v, label: v })))

const rangeLabel = computed(() => custom.value ? custom.value.label
  : { week: '本周', month: '本月', year: '本年', all: '全部时间' }[period.value as 'week' | 'month' | 'year' | 'all'])

/* ── 加载 ── */
let searchTimer: ReturnType<typeof setTimeout> | null = null
function debounceLoad() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 300)
}
const loadError = ref('')
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params: Record<string, any> = {}
    if (custom.value) { params.start = custom.value.start; params.end = custom.value.end }
    else params.period = period.value
    if (filters.result) params.result = filters.result
    if (filters.platform.length) params.platform = filters.platform.join(',')
    if (filters.chassis.length) params.chassis = filters.chassis.join(',')
    if (filters.industry.length) params.industry = filters.industry.join(',')
    if (filters.otype.length) params.otype = filters.otype.join(',')
    if (filters.sales.length) params.sales = filters.sales.join(',')
    if (filters.pn.length) params.pn = filters.pn.join(',')
    if (filters.customer.trim()) params.customer = filters.customer.trim()
    if (filters.province.length) params.province = filters.province.join(',')
    const res = await axios.get('/api/dashboard/cockpit', { params })
    data.value = res.data
  } catch (e: any) {
    // 加载失败明示错误态（不再静默渲染全 0）：多为后端未重启（无 /cockpit 端点）或网络问题
    loadError.value = e?.response?.status === 404
      ? '后端没有 /api/dashboard/cockpit 端点——请重启后端服务后重试'
      : (e?.response?.data?.detail || e?.message || '数据加载失败')
  } finally {
    loading.value = false
  }
}
function loadOnce() { if (!data.value) load() }
loadOnce()

/* ── 周期 / 自定义区间 ── */
function isPeriodActive(p: string) { return !custom.value && period.value === p }
function setPeriod(p: string) { custom.value = null; period.value = p; load() }
function fmt(d: dayjs.Dayjs) { return d.format('YYYY-MM-DD') }
function applyPreset(ps: { key: string; label: string }) {
  const today = dayjs()
  let s: dayjs.Dayjs, e: dayjs.Dayjs
  if (ps.key === 'lastWeek') {
    const dow = (today.day() + 6) % 7
    s = today.subtract(dow + 7, 'day')
    e = s.add(6, 'day')
  } else if (ps.key === 'lastMonth') {
    s = today.subtract(1, 'month').startOf('month')
    e = today.subtract(1, 'month').endOf('month')
  } else if (ps.key === 'lastYear') {
    s = today.subtract(1, 'year').startOf('year')
    e = today.subtract(1, 'year').endOf('year')
  } else if (ps.key === 'last30') {
    s = today.subtract(29, 'day'); e = today
  } else {
    s = today.subtract(89, 'day'); e = today
  }
  custom.value = { key: ps.key, start: fmt(s), end: fmt(e), label: ps.label }
  rangeOpen.value = false
  load()
}
function onMonthChange(v: any) {
  if (!v) return
  const d = dayjs(v + '-01')
  custom.value = { key: 'month:' + v, start: d.startOf('month').format('YYYY-MM-DD'), end: d.endOf('month').format('YYYY-MM-DD'), label: v }
  rangeOpen.value = false
  load()
}
function onRangeChange(v: any) {
  if (!v || !v.length) return
  const label = `${v[0]}~${v[1]}`
  custom.value = { key: 'range:' + label, start: v[0], end: v[1], label }
  rangeOpen.value = false
  load()
}

/* ── 下钻 / 筛选辅助 ── */
function setFilter(dim: string, val: string) {
  const map: Record<string, string[]> = { platform: filters.platform, chassis: filters.chassis, industry: filters.industry, otype: filters.otype, pn: filters.pn, sales: filters.sales, province: filters.province }
  const list = map[dim]
  if (!list) return
  const i = list.indexOf(val)
  i >= 0 ? list.splice(i, 1) : list.push(val)
  load()
}
function onDimClick(dim: string, p: any) {
  if (p?.componentType !== 'series' || typeof p.name !== 'string') return
  setFilter(dim, p.name)
}
function onMonthLabelPick(label: string) {
  // 点月柱 → 周期切到该月
  if (!/^(\d{4})-(\d{2})$/.test(label || '')) return
  const d = dayjs(label + '-01')
  custom.value = { key: 'month:' + label, start: d.startOf('month').format('YYYY-MM-DD'), end: d.endOf('month').format('YYYY-MM-DD'), label }
  period.value = ''
  load()
}
const chipList = computed(() => {
  const out: { dim: string; val: string }[] = []
  for (const dim of ['platform', 'chassis', 'industry', 'otype', 'pn', 'sales', 'province'] as const) {
    for (const val of filters[dim]) out.push({ dim, val })
  }
  if (filters.customer.trim()) out.push({ dim: 'customer', val: filters.customer.trim() })
  if (filters.result) out.push({ dim: 'result', val: { pending: '进行中', won: '已中标', lost: '已丢标', expired: '已过期' }[filters.result as 'pending'] || filters.result })
  if (custom.value) out.push({ dim: 'period', val: custom.value.label })
  return out
})
function removeChip(c: { dim: string; val: string }) {
  if (c.dim === 'period') { custom.value = null; load(); return }
  if (c.dim === 'result') { filters.result = ''; load(); return }
  if (c.dim === 'customer') { filters.customer = ''; load(); return }
  setFilter(c.dim, c.val)
}
function resetAll() {
  filters.result = ''
  filters.platform = []; filters.chassis = []; filters.sales = []
  filters.industry = []; filters.otype = []; filters.pn = []
  filters.customer = ''
  filters.province = []
  custom.value = null
  period.value = 'year'
  load()
}
function switchTab(key: string) {
  activeTab.value = key
  visited[key] = true
}

/* ── 环比 / 着色工具 ── */
function pctDelta(cur: number, prev: number | null | undefined): { text: string; cls: string } | null {
  if (prev == null || !prev) return null
  const d = (cur - prev) / prev * 100
  return { text: `${d >= 0 ? '▲' : '▼'} ${Math.abs(d).toFixed(1)}%`, cls: d >= 0 ? 'up' : 'down' }
}
function tintOf(color: string) {
  // 12% tint：语义色底 + 实色字（内联样式字符串，图表 canvas 色另由共享组件管理）
  return color + '1F'
}

/* ── 常态区 Hero ── */
const ringOffset = computed(() => {
  const rate = (kpi.value.win_rate || 0) / 100
  return RING_C * (1 - Math.min(1, Math.max(0.02, rate)))
})
const resultChips = computed(() => {
  const total = kpi.value.total_opportunities || 1
  return RESULT_META.map(m => ({
    ...m,
    value: (kpi.value as any)[m.key] ?? 0,
    pct: (((kpi.value as any)[m.key] || 0) / total * 100).toFixed(1) + '%',
    tint: tintOf(m.color),
  }))
})
const assetChips = computed(() => {
  const plats: { name: string; count: number }[] = data.value?.structure?.platforms || []
  const total = kpi.value.total_opportunities || 1
  const pick = () => {
    let amd = 0, zx = 0, intel = 0
    for (const d of plats) {
      if (/AMD/i.test(d.name)) amd += d.count
      else if (/兆芯/.test(d.name)) zx += d.count
      else if (/Intel|英特尔/i.test(d.name)) intel += d.count
    }
    return { amd, zx, intel }
  }
  const { amd, zx, intel } = pick()
  const mk = (label: string, glyph: string, color: string, value: number) => ({
    label, glyph, color, tint: tintOf(color), value, pct: (value / total * 100).toFixed(1) + '%',
  })
  return [
    mk('AMD', 'A', '#FF6B6B', amd),
    mk('兆芯', '兆', '#0ea5b7', zx),
    mk('Intel', 'I', '#1677FF', intel),
    mk('其他', '他', '#8A94A8', Math.max(0, kpi.value.total_opportunities - amd - zx - intel)),
  ]
})
const heroKpisLeft = computed(() => {
  const k = kpi.value
  const rateDelta = (prevKpi.value.win_rate != null && prevKpi.value.win_rate !== undefined)
    ? pctDelta(k.win_rate || 0, prevKpi.value.win_rate) : null
  const wm = data.value?.win?.won_markup
  return [
    {
      label: '成单率', v: (k.win_rate || 0).toFixed(1), unit: '%',
      stats: [
        { label: '成单', value: String(k.won ?? 0) },
        { label: '环比', value: rateDelta ? rateDelta.text : '—' },
      ],
    },
    {
      label: '成单平均加点', v: wm?.avg != null ? String(wm.avg) : '—', unit: wm?.avg != null ? ' %' : '',
      stats: [
        { label: '中位', value: wm?.median != null ? wm.median + ' %' : '—' },
        { label: '样本', value: wm ? wm.n + ' 单' : '—' },
      ],
    },
  ]
})
const heroKpisRight = computed(() => {
  const k = kpi.value
  const prev = prevKpi.value || {}
  const custDelta = (prev.customers != null && prev.customers) ? pctDelta(k.customers || 0, prev.customers) : null
  const cfgDelta = (prev.new_configs != null && prev.new_configs) ? pctDelta(k.total_configs || 0, prev.new_configs) : null
  return [
    {
      label: '客户数', v: String(k.customers ?? 0), unit: ' 家',
      stats: [
        { label: '同期', value: String(prev.customers ?? '—') },
        { label: '环比', value: custDelta ? custDelta.text : '—' },
      ],
    },
    {
      label: '配置总数', v: String(k.total_configs ?? 0), unit: ' 套',
      stats: [
        { label: '同期新增', value: String(prev.new_configs ?? '—') },
        { label: '环比', value: cfgDelta ? cfgDelta.text : '—' },
      ],
    },
  ]
})

/* ── 图表公共 ── */
function tipAxis() {
  const c = chartColors.value
  return { trigger: 'axis', backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText }, borderColor: c.tooltipBorder, borderWidth: 1 }
}
const SPLIT = computed(() => ({ lineStyle: { color: chartColors.value.splitLine } }))

function hbarOption(items: { name: string; count: number }[], opt?: { green?: boolean; tipFmt?: (d: any) => string }) {
  if (!items.length) return {}
  const c = chartColors.value
  const rows = items
  return {
    backgroundColor: 'transparent',
    tooltip: { axisPointer: { type: 'shadow' }, ...tipAxis(),
      formatter: (ps: any) => { const d = rows[ps[0].dataIndex]; return opt?.tipFmt ? opt.tipFmt(d) : `${d.name}<br/><b>${d.count}</b>` } },
    grid: { left: 4, right: 44, top: 8, bottom: 4, containLabel: true },
    xAxis: { type: 'value', max: Math.max(1, Math.ceil((rows[0]?.count || 1) * 1.15)), splitLine: SPLIT.value, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: c.axisLabel, fontSize: 10 } },
    yAxis: { type: 'category', inverse: true, data: rows.map(d => d.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { margin: 12, color: c.axisLabel, fontSize: 11 } },
    series: [{
      type: 'bar', barMaxWidth: 14,
      data: rows.map(d => ({
        value: d.count,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: opt?.green
            ? { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: 'rgba(82,201,160,.15)' }, { offset: 1, color: '#52C9A0' }] }
            : { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: 'rgba(22,119,255,.15)' }, { offset: 1, color: '#1677FF' }] },
        },
      })),
      label: { show: true, position: 'right', color: c.tooltipText, fontSize: 11, fontWeight: 600 },
    }],
  }
}

/* ── 共享图表组件的数据适配 ── */
const monthLabels = computed(() => data.value?.monthly?.months || [])
const monthTotals = computed(() => data.value?.monthly?.total || [])
const monthPlatformLines = computed(() =>
  Object.entries(data.value?.monthly?.platform_series || {}).map(([name, vals]) => ({
    name, data: vals as number[], color: PLAT_COLOR[name] || '#6B7280',
  }))
)
const wonLine = computed(() => [{ name: '当月成单', data: data.value?.monthly?.won || [], color: '#52C9A0' }])
const modelItems = computed(() => (data.value?.models?.data || []) as [string, number][])
const markupBoxes = computed(() => data.value?.markup?.boxes || [])
const structure = computed(() => data.value?.structure || { platforms: [], chassis: [], industry: [], otype: [] })
const rankTop = computed(() => data.value?.rank?.top || [])
const rankOthers = computed(() => data.value?.rank?.others || null)
const rankOthersList = computed(() => data.value?.rank?.others_list || [])
const lossReasonItems = computed(() =>
  (data.value?.win?.loss_reasons || []).map((d: any) => ({ name: d.label, count: d.count })))
const wonCustItems = computed(() => {
  const nvr = data.value?.win?.new_vs_repeat
  return nvr ? [{ name: '新客户首单', count: nvr.new || 0 }, { name: '老客户复购', count: nvr.repeat || 0 }] : []
})
const WON_CUST_COLORS: Record<string, string> = { '新客户首单': '#1677FF', '老客户复购': '#36CFCF' }
const conKpi = computed(() => {
  const k = kpi.value, p = prevKpi.value
  if (!data.value) return ''
  const d = pctDelta(k.total_opportunities || 0, p.new_opportunities)
  const rateDelta = p.win_rate != null ? pctDelta(k.win_rate || 0, p.win_rate) : null
  return `当前区间在册商机 <b>${k.total_opportunities ?? 0}</b>（同比 ${d ? `<span class="${d.cls}">${d.text}</span>` : '—'}）；` +
    `成单 <b>${k.won ?? 0}</b>、成单率 <b>${k.win_rate ?? 0}%</b>${rateDelta ? `（同比 <span class="${rateDelta.cls}">${rateDelta.text}</span>）` : ''}；进行中 <b>${k.pending ?? 0}</b> 单。` +
    ` 月度趋势固定近12月，仅随维度筛选。`
})

/* ── 产品结构 ── */
function statRow(tint: string, glyph: string, label: string, cur: number | string, prev: number | string | null, unit = '') {
  const numeric = typeof cur === 'number' && typeof prev === 'number'
  return { tint, glyph, label, cur, prev: prev == null ? '—' : prev, unit, delta: numeric ? pctDelta(cur as number, prev as number) : null }
}
const productStats = computed(() => {
  const st = data.value?.structure
  if (!st) return []
  const p = prevKpi.value
  return [
    statRow('blue', '台', '覆盖平台数', st.platforms.length, null),
    statRow('cyan', '型', '覆盖机型数', data.value.models.data.length, null),
    statRow('cyan', '配', '配置总数', kpi.value.total_configs ?? 0, p.new_configs ?? null),
  ]
})
const industryOpt = computed(() => hbarOption((data.value?.structure?.industry || []).map((d: any) => ({ name: d.name, count: d.count }))))
const conProduct = computed(() => {
  const st = data.value?.structure
  if (!st || !data.value) return ''
  const total = kpi.value.total_opportunities || 1
  const [tp, tc, ti, tm] = [st.platforms[0], st.chassis[0], st.industry[0], data.value.models.data[0]]
  return `${tp ? `${tp.name} 占 <b>${(tp.count / total * 100).toFixed(1)}%</b> 居首` : '暂无数据'}；` +
    `${tc ? `${tc.name} 形态占 <b>${(tc.count / total * 100).toFixed(1)}%</b>` : ''}；` +
    `${ti ? `${ti.name} 行业 <b>${ti.count}</b> 家最多` : ''}；${tm ? `${tm[0]} 报价 <b>${tm[1]}</b> 次为最热机型` : ''}。`
})

/* ── 人员与转化 ── */
const peopleStats = computed(() => {
  const rk = data.value?.rank
  if (!rk) return []
  const k = kpi.value
  return [
    statRow('blue', '人', '在册业务数', rk.top.length + (rk.others_list?.length || 0), null),
    statRow('cyan', '冠', 'Top5 商机占比', rk.total ? +((rk.top.reduce((s: number, d: any) => s + d.count, 0) / rk.total) * 100).toFixed(1) + '%' : '0%', null),
    statRow('green', '成', '整体成单数', k.won ?? 0, prevKpi.value.won ?? null),
    statRow('blue', '率', '整体成单率', (k.win_rate ?? 0) + '%', prevKpi.value.win_rate != null ? prevKpi.value.win_rate + '%' : null),
  ]
})
const conPeople = computed(() => {
  const rk = data.value?.rank
  if (!rk || !data.value) return ''
  const top = rk.top?.[0]
  if (!top) return '暂无数据。'
  const rate = top.count ? (top.won / top.count * 100).toFixed(1) : '0'
  const top5Share = rk.total ? (rk.top.reduce((s: number, d: any) => s + d.count, 0) / rk.total * 100).toFixed(1) : '0'
  return `Top5 业务承载 <b>${top5Share}%</b> 商机；${top.name} 以 <b>${top.count}</b> 单居首（成单率 <b>${rate}%</b>）。点人名可下钻。`
})

/* ── 成单与输单 ── */
const winStats = computed(() => {
  const w = data.value?.win
  if (!w) return []
  const k = kpi.value
  const median = w.cycle?.median
  return [
    statRow('green', '成', '成单数', k.won ?? 0, prevKpi.value.won ?? null),
    statRow('cyan', '点', '成单平均加点', w.won_models?.length
      ? (() => { const all = w.won_models.flatMap((m: any) => m.avg_markup != null ? [m.avg_markup] : []); return all.length ? (all.reduce((a: number, b: number) => a + b, 0) / all.length).toFixed(1) + '%' : '—' })()
      : '—', null),
    statRow('blue', '时', '成单时效中位', median != null ? median + ' 天' : '—', null),
    statRow('coral', '失', '未成单数', (k.lost ?? 0) + (k.expired ?? 0), (prevKpi.value.lost ?? 0) + (prevKpi.value.expired ?? 0) || null),
  ]
})
const winReasonOpt = computed(() => {
  const items = (data.value?.win?.win_reasons || []).map((d: any) => ({ name: d.label, count: d.count }))
  if (!items.length) return {}
  const o: any = hbarOption(items, { green: true, tipFmt: (d: any) => `${d.name}<br/>成单 <b>${d.count}</b> 单` })
  return o
})
const markupWinOpt = computed(() => {
  const bins = data.value?.markup?.bins || []
  if (!bins.length) return {}
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: { ...tipAxis(), formatter: (ps: any) => { const d = bins[ps[0].dataIndex]; return `${d.label}<br/>报价 <b>${d.count}</b> 次 · 成单率 <b>${d.rate}%</b>` } },
    legend: { top: 0, textStyle: { color: c.axisLabel, fontSize: 10 }, icon: 'roundRect', itemWidth: 12, itemHeight: 2 },
    grid: { left: 40, right: 44, bottom: 28, top: 32 },
    xAxis: { type: 'category', data: bins.map((d: any) => d.label), axisLine: { lineStyle: { color: c.grid } }, axisLabel: { color: c.axisLabel, fontSize: 10 }, axisTick: { show: false } },
    yAxis: [
      { type: 'value', name: '报价次数', splitLine: SPLIT.value, axisLabel: { color: c.axisLabel, fontSize: 10 }, nameTextStyle: { color: c.axisLabel, fontSize: 10 } },
      { type: 'value', name: '成单率%', max: 50, splitLine: { show: false }, axisLabel: { color: c.axisLabel, fontSize: 10, formatter: '{value}%' }, nameTextStyle: { color: c.axisLabel, fontSize: 10 } },
    ],
    series: [
      { name: '报价次数', type: 'bar', barWidth: '40%', data: bins.map((d: any) => d.count), itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#36CFCF' }, { offset: 1, color: 'rgba(54,207,207,.15)' }] }, borderRadius: [4, 4, 0, 0] } },
      { name: '成单率', type: 'line', yAxisIndex: 1, smooth: true, data: bins.map((d: any) => d.rate), lineStyle: { width: 2.5, color: '#FF3B5C' }, itemStyle: { color: '#FF3B5C' }, symbolSize: 6,
        label: { show: true, position: 'top', color: '#e5484d', fontSize: 10, formatter: '{c}%' } },
    ],
  }
})
const wonModelOpt = computed(() => {
  const items = data.value?.win?.won_models || []
  if (!items.length) return {}
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: { ...tipAxis(), formatter: (ps: any) => { const d = items[ps[0].dataIndex]; return `${d.name}<br/>成单 <b>${d.count}</b> 单 · 平均加点 <b>${d.avg_markup ?? '-'}%</b>` } },
    legend: { top: 0, textStyle: { color: c.axisLabel, fontSize: 10 }, icon: 'roundRect', itemWidth: 12, itemHeight: 2 },
    grid: { left: 40, right: 44, bottom: 28, top: 32 },
    xAxis: { type: 'category', data: items.map((d: any) => d.name), axisLine: { lineStyle: { color: c.grid } }, axisLabel: { color: c.axisLabel, fontSize: 10, rotate: items.length > 4 ? 20 : 0, interval: 0 }, axisTick: { show: false } },
    yAxis: [
      { type: 'value', name: '成单数', splitLine: SPLIT.value, axisLabel: { color: c.axisLabel, fontSize: 10 }, nameTextStyle: { color: c.axisLabel, fontSize: 10 } },
      { type: 'value', name: '平均加点%', splitLine: { show: false }, axisLabel: { color: c.axisLabel, fontSize: 10, formatter: '{value}%' }, nameTextStyle: { color: c.axisLabel, fontSize: 10 } },
    ],
    series: [
      { name: '成单数', type: 'bar', barWidth: '40%', data: items.map((d: any) => d.count), itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#52C9A0' }, { offset: 1, color: 'rgba(82,201,160,.15)' }] }, borderRadius: [4, 4, 0, 0] } },
      { name: '平均加点', type: 'line', yAxisIndex: 1, smooth: true, data: items.map((d: any) => d.avg_markup), lineStyle: { width: 2, color: '#FA8C16' }, itemStyle: { color: '#FA8C16' }, symbolSize: 5 },
    ],
  }
})
const cycleOpt = computed(() => {
  const cyc = data.value?.win?.cycle
  if (!cyc?.bins?.length) return {}
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: { axisPointer: { type: 'shadow' }, ...tipAxis(),
      formatter: (p: any) => `${cyc.bins[p[0].dataIndex].label}<br/>成单 <b>${p[0].value}</b> 单<br/>中位 <b>${cyc.median ?? '—'}</b>天 · P90 <b>${cyc.p90 ?? '—'}</b>天` },
    grid: { left: 40, right: 16, bottom: 28, top: 20 },
    xAxis: { type: 'category', data: cyc.bins.map((b: any) => b.label), axisLine: { lineStyle: { color: c.grid } }, axisLabel: { color: c.axisLabel, fontSize: 10 }, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: SPLIT.value, axisLabel: { color: c.axisLabel, fontSize: 10 } },
    series: [{ type: 'bar', barWidth: '46%', data: cyc.bins.map((b: any) => b.count), itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#722ED1' }, { offset: 1, color: 'rgba(114,46,209,.15)' }] }, borderRadius: [4, 4, 0, 0] } }],
  }
})
const conWin = computed(() => {
  const w = data.value?.win
  if (!w || !data.value) return ''
  const topWin = w.win_reasons?.[0]
  const topLoss = w.loss_reasons?.[0]
  let best: { label: string; rate: number } | null = null
  for (const b of data.value.markup.bins || []) {
    if (b.count >= 8 && (!best || b.rate > best.rate)) best = { label: b.label, rate: b.rate }
  }
  return `制胜首因 <span class="good">${topWin ? topWin.label : '—'}</span>；丢标首因 <span class="bad">${topLoss ? topLoss.label : '—'}</span>；` +
    `成单时效中位 <b>${w.cycle?.median ?? '—'}</b> 天；` +
    (best ? `加点 <b>${best.label}</b> 区间成单率最高（<b>${best.rate}%</b>）——加点越高成单越难，报价加点应锚定该拐点。` : '')
})

/* ── 客户与地区 ── */
const regionStats = computed(() => {
  const rg = data.value?.region
  if (!rg) return []
  const wonCustSet = new Set<string>((data.value.customers?.top || []).filter((c: any) => c.won > 0).map((c: any) => c.name))
  return [
    statRow('blue', '客', '客户数', kpi.value.customers ?? 0, prevKpi.value.customers ?? null),
    statRow('green', '胜', '成单客户数', wonCustSet.size, null),
    statRow('cyan', '购', '复购客户数（≥2商机）', (data.value.customers?.top || []).filter((c: any) => c.count >= 2).length, null),
    statRow('blue', '海', '海外商机数', rg.overseas ?? 0, null),
  ]
})
/* 地图：geoJSON 内置 public/geo/（不依赖 CDN），按需注册；中国/世界双视图 */
const mapReady = ref(false)
const mapMode = ref<'china' | 'world'>('china')
const registered = reactive({ china: false, world: false })
async function ensureMap(mode: 'china' | 'world') {
  if (registered[mode]) { mapReady.value = true; return }
  try {
    const res = await fetch(`/geo/${mode}.json`)
    echarts.registerMap(mode, await res.json())
    registered[mode] = true
    mapReady.value = true
  } catch { /* 离线时地图卡显示加载中提示 */ }
}
async function switchMapMode(mode: 'china' | 'world') {
  await ensureMap(mode)   // 先注册成功再切，避免 setOption 撞上未注册地图名
  mapMode.value = mode
}
onMounted(() => ensureMap('china'))
function onMapClick(p: any) {
  if (mapMode.value === 'china' && p?.name && p.componentType === 'series') setFilter('province', p.name)
}
const mapOpt = computed(() => {
  const mode = mapMode.value
  if (!registered[mode]) return {}   // reactive 依赖：geoJSON 注册完成后才出 option
  const c = chartColors.value
  const items = mode === 'china'
    ? (data.value?.region?.provinces || []) as { name: string; count: number }[]
    : (data.value?.region?.countries || []) as { name: string; count: number }[]
  const maxV = Math.max(1, ...items.map(d => d.count))
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: c.tooltipBg, textStyle: { color: c.tooltipText }, borderColor: c.tooltipBorder, borderWidth: 1,
      formatter: (p: any) => `${p.name}<br/>商机 <b>${p.value || 0}</b>${mode === 'china' && items.length ? '<br/><span style="color:#86909c">点击下钻</span>' : ''}` },
    visualMap: { min: 0, max: maxV, left: 8, bottom: 4, calculable: true, text: ['高', '低'],
      textStyle: { color: c.axisLabel, fontSize: 10 }, inRange: { color: [c.mapLow, '#1677FF'] } },
    series: [{
      type: 'map', map: mode, roam: true,
      label: { show: false }, itemStyle: { areaColor: c.mapArea, borderColor: c.mapBorder, borderWidth: .5 },
      emphasis: { label: { show: true, fontSize: 11, color: c.tooltipText }, itemStyle: { areaColor: '#91CCFF' } },
      select: { disabled: true },
      // ECharts map 的 data 需要 {name, value}；后端给的是 {name, count}
      data: items.map(d => ({ name: d.name, value: d.count })),
    }],
  }
})
const custOpt = computed(() => {
  const items = (data.value?.customers?.top || []).map((c: any) => ({ ...c, hasWon: c.won > 0 }))
  if (!items.length) return {}
  const c = chartColors.value
  return {
    backgroundColor: 'transparent',
    tooltip: { axisPointer: { type: 'shadow' }, ...tipAxis(),
      formatter: (p: any) => { const d = items[p[0].dataIndex]; return `${d.name}<br/>商机 <b>${d.count}</b> · 成单 <b>${d.won}</b><br/><span style="color:#86909c">点击下钻</span>` } },
    grid: { left: 4, right: 44, top: 8, bottom: 4, containLabel: true },
    xAxis: { type: 'value', splitLine: SPLIT.value, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: c.axisLabel, fontSize: 10 } },
    yAxis: { type: 'category', inverse: true, data: items.map((d: any) => d.name), axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { margin: 12, color: c.axisLabel, fontSize: 11 } },
    series: [{
      type: 'bar', barMaxWidth: 14,
      data: items.map((d: any) => ({
        value: d.count,
        itemStyle: { borderRadius: [0, 6, 6, 0],
          color: d.hasWon
            ? { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: 'rgba(82,201,160,.15)' }, { offset: 1, color: '#52C9A0' }] }
            : { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: 'rgba(22,119,255,.15)' }, { offset: 1, color: '#1677FF' }] } },
      })),
      label: { show: true, position: 'right', color: c.tooltipText, fontSize: 11, fontWeight: 600 },
    }],
  }
})
const conRegion = computed(() => {
  const rg = data.value?.region
  if (!rg || !data.value) return ''
  const topC = data.value.customers?.top?.[0]
  const topP = rg.provinces?.[0]
  return `${topC ? `<b>${topC.name}</b> 以 <b>${topC.count}</b> 商机居首` : ''}；` +
    `${topP ? `识别度最高的省份 <b>${topP.name}（${topP.count} 单）</b>` : '暂无可识别省份'}；海外商机 <b>${rg.overseas ?? 0}</b> 单。` +
    `省份为关键词推断口径。点地图省份/客户名可下钻。`
})
</script>

<style scoped>
/* 布局间距只用 --cpq-space-*；字号只用字阶 token；颜色/阴影/圆角走 tokens（style-gate 门禁） */
.cockpit-page { max-width: 1440px; margin: 0 auto; padding: var(--cpq-space-2) var(--cpq-space-5) var(--cpq-space-6); }
.bar-divider { width: 1px; align-self: stretch; margin: var(--cpq-space-1) 0; background: var(--cpq-border-primary); }
.ck-top { position: sticky; top: var(--cpq-space-2); z-index: 30; display: flex; flex-direction: column; gap: var(--cpq-space-2); margin-bottom: var(--cpq-space-4); }
.ck-bar { display: flex; align-items: center; gap: var(--cpq-space-2) var(--cpq-space-3); flex-wrap: wrap; padding: var(--cpq-space-2) var(--cpq-space-4); border-radius: var(--cpq-radius-xl); }
.ck-title {
  margin: 0; font-size: var(--cpq-font-size-xl); font-weight: 700; line-height: 1.25; white-space: nowrap;
  background: var(--cpq-accent-gradient); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.ck-sub { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); white-space: nowrap; }
.ck-hint { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }

/* 周期快捷 */
.period-toggle { display: flex; gap: 2px; background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-full); padding: 3px; }
.period-option { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); padding: 2px 14px; border-radius: var(--cpq-radius-full); cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: var(--cpq-space-2); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.period-option.active { background: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-weight: 600; }
.period-dot { width: 5px; height: 5px; border-radius: var(--cpq-radius-full); background: currentColor; opacity: .55; }
.range-btn { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-md); padding: 3px 12px; cursor: pointer; font-family: inherit; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.range-btn:hover, .range-btn.on { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.range-pop { min-width: 300px; }
.range-sec { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); margin: var(--cpq-space-2) 0 var(--cpq-space-1); }
.preset-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cpq-space-2); }
.preset-btn { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md); padding: 4px 8px; cursor: pointer; font-family: inherit; }
.preset-btn:hover, .preset-btn.active { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.range-inputs { margin-top: var(--cpq-space-2); }

/* 筛选行 */
.cust-search { width: 160px; }
.f-reset { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary); background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md); padding: 4px 12px; cursor: pointer; font-family: inherit; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.f-reset:hover { color: var(--cpq-accent-danger); border-color: var(--cpq-accent-danger); }

/* 下钻片 */
.ck-chips { display: flex; align-items: center; gap: var(--cpq-space-2); flex-wrap: wrap; padding: 0 var(--cpq-space-2); }
.f-chip { display: inline-flex; align-items: center; gap: 5px; font-size: var(--cpq-font-size-xs); font-weight: 600; color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border: 1px solid var(--cpq-overlay-a30); border-radius: var(--cpq-radius-full); padding: 2px 10px; cursor: pointer; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.f-chip:hover { background: var(--cpq-overlay-a15); }
.f-chip .dim { font-style: normal; opacity: .65; font-weight: 400; }
.f-chip b { font-weight: 400; opacity: .7; }

/* 常态区 Hero */
.hero-grid { display: grid; grid-template-columns: minmax(150px, .6fr) minmax(320px, 1.6fr) minmax(150px, .6fr); gap: var(--cpq-space-4); margin-bottom: var(--cpq-space-4); }
.kpi-col { display: flex; flex-direction: column; gap: var(--cpq-space-4); }
.kpi-col .kpi { flex: 1; padding: var(--cpq-space-3) var(--cpq-space-4); display: flex; flex-direction: column; justify-content: center; position: relative; }
.kpi-l { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); }
.kpi-v { font-size: var(--cpq-font-size-2xl); font-weight: 700; line-height: 1.3; font-variant-numeric: tabular-nums; margin: var(--cpq-space-1) 0; color: var(--cpq-text-primary); }
.kpi-v small { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); font-weight: 500; margin-left: var(--cpq-space-1); }
.kpi-stats { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cpq-space-1) var(--cpq-space-4); margin-top: var(--cpq-space-2); }
.kpi-stat { display: flex; flex-direction: column; }
.ks-l { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.ks-v { font-size: var(--cpq-font-size-sm); font-weight: 600; font-variant-numeric: tabular-nums; color: var(--cpq-text-primary); }

.hero { display: flex; align-items: center; justify-content: center; gap: var(--cpq-space-4); padding: var(--cpq-space-4); }
.hchips { display: flex; flex-direction: column; gap: var(--cpq-space-2); flex: 1; min-width: 0; }
.hchip { display: flex; align-items: center; gap: 10px; background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-lg); padding: var(--cpq-space-2) var(--cpq-space-3); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.hchip:hover { border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-w10); }
.hicon { width: 34px; height: 34px; border-radius: var(--cpq-radius-lg); flex: none; display: flex; align-items: center; justify-content: center; font-size: var(--cpq-font-size-base); font-weight: 700; }
.ht { display: flex; flex-direction: column; min-width: 0; }
.hl { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); white-space: nowrap; }
.hv { font-size: var(--cpq-font-size-lg); font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; color: var(--cpq-text-primary); }
.hp { margin-left: auto; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.hero-ring { position: relative; width: 220px; height: 220px; flex: none; }
.hero-ring svg { width: 100%; height: 100%; }
.hero-ring circle { transition: stroke-dashoffset .9s var(--cpq-ease-out-expo); }
.ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.rc-lab { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.rc-big { font-size: var(--cpq-font-size-3xl); font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.15; color: var(--cpq-text-primary); }
.rc-sub { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); margin-top: var(--cpq-space-1); }
.rc-sub b { color: var(--cpq-notif-green); }

/* Tab 板块 */
.tabs { display: flex; gap: var(--cpq-space-1); padding: var(--cpq-space-1); margin-bottom: var(--cpq-space-4); overflow-x: auto; border-radius: var(--cpq-radius-xl); }
.tab { flex: 1; min-width: 120px; display: inline-flex; align-items: center; justify-content: center; gap: var(--cpq-space-2); font-size: var(--cpq-font-size-base); font-weight: 600; color: var(--cpq-text-secondary); border: none; background: transparent; border-radius: var(--cpq-radius-lg); padding: 8px 16px; cursor: pointer; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); font-family: inherit; white-space: nowrap; }
.tab .tdot { width: 7px; height: 7px; border-radius: var(--cpq-radius-sm); background: var(--cpq-text-disabled); transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.tab:hover { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.tab.active { color: var(--cpq-accent-on-primary); background: var(--cpq-accent-gradient); box-shadow: var(--cpq-shadow-sm); }
.tab.active .tdot { background: var(--cpq-accent-on-primary); }

/* 面板 */
.panel { animation: ckFadeUp var(--cpq-dur-2) var(--cpq-ease-out-expo); }
@keyframes ckFadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.card-block { padding: var(--cpq-space-4); margin-bottom: var(--cpq-space-4); min-width: 0; }
.card-block:last-child { margin-bottom: 0; }
.card-head { display: flex; align-items: center; gap: 10px; font-size: var(--cpq-font-size-base); font-weight: 600; letter-spacing: .5px; color: var(--cpq-text-primary); margin-bottom: var(--cpq-space-3); }
.card-head::after { content: ''; flex: 1; height: 1px; background: var(--cpq-overlay-a15); }
.card-head .note { font-weight: 400; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); letter-spacing: 0; white-space: nowrap; }
.card-head-sub { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.map-toggle { display: inline-flex; gap: 2px; background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-full); padding: 2px; }
.map-toggle button { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary); border: none; background: transparent; padding: 2px 12px; border-radius: var(--cpq-radius-full); cursor: pointer; font-family: inherit; }
.map-toggle button.active { background: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-weight: 600; }
.conclusion { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); background: var(--cpq-overlay-a4); border-radius: var(--cpq-radius-md); padding: var(--cpq-space-2) var(--cpq-space-3); margin-bottom: var(--cpq-space-3); }
.conclusion b { color: var(--cpq-accent-primary); font-weight: 600; }
.conclusion .good { color: var(--cpq-notif-green); font-weight: 600; }
.conclusion .bad { color: var(--cpq-notif-red); font-weight: 600; }
.chart { width: 100%; height: 260px; }
.chart-tall { width: 100%; height: 320px; }
.chart-wide { width: 100%; height: 320px; }
.chart-big { width: 100%; height: 400px; }
.chart-mini { width: 100%; height: 210px; }
.chart-empty { height: 200px; display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }

/* KPI 指标条 */
.stats { display: grid; gap: var(--cpq-space-4); grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); margin-bottom: var(--cpq-space-3); }
.stat { display: flex; align-items: center; gap: var(--cpq-space-3); padding: var(--cpq-space-3) var(--cpq-space-4); border-radius: var(--cpq-radius-xl); min-width: 0; }
.sicon { width: 38px; height: 38px; border-radius: var(--cpq-radius-lg); flex: none; display: flex; align-items: center; justify-content: center; font-size: var(--cpq-font-size-base); font-weight: 700; }
.st { display: flex; flex-direction: column; min-width: 0; }
.sl { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); white-space: nowrap; }
.sv { font-size: var(--cpq-font-size-2xl); font-weight: 700; line-height: 1.25; font-variant-numeric: tabular-nums; color: var(--cpq-text-primary); }
.sv small { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); font-weight: 500; margin-left: 2px; }
.sp { margin-left: auto; text-align: right; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); line-height: 1.5; flex: none; }
.sp b { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); font-weight: 600; font-variant-numeric: tabular-nums; }
.delta2 { font-style: normal; font-size: var(--cpq-font-size-xs); font-weight: 600; }
.delta2.up { color: var(--cpq-notif-green); }
.delta2.down { color: var(--cpq-notif-red); }
.tint-blue .sicon { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.tint-cyan .sicon { background: var(--cpq-overlay-cyan15); color: var(--cpq-notif-cyan); }
.tint-green .sicon { background: var(--cpq-overlay-success15); color: var(--cpq-notif-green); }
.tint-coral .sicon { background: var(--cpq-overlay-danger10); color: var(--cpq-notif-red); }

/* 网格 */
.grid2 { display: grid; gap: var(--cpq-space-4); grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); }
.grid3 { display: grid; gap: var(--cpq-space-4); grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); }
.grid4 { display: grid; gap: var(--cpq-space-4); grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); }
.grid4 .card-block { margin-bottom: 0; }

.load-error { display: flex; align-items: center; justify-content: space-between; gap: var(--cpq-space-4); padding: var(--cpq-space-4) var(--cpq-space-5); margin-bottom: var(--cpq-space-4); border-radius: var(--cpq-radius-xl); }
.le-text { font-size: var(--cpq-font-size-base); color: var(--cpq-accent-danger); }

@media (max-width: 900px) {
  .hero-grid { grid-template-columns: 1fr; }
  .hchips { flex-direction: row; flex-wrap: wrap; }
  .hchip { flex: 1 1 45%; }
  .hero-ring { width: 190px; height: 190px; }
}
@media (max-width: 768px) {
  .cockpit-page { padding: var(--cpq-space-2) var(--cpq-space-3) var(--cpq-space-5); }
  .ck-bar { padding: var(--cpq-space-2) var(--cpq-space-3); }
  .ck-sub { display: none; }
  .tab { min-width: 96px; font-size: var(--cpq-font-size-sm); padding: 8px 10px; }
  .chart { height: 220px; }
  .chart-big { height: 300px; }
}
</style>
