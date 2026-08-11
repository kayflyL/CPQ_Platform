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

function buildNode(el: Element, depth: number, metaMap: Map<string, DrawingLayerMeta>, svg: SVGSVGElement): SvgLayerNode | null {
  const id = el.getAttribute('id') || ''
  const tag = el.tagName
  if (depth >= MAX_DEPTH && tag === 'g') return null
  const meta = id ? metaMap.get(id) : undefined
  const children: SvgLayerNode[] = []
  if (tag === 'g' || tag === 'svg') {
    for (const c of Array.from(el.children)) {
      if (SKIP_TAGS.has(c.tagName)) continue
      const n = buildNode(c, depth + 1, metaMap, svg)
      if (n) children.push(n)
    }
  }
  const bbox = elementBBox(el, svg)
  const meaningful = id || (tag === 'g' && children.length > 0) || bbox != null
  if (!meaningful) return null
  return {
    id,
    tag,
    name: meta?.name || id,
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
