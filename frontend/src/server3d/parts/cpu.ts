/**
 * 部件库 · CPU 部件工厂（闸3 落地,源自 docs/prototypes/服务器3D配置台/CPU部件建模蓝图.md 已批准闸2成片）
 * 契约（蓝图 §5）:
 *  - 根 Group userData.part='cpu',爆炸=轴向分层(IHS 上浮/chiplets 微浮/基板不动);
 *  - 每子件 userData={key,name,spec,desc},与 PART_INFO 悬浮标注同套渲染;
 *  - 尺寸单位 1unit=50mm(与 machine.ts 同标尺),内部按 mm 建模后整体缩放;
 *  - 刻字只出品牌字(AMD/兆芯),不出现具体型号(2026-11-03 用户定调)。
 * 2026-11-06 抽出公共单颗模块 createCpuModule(部件页/整机双消费,材质注入,见 CPU并入整机蓝图.md):
 *  整机装配态看不见底面触点阵,故 LGA pads 留在部件页专属层。
 */
import * as THREE from 'three'

export interface CpuSpec {
  /** 封装族:sp5=掀盖+chiplet 环绕 IOD;kh=单 die 银盖(尺寸近似,待核对) */
  family?: 'sp5' | 'kh'
  /** 顶盖品牌字(不含型号) */
  brand?: string
}

export const CPU_PART_INFO: Record<string, { name: string; spec: string; desc: string }> = {
  pcb: { name: '封装基板', spec: '约75×75mm', desc: 'LGA 触点阵在底面,金三角为 pin1 防插反标记。' },
  ccd: { name: 'CCD 核芯', spec: 'Zen4 · 象限布点', desc: '左右各2×2+上下各2,共12颗环绕 IOD(掀盖可见)。' },
  iod: { name: 'IOD', spec: 'I/O die', desc: '中央输入输出 die,负责内存/PCIe 通道。' },
  ihs: { name: 'IHS 顶盖', spec: '镀镍铜盖', desc: '台阶沿+边缘提拉凸台,激光刻品牌字。' },
  caps: { name: 'SMD 电容排', spec: '基板暴露带', desc: '供电滤波电容,沿台阶沿外圈布放。' },
  pads: { name: 'LGA 触点阵', spec: '底面焊盘阵列', desc: '翻到底面可见;安装时对准插座防插反。' },
  pin1: { name: '金三角 pin1', spec: '定位标记', desc: '基板角部金色三角,对准插座空角防插反。' },
}

/** 主题色映射(dark=原型值;light 提亮基板/压暗镀镍防糊白) */
export const CPU_THEME = {
  dark: { ihs: '#c9ced6', sub: '#2e5f66', subKh: '#2c4a34', chip: '#1a2032', iod: '#4a2a63', caps: '#2a2f3a' },
  light: { ihs: '#9fb0c0', sub: '#3f7d85', subKh: '#39624a', chip: '#2a3450', iod: '#5d3a80', caps: '#3a404c' },
}

/* 品牌刻字纹理按字缓存(整机双颗共享一张,部件页/整机各建各的) */
const _labelTex: Record<string, THREE.CanvasTexture> = {}
function brandTexture(brand: string) {
  if (_labelTex[brand]) return _labelTex[brand]
  const cv = document.createElement('canvas')
  cv.width = cv.height = 256
  const g = cv.getContext('2d')!
  g.fillStyle = '#2f353d'
  g.font = `700 ${brand.length > 2 ? 100 : 120}px "Arial","Microsoft YaHei"`
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText(brand, 128, 136)
  const tex = new THREE.CanvasTexture(cv)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  _labelTex[brand] = tex
  return tex
}

/** 公共单颗 CPU 模块(mm 域,按 family 定型):基板+chips+IHS 台阶沿+品牌刻字+电容排+pin1 金三角。
 *  材质调用方注入(部件页/整机各一组,禁每颗新建);不含底面 LGA 触点阵(整机装配态看不见)。
 *  返回分层组:部件页爆炸驱动用(gIhs 上浮/gChips 微浮/gSub 不动);整机装配态直接整组摆进插座。 */
