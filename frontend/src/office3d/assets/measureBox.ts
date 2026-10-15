/**
 * 模型世界尺寸精确测量（含 SkinnedMesh 蒙皮）。
 * 蒙皮 GLB 的普通包围盒是绑定位姿的塌缩值（曾差出 142 倍），
 * 必须用 precise=逐顶点世界坐标；独立成模块避免 gltfCache ⇄ vrmLoader 循环依赖。
 */
import * as THREE from 'three'

export function measurePrecise(root: THREE.Object3D): { height: number; depth: number } {
  const box = new THREE.Box3().setFromObject(root, true)
  const size = new THREE.Vector3()
  box.getSize(size)
  return { height: size.y, depth: size.z }
}
