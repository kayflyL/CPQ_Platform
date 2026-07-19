<script setup lang="ts">
/** 配置流程（standalone 服务器页）— L6 机箱选配复用 L6ChassisConfig + 自有 KP 面板。
 *  L6 部分（基准/前面板/后面板/电源）全部委托给 L6ChassisConfig；本组件只管 KP 核心配件 + 保存产出 BOM。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { kpPartsApi, configSchemeApi, type ServerModel, type KpPart } from '@/api/serverConfig'
import L6ChassisConfig from '@/components/quote/L6ChassisConfig.vue'
import PartPicker from '@/components/common/PartPicker.vue'
import { fromKpPart } from '@/composables/usePartAdapter'
import type { PickerItem } from '@/types/picker'

const props = defineProps<{ model: ServerModel }>()

// ---- KP 核心配件（本组件自有；L6 部分由 L6ChassisConfig 管）----
const kpLines = ref<{ cat: string; pn: string; qty: number }[]>([])
const gpuArch = ref<'none' | 'pt' | 'switch'>('none')
const kpCatalog = ref<Record<string, KpPart[]>>({})
const kpCategories = ref<{ id: number; name: string }[]>([])

const l6Apply = ref<{ baseConfigId: number | null; totals: any; picks: any; l6Rows: any[] } | null>(null)

const CATS = computed(() => kpCategories.value.map(c => c.name))
const CORE_CATS = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']
const isCore = (cat: string) => CORE_CATS.includes(cat)

async function init() {
  try {
    kpCategories.value = await kpPartsApi.categories()
    const series = props.model.base_config_id ? undefined : undefined // series 过滤交由 L6ChassisConfig；KP 按目录全量
    const kpPartsResults = await Promise.all(
      kpCategories.value.map(c => kpPartsApi.listByCategory(c.id))
    )
    kpCategories.value.forEach((c, i) => { kpCatalog.value[c.name] = kpPartsResults[i] })

    if (!kpLines.value.length) {
      const firstPn = (cat: string) => (kpCatalog.value[cat]?.[0] || {}).pn || ''
      const isAI = props.model.use === 'AI加速计算'
      kpLines.value = [
        { cat: 'CPU', pn: (partsOf('CPU')[0] || {}).pn || '', qty: 1 },
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
// KP 料号归一化为 PickerItem[]，喂给 PartPicker（只在 kpCatalog 变化时重算）
const pickerCatalog = computed<Record<string, PickerItem[]>>(() => {
  const out: Record<string, PickerItem[]> = {}
  for (const [cat, list] of Object.entries(kpCatalog.value)) out[cat] = (list || []).map(fromKpPart)
  return out
})
function kpPart(pn: string) { return CATS.value.flatMap(c => kpCatalog.value[c] || []).find(p => p.pn === pn) }
function priceOf(pn: string) { return kpPart(pn)?.unit_price || 0 }
function setKpCat(i: number, cat: string) { kpLines.value[i] = { ...kpLines.value[i], cat, pn: (partsOf(cat)[0] || {}).pn || '' } }
function setKp(i: number, patch: Partial<{ pn: string; qty: number }>) { kpLines.value[i] = { ...kpLines.value[i], ...patch } }
function delKp(i: number) { kpLines.value.splice(i, 1) }
function addEmptyKp() { kpLines.value.push({ cat: '', pn: '', qty: 1 }) }

// ---- kpSummary：喂给 L6ChassisConfig 做 derive ----
const kpSummary = computed(() => {
  const cpu = kpLines.value.find(l => l.cat === 'CPU')
  const gpu = kpLines.value.find(l => l.cat === 'GPU')
  const drivesByKind: Record<string, number> = {}
  for (const l of kpLines.value) {
    if (l.cat !== 'HDD/SSD') continue
    const part = kpPart(l.pn) as any
    const name = (part?.name || '') + ' ' + (part?.sub_type || '')
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
  if (!l6Apply.value) { message.warning('请先完成 L6 机箱选配'); return }
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

    <!-- 步骤指示器：基准/前面板/后面板/电源/核心配件 -->
    <div class="sc-steps">
      <div class="sc-step" @click="scrollToPanel('l6-panel-base')"><span class="sn">1</span><span class="st">基准配置</span></div>
      <div class="sc-step-line"></div>
      <div class="sc-step" @click="scrollToPanel('l6-panel-front')"><span class="sn">2</span><span class="st">前面板</span></div>
      <div class="sc-step-line"></div>
      <div class="sc-step" @click="scrollToPanel('l6-panel-rear')"><span class="sn">3</span><span class="st">后面板</span></div>
      <div class="sc-step-line"></div>
      <div class="sc-step" @click="scrollToPanel('l6-panel-psu')"><span class="sn">4</span><span class="st">电源</span></div>
      <div class="sc-step-line"></div>
      <div class="sc-step" @click="scrollToPanel('panel-kp')"><span class="sn">5</span><span class="st">核心配件</span></div>
    </div>

    <!-- L6 机箱选配（共用组件）-->
    <L6ChassisConfig
      :base-config-id="model.base_config_id"
      :kp-summary="kpSummary"
      @apply="onL6Apply"
    />

    <!-- ⑤ KP 核心配件（本组件自有）-->
    <div id="panel-kp" class="sc-panel" style="margin-top: 16px;">
      <div class="sc-phead"><span class="num">5</span><h2>核心配件</h2><span class="hint">CPU/GPU 驱动功耗与线缆推导</span><span class="amt">¥{{ kpTotal.toLocaleString() }}</span></div>
      <div class="sc-pbody">
        <div :class="['sc-kp-line', { core: isCore(l.cat) }]" v-for="(l, i) in kpLines" :key="i">
          <select v-if="!isCore(l.cat)" class="sc-sel" :value="l.cat" @change="(e:any)=>setKpCat(i, e.target.value)"><option v-for="c in CATS" :key="c" :value="c">{{ c }}</option></select>
          <span v-else class="sc-kp-cat-fixed">{{ l.cat }}</span>
          <PartPicker :items="pickerCatalog[l.cat] || []" :model-value="l.pn" size="small" placeholder="(请选择)" @update:model-value="(pn:any)=>setKp(i, { pn: typeof pn === 'string' ? pn : '' })" />
          <div class="sc-step"><button @click="setKp(i, { qty: Math.max(0, l.qty - 1) })">−</button><input :value="l.qty" @change="(e:any)=>setKp(i, { qty: parseInt(e.target.value)||0 })" /><button @click="setKp(i, { qty: l.qty + 1 })">+</button></div>
          <span class="sc-kp-price">¥{{ (priceOf(l.pn) * l.qty).toLocaleString() }}</span>
          <button v-if="!isCore(l.cat)" class="sc-del" @click="delKp(i)">✕</button>
          <span v-else class="sc-kp-del-placeholder" aria-hidden="true"></span>
        </div>
        <button class="sc-add" @click="addEmptyKp">+ 添加配件</button>
      </div>
    </div>

    <!-- 底部汇总 + 保存 -->
    <div class="sc-total">
      <span>L6 机箱 <b>¥{{ l6Total.toLocaleString() }}</b></span>
      <span>KP 配件 <b>¥{{ kpTotal.toLocaleString() }}</b></span>
      <span class="grand">整机 <b>¥{{ grand.toLocaleString() }}</b></span>
      <button class="sc-save" :disabled="saving" @click="saveConfig">{{ saving ? '保存中…' : '保存 / 生成 BOM' }}</button>
    </div>

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
.sc-wizard { max-width: 1180px; margin: 0 auto; padding-bottom: 70px; }
.sc-steps { display: flex; align-items: center; gap: 0; margin-bottom: 20px; padding: 12px 20px;
  background: linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.03) 40%, rgba(8,12,16,0.25) 100%);
  backdrop-filter: blur(16px) saturate(1.4);
  border: 1px solid rgba(0,245,212,0.12); border-radius: 18px;
  box-shadow: 0 22px 64px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.13); position: sticky; top: 0; z-index: 10; }
.sc-step { display: flex; align-items: center; gap: 6px; cursor: pointer; transition: all .2s; }
.sc-step:hover .sn { transform: scale(1.1); }
.sc-step .sn { width: 24px; height: 24px; border-radius: 6px; background: rgba(0,245,212,.12); color: var(--cpq-accent-primary,#00F5D4); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; transition: all .2s; }
.sc-step .st { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); transition: all .2s; }
.sc-step:hover .st { color: var(--cpq-accent-primary,#00F5D4); }
.sc-step-line { flex: 1; height: 1px; background: rgba(255,255,255,.10); margin: 0 8px; }
.sc-banner { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.sc-back { padding: 6px 14px; border: 1px solid var(--cpq-border-light,rgba(255,255,255,.18)); border-radius: 8px; color: var(--cpq-text-secondary,#9BA1AA); background: transparent; cursor: pointer; font-size: 13px; transition: all .2s; }
.sc-back:hover { color: var(--cpq-accent-primary,#00F5D4); border-color: var(--cpq-accent-primary,#00F5D4); }
.bm-name { font-size: 18px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.bm-sub { color: var(--cpq-text-secondary,#9BA1AA); font-size: 13px; }
.sc-panel { background: linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.03) 40%, rgba(8,12,16,0.25) 100%); backdrop-filter: blur(16px) saturate(1.4); border: 1px solid rgba(0,245,212,0.12); border-radius: 18px; overflow: hidden; box-shadow: 0 22px 64px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.13); }
.sc-phead { display: flex; align-items: center; gap: 12px; padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,.10); background: rgba(255,255,255,.015); }
.sc-phead .num { width: 26px; height: 26px; border-radius: 7px; background: rgba(0,245,212,.12); color: var(--cpq-accent-primary,#00F5D4); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
.sc-phead h2 { font-size: 16px; font-weight: 600; margin: 0; color: var(--cpq-text-primary, #E8ECEF); }
.sc-phead .hint { color: var(--cpq-text-muted,#6E7582); font-size: 12px; }
.sc-phead .amt { margin-left: auto; color: var(--cpq-accent-primary,#00F5D4); font-weight: 700; font-size: 14px; }
.sc-pbody { padding: 18px 20px; }
.sc-kp-line { display: grid; grid-template-columns: 110px 1fr 130px 90px 32px; gap: 9px; align-items: center; margin-bottom: 9px; }
.sc-kp-cat-fixed { display: flex; align-items: center; height: 36px; padding: 0 10px; font-size: 13px; font-weight: 600; color: var(--cpq-accent-primary,#00F5D4); }
.sc-kp-del-placeholder { width: 30px; }
.sc-sel { background: rgba(0,0,0,.2); color: var(--cpq-text-primary,#E8ECEF); border: 1px solid rgba(255,255,255,.10); border-radius: 8px; padding: 8px; font-size: 13px; outline: none; appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2300F5D4' d='M6 8L1 3h10z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 8px center; padding-right: 28px; }
.sc-sel option { background: #1a1d24; color: var(--cpq-text-primary,#E8ECEF); padding: 8px; }
.sc-sel.flex { width: 100%; }
.sc-sel:focus { border-color: var(--cpq-accent-primary,#00F5D4); box-shadow: 0 0 0 2px rgba(0,245,212,0.15); }
.sc-step { display: flex; background: rgba(0,0,0,.2); border: 1px solid rgba(255,255,255,.10); border-radius: 8px; overflow: hidden; }
.sc-step button { width: 30px; color: var(--cpq-text-secondary,#9BA1AA); font-size: 14px; background: transparent; border: none; cursor: pointer; transition: all .2s; }
.sc-step button:hover { color: var(--cpq-accent-primary,#00F5D4); }
.sc-step input { width: 100%; min-width: 0; text-align: center; border: none; background: transparent; color: var(--cpq-text-primary,#E8ECEF); font-size: 13px; outline: none; }
.sc-kp-price { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); text-align: right; }
.sc-del { width: 30px; height: 34px; border: 1px solid rgba(255,255,255,.10); border-radius: 8px; background: transparent; color: var(--cpq-text-muted,#6E7582); cursor: pointer; transition: all .2s; }
.sc-del:hover { color: #ff4d4f; border-color: rgba(255,77,79,.4); }
.sc-add { margin-top: 5px; padding: 7px 14px; border: 1px dashed rgba(255,255,255,.18); border-radius: 8px; background: transparent; color: var(--cpq-text-secondary,#9BA1AA); cursor: pointer; font-size: 13px; transition: all .2s; }
.sc-add:hover { border-color: var(--cpq-accent-primary,#00F5D4); color: var(--cpq-accent-primary,#00F5D4); background: rgba(0,245,212,.06); }
.sc-total { position: sticky; bottom: 0; display: flex; gap: 22px; align-items: center; padding: 13px 18px; margin-top: 16px;
  background: linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.03) 40%, rgba(8,12,16,0.25) 100%);
  backdrop-filter: blur(16px) saturate(1.4); border: 1px solid rgba(0,245,212,0.12); border-radius: 18px; box-shadow: 0 22px 64px rgba(0,0,0,0.30); }
.sc-total b { color: var(--cpq-accent-primary,#00F5D4); }
.sc-total .grand b { font-size: 16px; }
.sc-save { margin-left: auto; padding: 9px 22px; background: var(--cpq-accent-primary,#00F5D4); color: #062b25; font-weight: 700; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; transition: all .2s; }
.sc-save:hover { transform: translateY(-1px); box-shadow: 0 0 18px rgba(0,245,212,.4); }
.sc-save:disabled { opacity: .5; cursor: not-allowed; }
.sc-bom-mask { position: fixed; inset: 0; background: rgba(0,0,0,.7); backdrop-filter: blur(8px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 20px; }
.sc-bom { background: linear-gradient(135deg, rgba(20,22,28,0.65), rgba(12,14,20,0.55)); backdrop-filter: blur(24px) saturate(1.6); border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; max-width: 640px; width: 100%; max-height: 80vh; overflow-y: auto; padding: 22px; box-shadow: 0 12px 48px rgba(0,0,0,0.8); }
.bom-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.bom-head h3 { font-size: 16px; color: var(--cpq-text-primary, #E8ECEF); }
.bom-head button { background: transparent; border: none; color: var(--cpq-text-secondary,#9BA1AA); font-size: 18px; cursor: pointer; }
.bom-sec { margin-bottom: 16px; }
.bom-st { font-size: 13px; color: var(--cpq-text-secondary,#9BA1AA); margin-bottom: 8px; font-weight: 600; }
.bom-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px dashed rgba(255,255,255,.06); font-size: 13px; }
.bom-row .bmq { color: var(--cpq-text-secondary,#9BA1AA); }
.bom-note { margin-top: 12px; padding: 10px 14px; background: rgba(0,245,212,.08); border: 1px solid rgba(0,245,212,.2); border-radius: 12px; color: var(--cpq-accent-primary,#00F5D4); font-size: 12px; }
</style>
