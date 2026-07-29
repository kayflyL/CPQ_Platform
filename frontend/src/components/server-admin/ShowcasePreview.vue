<script setup lang="ts">
/** 3D 展示内联预览 — 在编辑参数时实时预览效果。
 *  使用 useServerModel3D composable 渲染模型。
 *  监听 config 变化，动态更新灯光、相机等参数。 */
import { ref, computed, watch } from 'vue'
import { useServerModel3D } from '@/composables/useServerModel3D'
import type { ShowcaseConfig } from '@/components/server-config/showcase-config'

const props = defineProps<{
  config: ShowcaseConfig
}>()

const stageRef = ref<HTMLElement | null>(null)

// 检查是否有有效的 GLB 路径
const hasGlbPath = computed(() => {
  const result = props.config?.glb_path && props.config.glb_path.trim() !== ''
  console.log('[ShowcasePreview] hasGlbPath:', result, 'glb_path:', props.config?.glb_path)
  return result
})

// 监听 config 变化
watch(() => props.config, (newConfig) => {
  console.log('[ShowcasePreview] Config changed:', {
    glb_path: newConfig?.glb_path,
    hasRender: !!newConfig?.render,
    renderLight: newConfig?.render?.light,
    renderDark: newConfig?.render?.dark,
  })
}, { immediate: true, deep: true })

// 创建响应式的渲染选项
const renderOptions = computed(() => ({
  src: props.config?.glb_path || '',
  renderConfig: props.config?.render,
}))

console.log('[ShowcasePreview] Calling useServerModel3D with src:', renderOptions.value.src)

const { loading, error } = useServerModel3D(stageRef, renderOptions)

// 监听 loading 和 error 变化
watch([loading, error], ([newLoading, newError]) => {
  console.log('[ShowcasePreview] State changed:', { loading: newLoading, error: newError })
}, { immediate: true })
</script>

<template>
  <div class="showcase-preview">
    <div v-if="!hasGlbPath" class="preview-placeholder">
      <span>请先上传 GLB 模型文件</span>
    </div>
    <template v-else>
      <!-- 加载提示：在模型加载时显示 -->
      <div v-if="loading" class="preview-loading">
        <a-spin size="large" />
        <span>加载模型中...</span>
      </div>
      <!-- 错误提示 -->
      <div v-if="error" class="preview-error">
        <span>{{ error }}</span>
      </div>
      <!-- 3D 渲染容器：总是渲染，用 v-show 控制显示 -->
      <div
        ref="stageRef"
        class="preview-stage"
        v-show="!loading && !error"
      ></div>
      <!-- 提示文本 -->
      <div v-if="!loading && !error" class="preview-hint">
        拖拽旋转 · 滚轮缩放
      </div>
    </template>
  </div>
</template>

<style scoped>
.showcase-preview {
  width: 100%;
  height: 100%;
  min-height: 500px;
  position: relative;
  display: flex;
  flex-direction: column;
}

.preview-stage {
  flex: 1;
  position: relative;
}

.preview-stage :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
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
  background: var(--cpq-overlay-b40, rgba(0, 0, 0, 0.4));
  backdrop-filter: blur(8px);
}
</style>