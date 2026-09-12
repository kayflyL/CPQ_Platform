<template>
  <div class="am-row" :class="`role-${role}`">
    <template v-if="role !== 'user'">
      <div
        class="am-avatar"
        :class="{ 'am-avatar-has-img': !!author.avatar_url }"
        :style="{ background: author.color || 'var(--cpq-accent-primary, #1677ff)' }"
      >
        <img v-if="author.avatar_url" :src="author.avatar_url" alt="" />
        <span v-else class="am-avatar-initial">{{ avatarInitial(author.name) }}</span>
      </div>
      <div class="am-content">
        <span v-if="showAuthor && author.name" class="am-author">{{ author.name }}</span>
        <!-- 思考过程：Claude Code 式多行增长暗色块——限高内部滚动自动跟底 -->
        <div v-if="thinking" class="am-thinking" :class="{ 'am-thinking--live': thinkingActive }">
          <span class="am-thinking-dot" />
          <span ref="thinkTextEl" class="am-thinking-text">{{ thinkingTail }}</span>
        </div>
      <AskCard
        v-if="isAskCard"
        :message="message"
        :thread-id="threadId"
        :pick-role="pickRole"
        :option-interactive="optionInteractive"
        :option-answered="optionAnswered"
        @select-option="onSelectOption"
        @submit-selections="onSubmitSelections"
      />
      <div v-else class="am-bubble am-bubble--live">
          <template v-if="content || streaming">
            {{ content }}<span v-if="streaming" class="am-cursor">▍</span>
            <span v-if="statusText" class="am-status-line am-status-under"><span class="am-status-dot"></span>{{ statusText }}</span>
          </template>
          <template v-else-if="statusText">
            <span class="am-status-line"><span class="am-status-dot"></span>{{ statusText }}</span>
          </template>
          <template v-else-if="idleText">
            <span class="am-status-line"><span class="am-status-dot"></span>{{ idleText }}</span>
          </template>
          <template v-else>
            <span class="am-typing"><i></i><i></i><i></i></span>
          </template>
        </div>
      </div>
    </template>
    <div v-else class="am-bubble">{{ content }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AskCard from '@/components/assistant/AskCard.vue'

const props = withDefaults(defineProps<{
  message?: {
    role?: string
    content?: string
    kind?: string
    data?: string
  }
  author?: {
    name?: string
    avatar_url?: string
    color?: string
  }
  streaming?: boolean
  typing?: boolean
  statusText?: string
  /** 静默心跳文案（父组件计时）：三条流全空时替呼吸点显示「模型思考中 Ns…」 */
  idleText?: string
  thinking?: string
  thinkingActive?: boolean
  /** 问题面板是否可点：已答/被取代或回合进行中为 false（父组件按消息序+运行态计算） */
  optionInteractive?: boolean
  /** 选项卡是否已被回答/取代（父组件按消息序计算）：塌成一行静态记录。
   *  与 optionInteractive 分离：回合进行中卡片可见但禁点，不再整卡消失 */
  optionAnswered?: boolean
  /** 当前会话 ID：配件库自选候选按它查询（card-pick 端点读留底卡） */
  threadId?: string
  /** 发卡角色（浮动面板会话可被分派，记忆按角色存）：留空走线程默认 */
  pickRole?: string
  /** 是否显示作者名：群聊/转接才显示（单人格 DM 常驻省略） */
  showAuthor?: boolean
}>(), {
  message: undefined,
  author: () => ({ name: 'AI', avatar_url: '', color: '' }),
  streaming: false,
  typing: false,
  statusText: '',
  idleText: '',
  thinking: '',
  thinkingActive: false,
  optionInteractive: true,
  optionAnswered: false,
  threadId: '',
  pickRole: '',
  showAuthor: true,
})

const emit = defineEmits<{
  (e: 'select-option', value: string, slot?: string): void
  (e: 'submit-selections', selections: Array<{ slot: string; value: string; label: string; qty?: number }>): void
}>()

// Claude Code 式思考块：多行增长（保留换行），限长尾部 + 块内自动跟底
const thinkingTail = computed(() => {
  const t = (props.thinking || '').trim()
  if (!t) return '思考中…'
  return t.length > 1600 ? '…' + t.slice(-1600) : t
})
const thinkTextEl = ref<HTMLElement | null>(null)
watch(() => props.thinking, async () => {
  await nextTick()
  const el = thinkTextEl.value
  if (el) el.scrollTop = el.scrollHeight
})
const role = computed(() => props.message?.role === 'user' ? 'user' : 'assistant')
const content = computed(() => props.message?.content || '')

function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

const isAskCard = computed(() => props.message?.kind === 'input_options' && !!props.message?.data)

function onSelectOption(value: string, slot?: string) {
  emit('select-option', value, slot)
}

function onSubmitSelections(selections: Array<{ slot: string; value: string; label: string; qty?: number }>) {
  emit('submit-selections', selections)
}
</script>

<style scoped>
.am-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.role-user {
  justify-content: flex-end;
}

.role-assistant,
.role-system {
  justify-content: flex-start;
}

.am-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
}

.am-avatar-initial {
  line-height: 1;
}

.am-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.am-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  max-width: calc(100% - 38px);
}

.am-author {
  font-size: 12px;
  line-height: 1.2;
  color: var(--cpq-text-muted);
  margin-bottom: 4px;
}

/* 思考过程：Claude Code 式单行动态刷新（实时显示思考尾部片段） */
.am-thinking {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 82%;
  margin-bottom: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  border: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.12));
  font-size: 12px;
  line-height: 18px;
  color: var(--cpq-text-secondary, #a6adb4);
  opacity: .9;
}
.am-thinking-dot {
  flex: none;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: currentColor;
}
.am-thinking--live .am-thinking-dot {
  animation: am-think-pulse 1.2s ease-in-out infinite;
}
.am-thinking--live {
  opacity: 1;
}
.am-thinking-text {
  min-width: 0;
  display: block;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 138px;
  overflow-y: auto;
  scrollbar-width: thin;
}
@keyframes am-think-pulse {
  0%, 100% { opacity: .35; transform: scale(.85); }
  50% { opacity: 1; transform: scale(1.1); }
}

.am-bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.7;
  word-break: break-word;
  white-space: pre-wrap;
}

.role-user .am-bubble {
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.role-assistant .am-bubble,
.role-system .am-bubble {
  background: var(--cpq-overlay-w3);
  color: var(--cpq-text-primary);
  border: none;
  border-bottom-left-radius: 4px;
}

.am-cursor {
  display: inline-block;
  animation: am-blink 1s steps(2, start) infinite;
  color: var(--cpq-accent-primary, #1677ff);
  margin-left: 1px;
}

@keyframes am-blink {
  to { visibility: hidden; }
}

.am-status-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--cpq-text-secondary, #a6adb4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 正文已流出后挂载的状态行：换行到正文下方，留一点呼吸 */
.am-status-under {
  display: flex;
  margin-top: 6px;
}
.am-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  animation: am-pulse-dot 1.1s ease-in-out infinite;
  flex: none;
}
@keyframes am-pulse-dot {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.1); }
}
.am-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}

.am-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: am-typing-bounce 1.2s infinite ease-in-out;
}

.am-typing i:nth-child(2) { animation-delay: 0.15s; }
.am-typing i:nth-child(3) { animation-delay: 0.3s; }

@keyframes am-typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
  30% { transform: translateY(-3px); opacity: 1; }
}
</style>
