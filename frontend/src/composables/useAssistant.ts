/**
 * useAssistant — 方案助手会话门面（ChatSessionRuntime Step 1/2）。
 *
 * 本函数不再持有任何聊天状态：全部会话级状态（消息/流式/瞬态/WS/看门狗）住在
 * chatRuntime 的会话对象里，按渠道键（dm:{role_key} | group | preview）共享——
 * 浮动窗、门户、AI 办公室传同一 productionRuntime，同角色即同一份状态；
 * 工作流画布预览传独立 runtime（preview: true），互不污染。
 *
 * 这里只剩：窗口自己的「激活指针」（activeChannelKey）+ 线程列表 + 实例级 UI 态
 * （pendingDispatch/colleagues/activeRoleKey）。对外 public API 与旧版完全一致，
 * UI 组件零改动。
 */
import { ref, computed, onUnmounted } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import { assistantApi } from '@/api/assistant'
import { resetTaskUI, clearThinking, applyTaskState } from '@/composables/assistantChatWs'
import type { NodeTrace, PauseFacts } from '@/composables/assistantChatWs'
import type { AssistantThread, AssistantMessage } from '@/api/assistant'
import { createChatRuntime, productionRuntime } from '@/composables/chatRuntime'
import type { ChatRuntime, ChatSession, ChatChannelKind, ChatContextUsage } from '@/composables/chatRuntime'

