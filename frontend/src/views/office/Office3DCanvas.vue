<template>
  <Teleport to="body" :disabled="!isFullscreen">
    <div class="office-3d-wrap" :class="{ 'office-3d-wrap--fullscreen': isFullscreen }">
      <div ref="containerRef" class="office-3d-canvas" :class="canvasCursorClass"></div>
      <pre v-if="debugOn" class="office-3d-debug" style="position:absolute;right:8px;bottom:8px;margin:0;padding:6px 8px;background:rgba(0,0,0,.55);color:#8ef59a;font:12px/1.5 ui-monospace,Consolas,monospace;z-index:40;pointer-events:none;white-space:pre-wrap">{{ debugText }}</pre>

      <div v-if="editable && !editing" class="office-3d-enter">
        <a-button size="small" type="primary" @click="toggleEdit">编辑空间</a-button>
      </div>

      <template v-if="editable && editing">
        <div class="office-3d-topbar">
          <div class="office-3d-toolgroup">
            <button type="button" class="office-3d-tool office-3d-tool--save" title="完成并保存 (Esc)" @click="saveAndExit"><CheckOutlined /><span>完成并保存</span></button>
            <button type="button" class="office-3d-tool" title="放弃本次编辑" @click="cancelAndExit"><CloseOutlined /><span>取消</span></button>
          </div>

          <span class="office-3d-topbar-sep"></span>

          <div class="office-3d-toolgroup">
            <button type="button" class="office-3d-tool" :disabled="!canUndo" title="撤销 (Ctrl+Z)" @click="undo"><UndoOutlined /></button>
            <button type="button" class="office-3d-tool" :disabled="!canRedo" title="重做 (Ctrl+Shift+Z)" @click="redo"><RedoOutlined /></button>
          </div>

          <span class="office-3d-topbar-sep"></span>

          <div class="office-3d-toolgroup office-3d-toolgroup--tools">
            <button type="button" class="office-3d-tool" :class="{ 'is-active': !panMode && !armedType && !armedRoom }" title="选择 (V)" @click="onSelectTool"><SelectOutlined /><span>选择</span></button>
            <button type="button" class="office-3d-tool" :class="{ 'is-active': panMode }" title="平移 (H)" @click="setPanMode(!panMode)"><DragOutlined /><span>平移</span></button>
            <button type="button" class="office-3d-tool" :class="{ 'is-active': rotateMode }" :disabled="!selected" title="旋转 (R)" @click="toggleRotate"><RotateRightOutlined /><span>旋转</span></button>
            <button type="button" class="office-3d-tool" :disabled="!selected" title="翻转 (180°) 翻面" @click="flipSelected"><SwapOutlined /><span>翻转</span></button>
            <button type="button" class="office-3d-tool office-3d-tool--danger" :disabled="!selected" title="删除 (Del)" @click="removeSelected"><DeleteOutlined /><span>删除</span></button>
          </div>

          <span class="office-3d-topbar-sep"></span>

          <div class="office-3d-toolgroup">
            <button type="button" class="office-3d-tool" :class="{ 'is-active': !view3D }" title="2D 平面编辑" @click="setView('2d')"><AppstoreOutlined /><span>2D</span></button>
            <button type="button" class="office-3d-tool" :class="{ 'is-active': view3D }" title="3D 预览" @click="setView('3d')"><HomeOutlined /><span>3D</span></button>
          </div>

          <span class="office-3d-topbar-sep"></span>

          <div class="office-3d-toolgroup">
            <button type="button" class="office-3d-tool" title="缩小" @click="zoomOut"><ZoomOutOutlined /></button>
            <span class="office-3d-zoom-pct">{{ Math.round(zoomPct) }}%</span>
            <button type="button" class="office-3d-tool" title="放大" @click="zoomIn"><ZoomInOutlined /></button>
            <button type="button" class="office-3d-tool" title="适配视图" @click="ensureFit"><ExpandOutlined /></button>
            <button type="button" class="office-3d-tool" title="全屏" @click="toggleFullscreen"><FullscreenOutlined /><span>{{ isFullscreen ? '退出全屏' : '全屏' }}</span></button>
          </div>
        </div>

        <div class="office-3d-side">
          <div class="office-3d-side-tabs">
            <button type="button" class="office-3d-side-tab" :class="{ 'is-active': sideTab === 'build' }" @click="sideTab = 'build'">建筑</button>
            <button type="button" class="office-3d-side-tab" :class="{ 'is-active': sideTab === 'rooms' }" @click="sideTab = 'rooms'">房间</button>
            <button type="button" class="office-3d-side-tab" :class="{ 'is-active': sideTab === 'objects' }" @click="sideTab = 'objects'">物品</button>
          </div>

          <div v-if="sideTab === 'build'" class="office-3d-side-body">
            <div class="office-3d-side-section">工具</div>
            <button type="button" class="office-3d-side-row" :class="{ 'is-active': !panMode && !armedType && !armedRoom }" @click="onSelectTool"><SelectOutlined /><span class="office-3d-side-row-main"><b>选择</b><i>点击选择元素 (V)</i></span></button>
            <button type="button" class="office-3d-side-row" :class="{ 'is-active': panMode }" @click="setPanMode(!panMode)"><DragOutlined /><span class="office-3d-side-row-main"><b>平移</b><i>拖动画布 (H)</i></span></button>
            <button type="button" class="office-3d-side-row" :class="{ 'is-active': rotateMode }" :disabled="!selected" @click="toggleRotate"><RotateRightOutlined /><span class="office-3d-side-row-main"><b>旋转</b><i>旋转选中元素 (R)</i></span></button>
            <button type="button" class="office-3d-side-row" :disabled="!selected" @click="flipSelected"><SwapOutlined /><span class="office-3d-side-row-main"><b>翻转</b><i>翻转 180° 翻面</i></span></button>
            <button type="button" class="office-3d-side-row office-3d-side-row--danger" :disabled="!selected" @click="removeSelected"><DeleteOutlined /><span class="office-3d-side-row-main"><b>删除</b><i>删除选中元素 (Del)</i></span></button>
            <div class="office-3d-side-section">历史</div>
            <button type="button" class="office-3d-side-row" :disabled="!canUndo" @click="undo"><UndoOutlined /><span class="office-3d-side-row-main"><b>撤销</b><i>Ctrl+Z</i></span></button>
            <button type="button" class="office-3d-side-row" :disabled="!canRedo" @click="redo"><RedoOutlined /><span class="office-3d-side-row-main"><b>重做</b><i>Ctrl+Shift+Z</i></span></button>
          </div>

          <div v-else-if="sideTab === 'rooms'" class="office-3d-side-body">
            <div class="office-3d-side-section">放置</div>
            <button type="button" class="office-3d-side-row office-3d-side-row--room" :class="{ 'is-active': armedRoom }" @click="onPlaceRoom"><InboxOutlined /><span class="office-3d-side-row-main"><b>空白房间</b><i>点击画布放置房间</i></span></button>
          </div>

          <div v-else class="office-3d-side-body">
            <div class="office-3d-side-search"><SearchOutlined /><input v-model="assetQuery" placeholder="搜索物品…" /></div>
            <div v-for="g in groupedCatalog" :key="g.category" class="office-3d-side-group">
              <div class="office-3d-side-section office-3d-side-section--group"><component :is="categoryIcon(g.category)" /><span>{{ g.label }}</span></div>
              <button
                v-for="c in g.items"
                :key="c.type"
                type="button"
                class="office-3d-side-row"
                :class="{ 'is-active': armedType === c.type }"
                :title="'放置 ' + c.label"
                @click="onPlaceAsset(c.type)"
              >
                <component :is="categoryIcon(g.category)" />
                <span class="office-3d-side-row-main"><b>{{ c.label }}</b><i>点击放置</i></span>
              </button>
            </div>
          </div>
        </div>

        <div v-if="selected" class="office-3d-props" :class="{ 'office-3d-props--hidden': view3D }">
          <template v-if="selected.kind !== 'room'">
            <div class="office-3d-props-title">已选中：{{ selected.item?.type || '席位' }}</div>
            <label>X <input type="number" step="0.5" :value="selected.item?.position?.x ?? 0" @change="onSelChange('x', $event)" /></label>
            <label>Z <input type="number" step="0.5" :value="selected.item?.position?.z ?? 0" @change="onSelChange('z', $event)" /></label>
            <label>旋转 <input type="number" step="90" :value="Math.round(((selected.item?.rotation_y ?? 0) * 180) / Math.PI)" @change="onSelChange('rot', $event)" /></label>
            <label>宽 <input type="number" step="0.1" :min="furnitureMinSize(selected.item?.type || '')" :max="FURNITURE_MAX_SIZE" :value="furnitureSize(selected.item?.type || '', selected.item).width" @change="onFurnitureSelChange('width', $event)" /></label>
            <label>深 <input type="number" step="0.1" :min="furnitureMinSize(selected.item?.type || '')" :max="FURNITURE_MAX_SIZE" :value="furnitureSize(selected.item?.type || '', selected.item).depth" @change="onFurnitureSelChange('depth', $event)" /></label>
          </template>
          <template v-else>
            <div class="office-3d-props-title">房间</div>
            <label>宽 <input type="number" step="0.5" :value="selected.zone?.width ?? 0" @change="onRoomSelChange('width', $event)" /></label>
            <label>深 <input type="number" step="0.5" :value="selected.zone?.depth ?? 0" @change="onRoomSelChange('depth', $event)" /></label>
            <label>X <input type="number" step="0.5" :value="selected.zone?.position?.x ?? 0" @change="onRoomSelChange('x', $event)" /></label>
            <label>Z <input type="number" step="0.5" :value="selected.zone?.position?.z ?? 0" @change="onRoomSelChange('z', $event)" /></label>
          </template>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import type { BehaviorConfig, OfficeColleagueStatus, OfficeConfig, OfficeEnvironmentTheme, OfficeFurnitureItem, OfficeZone } from '@/api/office'
