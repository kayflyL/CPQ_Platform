<template>
  <div class="business-fields-page">
    <!-- Page Header -->
    <div class="page-header">
      <h2>📋 字段管理</h2>
      <div class="header-actions">
        <a-button size="small" @click="showExport">
          <template #icon><ExportOutlined /></template>
          导出
        </a-button>
        <a-button size="small" @click="showImport">
          <template #icon><ImportOutlined /></template>
          导入
        </a-button>
        <a-button type="primary" size="small" @click="openAddModal">
          <template #icon><PlusOutlined /></template>
          新增字段
        </a-button>
      </div>
    </div>

    <!-- Main Layout -->
    <div class="main-layout">
      <!-- Left Sidebar: Object Tree -->
      <div class="sidebar">
        <div class="tree-header">对象导航</div>
        <div class="tree-content">
          <div v-for="obj in objectTree" :key="obj.key" class="tree-node">
            <div class="tree-object" @click="toggleObject(obj.key)">
              <span class="tree-icon">{{ expandedObjects[obj.key] ? '▼' : '▶' }}</span>
              <span class="tree-label">{{ obj.label }}</span>
              <span class="tree-count">{{ obj.count }}</span>
            </div>
            <div v-if="expandedObjects[obj.key]" class="tree-groups">
              <div 
                v-for="group in obj.groups" 
                :key="group.name"
                :class="['tree-group', { active: activeFilter === `${obj.key}:${group.name}` }]"
                @click="setFilter(obj.key, group.name)"
              >
                {{ group.label }}
                <span class="tree-count">{{ group.count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Content: Field Table -->
      <div class="content">
        <div class="content-header">
          <div class="filter-info">
            <span v-if="!activeFilter">全部字段 ({{ filteredFields.length }})</span>
            <span v-else>{{ currentObjectLabel }} / {{ currentGroupLabel }} ({{ filteredFields.length }})</span>
          </div>
          <div class="search-box">
            <a-input
              v-model:value="searchText"
              placeholder="搜索字段..."
              size="small"
              style="width: 200px;"
              allow-clear
            />
          </div>
        </div>

        <!-- Table -->
        <div class="table-wrapper">
          <a-table
            :dataSource="filteredFields"
            :columns="columns"
            :pagination="false"
            :rowClassName="(_r: any, i: number) => i % 2 === 0 ? 'table-row-even' : 'table-row-odd'"
            size="small"
            rowKey="key"
            :scroll="{ x: 900 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'export_visible'">
                <a-switch
                  :checked="record.export_visible ?? true"
                  checked-children="可见"
                  un-checked-children="隐藏"
                  size="small"
                  @change="(val: boolean) => toggleExportVisible(record, val)"
                />
              </template>
              <template v-if="column.key === 'label'">
                <a-input
                  :value="record.label"
                  size="small"
                  style="width: 120px;"
                  @change="(e: any) => record.label = e.target.value"
                  @blur="saveField(record)"
                />
              </template>
              <template v-if="column.key === 'display_type'">
                <a-select
                  :value="record.display_type || 'text'"
                  @change="(val: string) => { record.display_type = val; saveField(record) }"
                  size="small"
                  style="width: 100px;"
                >
                  <a-select-option value="text">文本</a-select-option>
                  <a-select-option value="number">数字</a-select-option>
                  <a-select-option value="money">金额</a-select-option>
                  <a-select-option value="percent">百分比</a-select-option>
                  <a-select-option value="date">日期</a-select-option>
                  <a-select-option value="enum">单选</a-select-option>
                  <a-select-option value="boolean">布尔</a-select-option>
                </a-select>
              </template>
              <template v-if="column.key === 'source_info'">
                <span style="font-size: 12px; color: var(--cpq-text-secondary, #999);">{{ getSource(record) }}</span>
              </template>
              <template v-if="column.key === 'action'">
                <a-space>
                  <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
                  <a-popconfirm
                    title="确定删除该字段？"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="deleteField(record)"
                  >
                    <a-button type="link" danger size="small">删除</a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
            <template #emptyText>
              <a-empty description="暂无字段" />
            </template>
          </a-table>
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <a-modal
      v-model:open="addModalVisible"
      :title="isEditing ? '编辑字段' : '新增业务字段'"
      @ok="handleSave"
      :confirmLoading="addLoading"
      ok-text="确定"
      cancel-text="取消"
      width="680px"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="字段 Key" required>
              <a-input 
                v-model:value="editField.key" 
                placeholder="如: custom_field" 
                :disabled="isEditing"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="显示名称" required>
              <a-input v-model:value="editField.label" placeholder="如: 自定义字段" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="分类" required>
              <a-select v-model:value="editField.category" placeholder="选择分类">
                <a-select-option value="opportunity">商机</a-select-option>
                <a-select-option value="item">配置项</a-select-option>
                <a-select-option value="config">配置</a-select-option>
                <a-select-option value="l6">机箱</a-select-option>
                <a-select-option value="kp">配件</a-select-option>
                <a-select-option value="system">系统</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="分组">
              <a-input v-model:value="editField.group_name" placeholder="如: 基本信息" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="数据源">
              <a-input v-model:value="editField.source" placeholder="如: Opportunity / L6Record / Custom" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="对应列名">
              <a-input v-model:value="editField.source_column" placeholder="数据库列名（可选）" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="显示类型">
              <a-select v-model:value="editField.display_type" placeholder="选择类型">
                <a-select-option value="text">文本</a-select-option>
                <a-select-option value="number">数字</a-select-option>
                <a-select-option value="money">金额</a-select-option>
                <a-select-option value="percent">百分比</a-select-option>
                <a-select-option value="date">日期</a-select-option>
                <a-select-option value="enum">单选</a-select-option>
                <a-select-option value="boolean">布尔</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-textarea v-model:value="editField.description" placeholder="字段说明" :rows="2" />
        </a-form-item>

        <!-- Enum Options -->
        <a-form-item v-if="editField.display_type === 'enum'" label="选项列表">
          <a-textarea 
            v-model:value="editField.options_text" 
            placeholder="每行一个选项，如：&#10;选项A&#10;选项B&#10;选项C" 
            :rows="4"
          />
          <div class="form-hint">每行一个选项值</div>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Import Modal -->
    <a-modal
      v-model:open="importModalVisible"
      title="导入字段定义"
      @ok="handleImport"
      :confirmLoading="importLoading"
      ok-text="导入"
      cancel-text="取消"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="JSON 数据">
          <a-textarea 
            v-model:value="importData" 
            placeholder='粘贴导出的 JSON 数据'
            :rows="10"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Export Modal -->
    <a-modal
      v-model:open="exportModalVisible"
      title="导出字段定义"
      :footer="null"
      width="600px"
    >
      <div style="margin-top: 16px;">
        <a-alert message="复制以下 JSON 数据用于导入到其他环境" type="info" show-icon style="margin-bottom: 12px;" />
        <a-textarea 
          :value="exportData" 
          :rows="12"
          readonly
        />
        <a-button type="primary" style="margin-top: 12px;" @click="copyExport">
          复制到剪贴板
        </a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, ExportOutlined, ImportOutlined } from '@ant-design/icons-vue'
import axios from 'axios'

const API_BASE = '/api/admin/business-fields'

interface BusinessField {
  id: number
  key: string
  label: string
  category: string
  source: string
  source_column: string | null
  type: string
  enabled: boolean
  sort_order: number
  description: string | null
  display_type: string
  group_name: string | null
  scope: string
  permission: string
  validation_rules: string | null
  options: string | null
  dependencies: string | null
  created_at: string | null
  updated_at: string | null
  created_by: string
  updated_by: string
  export_visible: boolean
  used_in?: string[]
}

const fields = ref<BusinessField[]>([])
const activeFilter = ref<string | null>(null)
const searchText = ref('')
const expandedObjects = ref<Record<string, boolean>>({
  opportunity: true,
  item: false,
  config: false,
  l6: false,
  kp: false,
  system: false,
})

const addModalVisible = ref(false)
const addLoading = ref(false)
const isEditing = ref(false)

const importModalVisible = ref(false)
const importLoading = ref(false)
const importData = ref('')

const exportModalVisible = ref(false)
const exportData = ref('')

const editField = ref({
  key: '',
  label: '',
  category: '',
  group_name: '',
  description: '',
  source: '',
  source_column: '',
  display_type: 'text',
  options_text: '',
})

const columns = [
  { title: '导出可见', key: 'export_visible', width: 90 },
  { title: '字段名称', key: 'label', width: 140 },
  { title: '类型', key: 'display_type', width: 100 },
  { title: '来源', key: 'source_info', width: 140 },
  { title: '操作', key: 'action', width: 120, fixed: 'right' as const },
]

// Object tree structure
const dynamicSourceNames: Record<string, string> = {
  config_summary: '配置汇总',
  l6_details: 'L6配置项',
  kp_details: 'KP配置项',
}

const objectTree = computed(() => {
  const objects = [
    { key: 'opportunity', label: '商机', count: 0, groups: [] as any[] },
    { key: 'item', label: '配置项', count: 0, groups: [] as any[] },
    { key: 'system', label: '系统', count: 0, groups: [] as any[] },
    { key: 'dynamic', label: '动态字段', count: 0, groups: [] as any[] },
  ]

  const groupMap: Record<string, Record<string, number>> = {}

  fields.value.forEach(f => {
    const obj = objects.find(o => o.key === f.category)
    if (obj) {
      obj.count++
      const groupName = f.group_name || '未分组'
      if (!groupMap[f.category]) groupMap[f.category] = {}
      groupMap[f.category][groupName] = (groupMap[f.category][groupName] || 0) + 1
    }
  })

  objects.forEach(obj => {
    if (groupMap[obj.key]) {
      obj.groups = Object.entries(groupMap[obj.key]).map(([name, count]) => ({
        name,
        label: dynamicSourceNames[name] || name,
        count,
      }))
    }
  })

  return objects
})

const filteredFields = computed(() => {
  let result = fields.value

  if (activeFilter.value) {
    const [category, group] = activeFilter.value.split(':')
    result = result.filter(f => f.category === category && (f.group_name || '未分组') === group)
  }

  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    result = result.filter(f => 
      f.key.toLowerCase().includes(search) ||
      f.label.toLowerCase().includes(search) ||
      (f.description && f.description.toLowerCase().includes(search))
    )
  }

  return result
})

