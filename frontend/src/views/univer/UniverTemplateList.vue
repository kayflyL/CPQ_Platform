<template>
  <div class="univer-template-list">
    <div class="page-header">
      <div>
        <h2 class="page-title">导出模板</h2>
        <p class="page-sub">管理报价单导出模板，点击卡片进入编辑</p>
      </div>
      <a-space>
        <a-button @click="showFieldDrawer = true">
          <template #icon><SettingOutlined /></template>
          字段管理
        </a-button>
        <a-button @click="handleCreateBlank">
          <template #icon><PlusOutlined /></template>
          从空白创建
        </a-button>
        <a-button type="primary" @click="showUploadModal = true">
          <template #icon><UploadOutlined /></template>
          上传新模板
        </a-button>
      </a-space>
    </div>

    <a-spin :spinning="loading">
      <div class="template-grid" v-if="templates.length">
        <div v-for="t in templates" :key="t.id" class="template-card glass-light" @click="handleEdit(t)">
          <div class="card-header">
            <span class="card-title">{{ t.display_name }}</span>
            <span v-if="t.is_default" class="cpq-led cpq-led--active">默认</span>
          </div>
          <div class="card-meta">
            <span class="meta-item">
              <ClockCircleOutlined />
              {{ formatDate(t.created_at) }}
            </span>
          </div>
          <div class="card-actions" @click.stop>
            <a-button type="link" size="small" @click="handleEdit(t)">编辑</a-button>
            <a-button
              v-if="!t.is_default"
              type="link"
              size="small"
              @click="handleSetDefault(t)"
            >设为默认</a-button>
            <a-popconfirm
              title="确定删除此模板？"
              @confirm="handleDelete(t.id)"
            >
              <a-button type="link" size="small" danger>删除</a-button>
            </a-popconfirm>
          </div>
        </div>
      </div>
      <div v-else-if="!loading" class="empty-state">
        <p>暂无模板</p>
        <a-button type="primary" @click="showUploadModal = true">
          <template #icon><UploadOutlined /></template>
          上传第一个模板
        </a-button>
      </div>
    </a-spin>

    <!-- 上传弹窗 -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传 Excel 模板"
      @ok="handleUpload"
      :confirmLoading="uploading"
    >
      <a-form layout="vertical">
        <a-form-item label="模板名称">
          <a-input v-model:value="newTemplateDisplayName" placeholder="如：标准报价单" />
        </a-form-item>
        <a-form-item label="选择 Excel 文件">
          <a-upload
            :beforeUpload="handleBeforeUpload"
            :fileList="fileList"
            :maxCount="1"
          >
            <a-button>
              <template #icon><UploadOutlined /></template>
              选择文件
            </a-button>
          </a-upload>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 字段管理抽屉 -->
    <a-drawer
      v-model:open="showFieldDrawer"
      title="字段管理"
      placement="right"
      width="72%"
      :closable="true"
      :destroyOnClose="false"
    >
      <BusinessFieldManagement />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { UploadOutlined, PlusOutlined, SettingOutlined, ClockCircleOutlined } from '@ant-design/icons-vue'
import { univerTemplateApi } from '@/api/univerTemplate'
import type { UniverTemplate } from '@/types/univerTemplate'
import BusinessFieldManagement from '@/views/admin/BusinessFieldManagement.vue'

const router = useRouter()

const templates = ref<UniverTemplate[]>([])
const loading = ref(false)
const showUploadModal = ref(false)
const showFieldDrawer = ref(false)
const uploading = ref(false)
const newTemplateDisplayName = ref('')
const fileList = ref<any[]>([])
let selectedFile: File | null = null

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function loadTemplates() {
  loading.value = true
  try {
    templates.value = await univerTemplateApi.list()
  } catch (err: any) {
    message.error(`加载失败: ${err.message}`)
  } finally {
    loading.value = false
  }
}

function handleEdit(record: UniverTemplate) {
  router.push(`/univer-templates/${record.id}/edit`)
}

async function handleSetDefault(record: UniverTemplate) {
  try {
    await univerTemplateApi.setDefault(record.id)
    message.success('已设为默认')
    await loadTemplates()
  } catch (err: any) {
    message.error(`操作失败: ${err.message}`)
  }
}

async function handleDelete(id: number) {
  try {
    await univerTemplateApi.delete(id)
    message.success('删除成功')
    await loadTemplates()
  } catch (err: any) {
    message.error(`删除失败: ${err.message}`)
  }
}

function handleBeforeUpload(file: File) {
  selectedFile = file
  fileList.value = [file]
  return false
}

async function handleUpload() {
  if (!selectedFile) {
    message.warning('请选择文件')
    return
  }
  if (!newTemplateDisplayName.value.trim()) {
    message.warning('请输入模板名称')
    return
  }

  uploading.value = true
  try {
    const result = await univerTemplateApi.uploadExcel(selectedFile)
    await univerTemplateApi.create({
      name: newTemplateDisplayName.value,
      display_name: newTemplateDisplayName.value,
      workbook_snapshot: result.workbook_snapshot,
      sheet_config: result.sheet_config,
    })
    message.success('上传成功')
    showUploadModal.value = false
    selectedFile = null
    fileList.value = []
    newTemplateDisplayName.value = ''
    await loadTemplates()
  } catch (err: any) {
    message.error(`上传失败: ${err.message}`)
  } finally {
    uploading.value = false
  }
}

async function handleCreateBlank() {
  const displayName = '新模板'
  try {
    const result = await univerTemplateApi.create({
      name: displayName,
      display_name: displayName,
      workbook_snapshot: {
        sheetOrder: ['sheet-1'],
        sheets: {
          'sheet-1': {
            id: 'sheet-1',
            name: 'Sheet1',
            cellData: {
              '0': {
                '0': { v: '在此开始编辑' }
              }
            },
            rowCount: 100,
            columnCount: 26,
          }
        }
      },
      sheet_config: {
        'sheet-1': { role: 'cover' }
      },
    })
    message.success('创建成功')
    router.push(`/univer-templates/${result.id}/edit`)
  } catch (err: any) {
    message.error(`创建失败: ${err.message}`)
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.univer-template-list {
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 4px;
  color: var(--cpq-text-primary, #E8ECEF);
}

.page-sub {
  color: var(--cpq-text-secondary, #9BA1AA);
  font-size: 14px;
  margin: 0;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.template-card {
  position: relative;
  padding: 24px;
  cursor: pointer;
  transition: transform var(--cpq-dur-2) var(--cpq-ease-smooth), border-color var(--cpq-dur-1) var(--cpq-ease-smooth), box-shadow var(--cpq-dur-1) var(--cpq-ease-smooth);
  overflow: hidden;
}

.template-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--cpq-accent-primary, #1677FF);
  opacity: 0;
  transition: opacity 0.3s;
}

.template-card:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-3px);
  box-shadow: var(--cpq-shadow-lg), inset 0 1px 0 var(--cpq-glass-highlight);
}

.template-card:hover::before {
  opacity: 1;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.card-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--cpq-text-primary, #E8ECEF);
}

.default-tag {
  flex-shrink: 0;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.meta-item {
  font-size: 13px;
  color: var(--cpq-text-muted, #6E7582);
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-actions {
  padding-top: 14px;
  border-top: 1px solid var(--cpq-overlay-w8);
  display: flex;
  gap: 4px;
}

.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--cpq-text-muted, #6E7582);
}

.empty-state p {
  font-size: 15px;
  margin-bottom: 16px;
}
</style>
