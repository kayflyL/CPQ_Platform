<script setup lang="ts">
/** 配置流程（standalone 服务器页）— 机箱概要卡 + KP 按类别拆卡。
 *  机箱（基准/前面板/后面板/电源）收进「机箱配置弹窗」（L6ChassisConfig stepper 模式）；
 *  KP 核心配件按 cat 独立成卡（CPU/Memory/HDD-SSD/GPU/NIC 预设 + 用户从 KP 类别新增）。
 *  kpLines 保持扁平 [{cat,pn,qty}]，卡片是渲染期 groupBy 视图 → 推导/持久化链路不动。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { kpPartsApi, configSchemeApi, baseConfigApi, type ServerModel, type KpPart } from '@/api/serverConfig'
import L6ChassisConfig from '@/components/quote/L6ChassisConfig.vue'
import ChassisCard from '@/components/server-config/ChassisCard.vue'
import KpCategoryCard from '@/components/server-config/KpCategoryCard.vue'
import CountNumber from '@/components/common/CountNumber.vue'
import { fromKpPart } from '@/composables/usePartAdapter'
import type { PickerItem } from '@/types/picker'
import type { GpuArch } from '@/composables/useServerConfig'

const props = defineProps<{ model: ServerModel }>()

// ---- KP 核心配件（扁平 kpLines；卡片是 groupBy 视图）----
const kpLines = ref<{ cat: string; pn: string; qty: number }[]>([])
const gpuArch = ref<GpuArch>('none')
const kpCatalog = ref<Record<string, KpPart[]>>({})
const kpCategories = ref<{ id: number; name: string }[]>([])

const l6Apply = ref<{ baseConfigId: number | null; totals: any; picks: any; l6Rows: any[] } | null>(null)

// 预设 5 类（常驻显示，不可删）；其余 KP 类别由用户「+ 新增配置卡片」加入
const CORE_CATS = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']

// 机箱卡片用的 series / 基准配置名（从 model.base_config_id 关联的 BaseConfig 读）
const series = ref('')
const baseConfigName = ref('')
const chassisModalOpen = ref(false)

async function init() {
  try {
    // 加载基准配置 → 拿 series（用户定调：芯片类型即显示 Orion/Polaris）+ name
    if (props.model.base_config_id) {
      try {
        const bc = await baseConfigApi.get(props.model.base_config_id)
        series.value = (bc as any).series || ''
        baseConfigName.value = (bc as any).name || ''
      } catch { /* 无基准配置时机箱卡片显示 — */ }
    }

    kpCategories.value = await kpPartsApi.categories()
    const kpPartsResults = await Promise.all(
      kpCategories.value.map(c => kpPartsApi.listByCategory(c.id))
    )
    kpCategories.value.forEach((c, i) => { kpCatalog.value[c.name] = kpPartsResults[i] })

    if (!kpLines.value.length) {
      const firstPn = (cat: string) => (kpCatalog.value[cat]?.[0] || {}).pn || ''
      const isAI = props.model.use === 'AI加速计算'
      kpLines.value = [
        { cat: 'CPU', pn: firstPn('CPU'), qty: 1 },
        { cat: 'Memory', pn: firstPn('Memory'), qty: 4 },
        { cat: 'HDD/SSD', pn: firstPn('HDD/SSD'), qty: 2 },
        { cat: 'GPU', pn: isAI ? firstPn('GPU') : '', qty: isAI ? 1 : 0 },
        { cat: 'NIC', pn: firstPn('NIC'), qty: 2 },
      ]
      gpuArch.value = isAI ? 'pt' : 'none'
    }
  } catch (e: any) {
    message.error('加载失败：' + (e.message || e))
  }
}

