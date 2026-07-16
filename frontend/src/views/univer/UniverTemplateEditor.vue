<template>
  <div class="univer-template-editor">
    <!-- 顶栏 -->
    <div class="header">
      <div class="header-left">
        <a-button @click="$router.back()" size="small">
          <template #icon><ArrowLeftOutlined /></template>
        </a-button>
        <a-input
          v-model:value="displayName"
          class="template-name-input"
          placeholder="模板名称"
          size="small"
        />
      </div>
      <div class="header-right">
        <a-select
          v-model:value="selectedOpportunityId"
          placeholder="选择商机"
          size="small"
          style="width: 220px"
          show-search
          :filter-option="filterOpportunityOption"
          @change="onOpportunityChange"
        >
          <a-select-option
            v-for="opp in opportunityList"
            :key="opp.opportunity_id"
            :value="opp.opportunity_id"
          >
            {{ opp.opportunity_name }} ({{ opp.customer_name }})
          </a-select-option>
        </a-select>
        <a-select
          v-model:value="selectedQuotationId"
          placeholder="选择报价单"
          size="small"
          style="width: 200px"
          :disabled="!selectedOpportunityId"
          :loading="quotationListLoading"
        >
          <a-select-option
            v-for="quo in quotationList"
            :key="quo.quotation_id"
            :value="quo.quotation_id"
          >
            {{ quo.quotation_name || quo.quotation_id }}
          </a-select-option>
        </a-select>
        <a-button
          @click="handlePreview"
          :loading="previewing"
          size="small"
          :type="isPreviewing ? 'primary' : 'default'"
        >
          <template #icon><EyeOutlined /></template>
          {{ isPreviewing ? '退出预览' : '预览' }}
        </a-button>
        <a-button type="primary" @click="handleSave" :loading="saving" size="small">
          <template #icon><SaveOutlined /></template>
          保存
        </a-button>
      </div>
    </div>

    <!-- 主体区域 -->
    <div class="main-content">
      <!-- 中栏：编辑/预览双实例 -->
      <div class="center-panel">
        <!-- 编辑层：v-show 隐藏，不销毁 -->
        <div class="editor-layer" v-show="!isPreviewing">
          <UniverSheet
            v-if="workbookData"
            ref="editorRef"
            :workbookData="workbookData"
            :editable="true"
            @cell-click="handleCellClick"
          />
          <div v-else class="loading-placeholder">加载中...</div>
        </div>

        <!-- 预览层：v-if 创建/销毁，只读 -->
        <div class="preview-layer" v-if="isPreviewing && previewData">
          <UniverSheet
            ref="previewRef"
            :workbookData="previewData"
            :editable="false"
          />
        </div>
      </div>

      <!-- 右栏：绑定面板 -->
      <div class="right-panel">
        <div class="panel-title">绑定设置</div>
        
        <!-- 当前单元格绑定 -->
        <div class="current-binding" v-if="selectedCell">
          <div class="binding-header">
            <span>当前单元格</span>
            <span class="cell-address">{{ selectedCell.address }}</span>
          </div>
          
          <div class="binding-form">
            <div class="form-item">
              <label>数据类型</label>
              <a-radio-group v-model:value="currentBindingType" size="small">
                <a-radio-button value="static">静态</a-radio-button>
                <a-radio-button value="dynamic">动态</a-radio-button>
              </a-radio-group>
            </div>

            <div class="form-item" v-if="currentBindingType === 'static'">
              <label>字段</label>
              <a-select
                v-model:value="currentBindingField"
                placeholder="选择字段"
                size="small"
                style="width: 100%"
              >
                <a-select-opt-group label="商机级字段">
                  <a-select-option
                    v-for="field in opportunityFields"
                    :key="field.key"
                    :value="field.key"
                  >
                    {{ field.label }}
                  </a-select-option>
                </a-select-opt-group>
                <a-select-opt-group label="配置项字段">
                  <a-select-option
                    v-for="field in configFields"
                    :key="field.key"
                    :value="field.key"
                  >
                    {{ field.label }}
                  </a-select-option>
                </a-select-opt-group>
                <a-select-opt-group label="系统字段">
                  <a-select-option
                    v-for="field in systemFields"
                    :key="field.key"
                    :value="field.key"
                  >
                    {{ field.label }}
                  </a-select-option>
                </a-select-opt-group>
              </a-select>
            </div>

            <div class="form-item" v-if="currentBindingType === 'dynamic'">
              <label>数据源</label>
              <a-select
                v-model:value="currentBindingSource"
                placeholder="选择数据源"
                size="small"
                style="width: 100%"
              >
                <a-select-option value="l6_details">L6 配置项</a-select-option>
                <a-select-option value="kp_details">KP 配置项</a-select-option>
                <a-select-option value="warranty_details">保修项</a-select-option>
                <a-select-option value="config_summary">配置汇总</a-select-option>
              </a-select>
            </div>

            <div class="form-item" v-if="currentBindingType === 'dynamic'">
              <label>列映射</label>
              <div class="field-mapping-list">
                <div v-for="(mapping, index) in fieldMappingList" :key="index" class="mapping-item">
                  <a-select
                    v-model:value="mapping.subField"
                    placeholder="选择子字段"
                    size="small"
                    style="width: 45%"
                    show-search
                    :filter-option="filterSubFieldOption"
                  >
                    <a-select-option
                      v-for="field in availableSubFields"
                      :key="field.key"
                      :value="field.key"
                    >
                      {{ field.label }}
                    </a-select-option>
                  </a-select>
                  <a-select
                    v-model:value="mapping.colLetter"
                    placeholder="列"
                    size="small"
                    style="width: 35%"
                    @change="onFieldMappingChange"
                  >
                    <a-select-option
                      v-for="col in availableColumns"
                      :key="col"
                      :value="col"
                      :disabled="isColumnMapped(col, index)"
                    >
                      {{ col }}
                    </a-select-option>
                  </a-select>
                  <a-button
                    type="text"
                    size="small"
                    danger
                    @click="removeFieldMapping(index)"
                  >
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </div>
                <a-button
                  type="dashed"
                  size="small"
                  block
                  @click="addFieldMapping"
                  style="margin-top: 8px"
                  :disabled="!canAddMoreMapping"
                >
                  + 添加映射
                </a-button>
              </div>
            </div>

            <div class="form-item" v-if="currentBindingType === 'dynamic' && currentBindingSource === 'config_summary'">
              <label>🎯 显示部件</label>
              <a-select
                v-model:value="currentBindingSelectedParts"
                mode="multiple"
                size="small"
                style="width: 100%"
                placeholder="选择要在描述中显示的部件类型"
                :options="[
                  { value: 'cpu', label: 'CPU' },
                  { value: 'memory', label: '内存' },
                  { value: 'hdd', label: '硬盘' },
                  { value: 'ssd', label: '固态' },
                  { value: 'gpu', label: '显卡' },
                  { value: 'nic', label: '网卡' },
                  { value: 'raid', label: 'RAID卡' },
                  { value: 'psu', label: '电源' },
                  { value: 'front_backplane', label: '前背板' },
                  { value: 'rear_backplane', label: '后背板' }
                ]"
                allowClear
              />
            </div>



            <a-button
              v-if="!isPreviewing"
              type="primary"
              size="small"
              block
              @click="isCellBound ? unbindCurrentCell() : saveCurrentBinding()"
              :disabled="!canSaveBinding"
            >
              {{ isCellBound ? '解除绑定' : '绑定字段' }}
            </a-button>
          </div>
        </div>

        <div v-else class="no-selection">
          <p>点击单元格查看绑定</p>
        </div>

        <!-- 已绑定列表 -->
        <div class="bindings-list">
          <div class="list-header">
            <span>已绑定 ({{ bindings.length }})</span>
          </div>
          <div class="list-content">
            <div
              v-for="binding in bindings"
              :key="binding.id"
              class="binding-item"
            >
              <div class="binding-info">
                <span class="binding-cell">{{ binding.cellAddress }}</span>
                <span class="binding-field">
                  {{ getFieldLabel(binding.fieldKey) }}
                  <template v-if="binding.dataType === 'dynamic' && (binding as any).fieldMapping">
                    ({{ Object.keys((binding as any).fieldMapping).length }}列映射)
                  </template>
                </span>
                <a-tag :color="binding.dataType === 'static' ? 'blue' : 'green'" size="small">
                  {{ binding.dataType === 'static' ? '静态' : '动态' }}
                </a-tag>
              </div>
              <a-button
                type="text"
                size="small"
                danger
                @click="removeBinding(binding.id)"
              >
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <div v-if="bindings.length === 0" class="empty-bindings">
              暂无绑定
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底栏 -->
    <div class="footer">
      <div class="footer-left">
        <span>绑定总览：{{ bindings.length }} 个绑定</span>
      </div>
      <div class="footer-right">
        <span>提示：点击预览按钮选择商机进行数据预览</span>
      </div>
    </div>


  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  SaveOutlined,
  EyeOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import UniverSheet from '@/components/UniverSheet.vue'
