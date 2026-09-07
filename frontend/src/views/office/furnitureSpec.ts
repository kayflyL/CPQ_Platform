import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import type { OfficeEnvironmentTheme } from '@/api/office'

export type FurnGeo = 'box' | 'roundedbox' | 'cylinder' | 'plane' | 'icosahedron' | 'sphere'

export type MaterialRole =
  | 'wood'
  | 'light'
  | 'metal'
  | 'frame'
  | 'wheel'
  | 'dark'
  | 'leather'
  | 'cushion'
  | 'screen'
  | 'accent'
  | 'foliage'

type Vec3 = [number, number, number]
type Vec2or3 = [number, number] | [number, number, number]

/** 个别部件的非主题材质覆盖：字面量颜色/发光/透明度等。角色表仍负责主题默认色。 */
export interface FurnMatOverride {
  color?: string
  roughness?: number
  metalness?: number
  emissive?: string
  emissiveIntensity?: number
  transparent?: boolean
  opacity?: number
  side?: THREE.Side
  depthWrite?: boolean
}

export interface FurnPart {
  geo: FurnGeo
  pos: Vec3
  rot?: Vec3
  size: Vec2or3
  mat: MaterialRole
  matOverride?: FurnMatOverride
  segments?: number
  rounded?: { radius?: number; segments?: number }
  loop?: { count: number; radius: number; phase?: number; rotate?: boolean }
  castShadow?: boolean
  receiveShadow?: boolean
  instanceColor?: boolean
}

export interface FurnitureSpec {
  category: string
  base: { width: number; depth: number; height: number }
  parts: FurnPart[]
  dynamic?: string
}

const FURN_ROLE_STYLE: Record<MaterialRole, { color: (theme: OfficeEnvironmentTheme) => string; roughness: number; metalness: number }> = {
  wood: { color: (t) => t.palette?.furniture ?? '#7a5c3d', roughness: 0.55, metalness: 0.16 },
  light: { color: (t) => t.palette?.furniture_light ?? '#34455f', roughness: 0.5, metalness: 0.14 },
  metal: { color: () => '#3a3f47', roughness: 0.34, metalness: 0.66 },
  frame: { color: () => '#2a2e35', roughness: 0.32, metalness: 0.72 },
  wheel: { color: () => '#15181d', roughness: 0.5, metalness: 0.5 },
  dark: { color: () => '#151c28', roughness: 0.5, metalness: 0.34 },
  leather: { color: (t) => t.palette?.furniture_light ?? '#23272e', roughness: 0.52, metalness: 0.08 },
  cushion: { color: (t) => t.palette?.furniture_light ?? '#31363d', roughness: 0.62, metalness: 0.05 },
  screen: { color: () => '#0a101c', roughness: 0.28, metalness: 0.42 },
  accent: { color: (t) => t.palette?.accent ?? '#1677ff', roughness: 0.34, metalness: 0.2 },
  foliage: { color: (t) => t.palette?.foliage ?? '#2f7d54', roughness: 0.78, metalness: 0.02 },
}

const specMatCache = new Map<string, THREE.MeshStandardMaterial>()

function specMat(role: MaterialRole, theme: OfficeEnvironmentTheme, override?: FurnMatOverride): THREE.MeshStandardMaterial {
  const style = FURN_ROLE_STYLE[role]
  const color = override?.color ?? style.color(theme)
  const key = `${role}|${color}|${JSON.stringify(override)}`
  let m = specMatCache.get(key)
  if (!m) {
    const params: THREE.MeshStandardMaterialParameters = {
      color: new THREE.Color(color),
      roughness: override?.roughness ?? style.roughness,
      metalness: override?.metalness ?? style.metalness,
    }
    if (override?.emissive) params.emissive = new THREE.Color(override.emissive)
    if (override?.emissiveIntensity !== undefined) params.emissiveIntensity = override.emissiveIntensity
    if (override?.transparent !== undefined) params.transparent = override.transparent
    if (override?.opacity !== undefined) params.opacity = override.opacity
    if (override?.side !== undefined) params.side = override.side
    if (override?.depthWrite !== undefined) params.depthWrite = override.depthWrite
    m = new THREE.MeshStandardMaterial(params)
    specMatCache.set(key, m)
  }
  return m
}

