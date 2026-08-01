/**
 * 加法定价引擎 —— 纯求值逻辑（无 vue/pinia 依赖，可独立单测）。
 *
 * 公式：最终毛利率 = (平台基准 + 行业浮动 + 区域浮动) × 订单系数 × 成本阶梯系数 → 夹在 [保底, 封顶]
 *
 * 策略 type（见 constants/pricingMeta.ts 的 DimensionKey）：
 *   platform_baseline: Record<platform, 毛利%>          base  加法链起点
 *   industry_adj:      Record<industry, ±百分点>         add
 *   region_adj:        { factors: Record<桶,±百分点>, keywords: Record<桶,[词]> }  add（先分桶）
 *   order_mult:        Record<customer_type, 系数>       mult
 *   cost_tier:         { tiers: [{ max?:成本上限, mult }] }  mult（按成本落档）
 *   guardrail:         { floor, cap }                    clamp
 *
 * 设计要点：
 *  - 优雅降级：任一维度未配置 / ctx 缺值 → 该维度不调整（add→+0、mult→×1），baseline 缺失回退保底 floor。
 *  - breakdown 记录每步数值与命中项，供画布/演算器/溯源展示；只带 dimKey + 数值，label 由 pricingMeta 渲染。
 *  - 抽出为纯模块：(1) node:test 独立单测；(2) 未来智能方案助手可直接 import 自动出报价。
 */
import type { DimensionKey, OpKind } from '@/constants/pricingMeta'

// ── 求值上下文（消费端构建：商机字段 + 报价成本）──
export interface PricingContext {
  platform?: string | null       // opportunity.platform_type
  industry?: string | null       // opportunity.industry
  region?: string | null         // opportunity.delivery_region（自由文本，引擎内分桶；已是桶名也认）
  customerType?: string | null   // opportunity.order_type（订单维度）
  form?: string | null           // opportunity.chassis_form（v1 预留不参与）
  cost?: number | null           // 报价单 BOM 总成本（RMB）
  qty?: number | null            // 销售台数（opportunity.purchase_qty）
}

// ── 维度系数表（strategy.body 的形态，store 加载后拼成此对象）──
export interface PricingDims {
  platform_baseline?: Record<string, number>
  industry_adj?: Record<string, number>
  region_adj?: { factors: Record<string, number>; keywords?: Record<string, string[]> }
  order_mult?: Record<string, number>
  cost_tier?: { tiers: Array<{ max?: number; mult: number }> }
  qty_mult?: { bands: Array<{ min: number; mult: number }> }
  guardrail?: { floor: number; cap: number }
}

export interface PricingStep {
  dimKey: DimensionKey
  opKind: OpKind
  value: number | string         // 命中的系数（base 15 / add +3 / mult ×0.75 / clamp "7~30"）；未命中为 '—'
  matched?: string               // 命中的枚举/桶（'Polaris' / '海外'）
  subtotal: number               // 本步后的累计毛利率（百分点）
  note?: string                  // 降级/未命中说明
  skipped?: boolean              // 该步实际未生效（无数据/无配置）
}

export interface PricingResult {
  target: number                 // 最终目标毛利率（百分点，1 位小数）
  breakdown: PricingStep[]
  floor: number
  cap: number
  clamped: boolean               // 是否触发保底/封顶
}

const round1 = (n: number): number => Math.round(n * 10) / 10

/** 枚举表里找 input 对应的 key（精确 → 大小写无关）；找不到返回 undefined */
function matchKey(values: Record<string, number> | undefined, input: string | null | undefined): string | undefined {
  if (!input || !values) return undefined
  const s = String(input).trim()
  if (s in values) return s
  const lower = s.toLowerCase()
  return Object.keys(values).find(k => k.toLowerCase() === lower)
}

/**
 * delivery_region 自由文本 → 桶。优先级 偏远 > 海外 > 国内(默认)。
 * 1) 若文本本身是桶名（factors 的 key）直接认；
 * 2) 否则按 keywords 命中（偏远先判，因其是国内的子集，避免被"国内"吞掉）。
 */
export function resolveRegion(raw: string | null | undefined, region?: PricingDims['region_adj']): string {
  if (!raw) return '国内'
  const r = String(raw).trim()
  const factors = region?.factors || {}
  if (r in factors) return r
  const kw = region?.keywords || {}
  // 偏远优先于海外判定
  if ((kw['偏远'] || []).some(k => r.includes(k))) return '偏远'
  if ((kw['海外'] || []).some(k => r.includes(k))) return '海外'
  return '国内'
}

/** 取成本阶梯系数：tiers 按 max 升序，找首个 cost ≤ max 的档；超出所有 max 落无 max 的末档；无命中 ×1.0 */
export function resolveCostTier(cost: number | null | undefined, tiers?: PricingDims['cost_tier']): { mult: number; matched?: string } {
  if (!tiers?.tiers?.length) return { mult: 1 }
  if (cost == null || !Number.isFinite(cost) || cost <= 0) return { mult: 1 }
  const sorted = [...tiers.tiers].sort((a, b) => (a.max ?? Infinity) - (b.max ?? Infinity))
  for (const t of sorted) {
    if (t.max == null || cost <= t.max) return { mult: Number(t.mult) || 1, matched: t.max == null ? `>${sorted[sorted.length - 2]?.max ?? 0}` : `≤${t.max}` }
  }
  return { mult: Number(sorted[sorted.length - 1].mult) || 1 }
}

