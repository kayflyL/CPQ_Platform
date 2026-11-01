<script setup lang="ts">
/** 线索池（/leads）—— 公开渠道汇聚线索的列表页：筛选 + 点击进线索详情页（操作在详情页）。 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { leadsApi, type LeadRecord } from '@/api/leads'

const router = useRouter()

const STATUS_TABS = [
  { value: '', label: '全部' },
  { value: 'new', label: '待处理' },
  { value: 'confirmed', label: '已确认' },
  { value: 'assigned', label: '已转化' },
  { value: 'rejected', label: '已驳回' },
  { value: 'deleted', label: '已删除' },
]
const SOURCE_LABEL: Record<string, string> = { catalog_model: '配置完成页', catalog_general: '登记表' }
const statusFilter = ref('')
const search = ref('')
const rows = ref<LeadRecord[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await leadsApi.list({ status: statusFilter.value, search: search.value, page: 1, page_size: 100 })
    rows.value = res.items
    total.value = res.total
  } catch { /* 列表加载失败不阻塞 */ } finally { loading.value = false }
}

const pendingCount = computed(() => rows.value.filter(r => r.status === 'new').length)
const statusMeta = (s: string) => ({
  new: { label: '新线索', cls: 's-new' },
  confirmed: { label: '已确认', cls: 's-confirmed' },
  converting: { label: '转化中', cls: 's-screening' },
  assigned: { label: '已转化', cls: 's-assigned' },
  rejected: { label: '已驳回', cls: 's-rejected' },
  deleted: { label: '已删除', cls: 's-deleted' },
} as Record<string, { label: string; cls: string }>)[s] || { label: s, cls: 's-new' }

function fmtTime(iso?: string) {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(5, 16)
}
function openLead(r: LeadRecord) {
  router.push(`/leads/${r.lead_id}`)
}

