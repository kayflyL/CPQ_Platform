<template>
  <div class="template-editor-page">
    <div class="page-header">
      <div class="header-left">
        <a-button @click="goBack" size="small">
          <template #icon><ArrowLeftOutlined /></template>
        </a-button>
        <a-form layout="inline" size="small">
          <a-form-item label="模板名称">
            <a-input
              v-model:value="templateNameInput"
              placeholder="输入模板名称"
              style="width: 200px;"
              @change="onNameChange"
            />
          </a-form-item>
        </a-form>
        <a-tag v-if="template?.is_default" color="gold">默认</a-tag>
      </div>
      <a-space>
        <a-button type="primary" :loading="saving" @click="handleSave">
          <template #icon><SaveOutlined /></template>
          保存
        </a-button>
      </a-space>
    </div>

    <div v-if="loading" class="loading-state">
      <a-spin tip="加载模板中..." />
    </div>
    <div v-else-if="template" class="editor-content">
        <!-- 上排：三栏布局 -->
        <div class="editor-layout">
          <!-- 左栏：页面切换 + 业务字段 -->
          <div class="left-panel glass">
            <a-segmented v-model:value="activePage" :options="pageOptions" block style="margin-bottom: 12px;" />
            <a-input
              v-model:value="fieldSearch"
              placeholder="搜索字段..."
              allow-clear
              size="small"
              style="margin-bottom: 12px;"
            />
            <div class="panel-title">业务字段</div>
            <!-- 封面页字段 -->
            <template v-if="activePage === 'cover'">
              <a-collapse v-model:activeKey="expandedCategories" ghost>
                <a-collapse-panel v-if="filteredOpportunityFields.length" key="opportunity" header="商机级字段">
                  <div
                    v-for="field in filteredOpportunityFields"
                    :key="field.key"
                    class="field-item"
                    :class="{ 'field-active': currentFieldKey === field.key }"
                    @click="selectField(field)"
                  >
                    <span class="field-label">{{ field.label }}</span>
                    <span class="field-key">{{ field.key }}</span>
                  </div>
                </a-collapse-panel>
                <a-collapse-panel v-if="filteredSystemFields.length" key="system" header="系统字段">
                  <div
                    v-for="field in filteredSystemFields"
                    :key="field.key"
                    class="field-item"
                    :class="{ 'field-active': currentFieldKey === field.key }"
                    @click="selectField(field)"
                  >
                    <span class="field-label">{{ field.label }}</span>
                    <span class="field-key">{{ field.key }}</span>
                  </div>
                </a-collapse-panel>
              </a-collapse>
            </template>
            <!-- 配置页字段 -->
            <template v-else>
              <a-collapse v-model:activeKey="expandedCategories" ghost>
                <a-collapse-panel v-if="filteredItemFields.length" key="item" header="配置项字段">
                  <div
                    v-for="field in filteredItemFields"
                    :key="field.key"
                    class="field-item"
                    :class="{ 'field-active': currentFieldKey === field.key }"
                    @click="selectField(field)"
                  >
                    <span class="field-label">{{ field.label }}</span>
                    <span class="field-key">{{ field.key }}</span>
                  </div>
                </a-collapse-panel>
                <a-collapse-panel v-if="filteredL6Fields.length" key="l6" header="L6 价格库字段">
                  <div
                    v-for="field in filteredL6Fields"
                    :key="field.key"
                    class="field-item"
                    :class="{ 'field-active': currentFieldKey === field.key }"
                    @click="selectField(field)"
                  >
                    <span class="field-label">{{ field.label }}</span>
                    <span class="field-key">{{ field.key }}</span>
                  </div>
                </a-collapse-panel>
                <a-collapse-panel v-if="filteredKpFields.length" key="kp" header="KP 价格库字段">
                  <div
                    v-for="field in filteredKpFields"
                    :key="field.key"
                    class="field-item"
                    :class="{ 'field-active': currentFieldKey === field.key }"
                    @click="selectField(field)"
                  >
                    <span class="field-label">{{ field.label }}</span>
                    <span class="field-key">{{ field.key }}</span>
                  </div>
                </a-collapse-panel>
              </a-collapse>
            </template>
          </div>

          <!-- 中栏：上传 + 预览 -->
          <div class="center-panel glass">
            <div class="upload-section glass-light">
              <a-upload
                :before-upload="(file) => handleUpload(file, activePage)"
                :show-upload-list="false"
                accept=".xlsx,.xls"
              >
                <a-button size="small">
                  <template #icon><UploadOutlined /></template>
                  上传 Excel
                </a-button>
              </a-upload>
              <span v-if="currentTemplateData" class="file-info">
                {{ currentTemplateData.fileName }}
                <a-tag color="blue">{{ currentTemplateData.sheets.length }} 个工作表</a-tag>
              </span>
            </div>
            <div class="preview-header">
              <span class="preview-title">实时预览</span>
              <a-space size="small">
                <!-- 数据源选择器 -->
                <a-select
                  v-model:value="selectedProjectId"
                  placeholder="选择商机"
                  size="small"
                  style="width: 180px;"
                  show-search
                  :filter-option="filterOption"
                >
                  <a-select-option value="">无商机</a-select-option>
                  <a-select-option v-for="p in opportunities" :key="p.opportunity_id" :value="p.opportunity_id">
                    {{ p.customer_name }} - {{ p.opportunity_name }}
                  </a-select-option>
                </a-select>
                <a-select
                  v-model:value="selectedQuotationId"
                  placeholder="选择报价单"
                  size="small"
                  style="width: 140px;"
                  show-search
                  :filter-option="filterOption"
                  :disabled="!selectedProjectId"
                >
                  <a-select-option value="">无报价单</a-select-option>
                  <a-select-option v-for="q in quotations" :key="q.quotation_id" :value="q.quotation_id">
                    {{ q.version || '未命名' }} ({{ q.created_at?.slice(0, 10) }})
                  </a-select-option>
                </a-select>
                <a-switch
                  v-model:checked="previewEnabled"
                  checked-children="数据预览"
                  un-checked-children="纯预览"
                  size="small"
                />
                <a-switch
                  v-model:checked="heatmapEnabled"
                  checked-children="热力图"
                  un-checked-children="纯预览"
                  size="small"
                />
                <a-button-group size="small">
                  <a-button @click="zoomOut" :disabled="previewScale <= MIN_SCALE">
                    <ZoomOutOutlined />
                  </a-button>
                  <a-button @click="resetZoom" style="min-width: 50px;">
                    {{ Math.round(previewScale * 100) }}%
                  </a-button>
                  <a-button @click="zoomIn" :disabled="previewScale >= MAX_SCALE">
                    <ZoomInOutlined />
                  </a-button>
                </a-button-group>
              </a-space>
            </div>
            <div v-if="!currentTemplateData" class="preview-empty">
              上传 Excel 模板后显示预览
            </div>
            <div v-else class="preview-area">
              <div class="excel-preview-scaler" :style="{ transform: `scale(${previewScale})`, transformOrigin: 'top left' }">
                <ExcelTable
                  :sheets="expandedSheets"
                  :overlayMap="heatmapEnabled ? currentOverlayMap : emptyOverlayMap"
                  :previewData="previewEnabled ? currentPreviewData : undefined"
                  @cell-click="onCellClick"
                />
              </div>
              <div v-if="heatmapEnabled" class="heatmap-legend">
                <div class="legend-item">
                  <span class="legend-color" style="background: rgba(0, 245, 212, 0.20);"></span>
                  静态字段
                </div>
                <div class="legend-item">
                  <span class="legend-color" style="background: rgba(0, 245, 212, 0.40);"></span>
                  动态行
                </div>
              </div>
            </div>
          </div>

          <!-- 右栏：单元格绑定 -->
          <div class="right-panel glass">
            <div class="panel-title">单元格绑定</div>
            <div v-if="!selectedCell" class="empty-hint">
              点击表格中的单元格进行绑定
            </div>
            <div v-else class="binding-form">
              <a-descriptions :column="1" size="small" bordered>
                <a-descriptions-item label="工作表">
                  {{ currentSheetName }}
                </a-descriptions-item>
                <a-descriptions-item label="单元格">
                  {{ selectedCellAddress }}
                </a-descriptions-item>
                <a-descriptions-item label="当前值">
                  {{ selectedCell.value ?? '(空)' }}
                </a-descriptions-item>
              </a-descriptions>

              <div class="binding-actions">
                <a-form layout="vertical" size="small">
                  <a-form-item label="数据类型">
                    <a-radio-group v-model:value="bindingForm.dataType">
                      <a-radio value="static">静态字段</a-radio>
                      <a-radio value="dynamic">动态行</a-radio>
                    </a-radio-group>
                  </a-form-item>

                  <a-form-item v-if="bindingForm.dataType === 'static'" label="绑定字段">
                    <a-select
                      v-model:value="bindingForm.fieldKey"
                      placeholder="选择业务字段"
                      allow-clear
                      show-search
                      :filter-option="filterOption"
                    >
                      <template v-if="activePage === 'cover'">
                        <a-select-opt-group label="商机级字段">
                          <a-select-option v-for="f in opportunityFields" :key="f.key" :value="f.key">
                            {{ f.label }}
                          </a-select-option>
                        </a-select-opt-group>
                        <a-select-opt-group label="系统字段">
                          <a-select-option v-for="f in systemFields" :key="f.key" :value="f.key">
                            {{ f.label }}
                          </a-select-option>
                        </a-select-opt-group>
                      </template>
                      <template v-else>
                        <a-select-opt-group label="配置项字段">
                          <a-select-option v-for="f in itemFields" :key="f.key" :value="f.key">
                            {{ f.label }}
                          </a-select-option>
                        </a-select-opt-group>
                        <a-select-opt-group label="L6 价格库字段">
                          <a-select-option v-for="f in l6Fields" :key="f.key" :value="f.key">
                            {{ f.label }}
                          </a-select-option>
                        </a-select-opt-group>
                        <a-select-opt-group label="KP 价格库字段">
                          <a-select-option v-for="f in kpFields" :key="f.key" :value="f.key">
                            {{ f.label }}
                          </a-select-option>
                        </a-select-opt-group>
                      </template>
                    </a-select>
                  </a-form-item>

                  <!-- 动态行：引用解析区域 -->
                  <template v-if="bindingForm.dataType === 'dynamic'">
                    <a-form-item label="引用解析区域">
                      <a-select
                        v-model:value="bindingForm.regionFieldKey"
                        placeholder="选择解析模板中定义的动态区域"
                        allow-clear
                        show-search
                        :filter-option="filterOption"
                        @change="onRegionFieldKeyChange"
                      >
                        <a-select-opt-group label="解析模板动态区域">
                          <a-select-option v-for="f in parseRegionOptions" :key="f.key" :value="f.key">
                            {{ f.label }}
                          </a-select-option>
                        </a-select-opt-group>
                      </a-select>
                    </a-form-item>

                    <!-- 字段映射表（可调整） -->
                    <a-form-item v-if="Object.keys(bindingForm.fieldMapping).length > 0" label="列对应关系">
                      <div class="field-mapping-table">
                        <div v-for="(col, field) in bindingForm.fieldMapping" :key="field" class="field-mapping-row">
                          <span class="field-name">{{ getFieldLabel(field) }}</span>
                          <a-select
                            :value="col"
                            @change="(val: string) => bindingForm.fieldMapping[field] = val"
                            size="small"
                            style="width: 80px;"
                          >
                            <a-select-option v-for="l in columnLetters" :key="l" :value="l">{{ l }}</a-select-option>
                          </a-select>
                          <a-button type="link" danger size="small" @click="removeExportFieldMapping(field)">×</a-button>
                        </div>
                        <div class="add-field-row">
                          <a-select 
                            v-model:value="newExportFieldKey" 
                            placeholder="选择字段" 
                            size="small" 
                            style="width: 140px;"
                            show-search
                            :filter-option="filterOption"
                          >
                            <a-select-option v-for="f in availableFieldsForAdd" :key="f.key" :value="f.key">
                              {{ f.label }}
                            </a-select-option>
                          </a-select>
                          <a-select v-model:value="newExportFieldCol" placeholder="列" size="small" style="width: 80px;">
                            <a-select-option v-for="l in columnLetters" :key="l" :value="l">{{ l }}</a-select-option>
                          </a-select>
                          <a-button size="small" @click="addExportFieldMapping">+</a-button>
                        </div>
                      </div>
                    </a-form-item>

                    <!-- 描述模板配置（仅当 regionFieldKey 为 config_summary 时显示） -->
                    <template v-if="bindingForm.regionFieldKey === 'config_summary'">
                      <a-form-item>
                        <template #label>
                          <span>
                            描述生成规则
                            <a-tooltip title="当 description 列需要自动生成文本时使用。例如 {kp_list} 会展开为配件列表。">
                              <InfoCircleOutlined style="margin-left: 4px; color: #999;" />
                            </a-tooltip>
                          </span>
                        </template>
                        <a-input
                          v-model:value="bindingForm.descriptionTemplate"
                          placeholder="例如：{kp_list} 或 {l6_list} + {kp_list}"
                        />
                        <div class="template-hint">
                          可用变量：{l6_list}, {kp_list}, {warranty_list}, {all_list}
                        </div>
                      </a-form-item>
                      <a-form-item label="分隔符">
                        <a-input
                          v-model:value="bindingForm.descriptionSeparator"
                          placeholder="默认：,"
                          style="width: 120px;"
                        />
                      </a-form-item>
                    </template>

                    <a-form-item>
                      <template #label>
                        <span>
                          样式模板行号
                          <a-tooltip title="用于继承格式，留空则不继承。系统会复制该行的字体、边框等样式到动态插入的所有行。">
                            <InfoCircleOutlined style="margin-left: 4px; color: #999;" />
                          </a-tooltip>
                        </span>
                      </template>
                      <a-input-number v-model:value="bindingForm.templateRow" :min="1" />
                    </a-form-item>
                  </template>
                </a-form>

                <a-space>
                  <a-button type="primary" size="small" @click="saveBinding">
                    保存绑定
                  </a-button>
                  <a-button size="small" @click="removeBinding">
                    移除绑定
                  </a-button>
                </a-space>
              </div>

              <div class="binding-list" v-if="currentBindings.length > 0">
                <div class="panel-subtitle">已绑定 ({{ currentBindings.length }})</div>
                <div
                  v-for="b in currentBindings"
                  :key="b.id"
                  class="binding-item clickable"
                  @click="onBindingItemClick(b)"
                >
                  <span class="binding-cell">{{ b.cellAddress }}</span>
                  <span class="binding-field">{{ getFieldLabel(b.fieldKey) }}</span>
                  <a-tag :color="b.dataType === 'static' ? 'blue' : 'green'" size="small">
                    {{ b.dataType === 'static' ? '静态' : '动态' }}
                  </a-tag>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 下排：绑定总览 -->
        <div class="bottom-panel glass-light">
          <div class="panel-title">绑定总览</div>
          <div class="binding-overview">
            <div class="overview-columns">
              <!-- 封面页绑定 -->
              <div class="overview-section">
                <div class="overview-title">
                  <span class="legend-color" style="background: rgba(0, 245, 212, 0.20);"></span>
                  封面页 ({{ coverTemplateData?.bindings.length || 0 }})
                </div>
                <div v-if="!coverTemplateData?.bindings.length" class="overview-empty">暂无绑定</div>
                <div v-else class="overview-table-wrap">
                  <table class="overview-table">
                    <thead><tr><th>单元格</th><th>字段</th><th>类型</th></tr></thead>
                    <tbody>
                      <tr
                        v-for="b in coverTemplateData?.bindings"
                        :key="b.id"
                        class="overview-row"
                        @click="onOverviewBindingClick(b, 'cover')"
                      >
                        <td class="mono">{{ b.cellAddress }}</td>
                        <td>{{ getFieldLabel(b.fieldKey) }}</td>
                        <td><a-tag :color="b.dataType === 'static' ? 'blue' : 'green'" size="small">{{ b.dataType === 'static' ? '静态' : '动态' }}</a-tag></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <!-- 配置页绑定 -->
              <div class="overview-section">
                <div class="overview-title">
                  <span class="legend-color" style="background: rgba(0, 245, 212, 0.40);"></span>
                  配置页 ({{ configTemplateData?.bindings.length || 0 }})
                </div>
                <div v-if="!configTemplateData?.bindings.length" class="overview-empty">暂无绑定</div>
                <div v-else class="overview-table-wrap">
                  <table class="overview-table">
                    <thead><tr><th>单元格</th><th>字段</th><th>类型</th></tr></thead>
                    <tbody>
                      <tr
                        v-for="b in configTemplateData?.bindings"
                        :key="b.id"
                        class="overview-row"
                        @click="onOverviewBindingClick(b, 'config')"
                      >
                        <td class="mono">{{ b.cellAddress }}</td>
                        <td>{{ getFieldLabel(b.fieldKey) }}</td>
                        <td><a-tag :color="b.dataType === 'static' ? 'blue' : 'green'" size="small">{{ b.dataType === 'static' ? '静态' : '动态' }}</a-tag></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  SaveOutlined,
  UploadOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  InfoCircleOutlined
} from '@ant-design/icons-vue'
import { useTemplateStore } from '@/store/template'
import { useParseTemplateStore } from '@/store/parseTemplate'
import { useSettingsStore } from '@/store/settings'
import type { RenderCell, BusinessField, BindingDataType, TemplateData, CellBinding } from '@/types/template'
import { exportTemplateApi, projectApi, quotationApi } from '@/api'
import type { ExportTemplate } from '@/types/template'
import type { Opportunity, Quotation } from '@/types/opportunity'
import ExcelTable from '@/components/ExcelTable.vue'
import { parseExcelTemplate } from '@/utils/excel-generator'

