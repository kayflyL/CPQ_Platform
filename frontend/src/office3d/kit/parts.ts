/**
 * 几何零件工具箱（D）。程序化建模的基础件，参照 floorplan-3d（MIT）移植：
 * 倒角盒/收分杆/弯管/旋转体/椭球/中空框/拉手/柜门网格。约定：
 * - 除特别注明外 y = 底面高度（box/rbox/cyl 内部抬升 h/2），单位米
 * - 所有 mesh 默认 castShadow + receiveShadow
 * - 材质参数可传色值字符串（走 surfaces 配方缓存）或现成 Material
 * 新文件理由：被环境/家具/角色多处置做消费的基础层，独立于 environment 单件。
 */
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { metalMat } from '../environment/surfaces.ts'

export type MatLike = string | THREE.Material

/** 可复现伪随机（mulberry32）：种子相同则序列相同——同一家具每次构建长得一样，不同实例各异 */
export function rng(seed: number): () => number {
  let s = seed | 0
  return () => {
    s = (s + 0x6d2b79f5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const asMat = (m: MatLike): THREE.Material => (typeof m === 'string' ? metalMat(m) : m)

const sh = <T extends THREE.Mesh>(o: T): T => {
  o.castShadow = true
  o.receiveShadow = true
  return o
}

export function box(w: number, h: number, d: number, m: MatLike, x = 0, y = 0, z = 0): THREE.Mesh {
  const o = sh(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), asMat(m)))
  o.position.set(x, y + h / 2, z)
  return o
}

/** 倒角盒：所有直角棱圆润化，r 默认 4cm（会被各轴半宽夹住防炸） */
export function rbox(w: number, h: number, d: number, m: MatLike, x = 0, y = 0, z = 0, r = 0.04): THREE.Mesh {
  const rr = Math.min(r, w / 2 - 0.001, h / 2 - 0.001, d / 2 - 0.001)
  const o = sh(new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, rr), asMat(m)))
  o.position.set(x, y + h / 2, z)
  return o
}

export function cyl(rt: number, rb: number, h: number, m: MatLike, x = 0, y = 0, z = 0, seg = 28): THREE.Mesh {
  const o = sh(new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), asMat(m)))
  o.position.set(x, y + h / 2, z)
  return o
}

/** 旋转体：pts = [[半径, 高度], …] 自下而上，y = 底面（花瓶/灯座/陶盆） */
export function lathe(pts: Array<[number, number]>, m: MatLike, x = 0, y = 0, z = 0, seg = 40): THREE.Mesh {
  const geo = new THREE.LatheGeometry(pts.map(([r, h]) => new THREE.Vector2(Math.max(r, 1e-4), h)), seg)
  const o = sh(new THREE.Mesh(geo, asMat(m)))
  o.position.set(x, y, z)
  return o
}

/** 两点间圆杆，r0 在 a 端、r1 在 b 端（收分腿、斜撑） */
export function rod(a: [number, number, number], b: [number, number, number], r0: number, m: MatLike, r1 = r0, seg = 12): THREE.Mesh {
  const A = new THREE.Vector3(...a)
  const B = new THREE.Vector3(...b)
  const o = sh(new THREE.Mesh(new THREE.CylinderGeometry(r1, r0, A.distanceTo(B), seg), asMat(m)))
  o.position.copy(A).add(B).multiplyScalar(0.5)
  o.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), B.sub(A).normalize())
  return o
}

/** 沿曲线的圆管（灯臂/扶手/线缆），pts 为折线控制点 */
export function tube(pts: Array<[number, number, number]>, r: number, m: MatLike, seg = 40): THREE.Mesh {
  const curve = new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p)), false, 'centripetal')
  return sh(new THREE.Mesh(new THREE.TubeGeometry(curve, seg, r, 10), asMat(m)))
}

/** 椭球（靠垫/软垫），y = 中心 */
export function blob(rx: number, ry: number, rz: number, m: MatLike, x = 0, y = 0, z = 0, seg = 24): THREE.Mesh {
  const o = sh(new THREE.Mesh(new THREE.SphereGeometry(1, seg, Math.round(seg * 0.7)), asMat(m)))
  o.scale.set(rx, ry, rz)
  o.position.set(x, y, z)
  return o
}

/** 水平圆环，y = 中心 */
export function ring(R: number, r: number, m: MatLike, x = 0, y = 0, z = 0): THREE.Mesh {
  const o = sh(new THREE.Mesh(new THREE.TorusGeometry(R, r, 10, 48), asMat(m)))
  o.rotation.x = Math.PI / 2
  o.position.set(x, y, z)
  return o
}

function rrectShape(w: number, d: number, r: number): THREE.Shape {
  const s = new THREE.Shape()
  const x = -w / 2
  const y = -d / 2
  const rr = Math.min(r, w / 2 - 0.001, d / 2 - 0.001)
  s.moveTo(x + rr, y)
  s.lineTo(x + w - rr, y)
  s.quadraticCurveTo(x + w, y, x + w, y + rr)
  s.lineTo(x + w, y + d - rr)
  s.quadraticCurveTo(x + w, y + d, x + w - rr, y + d)
  s.lineTo(x + rr, y + d)
  s.quadraticCurveTo(x, y + d, x, y + d - rr)
  s.lineTo(x, y + rr)
  s.quadraticCurveTo(x, y, x + rr, y)
  return s
}

