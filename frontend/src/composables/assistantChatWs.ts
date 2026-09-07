import type { AssistantMessage } from '@/api/assistant'

export interface NodeTrace {
  step: string
  label: string
  status: string
  input?: any
  output?: any
  summary?: string
  artifact?: { kind: string; title: string; data?: any } | null
  duration_ms?: number
}

export interface AssistantChatWsState {
  messages: AssistantMessage[]
  streamingText: string
  thinkingText: string
  waiting: boolean
  statusText: string
  error: string
  nodeTraces: NodeTrace[]
  running: boolean
  /** 任务胶囊（Claude Code 式计步器）：标题来自 pipeline_start.title，phase 由管线事件驱动 */
  taskTitle: string
  taskPhase: '' | 'running' | 'paused' | 'done'
}

/** 新消息发送时收起已完成的任务胶囊（running/paused 保留——任务还在进行） */
export function resetTaskUI(state: AssistantChatWsState) {
  if (state.taskPhase !== 'done') return
  state.nodeTraces = []
  state.taskPhase = ''
  state.taskTitle = ''
}

// ── 思考流合帧（2026-09-05）：reasoning token 逐个到达，直写状态 = 每 token 一次
// 响应式更新 + thinkingTail 全文正则重算，视觉上就是高频闪烁。这里 150ms 批量落盘，
// 并保持尾部滚动窗口（6000 字）让 thinkingTail 的成本有界。Claude Code 的思考行
// 同理是节流后的展示，不是原始 token 流。
const THINKING_FLUSH_MS = 150
const THINKING_MAX_CHARS = 6000
const thinkingBufs = new WeakMap<AssistantChatWsState, { text: string; timer: ReturnType<typeof setTimeout> | null }>()

function appendThinking(state: AssistantChatWsState, text: string) {
  let buf = thinkingBufs.get(state)
  if (!buf) {
    buf = { text: '', timer: null }
    thinkingBufs.set(state, buf)
  }
  buf.text += text
  if (buf.timer == null) {
    buf.timer = setTimeout(() => {
      if (buf.timer != null) { clearTimeout(buf.timer); buf.timer = null }
      const pending = buf.text
      buf.text = ''
      state.thinkingText = (state.thinkingText + pending).slice(-THINKING_MAX_CHARS)
    }, THINKING_FLUSH_MS)
  }
}

function clearThinking(state: AssistantChatWsState) {
  const buf = thinkingBufs.get(state)
  if (buf) {
    if (buf.timer != null) clearTimeout(buf.timer)
    buf.text = ''
    buf.timer = null
  }
  state.thinkingText = ''
}

export { clearThinking }

// ── 终态事件丢失兜底（2026-09-05）：WS 断线重连窗口里 done 等终态事件永久丢失，
// 后端回合其实已完成并持久化，前端 waiting 永真 = 三点假死。看门狗按「无事件超时」
// 触发 resync：拉服务端消息比对，有未收到的新消息 = 回合已结束，采纳并清流式态；
// 没有新消息 = 回合仍在跑（LLM 静默期），退避一个周期继续等。
const lastEventAt = new WeakMap<AssistantChatWsState, number>()
const TURN_STALE_MS = 45_000

/** 回合已被 resync 证实结束：清流式假死态（与终态事件同口径）。 */
export function adoptTurnEnd(state: AssistantChatWsState) {
  state.waiting = false
  state.running = false
  state.statusText = ''
  state.streamingText = ''
  if (state.taskPhase === 'running') state.taskPhase = 'done'
}

/**
 * @param resync 拉服务端消息并采纳，返回「是否有本地未见的新消息」（true=回合已结束）
 * @returns 停止函数
 */
export function createTurnWatchdog(state: AssistantChatWsState, resync: () => Promise<boolean>): () => void {
  let stopped = false
  const timer = setInterval(() => {
    if (stopped || !state.waiting) return
    const last = lastEventAt.get(state) || 0
    if (Date.now() - last < TURN_STALE_MS) return
    void (async () => {
      try {
        const adopted = await resync()
        if (adopted) {
          adoptTurnEnd(state)
        } else {
          lastEventAt.set(state, Date.now())
        }
      } catch {
        lastEventAt.set(state, Date.now())
      }
    })()
  }, 10_000)
  return () => {
    stopped = true
    clearInterval(timer)
  }
}

function pushMessage(state: AssistantChatWsState, msg: unknown) {
  const m = msg as { message_id?: string } | undefined
  if (!m) return
  // 去重：看门狗 resync 采纳过服务端消息后，迟到的同 id 广播不再重复入列
  if (m.message_id && state.messages.some((x) => x.message_id === m.message_id)) return
  state.messages.push(m as AssistantMessage)
}

