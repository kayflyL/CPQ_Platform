/**
 * useTestRun — 策略中心·需求分析画布「试运行」面板的状态机（2026-08：改为 WS 流式）。
 *
 * 此前：同步 HTTP 一次性拿到完整 events，再用 setTimeout 逐步回放 —— 后端跑多久（含 LLM
 * 单步 20~40s）前端就干等多久，跑完才"一口气列出全部步骤"，体验很差（用户反馈）。
 * 现在：POST /test-run/start 注册 run_id → 后端边跑边把 step_start/step_done/need_input/
 * candidates_ready 经 WS /api/reasoning-flow/test-run-ws/{run_id} 实时推送 → 本 composable
 * 收到事件即更新步骤状态 + 节点高亮（applyNodeState），真·完成一步显示一步。
 *
 * 与方案助手聊天通道（assistant_hub + thread 房间 + 聊天消息）的区别，
 * 本 composable 是画布试运行通道（独立 run_id 房间，无聊天语义），但复用同一套 hub 基建。
 */
import { ref, onBeforeUnmount } from 'vue'
import { reasoningFlowApi } from '@/api/reasoningFlow'
import type { Plan } from '@/api/reasoning'
import type { ReasoningStep, StepStatus } from '@/composables/reasoningTypes'
import { STEP_BADGE } from '@/utils/reasoningStepCopy'

export type NodeExecState = 'running' | 'done' | null
export interface NodeState {
  execState: NodeExecState
  badge?: string
  input?: any
  output?: any
  summary?: string
  artifact?: any
}

