<script setup lang="ts">
/** 单个 BOM 规则 source 编辑器（desc 或 qty）。
 *  单一职责:编辑一个 DescSource/QtySource。primary+fallback 组合由 BomTemplateEditor 负责。 */
import { computed } from 'vue'
import type { DescSource, QtySource } from '@/api/serverConfig'

defineOptions({ name: 'BomRuleSourceEditor' })

const props = defineProps<{
  modelValue: DescSource | QtySource | undefined
  mode: 'desc' | 'qty'
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: DescSource | QtySource): void }>()

const DESC_KINDS = [
  { value: 'fixed', label: '固定文案' },
  { value: 'part_field', label: '料号库字段' },
  { value: 'template', label: '模板字符串' },
  { value: 'struct_count', label: '结构计数' },
  { value: 'config_value', label: '配置参数' },
  { value: 'manual', label: '手填(留空)' },
]
const QTY_KINDS = [
  { value: 'fixed', label: '固定数字' },
  { value: 'part_quantity', label: '料号库数量' },
  { value: 'config_calc', label: '配置计算' },
  { value: 'manual', label: '手填(留空)' },
]
const STRUCT_SCOPES = [
  { value: 'io_slot', label: 'IO 槽(本行 slot)' },
  { value: 'rear_all', label: '后面板全聚合' },
  { value: 'front_cables', label: '前面板线缆' },
]
const CONFIG_KEYS_DESC = ['bays', 'form', 'series', 'bp_type', 'psu_qty', 'psu_wattage', 'psu_name', 'gpu_qty', 'gpu_cable_qty']
const CONFIG_KEYS_QTY = ['psu_qty', 'gpu_cable_qty']
const PART_FIELDS = ['name', 'sub_type', 'pn']
const VAR_HINT = '${bays} ${form} ${series} ${bp_type} ${psu_qty} ${psu_wattage} ${psu_name} ${gpu_qty} ${gpu_cable_qty}'

const kinds = computed(() => props.mode === 'desc' ? DESC_KINDS : QTY_KINDS)
const src = computed<any>({
  get: () => props.modelValue || { kind: 'manual' },
  set: (v) => emit('update:modelValue', v),
})

function defaultsFor(kind: string): Record<string, any> {
  switch (kind) {
    case 'fixed': return props.mode === 'desc' ? { value: '' } : { value: 1 }
    case 'part_field': return { category: '', field: 'name' }
    case 'part_quantity': return { category: '' }
    case 'template': return { template: '' }
    case 'struct_count': return { scope: 'io_slot' }
    case 'config_value': return { key: 'bays' }
    case 'config_calc': return { key: 'psu_qty' }
    case 'manual': return {}
    default: return {}
  }
}
function onKindChange(kind: any) { src.value = { kind, ...defaultsFor(kind) } }
function patch(p: any) { src.value = { ...src.value, ...p } }
</script>

<template>
  <div class="rs">
    <a-select :value="src.kind" size="small" style="width: 120px" @change="(v: any) => onKindChange(v)">
      <a-select-option v-for="k in kinds" :key="k.value" :value="k.value">{{ k.label }}</a-select-option>
    </a-select>

    <!-- desc 输入 -->
    <template v-if="mode === 'desc'">
      <a-input v-if="src.kind === 'fixed'" :value="src.value" size="small" style="flex:1; min-width: 140px"
        placeholder="固定文案" @update:value="(v: string) => patch({ value: v })" />
      <template v-else-if="src.kind === 'part_field'">
        <a-input :value="src.category" size="small" style="width: 140px"
          placeholder="category(如 heatsink)" @update:value="(v: string) => patch({ category: v })" />
        <a-select :value="src.field" size="small" style="width: 100px" @change="(v: any) => patch({ field: v })">
          <a-select-option v-for="f in PART_FIELDS" :key="f" :value="f">{{ f }}</a-select-option>
        </a-select>
      </template>
      <a-input v-else-if="src.kind === 'template'" :value="src.template" size="small" style="flex:1; min-width: 180px"
        :placeholder="VAR_HINT" @update:value="(v: string) => patch({ template: v })" />
      <a-select v-else-if="src.kind === 'struct_count'" :value="src.scope" size="small" style="width: 150px"
        @change="(v: any) => patch({ scope: v })">
        <a-select-option v-for="s in STRUCT_SCOPES" :key="s.value" :value="s.value">{{ s.label }}</a-select-option>
      </a-select>
      <a-select v-else-if="src.kind === 'config_value'" :value="src.key" size="small" style="width: 130px"
        @change="(v: any) => patch({ key: v })">
        <a-select-option v-for="k in CONFIG_KEYS_DESC" :key="k" :value="k">{{ k }}</a-select-option>
      </a-select>
      <span v-else class="rs-hint">留空 → 工作台手填</span>
    </template>

    <!-- qty 输入 -->
    <template v-else>
      <a-input-number v-if="src.kind === 'fixed'" :value="src.value" size="small" style="width: 90px"
        @update:value="(v: any) => patch({ value: v ?? 0 })" />
      <a-input v-else-if="src.kind === 'part_quantity'" :value="src.category" size="small" style="width: 140px"
        placeholder="category(如 fan)" @update:value="(v: string) => patch({ category: v })" />
      <a-select v-else-if="src.kind === 'config_calc'" :value="src.key" size="small" style="width: 130px"
        @change="(v: any) => patch({ key: v })">
        <a-select-option v-for="k in CONFIG_KEYS_QTY" :key="k" :value="k">{{ k }}</a-select-option>
      </a-select>
      <span v-else class="rs-hint">留空 → 工作台手填</span>
    </template>
  </div>
</template>

<style scoped>
.rs { display: flex; align-items: center; gap: 6px; flex: 1; flex-wrap: wrap; }
.rs-hint { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-style: italic; }
</style>
