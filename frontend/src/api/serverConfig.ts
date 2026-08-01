/**
 * 服务器配置相关的 API 封装（对接后端 /api/parts、/api/server-catalog、/api/base-configs、/api/derive）
 * 对应落地设计文档阶段②后端。
 */
import axios from 'axios'
import type { ShowcaseConfig } from '@/components/server-config/showcase-config'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

// ---------- 料号库 ----------
export interface PartSection {
  section: string
  count: number
  categories: string[]
}
export const partsApi = {
  list: (opts?: { category?: string; section?: string; search?: string; chassis?: string; page?: number; page_size?: number; sort_by?: string; sort_order?: string }) =>
    RESP<{ parts: PartMaster[]; total: number }>(axios.get('/api/parts', { params: opts })),
  sections: () => RESP<{ sections: PartSection[] }>(axios.get('/api/parts/sections')),
  categories: () => RESP<{ categories: string[] }>(axios.get('/api/parts/categories')),
  /** 每个品类下现有的 spec_key 列表（DISTINCT，从 parts_master.specs 实际数据）→ {category: [spec_key...]} */
  specKeys: () => RESP<Record<string, string[]>>(axios.get('/api/parts/spec-keys')),
  /** 指定 category + spec_key 下的所有不同值（DISTINCT）→ {values: [...]} */
  specValues: (category: string, specKey: string) =>
    RESP<{ values: string[] }>(axios.get('/api/parts/spec-values', { params: { category, spec_key: specKey } })),
  get: (pn: string) => RESP<PartMaster>(axios.get(`/api/parts/${encodeURIComponent(pn)}`)),
  create: (data: Partial<PartMaster>) => RESP<{ pn: string }>(axios.post('/api/parts', data)),
  update: (pn: string, data: Partial<PartMaster>) => RESP<{ ok: boolean }>(axios.put(`/api/parts/${encodeURIComponent(pn)}`, data)),
  delete: (pn: string) => RESP<{ ok: boolean }>(axios.delete(`/api/parts/${encodeURIComponent(pn)}`)),
  /** 导出料号库 */
  export: (section?: string) => axios.get('/api/parts/export', { params: { section }, responseType: 'blob' }),
  /** 批量导入料号（预览或确认） */
  import: (file: File, dryRun: boolean = true) => {
    const fd = new FormData()
    fd.append('file', file)
    return RESP<{ preview: any[]; summary: { total: number; new: number; update: number; invalid: number } }>(
      axios.post(`/api/parts/import?dry_run=${dryRun}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    )
  },
  /** 下载导入模板 */
  downloadTemplate: () => axios.get('/api/parts/import-template', { responseType: 'blob' }),
}

// ---------- KP 核心配件（从 kp.kp_parts 查，唯一数据源）----------
export const kpPartsApi = {
  categories: () => RESP<{ id: number; name: string }[]>(axios.get('/api/kp/categories')),
  /** 每个品类下现有的 spec_key 列表（DISTINCT，从 kp_part_specs 实际数据）→ {category: [spec_key...]} */
  specKeys: () => RESP<Record<string, string[]>>(axios.get('/api/kp/spec-keys')),
  listByCategory: (categoryId: number, series?: string) =>
    RESP<KpPart[]>(axios.get('/api/kp/parts', { params: { category_id: categoryId, series } })),
  listAll: () => RESP<KpPart[]>(axios.get('/api/kp/parts')),
}

// ---------- 服务器类型 / 机型目录 ----------
export const catalogApi = {
  listTypes: () => RESP<{ types: ServerType[] }>(axios.get('/api/server-catalog/types')),
  createType: (data: Partial<ServerType>) => RESP<{ id: number }>(axios.post('/api/server-catalog/types', data)),
  updateType: (id: number, data: Partial<ServerType>) => RESP<{ ok: boolean }>(axios.put(`/api/server-catalog/types/${id}`, data)),
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
  listSeries: () =>
    RESP<{ series: string[]; items: { value: string; label: string }[] }>(axios.get('/api/base-configs/series')),
  /** 机箱形态 DISTINCT（数据驱动，供词表编辑器机型表 form 字段下拉） */
  listForms: () =>
    RESP<{ forms: string[] }>(axios.get('/api/base-configs/forms')),
  get: (id: number) => RESP<BaseConfig & { parts: BaseConfigPart[] }>(axios.get(`/api/base-configs/${id}`)),
  create: (data: Partial<BaseConfig>) => RESP<{ id: number }>(axios.post('/api/base-configs', data)),
  update: (id: number, data: Partial<BaseConfig>) => RESP<{ ok: boolean }>(axios.put(`/api/base-configs/${id}`, data)),
  delete: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/base-configs/${id}`)),
  /** 整体替换底盘件清单（基准配置组装） */
  setParts: (id: number, parts: Partial<BaseConfigPart>[]) =>
    RESP<{ ok: boolean }>(axios.put(`/api/base-configs/${id}/parts`, parts)),
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
  | { kind: 'part_field'; category: string; field: string }                // 料号库字段(name/pn/specs.xxx)
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
  section?: string
  specs?: Record<string, any>
  unit_price?: number
  supplier?: string
  spec_text?: string     // 自由文本规格串（UI「规格」），如 PCBA_3.5''_Triple-mode
  description?: string   // 人话用途说明（UI「说明」）
  applicable?: Record<string, any>
  sort_order?: number
}
export interface ServerType {
  id: number
  name: string
  description?: string
  sort_order?: number
  showcase_config?: ShowcaseConfig
}
export interface ServerModelBaseConfig {
  id?: number
  form?: string
  bays?: number
  series?: string
  name?: string
}
/** 机型的产品化包装内容（结构化分块，JSONB 透传存 server_models.product_content）。 */
export interface ModelProductContent {
  overview?: string                              // 产品概述（一段话）
  features?: { icon?: string; text: string }[]   // 核心特性（可增删列表）
  specs?: { key: string; value: string }[]       // 技术参数（key-value，保序）
  scenarios?: string[]                          // 应用场景（标签数组，跨机型联想）
}
export interface ServerModel {
  id: number
  name: string
  server_type_id?: number
  use?: string
  base_config_id?: number
  sort_order?: number
  // 产品级字段（阶段一 Step 1）
  description?: string
  image_url?: string
  lifecycle_status?: 'new' | 'active' | 'eol' | 'discontinued'
  // 继承自基准配置的技术参数（阶段一 Step 2：form/bays 不再存于机型表）
  base_config?: ServerModelBaseConfig | null
  // 产品化包装内容（结构化分块，可空）
  product_content?: ModelProductContent | null
}
export interface BaseConfig {
  id: number; name: string; server_type_id?: number; series?: string; model?: string
  form?: string; bays?: number; bp_tri_pn?: string; bp_dc_pn?: string
  gpu_arch_default?: string; sort_order?: number
  // 机箱能力档案（P1：把原散落前端硬编码的「机箱物理上能装什么」提到数据）
  psu_bays?: number       // 电源槽位数（驱动电源数量上限/默认）
  rear_slots?: RearSlot[] // 后面板槽位布局 [{name, cap}]
  gpu_slots?: number      // 可装 GPU 数上限
  max_tdp?: number | null  // 散热/供电承载 TDP 上限(W)，可空，供 PSU↔GPU 功率规则参考
  parts_count?: number; total_price?: number
}
/** 后面板槽位：名称 + 容量（如 IO1 容纳 3 张卡、OCP 容纳 1 张）*/
export interface RearSlot { name: string; cap: number }
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
  specs?: Record<string, any>
  applicable?: { series?: string[] } | null
  unit_price?: number
}

// ---------- 后面板配置类型 ----------
export interface RearIOItem {
  pn: string
  name: string
  unit_price: number
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
