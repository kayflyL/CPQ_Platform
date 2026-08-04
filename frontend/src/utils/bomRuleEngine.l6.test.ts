/**
 * L6 配置单生成集成测试 —— 用 node 原生 test runner：
 *   node --test src/utils/bomRuleEngine.l6.test.ts
 *
 * 用 ESA24V3-P（模板 2 = 4U8-GPU直连）配置1 的推导 vars 跑 evalBomContext，
 * 锁住 L6 内容：GPU Power cord / Cable 行 desc 全部为描述（绝不显示 pn）、
 * 背板三模、Direct connected 含 NVMe、空行可隐藏。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evalBomContext } from './bomRuleEngine.ts'
import type { BomEvalContext } from './bomRuleEngine.ts'

// ===== 模板 2（4U8-GPU直连）当前 DB rows =====
const TPL2_ROWS: any[] = [
  { type: 'front_backplane', label: 'Front backplane', rule: {
    qty: { kind: 'fixed', value: 1 },
    desc: { kind: 'template', template: '${bays}*3.5 ${bp_type_desc}' },
    desc_fallback: { kind: 'part_field', field: 'sub_type', category: '背板' } } },
  { type: 'rear_summary', label: 'Direct connection', rule: {
    qty: { kind: 'fixed', value: 1 }, desc: { kind: 'struct_count', scope: 'rear_all' } } },
  { type: 'heatsink', label: 'Heatsink', rule: {
    qty: { kind: 'part_quantity', category: 'heatsink' },
    desc: { kind: 'part_field', field: 'name', category: 'heatsink' },
    qty_fallback: { kind: 'fixed', value: 2 } } },
  { type: 'psu_requirement', label: 'Power Supply Requirement', rule: {
    qty: { kind: 'config_calc', key: 'psu_qty' },
    desc: { kind: 'template', template: '${psu_wattage}W' },
    desc_fallback: { kind: 'config_value', key: 'psu_name' } } },
  { type: 'gpu_power_cord', label: 'GPU Power cord', rule: {
    qty: { kind: 'config_calc', key: 'gpu_cable_qty' },
    desc: { kind: 'config_value', key: 'gpu_power_cord_desc' } } },
  { type: 'power_cord', label: 'Power cord', rule: {
    qty: { kind: 'config_calc', key: 'psu_qty' }, desc: { kind: 'fixed', value: '国标电源线' } } },
  { type: 'rail_kit', label: 'Rail kit', rule: {
    qty: { kind: 'part_quantity', category: 'rail' },
    desc: { kind: 'part_field', field: 'name', category: 'rail' },
    qty_fallback: { kind: 'fixed', value: 1 } } },
  { type: 'cable', label: 'Cable', rule: {
    qty: { kind: 'fixed', value: 1 },
    desc: { kind: 'config_value', key: 'cable_desc' },
    desc_fallback: { kind: 'struct_count', scope: 'front_cables' } } },
]

// ===== deriveVars 输出（usePlanBom，ESA24V3-P 配置1：8×RTX5090 + 2 NVMe + 2 SATA + 9560 RAID）=====
const VARS = {
  bays: 12, form: '4U', series: 'Orion',
  gpu_qty: 8, drive_count: 4, psu_qty: 4, psu_wattage: '2700',
  standard_riser: { IO1: '1*X8 FHFL', IO2: '1*X8 FHFL' }, riser_x16: '1*X16+1*X8 FHFL',
  bp_type: 'tri', bp_type_desc: 'NVMe/SATA/SAS',
  gpu_cable_qty: 8, cable_qty: 1,
  gpu_model: 'NVIDIA RTX 5090', nvme_count: 2,
  gpu_power_cord_desc: 'NVIDIA RTX 5090 power cord',
  raid_model: '9560',
  cable_desc: '9560 4SAS Cable\n2NVMe Cable',
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
    frontCableQty: (k: string) => (k === 'SATA' ? 1 : k === 'NVMe' ? 1 : 0),
    frontCableInfo: (k: string) => ({ pn: k, n: 1, group: 2, price: 0, name: '' }),
  }
}

test('ESA24V3-P 配置1 L6 内容（模板 2 + deriveVars）', () => {
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
  assert.equal(out['cable'].desc, '9560 4SAS Cable\n2NVMe Cable')     // RAID + 盘数驱动
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

test('无 RAID 时 Cable 回落盘型分组（front_cables）', () => {
  const out = evalBomContext(TPL2_ROWS, ctx({ cable_desc: '', raid_model: '' }))
  assert.equal(out['cable'].desc, '1*SATA，1*NVMe')   // front_cables：按盘型分组（桩：SATA/NVMe 各 1 组）
  assert.equal(out['cable'].qty, 1)
})

// 模板 1 新增的「GPU 直连」汇总行（qty=config_calc gpu_qty + desc=struct_count gpu_direct）：
// 严格"配了 GPU 才显示"——不配 GPU 时 desc 与 qty 都空 → BomTable 整行隐藏。
const GPU_DIRECT_ROW = {
  type: 'rear_summary', label: 'GPU 直连', mode: 'direct',
  rule: { qty: { kind: 'config_calc', key: 'gpu_qty' },
          desc: { kind: 'struct_count', scope: 'gpu_direct' } },
}

test('GPU 直连汇总：严格配 GPU 才显示（有 NVMe 无 GPU 也隐藏）', () => {
  const withGpu = evalBomContext([GPU_DIRECT_ROW], ctx({ gpu_qty: 2, nvme_count: 4, gpu_cable_qty: 2, gpu_power_cord_desc: 'RTX 5090 power cord' }))
  assert.equal(withGpu['rear_summary'].desc, '2*GPU')
  assert.equal(withGpu['rear_summary'].qty, 2)
  // 有 NVMe 但无 GPU → desc 空 + qty 空 → 仍隐藏（严格配 GPU 才显示）
  const noGpu = evalBomContext([GPU_DIRECT_ROW], ctx({ gpu_qty: 0, nvme_count: 4, gpu_cable_qty: 0, gpu_power_cord_desc: '' }))
  const row = noGpu['rear_summary']
  assert.equal(row.desc, '')
  assert.equal(row.qty, '')
  assert.ok((row.desc === '' || row.desc == null) && (row.qty === '' || row.qty == null || row.qty === 0))
})


// I6 R25：L6 描述式——io_slot 不查后面板料号，riser 规格 = 机型标准(standard_riser)，装 GPU → 升级 x16
const IO_SLOT_ROWS = [
  { type: 'io_slot', label: 'IO1', slot: 'IO1', rule: { qty: { kind: 'fixed', value: 1 }, desc: { kind: 'struct_count', scope: 'io_slot' } } },
  { type: 'io_slot', label: 'IO2', slot: 'IO2', rule: { qty: { kind: 'fixed', value: 1 }, desc: { kind: 'struct_count', scope: 'io_slot' } } },
]

test('io_slot 描述派生（数据驱动）：无 GPU → standard_riser；GPU → riser_x16；未配置 → 留空', () => {
  const noGpu = evalBomContext(IO_SLOT_ROWS, ctx({ gpu_qty: 0 }))
  assert.equal(noGpu['IO1'].desc, '1*X8 FHFL')
  assert.equal(noGpu['IO2'].desc, '1*X8 FHFL')
  const withGpu = evalBomContext(IO_SLOT_ROWS, ctx({ gpu_qty: 2 }))
  assert.equal(withGpu['IO1'].desc, '1*X16+1*X8 FHFL')
  // 未配置数据 → 留空（拒绝硬编码）
  const noData = evalBomContext(IO_SLOT_ROWS, ctx({ standard_riser: '', riser_x16: '' }))
  assert.equal(noData['IO1'].desc, '')
})