import { univerTemplateApi } from '@/api/univerTemplate'
import { opportunityApi } from '@/api/template'
import { getFieldsByScope, getDynamicSources } from '@/api/fields'
import type {
  UniverTemplate,
  Binding,
} from '@/types/univerTemplate'

const route = useRoute()
const router = useRouter()

const templateId = computed(() => Number(route.params.id))

// 组件卸载保护
const isUnmounted = ref(false)
onBeforeUnmount(() => {
  isUnmounted.value = true
})

// 状态
const template = ref<UniverTemplate | null>(null)
const displayName = ref('')
const workbookData = ref<Record<string, any> | undefined>(undefined)
const bindings = ref<Binding[]>([])
const saving = ref(false)
const previewing = ref(false)
const dirty = ref(false)

// 预览相关
const isPreviewing = ref(false)
const previewData = ref<Record<string, any> | undefined>(undefined)
const selectedOpportunityId = ref('')
const selectedQuotationId = ref('')
const opportunityList = ref<any[]>([])
const quotationList = ref<any[]>([])
const quotationListLoading = ref(false)

// 字段列表
const opportunityFields = ref<any[]>([])
const configFields = ref<any[]>([])
const systemFields = ref<any[]>([])
// 动态数据源的子字段映射：{ sourceKey: [{key, label}, ...] }
const dataSourceFields = ref<Record<string, any[]>>({})

