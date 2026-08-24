/**
 * 加法定价引擎 —— 纯求值逻辑（无 vue/pinia 依赖，可独立单测）。
 *
 * 公式：最终毛利率 = (平台基准 + 行业浮动 + 区域浮动 + 形态浮动) × 订单系数 × 成本阶梯 × 台数折扣 → 夹在 [保底, 封顶]
 *
 * 策略 type（见 constants/pricingMeta.ts 的 DimensionKey）：
 *   platform_baseline: Record<platform, 毛利%>   base  加法链起点
 *   industry_adj:      Record<industry, ±百分点>  add
 *   region_adj:        { factors: Record<桶, ±百分点 | {pct,fixed_fee}>, keywords }  add（先分桶；海外可带每台固定费）
 *   form_adj:          Record<机箱形态, ±百分点>   add（2U/4U/5U/塔式…）
 *   order_mult:        Record<customer_type, 系数> mult（枚举存商机 extra_fields.customer_type）
 *   cost_tier:         { tiers: [{ max?:成本上限, mult }] }  mult（按成本落档）
 *   qty_mult:          { bands: [{ min, mult }] }  mult（量大让利）
 *   guardrail:         { floor, cap, tiers?: [{customer_type,floor,cap}] }  clamp（可按订单类型分档红线）
 *
 * 另有非流水线的分项毛利修正（pricing.part_margin）：computePartMargins 在 deal 目标毛利上
 * 按品类 ±百分点（CPU/内存/硬盘…），每个夹 [floor, cap]——未来 AI 出价 per-line margin 直接消费。
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
  customerType?: string | null   // 商机 extra_fields.customer_type（枚举：直签大客户/渠道分销/集采项目/零散项目；可用 order_type 兜底）
  form?: string | null           // opportunity.chassis_form（机箱形态：2U/4U/5U/塔式…）
  cost?: number | null           // 报价单 BOM 总成本（RMB）
  qty?: number | null            // 销售台数（opportunity.purchase_qty）
}

/** 区域桶系数：纯数字=±百分点；对象可带每台固定费（报关/国际物流/海外质保，只入售价不进毛利） */
export interface RegionFactor { pct: number; fixed_fee?: number }
/** 保底封顶分档：按订单类型差异化红线（首命中） */
export interface GuardrailTier { customer_type: string; floor: number; cap: number }
export interface GuardrailBody { floor: number; cap: number; tiers?: GuardrailTier[] }

