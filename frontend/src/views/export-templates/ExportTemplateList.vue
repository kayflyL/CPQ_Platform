<template>
  <div class="export-template-list">
    <div class="page-header">
      <div>
        <h2>导出模板</h2>
        <p class="subtitle">管理所有导出模板：Excel 模板和规格书模板</p>
      </div>
      <a-button @click="showFieldDrawer = true">
        <template #icon><SettingOutlined /></template>
        字段管理
      </a-button>
    </div>

    <a-tabs v-model:activeKey="activeTab" class="template-tabs">
      <!-- Excel 模板 Tab -->
      <a-tab-pane key="excel" tab="Excel 模板">
        <div class="template-grid">
          <div v-for="tpl in excelTemplates" :key="tpl.id" class="template-card">
            <div class="card-header">
              <h3>{{ tpl.display_name }}</h3>
              <a-tag v-if="tpl.is_default" color="blue">默认</a-tag>
            </div>
            <div class="card-body">
              <div class="info-row">
                <span class="label">名称：</span>
                <span>{{ tpl.name }}</span>
              </div>
              <div class="info-row">
                <span class="label">更新时间：</span>
                <span>{{ formatDate(tpl.updated_at) }}</span>
              </div>
            </div>
            <div class="card-actions">
              <a-button type="primary" @click="handleEditExcel(tpl)">编辑</a-button>
              <a-button v-if="!tpl.is_default" @click="handleSetDefaultExcel(tpl)">设为默认</a-button>
              <a-popconfirm title="确定删除此模板？" @confirm="handleDeleteExcel(tpl)">
                <a-button danger>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <div class="template-card add-card" @click="handleCreateExcel">
            <div class="add-icon">+</div>
            <div class="add-text">新建 Excel 模板</div>
          </div>
        </div>
      </a-tab-pane>

      <!-- 规格书模板 Tab -->
      <a-tab-pane key="spec" tab="规格书模板">
        <div class="template-grid">
          <div v-for="tpl in specTemplates" :key="tpl.id" class="template-card">
            <div class="card-header">
              <h3>{{ tpl.display_name }}</h3>
              <a-tag v-if="tpl.is_default" color="blue">默认</a-tag>
            </div>
            <div class="card-body">
              <div class="info-row">
                <span class="label">名称：</span>
                <span>{{ tpl.name }}</span>
              </div>
              <div class="info-row">
                <span class="label">更新时间：</span>
                <span>{{ formatDate(tpl.updated_at) }}</span>
              </div>
            </div>
            <div class="card-actions">
              <a-button type="primary" size="small" @click="handleEditSpec(tpl)">编辑</a-button>
              <a-button size="small" @click="handleCopySpec(tpl)">复制</a-button>
              <a-button v-if="!tpl.is_default" size="small" @click="handleSetDefaultSpec(tpl)">默认</a-button>
              <a-popconfirm
                :title="`确定删除「${tpl.display_name}」？此操作不可恢复。`"
                ok-text="删除"
                cancel-text="取消"
                @confirm="handleDeleteSpec(tpl)"
              >
                <a-button type="text" danger size="small">删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <div class="template-card add-card" @click="handleCreateSpec">
            <div class="add-icon">+</div>
            <div class="add-text">新建规格书模板</div>
          </div>
        </div>
      </a-tab-pane>
    </a-tabs>

    <!-- 新建 Excel 模板弹窗（从空白创建 / 上传 Excel 创建） -->
    <a-modal
      v-model:open="showCreateExcelModal"
      title="新建 Excel 模板"
      :footer="null"
      :destroyOnClose="true"
      width="520px"
    >
      <a-form layout="vertical">
        <a-form-item label="模板名称" required>
          <a-input v-model:value="newTemplateName" placeholder="如：标准报价单" :maxlength="50" />
        </a-form-item>
        <a-form-item label="Excel 文件（可选；不选则从空白创建）">
          <a-upload
            :before-upload="handleBeforeUpload"
            :file-list="fileList"
            :max-count="1"
            accept=".xlsx,.xls"
            :on-remove="handleRemoveFile"
          >
            <a-button>
              <template #icon><UploadOutlined /></template>
              选择文件
            </a-button>
          </a-upload>
        </a-form-item>
      </a-form>
      <div class="create-excel-footer">
        <a-button @click="showCreateExcelModal = false">取消</a-button>
        <a-button :loading="creatingExcel" @click="handleCreateBlankExcel">从空白创建</a-button>
        <a-button type="primary" :loading="creatingExcel" @click="handleUploadCreateExcel">上传创建</a-button>
      </div>
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
import { SettingOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { univerTemplateApi } from '@/api/univerTemplate'
import { specTemplateApi } from '@/api/specTemplate'
import BusinessFieldManagement from '@/views/admin/BusinessFieldManagement.vue'

const router = useRouter()
const activeTab = ref('excel')
const showFieldDrawer = ref(false)

// 新建 Excel 模板弹窗状态（方案 B：空白创建 / 上传 Excel 创建）
const showCreateExcelModal = ref(false)
const creatingExcel = ref(false)
const newTemplateName = ref('')
const selectedFile = ref<File | null>(null)
const fileList = ref<any[]>([])

const excelTemplates = ref<any[]>([])
const specTemplates = ref<any[]>([])

onMounted(async () => {
  await Promise.all([loadExcelTemplates(), loadSpecTemplates()])
})

async function loadExcelTemplates() {
  try {
    excelTemplates.value = await univerTemplateApi.list()
  } catch (error) {
    message.error('加载 Excel 模板列表失败')
  }
}

async function loadSpecTemplates() {
  try {
    specTemplates.value = await specTemplateApi.list()
  } catch (error) {
    message.error('加载规格书模板列表失败')
  }
}

function formatDate(dateStr: string) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Excel 模板操作
function handleCreateExcel() {
  // 方案 B：列表页弹窗内选择「从空白创建」或「上传 Excel 创建」，创建成功后再进编辑器
  newTemplateName.value = ''
  selectedFile.value = null
  fileList.value = []
  showCreateExcelModal.value = true
}


// ── 新建 Excel 模板：从空白创建 / 上传 Excel 创建（方案 B） ──

function handleBeforeUpload(file: File) {
  selectedFile.value = file
  fileList.value = [file]
  return false
}

function handleRemoveFile() {
  selectedFile.value = null
  fileList.value = []
}

function buildBlankSnapshot(): Record<string, any> {
  return {
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
  }
}

async function handleCreateBlankExcel() {
  const displayName = newTemplateName.value.trim() || '新模板'
  creatingExcel.value = true
  try {
    const result = await univerTemplateApi.create({
      name: displayName,
      display_name: displayName,
      workbook_snapshot: buildBlankSnapshot(),
      sheet_config: { cover: { sheetId: 'sheet-1' } },
    })
    message.success('创建成功')
    showCreateExcelModal.value = false
    resetCreateExcel()
    router.push(`/export-templates/excel/${result.id}/edit`)
    await loadExcelTemplates()
  } catch (err: any) {
    message.error(`创建失败: ${err.message}`)
  } finally {
    creatingExcel.value = false
  }
}

async function handleUploadCreateExcel() {
  if (!newTemplateName.value.trim()) {
    message.warning('请输入模板名称')
    return
  }
  if (!selectedFile.value) {
    message.warning('请选择 Excel 文件')
    return
  }
  creatingExcel.value = true
  try {
    const result = await univerTemplateApi.uploadExcel(selectedFile.value)
    const created = await univerTemplateApi.create({
      name: newTemplateName.value.trim(),
      display_name: newTemplateName.value.trim(),
      workbook_snapshot: result.workbook_snapshot,
      sheet_config: result.sheet_config,
    })
    message.success('上传创建成功')
    showCreateExcelModal.value = false
    resetCreateExcel()
    router.push(`/export-templates/excel/${created.id}/edit`)
    await loadExcelTemplates()
  } catch (err: any) {
    message.error(`上传创建失败: ${err.message}`)
  } finally {
    creatingExcel.value = false
  }
}

function resetCreateExcel() {
  newTemplateName.value = ''
  selectedFile.value = null
  fileList.value = []
}

function handleEditExcel(tpl: any) {
  router.push(`/export-templates/excel/${tpl.id}/edit`)
}

async function handleSetDefaultExcel(tpl: any) {
  try {
    await univerTemplateApi.setDefault(tpl.id)
    message.success('已设为默认')
    await loadExcelTemplates()
  } catch (error) {
    message.error('设置失败')
  }
}

async function handleDeleteExcel(tpl: any) {
  try {
    await univerTemplateApi.delete(tpl.id)
    message.success('已删除')
    await loadExcelTemplates()
  } catch (error) {
    message.error('删除失败')
  }
}

// 规格书模板操作
function handleCreateSpec() {
  router.push('/export-templates/spec/new')
}

function handleEditSpec(tpl: any) {
  router.push(`/export-templates/spec/${tpl.id}/edit`)
}

async function handleSetDefaultSpec(tpl: any) {
  try {
    await specTemplateApi.setDefault(tpl.id)
    message.success('已设为默认')
    await loadSpecTemplates()
  } catch (error) {
    message.error('设置失败')
  }
}

async function handleCopySpec(tpl: any) {
  try {
    const copied = await specTemplateApi.copy(tpl.id)
    message.success('模板已复制')
    await loadSpecTemplates()
    // 询问是否编辑副本
    router.push(`/export-templates/spec/${copied.id}/edit`)
  } catch (error) {
    message.error('复制失败')
  }
}

async function handleDeleteSpec(tpl: any) {
  try {
    await specTemplateApi.delete(tpl.id)
    message.success(`「${tpl.display_name}」已删除`)
    await loadSpecTemplates()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.create-excel-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.export-template-list {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.subtitle {
  margin: 0;
  color: var(--cpq-text-secondary);
  font-size: 14px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.template-card {
  position: relative;
  padding: 24px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 18px;
  cursor: pointer;
  transition: all .3s cubic-bezier(.16,1,.3,1);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
}

.template-card:hover {
  border-color: var(--cpq-overlay-a30);
  transform: translateY(-2px);
  box-shadow:
    0 22px 64px var(--cpq-shadow-color-strong),
    0 0 34px var(--cpq-overlay-a15),
    inset 0 1px 0 var(--cpq-overlay-w15),
    inset 0 -18px 48px var(--cpq-shadow-color-soft);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.card-body {
  margin-bottom: 20px;
}

.info-row {
  display: flex;
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--cpq-text-primary);
}

.info-row .label {
  color: var(--cpq-text-secondary);
  min-width: 80px;
}

.card-actions {
  display: flex;
  gap: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--cpq-overlay-w10);
}

.add-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  cursor: pointer;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 18px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  transition: all .3s cubic-bezier(.16,1,.3,1);
}

.add-card:hover {
  border-color: var(--cpq-overlay-a30);
  transform: translateY(-2px);
  box-shadow:
    0 22px 64px var(--cpq-shadow-color-strong),
    0 0 34px var(--cpq-overlay-a15),
    inset 0 1px 0 var(--cpq-overlay-w15),
    inset 0 -18px 48px var(--cpq-shadow-color-soft);
}

.add-icon {
  font-size: 48px;
  color: var(--cpq-accent-primary);
  margin-bottom: 12px;
}

.add-text {
  font-size: 16px;
  color: var(--cpq-accent-primary);
}
</style>
