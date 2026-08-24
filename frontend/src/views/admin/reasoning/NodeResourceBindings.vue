<template>
  <div class="node-resource-bindings">
    <section class="nrb-section nrb-card">
      <div class="nrb-section-title">数据来源</div>
      <a-select
        v-if="dataSourcesEnabled"
        v-model:value="dataModel"
        mode="multiple"
        :options="dataSourceSelectOptions"
        placeholder="选择本节点可使用的数据来源"
        style="width:100%"
      />
      <div v-else class="nrb-disabled">当前节点不使用数据来源</div>
      <p class="nrb-hint">决定本节点执行时可读取的真实业务数据；默认 <code>server_catalog</code>。</p>
    </section>

    <section class="nrb-section nrb-card">
      <div v-if="!rulesEnabled" class="nrb-section-title">规则</div>
      <RuleCatalogRef
        v-if="rulesEnabled"
        v-model="ruleModel"
        :available="ruleAvailable"
        :defaults="ruleDefaults"
      />
      <div v-else class="nrb-disabled">当前节点不使用规则目录</div>
    </section>

    <section v-if="toolsEnabled" class="nrb-section nrb-card">
      <div class="nrb-section-title">可用工具</div>
      <a-select
        v-model:value="toolModel"
        mode="multiple"
        :options="toolOptions"
        placeholder="选择该节点可调用的工具"
        style="width:100%"
      />
      <div v-if="showMaxIterations" class="nrb-field">
        <span class="nrb-field-label">最多执行步数</span>
        <a-input-number v-model:value="maxIterationsModel" :min="1" :max="20" style="width:100%" />
      </div>
      <p class="nrb-hint">工具列表来自全系统 AI 工具目录，不由节点写死；可多选、可清空。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import RuleCatalogRef from './RuleCatalogRef.vue'
import { RULE_TYPE_OPTIONS, type RuleType } from '@/api/requirementRules'

const props = withDefaults(defineProps<{
  dataSources?: string[]
  ruleTypes?: RuleType[]
  tools?: string[]
  dataSourceOptions?: Array<{ key: string; description?: string }>
  toolOptions?: Array<{ value: string; label: string }>
  ruleAvailable?: RuleType[]
  ruleDefaults?: RuleType[]
  dataSourcesEnabled?: boolean
  rulesEnabled?: boolean
  toolsEnabled?: boolean
  showMaxIterations?: boolean
  maxIterations?: number
}>(), {
  dataSources: () => [],
  ruleTypes: () => [],
  tools: () => [],
  dataSourceOptions: () => [],
  toolOptions: () => [],
  ruleAvailable: () => RULE_TYPE_OPTIONS.map((o) => o.value),
  ruleDefaults: () => [],
  dataSourcesEnabled: true,
  rulesEnabled: true,
  toolsEnabled: true,
  showMaxIterations: false,
  maxIterations: 6,
})

const emit = defineEmits<{
  'update:dataSources': [string[]]
  'update:ruleTypes': [RuleType[]]
  'update:tools': [string[]]
  'update:maxIterations': [number]
}>()

const dataModel = computed({
  get: () => props.dataSources,
  set: (value: string[]) => emit('update:dataSources', value || []),
})
const ruleModel = computed({
  get: () => props.ruleTypes,
  set: (value: RuleType[]) => emit('update:ruleTypes', value || []),
})
const toolModel = computed({
  get: () => props.tools,
  set: (value: string[]) => emit('update:tools', value || []),
})
const maxIterationsModel = computed({
  get: () => props.maxIterations,
  set: (value: number) => emit('update:maxIterations', Number(value) || 6),
})

const dataSourceSelectOptions = computed(() =>
  props.dataSourceOptions.map((item) => ({
    value: item.key,
    label: item.key,
    title: item.description || item.key,
  })),
)
</script>

<style scoped>
.node-resource-bindings { display: flex; flex-direction: column; gap: 18px; }
.nrb-section { display: flex; flex-direction: column; gap: 8px; }
.nrb-card {
  padding: 14px 15px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 12px;
  background: var(--cpq-glass-2-bg);
  box-shadow: var(--cpq-shadow-sm);
}
.nrb-section-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.nrb-field { display: flex; flex-direction: column; gap: 6px; }
.nrb-field-label { font-size: 12px; color: var(--cpq-text-secondary); }
.nrb-hint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--cpq-text-muted); }
.nrb-disabled { padding: 9px 11px; border: 1px dashed var(--cpq-border-color, rgba(255, 255, 255, 0.18)); border-radius: 9px; font-size: 12px; color: var(--cpq-text-muted); }
</style>