async function loadFields() {
  try {
    const [opp, cfg, sys, dynamicSources] = await Promise.all([
      getFieldsByScope('opportunity'),
      getFieldsByScope('config'),
      getFieldsByScope('system'),
      getDynamicSources(),
    ])
    opportunityFields.value = opp || []
    configFields.value = cfg || []
    systemFields.value = sys || []
    
    // 转换动态数据源字段格式：{ sourceKey: [{key, label}, ...] }
    if (dynamicSources) {
      const formatted: Record<string, any[]> = {}
      for (const [sourceKey, fields] of Object.entries(dynamicSources)) {
        formatted[sourceKey] = (fields as any[]).map(f => ({
          key: f.field_key,
          label: f.field_label || f.field_key,
        }))
      }
      dataSourceFields.value = formatted
    }
  } catch (err: any) {
    console.warn('加载字段列表失败:', err)
  }
}

// 加载商机列表
async function loadOpportunityList() {
  try {
    const { opportunityApi } = await import('@/api/template')
    opportunityList.value = await opportunityApi.list()
  } catch (err: any) {
    message.error(`加载商机列表失败: ${err.message}`)
  }
}

// 加载报价单列表
async function loadQuotationList(opportunityId: string) {
  if (!opportunityId) {
    quotationList.value = []
    return
  }
  quotationListLoading.value = true
  try {
    const { quotationApi } = await import('@/api')
    quotationList.value = await quotationApi.getByOpportunity(opportunityId)
  } catch (err: any) {
    message.error(`加载报价单列表失败: ${err.message}`)
    quotationList.value = []
  } finally {
    quotationListLoading.value = false
  }
}

// 商机变化时加载报价单
function onOpportunityChange() {
  selectedQuotationId.value = ''
  loadQuotationList(selectedOpportunityId.value)
  
  // 如果正在预览，自动刷新
  if (isPreviewing.value && selectedOpportunityId.value) {
    handlePreview()
  }
}

// 点击预览按钮（toggle）
async function handlePreview() {
  if (isPreviewing.value) {
    // 退出预览：销毁预览实例，编辑实例自动显示
    previewData.value = undefined
    isPreviewing.value = false
    message.info('已退出预览模式')
    return
  }
  
  // 进入预览：检查选择
  if (!selectedOpportunityId.value) {
    message.warning('请先选择商机')
    return
  }
  if (!selectedQuotationId.value) {
    message.warning('请先选择报价单')
    return
  }
  
  previewing.value = true
  try {
    // 传入当前编辑中的 bindings（包含 selectedParts）
    const result = await univerTemplateApi.preview(
      templateId.value,
      selectedOpportunityId.value,
      selectedQuotationId.value,
      bindings.value
    )
    const snapshot = result.workbook_snapshot || null
    
    if (!snapshot) {
      message.error('预览数据为空')
      return
    }
    
    // 确保所有 sheet 都有足够的行列
    if (snapshot.sheets) {
      for (const sheetId in snapshot.sheets) {
        const sheet = snapshot.sheets[sheetId]
        if (sheet) {
          if (!sheet.rowCount || sheet.rowCount < 50) sheet.rowCount = 50
          if (!sheet.columnCount || sheet.columnCount < 26) sheet.columnCount = 26
        }
      }
    }
    
    // 关键：设置 previewData，不修改 workbookData
    previewData.value = snapshot
    isPreviewing.value = true
    
    // 持久化选择
    saveSelectionToStorage()
    
    message.success('预览模式已开启')
  } catch (err: any) {
    message.error(`预览失败: ${err.message}`)
  } finally {
    previewing.value = false
  }
}

