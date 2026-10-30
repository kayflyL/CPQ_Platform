<script setup lang="ts">
/** 报价单详情弹窗（已导出快照只读查看）——成本表查看器同构形态。
 * 数据 = 导出冻结的 cost_snapshot（配置 tab + 分组行级表 + 合计条）。
 * 两种数据形态：
 *  - 完整快照：{totals, configs:{name:{qty,totals,kp_items,l6_items,...机型信息}}, rates}。
 *    l6_items 2026-10-30 起随导出冻结（Workspace.buildCostSnapshot）；旧快照无 l6_items →
 *    L6 组回落单行汇总（成本/售价/利润率取分段 totals）。
 *  - 手工补录快照（旧数据）：{manual:true, captured_at, totals} → 只渲染整机汇总。
 * 动作（解冻/复制为草稿/发送/分享/编辑）都在报价单行「更多」菜单，本弹窗纯查看。 */
import { computed, ref, watch } from 'vue'
import { money } from '@/utils/quoteCommon'
import { baseConfigApi, catalogApi } from '@/api/serverConfig'
import ResponsiveModal from '@/components/common/ResponsiveModal.vue'
import GroupedConfigDetail from '@/components/opportunity/GroupedConfigDetail.vue'
import { MODAL_BODY_MAX_HEIGHT } from '@/constants/modalPresets'

const props = defineProps<{
  quotation: any
}>()
const open = defineModel<boolean>('open', { default: false })

const snap = computed<any>(() => props.quotation?.cost_snapshot || null)
const hasSnapshot = computed(() => !!snap.value)
const isManual = computed(() => !!snap.value?.manual)
// L3 策略溯源（仅推理流来源的报价单显示依据）
const isReasoning = computed(() => props.quotation?.source === 'reasoning')
const strategySnap = computed<any[]>(() => props.quotation?.strategy_snapshot || [])
function formatStratBody(s: any): string {
  if (s.type === 'pricing_additive') {
    const b = s.body || {}
    const steps = Array.isArray(b.breakdown)
      ? b.breakdown.filter((x: any) => x.value !== '—').map((x: any) => `${x.matched || ''}${typeof x.value === 'number' ? (x.opKind === 'mult' ? `×${x.value}` : (x.opKind === 'add' ? `${x.value >= 0 ? '+' : ''}${x.value}` : `${x.value}`)) : ''}`.trim()).filter(Boolean).join(' · ')
      : ''
    return `目标 ${b.target}%（保底 ${b.floor}% ~ 封顶 ${b.cap}%${b.clamped ? ' · 已触边界' : ''}）${steps ? ' · ' + steps : ''}`
  }
  if (s.type === 'pricing_scenario') {
    const rb = s.body?.rule_body
    const tier = rb ? `底线 ${rb.floor}% / 标准 ${rb.standard}% / 优质 ${rb.premium}%` : ''
    return `${s.body?.description || '(无说明)'}${tier ? ' · ' + tier : ''}`
  }
  if (s.type === 'margin_tier') { const b = s.body || {}; return `底线 ${b.floor}% / 标准 ${b.standard}% / 优质 ${b.premium}%` }
  if (s.type === 'warranty_markup') { const b = s.body || {}; const y7 = b.y7 != null ? ` / 7年${b.y7}%` : ''; return `1年${b.y1}% / 3年${b.y3}% / 5年${b.y5}%${y7}` }
  return JSON.stringify(s.body || {})
}

const totals = computed(() => snap.value?.totals || {})
const cfgNames = computed<string[]>(() => (snap.value?.configs ? Object.keys(snap.value.configs) : []))

// ── 机型信息（服务器型号 / 机箱形态 / 盘位 / 系列）──
// 新导出单：快照已冻结（见 Workspace.buildCostSnapshot）；旧快照：回退报价单字段 + 机型目录/基准配置现查。
// 只做展示，不参与任何成本口径。
const liveInfo = ref<Record<string, { series?: string; form?: string; bays?: number; name?: string }>>({})
let modelCatalog: any[] | null = null

async function loadModelCatalog(): Promise<any[]> {
  if (modelCatalog) return modelCatalog
  try {
    const res = await catalogApi.listModels()
    modelCatalog = res.models || []
  } catch {
    modelCatalog = []
  }
  return modelCatalog
}

function baseConfigIdOf(name: string): number | null {
  const fromSnap = snap.value?.configs?.[name]?.base_config_id
  if (fromSnap) return Number(fromSnap)
  const fromQuote = props.quotation?.config_l6_picks?.[name]?.base_config_id
  return fromQuote ? Number(fromQuote) : null
}

