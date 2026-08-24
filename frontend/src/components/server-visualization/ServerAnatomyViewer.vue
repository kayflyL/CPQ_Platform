<script setup lang="ts">
/**
 * ServerAnatomyViewer —— 服务器可视化「浏览态」公共组件（PixiJS 渲染底座）。
 * 纯数据驱动：props 只描述场景，渲染/交互全部落在 Pixi：
 *  - 相机系统：worldContainer 统一 position/scale，滚轮缩放（跟随鼠标）+ 拖拽平移，DOM 底图同步
 *  - 拾取：region Graphics eventMode='static' + hitArea（Pixi EventSystem，不再手算坐标）
 *  - 热力色阶：Graphics fill 按 counts 上色 + ticker 亮度呼吸（威胁等级感）
 *  - 未探索区：命中 0 的区域 ticker 驱动「流动虚线」(marching ants) + BlurFilter 微弱外发光 + 「0 命中」角标
 *  - 选中/聚焦：发光描边（BlurFilter）+ 呼吸缩放；hover 高亮由 fx 层每帧渲染
 *  - 伤害数字：命中徽标 count 变化时弹出缩放 tween（游戏伤害数字）
 *  - 视图过渡：regions 整体变化（切视图）时旧场景淡出、新场景滑入（ticker 过渡）
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Application, BlurFilter, Container, Graphics, Rectangle, Text } from 'pixi.js'
import type { DrawingRegion, DrawingViewBox, DrawingLayerMeta } from '@/api/serverDrawing'
import { applyLayerMeta, parseSvgLayers, applySandboxVisibility, type SandboxLayerKind, type SvgLayerNode } from '@/utils/svgLayers'

const props = withDefaults(defineProps<{
  svgUrl?: string | null
  viewBox?: DrawingViewBox | null
  regions?: DrawingRegion[]
  layers?: DrawingLayerMeta[]
  counts?: Record<string, number>
  /** 自定义徽标文本（id → 文案），缺省显示 counts 数字 */
  badges?: Record<string, string>
  activeId?: string | null
  /** 规则聚焦高亮区域（双向联动：点规则 → 这些区域同时发光） */
  highlightIds?: string[]
  /** 命中 0 条规则的区域显示「未配置」流动虚线 + 角标；默认开 */
  showUnconfigured?: boolean
  /** 装饰模式：rules=兼容规则（热力/命中徽标/0命中虚线）；plain=纯图纸（仅区域框与名称） */
  decorMode?: 'rules' | 'plain'
  /** 配置沙盒：硬件数量 → 显示对应数量的 SVG 图层（GPU/内存/CPU，按图层 id 序列显隐，不重新绘制元素） */
  sandboxCounts?: Partial<Record<SandboxLayerKind, number>>
}>(), {
  svgUrl: null,
  viewBox: null,
  regions: () => [],
  layers: () => [],
  counts: () => ({}),
  badges: () => ({}),
  activeId: null,
  highlightIds: () => [],
  showUnconfigured: true,
  decorMode: 'rules',
  sandboxCounts: () => ({}),
})
const emit = defineEmits<{
  select: [id: string | null, region: DrawingRegion | null]
  hover: [id: string | null, region: DrawingRegion | null]
  /** HTML5 拖放：规则卡片拖到地图上放下（uid 为 null 表示没落在区域上） */
  'drop-rule': [ruleId: string, uid: string | null]
}>()

const host = ref<HTMLDivElement | null>(null)
const vb = computed<DrawingViewBox>(() => props.viewBox ?? [0, 0, 1000, 560])

const ACCENT = 0x1677ff
const FOCUS = 0x34d399 // 规则聚焦高亮（绿）
const TEXT_DIM = 0xcfd6e4
const UNCONF = 0x9aa3b2 // 0 命中区域灰

/** 热度色阶：0=灰 / 1-2=绿 / 3-5=琥珀 / 6+=红（威胁等级感） */
function heatColor(count: number): number {
  if (count <= 0) return 0x4b5463
  if (count <= 2) return 0x22c55e
  if (count <= 5) return 0xf59e0b
  return 0xef4444
}

