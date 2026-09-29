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

          <div class="office-3d-toolgroup office-3d-toolgroup--end">
            <a-popconfirm
              title="用默认样板替换当前布局？保存前可撤销。"
              ok-text="恢复样板"
              cancel-text="取消"
              placement="bottomRight"
              :overlay-style="{ zIndex: 10000 }"
              @confirm="resetToSample"
            >
              <button type="button" class="office-3d-tool office-3d-tool--danger" title="用默认样板替换当前编辑内容（保存后才写入）"><RollbackOutlined /><span>恢复样板</span></button>
            </a-popconfirm>
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
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { createCharacterAssetStore, loadCharacterAsset } from '@/office3d/assets/gltfCache'
import { envMaterial, applyShadow } from '@/office3d/environment/materials'
import { buildFloor, createRectangularGrid } from '@/office3d/environment/floor'
import { createWindowedBackWall, createSideWall, buildTerrace, buildCeilingEdges, buildLighting } from '@/office3d/environment/walls'
import { buildProps } from '@/office3d/environment/furniture'
import { clampFurnitureSize, furnitureMinSize, FURNITURE_MAX_SIZE, SYMMETRIC_FURNITURE_TYPES, furnitureSize as sizeOfCatalog } from '@/office3d/environment/furnitureSize'
import { WALK_SPEED } from '@/office3d/characters/metrics'
import { createActorSystem } from '@/office3d/characters/actorSystem'
import type { BehaviorConfig, OfficeColleagueStatus, OfficeConfig, OfficeEnvironmentTheme, OfficeFurnitureItem, OfficeZone } from '@/api/office'
import { officeApi } from '@/api/office'
import { message } from 'ant-design-vue'
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
  RollbackOutlined,
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
import { createNavWorld, type MeetingBounds, type MeetingDoorSide } from '@/office3d/nav/world'

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
  'open-mission': [roleKey: string]
  'save-config': [config: OfficeConfig]
}>()



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
  applySample,
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
  for (const actor of actors.actorMap.values()) {
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

async function resetToSample() {
  try {
    const { office } = await officeApi.getOfficeSample()
    if (!office) return
    applySample(office)
    message.success('已替换为样板，保存后才写入；Ctrl+Z 可撤销')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '样板加载失败')
  }
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
  if (!editing.value || view3D.value) {
    return hoveredRoleKey.value ? 'office-3d-cursor--pointer' : 'office-3d-cursor--grab'
  }
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
// 悬停命中的同事：驱动光标与名牌显示（探测限频，见 onPointerMove）
const hoveredRoleKey = ref<string | null>(null)
let hoverProbeAt = 0

// 角色资产 store（R2 自本文件抽出）：加载分派（GLB/VRM）与缓存逻辑在 office3d/assets/gltfCache。
const characterAssets = createCharacterAssetStore(loadCharacterAsset)
let lastFrameTime = 0
let renderLoopRunning = false

// 路由重算的按帧去抖：仅当 actor 终点真正变化时入队，下一帧统一重算 A*。

// 配置 watcher 的布局/模型/状态签名缓存，用于判断是否真的需要重建。
let lastLayoutSig = ''
let lastModelSig = ''
let lastStatusSig = ''

// 临时调诊断计数（仅 debugOn 时累加，不参与逻辑）。
let dbgFrame = 0
let dbgMs = 0
let dbgWorst = 0
let dbgNextLog = 0


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

/** 旧签名兼容壳：catalog 由当前配置注入（实现已迁 office3d/environment/furnitureSize）。 */
function furnitureSize(type: string, item?: OfficeFurnitureItem) {
  return sizeOfCatalog(officeConfigValue().furniture_catalog, type, item)
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

/** 输入尺寸下限：薄壁/挂墙类允许更小深度，其余给到 0.2 防止塌成 0。 */
/** 圆形/对称家具：宽深必须一致，避免拉成椭圆。 */



/** 家具尺寸的单一数据源：单件覆盖 -> 配置 catalog（后端下发）-> 前端回退表。 */

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

// 导航世界（R1 自本文件抽出）：障碍网格/寻路/房间几何的宿主，配置经 NavSource 注入。
const navWorld = createNavWorld({
  floor: () => officeFloor(),
  zones: () => officeZones(),
  furniture: () => officeFurniture(),
  furnitureSize: (type, item) => furnitureSize(type, item),
  debug: () => debugOn.value,
})

// 角色系统（R4b 自本文件抽出）：生命周期/状态机/路由在 office3d/characters/actorSystem。
const actors = createActorSystem({
  scene: () => scene,
  colleagues: () => props.colleagues,
  statusMap: () => props.statusMap,
  furniture: () => officeFurniture(),
  zones: () => officeZones(),
  config: () => officeConfigValue(),
  behaviorConfig: () => behaviorConfigValue(),
  theme: () => officeTheme(),
  statusMetaFor,
  statusColorHex,
  statusTextFor,
  selectedRoleKey: () => props.selectedRoleKey ?? null,
  hoveredRoleKey: () => hoveredRoleKey.value,
  navWorld,
  assets: characterAssets,
})






/** 重建所有会议区的座位分配：只让“确实要去该会议区”的角色参与占座，按同事顺序依次分配空位，避免哈希撞座。 */



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
    actors.rebuildActors()
  },
  { deep: true },
)

