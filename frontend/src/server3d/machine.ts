/**
 * server3d/machine.ts — 参数化服务器整机构建(纯TS,零Vue依赖)。
 * 蓝本=ESA240 V3 三视图图纸 + 底座档案:4U / 12×3.5"盘位(4列×3行) / 12×6056风扇 /
 * 绿色主板+2×CPU+24×DDR5单行三组(6/12/6) / 深绿Switch板+一排竖插双宽GPU /
 * CRPS 3+1电源 / 13×FHHL PCIe+OCP。配置是变量,模型是函数:数量驱动显隐。
 */
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { glow } from './themes'

export interface MachineConfig {
  bays: number
  fans: number
  cpus: number
  dimms: number
  gpus: number
  psu: { total: number; active: number }
  pcie: number
  ocp: number
  size: { W: number; H: number; D: number }
}

export const DEFAULT_MACHINE_CONFIG: MachineConfig = {
  bays: 12, fans: 12, cpus: 2, dimms: 24, gpus: 8,
  psu: { total: 4, active: 3 }, pcie: 13, ocp: 1,
  size: { W: 4.6, H: 1.78, D: 7.2 },
}

/** 部件语义(与图纸 region 标注对应):名称/规格/说明三行均为默认文案,可被模型分区标注逐项覆盖 */
export const PART_INFO: Record<string, { name: string; spec: string; desc: string }> = {
  drives: {
    name: '前置硬盘区', spec: '3.5" 热插拔盘位 · 4列×3行',
    desc: 'SATA / SAS / NVMe 热插拔。对应图纸前视图「前置硬盘区(12×3.5")」。',
  },
  ears: {
    name: '挂耳(指示灯/把手)', spec: '左电源键+状态灯 · 右VGA/USB',
    desc: '对应图纸前视图「左挂耳(指示灯/把手)」「右挂耳(VGA/USB/把手)」。',
  },
  fans: {
    name: '风扇区', spec: '6056 热插拔风扇墙',
    desc: '整机散热风道第一级。对应图纸俯视图「风扇区」。',
  },
  cpu: {
    name: 'CPU/内存区', spec: 'AMD 9004/9005 · DDR5 6400',
    desc: '绿色主板,双路 AMD 9004/9005,内存单行依次排列绕双CPU分三组(6/12/6)。对应图纸俯视图「CPU/内存区」。',
  },
  gpus: {
    name: 'GPU 区 · Switch板', spec: '双宽GPU 竖插一排 · Gen5 x16 直连',
    desc: '深绿 Switch 板上竖插一排双宽 GPU(俯视图的一排竖线),Passthrough 拓扑。',
  },
  psu: {
    name: '电源区', spec: 'CRPS 3+1 冗余',
    desc: 'CRPS 冗余电源(1300/1600/2000/2700W 可选)。对应图纸后视图「电源区(左/右)」。',
  },
  pcie: {
    name: 'PCIe 扩展槽区', spec: 'FHHL Gen5 x16 + OCP3.0',
    desc: '13×FHHL PCIe Gen5 x16 + 1×OCP3.0 x8。对应图纸后视图「PCIe 扩展槽区」「主板IO区」。',
  },
}

export const KEY_ALIAS: Record<string, string | null> = {
  front: 'drives', rear: 'psu', cover: null, shell: null,
}

