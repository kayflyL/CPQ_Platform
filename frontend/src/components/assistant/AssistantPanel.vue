<template>
  <Teleport :disabled="embedded" to="body">
    <transition name="assistant-panel">
      <div v-if="embedded || open" class="assistant-panel" :class="{ 'assistant-panel--embedded': embedded }" :style="panelStyle">
        <!-- header（可拖动）-->
        <div class="ap-header" @mousedown="startDrag">
          <button
            class="ap-role-card"
            type="button"
            :title="preview ? activeColleagueName : '切换 AI 角色'"
            :disabled="preview"
            @mousedown.stop
            @click="toggleRoleMenu"
          >
            <div class="ap-role-avatar" :style="roleAvatarStyle(activeColleague)">
              <img v-if="activeColleague?.avatar_url" :src="activeColleague.avatar_url" alt="" />
              <span v-else class="ap-avatar-initial">{{ avatarInitial(activeColleagueName) }}</span>
            </div>
            <div class="ap-role-meta">
              <div class="ap-role-name">
                <span class="ap-role-dot"></span>
                <span class="ap-role-title">{{ activeColleagueName }}</span>
              </div>
              <div class="ap-role-desc">{{ colleagueDescription(activeColleague) }}</div>
              <div v-if="contextLabel" class="ap-role-ctx">{{ contextLabel }}</div>
            </div>
          </button>
          <div v-if="!preview" class="ap-header-actions" @mousedown.stop>
            <button class="ap-icon-btn" type="button" title="会话历史" @click="toggleHistoryDrawer">
              <MenuOutlined />
            </button>
            <button class="ap-icon-btn ap-close" type="button" title="收起" @click="emit('update:open', false)">
              <CloseOutlined />
            </button>
          </div>
        </div>

        <!-- 角色切换下拉：挂在面板内部，避免 Ant 全局弹层层级问题 -->
        <transition name="ap-menu">
          <div v-if="roleMenuOpen && !preview" class="ap-role-menu" @mousedown.stop>
            <div class="ap-role-menu-head">切换 AI 角色</div>
            <button
              v-for="c in aiColleagues"
              :key="c.role_key"
              type="button"
              class="ap-role-opt"
              :class="{ active: c.role_key === activeRoleKey }"
              @click="chooseRole(c.role_key)"
            >
              <div class="ap-role-avatar sm" :style="roleAvatarStyle(c)">
                <img v-if="c.avatar_url" :src="c.avatar_url" alt="" />
                <span v-else class="ap-avatar-initial">{{ avatarInitial(c.name) }}</span>
              </div>
              <div class="ap-role-opt-main">
                <div class="ap-role-opt-name">{{ c.name || c.role_key }}</div>
                <div class="ap-role-opt-desc">{{ colleagueDescription(c) }}</div>
              </div>
              <CheckOutlined v-if="c.role_key === activeRoleKey" class="ap-role-opt-check" />
            </button>
          </div>
        </transition>

        <!-- 会话历史：内部右侧抽屉，不依赖全局 Drawer -->
        <transition name="ap-drawer">
          <div v-if="historyDrawerOpen && !preview" class="ap-history-drawer" @mousedown.stop>
            <div class="ap-history-mask" @click="historyDrawerOpen = false"></div>
            <aside class="ap-history-panel">
              <div class="ap-history-head">
                <div class="ap-history-title">会话历史</div>
                <button class="ap-new-thread" type="button" :disabled="loading" @click="onNewThread">
                  <PlusOutlined />
                  新对话
                </button>
              </div>
              <div class="ap-history-list">
                <button
                  v-for="t in threads"
                  :key="t.thread_id"
                  type="button"
                  class="ap-thread-item"
                  :class="{ active: t.thread_id === currentThreadId }"
                  @click="chooseThread(t.thread_id)"
                >
                  <div class="ap-thread-main">
                    <div class="ap-thread-title">{{ threadTitle(t) }}</div>
                    <div class="ap-thread-meta">{{ t.msg_count || 0 }} 条 · {{ formatThreadTime(t.updated_at) }}</div>
                  </div>
                  <DeleteOutlined class="ap-thread-del" @click.stop="onDeleteThread(t.thread_id)" />
                </button>
                <div v-if="!threads.length" class="ap-history-empty">暂无会话</div>
              </div>
            </aside>
          </div>
        </transition>

        <!-- 计划进度条：Skill 工作流执行时展示当前/已完成/卡住的步骤（纯对话时隐藏） -->
        <div v-if="nodeTraces.length" class="ap-plan-bar">
          <template v-for="(t, i) in nodeTraces" :key="t.step">
            <span class="ap-plan-step" :class="`ap-plan-step--${t.status}`">
              <span class="ap-plan-dot" />
              <span class="ap-plan-label">{{ t.label }}</span>
              <span v-if="t.artifact" class="ap-plan-artifact">{{ t.artifact.title }}</span>
            </span>
            <span v-if="i < nodeTraces.length - 1" class="ap-plan-arrow">→</span>
          </template>
          <span v-if="waitingAI" class="ap-plan-waiting">等待补充信息…</span>
        </div>

        <!-- 消息列表 -->
        <div class="ap-messages" ref="messagesEl">
          <a-spin v-if="loading" size="small" class="ap-spin" />
          <a-empty
            v-else-if="!messages.length && !streamingText && !waitingAI && !pendingDispatch"
            :image-style="{ height: '48px' }"
            :description="`和${activeColleagueName}聊聊？直接描述服务器配置需求，AI 会自动判断是否进入分析。`"
          />
          <div v-else class="ap-msg-list">
            <template v-for="m in messages" :key="m.message_id">
              <!-- 真实业务产出（需求单/BOM 方案草稿）：文本气泡 + 产出物卡片 -->
              <div v-if="m.kind === 'business_artifact'" class="ap-msg role-assistant ap-msg-result">
                <div class="ap-msg-head">
                  <div
                    class="ap-avatar"
                    :class="{ 'ap-avatar-has-img': !!colleagueForRole(m.colleague_role_key).avatar_url }"
                    :style="{ background: colleagueForRole(m.colleague_role_key).color || 'var(--cpq-accent-primary, #1677ff)' }"
                  >
                    <img v-if="colleagueForRole(m.colleague_role_key).avatar_url" :src="colleagueForRole(m.colleague_role_key).avatar_url" alt="" />
                    <span v-else class="ap-avatar-initial">{{ avatarInitial(colleagueForRole(m.colleague_role_key).name) }}</span>
                  </div>
                  <span class="ap-author">{{ colleagueForRole(m.colleague_role_key).name }}</span>
                </div>
                <div v-if="m.content" class="ap-bubble">{{ m.content }}</div>
                <BusinessArtifactView
                  v-if="artifactFor(m)"
                  :entity-type="artifactFor(m)!.entityType"
                  :entity="artifactFor(m)!.entity"
                  :target="artifactFor(m)!.target"
                  :thread-id="currentThreadId"
                  class="ap-artifact-card"
                />
              </div>
              <!-- 普通消息：与 AI 办公室角色聊天共用公共消息组件 -->
              <AssistantMessageItem
                v-else
                :message="m"
                :author="colleagueForRole(m.colleague_role_key)"
                @select-option="sendText"
              />
            </template>
            <AssistantMessageItem
              v-if="streamingText || waitingAI"
              :message="{ role: 'assistant', content: streamingText || '' }"
              :author="activeColleague || { name: '方案助手', avatar_url: '', color: '' }"
              :streaming="!!streamingText"
              :typing="!streamingText && !thinkingActive"
              :status-text="statusText"
              :thinking="thinkingText"
              :thinking-active="thinkingActive"
            />
          </div>
        </div>

        <!-- 快捷指令：按当前页 provider 条件渲染（需求分析由绑定 Skill 的 AI 角色判断进入） -->
        <div class="ap-quick">
          <button
            v-for="a in visibleQuickActions"
            :key="a.key"
            class="ap-quick-chip"
            :disabled="sending"
            @click="onQuickAction(a)"
          >
            <span>{{ a.label }}</span>
          </button>
        </div>

        <!-- 发送前转接确认：总助识别到更适合处理的 AI 同事 -->
        <div v-if="pendingDispatch" class="ap-dispatch">
          <div class="ap-dispatch-info">
            <div
              class="ap-avatar"
              :class="{ 'ap-avatar-has-img': !!pendingDispatch.colleague?.avatar_url }"
              :style="{ background: pendingDispatch.colleague?.color || 'var(--cpq-accent-primary, #1677ff)' }"
            >
              <img v-if="pendingDispatch.colleague?.avatar_url" :src="pendingDispatch.colleague.avatar_url" alt="" />
              <span v-else class="ap-avatar-initial">{{ avatarInitial(pendingDispatch.colleague?.name || 'AI 同事') }}</span>
            </div>
            <div class="ap-dispatch-text">
              <strong>{{ pendingDispatch.colleague?.name || 'AI 同事' }}</strong>
              <span>这条消息更适合由该同事处理，是否转接？</span>
            </div>
          </div>
          <div class="ap-dispatch-actions">
            <a-button size="small" :disabled="sending" @click="cancelDispatch">仍由总助处理</a-button>
            <a-button type="primary" size="small" :loading="sending" @click="confirmDispatch">确认转接</a-button>
          </div>
        </div>

        <!-- 输入：聊天/自然进入需求分析（由 AI 角色判断调用需求分析 Skill） -->
        <AssistantComposer
          v-model="draft"
          placeholder="输入消息…"
          :disabled="sending || running"
          :sending="sending"
          :running="running"
          @send="onSend"
          @stop="onStop"
        />
      </div>
    </transition>

  </Teleport>
