<template>
  <a-modal
    v-model:open="visible"
    title="模板预览"
    width="90%"
    :footer="null"
    @cancel="handleClose"
  >
    <div class="preview-modal-content">
      <!-- 数据源选择 -->
      <div class="preview-toolbar">
        <a-space>
          <span>数据源：</span>
          <a-radio-group v-model:value="dataSourceType" @change="handleDataSourceChange">
            <a-radio-button value="sample">示例数据</a-radio-button>
            <a-radio-button value="opportunity">商机数据</a-radio-button>
          </a-radio-group>
          
          <a-select
            v-if="dataSourceType === 'opportunity'"
            v-model:value="selectedOpportunityId"
            placeholder="选择商机"
            style="width: 300px"
            show-search
            :filter-option="filterOpportunity"
            @change="loadOpportunityData"
          >
            <a-select-option
              v-for="opp in opportunities"
              :key="opp.id"
              :value="opp.id"
            >
              {{ opp.name }} - {{ opp.customer_name }}
            </a-select-option>
          </a-select>
        </a-space>
        
        <a-space>
          <a-button @click="handleExport" :loading="exporting">
            <template #icon><DownloadOutlined /></template>
            导出 Excel
          </a-button>
        </a-space>
      </div>

      <!-- Univer 预览区域 -->
      <div class="preview-area">
        <UniverSheet
          v-if="previewData"
          ref="univerSheetRef"
          :workbook-data="previewData"
          :editable="false"
        />
        <a-spin v-else tip="加载中..." />
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { DownloadOutlined } from '@ant-design/icons-vue'
import UniverSheet from './UniverSheet.vue'
import { templateApi, opportunityApi } from '@/api/template'
import type { ExportTemplate } from '@/api/template'

const props = defineProps<{
  template: ExportTemplate | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const visible = ref(true)
const univerSheetRef = ref<InstanceType<typeof UniverSheet> | null>(null)

// 数据源
const dataSourceType = ref<'sample' | 'opportunity'>('sample')
const selectedOpportunityId = ref<number | null>(null)
const opportunities = ref<any[]>([])
const opportunityData = ref<any>(null)
const exporting = ref(false)

// 示例数据
const sampleData = {
  customer_name: '示例客户有限公司',
  quote_date: '2026-07-12',
  contact_person: '张三',
  contact_phone: '13800138000',
  total_amount: '¥120,000',
  items: [
    { product_name: '产品A', quantity: 10, unit_price: 1000, total_price: 10000 },
    { product_name: '产品B', quantity: 20, unit_price: 2000, total_price: 40000 }
  ]
}

// 计算预览数据
const previewData = computed(() => {
  if (!props.template || !props.template.workbook_snapshot) return null
  
  const snapshot = JSON.parse(JSON.stringify(props.template.workbook_snapshot))
  const bindingsArray = props.template.cell_bindings || []
  
  // 选择数据源
  const data = dataSourceType.value === 'sample' 
    ? sampleData 
    : opportunityData.value
  
  if (!data) return snapshot
  
  // 注入数据到单元格（处理数组格式的 bindings）
  for (const binding of bindingsArray) {
    const sheetId = binding.sheetId
    const cellAddress = binding.cellAddress
    const fieldKey = binding.fieldKey
    
    if (!sheetId || !cellAddress || !fieldKey) continue
    
    const sheet = snapshot.sheets[sheetId] as any
    if (!sheet) continue
    
    const { row, col } = parseCellAddress(cellAddress)
    if (!sheet.cellData) sheet.cellData = {}
    if (!sheet.cellData[row]) sheet.cellData[row] = {}
    
    const value = data[fieldKey]
    if (value !== undefined && value !== null) {
      sheet.cellData[row][col] = { v: value }
    }
  }
  
  // 确保每个 sheet 的行列范围至少为 Excel 默认值，避免预览区域过小
  for (const sheet of Object.values(snapshot.sheets) as any[]) {
    if (!sheet) continue
    if (!sheet.rowCount || sheet.rowCount < 1000) {
      sheet.rowCount = 1000
    }
    if (!sheet.columnCount || sheet.columnCount < 26) {
      sheet.columnCount = 26
    }
  }
  
  return snapshot
})

// 解析单元格地址（如 "A1" -> { row: 0, col: 0 }）
function parseCellAddress(address: string): { row: number; col: number } {
  const match = address.match(/^([A-Z]+)(\d+)$/)
  if (!match) return { row: 0, col: 0 }
  
  const colStr = match[1]
  const row = parseInt(match[2]) - 1
  
  let col = 0
  for (let i = 0; i < colStr.length; i++) {
    col = col * 26 + (colStr.charCodeAt(i) - 64)
  }
  col -= 1
  
  return { row, col }
}

// 加载商机列表
async function loadOpportunities() {
  try {
    opportunities.value = await opportunityApi.list()
  } catch (error) {
    console.error('加载商机列表失败', error)
    message.error('加载商机列表失败')
  }
}

// 加载商机数据
async function loadOpportunityData() {
  if (!selectedOpportunityId.value) return
  
  try {
    opportunityData.value = await opportunityApi.getQuoteData(String(selectedOpportunityId.value))
  } catch (error) {
    console.error('加载商机数据失败', error)
    message.error('加载商机数据失败')
  }
}

// 数据源切换
function handleDataSourceChange() {
  if (dataSourceType.value === 'opportunity' && opportunities.value.length === 0) {
    loadOpportunities()
  }
}

// 筛选商机
function filterOpportunity(input: string, option: any) {
  return option.label.toLowerCase().includes(input.toLowerCase())
}

// 导出 Excel
async function handleExport() {
  if (!univerSheetRef.value) {
    message.error('预览组件未就绪')
    return
  }
  
  exporting.value = true
  try {
    if (!props.template) {
      message.error('模板数据不存在')
      return
    }
    const snapshot = univerSheetRef.value.getWorkbookData()
    const bindings = props.template.cell_bindings || {}
    
    // 获取当前数据源的业务数据
    const businessData = dataSourceType.value === 'sample' 
      ? sampleData 
      : opportunityData.value
    
    const blob = await templateApi.exportToExcel(snapshot, bindings, businessData || {})
    
    // 下载文件
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.template.display_name || props.template.name}.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    message.success('导出成功')
  } catch (error) {
    console.error('导出失败', error)
    message.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// 关闭弹窗
function handleClose() {
  visible.value = false
  emit('close')
}

onMounted(() => {
  if (dataSourceType.value === 'opportunity') {
    loadOpportunities()
  }
})
</script>

<style scoped>
.preview-modal-content {
  display: flex;
  flex-direction: column;
  height: 70vh;
}

.preview-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.preview-area {
  flex: 1;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f5;
}
</style>
