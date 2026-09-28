<template>
  <div
    v-show="!open"
    ref="petRef"
    class="assistant-pet"
    :class="[{ dragging: isDragging }, dock ? `is-docked-${dock}` : '']"
    :style="petStyle"
    :title="dock ? '方案助手 · 点击展开，拖开可恢复' : '方案助手 · 拖动移动 / 右键调大小 / 拖到屏幕边缘可收起'"
    @pointerdown="onPointerDown"
    @click="onClick"
    @contextmenu.prevent="openMenu"
  >
    <!-- 拖拽近边缘时的吸附预览 -->
    <div v-if="isDragging && dockPreview" class="dock-preview"></div>
    <!-- 画布挂载层（呼吸浮动动画作用在这层，不干扰容器的贴边 transform） -->
    <div ref="stageRef" class="pet-stage">
      <span v-if="failed" class="fab-mark">助</span>
    </div>
    <!-- 回复中流式摘录气泡：面板关着时实时显示正在生成的内容 -->
    <div v-if="bubbleText && !isDragging" class="pet-bubble" :class="{ 'from-bottom': dock === 'top' }">{{ bubbleText }}</div>
  </div>

  <!-- 右键菜单：Teleport 到 body（容器在贴边 transform 下 fixed 会失真） -->
  <Teleport to="body">
    <transition name="pet-menu-fade">
      <div v-if="menuOpen" class="pet-menu" :style="menuStyle" @pointerdown.stop @contextmenu.prevent.stop>
        <div class="pet-menu-title">桌宠大小</div>
        <button
          v-for="t in PET_SIZE_TIERS"
          :key="t.px"
          type="button"
          class="pet-menu-item"
          :class="{ active: petSize === t.px }"
          @click="onPickSize(t.px)"
        >
          <span>{{ t.label }}</span>
          <span class="pet-menu-px">{{ t.px }}px</span>
          <span v-if="petSize === t.px" class="pet-menu-check">✓</span>
        </button>
        <div class="pet-menu-hint">拖到屏幕边缘可收起 · 拖开恢复</div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { petModelPath, usePetModelStore } from '@/store/petModel'
import { useAssistantFab, MOBILE_TABBAR_INSET, type PetDockEdge } from '@/composables/useAssistantFab'

const props = defineProps<{ open: boolean; modelKey?: string }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const {
  pos, petSize, dockEdge, moveClamped, refitToViewport, setFabEl, setPetSize, setDockEdge,
  FAB_DRAG_THRESHOLD, PET_SIZE_TIERS, PET_DOCK_SLIDE, PET_DOCK_SNAP,
} = useAssistantFab()
const dock = dockEdge
const petModel = usePetModelStore()

const petRef = ref<HTMLElement | null>(null)
const stageRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const failed = ref(false)
const dockPreview = ref<PetDockEdge | null>(null)
const vpTick = ref(0) // 视口尺寸变化计数：petStyle 依赖 window 尺寸，bump 强制重算

let widget: any = null

let startX = 0, startY = 0, originX = 0, originY = 0
let moved = false, active = false
let suppressClick = false
let suppressTimer: number | undefined

function clampCross(v: number, dim: number, s: number) {
  return Math.max(8, Math.min(v, dim - s - 8))
}

// 手机端底部导航避让：贴边 / 停靠 / 纵向夹取都以此为下界（拖拽自由位的夹取在 useAssistantFab.clampPos）
function bottomInset() {
  return window.matchMedia('(max-width: 768px)').matches ? MOBILE_TABBAR_INSET : 0
}

const petStyle = computed(() => {
  void vpTick.value
  const s = petSize.value
  const vw = window.innerWidth
  const vh = window.innerHeight - bottomInset()
  const style: Record<string, string> = {
    width: `${s}px`,
    height: `${s}px`,
    '--dock-slide': `${Math.round(PET_DOCK_SLIDE * 100)}%`,
  }
  // 贴边态：贴边轴取视口实时值（窗口缩放不脱边），横轴用 pos 夹取
  const d = dock.value
  if (d === 'right') {
    style.left = `${vw - s}px`
    style.top = `${clampCross(pos.value?.y ?? vh - s - 24, vh, s)}px`
  } else if (d === 'left') {
    style.left = '0px'
    style.top = `${clampCross(pos.value?.y ?? vh - s - 24, vh, s)}px`
  } else if (d === 'top') {
    style.left = `${clampCross(pos.value?.x ?? vw - s - 24, vw, s)}px`
    style.top = '0px'
  } else if (d === 'bottom') {
    style.left = `${clampCross(pos.value?.x ?? vw - s - 24, vw, s)}px`
    style.top = `${vh - s}px`
  } else if (pos.value) {
    style.left = `${pos.value.x}px`
    style.top = `${pos.value.y}px`
  }
  // 无 pos 且未贴边 → CSS 默认（right/bottom 锚定）
  return style
})

