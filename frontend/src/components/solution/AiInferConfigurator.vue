<script setup lang="ts">
/** AI 推理配置器(选型配置页·第一模式;皮肤=站内 Glass Console token,09-28 定调去「AI味」回归工具风)。
 *  模型搜索 combobox + 量化/框架/并发分段 + 场景 chips → 显存剖面(需求总量数字 + 显存量筒)
 *  → 「哪些卡合适」卡砖网格(批量试算,点砖调张数/看适配机型)。
 *  显存剖面 = 纯需求侧:每芯 100G 通用刻度,权重先填、KV 后填,不绑定任何卡型;
 *  卡型推荐只出现在 B 区卡砖。全部数字来自 /api/gpu-sizing,前端零硬编码。 */
import { ref, computed, onMounted, watch, onErrorCaptured } from 'vue'
import { gpuSizingApi, type Catalog, type EvalRow, type EvalResult } from '@/api/gpuSizing'

const cat = ref<Catalog | null>(null)
const modelId = ref<number | null>(null)
const bits = ref(8)
const framework = ref('vLLM')
const conc = ref(4)
const sceneId = ref<number | null>(null)
const evalRes = ref<EvalResult | null>(null)
const err = ref('')
const loading = ref(false)
// 渲染异常自报:任何子树渲染错误以红条显示,替代"页面静默坏死"
const fatal = ref('')
onErrorCaptured(e => {
  fatal.value = '页面渲染异常：' + (e as Error).message + '（请截图反馈）'
  return false
})
const openId = ref<number | null>(null)
const overN = ref<Record<number, number>>({})
const brandTab = ref<'all' | 'nv' | 'domestic'>('all')

const VENDOR_LABEL: Record<string, string> = {
  NVIDIA: 'NVIDIA', AMD: 'AMD', Intel: 'Intel', 影驰: 'NVIDIA',
}
const isDomestic = (b?: string | null) => !!b && !VENDOR_LABEL[b]

const allModels = computed(() => (cat.value?.vendors || []).flatMap(v => v.models).filter(m => m.params_b > 0))
const vendor = ref('')
const vendors = computed(() => (cat.value?.vendors || []).filter(g => g.models.some(m => m.params_b > 0)))
const vendorModels = computed(() => vendors.value.find(g => g.vendor === vendor.value)?.models || [])
// 切品牌 → 自动选该品牌内(high 置信度优先、参数量大优先)的模型;换模型 → 量化跟随默认精度
watch(vendor, v => {
  const pool = (vendors.value.find(g => g.vendor === v)?.models || []).filter(m => m.params_b > 0)
  modelId.value = (pool.filter(m => m.confidence === 'high').sort((a, b) => b.params_b - a.params_b)[0] || pool[0])?.id ?? null
})
watch(modelId, id => {
  const m = allModels.value.find(x => x.id === id)
  if (m?.default_bits) bits.value = m.default_bits
})

async function load() {
  try {
    const c = await gpuSizingApi.catalog()
    cat.value = c
    if (!allModels.value.length) { err.value = '模型库为空：先在「模型与参数库」导入模型'; return }
    // 默认:模型数最多公司里,置信度 high 且参数量最大的模型
    const groups = [...c.vendors].sort((a, b) => b.models.length - a.models.length)
    const g = groups.find(x => x.models.some(m => m.params_b > 0))!
    vendor.value = g.vendor
    const pool = g.models.filter(m => m.params_b > 0)
    const best = pool.filter(m => m.confidence === 'high').sort((a, b) => b.params_b - a.params_b)[0] || pool[0]
    modelId.value = best.id
    bits.value = best.default_bits || 8
    const rag = c.scenes.find(s => s.name === 'RAG知识库')
    sceneId.value = (rag || c.scenes[0])?.id ?? null
    await evaluate()
  } catch (e: any) { err.value = errText(e) }
}

