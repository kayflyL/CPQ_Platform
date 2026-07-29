<script setup lang="ts">
/** 机型产品详情页（配置面展示）— 看介绍/规格 → 点「配置这台」进配置向导。纯展示，无管理入口。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerModel } from '@/api/serverConfig'
import { useSeriesStore } from '@/stores/series'

const route = useRoute()
const router = useRouter()
const model = ref<ServerModel | null>(null)
const loading = ref(false)
const seriesStore = useSeriesStore()

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

const seriesRaw = computed(() => model.value?.base_config?.series || '')
const seriesLabel = computed(() => {
  const found = seriesStore.items.find(i => i.value === seriesRaw.value)
  return found?.label || seriesRaw.value || 'Polaris'
})

// 场景主题：天空渐变 + 大地遮罩 + 旭日三色（sun 光带/sunBright 中心/sun 光晕），集中管理
type StageThemeKey = 'wine' | 'ocean' | 'carbon' | 'violet'
interface StageTheme {
  key: StageThemeKey; label: string
  bg: string        // 天空→大地 整体垂直渐变
  earth: string     // 地平线下方遮罩（盖住太阳下半、加深大地）
  sun: string       // 地平线 / 太阳主色
  sunBright: string // 太阳最亮中心
  glow: string      // 天空光晕扩散
}
const STAGE_THEMES: StageTheme[] = [
  { key: 'wine', label: '酒红',
    bg: 'linear-gradient(to bottom, #1a0509 0%, #4a0e1f 28%, #7a1a2e 58%, #5a1228 70%, #2d0712 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(20,4,10,0.85) 35%, #0a0205 100%)',
    sun: '#FF7A4D', sunBright: '#FFE0C0', glow: 'rgba(255,122,77,0.55)' },
  { key: 'ocean', label: '深蓝',
    bg: 'linear-gradient(to bottom, #030814 0%, #0a1830 28%, #143a6b 58%, #0e2a52 70%, #06101f 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(3,8,20,0.85) 35%, #020610 100%)',
    sun: '#5BB8FF', sunBright: '#D6EBFF', glow: 'rgba(91,184,255,0.55)' },
  { key: 'carbon', label: '纯黑',
    bg: 'linear-gradient(to bottom, #050505 0%, #1a1a1a 28%, #2e2e2e 58%, #222222 70%, #0a0a0a 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(5,5,5,0.85) 35%, #000000 100%)',
    sun: '#E8E8E8', sunBright: '#FFFFFF', glow: 'rgba(232,232,232,0.45)' },
  { key: 'violet', label: '暗紫',
    bg: 'linear-gradient(to bottom, #0a0218 0%, #1e0a3c 28%, #3d1a6b 58%, #2a1252 70%, #120420 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(10,2,24,0.85) 35%, #06010f 100%)',
    sun: '#B07AFF', sunBright: '#E8D0FF', glow: 'rgba(176,122,255,0.55)' },
]
const stageTheme = ref<StageThemeKey>('wine')
const stageVars = computed(() => {
  const t = STAGE_THEMES.find(x => x.key === stageTheme.value) || STAGE_THEMES[0]
  return {
    '--sun-color': t.sun,
    '--sun-bright': t.sunBright,
    '--sun-glow': t.glow,
    '--earth-overlay': t.earth,
  } as Record<string, string>
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
onMounted(() => {
  load()
  seriesStore.ensureSeries()
})
</script>

<template>
  <div class="detail-page">
    <a-spin :spinning="loading">
      <template v-if="model">
        <!-- 全宽场景 hero：天空 / 旭日地平线 / 大地，服务器立在大地上 -->
        <section class="hero-scene" :style="stageVars">
          <!-- 背景：天空→大地 渐变（4 主题堆叠，opacity 过渡） -->
          <div class="scene-bg" aria-hidden="true">
            <div
              v-for="t in STAGE_THEMES"
              :key="t.key"
              class="scene-bg-layer"
              :style="{ background: t.bg, opacity: stageTheme === t.key ? 1 : 0 }"
            ></div>
          </div>

          <!-- 水印（系列类别名，铺底，永远在最后方） -->
          <div class="scene-watermark" aria-hidden="true">{{ seriesLabel }}</div>

          <!-- 天空光晕（旭日映亮地平线上方天空） -->
          <div class="scene-sky-glow" aria-hidden="true"></div>

          <!-- 旭日太阳（半圆露在地平线上） -->
          <div class="scene-sun" aria-hidden="true"></div>

          <!-- 大地遮罩（地平线下方，盖太阳下半 + 加深大地） -->
          <div class="scene-earth" aria-hidden="true"></div>

          <!-- 地面光晕（地平线下方旭日投射，照亮倒影区域） -->
          <div class="scene-ground-glow" aria-hidden="true"></div>

          <!-- 倒影（大地上的镜像，地平线下方） -->
          <div v-if="model.image_url" class="scene-reflection" aria-hidden="true">
            <img :src="model.image_url" alt="" />
          </div>

          <!-- 旭日地平线光带（切割服务器与倒影，横贯，中间最亮） -->
          <div class="scene-horizon" aria-hidden="true"></div>

          <!-- 服务器本体（立在大地/地平线上，放大居中） -->
          <div class="scene-product">
            <img v-if="model.image_url" class="product-img" :src="model.image_url" :alt="model.name" />
            <span v-else class="product-ph">{{ model.name?.charAt(0) || '机' }}</span>
          </div>

          <!-- 左上角返回 -->
          <a-button type="text" @click="back" class="scene-back">
            <template #icon><span style="font-size:16px">←</span></template>
            返回机型目录
          </a-button>

          <!-- 右上角生命周期标签 -->
          <span class="lc-chip scene-chip" :class="lcMeta(model.lifecycle_status).chip">{{ lcMeta(model.lifecycle_status).label }}</span>

          <!-- 底部配色切换 -->
          <div class="scene-switch">
            <button
              v-for="t in STAGE_THEMES"
              :key="t.key"
              type="button"
              class="scene-switch-btn"
              :class="{ active: stageTheme === t.key }"
              @click="stageTheme = t.key"
            >{{ t.label }}</button>
          </div>
        </section>

        <!-- 限宽内容（原样保留） -->
        <div class="page-inner">
          <div class="detail-body">
            <section class="hero-meta glass">
              <div class="meta-head">
                <h1 class="meta-name">{{ model.name }}</h1>
                <div class="meta-specs">
                  <span><i>形态</i><b>{{ model.base_config?.form || '—' }}</b></span>
                  <span><i>盘位</i><b>{{ model.base_config?.bays ?? '—' }}</b></span>
                  <span><i>系列</i><b>{{ seriesLabel }}</b></span>
                </div>
              </div>
              <div class="hero-actions">
                <a-button type="primary" size="large" @click="configure">配置这台服务器 →</a-button>
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

            <section v-if="pc?.features?.length" class="block block-plain">
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
        </div>
      </template>
    </a-spin>
  </div>
</template>

<style scoped>
.detail-page { padding: 0 0 80px; }

/* —— 全宽场景 hero：天空 / 旭日地平线 / 大地 —— */
/* z 序：背景0 → 水印1 → 天空光晕2 → 太阳3 → 大地4 → 倒影5 → 地平线光带6 → 服务器7 → UI8 */
.hero-scene {
  position: relative;
  width: 100%;
  min-height: 640px;
  overflow: hidden;
  background: #0a0508;
  color: #fff;
}