/** 旧快照补齐形态/盘位/系列：机型目录（按 server_model_id/型号名）→ 基准配置（base_config_id）。 */
async function ensureLiveInfo(name: string) {
  const c = snap.value?.configs?.[name] || {}
  if (c.form && c.series && c.bays != null) return  // 快照齐了，不必回查
  if (liveInfo.value[name]) return
  const modelId = c.server_model_id ?? props.quotation?.config_l6_picks?.[name]?.server_model_id ?? null
  const modelName = c.server_model || props.quotation?.config_server_models?.[name] || ''
  const models = await loadModelCatalog()
  const model = (modelId ? models.find((m: any) => m.id === Number(modelId)) : null)
    || models.find((m: any) => m.name === modelName)
  let info: { series?: string; form?: string; bays?: number; name?: string } = {}
  if (model?.base_config) {
    info = {
      series: model.base_config.series || '',
      form: model.base_config.form || '',
      bays: model.base_config.bays ?? undefined,
      name: model.base_config.name || '',
    }
  } else {
    const bcId = baseConfigIdOf(name)
    if (bcId) {
      try {
        const bc: any = await baseConfigApi.get(bcId)
        info = { series: bc.series || '', form: bc.form || '', bays: bc.bays ?? undefined, name: bc.name || '' }
      } catch { /* 机型信息缺失不阻塞成本复核 */ }
    }
  }
  liveInfo.value = { ...liveInfo.value, [name]: info }
}

watch(
  [open, () => props.quotation?.quotation_id, cfgNames],
  ([v]) => {
    if (!v) return
    cfgNames.value.forEach((n) => void ensureLiveInfo(n))
  },
  { immediate: true },
)

const modelInfoMap = computed<Record<string, any>>(() => {
  const out: Record<string, any> = {}
  for (const name of cfgNames.value) {
    const c = snap.value?.configs?.[name] || {}
    const live = liveInfo.value[name] || {}
    out[name] = {
      server_model: c.server_model || props.quotation?.config_server_models?.[name] || '',
      description: c.description || props.quotation?.config_descriptions?.[name] || '',
      form: c.form || live.form || '',
      bays: c.bays ?? live.bays ?? null,
      series: c.series || live.series || '',
      base_config_name: c.base_config_name || live.name || '',
    }
  }
  return out
})

function pct(n: any): string {
  const v = Number(n || 0)
  return (Number.isFinite(v) ? v : 0).toFixed(1) + '%'
}
function marginOf(cost: any, sales: any): number {
  const c = Number(cost || 0)
  if (c <= 0) return 0
  return ((Number(sales || 0) - c) / c) * 100
}

// ── 快照 → 通用配置明细组件的归一化映射（形态见 GroupedConfigDetail） ──
const detailConfigs = computed(() => cfgNames.value.map((name) => {
  const c = snap.value?.configs?.[name] || {}
  const t = c.totals || {}
  const l6 = Array.isArray(c.l6_items) ? c.l6_items : []
  const kp = Array.isArray(c.kp_items) ? c.kp_items : []
  const rows: { group: string; groupSpan?: number; catalogue: string; description: string; qty: string; cells: [string, string, string] }[] = []
  if (l6.length) {
    l6.forEach((it: any, i: number) => rows.push({
      group: 'L6',
      groupSpan: i === 0 ? l6.length : undefined,
      catalogue: it.name || '—',
      description: it.description || '',
      qty: String(it.qty ?? '—'),
      cells: ['—', '—', '—'],
    }))
  } else {
    rows.push({
      group: 'L6',
      groupSpan: 1,
      catalogue: '机箱 (L6) 汇总',
      description: '旧快照未冻结行级明细',
      qty: '—',
      cells: [money(t.l6Cost), money(t.l6Sales), pct(marginOf(t.l6Cost, t.l6Sales))],
    })
  }
  kp.forEach((it: any, i: number) => rows.push({
    group: 'KP',
    groupSpan: i === 0 ? kp.length : undefined,
    catalogue: it.cat || '—',
    description: it.name || '',
    qty: String(it.qty ?? '—'),
    cells: [money(it.cost), money(it.sales), pct(it.margin)],
  }))
  return {
    key: name,
    tab: name,
    summary: [
      { label: '配置名', value: name },
      { label: '机型型号', value: modelInfoMap.value[name]?.server_model || '—' },
      { label: '描述', value: modelInfoMap.value[name]?.description || '—', wide: true },
      { label: '数量', value: `${c.qty || 0} 台` },
    ],
    note: modelInfoMap.value[name]?.base_config_name
      ? `基准配置 · ${modelInfoMap.value[name].base_config_name}`
      : undefined,
    metricHeaders: ['成本', '售价', '利润率'] as [string, string, string],
    rows,
    totals: [
      { label: 'L6 成本合计', value: money(t.l6Cost) },
      { label: 'KP 成本合计', value: money(t.kpCost) },
      { label: '整机成本合计', value: money(t.totalCost) },
      { label: '整机售价', value: money(t.totalSales) },
      { label: '整机利润率', value: pct(t.marginPct), accent: true },
    ],
  }
}))
</script>

