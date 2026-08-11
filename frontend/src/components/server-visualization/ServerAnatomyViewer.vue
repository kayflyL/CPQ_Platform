<script setup lang="ts">
/**
 * ServerAnatomyViewer —— 服务器可视化「浏览态」公共组件（PixiJS 渲染底座）。
 * 纯数据驱动：props 只有 svgUrl / viewBox / regions / counts / activeId，
 * 不感知数据来源（后端机型配置 / 页面本地对象均可）。
 * 交互：hover 高亮、点击区域 emit('select', id)，点空白 emit(null)。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Application, Container, Graphics, Text } from 'pixi.js'
import type { DrawingRegion, DrawingViewBox, DrawingLayerMeta } from '@/api/serverDrawing'
import { applyLayerMeta } from '@/utils/svgLayers'

const props = withDefaults(defineProps<{
  svgUrl?: string | null
  viewBox?: DrawingViewBox | null
  regions?: DrawingRegion[]
  layers?: DrawingLayerMeta[]
  counts?: Record<string, number>
  activeId?: string | null
}>(), {
  svgUrl: null,
  viewBox: null,
  regions: () => [],
  layers: () => [],
  counts: () => ({}),
  activeId: null,
})
const emit = defineEmits<{ select: [id: string | null] }>()

const host = ref<HTMLDivElement | null>(null)
const vb = computed<DrawingViewBox>(() => props.viewBox ?? [0, 0, 1000, 560])

const ACCENT = 0x1677ff
const TEXT_DIM = 0xcfd6e4

let app: Application | null = null
let regionLayer: Container | null = null
let badgeLayer: Container | null = null
let hovered: string | null = null
let scale = 1
let offX = 0
let offY = 0
/** 底图（矢量）：内联 SVG 文本 + 定位层（与 Pixi 世界坐标共用 scale/offX/offY 变换） */
const svgMarkup = ref('')
const svgLayerEl = ref<HTMLDivElement | null>(null)
let ro: ResizeObserver | null = null

const worldToScreen = (x: number, y: number) => ({ x: offX + x * scale, y: offY + y * scale })

function screenToWorld(px: number, py: number) {
  return { x: (px - offX) / scale, y: (py - offY) / scale }
}

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
  badgeLayer = new Container()
  app.stage.addChild(regionLayer)
  app.stage.addChild(badgeLayer)
  await loadBg()
  layout()
  redraw()
  app.canvas.addEventListener('pointermove', onMove)
  app.canvas.addEventListener('pointerleave', onLeave)
  app.canvas.addEventListener('pointerdown', onDown)
  ro = new ResizeObserver(() => { layout(); redraw() })
  ro.observe(host.value)
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
    const svg = svgLayerEl.value?.querySelector('svg')
    if (svg) applyLayerMeta(svg as SVGSVGElement, props.layers)
    layoutBg()
  } catch {
    svgMarkup.value = ''
  }
}

/** 把内联 SVG 定位到当前世界坐标变换（scale/offX/offY）下，矢量渲染任意缩放清晰 */
function layoutBg() {
  const el = svgLayerEl.value
  if (!el) return
  const [, , vw, vh] = vb.value
  el.style.left = offX + 'px'
  el.style.top = offY + 'px'
  el.style.width = vw * scale + 'px'
  el.style.height = vh * scale + 'px'
}

function layout() {
  if (!app || !host.value) return
  const cw = Math.max(host.value.clientWidth, 40)
  const ch = Math.max(host.value.clientHeight, 40)
  const [, , vw, vh] = vb.value
  scale = Math.min(cw / vw, ch / vh)
  offX = (cw - vw * scale) / 2
  offY = (ch - vh * scale) / 2
  layoutBg()
}

