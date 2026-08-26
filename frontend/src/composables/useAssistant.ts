/**
 * useAssistant — 方案助手会话状态 + LLM 流式接收。
 *
 * 管理 thread 列表 / 当前 thread / 消息 / 发送 / WS 流式
 * (chunk → streamingText, done → 定稿入 messages)。
 */
import { ref, computed, watch } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import { assistantApi, assistantWsUrl } from '@/api/assistant'
import { handleAssistantChatWsEvent } from '@/composables/assistantChatWs'
import type { NodeTrace } from '@/composables/assistantChatWs'
import type { AssistantThread, AssistantMessage } from '@/api/assistant'

export function useAssistant(defaultEntryPoint: string = 'portal', options: { preview?: boolean; initialRoleKey?: string | null } = {}) {
  const entryPoint = defaultEntryPoint || 'portal'
  const preview = !!options.preview
  const initialRoleKey = options.initialRoleKey || null
  const threads = ref<AssistantThread[]>([])
  const currentThreadId = ref<string | null>(null)
  const messages = ref<AssistantMessage[]>([])
  const colleagues = ref<any[]>([])
  const activeRoleKey = ref<string | null>(null)
  const loading = ref(false)
  const sending = ref(false)
  const streamingText = ref('') // 当前正在流式输出的 assistant 文本(临时,done 后清空并入 messages)
  const thinkingText = ref('') // 当前需求分析 Agent 的流式思考（白盒展示，发消息/流程开始清空）
  const waitingAI = ref(false) // 已发送、等首个 chunk 到来前的等待态(显示 typing 指示)
  const statusText = ref('') // 流程节点实时状态（机型选型/配件选型等），非聊天台词
  const nodeTraces = ref<NodeTrace[]>([]) // 工作流 Skill 的节点执行卡（仅在触发需求分析等流程时出现）
  const pendingDispatch = ref<{ colleague: any; content: string; contextSummary?: string } | null>(null)

  const currentThread = computed(
    () => threads.value.find((t) => t.thread_id === currentThreadId.value) || null,
  )

  // ── WS:订阅当前 thread 的 token 流 + pipeline 事件 ──
  let ws: WebSocket | null = null
  // WS 意外断开后延迟重连（uvicorn reload / 网络抖动会断 WS，自动恢复收流）
  let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null

  const chatWsState = {
    get messages() { return messages.value },
    get streamingText() { return streamingText.value },
    set streamingText(value: string) { streamingText.value = value },
    get waiting() { return waitingAI.value },
    set waiting(value: boolean) { waitingAI.value = value },
    get statusText() { return statusText.value },
    set statusText(value: string) { statusText.value = value },
    get thinkingText() { return thinkingText.value },
    set thinkingText(value: string) { thinkingText.value = value },
    get error() { return '' },
    set error(_value: string) {},
    get nodeTraces() { return nodeTraces.value },
    set nodeTraces(value: NodeTrace[]) { nodeTraces.value = value },
  }
  function handleWsData(data: any) {
    handleAssistantChatWsEvent(chatWsState, data)
  }

  /** WS 意外断开后延迟重连（防重复定时器；disconnectWs 会清掉） */
  function scheduleWsReconnect() {
    if (wsReconnectTimer || !currentThreadId.value) return
    wsReconnectTimer = setTimeout(() => {
      wsReconnectTimer = null
      connectWs(currentThreadId.value)
    }, 2000)
  }

  function connectWs(threadId: string | null) {
    disconnectWs()
    if (!threadId) return
    try {
      ws = new WebSocket(assistantWsUrl(threadId))
    } catch {
      ws = null
      return
    }
    ws.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      handleWsData(data)
    }
    ws.onclose = () => {
      ws = null
      scheduleWsReconnect()
    }
    ws.onerror = () => {
      /* 静默:REST 已返回 user_message,WS 仅推流式回复 */
    }
  }

  function disconnectWs() {
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer)
      wsReconnectTimer = null
    }
    if (ws) {
      ws.onclose = null
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      ws = null
    }
    streamingText.value = ''
  }

  // 切换 thread → 重连 WS
  watch(currentThreadId, (id) => connectWs(id))

  async function loadColleagues() {
    try {
      const data = await assistantApi.aiColleagues.list()
      colleagues.value = Array.isArray(data.colleagues) ? data.colleagues : []
    } catch {
      colleagues.value = []
    }
  }

  function ensureActiveRole() {
    if (colleagues.value.length) {
      const exists = colleagues.value.some((c) => c?.role_key === activeRoleKey.value)
      if (!activeRoleKey.value || !exists) {
        if (initialRoleKey && colleagues.value.some((c) => c?.role_key === initialRoleKey)) {
          activeRoleKey.value = initialRoleKey
        } else {
          const preferred = colleagues.value.find((c) => c?.role_key === 'assistant')
          activeRoleKey.value = (preferred || colleagues.value[0])?.role_key || null
        }
      }
    } else {
      activeRoleKey.value = null
    }
  }

  async function loadThreads() {
    try {
      await loadColleagues()
      ensureActiveRole()
      if (preview) {
        threads.value = []
        return
      }
      threads.value = activeRoleKey.value
        ? await assistantApi.threads.listOffice(activeRoleKey.value)
        : await assistantApi.threads.list()
      const currentStillValid = threads.value.some(
        (t) => t.thread_id === currentThreadId.value && t.colleague_role_key === activeRoleKey.value,
      )
      if (!currentStillValid) currentThreadId.value = null
      if (!currentThreadId.value && threads.value.length) {
        await selectThread(threads.value[0].thread_id)
      }
    } catch {
      /* ignore */
    }
  }

  async function selectThread(id: string) {
    currentThreadId.value = id
    nodeTraces.value = []
    loading.value = true
    try {
      messages.value = await assistantApi.threads.messages(id)
    } finally {
      loading.value = false
    }
  }

  async function newThread(): Promise<AssistantThread | null> {
    try {
      await loadColleagues()
      ensureActiveRole()
      const roleKey = activeRoleKey.value
      if (!roleKey) return null
      const t = preview
        ? await assistantApi.threads.create({ entryPoint }, '需求分析预览', roleKey, 'office_colleague')
        : await assistantApi.threads.resolve(roleKey, { entryPoint })
      threads.value = [t, ...threads.value.filter((item) => item.thread_id !== t.thread_id)]
      await selectThread(t.thread_id)
      return t
    } catch {
      antMessage.error('新建会话失败')
      return null
    }
  }

  async function switchRole(roleKey: string) {
    activeRoleKey.value = roleKey
    try {
      if (preview) {
        const oldId = currentThreadId.value
        if (oldId) { try { await assistantApi.threads.purge(oldId) } catch { /* ignore */ } }
        currentThreadId.value = null
        messages.value = []
        await newThread()
        return
      }
      const list = await assistantApi.threads.listOffice(roleKey)
      if (list.length) {
        threads.value = list
        await selectThread(list[0].thread_id)
        return
      }
      const t = await assistantApi.threads.resolve(roleKey, { entryPoint })
      threads.value = [t]
      await selectThread(t.thread_id)
    } catch {
      antMessage.error('切换 AI 角色失败')
    }
  }

  async function postSend(content: string, contextSummary?: string, roleKey?: string) {
    sending.value = true
    streamingText.value = ''
    thinkingText.value = ''
    waitingAI.value = true
    try {
      const res = await assistantApi.threads.postMessage(
        currentThreadId.value!,
        content,
        contextSummary,
        roleKey,
        undefined,
        undefined,
        entryPoint,
      )
      messages.value.push(res.user_message)
      if (res.thread) {
        const i = threads.value.findIndex((t) => t.thread_id === res.thread!.thread_id)
        if (i >= 0) threads.value[i] = res.thread
      }
      // assistant 回复由 WS chunk 流式拼接(streamingText)→ done 定稿入 messages
    } catch {
      waitingAI.value = false
      streamingText.value = ''
      antMessage.error('发送失败')
    } finally {
      sending.value = false
    }
  }

  async function send(content: string, contextSummary?: string) {
    const text = content.trim()
    if (!text) return
    if (!currentThreadId.value) {
      const t = await newThread()
      if (!t) return
    }
    await postSend(text, contextSummary, activeRoleKey.value || undefined)
  }

  async function confirmDispatch() {
    const pending = pendingDispatch.value
    if (!pending) return
    pendingDispatch.value = null
    await postSend(pending.content, pending.contextSummary, pending.colleague.role_key)
  }

  async function cancelDispatch() {
    const pending = pendingDispatch.value
    if (!pending) return
    pendingDispatch.value = null
    // “仍由总助处理”：显式锁定总助，避免后端二次分派又把消息转给专业同事
    await postSend(pending.content, pending.contextSummary, 'assistant')
  }

  async function removeThread(id: string) {
    try {
      await assistantApi.threads.remove(id)
      threads.value = threads.value.filter((t) => t.thread_id !== id)
      if (currentThreadId.value === id) {
        currentThreadId.value = threads.value[0]?.thread_id || null
        if (currentThreadId.value) await selectThread(currentThreadId.value)
        else {
          messages.value = []
        }
      }
    } catch {
      antMessage.error('删除失败')
    }
  }

  async function createPreviewThread() {
    if (!currentThreadId.value) {
      await newThread()
    }
    return currentThreadId.value
  }

  async function destroyPreview() {
    if (!preview) return
    const id = currentThreadId.value
    if (id) {
      try { await assistantApi.threads.purge(id) } catch { /* ignore */ }
      currentThreadId.value = null
      messages.value = []
    }
  }

  return {
    threads, currentThreadId, currentThread, messages, loading, sending,
    streamingText, thinkingText, waitingAI, statusText, nodeTraces, pendingDispatch, loadThreads, selectThread, newThread, send,
    confirmDispatch, cancelDispatch, removeThread, colleagues, activeRoleKey, switchRole,
    connectWs, disconnectWs, createPreviewThread, destroyPreview,
  }
}
