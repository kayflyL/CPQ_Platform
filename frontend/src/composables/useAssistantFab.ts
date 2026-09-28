/** 方案助手浮动入口的位置共享。
 * FAB 与面板各自持久化独立位置（模块级单例，FAB / Panel / DefaultLayout 共用）：
 *  - FAB：拖动按钮时写入 pos（+ localStorage）。
 *  - 面板：自己持有 panelPos（+ localStorage），拖动窗口直接改面板位置，不再耦合到 FAB；
 *    避免“只能整块放 FAB 上方/下方”的锚定算法在面板过大时把窗口钉死在屏幕底部。 */
import { ref } from 'vue'

const STORAGE_KEY = 'cpq:assistant-fab-pos'
const PANEL_STORAGE_KEY = 'cpq:assistant-panel-pos'
const PET_SIZE_KEY = 'cpq:assistant-pet-size'
const PET_DOCK_KEY = 'cpq:assistant-pet-dock'

export const FAB_EDGE_MARGIN = 8
export const FAB_DRAG_THRESHOLD = 4
export const PANEL_WIDTH = 680
export const PANEL_MAX_HEIGHT = 680
export const PANEL_GAP = 12

/** 桌宠尺寸三档（默认中档 200）。 */
export const PET_SIZE_TIERS = [
  { label: '小', px: 160 },
  { label: '中', px: 200 },
  { label: '大', px: 280 },
] as const
/** 贴边收起时滑出屏幕的比例（保留约 1/3 身子作把手）。 */
export const PET_DOCK_SLIDE = 0.62
/** 拖拽中判定「贴边」的触发距离（px）。 */
export const PET_DOCK_SNAP = 28

/** 手机端（≤768）底部导航栏高度：桌宠 / 面板的视口下界要抬到底栏上方。
 * 与 DefaultLayout 全局 :root --cpq-tabbar-h 同源，改动需两处同步。 */
export const MOBILE_TABBAR_INSET = 58

function mobileBottomInset(): number {
  return window.matchMedia('(max-width: 768px)').matches ? MOBILE_TABBAR_INSET : 0
}

export type PetDockEdge = 'left' | 'right' | 'top' | 'bottom'

function loadPetSize(): number {
  try {
    const raw = localStorage.getItem(PET_SIZE_KEY)
    const n = raw ? Number(JSON.parse(raw)) : NaN
    if (PET_SIZE_TIERS.some((t) => t.px === n)) return n
  } catch { /* ignore */ }
  return 200
}

function loadDockEdge(): PetDockEdge | null {
  const raw = localStorage.getItem(PET_DOCK_KEY)
  return raw === 'left' || raw === 'right' || raw === 'top' || raw === 'bottom' ? raw : null
}

export interface FabPos { x: number; y: number }
export interface FabRect {
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
}

function loadPos(key: string): FabPos | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const p = JSON.parse(raw)
    if (typeof p?.x === 'number' && typeof p?.y === 'number') return p
  } catch { /* ignore */ }
  return null
}

const pos = ref<FabPos | null>(loadPos(STORAGE_KEY))
const panelPos = ref<FabPos | null>(loadPos(PANEL_STORAGE_KEY))
const petSize = ref(loadPetSize())
const dockEdge = ref<PetDockEdge | null>(loadDockEdge())
const fabEl = ref<HTMLElement | null>(null)

function clampPos(x: number, y: number, w: number, h: number): FabPos {
  const bottomExtra = mobileBottomInset()
  const maxX = Math.max(FAB_EDGE_MARGIN, window.innerWidth - w - FAB_EDGE_MARGIN)
  const maxY = Math.max(FAB_EDGE_MARGIN, window.innerHeight - h - FAB_EDGE_MARGIN - bottomExtra)
  return {
    x: Math.min(Math.max(FAB_EDGE_MARGIN, x), maxX),
    y: Math.min(Math.max(FAB_EDGE_MARGIN, y), maxY),
  }
}

function clampPanelPos(x: number, y: number, w: number, h: number, vw: number, vh: number): FabPos {
  const maxX = Math.max(FAB_EDGE_MARGIN, vw - w - FAB_EDGE_MARGIN)
  const maxY = Math.max(FAB_EDGE_MARGIN, vh - h - FAB_EDGE_MARGIN)
  return {
    x: Math.min(Math.max(FAB_EDGE_MARGIN, x), maxX),
    y: Math.min(Math.max(FAB_EDGE_MARGIN, y), maxY),
  }
}

/** 面板实际渲染尺寸：宽度对齐 CSS `min(680px, 100vw - 32px)`，
 * 高度对齐旧锚定算法 `min(680px, 100vh - 16px)`，保证拖拽夹取与渲染一致。 */
