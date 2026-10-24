/**
 * 三渲二（cel-shading）轻风格化模块 —— ?officeStyle=pbr 时整体关闭，默认开。
 *
 * 模块定位:
 *   在线上渲染管线（Office3DCanvas.buildEnvironment → mergeStaticGroup）之后叠加的风格化层。
 *   mergeStaticGroup 已把静态网格按材质合并成 ~40 个大网格（几何体按世界坐标烘焙、
 *   非索引化、只含 position/normal/uv），并把原始小网格隐藏保留作拾取代理（合并体
 *   raycast 已禁用）。本模块只处理「可见」的 Mesh——visible === false 的是拾取代理，
 *   不参与渲染，所有函数一律跳过，不做任何材质/几何触碰。
 *
 * 与 mergeStaticGroup 的协作关系:
 *   applyToonStyle 必须在 mergeStaticGroup 之后调用。合并体的 geometry 是多个合并体
 *   共享的大几何：描边外壳构建时先 clone 出私有副本再沿法线偏移，绝不原地改动共享
 *   几何；toon 替换是直接换 mesh.material 引用，原 MeshStandardMaterial 对象保留不动。
 *
 * polygonOffset 系必须照抄:
 *   显示器屏幕材质带 polygonOffset（furniture.ts 靠它让屏幕深度优先、避免与面板
 *   z-fight），actorSystem 靠 mat.polygonOffset 识别显示器材质——toon 孪生若丢了这组
 *   参数，屏幕会重新 z-fight，且 actorSystem 识别不到显示器、退化成自建桌 bug。
 */
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

/** URL ?officeStyle=pbr 时整体关闭三渲二（默认开）。每次调用实时读。 */
export function toonStyleEnabled(): boolean {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('officeStyle') !== 'pbr'
}

// ---- toon 材质孪生 ----------------------------------------------------------

/** 冷调阴影 ramp：暗部偏蓝紫——赛璐璐的阴影色是设计过的，不是单纯压暗。模块级单例。 */
let rampSingleton: THREE.DataTexture | null = null

function getRamp(): THREE.DataTexture {
  if (rampSingleton) return rampSingleton
  const tex = new THREE.DataTexture(
    new Uint8Array([
      118, 126, 180, 255,
      170, 178, 216, 255,
      224, 226, 240, 255,
      255, 255, 255, 255,
    ]),
    4,
    1,
    THREE.RGBAFormat,
  )
  tex.magFilter = THREE.NearestFilter
  tex.minFilter = THREE.NearestFilter
  tex.generateMipmaps = false
  tex.needsUpdate = true
  rampSingleton = tex
  return tex
}

// 孪生按原材质 uuid 缓存：同一材质被多个 mesh / 多个角色克隆共享时孪生也共享，避免材质翻倍
const twinCache = new Map<string, THREE.MeshToonMaterial>()

// MToon（VRM）材质本来就是三渲二，无需孪生；该标记 three 类型未声明，运行时判定。
// 调用方（applyToonStyle / toonifyStandardMaterials）已按 !isMToonMaterial 过滤后才进来。
function isMToonMaterial(mat: THREE.Material): boolean {
  return (mat as { isMToonMaterial?: boolean }).isMToonMaterial === true
}

function makeToonTwin(src: THREE.MeshStandardMaterial): THREE.MeshToonMaterial {
  const cached = twinCache.get(src.uuid)
  if (cached) return cached
  const twin = new THREE.MeshToonMaterial({
    color: src.color.clone(),
    map: src.map || null,
    gradientMap: getRamp(),
    transparent: src.transparent,
    opacity: src.opacity,
    side: src.side,
    depthWrite: src.depthWrite,
    alphaTest: src.alphaTest,
    emissive: src.emissive.clone(),
    emissiveIntensity: src.emissiveIntensity,
  })
  // polygonOffset 系必须照抄：actorSystem 靠 mat.polygonOffset 识别显示器材质，
  // 屏幕自身也靠它深度优先防 z-fight——丢了会退化成自建桌 bug
  twin.polygonOffset = src.polygonOffset
  twin.polygonOffsetFactor = src.polygonOffsetFactor
  twin.polygonOffsetUnits = src.polygonOffsetUnits
  twinCache.set(src.uuid, twin)
  return twin
}

