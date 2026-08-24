<template>
  <div ref="containerRef" class="office-3d-canvas"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js'
import type { BehaviorConfig, OfficeColleagueStatus, OfficeConfig, OfficeEnvironmentTheme, OfficeFurnitureItem, OfficeZone, OfficeZoneSlot } from '@/api/office'

const props = defineProps<{
  colleagues: any[]
  statusMap: Record<string, OfficeColleagueStatus>
  selectedRoleKey?: string | null
  officeConfig?: OfficeConfig
  behaviorConfig?: BehaviorConfig
}>()

const emit = defineEmits<{
  select: [roleKey: string]
}>()

type CharacterTemplate = {
  scene: THREE.Group
  animations: THREE.AnimationClip[]
  height: number
  depth: number
  frontRotation: number
}

type Actor = {
  roleKey: string
  group: THREE.Group
  character: THREE.Group
  desk: THREE.Group
  indicator: THREE.Mesh
  indicatorMat: THREE.MeshBasicMaterial
  monitorMat: THREE.MeshStandardMaterial
  selectionRing: THREE.Mesh
  basePosition: THREE.Vector3
  phase: number
  status: string
  bubble: THREE.Sprite
  label: THREE.Sprite
  bubbleTexture: THREE.CanvasTexture
  bubbleCanvas: HTMLCanvasElement
  bubbleCtx: CanvasRenderingContext2D
  targetPosition: THREE.Vector3
  walking: boolean
  mixer: THREE.AnimationMixer | null
  idleAction: THREE.AnimationAction | null
  walkAction: THREE.AnimationAction | null
  sitAction: THREE.AnimationAction | null
  halfDepth: number
  modelScale: number
  seatY: number
  forward: THREE.Vector3
  right: THREE.Vector3
  homeZoneId: string
  homeSlot: OfficeZoneSlot
  currentZoneId?: string | null
  targetZoneType?: string | null
  route: THREE.Vector3[]
  routeIndex: number
  walkTarget: THREE.Vector3
  armL?: THREE.Object3D | null
  armR?: THREE.Object3D | null
  legL?: THREE.Object3D | null
  legR?: THREE.Object3D | null
}

const containerRef = ref<HTMLElement | null>(null)

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let controls: OrbitControls | null = null
let resizeObserver: ResizeObserver | null = null
let environment: THREE.Group | null = null
let rafId = 0
let disposed = false
let pointerDown = { x: 0, y: 0 }
let followRoleKey: string | null = null

const actorMap = new Map<string, Actor>()
const characterTemplates: CharacterTemplate[] = []
let lastFrameTime = 0
let renderLoopRunning = false

const DESK_WORK_DISTANCE = 0.78
const DESK_IDLE_DISTANCE = 0.95
const DESK_WAIT_DISTANCE = 1.18
const DESK_WAIT_SIDE = 0.28
const DESK_CHAIR_OFFSET = 1.0
const MEETING_CHAIR_BACK_REACH = 0.27
const MEETING_STAND_GAP = 0.18
const WALK_SPEED = 2.4
const CHAIR_SEAT_HEIGHT = 0.48
const CHAIR_SEAT_BACK_OFFSET = 0.24
const SIT_HIP_LOCAL_Y = 0.026
const SIT_BACK_LOCAL_Z = 0.224
const FALLBACK_STATUS_COLOR = '#9aa4b2'
const DEFAULT_FLOOR = { width: 24, depth: 16 }

const ENVIRONMENT_PRESETS: Record<string, OfficeEnvironmentTheme> = {
  midnight: {
    preset: 'midnight',
    palette: {
      floor: '#151c29', wall: '#222e42', wall_lower: '#1a2434', accent: '#1677ff',
      ceiling: '#0d1320', furniture: '#26344a', furniture_light: '#34455f', foliage: '#2f7d54',
    },
    props: {
      plants: true, bookshelves: true, lounge: true, coffee_bar: true,
      whiteboard: true, windows: true, ceiling_lights: true, art: true,
    },
    lighting: { ambient_intensity: 0.62, key_intensity: 1.6, fill_intensity: 0.42, window_glow: 0.8 },
  },
  daylight: {
    preset: 'daylight',
    palette: {
      floor: '#d8c5a3', wall: '#eef2f5', wall_lower: '#dce4e9', accent: '#0ea5e9',
      ceiling: '#f7f9fb', furniture: '#6f5238', furniture_light: '#8a6b4e', foliage: '#4a9d6c',
    },
    props: {
      plants: true, bookshelves: true, lounge: true, coffee_bar: true,
      whiteboard: true, windows: true, ceiling_lights: true, art: true,
    },
    lighting: { ambient_intensity: 0.95, key_intensity: 1.3, fill_intensity: 0.6, window_glow: 1.15 },
  },
  'warm-loft': {
    preset: 'warm-loft',
    palette: {
      floor: '#7b5937', wall: '#3a302c', wall_lower: '#2b2521', accent: '#ff9f43',
      ceiling: '#241f1c', furniture: '#4a3b30', furniture_light: '#5e4b3c', foliage: '#4f8a5f',
    },
    props: {
      plants: true, bookshelves: true, lounge: true, coffee_bar: true,
      whiteboard: true, windows: true, ceiling_lights: true, art: true,
    },
    lighting: { ambient_intensity: 0.72, key_intensity: 1.25, fill_intensity: 0.5, window_glow: 0.9 },
  },
}

function officeTheme(): OfficeEnvironmentTheme {
  const raw = officeConfigValue().environment_theme || {}
  const preset = ENVIRONMENT_PRESETS[raw.preset || 'daylight'] || ENVIRONMENT_PRESETS.daylight
  return {
    ...preset,
    ...raw,
    palette: { ...preset.palette, ...(raw.palette || {}) },
    props: { ...preset.props, ...(raw.props || {}) },
    lighting: { ...preset.lighting, ...(raw.lighting || {}) },
  }
}

type BehaviorStatusMeta = {
  label?: string
  color?: string
  monitor_active?: boolean
  indicator_opacity?: number
  animation?: string
}

function officeConfigValue(): OfficeConfig {
  return props.officeConfig || {}
}

function behaviorConfigValue(): BehaviorConfig {
  return props.behaviorConfig || {}
}

function statusMetaMap(): Record<string, BehaviorStatusMeta> {
  return behaviorConfigValue().status_meta || {}
}

function statusMetaFor(status: string): BehaviorStatusMeta {
  return statusMetaMap()[status] || {}
}

function statusTextFor(status: string): string {
  return statusMetaFor(status).label || status || '空闲'
}

function statusColorHex(status: string): number {
  const raw = statusMetaFor(status).color || FALLBACK_STATUS_COLOR
  return new THREE.Color(raw).getHex()
}

function officeFloor(): { width: number; depth: number } {
  return { ...DEFAULT_FLOOR, ...(officeConfigValue().floor || {}) }
}

function officeWorkspace(): { width: number; depth: number } {
  const floor = officeFloor()
  return {
    width: officeConfigValue().workspace?.width || Math.max(floor.width, 24),
    depth: officeConfigValue().workspace?.depth || Math.max(floor.depth, 16),
  }
}

function officeFurniture(): OfficeFurnitureItem[] {
  return officeConfigValue().furniture || []
}

function officeZones(): OfficeZone[] {
  return officeConfigValue().zones || []
}

function deskZones(): OfficeZone[] {
  return officeZones().filter((zone) => zone.type === 'desk')
}

function zoneById(zoneId: string): OfficeZone | null {
  return officeZones().find((zone) => zone.id === zoneId) || null
}

function slotPosition(slot: OfficeZoneSlot): THREE.Vector3 {
  return new THREE.Vector3(slot.position?.x ?? 0, 0, slot.position?.z ?? 0)
}

function slotRotationY(slot: OfficeZoneSlot): number {
  return slot.rotation_y ?? 0
}

function slotForward(slot: OfficeZoneSlot): THREE.Vector3 {
  const rotation = slotRotationY(slot)
  return new THREE.Vector3(Math.sin(rotation), 0, Math.cos(rotation))
}

function slotRight(slot: OfficeZoneSlot): THREE.Vector3 {
  const rotation = slotRotationY(slot)
  return new THREE.Vector3(Math.cos(rotation), 0, -Math.sin(rotation))
}

function slotPhase(slot: OfficeZoneSlot): number {
  return slotRotationY(slot) + Math.PI
}

function hashRoleKey(roleKey: string): number {
  let hash = 0
  for (let i = 0; i < roleKey.length; i += 1) {
    hash = (hash * 31 + roleKey.charCodeAt(i)) >>> 0
  }
  return hash
}

function deskSlotAssignments(): Map<string, { zone: OfficeZone; slot: OfficeZoneSlot }> {
  const assignments = new Map<string, { zone: OfficeZone; slot: OfficeZoneSlot }>()
  const freeSlots: Array<{ zone: OfficeZone; slot: OfficeZoneSlot }> = []
  const roleKeys = new Set(props.colleagues.map((colleague) => colleague.role_key))
  for (const zone of deskZones()) {
    for (const slot of zone.slots || []) {
      if (slot.role_key && roleKeys.has(slot.role_key)) {
        assignments.set(slot.role_key, { zone, slot })
      } else {
        freeSlots.push({ zone, slot })
      }
    }
  }
  let cursor = 0
  for (const colleague of props.colleagues) {
    if (assignments.has(colleague.role_key)) continue
    const next = freeSlots[cursor % Math.max(1, freeSlots.length)]
    if (next) {
      assignments.set(colleague.role_key, next)
      cursor += 1
    }
  }
  return assignments
}

function fallbackDeskSlot(index: number): { zone: OfficeZone; slot: OfficeZoneSlot } | null {
  const slots: Array<{ zone: OfficeZone; slot: OfficeZoneSlot }> = []
  for (const zone of deskZones()) {
    for (const slot of zone.slots || []) slots.push({ zone, slot })
  }
  return slots[index % Math.max(1, slots.length)] || null
}

function resolveZoneForStatus(roleKey: string, status: string, event?: OfficeColleagueStatus): OfficeZone | null {
  const officeEvent = event || props.statusMap[roleKey]
  const requestedZone = officeEvent?.zone || officeEvent?.intent
  if (requestedZone) return zoneById(requestedZone)
  const zoneId = officeConfigValue().status_zone_map?.[status]
  return zoneId ? zoneById(zoneId) : null
}

function meetingSlotForActor(zone: OfficeZone, roleKey: string): OfficeZoneSlot {
  const slots = zone.slots || []
  if (!slots.length) return { id: 'meeting-fallback', position: zone.position || { x: 0, z: 0 }, rotation_y: 0 }
  const explicit = slots.find((slot) => slot.role_key === roleKey)
  if (explicit) return explicit
  return slots[hashRoleKey(roleKey) % slots.length]
}

