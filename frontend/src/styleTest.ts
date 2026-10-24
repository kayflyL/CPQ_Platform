/**
 * PBR vs 三渲二 分屏对比（临时验证页，不进路由，不改任何线上代码）。
 * 访问：npm run dev 后打开 /style-test.html
 * 左半 = 现状 PBR（MeshStandardMaterial 原样），右半 = 三渲二试验
 * （MeshToonMaterial + 4 级渐变带 + 反向外壳描边）。
 * 同一场景、同一相机、同一光源，每帧 scissor 两半各渲一次；拖动 / 自动旋转时两半天然同步。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { buildFloor } from './office3d/environment/floor.ts'
import {
  createWindowedBackWall,
  createSideWall,
  buildTerrace,
  buildCeilingEdges,
  buildLighting,
} from './office3d/environment/walls.ts'
import { buildProps } from './office3d/environment/furniture.ts'
import { loadCharacterAsset } from './office3d/assets/gltfCache.ts'
import { measurePrecise } from './office3d/assets/measureBox.ts'
// 只允许 import type：值导入 ./api/office 会把 API 模块拉进运行时（别名/依赖链下会挂）。
import type { OfficeEnvironmentTheme, OfficeFurnitureItem } from './api/office'

// ---------------------------------------------------------------------------
// 场景参数（与线上 Office3DCanvas 同构：24 x 16 米，墙高 3.25，墙厚 0.28）
// ---------------------------------------------------------------------------
const W = 24
const D = 16
const H = 3.25
const T = 0.28

const theme: OfficeEnvironmentTheme = {
  preset: 'daylight',
  palette: {
    floor: '#d8c5a3',
    wall: '#eef2f5',
    wall_lower: '#dce4e9',
    accent: '#0ea5e9',
    ceiling: '#f7f9fb',
    furniture: '#6f5238',
    furniture_light: '#8a6b4e',
    foliage: '#4a9d6c',
  },
  props: {
    plants: true,
    bookshelves: true,
    lounge: true,
    coffee_bar: true,
    whiteboard: true,
    windows: true,
    art: true,
    ceiling_lights: false,
  },
  lighting: {
    ambient_intensity: 0.95,
    key_intensity: 1.3,
    fill_intensity: 0.6,
    window_glow: 1.15,
  },
}

/** 家具清单（与线上 officeFurniture() 生成的默认布局同构）。 */
function makeFurnitureList(): OfficeFurnitureItem[] {
  const list: OfficeFurnitureItem[] = []
  for (let row = 0; row <= 1; row += 1) {
    for (let col = 0; col <= 3; col += 1) {
      list.push({
        id: `desk-r${row}c${col}`,
        type: 'desk',
        position: { x: -6 + col * 4, z: -2.2 + row * 4 },
        rotation_y: 0,
      })
    }
  }
  for (let i = 0; i < 8; i += 1) {
    list.push({
      id: `meeting-chair-${i}`,
      type: 'meeting_chair',
      position: { x: 8 + (i % 4) * 1.6, z: (Math.floor(i / 4) - 0.5) * 2.2 },
      rotation_y: Math.PI,
    })
  }
  list.push({ id: 'meeting-table', type: 'meeting_table', position: { x: 8, z: 0 }, rotation_y: 0 })
  const plantSpots: Array<[number, number]> = [
    [-10.5, -6.5], [10.5, -6.5], [-10.5, 6.5], [10.5, 6.5],
  ]
  for (const [px, pz] of plantSpots) {
    list.push({ id: `plant-${px}-${pz}`, type: 'plant', position: { x: px, z: pz }, rotation_y: 0 })
  }
  list.push({ id: 'bookshelf-a', type: 'bookshelf', position: { x: -11.4, z: -2.6 }, rotation_y: 0 })
  list.push({ id: 'bookshelf-b', type: 'bookshelf', position: { x: -11.4, z: 2.6 }, rotation_y: 0 })
  list.push({ id: 'coffee-bar', type: 'coffee_bar', position: { x: 11, z: 3.1 }, rotation_y: 0 })
  list.push({ id: 'lounge-sofa', type: 'lounge_sofa', position: { x: 9.7, z: -4.2 }, rotation_y: 0 })
  list.push({ id: 'whiteboard', type: 'whiteboard', position: { x: -11.84, z: -2.1 }, rotation_y: Math.PI / 2 })
  list.push({ id: 'art-a', type: 'art', position: { x: 11.84, z: -1.2 }, rotation_y: -Math.PI / 2 })
  list.push({ id: 'art-b', type: 'art', position: { x: 11.84, z: 1.6 }, rotation_y: -Math.PI / 2 })
  list.push({ id: 'reception-desk', type: 'reception_desk', position: { x: 0, z: 6.5 }, rotation_y: 0 })
  return list
}