/** 方案助手与 AI 办公室共用：把 chunk/done/error 收口到同一份聊天状态。 */
export function handleAssistantChatWsEvent(
  state: AssistantChatWsState,
  data: any,
): boolean {
  lastEventAt.set(state, Date.now())
  switch (data?.type) {
    case 'pipeline_start': {
      // 由后端算好的完整步骤骨架预置计划条，避免「只显示已跑节点」的闪烁/截断。
      state.nodeTraces = (Array.isArray(data.steps) ? data.steps : []).map((s: any) => ({
        step: String(s.key || s.step || ''),
        label: String(s.label || s.key || s.step || ''),
        status: 'pending',
      }))
      clearThinking(state)
      state.running = true
      state.taskTitle = String(data.title || '配置任务')
      state.taskPhase = 'running'
      return true
    }
    case 'stopping':
      state.statusText = data.message || '正在暂停当前任务…'
      return true
    case 'step_start': {
      const idx = state.nodeTraces.findIndex((t) => t.step === String(data.step))
      if (idx >= 0) state.nodeTraces.splice(idx, 1, { ...state.nodeTraces[idx], status: 'running', label: String(data.label || state.nodeTraces[idx].label || data.step) })
      else state.nodeTraces.push({ step: String(data.step), label: String(data.label || data.step), status: 'running' })
      return true
    }
    case 'step_done': {
      const idx = state.nodeTraces.findIndex((t) => t.step === String(data.step))
      if (idx >= 0) state.nodeTraces.splice(idx, 1, { ...state.nodeTraces[idx], status: 'done', label: String(data.label || state.nodeTraces[idx].label || data.step) })
      else state.nodeTraces.push({ step: String(data.step), label: String(data.label || data.step), status: 'done' })
      return true
    }
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
          duration_ms: typeof data.duration_ms === 'number' ? data.duration_ms : undefined,
        }
        if (idx >= 0) state.nodeTraces.splice(idx, 1, next)
        else state.nodeTraces.push(next)
      }
      return true
    case 'step_progress': {
      // 流式渲染 agent 思考/工具状态：让用户看到模型正在驱动，而非干等“思考中…”。
      const sub = data.sub || {}
      if (sub.kind === 'thinking' && typeof sub.text === 'string') {
        appendThinking(state, sub.text)
      } else if (sub.kind === 'tool' && typeof sub.text === 'string') {
        state.statusText = sub.text
      }
      return true
    }
    case 'thinking':
      if (typeof data.text === 'string') {
        appendThinking(state, data.text)
      }
      return true
    case 'approval_required':
      pushMessage(state, data.message)
      return true
    case 'business_entity_ready': {
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.streamingText = ''
      state.taskPhase = 'done'
      // 方案卡消息必须以完整消息对象入列（kind=business_artifact + data JSON 串）：
      // 裸字符串没有 role/kind/content，落进消息组件的直播兜底分支=永久三点泡、
      // 卡片不渲染（2026-09-06 四犯定案）。后端现已随事件带落库对象；此处对旧格式
      // 字符串兜底组装，字段口径对齐 colleague_turn_service.result_data
      const m = (data.message && typeof data.message === 'object') ? data.message : {
        role: 'assistant',
        kind: 'business_artifact',
        content: String(data.message || ''),
        data: JSON.stringify({
          bom_scheme: data.entity,
          entity_type: String(data.entity_type || 'bom_scheme'),
          opportunity_id: String(data.opportunity_id || ''),
          target: 'bom_scheme',
        }),
      }
      pushMessage(state, m)
      return true
    }
    case 'analysis_finished':
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.streamingText = ''
      state.taskPhase = 'done'
      return true
    case 'pipeline_done':
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.streamingText = ''
      state.taskPhase = 'done'
      return true
    case 'pipeline_paused':
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.streamingText = ''
      state.taskPhase = 'paused'
      return true
    case 'analysis_cancelled':
      state.nodeTraces = []
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.taskPhase = ''
      state.taskTitle = ''
      return true
    case 'chat_status':
      state.statusText = data.text || ''
      return true
    case 'chat_progress':
      pushMessage(state, data.message)
      return true
    case 'chunk':
      if (typeof data.delta === 'string') {
        state.streamingText += data.delta
      }
      return true
    case 'done':
      state.waiting = false
      state.statusText = ''
      state.running = false
      pushMessage(state, data.message)
      state.streamingText = ''
      return true
    case 'error':
      state.waiting = false
      state.statusText = ''
      state.error = data.message || '回复异常'
      state.streamingText = ''
      state.running = false
      return true
    default:
      return false
  }
}
