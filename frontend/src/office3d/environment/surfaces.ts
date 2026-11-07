/**
 * 表面配方库（C1）。材质差异靠粗糙度阶梯 + envMap 分级挂载，不靠颜色堆：
 * 布料近乎全哑光（.96）→ 木（.55）→ 陶瓷（.12）→ 镜面（.06），这条阶梯才是
 * "一眼分辨材质"的原因；环境反射只给金属和光滑面，哑光面显式归零，避免
 * RoomEnvironment 的白色反射把整屋垫灰（"彩色塑料感"的根源）。
 * 配方参照 floorplan-3d（MIT）的表面纪律移植，坐标系/单位按本引擎约定。
 * envMapIntensity 与场景级 scene.environmentIntensity 相乘生效，见 Office3DCanvas。
 */
import * as THREE from 'three'

/** envMap 分级：金属满反射，光滑面/弱金属半强，哑光面零 */
export function gradeEnv(metalness: number, roughness: number): number {
  if (metalness >= 0.5) return 1
  if (metalness > 0 || roughness < 0.4) return 0.5
  return 0
}

/** 同色系派生：明度阶梯用同一色相，一个模型内不引入第二个色相 */
export function darken(color: string | number, k = 0.8): string {
  return '#' + new THREE.Color(color).multiplyScalar(k).getHexString()
}
export function lighten(color: string | number, k = 0.2): string {
  return '#' + new THREE.Color(color).lerp(new THREE.Color('#ffffff'), k).getHexString()
}

type Opts = Partial<THREE.MeshStandardMaterialParameters>

function make(color: string | number, roughness: number, metalness: number, opts?: Opts): THREE.MeshStandardMaterial {
  const m = new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness, metalness, ...opts })
  m.envMapIntensity = gradeEnv(m.metalness, m.roughness)
  return m
}

/** 批量配方带缓存：同一（配方,颜色,参数）全场共用一份材质实例 */
const cache = new Map<string, THREE.MeshStandardMaterial>()
function cached(kind: string, color: string | number, opts: Opts | undefined, makeFn: () => THREE.MeshStandardMaterial): THREE.MeshStandardMaterial {
  const key = `${kind}|${color}|${opts ? JSON.stringify(opts) : ''}`
  let m = cache.get(key)
  if (!m) {
    m = makeFn()
    cache.set(key, m)
  }
  return m
}

/** 布料：沙发/椅面/床品，近乎全哑光 */
export function fabricMat(color: string | number, opts?: Opts) {
  return cached('fabric', color, opts, () => make(color, 0.96, 0, opts))
}
/** 木饰面：桌面/柜体/腿 */
export function woodMat(color: string | number, opts?: Opts) {
  return cached('wood', color, opts, () => make(color, 0.55, 0, opts))
}
/** 陶瓷：杯盘/洁具/灯座，近高光 */
export function ceramicMat(color: string | number = '#fbfbf9', opts?: Opts) {
  return cached('ceramic', color, opts, () => make(color, 0.12, 0, opts))
}
/** 哑光面：墙体/地面基材，永不挂反射 */
export function matteMat(color: string | number, roughness = 0.82, opts?: Opts) {
  return cached('matte', color, { roughness, ...opts }, () => make(color, roughness, 0, opts))
}
/** 金属：框架/拉手/桌腿 */
export function metalMat(color: string | number = '#cfd2d4') {
  return cached('metal', color, undefined, () => make(color, 0.25, 0.9))
}
/** 镀铬：气压杆/亮金属件 */
export function chromeMat() {
  return cached('chrome', '', undefined, () => make('#eef0f2', 0.08, 1))
}
/** 黑色金属：显示器支架/设备外壳 */
export function blackMetalMat() {
  return cached('blackMetal', '', undefined, () => make('#2b2b2d', 0.4, 0.6))
}
/** 镜面：金属度略低的高光面 */
export function mirrorMat(color: string | number = '#dfeaee') {
  return cached('mirror', color, undefined, () => make(color, 0.06, 0.55))
}
/** 屏幕：深色底 + 蓝灰辉光，"亮着但不过曝" */
export function screenGlowMat(glow = '#27405c') {
  return cached('screen', glow, undefined, () => make('#0a0e13', 0.1, 0.3, { emissive: new THREE.Color(glow), emissiveIntensity: 0.35 }))
}
/** 灯罩发光面：暖色自发光 */
export function lampGlowMat(color = '#fff4dc', emissive = '#ffdca0', intensity = 0.5) {
  return cached('lampGlow', `${color}|${emissive}|${intensity}`, undefined, () =>
    make(color, 0.9, 0, { emissive: new THREE.Color(emissive), emissiveIntensity: intensity, side: THREE.DoubleSide }))
}
