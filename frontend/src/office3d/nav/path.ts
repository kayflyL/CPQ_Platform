/**
 * 网格寻路：直线检测 → 网格 A* → 弦拉直平滑。（R1 自 Office3DCanvas 抽出，逻辑逐行等价）
 * 全部经由 NavWorld 查询障碍/边界/缓冲区，纯逻辑可单测。
 */
import * as THREE from 'three'
import type { NavWorld } from './world.ts'
import { NAV_STEP } from './world.ts'

/** 两点之间是否直线畅通（按点采样判断）。 */
export function segmentClear(nav: NavWorld, a: THREE.Vector3, b: THREE.Vector3): boolean {
  const dist = a.distanceTo(b)
  if (dist < 0.001) return true
  const steps = Math.max(2, Math.ceil(dist / 0.12))
  for (let i = 1; i < steps; i++) {
    const t = i / steps
    if (nav.blockedAt(a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t)) return false
  }
  return true
}

/** 把网格角点路径做“弦拉直”平滑，减少锯齿。 */
export function smoothPath(nav: NavWorld, path: THREE.Vector3[]): THREE.Vector3[] {
  if (path.length <= 2) return path
  const out: THREE.Vector3[] = [path[0]]
  let anchor = 0
  for (let i = 2; i < path.length; i++) {
    if (!segmentClear(nav, path[anchor], path[i])) {
      out.push(path[i - 1])
      anchor = i - 1
    }
  }
  out.push(path[path.length - 1])
  return out
}

