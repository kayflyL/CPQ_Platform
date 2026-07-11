<template>
  <div class="business-fields-page">
    <!-- Page Header -->
    <div class="page-header">
      <h2>📋 字段管理</h2>
      <div class="header-actions">
        <a-button v-if="selectedFields.length > 0" size="small" @click="batchToggle(true)">
          批量启用
        </a-button>
        <a-button v-if="selectedFields.length > 0" size="small" @click="batchToggle(false)">
          批量禁用
        </a-button>
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
            :row-selection="{ selectedRowKeys: selectedFields, onChange: onSelectChange }"
            :scroll="{ x: 1200 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'enabled'">
                <a-switch
                  :checked="record.enabled"
                  checked-children="启用"
                  un-checked-children="禁用"
                  size="small"
                  @change="(val: boolean) => toggleEnabled(record, val)"
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
              <template v-if="column.key === 'description'">
                <a-tooltip :title="record.description">
                  <span class="description-text">{{ record.description || '-' }}</span>
                </a-tooltip>
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
              <template v-if="column.key === 'permission'">
                <a-select
                  :value="record.permission || 'editable'"
                  @change="(val: string) => { record.permission = val; saveField(record) }"
                  size="small"
                  style="width: 90px;"
                >
                  <a-select-option value="editable">可编辑</a-select-option>
                  <a-select-option value="readonly">只读</a-select-option>
                  <a-select-option value="hidden">隐藏</a-select-option>
                </a-select>
              </template>
              <template v-if="column.key === 'usage_count'">
                <span :class="{ 'low-usage': getUsageCount(record.key) === 0 }">
                  {{ getUsageCount(record.key) }}
                </span>
              </template>
              <template v-if="column.key === 'action'">
                <a-space>
                  <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
                  <a-button type="link" size="small" @click="showHistory(record)">历史</a-button>
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
              <a-select v-model:value="editField.category" placeholder="选择分类" :disabled="isEditing">
                <a-select-option value="opportunity">商机</a-select-option>
                <a-select-option value="item">配置</a-select-option>
                <a-select-option value="l6">L6 价格库</a-select-option>
                <a-select-option value="kp">KP 价格库</a-select-option>
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
          <a-col :span="12">
            <a-form-item label="权限">
              <a-select v-model:value="editField.permission" placeholder="选择权限">
                <a-select-option value="editable">可编辑</a-select-option>
                <a-select-option value="readonly">只读</a-select-option>
                <a-select-option value="hidden">隐藏</a-select-option>
              </a-select>
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
        <a-form-item label="描述">
          <a-textarea v-model:value="editField.description" placeholder="字段说明" :rows="2" />
        </a-form-item>

        <!-- Enum Options (shown when display_type is enum) -->
        <a-form-item v-if="editField.display_type === 'enum'" label="选项列表">
          <a-textarea 
            v-model:value="editField.options_text" 
            placeholder="每行一个选项，如：&#10;选项A&#10;选项B&#10;选项C" 
            :rows="4"
          />
          <div class="form-hint">每行一个选项值</div>
        </a-form-item>

        <!-- Validation Rules -->
        <a-form-item label="校验规则">
          <a-space direction="vertical" style="width: 100%;">
            <a-checkbox v-model:checked="editField.validation_required">必填</a-checkbox>
            <a-row :gutter="8">
              <a-col :span="12">
                <a-input-number 
                  v-model:value="editField.validation_min" 
                  placeholder="最小值" 
                  style="width: 100%;" 
                  size="small"
                />
              </a-col>
              <a-col :span="12">
                <a-input-number 
                  v-model:value="editField.validation_max" 
                  placeholder="最大值" 
                  style="width: 100%;" 
                  size="small"
                />
              </a-col>
            </a-row>
            <a-row :gutter="8">
              <a-col :span="12">
                <a-input-number 
                  v-model:value="editField.validation_minLength" 
                  placeholder="最小长度" 
                  style="width: 100%;" 
                  size="small"
                />
              </a-col>
              <a-col :span="12">
                <a-input-number 
                  v-model:value="editField.validation_maxLength" 
                  placeholder="最大长度" 
                  style="width: 100%;" 
                  size="small"
                />
              </a-col>
            </a-row>
            <a-input 
              v-model:value="editField.validation_pattern" 
              placeholder="正则表达式（如: ^\d+$）"
              size="small"
            />
          </a-space>
        </a-form-item>

        <!-- Dependencies -->
        <a-form-item label="依赖条件（可选）">
          <a-row :gutter="8">
            <a-col :span="8">
              <a-input 
                v-model:value="editField.dep_field" 
                placeholder="依赖字段 key"
                size="small"
              />
            </a-col>
            <a-col :span="8">
              <a-select v-model:value="editField.dep_operator" placeholder="条件" size="small" style="width: 100%;">
                <a-select-option value="eq">等于</a-select-option>
                <a-select-option value="neq">不等于</a-select-option>
                <a-select-option value="contains">包含</a-select-option>
              </a-select>
            </a-col>
            <a-col :span="8">
              <a-input 
                v-model:value="editField.dep_value" 
                placeholder="条件值"
                size="small"
              />
            </a-col>
          </a-row>
          <div class="form-hint">当依赖字段满足条件时，该字段才显示</div>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- History Modal -->
    <a-modal
      v-model:open="historyModalVisible"
      :title="`变更历史 - ${historyFieldKey}`"
      :footer="null"
      width="600px"
    >
      <a-timeline style="margin-top: 16px; max-height: 400px; overflow-y: auto;">
        <a-timeline-item 
          v-for="log in historyLogs" 
          :key="log.id"
          :color="log.action === 'create' ? 'green' : log.action === 'delete' ? 'red' : 'blue'"
        >
          <div class="history-item">
            <div class="history-header">
              <a-tag :color="log.action === 'create' ? 'green' : log.action === 'delete' ? 'red' : 'blue'">
                {{ log.action === 'create' ? '创建' : log.action === 'delete' ? '删除' : '更新' }}
              </a-tag>
              <span class="history-operator">{{ log.operator }}</span>
              <span class="history-time">{{ formatTime(log.operated_at) }}</span>
            </div>
            <div v-if="log.changes" class="history-changes">
              <div v-for="(change, field) in parseChanges(log.changes)" :key="field" class="change-item">
                <span class="change-field">{{ field }}:</span>
                <span class="change-old">{{ change.old || '(空)' }}</span>
                <span class="change-arrow">→</span>
                <span class="change-new">{{ change.new || '(空)' }}</span>
              </div>
            </div>
          </div>
        </a-timeline-item>
      </a-timeline>
      <a-empty v-if="historyLogs.length === 0" description="暂无变更记录" />
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
        <a-form-item label="导入模式">
          <a-radio-group v-model:value="importMode">
            <a-radio value="skip">跳过已存在</a-radio>
            <a-radio value="overwrite">覆盖已存在</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="JSON 数据">
          <a-textarea 
            v-model:value="importData" 
            placeholder='粘贴导出的 JSON 数据，格式如：&#10;{"fields": [...]}'
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
}