export interface CpuModuleMats {
  sub: THREE.MeshPhysicalMaterial
  chip: THREE.MeshPhysicalMaterial
  iod: THREE.MeshPhysicalMaterial
  ihs: THREE.MeshPhysicalMaterial
  caps: THREE.MeshPhysicalMaterial
  gold: THREE.MeshPhysicalMaterial
}
export function createCpuModule(mats: CpuModuleMats, spec: CpuSpec = {}) {
  const family = spec.family ?? 'sp5'
  const brand = spec.brand ?? (family === 'kh' ? '兆芯' : 'AMD')
  const g = new THREE.Group()
  const gSub = new THREE.Group()
  const gChips = new THREE.Group()
  const gIhs = new THREE.Group()
  g.add(gSub, gChips, gIhs)
  function box(parent: THREE.Group, dims: [number, number, number], mat: THREE.Material, at: [number, number, number],
    ud: { key: string; name: string; spec: string; desc: string }) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(...dims), mat)
    m.position.set(...at)
    m.userData = ud
    m.castShadow = true
    m.receiveShadow = true
    parent.add(m)
    return m
  }

  // ── 基板(75×75mm) ──
  box(gSub, [75, 1.2, 75], mats.sub, [0, 0.6, 0],
    { key: 'pcb', name: CPU_PART_INFO.pcb.name, spec: CPU_PART_INFO.pcb.spec, desc: CPU_PART_INFO.pcb.desc })

  // ── chiplets:sp5=CCD 象限布点(左右2×2+上下各2)+中央 IOD;kh=单片大 die ──
  if (family === 'sp5') {
    for (const sx of [1, -1]) for (const x of [-25, -17].map(v => v * sx)) for (const z of [-4.5, -13, 4.5, 13])
      box(gChips, [7, 0.6, 8.5], mats.chip, [x, 1.5, z], { key: 'ccd', name: 'CCD', spec: 'Zen4', desc: CPU_PART_INFO.ccd.desc })
    for (const [x, z] of [[7, -26], [-7, -26], [7, 26], [-7, 26]] as const)
      box(gChips, [7, 0.6, 8.5], mats.chip, [x, 1.5, z], { key: 'ccd', name: 'CCD', spec: 'Zen4', desc: CPU_PART_INFO.ccd.desc })
    box(gChips, [17, 0.7, 17], mats.iod, [0, 1.55, 0], { key: 'iod', name: CPU_PART_INFO.iod.name, spec: CPU_PART_INFO.iod.spec, desc: CPU_PART_INFO.iod.desc })
  } else {
    box(gChips, [26, 0.8, 26], mats.chip, [0, 1.6, 0], { key: 'ccd', name: '单片大 die', spec: family.toUpperCase(), desc: CPU_PART_INFO.ccd.desc })
  }

  // ── SMD 电容排(基板暴露带,上下各20颗,instanced) ──
  const caps = new THREE.InstancedMesh(new THREE.BoxGeometry(3, 0.8, 1.6), mats.caps, 40)
  {
    const d = new THREE.Object3D()
    for (let i = 0; i < 20; i++) for (const [k, z] of [[0, 35.4], [1, -35.4]] as const) {
      d.position.set(-30 + i * 3.15, 1.6, z)
      d.updateMatrix()
      caps.setMatrixAt(k * 20 + i, d.matrix)
    }
  }
  caps.userData = { key: 'caps', name: CPU_PART_INFO.caps.name, spec: '上下各20颗', desc: CPU_PART_INFO.caps.desc }
  gSub.add(caps)

  // ── IHS:台阶沿+顶盖+提拉凸台(镀镍金属;粗糙度散开高光防顶视炸白,2026-11-03 闸4校准) ──
  const skirt = family === 'kh' ? 68 : 66
  const capW = family === 'kh' ? 58 : 55
  box(gIhs, [skirt, 1.2, skirt], mats.ihs, [0, 1.8, 0], { key: 'ihs', name: 'IHS 台阶沿', spec: `${skirt}×${skirt}mm`, desc: CPU_PART_INFO.ihs.desc })
  box(gIhs, [capW, 2.6, capW], mats.ihs, [0, 3.7, 0], { key: 'ihs', name: 'IHS 顶盖', spec: `${capW}×${capW}mm`, desc: CPU_PART_INFO.ihs.desc })
  for (const z of [30, -30])
    box(gIhs, [12, 2.6, 6], mats.ihs, [0, 3.7, z], { key: 'ihs', name: 'IHS 凸台', spec: '提拉位', desc: CPU_PART_INFO.ihs.desc })

  // ── 品牌刻字(CanvasTexture,只出品牌不出型号) ──
  const label = new THREE.Mesh(new THREE.PlaneGeometry(26, 26),
    new THREE.MeshBasicMaterial({ map: brandTexture(brand), transparent: true }))
  label.rotation.x = -Math.PI / 2
  label.position.y = 5.02
  label.userData = { key: 'ihs', name: '激光刻字', spec: brand, desc: '品牌字,不含型号(定调)。', noBloom: true }
  gIhs.add(label)

  // ── 金三角 pin1(基板顶面角部) ──
  {
    const s = new THREE.Shape()
    s.moveTo(0, 0)
    s.lineTo(6, 0)
    s.lineTo(0, 6)
    s.closePath()
    const tri = new THREE.Mesh(new THREE.ShapeGeometry(s), mats.gold)
    tri.rotation.x = -Math.PI / 2
    tri.position.set(-30.5, 1.22, -30.5)
    tri.userData = { key: 'pin1', name: CPU_PART_INFO.pin1.name, spec: CPU_PART_INFO.pin1.spec, desc: CPU_PART_INFO.pin1.desc }
    gSub.add(tri)
  }

  return { g, gSub, gChips, gIhs }
}

