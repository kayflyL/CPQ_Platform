import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

// ════════════════════════════════════════════════════════════
// Excel 解析 composable —— 模块级单例。
// 解析上下文全局唯一(一次只解析一个文件)，设置页与商机预览弹窗
// 互斥存在，故共享同一份规则与预览状态。热力图渲染专属逻辑
// (getCellClass/getCellTooltip/regionColorMap)留在 ParseHeatmapPreview
// 组件内自包含，这里只管数据 + 规则 CRUD + 文件预览。
// ════════════════════════════════════════════════════════════

// ── 数据状态 ──
const parseRegions = ref<any[]>([])
const parseFieldRules = ref<any[]>([])
const businessFields = ref<any[]>([])
const previewData = ref<any>(null)
const parseResult = ref<any>(null)
const loadingRules = ref(false)
const parsing = ref(false)
const uploadedFile = ref<File | null>(null)

// ── KP 分类映射 ──
const kpMappings = ref<any[]>([])
const loadingMappings = ref(false)
const adding = ref(false)
const newKeyword = ref('')
const newCategory = ref('')
const editingMappingId = ref<number | null>(null)
const mappingColumns = [
  { title: '关键词', dataIndex: 'keyword', key: 'keyword', width: 100 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 80 },
  { title: '', key: 'action', width: 55 }
]

// ── UI 状态 ──
const expandedRegions = ref<string[]>([])
const expandedDynamicRegions = ref<string[]>([])
const showAddRegionModal = ref(false)
const showAddFieldRuleModal = ref(false)
const editingRegion = ref<any>(null)
const editingFieldRule = ref<any>(null)

// ── 表单 ──
const regionForm = reactive({
  name: '',
  startKeywordsList: [] as string[],
  endKeywordsList: [] as string[],
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

// ── 表格列定义 ──
const fieldRuleColumns = [
  { title: '字段', dataIndex: 'field_key', key: 'field_key', width: 85, ellipsis: true },
  { title: '区域', dataIndex: 'region', key: 'region', width: 50 },
  { title: '状态', key: 'enabled', width: 45 },
  { title: '', key: 'action', width: 55 }
]

// 将数据库的逗号分隔字符串转换为标签数组
function parseKeywords(keywordsStr: string): string[] {
  if (!keywordsStr) return []
  return keywordsStr.split(',').map(k => k.trim()).filter(k => k)
}

// 将标签数组转换为逗号分隔字符串
function joinKeywords(keywordsList: string[]): string {
  return keywordsList.join(',')
}

// ── KP 分类映射 CRUD ──
async function loadMappings() {
  loadingMappings.value = true
  try {
    const res = await axios.get('/api/rules/kp-category-mappings')
    kpMappings.value = res.data.mappings || []
  } catch {
    message.error('加载 KP 分类映射失败')
  } finally {
    loadingMappings.value = false
  }
}

async function handleAddMapping() {
  if (!newKeyword.value.trim() || !newCategory.value) {
    message.warning('请填写关键词和分类')
    return
  }
  adding.value = true
  try {
    await axios.post('/api/rules/kp-category-mappings', {
      keyword: newKeyword.value.trim(),
      category: newCategory.value
    })
    message.success('映射已添加')
    newKeyword.value = ''
    newCategory.value = ''
    await loadMappings()
  } catch {
    message.error('添加失败')
  } finally {
    adding.value = false
  }
}

function handleEditMapping(record: any) {
  editingMappingId.value = record.id
}

async function handleCancelMappingEdit() {
  editingMappingId.value = null
  await loadMappings()
}

async function handleSaveMappingEdit(record: any) {
  try {
    await axios.put(`/api/rules/kp-category-mappings/${record.id}`, {
      keyword: record.keyword,
      category: record.category
    })
    message.success('已保存')
    editingMappingId.value = null
  } catch {
    message.error('保存失败')
  }
}

async function handleDeleteMapping(id: number) {
  try {
    await axios.delete(`/api/rules/kp-category-mappings/${id}`)
    message.success('已删除')
    await loadMappings()
  } catch {
    message.error('删除失败')
  }
}

// ── 规则加载 ──
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

async function loadBusinessFields() {
  try {
    const res = await axios.get('/api/admin/business-fields')
    businessFields.value = Array.isArray(res.data) ? res.data : (res.data.fields || [])
  } catch (error) {
    console.error('Failed to load business fields:', error)
  }
}

// ── 文件上传 + 预览（不落库，纯解析） ──
async function handleFileUpload(file: File, silent = false) {
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

    if (parseResult.value?.dynamic_regions) {
      expandedDynamicRegions.value = Object.keys(parseResult.value.dynamic_regions)
    }

    if (!silent) message.success('解析完成')
  } catch (error: any) {
    console.error('Parse failed:', error)
    message.error(error.response?.data?.detail || '解析失败')
  } finally {
    parsing.value = false
  }
  return false
}

// 用缓存文件刷新预览（规则改动后重算）
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
    if (parseResult.value?.dynamic_regions) {
      expandedDynamicRegions.value = Object.keys(parseResult.value.dynamic_regions)
    }
  } catch (error: any) {
    console.error('Refresh preview failed:', error)
  } finally {
    parsing.value = false
  }
}

