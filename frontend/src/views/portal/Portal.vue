<script setup lang="ts">
/**
 * 统一门户 (/portal) —— AI-first 工作台。
 *
 * 布局：单列纵向，两态联动。
 * - 空闲态：欢迎语 + 快捷磁贴 + 输入框居中；发消息后切换为聊天态。
 * - 聊天态：整块复用浮动窗口 AssistantPanel（inset 内嵌），左联系人栏 + 右动作栏
 *           与浮动窗口完全一致；改一处两边同步。
 *
 * 门户只做布局 + 接线，复用 useAssistant；门户持有唯一实例（provide 给入口，
 * 并以 prop 传给 AssistantPanel），保证消息/线程/WS 与浮动窗口同源。
 */
import { ref, computed, provide, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useAssistant } from '@/composables/useAssistant'
import { PORTAL_ASSISTANT_KEY } from '@/components/portal/portalAssistant'
import PortalAIInput from '@/components/portal/PortalAIInput.vue'
import AssistantPanel from '@/components/assistant/AssistantPanel.vue'

const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.can('page.opportunities_all'))

// 门户持有唯一实例，provide 给 PortalAIInput，也传给 AssistantPanel（保证线程连续）
const assistant = useAssistant()
const { colleagues, activeRoleKey, loadThreads, disconnectWs } = assistant
provide(PORTAL_ASSISTANT_KEY, assistant)

// 聊天态开关：发送首条自动开，点「收起」手动关。空闲态 = !chatOpen。
const chatOpen = ref(false)
const onChatOpen = () => { chatOpen.value = true }
const onCollapse = () => { chatOpen.value = false }

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

// 进入门户：拉可聊角色与会话列表，让空闲态欢迎语/头像显示正确角色
onMounted(async () => {
  try { await loadThreads() } catch { /* ignore */ }
})

// 离开门户断 WS（聊天态收起时保持实例与 WS，重开即续上文）
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
</script>

<template>
  <div class="portal" :class="{ 'is-chat': chatOpen }">
    <main class="portal-main">
      <!-- 空闲态：欢迎语 + 快捷磁贴 + 输入（发消息后切换为聊天态） -->
              <PortalAIInput
          v-if="!chatOpen"
          key="idle"
          class="portal-ai"
          @open="onChatOpen"
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

        <!-- 聊天态：整块复用浮动聊天窗口（同一 useAssistant 实例，自动带左联系人栏 + 右动作栏） -->
        <AssistantPanel
          v-else
          key="chat"
          inset
          :open="true"
          :assistant="assistant"
          @update:open="onCollapse"
        />
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

/* PortalAIInput 空闲态：流式 flex 子项，靠自身 align-items 居中 */
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
}
</style>
