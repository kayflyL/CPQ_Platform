<template>
  <article
    class="or-card"
    tabindex="0"
    :style="{ '--or-color': color }"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @focus="onEnter"
    @blur="onLeave"
    @keyup.enter.prevent="open"
    @keyup.space.prevent="open"
    @click="open"
  >
    <div class="or-accent-bar"></div>
    <div class="or-copy">
      <h3 class="or-name">{{ name }}</h3>
      <div class="or-role">{{ roleKey }}</div>
      <div class="or-bio"><p>{{ opening }}</p></div>
    </div>

    <div class="or-stage" v-show="active" aria-hidden="true">
      <canvas ref="glEl" class="or-gl" v-show="active"></canvas>
      <Live2dPreview
        v-if="alive"
        class="or-live"
        :class="{ 'is-on': living }"
        :model-key="petModel"
        :bg-color="color"
      />
    </div>
  </article>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { getLive2dSnapshot } from '@/utils/l2dSnapshot'
import Live2dPreview from '@/components/assistant/Live2dPreview.vue'

const props = defineProps<{ colleague: any }>()
const emit = defineEmits<{ (e: 'open'): void }>()

const glEl = ref<HTMLCanvasElement | null>(null)

const active = ref(false)
const revealed = ref(false)
const alive = ref(false)
const living = ref(false)

const name = computed(() => props.colleague?.name || props.colleague?.role_key || '')
const roleKey = computed(() => props.colleague?.role_key || '')
const opening = computed(() => props.colleague?.opening_message || '')
const color = computed(() => props.colleague?.color || '#1677ff')
const petModel = computed(() => props.colleague?.pet_model || 'koharu')

let gl: WebGLRenderingContext | null = null
let program: WebGLProgram | null = null
let texture: WebGLTexture | null = null
let quadBuf: WebGLBuffer | null = null
let uniforms: Record<string, WebGLUniformLocation | null> = {}
let tween: number | null = null
let progress = 0
let origin = { x: 0.5, y: 0.5 }
let snap: HTMLImageElement | HTMLCanvasElement | null = null
let textureSrc: HTMLImageElement | HTMLCanvasElement | null = null

const VERT = `
attribute vec2 a_position;
varying vec2 v_uv;
void main() {
  v_uv = vec2(a_position.x * 0.5 + 0.5, 0.5 - a_position.y * 0.5);
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`;

const FRAG = `
precision highp float;

uniform sampler2D u_image;
uniform vec2 u_resolution;
uniform vec2 u_imageSize;
uniform vec2 u_center;
uniform float u_progress;
uniform vec3 u_bgColor;

varying vec2 v_uv;

float hash21(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int index = 0; index < 4; index++) {
    value += amplitude * valueNoise(p);
    p *= 2.0;
    amplitude *= 0.5;
  }
  return value;
}

vec2 coverUv(vec2 uv, vec2 imageSize, vec2 resolution) {
  float imageAspect = imageSize.x / imageSize.y;
  float canvasAspect = resolution.x / resolution.y;
  vec2 scale = vec2(1.0);
  if (canvasAspect > imageAspect) {
    scale.y = imageAspect / canvasAspect;
  } else {
    scale.x = canvasAspect / imageAspect;
  }
  return (uv - 0.5) * scale + 0.5;
}

void main() {
  vec2 uv = v_uv;
  float aspect = u_resolution.x / u_resolution.y;
  vec2 point = uv - u_center;
  point.x *= aspect;

  float distanceFromCenter = length(point);
  float maxDistance = length(vec2(0.5 * aspect, 0.5));
  float normalizedDistance = clamp(distanceFromCenter / maxDistance, 0.0, 1.0);
  float largeNoise = fbm(point * 4.0 + vec2(u_progress, u_progress * 0.5));
  float smallNoise = valueNoise(point * 12.0 + vec2(u_progress * 2.0, -u_progress * 1.5));
  float warpGate = smoothstep(0.0, 0.05, u_progress);
  float warpedDistance = normalizedDistance
    + (largeNoise - 0.5) * 1.0 * warpGate
    + (smallNoise - 0.5) * 0.9 * warpGate;

  float waveFront = u_progress * 1.6;
  float delta = warpedDistance - waveFront;
  float baseEnvelope = exp(-delta * delta / (2.0 * 0.15 * 0.15));
  float ripples = max(0.0, cos(delta * 5.0));
  float envelope = baseEnvelope * ripples;
  envelope *= smoothstep(0.0, 0.05, u_progress) * (1.0 - smoothstep(0.85, 1.0, u_progress));

  vec2 direction = distanceFromCenter > 0.001 ? normalize(point) : vec2(0.0);
  vec2 displacement = direction * envelope * 0.145;
  displacement.x /= aspect;
  vec2 chroma = direction * envelope * 0.02;
  chroma.x /= aspect;

  vec2 uvRed = coverUv(uv - displacement - chroma, u_imageSize, u_resolution);
  vec2 uvGreen = coverUv(uv - displacement, u_imageSize, u_resolution);
  vec2 uvBlue = coverUv(uv - displacement + chroma, u_imageSize, u_resolution);

  vec4 red = texture2D(u_image, uvRed);
  vec4 green = texture2D(u_image, uvGreen);
  vec4 blue = texture2D(u_image, uvBlue);
  vec3 imgColor = vec3(red.r, green.g, blue.b);
  float imgAlpha = (red.a + green.a + blue.a) / 3.0;
  vec3 color = mix(u_bgColor, imgColor, imgAlpha);

  float feather = 0.04 + 0.05 * largeNoise;
  float reveal = 1.0 - smoothstep(waveFront - feather, waveFront + feather, warpedDistance);
  reveal *= smoothstep(0.0, 0.05, u_progress);
  reveal = mix(reveal, 1.0, smoothstep(0.88, 1.0, u_progress));
  float glow = envelope * 0.73;
  color = clamp(color / max(1.0 - glow, 0.01), 0.0, 1.0);

  gl_FragColor = vec4(color, clamp(reveal, 0.0, 1.0));
}
`;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const n = parseInt(f, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v))
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function compile(type: number, src: string): WebGLShader | null {
  if (!gl) return null
  const sh = gl.createShader(type)
  if (!sh) return null
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn('[ripple] shader', gl.getShaderInfoLog(sh))
    gl.deleteShader(sh)
    return null
  }
  return sh
}

