<script setup lang="ts">
/**
 * ServerAnatomyEditor —— 服务器图纸标注 + 图层编辑「编辑态」公共组件。
 * 两种工作模式：
 *  - 标注模式（绘制/选择）：PixiJS 画布上圈区域（热区 ↔ 规则关联）。
 *  - 图层模式：直接在矢量 SVG 上点选/移动/缩放/旋转图层元素，兑现分层意义；
 *    编辑结果通过 emit('saveSvg') 由父组件调用保存接口整份落盘。
 * 坐标一律以 viewBox 世界坐标存储（不存像素），与 ServerAnatomyViewer 同一坐标系。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Application, Container, Graphics, Text } from 'pixi.js'
import type { DrawingRegion, DrawingViewBox, DrawingLayerMeta } from '@/api/serverDrawing'
import { REGION_KIND_LABELS } from '@/constants/serverAnatomy'
import { applyLayerMeta, serializeSvg, elementBBox } from '@/utils/svgLayers'

const props = withDefaults(defineProps<{
  svgUrl?: string | null
  viewBox?: DrawingViewBox | null
  regions?: DrawingRegion[]
  layers?: DrawingLayerMeta[]
}>(), { svgUrl: null, viewBox: null, regions: () => [], layers: () => [] })
const emit = defineEmits<{
  change: [regions: DrawingRegion[]]
  select: [uid: string | null]
  /** 图层模式：选中图层（画布点击 / 面板点击同步） */
  layerSelect: [id: string | null]
  /** 图层内容被编辑（移动/缩放/删除/复制等），父组件应置 dirty 并开启保存 */
  layerChanged: []
  /** 请求保存编辑后的整份 SVG（父组件调用 saveSvg 接口） */
  saveSvg: [svg: string]
  /** SVG 底图就绪（父组件解析图层树用） */
  svgReady: [svg: SVGSVGElement]
}>()

const host = ref<HTMLDivElement | null>(null)
const vb = computed<DrawingViewBox>(() => props.viewBox ?? [0, 0, 1000, 560])

const ACCENT = 0x1677ff
const SELECT = 0x52c41a
const MIN_SIZE = 4 // viewBox 单位，防止误点出零尺寸框

const regions = ref<DrawingRegion[]>([])
const selectedUid = ref<string | null>(null)
const mode = ref<'select' | 'draw' | 'layer'>('draw')
/** 图层编辑状态 */
const selectedLayerId = ref<string | null>(null)
const layerDirty = ref(false)
let layerState: {
  el: Element
  wrapper: SVGGElement
  cx: number
  cy: number
  rot: number
  sx: number
  sy: number
  tx: number
  ty: number
} | null = null
type UndoEntry = { kind: 'regions'; regions: DrawingRegion[] } | { kind: 'svg'; markup: string }
const undoStack = ref<UndoEntry[]>([])
const dirty = ref(false)

let app: Application | null = null
let regionLayer: Container | null = null
let uiLayer: Container | null = null
let previewLayer: Container | null = null
let hovered: string | null = null
let ro: ResizeObserver | null = null
/** 底图（矢量）：内联 SVG 文本 + 定位层（与 Pixi 世界坐标共用 scale/tx/ty 变换） */
const svgMarkup = ref('')
const svgLayerEl = ref<HTMLDivElement | null>(null)

// view transform: screen = world * scale + (tx, ty)
let scale = 1
let tx = 0
let ty = 0
let cw = 100
let ch = 100

// 交互状态
let drawing: { startX: number; startY: number } | null = null
let ghost: { x: number; y: number; w: number; h: number } | null = null
let dragging: { uid: string; lastWorldX: number; lastWorldY: number } | null = null
let resizing: { handle: 'nw' | 'ne' | 'sw' | 'se'; orig: DrawingRegion; startWorldX: number; startWorldY: number } | null = null
let panning: { startClientX: number; startClientY: number; origTx: number; origTy: number } | null = null

const worldToScreen = (x: number, y: number) => ({ x: x * scale + tx, y: y * scale + ty })
const screenToWorld = (px: number, py: number) => ({ x: (px - tx) / scale, y: (py - ty) / scale })

// ── 撤销（热区 + 图层 SVG 统一栈）──
function snapshot() {
  if (undoStack.value.length > 30) undoStack.value.shift()
  undoStack.value.push({ kind: 'regions', regions: JSON.parse(JSON.stringify(regions.value)) })
}
/** 离散图层操作（删除/复制/改属性/重置变换）前快照整份 SVG */
function pushSvgUndo() {
  const svg = svgEl()
  if (!svg) return
  if (undoStack.value.length > 30) undoStack.value.shift()
  undoStack.value.push({ kind: 'svg', markup: serializeSvg(svg) })
}
/** 图层手势（拖拽/缩放/旋转）开始时的快照；pointerup 确有变化才入栈 */
let gestureSnapshot: string | null = null
let gestureMutated = false
function beginGesture() {
  const svg = svgEl()
  gestureSnapshot = svg ? serializeSvg(svg) : null
  gestureMutated = false
}
function endGesture() {
  if (gestureSnapshot && gestureMutated) {
    if (undoStack.value.length > 30) undoStack.value.shift()
    undoStack.value.push({ kind: 'svg', markup: gestureSnapshot })
  }
  gestureSnapshot = null
  gestureMutated = false
}
async function restoreSvg(markup: string) {
  clearLayerSelection()
  svgMarkup.value = markup
  await nextTick()
  const svg = svgEl()
  if (svg) {
    applyLayerMeta(svg, props.layers)
    emit('svgReady', svg)
  }
  layoutBg()
  redraw()
  markLayerDirty()
}
function undo() {
  const entry = undoStack.value.pop()
  if (!entry) return
  if (entry.kind === 'regions') {
    regions.value = entry.regions
    selectedUid.value = null
    dirty.value = true
    redraw()
  } else {
    restoreSvg(entry.markup)
  }
}
const canUndo = computed(() => undoStack.value.length > 0)