const route = useRoute()
const router = useRouter()
const store = useTemplateStore()
const settingsStore = useSettingsStore()
const templateId = computed(() => Number(route.params.id))

const template = ref<ExportTemplate | null>(null)
const loading = ref(false)
const saving = ref(false)
const activePage = ref<'cover' | 'config'>('cover')
const templateNameInput = ref('')
const previewEnabled = ref(false)
const fieldSearch = ref('')

const pageOptions = [
  { label: '封面页', value: 'cover' },
  { label: '配置页', value: 'config' }
]

// 封面页和配置页的模板数据
const coverTemplateData = ref<TemplateData | null>(null)
const configTemplateData = ref<TemplateData | null>(null)

// 当前激活的模板数据（根据页面切换）
const currentTemplateData = computed(() => {
  return activePage.value === 'cover' ? coverTemplateData.value : configTemplateData.value
})

// 扩展工作表：根据动态绑定的数据量插入额外行
const expandedSheets = computed(() => {
  const templateData = currentTemplateData.value
  if (!templateData) return []
  
  // 深拷贝 sheets
  const sheets = templateData.sheets.map(sheet => ({
    ...sheet,
    cells: sheet.cells.map(row => row.map(cell => ({ ...cell }))),
    rowHeights: sheet.rowHeights ? { ...sheet.rowHeights } : undefined
  }))
  
  // 处理每个动态绑定
  for (const binding of templateData.bindings) {
    if (binding.dataType !== 'dynamic') continue
    
    const regionKey = binding.regionFieldKey || ''
    const dataArray: any[] = previewDataSource.value[regionKey] || []
    const startRow = binding.templateRow || 1
    
    if (dataArray.length <= 1) continue // 模板已有 1 行，无需扩展
    
    const sheetIdx = sheets.findIndex(s => s.name === binding.sheetName)
    if (sheetIdx < 0) continue
    const sheet = sheets[sheetIdx]
    
    // 需要额外插入的行数
    const extraRows = dataArray.length - 1
    
    // 在 startRow 之后插入 extraRows 行
    // 找到 startRow 对应的 cells 索引（0-indexed）
    const insertAfterIdx = startRow - 1 // startRow 是 1-indexed
    
    // 创建新行（复制模板行的样式）
    const templateRowCells = sheet.cells[insertAfterIdx]
    if (!templateRowCells) continue
    
    const newRows: RenderCell[][] = []
    for (let i = 0; i < extraRows; i++) {
      const newRow = templateRowCells.map(cell => ({
        ...cell,
        row: startRow + i + 1, // 1-indexed row number
        value: null, // 清空值，由 previewData 填充
        isMerged: false,
        rowSpan: 1,
        merge: undefined
      }))
      newRows.push(newRow)
    }
    
    // 插入新行
    sheet.cells.splice(insertAfterIdx + 1, 0, ...newRows)
    
    // 更新 rowCount
    sheet.rowCount += extraRows
    
    // 更新后续行的 row 索引
    for (let r = insertAfterIdx + extraRows + 1; r < sheet.cells.length; r++) {
      for (const cell of sheet.cells[r]) {
        cell.row = r + 1 // 1-indexed
      }
    }
    
    // 复制行高
    if (sheet.rowHeights) {
      const templateHeight = sheet.rowHeights[startRow] || 20
      for (let i = 0; i < extraRows; i++) {
        sheet.rowHeights[startRow + i + 1] = templateHeight
      }
    }
  }
  
  return sheets
})

