<template>
  <div class="activity-stream glass">
    <div class="section-header">
      <h3>活动 / 备注</h3>
      <span class="section-hint">关键节点 + 简短备注(完整协作在右侧动态)</span>
    </div>
    <div class="stream-body">
      <a-empty v-if="!recent.length" :image-style="{ height: '40px' }" description="暂无活动,加一条备注吧" />
      <div v-else class="act-list">
        <div v-for="m in recent" :key="m.message_id" class="act-item" :class="`kind-${m.kind}`">
          <span class="act-dot"></span>
          <div class="act-content">
            <div v-if="m.body" class="act-body">{{ m.body }}</div>
            <div class="act-meta">
              <span class="act-author">{{ m.kind === 'system' ? '系统' : (m.author_name || '匿名') }}</span>
              <span>·</span>
              <span>{{ formatTime(m.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="stream-input">
      <a-input
        v-model:value="draft"
        placeholder="加一条备注…"
        :disabled="posting"
        @press-enter="post"
      />
      <a-button type="primary" size="small" :loading="posting" :disabled="!draft.trim()" @click="post">
        备注
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { message } from 'ant-design-vue'
import { feedApi } from '@/api/feed'
import type { FeedMessage } from '@/api/feed'

const props = defineProps<{ opportunityId: string; messages: FeedMessage[] }>()

const draft = ref('')
const posting = ref(false)

const recent = computed(() =>
  [...(props.messages || [])]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 30)
)

async function post() {
  const body = draft.value.trim()
  if (!body) return
  posting.value = true
  try {
    await feedApi.messages.create(props.opportunityId, body)
    draft.value = ''
  } catch {
    message.error('备注失败')
  } finally {
    posting.value = false
  }
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<style scoped>
.activity-stream {
  padding: 16px 20px;
  margin-bottom: 24px;
}
.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.section-hint { font-size: 12px; color: var(--cpq-text-muted); }
.stream-body {
  max-height: 280px;
  overflow-y: auto;
  padding: 4px 0;
}
.act-list { display: flex; flex-direction: column; gap: 4px; }
.act-item {
  display: flex; gap: 10px;
  padding: 7px 12px; border-radius: 8px;
  transition: background var(--cpq-transition-fast);
}
.act-item:hover { background: var(--cpq-overlay-w3); }
.act-dot {
  width: 7px; height: 7px; border-radius: 50%;
  margin-top: 6px; flex-shrink: 0;
  background: var(--cpq-accent-primary);
}
.act-item.kind-system .act-dot { background: var(--cpq-text-muted); }
.act-item.kind-system .act-body { color: var(--cpq-text-secondary); font-style: italic; }
.act-content { flex: 1; min-width: 0; }
.act-body {
  font-size: 13px; color: var(--cpq-text-primary);
  line-height: 1.5; word-break: break-word;
}
.act-meta {
  display: flex; gap: 5px;
  font-size: 11px; color: var(--cpq-text-muted); margin-top: 2px;
}
.act-author { font-weight: 500; }
.stream-input {
  display: flex; gap: 8px;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--cpq-overlay-w6);
}
</style>
