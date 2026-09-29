/**
 * 程序化动画烘焙（VRM 与绑骨 GLB 共用，F2）。
 * 以骨骼静止姿态为基，烘焙 idle/walk/sit 三段循环。纯数学无 IO，可 node --test。
 *
 * 面向无关：不假设模型朝 +Z——烘焙前先从左右臂/腿的实际静止方向自测量出
 * 「左右轴 rAxis」与「面朝轴 fAxis」，所有摆动绕这两根轴按实测符号进行。
 *
 * 世界轴换算：骨骼世界朝向 W = Wp·L（Wp=父级世界四元数）。施加世界系增量 Δw 时
 * W' = Δw·W ⇒ L' = Wp⁻¹·Δw·Wp·L，烘焙成局部四元数轨道后 SkeletonUtils 克隆按名解析仍成立。
 */
import * as THREE from 'three'

/** 与 actorSystem createCharacterFromTemplate 的模板归一身高保持一致。 */
const TARGET_HEIGHT = 1.42
/** 坐姿髋部目标：椅面上方（坐骨到髋关节中心的近似偏移）。 */
const SIT_HIP_ABOVE_SEAT = 0.1

export interface VrmBonePose {
  nodeName: string
  restQuat: THREE.Quaternion
  parentWorldQuat: THREE.Quaternion
  restPos: THREE.Vector3
  parentWorldPos: THREE.Vector3
}

export interface VrmSkeletonInfo {
  bones: Record<string, VrmBonePose>
  /** 模型原始身高（米）。 */
  height: number
}

const Y_UP = new THREE.Vector3(0, 1, 0)
const Y_DOWN = new THREE.Vector3(0, -1, 0)
const X_AXIS = new THREE.Vector3(1, 0, 0)
const Z_AXIS = new THREE.Vector3(0, 0, 1)
const d2r = (deg: number) => (deg * Math.PI) / 180

/** 世界系轴向旋转列表 → 局部四元数（列表靠后的先应用）。 */
function swingDelta(bone: VrmBonePose, delta: THREE.Quaternion): THREE.Quaternion {
  return bone.parentWorldQuat.clone().invert().multiply(delta).multiply(bone.parentWorldQuat).multiply(bone.restQuat)
}

function restWorldPos(bone: VrmBonePose): THREE.Vector3 {
  return bone.restPos.clone().applyQuaternion(bone.parentWorldQuat).add(bone.parentWorldPos)
}

/** 髋部位置：静止位置加世界系 Y 偏移（dy 按世界米制，内部换算模型局部单位）。 */
function hipsShiftedPos(bone: VrmBonePose, dy: number, height: number): THREE.Vector3 {
  const s = TARGET_HEIGHT / height
  const inv = bone.parentWorldQuat.clone().invert()
  return bone.restPos.clone().add(new THREE.Vector3(0, dy / s, 0).applyQuaternion(inv))
}

/** 坐姿髋部位置：令臀部（缩放后）落在「椅面上方 SIT_HIP_ABOVE_SEAT」的世界高度。 */
function hipsSeatedPos(bone: VrmBonePose, height: number): THREE.Vector3 {
  const s = TARGET_HEIGHT / height
  const restWorld = bone.restPos.clone().applyQuaternion(bone.parentWorldQuat).add(bone.parentWorldPos)
  const point = new THREE.Vector3(restWorld.x, SIT_HIP_ABOVE_SEAT / s, restWorld.z)
  return point.sub(bone.parentWorldPos).applyQuaternion(bone.parentWorldQuat.clone().invert())
}

type QuatSink = (bone: VrmBonePose, q: THREE.Quaternion) => void
type PosSink = (bone: VrmBonePose, p: THREE.Vector3) => void

