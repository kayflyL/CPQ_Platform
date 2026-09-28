/**
 * 统一门户 · 业务商机详情 API（/api/portal/opp/{oppId}）。
 * 后端：app/api/portal.py；设计：docs/协作流程方案/02-business-detail.md。
 * 需求单数据模型 = RequirementSlots 契约（后端可直接消费，无需反向抽取）。
 */
import axios from 'axios'

/** RequirementSlots 契约（与 LLM_UNDERSTAND_SCHEMA 同构；单值槽位存裸值） */
export interface RequirementSlots {
  server_type?: string
  server_model?: string
  platform_type?: string
  chassis_form?: string
  purchase_qty?: number
  warranty_years?: string
  config_relation?: string   // compose=组合拆分 / alternative=方案备选对比
  primary_config?: string    // 方案备选下的主推配置名（默认第一个配置）
  cpu?: { model?: string; brand?: string; qty?: number; cores?: number; tdp_w?: number }
  memory?: { per_stick_gb?: number; qty?: number; type?: string; speed_mt?: number; brand?: string }
  storage?: Array<{ capacity?: string; interface?: string; brand?: string; qty?: number }>
  gpu?: Array<{ model?: string; brand?: string; qty?: number }>
  nic?: Array<{ model?: string; brand?: string; speed_g?: number; ports?: number; qty?: number }>
  kp_rows?: Array<{
    category?: string
    part_category?: string
    catalogue?: string
    description?: string
    qty?: number
    note?: string
  }>
  configs?: Array<{
    name?: string
    server_model?: string
    platform_type?: string
    server_type?: string
    chassis_form?: string
    warranty_years?: string
    description?: string
    qty?: number
    kp_rows?: Array<{
      category?: string
      part_category?: string
      catalogue?: string
      description?: string
      qty?: number
      note?: string
    }>
  }>
  raid?: Array<{ model?: string; qty?: number; cache?: string | number | null }>
  psu?: { wattage?: number; qty?: number; redundancy?: string }
  [key: string]: any
}

export interface RequirementVersion {
  id: number
  opportunity_id: string
  version: number
  slots: RequirementSlots
  requirement_text: string
  status: 'draft' | 'current' | 'archived'
  created_by: string
  created_at: string
}

export interface FlowInfo {
  flow_id: string
  opportunity_id: string
  current_node: 'requirement' | 'assign' | 'boming' | 'costing' | 'quoting'
  status: string
  assignees: Record<string, string>
  created_at: string
  updated_at: string
}

export interface FlowNode {
  id: number
  flow_id: string
  node_key: string
  node_label: string
  version_tag: string
  actor: string
  action: 'submit' | 'assign' | 'complete' | 'return' | 'draft'
  comment: string
  artifacts: Record<string, any>
  locked?: boolean
  created_at: string
}

export interface PortalOpp {
  opportunity: {
    opportunity_id: string
    customer_name: string
    sales_person: string
    fae: string
    quotation_person: string
    industry: string
    delivery_region: string
    delivery_cycle: string
    warranty_years: string
    order_type: string
    platform_type: string
    chassis_form: string
    purchase_qty: number
    result: string
  }
  flow: FlowInfo
}

export interface FinalQuote {
  quotation_id: string
  version?: string
  quotation_name?: string
  total_price?: number
  quotation_date?: string
  exported_at?: string | null
  [key: string]: any
}

export interface BomRow {
  catalogue?: string
  description?: string
  part_category?: string
  qty?: number
  [key: string]: any
}

export interface BomConfig {
  name: string
  server_model?: string
  description?: string
  qty: number
  l6_rows: BomRow[]
  kp_rows: BomRow[]
}

export interface CostConfig {
  name: string
  server_model?: string
  description?: string
  qty: number
  l6_items?: BomRow[]
  totals: {
    l6Cost?: number
    kpCost?: number
    warrantyCost?: number
    l6Sales?: number
    kpSales?: number
    warrantySales?: number
    totalCost?: number
    totalSales?: number
    profit?: number
    marginPct?: number
    [key: string]: any
  }
  kp_items: Array<{
    cat?: string
    name?: string
    qty?: number
    cost?: number
    sales?: number
    margin?: number
    [key: string]: any
  }>
}

export interface PortalSheetRow {
  item_id?: number
  category?: string
  part_category?: string
  catalogue: string
  description: string
  qty: number
  base_price?: number
  final_price?: number
  profit_margin?: number
  currency?: string
  note?: string
}

