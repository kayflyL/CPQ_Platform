/**
 * 程序化家具/陈设/接待台/办公桌。（R3b 自 Office3DCanvas 抽出，逻辑逐行等价）
 * 原 SFC 模块级 environment 全局默认值改为显式 parent 参数；
 * 配置读取（officeFurniture）留在 SFC 壳层，经 buildProps 参数注入。
 */
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import type { OfficeEnvironmentTheme, OfficeFurnitureItem } from '@/api/office'
import { envMaterial, applyShadow } from './materials.ts'
import { furnitureSize, FALLBACK_FURNITURE_SIZE, type FurnitureCatalog } from './furnitureSize.ts'
import { DESK_CHAIR_OFFSET } from '../characters/metrics.ts'
import { buildFurniture } from '../../views/office/furnitureSpec.ts'

export function addPlant(x: number, z: number, theme: OfficeEnvironmentTheme, parent: THREE.Group | null) {
  const group = buildFurniture('plant', theme)
  if (!group) return group
  group.position.set(x, 0, z)
  if (parent) parent.add(group)
  return group
}

export function addBookshelf(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY: number | undefined, parent: THREE.Group | null) {
  const group = new THREE.Group()
  const frameMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.55, 0.12)
  const bookColors = [0x1677ff, 0xff9f43, 0x2f7d54, 0xd74c5e, 0x7b61ff, 0x37b6c7]
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2.1, 0.5), frameMat)
  body.position.y = 1.05
  body.castShadow = true
  body.receiveShadow = true
  group.add(body)

  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 7; col += 1) {
      const height = 0.36 + ((row * 13 + col) % 3) * 0.035
      const book = new THREE.Mesh(
        new THREE.BoxGeometry(0.12, height, 0.28),
        new THREE.MeshStandardMaterial({ color: bookColors[(row + col) % bookColors.length], roughness: 0.72, metalness: 0.02 }),
      )
      book.position.set(-0.52 + col * 0.17, 0.24 + row * 0.48 + height / 2, 0)
      group.add(book)
    }
  }

  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x < 0 ? 0 : Math.PI)
  if (parent) parent.add(group)
  return group
}

export function addCoffeeBar(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY: number | undefined, parent: THREE.Group | null) {
  const group = new THREE.Group()
  const counterMat = envMaterial(theme.palette?.furniture || '#26344a', 0.52, 0.16)
  const topMat = envMaterial(theme.palette?.furniture_light || '#34455f', 0.4, 0.2)
  const counter = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.95, 0.62), counterMat)
  counter.position.y = 0.475
  counter.castShadow = true
  counter.receiveShadow = true
  group.add(counter)

  const top = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.06, 0.72), topMat)
  top.position.y = 0.98
  top.castShadow = true
  top.receiveShadow = true
  group.add(top)

  const machine = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.5, 0.3), envMaterial('#1d2530', 0.42, 0.28))
  machine.position.set(-0.3, 1.24, 0)
  machine.castShadow = true
  group.add(machine)

  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.26, 14), envMaterial('#d6cfc0', 0.5, 0.22))
  pot.position.set(0.2, 1.12, 0)
  group.add(pot)

  for (const mx of [-0.18, 0.02, 0.22]) {
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.035, 0.09, 12), envMaterial('#e5e9f0', 0.6, 0.05))
    mug.position.set(mx + 0.25, 1.06, -0.18)
    group.add(mug)
  }

  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x > 0 ? -Math.PI / 2 : Math.PI / 2)
  if (parent) parent.add(group)
  return group
}

export function addLounge(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY: number | undefined, parent: THREE.Group | null) {
  const group = buildFurniture('lounge_sofa', theme)
  if (!group) return group
  group.position.set(x, 0, z)
  group.rotation.y = rotationY ?? (x > 0 ? -Math.PI / 2 : Math.PI / 2)
  if (parent) parent.add(group)
  return group
}