<template>
  <ResponsiveModal
    v-model:open="open"
    :title="quotation?.quotation_name || '报价单'"
    tier="sheet"
    centered
    wrap-class-name="portal-sheet-modal"
    :footer="null"
    :body-style="{ padding: '14px', maxHeight: MODAL_BODY_MAX_HEIGHT, overflowY: 'auto', overflowX: 'hidden' }"
  >
    <!-- 状态与冻结元信息（原抽屉标题栏 + rates 行合并） -->
    <div class="qd-meta">
      <span class="qd-tag">
        <template v-if="hasSnapshot && isManual">手工补录 · {{ snap.captured_at?.slice(0, 10) || '—' }}</template>
        <template v-else-if="hasSnapshot">已导出 · {{ quotation?.exported_at?.slice(0, 10) || '—' }}</template>
        <template v-else>无成本数据</template>
      </span>
      <span v-if="hasSnapshot && !isManual && snap.rates" class="qd-rates">
        汇率 {{ snap.rates.usd_to_rmb }} · 税率 {{ (snap.rates.tax_rate * 100).toFixed(0) }}% · 冻结于 {{ snap.captured_at?.slice(0, 16).replace('T', ' ') }}
      </span>
    </div>

    <!-- 无成本数据（历史导入或未导出）：仅提示，不再支持补录 -->
    <div v-if="!hasSnapshot" class="glass qd-hint">该报价单暂无成本快照数据。</div>

    <!-- 手工补录快照：只有项目级 totals，无 configs -->
    <section v-else-if="isManual" class="snap-block glass">
      <header class="sb-head"><h4>整机汇总</h4></header>
      <div class="kpi-row">
        <div class="kpi">
          <span class="kpi-label">整机成本</span>
          <span class="kpi-value">{{ money(totals.totalCost) }}</span>
        </div>
        <div class="kpi kpi-accent">
          <span class="kpi-label">整机利润率</span>
          <span class="kpi-value">{{ pct(totals.marginPct) }}</span>
        </div>
        <div class="kpi">
          <span class="kpi-label">利润额</span>
          <span class="kpi-value">{{ money(totals.profit) }}</span>
        </div>
      </div>
      <div class="qd-rates">补录于 {{ snap.captured_at?.slice(0, 16).replace('T', ' ') }}</div>
    </section>

    <!-- 导出冻结：成本表同构——配置 tab + 分组行级表 + 合计条 -->
    <template v-else>
      <!-- L3 策略依据（仅推理流来源单显示） -->
      <section v-if="isReasoning && strategySnap.length" class="snap-block glass strat-block">
        <header class="sb-head"><h4>策略依据（溯源）</h4></header>
        <div v-for="s in strategySnap" :key="s.type" class="strat-item">
          <span class="strat-name">{{ s.name }}</span>
          <span class="strat-meta">v{{ s.version ?? '?' }}</span>
          <span class="strat-body">{{ formatStratBody(s) }}</span>
        </div>
      </section>

      <GroupedConfigDetail v-if="cfgNames.length" :configs="detailConfigs" />
    </template>
  </ResponsiveModal>
</template>

<style scoped>
.qd-meta { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; padding-bottom: 10px; }
.qd-tag { font-size: var(--cpq-font-size-sm); color: var(--cpq-accent-primary); }
.qd-rates { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.qd-hint { padding: 16px; font-size: 12.5px; color: var(--cpq-text-muted); }

.glass {
  background: var(--cpq-glass-bg, rgba(255,255,255,0.6));
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.5));
  border-radius: var(--cpq-radius-md);
  box-shadow: 0 1px 3px var(--cpq-shadow-color, rgba(0,0,0,0.06));
}

.snap-block { padding: 14px 16px; margin-bottom: 12px; }
.sb-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.sb-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }

/* 策略溯源 */
.strat-block .strat-item { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; padding: 5px 0; border-bottom: 1px dashed var(--cpq-divider, rgba(0,0,0,0.06)); }
.strat-block .strat-item:last-child { border-bottom: none; }
.strat-block .strat-name { font-weight: 600; color: var(--cpq-text-primary); min-width: 96px; }
.strat-block .strat-meta { font-size: var(--cpq-font-size-xs); color: var(--cpq-accent-primary); }
.strat-block .strat-body { color: var(--cpq-text-secondary); margin-left: auto; font-variant-numeric: tabular-nums; }

/* KPI（手工补录旧快照形态） */
.kpi-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.kpi { display: flex; flex-direction: column; gap: 4px; }
.kpi-label { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); text-transform: uppercase; letter-spacing: 0.4px; }
.kpi-value { font-size: var(--cpq-font-size-lg); font-weight: 700; color: var(--cpq-text-primary); font-variant-numeric: tabular-nums; }
.kpi-accent .kpi-value { color: var(--cpq-accent-primary); }
</style>
