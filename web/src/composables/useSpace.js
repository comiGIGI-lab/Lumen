/**
 * 个人空间：三个悬浮窗（自习坞 / 待办 / 日期）的开关、尺寸、位置。
 * 存 localStorage zjxt.space；待办、日期、日倒数各自存键，不登录。
 * SPACE_VER 加一后旧坐标不再锁死，会落到新默认。
 * welcome / app / study 三套 x/y/size/collapsed 分开存；待办正文和倒数日走别的键。
 */
import { reactive, ref, watch } from 'vue'

export const SPACE_KEY = 'zjxt.space'
export const TODOS_KEY = 'zjxt.todos'
export const DATES_KEY = 'zjxt.dates'
export const COUNTDOWNS_KEY = 'zjxt.countdowns'
export const SPACE_VER = 3
export const LAYOUTS = ['welcome', 'app', 'study']

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

function normalizeLayout(mode) {
  if (mode === 'study') return 'study'
  if (mode === 'app') return 'app'
  return 'welcome'
}

function barWidth(collapsed, size, compact, layout, id) {
  if (collapsed) {
    if (id === 'todo' || id === 'date') return compact ? 196 : 248
    return compact ? 118 : 176
  }
  if (layout === 'study') {
    const { vw } = viewport()
    const padX = vw <= 430 ? 8 : 26
    const total = Math.min(980, Math.max(280, vw - padX * 2))
    const factor = size === 3 ? 1 : size === 2 ? 0.92 : 0.8
    if (vw <= 860) {
      return Math.round(Math.max(280, Math.min(total, vw - padX * 2) * factor))
    }
    const leftW = Math.round(total * 1.1 / 2)
    const rightW = Math.max(280, total - leftW - 14)
    const base = id === 'study' ? leftW : rightW
    const minW = id === 'study' ? 360 : 280
    return Math.round(Math.max(minW, base * factor))
  }
  return 216 + (Math.max(1, size) - 1) * 64
}

