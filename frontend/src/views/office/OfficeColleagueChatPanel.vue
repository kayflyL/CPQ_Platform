<template>
  <section class="colleague-chat" :class="{ expanded }">
    <div class="chat-head" @click="toggleExpanded">
      <div class="chat-head-label">
        <span class="chat-head-dot" :class="{ online: chatState?.connected }"></span>
        <span>{{ expanded ? '对话' : '和 TA 对话' }}</span>
      </div>
      <div class="chat-head-actions" @click.stop>
        <button class="chat-icon-btn" type="button" title="会话历史" @click="openHistory">
          <HistoryOutlined />
        </button>
        <button v-if="expanded" class="chat-icon-btn chat-close" type="button" title="收起对话" @click="toggleExpanded">
          <CloseOutlined />
        </button>
      </div>
    </div>

    <template v-if="expanded">
      <div v-if="chatState?.nodeTraces?.length" class="oc-plan-bar">
        <span v-for="t in chatState.nodeTraces" :key="t.step" class="oc-plan-step" :class="`oc-plan-step--${t.status}`">
          <span class="oc-plan-dot" />
          <span>{{ t.label }}</span>
        </span>
        <span v-if="chatState?.waiting" class="oc-plan-waiting">等待补充信息…</span>
      </div>
      <div ref="messagesEl" class="chat-messages">
        <div v-if="chatState?.loading" class="chat-empty">正在建立会话…</div>
        <div
          v-else-if="!chatState?.messages.length && !chatState?.streamingText && !chatState?.waiting"
          class="chat-empty"
        >
          和 {{ colleague.name || colleague.role_key }} 聊聊
        </div>

        <template v-for="item in chatState?.messages || []" :key="item.message_id">
          <div v-if="item.kind === 'business_artifact'" class="oc-result">
            <AssistantMessageItem :message="item" :author="colleagueAuthor" />
            <BusinessArtifactView
              v-if="artifactFor(item)"
              :entity-type="artifactFor(item)!.entityType"
              :entity="artifactFor(item)!.entity"
              :thread-id="chatState?.threadId"
            />
          </div>
          <AssistantMessageItem
            v-else
            :message="item"
            :author="colleagueAuthor"
            @select-option="sendOption"
          />
        </template>

        <AssistantMessageItem
          v-if="chatState?.streamingText || chatState?.waiting"
          :message="{ role: 'assistant', content: chatState?.streamingText || '' }"
          :author="colleagueAuthor"
          :streaming="!!chatState?.streamingText"
          :typing="!chatState?.streamingText && !officeThinkingActive"
          :status-text="chatState?.statusText"
          :thinking="chatState?.thinkingText"
          :thinking-active="officeThinkingActive"
        />
        <div v-if="chatState?.error" class="chat-error">{{ chatState.error }}</div>
      </div>

      <AssistantComposer
        v-model="draft"
        placeholder="直接告诉 TA 你想做什么…"
        :disabled="chatState?.loading"
        :sending="chatState?.sending"
        :running="chatState?.running"
        @send="onSend"
        @stop="onStop"
      />

      <transition name="chat-drawer">
        <div v-if="historyOpen" class="chat-history-drawer" @mousedown.stop>
          <div class="chat-history-mask" @click="historyOpen = false"></div>
          <aside class="chat-history-panel">
            <div class="chat-history-head">
              <div class="chat-history-title">会话历史</div>
              <button class="chat-new-thread" type="button" :disabled="historyLoading" @click="newConversation">
                <PlusOutlined />
                新对话
              </button>
            </div>
            <div class="chat-history-list">
              <div v-if="historyLoading" class="chat-history-empty">正在加载会话…</div>
              <div v-else-if="!historyThreads.length" class="chat-history-empty">暂无会话</div>
              <div
                v-for="thread in historyThreads"
                :key="thread.thread_id"
                class="chat-history-row"
                :class="{ active: thread.thread_id === chatState?.threadId }"
              >
                <button class="chat-history-main" type="button" @click="selectThread(thread)">
                  <span class="chat-history-title">
                    {{ thread.title || thread.first_message || thread.last_message || '未命名会话' }}
                  </span>
                  <span class="chat-history-meta">
                    {{ thread.msg_count || 0 }} 条 · {{ formatTime(thread.updated_at) }}
                  </span>
                </button>
                <a-popconfirm
                  title="删除该会话？"
                  :z-index="1800"
                  @confirm="toggleDelete(thread)"
                >
                  <button class="chat-thread-del" type="button" aria-label="删除会话">
                    <DeleteOutlined />
                  </button>
                </a-popconfirm>
              </div>
            </div>
          </aside>
        </div>
      </transition>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { CloseOutlined, DeleteOutlined, HistoryOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { AssistantContext, AssistantThread } from '@/api/assistant'
import AssistantComposer from '@/components/assistant/AssistantComposer.vue'
import AssistantMessageItem from '@/components/assistant/AssistantMessageItem.vue'
import BusinessArtifactView from '@/components/assistant/BusinessArtifactView.vue'
import { useEmployeeChat } from '@/composables/useEmployeeChat'

const props = defineProps<{
  colleague: any
  context?: AssistantContext
  contextSummary?: string
}>()

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const expanded = ref(false)
const historyOpen = ref(false)
const historyLoading = ref(false)
const historyThreads = ref<AssistantThread[]>([])
const chatContext = computed<AssistantContext>(() => ({
  ...(props.context || {}),
  entryPoint: props.context?.entryPoint || 'ai_office',
}))
const {
  activeState,
  open,
  close,
  send,
  stop,
  openThread,
  startNewThread,
  loadThreads,
  softDeleteThread,
} = useEmployeeChat()

const chatState = computed(() => activeState.value)
const officeThinkingActive = computed(() => !!chatState.value?.waiting && (!!chatState.value?.thinkingText || !chatState.value?.streamingText))
const colleagueAuthor = computed(() => ({
  name: props.colleague?.name || props.colleague?.role_key || 'AI 同事',
  avatar_url: props.colleague?.avatar_url || '',
  color: props.colleague?.color || '#1677ff',
}))

function artifactFor(message: { kind?: string; data?: string }): { entityType: string; entity: any } | null {
  if (message.kind !== 'business_artifact' || !message.data) return null
  try {
    const d = JSON.parse(message.data)
    const entity = d?.entity || d?.bom_scheme
    if (!entity || !d?.entity_type) return null
    return { entityType: String(d.entity_type), entity }
  } catch {
    return null
  }
}

function formatTime(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  if (d.toDateString() === yesterday.toDateString()) return '昨天'
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

async function openHistory() {
  if (!props.colleague?.role_key) return
  if (!expanded.value) {
    expanded.value = true
    await open(props.colleague, chatContext.value)
  }
  historyOpen.value = true
  historyLoading.value = true
  try {
    historyThreads.value = await loadThreads(props.colleague.role_key, {
      includePreview: true,
    })
  } catch {
    message.error('会话历史加载失败')
  } finally {
    historyLoading.value = false
  }
}

async function selectThread(thread: AssistantThread) {
  if (!props.colleague?.role_key) return
  historyOpen.value = false
  expanded.value = true
  await openThread(props.colleague.role_key, thread.thread_id)
  await scrollToBottom()
}

async function newConversation() {
  if (!props.colleague?.role_key) return
  await startNewThread(props.colleague.role_key, chatContext.value)
  historyOpen.value = false
  expanded.value = true
  await scrollToBottom()
}

async function toggleDelete(thread: AssistantThread) {
  if (!props.colleague?.role_key) return
  try {
    await softDeleteThread(props.colleague.role_key, thread.thread_id)
    message.success('会话已移入回收站')
    await openHistory()
  } catch {
    message.error('操作失败，请稍后重试')
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

async function toggleExpanded() {
  if (!expanded.value) {
    expanded.value = true
    historyOpen.value = false
    if (props.colleague?.role_key) {
      await open(props.colleague, chatContext.value)
      await scrollToBottom()
    }
  } else {
    expanded.value = false
    historyOpen.value = false
    close()
  }
}

watch(
  () => props.colleague?.role_key,
  () => {
    expanded.value = false
    historyOpen.value = false
    close()
  },
)

watch(
  () => [chatState.value?.messages.length, chatState.value?.streamingText, chatState.value?.waiting],
  () => scrollToBottom(),
)

async function onSend() {
  const text = draft.value.trim()
  if (!text || !props.colleague?.role_key) return
  try {
    await send(props.colleague.role_key, text, props.contextSummary, chatContext.value)
    draft.value = ''
  } catch {
    message.error(chatState.value?.error || '发送失败')
  }
}

async function onStop() {
  await stop()
}

async function sendOption(value: string) {
  if (!value || !props.colleague?.role_key) return
  try {
    await send(props.colleague.role_key, value, props.contextSummary, chatContext.value)
  } catch {
    message.error(chatState.value?.error || '发送失败')
  }
}

onBeforeUnmount(close)
</script>

<style scoped>
.colleague-chat {
  align-self: flex-start;
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  height: auto;
  border: 1px solid var(--cpq-glass-border, var(--cpq-border-secondary, rgba(255, 255, 255, 0.14)));
  border-radius: 16px;
  background: var(--cpq-glass-card-bg, var(--cpq-bg-card, rgba(255, 255, 255, 0.04)));
  box-shadow: var(--cpq-glass-card-shadow, none);
  backdrop-filter: blur(var(--cpq-glass-blur-2, 14px));
  overflow: hidden;
}

.colleague-chat.expanded {
  align-self: stretch;
  flex: 1;
  height: auto;
  min-height: 260px;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding: 12px 14px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255, 255, 255, 0.1));
  cursor: pointer;
}

.chat-head-copy {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--cpq-text-primary, #f5f7fa);
  font-size: 13px;
  font-weight: 700;
}

.chat-head-role {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--cpq-text-muted, #9aa4b2);
  font-size: 12px;
  font-weight: 500;
}

.chat-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.chat-head-state {
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--cpq-text-muted, #9aa4b2);
  background: var(--cpq-overlay-w6, rgba(154, 164, 178, 0.12));
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.chat-head-state.online {
  color: #37d399;
  background: rgba(55, 211, 153, 0.12);
}

.chat-head-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255, 255, 255, 0.08));
}

