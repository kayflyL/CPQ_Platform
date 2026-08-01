<script setup lang="ts">
/** 配置流程（standalone 服务器页）— 机箱概要卡 + KP 按类别拆卡。
 *  机箱（基准/前面板/后面板/电源）收进「机箱配置弹窗」（L6ChassisConfig stepper 模式）；
 *  KP 核心配件按 cat 独立成卡（CPU/Memory/HDD-SSD/GPU/NIC 预设 + 用户从 KP 类别新增）。
 *  kpLines 保持扁平 [{cat,pn,qty}]，卡片是渲染期 groupBy 视图 → 推导/持久化链路不动。 */
import { ref, computed, onMounted, nextTick } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { alertIcon, isBlockingSeverity } from '@/constants/ruleMeta'
import axios from 'axios'
import { kpPartsApi, configSchemeApi, baseConfigApi, type ServerModel, type KpPart } from '@/api/serverConfig'
import L6ChassisConfig from '@/components/quote/L6ChassisConfig.vue'
import ChassisCard from '@/components/server-config/ChassisCard.vue'
import KpCategoryCard from '@/components/server-config/KpCategoryCard.vue'
import SpecSheet from '@/components/server-config/SpecSheet.vue'
import CountNumber from '@/components/common/CountNumber.vue'
import { fromKpPart } from '@/composables/usePartAdapter'
import type { PickerItem } from '@/types/picker'
import type { GpuArch } from '@/composables/useServerConfig'
import { useSelectionRulesStore, type RuleContext } from '@/stores/selectionRules'
import { normalizeDriveKind } from '@/stores/selectionEngine'

const props = defineProps<{ model: ServerModel }>()
const selectionRulesStore = useSelectionRulesStore()

// ---- KP 核心配件（扁平 kpLines；卡片是 groupBy 视图）----
const kpLines = ref<{ cat: string; pn: string; qty: number }[]>([])
const gpuArch = ref<GpuArch>('none')
const kpCatalog = ref<Record<string, KpPart[]>>({})
const kpCategories = ref<{ id: number; name: string }[]>([])

const l6Apply = ref<{ baseConfigId: number | null; totals: any; picks: any; l6Rows: any[]; bomTemplate?: any; bomContext?: any } | null>(null)

// 构造 configs 数组供 SpecSheet 新模式使用
const specConfigs = computed(() => {
  if (!l6Apply.value) return []

  // 从 bomTemplate + bomContext 展开 L6 数据（对齐 BomTable 渲染逻辑）
  let l6Details: any[] = []
  const tpl = l6Apply.value.bomTemplate
  const ctx = l6Apply.value.bomContext || {}

  if (tpl?.rows && ctx) {
    // 按模板展开：catalogue=label（零件名），description=ctx.desc（规格）
    for (const row of tpl.rows) {
      const key = row.slot || row.type
      const v = ctx[key] || {}
      l6Details.push({
        catalogue: row.label || '',
        description: v.desc || '',
        part_category: '',
        qty: v.qty || '',
        category: 'L6',
        final_price: 0,
      })
    }
  } else {
    // Fallback：直接用 l6Rows（扁平料号）
    l6Details = (l6Apply.value.l6Rows || []).map((row: any) => ({
      catalogue: row.catalogue || '',
      description: row.description || '',
      part_category: '',
      qty: row.qty || 1,
      category: 'L6',
      final_price: row.final_price || row.base_price || 0,
    }))
  }

  // 从 kpLines 提取 KP 详细料件
  const kpDetails = kpLines.value.map((line) => {
    const part = kpPart(line.pn)
    return {
      catalogue: part?.name || line.pn || '',
      description: part?.specs ? Object.entries(part.specs).map(([k, v]) => `${k}: ${v}`).join(' · ') : '',
      part_category: line.cat || '',
      qty: line.qty || 1,
      category: 'Key Parts',
      final_price: (part?.unit_price || 0) * line.qty,
    }
  })

  // 从 picks 提取背板类型和电源信息
  const picks = l6Apply.value.picks || {}
  const bpType = picks.bp_type || 'dc'
  const bpDisplay = bpType === 'tri' ? 'Tri-Mode Backplane' : 'Pass-Thru Backplane'
  const psuDesc = ctx.psu_requirement?.desc || ''

  return [{
    config_name: 'Config1',
    server_model: props.model?.name || '',
    quantity: 1,
    l6_details: l6Details,
    kp_details: kpDetails,
    l6_total: l6Total.value,
    kp_total: kpTotal.value,
    unit_price: grand.value,
    total_price: grand.value,
    chassis_form: props.model?.base_config?.form || '',
    chassis_bays: props.model?.base_config?.bays ? `${props.model.base_config.bays} 盘位` : '',
    chassis_series: series.value || '',
    backplane_type: bpDisplay,
    power_supply: psuDesc,
  }]
})

