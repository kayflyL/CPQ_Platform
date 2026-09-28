<script setup lang="ts">
/** 基准配置全页双面板编辑器：左编辑（基准信息 + 整机解剖分组）/ 右成本分析（四卡：合计/构成/Top成本项/机型对比）。
 *  布局按解剖分组：能力/约束字段归属各分组（⑤处理器=CPU 颗数/TDP 上限；⑥内存=条数/通道/标准速率；
 *  ⑦供电=电源槽位/PSU 档位/默认型号；⑨扩展=GPU 槽上限/架构），固定件（底盘件）按料号库大类（major_category=解剖分组）归类。 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { UpOutlined } from '@ant-design/icons-vue'
import { catalogApi, baseConfigApi, partsApi, kpPartsApi, bomTemplateApi, rearIOApi, type BomTemplate, type PartMaster, type RearIOSlotOption, type RearIOItem, type ServerType } from '@/api/serverConfig'
import { systemConfigApi, type OptionItem } from '@/api/systemConfig'
import { useSeriesStore } from '@/stores/series'
import PartPicker from '@/components/common/PartPicker.vue'
import CostAnalysisPanel from '@/components/server-admin/CostAnalysisPanel.vue'
import { fromPartMaster } from '@/composables/usePartAdapter'
import { DEFAULT_REAR_SLOTS, rearSlotsFor, rearIOBucket, optionLabel, optionShortLabel, REAR_SLOT_SUPPORT, CORE_DRIVE_KINDS, gpuArchOptionsFor, formDefaults, PSU_WATTAGE_OPTIONS } from '@/constants/chassisMeta'
import { driveKindOf } from '@/utils/partFit'

const route = useRoute()
const router = useRouter()

const editingId = ref<number | null>(null)
const saving = ref(false)
const loading = ref(false)
const form = ref<any>({
  name: '', series: '', form: '2U', bays: 12, bom_template_id: null,
  server_type_id: null as number | null,
  // 机箱能力档案（物理边界：电源槽位 / GPU 槽 / TDP / 架构 —— 在⑤处理器、⑦供电、⑨扩展分组内编辑）
  psu_bays: 2, gpu_slots: 0, max_tdp: null as number | null, gpu_arch_default: 'none',
  // 机箱能力约束（PSU 档位 / CPU 上限 / 内存条数上限 / 每路通道数）：缺省走全局兜底，拒绝硬编码
  psu_wattages: [] as number[], max_cpu: 2, max_dimm: 24, mem_channels: 12,
  gpu_default: [] as { part_id?: number; qty: number }[],   // 默认 GPU 卡配置（KP 卡×数量；空=未维护）
  rear_slots: DEFAULT_REAR_SLOTS.map(s => ({ ...s, defaults: [] as string[] })),
  // config_content（riser / 内存速率 / 前面板线缆，数据驱动；description/spec_diff 由机型编辑维护）
  configContent: {
    description: '', spec_diff: '',
    standard_riser: {} as Record<string, string>,
    riser_x16: '', standard_mem_speed: null as number | null,
    front_cables: {} as Record<string, string>,   // 前面板线缆 PN 按盘类 {SATA,SAS,NVMe}（软默认，配置页可改）
    default_psu_pn: '',                           // 默认 PSU 料号（软默认，配置页可改；电源型号不锁死）
  },
})
interface Line { uid: number; major: string; pn: string; qty: number }
const commonLines = ref<Line[]>([])
// KP GPU 卡下拉（「GPU 默认卡配置」用）：kpPartsApi 取 GPU 类全部卡
const kpGpuOptions = ref<{ value: number; label: string }[]>([])
async function loadKpGpu() {
  try {
    const cats: any = await kpPartsApi.categories()
    const gpu = (Array.isArray(cats) ? cats : []).find((c: any) => c.name === 'GPU')
    if (!gpu?.id) return
    const parts: any = await kpPartsApi.listByCategory(gpu.id)
    kpGpuOptions.value = (Array.isArray(parts) ? parts : [])
      .filter((p: any) => p.id != null)
      .map((p: any) => ({ value: Number(p.id), label: String(p.name || '') }))
  } catch { /* KP 目录不可用时下拉为空；已有配置仍正常回显 */ }
}
const allParts = ref<PartMaster[]>([])
const templates = ref<BomTemplate[]>([])
const seriesStore = useSeriesStore()
const seriesOptions = seriesStore.items  // 全平台系列权威源（l6.server_types（设置-服务器管理-产品系列））
const formOptions = ref<OptionItem[]>([{ value: '2U', label: '2U' }, { value: '4U', label: '4U' }])
const types = ref<ServerType[]>([])   // 机型类型（通用计算 / AI / 存储），驱动编辑机型页下拉过滤
let uidSeq = 1

// 整机解剖分组骨架（视图数据；③后面板已激活，其余待逐节承接）
const ANATOMY = [
  { n: 1, title: '机箱主体', hint: '机箱 / 辅料 / 线缆固定件' },
  { n: 2, title: '前面板', hint: '硬盘背板连线（默认线缆，配置页可改）' },
  { n: 3, title: '后面板', hint: 'PCIe IO + OCP 网络' },
  { n: 4, title: '主板', hint: '主板 / 托盘 / BMC / 后IO板' },
  { n: 5, title: '处理器', hint: 'CPU 颗数 / TDP 上限 + 散热器固定件' },
  { n: 6, title: '内存', hint: '条数上限 / 通道数 / 标准速率 · 内存条是 KP 配置件（配置页选），这里只存物理边界与标准' },
  { n: 7, title: '供电', hint: '电源槽位 / PSU 档位 / 默认型号' },
  { n: 8, title: '硬盘', hint: '硬盘背板（固定件）' },
  { n: 9, title: '扩展', hint: 'GPU 槽上限 / 架构 + Riser 固定件' },
  { n: 10, title: '散热', hint: '风扇 / 导风罩（固定件）' },
] as const

