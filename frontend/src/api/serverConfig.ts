/**
 * 服务器配置相关的 API 封装（对接后端 /api/parts、/api/server-catalog、/api/base-configs、/api/derive）
 * 对应落地设计文档阶段②后端。
 */
import axios from 'axios'
import type { ShowcaseConfig } from '@/components/server-config/showcase-config'
import type { PerfScoreConfig } from '@/utils/performanceScore'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

// ---------- 料号库 ----------

/** 大类汇总项（一级主导航）：major_category 大类 + 段内子类列表 */
export interface PartMajorCategory {
  id: number | null
  major_category: string
  count: number
  categories: string[]
}
export const partsApi = {
  list: (opts?: { category?: string; major_category?: string; search?: string; chassis?: string; page?: number; page_size?: number; sort_by?: string; sort_order?: string }) =>
    RESP<{ parts: PartMaster[]; total: number }>(axios.get('/api/parts', { params: opts })),
  majorCategories: () => RESP<{ major_categories: PartMajorCategory[] }>(axios.get('/api/parts/major-categories')),
  /** 大类分类管理：增/改名/删，改名删除批量传播到所有相关料号 */
  taxonomy: {
    add: (kind: 'major', name: string) =>
      RESP<{ kind: string; name: string }>(axios.post('/api/parts/taxonomy', { kind, name })),
    rename: (kind: 'major', old_name: string, new_name: string) =>
      RESP<{ updated: number }>(axios.put('/api/parts/taxonomy/rename', { kind, old_name, new_name })),
    remove: (kind: 'major', name: string) =>
      RESP<{ name: string }>(axios.delete('/api/parts/taxonomy', { params: { kind, name } })),
  },
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
  export: () => axios.get('/api/parts/export', { responseType: 'blob' }),
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
  listModels: (typeId?: number, opts?: { publishedOnly?: boolean }) =>
    RESP<{ models: ServerModel[] }>(axios.get('/api/server-catalog/models', {
      params: { type_id: typeId, published_only: opts?.publishedOnly || undefined },
    })),
  getModel: (id: number) => RESP<ServerModel>(axios.get(`/api/server-catalog/models/${id}`)),
  createModel: (data: Partial<ServerModel>) => RESP<{ id: number }>(axios.post('/api/server-catalog/models', data)),
  updateModel: (id: number, data: Partial<ServerModel>) => RESP<{ ok: boolean }>(axios.put(`/api/server-catalog/models/${id}`, data)),
  deleteModel: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/server-catalog/models/${id}`)),
  // 门户 banner 配置（system_config 存储；标题/副标题空=门户用内置默认文案）
  getPortalBanner: () => RESP<PortalBanner>(axios.get('/api/server-catalog/portal-banner')),
  savePortalBanner: (data: PortalBanner) => RESP<PortalBanner>(axios.put('/api/server-catalog/portal-banner', data)),
  /** 性能六维打分锚点表（system_config；未配置返回 {}，前端回落内置默认锚点） */
  getPerformanceScoreConfig: () => RESP<PerfScoreConfig>(axios.get('/api/server-catalog/performance-score-config')),
}

// ---------- 基准配置（引用 parts_master + 底盘件清单）----------
export const baseConfigApi = {
  list: (params?: { series?: string; form?: string; bays?: number; model_id?: number; unassigned?: boolean }) =>
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
  /** 全量基准配置裸机成本（编辑器成本分析面板·机型对比卡；口径=底盘件+后面板默认卡+线缆+PSU×槽位） */
  costAnalysis: () => RESP<{ configs: BaseConfigCost[] }>(axios.get('/api/base-configs/cost-analysis')),
}

/** 裸机成本分析行（cost-analysis 端点返回；与 CostAnalysisPanel 前端口径一致） */
export interface BaseConfigCost {
  id: number
  name: string
  series?: string
  form?: string
  model_id: number | null
  model_name: string | null
  /** 完整裸机成本（下限：缺价件未计入） */
  total: number
  by_source: { chassis: number; rear: number; cables: number; psu: number }
  /** 缺价件数（unit_price 空 / PN 库外，未计入 total） */
  missing: number
}

// ---------- BOM 模板（左栏 L6 配置单的机型族行骨架）----------
// ---------- BOM 规则类型（行类型规则的内部形状；定义在 bomRuleEngine.TYPE_RULES，不随模板存）----------
export type DescSource =
  | { kind: 'fixed'; value: string }                                       // 固定文案
  | { kind: 'part_field'; category: string; field: string }                // 料号库字段(name/pn/specs.xxx)
  | { kind: 'template'; template: string }                                 // ${bays}*3.5 SATA/SAS 变量插值
  | { kind: 'struct_count'; scope: 'io_slot' | 'rear_all' }                // 结构计数
  | { kind: 'config_value'; key: string }                                  // 配置参数单值
  | { kind: 'cable_groups'; kinds?: Record<string, { size: number; template: string }> } // Cable 行专属：按盘型分组拼线缆文字（SATA/SAS/NVMe）
  | { kind: 'manual' }                                                     // 留空,工作台手填

export type QtySource =
  | { kind: 'fixed'; value: number }
  | { kind: 'part_quantity'; category: string }
  | { kind: 'config_calc'; key: string }   // psu_qty / gpu_cable_qty / ocp_qty
  | { kind: 'manual' }

export interface BomRule {
  desc: DescSource
  desc_fallback?: DescSource   // desc 算不出时回落,限一层;manual 不触发
  qty: QtySource
  qty_fallback?: QtySource
}

/** 行骨架：rule 可选——省略 = 跟随类型默认（bomRuleEngine.TYPE_RULES，零配置即合理）；
 *  填了 = 该行完全按自己的规则求值（编辑页点「取值方式」从类型默认拷贝起步可改）。
 *  相比旧版：rule 不再必填、不预填，默认干净的骨架；编辑能力保留完整。 */
export interface BomTemplateRow {
  type: string
  label: string
  slot?: string
  mode?: string
  rule?: BomRule
}
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
  major_category?: string
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
/** 门户 banner 轮播图项（每图可配独立副标题，门户随图切换展示；空=不显示） */
export interface PortalBannerImage {
  url: string
  subtitle?: string
}
/** 门户 banner 配置（system_config.server_portal_banner；标题空由门户回落内置默认） */
export interface PortalBanner {
  title?: string
  /** 轮播图列表（首张为主图；空=银河场景做背景） */
  images?: PortalBannerImage[]
}
export interface ServerModelBaseConfig {
  id?: number
  form?: string
  bays?: number
  series?: string
  name?: string
  // 机箱能力档案（配置页「机箱能力」标签可配；选型规则上下文读取，超上限出告警）
  psu_bays?: number
  gpu_slots?: number
  max_tdp?: number | null
  max_cpu?: number
  max_dimm?: number
}
/** 能力维度卡关键数字（详情页右侧 mono 数字列） */
export interface CapabilityMetric { v: string; l: string }
/** 能力维度卡（详情页「产品能力」暗色带，两列横向卡） */
export interface ModelCapability {
  name: string              // 维度名（如 算力）
  name_en?: string          // mono 英文标签（如 Compute）
  icon?: string             // capIcons 注册表键（chip/slots/net/…）
  desc?: string             // 一句话价值（约 25 字）
  metrics?: CapabilityMetric[]
}
/** 场景适配照片卡 */
export interface ModelScenario {
  name: string              // 场景名（跨机型联想）
  fit?: string              // 为什么适配（一句话）
  image?: string            // 配图 URL（后台上传）
}
/** 机型的产品化包装内容（结构化分块，JSONB 透传存 server_models.product_content）。 */
export interface ModelProductContent {
  tagline?: string                                // 一句话定位（铭牌副标题，15 字左右）
  overview?: string                               // 产品概述（一段话）
  stage_theme?: 'wine' | 'ocean' | 'carbon' | 'violet'  // 展示页主题色（默认 ocean）
  highlight_image?: string                      // 为什么选它模块配图（左栏正方形图，站内图库/外链）
  highlights?: { title: string; text: string }[]  // 为什么选它（ruled list：短标题 + 一句话）
  capabilities?: ModelCapability[]                // 产品能力（六维预设，编辑器增删）
  specs?: { key: string; value: string }[]        // 完整技术规格（详情页沉底折叠，保序）
  scenarios?: (ModelScenario | string)[]          // 场景适配（照片卡；string=旧版标签，展示时按 {name} 兼容）
  features?: { icon?: string; text: string }[]    // 旧版核心特性（只读兼容：无 highlights 时按亮点行降级展示）
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
  /** 是否上架：false=下架（服务器页机型目录不展示；管理面/报价/推理流照旧可见） */
  is_published?: boolean
  // 继承自基准配置的技术参数（阶段一 Step 2：form/bays 不再存于机型表）
  base_config?: ServerModelBaseConfig | null
  // 图纸摘要（列表/卡片预览用）：top 视图 svg_url + viewBox，无图时为 null
  drawing?: { svg_url: string; viewBox?: number[] | null } | null
  // 产品化包装内容（结构化分块，可空）
  product_content?: ModelProductContent | null
  // 该机型的所有配置变体（getModel 附带；含主配置 base_config）
  configs?: BaseConfig[]
}
/** 配置级内容（存 base_configs.config_content JSONB，后端不透明透传） */
export interface ConfigContent {
  description?: string   // 配置说明（一段话）
  spec_diff?: string     // 规格差异说明
  // IO/Riser 与内存速率（数据驱动，需求分析/报价工作台/server config 同源消费）：
  standard_riser?: Record<string, string> | string  // 各 IO 槽默认 riser（dict 按槽位 / 字符串全槽同规格）
  riser_x16?: string                                // 升级规格（装 GPU → 全槽；100G+ 网卡 → IO1）
  standard_mem_speed?: string | number | null       // 机型标准内存速率 (MT/s)，需求未写时按此选件
  front_cables?: Record<string, string>             // 前面板线缆 PN 按盘类 {SATA, SAS, NVMe}（基准配置选默认，配置页可改）
  default_psu_pn?: string                            // 默认电源 PSU 料号（基准配置选默认，配置页可改；与 front_cables 同为软默认，不锁死）
}
export interface BaseConfig {
  id: number; name: string; server_type_id?: number; series?: string; model?: string
  form?: string; bays?: number; bp_tri_pn?: string; bp_dc_pn?: string
  gpu_arch_default?: string; sort_order?: number
  // 机箱能力档案（P1：把原散落前端硬编码的「机箱物理上能装什么」提到数据）
  psu_bays?: number       // 电源槽位数（驱动电源数量上限/默认）
  rear_slots?: RearSlot[] // 后面板槽位布局 [{name, cap}]
  gpu_slots?: number      // 可装 GPU 数上限
  gpu_default?: { part_id: number; qty: number }[] | null  // 默认 GPU 卡配置（KP 卡 id×数量；AI 推理配置器「机型装得下判定」输入，空=未维护）
  max_tdp?: number | null  // 散热/供电承载 TDP 上限(W)，可空，供 PSU↔GPU 功率规则参考
  // 机箱能力约束（基准配置页可配；缺省 → 推理链路用全局兜底，不硬编码物理边界）：
  psu_wattages?: number[]   // 允许的 PSU 瓦数档位（如 [1300,1600,2000]；空/缺省=不限沿用全局）
  max_cpu?: number          // CPU 颗数上限（双路默认 2）
  max_dimm?: number         // 内存条数上限（EPYC 双路默认 24）
  mem_channels?: number     // 每路内存通道数（EPYC 12 通道/路，驱动内存选型目标条数）
  parts_count?: number; total_price?: number
  model_id?: number | null                    // 所属机型（一对多反向关联；NULL=孤儿待归属）
  config_content?: ConfigContent | null       // 配置级介绍
}
/** 后面板槽位：名称 + 容量（如 IO1 容纳 3 张卡、OCP 容纳 1 张）*/
export interface RearSlot {
  name: string
  cap: number
  /** 该槽默认装载的 option_type 多重集（重复即数量），与配置页 rear[slot] 同形：['x16','x16']=2 条 X16。
   *  基准配置在此选默认卡 + 默认数量；配置页选了基准机箱后用此播种 rear，且只能调数量不能换卡（电源除外）。
   *  空/缺省 = 挡片；配置页遇空 defaults 的旧基准回退自由选（向后兼容）。 */
  defaults?: string[]
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
  specs?: Record<string, any>
  applicable?: { series?: string[] } | null
  unit_price?: number
  unit_currency?: string
  latest_price_date?: string
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
