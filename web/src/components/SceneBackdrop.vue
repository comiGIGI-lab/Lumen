<script setup>
/**
 * SceneBackdrop —— 自习场景底层
 * 未选场景：米色上半透明俄罗斯方块缓慢漂浮。
 * 有场景：本地循环视频；缺文件走该场景气质的流动兜底。
 * 禁止热链，缺文件不破页。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  scene: { type: Object, default: null },
})

const videoEl = ref(null)
const canvasEl = ref(null)
const useVideo = ref(false)
let raf = 0
let t0 = 0

const SHAPES = {
  I: [[0, 1], [1, 1], [2, 1], [3, 1]],
  O: [[0, 0], [1, 0], [0, 1], [1, 1]],
  T: [[1, 0], [0, 1], [1, 1], [2, 1]],
  S: [[1, 0], [2, 0], [0, 1], [1, 1]],
  Z: [[0, 0], [1, 0], [1, 1], [2, 1]],
  J: [[0, 0], [0, 1], [1, 1], [2, 1]],
  L: [[2, 0], [0, 1], [1, 1], [2, 1]],
}

const FILLS = [
  'rgba(229, 21, 32, 0.14)',
  'rgba(229, 21, 32, 0.09)',
  'rgba(255, 255, 255, 0.46)',
  'rgba(248, 243, 236, 0.78)',
  'rgba(229, 21, 32, 0.11)',
  'rgba(255, 248, 240, 0.58)',
]

const idlePieces = [
  { x: 0.14, y: 0.18, s: 0.048, speed: 0.11, phase: 0.4, rot: 0.05, spin: 0, shape: 'T', fill: FILLS[0] },
  { x: 0.62, y: 0.12, s: 0.056, speed: 0.08, phase: 1.7, rot: -0.04, spin: 1, shape: 'L', fill: FILLS[1] },
  { x: 0.80, y: 0.48, s: 0.042, speed: 0.13, phase: 2.6, rot: 0.07, spin: 2, shape: 'S', fill: FILLS[2] },
  { x: 0.28, y: 0.58, s: 0.050, speed: 0.09, phase: 3.8, rot: -0.06, spin: 0, shape: 'J', fill: FILLS[3] },
  { x: 0.48, y: 0.32, s: 0.038, speed: 0.16, phase: 5.1, rot: 0.09, spin: 3, shape: 'Z', fill: FILLS[4] },
  { x: 0.08, y: 0.74, s: 0.052, speed: 0.07, phase: 0.9, rot: -0.03, spin: 1, shape: 'I', fill: FILLS[5] },
  { x: 0.86, y: 0.26, s: 0.040, speed: 0.14, phase: 4.2, rot: 0.11, spin: 2, shape: 'O', fill: FILLS[0] },
  { x: 0.58, y: 0.76, s: 0.046, speed: 0.10, phase: 2.1, rot: -0.08, spin: 0, shape: 'T', fill: FILLS[2] },
  { x: 0.36, y: 0.12, s: 0.034, speed: 0.12, phase: 3.3, rot: 0.06, spin: 1, shape: 'S', fill: FILLS[1] },
  { x: 0.72, y: 0.64, s: 0.044, speed: 0.09, phase: 1.2, rot: -0.05, spin: 3, shape: 'L', fill: FILLS[4] },
]

function rotateCell(x, y, times) {
  let a = x
  let b = y
  for (let i = 0; i < (times % 4); i += 1) {
    const nx = 3 - b
    const ny = a
    a = nx
    b = ny
  }
  return [a, b]
}

function paintIdle(ctx, w, h, t) {
  ctx.fillStyle = '#FBF9F6'
  ctx.fillRect(0, 0, w, h)
  const mist = ctx.createRadialGradient(w * 0.7, h * 0.18, 20, w * 0.7, h * 0.18, Math.max(w, h) * 0.62)
  mist.addColorStop(0, 'rgba(229, 21, 32, 0.06)')
  mist.addColorStop(1, 'rgba(251, 249, 246, 0)')
  ctx.fillStyle = mist
  ctx.fillRect(0, 0, w, h)

  idlePieces.forEach((p) => {
    const cell = Math.min(w, h) * p.s
    const dx = Math.sin(t * p.speed + p.phase) * 28
    const dy = Math.cos(t * p.speed * 0.82 + p.phase) * 22
    const x = w * p.x + dx
    const y = h * p.y + dy
    const cells = SHAPES[p.shape] || SHAPES.T
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(Math.sin(t * p.rot + p.phase) * 0.18)
    ctx.shadowColor = 'rgba(229, 21, 32, 0.18)'
    ctx.shadowBlur = 22
    ctx.fillStyle = p.fill
    ctx.strokeStyle = 'rgba(229, 21, 32, 0.16)'
    ctx.lineWidth = 1
    cells.forEach(([cx, cy]) => {
      const [rx, ry] = rotateCell(cx, cy, p.spin)
      const px = (rx - 1.5) * cell
      const py = (ry - 1.5) * cell
      ctx.fillRect(px, py, cell - 2, cell - 2)
      ctx.strokeRect(px, py, cell - 2, cell - 2)
    })
    ctx.restore()
  })
}

function paintScene(ctx, w, h, t, s) {
  const sky = s.sky || '#191919'
  const glow = s.glow || '#e51520'
  const mist = s.mist || '#4a4540'
  ctx.fillStyle = sky
  ctx.fillRect(0, 0, w, h)
  const drift = (a, speed, ox, oy, r) => {
    const x = w * (0.5 + 0.38 * Math.sin(t * speed + ox))
    const y = h * (0.48 + 0.28 * Math.cos(t * speed * 0.7 + oy))
    const g = ctx.createRadialGradient(x, y, 0, x, y, r)
    g.addColorStop(0, a)
    g.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, w, h)
  }
  drift(hexA(glow, 0.38), 0.11, 0.2, 1.1, Math.max(w, h) * 0.42)
  drift(hexA(mist, 0.32), 0.07, 2.4, 0.4, Math.max(w, h) * 0.5)
  drift(hexA(glow, 0.16), 0.16, 4.1, 3.2, Math.max(w, h) * 0.28)
  ctx.fillStyle = hexA('#000000', 0.12 + 0.04 * Math.sin(t * 0.3))
  ctx.fillRect(0, 0, w, h)
}

function paint(ts) {
  const c = canvasEl.value
  if (!c) {
    raf = requestAnimationFrame(paint)
    return
  }
  const ctx = c.getContext('2d')
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = c.clientWidth
  const h = c.clientHeight
  if (c.width !== Math.floor(w * dpr) || c.height !== Math.floor(h * dpr)) {
    c.width = Math.floor(w * dpr)
    c.height = Math.floor(h * dpr)
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (!t0) t0 = ts
  const t = (ts - t0) / 1000
  if (props.scene) paintScene(ctx, w, h, t, props.scene)
  else paintIdle(ctx, w, h, t)
  raf = requestAnimationFrame(paint)
}

function hexA(hex, a) {
  const h = (hex || '#000').replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r},${g},${b},${a})`
}

function tryVideo() {
  useVideo.value = false
  const el = videoEl.value
  if (!el || !props.scene) return
  el.src = props.scene.video
  const onOk = () => {
    useVideo.value = true
  }
  const onFail = () => {
    useVideo.value = false
  }
  el.onloadeddata = onOk
  el.onerror = onFail
  el.load()
  const p = el.play()
  if (p && typeof p.catch === 'function') p.catch(onFail)
}

watch(
  () => props.scene && props.scene.id,
  async () => {
    await nextTick()
    tryVideo()
  },
)

onMounted(() => {
  raf = requestAnimationFrame(paint)
  tryVideo()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
})
</script>

<template>
  <div class="backdrop on" :class="{ scene: !!scene }" aria-hidden="true">
    <canvas ref="canvasEl" class="flow"></canvas>
    <video
      v-if="scene"
      ref="videoEl"
      class="vid"
      :class="{ show: useVideo }"
      :poster="scene.poster"
      muted
      loop
      playsinline
      preload="metadata"
    ></video>
    <div class="scrim" :class="{ scene: !!scene }"></div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 1;
}

.flow,
.vid {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.vid {
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.4s ease;
}

.vid.show {
  opacity: 1;
}

.scrim {
  position: absolute;
  inset: 0;
  background: rgba(251, 249, 246, 0.18);
}

.scrim.scene {
  background: rgba(251, 249, 246, 0.28);
}
</style>