// ---- 后面板选项目录（按 series 分桶，rearIOApi 提供）----
// 每槽列「类型卡」(X8/X16/SATA/NVMe = option_type)；卡内"+加料"下拉逐件选料号(io_slot+option_type 过滤)，
// 多料组成一张捆绑卡(价=合计)；一槽可多类型(X8+X16 同时)。defaults 存 PN 料号列表。
// 配置页据此按 PN 算出 option_type 卡片 → 只调数量不改料（电源除外）。
const rearOptions = ref<Record<string, RearIOSlotOption[]>>({})
async function loadRearOptions(series?: string) {
  try {
    const res = await rearIOApi.getOptions(rearIOBucket(series || undefined))
    rearOptions.value = res.slots || {}
  } catch { rearOptions.value = {} }
}
function realOptions(name: string): RearIOSlotOption[] {
  return (rearOptions.value[name] || []).filter(o => o.option_type !== 'blank')
}
/** 全部后面板料的 pn→{name,price} 扁平索引（卡内料展示/计价用） */
const rearItemMap = computed<Record<string, { name: string; price: number }>>(() => {
  const m: Record<string, { name: string; price: number }> = {}
  for (const opts of Object.values(rearOptions.value)) {
    for (const o of (opts || [])) for (const it of (o.items || []))
      if (it.pn) m[it.pn] = { name: it.name || it.pn, price: it.unit_price || 0 }
  }
  return m
})
function isOcpSlot(name?: string) { return /^ocp/i.test((name || '').trim()) }
const ioSlots = computed(() => form.value.rear_slots.filter((s: any) => !isOcpSlot(s.name)))
const ocpSlot = computed(() => form.value.rear_slots.find((s: any) => isOcpSlot(s.name)) || null)
function rearIndex(slot: any) { return form.value.rear_slots.indexOf(slot) }
/** 该槽的目录 option_type 列表（= 类型卡列表） */
function optionTypes(name: string): string[] { return realOptions(name).map(o => o.option_type) }
function slotOption(name: string, type: string): RearIOSlotOption | undefined {
  return realOptions(name).find(o => o.option_type === type)
}
/** 该槽某类型卡已选的料号（defaults 里属于该类型的 PN） */
function cardPns(slot: any, type: string): string[] {
  const opt = slotOption(slot?.name, type)
  const itemPns = (opt?.items || []).map(i => i.pn)
  return (slot?.defaults || []).filter((pn: string) => itemPns.includes(pn))
}
/** 该类型卡还没选的候选料（+加料 下拉用） */
function cardCandidates(slot: any, type: string): RearIOItem[] {
  const opt = slotOption(slot?.name, type)
  const picked = new Set(cardPns(slot, type))
  return (opt?.items || []).filter(it => !picked.has(it.pn))
}
function cardPrice(slot: any, type: string): number {
  return cardPns(slot, type).reduce((s, pn) => s + (rearItemMap.value[pn]?.price || 0), 0)
}
/** 该槽已装类型卡摘要：一类型=1 张卡，多料=捆绑组成件（不是数量）。
 * 例：IO1="X16 + X8"；IO3="X8 + NVMe + SATA(3件捆绑)"；空槽显示 空。 */
function slotSpecSummary(slot: any): string {
  const segs: string[] = []
  for (const t of optionTypes(slot.name)) {
    const pns = cardPns(slot, t)
    if (pns.length) segs.push(pns.length > 1 ? `${optionShortLabel(t)}(${pns.length}件捆绑)` : optionShortLabel(t))
  }
  return segs.join(' + ') || '空'
}
/** 该槽已装类型卡的支持设备提示（展示层文案，去重） */
function slotSupport(slot: any): string {
  const set = new Set<string>()
  for (const t of optionTypes(slot.name)) {
    if (cardPns(slot, t).length && REAR_SLOT_SUPPORT[t]) set.add(REAR_SLOT_SUPPORT[t])
  }
  return [...set].join(' / ')
}
function addPn(slot: any, pn: any) {
  const arr = slot.defaults || (slot.defaults = [])
  if (pn && !arr.includes(pn)) arr.push(String(pn))
}
function removePn(slot: any, pn: string) {
  const arr = slot.defaults || (slot.defaults = [])
  arr.splice(0, arr.length, ...arr.filter((p: string) => p !== pn))
}
const pnName = (pn: string) => rearItemMap.value[pn]?.name || pn
const pnPrice = (pn: string) => rearItemMap.value[pn]?.price || 0

// ---- 前面板线缆 + 电源（软默认：基准选默认料号，配置页预填、可改，不锁死）----
// 从已加载的 allParts 客户端过滤（免额外请求）；与配置页 loadReference 同口径
const frontCableParts = computed(() => allParts.value.filter(p => p.category === '高速存储信号线' && p.major_category === '前面板'))
const psuParts = computed(() => allParts.value.filter(p => p.category === '电源模块'))
const psuOptions = computed(() => psuParts.value.map(p => ({ pn: p.pn, name: p.name || p.pn, price: p.unit_price || 0, watt: Number(p.specs?.wattage || p.specs?.power) || 0 })))
function cablesByKind(kind: string) { return frontCableParts.value.filter(p => driveKindOf(p) === kind) }
const cablePickedPn = (kind: string) => (form.value.configContent?.front_cables || {})[kind] || ''
function setCablePn(kind: string, pn: any) {
  const fc = form.value.configContent.front_cables || (form.value.configContent.front_cables = {})
  if (pn) fc[kind] = String(pn)
  else delete fc[kind]
}
const cableName = (pn: string) => frontCableParts.value.find(p => p.pn === pn)?.name || pn
const cablePrice = (pn: string) => frontCableParts.value.find(p => p.pn === pn)?.unit_price || 0
const psuPickedPn = () => form.value.configContent?.default_psu_pn || ''
function setPsuPn(pn: any) { form.value.configContent.default_psu_pn = pn ? String(pn) : '' }
const psuName = (pn: string) => psuParts.value.find(p => p.pn === pn)?.name || pn
const psuPrice = (pn: string) => psuParts.value.find(p => p.pn === pn)?.unit_price || 0

function partByPn(pn?: string) { return allParts.value.find(p => p.pn === pn) }

async function loadOptions() {
  seriesStore.ensureSeries()  // 系列走权威源 store（全平台）
  try {
    const f = await systemConfigApi.getValue<OptionItem[]>('server_form_factor')
    if (Array.isArray(f) && f.length) formOptions.value = f
  } catch { /* 降级默认 */ }
}

async function init() {
  loading.value = true
  try {
    const [partsRes, tplRes] = await Promise.all([partsApi.list({ page_size: 1000 }), bomTemplateApi.list()])
    allParts.value = partsRes.parts
    templates.value = tplRes.templates || []
    types.value = (await catalogApi.listTypes()).types
    const id = route.params.id as string | undefined
    if (id && id !== 'new') {
      editingId.value = Number(id)
      const full: any = await baseConfigApi.get(editingId.value)
      form.value = {
        name: full.name, series: full.series || '', form: full.form || '2U', bays: full.bays ?? 12, bom_template_id: full.bom_template_id ?? null,
        server_type_id: full.server_type_id ?? null,
        // 机箱能力档案（full 来自 baseConfigApi.get，含 psu_bays/rear_slots/gpu_slots/max_tdp/gpu_arch_default）
        psu_bays: full.psu_bays ?? 2, gpu_slots: full.gpu_slots ?? 0,
        max_tdp: full.max_tdp ?? null, gpu_arch_default: full.gpu_arch_default ?? 'none',
        psu_wattages: Array.isArray(full.psu_wattages) ? full.psu_wattages.map((v: any) => Number(v)).filter((n: number) => n > 0) : [],
        max_cpu: full.max_cpu ?? 2, max_dimm: full.max_dimm ?? 24, mem_channels: full.mem_channels ?? 12,
        gpu_default: Array.isArray(full.gpu_default) ? full.gpu_default.map((g: any) => ({ part_id: g.part_id != null ? Number(g.part_id) : undefined, qty: Number(g.qty) || 1 })) : [],
        // rear_slots：携带 defaults（每槽默认卡多重集，配置页据此播种 rear 只调数量）
        rear_slots: (full.rear_slots?.length ? full.rear_slots : DEFAULT_REAR_SLOTS).map((s: any) => ({ name: s.name, cap: s.cap, defaults: [...(s.defaults || [])] })),
      }
      commonLines.value = (full.parts || []).map((p: any) => ({ uid: uidSeq++, major: partByPn(p.pn)?.major_category || '', pn: p.pn, qty: p.quantity }))
      // config_content：riser 按槽位展开（字符串=全槽同规格）、内存速率、前面板线缆，保留 description/spec_diff
      const cc = full.config_content || {}
      const stdRiser: Record<string, string> = {}
      if (typeof cc.standard_riser === 'string') {
        ;(full.rear_slots || []).filter((s: any) => /^io/i.test((s.name || '').trim())).forEach((s: any) => { stdRiser[s.name] = cc.standard_riser as string })
      } else if (cc.standard_riser && typeof cc.standard_riser === 'object') {
        Object.assign(stdRiser, cc.standard_riser)
      }
      form.value.configContent = {
        description: cc.description || '', spec_diff: cc.spec_diff || '',
        standard_riser: stdRiser,
        riser_x16: cc.riser_x16 || '',
        standard_mem_speed: cc.standard_mem_speed != null && cc.standard_mem_speed !== '' ? Number(cc.standard_mem_speed) : null,
        front_cables: cc.front_cables && typeof cc.front_cables === 'object' ? cc.front_cables : {},
        default_psu_pn: cc.default_psu_pn || '',
      }
    }
    await loadRearOptions(form.value.series)
  } finally { loading.value = false }
}

