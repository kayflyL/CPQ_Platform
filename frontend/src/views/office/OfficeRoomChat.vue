<template>
  <Teleport to="body" :disabled="!fs">
    <section class="room-chat" :class="{ 'room-chat--fs': fs }">
    <div class="room-head">
      <span class="rh-glyph">群</span>
      <div class="rh-main">
        <div class="rh-title">团队群 <span class="rh-chip">房间</span></div>
        <div class="rh-sub">
          <template v-if="s?.waiting">{{ s.statusText || '对方正在回话…' }}</template>
          <template v-else>{{ members.length }} 位成员 · 可 @ 点名</template>
        </div>
      </div>
      <div class="rh-roster">
        <button
          v-for="c in members.slice(0, 5)"
          :key="c.role_key"
          type="button"
          class="rh-av"
          :class="{ 'rh-av--on': isOn(c) }"
          :style="{ background: c.color || 'var(--cpq-accent-primary, #1677ff)' }"
          :title="`${c.name || c.role_key} · ${statusTextOf(c)}`"
          @click="$emit('persona', c, $event)"
        >
          <img v-if="c.avatar_url" :src="c.avatar_url" alt="" />
          <span v-else>{{ initialOf(c) }}</span>
        </button>
        <span v-if="members.length > 5" class="rh-more">+{{ members.length - 5 }}</span>
        <div class="rh-actions">
          <button type="button" class="rh-btn" title="会话历史" @click="toggleHist">↺</button>
          <button type="button" class="rh-btn" title="新建会话（归档当前）" :disabled="!!s?.sending || !!s?.running" @click="startNewThread">＋</button>
          <button type="button" class="rh-btn" :title="fs ? '退出全屏（Esc）' : '全屏'" @click="fs = !fs">{{ fs ? '⤡' : '⛶' }}</button>
        </div>
      </div>
    </div>

    <!-- 会话历史抽屉（房间内浮层）：群渠道与浮动面板共享同一线程列表 -->
    <div v-if="histOpen" class="room-hist">
      <div class="rhi-head">
        <span class="rhi-title">会话历史</span>
        <button type="button" class="rq-x" @click="histOpen = false">✕</button>
      </div>
      <div class="rhi-list">
        <button
          v-for="t in histItems"
          :key="t.thread_id"
          type="button"
          class="rhi-item"
          :class="{ active: t.thread_id === s?.threadId }"
          @click="openHistThread(t)"
        >
          <span class="rhi-name">{{ t.title || '未命名会话' }}</span>
          <span class="rhi-meta">
            <span v-if="String(t.deleted_at || '').trim()" class="rhi-archived">已归档</span>
            <span>{{ (t.updated_at || t.created_at || '').slice(0, 10) }}</span>
          </span>
        </button>
        <div v-if="!histItems.length" class="rhi-empty">暂无历史会话</div>
      </div>
    </div>

    <div ref="messagesEl" class="room-messages">
      <div v-if="loading" class="room-hint">会话加载中…</div>
      <template v-for="m in s?.messages || []" :key="m.message_id">
        <AssistantMessageItem
          :message="m"
          :author="authorOf(m)"
          :thread-id="s?.threadId || ''"
          @select-option="(v: string, slot?: string) => $emit('select-option', v, slot)"
          @submit-selections="(sel: any) => $emit('submit-selections', sel)"
          @reply="(q: { name: string; text: string }) => (quoted = q)"
          @persona="(ev: MouseEvent) => $emit('persona', colleagueOf(m), ev)"
          :self-avatar="selfIdentity"
        />
      </template>
      <AssistantMessageItem
        v-if="s?.streamingText || s?.waiting"
        :message="{ role: 'assistant', content: s?.streamingText || '' }"
        :author="leadAuthor"
        :streaming="!!s?.streamingText"
        :typing="!s?.streamingText && !thinkingActive"
        :status-text="s?.statusText"
        :thinking="s?.thinkingText"
        :thinking-active="thinkingActive"
        :traces="s?.toolTraces || []"
      />
      <div v-if="s?.error" class="room-error">{{ s.error }}</div>
    </div>

    <div v-if="quoted" class="room-quote-bar">
      <span class="rq-text">↩ 引用 <b>{{ quoted.name }}</b>：{{ quoted.text }}</span>
      <button type="button" class="rq-x" @click="quoted = null">✕</button>
    </div>

    <AssistantComposer
      v-model="draft"
      placeholder="输入消息…（@ 可点名同事）"
      :disabled="loading"
      :sending="s?.sending"
      :running="s?.running"
      :queued="s?.queuedCount"
      :members="members"
      hint="@ = 指定该同事接话 · Enter 发送 · 悬停消息可引用"
      @send="onSend"
      @stop="onStop"
    />
    </section>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, nextTick, watch } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import AssistantMessageItem from '@/components/assistant/AssistantMessageItem.vue'