function errText(e: any): string {
  const st = e?.response?.status
  if (e?.code === 'ECONNABORTED') return '请求超时——后端可能未重启到最新版本（本页需要 /evaluate 接口）'
  if (st === 404) return '配置器接口未生效：请重启后端服务后刷新本页'
  if (st === 409) return e.response?.data?.detail || '该模型暂不可算'
  if (!e?.response) return '无法连接后端服务'
  return e.response?.data?.detail || `计算失败（HTTP ${st}）`
}

async function evaluate() {
  if (!modelId.value || !sceneId.value || loading.value) return
  loading.value = true; err.value = ''
  try {
    evalRes.value = await gpuSizingApi.evaluate({
      model_id: modelId.value!, bits: bits.value, scene_id: sceneId.value!,
      concurrency: conc.value, framework: framework.value,
    })
    overN.value = {}
  } catch (e: any) { err.value = errText(e) }
  finally { loading.value = false }
}
watch([modelId, bits, framework, sceneId, conc], () => evaluate())

// 行内张数步进:用 evaluate 返回的参数本地重算(零请求)
const P = computed(() => evalRes.value?.params)
function local(row: EvalRow, n: number) {
  const p = P.value!
  const pooled = evalRes.value?.tp === false ? 1 : n   // Excel 口径:非 TP 框架多卡不并显存
  const eff = row.usable_per_card * pooled
  const hd = Math.max(0, 1 - p.occ / eff)
  const mctx = Math.max(0, (eff - p.w0 - p.vision_gb) / (p.kvt * p.batch))
  const sp = row.bw_gb_s ? pooled * row.bw_gb_s * 1e9 / (p.occ * 1024 ** 3) : null
  return { eff, hd, over: p.occ > eff, mctx, sp }
}
function localEff(row: EvalRow) { return local(row, rowN(row)).eff }
function step(row: EvalRow, d: number) {
  overN.value[row.id] = Math.max(1, Math.min(64, (overN.value[row.id] ?? row.rec ?? 1) + d))
}
function rowN(row: EvalRow) { return overN.value[row.id] ?? row.rec ?? 1 }

const rowsView = computed(() => {
  const rows = evalRes.value?.rows || []
  const f = (r: EvalRow) => brandTab.value === 'all' ? true
    : brandTab.value === 'nv' ? !isDomestic(r.brand) : isDomestic(r.brand)
  const fit = rows.filter(r => r.fits && f(r))
  const out = rows.filter(r => !r.fits && f(r))
  return { fit, out }
})
function badgeOf(row: EvalRow) {
  const d = local(row, rowN(row))
  if (d.over) return { t: '装不下', c: 'bad' }
  return d.hd >= 0.3 ? { t: '余量达标', c: 'ok' } : { t: '余量偏小', c: 'soft' }
}
function applOf(row: EvalRow): string | null {
  const a = row.applicable as any
  return a && Array.isArray(a.series) && a.series.length ? a.series.join(' / ') : null
}
const fmtK = (v: number) => (v >= 10000 ? Math.round(v / 1000) + 'K' : Math.round(v).toLocaleString())

// —— 显存剖面(v6):需求侧冰芯量筒。每芯 = 100G 通用刻度,权重(含视觉)先填、KV 后填 ——
// setTimeout 驱动补间而非 rAF:预览窗格被遮挡时 rAF 停发,数字会卡在初值
const giga = ref(0)
let twTimer = 0
watch(() => evalRes.value?.need.total_gb ?? 0, to => {
  const from = giga.value, t0 = performance.now()
  clearTimeout(twTimer)
  const tick = () => {
    const p = Math.min(1, (performance.now() - t0) / 520), e = 1 - Math.pow(1 - p, 3)
    giga.value = from + (to - from) * e
    if (p < 1) twTimer = window.setTimeout(tick, 16)
  }
  tick()
}, { immediate: true })
const cores = computed(() => {
  const n = evalRes.value?.need
  if (!n) return []
  const cnt = Math.max(1, Math.ceil(n.total_gb / 100))
  let wLeft = n.weight_gb + (n.vision_gb || 0), kLeft = n.kv_at_ctx_gb
  const arr: { w: number; k: number }[] = []
  for (let i = 0; i < cnt; i++) {
    const w = Math.min(100, wLeft); wLeft -= w
    const k = Math.max(0, Math.min(100 - w, kLeft)); kLeft -= k
    arr.push({ w, k })
  }
  return arr
})
const coreN = computed(() => ((evalRes.value?.need.total_gb || 0) / 100).toFixed(2))
const kvtKb = computed(() => ((evalRes.value?.params.kvt || 0) * 1048576).toFixed(1))
const fwOh = computed(() => {
  const o = evalRes.value?.params.overhead
  return o == null ? '' : ' +' + Number(o).toFixed(1)
})
onMounted(load)
</script>

