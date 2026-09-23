/**
 * 个人空间：三个悬浮窗（自习坞 / 待办 / 日期）的开关、尺寸、位置。
 * 存 localStorage zjxt.space；待办、日期各自存键，不登录。
 */
import { reactive, ref, watch } from 'vue'

export const SPACE_KEY = 'zjxt.space'
export const TODOS_KEY = 'zjxt.todos'
export const DATES_KEY = 'zjxt.dates'

export const WIN_IDS = ['study', 'todo', 'date']

export const WIN_META = {
  study: { title: '自习坞' },
  todo: { title: '待办事项' },
  date: { title: '日期' },
}

const SIZE_MAX = 3

function defaultWin(id, vw, vh) {
  const compact = vw <= 430
  const cascade = {
    study: 0,
    todo: 1,
    date: 2,
  }
  const i = cascade[id] || 0
  if (compact) {
    return {
      on: true,
      collapsed: true,
      size: 1,
      x: Math.max(8, vw - 184),
      y: 268 + i * 40,
    }
  }
  const col = i < 2 ? 0 : 1
  const row = i % 2
  return {
    on: true,
    collapsed: false,
    size: 1,
    x: Math.max(16, vw - 292 - col * 280),
    y: 72 + row * 256,
  }
}

function blankState() {
  const vw = typeof window === 'undefined' ? 1280 : window.innerWidth
  const vh = typeof window === 'undefined' ? 800 : window.innerHeight
  const windows = {}
  WIN_IDS.forEach((id) => {
    windows[id] = defaultWin(id, vw, vh)
  })
  return { windows, zSeq: 110 }
}

function loadSpace() {
  const base = blankState()
  try {
    const raw = localStorage.getItem(SPACE_KEY)
    if (!raw) return base
    const saved = JSON.parse(raw)
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
  } catch (_) {
    /* 损坏则走默认 */
  }
  return base
}

function loadList(key) {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    const data = JSON.parse(raw)
    return Array.isArray(data) ? data : []
  } catch (_) {
    return []
  }
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

const todos = ref(loadList(TODOS_KEY))
const dateNotes = reactive(loadDates())

let persistTimer = 0
function persistSpace() {
  try {
    localStorage.setItem(
      SPACE_KEY,
      JSON.stringify({
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

function schedulePersist() {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(persistSpace, 80)
}

watch(windows, schedulePersist, { deep: true })
watch(todos, persistTodos, { deep: true })
watch(dateNotes, persistDates, { deep: true })

function clampPos(id, x, y) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const minY = vw <= 430 ? 220 : 8
  return {
    x: Math.min(Math.max(8, x), Math.max(8, vw - 48)),
    y: Math.min(Math.max(minY, y), Math.max(minY, vh - 36)),
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

function resetLayout() {
  const next = blankState()
  WIN_IDS.forEach((id) => {
    windows[id].x = next.windows[id].x
    windows[id].y = next.windows[id].y
    windows[id].size = 1
    windows[id].collapsed = false
    windows[id].on = true
  })
}

export function useSpace() {
  return {
    WIN_IDS,
    WIN_META,
    SIZE_MAX,
    windows,
    zOrder,
    panelOpen,
    todos,
    dateNotes,
    setOn,
    shrink,
    grow,
    moveTo,
    bringFront,
    resetLayout,
  }
}
