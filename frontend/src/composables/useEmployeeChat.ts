import { computed, reactive, ref } from 'vue'
import { assistantApi, assistantWsUrl, type AssistantContext, type AssistantMessage } from '@/api/assistant'
import { handleAssistantChatWsEvent, type NodeTrace } from '@/composables/assistantChatWs'

export interface EmployeeChatState {
  threadId: string | null
  messages: AssistantMessage[]
  threads: import('@/api/assistant').AssistantThread[]
  streamingText: string
  thinkingText: string
  sending: boolean
  running: boolean
  waiting: boolean
  statusText: string
  loading: boolean
  connected: boolean
  error: string
  nodeTraces: NodeTrace[]
}

const states = reactive<Record<string, EmployeeChatState>>({})
const activeRoleKey = ref<string | null>(null)

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function ensureState(roleKey: string): EmployeeChatState {
  if (!states[roleKey]) {
    states[roleKey] = {
      threadId: null,
      messages: [],
      threads: [],
      streamingText: '',
      thinkingText: '',
      sending: false,
      running: false,
      waiting: false,
      statusText: '',
      loading: false,
      connected: false,
      error: '',
      nodeTraces: [],
    }
  }
  return states[roleKey]
}

function clearReconnectTimer() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function disconnect() {
  clearReconnectTimer()
  if (socket) {
    socket.onclose = null
    try {
      socket.close()
    } catch {
      /* ignore */
    }
    socket = null
  }
  if (activeRoleKey.value) {
    const state = states[activeRoleKey.value]
    if (state) state.connected = false
  }
}

function handleSocketData(roleKey: string, data: any) {
  const state = ensureState(roleKey)
  handleAssistantChatWsEvent(state, data)
}

function connect(roleKey: string): Promise<void> {
  disconnect()
  const state = ensureState(roleKey)
  const threadId = state.threadId
  if (!threadId) return Promise.resolve()
  return new Promise((resolve) => {
    try {
      socket = new WebSocket(assistantWsUrl(threadId))
    } catch {
      socket = null
      resolve()
      return
    }
    socket.onopen = () => {
      state.connected = true
      resolve()
    }
    socket.onmessage = (event) => {
      let data: any
      try {
        data = JSON.parse(event.data)
      } catch {
        return
      }
      handleSocketData(roleKey, data)
    }
    socket.onclose = () => {
      socket = null
      state.connected = false
      if (activeRoleKey.value === roleKey && state.threadId) {
        clearReconnectTimer()
        reconnectTimer = setTimeout(() => connect(roleKey), 2000)
      }
    }
    socket.onerror = () => {
      /* REST 已保存用户消息，WS 流中断时允许重连。 */
      resolve()
    }
  })
}

async function ensureConnected(roleKey: string) {
  const state = ensureState(roleKey)
  if (!state.threadId) return
  if (socket && socket.readyState === WebSocket.OPEN && state.connected) return
  await connect(roleKey)
}

async function ensureThread(roleKey: string, context?: AssistantContext): Promise<EmployeeChatState> {
  const state = ensureState(roleKey)
  if (state.threadId) return state

  state.loading = true
  state.error = ''
  try {
    const thread = await assistantApi.threads.resolve(roleKey, context)
    state.threadId = thread.thread_id
    state.messages = await assistantApi.threads.messages(thread.thread_id, 50)
    return state
  } catch (error) {
    state.error = '无法创建与该同事的会话'
    throw error
  } finally {
    state.loading = false
  }
}

async function loadThreads(
  roleKey: string,
  options?: { includePreview?: boolean },
): Promise<import('@/api/assistant').AssistantThread[]> {
  const state = ensureState(roleKey)
  state.error = ''
  state.threads = await assistantApi.threads.listOffice(roleKey, options)
  return state.threads
}

