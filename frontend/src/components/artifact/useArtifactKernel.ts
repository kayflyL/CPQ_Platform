/**
 * 产出物模板编辑器内核（2B 路线：craft.js 蓝图的 Vue3 无头内核）。
 * 职责=区块状态 + 结构动作 + 撤销历史 + 类型注册表 + 画布样例渲染器；
 * 视图（ArtifactTemplateCenter 编辑器）只做交互接线。blocks JSON 与后端
 * artifact_render.py 渲染契约逐字段兼容（title/text/kpi/chart/table/fields
 * + heading/callout/divider/image 扩展），模板层零 AI 不变。
 *
 * craft.js 对应关系：blocks≈nodes 树（扁平）、BLOCK_DEFS≈resolver、
 * actions≈editor.actions、history≈序列化快照栈。样例内容只进画布，
 * 存库 blocks 不含任何示例数据。
 */
import { computed, ref } from 'vue'
import type { ArtifactBlock, ChartAssetMeta, KpiMetricOption } from '@/api/artifactTemplates'

/* ───────────── 类型注册表（craft.js resolver） ───────────── */

export interface BlockDef {
  /** 组件库键（'literal-text' 等虚拟键允许；defaults() 产出真实区块类型） */
  type: string
  label: string
  sub: string
  ico: string
  group: string
  /** 数据槽（渲染时由工作流产出填充，画布显示示例内容） */
  slot?: boolean
  /** 纯版式装饰 */
  deco?: boolean
  defaults: () => ArtifactBlock
}

let uidSeq = 100
export const blockUid = () => `b${uidSeq++}`

export const BLOCK_DEFS: BlockDef[] = [
  { type: 'title', label: '报告抬头', sub: '标题 / 副题 / 品牌 / Logo', ico: 'T', group: '基础', defaults: () => ({ id: blockUid(), type: 'title' }) },
  { type: 'heading', label: '小节题', sub: '独立编号小节标题', ico: '❭', group: '基础', defaults: () => ({ id: blockUid(), type: 'heading', title: '小节标题' }) },
  { type: 'callout', label: '提示卡', sub: '洞察 / 口径 / 风险', ico: '❝', group: '基础', defaults: () => ({ id: blockUid(), type: 'callout', tone: 'blue', co_title: '提示', text: '示例：GPU 密集型需求连续三月上升。' }) },
  { type: 'literal-text', label: '固定文案', sub: '口径说明等静态文字', ico: '✎', group: '基础', defaults: () => ({ id: blockUid(), type: 'text', source: 'literal', text: '口径说明：本文数据范围由报告配置指定，图表与文字同源。' }) },
  { type: 'text', label: '章节文本槽', sub: 'AI 答复按章节填入', ico: '¶', group: '数据槽', slot: true, defaults: () => ({ id: blockUid(), type: 'text', source: 'payload', key: '' }) },
  { type: 'kpi', label: 'KPI 指标槽', sub: '指标原子勾选组合', ico: '◧', group: '数据槽', slot: true, defaults: () => ({ id: blockUid(), type: 'kpi', asset: 'cockpit.kpi' }) },
  { type: 'chart', label: '图表槽', sub: '引用资产注册表', ico: '▲', group: '数据槽', slot: true, defaults: () => ({ id: blockUid(), type: 'chart', asset: 'cockpit.trend', height: 240 }) },
  { type: 'table', label: '表格槽', sub: '引用资产注册表', ico: '▦', group: '数据槽', slot: true, defaults: () => ({ id: blockUid(), type: 'table', asset: 'cockpit.top_opps' }) },
  { type: 'image', label: '图片', sub: '图片地址 / 上传产物', ico: '🖼', group: '媒体', deco: true, defaults: () => ({ id: blockUid(), type: 'image', src: '' }) },
  { type: 'divider', label: '分割线', sub: '版式', ico: '—', group: '版式', deco: true, defaults: () => ({ id: blockUid(), type: 'divider' }) },
]

export function blockDef(type: string): BlockDef | undefined {
  return BLOCK_DEFS.find((d) => d.type === type)
}

export const SPAN_OPTS = [12, 8, 6, 4] as const
export const spanLabel = (s: number) => ({ 12: '整行', 8: '2/3', 6: '半行', 4: '1/3' }[s] || '整行')

