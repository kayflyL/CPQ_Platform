<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { solutionApi, type Solution, type SolutionScene } from '@/api/solutions'

const router = useRouter()
const activeScene = ref('all')
const solutions = ref<Solution[]>([])
const loading = ref(false)
const scenes = ref<SolutionScene[]>([])
const chips = computed(() => [{ key: 'all', label: '全部' }, ...scenes.value])

const list = computed(() => activeScene.value === 'all'
  ? solutions.value
  : solutions.value.filter(s => s.scene_key === activeScene.value))

onMounted(async () => {
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
})

function setScene(k: string) { activeScene.value = k }
function open(sol: Solution) { router.push(`/strategies/solutions/${sol.key}`) }
function create() { router.push('/strategies/solutions/new') }
</script>

<template>
  <section class="sol-lib">
    <header class="sol-head">
      <div class="sol-headleft">
        <h2 class="sol-title">解决方案库</h2>
        <p class="sol-sub">按应用场景分类，点击卡片进入完整方案与适配平台。</p>
      </div>
      <a-button type="primary" @click="create">+ 新建方案</a-button>
    </header>

    <div class="scen-row">
      <button
        v-for="c in chips"
        :key="c.key"
        class="scen-chip"
        :class="{ on: activeScene === c.key }"
        @click="setScene(c.key)"
      >{{ c.label }}</button>
    </div>

    <div v-if="loading" class="sol-empty">加载中…</div>
    <div v-else-if="list.length === 0" class="sol-empty">该场景暂无解决方案，点右上角新建。</div>
    <div v-else class="sol-grid">
      <article
        v-for="sol in list"
        :key="sol.key"
        class="sol-card glass-light"
        @click="open(sol)"
      >
        <div class="card-accent-bar"></div>
        <div class="card-header">
          <span class="card-category-tag">{{ sol.scene }}</span>
        </div>
        <h3 class="sol-title">{{ sol.title }}</h3>
        <div class="sol-feats">
          <span v-for="f in sol.features" :key="f" class="sol-feat">{{ f }}</span>
        </div>
        <div class="sol-go">
          <span class="sol-count">{{ sol.platforms?.length || 0 }} 个适配平台</span> · 查看方案 →
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.sol-lib { margin-top: 6px; }
.sol-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.sol-headleft { min-width: 0; }
.sol-title { font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); margin: 0 0 4px; }
.sol-sub { font-size: 13px; color: var(--cpq-text-muted); margin: 0; }
.scen-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
.scen-chip { font-size: 12.5px; color: var(--cpq-text-secondary); background: var(--cpq-overlay-w6); border: 1px solid var(--cpq-glass-border); padding: 6px 14px; border-radius: 20px; cursor: pointer; transition: all .15s; }
.scen-chip:hover { border-color: var(--cpq-glass-border-strong); }
.scen-chip.on { color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border-color: var(--cpq-accent-primary); font-weight: 600; }
.sol-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.sol-card { position: relative; overflow: hidden; padding: 18px; cursor: pointer; transition: transform 0.25s var(--cpq-ease-out-expo), box-shadow 0.25s var(--cpq-ease-out-expo); animation: fadeInUp 0.4s var(--cpq-ease-out-expo) backwards; }
.sol-card:hover { transform: translateY(-3px); box-shadow: var(--cpq-glass-card-shadow-hover); }
.card-accent-bar { position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--cpq-accent-primary); transform: scaleX(0); transform-origin: left center; transition: transform 0.3s var(--cpq-ease-out-expo); }
.sol-card:hover .card-accent-bar { transform: scaleX(1); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-category-tag { font-size: 11px; font-weight: 500; color: var(--cpq-accent-primary); letter-spacing: 0.2px; padding: 2px 10px; border-radius: 10px; background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a20); }
.sol-title { font-size: 16px; font-weight: 700; color: var(--cpq-text-primary); margin: 0 0 10px; line-height: 1.35; }
.sol-feats { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.sol-feat { font-size: 10.5px; color: var(--cpq-text-muted); background: var(--cpq-overlay-w6); padding: 2px 8px; border-radius: 10px; }
.sol-go { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--cpq-text-muted); margin-top: auto; padding-top: 10px; border-top: 1px solid var(--cpq-border-primary); }
.sol-count { color: var(--cpq-accent-primary); font-size: 11.5px; font-weight: 600; }
.sol-empty { color: var(--cpq-text-muted); font-size: 13px; padding: 24px 0; text-align: center; }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
</style>