// ---------------------------------------------------------------------------
// 渲染器 / 场景 / 相机
// ---------------------------------------------------------------------------
const stage = document.getElementById('stage') as HTMLDivElement | null
const container = stage || document.body

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
renderer.setClearColor(0x000000, 0)
renderer.outputColorSpace = THREE.SRGBColorSpace
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 1.05
renderer.shadowMap.enabled = true
renderer.shadowMap.type = THREE.PCFSoftShadowMap
renderer.shadowMap.autoUpdate = true
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
renderer.setScissorTest(true)

let viewW = window.innerWidth
let viewH = window.innerHeight
renderer.setSize(viewW, viewH)
container.appendChild(renderer.domElement)

const scene = new THREE.Scene()

const camera = new THREE.PerspectiveCamera(42, viewW / viewH, 0.1, 140)
camera.position.set(6.72, 13, 24)

const controls = new OrbitControls(camera, renderer.domElement)
controls.target.set(4.32, 0.6, 0)
controls.enableDamping = true
controls.autoRotate = true
controls.autoRotateSpeed = 0.5
controls.update()

// ---------------------------------------------------------------------------
// 环境搭建（走线上抽出的真实模块，不做几何合并——本页与性能无关）
// ---------------------------------------------------------------------------
const envGroup = new THREE.Group()
envGroup.name = 'style-test-env'
scene.add(envGroup)

buildFloor(theme, W, D, envGroup)
envGroup.add(createWindowedBackWall(theme, W, D, H, T))
envGroup.add(createSideWall(theme, W, D, H, T, -1))
envGroup.add(createSideWall(theme, W, D, H, T, 1))
buildTerrace(theme, W, D, envGroup)
buildCeilingEdges(theme, W, D, H, T, envGroup)
buildLighting(theme, W, D, H, envGroup)
buildProps(theme, W, D, H, envGroup, makeFurnitureList(), undefined)

// 灯光引用：三渲二需要配套硬光（压环境光、抬主光，色阶才可读），PBR 侧保持原光照。
const lightRig: { hemi: THREE.HemisphereLight | null; ambient: THREE.AmbientLight | null; dir: THREE.DirectionalLight[]; point: THREE.PointLight[] } = { hemi: null, ambient: null, dir: [], point: [] }
const lightBase = new Map<THREE.Light, number>()
envGroup.traverse((obj) => {
  const l = obj as THREE.Light
  if ((l as THREE.HemisphereLight).isHemisphereLight) lightRig.hemi = l as THREE.HemisphereLight
  else if ((l as THREE.AmbientLight).isAmbientLight) lightRig.ambient = l as THREE.AmbientLight
  else if ((l as THREE.DirectionalLight).isDirectionalLight) lightRig.dir.push(l as THREE.DirectionalLight)
  else if ((l as THREE.PointLight).isPointLight) lightRig.point.push(l as THREE.PointLight)
})
for (const l of [lightRig.hemi, lightRig.ambient, ...lightRig.dir, ...lightRig.point]) {
  if (l) lightBase.set(l, l.intensity)
}
let toonLighting = true
const keyLight = lightRig.dir[0] || null
const keyBasePos = keyLight ? keyLight.position.clone() : null
/** 三渲二侧的主光构图：侧低位长影，给色阶"大块影子"。 */
const KEY_TOON_POS = new THREE.Vector3(-14, 11, 3)
function applyLighting(mode: 'pbr' | 'toon'): void {
  const mul = mode === 'toon' ? { hemi: 0.35, ambient: 0.28, dir: 2.2, point: 0.7 } : { hemi: 1, ambient: 1, dir: 1, point: 1 }
  if (lightRig.hemi && lightBase.has(lightRig.hemi)) lightRig.hemi.intensity = lightBase.get(lightRig.hemi)! * mul.hemi
  if (lightRig.ambient && lightBase.has(lightRig.ambient)) lightRig.ambient.intensity = lightBase.get(lightRig.ambient)! * mul.ambient
  for (const d of lightRig.dir) {
    if (!lightBase.has(d)) continue
    d.intensity = lightBase.get(d)! * mul.dir
    if (keyBasePos) d.position.copy(mode === 'toon' ? KEY_TOON_POS : keyBasePos)
  }
  for (const p of lightRig.point) { if (lightBase.has(p)) p.intensity = lightBase.get(p)! * mul.point }
}

