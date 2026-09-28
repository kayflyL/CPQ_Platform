/**
 * 全局站内通知 composable — WS 实时 + REST 兜底。
 *
 * 模块级单例：Portal 顶栏 / 商机详情页头等多个挂载点共享同一条 WS 连接
 * 与同一份未读数状态。断线按指数退避重连，重连成功后用 REST 校准未读数。
 */
import { ref } from 'vue'
import { notificationsApi } from '@/api/notifications'
import type { AppNotification } from '@/api/notifications'
import { AUTH_TOKEN_KEY } from '@/api/auth'

const unreadCount = ref(0)
const unreadByType = ref<Record<string, number>>({})
const connected = ref(false)
const latest = ref<AppNotification | null>(null)
const notifications = ref<AppNotification[]>([])
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let backoff = 1000
let started = false

function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem(AUTH_TOKEN_KEY) || ''
  return `${proto}://${location.host}/api/notifications/ws?token=${encodeURIComponent(token)}`
}

async function refreshUnread() {
  try {
    const s = await notificationsApi.unreadStats()
    unreadCount.value = s.count
    unreadByType.value = s.byType
  } catch {
    /* 未登录/后端不可达时静默 */
  }
}

function handleEvent(data: any) {
  if (data?.type === 'unread_count') {
    unreadCount.value = Number(data.count) || 0
    refreshUnread()
    return
  }
  if (data?.type === 'notification' && data.notification) {
    const n = data.notification as AppNotification
    unreadCount.value += 1
    unreadByType.value = { ...unreadByType.value, [n.type]: (unreadByType.value[n.type] || 0) + 1 }
    latest.value = n
    if (notifications.value.length) {
      notifications.value = [n, ...notifications.value.filter((x) => x.notification_id !== n.notification_id)]
    }
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  backoff = Math.min(backoff * 2, 15000)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, backoff)
}

function connect() {
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  try {
    ws = new WebSocket(wsUrl())
  } catch {
    scheduleReconnect()
    return
  }
  ws.onopen = () => {
    connected.value = true
    backoff = 1000
    refreshUnread()
  }
  ws.onmessage = (ev) => {
    try {
      handleEvent(JSON.parse(ev.data))
    } catch {
      /* 非 JSON 帧忽略 */
    }
  }
  ws.onclose = () => {
    connected.value = false
    scheduleReconnect()
  }
  ws.onerror = () => {
    ws?.close()
  }
}

export function useNotifications() {
  function start() {
    if (started) return
    started = true
    connect()
    refreshUnread()
  }

  function stopAll() {
    started = false
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    connected.value = false
  }

  async function loadNotifications(page = 1, unreadOnly = false) {
    const res = await notificationsApi.list(page, 20, unreadOnly)
    if (page === 1) notifications.value = res.notifications
    else notifications.value = [...notifications.value, ...res.notifications]
    return res
  }

  async function markRead(id: string) {
    unreadCount.value = Math.max(0, await notificationsApi.markRead(id))
    const item = notifications.value.find((x) => x.notification_id === id)
    if (item) {
      if (!item.read_at) {
        unreadByType.value = { ...unreadByType.value, [item.type]: Math.max(0, (unreadByType.value[item.type] || 0) - 1) }
      }
      item.read_at = item.read_at || new Date().toISOString()
    }
    refreshUnread()
  }

  async function markAllRead() {
    await notificationsApi.markAllRead()
    unreadCount.value = 0
    unreadByType.value = {}
    notifications.value.forEach((x) => {
      x.read_at = x.read_at || new Date().toISOString()
    })
  }

  async function removeOne(id: string) {
    await notificationsApi.remove(id)
    notifications.value = notifications.value.filter((x) => x.notification_id !== id)
    refreshUnread()
  }

  async function clearRead() {
    const deleted = await notificationsApi.clearRead()
    notifications.value = notifications.value.filter((x) => !x.read_at)
    return deleted
  }

  return {
    unreadCount,
    unreadByType,
    connected,
    latest,
    notifications,
    start,
    stopAll,
    loadNotifications,
    markRead,
    markAllRead,
    removeOne,
    clearRead,
  }
}