function partsOf(cat: string) { return kpCatalog.value[cat] || [] }
// KP 料号归一化为 PickerItem[]，喂给 KpCategoryCard（只在 kpCatalog 变化时重算）
const pickerCatalog = computed<Record<string, PickerItem[]>>(() => {
  const out: Record<string, PickerItem[]> = {}
  for (const [cat, list] of Object.entries(kpCatalog.value)) out[cat] = (list || []).map(fromKpPart)
  return out
})
function kpPart(pn: string) { return kpCategories.value.flatMap(c => kpCatalog.value[c.name] || []).find(p => p.pn === pn) }
function priceOf(pn: string) { return kpPart(pn)?.unit_price || 0 }

// ---- 卡片视图：kpLines 扁平 → 按 cat 分组；预设 5 类常驻 + 用户新增追加 ----
const kpCardCats = computed(() => {
  const extras = kpLines.value.map(l => l.cat).filter(c => !CORE_CATS.includes(c))
  const seen = new Set<string>()
  const out: string[] = []
  for (const c of [...CORE_CATS, ...extras]) {
    if (!seen.has(c)) { seen.add(c); out.push(c) }
  }
  return out
})
const kpLinesByCat = computed<Record<string, { cat: string; pn: string; qty: number }[]>>(() => {
  const m: Record<string, { cat: string; pn: string; qty: number }[]> = {}
  for (const l of kpLines.value) { (m[l.cat] = m[l.cat] || []).push(l) }
  return m
})

// 顶部导航：1 机箱 + 各 KP 卡片
const navSteps = computed(() => [
  { n: 1, label: '机箱', target: 'chassis-card' },
  ...kpCardCats.value.map((c, i) => ({ n: i + 2, label: c, target: `kp-card-${c}` })),
])

// 新增卡片下拉：KP 类别里还没显示的
const availableKpCats = computed(() => kpCategories.value.filter(c => !kpCardCats.value.includes(c.name)))
const pendingNewCat = ref('')
function onAddCard() {
  const cat = pendingNewCat.value
  pendingNewCat.value = ''
  if (!cat) return
  kpLines.value.push({ cat, pn: (partsOf(cat)[0] || {}).pn || '', qty: 1 })
}

// ---- KP 卡片事件 → 改扁平 kpLines（局部 index 反查全局 index）----
function globalIndexOfCat(cat: string, localIdx: number): number {
  let seen = 0
  for (let gi = 0; gi < kpLines.value.length; gi++) {
    if (kpLines.value[gi].cat === cat) {
      if (seen === localIdx) return gi
      seen++
    }
  }
  return -1
}
function setLineForCat(cat: string, localIdx: number, patch: Partial<{ pn: string; qty: number }>) {
  const gi = globalIndexOfCat(cat, localIdx)
  if (gi >= 0) kpLines.value[gi] = { ...kpLines.value[gi], ...patch }
}
function delLineForCat(cat: string, localIdx: number) {
  const gi = globalIndexOfCat(cat, localIdx)
  if (gi >= 0) kpLines.value.splice(gi, 1)
}
function addLineForCat(cat: string) {
  kpLines.value.push({ cat, pn: (partsOf(cat)[0] || {}).pn || '', qty: 1 })
}
function removeCard(cat: string) {
  kpLines.value = kpLines.value.filter(l => l.cat !== cat)
}

// ---- kpSummary：喂给 L6ChassisConfig 做 derive ----
const kpSummary = computed(() => {
  const cpu = kpLines.value.find(l => l.cat === 'CPU')
  const gpu = kpLines.value.find(l => l.cat === 'GPU')
  const drivesByKind: Record<string, number> = {}
  for (const l of kpLines.value) {
    if (l.cat !== 'HDD/SSD') continue
    const part = kpPart(l.pn) as any
    const name = (part?.name || '') + ' ' + ((part?.specs as any)?.kind || '')
    for (const k of ['SATA', 'SAS', 'NVMe']) {
      if (name.toUpperCase().includes(k)) { drivesByKind[k] = (drivesByKind[k] || 0) + (l.qty || 0); break }
    }
  }
  return {
    cpuPn: cpu?.pn, cpuQty: cpu?.qty,
    gpuPn: gpu?.pn, gpuQty: gpu?.qty,
    gpuArch: gpuArch.value,
    drivesByKind,
  }
})

