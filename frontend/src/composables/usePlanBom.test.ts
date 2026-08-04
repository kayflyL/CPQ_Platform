/**
 * usePlanBom L6 内容推导单测 —— 用 node 原生 test runner 跑（无需额外依赖）：
 *   node --test src/composables/usePlanBom.test.ts
 *
 * 锁住的是 L6 配置单内容正确性：GPU 型号清洗（desc 显示描述、绝不显示 pn）、
 * RAID 型号提取、Cable 行描述（SAS/NVMe 盘数驱动，物理规则见 ESA24V3-P 典型配置推算）。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { gpuModelFrom, raidModelFrom, cableDescFrom } from '../utils/bomL6Derive.ts'

// items 形状 = kpItemsFromPlan 输出（description = KP 名 + matched_spec，part_category = KP 品类）
const item = (part_category: string, description: string, qty = 1) => ({
  category: 'Key Parts', part_category, description, qty, pn: `pn-${description}`,
})

test('gpuModelFrom 去容量/规格后缀，保留型号描述', () => {
  const cases: [string, string][] = [
    ['NVIDIA RTX 5090 32G 涡轮卡', 'NVIDIA RTX 5090'],
    ['NVIDIA RTX 5090 32G 涡轮卡 · 容量=32G', 'NVIDIA RTX 5090'],
    ['AMD R9700', 'AMD R9700'],
    ['AMD AI Pro R9700 32G', 'AMD AI Pro R9700'],
    ['NVIDIA H100 80G', 'NVIDIA H100'],
    ['NVIDIA 4090涡轮卡', 'NVIDIA 4090'],
    ['NVIDIA GeForce RTX4090D 24GB', 'NVIDIA GeForce RTX4090D'],
    ['Nvida RTX PRO 5000 72G 涡轮显卡', 'Nvida RTX PRO 5000'],
  ]
  for (const [raw, want] of cases) {
    const items = [item('GPU card', raw)]
    assert.equal(gpuModelFrom(items), want, `raw=${raw}`)
  }
  // 无 GPU → 空
  assert.equal(gpuModelFrom([item('CPU', 'AMD EPYC 9745')]), '')
  assert.equal(gpuModelFrom([]), '')
})

test('raidModelFrom 从 RAID 名称提取型号数字', () => {
  const cases: [string, string][] = [
    ['LSI 9560-8i 4G+超级电容+支架', '9560'],
    ['LSI 9361-8i', '9361'],
    ['LSI-9540-8I', '9540'],
    ['LSI 9560-16i', '9560'],
  ]
  for (const [raw, want] of cases) {
    assert.equal(raidModelFrom([item('Raid card', raw)]), want, `raw=${raw}`)
  }
  assert.equal(raidModelFrom([item('GPU', 'AMD R9700')]), '')
  assert.equal(raidModelFrom([]), '')
})

test('cableDescFrom 按盘数驱动（SAS 按 4 取整 / NVMe 按 2 取整）', () => {
  // 配置1：2 SATA + 2 NVMe + 9560 → "9560 4SAS Cable\n2NVMe Cable"
  assert.equal(cableDescFrom({ sata: 2, sas: 0, nvme: 2 }, '9560'), '9560 4SAS Cable\n2NVMe Cable')
  // 配置2：2 SATA + 2 NVMe + 9361
  assert.equal(cableDescFrom({ sata: 2, sas: 0, nvme: 2 }, '9361'), '9361 4SAS Cable\n2NVMe Cable')
  // 配置3：2 SATA、无 NVMe → 只出 SAS
  assert.equal(cableDescFrom({ sata: 2, sas: 0, nvme: 0 }, '9361'), '9361 4SAS Cable')
  // 5-8 盘 → 8SAS
  assert.equal(cableDescFrom({ sata: 6, sas: 0, nvme: 0 }, '9560'), '9560 8SAS Cable')
  // 3-4 NVMe → 4NVMe（无 SAS/SATA 盘 → 只出 NVMe 缆）
  assert.equal(cableDescFrom({ sata: 0, sas: 0, nvme: 4 }, '9560'), '4NVMe Cable')
  // 无 RAID 只出 NVMe
  assert.equal(cableDescFrom({ sata: 2, sas: 0, nvme: 2 }, ''), '2NVMe Cable')
  // 都无 → 空（模板回落 front_cables）
  assert.equal(cableDescFrom({ sata: 0, sas: 0, nvme: 0 }, '9560'), '')
})
