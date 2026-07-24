/**
 * 全平台系列唯一权威源 composable。
 * 数据来自 system_config.server_series（经 /api/base-configs/series）。
 * 所有需要"系列/平台类型"枚举的地方——商机筛选、基准配置编辑、料号库适用机型、图表分组——
 * 都应读这里，避免各自硬编码 Orion/Polaris。改名/新增系列只改 server_series 一处即可全站生效。
 * 模块级缓存，跨组件共享，整个会话只请求一次。
 */
import { ref, computed } from 'vue'
import { baseConfigApi } from '@/api/serverConfig'

export interface SeriesItem { value: string; label: string }

const _items = ref<SeriesItem[]>([])
const _loaded = ref(false)
let _promise: Promise<void> | null = null

/** 加载系列列表（幂等，多次调用只请求一次；失败留空数组，各处自行兜底） */
export function ensureSeries(): Promise<void> {
  if (_loaded.value) return Promise.resolve()
  if (!_promise) {
    _promise = baseConfigApi.listSeries()
      .then(r => { _items.value = (r.items || []).filter(i => i && i.value) })
      .catch(() => {})
      .finally(() => { _loaded.value = true })
  }
  return _promise
}

export function useSeries() {
  const items = computed(() => _items.value)
  const values = computed(() => _items.value.map(i => i.value))
  return { items, values, ensureSeries }
}
