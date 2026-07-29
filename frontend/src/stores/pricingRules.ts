/**
 * 定价规则 Pinia Store — 替代原来的 usePricingRules composable。
 * 解决模块级 ref 跨组件响应式失效的问题。
 *
 * 数据源：
 *   - system_config: profit_margin_alert_threshold / default_markup_coefficient
 *   - strategies pricing.pricing_scenario：报价场景
 *   - strategies pricing.margin_tier：毛利三档规则
 *   - strategies pricing.warranty_markup：维保加价
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { systemConfigApi } from '@/api/systemConfig'
import { strategyApi, type MarginTier } from '@/api/strategies'

export const usePricingRulesStore = defineStore('pricingRules', () => {
  // 阈值与系数
  const _alertThreshold = ref(0.08)
  const _markupCoefficient = ref(0.1)

  // 报价策略重构：场景（pricing_scenario）+ 规则（margin_tier，按 id 索引）
  const _scenarios = ref<any[]>([])  // [{id, name, version, scope, rule_id, description}]
  const _rulesById = ref<Record<number, { body: MarginTier; name: string; version: number }>>({})
  const _warrantyMarkup = ref<{ y1: number; y3: number; y5: number } | null>(null)
  const _pricingStrategies = ref<any[]>([])  // L3 溯源：保留原始策略

  const _loaded = ref(false)
  let _promise: Promise<void> | null = null

  /** 加载定价规则（幂等，多次调用只请求一次） */
  async function ensurePricingRules(): Promise<void> {
    if (_loaded.value) return
    if (!_promise) {
      _promise = Promise.all([
        systemConfigApi.getValue<number>('profit_margin_alert_threshold'),
        systemConfigApi.getValue<number>('default_markup_coefficient'),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'margin_tier' }),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'warranty_markup' }),
        strategyApi.list({ domain: 'pricing', status: 'active', type: 'pricing_scenario' }),
      ])
        .then(([t, m, tiersRes, wmRes, scRes]) => {
          if (typeof t === 'number' && !isNaN(t)) _alertThreshold.value = t
          if (typeof m === 'number' && !isNaN(m)) _markupCoefficient.value = m
          // margin_tier 按 id 索引（规则栏，被场景连线）
          const byId: Record<number, any> = {}
          for (const s of tiersRes.strategies || []) {
            if (s.body) byId[s.id] = { body: s.body, name: s.name, version: s.version }
          }
          _rulesById.value = byId
          // pricing_scenario 场景栏
          _scenarios.value = (scRes.strategies || []).map((s: any) => ({
            id: s.id, name: s.name, version: s.version,
            scope: s.scope || {},
            rule_id: s.body?.rule_id,
            description: s.body?.description || s.description || '',
          }))
          // warranty_markup
          const wm = wmRes.strategies?.[0]?.body
          if (wm && typeof wm === 'object') {
            _warrantyMarkup.value = { y1: wm.y1 ?? 0, y3: wm.y3 ?? 0, y5: wm.y5 ?? 0 }
          }
          // 保留原始策略用于溯源
          _pricingStrategies.value = tiersRes.strategies || []
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

  /** scope 匹配：ctx 满足 scope 所有字段则命中 */
  function scopeMatch(scope: any, ctx: Record<string, any>): boolean {
    for (const [k, v] of Object.entries(scope || {})) {
      const cv = ctx[k]
      if (Array.isArray(v) ? !v.includes(cv) : cv !== v) return false
    }
    return true
  }

  function scopeSpecificity(scope: any): number {
    return Object.keys(scope || {}).filter(k => !['description'].includes(k)).length
  }

  /** 取命中的三档：遍历场景（最具体优先）→ rule_id → margin_tier 规则。无命中或规则缺失则 null。 */
  function getMarginTier(
    platformType?: string | null,
    customerType?: string | null,
    quoteScenario?: string | null,
  ): MarginTier | null {
    const ctx: Record<string, any> = {
      platform_type: platformType || '',
      customer_type: customerType || '',
      quote_scenario: quoteScenario || '',
    }
    const hits = _scenarios.value
      .filter(s => scopeMatch(s.scope, ctx) && s.rule_id != null)
      .sort((a, b) => scopeSpecificity(b.scope) - scopeSpecificity(a.scope))
    for (const s of hits) {
      const rule = _rulesById.value[s.rule_id]
      if (rule?.body) return rule.body
    }
    return null
  }

  /** 判断利润率（百分点）所处档位 */
  function judgeMargin(
    margin: number | undefined | null,
    tier: MarginTier | null,
  ): { level: 'below-floor' | 'normal' | 'premium' | 'unknown'; label: string } {
    if (margin == null || !tier) return { level: 'unknown', label: '—' }
    if (margin < tier.floor) return { level: 'below-floor', label: `低于底线 ${tier.floor}%` }
    if (margin >= tier.premium) return { level: 'premium', label: `优质（≥${tier.premium}%）` }
    return { level: 'normal', label: '正常' }
  }

  /** P4 维保加价：按年限返回建议费率（百分点）；未命中策略返回 null */
  function getWarrantyRate(years: number | undefined | null): number | null {
    const wm = _warrantyMarkup.value
    if (!wm || !years) return null
    if (years >= 5) return wm.y5
    if (years >= 3) return wm.y3
    return wm.y1
  }

  /** L3 策略溯源快照（场景化）：记命中场景 + 连线规则 + warranty_markup。 */
  function getStrategySnapshot(ctx: {
    platform?: string | null
    customer_type?: string | null
    quote_scenario?: string | null
    warrantyYears?: number | null
  }): Array<{ type: string; name: string; id?: number; version?: number; body: any; applied?: any }> {
    const out: Array<any> = []
    const ctxMatch: Record<string, any> = {
      platform_type: ctx.platform || '',
      customer_type: ctx.customer_type || '',
      quote_scenario: ctx.quote_scenario || '',
    }
    const hits = _scenarios.value
      .filter(s => scopeMatch(s.scope, ctxMatch) && s.rule_id != null)
      .sort((a, b) => scopeSpecificity(b.scope) - scopeSpecificity(a.scope))
    if (hits.length) {
      const s = hits[0]  // 最具体
      const rule = _rulesById.value[s.rule_id]
      out.push({
        type: 'pricing_scenario', name: s.name, id: s.id, version: s.version,
        body: { description: s.description, rule_body: rule?.body },
        applied: ctxMatch,
        linked_rule: { id: s.rule_id, name: rule?.name, version: rule?.version },
      })
    }
    // warranty_markup 通用策略（不依赖 platform），策略存在即记
    if (_warrantyMarkup.value) {
      out.push({
        type: 'warranty_markup', name: '维保加价',
        body: _warrantyMarkup.value,
        applied: { warranty_years: ctx.warrantyYears },
      })
    }
    return out
  }

  // 计算属性
  const alertThreshold = computed(() => _alertThreshold.value)
  const markupCoefficient = computed(() => _markupCoefficient.value)
  const scenarios = computed(() => _scenarios.value)
  const rulesById = computed(() => _rulesById.value)
  const warrantyMarkup = computed(() => _warrantyMarkup.value)
  const pricingStrategies = computed(() => _pricingStrategies.value)

  return {
    // 状态
    alertThreshold,
    markupCoefficient,
    scenarios,
    rulesById,
    warrantyMarkup,
    pricingStrategies,
    // 方法
    ensurePricingRules,
    invalidatePricingRules,
    getMarginTier,
    judgeMargin,
    getWarrantyRate,
    getStrategySnapshot,
    _loaded,
  }
})