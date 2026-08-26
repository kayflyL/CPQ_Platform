<template>
  <div class="workstation">
    <div class="hero">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p>{{ pageDesc }}</p>
      </div>
      <button v-if="view === 'business'" class="primary-btn" @click="createOpen = true">+ 新建商机</button>
      <button v-else-if="isTaskView" class="ghost-btn" :disabled="!taskItems.length" @click="openTransfer()">{{ pageTransferText }}</button>
      <button v-else-if="view === 'dispatch'" class="primary-btn" @click="openRuleModal()">+ 新增分派规则</button>
    </div>

    <div class="stats">
      <div class="stat" v-for="s in stats" :key="s.label">
        <small>{{ s.label }}</small>
        <b>{{ s.value }}</b>
        <span v-if="s.hint" class="hint">{{ s.hint }}</span>
      </div>
    </div>

    <div v-if="view === 'business'" class="card">
      <div class="card-head"><h3>商机线索列表</h3><small>点击进入商机详情 / 审批流</small><div class="card-tools"><input v-model="businessSearch" class="tool-input" placeholder="搜索客户 / 业务" @input="onBusinessSearch" /><a-select v-model:value="businessSortBy" class="tool-select" style="width:130px" placeholder="排序" @change="onBusinessTableChange({ current: businessPage })"><a-select-option value="updated_at">更新时间</a-select-option><a-select-option value="created_at">创建时间</a-select-option></a-select></div></div>
      <div class="card-body table-body">
        <a-table
          :data-source="businessRows"
          :columns="businessColumns"
          :pagination="businessPagination"
          :loading="businessLoading"
          size="small"
          row-key="opportunity_id"
          @change="onBusinessTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'customer_name'">
              <b>{{ record.customer_name || '—' }}</b>
            </template>
            <template v-else-if="column.key === 'summary'">
              <span>{{ record.summary || '—' }}</span>
            </template>
            <template v-else-if="column.key === 'sales_person'">
              <span>{{ record.sales_person || '—' }}</span>
            </template>
            <template v-else-if="column.key === 'current_node'">
              <span class="pill" :class="pillClass(record)">{{ nodeLabel(record.current_node) }}</span>
            </template>
            <template v-else-if="column.key === 'updated_at'">
              <span class="muted">{{ record.updated_at || '—' }}</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <button class="link" @click="openTask(record.opportunity_id)">{{ businessAction(record) }}</button>
            </template>
          </template>
        </a-table>
      </div>
    </div>
    <div v-else-if="isTaskView" class="card">
      <div class="card-head"><h3>{{ taskTableTitle }}</h3><small>当前节点：{{ nodeLabel(node || '') }}</small></div>
      <div class="card-body table-body">
        <a-table
          :data-source="taskItems"
          :columns="taskColumns"
          :pagination="taskPagination"
          :loading="taskLoading"
          size="small"
          row-key="opportunity_id"
          @change="onTaskTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'sales_person'">
              <span>{{ record.sales_person || '—' }}</span>
            </template>
            <template v-else-if="column.key === 'customer_name'">
              <b>{{ record.customer_name || '—' }}</b>
            </template>
            <template v-else-if="column.key === 'summary'">
              <span>{{ taskCell(record) }}</span>
            </template>
            <template v-else-if="column.key === 'source_actor'">
              <span>{{ taskActor(record) }}</span>
            </template>
            <template v-else-if="column.key === 'status'">
              <span class="pill" :class="taskPill(record)">{{ taskStatus(record) }}</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <button class="link" @click="openTask(record.opportunity_id)">{{ taskAction(record) }}</button>
            </template>
          </template>
        </a-table>
      </div>
    </div>

    <template v-else-if="view === 'dispatch'">
      <div class="card">
        <div class="card-head"><h3>业务 × 节点负责人</h3><small>同一技术可负责多个业务；支持单条转交覆盖</small></div>
        <div class="card-body">
          <div class="assign-grid">
            <div class="head">业务</div><div class="head">技术支持 / BOM</div><div class="head">成本核算</div><div class="head">报价专员</div>
            <template v-for="biz in dispatchData.businesses" :key="biz.user_id">
              <div class="assign-cell"><small>业务</small><b>{{ biz.name }}</b></div>
              <div class="assign-cell" v-for="n in nodeCols" :key="biz.user_id + n">
                <small>{{ nodeShort(n) }}</small>
                <select :value="ruleAssignee(biz.user_id, n)" @change="onRuleChange(biz.user_id, n, $event)">
                  <option value="">未设置</option>
                  <option v-for="name in assigneesFor(n)" :key="name" :value="name">{{ name }}</option>
                </select>
              </div>
            </template>
            <div class="assign-cell pool"><small>业务</small><b>公共池 / 未指派</b></div>
            <div class="assign-cell pool" v-for="n in nodeCols" :key="'pool-' + n">
              <small>{{ nodeShort(n) }}</small>
              <b class="muted">{{ dispatchData.unassigned[n] || 0 }} 条待认领</b>
            </div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h3>转交记录</h3></div>
        <div class="card-body table-body">
          <a-table
            :data-source="dispatchData.transfers"
            :columns="transferColumns"
            :loading="dispatchLoading"
            size="small"
            :pagination="false"
            row-key="opportunity_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'time'"><span class="muted">{{ record.time }}</span></template>
              <template v-else-if="column.key === 'customer_name'"><span>{{ record.customer_name || record.opportunity_id }}</span></template>
              <template v-else-if="column.key === 'node_label'"><span>{{ record.node_label }}</span></template>
              <template v-else-if="column.key === 'from_assignee'"><span>{{ record.from_assignee || '未指派' }}</span></template>
              <template v-else-if="column.key === 'to_assignee'"><span>{{ record.to_assignee || '—' }}</span></template>
              <template v-else-if="column.key === 'actor'"><span>{{ record.actor || '—' }}</span></template>
            </template>
          </a-table>
        </div>
      </div>
    </template>
    <CreateOpportunityModal v-model:open="createOpen" from="portal-business" />

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

    <a-modal
      v-model:open="ruleOpen"
      title="新增 / 修改分派规则"
      ok-text="保存规则"
      cancel-text="取消"
      :confirm-loading="ruleSaving"
      :mask-style="{ background: 'rgba(2, 6, 23, 0.62)', 'backdrop-filter': 'blur(2px)' }"
      :body-style="{ background: 'var(--cpq-bg-secondary)' }"
      wrap-class-name="portal-modal"
      @ok="saveRule"
    >
      <a-form layout="vertical">
        <a-form-item label="业务"><a-select v-model:value="ruleForm.business_user_id" :options="ruleBusinessOptions" placeholder="请选择业务" /></a-form-item>
        <a-form-item label="流程节点"><a-select v-model:value="ruleForm.node_key" :options="nodeOptions" /></a-form-item>
        <a-form-item label="默认处理人"><a-select v-model:value="ruleForm.assignee_name" :options="assigneeOptions(ruleForm.node_key)" placeholder="请选择处理人" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { portalApi, type PortalDispatchData, type PortalTaskItem } from '@/api/portal'
