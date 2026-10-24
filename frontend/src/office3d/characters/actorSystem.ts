/**
 * 角色系统（R4b 自 Office3DCanvas 抽出，逻辑逐行等价）：
 * Actor 生命周期 / 座位分配 / 状态→目标状态机 / 路由重算 / 资源释放。
 * 所有组件依赖（props/配置访问器/选中悬停态）经 ActorRuntime 注入，零 Vue 依赖。
 */
import * as THREE from 'three'
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js'
import type { BehaviorConfig, OfficeColleagueStatus, OfficeConfig, OfficeEnvironmentTheme, OfficeFurnitureItem, OfficeZone } from '@/api/office'
import { zoneSeats } from '../../composables/officeLayout.ts'
import type { NavWorld } from '../nav/world.ts'
import { findPath } from '../nav/path.ts'
import { hashRoleKey, slotForward, slotPhase, slotPosition, slotRight, slotRotationY } from '../nav/slots.ts'
import { DESK_CHAIR_OFFSET, DESK_IDLE_DISTANCE, DESK_WAIT_DISTANCE, DESK_WAIT_SIDE, DESK_WORK_DISTANCE, MEETING_CHAIR_BACK_REACH, MEETING_STAND_GAP, CHAIR_SEAT_HEIGHT, CHAIR_SEAT_BACK_OFFSET, SIT_BACK_LOCAL_Z } from './metrics.ts'
import { makeBubbleSprite, makeLabelSprite, drawBubble } from './sprites.ts'
import { createDesk } from '../environment/furniture.ts'
import { toonStyleEnabled, toonifyStandardMaterials } from '../environment/toonStyle.ts'
import type { CharacterAsset } from '../assets/gltfCache.ts'

type Actor = {
  roleKey: string
  group: THREE.Group
  character: THREE.Group
  desk: THREE.Group
  indicator: THREE.Mesh
  indicatorMat: THREE.MeshBasicMaterial
  monitorMat: THREE.MeshStandardMaterial
  selectionRing: THREE.Mesh
  basePosition: THREE.Vector3
  phase: number
  status: string
  bubbleSignature: string
  bubble: THREE.Sprite
  label: THREE.Sprite
  bubbleTexture: THREE.CanvasTexture
  bubbleCanvas: HTMLCanvasElement
  bubbleCtx: CanvasRenderingContext2D
  bubbleVisibleUntil: number
  bubbleOpacity: number
  targetPosition: THREE.Vector3
  walking: boolean
  mixer: THREE.AnimationMixer | null
  idleAction: THREE.AnimationAction | null
  walkAction: THREE.AnimationAction | null
  sitAction: THREE.AnimationAction | null
  halfDepth: number
  modelScale: number
  seatY: number
  /** 模型实测头顶高度（弹性锚定：名牌/气泡/状态球 Y 全部由此推导） */
  headY: number
  labelY: number
  bubbleY: number
  forward: THREE.Vector3
  right: THREE.Vector3
  homeZoneId: string
  homeSlot: Seat
  currentZoneId?: string | null
  targetZoneType?: string | null
  routeZone: OfficeZone | null
  lastPosX: number
  lastPosZ: number
  stuckFrames: number
  route: THREE.Vector3[]
  routeIndex: number
  walkTarget: THREE.Vector3
  armL?: THREE.Object3D | null
  armR?: THREE.Object3D | null
  legL?: THREE.Object3D | null
  legR?: THREE.Object3D | null
}

type Seat = OfficeFurnitureItem
export interface StatusMetaLike {
  animation?: string
  monitor_active?: boolean
  indicator_opacity?: number
  color?: string
  label?: string
}

export interface ActorRuntime {
  scene(): THREE.Scene | null
  colleagues(): any[]
  statusMap(): Record<string, OfficeColleagueStatus>
  furniture(): OfficeFurnitureItem[]
  zones(): OfficeZone[]
  config(): OfficeConfig
  behaviorConfig(): BehaviorConfig
  theme(): OfficeEnvironmentTheme
  statusMetaFor(status: string): StatusMetaLike
  statusColorHex(status: string): number
  statusTextFor(status: string): string
  selectedRoleKey(): string | null
  hoveredRoleKey(): string | null
  navWorld: NavWorld
  assets: { readonly assets: CharacterAsset[] }
}

