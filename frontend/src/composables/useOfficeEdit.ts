import { computed, ref, shallowRef } from 'vue'
import * as THREE from 'three'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import type {
  FurnitureDefinition,
  OfficeConfig,
  OfficeFurnitureItem,
  OfficeZone,
} from '@/api/office'
import { normalizeOfficeConfig, zoneAt, zoneFurniture } from '@/composables/officeLayout'

const DEFAULT_CATALOG: FurnitureDefinition[] = [
  { type: 'desk', label: '办公桌', category: 'desk', width: 1.75, depth: 0.95, height: 1.45, rotatable: true },
  { type: 'office_chair', label: '办公椅', category: 'chair', width: 0.6, depth: 0.62, height: 1.1, rotatable: true },
  { type: 'meeting_table', label: '会议长桌', category: 'meeting', width: 4, depth: 1.2, height: 0.72, rotatable: true },
  { type: 'meeting_chair', label: '会议椅', category: 'chair', width: 0.55, depth: 0.55, height: 0.95, rotatable: true },
  { type: 'plant', label: '绿植', category: 'plant', width: 0.55, depth: 0.55, height: 1.4, rotatable: false },
  { type: 'bookshelf', label: '书架', category: 'storage', width: 1.4, depth: 0.5, height: 2.1, rotatable: true },
  { type: 'coffee_bar', label: '茶水吧台', category: 'storage', width: 1.6, depth: 0.72, height: 1.3, rotatable: true },
  { type: 'lounge_sofa', label: '休息沙发', category: 'lounge', width: 2, depth: 0.9, height: 0.9, rotatable: true },
  { type: 'whiteboard', label: '白板', category: 'meeting', width: 2.1, depth: 0.08, height: 1.25, rotatable: true },
  { type: 'art', label: '装饰画', category: 'decor', width: 0.95, depth: 0.06, height: 0.7, rotatable: true },
  { type: 'rug', label: '地毯', category: 'decor', width: 2.4, depth: 1.8, height: 0.02, rotatable: true },
  { type: 'partition', label: '工位隔断', category: 'desk', width: 0.9, depth: 0.12, height: 1.4, rotatable: true },
  { type: 'fridge', label: '冰箱', category: 'storage', width: 0.9, depth: 0.9, height: 1.9, rotatable: true },
  { type: 'coffee_table', label: '茶几', category: 'lounge', width: 0.8, depth: 0.8, height: 0.45, rotatable: true },
  { type: 'round_table', label: '圆桌', category: 'lounge', width: 1.1, depth: 1.1, height: 0.75, rotatable: true },
  { type: 'stool', label: '高脚凳', category: 'chair', width: 0.4, depth: 0.4, height: 0.7, rotatable: true },
  { type: 'reception_desk', label: '前台', category: 'furniture', width: 2.2, depth: 0.9, height: 1.1, rotatable: true },
  { type: 'coat_rack', label: '衣帽架', category: 'decor', width: 0.5, depth: 0.5, height: 1.8, rotatable: true },
  { type: 'tv', label: '电视', category: 'decor', width: 1.4, depth: 0.12, height: 0.9, rotatable: true },
  { type: 'file_cabinet', label: '文件柜', category: 'storage', width: 0.6, depth: 0.6, height: 1.1, rotatable: true },
]

const GRID_STEP = 0.25
const PLAN_Y = 0.05
/** 距离墙面多近才触发“磁吸靠墙”（米）。 */
const WALL_SNAP_TOLERANCE = 0.35
/** 吸墙时家具边缘与墙之间保留的缝隙（米）。 */
const WALL_GAP = 0.03

export interface OfficeEditOptions {
  container: () => HTMLElement | null
  scene: () => THREE.Scene | null
  domElement: () => HTMLElement | null
  config: () => OfficeConfig
  environment: () => THREE.Group | null
  rebuildEnvironment?: () => void
  onChanged?: (config: OfficeConfig) => void
}

interface EditSel {
  kind: 'furniture' | 'room'
  item?: OfficeFurnitureItem
  zone?: OfficeZone
  mesh?: THREE.Object3D
  id: string
}

type DragState =
  | { type: 'pan'; sx: number; sy: number; cx: number; cz: number }
  | { type: 'body'; kind: 'furniture'; mesh: THREE.Object3D; id: string; startWorld: { x: number; z: number }; meshStart: { x: number; z: number } }
  | { type: 'room'; zone: OfficeZone; mesh: THREE.Object3D; startX: number; startZ: number; startCenterX: number; startCenterZ: number }
  | { type: 'roomHandle'; zone: OfficeZone; handle: RoomHandle; mesh: THREE.Object3D; startWorld: THREE.Vector3; start: RoomBounds }

type RoomHandle = 'center' | 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w'