// 预设 5 类（常驻显示，不可删）；其余 KP 类别由用户「+ 新增配置卡片」加入
const CORE_CATS = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']

// 机箱卡片用的 series / 基准配置名（从 model.base_config_id 关联的 BaseConfig 读）
const series = ref('')
const baseConfigName = ref('')
const baseGpuArchDefault = ref<string | null>(null)
const chassisModalOpen = ref(false)

async function init() {
  try {
    // 加载基准配置 → 拿 series（用户定调：芯片类型即显示 Orion/Polaris）+ name
    if (props.model.base_config_id) {
      try {
        const bc = await baseConfigApi.get(props.model.base_config_id)
        series.value = (bc as any).series || ''
        baseConfigName.value = (bc as any).name || ''
        baseGpuArchDefault.value = (bc as any).gpu_arch_default ?? null
      } catch { /* 无基准配置时机箱卡片显示 — */ }
    }

    kpCategories.value = await kpPartsApi.categories()
    // KP 目录按机型 series 过滤（API 已支持 series 参数；series 为空则不过滤）
    const kpPartsResults = await Promise.all(
      kpCategories.value.map(c => kpPartsApi.listByCategory(c.id, series.value || undefined))
    )
    kpCategories.value.forEach((c, i) => { kpCatalog.value[c.name] = kpPartsResults[i] })
    // 兼容性规则引擎：加载 active 规则供 selectionActions 求值（失败不阻塞配置）
    selectionRulesStore.ensureRules().catch(() => {})

    if (!kpLines.value.length) {
      const firstPn = (cat: string) => (kpCatalog.value[cat]?.[0] || {}).pn || ''
      // GPU 架构优先读 base_config.gpu_arch_default（数据驱动，可在「机箱能力」标签配）；
      // 未配时回退 model.use 字符串判定，兼容老基准配置
      const gd = baseGpuArchDefault.value
      const hasDefault = gd != null && gd !== ''
      const isAI = hasDefault ? gd !== 'none' : props.model.use === 'AI加速计算'
      kpLines.value = [
        { cat: 'CPU', pn: firstPn('CPU'), qty: 1 },
        { cat: 'Memory', pn: firstPn('Memory'), qty: 4 },
        { cat: 'HDD/SSD', pn: firstPn('HDD/SSD'), qty: 2 },
        { cat: 'GPU', pn: isAI ? firstPn('GPU') : '', qty: isAI ? 1 : 0 },
        { cat: 'NIC', pn: firstPn('NIC'), qty: 2 },
      ]
      gpuArch.value = hasDefault ? (gd as any) : (isAI ? 'pt' : 'none')
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
    // 盘类型：优先结构化 specs（interface/kind/type）；缺失回退型号名嗅探（大小写无关）
    const k = normalizeDriveKind(part?.specs?.interface || part?.specs?.kind || part?.specs?.type)
      || normalizeDriveKind(part?.name || '')
    if (k) drivesByKind[k] = (drivesByKind[k] || 0) + (l.qty || 0)
  }
  return {
    cpuPn: cpu?.pn, cpuQty: cpu?.qty,
    gpuPn: gpu?.pn, gpuQty: gpu?.qty,
    gpuArch: gpuArch.value,
    drivesByKind,
  }
})

