<script setup lang="ts">
/** 配置流程（standalone 服务器页）— 机箱概要卡 + KP 按类别拆卡。
 *  机箱（基准/前面板/后面板/电源）收进「机箱配置弹窗」（L6ChassisConfig stepper 模式）；
 *  KP 核心配件按 cat 独立成卡（CPU/Memory/HDD-SSD/GPU/NIC 预设 + 用户从 KP 类别新增）。
 *  kpLines 保持扁平 [{cat,pn,qty}]，卡片是渲染期 groupBy 视图 → 推导/持久化链路不动。 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { isBlockingSeverity } from '@/constants/ruleMeta'
import axios from 'axios'
import { kpPartsApi, partsApi, baseConfigApi, catalogApi, type ServerModel, type KpPart } from '@/api/serverConfig'
import { serverDrawingApi, type DrawingView, type DrawingViewType } from '@/api/serverDrawing'
import L6ChassisConfig from '@/components/quote/L6ChassisConfig.vue'
import ChassisCard from '@/components/server-config/ChassisCard.vue'
import KpCategoryCard from '@/components/server-config/KpCategoryCard.vue'
import PerfRadarChart from '@/components/server-config/PerfRadarChart.vue'
import SpecSheet from '@/components/server-config/SpecSheet.vue'
import { computePerformanceScores, type PerfRawInput, type PerfScoreConfig } from '@/utils/performanceScore'
import ServerAnatomyMap from '@/components/selection-map/ServerAnatomyMap.vue'
import { ServerAnatomyViewer } from '@/components/server-visualization'
import { fromKpPart } from '@/composables/usePartAdapter'
import { SERVER_ANATOMY, type AnatomyForm } from '@/constants/serverAnatomy'
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

// ---- 中部图纸：上传图纸优先，无图纸回退 2U/4U 解剖示意图 ----
const drawing = ref<DrawingView | null>(null)
const drawingLoading = ref(false)
const majorNameById = ref<Record<string, string>>({})
const currentView = ref<DrawingViewType>('top')
const viewOptions: { value: DrawingViewType; label: string }[] = [
  { value: 'top', label: '俯视图' },
  { value: 'front', label: '前视图' },
  { value: 'rear', label: '后视图' },
]
const currentViewLabel = computed(() => viewOptions.find(o => o.value === currentView.value)?.label || '俯视图')
const anatomyForm = computed<AnatomyForm>(() => props.model.base_config?.form === '2U' ? '2U' : '4U')
const anatomyRegions = computed(() => SERVER_ANATOMY[anatomyForm.value]?.[currentView.value] ?? SERVER_ANATOMY[anatomyForm.value]?.top ?? [])

const catQty = (cat: string) => kpLines.value.filter(l => l.cat === cat).reduce((s, l) => s + (l.qty || 0), 0)
const cpuQty = computed(() => catQty('CPU'))
const memoryQty = computed(() => catQty('Memory'))
const drivesQty = computed(() => catQty('HDD/SSD'))
const gpuQty = computed(() => catQty('GPU'))
const nicQty = computed(() => catQty('NIC'))
const psuQty = computed(() => Number(l6Apply.value?.picks?.overrides?.psuQty ?? props.model.base_config?.psu_bays ?? 0))

const sandboxCounts = computed(() => ({
  cpu: cpuQty.value,
  dimm: memoryQty.value,
  drives: drivesQty.value,
  bay: drivesQty.value,
  gpu: gpuQty.value,
  psu: psuQty.value,
}))

function countForDrawingRegion(r: any): number {
  const major = majorNameById.value[r.region_type] || r.region_type || ''
  if (major === '处理器') return cpuQty.value
  if (major === '内存') return memoryQty.value
  if (major === '硬盘') return drivesQty.value
  if (major === '供电') return psuQty.value
  if (major === '扩展') return gpuQty.value + nicQty.value
  return 0
}

const anatomyCounts = computed<Record<string, number>>(() => {
  if (drawing.value?.svg_url) {
    const out: Record<string, number> = {}
    for (const r of drawing.value.regions || []) out[r.uid] = countForDrawingRegion(r)
    return out
  }
  return {
    bays: drivesQty.value,
    cpu: cpuQty.value,
    gpu: gpuQty.value,
    psu: psuQty.value,
    io: nicQty.value,
  }
})

async function loadDrawing() {
  if (!props.model.id) { drawing.value = null; return }
  drawingLoading.value = true
  try { drawing.value = await serverDrawingApi.get(props.model.id, currentView.value) }
  catch { drawing.value = null }
  finally { drawingLoading.value = false }
}
watch(currentView, loadDrawing)

async function loadMajors() {
  try {
    const res = await partsApi.majorCategories()
    const m: Record<string, string> = {}
    for (const it of res.major_categories || []) if (it.id != null) m[String(it.id)] = it.major_category
    majorNameById.value = m
  } catch { majorNameById.value = {} }
}

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
      const desc = v.desc || ''
      const qty = v.qty || ''
      // 空行隐藏：desc 与 qty 都为空（含 0）→ 整行不显示（与左栏 BomTable 一致）
      if (!desc && (qty === '' || qty == null || qty === 0)) continue
      l6Details.push({
        catalogue: row.label || '',
        description: desc,
        part_category: '',
        qty,
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
  // 盘类型分别供给，供「每8盘→线缆」类 derive 规则；与 L6ChassisConfig 使用同一 kpSummary.drivesByKind
  const drivesByKind = kpSummary.value.drivesByKind || {}
  const drive_kinds = (Object.keys(drivesByKind) as string[]).filter(k => (drivesByKind as Record<string, number>)[k] > 0)
  // 注入机型能力档案（base_config 可配）：让「CPU 颗数 / 内存条数 / TDP 超上限」类规则在选型页真实触发
  // （手册：CPU 双路上限、内存 1 路 12 / 2 路 24 DIMM；未配置的能力字段 → undefined，规则自动不触发）
  const cap = props.model?.base_config || {}
  return {
    kp,
    config: {
      series: series.value,
      model: props.model?.name,
      form: props.model?.base_config?.form,
      sata_qty: drivesByKind.SATA || 0,
      sas_qty: drivesByKind.SAS || 0,
      nvme_qty: drivesByKind.NVMe || 0,
      drive_kinds,
      max_cpu: cap.max_cpu,
      max_dimm: cap.max_dimm,
      max_tdp: cap.max_tdp,
      gpu_slots: cap.gpu_slots,
      psu_bays: cap.psu_bays,
    },
    opportunity: {},
  }
}
const selectionActions = computed(() => selectionRulesStore.evaluateRules(buildRuleContext()))



// ---- 右栏结果面板：规则 / 电源 / 性能（只读，不改左侧配置流）----
function numSpec(part: any, key: string): number {
  const v = part?.specs?.[key]
  const n = typeof v === 'number' ? v : parseFloat(v)
  return Number.isFinite(n) ? n : 0
}
function parseCapacityGb(value: any): number {
  if (typeof value === 'number') return value
  const s = String(value ?? '').trim().toUpperCase()
  if (!s) return 0
  const m = s.match(/(\d+(?:\.\d+)?)\s*(TB|GB|T|G)/)
  if (!m) return 0
  return /TB|T/.test(m[2]) ? parseFloat(m[1]) * 1024 : parseFloat(m[1])
}
function fmtGb(gb: number): string {
  if (!gb) return '未维护'
  return gb >= 1024 ? (gb / 1024).toFixed(1) + ' TB' : gb.toFixed(0) + ' GB'
}
function catNumeric(cat: string, key: string): number {
  return kpLines.value.filter(l => l.cat === cat).reduce((s, l) => s + numSpec(kpPart(l.pn), key) * (l.qty || 0), 0)
}
function catCapacity(cat: string): number {
  return kpLines.value.filter(l => l.cat === cat).reduce((s, l) => s + parseCapacityGb(kpPart(l.pn)?.specs?.Capacity) * (l.qty || 0), 0)
}
function linkSpeedValue(value: any): number {
  const s = String(value ?? '').trim().toUpperCase()
  const m = s.match(/(\d+(?:\.\d+)?)\s*(T|G)?/)
  if (!m) return 0
  return m[2] === 'T' ? parseFloat(m[1]) * 1000 : parseFloat(m[1])
}
function actionLabel(kind: string): string {
  const map: Record<string, string> = { require: '必配', exclude: '互斥', derive: '派生', filter: '过滤', recommend: '建议' }
  return map[kind] || kind
}
function resultValueText(a: any): string {
  if (a.action === 'derive' && a.deriveQty != null) return '× ' + a.deriveQty
  if (a.action === 'derive' && a.assignValue != null) return String(a.assignValue)
  if (a.action === 'exclude' && a.offenders?.length) return a.offenders.join(' / ')
  return ''
}
function catPower(cat: string) {
  const rows = kpLines.value.filter(l => l.cat === cat).map(l => ({ w: numSpec(kpPart(l.pn), 'tdp'), qty: l.qty || 0 }))
  const total = rows.reduce((s, r) => s + r.w * r.qty, 0)
  const first = rows.find(r => r.qty > 0)
  const expr = first && first.w > 0 ? first.w + 'W × ' + first.qty : ''
  return { total, expr }
}
const powerSummary = computed(() => {
  const cpu = catPower('CPU')
  const gpu = catPower('GPU')
  const loadW = cpu.total + gpu.total
  const psuW = Number((l6Apply.value as any)?.bomContext?.psu_wattage || 0)
  const psuQty = Number((l6Apply.value as any)?.bomContext?.psu_qty || 0)
  const recW = Math.ceil(loadW * 1.3)
  let psuText = '未维护'
  if (psuW > 0) {
    psuText = psuQty > 0 ? psuW + 'W × ' + psuQty : psuW + 'W × ' + Math.max(1, Math.ceil(recW / psuW)) + '（建议）'
  } else if (recW > 0) {
    psuText = '约 ' + recW + 'W'
  }
  return {
    cpuText: cpu.total ? cpu.expr + ' = ' + cpu.total + 'W' : '未维护',
    gpuText: gpu.total ? gpu.expr + ' = ' + gpu.total + 'W' : '未维护',
    loadText: loadW ? '≈ ' + loadW + 'W' : '未维护',
    redundancyText: loadW ? '× 1.3' : '未维护',
    psuText,
  }
})
const performanceSummary = computed(() => {
  const cores = catNumeric('CPU', 'Cores')
  const memGb = catCapacity('Memory')
  const diskGb = catCapacity('HDD/SSD')
  const gpuMemGb = catCapacity('GPU')
  const nicPorts = catNumeric('NIC', 'Ports')
  const nicLabels = kpLines.value.filter(l => l.cat === 'NIC')
    .map(l => String(kpPart(l.pn)?.specs?.['Link Speed'] || '')).filter(Boolean)
  const nicSpeed = nicLabels.sort((a, b) => linkSpeedValue(b) - linkSpeedValue(a))[0] || ''
  return {
    coresText: cores ? String(cores) : '未维护',
    threadsText: cores ? String(cores * 2) : '未维护',
    memoryText: fmtGb(memGb),
    storageText: fmtGb(diskGb),
    gpuMemText: fmtGb(gpuMemGb),
    nicText: nicPorts ? nicPorts + ' 口' + (nicSpeed ? ' · ' + nicSpeed : '') : '未维护',
  }
})

const kpTotal = computed(() => kpLines.value.reduce((s, l) => s + priceOf(l.pn) * l.qty, 0))

// ---- 性能六维：原始值确定性聚合（缺数据 null 不编造）→ 锚点表打分（锚点存 system_config，零发版可调）----
const SPEC_KEY_CANDIDATES = {
  memSpeed: ['Speed', 'Memory Speed', '内存速度', '速率'],
  gpuFp16: ['FP16 TFLOPS', 'FP16 算力', 'FP16(TFLOPS)', 'FP16', 'AI 算力', '算力'],
}
function specNumberByKeys(part: any, keys: string[]): number {
  for (const k of keys) {
    const v = part?.specs?.[k]
    if (v !== undefined && v !== null && v !== '') {
      const s = String(v)
      // TOPS 是 INT8/FP4 口径，不能当 FP16 TFLOPS 读入（防误标爆分）
      if (/tops/i.test(s) && !/tflops/i.test(s)) continue
      const n = typeof v === 'number' ? v : parseFloat(s.replace(/[^0-9.]/g, ''))
      if (Number.isFinite(n) && n > 0) return n
    }
  }
  return 0
}
const perfCfg = ref<PerfScoreConfig | null>(null)
async function loadPerfConfig() {
  try { perfCfg.value = await catalogApi.getPerformanceScoreConfig() } catch { perfCfg.value = null }
}
const perfRaw = computed<PerfRawInput>(() => {
  const lines = kpLines.value

  // CPU：核数（FP64 峰值 specs 覆盖低，按核数折算并在明细注明）
  const cpuCores = catNumeric('CPU', 'Cores')

  // 内存：容量 + 带宽估算 Σ条数×速率×8B（GB/s）；任一行速率缺→整维带宽视为未维护
  const memGb = catCapacity('Memory')
  let memBw: number | null = 0
  const memBits: string[] = []
  const memLines = lines.filter(l => l.cat === 'Memory')
  if (!memLines.length) memBw = null
  for (const l of memLines) {
    const speed = specNumberByKeys(kpPart(l.pn), SPEC_KEY_CANDIDATES.memSpeed)
    if (!speed) { memBw = null; break }
    memBw! += (l.qty || 0) * speed * 8 / 1000
    memBits.push(`${l.qty}×${speed}MT/s`)
  }

  // 存储：类型加权盘位（NVMe 1.0 / SAS 0.6 / SATA 0.4 / 其他 0.5）
  const byKind: Record<string, number> = {}
  for (const l of lines.filter(l => l.cat === 'HDD/SSD')) {
    const p = kpPart(l.pn) as any
    const k = normalizeDriveKind(p?.specs?.interface || p?.specs?.kind || p?.specs?.type)
      || normalizeDriveKind(p?.name || '') || '其他'
    byKind[k] = (byKind[k] || 0) + (l.qty || 0)
  }
  let storageW: number | null = null
  const storageBits: string[] = []
  if (Object.keys(byKind).length) {
    const W: Record<string, number> = { NVMe: 1, SAS: 0.6, SATA: 0.4 }
    storageW = 0
    for (const [k, n] of Object.entries(byKind)) {
      storageW += n * (W[k] ?? 0.5)
      storageBits.push(`${n}×${k}`)
    }
  }

  // 网络：Σ 口数×端口速率（Gbps）；Link Speed 全缺→null
  let netGbps: number | null = null
  const netBits: string[] = []
  for (const l of lines.filter(l => l.cat === 'NIC')) {
    const p = kpPart(l.pn) as any
    const speed = linkSpeedValue(p?.specs?.['Link Speed'])
    if (!speed) continue
    const ports = numSpec(p, 'Ports') || 1
    netGbps = (netGbps || 0) + ports * speed
    netBits.push(`${ports}×${speed}G`)
  }

  // GPU：FP16 峰值 Σ卡数×单卡算力（specs 未维护→null，不按显存/瓦数折算）
  let gpuT: number | null = null
  const gpuBits: string[] = []
  for (const l of lines.filter(l => l.cat === 'GPU')) {
    const t = specNumberByKeys(kpPart(l.pn), SPEC_KEY_CANDIDATES.gpuFp16)
    if (!t) continue
    gpuT = (gpuT || 0) + (l.qty || 0) * t
    gpuBits.push(`${l.qty}×${t}T`)
  }

  // 可靠性：命中冗余项（PSU≥2 / RAID 卡 / MTBF specs 有维护）；PSU 与 MTBF 全未知→null
  const psuN = psuQty.value
  const hasRaid = lines.some(l => /raid/i.test(l.cat))
  let hasMtbf: boolean | null = null
  for (const l of lines) {
    const p = kpPart(l.pn) as any
    if (p?.specs && 'MTBF' in p.specs) { hasMtbf = !!p.specs['MTBF']; break }
  }
  let relCount: number | null = null
  const relBits: string[] = []
  if (psuN > 0 || hasMtbf !== null) {
    relCount = 0
    if (psuN > 0) {
      relCount += psuN >= 2 ? 1 : 0
      relBits.push(psuN >= 2 ? `电源 ${psuN}+ 冗余` : `电源 ${psuN} 无冗余`)
    }
    relCount += hasRaid ? 1 : 0
    relBits.push(hasRaid ? '含 RAID 卡' : '无 RAID 卡')
    if (hasMtbf !== null) {
      relCount += hasMtbf ? 1 : 0
      relBits.push('MTBF 已维护')
    }
  }

  return {
    cpuCores,
    memCapacityGb: memGb,
    memBandwidthGbs: memBw,
    memText: memBits.join(' + '),
    storageWeighted: storageW,
    storageText: storageBits.join(' + '),
    networkGbps: netGbps,
    networkText: netBits.join(' + '),
    gpuFp16Tflops: gpuT,
    gpuText: gpuBits.join(' + '),
    reliabilityCount: relCount,
    reliabilityText: relBits.join(' · '),
  }
})
const perfDims = computed(() => computePerformanceScores(perfRaw.value, perfCfg.value))

const l6Total = computed(() => l6Apply.value?.totals?.l6 || 0)
const grand = computed(() => l6Total.value + kpTotal.value)

function onL6Apply(payload: any) { l6Apply.value = payload }

const saving = ref(false)
const specVisible = ref(false)
const specTemplate = ref<{branding: any, display_options: any} | null>(null)

// serverconfig 只生成无价格规格书；报价工作台的价格展示自行控制
const specDisplayOptions = computed(() => ({
  ...(specTemplate.value?.display_options || {}),
  show_price_column: false,
  show_chassis_total: false,
  show_kp_subtotal: false,
  show_config_subtotal: false,
  show_grand_total: false,
  show_commercial_terms: false,
}))

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
async function generateSpec() {
  if (!l6Apply.value) { message.warning('请先完成机箱选配'); return }
  // CRE 阻断级校验升级：有 conflict/require 命中时弹确认，用户可「仍然保存」强存
  const blocking = selectionActions.value.filter(a => isBlockingSeverity(a.severity))
  if (blocking.length && !(await confirmBlocking(blocking))) return
  saving.value = true
  try {
    specVisible.value = true
    message.success('规格书已生成')
  } catch (e: any) {
    message.error('生成规格书失败：' + (e.message || e))
  } finally { saving.value = false }
}

function nearestScrollable(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement || null
  while (node) {
    if (node.scrollHeight > node.clientHeight + 1 && /(auto|scroll|overlay)/.test(getComputedStyle(node).overflowY)) return node
    node = node.parentElement
  }
  return null
}

function scrollToPanel(panelId: string) {
  const el = document.getElementById(panelId)
  if (!el) return
  const scroller = nearestScrollable(el)
  if (!scroller) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  const elTop = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top
  scroller.scrollTo({ top: scroller.scrollTop + elTop - 12, behavior: 'smooth' })
}

// ── 手机端（≤768）：三栏 → 双抽屉。左抽屉=服务器图纸，右抽屉=配置结果，
//     主屏=配置卡流；底部 sticky 摘要条常驻电源/规则/图纸入口（桌面三栏不受影响） ──
const isMobile = ref(false)
let _mqListener: ((e: MediaQueryListEvent) => void) | null = null
const openDrawer = ref<null | 'drawing' | 'result'>(null)
const drawingDrawerOpen = computed({
  get: () => openDrawer.value === 'drawing',
  set: (v: boolean) => { openDrawer.value = v ? 'drawing' : null },
})
const resultDrawerOpen = computed({
  get: () => openDrawer.value === 'result',
  set: (v: boolean) => { openDrawer.value = v ? 'result' : null },
})
// 机箱细配 L6 弹窗优先：开弹窗自动收抽屉
watch(chassisModalOpen, (v) => { if (v) openDrawer.value = null })
// 摘要条规则徽标：冲突红优先，其余黄
const ruleBadge = computed(() => {
  const acts = selectionActions.value
  if (!acts.length) return null
  const conflict = acts.filter((a) => a.severity === 'conflict').length
  return conflict > 0
    ? { n: conflict, cls: 'is-conflict' }
    : { n: acts.length, cls: 'is-warn' }
})

onMounted(() => {
  init()
  loadSpecTemplate()
  loadDrawing()
  loadMajors()
  loadPerfConfig()
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
  const mq = window.matchMedia('(max-width: 768px)')
  _mqListener = (e) => { isMobile.value = e.matches }
  mq.addEventListener('change', _mqListener)
})
onBeforeUnmount(() => {
  if (_mqListener) window.matchMedia('(max-width: 768px)').removeEventListener('change', _mqListener)
})
</script>

<template>
  <div class="sc-wizard">
    <div class="sc-banner">
      <span class="bm-name">{{ model.name }}</span>
      <span class="bm-sub">{{ model.use }} · {{ model.base_config?.form }} · {{ model.base_config?.bays }} 盘位</span>
    </div>

    <!-- 步骤指示器：机箱 + 各 KP 卡片（手机端退役：配置卡自带序号即步骤流） -->
    <div v-if="!isMobile" class="sc-steps">
      <template v-for="(s, i) in navSteps" :key="s.target">
        <div class="sc-step" @click="scrollToPanel(s.target)"><span class="sn">{{ s.n }}</span><span class="st">{{ s.label }}</span></div>
        <div v-if="i < navSteps.length - 1" class="sc-step-line"></div>
      </template>
    </div>

    <div class="sc-layout">
      <!-- 左栏：机箱 + KP 配置卡片 -->
      <div class="sc-col-config">
        <!-- ① 机箱概要（点配置按钮弹窗做 4 步细配）-->
        <ChassisCard
          :model="model"
          :series="series"
          :base-config-name="baseConfigName"
          :price-visible="false"
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

      </div>

      <!-- 中栏：服务器图纸 / 解剖示意图，数量随左栏实时变化（手机端移入左抽屉） -->
      <div v-if="!isMobile" class="sc-col-map">
        <div class="sc-map-card">
          <div class="sc-map-head">
            <div class="sc-map-head-left">
              <span class="sc-map-title">服务器图纸</span>
              <span class="sc-map-sub">{{ drawing?.svg_url ? `上传图纸 · ${currentViewLabel}` : `${anatomyForm} ${currentViewLabel} · 解剖示意图` }}</span>
            </div>
            <a-radio-group v-model:value="currentView" size="small" class="sc-view-tabs">
              <a-radio-button v-for="o in viewOptions" :key="o.value" :value="o.value">{{ o.label }}</a-radio-button>
            </a-radio-group>
          </div>
          <a-spin :spinning="drawingLoading">
            <ServerAnatomyViewer
              v-if="drawing?.svg_url"
              decor-mode="plain"
              :svg-url="drawing.svg_url"
              :view-box="drawing.viewBox"
              :regions="drawing.regions || []"
              :counts="anatomyCounts"
              :active-id="null"
              :highlight-ids="[]"
              :sandbox-counts="sandboxCounts"
            />
            <ServerAnatomyMap
              v-else
              decor-mode="plain"
              :view="currentView"
              :regions="anatomyRegions"
              :counts="anatomyCounts"
              :active-id="null"
              :highlight-ids="[]"
              :sandbox-counts="sandboxCounts"
            />
          </a-spin>
        </div>
      </div>

      <!-- 右栏：配置结果 + 保存（手机端移入右抽屉） -->
      <div v-if="!isMobile" class="sc-col-right">
        <div class="sc-result-card glass cpq-stream-edge">
          <div class="sc-result-head">
            <span class="sc-result-title">配置结果</span>
            <span class="sc-result-sub">实时计算 · 只读</span>
          </div>

          <section class="rr-block">
            <div class="rr-title"><span>🛡</span>规则结果</div>
            <div v-if="selectionActions.length" class="rr-rule-list">
              <div v-for="a in selectionActions" :key="a.ruleId" class="rr-rule" :class="`rr-${a.severity}`">
                <span class="rr-badge">{{ actionLabel(a.action) }}</span>
                <span class="rr-desc">{{ a.desc }}</span>
                <span class="rr-val">{{ resultValueText(a) }}</span>
              </div>
            </div>
            <div v-else class="rr-empty">暂无命中规则</div>
          </section>

          <section class="rr-block">
            <div class="rr-title"><span>⚡</span>电源功率</div>
            <div class="rr-rows">
              <div class="rr-row"><span>CPU TDP</span><b>{{ powerSummary.cpuText }}</b></div>
              <div class="rr-row"><span>GPU TDP</span><b>{{ powerSummary.gpuText }}</b></div>
              <div class="rr-row"><span>整机估算负载</span><b>{{ powerSummary.loadText }}</b></div>
              <div class="rr-row"><span>建议冗余系数</span><b>{{ powerSummary.redundancyText }}</b></div>
              <div class="rr-row"><span>建议电源</span><b class="rr-em">{{ powerSummary.psuText }}</b></div>
            </div>
            <div class="rr-note">未含内存 / 盘 / 网卡功耗，未维护 specs 显示「未维护」</div>
          </section>

          <section class="rr-block">
            <div class="rr-title"><span>📈</span>性能参数<span class="rr-title-tail">六维锚点打分 · 相对旗舰线</span></div>
            <PerfRadarChart :dims="perfDims" />
            <div class="rr-metrics" style="margin-top: 10px">
              <div class="rr-metric"><span>CPU 核心</span><b>{{ performanceSummary.coresText }}</b></div>
              <div class="rr-metric"><span>CPU 线程</span><b>{{ performanceSummary.threadsText }}</b></div>
              <div class="rr-metric"><span>内存容量</span><b>{{ performanceSummary.memoryText }}</b></div>
              <div class="rr-metric"><span>存储容量</span><b>{{ performanceSummary.storageText }}</b></div>
              <div class="rr-metric"><span>GPU 显存</span><b>{{ performanceSummary.gpuMemText }}</b></div>
              <div class="rr-metric"><span>高速网口</span><b>{{ performanceSummary.nicText }}</b></div>
            </div>
          </section>

          <button class="sc-save" :disabled="saving" @click="generateSpec">{{ saving ? '生成中…' : '生成 / 打印规格书' }}</button>
        </div>
      </div>
    </div>

    <!-- 手机端左抽屉：服务器图纸（核对位置与数量，随配置实时联动） -->
    <a-drawer
      v-model:open="drawingDrawerOpen"
      placement="left"
      width="94%"
      root-class-name="opp-sc-drawer"
      :closable="false"
      :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    >
      <div class="pd-head-row">
        <h3>服务器图纸</h3><span class="pd-sp"></span>
        <button class="pd-x" type="button" @click="drawingDrawerOpen = false">✕</button>
      </div>
      <div class="pd-scroll">
        <div class="sc-map-card sc-map-card-drawer">
          <div class="sc-map-head">
            <div class="sc-map-head-left">
              <span class="sc-map-title">服务器图纸</span>
              <span class="sc-map-sub">{{ drawing?.svg_url ? `上传图纸 · ${currentViewLabel}` : `${anatomyForm} ${currentViewLabel} · 解剖示意图` }}</span>
            </div>
            <a-radio-group v-model:value="currentView" size="small" class="sc-view-tabs">
              <a-radio-button v-for="o in viewOptions" :key="o.value" :value="o.value">{{ o.label }}</a-radio-button>
            </a-radio-group>
          </div>
          <a-spin :spinning="drawingLoading">
            <ServerAnatomyViewer
              v-if="drawing?.svg_url"
              decor-mode="plain"
              :svg-url="drawing.svg_url"
              :view-box="drawing.viewBox"
              :regions="drawing.regions || []"
              :counts="anatomyCounts"
              :active-id="null"
              :highlight-ids="[]"
              :sandbox-counts="sandboxCounts"
            />
            <ServerAnatomyMap
              v-else
              decor-mode="plain"
              :view="currentView"
              :regions="anatomyRegions"
              :counts="anatomyCounts"
              :active-id="null"
              :highlight-ids="[]"
              :sandbox-counts="sandboxCounts"
            />
          </a-spin>
        </div>
      </div>
    </a-drawer>

    <!-- 手机端右抽屉：配置结果（规则 / 电源 / 性能 / 规格书） -->
    <a-drawer
      v-model:open="resultDrawerOpen"
      placement="right"
      width="88%"
      root-class-name="opp-sc-drawer"
      :closable="false"
      :body-style="{ padding: '0', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    >
      <div class="pd-head-row">
        <h3>配置结果</h3><span class="pd-chip">实时计算 · 只读</span><span class="pd-sp"></span>
        <button class="pd-x" type="button" @click="resultDrawerOpen = false">✕</button>
      </div>
      <div class="pd-scroll">
        <div class="sc-result-card glass cpq-stream-edge">
          <section class="rr-block">
            <div class="rr-title"><span>🛡</span>规则结果</div>
            <div v-if="selectionActions.length" class="rr-rule-list">
              <div v-for="a in selectionActions" :key="a.ruleId" class="rr-rule" :class="`rr-${a.severity}`">
                <span class="rr-badge">{{ actionLabel(a.action) }}</span>
                <span class="rr-desc">{{ a.desc }}</span>
                <span class="rr-val">{{ resultValueText(a) }}</span>
              </div>
            </div>
            <div v-else class="rr-empty">暂无命中规则</div>
          </section>

          <section class="rr-block">
            <div class="rr-title"><span>⚡</span>电源功率</div>
            <div class="rr-rows">
              <div class="rr-row"><span>CPU TDP</span><b>{{ powerSummary.cpuText }}</b></div>
              <div class="rr-row"><span>GPU TDP</span><b>{{ powerSummary.gpuText }}</b></div>
              <div class="rr-row"><span>整机估算负载</span><b>{{ powerSummary.loadText }}</b></div>
              <div class="rr-row"><span>建议冗余系数</span><b>{{ powerSummary.redundancyText }}</b></div>
              <div class="rr-row"><span>建议电源</span><b class="rr-em">{{ powerSummary.psuText }}</b></div>
            </div>
            <div class="rr-note">未含内存 / 盘 / 网卡功耗，未维护 specs 显示「未维护」</div>
          </section>

          <section class="rr-block">
            <div class="rr-title"><span>📈</span>性能参数<span class="rr-title-tail">六维锚点打分 · 相对旗舰线</span></div>
            <PerfRadarChart :dims="perfDims" />
            <div class="rr-metrics" style="margin-top: 10px">
              <div class="rr-metric"><span>CPU 核心</span><b>{{ performanceSummary.coresText }}</b></div>
              <div class="rr-metric"><span>CPU 线程</span><b>{{ performanceSummary.threadsText }}</b></div>
              <div class="rr-metric"><span>内存容量</span><b>{{ performanceSummary.memoryText }}</b></div>
              <div class="rr-metric"><span>存储容量</span><b>{{ performanceSummary.storageText }}</b></div>
              <div class="rr-metric"><span>GPU 显存</span><b>{{ performanceSummary.gpuMemText }}</b></div>
              <div class="rr-metric"><span>高速网口</span><b>{{ performanceSummary.nicText }}</b></div>
            </div>
          </section>

          <button class="sc-save" :disabled="saving" @click="generateSpec">{{ saving ? '生成中…' : '生成 / 打印规格书' }}</button>
        </div>
      </div>
    </a-drawer>

    <!-- 手机端底部 sticky 摘要条：规则 / 电源 / 图纸入口 / 完整结果 -->
    <div v-if="isMobile" class="sumbar">
      <button class="sum-ic" type="button" title="规则命中" @click="resultDrawerOpen = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l8 3v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6l8-3z"/><path d="M9 12l2 2 4-4"/></svg>
        <span v-if="ruleBadge" class="sum-n" :class="ruleBadge.cls">{{ ruleBadge.n }}</span>
      </button>
      <div class="sum-metric" @click="resultDrawerOpen = true">
        <span class="v">{{ powerSummary.psuText }}</span>
        <span class="l">建议电源 · 负载 {{ powerSummary.loadText }}</span>
      </div>
      <button class="sum-ic" type="button" title="服务器图纸" @click="drawingDrawerOpen = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M8 5v14"/></svg>
      </button>
      <button class="sum-cta" type="button" @click="resultDrawerOpen = true">配置结果</button>
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
        :price-visible="false"
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
            :display-options="specDisplayOptions"
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
.sc-wizard { flex: 1; min-height: 0; display: flex; flex-direction: column; width: 100%; max-width: 1600px; margin: 0 auto; }
.sc-steps { display: flex; align-items: center; justify-content: center; gap: 0; margin-bottom: 20px; padding: 12px 20px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); border-radius: 18px;
  box-shadow: var(--cpq-shadow-md); flex-shrink: 0; }
.sc-step { display: flex; align-items: center; gap: 6px; cursor: pointer; transition: all .2s; }
.sc-step:hover .sn { transform: scale(1.1); }
.sc-step .sn { width: 24px; height: 24px; border-radius: 6px; background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; transition: all .2s; }
.sc-step .st { font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); transition: all .2s; }
.sc-step:hover .st { color: var(--cpq-accent-primary,#1677FF); }
.sc-step-line { flex: 1; height: 1px; background: var(--cpq-overlay-w10); margin: 0 8px; max-width: 60px; }
.sc-banner { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; flex-shrink: 0; }
.bm-name { font-size: 18px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.bm-sub { color: var(--cpq-text-secondary,#9BA1AA); font-size: 13px; }
.sc-layout { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(340px, 400px) minmax(0, 1fr) minmax(320px, 360px); gap: 18px; }
.sc-col-config { min-width: 0; height: 100%; max-height: 100%; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; overscroll-behavior: contain; }
.sc-col-config > .sc-panel, .sc-col-config > .add-card-wrap { flex-shrink: 0; }
.sc-col-map { min-width: 0; height: 100%; max-height: 100%; overflow: hidden; }
.sc-map-card { display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 0; padding: 14px;
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); border-radius: 18px; overflow: hidden;
  box-shadow: 0 22px 64px var(--cpq-shadow-color-strong), 0 0 34px var(--cpq-overlay-a4), inset 0 1px 0 var(--cpq-overlay-w15), inset 0 -18px 48px var(--cpq-shadow-color-soft); }
.sc-map-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; flex-shrink: 0; }
.sc-map-head-left { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.sc-view-tabs { flex-shrink: 0; }
.sc-map-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF); }
.sc-map-sub { font-size: 12px; color: var(--cpq-text-muted,#6E7582); }
.sc-map-card :deep(.ant-spin-nested-loading) { flex: 1; min-height: 0; height: auto; }
.sc-map-card :deep(.ant-spin-container) { height: 100%; }
.sc-map-card :deep(.sav-host) { min-height: 0; }
.sc-alerts { padding: 12px 16px; border-radius: var(--cpq-radius-lg, 14px); display: flex; flex-direction: column; gap: 8px; }
.sc-alerts-head { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #1d2129); }
.sc-alerts-ic { font-size: 14px; }
.sc-alert { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.5; padding: 6px 10px; border-radius: 8px; }
.sc-alert.sev-conflict { background: rgba(255,77,79,.1); color: var(--cpq-accent-danger, #ff4d4f); }
.sc-alert.sev-require { background: rgba(22,119,255,.1); color: var(--cpq-accent-primary, #1677ff); }
.sc-alert.sev-info { background: var(--cpq-overlay-a8, rgba(255,255,255,.5)); color: var(--cpq-text-secondary, #4e5969); }
.sc-alert.sev-warning { background: rgba(250,173,20,.12); color: var(--cpq-accent-warning, #faad14); }
.sc-alert-ic { flex: none; font-size: 13px; }
.sc-alert-tx { flex: 1; }

.sc-col-right { min-width: 0; height: 100%; max-height: 100%; overflow-y: auto; overscroll-behavior: contain; }
.sc-cost-card { padding: 18px; border-radius: 18px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(16px); border: 1px solid var(--cpq-overlay-a15); box-shadow: var(--cpq-shadow-md); }
.cc-hero { display: flex; flex-direction: column; gap: 2px; padding-bottom: 14px; margin-bottom: 14px; border-bottom: 1px solid var(--cpq-overlay-w10); }
.cc-hero-label { font-size: 12px; color: var(--cpq-text-muted,#6E7582); }
.cc-hero-val { font-size: 24px; font-weight: 700; color: var(--cpq-accent-primary,#1677FF); line-height: 1.2; }
.cc-row { display: flex; justify-content: space-between; align-items: baseline; padding: 9px 0; font-size: 13px; }
.cc-row-label { color: var(--cpq-text-secondary,#9BA1AA); }
.cc-row-val { color: var(--cpq-text-primary, #E8ECEF); font-weight: 600; }
.sc-save { width: 100%; margin-top: 16px; padding: 11px 22px; background: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-on-primary); font-weight: 700; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; transition: all .2s; }
.sc-save:hover { transform: translateY(-1px); box-shadow: 0 0 18px var(--cpq-overlay-a40); }
.sc-save:disabled { opacity: .5; cursor: not-allowed; }
.add-card-wrap { display: flex; justify-content: center; }
.add-card-sel { width: 100%; max-width: 320px; background: var(--cpq-overlay-b20); color: var(--cpq-text-secondary,#9BA1AA);
  border: 1px dashed var(--cpq-overlay-w20); border-radius: 12px; padding: 11px 14px; font-size: 13px; outline: none; cursor: pointer; transition: all .2s; appearance: none; }
.add-card-sel:hover { border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); background: var(--cpq-overlay-a8); }
/* ── 手机端：抽屉头/滚动体 + 底部 sticky 摘要条 ── */
.pd-head-row { display: flex; align-items: center; gap: 8px; padding: 14px 15px 10px; flex: none; }
.pd-head-row h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--cpq-text-primary, #E8ECEF); }
.pd-chip { font-size: 10px; color: var(--cpq-text-secondary, #9BA1AA); background: var(--cpq-overlay-a15); border-radius: 999px; padding: 2px 8px; white-space: nowrap; }
.pd-sp { flex: 1; }
.pd-x { width: 29px; height: 29px; border-radius: 10px; border: 1px solid var(--cpq-overlay-w20); background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary, #9BA1AA); cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; flex: none; }
.pd-scroll { flex: 1 1 0; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 0 12px 14px; }
.pd-scroll .sc-map-card { height: auto; min-height: 380px; }
.pd-scroll .sc-result-card { height: auto; }

.sumbar { position: fixed; left: 0; right: 0; bottom: var(--cpq-tabbar-inset, 0px); z-index: 170;
  display: flex; align-items: center; gap: 8px; padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0px));
  background: var(--cpq-glass-card-bg, rgba(16, 24, 38, .9));
  -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
  border-top: 1px solid var(--cpq-overlay-a15); }
.sum-ic { position: relative; width: 38px; height: 38px; border-radius: 12px; flex: none; display: inline-flex; align-items: center; justify-content: center;
  background: var(--cpq-overlay-a8); border: 1px solid var(--cpq-overlay-w20); color: var(--cpq-text-secondary, #9BA1AA); cursor: pointer; padding: 0; }
.sum-ic svg { width: 17px; height: 17px; }
.sum-n { position: absolute; top: -6px; right: -6px; min-width: 15px; height: 15px; border-radius: 999px;
  background: var(--cpq-accent-warning, #faad14); color: #1c1408; font-size: 9px; font-weight: 800;
  display: flex; align-items: center; justify-content: center; padding: 0 4px; }
.sum-n.is-conflict { background: var(--cpq-accent-danger, #ff4d4f); color: #fff; }
.sum-metric { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; padding-left: 2px; cursor: pointer; }
.sum-metric .v { font-size: 14.5px; font-weight: 800; color: var(--cpq-text-primary, #E8ECEF); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sum-metric .l { font-size: 9.5px; color: var(--cpq-text-muted, #6E7582); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sum-cta { flex: none; height: 38px; padding: 0 14px; border-radius: 12px; border: none; cursor: pointer;
  background: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-on-primary, #fff); font-size: 12px; font-weight: 700;
  display: inline-flex; align-items: center; gap: 4px; }
.sum-cta::after { content: "›"; font-size: 13px; opacity: .85; }

@media (max-width: 768px) {
  .sc-layout { display: flex; flex-direction: column; }
  .sc-banner { margin-bottom: 10px; }
}

@media (max-width: 1199px) {
  .sc-layout { grid-template-columns: minmax(320px, 360px) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) auto; grid-template-areas: "config map" "result result"; }
  .sc-col-config { grid-area: config; height: 100%; min-height: 0; }
  .sc-col-map { grid-area: map; height: 100%; min-height: 0; }
  .sc-col-right { grid-area: result; height: auto; max-height: 42vh; min-height: 0; overflow-y: auto; }
}
@media (max-width: 960px) {
  .sc-layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; grid-template-areas: "map" "config" "result"; }
  .sc-col-config, .sc-col-map, .sc-col-right { height: auto; max-height: none; overflow: visible; }
  .sc-col-config { grid-area: config; }
  .sc-col-map { grid-area: map; }
  .sc-col-right { grid-area: result; }
  .sc-map-card { height: auto; min-height: 440px; }
  .sc-steps { overflow-x: auto; justify-content: flex-start; }
}
.spec-sheet-overlay { position: fixed; inset: 0; z-index: 200; background: var(--cpq-overlay-b85);
  backdrop-filter: blur(8px); display: flex; flex-direction: row; align-items: flex-start; justify-content: center;
  gap: 16px; padding: 32px 16px; overflow-y: auto; }
.spec-sheet-scroll { display: flex; flex: 1; max-width: 900px; flex-direction: column; align-items: center; gap: 14px; }
/* 工具栏：贴规格书右侧边缘，sticky 随滚动停靠（overlay 自带 overflow 滚动，停靠位=overlay 自身 padding 顶，不吃全局吸顶变量） */
.spec-sheet-toolbar { position: sticky; top: 32px; align-self: flex-start;
  display: flex; flex-direction: column; gap: 10px; z-index: 10; }
.ss-tool-btn { padding: 7px 18px; font-size: 13px; font-weight: 600; border-radius: 10px; cursor: pointer;
  border: 1px solid var(--cpq-overlay-w20); background: var(--cpq-overlay-b60);
  color: var(--cpq-text-primary,#E8ECEF); backdrop-filter: blur(12px); transition: all .2s; }
.ss-tool-btn:hover { border-color: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-primary,#1677FF); }
.ss-tool-btn.primary { background: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-on-primary, #fff); border-color: transparent; }
.ss-tool-btn.primary:hover { color: var(--cpq-accent-on-primary, #fff); opacity: .92; }

.sc-result-card { padding: 16px; border-radius: 18px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(16px); border: 1px solid var(--cpq-overlay-a15); box-shadow: var(--cpq-shadow-md);
  display: flex; flex-direction: column; gap: 14px; }
.sc-result-head { display: flex; align-items: baseline; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid var(--cpq-overlay-w10); }
.sc-result-title { font-size: 15px; font-weight: 700; color: var(--cpq-text-primary, #E8ECEF); }
.sc-result-sub { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.rr-block { border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; padding: 12px; background: var(--cpq-overlay-a8); }
.rr-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--cpq-text-primary,#E8ECEF); margin-bottom: 10px; }
.rr-title span { font-size: 14px; }
.rr-title-tail { margin-left: auto; font-size: 10px; font-weight: 400; color: var(--cpq-text-muted,#6E7582); }
.rr-rule-list { display: flex; flex-direction: column; gap: 8px; }
.rr-rule { display: flex; align-items: flex-start; gap: 8px; padding: 7px 9px; border-radius: 8px; border: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-b20); }
.rr-badge { flex: none; font-size: 10px; padding: 2px 6px; border-radius: 5px; font-weight: 700; }
.rr-conflict .rr-badge { background: rgba(255,77,79,.14); color: var(--cpq-accent-danger,#ff4d4f); }
.rr-require .rr-badge { background: rgba(22,119,255,.14); color: var(--cpq-accent-primary,#1677ff); }
.rr-warning .rr-badge { background: rgba(250,173,20,.14); color: var(--cpq-accent-warning,#faad14); }
.rr-info .rr-badge { background: rgba(168,85,247,.14); color: #a855f7; }
.rr-desc { flex: 1; font-size: 12px; line-height: 1.5; color: var(--cpq-text-secondary,#9BA1AA); }
.rr-val { flex: none; font-size: 12px; font-weight: 700; color: var(--cpq-accent-primary,#1677ff); }
.rr-empty { padding: 12px; font-size: 12px; color: var(--cpq-text-muted,#6E7582); text-align: center; }
.rr-rows { display: flex; flex-direction: column; }
.rr-row { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; padding: 7px 0; border-bottom: 1px dashed var(--cpq-overlay-w10); font-size: 12px; color: var(--cpq-text-secondary,#9BA1AA); }
.rr-row:last-child { border-bottom: 0; }
.rr-row b { font-weight: 700; color: var(--cpq-text-primary,#E8ECEF); }
.rr-em { color: var(--cpq-accent-primary,#1677ff); font-size: 16px; }
.rr-note { margin-top: 8px; font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.rr-metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.rr-metric { display: flex; flex-direction: column; gap: 4px; padding: 9px 10px; border-radius: 10px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); min-width: 0; }
.rr-metric span { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.rr-metric b { font-size: 15px; font-weight: 800; color: var(--cpq-text-primary,#E8ECEF); }

.config-sheet-panel { height: 320px; overflow: hidden; border: 1px solid var(--cpq-overlay-a15); border-radius: 14px; background: var(--cpq-glass-card-bg); backdrop-filter: blur(16px); }
</style>

<!-- a-modal 渲染到 portal（scoped 之外），用全局样式撑满 L6ChassisConfig -->
<style>
.chassis-modal .ant-modal-body { padding: 18px 20px; max-height: 82vh; overflow-y: auto; }
.chassis-modal .ant-modal { top: 30px; }
</style>

<style>
/* 配置向导手机抽屉外壳：portal 到 body，scoped 够不到；本页为固定暗色链路，色值固定不接主题 */
.opp-sc-drawer .ant-drawer-content {
  background: rgba(15, 22, 36, 0.97);
  -webkit-backdrop-filter: blur(20px) saturate(1.2);
  backdrop-filter: blur(20px) saturate(1.2);
  overflow: hidden;
}
.opp-sc-drawer .ant-drawer-left .ant-drawer-content { border-radius: 0 18px 18px 0; }
.opp-sc-drawer .ant-drawer-right .ant-drawer-content { border-radius: 18px 0 0 18px; }
.opp-sc-drawer .ant-drawer-header { display: none; }
</style>
