<template>
  <div class="am-row" :class="`role-${role}`">
    <template v-if="role !== 'user'">
      <div
        class="am-avatar am-avatar--click"
        :class="{ 'am-avatar-has-img': !!author.avatar_url }"
        :style="{ background: author.color || 'var(--cpq-accent-primary, #1677ff)' }"
        title="查看名片"
        @click.stop="$emit('persona', $event)"
      >
        <img v-if="author.avatar_url" :src="author.avatar_url" alt="" />
        <span v-else class="am-avatar-initial">{{ avatarInitial(author.name) }}</span>
        <i v-if="presenceOn" class="am-presence"></i>
      </div>
      <div class="am-content">
        <div v-if="showAuthor || authorTime" class="am-metarow">
          <span v-if="showAuthor && author.name" class="am-author">{{ author.name }}</span>
          <span v-if="showAuthor && author.name" class="am-aichip">AI 员工</span>
          <span v-if="authorTime" class="am-time">{{ authorTime }}</span>
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
          <div v-if="quoteInfo" class="am-quote-card">
            <span class="am-q-n">{{ quoteInfo.name || '消息' }}</span>
            <span class="am-q-t">{{ quoteInfo.text }}</span>
          </div>
          <div v-if="thinking || thinkingActive" class="am-think" :class="{ 'am-think--live': thinkingActive }">
            <button type="button" class="am-think-head" @click="thinkOpen = !thinkOpen">
              <span class="am-think-ico">💡</span>
              <span class="am-think-label">{{ thinkingActive ? '思考中' : '已思考' }}</span>
              <span v-if="thinkSecText" class="am-think-sec">{{ thinkSecText }}</span>
              <span class="am-think-chev" :class="{ open: thinkOpen }">▾</span>
            </button>
            <div v-if="thinkOpen && thinkingTail" ref="thinkTextEl" class="am-think-body">{{ thinkingTail }}<span v-if="thinkingActive" class="am-think-caret"></span></div>
          </div>
          <div v-for="(t, i) in traceRows" :key="'step' + i" class="am-tool-trace">
            <span class="am-tt-ico">⚙</span>
            <span class="am-tt-text">{{ traceText(t) }}<span v-if="t.detail" class="am-tt-detail">{{ t.detail }}</span></span>
            <span v-if="t.elapsedMs" class="am-tt-ms">{{ (t.elapsedMs / 1000).toFixed(1) }}s</span>
            <span class="am-tt-st" :class="t.phase"><i v-if="t.phase === 'start'" class="am-tt-spin"></i></span>
          </div>
          <template v-if="content || streaming">
            {{ content }}<span v-if="streaming" class="am-cursor">▍</span>
            <span v-if="statusText && !traceRows.length" class="am-status-line am-status-under"><span class="am-status-dot"></span>{{ statusText }}</span>
          </template>
          <!-- 思考块/步骤行在场时它们就是进度指示，气泡内不再重复渲染状态行 -->
          <template v-else-if="statusText && !thinking && !thinkingActive && !traceRows.length">
            <span class="am-status-line"><span class="am-status-dot"></span>{{ statusText }}</span>
          </template>
          <template v-else-if="idleText && !thinking && !thinkingActive && !traceRows.length">
            <span class="am-status-line"><span class="am-status-dot"></span>{{ idleText }}</span>
          </template>
          <template v-else>
            <span class="am-typing"><i></i><i></i><i></i></span>
          </template>
        </div>
      </div>
      <button v-if="!streaming && !isAskCard" type="button" class="am-reply-btn" title="引用回复" @click="onReply">↩</button>
    </template>
    <div v-else class="am-usercol">
      <div class="am-usermeta">
        <span class="am-uname">{{ selfAvatar?.name || '你' }}</span>
        <span v-if="userTime" class="am-time">{{ userTime }}</span>
      </div>
      <div class="am-row-user">
        <button type="button" class="am-reply-btn" title="引用回复" @click="onReply">↩</button>
        <div class="am-bubble">
          <div v-if="quoteInfo" class="am-quote-card">
            <span class="am-q-n">{{ quoteInfo.name || '消息' }}</span>
            <span class="am-q-t">{{ quoteInfo.text }}</span>
          </div>
          {{ content }}
        </div>
        <span class="am-selfavatar">
          <img v-if="selfAvatar?.avatar_url" :src="selfAvatar.avatar_url" alt="" />
          <template v-else>{{ String(selfAvatar?.name || '你').slice(0, 1).toUpperCase() }}</template>
          <i class="am-presence on"></i>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onBeforeUnmount } from 'vue'
import AskCard from '@/components/assistant/AskCard.vue'
import type { ToolTrace } from '@/composables/assistantChatWs'
import { fmtChatTime } from '@/utils/chatTime'

