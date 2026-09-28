<template>
  <a-table
    :dataSource="rows"
    :columns="columns"
    :pagination="pagination"
    :loading="loading"
    size="small"
    class="opp-table"
    rowKey="opportunity_id"
    :rowSelection="selectable ? rowSelectionCfg : undefined"
    :scroll="{ x: scrollX }"
    @change="onChange"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.dataIndex === 'customer_name'">
        <div class="cell-customer">
          <div class="name-row">
            <a class="opp-name" @click="goDetail(record.opportunity_id)">{{ record.customer_name || '未命名客户' }}</a>
            <a-dropdown v-if="statusEditable" :trigger="['click']" placement="bottomLeft">
              <a-tag :color="resultTagColor(record)" class="opp-status-pick">{{ resultLabel(record.result) }}<span class="opp-caret">▾</span></a-tag>
              <template #overlay>
                <a-menu @click="(e: any) => emit('result-change', record, e.key)">
                  <a-menu-item v-for="o in RESULT_OPTIONS" :key="o.value">
                    <span :style="{ display:'inline-block', width:'7px', height:'7px', borderRadius:'50%', marginRight:'7px', verticalAlign:'middle', background: o.dot }"></span><span :style="{ fontWeight: o.value === record.result ? 600 : 400 }">{{ o.label }}</span>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
            <a-tag v-else :color="resultTagColor(record)">{{ resultLabel(record.result) }}</a-tag>
          </div>
          <div v-if="oppMetaLine(record)" class="opp-meta">{{ oppMetaLine(record) }}</div>
        </div>
      </template>
      <template v-else-if="column.key === 'platform'">
        <span class="cell-plat">{{ record.platform_type || '—' }}</span>
      </template>
      <template v-else-if="column.key === 'chassis'">
        <span class="cell-plat">{{ record.chassis_form || '—' }}</span>
      </template>
      <template v-else-if="column.dataIndex === 'sales_person'">
        <span class="cell-plat">{{ record.sales_person || '—' }}</span>
      </template>
      <template v-else-if="column.dataIndex === 'purchase_qty'">
        <span class="cell-num"><b>{{ record.purchase_qty || 0 }}</b><i>台</i></span>
      </template>
      <template v-else-if="column.dataIndex === 'config_count'">
        <span class="cell-num"><b>{{ record.config_count ?? 0 }}</b><i>套</i></span>
      </template>
      <template v-else-if="column.key === 'flow_node'">
        <span class="pill" :class="flowPillClass(record)">{{ flowNodeLabel(record) }}</span>
      </template>
      <template v-else-if="column.dataIndex === 'created_at'">
        <div class="cell-dt">
          <span class="dt-main">{{ fmtDateTime(record.created_at) }}</span>
          <span class="dt-rel">{{ relTime(record.created_at) }}</span>
        </div>
      </template>
      <template v-else-if="column.dataIndex === 'updated_at'">
        <div class="cell-dt">
          <span class="dt-main">{{ fmtDateTime(record.updated_at) }}</span>
          <span class="dt-rel">{{ relTime(record.updated_at) }}</span>
        </div>
      </template>
      <template v-else-if="column.key === 'part_hits'">
        <div v-if="record.part_hits?.length" class="hits">
          <span v-for="(h, i) in record.part_hits" :key="i" class="hit-badge" :title="`${h.date}${h.cfg ? ' · ' + h.cfg : ''}`">
            <i class="hd">{{ h.date }}</i><i v-if="h.cfg" class="hc">{{ h.cfg }}</i>{{ h.parts.map((p: any) => `${p.name} ×${p.qty}`).join(' · ') }}
          </span>
        </div>
        <span v-else class="hits-empty">—</span>
      </template>
      <template v-else-if="column.key === 'actions'">
        <a-dropdown :trigger="['click']" placement="bottomRight">
          <button class="row-more"><MoreOutlined /></button>
          <template #overlay>
            <a-menu @click="(e: any) => emit('row-menu', e.key, record)">
              <template v-for="item in effectiveMenu" :key="item.key || 'div'">
                <a-menu-divider v-if="item.divider" />
                <a-menu-item v-else :key="item.key" :danger="item.danger">{{ item.label }}</a-menu-item>
              </template>
            </a-menu>
          </template>
        </a-dropdown>
      </template>
    </template>
  </a-table>

  <!-- 批量操作浮条（selectable 开启时）：批量移至回收站 -->
  <Transition name="batch-fade">
    <div v-if="selectable && selectedRowKeys.length" class="batch-float glass-strong">
      <span class="batch-count">已选 <b>{{ selectedRowKeys.length }}</b> 项</span>
      <button class="batch-btn danger" :disabled="batching" @click="onBatchTrash">移至回收站</button>
      <button class="batch-btn" @click="selectedRowKeys = []">取消</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
