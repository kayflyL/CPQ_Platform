/**
 * 商机业务结果（商机状态）唯一口径：商机线索列表内联切换、商机详情页、门户工作台表格共用。
 */
export const RESULT_OPTIONS = [
  { value: 'pending', label: '进行中', color: 'processing', dot: '#1677FF' },
  { value: 'won', label: '已中标', color: 'success', dot: '#52C9A0' },
  { value: 'lost', label: '已丢标', color: 'error', dot: '#FF6B6B' },
  { value: 'expired', label: '已过期', color: 'warning', dot: '#F4D28A' },
] as const

export function resultLabel(val?: string | null): string {
  return RESULT_OPTIONS.find((o) => o.value === val)?.label ?? '进行中'
}

export function resultTagColor(record: any): string {
  return RESULT_OPTIONS.find((o) => o.value === record?.result)?.color ?? 'default'
}