// 当前页面的热力图覆盖映射
const currentOverlayMap = computed(() => {
  return activePage.value === 'cover' ? coverOverlayMap.value : configOverlayMap.value
})

// 当前页面的预览数据映射
const currentPreviewData = computed(() => {
  if (!previewEnabled.value) return {}
  return activePage.value === 'cover' ? coverPreviewData.value : configPreviewData.value
})

const expandedCategories = ref<string[]>(['opportunity', 'item', 'l6', 'kp', 'system'])
const currentFieldKey = ref<string>('')
const selectedCell = ref<RenderCell | null>(null)

// 热力图开关
const heatmapEnabled = ref(false)
const emptyOverlayMap = {}

// 预览数据源：商机 + 报价单选择
const opportunities = ref<Opportunity[]>([])
const quotations = ref<Quotation[]>([])
const selectedProjectId = ref<string>('')
const selectedQuotationId = ref<string>('')
const previewDataSource = ref<Record<string, any>>({}) // 真实数据：商机+报价单字段值
const previewLoading = ref(false)

// 缩放控制
const previewScale = ref(1)
const MIN_SCALE = 0.5
const MAX_SCALE = 2
const SCALE_STEP = 0.1

function zoomIn() {
  if (previewScale.value < MAX_SCALE) {
    previewScale.value = Math.min(MAX_SCALE, +(previewScale.value + SCALE_STEP).toFixed(1))
  }
}

function zoomOut() {
  if (previewScale.value > MIN_SCALE) {
    previewScale.value = Math.max(MIN_SCALE, +(previewScale.value - SCALE_STEP).toFixed(1))
  }
}

function resetZoom() {
  previewScale.value = 1
}

