/**
 * 选型配置页「服务器解剖图」区域定义 —— 数据驱动 SSOT（无硬编码规则名/分类）。
 *
 * 用途：策略中心-选型配置页新增「服务器图」视图：点击服务器上对应位置，
 *       显示该区域相关的兼容性规则。2U / 4U 布局与区域不同（forms 维度）。
 *
 * 区域 ↔ 规则关联：扫描规则 body 引用的字段（when.*.field / then.target / then.field / 值里的字段路径），
 *       与区域 fields 求交集，命中即属于该区域。一条规则可同时命中多个区域（规则本就跨组件）。
 *
 * 注意：区域关联的是「字段」，不是规则名/分类 —— 以后新增规则自动归位，无需改这里。
 *       新增 KP 品类时，如希望某区域涵盖它，只需在对应区域 fields 里补一项。
 */
import type { CompatibilityRule } from '@/api/compatibilityRules'

export type AnatomyForm = '2U' | '4U'

/** 区域装饰类型：决定俯视图里该区域块内画什么（数据驱动几何，装饰仅视觉） */
export type AnatomyRegionKind = 'bays' | 'cpus' | 'gpu' | 'fans' | 'psu' | 'io' | 'plain'

export interface AnatomyRegion {
  id: string
  name: string
  kind: AnatomyRegionKind
  /** 关联字段：支持 kp.<品类> / kp.<品类>.qty / kp.<品类>.spec.<键> / config.<字段> / opportunity.<字段>；
   *  以 .* 结尾表示前缀通配（如 kp.Memory.spec.*），裸 kp.<品类> 表示整个品类。 */
  fields: string[]
  /** 俯视图几何（viewBox 0 0 1000 560，坐标手绘） */
  x: number
  y: number
  w: number
  h: number
  tip?: string
}

const BAY_FIELDS = ['config.bays', 'config.sata_qty', 'config.sas_qty', 'config.nvme_qty', 'config.drive_kinds', 'kp.HDD/SSD']
const CPU_MEM_FIELDS = ['kp.CPU', 'kp.Memory', 'config.max_cpu', 'config.max_dimm']
const PSU_FIELDS = ['kp.PSU', 'kp.GPU供电线']
const NIC_FIELDS = ['kp.NIC']

/** 2U：前置盘位 → 背板 → CPU/内存 → 风扇 → 电源 → IO 扩展 + OCP */
export const SERVER_ANATOMY: Record<AnatomyForm, AnatomyRegion[]> = {
  '2U': [
    { id: 'bays',  name: '前置盘位', kind: 'bays',  fields: BAY_FIELDS,      x: 40,  y: 90, w: 230, h: 380, tip: 'SATA / SAS / NVMe 盘与背板、线缆相关规则' },
    { id: 'bp',    name: '背板',     kind: 'plain', fields: ['config.bp_type', 'kp.背板', 'kp.线缆'], x: 280, y: 90, w: 40, h: 380, tip: '三模 / 直连背板、线缆派生规则' },
    { id: 'cpu',   name: 'CPU·内存', kind: 'cpus',  fields: CPU_MEM_FIELDS,  x: 330, y: 90, w: 300, h: 380, tip: 'CPU 双路同型号、内存同型号、机型上限规则' },
    { id: 'fan',   name: '风扇',     kind: 'fans',  fields: [],              x: 640, y: 90, w: 100, h: 380 },
    { id: 'psu',   name: '电源',     kind: 'psu',   fields: PSU_FIELDS,      x: 750, y: 90, w: 100, h: 380, tip: '电源选配、GPU 供电相关规则' },
    { id: 'io',    name: 'IO·OCP',   kind: 'io',    fields: NIC_FIELDS,      x: 860, y: 90, w: 110, h: 380, tip: 'PCIe 扩展槽 / OCP 网卡位相关规则' },
  ],
  /** 4U：前置盘位 → CPU/内存 → GPU 区 → 风扇 → 电源（3+1）+ OCP */
  '4U': [
    { id: 'bays',  name: '前置盘位', kind: 'bays',  fields: BAY_FIELDS,      x: 40,  y: 90, w: 200, h: 380, tip: 'SATA / SAS / NVMe 盘与背板、线缆相关规则' },
    { id: 'cpu',   name: 'CPU·内存', kind: 'cpus',  fields: CPU_MEM_FIELDS,  x: 250, y: 90, w: 240, h: 380, tip: 'CPU 双路同型号、内存同型号、机型上限规则' },
    { id: 'gpu',   name: 'GPU 区',   kind: 'gpu',   fields: ['kp.GPU', 'kp.GPU供电线'], x: 500, y: 90, w: 260, h: 380, tip: 'GPU 同型号不混搭、GPU 供电线派生规则' },
    { id: 'fan',   name: '风扇',     kind: 'fans',  fields: [],              x: 770, y: 90, w: 110, h: 380 },
    { id: 'psu',   name: '电源',     kind: 'psu',   fields: PSU_FIELDS,      x: 890, y: 250, w: 80, h: 220, tip: '电源选配（3+1 冗余）、GPU 供电相关规则' },
    { id: 'io',    name: 'OCP·扩展', kind: 'io',    fields: NIC_FIELDS,      x: 890, y: 90, w: 80, h: 150, tip: 'OCP 网卡位 / PCIe 扩展槽相关规则' },
  ],
}

