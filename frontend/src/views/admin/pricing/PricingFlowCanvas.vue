<script setup lang="ts">
/** 定价策略画布 —— 加法定价引擎的可视化配置 + 演算器（pricing 域 tab）。
 *  上：VueFlow 固定流水线图（输入 → 平台基准 → +行业 → +区域 → +形态 → ×订单 → ×成本 → ×台数 → 保底封顶 → 输出），
 *     节点位置由公式顺序派生（不可拖/不可连线，拓扑固定）；点维度节点开抽屉改系数表。
 *  中：演算器——输入一笔 deal（平台/行业/区域/形态/订单/成本/台数）实时算目标毛利率 + breakdown + 建议售价 + 分项建议毛利。
 *  画布输出节点下方挂「BOM 分项毛利」伴生节点（part_margin，虚线连接=非公式步：deal 目标之上的品类二次分配）。
 *  下：margin_alert 卡（工作台低毛利弹窗配置）。
 *  signature：把「公式怎么叠加」一眼看清，把「这笔单该报多少毛利」一跑就出。 */
import { ref, computed, onMounted, markRaw } from 'vue'
import { VueFlow, useVueFlow, type Edge, type Node } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { usePricingRulesStore } from '@/stores/pricingRules'
import { suggestPrice, type PricingContext } from '@/stores/pricingEngine'
import {
  DIMENSION_MAP, PIPELINE_ORDER, PLATFORM_OPTIONS, INDUSTRY_OPTIONS, REGION_BUCKET_OPTIONS, FORM_OPTIONS,
  CUSTOMER_TYPE_OPTIONS, PART_MARGIN_META, PRICING_TEXT, type DimensionKey, type DrawerDimKey,
} from '@/constants/pricingMeta'
import DimensionNode from './DimensionNode.vue'
import DimensionDrawer from './DimensionDrawer.vue'
import MarginAlertEditor from './MarginAlertEditor.vue'

const store = usePricingRulesStore()
const nodeTypes: any = markRaw({ dim: DimensionNode })

// ── 维度系数摘要（节点上展示）──
function summarize(dimKey: DimensionKey, body: any): string {
  if (!body) return ''
  const cut = (arr: string[]) => arr.length > 4 ? [...arr.slice(0, 4), `+${arr.length - 4}`].join(' · ') : arr.join(' · ')
  const pp = (v: number) => `${v >= 0 ? '+' : ''}${v}`
  if (dimKey === 'platform_baseline') return cut(Object.entries(body).map(([k, v]: any) => `${k} ${v}%`))
  if (dimKey === 'industry_adj' || dimKey === 'form_adj') return cut(Object.entries(body).map(([k, v]: any) => `${k} ${pp(v)}`))
  if (dimKey === 'order_mult') return cut(Object.entries(body).map(([k, v]: any) => `${k} ×${v}`))
  if (dimKey === 'region_adj') {
    const f = body.factors || {}
    const norm = (v: any) => (typeof v === 'object' && v != null ? v : { pct: v, fixed_fee: 0 })
    return ['国内', '海外', '偏远'].map(b => {
      const { pct, fixed_fee } = norm(f[b]) as any
      const fee = Number(fixed_fee) > 0 ? ` 费${fixed_fee}` : ''
      return `${b} ${pp(Number(pct) || 0)}${fee}`
    }).join(' · ')
  }
  if (dimKey === 'cost_tier') {
    const tiers = body.tiers || []
    return tiers.map((t: any) => `${t.max == null ? '>兜底' : `≤${Math.round(t.max / 10000)}w`} ×${t.mult}`).join(' · ')
  }
  if (dimKey === 'qty_mult') {
    const bands = body.bands || []
    return bands.map((b: any) => `≥${b.min}台 ×${b.mult}`).join(' · ')
  }
  if (dimKey === 'guardrail') {
    const n = Array.isArray(body.tiers) ? body.tiers.length : 0
    return `保底 ${body.floor}% · 封顶 ${body.cap}%${n ? ` · ${n} 档分档` : ''}`
  }
  return ''
}