let app: Application | null = null
/** 相机容器：统一缩放/位移（滚轮+拖拽），DOM 底图做位置同步 */
let world: Container | null = null
/** 场景容器：视图切换过渡（淡入 + 滑入）作用在这一层 */
let scene: Container | null = null
let regionLayer: Container | null = null // 静态：区域底（可交互）、名称、未配置角标
let fxLayer: Container | null = null // 动画：热度呼吸 / 流动虚线 / 发光 / 徽标
let hovered: string | null = null
let camScale = 1
let camX = 0
let camY = 0
let elapsed = 0 // 动画累计秒数（ticker 驱动）

// ── 交互状态（Pixi EventSystem 拾取）──
let panStart: { x: number; y: number } | null = null
let moved = false
let downUid: string | null = null
let regionById = new Map<string, DrawingRegion>()
/** 拖放悬停区域（规则卡片拖过时的投放目标高亮） */
let dropHoverUid: string | null = null
let dragActive = false

// ── 动画状态 ──
/** 徽标「伤害数字」弹出动画：uid → 进度 0..1（1=静止） */
const pops = new Map<string, number>()
/** fx 层实例缓存（key=uid:role），ticker 内 clear+重绘，避免每帧创建/销毁 */
const fxCache = new Map<string, Graphics | Text | Container>()
let prevCounts: Record<string, number> = {}
/** 视图切换过渡：t ∈ [0,1]，regionLayer 整体淡入+滑入 */
const transition = { active: false, t: 1, fromX: -26 }
/** 上次 redraw 的区域 uid 签名：用于识别「视图切换」并触发过渡动画 */
let lastSig = ''
/** 沙盒图层树缓存（SVG 重载时重建） */
let layerTree: SvgLayerNode[] | null = null

/** 底图（矢量）：内联 SVG 文本 + 定位层（与 worldContainer 变换同步） */
const svgMarkup = ref('')
const svgLayerEl = ref<HTMLDivElement | null>(null)
const bgKey = ref(0)
let ro: ResizeObserver | null = null

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
  app.canvas.style.position = 'relative'
  app.canvas.style.zIndex = '2'
  world = new Container()
  scene = new Container()
  regionLayer = new Container()
  fxLayer = new Container()
  scene.addChild(regionLayer)
  scene.addChild(fxLayer)
  world.addChild(scene)
  app.stage.addChild(world)
  app.ticker.add(onTick)
  // Pixi EventSystem 拾取：stage 兜底（空白点击/拖拽），区域 Graphics 各自带 hitArea
  app.stage.eventMode = 'static'
  app.stage.hitArea = app.screen
  app.stage.on('pointerdown', onPointerDown)
  app.stage.on('globalpointermove', onGlobalMove)
  app.stage.on('pointerup', onPointerUp)
  app.canvas.addEventListener('wheel', onWheel, { passive: false })
  host.value.addEventListener('dragover', onDragOver)
  host.value.addEventListener('dragleave', onDragLeave)
  host.value.addEventListener('drop', onDrop)
  prevCounts = { ...props.counts } // 首帧不触发徽标弹出
  await loadBg()
  layout()
  redraw()
  ro = new ResizeObserver(() => { layout(); redraw() })
  ro.observe(host.value)
}

