/**
 * 无动画的绑骨 GLB 兜底通道：自动生成的角色（Meshy/Tripo 等）常带骨架却不带动画。
 * 按常见自动绑骨命名定位人形骨骼，复用 vrmClips 的世界轴摆动烘焙器生成 idle/walk/sit。
 * 权重未归一化或 IBMs 与静止姿态不一致的文件在这里顺手矫正。
 */
import * as THREE from 'three'
import { createVrmClips, measureSkeletonAxes, type VrmBonePose, type VrmSkeletonInfo } from './vrmClips.ts'

/** 生成器骨骼名 → 烘焙器规范名。twist/手部等辅助骨骼不参与动画。 */
const BONE_NAME_MAP: Record<string, string> = {
  Hip: 'hips',
  Spine01: 'spine',
  Spine02: 'chest',
  Head: 'head',
  L_Upperarm: 'leftUpperArm',
  L_Forearm: 'leftLowerArm',
  R_Upperarm: 'rightUpperArm',
  R_Forearm: 'rightLowerArm',
  L_Thigh: 'leftUpperLeg',
  L_Calf: 'leftLowerLeg',
  R_Thigh: 'rightUpperLeg',
  R_Calf: 'rightLowerLeg',
  L_Foot: 'leftFoot',
  R_Foot: 'rightFoot',
  L_ToeBase: 'leftToes',
  R_ToeBase: 'rightToes',
}

function findSkinned(root: THREE.Object3D): THREE.SkinnedMesh | null {
  let found: THREE.SkinnedMesh | null = null
  root.traverse((c) => {
    const sm = c as THREE.SkinnedMesh
    if (!found && sm.isSkinnedMesh) found = sm
  })
  return found
}

export function extractGlbSkeletonInfo(root: THREE.Object3D): VrmSkeletonInfo | null {
  const skinned = findSkinned(root)
  if (!skinned) return null
  skinned.normalizeSkinWeights()
  root.updateMatrixWorld(true)
  const byName = new Map<string, THREE.Bone>()
  for (const b of skinned.skeleton.bones) {
    if (b.name && !byName.has(b.name)) byName.set(b.name, b)
  }
  const bones: Record<string, VrmBonePose> = {}
  for (const [raw, canonical] of Object.entries(BONE_NAME_MAP)) {
    const node = byName.get(raw)
    if (!node) continue
    const parent = node.parent
    bones[canonical] = {
      nodeName: node.name,
      restQuat: node.quaternion.clone(),
      parentWorldQuat: parent ? parent.getWorldQuaternion(new THREE.Quaternion()) : new THREE.Quaternion(),
      restPos: node.position.clone(),
      parentWorldPos: parent ? parent.getWorldPosition(new THREE.Vector3()) : new THREE.Vector3(),
    }
  }
  if (!bones.hips || !bones.spine || !bones.leftUpperLeg || !bones.rightUpperLeg) return null
  const size = new THREE.Vector3()
  new THREE.Box3().setFromObject(root).getSize(size)
  return { bones, height: size.y }
}

/**
 * 正面判定：优先脚尖方向（T-pose 正反对称，手臂推导五五开；脚尖永远朝前），
 * 无脚趾骨时退回手臂推导。返回绕 Y 轴的 frontRotation（把模型前向转到 +Z）。
 */
export function measureFrontRotation(info: VrmSkeletonInfo): number | null {
  const toes = info.bones.leftToes
  const foot = info.bones.leftFoot
  if (toes && foot) {
    const world = (b: VrmBonePose) => b.restPos.clone().applyQuaternion(b.parentWorldQuat).add(b.parentWorldPos)
    const dir = world(toes).sub(world(foot))
    if (dir.lengthSq() > 1e-8) {
      dir.y = 0
      if (dir.lengthSq() > 1e-8) return Math.atan2(-dir.x, dir.z)
    }
  }
  return null
}

/** 有蒙皮但零动画时生成程序化三件套；不可烘焙（无骨架/关键骨骼缺失）返回 null。
 * 同时按实测面朝方向计算 frontRotation（生成器导出的模型常不朝 +Z）。 */
export function bakeProceduralClipsIfMissing(scene: THREE.Group, animations: THREE.AnimationClip[]): { clips: THREE.AnimationClip[]; frontRotation: number } | null {
  if (animations.length) return null
  const info = extractGlbSkeletonInfo(scene)
  if (!info) return null
  const toeBased = measureFrontRotation(info)
  const frontRotation = toeBased !== null ? toeBased : (() => {
    const ax = measureSkeletonAxes(info)
    return Math.atan2(-ax.fAxis.x, ax.fAxis.z || 0.001)
  })()
  return { clips: createVrmClips(info), frontRotation }
}