// ---------------------------------------------------------------------------
// 角色（走线上 loadCharacterAsset：自动分派 VRM/GLB、烘焙 idle/walk/sit）
// ---------------------------------------------------------------------------
const CHARACTER_URLS = [
  '/models/ai-colleagues/vrm/sample-girl.vrm',
  '/models/ai-colleagues/custom/meshy-girl.glb',
  '/models/ai-colleagues/kenney-mini/character-male-a.glb',
]
const CHARACTER_X = [-1.6, 0, 1.6]
const TARGET_HEIGHT = 1.42
const mixers: THREE.AnimationMixer[] = []

async function loadCharacters(): Promise<void> {
  for (let i = 0; i < CHARACTER_URLS.length; i += 1) {
    try {
      const asset = await loadCharacterAsset(CHARACTER_URLS[i])
      const model = asset.scene
      const scale = TARGET_HEIGHT / (asset.height || 2.5)
      model.scale.setScalar(scale)
      model.rotation.y = asset.frontRotation || 0
      // 二次校正：precise 实测（逐顶点世界坐标，含蒙皮）回对齐到目标身高，钳制防退化。
      try {
        const realHeight = measurePrecise(model).height
        if (realHeight > 0.05) {
          model.scale.multiplyScalar(THREE.MathUtils.clamp(TARGET_HEIGHT / realHeight, 0.1, 10))
        }
      } catch (e) {
        console.warn('[styleTest] 角色身高实测失败，沿用默认缩放:', e)
      }
      model.position.set(CHARACTER_X[i], 0, 3)
      model.userData.roleKey = 'demo'
      model.traverse((obj) => {
        const mesh = obj as THREE.Mesh
        if (mesh.isMesh) mesh.castShadow = true
      })
      scene.add(model)

      const idle = asset.animations.find((clip) => (clip.name || '').toLowerCase() === 'idle')
      if (idle) {
        const mixer = new THREE.AnimationMixer(model)
        mixer.clipAction(idle).play()
        mixer.update(0.5)
        mixers.push(mixer)
      }
    } catch (e) {
      console.warn(`[styleTest] 角色加载失败，跳过: ${CHARACTER_URLS[i]}`, e)
    }
  }
  // 角色全部落位后再统一构建双风格系统（全场景遍历一次）。
  buildStyleSystems()
}

loadCharacters().catch((e) => console.error('[styleTest] 角色加载流程失败:', e))

// ---------------------------------------------------------------------------
// 双风格系统：PBR / 三渲二孪生材质 + 反向外壳描边
// ---------------------------------------------------------------------------
// 三渲二明暗渐变带：4 级色阶（暗→亮），NearestFilter 保持硬边色阶。
// 冷调阴影色阶（RGBA 逐通道）：暗部偏蓝紫——赛璐璐的阴影是"设计过的颜色"，不是单纯变暗。
// gradientMap 以乘法作用于受光结果，暗阶带冷色即得到色相偏移的阴影。
const RAMP = new THREE.DataTexture(new Uint8Array([
  118, 126, 180, 255,
  170, 178, 216, 255,
  224, 226, 240, 255,
  255, 255, 255, 255,
]), 4, 1, THREE.RGBAFormat)
RAMP.magFilter = THREE.NearestFilter
RAMP.minFilter = THREE.NearestFilter
RAMP.generateMipmaps = false
RAMP.needsUpdate = true

