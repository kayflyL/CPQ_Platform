<script setup lang="ts">
/** 产品能力点选展示带（机型详情页 Capabilities）— n8n 式「左选右显」：
 *  左栏 = 维度 logo（capIcons 发丝线图标）+ 标题；右侧 = 介绍文案 + 取景框硬件特写插画。
 *  文字/数字全部来自 product_content.capabilities（管理面机型编辑器可改，本组件零新增数据约定）；
 *  插画 = icon key → 参数化 SVG 场景（展示层常量：重复结构做密度，SMIL 脉冲/闪烁/旋转做活性，
 *  prefers-reduced-motion 下全部静止）。自动轮播 4.5s，悬停暂停，点击直达。
 *  主题色沿用详情页根节点 stageVars 挂的 --sun-color / --sun-bright / --sun-glow 级联。
 *  原型：docs/原型/机型详情-产品能力点选介绍-原型v4.html */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { ModelCapability } from '@/api/serverConfig'
import { capIconSvg } from '@/constants/capIcons'

const props = defineProps<{ capabilities: ModelCapability[] }>()

const hasCaps = computed(() => props.capabilities.length > 0)
const reduced = typeof window !== 'undefined'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const cur = ref(0)
const active = computed(() => props.capabilities[cur.value] || props.capabilities[0])
const stageTag = computed(() => {
  const d = active.value
  if (!d) return ''
  const label = (d.name_en || d.name || '').toUpperCase()
  return `${label} · ${String(cur.value + 1).padStart(2, '0')}/${String(props.capabilities.length).padStart(2, '0')}`
})

/* ═══ 硬件特写插画（参数化场景，统一 viewBox 460×430 取景） ═══
   主结构 stroke rgba(255,255,255,.4)，次级 .18-.25，accent 用 --sun-color。
   场景按维度 icon key 选择（chip/slots/net/drive/term/fan），未知键回落 chip。 */
const W = 'rgba(255,255,255,'
const K = 'var(--sun-color, #5BB8FF)'
const pad = (x: number, y: number) => `<circle cx="${x}" cy="${y}" r="2.5" fill="${W}.3)"/>`
const pulse = (path: string, dur: string, begin?: string) =>
  `<circle class="sc-pulse" r="2.4"><animateMotion dur="${dur}"${begin ? ` begin="${begin}"` : ''} repeatCount="indefinite" path="${path}"/></circle>`
const blinkDot = (x: number, y: number, r: number, dur: string, begin?: string) =>
  `<circle cx="${x}" cy="${y}" r="${r}" fill="${K}" class="blink"><animate attributeName="opacity" values="1;.15;1" dur="${dur}"${begin ? ` begin="${begin}"` : ''} repeatCount="indefinite"/></circle>`

