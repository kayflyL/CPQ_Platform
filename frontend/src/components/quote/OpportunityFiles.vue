<template>
  <div class="opportunity-files">
    <div class="files-header">
      <span class="files-title">📁 商机文件</span>
      <div class="header-actions">
        <a-button type="text" size="small" @click="loadFiles" title="刷新">
          <template #icon><ReloadOutlined /></template>
        </a-button>
        <a-button type="text" size="small" @click="handleOpenFolder" title="打开文件夹">
          <template #icon><FolderOpenOutlined /></template>
        </a-button>
        <a-button type="text" size="small" @click="showUploadModal = true" title="上传文件">
          <template #icon><UploadOutlined /></template>
        </a-button>
      </div>
    </div>
    
    <div 
      class="files-list"
      :class="{ 'dragging': isDragging }"
      @dragover.prevent="handleDragOver"
      @dragleave="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <div v-if="isDragging" class="drag-overlay">
        <div class="drag-content">
          <UploadOutlined class="drag-icon" />
          <p>释放文件以上传</p>
        </div>
      </div>
      <a-spin v-if="loading" size="small" />
      <a-empty v-else-if="files.length === 0" description="暂无文件" :image-style="{ height: '40px' }" />
      <div v-else class="files-scroll">
        <div 
          v-for="file in files" 
          :key="file.name" 
          class="file-item"
        >
          <div class="file-icon">
            <FileExcelOutlined v-if="file.name?.endsWith('.xlsx') || file.name?.endsWith('.xls')" style="color: var(--cpq-accent-success)" />
            <FilePdfOutlined v-else-if="file.name?.endsWith('.pdf')" style="color: var(--cpq-accent-danger)" />
            <FileImageOutlined v-else-if="isImage(file.name)" style="color: var(--cpq-accent-primary)" />
            <FileOutlined v-else style="color: var(--cpq-text-muted)" />
          </div>
          <div class="file-info" @click="handleDownload(file)">
            <div class="file-name">{{ file.name }}</div>
            <div class="file-meta">
              <span class="file-size">{{ formatSize(file.size) }}</span>
              <span class="file-time">{{ formatTime(file.modified) }}</span>
            </div>
          </div>
          <div class="file-actions">
            <a-button type="text" size="small" @click.stop="handleOpenFile(file)" title="用系统默认程序打开">
              <template #icon><EditOutlined /></template>
            </a-button>
            <a-button type="text" size="small" @click.stop="showRenameModal(file)" title="重命名">
              <template #icon><FormOutlined /></template>
            </a-button>
            <a-button type="text" size="small" danger @click.stop="showDeleteConfirm(file)" title="删除">
              <template #icon><DeleteOutlined /></template>
            </a-button>
            <a-button type="text" size="small" @click.stop="handleDownload(file)" title="下载">
              <template #icon><DownloadOutlined /></template>
            </a-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传文件对话框 -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传文件"
      :footer="null"
      width="480px"
    >
      <a-upload-dragger
        :multiple="true"
        :before-upload="handleBeforeUpload"
        :file-list="uploadFileList"
        :remove="handleRemoveUploadFile"
      >
        <p class="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p class="ant-upload-hint">支持单个或批量上传</p>
      </a-upload-dragger>
      <a-button 
        type="primary" 
        block 
        :loading="uploading" 
        :disabled="uploadFileList.length === 0"
        @click="handleUpload"
        style="margin-top: 16px"
      >
        {{ uploading ? '上传中...' : `开始上传 (${uploadFileList.length})` }}
      </a-button>
    </a-modal>

    <!-- 重命名对话框 -->
    <a-modal
      v-model:open="showRenameDialog"
      title="重命名文件"
      @ok="handleRename"
      :confirm-loading="renaming"
      width="400px"
    >
      <a-form layout="vertical">
        <a-form-item label="原文件名">
          <span class="old-name">{{ renameTarget?.name }}</span>
        </a-form-item>
        <a-form-item label="新文件名">
          <a-input 
            v-model:value="newFileName" 
            placeholder="输入新文件名"
            @press-enter="handleRename"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 删除确认对话框 -->
    <a-modal
      v-model:open="showDeleteDialog"
      title="确认删除"
      @ok="handleDelete"
      :confirm-loading="deleting"
      ok-text="删除"
      ok-type="danger"
      width="400px"
    >
      <p>确定要删除文件 <strong>{{ deleteTarget?.name }}</strong> 吗？</p>
      <p style="color: var(--cpq-text-muted); font-size: 12px;">此操作不可撤销</p>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { 
  FileExcelOutlined, 
  FilePdfOutlined, 
  FileImageOutlined, 
  FileOutlined,
  FolderOpenOutlined,
  UploadOutlined,
  EditOutlined,
  FormOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ReloadOutlined,
  InboxOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { UploadFile } from 'ant-design-vue'
import axios from 'axios'

interface ProjectFile {
  name: string
  size: number
  modified: string
}

const props = defineProps<{
  opportunityId: string
  visible: boolean
}>()

const files = ref<ProjectFile[]>([])
const loading = ref(false)

// 拖拽上传相关
const isDragging = ref(false)

// 上传相关
const showUploadModal = ref(false)
const uploadFileList = ref<UploadFile[]>([])
const uploading = ref(false)

// 重命名相关
const showRenameDialog = ref(false)
const renameTarget = ref<ProjectFile | null>(null)
const newFileName = ref('')
const renaming = ref(false)

// 删除相关
const showDeleteDialog = ref(false)
const deleteTarget = ref<ProjectFile | null>(null)
const deleting = ref(false)

const isImage = (name: string | undefined) => {
  if (!name) return false
  const ext = name.toLowerCase().split('.').pop() || ''
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)
}