const kpTotal = computed(() => kpLines.value.reduce((s, l) => s + priceOf(l.pn) * l.qty, 0))
const l6Total = computed(() => l6Apply.value?.totals?.l6 || 0)
const grand = computed(() => l6Total.value + kpTotal.value)

function onL6Apply(payload: any) { l6Apply.value = payload }

const saving = ref(false)
const bomVisible = ref(false)
async function saveConfig() {
  if (!l6Apply.value) { message.warning('请先完成机箱选配'); return }
  saving.value = true
  try {
    await configSchemeApi.create({
      name: `${props.model.name} 配置 ${new Date().toLocaleDateString('zh-CN')}`,
      model_id: props.model.id,
      payload: {
        base_config_id: l6Apply.value.baseConfigId,
        l6_picks: l6Apply.value.picks,
        l6_totals: l6Apply.value.totals,
        kp_lines: kpLines.value.map(l => ({ cat: l.cat, pn: l.pn, qty: l.qty })),
        gpu_arch: gpuArch.value,
        totals: { l6: l6Total.value, kp: kpTotal.value, grand: grand.value },
      },
    })
    bomVisible.value = true
    message.success('配置已保存，已生成 BOM')
  } catch (e: any) {
    message.error('保存失败：' + (e.message || e))
  } finally { saving.value = false }
}

function scrollToPanel(panelId: string) {
  const el = document.getElementById(panelId)
  const scroller = document.querySelector('.main-scroll')
  if (el && scroller) {
    const elTop = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top
    scroller.scrollTo({ top: scroller.scrollTop + elTop - 12, behavior: 'smooth' })
  }
}

onMounted(init)
</script>

