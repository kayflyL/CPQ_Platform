<template>
  <div class="dispatch-panel">
    <!-- 统计条：无主任务卡可点击，点开处理抽屉 -->
    <div class="stats">
      <button type="button" class="stat stat-click" :class="{ danger: stats.stuck > 0, ok: stats.stuck === 0 }" @click="openStuck()">
        <small>🔥 无主任务</small>
        <b>{{ stats.stuck }}</b>
        <span class="hint">{{ stats.stuck > 0 ? '点击处理' : '全部有主' }}</span>
      </button>
      <div class="stat"><small>活跃任务</small><b>{{ stats.active }}</b><span class="hint">三条节点在办</span></div>
      <div class="stat"><small>今日转交</small><b>{{ stats.todayTransfers }}</b><span class="hint">近 30 条共 {{ dispatchData.transfers.length }} 条</span></div>
      <div class="stat"><small>规则覆盖</small><b>{{ stats.ruleCount }}</b><span class="hint">/ {{ stats.ruleTotal }} 格（业务×节点）</span></div>
    </div>

    <!-- 报价外发审批队列：客户版导出/平台内发送/规格书 PDF 出门前须总监批准 -->
    <div class="card">
      <div class="card-head">
        <h3>报价外发审批</h3>
        <small>等待越久越醒目 · 催办只提醒不改责任归属 · 系统永不自动批/拒</small>
      </div>
      <div class="card-body">
        <div class="queue-scroll">
          <table class="queue-table">
          <thead>
            <tr>
              <th>客户 / 商机</th><th>报价单</th><th>提交人</th><th>责任总监</th>
              <th>已等待</th><th>毛利率</th><th>状态</th><th style="text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in approvalQueue" :key="a.id">
              <td><a class="q-link" @click="goQuote(a)">{{ a.customer_name || a.opportunity_id }}</a></td>
              <td>{{ a.quotation_id }}</td>
              <td>{{ a.requested_by || '—' }}</td>
              <td>{{ a.assigned_name || '全体审批人' }}</td>
              <td :class="{ 'q-hot': a.status === 'pending' && (a.escalated_at || (a.waited_hours || 0) >= 24) }">
                {{ a.status === 'pending' ? waitedTextOf(a) : '—' }}
              </td>
              <td>{{ Number(a.margin_pct).toFixed(2) }}%</td>
              <td>
                <span class="q-pill" :class="a.status">
                  {{ a.status === 'pending' ? (a.escalated_at ? '已超时提醒' : '待审批') : a.status === 'approved' ? '已批准' : '已驳回' }}
                </span>
              </td>
              <td style="text-align: right">
                <button
                  v-if="a.status === 'pending'"
                  type="button"
                  class="mini-btn"
                  :disabled="remindingId === a.id"
                  @click="remindOne(a)"
                >{{ remindingId === a.id ? '催办中…' : '催办' }}</button>
              </td>
            </tr>
            <tr v-if="!approvalQueue.length && !queueLoading">
              <td colspan="8" class="q-empty">暂无审批单——报价单要出门（导出/发送）需要总监批准时才会出现在这里</td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>
    </div>

    <!-- 人 × 节点看板：在办负载与默认承接规则合并成同一视图 -->
    <div class="card">
      <div class="card-head">
        <h3>人员 × 节点</h3>
        <small>在办 = 名下当前任务数 · 默认承接 = 该业务新任务无指定处理人时的兜底人选</small>
      </div>
      <div class="card-body">
        <div class="roster-grid">
          <div v-for="col in rosterCols" :key="col.key" class="roster-col">
            <div class="roster-head">
              <b>{{ col.label }}</b>
              <span class="roster-total">{{ col.total }} 在办</span>
              <button v-if="col.unassigned > 0" type="button" class="roster-stuck" @click="openStuck(col.key)">无主 {{ col.unassigned }}</button>
            </div>

            <div class="handler-list">
              <div v-for="h in col.handlers" :key="h.name" class="handler-card">
                <div class="hc-top">
                  <span class="hc-avatar" :class="{ ghost: h.ghost }">{{ h.name.slice(0, 1) }}</span>
                  <span class="hc-name" :title="h.name">{{ h.name }}</span>
                  <span class="hc-count" :class="{ zero: !h.count }">在办 {{ h.count }}</span>
                  <button type="button" class="hc-remove" title="移除该处理人：在办任务转无主，默认规则一并删除" @click="askRemove(col.key, h)">移除</button>
                </div>
                <div class="hc-rules">
                  <!-- 业务多时折叠：只显示前 CHIP_VISIBLE 个，余量收进「+N 项」弹层，不撑卡片 -->
                  <span v-for="biz in h.businesses.slice(0, chipVisible)" :key="biz.uid" class="biz-chip" :class="{ fb: biz.uid === '*' }" :title="biz.uid === '*' ? '兜底：承接全部业务（含未来新增）' : `默认承接：${biz.name}`">
                    {{ biz.uid === '*' ? '全部业务' : biz.name }}
                    <i class="biz-x" @click.stop="removeRule(col.key, biz.uid)">×</i>
                  </span>
                  <a-popover v-if="h.businesses.length > chipVisible" placement="top" trigger="click">
                    <span class="biz-chip biz-more">+{{ h.businesses.length - chipVisible }} 项</span>
                    <template #content>
                      <div class="pop-biz">
                        <span v-for="biz in h.businesses" :key="biz.uid" class="biz-chip" :class="{ fb: biz.uid === '*' }" :title="biz.uid === '*' ? '兜底：承接全部业务（含未来新增）' : `默认承接：${biz.name}`">
                          {{ biz.uid === '*' ? '全部业务' : biz.name }}
                          <i class="biz-x" @click.stop="removeRule(col.key, biz.uid)">×</i>
                        </span>
                      </div>
                    </template>
                  </a-popover>
                  <button v-if="adding && adding.node === col.key && adding.handler === h.name" type="button" class="chip-add active">添加中…</button>
                  <button v-else type="button" class="chip-add" title="为该处理人添加默认承接业务" @click="startAdd(col.key, h.name)">＋</button>
                </div>
              </div>
              <div v-if="!col.handlers.length" class="col-empty">暂无在办任务与默认规则</div>
            </div>

            <!-- 尾卡：添加默认规则（列级表单，指定处理人时锁定人选） -->
            <div v-if="adding && adding.node === col.key" class="add-form">
              <a-select
                v-if="!adding.handler"
                v-model:value="addHandlerPick"
                :options="handlerOptions(col.key)"
                placeholder="处理人"
                size="small"
                style="width: 100%"
              />
              <div v-else class="add-form-handler">{{ adding.handler }}</div>
              <a-select
                v-model:value="addBizPick"
                :options="bizOptions(col.key)"
                mode="multiple"
                placeholder="选择默认承接的业务"
                size="small"
                style="width: 100%"
                show-search
                :max-tag-count="3"
                :disabled="addAll"
              />
              <div class="add-form-row">
                <label class="add-form-all">
                  <input v-model="addAll" type="checkbox" /> 承接全部业务（兜底，含未来新增）
                </label>
                <button type="button" class="mini-btn" :disabled="addAll" @click="selectAllBiz(col.key)">全选未分配</button>
              </div>
              <div class="add-form-ops">
                <button type="button" class="mini-btn primary" :disabled="addSaving || !((addAll || addBizPick.length) && (adding.handler || addHandlerPick))" @click="saveAdd(col.key)">保存</button>
                <button type="button" class="mini-btn" @click="cancelAdd">取消</button>
              </div>
            </div>
            <button v-else type="button" class="tail-add" @click="startAdd(col.key, '')">＋ 添加默认规则</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 转交记录：审计用，默认收起 -->
    <a-collapse :active-key="[]" class="transfer-collapse" ghost>
      <a-collapse-panel key="transfers" header="转交记录（近 30 条）">
        <a-table
          :data-source="dispatchData.transfers"
          :columns="transferColumns"
          :loading="loading"
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
      </a-collapse-panel>
    </a-collapse>

    <!-- 无主任务弹窗：灭火清单，统计卡/列头「无主N」均可唤起；三列密集卡片 -->
    <a-modal
      v-model:open="stuckOpen"
      width="920px"
      centered
      :body-style="{ background: 'var(--cpq-bg-secondary)', padding: '14px 16px 16px' }"
      wrap-class-name="portal-modal"
      :footer="null"
    >
      <template #title>
        <span class="stuck-title">无主任务 <b>{{ drawerStuck.length }}</b></span>
        <a-tag v-if="drawerNode" class="stuck-filter" closable @close="drawerNode = ''">{{ nodeLabelOf(drawerNode) }}</a-tag>
      </template>
      <div v-if="!drawerStuck.length" class="all-clear">
        <span class="ok-dot"></span>全部任务都有主，无卡死流程
      </div>
      <template v-else>
        <div class="stuck-toolbar">
          <span class="drawer-tip">当前节点无处理人的在办流程 · 按停留时长倒序 · ≥3 天标红</span>
          <button type="button" class="mini-btn primary" :disabled="!dispatchData.stuck.length || autofilling" @click="onAutofill">
            {{ autofilling ? '补齐中…' : '⚡ 一键按规则补齐' }}
          </button>
        </div>
        <div class="stuck-grid">
          <div v-for="item in drawerStuck" :key="item.opportunity_id" class="stuck-card">
            <div class="sc-top">
              <a class="sc-name" :title="item.customer_name" @click="goDetail(item.opportunity_id)">{{ item.customer_name || item.opportunity_id }}</a>
              <span class="sr-days" :class="{ hot: item.stuck_days >= 3 }">停 {{ item.stuck_days }} 天</span>
            </div>
            <div class="sc-meta">
              <span class="pill amber">{{ item.node_label }}</span>
              <span v-if="item.suggest" class="sc-suggest" :title="`默认规则 → ${item.suggest}`">默认 → {{ item.suggest }}</span>
            </div>
            <div class="sc-ops">
              <select v-model="pick[item.opportunity_id]">
                <option value="" disabled>{{ item.suggest ? '选择处理人' : '无默认规则，请选择' }}</option>
                <option v-for="name in assigneesFor(item.current_node)" :key="name" :value="name">{{ name }}</option>
              </select>
              <button type="button" class="mini-btn primary" :disabled="!pick[item.opportunity_id] || assigningId === item.opportunity_id" @click="assignStuck(item)">
                {{ assigningId === item.opportunity_id ? '指派中…' : '指派' }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
/**
 * 任务调度台面板（admin 专用）。
 * 三块：统计条（无主卡点击开弹窗）→ 人×节点看板（负载+默认规则合并，按人分组而非业务×节点矩阵，
 * 参考 GitHub code owners / review assignment 的按人分组口径）→ 转交记录（收起）。
 * 无主清单收在弹窗密集卡片网格里，不占主页面；指派走 /assign（留审计事件），一键补齐走 /dispatch/autofill。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { portalApi, type PortalDispatchData } from '@/api/portal'

const router = useRouter()

const NODE_LABELS: Record<string, string> = { boming: '方案配置', costing: '成本核算', quoting: '报价单' }
function nodeLabelOf(key: string) { return NODE_LABELS[key] || key }

const EMPTY: PortalDispatchData = { businesses: [], rules: [], transfers: [], nodes: [], stuck: [], matrix: {} }
const dispatchData = ref<PortalDispatchData>({ ...EMPTY })
const optionsMap = ref<Record<string, string[]>>({})
const loading = ref(false)
// 无主抽屉：每行的指派下拉值（opportunity_id → 姓名）
const pick = reactive<Record<string, string>>({})
const assigningId = ref('')
const autofilling = ref(false)

const transferColumns = [
  { title: '时间', key: 'time' },
  { title: '需求', key: 'customer_name' },
  { title: '节点', key: 'node_label' },
  { title: '原处理人', key: 'from_assignee' },
  { title: '新处理人', key: 'to_assignee' },
  { title: '操作人', key: 'actor' },
]

// ── 报价外发审批队列（pending 在前；积压全员可见，催办仅提交人/管理员走后端门禁） ──
interface ApprovalQueueItem {
  id: number
  opportunity_id: string
  quotation_id: string
  customer_name?: string
  requested_by: string
  assigned_name?: string
  status: 'pending' | 'approved' | 'rejected'
  margin_pct: number
  created_at: string
  waited_hours?: number
  escalated_at?: string
}
const approvalQueue = ref<ApprovalQueueItem[]>([])
const queueLoading = ref(false)
const remindingId = ref(0)
async function loadApprovalQueue() {
  queueLoading.value = true
  try {
    const res = await portalApi.pricingApprovalQueue()
    approvalQueue.value = res.approvals || []
  } catch { /* 队列端点 admin 限定，非管理端静默 */ }
  finally { queueLoading.value = false }
}
function waitedTextOf(a: ApprovalQueueItem): string {
  const h = a.waited_hours
  if (h == null) return '—'
  return h < 1 ? `${Math.max(1, Math.round(h * 60))} 分钟` : h < 48 ? `${Math.floor(h)} 小时` : `${Math.floor(h / 24)} 天`
}
async function remindOne(a: ApprovalQueueItem) {
  remindingId.value = a.id
  try {
    await portalApi.remindPricingApproval(a.opportunity_id, a.id)
    message.success('已催办（通知责任总监）')
    await loadApprovalQueue()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '催办失败')
  } finally { remindingId.value = 0 }
}
function goQuote(a: ApprovalQueueItem) {
  router.push(`/opportunities/${a.opportunity_id}`)
}

