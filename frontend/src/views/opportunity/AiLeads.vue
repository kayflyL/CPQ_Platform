<template>
  <div class="ai-leads-page">
    <!-- 顶栏 -->
    <header class="page-head glass-strong">
      <div class="page-title">
        <h1>AI 线索</h1>
        <span class="page-sub">AI 办公室对话自动登记的商机 · 转正后进入商机列表</span>
      </div>
      <input v-model="search" class="search-input dark-input" placeholder="搜索需求摘要 / 所属人..." @input="debounceLoad" />
      <div class="head-icons">
        <button class="icon-btn" title="刷新" @click="loadLeads"><ReloadOutlined :spin="loading" /></button>
        <button class="ghost-btn danger" @click="goBack"><LeftOutlined /> 返回商机</button>
      </div>
    </header>

    <!-- 列表 -->
    <div class="table-card glass">
      <a-table
        :dataSource="leads"
        :columns="columns"
        :pagination="pagination"
        :loading="loading"
        size="small"
        rowKey="opportunity_id"
        :rowSelection="rowSelectionCfg"
        :scroll="{ x: 900 }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'snippet'">
            <div class="cell-lead">
              <span class="lead-text">{{ record.snippet || record.customer_name || '（无摘要）' }}</span>
              <span class="lead-owner">
                <UserOutlined /> {{ record.owner_name || record.created_by || '—' }}
                <a-tag v-if="record.stale" class="stale-tag">7天无动态</a-tag>
              </span>
            </div>
          </template>
          <template v-else-if="column.key === 'role'">
            <span class="role-chip">{{ roleName(record.colleague_role_key) }}</span>
          </template>
          <template v-else-if="column.key === 'progress'">
            <a-tag :color="progressMeta(record.progress).color">
              <component :is="progressMeta(record.progress).icon" />
              {{ progressMeta(record.progress).label }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'msg_count'">
            <span class="cell-num">{{ record.msg_count }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'last_activity'">
            <span class="cell-date">{{ formatDate(record.last_activity) }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-dropdown :trigger="['click']" placement="bottomRight">
              <button class="row-more"><MoreOutlined /></button>
              <template #overlay>
                <a-menu @click="(e: any) => onRowMenu(e.key, record)">
                  <a-menu-item key="view" :disabled="!record.thread_id">查看对话</a-menu-item>
                  <a-menu-item key="promote">转正为商机…</a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="purge" danger>清理该线索</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </template>
        <template #emptyText>
          <a-empty description="暂无 AI 线索 — 在 AI 办公室与同事对话产生的商机草稿会登记在这里" />
        </template>
      </a-table>
    </div>

    <!-- 悬浮批量条 -->
    <Transition name="batch-fade">
      <div v-if="selectedKeys.length" class="batch-float glass-strong">
        <span class="batch-count">已选 <b>{{ selectedKeys.length }}</b> 项</span>
        <button class="batch-btn danger" :disabled="purging" @click="confirmBatchPurge">清理所选线索</button>
        <button class="batch-btn" @click="selectedKeys = []">取消</button>
      </div>
    </Transition>

    <!-- 转正 modal -->
    <a-modal v-model:open="promoteOpen" title="AI 线索转正" ok-text="转正" cancel-text="取消" :confirm-loading="promoting" @ok="confirmPromote">
      <div class="promote-form">
        <div class="promote-field">
          <div class="promote-label">客户名称 <span class="req">*</span></div>
          <a-input v-model:value="promoteForm.customer_name" placeholder="例如：XX 证券" :maxlength="60" @pressEnter="confirmPromote" />
        </div>
        <div class="promote-field">
          <div class="promote-label">业务归属</div>
          <a-select
            v-if="canViewAll"
            v-model:value="promoteForm.sales_person"
            placeholder="选择业务（可空）"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="businessOptions"
          />
          <a-input v-else :value="auth.user?.name || ''" disabled />
        </div>
        <div class="promote-hint">转正后线索进入商机列表；已出方案的需求单与 BOM 会一并带过去。</div>
      </div>
    </a-modal>

    <!-- 对话抽屉（只读） -->
    <a-drawer v-model:open="drawerOpen" width="560" placement="right" :title="drawerTitle" class="lead-thread-drawer">
      <a-spin :spinning="drawerLoading">
        <div class="thread-scroll">
          <div v-if="!drawerMessages.length && !drawerLoading" class="thread-empty">该线索没有关联会话消息</div>
          <div v-for="m in drawerMessages" :key="m.message_id" class="msg-row" :class="m.role === 'user' ? 'mine' : 'ai'">
            <div class="msg-head">
              <span class="msg-author">{{ m.role === 'user' ? (drawerOwner || '用户') : roleName(m.colleague_role_key) }}</span>
              <span class="msg-time">{{ formatTime(m.created_at) }}</span>
            </div>
            <div class="msg-body">{{ m.content }}</div>
          </div>
        </div>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message as antMessage, Modal } from 'ant-design-vue'
import {
  MoreOutlined, ReloadOutlined, LeftOutlined, UserOutlined,
  MessageOutlined, FileDoneOutlined, RocketOutlined,
} from '@ant-design/icons-vue'
import axios from 'axios'
import { assistantApi } from '@/api/assistant'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const auth = useAuthStore()
const canViewAll = computed(() => auth.can('page.opportunities_all'))

// AI 同事名册：role_key → 显示名
const colleagues = ref<any[]>([])
async function loadColleagues() {
  try {
    const data = await assistantApi.aiColleagues.list()
    colleagues.value = Array.isArray(data.colleagues) ? data.colleagues : []
  } catch { colleagues.value = [] }
}
function roleName(roleKey?: string) {
  if (!roleKey) return '总助手'
  const c = colleagues.value.find((x: any) => x?.role_key === roleKey)
  return c?.name || roleKey
}

// 列表数据
const leads = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const search = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null
function debounceLoad() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadLeads() }, 300)
}
async function loadLeads() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (search.value.trim()) params.search = search.value.trim()
    const res = await axios.get('/api/opportunities/ai-leads', { params })
    leads.value = res.data.items || []
    total.value = res.data.total || 0
    selectedKeys.value = []
  } finally { loading.value = false }
}
function onTableChange(pag: any) {
  page.value = pag.current || 1
  if (pag.pageSize) pageSize.value = pag.pageSize
  loadLeads()
}
const pagination = computed(() => ({
  current: page.value, pageSize: pageSize.value, total: total.value,
  showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '30', '50'],
}))

