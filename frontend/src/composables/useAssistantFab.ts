/** 方案助手浮动入口的位置共享。
 * FAB 拖动时写入 pos（+ localStorage），Panel 打开时读 FAB 实时 rect 贴边定位。
 * 单例（模块级 ref），FAB / Panel / DefaultLayout 共用同一份状态。 */
import { ref } from 'vue'

const STORAGE_KEY = 'cpq:assistant-fab-pos'

export const FAB_EDGE_MARGIN = 8
export const FAB_DRAG_THRESHOLD = 4
export const PANEL_WIDTH = 380
export const PANEL_MAX_HEIGHT = 560
export const PANEL_GAP = 12

export interface FabPos { x: number; y: number }

function loadPos(): FabPos | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const p = JSON.parse(raw)
    if (typeof p?.x === 'number' && typeof p?.y === 'number') return p
  } catch { /* ignore */ }
  return null
}

const pos = ref<FabPos | null>(loadPos())
const fabEl = ref<HTMLElement | null>(null)

function clampPos(x: number, y: number, w: number, h: number): FabPos {
  const maxX = Math.max(FAB_EDGE_MARGIN, window.innerWidth - w - FAB_EDGE_MARGIN)
  const maxY = Math.max(FAB_EDGE_MARGIN, window.innerHeight - h - FAB_EDGE_MARGIN)
  return {
    x: Math.min(Math.max(FAB_EDGE_MARGIN, x), maxX),
    y: Math.min(Math.max(FAB_EDGE_MARGIN, y), maxY),
  }
}

export function useAssistantFab() {
  function setFabEl(el: HTMLElement | null) {
    fabEl.value = el
  }
  function getFabRect(): DOMRect | null {
    return fabEl.value?.getBoundingClientRect() ?? null
  }
  function persist(p: FabPos | null) {
    pos.value = p
    if (p) localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
    else localStorage.removeItem(STORAGE_KEY)
  }
  /** 拖动中调用：夹进视口并落库。 */
  function moveClamped(x: number, y: number, w: number, h: number) {
    persist(clampPos(x, y, w, h))
  }
  /** 窗口缩放 / 启动时：把已存位置夹进当前视口。 */
  function refitToViewport(w: number, h: number) {
    if (!pos.value) return
    persist(clampPos(pos.value.x, pos.value.y, w, h))
  }

  return {
    pos,
    FAB_EDGE_MARGIN,
    FAB_DRAG_THRESHOLD,
    PANEL_WIDTH,
    PANEL_MAX_HEIGHT,
    PANEL_GAP,
    setFabEl,
    getFabRect,
    persist,
    moveClamped,
    refitToViewport,
  }
}

/** 给 Panel 用的定位算法：在 FAB 当前位置附近找一块塞得下的区域。
 * 优先 FAB 左上方；左边不够放右侧，上边不够放下方。 */
export function computePanelAnchor(fabRect: DOMRect, vw: number, vh: number) {
  const panelH = Math.min(PANEL_MAX_HEIGHT, vh - 2 * FAB_EDGE_MARGIN)
  // 水平：默认 panel 右边对齐 FAB 右边（panel 在 FAB 左侧）
  let left = fabRect.right - PANEL_WIDTH
  if (left < FAB_EDGE_MARGIN) {
    // 左侧放不下 → 改放 FAB 右侧（左对齐 FAB 左边）
    left = fabRect.left
  }
  if (left + PANEL_WIDTH > vw - FAB_EDGE_MARGIN) {
    left = vw - FAB_EDGE_MARGIN - PANEL_WIDTH
  }
  if (left < FAB_EDGE_MARGIN) left = FAB_EDGE_MARGIN
  // 垂直：默认 panel 在 FAB 上方（panel 底 = FAB 顶 - gap）
  let top = fabRect.top - PANEL_GAP - panelH
  if (top < FAB_EDGE_MARGIN) {
    // 上方放不下 → 放 FAB 下方
    top = fabRect.bottom + PANEL_GAP
  }
  if (top + panelH > vh - FAB_EDGE_MARGIN) {
    top = vh - FAB_EDGE_MARGIN - panelH
  }
  if (top < FAB_EDGE_MARGIN) top = FAB_EDGE_MARGIN
  return { left, top, height: panelH }
}
