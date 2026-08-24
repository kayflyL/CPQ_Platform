<template>
  <div class="opp-feed">
    <!-- header: tabs + presence + who-am-i -->
    <div class="feed-header">
      <div class="feed-title">协作动态</div>
      <div class="presence">
        <span
          v-for="u in online"
          :key="u.user_id"
          class="avatar"
          :title="`${u.name} 在线`"
          :style="{ background: avatarColor(u.name) }"
        >{{ initial(u.name) }}</span>
        <div class="me-btn" :title="me?.name || ''">
          <span class="me-dot" :class="{ on: connected }"></span>
          {{ me?.name || '未登录' }}
        </div>
      </div>
    </div>

    <!-- 动态 timeline -->
    <div class="feed-timeline">
      <a-spin v-if="loading" size="small" class="spin-center" />
      <div v-else class="messages" ref="messagesEl">
        <a-empty v-if="!messages.length" description="还没有消息，发一条吧" :image-style="{ height: '48px' }" />
        <div
          v-for="m in messages"
          :key="m.message_id"
          class="msg"
          :class="{ mine: m.author_user_id === me?.user_id }"
        >
          <div class="msg-head">
            <span class="author">{{ m.author_name }}</span>
            <span class="time">{{ formatTime(m.created_at) }}</span>
          </div>
          <div v-if="m.body" class="msg-body">{{ m.body }}</div>
          <a-button
            v-if="m.author_user_id === me?.user_id"
            class="msg-del"
            type="text"
            size="small"
            danger
            @click="onDeleteMessage(m)"
          >删除</a-button>
        </div>
      </div>

      <div class="feed-hint">评论已合并到各审批节点下方，请在对应节点中回复。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import type { FeedMessage, FeedUser } from '@/api/feed'
import { useFeedSocket } from '@/composables/useFeedSocket'
import { useAuthStore } from '@/store/auth'

const props = defineProps<{ opportunityId: string; visible: boolean }>()

const opportunityIdRef = computed(() => props.opportunityId)
const feed = useFeedSocket(opportunityIdRef)
const { messages, online, connected } = feed

const loading = ref(false)
const messagesEl = ref<HTMLElement | null>(null)

const auth = useAuthStore()
/** 当前身份 = 登录用户（后端按 JWT 记录归属；这里仅用于本地展示/判定 mine） */
const me = computed<FeedUser | null>(() =>
  auth.user
    ? {
        user_id: auth.user.user_id,
        name: auth.user.name,
        email: auth.user.email || '',
        role: auth.user.role,
        created_at: auth.user.created_at,
      }
    : null,
)

// ── lifecycle: open/close ──
async function activate() {
  if (!props.opportunityId) return
  loading.value = true
  try {
    await feed.load()
  } finally {
    loading.value = false
  }
  feed.connect()
  await nextTick(scrollToBottom)
}

watch(
  () => props.visible,
  async (v) => {
    if (v) await activate()
    else feed.disconnect()
  },
  { immediate: true },
)
watch(
  () => props.opportunityId,
  async (id) => {
    if (id && props.visible) await activate()
  },
)
onBeforeUnmount(() => feed.disconnect())

// keep pinned to bottom when new messages arrive
watch(
  () => messages.value.length,
  async () => {
    await nextTick(scrollToBottom)
  },
)
function scrollToBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

async function onDeleteMessage(m: FeedMessage) {
  await feed.deleteMessage(m.message_id)
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
const AVATAR_COLORS = ['#5b8ff9', '#5ad8a6', '#f6bd16', '#e86452', '#6dc8ec', '#945fb9', '#ff9845']
function avatarColor(name: string) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h)
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
}
function initial(name: string) {
  return (name || '?').trim().charAt(0).toUpperCase()
}
</script>

<style scoped>
.opp-feed {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: transparent;
}

/* header */
.feed-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  gap: 8px;
}
.presence {
  display: flex;
  align-items: center;
  gap: 4px;
}
.avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  border: 2px solid var(--cpq-glass-border);
  margin-left: -6px;
}
.me-btn {
  border: 1px solid var(--cpq-overlay-w6);
  background: var(--cpq-overlay-w3);
  border-radius: 14px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--cpq-text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
}
.me-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
}
.me-dot.on {
  background: var(--cpq-accent-success);
}

/* timeline */
.feed-hint {
  padding: 10px 14px;
  border-top: 1px solid var(--cpq-overlay-w6);
  color: var(--cpq-text-muted);
  font-size: 12px;
  text-align: center;
}

.feed-timeline {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.spin-center {
  align-self: center;
  margin-top: 24px;
}
.msg {
  background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 12px;
  padding: 8px 12px;
  max-width: 88%;
  align-self: flex-start;
  position: relative;
}
.msg.mine {
  align-self: flex-end;
  background: var(--cpq-accent-primary);
  border-color: transparent;
}
.msg.mine .author,
.msg.mine .time,
.msg.mine .msg-body {
  color: #fff;
}
.msg-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 2px;
}
.author {
  font-size: 12px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}
.time {
  font-size: 10px;
  color: var(--cpq-text-muted);
}
.msg-body {
  font-size: 13px;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-del {
  position: absolute;
  top: 4px;
  right: 4px;
  opacity: 0;
  transition: opacity var(--cpq-transition-fast);
}
.msg:hover .msg-del {
  opacity: 0.8;
}
.typing {
  padding: 0 14px 6px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-style: italic;
}

/* composer */
.composer {
  border-top: 1px solid var(--cpq-overlay-w6);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--cpq-overlay-w3);
}
.composer-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
</style>