function addLine(major: string = '') { commonLines.value.push({ uid: uidSeq++, major, pn: '', qty: 1 }) }
function delLine(l: Line) { const i = commonLines.value.indexOf(l); if (i >= 0) commonLines.value.splice(i, 1) }
function onPartPick(l: Line, pn: string) {
  l.pn = pn
  const p = partByPn(pn)
  if (p) l.major = p.major_category || ''
}

// ---- 底盘件按解剖分组：大类（major_category，SSOT=料号库 part_taxonomy kind='major'）→ 分组 ----
// 大类名与 ANATOMY 标题一一对应（①机箱主体 ②前面板 ③后面板 ④主板 ⑤处理器 ⑥内存 ⑦供电 ⑧硬盘 ⑨扩展 ⑩散热），
// 料号库左栏大类与编辑页从此同一套数据；②③前面板/后面板、⑥内存、⑦供电为自定义 UI（选择器/能力）。
const anatomyMajor = (n: number) => ANATOMY.find(a => a.n === n)?.title || ''
const linesForSection = (n: number) => commonLines.value.filter(l => l.major === anatomyMajor(n))
const partsForSection = (n: number) => allParts.value.filter(p => p.major_category === anatomyMajor(n))

// ---- 分组折叠 + 头部摘要（学商机详情中部栏：整头可点 + chevron + 0fr 收起动画；进入默认全收起）----
const infoOpen = ref(true)
const openSections = ref<Record<number, boolean>>({})
const tplLabel = computed(() => templates.value.find(t => t.id === form.value.bom_template_id)?.name || '')
function toggleSection(n: number) { openSections.value[n] = !openSections.value[n] }
function setAllSections(open: boolean) {
  const m: Record<number, boolean> = {}
  for (const s of ANATOMY) m[s.n] = open
  openSections.value = m
}
const EMPTY_SUM = '空 · 点击展开添加'
/** 该组已选底盘件摘要：N 件 · 合计¥（无件返回空串） */
function partsSummary(n: number): string {
  const lines = linesForSection(n).filter(l => l.pn)
  if (!lines.length) return ''
  const total = lines.reduce((s, l) => s + (partByPn(l.pn)?.unit_price || 0) * (l.qty || 0), 0)
  return `${lines.length} 件${total ? ` · ¥${Math.round(total).toLocaleString()}` : ''}`
}
/** 折叠态头部摘要：每组一眼看出配了什么；空组引导点开（替代原「待填充」橙标） */
function sectionSummary(n: number): string {
  const parts = partsSummary(n)
  switch (n) {
    case 2: return CORE_DRIVE_KINDS.map(k => cablePickedPn(k) ? `${k}✓` : `${k}–`).join(' ')
    case 3: {
      const segs = form.value.rear_slots
        .filter((sl: any) => (sl.name || '').trim() && slotSpecSummary(sl) !== '空')
        .map((sl: any) => `${sl.name} ${slotSpecSummary(sl)}`)
      return segs.join(' · ') || EMPTY_SUM
    }
    case 6: {
      const c = form.value.configContent
      return `${form.value.max_dimm} 条上限 · ${form.value.mem_channels} 通道${c.standard_mem_speed ? ` · ${c.standard_mem_speed} MT/s` : ''}`
    }
    case 7: {
      const w = (form.value.psu_wattages || []).length ? ` · 档位 ${form.value.psu_wattages.join('/')}W` : ''
      return `${form.value.psu_bays} 电源槽${psuPickedPn() ? ` · 默认 ${psuName(psuPickedPn())}` : ''}${w}`
    }
    case 5: return [`${form.value.max_cpu} CPU`, form.value.max_tdp ? `TDP≤${form.value.max_tdp}W` : '', parts].filter(Boolean).join(' · ')
    case 9: {
      const arch = form.value.gpu_arch_default && form.value.gpu_arch_default !== 'none'
        ? (gpuArchOptionsFor(form.value.form).find(o => o.value === form.value.gpu_arch_default)?.label || '') : ''
      return [`${form.value.gpu_slots} GPU 槽`, arch, parts].filter(Boolean).join(' · ')
    }
    default: return parts || EMPTY_SUM
  }
}

// ---- 后面板槽位行（rear_slots 可增删，命名/容量在槽头编辑；默认卡经 RearPanel 步进器选）----
function addSlot() { form.value.rear_slots.push({ name: '', cap: 1, defaults: [] as string[] }) }
function removeSlot(i: number | string) { form.value.rear_slots.splice(Number(i), 1) }
function resetSlots() { form.value.rear_slots = rearSlotsFor(form.value.form, form.value.series).map(s => ({ ...s, defaults: [] as string[] })) }

