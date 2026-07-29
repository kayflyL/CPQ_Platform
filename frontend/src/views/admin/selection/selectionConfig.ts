/**
 * 选型配置画布配置常量
 * 品类色系、图标映射、层级定义
 */

/** 品类色系（符合 Glass Console 马卡龙语义色） */
export const CATEGORY_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  // 核心计算 - 蓝系
  CPU: { bg: 'rgba(22, 119, 255, 0.08)', border: '#1677ff', text: '#1677ff' },
  Memory: { bg: 'rgba(168, 85, 247, 0.08)', border: '#a855f7', text: '#a855f7' },

  // 加速计算 - 橙系
  GPU: { bg: 'rgba(250, 140, 22, 0.08)', border: '#fa8c16', text: '#fa8c16' },
  'GPU电源线': { bg: 'rgba(250, 140, 22, 0.06)', border: '#ffa940', text: '#d48806' },

  // 存储子系统 - 青系
  '硬盘': { bg: 'rgba(54, 207, 207, 0.08)', border: '#36cfcf', text: '#13a8a8' },
  '背板': { bg: 'rgba(54, 207, 207, 0.06)', border: '#36cfcf', text: '#13a8a8' },
  HBA: { bg: 'rgba(92, 219, 211, 0.06)', border: '#5cdbd3', text: '#36cfcf' },
  RAID: { bg: 'rgba(92, 219, 211, 0.06)', border: '#5cdbd3', text: '#36cfcf' },

  // 电源/散热 - 红/灰系
  PSU: { bg: 'rgba(255, 107, 107, 0.08)', border: '#ff6b6b', text: '#f5222d' },
  '风扇': { bg: 'rgba(149, 160, 178, 0.08)', border: '#95a0b2', text: '#64748b' },

  // 网络 - 绿系
  '网卡': { bg: 'rgba(82, 201, 160, 0.08)', border: '#52c9a0', text: '#16a34a' },

  // 默认
  '_default': { bg: 'rgba(255, 255, 255, 0.7)', border: 'rgba(0, 0, 0, 0.12)', text: '#1d2129' },
}

/** 配件分类层级（用于 dagre 分组，从左到右） */
export const CATEGORY_LAYERS: Record<string, number> = {
  CPU: 1, Memory: 1,           // 第一列：核心计算
  GPU: 2, 'GPU电源线': 2,       // 第二列：加速计算
  '硬盘': 3, '背板': 3, HBA: 3, RAID: 3,  // 第三列：存储子系统
  PSU: 4, '风扇': 4, '网卡': 4,            // 第四列：其他
}

/** 获取品类样式 */
export function getCategoryStyle(category: string) {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS['_default']
}

/** 获取品类层级（用于 dagre 排序） */
export function getCategoryLayer(category: string) {
  return CATEGORY_LAYERS[category] || 5
}

/** 节点尺寸 */
export const NODE_WIDTH = 140
export const NODE_HEIGHT = 48