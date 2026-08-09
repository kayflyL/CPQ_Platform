<script setup lang="ts">
/**
 * L6 机箱选配（共用组件）— 服务器配置页(ConfigWizard) 与 报价工作台(Workspace) 共用。
 * 4 个面板：①基准配置（含「选择基准配置」下拉）②前面板 ③后面板(PCIe IO + OCP + GPU 线) ④电源。
 *
 * 内部用 useServerConfig() 管 rear/overrides/baseBpType；kpSummary prop 合成进 kpLines+gpuArch。
 * 选配变动 → emit `apply`（含 totals/picks/l6Rows）+ `update:baseConfigId`。
 * 父组件切 tab 重挂时由 onMounted 读 initialPicks 自 hydrate。
 *
 * 遵循：[[ocp-is-networking-not-pcie]]（OCP 独立网络分段）/ [[derive-must-have-manual-fallback]]（推导仅兜底，料号库手选）
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, watchEffect } from 'vue'
import { message } from 'ant-design-vue'
import {
  baseConfigApi, partsApi, rearIOApi, bomTemplateApi,
  type PartMaster, type BaseConfig, type RearSlot, type RearIOSlotOption, type BomTemplate,
} from '@/api/serverConfig'
import { useServerConfig, type GpuArch } from '@/composables/useServerConfig'
import { useSelectionRulesStore, type RuleContext, type RuleAction } from '@/stores/selectionRules'
import { evalBomContext, type BomEvalContext } from '@/utils/bomRuleEngine'
import { cableDescFrom } from '@/utils/bomL6Derive'
import { CORE_DRIVE_KINDS, DEFAULT_REAR_SLOTS, DEFAULT_PSU_BAYS, COMBO_REAR_SLOTS, optionLabel, rearIOBucket } from '@/constants/chassisMeta'
import { backplaneTypeOf, driveKindOf } from '@/utils/partFit'
import PartPicker from '@/components/common/PartPicker.vue'
import RearPanel from '@/components/server-config/RearPanel.vue'
import CountNumber from '@/components/common/CountNumber.vue'
import { fromPartMaster } from '@/composables/usePartAdapter'

const props = defineProps<{
  baseConfigId?: number | null
  kpSummary?: {
    cpuPn?: string; cpuQty?: number
    gpuPn?: string; gpuQty?: number
    gpuArch?: GpuArch
    drivesByKind?: Record<string, number> // {SATA, SAS, NVMe}
    highBwNic?: boolean                    // 含 100G+ 高带宽网卡（x16 卡）→ IO1 riser 升级 x16
  }
  initialPicks?: any
  /** 弹窗模式：左侧步骤条 + 右侧单步内容（堆叠模式为 false，Workspace 行为不变） */
  stepper?: boolean
  /** 是否显示 GPU 供电线选择行：报价页 GPU 线外移到 GPU 卡→传 false 隐藏；配置页默认 true 保留 */
  showGpuCable?: boolean
}>()

const emit = defineEmits<{
  (e: 'apply', payload: {
    baseConfigId: number | null
    totals: any
    picks: any
    l6Rows: any[]
    bomTemplate: BomTemplate | null
    bomContext: Record<string, { desc: string; qty: number | string }>
  }): void
  (e: 'update:baseConfigId', id: number | null): void
}>()

const {
  kpLines, gpuArch, rear, overrides, baseBpType, derivedBpType, derivedCableQty, basePsuBays,
  frontCableQty, psuQty, bpType, isManual, setOverride,
  optionQty, uniqueRealOptions,
} = useServerConfig()

const selectionRulesStore = useSelectionRulesStore()
// CRE 规则求值上下文：盘类型/各类盘数 + GPU 数量，全部取自 kpSummary（随工作台 KP 增删/换型反应式重算）
const ruleCtx = computed<RuleContext>(() => {
  const d = props.kpSummary?.drivesByKind || {}
  return {
    kp: { GPU: { qty: props.kpSummary?.gpuQty || 0, items: [], spec: {} } },
    config: {
      drive_kinds: (Object.keys(d) as string[]).filter(k => (d as Record<string, number>)[k] > 0),
      sata_qty: d.SATA || 0, sas_qty: d.SAS || 0, nvme_qty: d.NVMe || 0,
    },
    opportunity: {},
  }
})
// CRE 背板规则：盘类型 → 背板类型(tri/dc)，声明式可配、改即生效；注入 useServerConfig.derivedBpType
const ruleBpType = computed<'tri' | 'dc' | null>(() =>
  ((selectionRulesStore.assignValue('config.bp_type', ruleCtx.value) as 'tri' | 'dc') ?? null))