/** ticker 主循环：推进动画时间，驱动过渡与 fx 层 */
function onTick(ticker: { deltaMS: number }) {
  elapsed += ticker.deltaMS / 1000
  for (const [uid, t] of pops) {
    const nt = Math.min(1, t + ticker.deltaMS / 260)
    if (nt >= 1) pops.delete(uid)
    else pops.set(uid, nt)
  }
  if (transition.active) {
    transition.t += ticker.deltaMS / 320
    const e = easeOutCubic(Math.min(1, transition.t))
    if (scene) {
      scene.alpha = e
      scene.position.x = transition.fromX * (1 - e)
    }
    if (transition.t >= 1) {
      transition.active = false
      if (scene) { scene.alpha = 1; scene.position.x = 0 }
    }
  }
  drawFx()
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}
function easeOutBack(t: number): number {
  const c1 = 1.70158
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

/** 沿矩形周长写流动虚线（marching ants）：相位随 elapsed 前进 */
function traceDashedRect(g: Graphics, x: number, y: number, w: number, h: number, dash: number, gap: number, phase: number) {
  const edges: [number, number, number, number][] = [
    [x, y, x + w, y],
    [x + w, y, x + w, y + h],
    [x + w, y + h, x, y + h],
    [x, y + h, x, y],
  ]
  const P = dash + gap
  let s0 = 0
  for (const [ax, ay, bx, by] of edges) {
    const L = Math.hypot(bx - ax, by - ay)
    const ux = (bx - ax) / L
    const uy = (by - ay) / L
    let next = phase + Math.ceil((s0 - phase) / P) * P
    while (next < s0 + L) {
      const ds = Math.max(s0, next)
      const de = Math.min(s0 + L, next + dash)
      if (de > ds) {
        g.moveTo(ax + ux * (ds - s0), ay + uy * (ds - s0))
        g.lineTo(ax + ux * (de - s0), ay + uy * (de - s0))
      }
      next += P
    }
    s0 += L
  }
}

function getFx<T extends Graphics | Text | Container>(key: string, create: () => T): T {
  let obj = fxCache.get(key) as T | undefined
  if (!obj) {
    obj = create()
    obj.eventMode = 'none' // 动画层不参与拾取，避免抢区域点击/悬停
    fxCache.set(key, obj)
    fxLayer!.addChild(obj)
  }
  return obj
}

function drawFx() {
  if (!app || !fxLayer) return
  const seen = new Set<string>()
  for (const r of props.regions) {
    const cnt = props.counts?.[r.uid] ?? 0
    const hasCustom = props.badges?.[r.uid] != null
    const plain = props.decorMode === 'plain'
    const active = props.activeId === r.uid
    const focus = (props.highlightIds || []).includes(r.uid)
    const on = active || focus || hovered === r.uid
    const unconf = !plain && props.showUnconfigured && cnt === 0 && !hasCustom
    const { x, y, width: w, height: h } = r
    const cx = x + w / 2
    const cy = y + h / 2

    const heat = heatColor(cnt)
    const pulse = 0.5 + 0.5 * Math.sin(elapsed * 2.4 + r.uid.length * 1.7)
    // 1) 热度呼吸填充（覆盖在静态底之上）
    if (!plain) {
      const hg = getFx(r.uid + ':heat', () => new Graphics())
      hg.clear()
      hg.roundRect(x, y, w, h, 6)
      hg.fill({ color: heat, alpha: unconf ? 0.04 : 0.08 + 0.14 * pulse })
      seen.add(r.uid + ':heat')
    }

    // 2) 0 命中（灰）：流动虚线 + BlurFilter 微弱外发光
    if (unconf) {
      const lineCol = UNCONF
      const ag = getFx(r.uid + ':ants', () => new Graphics())
      ag.clear()
      traceDashedRect(ag, x + 2, y + 2, w - 4, h - 4, 10, 7, elapsed * 36 + r.uid.length * 13)
      ag.stroke({ width: 1.6, color: lineCol, alpha: 0.95 })
      seen.add(r.uid + ':ants')

      const ug = getFx(r.uid + ':unglow', () => {
        const g = new Graphics()
        g.filters = [new BlurFilter({ strength: 7 })]
        return g
      })
      ug.clear()
      ug.roundRect(x - 3, y - 3, w + 6, h + 6, 9)
      ug.stroke({ width: 2, color: lineCol, alpha: 0.12 + 0.1 * pulse })
      seen.add(r.uid + ':unglow')
    }

    // 3) 选中/聚焦/hover：发光描边（BlurFilter）+ 呼吸缩放
    if (on) {
      const gg = getFx(r.uid + ':glow', () => {
        const g = new Graphics()
        g.filters = [new BlurFilter({ strength: 6 })]
        return g
      })
      gg.clear()
      const gp = 0.5 + 0.5 * Math.sin(elapsed * 3.2 + x)
      const col = active ? ACCENT : (hovered === r.uid ? 0x7cb3ff : FOCUS)
      gg.roundRect(x - 6, y - 6, w + 12, h + 12, 10)
      gg.stroke({ width: 3, color: col, alpha: 0.5 + 0.3 * gp })
      // 呼吸缩放：绕区域中心轻微脉动（游戏「选中锁定」手感）
      const s = 1 + 0.022 * gp
      gg.pivot.set(cx, cy)
      gg.position.set(cx, cy)
      gg.scale.set(s, s)
      seen.add(r.uid + ':glow')
    }

    // 3.5) 拖放悬停：投放目标高亮（亮蓝流动虚线 + 淡填充）
    if (dropHoverUid === r.uid) {
      const dg = getFx(r.uid + ':dropGlow', () => new Graphics())
      dg.clear()
      traceDashedRect(dg, x - 4, y - 4, w + 8, h + 8, 12, 8, elapsed * 60)
      dg.stroke({ width: 2.4, color: 0x38bdf8, alpha: 0.95 })
      dg.fill({ color: 0x38bdf8, alpha: 0.07 })
      seen.add(r.uid + ':dropGlow')
    }

    // 4) 伤害数字徽标：命中数变化时弹出缩放
    if (!plain) {
      const badgeText = props.badges?.[r.uid] ?? String(cnt)
      const bx = x + w - 15
      const by = y + 15
      const pop = pops.get(r.uid) ?? 1
      const s = pop < 1 ? easeOutBack(pop) : 1
      const bg = getFx(r.uid + ':badge', () => new Graphics())
      bg.clear()
      bg.circle(bx, by, 13 * s)
      bg.fill({ color: cnt > 0 || hasCustom ? heat : 0x3a4150, alpha: 1 })
      bg.stroke({ width: 1, color: 0xffffff, alpha: on ? 0.9 : 0.45 })
      seen.add(r.uid + ':badge')
      const bt = getFx(r.uid + ':badgeText', () =>
        new Text({ text: '', style: { fontSize: 12, fontWeight: '700', fill: 0xffffff } }))
      bt.text = badgeText
      bt.anchor.set(0.5)
      bt.position.set(bx, by)
      bt.scale.set(s, s)
      seen.add(r.uid + ':badgeText')
    }
  }
  // 清理失效缓存
  for (const key of [...fxCache.keys()]) {
    if (!seen.has(key)) {
      const obj = fxCache.get(key)!
      obj.destroy({ children: true })
      fxCache.delete(key)
    }
  }
}

/** 静态层重建（数据变化时）：区域底（可交互）+ 名称 + 未配置角标 */
function redraw() {
  if (!app || !regionLayer) return
  // 视图切换（区域集合整体变化）→ 触发过渡动画
  const sig = props.regions.map(r => r.uid).join(',')
  if (lastSig !== '' && sig !== lastSig) {
    transition.active = true
    transition.t = 0
  }
  lastSig = sig
  for (const c of regionLayer.removeChildren()) c.destroy({ children: true })
  regionById.clear()
  for (const r of props.regions) {
    regionById.set(r.uid, r)
    const cnt = props.counts?.[r.uid] ?? 0
    const plain = props.decorMode === 'plain'
    const unconf = !plain && props.showUnconfigured && cnt === 0 && !props.badges?.[r.uid]
    const { x, y, width: w, height: h } = r

    // 区域底（事件拾取：eventMode='static' + hitArea）
    const g = new Graphics()
    g.roundRect(x, y, w, h, 6)
    g.fill({ color: ACCENT, alpha: 0.06 })
    g.stroke({ width: 1.4, color: 0xffffff, alpha: 0.22 })
    g.eventMode = 'static'
    g.hitArea = new Rectangle(x, y, w, h)
    ;(g as any)._ruid = r.uid
    g.on('pointerover', () => {
      if (hovered !== r.uid) {
        hovered = r.uid
        emit('hover', r.uid, r)
        if (app) app.canvas.style.cursor = 'pointer'
      }
    })
    g.on('pointerout', () => {
      if (hovered === r.uid) {
        hovered = null
        emit('hover', null, null)
        if (app) app.canvas.style.cursor = 'default'
      }
    })
    regionLayer.addChild(g)

    // 名称（hover/聚焦时的高亮由 fx 层 glow 承担，文本颜色保持稳定）
    const name = new Text({
      text: r.name,
      style: { fontSize: 13, fontWeight: '600', fill: unconf ? UNCONF : TEXT_DIM, fontFamily: 'inherit' },
    })
    name.anchor.set(0.5, 0)
    name.position.set(x + w / 2, y + h - 20)
    name.eventMode = 'none'
    regionLayer.addChild(name)

    if (unconf) {
      const tag = new Text({
        text: '0 命中',
        style: { fontSize: 10, fontWeight: '600', fill: 0x1e2430, fontFamily: 'inherit' },
      })
      const tagBg = new Graphics()
      tagBg.roundRect(x + 4, y + 4, tag.width + 10, tag.height + 6, 4)
      tagBg.fill({ color: UNCONF, alpha: 1 })
      tagBg.eventMode = 'none'
      tag.position.set(x + 9, y + 7)
      tag.eventMode = 'none'
      regionLayer.addChild(tagBg)
      regionLayer.addChild(tag)
    }

    // 徽标「伤害数字」弹出触发：count 变化
    if (prevCounts[r.uid] !== cnt) pops.set(r.uid, 0)
  }
  prevCounts = { ...props.counts }
}

// ── 相机系统：worldContainer 统一变换，DOM 底图同步 ──
function layout() {
  if (!app || !host.value || !world) return
  const cw = Math.max(host.value.clientWidth, 40)
  const ch = Math.max(host.value.clientHeight, 40)
  const [, , vw, vh] = vb.value
  camScale = Math.min(cw / vw, ch / vh)
  camX = (cw - vw * camScale) / 2
  camY = (ch - vh * camScale) / 2
  applyCamera()
}

function applyCamera() {
  if (!world) return
  world.scale.set(camScale, camScale)
  world.position.set(camX, camY)
  layoutBg()
}

/** 以屏幕点 (px,py) 为中心缩放（滚轮），保持鼠标下世界点不动 */
function zoomAt(px: number, py: number, factor: number) {
  const ns = Math.min(4, Math.max(0.25, camScale * factor))
  const k = ns / camScale
  camX = px - (px - camX) * k
  camY = py - (py - camY) * k
  camScale = ns
  applyCamera()
}

/** DOM 底图（矢量 SVG）与相机同步：left/top/width/height 等价于 world 变换 */
function layoutBg() {
  const el = svgLayerEl.value
  if (!el) return
  const [, , vw, vh] = vb.value
  el.style.left = camX + 'px'
  el.style.top = camY + 'px'
  el.style.width = vw * camScale + 'px'
  el.style.height = vh * camScale + 'px'
}

// ── 交互：滚轮缩放 / 拖拽平移 / 点击拾取 ──
function onWheel(e: WheelEvent) {
  if (!app) return
  e.preventDefault()
  const rect = app.canvas.getBoundingClientRect()
  zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.12 : 1 / 1.12)
}

