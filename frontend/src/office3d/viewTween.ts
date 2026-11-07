/**
 * 2D↔3D 视图过渡的纯数学层。参照 floorplan-3d（MIT）移植：
 * - planPose：与 2D 正交视口完全重合的正俯视透视位姿（地面可视高 = 正交视口高），
 *   保证切换第一帧像素级对齐，过渡从"图纸"无缝起飞。
 * - camTweenPose：以目标点为中心的球坐标插值，镜头沿弧线倾斜环绕而非直线穿越。
 * 相机/场景状态由 Office3DCanvas 持有，本模块只算位姿。
 * 新文件理由：进/出两条过渡路径复用的位姿数学，独立于场景代码可单测。
 */
import * as THREE from 'three'

export interface Pose3 {
  /** 视线目标点（地面） */
  t: THREE.Vector3
  /** 相机位置 */
  p: THREE.Vector3
  /** 相机 up（俯视帧与 2D 同向 = (0,0,-1)，等轴测落回 (0,1,0)） */
  up: THREE.Vector3
}

export const easeInOutCubic = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
export const clamp01 = (t: number): number => Math.max(0, Math.min(1, t))

/** 正交视口半高 halfH（世界米）换算成透视相机的正俯视高度 */
export function planPose(cx: number, cz: number, halfH: number, fovDeg: number): Pose3 {
  const dist = halfH / Math.tan((fovDeg / 2) * (Math.PI / 180))
  const t = new THREE.Vector3(cx, 0, cz)
  return { t, p: new THREE.Vector3(t.x, dist, t.z + 1e-4), up: new THREE.Vector3(0, 0, -1) }
}

/** 由俯视位姿推等轴测落点：方向固定，距离 = 俯视高度夹取（不跳变） */
export function isoFrom(P: Pose3, dirIn = new THREE.Vector3(0.3, 0.82, 0.49)): Pose3 {
  const d = THREE.MathUtils.clamp(P.p.y, 10, 34)
  const dir = dirIn.clone().normalize()
  return { t: P.t.clone(), p: P.t.clone().addScaledVector(dir, d), up: new THREE.Vector3(0, 1, 0) }
}

export function currentPose(camera: THREE.PerspectiveCamera, target: THREE.Vector3): Pose3 {
  return { t: target.clone(), p: camera.position.clone(), up: camera.up.clone() }
}

/** 以目标点为中心做球坐标插值：位置沿弧线，up 向量同步过渡（俯视 (0,0,-1) → 等轴测 (0,1,0)） */
export function camTweenPose(A: Pose3, B: Pose3, e: number, out: { p: THREE.Vector3; t: THREE.Vector3; up: THREE.Vector3 }): void {
  out.t.copy(A.t).lerp(B.t, e)
  const sa = new THREE.Spherical().setFromVector3(A.p.clone().sub(A.t))
  const sb = new THREE.Spherical().setFromVector3(B.p.clone().sub(B.t))
  let dth = sb.theta - sa.theta
  dth = Math.atan2(Math.sin(dth), Math.cos(dth))
  const s = new THREE.Spherical(sa.radius + (sb.radius - sa.radius) * e, sa.phi + (sb.phi - sa.phi) * e, sa.theta + dth * e)
  out.p.copy(out.t).add(new THREE.Vector3().setFromSpherical(s))
  out.up.copy(A.up).lerp(B.up, e).normalize()
}
