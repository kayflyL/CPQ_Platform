/**
 * 门户内共享同一个 useAssistant 实例的注入键。
 *
 * useAssistant() 每次调用返回独立 refs（非单例），门户的侧栏(Portal.vue) 与
 * 对话区(PortalAIInput.vue) 必须共享同一实例：在侧栏切会话才会更新对话区消息。
 * Portal.vue 持有唯一实例并 provide，PortalAIInput inject 复用。
 */
import type { InjectionKey } from 'vue'
import type { useAssistant } from '@/composables/useAssistant'

export type PortalAssistant = ReturnType<typeof useAssistant>
export const PORTAL_ASSISTANT_KEY: InjectionKey<PortalAssistant> = Symbol('portal-assistant')
