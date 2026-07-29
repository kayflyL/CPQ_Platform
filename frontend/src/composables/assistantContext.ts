/**
 * 多域上下文 provider — 助手是全局 UI,未来会接策略中心等模块,
 * 上下文不能写死成商机/报价。每个业务域注册一个 provider,助手按当前页
 * 激活的 provider 收集摘要,拼进 system prompt。
 *
 * 加新城(如策略中心):在 assistantProviders.ts 注册一个 provider 即可,
 * 助手核心(DefaultLayout / useAssistant / AssistantPanel)不改。
 */
import { computed, ref, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { useQuoteStore } from '@/store/quote'
import { contextProviders, assistantQuickActions } from '@/composables/assistantProviders'

export interface ProviderCtx {
  route: ReturnType<typeof useRoute>
  store: ReturnType<typeof useQuoteStore>
}

export interface ContextProvider {
  key: string
  label: string
  match: (ctx: ProviderCtx) => boolean
  summarize: (ctx: ProviderCtx) => Promise<string>
}

/** 助手快捷指令：绑到某个 provider，仅在该 provider 激活的页面渲染。 */
export interface QuickAction {
  key: string
  label: string
  icon?: string
  /** 命中该 key 的 provider 激活时才显示 */
  providerKey: string
  /** 点击后发出的指令文本；可为函数以动态读取配置（如趋势分析 prompt） */
  prompt: string | (() => Promise<string>)
  /** 可选：自定义上下文构造（缺省走通用 provider summarize） */
  context?: () => Promise<string>
}

// Provider 配置（从后端读取）
interface ProviderConfig {
  enabled: boolean
  label: string
  detail: 'brief' | 'detailed'
}

const providerConfig = ref<Record<string, ProviderConfig>>({})

// 加载 Provider 配置
async function loadProviderConfig() {
  try {
    const res = await fetch('/api/system-config/ai_assistant_config/value')
    const data = await res.json()
    if (data.value?.providers) {
      providerConfig.value = data.value.providers
    }
  } catch {
    // 使用默认配置
  }
}

// 首次加载
loadProviderConfig()

export function useAssistantContext() {
  const route = useRoute()
  const store = useQuoteStore()
  const ctx: ProviderCtx = { route, store }

  const activeProviders: ComputedRef<ContextProvider[]> = computed(() =>
    contextProviders.filter((p) => {
      // 检查是否被禁用
      const config = providerConfig.value[p.key]
      if (config && !config.enabled) {
        return false
      }
      try {
        return p.match(ctx)
      } catch {
        return false
      }
    }),
  )

  const contextLabel = computed(() => {
    const labels = activeProviders.value.map((p) => {
      // 使用配置的 label（如果有）
      const config = providerConfig.value[p.key]
      return config?.label || p.label
    })
    return labels.length ? labels.join(' · ') : ''
  })

  const visibleQuickActions = computed(() => {
    const activeKeys = new Set(activeProviders.value.map((p) => p.key))
    return assistantQuickActions.filter((a) => activeKeys.has(a.providerKey))
  })

  async function summarize(): Promise<string> {
    const active = activeProviders.value
    if (!active.length) return ''
    const parts: string[] = []
    for (const p of active) {
      try {
        const text = await p.summarize(ctx)
        if (text) {
          const config = providerConfig.value[p.key]
          const label = config?.label || p.label
          parts.push(`【${label}】\n${text}`)
        }
      } catch {
        /* skip failed provider */
      }
    }
    return parts.join('\n\n')
  }

  return { activeProviders, contextLabel, summarize, providerConfig, loadProviderConfig, visibleQuickActions }
}
