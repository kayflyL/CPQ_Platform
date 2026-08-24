<script setup lang="ts">
/**
 * 门户 AI 输入区 + 对话流（门户主角）。
 *
 * 设计定调（2026-08-14 重做）：门户是 task-scoped 的，不是 ChatGPT 式长对话复读机。
 * - composer 永远 dock 在底部（肌肉记忆，不跑顶部）
 * - 消息用全宽扁平卡片（微妙背景区分），不用圆气泡
 * - 复杂流程（完整分析时间线 / 多字段确认面板）不堆进主页聊天——主页只接对话 + 路由
 *
 * 零新逻辑：调现有 useAssistant.send（总助对话）/ 需求分析 Skill 自然流程事件，
 * dispatch 转派 / 出方案 / 转报价单全复用，见 memory: portal-ai-shell-pluggable。
 */
import { ref, computed, watch, nextTick, inject } from 'vue'
import { useAssistantContext, type QuickAction } from '@/composables/assistantContext'
import { PORTAL_ASSISTANT_KEY } from '@/components/portal/portalAssistant'

const props = defineProps<{ chatOpen?: boolean }>()
const emit = defineEmits<{ (e: 'open'): void; (e: 'collapse'): void }>()

// 注入 Portal.vue 持有的唯一实例（侧栏与对话区共享，否则切会话不联动）
const assistant = inject(PORTAL_ASSISTANT_KEY, null)
if (!assistant) throw new Error('PortalAIInput 必须在 Portal.vue 内使用（缺少 provide）')
const {
  messages, sending, streamingText, waitingAI,
  colleagues, activeRoleKey,
  pendingDispatch, confirmDispatch, cancelDispatch,
  send,
} = assistant

const { contextLabel, summarize, visibleQuickActions } = useAssistantContext()

const activeColleague = computed(() => {
  const key = activeRoleKey.value
  return (colleagues.value || []).find((c: any) => c?.role_key === key) || null
})
const assistantName = computed(() => activeColleague.value?.name || '方案助手')
const activeAvatarUrl = computed(() => activeColleague.value?.avatar_url || '')
const activeAvatarColor = computed(() => activeColleague.value?.color || 'var(--cpq-accent-primary, #1677ff)')
function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const composerEl = ref<HTMLElement | null>(null)

/**
 * FLIP：chatOpen 切换时，composer 从居中↔底部丝滑滑动。
 * flex 重排不可过渡，所以手动 First-Last-Invert-Play：
 * 切换前记 composer 旧矩形，DOM 更新后用 transform 拉回旧位，下一帧释放 transform 触发滑动。
 * 仅在 chatOpen 翻转那一帧执行一次（消息后续 push 不触发，避免打断）。
 */
watch(() => props.chatOpen, (open, prev) => {
  if (open === prev) return
  const el = composerEl.value
  if (!el) return
  const first = el.getBoundingClientRect()
  nextTick(() => {
    requestAnimationFrame(() => {
      const last = el.getBoundingClientRect()
      const dy = first.top - last.top
      if (!dy) return
      el.style.transition = 'none'
      el.style.transform = `translateY(${dy}px)`
      requestAnimationFrame(() => {
        el.style.transition = 'transform 0.36s cubic-bezier(0.22,1,0.36,1)'
        el.style.transform = ''
        // 兜底：transitionend 偶发不触发（被消息 push 打断），600ms 后强制清理，避免 transform 残留卡住 composer
        const done = () => {
          el.style.transition = ''
          el.style.transform = ''
          el.removeEventListener('transitionend', done)
        }
        el.addEventListener('transitionend', done)
        setTimeout(done, 600)
      })
    })
  })
})

async function onSend() {
  const text = draft.value
  if (!text.trim() || sending.value) return
  // 发送首条即进入聊天态：输入框滑到底部、磁贴隐藏
  emit('open')
  draft.value = ''
  const summary = await summarize()
  await send(text, summary)
}

function onEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  onSend()
}

// 快捷指令（气泡）：prompt 可为函数（动态读配置，如趋势分析）
async function onQuickAction(action: QuickAction) {
  if (sending.value) return
  const prompt = typeof action.prompt === 'function' ? await action.prompt() : action.prompt
  const ctx = action.context ? await action.context() : await summarize()
  await send(prompt, ctx)
}

