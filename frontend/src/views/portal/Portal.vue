<script setup lang="ts">
/**
 * 工作台 (/portal) —— 三层结构（原型 docs/prototypes/工作台-主入口强化原型.html v2）：
 * ① 信号波纹 banner：时段问候（hero 角标数字已移除：与「我的工作台」卡/流程条数字重复，2026-10-21）；
 * ② CPQ 业务流程条：五节点全局计数纯展示（不再承担入口职责）+ 右栏「我的工作台」入口卡 =
 *    全页唯一主 CTA（角色铭牌 + 个人统计与子页统计条同口径 + 主按钮；数据源=子页同款接口）；
 * ③ 常用功能：方案助手磁贴（聊天权限门控）置首，其余按 perm 过滤——
 *   报价工作台/报价策略两张门槛=价格视野（field.quote.price），不再对无价格权限角色露出。
 * 材料与全站玻璃体系同源；banner 纯 CSS 场景，prefers-reduced-motion 自动关动效。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useAssistantShell } from '@/composables/useAssistantShell'
import { portalApi } from '@/api/portal'

const router = useRouter()
const auth = useAuthStore()
const shell = useAssistantShell()

// ── 页面数据：问候 / 概括角标 / 流程阶段 / 常用功能 ──
const userName = computed(() => auth.user?.name || '')
const hello = computed(() => {
  const h = new Date().getHours()
  return h < 6 ? '夜深了' : h < 12 ? '上午好' : h < 18 ? '下午好' : '晚上好'
})
const stages = computed<Record<string, number>>(() => ({
  requirement: 0, assign: 0, boming: 0, costing: 0, quoting: 0, ...(stagesRaw.value || {}),
}))
// 流程条：五节点全局阶段计数，纯展示（原型 工作台-主入口强化原型.html v2）——
// 不再承担入口职责（主入口=右栏「我的工作台」卡），数字为全公司在办口径
const FLOW_NODES = [
  { key: 'requirement', label: '需求登记', unit: '进行中', icon: 'doc' },
  { key: 'assign', label: '指派', unit: '无主', icon: 'clock' },
  { key: 'boming', label: 'BOM 配置', unit: '进行中', icon: 'chip' },
  { key: 'costing', label: '核价', unit: '待核', icon: 'coin' },
  { key: 'quoting', label: '报价', unit: '待转', icon: 'doccheck' },
]
const myRole = computed(() => auth.user?.role || '')
const ACTS = [
  { key: 'opp-all', title: '商机线索', desc: '全公司商机池与驾驶舱', to: '/opportunities', perm: 'page.opportunities_all', icon: 'board' },
  { key: 'workspace', title: '报价工作台', desc: '整单报价与导出', to: '/workspace', perm: 'field.quote.price', icon: 'doc' },
  { key: 'servers', title: '服务器', desc: '查看服务器产品库', to: '/servers', perm: 'page.servers', icon: 'tower' },
  { key: 'parts', title: '配件', desc: '查看配件与兼容性', to: '/parts', perm: 'page.parts', icon: 'bins' },
  { key: 'selection', title: '选型配置', desc: '机型能力与推导规则', to: '/strategies/selection', perm: 'page.strategies', icon: 'chip' },
  { key: 'pricing', title: '报价策略', desc: '多维度策略计价', to: '/strategies/pricing', perm: 'field.quote.price', icon: 'coin' },
  { key: 'strategy', title: '解决方案', desc: '行业解决方案与案例', to: '/strategies', perm: 'page.strategies', icon: 'layers' },
  { key: 'office', title: 'AI 办公室', desc: '智能助手 · 任务协同', to: '/ai-office', perm: 'page.office', icon: 'office' },
]
// ── 右栏「我的工作台」入口卡（全页唯一主 CTA，原型 v2）：角色铭牌+个人统计+主按钮 ──
// view 必须与 workstation 路由参数同源（admin 的调度台视图键是 dispatch，别拿角色键当视图键）
const RAIL_META: Record<string, { role: string; stage: string; ws: string; to: string; node?: string }> = {
  business: { role: '业务', stage: '需求登记环节', ws: '我的商机', to: '/portal/workstation/business' },
  te: { role: '技术支持工程师', stage: '方案配置环节', ws: '技术支持工作台', to: '/portal/workstation/te', node: 'boming' },
  cost: { role: '成本核算', stage: '核价环节', ws: '成本核算工作台', to: '/portal/workstation/cost', node: 'costing' },
  quote: { role: '市场报价专员', stage: '报价环节', ws: '报价专员工作台', to: '/portal/workstation/quote', node: 'quoting' },
  admin: { role: '管理员', stage: '调度指挥', ws: '任务调度台', to: '/portal/workstation/dispatch' },
}
const railRole = computed(() => RAIL_META[myRole.value] || null)
const railStats = ref<Array<{ k: string; v: number }>>([])
async function loadRail() {
  const meta = railRole.value
  if (!meta) return
  try {
    if (meta.node) {
      // te/cost/quote：与工作台子页统计条同一接口同一口径
      const res = await portalApi.oppCards({ mode: 'involved', node: meta.node, page: 1, page_size: 1 })
      const s: any = res.summary || {}
      railStats.value = [
        { k: '待办事项', v: s.mine ?? 0 },
        { k: '今日完成', v: s.done_today ?? 0 },
        { k: '经手商机', v: s.total ?? 0 },
      ]
    } else if (myRole.value === 'business') {
      const res = await portalApi.oppCards({ page: 1, page_size: 1 })
      const s: any = res.summary || {}
      railStats.value = [
        { k: '待办事项', v: s.returned ?? 0 },
        { k: '流转中', v: s.in_progress ?? 0 },
        { k: '全部商机', v: s.total ?? 0 },
      ]
    } else {
      // admin：调度台口径
      const d: any = await portalApi.dispatch()
      const today = new Date().toISOString().slice(0, 10)
      const active = (d.nodes || []).reduce((sum: number, n: any) =>
        sum + n.workload.reduce((s: number, w: any) => s + w.count, 0) + n.unassigned_count, 0)
      railStats.value = [
        { k: '无主任务', v: (d.stuck || []).length },
        { k: '活跃任务', v: active },
        { k: '今日转交', v: (d.transfers || []).filter((t: any) => (t.time || '').startsWith(today)).length },
      ]
    }
  } catch { railStats.value = [] }
}
// 常用功能：方案助手磁贴（AI 入口，聊天权限门控）置首；其余按 perm 过滤——
// 报价工作台/报价策略两张门槛=价格视野（field.quote.price）。主入口已上移右栏「我的工作台」卡，
// 「我的任务」磁贴移除（同目标三入口互稀释）。
type Act = { key: string; title: string; desc: string; to?: string; perm?: string; icon: string; assistant?: boolean }
const myActs = computed<Act[]>(() => {
  const list: Act[] = []
  if (auth.chatRolesAllowed) {
    list.push({ key: 'assistant', title: '方案助手', desc: 'AI 硬件配置建议与报价洞察', icon: 'spark', assistant: true })
  }
  return [...list, ...ACTS.filter((a) => auth.can(a.perm || ''))]
})
function openAct(a: Act) {
  if (a.assistant) shell.show()
  else if (a.to) router.push(a.to)
}

// ── 全局 stages → 流程条（todo-summary 的 items 角标已移除：与「我的工作台」卡/流程条数字重复，2026-10-21） ──
const stagesRaw = ref<Record<string, number> | null>(null)
async function loadStages() {
  try {
    const res = await portalApi.todoSummary()
    stagesRaw.value = res.stages || null
  } catch {
    stagesRaw.value = null
  }
}

onMounted(() => { loadStages(); loadRail() })

// ── 待办格图标（20×20 线稿）──
const G = (inner: string) =>
  `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
const GLYPHS: Record<string, string> = {
  follow: G('<circle cx="10" cy="10" r="6.5"/><path d="M10 6.5v3.5l2.5 2.5"/>'),
  chip: G('<rect x="5.5" y="5.5" width="9" height="9" rx="1.5"/><path d="M9 2v3.5M11 2v3.5M9 14.5V18M11 14.5V18M2 9h3.5M2 11h3.5M14.5 9H18M14.5 11H18"/>'),
  doc: G('<path d="M5 2.5h7l3 3v12H5z"/><path d="M8 9.5h4M8 12.5h4"/>'),
  doccheck: G('<path d="M5 2.5h7l3 3v12H5z"/><path d="M7.5 12.5l2 2 3.5-3.5"/>'),
  warn: G('<path d="M10 3l7.5 13.5h-15z"/><path d="M10 8v3.2M10 13.8v.1"/>'),
  clock: G('<circle cx="10" cy="10" r="6.5"/><path d="M10 6v4l2.5 1.5"/>'),
  board: G('<rect x="3" y="3.5" width="14" height="13" rx="1.5"/><path d="M10 3.5v13M4 8h5M11 11h5"/>'),
  coin: G('<circle cx="10" cy="10" r="6.5"/><path d="M8 7.5h4M10 7.5V13M8.5 12h3"/>'),
  kanban: G('<rect x="3" y="3.5" width="14" height="13" rx="1.5"/><path d="M7.5 3.5v13M12.5 3.5v8"/>'),
  tower: G('<rect x="5.5" y="2.5" width="9" height="15" rx="1.5"/><path d="M5.5 8h9M8 14.5h.1M11.5 14.5h.1"/>'),
  bins: G('<rect x="3" y="3.5" width="14" height="13" rx="1.5"/><path d="M10 3.5v13M3 9.5h7"/>'),
  layers: G('<path d="M10 3l7 4-7 4-7-4z"/><path d="M3.8 11.5L10 15l6.2-3.5"/>'),
  office: G('<rect x="4" y="3.5" width="12" height="13" rx="1.5"/><path d="M7.5 7h2M11.5 7h2M7.5 10.5h2M11.5 10.5h2M9 16.5v-3h2v3"/>'),
  spark: G('<path d="M10 2.5l1.7 4.3 4.3 1.7-4.3 1.7L10 14.5l-1.7-4.3L4 8.5l4.3-1.7z"/><path d="M15.5 12.5l.8 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>'),
}
function glyph(name: string): string {
  return GLYPHS[name] || GLYPHS.doc
}

</script>

<template>
  <div class="portal">
      <!-- 信号波纹 banner -->
      <section class="hero">
        <div class="slogan">AI 赋能 · 让计算力更简单</div>
        <div class="rings"><i></i><i></i><i></i><i></i>
          <div class="sweep"></div>
          <span class="blip" style="right:70px;top:88px"></span>
          <span class="blip b2" style="right:150px;top:56px"></span>
          <span class="blip b3" style="right:40px;top:30px"></span>
        </div>
        <h1>{{ hello }}，{{ userName }}</h1>
        <div class="sub">欢迎使用霄擎算力 CPQ 平台，助您高效完成从需求到报价的全流程。</div>
      </section>
    <main class="portal-main">

      <!-- 流程条（纯展示，全局口径）+ 右栏「我的工作台」主入口卡 -->
      <section class="flowrow" :class="{ solo: !railRole }">
        <div class="flow">
          <div class="h">CPQ 业务流程<span>数字为全公司在办口径</span></div>
          <div class="fnodes">
            <template v-for="(n, i) in FLOW_NODES" :key="n.key">
              <div class="fnode">
                <span class="fico" v-html="glyph(n.icon)"></span>
                <span><span class="n">{{ n.label }}</span><span class="c num"><b>{{ stages[n.key] ?? 0 }}</b> {{ n.unit }}</span></span>
              </div>
              <svg v-if="i < FLOW_NODES.length - 1" class="farrow" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M5 12h13M13 7l5 5-5 5"/></svg>
            </template>
          </div>
        </div>
        <div v-if="railRole" class="mycard">
          <div class="h"><span class="chip" v-html="glyph('chip')"></span>我的工作台</div>
          <div class="roleline">{{ railRole.role }} · {{ railRole.stage }}</div>
          <div class="mrows">
            <div v-for="(s, i) in railStats" :key="s.k" class="mrow">
              <b class="num" :class="{ hot: i === 0 }">{{ s.v }}</b>
              <span>{{ s.k }}</span>
            </div>
          </div>
          <button type="button" class="mine-go" @click="router.push(railRole.to)">进入{{ railRole.ws }} →</button>
        </div>
      </section>

      <!-- 常用功能 -->
      <div class="sec-h">常用功能<span>高频操作一步直达</span></div>
      <div class="acts">
        <a v-for="a in myActs" :key="a.key" class="act" :class="{ ai: a.assistant }" @click="openAct(a)">
          <span class="chip" v-html="glyph(a.icon)"></span>
          <span class="ax"><b>{{ a.title }}</b><i>{{ a.desc }}</i></span>
          <span class="chev">›</span>
        </a>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* 材料与全站玻璃体系同源；banner=信号波纹场景（配方见 docs/prototypes/工作台-新架构原型.html） */