export function createActorSystem(rt: ActorRuntime) {
  const navWorld = rt.navWorld
  const characterAssets = rt.assets
  const actorMap = new Map<string, Actor>()
  // 悬停/点击拾取目标（代理胶囊 + 头顶 HUD 精灵）与显示器膜（点击开任务板）。
  // rebuildActors 全量刷新；actorAtPointer 只打这些轻量对象，不碰蒙皮网格。
  const pickTargets: THREE.Object3D[] = []
  const monitorTargets: THREE.Mesh[] = []
  let routeFlushRaf = 0
  const pendingRouteZones = new Map<Actor, OfficeZone | null>()
  let meetingSlotAllocationCache: Map<string, Map<string, Seat>> | null = null
  const zoneById = (zoneId: string): OfficeZone | null => rt.zones().find((zone) => zone.id === zoneId) || null
  const deskZones = () => rt.zones().filter((zone) => zone.type === 'desk')

function deskSlotAssignments(): Map<string, { zone: OfficeZone; slot: Seat }> {
  const assignments = new Map<string, { zone: OfficeZone; slot: Seat }>()
  const freeSlots: Array<{ zone: OfficeZone; slot: Seat }> = []
  const roleKeys = new Set(rt.colleagues().map((colleague) => colleague.role_key))
  for (const zone of deskZones()) {
    for (const slot of zoneSeats(rt.furniture(), zone.id)) {
      if (slot.role_key && roleKeys.has(slot.role_key)) {
        assignments.set(slot.role_key, { zone, slot })
      } else {
        freeSlots.push({ zone, slot })
      }
    }
  }
  let cursor = 0
  for (const colleague of rt.colleagues()) {
    if (assignments.has(colleague.role_key)) continue
    const next = freeSlots[cursor % Math.max(1, freeSlots.length)]
    if (next) {
      assignments.set(colleague.role_key, next)
      cursor += 1
    }
  }
  return assignments
}

function fallbackDeskSlot(index: number): { zone: OfficeZone; slot: Seat } | null {
  const slots: Array<{ zone: OfficeZone; slot: Seat }> = []
  for (const zone of deskZones()) {
    for (const slot of zoneSeats(rt.furniture(), zone.id)) slots.push({ zone, slot })
  }
  return slots[index % Math.max(1, slots.length)] || null
}

function resolveZoneForStatus(roleKey: string, status: string, event?: OfficeColleagueStatus): OfficeZone | null {
  const officeEvent = event || rt.statusMap()[roleKey]
  const requestedZone = officeEvent?.zone || officeEvent?.intent
  if (requestedZone) return zoneById(requestedZone)
  const zoneId = rt.config().status_zone_map?.[status]
  return zoneId ? zoneById(zoneId) : null
}

/** 重建所有会议区的座位分配：只让“确实要去该会议区”的角色参与占座，按同事顺序依次分配空位，避免哈希撞座。 */
function rebuildMeetingSlotAllocation() {
  const cache = new Map<string, Map<string, Seat>>()
  for (const zone of rt.zones()) {
    if (zone.type !== 'meeting') continue
    const seats = zoneSeats(rt.furniture(), zone.id)
    if (!seats.length) continue
    const attendees = rt.colleagues().filter((colleague) => {
      const event = rt.statusMap()[colleague.role_key]
      return resolveZoneForStatus(colleague.role_key, event?.status || 'idle', event)?.id === zone.id
    })
    const allocation = new Map<string, Seat>()
    const taken = new Set<Seat>()
    for (const colleague of attendees) {
      const explicit = seats.find((slot) => slot.role_key === colleague.role_key)
      if (explicit && !taken.has(explicit)) {
        allocation.set(colleague.role_key, explicit)
        taken.add(explicit)
        continue
      }
      // 取第一个未被占用且未显式预留给其他角色的空位。
      const free = seats.find((slot) => !taken.has(slot) && !slot.role_key)
      if (free) {
        allocation.set(colleague.role_key, free)
        taken.add(free)
      } else {
        allocation.set(colleague.role_key, seats[attendees.indexOf(colleague) % seats.length])
      }
    }
    cache.set(zone.id, allocation)
  }
  meetingSlotAllocationCache = cache
}

function meetingSlotForActor(zone: OfficeZone, roleKey: string): Seat {
  const slots = zoneSeats(rt.furniture(), zone.id)
  if (!slots.length) return { id: 'meeting-fallback', position: zone.position || { x: 0, z: 0 }, rotation_y: 0 } as Seat
  if (!meetingSlotAllocationCache) rebuildMeetingSlotAllocation()
  const cache = meetingSlotAllocationCache as Map<string, Map<string, Seat>>
  const allocated = cache.get(zone.id)?.get(roleKey)
  if (allocated) return allocated
  const explicit = slots.find((slot) => slot.role_key === roleKey)
  if (explicit) return explicit
  return slots[hashRoleKey(roleKey) % slots.length]
}

function meetingPhaseForSlot(zone: OfficeZone, slot: Seat): number {
  const center = zone.position || { x: 0, z: 0 }
  const position = slotPosition(slot)
  return Math.atan2(center.x - position.x, center.z - position.z)
}
function createCharacter(colleague: any, position: THREE.Vector3) {
  const group = new THREE.Group()
  const charColor = new THREE.Color(colleague.color || '#1677ff')
  const skinColor = new THREE.Color('#f0c9a1')
  const bodyMat = new THREE.MeshStandardMaterial({ color: charColor, roughness: 0.72, metalness: 0.03 })
  const skinMat = new THREE.MeshStandardMaterial({ color: skinColor, roughness: 0.82, metalness: 0.01 })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x1d2530, roughness: 0.78, metalness: 0.04 })
  const shoeMat = new THREE.MeshStandardMaterial({ color: 0x11151c, roughness: 0.86, metalness: 0.04 })

  // 头：方块脸
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.52, 0.52), skinMat)
  head.position.y = 1.06
  head.castShadow = true
  group.add(head)

  // 身体：主题色方块上衣
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.64, 0.36), bodyMat)
  body.position.y = 0.48
  body.castShadow = true
  group.add(body)

  // 手臂
  const armGeo = new THREE.BoxGeometry(0.14, 0.5, 0.18)
  const armL = new THREE.Mesh(armGeo, bodyMat)
  armL.position.set(-0.36, 0.5, 0)
  armL.castShadow = true
  group.add(armL)
  const armR = new THREE.Mesh(armGeo, bodyMat)
  armR.position.set(0.36, 0.5, 0)
  armR.castShadow = true
  group.add(armR)

  // 腿
  const legGeo = new THREE.BoxGeometry(0.18, 0.18, 0.2)
  const legL = new THREE.Mesh(legGeo, shoeMat)
  legL.position.set(-0.16, 0.09, 0)
  group.add(legL)
  const legR = new THREE.Mesh(legGeo, shoeMat)
  legR.position.set(0.16, 0.09, 0)
  group.add(legR)

  // 脸：方块眼 + 细长嘴
  const faceZ = 0.275
  const eyeGeo = new THREE.BoxGeometry(0.1, 0.1, 0.03)
  const eyeL = new THREE.Mesh(eyeGeo, darkMat)
  eyeL.position.set(0.13, 1.13, faceZ)
  group.add(eyeL)
  const eyeR = new THREE.Mesh(eyeGeo, darkMat)
  eyeR.position.set(-0.13, 1.13, faceZ)
  group.add(eyeR)

  const mouth = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.035, 0.02), darkMat)
  mouth.position.set(0, 0.92, faceZ)
  group.add(mouth)

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.5, 0.6, 32),
    new THREE.MeshBasicMaterial({
      color: charColor,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  )
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.02
  ring.visible = false
  group.add(ring)

  const indicatorMat = new THREE.MeshBasicMaterial({ color: rt.statusColorHex('idle'), transparent: true, opacity: 0.9 })
  const indicator = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 12), indicatorMat)
  indicator.position.y = 1.62
  group.add(indicator)

  group.position.copy(position)
  group.userData.roleKey = colleague.role_key
  group.traverse((child) => {
    child.userData.roleKey = colleague.role_key
  })

  // 拾取代理：隐藏圆柱体包住身体。悬停/点击射线只打它（+头顶 HUD/显示器膜），
  // 不再递归打整只角色（蒙皮网格逐顶点求交很贵），见 actorAtPointer。
  const proxy = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 1.5, 8), new THREE.MeshBasicMaterial())
  proxy.position.y = 0.75
  proxy.visible = false
  proxy.userData.roleKey = colleague.role_key
  group.add(proxy)

  return {
    group, ring, indicator, indicatorMat,
    mixer: null, idleAction: null, walkAction: null, sitAction: null,
    halfDepth: 0.18, modelScale: 1, seatY: 0,
    armL, armR, legL, legR,
    headY: 1.42,
    proxy,
  }
}
function createCharacterFromTemplate(colleague: any, position: THREE.Vector3, template: CharacterAsset) {
  const group = new THREE.Group()
  const charColor = new THREE.Color(colleague.color || '#1677ff')
  const model = cloneSkeleton(template.scene)
  const targetHeight = 1.42
  const scale = targetHeight / (template.height || 2.5)

  model.scale.setScalar(scale)
  model.rotation.y = template.frontRotation

  // 二次校正：precise 实测（逐顶点世界坐标，含蒙皮）归一到 targetHeight，钳制防退化；
  // 不可用非 precise 包围盒——蒙皮 GLB 的普通包围盒是绑定位姿的塌缩值（曾差出 142 倍）。
  // 整段容错：VRM 碰撞体节点会在 updateWorldMatrix 里抛错，实测失败回退默认高度。
  try {
    const scaled = new THREE.Box3().setFromObject(model, true)
    const realHeight = scaled.max.y - scaled.min.y
    if (realHeight > 0.05) {
      const fix = THREE.MathUtils.clamp(targetHeight / realHeight, 0.1, 10)
      if (Math.abs(fix - 1) > 0.02) model.scale.multiplyScalar(fix)
    }
  } catch (e) {
    console.warn('[actorSystem] 模型归一化实测失败:', e)
  }

  const mixer = new THREE.AnimationMixer(model)
  const idleClip = template.animations.find((clip) => (clip.name || '').toLowerCase() === 'idle') || null
  const walkClip = template.animations.find((clip) => (clip.name || '').toLowerCase() === 'walk') || null
  const sitClip = template.animations.find((clip) => (clip.name || '').toLowerCase() === 'sit') || null
  const idleAction = idleClip ? mixer.clipAction(idleClip) : null
  let walkAction: THREE.AnimationAction | null = null
  if (walkClip) {
    const groundedTracks = walkClip.tracks.filter((track) => {
      const trackName = track.name || ''
      const targetNode = trackName.split('.')[0]
      const isPosition = trackName.includes('.position')
      return !(targetNode === 'root' && isPosition)
    })
    const groundedClip = new THREE.AnimationClip(`${walkClip.name}-grounded`, walkClip.duration, groundedTracks)
    walkAction = mixer.clipAction(groundedClip)
  }
  const sitAction = sitClip ? mixer.clipAction(sitClip) : null

  // headY 必须在骨骼摆出真实姿态后测：AI 生成模型的绑定位姿顶点云塌缩且悬空
  // （data-analyst.glb 绑定位姿曾测出 201，状态球/名牌悬空一个身位），
  // 播 idle 后的包围盒才是可见身体的真实头顶。钳制 [0.9, 2.0] 只拦退化值
  // （正常模型 idle 后 ≤1.45；data-analyst 骨架自带 0.41 悬空，实测 1.81 属合法高头顶）。
  let headY = targetHeight
  try {
    if (idleAction) {
      idleAction.play()
      mixer.update(0.5)
    }
    const box = new THREE.Box3().setFromObject(model, true)
    headY = THREE.MathUtils.clamp(box.max.y, 0.9, 2.0)
  } catch (e) {
    console.warn('[actorSystem] 模型头顶实测失败，回退默认高度:', e)
  }

  model.traverse((child: THREE.Object3D) => {
    child.userData.roleKey = colleague.role_key
    const mesh = child as THREE.Mesh
    if (mesh.isMesh) {
      // 标记为“与缓存模板共享的资源”，dispose 时交由模板缓存持有，不随 actor 释放。
      child.userData.templateShared = true
      mesh.castShadow = true
      mesh.receiveShadow = true
    }
  })
  // 三渲二统一：非 MToon 的标准材质换 toon 孪生（模块级按材质缓存，克隆间共享；
  // VRM 的 MToon 材质本来就是三渲二，不动）。?officeStyle=pbr 时整体关闭。
  if (toonStyleEnabled()) toonifyStandardMaterials(model)
  group.add(model)

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.5, 0.6, 32),
    new THREE.MeshBasicMaterial({
      color: charColor,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  )
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.02
  ring.visible = false
  group.add(ring)

  const indicatorMat = new THREE.MeshBasicMaterial({ color: rt.statusColorHex('idle'), transparent: true, opacity: 0.9 })
  const indicator = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 12), indicatorMat)
  indicator.position.y = headY + 0.16
  group.add(indicator)

  // 拾取代理：包住实测头顶，尺寸随模型归一高度自适应。
  const proxy = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, headY + 0.2, 8), new THREE.MeshBasicMaterial())
  proxy.position.y = (headY + 0.2) / 2
  proxy.visible = false
  proxy.userData.roleKey = colleague.role_key
  group.add(proxy)

  group.position.copy(position)
  group.userData.roleKey = colleague.role_key
  group.traverse((child) => {
    child.userData.roleKey = colleague.role_key
  })

  return {
    group, ring, indicator, indicatorMat,
    mixer, idleAction, walkAction, sitAction,
    halfDepth: (template.depth * scale) / 2, modelScale: scale, seatY: 0,
    armL: null, armR: null, legL: null, legR: null,
    headY,
    proxy,
  }
}