export function addWhiteboard(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0, parent: THREE.Group | null) {
  const group = buildFurniture('whiteboard', theme)
  if (!group) return group
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}

export function addArt(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY: number, color: string, parent: THREE.Group | null) {
  const group = buildFurniture('art', theme, color)
  if (!group) return group
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}

export function addMeetingTable(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0, parent: THREE.Group | null) {
  const group = new THREE.Group()
  const top = envMaterial(theme.palette?.furniture || '#7a5c3d', 0.42, 0.16)
  const leg = envMaterial('#3a3f47', 0.42, 0.5)
  const length = 4.0
  const width = 1.2
  const thick = 0.1
  const height = 0.72
  const rect = new THREE.Mesh(new THREE.BoxGeometry(length - width, thick, width), top)
  rect.position.y = height
  rect.castShadow = true
  rect.receiveShadow = true
  group.add(rect)
  for (const sx of [-1, 1]) {
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(width / 2, width / 2, thick, 24), top)
    cap.position.set(sx * (length - width) / 2, height, 0)
    cap.castShadow = true
    group.add(cap)
  }
  for (const sx of [-1, 1]) {
    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.12, height, width * 0.72), leg)
    legs.position.set(sx * (length / 2 - 0.5), height / 2, 0)
    legs.castShadow = true
    group.add(legs)
  }
  const beam = new THREE.Mesh(new THREE.BoxGeometry(length - width, 0.08, 0.1), leg)
  beam.position.set(0, height - 0.3, 0)
  group.add(beam)
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}


const receptionLogoCache = new Map<string, THREE.CanvasTexture>()
export function makeReceptionLogo(text: string): THREE.CanvasTexture {
  let tex = receptionLogoCache.get(text)
  if (tex) return tex
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 160
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.font = '700 96px "Segoe UI", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#1b2736'
    ctx.fillText(text, canvas.width / 2, canvas.height / 2)
  }
  tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.minFilter = THREE.LinearFilter
  tex.anisotropy = 2
  receptionLogoCache.set(text, tex)
  return tex
}

