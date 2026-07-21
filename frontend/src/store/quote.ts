import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { message } from 'ant-design-vue'
import { saveProject as saveProjectAPI, quotationApi } from '@/api'

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
  quotation_id?: string
  version?: string
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
  pn?: string  // KP 新建模式：料号库 pn（PartPicker 选中）；走 opportunity_items.extra_fields 往返
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
  base_price?: number
  front_panel_price?: number
  rear_panel_price?: number
  psu_price?: number
  note?: string
  date?: string
  match_score?: number
  matched_dims?: number
  total_dims?: number
  match_type?: string
  candidates?: L6MatchedRecord[]  // Top 3 candidates for partial match
}

export interface WarrantyInfo {
  years: number | null
  rate: number
  description?: string
}

export interface ConfigData {
  name: string
  description: string  // 配置描述
  server_model?: string  // 服务器型号（型号名称字符串，导出模板字段绑定用，恒有值）
  server_model_id?: number  // 机型目录 id（下拉选中目录机型时填；自由输入/旧报价单留空）
  items: Item[]
  summary: {
    l6_total: number
    kp_total: number
    warranty_total: number
    grand_total: number
  }
  l6_matched_record?: L6MatchedRecord | null
  l6_bom_config?: {  // L6 BOM 配置数据
    base_template?: any
    front_panel_parts?: any[]
    rear_panel_parts?: any[]
    psu_parts?: any[]
  }
  l6_custom_price?: number  // 当前生效成本（自动推导或手填）
  l6_price_manual?: boolean // 手填锁定：true 时选配推导不覆盖 l6_custom_price
  l6_auto_price?: number    // 最近一次选配推导的成本，切回自动时恢复用
  l6_profit_margin?: number  // 利润率
  base_config_id?: number  // 新流程：L6ChassisConfig 选中的基准配置 ID
  l6_bom_picks?: any  // 新流程：L6ChassisConfig 组件状态快照（rear/overrides/bp…），切 tab 重挂 hydrate 用
  bom_template?: any  // 左栏 L6 摘要模板（机型族行骨架 {id,name,rows}）
  bom_context?: any  // 左栏 L6 摘要行值（{rowKey: {desc,qty}}，L6ChassisConfig 解析）
  bom_source?: 'live' | 'excel'  // 左栏模式：live=跟随中栏选配实时变动 / excel=Excel 上传参考(静态快照)
  bom_excel_rows?: Item[]  // excel 模式左栏快照（加载时固化的 L6+KP 原始行，不随中栏变）
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
  
  // 每个配置选择的部件类型（用于生成描述）
  const configSelectedParts = ref<Record<string, string[]>>({})
  
  // 质保费率（每个配置独立）
  const warrantyRates = ref<Record<string, { l6: number; kp: number }>>({})
  
  // 财务常量（用户可在线调整）
  const taxRate = ref(0.13) // 增值税率（默认 13%）
  const exchangeRate = ref(7.0) // 美元汇率（默认 7.0）

  // 从系统配置加载财务常量默认值
  const loadFinancialDefaults = async () => {
    try {
      const [taxRes, exchangeRes] = await Promise.all([
        fetch('/api/system-config/tax_rate'),
        fetch('/api/system-config/usd_to_rmb')
      ])
      if (taxRes.ok) {
        const taxData = await taxRes.json()
        taxRate.value = taxData.value ?? 0.13
      }
      if (exchangeRes.ok) {
        const exchangeData = await exchangeRes.json()
        exchangeRate.value = exchangeData.value ?? 7.0
      }
    } catch (e) {
      console.warn('Failed to load financial defaults:', e)
    }
  }

  // 初始化时加载默认值
  loadFinancialDefaults()

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
        // 跳过 L6/整机 项（L6 只有一个价格，由 l6_custom_price 统一管理）
        if (item.category === 'L6' || item.category === '整机') return
        
