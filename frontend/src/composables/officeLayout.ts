import type { OfficeConfig, OfficeFurnitureItem, OfficeZone } from '@/api/office'

export type RoomBounds = { minX: number; maxX: number; minZ: number; maxZ: number }

export function isRoomZone(zone: OfficeZone): boolean {
  return zone.room === true || zone.type === 'meeting' || zone.type === 'desk'
}

/** 房间 bounds：优先用 width/depth，其次按座位分布，最后回退 radius。 */
export function roomBounds(zone: OfficeZone): RoomBounds {
  const cx = zone.position?.x ?? 0
  const cz = zone.position?.z ?? 0
  if (zone.width && zone.depth) {
    return {
      minX: cx - zone.width / 2,
      maxX: cx + zone.width / 2,
      minZ: cz - zone.depth / 2,
      maxZ: cz + zone.depth / 2,
    }
  }
  const slots = zone.slots || []
  if (slots.length) {
    const xs = slots.map((s) => s.position?.x ?? cx)
    const zs = slots.map((s) => s.position?.z ?? cz)
    return {
      minX: Math.min(...xs) - 1.35,
      maxX: Math.max(...xs) + 1.35,
      minZ: Math.min(...zs) - 1.35,
      maxZ: Math.max(...zs) + 1.35,
    }
  }
  const r = Math.max(2.2, zone.radius || 3.2)
  return { minX: cx - r, maxX: cx + r, minZ: cz - r, maxZ: cz + r }
}

/** 判断一个世界坐标点落在哪个房间内；不在任何房间则返回 null。 */
export function zoneAt(config: OfficeConfig, x: number, z: number): OfficeZone | null {
  let best: OfficeZone | null = null
  let bestArea = Infinity
  for (const zone of config.zones || []) {
    if (!isRoomZone(zone)) continue
    const b = roomBounds(zone)
    if (x >= b.minX && x <= b.maxX && z >= b.minZ && z <= b.maxZ) {
      const area = (b.maxX - b.minX) * (b.maxZ - b.minZ)
      if (area < bestArea) {
        bestArea = area
        best = zone
      }
    }
  }
  return best
}

export function zoneFurniture(furniture: OfficeFurnitureItem[], zoneId: string): OfficeFurnitureItem[] {
  return (furniture || []).filter((f) => f.zoneId === zoneId)
}

export function zoneSeats(furniture: OfficeFurnitureItem[], zoneId: string): OfficeFurnitureItem[] {
  return (furniture || []).filter((f) => f.zoneId === zoneId && f.seat)
}

function seatTypeForZone(zone: OfficeZone): string {
  if (zone.type === 'desk') return 'desk'
  if (zone.type === 'meeting') return 'meeting_chair'
  return 'chair'
}

/**
 * 把旧模型（zone.slots 里存座位绝对坐标）归一化成新模型：
 * 每个 slot 变成一个独立 furniture（带 zoneId/role_key/seat），并清空 zone.slots。
 * 若会议房间有座位但没有 meeting_table 家具，则在房间中心补一张会议长桌。
 * 幂等：重复调用不会产生重复家具。
 */
export function normalizeOfficeConfig(cfg: OfficeConfig): OfficeConfig {
  const zones = cfg.zones ?? (cfg.zones = [])
  const furniture = cfg.furniture ?? (cfg.furniture = [])
  for (const zone of zones) {
    const slots = zone.slots || []
    for (const slot of slots) {
      const existing = furniture.find((f) => f.id === slot.id && f.zoneId === zone.id)
      if (existing) {
        if (slot.role_key && !existing.role_key) existing.role_key = slot.role_key
        existing.seat = true
        existing.zoneId = zone.id
        continue
      }
      furniture.push({
        id: slot.id,
        type: seatTypeForZone(zone),
        position: { x: slot.position?.x ?? zone.position?.x ?? 0, z: slot.position?.z ?? zone.position?.z ?? 0 },
        rotation_y: slot.rotation_y ?? 0,
        zoneId: zone.id,
        role_key: slot.role_key ?? null,
        seat: true,
      })
    }
    zone.slots = []
  }
  // 对缺少 width/depth/position 但已有座位的房间，用座位分布补全 bounds 与中心（避免归一化后房间塌陷为半径）。
  for (const zone of zones) {
    const seats = zoneSeats(furniture, zone.id)
    if (!seats.length) continue
    const xs = seats.map((s) => s.position.x)
    const zs = seats.map((s) => s.position.z)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minZ = Math.min(...zs)
    const maxZ = Math.max(...zs)
    if (!zone.position) {
      zone.position = { x: (minX + maxX) / 2, z: (minZ + maxZ) / 2 }
    }
    if (!zone.width || !zone.depth) {
      zone.width = Math.max(zone.width || 0, maxX - minX + 2.0)
      zone.depth = Math.max(zone.depth || 0, maxZ - minZ + 2.0)
    }
  }
  for (const zone of zones) {
    if (zone.type !== 'meeting') continue
    if (!zoneSeats(furniture, zone.id).length) continue
    const hasTable = furniture.some((f) => f.zoneId === zone.id && f.type === 'meeting_table')
    if (!hasTable) {
      const center = zone.position || { x: 0, z: 0 }
      furniture.push({
        id: `table-${zone.id}`,
        type: 'meeting_table',
        position: { ...center },
        rotation_y: 0,
        zoneId: zone.id,
        seat: false,
      })
    }
    const center = zone.position || { x: 0, z: 0 }
    for (const seat of zoneSeats(furniture, zone.id)) {
      if (seat.type === 'meeting_chair') {
        seat.rotation_y = Math.atan2(center.x - seat.position.x, center.z - seat.position.z)
      }
    }
  }
  return cfg
}
