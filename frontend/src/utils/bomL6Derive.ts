/**
 * L6 内容推导（纯函数，无依赖）—— 供 usePlanBom 求值 bom_context 前的 vars 派生。
 *
 * 原则：desc 只显示【描述】，绝不显示 pn/料号；线缆等行按盘数/配件型号推导（物理规则
 * 见 docs 里 ESA24V3-P 典型配置推算，SAS 缆按 4 盘取整、NVMe 缆按 2 盘取整）。
 */
export const DRIVE_RE = /hdd|ssd|nvme|sata|sas|硬盘|存储/i
export const GPU_RE = /gpu|显卡|图形/i
export const PSU_RE = /psu|电源|power/i

/** GPU 型号清洗：去容量/规格后缀，如 "NVIDIA RTX 5090 32G 涡轮卡" → "NVIDIA RTX 5090"。 */
export function gpuModelFrom(items: any[]): string {
  const gpu = (items || []).find((it) =>
    GPU_RE.test(`${it.part_category || ''} ${it.description || ''} ${it.name || ''}`))
  if (!gpu) return ''
  const raw = (gpu.description || gpu.name || '').split('·')[0]  // 去掉 matched_spec 后缀
  let s = raw.trim()
  s = s.replace(/\s*(?:server edition|涡轮显卡|涡轮卡)\s*$/i, '')
  s = s.replace(/(?:\s|-)\d{1,3}\s*G(?:B)?\s*$/i, '')
  return s.trim()
}

/** 是否含高带宽网卡（100G/200G/400G，x16 卡）——io_slot riser 升级 x16（R26，YC-0722 样本）。 */
export function highBwNicFrom(items: any[]): boolean {
  return (items || []).some((it) => {
    const cat = `${it.part_category || ''} ${it.name || ''}`
    if (!/nic|网卡|网络/i.test(cat)) return false
    const blob = `${it.description || ''} ${it.catalogue || ''} ${it.name || ''}`
    return /(100|200|400)\s*g/i.test(blob)
  })
}

/** RAID 卡型号：从名称提数字型号（"LSI 9560-8i 4G" → "9560"），给 Cable 行做 "{型号} N SAS Cable"。 */
export function raidModelFrom(items: any[]): string {
  const raid = (items || []).find((it) =>
    /raid|阵列/i.test(`${it.part_category || ''} ${it.description || ''} ${it.name || ''}`))
  if (!raid) return ''
  const m = /(\d{3,4})-(\d{1,2})\s*[iI]/.exec(`${raid.description || ''} ${raid.name || ''}`)
  return m ? m[1] : ''
}

/** Cable 行描述（盘数驱动）：SAS/SATA 盘按 4 向上取整 → "{raid型号} {N}SAS Cable"；
 *  NVMe 盘按 2 向上取整 → "{N}NVMe Cable"。无 RAID 时只出 NVMe 缆；都无 → ''（模板回落盘型分组）。 */
export function cableDescFrom(counts: { sata: number; sas: number; nvme: number }, raidModel: string): string {
  const lines: string[] = []
  const sasTotal = (counts.sata || 0) + (counts.sas || 0)
  if (sasTotal > 0 && raidModel) {
    lines.push(`${raidModel} ${Math.ceil(sasTotal / 4) * 4}SAS Cable`)
  }
  const nvme = counts.nvme || 0
  if (nvme > 0) {
    lines.push(`${Math.ceil(nvme / 2) * 2}NVMe Cable`)
  }
  return lines.join('\n')
}
