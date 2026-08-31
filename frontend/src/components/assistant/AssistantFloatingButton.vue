<template>
  <div
    v-show="!open"
    ref="petRef"
    class="assistant-pet"
    :class="{ dragging: isDragging }"
    :style="petStyle"
    title="方案助手 · 可拖动"
    @pointerdown="onPointerDown"
    @click="onClick"
  >
    <span v-if="failed" class="fab-mark">助</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useAssistantFab } from '@/composables/useAssistantFab'
import { petModelPath } from '@/store/petModel'

const props = defineProps<{ open: boolean; modelKey?: string }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const { pos, moveClamped, refitToViewport, setFabEl, FAB_DRAG_THRESHOLD } = useAssistantFab()

const PET_SIZE = 300
const petRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const failed = ref(false)
let widget: any = null

let startX = 0, startY = 0, originX = 0, originY = 0
let moved = false, active = false
let suppressClick = false
let suppressTimer: number | undefined

const petStyle = computed(() => {
  // 无保存位置时回落 CSS 默认（right/bottom 锚定）；有位置则用 left/top
  if (!pos.value) return undefined
  return { left: pos.value.x + "px", top: pos.value.y + "px", right: "auto", bottom: "auto" }
})

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
    if (!petRef.value) return
    const before = new Set<Element>(Array.from(document.body.children))
    widget = lib.createWidget({
      model: { path: petModelPath(props.modelKey), tips: false },
      position: "bottom-right",
      size: PET_SIZE,
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
      petRef.value.appendChild(root)
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

function onPointerMove(e: PointerEvent) {
  if (!active) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (!moved && Math.hypot(dx, dy) > FAB_DRAG_THRESHOLD) { moved = true; isDragging.value = true }
  if (moved && petRef.value) {
    moveClamped(originX + dx, originY + dy, petRef.value.offsetWidth, petRef.value.offsetHeight)
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
  }
  isDragging.value = false
}

function onClick() {
  if (suppressClick) { suppressClick = false; window.clearTimeout(suppressTimer); return }
  emit('update:open', !props.open)
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
  const el = petRef.value
  if (el) el.replaceChildren()
  failed.value = false
  initPet()
}

watch(() => props.modelKey, (n, o) => {
  if (o !== undefined && n !== o) rebuildPet()
})

function onResize() {
  if (!petRef.value) return
  refitToViewport(petRef.value.offsetWidth, petRef.value.offsetHeight)
}

onMounted(() => {
  setFabEl(petRef.value)
  if (petRef.value) refitToViewport(petRef.value.offsetWidth, petRef.value.offsetHeight)
  window.addEventListener("resize", onResize)
  initPet()
})

onBeforeUnmount(() => {
  setFabEl(null)
  window.removeEventListener("resize", onResize)
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
  width: 300px;
  height: 300px;
  z-index: 1550;
  cursor: grab;
  user-select: none;
  touch-action: none;
  filter: drop-shadow(0 12px 24px rgba(0,0,0,.35));
  transition: transform .2s, filter .2s;
}
.assistant-pet:hover { filter: drop-shadow(0 16px 32px rgba(0,0,0,.45)); transform: translateY(-2px); }
.assistant-pet.dragging { cursor: grabbing; transform: none; transition: none; }
.fab-mark {
  position: absolute; inset: 0; margin: auto; width: 52px; height: 52px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--cpq-accent-primary); color: #fff; font-size: 20px; font-weight: 700;
}
@media (max-width: 768px) {
  .assistant-pet { right: 16px; bottom: 80px; transform: scale(.7); transform-origin: bottom right; }
}
</style>
