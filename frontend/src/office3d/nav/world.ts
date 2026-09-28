/**
 * 导航世界：障碍网格 + 会议房间几何。（R1 自 Office3DCanvas 抽出，逻辑逐行等价）
 * 组件状态通过 NavSource 注入，模块自身零 Vue 依赖；
 * 布局/家具变化调用 invalidate() 后，blockedAt 查表 O(1)。
 */
import * as THREE from 'three'
import type { OfficeFurnitureItem, OfficeZone } from '@/api/office'
// node --test 下无 vite 别名，运行时导入走相对路径（officeLayout 自身仅 type 导入，运行时链路到此为止）。
import { zoneSeats } from '../../composables/officeLayout.ts'

/** 寻路网格步长（米）。 */
export const NAV_STEP = 0.25

export type NavBounds = { minX: number; maxX: number; minZ: number; maxZ: number }
export type MeetingBounds = NavBounds
export type MeetingDoorSide = 'front' | 'back' | 'left' | 'right'

/** 参与寻路阻挡的家具类型（尺寸一律从 furnitureSize 读取，避免与渲染/编辑 catalog 脱节）。 */
const BLOCKING_FURNITURE_TYPES = new Set([
  'desk',
  'meeting_table',
  'lounge_sofa',
  'coffee_bar',
  'fridge',
  'file_cabinet',
  'round_table',
  'coffee_table',
  'reception_desk',
  'bookshelf',
  'partition',
  'coat_rack',
])

export interface NavSource {
  floor(): { width: number; depth: number }
  zones(): OfficeZone[]
  furniture(): OfficeFurnitureItem[]
  furnitureSize(type: string, item?: OfficeFurnitureItem): { width: number; depth: number }
  debug?(): boolean
}

export interface AstarBuffers {
  g: Float64Array
  f: Float64Array
  parent: Int32Array
  inOpen: Uint8Array
  closed: Uint8Array
  heapIndex: Int32Array
}

export interface NavWorld {
  /** 布局/家具变化后调用，下一次 blockedAt 触发网格重建。 */
  invalidate(): void
  floor(): { width: number; depth: number }
  floorBounds(): NavBounds
  clampPointToFloor(v: THREE.Vector3): THREE.Vector3
  cellBlocked(x: number, z: number): boolean
  blockedAt(x: number, z: number): boolean
  meetingWallBlocked(x: number, z: number): boolean
  meetingRoomBounds(zone: OfficeZone): MeetingBounds
  meetingDoorSide(zone: OfficeZone): MeetingDoorSide
  meetingDoorWaypoints(zone: OfficeZone): THREE.Vector3[]
  /** A* 复用缓冲区（path.ts 内部接口，按网格尺寸只分配一次）。 */
  astarBuffers(n: number): AstarBuffers
  /** 调试探针：path.ts/world 累加，调试读数读取后归零。 */
  stats: { blocked: number; astar: number }
  debugEnabled(): boolean
}

