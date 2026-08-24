/**
 * SVG 图层解析 / 编辑工具 —— 把 Figma 导出的分层 SVG 变成可编辑的图层资产。
 *
 * 图层粒度：svg 直接子元素为一级，递归 g 分组最多 8 层（覆盖本机型整树；编辑包裹层不会截断子层）。
 * 坐标一律用 SVG 自身坐标系（getBBox / viewBox），与热区/部件存储统一。
 */
import type { DrawingLayerMeta } from '@/api/serverDrawing'

export interface SvgLayerNode {
  id: string
  /** 元素标签名：svg / g / rect / path ... */
  tag: string
  /** 用户重命名后的名称（无则回退到 id 或自动建议名） */
  name: string
  elCount: number
  bbox: { x: number; y: number; w: number; h: number } | null
  children: SvgLayerNode[]
  el: Element
  visible: boolean
  locked: boolean
  opacity: number
}

const MAX_DEPTH = 8
const SKIP_TAGS = new Set(['defs', 'clipPath', 'mask', 'pattern', 'marker', 'title', 'desc', 'metadata'])

/** 元素 bbox（SVG 世界坐标）。getBBox 对未渲染元素不可靠时回退 getBoundingClientRect 换算。 */
export function elementBBox(el: Element, svg: SVGSVGElement): { x: number; y: number; w: number; h: number } | null {
  try {
    const g = el as SVGGraphicsElement
    if (typeof g.getBBox === 'function') {
      const b = g.getBBox()
      if (b.width > 0 || b.height > 0) {
        return { x: b.x, y: b.y, w: b.width, h: b.height }
      }
    }
  } catch { /* 某些元素不支持 getBBox */ }
  try {
    const r = (el as Element).getBoundingClientRect()
    if (r.width === 0 && r.height === 0) return null
    const vb = svg.viewBox.baseVal
    const cw = svg.clientWidth || 1
    const ch = svg.clientHeight || 1
    const sx = vb.width / cw
    const sy = vb.height / ch
    const sr = svg.getBoundingClientRect()
    return { x: (r.x - sr.x) * sx + vb.x, y: (r.y - sr.y) * sy + vb.y, w: r.width * sx, h: r.height * sy }
  } catch {
    return null
  }
}

function countEls(el: Element): number {
  let n = 0
  const walk = (e: Element) => {
    for (const c of Array.from(e.children)) {
      if (SKIP_TAGS.has(c.tagName)) continue
      n++
      walk(c)
    }
  }
  walk(el)
  return n
}

/** 无 id 元素内部 id 计数器（每次解析重置，DOM 顺序稳定） */
let anonSeq = 0

function suggestAnonName(el: Element, seq: number): string {
  return el.tagName === 'g' ? `未命名分组 ${seq}` : `未命名形状 ${seq}`
}

function buildNode(el: Element, depth: number, metaMap: Map<string, DrawingLayerMeta>, svg: SVGSVGElement): SvgLayerNode | null {
  // 编辑器选中的瞬态包裹层（data-edit-wrap）不是图层：透传其唯一子元素，避免元素从树里消失
  if (el.hasAttribute('data-edit-wrap')) {
    for (const c of Array.from(el.children)) {
      if (SKIP_TAGS.has(c.tagName)) continue
      const n = buildNode(c, depth, metaMap, svg)
      if (n) return n
    }
    return null
  }
  const rawId = el.getAttribute('id') || ''
  const tag = el.tagName
  if (depth >= MAX_DEPTH && tag === 'g') return null
  const children: SvgLayerNode[] = []
  if (tag === 'g' || tag === 'svg') {
    for (const c of Array.from(el.children)) {
      if (SKIP_TAGS.has(c.tagName)) continue
      const n = buildNode(c, depth + 1, metaMap, svg)
      if (n) children.push(n)
    }
  }
  const bbox = elementBBox(el, svg)
  const meaningful = rawId || (tag === 'g' && children.length > 0) || bbox != null
  if (!meaningful) return null
  // 无 id 元素：分配稳定内部 id 并写回元素（编辑/保存/消费端显隐都按 id 定位）
  const id = rawId || `__anon_${++anonSeq}`
  if (!rawId) el.setAttribute('id', id)
  const meta = metaMap.get(id)
  const anonNo = /^__anon_(\d+)$/.exec(id)
  return {
    id,
    tag,
    name: meta?.name || (anonNo ? suggestAnonName(el, Number(anonNo[1])) : id),
    elCount: countEls(el),
    bbox,
    children,
    el,
    visible: meta?.visible ?? true,
    locked: meta?.locked ?? false,
    opacity: meta?.opacity ?? 1,
  }
}
/** 解析 SVG DOM → 图层树（元数据合并自 metaList） */
export function parseSvgLayers(svg: SVGSVGElement, metaList: DrawingLayerMeta[] = []): SvgLayerNode[] {
  anonSeq = 0
  const metaMap = new Map<string, DrawingLayerMeta>()
  for (const m of metaList || []) if (m.id) metaMap.set(m.id, m)
  const roots: SvgLayerNode[] = []
  for (const c of Array.from(svg.children)) {
    if (SKIP_TAGS.has(c.tagName)) continue
    const n = buildNode(c, 0, metaMap, svg)
    if (n) roots.push(n)
  }
  return roots
}

