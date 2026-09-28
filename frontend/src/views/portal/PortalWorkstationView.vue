<template>
  <div class="workstation">
    <div class="hero">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p>{{ pageDesc }}</p>
      </div>
      <button v-if="view === 'business'" class="primary-btn" @click="createOpen = true">+ 新建商机</button>
    </div>

    <div class="stats" v-if="view !== 'dispatch'">
      <div class="stat" v-for="s in stats" :key="s.label">
        <small>{{ s.label }}</small>
        <b>{{ s.value }}</b>
        <span v-if="s.hint" class="hint">{{ s.hint }}</span>
      </div>
    </div>

    <!-- 我的商机（业务本人视角；复用商机线索表公共组件） -->
    <div v-if="view === 'business'" class="card">
      <div class="card-head"><h3>商机线索列表</h3><small>点击进入商机详情 / 审批流</small><div class="card-tools"><input v-model="search" class="tool-input" placeholder="搜索客户 / 业务 / 商机号" @input="onSearch" /><a-select v-model:value="sortBy" class="tool-select" style="width:130px" @change="onSortChange"><a-select-option value="updated_at">更新时间</a-select-option><a-select-option value="created_at">创建时间</a-select-option></a-select></div></div>
      <div class="card-body table-body">
        <OpportunityTable
          :rows="cards"
          :loading="cardsLoading"
          :pagination="pagination"
          :status-editable="statusEditable"
          show-flow-node
          row-menu
          selectable
          from-tag="portal-business"
          :scroll-x="1024"
          @change="onTableChange"
          @result-change="changeResult"
          @row-menu="onRowMenu"
          @batch-trashed="onBatchTrashed"
        />
      </div>
    </div>
    <!-- 技术 / 成本 / 报价任务队列：node 过滤的商机卡片，同一张表 -->
    <div v-else-if="isTaskView" class="card">
      <div class="card-head"><h3>{{ taskTableTitle }}</h3><small>当前节点：{{ nodeLabel(node || '') }} · 点击客户名进入商机详情</small><div class="card-tools"><input v-model="search" class="tool-input" placeholder="搜索客户 / 业务 / 商机号" @input="onSearch" /></div></div>
      <div class="card-body table-body">
        <OpportunityTable
          :rows="cards"
          :loading="cardsLoading"
          :pagination="pagination"
          :status-editable="statusEditable"
          show-flow-node
          :sortable="false"
          row-menu
          menu-mode="task"
          :from-tag="fromTag"
          :scroll-x="964"
          @change="onTableChange"
          @result-change="changeResult"
          @row-menu="onRowMenu"
        />
      </div>
    </div>

    <!-- 任务调度页：统计条+人员×节点看板+转交记录，无主清单收在弹窗；面板自管数据 -->
    <PortalDispatchPanel v-else-if="view === 'dispatch'" />
    <CreateOpportunityModal v-model:open="createOpen" from="portal-business" />

    <a-modal
      v-model:open="renameOpen"
      title="重命名商机"
      ok-text="保存"
      cancel-text="取消"
      :confirm-loading="renaming"
      :mask-style="{ background: 'rgba(2, 6, 23, 0.62)', 'backdrop-filter': 'blur(2px)' }"
      :body-style="{ background: 'var(--cpq-bg-secondary)' }"
      wrap-class-name="portal-modal"
      @ok="confirmRename"
    >
      <a-input v-model:value="renameValue" placeholder="客户名称" @press-enter="confirmRename" />
    </a-modal>

    <a-modal
      v-model:open="transferOpen"
      title="转交任务"
      ok-text="确认转交"
      cancel-text="取消"
      :confirm-loading="transferSaving"
      :mask-style="{ background: 'rgba(2, 6, 23, 0.62)', 'backdrop-filter': 'blur(2px)' }"
      :body-style="{ background: 'var(--cpq-bg-secondary)' }"
      wrap-class-name="portal-modal"
      @ok="confirmTransfer"
    >
      <a-form layout="vertical">
        <a-form-item label="客户 / 节点"><span class="modal-tip">{{ transferItem?.customer_name || '—' }} · {{ nodeLabel(node || '') }}</span></a-form-item>
        <a-form-item label="转交给" required>
          <a-select v-model:value="transferAssignee" :options="transferCandidateOptions" :loading="transferCandidatesLoading" placeholder="请选择处理人" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import axios from 'axios'