<template>
  <div class="aic">
    <header>
      <div class="trow">
        <h1>推理配置器</h1>
        <span class="hsub">选模型 → 显存需求 → 哪些卡合适</span>
      </div>
    </header>
    <div v-if="fatal" class="warn">{{ fatal }}</div>
    <div v-if="err" class="warn">{{ err }}</div>

    <div class="aic-cols">
    <aside class="col-l">
    <div class="step">
      <div class="sk"><b>品牌商</b><span>{{ vendors.length }} 家</span></div>
      <div class="seg">
        <button v-for="g in vendors" :key="g.vendor" :class="{ on: vendor === g.vendor }"
                @click="vendor = g.vendor">{{ g.vendor }}</button>
      </div>
    </div>
    <div class="step">
      <div class="sk"><b>具体模型</b><span>输入名称可搜索</span></div>
      <a-select v-model:value="modelId" class="sel"
                show-search option-filter-prop="label" size="large"
                style="width:100%" placeholder="先选品牌商,再选模型">
        <a-select-option v-for="m in vendorModels" :key="m.id" :value="m.id"
                         :label="`${m.name} ${m.params_b}B`">
          {{ m.name }}（{{ m.params_b }}B · {{ m.attn }}{{ m.confidence === 'high' ? ' · ✓' : '' }}）
        </a-select-option>
      </a-select>
    </div>
    <div class="step">
      <div class="sk"><b>量化精度</b></div>
      <div class="seg">
        <button v-for="b in (cat?.bits_options || [4, 8, 16])" :key="b"
                :class="{ on: bits === b }" @click="bits = b">{{ b }}bit</button>
      </div>
    </div>
    <div class="step">
      <div class="sk"><b>推理框架</b></div>
      <div class="seg">
        <button v-for="f in (cat?.frameworks || [])" :key="f.name"
                :class="{ on: framework === f.name }" @click="framework = f.name">{{ f.name }}</button>
      </div>
    </div>
    <div class="step">
      <div class="sk"><b>并发</b></div>
      <div class="seg">
        <button v-for="n in [1, 4, 8, 16, 32]" :key="n"
                :class="{ on: conc === n }" @click="conc = n">×{{ n }}</button>
      </div>
    </div>
    <div class="step">
      <div class="sk"><b>应用场景</b></div>
      <div class="schips">
        <button v-for="s in (cat?.scenes || [])" :key="s.id" class="schip"
                :class="{ on: sceneId === s.id }" @click="sceneId = s.id">
          {{ s.name }}<em>{{ Math.round((s.recommend_ctx || 0) / 1024) }}K</em>
        </button>
      </div>
    </div>

    </aside>
    <section class="col-m">
    <div class="mark"><b>显存剖面</b><em></em></div>
    <div class="hero" v-if="evalRes?.need">
      <div>
        <div class="hero-kick">需求总量</div>
        <div class="giga">{{ giga.toFixed(1) }}<em>GB</em></div>
        <div class="verdict">≈ <b>{{ coreN }}</b> 芯 × 100G<span class="sub"> · 需求侧刻度,卡型见下方「哪些卡合适」</span></div>
        <div class="brk">
          <div class="r"><i>权重</i><b>{{ evalRes!.need.weight_gb.toFixed(2) }} <em>GB</em></b></div>
          <div class="r" v-if="evalRes!.need.vision_gb > 0"><i>视觉</i><b>{{ evalRes!.need.vision_gb.toFixed(2) }} <em>GB</em></b></div>
          <div class="r"><i>KV 缓存 @ {{ Math.round(evalRes!.scene.recommend_ctx / 1024) }}K × {{ conc }}</i><b>{{ evalRes!.need.kv_at_ctx_gb.toFixed(2) }} <em>GB</em></b></div>
          <div class="r"><i>每 token KV</i><b>{{ kvtKb }} <em>KB</em></b></div>
          <div class="r"><i>框架预留</i><b>{{ evalRes!.framework }}{{ fwOh }} <em>GB/卡</em></b></div>
        </div>
      </div>
      <div class="corewrap">
        <div class="corebox">
          <div v-for="(c, i) in cores" :key="i" class="core" :style="{ animationDelay: i * 40 + 'ms' }">
            <i class="cw" :style="{ height: c.w.toFixed(2) + '%' }"></i>
            <i class="ck" :style="{ height: c.k.toFixed(2) + '%' }"></i>
          </div>
        </div>
        <div class="coreidx"><i v-for="i in cores.length" :key="i">{{ String(i).padStart(2, '0') }}</i></div>
        <div class="legend">
          <span><s class="lw"></s>权重</span>
          <span><s class="lk"></s>KV 缓存</span>
          <span>每芯 = 100 GB 刻度</span>
        </div>
      </div>
    </div>
    <div v-else-if="loading || !err" class="hero-load">需求计算中 —</div>
    </section>
    <section class="col-r">
    <div class="mark"><b>哪些卡合适</b><em></em></div>
    <div class="rk-tools">
      <span class="rk-sub">共 {{ rowsView.fit.length }} 款 · 点卡片调张数试算、看适配机型</span>
      <span v-if="evalRes?.tp === false" class="tpnote">该框架不支持多卡并显存 · 按单卡判定</span>
      <div class="fchips">
        <button class="fchip" :class="{ on: brandTab === 'all' }" @click="brandTab = 'all'">全部</button>
        <button class="fchip" :class="{ on: brandTab === 'nv' }" @click="brandTab = 'nv'">NVIDIA</button>
        <button class="fchip" :class="{ on: brandTab === 'domestic' }" @click="brandTab = 'domestic'">国产</button>
      </div>
    </div>
    <div class="rbody">
    <div class="tiles" v-if="evalRes?.need && evalRes?.params">
      <div v-for="(r, i) in rowsView.fit" :key="r.id" class="tile"
           :class="{ open: openId === r.id }"
           @click="openId = openId === r.id ? null : r.id">
        <div class="t-head">
          <span class="rk">{{ String(i + 1).padStart(2, '0') }}</span>
          <span v-if="evalRes && evalRes.rows[0] && r.id === evalRes.rows[0].id && !overN[r.id]" class="star">推荐</span>
          <div class="cname">
            <b>{{ r.name }}</b>
            <span>{{ r.cap_gb }}G · {{ r.bw_gb_s ? r.bw_gb_s + 'GB/s' : '带宽待核' }} · {{ r.tdp_w ? r.tdp_w + 'W' : 'TDP待核' }}</span>
          </div>
        </div>
        <div class="fbar">
          <i class="w" :style="{ width: Math.min(100, evalRes!.need.weight_gb / localEff(r) * 100) + '%' }"></i>
          <i class="k" :style="{ width: Math.min(100, evalRes!.need.kv_at_ctx_gb / localEff(r) * 100) + '%' }"></i>
        </div>
        <span class="ftxt">{{ Math.min(100, Math.round(evalRes!.params.occ / localEff(r) * 100)) }}% 显存占用</span>
        <div class="stats">
          <div class="st"><div class="num" :class="{ hi: i === 0 }">×{{ rowN(r) }}</div><small>推荐张数</small></div>
          <div class="st"><div class="num">{{ Math.round(local(r, rowN(r)).hd * 100) }}%</div><small>余量</small></div>
          <div class="st"><div class="num">{{ fmtK(local(r, rowN(r)).mctx) }}</div><small>最大上下文</small></div>
        </div>
        <div class="t-sub">
          <span>最低 {{ r.min == null ? 'N/A(不并卡)' : r.min + ' 张' }} · {{ local(r, rowN(r)).sp ? '~' + Math.round(local(r, rowN(r)).sp!) + ' tok/s' : '估速不可用' }}</span>
          <span>试算 ▾</span>
        </div>
        <div class="detail">
          <div class="d-row">
            <span class="d-tag" :class="badgeOf(r).c">{{ badgeOf(r).t }}</span>
            <span class="d-lab">张数试算</span>
            <div class="stepc">
              <button @click.stop="step(r, -1)">−</button><b>{{ rowN(r) }}</b><button @click.stop="step(r, 1)">＋</button>
            </div>
            <span class="d-meta">有效 {{ local(r, rowN(r)).eff.toFixed(1) }}G / 占用 {{ evalRes?.params.occ }}G</span>
          </div>
          <div class="appl">
            <span class="l">适配机型</span>
            <span v-if="applOf(r)" class="chip">{{ applOf(r) }} 系列</span>
            <i v-else class="none">未维护 · 去配件管理填写该卡适配机型</i>
          </div>
        </div>
      </div>
    </div>

    <details v-if="rowsView.out.length" class="more">
      <summary>▸ 显存过小、需 12 张以上不实用的卡（{{ rowsView.out.length }}）</summary>
      <div class="tiles" style="margin-top:10px">
        <div v-for="(r, i) in rowsView.out" :key="r.id" class="tile dim">
          <div class="t-head">
            <span class="rk">{{ String(i + 1).padStart(2, '0') }}</span>
            <div class="cname"><b>{{ r.name }}</b><span>{{ r.cap_gb }}G</span></div>
          </div>
          <div class="stats" style="margin-top:10px">
            <div class="st"><div class="num">{{ r.min }}</div><small>张才够</small></div>
          </div>
        </div>
      </div>
    </details>

    <p class="foot">估算口径：权重 + KV 缓存（含并发）+ 框架开销（{{ evalRes?.framework || 'vLLM' }}）；吞吐 = 卡间总带宽 ÷ 每 step 读取（TP 口径）；
      MoE 按总参数偏保守，MLA 按压缩潜变量修正；带宽缺失显示「估速不可用」；适配机型读配件「适配机型」字段，未维护的卡提示去配件管理填写。</p>
    </div>
    </section>
    </div>
  </div>