// ---- 环境风格化：材质替换 + 描边外壳 ---------------------------------------

/**
 * 对 root 子树做 toon 材质替换（环境用）。返回替换数量。
 * outline 是整棵子树共用的描边外壳（BackSide 放大壳），由调用方决定挂载点，
 * 不 add 进 root——合并体几何已按世界坐标烘焙，外壳沿用同一坐标系，单位变换即可。
 */
export function applyToonStyle(root: THREE.Object3D, outlineWidth = 0.02): { twinCount: number; outline: THREE.Mesh | null } {
  let twinCount = 0
  // 描边外壳候选：可见 + castShadow + 单一不透明材质 + 有法线（含本调用里刚换成 toon 的 mesh）
  const outlineCandidates: THREE.Mesh[] = []

  // 先收集再处理：traverse 过程中只做引用赋值，不增删对象，无遍历失真问题
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    if (mesh.visible === false) return // visible === false 的是拾取代理（mergeStaticGroup 隐藏的原件），不碰
    if (!mesh.isMesh) return
    if ((mesh as THREE.SkinnedMesh).isSkinnedMesh) return // 蒙皮网格顶点逐帧驱动，静态外壳会脱节
    if ((obj as THREE.Sprite).isSprite) return
    const material = mesh.material
    if (Array.isArray(material)) return
    const std = material as THREE.MeshStandardMaterial
    if (std.isMeshStandardMaterial && !isMToonMaterial(std)) {
      // 直接换引用，原 MeshStandardMaterial 对象不动（孪生按 uuid 缓存共享）
      mesh.material = makeToonTwin(std)
      twinCount += 1
    }
    if (!mesh.castShadow) return
    if (material.transparent) return // 透明壳描边会脏（玻璃、屏幕）；孪生的 transparent 与原材质一致
    if (!mesh.geometry.getAttribute('normal')) return
    outlineCandidates.push(mesh)
  })

  // 逐个 clone + 沿法线外扩，单个失败只跳过自己
  const shells: THREE.BufferGeometry[] = []
  for (const mesh of outlineCandidates) {
    try {
      // merged 几何是合并体共享的：必须先 clone 出私有副本再偏移，绝不能原地改共享几何
      let g = mesh.geometry.clone()
      if (g.index) g = g.toNonIndexed()
      const pos = g.getAttribute('position')
      const nor = g.getAttribute('normal')
      for (let i = 0; i < pos.count; i += 1) {
        pos.setXYZ(
          i,
          pos.getX(i) + nor.getX(i) * outlineWidth,
          pos.getY(i) + nor.getY(i) * outlineWidth,
          pos.getZ(i) + nor.getZ(i) * outlineWidth,
        )
      }
      shells.push(g)
    } catch (e) {
      console.warn('[toonStyle] 描边外壳构建失败，已跳过该网格', mesh.name || mesh.uuid, e)
    }
  }
  if (shells.length === 0) return { twinCount, outline: null }

  const merged = mergeGeometries(shells, false)
  if (!merged) {
    console.warn(`[toonStyle] 描边外壳合并失败：${shells.length} 个几何体`)
    return { twinCount, outline: null }
  }
  const outline = new THREE.Mesh(merged, new THREE.MeshBasicMaterial({ color: 0x2a2f3a, side: THREE.BackSide }))
  outline.castShadow = false
  outline.receiveShadow = false
  outline.matrixAutoUpdate = false
  outline.raycast = () => {} // 外壳不参与拾取，拾取语义仍由隐藏原件承担
  outline.name = 'style-outline'
  outline.visible = true
  // 不 add 进 root：调用方决定挂载点
  return { twinCount, outline }
}

// ---- 灯光 rig ---------------------------------------------------------------

// 灯光基准快照：每次 applyToonLightRig 都按「第一次见到的 intensity」乘系数。
// 场景重建会 new 出新灯（新对象记新基准），已见过的灯重复调用不会因反复乘系数而漂移。
const lightBaseIntensity = new WeakMap<THREE.Light, number>()
// 主光基准位置：存下来以便未来需要回退原布光，本次不回退。
const mainLightBasePosition = new WeakMap<THREE.DirectionalLight, THREE.Vector3>()