function rebuildActors() {
  const activeScene = rt.scene()
  if (!activeScene) return

  // 旧 actor 即将销毁，丢弃尚未执行的路由重算，避免引用悬空对象。
  if (routeFlushRaf) {
    cancelAnimationFrame(routeFlushRaf)
    routeFlushRaf = 0
  }
  pendingRouteZones.clear()

  for (const actor of actorMap.values()) {
    actor.mixer?.stopAllAction()
    activeScene.remove(actor.group)
    disposeActor(actor)
  }
  actorMap.clear()
  pickTargets.length = 0
  monitorTargets.length = 0

  const assignments = deskSlotAssignments()

  // 同事级专属模型：model_url 精确匹配的资产归该同事所有，并从轮换池剔除。
  const claimedAssets = new Map<string, CharacterAsset>()
  for (const colleague of rt.colleagues()) {
    const url = (colleague as { model_url?: string }).model_url
    if (!url) continue
    const asset = characterAssets.assets.find((candidate) => candidate.url === url)
    if (asset) claimedAssets.set(colleague.role_key, asset)
  }
  const claimedSet = new Set(claimedAssets.values())
  const pool = characterAssets.assets.filter((asset) => !claimedSet.has(asset))

  rt.colleagues().forEach((colleague, index) => {
    const assignment = assignments.get(colleague.role_key) || fallbackDeskSlot(index)
    if (!assignment) return

    const { slot } = assignment
    const deskPosition = slotPosition(slot)
    const forward = slotForward(slot)
    const right = slotRight(slot)
    // 桌子已由 buildProps 按家具配置渲染（scene 里叫 furniture-${slot.id}）：
    // 这里只挂接它的显示器材质/名牌/屏幕网格，不再重复建桌。
    // 旧逻辑每工位两张桌同位叠放：双倍 draw call + 桌面 z-fighting 闪烁。
    const envDesk = activeScene.getObjectByName(`furniture-${slot.id}`) as THREE.Group | null
    let monitorMat: THREE.MeshStandardMaterial | null = null
    const deskMonitorMeshes: THREE.Mesh[] = []
    if (envDesk) {
      envDesk.traverse((obj) => {
        const mesh = obj as THREE.Mesh
        if (!mesh.userData?.monitor) return
        mesh.userData.roleKey = colleague.role_key
        deskMonitorMeshes.push(mesh)
        const mat = mesh.material as THREE.MeshStandardMaterial
        if (mat && mat.polygonOffset) monitorMat = mat
      })
    }
    let deskGroup: THREE.Group
    let deskMonitorMat: THREE.MeshStandardMaterial
    if (envDesk && monitorMat) {
      deskGroup = envDesk
      deskMonitorMat = monitorMat
      // 名牌改染同事专属色（旧逻辑是建一张染色桌；现在桌子共用，改色即可）
      envDesk.traverse((obj) => {
        if (obj.userData?.nameplate) {
          ((obj as THREE.Mesh).material as THREE.MeshStandardMaterial).color.set(colleague.color || '#1677ff')
        }
      })
    } else {
      // 容错：找不到已渲染的桌（异常配置）时退回旧路径自建一张，绝不丢角色
      const desk = createDesk(colleague.color || '#1677ff', rt.theme())
      desk.group.position.copy(deskPosition)
      desk.group.rotation.y = slotRotationY(slot)
      deskGroup = desk.group
      deskMonitorMat = desk.monitorMat
    }

    const characterHome = deskPosition.clone().addScaledVector(forward, DESK_IDLE_DISTANCE)
    const claimed = claimedAssets.get(colleague.role_key) || null
    const template = claimed || (pool.length ? pool[index % pool.length] : null)
    // 单同事容错：一个模型炸掉只降级该同事（程序小人），绝不拖死整批角色。
    let character
    try {
      character = template
        ? createCharacterFromTemplate(colleague, characterHome, template)
        : createCharacter(colleague, characterHome)
    } catch (e) {
      console.error(`[actorSystem] 同事 ${colleague.role_key} 模型创建失败，降级程序小人:`, e)
      character = createCharacter(colleague, characterHome)
    }

    const group = new THREE.Group()
    group.name = `ai-colleague-${colleague.role_key}`
    group.userData.roleKey = colleague.role_key
    // 挂接现有桌时桌已在环境组里，只有自建兜底桌才需要加进角色组
    if (deskGroup !== envDesk) group.add(deskGroup)

    const bubble = makeBubbleSprite(character.headY + 0.1)
    bubble.sprite.userData.roleKey = colleague.role_key
    character.group.add(bubble.sprite)
    group.add(character.group)

    const label = makeLabelSprite(colleague.name || colleague.role_key, colleague.color || '#1677ff', character.headY + 0.42)
    label.sprite.userData.roleKey = colleague.role_key
    character.group.add(label.sprite)

    activeScene.add(group)

    actorMap.set(colleague.role_key, {
      roleKey: colleague.role_key,
      group,
      character: character.group,
      desk: deskGroup,
      indicator: character.indicator,
      indicatorMat: character.indicatorMat,
      monitorMat: deskMonitorMat,
      selectionRing: character.ring,
      basePosition: deskPosition.clone(),
      phase: slotPhase(slot),
      status: 'idle',
      bubbleSignature: '',
      bubble: bubble.sprite,
      label: label.sprite,
      bubbleTexture: bubble.texture,
      bubbleCanvas: bubble.canvas,
      bubbleCtx: bubble.ctx,
      bubbleVisibleUntil: 0,
      bubbleOpacity: 0,
      targetPosition: characterHome.clone(),
      routeZone: null,
      lastPosX: characterHome.x,
      lastPosZ: characterHome.z,
      stuckFrames: 0,
      route: [],
      routeIndex: 0,
      walkTarget: characterHome.clone(),
      walking: false,
      mixer: character.mixer,
      idleAction: character.idleAction,
      headY: character.headY,
      labelY: character.headY + 0.42,
      bubbleY: character.headY + 0.1,
      walkAction: character.walkAction,
      sitAction: character.sitAction,
      halfDepth: character.halfDepth,
      modelScale: character.modelScale,
      seatY: character.seatY,
      armL: character.armL,
      armR: character.armR,
      legL: character.legL,
      legR: character.legR,
      forward,
      right,
      homeZoneId: assignment.zone.id,
      homeSlot: slot,
      currentZoneId: assignment.zone.id,
    })

    pickTargets.push(character.proxy, bubble.sprite, label.sprite)
    monitorTargets.push(...deskMonitorMeshes)
  })

  applyStatuses()
  updateSelection()
}

