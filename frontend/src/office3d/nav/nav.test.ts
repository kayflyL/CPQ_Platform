/**
 * 导航模块单测（R1）—— node 原生 test runner：
 *   node --test frontend/src/office3d/nav/nav.test.ts
 *
 * 锁住寻路正确性下限：blockedAt 三态（空地/家具/会议墙含门洞）、
 * findPath 直达/绕障/同格/不可达回退、smoothPath 拐点保留、
 * 槽位锚点数学（rotation_y=0 朝 +z）、meetingRoomBounds 三级回退与门口自动定向。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import * as THREE from 'three'
import { hashRoleKey, slotForward, slotPhase, slotPosition, slotRight, slotRotationY } from './slots.ts'
import { createNavWorld, type NavSource } from './world.ts'
import { findPath, smoothPath } from './path.ts'

function makeSource(over: Partial<NavSource> = {}): NavSource {
  return {
    floor: () => ({ width: 20, depth: 12 }),
    zones: () => [],
    furniture: () => [],
    furnitureSize: (_type, item) => ({ width: (item as any)?.w ?? 2, depth: (item as any)?.d ?? 1 }),
    ...over,
  }
}

function v3(x: number, z: number): THREE.Vector3 {
  return new THREE.Vector3(x, 0, z)
}

// ── 槽位数学 ──
test('slotForward/slotRight：rotation_y=0 朝 +z，右为 +x', () => {
  const slot: any = { id: 's', position: { x: 1, z: 2 }, rotation_y: 0 }
  assert.deepEqual(slotForward(slot).toArray().map((n) => +n.toFixed(9)), [0, 0, 1])
  assert.deepEqual(slotRight(slot).toArray().map((n) => +n.toFixed(9)), [1, 0, 0])
  assert.equal(slotRotationY(slot), 0)
  assert.equal(slotPhase(slot), Math.PI)
  assert.deepEqual(slotPosition(slot).toArray(), [1, 0, 2])
})

test('slotForward：rotation_y=π/2 朝 +x；缺省字段回退 0', () => {
  assert.deepEqual(slotForward({ rotation_y: Math.PI / 2 } as any).toArray().map((n) => +n.toFixed(9)), [1, 0, 0])
  assert.deepEqual(slotPosition({} as any).toArray(), [0, 0, 0])
})

test('hashRoleKey 确定性且无符号', () => {
  assert.equal(hashRoleKey('sales'), hashRoleKey('sales'))
  assert.notEqual(hashRoleKey('sales'), hashRoleKey('engineer'))
  assert.ok(hashRoleKey('任何key') >= 0)
})

// ── meetingRoomBounds 三级回退 ──
test('meetingRoomBounds：width/depth 优先', () => {
  const nav = createNavWorld(makeSource())
  const b = nav.meetingRoomBounds({ id: 'm', type: 'meeting', position: { x: 4, z: -2 }, width: 6, depth: 4 } as any)
  assert.deepEqual(b, { minX: 1, maxX: 7, minZ: -4, maxZ: 0 })
})

test('meetingRoomBounds：无尺寸时按家具座位外扩 1.35', () => {
  const nav = createNavWorld(makeSource({
    furniture: () => [
      { id: 'c1', type: 'meeting_chair', zoneId: 'm', seat: true, position: { x: 5, z: -5 } } as any,
      { id: 'c2', type: 'meeting_chair', zoneId: 'm', seat: true, position: { x: 7, z: -7 } } as any,
    ],
  }))
  const b = nav.meetingRoomBounds({ id: 'm', type: 'meeting', position: { x: 6, z: -6 } } as any)
  assert.deepEqual(b, { minX: 3.65, maxX: 8.35, minZ: -8.35, maxZ: -3.65 })
})

test('meetingRoomBounds：最终回退 radius（下限 2.2）', () => {
  const nav = createNavWorld(makeSource())
  const b = nav.meetingRoomBounds({ id: 'm', type: 'meeting', position: { x: 0, z: 0 }, radius: 1 } as any)
  assert.deepEqual(b, { minX: -2.2, maxX: 2.2, minZ: -2.2, maxZ: 2.2 })
})

// ── 门口自动定向（锁现状行为）──
test('meetingDoorSide：配置优先；自动按越界轴定向', () => {
  const nav = createNavWorld(makeSource()) // floor 20×12 → half 10/6
  assert.equal(nav.meetingDoorSide({ id: 'm', type: 'meeting', door: { side: 'back' } } as any), 'back')
  assert.equal(nav.meetingDoorSide({ id: 'm', type: 'meeting', position: { x: 0, z: 0 } } as any), 'left')
  assert.equal(nav.meetingDoorSide({ id: 'm', type: 'meeting', position: { x: 11, z: 0 } } as any), 'left')
  assert.equal(nav.meetingDoorSide({ id: 'm', type: 'meeting', position: { x: -11, z: 0 } } as any), 'right')
  assert.equal(nav.meetingDoorSide({ id: 'm', type: 'meeting', position: { x: 0, z: 7 } } as any), 'back')
  assert.equal(nav.meetingDoorSide({ id: 'm', type: 'meeting', position: { x: 0, z: -7 } } as any), 'front')
})

// ── blockedAt 三态 ──
test('blockedAt：家具阻挡，invalidate 后生效', () => {
  const furniture: any[] = []
  const nav = createNavWorld(makeSource({ furniture: () => furniture }))
  assert.equal(nav.blockedAt(0, 0), false)
  furniture.push({ id: 'd1', type: 'desk', position: { x: 0, z: 0 }, rotation_y: 0, w: 2, d: 1 })
  assert.equal(nav.blockedAt(0, 0), false, '未 invalidate 走旧网格，不应生效')
  nav.invalidate()
  assert.equal(nav.blockedAt(0, 0), true)
  nav.invalidate()
  assert.equal(nav.blockedAt(5, 5), false)
})

test('blockedAt：会议墙阻挡但门洞放行', () => {
  // 会议室中心 (6,-4) 4×3，门在 front（z=maxZ=-2.5），门宽 1.3 → 门洞 |x-6|<0.65
  const nav = createNavWorld(makeSource({
    zones: () => [{ id: 'm', type: 'meeting', position: { x: 6, z: -4 }, width: 4, depth: 3, door: { side: 'front', width: 1.3 } } as any],
  }))
  assert.equal(nav.blockedAt(4, -2.5), true, '门洞外撞墙')
  assert.equal(nav.blockedAt(6, -2.5), false, '门洞内放行')
  assert.equal(nav.blockedAt(6, -3.6), false, '房间内部不挡')
})

// ── findPath 四态 ──
test('findPath：直线畅通直接返回终点', () => {
  const nav = createNavWorld(makeSource())
  const path = findPath(nav, v3(-8, 4), v3(-8, -4))
  assert.equal(path.length, 1)
  assert.deepEqual(path[0].toArray(), [-8, 0, -4])
})

test('findPath：绕过桌子，路径点全部不撞障碍', () => {
  const nav = createNavWorld(makeSource({
    furniture: () => [{ id: 'd1', type: 'desk', position: { x: 0, z: 0 }, rotation_y: 0, w: 2, d: 1 } as any],
  }))
  const path = findPath(nav, v3(-4, 0), v3(4, 0))
  assert.ok(path.length >= 2, '应绕障而非直线')
  const end = path[path.length - 1]
  assert.ok(Math.abs(end.x - 4) < 1e-6 && Math.abs(end.z) < 1e-6, '终点应为目标点')
  for (const p of path) {
    // 桌子 2宽×1深 + 0.18 清障半径 → 内部判定 |x|<1.18 且 |z|<0.68
    const inside = Math.abs(p.x) < 1.18 && Math.abs(p.z) < 0.68
    assert.equal(inside, false, `路径点(${p.x},${p.z})落入桌子`)
  }
})

test('findPath：起终点同格直连（起点格被占也允许起步）', () => {
  const nav = createNavWorld(makeSource({
    furniture: () => [{ id: 'd1', type: 'desk', position: { x: 0, z: 0 }, rotation_y: 0, w: 2, d: 1 } as any],
  }))
  const path = findPath(nav, v3(0.05, 0.05), v3(0.1, 0.1))
  assert.equal(path.length, 1)
  assert.deepEqual(path[0].toArray(), [0.1, 0, 0.1])
})

test('findPath：终点不可达时回退到最近可达格而非直冲', () => {
  const nav = createNavWorld(makeSource({
    furniture: () => [{ id: 'big', type: 'meeting_table', position: { x: 0, z: 0 }, rotation_y: 0, w: 6, d: 6 } as any],
  }))
  const path = findPath(nav, v3(-8, 0), v3(0, 0))
  assert.ok(path.length >= 1)
  const end = path[path.length - 1]
  assert.ok(end.distanceTo(v3(0, 0)) > 1, '不应冲进障碍中心')
})

// ── smoothPath ──
test('smoothPath：空场折叠中间点，隔墙保留拐点', () => {
  const empty = createNavWorld(makeSource())
  const collapsed = smoothPath(empty, [v3(-1, 0), v3(-0.5, 0), v3(0.5, 0), v3(1, 0)])
  assert.equal(collapsed.length, 2)

  const walled = createNavWorld(makeSource({
    furniture: () => [{ id: 'wall', type: 'partition', position: { x: 0, z: 0 }, rotation_y: 0, w: 0.2, d: 6 } as any],
  }))
  const kept = smoothPath(walled, [v3(-1, 0), v3(-0.5, 0), v3(0.5, 0), v3(1, 0)])
  assert.equal(kept.length, 4)
})

// ── 门口路径点 / 地板夹持 ──
test('meetingDoorWaypoints：front 门在 maxZ 外外内两点', () => {
  const nav = createNavWorld(makeSource())
  const wps = nav.meetingDoorWaypoints({ id: 'm', type: 'meeting', position: { x: 6, z: -4 }, width: 4, depth: 3, door: { side: 'front' } } as any)
  assert.equal(wps.length, 2)
  assert.equal(wps[0].x, 6)
  assert.ok(Math.abs(wps[0].z - (-2.5 + 0.85)) < 1e-9)
  assert.ok(Math.abs(wps[1].z - (-2.5 - 0.85)) < 1e-9)
})

test('clampPointToFloor：按地板半宽收拢并归零 y', () => {
  const nav = createNavWorld(makeSource())
  const p = nav.clampPointToFloor(v3(100, 100))
  assert.equal(p.y, 0)
  assert.ok(Math.abs(p.x - (10 - 0.42)) < 1e-9)
  assert.ok(Math.abs(p.z - (6 - 0.42)) < 1e-9)
})

// ── 调试探针 ──
test('debug 关闭时不计数，开启时 astar/blocked 累加', () => {
  const quiet = createNavWorld(makeSource())
  findPath(quiet, v3(-8, 4), v3(-8, -4))
  assert.equal(quiet.stats.astar, 0)

  const noisy = createNavWorld(makeSource({ debug: () => true }))
  findPath(noisy, v3(-4, 0), v3(4, 0))
  assert.ok(noisy.stats.astar >= 1)
  assert.ok(noisy.stats.blocked >= 1)
  noisy.stats.astar = 0
  noisy.stats.blocked = 0
  assert.equal(noisy.stats.astar, 0)
})