/** 中空圆角框：外 w×d、壁厚 t、拉伸高 h（椅背框/台面沿口），y = 底面 */
export function shellFrame(w: number, d: number, h: number, t: number, r: number, m: MatLike, x = 0, y = 0, z = 0): THREE.Mesh {
  const s = rrectShape(w, d, r)
  s.holes.push(rrectShape(w - 2 * t, d - 2 * t, Math.max(0.004, r - t)))
  const geo = new THREE.ExtrudeGeometry(s, { depth: h, bevelEnabled: false, curveSegments: 10 })
  geo.rotateX(-Math.PI / 2)
  const o = sh(new THREE.Mesh(geo, asMat(m)))
  o.position.set(x, y, z)
  return o
}

/** 四条收分腿：inset 为距边距离，r 为腿底半径（顶部略粗） */
export function legs(g: THREE.Group, w: number, d: number, h: number, m: MatLike, inset = 0.05, r = 0.02): void {
  const corners: Array<[-1 | 1, -1 | 1]> = [[-1, -1], [1, -1], [-1, 1], [1, 1]]
  corners.forEach(([a, b]) => g.add(rod([a * (w / 2 - inset), 0, b * (d / 2 - inset)], [a * (w / 2 - inset), h, b * (d / 2 - inset)], r * 0.7, m, r)))
}

/** 金属拉手：bar 条形，vert 竖向；y 为拉手中心，z 为门板正面 */
export function pull(g: THREE.Group, len: number, vert: boolean, x: number, y: number, z: number, m: MatLike = ''): void {
  const mat = typeof m === 'string' && !m ? metalMat() : asMat(m)
  const o = new THREE.Group()
  const barGeo = () => (vert ? new THREE.BoxGeometry(0.01, len, 0.01) : new THREE.BoxGeometry(len, 0.01, 0.01))
  o.add(new THREE.Mesh(barGeo(), mat))
  const stubGeo = () => (vert ? new THREE.BoxGeometry(0.008, 0.008, 0.028) : new THREE.BoxGeometry(0.008, 0.008, 0.028))
  for (const s of [-1, 1]) {
    const stub = new THREE.Mesh(stubGeo(), mat)
    if (vert) stub.position.set(0, s * (len / 2 - 0.015) - 0.004, 0.014)
    else stub.position.set(s * (len / 2 - 0.015), -0.004, 0.014)
    o.add(stub)
  }
  o.position.set(x, y, z)
  g.add(o)
}

/** 圆钮拉手 */
export function knob(g: THREE.Group, x: number, y: number, z: number, m: MatLike = ''): void {
  const mat = typeof m === 'string' && !m ? metalMat() : asMat(m)
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.014, 0.02, 16), mat)
  base.rotation.x = Math.PI / 2
  base.position.set(x, y - 0.01, z + 0.01)
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.014, 12, 8), mat)
  cap.scale.z = 0.6
  cap.position.set(x, y, z + 0.022)
  g.add(base, cap)
}

/** 柜门/抽屉面板网格：区域内 nx×ny 块，缝隙透出暗色底板，拉手左右交替。
 *  hd：'bar' 条形拉手 | 'knob' 圆钮 | 'edge' 顶部隐形拉槽 | 'none'；hy：门拉手中心高度 */
export function fronts(
  g: THREE.Group, x0: number, y0: number, w: number, h: number, z: number,
  nx: number, ny: number, m: THREE.Material, hd: 'bar' | 'knob' | 'edge' | 'none' = 'bar', hy: number | null = null,
): void {
  const gap = 0.005
  const pw = w / nx
  const ph = h / ny
  const fz = z + 0.018
  g.add(box(w, h, 0.002, '#1f1d1a', x0 + w / 2, y0, z + 0.001))
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < ny; j++) {
      const cx = x0 + pw * (i + 0.5)
      const yb = y0 + ph * j
      const drawer = ph < 0.4 && pw >= ph
      g.add(rbox(pw - gap, ph - gap, 0.018, m, cx, yb + gap / 2, z + 0.009, 0.003))
      if (hd === 'none') continue
      if (hd === 'edge') {
        g.add(box(pw - 0.05, 0.01, 0.006, '#3c3a37', cx, yb + ph - gap - 0.018, fz))
        continue
      }
      if (drawer) {
        hd === 'knob' ? knob(g, cx, yb + ph / 2, fz) : pull(g, Math.min(0.3, pw * 0.45), false, cx, yb + ph / 2, fz)
        continue
      }
      const len = Math.min(0.45, ph * 0.35)
      const hx = nx === 1 ? cx + pw / 2 - 0.045 : i % 2 ? cx - pw / 2 + 0.04 : cx + pw / 2 - 0.04
      const y = Math.min(yb + ph - 0.05 - len / 2, Math.max(yb + 0.05 + len / 2, hy ?? yb + ph / 2))
      hd === 'knob' ? knob(g, hx, y, fz) : pull(g, len, true, hx, y, fz)
    }
  }
}
