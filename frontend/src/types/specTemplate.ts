/**
 * 规格书模板类型定义
 *
 * 设计原则：模板只控制"显示什么"（品牌信息 + 显示开关），
 * 不控制"怎么画"（布局/样式由 SpecSheet.vue 统一渲染）。
 */

import type { Branding } from '@/store/settings'

/** 显示控制开关 */
export interface DisplayOptions {
  show_price_column: boolean    // KP 表是否显示 Cost 列
  show_chassis_total: boolean   // 是否显示机箱总价行
  show_kp_subtotal: boolean     // 是否显示 KP 配件合计行
  show_grand_total: boolean     // 是否显示整机合计区块
  show_footer_check: boolean    // 是否显示"✓ 已通过机型兼容校验"
  show_config_subtotal?: boolean // 是否显示配置小计
  show_commercial_terms?: boolean // 是否显示报价条款区块（报价单位/有效期/交付付款/寄送）
  /** 自定义标签文本 */
  labels?: {
    chassis_title?: string       // 机箱规格标题
    chassis_model?: string       // 型号
    chassis_form?: string        // 形态
    chassis_bays?: string        // 盘位
    chassis_backplane?: string   // 背板类型
    chassis_power?: string       // 电源
    chassis_total?: string       // 机箱总价
    kp_title?: string            // KP 配件标题
    kp_catalogue?: string        // Catalogue 列标题
    kp_description?: string      // Description 列标题
    kp_qty?: string              // Qty 列标题
    kp_cost?: string             // Cost 列标题
    kp_subtotal?: string         // KP 配件合计
    config_subtotal?: string     // 含税单价（单配置）
    grand_total?: string         // 含税总价（单配置 × 数量）
  }
}

/** 默认标签 */
export const DEFAULT_LABELS: Required<DisplayOptions['labels']> = {
  chassis_title: '机箱规格',
  chassis_model: '型号',
  chassis_form: '形态',
  chassis_bays: '盘位',
  chassis_backplane: '背板类型',
  chassis_power: '电源',
  chassis_total: '机箱总价',
  kp_title: 'KP 配件',
  kp_catalogue: 'Catalogue',
  kp_description: 'Description',
  kp_qty: 'Qty',
  kp_cost: 'Cost',
  kp_subtotal: 'KP 配件合计',
  config_subtotal: '含税单价',
  grand_total: '含税总价',
}

/** 预览数据 - L6 配件项（字段去重载后，L6/KP/Warranty 共用统一展示列） */
export interface PreviewL6Item {
  catalogue: string
  description: string
  part_category: string
  qty: number
  category: string
  final_price: number
}

/** 预览数据 - KP 配件项 */
export interface PreviewKpItem {
  catalogue: string
  description: string
  part_category: string
  qty: number
  category: string
  final_price: number
}

/** 预览数据 - 单个配置 */
export interface PreviewConfig {
  config_name: string
  server_model: string
  quantity: number
  l6_details: PreviewL6Item[]
  kp_details: PreviewKpItem[]
  l6_total: number
  kp_total: number
  unit_price: number
  total_price: number
  chassis_form: string
  chassis_bays: string
  chassis_series: string
  backplane_type: string
  power_supply: string
}

/** 预览数据 - 完整响应（对应后端 load_preview_data） */
export interface PreviewData {
  customer_name?: string
  config_summary?: Array<{
    config_name: string
    server_model: string
    description: string
    unit_price: number
    quantity: number
    total_price: number
  }>
  configs: PreviewConfig[]
  l6_details?: PreviewL6Item[]
  kp_details?: PreviewKpItem[]
  [key: string]: any
}

/** 规格书模板 */
export interface SpecTemplate {
  id: number
  name: string
  display_name: string
  is_default: boolean
  branding: Branding
  display_options: DisplayOptions
  created_at: string
  updated_at: string
}