async function save() {
  if (!form.value.name) return message.warning('请填基准名称')
  const parts = commonLines.value.filter(l => l.pn)
  if (!parts.length) return message.warning('请至少添加一个底盘件')
  // 槽位名校验：不重；数量非负
  const slotNames = form.value.rear_slots.map((s: any) => (s.name || '').trim()).filter(Boolean)
  if (slotNames.length !== new Set(slotNames).size) return message.warning('后面板槽位名重复')
  saving.value = true
  try {
    const payload: any = {
      name: form.value.name, series: form.value.series, model: form.value.name,
      form: form.value.form, bays: form.value.bays, bom_template_id: form.value.bom_template_id ?? null,
      server_type_id: form.value.server_type_id ?? null,
      // 机箱能力档案（原 ChassisCapabilityEditor 编辑的字段，现并入；修掉历史 gpu_arch_default 写死 'none' 的 clobber 坑）
      psu_bays: Number(form.value.psu_bays) || 0,
      gpu_slots: Number(form.value.gpu_slots) || 0,
      max_tdp: form.value.max_tdp == null ? null : (Number(form.value.max_tdp) || null),
      gpu_arch_default: form.value.gpu_arch_default || 'none',
      psu_wattages: (form.value.psu_wattages || []).map((n: any) => Number(n)).filter((n: number) => n > 0),
      max_cpu: Number(form.value.max_cpu) || 2,
      max_dimm: Number(form.value.max_dimm) || 24,
      mem_channels: Number(form.value.mem_channels) || 12,
      gpu_default: (form.value.gpu_default || [])
        .filter((g: any) => g.part_id)
        .map((g: any) => ({ part_id: Number(g.part_id), qty: Number(g.qty) || 1 })),
      // rear_slots：携带 defaults（每槽默认卡多重集；留空=挡片，配置页该槽回退自由选）
      rear_slots: (form.value.rear_slots || []).filter((s: any) => (s.name || '').trim()).map((s: any) => {
        const out: any = { name: s.name.trim(), cap: Number(s.cap) || 0 }
        const d = (s.defaults || []).filter((t: string) => t && t !== 'blank')
        if (d.length) out.defaults = d
        return out
      }),
      // config_content：只写非空字段；standard_riser 按槽位 dict（留空的槽不落库 → 手填）
      config_content: (() => {
        const c: any = {}
        const d = form.value.configContent || {}
        if (d.description) c.description = d.description
        if (d.spec_diff) c.spec_diff = d.spec_diff
        const ioNames = new Set((form.value.rear_slots || []).map((s: any) => (s.name || '').trim()).filter((n: string) => /^io/i.test(n)))
        const stdRiser: Record<string, string> = {}
        for (const [k, v] of Object.entries(d.standard_riser || {})) {
          if (v && String(v).trim() && ioNames.has(k)) stdRiser[k] = String(v).trim()
        }
        if (Object.keys(stdRiser).length) c.standard_riser = stdRiser
        if (d.riser_x16 && String(d.riser_x16).trim()) c.riser_x16 = String(d.riser_x16).trim()
        if (d.standard_mem_speed != null && d.standard_mem_speed !== '') c.standard_mem_speed = Number(d.standard_mem_speed)
        if (d.front_cables && Object.keys(d.front_cables).length) c.front_cables = d.front_cables
        if (d.default_psu_pn) c.default_psu_pn = d.default_psu_pn
        return Object.keys(c).length ? c : null
      })(),
    }
    let id = editingId.value
    if (id) await baseConfigApi.update(id, payload)
    else id = (await baseConfigApi.create(payload)).id
    await baseConfigApi.setParts(id!, parts.map((l, idx) => ({ pn: l.pn, quantity: l.qty, sort_order: idx })))
    message.success((editingId.value ? '已更新' : '已新建') + '基准配置「' + form.value.name + '」')
    router.push({ path: '/servers/admin', query: { refresh: 'base-config' } })
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
function cancel() { router.push({ path: '/servers/admin', query: { refresh: 'base-config' } }) }

// 系列变化 → 重载后面板选项目录（不同 series 分桶不同）
watch(() => form.value.series, (s) => { loadRearOptions(s) })
// 机箱形态变化 → 重置结构性默认（后面板布局 / 电源槽 / GPU 槽 / GPU 架构）：2U 和 4U 物理结构不同
// 2U=IO1-4+OCP、2 电源、无 GPU 架构；4U=仅 OCP、4 电源、GPU 直通/交换
watch(() => form.value.form, (nf, of) => {
  if (!nf || nf === of) return
  const d = formDefaults(nf)
  form.value.rear_slots = rearSlotsFor(nf, form.value.series).map(s => ({ ...s, defaults: [] as string[] }))
  form.value.psu_bays = d.psu_bays
  form.value.gpu_slots = d.gpu_slots
  form.value.gpu_arch_default = d.gpu_arch
  message.info(`已切换为 ${nf} 标准布局：后面板/电源/GPU 已重置`)
})
onMounted(async () => { await Promise.all([init(), loadOptions(), loadKpGpu()]) })
</script>

<template>
  <div class="editor-page">
    <div class="content-inner">
      <div class="cfg-bar glass">
        <div class="cfg-bar-left">
          <a-button class="btn-ghost" @click="cancel">← 返回列表</a-button>
          <h2 class="cfg-title">{{ editingId ? '编辑基准配置' : '新建基准配置' }}</h2>
        </div>
        <div class="cfg-bar-right">
          <a-button @click="cancel">取消</a-button>
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
        </div>
      </div>

      <div class="two-col">
        <div class="col-left">

          <!-- ① 基准信息卡：头部可折叠（收起时头部即摘要）；BOM 模板并入首行字段行 -->
          <div class="bc-card">
            <div class="bc-card-head card-head-toggle" @click="infoOpen = !infoOpen">
              <span class="bc-card-tag">基准信息</span>
              <span v-if="!infoOpen" class="head-sum">{{ form.name || '未命名' }} · {{ form.form }} · {{ form.bays }} 盘位<template v-if="tplLabel"> · {{ tplLabel }}</template></span>
              <button class="card-chevron" :class="{ collapsed: !infoOpen }" type="button" @click.stop="infoOpen = !infoOpen"><UpOutlined /></button>
            </div>
            <div class="card-collapse" :class="{ collapsed: !infoOpen }">
              <div class="card-collapse-inner info-inner">
                <a-form layout="vertical" :disabled="loading">
                  <a-row :gutter="12">
                    <a-col :span="6"><a-form-item label="基准名称" required><a-input v-model:value="form.name" placeholder="如 Orion-2U-标准型" /></a-form-item></a-col>
                    <a-col :span="5"><a-form-item label="类型"><a-select v-model:value="form.server_type_id" allow-clear placeholder="机型类型"><a-select-option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</a-select-option></a-select></a-form-item></a-col>
                    <a-col :span="3"><a-form-item label="系列"><a-select v-model:value="form.series"><a-select-option v-for="o in seriesOptions" :key="o.value" :value="o.value">{{ o.label }}</a-select-option></a-select></a-form-item></a-col>
                    <a-col :span="3"><a-form-item label="形态"><a-select v-model:value="form.form"><a-select-option v-for="o in formOptions" :key="o.value" :value="o.value">{{ o.label }}</a-select-option></a-select></a-form-item></a-col>
                    <a-col :span="2"><a-form-item label="盘位"><a-input-number v-model:value="form.bays" :min="1" style="width:100%" /></a-form-item></a-col>
                    <a-col :span="5"><a-form-item label="BOM 模板"><a-select v-model:value="form.bom_template_id" allow-clear placeholder="(可选) 按模板推导"><a-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}（{{ t.rows?.length || 0 }}行）</a-select-option></a-select></a-form-item></a-col>
                  </a-row>
                </a-form>
              </div>
            </div>
          </div>

          <!-- ②~⑪ 整机解剖分组：头部即摘要，整头可点折叠（学商机详情中部栏）；默认全收起 -->
          <div class="group-label-row">
            <div class="group-label">整机配置 · 按解剖分组</div>
            <a-space :size="4">
              <a-button size="small" type="text" @click="setAllSections(true)">全部展开</a-button>
              <a-button size="small" type="text" @click="setAllSections(false)">全部收起</a-button>
            </a-space>
          </div>
          <div v-for="s in ANATOMY" :key="s.n" class="anatomy-card">
            <div class="anatomy-head card-head-toggle" @click="toggleSection(s.n)">
              <span class="anatomy-num">{{ s.n }}</span>
              <h3 class="anatomy-title">{{ s.title }}</h3>
              <span class="anatomy-sum" :title="sectionSummary(s.n)">{{ sectionSummary(s.n) }}</span>
              <button class="card-chevron" :class="{ collapsed: !openSections[s.n] }" type="button" @click.stop="toggleSection(s.n)"><UpOutlined /></button>
            </div>
            <div class="card-collapse" :class="{ collapsed: !openSections[s.n] }">
              <div class="card-collapse-inner">
                <div class="anatomy-body">
                <div v-if="s.hint" class="anatomy-hint-in">{{ s.hint }}</div>
              <!-- ③ 后面板：每槽列类型卡(X8/X16/SATA/NVMe)；卡内"+加料"下拉逐件选料号(io_slot+option_type 过滤)、
                   多料组成捆绑卡(价=合计)。一槽可多类型。defaults 存 PN 列表；配置页据此算类型卡→只调数量(电源除外)。 -->
              <div v-if="s.n === 3" class="rear-editor">
                <div class="rear-ctrl">
                  <a-space :size="6">
                    <a-button size="small" @click="addSlot">+ 槽位</a-button>
                    <a-button size="small" type="link" @click="resetSlots">恢复标准布局</a-button>
                  </a-space>
                </div>

                <div class="sc-section-head"><span class="sh-tag">PCIe 扩展能力</span><span class="sh-note">能力与默认结构件 · 每张类型卡内选料号，多料组成捆绑卡；标准 riser 规格留空 = 该槽留空手填</span></div>
                <div class="rear-grid" :style="{ gridTemplateColumns: `repeat(${ioSlots.length || 1}, minmax(0,1fr))` }">
                  <div class="slot-col" v-for="s2 in ioSlots" :key="rearIndex(s2)">
                    <div class="slot-col-head">
                      <a-input v-model:value="s2.name" placeholder="IO1" class="slot-name-in" />
                      <a-input-number v-model:value="s2.cap" :min="0" :max="12" :controls="false" class="slot-cap-in" />
                      <a-button danger size="small" class="slot-del" @click="removeSlot(rearIndex(s2))">✕</a-button>
                    </div>
                    <div class="slot-sum">
                      <span class="sum-line">规格：<b>{{ slotSpecSummary(s2) }}</b></span>
                      <span class="sum-line" v-if="slotSupport(s2)">支持：<b>{{ slotSupport(s2) }}</b></span>
                      <span class="sum-line std-riser-line"><span class="std-riser-lab">标准 riser 规格</span><a-input v-model:value="form.configContent.standard_riser[s2.name]" size="small" class="std-riser-in" placeholder="如 1*X16+1*X8 FHFL" /></span>
                    </div>
                    <div class="type-card" v-for="t in optionTypes(s2.name)" :key="t"
                         :class="{ active: cardPns(s2, t).length }">
                      <div class="type-card-head">
                        <span class="type-name">{{ optionLabel(t) }}</span>
                        <span class="type-bundle" v-if="(slotOption(s2.name, t)?.items?.length || 0) > 1">捆绑 {{ slotOption(s2.name, t)?.items?.length }} 件</span>
                        <span class="type-price" v-if="cardPns(s2, t).length">¥{{ cardPrice(s2, t).toLocaleString() }}/套</span>
                      </div>
                      <div class="type-pns" v-if="cardPns(s2, t).length">
                        <div v-for="pn in cardPns(s2, t)" :key="pn" class="pn-row">
                          <span class="pn-code">{{ pn }}</span>
                          <span class="pn-name">{{ pnName(pn) }}</span>
                          <span class="pn-price">¥{{ pnPrice(pn) }}</span>
                          <button class="pn-del" @click="removePn(s2, pn)">✕</button>
                        </div>
                      </div>
                      <a-select v-if="cardCandidates(s2, t).length" size="small" class="pn-add-sel"
                                placeholder="+ 加料" :value="undefined" @change="(v:any)=>addPn(s2, v)">
                        <a-select-option v-for="it in cardCandidates(s2, t)" :key="it.pn" :value="it.pn">
                          {{ it.name || it.pn }} · ¥{{ it.unit_price }}
                        </a-select-option>
                      </a-select>
                    </div>
                  </div>
                </div>

                <template v-if="ocpSlot">
                  <div class="sc-section-head sh-gap"><span class="sh-tag">网络扩展 · OCP 接口</span><span class="sh-note">OCP 转接适配板 · 支持 OCP 3.0 网络模块，不占 PCIe 槽</span></div>
                  <div class="ocp-cards">
                    <div class="type-card" v-for="t in optionTypes(ocpSlot.name)" :key="t"
                         :class="{ active: cardPns(ocpSlot, t).length }">
                      <div class="type-card-head">
                        <span class="type-name">{{ optionLabel(t) }}</span>
                        <span class="type-price" v-if="cardPns(ocpSlot, t).length">¥{{ cardPrice(ocpSlot, t).toLocaleString() }}</span>
                      </div>
                      <div class="type-pns" v-if="cardPns(ocpSlot, t).length">
                        <div v-for="pn in cardPns(ocpSlot, t)" :key="pn" class="pn-row">
                          <span class="pn-code">{{ pn }}</span>
                          <span class="pn-name">{{ pnName(pn) }}</span>
                          <button class="pn-del" @click="removePn(ocpSlot, pn)">✕</button>
                        </div>
                      </div>
                      <a-select v-if="cardCandidates(ocpSlot, t).length" size="small" class="pn-add-sel"
                                placeholder="+ 加料" :value="undefined" @change="(v:any)=>addPn(ocpSlot, v)">
                        <a-select-option v-for="it in cardCandidates(ocpSlot, t)" :key="it.pn" :value="it.pn">
                          {{ it.name || it.pn }} · ¥{{ it.unit_price }}
                        </a-select-option>
                      </a-select>
                    </div>
                  </div>
                </template>

                <div class="rear-x16">
                  <label class="rear-x16-lab">PCIe 扩展升级规则</label>
                  <div class="rear-x16-note">装 GPU（≥1 张）→ 全部 IO 槽应用此规格；含 100G/200G/400G 网卡 → IO1 应用此规格；留空 = 装 GPU 时对应行留空手填</div>
                  <a-input v-model:value="form.configContent.riser_x16" placeholder="如 1*X16+1*X8 FHFL" />
                </div>
              </div>

              <!-- ② 前面板：按盘类(SATA/SAS/NVMe)选默认线缆料号（软默认，配置页预填可改） -->
              <div v-else-if="s.n === 2" class="front-panel">
                <div class="front-cards">
                  <div class="type-card" v-for="k in CORE_DRIVE_KINDS" :key="k"
                       :class="{ active: !!cablePickedPn(k) }">
                    <div class="type-card-head">
                      <span class="type-name">{{ k }} 线缆</span>
                      <span class="type-price" v-if="cablePickedPn(k)">¥{{ cablePrice(cablePickedPn(k)) }}</span>
                    </div>
                    <div class="pn-row" v-if="cablePickedPn(k)">
                      <span class="pn-code">{{ cablePickedPn(k) }}</span>
                      <span class="pn-name">{{ cableName(cablePickedPn(k)) }}</span>
                      <button class="pn-del" @click="setCablePn(k, '')">✕</button>
                    </div>
                    <a-select v-if="cablesByKind(k).length" size="small" class="pn-add-sel"
                              :value="cablePickedPn(k) || undefined"
                              :placeholder="cablePickedPn(k) ? '更换线缆' : '+ 选默认线缆'"
                              @change="(v:any)=>setCablePn(k, v)">
                      <a-select-option v-for="p in cablesByKind(k)" :key="p.pn" :value="p.pn">
                        {{ p.name || p.pn }} · ¥{{ p.unit_price || 0 }}
                      </a-select-option>
                    </a-select>
                    <div v-else class="slot-blank-tag">料号库暂无 {{ k }} 线缆</div>
                  </div>
                </div>
              </div>

              <!-- ⑦ 供电：电源槽位 / PSU 档位 / 默认型号（软默认，配置页预填可改） -->
              <div v-else-if="s.n === 7" class="psu-panel">
                <div class="capability-block">
                  <a-row :gutter="12">
                    <a-col :span="6"><div class="cap-item"><span class="cap-lab">电源槽位</span><a-input-number v-model:value="form.psu_bays" :min="0" :max="8" style="width:100%" /></div></a-col>
                    <a-col :span="18"><div class="cap-item"><span class="cap-lab">PSU 瓦数档位 (W)</span><a-select v-model:value="form.psu_wattages" mode="tags" placeholder="留空=不限（沿用全局档位）；如 ES220 V3=[1300,1600,2000]" :options="PSU_WATTAGE_OPTIONS.map(v => ({ value: v, label: v + 'W' }))" style="width:100%" /></div></a-col>
                  </a-row>
                </div>
                <div class="psu-row-edit">
                  <label class="psu-lab-edit">默认 PSU 型号</label>
                  <a-select v-if="psuOptions.length" class="psu-sel-edit"
                            :value="psuPickedPn() || undefined" placeholder="(可选 — 给配置页预填默认 PSU)"
                            allow-clear @change="(v:any)=>setPsuPn(v)">
                    <a-select-option v-for="p in psuOptions" :key="p.pn" :value="p.pn">
                      {{ p.name }}<span v-if="p.watt"> · {{ p.watt }}W</span> · ¥{{ p.price }}
                    </a-select-option>
                  </a-select>
                  <div v-else class="slot-blank-tag">料号库暂无电源模块</div>
                </div>
                <div class="pn-row" v-if="psuPickedPn()" style="margin-top:6px">
                  <span class="pn-code">{{ psuPickedPn() }}</span>
                  <span class="pn-name">{{ psuName(psuPickedPn()) }}</span>
                  <span class="pn-price">¥{{ psuPrice(psuPickedPn()) }}</span>
                  <button class="pn-del" @click="setPsuPn('')">✕</button>
                </div>
              </div>

              <!-- ① 机箱主体：机箱 / 辅料 / 线缆固定件（能力/约束字段已归各分组）；行单行化：选中后规格/单价内联尾随 -->
              <div v-else-if="s.n === 1" class="section-parts">
                <div class="line-list">
                  <div class="line-row" v-for="l in linesForSection(1)" :key="l.uid">
                    <span class="line-idx">{{ commonLines.indexOf(l) + 1 }}</span>
                    <PartPicker style="flex:1" :items="partsForSection(1).map(fromPartMaster)" :model-value="l.pn" placeholder="🔍 选机箱/辅料/线缆件"
                                @update:model-value="(pn:any)=>onPartPick(l, typeof pn==='string'?pn:'')">
                      <template #option="{ item }"><div class="bcb-opt"><div class="bcb-opt-row"><span class="bcb-opt-name">{{ item.name }}</span><span v-if="item.unit_price != null" class="bcb-opt-price">¥{{ item.unit_price.toLocaleString() }}</span></div><div class="bcb-opt-sub"><span class="bcb-opt-cat">{{ item.category }}</span><span v-if="item.supplier" class="bcb-opt-brand">{{ item.supplier }}</span></div></div></template>
                    </PartPicker>
                    <span v-if="partByPn(l.pn)" class="li-spec" :title="partByPn(l.pn)?.spec_text">{{ partByPn(l.pn)?.spec_text || '—' }}</span>
                    <span v-if="partByPn(l.pn)" class="li-price">¥{{ (partByPn(l.pn)?.unit_price ?? 0).toLocaleString() }}</span>
                    <a-input-number v-model:value="l.qty" :min="1" style="width:72px" />
                    <a-button danger size="small" @click="delLine(l)">✕</a-button>
                  </div>
                </div>
                <a-button dashed size="small" style="margin-top:6px" @click="addLine(anatomyMajor(1))">+ 添加机箱/辅料/线缆件</a-button>
              </div>

              <!-- ⑥ 内存：条数上限 / 每路通道数 / 标准速率（能力属性；内存条是 KP 配置件，不进基准） -->
              <div v-else-if="s.n === 6" class="section-parts">
                <a-row :gutter="12">
                  <a-col :span="8"><div class="cap-item"><span class="cap-lab">内存条数上限</span><a-input-number v-model:value="form.max_dimm" :min="1" :max="64" style="width:100%" /></div></a-col>
                  <a-col :span="8"><div class="cap-item"><span class="cap-lab">每路通道数</span><a-input-number v-model:value="form.mem_channels" :min="1" :max="24" style="width:100%" /></div></a-col>
                  <a-col :span="8"><div class="cap-item"><span class="cap-lab">标准内存速率 (MT/s)</span><a-input-number v-model:value="form.configContent.standard_mem_speed" :min="0" placeholder="如 4800" style="width:100%" /></div></a-col>
                </a-row>
              </div>

              <!-- 通用固定件分组（④⑤⑧⑨⑩）：底盘件按 SECTION_CATS 分类迁入；固定件，数量随机箱、配置页不调 -->
              <div v-else-if="anatomyMajor(s.n)" class="section-parts">
                <!-- ⑤ 处理器：CPU 物理边界（颗数上限 / 散热·供电承载 TDP 上限） -->
                <div v-if="s.n === 5" class="capability-block">
                  <a-row :gutter="12">
                    <a-col :span="8"><div class="cap-item"><span class="cap-lab">CPU 颗数上限</span><a-input-number v-model:value="form.max_cpu" :min="1" :max="8" style="width:100%" /></div></a-col>
                    <a-col :span="8"><div class="cap-item"><span class="cap-lab">CPU TDP 上限 (W)</span><a-input-number v-model:value="form.max_tdp" :min="0" placeholder="可空" style="width:100%" /></div></a-col>
                  </a-row>
                </div>
                <!-- ⑨ 扩展：GPU 槽上限 / 默认拓扑架构 -->
                <div v-if="s.n === 9" class="capability-block">
                  <a-row :gutter="12">
                    <a-col :span="8"><div class="cap-item"><span class="cap-lab">GPU 槽上限</span><a-input-number v-model:value="form.gpu_slots" :min="0" :max="16" style="width:100%" /></div></a-col>
                    <a-col :span="8"><div class="cap-item"><span class="cap-lab">GPU 架构</span><a-select v-model:value="form.gpu_arch_default" :options="gpuArchOptionsFor(form.form)" style="width:100%" /></div></a-col>
                  </a-row>
                  <!-- GPU 默认卡配置（KP 卡×数量）：AI 推理配置器「机型装得下判定」的数据输入；空=该机型未维护，配置器诚实降级 -->
                  <div class="cap-item" style="margin-top:8px">
                    <span class="cap-lab">GPU 默认卡配置</span>
                    <div v-for="(g, gi) in form.gpu_default" :key="gi" style="display:flex;gap:6px;align-items:center;margin-top:6px">
                      <a-select v-model:value="g.part_id" show-search option-filter-prop="label" :options="kpGpuOptions" placeholder="选 KP GPU 卡" style="flex:1" />
                      <a-input-number v-model:value="g.qty" :min="1" :max="16" style="width:76px" />
                      <a-button size="small" type="text" danger @click="form.gpu_default.splice(gi, 1)">删</a-button>
                    </div>
                    <a-button size="small" type="dashed" block style="margin:6px 0 0" @click="form.gpu_default.push({ qty: 1 })">+ 加默认卡</a-button>
                  </div>
                </div>
                <div class="line-list">
                  <div class="line-row" v-for="l in linesForSection(s.n)" :key="l.uid">
                    <span class="line-idx">{{ commonLines.indexOf(l) + 1 }}</span>
                    <PartPicker style="flex:1" :items="partsForSection(s.n).map(fromPartMaster)" :model-value="l.pn" :placeholder="`🔍 选${s.title}件`"
                                @update:model-value="(pn:any)=>onPartPick(l, typeof pn==='string'?pn:'')">
                      <template #option="{ item }">
                        <div class="bcb-opt">
                          <div class="bcb-opt-row"><span class="bcb-opt-name">{{ item.name }}</span><span v-if="item.unit_price != null" class="bcb-opt-price">¥{{ item.unit_price.toLocaleString() }}</span></div>
                          <div class="bcb-opt-sub"><span class="bcb-opt-cat">{{ item.category }}</span><span v-if="item.supplier" class="bcb-opt-brand">{{ item.supplier }}</span></div>
                        </div>
                      </template>
                    </PartPicker>
                    <span v-if="partByPn(l.pn)" class="li-spec" :title="partByPn(l.pn)?.spec_text">{{ partByPn(l.pn)?.spec_text || '—' }}</span>
                    <span v-if="partByPn(l.pn)" class="li-price">¥{{ (partByPn(l.pn)?.unit_price ?? 0).toLocaleString() }}</span>
                    <a-input-number v-model:value="l.qty" :min="1" style="width:72px" />
                    <a-button danger size="small" @click="delLine(l)">✕</a-button>
                  </div>
                </div>
                <a-button dashed size="small" style="margin-top:6px" @click="addLine(anatomyMajor(s.n))">+ 添加{{ s.title }}件</a-button>
                <div v-if="!partsForSection(s.n).length" class="anatomy-placeholder">料号库暂无{{ s.title }}相关分类料号（{{ anatomyMajor(s.n) }}）</div>
              </div>
                </div>
              </div>
            </div>
          </div>

        </div>

        <div class="col-right">
          <CostAnalysisPanel
            :parts="allParts"
            :lines="commonLines"
            :rear-slots="form.rear_slots"
            :front-cables="form.configContent.front_cables || {}"
            :default-psu-pn="form.configContent.default_psu_pn || ''"
            :psu-bays="form.psu_bays"
            :editing-id="editingId"
            :groups="ANATOMY"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-page { min-height: calc(100vh - var(--cpq-header-clearance, 0px)); }
.content-inner { width: 100%; margin: 0 auto; padding: 24px; }
.cfg-bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; margin-bottom: 16px; }
.cfg-bar-left { display: flex; align-items: center; gap: 16px; }
.cfg-title { margin: 0; font-size: 16px; }
.cfg-bar-right { display: flex; gap: 8px; }
.btn-ghost { background: transparent; border: 1px solid var(--cpq-overlay-w15); }
.two-col { display: flex; gap: 16px; align-items: flex-start; }
.col-left { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.col-right { flex: 0 0 420px; position: sticky; top: calc(var(--cpq-sticky-top, 0px) + 16px); max-height: calc(100vh - var(--cpq-sticky-top, 0px) - 32px); overflow-y: auto; }

/* —— 通用玻璃卡片（基准信息 / 备份）—— 头在卡内、体走折叠容器，卡壳零内边距 */
.bc-card { padding: 0; border-radius: var(--cpq-radius-lg, 14px); overflow: hidden;
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); box-shadow: var(--cpq-shadow-md); }
.bc-card-head { display: flex; align-items: center; gap: 10px; padding: 10px 16px; }
.bc-card-tag { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary, #E8ECEF);
  padding: 3px 10px; border-radius: 6px; background: var(--cpq-overlay-a15); flex-shrink: 0; }
