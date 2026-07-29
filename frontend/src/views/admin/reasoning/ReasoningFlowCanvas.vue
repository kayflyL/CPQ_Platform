<script setup lang="ts">
/** 推理流可视化编排画布（策略中心·需求分析域）—— P2 vue flow 版。
 *  P2.1：VueFlow + Background/Controls/MiniMap；拖拽/连线持久化。
 *  P2.2：加节点 palette（dropdown 选 type → addNodes）+ 删节点（Backspace 键）+ watch 长度持久化；
 *        onNodeClick 传 nodeType（Drawer 按 type 渲染 condition/llm）。
 *  P2.3：condition 节点 + executor 图驱动（后端，本组件不涉及）。 */
import { ref, shallowRef, onMounted, markRaw, watch } from 'vue'
import { VueFlow, useVueFlow, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { message } from 'ant-design-vue'
import { reasoningFlowApi, type ReasoningFlow as RFlow } from '@/api/reasoningFlow'
import ReasoningNodeVf from './ReasoningNodeVf.vue'
import ReasoningNodeDrawer from './ReasoningNodeDrawer.vue'

const CFG_TYPES = ['extract', 'select_baseline', 'match_kp', 'condition', 'llm']
const NODE_TYPES = [
  { type: 'extract', label: '需求理解 extract' },
  { type: 'select_baseline', label: '机型选型 select_baseline' },
  { type: 'match_kp', label: '配件匹配 match_kp' },
  { type: 'compose', label: '组合方案 compose' },
  { type: 'review', label: '方案就绪 review' },
  { type: 'condition', label: '条件分支 condition' },
  { type: 'clarity_check', label: '明确度判定 clarity_check' },
  { type: 'ask_user', label: '反问补全 ask_user' },
  { type: 'budget_check', label: '预算校验 budget_check' },
  { type: 'llm', label: 'LLM 节点 llm' },
]

const nodes = ref<any[]>([])
const edges = shallowRef<Edge[]>([])
const flow = ref<RFlow | null>(null)
const loading = ref(false)
const nodeTypes = markRaw({ rf: ReasoningNodeVf }) as any

const drawerOpen = ref(false)
const drawerNodeKey = ref<string | null>(null)
const drawerNodeType = ref<string | null>(null)
const drawerConfig = ref<Record<string, any> | null>(null)

const { onConnect, onNodeDragStop, onNodeClick, onEdgeClick } = useVueFlow()

async function load() {
  loading.value = true
  try {
    const r = await reasoningFlowApi.get()
    flow.value = r.flow
    if (!r.flow) { message.warning('无 active 推理流'); return }
    nodes.value = r.flow.graph.nodes.map((n: any) => ({
      id: n.id,
      type: 'rf',
      position: n.position,
      data: { stepType: n.type, label: n.label, configurable: CFG_TYPES.includes(n.type) },
    }))
    edges.value = r.flow.graph.edges.map((e: any): Edge => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle,
      targetHandle: e.target_handle,
      animated: true,
    }))
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

let persistTimer: ReturnType<typeof setTimeout> | null = null
async function persistGraph() {
  if (!flow.value) return
  const g = {
    nodes: nodes.value.map(n => ({
      id: n.id,
      type: n.data?.stepType || 'unknown',
      label: n.data?.label || n.id,
      position: n.position,
    })),
    edges: edges.value.map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      source_handle: e.sourceHandle ?? null,
      target_handle: e.targetHandle ?? null,
    })),
  }
  try {
    await reasoningFlowApi.updateGraph(g)
  } catch (e: any) {
    message.error('持久化失败：' + (e.response?.data?.detail || e.message))
  }
}
function debouncePersist() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(persistGraph, 600)
}

