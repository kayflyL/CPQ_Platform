<script setup lang="ts">
/**
 * L6 机箱选配（共用组件）— 服务器配置页(ConfigWizard) 与 报价工作台(Workspace) 共用。
 * 4 个面板：①基准配置（含「选择基准配置」下拉）②前面板 ③后面板(PCIe IO + OCP + GPU 线) ④电源。
 *
 * 内部用 useServerConfig() 管 rear/overrides/baseBpType；kpSummary prop 合成进 kpLines+gpuArch 后 rederive。
 * 选配变动 → emit `apply`（含 totals/picks/l6Rows）+ `update:baseConfigId`。
 * 父组件切 tab 重挂时由 onMounted 读 initialPicks 自 hydrate。
 *
 * 遵循：[[ocp-is-networking-not-pcie]]（OCP 独立网络分段）/ [[derive-must-have-manual-fallback]]（推导仅兜底，料号库手选）
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, watchEffect, reactive } from 'vue'
import { message } from 'ant-design-vue'
import {
  baseConfigApi, partsApi, rearIOApi, deriveApi, bomTemplateApi,
  type PartMaster, type BaseConfig, type RearIOSlotOption, type BomTemplate,
} from '@/api/serverConfig'
import { useServerConfig, type GpuArch } from '@/composables/useServerConfig'
import { evalBomContext, type BomEvalContext } from '@/utils/bomRuleEngine'
import PartPicker from '@/components/common/PartPicker.vue'
import CountNumber from '@/components/common/CountNumber.vue'
import { fromPartMaster } from '@/composables/usePartAdapter'

const props = defineProps<{
  baseConfigId?: number | null
  kpSummary?: {
    cpuPn?: string; cpuQty?: number
    gpuPn?: string; gpuQty?: number
    gpuArch?: GpuArch
    drivesByKind?: Record<string, number> // {SATA, SAS, NVMe}
  }
  initialPicks?: any
  /** 弹窗模式：左侧步骤条 + 右侧单步内容（堆叠模式为 false，Workspace 行为不变） */
  stepper?: boolean
}>()

const emit = defineEmits<{
  (e: 'apply', payload: { baseConfigId: number | null; totals: any; picks: any; l6Rows: any[] }): void
  (e: 'update:baseConfigId', id: number | null): void
}>()

const {
  kpLines, gpuArch, rear, overrides, baseBpType, result,
  rederive, frontCableQty, psuQty, bpType, isManual, setOverride,
  optionQty, slotFilled, incOption, decOption, uniqueRealOptions, setRearSingle,
} = useServerConfig()

const allBaseConfigs = ref<BaseConfig[]>([])          // 「选择基准配置」下拉数据
const baseConfig = ref<(BaseConfig & { parts: any[]; rear_slots?: string[] }) | null>(null)
const bomTemplate = ref<BomTemplate | null>(null)     // 该机型族的左栏 L6 行骨架模板

// stepper 模式：左步骤条当前激活步（仅 stepper=true 时生效）
const L6_STEPS = [
  { id: 'base', n: 1, label: '基准配置' },
  { id: 'front', n: 2, label: '前面板' },
  { id: 'rear', n: 3, label: '后面板' },
  { id: 'psu', n: 4, label: '电源' },
] as const
const activeStep = ref<'base' | 'front' | 'rear' | 'psu'>('base')
const frontCables = ref<PartMaster[]>([])
const gpuCableParts = ref<PartMaster[]>([])
const psuParts = ref<PartMaster[]>([])
const bpParts = ref<PartMaster[]>([])
const rearOptions = ref<Record<string, RearIOSlotOption[]>>({})

// 模块级缓存：按 series 缓存 reference 数据，切 tab 重挂命中缓存（避免 6 调用风暴）
interface RefCache { frontCables: PartMaster[]; gpuCableParts: PartMaster[]; psuParts: PartMaster[]; bpParts: PartMaster[]; rearOptions: Record<string, RearIOSlotOption[]> }
const _refCache = new Map<string, RefCache>()
let _allBaseConfigsLoaded = false

const CORE_DRIVE_KINDS = ['SATA', 'SAS', 'NVMe'] as const
const DEFAULT_REAR_SLOTS = ['IO1', 'IO2', 'IO3', 'IO4', 'OCP']
const rearSlots = computed(() => (baseConfig.value as any)?.rear_slots || DEFAULT_REAR_SLOTS)
const ioSlots = computed(() => rearSlots.value.filter(s => s !== 'OCP'))
const hasOcp = computed(() => rearSlots.value.includes('OCP'))

const SLOT_CAP: Record<string, number> = { IO1: 2, IO2: 2, IO3: 2, IO4: 2, OCP: 1 }
const OPTION_LABEL: Record<string, string> = {
  x16: 'X16 Riser', x8: 'X8 Riser', nvme: 'NVMe模组', sata: 'SATA模组',
  ocp_x8: 'OCP X8', ocp_x16: 'OCP X16', blank: '挡片',
}
const optionLabel = (t: string) => OPTION_LABEL[t] || t

// ---- reference 数据加载（带缓存）----
async function loadAllBaseConfigs() {
  if (_allBaseConfigsLoaded) return
  try {
    const res = await baseConfigApi.list()
    allBaseConfigs.value = res.configs || []
    _allBaseConfigsLoaded = true
  } catch (e) { /* 忽略，下拉空 */ }
}

async function loadReference(series: string | undefined) {
  const key = series || '__default__'
  const cached = _refCache.get(key)
  if (cached) {
    frontCables.value = cached.frontCables
    gpuCableParts.value = cached.gpuCableParts
    psuParts.value = cached.psuParts
    bpParts.value = cached.bpParts
    rearOptions.value = cached.rearOptions
    return
  }
  const [fcRes, gpuCableRes, rearRes, psuPartsRes, bpRes] = await Promise.all([
    partsApi.list({ category: '前面板线缆' }),
    partsApi.list({ category: 'GPU电源线' }),
    rearIOApi.getOptions(series === 'Polaris' ? 'Polaris' : 'Orion'),
    partsApi.list({ category: '电源' }),
    partsApi.list({ category: '背板' }),
  ])
  frontCables.value = fcRes.parts
  gpuCableParts.value = gpuCableRes.parts
  rearOptions.value = (rearRes as any).slots || {}
  psuParts.value = psuPartsRes.parts
  bpParts.value = bpRes.parts
  _refCache.set(key, {
    frontCables: fcRes.parts, gpuCableParts: gpuCableRes.parts,
    psuParts: psuPartsRes.parts, bpParts: bpRes.parts,
    rearOptions: (rearRes as any).slots || {},
  })
}

