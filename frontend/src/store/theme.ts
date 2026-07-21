import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'cpq-theme'

/** 读取初始主题：localStorage 优先，否则跟随系统 prefers-color-scheme，默认 light（Soft Glassmorphism） */
export function detectTheme(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY)
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
    localStorage.setItem(STORAGE_KEY, next)
    applyTheme(next)
  }

  function toggle() {
    setMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  // 跟随系统：仅在用户未手动选择过时，响应系统深浅变化
  const mql = window.matchMedia?.('(prefers-color-scheme: dark)')
  if (mql) {
    mql.addEventListener('change', (e) => {
      if (!localStorage.getItem(STORAGE_KEY)) {
        const next: ThemeMode = e.matches ? 'dark' : 'light'
        mode.value = next
        applyTheme(next)
      }
    })
  }

  return { mode, isDark, setMode, toggle }
})