export function addReceptionDesk(x: number, z: number, theme: OfficeEnvironmentTheme, rotationY = 0, parent: THREE.Group | null) {
  const group = new THREE.Group()
  const woodMat = deskWoodMat(theme)
  const darkMat = deskDarkMat()
  const bodyMat = envMaterial(theme.palette?.furniture || '#3a4763', 0.7, 0.08)
  const logoPlateMat = envMaterial('#eef1f5', 0.55, 0.05)
  const screenMat = new THREE.MeshStandardMaterial({ color: 0x0a1a2b, roughness: 0.25, metalness: 0.42, emissive: 0x14293f, emissiveIntensity: 0.5 })
  const logoMat = new THREE.MeshStandardMaterial({ map: makeReceptionLogo('KayFly'), transparent: true, depthWrite: false, roughness: 0.5 })

  // 员工侧高台（后侧 -z）：接待员坐后面工作
  const staffBody = new THREE.Mesh(new RoundedBoxGeometry(2.2, 0.94, 0.55, 2, 0.02), bodyMat)
  staffBody.position.set(0, 0.47, -0.18)
  applyShadow(staffBody)
  group.add(staffBody)
  const staffTop = new THREE.Mesh(new RoundedBoxGeometry(2.26, 0.05, 0.58, 2, 0.015), woodMat)
  staffTop.position.set(0, 0.965, -0.17)
  applyShadow(staffTop)
  group.add(staffTop)

  // 顾客侧矮台（前侧 +z）：访客趴着签到/咨询
  const guestBody = new THREE.Mesh(new RoundedBoxGeometry(2.2, 0.6, 0.36, 2, 0.02), bodyMat)
  guestBody.position.set(0, 0.33, 0.27)
  applyShadow(guestBody)
  group.add(guestBody)
  const guestTop = new THREE.Mesh(new RoundedBoxGeometry(2.26, 0.045, 0.4, 2, 0.015), woodMat)
  guestTop.position.set(0, 0.663, 0.25)
  applyShadow(guestTop)
  group.add(guestTop)

  // 端头侧板
  const sidePanel = new THREE.Mesh(new RoundedBoxGeometry(0.06, 0.95, 0.9, 2, 0.015), bodyMat)
  sidePanel.position.set(1.07, 0.475, 0)
  applyShadow(sidePanel)
  group.add(sidePanel)

  // 正面 Logo 板 + KayFly 公司名
  const logoPlate = new THREE.Mesh(new RoundedBoxGeometry(1.5, 0.26, 0.02, 2, 0.008), logoPlateMat)
  logoPlate.position.set(0, 0.4, 0.44)
  group.add(logoPlate)
  const logo = new THREE.Mesh(new THREE.PlaneGeometry(1.35, 0.18), logoMat)
  logo.position.set(0, 0.4, 0.46)
  group.add(logo)

  // 员工台面小显示器（面向员工 -z）
  const monitorGroup = new THREE.Group()
  const mBase = new THREE.Mesh(new RoundedBoxGeometry(0.2, 0.03, 0.14, 1, 0.01), darkMat)
  mBase.position.y = 0.015
  monitorGroup.add(mBase)
  const mNeck = new THREE.Mesh(new RoundedBoxGeometry(0.05, 0.14, 0.05, 1, 0.01), darkMat)
  mNeck.position.set(0, 0.11, 0)
  monitorGroup.add(mNeck)
  const mPanel = new THREE.Mesh(new RoundedBoxGeometry(0.56, 0.35, 0.012, 2, 0.008), darkMat)
  mPanel.position.set(0, 0.34, 0.03)
  mPanel.castShadow = true
  monitorGroup.add(mPanel)
  const mScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.52, 0.31), screenMat)
  mScreen.position.set(0, 0.34, 0.037)
  monitorGroup.add(mScreen)
  monitorGroup.position.set(-0.55, 1.0, -0.18)
  monitorGroup.rotation.y = Math.PI
  group.add(monitorGroup)

  // 台灯
  const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.03, 12), darkMat)
  lampBase.position.set(-0.92, 1.01, -0.15)
  group.add(lampBase)
  const lampArm = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.2, 8), darkMat)
  lampArm.rotation.z = -0.5
  lampArm.position.set(-0.92, 1.1, -0.15)
  group.add(lampArm)
  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.08, 10), new THREE.MeshStandardMaterial({ color: 0xffd166, emissive: 0xffb347, emissiveIntensity: 0.4, roughness: 0.5 }))
  lampHead.rotation.z = Math.PI / 2
  lampHead.position.set(-0.87, 1.17, -0.15)
  group.add(lampHead)

  // 电话 / 名牌 / 笔筒 / 绿植
  const phone = new THREE.Mesh(new RoundedBoxGeometry(0.16, 0.04, 0.12, 1, 0.012), darkMat)
  phone.position.set(0.12, 1.01, -0.28)
  group.add(phone)
  const plate = new THREE.Mesh(new RoundedBoxGeometry(0.3, 0.05, 0.035, 1, 0.01), logoPlateMat)
  plate.position.set(0.4, 1.01, -0.1)
  group.add(plate)
  const penPot = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.03, 0.09, 8), darkMat)
  penPot.position.set(-0.2, 1.045, -0.1)
  group.add(penPot)
  const pen = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.12, 6), envMaterial('#e05a4e', 0.5, 0.1))
  pen.position.set(-0.2, 1.1, -0.1)
  group.add(pen)
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.055, 0.12, 10), darkMat)
  pot.position.set(0.85, 1.05, -0.18)
  group.add(pot)
  const foliage = new THREE.Mesh(new THREE.IcosahedronGeometry(0.11, 0), envMaterial(theme.palette?.foliage || '#2f7d54', 0.7, 0.02))
  foliage.position.set(0.85, 1.2, -0.18)
  foliage.castShadow = true
  group.add(foliage)

  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  if (parent) parent.add(group)
  return group
}

