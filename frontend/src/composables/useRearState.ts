/**
 * 后面板槽位「多重集」状态操作（共享内核）—— 基准配置编辑器与服务器配置页同源。
 *
 * 槽位装载状态是一个 option_type 数组，重复即数量：['x16','x16'] = 2 条 X16 Riser。
 * - 基准配置：存 rear_slots[].defaults（产默认卡 + 默认数量）
 * - 配置页：useServerConfig 的 reactive rear 对象（消费 + 调数量），rear[slot] 即此形状
 *
 * 所有写操作**就地改传入数组**（splice，不替换引用）——这样配置页的 reactive rear 与
 * 基准配置的 rear_slots[].defaults 都能用同一份逻辑，且改动双向回流到各自的响应式宿主。
 * 'blank' = 挡片，不计入数量；历史数据里的 'blank' 在读取时丢弃。
 */
import { COMBO_REAR_SLOTS } from '@/constants/chassisMeta'

/** 槽位中某 option_type 的数量（blank 不计） */
export function rearOptionQty(arr: string[] | undefined, optionType: string): number {
  return (arr || []).filter(t => t === optionType && t !== 'blank').length
}

/** 槽位已装总数（blank 不计） */
export function rearSlotFilled(arr: string[] | undefined): number {
  return (arr || []).filter(t => t !== 'blank').length
}

/** 就地把 arr 内容替换为 next（保持数组引用不变 → 宿主响应式不丢） */
function replaceInPlace(arr: string[], next: string[]) {
  arr.splice(0, arr.length, ...next)
}

/** 设某 option_type 数量为 qty，其它 option 保留；cap 限制该槽总容量（就地改 arr） */
export function rearSetOptionQty(arr: string[], optionType: string, qty: number, cap?: number) {
  const others = arr.filter(t => t !== optionType && t !== 'blank')
  const remaining = cap != null ? Math.max(0, cap - others.length) : Infinity
  const newQty = Math.max(0, Math.min(qty, remaining))
  replaceInPlace(arr, [...others, ...Array.from({ length: newQty }, () => optionType)])
}

/** 默认数量：组合槽(COMBO_REAR_SLOTS，如 IO1/IO2=1×X16+1×X8)首次选默认 1；其余槽默认填满槽(cap)。步进器仍可任意手改。 */
export function rearDefaultQty(slot: string, cap?: number, comboSlots: string[] = COMBO_REAR_SLOTS): number {
  if (comboSlots.includes(slot)) return 1
  return cap ?? 1
}

/** 加一：首次选按 rearDefaultQty（组合槽 1 / 其余填满 cap），否则 +1；受 cap 上限约束 */
export function rearIncOption(arr: string[], optionType: string, cap: number | undefined, slot: string, comboSlots?: string[]) {
  const cur = rearOptionQty(arr, optionType)
  rearSetOptionQty(arr, optionType, cur === 0 ? rearDefaultQty(slot, cap, comboSlots) : cur + 1, cap)
}

/** 减一 */
export function rearDecOption(arr: string[], optionType: string) {
  rearSetOptionQty(arr, optionType, rearOptionQty(arr, optionType) - 1)
}

/** 槽位已选 option_type 去重列表（blank 不计，用于明细/锁定类型推导） */
export function rearUniqueReal(arr: string[] | undefined): string[] {
  return [...new Set((arr || []).filter(t => t !== 'blank'))]
}

/** 单选槽位（如 OCP 网络卡）：就地设为 [type] 或清空 */
export function rearSetSingle(arr: string[], optionType: string | null) {
  replaceInPlace(arr, optionType && optionType !== 'blank' ? [optionType] : [])
}

/** 读取已保存配置时归一：旧 string / 数组一律转数组（blank 丢弃），就地写入 arr */
export function rearLoadInto(arr: string[], raw: any) {
  if (raw == null) { replaceInPlace(arr, []); return }
  if (Array.isArray(raw)) replaceInPlace(arr, raw.filter((t: string) => t !== 'blank'))
  else if (typeof raw === 'string' && raw !== 'blank') replaceInPlace(arr, [raw])
  else replaceInPlace(arr, [])
}