.chat-head-tool {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--cpq-border-light, rgba(255, 255, 255, 0.16));
  border-radius: 999px;
  color: var(--cpq-text-secondary, #c3cad5);
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.06));
  font-size: 11px;
  cursor: pointer;
}

.chat-head-tool:hover {
  border-color: var(--cpq-glass-border-strong, rgba(22, 119, 255, 0.45));
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.12));
}

.chat-collapse-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--cpq-text-muted, #9aa4b2);
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}

.chat-collapse-icon:hover {
  border-color: var(--cpq-border-secondary, rgba(255, 255, 255, 0.12));
  color: var(--cpq-text-primary, #f5f7fa);
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.06));
}

.chat-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-empty,
.chat-tool-activity { display: flex; flex-direction: column; gap: 6px; padding: 6px 2px; }
.chat-tool { display: flex; align-items: center; gap: 6px; padding: 7px 9px; border-radius: 8px; font-size: 12px; color: var(--cpq-text-secondary); background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w8); }
.chat-tool .anticon { color: var(--cpq-accent-primary); }
.chat-tool.done .anticon { color: var(--cpq-accent-success, #52c41a); }
.chat-tool-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-tool-status { flex-shrink: 0; font-size: 11px; color: var(--cpq-text-muted); }
.chat-workflow-steps { display: flex; flex-direction: column; gap: 6px; padding: 6px 2px; }
.chat-workflow-step { display: flex; align-items: center; gap: 6px; padding: 7px 9px; border-radius: 8px; font-size: 12px; color: var(--cpq-text-secondary); background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w8); }
.chat-workflow-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--cpq-text-muted); flex-shrink: 0; }
.chat-workflow-step.is-running .chat-workflow-dot { background: var(--cpq-accent-primary); box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.15); }
.chat-workflow-step.is-done .chat-workflow-dot { background: var(--cpq-accent-success, #52c41a); }
.chat-workflow-step.is-error .chat-workflow-dot { background: #ff4d4f; }
.chat-workflow-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-workflow-status { flex-shrink: 0; font-size: 11px; color: var(--cpq-text-muted); }
.oc-result { display: flex; flex-direction: column; gap: 8px; }
.oc-plans { display: flex; flex-direction: column; gap: 8px; padding-left: 38px; }
.oc-bom-summary { margin-bottom: 10px; color: var(--cpq-text-secondary); font-size: 13px; }
.chat-error {
  margin: auto;
  color: var(--cpq-text-muted, #9aa4b2);
  font-size: 12px;
  line-height: 1.6;
  text-align: center;
}

.chat-error {
  color: #ff8f8f;
}

.chat-history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow-y: auto;
}

.chat-history-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--cpq-border-secondary, rgba(255, 255, 255, 0.08));
  border-radius: 10px;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.03));
}