// —— 移动端 ——
const isMobile = ref(false)
let mqListener: ((e: MediaQueryListEvent) => void) | null = null
onMounted(() => {
  load()
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
  const mq = window.matchMedia('(max-width: 768px)')
  mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', mqListener)
})
onBeforeUnmount(() => {
  if (mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', mqListener)
})
</script>

<template>
  <div class="lead-pool">
    <header class="lp-head">
      <div>
        <h1>线索池</h1>
        <div class="lp-desc">公开渠道汇聚的线索 · 一期人工筛选 · 点击线索进详情核验与转化</div>
      </div>
      <div class="lp-stats">
        <div class="stat warn"><b>{{ pendingCount }}</b><span>待处理</span></div>
        <div class="stat"><b>{{ total }}</b><span>全部线索</span></div>
      </div>
    </header>

    <div class="lp-filter">
      <button v-for="t in STATUS_TABS" :key="t.value" class="tab-chip" :class="{ on: statusFilter === t.value }"
              @click="statusFilter = t.value; load()">{{ t.label }}</button>
      <input v-model="search" class="lp-search" placeholder="搜索公司 / 联系人 / 手机号" @input="load()">
    </div>

    <!-- 桌面表格 -->
    <div v-if="!isMobile" class="lp-table-card">
      <table class="lp-table">
        <thead>
          <tr>
            <th>公司 / 联系人</th>
            <th>需求摘要</th>
            <th style="width:170px">来源 / 时间</th>
            <th style="width:110px">状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.lead_id" @click="openLead(r)">
            <td>
              <div class="cell-main">{{ r.company || '（未留公司）' }}<span v-if="r.dedup_count > 1" class="dedup">×{{ r.dedup_count }} 并入</span></div>
              <div class="cell-sub">{{ r.contact_name || '—' }} · {{ r.contact_phone }}</div>
            </td>
            <td><div class="req-clip">{{ r.requirement_text }}</div></td>
            <td><span class="mono">{{ SOURCE_LABEL[r.source] || r.source }}<br>{{ fmtTime(r.created_at) }}</span></td>
            <td><span class="status-chip" :class="statusMeta(r.status).cls">{{ statusMeta(r.status).label }}</span></td>
          </tr>
          <tr v-if="!rows.length && !loading">
            <td colspan="4" class="lp-empty">暂无线索</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 移动端卡片 -->
    <div v-else class="lp-cards">
      <div v-for="r in rows" :key="r.lead_id" class="lp-card" @click="openLead(r)">
        <div class="row1"><b>{{ r.company || '（未留公司）' }}</b><span class="time">{{ fmtTime(r.created_at) }}</span></div>
        <div class="row2">{{ r.requirement_text }}</div>
        <div class="row2"><span class="status-chip" :class="statusMeta(r.status).cls">{{ statusMeta(r.status).label }}</span></div>
      </div>
      <div v-if="!rows.length" class="lp-empty">暂无线索</div>
    </div>
  </div>
</template>

<style scoped>
.lead-pool { padding: 20px 24px 48px; max-width: 1280px; margin: 0 auto; }
.lp-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.lp-head h1 { margin: 0; font-size: var(--cpq-font-size-2xl); font-weight: 700; line-height: var(--cpq-line-height-heading); }
.lp-desc { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); margin-top: 4px; }
.lp-stats { display: flex; gap: 8px; }
.stat {
  display: flex; flex-direction: column; align-items: center; padding: 8px 18px;
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
}
.stat b { font-family: var(--cpq-font-family); font-size: var(--cpq-font-size-xl); font-variant-numeric: tabular-nums; }
.stat span { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.stat.warn b { color: #d48806; }

.lp-filter { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.tab-chip {
  padding: 5px 14px; border-radius: var(--cpq-radius-full); cursor: pointer;
  font-size: var(--cpq-font-size-sm); font-family: inherit;
  border: 1px solid transparent; background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary);
}
.tab-chip:hover { color: var(--cpq-text-primary); }
.tab-chip.on { background: var(--cpq-accent-primary); color: #fff; font-weight: 600; }
.lp-search {
  margin-left: auto; width: 240px; padding: 6px 12px; font-size: var(--cpq-font-size-sm); font-family: inherit;
  border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md);
  background: var(--cpq-bg-input); color: var(--cpq-text-primary); outline: none;
}
.lp-search:focus { border-color: var(--cpq-accent-primary); }

.lp-table-card {
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-xl);
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow); overflow: hidden;
}
.lp-table { width: 100%; border-collapse: collapse; font-size: var(--cpq-font-size-sm); }
.lp-table thead th {
  text-align: left; padding: 10px 14px; font-size: var(--cpq-font-size-xs); font-weight: 600;
  color: var(--cpq-text-secondary); background: var(--cpq-overlay-w4); border-bottom: 1px solid var(--cpq-border-secondary);
  white-space: nowrap;
}
.lp-table tbody td { padding: 11px 14px; border-bottom: 1px solid var(--cpq-border-secondary); }
.lp-table tbody tr { cursor: pointer; transition: background 0.15s; }
.lp-table tbody tr:hover { background: var(--cpq-overlay-w6); }
.lp-table tbody tr:last-child td { border-bottom: none; }
.cell-main { font-weight: 600; color: var(--cpq-text-primary); }
.cell-sub { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); margin-top: 2px; }
.dedup {
  display: inline-block; margin-left: 6px; padding: 0 7px; font-size: var(--cpq-font-size-xs); font-weight: 600;
  color: var(--cpq-notif-violet); background: var(--cpq-notif-violet-bg);
  border: 1px solid color-mix(in srgb, var(--cpq-notif-violet) 30%, transparent); border-radius: var(--cpq-radius-full);
}
.req-clip { max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--cpq-text-secondary); }
.mono { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); font-variant-numeric: tabular-nums; }
.lp-empty { text-align: center; color: var(--cpq-text-muted); padding: 40px 0; }

.status-chip {
  display: inline-block; padding: 2px 10px; font-size: var(--cpq-font-size-xs); font-weight: 600;
  border-radius: var(--cpq-radius-full); border: 1px solid transparent; white-space: nowrap;
}
.s-new { color: var(--cpq-notif-blue); background: var(--cpq-notif-blue-bg); border-color: color-mix(in srgb, var(--cpq-notif-blue) 30%, transparent); }
.s-screening { color: var(--cpq-notif-cyan); background: var(--cpq-notif-cyan-bg); border-color: color-mix(in srgb, var(--cpq-notif-cyan) 30%, transparent); }
.s-confirmed { color: var(--cpq-notif-green); background: var(--cpq-notif-green-bg); border-color: color-mix(in srgb, var(--cpq-notif-green) 35%, transparent); }
.s-assigned { color: #fff; background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.s-rejected { color: var(--cpq-notif-red); background: var(--cpq-notif-red-bg); border-color: color-mix(in srgb, var(--cpq-notif-red) 30%, transparent); }
.s-deleted { color: var(--cpq-text-muted); background: var(--cpq-overlay-w4); border-color: var(--cpq-border-secondary); }

/* 移动端 */
.lp-cards { display: flex; flex-direction: column; gap: 10px; }
.lp-card {
  padding: 12px 14px; border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border);
  box-shadow: var(--cpq-glass-card-shadow);
}
.lp-card .row1 { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.lp-card .row1 b { font-size: var(--cpq-font-size-base); }
.lp-card .time { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.lp-card .row2 { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); margin-top: 6px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
@media (max-width: 768px) {
  .lead-pool { padding: 14px 12px 40px; }
  .lp-search { margin-left: 0; width: 100%; }
}
</style>