.info-inner { padding: 4px 16px 14px; transition: padding .25s ease; }
.card-collapse.collapsed .info-inner { padding-top: 0; padding-bottom: 0; }

/* —— 折叠（学商机详情中部栏）：整头可点 + chevron 旋转 + 0fr 网格收起动画 —— */
.card-head-toggle { cursor: pointer; user-select: none; }
.card-head-toggle:hover .anatomy-title, .card-head-toggle:hover .bc-card-tag { color: var(--cpq-accent-primary, #1677FF); }
.head-sum, .anatomy-sum { flex: 1; min-width: 0; font-size: 12px; color: var(--cpq-text-muted, #6E7582);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-chevron { margin-left: auto; flex-shrink: 0; width: 26px; height: 26px; border: none; border-radius: 7px;
  background: var(--cpq-overlay-a15); color: var(--cpq-text-muted, #6E7582); cursor: pointer;
  display: flex; align-items: center; justify-content: center; font-size: 12px;
  transition: transform .25s ease, background .2s, color .2s; }
.card-chevron:hover { color: var(--cpq-text-primary, #E8ECEF); background: var(--cpq-overlay-a30, rgba(22,119,255,.3)); }
.card-chevron.collapsed { transform: rotate(180deg); }
.card-collapse { display: grid; grid-template-rows: 1fr; transition: grid-template-rows .25s ease; }
.card-collapse.collapsed { grid-template-rows: 0fr; }
.card-collapse-inner { overflow: hidden; min-height: 0; }

/* —— 整机解剖分组 —— */
.group-label-row { display: flex; align-items: center; justify-content: space-between; margin: 6px 2px -2px; }
.group-label { font-size: 12px; font-weight: 600; letter-spacing: .5px;
  color: var(--cpq-text-muted, #6E7582); margin: 0; }
.anatomy-card { border-radius: var(--cpq-radius-lg, 14px); overflow: hidden;
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-w10); }
.anatomy-head { display: flex; align-items: center; gap: 12px; padding: 10px 16px;
  border-bottom: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w4); }
.anatomy-num { width: 26px; height: 26px; border-radius: 7px; background: var(--cpq-overlay-a15);
  color: var(--cpq-accent-primary, #1677FF); display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; flex-shrink: 0; }
.anatomy-title { font-size: 14px; font-weight: 600; margin: 0; color: var(--cpq-text-primary, #E8ECEF); flex-shrink: 0; }
.anatomy-hint-in { font-size: 12px; line-height: 1.5; color: var(--cpq-text-muted, #6E7582); margin-bottom: 10px; }
.anatomy-body { padding: 12px 16px; }
.anatomy-placeholder { font-size: 13px; line-height: 1.6; color: var(--cpq-text-muted, #6E7582); }

/* —— ③ 后面板：类型卡 + 卡内料号组成 —— */
.rear-editor { display: flex; flex-direction: column; gap: 10px; }
.rear-ctrl { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sc-section-head { display: flex; align-items: baseline; gap: 10px; margin: 2px 0 0; }
.sc-section-head.sh-gap { margin-top: 8px; }
.sc-section-head .sh-tag { font-size: 13px; font-weight: 700; color: var(--cpq-text-primary, #E8ECEF); }
.sc-section-head .sh-note { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.rear-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.slot-col { display: flex; flex-direction: column; gap: 8px; padding: 12px; min-width: 0;
  background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; }
.slot-col-head { display: flex; align-items: center; gap: 6px; padding-bottom: 6px; border-bottom: 1px solid var(--cpq-overlay-w8); }
.slot-sum { display: flex; flex-direction: column; gap: 2px; padding: 0 2px; }
.slot-sum .sum-line { font-size: 11px; color: var(--cpq-text-muted, #6E7582); }
.slot-sum .sum-line b { color: var(--cpq-text-secondary, #9BA1AA); font-weight: 600; }
.slot-sum .std-riser-line { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.slot-sum .std-riser-lab { flex-shrink: 0; }
.slot-sum .std-riser-in { flex: 1; min-width: 0; }
.slot-name-in { flex: 1; min-width: 56px; }
.slot-cap-in { width: 42px; flex-shrink: 0; }
.slot-cap-in :deep(input) { text-align: center; padding: 0 2px; font-size: 12px; }
.slot-del { flex-shrink: 0; }
.type-card { padding: 8px 9px; border: 1px solid var(--cpq-overlay-w8); border-radius: 8px;
  background: var(--cpq-overlay-w4); transition: all .2s; }
.type-card.active { border-color: var(--cpq-overlay-a40); background: var(--cpq-overlay-a8); box-shadow: 0 0 10px var(--cpq-overlay-a8); }
.type-card-head { display: flex; align-items: baseline; gap: 6px; margin-bottom: 5px; }
.type-name { font-size: 12px; font-weight: 700; color: var(--cpq-text-secondary, #9BA1AA); }
.type-card.active .type-name { color: var(--cpq-text-primary, #E8ECEF); }
.type-bundle { font-size: 10px; color: var(--cpq-accent-primary, #1677FF); background: var(--cpq-overlay-a15); padding: 1px 5px; border-radius: 4px; }
.type-price { margin-left: auto; font-size: 11px; font-weight: 600; color: var(--cpq-accent-primary, #1677FF); }
.type-pns { display: flex; flex-direction: column; gap: 3px; margin-bottom: 5px; }
.pn-row { display: flex; align-items: baseline; gap: 5px; }
.pn-code { font-size: 10px; font-family: monospace; color: var(--cpq-text-muted, #6E7582); flex-shrink: 0; }
.pn-name { font-size: 11px; color: var(--cpq-text-secondary, #9BA1AA); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pn-price { font-size: 11px; color: var(--cpq-text-muted, #6E7582); flex-shrink: 0; }
.pn-del { border: none; background: transparent; color: var(--cpq-text-muted, #6E7582); cursor: pointer;
  font-size: 11px; padding: 0 2px; flex-shrink: 0; }
.pn-del:hover { color: #ff4d4f; }
.pn-add-sel { width: 100%; }
.ocp-cards { display: flex; flex-wrap: wrap; gap: 10px; }
.ocp-cards .type-card { flex: 1; min-width: 200px; }
.rear-x16 { margin-top: 4px; }
.rear-x16-lab { display: block; font-size: 13px; color: var(--cpq-text-secondary, #9BA1AA); margin-bottom: 4px; }
.rear-x16-note { font-size: 11px; color: var(--cpq-text-muted, #6E7582); margin-bottom: 4px; }

/* —— ② 前面板 / ⑦ 供电（软默认）—— */
.front-panel { display: flex; flex-direction: column; gap: 8px; }
.front-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.psu-panel { display: flex; flex-direction: column; gap: 6px; }
.psu-row-edit { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.psu-lab-edit { font-size: 13px; color: var(--cpq-text-secondary, #9BA1AA); white-space: nowrap; }
.psu-sel-edit { min-width: 260px; flex: 1; }
.section-parts { display: flex; flex-direction: column; gap: 8px; }
.capability-block { padding: 10px 12px; background: var(--cpq-overlay-w4); border: 1px solid var(--cpq-overlay-w8); border-radius: 10px; }
.cap-item { display: flex; flex-direction: column; gap: 3px; }
.cap-lab { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }

/* —— 各分组底盘件行（单行：选择器 + 规格 + 单价 + 数量，选中后信息内联尾随）—— */
.line-list { min-height: 40px; display: flex; flex-direction: column; gap: 6px; }
.line-row { display: flex; gap: 6px; align-items: center; }
.drag-row { cursor: grab; color: var(--cpq-text-muted, #6E7582); padding: 0 4px; user-select: none; font-size: 16px; line-height: 1; }
.drag-row:active { cursor: grabbing; }
.line-idx { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-variant-numeric: tabular-nums; width: 18px; text-align: center; flex-shrink: 0; }
.li-spec { flex: 0 0 170px; font-size: 12px; color: var(--cpq-text-muted, #6E7582);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.li-price { flex-shrink: 0; font-size: 12px; color: var(--cpq-accent-primary); font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>

<!-- PartPicker 下拉 teleported 到 body，非 scoped；用 .bcb-opt 前缀限定 -->
<style>
.bcb-opt { padding: 5px 2px; line-height: 1.45; }
.bcb-opt-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.bcb-opt-name { font-size: 14px; color: var(--cpq-text-primary, #E8ECEF); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bcb-opt-price { font-size: 13px; color: var(--cpq-accent-primary); font-weight: 600; white-space: nowrap; }
.bcb-opt-sub { display: flex; gap: 8px; align-items: center; margin-top: 2px; font-size: 12px; }
.bcb-opt-cat { color: var(--cpq-accent-primary); }
.bcb-opt-brand { color: var(--cpq-text-muted, #6E7582); margin-left: auto; }
</style>