function geoFor(p: FurnPart): THREE.BufferGeometry {
  const a = p.size[0]
  const b = p.size[1]
  const c = p.size[2]
  switch (p.geo) {
    case 'box':
      return new THREE.BoxGeometry(a, b, c ?? 1)
    case 'roundedbox':
      return new RoundedBoxGeometry(a, b, c ?? 1, p.rounded?.segments ?? 2, p.rounded?.radius ?? Math.min(a, b, c ?? 1) / 6)
    case 'cylinder':
      return new THREE.CylinderGeometry(a, b, c ?? 1, p.segments ?? 12)
    case 'plane':
      return new THREE.PlaneGeometry(a, b)
    case 'icosahedron':
      return new THREE.IcosahedronGeometry(a, b ?? 0)
    case 'sphere':
      return new THREE.SphereGeometry(a, b ?? 12, c ?? 8)
  }
}

function placePart(mesh: THREE.Mesh, p: FurnPart): void {
  mesh.position.set(p.pos[0], p.pos[1], p.pos[2])
  if (p.rot) mesh.rotation.set(p.rot[0], p.rot[1], p.rot[2])
  mesh.castShadow = p.castShadow ?? false
  mesh.receiveShadow = p.receiveShadow ?? p.castShadow ?? false
}

function buildPart(p: FurnPart, theme: OfficeEnvironmentTheme, colorOverride?: string): THREE.Object3D {
  const mat = specMat(p.mat, theme, p.instanceColor && colorOverride ? { ...p.matOverride, color: colorOverride } : p.matOverride)
  const geo = geoFor(p)
  if (!p.loop) {
    const mesh = new THREE.Mesh(geo, mat)
    placePart(mesh, p)
    return mesh
  }
  const wrap = new THREE.Group()
  const { count, radius, phase = 0, rotate = true } = p.loop
  for (let i = 0; i < count; i += 1) {
    const angle = phase + (i / count) * Math.PI * 2
    const holder = new THREE.Group()
    holder.position.set(Math.sin(angle) * radius, 0, Math.cos(angle) * radius)
    if (rotate) holder.rotation.y = angle
    const mesh = new THREE.Mesh(geo, mat)
    placePart(mesh, p)
    holder.add(mesh)
    wrap.add(holder)
  }
  return wrap
}

const ergoChairParts: FurnPart[] = [
  { geo: 'cylinder', pos: [0, 0.045, 0], size: [0.06, 0.07, 0.05], segments: 12, mat: 'frame', castShadow: true },
  { geo: 'box', pos: [0, 0.045, 0], size: [0.05, 0.04, 0.27], mat: 'frame', loop: { count: 5, radius: 0.135, phase: Math.PI / 10 }, castShadow: true },
  { geo: 'cylinder', pos: [0, 0.032, 0], size: [0.032, 0.032, 0.026], segments: 10, rot: [0, 0, Math.PI / 2], mat: 'wheel', loop: { count: 5, radius: 0.27, phase: Math.PI / 10, rotate: true }, castShadow: true },
  { geo: 'cylinder', pos: [0, 0.32, 0], size: [0.032, 0.04, 0.34], segments: 12, mat: 'frame' },
  { geo: 'roundedbox', pos: [0, 0.5, 0], size: [0.5, 0.12, 0.47], rounded: { radius: 0.03, segments: 2 }, mat: 'leather', castShadow: true },
  { geo: 'roundedbox', pos: [0, 0.78, -0.22], size: [0.46, 0.34, 0.1], rot: [-0.06, 0, 0], rounded: { radius: 0.03, segments: 2 }, mat: 'leather', castShadow: true },
  { geo: 'roundedbox', pos: [0, 1.04, -0.25], size: [0.4, 0.28, 0.09], rot: [-0.1, 0, 0], rounded: { radius: 0.03, segments: 2 }, mat: 'leather', castShadow: true },
  { geo: 'roundedbox', pos: [0, 0.82, -0.28], size: [0.05, 0.6, 0.06], rounded: { radius: 0.012, segments: 1 }, mat: 'frame' },
  { geo: 'roundedbox', pos: [-0.27, 0.6, -0.02], size: [0.045, 0.22, 0.05], rounded: { radius: 0.012, segments: 1 }, mat: 'frame' },
  { geo: 'roundedbox', pos: [-0.27, 0.68, -0.02], size: [0.07, 0.05, 0.3], rounded: { radius: 0.015, segments: 2 }, mat: 'cushion', castShadow: true },
  { geo: 'roundedbox', pos: [0.27, 0.6, -0.02], size: [0.045, 0.22, 0.05], rounded: { radius: 0.012, segments: 1 }, mat: 'frame' },
  { geo: 'roundedbox', pos: [0.27, 0.68, -0.02], size: [0.07, 0.05, 0.3], rounded: { radius: 0.015, segments: 2 }, mat: 'cushion', castShadow: true },
]