const fields = ref<BusinessField[]>([])
const usageStats = ref<Record<string, { usage_count: number; last_used_at: string | null }>>({})
const activeFilter = ref<string | null>(null)
const searchText = ref('')
const selectedFields = ref<string[]>([])
const expandedObjects = ref<Record<string, boolean>>({
  opportunity: true,
  item: false,
  l6: false,
  kp: false,
  system: false,
})

const addModalVisible = ref(false)
const addLoading = ref(false)
const isEditing = ref(false)

const historyModalVisible = ref(false)
const historyFieldKey = ref('')
const historyLogs = ref<any[]>([])

const importModalVisible = ref(false)
const importLoading = ref(false)
const importMode = ref('skip')
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
  permission: 'editable',
  options_text: '',
  validation_required: false,
  validation_min: null as number | null,
  validation_max: null as number | null,
  validation_minLength: null as number | null,
  validation_maxLength: null as number | null,
  validation_pattern: '',
  dep_field: '',
  dep_operator: 'eq',
  dep_value: '',
})

const columns = [
  { title: '启用', key: 'enabled', width: 80 },
  { title: '字段名称', key: 'label', width: 140 },
  { title: '描述', key: 'description', width: 180, ellipsis: true },
  { title: '类型', key: 'display_type', width: 100 },
  { title: '权限', key: 'permission', width: 90 },
  { title: '使用次数', key: 'usage_count', width: 90 },
  { title: '操作', key: 'action', width: 160, fixed: 'right' as const },
]

