/**
 * 定价规则 Pinia Store — 加法定价引擎的加载/消费层。
 *
 * 数据源：
 *   - strategies pricing.<dim>：6 条维度系数表（platform_baseline/industry_adj/region_adj/
 *     order_mult/cost_tier/guardrail）；缺失维度回退 constants/pricingMeta 的 DEFAULT_DIM_BODIES
 *   - strategies pricing.warranty_markup：维保加价（独立维度，保留）
 *   - strategies pricing.margin_alert：利润率告警（开关+门槛+文案，工作台低毛利弹窗）
 *   - system_config profit_margin_alert_threshold：辅助告警阈值（已不驱动工作台告警，保留）
 *
 * 求值本身在 stores/pricingEngine（纯 TS，可独立单测）；本 store 只负责加载 + 薄封装 + 溯源快照。
 * 策略中心画布/抽屉 CRUD 后调 invalidatePricingRules → ensure 重新拉。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { systemConfigApi } from '@/api/systemConfig'
import { strategyApi } from '@/api/strategies'
import { computeTargetMargin as evalTargetMargin, type PricingContext, type PricingDims, type PricingResult } from '@/stores/pricingEngine'
import { PIPELINE_ORDER, DEFAULT_DIM_BODIES, DEFAULT_MARGIN_ALERT, type MarginAlertBody } from '@/constants/pricingMeta'

export const usePricingRulesStore = defineStore('pricingRules', () => {
  const _alertThreshold = ref(0.08)
  // 维度策略原始行（type → strategy），未持久化的维度缺失
  const _dimRows = ref<Record<string, any>>({})
  const _warrantyMarkup = ref<{ y1: number; y3: number; y5: number } | null>(null)
  // 利润率告警（独立策略 type=margin_alert）
  const _marginAlert = ref<MarginAlertBody>({ ...DEFAULT_MARGIN_ALERT })
  const _marginAlertId = ref<number | null>(null)

  const _loaded = ref(false)
  let _promise: Promise<void> | null = null

  /** 加载定价规则（幂等，多次调用只请求一次） */
  async function ensurePricingRules(): Promise<void> {
    if (_loaded.value) return
    if (!_promise) {
      _promise = Promise.all([
        systemConfigApi.getValue<number>('profit_margin_alert_threshold'),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'warranty_markup' }),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'margin_alert' }),
        ...PIPELINE_ORDER.map(k => strategyApi.list({ domain: 'pricing', status: 'active', type: k })),
      ])
        .then(([t, wmRes, maRes, ...dimReses]) => {
          if (typeof t === 'number' && !isNaN(t)) _alertThreshold.value = t
          const wm = wmRes.strategies?.[0]?.body
          if (wm && typeof wm === 'object') {
            _warrantyMarkup.value = { y1: wm.y1 ?? 0, y3: wm.y3 ?? 0, y5: wm.y5 ?? 0 }
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
    cost?: number | null
    qty?: number | null
    warrantyYears?: number | null
  }): Array<{ type: string; name: string; id?: number; version?: number; body: any; applied?: any }> {
    const out: Array<any> = []
    const pr = computeTargetMargin({
      platform: ctx.platform, industry: ctx.industry, region: ctx.region,
      customerType: ctx.customerType, cost: ctx.cost, qty: ctx.qty,
    })
    out.push({
      type: 'pricing_additive', name: '加法定价',
      body: { target: pr.target, floor: pr.floor, cap: pr.cap, clamped: pr.clamped, breakdown: pr.breakdown },
      applied: {
        platform: ctx.platform || null, industry: ctx.industry || null, region: ctx.region || null,
        customer_type: ctx.customerType || null, cost: ctx.cost ?? null, qty: ctx.qty ?? null,
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

  const alertThreshold = computed(() => _alertThreshold.value)
  const warrantyMarkup = computed(() => _warrantyMarkup.value)

  return {
    // 状态
    alertThreshold,
    warrantyMarkup,
    dims,
    dimStrategies,
    marginAlertState,
    // 方法
    ensurePricingRules,
    invalidatePricingRules,
    computeTargetMargin,
    getGuardrail,
    getMarginAlert,
    getStrategySnapshot,
    _loaded,
  }
})