import { portalApi, type PortalOppCard } from '@/api/portal'
import OpportunityTable from '@/components/opportunity/OpportunityTable.vue'
import CreateOpportunityModal from '@/components/opportunity/CreateOpportunityModal.vue'
import PortalDispatchPanel from './PortalDispatchPanel.vue'
import { resultLabel } from '@/constants/opportunityResult'
import { useAuthStore } from '@/store/auth'

type ViewKey = 'business' | 'te' | 'cost' | 'quote' | 'dispatch'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const view = computed<ViewKey>(() => (route.params.view as ViewKey) || 'business')
const node = computed(() => ({ business: '', te: 'boming', cost: 'costing', quote: 'quoting', dispatch: '' }[view.value] || ''))
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.can('page.opportunities_all'))
const isTaskView = computed(() => view.value === 'te' || view.value === 'cost' || view.value === 'quote')
const canResult = computed(() => auth.can('action.opportunity.result'))
// 商机状态列：业务/报价员（且持有权限键）可改，技术/成本只读
const statusEditable = computed(() => (view.value === 'business' || view.value === 'quote') && canResult.value)
const fromTag = computed(() => (({ business: 'portal-business', te: 'portal-te', cost: 'portal-cost', quote: 'portal-quote' } as Record<ViewKey, string>)[view.value]) || '')

const pageMeta: Record<ViewKey, { title: string; desc: string; short: string }> = {
  business: { title: '我的商机', desc: '只看自己创建/归属自己的商机，提交需求后进入统一审批流。', short: '业务' },
  te: { title: '技术支持工作台', desc: '汇总多个业务提交到我名下的 BOM 配置需求。', short: '需求' },
  cost: { title: '成本核算工作台', desc: '汇总已提交 BOM、待我核价的成本任务。', short: '成本' },
  quote: { title: '报价专员工作台', desc: '汇总已核价、待转正式报价或需退回的成本表。', short: '报价' },
  dispatch: { title: '任务调度页', desc: '调度台：无主任务弹窗灭火、人员×节点看板、默认承接规则与转交记录。', short: '调度' },
}
const pageTitle = computed(() => pageMeta[view.value].title)
const pageDesc = computed(() => pageMeta[view.value].desc)
const taskTableTitle = computed(() => (({ te: '需求任务队列', cost: '成本任务队列', quote: '报价任务队列' } as Record<string, string>)[view.value]) || '任务队列')

const nodeLabelMap: Record<string, string> = { requirement: '需求单', assign: '指派', boming: '方案配置', costing: '成本核算', quoting: '报价单', done: '已定稿' }
function nodeLabel(key: string) { return nodeLabelMap[key] || key || '—' }

// ── 商机列表（business 直查本人 / te·cost·quote 按节点+范围，同一张商机线索表） ──
const cards = ref<PortalOppCard[]>([])
const cardsLoading = ref(false)
const oppSummary = ref<any>({})
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const userPickedPageSize = ref(false)
const search = ref('')
const sortBy = ref<'updated_at' | 'created_at'>('updated_at')
const sortOrder = ref<'asc' | 'desc'>('desc')
let searchTimer: number | undefined
const pagination = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['5', '10', '15', '20', '30', '50'],
}))