async function loadBaseConfig(id: number) {
  try {
    baseConfig.value = await baseConfigApi.get(id)
    // baseBpType 由下方 watchEffect 跟踪 baseBackplaneType（须在 baseBackplaneType 声明之后注册）
    // 加载该机型族的左栏 BOM 行骨架模板
    try {
      bomTemplate.value = await bomTemplateApi.getForBaseConfig(id)
    } catch (e: any) {
      bomTemplate.value = null
    }
  } catch (e: any) {
    baseConfig.value = null
    bomTemplate.value = null
  }
}

// ---- 背板（从料号库，三模/直连）----
const bpTri = computed(() => bpParts.value.filter(p => /三模|tri/i.test((p.name || '') + ((p.specs as any)?.bt || ''))))
const bpDc = computed(() => bpParts.value.filter(p => /直连|dc|direct/i.test((p.name || '') + ((p.specs as any)?.bt || ''))))
const baseBackplane = computed(() => {
  const parts = baseConfig.value?.parts || []
  const inParts = parts.find((p: any) => p.category === '背板')
  if (inParts) return inParts
  const triPn = (baseConfig.value as any)?.bp_tri_pn
  const dcPn = (baseConfig.value as any)?.bp_dc_pn
  const pn = triPn || dcPn
  return pn ? bpParts.value.find(p => p.pn === pn) : null
})
const baseBackplaneType = computed<'tri' | 'dc' | null>(() => {
  const bp: any = baseBackplane.value
  if (!bp) return null
  return /三模|tri/i.test((bp.name || '') + ((bp.specs as any)?.bt || '')) ? 'tri' : 'dc'
})
const effectiveBp = computed(() => {
  if (overrides.bpPn) {
    const hit = bpParts.value.find(p => p.pn === overrides.bpPn)
    if (hit) return hit
  }
  // 未加载基准配置时不自动选背板（避免 Workspace 无机型时空配置凭空出现背板行）
  if (!baseConfig.value) return null
  const t = bpType()
  if (baseBackplane.value && baseBackplaneType.value === t) return baseBackplane.value
  const list = t === 'tri' ? bpTri.value : bpDc.value
  return list[0] || null
})
const effectiveBaseParts = computed(() => {
  const parts = [...(baseConfig.value?.parts || [])]
  const bp = effectiveBp.value
  if (bp) {
    const bpLine = { pn: bp.pn, name: bp.name, category: '背板', unit_price: bp.unit_price, quantity: 1 }
    const idx = parts.findIndex((p: any) => p.category === '背板')
    if (idx >= 0) parts[idx] = bpLine as any
    else parts.push(bpLine as any)
  }
  return parts
})

// ---- 前面板线缆 ----
function frontCableParts(k: string) {
  const ku = k.toUpperCase()
  return frontCables.value.filter(p => String((p.specs as any)?.kind ?? '').toUpperCase() === ku)
}
function frontCablePickedPn(k: string) {
  return overrides['fc-' + k + '-pn'] || frontCableParts(k)[0]?.pn || ''
}
function frontCableInfo(k: string): { pn: string; n: number; group: number | '-'; price: number; name: string } {
  const c = result.value?.front_cables.find(x => x.kind === k)
  const p = frontCables.value.find(x => x.pn === frontCablePickedPn(k))
  const group: number | '-' = c?.group_size != null ? c.group_size : '-'
  return {
    n: c?.drive_count ?? 0, group,
    price: p?.unit_price ?? 0, pn: p?.pn || '',
    name: p?.name || '',
  }
}

// ---- 后面板 ----
function realOptions(slot: string) {
  return (rearOptions.value[slot] || []).filter(o => o.option_type !== 'blank')
}
function canInc(slot: string) { return slotFilled(slot) < (SLOT_CAP[slot] ?? 0) }
function slotPrice(slot: string): number {
  const opts = rearOptions.value[slot] || []
  return (rear[slot] || []).reduce((s, t) => s + (t === 'blank' ? 0 : (opts.find(o => o.option_type === t)?.total_price || 0)), 0)
}

// ---- PSU / GPU 线（料号库手选，推导仅兜底）----
function psuPicked(): PartMaster | null {
  if (!overrides.psuPn) return null
  return psuParts.value.find(p => p.pn === overrides.psuPn) || null
}
function psuName(): string { return psuPicked()?.name || result.value?.psu?.psu?.name || '' }
function psuUnitPrice(): number {
  const p = psuPicked()
  if (p) return p.unit_price || 0
  return result.value?.psu?.psu?.unit_price || 0
}
function gpuCablePicked(): PartMaster | null {
  if (!overrides.gpuCablePn) return null
  return gpuCableParts.value.find(p => p.pn === overrides.gpuCablePn) || null
}
function gpuCableQty(): number {
  if (overrides.gpuCableQty != null) return Number(overrides.gpuCableQty) || 0
  return result.value?.gpu_cables.total ?? 0
}
function gpuCableUnitPrice(): number { return gpuCablePicked()?.unit_price || 0 }

