import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

/**
 * 数字补间滚动 —— 目标值变化时平滑过渡（ease-out），用于"数据读数"动效。
 * 尊重 prefers-reduced-motion：减弱动效环境下直接跳到目标值。
 */
export function useCountUp(getter: () => number, duration = 900) {
  const display = ref(0)
  let raf = 0

  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  const animate = (to: number) => {
    cancelAnimationFrame(raf)
    const from = display.value
    if (from === to) return
    if (reduceMotion) { display.value = to; return }
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      display.value = from + (to - from) * eased
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }

  onMounted(() => animate(getter()))
  watch(getter, (n) => animate(n))
  onBeforeUnmount(() => cancelAnimationFrame(raf))

  return display
}