async function loadCards() {
  cardsLoading.value = true
  try {
    // search 两模式同口径（客户/业务/商机ID）；business 走 SQL，node 模式后端内存过滤
    const params: Record<string, any> = { page: page.value, page_size: pageSize.value, search: search.value.trim() || undefined }
    if (view.value === 'business') {
      params.sort_by = sortBy.value
      params.sort_order = sortOrder.value
    } else {
      params.node = node.value
      params.scope = isAdmin.value ? 'all' : 'mine'
    }
    const res = await portalApi.oppCards(params)
    cards.value = res.cards || []
    oppSummary.value = res.summary || {}
    total.value = res.total || 0
  } catch (e: any) {
    message.error('加载商机失败：' + (e?.message || e))
  } finally {
    cardsLoading.value = false
  }
}

function onTableChange(pag: any, _filters: any, sorter: any) {
  page.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== pageSize.value) {
    pageSize.value = pag.pageSize
    userPickedPageSize.value = true
  }
  // 节点任务模式后端按流程更新时间倒序，忽略排序参数（排序箭头已关）
  if (view.value === 'business' && sorter?.order) {
    sortBy.value = sorter.field === 'created_at' ? 'created_at' : 'updated_at'
    sortOrder.value = sorter.order === 'ascend' ? 'asc' : 'desc'
  }
  loadCards()
}
function onSearch() {
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    page.value = 1
    loadCards()
  }, 300)
}
function onSortChange() {
  page.value = 1
  loadCards()
}
// 批量回收站在组件内完成，这里刷新列表（整页删空时回退一页）
function onBatchTrashed(keys: string[]) {
  if (keys.length >= cards.value.length && page.value > 1) page.value -= 1
  loadCards()
}
const createOpen = ref(false)

const stats = computed(() => {
  if (view.value === 'business') {
    const s = oppSummary.value || {}
    return [
      { label: '全部商机', value: s.total ?? 0, hint: '' },
      { label: '待我处理', value: s.returned ?? 0, hint: '需求待修改' },
      { label: '流转中', value: s.in_progress ?? 0, hint: 'BOM / 核价 / 报价' },
      { label: '已定稿', value: s.done ?? 0, hint: '正式报价可见' },
    ]
  }
  if (isTaskView.value) {
    const s = oppSummary.value || {}
    const firstLabel = view.value === 'te' ? '待配 BOM' : view.value === 'cost' ? '待核价' : '待报价'
    return [
      { label: firstLabel, value: s.mine ?? 0, hint: isAdmin.value ? '分派给我' : '' },
      { label: '今日处理中', value: s.today ?? 0, hint: '' },
      { label: '队列总数', value: s.total ?? 0, hint: '' },
      { label: '任务范围', value: isAdmin.value ? '全部' : '仅我的', hint: '管理员可看全部' },
    ]
  }
  return []
})

// 行内改商机状态（业务/报价员）：乐观更新 → 存库，失败回滚
async function changeResult(record: any, val: string) {
  if (val === record.result) return
  const prev = record.result
  record.result = val
  try {
    await axios.put(`/api/opportunities/${record.opportunity_id}/meta`, { result: val })
    message.success(`状态已改为「${resultLabel(val)}」`)
  } catch {
    record.result = prev
    message.error('状态更新失败')
  }
}