// ── 维度系数表（strategy.body 的形态，store 加载后拼成此对象）──
export interface PricingDims {
  platform_baseline?: Record<string, number>
  industry_adj?: Record<string, number>
  region_adj?: { factors: Record<string, number | RegionFactor>; keywords?: Record<string, string[]> }
  form_adj?: Record<string, number>
  order_mult?: Record<string, number>
  cost_tier?: { tiers: Array<{ max?: number; mult: number }> }
  qty_mult?: { bands: Array<{ min: number; mult: number }> }
  guardrail?: GuardrailBody
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
  fixedFee: number               // 每台固定附加费（元，海外报关/物流等；只入售价不进毛利）
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

/** 区域桶系数归一：number → {pct, fixed_fee:0}；非法返回 null */
function normFactor(v: number | RegionFactor | undefined | null): { pct: number; fixedFee: number } | null {
  if (v == null) return null
  if (typeof v === 'number') return Number.isFinite(v) ? { pct: v, fixedFee: 0 } : null
  const pct = Number(v.pct)
  if (!Number.isFinite(pct)) return null
  const fee = Number(v.fixed_fee)
  return { pct, fixedFee: Number.isFinite(fee) && fee > 0 ? fee : 0 }
}

/** 保底封顶解析：tiers 按 ctx.customerType 首命中分档（差异化红线），无命中/无 tiers 用默认档 */
export function resolveGuardrail(g: GuardrailBody | undefined, ctx: PricingContext): { floor: number; cap: number; matched?: string } {
  const floor = Number(g?.floor ?? 0) || 0
  const cap = Number(g?.cap ?? 100) || 100
  const hit = (g?.tiers || []).find(t => t.customer_type && ctx.customerType && t.customer_type === ctx.customerType)
  if (hit) {
    const f = Number(hit.floor), c = Number(hit.cap)
    if (Number.isFinite(f) && Number.isFinite(c)) return { floor: f, cap: c, matched: hit.customer_type }
  }
  return { floor, cap }
}

/**
 * 核心求值：按维度顺序线性叠加 → clamp。
 */
export function computeTargetMargin(ctx: PricingContext, dims: PricingDims): PricingResult {
  const breakdown: PricingStep[] = []
  const gr = resolveGuardrail(dims.guardrail, ctx)
  const floor = gr.floor
  const cap = gr.cap

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

  // ③ 区域浮动（add，先分桶；factor 可带每台固定费）
  const bucket = resolveRegion(ctx.region, dims.region_adj)
  const factor = normFactor(dims.region_adj?.factors?.[bucket])
  let fixedFee = 0
  if (factor) {
    m += factor.pct
    fixedFee = factor.fixedFee
    breakdown.push({ dimKey: 'region_adj', opKind: 'add', value: factor.pct, matched: bucket, subtotal: round1(m), note: ctx.region && bucket !== ctx.region ? `「${ctx.region}」→ ${bucket}` : undefined })
  } else {
    breakdown.push({ dimKey: 'region_adj', opKind: 'add', value: '—', matched: bucket, subtotal: round1(m), skipped: true, note: `桶「${bucket}」未配浮动` })
  }

  // ④ 形态浮动（add）
  const formKey = matchKey(dims.form_adj, ctx.form)
  if (formKey) {
    const v = Number(dims.form_adj![formKey]) || 0
    m += v
    breakdown.push({ dimKey: 'form_adj', opKind: 'add', value: v, matched: formKey, subtotal: round1(m) })
  } else {
    breakdown.push({ dimKey: 'form_adj', opKind: 'add', value: '—', subtotal: round1(m), skipped: true, note: ctx.form ? `形态「${ctx.form}」未配浮动` : '无机箱形态' })
  }

  // ⑤ 订单系数（mult）
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

  // ⑥ 成本阶梯（mult）
  const tier = resolveCostTier(ctx.cost, dims.cost_tier)
  if (tier.matched) {
    m *= tier.mult
    breakdown.push({ dimKey: 'cost_tier', opKind: 'mult', value: tier.mult, matched: tier.matched, subtotal: round1(m) })
  } else {
    breakdown.push({ dimKey: 'cost_tier', opKind: 'mult', value: '—', subtotal: round1(m), skipped: true, note: ctx.cost == null ? '无成本数据' : (dims.cost_tier ? '未配成本阶梯' : '未配成本阶梯') })
  }

  // ⑦ 台数折扣（mult）
  const qb = resolveQtyBand(ctx.qty, dims.qty_mult)
  if (qb.matched) {
    m *= qb.mult
    breakdown.push({ dimKey: 'qty_mult', opKind: 'mult', value: qb.mult, matched: qb.matched, subtotal: round1(m) })
  } else {
    breakdown.push({ dimKey: 'qty_mult', opKind: 'mult', value: '—', subtotal: round1(m), skipped: true, note: ctx.qty == null ? '无台数数据' : '未配台数折扣' })
  }

  // ⑧ 保底封顶（clamp，可按订单类型分档红线）
  const raw = m
  let clamped = false
  if (m < floor) { m = floor; clamped = true }
  else if (m > cap) { m = cap; clamped = true }
  const tierNote = gr.matched ? `（按「${gr.matched}」分档 ${floor}~${cap}）` : ''
  breakdown.push({
    dimKey: 'guardrail', opKind: 'clamp', value: `${floor}~${cap}`, subtotal: round1(m),
    note: clamped ? (raw < floor ? `低于保底 ${floor}%，上调${tierNote}` : `高于封顶 ${cap}%，下调${tierNote}`) : `在区间内${tierNote}`,
  })

  return { target: round1(m), breakdown, floor, cap, clamped, fixedFee }
}

/**
 * 由目标毛利率反推建议售价：售价 = (成本 + 每台固定费) × (1 + target/100)。
 * fixedFee 为海外报关/物流等每台固定附加（computeTargetMargin 结果的 fixedFee）；无成本返回 null。
 */
export function suggestPrice(cost: number | null | undefined, targetMarginPct: number, fixedFee = 0): number | null {
  if (cost == null || !Number.isFinite(cost) || cost <= 0) return null
  const fee = Number.isFinite(fixedFee) && fixedFee > 0 ? fixedFee : 0
  return round1((cost + fee) * (1 + targetMarginPct / 100))
}

/** 分项建议毛利条目 */
export interface PartMargin { category: string; adj: number; margin: number }

/**
 * 分项建议毛利（pricing.part_margin）：deal 目标毛利 + 品类修正（±百分点），每个夹 [floor, cap]。
 * 未列品类修正为 0（用 default）；供演算器预览 + 未来 AI 出价 per-line margin 直接消费。
 */
export function computePartMargins(
  target: number,
  adj: Record<string, number> | null | undefined,
  floor: number,
  cap: number,
): { default: number; parts: PartMargin[] } {
  const clamp = (v: number) => round1(Math.min(Math.max(v, floor), cap))
  const parts = Object.entries(adj || {})
    .map(([category, a]) => ({ category: String(category).trim(), adj: Number(a) || 0 }))
    .filter((p) => p.category)
    .sort((a, b) => a.category.localeCompare(b.category))
    .map((p) => ({ ...p, margin: clamp(target + p.adj) }))
  return { default: clamp(target), parts }
}
