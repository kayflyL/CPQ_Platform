import * as THREE from 'three'
import fs from 'node:fs'

const SRC = 'D:/CPQ_Platform_V1/tmp/vrm-src/meshy-raw.glb'
const DST = 'D:/CPQ_Platform_V1/tmp/vrm-src/meshy-fixed6.glb'

const buf = fs.readFileSync(SRC)
const jsonLen = buf.readUInt32LE(12)
const gjson = JSON.parse(buf.slice(20, 20 + jsonLen).toString('utf8'))
const binOff = 20 + jsonLen
const binLen = buf.readUInt32LE(binOff)
const bin = buf.slice(binOff + 8, binOff + 8 + binLen)

const nodes = gjson.nodes
const skin = gjson.skins[0]
const joints = skin.joints

// 读 IBM 现有数据
const ibmAcc = gjson.accessors[skin.inverseBindMatrices]
const ibmBv = gjson.bufferViews[ibmAcc.bufferView]
const ibmByteOff = (ibmBv.byteOffset || 0)
const ibmMatrices = []
for (let i = 0; i < joints.length; i++) {
  const floats = new Float32Array(bin.buffer, bin.byteOffset + ibmByteOff + i * 64, 16)
  ibmMatrices.push(new THREE.Matrix4().fromArray(floats))
}

// 父子关系 + 各节点静止局部矩阵（three 权威数学）
const parentOf = new Map()
nodes.forEach((n, i) => (n.children || []).forEach((c) => parentOf.set(c, i)))
function localMatrixOf(n) {
  if (n.matrix) return new THREE.Matrix4().fromArray(n.matrix)
  const t = new THREE.Vector3(...(n.translation || [0, 0, 0]))
  const q = new THREE.Quaternion(...(n.rotation || [0, 0, 0, 1]))
  const s = new THREE.Vector3(...(n.scale || [1, 1, 1]))
  return new THREE.Matrix4().compose(t, q, s)
}
function worldOf(i, cache = new Map()) {
  if (cache.has(i)) return cache.get(i)
  const m = localMatrixOf(nodes[i])
  const p = parentOf.get(i)
  if (p !== undefined) m.premultiply(worldOf(p, cache))
  cache.set(i, m)
  return m
}

// 目标静止世界：绑定姿势绕 X 转 -90° 站起来
const qStand = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2)
const worldCache = new Map()
const standWorld = new Map()
for (let k = 0; k < joints.length; k++) {
  const ji = joints[k]
  const bindW = ibmMatrices[k].clone().invert()
  standWorld.set(ji, bindW.premultiply(new THREE.Matrix4().makeRotationFromQuaternion(qStand)))
}
// 自上而下重写局部 TRS
const newLocals = new Map()
function solveLocal(i) {
  if (newLocals.has(i)) return standWorld.get(i)
  const p = parentOf.get(i)
  const pw = p !== undefined ? (joints.includes(p) ? solveLocal(p) : worldOf(p, worldCache)) : new THREE.Matrix4()
  const local = pw.clone().invert().multiply(standWorld.get(i))
  newLocals.set(i, local)
  return standWorld.get(i)
}
joints.forEach((j, i) => solveLocal(j))

// 写回 TRS + 重写 IBM 字节（原位覆盖）
let dev = 0
joints.forEach((ji, k) => {
  const n = nodes[ji]
  const m = newLocals.get(ji)
  const t = new THREE.Vector3()
  const q = new THREE.Quaternion()
  const s = new THREE.Vector3()
  m.decompose(t, q, s)
  delete n.matrix
  n.translation = [+t.x.toFixed(7), +t.y.toFixed(7), +t.z.toFixed(7)]
  n.rotation = [+q.x.toFixed(7), +q.y.toFixed(7), +q.z.toFixed(7), +q.w.toFixed(7)]
  if (!n.scale) n.scale = [1, 1, 1]
  // IBM := inverse(newRestWorld)
  const inv = standWorld.get(ji).clone().invert()
  console.log('stand', joints[ji], standWorld.get(ji).elements.slice(12, 15).map((v) => +v.toFixed(3)))
  const bytes = new Float32Array(inv.elements)
  console.log('ibmwrite', joints[ji], Array.from(new Uint8Array(bytes.buffer)).slice(0, 4), Array.from(bytes).slice(12, 15))
  new Uint8Array(bin.buffer, bin.byteOffset + ibmByteOff + k * 64, 64).set(new Uint8Array(bytes.buffer))
  // 自检 dev
  const chk = new THREE.Matrix4().multiplyMatrices(standWorld.get(ji), inv)
  const e = chk.elements
  dev = Math.max(dev, Math.abs(e[0] - 1), Math.abs(e[5] - 1), Math.abs(e[10] - 1), Math.abs(e[12]), Math.abs(e[13]), Math.abs(e[14]))
})

// 重打包（JSON 补空格对齐）
let jsonStr = JSON.stringify(gjson)
while (jsonStr.length % 4) jsonStr += ' '
const jsonBytes = Buffer.from(jsonStr, 'utf8')
const out = Buffer.concat([
  Buffer.from([0x67, 0x6c, 0x54, 0x46]), Buffer.from([2, 0, 0, 0]), (() => { const b = Buffer.alloc(4); b.writeUInt32LE(12 + jsonBytes.length + 8 + bin.length); return b })(),
  (() => { const b = Buffer.alloc(4); b.writeUInt32LE(jsonBytes.length); return b })(), Buffer.from([0x4a, 0x53, 0x4f, 0x4e]), jsonBytes,
  (() => { const b = Buffer.alloc(4); b.writeUInt32LE(bin.length); return b })(), Buffer.from([0x42, 0x49, 0x4e, 0x00]), bin,
])
fs.writeFileSync(DST, out)
console.log('written', DST, out.length, 'dev=', dev.toFixed(6))
const vbuf = fs.readFileSync(DST)
const vj = JSON.parse(vbuf.slice(20, 20 + vbuf.readUInt32LE(12)).toString('utf8').replace(/ +$/, ''))
const voff = 20 + vbuf.readUInt32LE(12) + 8
const vacc = vj.accessors[vj.skins[0].inverseBindMatrices]
const vbv = vj.bufferViews[vacc.bufferView]
const vbinOff = voff
console.log('readback IBM0 row0:', [0, 1, 2, 3].map((k) => +vbuf.readFloatLE(vbinOff + (vbv.byteOffset || 0) + k * 4).toFixed(3)))
