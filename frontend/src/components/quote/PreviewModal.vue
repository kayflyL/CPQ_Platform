<template>
  <a-modal
    v-model:open="visible"
    title="报价预览"
    :width="'92vw'"
    :footer="null"
    :destroyOnClose="true"
    @cancel="handleClose"
  >
    <div class="preview-modal-body" v-if="sheets.length > 0">
      <ExcelTable :sheets="sheets" :a4-preview="false" />
    </div>
    <div v-else class="preview-empty">
      <a-empty description="暂无数据" />
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ExcelTable from '@/components/ExcelTable.vue'
import type { SheetRenderData } from '@/types/template'

const props = defineProps<{
  open: boolean
  sheets: SheetRenderData[]
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

function handleClose() {
  emit('update:open', false)
}
</script>

<style scoped>
.preview-modal-body {
  height: 75vh;
  overflow: auto;
  background: #ffffff;
  border-radius: 8px;
  padding: 16px;
}
.preview-empty {
  padding: 60px 0;
  text-align: center;
}
</style>
