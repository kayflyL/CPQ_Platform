<template>
  <canvas ref="cv" class="ck-stars" aria-hidden="true" />
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'

// Canvas star twinkle layer for the cockpit sky scene.
// Falls back to a single static frame under prefers-reduced-motion.
const cv = ref<HTMLCanvasElement | null>(null)
let raf = 0

type Star = { x: number; y: number; r: number; ph: number; sp: number }
let stars: Star[] = []
let dpr = 1

function resize() {
  const parent = cv.value?.parentElement
  if (!parent || !cv.value) return
  dpr = window.devicePixelRatio || 1
  cv.value.width = Math.max(1, Math.round(parent.clientWidth * dpr))
  cv.value.height = Math.max(1, Math.round(parent.clientHeight * dpr))
}

function draw(t: number) {
  const el = cv.value
  if (!el) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const w = el.width, h = el.height
  ctx.clearRect(0, 0, w, h)
  for (const s of stars) {
    const a = reduce ? 0.7 : 0.35 + 0.35 * (1 + Math.sin(t / 1000 * s.sp + s.ph)) * 0.5
    ctx.globalAlpha = a
    ctx.fillStyle = '#cfe0ff'
    ctx.beginPath()
    ctx.arc(s.x * w, s.y * h, s.r * dpr, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalAlpha = 1
}

const reduce = typeof window !== 'undefined'
  && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

onMounted(() => {
  const el = cv.value
  if (!el) return
  resize()
  const rand = (n: number) => Math.random() * n
  stars = Array.from({ length: 170 }, () => ({
    x: rand(1), y: rand(1), r: 0.5 + rand(1.1),
    ph: rand(Math.PI * 2), sp: 0.4 + rand(1.2),
  }))
  if (reduce) { draw(0); return }
  const loop = (t: number) => { draw(t); raf = requestAnimationFrame(loop) }
  raf = requestAnimationFrame(loop)
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.ck-stars { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
