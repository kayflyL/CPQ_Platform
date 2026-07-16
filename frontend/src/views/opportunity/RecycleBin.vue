<template>
  <div class="recycle-bin-container">
    <div class="header-actions">
      <div class="header-left">
        <h2>🗑️ 回收站</h2>
        <span v-if="selectedIds.size > 0" class="select-hint">已选 {{ selectedIds.size }} 项</span>
      </div>
      <a-space>
        <a-button @click="router.push('/opportunities')">返回商机列表</a-button>
        <a-button v-if="selectedIds.size > 0" size="small" @click="handleBatchRestore">恢复选中</a-button>
        <a-button v-if="selectedIds.size > 0" size="small" danger @click="handleBatchPermanentDelete">永久删除选中</a-button>
        <a-button v-if="selectedIds.size > 0" size="small" @click="exitSelect">取消</a-button>
        <a-button type="primary" @click="fetchData" :loading="loading">🔄 刷新</a-button>
      </a-space>
    </div>
    
    <a-alert 
      message="回收站中的商机可以恢复或永久删除"
      description="勾选商机后可批量恢复或永久删除；单个商机也可点击右侧按钮操作"
      type="info" 
      show-icon
      style="margin-bottom: 16px"
    />
    
    <!-- 批量操作栏 -->
    <div v-if="selectedIds.size > 0" class="batch-bar glass">
      <div class="batch-left">
        <a-checkbox
          :checked="selectedIds.size === projects.length && projects.length > 0"
          :indeterminate="selectedIds.size > 0 && selectedIds.size < projects.length"
          @change="toggleSelectAll"
        >
          全选
        </a-checkbox>
        <span class="batch-count">已选 {{ selectedIds.size }} / {{ projects.length }} 项</span>
      </div>
      <div class="batch-actions">
        <a-button size="small" @click="handleBatchRestore">恢复选中 ({{ selectedIds.size }})</a-button>
        <a-button danger size="small" @click="handleBatchPermanentDelete">永久删除选中 ({{ selectedIds.size }})</a-button>
        <a-button size="small" @click="exitSelect">取消</a-button>
      </div>
    </div>
    
    <a-table 
      :dataSource="projects" 
      :columns="projectColumns" 
      :loading="loading"
      rowKey="project_id"
      :row-class-name="(record: any) => selectedIds.has(record.project_id) ? 'selected-row' : ''"
      bordered
      size="small"
      :pagination="{ pageSize: 20 }"
      :row-selection="rowSelection"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'action'">
          <a-space>
            <a-button size="small" type="link" @click="handleRestoreProject(record)">
              ↩️ 恢复
            </a-button>
            <a-popconfirm
              title="确定要永久删除吗？此操作无法恢复！"
              @confirm="handlePermanentDeleteProject(record)"
              ok-text="确定"
              cancel-text="取消"
              ok-type="danger"
            >
              <a-button size="small" type="link" danger>
                🗑️ 永久删除
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>
    
    <a-empty v-if="!loading && projects.length === 0" description="回收站中没有已删除的商机" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { projectApi } from '@/api'

const router = useRouter()
const projects = ref<any[]>([])
const loading = ref(false)

// Selection
const selectedIds = ref<Set<string>>(new Set())

const rowSelection = computed(() => ({
  selectedRowKeys: [...selectedIds.value],
  onChange: (selectedRowKeys: string[]) => {
    selectedIds.value = new Set(selectedRowKeys)
  }
}))

const projectColumns = [
  { title: '商机名称', dataIndex: 'project_name', width: 180 },
  { title: '平台', dataIndex: 'platform_type', width: 80 },
  { title: '机箱', dataIndex: 'chassis_form', width: 70 },
  { title: '采购数量', dataIndex: 'purchase_qty', width: 70 },
  { title: '配置数', dataIndex: 'config_count', width: 70 },
  { title: '删除时间', dataIndex: 'updated_at', width: 160 },
  { title: '操作', dataIndex: 'action', width: 180, fixed: 'right' }
]

const toggleSelectAll = (checked: boolean) => {
  if (checked) {
    selectedIds.value = new Set(projects.value.map(p => p.project_id))
  } else {
    selectedIds.value = new Set()
  }
}

const exitSelect = () => {
  selectedIds.value = new Set()
}

const handleBatchRestore = async () => {
  if (selectedIds.value.size === 0) return
  try {
    const result = await projectApi.batchRestore([...selectedIds.value])
    const ok = result.success?.length || 0
    const fail = result.failed?.length || 0
    message.success(`已恢复 ${ok} 个商机` + (fail > 0 ? `，${fail} 个失败` : ''))
    exitSelect()
    fetchData()
  } catch (err: any) {
    message.error('批量恢复失败: ' + (err.message || err))
  }
}

const handleBatchPermanentDelete = async () => {
  if (selectedIds.value.size === 0) return
  try {
    const result = await projectApi.batchPermanentDelete([...selectedIds.value])
    const ok = result.success?.length || 0
    const fail = result.failed?.length || 0
    message.success(`已永久删除 ${ok} 个商机` + (fail > 0 ? `，${fail} 个失败` : ''))
    exitSelect()
    fetchData()
  } catch (err: any) {
    message.error('批量永久删除失败: ' + (err.message || err))
  }
}

const fetchData = async () => {
  loading.value = true
  try {
    const projResp = await projectApi.list({ include_deleted: true, page_size: 100 })
    projects.value = projResp.items.filter((item: any) => item.status === 'deleted')
  } catch (err) {
    message.error('获取回收站数据失败')
  } finally {
    loading.value = false
  }
}

const handleRestoreProject = async (record: any) => {
  try {
    await projectApi.restore(record.project_id)
    message.success('✅ 商机已恢复')
    fetchData()
  } catch (err) {
    message.error('恢复失败')
  }
}

const handlePermanentDeleteProject = async (record: any) => {
  try {
    await projectApi.delete(record.project_id)
    message.success('✅ 商机已永久删除')
    fetchData()
  } catch (err) {
    message.error('删除失败')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.recycle-bin-container { 
  padding: 20px; 
  background: var(--cpq-bg-primary);
  color: var(--cpq-text-primary);
  min-height: 100vh;
}
.header-actions { 
  display: flex; 
  justify-content: space-between; 
  margin-bottom: 16px; 
  align-items: center;
}
.header-actions h2 {
  color: var(--cpq-text-primary);
  margin: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.select-hint {
  font-size: 13px;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
  padding: 4px 10px;
  border-radius: 8px;
}

/* 批量操作栏 */
.batch-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: var(--cpq-overlay-danger10);
  border: 1px solid var(--cpq-overlay-danger15);
  border-radius: 10px;
  animation: fadeInUp 0.3s var(--cpq-ease-out-expo) backwards;
}

.batch-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-count {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

.batch-actions {
  display: flex;
  gap: 8px;
}

/* 选中行高亮 */
:deep(.selected-row) {
  background: var(--cpq-overlay-a4) !important;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