import CreateOpportunityModal from '@/components/opportunity/CreateOpportunityModal.vue'
import { useAuthStore } from '@/store/auth'

type ViewKey = 'business' | 'te' | 'cost' | 'quote' | 'dispatch'
type TableColumn = { title: string; key: string }

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const view = computed<ViewKey>(() => (route.params.view as ViewKey) || 'business')
const node = computed(() => ({ business: '', te: 'boming', cost: 'costing', quote: 'quoting', dispatch: '' }[view.value] || ''))
const isAdmin = computed(() => auth.user?.role === 'admin' || auth.can('page.opportunities_all'))
const isTaskView = computed(() => view.value === 'te' || view.value === 'cost' || view.value === 'quote')

const pageMeta: Record<ViewKey, { title: string; desc: string; short: string; transfer: string }> = {
  business: { title: '我的商机', desc: '只看自己创建/归属自己的商机，提交需求后进入统一审批流。', short: '业务', transfer: '' },
  te: { title: '技术支持工作台', desc: '汇总多个业务提交到我名下的 BOM 配置需求。', short: '需求', transfer: '转交给我负责的需求' },
  cost: { title: '成本核算工作台', desc: '汇总已提交 BOM、待我核价的成本任务。', short: '成本', transfer: '转交成本任务' },
  quote: { title: '报价专员工作台', desc: '汇总已核价、待转正式报价或需退回的成本表。', short: '报价', transfer: '转交报价任务' },
  dispatch: { title: '任务调度页', desc: '按业务线或单个需求，配置技术、成本、报价负责人，并支持转交。', short: '调度', transfer: '' },
}
const pageTitle = computed(() => pageMeta[view.value].title)
const pageDesc = computed(() => pageMeta[view.value].desc)
const pageTransferText = computed(() => pageMeta[view.value].transfer)