.chat-history-main {
  flex: 1;
  min-width: 0;
  border: none;
  color: var(--cpq-text-primary);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.chat-history-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
}

.chat-history-meta {
  display: block;
  margin-top: 2px;
  color: var(--cpq-text-muted, #9aa4b2);
  font-size: 11px;
}

.chat-history-empty {
  padding: 24px;
  color: var(--cpq-text-muted, #9aa4b2);
  font-size: 12px;
  text-align: center;
}
/* ── AI Office 对话面板：与方案助手视觉对齐 ── */
.colleague-chat {
  position: relative;
}

.chat-head {
  padding: 12px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.chat-role-card {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 14px;
}

.chat-head:hover .chat-role-card {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
}

.chat-role-avatar {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-weight: 700;
  font-size: 17px;
  background: var(--cpq-accent-primary, #1677ff);
}

.chat-role-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-role-meta {
  min-width: 0;
}

.chat-role-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chat-role-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-text-muted, #9aa4b2);
  box-shadow: 0 0 0 4px rgba(154, 164, 178, 0.12);
  flex-shrink: 0;
}

.chat-role-dot.online {
  background: var(--cpq-accent-success, #22c55e);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
}

.chat-role-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-role-desc {
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.chat-icon-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, 0.12));
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  color: var(--cpq-text-muted);
  cursor: pointer;
  font-size: 14px;
}

.chat-icon-btn:hover {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.10));
}