/** 取台数折扣系数：bands 按 min 降序，找首个 min ≤ qty 的档（量越大让利越多）；无命中 ×1.0 */
export function resolveQtyBand(qty: number | null | undefined, bands?: PricingDims['qty_mult']): { mult: number; matched?: string } {
  if (!bands?.bands?.length) return { mult: 1 }
  if (qty == null || !Number.isFinite(qty) || qty <= 0) return { mult: 1 }
  const sorted = [...bands.bands].sort((a, b) => b.min - a.min)
  for (const b of sorted) {
    if (qty >= b.min) return { mult: Number(b.mult) || 1, matched: `≥${b.min}台` }
  }
  return { mult: 1 }
}

/**
 * 核心求值：按维度顺序线性叠加 → clamp。
 */
export function computeTargetMargin(ctx: PricingContext, dims: PricingDims): PricingResult {
  const breakdown: PricingStep[] = []
  const floor = dims.guardrail?.floor ?? 0
  const cap = dims.guardrail?.cap ?? 100

  // ① 平台基准（base）
  let m: number
  const platKey = matchKey(dims.platform_baseline, ctx.platform)
  const baseVal = platKey ? Number(dims.platform_baseline![platKey]) : NaN
  if (platKey && Number.isFinite(baseVal)) {
    m = baseVal
    breakdown.push({ dimKey: 'platform_baseline', opKind: 'base', value: baseVal, matched: platKey, subtotal: round1(m) })
  } else {
    m = floor
    breakdown.push({
      dimKey: 'platform_baseline', opKind: 'base', value: '—', subtotal: round1(m), skipped: true,
      note: ctx.platform ? `平台「${ctx.platform}」未配基准，回退保底 ${floor}%` : `无平台信息，回退保底 ${floor}%`,
    })
  }

  // ② 行业浮动（add）
  const indKey = matchKey(dims.industry_adj, ctx.industry)
  if (indKey) {
    const v = Number(dims.industry_adj![indKey]) || 0
    m += v
    breakdown.push({ dimKey: 'industry_adj', opKind: 'add', value: v, matched: indKey, subtotal: round1(m) })
  } else {
    breakdown.push({ dimKey: 'industry_adj', opKind: 'add', value: '—', subtotal: round1(m), skipped: true, note: ctx.industry ? `行业「${ctx.industry}」未配浮动` : '无行业信息' })
  }

  // ③ 区域浮动（add，先分桶）
  const bucket = resolveRegion(ctx.region, dims.region_adj)
  const regionVal = dims.region_adj?.factors?.[bucket]
  if (regionVal != null && Number.isFinite(Number(regionVal))) {
    const v = Number(regionVal)
    m += v
    breakdown.push({ dimKey: 'region_adj', opKind: 'add', value: v, matched: bucket, subtotal: round1(m), note: ctx.region && bucket !== ctx.region ? `「${ctx.region}」→ ${bucket}` : undefined })
  } else {
    breakdown.push({ dimKey: 'region_adj', opKind: 'add', value: '—', matched: bucket, subtotal: round1(m), skipped: true, note: `桶「${bucket}」未配浮动` })
  }

  // ④ 订单系数（mult）
  const ordKey = matchKey(dims.order_mult, ctx.customerType)
  if (ordKey) {
    const v = Number(dims.order_mult![ordKey])
    if (Number.isFinite(v)) {
      m *= v
      breakdown.push({ dimKey: 'order_mult', opKind: 'mult', value: v, matched: ordKey, subtotal: round1(m) })
    } else {
      breakdown.push({ dimKey: 'order_mult', opKind: 'mult', value: '—', matched: ordKey, subtotal: round1(m), skipped: true, note: '系数非法' })
    }
  } else {
    breakdown.push({ dimKey: 'order_mult', opKind: 'mult', value: '—', subtotal: round1(m), skipped: true, note: ctx.customerType ? `订单「${ctx.customerType}」未配系数` : '无订单类型' })
  }

  // ⑤ 成本阶梯（mult）
  const tier = resolveCostTier(ctx.cost, dims.cost_tier)
  if (tier.matched) {
    m *= tier.mult
    breakdown.push({ dimKey: 'cost_tier', opKind: 'mult', value: tier.mult, matched: tier.matched, subtotal: round1(m) })
  } else {
    breakdown.push({ dimKey: 'cost_tier', opKind: 'mult', value: '—', subtotal: round1(m), skipped: true, note: ctx.cost == null ? '无成本数据' : (dims.cost_tier ? '未配成本阶梯' : '未配成本阶梯') })
  }

  // ⑥ 台数折扣（mult）
  const qb = resolveQtyBand(ctx.qty, dims.qty_mult)
  if (qb.matched) {
    m *= qb.mult
    breakdown.push({ dimKey: 'qty_mult', opKind: 'mult', value: qb.mult, matched: qb.matched, subtotal: round1(m) })
  } else {
    breakdown.push({ dimKey: 'qty_mult', opKind: 'mult', value: '—', subtotal: round1(m), skipped: true, note: ctx.qty == null ? '无台数数据' : '未配台数折扣' })
  }

  // ⑦ 保底封顶（clamp）
  const raw = m
  let clamped = false
  if (m < floor) { m = floor; clamped = true }
  else if (m > cap) { m = cap; clamped = true }
  breakdown.push({
    dimKey: 'guardrail', opKind: 'clamp', value: `${floor}~${cap}`, subtotal: round1(m),
    note: clamped ? (raw < floor ? `低于保底 ${floor}%，上调` : `高于封顶 ${cap}%，下调`) : '在区间内',
  })

  return { target: round1(m), breakdown, floor, cap, clamped }
}

/**
 * 由目标毛利率反推建议售价：售价 = 成本 × (1 + target/100)。
 * 无成本返回 null（演算器/助手自行兜底）。
 */
export function suggestPrice(cost: number | null | undefined, targetMarginPct: number): number | null {
  if (cost == null || !Number.isFinite(cost) || cost <= 0) return null
  return round1(cost * (1 + targetMarginPct / 100))
}