/* 背景：天空→大地 整体渐变（4 主题堆叠） */
.scene-bg { position: absolute; inset: 0; z-index: 0; }
.scene-bg-layer { position: absolute; inset: 0; transition: opacity 0.7s ease; }

/* 水印 */
.scene-watermark {
  position: absolute; inset: 0; z-index: 1;
  display: flex; align-items: center; justify-content: center;
  font-size: clamp(150px, 26vw, 340px);
  font-weight: 900;
  letter-spacing: -0.03em;
  color: #ffffff;
  opacity: 0.06;
  white-space: nowrap;
  text-transform: uppercase;
  pointer-events: none; user-select: none;
}

/* 天空光晕（旭日映亮地平线上方） */
.scene-sky-glow {
  position: absolute;
  left: 0; right: 0;
  bottom: 30%;            /* 地平线位置 */
  height: 55%;
  background: radial-gradient(ellipse 60% 100% at 50% 100%, var(--sun-glow) 0%, transparent 62%);
  z-index: 2;
  pointer-events: none;
}

/* 旭日辉光（扁椭圆贴地平线，上半映亮天空下半被大地遮；重模糊柔化，换图挡不住也不突兀） */
.scene-sun {
  position: absolute;
  left: 50%;
  bottom: 30%;            /* 中心落于地平线 */
  width: 520px;
  height: 200px;
  transform: translate(-50%, 50%);
  border-radius: 50%;
  background: radial-gradient(ellipse at center, var(--sun-bright) 0%, var(--sun-color) 36%, transparent 70%);
  opacity: 0.85;
  filter: blur(12px);
  z-index: 3;
  pointer-events: none;
}

