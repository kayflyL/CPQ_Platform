<script setup lang="ts">
/** 报价单成本抽屉。
 * 两种数据形态：
 *  - 完整快照（导出冻结）：{totals, configs, rates}。多配置时「每个配置一个整机汇总」
 *    （各配置利润率独立，不再跨配置混算）；totals 仅作项目总计（Σ 单台 × qty）备用。
 *  - 手工补录快照（旧数据）：{manual:true, captured_at, totals} → 只渲染一个整机汇总（无 configs）。
 * 仅保留只读展示；不再支持补录/编辑。 */
import { computed, ref, watch } from 'vue'
import { money } from '@/utils/quoteCommon'
import { useAuthStore } from '@/store/auth'
import { baseConfigApi, catalogApi } from '@/api/serverConfig'

const props = defineProps<{
  open: boolean
  quotation: any
  excelLoading?: boolean
  reparseLoading?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'view-excel'): void
  (e: 'reparse'): void
  (e: 'unfreeze'): void
}>()

// 解冻已导出报价单：需 action.quote.unfreeze 权限（「用户与权限」页可分配）；
// 已发送的单需先退回审批节点，前端只置灰，最终以后端 409 为准。
const auth = useAuthStore()
const canUnfreeze = computed(() => auth.can('action.quote.unfreeze') && !!props.quotation?.exported_at)
const unfreezeBlocked = computed(() => !!props.quotation?.submitted_at)

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
  [() => props.open, () => props.quotation?.quotation_id],
  ([open]) => { if (open) cfgNames.value.forEach((n) => void ensureLiveInfo(n)) },
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
function close() {
  emit('update:open', false)
}
</script>

