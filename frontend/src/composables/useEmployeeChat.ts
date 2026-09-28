/**
 * useEmployeeChat — AI 办公室同事聊天门面（ChatSessionRuntime Step 4）。
 *
 * 旧版在这里平行实现了第二套聊天状态机（states[roleKey] + 全局单 socket +
 * 独立看门狗/重连/对账），与 useAssistant 各养各的。现在全部收敛到
 * chatRuntime 的 dm:{role_key} 会话：与浮动窗/门户共享同一份会话状态
 * （服务端本就是「每角色一个活跃会话」，所有入口同一条线程），本文件只剩
 * 办公室面板的角色指针与 ensureThread/startNewThread 等业务动作。
 *
 * 对外 public API 与旧版完全一致（OfficeColleagueChatPanel 零改动）。
 */
import { computed, ref } from 'vue'
import { assistantApi } from '@/api/assistant'
import type { AssistantContext, AssistantThread } from '@/api/assistant'
import { resetTaskUI, clearThinking, applyTaskState } from '@/composables/assistantChatWs'
import { productionRuntime } from '@/composables/chatRuntime'
import type { ChatSession } from '@/composables/chatRuntime'

/** 兼容旧导出：办公室聊天状态 = 运行时会话对象（AssistantChatWsState 超集）。 */
export type EmployeeChatState = ChatSession

const runtime = productionRuntime
const activeRoleKey = ref<string | null>(null)

/** 换角色指针时解持旧会话（办公室面板一次只盯一个角色，别给旧角色留空 socket）。 */
function adoptRole(roleKey: string): ChatSession {
  if (activeRoleKey.value && activeRoleKey.value !== roleKey) {
    const old = runtime.find('dm', activeRoleKey.value)
    if (old) runtime.detach(old)
  }
  activeRoleKey.value = roleKey
  const s = runtime.session('dm', roleKey)
  if (!runtime.isLive(s)) runtime.attach(s)
  return s
}

/** get-or-create 角色会话（不动指针/不连 WS——旧版 ensureState 语义）。 */
function ensureState(roleKey: string): ChatSession {
  return runtime.session('dm', roleKey)
}

async function ensureThread(roleKey: string, context?: AssistantContext): Promise<ChatSession> {
  const s = ensureState(roleKey)
  if (s.threadId) return s

  s.loading = true
  s.error = ''
  try {
    const thread = await assistantApi.threads.resolve(roleKey, context)
    s.threadId = thread.thread_id
    const st = await assistantApi.threads.messagesWithState(thread.thread_id, 50)
    s.messages = st.messages
    // 任务胶囊对账：回合在跑/缺口暂停的线程按服务端事实重建
    if (st.task_state) applyTaskState(s, st.task_state)
    if (!runtime.isLive(s)) runtime.attach(s)
    return s
  } catch (error) {
    s.error = '无法创建与该同事的会话'
    throw error
  } finally {
    s.loading = false
  }
}

async function loadThreads(
  roleKey: string,
  options?: { includePreview?: boolean },
): Promise<AssistantThread[]> {
  const s = ensureState(roleKey)
  s.error = ''
  s.threads = await assistantApi.threads.listOffice(roleKey, options)
  return s.threads
}

async function openThread(roleKey: string, threadId: string) {
  if (!roleKey || !threadId) return
  const s = adoptRole(roleKey)
  s.loading = true
  s.error = ''
  try {
    // 换线程即换回合：瞬态清零（streaming/waiting 等），消息重拉
    if (s.threadId !== threadId) runtime.setThread(s, threadId)
    s.nodeTraces = []
    s.taskPause = null
    const st = await assistantApi.threads.messagesWithState(threadId, 50)
    s.messages = st.messages
    // 任务胶囊对账：回合在跑/缺口暂停的线程按服务端事实重建
    if (st.task_state) applyTaskState(s, st.task_state)
  } finally {
    s.loading = false
  }
  return s
}

async function startNewThread(roleKey: string, context?: AssistantContext) {
  if (!roleKey) return
  const s = adoptRole(roleKey)
  // 先归档当前线程再 resolve（resolve 是 get-or-create，不归档会拿回同一条，新对话等于没点）
  if (s.threadId) {
    try {
      await assistantApi.threads.remove(s.threadId)
    } catch {
      /* ignore */
    }
  }
  runtime.setThread(s, null)
  s.messages = []
  s.threads = []
  s.loading = true
  try {
    const thread = await assistantApi.threads.resolve(roleKey, context)
    runtime.setThread(s, thread.thread_id)
    s.messages = []
    return s
  } catch (error) {
    s.error = '无法创建新会话'
    throw error
  } finally {
    s.loading = false
  }
}

async function softDeleteThread(roleKey: string, threadId: string) {
  await assistantApi.threads.remove(threadId)
  const s = ensureState(roleKey)
  if (s.threadId === threadId) {
    runtime.setThread(s, null)
    s.messages = []
  }
}

async function open(colleague: any, context?: AssistantContext) {
  const roleKey = String(colleague?.role_key || '')
  if (!roleKey) return

  adoptRole(roleKey)
  const s = await ensureThread(roleKey, context)
  return s
}

async function send(roleKey: string, content: string, contextSummary?: string, context?: AssistantContext,
                    optionSlot?: string, cardSelections?: Array<{ slot: string; value: string; label?: string; qty?: number }> | null) {
  const text = (content || '').trim()
  if (!text) return

  const s = await ensureThread(roleKey, context)
  if (!s.threadId) return

  resetTaskUI(s)
  s.sending = true
  s.running = true
  s.waiting = true
  s.streamingText = ''
  clearThinking(s)
  s.error = ''

  const localId = `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const optimisticMessage: import('@/api/assistant').AssistantMessage = {
    message_id: localId,
    thread_id: s.threadId,
    role: 'user',
    content: text,
    opportunity_id: context?.opportunityId || '',
    quotation_id: context?.quotationId || '',
    created_at: new Date().toISOString(),
  }
  s.messages.push(optimisticMessage)

  try {
    if (!runtime.isLive(s)) runtime.attach(s)
    const result = await assistantApi.threads.postMessage(
      s.threadId,
      text,
      contextSummary,
      roleKey,
      context?.opportunityId || null,
      context?.quotationId || null,
      context?.entryPoint,
      optionSlot || null,
      cardSelections || null,
    )
    const idx = s.messages.findIndex((message) => message.message_id === localId)
    if (idx >= 0) {
      s.messages.splice(idx, 1, result.user_message as import('@/api/assistant').AssistantMessage)
    }
  } catch (error) {
    const idx = s.messages.findIndex((message) => message.message_id === localId)
    if (idx >= 0) s.messages.splice(idx, 1)
    s.waiting = false
    s.running = false
    s.error = '发送失败，请稍后重试'
    throw error
  } finally {
    s.sending = false
  }
}

function close() {
  const s = activeRoleKey.value ? runtime.find('dm', activeRoleKey.value) : null
  if (s) runtime.detach(s)
  activeRoleKey.value = null
}

async function stop() {
  const s = activeRoleKey.value ? runtime.find('dm', activeRoleKey.value) : null
  if (!s?.threadId) return
  await runtime.stopTurn(s)
}

const activeState = computed<ChatSession | null>(() => {
  return activeRoleKey.value ? runtime.find('dm', activeRoleKey.value) : null
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