const styleMeshes: THREE.Mesh[] = []
const hulls: THREE.Mesh[] = []
let hullsVisible = true

/** 由 PBR 材质构建三渲二孪生（颜色/贴图/透明参数照抄，光照响应换成 toon 色阶）。 */
function makeToonTwin(src: THREE.MeshStandardMaterial): THREE.MeshToonMaterial {
  return new THREE.MeshToonMaterial({
    color: src.color.clone(),
    map: src.map || null,
    gradientMap: RAMP,
    transparent: src.transparent,
    opacity: src.opacity,
    side: src.side,
    depthWrite: src.depthWrite,
    alphaTest: src.alphaTest,
    emissive: src.emissive.clone(),
    emissiveIntensity: src.emissiveIntensity,
  })
}

/** 判定 mesh 是否属于角色树（角色描边偏移更小）。 */
function inCharacterTree(obj: THREE.Object3D): boolean {
  let cur: THREE.Object3D | null = obj
  while (cur) {
    if (cur.userData && cur.userData.roleKey === 'demo') return true
    cur = cur.parent
  }
  return false
}

/** 反向外壳描边：geometry 沿 normal 膨胀 offset，BackSide 深色壳。 */
function buildHull(mesh: THREE.Mesh, offset: number): void {
  try {
    if (mesh.userData.monitor === true) return
    if (mesh.userData.styleHull === true) return
    if (mesh.castShadow !== true) return
    const mat = mesh.material as THREE.Material | THREE.Material[]
    if (Array.isArray(mat) || mat.transparent) return
    const geo = mesh.geometry
    if (!geo || !geo.attributes || !geo.attributes.normal) return

    const hullGeo = geo.clone()
    const pos = hullGeo.attributes.position as THREE.BufferAttribute
    const nor = hullGeo.attributes.normal as THREE.BufferAttribute
    for (let i = 0; i < pos.count; i += 1) {
      pos.setXYZ(
        i,
        pos.getX(i) + nor.getX(i) * offset,
        pos.getY(i) + nor.getY(i) * offset,
        pos.getZ(i) + nor.getZ(i) * offset,
      )
    }
    pos.needsUpdate = true

    const hullMat = new THREE.MeshBasicMaterial({ color: 0x2a2f3a, side: THREE.BackSide })
    let hull: THREE.Mesh
    if ((mesh as THREE.SkinnedMesh).isSkinnedMesh) {
      // 蒙皮网格：外壳也做成 SkinnedMesh 绑同一骨架，跟随 idle 动画一起动。
      const src = mesh as THREE.SkinnedMesh
      const skinned = new THREE.SkinnedMesh(hullGeo, hullMat)
      skinned.bind(src.skeleton, src.bindMatrix)
      hull = skinned
    } else {
      hull = new THREE.Mesh(hullGeo, hullMat)
    }
    hull.userData.styleHull = true
    hull.name = `${mesh.name || 'mesh'}-style-hull`
    hull.castShadow = false
    hull.receiveShadow = false
    const parent = mesh.parent || scene
    parent.add(hull)
    hull.position.copy(mesh.position)
    hull.quaternion.copy(mesh.quaternion)
    hull.scale.copy(mesh.scale)
    hull.visible = false
    hulls.push(hull)
  } catch (e) {
    console.warn('[styleTest] 描边外壳构建失败，跳过该 mesh:', e)
  }
}

