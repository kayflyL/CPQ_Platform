/**
 * 外墙/露台/天花收边/灯光。（R3a 自 Office3DCanvas 抽出，逻辑逐行等价）
 * 原 SFC 模块级 environment 全局改为 parent 参数由调用方传入；
 * 门洞查询（officeWallDoorGap）读 zones 配置，留在 SFC 壳层。
 */
import * as THREE from 'three'
import type { OfficeEnvironmentTheme } from '@/api/office'
import { envMaterial } from './materials.ts'

export function createWindowedBackWall(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number) {
  const group = new THREE.Group()
  const wallColor = theme.palette?.wall || '#222e42'
  const lowerColor = theme.palette?.wall_lower || '#1a2434'
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xbfe2f5,
    roughness: 0.1,
    metalness: 0.08,
    envMapIntensity: 0.5,
    transparent: true,
    opacity: 0.3,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const frameMat = envMaterial(lowerColor, 0.5, 0.2)
  const z = -depth / 2
  const sillH = 0.42
  const glassTop = height - 0.5
  const glassH = glassTop - sillH
  const sill = new THREE.Mesh(new THREE.BoxGeometry(width, sillH, thickness), envMaterial(wallColor, 0.8, 0.06))
  sill.position.set(0, sillH / 2, z)
  sill.receiveShadow = true
  group.add(sill)
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(width - 0.2, glassH), glassMat)
  glass.position.set(0, sillH + glassH / 2, z + thickness / 2 + 0.02)
  group.add(glass)
  const bays = Math.max(2, Math.round(width / 4))
  const bayW = width / bays
  for (let i = 0; i <= bays; i += 1) {
    const mullion = new THREE.Mesh(new THREE.BoxGeometry(0.1, glassH, 0.12), frameMat)
    mullion.position.set(-width / 2 + i * bayW, sillH + glassH / 2, z + thickness / 2 + 0.03)
    group.add(mullion)
  }
  const header = new THREE.Mesh(new THREE.BoxGeometry(width, 0.16, 0.14), frameMat)
  header.position.set(0, glassTop + 0.06, z + thickness / 2 + 0.03)
  group.add(header)
  const base = new THREE.Mesh(new THREE.BoxGeometry(width, 0.06, 0.14), frameMat)
  base.position.set(0, sillH + 0.02, z + thickness / 2 + 0.03)
  group.add(base)
  return group
}