watch(
  () => props.statusMap,
  () => actors.applyStatuses(),
  { deep: true },
)

watch(
  () => props.selectedRoleKey,
  () => {
    actors.updateSelection()
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
    if (modelChanged) await characterAssets.reload(officeConfigValue().character_models || [])

    // 布局或模型变化才重建 actor；仅状态映射变化只重算目标，不重建场景。
    if (layoutChanged || modelChanged) {
      actors.rebuildActors()
      setEnvironmentVisible(true)
      setActorsVisible(true)
    } else if (statusChanged) {
      actors.applyStatuses()
    }
  },
  { deep: true },
)

watch(
  () => props.behaviorConfig,
  () => actors.applyStatuses(),
  { deep: true },
)

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

  // F1 精细度·环境光贴图（IBL）：全场材质获得反射质感。桌面档启用，移动档跳过省内存与带宽。
  if (!window.matchMedia('(max-width: 860px)').matches) {
    const pmrem = new THREE.PMREMGenerator(renderer)
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    scene.environmentIntensity = 0.45
    pmrem.dispose()
  }

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
    characterAssets.reload(officeConfigValue().character_models || []).then(() => {
      actors.rebuildActors()
      actors.applyStatuses()
      actors.updateSelection()
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
  navWorld.invalidate()
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

  buildFloor(theme, width, depth, environment)
  buildWalls(theme, width, depth, wallHeight, wallThickness)
  buildTerrace(theme, width, depth, environment)
  buildCeilingEdges(theme, width, depth, wallHeight, wallThickness, environment)
  buildLighting(theme, width, depth, wallHeight, environment)
  buildProps(theme, width, depth, wallHeight, environment, officeFurniture(), officeConfigValue().furniture_catalog)

  for (const zone of officeZones()) {
    if (zone.room === true || zone.type === 'meeting') {
      if (zone.type === 'meeting') buildMeetingRoom(zone)
      else buildRoomShell(zone)
    }
  }

  scene.add(environment)
}









function officeWallDoorGap(targetWall: 'left' | 'right' | 'back'): { center: number; width: number } | null {
  for (const zone of officeZones()) {
    if (zone.type !== 'meeting') continue
    const side = navWorld.meetingDoorSide(zone)
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

function buildMeetingRoom(zone: OfficeZone, parent: THREE.Group | null = environment) {
  const theme = officeTheme()
  const floor = officeFloor()
  const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
  const bounds = navWorld.meetingRoomBounds(zone)
  const doorSide = navWorld.meetingDoorSide(zone)
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

  // 门扇（半开、向房间内侧敞开）：办公室墙不参与寻路，纯装饰
  const openAngle = 1.2
  const leafLen = Math.max(0.6, doorWidth - 0.1)
  const leafH = doorH - 0.08
  const doorLeafMat = envMaterial(theme.palette?.furniture_light || '#8a6b4e', 0.5, 0.2)
  const hinge = new THREE.Group()
  const leaf = new THREE.Mesh(new THREE.BoxGeometry(leafLen, leafH, 0.06), doorLeafMat)
  leaf.position.set(leafLen / 2, leafH / 2 + 0.04, 0)
  applyShadow(leaf)
  hinge.add(leaf)
  const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.14, 10), frameMat)
  knob.rotation.x = Math.PI / 2
  knob.position.set(leafLen - 0.15, 1.0, 0)
  hinge.add(knob)
  if (doorSide === 'back') {
    hinge.position.set(doorCenterX - doorWidth / 2 + 0.04, 0, minZ)
    hinge.rotation.y = -openAngle
  } else if (doorSide === 'front') {
    hinge.position.set(doorCenterX + doorWidth / 2 - 0.04, 0, maxZ)
    hinge.rotation.y = Math.PI - openAngle
  } else if (doorSide === 'left') {
    hinge.position.set(minX, 0, doorCenterZ - doorWidth / 2 + 0.04)
    hinge.rotation.y = -Math.PI / 2 + openAngle
  } else {
    hinge.position.set(maxX, 0, doorCenterZ + doorWidth / 2 - 0.04)
    hinge.rotation.y = Math.PI / 2 + openAngle
  }
  group.add(hinge)

  return group
}

function buildRoomShell(zone: OfficeZone, parent: THREE.Group | null = environment) {
  const theme = officeTheme()
  const center = new THREE.Vector3(zone.position?.x ?? 0, 0, zone.position?.z ?? 0)
  const bounds = navWorld.meetingRoomBounds(zone)
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
  const bounds = navWorld.meetingRoomBounds(zone)
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
    if (Array.isArray(material)) material.forEach(actors.disposeMaterial)
    else if (material) actors.disposeMaterial(material)
  })
}












/** 把已入队的 actor 路由重算合并到下一帧执行，避免同一帧多次推送导致全量 A*。 */




