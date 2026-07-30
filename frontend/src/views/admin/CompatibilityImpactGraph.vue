<script setup lang="ts">
/** 兼容性规则因果流图（只读）—— 编辑态展示单条规则的运行逻辑。
 *
 *  三列因果流（左→右）：
 *    WHEN 条件  ──→  动作枢纽  ──→  THEN 结果
 *  把每条规则的触发条件（字段/操作符/值）和执行结果（派生算式/必配目标/赋值…）都明明白白画出，
 *  让用户一眼看清「什么条件 → 触发什么动作 → 产生什么结果」，而非抽象的品类依赖边。
 */
import { computed, markRaw } from 'vue'
import { VueFlow, MarkerType, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import ImpactNode from './ImpactNode.vue'
import type { CompatibilityRule } from '@/api/compatibilityRules'
import {
  RULE_TYPE_MAP, RULE_OP_MAP, FIELD_NS_LABEL, ctxFieldLabel,
  RULE_GRAPH_TEXT as T, excludeText,
} from '@/constants/ruleMeta'

const props = defineProps<{ rules: CompatibilityRule[] }>()
const nodeTypes: any = markRaw({ impact: ImpactNode })

/** 字段路径友好化：kp.GPU.qty→GPU·数量；config.bp_type→配置·背板类型 */
function beautifyField(f?: string): string {
  if (!f) return ''
  const j = T.nsJoin
  if (f.startsWith('kp.')) {
    const parts = f.split('.')
    const cat = parts[1] || ''
    if (parts[2] === 'qty') return [cat, T.qtySuffix].join(j)
    if (parts[2] === 'spec') return [cat, parts[3]].join(j)
    return cat
  }
  if (f.startsWith('config.')) return [FIELD_NS_LABEL.config, ctxFieldLabel('config', f.slice(7))].join(j)
  if (f.startsWith('opportunity.')) return [FIELD_NS_LABEL.opportunity, ctxFieldLabel('opportunity', f.slice(11))].join(j)
  return f
}

/** kp.GPU.qty → GPU；非 kp. 前缀友好化后返回 */
function parseCat(target?: string): string {
  if (!target) return ''
  if (target.startsWith('kp.')) return target.slice(3).split('.')[0]
  return beautifyField(target)
}

type Cond = { field?: string; op?: string; value?: any }
/** 展平 WHEN 条件树为条件数组（all/any/单条） */
function extractConds(when: any): { conds: Cond[]; any: boolean } {
  if (!when) return { conds: [], any: false }
  if (Array.isArray(when.all)) return { conds: when.all, any: false }
  if (Array.isArray(when.any)) return { conds: when.any, any: true }
  if (when.field) return { conds: [when], any: false }
  return { conds: [], any: false }
}

/** THEN 结果节点文本：派生算式 / 必配目标 / 赋值 / 过滤 / 推荐 */
function thenResult(then: any): { title: string; subtitle?: string } {
  switch (then.action) {
    case 'require': {
      const sub: string[] = []
      if (then.min_qty) sub.push(`${RULE_OP_MAP['>=']} ${then.min_qty}`)
      if (then.spec_constraint) sub.push(Object.entries(then.spec_constraint).map(([k, v]) => `${k}${T.eq}${v}`).join(','))
      return { title: parseCat(then.target), subtitle: [T.requirePrefix, ...sub].join(T.listSep) }
    }
    case 'exclude':
      return { title: parseCat(then.target), subtitle: excludeText(then.unique_field) }
    case 'derive':
      if (then.field && 'value' in then) return { title: beautifyField(then.field), subtitle: `${T.assignEq}${then.value}` }
      return { title: parseCat(then.target), subtitle: `${beautifyField(then.basis)}${T.divideBy}${then.per}${T.listSep}${T.round[then.round] || ''}` }
    case 'filter':
      return { title: T.filterScope[then.scope] || then.scope, subtitle: `${beautifyField(then.field)} ${RULE_OP_MAP[then.op] || then.op} ${then.value}` }
    case 'recommend':
      return { title: parseCat(then.target), subtitle: T.recommendLabel }
    default:
      return { title: then.action }
  }
}

const X = { when: 0, action: 200, then: 410 }
const NODE_H = 56
const GAP = 16
const ROW = NODE_H + GAP
const FLOW_GAP = 56

const graph = computed(() => {
  const nodes: any[] = []
  const edges: any[] = []
  let cursorY = 0

  for (const r of props.rules) {
    if (r.status !== 'active') continue
    const then: any = r.body?.then
    if (!then) continue
    const action = then.action
    const typeDef = RULE_TYPE_MAP[action as keyof typeof RULE_TYPE_MAP]
    const color = typeDef?.hex ?? RULE_TYPE_MAP.require.hex
    const { conds, any: isAny } = extractConds(r.body?.when)

    // ---- WHEN 条件节点 ----
    const whenNodes: { title: string; subtitle?: string }[] = []
    if (conds.length === 0) {
      whenNodes.push({ title: T.alwaysActive, subtitle: T.noCondition })
    } else {
      for (const c of conds) {
        whenNodes.push({ title: beautifyField(c.field), subtitle: `${RULE_OP_MAP[c.op || '=='] || c.op} ${c.value}` })
      }
    }

    // ---- THEN 结果节点 ----
    const result = thenResult(then)

    // ---- 三列各自垂直居中 ----
    const maxCount = Math.max(whenNodes.length, 1)
    const flowHeight = maxCount * ROW
    const centerY = cursorY + flowHeight / 2

    const whenStartY = centerY - (whenNodes.length * ROW) / 2
    const whenIds: string[] = []
    whenNodes.forEach((n, i) => {
      const id = `w-${r.id}-${i}`
      nodes.push({
        id, type: 'impact', position: { x: X.when, y: whenStartY + i * ROW + (ROW - NODE_H) / 2 },
        data: { kind: 'when', title: n.title, subtitle: n.subtitle },
      })
      whenIds.push(id)
    })

    const aId = `a-${r.id}`
    nodes.push({
      id: aId, type: 'impact', position: { x: X.action, y: centerY - NODE_H / 2 },
      data: { kind: 'action', title: r.name, badge: typeDef?.label || action, accent: color },
    })

    const tId = `t-${r.id}`
    nodes.push({
      id: tId, type: 'impact', position: { x: X.then, y: centerY - NODE_H / 2 },
      data: { kind: 'then', title: result.title, subtitle: result.subtitle, accent: color },
    })

    // ---- 边：条件 → 动作（灰虚线）；动作 → 结果（动作色实线带箭头）----
    for (const wid of whenIds) {
      edges.push({
        id: `e-${wid}-${aId}`, source: wid, target: aId, type: 'smoothstep',
        style: { stroke: '#b6bcc4', strokeWidth: 1.5, strokeDasharray: '4 3' },
      })
    }
    if (isAny && whenIds.length > 1) {
      edges.push({
        id: `e-${aId}-label`, source: whenIds[0], target: aId, label: T.matchAny, labelStyle: { fill: RULE_TYPE_MAP.filter.hex, fontWeight: 600, fontSize: 10 }, labelBgStyle: { fill: 'rgba(255,255,255,.85)' }, type: 'smoothstep', style: { stroke: 'transparent' },
      })
    }
    edges.push({
      id: `e-${aId}-${tId}`, source: aId, target: tId, type: 'smoothstep',
      animated: action === 'derive' || action === 'filter',
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 18, height: 18 },
      style: { stroke: color, strokeWidth: 2 },
    })

    cursorY += flowHeight + FLOW_GAP
  }

  return { nodes, edges: edges as Edge[] }
})
</script>

<template>
  <div class="impact-graph">
    <div v-if="!graph.nodes.length" class="impact-empty">{{ T.empty }}</div>
    <VueFlow
      v-else
      :nodes="graph.nodes"
      :edges="graph.edges"
      :node-types="nodeTypes"
      :fit-view-on-init="true"
      :nodes-connectable="false"
      :zoom-on-scroll="true"
      :pan-on-scroll="false"
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