// ── 派生布局：输入 + 6 维度 + 输出，单行左→右 ──
const X0 = 0, DX = 230, Y = 80
const graph = computed(() => {
  const dims = store.dims
  const nodes: Node[] = []
  const edges: Edge[] = []
  const seq: Array<{ id: string; kind: 'input' | 'dim' | 'output'; dimKey?: DimensionKey; accent: string }> = [
    { id: 'input', kind: 'input', accent: '#8a909a' },
    ...PIPELINE_ORDER.map(k => { const d = DIMENSION_MAP[k]; return { id: k, kind: 'dim' as const, dimKey: k, accent: ACCENT[d.opKind] } }),
    { id: 'output', kind: 'output', accent: '#1677ff' },
  ]
  seq.forEach((s, i) => {
    const def = s.dimKey ? DIMENSION_MAP[s.dimKey] : null
    nodes.push({
      id: s.id, type: 'dim', position: { x: X0 + i * DX, y: Y },
      data: s.kind === 'dim' && def && s.dimKey
        ? { kind: 'dim', dimKey: s.dimKey, label: def.label, opKind: def.opKind, sign: def.sign, summary: summarize(s.dimKey, dims[s.dimKey]) }
        : { kind: s.kind, label: s.kind === 'input' ? PRICING_TEXT.inputNode : PRICING_TEXT.outputNode },
    } as Node)
  })
  for (let i = 0; i < seq.length - 1; i++) {
    edges.push({
      id: `e-${seq[i].id}-${seq[i + 1].id}`, source: seq[i].id, target: seq[i + 1].id,
      type: 'smoothstep', animated: true,
      style: { stroke: seq[i].accent, strokeWidth: 2 },
    } as Edge)
  }
  // 分项毛利 = 输出侧伴生节点(非公式步,虚线连接):流水线输出一个 deal 目标,它做品类二次分配
  const outX = X0 + (seq.length - 1) * DX
  nodes.push({
    id: 'part_margin', type: 'dim', position: { x: outX, y: Y + 130 },
    data: { kind: 'dim', dimKey: 'part_margin', label: PART_MARGIN_META.label, sign: '±', accent: '#1677ff', summary: partSummary.value },
  } as Node)
  edges.push({
    id: 'e-output-part', source: 'output', target: 'part_margin',
    type: 'smoothstep', animated: false,
    style: { stroke: '#8a909a', strokeWidth: 1.5, strokeDasharray: '5 4' },
  } as Edge)
  return { nodes, edges }
})

const ACCENT: Record<string, string> = { base: '#1677ff', add: '#52c9a0', mult: '#fa8c16', clamp: '#8b5cf6' }

// ── 抽屉（流水线维度节点点击 + 分项毛利卡点击共用）──
const drawerOpen = ref(false)
const drawerKey = ref<DrawerDimKey | null>(null)
const drawerId = ref<number | null>(null)
const drawerBody = ref<any>(null)
const { onNodeClick } = useVueFlow()
onNodeClick(({ node }) => {
  const dk = node.data?.dimKey as string | undefined
  if (!dk) return
  if (dk === 'part_margin') { openPartDrawer(); return }   // 输出侧伴生节点 → 分项毛利抽屉
  const dimKey = dk as DimensionKey
  drawerKey.value = dimKey
  drawerId.value = store.dimStrategies[dimKey]?.id ?? null
  drawerBody.value = store.dims[dimKey]
  drawerOpen.value = true
})
/** BOM 分项毛利（part_margin，非流水线）——摘要卡点击开同一抽屉 */
const partSummary = computed(() => {
  const entries = Object.entries(store.partMargin || {})
  if (!entries.length) return '未配置（全部品类用 deal 目标毛利）'
  return entries.map(([k, v]) => `${k} ${Number(v) >= 0 ? '+' : ''}${v}`).join(' · ')
})
function openPartDrawer() {
  drawerKey.value = 'part_margin'
  drawerId.value = store.partMarginState.id
  drawerBody.value = store.partMargin
  drawerOpen.value = true
}
function onSaved() {
  store.invalidatePricingRules()
  store.ensurePricingRules()
}

onMounted(() => store.ensurePricingRules())

// ── 演算器 ──
const calc = ref<PricingContext>({ platform: 'Polaris', industry: '政企信息化', region: '国内', customerType: '集采项目', form: '2U', cost: 120000, qty: 1 })
const calcResult = computed(() => store.computeTargetMargin(calc.value))
const calcPrice = computed(() => suggestPrice(calc.value.cost ?? null, calcResult.value.target, calcResult.value.fixedFee))
const calcParts = computed(() => store.computePartMargins(calcResult.value.target))
function stepText(s: any): string {
  const def = DIMENSION_MAP[s.dimKey as DimensionKey]
  if (s.dimKey === 'guardrail') return `${s.value}`
  if (s.value === '—') return '—'
  if (def?.opKind === 'mult') return `${s.matched ? s.matched + ' ' : ''}×${s.value}`
  if (def?.opKind === 'add') return `${s.matched || ''} ${s.value >= 0 ? '+' : ''}${s.value}`.trim()
  return `${s.matched || ''} ${s.value}%`.trim()
}
</script>