// ── 统计条 ──
const stats = computed(() => {
  const stuck = dispatchData.value.stuck.length
  const active = dispatchData.value.nodes.reduce(
    (sum, n) => sum + n.workload.reduce((s, w) => s + w.count, 0) + n.unassigned_count, 0)
  const today = new Date().toISOString().slice(0, 10)
  const todayTransfers = dispatchData.value.transfers.filter(t => (t.time || '').startsWith(today)).length
  return {
    stuck, active, todayTransfers,
    ruleCount: dispatchData.value.rules.filter(r => r.business_user_id !== '*').length,
    ruleTotal: dispatchData.value.businesses.length * 3,
  }
})

// ── 人 × 节点看板：workload（在办）与 rules（默认承接）按处理人合并 ──
const bizNameMap = computed(() => {
  const m: Record<string, string> = {}
  for (const b of dispatchData.value.businesses) m[b.user_id] = b.name
  return m
})
type HandlerCard = { name: string; count: number; ghost: boolean; businesses: Array<{ uid: string; name: string }> }
const rosterCols = computed(() => dispatchData.value.nodes.map(n => {
  const byHandler = new Map<string, string[]>()
  for (const r of dispatchData.value.rules) {
    if (r.node_key !== n.key || !r.assignee_name) continue
    const arr = byHandler.get(r.assignee_name) || []
    arr.push(r.business_user_id)
    byHandler.set(r.assignee_name, arr)
  }
  const workload = new Map(n.workload.map(w => [w.name, w.count]))
  const handlers: HandlerCard[] = [...new Set([...workload.keys(), ...byHandler.keys()])]
    .map(name => ({
      name,
      count: workload.get(name) || 0,
      // legacy 自由填写值（姓名，手机号）匹配不到候选账号 → 幽灵处理人标记
      ghost: !(optionsMap.value[n.key] || []).includes(name),
      businesses: (byHandler.get(name) || []).map(uid => ({
        uid,
        // business_user_id='*' 的兜底规则渲染为「全部业务」特殊芯片
        name: uid === '*' ? '全部业务' : (bizNameMap.value[uid] || uid),
      })),
    }))
    .sort((a, b) => b.count - a.count || b.businesses.length - a.businesses.length)
  return {
    key: n.key, label: n.label, handlers,
    total: n.workload.reduce((s, w) => s + w.count, 0) + n.unassigned_count,
    unassigned: n.unassigned_count,
  }
}))

