<script setup lang="ts">
defineOptions({ name: 'StrategyPortal' })
/** 解决方案门户(/strategies)——Vercel/华为目录式布局。
 *  左侧:方案场景目录树(带数量) + 工作流入口;
 *  右侧:场景介绍横幅(含方案助手咨询 CTA) + 极简方案卡(场景铭牌 + 标题 + 一句话)。 */
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { solutionApi, type Solution, type SolutionScene } from '@/api/solutions'
import { useAssistantShell } from '@/composables/useAssistantShell'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const auth = useAuthStore()
const { show: showAssistant } = useAssistantShell()

/* ── 工作流入口（侧栏底部） ── */
interface ModuleCard { key: string; title: string; desc: string; to: string }
const MODULES: ModuleCard[] = [
  { key: 'requirement', title: '需求分析', desc: '该配什么、配多少', to: '/strategies/requirement' },
  { key: 'selection', title: '选型配置', desc: '互斥规则 + BOM 案例库', to: '/strategies/selection' },
  { key: 'pricing', title: '报价策略', desc: '加法定价引擎', to: '/strategies/pricing' },
]

/* ── 场景色编码（全页唯一的色彩预算） ── */
const SCENE_HUES: Record<string, string> = {
  ai: '#3B82F6',
  virt: '#8B5CF6',
  store: '#14B8A6',
  sim: '#F59E0B',
}
const hueOf = (sceneKey: string) => SCENE_HUES[sceneKey] || 'var(--cpq-accent-primary)'

/* ── 场景横幅文案 ── */
const HERO: Record<string, { kick: string; title: string; desc: string }> = {
  all: {
    kick: 'SOLUTION LIBRARY', title: '解决方案库',
    desc: '按场景沉淀可复用的服务器方案——每个场景都是从客户需求单到配置单、再到报价的完整路径。不确定客户需求落在哪？让方案助手帮你定位。',
  },
  ai: {
    kick: 'AI · ACCELERATED COMPUTING', title: 'AI·加速计算',
    desc: '推理、微调与信创算力：从模型显存估算到卡数配比的完整选型路径，覆盖知识库问答、生产级推理与国产化部署。',
  },
  virt: {
    kick: 'VIRTUALIZATION · DATABASE', title: '虚拟化·数据库',
    desc: '内存通道、RAID 层级与高可用：承载核心业务系统的稳定底座，虚拟化密度与数据库延迟的硬件账都在这里。',
  },
  store: {
    kick: 'STORAGE', title: '海量存储',
    desc: '盘位数量、冗余等级与冷热分层：让冷数据存得起、热数据跑得动。',
  },
  sim: {
    kick: 'SIMULATION', title: '工业仿真',
    desc: '多核浮点与超大内存：CAE 求解速度的硬件账，从 AVX2 指令集到内存通道布局。',
  },
}

/* ── 数据 ── */
const activeScene = ref('all')
const keyword = ref('')
const solutions = ref<Solution[]>([])
const scenes = ref<SolutionScene[]>([])
const loading = ref(false)

const counts = computed(() => {
  const c: Record<string, number> = { all: solutions.value.length }
  for (const s of solutions.value) c[s.scene_key] = (c[s.scene_key] || 0) + 1
  return c
})
const chips = computed(() => [{ key: 'all', label: '全部' }, ...scenes.value.map(s => ({ key: s.key, label: s.label }))])

const searched = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return solutions.value
  return solutions.value.filter(s =>
    [s.title, s.sub, s.scene, ...(s.features || [])].join(' ').toLowerCase().includes(q))
})
const list = computed(() => activeScene.value === 'all'
  ? searched.value
  : searched.value.filter(s => s.scene_key === activeScene.value))
const hero = computed(() => HERO[activeScene.value] || HERO.all)
const heroHue = computed(() => hueOf(activeScene.value))
const emptyText = computed(() => keyword.value.trim()
  ? `没有匹配「${keyword.value.trim()}」的方案，换个关键词试试。`
  : '该场景暂无解决方案。')