<template>
  <div class="pf-canvas">
    <div class="pf-toolbar">
      <span class="pf-tip">公式：(平台基准 + 行业 + 区域 + 形态) × 订单系数 × 成本阶梯 × 台数折扣 → 保底封顶（可按订单类型分档）。实线=公式步；输出下方虚线=分项毛利（品类二次分配）。点节点改系数。</span>
    </div>

    <div class="pf-flow-wrap">
      <VueFlow
        :nodes="graph.nodes"
        :edges="graph.edges"
        :node-types="nodeTypes"
        :fit-view-on-init="true"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :elements-selectable="true"
        :min-zoom="0.3" :max-zoom="1.8"
      >
        <Background :gap="20" :size="1" pattern-color="rgba(127,127,127,0.16)" />
        <Controls :show-interactive="false" />
      </VueFlow>
    </div>

    <!-- 演算器 -->
    <a-collapse :default-active-key="['calc']" class="pf-calc">
      <a-collapse-panel key="calc" header="🎯 演算器：输入一笔 deal，算目标毛利率与建议售价">
        <div class="pf-calc-grid">
          <a-form layout="vertical" size="small">
            <div class="pf-calc-row">
              <a-form-item label="平台"><a-select v-model:value="calc.platform" :options="PLATFORM_OPTIONS" style="width:100%" /></a-form-item>
              <a-form-item label="行业"><a-select v-model:value="calc.industry" :options="INDUSTRY_OPTIONS" style="width:100%" /></a-form-item>
              <a-form-item label="区域(桶)"><a-select v-model:value="calc.region" :options="REGION_BUCKET_OPTIONS" style="width:100%" /></a-form-item>
              <a-form-item label="机箱形态"><a-select v-model:value="calc.form" :options="FORM_OPTIONS" style="width:100%" /></a-form-item>
              <a-form-item label="订单类型"><a-select v-model:value="calc.customerType" :options="CUSTOMER_TYPE_OPTIONS" style="width:100%" /></a-form-item>
              <a-form-item label="销售台数"><a-input-number v-model:value="calc.qty" :min="0" :step="1" style="width:100%" /></a-form-item>
              <a-form-item label="BOM 成本(元)"><a-input-number v-model:value="calc.cost" :min="0" :step="10000" style="width:100%" /></a-form-item>
            </div>
          </a-form>
          <div class="pf-result">
            <div class="pf-result-head">
              <div class="pf-target">
                <span class="pf-target-label">目标毛利率</span>
                <span class="pf-target-val" :class="{ clamped: calcResult.clamped }">{{ calcResult.target }}%</span>
                <span v-if="calcResult.clamped" class="pf-clamp-tag">已触 {{ calcResult.target === calcResult.floor ? '保底' : '封顶' }}</span>
              </div>
              <div v-if="calcPrice != null" class="pf-price">
                建议售价 <b>{{ calcPrice.toLocaleString() }}</b> 元
                <span v-if="calcResult.fixedFee > 0" class="pf-fee-note">（含海外固定费 {{ calcResult.fixedFee.toLocaleString() }}/台）</span>
              </div>
            </div>
            <div class="pf-breakdown">
              <div v-for="s in calcResult.breakdown" :key="s.dimKey" class="pf-step" :class="{ skipped: s.skipped }">
                <span class="pf-step-label">{{ DIMENSION_MAP[s.dimKey as DimensionKey]?.label }}</span>
                <span class="pf-step-op">{{ stepText(s) }}</span>
                <span class="pf-step-sub">→ {{ s.subtotal }}%</span>
                <span v-if="s.note" class="pf-step-note">{{ s.note }}</span>
              </div>
            </div>
            <!-- 分项建议毛利（deal 目标 ± 品类修正，夹红线）-->
            <div class="pf-parts">
              <div class="pf-parts-title">分项建议毛利（deal 目标 {{ calcParts.default }}% ± 品类修正，每个夹 [{{ calcResult.floor }}~{{ calcResult.cap }}%]）</div>
              <div v-if="calcParts.parts.length" class="pf-parts-row">
                <span v-for="p in calcParts.parts" :key="p.category" class="pf-part-chip">
                  {{ p.category }} <b>{{ p.margin }}%</b><i v-if="p.adj !== 0">{{ p.adj > 0 ? '+' : '' }}{{ p.adj }}</i>
                </span>
                <span class="pf-part-chip pf-part-default">其他 <b>{{ calcParts.default }}%</b></span>
              </div>
              <div v-else class="pf-parts-empty">未配置分项修正，全部品类用 deal 目标 {{ calcParts.default }}%</div>
            </div>
          </div>
        </div>
      </a-collapse-panel>
    </a-collapse>

    <!-- 利润率告警配置（独立策略 margin_alert，工作台低毛利弹窗 SSOT）-->
    <MarginAlertEditor />

    <DimensionDrawer v-model:open="drawerOpen" :dim-key="drawerKey" :initial-body="drawerBody" :strategy-id="drawerId" @saved="onSaved" />
  </div>
