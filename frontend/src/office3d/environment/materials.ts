/**
 * 环境材质与阴影工具。（R3a 自 Office3DCanvas refactor 抽出）
 */
import * as THREE from 'three'
import { gradeEnv } from './surfaces.ts'

export function envMaterial(color: string, roughness = 0.82, metalness = 0.05): THREE.MeshStandardMaterial {
  const m = new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness, metalness })
  m.envMapIntensity = gradeEnv(metalness, roughness)
  return m
}

export function applyShadow(mesh: THREE.Mesh, castShadow = true, receiveShadow = true) {
  mesh.castShadow = castShadow
  mesh.receiveShadow = receiveShadow
}
