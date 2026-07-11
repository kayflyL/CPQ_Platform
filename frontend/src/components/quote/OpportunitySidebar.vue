<template>
  <!-- 遮罩层 -->
  <transition name="fade">
    <div v-if="internalShow" class="sidebar-overlay" @click="close"></div>
  </transition>
  
  <!-- 抽屉面板 -->
  <div class="sidebar-drawer" :class="{ open: internalShow }">
    <div class="sidebar-content">
      <!-- 上半：商机文件 -->
      <div class="sidebar-section files-section">
        <opportunity-files 
          :opportunity-id="opportunityId" 
          :visible="internalShow" 
        />
      </div>
      <!-- 下半：评论 -->
      <div class="sidebar-section comment-section">
        <comment-panel 
          :opportunity-id="opportunityId" 
          :visible="internalShow"
          :show-title="true"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import OpportunityFiles from '@/components/quote/OpportunityFiles.vue'
import CommentPanel from '@/components/CommentPanel.vue'

const props = defineProps<{
  opportunityId: string
  showSidebar?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:showSidebar', value: boolean): void
}>()

const internalShow = ref(false)

watch(() => props.showSidebar, (val) => {
  if (val !== undefined) internalShow.value = val
})

const toggle = () => {
  internalShow.value = !internalShow.value
  emit('update:showSidebar', internalShow.value)
}

const close = () => {
  internalShow.value = false
  emit('update:showSidebar', false)
}
</script>

<style scoped>
.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--cpq-overlay-b40);
  backdrop-filter: blur(4px);
  z-index: 999;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.sidebar-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 400px;
  background: rgba(12, 13, 16, 0.85);
  backdrop-filter: blur(24px) saturate(1.4);
  -webkit-backdrop-filter: blur(24px) saturate(1.4);
  border-left: 1px solid var(--cpq-overlay-w8);
  box-shadow: -8px 0 24px var(--cpq-overlay-b40);
  z-index: 1000;
  transform: translateX(100%);
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}

.sidebar-drawer.open {
  transform: translateX(0);
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-section {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.files-section {
  flex: 0 0 42%;
  min-height: 220px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
}

.comment-section {
  flex: 1;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