// 自动滚到底
function scrollToBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}
watch(() => messages.value.length, () => nextTick(scrollToBottom))
watch(streamingText, () => nextTick(scrollToBottom))

// 是否进入「双栏」态：已有任何对话/分析内容（决定 Portal 容器是否展开历史栏）
const hasConversation = computed(() =>
  messages.value.length > 0 || streamingText.value || waitingAI.value)
defineExpose({ hasConversation })
</script>

<template>
  <!-- 居中限宽列容器：空闲态(欢迎语+输入框+磁贴) 与 聊天态(消息流+输入框) 都在这里，
       切换是同一容器内部的动画，不铺满全屏、不进新页面 -->
  <div class="pai" :class="{ 'is-chat': props.chatOpen }">
    <!-- 消息流（聊天态才长出，在容器内、输入框上方，不铺满屏宽；淡入下滑出现） -->
    <transition name="stream">
    <div v-if="props.chatOpen" ref="messagesEl" class="pai-stream">
      <!-- 消息流（全宽扁平卡片） -->
      <div
        v-for="m in messages"
        :key="m.message_id ?? (m.role + m.created_at)"
        class="pai-msg"
        :class="`is-${m.role}`"
      >
        <div v-if="m.role !== 'user'" class="pai-msg-head">
          <div class="pai-avatar" :style="{ background: activeAvatarColor }">
            <img v-if="activeAvatarUrl" :src="activeAvatarUrl" alt="" />
            <span v-else>{{ avatarInitial(assistantName) }}</span>
          </div>
          <span class="pai-author">{{ assistantName }}</span>
        </div>
        <!-- 普通文本消息 -->
        <div class="pai-card">
          <div class="pai-msg-text">{{ m.content }}</div>
        </div>
      </div>

      <!-- 流式输出中 -->
      <div v-if="streamingText" class="pai-msg is-assistant">
        <div class="pai-msg-head">
          <div class="pai-avatar" :style="{ background: activeAvatarColor }">
            <img v-if="activeAvatarUrl" :src="activeAvatarUrl" alt="" />
            <span v-else>{{ avatarInitial(assistantName) }}</span>
          </div>
          <span class="pai-author">{{ assistantName }}</span>
        </div>
        <div class="pai-card"><div class="pai-msg-text">{{ streamingText }}</div></div>
      </div>
      <div v-if="waitingAI" class="pai-typing">{{ assistantName }}正在思考<span class="pai-dots">···</span></div>
    </div>
    </transition>

    <!-- 空闲态开场（欢迎语 + 磁贴），居中流的一部分，聊天态移除 -->
    <transition name="intro">
    <div v-if="!props.chatOpen" class="pai-intro">
      <slot name="intro" />
    </div>
    </transition>

    <!-- 转接确认（dispatch 命中专业同事） -->
    <div v-if="pendingDispatch" class="pai-dispatch glass">
      <span>由 <b>{{ pendingDispatch.colleague.name }}</b> 接管这条消息？</span>
      <button class="pai-dbtn primary" @click="confirmDispatch">转接</button>
      <button class="pai-dbtn" @click="cancelDispatch">仍由总助</button>
    </div>

    <!-- composer：空闲态在居中流里；聊天态在容器底部 -->
    <div ref="composerEl" class="pai-composer">
      <div v-if="visibleQuickActions.length && props.chatOpen" class="pai-bubbles">
        <button
          v-for="a in visibleQuickActions"
          :key="a.key"
          class="pai-bubble"
          :disabled="sending"
          @click="onQuickAction(a)"
        >{{ a.label }}</button>
      </div>
      <div class="pai-input-wrap">
        <textarea
          v-model="draft"
          class="pai-input"
          :placeholder="'配台 Orion 2U 50 台，内存 256G… / 查我的商机 / 帮我核价'"
          rows="1"
          @keydown.enter="onEnter"
        />
        <button class="pai-send" :disabled="!draft.trim() || sending" @click="onSend">
          <span v-if="!sending">发送</span>
          <span v-else class="pai-spin">·</span>
        </button>
        <button v-if="props.chatOpen" class="pai-collapse" title="收起对话，回到首页" @click="emit('collapse')">收起</button>
      </div>
      <p v-if="contextLabel && props.chatOpen" class="pai-context">上下文：{{ contextLabel }}</p>
    </div>

    <!-- 空闲态磁贴（composer 下方） -->
    <transition name="intro">
    <div v-if="!props.chatOpen" class="pai-below">
      <slot name="below" />
    </div>
    </transition>
  </div>
