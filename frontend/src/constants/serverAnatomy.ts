/**
 * serverconfig 配置向导中部「服务器解剖示意图」区域定义（2U/4U）。
 * 仅描述区域几何与装饰类型，供 ServerAnatomyMap 渲染，不参与规则匹配。
 */
export type AnatomyForm = '2U' | '4U'
export type AnatomyView = 'top' | 'front' | 'rear'

/** 区域装饰类型：决定俯视图里该区域块内画什么（数据驱动几何，装饰仅视觉） */
export type AnatomyRegionKind = 'bays' | 'cpus' | 'gpu' | 'fans' | 'psu' | 'io' | 'plain'

export interface AnatomyRegion {
  id: string
  name: string
  kind: AnatomyRegionKind
  /** 俯视图几何（viewBox 0 0 1000 560，坐标手绘） */
  x: number
  y: number
  w: number
  h: number
  tip?: string
}

/** 俯视图：前置盘位 → 背板 → CPU/内存 → 风扇 → 电源 → IO 扩展 + OCP */
const TOP: Record<AnatomyForm, AnatomyRegion[]> = {
  '2U': [
    { id: 'bays',  name: '前置盘位', kind: 'bays',  x: 40,  y: 90, w: 230, h: 380, tip: 'SATA / SAS / NVMe 盘位' },
    { id: 'bp',    name: '背板',     kind: 'plain', x: 280, y: 90, w: 40, h: 380, tip: '背板' },
    { id: 'cpu',   name: 'CPU·内存', kind: 'cpus',  x: 330, y: 90, w: 300, h: 380, tip: 'CPU 与内存插槽' },
    { id: 'fan',   name: '风扇',     kind: 'fans',  x: 640, y: 90, w: 100, h: 380 },
    { id: 'psu',   name: '电源',     kind: 'psu',   x: 750, y: 90, w: 100, h: 380, tip: '电源模块' },
    { id: 'io',    name: 'IO·OCP',   kind: 'io',    x: 860, y: 90, w: 110, h: 380, tip: 'PCIe 扩展槽 / OCP 网卡位' },
  ],
  /** 4U：前置盘位 → CPU/内存 → GPU 区 → 风扇 → 电源（3+1）+ OCP */
  '4U': [
    { id: 'bays',  name: '前置盘位', kind: 'bays',  x: 40,  y: 90, w: 200, h: 380, tip: 'SATA / SAS / NVMe 盘位' },
    { id: 'cpu',   name: 'CPU·内存', kind: 'cpus',  x: 250, y: 90, w: 240, h: 380, tip: 'CPU 与内存插槽' },
    { id: 'gpu',   name: 'GPU 区',   kind: 'gpu',   x: 500, y: 90, w: 260, h: 380, tip: 'GPU 扩展区' },
    { id: 'fan',   name: '风扇',     kind: 'fans',  x: 770, y: 90, w: 110, h: 380 },
    { id: 'psu',   name: '电源',     kind: 'psu',   x: 890, y: 250, w: 80, h: 220, tip: '电源模块' },
    { id: 'io',    name: 'OCP·扩展', kind: 'io',    x: 890, y: 90, w: 80, h: 150, tip: 'OCP 网卡位 / PCIe 扩展槽' },
  ],
}

/** 前视图：主要呈现前置盘位 */
const FRONT: Record<AnatomyForm, AnatomyRegion[]> = {
  '2U': [
    { id: 'bays', name: '前置盘位', kind: 'bays', x: 120, y: 100, w: 760, h: 360, tip: 'SATA / SAS / NVMe 盘位' },
  ],
  '4U': [
    { id: 'bays', name: '前置盘位', kind: 'bays', x: 120, y: 100, w: 760, h: 360, tip: 'SATA / SAS / NVMe 盘位' },
  ],
}

/** 后视图：主要呈现 IO/OCP 与电源 */
const REAR: Record<AnatomyForm, AnatomyRegion[]> = {
  '2U': [
    { id: 'io',  name: 'IO·OCP', kind: 'io',  x: 180, y: 90, w: 160, h: 380, tip: 'PCIe 扩展槽 / OCP 网卡位' },
    { id: 'psu', name: '电源',   kind: 'psu', x: 640, y: 90, w: 160, h: 380, tip: '电源模块' },
  ],
  '4U': [
    { id: 'io',  name: 'IO·OCP', kind: 'io',  x: 180, y: 90, w: 160, h: 380, tip: 'PCIe 扩展槽 / OCP 网卡位' },
    { id: 'psu', name: '电源',   kind: 'psu', x: 640, y: 90, w: 160, h: 380, tip: '电源模块' },
  ],
}

export const SERVER_ANATOMY: Record<AnatomyForm, Record<AnatomyView, AnatomyRegion[]>> = {
  '2U': { top: TOP['2U'], front: FRONT['2U'], rear: REAR['2U'] },
  '4U': { top: TOP['4U'], front: FRONT['4U'], rear: REAR['4U'] },
}