// Object tree structure
const objectTree = computed(() => {
  const objects = [
    { key: 'opportunity', label: '商机', count: 0, groups: [] as any[] },
    { key: 'item', label: '配置', count: 0, groups: [] as any[] },
    { key: 'l6', label: 'L6 价格库', count: 0, groups: [] as any[] },
    { key: 'kp', label: 'KP 价格库', count: 0, groups: [] as any[] },
    { key: 'system', label: '系统', count: 0, groups: [] as any[] },
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
        label: name,
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

function getUsageCount(key: string): number {
  return usageStats.value[key]?.usage_count || 0
}

function toggleObject(key: string) {
  expandedObjects.value[key] = !expandedObjects.value[key]
}

function setFilter(category: string, group: string) {
  const filterKey = `${category}:${group}`
  activeFilter.value = activeFilter.value === filterKey ? null : filterKey
}

function onSelectChange(keys: string[]) {
  selectedFields.value = keys
}

async function loadFields() {
  try {
    const res = await axios.get(API_BASE)
    fields.value = res.data
  } catch (e) {
    message.error('加载字段列表失败')
  }
}

async function loadUsageStats() {
  try {
    const res = await axios.get('/api/admin/business-fields-usage-stats')
    usageStats.value = res.data.stats || {}
  } catch (e) {
    // Stats may not exist yet, ignore
  }
}

async function toggleEnabled(record: BusinessField, val: boolean) {
  record.enabled = val
  try {
    await axios.put(`${API_BASE}/${record.key}`, { enabled: val })
    message.success(val ? '已启用' : '已禁用')
  } catch (e) {
    record.enabled = !val
    message.error('操作失败')
  }
}

async function saveField(record: BusinessField) {
  try {
    await axios.put(`${API_BASE}/${record.key}`, { 
      label: record.label,
      description: record.description,
      display_type: record.display_type,
      permission: record.permission,
    })
    message.success('已保存')
  } catch (e) {
    message.error('保存失败')
  }
}

async function deleteField(record: BusinessField) {
  try {
    const res = await axios.delete(`${API_BASE}/${record.key}`)
    if (res.data.has_references) {
      // Show reference warning
      const refList = res.data.references.map((r: any) => `${r.ref_type}#${r.ref_id} (${r.ref_name || ''})`).join(', ')
      message.warning(`该字段被引用: ${refList}。如需强制删除请联系管理员。`)
      return
    }
    fields.value = fields.value.filter(f => f.key !== record.key)
    message.success('已删除')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

async function batchToggle(enabled: boolean) {
  try {
    await Promise.all(
      selectedFields.value.map(key => 
        axios.put(`${API_BASE}/${key}`, { enabled })
      )
    )
    message.success(`已批量${enabled ? '启用' : '禁用'} ${selectedFields.value.length} 个字段`)
    selectedFields.value = []
    loadFields()
  } catch (e) {
    message.error('批量操作失败')
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
    permission: 'editable',
    options_text: '',
    validation_required: false,
    validation_min: null,
    validation_max: null,
    validation_minLength: null,
    validation_maxLength: null,
    validation_pattern: '',
    dep_field: '',
    dep_operator: 'eq',
    dep_value: '',
  }
}

function openAddModal() {
  isEditing.value = false
  resetEditField()
  addModalVisible.value = true
}

function openEditModal(record: BusinessField) {
  isEditing.value = true
  
  // Parse existing JSON fields
  let validationRules: any = {}
  try {
    if (record.validation_rules) validationRules = JSON.parse(record.validation_rules)
  } catch {}
  
  let options: string[] = []
  try {
    if (record.options) {
      const parsed = JSON.parse(record.options)
      options = parsed.map((o: any) => typeof o === 'string' ? o : o.value || o.label || '')
    }
  } catch {}
  
  let deps: any = {}
  try {
    if (record.dependencies) deps = JSON.parse(record.dependencies)
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
    permission: record.permission || 'editable',
    options_text: options.join('\n'),
    validation_required: validationRules.required || false,
    validation_min: validationRules.min ?? null,
    validation_max: validationRules.max ?? null,
    validation_minLength: validationRules.minLength ?? null,
    validation_maxLength: validationRules.maxLength ?? null,
    validation_pattern: validationRules.pattern || '',
    dep_field: deps.field || '',
    dep_operator: deps.operator || 'eq',
    dep_value: deps.value || '',
  }
  
  addModalVisible.value = true
}

function buildValidationRules(): string | null {
  const rules: any = {}
  if (editField.value.validation_required) rules.required = true
  if (editField.value.validation_min !== null) rules.min = editField.value.validation_min
  if (editField.value.validation_max !== null) rules.max = editField.value.validation_max
  if (editField.value.validation_minLength !== null) rules.minLength = editField.value.validation_minLength
  if (editField.value.validation_maxLength !== null) rules.maxLength = editField.value.validation_maxLength
  if (editField.value.validation_pattern) rules.pattern = editField.value.validation_pattern
  
  return Object.keys(rules).length > 0 ? JSON.stringify(rules) : null
}

function buildOptions(): string | null {
  if (editField.value.display_type !== 'enum') return null
  const text = editField.value.options_text.trim()
  if (!text) return null
  const options = text.split('\n').map(s => s.trim()).filter(s => s)
  return options.length > 0 ? JSON.stringify(options) : null
}

function buildDependencies(): string | null {
  if (!editField.value.dep_field) return null
  return JSON.stringify({
    field: editField.value.dep_field,
    operator: editField.value.dep_operator,
    value: editField.value.dep_value,
  })
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
      permission: editField.value.permission,
      validation_rules: buildValidationRules(),
      options: buildOptions(),
      dependencies: buildDependencies(),
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

async function showHistory(record: BusinessField) {
  historyFieldKey.value = record.key
  historyModalVisible.value = true
  try {
    const res = await axios.get(`${API_BASE}/${record.key}/history`)
    historyLogs.value = res.data.history || []
  } catch (e) {
    message.error('加载历史记录失败')
    historyLogs.value = []
  }
}

function parseChanges(changesStr: string): Record<string, { old: string; new: string }> {
  try {
    return JSON.parse(changesStr)
  } catch {
    return {}
  }
}

function formatTime(isoStr: string): string {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN')
  } catch {
    return isoStr
  }
}

function showImport() {
  importData.value = ''
  importMode.value = 'skip'
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
    const fields = data.fields || data
    if (!Array.isArray(fields)) {
      message.error('JSON 格式错误，需要 fields 数组')
      importLoading.value = false
      return
    }
    const res = await axios.post('/api/admin/business-fields-import', {
      fields,
      mode: importMode.value,
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
  loadUsageStats()
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

.description-text {
  color: var(--cpq-text-secondary, #999);
  font-size: 12px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}

.low-usage {
  color: var(--cpq-text-secondary, #666);
  font-style: italic;
}

/* History */
.history-item {
  margin-bottom: 4px;
}

.history-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.history-operator {
  font-size: 12px;
  color: var(--cpq-text-secondary, #999);
}

.history-time {
  font-size: 11px;
  color: var(--cpq-text-secondary, #666);
  margin-left: auto;
}

.history-changes {
  background: var(--cpq-overlay-w4);
  border-radius: 4px;
  padding: 8px;
  margin-top: 4px;
}

.change-item {
  font-size: 12px;
  margin-bottom: 2px;
}

.change-field {
  color: var(--cpq-text-secondary, #999);
  margin-right: 4px;
}

.change-old {
  color: #ff6b6b;
  text-decoration: line-through;
}

.change-arrow {
  color: var(--cpq-text-secondary, #666);
  margin: 0 4px;
}

.change-new {
  color: #51cf66;
}

/* Form hints */
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