watch(ruleBpType, v => { derivedBpType.value = v }, { immediate: true })
// CRE 线缆规则：跑 derive 算术规则，按线缆类型(SATA/SAS/NVMe/GPU线)收成动作；数量注入 useServerConfig.derivedCableQty
const cableActions = computed<Record<string, RuleAction>>(() => {
  const out: Record<string, RuleAction> = {}
  for (const a of selectionRulesStore.evaluateRules(ruleCtx.value)) {
    if (a.action === 'derive' && a.deriveTarget) out[a.deriveTarget] = a
  }
  return out
})
watch(cableActions, m => {
  derivedCableQty.value = Object.fromEntries(Object.entries(m).map(([k, a]) => [k, a.deriveQty ?? 0]))
}, { immediate: true })
void selectionRulesStore.ensureRules()

const allBaseConfigs = ref<BaseConfig[]>([])          // 「选择基准配置」下拉数据
const baseConfig = ref<(BaseConfig & { parts: any[] }) | null>(null)
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

// 槽位布局/容量来自 base_config 能力档案（RearSlot[]），缺数据兜底 chassisMeta.DEFAULT_REAR_SLOTS；
// 盘类型/选项标签也从 chassisMeta 取——无散落硬编码（[[systematic-cleanup-not-whackamole]]）
const rearSlotDefs = computed<RearSlot[]>(() => {
  const rs = baseConfig.value?.rear_slots
  return rs && rs.length ? rs : DEFAULT_REAR_SLOTS
})
const rearSlots = computed(() => rearSlotDefs.value.map(s => s.name))
const ioSlots = computed(() => rearSlots.value.filter((s: string) => s !== 'OCP'))   // buildPlanCfg 明细用（槽名）
const hasOcp = computed(() => rearSlots.value.includes('OCP'))

// RearPanel 视图：rear_slot 定义 + reactive rear 数组（defaults 即 rear[name]，RearPanel 就地改 → 回流 rear）
const rearSlotsView = computed<RearSlot[]>(() =>
  rearSlotDefs.value.filter(s => s.name !== 'OCP').map(s => ({ name: s.name, cap: s.cap, defaults: rear[s.name] }))
)
const ocpSlotView = computed<RearSlot | null>(() => {
  const o = rearSlotDefs.value.find(s => s.name === 'OCP')
  return o ? { name: 'OCP', cap: o.cap, defaults: rear['OCP'] } : null
})
// 配置页展示的后面板选项 = 按基准配置选中的料号(PN)过滤：只留基准选中的类型卡、卡内只留选中的料号。
// 旧基准无 defaults → 返回全目录（自由选，向后兼容）。这让「显示哪个料」受基准配置管理，不再系统按属性自动列。
const rearOptionsLocked = computed<Record<string, RearIOSlotOption[]>>(() => {
  const defs = baseConfig.value?.rear_slots || []
  if (!defs.some(s => ((s as any).defaults || []).length)) return rearOptions.value
  const out: Record<string, RearIOSlotOption[]> = {}
  for (const [slot, opts] of Object.entries(rearOptions.value)) {
    const slotDef = defs.find(s => s.name === slot)
    const pns = new Set<string>(((slotDef as any)?.defaults || []) as string[])
    if (!pns.size) { out[slot] = opts; continue }   // 该槽基准未选料 → 自由
    out[slot] = (opts || [])
      .filter(o => (o.items || []).some(it => pns.has(it.pn)))                       // 只留基准选中的类型卡
      .map(o => {
        const items = (o.items || []).filter(it => pns.has(it.pn))                    // 卡内只留选中的料号
        return { ...o, items, total_price: items.reduce((s, it) => s + (it.unit_price || 0), 0) }
      })
  }
  return out
})
// 保证 reactive rear 覆盖所有基准槽位名（RearPanel 就地改 defaults=rear[name]，键需存在才回流）
watchEffect(() => {
  for (const s of rearSlotDefs.value) {
    if (!rear[s.name]) rear[s.name] = []
  }
})

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
    // 高速存储信号线·前面板 = 前面板线缆；电源分配线缆·后面板 = GPU 供电线来源（见下方 gpuCables 过滤）
    partsApi.list({ category: '高速存储信号线', major_category: '前面板' }),
    partsApi.list({ category: '电源分配线缆', major_category: '后面板' }),
    // rear-IO 选项按系列分桶（chassisMeta.rearIOBucket：SERIES_REAR_IO_BUCKET 可配，未配置走默认桶）
    rearIOApi.getOptions(rearIOBucket(series)),
    partsApi.list({ category: '电源模块' }),
    partsApi.list({ category: '前置硬盘背板' }),
  ])
  // 电源分配线缆·后面板 含 GPU 供电线 + 后背板电源线，仅保留 GPU 供电线（PN/name 含 GPU）
  const gpuCables = gpuCableRes.parts.filter((p: any) => /gpu/i.test(p.pn) || /gpu/i.test(p.name || ''))
  frontCables.value = fcRes.parts
  gpuCableParts.value = gpuCables
  rearOptions.value = (rearRes as any).slots || {}
  psuParts.value = psuPartsRes.parts
  bpParts.value = bpRes.parts
  _refCache.set(key, {
    frontCables: fcRes.parts, gpuCableParts: gpuCables,
    psuParts: psuPartsRes.parts, bpParts: bpRes.parts,
    rearOptions: (rearRes as any).slots || {},
  })
}