const props = withDefaults(defineProps<{
  message?: {
    role?: string
    content?: string
    kind?: string
    data?: string
    created_at?: string
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
  /** 思考流工具卡：同事回合的工具调用 start/done 事实（仅回合进行中的直播项传入） */
  traces?: ToolTrace[]
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
  /** 头像 presence 点（面板接办公室状态流；办公室房间走自己的 statusMap） */
  presenceOn?: boolean
  /** 发消息的真实用户身份（人类侧标识：右侧小头像），不传则只显示「你」 */
  selfAvatar?: { name?: string; avatar_url?: string } | null
}>(), {
  message: undefined,
  author: () => ({ name: 'AI', avatar_url: '', color: '' }),
  streaming: false,
  typing: false,
  statusText: '',
  idleText: '',
  thinking: '',
  thinkingActive: false,
  traces: () => [],
  optionInteractive: true,
  optionAnswered: false,
  threadId: '',
  pickRole: '',
  showAuthor: true,
  presenceOn: false,
  selfAvatar: null,
})

const emit = defineEmits<{
  (e: 'select-option', value: string, slot?: string): void
  (e: 'submit-selections', selections: Array<{ slot: string; value: string; label: string; qty?: number }>): void
  (e: 'reply', q: { name: string; text: string }): void
  (e: 'persona', ev: MouseEvent): void
}>()

// 思考块：多行增长（保留换行），限长尾部 + 块内自动跟底；直播展开、收尾自动折叠
const thinkingTail = computed(() => {
  const t = (props.thinking || '').trim()
  return t.length > 1600 ? '…' + t.slice(-1600) : t
})
const thinkTextEl = ref<HTMLElement | null>(null)
watch(() => props.thinking, async () => {
  await nextTick()
  const el = thinkTextEl.value
  if (el) el.scrollTop = el.scrollHeight
})

// 思考计时 + 自动折叠：live 开始计时展开，live 结束（答案落地）折叠成一行
const thinkOpen = ref(true)
const thinkSec = ref(0)
let thinkTimer: ReturnType<typeof setInterval> | null = null
watch(() => props.thinkingActive, (v, old) => {
  if (v && !old) {
    thinkOpen.value = true
    thinkSec.value = 0
    thinkTimer = setInterval(() => { thinkSec.value += 1 }, 1000)
  }
  if (!v && old) {
    if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null }
    thinkOpen.value = false
  }
}, { immediate: true })
onBeforeUnmount(() => { if (thinkTimer) clearInterval(thinkTimer) })
const thinkSecText = computed(() => {
  if (!props.thinkingActive) return thinkSec.value > 0 ? `${thinkSec.value}s` : ''
  return `${thinkSec.value}s`
})

function traceText(t: ToolTrace): string {
  if (t.text) return t.text
  return t.phase === 'done' ? `${t.tool} 完成` : `正在调用 ${t.tool}…`
}

const role = computed(() => props.message?.role === 'user' ? 'user' : 'assistant')
const content = computed(() => props.message?.content || '')
const authorTime = computed(() => fmtChatTime(props.message?.created_at))
const userTime = authorTime

// 引用卡：随消息存的快照（data JSON 的 {quote:{name,text}}），原作者与原文 120 字内
const quoteInfo = computed<{ name: string; text: string } | null>(() => {
  const raw = props.message?.data
  if (!raw) return null
  try {
    const q = (JSON.parse(raw) || {}).quote
    if (q && typeof q.text === 'string' && q.text) {
      return { name: String(q.name || ''), text: String(q.text) }
    }
  } catch {
    /* data 另作他用的消息形状，当无引用处理 */
  }
  return null
})

// 步骤行：直播用 traces；历史消息读落库的 tool_steps（回合结束不清，常驻可查）
const traceRows = computed<Array<ToolTrace & { elapsedMs?: number }>>(() => {
  const live = props.traces || []
  if (live.length) return live
  const raw = props.message?.data
  if (!raw) return []
  try {
    const steps = (JSON.parse(raw) || {}).tool_steps
    if (!Array.isArray(steps)) return []
    return steps.map((s: any) => ({
      tool: String(s?.tool || ''),
      phase: 'done' as const,
      text: String(s?.text || ''),
      detail: String(s?.detail || ''),
      elapsedMs: Number(s?.elapsed_ms || 0),
    }))
  } catch {
    return []
  }
})

function onReply() {
  const text = content.value.replace(/\s+/g, ' ').trim()
  if (!text || props.streaming) return
  emit('reply', { name: role.value === 'user' ? '我' : (props.author?.name || '消息'), text: text.length > 60 ? text.slice(0, 60) + '…' : text })
}

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

/* 引用回复悬停按钮：行悬停浮现（触屏无 hover，随磁贴模式惯例不另做长按） */
.am-reply-btn {
  flex: none;
  width: 24px;
  height: 24px;
  margin-top: 4px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--cpq-border-light);
  background: var(--cpq-bg-card);
  color: var(--cpq-text-muted);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.am-row:hover .am-reply-btn { opacity: 1; }
.am-reply-btn:hover {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
}

.role-user {
  justify-content: flex-end;
}

.role-assistant,
.role-system {
  justify-content: flex-start;
}

/* 用户行包裹层：按钮 + 气泡右对齐 */
.am-row-user {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
}