const columns = [
  { title: '需求摘要', key: 'snippet' },
  { title: '来源角色', key: 'role', width: 130, ellipsis: true },
  { title: '进度', key: 'progress', width: 116 },
  { title: '消息', dataIndex: 'msg_count', width: 70, align: 'right' },
  { title: '最近活动', dataIndex: 'last_activity', width: 110 },
  { title: '', key: 'actions', width: 52, align: 'center' },
]
function progressMeta(p: string) {
  if (p === 'plan') return { label: '已出方案', color: 'success', icon: RocketOutlined }
  if (p === 'registered') return { label: '已登记需求', color: 'warning', icon: FileDoneOutlined }
  return { label: '对话中', color: 'processing', icon: MessageOutlined }
}
function formatDate(s: string) { return s ? s.slice(0, 10) : '-' }
function formatTime(s: string) { return s ? s.slice(5, 16).replace('T', ' ') : '' }

// 批量选择 + 清理
const selectedKeys = ref<string[]>([])
const rowSelectionCfg = computed(() => ({
  selectedRowKeys: selectedKeys.value,
  onChange: (keys: any[]) => { selectedKeys.value = keys as string[] },
}))
const purging = ref(false)
function confirmBatchPurge() {
  if (!selectedKeys.value.length) return
  Modal.confirm({
    title: `清理 ${selectedKeys.value.length} 条 AI 线索`,
    content: '将物理删除线索及其全部会话消息、需求单与 BOM 方案，不可恢复。确定清理？',
    okText: '清理', okType: 'danger', cancelText: '取消',
    onOk: () => purge(selectedKeys.value.slice()),
  })
}
function purgeOne(record: any) {
  Modal.confirm({
    title: '清理该 AI 线索',
    content: `将物理删除「${record.snippet || record.customer_name || '该线索'}」及其全部会话消息、需求单与 BOM 方案，不可恢复。`,
    okText: '清理', okType: 'danger', cancelText: '取消',
    onOk: () => purge([record.opportunity_id]),
  })
}
async function purge(ids: string[]) {
  purging.value = true
  try {
    const res = await axios.post('/api/opportunities/ai-leads/purge', { opportunity_ids: ids })
    const ok = res.data?.success?.length || 0
    const fail = res.data?.failed?.length || 0
    if (fail) antMessage.warning(`已清理 ${ok} 条，${fail} 条失败`)
    else antMessage.success(`已清理 ${ok} 条线索`)
    if (page.value > 1 && leads.value.length <= ids.length && ok >= leads.value.length) page.value -= 1
    loadLeads()
  } catch {
    antMessage.error('清理失败')
  } finally { purging.value = false }
}