</template>

<style scoped>
/* 皮肤 = 站内 Glass Console(09-28 去「AI味」):容器=唯一玻璃层,内部元素全平面;颜色/明暗全走 --cpq-* token,
   暗色主题由 token 自身切换,组件零双皮肤覆盖块。--mono/--ease 等本地别名重指向 token,让历史规则自动跟随。 */
.aic {
  --t1: var(--cpq-text-primary); --t2: var(--cpq-text-secondary); --t3: var(--cpq-text-muted);
  --inkHi: var(--cpq-text-primary);
  --ice: var(--cpq-accent-primary); --iceDim: var(--cpq-accent-primary);
  --steel: var(--cpq-accent-primary-light);
  --line: var(--cpq-border-primary); --line2: var(--cpq-border-light);
  --ok: var(--cpq-color-success); --bad: var(--cpq-accent-danger); --soft: var(--cpq-color-warning);
  --tileBg: var(--cpq-overlay-w8); --tileBgHover: var(--cpq-overlay-w15);
  --fbarBg: var(--cpq-overlay-a8);
  --coreBg: var(--cpq-overlay-a4); --coreEdge: var(--cpq-border-primary);
  --footC: var(--cpq-text-muted);
  --mono: var(--cpq-font-family);
  --ease: var(--cpq-ease-smooth);
  position: relative; border-radius: var(--cpq-radius-lg); padding: 24px 28px;
  color: var(--t1); border: 1px solid var(--cpq-glass-border);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  display: flex; flex-direction: column;
  height: calc(100vh - var(--cpq-sticky-top, 0px) - 122px);
}
.aic > * { position: relative; }

