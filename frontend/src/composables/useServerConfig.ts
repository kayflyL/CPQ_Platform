/**
 * 服务器配置流程的状态中枢（配置面用）。
 * 管理 KP 选配 / GPU 架构 / 后面板槽位 / 手改覆盖，调 /api/derive 实时推导。
 * 对应原型 server-config-prototype.html 的配置面逻辑，落地为 Vue 响应式。
 */
import { ref, reactive } from 'vue'
import { deriveApi, type DeriveState, type DeriveResult } from '@/api/serverConfig'

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

  const deriving = ref(false)
  const result = ref<DeriveResult | null>(null)
  const error = ref('')

  /** 重新推导（KP/GPU 架构变化后调用） */
  async function rederive() {
    deriving.value = true
    error.value = ''
    try {
      const state: DeriveState = {
        kp_lines: kpLines.value.map(l => ({ cat: l.cat, pn: l.pn, qty: l.qty })),
        gpu_arch: gpuArch.value,
      }
      result.value = await deriveApi.derive(state)
    } catch (e: any) {
      error.value = e?.message || '推导失败'
    } finally {
      deriving.value = false
    }
  }

  // ---- KP 行操作（每次变动触发重新推导）----
  function addKp(cat = 'drive', pn = '', qty = 1) {
    kpLines.value.push({ cat, pn, qty })
    rederive()
  }
  function delKp(i: number) {
    kpLines.value.splice(i, 1)
    rederive()
  }
  function setKp(i: number, patch: Partial<KpLineCfg>) {
    kpLines.value[i] = { ...kpLines.value[i], ...patch }
    rederive()
  }

  // ---- 显示值：手改覆盖优先，否则用推导结果 ----
  function frontCableQty(kind: string): number {
    const o = overrides['fc-' + kind]
    if (o != null) return o
    return result.value?.front_cables.find(c => c.kind === kind)?.qty ?? 0
  }
  function psuQty(): number {
    return overrides.psuQty != null ? overrides.psuQty : (result.value?.psu.qty ?? 2)
  }
  function bpType(): 'tri' | 'dc' {
    return overrides.bp ?? baseBpType.value ?? result.value?.bp_type ?? 'dc'
  }
  function isManual(key: string) {
    return overrides[key] != null
  }
  function setOverride(key: string, val: any) {
    overrides[key] = val
  }
  function clearOverride(key: string) {
    delete overrides[key]
    rederive()
  }

  // ---- 后面板：按 option_type 计数（数组里的重复条目 = 数量）----
  /** 槽位中某 option_type 的数量（blank 不计入） */
  function optionQty(slot: string, optionType: string): number {
    return (rear[slot] || []).filter(t => t === optionType && t !== 'blank').length
  }
  /** 槽位已装 Riser 总数（blank 不计入） */
  function slotFilled(slot: string): number {
    return (rear[slot] || []).filter(t => t !== 'blank').length
  }
  /** 设某 option_type 数量为 qty，其它 option 保留；cap 限制该槽位总容量 */
  function setOptionQty(slot: string, optionType: string, qty: number, cap?: number) {
    const others = (rear[slot] || []).filter(t => t !== optionType && t !== 'blank')
    const remaining = cap != null ? Math.max(0, cap - others.length) : Infinity
    const newQty = Math.max(0, Math.min(qty, remaining))
    rear[slot] = [...others, ...Array.from({ length: newQty }, () => optionType)]
  }
  function incOption(slot: string, optionType: string, cap?: number) {
    const cur = optionQty(slot, optionType)
    // 首次选某 option：IO1/IO2(组合槽,1×X16+1×X8)默认 1；IO3/IO4/OCP 默认填满槽（cap）
    const next = cur === 0 ? defaultQtyFor(slot, cap) : cur + 1
    setOptionQty(slot, optionType, next, cap)
  }
  /** 默认数量：IO1/IO2 是 x16+x8 组合槽各 1；其余槽首次选择默认填满槽（cap）。步进器仍可任意手改。 */
  function defaultQtyFor(slot: string, cap?: number): number {
    if (slot === 'IO1' || slot === 'IO2') return 1
    return cap ?? 1
  }
  function decOption(slot: string, optionType: string) {
    setOptionQty(slot, optionType, optionQty(slot, optionType) - 1)
  }
  /** 槽位中已选 option_type 去重列表（blank 不计入，用于明细） */
  function uniqueRealOptions(slot: string): string[] {
    return [...new Set((rear[slot] || []).filter(t => t !== 'blank'))]
  }
  /** 单选槽位（如 OCP 网络卡）：整槽设为 [optionType] 或清空 */
  function setRearSingle(slot: string, optionType: string | null) {
    rear[slot] = optionType && optionType !== 'blank' ? [optionType] : []
  }
  /** 读取已保存配置时归一 rear：旧 {slot:'x16'} / 数组一律转数组，blank 丢弃 */
  function loadRear(raw: Record<string, any> | undefined) {
    if (!raw) return
    for (const slot of Object.keys(rear)) {
      const v = raw[slot]
      if (Array.isArray(v)) rear[slot] = v.filter(t => t !== 'blank')
      else if (typeof v === 'string' && v !== 'blank') rear[slot] = [v]
      else rear[slot] = []
    }
  }

  return {
    kpLines, gpuArch, rear, overrides, baseBpType, deriving, result, error,
    rederive, addKp, delKp, setKp,
    frontCableQty, psuQty, bpType, isManual, setOverride, clearOverride,
    optionQty, slotFilled, setOptionQty, incOption, decOption, uniqueRealOptions, setRearSingle, loadRear,
  }
}