// localStorage 持久化：保存选择
function saveSelectionToStorage() {
  try {
    const key = 'univer_template_preview_selection'
    const stored = localStorage.getItem(key)
    const data = stored ? JSON.parse(stored) : { global: {}, perTemplate: {} }
    
    const selection = {
      opportunityId: selectedOpportunityId.value,
      quotationId: selectedQuotationId.value
    }
    
    // 更新全局
    data.global = selection
    
    // 更新当前模板
    if (!data.perTemplate) data.perTemplate = {}
    data.perTemplate[String(templateId.value)] = selection
    
    localStorage.setItem(key, JSON.stringify(data))
  } catch (err) {
    console.warn('保存选择到 localStorage 失败:', err)
  }
}

// localStorage 持久化：恢复选择
function loadSelectionFromStorage() {
  try {
    const key = 'univer_template_preview_selection'
    const stored = localStorage.getItem(key)
    if (!stored) return
    
    const data = JSON.parse(stored)
    
    // 优先使用当前模板的选择，否则用全局
    const templateSelection = data.perTemplate?.[String(templateId.value)]
    const selection = templateSelection || data.global
    
    if (selection) {
      selectedOpportunityId.value = selection.opportunityId || ''
      selectedQuotationId.value = selection.quotationId || ''
      
      // 如果恢复了商机，加载对应的报价单列表
      if (selectedOpportunityId.value) {
        loadQuotationList(selectedOpportunityId.value)
      }
    }
  } catch (err) {
    console.warn('从 localStorage 恢复选择失败:', err)
  }
}

// 搜索过滤
function filterOpportunityOption(input: string, option: any) {
  const label = option.label || option.children?.toString() || ''
  return label.toLowerCase().includes(input.toLowerCase())
}

// 报价单变化时，如果正在预览则自动刷新
watch(selectedQuotationId, (newVal) => {
  if (newVal && isPreviewing.value) {
    handlePreview()
  }
})

// 单元格选择
const selectedCell = ref<{ row: number; col: number; address: string; sheetId: string } | null>(null)
const currentBindingType = ref<'static' | 'dynamic'>('static')
const currentBindingField = ref('')
const currentBindingSource = ref('')
const currentBindingSelectedParts = ref<string[]>([])
const fieldMappingList = ref<Array<{ subField: string; colLetter: string }>>([])

// 实时保存：selectedParts 或 fieldMappingList 变化时自动保存
watch([currentBindingSelectedParts, fieldMappingList], async () => {
  if (!selectedCell.value) return
  if (currentBindingType.value !== 'dynamic') return
  
  // 更新 bindings 数组
  const bindingIndex = bindings.value.findIndex(
    b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
  )
  if (bindingIndex < 0) return
  
  const binding = bindings.value[bindingIndex] as any
  const updates: any = {}
  
  // 更新 selectedParts（仅 config_summary）
  if (currentBindingSource.value === 'config_summary') {
    updates.selectedParts = currentBindingSelectedParts.value
  }
  
  // 更新 fieldMapping
  const fieldMapping: Record<string, string> = {}
  fieldMappingList.value.forEach(m => {
    if (m.subField && m.colLetter) {
      fieldMapping[m.subField] = m.colLetter
    }
  })
  updates.fieldMapping = fieldMapping
  
  bindings.value[bindingIndex] = { ...binding, ...updates }
  dirty.value = true
  
  // 自动保存到后端
  try {
    const latestSnapshot = editorRef.value?.getWorkbookData()
    if (!latestSnapshot) return
    
    await univerTemplateApi.update(templateId.value, {
      display_name: displayName.value,
      workbook_snapshot: latestSnapshot,
      bindings: bindings.value,
    })
  } catch (err: any) {
    console.error('自动保存失败:', err)
  }
}, { deep: true })

// 动态数据源名称映射
const dynamicSourceMap = ref<Record<string, string>>({
  l6_details: 'L6配置项',
  kp_details: 'KP配置项',
  warranty_details: '保修项',
  config_summary: '配置汇总',
})

const editorRef = ref<InstanceType<typeof UniverSheet> | null>(null)
// const previewRef = ref<InstanceType<typeof UniverSheet> | null>(null) // 暂时未使用