/* ───────────── 内核 ───────────── */

export function useArtifactKernel(initial: ArtifactBlock[] = []) {
  const blocks = ref<ArtifactBlock[]>(initial.map(ensureId))
  const selectionId = ref<string>('')
  const history = ref<string[]>([])
  const future = ref<string[]>([])

  const canUndo = computed(() => history.value.length > 0)
  const canRedo = computed(() => future.value.length > 0)
  const selectedIndex = computed(() => blocks.value.findIndex((b) => b.id === selectionId.value))
  const selectedBlock = computed(() => blocks.value.find((b) => b.id === selectionId.value) || null)

  function ensureId(b: ArtifactBlock): ArtifactBlock {
    if (!b.id) b.id = blockUid()
    return b
  }
  const snap = () => JSON.stringify(blocks.value)
  function commit() {
    history.value.push(snap())
    if (history.value.length > 60) history.value.shift()
    future.value = []
  }
  function restore(json: string) {
    blocks.value = (JSON.parse(json) as ArtifactBlock[]).map(ensureId)
    selectionId.value = ''
  }

  function select(id: string) {
    selectionId.value = id
  }

  function insert(defType: string, index?: number) {
    const def = BLOCK_DEFS.find((d) => d.type === defType)
    if (!def) return
    const blk = ensureId(def.defaults())
    blocks.value.splice(index ?? blocks.value.length, 0, blk)
    commit()
    selectionId.value = blk.id!
  }

  function move(id: string, to: number) {
    const from = blocks.value.findIndex((b) => b.id === id)
    if (from < 0 || to < 0 || from === to) return
    const [n] = blocks.value.splice(from, 1)
    blocks.value.splice(to, 0, n)
    commit()
  }

  function moveRel(id: string, dir: -1 | 1) {
    const i = blocks.value.findIndex((b) => b.id === id)
    const j = i + dir
    if (i < 0 || j < 0 || j >= blocks.value.length) return
    ;[blocks.value[i], blocks.value[j]] = [blocks.value[j], blocks.value[i]]
    commit()
  }

  function remove(id: string) {
    blocks.value = blocks.value.filter((b) => b.id !== id)
    if (selectionId.value === id) selectionId.value = ''
    commit()
  }

  function duplicate(id: string) {
    const i = blocks.value.findIndex((b) => b.id === id)
    if (i < 0) return
    const copy = ensureId(JSON.parse(JSON.stringify(blocks.value[i])) as ArtifactBlock)
    blocks.value.splice(i + 1, 0, copy)
    commit()
    selectionId.value = copy.id!
  }

  function setSpan(id: string, span: number) {
    const b = blocks.value.find((x) => x.id === id)
    if (!b) return
    b.span = span === 12 ? undefined : span
    commit()
  }

  function replaceAll(next: ArtifactBlock[], { history: keepHistory = true } = {}) {
    if (keepHistory && blocks.value.length) history.value.push(snap())
    blocks.value = next.map(ensureId)
    if (!keepHistory) {
      history.value = []
      future.value = []
    }
    selectionId.value = ''
  }

  function undo() {
    if (!history.value.length) return
    future.value.push(snap())
    restore(history.value.pop()!)
  }
  function redo() {
    if (!future.value.length) return
    history.value.push(snap())
    restore(future.value.pop()!)
  }

  return {
    blocks, selectionId, selectedBlock, selectedIndex, canUndo, canRedo,
    select, insert, move, moveRel, remove, duplicate, setSpan, replaceAll,
    undo, redo, commit,
  }
}

/* ───────────── 画布样例渲染器（house 风格；样例数据不进存库 blocks） ───────────── */

const esc = (s: unknown) =>
  String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))