export function panelSize(vw: number, vh: number) {
  return {
    width: Math.min(PANEL_WIDTH, Math.max(280, vw - 32)),
    height: Math.min(PANEL_MAX_HEIGHT, Math.max(280, vh - 2 * FAB_EDGE_MARGIN)),
  }
}

/** 面板首次打开时的锚定位置：优先 FAB 左上方，放不下再换侧/下方，并夹进视口。
 * 无有效 FAB 位置（未挂载/被隐藏）时回落到右下角默认位（对齐 CSS right:24 / bottom:88）。 */
export function anchorPanel(fabRect: FabRect | null, vw: number, vh: number): FabPos {
  const { width, height } = panelSize(vw, vh)
  if (!fabRect || fabRect.width === 0) {
    return clampPanelPos(vw - width - 24, vh - height - 88, width, height, vw, vh)
  }
  // 水平：默认 panel 右边对齐 FAB 右边（panel 在 FAB 左侧）
  let left = fabRect.right - width
  if (left < FAB_EDGE_MARGIN) left = fabRect.left
  if (left + width > vw - FAB_EDGE_MARGIN) left = vw - FAB_EDGE_MARGIN - width
  if (left < FAB_EDGE_MARGIN) left = FAB_EDGE_MARGIN
  // 垂直：默认 panel 在 FAB 上方（panel 底 = FAB 顶 - gap）
  let top = fabRect.top - PANEL_GAP - height
  if (top < FAB_EDGE_MARGIN) top = fabRect.bottom + PANEL_GAP
  if (top + height > vh - FAB_EDGE_MARGIN) top = vh - FAB_EDGE_MARGIN - height
  if (top < FAB_EDGE_MARGIN) top = FAB_EDGE_MARGIN
  return clampPanelPos(left, top, width, height, vw, vh)
}

export function useAssistantFab() {
  function setFabEl(el: HTMLElement | null) {
    fabEl.value = el
  }
  function getFabRect(): FabRect | null {
    // FAB 在面板打开时 v-show 隐藏（display:none → getBoundingClientRect 返回零），
    // 改用 pos ref（模块级单例，FAB 挂载/拖动时实时更新）。
    if (pos.value) {
      const w = petSize.value, h = petSize.value // 桌宠容器尺寸（随三档设置变化）
      const fabElReal = fabEl.value
      if (fabElReal) {
        const r = fabElReal.getBoundingClientRect()
        if (r.width > 0) return r  // FAB 可见时用真实 rect
      }
      return { left: pos.value.x, top: pos.value.y, right: pos.value.x + w, bottom: pos.value.y + h, width: w, height: h }
    }
    // 无保存位置 → FAB 用 CSS 默认（右下角），读真实 DOM
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

  // ── 面板独立位置（与 FAB 解耦） ──
  function persistPanel(p: FabPos | null) {
    panelPos.value = p
    if (p) localStorage.setItem(PANEL_STORAGE_KEY, JSON.stringify(p))
    else localStorage.removeItem(PANEL_STORAGE_KEY)
  }
  /** 面板拖动中调用：夹进视口并落库。 */
  function movePanelClamped(x: number, y: number, w: number, h: number) {
    persistPanel(clampPos(x, y, w, h))
  }
  /** 窗口缩放时：把已存面板位置夹进当前视口。 */
  function refitPanelToViewport(w: number, h: number) {
    if (!panelPos.value) return
    persistPanel(clampPos(panelPos.value.x, panelPos.value.y, w, h))
  }

  // ── 桌宠尺寸 / 贴边收起（模块级单例，重启还原） ──
  function setPetSize(px: number) {
    if (!PET_SIZE_TIERS.some((t) => t.px === px)) return
    petSize.value = px
    localStorage.setItem(PET_SIZE_KEY, JSON.stringify(px))
  }
  function setDockEdge(edge: PetDockEdge | null) {
    dockEdge.value = edge
    if (edge) localStorage.setItem(PET_DOCK_KEY, edge)
    else localStorage.removeItem(PET_DOCK_KEY)
  }

  return {
    pos,
    panelPos,
    petSize,
    dockEdge,
    FAB_EDGE_MARGIN,
    FAB_DRAG_THRESHOLD,
    PANEL_WIDTH,
    PANEL_MAX_HEIGHT,
    PANEL_GAP,
    PET_SIZE_TIERS,
    PET_DOCK_SLIDE,
    PET_DOCK_SNAP,
    setFabEl,
    getFabRect,
    persist,
    moveClamped,
    refitToViewport,
    panelSize,
    persistPanel,
    movePanelClamped,
    refitPanelToViewport,
    setPetSize,
    setDockEdge,
  }
}
