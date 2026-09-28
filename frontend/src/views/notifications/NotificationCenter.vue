<template>
  <div class="nc-page">
    <header class="nc-head">
      <div>
        <h1 class="nc-title">通知中心</h1>
        <p class="nc-sub">共 {{ total }} 条 · {{ unreadCount }} 条未读</p>
      </div>
      <div class="nc-ops">
        <a-button :disabled="!total || !readInPage" @click="onClearRead">清空已读</a-button>
        <a-button type="primary" :disabled="!unreadCount" @click="onMarkAllRead">全部标为已读</a-button>
      </div>
    </header>

    <div class="nc-filters">
      <div class="nc-toggle">
        <button class="nc-toggle-btn" :class="{ on: mode === 'all' }" type="button" @click="setMode('all')">全部</button>
        <button class="nc-toggle-btn" :class="{ on: mode === 'unread' }" type="button" @click="setMode('unread')">
          未读<template v-if="unreadCount"> ({{ unreadCount }})</template>
        </button>
      </div>
      <button
        v-for="g in NOTIFICATION_GROUPS"
        :key="g.key"
        class="nc-chip"
        :class="{ on: activeGroups.has(g.key) }"
        type="button"
        @click="toggleGroup(g.key)"
      >
        <span class="nc-chip-dot" :class="`dot-${g.key}`" />
        {{ g.label }}
        <span v-if="groupCounts[g.key]" class="nc-chip-count">{{ groupCounts[g.key] }}</span>
      </button>
    </div>

    <a-spin :spinning="loading">
      <div v-if="!loading && !groups.length" class="nc-empty">
        <BellOutlined class="nc-empty-icon" />
        <p>{{ mode === 'unread' ? '没有未读通知' : '暂无通知' }}</p>
      </div>

      <section v-for="g in groups" :key="g.label" class="nc-group">
        <div class="nc-group-label">{{ g.label }}</div>
        <div
          v-for="n in g.items"
          :key="n.notification_id"
          class="nc-row"
          :class="{ unread: !n.read_at }"
          @click="onItemClick(n)"
        >
          <span class="nc-icon" :class="notificationMeta(n.type).colorClass">
            <component :is="notificationMeta(n.type).icon" />
          </span>
          <div class="nc-main">
            <div class="nc-row-title">
              {{ n.title }}
              <span class="nc-row-tag">{{ notificationMeta(n.type).label }}</span>
            </div>
            <div v-if="n.body" class="nc-row-body">{{ n.body }}</div>
          </div>
          <div class="nc-side">
            <div class="nc-row-time">
              <span v-if="!n.read_at" class="nc-unread-dot" />
              {{ formatRelativeTime(n.created_at) }}
            </div>
            <div class="nc-acts" @click.stop>
              <template v-if="!n.read_at">
                <a-button size="small" @click.stop="markRead(n.notification_id).catch(() => {})">标已读</a-button>
              </template>
              <template v-else>
                <a-popconfirm title="删除这条通知？" @confirm="removeOne(n.notification_id).catch(() => {})">
                  <a-button size="small" danger @click.stop>删除</a-button>
                </a-popconfirm>
              </template>
              <a-button v-if="n.opportunity_id" size="small" type="link" @click.stop="goOpp(n)">进入商机</a-button>
            </div>
          </div>
        </div>
      </section>
    </a-spin>

    <div v-if="total > pageSize" class="nc-pager">
      <a-pagination
        :current="page"
        :total="total"
        :page-size="pageSize"
        :show-size-changer="false"
        size="small"
        @change="setPage"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 通知中心全量页（/notifications）— 铃铛 popover 的「查看全部」落地页。
 * 列表/筛选/分页自持状态（走 REST）；未读徽标数与 WS 实时态复用 useNotifications 单例。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { BellOutlined } from '@ant-design/icons-vue'
import { useNotifications } from '@/composables/useNotifications'
import { NOTIFICATION_GROUPS, groupUnread, notificationMeta } from '@/components/notifications/notificationMeta'
import { formatRelativeTime, dayGroupLabel } from '@/utils/relativeTime'
import { notificationsApi } from '@/api/notifications'
import type { AppNotification } from '@/api/notifications'
import type { NotificationGroupKey } from '@/components/notifications/notificationMeta'

const router = useRouter()
const { unreadCount, unreadByType, start, markRead, markAllRead, removeOne, clearRead } = useNotifications()

const PAGE_SIZE = 20
const pageSize = PAGE_SIZE
const loading = ref(false)
const items = ref<AppNotification[]>([])
const total = ref(0)
const page = ref(1)
const mode = ref<'all' | 'unread'>('all')
const activeGroups = reactive(new Set<NotificationGroupKey>())

const groupCounts = computed(() => groupUnread(unreadByType.value))
const readInPage = computed(() => items.value.some((n) => n.read_at))

const groups = computed(() => {
  if (!items.value.length) return []
  const out: { label: string; items: AppNotification[] }[] = []
  for (const n of items.value) {
    const label = dayGroupLabel(n.created_at)
    const bucket = out.find((g) => g.label === label)
    if (bucket) bucket.items.push(n)
    else out.push({ label, items: [n] })
  }
  return out
})

onMounted(() => {
  start()
  reload()
})

