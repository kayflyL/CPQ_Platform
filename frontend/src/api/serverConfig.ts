/**
 * 服务器配置相关的 API 封装（对接后端 /api/parts、/api/server-catalog、/api/base-configs、/api/derive）
 * 对应落地设计文档阶段②后端。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

// ---------- 料号库 ----------
export const partsApi = {
  list: (category?: string, search?: string) =>
    RESP<{ parts: PartMaster[]; total: number }>(axios.get('/api/parts', { params: { category, search } })),
  categories: () => RESP<{ categories: string[] }>(axios.get('/api/parts/categories')),
  get: (pn: string) => RESP<PartMaster>(axios.get(`/api/parts/${encodeURIComponent(pn)}`)),
  create: (data: Partial<PartMaster>) => RESP<{ pn: string }>(axios.post('/api/parts', data)),
  update: (pn: string, data: Partial<PartMaster>) => RESP<{ ok: boolean }>(axios.put(`/api/parts/${encodeURIComponent(pn)}`, data)),
  delete: (pn: string) => RESP<{ ok: boolean }>(axios.delete(`/api/parts/${encodeURIComponent(pn)}`)),
}

// ---------- KP 核心配件（从 kp.kp_parts 查，唯一数据源）----------
export const kpPartsApi = {
  categories: () => RESP<{ id: number; name: string }[]>(axios.get('/api/kp/categories')),
  listByCategory: (categoryId: number, series?: string) =>
    RESP<KpPart[]>(axios.get('/api/kp/parts', { params: { category_id: categoryId, series } })),
  listAll: () => RESP<KpPart[]>(axios.get('/api/kp/parts')),
}

// ---------- 服务器类型 / 机型目录 ----------
export const catalogApi = {
  listTypes: () => RESP<{ types: ServerType[] }>(axios.get('/api/server-catalog/types')),
  createType: (data: Partial<ServerType>) => RESP<{ id: number }>(axios.post('/api/server-catalog/types', data)),
  listModels: (typeId?: number) =>
    RESP<{ models: ServerModel[] }>(axios.get('/api/server-catalog/models', { params: { type_id: typeId } })),
  getModel: (id: number) => RESP<ServerModel>(axios.get(`/api/server-catalog/models/${id}`)),
  createModel: (data: Partial<ServerModel>) => RESP<{ id: number }>(axios.post('/api/server-catalog/models', data)),
  updateModel: (id: number, data: Partial<ServerModel>) => RESP<{ ok: boolean }>(axios.put(`/api/server-catalog/models/${id}`, data)),
  deleteModel: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/server-catalog/models/${id}`)),
}

// ---------- 基准配置（引用 parts_master + 底盘件清单）----------
export const baseConfigApi = {
  list: (params?: { series?: string; form?: string; bays?: number }) =>
    RESP<{ configs: BaseConfig[]; total: number }>(axios.get('/api/base-configs', { params })),
  get: (id: number) => RESP<BaseConfig & { parts: BaseConfigPart[] }>(axios.get(`/api/base-configs/${id}`)),
  create: (data: Partial<BaseConfig>) => RESP<{ id: number }>(axios.post('/api/base-configs', data)),
  update: (id: number, data: Partial<BaseConfig>) => RESP<{ ok: boolean }>(axios.put(`/api/base-configs/${id}`, data)),
  delete: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/base-configs/${id}`)),
  /** 整体替换底盘件清单（基准配置组装） */
  setParts: (id: number, parts: Partial<BaseConfigPart>[]) =>
    RESP<{ ok: boolean }>(axios.put(`/api/base-configs/${id}/parts`, parts)),
}

// ---------- 推导（配置面实时调用）----------
export const deriveApi = {
  /** state: { kp_lines:[{cat,pn,qty}], gpu_arch, psu_options? } → 推导结果 + 校验 */
  derive: (state: DeriveState) => RESP<DeriveResult>(axios.post('/api/derive', state)),
}