// 回复中流式摘录：turn 结束 streamingText 清空 → 气泡自动消失
const bubbleText = computed(() => petModel.activeStreamTail.trim())

function loadL2D(): Promise<any> {
  return new Promise((resolve, reject) => {
    const w = window as any
    if (w.L2D_WIDGET) return resolve(w.L2D_WIDGET)
    if (w.__l2dLoading) { w.__l2dPending = resolve; return }
    w.__l2dLoading = true
    const s = document.createElement("script")
    s.src = "/vendor/l2d-widget.min.js"
    s.onload = () => {
      w.__l2dLoading = false
      if (w.L2D_WIDGET) { resolve(w.L2D_WIDGET); if (w.__l2dPending) w.__l2dPending(w.L2D_WIDGET) }
      else reject(new Error("L2D_WIDGET is not defined"))
    }
    s.onerror = () => { w.__l2dLoading = false; reject(new Error("l2d-widget load failed")) }
    document.head.appendChild(s)
  })
}

async function initPet() {
  try {
    const lib = await loadL2D()
    if (!stageRef.value) return
    const before = new Set<Element>(Array.from(document.body.children))
    widget = lib.createWidget({
      model: { path: petModelPath(props.modelKey), tips: false },
      position: "bottom-right",
      size: petSize.value,
      transitionType: "fade",
      transitionDuration: 800,
      menus: { items: [] },
    })
    // createWidget 生成的画布容器是固定右下角、z-index 9999 的 div
    const appended = Array.from(document.body.children).filter((el) => !before.has(el))
    const root = appended.find((el) =>
      el instanceof HTMLElement && el.style.position === "fixed" && el.style.zIndex === "9999"
    ) as HTMLElement | undefined
    if (root) {
      root.style.position = "absolute"
      root.style.left = "0"
      root.style.top = "0"
      root.style.right = "auto"
      root.style.bottom = "auto"
      root.style.width = "100%"
      root.style.height = "100%"
      root.style.pointerEvents = "auto"
      root.style.zIndex = "1"
      stageRef.value.appendChild(root)
    }
    // 隐藏其余 chrome（菜单/状态栏）
    appended.filter((el): el is HTMLElement => el !== root && el instanceof HTMLElement).forEach((el) => { el.style.display = "none" })
  } catch (e) {
    failed.value = true
    console.error("[assistant-pet] l2d init failed", e)
  }
}

function onPointerDown(e: PointerEvent) {
  if (e.pointerType === "mouse" && e.button !== 0) return
  const el = petRef.value
  if (!el) return
  menuOpen.value = false
  if (dock.value) setDockEdge(null) // 抓住即脱边，整只恢复
  const rect = el.getBoundingClientRect()
  startX = e.clientX
  startY = e.clientY
  originX = rect.left
  originY = rect.top
  moved = false
  active = true
  isDragging.value = false
  window.addEventListener("pointermove", onPointerMove)
  window.addEventListener("pointerup", onPointerUp)
  window.addEventListener("pointercancel", onPointerUp)
}

function edgeAt(cx: number, cy: number): PetDockEdge | null {
  if (cx <= PET_DOCK_SNAP) return 'left'
  if (cx >= window.innerWidth - PET_DOCK_SNAP) return 'right'
  if (cy <= PET_DOCK_SNAP) return 'top'
  if (cy >= window.innerHeight - bottomInset() - PET_DOCK_SNAP) return 'bottom'
  return null
}

function onPointerMove(e: PointerEvent) {
  if (!active) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (!moved && Math.hypot(dx, dy) > FAB_DRAG_THRESHOLD) { moved = true; isDragging.value = true }
  if (moved && petRef.value) {
    const s = petSize.value
    moveClamped(originX + dx, originY + dy, s, s)
    dockPreview.value = edgeAt(e.clientX, e.clientY)
  }
}

