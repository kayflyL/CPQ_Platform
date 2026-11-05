/**
 * 线索池 API（登录态，主应用）—— 公开线索的人工筛选与转化分配。
 */
import axios from 'axios'
import type { RequirementSlots } from './portal'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface LeadRecord {
  lead_id: string
  source: string
  status: string                      // new / confirmed / converting / assigned / rejected / deleted
  company: string
  contact_name: string
  contact_phone: string
  contact_email: string
  delivery_region: string             // 交付地区（国内-广东 / 海外-日本 / 海外-不在列表中），转化时原样写入商机
  requirement_text: string
  config_slots: RequirementSlots | null
  expected_delivery: string
  attachments: Array<{ storage_key: string; name: string; size: number }> | []
  dedup_count: number
  reject_reason: string
  reject_note: string
  converted_opportunity_id: string
  assigned_business_user_id: string
  created_at: string
  updated_at: string
}

export const leadsApi = {
  list: (params: { status?: string; search?: string; page?: number; page_size?: number }) =>
    RESP<{ items: LeadRecord[]; total: number; page: number; page_size: number }>(
      axios.get('/api/leads', { params })),
  get: (leadId: string) => RESP<LeadRecord>(axios.get(`/api/leads/${leadId}`)),
  businessOptions: () => RESP<{ options: Array<{ user_id: string; name: string }> }>(
    axios.get('/api/leads/business-options')),
  confirm: (leadId: string) => RESP<{ ok: boolean; status: string }>(
    axios.post(`/api/leads/${leadId}/confirm`)),
  convert: (leadId: string, assigneeUserId: string) =>
    RESP<{ ok: boolean; opportunity_id: string; requirement_version: number }>(
      axios.post(`/api/leads/${leadId}/convert`, { assignee_user_id: assigneeUserId })),
  reject: (leadId: string, reason: string, note: string) =>
    RESP<{ ok: boolean }>(axios.post(`/api/leads/${leadId}/reject`, { reason, note })),
  remove: (leadId: string) => RESP<{ ok: boolean }>(axios.post(`/api/leads/${leadId}/delete`)),
  restore: (leadId: string) => RESP<{ ok: boolean; status: string }>(axios.post(`/api/leads/${leadId}/restore`)),
  attachmentUrl: (leadId: string, index: number) => `/api/leads/${leadId}/attachments/${index}`,
}
