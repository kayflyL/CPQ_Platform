/**
 * 配件 ↔ 机箱适配（纯函数、数据驱动）—— 从 base_config 能力档案 + 配件 specs 判定适配关系。
 *
 * 设计原则（与 [[derive-must-have-manual-fallback]] 一致）：
 *   优先读结构化 specs（料号库声明的能力：bt / io_slot / kind / wattage / chassis），
 *   specs 缺失时回退型号名嗅探（excel 新件 / spec 未录全）。
 * 本模块只做「读取 + 规范化」，不内嵌任何魔法值——关键词/默认值都在 constants/chassisMeta.ts。
 */
import type { RearSlot } from '@/api/serverConfig'
import { BACKPLANE_TYPE_KEYWORDS } from '@/constants/chassisMeta'
import { normalizeDriveKind } from '@/stores/selectionEngine'

export type BackplaneType = 'tri' | 'dc'

/** 一个配件的可读 specs 输入（料号库件 / KP 件 / excel 行都按这个形状取） */
export interface SpecdPart {
  name?: string
  specs?: Record<string, any>
}

/**
 * 背板类型判定：
 *   1) specs.bt 是 'tri'/'dc' 直接采信（料号库声明）；
 *   2) 否则 specs.bt 可能是描述文本或缺失 → 按 BACKPLANE_TYPE_KEYWORDS 嗅探 name+bt；
 *   3) 都不命中返回 null（交消费端兜底，如 bpType 的 ?? 'dc'）。
 */
export function backplaneTypeOf(part: SpecdPart | null | undefined): BackplaneType | null {
  if (!part) return null
  const specs = part.specs || {}
  const btRaw = String(specs.bt ?? '').trim().toLowerCase()
  if (btRaw === 'tri' || btRaw === 'dc') return btRaw
  const text = `${part.name || ''} ${specs.bt || ''}`.toLowerCase()
  if (BACKPLANE_TYPE_KEYWORDS.tri.some(k => text.includes(k.toLowerCase()))) return 'tri'
  if (BACKPLANE_TYPE_KEYWORDS.dc.some(k => text.includes(k.toLowerCase()))) return 'dc'
  return null
}

/**
 * 盘类型：复用 selectionEngine.normalizeDriveKind——
 * specs.interface / kind / type 优先，缺失回退型号名嗅探。返回 SATA/SAS/NVMe 或 undefined。
 */
export function driveKindOf(part: SpecdPart): string | undefined {
  const s = part.specs || {}
  return normalizeDriveKind(s.interface || s.kind || s.type) || normalizeDriveKind(part.name)
}

/** 后面板槽位容量（从能力档案 rear_slots 查；未定义返 0，表示该槽不可用）*/
export function slotCapOf(rearSlots: RearSlot[] | undefined, slotName: string): number {
  return rearSlots?.find(s => s.name === slotName)?.cap ?? 0
}

// 注：specs.chassis「适用系列」声明曾由 配件适配页(PartFitMatrix) 可视化，但该声明未被
// 任何装配逻辑消费（L6/KP/推理均不过滤），页面已随 2026-08-03 移除；applicableSeries/fitsSeries 一并删除。