// 行菜单
function onRowMenu(key: string, record: any) {
  if (key === 'view') openDrawer(record)
  else if (key === 'promote') openPromote(record)
  else if (key === 'purge') purgeOne(record)
}

// 转正
const promoteOpen = ref(false)
const promoting = ref(false)
const promoteTarget = ref<any>(null)
const promoteForm = ref({ customer_name: '', sales_person: '' })
const businessOptions = ref<{ value: string; label: string }[]>([])
function openPromote(record: any) {
  promoteTarget.value = record
  promoteForm.value = { customer_name: '', sales_person: '' }
  promoteOpen.value = true
  if (canViewAll.value && !businessOptions.value.length) {
    axios.get('/api/opportunities/business-options').then((res) => {
      businessOptions.value = (res.data.items || []).map((name: string) => ({ value: name, label: name }))
    }).catch(() => { businessOptions.value = [] })
  }
}
async function confirmPromote() {
  const name = promoteForm.value.customer_name.trim()
  if (!name) { antMessage.warning('请输入客户名称'); return }
  if (!promoteTarget.value) return
  promoting.value = true
  try {
    const res = await axios.post(`/api/opportunities/${promoteTarget.value.opportunity_id}/promote`, {
      customer_name: name,
      sales_person: canViewAll.value ? promoteForm.value.sales_person : '',
    })
    const data = res.data || {}
    if (data.has_requirement) antMessage.success('已转正，可在商机列表查看')
    else antMessage.warning(data.message || '已转正；尚未登记需求单，补交后才出现在商机列表')
    promoteOpen.value = false
    loadLeads()
  } catch (e: any) {
    antMessage.error(e?.response?.data?.detail || '转正失败')
  } finally { promoting.value = false }
}

// 对话抽屉（只读）
const drawerOpen = ref(false)
const drawerLoading = ref(false)
const drawerMessages = ref<any[]>([])
const drawerTitle = ref('线索对话')
const drawerOwner = ref('')
async function openDrawer(record: any) {
  if (!record.thread_id) { antMessage.info('该线索没有关联会话'); return }
  drawerOwner.value = record.owner_name || record.created_by || ''
  drawerTitle.value = `线索对话 · ${record.snippet?.slice(0, 24) || record.customer_name || ''}`
  drawerOpen.value = true
  drawerLoading.value = true
  drawerMessages.value = []
  try {
    const res = await axios.get(`/api/assistant/threads/${record.thread_id}/messages`, { params: { limit: 200 } })
    drawerMessages.value = res.data.messages || []
  } catch {
    antMessage.error('会话读取失败')
  } finally { drawerLoading.value = false }
}

