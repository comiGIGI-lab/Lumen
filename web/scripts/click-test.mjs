/**
 * click-test.mjs —— 真正的「点击」端到端测试（无浏览器）
 *
 * 为什么需要它：
 *   SSR 只能证明「能渲染」，证明不了「点了有反应」；
 *   本机又跑不了无头浏览器。
 *   这里用 jsdom + 加载真实构建产物 + 真实 dispatch 点击事件来验证交互，
 *   是定位「点设置没反应」这类问题的唯一可靠手段。
 *
 * 用法：
 *   cd web
 *   node <vite> build --outDir dist-ct1
 *   node scripts/click-test.mjs dist-ct1
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const WEB = path.dirname(HERE)
const distName = process.argv[2] || 'dist-ct1'
const assetsDir = path.join(WEB, distName, 'assets')

if (!fs.existsSync(assetsDir)) {
  console.error(`✗ 找不到构建产物目录：${assetsDir}`)
  console.error(`  请先执行：node <vite> build --outDir ${distName}`)
  process.exit(2)
}
const jsFile = fs
  .readdirSync(assetsDir)
  .filter((f) => f.endsWith('.js'))
  .map((f) => path.join(assetsDir, f))
  .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0]
console.log('加载产物:', path.relative(WEB, jsFile))

// ---------------------------------------------------------------
// 1) jsdom：先铺好浏览器全局，再 import 产物
// ---------------------------------------------------------------
const { JSDOM } = await import('jsdom')
const dom = new JSDOM(
  '<!doctype html><html><body><div id="app"></div></body></html>',
  { url: 'http://127.0.0.1:5173/', pretendToBeVisual: true },
)
const { window } = dom

// Node 22 起 navigator 等是只读 getter，必须用 defineProperty 覆盖
const define = (key, value) =>
  Object.defineProperty(globalThis, key, { value, writable: true, configurable: true })

// ① 关键 DOM 全局必须用 jsdom 的版本（Node 自带的 Event/MouseEvent 语义不同，
//    dispatch 到 jsdom 元素上不会触发事件）
for (const key of [
  'window', 'document', 'navigator', 'location', 'history',
  'localStorage', 'sessionStorage',
  'HTMLElement', 'Element', 'Node', 'EventTarget', 'Event', 'MouseEvent',
  'KeyboardEvent', 'CustomEvent', 'MutationObserver', 'getComputedStyle',
  'requestAnimationFrame', 'cancelAnimationFrame', 'matchMedia', 'CSS',
]) {
  try {
    const v = window[key]
    if (v === undefined) continue
    define(key, typeof v === 'function' && key === 'getComputedStyle' ? v.bind(window) : v)
  } catch (_) {
    /* 个别属性不可覆盖则跳过 */
  }
}

// ② 其余产物会用到的少量 jsdom 全局（不要遍历 window 全量拷贝，
//    某些访问器会触发大量分配甚至死循环）
for (const key of [
  'MutationObserver', 'Blob', 'File', 'FileReader', 'FormData',
  'DOMParser', 'XMLHttpRequest', 'TextEncoder', 'TextDecoder',
  'CSSStyleDeclaration', 'HTMLInputElement', 'HTMLButtonElement',
  'HTMLSelectElement', 'PromiseRejectionEvent', 'DOMException',
  'SVGElement', 'MathMLElement', 'ShadowRoot', 'Document', 'DocumentFragment',
  'NodeFilter', 'Range', 'Selection', 'Image', 'URL',
]) {
  if (key in globalThis) continue
  try {
    if (typeof window[key] !== 'undefined') define(key, window[key])
  } catch (_) {
    /* 跳过 */
  }
}

// ---------------------------------------------------------------
// 2) 打桩后端：bootstrap 返回「LLM 模式但没 Key」
//    正好复现用户现在的处境
// ---------------------------------------------------------------
const BOOTSTRAP = {
  mode: {
    mode: 'llm',
    label: 'LLM 模式 · deepseek-chat',
    is_mock: false,
    has_key: false,
    api_key_masked: '',
    base_url: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    reason: '已配置 LLM 模式，但缺少 API Key',
  },
  options: { levels: ['入门'], daily_hours: ['2h'], goals: ['考试'] },
  profile: { level: '入门', daily_hours: '2h', goal: '考试', deadline: '' },
  suggested_days: 15,
  source_dir: 'X:/fake/source',
  trace_file: 'X:/fake/trace.log',
}