// ---------- 配置方案（服务器页配置产出 / 无价 BOM 保存读取）----------
export const configSchemeApi = {
  list: (modelId?: number) =>
    RESP<{ schemes: any[] }>(axios.get('/api/config-schemes', { params: { model_id: modelId } })),
  get: (id: number) => RESP<any>(axios.get(`/api/config-schemes/${id}`)),
  create: (data: { name?: string; model_id?: number; payload: any }) =>
    RESP<{ id: number }>(axios.post('/api/config-schemes', data)),
  delete: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/config-schemes/${id}`)),
}

// ---------- BOM 模板（左栏 L6 配置单的机型族行骨架）----------
// ---------- BOM 规则（模板每行 desc/qty 怎么算,跟模板存 JSONB,后端透传）----------
// 求值跑前端(bomContext 是临时态);算不出 → fallback;manual → 留空手填。
export type DescSource =
  | { kind: 'fixed'; value: string }                                       // 固定文案
  | { kind: 'part_field'; category: string; field: string }                // 料号库字段(name/sub_type/pn/specs.xxx)
  | { kind: 'template'; template: string }                                 // ${bays}*3.5 SATA/SAS 变量插值
  | { kind: 'struct_count'; scope: 'io_slot' | 'rear_all' | 'front_cables' } // 结构计数
  | { kind: 'config_value'; key: string }                                  // 配置参数单值
  | { kind: 'manual' }                                                     // 留空,工作台手填

export type QtySource =
  | { kind: 'fixed'; value: number }
  | { kind: 'part_quantity'; category: string }
  | { kind: 'config_calc'; key: string }   // psu_qty / gpu_cable_qty
  | { kind: 'manual' }

export interface BomRule {
  desc: DescSource
  desc_fallback?: DescSource   // desc 算不出时回落,限一层;manual 不触发
  qty: QtySource
  qty_fallback?: QtySource
}

export interface BomTemplateRow { type: string; label: string; slot?: string; mode?: string; rule?: BomRule }
export interface BomTemplate { id: number; name: string; rows: BomTemplateRow[]; sort_order?: number }
export const bomTemplateApi = {
  list: () => RESP<{ templates: BomTemplate[] }>(axios.get('/api/bom-templates')),
  get: (id: number) => RESP<BomTemplate>(axios.get(`/api/bom-templates/${id}`)),
  getForBaseConfig: (baseConfigId: number) =>
    RESP<BomTemplate | null>(axios.get(`/api/bom-templates/for-base-config/${baseConfigId}`)),
  create: (data: { name: string; rows: BomTemplateRow[]; sort_order?: number }) =>
    RESP<{ id: number }>(axios.post('/api/bom-templates', data)),
  update: (id: number, data: { name: string; rows: BomTemplateRow[]; sort_order?: number }) =>
    RESP<{ ok: boolean }>(axios.put(`/api/bom-templates/${id}`, data)),
  delete: (id: number) =>
    RESP<{ ok: boolean; detached_base_configs: number }>(axios.delete(`/api/bom-templates/${id}`)),
}

// ---------- 后面板配置 ----------
export const rearIOApi = {
  /** 获取后面板所有槽位的选项 */
  getOptions: (series?: string) =>
    RESP<{ slots: Record<string, RearIOSlotOption[]> }>(axios.get('/api/rear-io/options', { params: { series } })),
  /** 获取指定槽位的选项 */
  getSlotOptions: (slot: string, series?: string) =>
    RESP<{ options: RearIOSlotOption[] }>(axios.get(`/api/rear-io/options/${slot}`, { params: { series } })),
  /** 获取电源选项 */
  getPsuOptions: (series?: string) =>
    RESP<{ options: PsuOption[] }>(axios.get('/api/rear-io/psu-options', { params: { series } })),
}

// ---------- 类型 ----------
export interface PartMaster {
  pn: string
  name: string
  category: string
  sub_type?: string
  specs?: Record<string, any>
  unit_price?: number
  supplier?: string
  description?: string
  applicable?: Record<string, any>
  sort_order?: number
}
export interface ServerType { id: number; name: string; description?: string; sort_order?: number }
export interface ServerModel {
  id: number; name: string; server_type_id?: number; form?: string
  bays?: number; use?: string; base_config_id?: number; sort_order?: number
}
export interface BaseConfig {
  id: number; name: string; server_type_id?: number; series?: string; model?: string
  form?: string; bays?: number; bp_tri_pn?: string; bp_dc_pn?: string
  gpu_arch_default?: string; sort_order?: number
}
export interface BaseConfigPart {
  id?: number; config_id?: number; pn: string; quantity: number
  locked?: boolean; sort_order?: number
  // JOIN parts_master 带出：
  name?: string; category?: string; unit_price?: number; specs?: Record<string, any>
}
export interface KpLine { cat: string; pn: string; qty: number; part?: PartMaster }
export interface KpPart {
  id?: number
  pn: string
  name: string
  category: string
  brand?: string
  sub_type?: string
  specs?: Record<string, any>
  applicable?: { series?: string[] } | null
  unit_price?: number
}
export interface DeriveState {
  kp_lines: { cat: string; pn: string; qty: number }[]
  gpu_arch: 'none' | 'pt' | 'switch'
  psu_options?: { pn: string; name: string; wattage: number; price: number }[]
}
export interface DeriveResult {
  bp_type: 'tri' | 'dc'
  power: { total: number; base: number; cpu: number; gpu: number }
  psu: { power: { total: number; base: number; cpu: number; gpu: number }; qty: number; need_wattage: number; psu: PartMaster | null }
  front_cables: { kind: string; drive_count: number; group_size: number; qty: number }[]
  gpu_cables: { total: number; detail: { model: string; qty: number; per: number }[] }
  switch_extra: { category: string; gpu_count: number }[]
  switch_extra_parts?: { pn: string; name: string; category: string; qty: number; unit_price: number }[]
  warnings: string[]
}

// ---------- 后面板配置类型 ----------
export interface RearIOItem {
  item_id: number
  io_slot: string
  option_type: string
  pn: string
  part_name: string
  description?: string
  unit_price: number
  quantity: number
  applicable_chassis?: string
  applicable_backplane?: string
  note?: string
  sort_order: number
}

export interface RearIOSlotOption {
  option_type: string
  items: RearIOItem[]
  total_price: number
}

export interface PsuOption {
  psu_id: number
  wattage: number
  pn: string
  part_name: string
  description?: string
  unit_price: number
  applicable_chassis?: string
  note?: string
  sort_order: number
}
