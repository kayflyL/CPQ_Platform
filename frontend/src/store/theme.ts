import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'cpq-theme'

/** 读取初始主题：localStorage 优先，否则跟随系统 prefers-color-scheme，默认 light（Soft Glassmorphism） */
export function detectTheme(): ThemeMode {
  let stored: string | null
  try {
    stored = localStorage.getItem(STORAGE_KEY)
  } catch {
    stored = null
  }
  if (stored === 'dark' || stored === 'light') return stored
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

/** 把主题写到 <html data-theme="...">，驱动 tokens.css 双主题切换 */
export function applyTheme(mode: ThemeMode) {
  document.documentElement.dataset.theme = mode
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(detectTheme())
  applyTheme(mode.value)

  const isDark = computed(() => mode.value === 'dark')

  function setMode(next: ThemeMode) {
    mode.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* localStorage 不可用时静默降级，内存态 mode 仍生效 */
    }
    applyTheme(next)
  }

  function toggle() {
    setMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  // 守护：<html data-theme> 以 app 内 mode 为唯一真源。
  // 浏览器改色扩展（Dark Reader 等）或浏览器强制配色会直接写 data-theme，
  // 造成 CSS 主题（data-theme）与图表/Antd 主题（isDark）错位——表现为浅色页面+深色饼图黑边。
  // 一旦 data-theme 与 mode 不一致，立即纠正，保证两者永远同步。
  if (typeof MutationObserver !== 'undefined') {
    const el = document.documentElement
    const guard = new MutationObserver(() => {
      if (el.dataset.theme !== mode.value) applyTheme(mode.value)
    })
    guard.observe(el, { attributes: true, attributeFilter: ['data-theme'] })
  }

  // 不再监听系统 prefers-color-scheme 的中途变化：
  // 用户手动选择即为最终态，刷新/系统日夜切换都不覆盖；
  // 首次访问（未选过）由 index.html 首屏脚本 + detectTheme 一次性确定。

  return { mode, isDark, setMode, toggle }
})