.chat-close:hover {
  border-color: var(--cpq-accent-danger);
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10, rgba(255, 77, 79, 0.10));
}

.chat-history-drawer {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: flex;
  justify-content: flex-end;
}

.chat-history-mask {
  position: absolute;
  inset: 0;
  background: rgba(2, 6, 23, 0.30);
}

.chat-history-panel {
  position: relative;
  width: 86%;
  height: 100%;
  border-left: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.14));
  background: var(--cpq-bg-elevated, #ffffff);
  box-shadow: -20px 0 50px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
}

.chat-history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
}

.chat-history-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.chat-new-thread {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--cpq-accent-primary);
  border-radius: 10px;
  padding: 7px 10px;
  font-size: 12px;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.10));
  cursor: pointer;
}

.chat-new-thread:hover {
  background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.16));
}

.chat-new-thread:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.chat-history-list {
  flex: 1;
  max-height: none;
  overflow-y: auto;
  padding: 8px;
  gap: 4px;
}

.chat-history-row {
  align-items: center;
  padding: 11px;
  border: 0;
  border-radius: 12px;
  background: transparent;
}

.chat-history-row:hover {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
}

.chat-history-row.active {
  background: rgba(59, 130, 246, 0.14);
}

.chat-history-main {
  flex: 1;
  min-width: 0;
}

.chat-history-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.chat-history-meta {
  display: block;
  margin-top: 4px;
  color: var(--cpq-text-muted, #9aa4b2);
  font-size: 11px;
}

.chat-thread-del {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  font-size: 13px;
}

.chat-thread-del:hover {
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10, rgba(255, 77, 79, 0.10));
}

.chat-drawer-enter-active,
.chat-drawer-leave-active {
  transition: opacity 0.18s ease;
}

.chat-drawer-enter-active .chat-history-panel,
.chat-drawer-leave-active .chat-history-panel {
  transition: transform 0.18s ease;
}

.chat-drawer-enter-from,
.chat-drawer-leave-to {
  opacity: 0;
}

.chat-drawer-enter-from .chat-history-panel,
.chat-drawer-leave-to .chat-history-panel {
  transform: translateX(100%);
}

.chat-head-label {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--cpq-text-primary);
  font-size: 13px;
  font-weight: 700;
}

.chat-head-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-text-muted, #9aa4b2);
  box-shadow: 0 0 0 4px rgba(154, 164, 178, 0.12);
  flex-shrink: 0;
}

.chat-head-dot.online {
  background: var(--cpq-accent-success, #22c55e);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
}
.oc-plan-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,.1));
  font-size: 12px;
}
.oc-plan-step {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.12));
  color: var(--cpq-text-secondary, #a6adb4);
}
.oc-plan-step--done { color: #16a34a; border-color: #16a34a44; background: #16a34a0d; }
.oc-plan-step--running { color: var(--cpq-accent-primary, #1677ff); border-color: var(--cpq-accent-primary, #1677ff); background: #1677ff0d; }
.oc-plan-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.oc-plan-step--running .oc-plan-dot { animation: oc-pulse 1s ease-in-out infinite; }
.oc-plan-waiting { margin-left: auto; color: #b45309; }
@keyframes oc-pulse { 0%, 100% { transform: scale(.8); opacity: .6; } 50% { transform: scale(1.2); opacity: 1; } }
</style>
