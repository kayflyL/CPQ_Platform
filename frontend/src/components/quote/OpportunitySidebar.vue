<template>
  <Teleport to="body">
    <!-- 遮罩层 -->
    <transition name="fade">
      <div v-if="internalShow" class="sidebar-overlay" @click="close"></div>
    </transition>

    <!-- 抽屉面板：统一协作流（消息 + 文件 + 在线状态） -->
    <div class="sidebar-drawer" :class="{ open: internalShow }">
      <div class="sidebar-content">
        <OpportunityFeed :opportunity-id="opportunityId" :visible="internalShow" />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import OpportunityFeed from '@/components/feed/OpportunityFeed.vue'

const props = defineProps<{
  opportunityId: string
  showSidebar?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:showSidebar', value: boolean): void
}>()

const internalShow = ref(false)

// Parent owns the state via v-model:show-sidebar; this just mirrors it so the
// overlay/transition can react, and emits close back up.
watch(
  () => props.showSidebar,
  (val) => {
    internalShow.value = !!val
  },
)

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
  width: 420px;
  background: var(--cpq-glass-3-bg);
  backdrop-filter: blur(var(--cpq-glass-blur-3));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-3));
  border-left: 1px solid var(--cpq-glass-border);
  box-shadow: -8px 0 24px var(--cpq-shadow-color-strong);
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

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