// ---- 合计 ----
const baseTotal = computed(() => effectiveBaseParts.value.reduce((s, p) => s + (p.unit_price || 0) * (p.quantity || 1), 0))
const frontTotal = computed(() => CORE_DRIVE_KINDS.reduce((s, k) => s + frontCableQty(k) * frontCableInfo(k).price, 0))
const rearTotal = computed(() => ioSlots.value.reduce((sum, slot) => sum + slotPrice(slot), 0))
const ocpTotal = computed(() => hasOcp.value ? slotPrice('OCP') : 0)
const psuLineTotal = computed(() => psuUnitPrice() * psuQty())
const gpuCableCost = computed(() => gpuCableQty() * gpuCableUnitPrice())
const l6Total = computed(() => baseTotal.value + frontTotal.value + rearTotal.value + ocpTotal.value + psuLineTotal.value + gpuCableCost.value)

const totals = computed(() => ({
  base: baseTotal.value, front: frontTotal.value, rear: rearTotal.value,
  ocp: ocpTotal.value, psu: psuLineTotal.value, gpuCable: gpuCableCost.value,
  l6: l6Total.value,
}))

// baseBpType 响应式跟踪基准自带背板类型（迁自 ConfigWizard.vue:116）。
// 必须在 baseBackplaneType 声明之后注册，否则 watchEffect 立即执行触发 TDZ。
watchEffect(() => { baseBpType.value = baseBackplaneType.value })

// ---- picks 快照（组件状态，用于切 tab 重挂 hydrate）----
const picks = computed(() => ({
  base_config_id: baseConfig.value?.id ?? props.baseConfigId ?? null,
  bp_type: bpType(),
  bp_pn: effectiveBp.value?.pn ?? null,
  rear: JSON.parse(JSON.stringify(rear)),
  overrides: JSON.parse(JSON.stringify(overrides)),
}))

// ---- L6 行（写回 cfg.items，供导出 preview_data_loader + 左栏 BomTable）----
function buildL6Rows() {
  const rows: any[] = []
  for (const p of effectiveBaseParts.value) {
    rows.push({ category: 'L6', part_name: p.name || p.pn, spec: p.pn, qty: p.quantity || 1, base_price: p.unit_price || 0, currency: 'RMB' })
  }
  for (const k of CORE_DRIVE_KINDS) {
    const qty = frontCableQty(k); const info = frontCableInfo(k)
    if (qty > 0) rows.push({ category: 'L6', part_name: `前面板${k}线缆`, spec: info.pn, qty, base_price: info.price, currency: 'RMB' })
  }
  for (const slot of [...ioSlots.value, ...(hasOcp.value ? ['OCP'] : [])]) {
    for (const t of uniqueRealOptions(slot)) {
      const q = optionQty(slot, t)
      const opt = (rearOptions.value[slot] || []).find(o => o.option_type === t)
      const unit = opt?.total_price || 0
      if (q > 0) rows.push({ category: 'L6', part_name: `后面板${slot}:${optionLabel(t)}`, spec: '', qty: q, base_price: unit, currency: 'RMB' })
    }
  }
  if (psuQty() > 0 && psuUnitPrice() > 0) rows.push({ category: 'L6', part_name: `电源:${psuName()}`, spec: '', qty: psuQty(), base_price: psuUnitPrice(), currency: 'RMB' })
  if (gpuCableQty() > 0 && gpuCableUnitPrice() > 0) rows.push({ category: 'L6', part_name: 'GPU供电线', spec: gpuCablePicked()?.pn || '', qty: gpuCableQty(), base_price: gpuCableUnitPrice(), currency: 'RMB' })
  return rows
}

// ---- kpSummary → kpLines + gpuArch，喂给 derive ----
function applyKpSummary(s: any) {
  if (!s) return
  const lines: { cat: string; pn: string; qty: number }[] = []
  if (s.cpuPn) lines.push({ cat: 'CPU', pn: s.cpuPn, qty: s.cpuQty || 1 })
  if (s.gpuPn) lines.push({ cat: 'GPU', pn: s.gpuPn, qty: s.gpuQty || 1 })
  if (s.drivesByKind) {
    for (const [kind, q] of Object.entries(s.drivesByKind)) {
      if ((q as number) > 0) lines.push({ cat: 'HDD/SSD', pn: '', qty: q as number })
    }
  }
  kpLines.value = lines
  gpuArch.value = (s.gpuArch || (s.gpuPn ? 'pt' : 'none')) as GpuArch
  rederive()
}

// ---- 左栏 L6 摘要模板的行值解析（catalogue/desc/qty，无价）----
// 按 bom_templates.rows[].rule 求值（求值器跑前端，规则跟模板存 JSONB）。组装 ctx + 调 evalBomContext。
// 变量字典在此组装；规则失败(manual/缺数据)→ 留空，工作台手填（[[derive-must-have-manual-fallback]]）。
function buildBomContext(): Record<string, { desc: string; qty: number | string }> {
  const psuP = psuPicked()
  const ctx: BomEvalContext = {
    vars: {
      bays: (baseConfig.value as any)?.bays,
      form: (baseConfig.value as any)?.form,
      series: (baseConfig.value as any)?.series,
      bp_type: bpType(),
      psu_qty: psuQty(),
      psu_wattage: (psuP?.specs as any)?.wattage,
      psu_name: psuName(),
      gpu_qty: props.kpSummary?.gpuQty || 0,
      gpu_cable_qty: gpuCableQty(),
    },
    parts: effectiveBaseParts.value,
    rear,
    frontCableQty,
    frontCableInfo,
  }
  return evalBomContext(bomTemplate.value?.rows || [], ctx)
}

// ---- hydrate（父组件切 tab 重挂 / 编辑老报价单时回填）----
function hydrateFromPicks(p: any) {
  if (!p) return
  // 回填 rear
  if (p.rear) {
    for (const slot of Object.keys(rear)) {
      const v = p.rear[slot]
      if (Array.isArray(v)) rear[slot] = v.filter((t: string) => t !== 'blank')
      else if (typeof v === 'string' && v !== 'blank') rear[slot] = [v]
      else rear[slot] = []
    }
  }
  // 回填 overrides
  if (p.overrides) {
    for (const k of Object.keys(p.overrides)) overrides[k] = p.overrides[k]
  }
}

defineExpose({ hydrateFromPicks })

