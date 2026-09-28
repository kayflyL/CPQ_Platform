/**
 * ChatSessionRuntime — 会话级聊天运行时（ChatSessionRuntime 方案 Step 1）。
 *
 * 旧世界的病灶：useAssistant 是「单当前线程 + 一组全局瞬态 ref」，浮动窗/门户/
 * 工作流画布预览各持一份独立实例；办公室侧 useEmployeeChat 又平行实现一套。
 * 结果 = 同一条服务端线程在多个窗口里各有一份互不相通的客户端状态，瞬态
 * （waiting/running/streaming）全局单例，一个回合卡死全体假死。
 *
 * 本模块把「会话」提为一等公民：
 * - 渠道键（dm:{role_key} | group | preview:{entry_point}）→ 唯一会话对象。
 *   服务端约束本就是「每角色一个活跃会话」，客户端渠道与会话一一对应，
 *   同一角色的所有入口（浮动窗/门户/办公室）天然共享同一份会话状态。
 * - 会话对象即 AssistantChatWsState（超集），handleAssistantChatWsEvent /
 *   adoptTurnEnd / clearThinking / createTurnWatchdog 原样按会话工作
 *   （lastEventAt / thinkingBufs 本就按 state 对象 WeakMap 隔离）。
 * - 每会话独立 WS + 独立重连定时器 + 独立看门狗（waiting 才空转检查），
 *   会话被驱逐（LRU 上限 8）或显式 destroy 才关停。
 * - 事件溯源式对账（munder-difflin 思路）：服务端 messages + turn_active 是
 *   事实源，WS 只是增量；断线重连 / 看门狗 / 激活时都用同一 resync 采纳。
 * - 帧信封：后端每帧带 thread_id（assistant_hub 注入），客户端按会话线程校验，
 *   错帧/迟帧直接丢弃，永不写进别的会话。
 *
 * 编排权不在这里：分派/转接/排队仍归后端确定性管道（[[agent-architecture-decision]]）。
 */
import { reactive } from 'vue'
import { assistantApi, assistantWsUrl } from '@/api/assistant'
import { handleAssistantChatWsEvent, adoptTurnEnd, createTurnWatchdog, applyTaskState } from './assistantChatWs'
import type { AssistantChatWsState } from './assistantChatWs'
import type { AssistantMessage, AssistantThread } from '@/api/assistant'

export type ChatChannelKind = 'dm' | 'group' | 'preview'

export interface ChatContextUsage {
  chars: number
  est_tokens: number
  limit_tokens: number
  ratio: number
}

/** 聊天会话 = 渠道元数据 + 聊天状态（AssistantChatWsState 超集，可直接喂给 reducer/看门狗） */
export interface ChatSession extends AssistantChatWsState {
  /** 渠道键：dm:{role_key} | group | preview:{entry_point} */
  id: string
  kind: ChatChannelKind
  roleKey: string | null
  entryPoint: string
  threadId: string | null
  connected: boolean
  loading: boolean
  sending: boolean
  /** 上下文水位（selectThread/resync 刷新） */
  contextUsage: ChatContextUsage | null
  /** 该渠道的会话列表（办公室历史抽屉用；主助手侧列表在 useAssistant 实例级） */
  threads: AssistantThread[]
}

/** 渠道键规则：同渠道即同会话（跨窗口共享状态的根本）。 */
export function chatChannelKey(kind: ChatChannelKind, roleKey?: string | null, entryPoint?: string): string {
  if (kind === 'group') return 'group'
  if (kind === 'preview') return `preview:${entryPoint || 'default'}`
  return `dm:${roleKey || ''}`
}

/** 活跃会话数上限（LRU）：超出时优先驱逐「无指针持有 + 空闲」的最久未用会话。 */
const MAX_LIVE_SESSIONS = 8
const WS_RECONNECT_MS = 2000

function blankSession(id: string, kind: ChatChannelKind, roleKey: string | null, entryPoint: string): ChatSession {
  return reactive({
    id,
    kind,
    roleKey,
    entryPoint,
    threadId: null,
    connected: false,
    loading: false,
    sending: false,
    messages: [],
    streamingText: '',
    thinkingText: '',
    waiting: false,
    statusText: '',
    error: '',
    nodeTraces: [],
    running: false,
    queuedCount: 0,
    taskTitle: '',
    taskPhase: '',
    taskPause: null,
    contextUsage: null,
    threads: [],
  }) as ChatSession
}

