<template>
  <div class="excel-parser-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>Excel 解析</h2>
      <a-space>
        <a-button
          v-if="parsedResult"
          @click="handleExportJson"
        >
          <template #icon><DownloadOutlined /></template>
          导出 JSON
        </a-button>
        <a-button
          v-if="parsedResult"
          @click="handleReset"
        >
          重置
        </a-button>
      </a-space>
    </div>

    <!-- 步骤条 -->
    <a-steps :current="currentStep" size="small" style="margin-bottom: 16px;">
      <a-step title="选择模板" />
      <a-step title="上传文件" />
      <a-step title="查看结果" />
    </a-steps>

    <!-- Step 1: 选择模板 -->
    <div v-if="currentStep === 0" class="step-content">
      <a-card title="选择解析模板" size="small">
        <a-select
          v-model:value="selectedTemplateId"
          placeholder="选择已保存的解析模板"
          style="width: 100%; max-width: 400px;"
          size="large"
          show-search
          :filter-option="filterOption"
          @change="onTemplateChange"
        >
          <a-select-option v-for="t in templateList" :key="t.id" :value="t.id">
            {{ t.name }}
            <span v-if="t.description" style="color: var(--cpq-text-muted); font-size: 12px; margin-left: 8px;">
              {{ t.description }}
            </span>
          </a-select-option>
        </a-select>

        <div v-if="selectedTemplate" class="template-info">
          <a-descriptions :column="2" size="small" bordered style="margin-top: 12px;">
            <a-descriptions-item label="模板名称">{{ selectedTemplate.name }}</a-descriptions-item>
            <a-descriptions-item label="创建时间">{{ formatDate(selectedTemplate.createdAt) }}</a-descriptions-item>
            <a-descriptions-item label="静态字段数">{{ selectedTemplate.staticBindings.length }}</a-descriptions-item>
            <a-descriptions-item label="动态区域数">{{ selectedTemplate.dynamicRegions.length }}</a-descriptions-item>
            <a-descriptions-item label="描述" :span="2">{{ selectedTemplate.description || '—' }}</a-descriptions-item>
          </a-descriptions>

          <a-button
            type="primary"
            style="margin-top: 12px;"
            @click="currentStep = 1"
          >
            下一步
          </a-button>
        </div>
      </a-card>
    </div>

    <!-- Step 2: 上传文件 -->
    <div v-if="currentStep === 1" class="step-content">
      <a-card title="上传 Excel 文件" size="small">
        <a-upload-dragger
          :before-upload="handleFileUpload"
          :show-upload-list="false"
          accept=".xlsx,.xls"
          :disabled="!selectedTemplate"
        >
          <p class="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p class="ant-upload-text">点击或拖拽 Excel 文件到此区域</p>
          <p class="ant-upload-hint">
            将使用模板「{{ selectedTemplate?.name }}」进行解析
          </p>
        </a-upload-dragger>

        <a-button style="margin-top: 12px;" @click="currentStep = 0">
          上一步
        </a-button>
      </a-card>
    </div>

    <!-- Step 3: 查看结果 -->
    <div v-if="currentStep === 2" class="step-content">
      <!-- 警告信息 -->
      <a-alert
        v-if="parsedResult && parsedResult.warnings.length > 0"
        type="warning"
        show-icon
        style="margin-bottom: 12px;"
      >
        <template #message>
          <div v-for="(w, i) in parsedResult.warnings" :key="i">{{ w }}</div>
        </template>
      </a-alert>

      <!-- 静态字段结果 -->
      <a-card
        v-if="parsedResult && Object.keys(parsedResult.staticData).length > 0"
        title="基础信息"
        size="small"
        style="margin-bottom: 12px;"
      >
        <a-form layout="inline" size="small">
          <a-form-item
            v-for="(_, key) in editableStaticData"
            :key="key"
            :label="String(key)"
          >
            <a-input
              v-model:value="editableStaticData[key]"
              style="width: 160px;"
            />
          </a-form-item>
        </a-form>
      </a-card>

      <!-- 动态区域结果 -->
      <template v-if="parsedResult">
        <a-card
          v-for="(rows, regionName) in parsedResult.dynamicData"
          :key="regionName"
          size="small"
          style="margin-bottom: 12px;"
        >
          <template #title>
            {{ regionName }}
            <a-tag color="blue">{{ rows.length }} 行</a-tag>
          </template>

          <a-table
            :dataSource="rows.map((r, i) => ({ ...r, _key: i }))"
            :columns="getDynamicColumns(rows)"
            :pagination="rows.length > 10 ? { pageSize: 10 } : false"
            size="small"
            rowKey="_key"
            :scroll="{ x: 'max-content' }"
          />
        </a-card>
      </template>

      <a-button style="margin-top: 12px;" @click="currentStep = 1">
        重新上传
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { DownloadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { useParseTemplateStore } from '@/store/parseTemplate'
import type { ParseTemplate, ParsedResult, ParsedRow } from '@/types/parseTemplate'
import { parseExcelByTemplate } from '@/utils/excel-parser'

const store = useParseTemplateStore()

const currentStep = ref(0)
const selectedTemplateId = ref<string | undefined>(undefined)
const selectedTemplate = ref<ParseTemplate | null>(null)
const parsedResult = ref<ParsedResult | null>(null)
const editableStaticData = reactive<Record<string, string | number | null>>({})

const templateList = computed(() => store.templateList)

// store 在创建时已自动加载数据，无需 onMounted

function filterOption(input: string, option: Record<string, unknown>) {
  const label = option.label as string | undefined
  return label?.toLowerCase().includes(input.toLowerCase())
}

function onTemplateChange(id: string | undefined) {
  if (!id) {
    selectedTemplate.value = null
    return
  }
  store.loadTemplate(id)
  selectedTemplate.value = store.currentTemplate
}

async function handleFileUpload(file: File) {
  if (!file.name.match(/\.xlsx?$/i)) {
    message.error('仅支持 .xlsx 格式')
    return false
  }
  if (!selectedTemplate.value) {
    message.warning('请先选择模板')
    return false
  }

  store.setParsing(true)
  try {
    const buffer = await file.arrayBuffer()
    const result = await parseExcelByTemplate(buffer, selectedTemplate.value)
    parsedResult.value = result

    // 初始化可编辑静态数据
    Object.keys(editableStaticData).forEach(k => delete editableStaticData[k])
    Object.assign(editableStaticData, result.staticData)

    currentStep.value = 2

    if (result.warnings.length > 0) {
      message.warning(`解析完成，但有 ${result.warnings.length} 条警告`)
    } else {
      message.success('解析完成')
    }
  } catch (err) {
    console.error(err)
    message.error('解析失败，请检查文件格式')
  } finally {
    store.setParsing(false)
  }
  return false
}

function handleReset() {
  parsedResult.value = null
  Object.keys(editableStaticData).forEach(k => delete editableStaticData[k])
  currentStep.value = 0
  selectedTemplateId.value = undefined
  selectedTemplate.value = null
}

function handleExportJson() {
  if (!parsedResult.value) return

  const exportData = {
    staticData: { ...editableStaticData },
    dynamicData: parsedResult.value.dynamicData,
    exportedAt: new Date().toISOString()
  }

  const json = JSON.stringify(exportData, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `parsed_${selectedTemplate.value?.name || 'data'}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  message.success('JSON 已导出')
}

function getDynamicColumns(rows: ParsedRow[]) {
  if (rows.length === 0) return []
  const keys = Object.keys(rows[0]).filter(k => k !== '_key')
  return keys.map(k => ({
    title: k,
    dataIndex: k,
    key: k,
    ellipsis: true
  }))
}

function formatDate(ts: number): string {
  return new Date(ts).toLocaleString('zh-CN')
}
</script>

<style scoped>
.excel-parser-page {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: auto;
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

.step-content {
  flex: 1;
  overflow: auto;
}

.template-info {
  margin-top: 8px;
}

.ant-upload-drag-icon {
  font-size: 48px;
  color: var(--cpq-color-info);
  margin-bottom: 12px;
}

.ant-upload-text {
  color: var(--cpq-text-light);
  font-size: 16px;
}

.ant-upload-hint {
  color: var(--cpq-text-muted);
}
</style>
