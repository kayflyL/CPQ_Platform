/**
 * vrmClips 烘焙逻辑单测（node --test，Node 原生 TS 剥离）。
 * 合成骨骼信息（单位静止姿态）断言轨道生成与坐姿降髋纯逻辑。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import * as THREE from 'three'
import { createVrmClips, type VrmSkeletonInfo, type VrmBonePose } from './vrmClips.ts'

function fakeBone(name: string, restY = 0): VrmBonePose {
  return {
    nodeName: name,
    restQuat: new THREE.Quaternion(),
    parentWorldQuat: new THREE.Quaternion(),
    restPos: new THREE.Vector3(0, restY, 0),
    parentWorldPos: new THREE.Vector3(),
  }
}

function fakeInfo(): VrmSkeletonInfo {
  const names = ['hips', 'spine', 'chest', 'neck', 'head',
    'leftUpperArm', 'leftLowerArm', 'rightUpperArm', 'rightLowerArm',
    'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg', 'leftFoot', 'rightFoot']
  const bones: Record<string, VrmBonePose> = {}
  for (const name of names) bones[name] = fakeBone(name, name === 'hips' ? 0.87 : 0)
  return { bones, height: 1.5 }
}

test('vrmClips: 三段 clip 命名与轨道齐全', () => {
  const clips = createVrmClips(fakeInfo())
  assert.equal(clips.length, 3)
  assert.deepEqual(clips.map((c) => c.name).sort(), ['idle', 'sit', 'walk'])
  const walk = clips.find((c) => c.name === 'walk')!
  const trackNames = walk.tracks.map((t) => t.name)
  assert.ok(trackNames.includes('hips.position'))
  assert.ok(trackNames.includes('leftUpperLeg.quaternion'))
  assert.ok(trackNames.includes('rightUpperArm.quaternion'))
})

test('vrmClips: 关键骨骼缺失时优雅降级', () => {
  assert.deepEqual(createVrmClips({ bones: {}, height: 1.5 }), [])
  const partial = createVrmClips({ bones: { hips: fakeBone('Hips') }, height: 1.5 })
  assert.deepEqual(partial, [])
  const idleOnly = createVrmClips({ bones: { spine: fakeBone('Spine'), hips: fakeBone('Hips') }, height: 1.5 })
  assert.equal(idleOnly.length, 1)
  assert.equal(idleOnly[0].name, 'idle')
})

test('vrmClips: 坐姿降髋、步行髋部浮动', () => {
  const clips = createVrmClips(fakeInfo())
  const sit = clips.find((c) => c.name === 'sit')!
  const hipsTrack = sit.tracks.find((t) => t.name === 'hips.position')!
  const data = hipsTrack.values as unknown as Float32Array
  let maxSitY = -Infinity
  for (let i = 1; i < data.length; i += 3) maxSitY = Math.max(maxSitY, data[i])
  assert.ok(maxSitY < 0.12, `坐姿髋部应低于 0.12，实际 ${maxSitY}`)

  const walk = clips.find((c) => c.name === 'walk')!
  const walkHips = walk.tracks.find((t) => t.name === 'hips.position')!
  const wd = walkHips.values as unknown as Float32Array
  let minY = Infinity
  let maxY = -Infinity
  for (let i = 1; i < wd.length; i += 3) { minY = Math.min(minY, wd[i]); maxY = Math.max(maxY, wd[i]) }
  assert.ok(maxY > minY, '步行髋部应有浮动')
})
