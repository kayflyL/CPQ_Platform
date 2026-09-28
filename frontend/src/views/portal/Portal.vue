<script setup lang="ts">
/**
 * 工作台 (/portal) —— 三层结构（原型 docs/prototypes/工作台-新架构原型.html）：
 * ① 信号波纹 banner：时段问候 + 三个概括角标（今日待办/在办商机/今日新增，真实口径 todo-summary）；
 * ② CPQ 业务流程条：五节点全局阶段计数（todo-summary.stages）+ 方案助手卡（唤起全局浮动助手）；
 * ③ 常用功能 2×4：高频操作大行动行，perm 按 page.* 过滤（与菜单/直达 URL 联动）。
 * 材料与全站玻璃体系同源；banner 纯 CSS 场景，prefers-reduced-motion 自动关动效。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useAssistantShell } from '@/composables/useAssistantShell'
import { portalApi, type TodoSummaryItem } from '@/api/portal'

const router = useRouter()
const auth = useAuthStore()
const shell = useAssistantShell()

// ── 页面数据：问候 / 概括角标 / 流程阶段 / 常用功能 ──
const userName = computed(() => auth.user?.name || '')
const hello = computed(() => {
  const h = new Date().getHours()
  return h < 6 ? '夜深了' : h < 12 ? '上午好' : h < 18 ? '下午好' : '晚上好'
})
function statOf(key: string): number | null {
  const hit = todos.value.find((t) => t.key === key && t.level !== 'dim')
  return hit ? hit.count : null
}
const todoTotal = computed(() => {
  if (!todos.value.length) return null
  return todos.value.filter((t) => t.level !== 'dim').reduce((s, t) => s + t.count, 0)
})
const stages = computed<Record<string, number>>(() => ({
  requirement: 0, assign: 0, boming: 0, costing: 0, quoting: 0, ...(stagesRaw.value || {}),
}))
const FLOW_NODES = [
  { key: 'requirement', label: '需求登记', unit: '进行中', icon: 'doc', to: '/portal/workstation/business' },
  { key: 'assign', label: '指派', unit: '无主', icon: 'clock', to: '/portal/workstation/dispatch' },
  { key: 'boming', label: 'BOM 配置', unit: '进行中', icon: 'chip', to: '/portal/workstation/te' },
  { key: 'costing', label: '核价', unit: '待核', icon: 'coin', to: '/portal/workstation/cost' },
  { key: 'quoting', label: '报价', unit: '待转', icon: 'doccheck', to: '/portal/workstation/quote' },
]
const ACTS = [
  { key: 'opp-all', title: '商机线索', desc: '全公司商机池与驾驶舱', to: '/opportunities', perm: 'page.opportunities_all', icon: 'board' },
  { key: 'workspace', title: '报价工作台', desc: '整单报价与导出', to: '/workspace', perm: 'page.opportunities', icon: 'doc' },
  { key: 'servers', title: '服务器', desc: '查看服务器产品库', to: '/servers', perm: 'page.servers', icon: 'tower' },
  { key: 'parts', title: '配件', desc: '查看配件与兼容性', to: '/parts', perm: 'page.parts', icon: 'bins' },
  { key: 'selection', title: '选型配置', desc: '机型能力与推导规则', to: '/strategies/selection', perm: 'page.strategies', icon: 'chip' },
  { key: 'pricing', title: '报价策略', desc: '多维度策略计价', to: '/strategies/pricing', perm: 'page.strategies', icon: 'coin' },
  { key: 'strategy', title: '解决方案', desc: '行业解决方案与案例', to: '/strategies', perm: 'page.strategies', icon: 'layers' },
  { key: 'office', title: 'AI 办公室', desc: '智能助手 · 任务协同', to: '/ai-office', perm: 'page.office', icon: 'office' },
]
const myActs = computed(() => ACTS.filter((a) => auth.can(a.perm)))

// ── 待处理事项（角色口径 items → hero 角标；全局 stages → 流程条） ──
const todos = ref<TodoSummaryItem[]>([])
const stagesRaw = ref<Record<string, number> | null>(null)
async function loadTodos() {
  try {
    const res = await portalApi.todoSummary()
    todos.value = res.items || []
    stagesRaw.value = res.stages || null
  } catch {
    todos.value = []
  }
}

onMounted(loadTodos)


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
}
function glyph(name: string): string {
  return GLYPHS[name] || GLYPHS.doc
}

</script>

<template>
  <div class="portal">
    <main class="portal-main">
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
        <div class="sub">欢迎使用霄霖智力 CPQ 平台，助您高效完成从需求到报价的全流程。</div>
        <div class="today">
          <span v-if="todoTotal !== null" class="tchip hot">今日待办 <b class="num">{{ todoTotal }}</b></span>
          <span class="tchip">在办商机 <b class="num">{{ stages.running }}</b></span>
          <span v-if="statOf('opp_today') !== null" class="tchip">今日新增 <b class="num">{{ statOf('opp_today') }}</b></span>
        </div>
      </section>

      <!-- CPQ 业务流程条 -->
      <section class="flowrow" :class="{ solo: !auth.chatRolesAllowed }">
        <div class="flow">
          <div class="h">CPQ 业务流程<span>从需求到报价，AI 驱动的高效协同</span></div>
          <div class="fnodes">
            <template v-for="(n, i) in FLOW_NODES" :key="n.key">
              <a class="fnode" :title="'进入' + n.label + '工作台'" @click="router.push(n.to)">
                <span class="fico" v-html="glyph(n.icon)"></span>
                <span><span class="n">{{ n.label }}</span><span class="c num"><b>{{ stages[n.key] ?? 0 }}</b> {{ n.unit }}</span></span>
              </a>
              <svg v-if="i < FLOW_NODES.length - 1" class="farrow" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M5 12h13M13 7l5 5-5 5"/></svg>
            </template>
          </div>
        </div>
        <div v-if="auth.chatRolesAllowed" class="aicard">
          <div class="h"><span class="ai">AI</span>方案助手</div>
          <p>基于行业经验与产品知识，为您提供硬件智能配置建议与报价洞察。</p>
          <button type="button" @click="shell.show()">立即体验 →</button>
        </div>
      </section>

      <!-- 常用功能 -->
      <div class="sec-h">常用功能<span>高频操作一步直达</span></div>
      <div class="acts">
        <a v-for="a in myActs" :key="a.key" class="act" @click="router.push(a.to)">
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
--gb:rgba(255,255,255,.1);--card:rgba(255,255,255,.045);--hot:#f4756f}
.portal-main{max-width:1460px;margin:0 auto;padding:22px 30px 46px;position:relative;z-index:1}
.num{font-variant-numeric:tabular-nums}
@media (max-width:768px){.portal-main{padding:16px 14px calc(var(--cpq-tabbar-h,58px) + 16px)}
.acts{grid-template-columns:repeat(2,1fr)}
.flowrow{grid-template-columns:1fr}
.hero{margin:0 -14px 14px;padding:22px 16px 20px;min-height:0}
.hero h1{font-size:20px}
.slogan{display:none}
.rings{width:200px;height:200px;right:-52px;top:42%;opacity:.85}
.aicard{margin-bottom:2px}
.fnodes{flex-wrap:wrap;gap:10px 14px}
.fnode{flex:1 1 44%}
.farrow{display:none}}

/* ═══ Hero · 信号波纹（雷达环 + 旋转扫描 + 信号点）═══ */
.hero{position:relative;overflow:hidden;margin:0 -30px 18px;padding:34px 30px 30px;min-height:206px;
background:radial-gradient(ellipse at 74% 130%,#0a1e3d,#04070f 72%)}
.rings{position:absolute;right:6%;top:50%;transform:translateY(-50%);width:320px;height:320px}
.rings i{position:absolute;left:50%;top:50%;border:1px solid rgba(122,167,255,.15);border-radius:50%;transform:translate(-50%,-50%)}
.rings i:nth-child(1){width:90px;height:90px}
.rings i:nth-child(2){width:160px;height:160px;border-color:rgba(122,167,255,.11)}
.rings i:nth-child(3){width:230px;height:230px;border-color:rgba(122,167,255,.08)}
.rings i:nth-child(4){width:300px;height:300px;border-color:rgba(122,167,255,.05)}
.sweep{position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,rgba(122,167,255,.17),transparent 75deg);animation:spin 7s linear infinite;filter:blur(3px)}
@keyframes spin{to{transform:rotate(360deg)}}
.rings::after{content:'';position:absolute;left:50%;top:50%;width:8px;height:8px;border-radius:50%;background:#8fb5ff;box-shadow:0 0 14px rgba(122,167,255,.9);transform:translate(-50%,-50%);animation:core 2.4s ease-in-out infinite}
@keyframes core{0%,100%{opacity:.5}50%{opacity:1}}
.blip{position:absolute;width:6px;height:6px;border-radius:50%;background:#7aa7ff;box-shadow:0 0 10px rgba(122,167,255,.9);animation:blip 3s infinite}
.blip.b2{animation-delay:1.2s;background:#4fd6a5;box-shadow:0 0 10px rgba(79,214,165,.9)}
.blip.b3{animation-delay:2s}
@keyframes blip{0%,100%{opacity:.2}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){.sweep,.blip{animation:none !important}}
.hero > :not(.rings){position:relative;z-index:2}
.hero h1{font-size:23px;font-weight:650;letter-spacing:-.02em}
.hero .sub{margin-top:6px;font-size:13px;color:#8b94a8}
.today{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}
.tchip{display:flex;align-items:center;gap:7px;font-size:12.5px;color:#b7c0d4;background:rgba(255,255,255,.05);
border:1px solid rgba(255,255,255,.1);border-radius:99px;padding:6px 13px}
.tchip b{color:#7aa7ff;font-weight:600}
.tchip.hot b{color:#f4756f}
.tchip:hover{border-color:rgba(122,167,255,.45)}
.slogan{position:absolute;right:28px;top:24px;text-align:right;font-size:13px;color:#8b94a8;letter-spacing:2px}

.chip{width:36px;height:36px;border-radius:10px;background:rgba(59,130,246,.16);color:#7aa7ff;display:grid;place-items:center;flex:none}
.chip svg{width:18px;height:18px}

/* ═══ 流程条 ═══ */
.flowrow{display:grid;grid-template-columns:1fr 284px;gap:14px;margin-bottom:18px}
.flow{border:1px solid var(--gb);border-radius:14px;background:var(--card);backdrop-filter:blur(12px);
box-shadow:inset 0 1px 0 0 rgba(255,255,255,.07);padding:18px 22px}
.flow .h{font-size:14px;font-weight:600}
.flow .h span{margin-left:10px;font-size:12px;color:#8b94a8;font-weight:400}
.fnodes{display:flex;align-items:center;gap:6px;margin-top:16px}
.fnode{flex:1;display:flex;align-items:center;gap:12px;min-width:0;cursor:pointer}
.fnode:hover .fico{border-color:rgba(122,167,255,.65);background:rgba(59,130,246,.24)}
.fnode:hover .n{color:#cfe0ff}
.fico{width:42px;height:42px;border-radius:50%;background:rgba(59,130,246,.14);color:#7aa7ff;display:grid;place-items:center;flex:none;border:1px solid rgba(122,167,255,.25);transition:border-color .15s,background .15s}
.fico svg{width:19px;height:19px}
.fnode .n{font-size:13.5px;font-weight:600}
.fnode .c{font-size:12px;color:#8b94a8;margin-top:2px}
.fnode .c b{color:#7aa7ff;font-weight:600}
.farrow{color:#4a5670;flex:none}
.aicard{border:1px solid rgba(122,167,255,.3);border-radius:14px;background:linear-gradient(140deg,rgba(59,130,246,.16),rgba(14,165,233,.05) 60%),rgba(255,255,255,.045);
box-shadow:inset 0 1px 0 0 rgba(255,255,255,.09);padding:16px 18px;display:flex;flex-direction:column}
.aicard .h{display:flex;align-items:center;gap:9px;font-size:13.5px;font-weight:600;color:#cfe0ff}
.aicard .h .ai{width:28px;height:28px;border-radius:8px;background:rgba(59,130,246,.25);display:grid;place-items:center;font-size:11px;color:#cfe0ff;font-weight:700}
.aicard p{margin-top:8px;font-size:12px;color:#8b94a8;line-height:1.6}
.aicard button{margin-top:auto;align-self:flex-start;font-size:12px;color:#cfe0ff;background:rgba(59,130,246,.25);border:1px solid rgba(122,167,255,.4);border-radius:8px;padding:6px 13px}

.sec-h{display:flex;align-items:baseline;gap:10px;margin:2px 2px 12px;font-size:14px;font-weight:600}
.sec-h span{font-size:12px;color:#8b94a8;font-weight:400}
.sec-h .more{margin-left:auto;font-size:12px;color:#7aa7ff;font-weight:400}
.acts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.act{display:flex;align-items:center;gap:12px;border:1px solid var(--gb);border-radius:12px;background:var(--card);
backdrop-filter:blur(12px);box-shadow:inset 0 1px 0 0 rgba(255,255,255,.07);padding:14px 16px}
.act:hover{background:rgba(255,255,255,.07);border-color:rgba(122,167,255,.4)}
.act .chip{width:38px;height:38px}
.act .ax{flex:1;min-width:0}
.act .ax b{display:block;font-size:13.5px;font-weight:600}
.act .ax i{display:block;font-style:normal;font-size:11.5px;color:#8b94a8;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.act .chev{color:#4a5670;flex:none}

</style>