// 行菜单（我的商机）：打开 / 重命名 / 移至回收站
function goDetail(id: string) {
  router.push({ path: `/opportunities/${id}`, query: { from: fromTag.value || 'portal-business' } })
}
function onRowMenu(key: string, record: any) {
  if (key === 'open') goDetail(record.opportunity_id)
  else if (key === 'rename') openRename(record)
  else if (key === 'trash') trashOne(record)
  else if (key === 'transfer') openTransfer(record)
}
function trashOne(record: any) {
  Modal.confirm({
    title: '移至回收站',
    content: `将「${record.customer_name || '未命名客户'}」移至回收站？可在回收站恢复。`,
    okText: '移至回收站', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      await axios.post(`/api/opportunities/${record.opportunity_id}/trash`)
      message.success('已移至回收站')
      if (cards.value.length <= 1 && page.value > 1) page.value -= 1
      loadCards()
    },
  })
}
const renameOpen = ref(false)
const renameValue = ref('')
const renameTarget = ref<any>(null)
const renaming = ref(false)
function openRename(record: any) {
  renameTarget.value = record
  renameValue.value = record.customer_name || ''
  renameOpen.value = true
}
async function confirmRename() {
  const name = renameValue.value.trim()
  if (!name) { message.warning('请输入客户名称'); return }
  if (!renameTarget.value) return
  renaming.value = true
  try {
    await axios.put(`/api/opportunities/${renameTarget.value.opportunity_id}/meta`, { customer_name: name })
    const idx = cards.value.findIndex(c => c.opportunity_id === renameTarget.value.opportunity_id)
    if (idx >= 0) cards.value[idx] = { ...cards.value[idx], customer_name: name }
    message.success('已重命名')
    renameOpen.value = false
  } catch {
    message.error('重命名失败')
  } finally { renaming.value = false }
}

// ── 转交（任务视图行菜单） ──
const transferOpen = ref(false)
const transferItem = ref<PortalOppCard | null>(null)
const transferAssignee = ref('')
const transferCandidates = ref<string[]>([])
const transferCandidatesLoading = ref(false)
const transferSaving = ref(false)
const transferCandidateOptions = computed(() => transferCandidates.value.map(name => ({ label: name, value: name })))
async function openTransfer(item: PortalOppCard) {
  transferItem.value = item
  transferAssignee.value = ''
  transferCandidates.value = []
  transferCandidatesLoading.value = true
  transferOpen.value = true
  try {
    const opts = await portalApi.assignOptions()
    transferCandidates.value = opts.assignees[node.value] || []
  } catch (e: any) {
    message.error('加载转交候选人失败：' + (e?.message || e))
  } finally {
    transferCandidatesLoading.value = false
  }
}
async function confirmTransfer() {
  if (!transferItem.value || !transferAssignee.value) {
    message.warning('请选择要转交的处理人')
    return
  }
  transferSaving.value = true
  try {
    await portalApi.transfer(transferItem.value.opportunity_id, {
      node_key: node.value,
      assignee_name: transferAssignee.value,
    })
    message.success('已转交')
    transferOpen.value = false
    await load()
  } catch (e: any) {
    message.error('转交失败：' + (e?.message || e))
  } finally {
    transferSaving.value = false
  }
}

// ── 调度页：已迁出为 PortalDispatchPanel（自管数据加载） ──

const roleByView: Record<ViewKey, string> = {
  business: 'business',
  te: 'te',
  cost: 'cost',
  quote: 'quote',
  dispatch: 'admin',
}

async function load() {
  // dispatch 视图由 PortalDispatchPanel 自行加载
  if (view.value === 'business' || isTaskView.value) return loadCards()
}

function guardView() {
  if (!isAdmin.value && roleByView[view.value] && auth.user?.role !== roleByView[view.value]) {
    router.replace('/forbidden')
    return false
  }
  return true
}

// 分页 pageSize 自适应窗口高度；用户手动改过 pageSize 后停止自动调整。
const ADAPTIVE_ROW_H = 58
const ADAPTIVE_RESERVED_H = 200
function computeAdaptivePageSize() {
  const el = document.querySelector('.workstation') as HTMLElement | null
  const height = el?.clientHeight || window.innerHeight
  const usable = height - ADAPTIVE_RESERVED_H
  if (usable <= 0) return 5
  return Math.min(50, Math.max(5, Math.floor(usable / ADAPTIVE_ROW_H)))
}
let resizeTimer: ReturnType<typeof setTimeout> | undefined
function onResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    const next = computeAdaptivePageSize()
    if (!userPickedPageSize.value && next !== pageSize.value) {
      pageSize.value = next
      page.value = 1
      if (guardView()) load()
    }
  }, 200)
}

