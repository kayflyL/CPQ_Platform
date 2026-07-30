/**
 * 选型规则引擎单测 —— 用 node 原生 test runner 跑（无需 vitest/node_modules）。
 *   npx 不需要，直接：node --test frontend/src/stores/selectionEngine.test.ts
 *
 * 覆盖五种 action 的求值正确性，以及 when 解析 / 字段寻址 / 取整方向等易错点。
 * 这里锁住的是 CPQ 选型的正确性下限：互斥判定、必配数量、派生取整一旦错，会直接产出不可交付的报价。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  evalOp, resolveField, resolveValue, evalWhen, evalThen, evaluateRules, evalAssignValue, parseCat,
  type RuleContext,
} from './selectionEngine.ts'

// ── 测试夹具：构造一条兼容性规则（绕过 CompatibilityRule 的必填字段，仅给引擎用到的）──
function rule(partial: any): any {
  return {
    id: 1, name: 'r', status: 'active',
    body: { when: undefined, then: undefined, desc: undefined },
    ...partial,
  }
}

// 一个常用 ctx：2 条不同型号内存 + 1 块 GPU + 4 块 NVMe 盘
function sampleCtx(): RuleContext {
  return {
    kp: {
      Memory: {
        qty: 2,
        items: [
          { pn: 'MEM-3200-16', spec: {} },
          { pn: 'MEM-4800-16', spec: {} },
        ],
        spec: {},
      },
      GPU: { qty: 1, items: [{ pn: 'GPU-A', spec: {} }], spec: {} },
      'HDD/SSD': {
        qty: 4,
        items: [{ pn: 'SSD-NVMe-1', spec: { interface: 'NVMe' } }],
        spec: { interface: 'NVMe' },
      },
    },
    config: { series: 'Polaris', sata_qty: 8 },
    opportunity: { platform_type: 'Polaris' },
  }
}

// ============================================================
// evalOp —— 操作符语义
// ============================================================
test('evalOp: 比较操作符按数值比较', () => {
  assert.equal(evalOp(3, '>=', 2), true)
  assert.equal(evalOp(2, '>=', 2), true)
  assert.equal(evalOp(1, '>=', 2), false)
  assert.equal(evalOp(5, '<=', 5), true)
  assert.equal(evalOp(6, '>', 5), true)
  assert.equal(evalOp(5, '<', 5), false)
})

test('evalOp: == / != 宽松相等（"3" == 3）', () => {
  assert.equal(evalOp('3', '==', 3), true)
  assert.equal(evalOp('Polaris', '==', 'Polaris'), true)
  assert.equal(evalOp('A', '!=', 'B'), true)
  assert.equal(evalOp('A', '!=', 'A'), false)
})

test('evalOp: in 判定成员', () => {
  assert.equal(evalOp('Polaris', 'in', ['Polaris', 'Orion']), true)
  assert.equal(evalOp('Zen', 'in', ['Polaris', 'Orion']), false)
  // expected 非数组时安全失败
  assert.equal(evalOp('Polaris', 'in', 'Polaris'), false)
})

test('evalOp: contains 支持数组与字符串', () => {
  assert.equal(evalOp(['NVMe', 'SATA'], 'contains', 'NVMe'), true)
  assert.equal(evalOp('tri-mode backplane', 'contains', 'tri-mode'), true)
  assert.equal(evalOp('abc', 'contains', 'z'), false)
})

test('evalOp: exists 判定非空（null/undefined/"" 均视作不存在）', () => {
  assert.equal(evalOp('x', 'exists', undefined), true)
  assert.equal(evalOp('', 'exists', undefined), false)
  assert.equal(evalOp(null, 'exists', undefined), false)
  assert.equal(evalOp(undefined, 'exists', undefined), false)
})

test('evalOp: 未知操作符返回 false（不抛异常）', () => {
  assert.equal(evalOp(1, '~=', 1), false)
})

// ============================================================
// resolveField / resolveValue —— 字段寻址
// ============================================================
test('resolveField: kp.<cat>.qty / spec.<key> / 不存在分类', () => {
  const ctx = sampleCtx()
  assert.equal(resolveField(ctx, 'kp.Memory.qty'), 2)
  assert.equal(resolveField(ctx, 'kp.HDD/SSD.spec.interface'), 'NVMe')
  assert.equal(resolveField(ctx, 'kp.NotExist.qty'), undefined)
  assert.equal(resolveField(ctx, 'kp.Memory.spec.nokey'), undefined)
})

test('resolveField: config / opportunity 根', () => {
  const ctx = sampleCtx()
  assert.equal(resolveField(ctx, 'config.series'), 'Polaris')
  assert.equal(resolveField(ctx, 'config.sata_qty'), 8)
  assert.equal(resolveField(ctx, 'opportunity.platform_type'), 'Polaris')
  assert.equal(resolveField(ctx, 'config.missing'), undefined)
})

test('resolveField: config.sata_qty/sas_qty/nvme_qty 盘类型计数（线缆规则寻址）', () => {
  const ctx: RuleContext = { kp: {}, config: { sata_qty: 8, sas_qty: 4, nvme_qty: 2 }, opportunity: {} }
  assert.equal(resolveField(ctx, 'config.sata_qty'), 8)
  assert.equal(resolveField(ctx, 'config.sas_qty'), 4)
  assert.equal(resolveField(ctx, 'config.nvme_qty'), 2)
})

test('resolveValue: 字段路径取 ctx 值，字面量原样返回', () => {
  const ctx = sampleCtx()
  assert.equal(resolveValue(ctx, 'kp.GPU.qty'), 1)         // 字段路径
  assert.equal(resolveValue(ctx, 'NVMe'), 'NVMe')          // 字面量
  assert.equal(resolveValue(ctx, 3), 3)                    // 非字符串
  assert.equal(resolveValue(ctx, 'kp.NoCat.qty'), 'kp.NoCat.qty')  // 路径解析不到 → 退回字面量
})

test('parseCat: 去掉 kp. 前缀', () => {
  assert.equal(parseCat('kp.GPU供电线'), 'GPU供电线')
  assert.equal(parseCat('GPU'), 'GPU')
  assert.equal(parseCat(undefined), '')
})

// ============================================================
// evalWhen —— all / any / 单条件 / 空
// ============================================================
test('evalWhen: all 需全部满足', () => {
  const ctx = sampleCtx()
  assert.equal(evalWhen(ctx, { all: [
    { field: 'kp.GPU.qty', op: '>=', value: 1 },
    { field: 'config.series', op: '==', value: 'Polaris' },
  ] }), true)
  assert.equal(evalWhen(ctx, { all: [
    { field: 'kp.GPU.qty', op: '>=', value: 1 },
    { field: 'config.series', op: '==', value: 'Orion' },   // 不满足
  ] }), false)
})

test('evalWhen: any 任一满足即可', () => {
  const ctx = sampleCtx()
  assert.equal(evalWhen(ctx, { any: [
    { field: 'config.series', op: '==', value: 'Orion' },
    { field: 'config.series', op: '==', value: 'Polaris' },
  ] }), true)
})

test('evalWhen: 单条件（when 直接是 cond）与空 when 均放行', () => {
  const ctx = sampleCtx()
  assert.equal(evalWhen(ctx, { field: 'kp.GPU.qty', op: '>=', value: 1 }), true)
  assert.equal(evalWhen(ctx, undefined), true)
  assert.equal(evalWhen(ctx, {}), true)
})

// ============================================================
// evalThen —— exclude（互斥：同 unique_field 不同值）
// ============================================================
test('evalThen exclude: ≥2 条且 unique_field 不同 → 命中冲突', () => {
  const ctx = sampleCtx()  // Memory 有 2 条不同 pn
  const out = evalThen(ctx, rule({
    name: '内存同型号不混搭',
    body: { then: { action: 'exclude', target: 'kp.Memory', unique_field: 'pn' } },
  }))
  assert.equal(out.length, 1)
  assert.equal(out[0].action, 'exclude')
  assert.equal(out[0].severity, 'conflict')
  assert.deepEqual(out[0].offenders, ['MEM-3200-16', 'MEM-4800-16'])
})

test('evalThen exclude: 同 pn 不冲突；仅 1 条不判定', () => {
  const ctx: RuleContext = {
    kp: { Memory: { qty: 2, items: [{ pn: 'MEM-X', spec: {} }, { pn: 'MEM-X', spec: {} }], spec: {} } },
    config: {}, opportunity: {},
  }
  assert.equal(evalThen(ctx, rule({ body: { then: { action: 'exclude', target: 'kp.Memory', unique_field: 'pn' } } })).length, 0)

  ctx.kp.Memory = { qty: 1, items: [{ pn: 'MEM-X', spec: {} }], spec: {} }
  assert.equal(evalThen(ctx, rule({ body: { then: { action: 'exclude', target: 'kp.Memory', unique_field: 'pn' } } })).length, 0)
})

test('evalThen exclude: unique_field 默认 pn；target 无 kp. 前缀也识别', () => {
  const ctx = sampleCtx()
  const out = evalThen(ctx, rule({ body: { then: { action: 'exclude', target: 'Memory' } } }))
  assert.equal(out.length, 1)  // 缺省 unique_field=pn，仍命中
})

// ============================================================
// evalThen —— require（必配：数量 + spec 约束）
// ============================================================
test('evalThen require: 数量不足 → 命中；够 → 不命中', () => {
  const ctx = sampleCtx()  // GPU 1 个，GPU供电线 没有
  const r = rule({ body: { then: { action: 'require', target: 'kp.GPU供电线', min_qty: 1 } } })
  assert.equal(evalThen(ctx, r).length, 1)

  // 配上 1 条 GPU供电线后不再缺
  ctx.kp['GPU供电线'] = { qty: 1, items: [{ pn: 'CBL-GPU', spec: {} }], spec: {} }
  assert.equal(evalThen(ctx, r).length, 0)
})

test('evalThen require: min_qty 支持字段路径（数量随 GPU 数）', () => {
  const ctx = sampleCtx()  // GPU.qty=1，GPU供电线=0
  const r = rule({ body: { then: { action: 'require', target: 'kp.GPU供电线', min_qty: 'kp.GPU.qty' } } })
  const out = evalThen(ctx, r)
  assert.equal(out.length, 1)
  assert.match(out[0].desc, /需 1/)

  // GPU 加到 2、供电线仍 0 → 需 2
  ctx.kp.GPU = { qty: 2, items: [{ pn: 'GPU-A', spec: {} }, { pn: 'GPU-B', spec: {} }], spec: {} }
  const out2 = evalThen(ctx, r)
  assert.equal(out2.length, 1)
  assert.match(out2[0].desc, /需 2/)
})

test('evalThen require: spec_constraint 不符 → 命中；符合 → 不命中', () => {
  // NVMe 盘要求背板 support=tri-mode；当前无背板
  const ctx = sampleCtx()
  const r = rule({ body: { then: { action: 'require', target: 'kp.背板', spec_constraint: { support: 'tri-mode' } } } })
  assert.equal(evalThen(ctx, r).length, 1)  // 无背板 → 缺

  // 放一块 support=tri-mode 的背板
  ctx.kp['背板'] = { qty: 1, items: [{ pn: 'BP-TRI', spec: { support: 'tri-mode' } }], spec: {} }
  assert.equal(evalThen(ctx, r).length, 0)

  // 支持类型不符的背板仍判不符
  ctx.kp['背板'] = { qty: 1, items: [{ pn: 'BP-SATA', spec: { support: 'sata-only' } }], spec: {} }
  assert.equal(evalThen(ctx, r).length, 1)
})

// ============================================================
// evalThen —— derive（派生数量：basis ÷ per，ceil/floor）
// ============================================================
test('evalThen derive: ceil 向上取整（8 盘 ÷ 8 → 1 根）', () => {
  const ctx = sampleCtx()  // sata_qty=8
  const out = evalThen(ctx, rule({ body: { then: { action: 'derive', target: 'kp.前置背板', basis: 'config.sata_qty', per: 8, round: 'ceil' } } }))
  assert.equal(out.length, 1)
  assert.equal(out[0].deriveQty, 1)
  assert.equal(out[0].derivePer, 8)   // 透明展示用：每组基数随规则走
  assert.equal(out[0].action, 'derive')
})

test('evalThen derive: ceil 余数进位（9 盘 ÷ 8 → 2）', () => {
  const ctx = sampleCtx()
  ctx.config.sata_qty = 9
  const out = evalThen(ctx, rule({ body: { then: { action: 'derive', basis: 'config.sata_qty', per: 8, target: 'kp.前置背板', round: 'ceil' } } }))
  assert.equal(out[0].deriveQty, 2)
})

test('evalThen derive: floor 向下取整（默认 round）', () => {
  const ctx = sampleCtx()
  ctx.config.sata_qty = 9
  const out = evalThen(ctx, rule({ body: { then: { action: 'derive', basis: 'config.sata_qty', per: 8, target: 'kp.前置背板' } } }))
  assert.equal(out[0].deriveQty, 1)  // floor(9/8)=1
})

test('evalThen derive: 已有数量足够则不产生动作；basis<=0 跳过', () => {
  const ctx = sampleCtx()  // sata_qty=8 → 需 1
  const r = rule({ body: { then: { action: 'derive', basis: 'config.sata_qty', per: 8, target: 'kp.前置背板', round: 'ceil' } } })
  ctx.kp['前置背板'] = { qty: 1, items: [{ pn: 'X' }], spec: {} }
  assert.equal(evalThen(ctx, r).length, 0)  // 够了

  ctx.config.sata_qty = 0
  ctx.kp['前置背板'].qty = 0
  assert.equal(evalThen(ctx, r).length, 0)  // basis<=0，跳过
})

// ============================================================
// evalThen —— filter / recommend（总是返回动作）
// ============================================================
test('evalThen filter: 返回过滤动作，value 字段路径被解析', () => {
  const ctx = sampleCtx()  // platform_type=Polaris
  const out = evalThen(ctx, rule({ body: { then: { action: 'filter', scope: 'server_model', field: 'series', op: '==', value: 'opportunity.platform_type' } } }))
  assert.equal(out.length, 1)
  assert.equal(out[0].action, 'filter')
  assert.equal(out[0].filterValue, 'Polaris')  // 字段路径已解析
})

test('evalThen recommend: 返回推荐动作', () => {
  const ctx = sampleCtx()
  const out = evalThen(ctx, rule({ body: { then: { action: 'recommend', target: 'Polaris-G6', desc: '主推' } } }))
  assert.equal(out.length, 1)
  assert.equal(out[0].action, 'recommend')
  assert.equal(out[0].target, 'Polaris-G6')
})

// ============================================================
// evaluateRules —— 多规则编排：status 过滤 + when 不命中跳过
// ============================================================
test('evaluateRules: 跳过非 active 规则', () => {
  const ctx = sampleCtx()
  const rules = [
    rule({ id: 1, status: 'draft', body: { then: { action: 'recommend', target: 'X' } } }),
    rule({ id: 2, status: 'archived', body: { then: { action: 'recommend', target: 'Y' } } }),
    rule({ id: 3, status: 'active', body: { then: { action: 'recommend', target: 'Z' } } }),
  ]
  const out = evaluateRules(rules as any, ctx)
  assert.equal(out.length, 1)
  assert.equal(out[0].target, 'Z')
})

test('evaluateRules: when 不命中的规则跳过，命中的产出动作', () => {
  const ctx = sampleCtx()  // series=Polaris
  const rules = [
    rule({ id: 1, body: { when: { field: 'config.series', op: '==', value: 'Orion' }, then: { action: 'recommend', target: 'Orion-only' } } }),
    rule({ id: 2, body: { when: { field: 'config.series', op: '==', value: 'Polaris' }, then: { action: 'recommend', target: 'Polaris-rec' } } }),
  ]
  const out = evaluateRules(rules as any, ctx)
  assert.equal(out.length, 1)
  assert.equal(out[0].target, 'Polaris-rec')
})

test('evaluateRules: 默认 6 条 seed 规则在典型 ctx 下的集成行为', () => {
  // 复刻后端 DEFAULT_RULES（filter / bp_type 赋值 / SATA·SAS·NVMe·GPU线 derive），锁定 seed 与引擎的契约
  const ctx: RuleContext = {
    kp: { GPU: { qty: 1, items: [{ pn: 'GPU-A', spec: {} }], spec: {} } },
    config: { sata_qty: 8, sas_qty: 0, nvme_qty: 2, drive_kinds: ['SATA', 'NVMe'] },
    opportunity: { platform_type: 'Polaris' },
  }
  const seedRules = [
    rule({ id: 1, name: '按商机平台过滤候选机型', body: { when: { field: 'opportunity.platform_type', op: 'exists' }, then: { action: 'filter', scope: 'server_model', field: 'series', op: '==', value: 'opportunity.platform_type' } } }),
    rule({ id: 2, name: '背板类型：含 NVMe 盘→三模', body: { when: { field: 'config.drive_kinds', op: 'contains', value: 'NVMe' }, then: { action: 'derive', field: 'config.bp_type', value: 'tri' } } }),
    rule({ id: 3, name: 'SATA 线缆根数', body: { when: { field: 'config.sata_qty', op: '>=', value: 1 }, then: { action: 'derive', target: 'SATA', basis: 'config.sata_qty', per: 8, round: 'ceil' } } }),
    rule({ id: 4, name: 'SAS 线缆根数', body: { when: { field: 'config.sas_qty', op: '>=', value: 1 }, then: { action: 'derive', target: 'SAS', basis: 'config.sas_qty', per: 8, round: 'ceil' } } }),
    rule({ id: 5, name: 'NVMe 线缆根数', body: { when: { field: 'config.nvme_qty', op: '>=', value: 1 }, then: { action: 'derive', target: 'NVMe', basis: 'config.nvme_qty', per: 2, round: 'ceil' } } }),
    rule({ id: 6, name: 'GPU 供电线根数', body: { when: { field: 'kp.GPU.qty', op: '>=', value: 1 }, then: { action: 'derive', target: 'GPU线', basis: 'kp.GPU.qty', per: 1, round: 'ceil' } } }),
  ]
  const out = evaluateRules(seedRules as any, ctx)
  // 命中：filter + bp_type 赋值 + SATA(1) + NVMe(1) + GPU线(1) = 5；SAS 因 sas_qty=0 不命中
  assert.equal(out.length, 5)
  const qty: Record<string, number> = {}
  for (const a of out) if (a.action === 'derive' && a.deriveTarget) qty[a.deriveTarget] = a.deriveQty!
  assert.equal(qty['SATA'], 1)          // ceil(8/8)
  assert.equal(qty['NVMe'], 1)          // ceil(2/2)
  assert.equal(qty['GPU线'], 1)         // ceil(1/1)
  assert.equal(qty['SAS'], undefined)   // 未命中（sas_qty=0）
  const bp = out.find(a => a.assignField === 'config.bp_type')   // 含 NVMe → tri
  assert.equal(bp?.assignValue, 'tri')
  assert.ok(out.some(a => a.action === 'filter'))                // 平台过滤
})

// ============================================================
// evalThen derive（赋值型）+ evalAssignValue —— 条件→固定值（背板类型）
// ============================================================
test('evalThen derive 赋值型: then 带 field+value 产出 assign 动作（不走算术）', () => {
  const ctx = sampleCtx()
  const out = evalThen(ctx, rule({ body: { then: { action: 'derive', field: 'config.bp_type', value: 'tri' } } }))
  assert.equal(out.length, 1)
  assert.equal(out[0].action, 'derive')
  assert.equal(out[0].assignField, 'config.bp_type')
  assert.equal(out[0].assignValue, 'tri')
  assert.equal(out[0].deriveQty, undefined)  // 不应产出算术字段
})

test('evalAssignValue: 首条命中规则生效（short-circuit），更具体规则放前', () => {
  const ctx = { kp: {}, config: { drive_kinds: ['NVMe'] }, opportunity: {} } as RuleContext
  const rules = [
    // 规则1（在前）：含 NVMe → tri（应被采用）
    rule({ id: 1, body: { when: { field: 'config.drive_kinds', op: 'contains', value: 'NVMe' }, then: { action: 'derive', field: 'config.bp_type', value: 'tri' } } }),
    // 规则2（在后，也命中）：→ dc（不应采用，因规则1先命中）
    rule({ id: 2, body: { when: { any: [{ field: 'config.drive_kinds', op: 'contains', value: 'SATA' }, { field: 'config.drive_kinds', op: 'contains', value: 'NVMe' }] }, then: { action: 'derive', field: 'config.bp_type', value: 'dc' } } }),
  ]
  assert.equal(evalAssignValue(rules as any, ctx, 'config.bp_type'), 'tri')
})

test('evalAssignValue: 无命中返回 undefined（交消费端兜底 dc）', () => {
  const ctx = { kp: {}, config: { drive_kinds: [] }, opportunity: {} } as RuleContext
  const rules = [
    rule({ id: 1, body: { when: { field: 'config.drive_kinds', op: 'contains', value: 'SATA' }, then: { action: 'derive', field: 'config.bp_type', value: 'tri' } } }),
  ]
  assert.equal(evalAssignValue(rules as any, ctx, 'config.bp_type'), undefined)
})

test('evalAssignValue: 跳过算术型 derive 与非 active 规则', () => {
  const ctx = sampleCtx()
  const rules = [
    rule({ id: 1, status: 'draft', body: { then: { action: 'derive', field: 'config.bp_type', value: 'tri' } } }),
    rule({ id: 2, body: { then: { action: 'derive', basis: 'config.sata_qty', per: 8, target: 'kp.前置背板' } } }),
  ]
  assert.equal(evalAssignValue(rules as any, ctx, 'config.bp_type'), undefined)
})
