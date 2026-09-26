/**
 * 个人空间：三个悬浮窗（自习坞 / 待办 / 日期）的开关、尺寸、位置。
 * 存 localStorage zjxt.space；待办、日期、日倒数各自存键，不登录。
 * SPACE_VER 加一后旧坐标不再锁死，会落到新默认。
 * v5 起桌面默认展开；刷新 / 换页只保留窗口开关，位置和折叠回到当前 layout 默认。
 * welcome / app / study 三套 x/y/size/collapsed 分开存；待办正文和倒数日走别的键。
 */
import { computed, reactive, ref, watch } from 'vue'

export const SPACE_KEY = 'zjxt.space'
export const TODOS_KEY = 'zjxt.todos'
export const DATES_KEY = 'zjxt.dates'
export const COUNTDOWNS_KEY = 'zjxt.countdowns'
export const SPACE_VER = 7
export const LAYOUTS = ['welcome', 'app', 'study']

export const WIN_IDS = ['study', 'todo', 'date']

export const WIN_META = {
  // title 保留中文原文作兜底；titleKey 供界面按语言取值
  study: { title: '自习坞', titleKey: 'win.study' },
  todo: { title: '待办事项', titleKey: 'win.todo' },
  date: { title: '日期', titleKey: 'win.date' },
}

export const WIDTH_FACTOR_MOBILE = 0.6
export const WIDTH_FACTOR_DESKTOP = 1.0
export const TOP_SAFE_DESKTOP = 8
export const TOP_SAFE_MOBILE = 0