export interface ChatRuntime {
  /** 渠道键 → 会话（只读语义；经 session()/find() 访问） */
  readonly sessions: Map<string, ChatSession>
  /** get-or-create 一个渠道会话（带看门狗；触发 LRU 驱逐检查） */
  session(kind: ChatChannelKind, roleKey?: string | null, entryPoint?: string): ChatSession
  /** 仅查找，不创建（activeState 这类 computed 读侧用，避免读时副作用） */
  find(kind: ChatChannelKind, roleKey?: string | null, entryPoint?: string): ChatSession | null
  get(id: string): ChatSession | null
  /** 期望该会话在线（打开/重连 WS；幂等；线程切换后重调即换 socket）。
   *  引用计数：同一会话可被多个窗口激活，最后一个窗口离开才真正关 socket。 */
  attach(s: ChatSession): void
  /** 冻结一个持有者：关 WS、停重连，保留全部状态（回合服务端继续跑，回来靠 resync 采纳） */
  detach(s: ChatSession): void
  /** attach 的别名（指针持有 = 期望在线，同一引用计数：被任一窗口激活的会话不参与 LRU 驱逐） */
  pin(s: ChatSession): void
  unpin(s: ChatSession): void
  /** 引用计数 >0（任一窗口仍持有/在线）？用于门面 activate 的幂等判断 */
  isLive(s: ChatSession): boolean
  /** 服务端事实对账：有未见消息 ∨ turn_active=false ∨ 线程已硬删(404) → true（回合必已结束） */
  resync(s: ChatSession): Promise<boolean>
  /** 请求服务端停止当前回合 + 清瞬态（stop 按钮同口径） */
  stopTurn(s: ChatSession): Promise<void>
  /** 切线程：换 threadId + 清瞬态（上一回合的流式/等待态绝不带进新线程） */
  setThread(s: ChatSession, threadId: string | null): void
  /** 客户端销毁：关 WS + 停看门狗 + 删会话（服务端线程的删除/归档是调用方的事） */
  destroy(id: string): void
}

