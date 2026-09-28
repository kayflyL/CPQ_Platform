/**
 * 家具占位尺寸 —— 渲染/编辑/寻路共用的单一数据源。（R3b 自 Office3DCanvas 抽出，逻辑逐行等价）
 * furnitureSize 的 catalog 由调用方从 OfficeConfig 取（模块自身不读配置，保持纯逻辑）。
 */
import type { OfficeFurnitureItem } from '@/api/office'

export const FALLBACK_FURNITURE_SIZE: Record<string, { width: number; depth: number }> = {
  desk: { width: 1.75, depth: 0.95 },
  office_chair: { width: 0.6, depth: 0.6 },
  meeting_table: { width: 4, depth: 1.2 },
  meeting_chair: { width: 0.6, depth: 0.6 },
  plant: { width: 0.68, depth: 0.68 },
  bookshelf: { width: 1.4, depth: 0.5 },
  coffee_bar: { width: 1.6, depth: 0.72 },
  lounge_sofa: { width: 2, depth: 0.9 },
  whiteboard: { width: 2.1, depth: 0.08 },
  art: { width: 0.95, depth: 0.06 },
  rug: { width: 2.4, depth: 1.8 },
  partition: { width: 0.98, depth: 0.08 },
  fridge: { width: 0.9, depth: 0.9 },
  coffee_table: { width: 0.84, depth: 0.84 },
  round_table: { width: 1.24, depth: 1.24 },
  stool: { width: 0.4, depth: 0.4 },
  reception_desk: { width: 2.2, depth: 0.9 },
  coat_rack: { width: 0.64, depth: 0.64 },
  tv: { width: 1.4, depth: 0.12 },
  file_cabinet: { width: 0.6, depth: 0.6 },
}

export const FURNITURE_MIN_SIZE: Record<string, number> = {
  art: 0.04,
  whiteboard: 0.04,
  tv: 0.04,
  partition: 0.04,
}

export const FURNITURE_MAX_SIZE = 12

export const SYMMETRIC_FURNITURE_TYPES = new Set([
  'plant',
  'coffee_table',
  'round_table',
  'stool',
  'coat_rack',
  'fridge',
  'file_cabinet',
])

export function furnitureMinSize(type: string): number {
  return FURNITURE_MIN_SIZE[type] ?? 0.2
}

export function clampFurnitureSize(v: number, type: string): number {
  const min = furnitureMinSize(type)
  return Math.min(FURNITURE_MAX_SIZE, Math.max(min, v))
}

type CatalogEntry = { type?: string; width?: number; depth?: number } | undefined

/** OfficeConfig.furniture_catalog 的宽容类型（模块不直接依赖 OfficeConfig）。 */
export type FurnitureCatalog = CatalogEntry[] | null | undefined

/** 家具尺寸的单一数据源：单件覆盖 -> 配置 catalog（后端下发）-> 前端回退表。 */
export function furnitureSize(catalog: CatalogEntry[] | null | undefined, type: string, item?: OfficeFurnitureItem): { width: number; depth: number } {
  let width: number | undefined
  let depth: number | undefined
  if (item) {
    if (typeof item.width === 'number') width = item.width
    if (typeof item.depth === 'number') depth = item.depth
  }
  if (Array.isArray(catalog)) {
    const def = catalog.find((c) => c?.type === type)
    if (def) {
      if (width === undefined && typeof def.width === 'number') width = def.width
      if (depth === undefined && typeof def.depth === 'number') depth = def.depth
    }
  }
  const fb = FALLBACK_FURNITURE_SIZE[type]
  if (fb) {
    if (width === undefined) width = fb.width
    if (depth === undefined) depth = fb.depth
  }
  return { width: clampFurnitureSize(width ?? 1, type), depth: clampFurnitureSize(depth ?? 1, type) }
}