// 计算属性
const canSaveBinding = computed(() => {
  if (!selectedCell.value) return false
  if (currentBindingType.value === 'static') {
    return !!currentBindingField.value
  } else {
    return !!currentBindingSource.value
  }
})

const isCellBound = computed(() => {
  if (!selectedCell.value) return false
  return bindings.value.some(
    b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
  )
})

// 方法
function getFieldLabel(fieldKey: string): string {
  const allFields = [...opportunityFields.value, ...configFields.value, ...systemFields.value]
  const field = allFields.find(f => f.key === fieldKey)
  if (field?.label) return field.label
  
  return dynamicSourceMap.value[fieldKey] || fieldKey
}

function handleCellClick(cell: { row: number; col: number; sheetName: string; sheetId: string }) {
  // 转换为单元格地址
  let colStr = ''
  let colNum = cell.col + 1
  while (colNum > 0) {
    colNum--
    colStr = String.fromCharCode((colNum % 26) + 65) + colStr
    colNum = Math.floor(colNum / 26)
  }
  const address = `${colStr}${cell.row + 1}`
  
  // 使用 nextTick 延迟状态更新，避免 DOM 更新冲突
  nextTick(() => {
    selectedCell.value = {
      row: cell.row,
      col: cell.col,
      address,
      sheetId: cell.sheetId,
    }
    
    // 加载现有绑定
    const existingBinding = bindings.value.find(
      b => b.cellAddress === address && b.sheetId === cell.sheetId
    )
    
    if (existingBinding) {
      currentBindingType.value = existingBinding.dataType as 'static' | 'dynamic'
      if (existingBinding.dataType === 'static') {
        currentBindingField.value = existingBinding.fieldKey
      } else {
        currentBindingSource.value = (existingBinding as any).source || existingBinding.fieldKey
        // 加载列映射
        const fieldMapping = (existingBinding as any).fieldMapping || {}
        fieldMappingList.value = Object.entries(fieldMapping).map(([subField, colLetter]) => ({
          subField,
          colLetter: colLetter as string
        }))
        
        // 加载部件选择
        currentBindingSelectedParts.value = (existingBinding as any).selectedParts || []
      }
    } else {
      currentBindingType.value = 'static'
      currentBindingField.value = ''
      currentBindingSource.value = ''
      fieldMappingList.value = []
      currentBindingSelectedParts.value = []
    }
  })
}

function saveCurrentBinding() {
  if (!selectedCell.value) return
  
  const fieldKey = currentBindingType.value === 'static' ? currentBindingField.value : currentBindingSource.value
  if (!fieldKey) return
  
  const fieldLabel = getFieldLabel(fieldKey)
  
  const newBinding: any = {
    id: `binding_${Date.now()}`,
    sheetId: selectedCell.value.sheetId,
    cellAddress: selectedCell.value.address,
    fieldKey: fieldKey,
    dataType: currentBindingType.value,
  }
  
  // 如果是动态绑定，添加列映射
  if (currentBindingType.value === 'dynamic') {
    const fieldMapping: Record<string, string> = {}
    fieldMappingList.value.forEach(mapping => {
      if (mapping.subField && mapping.colLetter) {
        fieldMapping[mapping.subField] = mapping.colLetter
      }
    })
    ;(newBinding as any).fieldMapping = fieldMapping
    
    // 如果是配置汇总，保存部件选择（实时保存由 watch 处理）
    if (currentBindingSource.value === 'config_summary') {
      ;(newBinding as any).selectedParts = currentBindingSelectedParts.value
    }
  }
  
  // 检查是否已存在
  const existingIndex = bindings.value.findIndex(
    b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
  )
  
  if (existingIndex >= 0) {
    bindings.value[existingIndex] = newBinding
  } else {
    bindings.value.push(newBinding)
  }
  
  // 写入单元格：显示 {{字段标签}}，指定 sheetId 避免跨 sheet 污染
  editorRef.value?.setCellBinding(
    selectedCell.value.row,
    selectedCell.value.col,
    `{{${fieldLabel}}}`,
    undefined,
    selectedCell.value.sheetId
  )
  
  dirty.value = true
  message.success(`已保存绑定`)
}

function unbindCurrentCell() {
  if (!selectedCell.value) return
  const index = bindings.value.findIndex(
    b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
  )
  if (index >= 0) {
    bindings.value.splice(index, 1)
    dirty.value = true
    message.success('已解除绑定')
    
    // 清除单元格显示，指定 sheetId 避免跨 sheet 污染
    editorRef.value?.setCellBinding(
      selectedCell.value.row,
      selectedCell.value.col,
      '',
      undefined,
      selectedCell.value.sheetId
    )
    
    // 重置表单
    currentBindingType.value = 'static'
    currentBindingField.value = ''
    currentBindingSource.value = ''
    fieldMappingList.value = []
  }
}