/** 基准 defaults 是 PN 料号列表；按目录把它算成去重 option_type（配置页按类型卡调数量，多料捆绑=一个类型） */
function pnsToTypes(slot: string, pns: string[] | undefined): string[] {
  const opts = rearOptions.value[slot] || []
  const types: string[] = []
  for (const pn of (pns || [])) {
    const o = opts.find(opt => (opt.items || []).some(it => it.pn === pn))
    if (o && o.option_type !== 'blank' && !types.includes(o.option_type)) types.push(o.option_type)
  }
  return types
}

/** 用基准配置 rear_slots[].defaults（PN 列表）播种 rear（料自动填好，按类型卡填数量=1）。
 *  force=true 覆盖现有（切基准机箱时刷新默认）；false 只填空槽（保留 hydrate 回填的报价单 rear）。 */
function seedRearFromDefaults(force: boolean) {
  const defs = baseConfig.value?.rear_slots || []
  for (const s of defs) {
    const types = pnsToTypes(s.name, (s as any).defaults)
    if (force || !rear[s.name] || rear[s.name].length === 0) rear[s.name] = types
  }
}

async function loadBaseConfig(id: number, reseed: boolean = false) {
  try {
    baseConfig.value = await baseConfigApi.get(id)
    // 电源槽位数走 base_config 能力档案（psu_bays），缺省 chassisMeta.DEFAULT_PSU_BAYS
    basePsuBays.value = baseConfig.value?.psu_bays ?? DEFAULT_PSU_BAYS
    // baseBpType 由下方 watchEffect 跟踪 baseBackplaneType（须在 baseBackplaneType 声明之后注册）
    // 用基准 defaults 播种后面板（料自动填好）：reseed=false 保留 hydrate 回填，true 切机箱时刷新
    seedRearFromDefaults(reseed)
    // 加载该机型族的左栏 BOM 行骨架模板
    try {
      bomTemplate.value = await bomTemplateApi.getForBaseConfig(id)
    } catch (e: any) {
      bomTemplate.value = null
    }
  } catch (e: any) {
    baseConfig.value = null
    bomTemplate.value = null
    basePsuBays.value = DEFAULT_PSU_BAYS
  }
}

