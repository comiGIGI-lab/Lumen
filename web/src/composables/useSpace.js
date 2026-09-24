/**
 * 个人空间：三个悬浮窗（自习坞 / 待办 / 日期）的开关、尺寸、位置。
 * 存 localStorage zjxt.space；待办、日期、日倒数各自存键，不登录。
 * SPACE_VER 加一后旧坐标不再锁死，会落到新默认。
 */
import { reactive, ref, watch } from 'vue'

export const SPACE_KEY = 'zjxt.space'
export const TODOS_KEY = 'zjxt.todos'
export const DATES_KEY = 'zjxt.dates'
export const COUNTDOWNS_KEY = 'zjxt.countdowns'
export const SPACE_VER = 2

export const WIN_IDS = ['study', 'todo', 'date']

export const WIN_META = {
  study: { title: '自习坞' },
  todo: { title: '待办事项' },
  date: { title: '日期' },
}

const SIZE_MAX = 3
const HEADER_H = 64

function viewport() {
  return {
    vw: typeof window === 'undefined' ? 1280 : window.innerWidth,
    vh: typeof window === 'undefined' ? 800 : window.innerHeight,
  }
}

function barWidth(collapsed, size, compact) {
  if (collapsed) return compact ? 118 : 176
  return 216 + (Math.max(1, size) - 1) * 64
}

function defaultWin(id, vw, layout) {
  const compact = vw <= 430
  const cascade = { study: 0, todo: 1, date: 2 }
  const i = cascade[id] || 0
  const collapsed = layout === 'app' || compact
  const size = 1
  const w = barWidth(collapsed, size, compact)
  const gap = compact ? 6 : 12
  const y = layout === 'app' ? HEADER_H + 6 : 12
  const step = compact ? Math.min(w + gap, Math.max(96, (vw - 16 - w) / 2)) : w + gap
  return {
    on: true,
    collapsed,
    size,
    x: Math.max(8, 12 + i * step),
    y,
  }
}

function initialLayout() {
  try {
    const qs = new URLSearchParams(window.location.search)
    if (qs.get('welcome') === '1') return 'welcome'
    if (localStorage.getItem('zjxt.welcomed')) return 'app'
  } catch (_) {
    /* ignore */
  }
  return 'welcome'
}

function blankState(layout = initialLayout()) {
  const { vw } = viewport()
  const windows = {}
  WIN_IDS.forEach((id) => {
    windows[id] = defaultWin(id, vw, layout)
  })
  return { ver: SPACE_VER, windows, zSeq: 110, layout }
}

function loadSpace() {
  const base = blankState()
  try {
    const raw = localStorage.getItem(SPACE_KEY)
    if (!raw) return base
    const saved = JSON.parse(raw)
    if (saved?.ver !== SPACE_VER) return base
    WIN_IDS.forEach((id) => {
      const w = saved?.windows?.[id]
      if (!w || typeof w !== 'object') return
      base.windows[id] = {
        ...base.windows[id],
        on: w.on !== false,
        collapsed: !!w.collapsed,
        size: Math.min(SIZE_MAX, Math.max(1, Number(w.size) || 1)),
        x: Number.isFinite(w.x) ? w.x : base.windows[id].x,
        y: Number.isFinite(w.y) ? w.y : base.windows[id].y,
      }
    })
    if (Number.isFinite(saved.zSeq)) base.zSeq = saved.zSeq
    if (saved.layout === 'app' || saved.layout === 'welcome') base.layout = saved.layout
  } catch (_) {
    /* 损坏则走默认 */
  }
  return base
}

function parseYmd(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || '').slice(0, 10))
  if (!m) return ''
  const y = Number(m[1])
  const mo = Number(m[2]) - 1
  const d = Number(m[3])
  const t = new Date(y, mo, d)
  if (t.getFullYear() !== y || t.getMonth() !== mo || t.getDate() !== d) return ''
  return `${m[1]}-${m[2]}-${m[3]}`
}

function loadList(key) {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    const data = JSON.parse(raw)
    if (!Array.isArray(data)) return []
    if (key === TODOS_KEY) {
      let pinnedSeen = false
      return data.map((item) => {
        if (!item || typeof item !== 'object') return item
        const pinned = !pinnedSeen && !!item.pinned
        if (pinned) pinnedSeen = true
        return { ...item, pinned }
      })
    }
    return data
  } catch (_) {
    return []
  }
}

function normalizeCountdown(item, fallbackId) {
  if (typeof item === 'string') {
    const date = parseYmd(item)
    if (!date) return null
    return { id: fallbackId, title: '目标日', date }
  }
  if (!item || typeof item !== 'object') return null
  const date = parseYmd(item.date)
  if (!date) return null
  const title = String(item.title || '目标日').trim().slice(0, 20) || '目标日'
  return { id: item.id || fallbackId, title, date }
}

