/**
 * Assistant API client — 全局「方案助手」AI 聊天窗(骨架期,LLM 待接国产模型).
 * 照 feed.ts 模式:独立 axios + X-User-Id header(identity 复用 Feed user picker).
 */
import axios from 'axios'
import type { AxiosInstance } from 'axios'
import { getCurrentUser, setCurrentUser, feedApi } from './feed'

export interface AssistantThread {
  thread_id: string
  title: string
  opportunity_id: string
  quotation_id: string
  created_by: string
  created_at: string
  updated_at: string
}
export interface AssistantMessage {
  message_id: string
  thread_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  /** text | analysis_trigger | analysis_pending | analysis_confirm | analysis_result */
  kind?: string
  /** 结构化载荷 JSON（analysis_* 消息，如方案列表） */
  data?: string
  opportunity_id: string
  quotation_id: string
  created_at: string
}
export interface AssistantContext {
  opportunityId?: string | null
  quotationId?: string | null
}

/** 需求分析步骤（与 useReasoningStream.ReasoningStep 同构，避免循环依赖） */
export interface AssistantAnalysisStep {
  key: string
  label: string
  status: 'pending' | 'running' | 'done' | 'error'
  payload?: any
}

export interface AssistantAnalysisPrompt {
  reply_id: string
  question: string
  options: string[]
  round: number
  clarity_capped: boolean
  stage?: string
  format?: string
}

export interface AssistantAnalysisConfirmItem {
  id: string
  slot: string
  label: string
  rule?: string | null
  llm?: string | null
  level: 'conflict' | 'low_confidence'
  confidence?: number
  default?: string
}

export interface AssistantAnalysisConfirm {
  reply_id: string
  question: string
  items: AssistantAnalysisConfirmItem[]
  default: string
}

export interface AssistantAnalysisResultData {
  plans: import('@/api/reasoning').Plan[]
  keywords: string[]
  series?: string | null
  form?: string | null
}

const http: AxiosInstance = axios.create({ baseURL: '', timeout: 60000 })
http.interceptors.request.use((config) => {
  const u = getCurrentUser()
  if (u?.user_id) config.headers['X-User-Id'] = u.user_id
  return config
})

/**
 * 确保有一个稳定身份:优先复用 Feed 身份(cpq_feed_current_user),
 * 没有则 ensure 一个「助手用户」并写入 Feed 的 key(与 Feed 共享)。
 * 避免未选身份时落到后端「匿名」→ 会话归属漂移、历史看不到。
 */
export async function ensureAssistantUser() {
  let u = getCurrentUser()
  if (!u) {
    try {
      u = await feedApi.users.ensure('助手用户')
      setCurrentUser(u)
    } catch {
      u = null
    }
  }
  return u
}

export const assistantApi = {
  threads: {
    list: () =>
      http.get<{ threads: AssistantThread[] }>('/api/assistant/threads').then((r) => r.data.threads),
    create: (ctx?: AssistantContext, title?: string) =>
      http
        .post<{ thread: AssistantThread }>('/api/assistant/threads', {
          title,
          opportunity_id: ctx?.opportunityId || null,
          quotation_id: ctx?.quotationId || null,
        })
        .then((r) => r.data.thread),
    remove: (id: string) => http.delete(`/api/assistant/threads/${id}`),
    messages: (id: string) =>
      http
        .get<{ messages: AssistantMessage[] }>(`/api/assistant/threads/${id}/messages`)
        .then((r) => r.data.messages),
    postMessage: (id: string, content: string, contextSummary?: string) =>
      http
        .post<{ user_message: AssistantMessage; thread: AssistantThread }>(
          `/api/assistant/threads/${id}/messages`,
          { content, context_summary: contextSummary || null },
        )
        .then((r) => r.data),
    /** 方案助手需求分析：触发与商机详情页同一套 pipeline，步骤/方案经助手 WS 推送 */
    analyze: (
      id: string,
      body: {
        requirement_text?: string
        supplement_text?: string
        explicit_budget?: number
        force_complete?: boolean
        confirm?: Record<string, string>
      },
    ) =>
      http
        .post<{ status: string; thread_id: string; user_message: AssistantMessage }>(
          `/api/assistant/threads/${encodeURIComponent(id)}/analyze`,
          body,
        )
        .then((r) => r.data),
  },
}

/** WS 订阅某会话的 LLM token 流(chunk / done 由后端 _stream_llm_reply 广播)。 */
export function assistantWsUrl(threadId: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/api/assistant/ws/${encodeURIComponent(threadId)}`
}
