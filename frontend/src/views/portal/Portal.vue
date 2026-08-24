<script setup lang="ts">
/**
 * 统一门户 (/portal) —— AI-first 工作台。
 *
 * 布局（2026-08-14 重做，定调见 memory: portal-ai-shell-pluggable）：
 * 单列纵向，输入框位置驱动两态联动——
 * - 空闲态：输入框居中（不撑满）+ 下方磁贴快捷入口（Win10 风格，无图标）
 * - 聊天态：发送首条后输入框自动滑到底部，上方长出消息流 + 会话记录条，
 *           磁贴隐藏；点「收起」手动回到空闲态
 *
 * 门户是壳，AI 能力可插拔；门户只做布局 + 接线，复用 useAssistant，零新逻辑。
 *
 * 关键：门户持有唯一 useAssistant 实例（provide/inject），PortalAIInput 复用，
 * 否则切会话不联动（useAssistant 非单例，每次调用返回独立 refs）。
 */
import { ref, computed, provide, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Modal } from 'ant-design-vue'
import { useAuthStore } from '@/store/auth'
import { useAssistant } from '@/composables/useAssistant'
import { PORTAL_ASSISTANT_KEY } from '@/components/portal/portalAssistant'
import PortalAIInput from '@/components/portal/PortalAIInput.vue'

const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.can('page.opportunities_all'))

// 门户持有唯一实例，provide 给 PortalAIInput
const assistant = useAssistant()
const {
  threads, currentThreadId,
  selectThread, newThread, removeThread, connectWs, disconnectWs,
  colleagues, activeRoleKey, loadThreads,
} = assistant
provide(PORTAL_ASSISTANT_KEY, assistant)

// 聊天态开关：发送首条自动开，点「收起」手动关。空闲态 = !chatOpen。
const chatOpen = ref(false)

function onChatOpen() { chatOpen.value = true }
function onCollapse() { chatOpen.value = false }

const assistantName = computed(() =>
  colleagues.value.find((c) => c.role_key === activeRoleKey.value)?.name || '方案助手',
)
const activeColleague = computed(() =>
  colleagues.value.find((c) => c.role_key === activeRoleKey.value) || null,
)
function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

// 进入门户：拉可聊角色与对应会话列表（供「会话记录条」）
onMounted(async () => {
  try { await loadThreads() } catch { /* ignore */ }
})

// ── 会话记录条动作 ──
async function onNewThread() {
  await newThread()
  if (currentThreadId.value) connectWs(currentThreadId.value)
  nextTick(focusComposer)
}
async function onSelect(id: string) {
  await selectThread(id)
  connectWs(id)
  chatOpen.value = true
  nextTick(focusComposer)
}
function onDelete(id: string) {
  Modal.confirm({
    title: '删除该会话？',
    content: '将移除该会话及其全部消息。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => { await removeThread(id) },
  })
}
function focusComposer() {
  const el = document.querySelector('.pai-input') as HTMLTextAreaElement | null
  el?.focus()
}

// 离开门户断 WS（AssistantPanel 关闭同处理）
onUnmounted(() => disconnectWs())

// ── 快捷入口磁贴（无图标，纯文字层级；映射真实路由，按权限可见） ──
interface QuickEntry { key: string; title: string; desc: string; to: string; perm: string; roles?: string[] }
const ENTRIES: QuickEntry[] = [
  { key: 'business', title: '我的商机', desc: '业务发起、跟踪自己创建的商机', to: '/portal/workstation/business', perm: 'page.opportunities', roles: ['business'] },
  { key: 'te', title: '需求任务', desc: '技术支持查看待配 BOM 需求', to: '/portal/workstation/te', perm: 'page.opportunities', roles: ['te'] },
  { key: 'cost', title: '成本任务', desc: '成本核算查看待核价任务', to: '/portal/workstation/cost', perm: 'page.opportunities', roles: ['cost'] },
  { key: 'quote', title: '报价任务', desc: '报价专员查看待转报价任务', to: '/portal/workstation/quote', perm: 'page.opportunities', roles: ['quote'] },
  { key: 'dispatch', title: '任务调度', desc: '管理员配置/转交处理人', to: '/portal/workstation/dispatch', perm: 'page.opportunities', roles: ['admin'] },
]
const visibleEntries = computed(() => ENTRIES.filter((e) => auth.can(e.perm) && (!e.roles || isAdmin.value || e.roles.includes(auth.user?.role || ''))))
function enter(e: QuickEntry) { router.push(e.to) }

// 会话记录条折叠开关
const railOpen = ref(false)
</script>

