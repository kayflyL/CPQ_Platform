<template>
  <Teleport to="body">
    <transition name="assistant-panel">
      <div v-if="open" class="assistant-panel" :style="panelStyle">
        <!-- header（可拖动）-->
        <div class="ap-header" @mousedown="startDrag">
          <div class="ap-title">
            <RobotOutlined />
            <span>方案助手</span>
          </div>
          <div class="ap-ctx" v-if="contextLabel">
            <span class="ap-ctx-dot"></span>{{ contextLabel }}
          </div>
          <div class="ap-ctx ap-ctx-none" v-else>无上下文</div>
          <button class="ap-close" @click="emit('update:open', false)" title="收起">
            <CloseOutlined />
          </button>
        </div>

        <!-- thread 切换 -->
        <div class="ap-threads">
          <a-select
            :value="currentThreadId || undefined"
            size="small"
            class="ap-thread-select"
            :placeholder="threads.length ? `切换会话（共 ${threads.length} 个）` : '还没有会话'"
            :options="threadOptions"
            :allow-clear="false"
            :get-popup-container="getPopupContainer"
            @change="(id: any) => selectThread(String(id))"
          >
            <template #option="{ value, label }">
              <div class="thread-opt">
                <span class="thread-opt-label">{{ label }}</span>
                <DeleteOutlined class="thread-opt-del" @click.stop="onDeleteThread(String(value))" />
              </div>
            </template>
          </a-select>
          <a-button size="small" @click="onNewThread" :loading="loading">
            <template #icon><PlusOutlined /></template>
            新会话
          </a-button>
        </div>

        <!-- 消息列表 -->
        <div class="ap-messages" ref="messagesEl">
          <a-spin v-if="loading" size="small" class="ap-spin" />
          <a-empty
            v-else-if="!messages.length && !streamingText && !waitingAI"
            :image-style="{ height: '48px' }"
            description="和方案助手聊聊？输入消息开始"
          />
          <div v-else class="ap-msg-list">
            <div
              v-for="m in messages"
              :key="m.message_id"
              class="ap-msg"
              :class="`role-${m.role}`"
            >
              <div class="ap-bubble">{{ m.content }}</div>
            </div>
            <div v-if="streamingText || waitingAI" class="ap-msg role-assistant">
              <div class="ap-bubble">
                <template v-if="streamingText">{{ streamingText }}<span class="ap-cursor">▍</span></template>
                <span v-else class="ap-typing"><i></i><i></i><i></i></span>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入 -->
        <div class="ap-input">
          <a-textarea
            v-model:value="draft"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            placeholder="输入消息，Enter 发送 / Shift+Enter 换行"
            :disabled="sending"
            @press-enter="onEnter"
          />
          <a-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="onSend">
            发送
          </a-button>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { RobotOutlined, PlusOutlined, CloseOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import { useAssistant } from '@/composables/useAssistant'
import { useAssistantContext } from '@/composables/assistantContext'
import { useAssistantFab, computePanelAnchor } from '@/composables/useAssistantFab'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const {
  threads, currentThreadId, messages, loading, sending, streamingText, waitingAI,
  loadThreads, selectThread, newThread, send, removeThread, connectWs, disconnectWs,
} = useAssistant()

const { contextLabel, summarize } = useAssistantContext()

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)

// 面板贴着 FAB 当前位置打开（FAB 拖到哪儿，面板就跟到哪儿附近）
const { pos: fabPos, getFabRect } = useAssistantFab()
const viewportTick = ref(0)

// 用户拖动后的偏移量（持久化到 sessionStorage）
const dragOffset = ref({ x: 0, y: 0 })
const DRAG_KEY = 'assistant-panel-offset'

// 加载已保存的偏移
onMounted(() => {
  try {
    const saved = sessionStorage.getItem(DRAG_KEY)
    if (saved) {
      dragOffset.value = JSON.parse(saved)
    }
  } catch {
    /* ignore */
  }
})

const panelStyle = computed(() => {
  // 依赖 fabPos / viewportTick 触发重算（FAB 拖动或窗口缩放时跟着挪）
  void fabPos.value
  void viewportTick.value
  const rect = getFabRect()
  if (!rect) return undefined // FAB 还没挂载 → 回落 CSS 默认（右下角）
  const vw = window.innerWidth
  const vh = window.innerHeight
  const { left, top, height } = computePanelAnchor(rect, vw, vh)
  // 应用用户拖动偏移
  return {
    left: left + dragOffset.value.x + 'px',
    top: top + dragOffset.value.y + 'px',
    right: 'auto',
    bottom: 'auto',
    height: height + 'px',
    maxHeight: height + 'px',
  }
})
function onResize() { viewportTick.value++ }
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

// 拖动逻辑
let dragging = false
let dragStart = { x: 0, y: 0 }
let offsetStart = { x: 0, y: 0 }