// ---- 背板（从料号库，三模/直连）----
const bpTri = computed(() => bpParts.value.filter(p => backplaneTypeOf(p) === 'tri'))
const bpDc = computed(() => bpParts.value.filter(p => backplaneTypeOf(p) === 'dc'))
const baseBackplane = computed(() => {
  const parts = baseConfig.value?.parts || []
  const inParts = parts.find((p: any) => p.category === '前置硬盘背板')
  if (inParts) return inParts
  const triPn = (baseConfig.value as any)?.bp_tri_pn
  const dcPn = (baseConfig.value as any)?.bp_dc_pn
  const pn = triPn || dcPn
  return pn ? bpParts.value.find(p => p.pn === pn) : null
})
const baseBackplaneType = computed<'tri' | 'dc' | null>(() => {
  // specs.bt 优先，缺失按 chassisMeta 关键词嗅探；都判不出时，有背板默认 dc（与历史行为一致）
  const t = backplaneTypeOf(baseBackplane.value)
  return t ?? (baseBackplane.value ? 'dc' : null)
})
const effectiveBp = computed(() => {
  if (overrides.bpPn) {
    const hit = bpParts.value.find(p => p.pn === overrides.bpPn)
    if (hit) return hit
  }
  // 未加载基准配置时不自动选背板（避免 Workspace 无机型时空配置凭空出现背板行）
  if (!baseConfig.value) return null
  const t = bpType()
  if (!t) return null  // 用户选择不选背板
  if (baseBackplane.value && baseBackplaneType.value === t) return baseBackplane.value
  const list = t === 'tri' ? bpTri.value : bpDc.value
  return list[0] || null
})
const effectiveBaseParts = computed(() => {
  const parts = [...(baseConfig.value?.parts || [])]
  const bp = effectiveBp.value
  if (bp) {
    const bpLine = { pn: bp.pn, name: bp.name, category: '前置硬盘背板', unit_price: bp.unit_price, quantity: 1 }
    const idx = parts.findIndex((p: any) => p.category === '前置硬盘背板')
    if (idx >= 0) parts[idx] = bpLine as any
    else parts.push(bpLine as any)
  }
  return parts
})

// ---- 前面板线缆 ----
function frontCableParts(k: string) {
  return frontCables.value.filter(p => driveKindOf(p) === k)
}
/** 基准配置为该盘类选的默认线缆（机箱定义，配置页锁死不能换；空=未配，取料号库首件兜底） */
function baseFrontCable(k: string): string {
  return (baseConfig.value as any)?.config_content?.front_cables?.[k] || ''
}
function frontCablePickedPn(k: string) {
  // 锁死：基准选了线缆就用基准的（机箱定义，配置页不能换料，只跟盘数调数量）；未配 → 手改(旧报价单) → 料号库首件
  const base = baseFrontCable(k)
  if (base) return base
  return overrides['fc-' + k + '-pn'] || frontCableParts(k)[0]?.pn || ''
}
function frontCableInfo(k: string): { pn: string; n: number; group: number | '-'; price: number; name: string } {
  // 盘数取 kpSummary.drivesByKind；"每组"读 CRE 规则的 derivePer（改规则即同步，无死数）
  const p = frontCables.value.find(x => x.pn === frontCablePickedPn(k))
  return {
    n: props.kpSummary?.drivesByKind?.[k] ?? 0,
    group: cableActions.value[k]?.derivePer ?? '-',
    price: p?.unit_price ?? 0, pn: p?.pn || '',
    name: p?.name || '',
  }
}

// ---- 后面板 ----
function slotPrice(slot: string): number {
  const opts = rearOptionsLocked.value[slot] || []
  return (rear[slot] || []).reduce((s, t) => s + (t === 'blank' ? 0 : (opts.find(o => o.option_type === t)?.total_price || 0)), 0)
}

// ---- PSU / GPU 线（料号库手选，推导仅兜底）----
/** 有效 PSU 料号：手改 overrides 优先 → 基准配置默认(default_psu_pn) → 空（软默认，配置页可改） */
function effectivePsuPn(): string {
  return overrides.psuPn || (baseConfig.value as any)?.config_content?.default_psu_pn || ''
}
function psuPicked(): PartMaster | null {
  const pn = effectivePsuPn()
  if (!pn) return null
  return psuParts.value.find(p => p.pn === pn) || null
}
function psuName(): string { return psuPicked()?.name || '' }
function psuUnitPrice(): number {
  return psuPicked()?.unit_price || 0
}
function gpuCablePicked(): PartMaster | null {
  if (!overrides.gpuCablePn) return null
  return gpuCableParts.value.find(p => p.pn === overrides.gpuCablePn) || null
}
function gpuCableQty(): number {
  if (overrides.gpuCableQty != null) return Number(overrides.gpuCableQty) || 0
  return derivedCableQty.value['GPU线'] || 0
}
function gpuCableUnitPrice(): number { return gpuCablePicked()?.unit_price || 0 }