function redraw() {
  if (!app || !regionLayer || !badgeLayer) return
  for (const c of regionLayer.removeChildren()) c.destroy({ children: true })
  for (const c of badgeLayer.removeChildren()) c.destroy({ children: true })
  for (const r of props.regions) {
    const active = props.activeId === r.uid
    const hover = hovered === r.uid
    const on = active || hover
    const { x, y } = worldToScreen(r.x, r.y)
    const w = r.width * scale
    const h = r.height * scale

    const g = new Graphics()
    g.roundRect(x, y, w, h, 6)
    g.fill({ color: ACCENT, alpha: on ? 0.3 : 0.1 })
    g.stroke({ width: on ? 2.4 : 1.4, color: ACCENT, alpha: on ? 0.95 : 0.6 })
    regionLayer.addChild(g)

    const name = new Text({
      text: r.name,
      style: { fontSize: 13, fontWeight: '600', fill: on ? 0xffffff : TEXT_DIM, fontFamily: 'inherit' },
    })
    name.anchor.set(0.5, 0)
    name.position.set(x + w / 2, y + h - 20)
    regionLayer.addChild(name)

    const cnt = props.counts?.[r.uid] ?? 0
    const bx = x + w - 15
    const by = y + 15
    const badge = new Graphics()
    badge.circle(bx, by, 13)
    badge.fill({ color: cnt > 0 ? ACCENT : 0x3a4150, alpha: 1 })
    badge.stroke({ width: 1, color: 0xffffff, alpha: 0.45 })
    badgeLayer.addChild(badge)
    const bt = new Text({ text: String(cnt), style: { fontSize: 12, fontWeight: '700', fill: 0xffffff } })
    bt.anchor.set(0.5)
    bt.position.set(bx, by)
    badgeLayer.addChild(bt)
  }
}

function hitRegion(px: number, py: number): DrawingRegion | null {
  const p = screenToWorld(px, py)
  for (const r of props.regions) {
    if (p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height) return r
  }
  return null
}

function onMove(e: PointerEvent) {
  if (!app) return
  const rect = app.canvas.getBoundingClientRect()
  const r = hitRegion(e.clientX - rect.left, e.clientY - rect.top)
  const next = r ? r.uid : null
  if (next !== hovered) {
    hovered = next
    app.canvas.style.cursor = next ? 'pointer' : 'default'
    redraw()
  }
}

function onLeave() {
  if (hovered) {
    hovered = null
    redraw()
  }
}

function onDown(e: PointerEvent) {
  if (!app) return
  const rect = app.canvas.getBoundingClientRect()
  const r = hitRegion(e.clientX - rect.left, e.clientY - rect.top)
  emit('select', r ? (props.activeId === r.uid ? null : r.uid) : null)
}

watch(() => props.svgUrl, async () => { await loadBg(); layout(); redraw() })
watch(() => props.viewBox, () => { layout(); redraw() })
watch(() => [props.regions, props.counts, props.activeId], () => redraw(), { deep: true })
watch(() => props.layers, (meta) => {
  const svg = svgLayerEl.value?.querySelector('svg')
  if (svg && meta) applyLayerMeta(svg as SVGSVGElement, meta)
}, { deep: true })

onMounted(init)
onBeforeUnmount(() => {
  ro?.disconnect()
  if (app) {
    app.canvas.removeEventListener('pointermove', onMove)
    app.canvas.removeEventListener('pointerleave', onLeave)
    app.canvas.removeEventListener('pointerdown', onDown)
    app.destroy(true, { children: true })
    app = null
  }
})
</script>

<template>
  <div ref="host" class="sav-host">
    <div ref="svgLayerEl" v-if="svgMarkup" class="sav-svg-layer" v-html="svgMarkup"></div>
    <div v-if="!regions.length" class="sav-empty">图上还没有标注区域，请到「服务器图纸配置」页添加</div>
  </div>
</template>

<style scoped>
.sav-host { position: relative; width: 100%; height: 100%; min-height: 240px; overflow: hidden; }
.sav-svg-layer { position: absolute; top: 0; left: 0; z-index: 1; pointer-events: none; overflow: hidden; line-height: 0; }
.sav-svg-layer :deep(svg) { width: 100%; height: 100%; display: block; }
.sav-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--cpq-text-disabled); font-size: 13px; pointer-events: none; z-index: 2;
}
</style>