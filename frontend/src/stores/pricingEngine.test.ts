/**
 * 加法定价引擎单测 —— 用 node 原生 test runner 跑（无需 vitest/node_modules）。
 *   node --test frontend/src/stores/pricingEngine.test.ts
 *
 * 锁住的是 CPQ 定价的正确性下限：公式叠加顺序、维度缺失优雅降级、保底封顶 clamp、
 * 区域分桶与成本阶梯边界。这些错了会直接产出误导销售的报价建议。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  computeTargetMargin, resolveRegion, resolveCostTier, resolveQtyBand, resolveGuardrail, suggestPrice, computePartMargins,
  type PricingContext, type PricingDims,
} from './pricingEngine.ts'
import { DEFAULT_DIM_BODIES } from '../constants/pricingMeta.ts'

// ── 测试夹具：完整维度（镜像 backend seed DEFAULT_DIMS / pricingMeta DEFAULT_DIM_BODIES）──
// region 海外用纯数字、guardrail 无 tiers——夹具兼作「存量 body 形态」的向后兼容覆盖。
function fullDims(): PricingDims {
  return {
    platform_baseline: { Polaris: 15, Orion: 11, Intel: 11, '工作站': 13 },
    industry_adj: { 'AI算力': 3, 'IDC机房': -2, '政企信息化': 3, '高校科研': 0, '安防存储': 1, '工业边缘': 2 },
    region_adj: { factors: { 国内: 0, 海外: 2, 偏远: 1 }, keywords: { 海外: ['海外', '东南亚', '欧美'], 偏远: ['西藏', '新疆'] } },
    form_adj: { '2U': 0, '4U': -1, '5U': -1, '塔式': 1 },
    order_mult: { '直签大客户': 0.9, '渠道分销': 0.7, '集采项目': 0.75, '零散项目': 1.0 },
    cost_tier: { tiers: [{ max: 50000, mult: 1.1 }, { max: 300000, mult: 1.0 }, { mult: 0.9 }] },
    qty_mult: { bands: [{ min: 1, mult: 1.0 }, { min: 6, mult: 0.9 }, { min: 21, mult: 0.84 }, { min: 51, mult: 0.75 }] },
    guardrail: { floor: 7, cap: 30 },
  }
}

// ============================================================
// 完整流水线：全维度命中
// ============================================================
test('computeTargetMargin: 全维度命中按公式线性叠加', () => {
  const ctx: PricingContext = { platform: 'Polaris', industry: '政企信息化', region: '东南亚', customerType: '集采项目', form: '2U', cost: 120000, qty: 1 }
  // 15 +3(政企) +2(海外) +0(2U) =20 → ×0.75(集采)=15 → ×1.0(12w 中档)=15 → ×1.0(1台)=15 → clamp 7~30 =15
  const r = computeTargetMargin(ctx, fullDims())
  assert.equal(r.target, 15)
  assert.equal(r.clamped, false)
  assert.equal(r.breakdown.length, 8)
  assert.equal(r.breakdown[0].matched, 'Polaris')
  assert.equal(r.breakdown[2].matched, '海外')        // region 分桶后命中海外
  assert.equal(r.breakdown[3].matched, '2U')          // 形态 2U +0
  assert.equal(r.breakdown[6].matched, '≥1台')        // 台数折扣命中 1 台档
})

test('computeTargetMargin: 平台大小写无关匹配', () => {
  const r = computeTargetMargin({ platform: 'POLARIS', cost: 120000 }, fullDims())
  assert.equal(r.breakdown[0].matched, 'Polaris')
  assert.equal(r.breakdown[0].value, 15)
})

// ============================================================
// 优雅降级：单维度缺失/未配置 → 该步不调整
// ============================================================
test('computeTargetMargin: baseline 缺失 → 回退保底 floor', () => {
  const r = computeTargetMargin({ platform: 'UnknownPlatform', cost: 120000 }, fullDims())
  assert.equal(r.breakdown[0].skipped, true)
  assert.equal(r.breakdown[0].subtotal, 7)            // 回退 floor=7
  assert.match(r.breakdown[0].note!, /未配基准/)
})

test('computeTargetMargin: 行业/订单未配 → 跳过不调整', () => {
  const r = computeTargetMargin({ platform: 'Polaris', industry: '未知行业', customerType: '未知类型', cost: 120000 }, fullDims())
  const ind = r.breakdown.find(s => s.dimKey === 'industry_adj')!
  const ord = r.breakdown.find(s => s.dimKey === 'order_mult')!
  assert.equal(ind.skipped, true)
  assert.equal(ord.skipped, true)
  // 15(base) +0 +0 ×1 ×1.0 = 15
  assert.equal(r.target, 15)
})

test('computeTargetMargin: dims 完全为空 → target=floor(0)，全部降级', () => {
  const r = computeTargetMargin({ platform: 'Polaris', cost: 120000 }, {})
  assert.equal(r.target, 0)
  assert.equal(r.clamped, false)
  assert.equal(r.breakdown[0].skipped, true)          // baseline 无配置回退 floor=0
})

// ============================================================
// 区域分桶（delivery_region 自由文本）
// ============================================================
test('resolveRegion: 关键词分桶 偏远>海外>国内，已是桶名直认', () => {
  const region = fullDims().region_adj
  assert.equal(resolveRegion('西藏拉萨', region), '偏远')
  assert.equal(resolveRegion('东南亚-新加坡', region), '海外')
  assert.equal(resolveRegion('欧美', region), '海外')
  assert.equal(resolveRegion('北京', region), '国内')
  assert.equal(resolveRegion('国内', region), '国内')     // 本身是桶名
  assert.equal(resolveRegion('', region), '国内')         // 空默认国内
  assert.equal(resolveRegion(null, region), '国内')
})

test('computeTargetMargin: 区域分桶后命中对应系数', () => {
  // 偏远 +1：15 +1 =16 → ×1 ×1.0 =16
  const r = computeTargetMargin({ platform: 'Polaris', region: '新疆', cost: 120000 }, fullDims())
  const reg = r.breakdown.find(s => s.dimKey === 'region_adj')!
  assert.equal(reg.matched, '偏远')
  assert.equal(reg.value, 1)
  assert.equal(r.target, 16)
})

// ============================================================
// 形态浮动（form_adj）
// ============================================================
test('computeTargetMargin: 形态 4U -1 压点 / 塔式 +1 / 未配或未知跳过', () => {
  const dims = fullDims()
  assert.equal(computeTargetMargin({ platform: 'Polaris', form: '4U', cost: 120000 }, dims).target, 14)   // 15-1
  assert.equal(computeTargetMargin({ platform: 'Polaris', form: '塔式', cost: 120000 }, dims).target, 16) // 15+1
  // 无形态 → 跳过 ±0
  const noForm = computeTargetMargin({ platform: 'Polaris', cost: 120000 }, dims)
  assert.equal(noForm.breakdown.find(s => s.dimKey === 'form_adj')!.skipped, true)
  assert.equal(noForm.target, 15)
  // 未知形态 → 未命中提示
  const unknown = computeTargetMargin({ platform: 'Polaris', form: '8S', cost: 120000 }, dims)
  assert.match(unknown.breakdown.find(s => s.dimKey === 'form_adj')!.note!, /未配浮动/)
})

// ============================================================
// 海外固定费（region factor 对象形态；纯数字存量兼容）
// ============================================================
test('computeTargetMargin: 海外对象系数 pct 进毛利、fixed_fee 单列只入售价', () => {
  const dims = fullDims()
  dims.region_adj = { factors: { 国内: 0, 海外: { pct: 3, fixed_fee: 800 }, 偏远: 1 }, keywords: { 海外: ['海外'] } }
  const r = computeTargetMargin({ platform: 'Polaris', region: '海外', cost: 100000 }, dims)
  assert.equal(r.breakdown.find(s => s.dimKey === 'region_adj')!.value, 3)
  assert.equal(r.target, 18)          // 15 + 3
  assert.equal(r.fixedFee, 800)
  // 纯数字(存量 body)仍兼容：毛利生效、fixedFee=0
  const dims2 = fullDims()
  dims2.region_adj = { factors: { 国内: 0, 海外: 2, 偏远: 1 }, keywords: { 海外: ['海外'] } }
  const r2 = computeTargetMargin({ platform: 'Polaris', region: '海外', cost: 100000 }, dims2)
  assert.equal(r2.target, 17)
  assert.equal(r2.fixedFee, 0)
})

// ============================================================
// 成本阶梯边界
// ============================================================
test('resolveCostTier: 边界 ≤max 含端点，超 max 落下一档，无 max 末档兜底', () => {
  const ct = fullDims().cost_tier!
  assert.equal(resolveCostTier(40000, ct).mult, 1.1)
  assert.equal(resolveCostTier(50000, ct).mult, 1.1)       // 含端点
  assert.equal(resolveCostTier(50001, ct).mult, 1.0)
  assert.equal(resolveCostTier(300000, ct).mult, 1.0)
  assert.equal(resolveCostTier(300001, ct).mult, 0.9)      // 末档
  assert.equal(resolveCostTier(300001, ct).matched, '>300000')
  // 无成本 / 非法 → 不调整
  assert.equal(resolveCostTier(null, ct).mult, 1)
  assert.equal(resolveCostTier(0, ct).mult, 1)
  assert.equal(resolveCostTier(-5, ct).mult, 1)
  // 未配 tiers → ×1
  assert.equal(resolveCostTier(999, undefined).mult, 1)
})

// ============================================================
// 台数折扣（qty_mult）
// ============================================================
test('resolveQtyBand: 量大让利，按 min 降序取首个 min≤qty 的档', () => {
  const qm = fullDims().qty_mult
  assert.equal(resolveQtyBand(1, qm).mult, 1.0)
  assert.equal(resolveQtyBand(5, qm).mult, 1.0)        // 1-5 台
  assert.equal(resolveQtyBand(6, qm).mult, 0.9)        // ≥6 档
  assert.equal(resolveQtyBand(20, qm).mult, 0.9)
  assert.equal(resolveQtyBand(21, qm).mult, 0.84)      // ≥21 档
  assert.equal(resolveQtyBand(50, qm).mult, 0.84)
  assert.equal(resolveQtyBand(51, qm).mult, 0.75)      // ≥51 档
  assert.equal(resolveQtyBand(60, qm).mult, 0.75)
  assert.equal(resolveQtyBand(1000, qm).mult, 0.75)
  // 无台数 / 非法 / 未配 → ×1
  assert.equal(resolveQtyBand(null, qm).mult, 1)
  assert.equal(resolveQtyBand(0, qm).mult, 1)
  assert.equal(resolveQtyBand(5, undefined).mult, 1)
})

test('computeTargetMargin: 台数折扣乘进毛利（25台 落 ≥21档 ×0.84）', () => {
  // Polaris(15) +0+0 ×1 ×1.0(12w 中档) ×0.84(≥21台) = 12.6
  const r = computeTargetMargin({ platform: 'Polaris', cost: 120000, qty: 25 }, fullDims())
  const qStep = r.breakdown.find(s => s.dimKey === 'qty_mult')!
  assert.equal(qStep.matched, '≥21台')
  assert.equal(qStep.value, 0.84)
  assert.equal(r.target, 12.6)
})

test('computeTargetMargin: 台数缺失 → 该步跳过不影响毛利', () => {
  const r = computeTargetMargin({ platform: 'Polaris', cost: 120000 }, fullDims())  // 无 qty
  const qStep = r.breakdown.find(s => s.dimKey === 'qty_mult')!
  assert.equal(qStep.skipped, true)
  assert.equal(r.target, 15)
})

// ============================================================
// 保底封顶 clamp
// ============================================================
test('computeTargetMargin: 低于保底 → 上调至 floor，clamped=true', () => {
  // Orion(11) ×渠道0.7 ×末档0.9 = 6.93 → clamp 7
  const r = computeTargetMargin({ platform: 'Orion', customerType: '渠道分销', cost: 400000 }, fullDims())
  assert.equal(r.target, 7)
  assert.equal(r.clamped, true)
  assert.equal(r.breakdown.at(-1)!.note, '低于保底 7%，上调')
})

test('computeTargetMargin: 高于封顶 → 下调至 cap，clamped=true', () => {
  const dims = fullDims()
  dims.guardrail = { floor: 7, cap: 10 }
  // Polaris(15) > cap 10 → clamp 10
  const r = computeTargetMargin({ platform: 'Polaris', cost: 120000 }, dims)
  assert.equal(r.target, 10)
  assert.equal(r.clamped, true)
  assert.equal(r.breakdown.at(-1)!.note, '高于封顶 10%，下调')
})

// ============================================================
// suggestPrice
// ============================================================
test('suggestPrice: 成本×(1+目标%) ; 无成本返回 null', () => {
  assert.equal(suggestPrice(100000, 15), 115000)
  assert.equal(suggestPrice(100000, 0), 100000)
  assert.equal(suggestPrice(null, 15), null)
  assert.equal(suggestPrice(0, 15), null)
})

test('suggestPrice: 含每台固定费 → (成本+fee)×(1+目标%)；负费视为 0', () => {
  assert.equal(suggestPrice(100000, 15, 800), 115920)   // (100000+800)×1.15
  assert.equal(suggestPrice(100000, 15, 0), 115000)
  assert.equal(suggestPrice(100000, 15, -50), 115000)
})

// ============================================================
// 保底封顶分档（guardrail.tiers 按订单类型差异化红线）
// ============================================================
test('resolveGuardrail: tiers 按 customerType 首命中，无命中/无 tiers/未配置回默认档', () => {
  const g = { floor: 7, cap: 30, tiers: [{ customer_type: '渠道分销', floor: 5, cap: 25 }, { customer_type: '集采项目', floor: 5, cap: 20 }] }
  assert.deepEqual(resolveGuardrail(g, { customerType: '集采项目' }), { floor: 5, cap: 20, matched: '集采项目' })
  assert.deepEqual(resolveGuardrail(g, { customerType: '渠道分销' }), { floor: 5, cap: 25, matched: '渠道分销' })
  assert.deepEqual(resolveGuardrail(g, { customerType: '零散项目' }), { floor: 7, cap: 30 })
  assert.deepEqual(resolveGuardrail(g, {}), { floor: 7, cap: 30 })
  assert.deepEqual(resolveGuardrail({ floor: 7, cap: 30 }, { customerType: '渠道分销' }), { floor: 7, cap: 30 })
  assert.deepEqual(resolveGuardrail(undefined, {}), { floor: 0, cap: 100 })
})

test('computeTargetMargin: 分档红线参与 clamp（渠道 6.93 在分档 [5,25] 内放行，默认档会夹 7）', () => {
  const dims = fullDims()
  dims.guardrail = { floor: 7, cap: 30, tiers: [{ customer_type: '渠道分销', floor: 5, cap: 25 }] }
  const r = computeTargetMargin({ platform: 'Orion', customerType: '渠道分销', cost: 400000 }, dims)
  assert.equal(r.target, 6.9)            // 11 ×0.7 ×0.9 = 6.93，分档内不夹
  assert.equal(r.floor, 5)
  assert.equal(r.clamped, false)
  assert.match(r.breakdown.at(-1)!.note!, /渠道分销/)
})

// ============================================================
// 分项建议毛利（part_margin）
// ============================================================
test('computePartMargins: 目标 + 品类修正，每个夹 [floor, cap]', () => {
  const r = computePartMargins(15, { CPU: 2, Memory: 3, 'HDD/SSD': -2, GPU: 8 }, 7, 30)
  assert.equal(r.default, 15)
  const by: Record<string, number> = {}
  r.parts.forEach((p) => { by[p.category] = p.margin })
  assert.equal(by['CPU'], 17)
  assert.equal(by['Memory'], 18)
  assert.equal(by['HDD/SSD'], 13)
  assert.equal(by['GPU'], 23)            // 15+8=23 < cap，不夹
  // 超封顶夹 cap / 低于保底夹 floor
  const r2 = computePartMargins(15, { GPU: 20, 'HDD/SSD': -20 }, 7, 30)
  assert.equal(r2.parts.find(p => p.category === 'GPU')!.margin, 30)
  assert.equal(r2.parts.find(p => p.category === 'HDD/SSD')!.margin, 7)
  // 空表 → 只有 default
  const r3 = computePartMargins(15, null, 7, 30)
  assert.equal(r3.default, 15)
  assert.equal(r3.parts.length, 0)
})

// ============================================================
// 默认系数契约：DEFAULT_DIM_BODIES 在典型 deal 下产出预期毛利
// ============================================================
test('契约: DEFAULT_DIM_BODIES 集成（Polaris/政企/海外/集采/2U/12w → 15%，集采走分档 5~20；零散走默认 7~30）', () => {
  const r = computeTargetMargin(
    { platform: 'Polaris', industry: '政企信息化', region: '东南亚', customerType: '集采项目', form: '2U', cost: 120000 },
    DEFAULT_DIM_BODIES as unknown as PricingDims,
  )
  assert.equal(r.target, 15)             // (15+3+2+0) ×0.75 = 15
  assert.equal(r.floor, 5)               // 集采项目分档红线
  assert.equal(r.cap, 20)
  assert.equal(r.fixedFee, 800)          // 默认海外每台固定费
  const r2 = computeTargetMargin(
    { platform: 'Polaris', industry: '政企信息化', region: '东南亚', customerType: '零散项目', form: '2U', cost: 120000 },
    DEFAULT_DIM_BODIES as unknown as PricingDims,
  )
  assert.equal(r2.target, 20)            // (15+3+2+0) ×1.0 = 20
  assert.equal(r2.floor, 7)              // 无分档 → 默认档
  assert.equal(r2.cap, 30)
  assert.equal(r2.fixedFee, 800)
})
