/**
 * officeLayout 纯逻辑单测 —— node 原生 test runner（R0 测试跑道验证）：
 *   node --test frontend/src/composables/officeLayout.test.ts
 *
 * 锁住布局归一化的正确性下限：roomBounds 三级回退、zoneAt 最小房间优先、
 * normalizeOfficeConfig 的旧模型迁移（slots→furniture）幂等性、会议桌补齐与朝向。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { normalizeOfficeConfig, roomBounds, zoneAt } from './officeLayout.ts'

// ── roomBounds：width/depth 优先 ──
test('roomBounds 用 width/depth 求中心对称 bounds', () => {
  const b = roomBounds({ id: 'z', type: 'meeting', room: true, position: { x: 4, z: -2 }, width: 6, depth: 4 } as any)
  assert.deepEqual(b, { minX: 1, maxX: 7, minZ: -4, maxZ: 0 })
})

test('roomBounds 无 width/depth 时按座位分布外扩 1.35', () => {
  const zone: any = { id: 'z', type: 'desk', room: true, position: { x: 0, z: 0 }, slots: [
    { id: 's1', position: { x: -2, z: 1 } },
    { id: 's2', position: { x: 2, z: 1 } },
  ] }
  const b = roomBounds(zone)
  assert.equal(b.minX, -2 - 1.35)
  assert.equal(b.maxX, 2 + 1.35)
  assert.equal(b.minZ, 1 - 1.35)
  assert.equal(b.maxZ, 1 + 1.35)
})

test('roomBounds 最终回退 radius（缺省 3.2，下限 2.2）', () => {
  const small = roomBounds({ id: 'a', type: 'meeting', room: true, position: { x: 0, z: 0 }, radius: 1 } as any)
  assert.deepEqual(small, { minX: -2.2, maxX: 2.2, minZ: -2.2, maxZ: 2.2 })
  const big = roomBounds({ id: 'b', type: 'meeting', room: true, position: { x: 0, z: 0 }, radius: 5 } as any)
  assert.deepEqual(big, { minX: -5, maxX: 5, minZ: -5, maxZ: 5 })
})

// ── zoneAt：嵌套房间取面积最小者 ──
test('zoneAt 嵌套房间取小房间，界外返回 null', () => {
  const config: any = {
    zones: [
      { id: 'big', type: 'meeting', room: true, position: { x: 0, z: 0 }, width: 20, depth: 20 },
      { id: 'small', type: 'meeting', room: true, position: { x: 0, z: 0 }, width: 4, depth: 4 },
      { id: 'loose', type: 'lounge', position: { x: 0, z: 0 }, width: 30, depth: 30 }, // 非 room，不参与
    ],
  }
  assert.equal(zoneAt(config, 0.1, 0.1)?.id, 'small')
  assert.equal(zoneAt(config, 8, 8)?.id, 'big')
  assert.equal(zoneAt(config, 15, 15), null)
})

// ── normalizeOfficeConfig：旧模型迁移 ──
function legacyConfig(): any {
  return {
    zones: [
      { id: 'desk_zone', type: 'desk', room: true, position: { x: 0, z: 0 }, width: 10, depth: 8, slots: [
        { id: 's1', position: { x: -2, z: 2 }, rotation_y: 0.5, role_key: 'sales' },
        { id: 's2', position: { x: 2, z: 2 } },
      ] },
      { id: 'meeting_room', type: 'meeting', room: true, position: { x: 6, z: -6 }, slots: [
        { id: 'm1', position: { x: 5, z: -5 } },
        { id: 'm2', position: { x: 7, z: -7 } },
      ] },
    ],
    furniture: [],
  }
}

test('normalizeOfficeConfig 把 zone.slots 迁移为 furniture 并按 zone 类型定座位类型', () => {
  const cfg = legacyConfig()
  normalizeOfficeConfig(cfg)
  assert.equal(cfg.zones[0].slots.length, 0)
  const desk = cfg.furniture.filter((f: any) => f.zoneId === 'desk_zone')
  assert.equal(desk.length, 2)
  assert.ok(desk.every((f: any) => f.type === 'desk' && f.seat === true))
  assert.equal(desk.find((f: any) => f.id === 's1')?.role_key, 'sales')
  const meet = cfg.furniture.filter((f: any) => f.zoneId === 'meeting_room')
  assert.ok(meet.filter((f: any) => f.type === 'meeting_chair').length === 2)
  // 会议房自动补一张长桌
  assert.ok(meet.some((f: any) => f.type === 'meeting_table' && f.id === 'table-meeting_room'))
  // 会议椅朝向桌心
  const m1 = meet.find((f: any) => f.id === 'm1')
  assert.ok(Math.abs(m1.rotation_y - Math.atan2(6 - 5, -6 - -5)) < 1e-9)
})

test('normalizeOfficeConfig 幂等：重复调用不产生重复家具', () => {
  const cfg = legacyConfig()
  normalizeOfficeConfig(cfg)
  const afterFirst = cfg.furniture.length
  normalizeOfficeConfig(cfg)
  assert.equal(cfg.furniture.length, afterFirst)
})

test('normalizeOfficeConfig 补全缺 width/depth 房间的 bounds 与中心', () => {
  const cfg: any = { zones: [{ id: 'r', type: 'meeting', room: true, slots: [
    { id: 'a', position: { x: 1, z: 1 } },
    { id: 'b', position: { x: 3, z: 5 } },
  ] }], furniture: [] }
  normalizeOfficeConfig(cfg)
  const zone = cfg.zones[0]
  assert.deepEqual(zone.position, { x: 2, z: 3 })
  assert.equal(zone.width, 4) // span 2 + 2.0
  assert.equal(zone.depth, 6)
})
