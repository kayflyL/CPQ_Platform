/**
 * 环境材质与阴影工具。（R3a 自 Office3DCanvas 抽出，逻辑逐行等价）
 */
import * as THREE from 'three'

export function envMaterial(color: string, roughness = 0.82, metalness = 0.05): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness, metalness })
}

export function applyShadow(mesh: THREE.Mesh, castShadow = true, receiveShadow = true) {
  mesh.castShadow = castShadow
  mesh.receiveShadow = receiveShadow
}