/** 已知章节键的示例正文（与趋势契约对齐；其他键回落通用示例） */
const PROSE_SAMPLE: Record<string, string> = {
  weekly: '本周新增商机 18 条，环比上升 28.6%，为近八周最高单周水平。其中 Orion 平台贡献 9 条，Polaris 7 条。新增配置 27 份，集中在 4U 与 2U 两种形态。',
  monthly: '本月累计新增商机 61 条，环比增长 14.2%。周度节奏上，第 2 周为低谷（9 条），月末两周连续回升。',
  half_year: '拉长到半年窗口，商机总量呈稳步爬升态势：从 4 月的 79 条增至 9 月的 96 条，累计增幅 21.5%。Orion 平台占比稳定在 45%~52% 区间。',
  platform: '平台格局上，Orion 以 45% 的半年占比居首，Polaris 38% 次之且差距持续收窄；Intel 平台占 12%，主要服务存量客户替换。',
  chassis: '机箱形态方面，4U 机型以 47% 的占比保持第一，2U 占 39% 且在密度敏感场景中增长最快；5U 与工作站形态合计 14%。',
  top_sales: '半年维度看，王晓明以 38 条新增商机居首，李芸（31 条）、张伟（27 条）分列二三位，前三名合计贡献 46% 的新增商机。',
  insights: '需求侧三个信号值得注意：推理一体机需求连续三月上升；Polaris 平台增速显著；头部销售集中度提高，可推动标准化方案包下沉。',
}
const genericProse = (title: string) =>
  `本节「${title}」为数据槽：渲染时由 AI 答复的对应章节填入，此处仅为版式示例。图表与文字同源取数，口径由报告数据范围统一约束。`

const KPI_SAMPLE: Record<string, { v: string; u: string; d?: string }> = {
  total_opps: { v: '316', u: '条' },
  total_configs: { v: '1,024', u: '份' },
  new_opps: { v: '18', u: '条', d: '↑ 28.6%' },
  new_configs: { v: '27', u: '份', d: '↑ 12.5%' },
}

function chartPlaceholder(assetId: string): string {
  const kind = (assetId || '').split('.')[1] || 'trend'
  if (kind === 'dist' || kind === 'chassis_dist') {
    return `<svg viewBox="0 0 320 150"><circle cx="160" cy="76" r="50" fill="none" stroke="#E5E7EB" stroke-width="22"/><circle cx="160" cy="76" r="50" fill="none" stroke="#1668C0" stroke-width="22" stroke-dasharray="141 314" transform="rotate(-90 160 76)" stroke-linecap="round"/><circle cx="160" cy="76" r="50" fill="none" stroke="#5FA16F" stroke-width="22" stroke-dasharray="119 314" stroke-dashoffset="-145" transform="rotate(-90 160 76)" stroke-linecap="round"/><circle cx="160" cy="76" r="50" fill="none" stroke="#D0A23C" stroke-width="22" stroke-dasharray="38 314" stroke-dashoffset="-268" transform="rotate(-90 160 76)" stroke-linecap="round"/><text x="160" y="72" text-anchor="middle" font-size="19" font-weight="700" fill="#1668C0">135</text><text x="160" y="90" text-anchor="middle" font-size="9" fill="#9CA3AF">样例</text></svg>`
  }
  if (kind === 'sales_rank') {
    const rows: [string, number, string][] = [['王晓明', 38, '#1668C0'], ['李芸', 31, '#3F83D6'], ['张伟', 27, '#6EA3E0'], ['其他 11 人', 62, '#C9D8EC']]
    return `<svg viewBox="0 0 320 150">${rows.map((r, i) => `<text x="8" y="${26 + i * 32}" font-size="10" fill="#6B7280">${r[0]}</text><rect x="72" y="${16 + i * 32}" width="${r[1] * 3.2}" height="14" rx="7" fill="${r[2]}"/><text x="${78 + r[1] * 3.2}" y="${27 + i * 32}" font-size="10" font-weight="600" fill="#414B5C">${r[1]}</text>`).join('')}</svg>`
  }
  if (kind === 'model_trend') {
    const cells = [[0, 0, 150, 60], [152, 0, 166, 60], [0, 62, 96, 84], [98, 62, 120, 84], [220, 62, 98, 84], [0, 148, 318, 40]]
    return `<svg viewBox="0 0 320 150">${cells.map((c, i) => `<rect x="${c[0]}" y="${c[1]}" width="${c[2]}" height="${c[3]}" rx="5" fill="${i % 2 ? '#C9D8EC' : '#E1EAF5'}"/><text x="${c[0] + 8}" y="${c[1] + 16}" font-size="9" fill="#6B7280">机型 Top${i + 1}</text>`).join('')}</svg>`
  }
  const bars = [42, 35, 46, 30, 38, 52, 61, 55, 68, 74, 82, 96]
  const line = bars.map((v, i) => `${18 + i * 24},${132 - v * 0.95}`).join(' ')
  return `<svg viewBox="0 0 320 150"><defs><linearGradient id="aecg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1668C0" stop-opacity=".28"/><stop offset="1" stop-color="#1668C0" stop-opacity=".02"/></linearGradient></defs>${bars.map((v, i) => `<rect x="${10 + i * 24}" y="${132 - v * 0.95}" width="13" height="${v * 0.95}" rx="4" fill="#C9D8EC" opacity=".6"/>`).join('')}<polygon points="18,132 ${line} 294,132" fill="url(#aecg)"/><polyline points="${line}" fill="none" stroke="#1668C0" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`
}