function onPointerDown(e: any) {
  panStart = { x: e.global.x, y: e.global.y }
  moved = false
  downUid = (e.target as any)?._ruid ?? null
  if (app) app.canvas.style.cursor = 'grabbing'
}

function onGlobalMove(e: any) {
  if (!panStart) return
  const dx = e.global.x - panStart.x
  const dy = e.global.y - panStart.y
  if (!moved && Math.abs(dx) + Math.abs(dy) > 4) moved = true
  if (moved) {
    camX += dx
    camY += dy
    panStart = { x: e.global.x, y: e.global.y }
    applyCamera()
  }
}

function onPointerUp() {
  if (!moved && downUid != null) {
    const r = regionById.get(downUid) ?? null
    emit('select', props.activeId === downUid ? null : downUid, r)
  } else if (!moved && downUid == null) {
    emit('select', null, null)
  }
  panStart = null
  downUid = null
  moved = false
  if (app) app.canvas.style.cursor = 'default'
}

// ── 拖放投放：规则卡片拖到地图上放下，按屏幗坐标算出命中区域 ──
function clientToWorld(cx: number, cy: number): { x: number; y: number } {
  const rect = host.value!.getBoundingClientRect()
  return { x: (cx - rect.left - camX) / camScale, y: (cy - rect.top - camY) / camScale }
}
function regionAtWorld(wx: number, wy: number): string | null {
  for (const r of props.regions) {
    if (wx >= r.x && wx <= r.x + r.width && wy >= r.y && wy <= r.y + r.height) return r.uid
  }
  return null
}
function onDragOver(e: DragEvent) {
  if (!e.dataTransfer) return
  e.preventDefault()
  if (e.dataTransfer.types && !e.dataTransfer.types.includes('text/plain')) return
  dragActive = true
  const { x, y } = clientToWorld(e.clientX, e.clientY)
  const uid = regionAtWorld(x, y)
  if (uid !== dropHoverUid) {
    dropHoverUid = uid
    redraw()
  }
}
function onDragLeave() {
  if (!dragActive) return
  dragActive = false
  dropHoverUid = null
  redraw()
}
function onDrop(e: DragEvent) {
  e.preventDefault()
  dragActive = false
  const ruleId = e.dataTransfer?.getData('text/plain') ?? ''
  const { x, y } = clientToWorld(e.clientX, e.clientY)
  const uid = regionAtWorld(x, y)
  dropHoverUid = null
  redraw()
  if (ruleId) emit('drop-rule', ruleId, uid)
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
    bgKey.value++
    await nextTick()
    const svg = svgLayerEl.value?.querySelector('svg')
    if (svg) {
      applyLayerMeta(svg as SVGSVGElement, props.layers)
      layerTree = parseSvgLayers(svg as SVGSVGElement, props.layers)
      syncSandboxLayers()
    }
    layoutBg()
  } catch {
    svgMarkup.value = ''
  }
}