function goBack() { router.push('/opportunities') }

onMounted(() => {
  loadColleagues()
  loadLeads()
})
</script>

<style scoped>
.ai-leads-page { display: flex; flex-direction: column; gap: 12px; padding: 16px 24px 24px; min-height: calc(100vh - 56px); }

.page-head { display: flex; align-items: center; gap: 14px; padding: 12px 18px; border-radius: var(--cpq-radius-lg); }
.page-title { display: flex; flex-direction: column; gap: 1px; flex: none; }
.page-title h1 { margin: 0; font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); letter-spacing: 1px; }
.page-sub { font-size: 11px; color: var(--cpq-text-muted); letter-spacing: 0.5px; }
.search-input { flex: 1 1 1px; min-width: 160px; max-width: 460px; height: 34px; border-radius: 8px; }
.head-icons { display: flex; align-items: center; gap: 8px; margin-left: auto; flex: none; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px;
  border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary);
  border-radius: 8px; cursor: pointer; font-size: 15px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.icon-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.ghost-btn {
  display: inline-flex; align-items: center; gap: 5px; height: 34px; padding: 0 14px;
  border: 1px solid var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-secondary);
  border-radius: 8px; cursor: pointer; font-size: 13px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.ghost-btn:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.ghost-btn.danger:hover { color: var(--cpq-accent-danger); border-color: var(--cpq-accent-danger); }

.dark-input { background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-overlay-w10); color: var(--cpq-text-primary); padding: 6px 12px; border-radius: 6px; font-size: 13px; outline: none; transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.dark-input:focus { border-color: var(--cpq-accent-primary); box-shadow: 0 0 0 2px var(--cpq-overlay-a10); }
.dark-input::placeholder { color: var(--cpq-text-muted); }

.table-card { border-radius: var(--cpq-radius-lg); overflow: hidden; }

.cell-lead { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.lead-text { font-size: 13px; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 420px; }
.lead-owner { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--cpq-text-muted); }
.stale-tag { font-size: 10px; line-height: 14px; padding: 0 4px; margin-left: 4px; color: var(--cpq-text-muted); }
.role-chip { font-size: 12px; color: var(--cpq-text-secondary); }
.cell-num { font-size: 12.5px; color: var(--cpq-text-secondary); font-variant-numeric: tabular-nums; }
.cell-date { font-size: 12px; color: var(--cpq-text-secondary); font-variant-numeric: tabular-nums; }
.row-more {
  display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
  border: none; background: transparent; color: var(--cpq-text-muted); border-radius: 6px; cursor: pointer; font-size: 14px;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.row-more:hover { background: var(--cpq-overlay-w8); color: var(--cpq-text-primary); }

/* 批量悬浮条 */
.batch-float {
  position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 1000;
  display: flex; align-items: center; gap: 12px; padding: 10px 18px; border-radius: 999px;
  box-shadow: var(--cpq-shadow-lg, 0 8px 24px rgba(0,0,0,0.18));
}
.batch-count { font-size: 13px; color: var(--cpq-text-secondary); }
.batch-count b { color: var(--cpq-accent-primary); }
.batch-btn {
  padding: 5px 14px; border: 1px solid var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-secondary);
  border-radius: 999px; cursor: pointer; font-size: 12.5px; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.batch-btn:hover { color: var(--cpq-text-primary); border-color: var(--cpq-text-secondary); }
.batch-btn.danger { color: var(--cpq-accent-danger); border-color: var(--cpq-overlay-danger30, rgba(255,107,107,0.35)); }
.batch-btn.danger:hover:not(:disabled) { border-color: var(--cpq-accent-danger); }
.batch-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.batch-fade-enter-active, .batch-fade-leave-active { transition: opacity var(--cpq-dur-2) var(--cpq-ease-smooth), transform var(--cpq-dur-2) var(--cpq-ease-smooth); }
.batch-fade-enter-from, .batch-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(12px); }

