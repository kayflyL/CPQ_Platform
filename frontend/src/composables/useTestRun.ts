/**
 * useTestRun — 策略中心·需求分析「试运行」面板的状态机。
 *
 * 与 useReasoningStream 的区别：后者 WS 驱动（逐条事件到达），本 composable 同步 HTTP 一次性拿到完整 events，
 * 再用 setTimeout 按 events 顺序逐步回放（节点高亮 + 步骤 running→done 动画），让管理员看清每步在发挥什么作用。
 * 明细（plans/ext/kp_by_model）用响应顶层，回放动画只驱动 UI 状态。
 *
 * 节点高亮经 applyNodeState 回调注入画布（解耦：本 composable 不持有画布 nodes ref）。
 */
import { ref, onBeforeUnmount } from 'vue'
import { reasoningFlowApi, type TestRunResult, type TestRunEvent } from '@/api/reasoningFlow'
import type { Plan } from '@/api/reasoning'
import type { ReasoningStep, StepStatus } from '@/composables/useReasoningStream'
import { STEP_BADGE } from '@/utils/reasoningStepCopy'

export type NodeExecState = 'running' | 'done' | null
export interface NodeState { execState: NodeExecState; badge?: string }

export function useTestRun(opts: {
  applyNodeState?: (id: string | null, state: NodeState) => void
} = {}) {
  const steps = ref<ReasoningStep[]>([])
  const plans = ref<Plan[]>([])
  const ext = ref<Record<string, any>>({})
  const kpByModel = ref<Record<string, any[]>>({})
  const running = ref(false)
  const error = ref<string | null>(null)
  const awaitingInput = ref(false)
  const pendingQuestion = ref('')
  const pendingOptions = ref<string[]>([])

  let timers: ReturnType<typeof setTimeout>[] = []

  function clearTimers() {
    timers.forEach(clearTimeout)
    timers = []
  }

  function reset() {
    clearTimers()
    steps.value = []
    plans.value = []
    ext.value = {}
    kpByModel.value = {}
    error.value = null
    awaitingInput.value = false
    pendingQuestion.value = ''
    pendingOptions.value = []
    opts.applyNodeState?.(null, { execState: null })  // null id = 清所有节点高亮
  }

  function setStep(key: string, status: StepStatus, payload?: any) {
    const i = steps.value.findIndex((s) => s.key === key)
    if (i >= 0) steps.value[i] = { ...steps.value[i], status, payload: payload ?? steps.value[i].payload }
  }

  function seedSteps(events: TestRunEvent[]): ReasoningStep[] {
    const startEv = events.find((e) => e.type === 'pipeline_start')
    const seeds = startEv?.steps
      || events.filter((e) => e.type === 'step_start').map((e) => ({ key: e.step!, label: e.label || e.step! }))
    return (seeds as any[]).map((s) => ({ key: s.key, label: s.label, status: 'pending' as StepStatus }))
  }

  function finish(res: TestRunResult) {
    plans.value = res.plans || []
    ext.value = res.ext || {}
    kpByModel.value = res.kp_by_model || {}
    awaitingInput.value = !!res.awaiting_input
    const needInput = (res.events || []).filter((e) => e.type === 'need_input').pop() as any
    pendingQuestion.value = needInput?.question || ''
    pendingOptions.value = needInput?.options || []
    running.value = false
  }

  function replay(events: TestRunEvent[], res: TestRunResult) {
    const perEvent = 220  // 每个 step_start/step_done 事件间隔 ms
    let t = 0
    events.forEach((ev) => {
      if (ev.type === 'step_start' || ev.type === 'step_done') {
        const delay = t
        const fire = () => {
          if (ev.type === 'step_start') {
            setStep(ev.step!, 'running')
            opts.applyNodeState?.(ev.step!, { execState: 'running' })
          } else {
            setStep(ev.step!, 'done', ev.payload)
            const badge = ev.step ? STEP_BADGE[ev.step]?.(ev.payload) : undefined
            opts.applyNodeState?.(ev.step!, { execState: 'done', badge })
          }
        }
        timers.push(setTimeout(fire, delay))
        t += perEvent
      } else if (ev.type === 'pipeline_done' || ev.type === 'pipeline_paused') {
        timers.push(setTimeout(() => finish(res), t))
      }
    })
    // 兜底：无 pipeline_done/paused 事件时也要收尾
    timers.push(setTimeout(() => finish(res), t + 80))
  }

  async function runTest(text: string, budget?: number, forceComplete?: boolean) {
    if (!text.trim() || running.value) return
    reset()
    running.value = true
    let res: TestRunResult
    try {
      res = await reasoningFlowApi.testRun(text, budget, forceComplete)
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '试运行请求失败'
      running.value = false
      return
    }
    if (res.error) {
      error.value = res.error  // 报错也继续回放 events，让用户看到走到哪步崩了
    }
    steps.value = seedSteps(res.events || [])
    if ((res.events || []).length) {
      replay(res.events, res)
    } else {
      finish(res)
    }
  }

  onBeforeUnmount(() => clearTimers())

  return { steps, plans, ext, kpByModel, running, error, awaitingInput, pendingQuestion, pendingOptions, runTest, reset }
}