export interface PortalSheetConfig {
  name: string
  server_model?: string
  description?: string
  qty: number
  l6_cost?: number
  l6_margin?: number
  l6_rows: PortalSheetRow[]
  kp_rows: PortalSheetRow[]
  totals: Record<string, any>
}

export interface WorktableCostSheet {
  sheet_id: number
  sheet_name: string
  status: string
  quotation_id: string
  quotation_exported: boolean
  quotation_deleted?: boolean
  bom_configs: BomConfig[]
  cost_configs: CostConfig[]
}

export interface QuoteContext {
  bom_configs: BomConfig[]
  cost_configs: CostConfig[]
  worktable_quotation_id: string | null
  cost_snapshot: Record<string, any> | null
  worktable_cost_sheets?: WorktableCostSheet[]
}

export interface BomScheme {
  id: number
  opportunity_id: string
  name: string
  status: 'draft' | 'current' | 'archived'
  configs: PortalSheetConfig[]
  config_relation?: string   // compose=组合拆分 / alternative=方案备选对比
  primary_config?: string    // 方案备选下的主推配置名
  created_by: string
  created_at: string
  updated_at: string
}

export interface FlowCardEntity {
  id: number
  flow_card_id: number
  opportunity_id: string
  entity_type: 'requirement' | 'bom' | 'cost' | 'quote'
  entity_id: string
  created_at: string
}

export interface FlowCard {
  id: number
  opportunity_id: string
  origin_node: string
  current_node: string
  flow_status: string
  assignee_name: string
  visible_upstream: boolean
  withdraw_status: string
  withdraw_reason: string
  withdraw_requested_at: string
  returned_from_node: string
  created_by: string
  created_at: string
  updated_at: string
  entities: FlowCardEntity[]
}

