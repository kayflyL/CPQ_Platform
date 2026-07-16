import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ParseTemplate, ParsedResult } from '@/types/parseTemplate'

export const useParseTemplateStore = defineStore('parseTemplate', () => {
  // 状态
  const templates = ref<ParseTemplate[]>([])
  const currentTemplate = ref<ParseTemplate | null>(null)
  const parsedResult = ref<ParsedResult | null>(null)
  const parsing = ref(false)

  // 计算属性
  const templateList = computed(() => 
    templates.value.map(t => ({
      id: t.id,
      name: t.name,
      description: t.description,
      createdAt: t.createdAt
    }))
  )

  // 保存模板（新增或更新）
  function saveTemplate(template: ParseTemplate) {
    const index = templates.value.findIndex(t => t.id === template.id)
    if (index >= 0) {
      templates.value[index] = template
    } else {
      templates.value.push(template)
    }
  }

  // 加载模板
  function loadTemplate(id: string) {
    const template = templates.value.find(t => t.id === id)
    if (template) {
      currentTemplate.value = { ...template }
    }
  }

  // 删除模板
  function deleteTemplate(id: string) {
    templates.value = templates.value.filter(t => t.id !== id)
    if (currentTemplate.value?.id === id) {
      currentTemplate.value = null
    }
  }

  // 更新当前模板
  function updateCurrentTemplate(updates: Partial<ParseTemplate>) {
    if (currentTemplate.value) {
      currentTemplate.value = { ...currentTemplate.value, ...updates }
    }
  }

  // 创建新模板
  function createNewTemplate() {
    const newTemplate: ParseTemplate = {
      id: `template_${Date.now()}`,
      name: '',
      description: '',
      createdAt: Date.now(),
      staticBindings: [],
      dynamicRegions: []
    }
    currentTemplate.value = newTemplate
    return newTemplate
  }

  // 设置解析结果
  function setParsedResult(result: ParsedResult) {
    parsedResult.value = result
  }

  // 清空解析结果
  function clearParsedResult() {
    parsedResult.value = null
  }

  // 设置解析状态
  function setParsing(value: boolean) {
    parsing.value = value
  }

  // 从localStorage加载
  function loadFromStorage() {
    const stored = localStorage.getItem('parseTemplates')
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed) && parsed.length > 0) {
          templates.value = parsed
        } else {
          seedDefaultTemplate()
        }
      } catch (e) {
        console.error('Failed to parse templates from storage:', e)
        seedDefaultTemplate()
      }
    } else {
      seedDefaultTemplate()
    }
  }

  // 立即加载（store初始化时执行）
  loadFromStorage()

  // 注入默认模板（基于CFG详细表-7.xlsx）
  function seedDefaultTemplate() {
    const defaultTemplate: ParseTemplate = {
      id: 'template_cfg_v7',
      name: 'CFG详细表模板',
      description: '基于CFG详细表-7.xlsx的解析模板，适用于标准CFG报价单',
      createdAt: Date.now(),
      staticBindings: [
        { id: 'sb1', fieldKey: 'project_code', sheetName: 'CFG2', cellAddress: 'A1', dataType: 'static' },
        { id: 'sb2', fieldKey: 'project_name', sheetName: 'CFG2', cellAddress: 'D2', dataType: 'static' },
        { id: 'sb3', fieldKey: 'model_qty', sheetName: 'CFG2', cellAddress: 'D3', dataType: 'static' },
        { id: 'sb4', fieldKey: 'sales', sheetName: 'CFG2', cellAddress: 'I2', dataType: 'static' },
        { id: 'sb5', fieldKey: 'fae', sheetName: 'CFG2', cellAddress: 'I3', dataType: 'static' },
        { id: 'sb6', fieldKey: 'date', sheetName: 'CFG2', cellAddress: 'I4', dataType: 'static' },
        { id: 'sb7', fieldKey: 'spec', sheetName: 'CFG2', cellAddress: 'E4', dataType: 'static' },
        { id: 'sb8', fieldKey: 'total_price', sheetName: 'CFG2', cellAddress: 'H26', dataType: 'static' },
      ],
      dynamicRegions: [
        {
          id: 'l6_region',
          name: 'L6明细',
          regionType: 'l6',
          fieldKey: 'l6_details',
          fieldLabel: 'L6配件明细',
          startKeywords: 'Catalogue',
          endKeywords: 'Keyparts',
          fieldMapping: {
            item_no: 'B',
            category: 'C',
            catalogue: 'D',
            description: 'E',
            quantity: 'F',
            quotation: 'H',
            note: 'I'
          }
        },
        {
          id: 'kp_region',
          name: 'Keyparts明细',
          regionType: 'kp',
          fieldKey: 'kp_details',
          fieldLabel: 'KP配件明细',
          startKeywords: 'Component Description',
          endKeywords: 'Warranty',
          fieldMapping: {
            item_no: 'B',
            category: 'C',
            component: 'D',
            description: 'E',
            quantity: 'F',
            unit_price: 'G',
            total_price: 'H',
            note: 'I'
          }
        }
      ]
    }
    templates.value = [defaultTemplate]
    saveToStorage()
  }

  // 保存到localStorage
  function saveToStorage() {
    localStorage.setItem('parseTemplates', JSON.stringify(templates.value))
  }

  return {
    // 状态
    templates,
    currentTemplate,
    parsedResult,
    parsing,
    
    // 计算属性
    templateList,
    
    // 方法
    saveTemplate,
    loadTemplate,
    deleteTemplate,
    updateCurrentTemplate,
    createNewTemplate,
    setParsedResult,
    clearParsedResult,
    setParsing,
    loadFromStorage,
    saveToStorage
  }
})
