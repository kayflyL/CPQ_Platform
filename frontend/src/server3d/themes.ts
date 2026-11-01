/**
 * 服务器3D配置台 · 双主题表
 * 配置页可切主题(data-theme),3D场景整表跟随:背景/地台/机箱三材质/主板色/玻璃/灯光/bloom/曝光。
 * 接入方式:页面主题变化时调 applyThemeNames 侧的 setTheme('light'|'dark')。
 */
import * as THREE from 'three'

export interface StageTheme {
  bg: string
  floor: string
  grid1: number
  grid2: number
  body: string
  dark: string
  fin: string
  board: string
  boardDk: string
  glass: string
  glassBase: number
  amb: number
  key: number
  fill: number
  rimC: number
  rimV: number
  bloom: number
  bloomThr: number
  exp: number
}

export const STAGE_THEMES: Record<'dark' | 'light', StageTheme> = {
  dark: {
    bg: '#0a1526', floor: '#0c1930', grid1: 0x22456f, grid2: 0x16304f,
    body: '#2e4059', dark: '#1c2a40', fin: '#3d5378',
    board: '#1f8a4c', boardDk: '#14532d',
    glass: '#9fd4ff', glassBase: 0.1,
    amb: 0.65, key: 2.0, fill: 14, rimC: 7, rimV: 5,
    bloom: 0.85, bloomThr: 0.72, exp: 1.15,
  },
  light: {
    bg: '#e6edf7', floor: '#d7e1ee', grid1: 0xa8bcd8, grid2: 0xc3d2e6,
    body: '#97abc6', dark: '#6a80a0', fin: '#93a7c1',
    board: '#24a45c', boardDk: '#178a48',
    glass: '#4a7fb5', glassBase: 0.07,
    amb: 0.95, key: 1.7, fill: 18, rimC: 2.5, rimV: 2,
    bloom: 0.32, bloomThr: 0.9, exp: 1.0,
  },
}

export function glow(color: string, boost = 1.6): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(boost) })
}
