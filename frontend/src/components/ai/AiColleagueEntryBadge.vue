<template>
  <div v-if="matchedColleagues.length" class="ace-badges">
    <div
      v-for="colleague in matchedColleagues"
      :key="colleague.role_key"
      class="ace-badge"
      :title="colleague.opening_message || colleague.name"
    >
      <span
        class="ace-avatar"
        :style="{ background: colleague.color || 'var(--cpq-accent-primary, #1677ff)' }"
      >
        <img v-if="colleague.avatar_url" :src="colleague.avatar_url" alt="" class="ace-avatar-img" />
        <span v-else class="ace-avatar-initial">{{ avatarInitial(colleague.name) }}</span>
      </span>
      <div class="ace-meta">
        <div class="ace-name">{{ colleague.name }}</div>
        <div class="ace-desc">{{ colleague.system_prompt || colleague.opening_message || '当前入口 AI 同事' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const colleagues = ref<any[]>([])

function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}

async function loadColleagues() {
  try {
    const { data } = await axios.get('/api/ai-colleagues/')
    colleagues.value = Array.isArray(data.colleagues) ? data.colleagues : []
  } catch {
    colleagues.value = []
  }
}

const matchedColleagues = computed(() =>
  colleagues.value.filter((c) => {
    if (c?.enabled === false) return false
    const entryPoints = Array.isArray(c?.entry_points) ? c.entry_points : []
    return entryPoints.includes(route.name)
  }),
)

onMounted(loadColleagues)
</script>

<style scoped>
.ace-badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.ace-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 420px;
  padding: 4px 10px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 999px;
  background: var(--cpq-glass-3-bg, rgba(255, 255, 255, 0.65));
  color: var(--cpq-text-primary);
  overflow: hidden;
}
.ace-avatar {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.ace-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ace-avatar-initial {
  line-height: 1;
}
.ace-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.ace-name {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ace-desc {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