async function load() {
  loading.value = true
  try {
    const [solRes, sceneRes] = await Promise.all([solutionApi.list(), solutionApi.scenes()])
    solutions.value = solRes.solutions
    scenes.value = sceneRes.scenes
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
// KeepAlive：切回时刷新（首次挂载由 onMounted 加载，避免重复请求）
let _portalActivated = false
onActivated(() => {
  if (!_portalActivated) { _portalActivated = true; return }
  load()
})

function setScene(k: string) { activeScene.value = k }
function open(sol: Solution) { router.push(`/strategies/solutions/${sol.key}`) }
function create() { router.push('/strategies/solutions/new') }
function enter(to: string) { router.push(to) }
</script>

<template>
  <div class="portal">
    <!-- 左：目录树（场景 + 工作流） -->
    <aside class="side">
      <div class="side-brand">CPQ · 策略中心</div>
      <div class="side-cap">方案场景</div>
      <button
        v-for="c in chips"
        :key="c.key"
        class="tree-item"
        :class="{ on: activeScene === c.key }"
        :style="{ '--sc': hueOf(c.key) }"
        @click="setScene(c.key)"
      >
        <span class="dot"></span>{{ c.label }}<span class="n">{{ counts[c.key] || 0 }}</span>
      </button>
      <hr class="side-sep">
      <div class="side-cap">工作流</div>
      <button v-for="m in MODULES" :key="m.key" class="wf-item" :title="m.desc" @click="enter(m.to)">
        <span class="ic">{{ String(MODULES.indexOf(m) + 1).padStart(2, '0') }}</span>{{ m.title }}
      </button>
    </aside>

    <!-- 右：内容区 -->
    <main class="main">
      <div class="main-head">
        <div class="main-title">解决方案库</div>
        <div class="head-right">
          <input v-model="keyword" class="sol-search" type="search" placeholder="搜索方案、场景或关键词">
          <button class="btn-new" @click="create">＋ 新建方案</button>
        </div>
      </div>

      <!-- 场景横幅：介绍 + 方案助手咨询 -->
      <div class="hero" :style="{ '--h': heroHue }">
        <div class="hero-kicker">{{ hero.kick }}</div>
        <div class="hero-title">{{ hero.title }}</div>
        <div class="hero-desc">{{ hero.desc }}</div>
        <div class="hero-actions">
          <button v-if="auth.chatRolesAllowed" class="hero-cta" title="唤起方案助手，AI 根据客户需求推荐场景方案" @click="showAssistant()">
            <span class="sp">✦</span>方案助手咨询
          </button>
          <span class="hero-note">说出客户需求，AI 推荐匹配的场景方案</span>
        </div>
      </div>

      <div v-if="loading" class="sol-empty">加载中…</div>
      <div v-else-if="list.length === 0" class="sol-empty">{{ emptyText }}</div>
      <div v-else class="sol-grid">
        <article
          v-for="(sol, i) in list"
          :key="sol.key"
          class="sol-card"
          :style="{ '--h': hueOf(sol.scene_key), '--i': i }"
          @click="open(sol)"
        >
          <div class="plate-row"><span class="plate">{{ sol.scene }}</span></div>
          <div class="card-title">{{ sol.title }}</div>
          <div v-if="sol.sub" class="card-sub">{{ sol.sub }}</div>
          <span class="ar">→</span>
        </article>
      </div>
    </main>
  </div>
</template>

<style scoped>
.portal {
  --h-ring: color-mix(in srgb, var(--cpq-text-primary) 32%, transparent);
  --hover-bg: color-mix(in srgb, var(--cpq-text-primary) 4%, var(--cpq-glass-card-bg));
  display: flex; max-width: 1180px; margin: 0 auto;
  /* 满高壳：页面本身不滚（顶栏让位已由 .main-scroll 的占位元素垫掉），滚动收敛到 .main 内滚 */
  height: calc(100vh - var(--cpq-header-clearance, 72px)); padding: 8px 0 0;
}

/* 左：目录树 */
.side { width: 216px; flex-shrink: 0; padding: 14px 12px; border-right: 1px solid var(--cpq-glass-border); height: 100%; overflow: auto; }
.side-brand { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 10.5px; letter-spacing: .18em; color: var(--cpq-text-muted); padding: 0 10px 16px; }
.side-cap { font-size: 11px; color: var(--cpq-text-muted); letter-spacing: .1em; padding: 0 10px; margin: 4px 0 8px; }
.tree-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 8px 10px; margin-bottom: 2px; border: none; border-radius: 8px;
  background: none; color: var(--cpq-text-secondary); font-size: 13.5px; text-align: left; cursor: pointer;
  transition: background .15s, color .15s;
}
.tree-item:hover { background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); }
.tree-item.on { background: color-mix(in srgb, var(--sc, var(--cpq-accent-primary)) 12%, transparent); color: var(--cpq-text-primary); }
.tree-item.on .dot { background: var(--sc, var(--cpq-accent-primary)); box-shadow: 0 0 8px var(--sc, var(--cpq-accent-primary)); }
.tree-item .dot { width: 7px; height: 7px; border-radius: 2px; background: var(--cpq-text-muted); flex-shrink: 0; }
.tree-item .n { margin-left: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; color: var(--cpq-text-muted); }
.side-sep { border: none; border-top: 1px solid var(--cpq-glass-border); margin: 14px 10px; }
.wf-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 8px 10px; margin-bottom: 2px; border: none; border-radius: 8px;
  background: none; color: var(--cpq-text-secondary); font-size: 13px; text-align: left; cursor: pointer;
  transition: background .15s, color .15s;
}
.wf-item:hover { background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); }
.wf-item .ic { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; color: var(--cpq-text-muted); }