export function createChatRuntime(): ChatRuntime {
  const sessions = new Map<string, ChatSession>()
  const sockets = new Map<string, WebSocket>()
  /** socket 连的是哪条线程（信封校验 + 换线程识别） */
  const socketThreads = new Map<string, string>()
  const reconnects = new Map<string, ReturnType<typeof setTimeout>>()
  /** 持有计数（attach/pin 同一计数）：>0 = 期望在线；归零 = 关 socket 冻结（状态保留） */
  const liveCounts = new Map<string, number>()
  const lastTouch = new Map<string, number>()
  const watchdogStops = new Map<string, () => void>()

  const liveOf = (id: string) => liveCounts.get(id) || 0

  function touch(s: ChatSession) {
    lastTouch.set(s.id, Date.now())
  }

  function clearReconnect(id: string) {
    const t = reconnects.get(id)
    if (t) {
      clearTimeout(t)
      reconnects.delete(id)
    }
  }

  function closeSocket(id: string) {
    clearReconnect(id)
    const ws = sockets.get(id)
    if (ws) {
      ws.onclose = null
      ws.onmessage = null
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      sockets.delete(id)
    }
    socketThreads.delete(id)
  }

  function openSocket(s: ChatSession) {
    if (liveOf(s.id) <= 0 || !s.threadId) return
    const existing = sockets.get(s.id)
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      if (socketThreads.get(s.id) === s.threadId) return
      closeSocket(s.id) // 渠道没变、线程换了：旧 socket 作废重开
    }
    let ws: WebSocket
    try {
      ws = new WebSocket(assistantWsUrl(s.threadId))
    } catch {
      return
    }
    socketThreads.set(s.id, s.threadId)
    sockets.set(s.id, ws)
    ws.onopen = () => {
      s.connected = true
      // 重连即对账：断线窗口里终态事件已丢，回合可能早已完成落库——立即采纳
      if (s.waiting) {
        void resync(s)
          .then((ended) => {
            if (ended) adoptTurnEnd(s)
          })
          .catch(() => {
            /* 对账失败交给看门狗 */
          })
      }
    }
    ws.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      // FIPA-lite 信封校验：帧上的 thread_id 与本会话线程不符 → 迟帧/错帧，丢弃
      const boundThread = socketThreads.get(s.id)
      if (data && typeof data === 'object' && data.thread_id && boundThread && data.thread_id !== boundThread) return
      handleAssistantChatWsEvent(s, data)
    }
    ws.onclose = () => {
      if (sockets.get(s.id) === ws) sockets.delete(s.id)
      socketThreads.delete(s.id)
      s.connected = false
      if (liveOf(s.id) > 0) {
        clearReconnect(s.id)
        reconnects.set(
          s.id,
          setTimeout(() => {
            reconnects.delete(s.id)
            openSocket(s)
          }, WS_RECONNECT_MS),
        )
      }
    }
    ws.onerror = () => {
      /* 静默：REST 已落用户消息，WS 断了靠重连 + resync 恢复 */
    }
  }

  function detach(s: ChatSession) {
    const n = liveOf(s.id) - 1
    if (n > 0) liveCounts.set(s.id, n)
    else {
      liveCounts.delete(s.id)
      closeSocket(s.id)
      s.connected = false
    }
  }

  /** LRU 驱逐：仅清「无人持有 + 空闲」的会话；没有合格对象就允许暂时超限。 */
  function evictIfNeeded() {
    if (sessions.size <= MAX_LIVE_SESSIONS) return
    const candidates = [...sessions.values()]
      .filter((x) => !x.waiting && !x.running && liveOf(x.id) === 0)
      .sort((a, b) => (lastTouch.get(a.id) || 0) - (lastTouch.get(b.id) || 0))
    if (!candidates.length) return
    destroy(candidates[0].id)
  }

  function destroy(id: string) {
    const s = sessions.get(id)
    if (!s) return
    liveCounts.delete(id)
    closeSocket(id)
    watchdogStops.get(id)?.()
    watchdogStops.delete(id)
    lastTouch.delete(id)
    sessions.delete(id)
  }

  function session(kind: ChatChannelKind, roleKey?: string | null, entryPoint?: string): ChatSession {
    const id = chatChannelKey(kind, roleKey, entryPoint)
    const existing = sessions.get(id)
    if (existing) {
      touch(existing)
      return existing
    }
    const s = blankSession(id, kind, roleKey || null, entryPoint || '')
    sessions.set(id, s)
    // 每会话独立看门狗：waiting 且 45s 无事件才触发 resync（空闲会话零开销）
    watchdogStops.set(
      id,
      createTurnWatchdog(s, () => resync(s)),
    )
    evictIfNeeded()
    touch(s)
    return s
  }

  function find(kind: ChatChannelKind, roleKey?: string | null, entryPoint?: string): ChatSession | null {
    return sessions.get(chatChannelKey(kind, roleKey, entryPoint)) || null
  }

  async function resync(s: ChatSession): Promise<boolean> {
    if (!s.threadId) return false
    let data: Awaited<ReturnType<typeof assistantApi.threads.messagesWithState>>
    try {
      data = await assistantApi.threads.messagesWithState(s.threadId)
    } catch (e: any) {
      // 线程已被硬删（404）：轮询永远失败只会把 waiting 锁死——按终态采纳解锁
      if (e?.response?.status === 404) return true
      throw e
    }
    // 任务胶囊对账（2026-09-13）：服务端有任务态事实（回合在跑/缺口暂停）就重建，
    // 覆盖页面刷新 / WS 重连空窗 / 中途切会话后骨架丢失的全部路径
    if (data.task_state) applyTaskState(s, data.task_state)
    const server: AssistantMessage[] = data.messages || []
    const known = new Set(s.messages.map((m) => m.message_id))
    if (server.some((m) => !known.has(m.message_id))) {
      s.messages = server
      s.contextUsage = data.context_usage || null
      return true
    }
    return data.turn_active === false
  }

  async function stopTurn(s: ChatSession) {
    if (!s.threadId) return
    try {
      await assistantApi.threads.stop(s.threadId)
    } catch {
      /* ignore */
    }
    s.sending = false
    s.running = false
    s.waiting = false
    s.streamingText = ''
    s.statusText = '已请求暂停'
  }

  function setThread(s: ChatSession, threadId: string | null) {
    if (s.threadId === threadId) return
    s.threadId = threadId
    // 瞬态属于「线程上的回合」，线程换了瞬态必须清零（切会话绝不携带上一回合假死态）
    s.streamingText = ''
    s.thinkingText = ''
    s.statusText = ''
    s.queuedCount = 0
    s.nodeTraces = []
    s.taskTitle = ''
    s.taskPhase = ''
    s.taskPause = null
    s.waiting = false
    s.running = false
    s.sending = false
    s.error = ''
    s.contextUsage = null
    if (threadId) openSocket(s)
    else closeSocket(s.id)
  }

  return {
    sessions,
    session,
    find,
    get: (id: string) => sessions.get(id) || null,
    attach: (s: ChatSession) => {
      liveCounts.set(s.id, liveOf(s.id) + 1)
      touch(s)
      openSocket(s)
    },
    detach,
    pin: (s: ChatSession) => {
      liveCounts.set(s.id, liveOf(s.id) + 1)
      touch(s)
      openSocket(s)
    },
    unpin: detach,
    isLive: (s: ChatSession) => liveOf(s.id) > 0,
    resync,
    stopTurn,
    setThread,
    destroy,
  }
}

/** 生产运行时单例：浮动窗 / 门户 / AI 办公室共享一套会话（工作流画布预览用独立运行时）。 */
export const productionRuntime = createChatRuntime()
