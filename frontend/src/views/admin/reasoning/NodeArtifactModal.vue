<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import { useNodeArtifact } from '@/composables/useNodeArtifact'

const RequirementForm = defineAsyncComponent(() => import('@/components/flow/RequirementForm.vue'))
const { artifact, close } = useNodeArtifact()
const props = defineProps<{ bomScheme?: any }>()

const open = computed({
  get: () => !!artifact.value,
  set: (v: boolean) => { if (!v) close() },
})

const reqRef = ref<{ fromSlots: (slots: Record<string, any>) => void } | null>(null)
const requirementText = ref('')
const bomSchemeConfigs = computed(() => Array.isArray(props.bomScheme?.configs) ? props.bomScheme.configs : [])

function normalizeRequirementSlots(data: any) {
  const d = data && typeof data === 'object' ? data : {}
  return {
    ...d,
    server_type: d.server_type_name || d.server_type || '',
    platform_type: d.series || d.platform_type || '',
    chassis_form: d.form || d.chassis_form || '',
  }
}

watch(artifact, async (a) => {
  requirementText.value = (a?.data && typeof a.data === 'object' && a.data.requirement_text)
    || (a?.input && typeof a.input === 'object' && a.input.requirement_text)
    || (a?.output && typeof a.output === 'object' && a.output.requirement_text)
    || ''
  if (a?.kind === 'requirement_slots') {
    await nextTick()
    reqRef.value?.fromSlots(normalizeRequirementSlots(a.data || {}))
  }
}, { immediate: true })

const artifactData = computed(() => artifact.value?.data)
const l6Cols = [
  { title: '件名', dataIndex: 'catalogue', key: 'catalogue' },
  { title: '料号 · 规格', dataIndex: 'description', key: 'description' },
  { title: '数量', dataIndex: 'qty', key: 'qty', width: 64 },
]
const kpCols = [
  { title: '类别', dataIndex: 'category', key: 'category', width: 96 },
  { title: '型号', dataIndex: 'name', key: 'name' },
  { title: '规格', dataIndex: 'description', key: 'description' },
  { title: '数量', dataIndex: 'qty', key: 'qty', width: 64 },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', width: 110 },
  { title: '状态', key: 'status', width: 130 },
]
const kpRows = computed(() => {
  const rows = Array.isArray(artifactData.value?.rows) ? artifactData.value.rows : []
  return rows.map((r: any) => ({
    ...r,
    status: r.unmatched ? ('未命中：' + (r.unmatched_reason || '库内无对应件')) : (r.spec_mismatch ? '规格偏差' : '匹配'),
  }))
})
</script>

<template>
  <a-modal
    v-model:open="open"
    :title="artifact?.title || '节点产出物'"
    :footer="null"
    width="min(1180px, calc(100vw - 24px))"
    :z-index="1800"
    :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
  >
    <template v-if="artifact?.kind === 'bom_scheme'">
      <div v-if="bomScheme" class="artifact-scheme">
        <SchemeEditor :configs="bomSchemeConfigs" readonly :show-toolbar="false" />
      </div>
      <div v-else class="artifact-empty">BOM 方案尚未生成完整实体，请重新试运行。</div>
    </template>

    <template v-else-if="artifact?.kind === 'requirement_slots'">
      <RequirementForm v-if="artifact" ref="reqRef" v-model:req-text="requirementText" readonly />
    </template>

    <template v-else-if="artifact?.kind === 'requirement_missing'">
      <div class="missing-title">待补充字段</div>
      <a-tag v-for="(f, i) in artifactData?.missing_fields || []" :key="i" style="margin-right:8px">{{ f }}</a-tag>
    </template>

    <template v-else-if="artifact?.kind === 'model_choice'">
      <pre class="artifact-raw">{{ JSON.stringify(artifactData, null, 2) }}</pre>
    </template>

    <template v-else-if="artifact?.kind === 'parts_proposal'">
      <pre class="artifact-raw">{{ JSON.stringify(artifactData, null, 2) }}</pre>
    </template>

    <template v-else-if="artifact?.kind === 'plans'">
      <div class="plans-count">共 {{ artifactData?.plans_count ?? 0 }} 个方案</div>
      <pre class="artifact-raw">{{ JSON.stringify(artifactData, null, 2) }}</pre>
    </template>

    <template v-else-if="artifact?.kind === 'l6_chassis'">
      <div v-if="artifactData?.chosen" class="artifact-hint">锁定机型：{{ artifactData.chosen }}</div>
      <div v-if="artifactData?.reason" class="artifact-hint">推荐理由：{{ artifactData.reason }}</div>
      <a-table v-if="Array.isArray(artifactData?.rows) && artifactData.rows.length" :data-source="artifactData.rows" :columns="l6Cols" size="small" :row-key="(_: any, i: number) => i" :pagination="false" />
      <div v-else class="artifact-empty">暂无机箱表数据。</div>
    </template>

    <template v-else-if="artifact?.kind === 'kp_table'">
      <div v-if="artifactData?.summary" class="artifact-hint">KP 落地 {{ artifactData.summary.kp_count ?? 0 }} 项，未命中 {{ artifactData.summary.unmatched_count ?? 0 }} 项，规格偏差 {{ artifactData.summary.spec_mismatch_count ?? 0 }} 项</div>
      <a-table v-if="kpRows.length" :data-source="kpRows" :columns="kpCols" size="small" :row-key="(_: any, i: number) => i" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'unit_price'"><span>¥{{ (record.unit_price ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span></template>
          <template v-else-if="column.key === 'status'"><a-tag :color="record.unmatched ? 'red' : (record.spec_mismatch ? 'orange' : 'green')">{{ record.status }}</a-tag></template>
        </template>
      </a-table>
      <div v-else class="artifact-empty">暂无明显配件数据。</div>
    </template>

    <template v-else>
      <pre class="artifact-raw">{{ JSON.stringify(artifactData, null, 2) }}</pre>
    </template>
  </a-modal>
</template>

<style scoped>
.artifact-empty { color: var(--cpq-text-muted); font-size: 13px; padding: 12px 0; }
.artifact-scheme { min-height: 220px; }
.artifact-raw { white-space: pre-wrap; font-size: 12px; color: var(--cpq-text-secondary); }
.missing-title { font-weight: 600; margin-bottom: 8px; }
.plans-count { font-weight: 600; margin-bottom: 8px; }
.artifact-hint { font-weight: 600; margin-bottom: 8px; color: var(--cpq-text-secondary); }
</style>
