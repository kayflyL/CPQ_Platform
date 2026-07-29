<script setup lang="ts">
/** 规格别名编辑器（extract 节点用）。
 *  结构：触发词（如 千兆）→ 品类（KP 下拉）+ 搜索词（chips，如 1G/1000M）
 *  救 ILIKE 命不中的规格描述：库 model 是英文（含 10G/1000M），用户写"千兆"匹配不到 → 别名注入搜索词 */
import { ref, onMounted } from 'vue'
import { kpPartsApi } from '@/api/serverConfig'
import ChipListInput from './ChipListInput.vue'

interface SpecAlias { trigger: string; category: string; search_terms: string[] }
const props = defineProps<{ modelValue: SpecAlias[] }>()
const emit = defineEmits<{ 'update:modelValue': [SpecAlias[]] }>()

const kpCategories = ref<string[]>([])
onMounted(async () => {
  try { kpCategories.value = ((await kpPartsApi.categories()) || []).map(c => c.name) }
  catch { kpCategories.value = [] }
})

function update(i: number, patch: Partial<SpecAlias>) {
  emit('update:modelValue', props.modelValue.map((e, idx) => idx === i ? { ...e, ...patch } : e))
}
function remove(i: number) { emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== i)) }
function add() {
  emit('update:modelValue', [...(props.modelValue || []), { trigger: '', category: '', search_terms: [] }])
}
</script>

<template>
  <div class="sa-editor">
    <div v-for="(a, i) in modelValue" :key="i" class="sa-row">
      <a-input :value="a.trigger" size="small" placeholder="触发词（如 千兆）" style="width: 140px"
        @update:value="(v: any) => update(i, { trigger: v || '' })" />
      <a-select :value="a.category || undefined" size="small" placeholder="KP 品类" show-search allow-clear style="width: 200px"
        :options="kpCategories.map(c => ({ value: c, label: c }))"
        @update:value="(v: any) => update(i, { category: v || '' })" />
      <div class="sa-terms">
        <ChipListInput :model-value="a.search_terms" placeholder="搜索词（如 1G / 1000M），回车添加"
          @update:modelValue="(v: any) => update(i, { search_terms: v || [] })" />
      </div>
      <a-button size="small" type="link" danger @click="remove(i)">删</a-button>
    </div>
    <a-button size="small" type="dashed" block @click="add">+ 新增规格别名</a-button>
  </div>
</template>

<style scoped>
.sa-editor { display: flex; flex-direction: column; gap: 8px; }
.sa-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sa-terms { flex: 1; min-width: 160px; }
</style>