const daysText = (blk: ArtifactBlock) =>
  blk.params && blk.params.days ? `固定 ${blk.params.days} 天` : '跟随数据范围'

const slotChip = (txt: string) => `<span class="aec-slot-chip">${esc(txt)}</span>`

/** markdown 极简子集（加粗/行内码）——画布示意；真实渲染走后端 _markdown_to_html */
const inlineMd = (t: string) =>
  esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`(.+?)`/g, '<code>$1</code>')

/**
 * 区块 → 画布 HTML（house 视觉的客户端镜像）。注意：这里是编辑示意，
 * 真实渲染（取数/echarts/markdown 全量/PDF）以后端 artifact_render 为准。
 */
export function renderBlockHtml(blk: ArtifactBlock, assets: ChartAssetMeta[]): string {
  const assetName = (id?: string) => assets.find((a) => a.id === id)?.name || id || '未选资产'
  const t = blk.type
  if (t === 'title') {
    const ac = typeof blk.accent === 'string' && blk.accent ? blk.accent : ''
    const acStyle = ac ? ` style="border-color:${esc(ac)}"` : ''
    const acTxt = ac ? ` style="color:${esc(ac)}"` : ''
    return `<div class="aec-brandline"${acStyle}><span class="aec-brand"${acTxt}>${esc(blk.brand_name || 'CPQ PLATFORM')}</span><span class="aec-meta">${esc(blk.brand_tag || 'AI 办公室 · 工作流输出')}</span></div><div class="aec-hero"><h1 data-edit>${esc(blk.title || '（报告标题 · 留空跟随文档卡）')}</h1><span class="aec-accent"></span><div class="aec-hero-meta"><span>📊 数据范围 · 渲染时按文档卡</span><span>🗂 模板预览</span></div></div>`
  }
  if (t === 'heading') {
    return `<div class="aec-sec-title"><span class="tt" data-edit>${esc(blk.title || '小节标题')}</span><span class="rule"></span></div>`
  }
  if (t === 'callout') {
    const tone = blk.tone || 'blue'
    const ico = tone === 'green' ? '✅' : tone === 'amber' ? '⚠️' : '💡'
    const titleHtml = blk.co_title ? `<div class="aec-co-title" data-edit>${esc(blk.co_title)}</div>` : ''
    return `<div class="aec-callout tone-${esc(tone)}"><span class="ci">${ico}</span><div>${titleHtml}<div class="aec-co-body" data-edit>${inlineMd(blk.text || '')}</div></div></div>`
  }
  if (t === 'divider') return '<hr class="aec-divider"/>'
  if (t === 'image') {
    return blk.src
      ? `<img class="aec-img" src="${esc(blk.src)}" alt=""/>`
      : '<div class="aec-imgph">🖼 图片槽 · 在右侧属性填图片地址或上传产物路径</div>'
  }
  if (t === 'text') {
    const src = blk.source || 'answer'
    const titleHtml = blk.title ? `<div class="aec-sec-title"><span class="tt">${esc(blk.title)}</span><span class="rule"></span></div>` : ''
    if (src === 'literal') {
      return `<div class="aec-literal" data-edit>${inlineMd(blk.text || '')}</div>`
    }
    if (src === 'payload') {
      if (!blk.key) {
        return `<div style="position:relative">${slotChip('未绑定')}${titleHtml}<div class="aec-unbound">章节文本槽 · 在右侧「绑定」选择内容来源<br>渲染时由 AI 答复 / payload_map 填入</div></div>`
      }
      const prose = PROSE_SAMPLE[blk.key] || genericProse(blk.title || blk.key)
      return `<div style="position:relative">${slotChip(`payload.${esc(blk.key)}`)}${titleHtml}<div class="aec-text"><p>${esc(prose)}</p></div></div>`
    }
    return `${titleHtml}<div style="position:relative">${slotChip('AI 答复 · markdown')}<div class="aec-text"><p>渲染时 = 输出节点 AI 答复的整段 markdown。此处为版式示意：正文、表格、列表由后端 markdown 渲染器统一排版。</p></div></div>`
  }
  if (t === 'kpi') {
    const catalog: KpiMetricOption[] = assets.find((a) => a.id === blk.asset)?.metrics || []
    const keys = blk.metrics?.length ? blk.metrics.map((m) => m.key) : catalog.map((m) => m.key)
    const cells = keys.map((k) => {
      const s = KPI_SAMPLE[k] || { v: '128', u: '' }
      const label = blk.metrics?.find((m) => m.key === k)?.label || catalog.find((m) => m.key === k)?.label || k
      return `<div class="aec-kpi"><div class="k"><i></i>${esc(label)}</div>${s.d ? `<span class="d up">${s.d}</span>` : ''}<div class="vrow"><span class="v">${s.v}</span><span class="u">${s.u}</span></div></div>`
    }).join('')
    return `<div style="position:relative">${slotChip(`{kpi:${esc(blk.asset)}} · ${daysText(blk)}`)}<div class="aec-kpi-row">${cells}</div></div>`
  }
  if (t === 'chart') {
    return `<div style="position:relative">${slotChip(`{chart:${esc(blk.asset)}} · ${daysText(blk)}`)}<div class="aec-chart" style="height:${blk.height || 240}px"><span class="cap">${esc(assetName(blk.asset))}</span>${chartPlaceholder(blk.asset || '')}<span class="wm">编辑示意 · 正式=echarts SSR</span></div></div>`
  }
  if (t === 'table') {
    const rows = [
      ['2026.04', '23', '17', '2', '42'], ['2026.05', '21', '15', '3', '39'], ['2026.06', '26', '19', '1', '46'],
      ['2026.07', '24', '21', '2', '47'], ['合计', '96', '68', '8', '172'],
    ]
    .map((r, i) => `<tr class="${i === 4 ? 'sum' : ''}">${r.map((c) => `<td>${c}</td>`).join('')}</tr>`)
    .join('')
    return `<div style="position:relative">${slotChip(`{table:${esc(blk.asset)}} · ${daysText(blk)}`)}<table class="aec-table"><thead><tr><th>月份</th><th>Orion</th><th>Polaris</th><th>Intel</th><th>合计</th></tr></thead><tbody>${rows}</tbody></table></div>`
  }
  if (t === 'fields') {
    return `<div style="position:relative">${slotChip(`fields.${esc(blk.key || '')}`)}<div class="aec-unbound">结构化字段表 · 渲染时按 payload.${esc(blk.key || '')} 的字典形状展开两列表</div></div>`
  }
  return `<div class="aec-unbound">未知区块类型：${esc(t)}</div>`
}