function startDrag(e: MouseEvent) {
  // 忽略关闭按钮点击
  if ((e.target as HTMLElement).closest('.ap-close')) return

  dragging = true
  dragStart = { x: e.clientX, y: e.clientY }
  offsetStart = { ...dragOffset.value }

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)

  // 防止选中文字
  e.preventDefault()
}

function onDrag(e: MouseEvent) {
  if (!dragging) return

  const dx = e.clientX - dragStart.x
  const dy = e.clientY - dragStart.y

  dragOffset.value = {
    x: offsetStart.x + dx,
    y: offsetStart.y + dy,
  }
}

function stopDrag() {
  if (!dragging) return
  dragging = false

  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)

  // 持久化偏移
  try {
    sessionStorage.setItem(DRAG_KEY, JSON.stringify(dragOffset.value))
  } catch {
    /* ignore */
  }
}

// vue-tsc 模板里拿不到全局 document，集中到 script setup 暴露
const getPopupContainer = (node: any) => node?.closest('.assistant-panel') || document.body

const threadOptions = computed(() =>
  threads.value.map((t) => ({ value: t.thread_id, label: t.title || '新会话' })),
)

watch(
  () => props.open,
  async (v) => {
    if (v) {
      await loadThreads()
      if (currentThreadId.value) connectWs(currentThreadId.value)
    } else {
      disconnectWs()
    }
  },
  { immediate: true },
)

watch(() => messages.value.length, async () => {
  await nextTick(scrollToBottom)
})
watch(streamingText, async () => {
  await nextTick(scrollToBottom)
})

function scrollToBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function onEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  onSend()
}

async function onSend() {
  const text = draft.value
  if (!text.trim() || sending.value) return
  draft.value = ''
  const summary = await summarize()
  await send(text, summary)
}

async function onNewThread() {
  await newThread()
}

function onDeleteThread(id: string) {
  Modal.confirm({
    title: '删除该会话？',
    content: '将移除该会话及其全部消息。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      await removeThread(id)
    },
  })
}
</script>

<style scoped>
.assistant-panel {
  position: fixed;
  right: 24px;
  bottom: 88px;
  width: 380px;
  height: 560px;
  max-height: calc(100vh - 120px);
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(var(--cpq-glass-blur-3, 16px));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3, 16px));
  border: 1px solid var(--cpq-glass-border);
  border-radius: 16px;
  box-shadow: 0 12px 40px var(--cpq-shadow-color-strong, rgba(0, 0, 0, 0.25));
  z-index: 1500;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ap-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: move;
  user-select: none;
}
.ap-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-title :deep(.anticon) {
  color: var(--cpq-accent-primary);
}
.ap-ctx {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-ctx-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-success, #52c41a);
  flex-shrink: 0;
}
.ap-ctx-none {
  color: var(--cpq-text-muted);
}
.ap-ctx-none .ap-ctx-dot {
  background: var(--cpq-text-muted);
}
.ap-close {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.ap-close:hover {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
}

.ap-threads {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w4);
  align-items: center;
}
.ap-thread-select {
  flex: 1;
  min-width: 0;
}
.thread-opt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.thread-opt-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-opt-del {
  color: var(--cpq-text-muted);
  font-size: 12px;
  padding: 2px;
  flex-shrink: 0;
  cursor: pointer;
}
.thread-opt-del:hover {
  color: var(--cpq-accent-danger);
}

.ap-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  min-height: 0;
}
.ap-spin {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
.ap-msg-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ap-msg {
  display: flex;
}
.role-user {
  justify-content: flex-end;
}
.role-assistant,
.role-system {
  justify-content: flex-start;
}
.ap-bubble {
  max-width: 82%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}
.role-user .ap-bubble {
  background: var(--cpq-accent-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.role-assistant .ap-bubble {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary);
  border: 1px solid var(--cpq-overlay-w6);
  border-bottom-left-radius: 4px;
}
.role-system .ap-bubble {
  background: transparent;
  color: var(--cpq-text-muted);
  font-style: italic;
  font-size: 12px;
}
.ap-cursor {
  display: inline-block;
  animation: ap-blink 1s steps(2, start) infinite;
  color: var(--cpq-accent-primary);
  margin-left: 1px;
}
@keyframes ap-blink {
  to {
    visibility: hidden;
  }
}
.ap-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}
.ap-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: ap-typing-bounce 1.2s infinite ease-in-out;
}
.ap-typing i:nth-child(2) {
  animation-delay: 0.15s;
}
.ap-typing i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes ap-typing-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.ap-input {
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w6);
  display: flex;
  gap: 8px;
  align-items: flex-end;
  background: var(--cpq-overlay-w3);
}

.assistant-panel-enter-active,
.assistant-panel-leave-active {
  transition: opacity 0.25s ease, transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.assistant-panel-enter-from,
.assistant-panel-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}
</style>
