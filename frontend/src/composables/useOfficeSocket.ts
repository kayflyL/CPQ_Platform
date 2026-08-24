/**
 * useOfficeSocket — authenticated global AI office status stream.
 *
 * Connection lifecycle:
 * - exponential backoff with jitter on drop
 * - heartbeat ping/pong with stale-connection recovery
 * - revision-aware status merges plus REST snapshot reconciliation
 */
import { onBeforeUnmount, ref } from 'vue'
import { officeApi, officeWsUrl, type OfficeColleagueStatus } from '@/api/office'

export type OfficeStatusMap = Record<string, OfficeColleagueStatus>

const RECONCILE_INTERVAL_MS = 15000

export function useOfficeSocket() {
  const statusMap = ref<OfficeStatusMap>({})
  const connected = ref(false)

  const revisionByRole = new Map<string, number>()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let reconcileTimer: ReturnType<typeof setInterval> | null = null
  let reconnectDelay = 1000
  let stopped = false
  let lastPongAt = 0

  function currentRevision(roleKey: string): number {
    const inlineRevision = Number(statusMap.value[roleKey]?.revision ?? 0)
    return Math.max(inlineRevision, revisionByRole.get(roleKey) ?? 0)
  }

  function applyStatus(roleKey: string, status: OfficeColleagueStatus) {
    const nextRevision = Number(status.revision ?? 0)
    const previousRevision = currentRevision(roleKey)

    if (nextRevision < previousRevision) return
    if (nextRevision > previousRevision + 1) {
      void loadSnapshotFallback()
    }

    statusMap.value = { ...statusMap.value, [roleKey]: status }
    revisionByRole.set(roleKey, nextRevision)
  }

  function applySnapshot(snapshot: Record<string, OfficeColleagueStatus>) {
    if (!snapshot) return
    const nextMap = { ...statusMap.value }

    for (const [roleKey, status] of Object.entries(snapshot)) {
      const nextRevision = Number(status?.revision ?? 0)
      const previousRevision = currentRevision(roleKey)
      if (nextRevision < previousRevision) continue
      nextMap[roleKey] = status
      revisionByRole.set(roleKey, nextRevision)
    }

    statusMap.value = nextMap
  }

  async function loadSnapshotFallback() {
    try {
      const data = await officeApi.snapshot()
      applySnapshot(data.snapshot)
    } catch {
      /* keep the last known snapshot */
    }
  }

  function isVisible() {
    return document.visibilityState === 'visible'
  }

  function startReconciliation() {
    if (reconcileTimer) return
    reconcileTimer = setInterval(() => {
      if (!isVisible()) return
      void loadSnapshotFallback()
    }, RECONCILE_INTERVAL_MS)
  }

  function stopReconciliation() {
    if (reconcileTimer) {
      clearInterval(reconcileTimer)
      reconcileTimer = null
    }
  }

  function handleVisibilityChange() {
    if (isVisible()) void loadSnapshotFallback()
  }

  function handleWindowFocus() {
    if (isVisible()) void loadSnapshotFallback()
  }

  function connect() {
    disconnect()
    stopped = false
    window.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('focus', handleWindowFocus)
    startReconciliation()
    void loadSnapshotFallback()

    try {
      ws = new WebSocket(officeWsUrl())
    } catch {
      ws = null
      connected.value = false
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      connected.value = true
      reconnectDelay = 1000
      lastPongAt = Date.now()
      if (!heartbeatTimer) {
        heartbeatTimer = setInterval(() => {
          if (!ws || ws.readyState !== WebSocket.OPEN) return
          ws.send('{"type":"ping"}')
          if (Date.now() - lastPongAt > 70000) {
            ws.close()
          }
        }, 25000)
      }
    }

    ws.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }

      if (data.type === 'pong') {
        lastPongAt = Date.now()
        return
      }

      if (data.type === 'snapshot') {
        applySnapshot(data.snapshot || {})
        return
      }

      if (data.type === 'colleague_status') {
        applyStatus(data.role_key, data as OfficeColleagueStatus)
      }
    }

    ws.onclose = () => {
      ws = null
      connected.value = false
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer)
        heartbeatTimer = null
      }
      if (!stopped) {
        scheduleReconnect()
        void loadSnapshotFallback()
      }
    }

    ws.onerror = () => {
      /* REST snapshot fallback keeps the UI alive; reconnect happens on close. */
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer || stopped) return
    const jitter = 0.8 + Math.random() * 0.4
    const delay = Math.min(15000, Math.max(1000, Math.round(reconnectDelay * jitter)))
    reconnectDelay = Math.min(15000, reconnectDelay * 2)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function disconnect() {
    stopped = true
    stopReconciliation()
    window.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('focus', handleWindowFocus)
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    reconnectDelay = 1000
    if (ws) {
      ws.onclose = null
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      ws = null
    }
    connected.value = false
  }

  onBeforeUnmount(disconnect)

  return { statusMap, connected, connect, disconnect }
}