        // 成本 = base_price（底价，不含任何加成）
        const itemCost = item.base_price * item.qty
        // 销售价 = final_price * qty
        const itemSales = item.final_price * item.qty
        totalCost += itemCost
        totalSales += itemSales
      })
      // L6 只有一个机箱，始终使用 l6_custom_price
      totalCost += cfg.l6_custom_price || 0
      const margin = cfg.l6_profit_margin || 0
      totalSales += (cfg.l6_custom_price || 0) * (1 + margin / 100)
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
        // db_price 归一化：持久化往返可能残留 ""，统一成 null 或数字，避免后续 `== null` 误判
        const dbRaw = item.db_price
        const dbNum = dbRaw === '' || dbRaw == null ? null : Number(dbRaw)
        item.db_price = (dbNum == null || !Number.isFinite(dbNum)) ? null : dbNum
        return item
      })

      // 左栏来源:持久化 bom_source 优先,否则入口信号(Excel 上传→excel / 其余→live)
      const bomSource: 'live' | 'excel' = ((cfgData as any).bom_source ?? data.config_l6_picks?.[cfgName]?.bom_source ?? (data.is_excel_quote ? 'excel' : 'live')) === 'excel' ? 'excel' : 'live'

      // l6_custom_price：优先 config_l6_picks（显式持久化/手填）> cfgData.per_cfg_l6；
      // live 模式额外回落 items L6 行求和（老数据迁移）。excel 模式 L6 仅作参考、不参与算价。
      const picksL6Price = Number((data.config_l6_picks?.[cfgName] as any)?.l6_custom_price) || 0
      let l6CustomPrice = picksL6Price || Number((cfgData as any).l6_custom_price) || 0
      if (l6CustomPrice === 0 && bomSource !== 'excel') {
        const l6Items = processedItems.filter(i => i.category === 'L6' || i.category === '整机')
        if (l6Items.length > 0) {
          l6CustomPrice = l6Items.reduce((sum, i) => sum + i.base_price * i.qty, 0)
        }
      }

      newConfigs[cfgName] = {
        name: cfgName,
        description: (cfgData as any).description || '',
        server_model: (cfgData as any).server_model || '',
        server_model_id: (cfgData as any).server_model_id ?? (data.config_l6_picks?.[cfgName] as any)?.server_model_id ?? undefined,
        items: processedItems,
        summary: (cfgData as any).summary || { l6_total: 0, kp_total: 0, grand_total: 0 },
        l6_matched_record: (cfgData as any).l6_matched_record || null,
        l6_custom_price: l6CustomPrice,
        l6_price_manual: (data.config_l6_picks?.[cfgName] as any)?.l6_price_manual ?? false,
        l6_auto_price: (data.config_l6_picks?.[cfgName] as any)?.l6_auto_price ?? undefined,
        l6_profit_margin: (cfgData as any).l6_profit_margin || 10,
        base_config_id: (cfgData as any).base_config_id ?? (data.config_l6_picks?.[cfgName]?.base_config_id) ?? undefined,
        l6_bom_picks: (cfgData as any).l6_bom_picks ?? (data.config_l6_picks?.[cfgName]?.picks) ?? undefined,
        bom_template: (cfgData as any).bom_template ?? (data.config_l6_picks?.[cfgName]?.bom_template) ?? undefined,
        bom_context: (cfgData as any).bom_context ?? (data.config_l6_picks?.[cfgName]?.bom_context) ?? undefined,
        bom_source: bomSource,
        bom_excel_rows: bomSource === 'excel'
          ? ((data.config_l6_picks?.[cfgName] as any)?.bom_excel_rows
              ?? processedItems.filter((i: Item) => i.category === 'L6' || i.category === '整机' || i.category === 'Key Parts').map((i: Item) => ({ ...i })))
          : undefined,
        warranty_info: (cfgData as any).warranty_info || {
          l6: { years: null, rate: 0 },
          kp: { years: null, rate: 0 }
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

  // 设置 L6 自定义价格（四步配置的结果）
  function setL6CustomPrice(cfgName: string, price: number, margin?: number) {
    const cfg = configs.value[cfgName]
    if (cfg) {
      cfg.l6_custom_price = price
      cfg.l6_price_manual = true  // 手填即锁定，选配推导不再覆盖
      if (margin != null) cfg.l6_profit_margin = margin
      recalculateAll()
    }
  }

  // 切回自动：解除手填锁定，l6_custom_price 恢复为最近一次选配推导值
  function setL6PriceAuto(cfgName: string) {
    const cfg = configs.value[cfgName]
    if (!cfg) return
    cfg.l6_price_manual = false
    cfg.l6_custom_price = cfg.l6_auto_price ?? cfg.l6_custom_price ?? 0
    recalculateAll()
  }

  // 设置 L6 匹配记录（卡片显示用）
  function setL6MatchedRecord(cfgName: string, record: any) {
    const cfg = configs.value[cfgName]
    if (cfg) {
      cfg.l6_matched_record = record
    }
  }

  // 设置 L6 BOM 配置
  function setL6BomConfig(cfgName: string, bomConfig: any) {
    const cfg = configs.value[cfgName]
    if (cfg) {
      cfg.l6_bom_config = bomConfig
    }
  }

  // 新流程：L6ChassisConfig 选配变动 → 重建 cfg.items 的 L6 行 + 设 l6_custom_price + 存 picks 快照
  // payload: { baseConfigId, totals, picks, l6Rows }（来自 L6ChassisConfig 的 apply 事件）
  function setL6ChassisPicks(cfgName: string, payload: { baseConfigId: number | null; totals: any; picks: any; l6Rows: any[] }) {
    const cfg = configs.value[cfgName]
    if (!cfg) return
    // 守护：未选基准配置且组件初挂（空 l6Rows）时，保留已有 l6_custom_price，仅记录 picks
    if (!payload.baseConfigId && (!payload.l6Rows || payload.l6Rows.length === 0)) {
      cfg.l6_bom_picks = payload.picks
      return
    }
    // L6 选配结果不写回 cfg.items：避免污染 excel 原版 items，也避免左栏误显机箱原版料。
    // 左栏与导出统一走 bom_excel_rows（excel）或 bom_template（live）；L6 价格独立走 l6_custom_price。
    // 推导成本始终缓存到 l6_auto_price；仅未手填锁定时才覆盖 l6_custom_price。
    const derived = payload.totals?.l6 ?? 0
    cfg.l6_auto_price = derived
    if (!cfg.l6_price_manual) {
      cfg.l6_custom_price = derived
    }
    cfg.base_config_id = payload.baseConfigId ?? undefined
    cfg.l6_bom_picks = payload.picks
    cfg.bom_template = payload.bomTemplate ?? undefined
    cfg.bom_context = payload.bomContext ?? undefined
    recalculateAll()
  }

  // L6 单一利润率变动 → 重算 cfg.items 里所有 L6 行的 final_price（base × (1+利润率)）
  // 独立于 L6ChassisConfig 的 apply（选配变动），保证两路都同步利润率
  function setL6ProfitMargin(cfgName: string, marginPct: number) {
    const cfg = configs.value[cfgName]
    if (!cfg) return
    cfg.l6_profit_margin = marginPct
    const margin = marginPct / 100
    for (const item of cfg.items) {
      if (item.category === 'L6' || item.category === '整机') {
        item.final_price = Math.round(((item.base_price || 0) * (1 + margin)) * 100) / 100
        item.profit_margin = marginPct
      }
    }
    recalculateAll()
  }

  // KP 整体利润率：把该配置下所有 KP 配件的 profit_margin 统一设成同一个值
  // 每个 item 的 profit_margin 已随 items 持久化，这里只是批量统调，无需额外字段
  function setKpProfitMargin(cfgName: string, marginPct: number) {
    const cfg = configs.value[cfgName]
    if (!cfg) return
    for (const item of cfg.items) {
      if (item.category === 'Key Parts') {
        item.profit_margin = marginPct
      }
    }
    recalculateAll()
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

      // 跳过 L6/整机 项（L6 只有一个价格，由 l6_custom_price 统一管理）
      if (item.category === 'L6' || item.category === '整机') continue

      const partName = (item.part_name || '').toLowerCase()
      if (partName.includes('质保') || partName.includes('warranty')) {
        warrantyCost += lineCost
        warrantySales += lineSales
      } else {
        kpCost += lineCost
        kpSales += lineSales
      }
    }

    // L6 只有一个机箱，价格由 l6_custom_price 统一管理
    l6Cost = cfg.l6_custom_price || 0
    const l6Margin = cfg.l6_profit_margin || 0
    l6Sales = l6Cost * (1 + l6Margin / 100)

    // 加上手动质保费用
    const warrantyL6 = calcWarrantyFeeL6(cfgName)
    const warrantyKP = calcWarrantyFeeKP(cfgName)
    const totalWarranty = warrantyCost + warrantyL6 + warrantyKP
    const totalWarrantySales = warrantySales + warrantyL6 + warrantyKP
    
    const totalCost = l6Cost + kpCost + totalWarranty
    const totalSales = l6Sales + kpSales + totalWarrantySales
    const profit = totalSales - totalCost
    const marginPct = totalCost > 0 ? (profit / totalCost) * 100 : 0

    return { l6Cost, kpCost, warrantyCost: totalWarranty, l6Sales, kpSales, warrantySales: totalWarrantySales, totalCost, totalSales, profit, marginPct }
  }

  // 为每个配置创建 computed 的财务数据（确保响应式追踪）
  const configTotalsMap = computed(() => {
    const result: Record<string, any> = {}
    for (const cfgName of Object.keys(configs.value)) {
      result[cfgName] = calcConfigTotals(cfgName)
    }
    return result
  })

  // 获取指定配置的财务数据
  function getConfigTotals(cfgName: string) {
    return configTotalsMap.value[cfgName] || { l6Cost: 0, kpCost: 0, warrantyCost: 0, l6Sales: 0, kpSales: 0, warrantySales: 0, totalCost: 0, totalSales: 0, profit: 0, marginPct: 0 }
  }

  function recalculateAll() {
    for (const cfg of Object.values(configs.value)) {
      let l6Sum = 0
      let kpSum = 0
      let warrantySum = 0

      for (const item of cfg.items) {
        // 跳过 L6/整机 项（L6 只有一个价格，由 l6_custom_price 统一管理）
        if (item.category === 'L6' || item.category === '整机') continue

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
        kpSum += lineTotal
      }
      
      // L6 只有一个机箱，始终使用 l6_custom_price
      l6Sum = cfg.l6_custom_price || 0

      // 根据用户填写的年限和费率自动计算维保价格
      // 公式：维保价格 = 硬件总价 × 费率 × 年限
      const l6WarrantyPrice = cfg.warranty_info?.l6?.years && cfg.warranty_info?.l6?.rate
        ? l6Sum * cfg.warranty_info.l6.rate * cfg.warranty_info.l6.years
        : 0
      const kpWarrantyPrice = cfg.warranty_info?.kp?.years && cfg.warranty_info?.kp?.rate
        ? kpSum * cfg.warranty_info.kp.rate * cfg.warranty_info.kp.years
        : 0
      warrantySum = l6WarrantyPrice + kpWarrantyPrice

      cfg.summary.l6_total = Math.round(l6Sum * (1 + ((cfg.l6_profit_margin ?? 10) / 100)) * 100) / 100
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
          ),
          config_warranty_info: Object.fromEntries(
            Object.entries(configs.value).map(([name, cfg]) => [name, cfg.warranty_info || {}])
          ),
          config_l6_picks: Object.fromEntries(
            Object.entries(configs.value).map(([name, cfg]) => [name, {
              base_config_id: cfg.base_config_id ?? null,
              server_model_id: cfg.server_model_id ?? null,
              picks: cfg.l6_bom_picks ?? null,
              bom_template: cfg.bom_template ?? null,
              bom_context: cfg.bom_context ?? null,
              bom_source: cfg.bom_source ?? null,
              // excel 模式持久化左栏快照，使左栏与导出同源、不依赖可变的 cfg.items
              bom_excel_rows: cfg.bom_source === 'excel' ? (cfg.bom_excel_rows ?? null) : null,
              // 显式持久化 L6 价格：items 不再写 L6 行，价格不能再从 items 派生
              l6_custom_price: cfg.l6_custom_price ?? 0,
              l6_profit_margin: cfg.l6_profit_margin ?? 10,
              l6_price_manual: cfg.l6_price_manual ?? false,
              l6_auto_price: cfg.l6_auto_price ?? null,
            }])
          ),
          config_selected_parts: configSelectedParts.value
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
          opportunity_info: {
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

  return {
    opportunityInfo, configs, configQuantities, configSelectedParts, warrantyRates, taxRate, exchangeRate,
    l6Total, kpTotal, grandTotal, marginPercent,
    loadData, updateItem,
    setWarrantyRateL6, setWarrantyRateKP,
    setWarrantyYearsL6, setWarrantyYearsKP,
    clearWarrantyL6, clearWarrantyKP,
    setWarrantyDescription,
    getWarrantyRateL6Pct, getWarrantyRateKPPct,
    calcWarrantyFeeL6, calcWarrantyFeeKP,
    calcConfigTotals, getConfigTotals,
    setL6CustomPrice, setL6PriceAuto, setL6MatchedRecord, setL6BomConfig, setL6ChassisPicks, setL6ProfitMargin, setKpProfitMargin,
    recalculateAll, saveProject
  }
})
