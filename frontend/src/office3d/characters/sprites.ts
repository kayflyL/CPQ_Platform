/**
 * 角色头顶标签/气泡精灵。（R4a 自 Office3DCanvas 抽出，逻辑逐行等价）
 * drawBubble 的状态色/文案由调用方注入（原内部读 SFC 配置访问器）。
 */
import * as THREE from 'three'

export function makeLabelSprite(text: string, color: string) {
  const canvas = document.createElement('canvas')
  canvas.width = 320
  canvas.height = 80
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas 2d context unavailable')

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const radius = 16
  ctx.beginPath()
  ctx.moveTo(radius, 0)
  ctx.lineTo(canvas.width - radius, 0)
  ctx.quadraticCurveTo(canvas.width, 0, canvas.width, radius)
  ctx.lineTo(canvas.width, canvas.height - radius)
  ctx.quadraticCurveTo(canvas.width, canvas.height, canvas.width - radius, canvas.height)
  ctx.lineTo(radius, canvas.height)
  ctx.quadraticCurveTo(0, canvas.height, 0, canvas.height - radius)
  ctx.lineTo(0, radius)
  ctx.quadraticCurveTo(0, 0, radius, 0)
  ctx.closePath()
  ctx.fillStyle = 'rgba(8, 12, 20, 0.72)'
  ctx.fill()

  ctx.beginPath()
  ctx.arc(20, canvas.height / 2, 6, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.fill()

  ctx.font = 'bold 26px "Segoe UI", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#eaf0f8'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 40, canvas.height / 2)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false }),
  )
  sprite.scale.set(1.55, 0.39, 1)
  sprite.position.y = 2.22

  return { sprite, texture, canvas }
}

export function makeBubbleSprite() {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 128
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas 2d context unavailable')

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false }),
  )
  sprite.scale.set(1.75, 0.44, 1)
  sprite.position.y = 1.58

  return { sprite, texture, canvas, ctx }
}

export interface BubbleActor {
  bubbleCtx: CanvasRenderingContext2D
  bubbleCanvas: HTMLCanvasElement
  bubbleTexture: THREE.CanvasTexture
}

export function drawBubble(actor: BubbleActor, activity: string, message: string, statusColor: number, statusLabel: string) {
  const ctx = actor.bubbleCtx
  const canvas = actor.bubbleCanvas
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const color = `#${new THREE.Color(statusColor).getHexString()}`
  const statusText = statusLabel
  const detail = message || activity || ''
  let text = statusText
  if (detail && detail !== statusText) text = `${statusText} · ${detail}`
  if (text.length > 20) text = `${text.slice(0, 18)}…`

  const radius = 18
  ctx.beginPath()
  ctx.moveTo(radius, 0)
  ctx.lineTo(canvas.width - radius, 0)
  ctx.quadraticCurveTo(canvas.width, 0, canvas.width, radius)
  ctx.lineTo(canvas.width, canvas.height - radius)
  ctx.quadraticCurveTo(canvas.width, canvas.height, canvas.width - radius, canvas.height)
  ctx.lineTo(radius, canvas.height)
  ctx.quadraticCurveTo(0, canvas.height, 0, canvas.height - radius)
  ctx.lineTo(0, radius)
  ctx.quadraticCurveTo(0, 0, radius, 0)
  ctx.closePath()

  ctx.fillStyle = 'rgba(10, 16, 26, 0.86)'
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 4
  ctx.stroke()

  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(30, canvas.height / 2, 8, 0, Math.PI * 2)
  ctx.fill()

  ctx.font = 'bold 38px "Segoe UI", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#f3f6fb'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 52, canvas.height / 2)

  actor.bubbleTexture.needsUpdate = true
}