/** 单字段匹配：精确 / 裸品类前缀 / .* 通配 */
export function fieldMatches(ruleField: string, regionField: string): boolean {
  if (regionField.endsWith('.*')) return ruleField.startsWith(regionField.slice(0, -1))
  if (!regionField.includes('.')) return ruleField.startsWith(regionField + '.')
  return ruleField === regionField
}

/** 提取规则 body 引用的全部字段路径（when 条件 / then 动作目标与赋值） */
export function ruleFields(body: Record<string, any> | null): string[] {
  if (!body) return []
  const out = new Set<string>()
  const add = (v: unknown) => {
    if (typeof v === 'string' && /^(kp|config|opportunity)\./.test(v)) out.add(v)
  }
  const w = body.when
  if (w) {
    add(w.field)
    if (Array.isArray(w.all)) for (const c of w.all) { add(c?.field); add(c?.value) }
    if (Array.isArray(w.any)) for (const c of w.any) { add(c?.field); add(c?.value) }
    add(w.value)
  }
  const t = body.then
  if (t) {
    add(t.target)
    add(t.field)
    add(t.value)
  }
  return [...out]
}

/** 规则是否属于某区域（字段交集） */
export function ruleTouchesRegion(rule: Pick<CompatibilityRule, 'body'>, region: AnatomyRegion): boolean {
  return ruleFields(rule.body).some(f => region.fields.some(rf => fieldMatches(f, rf)))
}


/** 区域类型 → 默认关联字段（上传图纸标注按区域类型继承；与 SERVER_ANATOMY 同源语义） */
export const REGION_KIND_FIELDS: Record<AnatomyRegionKind, string[]> = {
  bays: BAY_FIELDS,
  cpus: CPU_MEM_FIELDS,
  gpu: ['kp.GPU', 'kp.GPU供电线'],
  fans: [],
  psu: PSU_FIELDS,
  io: NIC_FIELDS,
  plain: [],
}

/** 区域类型 → 中文名（上传图纸标注下拉 / 徽标提示） */
export const REGION_KIND_LABELS: Record<AnatomyRegionKind, string> = {
  bays: '盘位',
  cpus: 'CPU·内存',
  gpu: 'GPU 区',
  fans: '风扇',
  psu: '电源',
  io: 'IO·OCP',
  plain: '背板/其他',
}

/** 用户标注区域（与 DrawingRegion 结构一致，避免跨模块类型循环） */
export interface DrawingRegionLike {
  uid: string
  name: string
  region_type: AnatomyRegionKind
  x: number
  y: number
  width: number
  height: number
  remark?: string
}

/** 用户标注区域 → 规则匹配用 AnatomyRegion（字段按区域类型继承） */
export function regionFromDrawing(r: DrawingRegionLike): AnatomyRegion {
  return {
    id: r.uid,
    name: r.name,
    kind: r.region_type,
    fields: REGION_KIND_FIELDS[r.region_type],
    x: r.x,
    y: r.y,
    w: r.width,
    h: r.height,
    tip: r.remark,
  }
}
