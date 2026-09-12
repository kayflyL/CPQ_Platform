<template>
  <div class="node-resource-bindings">
    <section v-if="toolsEnabled" class="nrb-section nrb-card">
      <div class="nrb-section-title">可用工具</div>

      <!-- 机制工具：紧凑 chip，悬停看说明 -->
      <div v-if="lockedTools.length" class="nrb-locked-block">
        <span class="nrb-field-label">机制必需（节点机制依赖，不可取消）</span>
        <div class="nrb-tool-tags">
          <a-tooltip v-for="tool in lockedToolOptions" :key="tool.value" :title="tool.detail || tool.desc || tool.label">
            <span class="nrb-tool-tag nrb-tool-tag--locked">🔒 {{ tool.label }}</span>
          </a-tooltip>
        </div>
      </div>

      <!-- 增强工具：多选（选项名紧凑 + 下拉才见说明） -->
      <template v-if="!toolsReadonly">
        <div class="nrb-field">
          <span class="nrb-field-label">增强工具（可增删）</span>
          <a-select
            v-model:value="toolModel"
            mode="multiple"
            option-label-prop="label"
            :options="selectableOptions"
            :max-tag-count="4"
            placeholder="选择该节点可调用的增强工具"
            style="width:100%"
          >
            <template #option="opt">
              <div class="nrb-opt" :title="opt.item?.detail || opt.item?.desc || ''">
                <span class="nrb-opt-name">{{ opt.item?.label || opt.label }}</span>
                <span v-if="opt.item?.desc" class="nrb-opt-desc">{{ opt.item.desc }}</span>
              </div>
            </template>
          </a-select>
          <p class="nrb-hint">点击展开查看工具说明；工具已自动携带其数据源与规则读取权限。</p>
        </div>
      </template>
      <div v-else-if="readonlyToolOptions.length" class="nrb-tool-tags">
        <a-tooltip v-for="tool in readonlyToolOptions" :key="tool.value" :title="tool.detail || tool.desc || tool.label">
          <span class="nrb-tool-tag">{{ tool.label }}</span>
        </a-tooltip>
      </div>

      <!-- 数据源：随工具自动派生，无需单独配置 -->
      <div v-if="selectedDataSources.length" class="nrb-field">
        <span class="nrb-field-label">将读取的数据源（随工具自动派生）</span>
        <div class="nrb-data-source-list">
          <span v-for="source in selectedDataSources" :key="source" class="nrb-data-source-tag">{{ source }}</span>
        </div>
        <p class="nrb-hint">数据来源已由所选工具携带，无需单独配置；配置规则在「策略中心-需求分析」统一维护。</p>
      </div>

      <p v-if="toolsReadonly" class="nrb-hint">工具由节点类型固定，避免误选导致链路失效；数据源由工具自动派生。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  tools?: string[]
  toolOptions?: Array<{ value: string; label: string; desc?: string; detail?: string; dataSources?: string[] }>
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
  return { value: name, label: found?.label || name, desc: found?.desc || '', detail: found?.detail || '', dataSources: found?.dataSources || [] }
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
.nrb-section { display: flex; flex-direction: column; gap: 12px; }
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
  display: inline-flex; align-items: center; gap: 4px;
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
.nrb-opt { display: flex; flex-direction: column; line-height: 1.4; }
.nrb-opt-name { font-weight: 600; }
.nrb-opt-desc {
  font-size: 12px; color: var(--cpq-text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px;
}
.nrb-hint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--cpq-text-muted); }
</style>