function meetingPhaseForSlot(zone: OfficeZone, slot: OfficeZoneSlot): number {
  const center = zone.position || { x: 0, z: 0 }
  const position = slotPosition(slot)
  return Math.atan2(center.x - position.x, center.z - position.z)
}

onMounted(() => {
  init()
})

onBeforeUnmount(() => {
  dispose()
})

watch(
  () => props.colleagues,
  () => {
    if (!scene) return
    rebuildActors()
  },
  { deep: true },
)

watch(
  () => props.statusMap,
  () => applyStatuses(),
  { deep: true },
)

watch(
  () => props.selectedRoleKey,
  () => {
    updateSelection()
    if (!props.selectedRoleKey) followRoleKey = null
  },
)

watch(
  () => props.officeConfig,
  async () => {
    if (!scene) return
    buildEnvironment()
    await loadCharacterTemplates()
    rebuildActors()
  },
  { deep: true },
)

watch(
  () => props.behaviorConfig,
  () => applyStatuses(),
  { deep: true },
)

async function loadCharacterTemplates() {
  characterTemplates.length = 0
  const modelFiles = officeConfigValue().character_models || []
  const loader = new GLTFLoader()
  for (const url of modelFiles) {
    try {
      const gltf = await loader.loadAsync(url)
      const box = new THREE.Box3().setFromObject(gltf.scene)
      const size = new THREE.Vector3()
      box.getSize(size)
      characterTemplates.push({
        scene: gltf.scene,
        animations: gltf.animations || [],
        height: size.y || 2.5,
        depth: size.z || 0.45,
        frontRotation: 0,
      })
    } catch (error) {
      console.error(`加载 AI 同事模型失败: ${url}`, error)
    }
  }
}

function init() {
  const el = containerRef.value
  if (!el || el.clientWidth === 0 || el.clientHeight === 0) return

  scene = new THREE.Scene()

  const workspace = officeWorkspace()
  camera = new THREE.PerspectiveCamera(42, el.clientWidth / el.clientHeight, 0.1, 140)
  camera.position.set(workspace.width * 0.28, 13, 24)
  camera.lookAt(workspace.width * 0.18, 0.6, 0)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setClearColor(0x000000, 0)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(el.clientWidth, el.clientHeight, false)
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(workspace.width * 0.18, 0.6, 0)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = 6
  controls.maxDistance = 55
  controls.maxPolarAngle = 1.45
  controls.update()

  buildEnvironment()
  loadCharacterTemplates().then(() => {
    rebuildActors()
    applyStatuses()
    updateSelection()
  })

  resizeObserver = new ResizeObserver(onResize)
  resizeObserver.observe(el)

  renderer.domElement.addEventListener('pointerdown', onPointerDown)
  renderer.domElement.addEventListener('pointermove', onPointerMove)
  renderer.domElement.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)

  document.addEventListener('visibilitychange', onVisibilityChange)
  startRenderLoop()
}

function startRenderLoop() {
  if (renderLoopRunning || !scene || !camera || !renderer) return
  renderLoopRunning = true
  rafId = requestAnimationFrame(tick)
}

function stopRenderLoop() {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = 0
  renderLoopRunning = false
}

function onVisibilityChange() {
  if (document.hidden) stopRenderLoop()
  else startRenderLoop()
}

function onResize() {
  const el = containerRef.value
  if (!el || !camera || !renderer) return
  const w = el.clientWidth
  const h = el.clientHeight
  if (w === 0 || h === 0) return
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h, false)
}

function buildEnvironment() {
  if (!scene) return
  if (environment) {
    scene.remove(environment)
    disposeGroup(environment)
  }

  environment = new THREE.Group()
  environment.name = 'office-environment'

  const theme = officeTheme()
  const floorConfig = officeFloor()
  const width = floorConfig.width || 24
  const depth = floorConfig.depth || 16
  const wallHeight = 3.25
  const wallThickness = 0.28

  buildFloor(theme, width, depth)
  buildWalls(theme, width, depth, wallHeight, wallThickness)
  buildCeilingEdges(theme, width, depth, wallHeight, wallThickness)
  buildLighting(theme, width, depth, wallHeight)
  buildProps(theme, width, depth, wallHeight)

  for (const zone of officeZones()) {
    if (zone.type === 'meeting') buildMeetingRoom(zone)
  }

  scene.add(environment)
}

function envMaterial(color: string, roughness = 0.82, metalness = 0.05): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness, metalness })
}

function applyShadow(mesh: THREE.Mesh, castShadow = true, receiveShadow = true) {
  mesh.castShadow = castShadow
  mesh.receiveShadow = receiveShadow
}

function buildFloor(theme: OfficeEnvironmentTheme, width: number, depth: number) {
  if (!environment) return
  const floorColor = theme.palette?.floor || '#151c29'
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), envMaterial(floorColor, 0.9, 0.04))
  floor.rotation.x = -Math.PI / 2
  floor.position.y = 0
  floor.receiveShadow = true
  environment.add(floor)

  const officeGrid = createRectangularGrid(
    width,
    depth,
    Math.max(1, Math.round(Math.max(width, depth))),
    floorColor,
    0.012,
  )
  environment.add(officeGrid)
}

function createRectangularGrid(width: number, depth: number, divisions: number, color: string, y = 0.012): THREE.LineSegments {
  const maxDimension = Math.max(width, depth)
  const step = maxDimension / Math.max(1, divisions)
  const points: THREE.Vector3[] = []

  for (let x = -width / 2; x <= width / 2 + 0.001; x += step) {
    points.push(new THREE.Vector3(x, 0, -depth / 2), new THREE.Vector3(x, 0, depth / 2))
  }
  for (let z = -depth / 2; z <= depth / 2 + 0.001; z += step) {
    points.push(new THREE.Vector3(-width / 2, 0, z), new THREE.Vector3(width / 2, 0, z))
  }

  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const material = new THREE.LineBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.58,
  })
  const grid = new THREE.LineSegments(geometry, material)
  grid.position.y = y
  return grid
}

function createWindowedBackWall(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number) {
  const group = new THREE.Group()
  const wallColor = theme.palette?.wall || '#222e42'
  const lowerColor = theme.palette?.wall_lower || '#1a2434'

  const wall = new THREE.Mesh(new THREE.BoxGeometry(width, height, thickness), envMaterial(wallColor, 0.86, 0.06))
  wall.position.set(0, height / 2, -depth / 2)
  wall.receiveShadow = true
  group.add(wall)

  if (theme.props?.windows !== false) {
    const innerZ = -depth / 2 + thickness / 2 + 0.02
    const windowCount = Math.max(2, Math.floor(width / 4.2))
    const windowWidth = Math.min(2.05, (width - 1.4) / Math.max(1, windowCount))
    const gap = (width - windowCount * windowWidth) / (windowCount + 1)

    for (let i = 0; i < windowCount; i += 1) {
      const x = -width / 2 + gap + windowWidth / 2 + i * (windowWidth + gap)
      const glass = new THREE.Mesh(
        new THREE.PlaneGeometry(windowWidth, 1.5),
        new THREE.MeshStandardMaterial({
          color: 0x9fd4ff,
          emissive: 0x2f6d95,
          emissiveIntensity: 1.15,
          roughness: 0.16,
          metalness: 0.08,
          transparent: true,
          opacity: 0.9,
        }),
      )
      glass.position.set(x, 1.78, innerZ)
      group.add(glass)

      const frameMat = envMaterial(lowerColor, 0.5, 0.16)
      const frameThickness = 0.09
      const frameDepth = 0.12
      const horizontal = new THREE.BoxGeometry(windowWidth + 0.18, frameThickness, frameDepth)
      const top = new THREE.Mesh(horizontal, frameMat)
      top.position.set(x, 2.56, innerZ)
      group.add(top)
      const bottom = new THREE.Mesh(horizontal, frameMat)
      bottom.position.set(x, 1.0, innerZ)
      group.add(bottom)
      const vertical = new THREE.BoxGeometry(frameThickness, 1.68, frameDepth)
      for (const side of [-1, 1]) {
        const bar = new THREE.Mesh(vertical, frameMat)
        bar.position.set(x + side * (windowWidth / 2 + 0.09), 1.78, innerZ)
        group.add(bar)
      }

      const sill = new THREE.Mesh(new THREE.BoxGeometry(windowWidth + 0.4, 0.06, 0.24), envMaterial(lowerColor, 0.55, 0.12))
      sill.position.set(x, 0.94, innerZ + 0.04)
      sill.receiveShadow = true
      group.add(sill)
    }
  }

  return group
}

function createSideWall(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number, side: number, doorGap?: { center: number; width: number }) {
  const group = new THREE.Group()
  const wallColor = theme.palette?.wall || '#222e42'
  const lowerColor = theme.palette?.wall_lower || '#1a2434'
  const innerX = side * (width / 2 - thickness / 2 - 0.01)
  const segments: Array<[number, number]> = []
  const gapStart = doorGap ? doorGap.center - doorGap.width / 2 : 0
  const gapEnd = doorGap ? doorGap.center + doorGap.width / 2 : 0

  if (!doorGap) {
    segments.push([-depth / 2, depth / 2])
  } else {
    if (gapStart > -depth / 2) segments.push([-depth / 2, gapStart])
    if (gapEnd < depth / 2) segments.push([gapEnd, depth / 2])
  }

  for (const [fromZ, toZ] of segments) {
    const length = toZ - fromZ
    if (length <= 0.01) continue
    const centerZ = (fromZ + toZ) / 2

    const wall = new THREE.Mesh(new THREE.BoxGeometry(thickness, height, length), envMaterial(wallColor, 0.86, 0.06))
    wall.position.set(side * width / 2, height / 2, centerZ)
    wall.receiveShadow = true
    group.add(wall)

    const baseboard = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.18, Math.max(0.1, length - 0.06)), envMaterial(lowerColor, 0.6, 0.1))
    baseboard.position.set(innerX, 0.09, centerZ)
    group.add(baseboard)

    const panel = new THREE.Mesh(new THREE.BoxGeometry(0.035, 1.65, Math.max(0.1, length - 0.1)), envMaterial(lowerColor, 0.72, 0.08))
    panel.position.set(innerX, 1.15, centerZ)
    group.add(panel)

    const strip = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.07, Math.max(0.1, length - 0.1)), envMaterial(theme.palette?.accent || '#1677ff', 0.35, 0.15))
    strip.position.set(innerX, 2.68, centerZ)
    group.add(strip)
  }

  if (doorGap && gapEnd > gapStart) {
    const postGeo = new THREE.BoxGeometry(thickness + 0.08, height, 0.12)
    for (const z of [gapStart, gapEnd]) {
      const post = new THREE.Mesh(postGeo, envMaterial(wallColor, 0.86, 0.06))
      post.position.set(side * width / 2, height / 2, z)
      group.add(post)
    }
    const header = new THREE.Mesh(new THREE.BoxGeometry(thickness + 0.08, 0.22, doorGap.width), envMaterial(wallColor, 0.86, 0.06))
    header.position.set(side * width / 2, height - 0.11, doorGap.center)
    group.add(header)
  }

  return group
}

