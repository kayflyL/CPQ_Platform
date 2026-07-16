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
        <a-card title="解析规则" size="small">
          <template #extra>
            <a-button size="small" @click="showAddRegionModal = true">
              + 区域
            </a-button>
          </template>

          <!-- 区域列表 -->
          <div class="rule-section">
            <h4>区域定义</h4>
            <a-collapse v-model:activeKey="expandedRegions" :bordered="false">
              <a-collapse-panel v-for="region in parseRegions" :key="region.id" :header="region.name">
                <template #extra>
                  <a-space>
                    <a-button size="small" @click.stop="editRegion(region)">编辑</a-button>
                    <a-popconfirm title="确定删除？" @confirm="deleteRegion(region.id)">
                      <a-button size="small" danger>删除</a-button>
                    </a-popconfirm>
                  </a-space>
                </template>
                <a-descriptions :column="1" size="small">
                  <a-descriptions-item label="起始关键词">{{ region.start_keywords || '—' }}</a-descriptions-item>
                  <a-descriptions-item label="结束关键词">{{ region.end_keywords || '—' }}</a-descriptions-item>
                  <a-descriptions-item label="跳过行数">{{ region.skip_header_rows }}</a-descriptions-item>
                </a-descriptions>
              </a-collapse-panel>
            </a-collapse>
          </div>

          <!-- 字段规则列表 -->
          <div class="rule-section">
            <h4>字段映射</h4>
            <a-button size="small" @click="showAddFieldRuleModal = true" style="margin-bottom: 8px;">
              + 字段规则
            </a-button>
            <a-table
              :dataSource="parseFieldRules"
              :columns="fieldRuleColumns"
              :pagination="false"
              size="small"
              rowKey="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'enabled'">
                  <a-tag :color="record.enabled ? 'green' : 'default'" size="small">
                    {{ record.enabled ? '✓' : '✗' }}
                  </a-tag>
                </template>
                <template v-if="column.key === 'action'">
                  <a-space :size="2">
                    <a-button type="link" size="small" @click="editFieldRule(record)">
                      <template #icon><EditOutlined /></template>
                    </a-button>
                    <a-popconfirm title="确定删除？" @confirm="deleteFieldRule(record.id)">
                      <a-button type="link" size="small" danger>
                        <template #icon><DeleteOutlined /></template>
                      </a-button>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </div>
        </a-card>
      </div>

      <!-- 中栏：Excel 热力图预览 -->
      <div class="center-panel">
        <a-card title="Excel 预览" size="small" :loading="parsing">
          <template v-if="previewData">
            <div class="heatmap-container">
              <table class="heatmap-table">
                <tbody>
                  <tr v-for="(row, rIdx) in previewData.grid" :key="rIdx">
                    <td
                      v-for="(cell, cIdx) in row"
                      :key="cIdx"
                      :class="getCellClass(rIdx, cIdx)"
                      :title="getCellTooltip(rIdx, cIdx)"
                    >
                      {{ cell }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- 图例 -->
            <div class="legend">
              <a-space>
                <span class="legend-item"><span class="legend-color header-region"></span>Header</span>
                <span class="legend-item"><span class="legend-color l6-region"></span>L6</span>
                <span class="legend-item"><span class="legend-color kp-region"></span>KP</span>
                <span class="legend-item"><span class="legend-color warranty-region"></span>Warranty</span>
                <span class="legend-item"><span class="legend-color keyword"></span>关键词</span>
                <span class="legend-item"><span class="legend-color extracted"></span>提取值</span>
              </a-space>
            </div>
          </template>
          <template v-else>
            <a-empty description="上传 Excel 文件查看预览" />
          </template>
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
                    :dataSource="items.map((item, idx) => ({ ...item, _key: idx }))"
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

    <!-- 添加/编辑区域弹窗 -->
    <a-modal
      v-model:open="showAddRegionModal"
      :title="editingRegion ? '编辑区域' : '添加区域'"
      @ok="saveRegion"
      @cancel="cancelEditRegion"
    >
      <a-form :model="regionForm" layout="vertical">
        <a-form-item label="区域名称" required>
          <a-input v-model:value="regionForm.name" placeholder="如: header, L6, KP, Warranty" />
        </a-form-item>
        <a-form-item label="起始关键词">
          <a-input v-model:value="regionForm.start_keywords" placeholder="多个关键词用逗号分隔" />
        </a-form-item>
        <a-form-item label="结束关键词">
          <a-input v-model:value="regionForm.end_keywords" placeholder="多个关键词用逗号分隔" />
        </a-form-item>
        <a-form-item label="跳过行数">
          <a-input-number v-model:value="regionForm.skip_header_rows" :min="0" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="regionForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 添加/编辑字段规则弹窗 -->
    <a-modal
      v-model:open="showAddFieldRuleModal"
      :title="editingFieldRule ? '编辑字段规则' : '添加字段规则'"
      @ok="saveFieldRule"
      @cancel="cancelEditFieldRule"
      width="600px"
    >
      <a-form :model="fieldRuleForm" layout="vertical">
        <a-form-item label="字段" required>
          <a-select v-model:value="fieldRuleForm.field_key" placeholder="选择字段" show-search :filter-option="filterOption">
            <a-select-option v-for="field in businessFields" :key="field.key" :value="field.key" :label="field.label">
              {{ field.label }} ({{ field.key }})
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="所属区域" required>
          <a-select v-model:value="fieldRuleForm.region" placeholder="选择区域">
            <a-select-option v-for="region in parseRegions" :key="region.name" :value="region.name">
              {{ region.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="提取方式" required>
          <a-radio-group v-model:value="fieldRuleForm.source_type">
            <a-radio value="keyword">关键词匹配</a-radio>
            <a-radio value="column">列提取</a-radio>
          </a-radio-group>
        </a-form-item>

        <!-- 关键词匹配配置 -->
        <template v-if="fieldRuleForm.source_type === 'keyword'">
          <a-form-item label="关键词列表" required>
            <a-select
              v-model:value="fieldRuleForm.source_config.keywords"
              mode="tags"
              placeholder="输入关键词后按回车"
              style="width: 100%;"
            />
          </a-form-item>
          <a-form-item label="值偏移量">
            <a-input-number
              v-model:value="fieldRuleForm.source_config.value_offset"
              :min="1"
              style="width: 100%;"
              placeholder="关键词右侧第几列取值"
            />
          </a-form-item>
        </template>

        <!-- 列提取配置 -->
        <template v-if="fieldRuleForm.source_type === 'column'">
          <a-form-item label="列字母" required>
            <a-input
              v-model:value="fieldRuleForm.source_config.col"
              placeholder="如: A, B, C, D"
              style="width: 100%;"
            />
          </a-form-item>
        </template>

        <a-form-item label="启用">
          <a-switch v-model:checked="fieldRuleForm.enabled" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="fieldRuleForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import axios from 'axios'

// 数据状态
const parseRegions = ref<any[]>([])
const parseFieldRules = ref<any[]>([])
const businessFields = ref<any[]>([])
const previewData = ref<any>(null)
const parseResult = ref<any>(null)
const loadingRules = ref(false)
const parsing = ref(false)
const uploadedFile = ref<File | null>(null)

// UI 状态
const expandedRegions = ref<string[]>([])
const expandedDynamicRegions = ref<string[]>([])
const showAddRegionModal = ref(false)
const showAddFieldRuleModal = ref(false)
const editingRegion = ref<any>(null)
const editingFieldRule = ref<any>(null)

// 表单状态
const regionForm = reactive({
  name: '',
  start_keywords: '',
  end_keywords: '',
  skip_header_rows: 0,
  sort_order: 0
})

const fieldRuleForm = reactive({
  field_key: '',
  region: '',
  source_type: 'column',
  source_config: {
    keywords: [] as string[],
    col: '',
    value_offset: 1
  },
  enabled: true,
  sort_order: 0
})

// 表格列定义
const fieldRuleColumns = [
  { title: '字段', dataIndex: 'field_key', key: 'field_key', width: 85, ellipsis: true },
  { title: '区域', dataIndex: 'region', key: 'region', width: 50 },
  { title: '状态', key: 'enabled', width: 45 },
  { title: '', key: 'action', width: 55 }
]

// 生命周期
onMounted(() => {
  loadRules()
  loadBusinessFields()
})

// 加载解析规则
async function loadRules() {
  loadingRules.value = true
  try {
    const [regionsRes, rulesRes] = await Promise.all([
      axios.get('/api/rules/parse-regions'),
      axios.get('/api/rules/parse-field-rules')
    ])
    parseRegions.value = regionsRes.data.regions
    parseFieldRules.value = rulesRes.data.rules
  } catch (error) {
    console.error('Failed to load rules:', error)
    message.error('加载规则失败')
  } finally {
    loadingRules.value = false
  }
}

// 加载业务字段
async function loadBusinessFields() {
  try {
    const res = await axios.get('/api/admin/business-fields')
    businessFields.value = Array.isArray(res.data) ? res.data : (res.data.fields || [])
  } catch (error) {
    console.error('Failed to load business fields:', error)
  }
}

// 上传文件并解析
async function handleFileUpload(file: File) {
  if (!file.name.match(/\.xlsx?$/i)) {
    message.error('仅支持 .xlsx 格式')
    return false
  }

  parsing.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)

    const res = await axios.post('/api/rules/excel-parser-preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    uploadedFile.value = file
    previewData.value = res.data.preview
    parseResult.value = res.data.parse_result

    // 自动展开动态区域
    if (parseResult.value.dynamic_regions) {
      expandedDynamicRegions.value = Object.keys(parseResult.value.dynamic_regions)
    }

    message.success('解析完成')
  } catch (error: any) {
    console.error('Parse failed:', error)
    message.error(error.response?.data?.detail || '解析失败')
  } finally {
    parsing.value = false
  }
  return false
}

// 用缓存文件刷新预览
async function refreshPreview() {
  if (!uploadedFile.value) return
  parsing.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadedFile.value)
    const res = await axios.post('/api/rules/excel-parser-preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    previewData.value = res.data.preview
    parseResult.value = res.data.parse_result
    if (parseResult.value.dynamic_regions) {
      expandedDynamicRegions.value = Object.keys(parseResult.value.dynamic_regions)
    }
  } catch (error: any) {
    console.error('Refresh preview failed:', error)
  } finally {
    parsing.value = false
  }
}

// 区域 CRUD
function editRegion(region: any) {
  editingRegion.value = region
  Object.assign(regionForm, region)
  showAddRegionModal.value = true
}

function cancelEditRegion() {
  editingRegion.value = null
  Object.assign(regionForm, {
    name: '',
    start_keywords: '',
    end_keywords: '',
    skip_header_rows: 0,
    sort_order: 0
  })
}

async function saveRegion() {
  if (!regionForm.name) {
    message.warning('请填写区域名称')
    return
  }

  try {
    if (editingRegion.value) {
      await axios.put(`/api/rules/parse-regions/${editingRegion.value.id}`, regionForm)
      message.success('更新成功')
    } else {
      await axios.post('/api/rules/parse-regions', { regions: [...parseRegions.value, regionForm] })
      message.success('添加成功')
    }
    showAddRegionModal.value = false
    cancelEditRegion()
    await loadRules()
    await refreshPreview()
  } catch (error) {
    console.error('Save region failed:', error)
    message.error('保存失败')
  }
}

async function deleteRegion(regionId: number) {
  try {
    await axios.delete(`/api/rules/parse-regions/${regionId}`)
    message.success('删除成功')
    await loadRules()
    await refreshPreview()
  } catch (error) {
    console.error('Delete region failed:', error)
    message.error('删除失败')
  }
}

// 字段规则 CRUD
function editFieldRule(rule: any) {
  editingFieldRule.value = rule
  Object.assign(fieldRuleForm, {
    ...rule,
    source_config: {
      keywords: rule.source_config.keywords || [],
      col: rule.source_config.col || '',
      value_offset: rule.source_config.value_offset || 1
    }
  })
  showAddFieldRuleModal.value = true
}

function cancelEditFieldRule() {
  editingFieldRule.value = null
  Object.assign(fieldRuleForm, {
    field_key: '',
    region: '',
    source_type: 'column',
    source_config: {
      keywords: [],
      col: '',
      value_offset: 1
    },
    enabled: true,
    sort_order: 0
  })
}

async function saveFieldRule() {
  if (!fieldRuleForm.field_key || !fieldRuleForm.region) {
    message.warning('请填写必填字段')
    return
  }

  try {
    if (editingFieldRule.value) {
      await axios.put(`/api/rules/parse-field-rules/${editingFieldRule.value.id}`, fieldRuleForm)
      message.success('更新成功')
    } else {
      await axios.post('/api/rules/parse-field-rules', { rules: [...parseFieldRules.value, fieldRuleForm] })
      message.success('添加成功')
    }
    showAddFieldRuleModal.value = false
    cancelEditFieldRule()
    await loadRules()
    await refreshPreview()
  } catch (error) {
    console.error('Save field rule failed:', error)
    message.error('保存失败')
  }
}

async function deleteFieldRule(ruleId: number) {
  try {
    await axios.delete(`/api/rules/parse-field-rules/${ruleId}`)
    message.success('删除成功')
    await loadRules()
    await refreshPreview()
  } catch (error) {
    console.error('Delete field rule failed:', error)
    message.error('删除失败')
  }
}

// 辅助函数
function filterOption(input: string, option: any) {
  return option.label?.toLowerCase().includes(input.toLowerCase())
}

function getDynamicColumns(items: any[]) {
  if (items.length === 0) return []
  const keys = Object.keys(items[0]).filter(k => !k.startsWith('_'))
  return [
    ...keys.map(k => ({
      title: k,
      dataIndex: k,
      key: k,
      ellipsis: true
    })),
    {
      title: '溯源',
      key: '_trace',
      width: 80
    }
  ]
}

// 动态颜色映射
const regionColorMap = computed(() => {
  const map: Record<string, string> = {
    'header': 'cell-header',
    'l6': 'cell-l6',
    'kp': 'cell-kp',
    'warranty': 'cell-warranty'
  }
  
  // 备用色板（用于新增区域）
  const palette = [
    'cell-region-1', 'cell-region-2', 'cell-region-3', 
    'cell-region-4', 'cell-region-5', 'cell-region-6'
  ]
  let paletteIdx = 0
  
  if (previewData.value?.region_bounds) {
    for (const regionName of Object.keys(previewData.value.region_bounds)) {
      const key = regionName.toLowerCase()
      if (!(key in map)) {
        map[key] = palette[paletteIdx % palette.length]
        paletteIdx++
      }
    }
  }
  
  return map
})

function getCellClass(row: number, col: number): string {
  if (!previewData.value?.cell_marks) return ''
  
  const mark = previewData.value.cell_marks.find(
    (m: any) => Number(m.row) === row && Number(m.col) === col
  )
  
  if (!mark) return ''
  
  if (mark.type === 'keyword') return 'cell-keyword'
  if (mark.type === 'extracted') return 'cell-extracted'
  
  // 动态区域颜色：从 type 提取区域名（如 "l6_region" -> "l6"）
  const regionKey = mark.type.replace('_region', '').toLowerCase()
  return regionColorMap.value[regionKey] || ''
}

function getCellTooltip(row: number, col: number): string {
  if (!previewData.value?.cell_marks) return ''
  
  const mark = previewData.value.cell_marks.find(
    (m: any) => Number(m.row) === row && Number(m.col) === col
  )
  
  if (!mark) return ''
  
  return `${mark.target}: ${mark.value}`
}
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

.rule-section {
  margin-bottom: 16px;
}

.rule-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-light);
}