export function createCpuModel(spec: CpuSpec = {}) {
  const family = spec.family ?? 'sp5'
  const brand = spec.brand ?? (family === 'kh' ? '兆芯' : 'AMD')
  const SCALE = 0.02 // 1mm → 0.02unit(machine.ts ≈50mm/unit)
  const root = new THREE.Group()
  root.userData.part = 'cpu'
  root.scale.setScalar(SCALE)

  /** key→材质登记:setHover 时整体提亮 emissive */
  const byKey: Record<string, { mats: THREE.MeshPhysicalMaterial[] }> = {}
  function reg(key: string, m: THREE.MeshPhysicalMaterial) {
    m.emissive = new THREE.Color('#37c8ff')
    m.emissiveIntensity = 0
    ;(byKey[key] = byKey[key] || { mats: [] }).mats.push(m)
  }
  // 材质一组注入模块(原 box() 内联建材质改为共享,悬停行为不变:同 key 全提亮)
  const subMat = new THREE.MeshPhysicalMaterial({ color: family === 'kh' ? CPU_THEME.dark.subKh : CPU_THEME.dark.sub, roughness: 0.85, envMapIntensity: 0.15 })
  reg('pcb', subMat)
  const chipMat = new THREE.MeshPhysicalMaterial({ color: CPU_THEME.dark.chip, metalness: 0.5, roughness: 0.3, iridescence: 0.55, iridescenceIOR: 1.3, clearcoat: 0.5, envMapIntensity: 0.6 })
  reg('ccd', chipMat)
  const iodMat = new THREE.MeshPhysicalMaterial({ color: CPU_THEME.dark.iod, metalness: 0.4, roughness: 0.3, iridescence: 0.7, iridescenceIOR: 1.3, clearcoat: 0.5, envMapIntensity: 0.6 })
  reg('iod', iodMat)
  const ihsMat = new THREE.MeshPhysicalMaterial({ color: CPU_THEME.dark.ihs, metalness: 1.0, roughness: 0.55, envMapIntensity: 0.4 })
  reg('ihs', ihsMat)
  const capsMat = new THREE.MeshPhysicalMaterial({ color: CPU_THEME.dark.caps, metalness: 0.3, roughness: 0.5, envMapIntensity: 0.2 })
  reg('caps', capsMat)
  const goldMat = new THREE.MeshPhysicalMaterial({ color: '#d4a94f', metalness: 0.7, roughness: 0.4 })

  const mod = createCpuModule({ sub: subMat, chip: chipMat, iod: iodMat, ihs: ihsMat, caps: capsMat, gold: goldMat }, { family, brand })
  root.add(mod.g)

  // ── 底面 LGA 触点阵(部件页专属;52×52 instanced 示意密度,随基板层) ──
  const padsMat = new THREE.MeshPhysicalMaterial({ color: '#d4a94f', metalness: 0.8, roughness: 0.35, envMapIntensity: 0.5 })
  const N = 52
  const pads = new THREE.InstancedMesh(new THREE.BoxGeometry(0.8, 0.22, 0.8), padsMat, N * N)
  {
    const half = ((N - 1) * 1.35) / 2
    const d = new THREE.Object3D()
    let i = 0
    for (let ix = 0; ix < N; ix++) for (let iz = 0; iz < N; iz++) {
      d.position.set(-half + ix * 1.35, -0.11, -half + iz * 1.35)
      d.updateMatrix()
      pads.setMatrixAt(i++, d.matrix)
    }
  }
  pads.userData = { key: 'pads', name: CPU_PART_INFO.pads.name, spec: CPU_PART_INFO.pads.spec, desc: CPU_PART_INFO.pads.desc }
  mod.gSub.add(pads)

  // ── 爆炸(轴向分层,缓动趋近) / 悬停(emissive 提亮) ──
  let explodeTarget = 0
  let explode = 0
  let hoveredKey: string | null = null
  function updateTick(dt: number, _t: number) {
    explode += (explodeTarget - explode) * (1 - Math.exp(-dt * 5))
    mod.gIhs.position.y = explode * 60
    mod.gChips.position.y = explode * 28
    for (const [key, entry] of Object.entries(byKey)) {
      const on = key === hoveredKey ? 0.45 : 0
      for (const m of entry.mats) m.emissiveIntensity += (on - m.emissiveIntensity) * Math.min(1, dt * 10)
    }
  }
  function setHover(key: string | null) { hoveredKey = key }
  function setCounts() { /* 部件无数量步进,占位保持契约一致 */ }
  function applyTheme(t: Record<string, string>) {
    const pal = family === 'kh' ? { ...t, sub: t.subKh } : t
    subMat.color.set(pal.sub)
    ihsMat.color.set(pal.ihs)
    chipMat.color.set(pal.chip)
    iodMat.color.set(pal.iod)
    capsMat.color.set(pal.caps)
  }

  return {
    root, PART_INFO: CPU_PART_INFO, KEY_ALIAS: {} as Record<string, string | null>,
    setCounts, setExploded(on: boolean) { explodeTarget = on ? 1 : 0 },
    updateTick, setHover, applyTheme,
    setGlassBase() { /* 无玻璃件,占位 */ },
    get explodeRatio() { return explode },
  }
}

export type CpuModelHandles = ReturnType<typeof createCpuModel>