// ---- 选基准配置（D2 下拉）----
async function selectBaseConfig(id: number | null) {
  if (id == null) { baseConfig.value = null; emit('update:baseConfigId', null); return }
  await loadBaseConfig(id)
  emit('update:baseConfigId', id)
}

// ---- 变动 → emit（父组件写 store）----
let _emitTimer: any = null
function scheduleEmit() {
  if (_emitTimer) return
  _emitTimer = setTimeout(() => {
    _emitTimer = null
    emit('apply', {
      baseConfigId: baseConfig.value?.id ?? props.baseConfigId ?? null,
      totals: totals.value,
      picks: picks.value,
      l6Rows: buildL6Rows(),
      bomTemplate: bomTemplate.value ? { id: bomTemplate.value.id, name: bomTemplate.value.name, rows: bomTemplate.value.rows } : null,
      bomContext: buildBomContext(),
    })
  }, 50) // 合并连续变动（rear 累加等），避免高频 emit
}

watch([rear, overrides, baseConfig, result, bomTemplate], scheduleEmit, { deep: true })
watch(() => props.kpSummary, (s) => applyKpSummary(s), { deep: true })

onMounted(async () => {
  // 先 hydrate：必须在下方任何 await 之前。loadBaseConfig 会让 baseConfig 变化触发 watch → scheduleEmit，
  // 若 hydrate 在 await loadReference 之后，50ms timer 会在 hydrate 前到期，把组件空初始的 rear emit 出去覆盖 store，
  // 进而让 props.initialPicks 响应式变空，hydrate 读到空（配置丢失 bug）。
  if (props.initialPicks) hydrateFromPicks(props.initialPicks)
  try {
    await loadAllBaseConfigs()
    const seedId = props.initialPicks?.base_config_id ?? props.baseConfigId
    if (seedId) {
      await loadBaseConfig(seedId)
      await loadReference(baseConfig.value?.series)
    } else {
      await loadReference(undefined)
    }
    // baseBpType 由 watchEffect 跟踪 baseBackplaneType；hydrate 已在挂载伊始完成
    // 初次 derive（若有 kpSummary）
    if (props.kpSummary) applyKpSummary(props.kpSummary)
    scheduleEmit()
  } catch (e: any) {
    message.error('L6 配置加载失败：' + (e.message || e))
  }
})

// 组件卸载时清掉 pending 的 emit timer，避免卸载后残留 emit 把状态写进 store
onBeforeUnmount(() => {
  if (_emitTimer) {
    clearTimeout(_emitTimer)
    _emitTimer = null
  }
})
</script>