// ── 区域 CRUD ──
function editRegion(region: any) {
  editingRegion.value = region
  Object.assign(regionForm, {
    name: region.name,
    startKeywordsList: parseKeywords(region.start_keywords || ''),
    endKeywordsList: parseKeywords(region.end_keywords || ''),
    skip_header_rows: region.skip_header_rows,
    sort_order: region.sort_order
  })
  showAddRegionModal.value = true
}

function cancelEditRegion() {
  editingRegion.value = null
  Object.assign(regionForm, {
    name: '',
    startKeywordsList: [],
    endKeywordsList: [],
    skip_header_rows: 0,
    sort_order: 0
  })
}

async function saveRegion() {
  if (!regionForm.name) {
    message.warning('请填写区域名称')
    return
  }

  const payload = {
    name: regionForm.name,
    start_keywords: joinKeywords(regionForm.startKeywordsList),
    end_keywords: joinKeywords(regionForm.endKeywordsList),
    skip_header_rows: regionForm.skip_header_rows,
    sort_order: regionForm.sort_order
  }

  try {
    if (editingRegion.value) {
      await axios.put(`/api/rules/parse-regions/${editingRegion.value.id}`, payload)
      message.success('更新成功')
    } else {
      await axios.post('/api/rules/parse-regions', { regions: [...parseRegions.value, payload] })
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

// ── 字段规则 CRUD ──
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

// ── 辅助函数 ──
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

export function useExcelParser() {
  return {
    // 数据状态
    parseRegions, parseFieldRules, businessFields,
    previewData, parseResult, loadingRules, parsing, uploadedFile,
    // KP 映射
    kpMappings, loadingMappings, adding, newKeyword, newCategory,
    editingMappingId, mappingColumns,
    loadMappings, handleAddMapping, handleEditMapping,
    handleCancelMappingEdit, handleSaveMappingEdit, handleDeleteMapping,
    // 规则加载
    loadRules, loadBusinessFields,
    // 文件 + 预览
    handleFileUpload, refreshPreview,
    // 区域 CRUD
    expandedRegions, showAddRegionModal, editingRegion, regionForm,
    editRegion, cancelEditRegion, saveRegion, deleteRegion,
    // 字段规则 CRUD
    showAddFieldRuleModal, editingFieldRule, fieldRuleForm, fieldRuleColumns,
    editFieldRule, cancelEditFieldRule, saveFieldRule, deleteFieldRule,
    // 辅助
    filterOption, getDynamicColumns, expandedDynamicRegions,
    parseKeywords, joinKeywords
  }
}
