import { ref, computed, watch, type ComputedRef } from 'vue'
import { catalogApi, baseConfigApi, type ServerModel } from '@/api/serverConfig'
import type { ConfigData } from '@/store/quote'

export function useQuoteServerModels(activeConfig: ComputedRef<ConfigData | undefined>) {
  const serverModels = ref<ServerModel[]>([])
  const baseInfoCache = ref<Record<number, { series: string; name: string; model_id?: number | null }>>({})
  const chassisModalOpen = ref(false)

  async function loadServerModels() {
    try {
      const res = await catalogApi.listModels()
      serverModels.value = res.models || []
    } catch (e) {
      console.warn('加载机型目录失败', e)
    }
  }

  async function loadBaseInfo(baseConfigId?: number | null) {
    if (!baseConfigId) return
    if (baseInfoCache.value[baseConfigId]) return
    try {
      const bc = await baseConfigApi.get(baseConfigId)
      baseInfoCache.value[baseConfigId] = {
        series: (bc as any).series || '',
        name: (bc as any).name || '',
        model_id: (bc as any).model_id ?? null,
      }
    } catch {
      /* 基准配置缺失时机箱卡显示 — */
    }
  }

  function backfillServerModelId(cfg: ConfigData) {
    if (cfg.server_model_id) return
    const name = String(cfg.server_model || '').trim()
    if (name) {
      const byName = serverModels.value.find((m) => m.name === name)
      if (byName) {
        cfg.server_model_id = byName.id
        return
      }
    }
    const info = cfg.base_config_id ? baseInfoCache.value[cfg.base_config_id] : null
    if (info?.model_id) {
      const byBc = serverModels.value.find((m) => m.id === info.model_id)
      if (byBc) cfg.server_model_id = byBc.id
    }
  }

  const chassisModel = computed<ServerModel | { name: string }>(() => {
    const cfg = activeConfig.value
    if (!cfg) return { name: '' }
    const matched = serverModels.value.find((m) => m.id === cfg.server_model_id)
    if (matched) return matched
    return { name: cfg.server_model || '—' }
  })

  const chassisSeries = computed(() => {
    const cfg = activeConfig.value
    const id = cfg?.base_config_id
    return id ? (baseInfoCache.value[id]?.series || '') : ''
  })

  const chassisBaseName = computed(() => {
    const cfg = activeConfig.value
    const id = cfg?.base_config_id
    return id ? (baseInfoCache.value[id]?.name || '') : ''
  })

  const chassisMatched = computed(() => !!activeConfig.value?.server_model_id)

  const serverModelOptions = computed(() =>
    serverModels.value.map((m) => ({
      value: m.name,
      label: `${m.name}${m.base_config?.form ? ' · ' + m.base_config.form : ''}${m.use ? ' · ' + m.use : ''}`,
    })),
  )

  function onServerModelSelect(name: string) {
    const cfg = activeConfig.value
    if (!cfg) return
    const matched = serverModels.value.find((m) => m.name === name)
    if (matched) {
      cfg.server_model_id = matched.id
      if (matched.base_config_id) {
        cfg.base_config_id = matched.base_config_id
        loadBaseInfo(matched.base_config_id)
      }
    }
  }

  watch(
    () => activeConfig.value?.server_model,
    (name) => {
      const cfg = activeConfig.value
      if (!cfg) return
      const v = (name || '').toString()
      if (!v.trim()) {
        cfg.server_model_id = undefined
        return
      }
      const matched = serverModels.value.find((m) => m.name === v)
      if (matched) {
        cfg.server_model_id = matched.id
        if (matched.base_config_id && cfg.base_config_id !== matched.base_config_id) {
          cfg.base_config_id = matched.base_config_id
          loadBaseInfo(matched.base_config_id)
        }
      } else {
        cfg.server_model_id = undefined
      }
    },
  )

  watch(() => activeConfig.value?.base_config_id, (id) => {
    if (id) loadBaseInfo(id)
  })

  return {
    serverModels,
    baseInfoCache,
    chassisModalOpen,
    loadServerModels,
    loadBaseInfo,
    backfillServerModelId,
    chassisModel,
    chassisSeries,
    chassisBaseName,
    chassisMatched,
    serverModelOptions,
    onServerModelSelect,
  }
}