const fetched = []
globalThis.fetch = async (url) => {
  fetched.push(String(url))
  return { ok: true, status: 200, async json() { return BOOTSTRAP } }
}
globalThis.EventSource = class { close() {} addEventListener() {} removeEventListener() {} }

// ---------------------------------------------------------------
// 3) 加载真实产物（会自动 mount 到 #app）
// ---------------------------------------------------------------
let stage = 'before-import'
const t0 = Date.now()
const beat = setInterval(() => {
  const mb = (process.memoryUsage().heapUsed / 1048576).toFixed(0)
  console.log(`   … [${((Date.now() - t0) / 1000).toFixed(1)}s] stage=${stage} heap=${mb}MB rss=${(process.memoryUsage().rss / 1048576).toFixed(0)}MB`)
}, 1500)
beat.unref?.()

// ---------------------------------------------------------------
// 2.5) 给关键 DOM API 装计数器，用于定位同步死循环的热点
// ---------------------------------------------------------------
const counters = {}
function wrap(target, name, tag, detail) {
  const orig = target[name]
  if (typeof orig !== 'function') return
  let n = 0
  target[name] = function (...args) {
    n++
    counters[tag] = n
    if (n <= 3 || n % 20000 === 0) {
      const mb = (process.memoryUsage().heapUsed / 1048576).toFixed(0)
      const d = detail ? '  ' + detail.call(this, args) : ''
      console.log(`   ⚠ ${tag} #${n} (heap=${mb}MB)${d}`)
    }
    return orig.apply(this, args)
  }
}
const ORIG_GET_ATTR = window.Element.prototype.getAttribute
const attrDetail = function (args) {
  const el = this
  if (!el || !ORIG_GET_ATTR) return `attr="${args[0]}"`
  let cls = ''
  try { cls = ORIG_GET_ATTR.call(el, 'class') || '' } catch (_) {}
  return `<${(el.tagName || '?').toLowerCase()} class="${cls}" type="${el.type || ''}"> attr="${args[0]}"`
}
wrap(window.document, 'createElement', 'document.createElement')
wrap(window.document, 'createTextNode', 'document.createTextNode')
wrap(window.document, 'querySelector', 'document.querySelector')
wrap(window.document, 'querySelectorAll', 'document.querySelectorAll')
wrap(window.document, 'appendChild', 'document.appendChild')
wrap(window, 'getComputedStyle', 'window.getComputedStyle')
for (const k of ['appendChild', 'insertBefore', 'removeChild', 'replaceChild']) {
  wrap(window.Node.prototype, k, 'Node.' + k)
}
wrap(window.Element.prototype, 'setAttribute', 'Element.setAttribute', attrDetail)
wrap(window.Element.prototype, 'removeAttribute', 'Element.removeAttribute', attrDetail)
wrap(window.Element.prototype, 'getAttribute', 'Element.getAttribute', attrDetail)
wrap(window.Element.prototype, 'addEventListener', 'Element.addEventListener', attrDetail)

console.log('（DOM 计数器已就位）')
try {
  await import(pathToFileURL(jsFile).href)
  console.log('阶段 B：import 完成（含同步 mount）')
} catch (e) {
  console.log('阶段 B：import 抛错 ->', e.message)
}
console.log('DOM 调用统计:', JSON.stringify(counters))


const container = window.document.getElementById('app')
console.log('阶段 C：#app 子节点数 =', container ? container.childNodes.length : 'null')

const flush = (ms = 40) => new Promise((r) => setTimeout(r, ms))
stage = 'flushing'
await flush()
console.log('阶段 D：首帧刷新完成')
clearInterval(beat)