const nodeCols = ['boming', 'costing', 'quoting'] as const
const nodeShortMap: Record<string, string> = { boming: '技术', costing: '成本', quoting: '报价' }
const nodeLabelMap: Record<string, string> = { requirement: '需求单', assign: '指派', boming: '方案配置', costing: '成本核算', quoting: '报价单', done: '已定稿' }
function nodeShort(key: string) { return nodeShortMap[key] || key }
function nodeLabel(key: string) { return nodeLabelMap[key] || key || '—' }
function pillClass(row: { current_node?: string; flow_status?: string }) {
  if (row.flow_status === 'done') return 'green'
  if (row.flow_status === 'returned') return 'red'
  if (row.current_node === 'boming') return 'amber'
  return ''
}
function businessAction(row: { current_node?: string; flow_status?: string }) {
  return row.flow_status === 'returned' ? '处理' : '进入'
}

const businessColumns: TableColumn[] = [
  { title: '客户', key: 'customer_name' },
  { title: '需求摘要', key: 'summary' },
  { title: '业务', key: 'sales_person' },
  { title: '当前节点', key: 'current_node' },
  { title: '更新时间', key: 'updated_at' },
  { title: '操作', key: 'action' },
]
const transferColumns: TableColumn[] = [
  { title: '时间', key: 'time' },
  { title: '需求', key: 'customer_name' },
  { title: '节点', key: 'node_label' },
  { title: '原处理人', key: 'from_assignee' },
  { title: '新处理人', key: 'to_assignee' },
  { title: '操作人', key: 'actor' },
]
// 业务页
const businessCards = ref<any[]>([])
const businessLoading = ref(false)
const businessSummary = ref({ total: 0, returned: 0, in_progress: 0, done: 0 })
const businessPage = ref(1)
const businessPageSize = ref(10)
const businessTotal = ref(0)
const businessUserPickedPageSize = ref(false)
const businessSearch = ref('')
const businessSortBy = ref<'updated_at' | 'created_at'>('updated_at')
let businessSearchTimer: number | undefined
const businessPagination = computed(() => ({
  current: businessPage.value,
  pageSize: businessPageSize.value,
  total: businessTotal.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['5', '10', '15', '20', '30', '50'],
}))
function onBusinessTableChange(pag: any) {
  businessPage.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== businessPageSize.value) {
    businessPageSize.value = pag.pageSize
    businessUserPickedPageSize.value = true
  }
  if (pag.sorter && pag.sorter.order) {
    businessSortBy.value = pag.sorter.order === 'ascend' ? ('created_at' as const) : ('updated_at' as const)
  }
  loadBusiness()
}
function onBusinessSearch() {
  if (businessSearchTimer) window.clearTimeout(businessSearchTimer)
  businessSearchTimer = window.setTimeout(() => {
    businessPage.value = 1
    loadBusiness()
  }, 300)
}
const createOpen = ref(false)

const businessRows = computed(() => businessCards.value.map(c => ({
  ...c,
  summary: [c.platform_type, c.chassis_form, c.purchase_qty ? `${c.purchase_qty}台` : ''].filter(Boolean).join(' · '),
})))
const businessStats = computed(() => {
  const s = businessSummary.value
  return [
    { label: '全部商机', value: s.total, hint: '' },
    { label: '待我处理', value: s.returned, hint: '需求待修改' },
    { label: '流转中', value: s.in_progress, hint: 'BOM / 核价 / 报价' },
    { label: '已定稿', value: s.done, hint: '正式报价可见' },
  ]
})

async function loadBusiness() {
  businessLoading.value = true
  try {
    const res = await portalApi.oppCards({ page: businessPage.value, page_size: businessPageSize.value, search: businessSearch.value?.trim() || undefined, sort_by: businessSortBy.value, sort_order: 'desc' })
    businessCards.value = res.cards || []
    businessSummary.value = res.summary || { total: res.total || 0, returned: 0, in_progress: 0, done: 0 }
    businessTotal.value = res.total || 0
  } catch (e: any) {
    message.error('加载商机失败：' + (e?.message || e))
  } finally {
    businessLoading.value = false
  }
}