/* 三栏固定框架(09-28 用户定调):整卡高度=视口减宿主让位,页面级滚动消失;
   左=六步选择 中=显存剖面(常驻),右=卡砖结果(筛选头钉顶+结果区独立内滚) */
.aic-cols { flex: 1; min-height: 0; display: grid;
  grid-template-columns: minmax(292px, 324px) minmax(340px, 400px) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  grid-template-areas: "sel prof cards"; }
.col-l { grid-area: sel; padding-right: 24px; border-right: 1px solid var(--line);
  overflow-y: auto; min-height: 0; }
.col-l .sk { flex-wrap: wrap; gap: 5px 10px; }
.col-m { grid-area: prof; padding: 0 24px; border-right: 1px solid var(--line);
  overflow-y: auto; min-height: 0; }
.col-r { grid-area: cards; padding-left: 24px; min-width: 0; min-height: 0;
  display: flex; flex-direction: column; }
.rbody { flex: 1; min-height: 0; overflow-y: auto; }

/* 头部:常规工具页尺度 */
.trow { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.trow h1 { margin: 0; font-size: 18px; font-weight: 600; color: var(--inkHi); }
.hsub { font-size: 12px; color: var(--t3); }

/* 章节标:小标题 + 细分隔线 */
.mark { display: flex; align-items: center; gap: 12px; margin: 22px 0 12px; }
.mark b { font-size: 13px; font-weight: 600; color: var(--inkHi); }
.mark em { flex: 1; height: 1px; background: var(--line); }

/* 步骤行:普通标签 + 幽灵按钮,激活=蓝边+浅蓝底 */
.step { margin-top: 16px; }
.sk { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
.sk b { font-size: 12.5px; font-weight: 600; color: var(--inkHi); }
.sk span { font-size: 11px; color: var(--t3); margin-left: auto; }
.seg { display: flex; flex-wrap: wrap; gap: 8px; }
.seg button { font-size: 12px; color: var(--t2); padding: 5px 12px; border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--line); background: transparent; cursor: pointer;
  transition: color .18s var(--ease), border-color .18s var(--ease), background .18s var(--ease); }
.seg button:hover { color: var(--t1); border-color: var(--line2); }
.seg button.on { color: var(--cpq-accent-primary); border-color: var(--cpq-glass-border-strong); background: var(--cpq-bg-selected); }
.schips { display: flex; flex-wrap: wrap; gap: 8px; }
.schip { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--t2);
  padding: 5px 11px; border-radius: var(--cpq-radius-sm); border: 1px solid var(--line); background: transparent; cursor: pointer;
  transition: color .18s var(--ease), border-color .18s var(--ease), background .18s var(--ease); }