<template>
  <a-drawer
    :open="open"
    @update:open="emit('update:open', $event)"
    :width="520"
    placement="right"
    class="cost-drawer"
  >
    <template #title>
      <div class="drawer-title">
        <span class="dt-name">{{ quotation?.quotation_name || '报价单' }}</span>
        <span class="dt-tag">
          <template v-if="hasSnapshot && isManual">手工补录 · {{ snap.captured_at?.slice(0, 10) || '—' }}</template>
          <template v-else-if="hasSnapshot">已导出 · {{ quotation?.exported_at?.slice(0, 10) || '—' }}</template>
          <template v-else>无成本数据</template>
        </span>
      </div>
    </template>

    <!-- 无成本数据（历史导入或未导出）：仅提示，不再支持补录 -->
    <div v-if="!hasSnapshot" class="manual-form glass">
      <p class="mf-hint">该报价单暂无成本快照数据。</p>
    </div>

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
        <div class="rates">补录于 {{ snap.captured_at?.slice(0, 16).replace('T', ' ') }}</div>
      </section>

      <!-- 导出冻结：每配置独立整机汇总（各配置利润率不同，不跨配置混算） -->
      <template v-else>
        <div v-if="snap.rates" class="rates-line">
          汇率 {{ snap.rates.usd_to_rmb }} · 税率 {{ (snap.rates.tax_rate * 100).toFixed(0) }}% · 冻结于 {{ snap.captured_at?.slice(0, 16).replace('T', ' ') }}
        </div>

        <!-- L3 策略依据（仅推理流来源单显示） -->
        <section v-if="isReasoning && strategySnap.length" class="snap-block glass strat-block">
          <header class="sb-head"><h4>策略依据（溯源）</h4></header>
          <div v-for="s in strategySnap" :key="s.type" class="strat-item">
            <span class="strat-name">{{ s.name }}</span>
            <span class="strat-meta">v{{ s.version ?? '?' }}</span>
            <span class="strat-body">{{ formatStratBody(s) }}</span>
          </div>
        </section>

        <section v-for="name in cfgNames" :key="name" class="snap-block glass">
          <header class="sb-head">
            <h4>{{ name }}</h4>
            <span class="sb-qty">×{{ snap.configs[name].qty || 0 }} 台</span>
          </header>

          <!-- 机型信息：型号 / 机箱形态 / 盘位 / 系列（快照冻结优先，旧快照现查补齐） -->
          <div class="mi-grid">
            <div class="mi"><span class="mi-k">服务器型号</span><span class="mi-v mi-name">{{ modelInfoMap[name].server_model || '—' }}</span></div>
            <div class="mi"><span class="mi-k">机箱形态</span><span class="mi-v">{{ modelInfoMap[name].form || '—' }}</span></div>
            <div class="mi"><span class="mi-k">盘位</span><span class="mi-v">{{ modelInfoMap[name].bays ?? '—' }}</span></div>
            <div class="mi"><span class="mi-k">系列</span><span class="mi-v">{{ modelInfoMap[name].series || '—' }}</span></div>
          </div>
          <div v-if="modelInfoMap[name].base_config_name" class="mi-note">基准配置 · {{ modelInfoMap[name].base_config_name }}</div>
          <div v-if="modelInfoMap[name].description" class="mi-note mi-desc" :title="modelInfoMap[name].description">{{ modelInfoMap[name].description }}</div>

          <!-- 整机汇总 KPI（单台） -->
          <div class="kpi-row">
            <div class="kpi">
              <span class="kpi-label">整机成本</span>
              <span class="kpi-value">{{ money(snap.configs[name].totals.totalCost) }}</span>
            </div>
            <div class="kpi kpi-accent">
              <span class="kpi-label">整机利润率</span>
              <span class="kpi-value">{{ pct(snap.configs[name].totals.marginPct) }}</span>
            </div>
            <div class="kpi">
              <span class="kpi-label">整机售价</span>
              <span class="kpi-value">{{ money(snap.configs[name].totals.totalSales) }}</span>
            </div>
          </div>

          <!-- 分段明细 -->
          <table class="ct">
            <thead><tr><th>分段</th><th>成本</th><th>售价</th><th>利润率</th></tr></thead>
            <tbody>
              <tr>
                <td>机箱 (L6)</td>
                <td>{{ money(snap.configs[name].totals.l6Cost) }}</td>
                <td>{{ money(snap.configs[name].totals.l6Sales) }}</td>
                <td>{{ pct(marginOf(snap.configs[name].totals.l6Cost, snap.configs[name].totals.l6Sales)) }}</td>
              </tr>
              <tr>
                <td>KP 配件</td>
                <td>{{ money(snap.configs[name].totals.kpCost) }}</td>
                <td>{{ money(snap.configs[name].totals.kpSales) }}</td>
                <td>{{ pct(marginOf(snap.configs[name].totals.kpCost, snap.configs[name].totals.kpSales)) }}</td>
              </tr>
              <tr>
                <td>质保</td>
                <td>{{ money(snap.configs[name].totals.warrantyCost) }}</td>
                <td>{{ money(snap.configs[name].totals.warrantySales) }}</td>
                <td>{{ pct(marginOf(snap.configs[name].totals.warrantyCost, snap.configs[name].totals.warrantySales)) }}</td>
              </tr>
            </tbody>
          </table>

          <!-- KP 配件明细：逐项利润率 -->
          <details v-if="snap.configs[name].kp_items && snap.configs[name].kp_items.length" class="section-drill">
            <summary>KP 配件明细（{{ snap.configs[name].kp_items.length }} 项）</summary>
            <table class="ct kp-item-table">
              <thead>
                <tr><th>类别</th><th>配件</th><th>数量</th><th>成本</th><th>售价</th><th>利润率</th></tr>
              </thead>
              <tbody>
                <tr v-for="(it, i) in snap.configs[name].kp_items" :key="i">
                  <td>{{ it.cat }}</td>
                  <td>{{ it.name || '—' }}</td>
                  <td>{{ it.qty }}</td>
                  <td>{{ money(it.cost) }}</td>
                  <td>{{ money(it.sales) }}</td>
                  <td>{{ pct(it.margin) }}</td>
                </tr>
              </tbody>
            </table>
          </details>
        </section>
      </template>

    <template #footer>
      <div class="drawer-footer">
        <template v-if="canUnfreeze">
          <a-tooltip v-if="unfreezeBlocked" title="该报价单已发送，请先退回审批节点后再解冻">
            <span><a-button disabled>解冻并编辑</a-button></span>
          </a-tooltip>
          <a-button v-else type="primary" @click="emit('unfreeze')">解冻并编辑</a-button>
        </template>
        <template v-if="hasSnapshot">
          <a-button :loading="excelLoading" @click="emit('view-excel')">查看 Excel</a-button>
          <a-button v-if="!isManual" type="primary" ghost :loading="reparseLoading" @click="emit('reparse')">复制为草稿</a-button>
        </template>
        <a-button @click="close">关闭</a-button>
      </div>
    </template>
  </a-drawer>
