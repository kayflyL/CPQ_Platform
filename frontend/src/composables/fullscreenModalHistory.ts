/** 手机全屏弹窗（ResponsiveModal ≤768 全屏态）与浏览器历史的同步。
 *
 * 打开一个全屏弹窗就压一条 history 栈：系统返回手势 / Android 返回键 / 浏览器后退
 * 消费这条栈来关弹窗，而不是退出整个页面；UI 上的「返回」按钮则主动回退这条栈。
 * 支持嵌套（归档弹窗里再开附件预览）：一次返回只关栈顶那一个。
 */
type CloseFn = () => void

const stack: number[] = []
const closers = new Map<number, CloseFn>()
let seq = 0
let listening = false

function onPop(e: PopStateEvent) {
  const cur = (e.state as { cpqFs?: number } | null)?.cpqFs
  const idx = cur != null ? stack.indexOf(cur) : -1
  // 当前停留的栈条目之上的弹窗全部关闭（cur 不在我们栈里 = 全部退出）
  const cutoff = idx === -1 ? 0 : idx + 1
  while (stack.length > cutoff) {
    const id = stack.pop()!
    const close = closers.get(id)
    closers.delete(id)
    close?.()
  }
  syncBodyClass()
}

function ensureListener() {
  if (listening || typeof window === 'undefined') return
  listening = true
  window.addEventListener('popstate', onPop)
}

function syncBodyClass() {
  // 全屏弹窗打开期间隐藏 AI 桌宠悬浮球（与 em-editor-modal-open 同一机制，规则在 antd-overrides.css）
  document.body.classList.toggle('cpq-fs-modal-open', stack.length > 0)
}

/** 打开时压栈，返回本条栈的句柄（close = 关闭弹窗的回调） */
function push(close: CloseFn): number {
  ensureListener()
  const id = ++seq
  stack.push(id)
  closers.set(id, close)
  history.pushState({ cpqFs: id }, '')
  syncBodyClass()
  return id
}

/** UI 主动关闭（返回按钮/取消）：先摘栈再回退历史，popstate 到来时不会重复 close */
function release(id: number) {
  const idx = stack.indexOf(id)
  if (idx === -1) return
  stack.splice(idx, 1)
  closers.delete(id)
  history.back()
  syncBodyClass()
}

export function useFullscreenModalHistory() {
  return { push, release }
}