/* 右：内容区 */
.main { flex: 1; min-width: 0; padding: 0 4px 60px 26px; overflow-y: auto; }
.main-head {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  /* 吸顶工具条：嵌套滚动容器内一律 top:0；玻璃底带挡住从底下滚过的卡片 */
  position: sticky; top: 0; z-index: 5;
  margin: 0 -4px 8px -26px; padding: 14px 4px 12px 26px;
  background: var(--cpq-glass-card-bg); -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur)); backdrop-filter: blur(var(--cpq-glass-card-blur));
  border-bottom: 1px solid var(--cpq-glass-border);
}
.main-title { font-size: 17px; font-weight: 700; color: var(--cpq-text-primary); }
.head-right { display: flex; gap: 10px; align-items: center; }
.sol-search {
  width: 210px; height: 34px; padding: 0 12px; font-size: 13px;
  color: var(--cpq-text-primary); background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-glass-border); border-radius: 9px; outline: none;
  transition: border-color .15s;
}
.sol-search::placeholder { color: var(--cpq-text-muted); }
.sol-search:focus { border-color: var(--cpq-accent-primary); }
.btn-new {
  height: 34px; padding: 0 15px; font-size: 13px; font-weight: 600;
  color: #fff; background: var(--cpq-accent-primary); border: none; border-radius: 9px; cursor: pointer;
  transition: filter .15s;
}
.btn-new:hover { filter: brightness(1.12); }