/** 角色落位后调用：全场景遍历，收集孪生材质与描边外壳。 */
function buildStyleSystems(): void {
  const hullCandidates: THREE.Mesh[] = []
  scene.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    if (!mesh.isMesh) return
    const mat = mesh.material as THREE.Material | THREE.Material[]
    if (Array.isArray(mat)) {
      // 数组材质线上未使用，保底两侧同材质。
      mesh.userData.pbrMat = mat
      mesh.userData.toonMat = mat
      if (mesh.castShadow === true) hullCandidates.push(mesh)
      return
    }
    const std = mat as THREE.MeshStandardMaterial
    if (std.isMeshStandardMaterial === true && (std as unknown as { isMToonMaterial?: boolean }).isMToonMaterial !== true) {
      // 普通 PBR：建三渲二孪生。
      mesh.userData.pbrMat = std
      mesh.userData.toonMat = makeToonTwin(std)
      styleMeshes.push(mesh)
    } else {
      // MToon（VRM，本身就是三渲二）或非标准材质（Line/Basic 等）：两侧同材质。
      mesh.userData.pbrMat = mat
      mesh.userData.toonMat = mat
    }
    if (mesh.castShadow === true) hullCandidates.push(mesh)
  })
  for (const mesh of hullCandidates) {
    buildHull(mesh, inCharacterTree(mesh) ? 0.014 : 0.02)
  }
}

// ---------------------------------------------------------------------------
// 分屏渲染：左 PBR / 右三渲二，每帧各渲一次
// ---------------------------------------------------------------------------
function renderBothHalves(): void {
  const halfW = Math.floor(viewW / 2)
  // 左半：PBR + 无描边 + 原光照
  applyLighting('pbr')
  for (const mesh of styleMeshes) mesh.material = mesh.userData.pbrMat as THREE.Material
  for (const hull of hulls) hull.visible = false
  renderer.setScissor(0, 0, halfW, viewH)
  renderer.setViewport(0, 0, halfW, viewH)
  renderer.render(scene, camera)
  // 右半：三渲二 + 描边开关 + （可选）三渲二专用硬光
  applyLighting(toonLighting ? 'toon' : 'pbr')
  for (const mesh of styleMeshes) mesh.material = mesh.userData.toonMat as THREE.Material
  for (const hull of hulls) hull.visible = hullsVisible
  renderer.setScissor(halfW, 0, viewW - halfW, viewH)
  renderer.setViewport(halfW, 0, viewW - halfW, viewH)
  renderer.render(scene, camera)
}

const clock = new THREE.Clock()
function tick(): void {
  requestAnimationFrame(tick)
  const delta = clock.getDelta()
  controls.update()
  for (const mixer of mixers) mixer.update(delta)
  renderBothHalves()
}
tick()

window.addEventListener('resize', () => {
  viewW = window.innerWidth
  viewH = window.innerHeight
  camera.aspect = viewW / viewH
  camera.updateProjectionMatrix()
  renderer.setSize(viewW, viewH)
})

// ---------------------------------------------------------------------------
// UI 控制条
// ---------------------------------------------------------------------------
const btnOutline = document.getElementById('btn-outline') as HTMLButtonElement | null
if (btnOutline) {
  btnOutline.addEventListener('click', () => {
    hullsVisible = !hullsVisible
    btnOutline.textContent = hullsVisible ? '描边 开' : '描边 关'
  })
}
const btnToonLight = document.getElementById('btn-toonlight') as HTMLButtonElement | null
if (btnToonLight) {
  btnToonLight.addEventListener('click', () => {
    toonLighting = !toonLighting
    btnToonLight.textContent = toonLighting ? '三渲二专用光 开' : '三渲二专用光 关'
  })
}
const btnRotate = document.getElementById('btn-rotate') as HTMLButtonElement | null
if (btnRotate) {
  btnRotate.addEventListener('click', () => {
    controls.autoRotate = !controls.autoRotate
    btnRotate.textContent = controls.autoRotate ? '暂停旋转' : '恢复旋转'
  })
}

// ---------------------------------------------------------------------------
// 隐藏面板：自动化验证入口（renderOnce 同步渲两半，不依赖 rAF）
// ---------------------------------------------------------------------------
;(window as unknown as Record<string, unknown>).__STYLE__ = {
  renderer,
  scene,
  camera,
  renderOnce: () => {
    renderBothHalves()
  },
  get styleMeshCount(): number {
    return styleMeshes.length
  },
  get hullCount(): number {
    return hulls.length
  },
}
