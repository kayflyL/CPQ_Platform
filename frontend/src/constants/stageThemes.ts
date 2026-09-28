/** 机型详情页「场景主题」：天空渐变 + 大地遮罩 + 旭日三色 + 内容区底色。
 *  从 ModelDetailPage 抽取共享——星河首页机型详情弹窗 banner 同源复用。 */
export type StageThemeKey = 'wine' | 'ocean' | 'carbon' | 'violet'
export interface StageTheme {
  key: StageThemeKey; label: string
  bg: string        // 天空→大地 整体垂直渐变
  earth: string     // 地平线下方遮罩（盖住太阳下半、加深大地）
  sun: string       // 地平线 / 太阳主色
  sunBright: string // 太阳最亮中心
  glow: string      // 天空光晕扩散
  page: string      // 内容区整页底色（hero 之下）
  band: string      // 「产品能力」暗色带底色
}

export const STAGE_THEMES: StageTheme[] = [
  { key: 'wine', label: '酒红',
    bg: 'linear-gradient(to bottom, #1a0509 0%, #4a0e1f 28%, #7a1a2e 58%, #5a1228 70%, #2d0712 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(20,4,10,0.85) 35%, #0a0205 100%)',
    sun: '#FF7A4D', sunBright: '#FFE0C0', glow: 'rgba(255,122,77,0.55)',
    page: 'linear-gradient(to bottom, #0d0308 0%, #1c0912 45%, #0f040a 100%)',
    band: 'linear-gradient(to bottom, #160710 0%, #2d0b1a 55%, #1a0509 100%)' },
  { key: 'ocean', label: '深蓝',
    bg: 'linear-gradient(to bottom, #030814 0%, #0a1830 28%, #143a6b 58%, #0e2a52 70%, #06101f 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(3,8,20,0.85) 35%, #020610 100%)',
    sun: '#5BB8FF', sunBright: '#D6EBFF', glow: 'rgba(91,184,255,0.55)',
    page: 'linear-gradient(to bottom, #02050f 0%, #071226 45%, #030814 100%)',
    band: 'linear-gradient(to bottom, #02050f 0%, #0a1c38 55%, #030814 100%)' },
  { key: 'carbon', label: '纯黑',
    bg: 'linear-gradient(to bottom, #050505 0%, #1a1a1a 28%, #2e2e2e 58%, #222222 70%, #0a0a0a 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(5,5,5,0.85) 35%, #000000 100%)',
    sun: '#E8E8E8', sunBright: '#FFFFFF', glow: 'rgba(232,232,232,0.45)',
    page: 'linear-gradient(to bottom, #060606 0%, #161616 45%, #050505 100%)',
    band: 'linear-gradient(to bottom, #0a0a0a 0%, #232323 55%, #050505 100%)' },
  { key: 'violet', label: '暗紫',
    bg: 'linear-gradient(to bottom, #0a0218 0%, #1e0a3c 28%, #3d1a6b 58%, #2a1252 70%, #120420 100%)',
    earth: 'linear-gradient(to bottom, transparent 0%, rgba(10,2,24,0.85) 35%, #06010f 100%)',
    sun: '#B07AFF', sunBright: '#E8D0FF', glow: 'rgba(176,122,255,0.55)',
    page: 'linear-gradient(to bottom, #070113 0%, #180b30 45%, #0a0218 100%)',
    band: 'linear-gradient(to bottom, #080114 0%, #20103f 55%, #0a0218 100%)' },
]

/** 取主题（未知 key 回落 ocean，同详情页约定） */
export function getStageTheme(key?: string | null): StageTheme {
  return STAGE_THEMES.find(t => t.key === key) || STAGE_THEMES[1]
}
