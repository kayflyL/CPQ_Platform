/** 平台/系列颜色映射（表现层）。
 *  系列枚举本身是数据驱动（system_config.server_series，见 useSeries）；这里只管图表着色。
 *  已清理迁移过的脏键（兆芯→Polaris、INTEL→Intel）；保留 `INTEL&Orion` 混合值与未分类/其他兜底。
 *  未来要可配置：给 server_series 每项加 color 字段，这里改读 useSeries().items 的 color。 */
export const PLAT_COLOR: Record<string, string> = {
  Orion: '#0EA5E9',
  Polaris: '#FF3B5C',
  Intel: '#8A94A8',
  工作站: '#A855F7',
  'INTEL&Orion': '#8A94A8',  // 混合平台（特殊业务值，迁移不动）
  其他: '#6B7280',
  未分类: '#6B7280',
}
export const PLAT_COLOR_FALLBACK = '#6B7280'
