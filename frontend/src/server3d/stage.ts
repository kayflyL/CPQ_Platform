/**
 * server3d/stage.ts — 3D配置台渲染基座(纯TS,零Vue依赖)。
 * 渲染器/相机/轨道控制/bloom后期/灯光/地台光环/尘埃 + 双主题整场景切换 +
 * 视角预设镜头补间 + 部件悬停拾取。整机由 machine.ts 构建,本层只管舞台。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { STAGE_THEMES, glow } from './themes'
import { createMachine, DEFAULT_MACHINE_CONFIG, type MachineConfig } from './machine'
import { createCpuModel, type CpuSpec } from './parts/cpu'
import { createFanModel, type FanSpec } from './parts/fan'

export type StageView = 'front' | 'rear' | 'top' | 'inner'

/** 整机/部件统一舞台契约:machine 与 parts/* 工厂都满足,stage 只按此驱动 */
interface StageModel {
  root: THREE.Group
  /** 仅整机有:主题可换色的共享材质组(machine.applyTheme 缺省时走这里) */
  M?: Record<string, any>
  PART_INFO: Record<string, { name: string; spec: string; desc: string }>
  KEY_ALIAS?: Record<string, string | null>
  setCounts(c: { gpus?: number; cpus?: number; dimms?: number; bays?: number }): void
  setExploded(on: boolean): void
  updateTick(dt: number, t: number): void
  setHover(key: string | null): void
  setGlassBase?(v: number): void
  /** 部件自定主题钩子(按需取色表字段;整机无此钩子,走 M 材质换色)。参数放宽:any 主题表都可传 */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  applyTheme?(t: any, name: 'dark' | 'light'): void
  get explodeRatio(): number
}

/** 视角预设 = 方向向量(相对整机中心),距离由 auto-fit 按包围球实时推算 */
const VIEW_DIRS: Record<StageView, [number, number, number]> = {
  front: [0, 0.16, 1],
  rear: [0, 0.18, -1],
  top: [0.02, 1, 0.18],
  inner: [0.58, 0.42, 0.7],
}