// ── 默认规则增删（列级内联表单） ──
const adding = ref<null | { node: string; handler: string }>(null)
const addHandlerPick = ref('')
const addBizPick = ref<string[]>([])
const addAll = ref(false)  // 勾选=节点兜底规则（business_user_id='*'），承接全部业务含未来新增
const addSaving = ref(false)
function handlerOptions(nodeKey: string) {
  return assigneesFor(nodeKey).map(name => ({ label: name, value: name }))
}
// 该节点已有规则的业务不再出现在候选里（一业务一节点一个默认）
function bizOptions(nodeKey: string) {
  const covered = new Set(dispatchData.value.rules.filter(r => r.node_key === nodeKey).map(r => r.business_user_id))
  return dispatchData.value.businesses
    .filter(b => !covered.has(b.user_id))
    .map(b => ({ label: b.name, value: b.user_id }))
}
// 批量勾选：一键把该节点所有未分配业务填进多选框（与兜底勾选互补——兜底含未来，全选只含当前）
function selectAllBiz(nodeKey: string) {
  addBizPick.value = bizOptions(nodeKey).map(o => String(o.value))
}
// 处理人卡芯片折叠阈值：超出收进「+N 项」弹层
const chipVisible = 5
function startAdd(nodeKey: string, handler: string) {
  adding.value = { node: nodeKey, handler }
  addHandlerPick.value = ''
  addBizPick.value = []
  addAll.value = false
}
function cancelAdd() { adding.value = null }
async function saveAdd(nodeKey: string) {
  if (!adding.value) return
  const handler = adding.value.handler || addHandlerPick.value
  if (!handler || (!addAll.value && !addBizPick.value.length)) return
  addSaving.value = true
  try {
    if (addAll.value) {
      // 兜底规则：business_user_id='*'——没配专属规则的业务全归他，含未来新增的业务账号
      await portalApi.saveAssignmentRule({ business_user_id: '*', node_key: nodeKey, assignee_name: handler })
      message.success(`已设全部业务兜底 → ${handler}`)
    } else {
      for (const uid of addBizPick.value) {
        await portalApi.saveAssignmentRule({ business_user_id: uid, node_key: nodeKey, assignee_name: handler })
      }
      message.success(`已设 ${addBizPick.value.length} 条默认规则 → ${handler}`)
    }
    cancelAdd()
    await load()
  } catch (e: any) {
    message.error('保存规则失败：' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    addSaving.value = false
  }
}
async function removeRule(nodeKey: string, businessUserId: string) {
  try {
    await portalApi.deleteAssignmentRule({ business_user_id: businessUserId, node_key: nodeKey })
    message.success('已移除默认规则')
    await load()
  } catch (e: any) {
    message.error('删除规则失败：' + (e?.message || e))
  }
}
// 卡级移除：在办任务转无主 + 默认规则一并删除（无主清单/一键补齐负责后续再分配）
function askRemove(nodeKey: string, h: HandlerCard) {
  Modal.confirm({
    title: `移除处理人「${h.name}」？`,
    content: `该节点名下 ${h.count} 条在办任务将转为无主（可在无主清单重新指派或一键按规则补齐），${h.businesses.length} 条默认承接规则一并删除。`,
    okText: '移除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        const res = await portalApi.removeHandler({ node_key: nodeKey, handler: h.name })
        message.success(`已移除 ${h.name}：${res.cleared} 条任务转无主，${res.rules_removed} 条规则删除`)
        await load()
      } catch (e: any) {
        message.error('移除失败：' + (e?.response?.data?.detail || e?.message || e))
      }
    },
  })
}