function resizeGL() {
  const canvas = glEl.value
  if (!canvas || !gl) return
  const rect = canvas.getBoundingClientRect()
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = Math.max(1, Math.round(rect.width * dpr))
  const h = Math.max(1, Math.round(rect.height * dpr))
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w
    canvas.height = h
  }
}

function ensureGL(): boolean {
  const canvas = glEl.value
  if (!canvas) return false
  if (gl && program) {
    resizeGL()
    return true
  }
  gl = canvas.getContext('webgl', {
    alpha: true,
    premultipliedAlpha: false,
    preserveDrawingBuffer: true,
  }) as WebGLRenderingContext | null
  if (!gl) return false

  const vs = compile(gl.VERTEX_SHADER, VERT)
  const fs = compile(gl.FRAGMENT_SHADER, FRAG)
  if (!vs || !fs) return false

  program = gl.createProgram()
  if (!program) return false
  gl.attachShader(program, vs)
  gl.attachShader(program, fs)
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.warn('[ripple] link', gl.getProgramInfoLog(program))
    return false
  }
  gl.useProgram(program)

  quadBuf = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
  const aPos = gl.getAttribLocation(program, 'a_position')
  gl.enableVertexAttribArray(aPos)
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0)

  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)

  uniforms = {
    u_image: gl.getUniformLocation(program, 'u_image'),
    u_resolution: gl.getUniformLocation(program, 'u_resolution'),
    u_imageSize: gl.getUniformLocation(program, 'u_imageSize'),
    u_center: gl.getUniformLocation(program, 'u_center'),
    u_progress: gl.getUniformLocation(program, 'u_progress'),
    u_bgColor: gl.getUniformLocation(program, 'u_bgColor'),
  }

  resizeGL()
  return true
}

function uploadTexture(src: HTMLImageElement | HTMLCanvasElement) {
  if (!gl || !program) return false
  if (texture) { gl.deleteTexture(texture); texture = null }
  texture = gl.createTexture()
  if (!texture) return false
  gl.bindTexture(gl.TEXTURE_2D, texture)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src as any)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  snap = src
  textureSrc = src
  return true
}

function makeFallback(): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = 420
  c.height = 420
  const ctx = c.getContext('2d')!
  const [r, g, b] = hexToRgb(color.value)
  const grad = ctx.createLinearGradient(0, 0, c.width, c.height)
  grad.addColorStop(0, 'rgb(' + r + ',' + g + ',' + b + ')')
  grad.addColorStop(1, 'rgba(' + r + ',' + g + ',' + b + ',0.72)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.fillStyle = 'rgba(255,255,255,0.92)'
  ctx.font = '700 150px "Segoe UI", sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText((name.value || '\u00b7').slice(0, 1), c.width / 2, c.height / 2 + 6)
  return c
}