<template>
  <div class="l6-chassis-config" :class="{ stepper }">
    <div v-if="stepper" class="l6-steps">
      <div v-for="s in L6_STEPS" :key="s.id" :class="['l6-step', { active: activeStep === s.id }]" @click="activeStep = s.id">
        <span class="l6-step-num">{{ s.n }}</span>
        <span class="l6-step-label">{{ s.label }}</span>
      </div>
    </div>
    <div class="l6-panels">
    <!-- ① 基准配置 -->
    <div id="l6-panel-base" class="sc-panel" v-show="!stepper || activeStep === 'base'">
      <div class="sc-phead">
        <span class="num">1</span><h2>基准配置</h2>
        <span class="hint">背板由硬盘推导，可手改</span>
        <span class="amt">¥{{ baseTotal.toLocaleString() }}</span>
      </div>
      <div class="sc-pbody">
        <!-- 选择基准配置（D2）-->
        <div class="bc-picker">
          <label class="bc-lab">选择基准配置</label>
          <select class="sc-sel bc-sel" :value="baseConfig?.id ?? ''" @change="(e:any)=>selectBaseConfig(e.target.value ? Number(e.target.value) : null)">
            <option value="">(请选择)</option>
            <option v-for="c in allBaseConfigs" :key="c.id" :value="c.id">{{ c.name }} · {{ c.series }} · {{ c.form }} · {{ c.bays }}盘</option>
          </select>
        </div>
        <div v-if="baseConfig" class="sc-sumcard">
          <div class="si"><span class="k">基准</span><span class="v">{{ baseConfig.name }}</span></div>
          <div class="si"><span class="k">形态</span><span class="v">{{ baseConfig.form }}</span></div>
          <div class="si"><span class="k">盘位</span><span class="v">{{ baseConfig.bays }}</span></div>
          <div class="si"><span class="k">硬盘背板</span><span class="v derived">
            <span>{{ bpType() === 'tri' ? '三模' : '直连' }}</span>
            <span class="bp-btns"><button :class="{ on: bpType() === 'tri' }" @click="setOverride('bp', 'tri')">三模</button><button :class="{ on: bpType() === 'dc' }" @click="setOverride('bp', 'dc')">直连</button></span>
            <PartPicker v-if="bpTri.length > 1 || bpDc.length > 1" :items="(bpType()==='tri'?bpTri:bpDc).map(fromPartMaster)" :model-value="overrides.bpPn || effectiveBp?.pn || ''" size="small" placeholder="(选择背板)" :style="{ marginLeft: '6px', width: '180px', verticalAlign: 'middle' }" @update:model-value="(pn:any)=>setOverride('bpPn', typeof pn==='string'?pn:'')" />
            <span class="tiny">{{ effectiveBp ? (effectiveBp.name || effectiveBp.pn) + ' · ¥' + (effectiveBp.unit_price||0) + ' · ' + (isManual('bp') ? '已手改' : (baseBackplaneType ? '基准自带' : '硬盘推导')) : '料号库无此类型背板' }}</span>
          </span></div>
        </div>
        <div v-else class="sc-empty">请先选择基准配置</div>
      </div>
    </div>

    <!-- ② 前面板 -->
    <div id="l6-panel-front" class="sc-panel" v-show="!stepper || activeStep === 'front'">
      <div class="sc-phead"><span class="num">2</span><h2>前面板 · 硬盘背板连线</h2><span class="amt">¥{{ frontTotal.toLocaleString() }}</span></div>
      <div class="sc-pbody">
        <div class="front-grid">
          <div class="front-card" v-for="k in CORE_DRIVE_KINDS" :key="k" :class="{ active: frontCableQty(k) > 0 }">
            <div class="front-card-head">
              <span class="opt-dot"></span>
              <span class="front-card-name">{{ k }} 线缆</span>
              <span v-if="isManual('fc-' + k)" class="sc-badge man">已手动</span>
            </div>
            <div class="front-card-info">
              当前 {{ frontCableInfo(k).n }} 块 · 每组 {{ frontCableInfo(k).group }} · ¥{{ frontCableInfo(k).price }}/根
              <span class="front-card-pn" v-if="frontCableInfo(k).name">{{ frontCableInfo(k).name }}</span>
            </div>
            <PartPicker v-if="frontCableParts(k).length" :items="frontCableParts(k).map(fromPartMaster)" :model-value="frontCablePickedPn(k)" size="small" placeholder="(选择线缆)" class="front-card-pick" @update:model-value="(pn:any)=>setOverride('fc-'+k+'-pn', typeof pn==='string'?pn:'')" />
            <div v-else class="front-card-empty">料号库暂无 {{ k }} 线缆</div>
            <div class="front-card-step">
              <div class="sc-step"><button @click="setOverride('fc-' + k, Math.max(0, frontCableQty(k) - 1))">−</button><input :value="frontCableQty(k)" @change="(e:any)=>setOverride('fc-' + k, parseInt(e.target.value)||0)" /><button @click="setOverride('fc-' + k, frontCableQty(k) + 1)">+</button></div>
              <span class="u">根</span>
            </div>
          </div>
        </div>
        <div v-if="!frontCables.length" class="sc-empty">料号库暂无「前面板线缆」类别料号，请去管理面添加。</div>
      </div>
    </div>

    <!-- ③ 后面板（PCIe IO + 网络 OCP + GPU 供电线）-->
    <div id="l6-panel-rear" class="sc-panel" v-show="!stepper || activeStep === 'rear'">
      <div class="sc-phead"><span class="num">3</span><h2>后面板 · IO 与网络</h2><span class="hint">PCIe IO 槽位 + OCP 网络接口 + GPU 供电线</span><span class="amt">¥{{ (rearTotal + ocpTotal + gpuCableCost).toLocaleString() }}</span></div>
      <div class="sc-pbody">
        <div class="sc-section-head"><span class="sh-tag">PCIe IO 槽位</span><span class="sh-amt">¥{{ rearTotal.toLocaleString() }}</span></div>
        <div class="rear-grid" :style="{ gridTemplateColumns: `repeat(${ioSlots.length}, minmax(0,1fr))` }">
          <div class="slot-col" v-for="slot in ioSlots" :key="slot">
            <div class="slot-col-head">
              <span class="slot-name">{{ slot }}</span>
              <span class="slot-cap-mini" v-if="(SLOT_CAP[slot]||0) > 1">{{ slotFilled(slot) }}/{{ SLOT_CAP[slot] }}</span>
              <span class="slot-cap-mini" v-else>单卡</span>
            </div>
            <div class="opt-block" v-for="opt in realOptions(slot)" :key="opt.option_type" :class="{ active: optionQty(slot, opt.option_type) > 0 }">
              <div class="opt-top"><span class="opt-dot"></span><span class="opt-name">{{ optionLabel(opt.option_type) }}</span></div>
              <div class="opt-bundle" v-if="opt.items?.length">
                <span v-if="opt.items.length === 1" class="opt-bundle-pn">{{ opt.items[0].name || opt.items[0].pn }}</span>
                <a-tooltip v-else overlay-class-name="bundle-tip">
                  <template #title>
                    <div class="bundle-tip-title">{{ optionLabel(opt.option_type) }} · {{ opt.items.length }} 件捆绑（每件单价）</div>
                    <div v-for="it in opt.items" :key="it.pn" class="bundle-tip-row">
                      <span class="bt-name">{{ it.name || it.pn }}</span>
                      <span class="bt-price">¥{{ it.unit_price }}</span>
                    </div>
                    <div class="bundle-tip-sum">合计 ¥{{ opt.total_price.toLocaleString() }} / 件</div>
                  </template>
                  <span class="opt-bundle-multi">⭐ {{ opt.items.length }} 件捆绑</span>
                </a-tooltip>
              </div>
              <div class="opt-bot">
                <span class="opt-price">¥{{ opt.total_price.toLocaleString() }}<span class="opt-price-unit" v-if="opt.items?.length > 1">/件</span></span>
                <div class="opt-stepper">
                  <button :disabled="optionQty(slot, opt.option_type) <= 0" @click="decOption(slot, opt.option_type)">−</button>
                  <span class="opt-qty">{{ optionQty(slot, opt.option_type) }}</span>
                  <button :disabled="!canInc(slot)" @click="incOption(slot, opt.option_type, SLOT_CAP[slot])">＋</button>
                </div>
              </div>
            </div>
            <div class="slot-blank" v-if="realOptions(slot).length === 0"><span class="blank-tag">挡片</span></div>
            <div class="slot-blank" v-else-if="slotFilled(slot) === 0"><span class="blank-tag">挡片</span></div>
          </div>
        </div>

        <div class="sc-section-head sc-section-head-gap" v-if="hasOcp"><span class="sh-tag">网络 · OCP 网卡</span><span class="sh-note">OCP 走独立接口，不占 PCIe 槽位</span><span class="sh-amt">¥{{ ocpTotal.toLocaleString() }}</span></div>
        <div class="net-options" v-if="hasOcp">
          <button v-for="opt in realOptions('OCP')" :key="opt.option_type" :class="['net-card', { active: optionQty('OCP', opt.option_type) > 0 }]" @click="setRearSingle('OCP', opt.option_type)">
            <span class="net-name">{{ optionLabel(opt.option_type) }}</span>
            <span class="net-pn" v-if="opt.items?.length === 1">{{ opt.items[0].name || opt.items[0].pn }}</span>
            <span class="net-price">¥{{ opt.total_price.toLocaleString() }}</span>
          </button>
          <button :class="['net-card', 'blank', { active: slotFilled('OCP') === 0 }]" @click="setRearSingle('OCP', null)">
            <span class="net-name">不装（挡片）</span><span class="net-price">¥0</span>
          </button>
        </div>

        <div class="sc-section-head sc-section-head-gap"><span class="sh-tag">GPU 供电线</span><span class="sh-amt">¥{{ gpuCableCost.toLocaleString() }}</span></div>
        <div class="sc-dline gpu-cable-line" v-if="gpuCableParts.length">
          <div>
            <div class="dl-t">GPU 供电线<span :class="['sc-badge', isManual('gpuCableQty') ? 'man' : 'sys']">{{ gpuArch === 'none' ? '无 GPU' : (isManual('gpuCableQty') ? '手动' : '推导') }}</span></div>
            <div class="dl-b">{{ gpuCablePicked()?.name ? gpuCablePicked()!.name + ' · ' : '' }}单价 ¥{{ gpuCableUnitPrice() }}/根</div>
          </div>
          <div class="dl-r">
            <PartPicker :items="gpuCableParts.map(fromPartMaster)" :model-value="overrides.gpuCablePn || ''" size="small" placeholder="(选择线缆)" :style="{ width: '200px' }" @update:model-value="(pn:any)=>setOverride('gpuCablePn', typeof pn==='string'?pn:'')" />
            <div class="sc-step"><button @click="setOverride('gpuCableQty', Math.max(0, gpuCableQty() - 1))">−</button><input :value="gpuCableQty()" @change="(e:any)=>setOverride('gpuCableQty', parseInt(e.target.value)||0)" /><button @click="setOverride('gpuCableQty', gpuCableQty() + 1)">+</button></div>
            <span class="u">根</span>
          </div>
        </div>
        <div v-else class="sc-empty">料号库暂无「GPU电源线」类别料号。</div>
      </div>
    </div>

    <!-- ④ 电源 -->
    <div id="l6-panel-psu" class="sc-panel" v-show="!stepper || activeStep === 'psu'">
      <div class="sc-phead"><span class="num">4</span><h2>电源 PSU</h2><span class="hint">自选型号与数量；功耗推导仅供参考</span><span class="amt">¥{{ psuLineTotal.toLocaleString() }}</span></div>
      <div class="sc-pbody">
        <div class="power-breakdown" v-if="result?.power?.total">
          <div class="pb-item"><span class="pb-label">基础功耗</span><span class="pb-val">{{ result.power.base }}W</span></div>
          <div class="pb-item"><span class="pb-label">CPU 功耗</span><span class="pb-val">+ {{ result.power.cpu }}W</span></div>
          <div class="pb-item"><span class="pb-label">GPU 功耗</span><span class="pb-val">+ {{ result.power.gpu }}W</span></div>
          <div class="pb-item total"><span class="pb-label">整机峰值（参考）</span><span class="pb-val">{{ result.power.total }}W</span></div>
        </div>
        <div class="psu-empty-hint" v-else>功耗数据未维护，下方请直接从料号库选 PSU。</div>
        <div class="psu-row" v-if="psuParts.length">
          <label class="psu-lab">PSU 型号</label>
          <PartPicker :items="psuParts.map(fromPartMaster)" :model-value="overrides.psuPn || ''" size="small" placeholder="(选择 PSU)" @update:model-value="(pn:any)=>setOverride('psuPn', typeof pn==='string'?pn:'')" />
          <span class="psu-unit-price">单价 ¥{{ psuUnitPrice().toLocaleString() }}</span>
          <div class="sc-step psu-step"><button @click="setOverride('psuQty', Math.max(0, psuQty() - 1))">−</button><input :value="psuQty()" @change="(e:any)=>setOverride('psuQty', parseInt(e.target.value)||0)" /><button @click="setOverride('psuQty', psuQty() + 1)">+</button></div>
          <span class="psu-subtotal">¥{{ psuLineTotal.toLocaleString() }}</span>
        </div>
        <div v-else class="sc-empty">料号库暂无「电源」类别 PSU。</div>
      </div>
    </div>

    <!-- L6 合计 -->
    <div class="l6-total-bar cpq-stream-edge">
      <span>L6 机箱合计 <b>¥<CountNumber :value="l6Total" /></b></span>
      <span class="l6-total-hint">基准 + 前面板 + 后面板 + OCP + 电源 + GPU线</span>
    </div>
    </div>
  </div>
