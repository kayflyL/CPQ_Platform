<script setup lang="ts">
/** 基准配置编辑器 · 成本分析右侧栏（四卡）。
 *  口径 = 裸机成本四块：底盘件(lines) + 后面板默认卡(每槽1套,PN与底盘件去重) + 前面板默认线缆(每盘类1根)
 *  + 默认PSU×psu_bays(满配预估)。缺价件不计入合计、显式计数（合计为下限值）——价格覆盖率探针。
 *  卡1~3 编辑实时 computed；卡4 机型对比走 /api/base-configs/cost-analysis 已保存值。纯 CSS 条，无图表库。 */
import { computed, onMounted, ref } from 'vue'
import { baseConfigApi, type BaseConfigCost, type PartMaster } from '@/api/serverConfig'

const props = defineProps<{
  parts: PartMaster[]
  lines: { pn: string; qty: number }[]
  rearSlots: { name?: string; defaults?: string[] }[]
  frontCables: Record<string, string>
  defaultPsuPn: string
  psuBays: number
  editingId: number | null
  groups: readonly { n: number; title: string }[]
}>()

/** KP 配置件所在的解剖分组（内存条配置页选、不进基准成本；灰显提示口径而非留白让人误以为漏算） */
const KP_ONLY_GROUPS = ['内存']

const partByPn = computed(() => {
  const m: Record<string, PartMaster> = {}
  for (const p of props.parts) if (p.pn) m[p.pn] = p
  return m
})

type Src = 'chassis' | 'rear' | 'cable' | 'psu'
interface CostRow {
  pn: string; name: string; qty: number
  unit: number | null          // null = 缺价（不计入）
  amount: number
  group: string                // 解剖分组标题（rear/cable/psu 按功能归组）
  src: Src
}
const SRC_GROUP: Record<Src, string> = { chassis: '', rear: '后面板', cable: '前面板', psu: '供电' }

const rows = computed<CostRow[]>(() => {
  const out: CostRow[] = []
  const seen = new Set<string>()
  const groupOf = (major?: string | null) =>
    props.groups.find(g => g.title === major)?.title || major || '未分组'
  for (const l of props.lines) {
    if (!l.pn || seen.has(l.pn)) continue
    seen.add(l.pn)
    const p = partByPn.value[l.pn]
    const qty = Number(l.qty) || 0
    const unit = p?.unit_price ?? null
    out.push({ pn: l.pn, name: p?.name || l.pn, qty, unit, amount: unit != null ? unit * qty : 0, group: groupOf(p?.major_category), src: 'chassis' })
  }
  const pushRef = (pn: string, src: Src, nameFallback?: string, qty = 1) => {
    if (!pn || seen.has(pn)) return
    seen.add(pn)
    const p = partByPn.value[pn]
    const unit = p?.unit_price ?? null
    out.push({ pn, name: p?.name || nameFallback || pn, qty, unit, amount: unit != null ? unit * qty : 0, group: SRC_GROUP[src], src })
  }
  for (const s of props.rearSlots || [])
    for (const pn of s?.defaults || []) pushRef(String(pn), 'rear')
  for (const [kind, pn] of Object.entries(props.frontCables || {})) pushRef(String(pn), 'cable', `${kind} 线缆`)
  if (props.defaultPsuPn) pushRef(String(props.defaultPsuPn), 'psu', undefined, Math.max(0, Number(props.psuBays) || 0))
  return out
})

const total = computed(() => rows.value.reduce((s, r) => s + r.amount, 0))
const missingRows = computed(() => rows.value.filter(r => r.unit == null))
const partsCount = computed(() => rows.value.reduce((s, r) => s + r.qty, 0))
const tdp = computed(() =>
  rows.value.filter(r => r.src === 'chassis').reduce((s, r) => {
    const p = partByPn.value[r.pn]
    const t = Number(p?.specs?.tdp) || Number(p?.specs?.power) || 0
    return s + t * r.qty
  }, 0))

const bySource = computed(() => {
  const b = { chassis: 0, rear: 0, cables: 0, psu: 0 } as Record<Src | 'cables', number>
  for (const r of rows.value) b[r.src === 'cable' ? 'cables' : r.src] += r.amount
  return b
})
const SRC_META: { key: 'chassis' | 'psu' | 'rear' | 'cables'; label: string; color: string }[] = [
  { key: 'chassis', label: '底盘件', color: 'linear-gradient(90deg,#1677FF,#4096ff)' },
  { key: 'psu', label: 'PSU×槽位', color: '#5B8FF9' },
  { key: 'rear', label: '后板默认卡', color: '#85B0FA' },
  { key: 'cables', label: '线缆', color: '#B9CFFB' },
]
const srcPct = (key: string) => total.value > 0 ? (bySource.value[key as keyof typeof bySource.value] / total.value) * 100 : 0