// 角色任务页
const taskItems = ref<PortalTaskItem[]>([])
const taskLoading = ref(false)
const taskSummary = ref({ total: 0, today: 0, mine: 0, pool: 0 })
const taskPage = ref(1)
const taskPageSize = ref(10)
const taskTotal = ref(0)
const taskUserPickedPageSize = ref(false)
const taskPagination = computed(() => ({
  current: taskPage.value,
  pageSize: taskPageSize.value,
  total: taskTotal.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['5', '10', '15', '20', '30', '50'],
}))
function onTaskTableChange(pag: any) {
  taskPage.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== taskPageSize.value) {
    taskPageSize.value = pag.pageSize
    taskUserPickedPageSize.value = true
  }
  loadTasks()
}
const taskTableTitle = computed(() => {
  if (view.value === 'te') return '需求任务队列'
  if (view.value === 'cost') return '成本任务队列'
  return '报价任务队列'
})
const taskColumns = computed<TableColumn[]>(() => {
  if (view.value === 'te') return [
    { title: '来源业务', key: 'sales_person' },
    { title: '客户', key: 'customer_name' },
    { title: '需求摘要', key: 'summary' },
    { title: '状态', key: 'status' },
    { title: '操作', key: 'action' },
  ]
  if (view.value === 'cost') return [
    { title: '来源业务', key: 'sales_person' },
    { title: '客户', key: 'customer_name' },
    { title: '配置', key: 'summary' },
    { title: 'BOM 提交人', key: 'source_actor' },
    { title: '状态', key: 'status' },
    { title: '操作', key: 'action' },
  ]
  return [
    { title: '来源业务', key: 'sales_person' },
    { title: '客户', key: 'customer_name' },
    { title: '成本表', key: 'summary' },
    { title: '成本核算人', key: 'source_actor' },
    { title: '状态', key: 'status' },
    { title: '操作', key: 'action' },
  ]
})
const taskStats = computed(() => {
  if (view.value === 'te') return [
    { label: '待配 BOM', value: taskSummary.value.mine, hint: '' },
    { label: '今日处理中', value: taskSummary.value.today, hint: '' },
    { label: '已提交核价', value: taskSummary.value.total, hint: '' },
    { label: '平均处理时长', value: '—', hint: '' },
  ]
  if (view.value === 'cost') return [
    { label: '待核价', value: taskSummary.value.mine, hint: '' },
    { label: '今日完成', value: taskSummary.value.today, hint: '' },
    { label: '待我复核', value: 0, hint: '' },
    { label: '已进报价', value: taskSummary.value.total, hint: '' },
  ]
  return [
    { label: '待报价', value: taskSummary.value.mine, hint: '' },
    { label: '今日定稿', value: taskSummary.value.today, hint: '' },
    { label: '已退回', value: 0, hint: '' },
    { label: '报价单总数', value: taskSummary.value.total, hint: '' },
  ]
})

async function loadTasks() {
  taskLoading.value = true
  try {
    const scope = isAdmin.value ? 'all' : 'mine'
    const res = await portalApi.tasks({ node: node.value, scope, page: taskPage.value, page_size: taskPageSize.value })
    taskItems.value = res.items || []
    taskSummary.value = res.summary || { total: 0, today: 0, mine: 0, pool: 0 }
    taskTotal.value = res.total || 0
  } catch (e: any) {
    message.error('加载任务失败：' + (e?.message || e))
  } finally {
    taskLoading.value = false
  }
}
function taskCell(item: PortalTaskItem) {
  if (view.value === 'te') return item.summary || '—'
  if (view.value === 'cost') return item.config_summary || item.summary || '—'
  return [item.config_summary, item.amount_text].filter(Boolean).join(' · ') || item.summary || '—'
}
function taskActor(item: PortalTaskItem) {
  return item.source_actor || '—'
}
function taskStatus(item: PortalTaskItem) {
  if (item.flow_status === 'done') return '已完成'
  if (item.flow_status === 'returned') return '需退回'
  return view.value === 'te' ? '待处理' : view.value === 'cost' ? '待核价' : '待转报价'
}
function taskPill(item: PortalTaskItem) {
  if (item.flow_status === 'done') return 'green'
  if (item.flow_status === 'returned') return 'red'
  return 'amber'
}
function taskAction(item: PortalTaskItem) {
  if (item.flow_status === 'done') return '查看'
  if (item.flow_status === 'returned') return view.value === 'quote' ? '退回核价' : '处理'
  if (view.value === 'te') return '开始配 BOM'
  if (view.value === 'cost') return '开始核价'
  return '转为报价单'
}
function openTask(opportunityId: string) {
  const from = view.value === 'business' ? 'portal-business' : `portal-${roleByView[view.value]}`
  router.push({ path: `/opportunities/${opportunityId}`, query: { from } })
}