/* 大地遮罩（地平线下方，盖太阳下半 + 加深大地） */
.scene-earth {
  position: absolute;
  left: 0; right: 0;
  bottom: 0;
  height: 30%;
  background: var(--earth-overlay);
  z-index: 4;
  pointer-events: none;
}

/* 地面光晕（地平线下方旭日投射，照亮倒影区域，让倒影更显眼） */
.scene-ground-glow {
  position: absolute;
  left: 0; right: 0;
  bottom: 0;
  height: 30%;
  background: radial-gradient(ellipse 55% 95% at 50% 0%, var(--sun-glow) 0%, transparent 62%);
  opacity: 0.6;
  z-index: 4;
  pointer-events: none;
}

/* 倒影（大地上的镜像，顶部紧贴地平线/服务器底部，向下延伸进大地） */
.scene-reflection {
  position: absolute;
  left: 50%;
  top: 70%;            /* 倒影顶部 = 地平线 = 服务器底部 */
  margin-top: -16px;   /* 上移贴近服务器底部（重叠部分被服务器盖，视觉紧贴） */
  width: 540px;
  max-width: 64vw;
  transform: translateX(-50%);
  opacity: 0.6;
  z-index: 5;
  pointer-events: none;
  -webkit-mask: linear-gradient(to bottom, rgba(0,0,0,0.95) 0%, transparent 58%);
  mask: linear-gradient(to bottom, rgba(0,0,0,0.95) 0%, transparent 58%);
}
.scene-reflection img {
  width: 100%;
  object-fit: contain;
  display: block;
  transform: scaleY(-1);   /* 图片翻转 = 镜面倒影 */
  filter: blur(2px);
}

/* 旭日地平线光带（切割服务器与倒影；横贯，中间最亮如日出） */
.scene-horizon {
  position: absolute;
  left: -8%; right: -8%;
  bottom: 30%;            /* 地平线 = 服务器站立线 */
  height: 0;
  z-index: 6;
  pointer-events: none;
  border-top: 2px solid transparent;
  background: linear-gradient(to right,
    transparent 0%,
    var(--sun-color) 22%,
    var(--sun-bright) 50%,
    var(--sun-color) 78%,
    transparent 100%);
  background-size: 100% 2px;
  background-position: 0 0;
  background-repeat: no-repeat;
  box-shadow:
    0 0 24px var(--sun-color),
    0 0 50px var(--sun-color),
    0 -6px 70px var(--sun-glow),
    0 6px 70px var(--sun-glow);
}

/* 服务器本体（放大居中，底部接地平线） */
.scene-product {
  position: absolute;
  left: 50%;
  bottom: 30%;            /* 底部立于地平线 */
  transform: translateX(-50%);
  z-index: 7;
  display: flex;
  justify-content: center;
}
.product-img {
  width: 540px;
  max-width: 64vw;
  object-fit: contain;
  filter: drop-shadow(0 4px 18px rgba(0, 0, 0, 0.5));
}
.product-ph {
  width: 540px;
  max-width: 64vw;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 96px;
  font-weight: 800;
  color: var(--sun-color);
  opacity: 0.4;
}

