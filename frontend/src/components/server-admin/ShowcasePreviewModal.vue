<script setup lang="ts">
/** 3D 展示预览弹窗 — 实时预览渲染参数效果。
 *  使用 useServerModel3D composable 渲染模型。 */
import { ref, watch, computed } from 'vue'
import { useServerModel3D } from '@/composables/useServerModel3D'
import type { ShowcaseConfig } from '@/components/server-config/showcase-config'

const props = defineProps<{
  visible: boolean
  config: ShowcaseConfig | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const stageRef = ref<HTMLElement | null>(null)

// 创建响应式的渲染选项
const renderOptions = computed(() => ({
  src: props.config?.glb_path || '',
  renderConfig: props.config?.render,
}))

const { loading, error } = useServerModel3D(stageRef, renderOptions)

// 监听 visible 变化，关闭时清理
watch(() => props.visible, (v) => {
  if (!v) {
    // 组件销毁时 useServerModel3D 的 onBeforeUnmount 会自动清理
  }
})
</script>

<template>
  <a-modal
    :open="visible"
    title="3D 展示预览"
    @cancel="emit('update:visible', false)"
    width="80%"
    :footer="null"
  >
    <div class="preview-container">
      <div v-if="loading" class="preview-loading">
        <a-spin size="large" />
        <span>加载模型中...</span>
      </div>
      <div v-else-if="error" class="preview-error">
        <span>{{ error }}</span>
      </div>
      <div v-else ref="stageRef" class="preview-stage"></div>
    </div>
    <div class="preview-hint">拖拽旋转 · 滚轮缩放</div>
  </a-modal>
</template>

<style scoped>
.preview-container {
  width: 100%;
  height: 60vh;
  min-height: 400px;
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: var(--cpq-overlay-b20);
}

.preview-stage {
  width: 100%;
  height: 100%;
}

.preview-loading,
.preview-error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--cpq-text-muted, #6E7582);
}

.preview-hint {
  text-align: center;
  padding: 8px 0;
  font-size: 12px;
  color: var(--cpq-text-muted, #6E7582);
}
</style>