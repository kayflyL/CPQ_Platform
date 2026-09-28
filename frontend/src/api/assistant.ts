/**
 * Assistant API client — 全局「方案助手」AI 聊天窗(骨架期,LLM 待接国产模型).
 * 独立 axios + Bearer token（身份由后端 JWT 解析）。
 */
import axios from 'axios'
import type { AxiosInstance } from 'axios'
import { AUTH_TOKEN_KEY } from './auth'
import { attachAuthInterceptors } from './authHttp'

export interface AssistantThread {
  thread_id: string
  title: string
  thread_kind?: 'assistant' | 'office_colleague'
  colleague_role_key?: string
  colleague_name?: string
  created_by_name?: string
  first_message?: string
  last_message?: string
  entry_point?: string
  role_counts?: Record<string, number>
  opportunity_id: string
  quotation_id: string
  created_by: string
  created_at: string
  updated_at: string
  /** 管理页（scope=all）扩展字段 */
  deleted_at?: string
  msg_count?: number
}
/** 服务端任务态快照（messages 端点随 turn_active 下发，任务胶囊对账重建用，2026-09-13） */
export interface TaskStateSnapshot {
  title: string
  steps: Array<{ key?: string; step?: string; label?: string }>
  done: string[]
  phase: 'running' | 'paused'
  pause: Record<string, any> | null
}

export interface AssistantMessage {
  message_id: string
  thread_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  /** text | business_artifact */
  kind?: string
  /** 本条 assistant 消息由哪位 AI 同事生成（群聊头像/昵称展示用） */
  colleague_role_key?: string
  /** 结构化载荷 JSON（如业务草稿） */
  data?: string
  opportunity_id: string
  quotation_id: string
  created_at: string
}
export interface AssistantContext {
  opportunityId?: string | null
  quotationId?: string | null
  entryPoint?: string
}

/** AI 工具目录条目（注册表 agent_tool_specs + 人类展示层 agent_tool_display + DB 覆盖 agent_tool_text） */
export interface AssistantToolInfo {
  name: string
  category: 'selection' | 'data' | 'cost' | 'quote'
  /** 中文名（人类层） */
  display_name?: string
  /** 一句话（人类层） */
  one_liner?: string
  /** 模型 FC 契约（每回合注入大脑；DB 可覆盖，编辑受宪法 lint 约束） */
  summary?: string
  /** 人话详解（只给人看） */
  description: string
  parameters: Record<string, any>
  default_enabled: boolean
  /** 被 DB 覆盖的字段名（前端标「已自定义」/提供恢复默认） */
  custom?: string[]
}

export interface ToolTextPayload {
  display_name?: string
  one_liner?: string
  description?: string
  model_brief?: string
}

const http: AxiosInstance = axios.create({ baseURL: '', timeout: 60000 })
attachAuthInterceptors(http)