const currentObjectLabel = computed(() => {
  if (!activeFilter.value) return ''
  const category = activeFilter.value.split(':')[0]
  const obj = objectTree.value.find(o => o.key === category)
  return obj?.label || ''
})

const currentGroupLabel = computed(() => {
  if (!activeFilter.value) return ''
  const group = activeFilter.value.split(':')[1]
  return group
})

const pageMap: Record<string, string> = {
  opportunity_detail: '商机线索页',
  workbench: '报价工作台',
  config_page: '配置管理页',
  export_template: '导出模板',
}

const catMap: Record<string, string> = {
  opportunity: '商机线索页',
  item: '报价工作台',
  config: '配置管理页',
  l6: '机箱模块',
  kp: '配件模块',
  system: '系统内置',
}

function getSource(f: BusinessField): string {
  try {
    const pages = JSON.parse(f.used_in_pages || '[]')
    if (pages.length > 0) {
      return pages.map((p: string) => pageMap[p] || p).join(', ')
    }
  } catch {}
  if (f.category === 'dynamic') {
    return f.group_name || '动态数据源'
  }
  return catMap[f.category] || f.category
}

function toggleObject(key: string) {
  expandedObjects.value[key] = !expandedObjects.value[key]
}

function setFilter(category: string, group: string) {
  const filterKey = `${category}:${group}`
  activeFilter.value = activeFilter.value === filterKey ? null : filterKey
}

