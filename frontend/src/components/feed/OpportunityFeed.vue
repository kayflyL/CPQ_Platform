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
        <button class="me-btn" @click="openPicker" :title="me?.name || '点击选择身份'">
          <span class="me-dot" :class="{ on: connected }"></span>
          {{ me?.name || '未选择' }}
        </button>
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
          <div v-if="m.attachments?.length" class="msg-atts">
            <button
              v-for="a in m.attachments"
              :key="a.attachment_id"
              class="att-chip"
              @click="openPreview(a)"
            >
              <component :is="fileIcon(a.original_filename)" />
              <span class="att-name">{{ a.original_filename }}</span>
              <span class="att-size">{{ formatSize(a.file_size) }}</span>
            </button>
          </div>
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

      <div v-if="typingLabel" class="typing">{{ typingLabel }} 正在输入…</div>

      <!-- composer -->
      <div class="composer">
        <div v-if="pendingFiles.length" class="pending-files">
          <span v-for="(f, i) in pendingFiles" :key="i" class="pending-chip">
            {{ f.name }} <a-button type="text" size="small" @click="pendingFiles.splice(i, 1)">×</a-button>
          </span>
        </div>
        <a-textarea
          v-model:value="draft"
          :placeholder="me ? '输入消息，Enter 发送 / Shift+Enter 换行' : '请先选择身份'"
          :disabled="!me"
          :auto-size="{ minRows: 1, maxRows: 4 }"
          @press-enter="onEnter"
          @input="onTyping"
        />
        <div class="composer-actions">
          <a-button :disabled="!me" @click="triggerFilePick" title="附加文件">
            <template #icon><PaperClipOutlined /></template>
          </a-button>
          <a-button type="primary" :loading="sending" :disabled="!me || (!draft.trim() && !pendingFiles.length)" @click="onSend">
            发送
          </a-button>
          <input ref="fileInput" type="file" multiple hidden @change="onFilesPicked" />
        </div>
      </div>
    </div>

    <!-- 附件预览/在线编辑 -->
    <AttachmentPreviewModal
      v-model:open="previewOpen"
      :attachment="previewAttachment"
      @saved="onPreviewSaved"
    />

    <!-- 身份选择 modal -->
    <a-modal v-model:open="showPicker" title="选择你的身份" :footer="null" width="420px" :mask-closable="false">
      <p class="picker-hint">多人协作里你的每条消息/上传都会署名。选已有成员或输入新名字。</p>
      <a-input
        ref="pickerInput"
        v-model:value="pickerName"
        placeholder="输入你的名字"
        @press-enter="confirmPicker"
      />
      <div v-if="users.length" class="picker-suggestions">
        <button v-for="u in users" :key="u.user_id" class="suggestion-chip" @click="chooseExisting(u)">{{ u.name }}</button>
      </div>
      <a-button type="primary" block style="margin-top: 12px" :disabled="!pickerName.trim()" @click="confirmPicker">确定</a-button>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import {
  PaperClipOutlined,
  FileExcelOutlined, FilePdfOutlined, FileImageOutlined, FileOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { feedApi, getCurrentUser, setCurrentUser } from '@/api/feed'
import type { FeedAttachment, FeedMessage, FeedUser } from '@/api/feed'
import { useFeedSocket } from '@/composables/useFeedSocket'
import AttachmentPreviewModal from './AttachmentPreviewModal.vue'

const props = defineProps<{ opportunityId: string; visible: boolean }>()

const opportunityIdRef = computed(() => props.opportunityId)
const feed = useFeedSocket(opportunityIdRef)
const { messages, online, typingUsers, connected } = feed

const loading = ref(false)
const sending = ref(false)
const draft = ref('')
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const messagesEl = ref<HTMLElement | null>(null)

const me = ref<FeedUser | null>(getCurrentUser())
const users = ref<FeedUser[]>([])
const showPicker = ref(false)
const pickerName = ref('')
const pickerInput = ref<any>(null)

// attachment preview / online edit
const previewOpen = ref(false)
const previewAttachment = ref<FeedAttachment | null>(null)

const typingLabel = computed(() => {
  const names = Object.values(typingUsers.value).map((t) => t.name)
  return names.length ? names.join('、') : ''
})

// ── lifecycle: open/close ──
async function activate() {
  if (!props.opportunityId) return
  if (!me.value) {
    await loadUsers()
    showPicker.value = true
    return
  }
  await loadUsers()
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

// ── user picker ──
async function loadUsers() {
  try {
    users.value = await feedApi.users.list()
  } catch {
    /* ignore */
  }
}
function openPicker() {
  pickerName.value = me.value?.name || ''
  showPicker.value = true
  nextTick(() => pickerInput.value?.focus?.())
}
function chooseExisting(u: FeedUser) {
  me.value = u
  setCurrentUser(u)
  showPicker.value = false
  if (props.visible) activate()
}
async function confirmPicker() {
  const name = pickerName.value.trim()
  if (!name) return
  try {
    const u = await feedApi.users.ensure(name)
    me.value = u
    setCurrentUser(u)
    showPicker.value = false
    await activate()
  } catch {
    message.error('保存身份失败')
  }
}

// ── composer ──
function onEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  onSend()
}
let lastTyping = 0
function onTyping() {
  const now = Date.now()
  if (now - lastTyping > 1500) {
    lastTyping = now
    feed.sendTyping()
  }
}
async function onSend() {
  if (!me.value) return
  const body = draft.value.trim()
  const files = [...pendingFiles.value]
  if (!body && !files.length) return
  sending.value = true
  try {
    await feed.postMessage(body, files)
    draft.value = ''
    pendingFiles.value = []
  } catch {
    message.error('发送失败')
  } finally {
    sending.value = false
  }
}

function triggerFilePick() {
  fileInput.value?.click()
}
function onFilesPicked(e: Event) {
  const target = e.target as HTMLInputElement
  appendFiles(Array.from(target.files || []))
  target.value = ''
}
function appendFiles(fs: File[]) {
  pendingFiles.value.push(...fs)
}

async function onDeleteMessage(m: FeedMessage) {
  await feed.deleteMessage(m.message_id)
}

// ── helpers ──
function openPreview(a: FeedAttachment) {
  previewAttachment.value = a
  previewOpen.value = true
}
function onPreviewSaved(_att: FeedAttachment) {
  // 新版本保存后重新加载,让消息内嵌附件反映最新版本
  feed.load()
}
function fileIcon(name: string) {
  const ext = name.toLowerCase().split('.').pop() || ''
  if (['xlsx', 'xls', 'csv'].includes(ext)) return FileExcelOutlined
  if (ext === 'pdf') return FilePdfOutlined
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return FileImageOutlined
  return FileOutlined
}
function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
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
.feed-tabs {
  display: flex;
  gap: 4px;
}
.tab {
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  font-size: 13px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
}
.tab:hover {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary);
}
.tab.active {
  background: var(--cpq-accent-primary);
  color: #fff;
}
.tab-count {
  opacity: 0.8;
  font-weight: 500;
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
.msg-atts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.att-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w8);
  border-radius: 8px;
  padding: 3px 8px;
  font-size: 12px;
  color: var(--cpq-text-primary);
  cursor: pointer;
  max-width: 100%;
}
.msg.mine .att-chip {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
.att-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.att-size {
  opacity: 0.7;
  font-size: 11px;
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
.pending-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pending-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--cpq-overlay-w6);
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 12px;
}
.composer-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

/* files */
.feed-files {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  position: relative;
  border: 2px dashed transparent;
  border-radius: 10px;
}
.feed-files.dragging {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a4);
}
.drop-hint {
  position: absolute;
  inset: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cpq-overlay-a5);
  border-radius: 8px;
  color: var(--cpq-accent-primary);
  font-weight: 600;
  z-index: 5;
  pointer-events: none;
}
.files-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}
.file-card:hover {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a4);
}
.file-card-icon {
  font-size: 20px;
  flex-shrink: 0;
}
.file-card-body {
  flex: 1;
  min-width: 0;
}
.file-card-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-card-meta {
  display: flex;
  gap: 5px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.file-card-actions {
  display: flex;
  gap: 2px;
}
.files-upload-bar {
  padding-top: 10px;
  display: flex;
  justify-content: center;
}

/* picker */
.picker-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin-bottom: 10px;
}
.picker-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}
.suggestion-chip {
  border: 1px solid var(--cpq-overlay-w6);
  background: var(--cpq-overlay-w3);
  border-radius: 14px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--cpq-text-primary);
}
.suggestion-chip:hover {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
}
</style>