function loadCountdowns() {
  try {
    const raw = localStorage.getItem(COUNTDOWNS_KEY)
    if (!raw) return []
    const data = JSON.parse(raw)
    if (typeof data === 'string') {
      const item = normalizeCountdown(data, Date.now())
      return item ? [item] : []
    }
    if (Array.isArray(data)) {
      const list = []
      data.forEach((item, i) => {
        const n = normalizeCountdown(item, Date.now() + i)
        if (n) list.push(n)
      })
      return list
    }
    if (data && typeof data === 'object') {
      const item = normalizeCountdown(data, Date.now())
      return item ? [item] : []
    }
  } catch (_) {
    /* ignore */
  }
  return []
}

function loadDates() {
  try {
    const raw = localStorage.getItem(DATES_KEY)
    if (!raw) return {}
    const data = JSON.parse(raw)
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {}
  } catch (_) {
    return {}
  }
}

const boot = loadSpace()
const windows = reactive(boot.windows)
const zOrder = reactive(Object.fromEntries(WIN_IDS.map((id, i) => [id, 110 + i])))
let zSeq = boot.zSeq || 114
const panelOpen = ref(false)
const layoutMode = ref(boot.layout || 'welcome')

const todos = ref(loadList(TODOS_KEY))
const dateNotes = reactive(loadDates())
const countdowns = ref(loadCountdowns())

let persistTimer = 0
function persistSpace() {
  try {
    localStorage.setItem(
      SPACE_KEY,
      JSON.stringify({
        ver: SPACE_VER,
        layout: layoutMode.value,
        windows,
        zSeq,
      }),
    )
  } catch (_) {
    /* 配额满不阻塞 */
  }
}

function persistTodos() {
  try {
    localStorage.setItem(TODOS_KEY, JSON.stringify(todos.value))
  } catch (_) {
    /* ignore */
  }
}

function persistDates() {
  try {
    localStorage.setItem(DATES_KEY, JSON.stringify(dateNotes))
  } catch (_) {
    /* ignore */
  }
}

function persistCountdowns() {
  try {
    localStorage.setItem(COUNTDOWNS_KEY, JSON.stringify(countdowns.value))
  } catch (_) {
    /* ignore */
  }
}

function schedulePersist() {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(persistSpace, 80)
}

watch(windows, schedulePersist, { deep: true })
watch(todos, persistTodos, { deep: true })
watch(dateNotes, persistDates, { deep: true })
watch(countdowns, persistCountdowns, { deep: true })

function clampPos(id, x, y) {
  const { vw, vh } = viewport()
  return {
    x: Math.min(Math.max(8, x), Math.max(8, vw - 48)),
    y: Math.min(Math.max(8, y), Math.max(8, vh - 36)),
  }
}

function bringFront(id) {
  zSeq += 1
  if (zSeq > 125) {
    WIN_IDS.forEach((wid, i) => {
      zOrder[wid] = 110 + i
    })
    zSeq = 114
  }
  zOrder[id] = zSeq
  persistSpace()
}

function setOn(id, on) {
  windows[id].on = !!on
  if (on) bringFront(id)
}

function shrink(id) {
  const w = windows[id]
  if (!w.collapsed && w.size <= 1) {
    w.collapsed = true
    return
  }
  if (w.collapsed) return
  w.size = Math.max(1, w.size - 1)
}

function grow(id) {
  const w = windows[id]
  if (w.collapsed) {
    w.collapsed = false
    return
  }
  w.size = Math.min(SIZE_MAX, w.size + 1)
}

function moveTo(id, x, y) {
  const c = clampPos(id, x, y)
  windows[id].x = Math.round(c.x)
  windows[id].y = Math.round(c.y)
}

function applyLayout(mode) {
  const nextMode = mode === 'app' ? 'app' : 'welcome'
  layoutMode.value = nextMode
  const next = blankState(nextMode)
  WIN_IDS.forEach((id) => {
    windows[id].x = next.windows[id].x
    windows[id].y = next.windows[id].y
    windows[id].size = next.windows[id].size
    windows[id].collapsed = next.windows[id].collapsed
  })
  persistSpace()
}

function resetLayout() {
  applyLayout(layoutMode.value)
  WIN_IDS.forEach((id) => {
    windows[id].on = true
  })
}

export function useSpace() {
  return {
    WIN_IDS,
    WIN_META,
    SIZE_MAX,
    SPACE_VER,
    windows,
    zOrder,
    panelOpen,
    layoutMode,
    todos,
    dateNotes,
    countdowns,
    setOn,
    shrink,
    grow,
    moveTo,
    bringFront,
    resetLayout,
    applyLayout,
    barWidth,
    parseYmd,
  }
}
