<template>
  <div class="oel-panel">
    <div class="oel-toolbar">
      <a-radio-group v-model:value="filter" size="small">
        <a-radio-button value="all">全部</a-radio-button>
        <a-radio-button value="autonomous">作息</a-radio-button>
        <a-radio-button value="pipeline">任务</a-radio-button>
        <a-radio-button value="chat">对话</a-radio-button>
        <a-radio-button value="system">系统</a-radio-button>
      </a-radio-group>
      <span class="oel-live">● 实时 · 20s 自动刷新</span>
      <a-button size="small" :loading="loading" @click="load">刷新</a-button>
    </div>
    <div class="oel-list">
      <div v-for="(ev, i) in filtered" :key="ev.id ?? `${ev.role_key}-${ev.ts}-${i}`" class="oel-row">
        <span class="oel-time">{{ timeOf(ev) }}</span>
        <span class="oel-dot" :style="{ background: colorOf(ev) }" />
        <div class="oel-body">
          <span class="oel-who">{{ nameOf(ev) }}</span>
          <span class="oel-what">{{ ev.activity || ev.status || '' }}</span>
          <span v-if="ev.message" class="oel-say">{{ ev.message }}</span>
        </div>
        <a-tag :color="tagColor(ev)" class="oel-tag">{{ tagText(ev) }}</a-tag>
      </div>
      <div v-if="!filtered.length" class="oel-empty">暂无事件</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { officeApi, type OfficeEventItem } from '@/api/office'

const props = defineProps<{
  colleagues?: Array<{ role_key?: string; name?: string; color?: string }>
}>()

const events = ref<OfficeEventItem[]>([])
const filter = ref('all')
const loading = ref(false)
let timer = 0

async function load() {
  loading.value = true
  try {
    const res = await officeApi.officeEvents(60)
    events.value = res.events || []
  } catch {
    /* 静默：日志是辅助面板 */
  } finally {
    loading.value = false
  }
}

const filtered = computed(() =>
  events.value.filter((ev) => {
    const source = ev.source || 'system'
    if (filter.value === 'all') return true
    if (filter.value === 'chat') return ['chat', 'user', 'assistant'].includes(source)
    return source === filter.value
  }),
)

function timeOf(ev: OfficeEventItem): string {
  const ts = ev.ts ? ev.ts * 1000 : Date.parse(ev.created_at || '')
  if (!ts || Number.isNaN(ts)) return '--:--'
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function nameOf(ev: OfficeEventItem): string {
  const colleague = props.colleagues?.find((c) => c.role_key === ev.role_key)
  return colleague?.name || ev.role_key || '—'
}

function colorOf(ev: OfficeEventItem): string {
  return props.colleagues?.find((c) => c.role_key === ev.role_key)?.color || '#93a3ba'
}

function tagText(ev: OfficeEventItem): string {
  const source = ev.source || 'system'
  if (source === 'autonomous') return '作息'
  if (source === 'pipeline') return '任务'
  if (source === 'system') return '系统'
  return '对话'
}

function tagColor(ev: OfficeEventItem): string {
  const source = ev.source || 'system'
  if (source === 'autonomous') return 'blue'
  if (source === 'pipeline') return 'red'
  if (source === 'system') return 'cyan'
  return 'green'
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 20000)
})

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.oel-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.oel-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.oel-live {
  font-size: 11px;
  color: var(--cpq-notif-green, #2f9d78);
  margin-right: auto;
}
.oel-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}
.oel-row {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  background: var(--cpq-glass-1-bg, var(--cpq-overlay-w5, rgba(255, 255, 255, 0.4)));
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.3));
  border-radius: 11px;
  padding: 7px 11px;
}
.oel-time {
  font-size: 10.5px;
  color: var(--cpq-text-muted);
  font-family: ui-monospace, Consolas, monospace;
  flex: none;
  margin-top: 2px;
}
.oel-dot { width: 7px; height: 7px; border-radius: 50%; flex: none; margin-top: 6px; }
.oel-body { flex: 1; min-width: 0; }
.oel-who { font-size: 12px; font-weight: 600; margin-right: 6px; color: var(--cpq-text-primary); }
.oel-what { font-size: 11.5px; color: var(--cpq-text-secondary); }
.oel-say { display: block; font-size: 11.5px; color: var(--cpq-text-muted); font-style: italic; }
.oel-tag { margin-right: 0; flex: none; }
.oel-empty { text-align: center; color: var(--cpq-text-muted); font-size: 12px; padding: 18px 0; }
</style>