function bakeClip(name: string, duration: number, samples: number, write: (t: number, addQuat: QuatSink, addPos: PosSink) => void): THREE.AnimationClip {
  const quatRows = new Map<string, number[]>()
  const posRows = new Map<string, number[]>()
  for (let i = 0; i < samples; i++) {
    write(
      i / samples,
      (bone, q) => {
        const row = quatRows.get(bone.nodeName) ?? []
        row.push(q.x, q.y, q.z, q.w)
        quatRows.set(bone.nodeName, row)
      },
      (bone, p) => {
        const row = posRows.get(bone.nodeName) ?? []
        row.push(p.x, p.y, p.z)
        posRows.set(bone.nodeName, row)
      },
    )
  }
  const times = new Float32Array(samples)
  for (let i = 0; i < samples; i++) times[i] = (i / samples) * duration
  const tracks: THREE.KeyframeTrack[] = []
  for (const [nodeName, data] of quatRows) {
    tracks.push(new THREE.QuaternionKeyframeTrack(`${nodeName}.quaternion`, times, new Float32Array(data)))
  }
  for (const [nodeName, data] of posRows) {
    tracks.push(new THREE.VectorKeyframeTrack(`${nodeName}.position`, times, new Float32Array(data)))
  }
  return new THREE.AnimationClip(name, duration, tracks)
}

/** 自测量出的骨架姿态轴：左右轴/面朝轴 + 各段摆动符号 + 手臂下拉四元数。 */
export interface SkeletonAxes {
  rAxis: THREE.Vector3
  fAxis: THREE.Vector3
  leanSign: number
  legSignL: number
  pullL: THREE.Quaternion
  pullR: THREE.Quaternion
  armSignL: number
  armSignR: number
}

/** 从静止姿态实测「左右轴/面朝轴」与摆动符号；关键骨骼缺失时退回经典 +Z 面向假设。 */
function measureAxes(bones: Record<string, VrmBonePose>): SkeletonAxes {
  const fallback: SkeletonAxes = {
    rAxis: X_AXIS.clone(),
    fAxis: Z_AXIS.clone(),
    leanSign: 1,
    legSignL: 1,
    pullL: new THREE.Quaternion().setFromAxisAngle(Z_AXIS, -d2r(66)),
    pullR: new THREE.Quaternion().setFromAxisAngle(Z_AXIS, d2r(66)),
    armSignL: 1,
    armSignR: -1,
  }
  const armL = bones.leftUpperArm
  const armL2 = bones.leftLowerArm
  const armR = bones.rightUpperArm
  const armR2 = bones.rightLowerArm
  if (!armL || !armL2 || !armR || !armR2) return fallback
  const pL = restWorldPos(armL)
  const pL2 = restWorldPos(armL2)
  const pR = restWorldPos(armR)
  const pR2 = restWorldPos(armR2)
  const r = pR.clone().lerp(pR2, 0.5).sub(pL.clone().lerp(pL2, 0.5))
  if (r.lengthSq() < 1e-6) return fallback
  r.normalize()
  const f = new THREE.Vector3().crossVectors(Y_UP, r)
  if (f.lengthSq() < 1e-6) return fallback
  f.normalize()
  const dirL = pL2.sub(pL)
  const dirR = pR2.sub(pR)
  if (dirL.lengthSq() < 1e-6 || dirR.lengthSq() < 1e-6) return fallback
  dirL.normalize()
  dirR.normalize()
  const rotToward = (fromDir: THREE.Vector3, toDir: THREE.Vector3, k: number) => {
    const axis = new THREE.Vector3().crossVectors(fromDir, toDir)
    if (axis.lengthSq() < 1e-8) return new THREE.Quaternion()
    axis.normalize()
    const angle = Math.acos(THREE.MathUtils.clamp(fromDir.dot(toDir), -1, 1)) * k
    return new THREE.Quaternion().setFromAxisAngle(axis, angle)
  }
  const legL = bones.leftUpperLeg
  const legL2 = bones.leftLowerLeg
  let legSignL = 1
  if (legL && legL2) {
    const td = restWorldPos(legL2).sub(restWorldPos(legL))
    if (td.lengthSq() > 1e-6) {
      legSignL = Math.sign(new THREE.Vector3().crossVectors(td.normalize(), f).dot(r)) || 1
    }
  }
  const armSignL = Math.sign(new THREE.Vector3().crossVectors(dirL, f).dot(r)) || 1
  const armSignR = Math.sign(new THREE.Vector3().crossVectors(dirR, f).dot(r)) || -1
  const leanSign = Math.sign(new THREE.Vector3().crossVectors(Y_UP, f).dot(r)) || 1
  return { rAxis: r, fAxis: f, leanSign, legSignL, pullL: rotToward(dirL, Y_DOWN, 0.85), pullR: rotToward(dirR, Y_DOWN, 0.85), armSignL, armSignR }
}

