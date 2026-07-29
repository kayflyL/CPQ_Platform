<script setup lang="ts">
/** 行式规格匹配规则编辑器（P3 match_kp 节点用）。
 *  每行：品类 select（来自 spec_field_defs 的 key）+ 字段 select（该品类的 spec_key）+ 操作符 + 数值 + 单位。
 *  Glass Console .glass-light 行容器；增删行；v-model 双向 SpecRule[]。 */
import { computed } from 'vue'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'

export interface SpecRule {
  category: string
  spec_key: string
  op: '>=' | '<=' | '='
  value: number | null
  unit: string
}

const props = defineProps<{
  modelValue: SpecRule[]
  categoryOptions: string[]                  // KP 品类名（从 /api/kp/categories 拉取）
  specKeysMap?: Record<string, string[]>     // 品类 → 现有 spec_key（从 /api/kp/spec-keys 拉，联动）
}>()
const emit = defineEmits<{ 'update:modelValue': [SpecRule[]] }>()

const rules = computed({
  get: () => props.modelValue || [],
  set: (v) => emit('update:modelValue', v),
})
const ops = [{ value: '>=', label: '≥' }, { value: '<=', label: '≤' }, { value: '=', label: '=' }]
// a-auto-complete 的 options 只吃 {value,label}[]（纯 string[] 会触发 valueUtil 'in' 报错）
const categoryOpts = computed(() => (props.categoryOptions || []).map(s => ({ value: s, label: s })))
function fieldOptionsFor(cat: string) {
  return (props.specKeysMap?.[cat] || []).map(s => ({ value: s, label: s }))
}
// a-auto-complete 既要库选项可筛、又要允许手填自定义值（[derive-must-have-manual-fallback] 库 spec 稀疏）
const filterFn = (input: string, option: any) => {
  const opt = typeof option === 'string' ? option : String(option?.value ?? option?.label ?? '')
  return opt.toLowerCase().includes((input || '').toLowerCase())
}

function add() {
  rules.value = [...rules.value, { category: '', spec_key: '', op: '>=', value: null, unit: '' }]
}
function remove(i: number) {
  rules.value = rules.value.filter((_, idx) => idx !== i)
}
function update(i: number, patch: Partial<SpecRule>) {
  rules.value = rules.value.map((r, idx) => (idx === i ? { ...r, ...patch } : r))
}
</script>

<template>
  <div class="cb-wrap">
    <div v-for="(r, i) in rules" :key="i" class="cb-row glass-light">
      <a-auto-complete
        :value="r.category" :options="categoryOpts" placeholder="品类"
        size="small" style="width: 120px" :filter-option="filterFn"
        @update:value="(v: any) => update(i, { category: String(v || ''), spec_key: '' })"
      />
      <a-auto-complete
        :value="r.spec_key" :options="fieldOptionsFor(r.category)" placeholder="规格字段"
        size="small" style="width: 140px" :filter-option="filterFn"
        @update:value="(v: any) => update(i, { spec_key: String(v || '') })"
      />
      <a-select size="small" :value="r.op" style="width: 60px" :options="ops" @change="(v: any) => update(i, { op: v })" />
      <a-input-number
        size="small" :value="r.value" placeholder="默认值" style="width: 92px" :min="0"
        @change="(v: any) => update(i, { value: v == null ? null : +v })"
      />
      <a-input size="small" :value="r.unit" placeholder="单位" style="width: 72px" @change="(e: any) => update(i, { unit: e.target.value })" />
      <a-button size="small" type="text" danger @click="remove(i)"><DeleteOutlined /></a-button>
    </div>
    <a-button size="small" type="dashed" block @click="add"><PlusOutlined /> 增加规则</a-button>
  </div>
</template>

<style scoped>
.cb-wrap { display: flex; flex-direction: column; gap: 8px; }
.cb-row {
  display: flex; align-items: center; gap: 6px; padding: 8px;
  border-radius: var(--cpq-radius-md, 12px);
}
</style>
