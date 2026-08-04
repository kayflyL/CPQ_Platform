/**
 * useReasoningStream — 商机详情页推理面板的状态 + WS 接收.
 *
 * 与 useAssistant 物理隔离：独立 WS /api/reasoning/ws/{oid}，按 opportunity_id 分房间。
 * 收 step_start/step_done 驱动步骤时间线，收 candidates_ready 下发候选清单。
 */
import { ref } from 'vue'
import { reasoningWsUrl } from '@/api/reasoning'
import type { Plan } from '@/api/reasoning'

export type StepStatus = 'pending' | 'running' | 'done' | 'error'

export interface ReasoningStep {
  key: string
  label: string
  status: StepStatus
  payload?: any
}

export interface ConfirmItem {
  id: string
  slot: string
  label: string
  rule?: string | null
  llm?: string | null
  level: 'conflict' | 'low_confidence'
  confidence?: number
  default?: string
}

/** 二期占位步骤（面板内灰显，对应流程图虚线框） */
export const FUTURE_STEPS: { key: string; label: string }[] = [
  { key: 'llm_best_fit', label: 'LLM 语义择优（判断"最合适"）' },
  { key: 'vector_sim', label: '历史 BOM 向量相似度检测' },
  { key: 'auto_tune', label: '自动调整检索参数' },
  { key: 'history_pricing', label: '历史报价接入定价' },
  { key: 'segment_pricing', label: '精细化客户分层 / 阶梯加成' },
  { key: 'online_approval', label: '线上特价审批' },
  { key: 'auto_loopback', label: '驳回自动回流修正' },
]

export function useReasoningStream() {
  const steps = ref<ReasoningStep[]>([])
  const plans = ref<Plan[]>([])
  const running = ref(false)
  const error = ref<string | null>(null)
  const keywords = ref<string[]>([])
  const series = ref<string | null>(null)
  const form = ref<string | null>(null)
  /** 反问待回复（ask_user 节点触发，pipeline 暂停等用户补齐） */
  const pendingPrompt = ref<{
    reply_id: string
    question: string
    missing_fields: string[]
    options: string[]
    round: number
    clarity_capped: boolean
    stage?: string      // 目录驱动引导阶段：type/model/kp
    format?: string     // KP 填写格式模板（引导客户按格式回复）
  } | null>(null)
  /** LLM 确认面板待决策项（confirm 节点触发：冲突/低置信度，默认采纳可改） */
  const pendingConfirm = ref<{
    reply_id: string
    question: string
    items: ConfirmItem[]
    default: string
  } | null>(null)
  /** 当前 pipeline_id（过滤过期消息，防并发/重跑交错） */
  const currentPipelineId = ref<string | null>(null)

  let ws: WebSocket | null = null

  function reset() {
    steps.value = []
    plans.value = []
    error.value = null
    keywords.value = []
    series.value = null
    form.value = null
    pendingPrompt.value = null
    pendingConfirm.value = null
    currentPipelineId.value = null
  }

  function setStep(key: string, status: StepStatus, payload?: any) {
    const i = steps.value.findIndex((s) => s.key === key)
    if (i >= 0) {
      steps.value[i] = { ...steps.value[i], status, payload: payload ?? steps.value[i].payload }
    }
  }

  function connect(opportunityId: string) {
    disconnect()
    reset()
    running.value = true
    try {
      ws = new WebSocket(reasoningWsUrl(opportunityId))
    } catch {
      ws = null
      running.value = false
      error.value = '推理通道连接失败'
      return
    }
    ws.onmessage = (ev) => {
      let data: any
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      // 过滤过期 pipeline 消息（重跑/并发时旧事件丢弃）
      if (data.type !== 'pipeline_start' && data.pipeline_id && currentPipelineId.value
          && data.pipeline_id !== currentPipelineId.value) {
        return
      }
      switch (data.type) {
        case 'pipeline_start':
          // 重跑也走这里：新一轮必须重新置 running（上一轮 pipeline_paused 已置 false，
          // 否则 typing 指示不出、用户感觉"发送没反应"）
          running.value = true
          error.value = null
          if (data.pipeline_id) currentPipelineId.value = data.pipeline_id
          steps.value = (data.steps || []).map((s: any) => ({
            key: s.key,
            label: s.label,
            status: 'pending' as StepStatus,
          }))
          plans.value = []
          pendingPrompt.value = null  // 新轮次清旧反问
          pendingConfirm.value = null // 新轮次清旧确认
          break
        case 'step_start':
          setStep(data.step, 'running')
          break
        case 'step_done':
          setStep(data.step, 'done', data.payload)
          break
        case 'need_input':
          // ask_user 节点：暂停 pipeline，等用户回复补充
          pendingPrompt.value = {
            reply_id: data.reply_id,
            question: data.question,
            missing_fields: data.missing_fields || [],
            options: data.options || [],
            round: data.round || 1,
            clarity_capped: !!data.clarity_capped,
            stage: data.stage || undefined,
            format: data.format || undefined,
          }
          break
        case 'need_confirm':
          // confirm 节点：默认采纳 LLM 补充项（面板高亮可改），pipeline 已出默认方案
          pendingConfirm.value = {
            reply_id: data.reply_id || '',
            question: data.question || '',
            items: data.items || [],
            default: data.default || 'accept',
          }
          break
        case 'candidates_ready':
          plans.value = data.plans || []
          keywords.value = data.keywords || []
          series.value = data.series || null
          form.value = data.form || null
          break
        case 'pipeline_paused':
          // pipeline 停在 ask_user 等用户回复（pendingPrompt 已由 need_input 设置）
          running.value = false
          steps.value.forEach((s) => {
            if (s.status === 'running') s.status = 'done'
          })
          break
        case 'pipeline_done':
          running.value = false
          // 兜底：任何仍 pending/running 的标记 done
          steps.value.forEach((s) => {
            if (s.status === 'pending' || s.status === 'running') s.status = 'done'
          })
          break
        case 'error':
          error.value = data.message || '推理流程异常'
          running.value = false
          steps.value.forEach((s) => {
            if (s.status === 'running') s.status = 'error'
          })
          break
      }
    }
    ws.onclose = () => {
      ws = null
    }
    ws.onerror = () => {
      /* 静默：REST 已触发 pipeline，WS 仅推流式步骤 */
    }
  }

  function disconnect() {
    if (ws) {
      ws.onclose = null
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      ws = null
    }
    running.value = false
  }

  return { steps, plans, running, error, keywords, series, form, pendingPrompt, pendingConfirm, connect, disconnect, reset }
}