export function createServerStage(container: HTMLElement, cfg: MachineConfig = DEFAULT_MACHINE_CONFIG,
  opts: { partType?: 'cpu' | 'fan'; partSpec?: CpuSpec | FanSpec; cpuFamily?: 'sp5' | 'kh' } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(container.clientWidth || 800, container.clientHeight || 480)
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.15
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  container.appendChild(renderer.domElement)

  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#0a1526')
  scene.fog = new THREE.FogExp2('#0a1526', 0.022)
  // 室内环境反射:镀镍/金属件(metalness 1)没有 env 会渲染成近黑(部件库 CPU 闸4教训)
  const pmrem = new THREE.PMREMGenerator(renderer)
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
  scene.environmentIntensity = 0.45

  const camera = new THREE.PerspectiveCamera(42, (container.clientWidth || 800) / (container.clientHeight || 480), 0.1, 200)
  camera.position.set(20, 13, 20)

  const controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, 0.9, 0)
  controls.enableDamping = true
  controls.dampingFactor = 0.07
  controls.minDistance = 3.5
  controls.maxDistance = 40
  controls.maxPolarAngle = opts.partType ? Math.PI * 0.95 : Math.PI * 0.52
  controls.autoRotate = true
  controls.autoRotateSpeed = 0.85

  // ── 选择性bloom双composer:辉光件打BLOOM层,其余件在bloom-only通道涂黑——
  // 金属镜面高光与霓虹辉光彻底解耦(2026-11-05 炸白根治):镀镍再亮也进不了bloom,阈值不必再悬停妥协 ──
  const BLOOM_LAYER = 1
  const bloomLayer = new THREE.Layers()
  bloomLayer.set(BLOOM_LAYER)
  const renderPass = new RenderPass(scene, camera)
  const bloomComposer = new EffectComposer(renderer)
  bloomComposer.renderToScreen = false
  bloomComposer.addPass(renderPass)
  const bloom = new UnrealBloomPass(new THREE.Vector2(container.clientWidth || 800, container.clientHeight || 480), 1.1, 0.5, 0.25)
  bloomComposer.addPass(bloom)
  const mixPass = new ShaderPass(new THREE.ShaderMaterial({
    uniforms: {
      baseTexture: { value: null },
      bloomTexture: { value: bloomComposer.renderTarget2.texture },
    },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform sampler2D baseTexture; uniform sampler2D bloomTexture; varying vec2 vUv;
      void main(){ gl_FragColor = texture2D(baseTexture, vUv) + texture2D(bloomTexture, vUv); }`,
  }), 'baseTexture')
  const composer = new EffectComposer(renderer)
  composer.addPass(renderPass)
  composer.addPass(mixPass)
  composer.addPass(new OutputPass())

  // bloom-only 通道的涂黑/还原:黑涂料关雾(fog:true 会把涂黑件染向雾色=背景色,浅色下假发光)
  const darkMaterial = new THREE.MeshBasicMaterial({ color: 0x000000, fog: false })
  const darkened = new Map<THREE.Object3D, THREE.Material | THREE.Material[]>()
  function darkenNonBloomed(o: THREE.Object3D) {
    const mesh = o as THREE.Mesh
    if (mesh.isMesh && !bloomLayer.test(o.layers)) {
      darkened.set(o, mesh.material as THREE.Material)
      mesh.material = darkMaterial
    }
  }
  function restoreMaterial(o: THREE.Object3D) {
    const m = darkened.get(o)
    if (m) { (o as THREE.Mesh).material = m; darkened.delete(o) }
  }

  const ambient = new THREE.AmbientLight('#8fb4dd', 0.65)
  scene.add(ambient)
  const key = new THREE.DirectionalLight('#eaf4ff', 2.0)
  key.position.set(7, 12, 6)
  key.castShadow = true
  key.shadow.mapSize.set(2048, 2048)
  key.shadow.camera.left = -9
  key.shadow.camera.right = 9
  key.shadow.camera.top = 9
  key.shadow.camera.bottom = -9
  key.shadow.radius = 6
  scene.add(key)
  const rimCyan = new THREE.PointLight('#1e6fff', 7, 30)
  rimCyan.position.set(-8, 4, -8)
  scene.add(rimCyan)
  const rimViolet = new THREE.PointLight('#7c3aed', 5, 30)
  rimViolet.position.set(8, 3, -9)
  scene.add(rimViolet)
  const fillTop = new THREE.PointLight('#a5d8ff', 14, 16)
  fillTop.position.set(0, 4.2, 0.5)
  scene.add(fillTop)

  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(34, 72),
    new THREE.MeshStandardMaterial({ color: '#0c1930', roughness: 0.92, metalness: 0.25 }),
  )
  floor.rotation.x = -Math.PI / 2
  floor.position.y = -0.08
  floor.receiveShadow = true
  scene.add(floor)

  let grid: THREE.PolarGridHelper | null = null
  function buildGrid(c1: number, c2: number) {
    if (grid) {
      scene.remove(grid)
      grid.geometry.dispose()
      ;(grid.material as THREE.Material).dispose()
    }
    grid = new THREE.PolarGridHelper(30, 12, 8, 72, c1, c2)
    grid.position.y = -0.07
    scene.add(grid)
  }

  const ringA = new THREE.Mesh(new THREE.TorusGeometry(4.6, 0.02, 8, 128), glow('#21a8ff', 1.6))
  ringA.rotation.x = -Math.PI / 2
  ringA.position.y = -0.04
  scene.add(ringA)
  const ringB = new THREE.Mesh(new THREE.TorusGeometry(5.1, 0.02, 8, 128), glow('#7c5cff', 0.9))
  ringB.rotation.x = -Math.PI / 2
  ringB.position.y = -0.04
  scene.add(ringB)

  const dustGeo = new THREE.BufferGeometry()
  {
    const N = 260
    const pos = new Float32Array(N * 3)
    for (let i = 0; i < N; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 26
      pos[i * 3 + 1] = Math.random() * 9
      pos[i * 3 + 2] = (Math.random() - 0.5) * 26
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  }
  const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({
    color: '#3b82f6', size: 0.045, transparent: true, opacity: 0.5,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }))
  scene.add(dust)

  // ── 灯光rig:点光/装饰环/尘埃统一装组,随模型包围球缩放(基准=整机半径4.6)。
  // 点光物理衰减∝1/d²,位置×s则强度×s²,模型表面照度与模型尺寸无关;
  // 平行光方向/环境光/环境反射天然尺度不变;雾密度反比缩放保持同等的空气透视感。 ──
  const RIG_REF_RADIUS = 4.6
  const rig = new THREE.Group()
  scene.add(rig)
  rig.add(fillTop, rimCyan, rimViolet, ringA, ringB, dust)
  const rigScale = { s: 1 }
  let themeName: 'dark' | 'light' = 'dark'
  function applyRigScale() {
    if (!fitSphere || fitSphere.radius <= 0) return
    const s = Math.max(0.12, fitSphere.radius / RIG_REF_RADIUS)
    rigScale.s = s
    rig.scale.setScalar(s)
    ;(scene.fog as THREE.FogExp2).density = 0.022 / s
    const sc = key.shadow.camera
    sc.left = -9 * s; sc.right = 9 * s; sc.top = 9 * s; sc.bottom = -9 * s
    sc.updateProjectionMatrix()
    controls.minDistance = 3.5 * s
    controls.maxDistance = 40 * s
    const t = STAGE_THEMES[themeName]
    fillTop.intensity = t.fill * s * s
    rimCyan.intensity = t.rimC * s * s
    rimViolet.intensity = t.rimV * s * s
  }

  const machine = (opts.partType === 'cpu' ? createCpuModel(opts.partSpec)
    : opts.partType === 'fan' ? createFanModel(opts.partSpec as FanSpec)
    : createMachine(opts.cpuFamily ? { ...cfg, cpuFamily: opts.cpuFamily } : cfg)) as StageModel
  scene.add(machine.root)

  // 辉光件上bloom层:整机的霓虹件恰好全是 MeshBasicMaterial(边光/LED/光环/走线),按材质类型标记;
  // cpu 品牌刻字是白色 Basic 平面(非霓虹)带 noBloom 豁免。环/尘埃是舞台自带的霓虹,直接标记。
  machine.root.traverse(o => {
    const mesh = o as THREE.Mesh
    if (mesh.isMesh && (mesh.material as THREE.MeshBasicMaterial)?.isMeshBasicMaterial && !o.userData.noBloom)
      o.layers.enable(BLOOM_LAYER)
  })
  ringA.layers.enable(BLOOM_LAYER)
  ringB.layers.enable(BLOOM_LAYER)
  dust.layers.enable(BLOOM_LAYER)

  function applyTheme(name: 'dark' | 'light') {
    themeName = name
    const t = STAGE_THEMES[name]
    ;(scene.background as THREE.Color).set(t.bg)
    ;(scene.fog as THREE.FogExp2).color.set(t.bg)
    floor.material.color.set(t.floor)
    buildGrid(t.grid1, t.grid2)
    if (machine.applyTheme) {
      machine.applyTheme(t, name)
    } else {
      machine.M!.body.color.set(t.body)
      machine.M!.dark.color.set(t.dark)
      machine.M!.fin.color.set(t.fin)
      machine.M!.glass.color.set(t.glass)
      machine.M!.board.color.set(t.board)
      machine.M!.boardDk.color.set(t.boardDk)
      machine.setGlassBase!(t.glassBase)
    }
    ambient.intensity = t.amb
    key.intensity = t.key
    fillTop.intensity = t.fill * rigScale.s * rigScale.s
    rimCyan.intensity = t.rimC * rigScale.s * rigScale.s
    rimViolet.intensity = t.rimV * rigScale.s * rigScale.s
    scene.environmentIntensity = t.env
    bloom.strength = t.bloom
    bloom.threshold = t.bloomThr
    renderer.toneMappingExposure = t.exp
  }

  let camTween: null | { t: number; dur: number; p0: THREE.Vector3; p1: THREE.Vector3; g0: THREE.Vector3; g1: THREE.Vector3; resumeRotate?: boolean } = null

  // ── auto-fit 取景:按整机包围球与画布宽高比推算"刚好装下+留边"的相机距离 ──
  let fitSphere: { center: THREE.Vector3; radius: number } | null = null
  let userMoved = false
  controls.addEventListener('start', () => { userMoved = true })
  function computeFit() {
    const box = new THREE.Box3().setFromObject(machine.root)
    if (box.isEmpty()) return
    fitSphere = {
      center: box.getCenter(new THREE.Vector3()),
      radius: box.getBoundingSphere(new THREE.Sphere()).radius,
    }
    applyRigScale()
  }
  function fitDistance() {
    if (!fitSphere) return 12
    const vFov = (camera.fov * Math.PI) / 180
    const hFov = 2 * Math.atan(Math.tan(((camera.fov * Math.PI) / 180) / 2) * camera.aspect)
    return (fitSphere.radius / Math.sin(Math.min(vFov, hFov) / 2)) * 1.12
  }
  function flyTo(v: StageView, opts: { resumeRotate?: boolean; dur?: number } = {}) {
    if (!fitSphere) computeFit()
    if (!fitSphere) return
    const dir = new THREE.Vector3(...VIEW_DIRS[v]).normalize()
    const p1 = fitSphere.center.clone().addScaledVector(dir, fitDistance())
    camTween = {
      t: 0, dur: opts.dur ?? 0.9,
      p0: camera.position.clone(), p1,
      g0: controls.target.clone(), g1: fitSphere.center.clone(),
      resumeRotate: opts.resumeRotate,
    }
    controls.autoRotate = false
  }

  // ── 悬停拾取(userData.part 语义键) ──
  const ray = new THREE.Raycaster()
  const ptr = new THREE.Vector2()
  let hovered: string | null = null
  function resolveKey(obj: THREE.Object3D | null): string | null {
    let o: THREE.Object3D | null = obj
    while (o && o !== scene) {
      if (o.userData && o.userData.part != null) {
        const k = o.userData.part as string
        const ka = machine.KEY_ALIAS ?? {}
        return ka[k] !== undefined ? ka[k]! : (machine.PART_INFO[k] ? k : null)
      }
      o = o.parent
    }
    return null
  }
  function onPointerMove(e: PointerEvent) {
    const rect = renderer.domElement.getBoundingClientRect()
    ptr.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    ptr.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    ray.setFromCamera(ptr, camera)
    const hits = ray.intersectObjects(machine.root.children, true)
    let k: string | null = null
    const chainVisible = (o: THREE.Object3D) => {
      for (let p: THREE.Object3D | null = o; p && p !== machine.root; p = p.parent) if (p.visible === false) return false
      return true
    }
    for (const h of hits) {
      if (!chainVisible(h.object)) continue
      k = resolveKey(h.object)
      if (k) break
    }
    hovered = k
    if (onHover) onHover(k)
  }
  let onHover: ((k: string | null) => void) | null = null
  function setOnHover(fn: (k: string | null) => void) {
    onHover = fn
  }
  renderer.domElement.addEventListener('pointermove', onPointerMove)

  // ── 主循环 ──
  const clock = new THREE.Clock()
  let rafId = 0
  let disposed = false
  /** 选择性bloom一帧:涂黑非辉光件渲染bloom-only通道,再混进干净场景一次出屏 */
  function renderFrame() {
    const bg = scene.background
    scene.background = null
    scene.traverse(darkenNonBloomed)
    bloomComposer.render()
    scene.traverse(restoreMaterial)
    scene.background = bg
    composer.render()
  }
  function tick() {
    if (disposed) return
    rafId = requestAnimationFrame(tick)
    const dt = Math.min(clock.getDelta(), 0.05)
    const t = clock.elapsedTime
    controls.update()
    if (camTween) {
      camTween.t += dt / camTween.dur
      const k = Math.min(camTween.t, 1)
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2
      camera.position.lerpVectors(camTween.p0, camTween.p1, e)
      controls.target.lerpVectors(camTween.g0, camTween.g1, e)
      camera.lookAt(controls.target)
      if (camTween.t >= 1) {
        if (camTween.resumeRotate) {
          controls.autoRotate = true
          onResumeRotate?.()
        }
        camTween = null
      }
    }
    machine.updateTick(dt, t)
    machine.setHover(hovered)
    ringA.material.color.set('#21a8ff').multiplyScalar(1.2 + 0.35 * Math.sin(t * 1.4))
    dust.rotation.y += dt * 0.01
    dust.position.y = Math.sin(t * 0.18) * 0.3
    renderFrame()
  }

  function resize() {
    const w = container.clientWidth || 800
    const h = container.clientHeight || 480
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
    composer.setSize(w, h)
    bloomComposer.setSize(w, h)
    // 未动手前跟随画布尺寸自动取景;一旦用户手动控制即交还
    if (!userMoved && fitSphere) {
      const dir = camera.position.clone().sub(controls.target).normalize()
      camera.position.copy(controls.target.clone().addScaledVector(dir, fitDistance()))
    }
  }
  const ro = new ResizeObserver(resize)
  ro.observe(container)

  let onResumeRotate: (() => void) | null = null

  flyTo('inner', { resumeRotate: true, dur: 2.2 })
  applyTheme('dark')
  tick()

  return {
    machine,
    camera, controls,
    applyTheme,
    flyTo,
    setOnHover,
    setAutoRotate(on: boolean) { controls.autoRotate = on },
    setExploded(on: boolean) { machine.setExploded(on) },
    /** 调试口:后台页 rAF 暂停时手动步进一帧(排障/E2E 截图用) */
    renderOnce(dt = 0.016) {
      const t = clock.elapsedTime + dt
      clock.getDelta()
      machine.updateTick(dt, t)
      machine.setHover(hovered)
      controls.update()
      renderFrame()
    },
    onResize: resize,
    dispose() {
      disposed = true
      cancelAnimationFrame(rafId)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointermove', onPointerMove)
      controls.dispose()
      composer.dispose()
      bloomComposer.dispose()
      renderer.dispose()
      if (renderer.domElement.parentElement === container) container.removeChild(renderer.domElement)
    },
  }
}

export type ServerStage = ReturnType<typeof createServerStage>
