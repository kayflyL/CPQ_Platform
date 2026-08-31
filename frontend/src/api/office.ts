/**
 * AI office API client — AI Office 快照 + WebSocket 地址 + 团队/布局写接口。
 */
import axios from 'axios'
import { AUTH_TOKEN_KEY } from './auth'
import { attachAuthInterceptors } from './authHttp'

export interface OfficeColleagueStatus {
  id?: number | string
  event_type?: string
  type: string
  role_key: string
  status: string
  revision?: number
  activity?: string
  message?: string
  tool?: string | null
  thread_id?: string | null
  opportunity_id?: string | null
  zone?: string
  intent?: string
  participants?: string[]
  conversation_id?: string
  task_id?: string
  approval_required?: boolean
  priority?: string
  summary?: string
  assignments?: Array<{ role_key: string; task: string }>
  conclusion?: string
  actor?: string | null
  source?: string
  mission_id?: string | null
  assignment_id?: string | null
  assignment_status?: string
  step_id?: string | null
  result_summary?: string
  ts?: number
}

export interface OfficeSnapshot {
  snapshot: Record<string, OfficeColleagueStatus>
}

export interface OfficeZoneSlot {
  id: string
  role_key?: string | null
  position: { x: number; z: number }
  rotation_y?: number | null
}

export interface OfficeDoorConfig {
  side?: 'left' | 'right' | 'front' | 'back'
  offset?: number
  width?: number
}

export interface OfficeFurnitureItem {
  id: string
  type: string
  position: { x: number; z: number }
  rotation_y: number
  variant?: string
  scale?: number
  meta?: Record<string, any>
}

export interface FurnitureDefinition {
  type: string
  label: string
  category: string
  width: number
  depth: number
  height?: number
  rotatable?: boolean
  placeable_rooms?: string[]
  variant?: string
}

export interface OfficeZone {
  id: string
  type: string
  label?: string
  aliases?: string[]
  walk_target?: 'home' | 'center' | 'meeting' | 'slot'
  shape?: 'circle' | 'rect'
  position?: { x: number; z: number }
  radius?: number
  capacity?: number
  width?: number
  depth?: number
  room?: boolean
  door?: OfficeDoorConfig
  slots: OfficeZoneSlot[]
}

export interface OfficeEnvironmentTheme {
  preset?: 'midnight' | 'daylight' | 'warm-loft'
  palette?: {
    floor?: string
    wall?: string
    wall_lower?: string
    accent?: string
    ceiling?: string
    furniture?: string
    furniture_light?: string
    foliage?: string
  }
  props?: {
    plants?: boolean
    bookshelves?: boolean
    lounge?: boolean
    coffee_bar?: boolean
    whiteboard?: boolean
    windows?: boolean
    ceiling_lights?: boolean
    art?: boolean
  }
  lighting?: {
    ambient_intensity?: number
    key_intensity?: number
    fill_intensity?: number
    window_glow?: number
  }
}

export interface OfficeConfig {
  floor?: { width: number; depth: number }
  workspace?: { width: number; depth: number }
  zones?: OfficeZone[]
  furniture?: OfficeFurnitureItem[]
  furniture_catalog?: FurnitureDefinition[]
  status_zone_map?: Record<string, string>
  character_models?: string[]
  environment_theme?: OfficeEnvironmentTheme
}

export interface BehaviorConfig {
  mission?: {
    enabled?: boolean
    owner_role_key?: string
    max_steps?: number
    max_iterations?: number
    route_delay_seconds?: number
    work_delay_seconds?: number
    done_delay_seconds?: number
    default_intent?: string
    clear_statuses?: string[]
    default_deliverable_type?: string
    collaboration_deliverable_type?: string
    deliverable_types?: Record<string, OfficeDeliverableMeta>
    status_meta?: Record<string, BehaviorStatusMeta>
    assignment_status_meta?: Record<string, BehaviorStatusMeta>
    assignment_action_map?: Record<string, string>
    collaboration?: {
      enabled?: boolean
      zone?: string
      status?: string
      intent?: string
      activity?: string
      keywords?: string[]
      max_participants?: number
    }
  }
  status_meta?: Record<string, BehaviorStatusMeta>
  collaboration_rules?: any[]
  brain?: {
    enabled?: boolean
    model_override?: string | null
    max_attempts?: number
    generate_summary?: boolean
    generate_assignments?: boolean
    generate_conclusion?: boolean
  }
  autonomous?: {
    enabled?: boolean
    tick_seconds?: number
    timezone?: string
    life: {
      enabled?: boolean
      max_actions_per_tick?: number
      cooldown_seconds?: number
      llm_enabled?: boolean
      llm_min_interval_seconds?: number
      llm_timeout_seconds?: number
      interaction_enabled?: boolean
      interaction_cooldown_seconds?: number
      allowed_zones?: string[]
      active_statuses?: string[]
      fallback_actions: Array<{
        status?: string
        intent?: string
        zone?: string
        activity?: string
        message?: string
      }>
      interaction_action?: {
        status?: string
        intent?: string
        zone?: string
        activity?: string
        message?: string
      }
    }
    idle: {
      enabled?: boolean
      after_seconds?: number
      status?: string
      intent?: string
      activity?: string
      zone?: string
    }
    schedule_rules: Array<{
      id?: string
      time?: string
      status?: string
      intent?: string
      activity?: string
      zone?: string
      roles?: string[] | string
      message?: string
      conversation_id?: string
      priority?: string
    }>
  }
}