function render() {
  if (!gl || !program || !texture) return
  const canvas = glEl.value
  if (!canvas) return
  gl.viewport(0, 0, canvas.width, canvas.height)
  gl.useProgram(program)
  gl.activeTexture(gl.TEXTURE0)
  gl.bindTexture(gl.TEXTURE_2D, texture)
  gl.uniform1i(uniforms.u_image, 0)
  gl.uniform2f(uniforms.u_resolution, canvas.width, canvas.height)
  const size = snap instanceof HTMLImageElement
    ? { w: snap.naturalWidth, h: snap.naturalHeight }
    : snap instanceof HTMLCanvasElement
      ? { w: snap.width, h: snap.height }
      : { w: canvas.width, h: canvas.height }
  gl.uniform2f(uniforms.u_imageSize, size.w, size.h)
  gl.uniform2f(uniforms.u_center, origin.x, origin.y)
  gl.uniform1f(uniforms.u_progress, progress)
  const [r, g, b] = hexToRgb(color.value)
  gl.uniform3f(uniforms.u_bgColor, r / 255, g / 255, b / 255)
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
}

function stopTween() {
  if (tween !== null) { cancelAnimationFrame(tween); tween = null }
}

function startReveal() {
  if (!active.value) return
  if (!ensureGL()) {
    revealed.value = true
    alive.value = true
    living.value = true
    return
  }
  const target = snap || makeFallback()
  if (textureSrc !== target) uploadTexture(target)
  if (!texture) return
  stopTween()
  revealed.value = false
  alive.value = false
  living.value = false
  progress = 0
  const start = performance.now()
  const DUR = 1100
  const step = (now: number) => {
    progress = Math.min((now - start) / DUR, 1)
    render()
    if (progress >= 1) {
      tween = null
      revealed.value = true
      alive.value = true
      nextTick(() => { living.value = true })
      return
    }
    tween = requestAnimationFrame(step)
  }
  tween = requestAnimationFrame(step)
}

function onEnter(ev: Event) {
  const card = ev.currentTarget as HTMLElement
  if (!card) return
  const rect = card.getBoundingClientRect()
  if (ev instanceof MouseEvent) {
    origin.x = clamp01((ev.clientX - rect.left) / rect.width)
    origin.y = clamp01((ev.clientY - rect.top) / rect.height)
  } else {
    origin.x = 0.5
    origin.y = 0.5
  }
  active.value = true
  if (prefersReducedMotion()) {
    revealed.value = true
    alive.value = true
    living.value = true
    return
  }
  nextTick(() => startReveal())
}

function onLeave() {
  stopTween()
  active.value = false
  revealed.value = false
  alive.value = false
  living.value = false
  progress = 0
}

function open() {
  emit('open')
}

function destroyGL() {
  stopTween()
  if (gl) {
    if (texture) gl.deleteTexture(texture)
    if (quadBuf) gl.deleteBuffer(quadBuf)
    if (program) gl.deleteProgram(program)
  }
  gl = null
  program = null
  texture = null
  quadBuf = null
  uniforms = {}
  snap = null
  textureSrc = null
}

onMounted(() => {
  getLive2dSnapshot(petModel.value).then((url) => {
    if (!url) return
    const img = new Image()
    img.onload = () => {
      snap = img
      if (gl && program) uploadTexture(img)
    }
    img.src = url
  }).catch(() => {})
})

onBeforeUnmount(() => {
  destroyGL()
})
</script>

<style scoped>
.or-card {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.25s var(--cpq-ease-out-expo), box-shadow 0.25s var(--cpq-ease-out-expo), border-color 0.25s var(--cpq-ease-out-expo);
}
.or-card:hover,
.or-card:focus-visible {
  transform: translateY(-3px);
  box-shadow: var(--cpq-glass-card-shadow-glow);
  border-color: var(--cpq-glass-border-strong);
  outline: none;
}
.or-accent-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 4;
  background: var(--cpq-accent-primary);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.3s var(--cpq-ease-out-expo);
}
.or-card:hover .or-accent-bar {
  transform: scaleX(1);
}
.or-copy {
  position: relative;
  z-index: 1;
  padding: 18px;
  background: transparent;
}
.or-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  margin: 0;
  line-height: 1.35;
}
.or-role {
  font-size: 13px;
  color: var(--cpq-text-muted);
  margin-top: 10px;
}
.or-bio p {
  font-size: 13px;
  color: var(--cpq-text-muted);
  line-height: 1.6;
  margin: 10px 0 0;
}
.or-stage {
  position: absolute;
  inset: 0;
  z-index: 2;
}
.or-gl {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.or-live {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  transition: opacity 0.5s ease;
  z-index: 3;
}
.or-live.is-on {
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .or-card { transition: none; }
  .or-live { transition: none; }
}
</style>
