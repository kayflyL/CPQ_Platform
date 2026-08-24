/** 产品能力发丝线图标注册表（数据/技术派线稿）。
 *  约定：线稿元素用 currentColor（随容器文字色），每图恰好一个指示灯元素用 var(--sun-color)（详情页随主题联动；管理页回落酒红）。
 *  详情页能力卡与编辑器图标选择器共用这一份来源，别在页面里散落 SVG。 */
export const CAP_ICONS: Record<string, string> = {
  chip: '<rect x="12" y="8" width="28" height="24" rx="2" stroke="currentColor" stroke-width="1.5"/><rect x="19" y="15" width="14" height="10" rx="1" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5"/><path d="M18 8V3M24 8V3M30 8V3M34 8V3M18 32v-5M24 32v-5M30 32v-5M34 32v-5M12 14H7M12 20H7M12 26H7M40 14h5M40 20h5M40 26h5" stroke="currentColor" stroke-width="1.5"/>',
  slots: '<rect x="4" y="5" width="36" height="8" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="4" y="16" width="36" height="8" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="4" y="27" width="36" height="8" rx="1" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5" stroke-dasharray="4 3"/><path d="M44 27v10M39 32h10" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5"/>',
  net: '<rect x="4" y="9" width="11" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="4" y="22" width="11" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/><path d="M15 13.5h24m0 0-4-4m4 4-4 4M15 26.5h31m0 0-4-4m4 4-4 4" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5"/>',
  drive: '<rect x="10" y="5" width="32" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="10" y="16" width="32" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="10" y="27" width="32" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/><circle cx="37" cy="9.5" r="1.6" fill="var(--sun-color, #FF7A4D)"/><circle cx="37" cy="20.5" r="1.6" fill="var(--sun-color, #FF7A4D)"/><circle cx="37" cy="31.5" r="1.6" fill="var(--sun-color, #FF7A4D)"/>',
  term: '<rect x="5" y="6" width="42" height="28" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M5 14h42" stroke="currentColor" stroke-width="1.5"/><path d="M11 20l5 4-5 4" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5"/><path d="M20 28h14" stroke="currentColor" stroke-width="1.5"/>',
  fan: '<circle cx="18" cy="20" r="13" stroke="currentColor" stroke-width="1.5"/><path d="M18 20c0-5 3-8 8-8M18 20c5 0 8 3 8 8M18 20c0 5-3 8-8 8M18 20c-5 0-8-3-8-8" stroke="currentColor" stroke-width="1.5"/><circle cx="18" cy="20" r="2.2" fill="var(--sun-color, #FF7A4D)"/><rect x="36" y="12" width="11" height="16" rx="1" stroke="currentColor" stroke-width="1.5"/><path d="M38.5 16h6M38.5 20h6" stroke="currentColor" stroke-width="1.2"/>',
  shield: '<path d="M26 4l16 6v10c0 9-6.5 14.5-16 17-9.5-2.5-16-8-16-17V10l16-6z" stroke="currentColor" stroke-width="1.5"/><path d="M19 21l5 5 10-11" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5"/>',
  rack: '<rect x="10" y="4" width="32" height="32" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M10 14.7h32M10 25.4h32" stroke="currentColor" stroke-width="1.5"/><rect x="16" y="8" width="12" height="2.5" fill="var(--sun-color, #FF7A4D)"/><circle cx="36" cy="9" r="1.4" fill="currentColor"/><circle cx="36" cy="20" r="1.4" fill="currentColor"/><circle cx="36" cy="30" r="1.4" fill="currentColor"/>',
  mesh: '<rect x="5" y="5" width="17" height="11" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="30" y="5" width="17" height="11" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="5" y="24" width="17" height="11" rx="1" stroke="currentColor" stroke-width="1.5"/><rect x="30" y="24" width="17" height="11" rx="1" stroke="currentColor" stroke-width="1.5"/><path d="M13.5 16v8M38.5 16v8" stroke="currentColor" stroke-width="1.2"/><path d="M22 10.5h8M22 29.5h8" stroke="var(--sun-color, #FF7A4D)" stroke-width="1.5"/>',
}

export const CAP_ICON_KEYS = Object.keys(CAP_ICONS)

/** 包一层完整 <svg>；未知键回落 chip。 */
export function capIconSvg(key?: string): string {
  const body = (key && CAP_ICONS[key]) || CAP_ICONS.chip
  return `<svg viewBox="0 0 52 40" fill="none" xmlns="http://www.w3.org/2000/svg">${body}</svg>`
}
