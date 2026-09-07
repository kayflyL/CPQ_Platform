<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import { useNodeArtifact } from '@/composables/useNodeArtifact'

import RequirementForm from '@/components/flow/RequirementForm.vue'
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

watch([artifact, reqRef], async ([a]) => {
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
// 机箱表 = 基础机箱 L6（该机型 BOM 模板求值，与方案配置页 L6 部分同源同形状）
// 列由目标层定义驱动（artifact.data.columns），无定义时回退默认列
const l6Cols = computed(() => {
  const cols = Array.isArray(artifactData.value?.columns) ? artifactData.value.columns : []
  const ant = cols.map((c: any) => ({ title: c.label || c.key, dataIndex: c.key, key: c.key }))
  return ant.length ? ant : [
    { title: '配置件', dataIndex: 'catalogue', key: 'catalogue' },
    { title: '说明', dataIndex: 'description', key: 'description' },
    { title: '数量', dataIndex: 'qty', key: 'qty', width: 64 },
  ]
})
const kpTableCols = computed(() => {
  const cols = Array.isArray(artifactData.value?.columns) ? artifactData.value.columns : []
  const ant = cols.map((c: any) => ({ title: c.label || c.key, dataIndex: c.key, key: c.key }))
  return ant.length ? ant : kpCols
})
const kpCols = [
  { title: 'Catalogue', dataIndex: 'part_category', key: 'part_category', width: 120 },
  { title: 'Configuration Description', dataIndex: 'catalogue', key: 'catalogue' },
  { title: 'Quantity', dataIndex: 'qty', key: 'qty', width: 90 },
]
const kpRows = computed(() => {
  const rows = Array.isArray(artifactData.value?.rows) ? artifactData.value.rows : []
  return rows
})
const unmatchedRows = computed(() => {
  const list = Array.isArray(artifactData.value?.unmatched) ? artifactData.value.unmatched : []
  return list
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
      <div v-if="artifactData?.note" class="artifact-hint">{{ artifactData.note }}</div>
      <a-table v-if="Array.isArray(artifactData?.rows) && artifactData.rows.length" :data-source="artifactData.rows" :columns="l6Cols" size="small" :row-key="(_: any, i: number) => i" :pagination="false" />
      <div v-else class="artifact-empty">暂无机箱表数据。</div>
    </template>

    <template v-else-if="artifact?.kind === 'kp_table'">
      <div v-if="artifactData?.summary" class="artifact-hint">KP 落地 {{ artifactData.summary.kp_count ?? 0 }} 项，未命中 {{ artifactData.summary.unmatched_count ?? 0 }} 项，规格偏差 {{ artifactData.summary.spec_mismatch_count ?? 0 }} 项</div>
      <a-table v-if="kpRows.length" :data-source="kpRows" :columns="kpTableCols" size="small" :row-key="(_: any, i: number) => i" :pagination="false" :row-class-name="(record: any) => (record.unmatched ? 'kp-row-unmatched' : '')" />
      <div v-else class="artifact-empty">暂无明显配件数据。</div>
      <div v-if="unmatchedRows.length" class="artifact-unmatched">
        <div class="artifact-unmatched-title">未匹配 / 待确认（未能从配件库锁定真实料号，不作 KP 配置表行）</div>
        <ul class="artifact-unmatched-list">
          <li v-for="(u, i) in unmatchedRows" :key="i">
            <span class="artifact-unmatched-cat">{{ u.category || '未分类' }}</span>
            <span v-if="u.description" class="artifact-unmatched-desc">（{{ u.description }}）</span>
            <span class="artifact-unmatched-qty">× {{ u.qty ?? 1 }}</span>
          </li>
        </ul>
      </div>
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
:deep(.kp-row-unmatched td) { color: var(--cpq-text-muted); font-style: italic; }
.artifact-unmatched { margin-top: 10px; padding: 8px 12px; border: 1px dashed var(--cpq-border-color, #d9d9d9); border-radius: 6px; background: var(--cpq-bg-secondary, #fafafa); }
.artifact-unmatched-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; color: var(--cpq-text-warning, #d48806); }
.artifact-unmatched-list { margin: 0; padding: 0 0 0 16px; font-size: 12px; color: var(--cpq-text-secondary); line-height: 20px; }
.artifact-unmatched-cat { font-weight: 600; }
.artifact-unmatched-desc { color: var(--cpq-text-muted); }
.artifact-unmatched-qty { margin-left: 6px; color: var(--cpq-text-muted); }
</style>