// ── 预览数据源：加载商机列表 ──
async function loadProjects() {
  try {
    const resp = await projectApi.list({ include_deleted: false })
    opportunities.value = resp.items || []
    // 默认选中最新商机（列表第一项）
    if (opportunities.value.length > 0 && !selectedProjectId.value) {
      selectedProjectId.value = opportunities.value[0].opportunity_id
    }
  } catch (e) {
    console.error('[loadProjects] failed:', e)
  }
}

// ── 预览数据源：加载选中商机的报价单列表 ──
async function loadQuotationsForProject(opportunityId: string) {
  if (!opportunityId) {
    quotations.value = []
    selectedQuotationId.value = ''
    return
  }
  try {
    const list = await quotationApi.list(opportunityId)
    quotations.value = list || []
    // 默认选中最新报价单
    if (quotations.value.length > 0) {
      selectedQuotationId.value = quotations.value[0].quotation_id
    } else {
      selectedQuotationId.value = ''
    }
  } catch (e) {
    console.error('[loadQuotations] failed:', e)
    quotations.value = []
    selectedQuotationId.value = ''
  }
}

// ── 预览数据源：加载选中报价单的真实数据 ──
async function loadPreviewDataSource() {
  const opportunityId = selectedProjectId.value
  const quotationId = selectedQuotationId.value
  previewDataSource.value = {}
  
  if (!opportunityId) {
    return  // 没有商机就不加载
  }
  
  previewLoading.value = true
  try {
    // 加载商机级数据
    const resp = await projectApi.getById(opportunityId)
    // API 返回结构: {status, meta: {...}, configs: {...}, quotations: [...]}
    const p = resp.meta || {}
    previewDataSource.value = {
      // 商机级字段映射
      customer_name: p.customer_name || '',
      opportunity_name: p.opportunity_name || '',
      platform_type: p.platform_type || '',
      chassis_form: p.chassis_form || '',
      sales_person: p.sales_person || '',
      fae: p.fae || '',
      total_qty: p.total_qty ?? 0,
      l6_spec: p.l6_spec || '',
      model_name: p.model_name || '',
    }
    
    // 加载配置级数据（L6/KP）- 仅当有报价单时
    if (quotationId) {
      const q = await quotationApi.getById(quotationId)
      if (q) {
        // 报价单级别字段
        previewDataSource.value.quotation_date = q.quotation_date || q.created_at?.slice(0, 10) || ''
        previewDataSource.value.version = q.version || ''
        previewDataSource.value.l6_price = q.l6_price ?? 0
        previewDataSource.value.total_price = q.total_price ?? 0
        previewDataSource.value.profit_margin = q.profit_margin ?? 0
        
        // 提取配置级别数量（从 config_quantities 字段）
        // 后端返回的可能是对象或 JSON 字符串，需要兼容处理
        let configQuantities = q.config_quantities || {}
        if (typeof configQuantities === 'string') {
          try {
            configQuantities = JSON.parse(configQuantities)
          } catch (e) {
            configQuantities = {}
          }
        }
        
        // 提取配置级别服务器型号（从 config_server_models 字段）
        let configServerModels = q.config_server_models || {}
        if (typeof configServerModels === 'string') {
          try {
            configServerModels = JSON.parse(configServerModels)
          } catch (e) {
            configServerModels = {}
          }
        }
        
        // 加载所有 items（用于动态展开）
        const items = q.items || []
        previewDataSource.value.all_items = items
        
        // 按 category 分类 items
        const l6_items: any[] = []
        const kp_items: any[] = []
        const warranty_items: any[] = []
        
        items.forEach((item: any, idx: number) => {
          const itemWithNo = { ...item, item_no: item.item_no || idx + 1 }
          const category = item.category || ''
          if (category === 'L6') {
            l6_items.push(itemWithNo)
          } else if (category === 'Key Parts') {
            kp_items.push(itemWithNo)
          } else if (category === 'Warranty') {
            warranty_items.push(itemWithNo)
          }
        })
        
        previewDataSource.value.l6_details = l6_items
        previewDataSource.value.kp_details = kp_items
        previewDataSource.value.warranty_details = warranty_items
        
        // 构建 config_summary（每个配置一行）
        const configSummary: any[] = []
        const configGroups = new Map<string, any[]>()
        items.forEach((item: any) => {
          const cfgName = item.config_name || 'Default'
          if (!configGroups.has(cfgName)) {
            configGroups.set(cfgName, [])
          }
          configGroups.get(cfgName)!.push(item)
        })
        
        let seq = 1
        configGroups.forEach((cfgItems, cfgName) => {
          // 计算 unit_price = L6 + KP + Warranty
          const l6Sum = cfgItems.filter(i => i.category === 'L6').reduce((sum, i) => sum + (i.final_price || 0) * (i.qty || 1), 0)
          const kpSum = cfgItems.filter(i => i.category === 'Key Parts').reduce((sum, i) => sum + (i.final_price || 0) * (i.qty || 1), 0)
          const warrantySum = cfgItems.filter(i => i.category === 'Warranty').reduce((sum, i) => sum + (i.final_price || 0) * (i.qty || 1), 0)
          const unitPrice = l6Sum + kpSum + warrantySum
          
          // 提取 model_name（从第一个 L6 item）
          const firstL6 = cfgItems.find(i => i.category === 'L6')
          const modelName = firstL6?.model_name || firstL6?.spec || ''
          
          // 提取 KP 级别字段（用于字段列映射）
          const kpItems = cfgItems.filter(i => i.category === 'Key Parts')
          const firstKp = kpItems[0] || {}
          
          // 构建 description（默认模板）
          let desc = ''
          const descTemplate = '{kp_list}'
          const separator = ','
          
          // 提取各部分列表
          const l6List = cfgItems.filter(i => i.category === 'L6').map(i => i.model_name || i.spec || '').filter(Boolean)
          const kpList = cfgItems.filter(i => i.category === 'Key Parts').map(i => `${i.part_name || i.spec} × ${i.qty || 1}`).filter(Boolean)
          const warrantyList = cfgItems.filter(i => i.category === 'Warranty').map(i => `${i.part_name || i.spec} × ${i.qty || 1}`).filter(Boolean)
          const allList = [...l6List, ...kpList, ...warrantyList]
          
          // 替换模板变量
          desc = descTemplate
            .replace(/\{l6_list\}/g, l6List.join(separator))
            .replace(/\{kp_list\}/g, kpList.join(separator))
            .replace(/\{warranty_list\}/g, warrantyList.join(separator))
            .replace(/\{all_list\}/g, allList.join(separator))
          
          configSummary.push({
            seq: seq++,
            model_name: modelName,
            server_model: configServerModels[cfgName] || '',
            desc: desc,
            description: desc,  // 别名，匹配 fieldMapping 中的 "description" key
            unit_price: unitPrice,
            quantity: configQuantities[cfgName] ?? 1,  // 从 config_quantities 获取配置级别数量
            qty: configQuantities[cfgName] ?? 1,  // 别名
            total_price: unitPrice * (configQuantities[cfgName] ?? 1),
            // KP 级别字段（取第一个 KP）
            kp_model: firstKp.model || firstKp.model_name || '',
            kp_category: firstKp.kp_category || firstKp.category || '',
            kp_price: firstKp.price || firstKp.final_price || 0,
            kp_currency: firstKp.currency || 'CNY',
            // L6 级别字段（取第一个 L6）
            l6_model: firstL6?.model || firstL6?.model_name || '',
            l6_chassis: firstL6?.chassis || '',
            l6_motherboard: firstL6?.motherboard || '',
            l6_backplane: firstL6?.backplane || '',
            l6_gpu_expansion: firstL6?.gpu_expansion || '',
            l6_psu: firstL6?.psu || '',
            l6_drive_bays: firstL6?.drive_bays || 0,
            l6_price: firstL6?.price || firstL6?.final_price || 0,
          })
        })
        
        previewDataSource.value.config_summary = configSummary
        
        // 保留第一个 item 的字段（向后兼容）
        if (items.length > 0) {
          const firstItem = items[0]
          previewDataSource.value.config_name = firstItem.config_name || ''
          previewDataSource.value.part_name = firstItem.part_name || ''
          previewDataSource.value.category = firstItem.category || ''
          previewDataSource.value.spec = firstItem.spec || ''
          previewDataSource.value.qty = firstItem.qty ?? 0
          previewDataSource.value.confirmed_price = firstItem.confirmed_price ?? 0
          previewDataSource.value.base_price = firstItem.base_price ?? 0
          previewDataSource.value.final_price = firstItem.final_price ?? 0
        }
        
        // per_cfg_l6 中的 L6 匹配信息
        if (q.per_cfg_l6 && Object.keys(q.per_cfg_l6).length > 0) {
          const firstCfg = Object.values(q.per_cfg_l6)[0] as any
          const l6Meta = firstCfg?.l6_meta || {}
          previewDataSource.value.l6_model = l6Meta.model || ''
          previewDataSource.value.l6_cpu = l6Meta.cpu || ''
          previewDataSource.value.l6_memory = l6Meta.memory || ''
          previewDataSource.value.l6_storage = l6Meta.storage || ''
          previewDataSource.value.l6_psu = l6Meta.psu || ''
        }
      }
    }
  } catch (e) {
    console.error('[loadPreviewDataSource] failed:', e)
  } finally {
    previewLoading.value = false
  }
}