/* 转正 modal */
.promote-form { display: flex; flex-direction: column; gap: 14px; padding: 4px 2px; }
.promote-field { display: flex; flex-direction: column; gap: 6px; }
.promote-label { font-size: 12.5px; color: var(--cpq-text-secondary); font-weight: 500; }
.promote-label .req { color: var(--cpq-accent-danger); }
.promote-hint { font-size: 11.5px; color: var(--cpq-text-muted); line-height: 1.6; }

/* 对话抽屉 */
.thread-scroll { display: flex; flex-direction: column; gap: 14px; padding: 4px 2px 20px; }
.thread-empty { padding: 40px 0; text-align: center; font-size: 13px; color: var(--cpq-text-muted); }
.msg-row { display: flex; flex-direction: column; gap: 4px; max-width: 88%; }
.msg-row.mine { align-self: flex-end; align-items: flex-end; }
.msg-row.ai { align-self: flex-start; align-items: flex-start; }
.msg-head { display: flex; align-items: baseline; gap: 8px; font-size: 11px; color: var(--cpq-text-muted); }
.msg-author { font-weight: 600; color: var(--cpq-text-secondary); }
.msg-body {
  padding: 8px 12px; border-radius: 10px; font-size: 12.5px; line-height: 1.65;
  white-space: pre-wrap; word-break: break-word; color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-overlay-w8);
}
.mine .msg-body { background: var(--cpq-overlay-a12, rgba(22,119,255,0.10)); border-color: var(--cpq-overlay-a25, rgba(22,119,255,0.25)); }

/* Table dark overrides */
.ai-leads-page :deep(.ant-table-wrapper .ant-table) { background: transparent; color: var(--cpq-text-primary); }
.ai-leads-page :deep(.ant-table-thead > tr > th) { background: var(--cpq-overlay-w4) !important; color: var(--cpq-text-secondary) !important; font-size: 12px; font-weight: 500; border-bottom: 1px solid var(--cpq-overlay-w6) !important; white-space: nowrap; }
.ai-leads-page :deep(.ant-table-tbody > tr > td) { border-bottom: 1px solid var(--cpq-overlay-w4) !important; color: var(--cpq-text-primary); }
.ai-leads-page :deep(.ant-table-tbody > tr:hover > td) { background: var(--cpq-overlay-a5) !important; }
.ai-leads-page :deep(.ant-table-cell) { padding: 9px 12px; }
.ai-leads-page :deep(.ant-pagination) { padding: 12px 16px; border-top: 1px solid var(--cpq-overlay-w4); }
.ai-leads-page :deep(.ant-pagination-item), .ai-leads-page :deep(.ant-pagination-prev), .ai-leads-page :deep(.ant-pagination-next) { background: transparent !important; border-color: var(--cpq-overlay-w10) !important; }
.ai-leads-page :deep(.ant-pagination-item a), .ai-leads-page :deep(.ant-pagination-item-link) { color: var(--cpq-text-secondary) !important; background: transparent !important; border: none !important; }
.ai-leads-page :deep(.ant-pagination-item-active) { border-color: var(--cpq-accent-primary) !important; }
.ai-leads-page :deep(.ant-pagination-item-active a) { color: var(--cpq-accent-primary) !important; }

@media (max-width: 768px) {
  .ai-leads-page { padding: 10px 12px 96px; }
  .page-head { flex-wrap: wrap; gap: 10px; padding: 10px 14px; border-radius: 8px; }
  .search-input { order: 5; flex-basis: 100%; max-width: none; }
  .head-icons { margin-left: 0; }
  .lead-text { max-width: 200px; }
}
</style>