</template>

<style scoped>
.pai {
  /* 内容区适中宽度 + 居中：输入框与磁贴同宽对齐，宽屏左右适度留白，窄屏自适应填满。
     空闲态与聊天态都在这里，不进新页面 */
  display: flex;
  flex-direction: column;
  align-items: stretch;       /* 子项（输入框/磁贴）填满内容宽度，互相同宽对齐 */
  height: 100%;
  min-height: 0;
  width: 100%;
  max-width: 720px;           /* 输入框舒适宽度，磁贴跟它同宽；宽屏居中适度留白，窄屏填满 */
  margin: 0 auto;             /* 内容区在屏幕居中 */
  padding: 0 20px;
  position: relative;
}

/* 空闲态：整组（欢迎语+输入框+磁贴）垂直居中 */
.pai:not(.is-chat) { justify-content: center; }
/* 聊天态：消息流撑满上方，输入框在底部 */
.pai.is-chat { justify-content: flex-start; }

/* 空闲态开场（欢迎语）、磁贴：限宽居中，flex 子项 */
.pai-intro {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}
.pai-below {
  width: 100%;
  margin-top: 28px;
  flex-shrink: 0;
}

/* 消息流：聊天态在容器内撑满上方（flex:1），自动滚；空闲态不渲染 */
.pai-stream {
  flex: 1;
  width: 100%;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 4px 16px;
}

/* 全宽扁平卡片（非圆气泡） */
.pai-msg { display: flex; flex-direction: column; gap: 6px; }
.pai-card {
  padding: 12px 16px;
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w5);
  border: 1px solid var(--cpq-glass-border);
  font-size: 14px; line-height: 1.6;
}
.is-user .pai-card {
  align-self: flex-end;
  max-width: 80%;
  background: var(--cpq-accent-primary);
  color: #fff;
  border: none;
}
.is-assistant .pai-card { color: var(--cpq-text-primary); align-self: stretch; }
.pai-msg-text { white-space: pre-wrap; word-break: break-word; }

/* 角色头像 + 工具调用状态 */
.pai-msg-head {
  display: flex;
  align-items: center;
  gap: 7px;
  padding-left: 2px;
}
.pai-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  border: 1px solid var(--cpq-glass-border);
}
.pai-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.pai-author {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.pai-tool-activity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 2px 8px;
}
.pai-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border-radius: 8px;
  font-size: 12px;
  color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
}
.pai-tool .anticon {
  color: var(--cpq-accent-primary);
}
.pai-tool.done .anticon {
  color: var(--cpq-accent-success, #52c41a);
}
.pai-tool-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pai-tool-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.pai-msg-meta {
  font-size: 11px; color: var(--cpq-text-muted);
  padding-left: 2px; letter-spacing: 0.5px;
}

/* 方案卡 */
.pai-plans { display: flex; flex-direction: column; gap: 10px; }

/* 分析轻提示 */
.pai-status {
  display: inline-flex; align-items: center; gap: 8px;
  align-self: flex-start;
  padding: 6px 12px; border-radius: 999px;
  background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-glass-border);
  font-size: 13px; color: var(--cpq-text-secondary);
}
.pai-status-spin {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--cpq-accent-primary); animation: pai-pulse 1.2s infinite;
}
.pai-error { color: var(--cpq-color-danger, #ff4d4f); font-size: 13px; }

/* 反问面板（最简） */
.pai-card--ask { border-color: var(--cpq-glass-border-strong); }
.pai-ask-q { margin: 4px 0 0; font-size: 14px; color: var(--cpq-text-primary); }

.pai-typing { font-size: 13px; color: var(--cpq-text-muted); padding-left: 4px; }
.pai-dots { animation: pai-blink 1s infinite; }

/* 反问输入区（composer 上方独立条） */
.pai-reply {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 10px 12px; border-top: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-card-bg);
}
.pai-reply-input {
  flex: 1; min-width: 200px; resize: none;
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-w5); color: var(--cpq-text-primary);
  padding: 8px 12px; font-size: 14px; outline: none;
}
.pai-reply-send {
  font-size: 13px; padding: 7px 16px; border-radius: var(--cpq-radius-sm);
  border: none; cursor: pointer; color: #fff;
  background: var(--cpq-accent-primary); transition: opacity 0.15s;
}
.pai-reply-send:disabled { opacity: 0.4; cursor: not-allowed; }
.pai-reply-skip {
  font-size: 12px; color: var(--cpq-text-muted);
  background: none; border: none; cursor: pointer;
}
.pai-reply-skip:hover { color: var(--cpq-text-secondary); }