export function createNavWorld(source: NavSource): NavWorld {
  let obstacleGrid: Uint8Array | null = null
  let obstacleGridCols = 0
  let obstacleGridRows = 0
  let obstacleGridMinX = 0
  let obstacleGridMinZ = 0
  let obstacleGridStep = NAV_STEP
  let obstacleDirty = true
  let buffers: AstarBuffers | null = null
  const stats = { blocked: 0, astar: 0 }

  function meetingRoomBounds(zone: OfficeZone): MeetingBounds {
    const centerX = zone.position?.x ?? 0
    const centerZ = zone.position?.z ?? 0
    if (zone.width && zone.depth) {
      return {
        minX: centerX - zone.width / 2,
        maxX: centerX + zone.width / 2,
        minZ: centerZ - zone.depth / 2,
        maxZ: centerZ + zone.depth / 2,
      }
    }
    const seats = zoneSeats(source.furniture(), zone.id)
    if (seats.length) {
      const xs = seats.map((slot) => slot.position?.x ?? centerX)
      const zs = seats.map((slot) => slot.position?.z ?? centerZ)
      return {
        minX: Math.min(...xs) - 1.35,
        maxX: Math.max(...xs) + 1.35,
        minZ: Math.min(...zs) - 1.35,
        maxZ: Math.max(...zs) + 1.35,
      }
    }
    const radius = Math.max(2.2, zone.radius || 3.2)
    return {
      minX: centerX - radius,
      maxX: centerX + radius,
      minZ: centerZ - radius,
      maxZ: centerZ + radius,
    }
  }

  function meetingDoorSide(zone: OfficeZone): MeetingDoorSide {
    const floor = source.floor()
    const configuredSide = zone.door?.side
    if (configuredSide === 'left' || configuredSide === 'right' || configuredSide === 'front' || configuredSide === 'back') {
      return configuredSide
    }
    const centerX = zone.position?.x ?? 0
    const centerZ = zone.position?.z ?? 0
    const halfWidth = floor.width / 2
    const halfDepth = floor.depth / 2
    const outsideX = Math.abs(centerX) > halfWidth
    const outsideZ = Math.abs(centerZ) > halfDepth
    if (!outsideX && !outsideZ) return 'left'
    if (Math.abs(centerX) - halfWidth >= Math.abs(centerZ) - halfDepth) {
      return centerX > 0 ? 'left' : 'right'
    }
    return centerZ > 0 ? 'back' : 'front'
  }

  function meetingWallBlocked(x: number, z: number): boolean {
    const clearance = 0.22
    for (const zone of source.zones()) {
      if (zone.type !== 'meeting') continue
      const b = meetingRoomBounds(zone)
      const side = meetingDoorSide(zone)
      const doorWidth = zone.door?.width ?? 1.3
      const doorOffset = zone.door?.offset ?? 0
      const cx = (zone.position?.x ?? 0) + doorOffset
      const cz = (zone.position?.z ?? 0) + doorOffset
      if (side === 'front' || side === 'back') {
        const wallZ = side === 'front' ? b.maxZ : b.minZ
        if (Math.abs(z - wallZ) < clearance && x >= b.minX - clearance && x <= b.maxX + clearance) {
          if (Math.abs(x - cx) >= doorWidth / 2) return true
        }
      } else {
        const wallX = side === 'left' ? b.minX : b.maxX
        if (Math.abs(x - wallX) < clearance && z >= b.minZ - clearance && z <= b.maxZ + clearance) {
          if (Math.abs(z - cz) >= doorWidth / 2) return true
        }
      }
    }
    return false
  }

  /** 逐格判断是否阻挡（保留原逻辑，用于一次性重建网格）。 */
  function cellBlocked(x: number, z: number): boolean {
    const clearance = 0.18
    if (meetingWallBlocked(x, z)) return true
    const furniture = source.furniture()
    for (const item of furniture) {
      if (!BLOCKING_FURNITURE_TYPES.has(item.type)) continue
      const size = source.furnitureSize(item.type, item)
      const halfW = size.width / 2
      const halfD = size.depth / 2
      const rot = item.rotation_y ?? 0
      const cos = Math.cos(rot)
      const sin = Math.sin(rot)
      const hx = Math.abs(halfW * cos) + Math.abs(halfD * sin)
      const hz = Math.abs(halfW * sin) + Math.abs(halfD * cos)
      const dx = x - (item.position?.x ?? 0)
      const dz = z - (item.position?.z ?? 0)
      if (Math.abs(dx) < hx + clearance && Math.abs(dz) < hz + clearance) return true
    }
    return false
  }

  function floorBounds(): NavBounds {
    const floor = source.floor()
    return {
      minX: -floor.width / 2,
      maxX: floor.width / 2,
      minZ: -floor.depth / 2,
      maxZ: floor.depth / 2,
    }
  }

  function rebuildObstacleGrid() {
    obstacleDirty = false
    const b = floorBounds()
    const step = NAV_STEP
    const cols = Math.max(1, Math.ceil((b.maxX - b.minX) / step))
    const rows = Math.max(1, Math.ceil((b.maxZ - b.minZ) / step))
    const grid = new Uint8Array(cols * rows)
    for (let iz = 0; iz < rows; iz++) {
      for (let ix = 0; ix < cols; ix++) {
        const x = b.minX + (ix + 0.5) * step
        const z = b.minZ + (iz + 0.5) * step
        if (cellBlocked(x, z)) grid[iz * cols + ix] = 1
      }
    }
    obstacleGrid = grid
    obstacleGridCols = cols
    obstacleGridRows = rows
    obstacleGridMinX = b.minX
    obstacleGridMinZ = b.minZ
    obstacleGridStep = step
  }

  function astarBuffers(n: number): AstarBuffers {
    if (!buffers || buffers.g.length !== n) {
      buffers = {
        g: new Float64Array(n),
        f: new Float64Array(n),
        parent: new Int32Array(n),
        inOpen: new Uint8Array(n),
        closed: new Uint8Array(n),
        heapIndex: new Int32Array(n),
      }
    }
    return buffers
  }

  return {
    invalidate() {
      obstacleDirty = true
    },
    floor: () => source.floor(),
    floorBounds,
    clampPointToFloor(point: THREE.Vector3): THREE.Vector3 {
      const floor = source.floor()
      const margin = 0.42
      const halfWidth = Math.max(0.1, floor.width / 2 - margin)
      const halfDepth = Math.max(0.1, floor.depth / 2 - margin)
      return new THREE.Vector3(
        Math.max(-halfWidth, Math.min(halfWidth, point.x)),
        0,
        Math.max(-halfDepth, Math.min(halfDepth, point.z)),
      )
    },
    cellBlocked,
    blockedAt(x: number, z: number): boolean {
      if (source.debug?.()) stats.blocked += 1
      if (obstacleDirty) rebuildObstacleGrid()
      if (!obstacleGrid) return cellBlocked(x, z)
      const step = obstacleGridStep
      let ix = Math.round((x - obstacleGridMinX) / step - 0.5)
      let iz = Math.round((z - obstacleGridMinZ) / step - 0.5)
      ix = Math.max(0, Math.min(obstacleGridCols - 1, ix))
      iz = Math.max(0, Math.min(obstacleGridRows - 1, iz))
      return obstacleGrid[iz * obstacleGridCols + ix] === 1
    },
    meetingWallBlocked,
    meetingRoomBounds,
    meetingDoorSide,
    meetingDoorWaypoints(zone: OfficeZone): THREE.Vector3[] {
      const bounds = meetingRoomBounds(zone)
      const side = meetingDoorSide(zone)
      const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
      const doorOffset = zone.door?.offset ?? 0
      const standoff = 0.85

      if (side === 'front') {
        return [
          new THREE.Vector3(center.x + doorOffset, 0, bounds.maxZ + standoff),
          new THREE.Vector3(center.x + doorOffset, 0, bounds.maxZ - standoff),
        ]
      }
      if (side === 'back') {
        return [
          new THREE.Vector3(center.x + doorOffset, 0, bounds.minZ - standoff),
          new THREE.Vector3(center.x + doorOffset, 0, bounds.minZ + standoff),
        ]
      }
      if (side === 'left') {
        return [
          new THREE.Vector3(bounds.minX - standoff, 0, center.z + doorOffset),
          new THREE.Vector3(bounds.minX + standoff, 0, center.z + doorOffset),
        ]
      }
      return [
        new THREE.Vector3(bounds.maxX + standoff, 0, center.z + doorOffset),
        new THREE.Vector3(bounds.maxX - standoff, 0, center.z + doorOffset),
      ]
    },
    astarBuffers,
    stats,
    debugEnabled: () => !!source.debug?.(),
  }
}