function uid() {
  return 'r' + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-4)
}

// ── Pixi 初始化 ──
async function init() {
  if (!host.value || app) return
  app = new Application()
  await app.init({
    resizeTo: host.value,
    backgroundAlpha: 0,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })
  host.value.appendChild(app.canvas)
  app.canvas.style.display = 'block'
  // 标注层盖在矢量 SVG 底图之上（DOM 顺序由 Vue 管理，用 z-index 保证层级）
  app.canvas.style.position = 'relative'
  app.canvas.style.zIndex = '2'
  regionLayer = new Container()
  uiLayer = new Container()
  previewLayer = new Container()
  app.stage.addChild(regionLayer)
  app.stage.addChild(uiLayer)
  app.stage.addChild(previewLayer)
  await loadBg()
  fit()
  layoutBg()
  redraw()
  const c = app.canvas
  c.addEventListener('pointerdown', onDown)
  c.addEventListener('pointermove', onMove)
  c.addEventListener('pointerup', onUp)
  c.addEventListener('pointerleave', onLeave)
  c.addEventListener('pointercancel', onUp)
  c.addEventListener('wheel', onWheel, { passive: false })
  ro = new ResizeObserver(() => { layout(); redraw() })
  ro.observe(host.value)
  bindSvgLayerEvents()
}

async function loadBg() {
  svgMarkup.value = ''
  if (!props.svgUrl) return
  try {
    const res = await fetch(props.svgUrl)
    if (!res.ok) return
    const text = await res.text()
    // 后端已白名单清洗；前端再兜底一道，避免任何内联脚本/事件进入 v-html
    if (!/<svg[\s>]/i.test(text) || /<script|on(load|error|click)\s*=/i.test(text)) return
    svgMarkup.value = text
    await nextTick()
    const svg = svgEl()
    if (svg) {
      applyLayerMeta(svg, props.layers)
      emit('svgReady', svg)
    }
    clearLayerSelection()
    layoutBg()
  } catch {
    svgMarkup.value = ''
  }
}

/** 把内联 SVG 定位到当前世界坐标变换（scale/tx/ty）下，矢量渲染任意缩放清晰 */
function layoutBg() {
  const el = svgLayerEl.value
  if (!el) return
  const [, , vw, vh] = vb.value
  el.style.left = tx + 'px'
  el.style.top = ty + 'px'
  el.style.width = vw * scale + 'px'
  el.style.height = vh * scale + 'px'
}

function fit() {
  if (!host.value) return
  cw = Math.max(host.value.clientWidth, 40)
  ch = Math.max(host.value.clientHeight, 40)
  const [, , vw, vh] = vb.value
  scale = Math.min(cw / vw, ch / vh) * 0.96
  tx = (cw - vw * scale) / 2
  ty = (ch - vh * scale) / 2
}

function layout() {
  if (!host.value) return
  cw = Math.max(host.value.clientWidth, 40)
  ch = Math.max(host.value.clientHeight, 40)
  layoutBg()
}

function clampWorld(p: { x: number; y: number }) {
  const [, , vw, vh] = vb.value
  return { x: Math.min(Math.max(p.x, 0), vw), y: Math.min(Math.max(p.y, 0), vh) }
}

// ── 绘制 ──
function redraw() {
  if (!app) return
  drawRegions()
  drawHandles()
  drawPreview()
}

function drawRegions() {
  if (!regionLayer) return
  for (const c of regionLayer.removeChildren()) c.destroy({ children: true })
  for (const r of regions.value) {
    const { x, y } = worldToScreen(r.x, r.y)
    const w = r.width * scale
    const h = r.height * scale
    const isSel = selectedUid.value === r.uid
    const isHov = hovered === r.uid
    const g = new Graphics()
    g.roundRect(x, y, w, h, 6)
    g.fill({ color: ACCENT, alpha: isSel ? 0.4 : isHov ? 0.28 : 0.14 })
    g.stroke({ width: isSel ? 2.6 : 1.5, color: isSel ? SELECT : ACCENT, alpha: isSel ? 1 : 0.75 })
    regionLayer.addChild(g)
    if (w > 30) {
      const t = new Text({
        text: r.name,
        style: { fontSize: 12, fontWeight: '600', fill: 0xdfe6f2, fontFamily: 'inherit' },
      })
      t.anchor.set(0.5, 0)
      t.position.set(x + w / 2, y + Math.max(h - 22, 4))
      regionLayer.addChild(t)
    }
  }
}

