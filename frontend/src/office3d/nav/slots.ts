/**
 * 槽位（座位锚点）数学 —— 纯函数，无组件依赖。（R1 自 Office3DCanvas 抽出）
 * 坐标约定：rotation_y=0 时槽位朝向 +z；zones x 左负右正。
 */
import * as THREE from 'three'
import type { OfficeFurnitureItem } from '@/api/office'

export function slotPosition(slot: OfficeFurnitureItem): THREE.Vector3 {
  return new THREE.Vector3(slot.position?.x ?? 0, 0, slot.position?.z ?? 0)
}

export function slotRotationY(slot: OfficeFurnitureItem): number {
  return slot.rotation_y ?? 0
}

export function slotForward(slot: OfficeFurnitureItem): THREE.Vector3 {
  const rotation = slotRotationY(slot)
  return new THREE.Vector3(Math.sin(rotation), 0, Math.cos(rotation))
}

export function slotRight(slot: OfficeFurnitureItem): THREE.Vector3 {
  const rotation = slotRotationY(slot)
  return new THREE.Vector3(Math.cos(rotation), 0, -Math.sin(rotation))
}

export function slotPhase(slot: OfficeFurnitureItem): number {
  return slotRotationY(slot) + Math.PI
}

export function hashRoleKey(roleKey: string): number {
  let hash = 0
  for (let i = 0; i < roleKey.length; i += 1) {
    hash = (hash * 31 + roleKey.charCodeAt(i)) >>> 0
  }
  return hash
}
