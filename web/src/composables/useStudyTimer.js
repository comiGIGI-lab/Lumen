/**
 * 自习计时器单例：自习坞与沙漏共用 remaining / running。
 * 场景 UI 仍在自习坞；混音也挂在这里，关掉自习坞时声音不会断。
 */
import { computed, reactive, ref } from 'vue'
import { SOUNDS, soundSrc } from '@/study/catalog'

export const FOCUS_PRESETS = [5, 10, 15, 25, 50]
const MIN_MIN = 1
const MAX_MIN = 180

const presetMin = ref(25)
const customMin = ref(40)
const usingCustom = ref(false)
const remaining = ref(25 * 60)
const durationSec = ref(25 * 60)
const running = ref(false)
const volumes = reactive(Object.fromEntries(SOUNDS.map((s) => [s.id, 0])))
const players = {}

let tick = null

function clampMin(n) {
  const v = Math.round(Number(n) || 0)
  return Math.min(MAX_MIN, Math.max(MIN_MIN, v))
}

function padClock(sec) {
  const s = Math.max(0, Math.floor(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
}

function ensurePlayer(id) {
  if (players[id]) return players[id]
  const el = new Audio(soundSrc(id))
  el.loop = true
  el.preload = 'none'
  players[id] = el
  return el
}

function playMix() {
  SOUNDS.forEach((s) => {
    const vol = volumes[s.id] / 100
    const el = ensurePlayer(s.id)
    if (vol <= 0) {
      el.pause()
      return
    }
    el.volume = Math.min(1, vol)
    if (el.paused && running.value) {
      const p = el.play()
      if (p && typeof p.catch === 'function') p.catch(() => {})
    }
  })
}

function pauseMix() {
  Object.values(players).forEach((el) => el.pause())
}

function clearTick() {
  if (tick) {
    clearInterval(tick)
    tick = null
  }
}

function currentMinutes() {
  return usingCustom.value ? clampMin(customMin.value) : presetMin.value
}

function applyDuration(min) {
  const sec = clampMin(min) * 60
  durationSec.value = sec
  if (!running.value) remaining.value = sec
}

function pickPreset(min) {
  usingCustom.value = false
  presetMin.value = min
  applyDuration(min)
}

function applyCustom(min) {
  usingCustom.value = true
  customMin.value = clampMin(min)
  applyDuration(customMin.value)
}

function start() {
  if (remaining.value <= 0) remaining.value = currentMinutes() * 60
  if (durationSec.value <= 0) durationSec.value = remaining.value || currentMinutes() * 60
  running.value = true
  playMix()
  clearTick()
  tick = setInterval(() => {
    if (remaining.value <= 1) {
      remaining.value = 0
      running.value = false
      clearTick()
      pauseMix()
      return
    }
    remaining.value -= 1
  }, 1000)
}

function pause() {
  running.value = false
  clearTick()
  pauseMix()
}

function toggle() {
  if (running.value) pause()
  else start()
}

function onVolume(id, val) {
  volumes[id] = Number(val)
  if (running.value) playMix()
  else {
    const el = players[id]
    if (el && volumes[id] <= 0) el.pause()
  }
}

const clock = computed(() => padClock(remaining.value))
const mixCount = computed(() => SOUNDS.filter((s) => volumes[s.id] > 0).length)
const ratio = computed(() => {
  if (durationSec.value <= 0) return 0
  return Math.min(1, Math.max(0, remaining.value / durationSec.value))
})

export function useStudyTimer() {
  return {
    FOCUS_PRESETS,
    SOUNDS,
    presetMin,
    customMin,
    usingCustom,
    remaining,
    durationSec,
    running,
    volumes,
    clock,
    mixCount,
    ratio,
    pickPreset,
    applyCustom,
    start,
    pause,
    toggle,
    onVolume,
    playMix,
    pauseMix,
  }
}