const byGroup = computed(() => {
  const m = new Map<string, { amount: number; missing: number }>()
  for (const r of rows.value) {
    const g = m.get(r.group) || { amount: 0, missing: 0 }
    g.amount += r.amount
    if (r.unit == null) g.missing += 1
    m.set(r.group, g)
  }
  const data = [...m.entries()]
    .map(([title, v]) => ({ title, ...v, n: props.groups.find(g => g.title === title)?.n }))
    .filter(g => g.amount > 0 || g.missing > 0)
    .sort((a, b) => b.amount - a.amount)
  const max = Math.max(1, ...data.map(g => g.amount))
  return { data, max }
})

const topRows = computed(() => {
  const priced = rows.value.filter(r => r.unit != null).sort((a, b) => b.amount - a.amount)
  let cum = 0
  return priced.slice(0, 8).map((r, i) => {
    cum += r.amount
    return { ...r, rank: i + 1, pct: total.value > 0 ? (r.amount / total.value) * 100 : 0, cumPct: total.value > 0 ? (cum / total.value) * 100 : 0 }
  })
})
/** 二八结论：最贵的前 N 件占合计的百分比（N=累计到 80% 为止） */
const pareto = computed(() => {
  const priced = rows.value.filter(r => r.unit != null).sort((a, b) => b.amount - a.amount)
  let cum = 0
  for (let i = 0; i < priced.length; i++) {
    cum += priced[i].amount
    const pct = total.value > 0 ? cum / total.value : 0
    if (pct >= 0.8 || i === priced.length - 1) return { n: i + 1, pct: Math.round(pct * 100) }
  }
  return { n: 0, pct: 0 }
})

// ---- 卡4 机型对比（已保存值，后端口径与本面板一致）----
const compare = ref<BaseConfigCost[]>([])
const compareLoading = ref(false)
onMounted(async () => {
  compareLoading.value = true
  try { compare.value = (await baseConfigApi.costAnalysis()).configs || [] }
  catch { compare.value = [] }
  finally { compareLoading.value = false }
})
const compareMax = computed(() => Math.max(1, ...compare.value.map(c => c.total)))
const UNASSIGNED = '未关联机型'
const compareGroups = computed(() => {
  const groups: { name: string; items: BaseConfigCost[] }[] = []
  const idx = new Map<string, typeof groups[number]>()
  for (const c of compare.value) {
    const name = c.model_name || UNASSIGNED
    let g = idx.get(name)
    if (!g) { g = { name, items: [] }; idx.set(name, g); groups.push(g) }
    g.items.push(c)
  }
  for (const g of groups) g.items.sort((a, b) => b.total - a.total)
  const named = groups.filter(g => g.name !== UNASSIGNED)
    .sort((a, b) => Math.max(...b.items.map(i => i.total)) - Math.max(...a.items.map(i => i.total)))
  return [...named, ...groups.filter(g => g.name === UNASSIGNED)]
})

const money = (n: number) => '¥' + Math.round(n).toLocaleString('zh-CN')
</script>