async function reload() {
  loading.value = true
  try {
    const types = activeGroups.size
      ? NOTIFICATION_GROUPS.filter((g) => activeGroups.has(g.key)).flatMap((g) => g.types)
      : undefined
    const res = await notificationsApi.list(page.value, PAGE_SIZE, mode.value === 'unread', types)
    items.value = res.notifications
    total.value = res.total
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function resetAndReload() {
  page.value = 1
  reload()
}

function setMode(m: 'all' | 'unread') {
  if (mode.value === m) return
  mode.value = m
  resetAndReload()
}

function toggleGroup(key: NotificationGroupKey) {
  if (activeGroups.has(key)) activeGroups.delete(key)
  else activeGroups.add(key)
  resetAndReload()
}

function setPage(p: number) {
  page.value = p
  reload()
}

async function onMarkAllRead() {
  try {
    await markAllRead()
    await reload()
  } catch { /* 静默 */ }
}

async function onClearRead() {
  try {
    await clearRead()
    await reload()
  } catch { /* 静默 */ }
}

async function onItemClick(n: AppNotification) {
  goOpp(n)
}

function goOpp(n: AppNotification) {
  if (!n.opportunity_id) return
  if (!n.read_at) markRead(n.notification_id).catch(() => {})
  router.push(`/opportunities/${encodeURIComponent(n.opportunity_id)}`)
}
</script>

<style scoped>
.nc-page {
  max-width: 880px;
  margin: 0 auto;
  padding: 20px 20px 40px;
}
.nc-head {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 14px;
}
.nc-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}
.nc-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--cpq-text-muted);
}
.nc-ops {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.nc-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.nc-toggle {
  display: flex;
  background: var(--cpq-bg-secondary);
  border-radius: 8px;
  padding: 2px;
}
.nc-toggle-btn {
  height: 28px;
  padding: 0 14px;
  border: 0;
  border-radius: 7px;
  background: none;
  font-size: 12.5px;
  color: var(--cpq-text-secondary);
  cursor: pointer;
}
.nc-toggle-btn.on {
  background: var(--cpq-bg-card);
  color: var(--cpq-accent-primary);
  font-weight: 600;
  box-shadow: var(--cpq-shadow-sm, 0 2px 8px rgba(22, 119, 255, 0.06));
}
.nc-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--cpq-border-secondary);
  background: var(--cpq-bg-card);
  font-size: 12.5px;
  color: var(--cpq-text-secondary);
  cursor: pointer;
}
.nc-chip.on {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-overlay-a20, rgba(22, 119, 255, 0.2));
  font-weight: 600;
}
.nc-chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 3px;
}
.nc-chip-count {
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.dot-todo { background: var(--cpq-notif-blue); }
.dot-approval { background: var(--cpq-notif-amber); }
.dot-activity { background: var(--cpq-notif-green); }
.nc-empty {
  padding: 64px 0;
  text-align: center;
  color: var(--cpq-text-secondary);
  font-size: 13px;
}
.nc-empty-icon {
  font-size: 34px;
  color: var(--cpq-text-quaternary);
  margin-bottom: 10px;
}
.nc-empty p {
  margin: 0;
}
.nc-group {
  margin-bottom: 8px;
}
.nc-group-label {
  font-size: 12px;
  color: var(--cpq-text-muted);
  font-weight: 600;
  padding: 8px 4px 6px;
}
.nc-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--cpq-bg-card);
  border: 1px solid var(--cpq-border-secondary);
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.nc-row:hover {
  border-color: var(--cpq-overlay-a20, rgba(22, 119, 255, 0.2));
  box-shadow: var(--cpq-shadow-sm, 0 2px 8px rgba(22, 119, 255, 0.06));
}
.nc-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  flex-shrink: 0;
}
.nc-icon.i-blue { background: var(--cpq-notif-blue-bg); color: var(--cpq-notif-blue); }
.nc-icon.i-green { background: var(--cpq-notif-green-bg); color: var(--cpq-notif-green); }
.nc-icon.i-red { background: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.nc-icon.i-amber { background: var(--cpq-notif-amber-bg); color: var(--cpq-notif-amber); }
.nc-icon.i-violet { background: var(--cpq-notif-violet-bg); color: var(--cpq-notif-violet); }
.nc-icon.i-cyan { background: var(--cpq-notif-cyan-bg); color: var(--cpq-notif-cyan); }
.nc-main {
  flex: 1;
  min-width: 0;
}
.nc-row-title {
  font-size: 13.5px;
  color: var(--cpq-text-secondary);
  line-height: 1.4;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.nc-row.unread .nc-row-title {
  color: var(--cpq-text-primary);
  font-weight: 600;
}
.nc-row-tag {
  font-size: 10.5px;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--cpq-bg-tertiary);
  color: var(--cpq-text-muted);
}
.nc-row-body {
  font-size: 12.5px;
  color: var(--cpq-text-secondary);
  opacity: 0.75;
  margin-top: 3px;
  line-height: 1.5;
}
.nc-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}
.nc-row-time {
  font-size: 11.5px;
  color: var(--cpq-text-muted);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.nc-unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-accent-primary);
}
.nc-acts {
  display: inline-flex;
  gap: 6px;
  visibility: hidden;
}
.nc-row:hover .nc-acts {
  visibility: visible;
}
.nc-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
@media (max-width: 768px) {
  .nc-page { padding: 12px 12px 32px; }
  .nc-head { flex-wrap: wrap; gap: 8px; }
  .nc-title { font-size: 17px; }
  .nc-ops { margin-left: 0; width: 100%; }
  .nc-ops .ant-btn { flex: 1; }
  .nc-row { flex-wrap: wrap; gap: 9px; }
  .nc-side {
    width: 100%;
    margin-left: 46px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  /* 触屏无 hover：操作按钮常显 */
  .nc-acts { visibility: visible; }
  .nc-pager { justify-content: center; }
}
</style>
