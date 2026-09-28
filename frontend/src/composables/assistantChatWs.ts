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

/**
 * 中断点事实（P5-B2）：后端 pause 载荷（skill_plan_runtime.pause_payload）里与展示相关的字段。
 * 只有事实与原因码——怎么措辞是 UI 的事，载荷本身不带话术。
 */
export interface PauseFacts {
  kind: string
  step: string
  label: string
  reason_code: string
  resumable: boolean
}

export function pauseFactsOf(payload: unknown): PauseFacts | null {
  const p = (payload || null) as Record<string, any> | null
  if (!p || typeof p !== 'object') return null
  const kind = String(p.kind || '')
  if (!kind) return null
  return {
    kind,
    step: String(p.step || ''),
    label: String(p.label || ''),
    reason_code: String(p.reason_code || ''),
    resumable: p.resumable !== false,
  }
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
  /** 排队中消息数（后端 queue_state 事件驱动）：回合执行中再发消息会排队串行续跑 */
  queuedCount: number
  /** 任务胶囊（Claude Code 式计步器）：标题来自 pipeline_start.title，phase 由管线事件驱动 */
  taskTitle: string
  taskPhase: '' | 'running' | 'paused' | 'done'
  /** 中断点事实（P5-B2）：原样来自后端 pause 载荷，UI 只按事实显示，不加工 */
  taskPause: PauseFacts | null
}

/** 新消息发送时收起已完成的任务胶囊（running/paused 保留——任务还在进行） */
export function resetTaskUI(state: AssistantChatWsState) {
  if (state.taskPhase !== 'done') return
  state.nodeTraces = []
  state.taskPhase = ''
  state.taskPause = null
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
  state.queuedCount = 0
  if (state.taskPhase === 'running') state.taskPhase = 'done'
}

/**
 * 服务端事实重建任务胶囊（2026-09-13）：pipeline 事件只发一次不重放，页面刷新 /
 * WS 重连空窗 / 中途切会话后骨架已丢——messages 端点随 turn_active / engine_pause
 * 下发 task_state（引擎 steps_done + 步骤视图），按它重建。与 pipeline_start /
 * node_trace 事件同形状，展示层零加工。ts 为 null 时不动现有状态。
 */
export function applyTaskState(state: AssistantChatWsState, ts: { title?: string; steps?: Array<{ key?: string; step?: string; label?: string }>; done?: string[]; phase?: string; pause?: PauseFacts | Record<string, any> | null } | null | undefined) {
  const steps = Array.isArray(ts?.steps) ? ts!.steps : []
  if (!steps.length) return
  const doneSet = new Set((ts!.done || []).map((k) => String(k)))
  state.nodeTraces = steps.map((s) => ({
    step: String(s.key || s.step || ''),
    label: String(s.label || s.key || s.step || ''),
    status: doneSet.has(String(s.key || s.step || '')) ? 'done' : 'pending',
  }))
  state.taskTitle = String(ts!.title || '配置任务')
  state.taskPause = (ts!.pause && typeof ts!.pause === 'object' ? ts!.pause : null) as PauseFacts | null
  state.taskPhase = ts!.phase === 'paused' ? 'paused' : 'running'
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
      state.taskPause = null
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
      state.taskPause = null
      return true
    case 'pipeline_paused':
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.streamingText = ''
      state.taskPhase = 'paused'
      state.taskPause = pauseFactsOf(data.pause)
      return true
    case 'pipeline_waiting':
      // 问问题/弹卡时任务仍视为进行中（Claude Code 式：有问才停，但任务未结束）。
      state.waiting = false
      state.taskPhase = 'running'
      state.taskPause = pauseFactsOf(data.pause)
      // running=false 让卡片可点（两处 optionInteractive 均以 !running 判定）；
      // taskPhase='running' 让胶囊仍显示「执行中」而非「已暂停」。
      state.running = false
      state.streamingText = ''
      return true
    case 'analysis_cancelled':
      state.nodeTraces = []
      state.waiting = false
      state.statusText = ''
      state.running = false
      state.queuedCount = 0
      state.taskPhase = ''
      state.taskTitle = ''
      return true
    case 'chat_status':
      state.statusText = data.text || ''
      return true
    case 'queue_state':
      // 排队可见化：被扣住的消息不能看起来和空闲一样（2026-09-13 P0-③）
      state.queuedCount = Math.max(0, Number(data.depth) || 0)
      return true
    case 'chat_progress':
      pushMessage(state, data.message)
      return true
    case 'chunk':
      if (typeof data.delta === 'string') {
        state.streamingText += data.delta
      }
      return true
    case 'chunk_reset':
      // 工具轮覆盖语义（UI 侧）：新一轮正文首字前清空旁白，防止「旁白+最终答案」连拼
      state.streamingText = ''
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