<template>
  <div class="ca-panel">
    <!-- 卡1 成本合计 -->
    <section class="ca-card ca-hero">
      <header class="ca-head"><span class="ca-tag">成本合计</span><span class="ca-sub">裸机口径 · 编辑实时</span></header>
      <div class="ca-total-line">
        <span class="ca-cur">¥</span>
        <span class="ca-total num">{{ Math.round(total).toLocaleString('zh-CN') }}</span>
        <span v-if="missingRows.length" class="ca-badge warn">下限</span>
        <span v-else-if="rows.length" class="ca-badge ok">全件已定价</span>
      </div>
      <div v-if="total > 0" class="ca-strip" aria-hidden="true">
        <i v-for="s in SRC_META" :key="s.key" :style="{ width: srcPct(s.key) + '%', background: s.color }" />
      </div>
      <div v-if="total > 0" class="ca-legend">
        <span v-for="s in SRC_META" :key="s.key"><i class="dot" :style="{ background: s.color }" />{{ s.label }} <b class="num">{{ money(bySource[s.key]) }}</b></span>
      </div>
      <div class="ca-submetrics">
        <div class="ca-subm"><div class="lab">料件数（含默认装配）</div><div class="val num">{{ partsCount }} 件</div></div>
        <div class="ca-subm"><div class="lab">估算功耗</div><div class="val num">≈ {{ tdp }} W</div></div>
      </div>
      <div v-if="missingRows.length" class="ca-miss">
        ⚠ <span><b class="num">{{ missingRows.length }}</b> 项缺价未计入合计：{{ missingRows.slice(0, 3).map(r => r.name).join('、') }}{{ missingRows.length > 3 ? ' 等' : '' }}</span>
      </div>
      <footer class="ca-note">计价基准：料号库单价（实时查询，非快照）。CPU/内存/硬盘盘体/GPU/网卡为 KP 配置件，不在基准成本内。</footer>
    </section>

    <!-- 卡2 成本构成 -->
    <section v-if="byGroup.data.length" class="ca-card">
      <header class="ca-head"><span class="ca-tag">成本构成</span><span class="ca-sub">按整机解剖分组</span></header>
      <div v-for="g in byGroup.data" :key="g.title" class="ca-grp">
        <span class="grp-no" :class="{ ghost: !g.n }">{{ g.n || '·' }}</span>
        <span class="grp-name">{{ g.title }}<span v-if="g.missing" class="grp-miss">{{ g.missing }}缺价</span></span>
        <div class="grp-track"><div class="grp-bar" :style="{ width: (g.amount / byGroup.max * 100) + '%' }" /></div>
        <span class="grp-amt num">{{ money(g.amount) }}</span>
        <span class="grp-pct num">{{ total > 0 ? (g.amount / total * 100).toFixed(1) : 0 }}%</span>
      </div>
      <div v-for="t in KP_ONLY_GROUPS" :key="t">
        <div v-if="groups.some(g => g.title === t) && !byGroup.data.some(g => g.title === t)" class="ca-grp kp">
          <span class="grp-no ghost">{{ groups.find(g => g.title === t)?.n }}</span>
          <span class="grp-name">{{ t }}</span>
          <div class="grp-track kp-track" />
          <span class="grp-amt kp-lab">KP 配置件</span>
          <span />
        </div>
      </div>
    </section>

    <!-- 卡3 Top 成本项 -->
    <section v-if="rows.length" class="ca-card">
      <header class="ca-head"><span class="ca-tag">Top 成本项</span><span class="ca-sub">按金额从高到低</span></header>
      <div v-for="r in topRows" :key="r.pn" class="ca-top">
        <span class="top-rank" :class="{ lead: r.rank === 1 }">{{ r.rank }}</span>
        <div class="top-what">
          <div class="top-name">{{ r.name }}</div>
          <div class="top-meta"><span class="mono">{{ r.pn }}</span><span v-if="r.qty > 1" class="qty">×{{ r.qty }}</span></div>
        </div>
        <div class="top-nums"><span class="top-amt num">{{ money(r.amount) }}</span><span class="top-pct num">占 {{ r.pct.toFixed(1) }}%</span></div>
        <div class="cum-track" title="到这里累计占比"><i :style="{ width: r.cumPct + '%' }" /></div>
      </div>
      <footer v-if="pareto.n" class="ca-note">最贵的 <b>{{ pareto.n }}</b> 件已占合计 <b>{{ pareto.pct }}%</b>，想压成本优先看这几件。</footer>
      <template v-if="missingRows.length">
        <div class="miss-divider">以下缺价 · 未计入</div>
        <div v-for="r in missingRows" :key="r.pn" class="ca-top miss">
          <span class="top-rank">—</span>
          <div class="top-what">
            <div class="top-name">{{ r.name }}</div>
            <div class="top-meta"><span class="mono">{{ r.pn }}</span><span v-if="r.qty > 1" class="qty">×{{ r.qty }}</span></div>
          </div>
          <div class="top-nums"><span class="top-amt miss-amt">缺价</span></div>
          <div />
        </div>
      </template>
    </section>

    <!-- 卡4 机型成本对比 -->
    <section class="ca-card">
      <header class="ca-head"><span class="ca-tag">机型成本对比</span><span class="ca-sub">按机型分组 · 已保存值</span></header>
      <div v-if="compareLoading" class="ca-empty">加载中…</div>
      <div v-else-if="!compareGroups.length" class="ca-empty">暂无基准配置</div>
      <div v-for="g in compareGroups" :key="g.name" class="ca-cmp-group">
        <div class="cmp-ghead">{{ g.name }} <span class="cnt">{{ g.items.length }} 个配置</span></div>
        <div v-for="c in g.items" :key="c.id" class="cmp-row" :class="{ cur: c.id === editingId }">
          <span class="cmp-name">{{ c.name }}<span v-if="c.id === editingId" class="chip-cur">当前</span></span>
          <span class="cmp-amt num">{{ money(c.total) }}</span>
          <i class="cmp-bar" :style="{ width: (c.total / compareMax * 100) + '%' }" />
        </div>
      </div>
      <footer class="ca-note">展示各基准配置<b>已保存</b>的成本（未保存的编辑不反映）；条宽按全库最大值归一。</footer>
    </section>
  </div>