export function useAssistant(defaultEntryPoint: string = 'portal', options: { preview?: boolean; initialRoleKey?: string | null; runtime?: ChatRuntime } = {}) {
  const entryPoint = defaultEntryPoint || 'portal'
  const preview = !!options.preview
  const initialRoleKey = options.initialRoleKey || null
  const runtime = options.runtime || (preview ? createChatRuntime() : productionRuntime)

  // ── 实例级状态：激活指针 + 列表 + 表单态（会话级状态全部在 runtime.session 里）──
  const activeChannelKey = ref<string | null>(null)
  const threads = ref<AssistantThread[]>([])
  const colleagues = ref<any[]>([])
  const activeRoleKey = ref<string | null>(initialRoleKey)
  const pendingDispatch = ref<{ colleague: any; content: string; contextSummary?: string } | null>(null)

  const activeSession = computed<ChatSession | null>(() =>
    activeChannelKey.value ? runtime.get(activeChannelKey.value) : null,
  )

  const currentThreadId = computed<string | null>(() => activeSession.value?.threadId ?? null)
  const currentThread = computed(
    () => threads.value.find((t) => t.thread_id === currentThreadId.value) || null,
  )

  /** 激活一个渠道会话（换指针：旧会话解持有，新会话上持有 → socket 引用计数归一）。
   *  幂等：指针未变且仍在线时不重复 attach；曾被 disconnectWs 冻结则重新 attach。 */
  function activate(kind: ChatChannelKind, roleKey?: string | null): ChatSession {
    const s = runtime.session(kind, roleKey, entryPoint)
    if (activeChannelKey.value !== s.id) {
      const old = activeChannelKey.value ? runtime.get(activeChannelKey.value) : null
      if (old) runtime.unpin(old)
      activeChannelKey.value = s.id
      runtime.attach(s)
    } else if (!runtime.isLive(s)) {
      runtime.attach(s)
    }
    return s
  }

  // 指针解绑：会话级状态不销毁（回合服务端继续跑，回来靠 resync 采纳）
  onUnmounted(() => {
    const s = activeChannelKey.value ? runtime.get(activeChannelKey.value) : null
    if (s) runtime.unpin(s)
  })

  // ── 会话级状态的门面（computed 直读激活会话；内部代码一律写 session 本体）──
  const messages = computed<AssistantMessage[]>({
    get: () => activeSession.value?.messages ?? [],
    set: (v) => { if (activeSession.value) activeSession.value.messages = v },
  })
  const loading = computed(() => !!activeSession.value?.loading)
  const sending = computed(() => !!activeSession.value?.sending)
  const running = computed(() => !!activeSession.value?.running)
  const streamingText = computed<string>({
    get: () => activeSession.value?.streamingText ?? '',
    set: (v) => { if (activeSession.value) activeSession.value.streamingText = v },
  })
  const thinkingText = computed<string>(() => activeSession.value?.thinkingText ?? '')
  const waitingAI = computed(() => !!activeSession.value?.waiting)
  const statusText = computed<string>({
    get: () => activeSession.value?.statusText ?? '',
    set: (v) => { if (activeSession.value) activeSession.value.statusText = v },
  })
  const queuedCount = computed(() => activeSession.value?.queuedCount ?? 0)
  const nodeTraces = computed<NodeTrace[]>(() => activeSession.value?.nodeTraces ?? [])
  const taskTitle = computed(() => activeSession.value?.taskTitle ?? '')
  const taskPhase = computed<'' | 'running' | 'paused' | 'done'>(() => activeSession.value?.taskPhase ?? '')
  const taskPause = computed<PauseFacts | null>(() => activeSession.value?.taskPause ?? null)
  const contextUsage = computed<ChatContextUsage | null>(() => activeSession.value?.contextUsage ?? null)

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

  /** 从线程元数据猜渠道（列表里的会话带 colleague_role_key/thread_kind）。 */
  function channelOfThread(t?: AssistantThread): { kind: ChatChannelKind; roleKey: string | null } {
    const role = String(t?.colleague_role_key || '').trim()
    if (role) return { kind: 'dm', roleKey: role }
    if (t?.thread_kind === 'office_colleague') return { kind: 'dm', roleKey: activeRoleKey.value }
    return { kind: 'group', roleKey: null }
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
      if (!currentStillValid && activeSession.value) {
        runtime.setThread(activeSession.value, null)
      }
      // 面板重开（曾 disconnectWs 冻结）且指针还在旧线程上：这里是无 selectThread 路径的
      // 唯一入口，必须补 attach——否则重开窗口没有 socket，done 全靠看门狗兜底（旧假死路径）
      const cur = activeSession.value
      if (cur?.threadId && !runtime.isLive(cur)) runtime.attach(cur)
      if (!currentThreadId.value && threads.value.length) {
        await selectThread(threads.value[0].thread_id)
      }
    } catch {
      /* ignore */
    }
  }

  /**
   * 打开一条线程。hint 明确渠道（group 面板/历史抽屉传）；不传则按线程元数据推断，
   * 推断不出时维持当前渠道（dm 兜底 activeRoleKey）。
   */
  async function selectThread(id: string, hint?: { kind?: ChatChannelKind; roleKey?: string | null }) {
    let kind = hint?.kind
    let roleKey = hint?.roleKey ?? null
    if (!kind) {
      const meta = channelOfThread(threads.value.find((t) => t.thread_id === id))
      kind = meta.kind
      roleKey = meta.roleKey
      if (kind === 'dm' && !roleKey) roleKey = activeRoleKey.value
    }
    const s = activate(kind, roleKey)
    if (kind === 'dm') activeRoleKey.value = roleKey
    if (s.threadId !== id) runtime.setThread(s, id)
    // 同线程重选也清执行轨迹（与旧版一致）；瞬态等待态只在换线程时清（同线程回合还在跑）
    s.nodeTraces = []
    s.taskPause = null
    s.loading = true
    try {
      const data = await assistantApi.threads.messagesFull(id)
      // 加载途中用户已切走：结果只落回属于这条线程的会话，绝不污染当前激活会话
      if (s.threadId === id) {
        s.messages = data.messages
        s.contextUsage = data.context_usage || null
        // 任务胶囊对账：回合在跑/缺口暂停的线程按服务端事实重建（刷新/切换后恢复）
        if (data.task_state) applyTaskState(s, data.task_state)
      }
    } finally {
      s.loading = false
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
      await selectThread(t.thread_id, preview ? { kind: 'preview' } : { kind: 'dm', roleKey })
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
        const s = activate('preview')
        const oldId = s.threadId
        if (oldId) {
          // Esc 语义：purge 前先中断在途回合（同 destroyPreview）
          if (s.running || s.waiting) {
            try { await runtime.stopTurn(s) } catch { /* ignore */ }
            s.statusText = ''
          }
          try { await assistantApi.threads.purge(oldId) } catch { /* ignore */ }
        }
        runtime.setThread(s, null)
        s.messages = []
        await newThread()
        return
      }
      activate('dm', roleKey)
      const list = await assistantApi.threads.listOffice(roleKey)
      if (list.length) {
        threads.value = list
        await selectThread(list[0].thread_id, { kind: 'dm', roleKey })
        return
      }
      const t = await assistantApi.threads.resolve(roleKey, { entryPoint })
      threads.value = [t]
      await selectThread(t.thread_id, { kind: 'dm', roleKey })
    } catch {
      antMessage.error('切换 AI 角色失败')
    }
  }

  async function postSend(content: string, contextSummary?: string, roleKey?: string, optionSlot?: string | null,
                          cardSelections?: Array<{ slot: string; value: string; label?: string; qty?: number }> | null,
                          entryPointOverride?: string, workflowKey?: string | null) {
    const s = activeSession.value
    if (!s?.threadId) return
    resetTaskUI(s)
    s.sending = true
    s.running = true
    s.streamingText = ''
    clearThinking(s)
    s.waiting = true
    try {
      const res = await assistantApi.threads.postMessage(
        s.threadId,
        content,
        contextSummary,
        roleKey,
        undefined,
        undefined,
        entryPointOverride || entryPoint,
        optionSlot || null,
        cardSelections || null,
        workflowKey || null,
      )
      s.messages.push(res.user_message)
      if (res.thread) {
        const i = threads.value.findIndex((t) => t.thread_id === res.thread!.thread_id)
        if (i >= 0) threads.value[i] = res.thread
      }
      // assistant 回复由 WS chunk 流式拼接(streamingText)→ done 定稿入 messages
    } catch {
      s.waiting = false
      s.streamingText = ''
      s.running = false
      antMessage.error('发送失败')
    } finally {
      s.sending = false
    }
  }

  async function stop() {
    const s = activeSession.value
    if (!s) return
    await runtime.stopTurn(s)
  }

  async function send(content: string, contextSummary?: string, optionSlot?: string | null,
                      cardSelections?: Array<{ slot: string; value: string; label?: string; qty?: number }> | null,
                      workflowKey?: string | null) {
    const text = content.trim()
    if (!text) return
    if (!currentThreadId.value) {
      const t = await newThread()
      if (!t) return
    }
    await postSend(text, contextSummary, activeRoleKey.value || undefined, optionSlot || null,
                   cardSelections || null, undefined, workflowKey || null)
  }

  /** 方案助手「+」显式发起某工作流：直接进入 ACTIVE，不再走 IDLE→PROPOSING。 */
  async function launchWorkflow(workflowKey: string, displayName?: string) {
    const key = (workflowKey || '').trim()
    if (!key) return
    if (!currentThreadId.value) {
      const t = await newThread()
      if (!t) return
    }
    const label = (displayName || key).trim()
    await postSend(`请开始【${label}】工作流。`, undefined, activeRoleKey.value || undefined,
      null, null, 'workflow_launcher', key)
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
        const next = threads.value[0]
        if (next) await selectThread(next.thread_id)
        else if (activeSession.value) {
          runtime.setThread(activeSession.value, null)
          activeSession.value.messages = []
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
    const s = activate('preview')
    const id = s.threadId
    if (id) {
      // Esc 语义：purge 是硬删线程，在途回合先请求服务端中断再删，避免杀掉正在产出的大脑回合
      if (s.running || s.waiting) {
        try { await runtime.stopTurn(s) } catch { /* ignore */ }
        s.statusText = ''
      }
      try { await assistantApi.threads.purge(id) } catch { /* ignore */ }
      runtime.setThread(s, null)
      s.messages = []
    }
  }

  /** 预览会话整体重置（工作流画布「重置测试」）：purge 线程 + 清消息/节点轨迹/状态。 */
  async function resetPreview() {
    if (!preview) return
    await destroyPreview()
    const s = activeSession.value
    if (!s) return
    s.nodeTraces = []
    s.streamingText = ''
    s.thinkingText = ''
    s.statusText = ''
    s.taskPhase = ''
    s.taskPause = null
    s.waiting = false
    s.running = false
    s.taskTitle = ''
  }

  // ── 兼容旧导出：WS 生命周期已由 runtime 按会话管理，这里只做「激活会话」的持有开关 ──
  function connectWs(_threadId?: string | null) {
    const s = activeSession.value
    if (s && !runtime.isLive(s)) runtime.attach(s)
  }
  function disconnectWs() {
    const s = activeChannelKey.value ? runtime.get(activeChannelKey.value) : null
    if (s) runtime.detach(s)
  }

  return {
    threads, currentThreadId, currentThread, messages, loading, sending, running,
    streamingText, thinkingText, waitingAI, statusText, queuedCount, nodeTraces, taskTitle, taskPhase, taskPause,
    contextUsage, loadThreads, selectThread, newThread, send,
    launchWorkflow,
    confirmDispatch, cancelDispatch, removeThread, colleagues, activeRoleKey, switchRole,
    connectWs, disconnectWs, createPreviewThread, destroyPreview, resetPreview, stop,
  }
}