function addFieldMapping() {
  fieldMappingList.value.push({ subField: '', colLetter: '' })
}

function onFieldMappingChange() {
  if (selectedCell.value && currentBindingType.value === 'dynamic') {
    const bindingIndex = bindings.value.findIndex(
      b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
    )
    
    if (bindingIndex >= 0) {
      const fieldMapping: Record<string, string> = {}
      fieldMappingList.value.forEach(mapping => {
        if (mapping.subField && mapping.colLetter) {
          fieldMapping[mapping.subField] = mapping.colLetter
        }
      })
      const binding = bindings.value[bindingIndex] as any
      bindings.value[bindingIndex] = { ...binding, fieldMapping }
      dirty.value = true
      
      if (templateId.value) {
        univerTemplateApi.update(templateId.value, {
          bindings: bindings.value,
        }).then(() => {
          dirty.value = false
        }).catch((err: any) => {
          message.error(`保存失败: ${err.message}`)
        })
      }
    }
  }
}

function removeFieldMapping(index: number) {
  fieldMappingList.value.splice(index, 1)
  
  // 立即同步到 bindings 并保存
  if (selectedCell.value && currentBindingType.value === 'dynamic') {
    const bindingIndex = bindings.value.findIndex(
      b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
    )
    
    if (bindingIndex >= 0) {
      const fieldMapping: Record<string, string> = {}
      fieldMappingList.value.forEach(mapping => {
        if (mapping.subField && mapping.colLetter) {
          fieldMapping[mapping.subField] = mapping.colLetter
        }
      })
      // 类型断言：确保只在 dynamic binding 上设置 fieldMapping
      const binding = bindings.value[bindingIndex] as any
      bindings.value[bindingIndex] = { ...binding, fieldMapping }
      dirty.value = true
      
      // 立即保存到后端
      if (templateId.value) {
        univerTemplateApi.update(templateId.value, {
          bindings: bindings.value,
        }).then(() => {
          dirty.value = false
        }).catch((err: any) => {
          message.error(`保存失败: ${err.message}`)
        })
      }
    }
  }
}

// 可用列字母 A~Z
const availableColumns = computed(() => {
  const cols: string[] = []
  for (let i = 0; i < 26; i++) {
    cols.push(String.fromCharCode(65 + i))
  }
  return cols
})

// 根据当前数据源返回可用子字段
const availableSubFields = computed(() => {
  const source = currentBindingSource.value
  return dataSourceFields.value[source] || []
})

// 判断某列是否已被其他映射占用
function isColumnMapped(col: string, currentIndex: number): boolean {
  return fieldMappingList.value.some((m, i) => i !== currentIndex && m.colLetter === col)
}

// 是否还能添加更多映射（所有列都被占用时禁用）
const canAddMoreMapping = computed(() => {
  const mappedCols = new Set(fieldMappingList.value.map(m => m.colLetter).filter(Boolean))
  return mappedCols.size < 26
})

// 子字段搜索过滤
function filterSubFieldOption(input: string, option: any) {
  return option.children?.[0]?.children?.toLowerCase().includes(input.toLowerCase())
}

// 当切换数据源时，不再自动填充子字段（用户手动添加）

// 监听 fieldMappingList 变化，同步更新 bindings 数组（不自动保存，由 onFieldMappingChange 和 removeFieldMapping 处理）
watch(
  fieldMappingList,
  () => {
    if (!selectedCell.value || currentBindingType.value !== 'dynamic') return
    
    const bindingIndex = bindings.value.findIndex(
      b => b.cellAddress === selectedCell.value!.address && b.sheetId === selectedCell.value!.sheetId
    )
    
    if (bindingIndex >= 0) {
      const binding = bindings.value[bindingIndex] as any
      const fieldMapping: Record<string, string> = {}
      fieldMappingList.value.forEach(mapping => {
        if (mapping.subField && mapping.colLetter) {
          fieldMapping[mapping.subField] = mapping.colLetter
        }
      })
      // 替换整个对象，确保 Vue 响应式追踪
      bindings.value[bindingIndex] = { ...binding, fieldMapping }
      dirty.value = true
    }
  },
  { deep: true }
)

