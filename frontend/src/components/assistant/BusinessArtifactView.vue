<template>
  <div class="ba-artifact" :class="'ba-' + entityType">
    <div class="ba-head">
      <span class="ba-badge">{{ entityLabel }}</span>
      <span class="ba-title">{{ artifactTitle }}</span>
      <span v-if="statusLabel" class="ba-status">{{ statusLabel }}</span>
    </div>
    <div v-if="!inline && summaryText" class="ba-summary">{{ summaryText }}</div>

    <div v-if="entityType === 'model_candidates'" class="ba-body ba-candidates">
      <div v-for="(cand, i) in candidates" :key="String(cand.server_model_id ?? i)" class="ba-cand-row">
        <ServerModelCard
          :model="toModel(cand)"
          :show-base-config="false"
          :show-lifecycle="true"
          clickable
          @click="goConfigure(cand)"
        />
        <div v-if="cand.selling_points || cand.recommend_level || cand.fallback_note || cand.match_stage" class="ba-cand-note">
          {{ cand.selling_points || cand.recommend_level || cand.fallback_note || cand.match_stage }}
        </div>
        <a-button size="small" type="primary" block @click.stop="goConfigure(cand)">去配置这台服务器</a-button>
      </div>
    </div>

    <div v-if="inline" class="ba-body">
      <template v-if="entityType === 'bom_scheme'">
        <div class="ba-scheme-editor">
          <SchemeEditor
            :configs="configs"
            stage="boming"
            readonly
            :show-toolbar="false"
          />
        </div>
      </template>
      <template v-else-if="entityType === 'requirement'">
        <div class="ba-requirement-text">{{ requirementText || '（无需求文本）' }}</div>
        <table v-if="slotRows.length" class="ba-table">
          <thead><tr><th>字段</th><th>内容</th></tr></thead>
          <tbody><tr v-for="(row, i) in slotRows" :key="i"><td>{{ row.label }}</td><td>{{ row.value }}</td></tr></tbody>
        </table>
      </template>
      <template v-else-if="entityType !== 'model_candidates'">
        <pre class="ba-raw">{{ JSON.stringify(entity, null, 2) }}</pre>
      </template>
    </div>

    <div v-if="!inline && entityType !== 'model_candidates'" class="ba-actions">
      <a-button size="small" type="link" @click="open = true">查看详情</a-button>
    </div>

    <a-modal
      v-if="!inline && entityType !== 'model_candidates'"
      v-model:open="open"
      :title="artifactTitle"
      :footer="null"
      width="min(1180px, calc(100vw - 24px))"
      :z-index="1800"
      :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
      class="ba-modal"
    >
      <template v-if="entityType === 'bom_scheme'">
        <div class="ba-scheme-editor">
          <SchemeEditor
            :configs="configs"
            stage="boming"
            readonly
            :show-toolbar="false"
          />
        </div>
      </template>
      <template v-else-if="entityType === 'requirement'">
        <div class="ba-requirement-text">{{ requirementText || '（无需求文本）' }}</div>
        <table v-if="slotRows.length" class="ba-table">
          <thead><tr><th>字段</th><th>内容</th></tr></thead>
          <tbody><tr v-for="(row, i) in slotRows" :key="i"><td>{{ row.label }}</td><td>{{ row.value }}</td></tr></tbody>
        </table>
      </template>
      <template v-else>
        <pre class="ba-raw">{{ JSON.stringify(entity, null, 2) }}</pre>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import ServerModelCard from '@/components/common/ServerModelCard.vue'
import { assistantApi } from '@/api/assistant'

const props = defineProps<{
  entityType: string
  entity: any
  inline?: boolean
  threadId?: string | null
}>()

const open = ref(false)
const router = useRouter()

const entityLabel = computed(() => {
  if (props.entityType === 'bom_scheme') return 'BOM 方案'
  if (props.entityType === 'requirement') return '需求单'
  if (props.entityType === 'model_candidates') return '候选机型'
  return '业务产出'
})
const artifactTitle = computed(() => {
  if (props.entityType === 'bom_scheme') return props.entity?.name || 'AI BOM 方案草稿'
  if (props.entityType === 'requirement') return '需求单草稿'
  if (props.entityType === 'model_candidates') return '候选机型'
  return '业务产出物'
})
const statusLabel = computed(() => {
  const s = props.entity?.status
  if (s === 'draft') return '草稿'
  if (s === 'current') return '当前'
  if (s === 'archived') return '已归档'
  return ''
})
const configs = computed<any[]>(() => {
  const list = props.entity?.configs
  return Array.isArray(list) ? list : []
})
const requirementText = computed(() => props.entity?.requirement_text || '')
const summaryText = computed(() => {
  if (props.entityType === 'bom_scheme') {
    const count = configs.value.length
    return count ? count + ' 个配置页签' : '已生成 BOM 方案草稿'
  }
  if (props.entityType === 'requirement') {
    return requirementText.value ? requirementText.value.slice(0, 120) : '已保存需求单草稿'
  }
  return ''
})
const candidates = computed<any[]>(() => {
  const list = props.entity?.candidates
  return Array.isArray(list) ? list : []
})
function toModel(c: any): any {
  return {
    id: c.server_model_id,
    name: c.name,
    use: c.use,
    description: c.description,
    image_url: c.image_url,
    lifecycle_status: c.lifecycle_status,
    is_published: c.is_published,
    base_config: c.base_config || null,
    product_content: c.product_content || null,
  }
}
function goConfigure(c: any): void {
  const id = c.server_model_id
  if (id) {
    router.push('/servers/config/' + id)
    if (props.threadId) {
      assistantApi.threads.selfConfig(props.threadId, id).catch(() => {})
    }
  }
}
const slotRows = computed(() => {
  const slots = props.entity?.slots
  if (!slots || typeof slots !== 'object') return []
  const simple = Object.entries(slots).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length))
  return simple.map(([k, v]) => ({ label: k, value: typeof v === 'object' ? JSON.stringify(v) : String(v) }))
})

</script>

<style scoped>
.ba-artifact {
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid var(--cpq-border-secondary, #e5e6eb);
  border-radius: 10px;
  background: var(--cpq-bg-card, #ffffff);
}
.ba-head { display: flex; align-items: center; gap: 8px; }
.ba-badge { font-size: 12px; color: var(--cpq-accent-primary, #1677ff); background: var(--cpq-overlay-a10, #e8f3ff); padding: 2px 8px; border-radius: 999px; }
.ba-title { font-weight: 600; color: var(--cpq-text-primary); }
.ba-status { margin-left: auto; font-size: 12px; color: var(--cpq-text-muted, #86909c); }
.ba-summary { margin-top: 6px; font-size: 13px; color: var(--cpq-text-secondary, #4e5969); }
.ba-actions { margin-top: 6px; }
.ba-body { margin-top: 8px; }
.ba-candidates { display: flex; flex-direction: column; gap: 12px; }
.ba-cand-row { display: flex; flex-direction: column; gap: 6px; }
.ba-cand-note { font-size: 12px; color: var(--cpq-text-muted, #86909c); }
.ba-scheme-editor { min-height: 220px; }
.ba-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }
.ba-table th, .ba-table td { border: 1px solid var(--cpq-border-secondary, #f0f0f0); padding: 4px 8px; text-align: left; color: var(--cpq-text-primary); }
.ba-table th { background: var(--cpq-bg-tertiary, #fafafa); }
.ba-requirement-text { white-space: pre-wrap; margin-bottom: 10px; color: var(--cpq-text-primary); }
.ba-raw { white-space: pre-wrap; font-size: 12px; color: var(--cpq-text-secondary); }
</style>