function officeWallDoorGap(targetWall: 'left' | 'right' | 'back'): { center: number; width: number } | null {
  const floor = officeFloor()
  for (const zone of officeZones()) {
    if (zone.type !== 'meeting') continue
    const side = meetingDoorSide(zone, floor)
    const doorWidth = zone.door?.width ?? 1.3
    const doorOffset = zone.door?.offset ?? 0
    if (side === 'left' && targetWall === 'right') {
      return { center: (zone.position?.z ?? 0) + doorOffset, width: doorWidth }
    }
    if (side === 'right' && targetWall === 'left') {
      return { center: (zone.position?.z ?? 0) + doorOffset, width: doorWidth }
    }
    if (side === 'front' && targetWall === 'back') {
      return { center: (zone.position?.x ?? 0) + doorOffset, width: doorWidth }
    }
  }
  return null
}

function buildWalls(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number) {
  if (!environment) return
  environment.add(createWindowedBackWall(theme, width, depth, height, thickness))
  environment.add(createSideWall(theme, width, depth, height, thickness, -1, officeWallDoorGap('left') || undefined))
  environment.add(createSideWall(theme, width, depth, height, thickness, 1, officeWallDoorGap('right') || undefined))
}

function buildCeilingEdges(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number) {
  if (!environment) return
  const ceilingColor = theme.palette?.ceiling || '#0d1320'
  const edgeMat = envMaterial(ceilingColor, 0.75, 0.08)
  const edgeHeight = 0.14
  const edgeDepth = 0.24

  const back = new THREE.Mesh(new THREE.BoxGeometry(width + thickness * 2, edgeHeight, edgeDepth), edgeMat)
  back.position.set(0, height - edgeHeight / 2, -depth / 2)
  environment.add(back)

  const front = new THREE.Mesh(new THREE.BoxGeometry(width + thickness * 2, edgeHeight, edgeDepth), edgeMat)
  front.position.set(0, height - edgeHeight / 2, depth / 2)
  environment.add(front)

  for (const side of [-1, 1]) {
    const edge = new THREE.Mesh(new THREE.BoxGeometry(edgeDepth, edgeHeight, depth + thickness * 2), edgeMat)
    edge.position.set(side * width / 2, height - edgeHeight / 2, 0)
    environment.add(edge)
  }
}

function buildLighting(theme: OfficeEnvironmentTheme, width: number, depth: number, _height: number) {
  if (!environment) return
  const lighting = theme.lighting || {}
  const skyColor = theme.palette?.ceiling || '#d8e4f2'
  const groundColor = theme.palette?.floor || '#111722'

  environment.add(new THREE.HemisphereLight(skyColor, groundColor, 0.42))
  environment.add(new THREE.AmbientLight(0xffffff, lighting.ambient_intensity ?? 0.62))

  const keyLight = new THREE.DirectionalLight(0xfff3e0, lighting.key_intensity ?? 1.6)
  keyLight.position.set(5, 7, 4)
  keyLight.castShadow = true
  keyLight.shadow.mapSize.set(2048, 2048)
  keyLight.shadow.camera.near = 1
  keyLight.shadow.camera.far = 32
  keyLight.shadow.camera.left = -18
  keyLight.shadow.camera.right = 18
  keyLight.shadow.camera.top = 18
  keyLight.shadow.camera.bottom = -18
  keyLight.shadow.bias = -0.0002
  keyLight.shadow.radius = 4
  environment.add(keyLight)

  const fillLight = new THREE.DirectionalLight(0xbfd4ff, lighting.fill_intensity ?? 0.42)
  fillLight.position.set(-5, 3, -4)
  environment.add(fillLight)

  if (theme.props?.windows !== false) {
    const windowLight = new THREE.PointLight(0x9fd4ff, (lighting.window_glow ?? 0.8) * 2.2, Math.max(width, depth) * 1.2, 2)
    windowLight.position.set(0, 2.3, -depth / 2 + 0.5)
    environment.add(windowLight)
  }
}

function addPlant(x: number, z: number, theme: OfficeEnvironmentTheme) {
  const group = new THREE.Group()
  const potMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.5, 0.14)
  const foliageMat = envMaterial(theme.palette?.foliage || '#2f7d54', 0.78, 0.02)

  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.18, 0.42, 16), potMat)
  pot.position.y = 0.21
  pot.castShadow = true
  pot.receiveShadow = true
  group.add(pot)

  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.05, 0.55, 8), envMaterial('#6e4f34', 0.85, 0.02))
  trunk.position.y = 0.7
  group.add(trunk)

  const foliageA = new THREE.Mesh(new THREE.SphereGeometry(0.34, 12, 10), foliageMat)
  foliageA.position.y = 1.05
  foliageA.castShadow = true
  group.add(foliageA)

  const foliageB = new THREE.Mesh(new THREE.SphereGeometry(0.25, 12, 10), foliageMat)
  foliageB.position.set(0.12, 1.28, -0.05)
  foliageB.castShadow = true
  group.add(foliageB)

  group.position.set(x, 0, z)
  environment?.add(group)
}

function addBookshelf(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY?: number) {
  const group = new THREE.Group()
  const frameMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.55, 0.12)
  const bookColors = [0x1677ff, 0xff9f43, 0x2f7d54, 0xd74c5e, 0x7b61ff, 0x37b6c7]
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2.1, 0.5), frameMat)
  body.position.y = 1.05
  body.castShadow = true
  body.receiveShadow = true
  group.add(body)

  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 7; col += 1) {
      const height = 0.36 + ((row * 13 + col) % 3) * 0.035
      const book = new THREE.Mesh(
        new THREE.BoxGeometry(0.12, height, 0.28),
        new THREE.MeshStandardMaterial({ color: bookColors[(row + col) % bookColors.length], roughness: 0.72, metalness: 0.02 }),
      )
      book.position.set(-0.52 + col * 0.17, 0.24 + row * 0.48 + height / 2, 0)
      group.add(book)
    }
  }

  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x < 0 ? 0 : Math.PI)
  environment?.add(group)
}

function addCoffeeBar(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY?: number) {
  const group = new THREE.Group()
  const counterMat = envMaterial(theme.palette?.furniture || '#26344a', 0.52, 0.16)
  const topMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.4, 0.2)
  const counter = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.95, 0.62), counterMat)
  counter.position.y = 0.475
  counter.castShadow = true
  counter.receiveShadow = true
  group.add(counter)

  const top = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.06, 0.72), topMat)
  top.position.y = 0.98
  top.castShadow = true
  top.receiveShadow = true
  group.add(top)

  const machine = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.5, 0.3), envMaterial('#1d2530', 0.42, 0.28))
  machine.position.set(-0.3, 1.24, 0)
  machine.castShadow = true
  group.add(machine)

  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.26, 14), envMaterial('#d6cfc0', 0.5, 0.22))
  pot.position.set(0.2, 1.12, 0)
  group.add(pot)

  for (const mx of [-0.18, 0.02, 0.22]) {
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.035, 0.09, 12), envMaterial('#e5e9f0', 0.6, 0.05))
    mug.position.set(mx + 0.25, 1.06, -0.18)
    group.add(mug)
  }

  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x > 0 ? -Math.PI / 2 : Math.PI / 2)
  environment?.add(group)
}

function addLounge(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY?: number) {
  const group = new THREE.Group()
  const fabricMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.78, 0.04)
  const base = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.4, 0.9), fabricMat)
  base.position.y = 0.22
  base.castShadow = true
  base.receiveShadow = true
  group.add(base)

  const back = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.75, 0.22), fabricMat)
  back.position.set(0, 0.68, -0.35)
  back.castShadow = true
  group.add(back)

  for (const side of [-1, 1]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.55, 0.9), fabricMat)
    arm.position.set(side * 0.89, 0.45, 0)
    arm.castShadow = true
    group.add(arm)
  }

  const table = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.08, 18), envMaterial(theme.palette?.accent || '#1677ff', 0.35, 0.2))
  table.position.set(0, 0.38, 0.75)
  table.castShadow = true
  table.receiveShadow = true
  group.add(table)

  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x > 0 ? -Math.PI / 2 : Math.PI / 2)
  environment?.add(group)
}

function addWhiteboard(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0) {
  const group = new THREE.Group()
  const frameMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.5, 0.16)
  const surfaceMat = new THREE.MeshStandardMaterial({ color: 0xf4f7fb, roughness: 0.35, metalness: 0.02, emissive: 0x11161f, emissiveIntensity: 0.05 })
  const frame = new THREE.Mesh(new THREE.BoxGeometry(2.1, 1.25, 0.08), frameMat)
  frame.position.y = 1.5
  frame.castShadow = true
  group.add(frame)
  const surface = new THREE.Mesh(new THREE.PlaneGeometry(1.94, 1.09), surfaceMat)
  surface.position.set(0, 1.5, 0.05)
  group.add(surface)
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  environment?.add(group)
}

function addArt(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY: number, color: string) {
  const group = new THREE.Group()
  const frame = new THREE.Mesh(new THREE.BoxGeometry(0.95, 0.7, 0.06), envMaterial(theme.palette?.furniture_light || '#34455f', 0.5, 0.16))
  frame.position.y = 1.75
  group.add(frame)
  const canvas = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 0.55), new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.02 }))
  canvas.position.set(0, 1.75, 0.04)
  group.add(canvas)
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  environment?.add(group)
}

function addOfficeChair(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0) {
  const group = new THREE.Group()
  const chairFabric = envMaterial(theme.palette?.furniture_light || '#34455f', 0.72, 0.06)
  const chairDark = envMaterial('#111822', 0.55, 0.22)

  const chairBase = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.3, 0.06, 16), chairDark)
  chairBase.position.y = 0.04
  chairBase.castShadow = true
  group.add(chairBase)
  const chairPole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.045, 0.4, 10), chairDark)
  chairPole.position.y = 0.26
  group.add(chairPole)
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.1, 0.5), chairFabric)
  seat.position.y = 0.48
  seat.castShadow = true
  group.add(seat)
  const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.62, 0.1), chairFabric)
  chairBack.position.set(0, 0.86, -0.24)
  chairBack.castShadow = true
  group.add(chairBack)
  for (const x of [-0.3, 0.3]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.55, 0.16), chairFabric)
    arm.position.set(x, 0.66, 0.02)
    arm.castShadow = true
    group.add(arm)
  }

  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  environment?.add(group)
}

