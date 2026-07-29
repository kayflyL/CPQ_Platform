<script setup lang="ts">
/** 数量单位编辑器（extract 节点用）。
 *  口语化数量单位 → 品类：N卡→GPU, N条→Memory, N颗/N块→CPU
 *  用户写"8卡" → GPU qty=8。加新单位（如 pcs）这里配，不用改代码。 */
import { ref, onMounted } from 'vue'
import { kpPartsApi } from '@/api/serverConfig'

interface QtyUnit { unit: string; category: string }
const props = defineProps<{ modelValue: QtyUnit[] }>()
const emit = defineEmits<{ 'update:modelValue': [QtyUnit[]] }>()

const kpCategories = ref<string[]>([])
onMounted(async () => {
  try { kpCategories.value = ((await kpPartsApi.categories()) || []).map(c => c.name) }
  catch { kpCategories.value = [] }
})

function update(i: number, patch: Partial<QtyUnit>) {
  emit('update:modelValue', props.modelValue.map((e, idx) => idx === i ? { ...e, ...patch } : e))
}
function remove(i: number) { emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== i)) }
function add() { emit('update:modelValue', [...(props.modelValue || []), { unit: '', category: '' }]) }
</script>

<template>
  <div class="qu-editor">
    <div v-for="(u, i) in modelValue" :key="i" class="qu-row">
      <a-input :value="u.unit" size="small" placeholder="单位（如 卡）" style="width: 120px"
        @update:value="(v: any) => update(i, { unit: v || '' })" />
      <a-select :value="u.category || undefined" size="small" placeholder="关联品类" show-search allow-clear style="width: 200px"
        :options="kpCategories.map(c => ({ value: c, label: c }))"
        @update:value="(v: any) => update(i, { category: v || '' })" />
      <a-button size="small" type="link" danger @click="remove(i)">删</a-button>
    </div>
    <a-button size="small" type="dashed" block @click="add">+ 新增数量单位</a-button>
  </div>
</template>

<style scoped>
.qu-editor { display: flex; flex-direction: column; gap: 8px; }
.qu-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
</style>
