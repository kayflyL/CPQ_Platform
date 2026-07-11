import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  TemplateData,
  SheetRenderData,
  CellBinding,
  BusinessField,
  ProductRow,
  RenderCell,
  TemplateEditorState
} from '@/types/template'
import { parseExcelTemplate } from '@/utils/excel-generator'
import { exportTemplateApi } from '@/api'
import { useParseTemplateStore } from './parseTemplate'

export const useTemplateStore = defineStore('template', () => {
  // 状态
  const templateData = ref<TemplateData | null>(null)
  const editorState = ref<TemplateEditorState>({
    currentSheetIndex: 0,
    selectedCell: null,
    loading: false
  })

  // 业务字段定义（动态获取）
  const businessFields = ref<BusinessField[]>([])

  // 加载业务字段定义
  async function loadBusinessFields() {
    try {
      const fields = await exportTemplateApi.getFields()
      businessFields.value = fields.map((f: any) => ({
        key: f.key,
        label: f.label,
        category: f.category as 'opportunity' | 'item' | 'l6' | 'kp' | 'system',
        source: 'system' as const
      }))
    } catch (e) {
      console.error('Failed to load business fields:', e)
    }
  }

  // 从解析模板获取动态区域字段（合并到业务字段列表）
  const parseRegionFields = computed<BusinessField[]>(() => {
    const parseStore = useParseTemplateStore()
    const fields: BusinessField[] = []
    for (const region of parseStore.templates.flatMap(t => t.dynamicRegions)) {
      if (region.fieldKey) {
        fields.push({
          key: region.fieldKey,
          label: region.fieldLabel || region.name,
          category: 'parse_region',
          source: 'parse'
        })
      }
    }
    return fields
  })

  // 所有可用字段（系统字段 + 解析区域字段）
  const allFields = computed<BusinessField[]>(() => {
    return [...businessFields.value, ...parseRegionFields.value]
  })

  // 计算属性
  const currentSheet = computed<SheetRenderData | null>(() => {
    if (!templateData.value) return null
    return templateData.value.sheets[editorState.value.currentSheetIndex] || null
  })

  const currentBindings = computed<CellBinding[]>(() => {
    if (!templateData.value || !currentSheet.value) return []
    return templateData.value.bindings.filter(
      b => b.sheetName === currentSheet.value!.name
    )
  })

  const getBindingForCell = (sheetName: string, cellAddress: string) => {
    if (!templateData.value) return null
    return templateData.value.bindings.find(
      b => b.sheetName === sheetName && b.cellAddress === cellAddress
    ) || null
  }

  // 加载模板
  async function loadTemplate(file: File) {
    editorState.value.loading = true
    try {
      const buffer = await file.arrayBuffer()
      const sheets = await parseExcelTemplate(buffer)
      
      templateData.value = {
        fileBuffer: buffer,
        fileName: file.name,
        sheets,
        bindings: [],
        productData: [],
        staticData: {}
      }
      
      editorState.value.currentSheetIndex = 0
      editorState.value.selectedCell = null
    } finally {
      editorState.value.loading = false
    }
  }

  // 设置单元格绑定
  function setCellBinding(binding: Omit<CellBinding, 'id'>) {
    if (!templateData.value) return
    
    const existingIndex = templateData.value.bindings.findIndex(
      b => b.sheetName === binding.sheetName && b.cellAddress === binding.cellAddress
    )
    
    if (existingIndex >= 0) {
      templateData.value.bindings[existingIndex] = {
        ...binding,
        id: `${binding.sheetName}_${binding.cellAddress}`
      }
    } else {
      templateData.value.bindings.push({
        ...binding,
        id: `${binding.sheetName}_${binding.cellAddress}`
      })
    }
  }

  // 移除单元格绑定
  function removeCellBinding(sheetName: string, cellAddress: string) {
    if (!templateData.value) return
    const index = templateData.value.bindings.findIndex(
      b => b.sheetName === sheetName && b.cellAddress === cellAddress
    )
    if (index >= 0) {
      templateData.value.bindings.splice(index, 1)
    }
  }

  // 选择单元格
  function selectCell(cell: RenderCell | null) {
    editorState.value.selectedCell = cell
  }

  // 切换工作表
  function switchSheet(index: number) {
    editorState.value.currentSheetIndex = index
    editorState.value.selectedCell = null
  }

  // 设置产品数据
  function setProductData(data: ProductRow[]) {
    if (!templateData.value) return
    templateData.value.productData = data
  }

  // 设置静态数据
  function setStaticData(key: string, value: string | number | null) {
    if (!templateData.value) return
    templateData.value.staticData[key] = value
  }

  // 重置
  function reset() {
    templateData.value = null
    editorState.value = {
      currentSheetIndex: 0,
      selectedCell: null,
      loading: false
    }
  }

  return {
    // 状态
    templateData,
    editorState,
    businessFields,
    
    // 计算属性
    currentSheet,
    currentBindings,
    parseRegionFields,
    allFields,
    
    // 方法
    getBindingForCell,
    loadTemplate,
    loadBusinessFields,
    setCellBinding,
    removeCellBinding,
    selectCell,
    switchSheet,
    setProductData,
    setStaticData,
    reset
  }
})