const whiteboardParts: FurnPart[] = [
  { geo: 'box', pos: [0, 1.5, 0], size: [2.1, 1.25, 0.08], mat: 'light', matOverride: { metalness: 0.16 }, castShadow: true, receiveShadow: false },
  { geo: 'plane', pos: [0, 1.5, 0.05], size: [1.94, 1.09], mat: 'light', matOverride: { color: '#f4f7fb', roughness: 0.35, metalness: 0.02, emissive: '#11161f', emissiveIntensity: 0.05 } },
]

const rugParts: FurnPart[] = [
  { geo: 'box', pos: [0, 0.012, 0], size: [2.4, 0.02, 1.8], mat: 'accent', matOverride: { roughness: 0.96, metalness: 0.01 }, receiveShadow: true },
  { geo: 'box', pos: [0, 0.014, 0], size: [2.0, 0.025, 1.4], mat: 'light', matOverride: { color: '#f4f1ea', roughness: 0.96, metalness: 0.01 }, receiveShadow: true },
]

const coffeeTableParts: FurnPart[] = [
  { geo: 'cylinder', pos: [0, 0.42, 0], size: [0.42, 0.42, 0.07], segments: 20, mat: 'wood', matOverride: { roughness: 0.4, metalness: 0.18 }, castShadow: true, receiveShadow: true },
  { geo: 'box', pos: [0, 0.21, 0], size: [0.06, 0.42, 0.06], mat: 'light', matOverride: { roughness: 0.55, metalness: 0.22 }, loop: { count: 3, radius: 0.3 }, castShadow: true, receiveShadow: false },
]

const roundTableParts: FurnPart[] = [
  { geo: 'cylinder', pos: [0, 0.72, 0], size: [0.62, 0.62, 0.08], segments: 24, mat: 'wood', matOverride: { roughness: 0.42, metalness: 0.2 }, castShadow: true, receiveShadow: true },
  { geo: 'cylinder', pos: [0, 0.36, 0], size: [0.11, 0.11, 0.66], segments: 14, mat: 'light', matOverride: { roughness: 0.55, metalness: 0.22 }, castShadow: true, receiveShadow: false },
  { geo: 'cylinder', pos: [0, 0.03, 0], size: [0.4, 0.46, 0.06], segments: 14, mat: 'light', matOverride: { roughness: 0.55, metalness: 0.22 }, receiveShadow: true },
]

const plantParts: FurnPart[] = [
  { geo: 'cylinder', pos: [0, 0.21, 0], size: [0.22, 0.18, 0.42], segments: 16, mat: 'light', matOverride: { roughness: 0.5, metalness: 0.14 }, castShadow: true, receiveShadow: true },
  { geo: 'cylinder', pos: [0, 0.7, 0], size: [0.035, 0.05, 0.55], segments: 8, mat: 'wood', matOverride: { color: '#6e4f34', roughness: 0.85, metalness: 0.02 } },
  { geo: 'sphere', pos: [0, 1.05, 0], size: [0.34, 12, 10], mat: 'foliage', castShadow: true, receiveShadow: false },
  { geo: 'sphere', pos: [0.12, 1.28, -0.05], size: [0.25, 12, 10], mat: 'foliage', castShadow: true, receiveShadow: false },
]

