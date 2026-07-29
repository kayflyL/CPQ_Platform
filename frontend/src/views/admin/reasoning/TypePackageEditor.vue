<script setup lang="ts">
/** 机型类型套餐编辑器（match_kp 节点用）。
 *  机型类型（关键词，匹配 server_type.name）→ 标准 KP 品类套餐。
 *  如 AI 机型 → [CPU, GPU, Memory, HDD/SSD]。加新机型类型时这里配套餐，不用改代码。 */
import { ref, onMounted } from 'vue'
import { kpPartsApi } from '@/api/serverConfig'
import ChipListInput from './ChipListInput.vue'

interface TypePackage { type_keyword: string; categories: string[] }
const props = defineProps<{ modelValue: TypePackage[] }>()
const emit = defineEmits<{ 'update:modelValue': [TypePackage[]] }>()

const kpCategories = ref<string[]>([])
onMounted(async () => {
  try { kpCategories.value = ((await kpPartsApi.categories()) || []).map(c => c.name) }
  catch { kpCategories.value = [] }
})

function update(i: number, patch: Partial<TypePackage>) {
  emit('update:modelValue', props.modelValue.map((e, idx) => idx === i ? { ...e, ...patch } : e))
}
function remove(i: number) { emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== i)) }
function add() {
  emit('update:modelValue', [...(props.modelValue || []), { type_keyword: '', categories: [] }])
}
// 暴露给模板：品类下拉建议（用户也可自由输入）
defineExpose({ kpCategories })
</script>

<template>
  <div class="tp-editor">
    <div v-for="(p, i) in modelValue" :key="i" class="tp-row">
      <a-input :value="p.type_keyword" size="small" placeholder="类型关键词（如 AI）" style="width: 160px"
        @update:value="(v: any) => update(i, { type_keyword: v || '' })" />
      <div class="tp-cats">
        <ChipListInput :model-value="p.categories" placeholder="品类（回车添加，如 CPU/GPU/Memory）"
          @update:modelValue="(v: any) => update(i, { categories: v || [] })" />
      </div>
      <a-button size="small" type="link" danger @click="remove(i)">删</a-button>
    </div>
    <a-button size="small" type="dashed" block @click="add">+ 新增类型套餐</a-button>
  </div>
</template>

<style scoped>
.tp-editor { display: flex; flex-direction: column; gap: 8px; }
.tp-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tp-cats { flex: 1; min-width: 180px; }
</style>