function onPointerUp() {
  if (!active) return
  active = false
  window.removeEventListener("pointermove", onPointerMove)
  window.removeEventListener("pointerup", onPointerUp)
  window.removeEventListener("pointercancel", onPointerUp)
  if (moved) {
    suppressClick = true
    window.clearTimeout(suppressTimer)
    suppressTimer = window.setTimeout(() => { suppressClick = false }, 150)
    // 松手在边缘吸附区内 → 贴边收起（pos 落到贴边位，dock 状态持久化）
    const edge = dockPreview.value
    dockPreview.value = null
    if (edge) {
      const s = petSize.value
      const vw = window.innerWidth
      const vh = window.innerHeight - bottomInset()
      const x = edge === 'right' ? vw - s : edge === 'left' ? 0 : clampCross(pos.value?.x ?? 0, vw, s)
      const y = edge === 'top' ? 0 : edge === 'bottom' ? vh - s : clampCross(pos.value?.y ?? 0, vh, s)
      moveClamped(x, y, s, s)
      setDockEdge(edge)
    }
  }
  isDragging.value = false
}

function onClick() {
  if (suppressClick) { suppressClick = false; window.clearTimeout(suppressTimer); return }
  menuOpen.value = false
  emit('update:open', !props.open)
}

// ── 右键菜单：桌宠大小三档 ──
const menuOpen = ref(false)
const menuPos = ref({ x: 0, y: 0 })
const menuStyle = computed(() => ({ left: `${menuPos.value.x}px`, top: `${menuPos.value.y}px` }))

function openMenu(e: MouseEvent) {
  if (window.innerWidth <= 760) return // 移动端无右键语义
  menuPos.value = {
    x: Math.max(8, Math.min(e.clientX, window.innerWidth - 190)),
    y: Math.max(8, Math.min(e.clientY, window.innerHeight - 220)),
  }
  menuOpen.value = true
}

function onPickSize(px: number) {
  setPetSize(px)
  menuOpen.value = false
}

function onDocPointerDown(e: PointerEvent) {
  if (!menuOpen.value) return
  if (!(e.target as HTMLElement | null)?.closest?.('.pet-menu')) menuOpen.value = false
}

function onDocKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') menuOpen.value = false
}

function destroyWidget(w: any) {
  if (!w) return
  let c: HTMLCanvasElement | null = null
  try {
    c = (w.canvas?.parentElement?.querySelector?.('canvas') || w.canvas || null) as HTMLCanvasElement | null
  } catch {
    /* ignore */
  }
  try {
    w.destroy()
  } catch {
    /* ignore */
  }
  if (c) {
    try {
      const c2 = c.getContext('webgl2')
      if (c2) {
        c2.getExtension('WEBGL_lose_context')?.loseContext()
      } else {
        c.getContext('webgl')?.getExtension('WEBGL_lose_context')?.loseContext()
      }
    } catch {
      /* ignore */
    }
  }
}

function rebuildPet() {
  if (widget) {
    destroyWidget(widget)
    widget = null
  }
  const el = stageRef.value
  if (el) el.replaceChildren()
  failed.value = false
  initPet()
}

watch(() => props.modelKey, (n, o) => {
  if (o !== undefined && n !== o) rebuildPet()
})

// 尺寸换档：重建画布到新尺寸 + 位置夹取（贴边态坐标由 petStyle 依视口实时算，无需处理）
watch(petSize, () => {
  rebuildPet()
  refitToViewport(petSize.value, petSize.value)
})

function onResize() {
  vpTick.value++
  if (!dock.value) refitToViewport(petSize.value, petSize.value)
}

onMounted(() => {
  setFabEl(petRef.value)
  if (!dock.value) refitToViewport(petSize.value, petSize.value)
  window.addEventListener("resize", onResize)
  document.addEventListener("pointerdown", onDocPointerDown)
  document.addEventListener("keydown", onDocKeydown)
  initPet()
})

onBeforeUnmount(() => {
  setFabEl(null)
  window.removeEventListener("resize", onResize)
  document.removeEventListener("pointerdown", onDocPointerDown)
  document.removeEventListener("keydown", onDocKeydown)
  window.clearTimeout(suppressTimer)
  if (widget) {
    destroyWidget(widget)
  }
})
</script>

<style scoped>
.assistant-pet {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 200px;
  height: 200px;
  z-index: 1550;
  cursor: grab;
  user-select: none;
  touch-action: none;
  filter: drop-shadow(0 12px 24px rgba(0,0,0,.35));
  transition: transform .25s ease, filter .2s;
}
.assistant-pet:hover { filter: drop-shadow(0 16px 32px rgba(0,0,0,.45)); }
.assistant-pet.dragging { cursor: grabbing; transition: none; }

/* 手机端默认锚点上移：避开底部导航栏（58px + 安全区；拖拽夹取同步见 useAssistantFab.MOBILE_TABBAR_INSET） */
@media (max-width: 768px) {
  .assistant-pet {
    right: 14px;
    bottom: calc(14px + 58px + env(safe-area-inset-bottom, 0px));
  }
}