function defaultWin(id, vw, layout) {
  if (layout === 'study') {
    const stack = vw <= 860
    const padX = vw <= 430 ? 8 : 26
    const padY = HEADER_H + 16
    const gap = 14
    const total = Math.min(980, Math.max(280, vw - padX * 2))
    if (stack) {
      const h = { study: 0, todo: 300, date: 560 }
      return {
        on: true,
        collapsed: false,
        size: id === 'study' ? 3 : 2,
        x: padX,
        y: padY + (h[id] || 0),
      }
    }
    const leftW = Math.round(total * 1.1 / 2)
    const rightX = padX + leftW + gap
    if (id === 'study') {
      return { on: true, collapsed: false, size: 3, x: padX, y: padY }
    }
    if (id === 'todo') {
      return { on: true, collapsed: false, size: 2, x: rightX, y: padY }
    }
    return { on: true, collapsed: false, size: 2, x: rightX, y: padY + 280 }
  }
  const compact = vw <= 430
  const cascade = { study: 0, todo: 1, date: 2 }
  const i = cascade[id] || 0
  const collapsed = layout === 'app' || compact
  const size = 1
  const w = barWidth(collapsed, size, compact, layout, id)
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

function defaultWins(layout) {
  const { vw } = viewport()
  const windows = {}
  WIN_IDS.forEach((id) => {
    windows[id] = defaultWin(id, vw, layout)
  })
  return windows
}

function cloneWins(src) {
  const out = {}
  WIN_IDS.forEach((id) => {
    const w = src?.[id] || {}
    out[id] = {
      on: w.on !== false,
      collapsed: !!w.collapsed,
      size: Math.min(SIZE_MAX, Math.max(1, Number(w.size) || 1)),
      x: Number.isFinite(w.x) ? w.x : 12,
      y: Number.isFinite(w.y) ? w.y : 12,
    }
  })
  return out
}

function mergeWins(base, saved) {
  const next = cloneWins(base)
  WIN_IDS.forEach((id) => {
    const w = saved?.[id]
    if (!w || typeof w !== 'object') return
    next[id] = {
      ...next[id],
      on: w.on !== false,
      collapsed: !!w.collapsed,
      size: Math.min(SIZE_MAX, Math.max(1, Number(w.size) || 1)),
      x: Number.isFinite(w.x) ? w.x : next[id].x,
      y: Number.isFinite(w.y) ? w.y : next[id].y,
    }
  })
  return next
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
  const layouts = {
    welcome: defaultWins('welcome'),
    app: defaultWins('app'),
    study: defaultWins('study'),
  }
  return {
    ver: SPACE_VER,
    layout: normalizeLayout(layout),
    layouts,
    windows: layouts[normalizeLayout(layout)],
    zSeq: 110,
  }
}

function loadSpace() {
  const layout = initialLayout()
  const base = blankState(layout)
  try {
    const raw = localStorage.getItem(SPACE_KEY)
    if (!raw) return base
    const saved = JSON.parse(raw)
    const ver = Number(saved?.ver)
    if (ver === SPACE_VER && saved?.layouts && typeof saved.layouts === 'object') {
      LAYOUTS.forEach((key) => {
        base.layouts[key] = mergeWins(base.layouts[key], saved.layouts[key])
      })
      if (saved.layout === 'welcome' || saved.layout === 'app' || saved.layout === 'study') {
        base.layout = saved.layout
      }
      if (Number.isFinite(saved.zSeq)) base.zSeq = saved.zSeq
      base.windows = base.layouts[base.layout]
      return base
    }
    if (ver === 2 && saved?.windows) {
      const oldMode = saved.layout === 'app' ? 'app' : 'welcome'
      base.layouts[oldMode] = mergeWins(base.layouts[oldMode], saved.windows)
      if (oldMode === layout) base.layout = oldMode
      if (Number.isFinite(saved.zSeq)) base.zSeq = saved.zSeq
      base.windows = base.layouts[base.layout]
      return base
    }
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
const layouts = {
  welcome: reactive(boot.layouts.welcome),
  app: reactive(boot.layouts.app),
  study: reactive(boot.layouts.study),
}
const layoutMode = ref(boot.layout || 'welcome')
const windows = reactive(cloneWins(boot.windows))
const zOrder = reactive(Object.fromEntries(WIN_IDS.map((id, i) => [id, 110 + i])))
let zSeq = boot.zSeq || 114
const panelOpen = ref(false)

const todos = ref(loadList(TODOS_KEY))
const dateNotes = reactive(loadDates())
const countdowns = ref(loadCountdowns())

let persistTimer = 0
function persistSpace() {
  try {
    writeWins(layouts[normalizeLayout(layoutMode.value)], snapshotWins(windows))
    localStorage.setItem(
      SPACE_KEY,
      JSON.stringify({
        ver: SPACE_VER,
        layout: layoutMode.value,
        layouts,
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

function snapshotWins(src) {
  return cloneWins(src)
}

function writeWins(target, src) {
  WIN_IDS.forEach((id) => {
    const w = src[id]
    target[id].on = w.on
    target[id].collapsed = w.collapsed
    target[id].size = w.size
    target[id].x = w.x
    target[id].y = w.y
  })
}

function applyLayout(mode) {
  const nextMode = normalizeLayout(mode)
  if (layoutMode.value === nextMode) {
    persistSpace()
    return
  }
  writeWins(layouts[layoutMode.value], snapshotWins(windows))
  layoutMode.value = nextMode
  writeWins(windows, snapshotWins(layouts[nextMode]))
  persistSpace()
}

function resetLayout() {
  const mode = normalizeLayout(layoutMode.value)
  const fresh = defaultWins(mode)
  writeWins(windows, fresh)
  writeWins(layouts[mode], fresh)
  persistSpace()
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