// ── 无主任务抽屉 ──
const stuckOpen = ref(false)
const drawerNode = ref('')
function openStuck(nodeKey = '') {
  drawerNode.value = nodeKey
  stuckOpen.value = true
}
const drawerStuck = computed(() =>
  dispatchData.value.stuck.filter(s => !drawerNode.value || s.current_node === drawerNode.value))

async function assignStuck(item: { opportunity_id: string; current_node: string }) {
  const name = pick[item.opportunity_id]
  if (!name) return
  assigningId.value = item.opportunity_id
  try {
    await portalApi.assignTask(item.opportunity_id, { node_key: item.current_node, assignee_name: name })
    message.success(`已指派给 ${name}`)
    delete pick[item.opportunity_id]
    await load()
  } catch (e: any) {
    message.error('指派失败：' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    assigningId.value = ''
  }
}

async function onAutofill() {
  autofilling.value = true
  try {
    const res = await portalApi.dispatchAutofill()
    const parts = [`补齐 ${res.filled} 条`]
    if (res.unresolved) parts.push(`${res.unresolved} 条无有效规则`)
    if (res.failed) parts.push(`${res.failed} 条失败`)
    if (res.filled) message.success(parts.join('，'))
    else message.warning(parts.join('，'))
    await load()
  } catch (e: any) {
    message.error('一键补齐失败：' + (e?.message || e))
  } finally {
    autofilling.value = false
  }
}

function assigneesFor(key: string) { return optionsMap.value[key] || [] }
function goDetail(id: string) {
  router.push({ path: `/opportunities/${id}`, query: { from: 'portal-dispatch' } })
}

async function load() {
  loading.value = true
  try {
    const [data, opts] = await Promise.all([portalApi.dispatch(), portalApi.assignOptions()])
    dispatchData.value = { ...EMPTY, ...data }
    optionsMap.value = opts.assignees || {}
    // 下拉预填建议人选；建议不在候选内（如账号已停用/legacy 自由填写）则留空手选
    for (const s of dispatchData.value.stuck) {
      const cand = optionsMap.value[s.current_node] || []
      pick[s.opportunity_id] = s.suggest && cand.includes(s.suggest) ? s.suggest : ''
    }
  } catch (e: any) {
    message.error('加载调度数据失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

watch(stuckOpen, (open) => { if (!open) drawerNode.value = '' })
onMounted(() => {
  void load()
  void loadApprovalQueue()
})
</script>

<style scoped>
.dispatch-panel { display: flex; flex-direction: column; }

/* 统计条（无主卡=可点击按钮） */
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat {
  padding: 14px; border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur, 16px));
}
.stat small { display: block; color: var(--cpq-text-secondary); font-size: var(--cpq-font-size-sm); margin-bottom: 7px; }
.stat b { font-size: var(--cpq-font-size-2xl); }
.stat .hint { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); margin-left: 6px; font-weight: 500; }
.stat-click { cursor: pointer; transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), box-shadow var(--cpq-dur-1) var(--cpq-ease-smooth); }
.stat-click:hover { border-color: var(--cpq-glass-border-strong); box-shadow: var(--cpq-glass-card-shadow); }
.stat-click.danger { border-color: var(--cpq-notif-red-bg); }
.stat-click.danger b { color: var(--cpq-accent-danger); }
.stat-click.ok b { color: var(--cpq-notif-green); }

