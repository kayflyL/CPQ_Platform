<template>
  <a-modal :open="open" :title="title" :footer="null" :width="420" @cancel="emit('cancel')">
    <a-select :value="value" placeholder="请选择处理人" style="width: 100%" @change="emit('update:value', $event)">
      <a-select-option v-for="name in options" :key="name" :value="name">{{ name }}</a-select-option>
    </a-select>
    <p v-if="!options.length" class="picker-empty">该角色暂无可选处理人，请先到任务调度配置。</p>
    <div class="picker-actions">
      <a-button style="margin-right: 8px" @click="emit('cancel')">取消</a-button>
      <a-button type="primary" :disabled="!value" @click="emit('confirm')">确认</a-button>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
defineProps<{ open: boolean; title: string; options: string[]; value: string }>()
const emit = defineEmits<{ (e: 'confirm'): void; (e: 'cancel'): void; (e: 'update:value', v: string): void }>()
</script>

<style scoped>
.picker-empty {
  margin-top: 8px;
  color: rgba(0, 0, 0, 0.45);
}
.picker-actions {
  text-align: right;
}
</style>