const SCENES: Record<string, () => string> = {
  /* 算力：CPU 封装顶视 — 基板+角孔+晶格阵列+辐射走线 */
  chip() {
    let cores = ''
    const acc = new Set(['1-1', '4-2', '5-4', '2-3'])
    for (let c = 0; c < 7; c++) for (let r = 0; r < 5; r++) {
      const x = 163 + c * 20, y = 143 + r * 27
      cores += acc.has(`${c}-${r}`)
        ? `<rect x="${x}" y="${y}" width="16" height="21" rx="2" fill="${K}" opacity=".88"/>`
        : `<rect x="${x}" y="${y}" width="16" height="21" rx="2" fill="none" stroke="${W}.22)" stroke-width="1"/>`
    }
    const traces: [string, number, number][] = [
      ['M120,150 H70 V70 H30', 30, 70], ['M340,150 H398', 398, 150], ['M230,100 V46', 230, 46],
      ['M120,270 H64', 64, 270], ['M340,270 H396 V330', 396, 330], ['M230,320 V374', 230, 374],
    ]
    return `
      <rect x="120" y="100" width="220" height="220" rx="8" fill="none" stroke="${W}.4)" stroke-width="1.5"/>
      ${[[136, 116], [324, 116], [136, 304], [324, 304]].map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="5" fill="none" stroke="${W}.3)" stroke-width="1.5"/>`).join('')}
      <rect x="155" y="135" width="150" height="150" fill="none" stroke="${W}.55)" stroke-width="1.5"/>
      ${cores}
      ${traces.map(t => `<path d="${t[0]}" fill="none" stroke="${W}.18)" stroke-width="1.5"/>${pad(t[1], t[2])}`).join('')}
      ${pulse('M120,150 H70 V70 H30', '3.6s')}
      ${pulse('M340,270 H396 V330', '4.4s', '-2s')}
    `
  },
  /* 扩展性：PCIe 插卡侧视 — 槽列+插卡+金手指+防呆缺口 */
  slots() {
    const slotY = [112, 174, 236, 298, 360], cards = [0, 2, 3]
    let s = ''
    slotY.forEach((y, i) => {
      s += `<rect x="90" y="${y}" width="24" height="16" rx="2" fill="none" stroke="${W}.4)" stroke-width="1.5"/>
            <rect x="128" y="${y}" width="242" height="16" rx="2" fill="none" stroke="${W}.4)" stroke-width="1.5"/>`
      if (!cards.includes(i)) s += `<path d="M100,${y + 8} H360" stroke="${W}.15)" stroke-width="1" stroke-dasharray="3 6" fill="none"/>`
    })
    cards.forEach((i, k) => {
      const y = slotY[i], accent = k === 1
      let contacts = ''
      for (let c = 0; c < 13; c++) contacts += `<path d="M${138 + c * 16},${y - 2} v8" stroke="${W}.3)" stroke-width="1.5"/>`
      s += `<rect x="104" y="${y - 48}" width="262" height="46" rx="4" fill="none" stroke="${accent ? K : W}.5)" stroke-width="1.5"${accent ? ' opacity=".85"' : ''}/>
            <rect x="122" y="${y - 36}" width="30" height="18" rx="2" fill="none" stroke="${accent ? K : W}.45)" stroke-width="1.5"${accent ? ' opacity=".9"' : ''}/>
            <rect x="160" y="${y - 32}" width="16" height="10" rx="1" fill="none" stroke="${W}.3)" stroke-width="1.2"/>
            <rect x="184" y="${y - 32}" width="16" height="10" rx="1" fill="none" stroke="${W}.3)" stroke-width="1.2"/>
            ${contacts}`
      if (accent) s += blinkDot(340, y - 25, 2.5, '2.2s')
    })
    return s
  },
  /* 网络能力：网口阵列 + 出线流 */
  net() {
    let ports = ''
    for (let k = 0; k < 4; k++) {
      const x = 64 + k * 76
      ports += `<rect x="${x}" y="96" width="52" height="36" rx="4" fill="none" stroke="${W}.4)" stroke-width="1.5"/>
        <rect x="${x + 14}" y="107" width="24" height="13" rx="1" fill="none" stroke="${W}.32)" stroke-width="1.2"/>
        <circle cx="${x + 43}" cy="103" r="2" fill="${W}.35)"/>
        ${blinkDot(x + 43, 110, 2, (2 + k * .5) + 's')}
        <path d="M${x},114 C${x - 24},114 ${x - 30},${100 + k * 16} 12,${92 + k * 18}" fill="none" stroke="${W}.16)" stroke-width="1.5"/>`
    }
    let ocps = ''
    for (let k = 0; k < 2; k++) {
      const x = 96 + k * 140
      ocps += `<rect x="${x}" y="212" width="112" height="30" rx="4" fill="none" stroke="${W}.45)" stroke-width="1.5"/>
        <path d="M${x + 12},227 H${x + 100}" stroke="${W}.25)" stroke-width="1.2"/>
        <rect x="${x + 88}" y="218" width="14" height="18" rx="2" fill="none" stroke="${K}" stroke-width="1.5" opacity=".8"/>`
    }
    return `${ports}${ocps}
      <path d="M320,227 H446" fill="none" stroke="${W}.2)" stroke-width="1.5"/>
      <path d="M208,260 C260,300 320,330 446,338" fill="none" stroke="${W}.14)" stroke-width="1.5" stroke-dasharray="6 6"/>
      ${pulse('M320,227 H446', '3.2s')}
      ${pulse('M208,260 C260,300 320,330 446,338', '4.6s', '-2.4s')}
    `
  },
  /* 存储：25 盘位阵列 — 盘格+指示灯+拉出手感 */
  drive() {
    let bays = ''
    const acc = new Set(['1-1', '3-2']), pulled = '4-0'
    for (let c = 0; c < 5; c++) for (let r = 0; r < 5; r++) {
      const key = `${c}-${r}`, x = 76 + c * 64, y = 108 + r * 46
      const tf = key === pulled ? ' transform="translate(16,-8)"' : ''
      const led = acc.has(key) ? blinkDot(x + 46, y + 19, 2, key === '1-1' ? '1.8s' : '2.6s')
        : `<circle cx="${x + 46}" cy="${y + 19}" r="2" fill="${W}.35)"/>`
      bays += `<g${tf}>
        <rect x="${x}" y="${y}" width="56" height="38" rx="3" fill="none" stroke="${W}.28)" stroke-width="1.5"/>
        <path d="M${x + 10},${y + 11} V${y + 27}" stroke="${W}.35)" stroke-width="1.5"/>
        <path d="M${x + 18},${y + 12} H${x + 38}" stroke="${W}.16)" stroke-width="1.2"/>
        ${led}</g>`
      if (key === pulled) bays += `<rect x="${x}" y="${y}" width="56" height="38" rx="3" fill="none" stroke="${W}.15)" stroke-width="1" stroke-dasharray="3 5"/>`
    }
    return `<rect x="64" y="96" width="332" height="248" rx="6" fill="none" stroke="${W}.22)" stroke-width="1"/>
      ${bays}
      <path d="M64,372 H396" stroke="${W}.16)" stroke-width="1" stroke-dasharray="2 6" fill="none"/>
      <circle class="sc-pulse" r="2.2"><animateMotion dur="5s" repeatCount="indefinite" path="M64,372 H396"/></circle>
    `
  },
  /* 管理：带外终端 — 窗口+状态行+光标+心跳线 */
  term() {
    const widths = [150, 110, 170, 80, 130, 60]
    let rows = ''
    widths.forEach((w, i) => {
      rows += `<rect x="112" y="${150 + i * 23}" width="${w}" height="8" rx="4" fill="${i === 1 ? K : W}.2)"${i === 1 ? ' opacity=".85"' : ''}/>`
    })
    return `
      <rect x="92" y="104" width="276" height="190" rx="8" fill="none" stroke="${W}.45)" stroke-width="1.5"/>
      <path d="M92,132 H368" stroke="${W}.25)" stroke-width="1"/>
      <circle cx="108" cy="118" r="3.5" fill="${W}.3)"/><circle cx="124" cy="118" r="3.5" fill="${W}.3)"/><circle cx="140" cy="118" r="3.5" fill="${W}.3)"/>
      ${rows}
      <rect x="112" y="290" width="9" height="14" fill="${K}" class="blink"><animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite"/></rect>
      <path d="M92,356 h56 l10,-18 l10,34 l9,-26 h44 l8,-12 h139" fill="none" stroke="${W}.3)" stroke-width="1.5"/>
      ${pulse('M92,356 h56 l10,-18 l10,34 l9,-26 h44 l8,-12 h139', '3.4s')}
      ${blinkDot(352, 118, 2.5, '2.8s')}
    `
  },
  /* 可靠与运维：双风扇墙 + 冗余电源 */
  fan() {
    const centers: [number, number, number][] = [[140, 150, 11], [252, 150, 14], [140, 268, 12.5], [252, 268, 10.5]]
    let fans = ''
    centers.forEach(([cx, cy, dur]) => {
      let blades = ''
      for (let k = 0; k < 4; k++) {
        blades += `<path d="M${cx},${cy - 7} C${cx + 3},${cy - 16} ${cx + 10},${cy - 19} ${cx + 16},${cy - 16}" transform="rotate(${k * 90} ${cx} ${cy})" fill="none" stroke="${W}.4)" stroke-width="1.5"/>`
      }
      fans += `<circle cx="${cx}" cy="${cy}" r="44" fill="none" stroke="${W}.4)" stroke-width="1.5"/>
        <g class="rotg"><animateTransform attributeName="transform" type="rotate" from="0 ${cx} ${cy}" to="360 ${cx} ${cy}" dur="${dur}s" repeatCount="indefinite"/>${blades}</g>
        <circle cx="${cx}" cy="${cy}" r="5" fill="${W}.4)"/>
        ${blinkDot(cx + 30, cy - 30, 2, '3s')}`
    })
    return `
      <rect x="92" y="102" width="212" height="212" rx="8" fill="none" stroke="${W}.22)" stroke-width="1"/>
      ${fans}
      <path d="M304,208 C324,208 322,190 340,190" fill="none" stroke="${W}.2)" stroke-width="1.5" stroke-dasharray="5 5"/>
      <rect x="340" y="140" width="78" height="130" rx="8" fill="none" stroke="${W}.45)" stroke-width="1.5"/>
      <circle cx="379" cy="184" r="24" fill="none" stroke="${W}.35)" stroke-width="1.5"/>
      <g class="rotg"><animateTransform attributeName="transform" type="rotate" from="0 379 184" to="360 379 184" dur="9s" repeatCount="indefinite"/>
        <path d="M379,177 C381,170 385,167 390,169 M379,191 C381,198 385,201 390,199 M372,180 C367,178 364,174 366,169 M372,190 C367,192 364,196 366,201" fill="none" stroke="${W}.35)" stroke-width="1.5"/></g>
      ${blinkDot(356, 156, 2.5, '2s')}
      <path d="M340,244 H418" stroke="${W}.25)" stroke-width="1.2"/>
      <path d="M104,356 q12,-16 24,0 t24,0 t24,0 t24,0 t24,0 t24,0 t24,0 t24,0" fill="none" stroke="${W}.18)" stroke-width="1.5"/>
      ${pulse('M104,356 q12,-16 24,0 t24,0 t24,0 t24,0 t24,0 t24,0 t24,0 t24,0', '5.2s')}
    `
  },
}
const sceneHtml = computed(() => (SCENES[active.value?.icon || ''] || SCENES.chip)())

/* ── 选中 / 自动轮播（悬停暂停；reduced-motion 不自动播） ── */
const CYCLE = 4500
let timer: number | null = null
function stopCycle() { if (timer !== null) { window.clearInterval(timer); timer = null } }
function startCycle() {
  stopCycle()
  if (reduced || props.capabilities.length < 2) return
  timer = window.setInterval(() => { cur.value = (cur.value + 1) % props.capabilities.length }, CYCLE)
}
function pick(i: number) { cur.value = i; startCycle() }
onMounted(startCycle)
onBeforeUnmount(() => {
  stopCycle()
  document.removeEventListener('visibilitychange', onVis)
})
function onVis() { document.hidden ? stopCycle() : startCycle() }
document.addEventListener('visibilitychange', onVis)
</script>

<template>
  <section v-if="hasCaps" class="band-dark">
    <div class="page-inner">
      <div class="sec sec-flush-top">
        <div class="sec-head">
          <div><div class="sec-kicker">Capabilities</div><div class="sec-title">产品能力</div></div>
          <div class="cap-hint">{{ reduced ? '点击切换' : '自动轮播 · 悬停暂停 · 点击切换' }}</div>
        </div>

        <div class="cap-wrap" @mouseenter="stopCycle" @mouseleave="startCycle">
          <!-- 左栏：logo + 标题 -->
          <div class="rail" role="tablist">
            <button
              v-for="(c, i) in capabilities" :key="i" role="tab"
              class="item" :class="{ active: i === cur }" @click="pick(i)"
            >
              <span class="ico" v-html="capIconSvg(c.icon)"></span>
              <span class="tt">
                <span class="nm">{{ c.name }}</span>
                <span v-if="c.name_en" class="en">{{ c.name_en }}</span>
              </span>
              <span class="prog"></span>
            </button>
          </div>

          <!-- 右侧：内容 + 取景框硬件插画 -->
          <div class="detail-panel">
            <div class="dp-grid">
              <div :key="cur" class="dp-copy">
                <div v-if="active.name_en" class="dp-kicker">{{ active.name_en }}</div>
                <h3 class="dp-title">{{ active.name }}</h3>
                <div class="dp-rule"></div>
                <p v-if="active.desc" class="dp-desc">{{ active.desc }}</p>
                <div v-if="active.metrics?.length" class="dp-stats">
                  <div v-for="(m, j) in active.metrics" :key="j" class="stat">
                    <div class="v">{{ m.v }}</div>
                    <div class="l">{{ m.l }}</div>
                  </div>
                </div>
              </div>
              <div class="dp-stage">
                <svg viewBox="0 0 460 430" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path class="st-tick" d="M10 30 V10 H30 M430 10 H450 V30 M450 400 V420 H430 M30 420 H10 V400" />
                  <!-- :key 换维度即重挂载，入场动画随挂载重放 -->
                  <g :key="cur" class="sc" v-html="sceneHtml"></g>
                  <text class="st-tag" x="446" y="412" text-anchor="end">{{ stageTag }}</text>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
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
.page-inner { max-width: 1180px; margin: 0 auto; padding: 0 28px; }
.sec-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 28px; }
.sec-kicker {
  font-family: var(--font-mono, monospace); font-size: 11px; letter-spacing: 0.22em;
  text-transform: uppercase; color: var(--primary); margin-bottom: 8px;
}
.sec-title { font-size: 23px; font-weight: 700; color: #fff; letter-spacing: 0.02em; }
.cap-hint { font-family: var(--font-mono, monospace); font-size: 10px; letter-spacing: 0.16em; color: rgba(255, 255, 255, 0.32); }

.cap-wrap { display: flex; gap: 26px; align-items: stretch; }

/* ── 左栏：logo + 标题 ── */
.rail { width: 238px; flex: none; display: flex; flex-direction: column; gap: 6px; }
.item {
  position: relative; display: flex; align-items: center; gap: 14px; text-align: left;
  border: none; background: transparent; cursor: pointer; color: inherit; font-family: inherit;
  padding: 13px 14px 13px 20px; border-radius: 10px; border: 1px solid transparent;
  transition: background 0.25s var(--ease), border-color 0.25s var(--ease);
}
.item::before {
  content: ''; position: absolute; left: 0; top: 11px; bottom: 11px; width: 3px; border-radius: 2px;
  background: transparent; transition: 0.25s;
}
.item:hover { background: rgba(255, 255, 255, 0.03); }
.item.active { background: rgba(255, 255, 255, 0.055); border-color: rgba(255, 255, 255, 0.07); }
.item.active::before { background: var(--sun-color); box-shadow: 0 0 8px var(--sun-glow, rgba(91, 184, 255, 0.55)); }
.item .ico { width: 42px; flex: none; color: rgba(255, 255, 255, 0.42); transition: 0.25s; }
.item .ico :deep(svg) { display: block; width: 100%; height: auto; }
.item.active .ico { color: rgba(255, 255, 255, 0.92); }
.item .tt { display: flex; flex-direction: column; gap: 3px; }
.item .nm { font-size: 15.5px; font-weight: 700; color: rgba(245, 250, 255, 0.55); transition: 0.25s; line-height: 1.2; }
.item.active .nm { color: #fff; }
.item .en {
  font-family: var(--font-mono, monospace); font-size: 9px; letter-spacing: 0.2em;
  text-transform: uppercase; color: rgba(255, 255, 255, 0.28); transition: 0.25s;
}
.item.active .en { color: var(--sun-color); opacity: 0.75; }
.item .prog {
  position: absolute; left: 12px; right: 14px; bottom: 0; height: 2px; border-radius: 1px; width: 0;
  background: var(--sun-color); box-shadow: 0 0 6px var(--sun-glow, rgba(91, 184, 255, 0.55)); opacity: 0;
}
.item.active .prog { opacity: 0.8; animation: cap-prog 4.5s linear forwards; }
@keyframes cap-prog { from { width: 0; } to { width: 100%; } }

/* ── 右侧：内容 + 取景框 ── */
.detail-panel {
  flex: 1; min-width: 0; position: relative; border: 1px solid var(--line-soft); border-radius: 14px; overflow: hidden;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.008));
}
.dp-grid { display: grid; grid-template-columns: minmax(320px, 1fr) minmax(0, 1.18fr); }
.dp-copy { align-self: center; padding: 44px 38px 44px 46px; animation: cap-in 0.5s var(--ease) both; }
.dp-kicker {
  font-family: var(--font-mono, monospace); font-size: 11px; letter-spacing: 0.26em;
  text-transform: uppercase; color: var(--sun-color); opacity: 0.85; margin-bottom: 12px;
}
.dp-title { font-size: 31px; font-weight: 700; color: #fff; letter-spacing: 0.03em; margin-bottom: 15px; }
.dp-rule { width: 44px; height: 2px; border-radius: 1px; background: var(--sun-color); opacity: 0.6; margin-bottom: 20px; }
.dp-desc { font-size: 14px; line-height: 1.9; color: rgba(238, 243, 250, 0.72); margin-bottom: 28px; }
.dp-stats { display: flex; flex-wrap: wrap; row-gap: 18px; }
.stat { padding: 2px 26px; border-left: 1px solid rgba(255, 255, 255, 0.1); }
.stat:first-child { padding-left: 0; border-left: none; }
.stat .v { font-family: var(--font-mono, monospace); font-size: 28px; font-weight: 600; color: #fff; }
.stat .l { font-size: 10.5px; color: rgba(255, 255, 255, 0.42); letter-spacing: 0.1em; margin-top: 6px; }
@keyframes cap-in {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: none; }
}

/* 取景框舞台：点阵 + 主题辉光 + 暗角，场景 SVG 置于其上 */
.dp-stage {
  position: relative; border-left: 1px solid var(--line-soft); min-height: 430px; overflow: hidden;
  background:
    radial-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px) 0 0 / 22px 22px,
    linear-gradient(180deg, rgba(255, 255, 255, 0.015), rgba(255, 255, 255, 0));
}
.dp-stage::before {
  content: ''; position: absolute; left: 50%; top: 56%; width: 130%; aspect-ratio: 1.15;
  transform: translate(-50%, -50%);
  background: radial-gradient(closest-side, var(--sun-glow, rgba(91, 184, 255, 0.55)), transparent 72%);
  opacity: 0.5; pointer-events: none;
}
.dp-stage::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(115% 100% at 50% 45%, transparent 58%, rgba(0, 0, 0, 0.38));
}
.dp-stage svg { position: relative; display: block; width: 100%; height: auto; z-index: 1; }
.st-tick { fill: none; stroke: var(--sun-color); stroke-width: 2; opacity: 0.55; }
.st-tag { font-family: var(--font-mono, monospace); font-size: 9.5px; fill: rgba(255, 255, 255, 0.38); letter-spacing: 0.18em; }
.sc { animation: cap-scene-in 0.5s var(--ease) both; }
.sc :deep(.sc-pulse) { fill: var(--sun-bright, #D6EBFF); }
@keyframes cap-scene-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  .item .prog, .sc :deep(.sc-pulse), .sc :deep(.blink), .sc :deep(.rotg) { display: none; }
  .dp-copy, .sc { animation: none; }
}

/* 手机：左栏横滑 + 上下堆叠（全站适配定式） */
@media (max-width: 760px) {
  .cap-wrap { flex-direction: column; gap: 14px; }
  .rail { width: 100%; flex-direction: row; overflow-x: auto; padding-bottom: 4px; scrollbar-width: none; }
  .rail::-webkit-scrollbar { display: none; }
  .item { min-width: 172px; flex: none; }
  .dp-grid { grid-template-columns: 1fr; }
  .dp-copy { padding: 32px 26px 24px; }
  .dp-stage { border-left: none; border-top: 1px solid var(--line-soft); min-height: 0; }
  .stat { padding: 2px 18px; }
  .band-dark { margin-top: 32px; padding: 36px 0 44px; }
}
</style>