/** 判断目标的落点 / 归属区域 / 朝向是否相对上一状态发生了变化。 */








watch(hoveredRoleKey, () => actors.updateSelection())

function roleKeyUpward(obj: THREE.Object3D): string | null {
  let node: THREE.Object3D | null = obj
  while (node) {
    if (node.userData?.roleKey) return node.userData.roleKey as string
    node = node.parent
  }
  return null
}

function actorAtPointer(clientX: number, clientY: number): { roleKey: string; mesh: THREE.Object3D } | null {
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
  for (const actor of actors.actorMap.values()) {
    targets.push(actor.group)
  }

  const intersections = raycaster.intersectObjects(targets, true)
  if (!intersections.length) return null

  // 气泡/名牌是 HUD 板：不参与命中判定，否则从俯视角会整片挡住桌面；
  // 只在身后没有实体 mesh 时兜底（点空气里的气泡 = 选中该同事）
  let spriteRoleKey: string | null = null
  for (const it of intersections) {
    const obj = it.object
    if ((obj as THREE.Sprite).isSprite) {
      if (!spriteRoleKey) spriteRoleKey = roleKeyUpward(obj)
      continue
    }
    const roleKey = roleKeyUpward(obj)
    if (!roleKey) continue
    return { roleKey, mesh: obj }
  }
  return spriteRoleKey ? { roleKey: spriteRoleKey, mesh: intersections[0].object } : null
}

function onPointerDown(event: PointerEvent) {
  pointerDown = { x: event.clientX, y: event.clientY }
  if (editing.value && !view3D.value) editPointerDown(event)
}

function onPointerMove(event: PointerEvent) {
  if (editing.value) {
    if (!view3D.value) editPointerMove(event)
    hoveredRoleKey.value = null
    return
  }
  const dx = Math.abs(event.clientX - pointerDown.x)
  const dy = Math.abs(event.clientY - pointerDown.y)
  if (dx > 5 || dy > 5) {
    followRoleKey = null
  }
  // 拖拽/按压中不探测；空闲时限频 ~10Hz，驱动悬停光标与名牌
  if (event.buttons !== 0) {
    hoveredRoleKey.value = null
    return
  }
  const now = performance.now()
  if (now - hoverProbeAt < 100) return
  hoverProbeAt = now
  const hit = actorAtPointer(event.clientX, event.clientY)
  hoveredRoleKey.value = hit ? hit.roleKey : null
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
  const hit = actorAtPointer(clientX, clientY)
  if (!hit) return
  followRoleKey = hit.roleKey
  emit('select', hit.roleKey)
  if (hit.mesh.userData?.monitor) emit('open-mission', hit.roleKey)
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
    const followActor = actors.actorMap.get(followRoleKey)
    if (followActor) {
      const followTarget = followActor.character.position.clone().add(new THREE.Vector3(0, 1.05, 0))
      controls.target.lerp(followTarget, 0.08)
    }
  }

  controls?.update()
  // 头顶信息:事件气泡淡出、等待输入脉冲、悬停常显
  actors.updateOverheads(performance.now())

  for (const actor of actors.actorMap.values()) {
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
            if (!navWorld.blockedAt(nx, nz)) {
              actor.character.position.x = nx
              actor.character.position.z = nz
              moved = true
              break
            }
          }
          if (!moved) {
            const nx = actor.character.position.x + (dx / distance) * step
            const nz = actor.character.position.z + (dz / distance) * step
            if (!navWorld.blockedAt(nx, actor.character.position.z)) actor.character.position.x = nx
            else if (!navWorld.blockedAt(actor.character.position.x, nz)) actor.character.position.z = nz
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
        actors.rebuildActorRoute(actor, actor.routeZone)
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
        `a* ${navWorld.stats.astar}`,
        `blocked ${navWorld.stats.blocked}`,
        `meshes ${meshes}`,
        `dpr ${renderer.getPixelRatio()}`,
        `res ${renderer.domElement.width}x${renderer.domElement.height}`,
        `draws ${renderer.info.render.calls}`,
        `tris ${renderer.info.render.triangles}`,
      ].join('  ')
      dbgFrame = 0
      dbgMs = 0
      dbgWorst = 0
      navWorld.stats.astar = 0
      navWorld.stats.blocked = 0
    }
  }
  if (!document.hidden) {
    rafId = requestAnimationFrame(tick)
  } else {
    renderLoopRunning = false
  }
}



function dispose() {
  disposed = true
  stopRenderLoop()
  exit()
  actors.cancelPendingRoutes()
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

  for (const actor of actors.actorMap.values()) {
    actors.disposeActor(actor)
  }
  actors.actorMap.clear()

  if (environment) {
    environment.traverse((obj) => {
      const mesh = obj as THREE.Mesh
      if (mesh.geometry) mesh.geometry.dispose()
      const material = (mesh as any).material
      if (Array.isArray(material)) material.forEach(actors.disposeMaterial)
      else if (material) actors.disposeMaterial(material)
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

.office-3d-cursor--pointer {
  cursor: pointer;
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

.office-3d-toolgroup--end {
  margin-left: auto;
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
