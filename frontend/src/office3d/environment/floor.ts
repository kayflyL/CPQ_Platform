/**
 * 地板与网格。（R3a 自 Office3DCanvas 抽出，逻辑逐行等价）
 * 原 SFC 模块级 environment 全局改为 parent 参数由调用方传入。
 */
import * as THREE from 'three'
import type { OfficeEnvironmentTheme } from '@/api/office'

export function createWoodFloorTexture(baseColor: string): THREE.CanvasTexture {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.fillStyle = baseColor
    ctx.fillRect(0, 0, size, size)
    const plankW = 32
    const plankColors = ['#00000022', '#ffffff18', '#00000014', '#ffffff0c']
    for (let x = 0; x < size; x += plankW) {
      const shade = plankColors[(x / plankW) % plankColors.length]
      ctx.fillStyle = shade
      ctx.fillRect(x, 0, plankW, size)
      ctx.strokeStyle = 'rgba(60,40,20,0.28)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x + 0.5, 0)
      ctx.lineTo(x + 0.5, size)
      ctx.stroke()
      const seamY = ((x / plankW) * 97 + 40) % size
      ctx.beginPath()
      ctx.moveTo(x, seamY)
      ctx.lineTo(x + plankW, seamY)
      ctx.stroke()
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'
    ctx.lineWidth = 1
    for (let y = 0; y < size; y += 4) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(size, y)
      ctx.stroke()
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.anisotropy = 4
  return texture
}

export function buildFloor(theme: OfficeEnvironmentTheme, width: number, depth: number, parent: THREE.Group | null) {
  if (!parent) return
  const floorColor = theme.palette?.floor || '#151c29'
  const wood = createWoodFloorTexture(floorColor)
  const plankTile = 2.4
  wood.repeat.set(Math.max(4, Math.round(width / plankTile)), Math.max(4, Math.round(depth / plankTile)))
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: wood,
    roughness: theme.preset === 'midnight' ? 0.68 : 0.72,
    metalness: 0.04,
  })
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.position.y = 0
  floor.receiveShadow = true
  parent.add(floor)

  const officeGrid = createRectangularGrid(
    width,
    depth,
    Math.max(1, Math.round(Math.max(width, depth))),
    floorColor,
    0.013,
  )
  parent.add(officeGrid)
}

export function createRectangularGrid(width: number, depth: number, divisions: number, color: string, y = 0.012): THREE.LineSegments {
  const maxDimension = Math.max(width, depth)
  const step = maxDimension / Math.max(1, divisions)
  const points: THREE.Vector3[] = []

  for (let x = -width / 2; x <= width / 2 + 0.001; x += step) {
    points.push(new THREE.Vector3(x, 0, -depth / 2), new THREE.Vector3(x, 0, depth / 2))
  }
  for (let z = -depth / 2; z <= depth / 2 + 0.001; z += step) {
    points.push(new THREE.Vector3(-width / 2, 0, z), new THREE.Vector3(width / 2, 0, z))
  }

  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const material = new THREE.LineBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.26,
  })
  const grid = new THREE.LineSegments(geometry, material)
  grid.position.y = y
  return grid
}
