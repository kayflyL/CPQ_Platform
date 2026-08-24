<script setup lang="ts">
/** 机型产品详情页（配置面展示）— 看介绍/规格 → 点「配置这台」进配置向导。纯展示，无管理入口。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, type ServerModel, type ModelScenario } from '@/api/serverConfig'
import { capIconSvg } from '@/constants/capIcons'
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

// 内容归一化：新结构优先，旧数据降级（features→亮点行、scenarios string→场景对象）
const highlightList = computed(() => {
  const c = pc.value
  if (c?.highlights?.length) return c.highlights
  return (c?.features || []).map(f => ({ title: '', text: f.text }))
})
const capList = computed(() => pc.value?.capabilities || [])
const scnList = computed<ModelScenario[]>(() =>
  (pc.value?.scenarios || []).map(s => (typeof s === 'string' ? { name: s } : s))
)
const hasContent = computed(() => {
  const c = pc.value
  return !!(c && (c.tagline || c.overview || c.highlights?.length || c.features?.length
    || c.capabilities?.length || c.specs?.length || c.scenarios?.length))
})

// 配置变体卡片：点卡片展开看该配置的说明+规格差异（机型级 product_content 在上方固定，不随配置变）
const configs = computed(() => model.value?.configs || [])
const expandedCfgId = ref<number | null>(null)
function toggleCfg(id: number) {
  expandedCfgId.value = expandedCfgId.value === id ? null : id
}
const seriesRaw = computed(() => model.value?.base_config?.series || '')
const seriesLabel = computed(() => {
  const found = seriesStore.items.find(i => i.value === seriesRaw.value)
  return found?.label || seriesRaw.value || 'Polaris'
})

// 场景主题：天空渐变 + 大地遮罩 + 旭日三色 + 内容区页面/暗带底色，集中管理（四主题整页联动）
type StageThemeKey = 'wine' | 'ocean' | 'carbon' | 'violet'
interface StageTheme {
  key: StageThemeKey; label: string
  bg: string        // 天空→大地 整体垂直渐变
  earth: string     // 地平线下方遮罩（盖住太阳下半、加深大地）
  sun: string       // 地平线 / 太阳主色
  sunBright: string // 太阳最亮中心
  glow: string      // 天空光晕扩散
  page: string      // 内容区整页底色（hero 之下）
  band: string      // 「产品能力」暗色带底色
}
const STAGE_THEMES: StageTheme[] = [
  { key: 'wine', label: '酒红',
    bg: 'linear-gradient(to bottom, #1a0509 0%, #4a0e1f 28%, #7a1a2e 58%, #5a1228 70%, #2d0712 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(20,4,10,0.85) 35%, #0a0205 100%)',
    sun: '#FF7A4D', sunBright: '#FFE0C0', glow: 'rgba(255,122,77,0.55)',
    page: 'linear-gradient(to bottom, #0d0308 0%, #1c0912 45%, #0f040a 100%)',
    band: 'linear-gradient(to bottom, #160710 0%, #2d0b1a 55%, #1a0509 100%)' },
  { key: 'ocean', label: '深蓝',
    bg: 'linear-gradient(to bottom, #030814 0%, #0a1830 28%, #143a6b 58%, #0e2a52 70%, #06101f 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(3,8,20,0.85) 35%, #020610 100%)',
    sun: '#5BB8FF', sunBright: '#D6EBFF', glow: 'rgba(91,184,255,0.55)',
    page: 'linear-gradient(to bottom, #02050f 0%, #071226 45%, #030814 100%)',
    band: 'linear-gradient(to bottom, #02050f 0%, #0a1c38 55%, #030814 100%)' },
  { key: 'carbon', label: '纯黑',
    bg: 'linear-gradient(to bottom, #050505 0%, #1a1a1a 28%, #2e2e2e 58%, #222222 70%, #0a0a0a 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(5,5,5,0.85) 35%, #000000 100%)',
    sun: '#E8E8E8', sunBright: '#FFFFFF', glow: 'rgba(232,232,232,0.45)',
    page: 'linear-gradient(to bottom, #060606 0%, #161616 45%, #050505 100%)',
    band: 'linear-gradient(to bottom, #0a0a0a 0%, #232323 55%, #050505 100%)' },
  { key: 'violet', label: '暗紫',
    bg: 'linear-gradient(to bottom, #0a0218 0%, #1e0a3c 28%, #3d1a6b 58%, #2a1252 70%, #120420 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(10,2,24,0.85) 35%, #06010f 100%)',
    sun: '#B07AFF', sunBright: '#E8D0FF', glow: 'rgba(176,122,255,0.55)',
    page: 'linear-gradient(to bottom, #070113 0%, #180b30 45%, #0a0218 100%)',
    band: 'linear-gradient(to bottom, #080114 0%, #20103f 55%, #0a0218 100%)' },
]
const stageThemeKey = computed<StageThemeKey>(() => {
  const key = pc.value?.stage_theme
  return STAGE_THEMES.some(x => x.key === key) ? (key as StageThemeKey) : 'ocean'
})
const stageVars = computed(() => {
  const t = STAGE_THEMES.find(x => x.key === stageThemeKey.value) || STAGE_THEMES[0]
  return {
    '--sun-color': t.sun,
    '--sun-bright': t.sunBright,
    '--sun-glow': t.glow,
    '--earth-overlay': t.earth,
    '--page-bg': t.page,
    '--band-bg': t.band,
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
  // 有站内来路原路返回（如从服务器页门户货架直达）；直开详情页才回机型目录
  if (window.history.state?.back) { router.back(); return }
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
  <div class="detail-page" :style="stageVars">
    <a-spin :spinning="loading">
      <template v-if="model">
        <!-- 全宽场景 hero：天空 / 旭日地平线 / 大地，服务器立在大地上 -->
        <section class="hero-scene">
          <!-- 背景：天空→大地 渐变（4 主题堆叠，opacity 过渡） -->
          <div class="scene-bg" aria-hidden="true">
            <div
              v-for="t in STAGE_THEMES"
              :key="t.key"
              class="scene-bg-layer"
              :style="{ background: t.bg, opacity: stageThemeKey === t.key ? 1 : 0 }"
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

          <!-- 左上角返回（有来路原路返回，直开才回机型目录） -->
          <a-button type="text" @click="back" class="scene-back">
            <template #icon><span style="font-size:16px">←</span></template>
            返回
          </a-button>

          <!-- 右上角生命周期标签 -->
          <span class="lc-chip scene-chip" :class="lcMeta(model.lifecycle_status).chip">{{ lcMeta(model.lifecycle_status).label }}</span>

        </section>

        <!-- 限宽内容：铭牌信息卡 → 概述 → 为什么选它（暗带能力在中间全幅铺开）→ 场景/配置/规格 -->
        <div class="page-inner">
          <section class="hero-meta">
            <div class="meta-head">
              <h1 class="meta-name">{{ model.name }}</h1>
              <div v-if="pc?.tagline" class="meta-tagline">{{ pc.tagline }}</div>
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

          <section v-if="pc?.overview" class="sec">
            <div class="sec-head">
              <div><div class="sec-kicker">Overview</div><div class="sec-title">产品概述</div></div>
            </div>
            <p class="overview-text">{{ pc.overview }}</p>
          </section>

          <section v-if="highlightList.length" class="sec">
            <div class="sec-head">
              <div><div class="sec-kicker">Highlights</div><div class="sec-title">为什么选它</div></div>
            </div>
            <div class="hl-layout" :class="{ 'has-image': !!pc?.highlight_image }">
              <div v-if="pc?.highlight_image" class="hl-photo">
                <img :src="pc.highlight_image" alt="为什么选它" />
              </div>
              <div class="hl-grid">
                <div v-for="(h, i) in highlightList" :key="i" class="hl-card">
                  <b v-if="h.title">{{ h.title }}</b>
                  <span>{{ h.text }}</span>
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- 产品能力（暗色带，全幅，主题联动） -->
        <section v-if="capList.length" class="band-dark">
          <div class="page-inner">
            <div class="sec sec-flush-top">
              <div class="sec-head">
                <div><div class="sec-kicker">Capabilities</div><div class="sec-title">产品能力</div></div>
              </div>
              <div class="cap-grid">
                <div v-for="(c, i) in capList" :key="i" class="cap-block">
                  <div class="cap-ico" v-html="capIconSvg(c.icon)"></div>
                  <div class="cap-main">
                    <div class="cap-head">
                      <span class="cap-dim">{{ c.name }}</span>
                      <span v-if="c.name_en" class="cap-dim-en">{{ c.name_en }}</span>
                    </div>
                    <p v-if="c.desc" class="cap-desc">{{ c.desc }}</p>
                  </div>
                  <div v-if="c.metrics?.length" class="cap-metrics">
                    <span v-for="(m, j) in c.metrics" :key="j" class="metric">
                      <span class="v">{{ m.v }}</span>
                      <span class="l">{{ m.l }}</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div class="page-inner">
          <!-- 场景适配（照片卡） -->
          <section v-if="scnList.length" class="sec">
            <div class="sec-head">
              <div><div class="sec-kicker">Scenarios</div><div class="sec-title">场景适配</div></div>
            </div>
            <div class="scn-grid">
              <div v-for="(s, i) in scnList" :key="i" class="scn-card">
                <div v-if="s.image" class="scn-photo">
                  <img :src="s.image" alt="" loading="lazy" />
                </div>
                <div class="scn-body">
                  <div class="scn-name">{{ s.name }}</div>
                  <div v-if="s.fit" class="scn-fit">{{ s.fit }}</div>
                </div>
              </div>
            </div>
          </section>

          <!-- 可选配置（点卡片展开说明 + 规格差异） -->
          <section v-if="configs.length" class="sec">
            <div class="sec-head">
              <div><div class="sec-kicker">Configurations</div><div class="sec-title">可选配置</div></div>
              <div class="sec-sub">共 {{ configs.length }} 个 · 点卡片展开说明</div>
            </div>
            <div class="cfg-cards">
              <div
                v-for="c in configs" :key="c.id" class="cfg-card"
                :class="{ expanded: expandedCfgId === c.id }" @click="toggleCfg(c.id)"
              >
                <div class="cfg-name">
                  {{ c.name }}
                  <span v-if="c.id === model.base_config_id" class="cfg-primary">主配置 · 推荐</span>
                </div>
                <div class="cfg-spec">{{ c.form || '—' }} · {{ c.bays ?? '—' }}盘 · {{ c.series || '—' }}</div>
                <div v-if="expandedCfgId === c.id" class="cfg-body" @click.stop>
                  <p v-if="c.config_content?.description"><b>配置说明</b>{{ c.config_content.description }}</p>
                  <p v-if="c.config_content?.spec_diff"><b>规格差异</b>{{ c.config_content.spec_diff }}</p>
                  <div v-if="!c.config_content?.description && !c.config_content?.spec_diff" class="cfg-empty">
                    该配置暂未填写说明
                  </div>
                  <div class="cfg-cta" @click.stop="configure">用这款配置这台服务器 →</div>
                </div>
              </div>
            </div>
          </section>

          <!-- 完整技术规格（沉底折叠） -->
          <section v-if="pc?.specs?.length" class="sec sec-last">
            <details class="specs">
              <summary>
                完整技术规格 <span class="hint">参数都在这里，默认收起 · 需要的人自己展开</span><span class="chev">▼</span>
              </summary>
              <div class="spec-eyebrow">// {{ model.name }} · FULL TECHNICAL SPECIFICATIONS</div>
              <div v-for="(s, i) in pc.specs" :key="i" class="spec-row">
                <span class="spec-k">{{ s.key }}</span>
                <span class="spec-v">{{ s.value }}</span>
              </div>
            </details>
          </section>

          <div v-if="!hasContent" class="note-empty">该机型尚未补充产品介绍 —— 管理面「机型管理 → 编辑」可录入。</div>
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

/* —— 内容区：原型 R5.3 暗色数据/技术派（四主题联动，--sun-* 来自根 :style） —— */
.detail-page {
  --text: #eef3fa;
  --text-2: rgba(238, 243, 250, 0.72);
  --muted: rgba(238, 243, 250, 0.52);
  --line-soft: rgba(255, 255, 255, 0.1);
  --line-strong: rgba(255, 255, 255, 0.2);
  --font-mono: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --primary: var(--sun-color, #FF7A4D);
  --primary-bright: var(--sun-bright, #FFE0C0);
  --shadow: 0 14px 40px rgba(0, 0, 0, 0.45);
  color: var(--text);
  background: var(--page-bg, linear-gradient(to bottom, #0d0308 0%, #1c0912 45%, #0f040a 100%));
}
.page-inner { max-width: 1080px; margin: 0 auto; padding: 0 24px; }

/* 铭牌信息卡（Banner 下方，留出呼吸间距） */
.hero-meta {
  display: flex; justify-content: space-between; align-items: center; gap: 28px;
  padding: 24px 30px; margin: 28px auto 0;
  border-radius: 14px; border: 1px solid var(--line-strong);
  background: rgba(9, 10, 13, 0.8); backdrop-filter: blur(16px);
  box-shadow: var(--shadow), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  flex-wrap: wrap; position: relative; z-index: 9;
}
.hero-meta::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
  border-radius: 14px 14px 0 0;
  background: linear-gradient(to right, transparent 4%, var(--sun-color) 38%, var(--sun-bright) 50%, var(--sun-color) 62%, transparent 96%);
}
.meta-head { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.meta-name {
  margin: 0; font-family: var(--font-mono); font-size: 27px; font-weight: 700;
  line-height: 1.15; color: #f7fbff; letter-spacing: -0.01em;
}
.meta-tagline { font-size: 15px; color: var(--primary-bright); font-weight: 600; }
.meta-specs { display: flex; margin-top: 6px; }
.meta-specs span { display: flex; flex-direction: column; gap: 2px; padding: 0 22px; border-left: 1px solid var(--line-soft); }
.meta-specs span:first-child { padding-left: 0; border-left: none; }
.meta-specs i { font-size: 10.5px; font-style: normal; color: var(--muted); font-family: var(--font-mono); letter-spacing: 0.12em; }
.meta-specs b { font-family: var(--font-mono); font-size: 15px; font-weight: 600; color: #e8f3ff; }
.hero-actions { display: flex; gap: 10px; }

.lc-chip { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; border: 1px solid transparent; }
.lc-active { color: #1f9d6b; background: rgba(125, 215, 170, .18); border-color: rgba(125, 215, 170, .45); }
.lc-new    { color: #2f7de1; background: rgba(150, 195, 250, .18); border-color: rgba(150, 195, 250, .45); }
.lc-eol    { color: #c8861a; background: rgba(245, 200, 110, .18); border-color: rgba(245, 200, 110, .45); }
.lc-off    { color: var(--muted); background: rgba(255, 255, 255, .06); border-color: var(--line-soft); }

/* 章节头（Torra 式 kicker + 大标题） */
.sec { padding: 72px 0 8px; }
.sec-flush-top { padding-top: 0; }
.sec-last { padding-bottom: 8px; }
.sec-head { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.sec-kicker {
  font-family: var(--font-mono); font-size: 11px; font-weight: 600;
  letter-spacing: 0.22em; color: var(--primary); text-transform: uppercase; margin-bottom: 4px;
}
.sec-title { font-size: 24px; font-weight: 700; letter-spacing: 0.01em; line-height: 1.15; color: #f2f8ff; }
.sec-sub { font-size: 12.5px; color: var(--muted); margin-left: auto; padding-bottom: 3px; }

.overview-text { font-size: 15px; line-height: 1.9; color: var(--text-2); margin: 0; white-space: pre-wrap; }

/* 为什么选它：左图右文两栏（无图时退化为单栏 ruled list） */
.hl-layout.has-image { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 24px; align-items: start; }
.hl-photo {
  aspect-ratio: 1 / 1; width: 100%; border-radius: 14px; overflow: hidden;
  border: 1px solid var(--line-soft); background: #0a0d13;
}
.hl-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hl-grid { border-top: 1px solid var(--line-soft); }
.hl-card {
  display: grid; grid-template-columns: minmax(160px, 230px) 1fr; gap: 0 20px; align-items: baseline;
  padding: 16px 6px; border-bottom: 1px solid var(--line-soft); transition: background 0.15s var(--ease);
}
.hl-card:hover { background: rgba(255, 255, 255, 0.03); }
.hl-card b { font-size: 15px; font-weight: 700; color: #f2f8ff; }
.hl-card span { font-size: 13px; color: var(--text-2); line-height: 1.7; }

/* 产品能力：暗色带（全幅，主题联动） */
.band-dark {
  margin-top: 44px; padding: 52px 0 56px; color: #fff; position: relative;
  background-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.42), rgba(0, 0, 0, 0.58)), var(--band-bg, #160710);
}
.band-dark::before {
  content: ''; position: absolute; top: 0; left: -8%; right: -8%; height: 0;
  background: linear-gradient(to right, transparent 0%, var(--sun-color) 22%, var(--sun-bright) 50%, var(--sun-color) 78%, transparent 100%);
  background-size: 100% 1.5px; background-repeat: no-repeat;
  box-shadow: 0 0 18px var(--sun-color), 0 4px 46px var(--sun-glow, rgba(255, 122, 77, 0.55));
}
.band-dark .sec-kicker { color: var(--primary); }
.band-dark .sec-title { color: #fff; }
.band-dark .sec-sub { color: rgba(238, 243, 250, 0.5); }
.cap-grid {
  display: grid; grid-template-columns: repeat(2, 1fr);
  border: 1px solid var(--line-soft); border-radius: 12px; overflow: hidden; background: rgba(255, 255, 255, 0.02);
}
.cap-block {
  position: relative; padding: 26px 30px; margin: -1px 0 0 -1px;
  border-top: 1px solid var(--line-soft); border-left: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.035); transition: background 0.2s var(--ease);
  display: grid; grid-template-columns: 58px 1fr auto; column-gap: 22px; align-items: center;
}
.cap-block:hover { background: rgba(255, 255, 255, 0.06); }
.cap-ico { color: rgba(255, 255, 255, 0.42); }
.cap-ico :deep(svg) { width: 54px; height: auto; display: block; }
.cap-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 7px; }
.cap-dim { font-size: 17px; font-weight: 700; color: #f5faff; }
.cap-dim-en { font-family: var(--font-mono); font-size: 11px; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.14em; text-transform: uppercase; }
.cap-desc { margin: 0; font-size: 13.5px; color: rgba(238, 243, 250, 0.78); line-height: 1.7; }
/* 关键数字：小字注脚（值+标签同行右对齐，不再放大做视觉主角） */
.cap-metrics {
  display: flex; flex-direction: column; gap: 8px; align-items: flex-end;
  border-left: 1px solid var(--line-soft); padding-left: 20px;
}
.metric { display: flex; align-items: baseline; gap: 7px; }
.metric .v {
  font-size: 13px; font-weight: 600; color: rgba(240, 246, 255, 0.88);
  font-variant-numeric: tabular-nums; line-height: 1.5; white-space: nowrap;
}
.metric .l { font-size: 11.5px; color: rgba(255, 255, 255, 0.48); white-space: nowrap; }

/* 场景适配：照片卡 */
.scn-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.scn-card {
  border: 1px solid var(--line-soft); border-radius: 12px; overflow: hidden; background: rgba(255, 255, 255, 0.02);
  transition: border-color 0.2s var(--ease);
}
.scn-card:hover { border-color: var(--line-strong); }
.scn-photo { aspect-ratio: 16 / 10; overflow: hidden; background: #0a0d13; }
.scn-photo img {
  width: 100%; height: 100%; object-fit: cover; display: block;
  filter: saturate(0.82) brightness(0.86);
  transition: transform 0.4s var(--ease), filter 0.4s var(--ease);
}
.scn-card:hover .scn-photo img { transform: scale(1.045); filter: saturate(1) brightness(0.96); }
.scn-body { padding: 13px 16px 15px; border-top: 1px solid var(--line-soft); }
.scn-card > .scn-body:first-child { border-top: none; }   /* 无图卡：正文顶到卡边 */
.scn-name { font-size: 14px; font-weight: 700; color: #f2f8ff; margin-bottom: 5px; }
.scn-fit { font-size: 12.5px; color: var(--text-2); line-height: 1.65; }

/* 可选配置卡 */
.cfg-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.cfg-card {
  padding: 16px 20px; cursor: pointer; border: 1px solid var(--line-soft); border-radius: 12px;
  background: rgba(255, 255, 255, 0.02); transition: background 0.2s var(--ease), border-color 0.2s var(--ease);
}
.cfg-card:hover { background: rgba(255, 255, 255, 0.04); }
.cfg-card.expanded { border-color: var(--primary); }
.cfg-name { font-size: 14px; font-weight: 700; display: flex; gap: 8px; align-items: center; color: #f2f8ff; }
.cfg-primary { font-size: 10px; color: #1c0f07; background: var(--primary); padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
.cfg-spec { font-family: var(--font-mono); font-size: 12px; color: var(--muted); margin-top: 5px; }
.cfg-body { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line-soft); font-size: 12.5px; color: var(--text-2); line-height: 1.7; display: flex; flex-direction: column; gap: 10px; }
.cfg-body p { margin: 0; }
.cfg-body b { color: #e8f3ff; margin-right: 10px; }
.cfg-empty { color: var(--muted); font-style: italic; }
.cfg-cta { margin-top: 2px; font-size: 12.5px; color: #8cbdff; font-weight: 600; cursor: pointer; }
.cfg-cta:hover { text-decoration: underline; }

/* 完整技术规格（折叠） */
.specs { border-radius: 12px; border: 1px solid var(--line-soft); background: rgba(255, 255, 255, 0.02); overflow: hidden; }
.spec-eyebrow {
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--muted); padding: 13px 24px 12px;
}
.specs summary {
  list-style: none; cursor: pointer; padding: 16px 24px; font-size: 15px; font-weight: 700;
  color: #f2f8ff; display: flex; align-items: center; gap: 10px; user-select: none;
}
.specs summary::-webkit-details-marker { display: none; }
.specs summary .chev { transition: transform 0.2s; color: var(--muted); font-size: 13px; margin-left: auto; }
.specs[open] summary .chev { transform: rotate(180deg); }
.specs summary .hint { font-size: 12px; color: var(--muted); font-weight: 400; }
.spec-row { display: flex; border-top: 1px solid var(--line-soft); }
.spec-k { flex: 0 0 200px; padding: 11px 16px 11px 24px; font-size: 12.5px; color: var(--muted); }
.spec-v { flex: 1; padding: 11px 24px 11px 16px; font-size: 13.5px; font-weight: 500; color: var(--text); font-variant-numeric: tabular-nums; white-space: pre-wrap; }

.note-empty { padding: 56px 0; text-align: center; color: var(--muted); font-size: 14px; }

@media (max-width: 760px) {
  .hero-scene { min-height: 520px; }
  .product-img, .product-ph, .scene-reflection { width: 78vw; }
  .scene-sun { width: 220px; height: 220px; }
  .scene-back { top: 14px; left: 14px; }
  .scene-chip { top: 16px; right: 14px; }
  .meta-specs { gap: 18px; }
  .cap-grid { grid-template-columns: 1fr; }
  .cap-block { grid-template-columns: 52px 1fr; row-gap: 14px; }
  .cap-metrics {
    grid-column: 1 / -1; flex-direction: row; flex-wrap: wrap; gap: 18px; align-items: flex-start;
    border-left: none; padding-left: 0; border-top: 1px solid var(--line-soft); padding-top: 14px;
  }
  .metric { align-items: baseline; }
  .hl-layout.has-image { grid-template-columns: 1fr; }
  .hl-photo { max-width: 220px; }
  .hl-card { grid-template-columns: 1fr; row-gap: 2px; }
  .scn-grid { grid-template-columns: repeat(2, 1fr); }
  .sec-sub { margin-left: 0; width: 100%; }
  .spec-k { flex: 0 0 120px; }
}
@media (max-width: 480px) {
  .scn-grid { grid-template-columns: 1fr; }
}
</style>