.schip:hover { color: var(--t1); border-color: var(--line2); }
.schip.on { color: var(--cpq-accent-primary); border-color: var(--cpq-glass-border-strong); background: var(--cpq-bg-selected); }
.schip em { font-size: 10.5px; font-style: normal; color: var(--t3); }
.schip.on em { color: var(--ice); }

/* —— 主视觉 A:需求总量数字 + 明细行 + 显存量筒(每芯=100G,权重先填 KV 后填,不绑卡型) ——
   中栏常窄,默认竖排;两栏/宽幅时在下方媒体查询恢复并排 */
.hero { display: grid; grid-template-columns: 1fr; gap: 16px; }
.hero-kick { font-size: 11.5px; color: var(--t3); margin-bottom: 5px; }
.giga { font: 600 26px/1.1 var(--cpq-font-family); color: var(--inkHi);
  font-variant-numeric: tabular-nums; }
.giga em { font: 500 12px var(--cpq-font-family); font-style: normal; color: var(--t3); margin-left: 6px; }
.verdict { margin-top: 7px; font-size: 12.5px; line-height: 1.65; color: var(--t2); }
.verdict b { color: var(--ice); font-weight: 600; }
.verdict .sub { color: var(--t3); font-size: 11px; }
.brk { margin-top: 12px; max-width: 430px; }
.brk .r { display: flex; justify-content: space-between; align-items: baseline; padding: 5px 0;
  border-bottom: 1px solid var(--line); font-size: 11.5px; }