</template>

<style scoped>
.pf-canvas { display: flex; flex-direction: column; gap: 10px; }
.pf-toolbar { padding: 0 2px; }
.pf-tip { font-size: 12px; color: var(--cpq-text-muted); }

.pf-flow-wrap {
  width: 100%; height: 300px;
  border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-overlay-w3, transparent);
  border: 1px solid var(--cpq-glass-border, rgba(0,0,0,.08));
  overflow: hidden;
}

.pf-calc :deep(.ant-collapse-content) { background: transparent; }
.pf-calc-grid { display: flex; gap: 20px; flex-wrap: wrap; }
.pf-calc-grid > .ant-form { flex: 1 1 360px; min-width: 320px; }
.pf-calc-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.pf-result { flex: 1 1 320px; min-width: 300px; }

.pf-result-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.pf-target { display: flex; align-items: baseline; gap: 8px; }
.pf-target-label { font-size: 12px; color: var(--cpq-text-muted); }
.pf-target-val { font-size: 28px; font-weight: 700; color: var(--cpq-accent-primary, #1677ff); font-variant-numeric: tabular-nums; }
.pf-target-val.clamped { color: var(--cpq-accent-warning, #fa8c16); }
.pf-clamp-tag { font-size: 11px; padding: 1px 7px; border-radius: 6px; background: var(--cpq-overlay-w10); color: var(--cpq-accent-warning, #fa8c16); }
.pf-price { font-size: 13px; color: var(--cpq-text-secondary); }
.pf-price b { color: var(--cpq-accent-success, #52c41a); font-variant-numeric: tabular-nums; }

.pf-breakdown { display: flex; flex-direction: column; gap: 3px; }
.pf-step { display: grid; grid-template-columns: 92px 1fr 56px; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; border-bottom: 1px dashed var(--cpq-glass-border, rgba(0,0,0,.06)); }
.pf-step.skipped { opacity: .5; }
.pf-step-label { color: var(--cpq-text-secondary); }
.pf-step-op { color: var(--cpq-text-primary); font-family: ui-monospace, monospace; }
.pf-step-sub { text-align: right; font-weight: 600; color: var(--cpq-accent-primary, #1677ff); font-variant-numeric: tabular-nums; }
.pf-step-note { grid-column: 2 / 4; font-size: 11px; color: var(--cpq-text-muted); }
.pf-fee-note { font-size: 11px; color: var(--cpq-text-muted); }

/* 分项建议毛利 */
.pf-parts { margin-top: 10px; }
.pf-parts-title { font-size: 12px; color: var(--cpq-text-muted); margin-bottom: 6px; }
.pf-parts-row { display: flex; flex-wrap: wrap; gap: 6px; }
.pf-part-chip {
  font-size: 12px; padding: 2px 10px; border-radius: 8px;
  background: var(--cpq-overlay-w6); color: var(--cpq-text-secondary);
  display: inline-flex; align-items: baseline; gap: 4px;
}
.pf-part-chip b { color: var(--cpq-accent-primary, #1677ff); font-variant-numeric: tabular-nums; }
.pf-part-chip i { font-style: normal; font-size: 11px; color: var(--cpq-text-muted); }
.pf-part-default { border: 1px dashed var(--cpq-glass-border); }
.pf-parts-empty { font-size: 12px; color: var(--cpq-text-muted); }
</style>