function handlePositions(r: DrawingRegion) {
  const a = worldToScreen(r.x, r.y)
  const b = worldToScreen(r.x + r.width, r.y + r.height)
  return {
    nw: { x: a.x, y: a.y },
    ne: { x: b.x, y: a.y },
    sw: { x: a.x, y: b.y },
    se: { x: b.x, y: b.y },
  }
}

function drawHandles() {
  if (!uiLayer) return
  for (const c of uiLayer.removeChildren()) c.destroy({ children: true })
  const sel = regions.value.find(r => r.uid === selectedUid.value)
  if (!sel) return
  const hps = handlePositions(sel)
  const HS = 8
  for (const k of ['nw', 'ne', 'sw', 'se'] as const) {
    const p = hps[k]
    const g = new Graphics()
    g.rect(p.x - HS / 2, p.y - HS / 2, HS, HS)
    g.fill({ color: 0xffffff, alpha: 1 })
    g.stroke({ width: 1.6, color: SELECT, alpha: 1 })
    g.eventMode = 'static'
    g.cursor = k === 'nw' || k === 'se' ? 'nwse-resize' : 'nesw-resize'
    uiLayer.addChild(g)
  }
}

function drawPreview() {
  if (!previewLayer) return
  for (const c of previewLayer.removeChildren()) c.destroy({ children: true })
  if (!ghost) return
  const a = worldToScreen(ghost.x, ghost.y)
  const g = new Graphics()
  g.roundRect(a.x, a.y, ghost.w * scale, ghost.h * scale, 4)
  g.fill({ color: SELECT, alpha: 0.2 })
  g.stroke({ width: 1.5, color: SELECT, alpha: 0.9 })
  previewLayer.addChild(g)
}

function hitRegionWorld(p: { x: number; y: number }): DrawingRegion | null {
  for (const r of [...regions.value].reverse()) {
    if (p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height) return r
  }
  return null
}

function hitHandleScreen(px: number, py: number): 'nw' | 'ne' | 'sw' | 'se' | null {
  const sel = regions.value.find(r => r.uid === selectedUid.value)
  if (!sel) return null
  const hps = handlePositions(sel)
  const HS = 10
  for (const k of ['nw', 'ne', 'sw', 'se'] as const) {
    const p = hps[k]
    if (Math.abs(px - p.x) <= HS && Math.abs(py - p.y) <= HS) return k
  }
  return null
}

// ── 交互 ──
function onDown(e: PointerEvent) {
  if (!app) return
  const rect = app.canvas.getBoundingClientRect()
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  const p = screenToWorld(px, py)

  // 中键按住 → 平移画布（任意模式生效，同时阻止浏览器中键自动滚动）
  if (e.button === 1) {
    e.preventDefault()
    panning = { startClientX: px, startClientY: py, origTx: tx, origTy: ty }
    app.canvas.style.cursor = 'grabbing'
    return
  }

  if (mode.value === 'draw') {
    drawing = { startX: p.x, startY: p.y }
    ghost = { x: p.x, y: p.y, w: 0, h: 0 }
    drawPreview()
    return
  }
  // select 模式：优先控制点 → 区域 → 空白（平移）
  const h = hitHandleScreen(px, py)
  if (h && selectedUid.value) {
    snapshot()
    const sel = regions.value.find(r => r.uid === selectedUid.value)!
    resizing = { handle: h, orig: JSON.parse(JSON.stringify(sel)), startWorldX: p.x, startWorldY: p.y }
    return
  }
  const r = hitRegionWorld(p)
  if (r) {
    snapshot()
    selectedUid.value = r.uid
    dragging = { uid: r.uid, lastWorldX: p.x, lastWorldY: p.y }
    redraw()
    return
  }
  selectedUid.value = null
  redraw()
  panning = { startClientX: px, startClientY: py, origTx: tx, origTy: ty }
}

