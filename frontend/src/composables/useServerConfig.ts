/**
 * 服务器配置流程的状态中枢（配置面用）。
 * 管理 KP 选配 / GPU 架构 / 后面板槽位 / 手改覆盖。
 * 前面板线缆和 GPU 供电线已迁移到 CRE 兼容性规则卡片，此处不再调用推导 API。
 *
 * 默认值（电源数、组合槽）取自 constants/chassisMeta SSOT；per-chassis 实际能力（psu_bays）
 * 由 L6ChassisConfig 加载 base_config 后注入 basePsuBays。无散落硬编码。
 */
import { ref, reactive } from 'vue'
import { DEFAULT_PSU_BAYS } from '@/constants/chassisMeta'
import {
  rearOptionQty, rearSlotFilled, rearSetOptionQty, rearIncOption, rearDecOption,
  rearUniqueReal, rearSetSingle, rearLoadInto,
} from './useRearState'

export type GpuArch = 'none' | 'pt' | 'switch'
export interface KpLineCfg { cat: string; pn: string; qty: number }

export function useServerConfig() {
  const kpLines = ref<KpLineCfg[]>([])
  const gpuArch = ref<GpuArch>('none')
  // rear[slot] = option_type 数组（可重复，重复即"数量"）：['x16','x16'] = 2 条 X16 Riser。
  // 空数组 = 挡片；历史数据里的 'blank' 在读取时被忽略。
  const rear = reactive<Record<string, string[]>>({
    IO1: [], IO2: [], IO3: [], IO4: [], OCP: [],
  })
  /** 手改覆盖：fc-SATA/fc-NVMe...=线缆根数；psuQty=电源数量；bp=背板类型；bpPn=背板料号(手填兜底) */
  const overrides = reactive<Record<string, any>>({})
  /** 基准配置自带的背板类型（ConfigWizard 加载基准后回填，作 bpType 默认，优先于硬盘推导） */
  const baseBpType = ref<'tri' | 'dc' | null>(null)
  /** CRE 兼容性规则求出的背板类型（L6ChassisConfig 跑 derive 赋值规则注入），优先级低于手改/基准 */
  const derivedBpType = ref<'tri' | 'dc' | null>(null)
  /** CRE 兼容性规则求出的线缆默认数量（按类型键：SATA/SAS/NVMe/GPU线），L6ChassisConfig 跑 derive 算术规则注入；手改优先 */
  const derivedCableQty = ref<Record<string, number>>({})
  /** 基准配置的电源槽位数（L6ChassisConfig 加载 base_config.psu_bays 后注入；缺省 chassisMeta.DEFAULT_PSU_BAYS） */
  const basePsuBays = ref<number>(DEFAULT_PSU_BAYS)

  // ---- 显示值：手改覆盖优先，否则用 CRE 规则注入的默认数量 ----
  function frontCableQty(kind: string): number {
    const o = overrides['fc-' + kind]
    if (o != null) return o
    // 默认数量由 CRE 规则驱动（SATA/SAS÷per、NVMe÷per，per 可在选型配置页改即生效），不再写死 8/8/2
    return derivedCableQty.value[kind] ?? 0
  }
  function psuQty(): number {
    return overrides.psuQty ?? basePsuBays.value
  }
  function bpType(): 'tri' | 'dc' | null {
    // 允许手改覆盖为 null（表示"不选背板"），否则走默认链：手改 > 基准自带 > CRE规则推导 > dc 兜底
    if (overrides.bp === null) return null
    return overrides.bp ?? baseBpType.value ?? derivedBpType.value ?? 'dc'
  }
  function isManual(key: string) {
    return overrides[key] != null
  }
  function setOverride(key: string, val: any) {
    overrides[key] = val
  }
  function clearOverride(key: string) {
    delete overrides[key]
  }

  // ---- 后面板：按 option_type 计数（数组里的重复条目 = 数量）；逻辑下沉 useRearState（与 RearPanel 同源，无两份算法）----
  /** 取某槽的可变数组（缺省懒建空数组；rear 为 reactive，键级改动触发响应） */
  const rearArr = (slot: string): string[] => { if (!rear[slot]) rear[slot] = []; return rear[slot] }
  /** 槽位中某 option_type 的数量（blank 不计入） */
  function optionQty(slot: string, optionType: string): number { return rearOptionQty(rearArr(slot), optionType) }
  /** 槽位已装 Riser 总数（blank 不计入） */
  function slotFilled(slot: string): number { return rearSlotFilled(rearArr(slot)) }
  /** 设某 option_type 数量为 qty，其它 option 保留；cap 限制该槽位总容量（就地改，引用不变） */
  function setOptionQty(slot: string, optionType: string, qty: number, cap?: number) {
    rearSetOptionQty(rearArr(slot), optionType, qty, cap)
  }
  /** 加一：首次选按默认数量（组合槽 1 / 其余填满 cap），否则 +1；受 cap 约束（见 useRearState） */
  function incOption(slot: string, optionType: string, cap?: number) {
    rearIncOption(rearArr(slot), optionType, cap, slot)
  }
  function decOption(slot: string, optionType: string) { rearDecOption(rearArr(slot), optionType) }
  /** 槽位中已选 option_type 去重列表（blank 不计，用于明细） */
  function uniqueRealOptions(slot: string): string[] { return rearUniqueReal(rearArr(slot)) }
  /** 单选槽位（如 OCP 网络卡）：整槽设为 [optionType] 或清空（就地改） */
  function setRearSingle(slot: string, optionType: string | null) { rearSetSingle(rearArr(slot), optionType) }
  /** 读取已保存配置时归一 rear：旧 {slot:'x16'} / 数组一律转数组，blank 丢弃 */
  function loadRear(raw: Record<string, any> | undefined) {
    if (!raw) return
    for (const slot of Object.keys(rear)) rearLoadInto(rearArr(slot), raw[slot])
  }

  return {
    kpLines, gpuArch, rear, overrides, baseBpType, derivedBpType, derivedCableQty, basePsuBays,
    addKp: (cat = 'drive', pn = '', qty = 1) => kpLines.value.push({ cat, pn, qty }),
    delKp: (i: number) => kpLines.value.splice(i, 1),
    setKp: (i: number, patch: Partial<KpLineCfg>) => { kpLines.value[i] = { ...kpLines.value[i], ...patch } },
    frontCableQty, psuQty, bpType, isManual, setOverride, clearOverride,
    optionQty, slotFilled, setOptionQty, incOption, decOption, uniqueRealOptions, setRearSingle, loadRear,
  }
}