function applyStatuses() {
  rebuildMeetingSlotAllocation()
  for (const actor of actorMap.values()) {
    updateActorStatus(actor, rt.statusMap()[actor.roleKey])
  }
  scheduleRouteRecompute()
}

/** 把已入队的 actor 路由重算合并到下一帧执行，避免同一帧多次推送导致全量 A*。 */
function scheduleRouteRecompute() {
  if (routeFlushRaf || !pendingRouteZones.size) return
  const stepOne = () => {
    routeFlushRaf = 0
    const next = pendingRouteZones.keys().next()
    if (next.done) return
    const actor = next.value
    const zone = pendingRouteZones.get(actor) ?? null
    pendingRouteZones.delete(actor)
    rebuildActorRoute(actor, zone)
    if (pendingRouteZones.size) {
      routeFlushRaf = requestAnimationFrame(stepOne)
    }
  }
  routeFlushRaf = requestAnimationFrame(stepOne)
}

function assignmentActionFor(event?: OfficeColleagueStatus): string {
  const actionMap = rt.behaviorConfig().mission?.assignment_action_map || {}
  const assignmentStatus = event?.assignment_status || ''
  return typeof actionMap[assignmentStatus] === 'string' ? actionMap[assignmentStatus] : ''
}

function updateActorStatus(actor: Actor, event?: OfficeColleagueStatus) {
  const status = event?.status || 'idle'
  const activity = event?.activity || ''
  const message = event?.message || ''
  const bubbleSig = `${status}|${activity}|${message}`
  actor.status = status
  const meta = rt.statusMetaFor(status)
  const hex = rt.statusColorHex(status)
  actor.indicatorMat.color.setHex(hex)

  if (meta.monitor_active) {
    actor.monitorMat.emissive = new THREE.Color(hex)
    actor.monitorMat.emissiveIntensity = 0.75
  } else {
    actor.monitorMat.emissive = new THREE.Color(0x05080f)
    actor.monitorMat.emissiveIntensity = 0.25
  }

  actor.indicatorMat.opacity = typeof meta.indicator_opacity === 'number' ? meta.indicator_opacity : 0.9

  updateActorTarget(actor, status, event)
  // 只在气泡内容真正变化时重绘 512×128 canvas，避免每次 applyStatuses 全量重绘造成卡顿。
  if (bubbleSig !== actor.bubbleSignature) {
    drawBubble(actor, activity, message, rt.statusColorHex(status), rt.statusTextFor(status))
    actor.bubbleSignature = bubbleSig
    // 事件气泡：内容变化时闪现 6 秒，由 updateOverheads 淡出
    actor.bubbleVisibleUntil = performance.now() + 6000
  }
}