// 转交
const transferOpen = ref(false)
const transferItem = ref<PortalTaskItem | null>(null)
const transferAssignee = ref('')
const transferCandidates = ref<string[]>([])
const transferCandidatesLoading = ref(false)
const transferSaving = ref(false)
const transferCandidateOptions = computed(() => transferCandidates.value.map(name => ({ label: name, value: name })))
async function openTransfer(item?: PortalTaskItem) {
  if (!taskItems.value.length) {
    message.warning('当前队列暂无可转交任务')
    return
  }
  transferItem.value = item || taskItems.value[0] || null
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
// 调度页
const dispatchData = ref<PortalDispatchData>({ businesses: [], rules: [], unassigned: {}, transfers: [] })
const dispatchLoading = ref(false)
const optionsMap = ref<Record<string, string[]>>({})
const ruleOpen = ref(false)
const ruleSaving = ref(false)
const ruleForm = ref({ business_user_id: '', node_key: 'boming', assignee_name: '' })
const nodeOptions = ['boming', 'costing', 'quoting'].map(n => ({ label: nodeShort(n), value: n }))
const ruleBusinessOptions = computed(() => dispatchData.value.businesses.map(b => ({ label: b.name, value: b.user_id })))
function assigneeOptions(key: string) {
  return (optionsMap.value[key] || []).map(name => ({ label: name, value: name }))
}

const dispatchStats = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  const todayTransfers = dispatchData.value.transfers.filter(t => (t.time || '').startsWith(today)).length
  return [
    { label: '覆盖业务', value: dispatchData.value.businesses.length, hint: '' },
    { label: '待分派任务', value: nodeCols.reduce((sum, n) => sum + (dispatchData.value.unassigned[n] || 0), 0), hint: '' },
    { label: '今日转交', value: todayTransfers, hint: '' },
    { label: '公共池', value: dispatchData.value.unassigned['boming'] || 0, hint: 'BOM 未指派' },
  ]
})

async function loadDispatch() {
  dispatchLoading.value = true
  try {
    const [data, opts] = await Promise.all([portalApi.dispatch(), portalApi.assignOptions()])
    dispatchData.value = data || { businesses: [], rules: [], unassigned: {}, transfers: [] }
    optionsMap.value = opts.assignees || {}
  } catch (e: any) {
    message.error('加载调度数据失败：' + (e?.message || e))
  } finally {
    dispatchLoading.value = false
  }
}
function ruleAssignee(businessUserId: string, key: string) {
  return dispatchData.value.rules.find(r => r.business_user_id === businessUserId && r.node_key === key)?.assignee_name || ''
}
function assigneesFor(key: string) {
  return optionsMap.value[key] || []
}
async function onRuleChange(businessUserId: string, key: string, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  try {
    if (!value) {
      await portalApi.deleteAssignmentRule({ business_user_id: businessUserId, node_key: key })
    } else {
      await portalApi.saveAssignmentRule({ business_user_id: businessUserId, node_key: key, assignee_name: value })
    }
    message.success('规则已更新')
    await loadDispatch()
  } catch (e: any) {
    message.error('保存规则失败：' + (e?.message || e))
  }
}
function openRuleModal(businessUserId = '', key = 'boming') {
  ruleForm.value = { business_user_id: businessUserId, node_key: key, assignee_name: ruleAssignee(businessUserId, key) }
  ruleOpen.value = true
}
async function saveRule() {
  if (!ruleForm.value.business_user_id || !ruleForm.value.assignee_name) {
    message.warning('请选择业务和处理人')
    return
  }
  ruleSaving.value = true
  try {
    await portalApi.saveAssignmentRule({
      business_user_id: ruleForm.value.business_user_id,
      node_key: ruleForm.value.node_key,
      assignee_name: ruleForm.value.assignee_name,
    })
    message.success('规则已保存')
    ruleOpen.value = false
    await loadDispatch()
  } catch (e: any) {
    message.error('保存规则失败：' + (e?.message || e))
  } finally {
    ruleSaving.value = false
  }
}
const stats = computed(() => {
  if (view.value === 'business') return businessStats.value
  if (isTaskView.value) return taskStats.value
  return dispatchStats.value
})