</template>


<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import {
  PlusOutlined, CloseOutlined, DeleteOutlined, MenuOutlined, CheckOutlined,
} from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import { useAssistant } from '@/composables/useAssistant'
import { useAssistantContext, type QuickAction } from '@/composables/assistantContext'
import { useAssistantFab, computePanelAnchor } from '@/composables/useAssistantFab'
import AssistantComposer from '@/components/assistant/AssistantComposer.vue'
import BusinessArtifactView from '@/components/assistant/BusinessArtifactView.vue'
import AssistantMessageItem from '@/components/assistant/AssistantMessageItem.vue'
import { assistantApi } from '@/api/assistant'

const props = withDefaults(defineProps<{
  open: boolean
  embedded?: boolean
  preview?: boolean
  initialRoleKey?: string
  entryPoint?: string
}>(), {
  embedded: false,
  preview: false,
  initialRoleKey: '',
  entryPoint: 'floating_assistant',
})
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const {
  threads, currentThreadId, messages, loading, sending, running, streamingText, thinkingText, waitingAI, statusText, nodeTraces,
  pendingDispatch, confirmDispatch, cancelDispatch,
  loadThreads, selectThread, newThread, send, removeThread, connectWs, disconnectWs,
  activeRoleKey, switchRole, createPreviewThread, destroyPreview, stop,
} = useAssistant(props.entryPoint || 'floating_assistant', {
  preview: props.preview,
  initialRoleKey: props.initialRoleKey || null,
})

