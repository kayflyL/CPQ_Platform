<script setup lang="ts">
/** 兼容性规则影响拓扑图（只读）—— 从 active 规则的 WHEN/THEN 推出节点与依赖边。
 *  节点 = 配件 category（kp.X）或上下文维度（商机/机型）；边 = require 必配 / derive 派生 / exclude 互斥自环 / filter 过滤。
 *  按依赖拓扑深度自动分层布局（零依赖，不用 dagre）。配色复用 selectionConfig.getCategoryStyle。
 *  只读：不在图上编辑（编辑走 CompatibilityRuleEditor 条件构建器）；可拖拽/缩放查看。 */
import { computed, markRaw } from 'vue'
import { VueFlow, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import ImpactNode from './ImpactNode.vue'
import type { CompatibilityRule } from '@/api/compatibilityRules'

const props = defineProps<{ rules: CompatibilityRule[] }>()
const nodeTypes: any = markRaw({ impact: ImpactNode })

/** kp.GPU.qty → GPU；非 kp. 前缀原样返回 */
function parseCat(target?: string): string {
  if (!target) return ''
  return target.startsWith('kp.') ? target.slice(3) : target
}
/** 从 WHEN 条件树提取触发源 category（kp. 提品类；opportunity./config. 归「商机维度」） */
function extractCats(when: any): string[] {
  if (!when) return []
  const conds: any[] = []
  if (Array.isArray(when.all)) conds.push(...when.all)
  if (Array.isArray(when.any)) conds.push(...when.any)
  if (when.field) conds.push(when)
  const cats = new Set<string>()
  for (const c of conds) {
    const f: string = c.field || ''
    if (f.startsWith('kp.')) cats.add(f.split('.')[1])
    else if (f.startsWith('opportunity.') || f.startsWith('config.')) cats.add('商机维度')
  }
  return [...cats]
}

const EDGE_STYLE: Record<string, string> = {
  require: '#1677ff', derive: '#36cfcf', recommend: '#52c41a', exclude: '#ff4d4f', filter: '#fa8c16',
}

const graph = computed(() => {
  const nodesMap = new Map<string, { id: string; label: string; note?: string }>()
  const edges: any[] = []
  const ensure = (label: string, note?: string) => {
    if (!nodesMap.has(label)) nodesMap.set(label, { id: label, label, note })
    return label
  }

  for (const r of props.rules) {
    if (r.status !== 'active') continue
    const then: any = r.body?.then
    if (!then) continue
    const action = then.action
    const triggers = extractCats(r.body?.when)

    if (action === 'require' || action === 'derive' || action === 'recommend') {
      const tgt = ensure(parseCat(then.target))
      for (const t of triggers) {
        const src = ensure(t)
        if (!src || src === tgt) continue
        edges.push({
          id: `e-${r.id}-${src}-${tgt}`, source: src, target: tgt,
          label: action === 'require' ? '必配' : action === 'derive' ? '派生' : '推荐',
          animated: action === 'derive',
          style: { stroke: EDGE_STYLE[action], strokeWidth: 1.5 },
          labelStyle: { fill: EDGE_STYLE[action], fontWeight: 600 },
          labelBgStyle: { fill: 'rgba(255,255,255,.85)' },
        })
      }
    } else if (action === 'exclude') {
      const cat = ensure(parseCat(then.target))
      // 互斥：自环边表示「同型号不混搭」
      edges.push({ id: `e-${r.id}-x`, source: cat, target: cat, label: '不混搭', style: { stroke: EDGE_STYLE.exclude, strokeWidth: 1.5 }, labelStyle: { fill: EDGE_STYLE.exclude } })
    } else if (action === 'filter') {
      const src = ensure('商机维度', 'ctx')
      const tgt = ensure('候选机型', 'ctx')
      edges.push({ id: `e-${r.id}-f`, source: src, target: tgt, label: '过滤', animated: true, style: { stroke: EDGE_STYLE.filter, strokeWidth: 1.5 }, labelStyle: { fill: EDGE_STYLE.filter } })
    }
  }

  // 按依赖拓扑深度分层（左→右）
  const ids = [...nodesMap.values()].map(n => n.id)
  const inDeg: Record<string, number> = {}
  const outAdj: Record<string, string[]> = {}
  for (const id of ids) { inDeg[id] = 0; outAdj[id] = [] }
  for (const e of edges) {
    if (e.source !== e.target && inDeg[e.target] !== undefined) { inDeg[e.target]++; outAdj[e.source].push(e.target) }
  }
  const depth: Record<string, number> = {}
  const queue: [string, number][] = ids.filter(id => inDeg[id] === 0).map(id => [id, 0])
  while (queue.length) {
    const [id, d] = queue.shift()!
    if (depth[id] !== undefined && depth[id] >= d) continue
    depth[id] = d
    for (const nxt of outAdj[id]) queue.push([nxt, d + 1])
  }
  for (const id of ids) if (depth[id] === undefined) depth[id] = 0
  const cols: Record<number, string[]> = {}
  for (const id of ids) (cols[depth[id]] = cols[depth[id]] || []).push(id)
  const pos: Record<string, { x: number; y: number }> = {}
  for (const [d, colIds] of Object.entries(cols)) {
    const x = Number(d) * 240
    colIds.forEach((id, i) => { pos[id] = { x, y: i * 78 } })
  }
  const nodes = ids.map(id => ({
    id, type: 'impact', position: pos[id] || { x: 0, y: 0 },
    data: { label: nodesMap.get(id)!.label, note: nodesMap.get(id)!.note },
  }))
  return { nodes, edges: edges as Edge[] }
})
</script>

<template>
  <div class="impact-graph">
    <div v-if="!graph.nodes.length" class="impact-empty">
      暂无可视化关系——规则需含 require / derive / exclude / filter 动作，且 WHEN 指向具体品类
    </div>
    <VueFlow
      v-else
      :nodes="graph.nodes"
      :edges="graph.edges"
      :node-types="nodeTypes"
      :fit-view-on-init="true"
      :nodes-connectable="false"
      :zoom-on-scroll="true"
    >
      <Background :gap="18" :size="1" />
      <Controls :show-interactive="false" />
    </VueFlow>
  </div>
</template>

<style scoped>
.impact-graph {
  width: 100%; height: 100%; min-height: 420px;
  border: 1px solid var(--cpq-overlay-a15, rgba(0, 0, 0, .08));
  border-radius: 12px;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, .4));
  overflow: hidden;
}
.impact-empty {
  display: flex; align-items: center; justify-content: center; height: 100%;
  color: var(--cpq-text-muted, #86909c); font-size: 13px; padding: 0 24px; text-align: center;
}
</style>