/** 头顶信息三层策略：事件气泡闪现 6s 淡出；等待输入/异常持续显示；悬停角色常显。
 * 状态信标的位置/缩放由 tick 的弹性锚定与状态动画驱动，此处不碰。 */
function updateOverheads(now: number) {
  const hoverKey = rt.hoveredRoleKey()
  for (const actor of actorMap.values()) {
    const persistent = actor.status === 'waiting_input' || actor.status === 'error'
    const target = hoverKey === actor.roleKey || persistent || now < actor.bubbleVisibleUntil ? 1 : 0
    const next = actor.bubbleOpacity + (target - actor.bubbleOpacity) * 0.14
    actor.bubbleOpacity = next
    actor.bubble.material.opacity = next
    actor.bubble.visible = next > 0.02
  }
}

function updateActorTarget(actor: Actor, status: string, event?: OfficeColleagueStatus) {
  const targetZone = resolveZoneForStatus(actor.roleKey, status, event)
  const action = assignmentActionFor(event)

  const prevPosition = actor.targetPosition
  const prevZoneType = actor.targetZoneType
  const prevZoneId = actor.currentZoneId
  const prevPhase = actor.phase

  if (action === 'return_to_desk' || action === 'sit_idle' || action === 'show_error') {
    setHomeDeskTarget(actor, status)
  } else if (targetZone?.type === 'meeting') {
    setMeetingTarget(actor, targetZone)
  } else if (targetZone?.walk_target === 'center') {
    setOfficeCenterTarget(actor, targetZone)
  } else if (targetZone?.walk_target === 'slot' || action === 'walk_to_target') {
    setDeskRouteTarget(actor, targetZone)
  } else {
    setHomeDeskTarget(actor, status)
  }

  // 只在终点真正变化时才重算路径：仅 message/颜色/bubble 变化不会触发 A*。
  if (destinationChanged(prevPosition, prevZoneType, prevZoneId, prevPhase, actor)) {
    pendingRouteZones.set(actor, targetZone)
  }
}