/** 指示条/图层面用的区块显示名 */
export function blockDisplayName(blk: ArtifactBlock, assets: ChartAssetMeta[]): string {
  const def = BLOCK_DEFS.find((d) => d.type === blk.type)
  if (blk.type === 'text') {
    if ((blk.source || 'answer') === 'payload') return blk.key ? `章节槽 · ${blk.key}` : '章节槽 · 未绑定'
    if (blk.source === 'literal') return '固定文案'
    return 'AI 答复槽'
  }
  if (blk.asset) return `${def?.label || blk.type} · ${assets.find((a) => a.id === blk.asset)?.name || blk.asset}`
  if (blk.type === 'title') return blk.title || '报告抬头'
  if (blk.type === 'heading') return `小节题 · ${blk.title || ''}`
  if (blk.type === 'callout') return `提示卡 · ${blk.co_title || '提示'}`
  return def?.label || blk.type
}

/** 新建模板骨架（对齐旧编辑器默认：抬头 + KPI + AI 答复槽） */
export function skeletonBlocks(): ArtifactBlock[] {
  return [
    { id: blockUid(), type: 'title' },
    { id: blockUid(), type: 'kpi', asset: 'cockpit.kpi' },
    { id: blockUid(), type: 'text', source: 'answer', title: 'AI 分析结论' },
  ]
}
