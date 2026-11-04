/**
 * 部件库 · 风扇墙模块工厂（源自 docs/prototypes/服务器3D配置台/风扇部件建模蓝图.md 已批准闸2成片）
 * 契约同 cpu.ts：StageModel 同形句柄、轴向爆炸、语义标注、双主题钩子。
 * 参照 ZTE R6530 G3 拆解页风扇墙：2行×6列 8038（80×80×38mm，待核对），
 * 护罩框板银白金属漆 / 扇框转子哑黑塑胶，转子常转+爆炸停转（拆下即断电教学语义）。
 * 刻字定调：贴纸只做形状不写字，不出现具体型号。
 */
import * as THREE from 'three'

export interface FanSpec {
  cols?: number
  rows?: number
  /** 单扇外框边长(mm),8038=80,待核对 */
  size?: number
  brand?: string
}

export const FAN_PART_INFO: Record<string, { name: string; spec: string; desc: string }> = {
  grille: { name: '护罩框板', spec: '银白金属板阵列开孔', desc: '风扇墙前护板,开孔透风并保护手指。' },
  fanframe: { name: '风扇模块', spec: '8038 · 80×80×38mm(待核对)', desc: '热插拔风扇,八角外缘方框切角造型。' },
  rotor: { name: '转子叶轮', spec: '7叶弯刀', desc: '装配态常转;拆下即停转(断电教学语义)。' },
  hub: { name: '端盖毂', spec: '转子中心', desc: '马达轴端盖,藏滚珠轴承与测速线。' },
  screw: { name: '框角螺丝', spec: '四角沉孔', desc: '扇框与模组支架的固定点。' },
  handle: { name: '热插拔提手', spec: '底缘6组', desc: '拉出即断电,在线更换不停机。' },
  connector: { name: '金手指连接器', spec: 'PCB+金手指', desc: '供电与测速信号(PWM/转速反馈)接口。' },
}

/** 主题色(dark=原型值;light 提亮塑胶防糊白) */
const FAN_THEME = {
  dark: { plate: '#b7c1cd', frame: '#15171c', rotor: '#1a1d24', hub: '#22262e', sticker: '#3a3f4a', gold: '#d4a94f' },
  light: { plate: '#d6dee8', frame: '#3a4250', rotor: '#4a5060', hub: '#565e6c', sticker: '#565e6c', gold: '#c4984a' },
}