import { zoneSeats } from '@/composables/officeLayout'
import { buildFurniture } from './furnitureSpec'
import {
  AppstoreOutlined,
  CheckOutlined,
  CloseOutlined,
  CoffeeOutlined,
  DeleteOutlined,
  DragOutlined,
  ExpandOutlined,
  FullscreenOutlined,
  HomeOutlined,
  InboxOutlined,
  PictureOutlined,
  RedoOutlined,
  RotateRightOutlined,
  SearchOutlined,
  SelectOutlined,
  SwapOutlined,
  TeamOutlined,
  UndoOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons-vue'
import { useOfficeEdit } from '@/composables/useOfficeEdit'

const props = defineProps<{
  colleagues: any[]
  statusMap: Record<string, OfficeColleagueStatus>
  selectedRoleKey?: string | null
  officeConfig?: OfficeConfig
  behaviorConfig?: BehaviorConfig
  editable?: boolean
}>()

const emit = defineEmits<{
  select: [roleKey: string]
  'save-config': [config: OfficeConfig]
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
  bubbleSignature: string
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
  homeSlot: Seat
  currentZoneId?: string | null
  targetZoneType?: string | null
  routeZone: OfficeZone | null
  lastPosX: number
  lastPosZ: number
  stuckFrames: number
  route: THREE.Vector3[]
  routeIndex: number
  walkTarget: THREE.Vector3
  armL?: THREE.Object3D | null
  armR?: THREE.Object3D | null
  legL?: THREE.Object3D | null
  legR?: THREE.Object3D | null
}

type Seat = OfficeFurnitureItem

const containerRef = ref<HTMLElement | null>(null)
const isFullscreen = ref(false)
const view3D = ref(false)
/** 临时性能诊断开关：URL 加 ?officeDebug=1 开启，左上角显示读数（可随机关闭）。 */
const debugOn = ref(typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('officeDebug') === '1')
const debugText = ref('')
const assetQuery = ref('')
const sideTab = ref<'build' | 'rooms' | 'objects'>('objects')

const CATEGORY_LABELS: Record<string, string> = {
  furniture: '办公家具',
  seat: '座椅',
  desk: '办公桌',
  chair: '座椅',
  meeting: '会议',
  plant: '绿植',
  decor: '装饰',
  lounge: '休闲区',
  storage: '储物',
  room: '房间',
}

const CATEGORY_ICONS: Record<string, Component> = {
  room: TeamOutlined,
  furniture: HomeOutlined,
  desk: AppstoreOutlined,
  chair: TeamOutlined,
  seat: TeamOutlined,
  meeting: CoffeeOutlined,
  plant: PictureOutlined,
  decor: PictureOutlined,
  lounge: CoffeeOutlined,
  storage: InboxOutlined,
}

function categoryIcon(cat: string): Component {
  return CATEGORY_ICONS[cat] || AppstoreOutlined
}

const groupedCatalog = computed(() => {
  const q = assetQuery.value.trim().toLowerCase()
  const items = catalog.value.filter((c) => !q || c.label.toLowerCase().includes(q))
  const groups = new Map<string, typeof items>()
  for (const c of items) {
    const key = c.category || 'other'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(c)
  }
  const order = ['room', 'furniture', 'desk', 'chair', 'seat', 'lounge', 'meeting', 'storage', 'decor', 'plant']
  const keys = Array.from(groups.keys()).sort((a, b) => {
    const ia = order.indexOf(a)
    const ib = order.indexOf(b)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })
  return keys.map((category) => ({ category, label: CATEGORY_LABELS[category] || category, items: groups.get(category)! }))
})

const {
  editing,
  editCamera,
  catalog,
  hover,
  selected,
  armedType,
  armedRoom,
  rotateMode,
  zoomPct,
  enter,
  exit,
  onWheel: editWheel,
  editPointerDown,
  editPointerMove,
  editPointerUp,
  selectByType,
  setArmedRoom,
  toggleRotate,
  flipSelected,
  panMode,
  setPanMode,
  setPlanVisible,
  setTransformVisible,
  removeSelected,
  updateSelected,
  ensureFit,
  zoomIn,
  zoomOut,
  undo,
  redo,
  canUndo,
  canRedo,
  cancelEdit,
} = useOfficeEdit({
  container: () => containerRef.value,
  scene: () => scene,
  domElement: () => renderer?.domElement || containerRef.value,
  config: () => officeConfigValue(),
  environment: () => environment,
  rebuildEnvironment: () => buildEnvironment(),
})

function setEnvironmentVisible(visible: boolean) {
  if (environment) environment.visible = visible
}

function setActorsVisible(visible: boolean) {
  for (const actor of actorMap.values()) {
    actor.group.visible = visible
  }
}

function toggleEdit() {
  if (editing.value) {
    exit()
    view3D.value = false
    if (controls) controls.enabled = true
    setEnvironmentVisible(true)
    setActorsVisible(true)
    emit('save-config', officeConfigValue())
    leaveFullscreen()
  } else {
    enter()
    setPlanVisible(true)
    setEnvironmentVisible(true)
    setActorsVisible(false)
    if (controls) controls.enabled = false
    isFullscreen.value = true
    requestAnimationFrame(() => onResize())
  }
}

function saveAndExit() {
  if (!editing.value) return
  exit()
  view3D.value = false
  if (controls) controls.enabled = true
  setEnvironmentVisible(true)
  setActorsVisible(true)
  emit('save-config', officeConfigValue())
  leaveFullscreen()
}

function cancelAndExit() {
  if (!editing.value) return
  cancelEdit()
  view3D.value = false
  if (controls) controls.enabled = true
  setEnvironmentVisible(true)
  setActorsVisible(true)
  leaveFullscreen()
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  requestAnimationFrame(() => onResize())
}

function leaveFullscreen() {
  if (isFullscreen.value) {
    isFullscreen.value = false
    requestAnimationFrame(() => onResize())
  }
}

function setView(mode: '2d' | '3d') {
  const next = mode === '3d'
  if (view3D.value === next) return
  view3D.value = next
  setPlanVisible(!next)
  setTransformVisible(!next)
  setEnvironmentVisible(true)
  setActorsVisible(!editing.value)
  if (controls) controls.enabled = next
  if (!next && editing.value) ensureFit()
  requestAnimationFrame(() => onResize())
}

const canvasCursorClass = computed(() => {
  if (!editing.value || view3D.value) return 'office-3d-cursor--grab'
  if (armedType.value || armedRoom.value) return 'office-3d-cursor--place'
  if (panMode.value) return 'office-3d-cursor--pan'
  return hover.value ? 'office-3d-cursor--select-hit' : 'office-3d-cursor--select'
})

function onSelChange(axis: 'x' | 'z' | 'rot', event: Event) {
  const val = Number((event.target as HTMLInputElement).value)
  const sel = selected.value
  if (!sel) return
  const target = sel.item
  if (!target) return
  const pos = target.position ?? { x: 0, z: 0 }
  if (axis === 'x') updateSelected({ position: { ...pos, x: val } })
  else if (axis === 'z') updateSelected({ position: { ...pos, z: val } })
  else updateSelected({ rotation_y: (Math.round(val / 90) * 90 * Math.PI) / 180 })
}

function onFurnitureSelChange(axis: 'width' | 'depth', event: Event) {
  const raw = Number((event.target as HTMLInputElement).value)
  const sel = selected.value
  if (!sel || sel.kind === 'room' || !sel.item) return
  const s = furnitureSize(sel.item.type, sel.item)
  const symmetric = SYMMETRIC_FURNITURE_TYPES.has(sel.item.type)
  let width = s.width
  let depth = s.depth
  const snapped = Math.round(raw * 10) / 10
  if (axis === 'width') {
    width = clampFurnitureSize(snapped, sel.item.type)
    if (symmetric) depth = width
  } else {
    depth = clampFurnitureSize(snapped, sel.item.type)
    if (symmetric) width = depth
  }
  updateSelected({ width, depth })
}

function onSelectTool() {
  setView('2d')
  setPanMode(false)
  setArmedRoom(false)
  selectByType('')
}

function onPlaceAsset(type: string) {
  setView('2d')
  setPanMode(false)
  selectByType(type)
}

function onPlaceRoom() {
  setView('2d')
  setPanMode(false)
  setArmedRoom(!armedRoom.value)
}

function onRoomSelChange(axis: 'width' | 'depth' | 'x' | 'z', event: Event) {
  const val = Number((event.target as HTMLInputElement).value)
  const sel = selected.value
  if (!sel || sel.kind !== 'room' || !sel.zone) return
  const pos = sel.zone.position ?? { x: 0, z: 0 }
  if (axis === 'width') updateSelected({ width: val })
  else if (axis === 'depth') updateSelected({ depth: val })
  else if (axis === 'x') updateSelected({ position: { ...pos, x: val } })
  else updateSelected({ position: { ...pos, z: val } })
}

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

// 角色 GLB 模板按 URL 缓存，避免重复 fetch/parse。键为 URL，值为加载 Promise。
const characterTemplateCache = new Map<string, Promise<CharacterTemplate>>()
let templateLoadSeq = 0

// 路由重算的按帧去抖：仅当 actor 终点真正变化时入队，下一帧统一重算 A*。
let routeFlushRaf = 0
const pendingRouteZones = new Map<Actor, OfficeZone | null>()

// 配置 watcher 的布局/模型/状态签名缓存，用于判断是否真的需要重建。
let lastLayoutSig = ''
let lastModelSig = ''
let lastStatusSig = ''

// 临时调诊断计数（仅 debugOn 时累加，不参与逻辑）。
let dbgFrame = 0
let dbgMs = 0
let dbgWorst = 0
let dbgAstar = 0
let dbgBlocked = 0
let dbgNextLog = 0

// 会议区座位防碰撞分配缓存：zoneId -> (roleKey -> seat)。
// 每轮 applyStatuses 重建一次，确保同一会议区的参会角色不撞到同一把椅子。
let meetingSlotAllocationCache: Map<string, Map<string, Seat>> | null = null

const DESK_WORK_DISTANCE = 0.78
const DESK_IDLE_DISTANCE = 0.95
const DESK_WAIT_DISTANCE = 1.18
const DESK_WAIT_SIDE = 0.28
const DESK_CHAIR_OFFSET = 1.0
const MEETING_CHAIR_BACK_REACH = 0.27
const MEETING_STAND_GAP = 0.18
const WALK_SPEED = 2.4
/** 寻路网格步长（米）。 */
const NAV_STEP = 0.25
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
      whiteboard: true, windows: true, ceiling_lights: false, art: true,
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
      whiteboard: true, windows: true, ceiling_lights: false, art: true,
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
      whiteboard: true, windows: true, ceiling_lights: false, art: true,
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

/** 内置基准尺寸表：与各家具建模尺寸一致（米），作为缩放基准，保证渲染/碰撞与 catalog 严格对齐。 */
const FALLBACK_FURNITURE_SIZE: Record<string, { width: number; depth: number }> = {
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

/** 输入尺寸下限：薄壁/挂墙类允许更小深度，其余给到 0.2 防止塌成 0。 */
const FURNITURE_MIN_SIZE: Record<string, number> = {
  art: 0.04,
  whiteboard: 0.04,
  tv: 0.04,
  partition: 0.04,
}
const FURNITURE_MAX_SIZE = 12
/** 圆形/对称家具：宽深必须一致，避免拉成椭圆。 */
const SYMMETRIC_FURNITURE_TYPES = new Set([
  'plant',
  'coffee_table',
  'round_table',
  'stool',
  'coat_rack',
  'fridge',
  'file_cabinet',
])

function furnitureMinSize(type: string): number {
  return FURNITURE_MIN_SIZE[type] ?? 0.2
}

function clampFurnitureSize(v: number, type: string): number {
  const min = furnitureMinSize(type)
  return Math.min(FURNITURE_MAX_SIZE, Math.max(min, v))
}

/** 家具尺寸的单一数据源：单件覆盖 -> 配置 catalog（后端下发）-> 前端回退表。 */
function furnitureSize(type: string, item?: OfficeFurnitureItem): { width: number; depth: number } {
  let width: number | undefined
  let depth: number | undefined
  if (item) {
    if (typeof item.width === 'number') width = item.width
    if (typeof item.depth === 'number') depth = item.depth
  }
  const catalog = officeConfigValue().furniture_catalog
  if (Array.isArray(catalog)) {
    const def = catalog.find((c) => c.type === type)
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

function officeZones(): OfficeZone[] {
  return officeConfigValue().zones || []
}

/** 布局签名：zones/furniture/floor/workspace/catalog/theme 任一变化都会重建环境+actor。 */
function layoutSignature(): string {
  const cfg = officeConfigValue()
  return JSON.stringify({
    floor: cfg.floor,
    workspace: cfg.workspace,
    zones: cfg.zones,
    furniture: cfg.furniture,
    furniture_catalog: cfg.furniture_catalog,
    environment_theme: cfg.environment_theme,
  })
}

/** 角色模型签名：character_models 变化只重载模板并重建 actor，不重建环境。 */
function modelSignature(): string {
  return JSON.stringify(officeConfigValue().character_models || [])
}

/** 状态映射签名：status_zone_map 变化只重算目标，不重建场景。 */
function statusMappingSignature(): string {
  return JSON.stringify(officeConfigValue().status_zone_map || {})
}

/** 是否已拿到真实布局配置（zones/furniture/floor/workspace 任一非空）。 */
function officeConfigHasContent(): boolean {
  const cfg = officeConfigValue()
  return Boolean(
    (Array.isArray(cfg.zones) && cfg.zones.length > 0) ||
      (Array.isArray(cfg.furniture) && cfg.furniture.length > 0) ||
      (cfg.floor && (cfg.floor.width || cfg.floor.depth)) ||
      (cfg.workspace && (cfg.workspace.width || cfg.workspace.depth)),
  )
}

function deskZones(): OfficeZone[] {
  return officeZones().filter((zone) => zone.type === 'desk')
}

function zoneById(zoneId: string): OfficeZone | null {
  return officeZones().find((zone) => zone.id === zoneId) || null
}

function slotPosition(slot: Seat): THREE.Vector3 {
  return new THREE.Vector3(slot.position?.x ?? 0, 0, slot.position?.z ?? 0)
}

function slotRotationY(slot: Seat): number {
  return slot.rotation_y ?? 0
}

function slotForward(slot: Seat): THREE.Vector3 {
  const rotation = slotRotationY(slot)
  return new THREE.Vector3(Math.sin(rotation), 0, Math.cos(rotation))
}

function slotRight(slot: Seat): THREE.Vector3 {
  const rotation = slotRotationY(slot)
  return new THREE.Vector3(Math.cos(rotation), 0, -Math.sin(rotation))
}

function slotPhase(slot: Seat): number {
  return slotRotationY(slot) + Math.PI
}

function hashRoleKey(roleKey: string): number {
  let hash = 0
  for (let i = 0; i < roleKey.length; i += 1) {
    hash = (hash * 31 + roleKey.charCodeAt(i)) >>> 0
  }
  return hash
}

function deskSlotAssignments(): Map<string, { zone: OfficeZone; slot: Seat }> {
  const assignments = new Map<string, { zone: OfficeZone; slot: Seat }>()
  const freeSlots: Array<{ zone: OfficeZone; slot: Seat }> = []
  const roleKeys = new Set(props.colleagues.map((colleague) => colleague.role_key))
  for (const zone of deskZones()) {
    for (const slot of zoneSeats(officeFurniture(), zone.id)) {
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

function fallbackDeskSlot(index: number): { zone: OfficeZone; slot: Seat } | null {
  const slots: Array<{ zone: OfficeZone; slot: Seat }> = []
  for (const zone of deskZones()) {
    for (const slot of zoneSeats(officeFurniture(), zone.id)) slots.push({ zone, slot })
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

/** 重建所有会议区的座位分配：只让“确实要去该会议区”的角色参与占座，按同事顺序依次分配空位，避免哈希撞座。 */
function rebuildMeetingSlotAllocation() {
  const cache = new Map<string, Map<string, Seat>>()
  for (const zone of officeZones()) {
    if (zone.type !== 'meeting') continue
    const seats = zoneSeats(officeFurniture(), zone.id)
    if (!seats.length) continue
    const attendees = props.colleagues.filter((colleague) => {
      const event = props.statusMap[colleague.role_key]
      return resolveZoneForStatus(colleague.role_key, event?.status || 'idle', event)?.id === zone.id
    })
    const allocation = new Map<string, Seat>()
    const taken = new Set<Seat>()
    for (const colleague of attendees) {
      const explicit = seats.find((slot) => slot.role_key === colleague.role_key)
      if (explicit && !taken.has(explicit)) {
        allocation.set(colleague.role_key, explicit)
        taken.add(explicit)
        continue
      }
      // 取第一个未被占用且未显式预留给其他角色的空位。
      const free = seats.find((slot) => !taken.has(slot) && !slot.role_key)
      if (free) {
        allocation.set(colleague.role_key, free)
        taken.add(free)
      } else {
        allocation.set(colleague.role_key, seats[attendees.indexOf(colleague) % seats.length])
      }
    }
    cache.set(zone.id, allocation)
  }
  meetingSlotAllocationCache = cache
}

function meetingSlotForActor(zone: OfficeZone, roleKey: string): Seat {
  const slots = zoneSeats(officeFurniture(), zone.id)
  if (!slots.length) return { id: 'meeting-fallback', position: zone.position || { x: 0, z: 0 }, rotation_y: 0 } as Seat
  if (!meetingSlotAllocationCache) rebuildMeetingSlotAllocation()
  const cache = meetingSlotAllocationCache as Map<string, Map<string, Seat>>
  const allocated = cache.get(zone.id)?.get(roleKey)
  if (allocated) return allocated
  const explicit = slots.find((slot) => slot.role_key === roleKey)
  if (explicit) return explicit
  return slots[hashRoleKey(roleKey) % slots.length]
}

function meetingPhaseForSlot(zone: OfficeZone, slot: Seat): number {
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
    if (!scene || !environment) return
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
    const layoutSig = layoutSignature()
    const modelSig = modelSignature()
    const statusSig = statusMappingSignature()

    if (editing.value) {
      // 编辑态沿用旧行为：仅切换可见性、不重建；也不记录签名，
      // 使退出编辑时的 save-config 仍能触发真正的重建。
      setEnvironmentVisible(true)
      setActorsVisible(false)
      return
    }

    const layoutChanged = layoutSig !== lastLayoutSig
    const modelChanged = modelSig !== lastModelSig
    const statusChanged = statusSig !== lastStatusSig

    lastLayoutSig = layoutSig
    lastModelSig = modelSig
    lastStatusSig = statusSig

    if (!layoutChanged && !modelChanged && !statusChanged) return

    if (layoutChanged) buildEnvironment()
    if (modelChanged) await loadCharacterTemplates()

    // 布局或模型变化才重建 actor；仅状态映射变化只重算目标，不重建场景。
    if (layoutChanged || modelChanged) {
      rebuildActors()
      setEnvironmentVisible(true)
      setActorsVisible(true)
    } else if (statusChanged) {
      applyStatuses()
    }
  },
  { deep: true },
)

watch(
  () => props.behaviorConfig,
  () => applyStatuses(),
  { deep: true },
)

async function loadCharacterTemplates() {
  const modelFiles = officeConfigValue().character_models || []
  const seq = ++templateLoadSeq
  const tasks = modelFiles.map((url) => fetchTemplateCached(url))
  const results = await Promise.allSettled(tasks)
  // 被更高序号的加载覆盖时丢弃结果，避免旧配置覆盖新配置。
  if (seq !== templateLoadSeq) return

  characterTemplates.length = 0
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      characterTemplates.push(result.value)
    } else {
      console.error(`加载 AI 同事模型失败: ${modelFiles[index]}`, result.reason)
    }
  })
}

/** 单 URL 的缓存式加载：命中缓存直接复用，否则解析后写入缓存。 */
function fetchTemplateCached(url: string): Promise<CharacterTemplate> {
  let cached = characterTemplateCache.get(url)
  if (!cached) {
    cached = loadCharacterTemplate(url)
    cached.catch(() => characterTemplateCache.delete(url))
    characterTemplateCache.set(url, cached)
  }
  return cached
}

/** 解析单个 GLB 并获得包围盒尺寸（缓存的是加载结果，克隆时再复制场景树）。 */
function loadCharacterTemplate(url: string): Promise<CharacterTemplate> {
  const loader = new GLTFLoader()
  return loader.loadAsync(url).then((gltf) => {
    const box = new THREE.Box3().setFromObject(gltf.scene)
    const size = new THREE.Vector3()
    box.getSize(size)
    return {
      scene: gltf.scene,
      animations: gltf.animations || [],
      height: size.y || 2.5,
      depth: size.z || 0.45,
      frontRotation: 0,
    }
  })
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

  // 挂载时配置通常还是空的（loadConfig 异步返回），此时不构建；
  // 交由 officeConfig watcher 在数据到位后只构建一次，避免入口重复建场景。
  // 若挂载时配置已就绪（例如 KeepAlive 重挂载），这里兜底直接构建。
  if (officeConfigHasContent()) {
    buildEnvironment()
    loadCharacterTemplates().then(() => {
      rebuildActors()
      applyStatuses()
      updateSelection()
    })
  }

  resizeObserver = new ResizeObserver(onResize)
  resizeObserver.observe(el)

  renderer.domElement.addEventListener('pointerdown', onPointerDown)
  renderer.domElement.addEventListener('pointermove', onPointerMove)
  renderer.domElement.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  renderer.domElement.addEventListener('wheel', onWheelEdit, { passive: false })
  renderer.domElement.addEventListener('contextmenu', onContextEdit)
  window.addEventListener('keydown', onKeyEdit)

  document.addEventListener('visibilitychange', onVisibilityChange)
  startRenderLoop()
}

function onContextEdit(event: MouseEvent) {
  if (editing.value) event.preventDefault()
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
  if (editing.value && !view3D.value) ensureFit()
}

function buildEnvironment() {
  if (!scene) return
  invalidateObstacleGrid()
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
  buildTerrace(theme, width, depth)
  buildCeilingEdges(theme, width, depth, wallHeight, wallThickness)
  buildLighting(theme, width, depth, wallHeight)
  buildProps(theme, width, depth, wallHeight)

  for (const zone of officeZones()) {
    if (zone.room === true || zone.type === 'meeting') {
      if (zone.type === 'meeting') buildMeetingRoom(zone)
      else buildRoomShell(zone)
    }
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


function createWoodFloorTexture(baseColor: string): THREE.CanvasTexture {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.fillStyle = baseColor
    ctx.fillRect(0, 0, size, size)
    const plankW = 32
    const plankColors = ['#00000022', '#ffffff18', '#00000014', '#ffffff0c']
    for (let x = 0; x < size; x += plankW) {
      const shade = plankColors[(x / plankW) % plankColors.length]
      ctx.fillStyle = shade
      ctx.fillRect(x, 0, plankW, size)
      ctx.strokeStyle = 'rgba(60,40,20,0.28)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x + 0.5, 0)
      ctx.lineTo(x + 0.5, size)
      ctx.stroke()
      const seamY = ((x / plankW) * 97 + 40) % size
      ctx.beginPath()
      ctx.moveTo(x, seamY)
      ctx.lineTo(x + plankW, seamY)
      ctx.stroke()
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'
    ctx.lineWidth = 1
    for (let y = 0; y < size; y += 4) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(size, y)
      ctx.stroke()
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.anisotropy = 4
  return texture
}

function buildFloor(theme: OfficeEnvironmentTheme, width: number, depth: number) {
  if (!environment) return
  const floorColor = theme.palette?.floor || '#151c29'
  const wood = createWoodFloorTexture(floorColor)
  const plankTile = 2.4
  wood.repeat.set(Math.max(4, Math.round(width / plankTile)), Math.max(4, Math.round(depth / plankTile)))
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: wood,
    roughness: theme.preset === 'midnight' ? 0.68 : 0.72,
    metalness: 0.04,
  })
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.position.y = 0
  floor.receiveShadow = true
  environment.add(floor)

  const officeGrid = createRectangularGrid(
    width,
    depth,
    Math.max(1, Math.round(Math.max(width, depth))),
    floorColor,
    0.013,
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
    opacity: 0.26,
  })
  const grid = new THREE.LineSegments(geometry, material)
  grid.position.y = y
  return grid
}

function createWindowedBackWall(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number) {
  const group = new THREE.Group()
  const wallColor = theme.palette?.wall || '#222e42'
  const lowerColor = theme.palette?.wall_lower || '#1a2434'
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xbfe2f5,
    roughness: 0.1,
    metalness: 0.08,
    transparent: true,
    opacity: 0.3,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const frameMat = envMaterial(lowerColor, 0.5, 0.2)
  const z = -depth / 2
  const sillH = 0.42
  const glassTop = height - 0.5
  const glassH = glassTop - sillH
  const sill = new THREE.Mesh(new THREE.BoxGeometry(width, sillH, thickness), envMaterial(wallColor, 0.8, 0.06))
  sill.position.set(0, sillH / 2, z)
  sill.receiveShadow = true
  group.add(sill)
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(width - 0.2, glassH), glassMat)
  glass.position.set(0, sillH + glassH / 2, z + thickness / 2 + 0.02)
  group.add(glass)
  const bays = Math.max(2, Math.round(width / 4))
  const bayW = width / bays
  for (let i = 0; i <= bays; i += 1) {
    const mullion = new THREE.Mesh(new THREE.BoxGeometry(0.1, glassH, 0.12), frameMat)
    mullion.position.set(-width / 2 + i * bayW, sillH + glassH / 2, z + thickness / 2 + 0.03)
    group.add(mullion)
  }
  const header = new THREE.Mesh(new THREE.BoxGeometry(width, 0.16, 0.14), frameMat)
  header.position.set(0, glassTop + 0.06, z + thickness / 2 + 0.03)
  group.add(header)
  const base = new THREE.Mesh(new THREE.BoxGeometry(width, 0.06, 0.14), frameMat)
  base.position.set(0, sillH + 0.02, z + thickness / 2 + 0.03)
  group.add(base)
  return group
}

function createSideWall(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number, side: number, doorGap?: { center: number; width: number }) {
  const group = new THREE.Group()
  const wallColor = theme.palette?.wall || '#222e42'
  const lowerColor = theme.palette?.wall_lower || '#1a2434'
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xbfe2f5,
    roughness: 0.1,
    metalness: 0.08,
    transparent: true,
    opacity: 0.3,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const frameMat = envMaterial(lowerColor, 0.5, 0.2)
  const x = side * width / 2
  const sillH = 0.42
  const glassTop = height - 0.5
  const glassH = glassTop - sillH
  const segments: Array<[number, number]> = []
  if (!doorGap) {
    segments.push([-depth / 2, depth / 2])
  } else {
    const gs = doorGap.center - doorGap.width / 2
    const ge = doorGap.center + doorGap.width / 2
    if (gs > -depth / 2) segments.push([-depth / 2, gs])
    if (ge < depth / 2) segments.push([ge, depth / 2])
  }
  for (const [fromZ, toZ] of segments) {
    const len = toZ - fromZ
    if (len <= 0.1) continue
    const cz = (fromZ + toZ) / 2
    const sill = new THREE.Mesh(new THREE.BoxGeometry(thickness, sillH, len), envMaterial(wallColor, 0.8, 0.06))
    sill.position.set(x, sillH / 2, cz)
    group.add(sill)
    const glass = new THREE.Mesh(new THREE.PlaneGeometry(len - 0.2, glassH), glassMat)
    glass.rotation.y = Math.PI / 2
    glass.position.set(x + side * (thickness / 2 + 0.02), sillH + glassH / 2, cz)
    group.add(glass)
    const bays = Math.max(1, Math.round(len / 4))
    const bayW = len / bays
    for (let i = 0; i <= bays; i += 1) {
      const mullion = new THREE.Mesh(new THREE.BoxGeometry(0.12, glassH, 0.1), frameMat)
      mullion.position.set(x + side * (thickness / 2 + 0.03), sillH + glassH / 2, fromZ + i * bayW)
      group.add(mullion)
    }
    const header = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.16, len), frameMat)
    header.position.set(x + side * (thickness / 2 + 0.03), glassTop + 0.06, cz)
    group.add(header)
    const base = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.06, len), frameMat)
    base.position.set(x + side * (thickness / 2 + 0.03), sillH + 0.02, cz)
    group.add(base)
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

function buildTerrace(theme: OfficeEnvironmentTheme, width: number, depth: number) {
  if (!environment) return
  const env = environment
  const margin = 1.4
  const tw = width + margin * 2
  const td = depth + margin * 2
  const terraceMat = envMaterial(theme.palette?.floor || '#b9a488', 0.85, 0.04)
  const terrace = new THREE.Mesh(new THREE.PlaneGeometry(tw, td), terraceMat)
  terrace.rotation.x = -Math.PI / 2
  terrace.position.y = -0.02
  terrace.receiveShadow = true
  env.add(terrace)
  const railMat = envMaterial(theme.palette?.wall_lower || '#8a9bb0', 0.4, 0.35)
  const railH = 1.05
  const postGap = 2.2
  const addRail = (cx: number, cz: number, len: number, horizontal: boolean) => {
    const top = new THREE.Mesh(new THREE.BoxGeometry(horizontal ? len : 0.08, 0.08, horizontal ? 0.08 : len), railMat)
    top.position.set(cx, railH, cz)
    env.add(top)
    const mid = new THREE.Mesh(new THREE.BoxGeometry(horizontal ? len : 0.05, 0.05, horizontal ? 0.05 : len), railMat)
    mid.position.set(cx, railH * 0.55, cz)
    env.add(mid)
    const count = Math.max(1, Math.round(len / postGap))
    for (let i = 0; i <= count; i += 1) {
      const t = i / count
      const px = horizontal ? cx - len / 2 + t * len : cx
      const pz = horizontal ? cz : cz - len / 2 + t * len
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.08, railH, 0.08), railMat)
      post.position.set(px, railH / 2, pz)
      env.add(post)
    }
  }
  addRail(0, -td / 2, tw, true)
  addRail(0, td / 2, tw, true)
  addRail(-tw / 2, 0, td, false)
  addRail(tw / 2, 0, td, false)
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


function addPlant(x: number, z: number, theme: OfficeEnvironmentTheme, parent: THREE.Group | null = environment) {
  const group = buildFurniture('plant', theme)
  if (!group) return group
  group.position.set(x, 0, z)
  if (parent) parent.add(group)
  return group
}

function addBookshelf(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY?: number, parent: THREE.Group | null = environment) {
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
  if (parent) parent.add(group)
  return group
}

function addCoffeeBar(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY?: number, parent: THREE.Group | null = environment) {
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
  if (parent) parent.add(group)
  return group
}

function addLounge(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY?: number, parent: THREE.Group | null = environment) {
  const group = buildFurniture('lounge_sofa', theme)
  if (!group) return group
  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x > 0 ? -Math.PI / 2 : Math.PI / 2)
  if (parent) parent.add(group)
  return group
}

