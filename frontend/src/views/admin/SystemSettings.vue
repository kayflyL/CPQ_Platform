<template>
  <div class="system-settings">
    <div class="page-header">
      <h2>系统设置</h2>
      <p class="page-desc">全局配置，影响系统整体行为</p>
    </div>

    <a-tabs v-model:activeKey="activeTab" class="settings-tabs">
      <a-tab-pane key="business" tab="业务参数">
        <div class="settings-card">
          <div class="settings-card-title">业务参数</div>
          <p class="settings-card-desc">系统级业务参数，影响报价计算和导出</p>
          <a-table
            :columns="configColumns"
            :data-source="configItems"
            :pagination="false"
            row-key="key"
            size="small"
            :loading="loadingConfig"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'value'">
                <a-input
                  v-if="editingKey === record.key"
                  v-model:value="editValue"
                  size="small"
                  style="width: 200px"
                />
                <span v-else>{{ record.value }}</span>
              </template>
              <template v-if="column.key === 'action'">
                <a-space>
                  <a-button
                    v-if="editingKey === record.key"
                    type="link"
                    size="small"
                    @click="handleSaveConfig(record)"
                  >
                    保存
                  </a-button>
                  <a-button
                    v-if="editingKey === record.key"
                    type="link"
                    size="small"
                    @click="handleCancelEditConfig"
                  >
                    取消
                  </a-button>
                  <a-button
                    v-if="editingKey !== record.key"
                    type="link"
                    size="small"
                    @click="handleEditConfig(record)"
                  >
                    编辑
                  </a-button>
                </a-space>
              </template>
            </template>
          </a-table>
        </div>
      </a-tab-pane>

      <a-tab-pane key="precision" tab="数字精度">
        <div class="settings-card">
          <div class="settings-card-title">数字精度</div>
          <p class="settings-card-desc">设置报价单中数字的显示精度，影响 Excel 导出和前端显示</p>
          <div class="setting-row">
            <span class="setting-label">小数位数：</span>
            <a-select
              v-model:value="numberPrecision"
              style="width: 120px"
              :loading="saving"
              @change="handlePrecisionChange"
            >
              <a-select-option :value="0">0 位</a-select-option>
              <a-select-option :value="2">2 位</a-select-option>
              <a-select-option :value="4">4 位</a-select-option>
            </a-select>
            <span class="setting-hint">当前：{{ numberPrecision }} 位小数</span>
          </div>
        </div>
      </a-tab-pane>

      <a-tab-pane key="kpMapping" tab="KP 分类映射">
        <div class="settings-card">
          <div class="settings-card-title">KP 分类映射</div>
          <p class="settings-card-desc">配置 KP 配件关键词到标准分类的映射规则，用于自动归类 KP 配件</p>
          
          <div class="kp-mapping-add">
            <a-input
              v-model:value="newKeyword"
              placeholder="关键词（如 CPU、Memory）"
              style="width: 200px"
            />
            <a-select
              v-model:value="newCategory"
              placeholder="选择分类"
              style="width: 150px"
            >
              <a-select-option value="CPU">CPU</a-select-option>
              <a-select-option value="Memory">Memory</a-select-option>
              <a-select-option value="Storage">Storage</a-select-option>
              <a-select-option value="Network">Network</a-select-option>
              <a-select-option value="PSU">PSU</a-select-option>
              <a-select-option value="Chassis">Chassis</a-select-option>
              <a-select-option value="Motherboard">Motherboard</a-select-option>
              <a-select-option value="Other">Other</a-select-option>
            </a-select>
            <a-button type="primary" @click="handleAddMapping" :loading="adding">
              添加映射
            </a-button>
          </div>

          <a-table
            :columns="mappingColumns"
            :data-source="mappings"
            :pagination="false"
            row-key="id"
            size="small"
            :loading="loadingMappings"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'keyword'">
                <a-input
                  v-if="editingId === record.id"
                  v-model:value="record.keyword"
                  size="small"
                />
                <span v-else>{{ record.keyword }}</span>
              </template>
              <template v-if="column.key === 'category'">
                <a-select
                  v-if="editingId === record.id"
                  v-model:value="record.category"
                  size="small"
                  style="width: 120px"
                >
                  <a-select-option value="CPU">CPU</a-select-option>
                  <a-select-option value="Memory">Memory</a-select-option>
                  <a-select-option value="Storage">Storage</a-select-option>
                  <a-select-option value="Network">Network</a-select-option>
                  <a-select-option value="PSU">PSU</a-select-option>
                  <a-select-option value="Chassis">Chassis</a-select-option>
                  <a-select-option value="Motherboard">Motherboard</a-select-option>
                  <a-select-option value="Other">Other</a-select-option>
                </a-select>
                <span v-else>{{ record.category }}</span>
              </template>
              <template v-if="column.key === 'action'">
                <a-space>
                  <a-button
                    v-if="editingId === record.id"
                    type="link"
                    size="small"
                    @click="handleSaveEdit(record)"
                  >
                    保存
                  </a-button>
                  <a-button
                    v-if="editingId === record.id"
                    type="link"
                    size="small"
                    @click="handleCancelEdit"
                  >
                    取消
                  </a-button>
                  <a-button
                    v-if="editingId !== record.id"
                    type="link"
                    size="small"
                    @click="handleEdit(record)"
                  >
                    编辑
                  </a-button>
                  <a-popconfirm
                    title="确定删除此映射？"
                    @confirm="handleDelete(record.id)"
                  >
                    <a-button type="link" size="small" danger>
                      删除
                    </a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const activeTab = ref('business')
