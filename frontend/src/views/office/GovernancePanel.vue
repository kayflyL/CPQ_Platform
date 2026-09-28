<template>
  <div class="gov-panel">
    <header class="gov-header">
      <div>
        <h3>日志与审批</h3>
        <p>同事行为事件流 + 敏感事件审批。</p>
      </div>
      <div class="gov-header-actions" v-if="panelTab === 'governance'">
        <a-button v-if="statusFilter === 'pending' && pendingItems.length" size="small" :loading="batchActing" type="primary" @click="batchApprove">
          批量批准 ({{ selectedIds.length }})
        </a-button>
        <a-button v-if="statusFilter === 'pending' && pendingItems.length" size="small" danger :loading="batchActing" @click="batchReject">
          批量拒绝
        </a-button>
        <a-button size="small" @click="loadItems">刷新</a-button>
      </div>
    </header>

    <a-tabs v-model:activeKey="panelTab" class="gov-tabs">
      <a-tab-pane key="governance" tab="治理审批">
    <div class="gov-toolbar">
      <a-radio-group v-model:value="statusFilter" size="small" class="gov-filter">
        <a-radio-button value="pending">待审批</a-radio-button>
        <a-radio-button value="approved">已批准</a-radio-button>
        <a-radio-button value="rejected">已拒绝</a-radio-button>
        <a-radio-button value="">全部</a-radio-button>
      </a-radio-group>

      <div v-if="statusFilter === 'pending' && pendingItems.length" class="gov-select-all">
        <a-checkbox :checked="allSelected" @change="toggleSelectAll">
          全选待审批
        </a-checkbox>
        <span>{{ selectedIds.length }} / {{ pendingItems.length }} 已选</span>
      </div>
    </div>

    <div v-if="!items.length && !loading" class="gov-empty">暂无审批项</div>
    <div v-for="item in items" :key="item.id" class="gov-item" :class="{ selected: isSelected(item.id) }">
      <div class="gov-item-main">
        <a-checkbox v-if="item.status === 'pending'" :checked="isSelected(item.id)" class="gov-item-check" @change="toggleSelection(item.id)" />
        <div class="gov-item-body">
          <div class="gov-item-head">
            <span class="gov-role">{{ item.payload?.role_key || '未知角色' }}</span>
            <a-tag :color="statusColor(item.status)">{{ statusLabel(item.status) }}</a-tag>
            <span class="gov-time">{{ formatTime(item.created_ts) }}</span>
          </div>
          <div class="gov-line">意图：{{ item.payload?.intent || '—' }} · 区域：{{ item.payload?.zone || '—' }}</div>
          <div class="gov-line">活动：{{ item.payload?.activity || '—' }}</div>
          <div v-if="item.payload?.message" class="gov-line">说明：{{ item.payload.message }}</div>
          <div v-if="item.status === 'pending'" class="gov-actions">
            <a-button size="small" type="primary" :loading="actingId === item.id" @click="approve(item.id)">批准</a-button>
            <a-button size="small" danger :loading="actingId === item.id" @click="reject(item.id)">拒绝</a-button>
          </div>
        </div>
      </div>
    </div>
      </a-tab-pane>
      <a-tab-pane key="log" tab="行为日志">
        <OfficeEventLogPanel :colleagues="colleagues" />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { officeApi } from '@/api/office'
import OfficeEventLogPanel from './OfficeEventLogPanel.vue'

defineProps<{ colleagues?: Array<{ role_key?: string; name?: string; color?: string }> }>()
const panelTab = ref('governance')

const items = ref<any[]>([])
const loading = ref(false)
const actingId = ref<string | null>(null)
const batchActing = ref(false)
const statusFilter = ref('pending')
const selectedIds = ref<string[]>([])

const pendingItems = computed(() => items.value.filter((item) => item.status === 'pending'))
const allSelected = computed(() => pendingItems.value.length > 0 && pendingItems.value.every((item) => isSelected(item.id)))