function onMove(e: PointerEvent) {
  if (!app) return
  const rect = app.canvas.getBoundingClientRect()
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  const p = screenToWorld(px, py)

  if (drawing) {
    const a = clampWorld({ x: Math.min(drawing.startX, p.x), y: Math.min(drawing.startY, p.y) })
    const b = clampWorld({ x: Math.max(drawing.startX, p.x), y: Math.max(drawing.startY, p.y) })
    ghost = { x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y }
    drawPreview()
    return
  }
  if (resizing) {
    const sel = regions.value.find(r => r.uid === selectedUid.value)
    if (!sel) return
    const dx = p.x - resizing.startWorldX
    const dy = p.y - resizing.startWorldY
    const o = resizing.orig
    let nx = o.x, ny = o.y, nw = o.width, nh = o.height
    if (resizing.handle.includes('e')) nw = o.width + dx
    if (resizing.handle.includes('s')) nh = o.height + dy
    if (resizing.handle.includes('w')) { nx = o.x + dx; nw = o.width - dx }
    if (resizing.handle.includes('n')) { ny = o.y + dy; nh = o.height - dy }
    if (nw < MIN_SIZE) { if (resizing.handle.includes('w')) nx = o.x + o.width - MIN_SIZE; nw = MIN_SIZE }
    if (nh < MIN_SIZE) { if (resizing.handle.includes('n')) ny = o.y + o.height - MIN_SIZE; nh = MIN_SIZE }
    sel.x = Math.round(nx); sel.y = Math.round(ny)
    sel.width = Math.round(nw); sel.height = Math.round(nh)
    dirty.value = true
    redraw()
    return
  }
  if (dragging) {
    const r = regions.value.find(x => x.uid === dragging!.uid)
    if (!r) return
    const dx = p.x - dragging.lastWorldX
    const dy = p.y - dragging.lastWorldY
    r.x = Math.round(Math.min(Math.max(r.x + dx, 0), vb.value[2] - r.width))
    r.y = Math.round(Math.min(Math.max(r.y + dy, 0), vb.value[3] - r.height))
    dragging.lastWorldX = p.x
    dragging.lastWorldY = p.y
    dirty.value = true
    redraw()
    return
  }
  if (panning) {
    tx = panning.origTx + (px - panning.startClientX)
    ty = panning.origTy + (py - panning.startClientY)
    layoutBg()
    redraw()
    return
  }
  // hover
  const r = hitRegionWorld(p)
  const next = r ? r.uid : null
  if (next !== hovered) {
    hovered = next
    app.canvas.style.cursor = next ? 'move' : 'default'
    redraw()
  }
}

function onUp() {
  if (drawing) {
    if (ghost && ghost.w >= MIN_SIZE && ghost.h >= MIN_SIZE) {
      snapshot()
      regions.value.push({
        uid: uid(), name: '', region_type: 'plain',
        x: Math.round(ghost.x), y: Math.round(ghost.y),
        width: Math.round(ghost.w), height: Math.round(ghost.h),
      })
      selectedUid.value = regions.value[regions.value.length - 1].uid
      dirty.value = true
      openForm(selectedUid.value)
    }
    drawing = null
    ghost = null
    drawPreview()
  }
  if (dragging || resizing) {
    // 移动/拉伸期间已多次标记 dirty；这里收尾（撤销栈在操作开始时已有快照）
  }
  dragging = null
  resizing = null
  if (panning && app) app.canvas.style.cursor = hovered ? 'move' : 'default'
  panning = null
}

function onLeave() {
  hovered = null
  if (app) app.canvas.style.cursor = 'default'
  redraw()
}

function onWheel(e: WheelEvent) {
  if (!app) return
  e.preventDefault()
  const rect = app.canvas.getBoundingClientRect()
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  const before = screenToWorld(px, py)
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  scale = Math.min(Math.max(scale * factor, 0.1), 12)
  tx = px - before.x * scale
  ty = py - before.y * scale
  layoutBg()
  redraw()
}

// ── 区域表单 ──
const formOpen = ref(false)
const form = reactive({ name: '', region_type: 'plain' as DrawingRegion['region_type'], remark: '' })
const formUid = ref<string | null>(null)

function openForm(uidv: string) {
  const r = regions.value.find(x => x.uid === uidv)
  if (!r) return
  formUid.value = uidv
  form.name = r.name
  form.region_type = r.region_type
  form.remark = r.remark || ''
  formOpen.value = true
}
function saveForm() {
  const r = regions.value.find(x => x.uid === formUid.value)
  if (!r) return
  if (!form.name.trim()) return
  r.name = form.name.trim()
  r.region_type = form.region_type
  r.remark = form.remark.trim() || undefined
  dirty.value = true
  formOpen.value = false
  redraw()
}
function removeRegion(uid: string) {
  if (!regions.value.some(r => r.uid === uid)) return
  snapshot()
  regions.value = regions.value.filter(r => r.uid !== uid)
  if (selectedUid.value === uid) selectedUid.value = null
  dirty.value = true
  redraw()
}
function selectRegion(uid: string) {
  selectedUid.value = uid
  redraw()
}
function clearAll() {
  if (!regions.value.length) return
  snapshot()
  regions.value = []
  selectedUid.value = null
  dirty.value = true
  redraw()
}
function zoomBy(f: number) {
  if (!host.value) return
  const px = cw / 2
  const py = ch / 2
  const before = screenToWorld(px, py)
  scale = Math.min(Math.max(scale * f, 0.1), 12)
  tx = px - before.x * scale
  ty = py - before.y * scale
  layoutBg()
  redraw()
}

// ── 外部同步（深比较，避免父组件重拉时清掉本地撤销栈）──
watch(() => props.regions, (val) => {
  const incoming = JSON.stringify(val || [])
  if (incoming !== JSON.stringify(regions.value)) {
    regions.value = JSON.parse(incoming)
    selectedUid.value = null
    undoStack.value.length = 0
    dirty.value = false
    redraw()
  }
}, { deep: true })

watch(() => props.svgUrl, async () => { await loadBg(); fit(); layoutBg(); redraw() })
watch(() => props.viewBox, () => { fit(); layoutBg(); redraw() })