export function useTestRun(opts: {
  applyNodeState?: (id: string | null, state: NodeState) => void
} = {}) {
  const steps = ref<ReasoningStep[]>([])
  const plans = ref<Plan[]>([])
  const bomScheme = ref<any>(null)
  const ext = ref<Record<string, any>>({})
  const kpByModel = ref<Record<string, any[]>>({})
  const running = ref(false)
  const error = ref<string | null>(null)
  const awaitingInput = ref(false)
  const pendingQuestion = ref('')
  const pendingOptions = ref<string[]>([])
  const planProgress = ref<{ remaining: number; elapsedS: number } | null>(null)
  const missingFields = ref<string[]>([])

  let ws: WebSocket | null = null

  function closeWs() {
    if (ws) {
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      try { ws.close() } catch { /* noop */ }
      ws = null
    }
  }

  function reset() {
    closeWs()
    steps.value = []
    plans.value = []
    bomScheme.value = null
    ext.value = {}
    kpByModel.value = {}
    error.value = null
    awaitingInput.value = false
    pendingQuestion.value = ''
    pendingOptions.value = []
    missingFields.value = []
    planProgress.value = null
    opts.applyNodeState?.(null, { execState: null })  // null id = 清所有节点高亮
  }

  function ensureStep(key: string, label?: string) {
    if (!steps.value.some((s) => s.key === key)) {
      steps.value.push({ key, label: label || key, status: 'pending' as StepStatus })
    }
  }

  function setStep(key: string, status: StepStatus, payload?: any) {
    const i = steps.value.findIndex((s) => s.key === key)
    if (i >= 0) steps.value[i] = { ...steps.value[i], status, payload: payload ?? steps.value[i].payload }
  }

  const MAX_SUBSTEPS = 30
  // step_progress 节流：连续 thinking 增量合并为一条，并限制子步骤总数，避免逐 delta 刷屏。
  function pushSubstep(key: string, sub: { kind: string; text: string }) {
    const i = steps.value.findIndex((s) => s.key === key)
    if (i < 0) return
    const cur = steps.value[i]
    const subs = cur.substeps || []
    const last = subs[subs.length - 1]
    if (sub?.kind === 'thinking' && last?.kind === 'thinking') {
      const merged = { ...last, text: ((last.text || '') + (sub.text || '')).trim() }
      steps.value[i] = { ...cur, substeps: [...subs.slice(0, -1), merged] }
      return
    }
    const next = [...subs, sub]
    if (next.length > MAX_SUBSTEPS) {
      steps.value[i] = { ...cur, substeps: next.slice(next.length - MAX_SUBSTEPS) }
      return
    }
    steps.value[i] = { ...cur, substeps: next }
  }

  function handle(data: any) {
    switch (data.type) {
      case 'pipeline_start':
        // 预置全部将执行步骤为 pending（后端按图节点算好；extract 兜底跑到时再懒创建）
        steps.value = (data.steps || []).map((s: any) => ({
          key: s.key,
          label: s.label || s.key,
          status: 'pending' as StepStatus,
        }))
        return
      case 'step_start':
        ensureStep(data.step, data.label)
        setStep(data.step, 'running')
        const si = steps.value.findIndex((s) => s.key === data.step)
        if (si >= 0) steps.value[si] = { ...steps.value[si], input: data.input }
        opts.applyNodeState?.(data.step, { execState: 'running', input: data.input })
        return
      case 'step_done':
        ensureStep(data.step, data.label)
        setStep(data.step, 'done', data.payload)
        const di = steps.value.findIndex((s) => s.key === data.step)
        if (di >= 0) {
          steps.value[di] = {
            ...steps.value[di],
            input: data.input ?? steps.value[di].input,
            output: data.output,
            summary: data.summary,
            artifact: data.artifact,
          }
        }
        const badge = data.step ? STEP_BADGE[data.step]?.(data.payload) : undefined
        opts.applyNodeState?.(data.step, {
          execState: 'done',
          badge,
          input: data.input,
          output: data.output,
          summary: data.summary,
          artifact: data.artifact,
        })
        if (data.artifact?.kind === 'requirement_missing') {
          missingFields.value = Array.isArray(data.artifact?.data?.missing_fields) ? data.artifact.data.missing_fields : []
        }
        return
      case 'step_progress':
        pushSubstep(data.step, data.sub || { kind: 'progress', text: '' })
        return
      case 'plan_progress':
        planProgress.value = {
          remaining: (data.remaining || []).length,
          elapsedS: Math.round(data.elapsed_s || data.budget?.elapsed_s || 0),
        }
        return
      case 'need_input':
        awaitingInput.value = true
        pendingQuestion.value = data.question || ''
        pendingOptions.value = data.options || []
        missingFields.value = Array.isArray(data.missing_fields) ? data.missing_fields : []
        running.value = false
        return
      case 'candidates_ready':
        plans.value = data.plans || []
        return
      case 'pipeline_paused':
      case 'pipeline_done':
        planProgress.value = null
        ext.value = data.ext || {}
        kpByModel.value = data.kp_by_model || {}
        if (data.plans?.length) plans.value = data.plans
        bomScheme.value = data.bom_scheme || null
        awaitingInput.value = !!data.awaiting_input
        running.value = false
        closeWs()
        return
      case 'error':
        error.value = data.message || '试运行失败'
        running.value = false
        closeWs()
        return
      default:
        return
    }
  }

  async function runTest(text: string, budget?: number, forceComplete?: boolean, skillKey?: string) {
    if (!text.trim() || running.value) return
    reset()
    running.value = true
    let runId = ''
    try {
      const res = await reasoningFlowApi.testRunStart(text, budget, forceComplete, skillKey)
      runId = res.run_id
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '试运行启动失败'
      running.value = false
      return
    }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    try {
      ws = new WebSocket(`${proto}://${location.host}/api/reasoning-flow/test-run-ws/${encodeURIComponent(runId)}`)
    } catch {
      error.value = '流式连接建立失败'
      running.value = false
      return
    }
    ws.onmessage = (ev) => {
      try { handle(JSON.parse(ev.data)) } catch { /* 忽略坏帧 */ }
    }
    ws.onerror = () => {
      if (running.value) { error.value = '流式连接中断，请重试'; running.value = false }
    }
    ws.onclose = () => {
      // 未收到终态就断开 → 保底结束（防止一直转圈）
      if (running.value) running.value = false
    }
  }

  onBeforeUnmount(() => closeWs())

  return { steps, plans, bomScheme, ext, kpByModel, running, error, awaitingInput, pendingQuestion, pendingOptions, missingFields, planProgress, runTest, reset }
}