/**
 * 三渲二专用光：压环境光、抬主光，主光挪侧低位出长影。重复调用安全（基于基准乘系数，不漂移）。
 */
export function applyToonLightRig(root: THREE.Object3D): void {
  // 取基准：第一次见到的灯记下当前 intensity 作为基准，之后一律按基准乘系数
  const baseOf = (light: THREE.Light): number => {
    let base = lightBaseIntensity.get(light)
    if (base === undefined) {
      base = light.intensity
      lightBaseIntensity.set(light, base)
    }
    return base
  }
  let mainLightTaken = false
  root.traverse((obj) => {
    const light = obj as THREE.Light
    const hemi = obj as THREE.HemisphereLight
    const ambient = obj as THREE.AmbientLight
    const dir = obj as THREE.DirectionalLight
    const point = obj as THREE.PointLight
    if (hemi.isHemisphereLight) {
      // 压环境光：明暗对比集中到主光，双色明暗 + 描边才立得住
      light.intensity = baseOf(light) * 0.35
    } else if (ambient.isAmbientLight) {
      light.intensity = baseOf(light) * 0.28
    } else if (dir.isDirectionalLight) {
      light.intensity = baseOf(light) * 2.0
      if (!mainLightTaken) {
        // 第一个平行光视为主光：挪到侧低位，出赛璐璐构图的标志性长投影
        mainLightTaken = true
        if (!mainLightBasePosition.has(dir)) mainLightBasePosition.set(dir, dir.position.clone())
        dir.position.set(-14, 11, 3)
      }
    } else if (point.isPointLight) {
      light.intensity = baseOf(light) * 0.7
    }
  })
}

// ---- 窗口光柱 ---------------------------------------------------------------

/**
 * 窗口光柱：三片带渐变透明的斜置平面，从后墙窗户斜到地面。
 * 纯 MeshBasicMaterial 叠加，不受灯光/阴影影响，仅靠透明度渐隐营造体积光错觉。
 */
export function buildWindowShafts(width: number, depth: number, wallHeight: number): THREE.Group {
  // 渐变贴图：32x128 canvas 自上而下 0.85 → 0 线性渐隐（顶亮底淡，模拟光柱沿程衰减）
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 128
  const ctx = canvas.getContext('2d')
  if (ctx) {
    const grad = ctx.createLinearGradient(0, 0, 0, 128)
    grad.addColorStop(0, 'rgba(255,255,255,0.85)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, 32, 128)
  }
  const gradient = new THREE.CanvasTexture(canvas)

  // 三片同尺寸：几何与材质共享
  const geo = new THREE.PlaneGeometry(2.3, wallHeight * 1.55)
  const mat = new THREE.MeshBasicMaterial({
    map: gradient,
    transparent: true,
    opacity: 0.13,
    depthWrite: false,
    side: THREE.DoubleSide,
    color: 0xcfe2ff,
  })

  const group = new THREE.Group()
  group.name = 'window-shafts'
  // 以下摆位均为起始参考，可按房间尺寸微调：
  // 顶部对齐窗高（y ≈ wallHeight - 0.9），rotation.x = -1.15（约 66°）让平面从窗沿倒向 +z 地面
  const xs = [-width / 4, 0, width / 4]
  for (const x of xs) {
    const shaft = new THREE.Mesh(geo, mat)
    shaft.position.set(x, wallHeight * 0.62, -depth / 2 + 1.7)
    shaft.rotation.x = -1.15
    shaft.raycast = () => {}
    shaft.renderOrder = 5
    shaft.name = 'window-shaft'
    group.add(shaft)
  }
  return group
}

// ---- 角色树 -----------------------------------------------------------------

/**
 * 角色树用：把非 MToon 的 MeshStandardMaterial 原地换成 toon 孪生。
 * 角色模板此刻可能还没挂场景，因此不检查 visible；孪生走模块级缓存，
 * 多个角色克隆（clone 共享材质）命中同一个孪生。
 */
export function toonifyStandardMaterials(root: THREE.Object3D): void {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    if (!mesh.isMesh) return
    const material = mesh.material
    if (Array.isArray(material)) return
    const std = material as THREE.MeshStandardMaterial
    if (std.isMeshStandardMaterial && !isMToonMaterial(std)) {
      mesh.material = makeToonTwin(std)
    }
  })
}
