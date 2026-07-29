<script setup lang="ts">
/** 报价单成本抽屉。
 * 两种数据形态：
 *  - 完整快照（导出冻结）：{totals, configs, rates}。多配置时「每个配置一个整机汇总」
 *    （各配置利润率独立，不再跨配置混算）；totals 仅作项目总计（Σ 单台 × qty）备用。
 *  - 手工补录快照：{manual:true, captured_at, totals} → 只渲染一个整机汇总（无 configs）。
 * 无快照时（历史导入单）切换为录入模式。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'

const props = defineProps<{
  open: boolean
  quotation: any
  excelLoading?: boolean
  reparseLoading?: boolean
  saveLoading?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'view-excel'): void
  (e: 'reparse'): void
  (e: 'save-cost', snapshot: Record<string, any>): void
}>()

const snap = computed<any>(() => props.quotation?.cost_snapshot || null)
const hasSnapshot = computed(() => !!snap.value)
const isManual = computed(() => !!snap.value?.manual)
// L3 策略溯源（仅推理流来源的报价单显示依据）
const isReasoning = computed(() => props.quotation?.source === 'reasoning')
const strategySnap = computed<any[]>(() => props.quotation?.strategy_snapshot || [])
function formatStratBody(s: any): string {
  if (s.type === 'pricing_scenario') {
    const rb = s.body?.rule_body
    const tier = rb ? `底线 ${rb.floor}% / 标准 ${rb.standard}% / 优质 ${rb.premium}%` : ''
    return `${s.body?.description || '(无说明)'}${tier ? ' · ' + tier : ''}`
  }
  if (s.type === 'margin_tier') { const b = s.body || {}; return `底线 ${b.floor}% / 标准 ${b.standard}% / 优质 ${b.premium}%` }
  if (s.type === 'warranty_markup') { const b = s.body || {}; return `1年${b.y1}% / 3年${b.y3}% / 5年${b.y5}%` }
  return JSON.stringify(s.body || {})
}

const totals = computed(() => snap.value?.totals || {})
const cfgNames = computed<string[]>(() => (snap.value?.configs ? Object.keys(snap.value.configs) : []))

// 手工录入态
const inputCost = ref<number | null>(null)
const inputSales = ref<number | null>(null)
// 已有手工补录时点「编辑」切回录入态；保存成功（snap 变化）后自动切回展示
const editing = ref(false)
const previewProfit = computed(() => (inputSales.value ?? 0) - (inputCost.value ?? 0))
const previewMargin = computed(() => {
  const c = inputCost.value ?? 0
  if (c <= 0) return 0
  return (previewProfit.value / c) * 100
})

// 切换报价单 → 清空输入 + 回到展示态
watch(() => props.quotation?.quotation_id, () => {
  inputCost.value = null
  inputSales.value = null
  editing.value = false
})

// 保存成功后 snap 引用变化 → 退出编辑态（失败时保持编辑，方便再改）
watch(snap, () => { editing.value = false })

function requestEdit() {
  inputCost.value = totals.value.totalCost ?? null
  inputSales.value = totals.value.totalSales ?? null
  editing.value = true
}

function money(n: any): string {
  const v = Number(n || 0)
  return '¥' + v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}
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
function saveSnapshot() {
  const cost = Number(inputCost.value || 0)
  const sales = Number(inputSales.value || 0)
  if (cost <= 0 && sales <= 0) {
    message.warning('请至少输入整机成本或整机售价')
    return
  }
  const profit = sales - cost
  const marginPct = cost > 0 ? Math.round((profit / cost) * 10000) / 100 : 0
  emit('save-cost', {
    manual: true,
    captured_at: new Date().toISOString(),
    totals: { totalCost: cost, totalSales: sales, profit, marginPct }
  })
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
          <template v-else>待补录成本</template>
        </span>
      </div>
    </template>

    <!-- 录入模式：无快照，或对已有手工补录点「编辑」后 -->
    <div v-if="!hasSnapshot || (isManual && editing)" class="manual-form glass">
      <p class="mf-hint">{{ editing ? '修改整机成本与售价，保存后将覆盖原补录数据。' : '该报价单无成本数据。手动录入整机级成本与售价，利润额 / 利润率自动计算。' }}</p>
      <div class="mf-row">
        <label>整机成本</label>
        <a-input-number v-model:value="inputCost" :min="0" :step="1000" placeholder="如 120000" style="width:100%">
          <template #prefix>¥</template>
        </a-input-number>
      </div>
      <div class="mf-row">
        <label>整机售价</label>
        <a-input-number v-model:value="inputSales" :min="0" :step="1000" placeholder="如 150000" style="width:100%">
          <template #prefix>¥</template>
        </a-input-number>
      </div>
      <div class="mf-preview">
        <div class="kpi">
          <span class="kpi-label">利润额</span>
          <span class="kpi-value">{{ money(previewProfit) }}</span>
        </div>
        <div class="kpi kpi-accent">
          <span class="kpi-label">利润率</span>
          <span class="kpi-value">{{ pct(previewMargin) }}</span>
        </div>
      </div>
    </div>

    <template v-else>
      <!-- 手工补录快照：只有项目级 totals，无 configs -->
      <section v-if="isManual" class="snap-block glass">
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
                <tr><th>配件</th><th>分类</th><th>数量</th><th>成本</th><th>售价</th><th>利润率</th></tr>
              </thead>
              <tbody>
                <tr v-for="(it, i) in snap.configs[name].kp_items" :key="i">
                  <td>{{ it.name || '—' }}</td>
                  <td class="td-text">{{ it.cat }}</td>
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
    </template>

    <template #footer>
      <div class="drawer-footer">
        <template v-if="!hasSnapshot || (isManual && editing)">
          <a-button v-if="editing" @click="editing = false">取消</a-button>
          <a-button type="primary" :loading="saveLoading" @click="saveSnapshot">保存成本</a-button>
        </template>
        <template v-else>
          <a-button :loading="excelLoading" @click="emit('view-excel')">查看 Excel</a-button>
          <a-button v-if="isManual" type="primary" ghost @click="requestEdit">编辑</a-button>
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

.kp-item-table td.td-text { text-align: left; }

.section-drill { margin-top: 10px; }
.section-drill summary { cursor: pointer; font-size: 12px; color: var(--cpq-text-muted, #6E7582); }

.strat-block .strat-item { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; padding: 5px 0; border-bottom: 1px dashed var(--cpq-divider, rgba(0,0,0,0.06)); }
.strat-block .strat-item:last-child { border-bottom: none; }
.strat-block .strat-name { font-weight: 600; color: var(--cpq-text-primary, #1f2937); min-width: 96px; }
.strat-block .strat-meta { font-size: 11px; color: var(--cpq-accent-primary, #1677FF); }
.strat-block .strat-body { color: var(--cpq-text-secondary, #4b5563); margin-left: auto; font-variant-numeric: tabular-nums; }

.drawer-footer { display: flex; gap: 8px; justify-content: flex-end; }
</style>
