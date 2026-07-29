<template>
  <button
    ref="btnRef"
    class="assistant-fab"
    :class="{ open, dragging: isDragging }"
    :style="fabStyle"
    @click="onClick"
    @pointerdown="onPointerDown"
    :title="open ? '收起方案助手 · 可拖动' : '方案助手 · 可拖动'"
  >
    <CloseOutlined v-if="open" />
    <RobotOutlined v-else />
    <span v-if="!open" class="fab-label">方案助手</span>
  </button>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { RobotOutlined, CloseOutlined } from '@ant-design/icons-vue'
import { useAssistantFab } from '@/composables/useAssistantFab'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const { pos, moveClamped, refitToViewport, setFabEl, FAB_DRAG_THRESHOLD } = useAssistantFab()

const btnRef = ref<HTMLButtonElement | null>(null)
const isDragging = ref(false)

let startX = 0, startY = 0
let originX = 0, originY = 0
let moved = false
let active = false
let suppressClick = false
let suppressTimer: number | undefined

const fabStyle = computed(() => {
  // 无保存位置时回落到 CSS 默认（right/bottom 锚定）
  if (!pos.value) return undefined
  return {
    left: pos.value.x + 'px',
    top: pos.value.y + 'px',
    right: 'auto',
    bottom: 'auto',
  }
})

function onPointerDown(e: PointerEvent) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  const el = btnRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  startX = e.clientX
  startY = e.clientY
  originX = rect.left
  originY = rect.top
  moved = false
  active = true
  isDragging.value = false
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(e: PointerEvent) {
  if (!active) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (!moved && Math.hypot(dx, dy) > FAB_DRAG_THRESHOLD) {
    moved = true
    isDragging.value = true
  }
  if (moved && btnRef.value) {
    const el = btnRef.value
    moveClamped(originX + dx, originY + dy, el.offsetWidth, el.offsetHeight)
  }
}

function onPointerUp() {
  if (!active) return
  active = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  if (moved) {
    // 抑制紧随其后的 click，避免拖完就把面板打开了
    suppressClick = true
    window.clearTimeout(suppressTimer)
    suppressTimer = window.setTimeout(() => { suppressClick = false }, 150)
  }
  isDragging.value = false
}

function onClick() {
  if (suppressClick) {
    suppressClick = false
    window.clearTimeout(suppressTimer)
    return
  }
  emit('update:open', !props.open)
}

function onResize() {
  if (!btnRef.value) return
  refitToViewport(btnRef.value.offsetWidth, btnRef.value.offsetHeight)
}

onMounted(() => {
  setFabEl(btnRef.value)
  if (btnRef.value) {
    refitToViewport(btnRef.value.offsetWidth, btnRef.value.offsetHeight)
  }
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  setFabEl(null)
  window.removeEventListener('resize', onResize)
  window.clearTimeout(suppressTimer)
})
</script>

<style scoped>
.assistant-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  height: 52px;
  min-width: 52px;
  padding: 0 20px;
  border-radius: 26px;
  border: 1px solid var(--cpq-overlay-a30, transparent);
  background: var(--cpq-accent-primary);
  color: #fff;
  cursor: grab;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  z-index: 1500;
  user-select: none;
  touch-action: none; /* 拖动时不触发移动端滚动/手势 */
  box-shadow: 0 8px 24px var(--cpq-shadow-color-strong, rgba(0, 0, 0, 0.25));
  transition: transform var(--cpq-transition-fast, 0.2s), box-shadow var(--cpq-transition-fast, 0.2s);
}
.assistant-fab:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3), 0 0 24px var(--cpq-overlay-a40, transparent);
}
.assistant-fab.dragging {
  cursor: grabbing;
  transform: none;
  transition: none; /* 拖动期间 1:1 跟手，不补间 */
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
}
.assistant-fab.open {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
  border-color: var(--cpq-glass-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.fab-label {
  font-size: 14px;
  font-weight: 600;
}
</style>