// 变更上报：父级右栏列表实时同步（防抖），选中态同步
let changeTimer: ReturnType<typeof setTimeout> | null = null
watch(regions, () => {
  if (changeTimer) clearTimeout(changeTimer)
  changeTimer = setTimeout(() => emit('change', JSON.parse(JSON.stringify(regions.value))), 120)
}, { deep: true })
watch(selectedUid, (uid) => emit('select', uid))

onMounted(init)
onBeforeUnmount(() => {
  ro?.disconnect()
  if (app) {
    const c = app.canvas
    c.removeEventListener('pointerdown', onDown)
    c.removeEventListener('pointermove', onMove)
    c.removeEventListener('pointerup', onUp)
    c.removeEventListener('pointerleave', onLeave)
    c.removeEventListener('pointercancel', onUp)
    c.removeEventListener('wheel', onWheel)
    app.destroy(true, { children: true })
    app = null
  }
})

const hintText = computed(() => {
  if (mode.value === 'layer') return '点选图层元素移动 · 拖控制点缩放（中心锚）· 顶部手柄旋转'
  return mode.value === 'draw' ? '拖拽拉出矩形区域' : '点击区域移动，拖四角拉伸'
})

const kindOptions = Object.entries(REGION_KIND_LABELS).map(([value, label]) => ({ value, label }))

// ══ 图层编辑（mode === 'layer'）══
const LAYER_NS = 'http://www.w3.org/2000/svg'
function svgEl(): SVGSVGElement | null {
  return svgLayerEl.value?.querySelector('svg') || null
}

function ensureWrapper(el: Element): SVGGElement {
  const p = el.parentElement
  if (p && p.tagName === 'g' && !p.getAttribute('id') &&
      (p.children.length === 1 || p.hasAttribute('transform') || p.hasAttribute('data-edit-wrap'))) {
    return p as unknown as SVGGElement
  }
  const w = document.createElementNS(LAYER_NS, 'g')
  w.setAttribute('data-edit-wrap', '1')
  const parent = el.parentElement || svgEl()
  parent!.insertBefore(w, el)
  w.appendChild(el)
  return w
}

/** 元素当前世界坐标 bbox（用 getBoundingClientRect 换算，包含 wrapper transform 效果） */
function layerWorldBox(el: Element): { x: number; y: number; w: number; h: number } {
  const svg = svgEl()
  const r = el.getBoundingClientRect()
  const sr = svg!.getBoundingClientRect()
  const vb = svg!.viewBox.baseVal
  const sx = vb.width / (sr.width || 1)
  const sy = vb.height / (sr.height || 1)
  return { x: (r.left - sr.left) * sx + vb.x, y: (r.top - sr.top) * sy + vb.y, w: r.width * sx, h: r.height * sy }
}

function worldFromClient(clientX: number, clientY: number) {
  const svg = svgEl()!
  const sr = svg.getBoundingClientRect()
  const vb = svg.viewBox.baseVal
  return {
    x: ((clientX - sr.left) / (sr.width || 1)) * vb.width + vb.x,
    y: ((clientY - sr.top) / (sr.height || 1)) * vb.height + vb.y,
  }
}

function hitLayer(e: PointerEvent): Element | null {
  const t = e.target as Element
  if (!t || t === svgEl()) return null
  let el: Element | null = t
  while (el && el !== svgEl()) {
    if (el.getAttribute('id')) return el
    el = el.parentElement
  }
  return null
}

function selectLayer(id: string | null) {
  if (mode.value !== 'layer') mode.value = 'layer'
  if (!id) { clearLayerSelection(); return }
  const svg = svgEl()
  const el = svg?.getElementById(id) || null
  if (!el) { clearLayerSelection(); return }
  clearLayerSelection(false)
  selectedLayerId.value = id
  const wrapper = ensureWrapper(el)
  const b = elementBBox(wrapper, svg!)
  const c = b || { x: 0, y: 0, w: 10, h: 10 }
  layerState = { el, wrapper, cx: c.x + c.w / 2, cy: c.y + c.h / 2, rot: 0, sx: 1, sy: 1, tx: 0, ty: 0 }
  emit('layerSelect', id)
  syncSelectionBox()
}

function clearLayerSelection(emitSelect = true) {
  selectedLayerId.value = null
  layerState = null
  const box = host.value?.querySelector('.sae-selection') as HTMLElement | null
  if (box) box.style.display = 'none'
  if (emitSelect) emit('layerSelect', null)
}

function syncSelectionBox() {
  const box = host.value?.querySelector('.sae-selection') as HTMLElement | null
  if (!box || !layerState) return
  const b = layerWorldBox(layerState.wrapper)
  const sp = worldToScreen(b.x, b.y)
  box.style.display = 'block'
  box.style.left = sp.x + 'px'
  box.style.top = sp.y + 'px'
  box.style.width = b.w * scale + 'px'
  box.style.height = b.h * scale + 'px'
}

function markLayerDirty() {
  layerDirty.value = true
  emit('layerChanged')
}