export function createSideWall(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number, side: number, doorGap?: { center: number; width: number }) {
  const group = new THREE.Group()
  const wallColor = theme.palette?.wall || '#222e42'
  const lowerColor = theme.palette?.wall_lower || '#1a2434'
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xbfe2f5,
    roughness: 0.1,
    metalness: 0.08,
    envMapIntensity: 0.5,
    transparent: true,
    opacity: 0.3,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  const frameMat = envMaterial(lowerColor, 0.5, 0.2)
  const x = side * width / 2
  const sillH = 0.42
  const glassTop = height - 0.5
  const glassH = glassTop - sillH
  const segments: Array<[number, number]> = []
  if (!doorGap) {
    segments.push([-depth / 2, depth / 2])
  } else {
    const gs = doorGap.center - doorGap.width / 2
    const ge = doorGap.center + doorGap.width / 2
    if (gs > -depth / 2) segments.push([-depth / 2, gs])
    if (ge < depth / 2) segments.push([ge, depth / 2])
  }
  for (const [fromZ, toZ] of segments) {
    const len = toZ - fromZ
    if (len <= 0.1) continue
    const cz = (fromZ + toZ) / 2
    const sill = new THREE.Mesh(new THREE.BoxGeometry(thickness, sillH, len), envMaterial(wallColor, 0.8, 0.06))
    sill.position.set(x, sillH / 2, cz)
    group.add(sill)
    const glass = new THREE.Mesh(new THREE.PlaneGeometry(len - 0.2, glassH), glassMat)
    glass.rotation.y = Math.PI / 2
    glass.position.set(x + side * (thickness / 2 + 0.02), sillH + glassH / 2, cz)
    group.add(glass)
    const bays = Math.max(1, Math.round(len / 4))
    const bayW = len / bays
    for (let i = 0; i <= bays; i += 1) {
      const mullion = new THREE.Mesh(new THREE.BoxGeometry(0.12, glassH, 0.1), frameMat)
      mullion.position.set(x + side * (thickness / 2 + 0.03), sillH + glassH / 2, fromZ + i * bayW)
      group.add(mullion)
    }
    const header = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.16, len), frameMat)
    header.position.set(x + side * (thickness / 2 + 0.03), glassTop + 0.06, cz)
    group.add(header)
    const base = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.06, len), frameMat)
    base.position.set(x + side * (thickness / 2 + 0.03), sillH + 0.02, cz)
    group.add(base)
  }
  return group
}
export function buildTerrace(theme: OfficeEnvironmentTheme, width: number, depth: number, parent: THREE.Group | null) {
  if (!parent) return
  const env = parent
  const margin = 1.4
  const tw = width + margin * 2
  const td = depth + margin * 2
  const terraceMat = envMaterial(theme.palette?.floor || '#b9a488', 0.85, 0.04)
  const terrace = new THREE.Mesh(new THREE.PlaneGeometry(tw, td), terraceMat)
  terrace.rotation.x = -Math.PI / 2
  terrace.position.y = -0.02
  terrace.receiveShadow = true
  env.add(terrace)
  const railMat = envMaterial(theme.palette?.wall_lower || '#8a9bb0', 0.4, 0.35)
  const railH = 1.05
  const postGap = 2.2
  const addRail = (cx: number, cz: number, len: number, horizontal: boolean) => {
    const top = new THREE.Mesh(new THREE.BoxGeometry(horizontal ? len : 0.08, 0.08, horizontal ? 0.08 : len), railMat)
    top.position.set(cx, railH, cz)
    env.add(top)
    const mid = new THREE.Mesh(new THREE.BoxGeometry(horizontal ? len : 0.05, 0.05, horizontal ? 0.05 : len), railMat)
    mid.position.set(cx, railH * 0.55, cz)
    env.add(mid)
    const count = Math.max(1, Math.round(len / postGap))
    for (let i = 0; i <= count; i += 1) {
      const t = i / count
      const px = horizontal ? cx - len / 2 + t * len : cx
      const pz = horizontal ? cz : cz - len / 2 + t * len
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.08, railH, 0.08), railMat)
      post.position.set(px, railH / 2, pz)
      env.add(post)
    }
  }
  addRail(0, -td / 2, tw, true)
  addRail(0, td / 2, tw, true)
  addRail(-tw / 2, 0, td, false)
  addRail(tw / 2, 0, td, false)
}

export function buildCeilingEdges(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, thickness: number, parent: THREE.Group | null) {
  if (!parent) return
  const ceilingColor = theme.palette?.ceiling || '#0d1320'
  const edgeMat = envMaterial(ceilingColor, 0.75, 0.08)
  const edgeHeight = 0.14
  const edgeDepth = 0.24

  const back = new THREE.Mesh(new THREE.BoxGeometry(width + thickness * 2, edgeHeight, edgeDepth), edgeMat)
  back.position.set(0, height - edgeHeight / 2, -depth / 2)
  parent.add(back)

  const front = new THREE.Mesh(new THREE.BoxGeometry(width + thickness * 2, edgeHeight, edgeDepth), edgeMat)
  front.position.set(0, height - edgeHeight / 2, depth / 2)
  parent.add(front)

  for (const side of [-1, 1]) {
    const edge = new THREE.Mesh(new THREE.BoxGeometry(edgeDepth, edgeHeight, depth + thickness * 2), edgeMat)
    edge.position.set(side * width / 2, height - edgeHeight / 2, 0)
    parent.add(edge)
  }
}

/** 玻璃幕墙转角立柱（H 适配）：三面玻璃在四角是对拼裸边，四根方柱收边，
 *  同时给顶部收边框一个"有东西撑着"的结构感。 */