/**
 * 商机线索表（公共组件）：从商机线索页右栏表格抽出。
 * 含多选 + 批量移至回收站浮条（selectable 开）、状态 tag 下拉、流程节点列、行菜单。
 * 只管呈现与批量回收站这一统一动作；数据加载/分页/筛选留在各页面。
 * 消费方：商机线索页、门户工作台四子页（我的商机 / 技术支持 / 成本核算 / 报价专员）。
 * 点行内客户名进商机详情页。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import axios from 'axios'
import { MoreOutlined } from '@ant-design/icons-vue'
import { RESULT_OPTIONS, resultLabel, resultTagColor } from '@/constants/opportunityResult'

const props = withDefaults(defineProps<{
  rows: any[]
  loading?: boolean
  pagination?: object | false
  /** 商机状态 tag 是否可下拉修改（业务/报价员/管理员；te/cost 只读） */
  statusEditable?: boolean
  /** 是否显示「流程节点」列（门户工作台用；线索页不开） */
  showFlowNode?: boolean
  /** 是否显示行菜单——数据归属者页面才开 */
  rowMenu?: boolean
  /** 行菜单形态：owner=打开/重命名/移至回收站（商机归属页）；task=打开/转交（节点任务页） */
  menuMode?: 'owner' | 'task'
  /** 是否开启复选框（线索页批量操作用） */
  selectable?: boolean
  /** 是否显示「命中配件」列（商机线索页配件筛选开启时） */
  showPartHits?: boolean
  /** 时间列是否可排序（节点任务模式后端恒按流程更新时间倒序，排序无效 → 关掉箭头） */
  sortable?: boolean
  /** 点行进详情携带的 from 参数（返回时回对应工作台） */
  fromTag?: string
  scrollX?: number
}>(), {
  loading: false,
  pagination: false,
  statusEditable: false,
  showFlowNode: false,
  showPartHits: false,
  rowMenu: false,
  menuMode: 'owner',
  selectable: false,
  sortable: true,
  fromTag: '',
  scrollX: 860,
})

const emit = defineEmits<{
  (e: 'change', pag: any, filters: any, sorter: any): void
  (e: 'result-change', record: any, val: string): void
  (e: 'row-menu', key: string, record: any): void
  (e: 'batch-trashed', keys: string[]): void
}>()

const router = useRouter()

const columns = computed(() => {
  const cols: any[] = [
    { title: '客户 / 状态', dataIndex: 'customer_name', key: 'customer' },
    { title: '业务', dataIndex: 'sales_person', width: 100, ellipsis: true },
    { title: '平台', dataIndex: 'platform_type', key: 'platform', width: 96 },
    { title: '形态', dataIndex: 'chassis_form', key: 'chassis', width: 84 },
    { title: '数量', dataIndex: 'purchase_qty', width: 80 },
    { title: '配置', dataIndex: 'config_count', width: 72 },
  ]
  if (props.showFlowNode) cols.push({ title: '流程节点', key: 'flow_node', width: 104 })
  if (props.showPartHits) cols.push({ title: '命中配件', key: 'part_hits', width: 240 })
  cols.push(
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 116, sorter: props.sortable || undefined },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 116, sorter: props.sortable || undefined, defaultSortOrder: (props.sortable ? 'descend' : undefined) as any },
  )
  if (props.rowMenu) cols.push({ title: '', key: 'actions', width: 60, align: 'center' as const })
  return cols
})

function onChange(pag: any, filters: any, sorter: any) {
  emit('change', pag, filters, sorter)
}

type RowMenuItem = { key?: string; label?: string; danger?: boolean; divider?: boolean }
const OWNER_MENU: RowMenuItem[] = [
  { key: 'open', label: '打开' },
  { key: 'rename', label: '重命名' },
  { divider: true },
  { key: 'trash', label: '移至回收站', danger: true },
]
const TASK_MENU: RowMenuItem[] = [
  { key: 'open', label: '打开' },
  { key: 'transfer', label: '转交' },
]
const effectiveMenu = computed(() => (props.menuMode === 'task' ? TASK_MENU : OWNER_MENU))

const rowSelectionCfg = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: any[]) => { selectedRowKeys.value = keys as string[] },
}))

// 批量移至回收站：统一动作收在组件内，各页面只负责收 batch-trashed 后刷新列表
const selectedRowKeys = ref<string[]>([])
const batching = ref(false)
// 列表换页/刷新后清掉不在当前页的选中（沿用线索页旧口径：每次加载重置选择）
watch(() => props.rows, (rows) => {
  const live = new Set((rows || []).map((r: any) => r.opportunity_id))
  selectedRowKeys.value = selectedRowKeys.value.filter(k => live.has(k))
})
async function onBatchTrash() {
  if (!selectedRowKeys.value.length || batching.value) return
  batching.value = true
  try {
    const res = await axios.post('/api/opportunities/batch-trash', { opportunity_ids: selectedRowKeys.value })
    // 后端逐项校验权限，部分失败仍 200：按 success/failed 分别提示
    const failed: any[] = res.data?.failed || []
    const okCount = (res.data?.success || []).length
    if (failed.length) {
      message.warning(`已移 ${okCount} 项；${failed.length} 项失败（无权限或已不存在）`)
    } else {
      message.success(`已将 ${okCount} 项移至回收站`)
    }
    const keys = selectedRowKeys.value
    selectedRowKeys.value = []
    emit('batch-trashed', keys)
  } catch {
    message.error('批量移至回收站失败')
  } finally {
    batching.value = false
  }
}