/** 收集 SVG 内全部元素 id（替换向导比对用） */
export function collectSvgIds(svg: SVGSVGElement): string[] {
  const out = new Set<string>()
  svg.querySelectorAll('[id]').forEach(el => {
    const id = el.getAttribute('id')
    if (id) out.add(id)
  })
  return [...out]
}

/** 序列化当前 SVG DOM（清除编辑态临时样式）→ 字符串，供保存接口清洗落盘 */
export function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.querySelectorAll('*').forEach(el => {
    for (const attr of Array.from(el.attributes)) {
      const n = attr.name
      if (n.startsWith('data-layerselected') || n.startsWith('data-layerhover') || n.startsWith('data-edit-temp')) {
        el.removeAttribute(n)
      }
    }
  })
  return new XMLSerializer().serializeToString(clone)
}

/** 应用图层元数据到 SVG DOM（消费端/编辑端渲染时调用）：visible→display、opacity→透明度 */
export function applyLayerMeta(svg: SVGSVGElement, metaList: DrawingLayerMeta[] = []) {
  for (const m of metaList || []) {
    if (!m.id) continue
    const els = svg.querySelectorAll('#' + cssEscape(m.id))
    for (const el of Array.from(els)) {
      if (m.visible === false) el.setAttribute('display', 'none')
      else if (el.getAttribute('display') === 'none') el.removeAttribute('display')
      if (m.opacity != null) el.setAttribute('opacity', String(m.opacity))
    }
  }
}

function cssEscape(s: string): string {
  return s.replace(/[^a-zA-Z0-9_-]/g, ch => '\\' + ch.charCodeAt(0).toString(16) + ' ')
}

/** 命名模板：按前缀 + 序号生成名称（fan_1、psu_1...），供图层面板批量重命名 */
export const LAYER_NAME_TEMPLATES: { key: string; label: string; prefix: string }[] = [
  { key: 'fan', label: '风扇', prefix: 'fan' },
  { key: 'bay', label: '盘位', prefix: 'bay' },
  { key: 'psu', label: '电源', prefix: 'psu' },
  { key: 'cpu', label: 'CPU', prefix: 'cpu' },
  { key: 'gpu', label: 'GPU', prefix: 'gpu' },
  { key: 'io', label: 'IO/OCP', prefix: 'io' },
  { key: 'bp', label: '背板', prefix: 'bp' },
  { key: 'custom', label: '自定义', prefix: '' },
]

export function templateName(prefix: string, index: number): string {
  return prefix ? prefix + '_' + (index + 1) : ''
}


// ── 配置沙盒：借用 SVG 自身分层，显隐某类硬件图层序列（不重新绘制元素） ──
// Figma 重复元素命名约定：GPU / GPU_2 / GPU_3 …、内存槽 / 内存槽_2 …、CPU 0 / CPU 1。
export type SandboxLayerKind = 'gpu' | 'cpu' | 'dimm' | 'psu' | 'bay'
export const SANDBOX_LAYER_PATTERNS: Record<SandboxLayerKind, RegExp> = {
  gpu: /^GPU(?:_(\d+))?$/,
  cpu: /^CPU (\d+)$/,
  dimm: /^内存槽(?:_(\d+))?$/,
  // 后视图电源分层（ESA24 V3-P 实测：PSU / PSU_2 / PSU_3 / PSU_4，对应 4 槽 3+1 冗余）
  psu: /^PSU(?:_(\d+))?$/,
  // 前视图盘位分层（ESA24 V3-P 实测：3.5英寸硬盘 / _2 ~ _12，共 12 盘位）
  bay: /^3\.5英寸硬盘(?:_(\d+))?$/,
}

/** 收集某类硬件的图层（按 id 序号升序；无后缀基准计 1） */
export function collectLayerSequence(nodes: SvgLayerNode[], kind: SandboxLayerKind): Element[] {
  const re = SANDBOX_LAYER_PATTERNS[kind]
  const found: { el: Element; idx: number }[] = []
  const walk = (list: SvgLayerNode[]) => {
    for (const n of list) {
      const m = re.exec(n.id)
      if (m) found.push({ el: n.el, idx: m[1] != null ? Number(m[1]) : 1 })
      if (n.children.length) walk(n.children)
    }
  }
  walk(nodes)
  return found.sort((a, b) => a.idx - b.idx).map(x => x.el)
}

/** 沙盒图层显隐：显示前 count 个图层、隐藏其余（某 kind 未传（undefined）则不动，防止无沙盒场景下误隐藏） */
export function applySandboxVisibility(tree: SvgLayerNode[], counts: Partial<Record<SandboxLayerKind, number>> | undefined) {
  for (const kind of Object.keys(SANDBOX_LAYER_PATTERNS) as SandboxLayerKind[]) {
    const count = counts?.[kind]
    if (count == null) continue
    for (const [i, el] of collectLayerSequence(tree, kind).entries()) {
      if (i < count) el.removeAttribute('display')
      else el.setAttribute('display', 'none')
    }
  }
}