/** 网格 A* 寻路：返回从 start 到 end 的平滑世界坐标点（避开 blockedAt 障碍）。 */
export function findPath(nav: NavWorld, start: THREE.Vector3, end: THREE.Vector3): THREE.Vector3[] {
  if (nav.debugEnabled()) nav.stats.astar += 1
  // 直线畅通时直接返回，避免不必要的网格搜索。
  if (segmentClear(nav, start, end)) return [end.clone()]
  const b = nav.floorBounds()
  const step = NAV_STEP
  const cols = Math.max(1, Math.ceil((b.maxX - b.minX) / step))
  const rows = Math.max(1, Math.ceil((b.maxZ - b.minZ) / step))
  const toCellX = (x: number) => Math.min(cols - 1, Math.max(0, Math.round((x - b.minX) / step - 0.5)))
  const toCellZ = (z: number) => Math.min(rows - 1, Math.max(0, Math.round((z - b.minZ) / step - 0.5)))
  const cellCenterX = (ix: number) => b.minX + (ix + 0.5) * step
  const cellCenterZ = (iz: number) => b.minZ + (iz + 0.5) * step
  const idx = (ix: number, iz: number) => iz * cols + ix
  const walkable = (ix: number, iz: number) => ix >= 0 && ix < cols && iz >= 0 && iz < rows && !nav.blockedAt(cellCenterX(ix), cellCenterZ(iz))

  const sx = toCellX(start.x)
  const sz = toCellZ(start.z)
  const ex = toCellX(end.x)
  const ez = toCellZ(end.z)
  // 起点格即使被家具/会议墙占据也允许起步：仅当起终点同格时直连，
  // 否则让 A* 从起点格向外搜索，撞墙/被卡在阻挡格时可先脱离而不是“直线冲向墙”。
  if (sx === ex && sz === ez) return [end.clone()]

  const n = cols * rows
  const scratch = nav.astarBuffers(n)
  const g = scratch.g
  const f = scratch.f
  const parent = scratch.parent
  const inOpen = scratch.inOpen
  const closed = scratch.closed
  g.fill(Infinity)
  f.fill(Infinity)
  parent.fill(-1)
  inOpen.fill(0)
  closed.fill(0)
  // 最小二叉堆开放集，替代原先的线性扫描 + splice（O(n)），避免大网格下寻路卡顿。
  const heap: number[] = []
  const heapIndex = scratch.heapIndex
  heapIndex.fill(-1)
  const less = (a: number, b: number) => f[a] < f[b]
  const swap = (a: number, b: number) => {
    const t = heap[a]
    heap[a] = heap[b]
    heap[b] = t
    heapIndex[heap[a]] = a
    heapIndex[heap[b]] = b
  }
  const siftUp = (i: number) => {
    while (i > 0) {
      const p = (i - 1) >> 1
      if (less(heap[i], heap[p])) {
        swap(i, p)
        i = p
      } else break
    }
  }
  const siftDown = (i: number) => {
    const n = heap.length
    while (true) {
      const l = i * 2 + 1
      const r = l + 1
      let m = i
      if (l < n && less(heap[l], heap[m])) m = l
      if (r < n && less(heap[r], heap[m])) m = r
      if (m === i) break
      swap(i, m)
      i = m
    }
  }
  const push = (node: number) => {
    heap.push(node)
    heapIndex[node] = heap.length - 1
    siftUp(heap.length - 1)
  }
  const pop = (): number => {
    const top = heap[0]
    const last = heap.pop()!
    if (heap.length) {
      heap[0] = last
      heapIndex[last] = 0
      siftDown(0)
    }
    heapIndex[top] = -1
    return top
  }
  g[idx(sx, sz)] = 0
  f[idx(sx, sz)] = 0
  inOpen[idx(sx, sz)] = 1
  push(idx(sx, sz))
  const hval = (ix: number, iz: number) => {
    const dx = Math.abs(ix - ex)
    const dz = Math.abs(iz - ez)
    return dx + dz + (Math.SQRT2 - 2) * Math.min(dx, dz)
  }
  const neighbors: Array<[number, number, number]> = [
    [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
    [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2],
  ]
  // 记录已探索到的“离终点最近的可达格”，A* 无解时回退到该格而非直冲终点。
  let bestNode = idx(sx, sz)
  let bestH = hval(sx, sz)

  while (heap.length) {
    const cur = pop()
    inOpen[cur] = 0
    if (closed[cur]) continue
    closed[cur] = 1
    if (cur === idx(ex, ez)) {
      const raw: THREE.Vector3[] = []
      let c = cur
      while (c !== -1) {
        const ix = c % cols
        const iz = Math.floor(c / cols)
        raw.push(new THREE.Vector3(cellCenterX(ix), 0, cellCenterZ(iz)))
        c = parent[c]
      }
      raw.reverse()
      const smoothed = smoothPath(nav, raw)
      smoothed.push(end.clone())
      return smoothed
    }
    const cix = cur % cols
    const ciz = Math.floor(cur / cols)
    const ch = hval(cix, ciz)
    if (ch < bestH) {
      bestH = ch
      bestNode = cur
    }
    for (const [dx, dz, cost] of neighbors) {
      const nix = cix + dx
      const niz = ciz + dz
      if (!walkable(nix, niz)) continue
      if (dx !== 0 && dz !== 0 && (!walkable(cix + dx, ciz) || !walkable(cix, ciz + dz))) continue
      const nidx = idx(nix, niz)
      if (closed[nidx]) continue
      const ng = g[cur] + cost
      if (ng < g[nidx]) {
        parent[nidx] = cur
        g[nidx] = ng
        f[nidx] = ng + hval(nix, niz)
        if (inOpen[nidx]) {
          siftUp(heapIndex[nidx])
        } else {
          inOpen[nidx] = 1
          push(nidx)
        }
      }
    }
  }
  // 目标不可达：回退到已探索到的“离终点最近的可达格”，避免直线冲向墙导致卡死。
  const raw: THREE.Vector3[] = []
  let c = bestNode
  while (c !== -1) {
    const ix = c % cols
    const iz = Math.floor(c / cols)
    raw.push(new THREE.Vector3(cellCenterX(ix), 0, cellCenterZ(iz)))
    c = parent[c]
  }
  raw.reverse()
  if (raw.length <= 1) return [end.clone()]
  return smoothPath(nav, raw)
}