/* 消息内引用卡（原型 quote-card）：快照展示，原作者+原文 */
.am-quote-card {
  display: flex;
  gap: 6px;
  align-items: baseline;
  max-width: 100%;
  padding: 4px 8px;
  margin-bottom: 4px;
  border-radius: 6px;
  background: var(--cpq-overlay-w4);
  font-size: 12px;
}
.am-q-n { flex-shrink: 0; font-weight: 600; color: var(--cpq-text-secondary); }
.am-q-t {
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  overflow: visible;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
  position: relative;
}
/* 作者头像可点（查看名片）：聊天流里点谁的头像看谁的名片 */
.am-avatar--click { cursor: pointer; }
.am-avatar--click:hover { box-shadow: 0 0 0 2px var(--cpq-overlay-a15, rgba(22, 119, 255, 0.15)); }

.am-avatar-initial {
  line-height: 1;
}

.am-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
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
  margin-bottom: 0;
  font-weight: 600;
}

/* 作者 meta 行：名字 + 时间（原型 msg-name + msg-time） */
.am-metarow {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
  min-width: 0;
}
.am-time {
  flex: none;
  font-size: 11px;
  color: var(--cpq-text-disabled);
}

/* 头像 presence 点（面板接办公室状态流时传入） */
.am-avatar { position: relative; }
.am-presence {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #52c9a0;
  border: 2px solid var(--cpq-bg-card, #fff);
}

/* 用户消息列：meta 行（你 · 时间）在气泡上方右对齐 */
.am-usercol {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  width: 100%;
  min-width: 0;
}
.am-usermeta {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  margin-bottom: 3px;
}
.am-uname {
  font-weight: 600;
  color: var(--cpq-text-secondary);
}

/* 身份徽标：AI 消息名字旁小蓝牌，人类消息「你」旁小灰牌（真人/AI 一眼可分） */
.am-aichip {
  flex: none;
  font-size: 10px;
  font-weight: 600;
  padding: 0 5px;
  border-radius: 999px;
  line-height: 16px;
  color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.1));
}
/* 用户消息右侧小头像（真人侧对称 AI 侧头像） */
.am-selfavatar {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  overflow: visible;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}
.am-selfavatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

/* 思考块/工具卡长在气泡卡内部（原型消息卡形态）：占满气泡宽 */
.am-bubble .am-think,
.am-bubble .am-tool-trace {
  width: 100%;
}
.am-bubble .am-think { margin-bottom: 6px; }
.am-bubble .am-tool-trace { margin-bottom: 4px; }

/* 思考块（可折叠）：头部一行（图标+标签+计时+箭头），展开是限高滚动的思考尾部 */
.am-think {
  /* 气泡内整卡宽行（参考云助手步骤行）：无 min-width 会被气泡按最短内容折成竖排细条 */
  width: 100%;
  min-width: 260px;
  margin: 0 0 6px;
  border-radius: 8px;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  border: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.12));
  font-size: 12px;
  color: var(--cpq-text-secondary, #a6adb4);
  overflow: hidden;
}
.am-think-head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  user-select: none;
  text-align: left;
  color: inherit;
  font-size: 12px;
}
.am-think-head:hover { color: var(--cpq-accent-primary, #1677ff); }
.am-think-label { font-weight: 600; }
.am-think-sec {
  margin-left: auto;
  color: var(--cpq-text-muted, #86909c);
  font-variant-numeric: tabular-nums;
}
.am-think-chev { margin-left: 2px; font-size: 10px; transition: transform 0.2s cubic-bezier(.16, 1, .3, 1); }
.am-think-chev.open { transform: rotate(180deg); }
.am-think-body {
  padding: 2px 10px 9px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 138px;
  overflow-y: auto;
  scrollbar-width: thin;
  line-height: 18px;
}
.am-think-caret {
  display: inline-block;
  width: 7px;
  height: 13px;
  margin-left: 2px;
  vertical-align: -2px;
  border-radius: 1px;
  background: var(--cpq-accent-primary, #1677ff);
  animation: am-blink 1s steps(2, start) infinite;
}

/* 工具活动卡：start 转圈 → done 打勾，同一工具原地翻状态 */
.am-tool-trace {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 260px;
  margin-bottom: 5px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  border: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.12));
  font-size: 12px;
  color: var(--cpq-text-secondary, #a6adb4);
}
.am-tt-ico { flex: none; font-size: 12px; opacity: .75; }
.am-tt-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.am-tt-detail { color: var(--cpq-text-muted, #86909c); margin-left: 6px; }
.am-tt-ms {
  flex: none;
  margin-left: 4px;
  color: var(--cpq-text-muted, #86909c);
  font-variant-numeric: tabular-nums;
}
.am-tt-st { flex: none; min-width: 14px; text-align: center; }
.am-tt-st.done::after { content: '✓'; color: #2f9d78; }
.am-tt-spin {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 2px solid color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 25%, transparent);
  border-top-color: var(--cpq-accent-primary, #1677ff);
  border-radius: 50%;
  animation: am-tt-rotate 0.8s linear infinite;
}
@keyframes am-tt-rotate { to { transform: rotate(360deg); } }

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