/** 判断目标的落点 / 归属区域 / 朝向是否相对上一状态发生了变化。 */
function destinationChanged(
  prevPosition: THREE.Vector3,
  prevZoneType: string | null | undefined,
  prevZoneId: string | null | undefined,
  prevPhase: number,
  actor: Actor,
): boolean {
  const next = actor.targetPosition
  return (
    Math.abs(prevPosition.x - next.x) > 1e-4 ||
    Math.abs(prevPosition.z - next.z) > 1e-4 ||
    prevZoneType !== actor.targetZoneType ||
    prevZoneId !== actor.currentZoneId ||
    prevPhase !== actor.phase
  )
}

function setHomeDeskTarget(actor: Actor, status: string) {
  const animation = rt.statusMetaFor(status).animation || 'idle'
  const base = actor.basePosition
  const forward = actor.forward
  const right = actor.right

  if (animation === 'working' && actor.sitAction) {
    const chairPosition = base.clone().addScaledVector(forward, DESK_CHAIR_OFFSET)
    const backReachWorld = SIT_BACK_LOCAL_Z
    const backOffset = Math.max(0, CHAIR_SEAT_BACK_OFFSET - backReachWorld)
    actor.seatY = CHAIR_SEAT_HEIGHT - 0.02
    actor.targetZoneType = 'desk_work'
    actor.targetPosition = chairPosition
      .clone()
      .addScaledVector(forward, backOffset)
  } else {
    actor.seatY = 0
    actor.targetZoneType = null
    if (animation === 'working') {
      actor.targetPosition = base.clone().addScaledVector(forward, DESK_WORK_DISTANCE)
    } else if (animation === 'waiting') {
      actor.targetPosition = base
        .clone()
        .addScaledVector(forward, DESK_WAIT_DISTANCE)
        .addScaledVector(right, DESK_WAIT_SIDE)
    } else {
      actor.targetPosition = base.clone().addScaledVector(forward, DESK_IDLE_DISTANCE)
    }
  }

  actor.phase = slotPhase(actor.homeSlot)
  actor.currentZoneId = actor.homeZoneId
}

