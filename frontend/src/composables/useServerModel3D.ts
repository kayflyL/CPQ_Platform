import { ref, watch, onMounted, onBeforeUnmount, computed, unref, type Ref } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { useThemeStore } from '@/store/theme'

interface RenderConfig {
  ambient_intensity?: number
  key_light_intensity?: number
  fill_light_intensity?: number
  key_light_color?: string
  fill_light_color?: string
  background_color?: string
  tone_mapping?: 'NoToneMapping' | 'LinearToneMapping' | 'ACESFilmicToneMapping'
  exposure?: number
}

interface RenderOptions {
  src: string
  renderConfig?: {
    light?: RenderConfig
    dark?: RenderConfig
    camera_fov?: number
    auto_rotate_speed?: number
    enable_damping?: boolean
    damping_factor?: number
  }
}

type MaybeRef<T> = T | Ref<T>

/**
 * 服务器 3D 模型展示 —— 加载 .glb，自动缓慢旋转 + 拖拽/滚轮缩放。
 * canvas 透明，露出玻璃卡片 CSS 背景；光照随主题切换。
 * 尊重 prefers-reduced-motion：减弱动效环境下关闭自转。
 * 参照 useCountUp 的 RAF 清理 + useChartTheme 的主题读取。
 *
 * @param containerRef 容器元素引用
 * @param options 渲染选项，支持 Ref 包装以实现实时预览
 */