async function openThread(roleKey: string, threadId: string) {
  if (!roleKey || !threadId) return
  const state = ensureState(roleKey)
  activeRoleKey.value = roleKey
  state.loading = true
  state.error = ''
  try {
    state.threadId = threadId
    state.nodeTraces = []
    state.messages = await assistantApi.threads.messages(threadId, 50)
    await connect(roleKey)
  } finally {
    state.loading = false
  }
  return state
}

async function startNewThread(roleKey: string, context?: AssistantContext) {
  if (!roleKey) return
  const state = ensureState(roleKey)
  activeRoleKey.value = roleKey
  state.threadId = null
  state.messages = []
  state.streamingText = ''
  state.waiting = false
  state.error = ''
  state.nodeTraces = []
  state.threads = []
  state.loading = true
  try {
    const thread = await assistantApi.threads.resolve(roleKey, context)
    state.threadId = thread.thread_id
    await connect(roleKey)
    return state
  } catch (error) {
    state.error = '无法创建新会话'
    throw error
  } finally {
    state.loading = false
  }
}

async function softDeleteThread(roleKey: string, threadId: string) {
  await assistantApi.threads.remove(threadId)
  const state = ensureState(roleKey)
  if (state.threadId === threadId) {
    state.threadId = null
    state.messages = []
    state.streamingText = ''
    state.waiting = false
    state.nodeTraces = []
    disconnect()
  }
}

async function open(colleague: any, context?: AssistantContext) {
  const roleKey = String(colleague?.role_key || '')
  if (!roleKey) return

  activeRoleKey.value = roleKey
  const state = await ensureThread(roleKey, context)
  connect(roleKey)
  return state
}

async function send(roleKey: string, content: string, contextSummary?: string, context?: AssistantContext, optionSlot?: string) {
  const text = (content || '').trim()
  if (!text) return

  const state = await ensureThread(roleKey, context)
  if (!state.threadId) return

  state.sending = true
  state.running = true
  state.waiting = true
  state.streamingText = ''
  state.thinkingText = ''
  state.error = ''

  const localId = `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const optimisticMessage: AssistantMessage = {
    message_id: localId,
    thread_id: state.threadId,
    role: 'user',
    content: text,
    opportunity_id: context?.opportunityId || '',
    quotation_id: context?.quotationId || '',
    created_at: new Date().toISOString(),
  }
  state.messages.push(optimisticMessage)

  try {
    await ensureConnected(roleKey)
    const result = await assistantApi.threads.postMessage(
      state.threadId,
      text,
      contextSummary,
      roleKey,
      context?.opportunityId || null,
      context?.quotationId || null,
      context?.entryPoint,
      optionSlot || null,
    )
    const idx = state.messages.findIndex((message) => message.message_id === localId)
    if (idx >= 0) {
      state.messages.splice(idx, 1, result.user_message as AssistantMessage)
    }
  } catch (error) {
    const idx = state.messages.findIndex((message) => message.message_id === localId)
    if (idx >= 0) state.messages.splice(idx, 1)
    state.waiting = false
    state.running = false
    state.error = '发送失败，请稍后重试'
    throw error
  } finally {
    state.sending = false
  }
}

function close() {
  activeRoleKey.value = null
  disconnect()
}

async function stop() {
  const roleKey = activeRoleKey.value
  if (!roleKey) return
  const state = states[roleKey]
  if (!state?.threadId) return
  try {
    await assistantApi.threads.stop(state.threadId)
  } catch {
    /* ignore */
  }
  state.sending = false
  state.running = false
  state.waiting = false
  state.streamingText = ''
  state.statusText = '已请求暂停'
}

const activeState = computed(() => {
  const roleKey = activeRoleKey.value
  return roleKey ? states[roleKey] || null : null
})

export function useEmployeeChat() {
  return {
    activeRoleKey,
    activeState,
    open,
    close,
    send,
    stop,
    ensureState,
    loadThreads,
    openThread,
    startNewThread,
    softDeleteThread,
  }
}