function removeBinding(bindingId: string) {
  const binding = bindings.value.find(b => b.id === bindingId)
  if (binding) {
    // 清除单元格内容
    const pos = cellAddressToRowCol(binding.cellAddress)
    if (pos) {
      editorRef.value?.clearCellBinding(pos.row, pos.col)
    }
  }
  
  bindings.value = bindings.value.filter(b => b.id !== bindingId)
  dirty.value = true
  message.success('已删除绑定')
}

/**
 * Convert cellAddress (e.g. "A1") to 0-indexed row/col
 */
function cellAddressToRowCol(addr: string): { row: number; col: number } | null {
  const match = addr.match(/^([A-Z]+)(\d+)$/)
  if (!match) return null
  const colStr = match[1]
  const row = parseInt(match[2]) - 1
  let col = 0
  for (let i = 0; i < colStr.length; i++) {
    col = col * 26 + (colStr.charCodeAt(i) - 64)
  }
  col -= 1
  return { row, col }
}

async function handleSave() {
  if (!displayName.value.trim()) {
    message.warning('请输入模板名称')
    return
  }
  
  // 检查重复绑定
  const duplicateBindings = checkDuplicateBindings()
  if (duplicateBindings.length > 0) {
    const cells = duplicateBindings.map(b => b.cellAddress).join(', ')
    message.warning(`发现重复绑定: ${cells}。请检查并修正。`)
    return
  }
  
  // 如果正在预览，先退出预览
  if (isPreviewing.value) {
    previewData.value = undefined
    isPreviewing.value = false
    await nextTick()
  }
  
  saving.value = true
  try {
    // 获取当前 Univer 的 snapshot（包含绑定修改，但不包含预览数据）
    const latestSnapshot = editorRef.value?.getWorkbookData()
    if (!latestSnapshot) {
      throw new Error('无法获取工作簿数据')
    }
    
    // 清除所有绑定字段的背景色（只保留值，不保留样式）
    // 背景色仅用于编辑时标识绑定，不应保存到模板中
    for (const binding of bindings.value) {
      const pos = cellAddressToRowCol(binding.cellAddress)
      if (!pos) continue
      
      const sheet = latestSnapshot.sheets[binding.sheetId]
      if (!sheet?.cellData?.[pos.row]?.[pos.col]) continue
      
      // 清除背景色，保留值
      const cell = sheet.cellData[pos.row][pos.col]
      if (cell.s) {
        delete cell.s.bg
        delete cell.s.background
      }
      delete cell.bg
      delete cell.background
    }
    
    await univerTemplateApi.update(templateId.value, {
      display_name: displayName.value,
      workbook_snapshot: latestSnapshot,
      bindings: bindings.value,
    })
    
    message.success('保存成功')
    dirty.value = false
  } catch (err: any) {
    message.error(`保存失败: ${err.message}`)
  } finally {
    saving.value = false
  }
}

/**
 * 检查重复绑定
 */
function checkDuplicateBindings(): Binding[] {
  const seen = new Map<string, Binding>()
  const duplicates: Binding[] = []
  
  for (const binding of bindings.value) {
    const key = `${binding.sheetId}:${binding.cellAddress}`
    if (seen.has(key)) {
      duplicates.push(binding)
    } else {
      seen.set(key, binding)
    }
  }
  
  return duplicates
}
/**
 * 等待 Univer 实例就绪（轮询 editorRef）
 */
async function waitForUniverReady(): Promise<void> {
  const maxWait = 3000
  const interval = 100
  let waited = 0
  while (waited < maxWait) {
    if (isUnmounted.value) return
    if (editorRef.value) {
      // editorRef 存在即认为 Univer 已渲染
      return
    }
    await new Promise(resolve => setTimeout(resolve, interval))
    waited += interval
  }
  console.warn('[UniverTemplateEditor] Univer 渲染超时')
}

async function loadTemplate() {
  try {
    const data = await univerTemplateApi.getById(templateId.value)
    if (isUnmounted.value) return
    template.value = data
    displayName.value = data.display_name
    workbookData.value = data.workbook_snapshot
    bindings.value = data.bindings || []
    
    // 加载后恢复已有绑定的单元格显示
    // 等待 Univer 渲染完成后恢复绑定显示
    await waitForUniverReady()
    if (isUnmounted.value) return
    restoreBindingCells()
  } catch (err: any) {
    if (!isUnmounted.value) {
      message.error(`加载模板失败: ${err.message}`)
    }
  }
}

/**
 * 恢复已有绑定在单元格中的显示
 */