const formatSize = (bytes: number) => {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const formatTime = (isoStr: string) => {
  if (!isoStr) return ''
  const date = new Date(isoStr)
  return date.toLocaleString('zh-CN', { 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}

const loadFiles = async () => {
  if (!props.opportunityId) return
  
  loading.value = true
  try {
    const res = await axios.get(`/api/opportunities/${props.opportunityId}/files`)
    files.value = res.data.files || []
  } catch (error) {
    console.error('加载文件列表失败:', error)
    message.error('加载文件列表失败')
  } finally {
    loading.value = false
  }
}

// 下载文件
const handleDownload = async (file: ProjectFile) => {
  try {
    const response = await axios.get(
      `/api/opportunities/${props.opportunityId}/files/download?filename=${encodeURIComponent(file.name)}`,
      { responseType: 'blob' }
    )
    
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', file.name)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载失败:', error)
    message.error('下载失败')
  }
}

// 打开文件夹
const handleOpenFolder = async () => {
  try {
    const res = await axios.get(`/api/opportunities/${props.opportunityId}/folder-path`)
    const folderPath = res.data.uploads_path
    
    // 复制到剪贴板
    await navigator.clipboard.writeText(folderPath)
    message.success(`文件夹路径已复制: ${folderPath}`)
  } catch (error) {
    console.error('获取文件夹路径失败:', error)
    message.error('获取文件夹路径失败')
  }
}

// 用系统默认程序打开文件
const handleOpenFile = async (file: ProjectFile) => {
  try {
    await axios.post(
      `/api/opportunities/${props.opportunityId}/files/open?filename=${encodeURIComponent(file.name)}`
    )
    message.success(`已打开: ${file.name}`)
  } catch (error: any) {
    console.error('打开文件失败:', error)
    if (error.response?.status === 500) {
      message.error('打开文件失败，可能服务器不支持此操作')
    } else {
      message.error('打开文件失败')
    }
  }
}

// 显示重命名对话框
const showRenameModal = (file: ProjectFile) => {
  renameTarget.value = file
  newFileName.value = file.name
  showRenameDialog.value = true
}

// 执行重命名
const handleRename = async () => {
  if (!renameTarget.value || !newFileName.value) return
  
  if (newFileName.value === renameTarget.value.name) {
    showRenameDialog.value = false
    return
  }
  
  renaming.value = true
  try {
    await axios.put(
      `/api/opportunities/${props.opportunityId}/files/rename`,
      null,
      {
        params: {
          old_name: renameTarget.value.name,
          new_name: newFileName.value
        }
      }
    )
    message.success('重命名成功')
    showRenameDialog.value = false
    loadFiles()
  } catch (error: any) {
    console.error('重命名失败:', error)
    if (error.response?.data?.detail) {
      message.error(error.response.data.detail)
    } else {
      message.error('重命名失败')
    }
  } finally {
    renaming.value = false
  }
}

// 显示删除确认
const showDeleteConfirm = (file: ProjectFile) => {
  deleteTarget.value = file
  showDeleteDialog.value = true
}

// 执行删除
const handleDelete = async () => {
  if (!deleteTarget.value) return
  
  deleting.value = true
  try {
    await axios.delete(
      `/api/opportunities/${props.opportunityId}/files`,
      {
        params: {
          filename: deleteTarget.value.name
        }
      }
    )
    message.success('删除成功')
    showDeleteDialog.value = false
    loadFiles()
  } catch (error: any) {
    console.error('删除失败:', error)
    if (error.response?.data?.detail) {
      message.error(error.response.data.detail)
    } else {
      message.error('删除失败')
    }
  } finally {
    deleting.value = false
  }
}

// 拖拽上传处理
const handleDragOver = (e: DragEvent) => {
  isDragging.value = true
}

const handleDragLeave = (e: DragEvent) => {
  isDragging.value = false
}

const handleDrop = async (e: DragEvent) => {
  isDragging.value = false
  
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  
  uploading.value = true
  let successCount = 0
  let failCount = 0
  
  for (const file of Array.from(files)) {
    try {
      const formData = new FormData()
      formData.append('file', file)
      
      await axios.post(
        `/api/opportunities/${props.opportunityId}/files/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        }
      )
      successCount++
    } catch (error) {
      console.error('上传失败:', file.name, error)
      failCount++
    }
  }
  
  uploading.value = false
  
  if (successCount > 0) {
    message.success(`成功上传 ${successCount} 个文件`)
    loadFiles()
  }
  
  if (failCount > 0) {
    message.error(`${failCount} 个文件上传失败`)
  }
}

// 上传相关
const handleBeforeUpload = (file: UploadFile) => {
  uploadFileList.value.push(file)
  return false
}

const handleRemoveUploadFile = (file: UploadFile) => {
  const index = uploadFileList.value.indexOf(file)
  if (index > -1) {
    uploadFileList.value.splice(index, 1)
  }
}

const handleUpload = async () => {
  if (uploadFileList.value.length === 0) return
  
  uploading.value = true
  let successCount = 0
  let failCount = 0
  
  for (const file of uploadFileList.value) {
    try {
      const formData = new FormData()
      formData.append('file', file.originFileObj as File)
      
      await axios.post(
        `/api/opportunities/${props.opportunityId}/files/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        }
      )
      successCount++
    } catch (error) {
      console.error('上传失败:', file.name, error)
      failCount++
    }
  }
  
  uploading.value = false
  
  if (successCount > 0) {
    message.success(`成功上传 ${successCount} 个文件`)
    showUploadModal.value = false
    uploadFileList.value = []
    loadFiles()
  }
  
  if (failCount > 0) {
    message.error(`${failCount} 个文件上传失败`)
  }
}

// 监听 visible 变化，打开时加载文件
watch(() => props.visible, (val) => {
  if (val) {
    loadFiles()
  }
})

// 监听 opportunityId 变化
watch(() => props.opportunityId, () => {
  if (props.visible) {
    loadFiles()
  }
})
</script>

<style scoped>
.opportunity-files {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: transparent;
}

.files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
}