export function addFurnitureItem(item: OfficeFurnitureItem, theme: OfficeEnvironmentTheme, parent: THREE.Group | null, catalog: FurnitureCatalog) {
  const x = item.position?.x ?? 0
  const z = item.position?.z ?? 0
  const rotationY = item.rotation_y ?? 0
  const accentColor = theme.palette?.accent || '#1677ff'
  let group: THREE.Group | null = null

  switch (item.type) {
    case 'desk':
      group = createDesk(accentColor, theme).group
      break
    case 'office_chair':
      group = buildFurniture(item.type, theme)
      break
    case 'meeting_chair':
      group = buildFurniture(item.type, theme)
      break
    case 'meeting_table':
      group = addMeetingTable(x, z, theme, rotationY, parent)
      break
    case 'plant':
      group = buildFurniture('plant', theme)
      break
    case 'bookshelf':
      group = addBookshelf(x, z, theme, rotationY, parent)
      break
    case 'coffee_bar':
      group = addCoffeeBar(x, z, theme, rotationY, parent)
      break
    case 'lounge_sofa':
      group = buildFurniture('lounge_sofa', theme)
      break
    case 'whiteboard':
      group = buildFurniture('whiteboard', theme)
      break
    case 'art':
      group = buildFurniture('art', theme, accentColor)
      break
    case 'rug':
      group = buildFurniture('rug', theme)
      break
    case 'partition':
      group = buildFurniture('partition', theme)
      break
    case 'fridge':
      group = buildFurniture('fridge', theme)
      break
    case 'coffee_table':
      group = buildFurniture('coffee_table', theme)
      break
    case 'round_table':
      group = buildFurniture('round_table', theme)
      break
    case 'stool':
      group = buildFurniture('stool', theme)
      break
    case 'reception_desk':
      group = addReceptionDesk(x, z, theme, rotationY, parent)
      break
    case 'coat_rack':
      group = buildFurniture('coat_rack', theme)
      break
    case 'tv':
      group = buildFurniture('tv', theme)
      break
    case 'file_cabinet':
      group = buildFurniture('file_cabinet', theme)
      break

    default:
      break
  }

  if (!group) return null
  // 单一数据源：渲染尺寸跟随 catalog / 单件 width-depth（相对设计基底等比缩放，保持外观）。
  const size = furnitureSize(catalog, item.type, item)
  const base = FALLBACK_FURNITURE_SIZE[item.type]
  if (base && base.width > 0 && base.depth > 0) {
    group.scale.set(size.width / base.width, 1, size.depth / base.depth)
  }
  group.position.set(x, 0, z)
  group.rotation.y = rotationY
  group.name = `furniture-${item.id}`
  group.userData.edit = { kind: 'furniture', item, id: item.id }
  parent?.add(group)
  return group
}
export function buildProps(theme: OfficeEnvironmentTheme, width: number, depth: number, _height: number, parent: THREE.Group | null, configuredFurniture: OfficeFurnitureItem[], catalog: FurnitureCatalog) {
  if (!parent) return

  if (configuredFurniture.length) {
    const props = theme.props || {}
    const enabledByType: Record<string, boolean> = {
      plant: props.plants !== false,
      bookshelf: props.bookshelves !== false,
      coffee_bar: props.coffee_bar !== false,
      lounge_sofa: props.lounge !== false,
      whiteboard: props.whiteboard !== false,
      art: props.art !== false,
    }
    for (const item of configuredFurniture) {
      if (enabledByType[item.type] === false) continue
      addFurnitureItem(item, theme, parent, catalog)
    }
    return
  }

  const props = theme.props || {}
  const foliageColor = theme.palette?.foliage || '#2f7d54'
  const accentColor = theme.palette?.accent || '#1677ff'

  if (props.plants !== false) {
    addPlant(-width / 2 + 0.85, -depth / 2 + 1.05, theme, parent)
    addPlant(width / 2 - 0.85, -depth / 2 + 1.05, theme, parent)
    addPlant(-width / 2 + 0.85, depth / 2 - 1.05, theme, parent)
    addPlant(width / 2 - 0.85, depth / 2 - 1.05, theme, parent)
  }

  if (props.bookshelves !== false) {
    addBookshelf(-width / 2 + 0.8, -2.6, theme, undefined, parent)
    addBookshelf(-width / 2 + 0.8, 2.6, theme, undefined, parent)
  }

  if (props.coffee_bar !== false) {
    addCoffeeBar(width / 2 - 1.0, 3.1, theme, undefined, parent)
  }

  if (props.lounge !== false) {
    addLounge(width / 2 - 2.3, -4.2, theme, undefined, parent)
  }

  if (props.whiteboard !== false) {
    addWhiteboard(-width / 2 + 0.16, -2.1, theme, Math.PI / 2, parent)
  }

  if (props.art !== false) {
    addArt(width / 2 - 0.16, -1.2, theme, -Math.PI / 2, accentColor, parent)
    addArt(width / 2 - 0.16, 1.6, theme, -Math.PI / 2, foliageColor, parent)
  }
}
const deskMatCache = new Map<string, THREE.MeshStandardMaterial>()
export function deskSharedMat(key: string, make: () => THREE.MeshStandardMaterial): THREE.MeshStandardMaterial {
  let m = deskMatCache.get(key)
  if (!m) {
    m = make()
    deskMatCache.set(key, m)
  }
  return m
}