/* 卡容器 */
.card { border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-xl); background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur, 18px)); box-shadow: var(--cpq-glass-card-shadow); margin-bottom: 16px; overflow: hidden; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.card-head h3 { margin: 0; font-size: var(--cpq-font-size-lg); }
.card-head small { color: var(--cpq-text-secondary); font-size: var(--cpq-font-size-sm); }
.card-body { padding: 14px 16px 16px; }
.muted { color: var(--cpq-text-secondary); }

/* 人 × 节点看板 */
.roster-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.roster-col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.roster-head { display: flex; align-items: center; gap: 8px; }
.roster-head b { font-size: 13.5px; }
.roster-total { font-size: 11.5px; color: var(--cpq-text-muted); }
.roster-stuck {
  margin-left: auto; border: 1px solid var(--cpq-notif-red-bg); background: var(--cpq-notif-red-bg);
  color: var(--cpq-accent-danger); border-radius: var(--cpq-radius-full); padding: 2px 10px; font-size: 11.5px; font-weight: 600;
  cursor: pointer; transition: filter var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.roster-stuck:hover { filter: brightness(0.96); }
.handler-list { display: flex; flex-direction: column; gap: 8px; }
.handler-card { padding: 10px 12px; border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-md); background: var(--cpq-overlay-w4); transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.handler-card:hover { border-color: var(--cpq-glass-border-strong); }
.hc-top { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; min-width: 0; }
.hc-avatar {
  flex: none; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); font-size: var(--cpq-font-size-sm); font-weight: 700;
}
.hc-avatar.ghost { background: var(--cpq-warn-surface); color: var(--cpq-notif-amber); }
.hc-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hc-count { margin-left: auto; flex: none; font-size: var(--cpq-font-size-xs); color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border-radius: var(--cpq-radius-full); padding: 2px 9px; font-weight: 600; }
.hc-count.zero { color: var(--cpq-text-muted); background: var(--cpq-overlay-w8); }
/* 卡级「移除」：常驻弱文本，悬停转危险色 */
.hc-remove {
  flex: none; border: 0; background: transparent; padding: 2px 5px; font-size: var(--cpq-font-size-xs);
  color: var(--cpq-text-muted); cursor: pointer; border-radius: var(--cpq-radius-sm);
  transition: color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.hc-remove:hover { color: var(--cpq-accent-danger); }
.hc-rules { display: flex; flex-wrap: wrap; gap: 6px; min-height: 22px; }
.biz-chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 2px 4px 2px 9px; border-radius: var(--cpq-radius-full);
  font-size: 11.5px; color: var(--cpq-text-primary); background: var(--cpq-overlay-w8); border: 1px solid var(--cpq-overlay-w10);
  max-width: 100%; overflow: hidden;
}
.biz-chip .biz-x { font-style: normal; cursor: pointer; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); line-height: 1; padding: 0 3px; border-radius: 50%; }
.biz-chip .biz-x:hover { color: var(--cpq-accent-danger); }
/* 兜底规则芯片：虚线边框区分「全部业务」与单业务 */
.biz-chip.fb { border-style: dashed; border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); background: transparent; }
/* 「+N 项」折叠芯片 + 弹层全量列表 */
.biz-chip.biz-more { cursor: pointer; color: var(--cpq-accent-primary); background: transparent; border: 1px dashed var(--cpq-glass-border-strong); }
.pop-biz { display: flex; flex-wrap: wrap; gap: 6px; max-width: 320px; max-height: 240px; overflow: auto; }
.add-form-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.chip-add {
  border: 1px dashed var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-muted);
  border-radius: var(--cpq-radius-full); padding: 2px 10px; font-size: 11.5px; cursor: pointer;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.chip-add:hover, .chip-add.active { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
.col-empty { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); padding: 6px 2px; }
.no-rule-hint { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }

/* 列级添加表单 + 尾卡（虚线＋，全站新增入口范式） */
.add-form { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid var(--cpq-glass-border-strong); border-radius: var(--cpq-radius-md); background: var(--cpq-overlay-w4); }
.add-form-handler { font-size: 12.5px; font-weight: 600; color: var(--cpq-accent-primary); }
.add-form-all { display: flex; align-items: center; gap: 6px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); cursor: pointer; user-select: none; }
.add-form-ops { display: flex; gap: 8px; }
.tail-add {
  border: 1px dashed var(--cpq-glass-border); background: transparent; color: var(--cpq-text-muted);
  border-radius: var(--cpq-radius-md); padding: 8px; font-size: 12.5px; cursor: pointer;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.tail-add:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }

/* 迷你按钮（指派/补齐/表单） */
.mini-btn {
  border: 1px solid var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-secondary);
  border-radius: var(--cpq-radius-sm); padding: 4px 12px; font-size: var(--cpq-font-size-sm); cursor: pointer;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.mini-btn:hover:not(:disabled) { color: var(--cpq-text-primary); border-color: var(--cpq-glass-border-strong); }
.mini-btn.primary { border: 0; color: var(--cpq-accent-on-primary); background: var(--cpq-accent-gradient); font-weight: 600; }
.mini-btn.primary:disabled { opacity: .5; cursor: not-allowed; }

