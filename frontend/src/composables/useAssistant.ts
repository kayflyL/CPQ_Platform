/**
 * useAssistant — 当前助手会话状态 + LLM 流式接收 + 需求分析（生成 BOM）。
 *
 * 全局单例语义(DefaultLayout 持有 Panel,Panel 调用一次):管理 thread 列表 /
 * 当前 thread / 消息 / 发送 / WS 流式(chunk → streamingText,done → 定稿入 messages)。
 *
 * 需求分析（2026-08-05）：方案助手与商机详情页跑同一套后端 pipeline。触发后
 * 后端把 pipeline 事件广播到 /api/assistant/ws/{threadId}（pipeline_start /
 * step_start / step_done / need_input / need_confirm / candidates_ready /
 * pipeline_done|paused / analysis_finished），本 composable 消费并驱动
 * 步骤时间线 + 反问框 + LLM 确认面板 + 整机方案卡。
 */
import { ref, computed, watch } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import { assistantApi, assistantWsUrl } from '@/api/assistant'
import type { AssistantThread, AssistantMessage, AssistantAnalysisStep } from '@/api/assistant'

export type AnalysisStepStatus = 'pending' | 'running' | 'done' | 'error'

export interface AnalysisPrompt {
  reply_id: string
  question: string
  options: string[]
  round: number
  clarity_capped: boolean
  stage?: string
  format?: string
  why?: string
}
export interface AnalysisConfirm {
  reply_id: string
  question: string
  items: Array<{
    id: string
    slot: string
    label: string
    rule?: string | null
    llm?: string | null
    level: 'conflict' | 'low_confidence'
    confidence?: number
    default?: string
  }>
  default: string
}

