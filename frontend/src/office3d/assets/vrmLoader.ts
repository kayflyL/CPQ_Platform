/**
 * VRM 角色加载器（F2 · CharacterAsset 第二实现）。
 * - VRM0/VRM1 经 rotateVRM0 统一朝 +Z（与 GLB 模板约定一致，frontRotation=0）。
 * - VRM 文件内不带动画：在 T-pose 静止姿态上程序化烘焙 idle/walk/sit（见 vrmClips）。
 * - pilot 不调用 vrm.update（弹簧骨骼/表情静止），动画直接驱动原始骨骼节点，
 *   因此 SkeletonUtils 克隆 + AnimationMixer 路径与 GLB 模板完全一致。
 */
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import type { VRMHumanBoneName } from '@pixiv/three-vrm'
import type { CharacterAsset } from './gltfCache.ts'
import { createVrmClips, type VrmBonePose, type VrmSkeletonInfo } from './vrmClips.ts'

const ANIMATED_BONES = [
  'hips', 'spine', 'chest', 'neck', 'head',
  'leftUpperArm', 'leftLowerArm', 'rightUpperArm', 'rightLowerArm',
  'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg',
  'leftFoot', 'rightFoot',
] as const

/** 从静止姿态场景提取烘焙所需骨骼信息（世界量取自父级，供世界轴摆动换算）。 */
function extractSkeletonInfo(root: THREE.Object3D, humanoid: { getRawBoneNode(name: VRMHumanBoneName): THREE.Object3D | null }): VrmSkeletonInfo {
  root.updateMatrixWorld(true)
  const bones: Record<string, VrmBonePose> = {}
  for (const canonical of ANIMATED_BONES) {
    const node = humanoid.getRawBoneNode(canonical)
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
  const size = new THREE.Vector3()
  new THREE.Box3().setFromObject(root).getSize(size)
  return { bones, height: size.y }
}

export async function loadVrmCharacter(url: string): Promise<CharacterAsset> {
  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))
  const gltf = await loader.loadAsync(url)
  const vrm = (gltf.userData as { vrm?: { humanoid: Parameters<typeof extractSkeletonInfo>[1] } }).vrm
  if (!vrm) throw new Error(`VRM 解析失败（userData.vrm 缺失，是否为合法 .vrm 文件？）: ${url}`)
  VRMUtils.removeUnnecessaryVertices(gltf.scene)
  VRMUtils.combineSkeletons(gltf.scene)
  VRMUtils.rotateVRM0(vrm as never)
  const info = extractSkeletonInfo(gltf.scene, vrm.humanoid)
  const animations = createVrmClips(info)
  const size = new THREE.Vector3()
  new THREE.Box3().setFromObject(gltf.scene).getSize(size)
  return { scene: gltf.scene, animations, height: size.y || 1.5, depth: size.z || 0.45, frontRotation: 0 }
}
