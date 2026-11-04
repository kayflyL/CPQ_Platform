<script setup lang="ts">
/**
 * 报价外发审批（/approvals）—— 独立收件箱页（审批卡从调度页迁出并升级）。
 * 状态分栏（待审批/已超时/已批准/已驳回）+ 搜索；审批总监就地批准/驳回（复用 decide 端点，
 * 批准 = 对内容指纹签发外发许可，改价自动失效需重批），提交人/管理员可催办。
 * 队列口径：admin 全量，审批总监=指派给自己 + 自己提交的（后端过滤）。
 * 原型规格：docs/prototypes/报价外发审批独立页-原型.html。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { portalApi, type PricingApproval } from '@/api/portal'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const meId = computed(() => auth.user?.user_id || '')
const meName = computed(() => auth.user?.name || '')

type TabKey = 'pending' | 'escalated' | 'approved' | 'rejected'
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'pending', label: '待审批' },
  { key: 'escalated', label: '已超时' },
  { key: 'approved', label: '已批准' },
  { key: 'rejected', label: '已驳回' },
]

const rows = ref<PricingApproval[]>([])
const loading = ref(false)
const tab = ref<TabKey>('pending')
const search = ref('')

async function load() {
  loading.value = true
  try {
    const res = await portalApi.pricingApprovalQueue()
    rows.value = res.approvals || []
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '审批队列加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const isPending = (a: PricingApproval) => a.status === 'pending'
const isEscalated = (a: PricingApproval) => isPending(a) && !!(a.escalated_at || (a.waited_hours || 0) >= 24)
const counts = computed(() => ({
  pending: rows.value.filter(isPending).length,
  escalated: rows.value.filter(isEscalated).length,
  approved: rows.value.filter(a => a.status === 'approved').length,
  rejected: rows.value.filter(a => a.status === 'rejected').length,
}))
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return rows.value.filter(a => {
    if (tab.value === 'escalated' ? !isEscalated(a) : a.status !== tab.value) return false
    if (!q) return true
    return [a.customer_name, a.quotation_id, a.requested_by, a.opportunity_id]
      .some(v => (v || '').toLowerCase().includes(q))
  })
})

/** 可裁决 = 审批权限 && pending &&（未指派广播 || 指派给我 || admin）——行级与后端 decide 同口径 */
function canDecide(a: PricingApproval) {
  if (!auth.can('action.flow.approve.pricing') || a.status !== 'pending') return false
  const assigned = a.assigned_to || ''
  return isAdmin.value || !assigned || assigned === meId.value
}
/** 可催办 = 提交人本人或 admin（后端同口径，按钮只做预筛） */
function canRemind(a: PricingApproval) {
  return a.status === 'pending' && (isAdmin.value || (a.requested_by || '') === meName.value)
}

function waitedTextOf(a: PricingApproval) {
  const h = a.waited_hours
  if (h == null) return '—'
  return h < 1 ? `${Math.max(1, Math.round(h * 60))} 分钟` : h < 48 ? `${Math.floor(h)} 小时` : `${Math.floor(h / 24)} 天`
}
const TRIGGER_LABEL: Record<string, string> = { outbound: '外发', low_margin: '低于阈值' }
function triggerLabel(a: PricingApproval) {
  const parts: string[] = []
  if (a.trigger_reason) parts.push(TRIGGER_LABEL[a.trigger_reason] || a.trigger_reason)
  if (Number(a.margin_pct) < Number(a.threshold)) parts.push('低于阈值')
  return [...new Set(parts)].join(' + ') || '外发'
}