function setMeetingTarget(actor: Actor, targetZone: OfficeZone) {
  const slot = meetingSlotForActor(targetZone, actor.roleKey)
  const chairPosition = slotPosition(slot)
  const zoneCenter = new THREE.Vector3(targetZone.position?.x ?? 0, 0, targetZone.position?.z ?? 0)
  const away = chairPosition.clone().sub(zoneCenter)
  if (away.lengthSq() < 0.001) away.set(0, 0, 1)
  away.normalize()

  actor.targetZoneType = 'meeting'
  if (actor.sitAction) {
    actor.seatY = CHAIR_SEAT_HEIGHT - 0.02
    const backReachWorld = SIT_BACK_LOCAL_Z
    actor.targetPosition = chairPosition
      .clone()
      .addScaledVector(away, CHAIR_SEAT_BACK_OFFSET - backReachWorld)
  } else {
    actor.seatY = 0
    const standDistance = MEETING_CHAIR_BACK_REACH + actor.halfDepth + MEETING_STAND_GAP
    actor.targetPosition = chairPosition.clone().addScaledVector(away, standDistance)
  }
  actor.phase = meetingPhaseForSlot(targetZone, slot)
  actor.currentZoneId = targetZone.id
}

function deskRouteSlotForActor(actor: Actor, targetZone: OfficeZone | null): Seat {
  const slots = targetZone ? zoneSeats(rt.furniture(), targetZone.id) : []
  if (!slots.length) return actor.homeSlot
  const alternatives = slots.filter((slot) => slot.id !== actor.homeSlot.id)
  const pool = alternatives.length ? alternatives : slots
  return pool[hashRoleKey(actor.roleKey) % pool.length]
}