.brk .r:first-child { border-top: 1px solid var(--line); }
.brk .r i { font-style: normal; color: var(--t3); }
.brk .r b { color: var(--inkHi); font-weight: 600; font-variant-numeric: tabular-nums; }
.brk .r b em { font-style: normal; color: var(--t3); font-weight: 500; }
.hero-load { margin-top: 26px; font-size: 12px; color: var(--t3); }

.corewrap { display: flex; flex-direction: column; gap: 9px; min-width: 0; }
.corebox { position: relative; display: flex; align-items: flex-end; gap: 8px; height: 204px;
  width: 100%; border-bottom: 1px solid var(--line2); }
.core { position: relative; flex: 1; max-width: 36px; height: 100%; display: flex; flex-direction: column; justify-content: flex-end;
  background: var(--coreBg); border: 1px solid var(--coreEdge); border-bottom: none;
  animation: rise .55s var(--ease) backwards; }
@keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
.core i { display: block; width: 100%; pointer-events: none; }
.core .cw { background: var(--cpq-accent-primary); transition: height .7s var(--ease); }
.core .ck { background: var(--cpq-accent-primary-light); opacity: .9; transition: height .7s var(--ease); }
.coreidx { display: flex; gap: 8px; }
.coreidx i { flex: 1; max-width: 36px; text-align: center; font-size: 10px; color: var(--t3); font-style: normal; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; color: var(--t3); }
.legend s { text-decoration: none; display: inline-block; width: 8px; height: 8px; margin-right: 6px; vertical-align: -1px; border-radius: 2px; }
.legend .lw { background: var(--cpq-accent-primary); }
.legend .lk { background: var(--cpq-accent-primary-light); }

/* —— 主视觉 B:卡砖矩阵 —— */
.rk-tools { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.rk-sub { font-size: 11.5px; color: var(--t3); }
.tpnote { font-size: 11.5px; color: var(--soft);
  border: 1px solid var(--cpq-warn-border); background: var(--cpq-warn-surface); border-radius: var(--cpq-radius-sm); padding: 3px 10px; }
.fchips { display: flex; gap: 7px; margin-left: auto; }
.fchip { font-size: 11.5px; color: var(--t3); padding: 3px 11px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line); background: transparent; transition: color .18s var(--ease), border-color .18s var(--ease); }
.fchip:hover { color: var(--t1); }
.fchip.on { color: var(--ice); border-color: var(--cpq-glass-border-strong); }
.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.tile { position: relative; border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-sm); background: var(--tileBg);
  padding: 11px 13px; cursor: pointer; transition: border-color .2s var(--ease), background .2s var(--ease), box-shadow .2s var(--ease); }
.tile:hover { background: var(--tileBgHover); border-color: var(--cpq-glass-border-strong); box-shadow: var(--cpq-shadow-sm); }
.tile.open { border-color: var(--cpq-glass-border-strong); background: var(--tileBgHover); }
.tile.dim { opacity: .45; }
.t-head { display: flex; align-items: center; gap: 10px; }
.rk { font-size: 11px; color: var(--t3); min-width: 20px; font-variant-numeric: tabular-nums; }
.star { font-size: 10.5px; color: var(--ice); border: 1px solid var(--cpq-overlay-a30);
  background: var(--cpq-overlay-a10); padding: 1px 7px; border-radius: 4px; white-space: nowrap; }
.cname { flex: 1; min-width: 0; }
.cname b { display: block; font-size: 12.5px; font-weight: 600; color: var(--inkHi);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cname span { font-size: 10.5px; color: var(--t3); }
.fbar { height: 4px; display: flex; background: var(--fbarBg); margin-top: 9px; overflow: hidden; border-radius: 2px; }
.fbar .w { background: var(--cpq-accent-primary); transition: width .5s var(--ease); }
.fbar .k { background: var(--cpq-accent-primary-light); opacity: .9; transition: width .5s var(--ease); }
.ftxt { display: block; font-size: 10.5px; color: var(--t3); margin-top: 5px;
  font-variant-numeric: tabular-nums; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;
  border-top: 1px solid var(--line); margin-top: 9px; padding-top: 8px; }
.st .num { font-size: 14.5px; font-weight: 600; color: var(--t1); font-variant-numeric: tabular-nums; }
.st .num.hi { color: var(--ice); }
.st small { display: block; font-size: 10.5px; color: var(--t3); margin-top: 2px; }
.t-sub { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--t3); margin-top: 8px; }

