import { computed } from 'vue'
import { useThemeStore } from '@/store/theme'

/**
 * 图表配色（chart.js / echarts 用 canvas 渲染，读不到 CSS 变量，必须给真实色值）。
 * 按当前主题返回对应色板；主题切换时 computed 重算，驱动图表重绘。
 */
export function useChartTheme() {
  const themeStore = useThemeStore()

  const chartColors = computed(() => {
    const isDark = themeStore.isDark
    return {
      accent: '#1677FF',
      accentFill: 'rgba(22, 119, 255, 0.10)',
      grid: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(22, 119, 255, 0.05)',
      splitLine: isDark ? 'rgba(255, 255, 255, 0.03)' : 'rgba(22, 119, 255, 0.04)',
      tick: isDark ? '#6E7582' : '#86909c',
      axisLabel: isDark ? '#8A94A8' : '#86909c',
      tooltipBg: isDark ? 'rgba(8, 9, 11, 0.92)' : 'rgba(255, 255, 255, 0.92)',
      tooltipBorder: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.6)',
      tooltipText: isDark ? '#E8EDF7' : '#1d2129',
      tooltipTitle: isDark ? '#E8ECEF' : '#1d2129',
      barStart: '#1677FF',
      barEnd: 'rgba(22, 119, 255, 0.15)',
      pointEdge: isDark ? '#08090B' : '#ffffff',
      // 饼图扇区间隔色：匹配图表容器底色，dark 用卡片底色（不再近黑突兀）、light 用白
      segmentBorder: isDark ? '#101217' : '#ffffff',
      // 趋势涨跌色：绿涨红跌（马卡龙浅色系，呼应 Soft Glassmorphism 语义色）
      up: '#52C9A0',
      down: '#FF6B6B',
    }
  })

  return { chartColors }
}
