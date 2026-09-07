<script setup lang="ts">
/** 服务器配置门户主体 — 旭日舞台 banner + 类型胶囊快捷入口 + 全部机型货架。
 *  banner 场景配方复用机型详情页 hero（天空渐变/水印/旭日/地平线光带），固定深蓝「银河 · 擎天」主题；
 *  胶囊=导航（跳类型目录页，配方同详情页底部配色胶囊）；货架只展示上架机型（published_only）。 */
import { ref, computed, nextTick, onMounted, onActivated, watch } from 'vue'
import { useRouter } from 'vue-router'
import { catalogApi, type ServerType, type ServerModel, type PortalBanner } from '@/api/serverConfig'
import ServerModelCard from '@/components/common/ServerModelCard.vue'

const router = useRouter()
const types = ref<ServerType[]>([])
const models = ref<ServerModel[]>([])
const loading = ref(false)

// ---- 门户 banner 配置（system_config；标题空回落内置默认，图片空=银河场景做背景；每图可带独立副标题） ----
const DEFAULT_TITLE = '配置一台服务器'
const banner = ref<PortalBanner>({})
const bannerTitle = computed(() => banner.value.title?.trim() || DEFAULT_TITLE)
const slides = computed(() => (banner.value.images || []).filter(e => e?.url))

// 轮播：主图立地平线（详情页同款）+ 镜像倒影，切换如车驶入 —— 从 banner 最边缘滑入/出（±110vw 必在画面外）。
// 方向纯按钮驱动（传送带恒向）：点左箭头旧图永远向左驶离、新图从右边缘驶入；不随循环索引回弹换向。
const slideIdx = ref(0)
const slideOffsets = ref<number[]>([0])       // 每张图的轨道偏移（格=110vw；±1 格即画面外）
const pendingIdx = ref<number | null>(null)   // 正被无动画瞬移到入场侧的图
let shifting = false                          // 瞬移窗口内防重入（连点会让两次起点竞态）
watch(slides, (s) => {
  slideIdx.value = 0
  slideOffsets.value = s.map((_, i) => (i === 0 ? 0 : i))   // 其余先停到画面外
  pendingIdx.value = null
}, { immediate: true })
async function shiftSlide(belt: 1 | -1) {     // belt=带移动方向：+1=右箭头(旧图右驶离,新图自左驶入)，-1=左箭头镜像
  const n = slides.value.length
  if (n < 2 || shifting) return
  shifting = true
  try {
    const target = (slideIdx.value - belt + n) % n
    pendingIdx.value = target
    slideOffsets.value[target] = -belt               // 入场图瞬移到入场侧（驶离方向的对侧）
    await nextTick()
    // 双 rAF：等浏览器真的绘出瞬移位置。nextTick 只是微任务，若同帧改回主位，
    // 两次样式合并成一帧，过渡起点回落到上次绘制位置 → 旧图从错侧滑回、两图交织
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    pendingIdx.value = null
    slideIdx.value = target
    slideOffsets.value = slideOffsets.value.map((o, i) =>
      i === target ? 0 : o + belt,                   // 入场图滑入主位；其余（含旧主图）向 belt 侧挪一格驶离
    )
  } finally { shifting = false }
}
const prevSlide = () => shiftSlide(-1)
const nextSlide = () => shiftSlide(1)
// 当前图自带的副标题（空=不显示；随轮播切换淡入淡出）
const slideSubtitle = computed(() => slides.value[slideIdx.value]?.subtitle?.trim() || '')

const typeName = (id?: number) => types.value.find(t => t.id === id)?.name || ''
const countOfType = (id: number) => models.value.filter(m => m.server_type_id === id).length

async function load() {
  loading.value = true
  try {
    const [typesRes, modelsRes, bannerRes] = await Promise.all([
      catalogApi.listTypes(),
      catalogApi.listModels(undefined, { publishedOnly: true }),
      catalogApi.getPortalBanner().catch(() => ({})),
    ])
    types.value = typesRes.types
    models.value = modelsRes.models
    banner.value = bannerRes || {}
  } catch (e: any) {
    console.error('加载服务器目录失败', e)
  } finally { loading.value = false }
}

function goToModels(type: ServerType) {
  router.push(`/servers/types/${type.id}`)
}
function goToDetail(m: ServerModel) {
  router.push(`/servers/models/${m.id}`)
}

onMounted(load)

