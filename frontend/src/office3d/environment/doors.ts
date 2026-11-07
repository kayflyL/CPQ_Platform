/**
 * G3 门模型与门动画：铰链门板（木门/玻璃门）+ 「同事走近自动开、离开缓关」步进器。
 *
 * 门板挂在 hinge 组上（局部 +X 为门板展开方向），userData.door 记录关/开两个旋转角
 * 与门洞中点，userData.noMerge = true 让 mergeStatic 跳过——门要逐帧转动，
 * 烘进静态合并体就焊死了。场景重建后由调用方 collectDoors 重新收集，
 * tick 里 stepDoors 按 delta 阻尼逼近目标角。
 */
import * as THREE from 'three'
import { envMaterial, applyShadow } from './materials.ts'

/** 开门张角（弧度，~100°，向门洞所属房间内侧摆） */
export const DOOR_SWING = 1.75

/** 按门洞朝向推导铰链位置与关/开角（hinge 缩进 0.04 躲开门框立柱，门洞中点作触发圆心）。 */
export function sideDoorSpec(
  side: string,
  doorCenterX: number,
  doorCenterZ: number,
  minX: number,
  maxX: number,
  minZ: number,
  maxZ: number,
  width: number,
): { hx: number; hz: number; closed: number; open: number; cx: number; cz: number } {
  const j = 0.04
  if (side === 'back') return { hx: doorCenterX - width / 2 + j, hz: minZ, closed: 0, open: -DOOR_SWING, cx: doorCenterX, cz: minZ }
  if (side === 'front') return { hx: doorCenterX + width / 2 - j, hz: maxZ, closed: Math.PI, open: Math.PI - DOOR_SWING, cx: doorCenterX, cz: maxZ }
  if (side === 'left') return { hx: minX, hz: doorCenterZ - width / 2 + j, closed: -Math.PI / 2, open: -Math.PI / 2 + DOOR_SWING, cx: minX, cz: doorCenterZ }
  return { hx: maxX, hz: doorCenterZ + width / 2 - j, closed: Math.PI / 2, open: Math.PI / 2 + DOOR_SWING, cx: maxX, cz: doorCenterZ }
}

export interface DoorSpec {
  /** 铰链世界坐标 */
  hx: number
  hz: number
  /** 关门时门板指向（绕 Y 旋转角，门板沿局部 +X 展开） */
  closed: number
  /** 开门旋转角（含方向） */
  open: number
  /** 门洞中点（触发半径的圆心） */
  cx: number
  cz: number
  /** 门板长/高 */
  len: number
  height: number
  /** 木门板颜色；玻璃门时作门框收边色 */
  color: string
  /** 玻璃门板（会议室）：玻璃芯 + 四边框收边 */
  glass?: boolean
}

export function createDoor(spec: DoorSpec): THREE.Group {
  const hinge = new THREE.Group()
  hinge.name = 'door'
  hinge.position.set(spec.hx, 0, spec.hz)

  const frameMat = envMaterial(spec.color, 0.5, 0.2)
  const leafY = spec.height / 2 + 0.04
  if (spec.glass) {
    const glassMat = new THREE.MeshStandardMaterial({
      color: 0xbfe2f5,
      roughness: 0.08,
      metalness: 0.08,
      envMapIntensity: 0.5,
      transparent: true,
      opacity: 0.3,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
    const stileW = 0.06
    const railH = 0.2
    const innerL = spec.len - stileW * 2
    const innerH = spec.height - railH * 2
    const pane = new THREE.Mesh(new THREE.BoxGeometry(innerL, innerH, 0.05), glassMat)
    pane.position.set(stileW + innerL / 2, railH + innerH / 2 + 0.04, 0)
    hinge.add(pane)
    const bottom = new THREE.Mesh(new THREE.BoxGeometry(spec.len, railH, 0.07), frameMat)
    bottom.position.set(spec.len / 2, railH / 2 + 0.04, 0)
    applyShadow(bottom)
    hinge.add(bottom)
    const top = new THREE.Mesh(new THREE.BoxGeometry(spec.len, railH, 0.07), frameMat)
    top.position.set(spec.len / 2, railH + innerH + railH / 2 + 0.04, 0)
    applyShadow(top)
    hinge.add(top)
    for (const s of [0, 1]) {
      const stile = new THREE.Mesh(new THREE.BoxGeometry(stileW, spec.height, 0.07), frameMat)
      stile.position.set(s === 0 ? stileW / 2 : spec.len - stileW / 2, leafY, 0)
      applyShadow(stile)
      hinge.add(stile)
    }
  } else {
    const leaf = new THREE.Mesh(new THREE.BoxGeometry(spec.len, spec.height, 0.06), frameMat)
    leaf.position.set(spec.len / 2, leafY, 0)
    applyShadow(leaf)
    hinge.add(leaf)
  }

  const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.14, 10), frameMat)
  knob.rotation.x = Math.PI / 2
  knob.position.set(spec.len - 0.15, 1.0, 0)
  hinge.add(knob)

  hinge.userData.door = { closed: spec.closed, open: spec.open, cx: spec.cx, cz: spec.cz }
  hinge.userData.noMerge = true
  hinge.rotation.y = spec.closed
  return hinge
}

export interface DoorJoint {
  hinge: THREE.Group
  closed: number
  open: number
  current: number
  cx: number
  cz: number
}

/** 从场景树收集门铰链并复位到关门角（重建后旧引用作废，须重新收集）。 */
export function collectDoors(root: THREE.Object3D): DoorJoint[] {
  const out: DoorJoint[] = []
  root.traverse((obj) => {
    const door = obj.userData.door as { closed: number; open: number; cx: number; cz: number } | undefined
    if (!door || typeof door.closed !== 'number') return
    obj.rotation.y = door.closed
    out.push({ hinge: obj as THREE.Group, closed: door.closed, open: door.open, current: door.closed, cx: door.cx, cz: door.cz })
  })
  return out
}

const OPEN_DIST = 1.7
const CLOSE_LAMBDA = 4.5

/** 逐帧步进：有同事在门洞半径内 → 开，否则缓关。delta 用 tick 的帧间隔。 */
export function stepDoors(joints: DoorJoint[], actors: Array<{ x: number; z: number }>, delta: number) {
  for (const j of joints) {
    let near = false
    for (const p of actors) {
      if (Math.hypot(p.x - j.cx, p.z - j.cz) < OPEN_DIST) {
        near = true
        break
      }
    }
    j.current = THREE.MathUtils.damp(j.current, near ? j.open : j.closed, CLOSE_LAMBDA, Math.max(delta, 0.001))
    j.hinge.rotation.y = j.current
  }
}