// ── 详情抽屉 ──
const drawerOpen = ref(false)
const selected = ref<PricingApproval | null>(null)
function openDrawer(a: PricingApproval) { selected.value = a; drawerOpen.value = true }
function closeDrawer() { drawerOpen.value = false; selected.value = null }
/** 毛利率标尺：0 ~ 阈值×1.5 的量程，阈值线在 2/3 处 */
const marginPct = computed(() => {
  const a = selected.value
  if (!a) return { fill: 0, mark: 0, low: false }
  const range = Number(a.threshold) * 1.5 || 1
  return {
    fill: Math.min(100, (Number(a.margin_pct) / range) * 100),
    mark: (Number(a.threshold) / range) * 100,
    low: Number(a.margin_pct) < Number(a.threshold),
  }
})
const decideNote = ref('')
async function approveOne(a: PricingApproval) {
  try {
    await portalApi.decidePricingApproval(a.opportunity_id, a.id, { decision: 'approve', comment: decideNote.value })
    message.success('已批准：外发许可已签发，批准后改价将自动失效需重批')
    closeDrawer()
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '批准失败')
  }
}

// ── 驳回（必填理由） ──
const rejectOpen = ref(false)
const rejectReason = ref('')
const rejectSaving = ref(false)
function openReject(a: PricingApproval) {
  selected.value = a
  rejectReason.value = ''
  rejectOpen.value = true
}
async function confirmReject() {
  const a = selected.value
  if (!a) return
  if (!rejectReason.value.trim()) { message.warning('驳回时请填写审批意见，让报价员知道如何调整'); return }
  rejectSaving.value = true
  try {
    await portalApi.decidePricingApproval(a.opportunity_id, a.id, { decision: 'reject', comment: rejectReason.value })
    message.success('已驳回，理由将进入商机协作流')
    rejectOpen.value = false
    closeDrawer()
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '驳回失败')
  } finally {
    rejectSaving.value = false
  }
}

// ── 催办 ──
const remindingId = ref(0)
async function remindOne(a: PricingApproval) {
  remindingId.value = a.id
  try {
    await portalApi.remindPricingApproval(a.opportunity_id, a.id)
    message.success('已催办（通知责任总监）')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '催办失败')
  } finally {
    remindingId.value = 0
  }
}

function goOpp(a: PricingApproval) {
  router.push(`/opportunities/${a.opportunity_id}`)
}
</script>