</template>

<style scoped>
.ca-panel { display: flex; flex-direction: column; gap: 12px; }
.ca-card {
  padding: 14px 16px; border-radius: var(--cpq-radius-lg, 14px);
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); box-shadow: var(--cpq-shadow-md);
}
.ca-hero { border-color: var(--cpq-glass-border-strong, rgba(22,119,255,.45)); }
.ca-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.ca-tag { font-size: 12px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF);
  padding: 2px 9px; border-radius: 6px; background: var(--cpq-overlay-a15); }
.ca-sub { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.num { font-variant-numeric: tabular-nums lining-nums; letter-spacing: .2px; }
.mono { font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace; font-size: 10px; }

/* 卡1 */
.ca-total-line { display: flex; align-items: baseline; gap: 8px; }
.ca-cur { font-size: 15px; color: var(--cpq-text-secondary, #9BA1AA); font-weight: 600; }
.ca-total { font-size: 30px; font-weight: 750; line-height: 1.15;
  background: var(--cpq-accent-gradient); -webkit-background-clip: text; background-clip: text; color: transparent; }
.ca-badge { font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 5px; transform: translateY(-3px); }
.ca-badge.warn { color: #ad6800; background: var(--cpq-warn30, rgba(244,210,138,.3)); border: 1px solid rgba(250,173,20,.45); }
.ca-badge.ok { color: #1a7f5e; background: var(--cpq-overlay-success15, rgba(82,201,160,.15)); border: 1px solid rgba(82,201,160,.4); }
.ca-strip { display: flex; height: 10px; border-radius: 5px; overflow: hidden; margin: 10px 0 8px; }
.ca-strip i { display: block; height: 100%; }
.ca-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 10.5px; color: var(--cpq-text-secondary, #9BA1AA); }
.ca-legend .dot { display: inline-block; width: 7px; height: 7px; border-radius: 2.5px; margin-right: 4px; }
.ca-legend b { color: var(--cpq-text-primary, #E8ECEF); font-weight: 600; }
.ca-submetrics { display: flex; gap: 8px; margin-top: 11px; }
.ca-subm { flex: 1; background: var(--cpq-overlay-w4, rgba(255,255,255,.06)); border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.08)); border-radius: 9px; padding: 6px 9px; }
.ca-subm .lab { font-size: 10.5px; color: var(--cpq-text-muted, #6E7582); }
.ca-subm .val { font-size: 14px; font-weight: 650; color: var(--cpq-text-primary, #E8ECEF); margin-top: 1px; }
.ca-miss { display: flex; align-items: center; gap: 7px; margin-top: 10px; padding: 6px 10px; border-radius: 8px;
  background: var(--cpq-overlay-danger10, rgba(250,173,20,.12)); border: 1px dashed rgba(250,173,20,.45); font-size: 11.5px; color: var(--cpq-text-secondary, #9BA1AA); }
.ca-miss b { color: #ad6800; }
.ca-note { margin-top: 9px; font-size: 10.5px; color: var(--cpq-text-muted, #6E7582); line-height: 1.5; }

/* 卡2 */
.ca-grp { display: grid; grid-template-columns: 20px 66px 1fr 62px 42px; gap: 0 8px; align-items: center; padding: 3.5px 0; }
.grp-no { width: 17px; height: 17px; border-radius: 5px; background: var(--cpq-overlay-a12, var(--cpq-overlay-a15));
  color: var(--cpq-accent-primary, #1677FF); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 650; }
.grp-no.ghost { background: transparent; border: 1px solid var(--cpq-overlay-w15, rgba(255,255,255,.12)); color: var(--cpq-text-muted, #6E7582); }
.grp-name { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grp-miss { font-size: 9.5px; color: #ad6800; background: var(--cpq-overlay-warn30, rgba(244,210,138,.3)); padding: 0 4px; border-radius: 4px; margin-left: 4px; }
.grp-track { height: 8px; background: var(--cpq-overlay-w10, rgba(255,255,255,.1)); border-radius: 4px; overflow: hidden; }
.grp-bar { height: 100%; border-radius: 4px; background: var(--cpq-accent-gradient); transform-origin: left; animation: ca-grow .5s var(--cpq-ease-out-expo, ease-out) both; }
.grp-amt { font-size: 12px; font-weight: 650; text-align: right; color: var(--cpq-text-primary, #E8ECEF); }
.grp-pct { font-size: 10.5px; color: var(--cpq-text-muted, #6E7582); text-align: right; }
.ca-grp.kp { opacity: .55; }
.ca-grp.kp .grp-amt { font-size: 10px; color: var(--cpq-text-muted, #6E7582); font-weight: 400; }
.kp-track { background: repeating-linear-gradient(45deg, var(--cpq-overlay-w10, rgba(255,255,255,.1)) 0 4px, transparent 4px 8px); }
@keyframes ca-grow { from { transform: scaleX(0); } }

/* 卡3 */
.ca-top { display: grid; grid-template-columns: 18px 1fr 64px; gap: 0 8px; align-items: center; padding: 4.5px 0; border-bottom: 1px dashed var(--cpq-overlay-w10, rgba(255,255,255,.08)); }
.top-rank { font-size: 11px; font-weight: 700; color: var(--cpq-text-muted, #6E7582); }
.top-rank.lead { color: var(--cpq-accent-primary, #1677FF); }
.top-what { min-width: 0; }
.top-name { font-size: 12px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.top-meta { font-size: 10px; color: var(--cpq-text-muted, #6E7582); display: flex; gap: 6px; align-items: baseline; }
.top-meta .qty { color: var(--cpq-text-secondary, #9BA1AA); }
.top-nums { text-align: right; }
.top-amt { font-size: 12.5px; font-weight: 650; color: var(--cpq-text-primary, #E8ECEF); display: block; }
.top-pct { font-size: 10px; color: var(--cpq-text-muted, #6E7582); }
.cum-track { grid-column: 2 / 4; height: 3px; border-radius: 2px; background: var(--cpq-overlay-w10, rgba(255,255,255,.1)); margin-top: 2px; overflow: hidden; }
.cum-track i { display: block; height: 100%; border-radius: 2px; background: linear-gradient(90deg, var(--cpq-accent-primary, #1677FF), var(--cpq-accent-cyan, #36CFCF)); }
.miss-divider { display: flex; align-items: center; gap: 8px; margin: 8px 0 3px; font-size: 10px; color: #ad6800; }
.miss-divider::before, .miss-divider::after { content: ''; flex: 1; border-top: 1px dashed rgba(250,173,20,.4); }
.ca-top.miss .top-name { color: var(--cpq-text-muted, #6E7582); font-weight: 500; }
.miss-amt { font-size: 11px; color: #ad6800; font-weight: 600; }

/* 卡4 */
.ca-cmp-group + .ca-cmp-group { margin-top: 10px; }
.cmp-ghead { display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 650; color: var(--cpq-text-secondary, #9BA1AA); margin-bottom: 4px; }
.cmp-ghead .cnt { font-size: 9.5px; color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w15, rgba(255,255,255,.1)); padding: 0 5px; border-radius: 4px; }
.cmp-row { position: relative; display: grid; grid-template-columns: 1fr 66px; gap: 0 8px; align-items: center; padding: 2.5px 6px; border-radius: 8px; border: 1px solid transparent; }
.cmp-row:hover { background: var(--cpq-overlay-w4, rgba(255,255,255,.05)); }
.cmp-bar { position: absolute; left: 0; top: 2px; bottom: 2px; border-radius: 6px; background: var(--cpq-overlay-a15); z-index: 0; }
.cmp-name { position: relative; z-index: 1; font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmp-amt { position: relative; z-index: 1; font-size: 12px; font-weight: 650; text-align: right; color: var(--cpq-text-secondary, #9BA1AA); }
.cmp-row.cur { border-color: var(--cpq-glass-border-strong, rgba(22,119,255,.45)); background: var(--cpq-overlay-a8); }
.cmp-row.cur .cmp-name { color: var(--cpq-accent-primary, #1677FF); font-weight: 650; }
.cmp-row.cur .cmp-amt { color: var(--cpq-accent-primary, #1677FF); }
.chip-cur { font-size: 9px; font-weight: 700; color: #fff; background: var(--cpq-accent-gradient); padding: 0 5px; border-radius: 4px; margin-left: 5px; }
.ca-empty { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }

@media (prefers-reduced-motion: reduce) { .grp-bar { animation: none; } }
</style>