// ---- 合计 ----
const baseTotal = computed(() => effectiveBaseParts.value.reduce((s, p) => s + (p.unit_price || 0) * (p.quantity || 1), 0))
const frontTotal = computed(() => CORE_DRIVE_KINDS.reduce((s, k) => s + frontCableQty(k) * frontCableInfo(k).price, 0))
const rearTotal = computed(() => ioSlots.value.reduce((sum: number, slot: string) => sum + slotPrice(slot), 0))
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
// 字段语义：L6 行 catalogue=零件名（旧 part_name），description=规格/PN（旧 spec），part_category 恒空
function buildL6Rows() {
  const rows: any[] = []
  for (const p of effectiveBaseParts.value) {
    rows.push({ category: 'L6', catalogue: p.name || p.pn, description: p.pn, part_category: '', qty: p.quantity || 1, base_price: p.unit_price || 0, currency: 'RMB' })
  }
  for (const k of CORE_DRIVE_KINDS) {
    const qty = frontCableQty(k); const info = frontCableInfo(k)
    if (qty > 0) rows.push({ category: 'L6', catalogue: `前面板${k}线缆`, description: info.pn, part_category: '', qty, base_price: info.price, currency: 'RMB' })
  }
  for (const slot of [...ioSlots.value, ...(hasOcp.value ? ['OCP'] : [])]) {
    for (const t of uniqueRealOptions(slot)) {
      const q = optionQty(slot, t)
      const opt = (rearOptions.value[slot] || []).find(o => o.option_type === t)
      const unit = opt?.total_price || 0
      if (q > 0) rows.push({ category: 'L6', catalogue: `后面板${slot}:${optionLabel(t)}`, description: '', part_category: '', qty: q, base_price: unit, currency: 'RMB' })
    }
  }
  if (psuQty() > 0 && psuUnitPrice() > 0) rows.push({ category: 'L6', catalogue: `电源:${psuName()}`, description: '', part_category: '', qty: psuQty(), base_price: psuUnitPrice(), currency: 'RMB' })
  if (gpuCableQty() > 0 && gpuCableUnitPrice() > 0) rows.push({ category: 'L6', catalogue: 'GPU供电线', description: gpuCablePicked()?.pn || '', part_category: '', qty: gpuCableQty(), base_price: gpuCableUnitPrice(), currency: 'RMB' })
  return rows
}

