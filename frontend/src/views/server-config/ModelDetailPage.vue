<script setup lang="ts">
/** 机型产品详情页（配置面展示）— 看介绍/规格 → 点「配置这台」进配置向导。纯展示，无管理入口。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerModel } from '@/api/serverConfig'

const route = useRoute()
const router = useRouter()
const model = ref<ServerModel | null>(null)
const loading = ref(false)

const LIFECYCLES: Record<string, { label: string; chip: string }> = {
  new: { label: '新品', chip: 'lc-new' },
  active: { label: '在售', chip: 'lc-active' },
  eol: { label: '即将停产', chip: 'lc-eol' },
  discontinued: { label: '停产', chip: 'lc-off' },
}
const lcMeta = (s?: string | null) => (s && LIFECYCLES[s]) || LIFECYCLES.active

const pc = computed(() => model.value?.product_content)
const hasContent = computed(() => {
  const c = pc.value
  return !!(c && (c.overview || c.features?.length || c.specs?.length || c.scenarios?.length))
})

async function load() {
  loading.value = true
  try {
    const id = Number(route.params.modelId)
    model.value = await catalogApi.getModel(id)
  } finally { loading.value = false }
}
function back() {
  const tid = model.value?.server_type_id
  router.push(tid ? `/servers/types/${tid}` : '/servers')
}
function configure() { if (model.value) router.push(`/servers/config/${model.value.id}`) }
onMounted(load)
</script>

<template>
  <div class="detail-page">
    <div class="page-inner">
      <div class="breadcrumb">
        <a-button type="text" @click="back" class="back-btn">
          <template #icon><span style="font-size:16px">←</span></template>
          返回机型目录
        </a-button>
      </div>

      <a-spin :spinning="loading">
        <div v-if="model" class="detail-body">
          <!-- 头部：主图 + 标题 + 规格 + 生命周期 -->
          <section class="hero glass">
            <div class="hero-thumb">
              <img v-if="model.image_url" :src="model.image_url" :alt="model.name" />
              <span v-else class="thumb-ph">机</span>
            </div>
            <div class="hero-info">
              <div class="hero-top">
                <h1 class="hero-name">{{ model.name }}</h1>
                <span class="lc-chip" :class="lcMeta(model.lifecycle_status).chip">{{ lcMeta(model.lifecycle_status).label }}</span>
              </div>
              <div class="hero-specs">
                <span><i>形态</i><b>{{ model.base_config?.form || '—' }}</b></span>
                <span><i>盘位</i><b>{{ model.base_config?.bays ?? '—' }}</b></span>
                <span><i>系列</i><b>{{ model.base_config?.series || '—' }}</b></span>
              </div>
              <div class="hero-actions">
                <a-button type="primary" size="large" @click="configure">配置这台服务器 →</a-button>
              </div>
            </div>
          </section>

          <section v-if="pc?.overview" class="block glass">
            <h3 class="block-title">产品概述</h3>
            <p class="overview-text">{{ pc.overview }}</p>
          </section>

          <section v-if="pc?.scenarios?.length" class="block glass">
            <h3 class="block-title">应用场景</h3>
            <div class="tag-list">
              <span v-for="(s, i) in pc.scenarios" :key="i" class="scenario-tag">{{ s }}</span>
            </div>
          </section>

          <section v-if="pc?.features?.length" class="block glass">
            <h3 class="block-title">核心特性</h3>
            <ul class="feature-list">
              <li v-for="(f, i) in pc.features" :key="i">
                <span class="feat-icon" v-if="f.icon">{{ f.icon }}</span>
                <span class="feat-dot" v-else></span>
                <span class="feat-text">{{ f.text }}</span>
              </li>
            </ul>
          </section>

          <section v-if="pc?.specs?.length" class="block glass">
            <h3 class="block-title">产品规格</h3>
            <div class="spec-table">
              <div v-for="(s, i) in pc.specs" :key="i" class="spec-row">
                <span class="spec-k">{{ s.key }}</span>
                <span class="spec-v">{{ s.value }}</span>
              </div>
            </div>
          </section>

          <section v-if="!hasContent" class="block glass empty-content">
            该机型尚未补充产品介绍。
          </section>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<style scoped>
.detail-page { padding: 4px 0 80px; }
.page-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; }
.breadcrumb { margin-bottom: 20px; }
.back-btn { color: var(--cpq-text-secondary, #9BA1AA); font-size: 14px; padding: 4px 8px; }
.back-btn:hover { color: var(--cpq-accent-primary, #1677FF); }

.hero { display: flex; gap: 28px; padding: 28px; margin-bottom: 20px; align-items: center; }
.hero-thumb { flex: 0 0 240px; height: 200px; border-radius: 12px; overflow: hidden; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); display: flex; align-items: center; justify-content: center; }
.hero-thumb img { width: 100%; height: 100%; object-fit: contain; }
.thumb-ph { font-size: 40px; font-weight: 700; color: var(--cpq-text-muted, #6E7582); opacity: .4; }
.hero-info { flex: 1; min-width: 0; }
.hero-top { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.hero-name { font-size: 26px; font-weight: 700; margin: 0; color: var(--cpq-text-primary, #E8ECEF); }
.hero-specs { display: flex; gap: 28px; padding: 12px 0; border-top: 1px solid var(--cpq-overlay-w10); border-bottom: 1px solid var(--cpq-overlay-w10); margin-bottom: 18px; }
.hero-specs span { display: flex; flex-direction: column; }
.hero-specs i { font-size: 12px; font-style: normal; color: var(--cpq-text-muted, #6E7582); }
.hero-specs b { font-size: 16px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.hero-actions { display: flex; gap: 10px; }

.lc-chip { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; border: 1px solid transparent; }
.lc-active { color: #1f9d6b; background: rgba(125, 215, 170, .18); border-color: rgba(125, 215, 170, .45); }
.lc-new    { color: #2f7de1; background: rgba(150, 195, 250, .18); border-color: rgba(150, 195, 250, .45); }
.lc-eol    { color: #c8861a; background: rgba(245, 200, 110, .18); border-color: rgba(245, 200, 110, .45); }
.lc-off    { color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w6); border-color: var(--cpq-overlay-w15); }

.block { padding: 22px 26px; margin-bottom: 16px; }
.block-title { font-size: 16px; font-weight: 600; margin: 0 0 14px; color: var(--cpq-text-primary, #E8ECEF); }
.overview-text { font-size: 14px; line-height: 1.8; color: var(--cpq-text-secondary, #9BA1AA); margin: 0; white-space: pre-wrap; }

.tag-list { display: flex; flex-wrap: wrap; gap: 8px; }
.scenario-tag { font-size: 13px; padding: 4px 12px; border-radius: 999px; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a15, rgba(22, 119, 255, .15)); border: 1px solid var(--cpq-overlay-a30, rgba(22, 119, 255, .3)); }

.feature-list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.feature-list li { display: flex; gap: 10px; align-items: flex-start; font-size: 14px; color: var(--cpq-text-secondary, #9BA1AA); line-height: 1.5; }
.feat-icon { flex: 0 0 auto; color: var(--cpq-accent-primary, #1677FF); font-size: 16px; line-height: 1.4; }
.feat-dot { flex: 0 0 auto; width: 6px; height: 6px; margin-top: 8px; border-radius: 50%; background: var(--cpq-accent-primary, #1677FF); box-shadow: 0 0 6px var(--cpq-overlay-a30, rgba(22, 119, 255, .3)); }
.feat-text { flex: 1; min-width: 0; }

.spec-table { display: flex; flex-direction: column; border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; overflow: hidden; }
.spec-row { display: flex; border-bottom: 1px solid var(--cpq-overlay-w10); }
.spec-row:last-child { border-bottom: none; }
.spec-k { flex: 0 0 180px; padding: 10px 14px; font-size: 13px; color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w4); }
.spec-v { flex: 1; padding: 10px 14px; font-size: 14px; color: var(--cpq-text-primary, #E8ECEF); white-space: pre-wrap; }

.empty-content { text-align: center; color: var(--cpq-text-muted, #6E7582); font-size: 14px; }

@media (max-width: 720px) {
  .hero { flex-direction: column; }
  .hero-thumb { flex: none; width: 100%; }
  .spec-k { flex: 0 0 120px; }
}
</style>
