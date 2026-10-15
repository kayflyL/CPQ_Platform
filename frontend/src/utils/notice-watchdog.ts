import { message } from 'ant-design-vue'

// 后台标签页里 setTimeout 被浏览器强节流，antd message 的自动关闭定时器在切走期间
// 不触发，回前台后偶发提示滞留不消失（antd 已知问题，同 ant-design#32161），
// 残留的提示会盖在顶栏导航按钮上。这里记录每条提示的诞生时间，回前台（另加 5s 定期）
// 把超过正常寿命仍残留的提示强制清掉；顺带把全局提示位置下移到 56px 顶栏之下。
const MAX_AGE_MS = 10_000 // message 默认 3s；loading 型手动关、见豁免，10s 起算僵尸
const NOTICE_SELECTOR = '.ant-message-notice, .ant-notification-notice'
const LOADING_SELECTOR = '.ant-message-notice-loading, .ant-notification-notice-loading'

const bornAt = new WeakMap<Element, number>()
let installed = false

function sweep() {
  if (document.visibilityState !== 'visible') return
  const now = Date.now()
  const stale = Array.from(document.querySelectorAll<Element>(NOTICE_SELECTOR)).some(
    (el) =>
      !el.matches(LOADING_SELECTOR) && now - (bornAt.get(el) ?? now) > MAX_AGE_MS,
  )
  // destroy() 重置内部提示列表并清空容器——「内部已关、DOM 残留」的僵尸只有这一种清法
  if (stale) message.destroy()
}

export function installNoticeWatchdog() {
  if (installed) return
  installed = true
  // 顶栏 fixed 56px（DefaultLayout .site-header），默认 top:8px 会盖住导航按钮
  message.config({ top: '64px' })
  new MutationObserver((muts) => {
    for (const m of muts) {
      for (const n of m.addedNodes) {
        if (!(n instanceof Element)) continue
        if (n.matches(NOTICE_SELECTOR)) {
          bornAt.set(n, Date.now())
          continue
        }
        // 首条提示会和容器一起插入，notice 藏在新增子树里
        n.querySelectorAll(NOTICE_SELECTOR).forEach((el) => {
          if (!bornAt.has(el)) bornAt.set(el, Date.now())
        })
      }
    }
  }).observe(document.body, { childList: true, subtree: true })
  document.addEventListener('visibilitychange', sweep)
  setInterval(sweep, 5000)
}
