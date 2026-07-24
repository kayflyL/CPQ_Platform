/**
 * useAssistant — 当前助手会话状态 + LLM 流式接收.
 *
 * 全局单例语义(DefaultLayout 持有 Panel,Panel 调用一次):管理 thread 列表 /
 * 当前 thread / 消息 / 发送 / WS 流式(chunk → streamingText,done → 定稿入 messages)。
 */
import { ref, computed, watch } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import { assistantApi, assistantWsUrl, ensureAssistantUser } from '@/api/assistant'
import type { AssistantThread, AssistantMessage } from '@/api/assistant'

export function useAssistant() {
  const threads = ref<AssistantThread[]>([])
  const currentThreadId = ref<string | null>(null)
  const messages = ref<AssistantMessage[]>([])
  const loading = ref(false)
  const sending = ref(false)
  const streamingText = ref('') // 当前正在流式输出的 assistant 文本(临时,done 后清空并入 messages)
  const waitingAI = ref(false) // 已发送、等首个 chunk 到来前的等待态(显示 typing 指示)

  const currentThread = computed(
    () => threads.value.find((t) => t.thread_id === currentThreadId.value) || null,
  )

  // ── WS:订阅当前 thread 的 token 流 ──
  let ws: WebSocket | null = null

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
      if (data.type === 'chunk' && typeof data.delta === 'string') {
        waitingAI.value = false
        streamingText.value += data.delta
      } else if (data.type === 'done') {
        waitingAI.value = false
        if (data.message) messages.value.push(data.message as AssistantMessage)
        streamingText.value = ''
      }
    }
    ws.onclose = () => {
      ws = null
    }
    ws.onerror = () => {
      /* 静默:REST 已返回 user_message,WS 仅推流式回复 */
    }
  }

  function disconnectWs() {
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

  async function loadThreads() {
    try {
      await ensureAssistantUser()
      threads.value = await assistantApi.threads.list()
      if (!currentThreadId.value && threads.value.length) {
        await selectThread(threads.value[0].thread_id)
      }
    } catch {
      /* ignore */
    }
  }

  async function selectThread(id: string) {
    currentThreadId.value = id
    loading.value = true
    try {
      messages.value = await assistantApi.threads.messages(id)
    } finally {
      loading.value = false
    }
  }

  async function newThread(): Promise<AssistantThread | null> {
    try {
      const t = await assistantApi.threads.create()
      threads.value.unshift(t)
      await selectThread(t.thread_id)
      return t
    } catch {
      antMessage.error('新建会话失败')
      return null
    }
  }

  async function send(content: string, contextSummary?: string) {
    const text = content.trim()
    if (!text) return
    if (!currentThreadId.value) {
      const t = await newThread()
      if (!t) return
    }
    sending.value = true
    streamingText.value = ''
    waitingAI.value = true
    try {
      const res = await assistantApi.threads.postMessage(currentThreadId.value!, text, contextSummary)
      messages.value.push(res.user_message)
      if (res.thread) {
        const i = threads.value.findIndex((t) => t.thread_id === res.thread!.thread_id)
        if (i >= 0) threads.value[i] = res.thread
      }
      // assistant 回复由 WS chunk 流式拼接(streamingText)→ done 定稿入 messages
    } catch {
      antMessage.error('发送失败')
    } finally {
      sending.value = false
    }
  }

  async function removeThread(id: string) {
    try {
      await assistantApi.threads.remove(id)
      threads.value = threads.value.filter((t) => t.thread_id !== id)
      if (currentThreadId.value === id) {
        currentThreadId.value = threads.value[0]?.thread_id || null
        if (currentThreadId.value) await selectThread(currentThreadId.value)
        else messages.value = []
      }
    } catch {
      antMessage.error('删除失败')
    }
  }

  return {
    threads, currentThreadId, currentThread, messages, loading, sending,
    streamingText, waitingAI, loadThreads, selectThread, newThread, send, removeThread,
    connectWs, disconnectWs,
  }
}
