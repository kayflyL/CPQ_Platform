/**
 * 全平台系列 Pinia Store —— 替代原来的 useSeries composable。
 * 解决模块级 ref 跨组件响应式失效的问题。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { baseConfigApi } from '@/api/serverConfig'

export interface SeriesItem { value: string; label: string }

export const useSeriesStore = defineStore('series', () => {
  const _items = ref<SeriesItem[]>([])
  const _loaded = ref(false)
  let _promise: Promise<void> | null = null

  /** 加载系列列表（幂等，多次调用只请求一次） */
  async function ensureSeries(): Promise<void> {
    if (_loaded.value) return
    if (!_promise) {
      _promise = baseConfigApi.listSeries()
        .then(r => { _items.value = (r.items || []).filter(i => i && i.value) })
        .catch(() => {})
        .finally(() => { _loaded.value = true })
    }
    return _promise
  }

  const items = computed(() => _items.value)
  const values = computed(() => _items.value.map(i => i.value))

  return { items, values, ensureSeries, _loaded }
})