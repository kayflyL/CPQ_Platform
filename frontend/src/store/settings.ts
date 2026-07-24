import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

/** 报价/商务条款：每页「合计」与「页脚」之间展示的标准条款文本，留空则不显示该条 */
export interface CommercialTerms {
  currency?: string   // 报价单位
  validity?: string   // 报价有效期
  delivery?: string   // 交付与付款
  shipping?: string   // 寄送范围
}

/** 默认商务条款（公司标准口径） */
export const DEFAULT_COMMERCIAL_TERMS: CommercialTerms = {
  currency: '报价单位：人民币含税',
  validity: '因 KP 波动，报价有效期 2 天',
  delivery: '交付周期为签订合同收到预付款后 2-4 周内，合同签订后预付 50% 预付款',
  shipping: '寄送至中国大陆境内',
}

export interface Branding {
  company_name: string
  doc_title: string
  tagline: string
  contact_phone: string
  contact_email: string
  address: string
  footer_note: string
  logo_url: string
  logo_path?: string
  commercial_terms: CommercialTerms
}

const DEFAULT_BRANDING: Branding = {
  company_name: '',
  doc_title: '配置规格书 / Server Build Specification',
  tagline: '',
  contact_phone: '',
  contact_email: '',
  address: '',
  footer_note: '',
  logo_url: '',
  commercial_terms: { ...DEFAULT_COMMERCIAL_TERMS },
}

export const useSettingsStore = defineStore('settings', () => {
  const numberPrecision = ref<number>(2)

  async function loadNumberPrecision() {
    try {
      const resp = await axios.get('/api/rules/number-precision')
      numberPrecision.value = resp.data.precision
    } catch (e) {
      console.error('Failed to load number precision:', e)
    }
  }

  async function setNumberPrecision(precision: number) {
    try {
      await axios.put('/api/rules/number-precision', { precision })
      numberPrecision.value = precision
    } catch (e) {
      console.error('Failed to set number precision:', e)
      throw e
    }
  }

  function formatNumber(value: number | string | null | undefined): string {
    if (value === null || value === undefined || value === '') return ''
    if (typeof value === 'string') {
      const num = parseFloat(value)
      if (isNaN(num)) return value
      return num.toFixed(numberPrecision.value)
    }
    return value.toFixed(numberPrecision.value)
  }

  // ---- 品牌 / 抬头（system_config key=branding，type=json）----
  const branding = ref<Branding>({ ...DEFAULT_BRANDING })
  const brandingLoaded = ref(false)

  async function loadBranding() {
    try {
      const resp = await axios.get('/api/system-config/branding/value')
      const v = resp.data?.value
      if (v && typeof v === 'object') {
        branding.value = { ...DEFAULT_BRANDING, ...v }
      }
    } catch (e) {
      console.error('Failed to load branding:', e)
    } finally {
      brandingLoaded.value = true
    }
  }

  async function saveBranding(patch: Partial<Branding>) {
    const merged = { ...branding.value, ...patch }
    await axios.put('/api/system-config/branding', { value: merged, type: 'json' })
    branding.value = merged
  }

  /** 作为 a-upload 的 before-upload：手动 POST 上传，成功后写回 logo_url，返回 false 阻止 antd 自动上传。失败抛异常由调用方提示。 */
  async function uploadLogo(file: File): Promise<boolean> {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/system-config/branding/logo', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    branding.value = {
      ...branding.value,
      logo_url: resp.data?.logo_url || '',
      logo_path: resp.data?.logo_path,
    }
    return false
  }

  return {
    numberPrecision,
    loadNumberPrecision,
    setNumberPrecision,
    formatNumber,
    branding,
    brandingLoaded,
    loadBranding,
    saveBranding,
    uploadLogo,
  }
})