function addWhiteboard(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0, parent: THREE.Group | null = environment) {
  const group = buildFurniture('whiteboard', theme)
  if (!group) return group
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}

function addArt(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY: number, color: string, parent: THREE.Group | null = environment) {
  const group = buildFurniture('art', theme, color)
  if (!group) return group
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}

function addMeetingTable(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0, parent: THREE.Group | null = environment) {
  const group = new THREE.Group()
  const top = envMaterial(theme.palette?.furniture || '#7a5c3d', 0.42, 0.16)
  const leg = envMaterial('#3a3f47', 0.42, 0.5)
  const length = 4.0
  const width = 1.2
  const thick = 0.1
  const height = 0.72
  const rect = new THREE.Mesh(new THREE.BoxGeometry(length - width, thick, width), top)
  rect.position.y = height
  rect.castShadow = true
  rect.receiveShadow = true
  group.add(rect)
  for (const sx of [-1, 1]) {
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(width / 2, width / 2, thick, 24), top)
    cap.position.set(sx * (length - width) / 2, height, 0)
    cap.castShadow = true
    group.add(cap)
  }
  for (const sx of [-1, 1]) {
    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.12, height, width * 0.72), leg)
    legs.position.set(sx * (length / 2 - 0.5), height / 2, 0)
    legs.castShadow = true
    group.add(legs)
  }
  const beam = new THREE.Mesh(new THREE.BoxGeometry(length - width, 0.08, 0.1), leg)
  beam.position.set(0, height - 0.3, 0)
  group.add(beam)
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}


