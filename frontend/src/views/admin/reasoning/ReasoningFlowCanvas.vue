<script setup lang="ts">
/** 推理流可视化编排画布（策略中心·需求分析域）—— 三栏布局（参考导出模板页 UniverTemplateEditor）：
 *  左节点 palette（点击添加）/ 中 vue flow 画布（编排+连线）/ 右试运行 playground。
 *  P2 vue flow 编排（拖拽/连线/加删节点/配置抽屉）+ 图驱动 executor（后端）。
 *  试运行：输入需求 → 复用线上图执行器（POST /test-run）→ 节点逐步高亮 + 步骤明细 + 候选方案。
 *  三栏而非上下叠/两栏：画布吃滚轮缩放，放下方时下滑找入口会误缩放；左 palette 常驻加节点更顺手。 */
import { ref, shallowRef, onMounted, markRaw, watch, computed } from 'vue'
import { VueFlow, useVueFlow, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { message } from 'ant-design-vue'
import { PlayCircleOutlined, ExclamationCircleOutlined, NodeIndexOutlined } from '@ant-design/icons-vue'
import { reasoningFlowApi, type ReasoningFlow as RFlow } from '@/api/reasoningFlow'
import ReasoningNodeVf from './ReasoningNodeVf.vue'
import ReasoningNodeDrawer from './ReasoningNodeDrawer.vue'
import PlanCard from '@/components/reasoning/PlanCard.vue'
import BomTable from '@/components/BomTable.vue'
import { useTestRun } from '@/composables/useTestRun'
import { buildPlanCfg, type PlanLiveCfg } from '@/composables/usePlanBom'
import { STEP_COPY } from '@/utils/reasoningStepCopy'
import { NODE_IO } from '@/utils/reasoningNodeIo'
import type { Plan } from '@/api/reasoning'

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
/** 左栏 palette 分组（按信息收集 / 判断处理 / 分支控制三环节，参考腾讯元器节点分类） */
const NODE_GROUPS = [
  { name: '信息收集', types: ['extract', 'ask_user'] },
  { name: '判断处理', types: ['clarity_check', 'select_baseline', 'match_kp', 'compose', 'budget_check', 'review'] },
  { name: '分支控制', types: ['condition'] },
  { name: '预留', types: ['llm'] },
]
const nodeMeta = (t: string) => NODE_TYPES.find((n) => n.type === t)

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

// ── 试运行 playground（右栏）──
const reqText = ref('2u服务器全套配置KH-50000\n256G D5\n1张480G启动盘\n四口千兆网卡\n电源配1300\n双口万兆')
const reqBudget = ref<number | null>(150000)

/** useTestRun 回调：把执行状态/徽标写回画布 nodes（按 node id 精确匹配，id=null 清全部） */
function applyNodeState(id: string | null, state: { execState: 'running' | 'done' | null; badge?: string }) {
  nodes.value = nodes.value.map((n) => (id === null || n.id === id
    ? { ...n, data: { ...n.data, execState: id === null ? null : state.execState, badge: id === null ? undefined : state.badge } }
    : n))
}

const { steps, plans, ext, kpByModel, running, error, awaitingInput, runTest } = useTestRun({ applyNodeState })

const expandedStep = ref<string | null>(null)
function toggleStep(key: string) {
  expandedStep.value = expandedStep.value === key ? null : key
}
function stepSummary(key: string, payload: any) {
  return STEP_COPY[key]?.(payload) || ''
}
function statusText(s: string) {
  return s === 'running' ? '执行中' : s === 'done' ? '完成' : s === 'error' ? '失败' : '待执行'
}
const modelKpList = computed(() => plans.value.map((p) => {
  const key = String(p.server_model_id ?? p.config_id)
  return { name: p.name || p.model || key, kps: kpByModel.value[key] || [] }
}))
/** P2 分支必连校验：condition 节点必须有 true + false 出边（兜底），否则路由死路（参考腾讯元器分支必连约束） */
const danglingBranches = computed(() => {
  const issues: string[] = []
  nodes.value.filter((n) => n.data?.stepType === 'condition').forEach((cn) => {
    const handles = new Set(edges.value.filter((e) => e.source === cn.id).map((e) => e.sourceHandle || 'true'))
    if (!handles.has('true')) issues.push(`${cn.data?.label || cn.id}：缺 true 分支`)
    if (!handles.has('false')) issues.push(`${cn.data?.label || cn.id}：缺 false 分支`)
  })
  return issues
})
const currencySymbol = (c?: string) => (c || 'RMB').toUpperCase() === 'USD' ? '$' : '¥'

async function onRun() {
  await runTest(reqText.value, reqBudget.value ?? undefined)
}

// P1 路径回溯：点方案 → 高亮该次试运行**实际执行过**的节点（steps 里 status=done 的，
// 含控制流 clarity_check / 后处理 budget_check / 下发 review），反映完整生成路径；其余变暗。再点退出。
const traced = ref(false)
function tracePlan() {
  traced.value = true
  const executed = new Set(steps.value.filter((s) => s.status === 'done').map((s) => s.key))
  nodes.value = nodes.value.map((n) => {
    const inChain = executed.has(n.id)
    return { ...n, data: { ...n.data, trace: inChain, dim: !inChain } }
  })
  // 连线：连接两个参与节点的边高亮（数据流向），其余变淡
  edges.value = edges.value.map((e: any) => ({
    ...e,
    class: (executed.has(e.source) && executed.has(e.target)) ? 'rf-edge--trace' : 'rf-edge--dim',
  }))
}
function clearTrace() {
  traced.value = false
  nodes.value = nodes.value.map((n) => ({ ...n, data: { ...n.data, trace: false, dim: false } }))
  edges.value = edges.value.map((e: any) => ({ ...e, class: '' }))
}

// 试运行方案卡的 BOM 详情抽屉（复用工作台 buildPlanCfg + BomTable）
const bomOpen = ref(false)
const bomPlan = ref<Plan | null>(null)
const bomCfg = ref<PlanLiveCfg | null>(null)
const bomLoading = ref(false)
async function viewBom(p: Plan) {
  bomPlan.value = p
  bomCfg.value = null
  bomLoading.value = true
  bomOpen.value = true
  try {
    bomCfg.value = await buildPlanCfg(p)
  } finally {
    bomLoading.value = false
  }
}

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
  const meta = nodeMeta(type)
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
  // 回溯模式：点节点 → 展开右栏该步的输入/输出明细（看实际数据），不开配置抽屉
  if (traced.value) { expandedStep.value = node.id; return }
  drawerNodeKey.value = node.id
  drawerNodeType.value = node.data?.stepType || node.data?.type
  drawerConfig.value = (flow.value?.node_configs as Record<string, any> | undefined)?.[node.id] || null
  drawerOpen.value = true
})
onEdgeClick(({ edge }) => {
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

watch(() => nodes.value.length, () => debouncePersist())
watch(() => edges.value.length, () => debouncePersist())

onMounted(load)
function onSaved() { load() }
</script>

<template>
  <div class="rf-canvas">
    <div class="rf-toolbar">
      <span class="rf-tip">左栏点节点添加到画布 · 中画布拖拽编排/连线（点边删连线）· 右栏试运行验证 · 单击节点开配置</span>
      <div class="rf-actions">
        <span v-if="flow" class="rf-version">v{{ flow.version }} · {{ flow.status }}</span>
      </div>
    </div>

    <div v-if="danglingBranches.length" class="rf-warn-bar">
      <ExclamationCircleOutlined />
      <span>{{ danglingBranches.join('；') }}（condition 需连 true/false 两个分支，避免路由死路）</span>
    </div>

    <div class="main-content">
      <!-- 左栏：节点 palette（点击添加到画布） -->
      <aside class="left-panel">
        <div class="panel-title">节点 · 点击添加</div>
        <div class="node-palette">
          <div v-for="g in NODE_GROUPS" :key="g.name" class="node-group">
            <div class="node-group-name">{{ g.name }}</div>
            <div v-for="t in g.types" :key="t" class="node-item" @click="addNode(t)">
              <span class="node-item-title">{{ nodeMeta(t)?.label || t }}</span>
              <span class="node-item-type">{{ t }}</span>
            </div>
          </div>
        </div>
      </aside>

      <!-- 中栏：vue flow 画布（编排 + 试运行时节点逐步高亮） -->
      <main class="center-panel">
        <a-spin :spinning="loading" class="center-spin">
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
      </main>

      <!-- 右栏：试运行 playground -->
      <aside class="right-panel">
        <div class="panel-title">
          <PlayCircleOutlined />
          <span>试运行</span>
          <span class="panel-sub">改完配置立刻验证</span>
        </div>
        <div class="rf-testrun">
          <div class="rf-tr-input">
            <a-textarea
              v-model:value="reqText"
              :auto-size="{ minRows: 2, maxRows: 5 }"
              placeholder="输入客户需求文本，如：2u服务器全套配置KH-50000 / 256G D5 / 四口千兆网卡…"
              class="rf-tr-textarea"
            />
            <div class="rf-tr-input-row">
              <a-input-number v-model:value="reqBudget" :min="0" :step="10000" placeholder="预算（可选）" class="rf-tr-budget">
                <template #addonBefore>¥</template>
              </a-input-number>
              <a-button type="primary" :loading="running" @click="onRun">
                <template #icon><PlayCircleOutlined /></template>
                {{ running ? '运行中…' : '运行' }}
              </a-button>
            </div>
            <span class="rf-tr-hint">force_complete 已开（跳过反问）· 总价按汇率/增值税折算为含税 ¥</span>
          </div>

          <p v-if="error" class="rf-tr-error"><ExclamationCircleOutlined /> {{ error }}</p>

          <!-- 步骤时间线 -->
          <div v-if="steps.length" class="rf-tr-steps">
            <div
              v-for="s in steps"
              :key="s.key"
              class="rf-tr-step"
              :class="`is-${s.status}`"
              @click="s.status === 'done' && toggleStep(s.key)"
            >
              <span class="rf-tr-dot"></span>
              <div class="rf-tr-step-body">
                <div class="rf-tr-step-head">
                  <span class="rf-tr-step-label">{{ s.label }}</span>
                  <span class="rf-tr-step-status">{{ statusText(s.status) }}</span>
                </div>
                <p v-if="s.status === 'done' && stepSummary(s.key, s.payload)" class="rf-tr-step-summary">
                  {{ stepSummary(s.key, s.payload) }}
                </p>
                <div v-if="expandedStep === s.key && s.status === 'done'" class="rf-tr-detail">
                  <!-- 变量流转：该节点消费的上游变量 + 产出的下游变量（IO 元数据，可解释性） -->
                  <div v-if="NODE_IO[s.key]" class="rf-tr-io">
                    <div class="rf-tr-io-row">
                      <span class="rf-tr-io-tag">← 输入</span>
                      <span v-for="v in NODE_IO[s.key].in" :key="v.name" class="rf-tr-io-var in">{{ v.name }}<small v-if="v.from"> ←{{ v.from }}</small></span>
                    </div>
                    <div class="rf-tr-io-row">
                      <span class="rf-tr-io-tag">→ 输出</span>
                      <span v-for="v in NODE_IO[s.key].out" :key="v.name" class="rf-tr-io-var out">{{ v.name }}<small v-if="v.desc"> · {{ v.desc }}</small></span>
                    </div>
                  </div>
                  <template v-if="s.key === 'extract'">
                    <div class="rf-tr-kv"><span>关键词</span><b>{{ (ext.keywords || []).join('、') || '—' }}</b></div>
                    <div class="rf-tr-kv"><span>KP 品类</span><b>{{ (ext.categories || []).join('、') || '—' }}</b></div>
                    <div class="rf-tr-kv"><span>系列 / 形态</span><b>{{ ext.series || '—' }} / {{ ext.form || '—' }}</b></div>
                    <div v-if="ext.mem_signal" class="rf-tr-kv"><span>内存信号</span><b>{{ ext.mem_signal.type }} · {{ ext.mem_signal.total_gb }}G</b></div>
                    <div v-if="ext.cpu_signal?.duality" class="rf-tr-kv"><span>CPU</span><b>双路信号</b></div>
                  </template>
                  <template v-else-if="s.key === 'match_kp'">
                    <div v-for="m in modelKpList" :key="m.name" class="rf-tr-model">
                      <div class="rf-tr-model-name">{{ m.name }} · {{ m.kps.length }} 件</div>
                      <div v-for="kp in m.kps" :key="(kp.pn || '') + (kp.category || '')" class="rf-tr-kp" :class="{ unmatched: kp.unmatched }">
                        <span class="rf-tr-kp-cat">{{ kp.category || '—' }}</span>
                        <span class="rf-tr-kp-pn">{{ kp.pn || '?' }}</span>
                        <span class="rf-tr-kp-qty">×{{ kp.qty || 1 }}</span>
                        <span class="rf-tr-kp-price">{{ currencySymbol(kp.currency) }}{{ kp.unit_price || 0 }}</span>
                        <span v-if="kp.matched_spec" class="rf-tr-kp-spec">↳ {{ kp.matched_spec }}</span>
                      </div>
                    </div>
                  </template>
                  <template v-else>
                    <pre class="rf-tr-raw">{{ JSON.stringify(s.payload, null, 2) }}</pre>
                  </template>
                </div>
              </div>
            </div>
          </div>

          <!-- 候选方案 -->
          <div v-if="plans.length" class="rf-tr-plans">
            <div v-if="traced" class="rf-tr-trace-hint">🔍 回溯模式：生成链节点 + 连线高亮；点任一高亮节点 → 右栏展开该步输入/输出数据；点「退出回溯」恢复</div>
            <PlanCard v-for="p in plans" :key="p.config_id" :plan="p" @view-bom="viewBom">
              <template #extra-actions>
                <a-button size="small" :type="traced ? 'default' : 'primary'" ghost @click="traced ? clearTrace() : tracePlan()">
                  <template #icon><NodeIndexOutlined /></template>
                  {{ traced ? '退出回溯' : '回溯路径' }}
                </a-button>
              </template>
            </PlanCard>
          </div>
          <p v-else-if="awaitingInput" class="rf-tr-empty">
            流程在此反问暂停，未走到选型——检查 flow 图分支或需求完整度。
          </p>
          <p v-else-if="!running && !error && steps.length && steps.every(s => s.status === 'done')" class="rf-tr-empty">
            流程走完但未产出方案（选型为空或机型库无匹配）。
          </p>
        </div>
      </aside>
    </div>

    <ReasoningNodeDrawer v-model:open="drawerOpen" :node-key="drawerNodeKey" :node-type="drawerNodeType" :initial-config="drawerConfig" @saved="onSaved" @remove="onRemove" />

    <!-- 试运行方案 BOM 详情抽屉 -->
    <a-drawer v-model:open="bomOpen" :title="bomPlan?.name || '整机 BOM 详情'" placement="right" width="640">
      <div v-if="bomPlan" class="rf-tr-bom">
        <div class="rf-tr-bom-summary">
          {{ [bomPlan.series, bomPlan.form, bomPlan.bays != null ? `${bomPlan.bays}盘位` : ''].filter(Boolean).join(' · ') }}
          · 底盘 {{ bomPlan.summary.parts_count }} 件 + KP {{ bomPlan.summary.kp_count }} 件
        </div>
        <a-spin :spinning="bomLoading" tip="转 BOM 模板格式…">
          <BomTable v-if="bomCfg" :cfg="bomCfg" />
        </a-spin>
      </div>
    </a-drawer>
  </div>
</template>

<style scoped>
.rf-canvas { display: flex; flex-direction: column; gap: 8px; height: calc(100vh - 150px); min-height: 480px; }
.rf-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0 2px; gap: 12px; }
.rf-warn-bar { display: flex; align-items: center; gap: 6px; padding: 6px 12px; font-size: 12px; color: var(--cpq-accent-warning, #faad14); background: rgba(244, 210, 138, 0.12); border: 1px solid rgba(244, 210, 138, 0.3); border-radius: 8px; }
.rf-tip { font-size: 12px; color: var(--cpq-text-muted); flex: 1; }
.rf-actions { display: flex; align-items: center; gap: 10px; }
.rf-version {
  font-size: 11px; color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-w8); padding: 1px 8px; border-radius: 8px;
  font-variant-numeric: tabular-nums;
}

/* ── 三栏主区（参考 UniverTemplateEditor）── */
.main-content { flex: 1; display: flex; overflow: hidden; min-height: 0; border: 1px solid var(--cpq-overlay-w10); border-radius: var(--cpq-radius-md, 12px); background: var(--cpq-overlay-w3, transparent); }
.left-panel { width: 240px; background: var(--cpq-overlay-w4); border-right: 1px solid var(--cpq-overlay-w10); display: flex; flex-direction: column; overflow: hidden; border-radius: var(--cpq-radius-md, 12px) 0 0 var(--cpq-radius-md, 12px); }
.center-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
.center-panel :deep(.ant-spin-nested-loading) { flex: 1; display: flex; }
.center-panel :deep(.ant-spin-container) { flex: 1; display: flex; }
.rf-flow-wrap { flex: 1; min-width: 0; min-height: 0; overflow: hidden; }

/* MiniMap 默认白底（@vue-flow/minimap style.css 写死 #fff），深色模式很突兀；
   用面板背景 token 跟随主题（深色 #101217 / 浅色 #F0F4FA），节点用主色醒目 */
.center-panel :deep(.vue-flow__minimap) { background-color: var(--cpq-bg-secondary); }
.center-panel :deep(.vue-flow__minimap-node) { fill: var(--cpq-accent-primary, #1677FF); opacity: 0.75; }
/* minimap 视口遮罩默认浅灰 rgba(240,240,240,.6)，深色 minimap 上显白雾 → 深色模式改黑半透 */
[data-theme="dark"] .center-panel :deep(.vue-flow__minimap-mask) { fill: rgba(0, 0, 0, 0.45); }
/* 回溯连线：生成链边高亮（蓝粗），其余变淡 */
.center-panel :deep(.rf-edge--trace .vue-flow__edge-path) { stroke: var(--cpq-accent-primary); stroke-width: 2.5; }
.center-panel :deep(.rf-edge--dim) { opacity: 0.12; }

/* Controls 按钮组默认白底（#fefefe）+ hover 浅灰，深色突兀；跟随主题 + svg 用主题文字色 */
.center-panel :deep(.vue-flow__controls) { box-shadow: 0 0 2px 1px var(--cpq-overlay-w15, rgba(0, 0, 0, 0.08)); }
.center-panel :deep(.vue-flow__controls-button) {
  background: var(--cpq-bg-secondary);
  border-bottom: 1px solid var(--cpq-overlay-w10);
}
.center-panel :deep(.vue-flow__controls-button:hover) { background: var(--cpq-overlay-a8); }
.center-panel :deep(.vue-flow__controls-button svg) { fill: var(--cpq-text-primary); }
.right-panel { width: 380px; background: var(--cpq-overlay-w4); border-left: 1px solid var(--cpq-overlay-w10); display: flex; flex-direction: column; overflow: hidden; border-radius: 0 var(--cpq-radius-md, 12px) var(--cpq-radius-md, 12px) 0; }

/* ── panel 标题 ── */
.panel-title {
  display: flex; align-items: center; gap: 6px;
  padding: 12px 14px; font-weight: 600; font-size: 13px; color: var(--cpq-text-primary);
  border-bottom: 1px solid var(--cpq-overlay-w8); flex-shrink: 0;
}
.panel-title .anticon { color: var(--cpq-accent-primary); }
.panel-sub { margin-left: auto; font-size: 11px; color: var(--cpq-text-muted); font-weight: 400; }

/* ── 左栏节点 palette ── */
.node-palette { flex: 1; overflow-y: auto; padding: 6px 0; }
.node-group { margin-bottom: 4px; }
.node-group-name {
  font-size: 10px; font-weight: 600; color: var(--cpq-text-muted);
  text-transform: uppercase; letter-spacing: .5px; padding: 8px 14px 3px;
}
.node-item {
  display: flex; flex-direction: column; gap: 1px; padding: 7px 14px;
  cursor: pointer; transition: background var(--cpq-transition-fast);
  border-left: 2px solid transparent;
}
.node-item:hover { background: var(--cpq-overlay-a8); border-left-color: var(--cpq-accent-primary); }
.node-item:active { background: var(--cpq-overlay-a15); }
.node-item-title { font-size: 12px; font-weight: 500; color: var(--cpq-text-primary); }
.node-item-type { font-size: 10px; color: var(--cpq-text-muted); font-family: ui-monospace, monospace; }

/* ── 右栏试运行 ── */
.rf-testrun { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.rf-tr-input { display: flex; flex-direction: column; gap: 8px; }
.rf-tr-input-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rf-tr-budget { flex: 1 1 120px; min-width: 0; }
.rf-tr-textarea { border-radius: var(--cpq-radius-sm, 8px); }
.rf-tr-hint { font-size: 11px; color: var(--cpq-text-muted); }
.rf-tr-error {
  margin: 0; font-size: 12px; color: var(--cpq-accent-danger);
  display: flex; align-items: center; gap: 6px;
}

.rf-tr-steps { display: flex; flex-direction: column; gap: 6px; }
.rf-tr-step {
  display: flex; gap: 10px; padding: 8px 10px;
  border-radius: var(--cpq-radius-sm, 8px);
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w10);
  transition: border-color var(--cpq-transition-fast);
}
.rf-tr-step.is-done { cursor: pointer; }
.rf-tr-step:hover { border-color: var(--cpq-glass-border-strong); }
.rf-tr-dot {
  width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; flex-shrink: 0;
  background: var(--cpq-overlay-w15);
}
.rf-tr-step.is-running .rf-tr-dot { background: var(--cpq-accent-primary); animation: rf-tr-pulse 1s infinite; }
.rf-tr-step.is-done .rf-tr-dot { background: var(--cpq-color-success); }
.rf-tr-step.is-error .rf-tr-dot { background: var(--cpq-accent-danger); }
@keyframes rf-tr-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.rf-tr-step-body { flex: 1; min-width: 0; }
.rf-tr-step-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rf-tr-step-label { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.rf-tr-step-status { font-size: 11px; color: var(--cpq-text-muted); }
.rf-tr-step.is-running .rf-tr-step-status { color: var(--cpq-accent-primary); }
.rf-tr-step.is-done .rf-tr-step-status { color: var(--cpq-color-success); }
.rf-tr-step-summary { margin: 3px 0 0; font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.5; }

.rf-tr-detail {
  margin-top: 8px; padding-top: 8px;
  border-top: 1px dashed var(--cpq-overlay-w10);
  display: flex; flex-direction: column; gap: 4px;
}
/* 变量流转 IO 展示（输入←上游 / 输出→下游） */
.rf-tr-io { display: flex; flex-direction: column; gap: 3px; margin-bottom: 6px; padding: 5px 8px; background: var(--cpq-overlay-w4); border-radius: 6px; }
.rf-tr-io-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; }
.rf-tr-io-tag { font-size: 10px; font-weight: 600; color: var(--cpq-text-muted); flex-shrink: 0; }
.rf-tr-io-var { font-size: 10px; padding: 1px 5px; border-radius: 4px; font-family: ui-monospace, monospace; word-break: break-all; }
.rf-tr-io-var.in { background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
.rf-tr-io-var.out { background: rgba(82, 201, 160, 0.15); color: var(--cpq-color-success); }
.rf-tr-io-var small { font-family: inherit; opacity: 0.7; font-size: 9px; }
.rf-tr-kv { font-size: 12px; color: var(--cpq-text-secondary); display: flex; gap: 8px; }
.rf-tr-kv span { color: var(--cpq-text-muted); min-width: 56px; }
.rf-tr-kv b { font-weight: 500; }
.rf-tr-model { padding: 4px 0; }
.rf-tr-model-name { font-size: 12px; font-weight: 600; color: var(--cpq-accent-primary); margin-bottom: 3px; }
.rf-tr-kp {
  display: grid; grid-template-columns: 80px 1fr 32px 72px; gap: 6px;
  font-size: 11px; padding: 2px 0; color: var(--cpq-text-secondary); align-items: baseline;
}
.rf-tr-kp.unmatched { color: var(--cpq-accent-danger); }
.rf-tr-kp-pn { font-family: ui-monospace, monospace; word-break: break-all; }
.rf-tr-kp-price { font-variant-numeric: tabular-nums; text-align: right; }
.rf-tr-kp-spec { grid-column: 1 / -1; font-size: 10px; color: var(--cpq-text-muted); }
.rf-tr-raw {
  margin: 0; font-size: 11px; white-space: pre-wrap; word-break: break-all;
  color: var(--cpq-text-muted); font-family: ui-monospace, monospace;
}

.rf-tr-plans { display: flex; flex-direction: column; gap: 8px; }
.rf-tr-trace-hint { font-size: 11px; color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); padding: 6px 10px; border-radius: 6px; }
.rf-tr-empty { font-size: 12px; color: var(--cpq-text-muted); text-align: center; padding: 12px 0; margin: 0; }

.rf-tr-bom { display: flex; flex-direction: column; height: 100%; }
.rf-tr-bom-summary {
  font-size: 12px; color: var(--cpq-text-secondary);
  padding: 0 0 10px; border-bottom: 1px solid var(--cpq-overlay-w8); margin-bottom: 10px;
}
</style>