export function createDeskWoodTexture(baseColor: string): THREE.CanvasTexture {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.fillStyle = baseColor
    ctx.fillRect(0, 0, size, size)
    for (let i = 0; i < 24; i += 1) {
      const y = (i * 17 + 7) % size
      ctx.strokeStyle = i % 2 ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.06)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.bezierCurveTo(size * 0.3, y + 3, size * 0.6, y - 3, size, y)
      ctx.stroke()
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.anisotropy = 2
  return texture
}

export function deskWoodMat(theme: OfficeEnvironmentTheme): THREE.MeshStandardMaterial {
  const base = theme.palette?.floor || '#9a7b56'
  return deskSharedMat(`wood|${base}`, () => new THREE.MeshStandardMaterial({ color: 0xffffff, map: createDeskWoodTexture(base), roughness: 0.55, metalness: 0.02 }))
}

export function deskMetalMat(theme: OfficeEnvironmentTheme): THREE.MeshStandardMaterial {
  const c = theme.palette?.furniture_light || '#34455f'
  return deskSharedMat(`metal|${c}`, () => envMaterial(c, 0.34, 0.66))
}

export function deskDarkMat(): THREE.MeshStandardMaterial {
  return deskSharedMat('dark', () => envMaterial('#151c28', 0.5, 0.34))
}

