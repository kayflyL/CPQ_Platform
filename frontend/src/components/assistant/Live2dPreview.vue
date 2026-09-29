<template>
  <div ref="root" class="l2d-preview-box" :class="{ empty: !effectiveKey }" :style="{ background: bgColor || 'var(--cpq-bg-card)' }">
    <span v-if="!effectiveKey" class="l2d-preview-empty">未设置形象</span>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { petModelPath, petModelScale, DEFAULT_PET_MODEL } from '@/store/petModel'

const props = defineProps<{ modelKey?: string | null; bgColor?: string }>()

const root = ref<HTMLElement | null>(null)
let widget: any = null

const effectiveKey = computed(() => props.modelKey || DEFAULT_PET_MODEL)

function loadL2D(): Promise<any> {
  return new Promise((resolve, reject) => {
    const w = window as any
    if (w.L2D_WIDGET) return resolve(w.L2D_WIDGET)
    if (w.__l2dLoading) { w.__l2dPending = resolve; return }
    w.__l2dLoading = true
    const s = document.createElement('script')
    s.src = '/vendor/l2d-widget.min.js'
    s.onload = () => {
      w.__l2dLoading = false
      if (w.L2D_WIDGET) { resolve(w.L2D_WIDGET); if (w.__l2dPending) w.__l2dPending(w.L2D_WIDGET) }
      else reject(new Error('L2D_WIDGET is not defined'))
    }
    s.onerror = () => { w.__l2dLoading = false; reject(new Error('l2d-widget load failed')) }
    document.head.appendChild(s)
  })
}

function destroy() {
  if (widget) {
    try {
      const box = root.value
      const c = box?.querySelector?.('canvas') as HTMLCanvasElement | null
      try {
        widget.destroy()
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
    } finally {
      widget = null
    }
  }
  if (root.value) root.value.replaceChildren()
}

async function render(key: string) {
  const el = root.value
  if (!el) return
  destroy()
  try {
    const lib = await loadL2D()
    if (!root.value) return
    const before = new Set<Element>(Array.from(document.body.children))
    widget = lib.createWidget({
      model: { path: petModelPath(key), tips: false, scale: petModelScale(key) },
      position: 'bottom-right',
      size: 300,
      transitionType: 'fade',
      transitionDuration: 800,
      menus: { items: [] },
    })
    const appended = Array.from(document.body.children).filter((elx) => !before.has(elx))
    const box = appended.find((elx: Element) => elx instanceof HTMLElement && elx.style.position === 'fixed' && elx.style.zIndex === '9999') as HTMLElement | undefined
    if (box) {
      box.style.position = 'absolute'
      box.style.left = '0'
      box.style.top = '0'
      box.style.right = 'auto'
      box.style.bottom = 'auto'
      box.style.width = '100%'
      box.style.height = '100%'
      box.style.pointerEvents = 'none'
      box.style.zIndex = '1'
      root.value.appendChild(box)
    }
    appended.filter((elx: Element): elx is HTMLElement => elx !== box && elx instanceof HTMLElement).forEach((elx) => { elx.style.display = 'none' })
  } catch (e) {
    console.error('[l2d-preview] init failed', e)
  }
}

watch(() => effectiveKey.value, (k) => { render(k) })
onMounted(() => { render(effectiveKey.value) })
onBeforeUnmount(() => { destroy() })
</script>

<style scoped>
.l2d-preview-box {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 220px;
  overflow: hidden;
  border-radius: 10px;
}
.l2d-preview-box.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
}
</style>