/* 转交记录 */
.transfer-collapse { border-radius: var(--cpq-radius-xl); background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border); overflow: hidden; }
.transfer-collapse :deep(.ant-collapse-header) { font-weight: 600; }

/* 无主任务弹窗 */
.stuck-title b { color: var(--cpq-accent-danger); margin-right: 6px; }
.stuck-filter { margin-left: 10px; }
.stuck-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.drawer-tip { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.all-clear { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-radius: var(--cpq-radius-md); font-size: 13px; color: var(--cpq-notif-green); background: var(--cpq-notif-green-bg); border: 1px solid transparent; }
.ok-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cpq-notif-green); }
.stuck-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; max-height: 62vh; overflow-y: auto; }
.stuck-card { padding: 10px 12px; border-radius: var(--cpq-radius-md); border: 1px solid var(--cpq-notif-red-bg); background: var(--cpq-notif-red-bg); }
.sc-top { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sc-name { color: var(--cpq-text-primary); font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sc-name:hover { color: var(--cpq-accent-primary); }
.sr-days { margin-left: auto; flex: none; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary); white-space: nowrap; }
.sr-days.hot { color: var(--cpq-accent-danger); font-weight: 700; }
.sc-meta { display: flex; align-items: center; gap: 8px; margin: 7px 0; min-width: 0; }
.pill { padding: 2px 8px; border-radius: var(--cpq-radius-full); background: var(--cpq-notif-amber-bg); color: var(--cpq-notif-amber); font-size: 11.5px; white-space: nowrap; }
.sc-suggest { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sc-ops { display: flex; gap: 8px; }
.sc-ops select { flex: 1; min-width: 0; padding: 5px 8px; border-radius: var(--cpq-radius-sm); border: 1px solid var(--cpq-glass-border-strong); background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); font-size: 12.5px; }

@media (max-width: 900px) {
  .stats { grid-template-columns: 1fr 1fr; }
  .roster-grid { grid-template-columns: 1fr; }
  .stuck-grid { grid-template-columns: 1fr; }
}

/* ── 报价外发审批队列 ── */
.queue-scroll { overflow-x: auto; }   /* 手机端窄屏横向滚动兜底，列不挤压 */
.queue-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.queue-table th {
  text-align: left; padding: 8px 10px; font-size: var(--cpq-font-size-xs); font-weight: 600;
  color: var(--cpq-text-secondary); background: var(--cpq-bg-tertiary);
  border-bottom: 1px solid var(--cpq-border-primary); white-space: nowrap;
}
.queue-table td { padding: 9px 10px; border-bottom: 1px solid var(--cpq-border-secondary); color: var(--cpq-text-primary); }
.queue-table tbody tr:hover td { background: var(--cpq-overlay-w3); }
.q-link { color: var(--cpq-text-primary); font-weight: 600; cursor: pointer; text-decoration: none; }
.q-link:hover { color: var(--cpq-accent-primary); }
.q-hot { color: var(--cpq-accent-danger); font-weight: 700; }
.q-pill { padding: 2px 10px; border-radius: var(--cpq-radius-full); font-size: var(--cpq-font-size-xs); white-space: nowrap; }
.q-pill.pending { background: var(--cpq-notif-amber-bg); color: var(--cpq-notif-amber); }
.q-pill.approved { background: var(--cpq-notif-green-bg); color: var(--cpq-notif-green); }
.q-pill.rejected { background: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.q-empty { text-align: center; color: var(--cpq-text-muted); padding: 22px 10px !important; }
</style>
