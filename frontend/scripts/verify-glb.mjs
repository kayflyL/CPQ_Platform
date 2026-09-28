import * as THREE from 'three'
import fs from 'node:fs'

const buf = fs.readFileSync(process.argv[2] || 'D:/CPQ_Platform_V1/tmp/vrm-src/meshy-fixed6.glb')
const jsonLen = buf.readUInt32LE(12)
const gjson = JSON.parse(buf.slice(20, 20 + jsonLen).toString('utf8'))
const binOff = 20 + jsonLen
const binLen = buf.readUInt32LE(binOff)
const bin = buf.slice(binOff + 8, binOff + 8 + binLen)

const nodes = gjson.nodes
const skin = gjson.skins[0]
const joints = skin.joints
const ibmAcc = gjson.accessors[skin.inverseBindMatrices]
const ibmBv = gjson.bufferViews[ibmAcc.bufferView]
const ibmOff = (ibmBv.byteOffset || 0)

const parentOf = new Map()
nodes.forEach((n, i) => (n.children || []).forEach((c) => parentOf.set(c, i)))
function localMatrixOf(n) {
  if (n.matrix) return new THREE.Matrix4().fromArray(n.matrix)
  const t = new THREE.Vector3(...(n.translation || [0, 0, 0]))
  const q = new THREE.Quaternion(...(n.rotation || [0, 0, 0, 1]))
  const s = new THREE.Vector3(...(n.scale || [1, 1, 1]))
  return new THREE.Matrix4().compose(t, q, s)
}
const cache = new Map()
function worldOf(i) {
  if (cache.has(i)) return cache.get(i)
  const m = localMatrixOf(nodes[i]).clone()
  const p = parentOf.get(i)
  if (p !== undefined) m.premultiply(worldOf(p))
  cache.set(i, m)
  return m
}

let maxDev = 0
let worst = ''
const samples = {}
joints.forEach((ji, k) => {
  const floats = new Float32Array(bin.buffer, bin.byteOffset + ibmOff + k * 64, 16)
  const ibm = new THREE.Matrix4().fromArray(floats)
  const m = new THREE.Matrix4().multiplyMatrices(worldOf(ji), ibm)
  const e = m.elements
  const d = Math.max(Math.abs(e[0] - 1), Math.abs(e[5] - 1), Math.abs(e[10] - 1), Math.abs(e[12]), Math.abs(e[13]), Math.abs(e[14]))
  if (d > maxDev) { maxDev = d; worst = nodes[ji].name }
  if (['Hip', 'L_Thigh', 'Head', 'R_Hand'].includes(nodes[ji].name)) {
    samples[nodes[ji].name] = { rest: worldOf(ji).elements.slice(12, 15).map((v) => +v.toFixed(3)) }
  }
})
console.log(JSON.stringify({ maxDev: +maxDev.toFixed(5), worst, samples }))