<template>
  <div class="sc-wizard">
    <div class="sc-banner">
      <span class="bm-name">{{ model.name }}</span>
      <span class="bm-sub">{{ model.use }} · {{ model.form }} · {{ model.bays }} 盘位</span>
    </div>

    <!-- 步骤指示器：机箱 + 各 KP 卡片 -->
    <div class="sc-steps">
      <template v-for="(s, i) in navSteps" :key="s.target">
        <div class="sc-step" @click="scrollToPanel(s.target)"><span class="sn">{{ s.n }}</span><span class="st">{{ s.label }}</span></div>
        <div v-if="i < navSteps.length - 1" class="sc-step-line"></div>
      </template>
    </div>

    <div class="sc-layout">
      <!-- 左栏：机箱卡 + KP 各类别卡 -->
      <div class="sc-col-left">
        <!-- ① 机箱概要（点配置按钮弹窗做 4 步细配）-->
        <ChassisCard
          :model="model"
          :series="series"
          :base-config-name="baseConfigName"
          :l6-total="l6Total"
          @open="chassisModalOpen = true"
        />

        <!-- ②~ KP 各类别卡片 -->
        <KpCategoryCard
          v-for="(cat, i) in kpCardCats"
          :key="cat"
          :cat="cat"
          :step-num="i + 2"
          :lines="kpLinesByCat[cat] || []"
          :picker-items="pickerCatalog[cat] || []"
          :price-of="priceOf"
          :removable="!CORE_CATS.includes(cat)"
          :is-gpu="cat === 'GPU'"
          :gpu-arch="gpuArch"
          @set-line="(idx:any, patch:any)=>setLineForCat(cat, idx, patch)"
          @del-line="(idx:any)=>delLineForCat(cat, idx)"
          @add-line="addLineForCat(cat)"
          @remove-card="removeCard(cat)"
          @update:gpu-arch="(a:any)=>gpuArch = a"
        />

        <!-- 新增配置卡片（从 KP 类别列表选）-->
        <div class="add-card-wrap" v-if="availableKpCats.length">
          <select class="add-card-sel" v-model="pendingNewCat" @change="onAddCard">
            <option value="">+ 新增配置卡片…</option>
            <option v-for="c in availableKpCats" :key="c.id" :value="c.name">{{ c.name }}</option>
          </select>
        </div>

        <!-- KP 配件合计 -->
        <div class="kp-total-bar cpq-stream-edge">
          <span>KP 配件合计 <b>¥<CountNumber :value="kpTotal" /></b></span>
          <span class="kp-total-hint">CPU + 内存 + 硬盘 + GPU + 网卡 + …</span>
        </div>
      </div>

      <!-- 右栏：成本汇总 + 保存 -->
      <div class="sc-col-right">
        <div class="sc-cost-card glass cpq-stream-edge">
          <div class="cc-hero">
            <span class="cc-hero-label">整机总价</span>
            <span class="cc-hero-val">¥<CountNumber :value="grand" /></span>
          </div>
          <div class="cc-row">
            <span class="cc-row-label">机箱成本（L6）</span>
            <span class="cc-row-val">¥<CountNumber :value="l6Total" /></span>
          </div>
          <div class="cc-row">
            <span class="cc-row-label">KP 配件成本</span>
            <span class="cc-row-val">¥<CountNumber :value="kpTotal" /></span>
          </div>
          <button class="sc-save" :disabled="saving" @click="saveConfig">{{ saving ? '保存中…' : '保存 / 生成 BOM' }}</button>
        </div>
      </div>
    </div>

    <!-- 机箱配置弹窗：L6 四步（基准 / 前 / 后面板 / 电源）-->
    <a-modal
      v-model:open="chassisModalOpen"
      :title="`${model.name} · 机箱配置`"
      :footer="null"
      width="1120px"
      wrap-class-name="chassis-modal"
    >
      <L6ChassisConfig
        stepper
        :base-config-id="model.base_config_id"
        :kp-summary="kpSummary"
        @apply="onL6Apply"
      />
    </a-modal>

    <!-- BOM 展示 -->
    <div v-if="bomVisible" class="sc-bom-mask" @click.self="bomVisible = false">
      <div class="sc-bom">
        <div class="bom-head"><h3>配置清单（BOM · 无价）</h3><button @click="bomVisible = false">✕</button></div>
        <div class="bom-sec"><div class="bom-st">L6 机箱配置</div>
          <div class="bom-row" v-for="(r, ri) in (l6Apply?.l6Rows || [])" :key="'l'+ri"><span class="bmn">{{ r.part_name }}</span><span class="bmq">{{ r.qty }}</span></div>
        </div>
        <div class="bom-sec"><div class="bom-st">KP 核心配件</div>
          <div class="bom-row" v-for="(l, i) in kpLines" :key="'k'+i"><span class="bmn">{{ l.cat }}：{{ kpPart(l.pn)?.name || l.pn }}</span><span class="bmq">{{ l.qty }}</span></div>
        </div>
        <div class="bom-note">此清单为无价 BOM（服务器页产物）。如需报价，请在报价工作台基于此配置生成。</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sc-wizard { max-width: 1440px; margin: 0 auto; }
.sc-steps { display: flex; align-items: center; gap: 0; margin-bottom: 20px; padding: 12px 20px;
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); border-radius: 18px;
  box-shadow: var(--cpq-shadow-md); position: sticky; top: 0; z-index: 10; }