export function useServerModel3D(
  containerRef: Ref<HTMLElement | null>,
  options: MaybeRef<RenderOptions>,
) {
  const loading = ref(true)
  const error = ref<string | null>(null)

  // 响应式解包 options
  const opts = computed(() => unref(options))

  const reduceMotion = typeof window !== 'undefined'
    && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  let scene!: THREE.Scene
  let camera!: THREE.PerspectiveCamera
  let renderer!: THREE.WebGLRenderer
  let controls!: OrbitControls
  let ambient!: THREE.AmbientLight
  let keyLight!: THREE.DirectionalLight
  let fillLight!: THREE.DirectionalLight
  let pivot: THREE.Group | null = null
  let raf = 0
  let ro: ResizeObserver | null = null
  let disposed = false
  let initialized = false

  function applyLights(isDark: boolean, renderConfig?: RenderOptions['renderConfig']) {
    const themeConfig = isDark
      ? (renderConfig?.dark || {})
      : (renderConfig?.light || {})

    // 灯光强度
    ambient.intensity = themeConfig.ambient_intensity ?? (isDark ? 0.9 : 0.6)
    keyLight.intensity = themeConfig.key_light_intensity ?? (isDark ? 1.1 : 1.45)
    fillLight.intensity = themeConfig.fill_light_intensity ?? (isDark ? 0.5 : 0.35)

    // 灯光颜色
    if (themeConfig.key_light_color) {
      keyLight.color.set(themeConfig.key_light_color)
    }
    if (themeConfig.fill_light_color) {
      fillLight.color.set(themeConfig.fill_light_color)
    }

    // 背景颜色
    if (themeConfig.background_color) {
      scene.background = new THREE.Color(themeConfig.background_color)
    } else {
      scene.background = null
    }

    // 色调映射
    const toneMapping = themeConfig.tone_mapping || 'NoToneMapping'
    renderer.toneMapping = THREE[toneMapping]

    // 曝光度
    if (themeConfig.exposure !== undefined) {
      renderer.toneMappingExposure = themeConfig.exposure
    }
  }

  function onResize() {
    const el = containerRef.value
    if (!el || !renderer) return
    const w = el.clientWidth
    const h = el.clientHeight
    if (w === 0 || h === 0) return
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(w, h, false)
  }

  function tick() {
    if (disposed) return
    controls.update()
    renderer.render(scene, camera)
    raf = requestAnimationFrame(tick)
  }

  const themeStore = useThemeStore()

  onMounted(() => {
    const el = containerRef.value
    const currentOpts = opts.value
    console.log('[useServerModel3D] onMounted, containerRef:', el, 'src:', currentOpts.src)
    if (!el) {
      console.warn('[useServerModel3D] Container element is null, skipping initialization')
      return
    }

    scene = new THREE.Scene()
    camera = new THREE.PerspectiveCamera(
      currentOpts.renderConfig?.camera_fov || 45,
      1,
      0.1,
      1000,
    )
    camera.position.set(0, 1, 5)

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setClearColor(0x000000, 0)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    el.appendChild(renderer.domElement)

    ambient = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambient)
    keyLight = new THREE.DirectionalLight(0xffffff, 1.45)
    keyLight.position.set(4, 6, 5)
    scene.add(keyLight)
    fillLight = new THREE.DirectionalLight(0xbfd4ff, 0.35)
    fillLight.position.set(-5, 2, -3)
    scene.add(fillLight)
    applyLights(themeStore.isDark, currentOpts.renderConfig)

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = currentOpts.renderConfig?.enable_damping ?? true
    controls.dampingFactor = currentOpts.renderConfig?.damping_factor || 0.08
    controls.enablePan = false
    controls.autoRotate = !reduceMotion
    controls.autoRotateSpeed = currentOpts.renderConfig?.auto_rotate_speed || 0.8

    onResize()
    ro = new ResizeObserver(onResize)
    ro.observe(el)

    raf = requestAnimationFrame(tick)

    const loader = new GLTFLoader()
    console.log('[useServerModel3D] Starting GLB load:', currentOpts.src)
    loader.load(
      currentOpts.src,
      (gltf) => {
        if (disposed) return
        console.log('[useServerModel3D] GLB loaded successfully')
        const model = gltf.scene
        pivot = new THREE.Group()
        pivot.add(model)
        scene.add(pivot)

        // 归一化：box 中心归原点 + 缩放到 max dim = 2，缩放绕 pivot 原点即 box 中心，位置不漂
        const box = new THREE.Box3().setFromObject(model)
        const center = new THREE.Vector3()
        const size = new THREE.Vector3()
        box.getCenter(center)
        box.getSize(size)
        model.position.sub(center)
        const maxDim = Math.max(size.x, size.y, size.z) || 1
        pivot.scale.setScalar(2 / maxDim)

        // 按 scaled 包围球 + fov 反算相机距离
        const sphere = new THREE.Sphere()
        box.getBoundingSphere(sphere)
        const scaledR = sphere.radius * (2 / maxDim)
        const fov = (camera.fov * Math.PI) / 180
        const dist = (scaledR / Math.sin(fov / 2)) * 1.15
        camera.position.set(dist * 0.5, dist * 0.35, dist)
        camera.lookAt(0, 0, 0)
        controls.target.set(0, 0, 0)
        controls.minDistance = dist * 0.4
        controls.maxDistance = dist * 2.5
        controls.update()

        initialized = true
        loading.value = false
      },
      undefined,
      (err) => {
        if (disposed) return
        console.error('[useServerModel3D] GLB 加载失败', err)
        error.value = '3D 模型加载失败'
        loading.value = false
      },
    )
  })

  // 监听主题变化
  watch(() => themeStore.isDark, (isDark) => {
    if (ambient && initialized) {
      applyLights(isDark, opts.value.renderConfig)
    }
  })

  // 监听渲染配置变化（实时预览）
  watch(() => opts.value.renderConfig, (newConfig) => {
    if (!newConfig || !ambient || !initialized) return

    const themeConfig = themeStore.isDark ? newConfig.dark : newConfig.light
    if (themeConfig) {
      ambient.intensity = themeConfig.ambient_intensity ?? ambient.intensity
      keyLight.intensity = themeConfig.key_light_intensity ?? keyLight.intensity
      fillLight.intensity = themeConfig.fill_light_intensity ?? fillLight.intensity

      if (themeConfig.key_light_color) {
        keyLight.color.set(themeConfig.key_light_color)
      }
      if (themeConfig.fill_light_color) {
        fillLight.color.set(themeConfig.fill_light_color)
      }
      if (themeConfig.background_color) {
        scene.background = new THREE.Color(themeConfig.background_color)
      }
      if (themeConfig.tone_mapping) {
        renderer.toneMapping = THREE[themeConfig.tone_mapping]
      }
      if (themeConfig.exposure !== undefined) {
        renderer.toneMappingExposure = themeConfig.exposure
      }
    }

    // 相机参数
    if (newConfig.camera_fov !== undefined) {
      camera.fov = newConfig.camera_fov
      camera.updateProjectionMatrix()
    }

    // 控制器参数
    if (newConfig.auto_rotate_speed !== undefined) {
      controls.autoRotateSpeed = newConfig.auto_rotate_speed
    }
    if (newConfig.enable_damping !== undefined) {
      controls.enableDamping = newConfig.enable_damping
    }
    if (newConfig.damping_factor !== undefined) {
      controls.dampingFactor = newConfig.damping_factor
    }
  }, { deep: true })

  onBeforeUnmount(() => {
    disposed = true
    cancelAnimationFrame(raf)
    ro?.disconnect()
    ro = null
    controls?.dispose()
    if (pivot) {
      pivot.traverse((obj) => {
        const mesh = obj as THREE.Mesh
        if (mesh.geometry) mesh.geometry.dispose()
        const mat = (mesh as any).material
        if (Array.isArray(mat)) mat.forEach(disposeMaterial)
        else if (mat) disposeMaterial(mat)
      })
      pivot = null
    }
    renderer?.dispose()
    const canvas = renderer?.domElement
    if (canvas?.parentNode) canvas.parentNode.removeChild(canvas)
  })

  return { loading, error }
}

function disposeMaterial(m: THREE.Material) {
  const any = m as any
  for (const k of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap']) {
    any[k]?.dispose?.()
  }
  m.dispose()
}