// ---- 兼容性规则引擎：构建 context + 求值（缺必配 / 互斥 / 派生建议）----
function buildRuleContext(): RuleContext {
  const kp: RuleContext['kp'] = {}
  for (const l of kpLines.value) {
    const spec = (kpPart(l.pn)?.specs || {}) as Record<string, any>
    const node = kp[l.cat] || (kp[l.cat] = { qty: 0, items: [], spec: {} })
    node.qty += l.qty || 0
    node.items.push({ pn: l.pn, qty: l.qty, spec })
    if (Object.keys(node.spec).length === 0) node.spec = spec
  }
  // sata_qty：HDD/SSD 中机械盘(SATA/SAS)数量，供「每8盘→线缆」类 derive 规则
  let sata_qty = 0
  for (const it of (kp['HDD/SSD']?.items || [])) {
    const kind = String(it.spec?.kind || it.spec?.interface || '').toUpperCase()
    if (kind.includes('SATA') || kind.includes('SAS')) sata_qty += it.qty || 0
  }
  return {
    kp,
    config: { series: series.value, model: props.model?.name, form: props.model?.base_config?.form, sata_qty },
    opportunity: {},
  }
}
const selectionActions = computed(() => selectionRulesStore.evaluateRules(buildRuleContext()))

const kpTotal = computed(() => kpLines.value.reduce((s, l) => s + priceOf(l.pn) * l.qty, 0))
const l6Total = computed(() => l6Apply.value?.totals?.l6 || 0)
const grand = computed(() => l6Total.value + kpTotal.value)

function onL6Apply(payload: any) { l6Apply.value = payload }

const saving = ref(false)
const specVisible = ref(false)
const specTemplate = ref<{branding: any, display_options: any} | null>(null)

// 加载默认规格书模板
async function loadSpecTemplate() {
  try {
    const resp = await axios.get('/api/spec-templates/default')
    specTemplate.value = resp.data
  } catch (e: any) {
    console.error('Failed to load spec template:', e)
    message.warning('未找到默认规格书模板，请先在模板编辑器中创建')
  }
}