export interface BehaviorStatusMeta {
  label?: string
  color?: string
  monitor_active?: boolean
  indicator_opacity?: number
  animation?: string
}

export interface BehaviorProfile {
  wander_enabled?: boolean
  min_idle_seconds?: number
  max_idle_seconds?: number
  preferred_zones?: Array<{
    zone?: string
    weight?: number
    activity?: string
  }>
  preferred_idle_actions?: string[]
  window_activity?: {
    enabled?: boolean
    zone?: string
    activity?: string
  }
}

export interface OfficeColleagueMemory {
  id: number
  role_key: string
  type: string
  type_label?: string
  content: string
  source?: 'auto' | 'manual'
  pinned?: boolean
  created_by?: string
  created_at?: string
  updated_at?: string
}

export interface OfficeDeliverable {
  type: string
  title?: string
  content?: string
  url?: string
  created_at?: string
  created_by?: string
}

export interface OfficeDeliverableMeta {
  label?: string
  color?: string
  icon?: string
}

export interface OfficeMissionStep {
  step_id: string
  assignment_id: string
  role_key: string
  task: string
  intent?: string
  zone?: string
  assignment_status: string
  result_summary?: string
  participants?: string[]
  collaboration?: boolean
  status?: string
  assigned_at?: string
  started_at?: string
  completed_at?: string
  completed_by?: string
  deliverables?: OfficeDeliverable[]
}

export interface OfficeMission {
  ok?: boolean
  error?: string
  mission_id: string
  owner_role_key?: string
  lead_role_key?: string
  prompt: string
  status: string
  source?: string
  planning?: boolean
  priority?: string
  created_at?: string
  updated_at?: string
  created_by?: string
  completed_at?: string
  completed_by?: string
  opportunity_id?: string
  flow_node?: string
  skill_key?: string
  artifacts?: Array<Record<string, any>>
  deliverables?: OfficeDeliverable[]
  steps: OfficeMissionStep[]
}

export interface OfficeAccessPolicy {
  enabled?: boolean
  default_room_ids?: string[]
  role_room_map?: Record<string, string[]>
  user_room_map?: Record<string, string[]>
  default_chat_role_keys?: string[]
  role_chat_role_keys?: Record<string, string[]>
  user_chat_role_keys?: Record<string, string[]>
}

export interface AiTeamConfig {
  colleagues: any[]
  dispatch_enabled?: boolean
  dispatch_rules?: any[]
  team_meta?: {
    name?: string
    description?: string
    color?: string
  }
  access_policy?: OfficeAccessPolicy
  rooms?: Array<{
    id: string
    name?: string
    description?: string
    color?: string
    role_keys?: string[]
  }>
  layout?: {
    nodes?: any[]
    edges?: any[]
    office?: OfficeConfig
    team_graph?: {
      lead_role_key?: string
      subagent_role_keys?: string[]
    }
  }
  behavior?: BehaviorConfig
}

const http = axios.create({ baseURL: '', timeout: 60000 })
attachAuthInterceptors(http)