export interface CostSheet {
  id: number
  opportunity_id: string
  bom_scheme_id: number | null
  name: string
  status: 'draft' | 'current' | 'archived'
  configs: PortalSheetConfig[]
  quotation_id: string
  quotation_exported?: boolean
  quotation_deleted?: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface PortalBoard {
  opportunity: PortalOpp['opportunity']
  flow: FlowInfo
  nodes: FlowNode[]
  requirements: RequirementVersion[]
  draft_requirement: RequirementVersion | null
  current_version: number | null
  requirement: RequirementVersion | null
  bom_schemes: BomScheme[]
  cost_sheets: CostSheet[]
  bom: {
    locked: boolean
    quotation_id: string | null
    quotation_name: string
    configs: BomConfig[]
  }
  cost: {
    locked: boolean
    snapshot: Record<string, any> | null
    configs: CostConfig[]
  }
  quote_context: QuoteContext
  quote: FinalQuote | null
  approvals: ApprovalItem[]
  flow_cards: FlowCard[]
}

export interface ApprovalItem {
  key: string
  label: string
  assignee: string
  state: 'pending' | 'current' | 'done'
  status_label: string
  has_return: boolean
  latest_time: string
  latest_comment: string
  latest_action: string
}

/** 门户商机卡片（列表行） */
export interface PortalOppCard {
  opportunity_id: string
  customer_name: string
  sales_person: string
  platform_type: string
  chassis_form: string
  purchase_qty: number
  industry: string
  order_type: string
  config_count: number
  quotation_count: number
  result: string
  created_at: string
  updated_at: string
  current_node: string
  flow_status: string
}

export interface PortalOppSummary {
  total: number
  returned: number
  in_progress: number
  done: number
}

/** 节点任务模式（node=boming|costing|quoting）下 /api/portal/opps 的 summary */
export interface PortalOppNodeSummary {
  total: number
  today: number
  mine: number
}

export interface PortalAssignmentRule {
  id: number
  business_user_id: string
  node_key: string
  assignee_name: string
  created_at: string
  updated_at: string
}

export interface PricingApproval {
  id: number
  opportunity_id: string
  quotation_id: string
  margin_pct: number
  threshold: number
  status: 'pending' | 'approved' | 'rejected'
  requested_by: string
  decided_by: string
  decided_at: string
  comment: string
  created_at: string
}

export interface PortalTransferRecord {
  time: string
  opportunity_id: string
  customer_name: string
  node_key: string
  node_label: string
  from_assignee: string
  to_assignee: string
  actor: string
}

/** 调度快照：单节点负载（处理人姓名→活跃任务数） */
export interface DispatchNodeLoad {
  key: string
  label: string
  workload: Array<{ name: string; count: number }>
  unassigned_count: number
}

/** 调度快照：无主任务（当前节点无处理人的活跃流程） */
export interface DispatchStuckItem {
  opportunity_id: string
  customer_name: string
  flow_id: string
  current_node: string
  node_label: string
  updated_at: string
  stuck_days: number
  suggest: string
}

export interface PortalDispatchData {
  businesses: Array<{ user_id: string; name: string }>
  rules: PortalAssignmentRule[]
  transfers: PortalTransferRecord[]
  nodes: DispatchNodeLoad[]
  stuck: DispatchStuckItem[]
  /** owner_user_id → node_key → 活跃任务数 */
  matrix: Record<string, Record<string, number>>
}

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

/** 工作台「待处理事项」单项（后端 /api/portal/todo-summary） */
export interface TodoSummaryItem {
  key: string
  label: string
  count: number
  level: 'hot' | 'act' | 'dim'
  to: string
}

export const portalApi = {
  /** 待处理事项：按当前账号角色返回口径化计数（工作台 hero 角标）+ 全局流程阶段分布（流程条） */
  todoSummary: () => RESP<{ role: string; items: TodoSummaryItem[]; stages?: Record<string, number> }>(axios.get('/api/portal/todo-summary')),
  oppCards: (params?: { page?: number; page_size?: number; search?: string; sort_by?: string; sort_order?: string; node?: string; scope?: 'mine' | 'all' }) =>
    RESP<{ cards: PortalOppCard[]; total: number; summary: PortalOppSummary | PortalOppNodeSummary }>(axios.get('/api/portal/opps', { params })),
  opp: (oppId: string) => RESP<PortalOpp>(axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}`)),
  board: (oppId: string) => RESP<PortalBoard>(axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/board`)),
  requirements: (oppId: string) =>
    RESP<{ requirements: RequirementVersion[]; current_version: number | null }>(
      axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/requirements`)),
  requirement: (oppId: string, version: number) =>
    RESP<RequirementVersion>(axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/requirements/${version}`)),
  submitRequirement: (oppId: string, slots: RequirementSlots, requirement_text: string) =>
    RESP<{ requirement: RequirementVersion }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/requirements`, { slots, requirement_text })),
  saveRequirementDraft: (oppId: string, slots: RequirementSlots, requirement_text: string) =>
    RESP<{ requirement: RequirementVersion }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/requirements/draft`, { slots, requirement_text })),
  submitRequirementDraft: (oppId: string, version: number, assignee_name = '') =>
    RESP<{ requirement: RequirementVersion }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/requirements/${version}/submit`, { assignee_name })),
  deleteRequirementDraft: (oppId: string, version: number) =>
    RESP<{ ok: boolean }>(axios.delete(`/api/portal/opp/${encodeURIComponent(oppId)}/requirements/${version}`)),
  initiate: (oppId: string, opportunity: Record<string, any>, slots: RequirementSlots, requirement_text: string, assignee_name = '') =>
    RESP<{ requirement: RequirementVersion }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/initiate`, { opportunity, slots, requirement_text, assignee_name })),
  listBomSchemes: (oppId: string) =>
    RESP<{ bom_schemes: BomScheme[] }>(
      axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/bom-schemes`)),
  saveBomSchemeDraft: (oppId: string, data: { scheme_id?: number | null; expected_updated_at?: string; flow_card_id?: number | null; name: string; configs: PortalSheetConfig[]; config_relation?: string; primary_config?: string }) =>
    RESP<{ scheme: BomScheme; bom_schemes: BomScheme[] }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/bom-schemes/draft`, data)),
  submitBomScheme: (oppId: string, schemeId: number, assignee_name = '') =>
    RESP<{ scheme: BomScheme; bom_schemes: BomScheme[]; flow: FlowInfo; nodes: FlowNode[] }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/bom-schemes/${schemeId}/submit`, { assignee_name })),
  deleteBomScheme: (oppId: string, schemeId: number) =>
    RESP<{ ok: boolean; bom_schemes: BomScheme[] }>(
      axios.delete(`/api/portal/opp/${encodeURIComponent(oppId)}/bom-schemes/${schemeId}`)),
  listCostSheets: (oppId: string) =>
    RESP<{ cost_sheets: CostSheet[] }>(
      axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/cost-sheets`)),
  saveCostSheetDraft: (oppId: string, data: {
    sheet_id?: number | null
    expected_updated_at?: string
    flow_card_id?: number | null
    name: string
    configs: PortalSheetConfig[]
    bom_scheme_id?: number | null
    quotation_id?: string | null
  }) =>
    RESP<{ sheet: CostSheet; cost_sheets: CostSheet[] }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cost-sheets/draft`, data)),
  submitCostSheet: (oppId: string, sheetId: number, assignee_name = '') =>
    RESP<{ sheet: CostSheet; cost_sheets: CostSheet[]; flow: FlowInfo; nodes: FlowNode[]; quotation_id: string }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cost-sheets/${sheetId}/submit`, { assignee_name })),
  deleteCostSheet: (oppId: string, sheetId: number) =>
    RESP<{ ok: boolean; cost_sheets: CostSheet[] }>(
      axios.delete(`/api/portal/opp/${encodeURIComponent(oppId)}/cost-sheets/${sheetId}`)),
  uploadCostSheet: (oppId: string, file: File, parseOverrides?: Record<string, any>) => {
    const fd = new FormData()
    fd.append('file', file)
    if (parseOverrides && Object.keys(parseOverrides).length) {
      fd.append('parse_overrides', JSON.stringify(parseOverrides))
    }
    return RESP<{ sheet: CostSheet; cost_sheets: CostSheet[] }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cost-sheets/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }))
  },
  listCards: (oppId: string) =>
    RESP<{ cards: FlowCard[] }>(axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/cards`)),
  returnCard: (oppId: string, cardId: number, comment = '') =>
    RESP<{ card: FlowCard }>(axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cards/${cardId}/return`, { comment })),
  requestWithdrawCard: (oppId: string, cardId: number, comment = '') =>
    RESP<{ card: FlowCard }>(axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cards/${cardId}/withdraw`, { comment })),
  approveWithdrawCard: (oppId: string, cardId: number) =>
    RESP<{ card: FlowCard }>(axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cards/${cardId}/withdraw/approve`)),
  rejectWithdrawCard: (oppId: string, cardId: number, reason = '') =>
    RESP<{ card: FlowCard }>(axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/cards/${cardId}/withdraw/reject`, { reason })),
  convertCostToQuotation: (oppId: string, quotationId: string) =>
    RESP<{ ok: boolean; quotation_id: string }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/convert-to-quotation`, { quotation_id: quotationId })),
  submitQuote: (oppId: string, quotationId: string, data: { attachment_id: string; comment?: string }) =>
    RESP<{ ok: boolean; quotation_id: string; submitted_attachment_id: string; message: any }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/quotes/${encodeURIComponent(quotationId)}/submit`, data)),
  oppPricingApprovals: (oppId: string) =>
    RESP<{ approvals: PricingApproval[] }>(
      axios.get(`/api/portal/opp/${encodeURIComponent(oppId)}/pricing-approvals`)),
  decidePricingApproval: (oppId: string, approvalId: number, data: { decision: 'approve' | 'reject'; comment?: string }) =>
    RESP<{ approval: PricingApproval }>(
      axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/pricing-approvals/${approvalId}/decide`, data)),
  dispatch: () => RESP<PortalDispatchData>(axios.get('/api/portal/dispatch')),
  dispatchAutofill: (data?: { opportunity_ids?: string[] }) =>
    RESP<{ filled: number; unresolved: number; failed: number }>(
      axios.post('/api/portal/dispatch/autofill', data || {})),
  assignOptions: () =>
    RESP<{ businesses: Array<{ user_id: string; name: string }>; assignees: Record<string, string[]> }>(
      axios.get('/api/portal/assign-options')),
  assignmentRules: (businessUserId: string) =>
    RESP<{ rules: PortalAssignmentRule[] }>(
      axios.get(`/api/portal/assignment-rules/${encodeURIComponent(businessUserId)}`)),
  saveAssignmentRule: (data: { business_user_id: string; node_key: string; assignee_name: string }) =>
    RESP<{ rule: PortalAssignmentRule }>(axios.put('/api/portal/assignment-rules', data)),
  deleteAssignmentRule: (data: { business_user_id: string; node_key: string }) =>
    RESP<{ ok: boolean }>(axios.delete('/api/portal/assignment-rules', { data })),
  transfer: (oppId: string, data: { node_key: string; assignee_name: string }) =>
    RESP<{ flow: FlowInfo; nodes: FlowNode[] }>(axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/transfer`, data)),
  assignTask: (oppId: string, data: { node_key: string; assignee_name: string; save_rule?: boolean }) =>
    RESP<{ flow: FlowInfo; nodes: FlowNode[] }>(axios.post(`/api/portal/opp/${encodeURIComponent(oppId)}/assign`, data)),
}
