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
        <SchemeEditor :configs="bomSchemeConfigs" stage="boming" readonly :show-toolbar="false" />
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
</style>
