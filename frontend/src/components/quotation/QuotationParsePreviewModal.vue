<template>
  <a-modal
    :open="open"
    title="解析预览 — 确认成本表内容"
    width="92%"
    :footer="null"
    :destroy-on-close="true"
    :body-style="{ padding: '16px', height: '80vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    @cancel="emit('cancel')"
  >
    <!-- 操作引导 -->
    <a-alert
      type="info"
      show-icon
      banner
      message="核对热力图里的取值位置是否正确；若区域边界或取值列有误，在右侧「解析规则」调整，保存后会用本文件自动重算。确认无误后再生成成本表。"
      style="margin-bottom: 12px; flex-shrink: 0;"
    />

    <!-- 左右布局：左热力图 / 右规则 -->
    <div class="preview-layout">
      <div class="preview-main">
        <a-card title="Excel 预览" size="small" :loading="parsing">
          <a-tabs
            v-if="sheetNames.length"
            v-model:activeKey="activeSheetName"
            size="small"
            @change="handleSheetChange"
          >
            <a-tab-pane v-for="name in sheetNames" :key="name" :tab="name">
              <ParseHeatmapPreview :previewData="previewData" />
            </a-tab-pane>
          </a-tabs>
          <ParseHeatmapPreview v-else :previewData="previewData" />
        </a-card>
      </div>
      <div class="preview-side">
        <a-card title="解析规则（调整后自动重算）" size="small">
          <ParseRulesEditor />
        </a-card>
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="preview-footer">
      <a-button @click="emit('cancel')">取消</a-button>
      <a-button
        type="primary"
        :loading="confirming"
        :disabled="confirming"
        @click="emit('confirm')"
      >确认生成成本表</a-button>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import ParseHeatmapPreview from '@/components/excel-parser/ParseHeatmapPreview.vue'
import ParseRulesEditor from '@/components/excel-parser/ParseRulesEditor.vue'
import { useExcelParser } from '@/composables/useExcelParser'

const props = defineProps<{
  open: boolean
  file: File | null
  opportunityId: string
  confirming: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const {
  previewData, parsing,
  sheetNames, activeSheetName,
  loadRules, loadBusinessFields, loadMappings, handleFileUpload, refreshPreview
} = useExcelParser()

function handleSheetChange(name: string) {
  void refreshPreview(name)
}

// 打开弹窗时：加载规则（幂等）+ 用传入文件触发预览。
// 规则改动后在 ParseRulesEditor 内保存会自动 refreshPreview（用 uploadedFile 重算）。
watch(
  () => [props.open, props.file],
  async ([open, file]) => {
    if (open && file) {
      await Promise.all([loadRules(), loadBusinessFields(), loadMappings()])
      await handleFileUpload(file as File, true)
    }
  }
)
</script>

<style scoped>
.preview-layout {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow: hidden;
  min-height: 0;
}

.preview-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.preview-side {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
}

.preview-main :deep(.ant-card) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-main :deep(.ant-card-body) {
  flex: 1;
  overflow: auto;
}

.preview-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
}
</style>