const numberPrecision = ref(2)
const saving = ref(false)

// 业务参数（system_config）
const configItems = ref<any[]>([])
const loadingConfig = ref(false)
const editingKey = ref<string | null>(null)
const editValue = ref('')

const configColumns = [
  { title: '参数名', dataIndex: 'key', key: 'key', width: 150 },
  { title: '描述', dataIndex: 'description', key: 'description', width: 200 },
  { title: '值', dataIndex: 'value', key: 'value', width: 350 },
  { title: '操作', key: 'action', width: 100 }
]

const loadConfig = async () => {
  loadingConfig.value = true
  try {
    const res = await axios.get('/api/system-config/')
    configItems.value = res.data || []
  } catch {
    message.error('加载业务参数失败')
  } finally {
    loadingConfig.value = false
  }
}

const handleEditConfig = (record: any) => {
  editingKey.value = record.key
  editValue.value = String(record.value)
}

const handleCancelEditConfig = () => {
  editingKey.value = null
  editValue.value = ''
}

const handleSaveConfig = async (record: any) => {
  try {
    let val: any = editValue.value
    // 尝试转为数字
    if (record.type === 'number') {
      val = parseFloat(editValue.value)
      if (isNaN(val)) {
        message.error('请输入有效数字')
        return
      }
    }
    await axios.put(`/api/system-config/${record.key}`, { value: val })
    message.success('已保存')
    editingKey.value = null
    editValue.value = ''
    await loadConfig()
  } catch {
    message.error('保存失败')
  }
}

// KP 分类映射
const mappings = ref<any[]>([])
const loadingMappings = ref(false)
const adding = ref(false)
const newKeyword = ref('')
const newCategory = ref('')
const editingId = ref<number | null>(null)

const mappingColumns = [
  { title: '关键词', dataIndex: 'keyword', key: 'keyword', width: 200 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 150 },
  { title: '操作', key: 'action', width: 180 }
]

const loadPrecision = async () => {
  try {
    const res = await axios.get('/api/rules/number-precision')
    numberPrecision.value = res.data.precision
  } catch {
    message.error('加载精度设置失败')
  }
}

const handlePrecisionChange = async (value: number) => {
  saving.value = true
  try {
    await axios.put('/api/rules/number-precision', { precision: value })
    message.success('精度设置已保存')
  } catch {
    message.error('保存失败')
    await loadPrecision()
  } finally {
    saving.value = false
  }
}

const loadMappings = async () => {
  loadingMappings.value = true
  try {
    const res = await axios.get('/api/rules/kp-category-mappings')
    mappings.value = res.data.mappings || []
  } catch {
    message.error('加载 KP 分类映射失败')
  } finally {
    loadingMappings.value = false
  }
}

const handleAddMapping = async () => {
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

const handleEdit = (record: any) => {
  editingId.value = record.id
}

const handleCancelEdit = () => {
  editingId.value = null
  loadMappings()
}

const handleSaveEdit = async (record: any) => {
  try {
    await axios.put(`/api/rules/kp-category-mappings/${record.id}`, {
      keyword: record.keyword,
      category: record.category
    })
    message.success('已保存')
    editingId.value = null
  } catch {
    message.error('保存失败')
  }
}

const handleDelete = async (id: number) => {
  try {
    await axios.delete(`/api/rules/kp-category-mappings/${id}`)
    message.success('已删除')
    await loadMappings()
  } catch {
    message.error('删除失败')
  }
}

onMounted(() => {
  loadConfig()
  loadPrecision()
  loadMappings()
})
</script>

<style scoped>
.system-settings {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin: 0 0 8px 0;
}

.page-desc {
  font-size: 13px;
  color: var(--cpq-text-secondary);
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-content) {
  padding-top: 16px;
}

.settings-card {
  background: var(--cpq-bg-secondary);
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 8px;
  padding: 20px;
}

.settings-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 8px;
}

.settings-card-desc {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  margin: 0 0 16px 0;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.setting-label {
  font-size: 13px;
  color: var(--cpq-text-primary);
}

.setting-hint {
  font-size: 12px;
  color: var(--cpq-text-secondary);
}

.kp-mapping-add {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
</style>