/* 转接确认 */
.pai-dispatch {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 14px; font-size: 13px; color: var(--cpq-text-secondary);
  border-radius: var(--cpq-radius-md);
}
.pai-dbtn {
  font-size: 13px; padding: 5px 14px; border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-glass-border); background: transparent;
  color: var(--cpq-text-secondary); cursor: pointer; transition: all 0.15s;
}
.pai-dbtn:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-text-primary); }
.pai-dbtn.primary { background: var(--cpq-accent-primary); color: #fff; border-color: transparent; }

/* composer：限宽列内的 flex 子项。
   空闲态：在居中流里（欢迎语与磁贴之间），无边框无背景，像独立输入框；
   聊天态：被上方消息流(flex:1)顶到容器底部，加顶边框分隔。 */
.pai-composer {
  flex-shrink: 0;
  width: 100%;
  padding: 12px 0 4px;
  border-top: none;
  background: transparent;
  transition: background 0.28s ease, border-color 0.28s ease;
}
.pai.is-chat .pai-composer {
  border-top: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-card-bg);
}
.pai-bubbles { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.pai-bubble {
  font-size: 13px; padding: 6px 14px; border-radius: 16px;
  border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary);
  cursor: pointer; transition: all 0.15s;
}
.pai-bubble:hover:not(:disabled) {
  border-color: var(--cpq-glass-border-strong); color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w8);
}
.pai-bubble:disabled { opacity: 0.5; cursor: not-allowed; }

.pai-input-wrap {
  display: flex; gap: 10px; align-items: flex-end;
  padding: 10px 14px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-overlay-w5);
  transition: border-color 0.2s;
}
.pai-input-wrap:focus-within { border-color: var(--cpq-glass-border-strong); }
.pai-input {
  flex: 1; resize: none; border: none; outline: none; background: transparent;
  font-size: 15px; line-height: 1.6; color: var(--cpq-text-primary);
  max-height: 160px;
}
.pai-input::placeholder { color: var(--cpq-text-muted); }
.pai-send {
  flex-shrink: 0; padding: 0 20px; height: 40px; border-radius: var(--cpq-radius-sm);
  border: none; cursor: pointer; font-size: 14px; color: #fff;
  background: var(--cpq-accent-primary);
  transition: transform 0.15s, opacity 0.15s;
}
.pai-send:hover:not(:disabled) { transform: scale(1.02); }
.pai-send:disabled { opacity: 0.4; cursor: not-allowed; }
.pai-spin { animation: pai-blink 1s infinite; }

/* 收起按钮（聊天态，composer 右侧） */
.pai-collapse {
  flex-shrink: 0; height: 40px; padding: 0 14px;
  border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-glass-border); background: transparent;
  color: var(--cpq-text-muted); font-size: 13px;
  cursor: pointer; transition: all 0.15s;
}
.pai-collapse:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-text-primary); }
.pai-context { font-size: 11px; color: var(--cpq-text-muted); margin: 6px 2px 0; }

@keyframes pai-pulse { 50% { opacity: 0.4; } }
@keyframes pai-blink { 50% { opacity: 0.3; } }

/* 消息流：聊天态淡入 + 从上方轻微下滑出现（输入框顺势下移的体感） */
.stream-enter-active { transition: opacity 0.34s ease, transform 0.34s cubic-bezier(0.22,1,0.36,1); }
.stream-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.stream-enter-from { opacity: 0; transform: translateY(18px); }
.stream-leave-to { opacity: 0; transform: translateY(-8px); }

/* 欢迎语/磁贴：空闲态淡入，聊天态淡出 */
.intro-enter-active, .intro-leave-active { transition: opacity 0.26s ease; }
.intro-enter-from, .intro-leave-to { opacity: 0; }

/* 手机端 */
@media (max-width: 768px) {
  .is-user .pai-card { max-width: 88%; }
  .pai-input { font-size: 16px; } /* iOS 防缩放 */
}
</style>
