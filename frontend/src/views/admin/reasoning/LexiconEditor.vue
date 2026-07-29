<script setup lang="ts">
/** 词表词条编辑器（extract 节点用，5 张词表共用）。
 *  结构统一：左侧品类下拉（a-auto-complete：DB 建议 + 自由输入）+ 右侧触发词 chips。
 *  kind 决定左侧下拉源：
 *  - kp          → KP 库品类（/api/kp/categories）
 *  - chassis     → 配件库分类（/api/parts/categories，底盘件为主）
 *  - server_type → 服务器类型（/api/server-catalog/types）
 *  - series      → 系列（/api/base-configs/series，SSOT）
 *  - form        → 机箱形态（/api/base-configs/forms，DISTINCT）
 *  下拉 onMounted 实时拉，保证菜单新增类别后重开抽屉自动出现；
 *  a-auto-complete 让预填值即使不在 DB 里也能显示，且用户可自由输入。 */
import { ref, computed, onMounted } from 'vue'
import { kpPartsApi, catalogApi, baseConfigApi, partsApi } from '@/api/serverConfig'
import ChipListInput from './ChipListInput.vue'
import type { LexiconEntry } from '@/api/reasoningFlow'

type Kind = 'kp' | 'chassis' | 'server_type' | 'series' | 'form'
const props = defineProps<{
  modelValue: LexiconEntry[]
  kind: Kind
}>()
const emit = defineEmits<{ 'update:modelValue': [LexiconEntry[]] }>()

const rawOptions = ref<string[]>([])
// 下拉 = DB 真实源（表数据 / DISTINCT），不合并已配置值
const options = computed(() => rawOptions.value.map(v => ({ value: v, label: v })))

async function loadOptions() {
  try {
    if (props.kind === 'kp') {
      rawOptions.value = ((await kpPartsApi.categories()) || []).map(c => c.name)
    } else if (props.kind === 'chassis') {
      rawOptions.value = ((await partsApi.categories()).categories) || []
    } else if (props.kind === 'server_type') {
      rawOptions.value = (((await catalogApi.listTypes()).types) || []).map(t => t.name)
    } else if (props.kind === 'series') {
      rawOptions.value = ((await baseConfigApi.listSeries()).series) || []
    } else if (props.kind === 'form') {
      rawOptions.value = ((await baseConfigApi.listForms()).forms) || []
    }
  } catch { rawOptions.value = [] }
}
onMounted(loadOptions)

function updateEntry(i: number, patch: Partial<LexiconEntry>) {
  emit('update:modelValue', props.modelValue.map((e, idx) => idx === i ? { ...e, ...patch } : e))
}
function removeEntry(i: number) {
  emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== i))
}
function addEntry() {
  emit('update:modelValue', [...(props.modelValue || []), { key: '', triggers: [] }])
}
</script>

<template>
  <div class="lex-editor">
    <div v-for="(e, i) in modelValue" :key="i" class="lex-row">
      <a-auto-complete
        :value="e.key"
        :options="options"
        size="small"
        style="width: 200px"
        :placeholder="`选/输入 ${kind}`"
        @update:value="(v: any) => updateEntry(i, { key: v || '' })"
      />
      <div class="lex-triggers">
        <ChipListInput
          :model-value="e.triggers"
          placeholder="触发词，回车添加"
          @update:modelValue="(v: any) => updateEntry(i, { triggers: v || [] })"
        />
      </div>
      <a-button size="small" type="link" danger @click="removeEntry(i)">删</a-button>
    </div>
    <a-button size="small" type="dashed" block @click="addEntry">+ 新增词条</a-button>
  </div>
</template>

<style scoped>
.lex-editor { display: flex; flex-direction: column; gap: 8px; }
.lex-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.lex-triggers { flex: 1; min-width: 180px; }
</style>
