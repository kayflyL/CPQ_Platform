/**
 * 定价规则 Pinia Store — 加法定价引擎的加载/消费层。
 *
 * 数据源：
 *   - strategies pricing.<dim>：8 条维度系数表（platform_baseline/industry_adj/region_adj/form_adj/
 *     order_mult/cost_tier/qty_mult/guardrail）；缺失维度回退 constants/pricingMeta 的 DEFAULT_DIM_BODIES
 *   - strategies pricing.part_margin：BOM 分项毛利（deal 目标毛利上的品类修正，非流水线）
 *   - strategies pricing.warranty_markup：维保加价（独立维度，保留）
 *   - strategies pricing.margin_alert：利润率告警（开关+门槛+文案，工作台低毛利弹窗）
 *
 * 求值本身在 stores/pricingEngine（纯 TS，可独立单测）；本 store 只负责加载 + 薄封装 + 溯源快照。
 * 策略中心画布/抽屉 CRUD 后调 invalidatePricingRules → ensure 重新拉。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { strategyApi } from '@/api/strategies'
import { computeTargetMargin as evalTargetMargin, computePartMargins as evalPartMargins, resolveGuardrail, type PricingContext, type PricingDims, type PricingResult, type PartMargin } from '@/stores/pricingEngine'
import { PIPELINE_ORDER, DEFAULT_DIM_BODIES, DEFAULT_MARGIN_ALERT, DEFAULT_PART_MARGIN, type MarginAlertBody } from '@/constants/pricingMeta'

export const usePricingRulesStore = defineStore('pricingRules', () => {
  // 维度策略原始行（type → strategy），未持久化的维度缺失
  const _dimRows = ref<Record<string, any>>({})
  const _warrantyMarkup = ref<{ y1: number; y3: number; y5: number; y7?: number } | null>(null)
  // 利润率告警（独立策略 type=margin_alert）
  const _marginAlert = ref<MarginAlertBody>({ ...DEFAULT_MARGIN_ALERT })
  const _marginAlertId = ref<number | null>(null)
  // BOM 分项毛利（独立策略 type=part_margin，非流水线）
  const _partMarginRow = ref<any>(null)

  const _loaded = ref(false)
  let _promise: Promise<void> | null = null

  /** 加载定价规则（幂等，多次调用只请求一次） */
  async function ensurePricingRules(): Promise<void> {
    if (_loaded.value) return
    if (!_promise) {
      _promise = Promise.all([
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'warranty_markup' }),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'margin_alert' }),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'part_margin' }),
        ...PIPELINE_ORDER.map(k => strategyApi.list({ domain: 'pricing', status: 'active', type: k })),
      ])
        .then(([wmRes, maRes, pmRes, ...dimReses]) => {
          const wm = wmRes.strategies?.[0]?.body
          if (wm && typeof wm === 'object') {
            _warrantyMarkup.value = { y1: wm.y1 ?? 0, y3: wm.y3 ?? 0, y5: wm.y5 ?? 0, ...(wm.y7 != null ? { y7: Number(wm.y7) } : {}) }
          }
          const maStrat = maRes.strategies?.[0]
          const ma = maStrat?.body
          if (ma && typeof ma === 'object') {
            _marginAlertId.value = maStrat.id ?? null
            _marginAlert.value = {
              enabled: ma.enabled !== false,
              threshold: Number.isFinite(Number(ma.threshold)) ? Number(ma.threshold) : DEFAULT_MARGIN_ALERT.threshold,
              title: typeof ma.title === 'string' && ma.title.trim() ? ma.title : DEFAULT_MARGIN_ALERT.title,
              content: typeof ma.content === 'string' && ma.content.trim() ? ma.content : DEFAULT_MARGIN_ALERT.content,
            }
          }
          _partMarginRow.value = pmRes.strategies?.[0] || null
          const rows: Record<string, any> = {}
          PIPELINE_ORDER.forEach((k, i) => {
            const s = dimReses[i]?.strategies?.[0]
            if (s) rows[k] = s
          })
          _dimRows.value = rows
        })
        .catch(() => {})
        .finally(() => { _loaded.value = true })
    }
    return _promise
  }

  /** 失效缓存：策略中心 CRUD 后调用，下次 ensure 重新拉 */
  function invalidatePricingRules(): void {
    _loaded.value = false
    _promise = null
  }

  /** 维度系数表：DB 行优先，缺失回退 DEFAULT_DIM_BODIES（未 seed 也能用） */
  const dims = computed<PricingDims>(() => {
    const out: any = {}
    for (const k of PIPELINE_ORDER) {
      const row = _dimRows.value[k]
      out[k] = row?.body != null ? row.body : (DEFAULT_DIM_BODIES as any)[k]
    }
    return out
  })

  /** 维度原始策略行（抽屉按 type 取 id 判 create/update；未持久化为 undefined） */
  const dimStrategies = computed(() => _dimRows.value)

  /** 跑加法引擎：ctx → 目标毛利率 + breakdown */
  function computeTargetMargin(ctx: PricingContext): PricingResult {
    return evalTargetMargin(ctx, dims.value)
  }

  /** 保底封顶（引擎 clamp 边界） */
  function getGuardrail(): { floor: number; cap: number } {
    const g: any = dims.value.guardrail || (DEFAULT_DIM_BODIES as any).guardrail
    const floor = Number(g?.floor); const cap = Number(g?.cap)
    return { floor: Number.isFinite(floor) ? floor : 7, cap: Number.isFinite(cap) ? cap : 30 }
  }

  /** BOM 分项毛利修正（DB part_margin 优先，缺失回退 DEFAULT_PART_MARGIN；品类→±百分点） */
  const partMargin = computed<Record<string, number>>(() => {
    const b = _partMarginRow.value?.body
    return b && typeof b === 'object' ? b : { ...(DEFAULT_PART_MARGIN as Record<string, number>) }
  })
  /** 分项策略原始行（抽屉判 create/update 用） */
  const partMarginState = computed(() => ({ id: _partMarginRow.value?.id ?? null, body: partMargin.value }))

  /** 分项建议毛利：deal 目标毛利 + 品类修正，每个夹默认保底封顶（演算器预览 / 未来 AI 出价 per-line） */
  function computePartMargins(target: number): { default: number; parts: PartMargin[] } {
    const g = resolveGuardrail(dims.value.guardrail, {})
    return evalPartMargins(target, partMargin.value, g.floor, g.cap)
  }

  /** 利润率告警配置（工作台低毛利弹窗用；DB margin_alert 优先，缺失回退 DEFAULT_MARGIN_ALERT） */
  function getMarginAlert(): MarginAlertBody {
    return _marginAlert.value
  }
  /** 告警策略 id + body（策略中心编辑器判断 create/update 用） */
  const marginAlertState = computed(() => ({ id: _marginAlertId.value, body: _marginAlert.value }))

  /** L3 策略溯源快照（加法引擎依据 + 维保）。reasoning 报价单导出时记录。 */
  function getStrategySnapshot(ctx: {
    platform?: string | null
    industry?: string | null
    region?: string | null
    customerType?: string | null
    form?: string | null
    cost?: number | null
    qty?: number | null
    warrantyYears?: number | null
  }): Array<{ type: string; name: string; id?: number; version?: number; body: any; applied?: any }> {
    const out: Array<any> = []
    const pr = computeTargetMargin({
      platform: ctx.platform, industry: ctx.industry, region: ctx.region,
      customerType: ctx.customerType, form: ctx.form, cost: ctx.cost, qty: ctx.qty,
    })
    out.push({
      type: 'pricing_additive', name: '加法定价',
      body: { target: pr.target, floor: pr.floor, cap: pr.cap, clamped: pr.clamped, fixedFee: pr.fixedFee, breakdown: pr.breakdown },
      applied: {
        platform: ctx.platform || null, industry: ctx.industry || null, region: ctx.region || null,
        customer_type: ctx.customerType || null, form: ctx.form || null, cost: ctx.cost ?? null, qty: ctx.qty ?? null,
      },
    })
    if (_warrantyMarkup.value) {
      out.push({
        type: 'warranty_markup', name: '维保加价',
        body: _warrantyMarkup.value,
        applied: { warranty_years: ctx.warrantyYears },
      })
    }
    return out
  }

  const warrantyMarkup = computed(() => _warrantyMarkup.value)

  return {
    // 状态
    warrantyMarkup,
    dims,
    dimStrategies,
    marginAlertState,
    partMargin,
    partMarginState,
    // 方法
    ensurePricingRules,
    invalidatePricingRules,
    computeTargetMargin,
    computePartMargins,
    getGuardrail,
    getMarginAlert,
    getStrategySnapshot,
    _loaded,
  }
})
