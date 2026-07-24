/**
 * 多域上下文 provider — 助手是全局 UI,未来会接策略中心等模块,
 * 上下文不能写死成商机/报价。每个业务域注册一个 provider,助手按当前页
 * 激活的 provider 收集摘要,拼进 system prompt。
 *
 * 加新城(如策略中心):在 assistantProviders.ts 注册一个 provider 即可,
 * 助手核心(DefaultLayout / useAssistant / AssistantPanel)不改。
 */
import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { useQuoteStore } from '@/store/quote'
import { contextProviders } from '@/composables/assistantProviders'

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

export function useAssistantContext() {
  const route = useRoute()
  const store = useQuoteStore()
  const ctx: ProviderCtx = { route, store }

  const activeProviders: ComputedRef<ContextProvider[]> = computed(() =>
    contextProviders.filter((p) => {
      try {
        return p.match(ctx)
      } catch {
        return false
      }
    }),
  )

  const contextLabel = computed(() => {
    const labels = activeProviders.value.map((p) => p.label)
    return labels.length ? labels.join(' · ') : ''
  })

  async function summarize(): Promise<string> {
    const active = activeProviders.value
    if (!active.length) return ''
    const parts: string[] = []
    for (const p of active) {
      try {
        const text = await p.summarize(ctx)
        if (text) parts.push(`【${p.label}】\n${text}`)
      } catch {
        /* skip failed provider */
      }
    }
    return parts.join('\n\n')
  }

  return { activeProviders, contextLabel, summarize }
}