</template>

<style scoped>
.l6-chassis-config { display: flex; flex-direction: column; }
.l6-chassis-config.stepper { flex-direction: row; align-items: flex-start; gap: 16px; }
.l6-steps { flex: 0 0 150px; display: flex; flex-direction: column; gap: 8px; padding: 12px;
  background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w10); border-radius: 14px; position: sticky; top: 12px; }
.l6-step { display: flex; align-items: center; gap: 9px; padding: 9px 11px; border-radius: 9px; cursor: pointer; transition: all .2s;
  border: 1px solid transparent; }
.l6-step:hover { background: var(--cpq-overlay-a8); }
.l6-step.active { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary,#1677FF); box-shadow: 0 0 12px var(--cpq-overlay-a8); }
.l6-step-num { width: 22px; height: 22px; border-radius: 6px; background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF);
  display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.l6-step.active .l6-step-num { background: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-on-primary); }
.l6-step-label { font-size: 13px; color: var(--cpq-text-secondary,#9BA1AA); font-weight: 500; }
.l6-step.active .l6-step-label { color: var(--cpq-accent-primary,#1677FF); font-weight: 600; }
.l6-panels { display: flex; flex-direction: column; gap: 14px; flex: 1; min-width: 0; }
.sc-panel {
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); border-radius: 18px; overflow: hidden;
  box-shadow: 0 22px 64px var(--cpq-shadow-color-strong), 0 0 34px var(--cpq-overlay-a4), inset 0 1px 0 var(--cpq-overlay-w15), inset 0 -18px 48px var(--cpq-shadow-color-soft);
}
.sc-phead { display: flex; align-items: center; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w4); }
.sc-phead .num { width: 26px; height: 26px; border-radius: 7px; background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
.sc-phead h2 { font-size: 16px; font-weight: 600; margin: 0; color: var(--cpq-text-primary, #E8ECEF); }
.sc-phead .hint { color: var(--cpq-text-muted,#6E7582); font-size: 12px; }
.sc-phead .amt { margin-left: auto; color: var(--cpq-accent-primary,#1677FF); font-weight: 700; font-size: 14px; }
.sc-pbody { padding: 18px 20px; }
.sc-sumcard { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; padding: 14px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; }
.sc-sumcard .k { display: block; font-size: 12px; color: var(--cpq-text-muted,#6E7582); margin-bottom: 3px; }
.sc-sumcard .v { font-weight: 600; font-size: 14px; color: var(--cpq-text-primary, #E8ECEF); }
.sc-sumcard .v.derived { color: var(--cpq-accent-primary,#1677FF); }
.bp-btns { display: inline-flex; gap: 4px; margin-left: 6px; }
.bp-btns button { padding: 2px 9px; border: 1px solid var(--cpq-overlay-w10); background: transparent; color: var(--cpq-text-secondary,#9BA1AA); border-radius: 6px; font-size: 12px; cursor: pointer; transition: all .2s; }
.bp-btns button.on { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); }
.bp-sel { margin-left: 6px; background: var(--cpq-overlay-b20); color: var(--cpq-text-primary,#E8ECEF); border: 1px solid var(--cpq-overlay-w10); border-radius: 6px; padding: 2px 6px; font-size: 12px; outline: none; }
.tiny { display: block; font-size: 12px; color: var(--cpq-text-muted,#6E7582); margin-top: 3px; }
.bc-picker { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.bc-lab { font-size: 13px; color: var(--cpq-text-secondary,#9BA1AA); white-space: nowrap; }
.bc-sel { flex: 1; }
.sc-sel { background: var(--cpq-overlay-b20); color: var(--cpq-text-primary,#E8ECEF); border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; padding: 8px; font-size: 13px; outline: none; transition: all .2s; appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%231677FF' d='M6 8L1 3h10z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 8px center; padding-right: 28px; }
.sc-sel option { background: var(--cpq-bg-tertiary); color: var(--cpq-text-primary,#E8ECEF); padding: 8px; }
.sc-sel:focus { border-color: var(--cpq-accent-primary,#1677FF); box-shadow: 0 0 0 2px var(--cpq-overlay-a15); }
.sc-step { display: flex; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; overflow: hidden; }
.sc-step button { width: 30px; color: var(--cpq-text-secondary,#9BA1AA); font-size: 14px; background: transparent; border: none; cursor: pointer; transition: all .2s; }
.sc-step button:hover { color: var(--cpq-accent-primary,#1677FF); }
.sc-step input { width: 100%; min-width: 0; text-align: center; border: none; background: transparent; color: var(--cpq-text-primary,#E8ECEF); font-size: 13px; outline: none; }
.sc-dline { display: flex; justify-content: space-between; align-items: center; padding: 11px 14px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; margin-bottom: 9px; }
.dl-t { font-weight: 500; font-size: 13px; color: var(--cpq-text-primary, #E8ECEF); }
.dl-b { font-size: 12px; color: var(--cpq-text-muted,#6E7582); margin-top: 2px; }
.dl-r { display: flex; align-items: center; gap: 7px; }
.u { color: var(--cpq-text-muted,#6E7582); font-size: 12px; }
.sc-badge { font-size: 12px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
.sc-badge.sys { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF); }
.sc-badge.man { background: rgba(250,140,22,.14); color: #fa8c16; }
.fc-sel { width: 200px; }
.gc-sel { width: 200px; }
.sc-empty { color: var(--cpq-text-muted,#6E7582); text-align: center; padding: 20px; font-size: 13px; }
.front-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.front-card { display: flex; flex-direction: column; gap: 9px; padding: 14px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; min-width: 0; transition: all .2s; }
.front-card.active { border-color: var(--cpq-overlay-a40); background: var(--cpq-overlay-a8); box-shadow: 0 0 12px var(--cpq-overlay-a8); }
.front-card-head { display: flex; align-items: center; gap: 7px; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.front-card-name { font-size: 14px; font-weight: 700; color: var(--cpq-text-primary,#E8ECEF); }
.front-card.active .opt-dot { background: var(--cpq-accent-primary,#1677FF); border-color: var(--cpq-accent-primary,#1677FF); box-shadow: 0 0 8px var(--cpq-overlay-a40); }
.front-card-info { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.front-card-pn { display: block; color: var(--cpq-text-secondary,#9BA1AA); margin-top: 2px; }
.front-card-pick { width: 100%; }
.front-card-pick :deep(.ant-select) { width: 100% !important; }
.front-card-empty { font-size: 12px; color: var(--cpq-text-muted,#6E7582); padding: 9px 10px; background: var(--cpq-overlay-w3); border: 1px dashed var(--cpq-overlay-w10); border-radius: 8px; text-align: center; }
.front-card-step { display: flex; align-items: center; gap: 7px; margin-top: auto; }
.front-card-step .sc-step { flex: 1; }
.rear-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.slot-col { display: flex; flex-direction: column; padding: 12px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; min-width: 0; }
.slot-col-head { display: flex; align-items: baseline; gap: 6px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.slot-col-head .slot-name { font-weight: 700; font-size: 14px; color: var(--cpq-text-primary,#E8ECEF); }
.slot-cap-mini { font-size: 11px; color: var(--cpq-text-muted,#6E7582); margin-left: auto; }
.opt-block { padding: 8px; border: 1px solid var(--cpq-overlay-w8); border-radius: 8px; margin-bottom: 8px; background: var(--cpq-overlay-w4); transition: all .2s; }
.opt-block.active { border-color: var(--cpq-overlay-a40); background: var(--cpq-overlay-a8); box-shadow: 0 0 12px var(--cpq-overlay-a8); }
.opt-top { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.opt-dot { width: 8px; height: 8px; border-radius: 50%; border: 1px solid var(--cpq-text-muted,#6E7582); flex-shrink: 0; transition: all .2s; }
.opt-block.active .opt-dot { background: var(--cpq-accent-primary,#1677FF); border-color: var(--cpq-accent-primary,#1677FF); box-shadow: 0 0 8px var(--cpq-overlay-a40); }
.opt-name { font-size: 12px; font-weight: 600; color: var(--cpq-text-secondary,#9BA1AA); }
.opt-block.active .opt-name { color: var(--cpq-text-primary,#E8ECEF); }
.opt-bot { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.opt-price { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.opt-price-unit { font-size: 10px; opacity: .7; margin-left: 1px; }
.opt-bundle { margin-bottom: 6px; min-height: 14px; }
.opt-bundle-pn { font-size: 10px; font-family: monospace; color: var(--cpq-text-muted,#6E7582); }
.opt-bundle-multi { font-size: 10px; color: var(--cpq-accent-primary,#1677FF); cursor: help; }
.net-pn { font-size: 10px; font-family: monospace; color: var(--cpq-text-muted,#6E7582); }
.opt-stepper { display: flex; align-items: center; background: var(--cpq-overlay-b30); border: 1px solid var(--cpq-overlay-w10); border-radius: 6px; overflow: hidden; }
.opt-stepper button { width: 22px; height: 22px; border: none; background: transparent; color: var(--cpq-text-secondary,#9BA1AA); font-size: 13px; cursor: pointer; transition: all .15s; padding: 0; }
.opt-stepper button:hover:not(:disabled) { color: var(--cpq-accent-primary,#1677FF); background: var(--cpq-overlay-a8); }
.opt-stepper button:disabled { opacity: .3; cursor: not-allowed; }
.opt-qty { min-width: 20px; text-align: center; font-size: 12px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); }
.slot-blank { padding: 10px 8px; text-align: center; }
.blank-tag { display: inline-block; font-size: 12px; color: var(--cpq-text-muted,#6E7582); background: var(--cpq-overlay-w4); border: 1px dashed var(--cpq-overlay-w10); border-radius: 6px; padding: 3px 12px; }
.sc-section-head { display: flex; align-items: baseline; gap: 10px; margin: 4px 0 10px; }
.sc-section-head.sh-gap { margin-top: 18px; }
.sc-section-head .sh-tag { font-size: 13px; font-weight: 700; color: var(--cpq-text-primary,#E8ECEF); }
.sc-section-head .sh-note { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.sc-section-head .sh-amt { margin-left: auto; font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); }
.net-options { display: flex; flex-wrap: wrap; gap: 12px; }
.net-card { flex: 1; min-width: 150px; padding: 14px 16px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; color: var(--cpq-text-secondary,#9BA1AA); cursor: pointer; transition: all .25s; text-align: left; display: flex; flex-direction: column; gap: 6px; font-family: inherit; }
.net-card:hover { border-color: var(--cpq-overlay-w20); color: var(--cpq-text-primary,#E8ECEF); transform: translateY(-1px); }
.net-card.active { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); box-shadow: 0 0 16px var(--cpq-overlay-a20); }
.net-card.blank { flex: 0 0 auto; min-width: 150px; border-style: dashed; }
.net-name { font-size: 14px; font-weight: 600; }
.net-price { font-size: 12px; opacity: .75; }
.power-breakdown { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 12px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; margin-bottom: 12px; }
.pb-item { display: flex; flex-direction: column; gap: 4px; padding: 8px; background: var(--cpq-overlay-w3); border-radius: 8px; }
.pb-item.total { background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-a20); }
.pb-label { font-size: 12px; color: var(--cpq-text-muted,#6E7582); }
.pb-val { font-size: 14px; font-weight: 700; color: var(--cpq-text-primary,#E8ECEF); }
.pb-item.total .pb-val { color: var(--cpq-accent-primary,#1677FF); }
.psu-row { display: grid; grid-template-columns: 70px minmax(150px,1fr) 110px 110px 90px; gap: 9px; align-items: center; padding: 11px 14px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; margin-bottom: 9px; }
.psu-lab { font-size: 13px; font-weight: 500; color: var(--cpq-text-primary,#E8ECEF); }
.psu-sel { width: 100%; }
.psu-unit-price { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); }
.psu-step { width: auto; flex: 1; }
.psu-subtotal { font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); text-align: right; }
.psu-empty-hint { font-size: 12px; color: var(--cpq-text-muted,#6E7582); margin-bottom: 10px; padding: 9px 12px; background: rgba(250,140,22,.08); border: 1px solid rgba(250,140,22,.25); border-radius: 10px; }
.gpu-cable-line .dl-r { gap: 5px; }
.l6-total-bar { position: relative; display: flex; align-items: baseline; gap: 14px; padding: 12px 18px; border: 1px solid var(--cpq-glass-border-strong); border-radius: var(--cpq-radius-lg); background: var(--cpq-overlay-a8); backdrop-filter: blur(var(--cpq-glass-blur-1)); -webkit-backdrop-filter: blur(var(--cpq-glass-blur-1)); }
.l6-total-bar b { color: var(--cpq-accent-primary,#1677FF); font-size: 18px; }
.l6-total-hint { font-size: 11px; color: var(--cpq-text-muted,#6E7582); margin-left: auto; }
</style>

<!-- a-tooltip 渲染到 portal（scoped 之外），用全局样式 -->
<style>
.bundle-tip { max-width: 340px; }
.bundle-tip .ant-tooltip-inner { padding: 10px 12px; }
.bundle-tip-title { font-weight: 600; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,.18); font-size: 12px; }
.bundle-tip-row { display: flex; gap: 8px; align-items: baseline; font-size: 12px; line-height: 1.7; }
.bundle-tip-row .bt-name { flex: 1; color: rgba(255,255,255,.72); }
.bundle-tip-row .bt-price { margin-left: auto; }
.bundle-tip-sum { margin-top: 5px; padding-top: 4px; border-top: 1px solid rgba(255,255,255,.18); font-weight: 600; font-size: 12px; }
</style>