async function printSpec() {
  specVisible.value = true
  await nextTick()
  window.print()
}
// 阻断级兼容性冲突（互斥/缺必配）确认：可强存，仅校验不锁死（保留手改优先 [[derive-must-have-manual-fallback]]）
function confirmBlocking(blocking: { desc: string }[]): Promise<boolean> {
  return new Promise(resolve => {
    Modal.confirm({
      title: `存在 ${blocking.length} 项兼容性冲突`,
      content: blocking.map(b => b.desc).join('；'),
      okText: '仍然保存',
      okType: 'danger',
      cancelText: '返回修改',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}
async function saveConfig() {
  if (!l6Apply.value) { message.warning('请先完成机箱选配'); return }
  // CRE 阻断级校验升级：有 conflict/require 命中时弹确认，用户可「仍然保存」强存
  const blocking = selectionActions.value.filter(a => isBlockingSeverity(a.severity))
  if (blocking.length && !(await confirmBlocking(blocking))) return
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
    specVisible.value = true
    message.success('配置已保存，已生成规格书')
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

onMounted(() => {
  init()
  loadSpecTemplate()
})
</script>

<template>
  <div class="sc-wizard">
    <div class="sc-banner">
      <span class="bm-name">{{ model.name }}</span>
      <span class="bm-sub">{{ model.use }} · {{ model.base_config?.form }} · {{ model.base_config?.bays }} 盘位</span>
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
        <!-- 兼容性规则实时校验（缺必配 / 互斥 / 派生建议）-->
        <div v-if="selectionActions.length" class="sc-alerts glass-light">
          <div class="sc-alerts-head"><span class="sc-alerts-ic">🛡</span> 兼容性校验</div>
          <div v-for="a in selectionActions" :key="a.ruleId" class="sc-alert" :class="`sev-${a.severity}`">
            <span class="sc-alert-ic">{{ alertIcon(a.severity) }}</span>
            <span class="sc-alert-tx">{{ a.desc }}</span>
          </div>
        </div>

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
          @set-line="(idx:any, patch:any)=>setLineForCat(cat, idx, patch)"
          @del-line="(idx:any)=>delLineForCat(cat, idx)"
          @add-line="addLineForCat(cat)"
          @remove-card="removeCard(cat)"
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
          <button class="sc-save" :disabled="saving" @click="saveConfig">{{ saving ? '保存中…' : '保存 / 生成规格书' }}</button>
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

    <!-- 配置规格书（打印用 overlay，使用 Teleport 移到 body 层级，避免打印时父级样式干扰） -->
    <Teleport to="body">
      <div v-if="specVisible" class="spec-sheet-overlay" @click.self="specVisible = false">
        <div class="spec-sheet-scroll">
          <SpecSheet
            class="spec-sheet-root"
            :configs="specConfigs"
            :branding="specTemplate?.branding || {}"
            :display-options="specTemplate?.display_options"
          />
        </div>
        <!-- 工具栏：贴规格书右侧边缘，sticky 随滚动停靠 -->
        <div class="spec-sheet-toolbar ss-no-print">
          <button class="ss-tool-btn primary" @click="printSpec">打印 / 导出 PDF</button>
          <button class="ss-tool-btn" @click="specVisible = false">关闭</button>
        </div>
      </div>
    </Teleport>
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
.sc-alerts { padding: 12px 16px; border-radius: var(--cpq-radius-lg, 14px); display: flex; flex-direction: column; gap: 8px; }
.sc-alerts-head { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #1d2129); }
.sc-alerts-ic { font-size: 14px; }
.sc-alert { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.5; padding: 6px 10px; border-radius: 8px; }
.sc-alert.sev-conflict { background: rgba(255,77,79,.1); color: var(--cpq-accent-danger, #ff4d4f); }
.sc-alert.sev-require { background: rgba(22,119,255,.1); color: var(--cpq-accent-primary, #1677ff); }
.sc-alert.sev-info { background: var(--cpq-overlay-a8, rgba(255,255,255,.5)); color: var(--cpq-text-secondary, #4e5969); }
.sc-alert-ic { flex: none; font-size: 13px; }
.sc-alert-tx { flex: 1; }
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
.spec-sheet-overlay { position: fixed; inset: 0; z-index: 200; background: var(--cpq-overlay-b85);
  backdrop-filter: blur(8px); display: flex; flex-direction: row; align-items: flex-start; justify-content: center;
  gap: 16px; padding: 32px 16px; overflow-y: auto; }
.spec-sheet-scroll { display: flex; flex: 1; max-width: 900px; flex-direction: column; align-items: center; gap: 14px; }
/* 工具栏：贴规格书右侧边缘，sticky 随滚动停靠（overlay 的直接子元素，scroll context 内生效） */
.spec-sheet-toolbar { position: sticky; top: 32px; align-self: flex-start;
  display: flex; flex-direction: column; gap: 10px; z-index: 10; }
.ss-tool-btn { padding: 7px 18px; font-size: 13px; font-weight: 600; border-radius: 10px; cursor: pointer;
  border: 1px solid var(--cpq-overlay-w20); background: var(--cpq-overlay-b60);
  color: var(--cpq-text-primary,#E8ECEF); backdrop-filter: blur(12px); transition: all .2s; }
.ss-tool-btn:hover { border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); }
.ss-tool-btn.primary { background: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-on-primary, #fff); border-color: transparent; }
.ss-tool-btn.primary:hover { color: var(--cpq-accent-on-primary, #fff); opacity: .92; }
</style>

<!-- a-modal 渲染到 portal（scoped 之外），用全局样式撑满 L6ChassisConfig -->
<style>
.chassis-modal .ant-modal-body { padding: 18px 20px; max-height: 82vh; overflow-y: auto; }
.chassis-modal .ant-modal { top: 30px; }
</style>