/* 展开试算:判定徽记 + 步进器 + 适配机型 */
.detail { max-height: 0; overflow: hidden; transition: max-height .3s var(--ease); }
.tile.open .detail { max-height: 230px; }
.d-row { display: flex; align-items: center; gap: 12px; border-top: 1px solid var(--line); margin-top: 11px; padding-top: 11px; }
.d-tag { font-size: 11px; padding: 2px 10px; border-radius: 999px; border: 1px solid; }
.d-tag.ok { color: var(--ok); border-color: var(--cpq-overlay-success15); background: var(--cpq-overlay-success15); }
.d-tag.bad { color: var(--bad); border-color: var(--cpq-overlay-danger15); background: var(--cpq-overlay-danger10); }
.d-tag.soft { color: var(--soft); border-color: var(--cpq-overlay-warn30); background: var(--cpq-overlay-warn30); }
.d-lab { font-size: 11px; color: var(--t3); }
.stepc { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.stepc button { width: 25px; height: 25px; border-radius: 6px; font-size: 14px; color: var(--t2);
  border: 1px solid var(--line); background: transparent; cursor: pointer;
  transition: color .15s var(--ease), border-color .15s var(--ease); }
.stepc button:hover { color: var(--ice); border-color: var(--cpq-glass-border-strong); }
.stepc b { font-size: 14px; font-weight: 600; color: var(--inkHi); min-width: 26px; text-align: center; font-variant-numeric: tabular-nums; }
.d-meta { font-size: 11px; color: var(--t3); }
.appl { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; border-top: 1px solid var(--line);
  margin-top: 10px; padding-top: 10px; font-size: 12px; }
.appl .l { color: var(--t3); }
.chip { color: var(--ice); border: 1px solid var(--cpq-overlay-a30); background: var(--cpq-overlay-a10);
  padding: 2px 9px; border-radius: 5px; }
.none { color: var(--t3); font-style: normal; }
.warn { margin-top: 14px; padding: 10px 13px; border-radius: var(--cpq-radius-sm); font-size: 12px;
  background: var(--cpq-warn-surface); color: var(--soft); border: 1px solid var(--cpq-warn-border); }
details.more { border: 1px dashed var(--line); border-radius: var(--cpq-radius-sm); padding: 12px 15px; margin-top: 13px; }
details.more summary { font-size: 12px; color: var(--t3); cursor: pointer; list-style: none; }
details.more summary::-webkit-details-marker { display: none; }
.foot { margin-top: 20px; font-size: 11px; line-height: 1.8; color: var(--footC); }
/* 矮视口:量筒降高,剖面不顶爆中栏 */
@media (max-height: 840px) { .corebox { height: 156px; } }
/* 窄幅:≤1280 收窄两根固定栏给卡区腾位;≤1080 才退单栏文档流——中间不出两栏档(三栏固定框架在放大区间 110%~125% 必须保持) */
@media (max-width: 1280px) {
  .aic-cols { grid-template-columns: 292px 360px minmax(0, 1fr); }
}
@media (max-width: 1080px) {
  .aic { height: auto; padding: 20px 16px; }
  .aic-cols { grid-template-columns: 1fr; grid-template-rows: none;
    grid-template-areas: "sel" "prof" "cards"; }
  .col-l { border-right: none; padding-right: 0; overflow-y: visible; }
  .col-m { border-right: none; padding: 0; overflow-y: visible; }
  .col-r { padding-left: 0; }
  .rbody { overflow-y: visible; }
  .hero { grid-template-columns: 1fr; gap: 20px; }
  .corebox { width: 100%; }
}
</style>