/** 模型面朝轴（自左右臂静止方向推导；面朝 +Z 时结果为 +Z，office frontRotation 无需修正）。 */
export function measureSkeletonAxes(info: VrmSkeletonInfo): SkeletonAxes {
  return measureAxes(info.bones)
}

/** 待机：轻微呼吸/重心摇曳，双臂自然下垂（下拉量按实测臂向计算）。 */
function bakeIdle(bones: Record<string, VrmBonePose>, ax: SkeletonAxes, height: number): THREE.AnimationClip | null {
  const b = (key: string) => bones[key]
  if (!b('spine')) return null
  const axq = (axis: THREE.Vector3, deg: number) => new THREE.Quaternion().setFromAxisAngle(axis, d2r(deg))
  return bakeClip('idle', 4, 48, (t, q, p) => {
    const w = t * Math.PI * 2
    const breathe = Math.sin(w)
    const slow = Math.sin(w * 0.5)
    const put = (key: string, delta: THREE.Quaternion) => { const bone = b(key); if (bone) q(bone, swingDelta(bone, delta)) }
    put('spine', axq(ax.rAxis, ax.leanSign * (2 + 1.2 * breathe)))
    put('chest', axq(ax.rAxis, ax.leanSign * 1.5 * breathe))
    put('neck', axq(ax.rAxis, ax.leanSign * 1.2 * Math.sin(w + 1.1)))
    put('head', axq(Y_UP, 2.5 * slow))
    put('head', axq(ax.rAxis, ax.leanSign * 1.5 * Math.sin(w * 0.5 + 0.7)))
    put('leftUpperArm', axq(ax.rAxis, ax.armSignL * 2 * Math.sin(w * 0.5 + 0.4)).multiply(ax.pullL))
    put('rightUpperArm', axq(ax.rAxis, ax.armSignR * 2 * Math.sin(w * 0.5 + 2.1)).multiply(ax.pullR))
    put('leftLowerArm', axq(ax.rAxis, ax.armSignL * 6))
    put('rightLowerArm', axq(ax.rAxis, ax.armSignR * 6))
    const hips = b('hips')
    if (hips) p(hips, hipsShiftedPos(hips, 0.004 * breathe, height))
  })
}

/** 步行：0.9s 一整步态周期，摆动/屈膝/摆臂全部绕实测左右轴。 */
function bakeWalk(bones: Record<string, VrmBonePose>, ax: SkeletonAxes, height: number): THREE.AnimationClip | null {
  const b = (key: string) => bones[key]
  if (!b('leftUpperLeg') || !b('rightUpperLeg')) return null
  const axq = (axis: THREE.Vector3, deg: number) => new THREE.Quaternion().setFromAxisAngle(axis, d2r(deg))
  return bakeClip('walk', 0.9, 36, (t, q, p) => {
    const w = t * Math.PI * 2
    const legL = Math.sin(w)
    const legR = Math.sin(w + Math.PI)
    const put = (key: string, delta: THREE.Quaternion) => { const bone = b(key); if (bone) q(bone, swingDelta(bone, delta)) }
    put('leftUpperLeg', axq(ax.rAxis, ax.legSignL * -26 * legL))
    put('rightUpperLeg', axq(ax.rAxis, -ax.legSignL * -26 * legR))
    put('leftLowerLeg', axq(ax.rAxis, -ax.legSignL * (6 + 30 * Math.max(0, Math.sin(w - 1.7)))))
    put('rightLowerLeg', axq(ax.rAxis, ax.legSignL * (6 + 30 * Math.max(0, Math.sin(w - 1.7)))))
    put('leftFoot', axq(ax.rAxis, ax.legSignL * 10 * Math.sin(w - 2.2)))
    put('rightFoot', axq(ax.rAxis, -ax.legSignL * 10 * Math.sin(w - 2.2)))
    put('spine', axq(Y_UP, -3 * legL))
    put('head', axq(Y_UP, 2 * Math.sin(w + Math.PI / 2)))
    put('leftUpperArm', axq(ax.rAxis, ax.armSignL * 16 * legL).multiply(ax.pullL))
    put('rightUpperArm', axq(ax.rAxis, ax.armSignR * 16 * legR).multiply(ax.pullR))
    put('leftLowerArm', axq(ax.rAxis, ax.armSignL * 4 * Math.sin(w + 0.8)))
    put('rightLowerArm', axq(ax.rAxis, ax.armSignR * 4 * Math.sin(w + 0.8 + Math.PI)))
    const hips = b('hips')
    if (hips) p(hips, hipsShiftedPos(hips, -0.01 + 0.02 * Math.abs(Math.cos(w)), height))
  })
}