/* —— UI 浮层 —— */
.scene-back {
  position: absolute;
  top: 22px; left: 28px;
  z-index: 8;
  color: rgba(255, 255, 255, 0.78) !important;
}
.scene-back:hover { color: #fff !important; }

.scene-chip { position: absolute; top: 24px; right: 28px; z-index: 8; }

.scene-switch {
  position: absolute;
  bottom: 26px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 8;
  display: flex;
  gap: 8px;
}
.scene-switch-btn {
  padding: 6px 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.72);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: all 0.25s ease;
}
.scene-switch-btn:hover { background: rgba(255, 255, 255, 0.16); color: #fff; }
.scene-switch-btn.active {
  color: #fff;
  background: rgba(255, 255, 255, 0.24);
  border-color: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 14px rgba(255, 255, 255, 0.22);
}

/* —— 下方限宽内容（原样保留） —— */
.page-inner { max-width: 1100px; margin: 0 auto; padding: 24px 24px 0; }
.detail-body { }

.hero-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  padding: 20px 28px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.meta-head { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.meta-name {
  margin: 0;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 0.01em;
  line-height: 1.2;
  color: var(--cpq-text-primary, #1F2430);
}
.meta-specs { display: flex; gap: 36px; }
.meta-specs span { display: flex; flex-direction: column; }
.meta-specs i { font-size: 12px; font-style: normal; color: var(--cpq-text-muted, #6E7582); }
.meta-specs b { font-size: 16px; font-weight: 600; color: var(--cpq-text-primary, #1F2430); }
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

/* 核心特性：外层透明容器（避玻璃嵌套），每个 li 独立 glass-light 图标卡 */
.feature-list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.feature-list li {
  display: flex; gap: 14px; align-items: flex-start;
  padding: 16px 18px;
  background: var(--cpq-glass-2-bg);
  backdrop-filter: blur(var(--cpq-glass-blur-2));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-2));
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  box-shadow: var(--cpq-shadow-sm), inset 0 1px 0 var(--cpq-glass-highlight);
  transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), box-shadow var(--cpq-dur-1) var(--cpq-ease-smooth), transform var(--cpq-dur-2) var(--cpq-ease-smooth);
  font-size: 14px; color: var(--cpq-text-secondary, #4e5969); line-height: 1.5;
}
.feature-list li:hover {
  border-color: var(--cpq-glass-border-strong);
  box-shadow: var(--cpq-shadow-md), 0 0 14px var(--cpq-overlay-a15), inset 0 1px 0 var(--cpq-glass-highlight);
  transform: translateY(-2px);
}
.feat-icon {
  flex: 0 0 auto;
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--cpq-accent-gradient);
  color: #fff;
  font-size: 16px; font-weight: 700;
  box-shadow: 0 2px 8px var(--cpq-overlay-a30);
}
.feat-dot {
  flex: 0 0 auto;
  width: 10px; height: 10px;
  margin-top: 11px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677FF);
  box-shadow: 0 0 8px var(--cpq-overlay-a30, rgba(22,119,255,0.3));
}
.feat-text { flex: 1; min-width: 0; }

.spec-table { display: flex; flex-direction: column; border: 1px solid var(--cpq-overlay-w8); border-radius: var(--cpq-radius-md); overflow: hidden; }
.spec-row { display: flex; border-bottom: 1px solid var(--cpq-overlay-w8); transition: background var(--cpq-dur-1) var(--cpq-ease-smooth); }
.spec-row:last-child { border-bottom: none; }
.spec-row:hover { background: var(--cpq-overlay-a8); }
.spec-k { flex: 0 0 180px; padding: 12px 16px; font-size: 13px; color: var(--cpq-text-muted, #86909c); background: var(--cpq-overlay-w4); }
.spec-v { flex: 1; padding: 12px 16px; font-size: 14px; font-weight: 500; color: var(--cpq-text-primary, #1d2129); white-space: pre-wrap; }

.empty-content { text-align: center; color: var(--cpq-text-muted, #6E7582); font-size: 14px; }

@media (max-width: 760px) {
  .hero-scene { min-height: 520px; }
  .product-img, .product-ph, .scene-reflection { width: 78vw; }
  .scene-sun { width: 220px; height: 220px; }
  .scene-back { top: 14px; left: 14px; }
  .scene-chip { top: 16px; right: 14px; }
  .meta-specs { gap: 20px; }
  .spec-k { flex: 0 0 120px; }
}
</style>