<template>
  <div class="ap-page">
    <header class="ap-head">
      <div>
        <h1>报价外发审批</h1>
        <div class="ap-desc">报价单出门（客户版导出 / 平台内发送 / 规格书 PDF）前须总监批准 · 系统永不自动批/拒</div>
      </div>
      <div class="ap-stats">
        <div class="stat"><b>{{ counts.pending }}</b><span>待审批</span></div>
        <div class="stat danger"><b>{{ counts.escalated }}</b><span>已超时</span></div>
        <div class="stat ok"><b>{{ counts.approved }}</b><span>已批准</span></div>
        <div class="stat"><b>{{ counts.rejected }}</b><span>已驳回</span></div>
      </div>
    </header>

    <div class="ap-filter">
      <button v-for="t in TABS" :key="t.key" class="tab-chip" :class="{ on: tab === t.key, warn: t.key === 'escalated' }" @click="tab = t.key">
        {{ t.label }}<span v-if="counts[t.key]" class="n">{{ counts[t.key] }}</span>
      </button>
      <input v-model="search" class="ap-search" placeholder="搜索客户 / 报价单号 / 提交人" />
    </div>

    <div class="ap-card">
      <div class="table-scroll">
        <table class="ap-table">
          <thead>
            <tr>
              <th>客户 / 商机</th><th>报价单</th><th>提交人</th><th>责任总监</th>
              <th>毛利率</th><th>已等待</th><th>状态</th><th class="ta-r">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in filtered" :key="a.id" @click="openDrawer(a)">
              <td>
                <div class="cell-main"><a class="cell-link" @click.stop="goOpp(a)">{{ a.customer_name || a.opportunity_id }}</a></div>
                <div class="cell-sub">{{ a.requested_by || '—' }} 发起 · {{ triggerLabel(a) }}</div>
              </td>
              <td class="mono">{{ a.quotation_id }}</td>
              <td>{{ a.requested_by || '—' }}</td>
              <td>{{ a.assigned_name || '全体审批人' }}</td>
              <td :class="{ 'margin-low': Number(a.margin_pct) < Number(a.threshold) }">
                {{ Number(a.margin_pct).toFixed(2) }}%<span v-if="Number(a.margin_pct) < Number(a.threshold)" class="low-tag">低于阈值 {{ Number(a.threshold).toFixed(0) }}%</span>
              </td>
              <td class="mono" :class="{ 'wait-hot': isEscalated(a) }">{{ isPending(a) ? waitedTextOf(a) : '—' }}</td>
              <td>
                <span class="pill" :class="a.status === 'pending' ? (isEscalated(a) ? 'escalated' : 'pending') : a.status">
                  {{ a.status === 'pending' ? (isEscalated(a) ? '已超时提醒' : '待审批') : a.status === 'approved' ? '已批准' : '已驳回' }}
                </span>
              </td>
              <td class="ta-r">
                <div class="op-row" @click.stop>
                  <button v-if="canDecide(a)" type="button" class="op-btn go" @click="selected = a; drawerOpen = true">批准</button>
                  <button v-if="canDecide(a)" type="button" class="op-btn no" @click="openReject(a)">驳回</button>
                  <button v-if="canRemind(a)" type="button" class="op-btn" :disabled="remindingId === a.id" @click="remindOne(a)">
                    {{ remindingId === a.id ? '催办中…' : '催办' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!filtered.length && !loading">
              <td colspan="8" class="ap-empty">该状态下暂无审批单——报价单要出门（导出/发送）需要总监批准时才会出现在这里</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 详情抽屉：审批单全貌 + 就地裁决 -->
    <div class="mask" :class="{ on: drawerOpen }" @click="closeDrawer"></div>
    <aside class="drawer" :class="{ on: drawerOpen }">
      <div class="drawer-head">
        <div>
          <h2>{{ selected?.customer_name || selected?.opportunity_id || '审批单' }}</h2>
          <div class="drawer-sub">{{ selected?.quotation_id }} · {{ selected?.requested_by }} 发起</div>
        </div>
        <button type="button" class="drawer-close" @click="closeDrawer">×</button>
      </div>
      <div class="drawer-body" v-if="selected">
        <div class="note-block" v-if="selected.request_note">{{ selected.request_note }}</div>
        <div class="d-grid">
          <div class="d-item"><div class="k">商机</div><div class="v">{{ selected.customer_name || selected.opportunity_id }}</div></div>
          <div class="d-item"><div class="k">报价单</div><div class="v mono">{{ selected.quotation_id }}</div></div>
          <div class="d-item"><div class="k">提交人</div><div class="v">{{ selected.requested_by || '—' }}</div></div>
          <div class="d-item"><div class="k">责任总监</div><div class="v">{{ selected.assigned_name || '全体审批人（先到先批）' }}</div></div>
          <div class="d-item"><div class="k">发起时间</div><div class="v mono">{{ (selected.created_at || '').replace('T', ' ').slice(0, 16) }}</div></div>
          <div class="d-item"><div class="k">已等待</div><div class="v mono">{{ isPending(selected) ? waitedTextOf(selected) : '—' }}</div></div>
        </div>
        <div class="margin-track">
          <div class="bar"><i :style="{ width: marginPct.fill + '%', background: marginPct.low ? 'var(--cpq-notif-amber)' : 'var(--cpq-notif-green)' }"></i><em :style="{ left: marginPct.mark + '%' }"></em></div>
          <div class="lab">
            <span>毛利率 {{ Number(selected.margin_pct).toFixed(2) }}%</span>
            <span class="lab-mark">批准阈值 {{ Number(selected.threshold).toFixed(0) }}%</span>
          </div>
        </div>
        <div class="hash-line" v-if="selected.content_hash">
          <span>内容指纹</span><code>{{ selected.content_hash.slice(0, 12) }}…</code>
        </div>
        <div class="d-grid">
          <div class="d-item"><div class="k">路由依据</div><div class="v plain">{{ selected.route_snapshot || '按报价人所属总监' }}</div></div>
          <div class="d-item"><div class="k">触发原因</div><div class="v">{{ triggerLabel(selected) }}</div></div>
        </div>

        <template v-if="isPending(selected) && canDecide(selected)">
          <input v-model="decideNote" class="decide-note" placeholder="备注（选填，将随结果通知提交人）" />
          <div class="d-ops">
            <button type="button" class="btn primary" @click="approveOne(selected)">批准外发</button>
            <button type="button" class="btn no" @click="openReject(selected)">驳回</button>
          </div>
          <div class="gate-note">
            批准 = 对当前内容指纹签发外发许可：客户版导出 / 平台内发送 / 规格书 PDF 放行；<br />
            批准后改价或改动报价内容，许可自动失效，需重新发起审批。驳回必填理由，打回改价。
          </div>
        </template>
        <div v-else-if="!isPending(selected)" class="verdict-block">
          {{ selected.status === 'approved' ? '已批准' : '已驳回' }} · {{ selected.decided_by || '—' }} ·
          {{ (selected.decided_at || '').replace('T', ' ').slice(0, 16) }}
          <template v-if="selected.comment"> — 「{{ selected.comment }}」</template>
        </div>
        <div v-else class="gate-note">该单指派给 {{ selected.assigned_name || '全体审批人' }}，由其裁决（可在详情页转交）。</div>
      </div>
    </aside>

    <!-- 驳回弹窗：理由必填 -->
    <a-modal
      v-model:open="rejectOpen"
      title="驳回审批单"
      :confirm-loading="rejectSaving"
      ok-text="确认驳回"
      cancel-text="取消"
      :ok-button-props="{ danger: true }"
      @ok="confirmReject"
    >
      <p class="reject-tip">驳回会打回给提交人改价，理由将以评论进入商机协作流。</p>
      <a-input v-model:value="rejectReason" placeholder="驳回理由（必填，例如：毛利率低于红线，调整后重报）" />
    </a-modal>
  </div>
</template>

<style scoped>
.ap-page { max-width: 1280px; margin: 0 auto; }

/* 页头 + 统计 */
.ap-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--cpq-space-4); margin-bottom: var(--cpq-space-5); }
.ap-head h1 { margin: 0; font-size: var(--cpq-font-size-2xl); font-weight: var(--cpq-font-weight-semibold); line-height: var(--cpq-line-height-heading); }
.ap-desc { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); margin-top: var(--cpq-space-1); }
.ap-stats { display: flex; gap: var(--cpq-space-2); }
.stat {
  display: flex; flex-direction: column; align-items: center; padding: var(--cpq-space-2) var(--cpq-space-5);
  background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg); backdrop-filter: blur(var(--cpq-glass-card-blur, 16px));
  box-shadow: var(--cpq-glass-card-shadow);
}
.stat b { font-size: var(--cpq-font-size-xl); font-variant-numeric: tabular-nums; }
.stat span { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.stat.danger b { color: var(--cpq-accent-danger); }
.stat.ok b { color: var(--cpq-notif-green); }

/* 筛选条 */
.ap-filter { display: flex; align-items: center; gap: var(--cpq-space-2); flex-wrap: wrap; margin-bottom: var(--cpq-space-4); }
.tab-chip {
  padding: var(--cpq-space-1) var(--cpq-space-4); border-radius: var(--cpq-radius-full); cursor: pointer;
  font-family: inherit; font-size: var(--cpq-font-size-sm);
  border: 1px solid transparent; background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary);
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.tab-chip:hover { color: var(--cpq-text-primary); }
.tab-chip.on { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-weight: var(--cpq-font-weight-medium); }
.tab-chip.warn.on { background: var(--cpq-notif-amber); }
.tab-chip .n { opacity: 0.65; margin-left: var(--cpq-space-1); }
.ap-search {
  margin-left: auto; width: 240px; padding: var(--cpq-space-1) var(--cpq-space-3);
  font-family: inherit; font-size: var(--cpq-font-size-sm);
  border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md);
  background: var(--cpq-bg-input); color: var(--cpq-text-primary); outline: none;
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.ap-search:focus { border-color: var(--cpq-accent-primary); }

/* 表格卡 */
.ap-card {
  background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-xl); backdrop-filter: blur(var(--cpq-glass-card-blur, 18px));
  box-shadow: var(--cpq-glass-card-shadow); overflow: hidden;
}
.table-scroll { overflow-x: auto; }
.ap-table { width: 100%; border-collapse: collapse; font-size: var(--cpq-font-size-sm); }
.ap-table th {
  text-align: left; padding: var(--cpq-space-3) var(--cpq-space-3); font-size: var(--cpq-font-size-xs); font-weight: var(--cpq-font-weight-medium);
  color: var(--cpq-text-secondary); background: var(--cpq-overlay-w4);
  border-bottom: 1px solid var(--cpq-border-primary); white-space: nowrap;
}
.ap-table td { padding: var(--cpq-space-3) var(--cpq-space-3); border-bottom: 1px solid var(--cpq-border-secondary); color: var(--cpq-text-primary); }
.ap-table tbody tr { cursor: pointer; transition: background var(--cpq-dur-1) var(--cpq-ease-smooth); }
.ap-table tbody tr:hover td { background: var(--cpq-overlay-w3); }
.ap-table tbody tr:last-child td { border-bottom: none; }
.ta-r { text-align: right; }
.cell-main { font-weight: var(--cpq-font-weight-medium); }
.cell-link { color: var(--cpq-text-primary); font-weight: var(--cpq-font-weight-medium); cursor: pointer; text-decoration: none; }
.cell-link:hover { color: var(--cpq-accent-primary); }
.cell-sub { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); margin-top: 2px; }
.mono { font-family: var(--cpq-font-family); font-variant-numeric: tabular-nums; }
.margin-low { color: var(--cpq-notif-amber); font-weight: var(--cpq-font-weight-medium); }
.low-tag { margin-left: var(--cpq-space-1); font-size: var(--cpq-font-size-xs); }
.wait-hot { color: var(--cpq-accent-danger); font-weight: var(--cpq-font-weight-semibold); }
.pill { display: inline-block; padding: 2px var(--cpq-space-2); border-radius: var(--cpq-radius-full); font-size: var(--cpq-font-size-xs); white-space: nowrap; }
.pill.pending { background: var(--cpq-notif-amber-bg); color: var(--cpq-notif-amber); }
.pill.escalated { background: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.pill.approved { background: var(--cpq-notif-green-bg); color: var(--cpq-notif-green); }
.pill.rejected { background: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.ap-empty { text-align: center; color: var(--cpq-text-muted); padding: var(--cpq-space-5) var(--cpq-space-2) !important; cursor: default; }
.op-row { display: flex; gap: var(--cpq-space-1); justify-content: flex-end; }
.op-btn {
  padding: 4px var(--cpq-space-3); border-radius: var(--cpq-radius-md); cursor: pointer; font-family: inherit;
  font-size: var(--cpq-font-size-xs);
  border: 1px solid var(--cpq-border-primary); background: transparent; color: var(--cpq-text-secondary);
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.op-btn:hover:not(:disabled) { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
.op-btn.go { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-weight: var(--cpq-font-weight-medium); }
.op-btn.no { border-color: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.op-btn.no:hover:not(:disabled) { background: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }

/* 详情抽屉 */
.mask { position: fixed; inset: 0; z-index: 500; background: var(--cpq-overlay-b40); opacity: 0; pointer-events: none; transition: opacity var(--cpq-dur-2) var(--cpq-ease-smooth); }
.mask.on { opacity: 1; pointer-events: auto; }
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 501; width: 460px; max-width: 92vw;
  background: var(--cpq-glass-3-bg-solid); backdrop-filter: blur(var(--cpq-glass-blur-3));
  border-left: 1px solid var(--cpq-glass-border);
  transform: translateX(102%); transition: transform var(--cpq-dur-2) var(--cpq-ease-out-expo);
  display: flex; flex-direction: column;
}
.drawer.on { transform: translateX(0); }
.drawer-head { display: flex; align-items: center; gap: var(--cpq-space-3); padding: var(--cpq-space-5) var(--cpq-space-5) var(--cpq-space-4); }
.drawer-head h2 { margin: 0; font-size: var(--cpq-font-size-xl); font-weight: var(--cpq-font-weight-semibold); line-height: var(--cpq-line-height-heading); }
.drawer-sub { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); margin-top: 2px; }
.drawer-close {
  margin-left: auto; width: var(--cpq-space-6); height: var(--cpq-space-6); border-radius: var(--cpq-radius-full);
  border: 1px solid var(--cpq-border-primary); background: transparent; color: var(--cpq-text-secondary);
  cursor: pointer; font-size: var(--cpq-font-size-base); font-family: inherit;
}
.drawer-close:hover { color: var(--cpq-text-primary); }
.drawer-body { flex: 1; overflow-y: auto; padding: 0 var(--cpq-space-5) var(--cpq-space-5); }
.note-block {
  padding: var(--cpq-space-3) var(--cpq-space-4); margin-bottom: var(--cpq-space-4);
  background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-border-secondary); border-radius: var(--cpq-radius-md);
  font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary);
}
.d-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cpq-space-3) var(--cpq-space-4); margin-bottom: var(--cpq-space-4); }
.d-item .k { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.d-item .v { font-size: var(--cpq-font-size-sm); font-weight: var(--cpq-font-weight-medium); margin-top: 2px; }
.d-item .v.plain { font-weight: var(--cpq-font-weight-normal); }
.margin-track { margin-bottom: var(--cpq-space-4); }
.margin-track .bar { height: 6px; border-radius: var(--cpq-radius-full); background: var(--cpq-overlay-w6); position: relative; overflow: visible; }
.margin-track .bar i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: var(--cpq-radius-full); transition: width var(--cpq-dur-2) var(--cpq-ease-out-expo); }
.margin-track .bar em { position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--cpq-accent-danger); border-radius: var(--cpq-radius-xs); }
.margin-track .lab { display: flex; justify-content: space-between; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); margin-top: var(--cpq-space-1); }
.lab-mark { color: var(--cpq-accent-danger); }
.hash-line { display: flex; align-items: center; gap: var(--cpq-space-2); font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary); margin-bottom: var(--cpq-space-4); }
.hash-line code {
  font-family: var(--cpq-font-family); font-variant-numeric: tabular-nums;
  background: var(--cpq-overlay-a5); padding: 2px var(--cpq-space-2); border-radius: var(--cpq-radius-sm);
}
.decide-note {
  width: 100%; padding: var(--cpq-space-2) var(--cpq-space-3); margin-bottom: var(--cpq-space-3);
  font-family: inherit; font-size: var(--cpq-font-size-sm);
  border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md);
  background: var(--cpq-bg-input); color: var(--cpq-text-primary); outline: none;
}
.decide-note:focus { border-color: var(--cpq-accent-primary); }
.d-ops { display: flex; gap: var(--cpq-space-2); }
.btn {
  padding: var(--cpq-space-2) var(--cpq-space-4); border-radius: var(--cpq-radius-md); cursor: pointer;
  font-family: inherit; font-size: var(--cpq-font-size-sm);
  border: 1px solid var(--cpq-border-primary); background: transparent; color: var(--cpq-text-secondary);
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.btn.primary { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-weight: var(--cpq-font-weight-medium); }
.btn.primary:hover { filter: brightness(1.08); }
.btn.no { border-color: var(--cpq-notif-red-bg); color: var(--cpq-notif-red); }
.btn.no:hover { background: var(--cpq-notif-red-bg); }
.gate-note { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); margin-top: var(--cpq-space-3); line-height: var(--cpq-line-height-body); }
.verdict-block {
  padding: var(--cpq-space-3) var(--cpq-space-4); border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-border-secondary);
  font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary);
}
.reject-tip { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); margin-bottom: var(--cpq-space-3); }

@media (max-width: 768px) {
  .ap-head { flex-direction: column; }
  .ap-stats { width: 100%; }
  .stat { flex: 1; padding: var(--cpq-space-2) var(--cpq-space-2); }
  .ap-search { margin-left: 0; width: 100%; }
}
</style>
