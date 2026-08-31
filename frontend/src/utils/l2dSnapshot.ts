import { petModelPath, isPetModelKey } from '@/store/petModel'

type Lib = any

const frameCache = new Map<string, string | null>()
const inflight = new Map<string, Promise<string | null>>()
let chain: Promise<unknown> = Promise.resolve()
let scriptPromise: Promise<Lib> | null = null

function loadLib(): Promise<Lib> {
  const w = window as any
  if (w.L2D_WIDGET) return Promise.resolve(w.L2D_WIDGET)
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise<Lib>((resolve, reject) => {
    const s = document.createElement('script')
    s.src = '/vendor/l2d-widget.min.js'
    s.onload = () => {
      if (w.L2D_WIDGET) resolve(w.L2D_WIDGET)
      else reject(new Error('L2D_WIDGET is not defined'))
    }
    s.onerror = () => reject(new Error('l2d-widget load failed'))
    document.head.appendChild(s)
  })
  scriptPromise.catch(() => { scriptPromise = null })
  return scriptPromise
}

function parkWidget(box: HTMLElement) {
  box.style.position = 'fixed'
  box.style.left = '-10000px'
  box.style.top = '0'
  box.style.right = 'auto'
  box.style.bottom = 'auto'
  box.style.width = '300px'
  box.style.height = '300px'
  box.style.opacity = '0'
  box.style.pointerEvents = 'none'
  box.style.zIndex = '-1'
}

function dominantCanvas(box: HTMLElement): HTMLCanvasElement | null {
  const list = Array.from(box.querySelectorAll('canvas')) as HTMLCanvasElement[]
  if (list.length === 0) return null
  return list.sort((a, b) => b.width * b.height - a.width * a.height)[0]
}

async function captureFrame(modelKey: string): Promise<string | null> {
  let lib: Lib
  try {
    lib = await loadLib()
  } catch {
    return null
  }
  let widget: any = null
  let snapCanvas: HTMLCanvasElement | null = null
  const start = Date.now()
  const probe = document.createElement('canvas')
  probe.width = 64
  probe.height = 64
  const pctx = probe.getContext('2d')
  if (!pctx) return null
  const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))
  try {
    const before = new Set<Element>(Array.from(document.body.children))
    widget = lib.createWidget({
      model: { path: petModelPath(modelKey), tips: false },
      position: 'bottom-right',
      size: 300,
      menus: { items: [] },
    })
    const appended = Array.from(document.body.children).filter((e) => !before.has(e))
    const box = appended.find(
      (e): e is HTMLElement => e instanceof HTMLElement && e.style.position === 'fixed',
    )
    if (!box) return null
    parkWidget(box)
    appended.forEach((e) => {
      if (e === box) return
      if (e instanceof HTMLElement) e.style.display = 'none'
    })
    const canvas = dominantCanvas(box)
    if (!canvas) return null
    snapCanvas = canvas
    while (Date.now() - start < 15000) {
      pctx.clearRect(0, 0, 64, 64)
      try {
        pctx.drawImage(canvas, 0, 0, 64, 64)
      } catch {
        /* drawing not ready yet */
      }
      const data = pctx.getImageData(0, 0, 64, 64).data
      let n = 0
      for (let i = 3; i < data.length; i += 4) if (data[i] >= 200) n++
      if (n > 50) {
        return canvas.toDataURL('image/png')
      }
      await delay(150)
    }
    return null
  } catch {
    return null
  } finally {
    if (widget && widget.destroy) {
      try {
        widget.destroy()
      } catch {
        /* ignore */
      }
      widget = null
    }
    if (snapCanvas) {
      try {
        const c2 = snapCanvas.getContext('webgl2')
        if (c2) {
          c2.getExtension('WEBGL_lose_context')?.loseContext()
        } else {
          const c1 = snapCanvas.getContext('webgl')
          c1?.getExtension('WEBGL_lose_context')?.loseContext()
        }
      } catch {
        /* ignore */
      }
      snapCanvas = null
    }
  }
}

export function getLive2dSnapshot(modelKey: string | null | undefined): Promise<string | null> {
  const key = modelKey || ''
  if (!isPetModelKey(key)) return Promise.resolve(null)
  const cached = frameCache.get(key)
  if (cached !== undefined) return Promise.resolve(cached)
  const running = inflight.get(key)
  if (running) return running
  const p = chain
    .then(() => captureFrame(key))
    .then((url) => {
      frameCache.set(key, url)
      inflight.delete(key)
      return url
    })
    .catch(() => {
      frameCache.set(key, null)
      inflight.delete(key)
      return null
    })
  inflight.set(key, p)
  chain = p.catch(() => {})
  return p
}
