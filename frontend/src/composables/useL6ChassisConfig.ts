import { ref, computed } from 'vue'
import axios from 'axios'

// 数据类型定义
export interface BaseConfig {
  config_id: number
  chassis: string
  chassis_series: string
  drive_bays: string
  backplane_type: string
  base_price: number
  description?: string
}

export interface FrontPanelItem {
  item_id: number
  cable_type: string
  part_name: string
  description: string
  unit_price: number
  applicable_drive_bays: string
  applicable_backplane: string
}

export interface RearPanelItem {
  item_id: number
  option_type: string
  part_name: string
  description: string
  unit_price: number
  applicable_chassis: string
  applicable_backplane: string
}

export interface PsuOption {
  psu_id: number
  wattage: string
  part_name: string
  description: string
  unit_price: number
  applicable_chassis: string
}

/** 解析 JSON 数组字段（数据库存的是 '["a","b"]' 格式） */
function parseJsonArray(val: string | string[] | null | undefined): string[] {
  if (!val) return []
  if (Array.isArray(val)) return val
  try { return JSON.parse(val) } catch { return [] }
}

export function useL6ChassisConfig() {
  // 数据状态
  const baseConfigs = ref<BaseConfig[]>([])
  const frontPanelItems = ref<FrontPanelItem[]>([])
  const rearPanelItems = ref<RearPanelItem[]>([])
  const psuOptions = ref<PsuOption[]>([])

  // 选择状态（ID）
  const selectedBaseConfigId = ref<number | null>(null)
  const selectedFrontPanelId = ref<number | null>(null)
  const selectedRearPanelId = ref<number | null>(null)
  const selectedPsuId = ref<number | null>(null)

  // 选中的对象（computed）
  const selectedBaseConfig = computed(() => baseConfigs.value.find(c => c.config_id === selectedBaseConfigId.value) || null)
  const selectedFrontPanel = computed(() => frontPanelItems.value.find(i => i.item_id === selectedFrontPanelId.value) || null)
  const selectedRearPanel = computed(() => rearPanelItems.value.find(i => i.item_id === selectedRearPanelId.value) || null)
  const selectedPsu = computed(() => psuOptions.value.find(i => i.psu_id === selectedPsuId.value) || null)

  // 级联过滤（正确的 JSON 解析逻辑）
  const filteredFrontPanelItems = computed(() => {
    if (!selectedBaseConfig.value) return frontPanelItems.value
    const driveBays = selectedBaseConfig.value.drive_bays
    const backplaneType = selectedBaseConfig.value.backplane_type
    return frontPanelItems.value.filter(item => {
      const bays = parseJsonArray(item.applicable_drive_bays)
      const baysMatch = bays.length === 0 || bays.includes(driveBays)
      const backplanes = parseJsonArray(item.applicable_backplane)
      const backplaneMatch = backplanes.length === 0 || backplanes.includes(backplaneType)
      return baysMatch && backplaneMatch
    })
  })

  const filteredRearPanelItems = computed(() => {
    if (!selectedBaseConfig.value) return rearPanelItems.value
    const chassisType = selectedBaseConfig.value.chassis
    const backplaneType = selectedBaseConfig.value.backplane_type
    return rearPanelItems.value.filter(item => {
      const chassis = parseJsonArray(item.applicable_chassis)
      const chassisMatch = chassis.length === 0 || chassis.includes(chassisType)
      const backplanes = parseJsonArray(item.applicable_backplane)
      const backplaneMatch = backplanes.length === 0 || backplanes.includes(backplaneType)
      return chassisMatch && backplaneMatch
    })
  })

  const filteredPsuOptions = computed(() => {
    if (!selectedBaseConfig.value) return psuOptions.value
    const chassisType = selectedBaseConfig.value.chassis
    return psuOptions.value.filter(item => {
      const chassis = parseJsonArray(item.applicable_chassis)
      return chassis.length === 0 || chassis.includes(chassisType)
    })
  })

  // 数据加载函数
  const loadBaseConfigs = async () => {
    try {
      const res = await axios.get('/api/l6-chassis/base-configs')
      baseConfigs.value = res.data.configs || []
    } catch (e: any) {
      console.error('Failed to load base configs:', e)
    }
  }

  const loadFrontPanelItems = async () => {
    try {
      const res = await axios.get('/api/l6-chassis/front-panel')
      frontPanelItems.value = res.data.items || []
    } catch (e: any) {
      console.error('Failed to load front panel items:', e)
    }
  }

  const loadRearPanelItems = async () => {
    try {
      const res = await axios.get('/api/l6-chassis/rear-panel')
      rearPanelItems.value = res.data.items || []
    } catch (e: any) {
      console.error('Failed to load rear panel items:', e)
    }
  }

  const loadPsuOptions = async () => {
    try {
      const res = await axios.get('/api/l6-chassis/psu')
      psuOptions.value = res.data.items || []
    } catch (e: any) {
      console.error('Failed to load PSU options:', e)
    }
  }

  // 批量刷新
  const refreshAll = async () => {
    await Promise.all([
      loadBaseConfigs(),
      loadFrontPanelItems(),
      loadRearPanelItems(),
      loadPsuOptions()
    ])
  }

  // 选择处理（接收 row-selection 的数组格式）
  const onSelectBaseConfig = (selectedRowKeys: number[]) => {
    selectedBaseConfigId.value = selectedRowKeys[0] || null
    selectedFrontPanelId.value = null
    selectedRearPanelId.value = null
    selectedPsuId.value = null
  }

  const onSelectFrontPanel = (selectedRowKeys: number[]) => {
    selectedFrontPanelId.value = selectedRowKeys[0] || null
  }

  const onSelectRearPanel = (selectedRowKeys: number[]) => {
    selectedRearPanelId.value = selectedRowKeys[0] || null
  }

  const onSelectPsu = (selectedRowKeys: number[]) => {
    selectedPsuId.value = selectedRowKeys[0] || null
  }

  // 价格计算
  const baseConfigPrice = computed(() => selectedBaseConfig.value?.base_price || 0)
  const frontPanelPrice = computed(() => selectedFrontPanel.value?.unit_price || 0)
  const rearPanelPrice = computed(() => selectedRearPanel.value?.unit_price || 0)
  const psuPrice = computed(() => selectedPsu.value?.unit_price || 0)
  const totalBasePrice = computed(() => baseConfigPrice.value + frontPanelPrice.value + rearPanelPrice.value + psuPrice.value)

  // 重置选择
  const resetSelections = () => {
    selectedBaseConfigId.value = null
    selectedFrontPanelId.value = null
    selectedRearPanelId.value = null
    selectedPsuId.value = null
  }

  return {
    // 数据
    baseConfigs,
    frontPanelItems,
    rearPanelItems,
    psuOptions,
    // 选择 ID
    selectedBaseConfigId,
    selectedFrontPanelId,
    selectedRearPanelId,
    selectedPsuId,
    // 选中对象
    selectedBaseConfig,
    selectedFrontPanel,
    selectedRearPanel,
    selectedPsu,
    // 级联过滤
    filteredFrontPanelItems,
    filteredRearPanelItems,
    filteredPsuOptions,
    // 数据加载
    loadBaseConfigs,
    loadFrontPanelItems,
    loadRearPanelItems,
    loadPsuOptions,
    refreshAll,
    // 选择处理
    onSelectBaseConfig,
    onSelectFrontPanel,
    onSelectRearPanel,
    onSelectPsu,
    // 价格计算
    baseConfigPrice,
    frontPanelPrice,
    rearPanelPrice,
    psuPrice,
    totalBasePrice,
    // 重置
    resetSelections
  }
}