export function getWidthFactor(compact, id) {
  if (compact && (id === 'study' || id === 'todo')) {
    return WIDTH_FACTOR_MOBILE
  }
  return WIDTH_FACTOR_DESKTOP
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

function barWidthRaw(collapsed, size, compact, layout, id) {
  const { vw } = viewport()
  const maxW = Math.max(160, vw - 16)
  const widthFactor = getWidthFactor(compact, id)
  if (collapsed) {
    if (id === 'todo' || id === 'date') {
      const base = compact ? 196 : 248
      return Math.round(Math.min(base * widthFactor, maxW))
    }
    const base = compact ? 136 : 176
    return Math.round(Math.min(base * widthFactor, maxW))
  }
  if (layout === 'study') {
    const padX = compact ? 8 : vw <= 860 ? 16 : 26
    const total = Math.min(980, Math.max(200, vw - padX * 2))
    const factor = size === 3 ? 1 : size === 2 ? 0.92 : 0.8
    if (vw <= 860) {
      const minW = compact ? Math.round(200 * widthFactor) : 280
      const rawW = Math.min(total, vw - padX * 2) * factor * widthFactor
      return Math.round(Math.max(minW, Math.min(rawW, maxW)))
    }
    const leftW = Math.round(total * 1.1 / 2)
    const rightW = Math.max(280, total - leftW - 14)
    const base = id === 'study' ? leftW : rightW
    const minW = id === 'study' ? 360 : 280
    return Math.round(Math.max(minW, base * factor))
  }
  const desktop = 216 + (Math.max(1, size) - 1) * 64
  if (compact) {
    const base = Math.max(176, desktop - 24)
    return Math.round(Math.min(base * widthFactor, maxW))
  }
  return Math.min(desktop, maxW)
}

/** 倒数日窗比其他浮窗再宽 40%（收成探头时仍是竖签，不加宽）。 */
function barWidth(collapsed, size, compact, layout, id) {
  const width = barWidthRaw(collapsed, size, compact, layout, id)
  if (collapsed || id !== 'date') return width
  const { vw } = viewport()
  const maxW = Math.max(160, vw - 16)
  return Math.round(Math.min(maxW, width * 1.4))
}

function defaultWin(id, vw, layout) {
  const compact = vw <= 430
  if (layout === 'study') {
    const stack = vw <= 860
    const padX = compact ? 8 : vw <= 860 ? 16 : 26
    const padY = compact ? HEADER_H + 88 : HEADER_H + 16
    const gap = 14
    const total = Math.min(980, Math.max(200, vw - padX * 2))
    if (stack) {
      const stacked = {
        study: 0,
        todo: compact ? 52 : 300,
        date: compact ? 104 : 560,
      }
      return {
        on: true,
        collapsed: true,
        size: 2,  // 三块统一大小：study 原为 3（344px），与另两块不一致
        x: padX,
        y: padY + (stacked[id] || 0),
      }
    }
    const leftW = Math.round(total * 1.1 / 2)
    const rightX = padX + leftW + gap
    if (id === 'study') {
      return { on: true, collapsed: true, size: 2, x: padX, y: padY }
    }
    if (id === 'todo') {
      return { on: true, collapsed: true, size: 2, x: rightX, y: padY }
    }
    return { on: true, collapsed: true, size: 2, x: rightX, y: padY + 280 }
  }
  const cascade = { study: 0, todo: 1, date: 2 }
  const i = cascade[id] || 0
  // 默认一律收成边签（贴边成窄条），需要时再展开 —— 免得三块窗盖住正文。
  const collapsed = compact
  const size = 1
  const w = barWidth(collapsed, size, compact, layout, id)
  const gap = compact ? 6 : 12
  const y0 = layout === 'app' ? (compact ? HEADER_H + 88 : HEADER_H + 6) : compact ? HEADER_H + 88 : 12
  if (compact) {
    return {
      on: true,
      collapsed,
      size,
      x: 8,
      y: y0 + i * 52,
    }
  }
  const step = w + gap
  return {
    on: true,
    collapsed,
    size,
    x: Math.max(8, 12 + i * step),
    y: y0,
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

/** 刷新 / 导航只保留开关；位置和折叠回到当前 layout 的默认。 */
function mergeOnOnly(base, saved) {
  const next = cloneWins(base)
  WIN_IDS.forEach((id) => {
    const w = saved?.[id]
    if (!w || typeof w !== 'object') return
    if ('on' in w) next[id].on = w.on !== false
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
    zSeq: 132,
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
    if ((ver === SPACE_VER || ver === 4 || ver === 3) && saved?.layouts && typeof saved.layouts === 'object') {
      LAYOUTS.forEach((key) => {
        // 坐标、折叠不跟刷新走：只把「开 / 关」从旧存档接回来。
        base.layouts[key] = mergeOnOnly(base.layouts[key], saved.layouts[key])
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
      base.layouts[oldMode] = mergeOnOnly(base.layouts[oldMode], saved.windows)
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
const zOrder = reactive(Object.fromEntries(WIN_IDS.map((id, i) => [id, 129 + i])))
let zSeq = boot.zSeq || 132
const panelOpen = ref(false)
/** 左下「空间」钮本会话是否收到左边签。刷新 / 换页会清掉。 */
const fabDocked = ref(false)
const viewW = ref(typeof window === 'undefined' ? 1280 : window.innerWidth)
const viewH = ref(typeof window === 'undefined' ? 800 : window.innerHeight)

if (typeof window !== 'undefined') {
  let resizeTimer = 0
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      viewW.value = window.innerWidth
      viewH.value = window.innerHeight
    }, 50)
  })
}

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
  const vw = viewW.value
  const vh = viewH.value
  const w = windows[id]
  const compact = vw <= 430
  const width = w ? barWidth(w.collapsed, w.size, compact, layoutMode.value, id) : 176
  const margin = 8
  const topSafe = compact ? TOP_SAFE_MOBILE : TOP_SAFE_DESKTOP
  const minY = topSafe
  const maxX = Math.max(margin, vw - Math.min(width, vw - margin * 2) - margin)
  const maxY = Math.max(minY, vh - 44)
  return {
    x: Math.min(Math.max(margin, x), maxX),
    y: Math.min(Math.max(minY, y), maxY),
  }
}

function bringFront(id) {
  zSeq += 1
  if (zSeq > 139) {
    WIN_IDS.forEach((wid, i) => {
      zOrder[wid] = 129 + i
    })
    zSeq = 132
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
  bringFront(id)
  // 一次 − 就收到边签。继续缩小尺寸走已展开时的再次 −。
  if (!w.collapsed) {
    w.collapsed = true
    return
  }
}

function grow(id) {
  const w = windows[id]
  bringFront(id)
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

function resetPetPos() {
  fabDocked.value = false
  try {
    localStorage.removeItem('zjxt.pet_pos')
  } catch (_) {
    /* ignore */
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('zjxt:reset-layout'))
  }
}

function setFabDocked(on) {
  fabDocked.value = !!on
}

function applyLayout(mode) {
  const nextMode = normalizeLayout(mode)
  layoutMode.value = nextMode
  const fresh = defaultWins(nextMode)
  writeWins(windows, fresh)
  writeWins(layouts[nextMode], fresh)
  persistSpace()
  resetPetPos()
}

function resetLayout() {
  const mode = normalizeLayout(layoutMode.value)
  const fresh = defaultWins(mode)
  writeWins(windows, fresh)
  writeWins(layouts[mode], fresh)
  persistSpace()
  resetPetPos()
}

function startOfDay(ts) {
  const d = new Date(ts)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

function daysUntil(ymd, now = Date.now()) {
  const date = parseYmd(ymd)
  if (!date) return null
  const [y, mo, d] = date.split('-').map(Number)
  const target = new Date(y, mo - 1, d)
  return Math.round((startOfDay(target) - startOfDay(now)) / 86400000)
}

/** 最近一条未到期倒数日（不含今天、不含已过）。 */
const nearestCountdown = computed(() => {
  let best = null
  countdowns.value.forEach((item) => {
    const days = daysUntil(item.date)
    if (days == null || days < 0) return
    if (!best || days < best.days) best = { id: item.id, title: item.title, date: item.date, days }
  })
  return best
})

const dateWinTitle = computed(() => {
  const n = nearestCountdown.value
  if (!n) return ''
  if (n.days === 0) return `距 ${n.title} 就是今天`
  return `距 ${n.title} 还有 ${n.days} 天`
})

export function useSpace() {
  const widthFactor = computed(() => (viewW.value <= 430 ? WIDTH_FACTOR_MOBILE : WIDTH_FACTOR_DESKTOP))
  return {
    WIN_IDS,
    WIN_META,
    SIZE_MAX,
    SPACE_VER,
    WIDTH_FACTOR_MOBILE,
    WIDTH_FACTOR_DESKTOP,
    widthFactor,
    windows,
    zOrder,
    panelOpen,
    fabDocked,
    setFabDocked,
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
    nearestCountdown,
    dateWinTitle,
    clampPos,
    viewW,
    viewH,
    parseYmd,
  }
}
