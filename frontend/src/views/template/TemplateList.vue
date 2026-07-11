<template>
  <div class="template-list-page">
    <div class="page-header">
      <h2>导出模板管理</h2>
      <a-button type="primary" @click="handleCreate">
        <template #icon><PlusOutlined /></template>
        新建模板
      </a-button>
    </div>

    <Transition name="fade-in">
      <div class="template-grid" v-if="templates.length > 0">
      <div
        v-for="t in sortedTemplates"
        :key="t.id"
        class="template-card"
      >
        <div class="card-header">
          <div class="card-title">
            <FileExcelOutlined />
            <span>{{ t.display_name }}</span>
            <StarFilled v-if="t.is_default" class="default-star" />
          </div>
          <div class="card-actions">
            <a-button size="small" @click="handleEdit(t)">
              <template #icon><EditOutlined /></template>
            </a-button>
            <a-button size="small" danger @click="handleDelete(t)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
            <a-button
              v-if="!t.is_default"
              size="small"
              @click="handleSetDefault(t)"
            >
              <template #icon><StarOutlined /></template>
            </a-button>
          </div>
        </div>

        <div class="card-info">
          <div class="info-row">
            <span class="info-label">封面：</span>
            <span class="info-value" :class="{ empty: !t.template_json?.cover?.fileName }">
              {{ t.template_json?.cover?.fileName || '未上传' }}
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">配置页：</span>
            <span class="info-value" :class="{ empty: !t.template_json?.config_sheet?.fileName }">
              {{ t.template_json?.config_sheet?.fileName || '未上传' }}
            </span>
          </div>
        </div>

        <div class="card-footer">
          <span class="update-time">更新于 {{ formatTime(t.updated_at) }}</span>
        </div>
      </div>
    </div>
    </Transition>



    <div v-if="templates.length === 0 && !loading" class="empty-state">
      <a-empty description="暂无导出模板，点击「新建模板」开始创建" />
    </div>

    <a-modal
      v-model:open="createModalVisible"
      title="新建模板"
      @ok="handleCreateConfirm"
      :confirm-loading="createLoading"
    >
      <a-form layout="vertical">
        <a-form-item label="模板名称" required>
          <a-input
            v-model:value="newTemplateName"
            placeholder="请输入模板名称"
            @press-enter="handleCreateConfirm"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  StarOutlined,
  StarFilled,
  FileExcelOutlined
} from '@ant-design/icons-vue'
import { exportTemplateApi } from '@/api'
import type { ExportTemplate } from '@/types/template'

const router = useRouter()
const templates = ref<ExportTemplate[]>([])
const loading = ref(false)

const createModalVisible = ref(false)
const newTemplateName = ref('')
const createLoading = ref(false)

const sortedTemplates = computed(() => {
  return [...templates.value].sort((a, b) => {
    if (a.is_default && !b.is_default) return -1
    if (!a.is_default && b.is_default) return 1
    return b.id - a.id
  })
})

async function loadTemplates() {
  loading.value = true
  try {
    const data = await exportTemplateApi.list()
    templates.value = data
  } catch (e) {
    message.error('加载模板列表失败')
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  newTemplateName.value = ''
  createModalVisible.value = true
}

async function handleCreateConfirm() {
  if (!newTemplateName.value.trim()) {
    message.warning('请输入模板名称')
    return
  }

  createLoading.value = true
  try {
    const created = await exportTemplateApi.create(newTemplateName.value.trim())
    message.success('模板创建成功')
    createModalVisible.value = false
    router.push(`/export-templates/${created.id}/edit`)
  } catch (e) {
    message.error('创建失败')
  } finally {
    createLoading.value = false
  }
}

function handleEdit(t: ExportTemplate) {
  router.push(`/export-templates/${t.id}/edit`)
}

function handleDelete(t: ExportTemplate) {
  Modal.confirm({
    title: `确认删除模板「${t.display_name}」？`,
    content: '删除后不可恢复。',
    okType: 'danger',
    async onOk() {
      try {
        await exportTemplateApi.delete(t.id)
        message.success('已删除')
        await loadTemplates()
      } catch (e) {
        message.error('删除失败')
      }
    }
  })
}

async function handleSetDefault(t: ExportTemplate) {
  try {
    await exportTemplateApi.setDefault(t.id)
    message.success('已设为默认')
    await loadTemplates()
  } catch (e) {
    message.error('设置失败')
  }
}

function formatTime(s: string) {
  if (!s) return '-'
  return s.replace('T', ' ').substring(0, 16)
}

onMounted(loadTemplates)
</script>

<style scoped>
.template-list-page {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  color: var(--cpq-text-light);
  font-size: 20px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.template-card {
  background: var(--bg-card, var(--cpq-bg-card));
  border: 1px solid var(--border-color, var(--cpq-border-dark));
  border-radius: 8px;
  padding: 20px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.template-card:hover {
  border-color: var(--cpq-color-info);
  box-shadow: 0 2px 8px var(--cpq-overlay-info20);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-light);
}

.default-star {
  color: var(--cpq-color-warning);
  font-size: 14px;
}

.card-actions {
  display: flex;
  gap: 4px;
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--cpq-text-tertiary);
}

.info-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.info-label {
  color: var(--cpq-text-quaternary);
  min-width: 60px;
}

.info-value {
  color: var(--cpq-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-value.empty {
  color: var(--cpq-text-quinary);
  font-style: italic;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--border-color, var(--cpq-border-dark));
}

.update-time {
  font-size: 12px;
  color: var(--cpq-text-quaternary);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}

.fade-in-enter-active,
.fade-in-leave-active {
  transition: opacity 0.2s ease;
}

.fade-in-enter-from,
.fade-in-leave-to {
  opacity: 0;
}
</style>