// KeepAlive：切回时刷新机型数据（首次挂载由 onMounted 加载）
let _catalogActivated = false
onActivated(() => {
  if (!_catalogActivated) {
    _catalogActivated = true
    return
  }
  load()
})
</script>

<template>
  <div class="sc-portal">
    <!-- 旭日舞台 banner（全幅；z 序：背景0 → 水印1 → 银河/星野2 → 擎天光柱3 → 太阳4 → 大地6 → 地平线光带7 → 轮播图7 → UI8 → 箭头9） -->
    <section class="scene">
      <div class="scene-bg" aria-hidden="true"></div>
      <div class="scene-watermark" aria-hidden="true">SERVERS</div>

      <!-- 银河（斜跨天空的星带 + 带内星点 + 全天星野） -->
      <div class="galaxy" aria-hidden="true"></div>
      <div class="galaxy-stars" aria-hidden="true"></div>
      <div class="stars" aria-hidden="true"></div>

      <!-- 擎天 · 自地平线升起的光柱 -->
      <div class="pillars" aria-hidden="true">
        <span class="pillar p1"></span>
        <span class="pillar p2"></span>
        <span class="pillar p3"></span>
      </div>

      <div class="scene-sky-glow" aria-hidden="true"></div>
      <div class="scene-sun" aria-hidden="true"></div>

      <div class="scene-earth" aria-hidden="true"></div>
      <div class="scene-ground-glow" aria-hidden="true"></div>

      <!-- 轮播倒影层（镜像立于地平线下，随主图同步滑动；z 在大地之上、地平线光带之下） -->
      <div v-if="slides.length" class="scene-slide-refs" aria-hidden="true">
        <div
          v-for="(s, i) in slides"
          :key="s.url"
          class="slide-item"
          :class="{ 'no-anim': pendingIdx === i }"
          :style="{ transform: `translateX(calc(-50% + ${(slideOffsets[i] ?? i) * 110}vw))` }"
        ><img :src="s.url" class="slide-ref-img" draggable="false" alt="" /></div>
      </div>

      <div class="scene-horizon" aria-hidden="true"></div>

      <!-- 轮播主图层（详情页产品图同款：立地平线 + 投影；从 banner 最边缘滑入/出） -->
      <div v-if="slides.length" class="scene-slides" aria-hidden="true">
        <div
          v-for="(s, i) in slides"
          :key="s.url"
          class="slide-item"
          :class="{ 'no-anim': pendingIdx === i }"
          :style="{ transform: `translateX(calc(-50% + ${(slideOffsets[i] ?? i) * 110}vw))`, zIndex: (slideOffsets[i] ?? i) === 0 ? 2 : 1 }"
        ><img :src="s.url" class="slide-img" draggable="false" alt="" /></div>
      </div>
      <template v-if="slides.length > 1">
        <button type="button" class="slide-arrow sa-left" aria-label="上一张" @click="prevSlide">‹</button>
        <button type="button" class="slide-arrow sa-right" aria-label="下一张" @click="nextSlide">›</button>
      </template>

      <div class="scene-copy">
        <!-- 每张轮播图自己的大标题（没配副标题的图回落 banner 主标题文案）；随切图淡入淡出 -->
        <Transition name="sub-swap" mode="out-in">
          <h1 :key="slideIdx" class="scene-title">{{ slideSubtitle || bannerTitle }}</h1>
        </Transition>
      </div>

      <!-- 类型胶囊快捷入口（点击跳类型目录页；数字=该类型上架机型数） -->
      <nav v-if="types.length" class="scene-capsule" aria-label="按类型选机型">
        <button
          v-for="t in types"
          :key="t.id"
          type="button"
          class="cap-btn"
          @click="goToModels(t)"
        >{{ t.name }}<i v-if="countOfType(t.id)"> · {{ countOfType(t.id) }}</i></button>
      </nav>
    </section>

    <div class="page-inner">
      <!-- 全部机型货架：一眼看全产品线，点卡直达详情（熟客少穿一层） -->
      <template v-if="models.length">
        <div class="sc-sec-head">
          <h2 class="sc-sec-title">全部机型</h2>
          <span class="sc-sec-count">{{ models.length }} 款机型</span>
        </div>
        <div class="sc-models">
          <ServerModelCard
            v-for="m in models"
            :key="m.id"
            :model="m"
            :type-name="typeName(m.server_type_id)"
            :show-base-config="false"
            :show-tagline="true"
            @click="goToDetail(m)"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sc-portal { padding: 0 0 80px; }