function addMeetingTable(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0) {
  const group = new THREE.Group()
  const topMat = envMaterial(theme.palette?.furniture || '#6f5238', 0.42, 0.2)
  const legMat = envMaterial(theme.palette?.furniture_light || '#8a6b4e', 0.55, 0.24)
  const tableLength = 6.0
  const tableWidth = 1.4

  const top = new THREE.Mesh(new THREE.BoxGeometry(tableLength, 0.1, tableWidth), topMat)
  top.position.y = 0.72
  top.castShadow = true
  top.receiveShadow = true
  group.add(top)
  for (const side of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.72, tableWidth * 0.72), legMat)
    leg.position.set(side * tableLength * 0.36, 0.36, 0)
    leg.castShadow = true
    group.add(leg)
  }

  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  environment?.add(group)
}

function addFurnitureItem(item: OfficeFurnitureItem, theme: OfficeEnvironmentTheme) {
  const x = item.position?.x ?? 0
  const z = item.position?.z ?? 0
  const rotationY = item.rotation_y ?? 0
  const accentColor = theme.palette?.accent || '#1677ff'

  switch (item.type) {
    case 'desk': {
      const { group } = createDesk(accentColor)
      group.position.set(x, 0, z)
      group.rotation.y = rotationY
      environment?.add(group)
      break
    }
    case 'office_chair':
      addOfficeChair(x, z, theme, rotationY)
      break
    case 'meeting_table':
      addMeetingTable(x, z, theme, rotationY)
      break
    case 'meeting_chair':
      addOfficeChair(x, z, theme, rotationY)
      break
    case 'plant':
      addPlant(x, z, theme)
      break
    case 'bookshelf':
      addBookshelf(x, z, theme, rotationY)
      break
    case 'coffee_bar':
      addCoffeeBar(x, z, theme, rotationY)
      break
    case 'lounge_sofa':
      addLounge(x, z, theme, rotationY)
      break
    case 'whiteboard':
      addWhiteboard(x, z, theme, rotationY)
      break
    case 'art':
      addArt(x, z, theme, rotationY, accentColor)
      break
    default:
      break
  }
}

function buildProps(theme: OfficeEnvironmentTheme, width: number, depth: number, _height: number) {
  if (!environment) return
  const configuredFurniture = officeFurniture()
  if (configuredFurniture.length) {
    const props = theme.props || {}
    const enabledByType: Record<string, boolean> = {
      plant: props.plants !== false,
      bookshelf: props.bookshelves !== false,
      coffee_bar: props.coffee_bar !== false,
      lounge_sofa: props.lounge !== false,
      whiteboard: props.whiteboard !== false,
      art: props.art !== false,
    }
    for (const item of configuredFurniture) {
      if (enabledByType[item.type] === false) continue
      addFurnitureItem(item, theme)
    }
    return
  }

  const props = theme.props || {}
  const foliageColor = theme.palette?.foliage || '#2f7d54'
  const accentColor = theme.palette?.accent || '#1677ff'

  if (props.plants !== false) {
    addPlant(-width / 2 + 0.85, -depth / 2 + 1.05, theme)
    addPlant(width / 2 - 0.85, -depth / 2 + 1.05, theme)
    addPlant(-width / 2 + 0.85, depth / 2 - 1.05, theme)
    addPlant(width / 2 - 0.85, depth / 2 - 1.05, theme)
  }

  if (props.bookshelves !== false) {
    addBookshelf(-width / 2 + 0.8, -2.6, theme)
    addBookshelf(-width / 2 + 0.8, 2.6, theme)
  }

  if (props.coffee_bar !== false) {
    addCoffeeBar(width / 2 - 1.0, 3.1, theme)
  }

  if (props.lounge !== false) {
    addLounge(width / 2 - 2.3, -4.2, theme)
  }

  if (props.whiteboard !== false) {
    addWhiteboard(-width / 2 + 0.16, -2.1, theme, Math.PI / 2)
  }

  if (props.art !== false) {
    addArt(width / 2 - 0.16, -1.2, theme, -Math.PI / 2, accentColor)
    addArt(width / 2 - 0.16, 1.6, theme, -Math.PI / 2, foliageColor)
  }
}

type MeetingBounds = { minX: number; maxX: number; minZ: number; maxZ: number }

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
  const slots = zone.slots || []
  if (slots.length) {
    const xs = slots.map((slot) => slot.position?.x ?? centerX)
    const zs = slots.map((slot) => slot.position?.z ?? centerZ)
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

type MeetingDoorSide = 'front' | 'back' | 'left' | 'right'

function createMeetingRoomShell(
  theme: OfficeEnvironmentTheme,
  center: THREE.Vector3,
  bounds: MeetingBounds,
  parent: THREE.Group,
  doorSide: MeetingDoorSide = 'front',
  doorWidth = 1.3,
  doorOffset = 0,
) {
  const wallHeight = 2.55
  const doorCenterX = center.x + doorOffset
  const doorCenterZ = center.z + doorOffset
  const doorHeight = 2.1
  const frameColor = theme.palette?.wall_lower || '#dce4e9'
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xbfe2f5,
    roughness: 0.08,
    metalness: 0.08,
    transparent: true,
    opacity: 0.26,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const frameMat = envMaterial(frameColor, 0.48, 0.22)
  const { minX, maxX, minZ, maxZ } = bounds

  const addFrontBackPanel = (fromX: number, toX: number, z: number) => {
    if (toX <= fromX) return
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(toX - fromX, wallHeight), glassMat)
    panel.position.set((fromX + toX) / 2, wallHeight / 2 + 0.05, z)
    panel.receiveShadow = true
    parent.add(panel)
  }

  const addSidePanel = (fromZ: number, toZ: number, x: number) => {
    if (toZ <= fromZ) return
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(toZ - fromZ, wallHeight), glassMat)
    panel.rotation.y = Math.PI / 2
    panel.position.set(x, wallHeight / 2 + 0.05, (fromZ + toZ) / 2)
    panel.receiveShadow = true
    parent.add(panel)
  }

  const frontGapStart = doorCenterX - doorWidth / 2
  const frontGapEnd = doorCenterX + doorWidth / 2
  const sideGapStart = doorCenterZ - doorWidth / 2
  const sideGapEnd = doorCenterZ + doorWidth / 2

  if (doorSide === 'back') {
    addFrontBackPanel(minX, frontGapStart, minZ)
    addFrontBackPanel(frontGapEnd, maxX, minZ)
    addSidePanel(minZ, maxZ, minX)
    addSidePanel(minZ, maxZ, maxX)
    addFrontBackPanel(minX, maxX, maxZ)
  } else if (doorSide === 'left') {
    addFrontBackPanel(minX, maxX, minZ)
    addFrontBackPanel(minX, maxX, maxZ)
    addSidePanel(minZ, sideGapStart, minX)
    addSidePanel(sideGapEnd, maxZ, minX)
    addSidePanel(minZ, maxZ, maxX)
  } else if (doorSide === 'right') {
    addFrontBackPanel(minX, maxX, minZ)
    addFrontBackPanel(minX, maxX, maxZ)
    addSidePanel(minZ, maxZ, minX)
    addSidePanel(minZ, sideGapStart, maxX)
    addSidePanel(sideGapEnd, maxZ, maxX)
  } else {
    addFrontBackPanel(minX, frontGapStart, maxZ)
    addFrontBackPanel(frontGapEnd, maxX, maxZ)
    addSidePanel(minZ, maxZ, minX)
    addSidePanel(minZ, maxZ, maxX)
    addFrontBackPanel(minX, maxX, minZ)
  }

  const postGeo = new THREE.BoxGeometry(0.09, wallHeight, 0.09)
  for (const x of [minX, maxX]) {
    for (const z of [minZ, maxZ]) {
      const post = new THREE.Mesh(postGeo, frameMat)
      post.position.set(x, wallHeight / 2, z)
      post.castShadow = true
      parent.add(post)
    }
  }

  const addDoorPosts = (edgeX: number, edgeZ: number, horizontal: boolean) => {
    for (const side of [-1, 1]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.09, doorHeight, 0.09), frameMat)
      if (horizontal) {
        post.position.set(doorCenterX + side * doorWidth / 2, doorHeight / 2, edgeZ)
      } else {
        post.position.set(edgeX, doorHeight / 2, doorCenterZ + side * doorWidth / 2)
      }
      post.castShadow = true
      parent.add(post)
    }
  }

  if (doorSide === 'front') {
    addDoorPosts(0, maxZ, true)
    const lintel = new THREE.Mesh(new THREE.BoxGeometry(doorWidth + 0.22, wallHeight - doorHeight, 0.08), frameMat)
    lintel.position.set(doorCenterX, doorHeight + (wallHeight - doorHeight) / 2, maxZ)
    parent.add(lintel)
  } else if (doorSide === 'back') {
    addDoorPosts(0, minZ, true)
    const lintel = new THREE.Mesh(new THREE.BoxGeometry(doorWidth + 0.22, wallHeight - doorHeight, 0.08), frameMat)
    lintel.position.set(doorCenterX, doorHeight + (wallHeight - doorHeight) / 2, minZ)
    parent.add(lintel)
  } else if (doorSide === 'left') {
    addDoorPosts(minX, 0, false)
    const lintel = new THREE.Mesh(new THREE.BoxGeometry(0.08, wallHeight - doorHeight, doorWidth + 0.22), frameMat)
    lintel.position.set(minX, doorHeight + (wallHeight - doorHeight) / 2, doorCenterZ)
    parent.add(lintel)
  } else {
    addDoorPosts(maxX, 0, false)
    const lintel = new THREE.Mesh(new THREE.BoxGeometry(0.08, wallHeight - doorHeight, doorWidth + 0.22), frameMat)
    lintel.position.set(maxX, doorHeight + (wallHeight - doorHeight) / 2, doorCenterZ)
    parent.add(lintel)
  }

  const addTopRailFrontBack = (fromX: number, toX: number, z: number) => {
    if (toX <= fromX) return
    const rail = new THREE.Mesh(new THREE.BoxGeometry(toX - fromX + 0.1, 0.1, 0.06), frameMat)
    rail.position.set((fromX + toX) / 2, wallHeight + 0.05, z)
    parent.add(rail)
  }

  const addTopRailSide = (fromZ: number, toZ: number, x: number) => {
    if (toZ <= fromZ) return
    const rail = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.1, toZ - fromZ + 0.1), frameMat)
    rail.position.set(x, wallHeight + 0.05, (fromZ + toZ) / 2)
    parent.add(rail)
  }

  if (doorSide === 'front') {
    addTopRailFrontBack(minX, frontGapStart, maxZ)
    addTopRailFrontBack(frontGapEnd, maxX, maxZ)
  } else {
    addTopRailFrontBack(minX, maxX, maxZ)
  }
  if (doorSide === 'back') {
    addTopRailFrontBack(minX, frontGapStart, minZ)
    addTopRailFrontBack(frontGapEnd, maxX, minZ)
  } else {
    addTopRailFrontBack(minX, maxX, minZ)
  }
  if (doorSide === 'left') {
    addTopRailSide(minZ, sideGapStart, minX)
    addTopRailSide(sideGapEnd, maxZ, minX)
  } else {
    addTopRailSide(minZ, maxZ, minX)
  }
  if (doorSide === 'right') {
    addTopRailSide(minZ, sideGapStart, maxX)
    addTopRailSide(sideGapEnd, maxZ, maxX)
  } else {
    addTopRailSide(minZ, maxZ, maxX)
  }
}