/* 贴边半隐：滑出约 2/3，留 1/3 身子作把手；hover 弹回 */
.assistant-pet.is-docked-right { transform: translateX(var(--dock-slide, 62%)); }
.assistant-pet.is-docked-left { transform: translateX(calc(-1 * var(--dock-slide, 62%))); }
.assistant-pet.is-docked-top { transform: translateY(calc(-1 * var(--dock-slide, 62%))); }
.assistant-pet.is-docked-bottom { transform: translateY(var(--dock-slide, 62%)); }
.assistant-pet.is-docked-right:hover,
.assistant-pet.is-docked-left:hover,
.assistant-pet.is-docked-top:hover,
.assistant-pet.is-docked-bottom:hover { transform: translate(0, 0); }

/* 吸附预览：拖近边缘时的虚线落位提示 */
.dock-preview {
  position: absolute;
  inset: 0;
  border: 2px dashed var(--cpq-accent-primary, #1677ff);
  border-radius: 18px;
  background: var(--cpq-overlay-w2, rgba(22, 119, 255, .08));
  pointer-events: none;
  z-index: 2;
}

/* 画布挂载层：呼吸浮动（贴边/hover 的 transform 在容器层，互不干扰） */
.pet-stage {
  position: absolute;
  inset: 0;
  animation: pet-bob 3.6s ease-in-out infinite;
}
.assistant-pet.dragging .pet-stage { animation-play-state: paused; }
@keyframes pet-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}
@media (prefers-reduced-motion: reduce) {
  .pet-stage { animation: none; }
}

.fab-mark {
  position: absolute; inset: 0; margin: auto; width: 52px; height: 52px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--cpq-accent-primary); color: #fff; font-size: 20px; font-weight: 700;
}

/* 头顶气泡：回复中流式摘录 */
.pet-bubble {
  position: absolute;
  bottom: calc(100% - 30px);
  left: 50%;
  transform: translateX(-50%);
  max-width: 240px;
  padding: 7px 11px;
  border-radius: 12px 12px 12px 4px;
  background: var(--cpq-glass-card-bg, rgba(255, 255, 255, .88));
  border: 1px solid var(--cpq-glass-border, rgba(0, 0, 0, .08));
  box-shadow: var(--cpq-glass-card-shadow, 0 8px 24px rgba(0, 0, 0, .12));
  backdrop-filter: blur(10px);
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  z-index: 3;
}
.pet-bubble.from-bottom {
  bottom: auto;
  top: calc(100% - 30px);
  border-radius: 4px 12px 12px 12px;
}

/* 右键菜单（Teleport 到 body，fixed 直达视口） */
.pet-menu {
  position: fixed;
  z-index: 3000;
  min-width: 172px;
  padding: 6px;
  border-radius: 14px;
  background: var(--cpq-glass-card-bg, rgba(255, 255, 255, .92));
  border: 1px solid var(--cpq-glass-border, rgba(0, 0, 0, .08));
  box-shadow: var(--cpq-glass-card-shadow, 0 12px 32px rgba(0, 0, 0, .16));
  backdrop-filter: blur(14px);
  user-select: none;
}
.pet-menu-title { padding: 6px 10px 4px; font-size: 11px; color: var(--cpq-text-muted, #888); }
.pet-menu-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 7px 10px; border: 0; border-radius: 9px; background: transparent;
  font-size: 13px; cursor: pointer; text-align: left; color: inherit;
}
.pet-menu-item:hover { background: var(--cpq-overlay-w2, rgba(0, 0, 0, .05)); }
.pet-menu-item.active { color: var(--cpq-accent-primary, #1677ff); font-weight: 600; }
.pet-menu-px { margin-left: auto; font-size: 11px; opacity: .55; font-variant-numeric: tabular-nums; }
.pet-menu-check { font-size: 12px; }
.pet-menu-hint {
  padding: 6px 10px 4px; font-size: 11px; opacity: .55;
  border-top: 1px solid var(--cpq-border-secondary, rgba(0, 0, 0, .06));
  margin-top: 4px;
}
.pet-menu-fade-enter-active, .pet-menu-fade-leave-active { transition: opacity .15s ease, transform .15s ease; }
.pet-menu-fade-enter-from, .pet-menu-fade-leave-to { opacity: 0; transform: scale(.96); }

@media (max-width: 768px) {
  .assistant-pet { right: 16px; bottom: 80px; }
}
</style>