.portal{position:relative;min-height:calc(100% - var(--cpq-header-clearance,0px));
--gb:var(--cpq-glass-border,rgba(255,255,255,.1));--card:var(--cpq-glass-card-bg,rgba(255,255,255,.045));--hot:#f4756f;--sc-fade:var(--cpq-bg-primary,#08090B)}
.portal-main{max-width:1460px;margin:0 auto;padding:22px 30px 46px;position:relative;z-index:1}
.num{font-variant-numeric:tabular-nums}

/* ═══ Hero · 信号波纹（雷达环 + 旋转扫描 + 信号点）═══ */
.hero{position:relative;overflow:hidden;margin:calc(-1 * var(--cpq-header-clearance,0px)) 0 18px;
padding:calc(var(--cpq-header-clearance,0px) + 34px) 30px 34px;min-height:206px;
background:radial-gradient(ellipse at 74% 130%,var(--sc-bg2),var(--sc-bg1) 72%)}
.hero::after{content:'';position:absolute;left:0;right:0;bottom:0;height:90px;
background:linear-gradient(to bottom,transparent,var(--sc-fade));pointer-events:none}
.rings{position:absolute;right:6%;top:50%;transform:translateY(-50%);width:320px;height:320px}
.rings i{position:absolute;left:50%;top:50%;border:1px solid var(--sc-ring);border-radius: 50%;transform:translate(-50%,-50%)}
.rings i:nth-child(1){width:90px;height:90px}
.rings i:nth-child(2){width:160px;height:160px;border-color:var(--sc-ring-dim)}
.rings i:nth-child(3){width:230px;height:230px;border-color:var(--sc-ring-dim)}
.rings i:nth-child(4){width:300px;height:300px;border-color:var(--sc-ring-faint)}
.sweep{position:absolute;inset:0;border-radius: 50%;background:conic-gradient(from 0deg,var(--sc-sweep),transparent 75deg);animation:spin 7s linear infinite;filter:blur(3px)}
@keyframes spin{to{transform:rotate(360deg)}}
.rings::after{content:'';position:absolute;left:50%;top:50%;width:8px;height:8px;border-radius: 50%;background:var(--sc-core);box-shadow:0 0 14px var(--sc-core-glow);transform:translate(-50%,-50%);animation:core 2.4s ease-in-out infinite}
@keyframes core{0%,100%{opacity:.5}50%{opacity:1}}
.blip{position:absolute;width:6px;height:6px;border-radius: 50%;background:var(--sc-blip);box-shadow:0 0 10px var(--sc-blip-glow);animation:blip 3s infinite}
.blip.b2{animation-delay:1.2s;background:var(--sc-blip2);box-shadow:0 0 10px var(--sc-blip2-glow)}
.blip.b3{animation-delay:2s}
@keyframes blip{0%,100%{opacity:.2}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){.sweep,.blip{animation:none !important}}
.hero > :not(.rings){position:relative;z-index:2}
.hero h1{font-size:23px;font-weight:650;letter-spacing:-.02em;color:var(--sc-t1)}
.hero .sub{margin-top:6px;font-size:13px;color:var(--sc-t2)}
.slogan{position:absolute;right:28px;top:24px;text-align:right;font-size:13px;color:var(--sc-slog);letter-spacing:2px}

.chip{width:36px;height:36px;border-radius: var(--cpq-radius-md);background:rgba(59,130,246,.14);color:var(--cpq-accent-primary,#1677ff);display:grid;place-items:center;flex:none}
.chip svg{width:18px;height:18px}

/* ═══ 流程条（纯展示）+ 右栏「我的工作台」入口卡 ═══ */
/* 轨道用 minmax(0,1fr)：手机端 fnodes 横滑后内容宽会把 1fr 的自动最小尺寸撑破，整页横向溢出（2026-10-21） */
.flowrow{display:grid;grid-template-columns:minmax(0,1fr) 284px;gap:14px;margin-bottom:18px}
.flowrow.solo{grid-template-columns:minmax(0,1fr)}
.flow{border:1px solid var(--gb);border-radius: var(--cpq-radius-lg);background:var(--card);backdrop-filter:blur(12px);
box-shadow:inset 0 1px 0 0 rgba(255,255,255,.07);padding:18px 22px;display:flex;flex-direction:column}
.flow .h{font-size:var(--cpq-font-size-base);font-weight:600}
.flow .h span{margin-left:10px;font-size:var(--cpq-font-size-sm);color:var(--cpq-text-muted,#8b94a8);font-weight:400}
.fnodes{flex:1;display:flex;align-items:center;gap:6px;margin-top:8px}
.fnode{flex:1;display:flex;align-items:center;gap:12px;min-width:0}
.fico{width:42px;height:42px;border-radius: 50%;background:rgba(59,130,246,.12);color:var(--cpq-accent-primary,#1677ff);display:grid;place-items:center;flex:none;border:1px solid rgba(122,167,255,.25)}
.fico svg{width:19px;height:19px}
.fnode .n{font-size:13.5px;font-weight:600;color:var(--cpq-text-primary)}
.fnode .c{font-size:var(--cpq-font-size-sm);color:var(--cpq-text-muted,#8b94a8);margin-top:2px}
.fnode .c b{color:var(--cpq-accent-primary,#1677ff);font-weight:600}
.farrow{color:var(--cpq-text-muted,#8b94a8);flex:none}
/* 我的入口卡：accent 渐变描边，全页唯一主 CTA */
.mycard{position:relative;border:1px solid rgba(122,167,255,.5);border-radius: var(--cpq-radius-lg);
background:linear-gradient(155deg,rgba(59,130,246,.20),rgba(59,130,246,.05) 55%),var(--card);
box-shadow:0 10px 30px rgba(59,130,246,.16),inset 0 1px 0 0 rgba(255,255,255,.1);
padding:16px 18px;display:flex;flex-direction:column}
.mycard .h{display:flex;align-items:center;gap:9px;font-size:13.5px;font-weight:600;color:var(--cpq-text-primary)}
.mycard .h .chip{width:32px;height:32px;border-radius: var(--cpq-radius-sm);background:rgba(59,130,246,.28);color:#cfe0ff}
.mycard .h .chip svg{width:16px;height:16px}
.roleline{font-size:11.5px;color:var(--cpq-text-muted,#8b94a8);margin-top:8px}
/* 统计行：桌面行式（label 左数字右，row-reverse 因 DOM 数字在前）；手机端媒体查询改三列格 */
.mrow{display:flex;flex-direction:row-reverse;justify-content:space-between;align-items:baseline;margin-top:9px;font-size:var(--cpq-font-size-sm);color:var(--cpq-text-muted,#8b94a8)}
.mrow b{font-size:17px;font-weight:600;color:var(--cpq-text-primary)}
.mrow b.hot{color:#f4756f}
.mycard .mrows{margin-bottom:var(--cpq-space-3)} /* CTA 吸底 auto 在卡片=内容高时坍缩为0，这里保底间隙 */
.mine-go{margin-top:auto;width:100%;display:flex;align-items:center;justify-content:center;gap:7px;
font-size:12.5px;font-weight:600;color:#fff;background:linear-gradient(135deg,#3b82f6,#5b8ff9);
border:0;border-radius: var(--cpq-radius-sm);padding:9px 0;box-shadow:0 4px 12px rgba(22,119,255,.32);cursor:pointer}
.mine-go:hover{filter:brightness(1.08)}
/* 方案助手磁贴：AI 渐变识别 */
.act.ai{border-color:rgba(122,167,255,.35);background:linear-gradient(140deg,rgba(59,130,246,.14),rgba(14,165,233,.04) 60%),var(--card)}
.act.ai .chip{background:rgba(59,130,246,.25);color:#cfe0ff}

.sec-h{display:flex;align-items:baseline;gap:10px;margin:2px 2px 12px;font-size:var(--cpq-font-size-base);font-weight:600}
.sec-h span{font-size:var(--cpq-font-size-sm);color:var(--cpq-text-muted,#8b94a8);font-weight:400}
.sec-h .more{margin-left:auto;font-size:var(--cpq-font-size-sm);color:var(--cpq-accent-primary,#1677ff);font-weight:400}
.acts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.act{display:flex;align-items:center;gap:12px;border:1px solid var(--gb);border-radius: var(--cpq-radius-md);background:var(--card);
backdrop-filter:blur(12px);box-shadow:inset 0 1px 0 0 rgba(255,255,255,.07);padding:14px 16px}
.act:hover{background:rgba(255,255,255,.07);border-color:rgba(122,167,255,.4)}
.act .chip{width:38px;height:38px}
.act .ax{flex:1;min-width:0}
.act .ax b{display:block;font-size:13.5px;font-weight:600}
.act .ax i{display:block;font-style:normal;font-size:11.5px;color:var(--cpq-text-muted,#8b94a8);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.act .chev{color:var(--cpq-text-muted,#8b94a8);flex:none}

/* ═══ 手机端（≤768）：须置于全部基础规则之后，否则被同特异性后写规则覆盖 ═══ */
@media (max-width:768px){
.portal-main{padding:14px 14px calc(var(--cpq-tabbar-h,58px) + 20px)}
.flowrow{grid-template-columns:minmax(0,1fr)}
.hero{margin:calc(-1 * var(--cpq-header-clearance,0px)) 0 14px;padding:calc(var(--cpq-header-clearance,0px) + 20px) 16px 20px;min-height:0}
.hero h1{font-size:var(--cpq-font-size-xl)}
.slogan{display:none}
/* 手机 hero 变矮后波纹只剩孤立信号点，干脆去掉，留纯净渐变 */
.rings{display:none}
/* 流程条：与 PC 同构单行，窄屏放不下整行横滑；箭头保留；隐藏原生滚动条（右缘截断即可暗示可滑） */
.fnodes{overflow-x:auto;padding-bottom:4px;scrollbar-width:none}
.fnodes::-webkit-scrollbar{display:none}
.fnode{flex:none;gap:10px}
.fico{width:36px;height:36px}
.fico svg{width:16px;height:16px}
.fnode .n{font-size:12.5px;white-space:nowrap}
.fnode .c{font-size:var(--cpq-font-size-xs);white-space:nowrap}
/* 常用功能：两列；描述允许换行不再单行截断 */
.acts{grid-template-columns:1fr 1fr;gap:8px}
.act{padding:11px 12px;gap:10px}
.act .chip{width:32px;height:32px}
.act .chip svg{width:15px;height:15px}
.act .ax b{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.act .ax i{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.act .chev{display:none}
/* 我的入口卡统计：三列格（数字上 label 下），避免全宽下两端对齐把 label 与数字扯开 */
.mrows{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
.mrow{flex-direction:column;align-items:center;gap:3px;margin-top:0;text-align:center}
.mrow b{font-size:18px}
.mrow span{font-size:var(--cpq-font-size-xs)}
}

</style>
<style>
/* banner 场景主题变量（非 scoped；场景默认暗色，浅色主题切日间版） */
.portal{--sc-bg1:#04070f;--sc-bg2:#0a1e3d;--sc-ring:rgba(122,167,255,.15);--sc-ring-dim:rgba(122,167,255,.09);
--sc-ring-faint:rgba(122,167,255,.05);--sc-sweep:rgba(122,167,255,.17);--sc-core:#8fb5ff;--sc-core-glow:rgba(122,167,255,.9);
--sc-blip:#7aa7ff;--sc-blip-glow:rgba(122,167,255,.9);--sc-blip2:#4fd6a5;--sc-blip2-glow:rgba(79,214,165,.9);
--sc-t1:#fff;--sc-t2:rgba(226,234,248,.75);--sc-slog:rgba(205,216,238,.55)}
html[data-theme='light'] .portal{--sc-bg1:#f4f8ff;--sc-bg2:#d8e8fd;--sc-ring:rgba(59,130,246,.18);--sc-ring-dim:rgba(59,130,246,.10);
--sc-ring-faint:rgba(59,130,246,.05);--sc-sweep:rgba(59,130,246,.10);--sc-core:#2f6fe4;--sc-core-glow:rgba(59,130,246,.55);
--sc-blip:#2f6fe4;--sc-blip-glow:rgba(59,130,246,.5);--sc-blip2:#149d82;--sc-blip2-glow:rgba(20,157,130,.5);
--sc-t1:var(--cpq-text-primary,#1a2333);--sc-t2:var(--cpq-text-secondary,#48546e);--sc-slog:rgba(90,118,168,.75)}
</style>