function setDeskRouteTarget(actor: Actor, targetZone: OfficeZone | null) {
  const zone = targetZone || zoneById(actor.homeZoneId)
  const slot = deskRouteSlotForActor(actor, zone)
  const position = slotPosition(slot)
  actor.seatY = 0
  actor.targetZoneType = zone?.type || null
  actor.targetPosition = position.clone().addScaledVector(slotForward(slot), DESK_IDLE_DISTANCE)
  actor.phase = slotPhase(slot)
  actor.currentZoneId = zone?.id || actor.homeZoneId
}

function setOfficeCenterTarget(actor: Actor, targetZone: OfficeZone | null) {
  const zone = targetZone || zoneById(actor.homeZoneId)
  const center = zone?.position
    ? new THREE.Vector3(zone.position.x ?? 0, 0, zone.position.z ?? 0)
    : actor.basePosition.clone()
  actor.seatY = 0
  actor.targetZoneType = zone?.type || null
  actor.targetPosition = center
  actor.phase = slotPhase(actor.homeSlot)
  actor.currentZoneId = zone?.id || actor.homeZoneId
}

function rebuildActorRoute(actor: Actor, targetZone: OfficeZone | null) {
  const start = navWorld.clampPointToFloor(actor.character.position.clone())
  const target = navWorld.clampPointToFloor(actor.targetPosition)
  const chain: THREE.Vector3[] = []
  if (targetZone?.type === 'meeting') {
    chain.push(...navWorld.meetingDoorWaypoints(targetZone).map(navWorld.clampPointToFloor))
  }
  chain.push(target)
  const route: THREE.Vector3[] = []
  let prev = start
  for (const wp of chain) {
    const seg = findPath(navWorld, prev, wp)
    for (const p of seg) {
      if (!route.length || p.distanceTo(route[route.length - 1]) > 0.02) route.push(p)
    }
    prev = wp
  }
  if (!route.length) route.push(target)
  actor.route = route
  actor.routeIndex = 0
  actor.walkTarget = actor.route[0] || target
  actor.routeZone = targetZone
  actor.stuckFrames = 0
  actor.lastPosX = actor.character.position.x
  actor.lastPosZ = actor.character.position.z
}

function updateSelection() {
  for (const actor of actorMap.values()) {
    actor.selectionRing.visible = actor.roleKey === rt.selectedRoleKey()
    actor.label.visible = actor.roleKey === rt.selectedRoleKey() || actor.roleKey === rt.hoveredRoleKey()
  }
}

function disposeActor(actor: Actor) {
  actor.group.traverse((obj) => {
    const mesh = obj as THREE.Mesh
    // 模板克隆的 mesh 与缓存模板共享 geometry/material，资源交由模板缓存持有。
    if (mesh.userData.templateShared) return
    if (mesh.geometry) mesh.geometry.dispose()
    const material = (mesh as any).material
    if (Array.isArray(material)) material.forEach(disposeMaterial)
    else if (material) disposeMaterial(material)
  })
}

function disposeMaterial(material: THREE.Material) {
  const anyMat = material as any
  for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'alphaMap']) {
    anyMat[key]?.dispose?.()
  }
  material.dispose()
}
  return {
    actorMap,
    rebuildActors,
    applyStatuses,
    updateSelection,
    updateActorStatus,
    rebuildActorRoute,
    scheduleRouteRecompute,
    updateOverheads,
    meetingSlotForActor,
    pickTargets: () => [...pickTargets],
    monitorTargets: () => [...monitorTargets],
    disposeActor,
    disposeMaterial,
    cancelPendingRoutes() {
      if (routeFlushRaf) {
        cancelAnimationFrame(routeFlushRaf)
        routeFlushRaf = 0
      }
      pendingRouteZones.clear()
    },
  }
}