// ---------------------------------------------------------------
// 4) 断言
// ---------------------------------------------------------------
let pass = 0
let fail = 0
function check(label, ok, extra = '') {
  console.log(`${ok ? '✓' : '✗'} ${label}${extra ? '  ' + extra : ''}`)
  ok ? pass++ : fail++
}
const findButton = (text, scope = container) =>
  [...scope.querySelectorAll('button')].find((b) => (b.textContent || '').includes(text))
const click = (el) => el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))

console.log('\n--- 1. 基础渲染 ---')
check('bootstrap 已被调用', fetched.some((u) => u.includes('/bootstrap')))
check('顶栏有「设置」', !!findButton('设置'))
check('顶栏有「历史」', !!findButton('历史'))
check('顶栏有「日志」', !!findButton('日志'))
// 打桩数据是「LLM 模式但没 Key」，按设计应自动弹出设置窗引导填 Key
check('LLM 缺 Key 时自动弹设置窗', !!container.querySelector('.mask'))
const autoMask = container.querySelector('.mask')
if (autoMask) {
  check('自动弹出的是设置窗', (autoMask.textContent || '').includes('AI 模型设置'))
  const x0 = [...autoMask.querySelectorAll('button')].find((b) => (b.textContent || '').trim() === '✕')
  if (x0) { click(x0); await flush() }
}
check('关闭后无弹窗', !container.querySelector('.mask'))

console.log('\n--- 2. 点击「设置」 ---')
const settingsBtn = findButton('设置')
if (!settingsBtn) {
  console.log('  ！找不到设置按钮，后续无法继续')
} else {
  click(settingsBtn)
  await flush()
  const mask = container.querySelector('.mask')
  check('弹窗打开（.mask 出现）', !!mask)

  if (mask) {
    const txt = mask.textContent || ''
    check('标题为「AI 模型设置」', txt.includes('AI 模型设置'))
    check('含「离线 Mock 模式」', txt.includes('离线 Mock 模式'))
    check('含「在线 LLM 模式」', txt.includes('在线 LLM 模式'))
    check('含「测试连接」', txt.includes('测试连接'))
    const segs = mask.querySelectorAll('.seg-btn')
    check('两段切换按钮 = 2', segs.length === 2, `实际 ${segs.length}`)
    check('平台下拉 = 1', mask.querySelectorAll('select').length === 1)

    console.log('\n--- 3. 切换运行模式 ---')
    const mockSeg = [...segs].find((b) => (b.textContent || '').includes('Mock'))
    if (mockSeg) {
      click(mockSeg)
      await flush()
      const on = mask.querySelectorAll('.seg-btn.on')
      check('Mock 段被选中', on.length === 1 && (on[0].textContent || '').includes('Mock'))
      check('Mock 下「测试连接」置灰', !!mask.querySelector('button[disabled]'))
    }

    console.log('\n--- 4. 输入 API Key ---')
    const keyInput = [...mask.querySelectorAll('input')].find(
      (i) => (i.getAttribute('type') || '') === 'password',
    )
    check('存在密码型输入框', !!keyInput)
    if (keyInput) {
      keyInput.value = 'sk-my-own-key'
      keyInput.dispatchEvent(new window.Event('input', { bubbles: true }))
      await flush()
      check('输入值已写入', keyInput.value === 'sk-my-own-key')
    }

    console.log('\n--- 5. 反复开关 ---')
    const x = [...mask.querySelectorAll('button')].find((b) => (b.textContent || '').trim() === '✕')
    if (x) {
      click(x)
      await flush()
      check('关闭成功', !container.querySelector('.mask'))
      click(findButton('设置'))
      await flush()
      check('可再次打开', !!container.querySelector('.mask'))
    }
  }
}

console.log('\n--- 6. 点击「历史」 ---')
const maskNow = container.querySelector('.mask')
if (maskNow) {
  const x = [...maskNow.querySelectorAll('button')].find((b) => (b.textContent || '').trim() === '✕')
  if (x) { click(x); await flush() }
}
click(findButton('历史'))
await flush()
check('历史弹窗出现', !!container.querySelector('.mask'))

console.log(`\n结果：${pass} 通过 / ${fail} 失败`)
dom.window.close()
process.exit(fail ? 1 : 0)
