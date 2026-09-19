/**
 * ssr-check.mjs —— 不依赖浏览器，用 SSR 把组件真正渲染一遍。
 *
 * 为什么需要它：
 *   `vite build` 只能证明「能编译」，证明不了「运行时不会炸」。
 *   本机无法跑无头浏览器截图，SSR 是唯一能真正执行 setup + 模板的手段。
 *
 * 用法（在 web 目录下）：
 *   node <这个脚本的路径>
 */
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'

const server = await createServer({
  root: process.cwd(),
  appType: 'custom',
  logLevel: 'error',
  server: { middlewareMode: true },
})

const results = []
const warnings = []

async function check(name, modulePath, props) {
  try {
    const mod = await server.ssrLoadModule(modulePath)
    const app = createSSRApp(mod.default, props)
    // 把 Vue 的警告收集起来 —— 「Failed to resolve component」之类的
    // 问题不会抛异常，只会静默渲染成空，必须靠警告才能发现
    app.config.warnHandler = (msg, _inst, trace) => {
      warnings.push(`[${name}] ${msg}${trace ? ' @ ' + String(trace).split('\n')[1]?.trim() : ''}`)
    }
    const html = await renderToString(app)
    results.push({ name, ok: true, html })
  } catch (e) {
    results.push({ name, ok: false, err: `${e.message}\n${String(e.stack).split('\n').slice(0, 4).join('\n')}` })
  }
}

// 1) 整个 App
await check('App.vue', '/src/App.vue')

// 2) 设置弹窗（open=true，真正把内容渲染出来）
await check('SettingsDialog.vue', '/src/components/SettingsDialog.vue', {
  open: true,
  mode: {
    mode: 'llm',
    label: 'LLM 模式 · deepseek-chat',
    has_key: false,
    api_key_masked: '',
    base_url: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    reason: '已配置 LLM 模式，但缺少 API Key',
  },
})

// 3) 设置弹窗（Mock 态）
await check('SettingsDialog.vue#mock', '/src/components/SettingsDialog.vue', {
  open: true,
  mode: { mode: 'mock', label: 'Mock 模式', has_key: false, base_url: '', model: '' },
})

let failed = 0
for (const r of results) {
  if (!r.ok) {
    failed++
    console.log(`✗ ${r.name}\n   ${r.err}\n`)
    continue
  }
  console.log(`✓ ${r.name}  ->  渲染出 ${r.html.length} 字符`)
}

const dialog = results.find((r) => r.name === 'SettingsDialog.vue')
if (dialog?.ok) {
  const probes = [
    ['离线 Mock 模式', '两段切换：Mock'],
    ['在线 LLM 模式', '两段切换：LLM'],
    ['测试连接', '测试连接按钮'],
    ['通义千问', '平台下拉里的选项'],
    ['必填', '红色必填提示'],
    ['API Base URL', 'Base URL 字段'],
  ]
  console.log('\n--- 弹窗内容抽查 ---')
  for (const [needle, desc] of probes) {
    console.log(`${dialog.html.includes(needle) ? '✓' : '✗'} ${desc}（"${needle}"）`)
  }
  const segCount = (dialog.html.match(/seg-btn/g) || []).length
  console.log(`\n两段按钮数量 = ${segCount}（期望 2）`)
  const selCount = (dialog.html.match(/<select/g) || []).length
  console.log(`平台下拉数量 = ${selCount}（期望 1）`)
}

console.log(failed ? `\n结果：${failed} 个组件渲染失败` : '\n结果：全部通过')

console.log('\n--- Vue 警告 ---')
if (warnings.length) {
  for (const w of [...new Set(warnings)]) console.log(`  ⚠ ${w}`)
} else {
  console.log('  无')
}

// 顶栏四个按钮是否真的渲染出来了
const appHtml = results.find((r) => r.name === 'App.vue')?.html || ''
console.log('\n--- 顶栏按钮 ---')
for (const [needle, desc] of [
  ['⚙ 设置', '设置'],
  ['🕘 历史', '历史'],
  ['📜 日志', '日志'],
  ['📥 导出方案', '导出'],
]) {
  console.log(`${appHtml.includes(needle) ? '✓' : '✗'} ${desc} 按钮`)
}

await server.close()
process.exit(failed ? 1 : 0)