function updateLayerTransform() {
  if (!layerState) return
  const { cx, cy, rot, sx, sy, tx, ty } = layerState
  layerState.wrapper.setAttribute(
    'transform',
    'translate(' + cx + ' ' + cy + ') rotate(' + rot + ') scale(' + sx + ' ' + sy + ') translate(' + (-cx) + ' ' + (-cy) + ') translate(' + tx + ' ' + ty + ')'
  )
  if (gestureSnapshot) gestureMutated = true
  markLayerDirty()
}

let layerDrag: { startClientX: number; startClientY: number; origTx: number; origTy: number } | null = null
let layerResize: { handle: string; origSx: number; origSy: number } | null = null
let layerRotate: { startAngle: number; origRot: number } | null = null

function bindSvgLayerEvents() {
  const h = host.value
  if (!h) return
  h.addEventListener('pointerdown', onLayerPointerDown)
  h.addEventListener('pointermove', onLayerPointerMove)
  h.addEventListener('pointerup', onLayerPointerUp)
  h.addEventListener('pointercancel', onLayerPointerUp)
  h.addEventListener('wheel', onLayerWheel, { passive: false })
}

function onLayerPointerDown(e: PointerEvent) {
  if (mode.value !== 'layer' || !svgEl()) return
  const t = e.target as HTMLElement
  if (t.closest && t.closest('.sae-selection')) {
    const handle = t.dataset?.handle
    if (handle) { startLayerResize(handle, e); return }
    if (t.dataset?.rot === '1') { startLayerRotate(e); return }
    return
  }
  if (e.button === 1) {
    const rect = host.value!.getBoundingClientRect()
    panning = { startClientX: e.clientX - rect.left, startClientY: e.clientY - rect.top, origTx: tx, origTy: ty }
    host.value!.style.cursor = 'grabbing'
    e.preventDefault()
    return
  }
  const el = hitLayer(e)
  if (!el) { clearLayerSelection(); return }
  selectLayer(el.getAttribute('id'))
  if (e.button !== 0 || !layerState) return
  beginGesture()
  layerDrag = { startClientX: e.clientX, startClientY: e.clientY, origTx: layerState.tx, origTy: layerState.ty }
  e.preventDefault()
}

function onLayerPointerMove(e: PointerEvent) {
  if (mode.value !== 'layer' || !layerState) return
  if (panning) {
    const rect = host.value!.getBoundingClientRect()
    const px = e.clientX - rect.left
    const py = e.clientY - rect.top
    tx = panning.origTx + (px - panning.startClientX)
    ty = panning.origTy + (py - panning.startClientY)
    layoutBg()
    redraw()
    syncSelectionBox()
    return
  }
  if (layerDrag) {
    layerState.tx = layerDrag.origTx + (e.clientX - layerDrag.startClientX) / scale
    layerState.ty = layerDrag.origTy + (e.clientY - layerDrag.startClientY) / scale
    updateLayerTransform()
    syncSelectionBox()
    return
  }
  if (layerResize) {
    const p = worldFromClient(e.clientX, e.clientY)
    const b = layerWorldBox(layerState.wrapper)
    const hnd = layerResize.handle
    const dx = hnd.includes('e') ? p.x - (b.x + b.w) : hnd.includes('w') ? (b.x - p.x) : 0
    const dy = hnd.includes('s') ? p.y - (b.y + b.h) : hnd.includes('n') ? (b.y - p.y) : 0
    const nw = Math.max(b.w + dx * 2, 8)
    const nh = Math.max(b.h + dy * 2, 8)
    layerState.sx = layerResize.origSx * (nw / b.w)
    layerState.sy = layerResize.origSy * (nh / b.h)
    updateLayerTransform()
    syncSelectionBox()
    return
  }
  if (layerRotate) {
    const p = worldFromClient(e.clientX, e.clientY)
    const b = layerWorldBox(layerState.wrapper)
    const cx = b.x + b.w / 2
    const cy = b.y + b.h / 2
    const ang = (Math.atan2(p.y - cy, p.x - cx) * 180) / Math.PI
    layerState.rot = layerRotate.origRot + (ang - layerRotate.startAngle)
    updateLayerTransform()
    syncSelectionBox()
  }
}

function onLayerPointerUp() {
  endGesture()
  layerDrag = null
  layerResize = null
  layerRotate = null
  if (panning && host.value) host.value.style.cursor = ''
  panning = null
}

function onLayerWheel(e: WheelEvent) {
  if (mode.value !== 'layer' || !svgEl()) return
  e.preventDefault()
  const rect = host.value!.getBoundingClientRect()
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  const before = screenToWorld(px, py)
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  scale = Math.min(Math.max(scale * factor, 0.1), 12)
  tx = px - before.x * scale
  ty = py - before.y * scale
  layoutBg()
  redraw()
  syncSelectionBox()
}

function startLayerResize(handle: string, e: PointerEvent) {
  if (!layerState) return
  beginGesture()
  layerResize = { handle, origSx: layerState.sx, origSy: layerState.sy }
  e.preventDefault()
  e.stopPropagation()
}

function startLayerRotate(e: PointerEvent) {
  if (!layerState) return
  beginGesture()
  const b = layerWorldBox(layerState.wrapper)
  const p = worldFromClient(e.clientX, e.clientY)
  layerRotate = {
    startAngle: (Math.atan2(p.y - (b.y + b.h / 2), p.x - (b.x + b.w / 2)) * 180) / Math.PI,
    origRot: layerState.rot,
  }
  e.preventDefault()
  e.stopPropagation()
}