export function useAssistant() {
  const threads = ref<AssistantThread[]>([])
  const currentThreadId = ref<string | null>(null)
  const messages = ref<AssistantMessage[]>([])
  const loading = ref(false)
  const sending = ref(false)
  const streamingText = ref('') // 当前正在流式输出的 assistant 文本(临时,done 后清空并入 messages)
  const waitingAI = ref(false) // 已发送、等首个 chunk 到来前的等待态(显示 typing 指示)

  // ── 需求分析状态（方案助手生成 BOM）──
  const analysisSteps = ref<AssistantAnalysisStep[]>([])
  const analysisRunning = ref(false)
  const analysisBusy = ref(false) // REST 请求在途（防连点）
  const analysisError = ref<string | null>(null)
  const analysisPrompt = ref<AnalysisPrompt | null>(null)
  const analysisConfirm = ref<AnalysisConfirm | null>(null)
  const analysisActive = ref(false) // 是否有进行中/未完成的分析（显示步骤区/收尾）

  const currentThread = computed(
    () => threads.value.find((t) => t.thread_id === currentThreadId.value) || null,
  )

  // ── WS:订阅当前 thread 的 token 流 + pipeline 事件 ──
  let ws: WebSocket | null = null

  function setAnalysisStep(key: string, status: AnalysisStepStatus, payload?: any) {
    const i = analysisSteps.value.findIndex((s) => s.key === key)
    if (i >= 0) {
      analysisSteps.value[i] = {
        ...analysisSteps.value[i],
        status,
        payload: payload ?? analysisSteps.value[i].payload,
      }
    }
  }
  function pushAnalysisSubstep(key: string, sub: { kind: string; text: string }) {
    const i = analysisSteps.value.findIndex((s) => s.key === key)
    if (i >= 0) {
      const cur = analysisSteps.value[i]
      analysisSteps.value[i] = { ...cur, substeps: [...(cur.substeps || []), sub] }
    }
  }
  function finishAnalysisSteps() {
    analysisSteps.value.forEach((s) => {
      if (s.status === 'pending' || s.status === 'running') s.status = 'done'
    })
  }
  /** 分析走到终点（结果已进消息流）→ 收起步骤时间线，否则它会一直挂在输入框上方、不被新消息顶走 */
  function endAnalysisTimeline() {
    analysisSteps.value = []
    analysisActive.value = false
  }
  function resetAnalysis() {
    analysisSteps.value = []
    analysisRunning.value = false
    analysisError.value = null
    analysisPrompt.value = null
    analysisConfirm.value = null
  }

  function handleWsData(data: any) {
    // 需求分析 pipeline 事件（与 LLM 聊天 chunk/done 走同一条 WS，按 type 分流）
    switch (data.type) {
      case 'pipeline_start':
        analysisActive.value = true
        analysisRunning.value = true
        analysisError.value = null
        analysisPrompt.value = null
        analysisConfirm.value = null
        analysisSteps.value = (data.steps || []).map((s: any) => ({
          key: s.key,
          label: s.label || s.key,
          status: 'pending' as AnalysisStepStatus,
        }))
        return
      case 'step_start':
        setAnalysisStep(data.step, 'running')
        return
      case 'step_done':
        setAnalysisStep(data.step, 'done', data.payload)
        return
      case 'step_progress':
        pushAnalysisSubstep(data.step, data.sub || { kind: 'progress', text: '' })
        return
      case 'need_input':
        analysisPrompt.value = {
          reply_id: data.reply_id || '',
          question: data.question || '',
          options: data.options || [],
          round: data.round || 1,
          clarity_capped: !!data.clarity_capped,
          stage: data.stage || undefined,
          format: data.format || undefined,
          why: data.why || undefined,
        }
        return
      case 'need_confirm':
        analysisConfirm.value = {
          reply_id: data.reply_id || '',
          question: data.question || '',
          items: data.items || [],
          default: data.default || 'accept',
        }
        return
      case 'candidates_ready':
        // plans 由后续 analysis_result 消息承载（融入消息流，不再单独存 ref）
        return
      case 'pipeline_paused':
        analysisRunning.value = false
        finishAnalysisSteps()
        return
      case 'pipeline_done':
        analysisRunning.value = false
        endAnalysisTimeline()
        return
      case 'error':
        analysisError.value = data.message || '推理流程异常'
        analysisRunning.value = false
        analysisSteps.value.forEach((s) => {
          if (s.status === 'running') s.status = 'error'
        })
        return
      case 'analysis_result':
        // 需求分析结果消息（BOM 文本）→ 推进对话流（企微端也推同一段文本）
        analysisRunning.value = false
        if (data.message) messages.value.push(data.message as AssistantMessage)
        endAnalysisTimeline()
        return
      case 'analysis_finished':
        analysisRunning.value = false
        endAnalysisTimeline()
        return
      case 'chunk':
        if (typeof data.delta === 'string') {
          waitingAI.value = false
          streamingText.value += data.delta
        }
        return
      case 'done':
        waitingAI.value = false
        if (data.message) messages.value.push(data.message as AssistantMessage)
        streamingText.value = ''
        return
      default:
        return
    }
  }

  function connectWs(threadId: string | null) {
    disconnectWs()
    if (!threadId) return
    try {
      ws = new WebSocket(assistantWsUrl(threadId))
    } catch {
      ws = null
      return
    }
    ws.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      handleWsData(data)
    }
    ws.onclose = () => {
      ws = null
    }
    ws.onerror = () => {
      /* 静默:REST 已返回 user_message,WS 仅推流式回复 */
    }
  }

  function disconnectWs() {
    if (ws) {
      ws.onclose = null
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      ws = null
    }
    streamingText.value = ''
  }

  // 切换 thread → 重连 WS
  watch(currentThreadId, (id) => connectWs(id))

  async function loadThreads() {
    try {
      threads.value = await assistantApi.threads.list()
      if (!currentThreadId.value && threads.value.length) {
        await selectThread(threads.value[0].thread_id)
      }
    } catch {
      /* ignore */
    }
  }

  async function selectThread(id: string) {
    currentThreadId.value = id
    loading.value = true
    try {
      messages.value = await assistantApi.threads.messages(id)
      // 历史重放：从 analysis_* 结构化消息恢复方案卡 / 反问框 / 确认面板
      restoreAnalysisFromHistory(messages.value)
    } finally {
      loading.value = false
    }
  }

  /** 从历史消息恢复需求分析 UI 状态（刷新/切换会话后方案卡不丢） */
  function restoreAnalysisFromHistory(msgs: AssistantMessage[]) {
    resetAnalysis()
    // 找到最后一条 analysis_ 消息作为当前分析态
    for (const m of msgs) {
      if (m.kind === 'analysis_result') {
        // 方案卡融入消息流渲染（parsePlans 在模板侧），这里只标记分析态
        analysisActive.value = true
        analysisRunning.value = false
        analysisPrompt.value = null
        analysisConfirm.value = null
      } else if (m.kind === 'analysis_pending') {
        try {
          const d = JSON.parse(m.data || '{}')
          analysisPrompt.value = {
            reply_id: d.reply_id || '',
            question: d.question || m.content,
            options: d.options || [],
            round: d.round || 1,
            clarity_capped: !!d.clarity_capped,
            stage: d.stage || undefined,
            format: d.format || undefined,
          }
          analysisActive.value = true
          analysisRunning.value = false
        } catch {
          /* ignore */
        }
      } else if (m.kind === 'analysis_confirm') {
        try {
          const d = JSON.parse(m.data || '{}')
          analysisConfirm.value = {
            reply_id: d.reply_id || '',
            question: d.question || m.content,
            items: d.items || [],
            default: d.default || 'accept',
          }
          analysisActive.value = true
          analysisRunning.value = false
        } catch {
          /* ignore */
        }
      }
    }
  }

  async function newThread(): Promise<AssistantThread | null> {
    try {
      const t = await assistantApi.threads.create()
      threads.value.unshift(t)
      await selectThread(t.thread_id)
      return t
    } catch {
      antMessage.error('新建会话失败')
      return null
    }
  }

  async function send(content: string, contextSummary?: string) {
    const text = content.trim()
    if (!text) return
    if (!currentThreadId.value) {
      const t = await newThread()
      if (!t) return
    }
    sending.value = true
    streamingText.value = ''
    waitingAI.value = true
    try {
      const res = await assistantApi.threads.postMessage(currentThreadId.value!, text, contextSummary)
      messages.value.push(res.user_message)
      if (res.thread) {
        const i = threads.value.findIndex((t) => t.thread_id === res.thread!.thread_id)
        if (i >= 0) threads.value[i] = res.thread
      }
      // assistant 回复由 WS chunk 流式拼接(streamingText)→ done 定稿入 messages
    } catch {
      antMessage.error('发送失败')
    } finally {
      sending.value = false
    }
  }

  // ── 需求分析动作 ──
  /**
   * 触发需求分析（新分析或续接）。
   * @param requirement 需求文本；补充回答时传空串
   * @param opts supplementText: 反问补充 / budget: 预算 / forceComplete: 跳过反问 / confirm: LLM 确认决策
   */
  async function runAnalysis(
    requirement: string,
    opts: {
      supplementText?: string
      budget?: number
      forceComplete?: boolean
      confirm?: Record<string, string>
    } = {},
  ) {
    const text = requirement.trim()
    if (!text && !opts.supplementText && !opts.forceComplete && !opts.confirm) return
    if (analysisBusy.value) return
    if (!currentThreadId.value) {
      const t = await newThread()
      if (!t) return
    }
    analysisBusy.value = true
    analysisRunning.value = true
    analysisError.value = null
    try {
      const res = await assistantApi.threads.analyze(currentThreadId.value!, {
        requirement_text: text,
        supplement_text: opts.supplementText,
        explicit_budget: opts.budget,
        force_complete: opts.forceComplete ?? false,
        confirm: opts.confirm,
      })
      if (res.user_message) messages.value.push(res.user_message)
    } catch (e: any) {
      antMessage.error('需求分析启动失败：' + (e?.message || e))
      analysisRunning.value = false
    } finally {
      analysisBusy.value = false
    }
  }

  /** 反问回复（续接暂停的 pipeline） */
  function replyAnalysis(text: string) {
    return runAnalysis('', { supplementText: text })
  }

  /** 跳过反问，强制出方案 */
  function skipAnalysis() {
    return runAnalysis('', { forceComplete: true })
  }

  /** LLM 确认面板：按选择重新生成 */
  function confirmAnalysis(decisions: Record<string, string>) {
    return runAnalysis('', { confirm: decisions })
  }

  /** 全部采纳：关闭确认面板直接看当前方案（方案已在 candidates_ready 下发，无需重跑） */
  function acceptAllAnalysis() {
    analysisConfirm.value = null
  }

  async function removeThread(id: string) {
    try {
      await assistantApi.threads.remove(id)
      threads.value = threads.value.filter((t) => t.thread_id !== id)
      if (currentThreadId.value === id) {
        currentThreadId.value = threads.value[0]?.thread_id || null
        if (currentThreadId.value) await selectThread(currentThreadId.value)
        else {
          messages.value = []
          resetAnalysis()
        }
      }
    } catch {
      antMessage.error('删除失败')
    }
  }

  return {
    threads, currentThreadId, currentThread, messages, loading, sending,
    streamingText, waitingAI, loadThreads, selectThread, newThread, send, removeThread,
    connectWs, disconnectWs,
    analysisSteps, analysisRunning, analysisBusy, analysisError,
    analysisPrompt, analysisConfirm, analysisActive,
    runAnalysis, replyAnalysis, skipAnalysis, confirmAnalysis, acceptAllAnalysis,
  }
}