const loungeSofaParts: FurnPart[] = [
  { geo: 'box', pos: [0, 0.26, 0], size: [2.0, 0.42, 0.9], mat: 'light', matOverride: { roughness: 0.82, metalness: 0.02 }, castShadow: true, receiveShadow: true },
  { geo: 'cylinder', pos: [0, 0.62, -0.35], size: [0.18, 0.18, 2.0], segments: 20, rot: [0, 0, Math.PI / 2], mat: 'light', matOverride: { roughness: 0.82, metalness: 0.02 }, castShadow: true },
  { geo: 'cylinder', pos: [-0.93, 0.42, 0], size: [0.14, 0.14, 0.9], segments: 16, rot: [Math.PI / 2, 0, 0], mat: 'light', matOverride: { roughness: 0.82, metalness: 0.02 }, castShadow: true },
  { geo: 'cylinder', pos: [0.93, 0.42, 0], size: [0.14, 0.14, 0.9], segments: 16, rot: [Math.PI / 2, 0, 0], mat: 'light', matOverride: { roughness: 0.82, metalness: 0.02 }, castShadow: true },
  { geo: 'box', pos: [-0.45, 0.62, -0.12], size: [0.42, 0.4, 0.18], rot: [-0.5, 0, 0], mat: 'accent', matOverride: { roughness: 0.8, metalness: 0.02 }, castShadow: true },
  { geo: 'box', pos: [0.45, 0.62, -0.12], size: [0.42, 0.4, 0.18], rot: [-0.5, 0, 0], mat: 'accent', matOverride: { roughness: 0.8, metalness: 0.02 }, castShadow: true },
  { geo: 'cylinder', pos: [0, 0.38, 0.72], size: [0.34, 0.34, 0.08], segments: 20, mat: 'accent', matOverride: { roughness: 0.35, metalness: 0.2 }, castShadow: true, receiveShadow: true },
]

const partitionParts: FurnPart[] = [
  { geo: 'plane', pos: [0, 0.72, 0], size: [0.86, 1.3], mat: 'light', matOverride: { color: '#d8ecf5', roughness: 0.12, metalness: 0.05, transparent: true, opacity: 0.34, side: THREE.DoubleSide, depthWrite: false }, receiveShadow: true },
  { geo: 'box', pos: [-0.44, 0.73, 0], size: [0.07, 1.42, 0.07], mat: 'light', matOverride: { roughness: 0.45, metalness: 0.25 }, castShadow: true },
  { geo: 'box', pos: [0.44, 0.73, 0], size: [0.07, 1.42, 0.07], mat: 'light', matOverride: { roughness: 0.45, metalness: 0.25 }, castShadow: true },
  { geo: 'box', pos: [0, 1.42, 0], size: [0.98, 0.06, 0.08], mat: 'light', matOverride: { roughness: 0.45, metalness: 0.25 }, castShadow: true },
]

const fridgeParts: FurnPart[] = [
  { geo: 'box', pos: [0, 0.95, 0], size: [0.9, 1.9, 0.9], mat: 'light', matOverride: { color: '#d7dee6', roughness: 0.32, metalness: 0.45 }, castShadow: true, receiveShadow: true },
  { geo: 'box', pos: [0, 1.18, 0], size: [0.9, 0.02, 0.9], mat: 'dark', matOverride: { color: '#20303f', roughness: 0.45, metalness: 0.35 }, receiveShadow: true },
  { geo: 'box', pos: [0.3, 1.5, 0.48], size: [0.04, 0.3, 0.06], mat: 'dark', matOverride: { color: '#20303f', roughness: 0.45, metalness: 0.35 } },
  { geo: 'box', pos: [0.3, 0.82, 0.48], size: [0.04, 0.3, 0.06], mat: 'dark', matOverride: { color: '#20303f', roughness: 0.45, metalness: 0.35 } },
]