// ── 商机选择变更 → 加载报价单 ──
watch(selectedProjectId, (newId) => {
  loadQuotationsForProject(newId)
})

// ── 报价单选择变更 → 加载预览数据 ──
watch(selectedQuotationId, (newId) => {
  loadPreviewDataSource()
})

// 通用：生成热力图覆盖映射
function buildOverlayMap(templateData: TemplateData | null): Record<string, string> {
  const map: Record<string, string> = {}
  if (!templateData) return map
  for (const binding of templateData.bindings) {
    if (binding.dataType === 'static') {
      const key = `${binding.sheetName}!${binding.cellAddress}`
      map[key] = 'rgba(0, 245, 212, 0.20)'
    } else if (binding.dataType === 'dynamic' && binding.fieldMapping) {
      const startRow = binding.templateRow || parseInt(binding.cellAddress.replace(/[A-Z]+/, ''))
      
      // 获取数据量以覆盖所有扩展行
      const regionKey = binding.regionFieldKey || ''
      const dataArray: any[] = previewDataSource.value[regionKey] || []
      const rowCount = Math.max(1, dataArray.length) // 至少覆盖模板行
      
      // 覆盖所有数据行（包括扩展的行）
      for (let i = 0; i < rowCount; i++) {
        const row = startRow + i
        for (const col of Object.values(binding.fieldMapping)) {
          const key = `${binding.sheetName}!${col}${row}`
          map[key] = 'rgba(0, 245, 212, 0.40)'
        }
      }
    }
  }
  return map
}

// 封面页热力图覆盖映射
const coverOverlayMap = computed(() => buildOverlayMap(coverTemplateData.value))

// 配置页热力图覆盖映射
const configOverlayMap = computed(() => buildOverlayMap(configTemplateData.value))

// 获取字段的示例值：必须从真实数据源获取
function getSampleValue(fieldKey: string): string {
  const field = store.businessFields.find(f => f.key === fieldKey)
  if (!field) {
    return `[${fieldKey}]`
  }
  
  // 从真实数据源获取
  const realValue = previewDataSource.value[fieldKey]
  if (realValue !== undefined && realValue !== null && realValue !== '') {
    return String(realValue)
  }
  
  // 无真实数据时的回退逻辑
  const label = field.label || fieldKey
  
  // 如果已选择商机但无报价单 → 配置级字段显示 [未绑定]
  if (selectedProjectId.value && !selectedQuotationId.value) {
    const configCategories = ['item', 'l6', 'kp']
    if (configCategories.includes(field.category)) {
      return '[未绑定]'
    }
  }
  
  // 未选择数据源 → 显示 [请选择数据源]
  return `[请选择数据源]`
}

// 通用：生成预览数据映射（支持 static + dynamic 展开）
function buildPreviewData(templateData: TemplateData | null): Record<string, string | number> {
  const map: Record<string, string | number> = {}
  if (!templateData) return map
  
  for (const binding of templateData.bindings) {
    if (binding.dataType === 'static') {
      const key = `${binding.sheetName}!${binding.cellAddress}`
      const sampleValue = getSampleValue(binding.fieldKey)
      map[key] = sampleValue
    } else if (binding.dataType === 'dynamic') {
      // 动态展开：从 previewDataSource 获取数据数组
      const regionKey = binding.regionFieldKey || ''
      const dataArray: any[] = previewDataSource.value[regionKey] || []
      const startRow = binding.templateRow || 1
      const fieldMapping = binding.fieldMapping || {}
      
      
      if (dataArray.length === 0) {
        // 无数据：在起始行显示 [无数据]
        const cols = Object.values(fieldMapping)
        if (cols.length > 0) {
          const firstCol = cols[0] as string
          map[`${binding.sheetName}!${firstCol}${startRow}`] = '[无数据]'
        }
      } else {
        // 有数据：按行展开
        dataArray.forEach((item, idx) => {
          const row = startRow + idx
          for (const [fieldKey, colLetter] of Object.entries(fieldMapping)) {
            const cellKey = `${binding.sheetName}!${colLetter}${row}`
            let value = item[fieldKey]
            
            // 处理 descriptionTemplate（仅 config_summary）
            if ((fieldKey === 'desc' || fieldKey === 'description') && binding.descriptionTemplate && regionKey === 'config_summary') {
              value = renderDescriptionTemplate(binding.descriptionTemplate, item, binding.descriptionSeparator || ',')
            }
            
            map[cellKey] = value !== undefined && value !== null ? (typeof value === 'number' ? value : String(value)) : ''
          }
        })
      }
    }
  }
  return map
}

// 渲染描述模板（简化版，用于预览）
function renderDescriptionTemplate(template: string, item: any, separator: string): string {
  let result = template
  
  // 处理 {kp_list} - 从 config_summary item 中取 kp 列表
  if (result.includes('{kp_list}')) {
    // config_summary 的 desc 字段已经是拼接好的
    result = result.replace('{kp_list}', item.desc || '')
  }
  
  // 处理 {l6_list}
  if (result.includes('{l6_list}')) {
    result = result.replace('{l6_list}', item.l6_list || '')
  }
  
  return result
}

// 封面页预览数据映射
const coverPreviewData = computed(() => {
  const result = buildPreviewData(coverTemplateData.value)
  return result
})

// 配置页预览数据映射
const configPreviewData = computed(() => {
  const result = buildPreviewData(configTemplateData.value)
  return result
})

const bindingForm = ref<{
  dataType: BindingDataType
  fieldKey: string
  templateRow: number
  regionFieldKey: string
  fieldMapping: Record<string, string>
  descriptionTemplate?: string
  descriptionSeparator?: string
}>({
  dataType: 'static',
  fieldKey: '',
  templateRow: 1,
  regionFieldKey: '',
  fieldMapping: {},
  descriptionTemplate: '{kp_list}',
  descriptionSeparator: ','
})

