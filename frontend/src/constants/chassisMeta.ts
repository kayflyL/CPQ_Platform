/**
 * 机箱域 SSOT —— 后面板槽位 / 选项标签 / 背板类型 / 电源 / 系列路由 的默认值与显示文案集中处。
 *
 * 与后端 base_config 能力档案（psu_bays / rear_slots / gpu_slots / max_tdp）互补：
 *   base_config 存「每台机箱的实际能力」（可在选型配置「机箱能力」标签按机箱改）；
 *   本文件存「缺数据时的兜底默认」+ 显示映射 + 关键词表——都是可配常量，拒绝散落硬编码。
 *
 * 配件↔机箱的适配判定（读 specs.bt/io_slot/kind/wattage/chassis）见 utils/partFit.ts。
 */
import type { RearSlot } from '@/api/serverConfig'

/** 盘类型协议集（SSOT 在 selectionEngine，这里透出给机箱域复用）*/
export { DRIVE_KIND_KEYS as CORE_DRIVE_KINDS } from '@/stores/selectionEngine'

/**
 * 后面板槽位按底座分模板（基于 15 份真实配置归纳）。
 *   - 2U AMD(Orion)：IO1~IO4 + OCP（单 GPU 走 IO1/2 双宽 FHFL）
 *   - 2U Polaris（兆芯）：IO1~IO4，无 OCP（OCP 是 AMD/Orion 平台特性；4U GPU 机仍带 OCP）
 *   - 4U GPU 机：仅 OCP（业内 GPU 槽与 IO 槽物理分区，IO1-4 是 2U 通用机 Riser 命名，4U 不用；
 *     8 GPU 走 gpu_slots，拓扑 direct/switch 走 gpu_arch；OCP3.0 是标准网卡位）
 * 2U 槽名沿用 IO1-4+OCP、cap 保持 3 不动，与存量配置一致（避免 step 容量行为回退）。
 * DEFAULT_REAR_SLOTS 是「base_config.rear_slots 缺失时」的兜底（= 2U AMD，最常见）。
 */
export const REAR_SLOTS_2U_AMD: RearSlot[] = [
  { name: 'IO1', cap: 3 }, { name: 'IO2', cap: 3 }, { name: 'IO3', cap: 3 }, { name: 'IO4', cap: 3 }, { name: 'OCP', cap: 1 },
]
// 2U Polaris（兆芯）：同 AMD 布局但无 OCP（真实配置 2U 兆芯无 OCP 行；4U GPU 机仍带 OCP）
export const REAR_SLOTS_2U_POLARIS: RearSlot[] = [
  { name: 'IO1', cap: 3 }, { name: 'IO2', cap: 3 }, { name: 'IO3', cap: 3 }, { name: 'IO4', cap: 3 },
]
// 4U GPU 机：后面板仅 OCP(网卡)，无 IO1-IO4 Riser。业内定式（Dell XE9680 / HPE DL380 GPU cage /
// Supermicro 4U）：GPU 槽与通用 IO 槽物理分区，IO1-4 是 2U 通用机命名；8 GPU 走 gpu_slots，拓扑走 gpu_arch。
// OCP3.0 是 4U GPU 机标准网卡位（独立分区），料号库 ocp_x16(AI)/ocp_x8(普通) 支撑。
export const REAR_SLOTS_4U: RearSlot[] = [{ name: 'OCP', cap: 1 }]

/** 后面板槽位兜底默认（= 2U AMD）。仅当 base_config.rear_slots 缺失时用。
 *  与后端 scripts/migrate_base_config_capability.py 的 DEFAULT_REAR_SLOTS 对齐。 */
export const DEFAULT_REAR_SLOTS: RearSlot[] = REAR_SLOTS_2U_AMD

/** 按 form+series 取该底座的标准后面板布局（「恢复标准布局」按钮 / 新建默认用）。返回克隆副本。
 *  2U AMD/Orion=IO1-4+OCP；2U Polaris（兆芯）=IO1-4 无 OCP；4U=仅 OCP（GPU 走 gpu_slots+gpu_arch，业内 GPU 机无 IO1-4）。 */
export function rearSlotsFor(form?: string, series?: string): RearSlot[] {
  if (form === '4U') return REAR_SLOTS_4U.map(s => ({ ...s }))                       // 4U GPU 机：仅 OCP，无 IO1-4
  if (form === '2U' && series === 'Polaris') return REAR_SLOTS_2U_POLARIS.map(s => ({ ...s }))
  return REAR_SLOTS_2U_AMD.map(s => ({ ...s }))
}

/** 组合槽：首次选默认 1 条（如 IO1/IO2 = 1×X16 + 1×X8），其余槽首次默认填满 cap。步进器仍可手改。 */
export const COMBO_REAR_SLOTS = ['IO1', 'IO2']

/** 后面板 option_type 显示标签（option_type 是料号库声明，标签是展示文案）*/
export const OPTION_LABEL: Record<string, string> = {
  x16: 'X16 Riser', x8: 'X8 Riser', nvme: 'NVMe模组', sata: 'SATA模组',
  ocp_x8: 'OCP X8', ocp_x16: 'OCP X16', blank: '挡片',
}
/** 取 option_type 的展示标签，未配置原样返回 */
export const optionLabel = (t: string) => OPTION_LABEL[t] || t

/**
 * 背板类型关键词。适配判定优先读 specs.bt（料号库声明），缺失时按这些关键词嗅探 name+bt 文本。
 * tri = 三模（SATA/SAS/NVMe 三协议）；dc = 直连（只 SATA/SAS）。关键词可配可扩。
 */
export const BACKPLANE_TYPE_KEYWORDS: Record<'tri' | 'dc', string[]> = {
  tri: ['三模', 'tri-mode', 'tri', '三协议'],
  dc: ['直连', 'direct', 'dc'],
}

/** 电源默认数量兜底（正常走 base_config.psu_bays，每台机箱可不同）*/
export const DEFAULT_PSU_BAYS = 2

/** GPU 架构选项（base_config.gpu_arch_default 用；与 useServerConfig.GpuArch = none/pt/switch 对齐）*/
export const GPU_ARCH_OPTIONS: { value: string; label: string }[] = [
  { value: 'none', label: '无 GPU' },
  { value: 'pt', label: '直通 (Passthrough)' },
  { value: 'switch', label: '交换 (Switch)' },
]

/**
 * 系列 → 后面板选项桶映射。rear-io 选项按 bucket 查（rear_io_api），不同系列可能走不同选项集。
 * 未在表里的系列走 DEFAULT_REAR_IO_BUCKET。未来 Intel/工作站 有独立 rear-IO 时在此加映射，
 * 或改造为按 server_series 动态分发（数据驱动）。
 */
export const SERIES_REAR_IO_BUCKET: Record<string, string> = {
  Polaris: 'Polaris',
}
export const DEFAULT_REAR_IO_BUCKET = 'Orion'
/** 取某系列对应的 rear-IO 选项桶（未配置走默认桶）*/
export function rearIOBucket(series?: string): string {
  return (series && SERIES_REAR_IO_BUCKET[series]) || DEFAULT_REAR_IO_BUCKET
}