.sc-step { display: flex; align-items: center; gap: 6px; cursor: pointer; transition: all .2s; }
.sc-step:hover .sn { transform: scale(1.1); }
.sc-step .sn { width: 24px; height: 24px; border-radius: 6px; background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; transition: all .2s; }
.sc-step .st { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); transition: all .2s; }
.sc-step:hover .st { color: var(--cpq-accent-primary,#1677FF); }
.sc-step-line { flex: 1; height: 1px; background: var(--cpq-overlay-w10); margin: 0 8px; max-width: 60px; }
.sc-banner { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.bm-name { font-size: 18px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.bm-sub { color: var(--cpq-text-secondary,#9BA1AA); font-size: 13px; }
.sc-layout { display: flex; gap: 16px; align-items: flex-start; }
.sc-col-left { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.sc-col-right { flex: 0 0 280px; position: sticky; top: 76px; max-height: calc(100vh - 92px); overflow-y: auto; }
.sc-cost-card { padding: 18px; border-radius: 18px;
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px); border: 1px solid var(--cpq-overlay-a15); box-shadow: var(--cpq-shadow-md); }
.cc-hero { display: flex; flex-direction: column; gap: 2px; padding-bottom: 14px; margin-bottom: 14px; border-bottom: 1px solid var(--cpq-overlay-w10); }
.cc-hero-label { font-size: 12px; color: var(--cpq-text-muted,#6E7582); }
.cc-hero-val { font-size: 24px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); line-height: 1.2; }
.cc-row { display: flex; justify-content: space-between; align-items: baseline; padding: 9px 0; font-size: 13px; }
.cc-row-label { color: var(--cpq-text-secondary,#9BA1AA); }
.cc-row-val { color: var(--cpq-text-primary, #E8ECEF); font-weight: 600; }
.kp-total-bar { position: relative; display: flex; align-items: baseline; gap: 14px; padding: 12px 18px;
  border: 1px solid var(--cpq-glass-border-strong, var(--cpq-overlay-a15)); border-radius: var(--cpq-radius-lg, 14px);
  background: var(--cpq-overlay-a8); backdrop-filter: blur(var(--cpq-glass-blur-1, 12px)); }
.kp-total-bar b { color: var(--cpq-accent-primary,#1677FF); font-size: 18px; }
.kp-total-hint { font-size: 11px; color: var(--cpq-text-muted,#6E7582); margin-left: auto; }
.sc-save { width: 100%; margin-top: 16px; padding: 11px 22px; background: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-on-primary); font-weight: 700; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; transition: all .2s; }
.sc-save:hover { transform: translateY(-1px); box-shadow: 0 0 18px var(--cpq-overlay-a40); }
.sc-save:disabled { opacity: .5; cursor: not-allowed; }
.add-card-wrap { display: flex; justify-content: center; }
.add-card-sel { width: 100%; max-width: 320px; background: var(--cpq-overlay-b20); color: var(--cpq-text-secondary,#9BA1AA);
  border: 1px dashed var(--cpq-overlay-w20); border-radius: 12px; padding: 11px 14px; font-size: 13px; outline: none; cursor: pointer; transition: all .2s; appearance: none; }
.add-card-sel:hover { border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); background: var(--cpq-overlay-a8); }
@media (max-width: 960px) {
  .sc-layout { flex-direction: column; align-items: stretch; }
  .sc-col-right { position: static; max-height: none; flex: 1; }
}
.sc-bom-mask { position: fixed; inset: 0; background: var(--cpq-overlay-b85); backdrop-filter: blur(8px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 20px; }
.sc-bom { background: var(--cpq-bg-elevated); backdrop-filter: blur(24px); border: 1px solid var(--cpq-border-primary); border-radius: 16px; max-width: 640px; width: 100%; max-height: 80vh; overflow-y: auto; padding: 22px; box-shadow: var(--cpq-shadow-lg); }
.bom-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.bom-head h3 { font-size: 16px; color: var(--cpq-text-primary, #E8ECEF); }
.bom-head button { background: transparent; border: none; color: var(--cpq-text-secondary,#9BA1AA); font-size: 18px; cursor: pointer; }
.bom-sec { margin-bottom: 16px; }
.bom-st { font-size: 13px; color: var(--cpq-text-secondary,#9BA1AA); margin-bottom: 8px; font-weight: 600; }
.bom-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px dashed var(--cpq-overlay-w6); font-size: 13px; }
.bom-row .bmq { color: var(--cpq-text-secondary,#9BA1AA); }
.bom-note { margin-top: 12px; padding: 10px 14px; background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a20); border-radius: 12px; color: var(--cpq-accent-primary,#1677FF); font-size: 12px; }
</style>

<!-- a-modal 渲染到 portal（scoped 之外），用全局样式撑满 L6ChassisConfig -->
<style>
.chassis-modal .ant-modal-body { padding: 18px 20px; max-height: 82vh; overflow-y: auto; }
.chassis-modal .ant-modal { top: 30px; }
</style>
