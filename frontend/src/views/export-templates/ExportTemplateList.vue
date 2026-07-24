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
import { SettingOutlined } from '@ant-design/icons-vue'
import { univerTemplateApi } from '@/api/univerTemplate'
import { specTemplateApi } from '@/api/specTemplate'
import BusinessFieldManagement from '@/views/admin/BusinessFieldManagement.vue'

const router = useRouter()
const activeTab = ref('excel')
const showFieldDrawer = ref(false)

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
  router.push('/export-templates/excel/new')
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
  background: linear-gradient(135deg,
    var(--cpq-overlay-w6) 0%,
    var(--cpq-overlay-w3) 40%,
    var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  box-shadow:
    0 22px 64px var(--cpq-overlay-b30),
    0 0 34px var(--cpq-overlay-a4),
    inset 0 1px 0 var(--cpq-overlay-w15),
    inset 0 -18px 48px var(--cpq-overlay-b15);
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
  background: linear-gradient(135deg,
    var(--cpq-overlay-w6) 0%,
    var(--cpq-overlay-w3) 40%,
    var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  box-shadow:
    0 22px 64px var(--cpq-overlay-b30),
    0 0 34px var(--cpq-overlay-a4),
    inset 0 1px 0 var(--cpq-overlay-w15),
    inset 0 -18px 48px var(--cpq-overlay-b15);
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