function meetingDoorSide(zone: OfficeZone, floor: { width: number; depth: number }): MeetingDoorSide {
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

function buildMeetingRoom(zone: OfficeZone) {
  if (!environment) return
  const theme = officeTheme()
  const floor = officeFloor()
  const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
  const bounds = meetingRoomBounds(zone)
  const doorSide = meetingDoorSide(zone, floor)
  const doorWidth = zone.door?.width ?? 1.3
  const doorOffset = zone.door?.offset ?? 0
  const doorCenterX = center.x + doorOffset
  const doorCenterZ = center.z + doorOffset
  const roomWidth = bounds.maxX - bounds.minX
  const roomDepth = bounds.maxZ - bounds.minZ
  const corridorWidth = 1.3
  const floorColor = theme.palette?.floor || '#d8c5a3'

  const roomFloor = new THREE.Mesh(new THREE.PlaneGeometry(roomWidth, roomDepth), envMaterial(floorColor, 0.9, 0.04))
  roomFloor.rotation.x = -Math.PI / 2
  roomFloor.position.set(center.x, 0.002, center.z)
  roomFloor.receiveShadow = true
  environment.add(roomFloor)

  const roomGrid = createRectangularGrid(
    roomWidth,
    roomDepth,
    Math.max(1, Math.round(Math.max(roomWidth, roomDepth))),
    floorColor,
    0.012,
  )
  roomGrid.position.x = center.x
  roomGrid.position.z = center.z
  environment.add(roomGrid)

  createMeetingRoomShell(theme, center, bounds, environment, doorSide, doorWidth, doorOffset)

  let mainEdge = 0
  let roomEdge = 0
  let horizontal = true
  if (doorSide === 'left') {
    roomEdge = bounds.minX
    mainEdge = floor.width / 2
    horizontal = true
  } else if (doorSide === 'right') {
    roomEdge = bounds.maxX
    mainEdge = -floor.width / 2
    horizontal = true
  } else if (doorSide === 'back') {
    roomEdge = bounds.minZ
    mainEdge = floor.depth / 2
    horizontal = false
  } else {
    roomEdge = bounds.maxZ
    mainEdge = -floor.depth / 2
    horizontal = false
  }

  const corridorFrom = Math.min(roomEdge, mainEdge)
  const corridorTo = Math.max(roomEdge, mainEdge)
  const corridorLength = corridorTo - corridorFrom
  if (corridorLength > 0.05) {
    const corridor = new THREE.Mesh(
      new THREE.PlaneGeometry(horizontal ? corridorLength : corridorWidth, horizontal ? corridorWidth : corridorLength),
      envMaterial(floorColor, 0.9, 0.04),
    )
    corridor.rotation.x = -Math.PI / 2
    corridor.position.set(
      horizontal ? (corridorFrom + corridorTo) / 2 : doorCenterX,
      0.002,
      horizontal ? doorCenterZ : (corridorFrom + corridorTo) / 2,
    )
    corridor.receiveShadow = true
    environment.add(corridor)

    const doorMat = envMaterial(theme.palette?.wall_lower || '#dce4e9', 0.52, 0.18)
    const mainDoor = new THREE.Mesh(
      horizontal
        ? new THREE.BoxGeometry(0.12, 2.1, corridorWidth)
        : new THREE.BoxGeometry(corridorWidth, 2.1, 0.12),
      doorMat,
    )
    mainDoor.position.set(
      horizontal ? mainEdge : doorCenterX,
      1.05,
      horizontal ? doorCenterZ : mainEdge,
    )
    environment.add(mainDoor)
  }

  createMeetingZone(zone)
}

function meetingSeatRotation(center: THREE.Vector3, position: THREE.Vector3, horizontal: boolean): number {
  const dx = position.x - center.x
  const dz = position.z - center.z
  if (horizontal) {
    if (Math.abs(dz) >= Math.abs(dx) * 0.8) return dz > 0 ? Math.PI : 0
    return dx > 0 ? -Math.PI / 2 : Math.PI / 2
  }
  if (Math.abs(dx) >= Math.abs(dz) * 0.8) return dx > 0 ? -Math.PI / 2 : Math.PI / 2
  return dz > 0 ? Math.PI : 0
}

function createMeetingZone(zone: OfficeZone) {
  if (!environment) return

  const theme = officeTheme()
  const group = new THREE.Group()
  group.name = `meeting-zone-${zone.id}`

  const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
  const bounds = meetingRoomBounds(zone)

  const carpetWidth = (bounds.maxX - bounds.minX) - 0.4
  const carpetDepth = (bounds.maxZ - bounds.minZ) - 0.4
  const carpet = new THREE.Mesh(
    new THREE.PlaneGeometry(carpetWidth, carpetDepth),
    envMaterial(theme.palette?.wall_lower || '#dce4e9', 0.92, 0.03),
  )
  carpet.rotation.x = -Math.PI / 2
  carpet.position.set(center.x, 0.015, center.z)
  carpet.receiveShadow = true
  group.add(carpet)

  const slots = zone.slots || []
  const slotXs = slots.length ? slots.map((slot) => slot.position?.x ?? center.x) : [center.x]
  const slotZs = slots.length ? slots.map((slot) => slot.position?.z ?? center.z) : [center.z]
  const minSlotX = Math.min(...slotXs)
  const maxSlotX = Math.max(...slotXs)
  const minSlotZ = Math.min(...slotZs)
  const maxSlotZ = Math.max(...slotZs)
  const horizontal = (maxSlotX - minSlotX) >= (maxSlotZ - minSlotZ)
  const tableLength = Math.max(2.0, (horizontal ? maxSlotX - minSlotX : maxSlotZ - minSlotZ) + 1.0)
  const tableWidth = 1.15

  const tableTop = new THREE.Mesh(
    new THREE.BoxGeometry(horizontal ? tableLength : tableWidth, 0.1, horizontal ? tableWidth : tableLength),
    envMaterial(theme.palette?.furniture || '#6f5238', 0.42, 0.2),
  )
  tableTop.position.set(center.x, 0.72, center.z)
  applyShadow(tableTop)
  group.add(tableTop)

  const legMat = envMaterial(theme.palette?.furniture_light || '#8a6b4e', 0.55, 0.24)
  if (horizontal) {
    for (const side of [-1, 1]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.72, tableWidth * 0.72), legMat)
      leg.position.set(center.x + side * tableLength * 0.36, 0.36, center.z)
      leg.castShadow = true
      group.add(leg)
    }
  } else {
    for (const side of [-1, 1]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(tableWidth * 0.72, 0.72, 0.12), legMat)
      leg.position.set(center.x, 0.36, center.z + side * tableLength * 0.36)
      leg.castShadow = true
      group.add(leg)
    }
  }

  const screen = new THREE.Mesh(
    new THREE.BoxGeometry(1.55, 0.92, 0.06),
    new THREE.MeshStandardMaterial({ color: 0x0a101c, emissive: 0x1a3448, emissiveIntensity: 0.85, roughness: 0.3, metalness: 0.3 }),
  )
  screen.position.set(center.x, 1.35, bounds.minZ + 0.14)
  screen.castShadow = true
  group.add(screen)

  const screenStand = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.62, 0.1), envMaterial(theme.palette?.furniture_light || '#8a6b4e', 0.55, 0.22))
  screenStand.position.set(center.x, 0.5, bounds.minZ + 0.14)
  group.add(screenStand)

  for (const slot of slots) {
    const position = slotPosition(slot)
    const rotation = meetingSeatRotation(center, position, horizontal)
    const chair = new THREE.Group()
    const chairFabric = envMaterial(theme.palette?.furniture_light || '#8a6b4e', 0.72, 0.06)
    const chairDark = envMaterial('#111822', 0.55, 0.22)
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.28, 0.05, 14), chairDark)
    base.position.y = 0.035
    base.castShadow = true
    chair.add(base)
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.045, 0.38, 8), chairDark)
    pole.position.y = 0.24
    chair.add(pole)
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.54, 0.1, 0.52), chairFabric)
    seat.position.y = 0.48
    seat.castShadow = true
    chair.add(seat)
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.54, 0.62, 0.1), chairFabric)
    back.position.set(0, 0.86, -0.22)
    back.castShadow = true
    chair.add(back)
    chair.position.set(position.x, 0, position.z)
    chair.rotation.y = rotation
    group.add(chair)
  }

  environment.add(group)
}

function disposeGroup(group: THREE.Group) {
  group.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    if (mesh.geometry) mesh.geometry.dispose()
    const material = (mesh as any).material
    if (Array.isArray(material)) material.forEach(disposeMaterial)
    else if (material) disposeMaterial(material)
  })
}