function goDetail(id: string) {
  if (props.fromTag) router.push({ path: `/opportunities/${id}`, query: { from: props.fromTag } })
  else router.push(`/opportunities/${id}`)
}

// 客户单元格第二行元信息：行业 · 订单类型 · 报价份数
function oppMetaLine(r: any) {
  const parts: string[] = []
  if (r.industry) parts.push(r.industry)
  if (r.order_type) parts.push(r.order_type)
  if (r.quotation_count > 0) parts.push(`${r.quotation_count} 份报价`)
  return parts.join(' · ')
}

// 时间：同年显示 MM-DD HH:mm，跨年带年份；第二行相对时间
function fmtDateTime(s: string) {
  if (!s) return '-'
  const now = new Date()
  const sameYear = Number(s.slice(0, 4)) === now.getFullYear()
  return sameYear ? s.slice(5, 16) : s.slice(0, 10)
}
function relTime(s: string) {
  if (!s) return ''
  const t = new Date(s.replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  const m = Math.floor(diff / 60_000)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d} 天前`
  if (d < 30) return `${Math.floor(d / 7)} 周前`
  return `${Math.floor(d / 30)} 个月前`
}

// 流程节点列（门户工作台）：节点名 + 状态 pill（退回红 / 定稿绿 / 待处理琥珀）
const FLOW_NODE_LABELS: Record<string, string> = {
  requirement: '需求单', assign: '指派', boming: '方案配置',
  costing: '成本核算', quoting: '报价单', done: '已定稿',
}
function flowNodeLabel(r: any) {
  if (r?.flow_status === 'done') return '已定稿'
  return FLOW_NODE_LABELS[r?.current_node] || r?.current_node || '—'
}
function flowPillClass(r: any) {
  if (r?.flow_status === 'done') return 'green'
  if (r?.flow_status === 'returned') return 'red'
  if (r?.current_node === 'boming') return 'amber'
  return ''
}
</script>

<style scoped>
.cell-customer { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name-row { display: flex; align-items: center; gap: 10px; min-width: 0; flex-wrap: wrap; }
.opp-name { color: var(--cpq-text-primary); font-size: 13.5px; font-weight: 500; cursor: pointer; text-decoration: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.opp-name:hover { color: var(--cpq-accent-primary); }
.opp-meta { font-size: 11px; color: var(--cpq-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 380px; }
.opp-status-pick { cursor: pointer; user-select: none; margin-right: 0 !important; transition: filter var(--cpq-dur-1) var(--cpq-ease-smooth); }
.opp-status-pick:hover { filter: brightness(1.06); }
.opp-caret { font-size: 9px; margin-left: 3px; opacity: 0.7; }
.cell-plat { font-size: 12.5px; color: var(--cpq-text-primary); white-space: nowrap; }
.cell-num { display: inline-flex; align-items: baseline; gap: 3px; }
.cell-num b { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); font-variant-numeric: tabular-nums; }
.cell-num i { font-style: normal; font-size: 11px; color: var(--cpq-text-muted); }
.cell-dt { display: flex; flex-direction: column; gap: 1px; }
.dt-main { font-size: 12px; color: var(--cpq-text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.dt-rel { font-size: 10.5px; color: var(--cpq-text-muted); white-space: nowrap; }
.row-more {
  display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
  border: none; background: transparent; color: var(--cpq-text-muted); border-radius: 6px; cursor: pointer; font-size: 14px;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.row-more:hover { background: var(--cpq-overlay-w8); color: var(--cpq-text-primary); }

/* 流程节点 pill（对齐门户工作台原有样式） */
.pill { display: inline-block; padding: 3px 9px; border-radius: 999px; background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); font-size: 12px; white-space: nowrap; }
.pill.amber { background: rgba(217, 119, 6, .14); color: #d97706; }
.pill.green { background: rgba(22, 163, 74, .14); color: #16a34a; }
.pill.red { background: rgba(220, 38, 38, .12); color: #dc2626; }

/* 命中配件徽标：报价日期 + 配置页签 + 型号×数量（后端红线：不带 PN/价格） */
.hits { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.hit-badge {
  display: inline-flex; align-items: center; gap: 6px; max-width: 100%; white-space: nowrap;
  font-size: 11px; color: var(--cpq-text-primary); background: rgba(22, 119, 255, .08);
  border: 1px solid rgba(22, 119, 255, .28); border-radius: 6px; padding: 1px 8px;
  overflow: hidden; text-overflow: ellipsis;
}
.hit-badge .hd { font-style: normal; font-size: 10px; color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.hit-badge .hc { font-style: normal; color: var(--cpq-accent-primary); font-weight: 600; max-width: 90px; overflow: hidden; text-overflow: ellipsis; }
.hits-empty { font-size: 11px; color: var(--cpq-text-muted); }

/* 批量操作浮条（从商机线索页迁入，样式口径不变） */
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
</style>