const { contextLabel, summarize, visibleQuickActions } = useAssistantContext()

function artifactFor(m: { kind?: string; data?: string }): { entityType: string; entity: any; target?: string } | null {
  if (m.kind !== 'business_artifact' || !m.data) return null
  try {
    const d = JSON.parse(m.data)
    const entity = d?.entity || d?.bom_scheme
    if (!entity || !d?.entity_type) return null
    return { entityType: String(d.entity_type), entity, target: d.target ? String(d.target) : undefined }
  } catch {
    return null
  }
}

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const roleMenuOpen = ref(false)
const historyDrawerOpen = ref(false)

// 技能流程是否运行中（用于画布 input 节点「运行」状态）
const busy = computed(() => waitingAI.value || !!statusText.value || !!streamingText.value)
const thinkingActive = computed(() => waitingAI.value && (!!thinkingText.value || !streamingText.value))

// ── AI 同事身份：群聊式头像/昵称 + 发送前转接确认 ──
const aiColleagues = ref<any[]>([])
async function loadColleagues() {
  try {
    const data = await assistantApi.aiColleagues.list()
    aiColleagues.value = Array.isArray(data.colleagues) ? data.colleagues : []
  } catch {
    aiColleagues.value = []
  }
}
const activeColleague = computed(
  () => aiColleagues.value.find((c) => c.role_key === activeRoleKey.value) || null,
)
const activeColleagueName = computed(() =>
  activeColleague.value?.name || '方案助手',
)
function colleagueForRole(roleKey?: string): {
  name: string
  avatar_url: string
  color?: string
} {
  if (!roleKey) return { name: '方案助手', avatar_url: '', color: '' }
  const found = aiColleagues.value.find((c) => c?.role_key === roleKey)
  if (found) return found
  return { name: roleKey, avatar_url: '', color: '' }
}
function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}
function colleagueDescription(c?: any): string {
  if (!c) return 'AI 员工'
  if (typeof c.description === 'string' && c.description.trim()) return c.description.trim()
  const caps = Array.isArray(c.capabilities) ? c.capabilities : []
  const capText = caps
    .map((x: any) => (typeof x === 'string' ? x : x?.label || x?.name || ''))
    .filter(Boolean)
    .join('、')
  if (capText) return capText
  const skills = Array.isArray(c.skills) ? c.skills : []
  const skillText = skills
    .map((x: any) => (typeof x === 'string' ? x : x?.name || x?.key || ''))
    .filter(Boolean)
    .join('、')
  if (skillText) return skillText
  return 'AI 员工'
}
function roleAvatarStyle(c?: any) {
  return { background: c?.color || 'var(--cpq-accent-primary, #1677ff)' }
}
function threadTitle(t: { title?: string; first_message?: string; thread_id: string }) {
  return t.title?.trim() || t.first_message?.trim() || t.thread_id
}
function formatThreadTime(value?: string) {
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
function toggleRoleMenu() {
  if (props.preview) return
  roleMenuOpen.value = !roleMenuOpen.value
  historyDrawerOpen.value = false
}
function toggleHistoryDrawer() {
  if (props.preview) return
  historyDrawerOpen.value = !historyDrawerOpen.value
  roleMenuOpen.value = false
}
async function chooseRole(roleKey: string) {
  roleMenuOpen.value = false
  if (!roleKey || roleKey === activeRoleKey.value) return
  await switchRole(roleKey)
}
async function chooseThread(id: string) {
  historyDrawerOpen.value = false
  if (id === currentThreadId.value) return
  await selectThread(id)
}

// 面板贴着 FAB 当前位置打开（FAB 拖到哪儿，面板就跟到哪儿附近）
const { pos: fabPos, getFabRect, moveClamped, refitToViewport } = useAssistantFab()
const viewportTick = ref(0)

const panelStyle = computed(() => {
  if (props.embedded) return {}
  // 依赖 fabPos / viewportTick 触发重算（FAB 拖动或窗口缩放时跟着挪）
  void fabPos.value
  void viewportTick.value
  // 窄屏（手机）：面板占满全屏，不再贴 FAB 锚定——像原生 App 的全屏聊天
  if (typeof window !== 'undefined' && window.innerWidth <= 768) {
    return { left: '0px', top: '0px', right: 'auto', bottom: 'auto', width: '100vw', height: '100vh', maxHeight: '100vh' }
  }
  const rect = getFabRect()
  // FAB 还没挂载 / 被隐藏（rect 退化）→ 回落 CSS 默认（右下角），避免面板飞到左上角
  if (!rect || rect.width === 0) return undefined
  // 面板以 FAB 为锚、由 computePanelAnchor 夹进视口；不再叠加额外偏移，杜绝跑出页面/远离按钮
  const { left, top, height } = computePanelAnchor(rect, window.innerWidth, window.innerHeight)
  return {
    left: left + 'px',
    top: top + 'px',
    right: 'auto',
    bottom: 'auto',
    height: height + 'px',
    maxHeight: height + 'px',
  }
})
function onResize() {
  // 视口变小 → 把 FAB 也夹回视口，面板随之重算
  const rect = getFabRect()
  if (rect && rect.width > 0) refitToViewport(rect.width, rect.height)
  viewportTick.value++
}
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (props.embedded && props.preview) {
    destroyPreview()
  }
})