function createDesk(color: string): { group: THREE.Group; monitorMat: THREE.MeshStandardMaterial } {
  const group = new THREE.Group()
  const theme = officeTheme()
  const topMat = envMaterial(theme.palette?.furniture || '#26344a', 0.5, 0.16)
  const accentMat = envMaterial(color, 0.32, 0.18)
  const legMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.55, 0.18)
  const darkMat = envMaterial('#111822', 0.55, 0.22)
  const monitorMat = new THREE.MeshStandardMaterial({
    color: 0x0a101c, roughness: 0.28, metalness: 0.42,
    emissive: 0x05080f, emissiveIntensity: 0.25,
  })

  const top = new THREE.Mesh(new THREE.BoxGeometry(1.75, 0.08, 0.95), topMat)
  top.position.y = 0.73
  applyShadow(top)
  group.add(top)

  const sidePanelGeo = new THREE.BoxGeometry(0.1, 0.73, 0.78)
  for (const x of [-0.825, 0.825]) {
    const panel = new THREE.Mesh(sidePanelGeo, legMat)
    panel.position.set(x, 0.365, 0.02)
    panel.castShadow = true
    panel.receiveShadow = true
    group.add(panel)
  }

  const modesty = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.5, 0.06), darkMat)
  modesty.position.set(0, 0.44, -0.3)
  modesty.castShadow = true
  group.add(modesty)

  const drawer = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.2, 0.06), accentMat)
  drawer.position.set(0, 0.62, 0.42)
  group.add(drawer)
  const drawerHandle = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.03, 0.02), darkMat)
  drawerHandle.position.set(0, 0.62, 0.46)
  group.add(drawerHandle)

  const monitorStand = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.42, 0.16), darkMat)
  monitorStand.position.set(0, 0.91, -0.24)
  monitorStand.castShadow = true
  group.add(monitorStand)

  const monitor = new THREE.Mesh(new THREE.BoxGeometry(1.22, 0.72, 0.045), monitorMat)
  monitor.position.set(0, 1.28, -0.27)
  monitor.rotation.x = -0.05
  monitor.castShadow = true
  group.add(monitor)

  const keyboard = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.03, 0.18), envMaterial('#151c28', 0.6, 0.12))
  keyboard.position.set(0, 0.78, 0.26)
  keyboard.receiveShadow = true
  group.add(keyboard)

  const mouse = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 8), envMaterial('#151c28', 0.6, 0.12))
  mouse.position.set(0.42, 0.78, 0.3)
  mouse.receiveShadow = true
  group.add(mouse)

  const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 0.05, 14), darkMat)
  lampBase.position.set(-0.66, 0.8, -0.05)
  group.add(lampBase)
  const lampArm = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.38, 8), darkMat)
  lampArm.position.set(-0.66, 1.0, -0.05)
  group.add(lampArm)
  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.14, 12), envMaterial('#ffd166', 0.45, 0.12))
  lampHead.rotation.z = Math.PI / 2
  lampHead.position.set(-0.66, 1.16, -0.05)
  group.add(lampHead)

  const plantPot = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.075, 0.16, 10), envMaterial(theme.palette?.furniture_light || '#34455f', 0.5, 0.14))
  plantPot.position.set(0.72, 0.81, 0.28)
  group.add(plantPot)
  const plantBall = new THREE.Mesh(new THREE.SphereGeometry(0.13, 10, 8), envMaterial(theme.palette?.foliage || '#2f7d54', 0.8, 0.02))
  plantBall.position.set(0.72, 1.02, 0.28)
  plantBall.castShadow = true
  group.add(plantBall)

  const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.033, 0.08, 10), envMaterial('#e5e9f0', 0.6, 0.05))
  mug.position.set(-0.46, 0.81, 0.28)
  group.add(mug)

  const nameplate = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.07, 0.035), envMaterial(color, 0.4, 0.2))
  nameplate.position.set(0.28, 0.79, 0.46)
  group.add(nameplate)

  const chair = new THREE.Group()
  const chairFabric = envMaterial(theme.palette?.furniture_light || '#34455f', 0.72, 0.06)
  const chairDark = envMaterial('#111822', 0.55, 0.22)

  const chairBase = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.3, 0.06, 16), chairDark)
  chairBase.position.y = 0.04
  chairBase.castShadow = true
  chair.add(chairBase)
  const chairPole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.045, 0.4, 10), chairDark)
  chairPole.position.y = 0.26
  chair.add(chairPole)
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.1, 0.5), chairFabric)
  seat.position.y = 0.48
  seat.castShadow = true
  chair.add(seat)
  const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.62, 0.1), chairFabric)
  chairBack.position.set(0, 0.86, -0.24)
  chairBack.castShadow = true
  chair.add(chairBack)
  for (const x of [-0.3, 0.3]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.55, 0.16), chairFabric)
    arm.position.set(x, 0.66, 0.02)
    arm.castShadow = true
    chair.add(arm)
  }
  for (let i = 0; i < 5; i += 1) {
    const angle = (i / 5) * Math.PI * 2
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.03, 8), chairDark)
    wheel.position.set(Math.cos(angle) * 0.3, 0.015, Math.sin(angle) * 0.3)
    chair.add(wheel)
  }
  chair.position.set(0, 0, DESK_CHAIR_OFFSET)
  chair.rotation.y = Math.PI
  group.add(chair)

  return { group, monitorMat }
}

function makeLabelSprite(text: string, color: string) {
  const canvas = document.createElement('canvas')
  canvas.width = 320
  canvas.height = 80
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas 2d context unavailable')

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const radius = 16
  ctx.beginPath()
  ctx.moveTo(radius, 0)
  ctx.lineTo(canvas.width - radius, 0)
  ctx.quadraticCurveTo(canvas.width, 0, canvas.width, radius)
  ctx.lineTo(canvas.width, canvas.height - radius)
  ctx.quadraticCurveTo(canvas.width, canvas.height, canvas.width - radius, canvas.height)
  ctx.lineTo(radius, canvas.height)
  ctx.quadraticCurveTo(0, canvas.height, 0, canvas.height - radius)
  ctx.lineTo(0, radius)
  ctx.quadraticCurveTo(0, 0, radius, 0)
  ctx.closePath()
  ctx.fillStyle = 'rgba(8, 12, 20, 0.72)'
  ctx.fill()

  ctx.beginPath()
  ctx.arc(20, canvas.height / 2, 6, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.fill()

  ctx.font = 'bold 26px "Segoe UI", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#eaf0f8'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 40, canvas.height / 2)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false }),
  )
  sprite.scale.set(1.55, 0.39, 1)
  sprite.position.y = 2.22

  return { sprite, texture, canvas }
}

function makeBubbleSprite() {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 128
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas 2d context unavailable')

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false }),
  )
  sprite.scale.set(1.75, 0.44, 1)
  sprite.position.y = 1.58

  return { sprite, texture, canvas, ctx }
}

function drawBubble(actor: Actor, status: string, activity: string, message: string) {
  const ctx = actor.bubbleCtx
  const canvas = actor.bubbleCanvas
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const color = `#${new THREE.Color(statusColorHex(status)).getHexString()}`
  const statusText = statusTextFor(status)
  const detail = message || activity || ''
  let text = statusText
  if (detail && detail !== statusText) text = `${statusText} · ${detail}`
  if (text.length > 20) text = `${text.slice(0, 18)}…`

  const radius = 18
  ctx.beginPath()
  ctx.moveTo(radius, 0)
  ctx.lineTo(canvas.width - radius, 0)
  ctx.quadraticCurveTo(canvas.width, 0, canvas.width, radius)
  ctx.lineTo(canvas.width, canvas.height - radius)
  ctx.quadraticCurveTo(canvas.width, canvas.height, canvas.width - radius, canvas.height)
  ctx.lineTo(radius, canvas.height)
  ctx.quadraticCurveTo(0, canvas.height, 0, canvas.height - radius)
  ctx.lineTo(0, radius)
  ctx.quadraticCurveTo(0, 0, radius, 0)
  ctx.closePath()

  ctx.fillStyle = 'rgba(10, 16, 26, 0.86)'
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 4
  ctx.stroke()

  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(30, canvas.height / 2, 8, 0, Math.PI * 2)
  ctx.fill()

  ctx.font = 'bold 38px "Segoe UI", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#f3f6fb'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 52, canvas.height / 2)

  actor.bubbleTexture.needsUpdate = true
}
function createCharacter(colleague: any, position: THREE.Vector3) {
  const group = new THREE.Group()
  const charColor = new THREE.Color(colleague.color || '#1677ff')
  const skinColor = new THREE.Color('#f0c9a1')
  const bodyMat = new THREE.MeshStandardMaterial({ color: charColor, roughness: 0.72, metalness: 0.03 })
  const skinMat = new THREE.MeshStandardMaterial({ color: skinColor, roughness: 0.82, metalness: 0.01 })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x1d2530, roughness: 0.78, metalness: 0.04 })
  const shoeMat = new THREE.MeshStandardMaterial({ color: 0x11151c, roughness: 0.86, metalness: 0.04 })

  // 头：方块脸
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.52, 0.52), skinMat)
  head.position.y = 1.06
  head.castShadow = true
  group.add(head)

  // 身体：主题色方块上衣
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.64, 0.36), bodyMat)
  body.position.y = 0.48
  body.castShadow = true
  group.add(body)

  // 手臂
  const armGeo = new THREE.BoxGeometry(0.14, 0.5, 0.18)
  const armL = new THREE.Mesh(armGeo, bodyMat)
  armL.position.set(-0.36, 0.5, 0)
  armL.castShadow = true
  group.add(armL)
  const armR = new THREE.Mesh(armGeo, bodyMat)
  armR.position.set(0.36, 0.5, 0)
  armR.castShadow = true
  group.add(armR)

  // 腿
  const legGeo = new THREE.BoxGeometry(0.18, 0.18, 0.2)
  const legL = new THREE.Mesh(legGeo, shoeMat)
  legL.position.set(-0.16, 0.09, 0)
  group.add(legL)
  const legR = new THREE.Mesh(legGeo, shoeMat)
  legR.position.set(0.16, 0.09, 0)
  group.add(legR)

  // 脸：方块眼 + 细长嘴
  const faceZ = 0.275
  const eyeGeo = new THREE.BoxGeometry(0.1, 0.1, 0.03)
  const eyeL = new THREE.Mesh(eyeGeo, darkMat)
  eyeL.position.set(0.13, 1.13, faceZ)
  group.add(eyeL)
  const eyeR = new THREE.Mesh(eyeGeo, darkMat)
  eyeR.position.set(-0.13, 1.13, faceZ)
  group.add(eyeR)

  const mouth = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.035, 0.02), darkMat)
  mouth.position.set(0, 0.92, faceZ)
  group.add(mouth)

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.5, 0.6, 32),
    new THREE.MeshBasicMaterial({
      color: charColor,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  )
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.02
  ring.visible = false
  group.add(ring)

  const indicatorMat = new THREE.MeshBasicMaterial({ color: statusColorHex('idle'), transparent: true, opacity: 0.9 })
  const indicator = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 12), indicatorMat)
  indicator.position.y = 1.62
  group.add(indicator)

  group.position.copy(position)
  group.userData.roleKey = colleague.role_key
  group.traverse((child) => {
    child.userData.roleKey = colleague.role_key
  })

  return {
    group, ring, indicator, indicatorMat,
    mixer: null, idleAction: null, walkAction: null, sitAction: null,
    halfDepth: 0.18, modelScale: 1, seatY: 0,
    armL, armR, legL, legR,
  }
}
function createCharacterFromTemplate(colleague: any, position: THREE.Vector3, template: CharacterTemplate) {
  const group = new THREE.Group()
  const charColor = new THREE.Color(colleague.color || '#1677ff')
  const model = cloneSkeleton(template.scene)
  const targetHeight = 1.42
  const scale = targetHeight / (template.height || 2.5)

  model.scale.setScalar(scale)
  model.rotation.y = template.frontRotation

  model.traverse((child: THREE.Object3D) => {
    child.userData.roleKey = colleague.role_key
    const mesh = child as THREE.Mesh
    if (mesh.isMesh) {
      mesh.castShadow = true
      mesh.receiveShadow = true
    }
  })
  group.add(model)

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.5, 0.6, 32),
    new THREE.MeshBasicMaterial({
      color: charColor,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  )
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.02
  ring.visible = false
  group.add(ring)

  const indicatorMat = new THREE.MeshBasicMaterial({ color: statusColorHex('idle'), transparent: true, opacity: 0.9 })
  const indicator = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 12), indicatorMat)
  indicator.position.y = 1.62
  group.add(indicator)

  const mixer = new THREE.AnimationMixer(model)
  const idleClip = template.animations.find((clip) => (clip.name || '').toLowerCase() === 'idle') || null
  const walkClip = template.animations.find((clip) => (clip.name || '').toLowerCase() === 'walk') || null
  const sitClip = template.animations.find((clip) => (clip.name || '').toLowerCase() === 'sit') || null
  const idleAction = idleClip ? mixer.clipAction(idleClip) : null
  let walkAction: THREE.AnimationAction | null = null
  if (walkClip) {
    const groundedTracks = walkClip.tracks.filter((track) => {
      const trackName = track.name || ''
      const targetNode = trackName.split('.')[0]
      const isPosition = trackName.includes('.position')
      return !(targetNode === 'root' && isPosition)
    })
    const groundedClip = new THREE.AnimationClip(`${walkClip.name}-grounded`, walkClip.duration, groundedTracks)
    walkAction = mixer.clipAction(groundedClip)
  }
  const sitAction = sitClip ? mixer.clipAction(sitClip) : null
  idleAction?.play()

  group.position.copy(position)
  group.userData.roleKey = colleague.role_key
  group.traverse((child) => {
    child.userData.roleKey = colleague.role_key
  })

  return {
    group, ring, indicator, indicatorMat,
    mixer, idleAction, walkAction, sitAction,
    halfDepth: (template.depth * scale) / 2, modelScale: scale, seatY: 0,
    armL: null, armR: null, legL: null, legR: null,
  }
}

