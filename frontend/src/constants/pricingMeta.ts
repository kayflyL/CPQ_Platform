/**
 * 定价维度元数据 SSOT —— 加法定价引擎(pricingEngine)、定价画布(PricingFlowCanvas)、
 * 维度配置抽屉(DimensionDrawer)、演算器共用的唯一真相源。
 *
 * 集中四类元数据，杜绝 label / 维度顺序 / 枚举 / 单位散落多处裸字面导致漂移：
 *   ① 维度定义（key + label + 运算类型 opKind + 单位 + 说明，按公式流水线顺序）
 *   ② 各维度枚举选项（platform / industry / region 分桶 / customer_type）——统一三处历史不一致
 *   ③ 区域分桶关键词（delivery_region 自由文本 → 国内/海外/偏远）
 *   ④ 默认系数表（DEFAULT_DIM_BODIES）——与 backend/scripts/seed_pricing_strategies.py 必须保持一致
 *
 * 运算类型 opKind 决定该维度在公式里的角色：
 *   base  = 基准（平台基准毛利，加法链起点）
 *   add   = 加减（行业 / 区域 ±百分点）
 *   mult  = 乘（订单系数 / 成本阶梯系数）
 *   clamp = 夹取（保底封顶）
 *
 * 注意：platform 枚举应与 system_config.server_series 对齐（[[series-ssot]]）；
 *       此处集中定价用到的展示枚举，是消除 seed_strategy_fields / 旧画布 / 模型注释三处不一致的落点。
 */

// ── 维度 key（与 strategy.type 一致，去掉 pricing. 前缀）──
export type DimensionKey =
  | 'platform_baseline'
  | 'industry_adj'
  | 'region_adj'
  | 'order_mult'
  | 'cost_tier'
  | 'qty_mult'
  | 'guardrail'

// 运算类型
export type OpKind = 'base' | 'add' | 'mult' | 'clamp'

// ── ① 维度定义（公式流水线顺序，画布派生布局 & breakdown 顺序都读这个）──
export interface DimensionDef {
  key: DimensionKey
  label: string          // 节点标题 / 抽屉标题
  shortLabel: string     // 节点内紧凑标题
  opKind: OpKind
  unit: string           // '%' | '百分点' | '×' | ''
  sign: string           // 运算符展示：base→'' add→'+' mult→'×' clamp→'⎯'
  desc: string           // 节点说明 / tooltip
}

export const DIMENSION_DEFS: DimensionDef[] = [
  { key: 'platform_baseline', label: '平台基准毛利', shortLabel: '平台基准', opKind: 'base',  unit: '%',  sign: '',  desc: '按芯片平台取基准毛利率，是加法链的起点' },
  { key: 'industry_adj',      label: '行业浮动',     shortLabel: '行业',     opKind: 'add',   unit: '百分点', sign: '+', desc: '在基准上按客户行业 ±百分点' },
  { key: 'region_adj',        label: '区域浮动',     shortLabel: '区域',     opKind: 'add',   unit: '百分点', sign: '+', desc: '按客户区域(交付地区)分桶后 ±百分点' },
  { key: 'order_mult',        label: '订单系数',     shortLabel: '订单',     opKind: 'mult',  unit: '×', sign: '×', desc: '按订单/客户类型乘系数修正' },
  { key: 'cost_tier',         label: '成本阶梯',     shortLabel: '成本',     opKind: 'mult',  unit: '×', sign: '×', desc: '按整机 BOM 总成本阶梯乘系数（成本越高点位越低）' },
  { key: 'qty_mult',          label: '台数折扣',     shortLabel: '台数',     opKind: 'mult',  unit: '×', sign: '×', desc: '按销售台数分档乘系数（量越大让利越多）' },
  { key: 'guardrail',         label: '保底封顶',     shortLabel: '保底封顶', opKind: 'clamp', unit: '%',  sign: '⎯', desc: '最终毛利率夹在 [保底, 封顶] 之间' },
]
export const DIMENSION_MAP = Object.fromEntries(DIMENSION_DEFS.map(d => [d.key, d])) as Record<DimensionKey, DimensionDef>

/** 流水线里参与运算的维度顺序（不含输入/输出节点，画布据此派生 X 坐标）*/
export const PIPELINE_ORDER: DimensionKey[] = DIMENSION_DEFS.map(d => d.key)

// ── ② 维度枚举选项（演算器/抽屉下拉用；与商机字段值对齐）──

/** 平台类型（对齐 system_config.server_series：[[series-ssot]]）*/
export const PLATFORM_OPTIONS = [
  { value: 'Polaris', label: 'Polaris（兆芯）' },
  { value: 'Orion', label: 'Orion（AMD）' },
  { value: 'Intel', label: 'Intel' },
  { value: '工作站', label: '工作站' },
]

/** 客户行业（对齐 seed_strategy_fields 的 industry 枚举）*/
export const INDUSTRY_OPTIONS = [
  { value: 'AI算力', label: 'AI算力' },
  { value: 'IDC机房', label: 'IDC机房' },
  { value: '政企信息化', label: '政企信息化' },
  { value: '高校科研', label: '高校科研' },
  { value: '安防存储', label: '安防存储' },
  { value: '工业边缘', label: '工业边缘' },
]