</template>

<style scoped>
.drawer-title { display: flex; flex-direction: column; gap: 2px; }
.dt-name { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary, #1f2937); }
.dt-tag { font-size: 12px; color: var(--cpq-accent-primary, #1677FF); }

.glass {
  background: var(--cpq-glass-bg, rgba(255,255,255,0.6));
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-glass-border, rgba(255,255,255,0.5));
  border-radius: 12px;
  box-shadow: 0 1px 3px var(--cpq-shadow-color, rgba(0,0,0,0.06));
}

.manual-form { padding: 16px; }
.mf-hint { font-size: 12.5px; color: var(--cpq-text-muted, #6E7582); margin: 0 0 14px; line-height: 1.6; }
.mf-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.mf-row label { font-size: 12px; color: var(--cpq-text-secondary, #4b5563); font-weight: 500; }
.mf-preview { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px; padding-top: 12px; border-top: 1px solid var(--cpq-divider, rgba(0,0,0,0.06)); }

.rates-line { font-size: 11px; color: var(--cpq-text-muted, #6E7582); padding: 2px 2px 8px; }

.snap-block { padding: 14px 16px; margin-bottom: 12px; }
.sb-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.sb-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #1f2937); }
.sb-qty { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }

/* 机型信息（型号/形态/盘位/系列）：与工作台机箱卡同字段同口径 */
.mi-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 5px 14px;
  padding-bottom: 10px; margin-bottom: 10px;
  border-bottom: 1px dashed var(--cpq-divider, rgba(0,0,0,0.06));
}
.mi { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; min-width: 0; }
.mi-k { font-size: 11px; color: var(--cpq-text-muted, #6E7582); flex-shrink: 0; }
.mi-v { font-size: 12.5px; color: var(--cpq-text-primary, #1f2937); font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mi-name { font-weight: 600; }
.mi-note { font-size: 11.5px; color: var(--cpq-text-muted, #6E7582); line-height: 1.5; margin: -4px 0 8px; }
.mi-desc { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.kpi-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.kpi { display: flex; flex-direction: column; gap: 4px; }
.kpi-label { font-size: 11px; color: var(--cpq-text-muted, #6E7582); text-transform: uppercase; letter-spacing: 0.4px; }
.kpi-value { font-size: 16px; font-weight: 700; color: var(--cpq-text-primary, #1f2937); font-variant-numeric: tabular-nums; }
.kpi-accent .kpi-value { color: var(--cpq-accent-primary, #1677FF); }
.rates { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }

.ct { width: 100%; border-collapse: collapse; font-size: 12.5px; font-variant-numeric: tabular-nums; }
.ct th { text-align: right; font-weight: 500; color: var(--cpq-text-muted, #6E7582); padding: 4px 6px; border-bottom: 1px solid var(--cpq-divider, rgba(0,0,0,0.06)); }
.ct th:first-child { text-align: left; }
.ct td { text-align: right; padding: 5px 6px; color: var(--cpq-text-secondary, #4b5563); }
.ct td:first-child { text-align: left; color: var(--cpq-text-primary, #1f2937); }

/* KP 配件明细：类别在第一列，全表（表头+单元格）统一左对齐，避免右对齐数字与左对齐文字混排 */
.kp-item-table th,
.kp-item-table td { text-align: left; }
.kp-item-table th { white-space: nowrap; }
.kp-item-table td:first-child { color: var(--cpq-text-secondary, #4b5563); }
.kp-item-table td:nth-child(2) { color: var(--cpq-text-primary, #1f2937); }

.section-drill { margin-top: 10px; }
.section-drill summary { cursor: pointer; font-size: 12px; color: var(--cpq-text-muted, #6E7582); }

.strat-block .strat-item { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; padding: 5px 0; border-bottom: 1px dashed var(--cpq-divider, rgba(0,0,0,0.06)); }
.strat-block .strat-item:last-child { border-bottom: none; }
.strat-block .strat-name { font-weight: 600; color: var(--cpq-text-primary, #1f2937); min-width: 96px; }
.strat-block .strat-meta { font-size: 11px; color: var(--cpq-accent-primary, #1677FF); }
.strat-block .strat-body { color: var(--cpq-text-secondary, #4b5563); margin-left: auto; font-variant-numeric: tabular-nums; }

.drawer-footer { display: flex; gap: 8px; justify-content: flex-end; }
</style>