/** 坐姿：大腿前抬+小腿垂下，髋部降到椅面高度，静态骨架加微小呼吸。 */
function bakeSit(bones: Record<string, VrmBonePose>, ax: SkeletonAxes, height: number): THREE.AnimationClip | null {
  const b = (key: string) => bones[key]
  if (!b('leftUpperLeg') || !b('hips')) return null
  const axq = (axis: THREE.Vector3, deg: number) => new THREE.Quaternion().setFromAxisAngle(axis, d2r(deg))
  return bakeClip('sit', 2.4, 24, (t, q, p) => {
    const s = Math.sin(t * Math.PI * 2)
    const sR = Math.sin(t * Math.PI * 2 + Math.PI)
    const put = (key: string, delta: THREE.Quaternion) => { const bone = b(key); if (bone) q(bone, swingDelta(bone, delta)) }
    put('leftUpperLeg', axq(ax.rAxis, ax.legSignL * (85 + 0.8 * s)))
    put('rightUpperLeg', axq(ax.rAxis, ax.legSignL * (85 + 0.8 * sR)))
    put('leftLowerLeg', axq(ax.rAxis, -ax.legSignL * (83 - 0.8 * s)))
    put('rightLowerLeg', axq(ax.rAxis, -ax.legSignL * (83 - 0.8 * sR)))
    put('leftFoot', axq(ax.rAxis, ax.legSignL * 2))
    put('rightFoot', axq(ax.rAxis, ax.legSignL * 2))
    put('hips', axq(ax.rAxis, -ax.leanSign * (12 + 0.8 * s)))
    put('spine', axq(ax.rAxis, ax.leanSign * 6))
    put('chest', axq(ax.rAxis, ax.leanSign * 3))
    put('neck', axq(ax.rAxis, ax.leanSign * 3))
    put('head', axq(ax.rAxis, ax.leanSign * (2 + 0.6 * s)))
    put('leftUpperArm', axq(ax.rAxis, ax.armSignL * 12).multiply(ax.pullL))
    put('rightUpperArm', axq(ax.rAxis, ax.armSignR * 12).multiply(ax.pullR))
    put('leftLowerArm', axq(ax.rAxis, ax.armSignL * 20))
    put('rightLowerArm', axq(ax.rAxis, ax.armSignR * 20))
    const hips = b('hips')
    if (hips) p(hips, hipsSeatedPos(hips, height))
  })
}

/** 烘焙三件套；缺关键骨骼时返回空数组（actor 系统对无动画路径已有兜底）。 */
export function createVrmClips(info: VrmSkeletonInfo): THREE.AnimationClip[] {
  const ax = measureAxes(info.bones)
  const clips = [bakeIdle(info.bones, ax, info.height), bakeWalk(info.bones, ax, info.height), bakeSit(info.bones, ax, info.height)]
  return clips.filter((clip): clip is THREE.AnimationClip => clip !== null)
}
