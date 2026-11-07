<script setup lang="ts">
defineOptions({ name: 'StrategyPortal' })
/** 解决方案门户(/strategies)——全宽横幅布局。
 *  顶部:吸顶工具行(场景胶囊过滤 + 搜索/新建方案);
 *  横幅:全宽 hero(左=场景介绍 + 方案助手咨询 CTA);
 *  下方:固定 3 列方案卡网格(封面 + 场景铭牌 + 标题 + 一句话摘要)。 */
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { solutionApi, type Solution, type SolutionScene } from '@/api/solutions'
import { useAssistantShell } from '@/composables/useAssistantShell'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const auth = useAuthStore()
const { show: showAssistant } = useAssistantShell()

/* ── 工作流入口（横幅右肩） ── */


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

/* ── 杂志卡辅助：摘要 / 阅读时长 / 日期 ── */
// 摘要：intro 去 Markdown 标记 → 纯文本；无 intro 回落 sub
function plainOf(sol: Solution): string {
  const src = sol.intro || sol.sub || ''
  return src.replace(/[#*`>\-\[\]()!]/g, '').replace(/\s+/g, ' ').trim()
}
// 阅读时长：中文按字数 / 400字每分钟，英文按词数 / 200wpm，最低 1 分钟
function readMinutesOf(sol: Solution): number {
  const text = (sol.intro || '') + ' ' + (sol.content_md || '')
  const cjk = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const words = text.replace(/[\u4e00-\u9fff]/g, ' ').split(/\s+/).filter(Boolean).length
  return Math.max(1, Math.round(cjk / 400 + words / 200))
}
function dateOf(sol: Solution): string {
  const raw = sol.updated_at || sol.created_at
  if (!raw) return ''
  const d = new Date(raw)
  return isNaN(d.getTime()) ? '' : `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}
// 自动封面：按 key 做确定性伪随机，同一方案每次渲染同一图案（无闪烁）
function coverSeedOf(key: string): number {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
  return h
}
</script>

<template>
  <div class="portal">
    <main class="main">
      <!-- 全宽横幅：左=场景介绍 + 方案助手咨询 -->
      <div class="hero" :style="{ '--h': heroHue }">
        <div class="hero-main">
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
      </div>

      <!-- 列表工具行：场景 tabs（左） + 搜索/新建（右）；横幅之后、卡片之前 -->
      <div class="main-head">
        <div class="scene-row">
          <button
            v-for="c in chips"
            :key="c.key"
            class="chip"
            :class="{ on: activeScene === c.key }"
            :style="{ '--sc': hueOf(c.key) }"
            @click="setScene(c.key)"
          >
            {{ c.label }}<span class="n">{{ counts[c.key] || 0 }}</span>
          </button>
        </div>
        <div class="head-right">
          <input v-model="keyword" class="sol-search" type="search" placeholder="搜索方案、场景或关键词">
          <button class="btn-new" @click="create">＋ 新建方案</button>
        </div>
      </div>

      <div v-if="loading" class="sol-empty">加载中…</div>
      <div v-else-if="list.length === 0" class="sol-empty">{{ emptyText }}</div>
      <div v-else class="sol-grid">
        <article
          v-for="(sol, i) in list"
          :key="sol.key"
          class="sol-card"
          :style="{ '--h': hueOf(sol.scene_key), '--i': i, '--seed': coverSeedOf(sol.key) }"
          @click="open(sol)"
        >
          <div class="cover">
            <img v-if="sol.cover_url" :src="sol.cover_url" alt="">
            <div v-else class="cover-gen">
              <span class="cover-mono">{{ sol.scene }}</span>
            </div>
          </div>
          <div class="card-body">
            <div class="meta-row">
              <span class="plate">{{ sol.scene }}</span>
              <span v-if="dateOf(sol)" class="meta-date">{{ dateOf(sol) }}</span>
            </div>
            <div class="card-title">{{ sol.title }}</div>
            <div v-if="plainOf(sol)" class="card-sub">{{ plainOf(sol) }}</div>
            <div class="foot-row">
              <span class="read-min">约 {{ readMinutesOf(sol) }} 分钟阅读</span>
              <span class="read-more">阅读全文 <span class="ar">→</span></span>
            </div>
          </div>
        </article>
      </div>
    </main>
  </div>
</template>

<style scoped>
.portal {
  --hover-bg: color-mix(in srgb, var(--cpq-text-primary) 4%, var(--cpq-glass-card-bg));
  max-width: 1180px; margin: 0 auto;
  /* 满高壳：页面本身不滚（顶栏让位已由 .main-scroll 的占位元素垫掉），滚动收敛到 .main 内滚 */
  height: calc(100vh - var(--cpq-header-clearance, 72px)); padding: var(--cpq-space-2) 0 0;
}
.main { height: 100%; overflow-y: auto; padding: 0 var(--cpq-space-5) 60px; }

/* 列表工具行：场景 tabs（左） + 搜索/新建（右）；常规流内不吸顶，轻编辑风格 */
.main-head {
  display: flex; align-items: center; justify-content: space-between; gap: var(--cpq-space-4);
  margin-bottom: var(--cpq-space-5); padding-bottom: var(--cpq-space-3);
  border-bottom: 1px solid var(--cpq-glass-border);
}
.scene-row { display: flex; align-items: baseline; gap: var(--cpq-space-4); min-width: 0; overflow-x: auto; }
.chip {
  display: inline-flex; align-items: baseline; gap: var(--cpq-space-1);
  padding: 0 0 var(--cpq-space-2); border: none; border-bottom: 2px solid transparent;
  background: none; color: var(--cpq-text-secondary); font-size: var(--cpq-font-size-base); white-space: nowrap; cursor: pointer;
  transition: color .15s, border-color .15s;
}
.chip:hover { color: var(--cpq-text-primary); }
.chip.on { color: var(--cpq-text-primary); font-weight: 600; border-bottom-color: var(--sc, var(--cpq-accent-primary)); }
.chip .n { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.head-right { display: flex; gap: var(--cpq-space-2); align-items: center; flex-shrink: 0; }
.sol-search {
  width: 210px; height: 34px; padding: 0 12px; font-size: 13px;
  color: var(--cpq-text-primary); background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-sm); outline: none;
  transition: border-color .15s;
}
.sol-search::placeholder { color: var(--cpq-text-muted); }
.sol-search:focus { border-color: var(--cpq-accent-primary); }
.btn-new {
  height: 34px; padding: 0 15px; font-size: 13px; font-weight: 600; white-space: nowrap;
  color: #fff; background: var(--cpq-accent-primary); border: none; border-radius: var(--cpq-radius-sm); cursor: pointer;
  transition: filter .15s;
}
.btn-new:hover { filter: brightness(1.12); }

/* 全宽横幅：左=场景介绍 + 方案助手咨询，右肩=工作流三入口 */
.hero {
  position: relative; overflow: hidden; display: flex; gap: var(--cpq-space-6); border-radius: var(--cpq-radius-lg);
  border: 1px solid color-mix(in srgb, var(--h) 38%, var(--cpq-glass-border));
  background:
    radial-gradient(90% 160% at 88% 10%, color-mix(in srgb, var(--h) 18%, transparent), transparent 62%),
    radial-gradient(60% 120% at 4% 108%, color-mix(in srgb, var(--h) 8%, transparent), transparent 55%),
    var(--cpq-glass-card-bg);
  padding: var(--cpq-space-6); margin-bottom: var(--cpq-space-5);
  transition: border-color .3s, background .3s;
}
.hero::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background-image: linear-gradient(color-mix(in srgb, var(--h) 7%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--h) 7%, transparent) 1px, transparent 1px);
  background-size: 34px 34px; mask-image: linear-gradient(100deg, transparent 42%, #000 100%);
}
.hero-main { flex: 1; min-width: 0; }
.hero-kicker { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: var(--cpq-font-size-xs); letter-spacing: .16em; color: color-mix(in srgb, var(--h) 78%, var(--cpq-text-primary)); margin-bottom: var(--cpq-space-3); }
.hero-title { font-size: var(--cpq-font-size-3xl); font-weight: 800; letter-spacing: -.5px; color: var(--cpq-text-primary); margin-bottom: var(--cpq-space-2); }
.hero-desc { font-size: var(--cpq-font-size-base); color: var(--cpq-text-secondary); line-height: 1.75; max-width: 560px; margin-bottom: var(--cpq-space-5); }
.hero-actions { display: flex; align-items: center; gap: var(--cpq-space-4); flex-wrap: wrap; }
.hero-cta {
  display: inline-flex; align-items: center; gap: 9px;
  height: 40px; padding: 0 var(--cpq-space-5); border-radius: var(--cpq-radius-xl); border: none; cursor: pointer;
  font-size: var(--cpq-font-size-base); font-weight: 700; color: #fff;
  background: linear-gradient(135deg, color-mix(in srgb, var(--h) 88%, #fff), var(--h));
  box-shadow: 0 8px 24px -10px color-mix(in srgb, var(--h) 80%, transparent);
  transition: transform .2s, filter .2s;
}
.hero-cta:hover { transform: translateY(-1px); filter: brightness(1.08); }
.hero-cta .sp { font-size: 15px; }
.hero-note { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }


/* 方案卡：杂志式（封面 + 元信息 + 标题 + 摘要 + 阅读全文）；hover 走 Vercel 口径（100ms 颜色状态） */
.sol-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--cpq-space-4); }
.sol-card {
  position: relative; display: flex; flex-direction: column; overflow: hidden; cursor: pointer;
  background: var(--cpq-glass-card-bg); border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-xl);
  transition: color .1s, background-color .1s, border-color .1s, box-shadow .1s;
  animation: rise .4s cubic-bezier(.16, 1, .3, 1) backwards;
  animation-delay: calc(var(--i) * 40ms);
}
.sol-card:hover {
  background: var(--hover-bg);
  border-color: color-mix(in srgb, var(--h) 50%, var(--cpq-glass-border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--h) 50%, transparent);
}
.sol-card:hover .card-title { color: var(--cpq-text-primary); }
.sol-card:hover .read-more { color: var(--h); }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } }

/* 封面：固定高度横带（不抢卡片主体），自动封面用场景色渐变 + seed 驱动的图案角度/位置（确定性，无闪烁） */
.cover { aspect-ratio: 16 / 10; position: relative; overflow: hidden; border-bottom: 1px solid var(--cpq-glass-border); flex-shrink: 0; }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-gen {
  position: absolute; inset: 0; display: flex; align-items: flex-end;
  padding: var(--cpq-space-3) var(--cpq-space-4);
  background:
    radial-gradient(120% 200% at calc(78% + (var(--seed) % 3) * 6%) calc(-40% + (var(--seed) % 4) * 14%),
      color-mix(in srgb, var(--h) 42%, transparent), transparent 62%),
    radial-gradient(90% 160% at 8% 130%, color-mix(in srgb, var(--h) 20%, transparent), transparent 58%),
    var(--cpq-overlay-w6);
}
.cover-gen::after {
  content: ''; position: absolute; inset: 0; pointer-events: none; opacity: .5;
  background-image: linear-gradient(color-mix(in srgb, var(--h) 10%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--h) 10%, transparent) 1px, transparent 1px);
  background-size: 30px 30px;
  transform: rotate(calc((var(--seed) % 7 - 3) * 2deg)) scale(1.4);
  mask-image: linear-gradient(115deg, transparent 30%, #000 100%);
}
.cover-mono {
  position: relative; z-index: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: var(--cpq-font-size-xs); letter-spacing: .16em; text-transform: uppercase;
  color: color-mix(in srgb, var(--h) 82%, var(--cpq-text-primary));
}

.card-body { display: flex; flex-direction: column; gap: var(--cpq-space-2); padding: var(--cpq-space-4); flex: 1; }
.meta-row { display: flex; align-items: center; gap: var(--cpq-space-2); }
.plate {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: var(--cpq-font-size-xs); letter-spacing: .04em;
  color: var(--h); background: color-mix(in srgb, var(--h) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--h) 45%, transparent);
  padding: 2px 9px; border-radius: var(--cpq-radius-xs);
}
.meta-date { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.card-title {
  font-size: var(--cpq-font-size-lg); font-weight: 700; line-height: 1.45; color: var(--cpq-text-primary);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  transition: color .1s;
}
.card-sub {
  font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); line-height: 1.65; transition: color .1s;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.foot-row { display: flex; align-items: center; justify-content: space-between; margin-top: auto; padding-top: var(--cpq-space-2); }
.read-min { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.read-more { font-size: var(--cpq-font-size-sm); font-weight: 600; color: var(--cpq-text-secondary); transition: color .1s; }
.read-more .ar { font-size: var(--cpq-font-size-sm); }

.sol-empty { color: var(--cpq-text-muted); font-size: 13px; padding: 24px 0; text-align: center; }
@media (prefers-reduced-motion: reduce) { .sol-card { animation: none !important; } }

/* 中屏收列：≤1200 四列收三列 */
@media (max-width: 1200px) {
  .sol-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

/* 窄屏：工具行换行，横幅改纵向堆叠，卡两列 */
@media (max-width: 920px) {
  .portal { height: auto; padding-bottom: var(--cpq-space-6); }
  .main { height: auto; overflow: visible; padding: 0 var(--cpq-space-4) 0; }
  .main-head { flex-wrap: wrap; gap: var(--cpq-space-2) var(--cpq-space-4); }
  .scene-row { flex: 1; min-width: 0; }
  .head-right { flex: 1 1 100%; }
  .sol-search { flex: 1; width: auto; min-width: 0; }
  .btn-new { flex-shrink: 0; }
  .sol-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero { flex-direction: column; gap: 0; padding: var(--cpq-space-5) var(--cpq-space-4); }
}

/* 手机：卡单列，横幅边距再收一档 */
@media (max-width: 640px) {
  .sol-grid { grid-template-columns: minmax(0, 1fr); gap: var(--cpq-space-3); }
  .hero { padding: var(--cpq-space-4); }
  .main { padding: 0 var(--cpq-space-3) 0; }
}
</style>