interface RoomBounds {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

export function useOfficeEdit(opts: OfficeEditOptions) {
  const editing = ref(false)
  const editCamera = shallowRef<THREE.OrthographicCamera | null>(null)
  const selected = shallowRef<EditSel | null>(null)
  const armedType = ref<string | null>(null)
  const armedRoom = ref(false)
  const rotateMode = ref(false)
  const panMode = ref(false)
  const zoomPct = ref(100)
  const hover = ref(false)

  const catalog = computed<FurnitureDefinition[]>(() => {
    const c = opts.config().furniture_catalog
    if (Array.isArray(c) && c.length) return c
    return DEFAULT_CATALOG
  })

  let planGroup: THREE.Group | null = null
  let groundPlane: THREE.Mesh | null = null
  let tc: TransformControls | null = null
  let ghostMesh: THREE.Mesh | null = null
  let downPt = { x: 0, y: 0 }
  let dragState: DragState | null = null
  let pointerActive = false
  let dragButton = 0
  let view = { cx: 0, cz: 0 }

  const raycaster = new THREE.Raycaster()
  const pointerV = new THREE.Vector2()
  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])
  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)
  let enterSnapshot: string | null = null
  const furnitureMeshes = new Map<string, THREE.Object3D>()
  const roomMeshes = new Map<string, THREE.Object3D>()
  const roomHandleMeshes: THREE.Object3D[] = []

  function snapConfig(): string {
    return JSON.stringify(opts.config())
  }

  function applySnapshot(json: string) {
    const cfg = opts.config()
    const next = JSON.parse(json) as Record<string, unknown>
    for (const k of Object.keys(cfg)) delete (cfg as any)[k]
    Object.assign(cfg, next)
    selected.value = null
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
    attachTransform()
  }

  function pushHistory() {
    undoStack.value.push(snapConfig())
    if (undoStack.value.length > 100) undoStack.value.shift()
    redoStack.value.length = 0
  }

  function undo() {
    if (!undoStack.value.length) return
    redoStack.value.push(snapConfig())
    const s = undoStack.value.pop()
    if (s) applySnapshot(s)
  }

  function redo() {
    if (!redoStack.value.length) return
    undoStack.value.push(snapConfig())
    const s = redoStack.value.pop()
    if (s) applySnapshot(s)
  }

  function cancelEdit() {
    if (enterSnapshot) applySnapshot(enterSnapshot)
    exit()
  }

  function workspace(): { width: number; depth: number } {
    const cfg = opts.config()
    const floorW = cfg.floor?.width ?? 24
    const floorD = cfg.floor?.depth ?? 16
    return {
      width: cfg.workspace?.width ?? Math.max(floorW, 24),
      depth: cfg.workspace?.depth ?? Math.max(floorD, 16),
    }
  }

  function snap(v: number) {
    return Math.round(v / GRID_STEP) * GRID_STEP
  }

  function isRoom(zone: OfficeZone): boolean {
    return zone.room === true || zone.type === 'meeting'
  }

  function roomBounds(zone: OfficeZone): RoomBounds {
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

  /** 取家具实际尺寸（优先 item 覆盖，回退 catalog）。 */
  function furnitureSizeOf(item: OfficeFurnitureItem): { width: number; depth: number } {
    let width = item.width
    let depth = item.depth
    const def = catalogDef(item.type)
    if (width == null) width = def.width
    if (depth == null) depth = def.depth
    return { width: width || 1, depth: depth || 1 }
  }

  /** 把旋转角归一化到最近的 90° 倍数（弧度，范围 [0, 2π)）。 */
  function normalizeRotation(rot: number): number {
    const step = Math.PI / 2
    const twoPi = Math.PI * 2
    let a = rot % twoPi
    if (a < 0) a += twoPi
    const snapped = Math.round(a / step) * step
    return snapped >= twoPi ? snapped - twoPi : snapped
  }

  /**
   * 摆放约束：家具中心候选 (x,z) + 当前旋转 rot。
   * - 若家具可旋转，则把旋转归一化到最近的 90°。
   * - 若某家具边缘进入某个房间墙的吸附阈值，则贴墙（留 WALL_GAP），并让“正面”朝向房间内侧。
   * - 否则仅按 GRID_STEP 网格吸附。
   */
  function constrainFurniture(item: OfficeFurnitureItem, x: number, z: number, rot: number): { x: number; z: number; rotationY: number } {
    const def = catalogDef(item.type)
    const rotatable = def.rotatable !== false
    const rotationY = rotatable ? normalizeRotation(rot) : (item.rotation_y ?? 0)
    const s = furnitureSizeOf(item)
    const zones = opts.config().zones || []
    let best: { nx: number; nz: number; rotationY: number; dist: number } | null = null

    for (const zone of zones) {
      if (!isRoom(zone)) continue
      const b = roomBounds(zone)
      for (const wall of ['minZ', 'maxZ', 'minX', 'maxX'] as const) {
        const targetRot = wall === 'minZ' ? 0 : wall === 'maxZ' ? Math.PI : wall === 'minX' ? Math.PI / 2 : (3 * Math.PI) / 2
        if (!rotatable) continue
        const quarter = Math.round(targetRot / (Math.PI / 2)) % 4
        const swapped = quarter % 2 === 1
        const halfX = (swapped ? s.depth : s.width) / 2
        const halfZ = (swapped ? s.width : s.depth) / 2
        const margin = 0.03

        if (wall === 'minZ' || wall === 'maxZ') {
          // 物品沿 X 方向不得超出墙段跨度
          if (x - halfX < b.minX - margin || x + halfX > b.maxX + margin) continue
          const perp = halfZ
          const wallCoord = wall === 'minZ' ? b.minZ : b.maxZ
          const edge = wall === 'minZ' ? z - perp : z + perp
          const d = wall === 'minZ' ? edge - wallCoord : wallCoord - edge
          if (d < -0.05 || d > WALL_SNAP_TOLERANCE) continue
          const nx = Math.min(Math.max(x, b.minX + halfX), b.maxX - halfX)
          const nz = wall === 'minZ' ? b.minZ + WALL_GAP + perp : b.maxZ - WALL_GAP - perp
          const dist = Math.hypot(nx - x, nz - z)
          if (!best || dist < best.dist) best = { nx, nz, rotationY: targetRot, dist }
        } else {
          if (z - halfZ < b.minZ - margin || z + halfZ > b.maxZ + margin) continue
          const perp = halfX
          const wallCoord = wall === 'minX' ? b.minX : b.maxX
          const edge = wall === 'minX' ? x - perp : x + perp
          const d = wall === 'minX' ? edge - wallCoord : wallCoord - edge
          if (d < -0.05 || d > WALL_SNAP_TOLERANCE) continue
          const nz = Math.min(Math.max(z, b.minZ + halfZ), b.maxZ - halfZ)
          const nx = wall === 'minX' ? b.minX + WALL_GAP + perp : b.maxX - WALL_GAP - perp
          const dist = Math.hypot(nx - x, nz - z)
          if (!best || dist < best.dist) best = { nx, nz, rotationY: targetRot, dist }
        }
      }
    }

    if (best) {
      return { x: best.nx, z: best.nz, rotationY: best.rotationY }
    }
    return { x: snap(x), z: snap(z), rotationY }
  }

  function catalogDef(type: string): FurnitureDefinition {
    return catalog.value.find((c) => c.type === type) || { type, label: type, category: 'furniture', width: 1, depth: 1 }
  }

  function ensureCamera(w: number, h: number) {
    if (!editCamera.value) {
      editCamera.value = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200)
    }
    const ws = workspace()
    const aspect = w && h ? w / h : 1
    const scale = Math.max(0.2, zoomPct.value / 100)
    let halfW = (ws.width / 2 + 1.5) / scale
    let halfH = halfW / aspect
    const halfD = (ws.depth / 2 + 1.5) / scale
    if (halfH < halfD) {
      halfH = halfD
      halfW = halfH * aspect
    }
    const cam = editCamera.value
    cam.left = -halfW
    cam.right = halfW
    cam.top = halfH
    cam.bottom = -halfH
    cam.updateProjectionMatrix()
    cam.position.set(view.cx, 40, view.cz)
    cam.up.set(0, 0, -1)
    cam.lookAt(view.cx, 0, view.cz)
  }

  function fitView() {
    view.cx = 0
    view.cz = 0
    zoomPct.value = 100
    const el = opts.container()
    if (el) ensureCamera(el.clientWidth || 1, el.clientHeight || 1)
  }

  function screenToWorld(clientX: number, clientY: number): THREE.Vector3 | null {
    const el = opts.domElement()
    const cam = editCamera.value
    if (!el || !cam || !groundPlane) return null
    const rect = el.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    pointerV.x = ((clientX - rect.left) / rect.width) * 2 - 1
    pointerV.y = -((clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointerV, cam)
    const hits = raycaster.intersectObject(groundPlane, false)
    return hits.length ? hits[0].point : null
  }

  function zoomAt(clientX: number, clientY: number, factor: number) {
    const before = screenToWorld(clientX, clientY)
    const next = Math.min(600, Math.max(25, zoomPct.value * factor))
    zoomPct.value = next
    const el = opts.container()
    if (el) ensureCamera(el.clientWidth || 1, el.clientHeight || 1)
    const after = screenToWorld(clientX, clientY)
    if (before && after) {
      view.cx += before.x - after.x
      view.cz += before.z - after.z
      if (el) ensureCamera(el.clientWidth || 1, el.clientHeight || 1)
    }
  }

  function planMaterial(color: string, opacity = 1): THREE.MeshBasicMaterial {
    const m = new THREE.MeshBasicMaterial({ color: new THREE.Color(color) })
    if (opacity < 1) m.transparent = true
    m.opacity = opacity
    return m
  }

  function disposeGroup(group: THREE.Group) {
    group.traverse((obj) => {
      const mesh = obj as THREE.Mesh
      if (mesh.geometry) mesh.geometry.dispose()
      const mat = (mesh as any).material
      if (Array.isArray(mat)) mat.forEach((m: THREE.Material) => m.dispose())
      else if (mat) mat.dispose()
    })
  }

  function addEditGrid() {
    if (!planGroup) return
    const ws = workspace()
    const color = '#3a4964'
    const pts: number[] = []
    for (let x = -ws.width / 2; x <= ws.width / 2 + 0.001; x += GRID_STEP) {
      pts.push(x, PLAN_Y, -ws.depth / 2, x, PLAN_Y, ws.depth / 2)
    }
    for (let z = -ws.depth / 2; z <= ws.depth / 2 + 0.001; z += GRID_STEP) {
      pts.push(-ws.width / 2, PLAN_Y, z, ws.width / 2, PLAN_Y, z)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    const lines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: color, transparent: true, opacity: 0.5 }))
    lines.name = 'office-edit-grid'
    planGroup.add(lines)
  }

  function rectMesh(w: number, d: number, color: string, opacity = 1, y = PLAN_Y): THREE.Mesh {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, 0.06, d), planMaterial(color, opacity))
    mesh.position.y = y
    return mesh
  }

  function syncFurnitureZone(item: OfficeFurnitureItem) {
    const cfg = opts.config()
    const z = zoneAt(cfg, item.position.x, item.position.z)
    item.zoneId = z ? z.id : null
  }

  function syncZoneAssignments(cfg: OfficeConfig) {
    for (const f of cfg.furniture || []) {
      const z = zoneAt(cfg, f.position.x, f.position.z)
      f.zoneId = z ? z.id : null
    }
  }

  function moveZone(zone: OfficeZone, nx: number, nz: number) {
    const oldX = zone.position?.x ?? 0
    const oldZ = zone.position?.z ?? 0
    const dx = nx - oldX
    const dz = nz - oldZ
    if (!zone.position) zone.position = { x: nx, z: nz }
    else {
      zone.position.x = nx
      zone.position.z = nz
    }
    if (dx !== 0 || dz !== 0) {
      const cfg = opts.config()
      for (const f of zoneFurniture(cfg.furniture || [], zone.id)) {
        f.position.x += dx
        f.position.z += dz
        const mesh = furnitureMeshes.get(f.id)
        if (mesh) {
          mesh.position.x = f.position.x
          mesh.position.z = f.position.z
        }
      }
      const rg = roomMeshes.get(zone.id)
      if (rg) {
        rg.position.x += dx
        rg.position.z += dz
      }
    }
  }

  function buildGhost() {
    if (!planGroup || (!armedType.value && !armedRoom.value)) {
      if (ghostMesh) {
        planGroup?.remove(ghostMesh)
        ghostMesh.geometry.dispose()
        const mat = (ghostMesh as any).material
        if (mat) mat.dispose()
        ghostMesh = null
      }
      return
    }
    const gw = armedType.value ? catalogDef(armedType.value).width : 4
    const gd = armedType.value ? catalogDef(armedType.value).depth : 3
    if (armedRoom.value) {
      if (!ghostMesh) {
        ghostMesh = rectMesh(gw, gd, '#39d98a', 0.3, PLAN_Y + 0.06)
        planGroup.add(ghostMesh)
      } else {
        ghostMesh.geometry.dispose()
        ghostMesh.geometry = new THREE.BoxGeometry(gw, 0.06, gd)
      }
    } else {
      if (!ghostMesh) {
        ghostMesh = rectMesh(gw, gd, '#39d98a', 0.45, PLAN_Y + 0.08)
        planGroup.add(ghostMesh)
      } else {
        ghostMesh.geometry.dispose()
        ghostMesh.geometry = new THREE.BoxGeometry(gw, 0.06, gd)
      }
    }
  }

  function setGhostFromEvent(ev: PointerEvent) {
    if (!ghostMesh || (!armedType.value && !armedRoom.value)) return
    const pt = screenToWorld(ev.clientX, ev.clientY)
    if (!pt) return
    const x = snap(pt.x)
    const z = snap(pt.z)
    const y = armedRoom.value ? PLAN_Y + 0.06 : PLAN_Y + 0.08
    ghostMesh.position.set(x, y, z)
    if (armedType.value) {
      const inside = roomAtPoint(x, z)
      ;(ghostMesh.material as THREE.MeshBasicMaterial).color.set(inside ? '#39d98a' : '#e5484d')
    } else {
      ;(ghostMesh.material as THREE.MeshBasicMaterial).color.set('#39d98a')
    }
  }

  function buildSelection() {
    if (!planGroup) return
    for (const h of roomHandleMeshes) {
      planGroup.remove(h)
      const mesh = h as THREE.Mesh
      mesh.geometry.dispose()
      const mat = (mesh as any).material
      if (mat) mat.dispose()
    }
    roomHandleMeshes.length = 0
    const sel = selected.value
    if (!sel) return
    if (sel.kind === 'room' && sel.zone) {
      const b = roomBounds(sel.zone)
      const cx = (b.minX + b.maxX) / 2
      const cz = (b.minZ + b.maxZ) / 2
      const hl = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(b.maxX - b.minX + 0.3, 0.02, b.maxZ - b.minZ + 0.3)),
        new THREE.LineBasicMaterial({ color: '#39d98a' }),
      )
      hl.position.set(cx, PLAN_Y + 0.06, cz)
      planGroup.add(hl)
      roomHandleMeshes.push(hl)
      addRoomHandle('center', cx, cz, '#39d98a')
      addRoomHandle('nw', b.minX, b.minZ, '#f5c542')
      addRoomHandle('ne', b.maxX, b.minZ, '#f5c542')
      addRoomHandle('sw', b.minX, b.maxZ, '#f5c542')
      addRoomHandle('se', b.maxX, b.maxZ, '#f5c542')
      addRoomHandle('n', cx, b.minZ, '#f5c542')
      addRoomHandle('s', cx, b.maxZ, '#f5c542')
      addRoomHandle('w', b.minX, cz, '#f5c542')
      addRoomHandle('e', b.maxX, cz, '#f5c542')
    } else if (sel.mesh) {
      const bbox = new THREE.Box3().setFromObject(sel.mesh)
      const size = bbox.getSize(new THREE.Vector3())
      const ring = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(size.x + 0.3, 0.05, size.z + 0.3)),
        new THREE.LineBasicMaterial({ color: '#39d98a' }),
      )
      ring.position.copy((sel.mesh as THREE.Mesh).position)
      planGroup.add(ring)
      roomHandleMeshes.push(ring)
    }
  }

  function addRoomHandle(handle: RoomHandle, x: number, z: number, color: string) {
    if (!planGroup) return
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.05, 0.35), planMaterial(color, 0.95))
    mesh.position.set(x, PLAN_Y + 0.1, z)
    mesh.userData.edit = { kind: 'roomHandle', zone: selected.value?.zone, handle, id: handle }
    planGroup.add(mesh)
    roomHandleMeshes.push(mesh)
  }

  function roomAtPoint(x: number, z: number): boolean {
    const zones = opts.config().zones || []
    return zones.some((zone) => {
      if (!isRoom(zone)) return false
      const b = roomBounds(zone)
      return x >= b.minX && x <= b.maxX && z >= b.minZ && z <= b.maxZ
    })
  }

  function refreshEnvironmentMeshes() {
    furnitureMeshes.clear()
    roomMeshes.clear()
    const env = opts.environment()
    if (!env) return
    env.traverse((obj) => {
      const edit = (obj as any).userData?.edit
      if (!edit) return
      if (edit.kind === 'furniture') furnitureMeshes.set(edit.id, obj as THREE.Object3D)
      else if (edit.kind === 'room') roomMeshes.set(edit.id, obj as THREE.Object3D)
    })
  }

  function rebuildEnvironment() {
    opts.rebuildEnvironment?.()
  }

  function rebuildPlan() {
    const sc = opts.scene()
    if (!sc) return
    if (planGroup) {
      sc.remove(planGroup)
      disposeGroup(planGroup)
    }
    planGroup = new THREE.Group()
    planGroup.name = 'office-edit-plan'
    sc.add(planGroup)
    furnitureMeshes.clear()
    roomMeshes.clear()
    roomHandleMeshes.length = 0
    addEditGrid()
    refreshEnvironmentMeshes()
    buildGhost()
    buildSelection()
    const el = opts.container()
    if (el) ensureCamera(el.clientWidth || 1, el.clientHeight || 1)
    if (selected.value) {
      const m = findCurrentMesh(selected.value)
      if (m) selected.value.mesh = m
    }
    ensureTransform()
    const selMesh = findCurrentMesh(selected.value as EditSel)
    if (selMesh && selected.value?.mesh) tc?.attach(selMesh)
  }

  function ensureGroundPlane() {
    const sc = opts.scene()
    if (!sc) return
    if (groundPlane) return
    const ws = workspace()
    groundPlane = new THREE.Mesh(
      new THREE.PlaneGeometry(ws.width * 2, ws.depth * 2),
      new THREE.MeshBasicMaterial({ visible: false }),
    )
    groundPlane.rotation.x = -Math.PI / 2
    groundPlane.position.set(0, 0, 0)
    groundPlane.name = 'office-edit-ground'
    sc.add(groundPlane)
  }

  function ensureTransform(): TransformControls | null {
    const sc = opts.scene()
    const el = opts.domElement()
    if (!editCamera.value || !el || !sc) return null
    if (tc) {
      if (tc.getHelper().parent !== sc) sc.add(tc.getHelper())
      setTransformMode()
      return tc
    }
    tc = new TransformControls(editCamera.value, el)
    tc.translationSnap = GRID_STEP
    tc.rotationSnap = Math.PI / 2
    tc.size = 0.5
    tc.addEventListener('objectChange', () => {})
    tc.addEventListener('dragging-changed', (e) => {
      const dragging = (e as any).value as boolean
      if (dragging) pushHistory()
      else commitTransformDrag()
    })
    sc.add(tc.getHelper())
    setTransformMode()
    return tc
  }

  function findCurrentMesh(sel: EditSel): THREE.Object3D | null {
    if (!sel) return null
    if (sel.kind === 'furniture') return furnitureMeshes.get(sel.id) || null
    if (sel.kind === 'room' && sel.zone) return roomMeshes.get(sel.zone.id) || null
    return null
  }

  function setTransformMode() {
    if (!tc) return
    const rotate = rotateMode.value
    tc.setMode(rotate ? 'rotate' : 'translate')
    tc.showX = !rotate
    tc.showZ = !rotate
    tc.showY = rotate
    tc.showXY = false
    tc.showYZ = false
    tc.showXZ = false
    tc.showXYZE = !rotate
  }

  function attachTransform() {
    if (!tc) return
    const sel = selected.value
    if (sel && sel.kind === 'furniture') {
      const mesh = findCurrentMesh(sel)
      if (mesh) {
        tc.attach(mesh)
        setTransformMode()
        return
      }
    }
    tc.detach()
  }

  function commitTransformDrag() {
    if (!tc || !selected.value) return
    const mesh = tc.object as THREE.Object3D | undefined
    if (!mesh) return
    const cfg = opts.config()
    const sel = selected.value
    if (sel.kind === 'furniture' && sel.item) {
      const constrained = constrainFurniture(sel.item, mesh.position.x, mesh.position.z, mesh.rotation.y)
      sel.item.position = { x: constrained.x, z: constrained.z }
      sel.item.rotation_y = constrained.rotationY
    }
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
    attachTransform()
  }

  function hitTestAt(clientX: number, clientY: number) {
    const el = opts.domElement()
    const cam = editCamera.value
    const env = opts.environment()
    if (!el || !cam || !env) return null
    const rect = el.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    pointerV.x = ((clientX - rect.left) / rect.width) * 2 - 1
    pointerV.y = -((clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointerV, cam)
    const targets: THREE.Object3D[] = [...env.children]
    if (planGroup) targets.push(...planGroup.children)
    const hits = raycaster.intersectObjects(targets, true)
    for (const h of hits) {
      let o: THREE.Object3D | null = h.object
      while (o) {
        const edit = o.userData.edit
        if (edit && (edit.kind === 'furniture' || edit.kind === 'room' || edit.kind === 'roomHandle')) {
          return { object: o, edit }
        }
        o = o.parent
      }
    }
    return null
  }

  function selectHit(edit: any, object: THREE.Object3D) {
    let sel: EditSel
    if (edit.kind === 'furniture') sel = { kind: 'furniture', item: edit.item, mesh: object, id: edit.id }
    else if (edit.kind === 'room') sel = { kind: 'room', zone: edit.zone, mesh: object, id: edit.id }
    else return
    selected.value = sel
    rebuildPlan()
    attachTransform()
  }

  function beginDrag(clientX: number, clientY: number): DragState | null {
    if (dragButton === 1 || panMode.value) {
      return { type: 'pan', sx: clientX, sy: clientY, cx: view.cx, cz: view.cz }
    }
    const hit = hitTestAt(clientX, clientY)
    if (hit) {
      const edit = hit.edit
      if (edit.kind === 'roomHandle' && edit.zone) {
        const b = roomBounds(edit.zone)
        const world = screenToWorld(clientX, clientY) || new THREE.Vector3()
        pushHistory()
        return { type: 'roomHandle', zone: edit.zone, handle: edit.handle, mesh: hit.object, startWorld: world, start: b }
      }
      if (edit.kind === 'room' && edit.zone) {
        const world = screenToWorld(clientX, clientY) || new THREE.Vector3()
        pushHistory()
        return { type: 'room', zone: edit.zone, mesh: edit.zone ? roomMeshes.get(edit.zone.id) || hit.object : hit.object, startX: world.x, startZ: world.z, startCenterX: edit.zone.position?.x ?? 0, startCenterZ: edit.zone.position?.z ?? 0 }
      }
      if (edit.kind === 'furniture') {
        selectHit(edit, hit.object)
        const mesh = findCurrentMesh(selected.value as EditSel) || hit.object
        const world = screenToWorld(clientX, clientY) || new THREE.Vector3()
        pushHistory()
        return { type: 'body', kind: edit.kind, mesh, id: edit.id, startWorld: { x: world.x, z: world.z }, meshStart: { x: mesh.position.x, z: mesh.position.z } }
      }
    }
    return null
  }

  function applyDrag(ev: PointerEvent, ds: DragState) {
    const cam = editCamera.value
    const el = opts.container()
    if (!cam || !el) return
    if (ds.type === 'pan') {
      const wpp = (cam.right - cam.left) / el.clientWidth
      view.cx = ds.cx - (ev.clientX - ds.sx) * wpp
      view.cz = ds.cz - (ev.clientY - ds.sy) * wpp
      ensureCamera(el.clientWidth || 1, el.clientHeight || 1)
      return
    }
    if (ds.type === 'body') {
      const world = screenToWorld(ev.clientX, ev.clientY)
      if (!world) return
      const item = (opts.config().furniture || []).find((f) => f.id === ds.id)
      const rawX = ds.meshStart.x + (world.x - ds.startWorld.x)
      const rawZ = ds.meshStart.z + (world.z - ds.startWorld.z)
      const constrained = item
        ? constrainFurniture(item, rawX, rawZ, ds.mesh.rotation.y)
        : { x: snap(rawX), z: snap(rawZ), rotationY: ds.mesh.rotation.y }
      ds.mesh.position.x = constrained.x
      ds.mesh.position.z = constrained.z
      ds.mesh.rotation.y = constrained.rotationY
      return
    }
    if (ds.type === 'room') {
      const world = screenToWorld(ev.clientX, ev.clientY)
      if (!world) return
      const nx = snap(ds.startCenterX + (world.x - ds.startX))
      const nz = snap(ds.startCenterZ + (world.z - ds.startZ))
      moveZone(ds.zone, nx, nz)
      return
    }
    if (ds.type === 'roomHandle') {
      const world = screenToWorld(ev.clientX, ev.clientY)
      if (!world) return
      if (ds.handle === 'center') {
        const startCenterX = (ds.start.minX + ds.start.maxX) / 2
        const startCenterZ = (ds.start.minZ + ds.start.maxZ) / 2
        const nx = snap(startCenterX + (world.x - ds.startWorld.x))
        const nz = snap(startCenterZ + (world.z - ds.startWorld.z))
        moveZone(ds.zone, nx, nz)
      } else {
        applyRoomHandle(ds, world)
      }
      ds.mesh.position.set(world.x, PLAN_Y + 0.1, world.z)
    }
  }

  function applyRoomHandle(ds: { type: 'roomHandle'; zone: OfficeZone; handle: RoomHandle; start: RoomBounds }, world: THREE.Vector3) {
    const b = ds.start
    let minX = b.minX
    let maxX = b.maxX
    let minZ = b.minZ
    let maxZ = b.maxZ
    const h = ds.handle
    if (h === 'nw') { minX = snap(world.x); minZ = snap(world.z) }
    else if (h === 'ne') { maxX = snap(world.x); minZ = snap(world.z) }
    else if (h === 'sw') { minX = snap(world.x); maxZ = snap(world.z) }
    else if (h === 'se') { maxX = snap(world.x); maxZ = snap(world.z) }
    else if (h === 'n') minZ = snap(world.z)
    else if (h === 's') maxZ = snap(world.z)
    else if (h === 'w') minX = snap(world.x)
    else if (h === 'e') maxX = snap(world.x)
    if (maxX - minX < 1) maxX = minX + 1
    if (maxZ - minZ < 1) maxZ = minZ + 1
    ds.zone.width = maxX - minX
    ds.zone.depth = maxZ - minZ
    ds.zone.position = { x: (minX + maxX) / 2, z: (minZ + maxZ) / 2 }
  }

  function commitDrag() {
    if (!dragState) return
    const cfg = opts.config()
    const sel = selected.value
    if (dragState.type === 'body' && sel) {
      if (dragState.kind === 'furniture' && sel.item) {
        const constrained = constrainFurniture(sel.item, dragState.mesh.position.x, dragState.mesh.position.z, dragState.mesh.rotation.y)
        sel.item.position = { x: constrained.x, z: constrained.z }
        sel.item.rotation_y = constrained.rotationY
        syncFurnitureZone(sel.item)
      }
    }
    if (dragState.type === 'room' || dragState.type === 'roomHandle') {
      syncZoneAssignments(cfg)
    }
    dragState = null
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
    attachTransform()
  }

  function editPointerDown(ev: PointerEvent) {
    if (tc?.dragging) return
    pointerActive = true
    downPt = { x: ev.clientX, y: ev.clientY }
    dragButton = ev.button
    dragState = null
    try {
      opts.domElement()?.setPointerCapture?.(ev.pointerId)
    } catch {}
  }

  function editPointerMove(ev: PointerEvent) {
    if (tc?.dragging) return
    if (!pointerActive) {
      updateHover(ev)
      setGhostFromEvent(ev)
      return
    }
    if (!dragState) {
      const dx = Math.abs(ev.clientX - downPt.x)
      const dy = Math.abs(ev.clientY - downPt.y)
      if (dx < 5 && dy < 5) {
        setGhostFromEvent(ev)
        return
      }
      dragState = beginDrag(downPt.x, downPt.y)
    }
    if (dragState) applyDrag(ev, dragState)
  }

  function updateHover(ev: PointerEvent) {
    hover.value =
      !panMode.value && !armedType.value && !armedRoom.value
        ? !!hitTestAt(ev.clientX, ev.clientY)
        : false
  }

  function editPointerUp(ev: PointerEvent) {
    if (!pointerActive) return
    pointerActive = false
    hover.value = false
    try {
      opts.domElement()?.releasePointerCapture?.(ev.pointerId)
    } catch {}
    if (tc?.dragging) return
    const dx = Math.abs(ev.clientX - downPt.x)
    const dy = Math.abs(ev.clientY - downPt.y)
    if (dragState) {
      commitDrag()
      return
    }
    if (dx > 5 || dy > 5) return
    if (panMode.value) return
    if (armedRoom.value) {
      placeRoomAt(ev.clientX, ev.clientY)
      return
    }
    if (armedType.value) {
      placeFurnitureAt(ev.clientX, ev.clientY)
      return
    }
    const hit = hitTestAt(ev.clientX, ev.clientY)
    if (hit && hit.edit.kind !== 'roomHandle') {
      selectHit(hit.edit, hit.object)
      return
    }
    selected.value = null
    rebuildPlan()
    attachTransform()
  }

  function placeFurnitureAt(clientX: number, clientY: number) {
    const pt = screenToWorld(clientX, clientY)
    if (!pt || !armedType.value) return
    const cfg = opts.config()
    const furniture = cfg.furniture ?? (cfg.furniture = [])
    pushHistory()
    const item: OfficeFurnitureItem = {
      id: `${armedType.value}-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
      type: armedType.value,
      position: { x: snap(pt.x), z: snap(pt.z) },
      rotation_y: 0,
      zoneId: null,
    }
    furniture.push(item)
    syncFurnitureZone(item)
    armedType.value = null
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
  }

  function placeRoomAt(clientX: number, clientY: number) {
    const pt = screenToWorld(clientX, clientY)
    if (!pt) return
    const cfg = opts.config()
    const zones = cfg.zones ?? (cfg.zones = [])
    pushHistory()
    const w = 4
    const d = 3
    const zone: OfficeZone = {
      id: `room-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
      type: 'room',
      label: '房间',
      room: true,
      position: { x: snap(pt.x), z: snap(pt.z) },
      width: w,
      depth: d,
    }
    zones.push(zone)
    armedRoom.value = false
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
    selected.value = { kind: 'room', zone, id: zone.id }
    buildSelection()
  }

  function onWheel(ev: WheelEvent) {
    if (!editing.value) return
    ev.preventDefault()
    zoomAt(ev.clientX, ev.clientY, ev.deltaY < 0 ? 1.1 : 0.9)
  }

  function selectByType(type: string) {
    armedType.value = type
    armedRoom.value = false
    selected.value = null
    hover.value = false
    rebuildPlan()
    attachTransform()
  }

  function setArmedRoom(on: boolean) {
    armedRoom.value = on
    armedType.value = null
    selected.value = null
    hover.value = false
    rebuildPlan()
    attachTransform()
  }

  function setPanMode(on: boolean) {
    panMode.value = on
    hover.value = false
    if (on) {
      armedType.value = null
      armedRoom.value = false
      selected.value = null
      if (tc) tc.detach()
      rebuildPlan()
      attachTransform()
    }
  }

  function removeSelected() {
    const sel = selected.value
    if (!sel) return
    const cfg = opts.config()
    pushHistory()
    if (sel.kind === 'furniture') {
      cfg.furniture = (cfg.furniture || []).filter((it) => it.id !== sel.id)
    } else if (sel.kind === 'room' && sel.zone) {
      cfg.zones = (cfg.zones || []).filter((z) => z.id !== sel.id)
    }
    selected.value = null
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
    attachTransform()
  }

  function toggleRotate() {
    rotateMode.value = !rotateMode.value
    if (tc) tc.detach()
    attachTransform()
    setTransformMode()
  }

  function flipSelected() {
    const sel = selected.value
    if (!sel || sel.kind !== 'furniture' || !sel.item) return
    const def = catalogDef(sel.item.type)
    if (def.rotatable === false) return
    pushHistory()
    sel.item.rotation_y = normalizeRotation((sel.item.rotation_y ?? 0) + Math.PI)
    opts.onChanged?.(opts.config())
    rebuildEnvironment()
    rebuildPlan()
    attachTransform()
  }

  function updateSelected(patch: Partial<OfficeFurnitureItem & { width?: number; depth?: number }>) {
    const sel = selected.value
    if (!sel) return
    const cfg = opts.config()
    pushHistory()
    if (sel.kind === 'furniture' && sel.item) {
      Object.assign(sel.item, patch)
      if (patch.position !== undefined) syncFurnitureZone(sel.item)
    }
    else if (sel.kind === 'room' && sel.zone) {
      if (patch.position !== undefined) {
        moveZone(sel.zone, patch.position.x ?? sel.zone.position?.x ?? 0, patch.position.z ?? sel.zone.position?.z ?? 0)
        if (patch.width !== undefined || patch.depth !== undefined) syncZoneAssignments(cfg)
      } else {
        Object.assign(sel.zone, patch)
        syncZoneAssignments(cfg)
      }
    }
    opts.onChanged?.(cfg)
    rebuildEnvironment()
    rebuildPlan()
    attachTransform()
  }

  function enter() {
    const el = opts.container()
    const sc = opts.scene()
    if (!el || !sc) return
    normalizeOfficeConfig(opts.config())
    syncZoneAssignments(opts.config())
    editing.value = true
    enterSnapshot = snapConfig()
    undoStack.value.length = 0
    redoStack.value.length = 0
    selected.value = null
    hover.value = false
    armedType.value = null
    armedRoom.value = false
    rotateMode.value = false
    view = { cx: 0, cz: 0 }
    zoomPct.value = 100
    panMode.value = false
    pointerActive = false
    dragButton = 0
    dragState = null
    ensureGroundPlane()
    ensureCamera(el.clientWidth || 1, el.clientHeight || 1)
    rebuildEnvironment()
    rebuildPlan()
  }

  function exit() {
    editing.value = false
    selected.value = null
    hover.value = false
    armedType.value = null
    armedRoom.value = false
    rotateMode.value = false
    dragState = null
    panMode.value = false
    pointerActive = false
    dragButton = 0
    if (tc) {
      tc.detach()
      const helper = tc.getHelper()
      if (opts.scene()) opts.scene()!.remove(helper)
    }
    if (planGroup && opts.scene()) {
      opts.scene()!.remove(planGroup)
      disposeGroup(planGroup)
    }
    planGroup = null
    if (groundPlane && opts.scene()) opts.scene()!.remove(groundPlane)
    groundPlane = null
    ghostMesh = null
    furnitureMeshes.clear()
    roomMeshes.clear()
    roomHandleMeshes.length = 0
  }

  function syncEditor() {
    if (!editing.value) return
    rebuildPlan()
  }

  function setPlanVisible(visible: boolean) {
    if (planGroup) planGroup.visible = visible
  }

  function setTransformVisible(visible: boolean) {
    if (tc) tc.getHelper().visible = visible
  }

  function ensureFit() {
    fitView()
  }

  function zoomCenter(factor: number) {
    const el = opts.container()
    if (!el) return
    const rect = el.getBoundingClientRect()
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor)
  }

  return {
    editing,
    editCamera,
    selected,
    armedType,
    armedRoom,
    rotateMode,
    panMode,
    zoomPct,
    catalog,
    hover,
    enter,
    exit,
    setPlanVisible,
    setTransformVisible,
    syncEditor,
    ensureFit,
    editPointerDown,
    editPointerMove,
    editPointerUp,
    onWheel,
    selectByType,
    setArmedRoom,
    setPanMode,
    removeSelected,
    updateSelected,
    toggleRotate,
    flipSelected,
    undo,
    redo,
    canUndo,
    canRedo,
    cancelEdit,
    zoomIn: () => zoomCenter(1.1),
    zoomOut: () => zoomCenter(0.9),
    fitView,
  }
}
