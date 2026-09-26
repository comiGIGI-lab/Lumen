/**
 * 课程浏览历史：PlanPanel 顶部「最近学过」快捷入口用。
 * 不调 API，只读本地 localStorage：
 *   zjxt.course_history: [{ name, profile, ts }, ...]，最多 MAX 条，超出按时间淘汰最旧。
 *
 * 去重键 = 课程名 + 画像指纹（同课同画像只保留最新一条顶置；同课不同画像可并存）。
 * 点击 chip 会带上当时的 profile 重新 generate（use_cache=true，命中则秒回）。
 */
import { ref, watch } from 'vue'

export const HISTORY_KEY = 'zjxt.course_history'
export const MAX = 50

const GOAL_PRESETS = ['考试', '项目', '兴趣', '考研', '考证']

function load() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const data = JSON.parse(raw)
    if (!Array.isArray(data)) return []
    return data
      .filter((e) => e && typeof e.name === 'string' && e.name.trim())
      .map((e) => ({
        name: e.name.trim(),
        profile: slim(e.profile || {}),
        ts: Number(e.ts) || 0,
      }))
      .slice(0, MAX)
  } catch (_) {
    return []
  }
}

function save(list) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, MAX)))
  } catch (_) {
    /* 配额满不阻塞 */
  }
}

export function minutesFromProfile(profile) {
  const n = Number(profile?.daily_minutes)
  if (Number.isFinite(n) && n > 0) return Math.round(n)
  const h = String(profile?.daily_hours || '').trim()
  const hours = h.match(/^(\d+(?:\.\d+)?)\s*h$/i)
  if (hours) return Math.round(parseFloat(hours[1]) * 60)
  const mins = h.match(/^(\d+)\s*min$/i)
  if (mins) return parseInt(mins[1], 10)
  return 60
}

function hoursLabel(minutes) {
  const min = Number(minutes) || 60
  if (min >= 60) {
    const h = Math.round((min / 60) * 10) / 10
    return `${h}h`
  }
  return `${min}min`
}

export function slim(profile) {
  if (!profile || typeof profile !== 'object') {
    return { level: '', daily_minutes: 60, daily_hours: '1h', goal: '', goal_other: '', deadline: '' }
  }
  const daily_minutes = minutesFromProfile(profile)
  const rawGoal = String(profile.goal || '').trim()
  const isOther = rawGoal === '其他' || (rawGoal !== '' && !GOAL_PRESETS.includes(rawGoal))
  const goal_other = isOther
    ? String(profile.goal_other || (rawGoal === '其他' ? '' : rawGoal) || '').trim()
    : String(profile.goal_other || '').trim()
  return {
    level: String(profile.level || '').trim(),
    daily_minutes,
    daily_hours: profile.daily_hours || hoursLabel(daily_minutes),
    goal: isOther ? '其他' : rawGoal,
    goal_other,
    deadline: String(profile.deadline || '').trim(),
  }
}

/** 与后端 cache_store「课程名 + 画像」对齐的稳定指纹（不含 ts） */
export function profileFingerprint(profile) {
  const p = slim(profile)
  return [p.level, String(p.daily_minutes), p.goal, p.goal_other, p.deadline].join('|')
}

export function entryKey(name, profile) {
  return `${String(name || '').trim()}::${profileFingerprint(profile)}`
}

const history = ref(load())

watch(
  history,
  (list) => save(list),
  { deep: true },
)

function record(name, profile) {
  const clean = String(name || '').trim()
  if (!clean) return
  const stored = slim(profile)
  const key = entryKey(clean, stored)
  const filtered = history.value.filter((e) => entryKey(e.name, e.profile) !== key)
  filtered.unshift({ name: clean, profile: stored, ts: Date.now() })
  if (filtered.length > MAX) filtered.length = MAX
  history.value = filtered
}

function list() {
  return [...history.value].sort((a, b) => (b.ts || 0) - (a.ts || 0))
}

function clear() {
  history.value = []
}

export function usePlanHistory() {
  return {
    HISTORY_KEY,
    MAX,
    history,
    record,
    list,
    clear,
    slim,
    profileFingerprint,
    entryKey,
  }
}