async function loadFields() {
  try {
    const res = await axios.get(API_BASE)
    fields.value = res.data
  } catch (e) {
    message.error('加载字段列表失败')
  }
}

async function toggleExportVisible(record: BusinessField, val: boolean) {
  record.export_visible = val
  try {
    await axios.put(`${API_BASE}/${record.key}`, { export_visible: val })
    message.success(val ? '已设为可见' : '已设为隐藏')
  } catch (e) {
    record.export_visible = !val
    message.error('操作失败')
  }
}

async function saveField(record: BusinessField) {
  try {
    await axios.put(`${API_BASE}/${record.key}`, { 
      label: record.label,
      display_type: record.display_type,
    })
  } catch (e) {
    message.error('保存失败')
  }
}

async function deleteField(record: BusinessField) {
  try {
    await axios.delete(`${API_BASE}/${record.key}`)
    fields.value = fields.value.filter(f => f.key !== record.key)
    message.success('已删除')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

function resetEditField() {
  editField.value = {
    key: '',
    label: '',
    category: '',
    group_name: '',
    description: '',
    source: '',
    source_column: '',
    display_type: 'text',
    options_text: '',
  }
}

function openAddModal() {
  isEditing.value = false
  resetEditField()
  addModalVisible.value = true
}

function openEditModal(record: BusinessField) {
  isEditing.value = true
  
  let options: string[] = []
  try {
    if (record.options) {
      const parsed = JSON.parse(record.options)
      options = parsed.map((o: any) => typeof o === 'string' ? o : o.value || o.label || '')
    }
  } catch {}
  
  editField.value = {
    key: record.key,
    label: record.label,
    category: record.category,
    group_name: record.group_name || '',
    description: record.description || '',
    source: record.source,
    source_column: record.source_column || '',
    display_type: record.display_type || 'text',
    options_text: options.join('\n'),
  }
  
  addModalVisible.value = true
}

function buildOptions(): string | null {
  if (editField.value.display_type !== 'enum') return null
  const text = editField.value.options_text.trim()
  if (!text) return null
  const options = text.split('\n').map(s => s.trim()).filter(s => s)
  return options.length > 0 ? JSON.stringify(options) : null
}

async function handleSave() {
  if (!editField.value.key || !editField.value.label || !editField.value.category) {
    message.warning('请填写必填项')
    return
  }
  addLoading.value = true
  try {
    const payload: any = {
      key: editField.value.key,
      label: editField.value.label,
      category: editField.value.category,
      group_name: editField.value.group_name || null,
      description: editField.value.description || null,
      source: editField.value.source || editField.value.category,
      source_column: editField.value.source_column || null,
      display_type: editField.value.display_type,
      options: buildOptions(),
    }
    
    if (isEditing.value) {
      await axios.put(`${API_BASE}/${editField.value.key}`, payload)
      message.success('已更新')
    } else {
      payload.enabled = true
      payload.sort_order = fields.value.length + 1
      await axios.post(API_BASE, payload)
      message.success('新增成功')
    }
    addModalVisible.value = false
    loadFields()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || (isEditing.value ? '更新失败' : '新增失败'))
  } finally {
    addLoading.value = false
  }
}

function showImport() {
  importData.value = ''
  importModalVisible.value = true
}

async function handleImport() {
  if (!importData.value.trim()) {
    message.warning('请粘贴 JSON 数据')
    return
  }
  importLoading.value = true
  try {
    const data = JSON.parse(importData.value)
    const fieldsList = data.fields || data
    if (!Array.isArray(fieldsList)) {
      message.error('JSON 格式错误，需要 fields 数组')
      importLoading.value = false
      return
    }
    const res = await axios.post('/api/admin/business-fields-import', {
      fields: fieldsList,
      mode: 'skip',
    })
    message.success(`导入完成: 新增 ${res.data.created}, 更新 ${res.data.updated}, 跳过 ${res.data.skipped}`)
    importModalVisible.value = false
    loadFields()
  } catch (e: any) {
    if (e instanceof SyntaxError) {
      message.error('JSON 格式错误')
    } else {
      message.error(e?.response?.data?.detail || '导入失败')
    }
  } finally {
    importLoading.value = false
  }
}

async function showExport() {
  try {
    const res = await axios.get('/api/admin/business-fields-export')
    exportData.value = JSON.stringify(res.data, null, 2)
    exportModalVisible.value = true
  } catch (e) {
    message.error('导出失败')
  }
}

async function copyExport() {
  try {
    await navigator.clipboard.writeText(exportData.value)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

onMounted(() => {
  loadFields()
})
</script>

<style scoped>
.business-fields-page {
  padding: 24px 32px;
  position: relative;
  z-index: 1;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--cpq-text-primary, #e0e0e0);
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* Main Layout */
.main-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 200px);
}

/* Sidebar */
.sidebar {
  width: 240px;
  background: var(--cpq-overlay-w3);
  border-radius: 8px;
  border: 1px solid var(--cpq-overlay-w6);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.tree-header {
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary, #999);
  border-bottom: 1px solid var(--cpq-overlay-w6);
}

.tree-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.tree-object {
  padding: 8px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.2s;
}

.tree-object:hover {
  background: var(--cpq-overlay-w4);
}

.tree-icon {
  font-size: 10px;
  color: var(--cpq-text-secondary, #999);
  width: 12px;
}

.tree-label {
  flex: 1;
  color: var(--cpq-text-primary, #e0e0e0);
  font-size: 13px;
}

.tree-count {
  font-size: 11px;
  color: var(--cpq-text-secondary, #666);
}

.tree-groups {
  padding-left: 20px;
}

.tree-group {
  padding: 6px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--cpq-text-secondary, #999);
  transition: all 0.2s;
}

.tree-group:hover {
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-primary, #e0e0e0);
}

.tree-group.active {
  background: var(--cpq-overlay-a8);
  color: var(--cpq-accent-primary, #00F5D4);
}

/* Content */
.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.filter-info {
  font-size: 14px;
  color: var(--cpq-text-primary, #e0e0e0);
}

.search-box {
  display: flex;
  gap: 8px;
}

/* Table */
.table-wrapper {
  flex: 1;
  background: var(--cpq-overlay-w3);
  border-radius: 8px;
  border: 1px solid var(--cpq-overlay-w6);
  overflow: hidden;
  overflow-y: auto;
}

.form-hint {
  font-size: 11px;
  color: var(--cpq-text-secondary, #666);
  margin-top: 4px;
}

:deep(.ant-table) {
  background: transparent !important;
  color: var(--cpq-text-primary, #e0e0e0) !important;
}

:deep(.ant-table-thead > tr > th) {
  background: var(--cpq-overlay-w4) !important;
  color: var(--cpq-text-secondary, #999) !important;
  border-bottom: 1px solid var(--cpq-overlay-w8) !important;
  font-size: 12px;
  font-weight: 500;
}

:deep(.table-row-even) {
  background: rgba(255, 255, 255, 0.01);
}

:deep(.table-row-odd) {
  background: var(--cpq-overlay-w3);
}

:deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--cpq-overlay-w4) !important;
  color: var(--cpq-text-primary, #e0e0e0) !important;
  font-size: 13px;
}

:deep(.ant-table-tbody > tr:hover > td) {
  background: var(--cpq-overlay-a4) !important;
}

:deep(.ant-empty-description) {
  color: var(--cpq-text-secondary, #666) !important;
}
</style>
