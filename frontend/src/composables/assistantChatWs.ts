import type { AssistantMessage } from '@/api/assistant'

export interface NodeTrace {
  step: string
  label: string
  status: string
  input?: any
  output?: any
  summary?: string
  artifact?: { kind: string; title: string; data?: any } | null
}

export interface AssistantChatWsState {
  messages: AssistantMessage[]
  streamingText: string
  thinkingText: string
  waiting: boolean
  statusText: string
  error: string
  nodeTraces: NodeTrace[]
}

/** 方案助手与 AI 办公室共用：把 chunk/done/error 收口到同一份聊天状态。 */
export function handleAssistantChatWsEvent(
  state: AssistantChatWsState,
  data: any,
): boolean {
  switch (data?.type) {
    case 'pipeline_start':
      state.nodeTraces = []
      state.thinkingText = ''
      return true
    case 'step_start':
      return true
    case 'step_done':
      return true
    case 'node_trace':
      if (data.step) {
        const idx = state.nodeTraces.findIndex((t) => t.step === String(data.step))
        const next: NodeTrace = {
          step: String(data.step),
          label: String(data.label || data.step || ''),
          status: String(data.status || 'done'),
          input: data.input,
          output: data.output,
          summary: data.summary || '',
          artifact: data.artifact || null,
        }
        if (idx >= 0) state.nodeTraces.splice(idx, 1, next)
        else state.nodeTraces.push(next)
      }
      return true
    case 'step_progress': {
      // 流式渲染 agent 思考/工具状态：让用户看到模型正在驱动，而非干等“思考中…”。
      const sub = data.sub || {}
      if (sub.kind === 'thinking' && typeof sub.text === 'string') {
        state.thinkingText += sub.text
      } else if (sub.kind === 'tool' && typeof sub.text === 'string') {
        state.statusText = sub.text
      }
      return true
    }
    case 'thinking':
      if (typeof data.text === 'string') {
        state.thinkingText += data.text
      }
      return true
    case 'approval_required':
      if (data.message) state.messages.push(data.message as AssistantMessage)
      return true
    case 'business_entity_ready':
      state.waiting = false
      state.statusText = ''
      if (data.message) state.messages.push(data.message as AssistantMessage)
      return true
    case 'analysis_finished':
    case 'pipeline_done':
    case 'pipeline_paused':
      state.waiting = false
      state.statusText = ''
      return true
    case 'chat_status':
      state.statusText = data.text || ''
      return true
    case 'chat_progress':
      if (data.message) state.messages.push(data.message as AssistantMessage)
      return true
    case 'chunk':
      if (typeof data.delta === 'string') {
        state.streamingText += data.delta
      }
      return true
    case 'done':
      state.waiting = false
      state.statusText = ''
      if (data.message) state.messages.push(data.message as AssistantMessage)
      state.streamingText = ''
      return true
    case 'error':
      state.waiting = false
      state.statusText = ''
      state.error = data.message || '回复异常'
      state.streamingText = ''
      return true
    default:
      return false
  }
}