import AssistantComposer from '@/components/assistant/AssistantComposer.vue'
import { assistantApi, type AssistantContext, type AssistantMessage, type AssistantThread } from '@/api/assistant'
import { useAuthStore } from '@/store/auth'
import { productionRuntime } from '@/composables/chatRuntime'
import type { ChatSession } from '@/composables/chatRuntime'
import { applyTaskState, clearThinking, resetTaskUI } from '@/composables/assistantChatWs'
import { useChatAutoScroll } from '@/composables/useChatAutoScroll'

const props = defineProps<{
  /** 房间名册（办公室当前房间的同事） */
  colleagues: any[]
  /** 商机/报价上下文（与 DM 面板同源） */
  context?: AssistantContext | null
  contextSummary?: string
  /** 行为状态文案表（head 名册 presence 提示用） */
  statusMeta?: Record<string, { label?: string; color?: string }>
  /** 办公室实时状态流（useOfficeSocket.statusMap）：名册 presence 点与提示 */
  statusMap?: Record<string, { status?: string; activity?: string }>
}>()

defineEmits<{
  (e: 'open-dm', roleKey: string): void
  (e: 'persona', colleague: any, ev: MouseEvent): void
  (e: 'select-option', value: string, slot?: string): void
  (e: 'submit-selections', selections: Array<{ slot: string; value: string; label?: string; qty?: number }>): void
}>()

const runtime = productionRuntime
const s = ref<ChatSession | null>(null)
const draft = ref('')
const loading = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const { scrollToBottom } = useChatAutoScroll(messagesEl)
/** 引用回复：随下一条用户消息发出（快照由后端截断落库） */
const quoted = ref<{ name: string; text: string } | null>(null)
/** 登录用户身份（人类侧消息：右侧小头像） */
const auth = useAuthStore()
const selfIdentity = computed(() => ({
  name: String((auth.user as any)?.name || '你'),
  avatar_url: String((auth.user as any)?.avatar_url || ''),
}))

const members = computed(() => (Array.isArray(props.colleagues) ? props.colleagues : []))
const leadAuthor = computed(() => {
  const lead = members.value.find((c) => c.role_key === 'assistant') || members.value[0]
  return lead ? { name: lead.name || lead.role_key, avatar_url: lead.avatar_url || '', color: lead.color || '' } : { name: '方案助手', avatar_url: '', color: '' }
})
const thinkingActive = computed(() => !!s.value?.waiting && (!!s.value?.thinkingText || !s.value?.streamingText))