const tvParts: FurnPart[] = [
  { geo: 'box', pos: [0, 1.2, 0], size: [1.4, 0.9, 0.08], mat: 'frame', matOverride: { color: '#101820', roughness: 0.45, metalness: 0.4 }, castShadow: true },
  { geo: 'plane', pos: [0, 1.2, 0.045], size: [1.26, 0.76], mat: 'screen', matOverride: { color: '#0c1a2b', roughness: 0.2, metalness: 0.4, emissive: '#1a3b5c', emissiveIntensity: 0.9 } },
  { geo: 'box', pos: [0, 0.5, 0], size: [0.3, 0.5, 0.2], mat: 'frame', matOverride: { color: '#101820', roughness: 0.45, metalness: 0.4 }, castShadow: true },
  { geo: 'box', pos: [0, 0.03, 0], size: [0.6, 0.05, 0.36], mat: 'frame', matOverride: { color: '#101820', roughness: 0.45, metalness: 0.4 } },
]

const stoolParts: FurnPart[] = [
  { geo: 'cylinder', pos: [0, 0.66, 0], size: [0.2, 0.2, 0.08], segments: 18, mat: 'light', matOverride: { roughness: 0.6, metalness: 0.14 }, castShadow: true },
  { geo: 'cylinder', pos: [0.07, 0.32, 0.12124], size: [0.025, 0.025, 0.64], segments: 8, rot: [0.10392, 0, 0.06], mat: 'accent', matOverride: { roughness: 0.5, metalness: 0.28 }, castShadow: true },
  { geo: 'cylinder', pos: [-0.14, 0.32, 0], size: [0.025, 0.025, 0.64], segments: 8, rot: [0, 0, -0.12], mat: 'accent', matOverride: { roughness: 0.5, metalness: 0.28 }, castShadow: true },
  { geo: 'cylinder', pos: [0.07, 0.32, -0.12124], size: [0.025, 0.025, 0.64], segments: 8, rot: [-0.10392, 0, 0.06], mat: 'accent', matOverride: { roughness: 0.5, metalness: 0.28 }, castShadow: true },
]

const coatRackParts: FurnPart[] = [
  { geo: 'cylinder', pos: [0, 0.03, 0], size: [0.28, 0.32, 0.06], segments: 14, mat: 'wood', matOverride: { color: '#6e4f34', roughness: 0.7, metalness: 0.06 }, castShadow: true, receiveShadow: true },
  { geo: 'cylinder', pos: [0, 0.9, 0], size: [0.035, 0.04, 1.7], segments: 10, mat: 'wood', matOverride: { color: '#6e4f34', roughness: 0.7, metalness: 0.06 }, castShadow: true },
  { geo: 'cylinder', pos: [0.13, 1.45, 0], size: [0.014, 0.014, 0.3], segments: 8, rot: [0, 0, Math.PI / 2], mat: 'wood', matOverride: { color: '#6e4f34', roughness: 0.7, metalness: 0.06 } },
  { geo: 'cylinder', pos: [-0.065, 1.45, 0.11258], size: [0.014, 0.014, 0.3], segments: 8, rot: [0, -2 * Math.PI / 3, Math.PI / 2], mat: 'wood', matOverride: { color: '#6e4f34', roughness: 0.7, metalness: 0.06 } },
  { geo: 'cylinder', pos: [-0.065, 1.45, -0.11258], size: [0.014, 0.014, 0.3], segments: 8, rot: [0, -4 * Math.PI / 3, Math.PI / 2], mat: 'wood', matOverride: { color: '#6e4f34', roughness: 0.7, metalness: 0.06 } },
]

