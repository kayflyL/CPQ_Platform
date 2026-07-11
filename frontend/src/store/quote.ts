import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { message } from 'ant-design-vue'
import { saveProject as saveProjectAPI, exportProject as exportProjectAPI, quotationApi } from '@/api'

// Type definitions
export interface ProjectInfo {
  opportunity_id: string
  opportunity_name: string
  sales_person: string
  fae: string
  customer_name: string
  date: string
  model_name: string
  total_qty: number
  platform_type: string
  chassis_form: string
  company?: string
  id?: string
}

export interface Item {
  category: string
  part_name: string
  spec: string
  qty: number
  base_price: number
  profit_margin: number
  final_price: number
  currency: string
  is_usd_cpu?: boolean
  match_status?: string
  db_price?: number
  history?: any[]
  _histActiveKeys?: string[]
  _histLoaded?: boolean
  _history?: any[]
  _histLoading?: boolean
}

export interface L6MatchedRecord {
  id?: number
  model?: string
  chassis?: string
  drive_bays?: string
  psu?: string
  motherboard?: string
  price?: number
  note?: string
  date?: string
  match_score?: number
  matched_dims?: number
  total_dims?: number
  match_type?: string
  candidates?: L6MatchedRecord[]  // Top 3 candidates for partial match
}

export interface WarrantyInfo {
  detected: boolean
  years: number | null
  rate: number
  description?: string
}

export interface L6Meta {
  model_name?: string
  chassis_form?: string
  drive_bays?: string
  psu?: string
  motherboard?: string
  backplane_desc?: string
  gpu_expansion?: string
  power_cord?: string
  rail_kit?: string
}

export interface ConfigData {
  name: string
  description: string  // 配置描述
  server_model?: string  // 服务器型号
  items: Item[]
  summary: {
    l6_total: number
    kp_total: number
    warranty_total: number
    grand_total: number
  }
  l6_matched_record?: L6MatchedRecord | null
  l6_meta?: L6Meta  // Excel 解析出的原始需求
  warranty_info?: {
    l6: WarrantyInfo
    kp: WarrantyInfo
  }
}