function rebuildActors() {
  const activeScene = scene
  if (!activeScene) return

  for (const actor of actorMap.values()) {
    actor.mixer?.stopAllAction()
    activeScene.remove(actor.group)
    disposeActor(actor)
  }
  actorMap.clear()

  const assignments = deskSlotAssignments()

  props.colleagues.forEach((colleague, index) => {
    const assignment = assignments.get(colleague.role_key) || fallbackDeskSlot(index)
    if (!assignment) return

    const { slot } = assignment
    const deskPosition = slotPosition(slot)
    const forward = slotForward(slot)
    const right = slotRight(slot)
    const desk = createDesk(colleague.color || '#1677ff')
    desk.group.position.copy(deskPosition)
    desk.group.rotation.y = slotRotationY(slot)

    const characterHome = deskPosition.clone().addScaledVector(forward, DESK_IDLE_DISTANCE)
    const template = characterTemplates.length
      ? characterTemplates[index % characterTemplates.length]
      : null
    const character = template
      ? createCharacterFromTemplate(colleague, characterHome, template)
      : createCharacter(colleague, characterHome)

    const group = new THREE.Group()
    group.name = `ai-colleague-${colleague.role_key}`
    group.userData.roleKey = colleague.role_key
    group.add(desk.group)

    const bubble = makeBubbleSprite()
    bubble.sprite.userData.roleKey = colleague.role_key
    character.group.add(bubble.sprite)
    group.add(character.group)

    const label = makeLabelSprite(colleague.name || colleague.role_key, colleague.color || '#1677ff')
    label.sprite.userData.roleKey = colleague.role_key
    character.group.add(label.sprite)

    activeScene.add(group)

    actorMap.set(colleague.role_key, {
      roleKey: colleague.role_key,
      group,
      character: character.group,
      desk: desk.group,
      indicator: character.indicator,
      indicatorMat: character.indicatorMat,
      monitorMat: desk.monitorMat,
      selectionRing: character.ring,
      basePosition: deskPosition.clone(),
      phase: slotPhase(slot),
      status: 'idle',
      bubble: bubble.sprite,
      label: label.sprite,
      bubbleTexture: bubble.texture,
      bubbleCanvas: bubble.canvas,
      bubbleCtx: bubble.ctx,
      targetPosition: characterHome.clone(),
      route: [],
      routeIndex: 0,
      walkTarget: characterHome.clone(),
      walking: false,
      mixer: character.mixer,
      idleAction: character.idleAction,
      walkAction: character.walkAction,
      sitAction: character.sitAction,
      halfDepth: character.halfDepth,
      modelScale: character.modelScale,
      seatY: character.seatY,
      armL: character.armL,
      armR: character.armR,
      legL: character.legL,
      legR: character.legR,
      forward,
      right,
      homeZoneId: assignment.zone.id,
      homeSlot: slot,
      currentZoneId: assignment.zone.id,
    })
  })

  applyStatuses()
  updateSelection()
}

function applyStatuses() {
  for (const actor of actorMap.values()) {
    updateActorStatus(actor, props.statusMap[actor.roleKey])
  }
}

function assignmentActionFor(event?: OfficeColleagueStatus): string {
  const actionMap = behaviorConfigValue().mission?.assignment_action_map || {}
  const assignmentStatus = event?.assignment_status || ''
  return typeof actionMap[assignmentStatus] === 'string' ? actionMap[assignmentStatus] : ''
}

function updateActorStatus(actor: Actor, event?: OfficeColleagueStatus) {
  const status = event?.status || 'idle'
  const activity = event?.activity || ''
  const message = event?.message || ''
  actor.status = status
  const meta = statusMetaFor(status)
  const hex = statusColorHex(status)
  actor.indicatorMat.color.setHex(hex)

  if (meta.monitor_active) {
    actor.monitorMat.emissive = new THREE.Color(hex)
    actor.monitorMat.emissiveIntensity = 0.75
  } else {
    actor.monitorMat.emissive = new THREE.Color(0x05080f)
    actor.monitorMat.emissiveIntensity = 0.25
  }

  actor.indicatorMat.opacity = typeof meta.indicator_opacity === 'number' ? meta.indicator_opacity : 0.9

  updateActorTarget(actor, status, event)
  drawBubble(actor, status, activity, message)
}

function updateActorTarget(actor: Actor, status: string, event?: OfficeColleagueStatus) {
  const targetZone = resolveZoneForStatus(actor.roleKey, status, event)
  const action = assignmentActionFor(event)

  if (action === 'return_to_desk' || action === 'sit_idle' || action === 'show_error') {
    setHomeDeskTarget(actor, status)
  } else if (targetZone?.type === 'meeting') {
    setMeetingTarget(actor, targetZone)
  } else if (targetZone?.walk_target === 'center') {
    setOfficeCenterTarget(actor, targetZone)
  } else if (targetZone?.walk_target === 'slot' || action === 'walk_to_target') {
    setDeskRouteTarget(actor, targetZone)
  } else {
    setHomeDeskTarget(actor, status)
  }

  rebuildActorRoute(actor, targetZone)
}

function setHomeDeskTarget(actor: Actor, status: string) {
  const animation = statusMetaFor(status).animation || 'idle'
  const base = actor.basePosition
  const forward = actor.forward
  const right = actor.right

  if (animation === 'working' && actor.sitAction) {
    const chairPosition = base.clone().addScaledVector(forward, DESK_CHAIR_OFFSET)
    const backReachWorld = SIT_BACK_LOCAL_Z * actor.modelScale
    const backOffset = Math.max(0, CHAIR_SEAT_BACK_OFFSET - backReachWorld)
    actor.seatY = CHAIR_SEAT_HEIGHT - SIT_HIP_LOCAL_Y * actor.modelScale
    actor.targetZoneType = 'desk_work'
    actor.targetPosition = chairPosition
      .clone()
      .addScaledVector(forward, backOffset)
  } else {
    actor.seatY = 0
    actor.targetZoneType = null
    if (animation === 'working') {
      actor.targetPosition = base.clone().addScaledVector(forward, DESK_WORK_DISTANCE)
    } else if (animation === 'waiting') {
      actor.targetPosition = base
        .clone()
        .addScaledVector(forward, DESK_WAIT_DISTANCE)
        .addScaledVector(right, DESK_WAIT_SIDE)
    } else {
      actor.targetPosition = base.clone().addScaledVector(forward, DESK_IDLE_DISTANCE)
    }
  }

  actor.phase = slotPhase(actor.homeSlot)
  actor.currentZoneId = actor.homeZoneId
}

function setMeetingTarget(actor: Actor, targetZone: OfficeZone) {
  const slot = meetingSlotForActor(targetZone, actor.roleKey)
  const chairPosition = slotPosition(slot)
  const zoneCenter = new THREE.Vector3(targetZone.position?.x ?? 0, 0, targetZone.position?.z ?? 0)
  const away = chairPosition.clone().sub(zoneCenter)
  if (away.lengthSq() < 0.001) away.set(0, 0, 1)
  away.normalize()

  actor.targetZoneType = 'meeting'
  if (actor.sitAction) {
    actor.seatY = CHAIR_SEAT_HEIGHT - SIT_HIP_LOCAL_Y * actor.modelScale
    const backReachWorld = SIT_BACK_LOCAL_Z * actor.modelScale
    actor.targetPosition = chairPosition
      .clone()
      .addScaledVector(away, CHAIR_SEAT_BACK_OFFSET - backReachWorld)
  } else {
    actor.seatY = 0
    const standDistance = MEETING_CHAIR_BACK_REACH + actor.halfDepth + MEETING_STAND_GAP
    actor.targetPosition = chairPosition.clone().addScaledVector(away, standDistance)
  }
  actor.phase = meetingPhaseForSlot(targetZone, slot)
  actor.currentZoneId = targetZone.id
}

function deskRouteSlotForActor(actor: Actor, targetZone: OfficeZone | null): OfficeZoneSlot {
  const slots = targetZone?.slots || []
  if (!slots.length) return actor.homeSlot
  const alternatives = slots.filter((slot) => slot.id !== actor.homeSlot.id)
  const pool = alternatives.length ? alternatives : slots
  return pool[hashRoleKey(actor.roleKey) % pool.length]
}