export function createDesk(color: string, theme: OfficeEnvironmentTheme): { group: THREE.Group; monitorMat: THREE.MeshStandardMaterial } {
  const group = new THREE.Group()

  const woodMat = deskWoodMat(theme)
  const metalMat = deskMetalMat(theme)
  const darkMat = deskDarkMat()
  const accentMat = envMaterial(color, 0.34, 0.2)
  const monitorMat = new THREE.MeshStandardMaterial({
    color: 0x0a101c, roughness: 0.28, metalness: 0.42,
    emissive: 0x05080f, emissiveIntensity: 0.25,
  })
  // 屏幕与面板共面，靠 polygonOffset 让屏幕深度优先，避免 z-fight 黑块/悬空
  monitorMat.polygonOffset = true
  monitorMat.polygonOffsetFactor = -2
  monitorMat.polygonOffsetUnits = -2

  // 桌面：圆角木板 + 程序化木纹
  const top = new THREE.Mesh(new RoundedBoxGeometry(1.78, 0.07, 0.98, 2, 0.02), woodMat)
  top.position.y = 0.7
  applyShadow(top)
  group.add(top)

  // 桌下横撑
  const apron = new THREE.Mesh(new RoundedBoxGeometry(1.7, 0.1, 0.86, 1, 0.015), darkMat)
  apron.position.y = 0.62
  group.add(apron)

  // 金属侧板腿
  for (const sx of [-0.8, 0.8]) {
    const panel = new THREE.Mesh(new RoundedBoxGeometry(0.07, 0.6, 0.8, 1, 0.015), metalMat)
    panel.position.set(sx, 0.31, 0)
    applyShadow(panel)
    group.add(panel)
  }

  // 后挡板
  const modesty = new THREE.Mesh(new RoundedBoxGeometry(1.5, 0.34, 0.05, 1, 0.012), darkMat)
  modesty.position.set(0, 0.46, -0.34)
  group.add(modesty)

  // 显示器：玻璃屏 + 支架底座（monitorMat 每张桌独立以支持开/关屏）
  // 底座/支架放在屏幕背后（更靠 -z），避免顶到屏幕
  const monitorBase = new THREE.Mesh(new RoundedBoxGeometry(0.26, 0.035, 0.18, 1, 0.01), darkMat)
  monitorBase.position.set(0, 0.755, -0.3)
  group.add(monitorBase)
  // 支架：底座 + 短颈接到面板背面，比例收敛
  const monitorNeck = new THREE.Mesh(new RoundedBoxGeometry(0.06, 0.16, 0.06, 1, 0.01), darkMat)
  monitorNeck.position.set(0, 0.86, -0.29)
  monitorNeck.castShadow = true
  group.add(monitorNeck)
  // 面板：薄圆角板（0.014 厚）；屏幕用平面贴在前表面，靠 polygonOffset 叠前，无厚度就不会从背面/侧面穿出
  const monitorPanel = new THREE.Mesh(new RoundedBoxGeometry(0.72, 0.44, 0.014, 2, 0.01), darkMat)
  monitorPanel.position.set(0, 1.16, -0.26)
  monitorPanel.castShadow = true
  // 面板与屏幕都算「显示器」命中面：只认屏幕薄膜的话，点边框会退化成普通选中
  monitorPanel.userData.monitor = true
  group.add(monitorPanel)
  const monitorScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.42), monitorMat)
  monitorScreen.position.set(0, 1.16, -0.253)
  monitorScreen.userData.monitor = true
  group.add(monitorScreen)

  const keyboard = new THREE.Mesh(new RoundedBoxGeometry(0.5, 0.035, 0.19, 1, 0.01), darkMat)
  keyboard.position.set(-0.05, 0.75, 0.3)
  keyboard.receiveShadow = true
  group.add(keyboard)
  // 键帽区（用暗色调，不再用亮色贴条）
  const keycapBase = new THREE.Mesh(new RoundedBoxGeometry(0.44, 0.02, 0.15, 1, 0.006), envMaterial('#2a3a4d', 0.6, 0.1))
  keycapBase.position.set(-0.05, 0.77, 0.3)
  group.add(keycapBase)
  const spaceBar = new THREE.Mesh(new RoundedBoxGeometry(0.24, 0.018, 0.05, 1, 0.005), envMaterial('#394a5f', 0.55, 0.12))
  spaceBar.position.set(-0.05, 0.773, 0.34)
  group.add(spaceBar)
  const mouse = new THREE.Mesh(new RoundedBoxGeometry(0.07, 0.035, 0.12, 2, 0.015), darkMat)
  mouse.position.set(0.4, 0.768, 0.32)
  mouse.rotation.y = -0.2
  group.add(mouse)

  const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, 0.03, 14), metalMat)
  lampBase.position.set(-0.66, 0.755, -0.05)
  group.add(lampBase)
  const lampArm1 = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 0.24, 8), metalMat)
  lampArm1.rotation.z = -0.5
  lampArm1.position.set(-0.66, 0.86, -0.05)
  group.add(lampArm1)
  const lampArm2 = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.2, 8), metalMat)
  lampArm2.rotation.z = 0.9
  lampArm2.position.set(-0.62, 0.98, -0.05)
  group.add(lampArm2)
  const lampHead = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.09, 12), new THREE.MeshStandardMaterial({ color: 0xffd166, emissive: 0xffb347, emissiveIntensity: 0.45, roughness: 0.5 }))
  lampHead.rotation.z = Math.PI / 2
  lampHead.position.set(-0.58, 1.04, -0.05)
  group.add(lampHead)

  const plantPot = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.16, 10), metalMat)
  plantPot.position.set(0.72, 0.815, 0.26)
  group.add(plantPot)
  const plantBall = new THREE.Mesh(new THREE.IcosahedronGeometry(0.13, 0), envMaterial(theme.palette?.foliage || '#2f7d54', 0.7, 0.02))
  plantBall.position.set(0.72, 1.0, 0.26)
  plantBall.castShadow = true
  group.add(plantBall)

  const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.034, 0.08, 10), envMaterial('#e5e9f0', 0.5, 0.05))
  mug.position.set(-0.42, 0.775, 0.3)
  group.add(mug)

  const nameplate = new THREE.Mesh(new RoundedBoxGeometry(0.3, 0.06, 0.035, 1, 0.01), accentMat)
  nameplate.position.set(0.28, 0.765, 0.42)
  group.add(nameplate)

  const chair = new THREE.Group()
  const chairFabric = envMaterial(theme.palette?.furniture_light || '#34455f', 0.74, 0.05)
  const chairDark = envMaterial('#111822', 0.5, 0.28)

  // 五星脚 + 轮子：每条撑杆沿半径方向辐射，轮子在杆端
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.07, 0.06, 12), chairDark)
  hub.position.y = 0.05
  hub.castShadow = true
  chair.add(hub)
  for (let i = 0; i < 5; i += 1) {
    const angle = (i / 5) * Math.PI * 2 + Math.PI / 2
    const pivot = new THREE.Group()
    pivot.position.set(0, 0.05, 0)
    pivot.rotation.y = Math.PI / 2 - angle
    chair.add(pivot)
    const arm = new THREE.Mesh(new RoundedBoxGeometry(0.045, 0.045, 0.42, 1, 0.012), chairDark)
    arm.position.z = 0.2
    arm.castShadow = true
    pivot.add(arm)
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.03, 10), chairDark)
    wheel.rotation.z = Math.PI / 2
    wheel.position.set(0, 0, 0.4)
    pivot.add(wheel)
  }
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.045, 0.38, 12), chairDark)
  pole.position.y = 0.27
  pole.castShadow = true
  chair.add(pole)
  // 座垫顶面 ~0.53，保持入座高度不变
  const seat = new THREE.Mesh(new RoundedBoxGeometry(0.52, 0.11, 0.5, 2, 0.035), chairFabric)
  seat.position.y = 0.475
  seat.castShadow = true
  chair.add(seat)
  const back = new THREE.Mesh(new RoundedBoxGeometry(0.5, 0.58, 0.12, 2, 0.035), chairFabric)
  back.position.set(0, 0.82, -0.24)
  back.rotation.x = -0.1
  back.castShadow = true
  chair.add(back)
  for (const sx of [-0.28, 0.28]) {
    const armSupport = new THREE.Mesh(new RoundedBoxGeometry(0.05, 0.16, 0.06, 1, 0.012), chairDark)
    armSupport.position.set(sx, 0.56, 0.02)
    armSupport.castShadow = true
    chair.add(armSupport)
    const armPad = new THREE.Mesh(new RoundedBoxGeometry(0.08, 0.05, 0.3, 2, 0.02), chairDark)
    armPad.position.set(sx, 0.65, 0.02)
    armPad.castShadow = true
    chair.add(armPad)
  }
  chair.position.set(0, 0, DESK_CHAIR_OFFSET)
  chair.rotation.y = Math.PI
  group.add(chair)

  return { group, monitorMat }
}