/** 区域分桶（delivery_region 自由文本 → 这三个桶）*/
export const REGION_BUCKET_OPTIONS = [
  { value: '国内', label: '国内' },
  { value: '海外', label: '海外' },
  { value: '偏远', label: '偏远（国内偏远地区）' },
]

/** 订单/客户类型（对齐 seed_strategy_fields 的 customer_type 枚举）*/
export const CUSTOMER_TYPE_OPTIONS = [
  { value: '直签大客户', label: '直签大客户' },
  { value: '渠道分销', label: '渠道分销' },
  { value: '集采项目', label: '集采项目' },
  { value: '零散项目', label: '零散项目' },
]

// ── ③ 区域分桶关键词（delivery_region 自由文本命中关键词 → 桶）──
// 桶判定优先级：偏远 > 海外 > 国内；命中即止。国内是默认兜底桶。
export const REGION_KEYWORDS: Record<string, string[]> = {
  海外: ['海外', '境外', '东南亚', '欧美', '中东', '日本', '韩国', '新加坡', '德国', '美国', '越南', '泰国', '马来西亚', '欧洲', '北美'],
  偏远: ['西藏', '新疆', '青海', '内蒙古', '宁夏', '甘肃', '偏远'],
}

// ── ④ 默认系数表（与 seed_pricing_strategies.py 同步；抽屉「恢复默认」/ 演算器空配置兜底用）──
// ⚠️ 改这里必须同步改 backend/scripts/seed_pricing_strategies.py 的 DEFAULT_DIMS
export const DEFAULT_DIM_BODIES = {
  platform_baseline: { Polaris: 15, Orion: 11, Intel: 11, '工作站': 13 },
  industry_adj: { 'AI算力': 3, 'IDC机房': -2, '政企信息化': 3, '高校科研': 0, '安防存储': 1, '工业边缘': 2 },
  region_adj: {
    factors: { 国内: 0, 海外: 2, 偏远: 1 },
    keywords: REGION_KEYWORDS,
  },
  order_mult: { '直签大客户': 0.9, '渠道分销': 0.7, '集采项目': 0.75, '零散项目': 1.0 },
  cost_tier: {
    tiers: [
      { max: 50000, mult: 1.1 },    // <5w 高档
      { max: 300000, mult: 1.0 },   // 5w~30w 中档
      { mult: 0.9 },                // >30w 走量
    ],
  },
  qty_mult: {
    bands: [
      { min: 1, mult: 1.0 },        // 1-5 台 散单/样机/小客户，全额毛利
      { min: 6, mult: 0.9 },        // 6-20 台 中小项目/企业批量，小幅让利
      { min: 21, mult: 0.84 },      // 21-50 台 标准项目集采/机房上架，正常让利
      { min: 51, mult: 0.75 },      // 51+ 台 大型机房/IDC 整批/总包，大幅折价走量
    ],
  },
  guardrail: { floor: 7, cap: 30 },
} as const

// ── ⑤ 利润率告警默认配置（独立策略 type=margin_alert；与 seed_pricing_strategies.py 同步）──
// 工作台综合毛利率低于门槛时弹窗提示；与保底封顶（引擎 clamp）解耦——独立开关 + 门槛 + 文案。
// ⚠️ 改这里必须同步改 backend/scripts/seed_pricing_strategies.py 的 MARGIN_ALERT
export interface MarginAlertBody {
  enabled: boolean       // 是否启用工作台低利润率告警
  threshold: number      // 告警门槛（综合毛利率 %），低于此值弹窗
  title: string          // 弹窗标题
  content: string        // 弹窗正文模板，支持 ${margin}（当前毛利率）与 ${threshold}（门槛）占位符
}
export const DEFAULT_MARGIN_ALERT: MarginAlertBody = {
  enabled: true,
  threshold: 7,
  title: '利润率低于告警线',
  content: '当前综合毛利率 ${margin}% 低于告警线 ${threshold}%，建议线下走特价审批，系统仅作记录。',
}

/** 维度的系数值容器 key（region/guardrail/cost_tier 是对象，其余是 Record<enum,number>）——抽屉按维度分支读 */
export type DimBody = typeof DEFAULT_DIM_BODIES[DimensionKey]

// ── 展示文案（画布/演算器共用）──
export const PRICING_TEXT = {
  inputNode: '商机属性 / 成本',
  outputNode: '目标毛利率',
  // breakdown 备注
  noAdjust: '未配置 / 无数据 → 不调整',
  fallbackBase: '基准缺失，回退保底',
  inRange: '在保底封顶区间内',
  belowFloor: (floor: number) => `低于保底 ${floor}%，上调至保底`,
  aboveCap: (cap: number) => `高于封顶 ${cap}%，下调至封顶`,
  empty: '暂无定价维度策略——将在 seed 后显示',
} as const