.header-actions {
  display: flex;
  gap: 4px;
}

.files-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.files-list {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 10px;
  position: relative;
  min-height: 100px;
  border: 2px solid transparent;
  border-radius: 10px;
  transition: all var(--cpq-transition-fast);
}

.files-list.dragging {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a5);
  box-shadow: inset 0 0 20px var(--cpq-overlay-a8);
}

.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cpq-overlay-a5);
  backdrop-filter: blur(8px);
  border-radius: 10px;
  z-index: 10;
  pointer-events: none;
  animation: dragPulse 1.5s ease-in-out infinite;
}

@keyframes dragPulse {
  0%, 100% { background: var(--cpq-overlay-a4); }
  50% { background: var(--cpq-overlay-a10); }
}

.drag-content {
  text-align: center;
  color: var(--cpq-accent-primary);
}

.drag-icon {
  font-size: 48px;
  margin-bottom: 12px;
  animation: dragBounce 1s ease-in-out infinite;
}

@keyframes dragBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.drag-content p {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--cpq-accent-primary);
}

.files-scroll {
  flex: 1;
  overflow-y: auto;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 6px;
  background: var(--cpq-overlay-w3);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.file-item:hover {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a4);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--cpq-overlay-a8);
}

.file-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.file-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.file-size {
  color: var(--cpq-text-secondary);
}

.file-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity var(--cpq-transition-fast);
}

.file-item:hover .file-actions {
  opacity: 1;
}

.old-name {
  color: var(--cpq-text-secondary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