// 业务字段（按新分类）
const opportunityFields = computed(() => store.businessFields.filter(f => f.category === 'opportunity'))
const itemFields = computed(() => store.businessFields.filter(f => f.category === 'item'))
const l6Fields = computed(() => store.businessFields.filter(f => f.category === 'l6'))
const kpFields = computed(() => store.businessFields.filter(f => f.category === 'kp'))
const systemFields = computed(() => store.businessFields.filter(f => f.category === 'system'))

// config_summary 专属字段（匹配后端 _build_config_summary + 前端预览生成的字段）
const configSummaryFields = computed<BusinessField[]>(() => [
  { key: 'seq', label: '序号', category: 'item', source: 'system' },
  { key: 'model_name', label: '型号', category: 'item', source: 'system' },
  { key: 'server_model', label: '服务器型号', category: 'item', source: 'system' },
  { key: 'desc', label: '描述', category: 'item', source: 'system' },
  { key: 'description', label: '描述(别名)', category: 'item', source: 'system' },
  { key: 'unit_price', label: '单价', category: 'item', source: 'system' },
  { key: 'qty', label: '数量', category: 'item', source: 'system' },
  { key: 'quantity', label: '数量(别名)', category: 'item', source: 'system' },
  { key: 'total_price', label: '总价', category: 'item', source: 'system' },
  // KP 子字段（取第一个 Key Parts）
  { key: 'kp_model', label: 'KP型号', category: 'item', source: 'system' },
  { key: 'kp_category', label: 'KP类别', category: 'item', source: 'system' },
  { key: 'kp_price', label: 'KP单价', category: 'item', source: 'system' },
  { key: 'kp_currency', label: 'KP币种', category: 'item', source: 'system' },
  // L6 子字段（取第一个 L6）
  { key: 'l6_model', label: 'L6型号', category: 'item', source: 'system' },
  { key: 'l6_chassis', label: 'L6机箱', category: 'item', source: 'system' },
  { key: 'l6_motherboard', label: 'L6主板', category: 'item', source: 'system' },
  { key: 'l6_backplane', label: 'L6背板', category: 'item', source: 'system' },
  { key: 'l6_gpu_expansion', label: 'L6 GPU扩展', category: 'item', source: 'system' },
  { key: 'l6_psu', label: 'L6电源', category: 'item', source: 'system' },
  { key: 'l6_drive_bays', label: 'L6盘位数', category: 'item', source: 'system' },
  { key: 'l6_price', label: 'L6单价', category: 'item', source: 'system' },
])

// 字段搜索过滤
const filterFields = (fields: BusinessField[]) => {
  if (!fieldSearch.value.trim()) return fields
  const keyword = fieldSearch.value.toLowerCase()
  return fields.filter(f => 
    f.label.toLowerCase().includes(keyword) || 
    f.key.toLowerCase().includes(keyword)
  )
}
const filteredOpportunityFields = computed(() => filterFields(opportunityFields.value))
const filteredSystemFields = computed(() => filterFields(systemFields.value))
const filteredItemFields = computed(() => filterFields(itemFields.value))
const filteredL6Fields = computed(() => filterFields(l6Fields.value))
const filteredKpFields = computed(() => filterFields(kpFields.value))

// 解析模板动态区域（供导出模板引用）
const parseRegionOptions = computed(() => store.parseRegionFields)

// 根据 fieldKey 查找解析区域，获取其 fieldMapping
function getParseRegionMapping(fieldKey: string): Record<string, string> {
  const parseStore = useParseTemplateStore()
  for (const region of parseStore.templates.flatMap(t => t.dynamicRegions)) {
    if (region.fieldKey === fieldKey) {
      return { ...region.fieldMapping }
    }
  }
  return {}
}

// 根据当前页面和引用区域，返回可用于字段列映射的字段列表
const availableFieldsForMapping = computed<BusinessField[]>(() => {
  const regionKey = bindingForm.value.regionFieldKey
  
  // 动态区域优先：无论哪个页面，选了 regionFieldKey 就返回对应字段
  if (regionKey === 'l6_details') return l6Fields.value
  if (regionKey === 'kp_details') return kpFields.value
  if (regionKey === 'config_summary') return configSummaryFields.value
  
  // 静态字段绑定（未选 regionFieldKey）
  if (activePage.value === 'cover') {
    return [...opportunityFields.value, ...systemFields.value]
  }
  // 配置页默认返回所有字段
  return [...itemFields.value, ...l6Fields.value, ...kpFields.value]
})

// 已选字段（用于"添加字段"下拉过滤）
const availableFieldsForAdd = computed(() => {
  const used = new Set(Object.keys(bindingForm.value.fieldMapping))
  return availableFieldsForMapping.value.filter(f => !used.has(f.key))
})

// 根据 fieldKey 查找中文 label
function getFieldLabel(fieldKey: string): string {
  const all = store.businessFields
  const found = all.find(f => f.key === fieldKey)
  return found?.label || fieldKey
}

// 当用户选择引用解析区域时，自动填充 fieldMapping
function onRegionFieldKeyChange() {
  const regionKey = bindingForm.value.regionFieldKey
  if (!regionKey) {
    bindingForm.value.fieldMapping = {}
    bindingForm.value.fieldKey = ''
    return
  }
  // 自动填充 fieldMapping（从解析区域继承，转换为列字母）
  const parseMapping = getParseRegionMapping(regionKey)
  if (Object.keys(parseMapping).length > 0) {
    // 解析模板的 fieldMapping 是 {fieldKey: columnLetter}，直接继承
    bindingForm.value.fieldMapping = parseMapping
  } else {
    // 没有解析模板映射时，用当前页面可用字段自动填充（按顺序分配列）
    const fields = availableFieldsForMapping.value
    const mapping: Record<string, string> = {}
    fields.forEach((f, i) => {
      mapping[f.key] = columnLetters.value[i] || 'A'
    })
    bindingForm.value.fieldMapping = mapping
  }
  // fieldKey 也设为 regionFieldKey，便于后续查找
  bindingForm.value.fieldKey = regionKey
}

// 添加导出字段映射行（改为下拉选择）
const newExportFieldKey = ref('')
const newExportFieldCol = ref('')
function addExportFieldMapping() {
  if (!newExportFieldKey.value || !newExportFieldCol.value) return
  bindingForm.value.fieldMapping[newExportFieldKey.value] = newExportFieldCol.value
  newExportFieldKey.value = ''
  newExportFieldCol.value = ''
}
function removeExportFieldMapping(field: string) {
  delete bindingForm.value.fieldMapping[field]
}

// 列字母列表（A-Z, AA-AZ）
const columnLetters = computed(() => {
  const letters: string[] = []
  for (let i = 0; i < 26; i++) letters.push(String.fromCharCode(65 + i))
  for (let i = 0; i < 26; i++) letters.push('A' + String.fromCharCode(65 + i))
  return letters
})

// 当前选中单元格信息
const currentSheetName = computed(() => {
  const data = currentTemplateData.value
  if (!data || data.sheets.length === 0) return ''
  return data.sheets[0]?.name || ''
})

const selectedCellAddress = computed(() => {
  if (!selectedCell.value) return ''
  return `${colToLetter(selectedCell.value.col)}${selectedCell.value.row}`
})

// 当前 tab 的绑定列表
const currentBindings = computed<CellBinding[]>(() => {
  const data = currentTemplateData.value
  if (!data) return []
  return data.bindings.filter(b => !b.fieldKey.startsWith('remark'))
})

