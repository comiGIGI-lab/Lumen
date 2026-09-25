/**
 * useTheme —— 明暗主题
 *
 * 实现方式：在 <html> 上打 data-theme="dark"，
 * 具体配色全交给 global.css 的 [data-theme="dark"] 变量块，
 * JS 这边只管「切换 + 记住 + 首次跟随系统」。
 *
 * 为什么不用 class：data-* 属性语义更清楚，也方便将来加
 * data-theme="sepia" 之类的第三套主题而不必再想类名。
 */
import { computed, ref } from 'vue'

const KEY = 'zjxt.theme'

/** 已生效的主题（'light' | 'dark'） */
const theme = ref('light')

/** 只初始化一次 —— 多个组件同时调 useTheme() 不该重复读 localStorage */
let inited = false

function apply(next) {
  const t = next === 'dark' ? 'dark' : 'light'
  theme.value = t

  // 防御：SSR / 测试环境里的 document 可能是残缺的桩（没有 dataset），
  // 直接 delete dataset.theme 会抛 TypeError 把整个组件拖垮。
  if (typeof document !== 'undefined' && document.documentElement) {
    const el = document.documentElement
    if (el.dataset) {
      // 亮色时移除属性而不是写 "light"，这样 :root 的默认值直接生效
      if (t === 'dark') el.dataset.theme = 'dark'
      else delete el.dataset.theme
    }
  }

  try {
    localStorage.setItem(KEY, t)
  } catch (_) {
    /* 隐私模式下写不了，忽略即可 */
  }
}

function readSaved() {
  try {
    return localStorage.getItem(KEY) || ''
  } catch (_) {
    return ''
  }
}

function systemPrefersDark() {
  try {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
  } catch (_) {
    return false
  }
}

export function useTheme() {
  if (!inited && typeof window !== 'undefined') {
    inited = true
    const saved = readSaved()
    // 用户没选过就跟随系统偏好，选过就以用户为准
    apply(saved || (systemPrefersDark() ? 'dark' : 'light'))
  }

  return {
    theme,
    isDark: computed(() => theme.value === 'dark'),
    toggle: () => apply(theme.value === 'dark' ? 'light' : 'dark'),
    set: apply,
  }
}