export const useQuoteStore = defineStore('quote', () => {
  // --- State ---
  const opportunityInfo = ref<ProjectInfo>({
    opportunity_id: '', opportunity_name: '', sales_person: '', fae: '', customer_name: '',
    date: '', model_name: '', total_qty: 0, platform_type: '', chassis_form: ''
  })

  const configs = ref<Record<string, ConfigData>>({})
  
  // 每个配置的数量（报价单维度）
  const configQuantities = ref<Record<string, number>>({})
  
  // 质保费率（每个配置独立）
  const warrantyRates = ref<Record<string, { l6: number; kp: number }>>({})
  
  // 财务常量（用户可在线调整）
  const taxRate = ref(0.13) // 增值税率（默认 13%）
  const exchangeRate = ref(7.0) // 美元汇率（默认 7.0）

  // ... Getters (Totals) ---
  const l6Total = computed(() => {
    return Object.values(configs.value).reduce((sum, cfg) => {
      return sum + cfg.summary.l6_total
    }, 0)
  })

  const kpTotal = computed(() => {
    return Object.values(configs.value).reduce((sum, cfg) => {
      return sum + cfg.summary.kp_total
    }, 0)
  })

  const warrantyTotal = computed(() => {
    return Object.values(configs.value).reduce((sum, cfg) => {
      return sum + (cfg.summary.warranty_total || 0)
    }, 0)
  })

  const grandTotal = computed(() => {
    return l6Total.value + kpTotal.value + warrantyTotal.value
  })

  const marginPercent = computed(() => {
    if (grandTotal.value === 0) return 0
    // 计算综合毛利率: (总销售价 - 总成本) / 总销售价
    // 成本 = base_price * qty 的总和（不含利润、不含税）
    let totalCost = 0
    let totalSales = 0
    
    Object.values(configs.value).forEach(cfg => {
      cfg.items.forEach(item => {
        // 成本 = base_price（底价，不含任何加成）
        const itemCost = item.base_price * item.qty
        // 销售价 = final_price * qty
        const itemSales = item.final_price * item.qty
        totalCost += itemCost
        totalSales += itemSales
      })
    })

    if (totalSales === 0) return 0
    return ((totalSales - totalCost) / totalSales) * 100
  })

  // --- Actions ---
  
  function loadData(data: any) {
    // Load Opportunity Info
    if (data.project_info) {
      opportunityInfo.value = {
        ...opportunityInfo.value,
        ...data.project_info
      }
    }
    
    // Load Config Quantities (配置数量)
    if (data.config_quantities) {
      configQuantities.value = data.config_quantities
    }
    
    // Load Configs & Calculate Initial Totals
    const newConfigs: Record<string, ConfigData> = {}
    
    for (const [cfgName, cfgData] of Object.entries(data.configs || {})) {
      const items = (cfgData as any).items || []
      
      // Enrich items with computed final_price if missing
      const processedItems: Item[] = items.map((item: any) => {
        // Ensure numeric types
        item.qty = Number(item.qty) || 1
        item.base_price = Number(item.base_price) || 0
        item.profit_margin = Number(item.profit_margin) || 10
        item.final_price = Number(item.final_price) || 0
        return item
      })

      newConfigs[cfgName] = {
        name: cfgName,
        description: (cfgData as any).description || '',
        server_model: (cfgData as any).server_model || '',
        items: processedItems,
        summary: (cfgData as any).summary || { l6_total: 0, kp_total: 0, grand_total: 0 },
        l6_matched_record: (cfgData as any).l6_matched_record || null,
        l6_meta: (cfgData as any).l6_meta || {},  // Excel 解析出的原始需求
        warranty_info: (cfgData as any).warranty_info || {
          l6: { detected: false, years: null, rate: 0 },
          kp: { detected: false, years: null, rate: 0 }
        }
      }
      
      // 初始化质保费率（从后端返回的 warranty_info）
      // 所有费率默认为 0，遵循"不自动加钱"原则
      const wInfo = (cfgData as any).warranty_info
      if (wInfo) {
        warrantyRates.value[cfgName] = {
          l6: wInfo.l6?.rate ?? 0,
          kp: wInfo.kp?.rate ?? 0
        }
      } else {
        warrantyRates.value[cfgName] = { l6: 0, kp: 0 }
      }
    }
    
    configs.value = newConfigs
    recalculateAll()
  }

  function updateItem(cfgName: string, index: number, field: keyof Item, value: any) {
    const item = configs.value[cfgName]?.items[index]
    if (item) {
      (item as any)[field] = value
      recalculateAll()
    }
  }

  // 设置 L6 质保费率（%）
  function setWarrantyRateL6(cfgName: string, ratePercent: number) {
    if (!warrantyRates.value[cfgName]) {
      warrantyRates.value[cfgName] = { l6: 0, kp: 0 }
    }
    warrantyRates.value[cfgName].l6 = ratePercent / 100
    recalculateAll()
  }

  // 设置 KP 质保费率（%）
  function setWarrantyRateKP(cfgName: string, ratePercent: number) {
    if (!warrantyRates.value[cfgName]) {
      warrantyRates.value[cfgName] = { l6: 0, kp: 0 }
    }
    warrantyRates.value[cfgName].kp = ratePercent / 100
    recalculateAll()
  }

  // 设置 L6 质保年限
  function setWarrantyYearsL6(cfgName: string, years: number | null) {
    const cfg = configs.value[cfgName]
    if (cfg?.warranty_info) {
      cfg.warranty_info.l6.years = years
    }
  }

  // 设置 KP 质保年限
  function setWarrantyYearsKP(cfgName: string, years: number | null) {
    const cfg = configs.value[cfgName]
    if (cfg?.warranty_info) {
      cfg.warranty_info.kp.years = years
    }
  }

  // 清零 L6 质保费率
  function clearWarrantyL6(cfgName: string) {
    if (warrantyRates.value[cfgName]) {
      warrantyRates.value[cfgName].l6 = 0
    }
    recalculateAll()
  }

  // 清零 KP 质保费率
  function clearWarrantyKP(cfgName: string) {
    if (warrantyRates.value[cfgName]) {
      warrantyRates.value[cfgName].kp = 0
    }
    recalculateAll()
  }

  // 设置质保描述
  function setWarrantyDescription(cfgName: string, type: 'l6' | 'kp', desc: string) {
    const cfg = configs.value[cfgName]
    if (cfg?.warranty_info) {
      cfg.warranty_info[type].description = desc
    }
  }

  // 获取某配置的 L6 质保费率（%）
  function getWarrantyRateL6Pct(cfgName: string): number {
    return (warrantyRates.value[cfgName]?.l6 ?? 0) * 100
  }

  // 获取某配置的 KP 质保费率（%）
  function getWarrantyRateKPPct(cfgName: string): number {
    return (warrantyRates.value[cfgName]?.kp ?? 0) * 100
  }

  // 计算某配置的 L6 质保费
  function calcWarrantyFeeL6(cfgName: string): number {
    const cfg = configs.value[cfgName]
    if (!cfg) return 0
    const rate = warrantyRates.value[cfgName]?.l6 ?? 0
    return cfg.summary.l6_total * rate
  }

  // 计算某配置的 KP 质保费
  function calcWarrantyFeeKP(cfgName: string): number {
    const cfg = configs.value[cfgName]
    if (!cfg) return 0
    const rate = warrantyRates.value[cfgName]?.kp ?? 0
    return cfg.summary.kp_total * rate
  }

  // 计算单个配置的财务数据（供组件调用，替代组件内重复逻辑）
  function calcConfigTotals(cfgName: string) {
    const cfg = configs.value[cfgName]
    if (!cfg) return { l6Cost: 0, kpCost: 0, warrantyCost: 0, l6Sales: 0, kpSales: 0, warrantySales: 0, totalCost: 0, totalSales: 0, profit: 0, marginPct: 0 }

    let l6Cost = 0, kpCost = 0, warrantyCost = 0
    let l6Sales = 0, kpSales = 0, warrantySales = 0

    for (const item of cfg.items) {
      const base = item.base_price || 0
      const qty = item.qty || 1
      let unitSales = 0

      if (item.is_usd_cpu || item.currency === 'USD') {
        unitSales = base * exchangeRate.value * (1 + taxRate.value) * (1 + (item.profit_margin || 10) / 100)
      } else {
        const marginDec = (item.profit_margin || 10) > 1 ? (item.profit_margin || 10) / 100 : (item.profit_margin || 10)
        unitSales = base * (1 + marginDec)
      }

      const lineSales = unitSales * qty
      const lineCost = base * qty

      const partName = (item.part_name || '').toLowerCase()
      if (item.category === 'L6' || item.category === '整机') {
        l6Cost += lineCost
        l6Sales += lineSales
      } else if (partName.includes('质保') || partName.includes('warranty')) {
        warrantyCost += lineCost
        warrantySales += lineSales
      } else {
        kpCost += lineCost
        kpSales += lineSales
      }
    }

    // 加上手动质保费用
    const warrantyL6 = calcWarrantyFeeL6(cfgName)
    const warrantyKP = calcWarrantyFeeKP(cfgName)
    const totalWarranty = warrantyCost + warrantyL6 + warrantyKP
    const totalWarrantySales = warrantySales + warrantyL6 + warrantyKP
    
    const totalCost = l6Cost + kpCost + totalWarranty
    const totalSales = l6Sales + kpSales + totalWarrantySales
    const profit = totalSales - totalCost
    const marginPct = totalSales > 0 ? (profit / totalSales) * 100 : 0

    return { l6Cost, kpCost, warrantyCost: totalWarranty, l6Sales, kpSales, warrantySales: totalWarrantySales, totalCost, totalSales, profit, marginPct }
  }

  function recalculateAll() {
    for (const cfg of Object.values(configs.value)) {
      let l6Sum = 0
      let kpSum = 0
      let warrantySum = 0

      for (const item of cfg.items) {
        let unitPrice = item.base_price
        
        // Currency conversion for USD items (with tax)
        // 与后端保持一致：检查 is_usd_cpu 或 currency === 'USD'
        if (item.is_usd_cpu || item.currency === 'USD') {
          unitPrice = unitPrice * exchangeRate.value * (1 + taxRate.value) * (1 + item.profit_margin / 100)
        } else {
          // Normal RMB calculation: Base * (1 + Margin/100)
          // 注意：RMB 项不加税，与后端保持一致
          const marginDecimal = item.profit_margin > 1 ? item.profit_margin / 100 : item.profit_margin
          unitPrice = unitPrice * (1 + marginDecimal)
        }

        item.final_price = Math.round(unitPrice * 100) / 100
        const lineTotal = item.final_price * item.qty

        // 分类统计：L6 / 质保 / KP
        const partName = (item.part_name || '').toLowerCase()
        if (item.category === 'L6' || item.category === '整机') {
          l6Sum += lineTotal
        } else if (partName.includes('质保') || partName.includes('warranty')) {
          warrantySum += lineTotal
        } else {
          kpSum += lineTotal
        }
      }
      cfg.summary.l6_total = Math.round(l6Sum * 100) / 100
      cfg.summary.kp_total = Math.round(kpSum * 100) / 100
      cfg.summary.warranty_total = Math.round(warrantySum * 100) / 100
      cfg.summary.grand_total = cfg.summary.l6_total + cfg.summary.kp_total + cfg.summary.warranty_total
    }
  }

  async function saveProject() {
    try {
      // Check if we're editing an existing quotation
      const quotationId = opportunityInfo.value.quotation_id
      
      if (quotationId) {
        // Editing existing quotation: update items + config_quantities + config_descriptions
        const items: any[] = []
        for (const [cfgName, cfg] of Object.entries(configs.value)) {
          for (const item of cfg.items) {
            items.push({
              ...item,
              config_name: cfgName
            })
          }
        }
        
        const payload = {
          items: items,
          config_quantities: configQuantities.value,
          config_descriptions: Object.fromEntries(
            Object.entries(configs.value).map(([name, cfg]) => [name, cfg.description])
          ),
          config_server_models: Object.fromEntries(
            Object.entries(configs.value).map(([name, cfg]) => [name, cfg.server_model || ''])
          )
        }

        const result = await quotationApi.updateDetails(quotationId, payload)
        console.log('[saveProject] Updated quotation items:', result)
        message.success('报价单已更新')
      } else {
        // Creating new opportunity: use existing /opportunities endpoint
        // Ensure opportunity_id exists
        if (!opportunityInfo.value.opportunity_id) {
          // Generate one from opportunity_name + timestamp
          const ts = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').slice(4)
          opportunityInfo.value.opportunity_id = `${opportunityInfo.value.opportunity_name || 'opportunity'}_${ts}`
        }
        
        // Read temp_file info from sessionStorage (saved during upload)
        const quotationData = JSON.parse(sessionStorage.getItem('quotation_data') || '{}')
        console.log('[DEBUG saveProject] quotationData:', quotationData)
        console.log('[DEBUG saveProject] temp_file:', quotationData.temp_file)
        
        const payload = {
          project_info: {
            ...opportunityInfo.value,
            config_count: Object.keys(configs.value).length
          },
          configs: configs.value,
          config_quantities: configQuantities.value,
          warranty_rates: warrantyRates.value,
          totals: {
            l6_total: l6Total.value,
            kp_total: kpTotal.value,
            grand_total: grandTotal.value
          },
          temp_file: quotationData.temp_file || null
        }
        // configs already includes server_model per config, so no extra field needed
        console.log('[DEBUG saveProject] payload.temp_file:', payload.temp_file)
        await saveProjectAPI(payload)
        message.success('✅ 商机保存成功！')
      }
    } catch (e) {
      console.error('[saveProject] Error:', e)
      message.error('❌ 保存失败')
    }
  }

  async function doExport(templateId?: string) {
    const pid = opportunityInfo.value.opportunity_id || opportunityInfo.value.opportunity_name
    if (!pid) {
      message.warning('请先保存商机或提供商机信息后再导出')
      return
    }
    try {
      await exportProjectAPI(pid, templateId)
      message.success('✅ 导出成功')
    } catch (e) {
      console.error('[doExport]', e)
      message.error('❌ 导出失败')
    }
  }

  return {
    opportunityInfo, configs, configQuantities, warrantyRates, taxRate, exchangeRate,
    l6Total, kpTotal, grandTotal, marginPercent,
    loadData, updateItem,
    setWarrantyRateL6, setWarrantyRateKP,
    setWarrantyYearsL6, setWarrantyYearsKP,
    clearWarrantyL6, clearWarrantyKP,
    setWarrantyDescription,
    getWarrantyRateL6Pct, getWarrantyRateKPPct,
    calcWarrantyFeeL6, calcWarrantyFeeKP,
    calcConfigTotals,
    recalculateAll, saveProject, doExport
  }
})