const receptionLogoCache = new Map<string, THREE.CanvasTexture>()
function makeReceptionLogo(text: string): THREE.CanvasTexture {
  let tex = receptionLogoCache.get(text)
  if (tex) return tex
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 160
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.font = '700 96px "Segoe UI", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#1b2736'
    ctx.fillText(text, canvas.width / 2, canvas.height / 2)
  }
  tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.minFilter = THREE.LinearFilter
  tex.anisotropy = 2
  receptionLogoCache.set(text, tex)
  return tex
}

function addReceptionDesk(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0, parent: THREE.Group | null = environment) {
  const group = new THREE.Group()
  const woodMat = deskWoodMat(theme)
  const darkMat = deskDarkMat()
  const bodyMat = envMaterial(theme.palette?.furniture || '#3a4763', 0.7, 0.08)
  const logoPlateMat = envMaterial('#eef1f5', 0.55, 0.05)
  const screenMat = new THREE.MeshStandardMaterial({ color: 0x0a1a2b, roughness: 0.25, metalness: 0.42, emissive: 0x14293f, emissiveIntensity: 0.5 })
  const logoMat = new THREE.MeshStandardMaterial({ map: makeReceptionLogo('KayFly'), transparent: true, depthWrite: false, roughness: 0.5 })

  // 员工侧高台（后侧 -z）：接待员坐后面工作
  const staffBody = new THREE.Mesh(new RoundedBoxGeometry(2.2, 0.94, 0.55, 2, 0.02), bodyMat)
  staffBody.position.set(0, 0.47, -0.18)
  applyShadow(staffBody)
  group.add(staffBody)
  const staffTop = new THREE.Mesh(new RoundedBoxGeometry(2.26, 0.05, 0.58, 2, 0.015), woodMat)
  staffTop.position.set(0, 0.965, -0.17)
  applyShadow(staffTop)
  group.add(staffTop)

  // 顾客侧矮台（前侧 +z）：访客趴着签到/咨询
  const guestBody = new THREE.Mesh(new RoundedBoxGeometry(2.2, 0.6, 0.36, 2, 0.02), bodyMat)
  guestBody.position.set(0, 0.33, 0.27)
  applyShadow(guestBody)
  group.add(guestBody)
  const guestTop = new THREE.Mesh(new RoundedBoxGeometry(2.26, 0.045, 0.4, 2, 0.015), woodMat)
  guestTop.position.set(0, 0.663, 0.25)
  applyShadow(guestTop)
  group.add(guestTop)

  // 端头侧板
  const sidePanel = new THREE.Mesh(new RoundedBoxGeometry(0.06, 0.95, 0.9, 2, 0.015), bodyMat)
  sidePanel.position.set(1.07, 0.475, 0)
  applyShadow(sidePanel)
  group.add(sidePanel)

  // 正面 Logo 板 + KayFly 公司名
  const logoPlate = new THREE.Mesh(new RoundedBoxGeometry(1.5, 0.26, 0.02, 2, 0.008), logoPlateMat)
  logoPlate.position.set(0, 0.4, 0.44)
  group.add(logoPlate)
  const logo = new THREE.Mesh(new THREE.PlaneGeometry(1.35, 0.18), logoMat)
  logo.position.set(0, 0.4, 0.46)
  group.add(logo)

  // 员工台面小显示器（面向员工 -z）
  const monitorGroup = new THREE.Group()
  const mBase = new THREE.Mesh(new RoundedBoxGeometry(0.2, 0.03, 0.14, 1, 0.01), darkMat)
  mBase.position.y = 0.015
  monitorGroup.add(mBase)
  const mNeck = new THREE.Mesh(new RoundedBoxGeometry(0.05, 0.14, 0.05, 1, 0.01), darkMat)
  mNeck.position.set(0, 0.11, 0)
  monitorGroup.add(mNeck)
  const mPanel = new THREE.Mesh(new RoundedBoxGeometry(0.56, 0.35, 0.012, 2, 0.008), darkMat)
  mPanel.position.set(0, 0.34, 0.03)
  mPanel.castShadow = true
  monitorGroup.add(mPanel)
  const mScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.52, 0.31), screenMat)
  mScreen.position.set(0, 0.34, 0.037)
  monitorGroup.add(mScreen)
  monitorGroup.position.set(-0.55, 1.0, -0.18)
  monitorGroup.rotation.y = Math.PI
  group.add(monitorGroup)

  // 台灯
  const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.03, 12), darkMat)
  lampBase.position.set(-0.92, 1.01, -0.15)
  group.add(lampBase)
  const lampArm = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.2, 8), darkMat)
  lampArm.rotation.z = -0.5
  lampArm.position.set(-0.92, 1.1, -0.15)
  group.add(lampArm)
  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.08, 10), new THREE.MeshStandardMaterial({ color: 0xffd166, emissive: 0xffb347, emissiveIntensity: 0.4, roughness: 0.5 }))
  lampHead.rotation.z = Math.PI / 2
  lampHead.position.set(-0.87, 1.17, -0.15)
  group.add(lampHead)

  // 电话 / 名牌 / 笔筒 / 绿植
  const phone = new THREE.Mesh(new RoundedBoxGeometry(0.16, 0.04, 0.12, 1, 0.012), darkMat)
  phone.position.set(0.12, 1.01, -0.28)
  group.add(phone)
  const plate = new THREE.Mesh(new RoundedBoxGeometry(0.3, 0.05, 0.035, 1, 0.01), logoPlateMat)
  plate.position.set(0.4, 1.01, -0.1)
  group.add(plate)
  const penPot = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.03, 0.09, 8), darkMat)
  penPot.position.set(-0.2, 1.045, -0.1)
  group.add(penPot)
  const pen = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.12, 6), envMaterial('#e05a4e', 0.5, 0.1))
  pen.position.set(-0.2, 1.1, -0.1)
  group.add(pen)
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.055, 0.12, 10), darkMat)
  pot.position.set(0.85, 1.05, -0.18)
  group.add(pot)
  const foliage = new THREE.Mesh(new THREE.IcosahedronGeometry(0.11, 0), envMaterial(theme.palette?.foliage || '#2f7d54', 0.7, 0.02))
  foliage.position.set(0.85, 1.2, -0.18)
  foliage.castShadow = true
  group.add(foliage)

  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}

