/**
 * L6 配置单生成集成测试 —— 用 node 原生 test runner：
 *   node --test src/utils/bomRuleEngine.l6.test.ts
 *
 * 2026-09-15 重构后：模板 rows = 纯骨架（type/label/slot/mode），
 * 取值语义 = 行类型固定属性（TYPE_RULES）——fixture 与 DB 迁移后同形。
 * 用 ESA240 V3（模板 2 = 4U8-GPU直连）配置1 的推导 vars 跑 evalBomContext，
 * 锁住 L6 内容：GPU Power cord / Cable 行 desc 全部为描述（绝不显示 pn）、
 * 背板三模、Direct connected 含 NVMe、空行可隐藏、fan 兜底数量跟形态走。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evalBomContext } from './bomRuleEngine.ts'
import type { BomEvalContext } from './bomRuleEngine.ts'

// ===== 模板 2（4U8-GPU直连）迁移后骨架（rule 键已剥，语义在 TYPE_RULES）=====
const TPL2_ROWS: any[] = [
  { type: 'front_backplane', label: 'Front backplane' },
  { type: 'rear_summary', label: 'Direct connection', mode: 'direct' },
  { type: 'heatsink', label: 'Heatsink' },
  { type: 'fan', label: 'FAN' },
  { type: 'psu_requirement', label: 'Power Supply Requirement' },
  { type: 'gpu_power_cord', label: 'GPU Power cord' },
  { type: 'power_cord', label: 'Power cord' },
  { type: 'rail_kit', label: 'Rail kit' },
  { type: 'cable', label: 'Cable' },
]

// ===== deriveVars 输出（usePlanBom，ESA240 V3 配置1：8×RTX5090 + 2 NVMe + 2 SATA + 9560 RAID）=====
const VARS = {
  bays: 12, form: '4U', series: 'Orion',
  gpu_qty: 8, drive_count: 4, psu_qty: 4, psu_wattage: '2700',
  standard_riser: { IO1: '1*X8 FHFL', IO2: '1*X8 FHFL' }, riser_x16: '1*X16+1*X8 FHFL',
  bp_type: 'tri', bp_type_desc: 'NVMe/SATA/SAS',
  gpu_cable_qty: 8, cable_qty: 1,
  gpu_model: 'NVIDIA RTX 5090', nvme_count: 2,
  gpu_power_cord_desc: 'NVIDIA RTX 5090 power cord',
  raid_model: '9560', sata_count: 2, sas_count: 0,
}

function ctx(over: Partial<Record<string, any>> = {}): BomEvalContext {
  return {
    vars: { ...VARS, ...over },
    parts: [
      { category: '机箱主体', name: '4U-Orion', pn: 'pn-4U-Orion', quantity: 1, specs: { form: ['4U'], chassis: ['Orion'] } },
      { category: 'CPU散热器', name: '2U heatsink', pn: 'S.E.M.0000502', quantity: 2, specs: {} },
      { category: '滑轨', name: 'Rail', pn: 'S.E.M.0000503', quantity: 1, specs: {} },
    ],
    rear: { IO1: ['x16', 'x8'], IO2: ['x8'], OCP: ['ocp_x8'] },
  }
}

test('ESA240 V3 配置1 L6 内容（模板 2 骨架 + deriveVars）', () => {
  const out = evalBomContext(TPL2_ROWS, ctx())
  assert.equal(out['front_backplane'].desc, '12*3.5 NVMe/SATA/SAS')   // 三模背板
  assert.equal(out['front_backplane'].qty, 1)
  assert.match(out['rear_summary'].desc, /8\*GPU/)                    // Direct connected
  assert.match(out['rear_summary'].desc, /2NVME/)                      // NVMe 直连汇总
  assert.equal(out['heatsink'].desc, '2U heatsink')                    // 料件入库后 part_field 取到
  assert.equal(out['heatsink'].qty, 2)
  assert.equal(out['psu_requirement'].desc, '2700W')
  assert.equal(out['psu_requirement'].qty, 4)
  assert.equal(out['gpu_power_cord'].desc, 'NVIDIA RTX 5090 power cord') // desc=描述，非 pn
  assert.equal(out['gpu_power_cord'].qty, 8)
  assert.equal(out['power_cord'].desc, '国标电源线')
  assert.equal(out['power_cord'].qty, 4)
  assert.equal(out['rail_kit'].desc, 'Rail')
  assert.equal(out['rail_kit'].qty, 1)
  // Cable 行（用户定调 2026-09-17）：单行汇总、qty 恒 1、描述按盘型分段写各自组数
  // 2 SATA（⌈2/8⌉=1 组，带 RAID 前缀）+ 2 NVMe（⌈2/2⌉=1 组，不带前缀）
  assert.equal(out['cable'].desc, '9560 SATA cable*1\nNVMe cable*1')
  assert.equal(out['cable'].qty, 1)
})

test('无 GPU 时 GPU Power cord 空（前端将隐藏该行）', () => {
  const out = evalBomContext(TPL2_ROWS, ctx({ gpu_qty: 0, gpu_cable_qty: 0, gpu_power_cord_desc: '' }))
  const row = out['gpu_power_cord']
  assert.equal(row.desc, '')
  assert.equal(row.qty, '')   // config_calc 0 → 空（不进 0，保证可隐藏）
  // BomTable 过滤条件：desc 与 qty 都空 → 不显示
  assert.ok((row.desc === '' || row.desc == null) && (row.qty === '' || row.qty == null || row.qty === 0))
})

// Cable 行（cable_groups，用户定调 2026-09-17）：无盘 → 整行隐藏；自定义分组/模板完全接管
test('cable 行：没盘 → desc/qty 全空整行隐藏（qty 恒 1 不留孤儿行）', () => {
  const out = evalBomContext(TPL2_ROWS, ctx({ sata_count: 0, sas_count: 0, nvme_count: 0 }))
  assert.equal(out['cable'].desc, '')
  assert.equal(out['cable'].qty, '')
})

test('cable 行：无 RAID 型号自动去前缀；SAS 独立分组不与 SATA 合并', () => {
  const out = evalBomContext(TPL2_ROWS, ctx({ raid_model: '', sata_count: 2, sas_count: 9, nvme_count: 0 }))
  // 2 SATA → 1 组；9 SAS → ⌈9/8⌉=2 组；raid 缺省 → 前缀和空格一起去掉
  assert.equal(out['cable'].desc, 'SATA cable*1\nSAS cable*2')
})

test('cable 行：自定义分组大小与模板（如中文文案 ${raid_model} ${n}SAS 线缆）完全接管', () => {
  const row = {
    type: 'cable', label: 'Cable',
    rule: {
      desc: { kind: 'cable_groups', kinds: {
        SATA: { size: 4, template: '${raid_model} ${n}SATA 线缆' },
        SAS: { size: 8, template: 'SAS 线缆*${n}' },
        NVMe: { size: 2, template: 'NVMe cable*${n}' },
      } },
      qty: { kind: 'fixed', value: 1 },
    },
  }
  // 10 SATA → ⌈10/4⌉=3 组；2 NVMe → 1 组；0 SAS 不出现
  const out = evalBomContext([row], ctx({ sata_count: 10, sas_count: 0, nvme_count: 2 }))
  assert.equal(out['cable'].desc, '9560 3SATA 线缆\nNVMe cable*1')
  assert.equal(out['cable'].qty, 1)
})

// I6 R25 + R28：L6 描述式——riser 规格数据驱动；R28 起后面板显式选卡（重复=数量）优先按实际选择输出签名
const IO_SLOT_ROWS = [
  { type: 'io_slot', label: 'IO1', slot: 'IO1' },
  { type: 'io_slot', label: 'IO2', slot: 'IO2' },
]

test('io_slot 描述派生：显式选卡 → 实际规格签名；未选 → standard_riser；GPU → riser_x16；未配置 → 留空', () => {
  const base = ctx()
  const run = (rear: Record<string, string[]>, vars: Record<string, any> = {}) =>
    evalBomContext(IO_SLOT_ROWS, {
      ...base,
      vars: { ...base.vars, gpu_qty: 0, ...vars },
      rear: { ...base.rear, ...rear },
    })

  // 后面板显式选卡（重复即数量）→ desc 按实际选择（用户场景：IO1 选 3×X16 + 1×X8）
  const picked = run({ IO1: ['x16', 'x16', 'x16', 'x8'], IO2: ['x8'] })
  assert.equal(picked['IO1'].desc, '3*X16+1*X8')
  assert.equal(picked['IO2'].desc, '1*X8')
  // 未显式选卡 → 机型标准 standard_riser（兜底不变）
  const none = run({ IO1: [], IO2: [] })
  assert.equal(none['IO1'].desc, '1*X8 FHFL')
  assert.equal(none['IO2'].desc, '1*X8 FHFL')
  // 装 GPU → riser_x16（硬约束优先于选卡）
  const withGpu = run({ IO1: ['x8'] }, { gpu_qty: 2 })
  assert.equal(withGpu['IO1'].desc, '1*X16+1*X8 FHFL')
  // 未配置数据 → 留空（拒绝硬编码）
  const noData = run({ IO1: [], IO2: [] }, { standard_riser: '', riser_x16: '' })
  assert.equal(noData['IO1'].desc, '')
})

// OCP 网络槽行（引擎层防呆：slot=OCP 的 io_slot 行 qty 跟 ocp_qty 走，不再靠 UI 改规则）：
// desc 跟实际选的适配板（ocp_x8/ocp_x16）走，没选 OCP → desc 空 + qty 空 → 整行隐藏
const OCP_ROW = { type: 'io_slot', label: 'OCP', slot: 'OCP' }

test('OCP 行：desc 跟实际选适配板走（X16/X8），未选 → 空行可隐藏', () => {
  const base = ctx()
  const make = (ocp: string[], ocpQty: number, extra: Record<string, any> = {}) =>
    evalBomContext([OCP_ROW], {
      ...base,
      vars: { ...base.vars, ocp_qty: ocpQty, ...extra },
      rear: { ...base.rear, OCP: ocp },
    })
  const x16 = make(['ocp_x16'], 1)
  assert.equal(x16['OCP'].desc, 'OCP 3.0 X16')
  assert.equal(x16['OCP'].qty, 1)
  const x8 = make(['ocp_x8'], 1)
  assert.equal(x8['OCP'].desc, 'OCP 3.0 X8')
  assert.equal(x8['OCP'].qty, 1)
  // OCP 独立分段：装 GPU 不影响 OCP 描述（riser_x16 只作用于 PCIe IO 槽）
  const x8Gpu = make(['ocp_x8'], 1, { gpu_qty: 2 })
  assert.equal(x8Gpu['OCP'].desc, 'OCP 3.0 X8')
  // 未选 → desc 与 qty 都空 → BomTable / 规格书整行隐藏
  const none = make([], 0)
  assert.equal(none['OCP'].desc, '')
  assert.equal(none['OCP'].qty, '')
  assert.ok((none['OCP'].desc === '' || none['OCP'].desc == null) && (none['OCP'].qty === '' || none['OCP'].qty == null || none['OCP'].qty === 0))
})

// 分级匹配防回归（2026-09-15 风扇蹭线缆事故）：findBomPart ①category 命中优先 ②name 子串仅兜底。
// 复刻 ESA240 V3 实况：挂载列表里「风扇背板转接线」（电源分配线缆类，sort_order 靠前）
// 与「6056高性能热插拔风扇」（机箱风扇类，靠后）并存时，fan 行必须取真风扇。
const FAN_ROW = { type: 'fan', label: 'FAN' }
const FAN_ALIASES = { fan: ['风扇'] }

test('fan 行分级匹配：category 命中优先，线缆（name 含"风扇"）不得抢先', () => {
  const parts = [
    { category: '电源分配线缆', name: '风扇背板转接线（2x6pin→2x3pinX2 550mm）', pn: 'S.E.E.0001888', quantity: 1 },
    { category: '电源分配线缆', name: '风扇背板转接线（2x6pin→2x3pinX2 470mm）', pn: 'S.E.E.0002610', quantity: 1 },
    { category: '机箱风扇', name: '6056高性能热插拔风扇', pn: 'S.E.M.0000501', quantity: 12 },
  ]
  const out = evalBomContext([FAN_ROW], { ...ctx(), parts, categoryAliases: FAN_ALIASES })
  assert.equal(out['fan'].desc, '6056高性能热插拔风扇')
  assert.equal(out['fan'].qty, 12)
})

test('fan 行 name 子串兜底：库里没有任何风扇类件时仍能按名称找到（留给人工纠正的显式信号）', () => {
  const parts = [
    { category: '电源分配线缆', name: '风扇背板转接线（2x6pin→2x3pinX2 550mm）', pn: 'S.E.E.0001888', quantity: 1 },
  ]
  const out = evalBomContext([FAN_ROW], { ...ctx(), parts, categoryAliases: FAN_ALIASES })
  assert.equal(out['fan'].desc, '风扇背板转接线（2x6pin→2x3pinX2 550mm）')
  assert.equal(out['fan'].qty, 1)
})

// 用户定调：fan 兜底数量跟形态走（2U=6 / 4U=12）——规则不再存模板，由 form 变量驱动
test('fan 形态兜底：无风扇料件时 desc=系统风扇，qty 跟 form 走（4U=12 / 2U=6）', () => {
  const noFanParts = [
    { category: '机箱主体', name: '4U-Orion', pn: 'pn-4U-Orion', quantity: 1, specs: {} },
  ]
  const four = evalBomContext([FAN_ROW], { ...ctx({ form: '4U' }), parts: noFanParts, categoryAliases: FAN_ALIASES })
  assert.equal(four['fan'].desc, '系统风扇')
  assert.equal(four['fan'].qty, 12)
  const two = evalBomContext([FAN_ROW], { ...ctx({ form: '2U' }), parts: noFanParts, categoryAliases: FAN_ALIASES })
  assert.equal(two['fan'].desc, '系统风扇')
  assert.equal(two['fan'].qty, 6)
})

// 逐行 rule 优先（2026-09-15 三轮定稿）：行上带完整 rule 就完全按它求值；
// 省略 = 跟随类型默认。编辑页从类型默认拷贝起步改，能力=旧版完整规则。
test('rule 优先：行上自定义规则完全接管（含 fan 形态兜底被替换）', () => {
  const row = {
    type: 'fan', label: 'FAN',
    rule: {
      desc: { kind: 'fixed', value: '高速风扇' },
      qty: { kind: 'part_quantity', category: 'fan' },
      qty_fallback: { kind: 'fixed', value: 8 },
    },
  }
  const out = evalBomContext([row], {
    ...ctx({ form: '4U' }),   // 类型默认会兜 12，被行规则兜 8 接管
    parts: [{ category: '机箱主体', name: 'x', pn: 'pn', quantity: 1 }],
    categoryAliases: FAN_ALIASES,
  })
  assert.equal(out['fan'].desc, '高速风扇')   // 固定文字接管 part_field
  assert.equal(out['fan'].qty, 8)            // 自定义兜底数量接管形态表
})

test('rule 优先：psu 行换模板串 + 手填数量', () => {
  const row = {
    type: 'psu_requirement', label: 'PSU',
    rule: {
      desc: { kind: 'template', template: '${psu_wattage}W 钛金' },
      qty: { kind: 'manual' },
    },
  }
  const out = evalBomContext([row], ctx())
  assert.equal(out['psu_requirement'].desc, '2700W 钛金')
  assert.equal(out['psu_requirement'].qty, '')   // manual → 留空手填
})

test('rule 优先：OCP 特殊分支也可被行规则覆盖（如直接固定）', () => {
  const row = {
    type: 'io_slot', label: 'OCP', slot: 'OCP',
    rule: { desc: { kind: 'fixed', value: 'OCP 3.0 X16（标配）' }, qty: { kind: 'fixed', value: 1 } },
  }
  const out = evalBomContext([row], ctx({ ocp_qty: 0 }))
  assert.equal(out['OCP'].desc, 'OCP 3.0 X16（标配）')   // 未选也显示（用户显式选择固定）
  assert.equal(out['OCP'].qty, 1)
})

// 取值来源标注（预览「所见即所算」）：hit 主规则 / fb 兜底 / empty 留空
test('src 标注：料件命中=hit，无料件走兜底=fb', () => {
  const hit = evalBomContext([FAN_ROW], {
    ...ctx(),
    parts: [{ category: '机箱风扇', name: '6056高性能热插拔风扇', pn: 'S.E.M.0000501', quantity: 12 }],
    categoryAliases: FAN_ALIASES,
  })
  assert.equal(hit['fan'].descSrc, 'hit')
  assert.equal(hit['fan'].qtySrc, 'hit')
  const fb = evalBomContext([FAN_ROW], {
    ...ctx({ form: '4U' }),
    parts: [{ category: '机箱主体', name: 'x', pn: 'pn', quantity: 1 }],
    categoryAliases: FAN_ALIASES,
  })
  assert.equal(fb['fan'].descSrc, 'fb')
  assert.equal(fb['fan'].qtySrc, 'fb')
  assert.equal(fb['fan'].qty, 12)
})