function statusLabel(status: string): string {
  if (status === 'pending') return '待审批'
  if (status === 'approved') return '已批准'
  if (status === 'rejected') return '已拒绝'
  return status
}

function statusColor(status: string): string {
  if (status === 'pending') return 'warning'
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'error'
  return 'default'
}

function formatTime(ts?: number): string {
  if (!ts) return '--:--:--'
  return new Date(ts).toLocaleString('zh-CN', { hour12: false })
}

function isSelected(itemId: string): boolean {
  return selectedIds.value.includes(itemId)
}

function toggleSelection(itemId: string) {
  selectedIds.value = isSelected(itemId)
    ? selectedIds.value.filter((id) => id !== itemId)
    : [...selectedIds.value, itemId]
}

function toggleSelectAll() {
  selectedIds.value = allSelected.value
    ? []
    : pendingItems.value.map((item) => item.id)
}

async function loadItems() {
  loading.value = true
  try {
    const data = await officeApi.governance(statusFilter.value || undefined)
    items.value = data.items || []
    selectedIds.value = []
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '审批列表加载失败')
  } finally {
    loading.value = false
  }
}

async function approve(itemId: string) {
  actingId.value = itemId
  try {
    await officeApi.approveGovernance(itemId)
    message.success('已批准')
    await loadItems()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '批准失败')
  } finally {
    actingId.value = null
  }
}

async function reject(itemId: string) {
  actingId.value = itemId
  try {
    await officeApi.rejectGovernance(itemId)
    message.success('已拒绝')
    await loadItems()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '拒绝失败')
  } finally {
    actingId.value = null
  }
}

function batchApprove() {
  if (!selectedIds.value.length) {
    message.warning('请先选择待审批项')
    return
  }
  Modal.confirm({
    title: `批量批准 ${selectedIds.value.length} 项？`,
    content: '批准后这些事件会立即广播到办公室。',
    okText: '批量批准',
    okType: 'primary',
    cancelText: '取消',
    onOk: () => runBatch('approve'),
  })
}

function batchReject() {
  if (!selectedIds.value.length) {
    message.warning('请先选择待审批项')
    return
  }
  Modal.confirm({
    title: `批量拒绝 ${selectedIds.value.length} 项？`,
    content: '拒绝后这些事件不会广播，审批状态会变为已拒绝。',
    okText: '批量拒绝',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => runBatch('reject'),
  })
}

async function runBatch(action: 'approve' | 'reject') {
  batchActing.value = true
  try {
    const result = await officeApi.batchGovernance(action, selectedIds.value)
    const done = result.processed?.length || 0
    const skipped = result.skipped?.length || 0
    const failed = result.failed?.length || 0
    message.success(`已完成 ${done} 项${skipped ? `，跳过 ${skipped} 项` : ''}${failed ? `，失败 ${failed} 项` : ''}`)
    await loadItems()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '批量操作失败')
  } finally {
    batchActing.value = false
  }
}

watch(statusFilter, loadItems)
onMounted(loadItems)
</script>

<style scoped>
.gov-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: auto;
  padding: 16px;
}

.gov-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.gov-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gov-header h3 {
  margin: 0;
  font-size: 18px;
}

.gov-header p {
  margin: 4px 0 0;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.gov-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.gov-filter {
  align-self: flex-start;
}

.gov-select-all {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.gov-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--cpq-text-muted);
  border: 1px dashed var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
}

.gov-item {
  padding: 10px;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  background: var(--cpq-bg-elevated, rgba(255,255,255,0.03));
}

.gov-item.selected {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a5, rgba(22, 119, 255, 0.05));
}

.gov-item-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.gov-item-check {
  margin-top: 2px;
}

.gov-item-body {
  flex: 1;
  min-width: 0;
}

.gov-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.gov-role {
  font-size: 13px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.gov-time {
  margin-left: auto;
  color: var(--cpq-text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.gov-line {
  color: var(--cpq-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.gov-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>