function restoreBindingCells() {
  for (const binding of bindings.value) {
    const pos = cellAddressToRowCol(binding.cellAddress)
    if (!pos) continue
    
    const fieldLabel = getFieldLabel(binding.fieldKey)
    // 指定 sheetId 避免跨 sheet 污染
    editorRef.value?.setCellBinding(pos.row, pos.col, `{{${fieldLabel}}}`, undefined, binding.sheetId)
  }
}

onMounted(async () => {
  // 先加载商机列表（恢复选择需要）
  await loadOpportunityList()
  
  // 加载字段列表
  await loadFields()
  
  // 恢复选择
  loadSelectionFromStorage()
  
  // 加载模板
  await loadTemplate()
})
</script>

<style scoped>
.univer-template-editor {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--cpq-bg-primary);
  overflow: hidden;
  color: var(--cpq-text-primary);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--cpq-bg-secondary);
  border-bottom: 1px solid var(--cpq-border-primary);
  backdrop-filter: blur(10px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.template-name-input {
  width: 300px;
}

.template-name-input :deep(.ant-input) {
  background: var(--cpq-bg-input);
  border-color: var(--cpq-border-primary);
  color: var(--cpq-text-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-right :deep(.ant-select-selector) {
  background: var(--cpq-bg-input) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}

.header-right :deep(.ant-select-selection-placeholder) {
  color: var(--cpq-text-muted) !important;
}

.header-right :deep(.ant-select-arrow) {
  color: var(--cpq-text-muted) !important;
}

.main-content {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.panel-title {
  padding: 16px 20px;
  font-weight: 600;
  font-size: 14px;
  color: var(--cpq-text-primary);
  border-bottom: 1px solid var(--cpq-border-secondary);
  background: var(--cpq-overlay-w3);
}

.center-panel {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-width: 0;
  background: white;
}

.editor-layer,
.preview-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.preview-layer {
  z-index: 10;
}

.center-panel :deep(.univer-container) {
  width: 100% !important;
  height: 100% !important;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--cpq-text-secondary);
}

.right-panel {
  width: 320px;
  background: var(--cpq-bg-secondary);
  border-left: 1px solid var(--cpq-border-primary);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(10px);
}

.current-binding {
  padding: 20px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.binding-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.binding-header span:first-child {
  color: var(--cpq-text-secondary);
  font-size: 13px;
}

.cell-address {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  color: var(--cpq-accent-primary);
  font-size: 14px;
}

.binding-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-item label {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}

.form-item :deep(.ant-radio-button-wrapper) {
  background: var(--cpq-bg-input);
  border-color: var(--cpq-border-primary);
  color: var(--cpq-text-secondary);
}

.form-item :deep(.ant-radio-button-wrapper-checked) {
  background: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-text-inverse);
}

.form-item :deep(.ant-select-selector) {
  background: var(--cpq-bg-input) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}

.no-selection {
  padding: 40px 20px;
  text-align: center;
  color: var(--cpq-text-muted);
}

.bindings-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-header {
  padding: 14px 20px;
  font-weight: 500;
  font-size: 13px;
  color: var(--cpq-text-secondary);
  border-bottom: 1px solid var(--cpq-border-secondary);
  background: var(--cpq-overlay-w3);
}

.list-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.binding-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--cpq-bg-tertiary);
  border: 1px solid var(--cpq-border-primary);
  border-radius: 6px;
  margin-bottom: 6px;
}

.binding-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.binding-cell {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  color: var(--cpq-accent-primary);
  font-size: 13px;
}

.binding-field {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}

.empty-bindings {
  padding: 24px;
  text-align: center;
  color: var(--cpq-text-muted);
  font-size: 13px;
}

.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: var(--cpq-bg-secondary);
  border-top: 1px solid var(--cpq-border-primary);
  backdrop-filter: blur(10px);
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--cpq-text-secondary);
  font-size: 13px;
}

.footer-left :deep(.ant-select-selector) {
  background: var(--cpq-bg-input) !important;
  border-color: var(--cpq-border-primary) !important;
  color: var(--cpq-text-primary) !important;
}

.footer-left :deep(.ant-switch) {
  background: var(--cpq-bg-input);
}

.footer-left :deep(.ant-switch-checked) {
  background: var(--cpq-accent-primary);
}

.footer-right {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

/* Scrollbar styling */
.list-content::-webkit-scrollbar {
  width: 6px;
}

.list-content::-webkit-scrollbar-track {
  background: var(--cpq-bg-tertiary);
}

.list-content::-webkit-scrollbar-thumb {
  background: var(--cpq-border-primary);
  border-radius: 3px;
}

.list-content::-webkit-scrollbar-thumb:hover {
  background: var(--cpq-border-light);
}
</style>
