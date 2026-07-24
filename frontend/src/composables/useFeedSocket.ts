/**
 * Feed WebSocket client + reactive state.
 *
 * Single source of truth for messages, attachments, online presence, and
 * typing indicators for one opportunity. Loads via REST on connect, then
 * converges via WS broadcasts (deduped by id so optimistic REST results and
 * WS echoes don't double).
 */
import { ref } from 'vue'
import type { Ref } from 'vue'
import { feedApi, getCurrentUser } from '@/api/feed'
import type { FeedMessage, FeedAttachment } from '@/api/feed'

export type PresenceUser = { user_id: string; name: string }

export function useFeedSocket(opportunityId: Ref<string>) {
  const messages = ref<FeedMessage[]>([])
  const attachments = ref<FeedAttachment[]>([])
  const online = ref<PresenceUser[]>([])
  const typingUsers = ref<Record<string, { name: string; until: number }>>({})
  const connected = ref(false)

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let backoff = 1000
  const typingTimers: Record<string, ReturnType<typeof setTimeout>> = {}

  // ── helpers ──
  function upsertMessage(m: FeedMessage) {
    const i = messages.value.findIndex((x) => x.message_id === m.message_id)
    if (i >= 0) messages.value[i] = m
    else messages.value.push(m)
    messages.value.sort((a, b) => (a.created_at < b.created_at ? -1 : 1))
    ;(m.attachments || []).forEach((a) => upsertAttachment(a))
  }
  function upsertAttachment(a: FeedAttachment) {
    const i = attachments.value.findIndex((x) => x.attachment_id === a.attachment_id)
    if (i >= 0) attachments.value[i] = a
    else attachments.value.unshift(a)
  }
  function wsUrl(oppId: string): string {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const u = getCurrentUser()
    const uid = u?.user_id || ''
    return `${proto}://${location.host}/api/feed/ws/${encodeURIComponent(oppId)}?user_id=${encodeURIComponent(uid)}`
  }

  // ── lifecycle ──
  async function load() {
    const [msgs, atts] = await Promise.all([
      feedApi.messages.list(opportunityId.value),
      feedApi.attachments.list(opportunityId.value),
    ])
    messages.value = msgs
    attachments.value = atts
  }

  function connect() {
    if (ws) disconnect()
    ws = new WebSocket(wsUrl(opportunityId.value))
    ws.onopen = () => {
      connected.value = true
      backoff = 1000
    }
    ws.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      switch (data.type) {
        case 'message':
          upsertMessage(data.message)
          break
        case 'attachment':
          upsertAttachment(data.attachment)
          break
        case 'delete_message':
          messages.value = messages.value.filter((m) => m.message_id !== data.message_id)
          break
        case 'delete_attachment':
          attachments.value = attachments.value.filter((a) => a.attachment_id !== data.attachment_id)
          messages.value.forEach((m) => {
            m.attachments = (m.attachments || []).filter((a) => a.attachment_id !== data.attachment_id)
          })
          break
        case 'presence':
          online.value = data.online || []
          break
        case 'typing':
          if (data.user_id) {
            const me = getCurrentUser()?.user_id
            if (data.user_id === me) break // don't show our own typing
            typingUsers.value[data.user_id] = { name: data.name || '某人', until: Date.now() + 3000 }
            clearTimeout(typingTimers[data.user_id])
            typingTimers[data.user_id] = setTimeout(() => {
              delete typingUsers.value[data.user_id]
            }, 3000)
          }
          break
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

  function scheduleReconnect() {
    if (reconnectTimer) return
    backoff = Math.min(backoff * 2, 15000)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, backoff)
  }

  function disconnect() {
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

  function sendTyping() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'typing' }))
    }
  }

  // ── mutations (REST; WS echo updates state) ──
  async function postMessage(body: string, files: File[] = []) {
    const m = await feedApi.messages.create(opportunityId.value, body, files)
    upsertMessage(m) // optimistic; WS dedupes
    return m
  }
  async function postAttachment(file: File) {
    const a = await feedApi.attachments.upload(opportunityId.value, file)
    upsertAttachment(a)
    return a
  }
  async function deleteMessage(id: string) {
    await feedApi.messages.remove(id)
    messages.value = messages.value.filter((m) => m.message_id !== id)
  }
  async function deleteAttachment(id: string) {
    await feedApi.attachments.remove(id)
    attachments.value = attachments.value.filter((a) => a.attachment_id !== id)
  }

  return {
    messages,
    attachments,
    online,
    typingUsers,
    connected,
    load,
    connect,
    disconnect,
    sendTyping,
    postMessage,
    postAttachment,
    deleteMessage,
    deleteAttachment,
  }
}
