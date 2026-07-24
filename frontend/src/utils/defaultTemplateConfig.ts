/**
 * 默认规格书模板配置服务
 *
 * 集中管理模板默认值，前后端保持一致
 */
import type { Branding } from '@/store/settings'
import { DEFAULT_COMMERCIAL_TERMS } from '@/store/settings'
import { DEFAULT_LABELS, type DisplayOptions } from '@/types/specTemplate'

/** 默认品牌配置 */
export const DEFAULT_BRANDING: Branding = {
  logo_url: '',
  company_name: '',
  tagline: '',
  doc_title: '配置规格书 / Server Build Specification',
  contact_phone: '',
  contact_email: '',
  address: '',
  footer_note: '',
  commercial_terms: { ...DEFAULT_COMMERCIAL_TERMS },
}

/** 默认显示控制选项 */
export const DEFAULT_DISPLAY_OPTIONS: DisplayOptions = {
  show_price_column: true,
  show_chassis_total: true,
  show_kp_subtotal: true,
  show_grand_total: true,
  show_config_subtotal: true,
  show_footer_check: true,
  show_commercial_terms: true,
  labels: { ...DEFAULT_LABELS }
}

/** 获取完整的默认模板配置 */
export function getDefaultTemplateConfig() {
  return {
    branding: { ...DEFAULT_BRANDING },
    display_options: { ...DEFAULT_DISPLAY_OPTIONS, labels: { ...DEFAULT_LABELS } }
  }
}

/** 创建新模板的默认值 */
export function createNewTemplateDefaults() {
  return getDefaultTemplateConfig()
}
