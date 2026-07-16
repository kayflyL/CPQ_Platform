<template>
  <div class="univer-template-list">
    <div class="page-header">
      <h2>导出模板</h2>
      <a-space>
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

    <a-table
      :dataSource="templates"
      :columns="columns"
      :loading="loading"
      rowKey="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'display_name'">
          <a @click="handleEdit(record)">{{ record.display_name }}</a>
          <a-tag v-if="record.is_default" color="green" style="margin-left: 8px">默认</a-tag>
        </template>
        <template v-if="column.key === 'action'">
          <a-space>
            <a-button type="link" size="small" @click="handleEdit(record)">编辑</a-button>
            <a-button
              v-if="!record.is_default"
              type="link"
              size="small"
              @click="handleSetDefault(record)"
            >设为默认</a-button>
            <a-popconfirm
              title="确定删除此模板？"
              @confirm="handleDelete(record.id)"
            >
              <a-button type="link" size="small" danger>删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

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
            accept=".xlsx,.xls"
          >
            <a-button>
              <template #icon><UploadOutlined /></template>
              选择文件
            </a-button>
          </a-upload>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { UploadOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { univerTemplateApi } from '@/api/univerTemplate'
import type { UniverTemplate } from '@/types/univerTemplate'

const router = useRouter()

const templates = ref<UniverTemplate[]>([])
const loading = ref(false)
const showUploadModal = ref(false)
const uploading = ref(false)
const newTemplateDisplayName = ref('')
const fileList = ref<any[]>([])
let selectedFile: File | null = null

const columns = [
  { title: '模板名称', key: 'display_name', dataIndex: 'display_name' },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  { title: '操作', key: 'action', width: 200 },
]

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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
</style>