function setDeskRouteTarget(actor: Actor, targetZone: OfficeZone | null) {
  const zone = targetZone || zoneById(actor.homeZoneId)
  const slot = deskRouteSlotForActor(actor, zone)
  const position = slotPosition(slot)
  actor.seatY = 0
  actor.targetZoneType = zone?.type || null
  actor.targetPosition = position.clone().addScaledVector(slotForward(slot), DESK_IDLE_DISTANCE)
  actor.phase = slotPhase(slot)
  actor.currentZoneId = zone?.id || actor.homeZoneId
}

function setOfficeCenterTarget(actor: Actor, targetZone: OfficeZone | null) {
  const zone = targetZone || zoneById(actor.homeZoneId)
  const center = zone?.position
    ? new THREE.Vector3(zone.position.x ?? 0, 0, zone.position.z ?? 0)
    : actor.basePosition.clone()
  actor.seatY = 0
  actor.targetZoneType = zone?.type || null
  actor.targetPosition = center
  actor.phase = slotPhase(actor.homeSlot)
  actor.currentZoneId = zone?.id || actor.homeZoneId
}

function clampPointToFloor(point: THREE.Vector3): THREE.Vector3 {
  const workspace = officeWorkspace()
  const margin = 0.45
  const halfWidth = Math.max(0.1, workspace.width / 2 - margin)
  const halfDepth = Math.max(0.1, workspace.depth / 2 - margin)
  return new THREE.Vector3(
    Math.max(-halfWidth, Math.min(halfWidth, point.x)),
    0,
    Math.max(-halfDepth, Math.min(halfDepth, point.z)),
  )
}

function meetingDoorWaypoints(targetZone: OfficeZone): THREE.Vector3[] {
  const floor = officeFloor()
  const bounds = meetingRoomBounds(targetZone)
  const side = meetingDoorSide(targetZone, floor)
  const center = new THREE.Vector3(targetZone.position?.x ?? 0, 0, targetZone.position?.z ?? 0)
  const doorOffset = targetZone.door?.offset ?? 0
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
}

function rebuildActorRoute(actor: Actor, targetZone: OfficeZone | null) {
  const target = clampPointToFloor(actor.targetPosition)
  if (targetZone?.type === 'meeting') {
    actor.route = [...meetingDoorWaypoints(targetZone).map(clampPointToFloor), target]
  } else {
    actor.route = [target]
  }
  actor.routeIndex = 0
  actor.walkTarget = actor.route[0] || target
}

function updateSelection() {
  for (const actor of actorMap.values()) {
    actor.selectionRing.visible = actor.roleKey === props.selectedRoleKey
    actor.label.visible = actor.roleKey === props.selectedRoleKey
  }
}

function actorAtPointer(clientX: number, clientY: number): string | null {
  if (!scene || !camera || !renderer) return null

  const rect = renderer.domElement.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return null

  const pointer = new THREE.Vector2(
    ((clientX - rect.left) / rect.width) * 2 - 1,
    -((clientY - rect.top) / rect.height) * 2 + 1,
  )

  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(pointer, camera)

  const targets: THREE.Object3D[] = []
  for (const actor of actorMap.values()) {
    targets.push(actor.group)
  }

  const intersections = raycaster.intersectObjects(targets, true)
  if (!intersections.length) return null

  let node: THREE.Object3D | null = intersections[0].object
  while (node) {
    if (node.userData?.roleKey) return node.userData.roleKey
    node = node.parent
  }
  return null
}

function onPointerDown(event: PointerEvent) {
  pointerDown = { x: event.clientX, y: event.clientY }
}

function onPointerMove(event: PointerEvent) {
  if (!pointerDown) return
  const dx = Math.abs(event.clientX - pointerDown.x)
  const dy = Math.abs(event.clientY - pointerDown.y)
  if (dx > 5 || dy > 5) {
    followRoleKey = null
  }
}

function onPointerUp(event: PointerEvent) {
  const dx = Math.abs(event.clientX - pointerDown.x)
  const dy = Math.abs(event.clientY - pointerDown.y)

  if (dx > 5 || dy > 5) return
  pickActor(event.clientX, event.clientY)
}

function pickActor(clientX: number, clientY: number) {
  const roleKey = actorAtPointer(clientX, clientY)
  if (!roleKey) return
  followRoleKey = roleKey
  emit('select', roleKey)
}

function tick(time: number) {
  if (disposed || !scene || !camera || !renderer) return

  const t = time / 1000
  const delta = lastFrameTime ? Math.min((time - lastFrameTime) / 1000, 0.1) : 0
  lastFrameTime = time

  if (controls && followRoleKey) {
    const followActor = actorMap.get(followRoleKey)
    if (followActor) {
      const followTarget = followActor.character.position.clone().add(new THREE.Vector3(0, 1.05, 0))
      controls.target.lerp(followTarget, 0.08)
    }
  }

  controls?.update()

  for (const actor of actorMap.values()) {
    const phase = actor.phase
    const status = actor.status
    const animation = statusMetaFor(status).animation || 'idle'
    const sitting = (actor.targetZoneType === 'meeting' || actor.targetZoneType === 'desk_work') && actor.sitAction && !actor.walking

    let moveDirX = 0
    let moveDirZ = 0
    let walking = false
    if (actor.route.length) {
      const waypoint = actor.walkTarget
      const dx = waypoint.x - actor.character.position.x
      const dz = waypoint.z - actor.character.position.z
      const distance = Math.hypot(dx, dz)
      const step = WALK_SPEED * delta

      if (distance > 0.03) {
        walking = true
        moveDirX = dx
        moveDirZ = dz
        if (step >= distance) {
          actor.character.position.x = waypoint.x
          actor.character.position.z = waypoint.z
          actor.routeIndex += 1
          if (actor.routeIndex < actor.route.length) {
            actor.walkTarget = actor.route[actor.routeIndex]
          } else {
            actor.route = []
            actor.walkTarget = actor.targetPosition
            walking = false
          }
        } else {
          actor.character.position.x += (dx / distance) * step
          actor.character.position.z += (dz / distance) * step
        }
      } else {
        actor.character.position.x = waypoint.x
        actor.character.position.z = waypoint.z
        actor.routeIndex += 1
        if (actor.routeIndex < actor.route.length) {
          actor.walkTarget = actor.route[actor.routeIndex]
        } else {
          actor.route = []
          actor.walkTarget = actor.targetPosition
        }
      }
    }
    actor.walking = walking

    let rotationY = phase
    let bobY = 0
    let indicatorScale = 1

    if (actor.walking) {
      rotationY = Math.atan2(moveDirX, moveDirZ)
      bobY = Math.sin(t * 3.2 + phase) * 0.008
    } else if (animation === 'working' && !sitting) {
      rotationY = phase + Math.sin(t * 0.7 + phase) * 0.16
      bobY = Math.sin(t * 3.2 + phase) * 0.015
      indicatorScale = 1 + Math.sin(t * 5 + phase) * 0.12
    } else if (animation === 'waiting') {
      bobY = Math.sin(t * 2.4 + phase) * 0.02
      indicatorScale = 1 + Math.sin(t * 4.2 + phase) * 0.22
    } else if (animation === 'error') {
      rotationY = phase + Math.sin(t * 1.2 + phase) * 0.08
      indicatorScale = 1 + Math.sin(t * 6 + phase) * 0.18
    } else if (animation === 'done') {
      indicatorScale = 1
    } else if (sitting) {
      rotationY = phase
      bobY = 0
      indicatorScale = 1
    } else {
      rotationY = phase + Math.sin(t * 0.35 + phase) * 0.06
      bobY = Math.sin(t * 1.6 + phase) * 0.01
      indicatorScale = 1 + Math.sin(t * 2 + phase) * 0.08
    }

    actor.character.rotation.y = rotationY
    actor.character.position.y = sitting ? actor.seatY : bobY
    actor.indicator.scale.setScalar(indicatorScale)

    if (!actor.mixer) {
      const swing = actor.walking ? Math.sin(t * 9) * 0.5 : 0
      if (actor.armL) actor.armL.rotation.x = swing
      if (actor.armR) actor.armR.rotation.x = -swing
      if (actor.legL) actor.legL.rotation.x = -swing * 0.8
      if (actor.legR) actor.legR.rotation.x = swing * 0.8
    }

    if (actor.mixer) {
      if (actor.walking && actor.walkAction && !actor.walkAction.isRunning()) {
        actor.walkAction.reset().play()
        actor.idleAction?.stop()
        actor.sitAction?.stop()
      } else if (!actor.walking && sitting && actor.sitAction && !actor.sitAction.isRunning()) {
        actor.sitAction.reset().play()
        actor.idleAction?.stop()
        actor.walkAction?.stop()
      } else if (!actor.walking && !sitting && actor.idleAction && !actor.idleAction.isRunning()) {
        actor.idleAction.reset().play()
        actor.walkAction?.stop()
        actor.sitAction?.stop()
      }
      actor.mixer.update(delta)
    }
  }

  renderer.render(scene, camera)
  if (!document.hidden) {
    rafId = requestAnimationFrame(tick)
  } else {
    renderLoopRunning = false
  }
}

function disposeActor(actor: Actor) {
  actor.group.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    if (mesh.geometry) mesh.geometry.dispose()
    const material = (mesh as any).material
    if (Array.isArray(material)) material.forEach(disposeMaterial)
    else if (material) disposeMaterial(material)
  })
}

function disposeMaterial(material: THREE.Material) {
  const anyMat = material as any
  for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'alphaMap']) {
    anyMat[key]?.dispose?.()
  }
  material.dispose()
}

function dispose() {
  disposed = true
  stopRenderLoop()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  resizeObserver?.disconnect()
  resizeObserver = null

  if (renderer) {
    renderer.domElement.removeEventListener('pointerdown', onPointerDown)
    renderer.domElement.removeEventListener('pointermove', onPointerMove)
    renderer.domElement.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
  }

  for (const actor of actorMap.values()) {
    disposeActor(actor)
  }
  actorMap.clear()

  if (environment) {
    environment.traverse((obj) => {
      const mesh = obj as THREE.Mesh
      if (mesh.geometry) mesh.geometry.dispose()
      const material = (mesh as any).material
      if (Array.isArray(material)) material.forEach(disposeMaterial)
      else if (material) disposeMaterial(material)
    })
    environment = null
  }

  controls?.dispose()
  controls = null
  renderer?.dispose()
  const canvas = renderer?.domElement
  if (canvas?.parentNode) canvas.parentNode.removeChild(canvas)
  renderer = null
  scene = null
  camera = null
}
</script>

<style scoped>
.office-3d-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: block;
  cursor: grab;
}

.office-3d-canvas:active {
  cursor: grabbing;
}
</style>