/* 场景横幅（华为式：介绍 + 咨询 CTA） */
.hero {
  position: relative; overflow: hidden; border-radius: 16px;
  border: 1px solid color-mix(in srgb, var(--h) 38%, var(--cpq-glass-border));
  background:
    radial-gradient(90% 160% at 88% 10%, color-mix(in srgb, var(--h) 18%, transparent), transparent 62%),
    radial-gradient(60% 120% at 4% 108%, color-mix(in srgb, var(--h) 8%, transparent), transparent 55%),
    var(--cpq-glass-card-bg);
  padding: 30px 34px 28px; margin-bottom: 24px;
  transition: border-color .3s, background .3s;
}
.hero::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background-image: linear-gradient(color-mix(in srgb, var(--h) 7%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--h) 7%, transparent) 1px, transparent 1px);
  background-size: 34px 34px; mask-image: linear-gradient(100deg, transparent 42%, #000 100%);
}
.hero-kicker { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; letter-spacing: .16em; color: color-mix(in srgb, var(--h) 78%, var(--cpq-text-primary)); margin-bottom: 12px; }
.hero-title { font-size: 25px; font-weight: 800; letter-spacing: -.5px; color: var(--cpq-text-primary); margin-bottom: 10px; }
.hero-desc { font-size: 13.5px; color: var(--cpq-text-secondary); line-height: 1.75; max-width: 560px; margin-bottom: 20px; }
.hero-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.hero-cta {
  display: inline-flex; align-items: center; gap: 9px;
  height: 40px; padding: 0 20px; border-radius: 20px; border: none; cursor: pointer;
  font-size: 13.5px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, color-mix(in srgb, var(--h) 88%, #fff), var(--h));
  box-shadow: 0 8px 24px -10px color-mix(in srgb, var(--h) 80%, transparent);
  transition: transform .2s, filter .2s;
}
.hero-cta:hover { transform: translateY(-1px); filter: brightness(1.08); }
.hero-cta .sp { font-size: 15px; }
.hero-note { font-size: 11.5px; color: var(--cpq-text-muted); }

/* 方案卡：铭牌 + 标题 + 一句话；hover 走 Vercel 口径（100ms 颜色状态） */
.sol-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(258px, 1fr)); gap: 14px; }
.sol-card {
  position: relative; display: flex; flex-direction: column; gap: 8px; padding: 18px 18px 20px; cursor: pointer;
  background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border); border-radius: 14px;
  transition: color .1s, background-color .1s, border-color .1s, box-shadow .1s;
  animation: rise .4s cubic-bezier(.16, 1, .3, 1) backwards;
  animation-delay: calc(var(--i) * 40ms);
}
.sol-card:hover {
  background: var(--hover-bg);
  border-color: var(--h-ring);
  box-shadow: 0 0 0 1px var(--h-ring);
}
.sol-card:hover .card-title { color: var(--cpq-text-primary); }
.sol-card:hover .card-sub { color: var(--cpq-text-secondary); }
.sol-card:hover .ar { color: var(--cpq-text-primary); }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } }

.plate-row { display: flex; align-items: center; gap: 8px; }
.plate {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10.5px; letter-spacing: .04em;
  color: var(--h); background: color-mix(in srgb, var(--h) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--h) 45%, transparent);
  padding: 2px 9px; border-radius: 4px;
}
.card-title { font-size: 15.5px; font-weight: 600; line-height: 1.45; color: var(--cpq-text-primary); transition: color .1s; }
.card-sub { font-size: 12.5px; color: var(--cpq-text-secondary); line-height: 1.65; transition: color .1s; }
.ar { position: absolute; right: 16px; bottom: 16px; color: var(--cpq-text-muted); font-size: 14px; transition: color .1s; }

.sol-empty { color: var(--cpq-text-muted); font-size: 13px; padding: 24px 0; text-align: center; }
@media (prefers-reduced-motion: reduce) { .sol-card { animation: none !important; } }

/* 窄屏：侧栏折为横向条 */
@media (max-width: 920px) {
  .portal { flex-direction: column; height: auto; padding-bottom: 32px; }
  .side { width: auto; height: auto; border-right: none; border-bottom: 1px solid var(--cpq-glass-border); display: flex; gap: 14px; overflow-x: auto; padding: 10px 2px; align-items: center; }
  .side-brand, .side-sep { display: none; }
  .side-cap { margin: 0 2px 0 0; }
  .side .side-cap:first-of-type { margin-left: 8px; }
  .tree-item, .wf-item { width: auto; white-space: nowrap; margin-bottom: 0; }
  .main { padding-left: 0; overflow: visible; }
  .main-head { position: static; margin: 0 0 20px; padding: 0 4px 12px; background: none; -webkit-backdrop-filter: none; backdrop-filter: none; border-bottom: 1px solid var(--cpq-glass-border); }
}
</style>