function removeLayer(id: string) {
  const svg = svgEl()
  const el = svg?.getElementById(id)
  if (!el) return
  pushSvgUndo()
  const wrapper = el.parentElement && el.parentElement.tagName === 'g' && el.parentElement.hasAttribute('data-edit-wrap')
    ? el.parentElement : el
  wrapper.remove()
  clearLayerSelection()
  markLayerDirty()
}

function duplicateLayer(id: string) {
  const svg = svgEl()
  const el = svg?.getElementById(id)
  if (!el) return
  pushSvgUndo()
  const clone = el.cloneNode(true) as Element
  const cid = 'copy_' + Math.random().toString(36).slice(2, 8)
  clone.setAttribute('id', cid)
  // 克隆体尚未挂载，直接创建包裹层并挂到源元素同一父级（不能用 ensureWrapper）
  const wrapper = document.createElementNS(LAYER_NS, 'g')
  wrapper.setAttribute('data-edit-wrap', '1')
  wrapper.setAttribute('transform', 'translate(20 20)')
  wrapper.appendChild(clone)
  const parent = (el.parentElement && el.parentElement.tagName === 'g') ? el.parentElement : svg
  parent!.appendChild(wrapper)
  markLayerDirty()
  selectLayer(cid)
}

function saveLayers() {
  const svg = svgEl()
  if (!svg) return
  emit('saveSvg', serializeSvg(svg))
}

/** 属性面板支持：fill / stroke / opacity 直接改元素属性（仅非 g 叶子元素） */
function setLayerProp(prop: 'fill' | 'stroke' | 'opacity', value: string) {
  if (!layerState || layerState.el.tagName === 'g') return
  pushSvgUndo()
  layerState.el.setAttribute(prop, value)
  markLayerDirty()
}

/** 属性面板支持：rect 元素直接改几何（未做变换时） */
function setLayerRect(rect: { x?: number; y?: number; w?: number; h?: number }) {
  const el = layerState?.el
  if (!el || el.tagName !== 'rect' || !isLayerUntransformed()) return
  pushSvgUndo()
  if (rect.x != null) el.setAttribute('x', String(rect.x))
  if (rect.y != null) el.setAttribute('y', String(rect.y))
  if (rect.w != null) el.setAttribute('width', String(rect.w))
  if (rect.h != null) el.setAttribute('height', String(rect.h))
  markLayerDirty()
  syncSelectionBox()
}

function isLayerUntransformed(): boolean {
  return !!(layerState && layerState.sx === 1 && layerState.sy === 1 && layerState.rot === 0 && layerState.tx === 0 && layerState.ty === 0)
}

/** 重置选中图层变换（回初始位置/大小），之后可直接编辑几何属性 */
function resetLayerTransform() {
  if (!layerState) return
  pushSvgUndo()
  layerState.wrapper.removeAttribute('transform')
  layerState.sx = 1; layerState.sy = 1; layerState.rot = 0; layerState.tx = 0; layerState.ty = 0
  const b = layerWorldBox(layerState.wrapper)
  layerState.cx = b.x + b.w / 2
  layerState.cy = b.y + b.h / 2
  markLayerDirty()
  syncSelectionBox()
}

// 图层元数据变化 → 应用到 SVG DOM（显隐/透明度）
watch(() => props.layers, (meta) => {
  const svg = svgEl()
  if (svg && meta) applyLayerMeta(svg, meta)
}, { deep: true })

// 切到图层模式时同步一次选中框
watch(mode, (m) => {
  if (m === 'layer' && layerState) syncSelectionBox()
})

defineExpose({
  selectRegion, removeRegion, openForm, fit,
  selectLayer, clearLayerSelection, removeLayer, duplicateLayer, saveLayers,
  setLayerProp, setLayerRect, resetLayerTransform,
})
</script>