function authorOf(m: AssistantMessage) {
  if (m.role !== 'assistant' || !m.colleague_role_key) return leadAuthor.value
  const c = members.value.find((x) => x.role_key === m.colleague_role_key)
  if (c) return { name: c.name || c.role_key, avatar_url: c.avatar_url || '', color: c.color || '' }
  return { name: m.colleague_role_key, avatar_url: '', color: '' }
}
/** 消息作者完整档案（名片用：职责/工具/手头任务都在成员字典上） */
function colleagueOf(m: AssistantMessage): any {
  return members.value.find((x) => x.role_key === m.colleague_role_key) || null
}
function initialOf(c: any): string {
  const text = String(c?.name || c?.role_key || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}
function isOn(c: any): boolean {
  const st = String(props.statusMap?.[c?.role_key]?.status || '')
  return !!st && st !== 'idle'
}
function statusTextOf(c: any): string {
  const st = String(props.statusMap?.[c?.role_key]?.status || '')
  const label = props.statusMeta?.[st]?.label || st
  const activity = String(props.statusMap?.[c?.role_key]?.activity || '')
  return [label, activity].filter(Boolean).join(' · ') || '空闲'
}

// ── 群会话接线：与浮动面板「团队群」同渠道（productionRuntime 'group'），跨入口同一份状态 ──
async function ensureThread() {
  const session = runtime.session('group')
  s.value = session
  if (session.threadId) {
    if (!runtime.isLive(session)) runtime.attach(session)
    return
  }
  loading.value = true
  session.loading = true
  try {
    const data = await assistantApi.threads.groupResolve({ entry_point: 'ai_office' })
    runtime.setThread(session, data.thread.thread_id)
    const st = await assistantApi.threads.messagesWithState(data.thread.thread_id, 50)
    session.messages = st.messages
    if (st.task_state) applyTaskState(session, st.task_state)
    if (!runtime.isLive(session)) runtime.attach(session)
  } catch {
    antMessage.error('团队群会话加载失败')
  } finally {
    session.loading = false
    loading.value = false
  }
}

async function onSend() {
  const body = draft.value.trim()
  const session = s.value
  if (!body || !session?.threadId || session.sending || session.running) return
  draft.value = ''
  resetTaskUI(session)
  session.sending = true
  session.running = true
  session.streamingText = ''
  clearThinking(session)
  session.waiting = true
  session.error = ''
  try {
    if (!runtime.isLive(session)) runtime.attach(session)
    const res = await assistantApi.threads.postMessage(
      session.threadId,
      body,
      props.contextSummary || undefined,
      'assistant',
      props.context?.opportunityId || null,
      props.context?.quotationId || null,
      'ai_office',
      null,
      null,
      null,
      quoted.value ? { ...quoted.value } : null,
    )
    quoted.value = null
    if (res.user_message) session.messages.push(res.user_message)
  } catch {
    session.waiting = false
    session.streamingText = ''
    session.running = false
    session.error = '发送失败，请稍后重试'
  } finally {
    session.sending = false
  }
}

async function onStop() {
  const session = s.value
  if (!session?.threadId) return
  await runtime.stopTurn(session)
}

// ── 历史会话 / 新建 / 全屏（原型 stage 三件）：与浮动面板共享同一条 group 渠道 ──
const fs = ref(false)
const histOpen = ref(false)
const histItems = ref<AssistantThread[]>([])

async function loadHist() {
  try {
    // 群线程没有 colleague_role_key，同一过滤口径见 AssistantPanel.loadHistory
    histItems.value = ((await assistantApi.threads.list({ includeDeleted: true })) || []).filter(
      (t) => !String(t.colleague_role_key || '').trim(),
    )
  } catch {
    histItems.value = []
  }
}
function toggleHist() {
  histOpen.value = !histOpen.value
  if (histOpen.value) void loadHist()
}

async function openHistThread(t: AssistantThread) {
  const session = s.value
  if (!session || session.sending || session.running) return
  histOpen.value = false
  try {
    let tid = t.thread_id
    if (String(t.deleted_at || '').trim()) {
      // 归档会话恢复：后端自动把当前活跃群会话归档换位
      const restored = await assistantApi.threads.restore(tid)
      tid = restored.thread_id
    }
    if (tid === session.threadId) return
    runtime.setThread(session, tid)
    loading.value = true
    session.loading = true
    try {
      const st = await assistantApi.threads.messagesWithState(tid, 50)
      session.messages = st.messages
      if (st.task_state) applyTaskState(session, st.task_state)
    } finally {
      session.loading = false
      loading.value = false
    }
  } catch {
    antMessage.error('切换会话失败')
  }
}

async function startNewThread() {
  const session = s.value
  if (!session?.threadId || session.sending || session.running) return
  try {
    await assistantApi.threads.remove(session.threadId)
  } catch {
    /* 归档失败不阻断，groupResolve 也会开出新线程 */
  }
  try {
    const data = await assistantApi.threads.groupResolve({ entry_point: 'ai_office' })
    runtime.setThread(session, data.thread.thread_id)
    session.messages = []
  } catch {
    antMessage.error('新建会话失败')
  }
}

function onFsKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && fs.value) fs.value = false
}
onMounted(() => {
  window.addEventListener('keydown', onFsKey)
  void ensureThread()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onFsKey)
})

watch(() => s.value?.messages.length, () => { void nextTick(() => scrollToBottom(true)) })
watch(() => s.value?.streamingText, () => scrollToBottom())
</script>