onMounted(() => {
  if (guardView()) {
    pageSize.value = computeAdaptivePageSize()
    load()
  }
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})
watch(view, () => {
  page.value = 1
  search.value = ''
  if (guardView()) load()
})
</script>
<style scoped>
.workstation {
  min-height: calc(100% - var(--cpq-header-clearance, 0px));
  padding: 22px;
  color: var(--cpq-text-primary);
  background:
    radial-gradient(circle at 12% 8%, var(--cpq-overlay-a15), transparent 32%),
    radial-gradient(circle at 88% 12%, var(--cpq-overlay-a15), transparent 30%),
    var(--cpq-bg-primary);
  font-family: "Segoe UI", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
}
.hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
.hero h1 { margin: 0 0 6px; font-size: 26px; letter-spacing: -.5px; }
.hero p { margin: 0; color: var(--cpq-text-secondary); font-size: 14px; }
.primary-btn { border: 0; border-radius: 12px; padding: 10px 14px; cursor: pointer; font-weight: 700; font-size: 13px; color: white; background: linear-gradient(135deg, var(--cpq-accent-primary), #7c5cfc); box-shadow: 0 8px 20px var(--cpq-overlay-a20); }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat { padding: 14px; border: 1px solid var(--cpq-glass-border); border-radius: 16px; background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur, 16px)); }
.stat small { display: block; color: var(--cpq-text-secondary); font-size: 12px; margin-bottom: 7px; }
.stat b { font-size: 24px; }
.stat .hint { font-size: 12px; color: var(--cpq-text-muted); margin-left: 6px; font-weight: 500; }
.card { border: 1px solid var(--cpq-glass-border); border-radius: 18px; background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur, 18px)); box-shadow: var(--cpq-glass-card-shadow); margin-bottom: 16px; overflow: hidden; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.card-head h3 { margin: 0; font-size: 16px; }
.card-head small { color: var(--cpq-text-secondary); font-size: 12px; }
.card-tools { display: flex; align-items: center; gap: 8px; }
.tool-input {
  height: 30px; width: 220px; padding: 0 10px; font-size: 12.5px; outline: none;
  background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-overlay-w10);
  color: var(--cpq-text-primary); border-radius: 8px;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.tool-input:focus { border-color: var(--cpq-accent-primary); box-shadow: 0 0 0 2px var(--cpq-overlay-a10); }
.tool-input::placeholder { color: var(--cpq-text-muted); }
.card-body { padding: 4px 8px 8px; }
.table-body { padding: 0; }
.table-body :deep(.ant-table-wrapper) { border-radius:  0 0 18px 18px; }
.table-body :deep(.ant-pagination) { padding: 12px 16px; border-top: 1px solid var(--cpq-overlay-w8); }

.modal-tip { color: var(--cpq-text-secondary); font-size: 13px; }
@media (max-width: 900px) {
  .stats { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 768px) {
  .workstation { padding: 12px 12px 24px; }
  .hero { align-items: flex-start; gap: 10px; margin-bottom: 12px; }
  .hero h1 { font-size: 20px; margin-bottom: 2px; }
  .hero p { font-size: 12.5px; }
  .primary-btn { padding: 9px 13px; font-size: 12.5px; }
  .stats { gap: 8px; margin-bottom: 12px; }
  .stat { padding: 10px 12px; border-radius: 13px; }
  .stat b { font-size: 19px; }
  .card { border-radius: 14px; margin-bottom: 12px; }
  .card-head { flex-wrap: wrap; align-items: flex-start; padding: 11px 12px; gap: 6px 10px; }
  .card-head h3 { font-size: 14.5px; }
  .card-tools { flex-wrap: wrap; width: 100%; }
  .tool-input { flex: 1 1 150px; width: auto; }
  .card-body { padding: 2px 4px 6px; }
}
</style>