/** 沙盒图层显隐：调参后显示前 N 个图层、隐藏其余 */
function syncSandboxLayers() {
  const svg = svgLayerEl.value?.querySelector('svg') as SVGSVGElement | null
  if (!svg) return
  if (!layerTree) layerTree = parseSvgLayers(svg, props.layers)
  applySandboxVisibility(layerTree, props.sandboxCounts)
}

watch(() => props.svgUrl, async () => { await loadBg(); layout(); redraw() })
watch(() => props.viewBox, () => { layout(); redraw() })
watch(() => [props.regions, props.counts, props.badges, props.activeId, props.highlightIds], () => redraw(), { deep: true })
watch(() => props.sandboxCounts, () => syncSandboxLayers(), { deep: true })
watch(() => props.layers, (meta) => {
  const svg = svgLayerEl.value?.querySelector('svg')
  if (svg) {
    applyLayerMeta(svg as SVGSVGElement, meta || [])
    syncSandboxLayers()
  }
}, { deep: true })

onMounted(init)
onBeforeUnmount(() => {
  ro?.disconnect()
  if (app) {
    app.stage.off('pointerdown', onPointerDown)
    app.stage.off('globalpointermove', onGlobalMove)
    app.stage.off('pointerup', onPointerUp)
    app.canvas.removeEventListener('wheel', onWheel)
    host.value?.removeEventListener('dragover', onDragOver)
    host.value?.removeEventListener('dragleave', onDragLeave)
    host.value?.removeEventListener('drop', onDrop)
    app.destroy(true, { children: true })
    app = null
  }
})
</script>

<template>
  <div ref="host" class="sav-host">
    <div ref="svgLayerEl" v-if="svgMarkup" :key="bgKey" class="sav-svg-layer" v-html="svgMarkup"></div>
    <div v-if="!regions.length" class="sav-empty">图上还没有标注区域，请到「服务器图纸配置」页添加</div>
  </div>
</template>

<style scoped>
.sav-host { position: relative; width: 100%; height: 100%; min-height: 240px; overflow: hidden; touch-action: none; }
.sav-svg-layer {
  position: absolute; top: 0; left: 0; z-index: 1; pointer-events: none; overflow: hidden; line-height: 0;
  /* 视图切换：与 Pixi 场景层同节奏滑入淡入 */
  animation: sav-bg-in 0.32s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes sav-bg-in {
  from { opacity: 0; transform: translateX(-26px); }
  to { opacity: 1; transform: translateX(0); }
}
.sav-svg-layer :deep(svg) { width: 100%; height: 100%; display: block; }
.sav-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--cpq-text-disabled); font-size: 13px; pointer-events: none; z-index: 2;
}
</style>