// ---- kpSummary → kpLines + gpuArch，喂给 derive ----
function applyKpSummary(s: any) {
  if (!s) return
  const lines: { cat: string; pn: string; qty: number }[] = []
  if (s.cpuPn) lines.push({ cat: 'CPU', pn: s.cpuPn, qty: s.cpuQty || 1 })
  if (s.gpuPn) lines.push({ cat: 'GPU', pn: s.gpuPn, qty: s.gpuQty || 1 })
  if (s.drivesByKind) {
    for (const [_kind, q] of Object.entries(s.drivesByKind)) {
      if ((q as number) > 0) lines.push({ cat: 'HDD/SSD', pn: '', qty: q as number })
    }
  }
  kpLines.value = lines
  gpuArch.value = (s.gpuArch || (s.gpuPn ? 'pt' : 'none')) as GpuArch
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
      // I6 R25 + R27：io_slot riser 数据驱动（standard_riser/riser_x16），不硬编码、不查料号
      standard_riser: (baseConfig.value as any)?.config_content?.standard_riser || '',
      riser_x16: (baseConfig.value as any)?.config_content?.riser_x16 || '',
      // R26：高带宽网卡（100G+，x16 卡）→ IO1 riser 升级 x16
      high_bw_nic: !!props.kpSummary?.highBwNic,
      psu_qty: psuQty(),
      psu_wattage: (psuP?.specs as any)?.wattage,
      psu_name: psuName(),
      gpu_qty: props.kpSummary?.gpuQty || 0,
      gpu_cable_qty: gpuCableQty(),
      // GPU 电源线描述（模板 gpu_power_cord 行用；无 GPU 为空 → 行自动隐藏）
      gpu_power_cord_desc: props.kpSummary?.gpuPn
        ? `${String(props.kpSummary.gpuPn).split('·')[0].trim()} power cord`
        : '',
      // NVMe 盘数（模板 rear_summary 行「N NVME」直连汇总用；与 buildPlanCfg 同口径）
      nvme_count: props.kpSummary?.drivesByKind?.NVMe || 0,
      // 背板描述 + 前面板线缆总根数（模板 Cable/背板行用；与 buildPlanCfg 同口径）
      bp_type_desc: bpType() === 'tri' ? 'NVMe/SATA/SAS' : 'SATA/SAS',
      cable_qty: CORE_DRIVE_KINDS.reduce((s, k) => s + frontCableQty(k), 0),
      // Cable 行主描述（盘数驱动，desc 只显示描述）：live 路径缺 RAID 型号 → 通用 "12SAS Cable" 可读文案，
      // 避免回退 front_cables 把裸 pn 拼进描述
      cable_desc: cableDescFrom({
        sata: props.kpSummary?.drivesByKind?.SATA || 0,
        sas: props.kpSummary?.drivesByKind?.SAS || 0,
        nvme: props.kpSummary?.drivesByKind?.NVMe || 0,
      }, ''),
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
  await loadBaseConfig(id, true)
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

watch([rear, overrides, baseConfig, bomTemplate], scheduleEmit, { deep: true })
watch(() => props.kpSummary, (s) => applyKpSummary(s), { deep: true })
// 外部 baseConfigId 变化时重新加载基准配置（用户在报价页选服务器型号后打开弹窗）
watch(() => props.baseConfigId, async (newId, oldId) => {
  if (newId && newId !== oldId && newId !== baseConfig.value?.id) {
    await loadAllBaseConfigs()
    await loadBaseConfig(newId, true)
    await loadReference(baseConfig.value?.series)
    scheduleEmit()
  }
})
// 外部（报价页 GPU 卡）改 GPU 线 → 同步进内部 overrides 触发成本重算 + apply
// 仅 GPU 线 UI 外移(showGpuCable=false)时由父驱动；ConfigWizard 弹窗内手改走 setOverride 不经此
watch(
  () => [props.initialPicks?.overrides?.gpuCablePn, props.initialPicks?.overrides?.gpuCableQty],
  ([pn, qty]) => {
    if (overrides.gpuCablePn === pn && Number(overrides.gpuCableQty) === Number(qty)) return
    overrides.gpuCablePn = pn as any
    overrides.gpuCableQty = qty as any
    scheduleEmit()
  }
)

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
            <span>{{ bpType() === 'tri' ? '三模' : bpType() === 'dc' ? '直连' : '未选择' }}</span>
            <span class="bp-btns"><button :class="{ on: bpType() === 'tri' }" @click="setOverride('bp', bpType() === 'tri' ? null : 'tri')">三模</button><button :class="{ on: bpType() === 'dc' }" @click="setOverride('bp', bpType() === 'dc' ? null : 'dc')">直连</button></span>
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
            <div v-if="!frontCableParts(k).length" class="front-card-empty">料号库暂无 {{ k }} 线缆</div>
            <div v-else class="front-card-bot">
              <span class="front-price">¥{{ frontCableInfo(k).price }}</span>
              <div class="sc-step"><button @click="setOverride('fc-' + k, Math.max(0, frontCableQty(k) - 1))">−</button><input :value="frontCableQty(k)" @change="(e:any)=>setOverride('fc-' + k, parseInt(e.target.value)||0)" /><button @click="setOverride('fc-' + k, frontCableQty(k) + 1)">+</button></div>
            </div>
          </div>
        </div>
        <div v-if="!frontCables.length" class="sc-empty">料号库暂无「高速存储信号线(前面板件)」料号，请去管理面添加。</div>
      </div>
    </div>

    <!-- ③ 后面板（PCIe IO + 网络 OCP + GPU 供电线）-->
    <div id="l6-panel-rear" class="sc-panel" v-show="!stepper || activeStep === 'rear'">
      <div class="sc-phead"><span class="num">3</span><h2>后面板 · IO 与网络</h2><span class="hint">PCIe IO 槽位 + OCP 网络接口 + GPU 供电线</span><span class="amt">¥{{ (rearTotal + ocpTotal + gpuCableCost).toLocaleString() }}</span></div>
      <div class="sc-pbody">
        <RearPanel
          :slots="rearSlotsView"
          :ocp-slot="ocpSlotView"
          :options="rearOptionsLocked"
          :combo-slots="COMBO_REAR_SLOTS"
          :totals="{ io: rearTotal, ocp: ocpTotal }"
        />

        <template v-if="showGpuCable !== false">
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
        <div v-else class="sc-empty">料号库暂无 GPU 供电线料号（电源分配线缆·后面板件）。</div>
        </template>
      </div>
    </div>

    <!-- ④ 电源 -->
    <div id="l6-panel-psu" class="sc-panel" v-show="!stepper || activeStep === 'psu'">
      <div class="sc-phead"><span class="num">4</span><h2>电源 PSU</h2><span class="hint">自选型号与数量</span><span class="amt">¥{{ psuLineTotal.toLocaleString() }}</span></div>
      <div class="sc-pbody">
        <div class="psu-row" v-if="psuParts.length">
          <label class="psu-lab">PSU 型号</label>
          <PartPicker :items="psuParts.map(fromPartMaster)" :model-value="effectivePsuPn()" size="small" placeholder="(选择 PSU)" @update:model-value="(pn:any)=>setOverride('psuPn', typeof pn==='string'?pn:'')" />
          <span class="psu-unit-price">单价 ¥{{ psuUnitPrice().toLocaleString() }}</span>
          <div class="sc-step psu-step"><button @click="setOverride('psuQty', Math.max(0, psuQty() - 1))">−</button><input :value="psuQty()" @change="(e:any)=>setOverride('psuQty', parseInt(e.target.value)||0)" /><button @click="setOverride('psuQty', psuQty() + 1)">+</button></div>
          <span class="psu-subtotal">¥{{ psuLineTotal.toLocaleString() }}</span>
        </div>
        <div v-else class="sc-empty">料号库暂无「电源模块」类别 PSU。</div>
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
  background: var(--cpq-glass-card-bg);
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
.front-card-empty { font-size: 12px; color: var(--cpq-text-muted,#6E7582); padding: 9px 10px; background: var(--cpq-overlay-w3); border: 1px dashed var(--cpq-overlay-w10); border-radius: 8px; text-align: center; }
.front-card-bot { display: flex; align-items: center; justify-content: space-between; gap: 7px; margin-top: auto; }
.front-price { font-size: 13px; font-weight: 600; color: var(--cpq-text-muted,#6E7582); }
.front-card.active .front-price { color: var(--cpq-accent-primary,#1677FF); }
.sc-section-head { display: flex; align-items: baseline; gap: 10px; margin: 4px 0 10px; }
.sc-section-head.sh-gap { margin-top: 18px; }
.sc-section-head .sh-tag { font-size: 13px; font-weight: 700; color: var(--cpq-text-primary,#E8ECEF); }
.sc-section-head .sh-note { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.sc-section-head .sh-amt { margin-left: auto; font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); }
.psu-row { display: grid; grid-template-columns: 70px minmax(150px,1fr) 110px 110px 90px; gap: 9px; align-items: center; padding: 11px 14px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; margin-bottom: 9px; }
.psu-lab { font-size: 13px; font-weight: 500; color: var(--cpq-text-primary,#E8ECEF); }
.psu-sel { width: 100%; }
.psu-unit-price { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); }
.psu-step { width: auto; flex: 1; }
.psu-subtotal { font-size: 13px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); text-align: right; }
.gpu-cable-line .dl-r { gap: 5px; }
.l6-total-bar { position: relative; display: flex; align-items: baseline; gap: 14px; padding: 12px 18px; border: 1px solid var(--cpq-glass-border-strong); border-radius: var(--cpq-radius-lg); background: var(--cpq-overlay-a8); backdrop-filter: blur(var(--cpq-glass-blur-1)); -webkit-backdrop-filter: blur(var(--cpq-glass-blur-1)); }
.l6-total-bar b { color: var(--cpq-accent-primary,#1677FF); font-size: 18px; }
.l6-total-hint { font-size: 11px; color: var(--cpq-text-muted,#6E7582); margin-left: auto; }
</style>