export const assistantApi = {
  /** AI 同事配置（群聊式头像/昵称展示 + 转接目标） */
  aiColleagues: {
    list: () =>
      http
        .get<{ colleagues: any[]; dispatch_enabled?: boolean; dispatch_rules?: any[] }>('/api/ai-colleagues/')
        .then((r) => r.data),
  },
  /** AI 工具目录；usage = 工具名 → 引用它的节点标签（活跃流生效集） */
  tools: {
    catalog: () =>
      http
        .get<{ tools: AssistantToolInfo[]; usage?: Record<string, string[]> }>('/api/assistant/tools')
        .then((r) => ({ tools: r.data.tools, usage: r.data.usage || {} })),
    /** 编辑工具文案（DB 覆盖层；model_brief 保存受宪法 lint 约束，命中会被 400 拒） */
    updateText: (name: string, payload: ToolTextPayload) =>
      http
        .put<{ tool: AssistantToolInfo }>(`/api/assistant/tools/${name}/text`, payload)
        .then((r) => r.data.tool),
    /** 整工具恢复默认文案（删 DB 覆盖行） */
    resetText: (name: string) =>
      http
        .delete<{ tool: AssistantToolInfo }>(`/api/assistant/tools/${name}/text`)
        .then((r) => r.data.tool),
  },
  threads: {
    list: (opts?: { includeDeleted?: boolean }) =>
      http.get<{ threads: AssistantThread[] }>('/api/assistant/threads', {
        params: { include_deleted: opts?.includeDeleted ? 1 : undefined },
      }).then((r) => r.data.threads),
    listOffice: (
      roleKey: string,
      options?: { includeDeleted?: boolean; includePreview?: boolean },
    ) =>
      http
        .get<{ threads: AssistantThread[] }>('/api/assistant/threads', {
          params: {
            thread_kind: 'office_colleague',
            role_key: roleKey,
            include_deleted: options?.includeDeleted ? 1 : undefined,
            include_preview: options?.includePreview ? 1 : undefined,
          },
        })
        .then((r) => r.data.threads),
    /** 获取或创建当前账号与指定 AI 角色的统一会话（所有入口共享同一 thread）。 */
    resolve: (roleKey: string, ctx?: AssistantContext) =>
      http
        .post<{ thread: AssistantThread }>('/api/assistant/threads/resolve', {
          role_key: roleKey,
          opportunity_id: ctx?.opportunityId || null,
          quotation_id: ctx?.quotationId || null,
          entry_point: ctx?.entryPoint || null,
        })
        .then((r) => r.data.thread),
    rename: (id: string, title: string) =>
      http
        .patch<{ thread: AssistantThread }>(`/api/assistant/threads/${encodeURIComponent(id)}`, { title })
        .then((r) => r.data.thread),
    create: (ctx?: AssistantContext, title?: string, openingRoleKey?: string, threadKind?: 'assistant' | 'office_colleague') =>
      http
        .post<{ thread: AssistantThread }>('/api/assistant/threads', {
          title,
          opportunity_id: ctx?.opportunityId || null,
          quotation_id: ctx?.quotationId || null,
          opening_role_key: openingRoleKey || null,
          thread_kind: threadKind || 'assistant',
          entry_point: ctx?.entryPoint || null,
        })
        .then((r) => r.data.thread),
    remove: (id: string) => http.delete(`/api/assistant/threads/${id}`),
    /** 团队群会话（未绑定同事的总助线程）get-or-create */
    groupResolve: (payload?: { entry_point?: string }) =>
      http
        .post<{ thread: AssistantThread }>('/api/assistant/threads/group-resolve', {
          entry_point: payload?.entry_point || null,
        })
        .then((r) => r.data),
    /** AI 设置·会话记录：管理员列全部会话（含回收站 + 消息数） */
    listAll: (filters?: {
      thread_kind?: string
      role_key?: string
      created_by?: string
      keyword?: string
    }) =>
      http
        .get<{ threads: AssistantThread[] }>('/api/assistant/threads', {
          params: { scope: 'all', ...(filters || {}) },
        })
        .then((r) => r.data.threads),
    /** 回收站恢复（同角色当前活跃会话自动归档换位） */
    restore: (id: string) =>
      http
        .post<{ thread: AssistantThread }>(`/api/assistant/threads/${encodeURIComponent(id)}/restore`)
        .then((r) => r.data.thread),
    /** 彻底删除（消息+状态一起物理清） */
    purge: (id: string) => http.delete(`/api/assistant/threads/${id}`, { params: { hard: 1 } }),
    /** 一键清理空会话（0 消息，硬删除） */
    cleanupEmptyThreads: () =>
      http.post<{ deleted: number }>('/api/assistant/admin/cleanup/empty-threads').then((r) => r.data.deleted),
    /** LLM 调用痕迹清理：只保留最近 keepDays 天 */
    cleanupTrace: (keepDays: number) =>
      http.post('/api/assistant/admin/cleanup/trace', { keep_days: keepDays }),
    /** AI 同事审计/绩效面板（方案助手 LLM 与工具调用 trace） */
    audit: () =>
      http
        .get<{ calls: number; tool_calls: number; avg_duration_ms: number; success_rate: number; by_node: any[]; last_calls: any[] }>(
          '/api/assistant/admin/audit',
        )
        .then((r) => r.data),
    /** 需求反馈样本清理：保留最近 keepN 条（0=全清） */
    cleanupSamples: (keepN: number) =>
      http.post('/api/assistant/admin/cleanup/samples', { keep_n: keepN }),
    messages: (id: string, limit?: number) =>
      http
        .get<{ messages: AssistantMessage[] }>(`/api/assistant/threads/${id}/messages`, {
          params: limit ? { limit } : undefined,
        })
        .then((r) => r.data.messages),
    /** 会话消息 + 上下文水位（估算 token 占比） */
    messagesFull: (id: string, limit?: number) =>
      http
        .get<{
          messages: AssistantMessage[]
          turn_active?: boolean
          task_state?: TaskStateSnapshot | null
          context_usage?: { chars: number; est_tokens: number; limit_tokens: number; ratio: number }
        }>(`/api/assistant/threads/${id}/messages`, {
          params: limit ? { limit } : undefined,
        })
        .then((r) => r.data),
    /** 会话消息 + 回合在跑事实（看门狗终态判定：无新消息 + turn_active=false = 回合必已结束） */
    messagesWithState: (id: string, limit?: number) =>
      http
        .get<{
          messages: AssistantMessage[]
          turn_active?: boolean
          task_state?: TaskStateSnapshot | null
          context_usage?: { chars: number; est_tokens: number; limit_tokens: number; ratio: number }
        }>(`/api/assistant/threads/${id}/messages`, {
          params: limit ? { limit } : undefined,
        })
        .then((r) => r.data),
    postMessage: (
      id: string,
      content: string,
      contextSummary?: string,
      roleKey?: string,
      opportunityId?: string | null,
      quotationId?: string | null,
      entryPoint?: string,
      optionSlot?: string | null,
      cardSelections?: Array<{ slot: string; value: string; label?: string; qty?: number }> | null,
      workflowKey?: string | null,
    ) =>
      http
        .post<{ user_message: AssistantMessage; thread: AssistantThread; colleague?: any }>(
          `/api/assistant/threads/${id}/messages`,
          {
            content,
            context_summary: contextSummary || null,
            role_key: roleKey || null,
            opportunity_id: opportunityId || null,
            quotation_id: quotationId || null,
            entry_point: entryPoint || null,
            option_slot: optionSlot || null,
            card_selections: cardSelections && cardSelections.length
              ? cardSelections.map((s) => ({
                  slot: s.slot, value: s.value, label: s.label || null,
                  ...(s.qty ? { qty: s.qty } : {}),
                }))
              : null,
            workflow_key: workflowKey || null,
          },
        )
        .then((r) => r.data),
    stop: (id: string) =>
      http.post<{ status: string }>(`/api/assistant/threads/${encodeURIComponent(id)}/stop`).then((r) => r.data),
    /** 配件库自选候选：服务端按留底卡 pick_meta 生成并登记，选项与发卡同格式（含 slot/value/label） */
    cardPick: (id: string, slot: string, roleKey?: string) =>
      http
        .get<{ slot: string; options: Array<{ label: string; value: string; desc?: string; slot: string; group?: string; qty?: number; qty_max?: number }> }>(
          `/api/assistant/threads/${id}/card-pick`,
          { params: { slot, ...(roleKey ? { role_key: roleKey } : {}) } },
        )
        .then((r) => r.data),
    /** 发送前预览总助推荐同事（不落库） */
    resolveTarget: (id: string, content: string, contextSummary?: string) =>
      http
        .post<{ colleague?: any; reason?: string }>(
          `/api/assistant/threads/${id}/dispatch-preview`,
          { content, context_summary: contextSummary || null },
        )
        .then((r) => r.data),
  },

}

/** WS 订阅某会话的 LLM token 流(chunk / done 由后端 _stream_llm_reply 广播)。 */
export function assistantWsUrl(threadId: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${proto}://${location.host}/api/assistant/ws/${encodeURIComponent(threadId)}${query}`
}