export function createFanModel(spec: FanSpec = {}) {
  const COLS = spec.cols ?? 6
  const ROWS = spec.rows ?? 2
  const FAN = spec.size ?? 80
  const DEPTH = 38
  const PITCH = FAN + 2
  const GAP = 4
  const WALL_W = COLS * PITCH + GAP * 2
  const WALL_H = ROWS * PITCH + GAP * 2
  const SCALE = 0.02 // 1mm → 0.02unit(与 machine.ts 同标尺)

  const root = new THREE.Group()
  root.userData.part = 'fan'
  root.scale.setScalar(SCALE)
  root.position.y = (WALL_H / 2 + 12) * SCALE // 抬升到地台上方(底缘离地防穿模);position 是父域,要乘缩放

  const gGrille = new THREE.Group()
  const gFans = new THREE.Group()
  const gRotors = new THREE.Group()
  root.add(gGrille, gFans, gRotors)

  const byKey: Record<string, { mats: THREE.MeshPhysicalMaterial[] }> = {}
  function reg(key: string, m: THREE.MeshPhysicalMaterial) {
    m.emissive = new THREE.Color('#37c8ff')
    m.emissiveIntensity = 0
    ;(byKey[key] = byKey[key] || { mats: [] }).mats.push(m)
  }
  const T = FAN_THEME.dark
  const plateMat = new THREE.MeshPhysicalMaterial({ color: T.plate, roughness: 0.5, metalness: 0.6, envMapIntensity: 0.5 })
  const frameMat = new THREE.MeshPhysicalMaterial({ color: T.frame, roughness: 0.7, envMapIntensity: 0.15 })
  const rotorMat = new THREE.MeshPhysicalMaterial({ color: T.rotor, roughness: 0.45, iridescence: 0.25, iridescenceIOR: 1.3, envMapIntensity: 0.25 })
  const hubMat = new THREE.MeshPhysicalMaterial({ color: T.hub, roughness: 0.5, envMapIntensity: 0.15 })
  const goldMat = new THREE.MeshPhysicalMaterial({ color: T.gold, metalness: 0.8, roughness: 0.35, envMapIntensity: 0.5 })
  const stickerMat = new THREE.MeshPhysicalMaterial({ color: T.sticker, roughness: 0.6, envMapIntensity: 0.15 })
  reg('grille', plateMat)
  reg('fanframe', frameMat)
  reg('rotor', rotorMat)
  reg('hub', hubMat)
  reg('handle', frameMat)
  reg('connector', goldMat)
  reg('screw', hubMat)

  function mesh(parent: THREE.Group, geo: THREE.BufferGeometry, mat: THREE.MeshPhysicalMaterial,
    ud: { key: string; name: string; spec: string; desc: string }) {
    const m = new THREE.Mesh(geo, mat)
    m.castShadow = true
    m.receiveShadow = true
    m.userData = ud
    parent.add(m)
    return m
  }

  /* L1 护罩框板:圆角矩形开孔阵列+倒角 */
  function roundedHole(hx: number, hy: number, hw: number, hh: number, r: number) {
    const p = new THREE.Path()
    const x = hx - hw / 2, y = hy - hh / 2
    p.moveTo(x + r, y)
    p.lineTo(x + hw - r, y); p.absarc(x + hw - r, y + r, r, -Math.PI / 2, 0, false)
    p.lineTo(x + hw, y + hh - r); p.absarc(x + hw - r, y + hh - r, r, 0, Math.PI / 2, false)
    p.lineTo(x + r, y + hh); p.absarc(x + r, y + hh - r, r, Math.PI / 2, Math.PI, false)
    p.lineTo(x, y + r); p.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5, false)
    p.closePath()
    return p
  }
  const plate = new THREE.Shape()
  plate.moveTo(-WALL_W / 2, -WALL_H / 2); plate.lineTo(WALL_W / 2, -WALL_H / 2)
  plate.lineTo(WALL_W / 2, WALL_H / 2); plate.lineTo(-WALL_W / 2, WALL_H / 2); plate.closePath()
  const cellX = (c: number) => -WALL_W / 2 + GAP + c * PITCH + PITCH / 2
  const cellY = (r: number) => WALL_H / 2 - GAP - r * PITCH - PITCH / 2
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++)
    plate.holes.push(roundedHole(cellX(c), cellY(r), FAN - 2, FAN - 2, 8))
  const grille = mesh(gGrille, new THREE.ExtrudeGeometry(plate, { depth: 2, bevelEnabled: true, bevelThickness: 0.6, bevelSize: 0.8, bevelSegments: 2 }),
    plateMat, { key: 'grille', name: FAN_PART_INFO.grille.name, spec: FAN_PART_INFO.grille.spec, desc: FAN_PART_INFO.grille.desc })
  grille.position.z = DEPTH + 6

  /* L2 风扇模块×12:八角环框+螺丝沉孔+贴纸形;L3 转子:7叶弯刀+毂 */
  function octagon(size: number, holeR: number) {
    const c = size / 2, k = size * 0.18
    const s = new THREE.Shape()
    s.moveTo(-c + k, -c); s.lineTo(c - k, -c); s.lineTo(c, -c + k); s.lineTo(c, c - k)
    s.lineTo(c - k, c); s.lineTo(-c + k, c); s.lineTo(-c, c - k); s.lineTo(-c, -c + k); s.closePath()
    const p = new THREE.Path()
    p.absarc(0, 0, holeR, 0, Math.PI * 2, true)
    s.holes.push(p)
    return s
  }
  const blade = new THREE.Shape()
  blade.absarc(0, 0, 33, 0, 0.62, false)
  blade.absarc(0, 0, 15, 0.62, 0, true)
  blade.closePath()

  const rotorGroups: THREE.Group[] = []
  const bladeGeo = new THREE.ExtrudeGeometry(blade, { depth: 2.4, bevelEnabled: false })
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
    const g = new THREE.Group()
    g.position.set(cellX(c), cellY(r), 0)
    gFans.add(g)
    const frame = mesh(g, new THREE.ExtrudeGeometry(octagon(FAN, 34), { depth: DEPTH, bevelEnabled: false }),
      frameMat, { key: 'fanframe', name: FAN_PART_INFO.fanframe.name, spec: FAN_PART_INFO.fanframe.spec, desc: FAN_PART_INFO.fanframe.desc })
    void frame
    for (const [sx, sy] of [[28, 28], [-28, 28], [28, -28], [-28, -28]] as const) {
      const screw = mesh(g, new THREE.CylinderGeometry(2.5, 2.5, 2.5, 12),
        hubMat, { key: 'screw', name: FAN_PART_INFO.screw.name, spec: FAN_PART_INFO.screw.spec, desc: FAN_PART_INFO.screw.desc })
      screw.rotation.x = Math.PI / 2
      screw.position.set(sx, sy, DEPTH - 1)
    }
    const sticker = mesh(g, new THREE.BoxGeometry(22, 9, 1),
      stickerMat, { key: 'fanframe', name: '规格贴纸', spec: '图形示意', desc: '只做形状不写字(避型号定调)。' })
    sticker.position.set(22, 28, DEPTH + 0.5)

    const rotor = new THREE.Group()
    rotor.position.set(cellX(c), cellY(r), DEPTH / 2)
    for (let i = 0; i < 7; i++) {
      const wrap = new THREE.Group()
      wrap.rotation.z = i * Math.PI * 2 / 7 + 0.18
      const b = mesh(wrap, bladeGeo,
        rotorMat, { key: 'rotor', name: FAN_PART_INFO.rotor.name, spec: FAN_PART_INFO.rotor.spec, desc: FAN_PART_INFO.rotor.desc })
      b.rotation.x = 0.52
      b.position.z = -1.2
      wrap.add(b)
      rotor.add(wrap)
    }
    const hub = mesh(rotor, new THREE.CylinderGeometry(12, 12, DEPTH - 14, 24),
      hubMat, { key: 'hub', name: FAN_PART_INFO.hub.name, spec: FAN_PART_INFO.hub.spec, desc: FAN_PART_INFO.hub.desc })
    hub.rotation.x = Math.PI / 2
    gRotors.add(rotor)
    rotorGroups.push(rotor)
  }

  /* L4 提手+金手指连接器(底缘,随框板层) */
  for (let c = 0; c < COLS; c++) {
    const h = new THREE.Group()
    const grip = mesh(h, new THREE.BoxGeometry(26, 12, 10),
      frameMat, { key: 'handle', name: FAN_PART_INFO.handle.name, spec: FAN_PART_INFO.handle.spec, desc: FAN_PART_INFO.handle.desc })
    grip.position.set(cellX(c), -WALL_H / 2 - 2, DEPTH / 2)
    const pcb = mesh(h, new THREE.BoxGeometry(18, 2, 26),
      hubMat, { key: 'connector', name: FAN_PART_INFO.connector.name, spec: FAN_PART_INFO.connector.spec, desc: FAN_PART_INFO.connector.desc })
    pcb.position.set(cellX(c), -WALL_H / 2 - 1, -DEPTH / 2)
    for (let i = 0; i < 4; i++) {
      const f = mesh(h, new THREE.BoxGeometry(2.5, 1.5, 14),
        goldMat, { key: 'connector', name: FAN_PART_INFO.connector.name, spec: FAN_PART_INFO.connector.spec, desc: FAN_PART_INFO.connector.desc })
      f.position.set(cellX(c) - 6.75 + i * 4.5, -WALL_H / 2 - 2.5, -DEPTH / 2 + 3)
    }
    gGrille.add(h)
  }

  /* 爆炸(轴向:护罩框前移/转子拔出) + 悬停(emissive) + 转子常转(爆炸停转) */
  let explodeTarget = 0
  let explode = 0
  let hoveredKey: string | null = null
  function updateTick(dt: number, _t: number) {
    explode += (explodeTarget - explode) * (1 - Math.exp(-dt * 5))
    gGrille.position.z = explode * 120
    gRotors.position.z = explode * 40
    if (explode < 0.02) for (const rg of rotorGroups) rg.rotation.z += dt * 1.2
    for (const [key, entry] of Object.entries(byKey)) {
      const on = key === hoveredKey ? 0.45 : 0
      for (const m of entry.mats) m.emissiveIntensity += (on - m.emissiveIntensity) * Math.min(1, dt * 10)
    }
  }
  function setHover(key: string | null) { hoveredKey = key }

  function applyTheme(t: Record<string, string>, name: 'dark' | 'light') {
    const pal = FAN_THEME[name]
    plateMat.color.set(pal.plate)
    frameMat.color.set(pal.frame)
    rotorMat.color.set(pal.rotor)
    hubMat.color.set(pal.hub)
    stickerMat.color.set(pal.sticker)
    goldMat.color.set(pal.gold)
    void t
  }

  return {
    root, PART_INFO: FAN_PART_INFO, KEY_ALIAS: {} as Record<string, string | null>,
    setCounts() { /* 部件无数量步进 */ },
    setExploded(on: boolean) { explodeTarget = on ? 1 : 0 },
    updateTick, setHover, applyTheme,
    setGlassBase() { /* 无玻璃件 */ },
    get explodeRatio() { return explode },
  }
}

export type FanModelHandles = ReturnType<typeof createFanModel>
