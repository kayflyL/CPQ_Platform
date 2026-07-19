/** 料号归一化 adapter —— 把 KpPart / PartMaster / PsuOption 三种源映射成统一的 PickerItem。
 *  只做形状映射，不合并两表（memory: kp-parts-unification-roadmap）。
 *  输出处强制断言 pn 为非空字符串——这是 L6 产出契约的兜底：
 *  PartPicker 的 update:modelValue 只回传 pn，若此处 pn 缺失会直接抛错而非静默破坏 picks/l6Rows。 */
import type { KpPart, PartMaster, PsuOption } from '@/api/serverConfig'
import type { PickerItem } from '@/types/picker'

function assertPn(x: PickerItem): PickerItem {
  if (typeof x.pn !== 'string' || !x.pn) {
    throw new Error(`[usePartAdapter] 归一化失败：源数据缺少 pn 字段，已阻止（避免破坏产出契约）`)
  }
  return x
}

export const fromKpPart = (p: KpPart): PickerItem =>
  assertPn({
    pn: p.pn, name: p.name, category: p.category, sub_type: p.sub_type,
    specs: p.specs, unit_price: p.unit_price, brand: p.brand,
    applicable: p.applicable, source: 'kp',
  })

export const fromPartMaster = (p: PartMaster): PickerItem =>
  assertPn({
    pn: p.pn, name: p.name, category: p.category, sub_type: p.sub_type,
    specs: p.specs, unit_price: p.unit_price, supplier: p.supplier,
    description: p.description, applicable: p.applicable, source: 'l6',
  })

export const fromPsuOption = (o: PsuOption): PickerItem =>
  assertPn({
    pn: o.pn, name: o.part_name, category: '电源',
    specs: { wattage: o.wattage }, unit_price: o.unit_price,
    description: o.description, source: 'psu',
  })