<style scoped>
.room-chat { position: relative; display: flex; flex-direction: column; height: 100%; min-height: 0; }
.room-head {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border-bottom: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
}
.rh-glyph {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 14%, transparent);
  color: var(--cpq-accent-primary, #1677ff); font-size: 15px; font-weight: 700;
}
.rh-main { flex: 1; min-width: 0; }
.rh-title { font-size: 13.5px; font-weight: 700; display: flex; align-items: center; gap: 6px; }
.rh-chip {
  font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: var(--cpq-radius-full);
  color: var(--cpq-accent-primary, #1677ff);
  background: color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--cpq-accent-primary, #1677ff) 18%, transparent);
}
.rh-sub { font-size: 11.5px; color: var(--cpq-text-muted, #86909c); margin-top: 1px; }
.rh-roster { display: flex; align-items: center; }
.rh-av {
  width: 26px; height: 26px; border-radius: 50%; margin-left: -6px; padding: 0;
  border: 2px solid var(--cpq-bg-card, #fff); cursor: pointer; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 11px; font-weight: 600; opacity: 0.55; transition: opacity 0.15s;
}
.rh-av:first-child { margin-left: 0; }
.rh-av--on { opacity: 1; }
.rh-av img { width: 100%; height: 100%; object-fit: cover; }
.rh-more { font-size: 11px; color: var(--cpq-text-muted, #86909c); margin-left: 6px; }
.room-messages { flex: 1; min-height: 0; overflow-y: auto; padding: 12px 10px; display: flex; flex-direction: column; gap: 12px; }
.room-hint { text-align: center; font-size: 12px; color: var(--cpq-text-muted, #86909c); }
.room-error { font-size: 12px; color: #e5484d; }
/* 引用回复条（composer 上方，原型 composer-quote 同款） */
.room-quote-bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 10px 4px;
  padding: 4px 10px;
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-w4);
  border-left: 2px solid var(--cpq-accent-primary, #1677ff);
  font-size: 12px;
  color: var(--cpq-text-secondary, #4e5969);
}
.rq-text { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rq-x {
  flex: none; border: none; background: transparent;
  color: var(--cpq-text-muted, #86909c); cursor: pointer; font-size: 12px; padding: 0 2px;
}
.rq-x:hover { color: #e5484d; }
/* 房头动作：历史 / 新建 / 全屏 */
.rh-actions { display: flex; align-items: center; gap: 4px; margin-left: 8px; flex-shrink: 0; }
.rh-btn {
  width: 24px; height: 24px; padding: 0; border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-border-light, rgba(22, 119, 255, 0.16));
  background: transparent; color: var(--cpq-text-muted, #86909c);
  font-size: 13px; line-height: 1; cursor: pointer; transition: all 0.15s;
}
.rh-btn:hover { color: var(--cpq-accent-primary, #1677ff); border-color: var(--cpq-accent-primary, #1677ff); }
.rh-btn:disabled { opacity: 0.45; cursor: default; }
/* 会话历史抽屉：房间内浮层，盖在消息区上 */
.room-hist {
  position: absolute; top: 0; right: 0; bottom: 0; width: 240px; z-index: 5;
  display: flex; flex-direction: column;
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-left: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  box-shadow: -8px 0 24px var(--cpq-shadow-color-soft, rgba(22, 119, 255, 0.08));
}
.rhi-head {
  flex: none; display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.06));
}
.rhi-title { font-size: 12.5px; font-weight: 700; color: var(--cpq-text-primary, #1d2129); }
.rhi-list { flex: 1; min-height: 0; overflow-y: auto; padding: 6px; }
.rhi-item {
  display: block; width: 100%; text-align: left; padding: 7px 9px; margin-bottom: 2px;
  border: 1px solid transparent; border-radius: var(--cpq-radius-sm); background: transparent; cursor: pointer;
}
.rhi-item:hover { background: var(--cpq-overlay-w5, rgba(255, 255, 255, 0.05)); }
.rhi-item.active {
  background: var(--cpq-overlay-w5, rgba(255, 255, 255, 0.05));
  border-color: var(--cpq-border-primary, rgba(22, 119, 255, 0.1));
}
.rhi-name {
  display: block; font-size: 12.5px; font-weight: 600; color: var(--cpq-text-primary, #1d2129);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rhi-meta {
  display: flex; gap: 6px; align-items: center; margin-top: 2px;
  font-size: 11px; color: var(--cpq-text-muted, #86909c);
}
.rhi-archived {
  font-size: 10px; padding: 0 5px; border-radius: var(--cpq-radius-full);
  color: var(--cpq-text-muted, #86909c);
  border: 1px solid var(--cpq-border-light, rgba(22, 119, 255, 0.16));
}
.rhi-empty { text-align: center; font-size: 12px; color: var(--cpq-text-muted, #86909c); padding: 18px 0; }
/* 全屏态：Teleport 到 body 的固定层（房间内 backdrop-filter 祖先会吞 fixed，必须出逃） */
.room-chat--fs {
  position: fixed; inset: 0; z-index: 1200; height: 100vh;
  border-radius: 0;
  background: var(--cpq-bg-primary, #08090b);
}
</style>

