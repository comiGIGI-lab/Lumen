/**
 * 自习计时器单例：自习坞标题栏与正文共用 remaining / running。
 * 场景 UI 仍在自习坞；混音也挂在这里，关掉自习坞时声音不会断。
 */
import { computed, reactive, ref, watch } from 'vue'
import { MUSIC, SCENES, SOUNDS, musicSrc, scenePoster, sceneVideo, soundSrc } from '@/study/catalog'
import { useAuth } from '@/composables/useAuth'
import { keyedStorage } from '@/composables/ownerTag'

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
const sceneId = ref('')
const musicId = ref('')
const musicVolume = ref(50)
const players = {}
let musicPlayer = null

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

function ensureMusic() {
  if (musicPlayer) return musicPlayer
  const el = new Audio()
  el.loop = true
  el.preload = 'none'
  musicPlayer = el
  return el
}

function playMusic() {
  const el = ensureMusic()
  const id = musicId.value
  const vol = musicVolume.value / 100
  if (!id || vol <= 0) {
    el.pause()
    return
  }
  const src = musicSrc(id)
  if (!el.src.endsWith(src)) el.src = src
  el.volume = Math.min(1, vol)
  if (el.paused && running.value) {
    const p = el.play()
    if (p && typeof p.catch === 'function') p.catch(() => {})
  }
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
  playMusic()
}

function pauseMix() {
  Object.values(players).forEach((el) => el.pause())
  if (musicPlayer) musicPlayer.pause()
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
  sessionMinutes = Math.round(durationSec.value / 60)
  running.value = true
  playMix()
  clearTick()
  tick = setInterval(() => {
    if (remaining.value <= 1) {
      remaining.value = 0
      running.value = false
      clearTick()
      pauseMix()
      if (sessionCallback) {
        try {
          sessionCallback(sessionMinutes)
        } catch (_) {
          /* 回调出错不阻塞 */
        }
      }
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

function pickScene(id) {
  sceneId.value = sceneId.value === id ? '' : id
}

function onVolume(id, val) {
  volumes[id] = Number(val)
  if (running.value) playMix()
  else {
    const el = players[id]
    if (el && volumes[id] <= 0) el.pause()
  }
}

function pickMusic(id) {
  musicId.value = musicId.value === id ? '' : id
  if (running.value) playMusic()
  else if (musicPlayer && !musicId.value) musicPlayer.pause()
}

function onMusicVolume(val) {
  musicVolume.value = Number(val)
  if (running.value) playMusic()
  else if (musicPlayer && musicVolume.value <= 0) musicPlayer.pause()
}

const clock = computed(() => padClock(remaining.value))
const mixCount = computed(() => {
  const env = SOUNDS.filter((s) => volumes[s.id] > 0).length
  const music = musicId.value && musicVolume.value > 0 ? 1 : 0
  return env + music
})

/**
 * 自习完整跑完钩子：start() 起点记下本次 durationMin，每秒扣时，remaining<=1 时
 * 调 fireSessionComplete(minutes) 给外部注册的回调；App.vue 那边注册并走 logExp。
 * 没注册回调也不会报错。
 */
let sessionMinutes = 0
let sessionCallback = null
function onSessionComplete(cb) {
  sessionCallback = typeof cb === 'function' ? cb : null
}
const scene = computed(() => {
  const s = SCENES.find((item) => item.id === sceneId.value)
  if (!s) return null
  return {
    id: s.id,
    name: s.name,
    sky: s.sky,
    glow: s.glow,
    mist: s.mist,
    poster: scenePoster(s.id),
    video: sceneVideo(s.id),
  }
})
const ratio = computed(() => {
  if (durationSec.value <= 0) return 0
  return Math.min(1, Math.max(0, remaining.value / durationSec.value))
})

// ---------- 自习设置持久化（按账号分档，只存浏览器本地） ----------
//
// 用户诉求：上次选的自习音乐 / 音量 / 场景，刷新浏览器后依然是这个设定。
// 全部存 localStorage（zjxt.study.<u:用户名|anon>），不占服务器空间（2G 机器
// 压力点在内存与知识库文件，这类个性化小状态坚决不上传）。
// 登录态变化时自动换档重载（token 里的用户名变了 → 存储 key 变）。

const STUDY_KEY = 'zjxt.study'

function studyKey() {
  return keyedStorage(STUDY_KEY)
}

function saveStudyPrefs() {
  try {
    localStorage.setItem(studyKey(), JSON.stringify({
      sceneId: sceneId.value,
      musicId: musicId.value,
      musicVolume: musicVolume.value,
      volumes: { ...volumes },
    }))
  } catch (_) {
    /* 隐私模式写不进去就算了 */
  }
}

function loadStudyPrefs() {
  let data = null
  try {
    data = JSON.parse(localStorage.getItem(studyKey()) || 'null')
  } catch (_) {
    /* 损坏就当没存过 */
  }
  sceneId.value = data && typeof data.sceneId === 'string' ? data.sceneId : ''
  musicId.value = data && typeof data.musicId === 'string' ? data.musicId : ''
  const mv = data && Number(data.musicVolume)
  musicVolume.value = Number.isFinite(mv) ? Math.min(100, Math.max(0, mv)) : 50
  for (const s of SOUNDS) {
    const v = data && data.volumes ? Number(data.volumes[s.id]) : 0
    volumes[s.id] = Number.isFinite(v) ? Math.min(100, Math.max(0, v)) : 0
  }
}

loadStudyPrefs()
watch([sceneId, musicId, musicVolume], saveStudyPrefs)
watch(() => JSON.stringify(volumes), saveStudyPrefs)
// 登录 / 登出后换档重载（useAuth 的 user 在 /me 回来后才填上用户名）
{
  const { user } = useAuth()
  watch(() => user.value.username, loadStudyPrefs)
}

export function useStudyTimer() {
  return {
    FOCUS_PRESETS,
    SOUNDS,
    MUSIC,
    presetMin,
    customMin,
    usingCustom,
    remaining,
    durationSec,
    running,
    volumes,
    sceneId,
    scene,
    musicId,
    musicVolume,
    clock,
    mixCount,
    ratio,
    pickScene,
    pickPreset,
    applyCustom,
    start,
    pause,
    toggle,
    onVolume,
    pickMusic,
    onMusicVolume,
    playMix,
    pauseMix,
    onSessionComplete,
  }
}
