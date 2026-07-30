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
  computeTargetMargin, resolveRegion, resolveCostTier, resolveQtyBand, suggestPrice,
  type PricingContext, type PricingDims,
} from './pricingEngine.ts'
import { DEFAULT_DIM_BODIES } from '../constants/pricingMeta.ts'

// ── 测试夹具：完整维度（镜像 backend seed DEFAULT_DIMS / pricingMeta DEFAULT_DIM_BODIES）──
function fullDims(): PricingDims {
  return {
    platform_baseline: { Polaris: 15, Orion: 11, Intel: 11, '工作站': 13 },
    industry_adj: { 'AI算力': 3, 'IDC机房': -2, '政企信息化': 3, '高校科研': 0, '安防存储': 1, '工业边缘': 2 },
    region_adj: { factors: { 国内: 0, 海外: 2, 偏远: 1 }, keywords: { 海外: ['海外', '东南亚', '欧美'], 偏远: ['西藏', '新疆'] } },
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
  const ctx: PricingContext = { platform: 'Polaris', industry: '政企信息化', region: '东南亚', customerType: '集采项目', cost: 120000, qty: 1 }
  // 15 +3(政企) +2(海外) =20 → ×0.75(集采)=15 → ×1.0(12w 中档)=15 → ×1.0(1台)=15 → clamp 7~30 =15
  const r = computeTargetMargin(ctx, fullDims())
  assert.equal(r.target, 15)
  assert.equal(r.clamped, false)
  assert.equal(r.breakdown.length, 7)
  assert.equal(r.breakdown[0].matched, 'Polaris')
  assert.equal(r.breakdown[2].matched, '海外')        // region 分桶后命中海外
  assert.equal(r.breakdown[5].matched, '≥1台')        // 台数折扣命中 1 台档
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

// ============================================================
// 默认系数契约：DEFAULT_DIM_BODIES 在典型 deal 下产出预期毛利
// ============================================================
test('契约: DEFAULT_DIM_BODIES 集成（Polaris/政企/海外/集采/12w → 15%）', () => {
  const r = computeTargetMargin(
    { platform: 'Polaris', industry: '政企信息化', region: '东南亚', customerType: '集采项目', cost: 120000 },
    DEFAULT_DIM_BODIES as unknown as PricingDims,
  )
  assert.equal(r.target, 15)
  assert.equal(r.floor, 7)
  assert.equal(r.cap, 30)
})