function addFurnitureItem(item: OfficeFurnitureItem, theme: OfficeEnvironmentTheme, parent: THREE.Group | null = environment) {
  const x = item.position?.x ?? 0
  const z = item.position?.z ?? 0
  const rotationY = item.rotation_y ?? 0
  const accentColor = theme.palette?.accent || '#1677ff'
  let group: THREE.Group | null = null

  switch (item.type) {
    case 'desk':
      group = createDesk(accentColor).group
      break
    case 'office_chair':
      group = buildFurniture(item.type, theme)
      break
    case 'meeting_chair':
      group = buildFurniture(item.type, theme)
      break
    case 'meeting_table':
      group = addMeetingTable(x, z, theme, rotationY, parent)
      break
    case 'plant':
      group = buildFurniture('plant', theme)
      break
    case 'bookshelf':
      group = addBookshelf(x, z, theme, rotationY, parent)
      break
    case 'coffee_bar':
      group = addCoffeeBar(x, z, theme, rotationY, parent)
      break
    case 'lounge_sofa':
      group = buildFurniture('lounge_sofa', theme)
      break
    case 'whiteboard':
      group = buildFurniture('whiteboard', theme)
      break
    case 'art':
      group = buildFurniture('art', theme, accentColor)
      break
    case 'rug':
      group = buildFurniture('rug', theme)
      break
    case 'partition':
      group = buildFurniture('partition', theme)
      break
    case 'fridge':
      group = buildFurniture('fridge', theme)
      break
    case 'coffee_table':
      group = buildFurniture('coffee_table', theme)
      break
    case 'round_table':
      group = buildFurniture('round_table', theme)
      break
    case 'stool':
      group = buildFurniture('stool', theme)
      break
    case 'reception_desk':
      group = addReceptionDesk(x, z, theme, rotationY, parent)
      break
    case 'coat_rack':
      group = buildFurniture('coat_rack', theme)
      break
    case 'tv':
      group = buildFurniture('tv', theme)
      break
    case 'file_cabinet':
      group = buildFurniture('file_cabinet', theme)
      break

    default:
      break
  }

  if (!group) return null
  // 单一数据源：渲染尺寸跟随 catalog / 单件 width-depth（相对设计基底等比缩放，保持外观）。
  const size = furnitureSize(item.type, item)
  const base = FALLBACK_FURNITURE_SIZE[item.type]
  if (base && base.width > 0 && base.depth > 0) {
    group.scale.set(size.width / base.width, 1, size.depth / base.depth)
  }
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  group.name = `furniture-${item.id}`
  group.userData.edit = { kind: 'furniture', item, id: item.id }
  parent?.add(group)
  return group
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
  const seats = zoneSeats(officeFurniture(), zone.id)
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

function buildMeetingRoom(zone: OfficeZone, parent: THREE.Group | null = environment) {
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
  const roomGroup = new THREE.Group()
  roomGroup.name = `room-${zone.id}`
  const floorColor = zone.glass ? '#cfd8dc' : (theme.palette?.floor || '#d8c5a3')

  const roomFloor = new THREE.Mesh(new THREE.PlaneGeometry(roomWidth, roomDepth), envMaterial(floorColor, 0.9, 0.04))
  roomFloor.rotation.x = -Math.PI / 2
  roomFloor.position.set(center.x, 0.002, center.z)
  roomFloor.receiveShadow = true
  roomGroup.add(roomFloor)

  const roomGrid = createRectangularGrid(
    roomWidth,
    roomDepth,
    Math.max(1, Math.round(Math.max(roomWidth, roomDepth))),
    floorColor,
    0.012,
  )
  roomGrid.position.x = center.x
  roomGrid.position.z = center.z
  roomGroup.add(roomGrid)

  createMeetingRoomShell(theme, center, bounds, roomGroup, doorSide, doorWidth, doorOffset)

  const linkToWall = zone.door_to_wall !== false
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
  const corridorLength = linkToWall ? corridorTo - corridorFrom : 0
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
    roomGroup.add(corridor)

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
    roomGroup.add(mainDoor)
  }

  createMeetingZone(zone, roomGroup, doorSide)

  roomGroup.userData.edit = { kind: 'room', zone, id: zone.id }
  if (parent) parent.add(roomGroup)
  return roomGroup
}

function createRoomWalls(
  theme: OfficeEnvironmentTheme,
  center: THREE.Vector3,
  bounds: MeetingBounds,
  doorSide: MeetingDoorSide = 'front',
  doorWidth = 1.3,
  doorOffset = 0,
  thickness = 0.12,
): THREE.Group {
  const group = new THREE.Group()
  const wallH = 2.55
  const wallMat = envMaterial(theme.palette?.wall_lower || '#dce4e9', 0.85, 0.05)
  const frameMat = envMaterial(theme.palette?.wall_lower || '#dce4e9', 0.55, 0.2)
  const { minX, maxX, minZ, maxZ } = bounds
  const doorCenterX = center.x + doorOffset
  const doorCenterZ = center.z + doorOffset
  const frontGapStart = doorCenterX - doorWidth / 2
  const frontGapEnd = doorCenterX + doorWidth / 2
  const sideGapStart = doorCenterZ - doorWidth / 2
  const sideGapEnd = doorCenterZ + doorWidth / 2

  const addWallZ = (z: number, fromX: number, toX: number) => {
    if (toX <= fromX) return
    const m = new THREE.Mesh(new THREE.BoxGeometry(toX - fromX, wallH, thickness), wallMat)
    m.position.set((fromX + toX) / 2, wallH / 2, z)
    applyShadow(m)
    group.add(m)
  }
  const addWallX = (x: number, fromZ: number, toZ: number) => {
    if (toZ <= fromZ) return
    const m = new THREE.Mesh(new THREE.BoxGeometry(thickness, wallH, toZ - fromZ), wallMat)
    m.position.set(x, wallH / 2, (fromZ + toZ) / 2)
    applyShadow(m)
    group.add(m)
  }

  if (doorSide === 'back') {
    addWallZ(minZ, minX, frontGapStart); addWallZ(minZ, frontGapEnd, maxX)
    addWallX(minX, minZ, maxZ); addWallX(maxX, minZ, maxZ)
    addWallZ(maxZ, minX, maxX)
  } else if (doorSide === 'left') {
    addWallZ(minZ, minX, maxX); addWallZ(maxZ, minX, maxX)
    addWallX(minX, minZ, sideGapStart); addWallX(minX, sideGapEnd, maxZ); addWallX(maxX, minZ, maxZ)
  } else if (doorSide === 'right') {
    addWallZ(minZ, minX, maxX); addWallZ(maxZ, minX, maxX)
    addWallX(minX, minZ, maxZ); addWallX(maxX, minZ, sideGapStart); addWallX(maxX, sideGapEnd, maxZ)
  } else {
    addWallZ(minZ, minX, maxX)
    addWallX(minX, minZ, maxZ); addWallX(maxX, minZ, maxZ)
    addWallZ(maxZ, minX, frontGapStart); addWallZ(maxZ, frontGapEnd, maxX)
  }

  const doorH = 2.1
  const addPosts = (edgeX: number, edgeZ: number, horizontal: boolean) => {
    for (const s of [-1, 1]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.09, doorH, 0.09), frameMat)
      if (horizontal) post.position.set(doorCenterX + s * doorWidth / 2, doorH / 2, edgeZ)
      else post.position.set(edgeX, doorH / 2, doorCenterZ + s * doorWidth / 2)
      applyShadow(post)
      group.add(post)
    }
  }
  if (doorSide === 'back') addPosts(0, minZ, true)
  else if (doorSide === 'left') addPosts(minX, 0, false)
  else if (doorSide === 'right') addPosts(maxX, 0, false)
  else addPosts(0, maxZ, true)

  return group
}

function buildRoomShell(zone: OfficeZone, parent: THREE.Group | null = environment) {
  const theme = officeTheme()
  const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
  const bounds = meetingRoomBounds(zone)
  const roomWidth = bounds.maxX - bounds.minX
  const roomDepth = bounds.maxZ - bounds.minZ
  const floorColor = theme.palette?.floor || '#d8c5a3'
  const roomGroup = new THREE.Group()
  roomGroup.name = `room-${zone.id}`

  const roomFloor = new THREE.Mesh(new THREE.PlaneGeometry(roomWidth, roomDepth), envMaterial(floorColor, 0.9, 0.04))
  roomFloor.rotation.x = -Math.PI / 2
  roomFloor.position.set(center.x, 0.002, center.z)
  roomFloor.receiveShadow = true
  roomGroup.add(roomFloor)

  const roomGrid = createRectangularGrid(
    roomWidth,
    roomDepth,
    Math.max(1, Math.round(Math.max(roomWidth, roomDepth))),
    floorColor,
    0.012,
  )
  roomGrid.position.x = center.x
  roomGrid.position.z = center.z
  roomGroup.add(roomGrid)

  if (zone.door && typeof zone.door === 'object') {
    const doorSide = (zone.door.side as MeetingDoorSide) || 'front'
    roomGroup.add(createRoomWalls(theme, center, bounds, doorSide, zone.door.width ?? 1.3, zone.door.offset ?? 0))
  }

  roomGroup.userData.edit = { kind: 'room', zone, id: zone.id }
  if (parent) parent.add(roomGroup)
  return roomGroup
}

function createMeetingZone(zone: OfficeZone, parent: THREE.Group | null = environment, doorSide: MeetingDoorSide = 'front') {
  if (!environment) return

  const theme = officeTheme()
  const group = new THREE.Group()
  group.name = `meeting-zone-${zone.id}`

  const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
  const bounds = meetingRoomBounds(zone)
  const screenZ = doorSide === 'back' ? bounds.maxZ - 0.14 : bounds.minZ + 0.14

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

  const screen = new THREE.Mesh(
    new THREE.BoxGeometry(1.55, 0.92, 0.06),
    new THREE.MeshStandardMaterial({ color: 0x0a101c, emissive: 0x1a3448, emissiveIntensity: 0.85, roughness: 0.3, metalness: 0.3 }),
  )
  screen.position.set(center.x, 1.35, screenZ)
  screen.castShadow = true
  group.add(screen)

  const screenStand = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.62, 0.1), envMaterial(theme.palette?.furniture_light || '#8a6b4e', 0.55, 0.22))
  screenStand.position.set(center.x, 0.5, screenZ)
  group.add(screenStand)

  parent?.add(group)
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

// ---- 办公桌共享材质（同主题多张桌复用，降低重建/编译开销；monitorMat 仍每张独立）----
const deskMatCache = new Map<string, THREE.MeshStandardMaterial>()
function deskSharedMat(key: string, make: () => THREE.MeshStandardMaterial): THREE.MeshStandardMaterial {
  let m = deskMatCache.get(key)
  if (!m) {
    m = make()
    deskMatCache.set(key, m)
  }
  return m
}

function createDeskWoodTexture(baseColor: string): THREE.CanvasTexture {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.fillStyle = baseColor
    ctx.fillRect(0, 0, size, size)
    for (let i = 0; i < 24; i += 1) {
      const y = (i * 17 + 7) % size
      ctx.strokeStyle = i % 2 ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.06)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.bezierCurveTo(size * 0.3, y + 3, size * 0.6, y - 3, size, y)
      ctx.stroke()
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.anisotropy = 2
  return texture
}