const roleByView: Record<ViewKey, string> = {
  business: 'business',
  te: 'te',
  cost: 'cost',
  quote: 'quote',
  dispatch: 'admin',
}

async function load() {
  if (view.value === 'business') return loadBusiness()
  if (isTaskView.value) return loadTasks()
  return loadDispatch()
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
    let changed = false
    if (!businessUserPickedPageSize.value && next !== businessPageSize.value) {
      businessPageSize.value = next
      businessPage.value = 1
      changed = true
    }
    if (!taskUserPickedPageSize.value && next !== taskPageSize.value) {
      taskPageSize.value = next
      taskPage.value = 1
      changed = true
    }
    if (changed && guardView()) load()
  }, 200)
}

onMounted(() => {
  if (guardView()) {
    businessPageSize.value = computeAdaptivePageSize()
    taskPageSize.value = computeAdaptivePageSize()
    load()
  }
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})
watch(view, () => {
  if (guardView()) load()
})
</script>
<style scoped>
.workstation {
  min-height: 100%;
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
.primary-btn, .ghost-btn { border: 0; border-radius: 12px; padding: 10px 14px; cursor: pointer; font-weight: 700; font-size: 13px; }
.primary-btn { color: white; background: linear-gradient(135deg, var(--cpq-accent-primary), #7c5cfc); box-shadow: 0 8px 20px var(--cpq-overlay-a20); }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.ghost-btn { background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-glass-border); color: var(--cpq-text-primary); }
.ghost-btn:disabled { opacity: .45; cursor: not-allowed; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat { padding: 14px; border: 1px solid var(--cpq-glass-border); border-radius: 16px; background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur, 16px)); }
.stat small { display: block; color: var(--cpq-text-secondary); font-size: 12px; margin-bottom: 7px; }
.stat b { font-size: 24px; }
.stat .hint { font-size: 12px; color: var(--cpq-text-muted); margin-left: 6px; font-weight: 500; }
.card { border: 1px solid var(--cpq-glass-border); border-radius: 18px; background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur, 18px)); box-shadow: var(--cpq-glass-card-shadow); margin-bottom: 16px; overflow: hidden; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.card-head h3 { margin: 0; font-size: 16px; }
.card-head small { color: var(--cpq-text-secondary); font-size: 12px; }
.card-body { padding: 4px 8px 8px; }
.table-body { padding: 0; }
.table-body :deep(.ant-table-wrapper) { border-radius: 0 0 18px 18px; }
.table-body :deep(.ant-pagination) { padding: 12px 16px; border-top: 1px solid var(--cpq-overlay-w8); }
.muted { color: var(--cpq-text-secondary); }
.pill { display: inline-block; padding: 3px 9px; border-radius: 999px; background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); font-size: 12px; }
.pill.amber { background: rgba(217, 119, 6, .14); color: #d97706; }
.pill.green { background: rgba(22, 163, 74, .14); color: #16a34a; }
.pill.red { background: rgba(220, 38, 38, .12); color: #dc2626; }
.link { border: 0; background: none; color: var(--cpq-accent-primary); cursor: pointer; font-size: 13px; }

.assign-grid { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr; gap: 8px; }
.assign-grid .head { font-size: 11px; color: var(--cpq-text-secondary); font-weight: 700; padding: 8px 10px; }
.assign-cell { padding: 9px 10px; border: 1px solid var(--cpq-glass-border); border-radius: 11px; background: var(--cpq-overlay-w4); min-width: 0; }
.assign-cell small { display: block; color: var(--cpq-text-secondary); font-size: 10px; margin-bottom: 3px; }
.assign-cell b { font-size: 12px; display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.assign-cell.pool { background: var(--cpq-overlay-a8); }
.assign-cell select { width: 100%; padding: 6px 7px; border-radius: 9px; border: 1px solid var(--cpq-glass-border-strong); background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); font-size: 12px; }
.modal-tip { color: var(--cpq-text-secondary); font-size: 13px; }
@media (max-width: 900px) {
  .stats { grid-template-columns: 1fr 1fr; }
  .assign-grid { grid-template-columns: 1fr 1fr; }
}
</style>