export function buildWallColumns(theme: OfficeEnvironmentTheme, width: number, depth: number, height: number, parent: THREE.Group | null) {
  if (!parent) return
  const colMat = envMaterial(theme.palette?.wall_lower || '#1a2434', 0.5, 0.2)
  const s = 0.16
  for (const [x, z] of [[-width / 2, -depth / 2], [width / 2, -depth / 2], [-width / 2, depth / 2], [width / 2, depth / 2]]) {
    const col = new THREE.Mesh(new THREE.BoxGeometry(s, height, s), colMat)
    col.position.set(x, height / 2, z)
    col.castShadow = true
    col.receiveShadow = true
    parent.add(col)
  }
}

export function buildLighting(theme: OfficeEnvironmentTheme, width: number, depth: number, _height: number, parent: THREE.Group | null) {
  if (!parent) return
  const skyColor = theme.palette?.ceiling || '#d8e4f2'
  const groundColor = theme.palette?.floor || '#111722'

  // 穿窗阳光 rig：环境光砍到主光的零头，方向对比全交给一束从后墙落地窗进来的
  // 暖阳（低仰角出长影）。theme.lighting 的强度配置（daylight 预设 ambient 0.95
  // 比主光还高）会把影子冲没，已随三渲二一起退役，不再读取。
  const hemi = new THREE.HemisphereLight(skyColor, groundColor, 0.22)
  hemi.name = 'office-hemi'
  parent.add(hemi)
  parent.add(new THREE.AmbientLight(0xffffff, 0.10))

  const sun = new THREE.DirectionalLight(0xffe2b8, 3.2)
  sun.name = 'office-sun'
  sun.position.set(-7, 10, -13)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  sun.shadow.camera.near = 1
  sun.shadow.camera.far = 40
  sun.shadow.camera.left = -22
  sun.shadow.camera.right = 22
  sun.shadow.camera.top = 22
  sun.shadow.camera.bottom = -22
  sun.shadow.bias = -0.0002
  sun.shadow.normalBias = 0.02
  sun.shadow.radius = 3
  parent.add(sun)

  const fillLight = new THREE.DirectionalLight(0xcfe0ff, 0.25)
  fillLight.position.set(6, 4, 6)
  parent.add(fillLight)

  if (theme.props?.windows !== false) {
    const windowLight = new THREE.PointLight(0x9fd4ff, 0.8, Math.max(width, depth) * 1.2, 2)
    windowLight.position.set(0, 2.3, -depth / 2 + 0.5)
    windowLight.name = 'office-window-light'
    parent.add(windowLight)
  }
}

/** 日照滑块（G4）：按小时(6~20)重摆太阳——方位角随时刻扫过、正午最高、晨昏偏暖压强度。
 *  参照 floorplan-3d applyLight 移植；宽度参数随办公室尺寸缩放太阳半径。 */
export function applySunlight(parent: THREE.Group | null, hour: number, width: number, depth: number): void {
  if (!parent) return
  const sun = parent.getObjectByName('office-sun') as THREE.DirectionalLight | null
  if (!sun) return
  const t = Math.min(1, Math.max(0, (hour - 6) / 14))
  const az = Math.PI * (0.15 + t * 0.7)
  const el = Math.sin(Math.PI * t) * 1.05 + 0.15
  const warm = 1 - Math.sin(Math.PI * t)
  const r = Math.max(width, depth) * 1.15
  sun.position.set(Math.cos(az) * r * 0.55, Math.sin(el) * r * 0.72 + 3, -Math.sin(az) * r * 0.42 - r * 0.25)
  sun.color.setHSL(0.09, 0.5 + warm * 0.4, 0.92 - warm * 0.12)
  sun.intensity = 1.6 + Math.sin(Math.PI * t) * 1.6
  const hemi = parent.getObjectByName('office-hemi') as THREE.HemisphereLight | null
  if (hemi) hemi.intensity = 0.16 + Math.sin(Math.PI * t) * 0.1
  const win = parent.getObjectByName('office-window-light') as THREE.PointLight | null
  if (win) win.intensity = 0.45 + Math.sin(Math.PI * t) * 0.5
}
