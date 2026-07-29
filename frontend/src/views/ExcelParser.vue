<template>
  <div class="excel-parser-debug">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>Excel 解析调试</h2>
      <a-space>
        <a-upload
          :before-upload="handleFileUpload"
          :show-upload-list="false"
          accept=".xlsx,.xls"
        >
          <a-button type="primary">
            <template #icon><UploadOutlined /></template>
            上传 Excel
          </a-button>
        </a-upload>
        <a-button @click="loadRules" :loading="loadingRules">
          <template #icon><ReloadOutlined /></template>
          刷新规则
        </a-button>
      </a-space>
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
          <template v-if="parseResult">
            <!-- 静态字段 -->
            <div class="result-section">
              <h4>静态字段</h4>
              <a-descriptions :column="1" size="small" bordered>
                <a-descriptions-item
                  v-for="(field, key) in parseResult.static_fields"
                  :key="key"
                  :label="String(key)"
                >
                  <div>{{ field.value }}</div>
                  <div class="source-info">
                    <a-tag size="small">行 {{ field.source.row + 1 }}</a-tag>
                    <a-tag size="small">列 {{ field.source.col_letter || field.source.col + 1 }}</a-tag>
                    <span v-if="field.source.keyword" class="keyword-tag">
                      关键词: {{ field.source.keyword }}
                    </span>
                  </div>
                </a-descriptions-item>
              </a-descriptions>
            </div>

            <!-- 动态区域 -->
            <div class="result-section">
              <h4>动态区域</h4>
              <a-collapse v-model:activeKey="expandedDynamicRegions" :bordered="false">
                <a-collapse-panel
                  v-for="(items, regionName) in parseResult.dynamic_regions"
                  :key="regionName"
                  :header="`${regionName} (${items.length} 行)`"
                >
                  <a-table
                    :dataSource="items.map((item: Record<string, any>, idx: number) => ({ ...item, _key: idx }))"
                    :columns="getDynamicColumns(items)"
                    :pagination="false"
                    size="small"
                    rowKey="_key"
                  >
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === '_trace'">
                        <a-tooltip>
                          <template #title>
                            <div v-for="trace in record._trace" :key="trace.field_key">
                              {{ trace.field_key }}: 行 {{ trace.source.row + 1 }}, 列 {{ trace.source.col_letter || trace.source.col + 1 }}
                            </div>
                          </template>
                          <a-tag color="blue">溯源</a-tag>
                        </a-tooltip>
                      </template>
                    </template>
                  </a-table>
                </a-collapse-panel>
              </a-collapse>
            </div>

            <!-- 解析追踪 -->
            <div class="result-section">
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
          </template>
          <template v-else>
            <a-empty description="上传 Excel 文件查看解析结果" />
          </template>
        </a-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { UploadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import ParseRulesEditor from '@/components/excel-parser/ParseRulesEditor.vue'
import ParseHeatmapPreview from '@/components/excel-parser/ParseHeatmapPreview.vue'
import { useExcelParser } from '@/composables/useExcelParser'

const {
  previewData, parseResult, parsing, loadingRules,
  expandedDynamicRegions, getDynamicColumns,
  loadRules, loadBusinessFields, loadMappings, handleFileUpload
} = useExcelParser()

onMounted(() => {
  loadRules()
  loadBusinessFields()
  loadMappings()
})
</script>

<style scoped>
.excel-parser-debug {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.page-header h2 {
  margin: 0;
  color: var(--cpq-text-light);
}

.three-column-layout {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow: hidden;
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

.source-info {
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.keyword-tag {
  margin-left: 8px;
  color: var(--cpq-color-primary);
}

.trace-detail {
  font-size: 11px;
  color: var(--cpq-text-muted);
  margin-top: 2px;
}
</style>