/* —— 旭日舞台 banner（深蓝「银河 · 擎天」主题；配方承详情页 hero-scene，无产品/倒影） —— */
.scene {
  --sun-color: #5BB8FF;
  --sun-bright: #D6EBFF;
  --sun-glow: rgba(91, 184, 255, 0.5);
  --earth-overlay: linear-gradient(to bottom, transparent 0%, rgba(2, 6, 16, 0.88) 35%, #010409 100%);
  position: relative;
  width: 100%;
  min-height: 460px;
  overflow: hidden;
  background: #020610;
  color: #fff;
}

.scene-bg {
  position: absolute; inset: 0; z-index: 0;
  background: linear-gradient(to bottom,
    #020610 0%, #050f1f 24%, #0a1e3d 48%, #123763 68%, #0a2244 80%, #04101f 100%);
}

.scene-watermark {
  position: absolute; inset: 0; z-index: 1;
  display: flex; align-items: center; justify-content: center;
  font-size: clamp(96px, 15vw, 200px);
  font-weight: 900;
  letter-spacing: -0.03em;
  color: #fff;
  opacity: 0.06;
  white-space: nowrap;
  text-transform: uppercase;
  pointer-events: none; user-select: none;
}

.scene-sky-glow {
  position: absolute; left: 0; right: 0;
  bottom: 30%;            /* 地平线位置 */
  height: 55%;
  background: radial-gradient(ellipse 60% 100% at 50% 100%, var(--sun-glow) 0%, transparent 62%);
  z-index: 2;
  pointer-events: none;
}

.scene-sun {
  position: absolute; left: 50%;
  bottom: 30%;            /* 中心落于地平线 */
  width: 520px; height: 200px;
  transform: translate(-50%, 50%);
  border-radius: 50%;
  background: radial-gradient(ellipse at center, var(--sun-bright) 0%, var(--sun-color) 36%, transparent 70%);
  opacity: 0.85;
  filter: blur(12px);
  z-index: 4;
  pointer-events: none;
}

.scene-earth {
  position: absolute; left: 0; right: 0; bottom: 0;
  height: 30%;
  background: var(--earth-overlay);
  z-index: 6;
  pointer-events: none;
}

.scene-ground-glow {
  position: absolute; left: 0; right: 0; bottom: 0;
  height: 30%;
  background: radial-gradient(ellipse 55% 95% at 50% 0%, var(--sun-glow) 0%, transparent 62%);
  opacity: 0.6;
  z-index: 6;
  pointer-events: none;
}

.scene-horizon {
  position: absolute; left: -8%; right: -8%;
  bottom: 30%;            /* 地平线 */
  height: 0;
  z-index: 7;
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

/* 轮播主图层 + 倒影层（详情页产品图同款：min(540px,64vw) contain 立于地平线 + 镜像倒影）。
 * 切换时图从 banner 最边缘滑入/出（偏移 ±110vw，必在画面外）；倒影层 z 在大地之上、地平线光带之下 */
.scene-slides {
  position: absolute;
  left: 0; right: 0;
  bottom: 30%;            /* 层底 = 地平线 */
  height: 0;
  z-index: 7;
  pointer-events: none;
}
.scene-slide-refs {
  position: absolute;
  left: 0; right: 0;
  top: 70%;               /* 倒影顶 = 地平线 */
  height: 0;
  z-index: 6;
  pointer-events: none;
}
.slide-item {
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  transition: transform 1.15s cubic-bezier(0.55, 0, 0.18, 1);   /* 车驶入：缓起加速 → 平稳刹停 */
  will-change: transform;
}
.slide-item.no-anim { transition: none; }
.scene-slide-refs .slide-item {
  bottom: auto;
  top: -16px;             /* 上移贴住主图底部（同详情页倒影 margin-top:-16px） */
  opacity: 0.6;
  -webkit-mask: linear-gradient(to bottom, rgba(0, 0, 0, 0.95) 0%, transparent 58%);
  mask: linear-gradient(to bottom, rgba(0, 0, 0, 0.95) 0%, transparent 58%);
}
.slide-img {
  display: block;
  width: min(540px, 64vw);
  max-height: 175px;
  object-fit: contain;
  object-position: bottom center;   /* 底边贴地平线，contain 不落空 */
  filter: drop-shadow(0 4px 18px rgba(0, 0, 0, 0.5));
}
.slide-ref-img {
  display: block;
  width: min(540px, 64vw);
  max-height: 175px;
  object-fit: contain;
  object-position: bottom center;   /* 翻转前贴盒底，翻转后贴地平线，与主图严丝合缝 */
  transform: scaleY(-1);            /* 镜面倒影 */
  filter: blur(2px);
}

/* 轮播左右箭头（微透明玻璃圆钮，banner 两侧垂直居中） */
.slide-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 9;
  width: 38px; height: 38px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  line-height: 1;
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 50%;
  cursor: pointer;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: background 0.25s ease, border-color 0.25s ease;
  padding: 0;
}
.slide-arrow:hover {
  background: rgba(255, 255, 255, 0.24);
  border-color: rgba(255, 255, 255, 0.5);
  color: #fff;
}
.sa-left { left: 18px; }
.sa-right { right: 18px; }

/* 银河 · 斜跨天空的星带（蓝白为主，核心一点暖光；重模糊成雾） */
.galaxy {
  position: absolute;
  top: 2%; left: -25%;
  width: 150%; height: 46%;
  transform: rotate(-26deg);
  z-index: 2;
  filter: blur(18px);
  pointer-events: none;
  background:
    radial-gradient(ellipse 80% 14% at 50% 50%, rgba(170, 200, 255, 0.07), transparent 75%),
    radial-gradient(ellipse 62% 30% at 44% 55%, rgba(150, 185, 255, 0.13), transparent 70%),
    radial-gradient(ellipse 40% 20% at 58% 48%, rgba(120, 150, 240, 0.10), transparent 70%),
    radial-gradient(ellipse 24% 12% at 52% 52%, rgba(255, 235, 210, 0.07), transparent 70%),
    radial-gradient(ellipse 30% 10% at 68% 56%, rgba(150, 130, 255, 0.05), transparent 70%);
}

/* 银河 · 带内星点（密集、顺带分布，微微闪烁） */
.galaxy-stars {
  position: absolute;
  top: 2%; left: -25%;
  width: 150%; height: 46%;
  transform: rotate(-26deg);
  z-index: 2;
  pointer-events: none;
  animation: twinkle 6s ease-in-out infinite alternate;
  background:
    radial-gradient(1.4px 1.4px at 31% 58%, rgba(255,255,255,.95), transparent),
    radial-gradient(1px 1px at 35% 42%, rgba(214,235,255,.8), transparent),
    radial-gradient(1.2px 1.2px at 38% 66%, rgba(255,255,255,.85), transparent),
    radial-gradient(1px 1px at 41% 35%, rgba(255,255,255,.7), transparent),
    radial-gradient(1.5px 1.5px at 44% 52%, rgba(255,255,255,.95), transparent),
    radial-gradient(1px 1px at 46% 70%, rgba(214,235,255,.75), transparent),
    radial-gradient(1.2px 1.2px at 48% 44%, rgba(255,255,255,.8), transparent),
    radial-gradient(1px 1px at 50% 30%, rgba(255,255,255,.65), transparent),
    radial-gradient(1.4px 1.4px at 52% 58%, rgba(255,255,255,.9), transparent),
    radial-gradient(1px 1px at 54% 38%, rgba(214,235,255,.8), transparent),
    radial-gradient(1.2px 1.2px at 56% 64%, rgba(255,255,255,.85), transparent),
    radial-gradient(1px 1px at 58% 48%, rgba(255,255,255,.75), transparent),
    radial-gradient(1.5px 1.5px at 60% 34%, rgba(255,255,255,.9), transparent),
    radial-gradient(1px 1px at 62% 55%, rgba(214,235,255,.8), transparent),
    radial-gradient(1.2px 1.2px at 65% 42%, rgba(255,255,255,.8), transparent),
    radial-gradient(1px 1px at 68% 60%, rgba(255,255,255,.7), transparent),
    radial-gradient(1.2px 1.2px at 57% 26%, rgba(214,235,255,.7), transparent),
    radial-gradient(1px 1px at 47% 78%, rgba(255,255,255,.65), transparent);
}

/* 全天星野（稀疏散布，慢闪） */
.stars {
  position: absolute; inset: 0;
  z-index: 2;
  pointer-events: none;
  animation: twinkle 9s ease-in-out infinite alternate-reverse;
  background:
    radial-gradient(1.2px 1.2px at 5% 18%, rgba(255,255,255,.8), transparent),
    radial-gradient(1px 1px at 12% 55%, rgba(214,235,255,.6), transparent),
    radial-gradient(1.4px 1.4px at 18% 32%, rgba(255,255,255,.85), transparent),
    radial-gradient(1px 1px at 24% 70%, rgba(255,255,255,.55), transparent),
    radial-gradient(1.2px 1.2px at 31% 12%, rgba(255,255,255,.75), transparent),
    radial-gradient(1px 1px at 80% 15%, rgba(214,235,255,.65), transparent),
    radial-gradient(1.4px 1.4px at 85% 48%, rgba(255,255,255,.85), transparent),
    radial-gradient(1px 1px at 76% 72%, rgba(255,255,255,.6), transparent),
    radial-gradient(1.2px 1.2px at 90% 30%, rgba(255,255,255,.75), transparent),
    radial-gradient(1px 1px at 95% 60%, rgba(214,235,255,.55), transparent),
    radial-gradient(1.2px 1.2px at 8% 82%, rgba(255,255,255,.6), transparent),
    radial-gradient(1px 1px at 68% 8%, rgba(255,255,255,.6), transparent);
}

/* 擎天 · 自地平线升起的光柱（中间主柱，两翼微倾如撑天） */
.pillars {
  position: absolute; left: 0; right: 0;
  bottom: 30%;            /* 柱脚 = 地平线 */
  height: 58%;
  z-index: 3;
  pointer-events: none;
}
.pillar {
  position: absolute;
  bottom: 0;
  width: 90px;
  height: 100%;
  background: linear-gradient(to top, rgba(91, 184, 255, 0.20), rgba(91, 184, 255, 0.05) 55%, transparent 85%);
  filter: blur(10px);
  transform-origin: bottom center;
}
.pillar.p1 { left: 26%; transform: rotate(4deg); opacity: 0.75; }
.pillar.p2 {
  left: 50%; width: 140px; transform: translateX(-50%);
  background: linear-gradient(to top, rgba(214, 235, 255, 0.28), rgba(91, 184, 255, 0.07) 55%, transparent 85%);
}
.pillar.p3 { left: 72%; transform: rotate(-5deg); opacity: 0.65; }

@keyframes twinkle {
  from { opacity: 0.6; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .galaxy-stars, .stars { animation: none; }
  .slide-item { transition: none; }
}

/* 标题（天空区居中） */
.scene-copy {
  position: absolute;
  left: 0; right: 0; top: 13%;
  z-index: 8;
  text-align: center;
  padding: 0 24px;
}
/* banner 大标题·玻璃字：竖向 白→半透白 渐变（透感）+ 深色投影托底；内容=每图副标题，没配回落主标题文案 */
.scene-title {
  font-size: clamp(26px, 3.2vw, 30px);
  font-weight: 600;
  letter-spacing: 0.05em;
  margin: 0;
  background: linear-gradient(180deg, #ffffff 30%, rgba(255, 255, 255, 0.55));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 2px 14px rgba(0, 0, 0, 0.4));
}
/* 标题随轮播切换：淡入淡出 + 轻微上下错位，与 ~1.15s 车驶入节奏错开成短促一档 */
.sub-swap-enter-active, .sub-swap-leave-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.sub-swap-enter-from, .sub-swap-leave-to { opacity: 0; transform: translateY(4px); }
@media (prefers-reduced-motion: reduce) {
  .sub-swap-enter-active, .sub-swap-leave-active { transition: none; }
}

/* 类型胶囊（配方同详情页 scene-switch） */
.scene-capsule {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 8;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  padding: 0 24px;
  max-width: 100%;
}
.cap-btn {
  padding: 7px 18px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.78);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: all 0.25s ease;
  white-space: nowrap;
}
.cap-btn i {
  font-style: normal;
  font-size: 12px;
  opacity: 0.6;
}
.cap-btn:hover {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 14px rgba(255, 255, 255, 0.22);
}

/* —— 内容区（跟随系统浅/深主题） —— */
.page-inner { max-width: 1180px; margin: 0 auto; padding: 36px 24px 0; }

.sc-sec-head {
  display: flex; align-items: baseline; gap: 10px;
  margin: 0 0 16px;
}
.sc-sec-title { font-size: 17px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.sc-sec-count { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }
.sc-models { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; }

@media (max-width: 640px) {
  .scene { min-height: 340px; }
  .scene-copy { top: 10%; }
  .slide-img, .slide-ref-img { max-height: 120px; }
}
</style>
