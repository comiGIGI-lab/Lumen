<script setup>
/**
 * SceneBackdrop —— 自习场景底层
 * 有本地循环视频则播视频；没有则 CSS + canvas 做该场景气质的流动。
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

function paint(ts) {
  const c = canvasEl.value
  const s = props.scene
  if (!c || !s) {
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
  <div class="backdrop" :class="{ on: !!scene }" aria-hidden="true">
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
    <div class="scrim"></div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.45s ease;
}

.backdrop.on {
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
  background: rgba(251, 249, 246, 0.28);
}
</style>
