<template>
  <a-popover
    v-model:open="panelOpen"
    trigger="click"
    placement="bottomRight"
    overlay-class-name="notif-bell-popover"
  >
    <a-badge :count="unreadCount" :overflow-count="99" size="small">
      <a-button type="text" class="bell-btn" title="站内通知">
        <BellOutlined class="bell-icon" />
      </a-button>
    </a-badge>
    <template #content>
      <div class="notif-panel">
        <div class="notif-head">
          <span class="notif-title">通知</span>
          <div class="notif-tabs">
            <button
              v-for="t in TABS"
              :key="t.key"
              class="notif-tab"
              :class="{ on: activeTab === t.key }"
              type="button"
              @click="switchTab(t.key)"
            >
              {{ t.label }}<span v-if="t.key === 'unread' && unreadCount" class="notif-tab-count">{{ unreadCount }}</span>
            </button>
          </div>
          <a-tooltip title="全部标为已读">
            <button class="notif-mark-all" type="button" :disabled="!unreadCount" @click="onMarkAllRead">
              <CheckOutlined />
            </button>
          </a-tooltip>
        </div>

        <div class="notif-list">
          <div v-if="loading" class="notif-empty">加载中…</div>
          <div v-else-if="!notifications.length" class="notif-empty">
            {{ activeTab === 'unread' ? '没有未读通知' : '暂无通知' }}
          </div>
          <div
            v-for="n in notifications"
            :key="n.notification_id"
            class="notif-item"
            :class="{ unread: !n.read_at }"
            @click="onItemClick(n)"
          >
            <span class="notif-icon" :class="notificationMeta(n.type).colorClass">
              <component :is="notificationMeta(n.type).icon" />
            </span>
            <div class="notif-item-main">
              <div class="notif-item-title">{{ n.title }}</div>
              <div v-if="n.body" class="notif-item-body">{{ n.body }}</div>
            </div>
            <div class="notif-item-side">
              <div class="notif-item-time">{{ formatRelativeTime(n.created_at) }}</div>
              <span v-if="!n.read_at" class="notif-unread-dot" />
              <div class="notif-acts" @click.stop>
                <a-tooltip v-if="!n.read_at" title="标为已读">
                  <button class="notif-act" type="button" @click="markRead(n.notification_id).catch(() => {})">
                    <CheckOutlined />
                  </button>
                </a-tooltip>
                <a-tooltip v-else title="删除">
                  <button class="notif-act danger" type="button" @click="removeOne(n.notification_id).catch(() => {})">
                    <DeleteOutlined />
                  </button>
                </a-tooltip>
              </div>
            </div>
          </div>
        </div>

        <div class="notif-foot">
          <a-button size="small" :disabled="!readCount" @click="onClearRead">清空已读</a-button>
          <a-button size="small" type="primary" @click="goAll">查看全部</a-button>
        </div>
      </div>
    </template>
  </a-popover>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { BellOutlined, CheckOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { useNotifications } from '@/composables/useNotifications'
import { notificationMeta } from '@/components/notifications/notificationMeta'
import { formatRelativeTime } from '@/utils/relativeTime'
import type { AppNotification } from '@/api/notifications'

const TABS = [
  { key: 'unread' as const, label: '未读' },
  { key: 'all' as const, label: '全部' },
]

const router = useRouter()
const panelOpen = ref(false)
const activeTab = ref<'unread' | 'all'>('unread')
const loading = ref(false)
const { unreadCount, notifications, start, loadNotifications, markRead, markAllRead, removeOne, clearRead } = useNotifications()

start()

const readCount = computed(() => notifications.value.filter((n) => n.read_at).length)

watch(panelOpen, (open) => {
  if (open) load(1)
})

async function load(page: number) {
  loading.value = true
  try {
    await loadNotifications(page, activeTab.value === 'unread')
  } catch {
    /* 静默 */
  } finally {
    loading.value = false
  }
}

async function switchTab(tab: 'unread' | 'all') {
  if (activeTab.value === tab) return
  activeTab.value = tab
  await load(1)
}

async function onItemClick(n: AppNotification) {
  if (!n.read_at) markRead(n.notification_id).catch(() => {})
  if (n.opportunity_id) {
    panelOpen.value = false
    router.push(`/opportunities/${encodeURIComponent(n.opportunity_id)}`)
  }
}

async function onMarkAllRead() {
  try {
    await markAllRead()
    if (activeTab.value === 'unread') await load(1)
  } catch {
    /* 静默 */
  }
}

async function onClearRead() {
  try {
    await clearRead()
  } catch {
    /* 静默 */
  }
}

function goAll() {
  panelOpen.value = false
  router.push('/notifications')
}
</script>

<style scoped>
.bell-btn {
  color: var(--cpq-text-secondary) !important;
  font-size: 16px;
  display: inline-flex;
  align-items: center;
}
.bell-btn:hover {
  color: var(--cpq-accent-primary) !important;
}
.bell-btn:hover .bell-icon {
  animation: bell-ring 0.9s ease-in-out;
  transform-origin: top center;
  display: inline-block;
}
@keyframes bell-ring {
  0%, 100% { transform: rotate(0); }
  15% { transform: rotate(12deg); }
  30% { transform: rotate(-12deg); }
  45% { transform: rotate(6deg); }
  60% { transform: rotate(-6deg); }
  75% { transform: rotate(2deg); }
}
.notif-panel {
  width: 372px;
  display: flex;
  flex-direction: column;
  margin: -4px -8px;
}
.notif-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}
.notif-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-size: 14px;
}
.notif-tabs {
  display: flex;
  gap: 2px;
  background: var(--cpq-bg-secondary);
  border-radius: 8px;
  padding: 2px;
}
.notif-tab {
  height: 26px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  background: none;
  font-size: 12px;
  color: var(--cpq-text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}
.notif-tab.on {
  background: var(--cpq-bg-card);
  color: var(--cpq-accent-primary);
  font-weight: 600;
  box-shadow: var(--cpq-shadow-sm, 0 2px 8px rgba(22, 119, 255, 0.06));
}
.notif-tab-count {
  font-size: 10.5px;
  background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.1));
  border-radius: 999px;
  padding: 0 6px;
}
.notif-mark-all {
  margin-left: auto;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 7px;
  background: none;
  color: var(--cpq-accent-primary);
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.notif-mark-all:disabled {
  color: var(--cpq-text-quaternary);
  cursor: default;
}
.notif-list {
  overflow-y: auto;
  max-height: 336px;
}
.notif-empty {
  padding: 32px 0;
  text-align: center;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}
.notif-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-bg-secondary);
  cursor: pointer;
  align-items: flex-start;
  transition: background 0.15s;
}
.notif-item:hover {
  background: var(--cpq-overlay-a4, rgba(22, 119, 255, 0.04));
}
.notif-item.unread .notif-item-title {
  color: var(--cpq-text-primary);
  font-weight: 600;
}
.notif-icon {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.notif-icon.i-blue { background: var(--cpq-notif-blue-bg); color: var(--cpq-notif-blue); }
.notif-icon.i-green { background: var(--cpq-notif-green-bg); color: var(--cpq-notif-green); }
.notif-icon.i-red { background: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.notif-icon.i-amber { background: var(--cpq-notif-amber-bg); color: var(--cpq-notif-amber); }
.notif-icon.i-violet { background: var(--cpq-notif-violet-bg); color: var(--cpq-notif-violet); }
.notif-icon.i-cyan { background: var(--cpq-notif-cyan-bg); color: var(--cpq-notif-cyan); }
.notif-item-main {
  flex: 1;
  min-width: 0;
}
.notif-item-title {
  font-size: 13px;
  color: var(--cpq-text-secondary);
  line-height: 1.4;
}
.notif-item-body {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  opacity: 0.75;
  margin-top: 2px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notif-item-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}
.notif-item-time {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.notif-unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-accent-primary);
}
.notif-acts {
  display: none;
  gap: 4px;
}
.notif-item:hover .notif-acts {
  display: inline-flex;
}
.notif-act {
  width: 22px;
  height: 22px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 6px;
  background: var(--cpq-bg-elevated);
  color: var(--cpq-text-secondary);
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.notif-act.danger {
  color: var(--cpq-notif-red);
}
.notif-act:hover {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
}
.notif-act.danger:hover {
  border-color: var(--cpq-notif-red);
  color: var(--cpq-notif-red);
}
.notif-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-top: 1px solid var(--cpq-border-secondary);
}
</style>

<style>
/* popover 浮层挂在 body 下，需全局覆盖内边距 */
.notif-bell-popover .ant-popover-inner-content {
  padding: 8px;
}
</style>