export function createMachine(cfg: MachineConfig) {
  const { W, H, D } = cfg.size
  const root = new THREE.Group()

  // ── 共享材质(少材质=少切换;主题切换时整批换色) ──
  const M = {
    body: new THREE.MeshStandardMaterial({ color: '#2e4059', metalness: 0.6, roughness: 0.45 }),
    dark: new THREE.MeshStandardMaterial({ color: '#1c2a40', metalness: 0.55, roughness: 0.55 }),
    glass: new THREE.MeshStandardMaterial({ color: '#9fd4ff', metalness: 0, roughness: 0.3, transparent: true, opacity: 0.1, depthWrite: false }),
    edge: glow('#2fbcff', 1.9),
    cyan: glow('#37c8ff', 2.0),
    violet: glow('#9a6bff', 1.2),
    green: glow('#2fe6a8', 2.1),
    amber: glow('#ffb454', 1.7),
    dim: glow('#1d3a5c', 1.2),
    fin: new THREE.MeshStandardMaterial({ color: '#3d5378', metalness: 0.7, roughness: 0.35 }),
    board: new THREE.MeshStandardMaterial({ color: '#1f8a4c', metalness: 0.3, roughness: 0.5 }),
    boardDk: new THREE.MeshStandardMaterial({ color: '#14532d', metalness: 0.3, roughness: 0.55 }),
    dimm: new THREE.MeshStandardMaterial({ color: '#4ade80', metalness: 0.25, roughness: 0.4, emissive: '#166534', emissiveIntensity: 0.3 }),
    cpuCap: glow('#38bdf8', 1.4),
  }

  const parts: { g: THREE.Group; base: THREE.Vector3; off: THREE.Vector3 }[] = []
  const glowMats: Record<string, THREE.MeshBasicMaterial[]> = {}
  const fanSpinners: { s: THREE.Group; v: number }[] = []
  const driveLEDs: THREE.MeshBasicMaterial[] = []
  const earGlow: THREE.MeshBasicMaterial[] = []
  const psuGlow: THREE.MeshBasicMaterial[] = []
  const gpuUnits: THREE.Group[] = []
  const cpuUnits: THREE.Group[] = []
  const dimmUnits: THREE.Group[] = []
  const bayTrays: THREE.Group[] = []
  const popTweens: THREE.Object3D[] = []

  function tagGlow(key: string, m: THREE.MeshBasicMaterial) {
    ;(glowMats[key] = glowMats[key] || []).push(m)
    return m
  }
  function part(key: string, off: THREE.Vector3) {
    const g = new THREE.Group()
    g.userData.part = key
    root.add(g)
    parts.push({ g, base: new THREE.Vector3(), off })
    return g
  }
  function box(w: number, h: number, d: number, mat: THREE.Material, r = 0.02) {
    const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 2, r), mat)
    m.castShadow = true
    m.receiveShadow = true
    return m
  }
  function popIn(o: THREE.Object3D) {
    o.visible = true
    // 单实例补间:同一对象重复 popIn 只重置进度,不堆重复条目(重复条目会算出 NaN scale 致对象永久消失)
    if (!o.userData.pop) popTweens.push(o)
    o.userData.pop = 0.0001
  }
  // ── 机身外壳(底+两侧+后,顶留空给玻璃盖)+侧面刻线 ──
  {
    const t = 0.07
    const shell = part('shell', new THREE.Vector3(0, 0, 0))
    const bottom = box(W, t, D, M.body)
    bottom.position.y = t / 2
    shell.add(bottom)
    for (const s of [-1, 1]) {
      const side = box(t, H - t, D, M.body)
      side.position.set((s * (W - t)) / 2, t + (H - t) / 2, 0)
      shell.add(side)
    }
    const back = box(W - 2 * t, H - t, t, M.body)
    back.position.set(0, t + (H - t) / 2, -(D - t) / 2)
    shell.add(back)
    for (const s of [-1, 1]) {
      for (let seg = 0; seg < 4; seg++) {
        const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.016, D * 0.12), tagGlow('shell', M.edge.clone()))
        stripe.material.color.set('#1d5f9e').multiplyScalar(0.9)
        stripe.position.set(s * (W / 2 + 0.002), H * 0.5, -D * 0.32 + seg * D * 0.21)
        shell.add(stripe)
      }
    }
  }

  // ── 烟熏玻璃顶盖(爆炸时悬浮)+盖沿发光框 ──
  const topCover = part('cover', new THREE.Vector3(0, 2.3, 0))
  {
    const cover = new THREE.Mesh(new RoundedBoxGeometry(W - 0.08, 0.05, D - 0.08, 2, 0.02), M.glass)
    cover.position.set(0, H + 0.025, 0)
    topCover.add(cover)
    const frMat = tagGlow('cover', M.edge.clone())
    frMat.color.set('#2fa8e8').multiplyScalar(1.1)
    const frT = 0.014
    const frY = H + 0.02
    const frDims: [number, number, number, number, number, number][] = [
      [W - 0.04, frT, frT, 0, frY, (D - 0.04) / 2],
      [W - 0.04, frT, frT, 0, frY, -(D - 0.04) / 2],
      [frT, frT, D - 0.04, (W - 0.04) / 2, frY, 0],
      [frT, frT, D - 0.04, -(W - 0.04) / 2, frY, 0],
    ]
    for (const [sw, sh, sd, sx, sy, sz] of frDims) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(sw, sh, sd), frMat)
      seg.position.set(sx, sy, sz)
      topCover.add(seg)
    }
  }

  // ── 前部:挂耳 + 盘位笼(4列×3行) ──
  const frontAsm = part('front', new THREE.Vector3(0, 0, 2.1))
  {
    for (const s of [-1, 1]) {
      const ear = box(0.16, H, 0.5, M.body, 0.03)
      ear.position.set(s * (W / 2 + 0.06), H / 2, D / 2 - 0.25)
      frontAsm.add(ear)
      const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.012, H * 0.8, 0.012), tagGlow('ears', M.edge.clone()))
      stripe.material.color.set('#1f7fd0').multiplyScalar(1.3)
      stripe.position.set(s * (W / 2 + 0.06) + s * 0.086, H * 0.5, D / 2 + 0.01)
      frontAsm.add(stripe)
    }
    const pwr = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.02, 24), M.cyan.clone())
    pwr.rotation.x = Math.PI / 2
    pwr.position.set(-(W / 2 + 0.06), H * 0.72, D / 2 + 0.012)
    frontAsm.add(pwr)
    earGlow.push(pwr.material as THREE.MeshBasicMaterial)
    const leds = ['#2fe6a8', '#ffb454', '#37c8ff']
    leds.forEach((c, i) => {
      const l = new THREE.Mesh(new THREE.BoxGeometry(0.016, 0.03, 0.01), glow(c, 1.8))
      l.position.set(-(W / 2 + 0.06), H * (0.5 - i * 0.13), D / 2 + 0.012)
      frontAsm.add(l)
    })
    for (let i = 0; i < 3; i++) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.024, 0.012), M.dim.clone())
      p.position.set(W / 2 + 0.06, H * (0.62 - i * 0.14), D / 2 + 0.012)
      frontAsm.add(p)
    }
  }
  const driveCage = new THREE.Group()
  frontAsm.add(driveCage)
  {
    const grille = new THREE.Group()
    for (let i = 0; i < 5; i++) {
      const s = new THREE.Mesh(new THREE.BoxGeometry(W - 0.5, 0.02, 0.015), M.dark)
      s.position.set(-0.15, H * 0.78 + i * 0.055, D / 2 + 0.005)
      grille.add(s)
    }
    driveCage.add(grille)
    const brandMat = tagGlow('drives', M.edge.clone())
    brandMat.color.set('#2fa8e8').multiplyScalar(1.6)
    const brand = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.05, 0.012), brandMat)
    brand.position.set(-0.15, H * 0.62, D / 2 + 0.01)
    driveCage.add(brand)
    // 12盘 = 4列×3行,列间蓝色分隔线;数量减少时隐藏行尾
    for (let i = 0; i < cfg.bays; i++) {
      const g = new THREE.Group()
      const bw = 0.62
      const bh = 0.3
      const tray = box(bw, bh, 0.08, M.dark, 0.012)
      g.add(tray)
      const driveBody = box(bw * 0.88, bh * 0.8, 1.05, M.body, 0.01)
      driveBody.position.set(0, 0, -0.6)
      g.add(driveBody)
      const hm = M.edge.clone()
      hm.color.set('#1f7fd0').multiplyScalar(1.5)
      const handle = new THREE.Mesh(new THREE.BoxGeometry(bw * 0.55, 0.04, 0.012), tagGlow('drives', hm))
      handle.position.set(0, bh * 0.28, 0.05)
      g.add(handle)
      const led = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.01), glow('#2fe6a8', 1.6).clone())
      led.position.set(-bw * 0.32, bh * 0.28, 0.05)
      g.add(led)
      driveLEDs.push(led.material as THREE.MeshBasicMaterial)
      g.position.set(-1.55 + (i % 4) * 1.03, 0.26 + Math.floor(i / 4) * 0.42, D / 2 + 0.02)
      g.userData.idx = i
      driveCage.add(g)
      bayTrays.push(g)
    }
    for (let c = 0; c < 3; c++) {
      const sep = new THREE.Mesh(new THREE.BoxGeometry(0.012, 3 * 0.42, 0.012), tagGlow('drives', M.cyan.clone()))
      sep.position.set(-1.035 + c * 1.03, 0.47, D / 2 + 0.02)
      driveCage.add(sep)
    }
  }

  // ── 风扇墙(12×6056,旋转+青光环) ──
  const fanWall = part('fans', new THREE.Vector3(0, 0, 0))
  {
    const n = cfg.fans
    const r = 0.17
    const x0 = -(n * (r * 2 + 0.06) - 0.06) / 2
    for (let i = 0; i < n; i++) {
      const g = new THREE.Group()
      const frame = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.16, 24), M.body)
      frame.rotation.x = Math.PI / 2
      frame.castShadow = true
      g.add(frame)
      const hub = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.32, r * 0.32, 0.17, 16), M.fin)
      hub.rotation.x = Math.PI / 2
      g.add(hub)
      const halo = new THREE.Mesh(new THREE.TorusGeometry(r * 0.38, 0.012, 8, 28), tagGlow('fans', M.cyan.clone()))
      halo.position.z = 0.09
      g.add(halo)
      const spin = new THREE.Group()
      for (let b = 0; b < 7; b++) {
        const blade = new THREE.Mesh(new THREE.BoxGeometry(r * 0.72, 0.008, r * 0.3), M.fin)
        blade.position.x = r * 0.45
        const holder = new THREE.Group()
        holder.rotation.z = (b / 7) * Math.PI * 2
        holder.add(blade)
        spin.add(holder)
      }
      g.add(spin)
      fanSpinners.push({ s: spin, v: 7 + Math.random() * 5 })
      g.position.set(x0 + i * (r * 2 + 0.06) + r, H * 0.52, D * 0.245)
      fanWall.add(g)
    }
  }
  // ── CPU/内存区:绿色主板+双CPU(蓝色顶盖+鳍片塔,随配置增减)+24根内存单行三组 ──
  const cpuBank = part('cpu', new THREE.Vector3(0, 2.0, 0))
  {
    const mb = box(W - 0.7, 0.05, 2.05, M.board, 0.01)
    mb.position.set(0, 0.3, D * 0.09)
    cpuBank.add(mb)
    for (let i = 0; i < 7; i++) {
      const tr = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.006, 1.85), tagGlow('cpu', M.dim.clone()))
      tr.position.set(-1.5 + i * 0.5, 0.335, D * 0.09)
      cpuBank.add(tr)
    }
    for (const s of [-1, 1]) {
      const unit = new THREE.Group()
      const fin = new THREE.Group()
      const cap = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.06, 0.48), tagGlow('cpu', M.cpuCap.clone()))
      cap.position.y = 0.38
      fin.add(cap)
      for (let i = 0; i < 9; i++) {
        const f = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.012, 0.44), M.fin)
        f.position.y = 0.44 + i * 0.03
        f.castShadow = true
        fin.add(f)
      }
      fin.position.set(0, 0, D * 0.09)
      unit.add(fin)
      unit.position.set(s * 0.85, 0, 0)
      cpuBank.add(unit)
      cpuUnits.push(unit)
    }
    // 24根内存单行依次排列,绕双CPU分三组6/12/6(俯视浅黄竖条)
    const dimmX: number[] = []
    for (let i = 0; i < 6; i++) dimmX.push(-1.92 + i * 0.12)
    for (let i = 0; i < 12; i++) dimmX.push(-0.5 + i * 0.09)
    for (let i = 0; i < 6; i++) dimmX.push(1.2 + i * 0.12)
    for (let i = 0; i < dimmX.length; i++) {
      const d = new THREE.Group()
      const bar = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.42, 0.85), M.dimm)
      bar.position.y = 0.535
      bar.castShadow = true
      d.add(bar)
      const tip = new THREE.Mesh(new THREE.BoxGeometry(0.054, 0.014, 0.85), M.dimm.clone())
      tip.material.emissive = new THREE.Color('#86efac')
      tip.material.emissiveIntensity = 0.5
      tip.position.y = 0.738
      d.add(tip)
      d.position.set(dimmX[i], 0, D * 0.09)
      cpuBank.add(d)
      dimmUnits.push(d)
    }
  }

  // ── GPU区:深绿Switch板 + 一排竖插双宽GPU(俯视一排细竖线) ──
  const gpuBank = part('gpus', new THREE.Vector3(0, 3.4, 0))
  {
    const sw = box(W - 0.6, 0.06, 0.55, M.boardDk, 0.01)
    sw.position.set(0, 0.32, -(D / 2) + 0.62)
    gpuBank.add(sw)
    for (let i = 0; i < cfg.gpus; i++) {
      const g = new THREE.Group()
      const x = -1.75 + i * 0.5
      const conn = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.03, 0.12), tagGlow('gpus', M.violet.clone()))
      conn.position.set(0, 0.37, 0)
      g.add(conn)
      const pcb = box(0.36, 1.0, 2.3, M.dark, 0.02)
      pcb.position.set(0, 0.85, 1.18)
      g.add(pcb)
      const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.018, 2.15), tagGlow('gpus', M.violet.clone()))
      stripe.position.set(0, 1.36, 1.18)
      g.add(stripe)
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.014, 8, 32), tagGlow('gpus', M.cyan.clone()))
      ring.rotation.x = Math.PI / 2
      ring.position.set(0, 0.9, 0.42)
      g.add(ring)
      const bracket = box(0.34, 0.8, 0.03, M.body, 0.008)
      bracket.position.set(0, 0.74, 0.02)
      g.add(bracket)
      g.position.set(x, 0, -(D / 2) + 0.62)
      g.userData.idx = i
      gpuBank.add(g)
      gpuUnits.push(g)
    }
  }

  // ── 后部:CRPS电源3+1 + PCIe槽排 + OCP + BMC灯 ──
  const rearAsm = part('rear', new THREE.Vector3(0, 0, -2.4))
  {
    for (let i = 0; i < cfg.psu.total; i++) {
      const g = new THREE.Group()
      const mod = box(0.72, 0.82, 0.3, M.body, 0.02)
      mod.position.y = 0.5
      g.add(mod)
      const handle = new THREE.Mesh(
        new THREE.BoxGeometry(0.5, 0.05, 0.014),
        i < cfg.psu.active ? M.green.clone() : tagGlow('psu', M.dim.clone()),
      )
      handle.position.set(0, 0.72, 0.16)
      g.add(handle)
      if (i < cfg.psu.active) psuGlow.push(handle.material as THREE.MeshBasicMaterial)
      for (let k = 0; k < 6; k++) {
        const s = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.014, 0.012), M.dark)
        s.position.set(0, 0.2 + k * 0.07, 0.16)
        g.add(s)
      }
      g.position.set((-(cfg.psu.total * 0.82)) / 2 + 0.45 + i * 0.82, 0, -(D / 2) - 0.13)
      rearAsm.add(g)
    }
    const pcieSub = new THREE.Group()
    pcieSub.userData.part = 'pcie'
    rearAsm.add(pcieSub)
    for (let i = 0; i < cfg.pcie; i++) {
      const sm = M.amber.clone()
      sm.color.set('#c88a3f').multiplyScalar(1.1)
      const s = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.3, 0.012), tagGlow('pcie', sm))
      s.position.set(-1.72 + i * 0.265, H * 0.66, -(D / 2) - 0.012)
      pcieSub.add(s)
    }
    const ocp = box(0.44, 0.42, 0.06, M.body, 0.02)
    ocp.position.set(1.95, H * 0.66, -(D / 2) - 0.05)
    pcieSub.add(ocp)
    const ocpLed = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.02, 0.015), tagGlow('pcie', M.cyan.clone()))
    ocpLed.position.set(1.95, H * 0.78, -(D / 2) - 0.085)
    pcieSub.add(ocpLed)
    const bmc = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.03, 0.012), tagGlow('pcie', M.green.clone()))
    bmc.position.set(-2.05, H * 0.4, -(D / 2) - 0.012)
    pcieSub.add(bmc)
  }

  // ── 内部走线(发光弧线示意) ──
  for (let i = 0; i < 3; i++) {
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-1.6 + i * 1.6, 0.35, -(D / 2) - 0.1),
      new THREE.Vector3(-1.2 + i * 1.2, 1.15, -1.2 - i * 0.4),
      new THREE.Vector3(-0.6 + i * 0.6, 0.6, D * 0.12 + i * 0.3),
    ])
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 32, 0.014, 6), M.dim)
    root.add(tube)
  }

  for (const p of parts) p.base = p.g.position.clone()

  // ── 数量驱动显隐(配置即入参) ──
  function setCounts(c: { gpus?: number; cpus?: number; dimms?: number; bays?: number }) {
    const apply = (list: THREE.Object3D[], n: number) =>
      list.forEach((g, i) => (i < n ? popIn(g) : ((g.visible = false), delete g.userData.pop)))
    if (c.gpus != null) apply(gpuUnits, Math.max(0, Math.min(cfg.gpus, c.gpus)))
    if (c.cpus != null) apply(cpuUnits, Math.max(0, Math.min(cfg.cpus, c.cpus)))
    if (c.dimms != null) apply(dimmUnits, Math.max(0, Math.min(cfg.dimms, c.dimms)))
    if (c.bays != null) apply(bayTrays, Math.max(0, Math.min(cfg.bays, c.bays)))
  }
  function setExploded(e: boolean) {
    explodeTarget = e ? 1 : 0
  }
  let explodeTarget = 0
  let explode = 0
  let glassBase = 0.1
  function setGlassBase(v: number) { glassBase = v }

  function updateTick(dt: number, t: number) {
    explode += (explodeTarget - explode) * (1 - Math.exp(-dt * 5))
    const eo = 1 - Math.pow(1 - explode, 3)
    for (const p of parts) p.g.position.copy(p.base).addScaledVector(p.off, eo)
    M.glass.opacity = Math.max(0.02, glassBase - 0.06 * explode)
    const breath = 1.1 + 0.45 * Math.sin(t * 2.1)
    for (const m of earGlow) m.color.set('#37c8ff').multiplyScalar(breath)
    for (const f of fanSpinners) f.s.rotation.z += dt * f.v
    for (const m of driveLEDs) m.color.set('#2fe6a8').multiplyScalar(Math.random() < 0.015 ? 2.6 : 1.2 + 0.25 * Math.sin(t * 3 + Math.random()))
    for (const m of psuGlow) m.color.set('#2fe6a8').multiplyScalar(1.5 + 0.3 * Math.sin(t * 2.6))
    for (let i = popTweens.length - 1; i >= 0; i--) {
      const o = popTweens[i]
      const k0 = Number(o.userData.pop) + dt * 4
      if (!Number.isFinite(k0)) {
        // 兜底:进度被污染(历史NaN)直接归位
        o.scale.setScalar(1)
        delete o.userData.pop
        popTweens.splice(i, 1)
        continue
      }
      const k = Math.min(k0, 1)
      o.userData.pop = k
      o.scale.setScalar(0.6 + 0.4 * (1 - Math.pow(1 - k, 3)))
      if (k >= 1) {
        o.scale.setScalar(1)
        delete o.userData.pop
        popTweens.splice(i, 1)
      }
    }
  }
  function setHover(key: string | null) {
    for (const [k, mats] of Object.entries(glowMats)) {
      const on = k === key
      for (const m of mats) {
        if (m.userData.base == null) m.userData.base = m.color.clone()
        m.userData.lerp = ((m.userData.lerp as number) ?? 1) + ((on ? 2.0 : 1.0) - ((m.userData.lerp as number) ?? 1)) * 0.35
        m.color.copy(m.userData.base as THREE.Color).multiplyScalar(m.userData.lerp as number)
      }
    }
  }

  return {
    root, M, parts, glowMats, PART_INFO, KEY_ALIAS,
    units: { gpuUnits, cpuUnits, dimmUnits, bayTrays },
    setCounts, setExploded, updateTick, setHover, setGlassBase,
    get explodeRatio() { return explode },
  }
}

export type MachineHandles = ReturnType<typeof createMachine>
