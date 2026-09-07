<template>
  <div class="node-resource-bindings">
    <section v-if="toolsEnabled" class="nrb-section nrb-card">
      <div class="nrb-section-title">可用工具</div>
      <div v-if="lockedTools.length" class="nrb-locked-block">
        <span class="nrb-field-label">机制必需（节点机制依赖，不可取消）</span>
        <div class="nrb-tool-tags">
          <span v-for="tool in lockedToolOptions" :key="tool.value" class="nrb-tool-tag nrb-tool-tag--locked">🔒 {{ tool.label }}</span>
        </div>
      </div>
      <a-select
        v-if="!toolsReadonly"
        v-model:value="toolModel"
        mode="multiple"
        :options="selectableOptions"
        placeholder="选择该节点可调用的增强工具"
        style="width:100%"
      />
      <div v-else-if="readonlyToolOptions.length" class="nrb-tool-tags">
        <span v-for="tool in readonlyToolOptions" :key="tool.value" class="nrb-tool-tag">{{ tool.label }}</span>
      </div>
      <div v-if="selectedDataSources.length" class="nrb-field">
        <span class="nrb-field-label">本节点将查询的数据源</span>
        <div class="nrb-data-source-list">
          <span v-for="source in selectedDataSources" :key="source" class="nrb-data-source-tag">{{ source }}</span>
        </div>
        <p class="nrb-hint">数据源由已选工具自动派生，不由节点单独填写。</p>
      </div>
      <p v-if="toolsReadonly" class="nrb-hint">工具由节点类型固定，避免误选导致链路失效；数据源由工具自动派生。</p>
      <p v-else class="nrb-hint">工具真源 = 此处勾选（存 DB，运行期按此执行）；机制工具锁定不可取消，增强工具可自由增删。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  tools?: string[]
  toolOptions?: Array<{ value: string; label: string; dataSources?: string[] }>
  toolsEnabled?: boolean
  toolsReadonly?: boolean
  /** 机制工具：节点机制必需，锁定勾选不可取消（后端也会保底补回） */
  lockedTools?: string[]
}>(), {
  tools: () => [],
  toolOptions: () => [],
  toolsEnabled: true,
  toolsReadonly: false,
  lockedTools: () => [],
})

const emit = defineEmits<{
  'update:tools': [string[]]
}>()

const findOption = (name: string) => props.toolOptions.find((o) => String(o.value) === name)
const toOption = (name: string) => {
  const found = findOption(name)
  return { value: name, label: found?.label || name, dataSources: found?.dataSources || [] }
}

const lockedToolOptions = computed(() => (props.lockedTools || []).map(toOption))

/** 可编辑的增强工具 = 勾选集 − 机制工具（机制工具不可被勾选操作增删） */
const toolModel = computed({
  get: () => (props.tools || []).filter((t) => !(props.lockedTools || []).includes(String(t))),
  set: (value: string[]) => emit('update:tools', (value || []).filter((t) => !(props.lockedTools || []).includes(String(t)))),
})

const selectableOptions = computed(() =>
  props.toolOptions.filter((o) => !(props.lockedTools || []).includes(String(o.value))))

const readonlyToolOptions = computed(() => (props.tools || []).map((t) => toOption(String(t))))

const selectedDataSources = computed(() => {
  const selected = new Set([...(props.tools || []), ...(props.lockedTools || [])].map((t) => String(t)))
  const sources = new Set<string>()
  for (const option of props.toolOptions) {
    if (!selected.has(option.value)) continue
    for (const source of option.dataSources || []) {
      if (source) sources.add(source)
    }
  }
  return [...sources].sort()
})

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
.nrb-locked-block { display: flex; flex-direction: column; gap: 6px; }
.nrb-data-source-list { display: flex; flex-wrap: wrap; gap: 6px; }
.nrb-tool-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.nrb-tool-tag {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  background: var(--cpq-glass-1-bg, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--cpq-border-primary);
}
.nrb-tool-tag--locked {
  border-style: dashed;
  color: var(--cpq-text-secondary);
}
.nrb-data-source-tag {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  background: var(--cpq-glass-1-bg, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--cpq-border-primary);
}
.nrb-hint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--cpq-text-muted); }
</style>
