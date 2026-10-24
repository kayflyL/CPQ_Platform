/** 全站统一的移动端判断（≤768px，与各页 CSS 断点同源）。
 * 模块级单例：一个 matchMedia 监听器驱动所有订阅组件，
 * 替代此前各组件各自手写 window.matchMedia 的散乱做法；新代码一律用这个。 */
import { ref } from 'vue'

const QUERY = '(max-width: 768px)'
const isMobile = ref(false)
let initialized = false

function init() {
  if (initialized || typeof window === 'undefined') return
  initialized = true
  const mq = window.matchMedia(QUERY)
  isMobile.value = mq.matches
  mq.addEventListener('change', (e) => { isMobile.value = e.matches })
}

export function useIsMobile() {
  init()
  return isMobile
}