<template>
  <div class="portal" :class="{ 'is-chat': chatOpen }">
    <!-- ── 聊天态：顶部会话记录条（默认收起，点开浮层） ── -->
    <div class="portal-railbar">
      <template v-if="chatOpen">
        <button class="railbar-toggle" :class="{ open: railOpen }" @click="railOpen = !railOpen">
          会话记录 <span class="railbar-count" v-if="threads.length">{{ threads.length }}</span>
          <span class="railbar-caret">{{ railOpen ? '▴' : '▾' }}</span>
        </button>
        <transition name="rail">
          <div v-if="railOpen" class="railbar-panel glass">
            <button class="railbar-new" @click="onNewThread">+ 新对话</button>
            <div class="railbar-list">
              <button
                v-for="t in threads"
                :key="t.thread_id"
                class="railbar-item"
                :class="{ active: t.thread_id === currentThreadId }"
                @click="onSelect(t.thread_id)"
              >
                <span class="railbar-title">{{ t.title || '新会话' }}</span>
                <span
                  class="railbar-del"
                  title="删除"
                  @click.stop="onDelete(t.thread_id)"
                >×</span>
              </button>
              <p v-if="!threads.length" class="railbar-empty">暂无历史会话</p>
            </div>
          </div>
        </transition>
      </template>
    </div>

    <!-- ── 主体 ── -->
    <main class="portal-main">
      <!-- 唯一实例：空闲态开场（欢迎语+磁贴 经 intro slot + composer 居中），聊天态消息流+composer 占满 -->
      <PortalAIInput
        class="portal-ai"
        :chat-open="chatOpen"
        @open="onChatOpen"
        @collapse="onCollapse"
      >
        <template #intro>
          <header class="pl-greet">
            <div
              class="pl-avatar"
              :class="{ 'pl-avatar-has-img': !!activeColleague?.avatar_url }"
              :style="{ background: activeColleague?.color || 'var(--cpq-accent-primary, #1677ff)' }"
            >
              <img v-if="activeColleague?.avatar_url" :src="activeColleague.avatar_url" alt="" />
              <span v-else>{{ avatarInitial(assistantName) }}</span>
            </div>
            <h1 class="pl-title">你好，需要我帮你做什么？</h1>
            <p class="pl-sub">{{ assistantName || '方案助手' }} · 你的 AI 工作搭档</p>
          </header>
        </template>
        <template #below>
          <div v-if="visibleEntries.length" class="pl-entries-grid">
            <button
              v-for="e in visibleEntries"
              :key="e.key"
              class="entry-tile"
              @click="enter(e)"
            >
              <span class="entry-title">{{ e.title }}</span>
              <span class="entry-desc">{{ e.desc }}</span>
            </button>
          </div>
        </template>
      </PortalAIInput>
    </main>
  </div>
</template>

<style scoped>
.portal {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* ── 顶部会话记录条（仅聊天态） ── */
.portal-railbar {
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  height: 42px;
  border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  padding: 0 16px;
  z-index: 5;
}
.railbar-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--cpq-text-secondary);
  background: none; border: none; cursor: pointer;
  padding: 4px 8px; border-radius: var(--cpq-radius-sm);
  transition: background 0.15s;
}
.railbar-toggle:hover { background: var(--cpq-overlay-w8); color: var(--cpq-text-primary); }
.railbar-count {
  font-size: 11px; color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w8); border-radius: 999px;
  padding: 0 6px; line-height: 16px;
}
.railbar-caret { font-size: 10px; color: var(--cpq-text-muted); }

.railbar-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 12px;
  width: 280px;
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-glass-border-strong);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow-hover);
  padding: 10px;
  z-index: 20;
}
.railbar-new {
  margin-bottom: 8px;
  padding: 9px;
  border-radius: var(--cpq-radius-md);
  border: 1px dashed var(--cpq-glass-border-strong);
  background: transparent;
  color: var(--cpq-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.railbar-new:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
.railbar-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 4px;
}
.railbar-item {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; text-align: left;
  padding: 9px 10px; margin: 2px 0;
  border-radius: var(--cpq-radius-sm);
  border: none; background: transparent;
  cursor: pointer; transition: background 0.15s;
}
.railbar-item:hover { background: var(--cpq-overlay-w8); }
.railbar-item.active { background: var(--cpq-overlay-w12); }
.railbar-title {
  font-size: 13px; color: var(--cpq-text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.railbar-item.active .railbar-title { font-weight: 600; }
.railbar-del {
  flex-shrink: 0; width: 18px; height: 18px; line-height: 16px; text-align: center;
  border-radius: 50%; color: var(--cpq-text-muted); font-size: 14px;
  opacity: 0; transition: opacity 0.15s;
}
.railbar-item:hover .railbar-del { opacity: 1; }
.railbar-del:hover { background: var(--cpq-color-danger, #ff4d4f); color: #fff; }
.railbar-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 12px; }

/* 浮层展开/收起过渡 */
.rail-enter-active, .rail-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.rail-enter-from, .rail-leave-to {
  opacity: 0; transform: translateY(-6px);
}

/* ── 主体 ── */
.portal-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* PortalAIInput 永远是流式 flex 子项：
   空闲态靠自身 align-items 居中并只露 composer；聊天态占满主体 */
.portal-ai {
  flex: 1;
  min-height: 0;
}

/* 空闲态开场内容（经 PortalAIInput 的 intro slot 渲染，居中流的一部分） */
.pl-greet { text-align: center; }
.pl-avatar {
  width: 56px;
  height: 56px;
  margin: 0 auto;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: #fff;
  font-size: 24px;
  font-weight: 700;
  border: 1px solid var(--cpq-glass-border);
  box-shadow: 0 0 28px var(--cpq-overlay-a40);
}
.pl-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.pl-title {
  font-size: 24px; font-weight: 700; color: var(--cpq-text-primary);
  margin: 14px 0 6px;
}
.pl-sub { font-size: 13px; color: var(--cpq-text-muted); margin: 0; }

/* 磁贴网格（Win10 风格，无图标，纯文字层级） */
.pl-entries-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  width: 100%;
}
.entry-tile {
  display: flex; flex-direction: column; align-items: flex-start; gap: 4px;
  padding: 14px 16px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  cursor: pointer; text-align: left;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.entry-tile:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-2px);
  box-shadow: var(--cpq-glass-card-shadow-hover);
}
.entry-title { font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.entry-desc { font-size: 12px; color: var(--cpq-text-muted); }

/* 手机端 */
@media (max-width: 768px) {
  .pl-title { font-size: 20px; }
  .pl-entries-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .entry-tile { padding: 12px 14px; }
  .entry-title { font-size: 13px; }
  .railbar-panel { left: 8px; right: 8px; width: auto; }
}
</style>