// 加载模板数据
async function loadTemplate() {
  loading.value = true
  try {
    const data = await exportTemplateApi.getById(templateId.value)
    template.value = data
    templateNameInput.value = data.display_name || ''

    // 加载业务字段定义
    await store.loadBusinessFields()

    // 恢复封面页数据
    if (data.template_json?.cover?.fileBuffer) {
      const buffer = base64ToArrayBuffer(data.template_json.cover.fileBuffer)
      const sheets = await parseExcelTemplate(buffer)
      coverTemplateData.value = {
        fileBuffer: buffer,
        fileName: data.template_json.cover.fileName,
        sheets,
        bindings: data.template_json.cover.bindings || [],
        productData: [],
        staticData: {}
      }
    }

    // 恢复配置页数据
    if (data.template_json?.config_sheet?.fileBuffer) {
      const buffer = base64ToArrayBuffer(data.template_json.config_sheet.fileBuffer)
      const sheets = await parseExcelTemplate(buffer)
      configTemplateData.value = {
        fileBuffer: buffer,
        fileName: data.template_json.config_sheet.fileName,
        sheets,
        bindings: data.template_json.config_sheet.bindings || [],
        productData: [],
        staticData: {}
      }
    }
  } catch (e) {
    message.error('加载模板失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 上传处理
async function handleUpload(file: File, type: 'cover' | 'config') {
  if (!file.name.match(/\.xlsx?$/i)) {
    message.error('仅支持 .xlsx 格式')
    return false
  }

  const currentData = type === 'cover' ? coverTemplateData.value : configTemplateData.value
  const hasBindings = currentData && currentData.bindings.length > 0

  const doUpload = async () => {
    try {
      const buffer = await file.arrayBuffer()
      const sheets = await parseExcelTemplate(buffer)

      const templateData: TemplateData = {
        fileBuffer: buffer,
        fileName: file.name,
        sheets,
        bindings: [],
        productData: [],
        staticData: {}
      }

      if (type === 'cover') {
        coverTemplateData.value = templateData
        if (template.value) {
          template.value.template_json.cover = {
            fileName: file.name,
            fileBuffer: arrayBufferToBase64(buffer),
            bindings: []
          }
        }
      } else {
        configTemplateData.value = templateData
        if (template.value) {
          template.value.template_json.config_sheet = {
            fileName: file.name,
            fileBuffer: arrayBufferToBase64(buffer),
            bindings: []
          }
        }
      }

      message.success(`${type === 'cover' ? '封面' : '配置页'}模板加载成功`)
    } catch (err) {
      console.error(err)
      message.error('模板解析失败，请检查文件格式')
    }
  }

  if (hasBindings) {
    Modal.confirm({
      title: '重新上传模板',
      content: `当前${type === 'cover' ? '封面' : '配置页'}模板已有 ${currentData!.bindings.length} 条绑定配置，重新上传将清空所有绑定。是否继续？`,
      okText: '继续上传',
      cancelText: '取消',
      onOk: doUpload
    })
  } else {
    await doUpload()
  }

  return false
}

// 保存模板
async function handleSave() {
  if (!template.value) return

  saving.value = true
  try {
    // 更新名称
    if (template.value) {
      template.value.display_name = templateNameInput.value
    }

    // 更新封面页绑定数据
    if (coverTemplateData.value && template.value.template_json.cover) {
      template.value.template_json.cover.bindings = coverTemplateData.value.bindings
    }

    // 更新配置页绑定数据
    if (configTemplateData.value && template.value.template_json.config_sheet) {
      template.value.template_json.config_sheet.bindings = configTemplateData.value.bindings
    }

    await exportTemplateApi.update(templateId.value, {
      display_name: template.value.display_name,
      template_json: template.value.template_json
    })

    message.success('保存成功')
  } catch (e) {
    message.error('保存失败')
    console.error(e)
  } finally {
    saving.value = false
  }
}

// 名称变更
function onNameChange() {
  if (template.value) {
    template.value.display_name = templateNameInput.value
  }
}

function goBack() {
  router.push('/export-templates')
}

// 字段和单元格交互
function selectField(field: BusinessField) {
  currentFieldKey.value = field.key
  bindingForm.value.fieldKey = field.key
}

function onCellClick(cell: RenderCell) {
  selectedCell.value = cell
  const addr = selectedCellAddress.value
  const data = currentTemplateData.value
  if (!data) return

  const existing = data.bindings.find(
    b => b.cellAddress === addr
  )

  if (existing) {
    bindingForm.value = {
      dataType: existing.dataType,
      fieldKey: existing.fieldKey,
      templateRow: existing.templateRow || 1,
      regionFieldKey: existing.regionFieldKey || '',
      fieldMapping: existing.fieldMapping ? { ...existing.fieldMapping } : {},
      descriptionTemplate: existing.descriptionTemplate || '{kp_list}',
      descriptionSeparator: existing.descriptionSeparator || ','
    }
  } else {
    bindingForm.value = {
      dataType: 'static',
      fieldKey: currentFieldKey.value,
      templateRow: cell.row,
      regionFieldKey: '',
      fieldMapping: {},
      descriptionTemplate: '{kp_list}',
      descriptionSeparator: ','
    }
  }
}

// Commit the current bindingForm into data.bindings. When `silent` (auto-save),
// only dynamic bindings are written so that merely clicking a static cell (e.g.
// a title) can never rewrite it. Because data.bindings stays current, the preview
// reflects every edit at once and re-selecting a cell can no longer drop unsaved
// fieldMapping changes.
function commitBindingToData(silent: boolean) {
  if (!selectedCell.value) return
  const data = currentTemplateData.value
  if (!data) return

  const f = bindingForm.value
  // Auto-save only touches dynamic bindings; static cells keep requiring 保存绑定.
  if (silent && f.dataType !== 'dynamic') return
  if (f.dataType === 'static' && !f.fieldKey) {
    if (!silent) message.warning('请选择要绑定的字段')
    return
  }
  if (f.dataType === 'dynamic' && !f.regionFieldKey) {
    if (!silent) message.warning('请选择引用解析区域')
    return
  }

  const addr = selectedCellAddress.value
  const binding: CellBinding = {
    id: addr,
    sheetName: currentSheetName.value,
    cellAddress: addr,
    fieldKey: f.dataType === 'dynamic' ? f.regionFieldKey : f.fieldKey,
    dataType: f.dataType,
    templateRow: f.dataType === 'dynamic' ? f.templateRow : undefined,
    regionFieldKey: f.dataType === 'dynamic' ? f.regionFieldKey : undefined,
    fieldMapping: f.dataType === 'dynamic' && Object.keys(f.fieldMapping).length > 0
      ? { ...f.fieldMapping }
      : undefined,
    descriptionTemplate: f.dataType === 'dynamic' && f.regionFieldKey === 'config_summary'
      ? f.descriptionTemplate
      : undefined,
    descriptionSeparator: f.dataType === 'dynamic' && f.regionFieldKey === 'config_summary'
      ? f.descriptionSeparator
      : undefined
  }

  const idx = data.bindings.findIndex(b => b.cellAddress === addr)
  if (idx >= 0) data.bindings[idx] = binding
  else data.bindings.push(binding)

  if (!silent) message.success('绑定已保存')
}

function saveBinding() {
  commitBindingToData(false)
}

// Live auto-save: every dynamic binding edit (add/remove field, change column,
// region, template row, description template) lands in data.bindings immediately,
// so the preview updates in real time and nothing is lost on re-select.
watch(bindingForm, () => commitBindingToData(true), { deep: true })

function removeBinding() {
  if (!selectedCell.value) return
  const data = currentTemplateData.value
  if (!data) return

  const addr = selectedCellAddress.value
  const index = data.bindings.findIndex(b => b.cellAddress === addr)
  if (index >= 0) {
    data.bindings.splice(index, 1)
  }
  message.success('绑定已移除')
}

function filterOption(input: string, option: any) {
  return option.label?.toLowerCase().includes(input.toLowerCase())
}

// 右侧绑定列表点击：选中对应单元格（通过 store）
function onBindingItemClick(binding: CellBinding) {
  const data = currentTemplateData.value
  if (!data) return
  const match = binding.cellAddress.match(/^([A-Z]+)(\d+)$/)
  if (!match) return
  const colStr = match[1]
  const row = parseInt(match[2])
  let col = 0
  for (let i = 0; i < colStr.length; i++) {
    col = col * 26 + (colStr.charCodeAt(i) - 64)
  }
  const sheet = data.sheets.find(s => s.name === binding.sheetName) || data.sheets[0]
  if (!sheet) return
  const cell = sheet.cells[row - 1]?.[col - 1]
  if (cell) {
    store.selectCell(cell)
    selectedCell.value = cell
    bindingForm.value = {
      dataType: binding.dataType,
      fieldKey: binding.fieldKey,
      templateRow: binding.templateRow || 1,
      regionFieldKey: binding.regionFieldKey || '',
      fieldMapping: binding.fieldMapping ? { ...binding.fieldMapping } : {},
      descriptionTemplate: binding.descriptionTemplate || '{kp_list}',
      descriptionSeparator: binding.descriptionSeparator || ','
    }
  }
}

// 绑定总览点击：跳转到对应页面 + 选中单元格
function onOverviewBindingClick(binding: CellBinding, tab: 'cover' | 'config') {
  activePage.value = tab
  nextTick(() => {
    const data = tab === 'cover' ? coverTemplateData.value : configTemplateData.value
    if (!data) return
    const match = binding.cellAddress.match(/^([A-Z]+)(\d+)$/)
    if (!match) return
    const colStr = match[1]
    const row = parseInt(match[2])
    let col = 0
    for (let i = 0; i < colStr.length; i++) {
      col = col * 26 + (colStr.charCodeAt(i) - 64)
    }
    const sheet = data.sheets.find(s => s.name === binding.sheetName) || data.sheets[0]
    if (!sheet) return
    const cell = sheet.cells[row - 1]?.[col - 1]
    if (cell) {
      store.selectCell(cell)
      selectedCell.value = cell
      bindingForm.value = {
        dataType: binding.dataType,
        fieldKey: binding.fieldKey,
        templateRow: binding.templateRow || 1,
        regionFieldKey: binding.regionFieldKey || '',
        fieldMapping: binding.fieldMapping ? { ...binding.fieldMapping } : {},
        descriptionTemplate: binding.descriptionTemplate || '{kp_list}',
        descriptionSeparator: binding.descriptionSeparator || ','
      }
    }
  })
}

// 工具函数
function colToLetter(col: number): string {
  let result = ''
  while (col > 0) {
    const mod = (col - 1) % 26
    result = String.fromCharCode(65 + mod) + result
    col = Math.floor((col - 1) / 26)
  }
  return result
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

// 页面切换时清空选中状态和绑定表单
watch(activePage, () => {
  selectedCell.value = null
  currentFieldKey.value = ''
  bindingForm.value = {
    dataType: 'static',
    fieldKey: '',
    templateRow: 1,
    regionFieldKey: '',
    fieldMapping: {},
    descriptionTemplate: '{kp_list}',
    descriptionSeparator: ','
  }
})

onMounted(() => {
  loadTemplate()
  loadProjects()
})
</script>

<style scoped>
.template-editor-page {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.loading-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.template-name {
  margin: 0;
  color: var(--cpq-text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: color var(--cpq-transition-fast);
}

.template-name:hover {
  color: var(--cpq-accent-primary);
}

.edit-icon {
  font-size: 14px;
  color: var(--cpq-text-muted);
}

.upload-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.editor-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.upload-section {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px;
  border-radius: 18px;
}

.upload-section h3 {
  margin: 0;
  color: var(--cpq-text-primary);
  font-size: 14px;
}

.file-info {
  color: var(--cpq-text-secondary);
  font-size: 13px;
}

.editor-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 220px 1fr 280px;
  gap: 12px;
  overflow: hidden;
}

.bottom-panel {
  max-height: 300px;
  flex-shrink: 0;
  overflow-y: auto;
  margin-top: 12px;
}

.left-panel,
.right-panel {
  padding: 12px;
  overflow-y: auto;
  min-height: 0;
}

.center-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.preview-area {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: #ffffff;
}

.excel-preview-scaler {
  display: inline-block;
  width: fit-content;
  min-width: 100%;
}

.preview-area::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.preview-area::-webkit-scrollbar-track {
  background: var(--cpq-bg-primary);
  border-radius: 5px;
}

.preview-area::-webkit-scrollbar-thumb {
  background: var(--cpq-accent-primary);
  border-radius: 5px;
}

.preview-area::-webkit-scrollbar-thumb:hover {
  background: var(--cpq-accent-primary-light); /* cyan hover 变体，无对应变量 */
}

.preview-area::-webkit-scrollbar-corner {
  background: var(--cpq-bg-primary);
}

.panel-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--cpq-border-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-subtitle {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  margin: 12px 0 8px;
}

.field-item {
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  transition: background-color var(--cpq-transition-fast);
}

.field-item:hover {
  background: var(--cpq-bg-tertiary);
}

.field-active {
  background: var(--cpq-overlay-a8);
  border: 1px solid var(--cpq-accent-primary);
}

.field-label {
  color: var(--cpq-text-primary);
  font-size: 13px;
}

.field-key {
  color: var(--cpq-text-muted);
  font-size: 11px;
  font-family: monospace;
}

.empty-hint {
  color: var(--cpq-text-muted);
  text-align: center;
  padding: 40px 20px;
}

.binding-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.binding-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.binding-list {
  border-top: 1px solid var(--cpq-border-primary);
  padding-top: 8px;
}

.binding-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--cpq-bg-tertiary);
  margin-bottom: 4px;
  font-size: 12px;
}

.binding-cell {
  color: var(--cpq-accent-primary);
  font-family: monospace;
  font-weight: 600;
  min-width: 40px;
}

.binding-field {
  color: var(--cpq-text-primary);
  flex: 1;
}

.binding-item.clickable {
  cursor: pointer;
  transition: background-color var(--cpq-transition-fast);
}

.binding-item.clickable:hover {
  background: var(--cpq-bg-secondary);
  border-color: var(--cpq-accent-primary);
}

/* 热力图图例 */
.heatmap-legend {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  margin-top: 8px;
  background: var(--cpq-bg-tertiary);
  border-radius: 4px;
  font-size: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-text-primary);
}

.legend-color {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

/* 绑定总览 */
.binding-overview {
  padding: 16px;
}

.overview-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.overview-section {
  background: var(--cpq-bg-secondary);
  border: 1px solid var(--cpq-border-primary);
  border-radius: 18px;
  padding: 16px;
}

.overview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-empty {
  color: var(--cpq-text-muted);
  text-align: center;
  padding: 24px;
  font-size: 13px;
}

.overview-table-wrap {
  max-height: 400px;
  overflow: auto;
}

.overview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.overview-table thead th {
  background: var(--cpq-bg-tertiary);
  color: var(--cpq-text-primary);
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  border-bottom: 1px solid var(--cpq-border-primary);
  position: sticky;
  top: 0;
  z-index: 1;
}

.overview-table tbody td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--cpq-border-primary);
  color: var(--cpq-text-primary);
}

.overview-table .mono {
  font-family: 'Courier New', monospace;
  color: var(--cpq-accent-primary);
  font-weight: 600;
}

.overview-row {
  cursor: pointer;
  transition: background-color var(--cpq-transition-fast);
}

.overview-row:hover {
  background: var(--cpq-bg-tertiary);
}

/* 字段映射表 */
.field-mapping-table {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-mapping-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.field-mapping-row .field-name {
  color: var(--cpq-text-primary);
  font-size: 12px;
  min-width: 60px;
  font-family: 'Courier New', monospace;
}

.add-field-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
</style>
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             