function deskWoodMat(theme: OfficeEnvironmentTheme): THREE.MeshStandardMaterial {
  const base = theme.palette?.floor || '#9a7b56'
  return deskSharedMat(`wood|${base}`, () => new THREE.MeshStandardMaterial({ color: 0xffffff, map: createDeskWoodTexture(base), roughness: 0.55, metalness: 0.02 }))
}

function deskMetalMat(theme: OfficeEnvironmentTheme): THREE.MeshStandardMaterial {
  const c = theme.palette?.furniture_light || '#34455f'
  return deskSharedMat(`metal|${c}`, () => envMaterial(c, 0.34, 0.66))
}

function deskDarkMat(): THREE.MeshStandardMaterial {
  return deskSharedMat('dark', () => envMaterial('#151c28', 0.5, 0.34))
}

function createDesk(color: string): { group: THREE.Group; monitorMat: THREE.MeshStandardMaterial } {
  const group = new THREE.Group()
  const theme = officeTheme()
  const woodMat = deskWoodMat(theme)
  const metalMat = deskMetalMat(theme)
  const darkMat = deskDarkMat()
  const accentMat = envMaterial(color, 0.34, 0.2)
  const monitorMat = new THREE.MeshStandardMaterial({
    color: 0x0a101c, roughness: 0.28, metalness: 0.42,
    emissive: 0x05080f, emissiveIntensity: 0.25,
  })
  // 屏幕与面板共面，靠 polygonOffset 让屏幕深度优先，避免 z-fight 黑块/悬空
  monitorMat.polygonOffset = true
  monitorMat.polygonOffsetFactor = -2
  monitorMat.polygonOffsetUnits = -2

  // 桌面：圆角木板 + 程序化木纹
  const top = new THREE.Mesh(new RoundedBoxGeometry(1.78, 0.07, 0.98, 2, 0.02), woodMat)
  top.position.y = 0.7
  applyShadow(top)
  group.add(top)

  // 桌下横撑
  const apron = new THREE.Mesh(new RoundedBoxGeometry(1.7, 0.1, 0.86, 1, 0.015), darkMat)
  apron.position.y = 0.62
  group.add(apron)

  // 金属侧板腿
  for (const sx of [-0.8, 0.8]) {
    const panel = new THREE.Mesh(new RoundedBoxGeometry(0.07, 0.6, 0.8, 1, 0.015), metalMat)
    panel.position.set(sx, 0.31, 0)
    applyShadow(panel)
    group.add(panel)
  }

  // 后挡板
  const modesty = new THREE.Mesh(new RoundedBoxGeometry(1.5, 0.34, 0.05, 1, 0.012), darkMat)
  modesty.position.set(0, 0.46, -0.34)
  group.add(modesty)

  // 显示器：玻璃屏 + 支架底座（monitorMat 每张桌独立以支持开/关屏）
  // 底座/支架放在屏幕背后（更靠 -z），避免顶到屏幕
  const monitorBase = new THREE.Mesh(new RoundedBoxGeometry(0.26, 0.035, 0.18, 1, 0.01), darkMat)
  monitorBase.position.set(0, 0.755, -0.3)
  group.add(monitorBase)
  // 支架：底座 + 短颈接到面板背面，比例收敛
  const monitorNeck = new THREE.Mesh(new RoundedBoxGeometry(0.06, 0.16, 0.06, 1, 0.01), darkMat)
  monitorNeck.position.set(0, 0.86, -0.29)
  monitorNeck.castShadow = true
  group.add(monitorNeck)
  // 面板：薄圆角板（0.014 厚）；屏幕用平面贴在前表面，靠 polygonOffset 叠前，无厚度就不会从背面/侧面穿出
  const monitorPanel = new THREE.Mesh(new RoundedBoxGeometry(0.72, 0.44, 0.014, 2, 0.01), darkMat)
  monitorPanel.position.set(0, 1.16, -0.26)
  monitorPanel.castShadow = true
  group.add(monitorPanel)
  const monitorScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.42), monitorMat)
  monitorScreen.position.set(0, 1.16, -0.253)
  group.add(monitorScreen)

  const keyboard = new THREE.Mesh(new RoundedBoxGeometry(0.5, 0.035, 0.19, 1, 0.01), darkMat)
  keyboard.position.set(-0.05, 0.75, 0.3)
  keyboard.receiveShadow = true
  group.add(keyboard)
  // 键帽区（用暗色调，不再用亮色贴条）
  const keycapBase = new THREE.Mesh(new RoundedBoxGeometry(0.44, 0.02, 0.15, 1, 0.006), envMaterial('#2a3a4d', 0.6, 0.1))
  keycapBase.position.set(-0.05, 0.77, 0.3)
  group.add(keycapBase)
  const spaceBar = new THREE.Mesh(new RoundedBoxGeometry(0.24, 0.018, 0.05, 1, 0.005), envMaterial('#394a5f', 0.55, 0.12))
  spaceBar.position.set(-0.05, 0.773, 0.34)
  group.add(spaceBar)
  const mouse = new THREE.Mesh(new RoundedBoxGeometry(0.07, 0.035, 0.12, 2, 0.015), darkMat)
  mouse.position.set(0.4, 0.768, 0.32)
  mouse.rotation.y = -0.2
  group.add(mouse)

  const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, 0.03, 14), metalMat)
  lampBase.position.set(-0.66, 0.755, -0.05)
  group.add(lampBase)
  const lampArm1 = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 0.24, 8), metalMat)
  lampArm1.rotation.z = -0.5
  lampArm1.position.set(-0.66, 0.86, -0.05)
  group.add(lampArm1)
  const lampArm2 = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.2, 8), metalMat)
  lampArm2.rotation.z = 0.9
  lampArm2.position.set(-0.62, 0.98, -0.05)
  group.add(lampArm2)
  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.09, 12), new THREE.MeshStandardMaterial({ color: 0xffd166, emissive: 0xffb347, emissiveIntensity: 0.45, roughness: 0.5 }))
  lampHead.rotation.z = Math.PI / 2
  lampHead.position.set(-0.58, 1.04, -0.05)
  group.add(lampHead)

  const plantPot = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.16, 10), metalMat)
  plantPot.position.set(0.72, 0.815, 0.26)
  group.add(plantPot)
  const plantBall = new THREE.Mesh(new THREE.IcosahedronGeometry(0.13, 0), envMaterial(theme.palette?.foliage || '#2f7d54', 0.7, 0.02))
  plantBall.position.set(0.72, 1.0, 0.26)
  plantBall.castShadow = true
  group.add(plantBall)

  const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.034, 0.08, 10), envMaterial('#e5e9f0', 0.5, 0.05))
  mug.position.set(-0.42, 0.775, 0.3)
  group.add(mug)

  const nameplate = new THREE.Mesh(new RoundedBoxGeometry(0.3, 0.06, 0.035, 1, 0.01), accentMat)
  nameplate.position.set(0.28, 0.765, 0.42)
  group.add(nameplate)

  const chair = new THREE.Group()
  const chairFabric = envMaterial(theme.palette?.furniture_light || '#34455f', 0.74, 0.05)
  const chairDark = envMaterial('#111822', 0.5, 0.28)

  // 五星脚 + 轮子：每条撑杆沿半径方向辐射，轮子在杆端
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.07, 0.06, 12), chairDark)
  hub.position.y = 0.05
  hub.castShadow = true
  chair.add(hub)
  for (let i = 0; i < 5; i += 1) {
    const angle = (i / 5) * Math.PI * 2 + Math.PI / 2
    const pivot = new THREE.Group()
    pivot.position.set(0, 0.05, 0)
    pivot.rotation.y = Math.PI / 2 - angle
    chair.add(pivot)
    const arm = new THREE.Mesh(new RoundedBoxGeometry(0.045, 0.045, 0.42, 1, 0.012), chairDark)
    arm.position.z = 0.2
    arm.castShadow = true
    pivot.add(arm)
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.03, 10), chairDark)
    wheel.rotation.z = Math.PI / 2
    wheel.position.set(0, 0, 0.4)
    pivot.add(wheel)
  }
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.045, 0.38, 12), chairDark)
  pole.position.y = 0.27
  pole.castShadow = true
  chair.add(pole)
  // 座垫顶面 ~0.53，保持入座高度不变
  const seat = new THREE.Mesh(new RoundedBoxGeometry(0.52, 0.11, 0.5, 2, 0.035), chairFabric)
  seat.position.y = 0.475
  seat.castShadow = true
  chair.add(seat)
  const back = new THREE.Mesh(new RoundedBoxGeometry(0.5, 0.58, 0.12, 2, 0.035), chairFabric)
  back.position.set(0, 0.82, -0.24)
  back.rotation.x = -0.1
  back.castShadow = true
  chair.add(back)
  for (const sx of [-0.28, 0.28]) {
    const armSupport = new THREE.Mesh(new RoundedBoxGeometry(0.05, 0.16, 0.06, 1, 0.012), chairDark)
    armSupport.position.set(sx, 0.56, 0.02)
    armSupport.castShadow = true
    chair.add(armSupport)
    const armPad = new THREE.Mesh(new RoundedBoxGeometry(0.08, 0.05, 0.3, 2, 0.02), chairDark)
    armPad.position.set(sx, 0.65, 0.02)
    armPad.castShadow = true
    chair.add(armPad)
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
      // 标记为“与缓存模板共享的资源”，dispose 时交由模板缓存持有，不随 actor 释放。
      child.userData.templateShared = true
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

  // 旧 actor 即将销毁，丢弃尚未执行的路由重算，避免引用悬空对象。
  if (routeFlushRaf) {
    cancelAnimationFrame(routeFlushRaf)
    routeFlushRaf = 0
  }
  pendingRouteZones.clear()

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
      bubbleSignature: '',
      bubble: bubble.sprite,
      label: label.sprite,
      bubbleTexture: bubble.texture,
      bubbleCanvas: bubble.canvas,
      bubbleCtx: bubble.ctx,
      targetPosition: characterHome.clone(),
      routeZone: null,
      lastPosX: characterHome.x,
      lastPosZ: characterHome.z,
      stuckFrames: 0,
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
  rebuildMeetingSlotAllocation()
  for (const actor of actorMap.values()) {
    updateActorStatus(actor, props.statusMap[actor.roleKey])
  }
  scheduleRouteRecompute()
}

/** 把已入队的 actor 路由重算合并到下一帧执行，避免同一帧多次推送导致全量 A*。 */
function scheduleRouteRecompute() {
  if (routeFlushRaf || !pendingRouteZones.size) return
  const stepOne = () => {
    routeFlushRaf = 0
    const next = pendingRouteZones.keys().next()
    if (next.done) return
    const actor = next.value
    const zone = pendingRouteZones.get(actor) ?? null
    pendingRouteZones.delete(actor)
    rebuildActorRoute(actor, zone)
    if (pendingRouteZones.size) {
      routeFlushRaf = requestAnimationFrame(stepOne)
    }
  }
  routeFlushRaf = requestAnimationFrame(stepOne)
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
  const bubbleSig = `${status}|${activity}|${message}`
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
  // 只在气泡内容真正变化时重绘 512×128 canvas，避免每次 applyStatuses 全量重绘造成卡顿。
  if (bubbleSig !== actor.bubbleSignature) {
    drawBubble(actor, status, activity, message)
    actor.bubbleSignature = bubbleSig
  }
}

function updateActorTarget(actor: Actor, status: string, event?: OfficeColleagueStatus) {
  const targetZone = resolveZoneForStatus(actor.roleKey, status, event)
  const action = assignmentActionFor(event)

  const prevPosition = actor.targetPosition
  const prevZoneType = actor.targetZoneType
  const prevZoneId = actor.currentZoneId
  const prevPhase = actor.phase

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

  // 只在终点真正变化时才重算路径：仅 message/颜色/bubble 变化不会触发 A*。
  if (destinationChanged(prevPosition, prevZoneType, prevZoneId, prevPhase, actor)) {
    pendingRouteZones.set(actor, targetZone)
  }
}