// 拖动逻辑：拖面板 = 同步移动 FAB（夹进视口）。面板以 FAB 为锚 → FAB 不出界面板就不出界，
// 且每次都贴着 FAB 打开（不再有独立持久化偏移把面板拽远/拽出页面）
let dragging = false
let dragStart = { x: 0, y: 0 }
let fabStart = { x: 0, y: 0 }
let fabSize = { w: 120, h: 52 }

function startDrag(e: MouseEvent) {
  // 忽略关闭按钮点击
  if ((e.target as HTMLElement).closest('.ap-close')) return
  const rect = getFabRect()
  if (!rect || rect.width === 0) return
  dragging = true
  dragStart = { x: e.clientX, y: e.clientY }
  fabStart = { x: rect.left, y: rect.top }
  fabSize = { w: rect.width || 120, h: rect.height || 52 }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  // 防止选中文字
  e.preventDefault()
}

function onDrag(e: MouseEvent) {
  if (!dragging) return
  const dx = e.clientX - dragStart.x
  const dy = e.clientY - dragStart.y
  moveClamped(fabStart.x + dx, fabStart.y + dy, fabSize.w, fabSize.h)
}

function stopDrag() {
  if (!dragging) return
  dragging = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

watch(
  () => props.open,
  async (v) => {
    const active = props.embedded || v
    if (active) {
      await Promise.all([loadThreads(), loadColleagues()])
      if (props.embedded && props.preview) {
        await createPreviewThread()
      }
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

async function onSend() {
  const text = draft.value
  if (!text.trim() || sending.value || running.value) return
  draft.value = ''
  await sendText(text)
}

async function onStop() {
  await stop()
}

// 供父组件（SkillStudio 输入节点「运行」）注入文本到真实 AI 对话
async function sendText(text: string) {
  const content = (text || '').trim()
  if (!content || sending.value || running.value) return
  if (props.embedded && props.preview && !currentThreadId.value) {
    await createPreviewThread()
  }
  const summary = await summarize()
  await send(content, summary)
}

defineExpose({ sendText, nodeTraces, busy })

// 快捷指令：prompt 可为函数（动态读配置，如趋势分析）；context 缺省走通用 provider 摘要
async function onQuickAction(action: QuickAction) {
  if (sending.value || running.value) return
  const prompt = typeof action.prompt === 'function' ? await action.prompt() : action.prompt
  const ctx = action.context ? await action.context() : await summarize()
  await send(prompt, ctx)
}

async function onNewThread() {
  if (props.preview) return
  await newThread()
  historyDrawerOpen.value = false
}

function onDeleteThread(id: string) {
  Modal.confirm({
    title: '删除该会话？',
    content: '将移除该会话及其全部消息。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    zIndex: 1800,
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
  width: min(390px, calc(100vw - 32px));
  height: min(680px, calc(100vh - 120px));
  max-height: calc(100vh - 120px);
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(var(--cpq-glass-blur-3, 16px));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3, 16px));
  border: 1px solid var(--cpq-glass-border);
  border-radius: 16px;
  box-shadow: 0 12px 40px var(--cpq-shadow-color-strong, rgba(0, 0, 0, 0.25));
  z-index: 1600;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.assistant-panel--embedded {
  flex: 1;
  min-height: 0;
  position: static;
  right: auto;
  bottom: auto;
  width: 100%;
  height: 100%;
  max-height: none;
  border-radius: 0;
  box-shadow: none;
  border: 0;
  z-index: auto;
}

.assistant-panel--embedded .ap-header {
  cursor: default;
}
.assistant-panel--embedded .ap-role-card {
  cursor: default;
}
.assistant-panel--embedded .ap-role-card:hover {
  background: transparent;
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
.ap-role-select {
  width: 132px;
  flex-shrink: 0;
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

.ap-plan-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--cpq-overlay-w4);
  background: var(--cpq-overlay-a6, rgba(0, 0, 0, 0.03));
  font-size: 12px;
}
.ap-plan-step {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--cpq-overlay-w6);
  color: var(--cpq-text-secondary, #666);
}
.ap-plan-step--done { color: #16a34a; border-color: #16a34a44; background: #16a34a0d; }
.ap-plan-step--running { color: var(--cpq-accent-primary, #1677ff); border-color: var(--cpq-accent-primary, #1677ff); background: #1677ff0d; }
.ap-plan-step--pending { color: var(--cpq-text-muted, #8c8c8c); border-color: var(--cpq-overlay-w10, rgba(255,255,255,.12)); background: transparent; }
.ap-plan-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.ap-plan-step--running .ap-plan-dot { animation: ap-pulse 1s ease-in-out infinite; }
.ap-plan-arrow { color: var(--cpq-text-tertiary, #aaa); }
.ap-plan-artifact { font-size: 11px; opacity: 0.8; }
.ap-plan-waiting { margin-left: auto; color: #b45309; }
@keyframes ap-pulse { 0%, 100% { transform: scale(0.8); opacity: 0.6; } 50% { transform: scale(1.2); opacity: 1; } }

.ap-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  min-height: 0;
}
.ap-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid var(--cpq-overlay-w4);
}
.ap-quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--cpq-overlay-w15);
  border-radius: 999px;
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.ap-quick-chip:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.ap-quick-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
  align-items: flex-start;
  gap: 8px;
}
.ap-msg-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ap-avatar {
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
.ap-avatar-initial {
  line-height: 1;
}
.ap-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ap-author {
  font-size: 12px;
  line-height: 1.2;
  color: var(--cpq-text-muted);
  margin-bottom: 4px;
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
.role-assistant .ap-bubble {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary);
  border: 1px solid var(--cpq-overlay-w6);
  border-bottom-left-radius: 4px;
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

/* ── 发送前转接确认 ── */
.ap-dispatch {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w8);
  background: var(--cpq-accent-soft);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ap-dispatch-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ap-dispatch-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.ap-dispatch-text strong {
  color: var(--cpq-text-primary);
  font-size: 13px;
}
.ap-dispatch-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.ap-input {
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w6);
  display: flex;
  gap: 8px;
  align-items: flex-end;
  background: var(--cpq-overlay-w3);
}

/* ── 需求分析：步骤时间线 ── */
.ap-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 2px 0;
}
.ap-step {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
  white-space: nowrap;
}
.ap-step.st-running {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.ap-step.st-done {
  color: var(--cpq-text-secondary);
}
.ap-step.st-error {
  color: var(--cpq-accent-danger);
  border-color: var(--cpq-accent-danger);
}
/* ── AI 工具调用状态条 ── */
.ap-tool-activity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 2px 0 6px;
}
.ap-tool {
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
.ap-tool .anticon {
  color: var(--cpq-accent-primary);
}
.ap-tool.done .anticon {
  color: var(--cpq-accent-success, #52c41a);
}
.ap-tool-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-tool-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.ap-plan-card {
  max-width: 100%;
}
/* 需求分析结果：文本气泡 + 方案卡纵向堆叠（.ap-msg 默认 row-flex 会把两者并排挤成两栏、且等高拉伸把卡片撑得特别长） */
.ap-msg-result {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}
.ap-bubble.err {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10);
  border-color: var(--cpq-overlay-danger15);
}

/* ── 需求分析：反问回复区 ── */
.ap-reply-footer {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w8);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ap-reply-q {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  white-space: pre-wrap;
}
.ap-format {
  white-space: pre-line;
  padding: 6px 8px;
  background: var(--cpq-overlay-w4);
  border: 1px dashed var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm, 8px);
  color: var(--cpq-text-secondary);
}
.ap-reply-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ap-reply-opt {
  cursor: pointer;
  margin: 0;
}
.ap-reply-input {
  border-radius: var(--cpq-radius-sm, 8px);
}
.ap-reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ── 需求分析：LLM 确认面板 ── */
.ap-confirm-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--cpq-overlay-w8);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 45%;
  overflow-y: auto;
}
.ap-confirm-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-confirm-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-a4);
}
.ap-confirm-item.accepted {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.ap-confirm-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}
.ap-confirm-label { font-weight: 600; color: var(--cpq-text-primary); }
.ap-confirm-tag { margin-inline-end: 0 !important; }
.ap-confirm-v { color: var(--cpq-text-secondary); }
.ap-confirm-v.llm { color: var(--cpq-accent-primary); }
.ap-confirm-conf { color: var(--cpq-text-muted); }
.ap-confirm-opts { display: flex; gap: 6px; flex-shrink: 0; }
.ap-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

/* ── 网页端增强：BOM 弹窗 ── */
.ap-bom-modal-summary {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
  margin-bottom: 12px;
}
/* 弹窗要在方案助手面板(z-index:1500)之上；内容超高时弹窗内部滚动，不撑破视口 */
.ap-bom-modal :deep(.ant-modal-body) {
  max-height: 70vh;
  overflow-y: auto;
}
.ap-quick-chip.primary {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
  font-weight: 600;
}
.ap-quick-chip.primary:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.ap-quick-chip.primary.active {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-primary);
  color: #fff;
}

/* ── 方案助手改版：角色卡 + 内部角色菜单 + 内部会话抽屉 ── */
.ap-header {
  padding: 12px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: move;
  user-select: none;
  background: transparent;
}
.ap-role-card {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border: 0;
  border-radius: 14px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.ap-role-card:hover {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
}
.ap-role-avatar {
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
.ap-role-avatar.sm {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  font-size: 13px;
}
.ap-role-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ap-role-meta {
  min-width: 0;
}
.ap-role-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ap-role-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-accent-success, #22c55e);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
  flex-shrink: 0;
}
.ap-role-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-role-desc {
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-role-ctx {
  margin-top: 3px;
  font-size: 11px;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-header-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.ap-icon-btn {
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
.ap-icon-btn:hover {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.10));
}
.ap-close:hover {
  border-color: var(--cpq-accent-danger);
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10, rgba(255, 77, 79, 0.10));
}

.ap-role-menu {
  position: absolute;
  left: 12px;
  right: 12px;
  top: 66px;
  z-index: 6;
  overflow: hidden;
  border: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.14));
  border-radius: 16px;
  background: var(--cpq-glass-3-bg, rgba(18, 24, 38, 0.96));
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
  max-height: min(320px, calc(100% - 76px));
  overflow-y: auto;
}
.ap-role-menu-head {
  padding: 10px 12px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--cpq-text-muted);
  border-bottom: 1px solid var(--cpq-overlay-w6);
}
.ap-role-opt {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.ap-role-opt:hover {
  background: rgba(59, 130, 246, 0.10);
}
.ap-role-opt.active {
  background: rgba(59, 130, 246, 0.14);
}
.ap-role-opt-main {
  flex: 1;
  min-width: 0;
}
.ap-role-opt-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-role-opt-desc {
  margin-top: 3px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-role-opt-check {
  color: var(--cpq-accent-success, #22c55e);
  font-weight: 700;
}

.ap-history-drawer {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: flex;
  justify-content: flex-end;
}
.ap-history-mask {
  position: absolute;
  inset: 0;
  background: rgba(2, 6, 23, 0.30);
}
.ap-history-panel {
  position: relative;
  width: 86%;
  height: 100%;
  border-left: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.14));
  background: var(--cpq-bg-elevated, #ffffff);
  box-shadow: -20px 0 50px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
}
.ap-history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
}
.ap-history-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}
.ap-new-thread {
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
.ap-new-thread:hover {
  background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.16));
}
.ap-new-thread:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.ap-history-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.ap-thread-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.ap-thread-item:hover {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
}
.ap-thread-item.active {
  background: rgba(59, 130, 246, 0.14);
}
.ap-thread-main {
  flex: 1;
  min-width: 0;
}
.ap-thread-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-thread-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.ap-thread-del {
  color: var(--cpq-text-muted);
  font-size: 13px;
  flex-shrink: 0;
}
.ap-thread-del:hover {
  color: var(--cpq-accent-danger);
}
.ap-history-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.ap-menu-enter-active,
.ap-menu-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.ap-menu-enter-from,
.ap-menu-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
.ap-drawer-enter-active,
.ap-drawer-leave-active {
  transition: opacity 0.18s ease;
}
.ap-drawer-enter-active .ap-history-panel,
.ap-drawer-leave-active .ap-history-panel {
  transition: transform 0.18s ease;
}
.ap-drawer-enter-from,
.ap-drawer-leave-to {
  opacity: 0;
}
.ap-drawer-enter-from .ap-history-panel,
.ap-drawer-leave-to .ap-history-panel {
  transform: translateX(100%);
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

<style>
/* BOM 弹窗是 Teleport 到 body 的 a-modal 内部 DOM，scoped 样式覆盖不到，用全局类收口 */
.ap-bom-modal .ant-modal-body {
  max-height: 70vh;
  overflow-y: auto;
}


</style>