function addNode(type: string) {
  const sameTypeCount = nodes.value.filter(n => n.data?.stepType === type).length
  const id = `${type}_${sameTypeCount + 1}`
  const meta = NODE_TYPES.find(n => n.type === type)
  nodes.value = [...nodes.value, {
    id,
    type: 'rf',
    position: { x: 250 + sameTypeCount * 30, y: 120 + sameTypeCount * 40 },
    data: { stepType: type, label: meta?.label || type, configurable: CFG_TYPES.includes(type) },
  }]
  debouncePersist()
}

onConnect(params => {
  edges.value = [...edges.value, {
    id: `e${edges.value.length + 1}_${params.source}_${params.target}`,
    source: params.source,
    target: params.target,
    sourceHandle: params.sourceHandle,
    targetHandle: params.targetHandle,
    animated: true,
  } as Edge]
  debouncePersist()
})
onNodeDragStop(() => debouncePersist())
onNodeClick(({ node }) => {
  // 单击节点开配置抽屉（所有节点；抽屉内「删除节点」按钮删）
  drawerNodeKey.value = node.id
  drawerNodeType.value = node.data?.stepType || node.data?.type
  drawerConfig.value = (flow.value?.node_configs as Record<string, any> | undefined)?.[node.id] || null
  drawerOpen.value = true
})
onEdgeClick(({ edge }) => {
  // 点边即删（连线易重建，无需确认）
  edges.value = edges.value.filter(e => e.id !== edge.id)
  debouncePersist()
  message.success('已删除连线')
})
function onRemove(nodeKey: string) {
  nodes.value = nodes.value.filter(n => n.id !== nodeKey)
  edges.value = edges.value.filter(e => e.source !== nodeKey && e.target !== nodeKey)
  drawerOpen.value = false
  debouncePersist()
  message.success('已删除节点')
}

// 加/删节点/边 → 持久化（长度变化触发；拖拽 position 不变长度，靠 onNodeDragStop）
watch(() => nodes.value.length, () => debouncePersist())
watch(() => edges.value.length, () => debouncePersist())

onMounted(load)
function onSaved() { load() }
</script>

<template>
  <div class="rf-canvas">
    <div class="rf-toolbar">
      <span class="rf-tip">拖节点改位置 · 拖锚点连线 · 点边删连线 · 单击节点开配置（抽屉内「删除节点」）</span>
      <div class="rf-actions">
        <a-dropdown>
          <a-button size="small" type="primary" ghost>+ 加节点</a-button>
          <template #overlay>
            <a-menu>
              <a-menu-item v-for="n in NODE_TYPES" :key="n.type" @click="addNode(n.type)">{{ n.label }}</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
        <span v-if="flow" class="rf-version">v{{ flow.version }} · {{ flow.status }}</span>
      </div>
    </div>
    <a-spin :spinning="loading">
      <div class="rf-flow-wrap">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          fit-view-on-init
          :min-zoom="0.3"
          :max-zoom="2"
          delete-key-code="Backspace"
        >
          <Background :gap="20" :size="1" pattern-color="rgba(127,127,127,0.18)" />
          <Controls />
          <MiniMap pannable zoomable />
        </VueFlow>
      </div>
    </a-spin>
    <ReasoningNodeDrawer v-model:open="drawerOpen" :node-key="drawerNodeKey" :node-type="drawerNodeType" :initial-config="drawerConfig" @saved="onSaved" @remove="onRemove" />
  </div>
</template>

<style scoped>
.rf-canvas { display: flex; flex-direction: column; gap: 10px; }
.rf-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0 2px; gap: 12px; }
.rf-tip { font-size: 12px; color: var(--cpq-text-muted); flex: 1; }
.rf-actions { display: flex; align-items: center; gap: 10px; }
.rf-version {
  font-size: 11px; color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-w8); padding: 1px 8px; border-radius: 8px;
  font-variant-numeric: tabular-nums;
}
.rf-flow-wrap {
  width: 100%; height: 520px;
  border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-overlay-w3, transparent);
  overflow: hidden;
}
</style>
