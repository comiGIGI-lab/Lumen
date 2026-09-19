/**
 * minimal-dom-test.mjs —— 对照实验
 *
 * 目的：判断「同步挂载时死循环」是 jsdom 环境/我的 harness 的问题，
 * 还是 study-liu 前端代码的问题。
 * 做法：在完全相同的 jsdom 环境里挂载一个最简单的 Vue 组件。
 */
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {
  url: 'http://127.0.0.1:5173/',
  pretendToBeVisual: true,
})
const { window } = dom

const define = (k, v) => Object.defineProperty(globalThis, k, { value: v, writable: true, configurable: true })
for (const k of ['window', 'document', 'navigator', 'location', 'history', 'HTMLElement', 'Element',
  'Node', 'EventTarget', 'Event', 'MouseEvent', 'CustomEvent', 'MutationObserver', 'SVGElement',
  'MathMLElement', 'getComputedStyle', 'requestAnimationFrame', 'cancelAnimationFrame', 'NodeFilter',
  'Document', 'DocumentFragment', 'Text', 'Comment', 'ShadowRoot', 'TextEncoder', 'TextDecoder', 'URL']) {
  try { if (window[k] !== undefined) define(k, k === 'getComputedStyle' ? window[k].bind(window) : window[k]) } catch (_) {}
}
define('fetch', async () => ({ ok: true, status: 200, async json() { return {} } }))

console.log('① 环境就绪，准备 import vue …')
const t0 = Date.now()
const { createApp, h, ref, computed, watch, onMounted, nextTick } = await import('vue')
console.log(`② vue 已加载（${Date.now() - t0}ms），版本相关导出正常`)

console.log('③ 挂载最简组件 …')
const Comp = {
  setup() {
    const n = ref(0)
    const twice = computed(() => n.value * 2)
    onMounted(() => { n.value = 1 })
    return () => h('div', { class: 'x' }, `hello ${n.value} / ${twice.value}`)
  },
}
const app = createApp(Comp)
app.mount('#app')
console.log('④ 挂载返回，innerHTML =', window.document.getElementById('app').innerHTML)

await nextTick()
console.log('⑤ nextTick 完成，innerHTML =', window.document.getElementById('app').innerHTML)
console.log('\n结论：jsdom + Vue 基本挂载链路正常 —— 说明死循环出在应用代码里')
dom.window.close()
process.exit(0)
