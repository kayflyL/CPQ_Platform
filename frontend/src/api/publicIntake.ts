/**
 * 公开线索汇聚 API —— 公开应用（public.html 入口）专用。
 *
 * 红线：本模块必须保持零登录态依赖——不许 import api/index、store/auth、authHttp
 * （它们会往全局 axios 挂 401 跳登录拦截器，公开访客没有 token 会被误踢）。
 * 类型复用 serverConfig.ts 的 ServerType/ServerModel/PortalBanner：公开 DTO 是其
 * 字段子集，TS 结构类型直接赋值，组件零改动消费。
 */
import axios from 'axios'
import type { ServerModel, ServerType, PortalBanner } from './serverConfig'

const http = axios.create({ baseURL: '', timeout: 30000 })

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface LeadSubmitPayload {
  requirement_text: string
  company: string
  contact_name: string
  contact_phone: string
  contact_email?: string
  expected_delivery?: string
  source?: 'catalog_model' | 'catalog_general'
  config_slots?: string            // RequirementSlots JSON（后端白名单键重建）
  files?: File[]
}

export const publicCatalogApi = {
  listTypes: () => RESP<{ types: ServerType[] }>(http.get('/api/public/catalog/types')),
  listModels: (typeId?: number) =>
    RESP<{ models: ServerModel[] }>(http.get('/api/public/catalog/models', { params: { type_id: typeId } })),
  getModel: (id: number) => RESP<ServerModel>(http.get(`/api/public/catalog/models/${id}`)),
  getBanner: () => RESP<PortalBanner>(http.get('/api/public/catalog/banner')),
  /** 线索登记表字段定义（公开表单渲染用；纯表单结构，无业务数据） */
  getSheetForm: () => RESP<{ config_fields?: Array<{ key: string; label: string; control: string; placeholder?: string; min?: number; unit?: string; bind?: string }> }>(
    http.get('/api/public/requirement-sheet-form')),
}

export const publicLeadApi = {
  submit: (data: LeadSubmitPayload) => {
    const fd = new FormData()
    fd.append('requirement_text', data.requirement_text || '')
    fd.append('company', data.company || '')
    fd.append('contact_name', data.contact_name || '')
    fd.append('contact_phone', data.contact_phone || '')
    if (data.contact_email) fd.append('contact_email', data.contact_email)
    if (data.expected_delivery) fd.append('expected_delivery', data.expected_delivery)
    fd.append('source', data.source || 'catalog_general')
    if (data.config_slots) fd.append('config_slots', data.config_slots)
    for (const f of data.files || []) fd.append('files', f)
    return RESP<{ ok: boolean; lead_id: string | null; merged: boolean }>(
      http.post('/api/public/leads', fd))
  },
}