<template>
  <div class="sae">
    <div class="sae-toolbar">
      <a-space>
        <a-radio-group v-model:value="mode" size="small" button-style="solid">
          <a-radio-button value="draw">绘制</a-radio-button>
          <a-radio-button value="select">选择</a-radio-button>
          <a-radio-button value="layer">图层</a-radio-button>
        </a-radio-group>
        <a-button size="small" @click="undo" :disabled="!canUndo">撤销</a-button>
        <a-button size="small" @click="zoomBy(1.2)">放大</a-button>
        <a-button size="small" @click="zoomBy(1 / 1.2)">缩小</a-button>
        <a-button size="small" @click="fit(); layoutBg(); redraw()">适配</a-button>
        <a-divider type="vertical" />
        <a-button size="small" danger :disabled="!selectedUid" @click="selectedUid && removeRegion(selectedUid)">删除选中</a-button>
        <a-button size="small" danger :disabled="!regions.length" @click="clearAll">清空</a-button>
        <a-divider type="vertical" />
        <a-button size="small" danger :disabled="!selectedLayerId" @click="selectedLayerId && removeLayer(selectedLayerId)">删除图层</a-button>
        <a-button size="small" :disabled="!selectedLayerId" @click="selectedLayerId && duplicateLayer(selectedLayerId)">复制图层</a-button>
        <a-button size="small" type="primary" :disabled="!layerDirty" @click="saveLayers">保存图纸</a-button>
      </a-space>
      <span class="sae-hint">{{ hintText }} · 滚轮缩放 · 按住中键拖动画布</span>
    </div>

    <div ref="host" class="sae-canvas">
      <div ref="svgLayerEl" v-if="svgMarkup" class="sae-svg-layer" :class="{ 'layer-active': mode === 'layer' }" v-html="svgMarkup"></div>
      <div v-if="!svgUrl" class="sae-nosvg">请先上传 SVG 图纸</div>
      <div v-show="mode === 'layer'" class="sae-selection">
        <div class="sae-sel-box"></div>
        <div class="sae-hp" data-handle="nw"></div>
        <div class="sae-hp" data-handle="n"></div>
        <div class="sae-hp" data-handle="ne"></div>
        <div class="sae-hp" data-handle="e"></div>
        <div class="sae-hp" data-handle="se"></div>
        <div class="sae-hp" data-handle="s"></div>
        <div class="sae-hp" data-handle="sw"></div>
        <div class="sae-hp" data-handle="w"></div>
        <div class="sae-rot" data-rot="1">⟳</div>
      </div>
    </div>

    <a-modal v-model:open="formOpen" title="区域标注" :footer="null" width="420px" :mask-closable="false" @cancel="formOpen = false">
      <a-form layout="vertical" size="small">
        <a-form-item label="区域名称" required>
          <a-input v-model:value="form.name" placeholder="如：前置盘位 / GPU 区" />
        </a-form-item>
        <a-form-item label="区域类型">
          <a-select v-model:value="form.region_type" :options="kindOptions" />
        </a-form-item>
        <a-form-item label="备注">
          <a-input v-model:value="form.remark" placeholder="可选：对该区域的补充说明" />
        </a-form-item>
      </a-form>
      <div style="text-align: right; margin-top: 8px">
        <a-space>
          <a-button @click="formOpen = false">取消</a-button>
          <a-button type="primary" :disabled="!form.name.trim()" @click="saveForm">确定</a-button>
        </a-space>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.sae { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 420px; }
.sae-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; }
.sae-toolbar > * { flex-shrink: 0; }
.sae-toolbar :deep(.ant-space-item) { flex-shrink: 0; }
.sae-hint { color: var(--cpq-text-secondary); font-size: 12px; white-space: nowrap; flex-shrink: 0; }
.sae-canvas { position: relative; flex: 1; min-height: 360px; border-radius: 12px; overflow: hidden;
  background: rgba(0, 0, 0, 0.12); border: 1px solid var(--cpq-glass-border); }
.sae-canvas canvas { touch-action: none; }
.sae-nosvg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--cpq-text-disabled); font-size: 13px; }
.sae-svg-layer { position: absolute; top: 0; left: 0; z-index: 1; pointer-events: none; overflow: hidden; line-height: 0; }
.sae-svg-layer :deep(svg) { width: 100%; height: 100%; display: block; }
.sae-svg-layer.layer-active { pointer-events: auto; z-index: 3; }
.sae-svg-layer.layer-active :deep(svg) { cursor: default; }
.sae-selection { position: absolute; z-index: 4; pointer-events: none; }
.sae-sel-box { position: absolute; inset: 0; border: 1.5px dashed #52c41a; background: rgba(82, 196, 26, 0.07); border-radius: 2px; }
.sae-hp { position: absolute; width: 9px; height: 9px; background: #fff; border: 1.5px solid #52c41a; pointer-events: auto; z-index: 1; }
.sae-hp[data-handle="nw"] { top: -5px; left: -5px; cursor: nwse-resize; }
.sae-hp[data-handle="n"] { top: -5px; left: 50%; margin-left: -4.5px; cursor: ns-resize; }
.sae-hp[data-handle="ne"] { top: -5px; right: -5px; cursor: nesw-resize; }
.sae-hp[data-handle="e"] { top: 50%; right: -5px; margin-top: -4.5px; cursor: ew-resize; }
.sae-hp[data-handle="se"] { bottom: -5px; right: -5px; cursor: nwse-resize; }
.sae-hp[data-handle="s"] { bottom: -5px; left: 50%; margin-left: -4.5px; cursor: ns-resize; }
.sae-hp[data-handle="sw"] { bottom: -5px; left: -5px; cursor: nesw-resize; }
.sae-hp[data-handle="w"] { top: 50%; left: -5px; margin-top: -4.5px; cursor: ew-resize; }
.sae-rot { position: absolute; top: -30px; left: 50%; margin-left: -11px; width: 22px; height: 22px;
  border-radius: 50%; background: #52c41a; color: #fff; font-size: 12px; line-height: 22px; text-align: center;
  pointer-events: auto; cursor: grab; z-index: 1; user-select: none; }
.sae-selection::before { content: ''; position: absolute; top: -24px; left: 50%; width: 1px; height: 24px; background: #52c41a; }
</style>