const fileCabinetParts: FurnPart[] = [
  { geo: 'box', pos: [0, 0.55, 0], size: [0.6, 1.1, 0.6], mat: 'light', matOverride: { roughness: 0.5, metalness: 0.2 }, castShadow: true, receiveShadow: true },
  { geo: 'box', pos: [0, 0.3, 0.31], size: [0.56, 0.26, 0.03], mat: 'dark', matOverride: { color: '#26344a', roughness: 0.5, metalness: 0.2 } },
  { geo: 'box', pos: [0, 0.3, 0.35], size: [0.24, 0.03, 0.03], mat: 'light', matOverride: { roughness: 0.5, metalness: 0.2 } },
  { geo: 'box', pos: [0, 0.62, 0.31], size: [0.56, 0.26, 0.03], mat: 'dark', matOverride: { color: '#26344a', roughness: 0.5, metalness: 0.2 } },
  { geo: 'box', pos: [0, 0.62, 0.35], size: [0.24, 0.03, 0.03], mat: 'light', matOverride: { roughness: 0.5, metalness: 0.2 } },
  { geo: 'box', pos: [0, 0.94, 0.31], size: [0.56, 0.26, 0.03], mat: 'dark', matOverride: { color: '#26344a', roughness: 0.5, metalness: 0.2 } },
  { geo: 'box', pos: [0, 0.94, 0.35], size: [0.24, 0.03, 0.03], mat: 'light', matOverride: { roughness: 0.5, metalness: 0.2 } },
]

const artParts: FurnPart[] = [
  { geo: 'box', pos: [0, 1.75, 0], size: [0.95, 0.7, 0.06], mat: 'light', matOverride: { metalness: 0.16 } },
  { geo: 'plane', pos: [0, 1.75, 0.04], size: [0.8, 0.55], mat: 'accent', matOverride: { roughness: 0.7, metalness: 0.02 }, instanceColor: true },
]

export const FURNITURE_SPEC: Record<string, FurnitureSpec> = {
  office_chair: { category: 'chair', base: { width: 0.6, depth: 0.6, height: 1.1 }, parts: ergoChairParts },
  meeting_chair: { category: 'chair', base: { width: 0.6, depth: 0.6, height: 1.1 }, parts: ergoChairParts },
  whiteboard: { category: 'meeting', base: { width: 2.1, depth: 0.08, height: 1.25 }, parts: whiteboardParts },
  rug: { category: 'decor', base: { width: 2.4, depth: 1.8, height: 0.02 }, parts: rugParts },
  coffee_table: { category: 'lounge', base: { width: 0.84, depth: 0.84, height: 0.45 }, parts: coffeeTableParts },
  round_table: { category: 'lounge', base: { width: 1.24, depth: 1.24, height: 0.75 }, parts: roundTableParts },
  plant: { category: 'decor', base: { width: 0.68, depth: 0.68, height: 1.4 }, parts: plantParts },
  lounge_sofa: { category: 'lounge', base: { width: 2, depth: 0.9, height: 0.82 }, parts: loungeSofaParts },
  partition: { category: 'office', base: { width: 0.98, depth: 0.08, height: 1.42 }, parts: partitionParts },
  fridge: { category: 'lounge', base: { width: 0.9, depth: 0.9, height: 1.9 }, parts: fridgeParts },
  stool: { category: 'lounge', base: { width: 0.4, depth: 0.4, height: 0.66 }, parts: stoolParts },
  coat_rack: { category: 'office', base: { width: 0.64, depth: 0.64, height: 1.7 }, parts: coatRackParts },
  tv: { category: 'meeting', base: { width: 1.4, depth: 0.12, height: 1.2 }, parts: tvParts },
  file_cabinet: { category: 'office', base: { width: 0.6, depth: 0.6, height: 1.1 }, parts: fileCabinetParts },
  art: { category: 'decor', base: { width: 0.95, depth: 0.06, height: 1.75 }, parts: artParts },
}

export function buildFurniture(type: string, theme: OfficeEnvironmentTheme, colorOverride?: string): THREE.Group | null {
  const spec = FURNITURE_SPEC[type]
  if (!spec) return null
  if (spec.dynamic) return null
  const group = new THREE.Group()
  for (const p of spec.parts) group.add(buildPart(p, theme, colorOverride))
  return group
}