/** 判断目标的落点 / 归属区域 / 朝向是否相对上一状态发生了变化。 */
function destinationChanged(
  prevPosition: THREE.Vector3,
  prevZoneType: string | null | undefined,
  prevZoneId: string | null | undefined,
  prevPhase: number,
  actor: Actor,
): boolean {
  const next = actor.targetPosition
  return (
    Math.abs(prevPosition.x - next.x) > 1e-4 ||
    Math.abs(prevPosition.z - next.z) > 1e-4 ||
    prevZoneType !== actor.targetZoneType ||
    prevZoneId !== actor.currentZoneId ||
    prevPhase !== actor.phase
  )
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

function deskRouteSlotForActor(actor: Actor, targetZone: OfficeZone | null): Seat {
  const slots = targetZone ? zoneSeats(officeFurniture(), targetZone.id) : []
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
  const floor = officeFloor()
  const margin = 0.42
  const halfWidth = Math.max(0.1, floor.width / 2 - margin)
  const halfDepth = Math.max(0.1, floor.depth / 2 - margin)
  return new THREE.Vector3(
    Math.max(-halfWidth, Math.min(halfWidth, point.x)),
    0,
    Math.max(-halfDepth, Math.min(halfDepth, point.z)),
  )
}


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

function meetingWallBlocked(x: number, z: number): boolean {
  const clearance = 0.22
  for (const zone of officeZones()) {
    if (zone.type !== 'meeting') continue
    const b = meetingRoomBounds(zone)
    const side = meetingDoorSide(zone, officeFloor())
    const doorWidth = zone.door?.width ?? 1.3
    const doorOffset = zone.door?.offset ?? 0
    const cx = (zone.position?.x ?? 0) + doorOffset
    const cz = (zone.position?.z ?? 0) + doorOffset
    if (side === 'front' || side === 'back') {
      const wallZ = side === 'front' ? b.maxZ : b.minZ
      if (Math.abs(z - wallZ) < clearance && x >= b.minX - clearance && x <= b.maxX + clearance) {
        if (!(side === 'front' ? Math.abs(x - cx) < doorWidth / 2 : Math.abs(x - cx) < doorWidth / 2)) return true
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

/** 静态障碍网格：布局/家具变化时重建一次，blockedAt 查表 O(1)，消除"全格子×全家具"的主线程开销。 */
let obstacleGrid: Uint8Array | null = null
let obstacleGridCols = 0
let obstacleGridRows = 0
let obstacleGridMinX = 0
let obstacleGridMinZ = 0
let obstacleGridStep = NAV_STEP
let obstacleDirty = true
// A* 复用的寻路缓冲区（按网格尺寸只分配一次，避免每次寻路触发 GC）。
let astarG: Float64Array | null = null
let astarF: Float64Array | null = null
let astarParent: Int32Array | null = null
let astarInOpen: Uint8Array | null = null
let astarClosed: Uint8Array | null = null
let astarHeapIndex: Int32Array | null = null

function invalidateObstacleGrid() {
  obstacleDirty = true
}

/** 逐格判断是否阻挡（保留原逻辑，用于一次性重建网格）。 */
function cellBlocked(x: number, z: number): boolean {
  const clearance = 0.18
  if (meetingWallBlocked(x, z)) return true
  const furniture = officeFurniture()
  for (const item of furniture) {
    if (!BLOCKING_FURNITURE_TYPES.has(item.type)) continue
    const size = furnitureSize(item.type, item)
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

function rebuildObstacleGrid() {
  obstacleDirty = false
  const b = navFloorBounds()
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

function blockedAt(x: number, z: number): boolean {
  if (debugOn.value) dbgBlocked += 1
  if (obstacleDirty) rebuildObstacleGrid()
  if (!obstacleGrid) return cellBlocked(x, z)
  const step = obstacleGridStep
  let ix = Math.round((x - obstacleGridMinX) / step - 0.5)
  let iz = Math.round((z - obstacleGridMinZ) / step - 0.5)
  ix = Math.max(0, Math.min(obstacleGridCols - 1, ix))
  iz = Math.max(0, Math.min(obstacleGridRows - 1, iz))
  return obstacleGrid[iz * obstacleGridCols + ix] === 1
}


/** 寻路地板范围（以原点为中心）。 */
function navFloorBounds(): { minX: number; maxX: number; minZ: number; maxZ: number } {
  const floor = officeFloor()
  return {
    minX: -floor.width / 2,
    maxX: floor.width / 2,
    minZ: -floor.depth / 2,
    maxZ: floor.depth / 2,
  }
}

/** 两点之间是否直线畅通（按点采样判断）。 */
function segmentClear(a: THREE.Vector3, b: THREE.Vector3): boolean {
  const dist = a.distanceTo(b)
  if (dist < 0.001) return true
  const steps = Math.max(2, Math.ceil(dist / 0.12))
  for (let i = 1; i < steps; i++) {
    const t = i / steps
    if (blockedAt(a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t)) return false
  }
  return true
}

/** 把网格角点路径做“弦拉直”平滑，减少锯齿。 */
function smoothPath(path: THREE.Vector3[]): THREE.Vector3[] {
  if (path.length <= 2) return path
  const out: THREE.Vector3[] = [path[0]]
  let anchor = 0
  for (let i = 2; i < path.length; i++) {
    if (!segmentClear(path[anchor], path[i])) {
      out.push(path[i - 1])
      anchor = i - 1
    }
  }
  out.push(path[path.length - 1])
  return out
}

/** 网格 A* 寻路：返回从 start 到 end 的平滑世界坐标点（避开 blockedAt 障碍）。 */
function findPath(start: THREE.Vector3, end: THREE.Vector3): THREE.Vector3[] {
  if (debugOn.value) dbgAstar += 1
  // 直线畅通时直接返回，避免不必要的网格搜索。
  if (segmentClear(start, end)) return [end.clone()]
  const b = navFloorBounds()
  const step = NAV_STEP
  const cols = Math.max(1, Math.ceil((b.maxX - b.minX) / step))
  const rows = Math.max(1, Math.ceil((b.maxZ - b.minZ) / step))
  const toCellX = (x: number) => Math.min(cols - 1, Math.max(0, Math.round((x - b.minX) / step - 0.5)))
  const toCellZ = (z: number) => Math.min(rows - 1, Math.max(0, Math.round((z - b.minZ) / step - 0.5)))
  const cellCenterX = (ix: number) => b.minX + (ix + 0.5) * step
  const cellCenterZ = (iz: number) => b.minZ + (iz + 0.5) * step
  const idx = (ix: number, iz: number) => iz * cols + ix
  const walkable = (ix: number, iz: number) => ix >= 0 && ix < cols && iz >= 0 && iz < rows && !blockedAt(cellCenterX(ix), cellCenterZ(iz))

  const sx = toCellX(start.x)
  const sz = toCellZ(start.z)
  const ex = toCellX(end.x)
  const ez = toCellZ(end.z)
  // 起点格即使被家具/会议墙占据也允许起步：仅当起终点同格时直连，
  // 否则让 A* 从起点格向外搜索，撞墙/被卡在阻挡格时可先脱离而不是“直线冲向墙”。
  if (sx === ex && sz === ez) return [end.clone()]

  const n = cols * rows
  if (!astarG || astarG.length !== n) {
    astarG = new Float64Array(n)
    astarF = new Float64Array(n)
    astarParent = new Int32Array(n)
    astarInOpen = new Uint8Array(n)
    astarClosed = new Uint8Array(n)
    astarHeapIndex = new Int32Array(n)
  }
  const g = astarG!
  const f = astarF!
  const parent = astarParent!
  const inOpen = astarInOpen!
  const closed = astarClosed!
  g.fill(Infinity)
  f.fill(Infinity)
  parent.fill(-1)
  inOpen.fill(0)
  closed.fill(0)
  // 最小二叉堆开放集，替代原先的线性扫描 + splice（O(n)），避免大网格下寻路卡顿。
  const heap: number[] = []
  const heapIndex = astarHeapIndex!
  heapIndex.fill(-1)
  const less = (a: number, b: number) => f[a] < f[b]
  const swap = (a: number, b: number) => {
    const t = heap[a]
    heap[a] = heap[b]
    heap[b] = t
    heapIndex[heap[a]] = a
    heapIndex[heap[b]] = b
  }
  const siftUp = (i: number) => {
    while (i > 0) {
      const p = (i - 1) >> 1
      if (less(heap[i], heap[p])) {
        swap(i, p)
        i = p
      } else break
    }
  }
  const siftDown = (i: number) => {
    const n = heap.length
    while (true) {
      const l = i * 2 + 1
      const r = l + 1
      let m = i
      if (l < n && less(heap[l], heap[m])) m = l
      if (r < n && less(heap[r], heap[m])) m = r
      if (m === i) break
      swap(i, m)
      i = m
    }
  }
  const push = (node: number) => {
    heap.push(node)
    heapIndex[node] = heap.length - 1
    siftUp(heap.length - 1)
  }
  const pop = (): number => {
    const top = heap[0]
    const last = heap.pop()!
    if (heap.length) {
      heap[0] = last
      heapIndex[last] = 0
      siftDown(0)
    }
    heapIndex[top] = -1
    return top
  }
  g[idx(sx, sz)] = 0
  f[idx(sx, sz)] = 0
  inOpen[idx(sx, sz)] = 1
  push(idx(sx, sz))
  const hval = (ix: number, iz: number) => {
    const dx = Math.abs(ix - ex)
    const dz = Math.abs(iz - ez)
    return dx + dz + (Math.SQRT2 - 2) * Math.min(dx, dz)
  }
  const neighbors: Array<[number, number, number]> = [
    [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
    [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2],
  ]
  // 记录已探索到的“离终点最近的可达格”，A* 无解时回退到该格而非直冲终点。
  let bestNode = idx(sx, sz)
  let bestH = hval(sx, sz)

  while (heap.length) {
    const cur = pop()
    inOpen[cur] = 0
    if (closed[cur]) continue
    closed[cur] = 1
    if (cur === idx(ex, ez)) {
      const raw: THREE.Vector3[] = []
      let c = cur
      while (c !== -1) {
        const ix = c % cols
        const iz = Math.floor(c / cols)
        raw.push(new THREE.Vector3(cellCenterX(ix), 0, cellCenterZ(iz)))
        c = parent[c]
      }
      raw.reverse()
      const smoothed = smoothPath(raw)
      smoothed.push(end.clone())
      return smoothed
    }
    const cix = cur % cols
    const ciz = Math.floor(cur / cols)
    const ch = hval(cix, ciz)
    if (ch < bestH) {
      bestH = ch
      bestNode = cur
    }
    for (const [dx, dz, cost] of neighbors) {
      const nix = cix + dx
      const niz = ciz + dz
      if (!walkable(nix, niz)) continue
      if (dx !== 0 && dz !== 0 && (!walkable(cix + dx, ciz) || !walkable(cix, ciz + dz))) continue
      const nidx = idx(nix, niz)
      if (closed[nidx]) continue
      const ng = g[cur] + cost
      if (ng < g[nidx]) {
        parent[nidx] = cur
        g[nidx] = ng
        f[nidx] = ng + hval(nix, niz)
        if (inOpen[nidx]) {
          siftUp(heapIndex[nidx])
        } else {
          inOpen[nidx] = 1
          push(nidx)
        }
      }
    }
  }
  // 目标不可达：回退到已探索到的“离终点最近的可达格”，避免直线冲向墙导致卡死。
  const raw: THREE.Vector3[] = []
  let c = bestNode
  while (c !== -1) {
    const ix = c % cols
    const iz = Math.floor(c / cols)
    raw.push(new THREE.Vector3(cellCenterX(ix), 0, cellCenterZ(iz)))
    c = parent[c]
  }
  raw.reverse()
  if (raw.length <= 1) return [end.clone()]
  return smoothPath(raw)
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
  const start = clampPointToFloor(actor.character.position.clone())
  const target = clampPointToFloor(actor.targetPosition)
  const chain: THREE.Vector3[] = []
  if (targetZone?.type === 'meeting') {
    chain.push(...meetingDoorWaypoints(targetZone).map(clampPointToFloor))
  }
  chain.push(target)
  const route: THREE.Vector3[] = []
  let prev = start
  for (const wp of chain) {
    const seg = findPath(prev, wp)
    for (const p of seg) {
      if (!route.length || p.distanceTo(route[route.length - 1]) > 0.02) route.push(p)
    }
    prev = wp
  }
  if (!route.length) route.push(target)
  actor.route = route
  actor.routeIndex = 0
  actor.walkTarget = actor.route[0] || target
  actor.routeZone = targetZone
  actor.stuckFrames = 0
  actor.lastPosX = actor.character.position.x
  actor.lastPosZ = actor.character.position.z
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
  if (editing.value && !view3D.value) editPointerDown(event)
}

function onPointerMove(event: PointerEvent) {
  if (editing.value) {
    if (!view3D.value) editPointerMove(event)
    return
  }
  if (!pointerDown) return
  const dx = Math.abs(event.clientX - pointerDown.x)
  const dy = Math.abs(event.clientY - pointerDown.y)
  if (dx > 5 || dy > 5) {
    followRoleKey = null
  }
}

function onPointerUp(event: PointerEvent) {
  if (editing.value) {
    if (!view3D.value) editPointerUp(event)
    return
  }
  const dx = Math.abs(event.clientX - pointerDown.x)
  const dy = Math.abs(event.clientY - pointerDown.y)
  if (dx > 5 || dy > 5) return
  pickActor(event.clientX, event.clientY)
}

function onWheelEdit(event: WheelEvent) {
  if (view3D.value) return
  editWheel(event)
}

function onKeyEdit(event: KeyboardEvent) {
  if (!editing.value) return
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    if (event.shiftKey) redo()
    else undo()
    return
  }
  if (event.key === 'Escape') {
    saveAndExit()
    return
  }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    removeSelected()
    return
  }
  if (event.key.toLowerCase() === 'r') {
    toggleRotate()
  }
}

function pickActor(clientX: number, clientY: number) {
  const roleKey = actorAtPointer(clientX, clientY)
  if (!roleKey) return
  followRoleKey = roleKey
  emit('select', roleKey)
}

function tick(time: number) {
  if (disposed || !scene || !camera || !renderer) return
  const dbgStart = performance.now()
  const dbgRunning = debugOn.value
  if (dbgRunning) dbgFrame += 1

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
          const dir = Math.atan2(dz, dx)
          const candidates = [0, 0.5, -0.5, 1.0, -1.0, 1.57, -1.57]
          let moved = false
          for (const off of candidates) {
            const a = dir + off
            const nx = actor.character.position.x + Math.cos(a) * step
            const nz = actor.character.position.z + Math.sin(a) * step
            if (!blockedAt(nx, nz)) {
              actor.character.position.x = nx
              actor.character.position.z = nz
              moved = true
              break
            }
          }
          if (!moved) {
            const nx = actor.character.position.x + (dx / distance) * step
            const nz = actor.character.position.z + (dz / distance) * step
            if (!blockedAt(nx, actor.character.position.z)) actor.character.position.x = nx
            else if (!blockedAt(actor.character.position.x, nz)) actor.character.position.z = nz
          }
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

    // 卡死检测：连续帧实际位置几乎不动时重算路由，避免撞墙/被阻挡格困住原地打转。
    if (actor.route.length) {
      const px = actor.character.position.x
      const pz = actor.character.position.z
      const moved = Math.hypot(px - actor.lastPosX, pz - actor.lastPosZ)
      actor.stuckFrames = moved < 0.004 ? actor.stuckFrames + 1 : 0
      actor.lastPosX = px
      actor.lastPosZ = pz
      if (actor.stuckFrames >= 30) {
        actor.stuckFrames = 0
        rebuildActorRoute(actor, actor.routeZone)
      }
    } else {
      actor.stuckFrames = 0
      actor.lastPosX = actor.character.position.x
      actor.lastPosZ = actor.character.position.z
    }

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

  const activeCamera = editing.value && editCamera.value && !view3D.value ? editCamera.value : camera
  renderer.render(scene, activeCamera)
  if (dbgRunning) {
    const frameMs = performance.now() - dbgStart
    dbgMs += frameMs
    if (frameMs > dbgWorst) dbgWorst = frameMs
    if (dbgStart > dbgNextLog) {
      dbgNextLog = dbgStart + 2000
      let meshes = 0
      scene.traverse((o) => { if ((o as THREE.Mesh).isMesh) meshes += 1 })
      debugText.value = [
        `fps~${Math.max(1, Math.round(1000 / (dbgMs / Math.max(1, dbgFrame))))}`,
        `avg ${(dbgMs / Math.max(1, dbgFrame)).toFixed(1)}ms`,
        `worst ${dbgWorst.toFixed(1)}ms`,
        `a* ${dbgAstar}`,
        `blocked ${dbgBlocked}`,
        `meshes ${meshes}`,
        `dpr ${renderer.getPixelRatio()}`,
        `res ${renderer.domElement.width}x${renderer.domElement.height}`,
        `draws ${renderer.info.render.calls}`,
        `tris ${renderer.info.render.triangles}`,
      ].join('  ')
      dbgFrame = 0
      dbgMs = 0
      dbgWorst = 0
      dbgAstar = 0
      dbgBlocked = 0
    }
  }
  if (!document.hidden) {
    rafId = requestAnimationFrame(tick)
  } else {
    renderLoopRunning = false
  }
}

function disposeActor(actor: Actor) {
  actor.group.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    // 模板克隆的 mesh 与缓存模板共享 geometry/material，资源交由模板缓存持有。
    if (mesh.userData.templateShared) return
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
  exit()
  if (routeFlushRaf) {
    cancelAnimationFrame(routeFlushRaf)
    routeFlushRaf = 0
  }
  pendingRouteZones.clear()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  resizeObserver?.disconnect()
  resizeObserver = null

  if (renderer) {
    renderer.domElement.removeEventListener('pointerdown', onPointerDown)
    renderer.domElement.removeEventListener('pointermove', onPointerMove)
    renderer.domElement.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    renderer.domElement.removeEventListener('wheel', onWheelEdit)
    renderer.domElement.removeEventListener('contextmenu', onContextEdit)
    window.removeEventListener('keydown', onKeyEdit)
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
.office-3d-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.office-3d-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: block;
}

.office-3d-cursor--select {
  cursor: default;
}

.office-3d-cursor--select-hit {
  cursor: crosshair;
}

.office-3d-cursor--pan {
  cursor: grab;
}

.office-3d-cursor--pan:active {
  cursor: grabbing;
}

.office-3d-cursor--place {
  cursor: crosshair;
}

.office-3d-cursor--grab {
  cursor: grab;
}

.office-3d-cursor--grab:active {
  cursor: grabbing;
}

.office-3d-enter {
  position: absolute;
  top: 10px;
  left: 10px;
  display: flex;
  gap: 6px;
  align-items: center;
  z-index: 5;
}

.office-3d-topbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 7px 12px;
  background: linear-gradient(180deg, rgba(13, 20, 36, 0.96), rgba(13, 20, 36, 0.78));
  border-bottom: 1px solid rgba(120, 170, 255, 0.16);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
  z-index: 7;
}

.office-3d-topbar-sep {
  width: 1px;
  align-self: stretch;
  background: rgba(255, 255, 255, 0.1);
  margin: 0 4px;
}

.office-3d-toolgroup {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
}

.office-3d-tool {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 27px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #c5d6f2;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.office-3d-tool .anticon {
  font-size: 15px;
}

.office-3d-tool:hover {
  background: rgba(120, 170, 255, 0.16);
  color: #fff;
  border-color: rgba(120, 170, 255, 0.35);
}

.office-3d-tool:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.office-3d-tool.is-active {
  background: linear-gradient(180deg, #3b82f6, #2563eb);
  color: #fff;
  border-color: rgba(120, 170, 255, 0.5);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.45);
}

.office-3d-tool--save {
  background: linear-gradient(180deg, #2f9e6f, #1f7a50);
  border-color: rgba(90, 220, 160, 0.4);
  color: #eafff4;
  font-weight: 600;
}

.office-3d-tool--save:hover {
  background: linear-gradient(180deg, #34b57d, #23855a);
  color: #fff;
  border-color: rgba(90, 220, 160, 0.6);
}

.office-3d-tool--danger {
  color: #ff7a85;
}

.office-3d-tool--danger:hover {
  background: rgba(255, 90, 100, 0.16);
  color: #ff9aa2;
  border-color: rgba(255, 90, 100, 0.4);
}

.office-3d-zoom-pct {
  min-width: 44px;
  text-align: center;
  color: #c5d6f2;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.office-3d-side {
  position: absolute;
  top: 56px;
  left: 10px;
  bottom: 10px;
  display: flex;
  flex-direction: column;
  width: 210px;
  background: rgba(9, 14, 26, 0.8);
  border: 1px solid rgba(120, 170, 255, 0.16);
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(10px);
  z-index: 6;
  overflow: hidden;
}

.office-3d-side-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.office-3d-side-tab {
  flex: 1;
  height: 34px;
  padding: 0;
  border: none;
  background: transparent;
  color: #8aa0c8;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.office-3d-side-tab:hover {
  color: #cfe0ff;
}

.office-3d-side-tab.is-active {
  color: #fff;
  border-bottom-color: #3b82f6;
}

.office-3d-side-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.office-3d-side-section {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #7f9bd0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 10px 6px 4px;
}

.office-3d-side-section--group {
  margin-top: 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.office-3d-side-section--group .anticon {
  font-size: 13px;
  color: #6f8cc4;
}

.office-3d-side-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 2px 8px;
  padding: 0 8px;
  height: 30px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 7px;
}

.office-3d-side-search .anticon {
  color: #7f9bd0;
  font-size: 14px;
}

.office-3d-side-search input {
  flex: 1;
  border: none;
  background: transparent;
  color: #fff;
  font-size: 12px;
  outline: none;
}

.office-3d-side-search input::placeholder {
  color: rgba(255, 255, 255, 0.35);
}

.office-3d-side-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #dbe6ff;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.office-3d-side-row > .anticon {
  font-size: 16px;
  color: #8aa0c8;
  width: 18px;
  text-align: center;
  flex: none;
}

.office-3d-side-row:hover {
  background: rgba(120, 170, 255, 0.12);
  border-color: rgba(120, 170, 255, 0.2);
}

.office-3d-side-row.is-active {
  background: rgba(59, 130, 246, 0.22);
  border-color: rgba(59, 130, 246, 0.4);
  color: #fff;
}

.office-3d-side-row.is-active > .anticon {
  color: #8ac0ff;
}

.office-3d-side-row:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.office-3d-side-row--room > .anticon {
  color: #7aa6e8;
}

.office-3d-side-row--danger > .anticon {
  color: #ff7a85;
}

.office-3d-side-row-main {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.office-3d-side-row-main b {
  font-size: 13px;
  font-weight: 600;
}

.office-3d-side-row-main i {
  font-size: 11px;
  color: #7f93ba;
  font-style: normal;
}

.office-3d-props {
  position: absolute;
  top: 56px;
  right: 10px;
  bottom: 10px;
  width: 220px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  background: rgba(9, 14, 26, 0.72);
  border: 1px solid rgba(120, 170, 255, 0.18);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(8px);
  z-index: 6;
  color: #fff;
}

.office-3d-props--hidden {
  display: none;
}

.office-3d-props-title {
  color: #a2c8ff;
  font-size: 12px;
  font-weight: 600;
}

.office-3d-props label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.office-3d-props input {
  width: 72px;
  box-sizing: border-box;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 12px;
}

.office-3d-inspector {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 10px;
  align-items: center;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  z-index: 5;
}

.office-3d-inspector label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.office-3d-inspector input {
  width: 64px;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 4px;
  padding: 2px 6px;
}

.office-3d-inspector-title {
  color: #a2c8ff;
}

.office-3d-wrap--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #0d1320;
}

.office-3d-zoom-pct {
  min-width: 48px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
</style>