.heatmap-container {
  overflow: auto;
  max-height: 500px;
  border: 1px solid var(--cpq-border);
  border-radius: 4px;
  background-color: #fff;
}

.heatmap-table {
  border-collapse: collapse;
  font-size: 12px;
  width: 100%;
}

.heatmap-table td {
  border: 1px solid #ddd;
  padding: 4px 8px;
  min-width: 80px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
}

.cell-keyword {
  background-color: #fff3cd;
  font-weight: 600;
}

.cell-extracted {
  background-color: #d4edda;
  font-weight: 600;
}

.cell-header {
  background-color: #e7f3ff;
}

.cell-l6 {
  background-color: #fff4e6;
}

.cell-kp {
  background-color: #f3e5f5;
}

.cell-warranty {
  background-color: #e8f5e9;
}

.cell-region-1 { background-color: #fce4ec; }
.cell-region-2 { background-color: #e0f7fa; }
.cell-region-3 { background-color: #fff8e1; }
.cell-region-4 { background-color: #ede7f6; }
.cell-region-5 { background-color: #e8eaf6; }
.cell-region-6 { background-color: #efebe9; }

.legend {
  margin-top: 12px;
  padding: 8px;
  background: var(--cpq-bg-secondary);
  border-radius: 4px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.legend-color {
  display: inline-block;
  width: 16px;
  height: 16px;
  border-radius: 2px;
}

.legend-color.keyword {
  background-color: #fff3cd;
}

.legend-color.extracted {
  background-color: #d4edda;
}

.legend-color.header-region {
  background-color: #e7f3ff;
}

.legend-color.l6-region {
  background-color: #fff4e6;
}

.legend-color.kp-region {
  background-color: #f3e5f5;
}

.legend-color.warranty-region {
  background-color: #e8f5e9;
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
