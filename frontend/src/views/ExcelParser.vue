<template>
  <div class="excel-parser-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>Excel 解析</h2>
      <a-space>
        <a-upload
          :before-upload="handleFileUpload"
          :show-upload-list="false"
          accept=".xlsx"
        >
          <a-button type="primary">
            <template #icon><UploadOutlined /></template>
            上传 Excel
          </a-button>
        </a-upload>
        <a-button @click="loadRules()" :loading="loadingRules">
          <template #icon><ReloadOutlined /></template>
          刷新规则
        </a-button>
      </a-space>
    </div>

    <!-- 模板页签条 -->
    <div class="template-bar">
      <a-tabs
        v-if="parseTemplates.length"
        class="template-tabs"
        type="card"
        size="small"
        :active-key="activeTemplateId != null ? String(activeTemplateId) : ''"
        @change="onTabChange"
      >
        <a-tab-pane v-for="tpl in parseTemplates" :key="String(tpl.id)">
          <template #tab>
            <span class="tpl-tab-label">
              <span class="tpl-status-dot" :class="tpl.selfcheck_status" />
              {{ tpl.name }}
              <a-tag v-if="tpl.is_fallback" class="tpl-tag" :bordered="false">兜底</a-tag>
            </span>
          </template>
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- 使用位置绑定：哪个入口用哪套模板，在此配置 -->
    <div v-if="scopeBindings.length" class="scope-bind-row">
      <span class="scope-label">
        使用位置
        <a-tooltip title="各上传入口用哪套解析模板在此绑定；未绑定的入口走「通用」兜底">
          <QuestionCircleOutlined class="scope-help" />
        </a-tooltip>
      </span>
      <div v-for="b in scopeBindings" :key="b.scope_key" class="scope-item">
        <span class="scope-name">{{ b.label }}</span>
        <a-select
          size="small"
          style="width: 200px"
          :value="b.template_id ?? -1"
          @change="(v: any) => setScopeBinding(b.scope_key, v)"
        >
          <a-select-option v-for="t in parseTemplates.filter((x: any) => x.enabled !== false)" :key="t.id" :value="t.id">
            {{ t.name }}{{ t.is_fallback ? '（通用兜底）' : '' }}
          </a-select-option>
        </a-select>
      </div>
      <div class="scope-actions">
        <a-button size="small" @click="onDownloadStd">
          <template #icon><DownloadOutlined /></template>
          下载标准模板
        </a-button>
        <a-button size="small" @click="showCreateModal = true">
          <template #icon><PlusOutlined /></template>
          新建模板
        </a-button>
      </div>
    </div>

    <!-- 三栏布局 -->
    <div class="three-column-layout">
      <!-- 左栏：解析规则配置 -->
      <div class="left-panel">
        <ParseRulesEditor />
      </div>

      <!-- 中栏：Excel 热力图预览 -->
      <div class="center-panel">
        <a-card title="Excel 预览" size="small" :loading="parsing">
          <ParseHeatmapPreview :previewData="previewData" />
        </a-card>
      </div>

      <!-- 右栏：解析结果（带溯源） -->
      <div class="right-panel">
        <a-card title="解析结果" size="small">
          <ParseResultPanel v-if="parseResult" :parseResult="parseResult" />

          <!-- 解析追踪 -->
          <div v-if="parseResult" class="result-section">
            <h4>解析追踪</h4>
            <a-timeline>
              <a-timeline-item
                v-for="(trace, idx) in parseResult.trace"
                :key="idx"
                :color="trace.type === 'static_field' ? 'green' : 'blue'"
              >
                <template v-if="trace.type === 'static_field'">
                  <strong>{{ trace.field_key }}</strong>: {{ trace.value }}
                  <div class="trace-detail">
                    行 {{ trace.source.row + 1 }}, 列 {{ trace.source.col + 1 }}
                  </div>
                </template>
                <template v-else-if="trace.type === 'dynamic_region'">
                  <strong>{{ trace.region }}</strong>: {{ trace.item_count }} 行数据
                  <div class="trace-detail">
                    起始行 {{ trace.bounds.start_row + 1 }}, 结束行 {{ trace.bounds.end_row + 1 }}
                  </div>
                </template>
              </a-timeline-item>
            </a-timeline>
          </div>

          <template v-if="!parseResult">
            <a-empty description="上传 Excel 文件查看解析结果" />
          </template>
        </a-card>
      </div>
    </div>

    <!-- 新建模板 -->
    <a-modal
      v-model:open="showCreateModal"
      title="新建解析模板"
      @ok="onCreateTemplate"
    >
      <a-form layout="vertical">
        <a-form-item label="模板名" required>
          <a-input v-model:value="createForm.name" placeholder="如: 方案部配置表-B版" />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model:value="createForm.note" :rows="2" placeholder="适用场景 / 差异说明" />
        </a-form-item>
      </a-form>
      <a-alert
        type="info"
        show-icon
        message="新建的是空壳模板：接下来在此页签下添加区域与字段映射，并把「使用位置」绑定到它即可生效。"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { UploadOutlined, ReloadOutlined, PlusOutlined, DownloadOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import ParseRulesEditor from '@/components/excel-parser/ParseRulesEditor.vue'
import ParseHeatmapPreview from '@/components/excel-parser/ParseHeatmapPreview.vue'
import ParseResultPanel from '@/components/excel-parser/ParseResultPanel.vue'
import { useExcelParser } from '@/composables/useExcelParser'

const {
  parseTemplates, activeTemplateId,
  previewData, parseResult, parsing, loadingRules,
  loadTemplates, selectTemplate, createTemplate,
  scopeBindings, loadScopeBindings, setScopeBinding,
  loadRules, loadBusinessFields, loadMappings, handleFileUpload, downloadStd, loadStdPreview
} = useExcelParser()

const showCreateModal = ref(false)
const createForm = reactive({ name: '', note: '' })

function onTabChange(key: string | number) {
  void selectTemplate(Number(key))
}

async function onDownloadStd() {
  const id = activeTemplateId.value
  if (id == null) {
    message.warning('没有可下载的模板')
    return
  }
  const result = await downloadStd(id)
  if (result === 'blocked') {
    Modal.confirm({
      title: '标准模板暂停下发',
      content: '当前模板规则改动后还没通过自检回归，下载出去的模板可能解析出错。仍要强制下载？',
      okText: '强制下载',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => downloadStd(id, true),
    })
  }
}

async function onCreateTemplate() {
  if (!createForm.name.trim()) {
    message.warning('请填写模板名')
    return
  }
  if (await createTemplate(createForm.name.trim(), createForm.note.trim())) {
    showCreateModal.value = false
    createForm.name = ''
    createForm.note = ''
  }
}

onMounted(async () => {
  await loadTemplates()
  loadBusinessFields()
  loadMappings()
  await loadScopeBindings()
  // 未上传文件时中部预览常驻显示标准模板
  void loadStdPreview()
})
</script>

<style scoped>
.excel-parser-page {
  padding: 16px;
  /* 滚动容器内自带 72px 顶栏让位占位（--cpq-header-clearance）：满高页必须扣掉，
     否则整页超高一段、底部要下滑才能看到 */
  height: calc(100% - var(--cpq-header-clearance, 72px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.page-header h2 {
  margin: 0;
  color: var(--cpq-text-light);
}

/* ── 模板页签条 ── */
.template-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.template-tabs {
  flex: 1;
  min-width: 0;
}

.scope-bind-row {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 6px 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: var(--cpq-glass-1-bg);
  border: 1px solid var(--cpq-glass-border);
  font-size: 12px;
}

.scope-label {
  font-weight: 600;
  color: var(--cpq-text-light);
}

.scope-help {
  color: var(--cpq-text-muted);
  margin-left: 2px;
}

.scope-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.scope-name {
  color: var(--cpq-text-muted);
}

.scope-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.template-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 0;
}

.tpl-add-btn {
  flex-shrink: 0;
}

.tpl-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tpl-tag {
  margin-left: 2px;
  font-size: 11px;
  line-height: 16px;
  padding: 0 4px;
}

.tpl-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-faint, #bfbfbf);
  flex-shrink: 0;
}

.tpl-status-dot.passed { background: var(--cpq-success, #52c41a); }
.tpl-status-dot.failed { background: var(--cpq-error, #ff4d4f); }
.tpl-status-dot.stale { background: var(--cpq-warning, #faad14); }

/* ── 三栏 ── */
.three-column-layout {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow: hidden;
  min-height: 0;
}

.left-panel {
  width: 320px;
  flex-shrink: 0;
  overflow-y: auto;
}

.center-panel {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.right-panel {
  width: 380px;
  flex-shrink: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.center-panel :deep(.ant-card),
.right-panel :deep(.ant-card) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.center-panel :deep(.ant-card-body),
.right-panel :deep(.ant-card-body) {
  flex: 1;
  overflow: auto;
}

.result-section {
  margin-bottom: 16px;
}

.result-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-light);
}

.trace-detail {
  font-size: 11px;
  color: var(--cpq-text-muted);
  margin-top: 2px;
}
</style>