export const officeApi = {
  snapshot: () =>
    http.get<OfficeSnapshot>('/api/office/snapshot').then((r) => r.data),
  teamConfig: () =>
    http.get<AiTeamConfig>('/api/ai-colleagues/').then((r) => r.data),
  teamConfigAdmin: () =>
    http.get<AiTeamConfig>('/api/ai-colleagues/admin-config').then((r) => r.data),
  teamRoles: () =>
    http.get<{ roles: Array<{ role_key: string; name: string }> }>('/api/ai-colleagues/manage-roles').then((r) => r.data),
  updateTeamMeta: (payload: { name?: string; description?: string; color?: string }) =>
    http.put<{ team_meta: any }>('/api/ai-colleagues/team-meta', payload).then((r) => r.data),
  updateRooms: (payload: { rooms: any[] }) =>
    http.put<{ rooms: any[] }>('/api/ai-colleagues/rooms', payload).then((r) => r.data),
  updateAccessPolicy: (payload: OfficeAccessPolicy) =>
    http.put<{ access_policy: OfficeAccessPolicy }>('/api/ai-colleagues/access-policy', payload).then((r) => r.data),
  listUsers: () =>
    http.get<{ users: Array<{ user_id: string; name: string; role?: string; is_active?: boolean }> }>('/api/ai-colleagues/manage-users').then((r) => r.data),
  updateLayout: (payload: { nodes?: any[]; edges?: any[]; office?: OfficeConfig; lead_role_key?: string }) =>
    http.put<{ layout: any }>('/api/ai-colleagues/layout', payload).then((r) => r.data),
  updateBehavior: (payload: BehaviorConfig) =>
    http.put<{ behavior: any }>('/api/ai-colleagues/behavior', { behavior: payload }).then((r) => r.data),
  listColleagueMemories: (roleKey: string, params: { keyword?: string; limit?: number } = {}) =>
    http.get<{ memories: OfficeColleagueMemory[]; total: number }>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}/memories`, { params }).then((r) => r.data),
  createColleagueMemory: (roleKey: string, payload: { type?: string; content: string; pinned?: boolean }) =>
    http.post<{ memory: OfficeColleagueMemory }>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}/memories`, payload).then((r) => r.data),
  updateColleagueMemory: (roleKey: string, memoryId: number, payload: { type?: string; content?: string; pinned?: boolean }) =>
    http.put<{ memory: OfficeColleagueMemory }>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}/memories/${memoryId}`, payload).then((r) => r.data),
  deleteColleagueMemory: (roleKey: string, memoryId: number) =>
    http.delete<{ deleted: number }>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}/memories/${memoryId}`).then((r) => r.data),
  clearColleagueMemories: (roleKey: string) =>
    http.delete<{ deleted: number; role_key: string }>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}/memories`).then((r) => r.data),
  createMission: (payload: {
    prompt: string
    owner_role_key?: string | null
    priority?: string
    opportunity_id?: string | null
    flow_node?: string | null
    skill_key?: string | null
    artifacts?: Array<Record<string, any>>
  }) =>
    http.post<OfficeMission>('/api/office/missions', payload).then((r) => r.data),
  listMissions: (limit = 50) =>
    http.get<{ missions: OfficeMission[] }>('/api/office/missions', { params: { limit } }).then((r) => r.data),
  getMission: (missionId: string) =>
    http.get<OfficeMission>(`/api/office/missions/${encodeURIComponent(missionId)}`).then((r) => r.data),
  cancelMission: (missionId: string) =>
    http.post<OfficeMission>(`/api/office/missions/${encodeURIComponent(missionId)}/cancel`).then((r) => r.data),
  retryMission: (missionId: string) =>
    http.post<OfficeMission>(`/api/office/missions/${encodeURIComponent(missionId)}/retry`).then((r) => r.data),
  deleteMission: (missionId: string) =>
    http.delete<{ deleted: string }>(`/api/office/missions/${encodeURIComponent(missionId)}`).then((r) => r.data),
  clearMissions: (statuses?: string[]) =>
    http.post<{ removed: number }>('/api/office/missions/clear', { statuses }).then((r) => r.data),
  sendIntent: (payload: { role_key: string; intent: string; status: string; zone?: string; activity?: string; message?: string }) =>
    http.post<{ published: boolean }>('/api/office/intent', payload).then((r) => r.data),
  governance: (status?: string) =>
    http.get<{ items: any[] }>('/api/office/governance', { params: status ? { status } : {} }).then((r) => r.data),
  approveGovernance: (itemId: string) =>
    http.post<{ item: any }>(`/api/office/governance/${encodeURIComponent(itemId)}/approve`).then((r) => r.data),
  batchGovernance: (action: 'approve' | 'reject', itemIds: string[], reason?: string) =>
    http.post<{ processed: any[]; skipped: any[]; failed: any[]; total_requested: number }>('/api/office/governance/batch', { action, item_ids: itemIds, reason }).then((r) => r.data),
  rejectGovernance: (itemId: string, reason?: string) =>
    http.post<{ item: any }>(`/api/office/governance/${encodeURIComponent(itemId)}/reject`, { reason }).then((r) => r.data),
  updateColleague: (roleKey: string, payload: Record<string, any>) =>
    http.put<any>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}`, payload).then((r) => r.data),
  createColleague: (payload: Record<string, any>) =>
    http.post<any>('/api/ai-colleagues/', payload).then((r) => r.data),
  deleteColleague: (roleKey: string) =>
    http.delete<any>(`/api/ai-colleagues/${encodeURIComponent(roleKey)}`).then((r) => r.data),
  scopeOptions: () =>
    http.get<{ data_sources: Array<{ key: string; label: string; description: string }>; page_scopes: Array<{ key: string; label: string; description: string; data_sources: string[] }> }>('/api/ai-colleagues/scope-options').then((r) => r.data),
  listSkills: () =>
    http.get<{ skills: any[] }>('/api/ai-colleagues/skills').then((r) => r.data.skills),

  createSkill: (payload: Record<string, any>) =>
    http.post<any>('/api/ai-colleagues/skills', payload).then((r) => r.data),
  updateSkill: (skillKey: string, payload: Record<string, any>) =>
    http.put<any>(`/api/ai-colleagues/skills/${encodeURIComponent(skillKey)}`, payload).then((r) => r.data),
  deleteSkill: (skillKey: string) =>
    http.delete<any>(`/api/ai-colleagues/skills/${encodeURIComponent(skillKey)}`).then((r) => r.data),
  updateDispatch: (payload: { dispatch_enabled?: boolean; dispatch_rules?: any[] }) =>
    http.put<{ dispatch_enabled: boolean; dispatch_rules: any[] }>('/api/ai-colleagues/dispatch', payload).then((r) => r.data),
}

export function officeWsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${proto}://${location.host}/api/office/ws${query}`
}
