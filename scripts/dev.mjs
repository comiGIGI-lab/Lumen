#!/usr/bin/env node
/**
 * scripts/dev.mjs —— 一键启动「Python API 后端 + Vite 前端」
 *
 * 设计约束：
 *   本项目刻意保持 **零额外依赖**（不用 concurrently / npm-run-all），
 *   只用 Node 内置 child_process 编排两个进程。
 *
 * 用法：
 *   npm run dev
 *   PYTHON=/path/to/python npm run dev     # 指定解释器
 *   API_PORT=8010 npm run dev              # 指定后端端口
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readdirSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPTS_DIR = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.dirname(SCRIPTS_DIR)
const WEB_DIR = path.join(ROOT, 'web')
const VITE_BIN = path.join(WEB_DIR, 'node_modules', 'vite', 'bin', 'vite.js')

const isWin = process.platform === 'win32'
const API_PORT = process.env.API_PORT || '8000'
const WEB_PORT = process.env.WEB_PORT || '5173'
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`

/** 探测某个端口是否已有服务在监听 */
function checkPort(port, host = '127.0.0.1', timeout = 500) {
  return new Promise((resolve) => {
    const sock = net.connect({ port, host })
    let settled = false
    const finish = (ok) => {
      if (settled) return
      settled = true
      sock.destroy()
      resolve(ok)
    }
    sock.setTimeout(timeout)
    sock.once('connect', () => finish(true))
    sock.once('timeout', () => finish(false))
    sock.once('error', () => finish(false))
  })
}

/** 轮询等待端口就绪（最多约 tries × 500ms） */
async function waitForPort(port, tries = 60) {
  for (let i = 0; i < tries; i++) {
    if (await checkPort(port)) return true
    await new Promise((r) => setTimeout(r, 500))
  }
  return false
}

/** 用系统默认浏览器打开 URL */
function openBrowser(url) {
  try {
    if (isWin) {
      spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref()
    } else if (process.platform === 'darwin') {
      spawn('open', [url], { detached: true, stdio: 'ignore' }).unref()
    } else {
      spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref()
    }
  } catch (_) {
    /* 打不开就算了，URL 已经打印在控制台 */
  }
}

/**
 * 找一个真正能跑的 Python 解释器。
 * 只依赖标准库，所以任何 3.9+ 解释器都可以。
 *
 * 探测顺序：
 *   1. PYTHON 环境变量
 *   2. PATH 上的 python / python3 / py
 *   3. Windows 常见安装目录（%LOCALAPPDATA%\Programs\Python\Python3*、C:\Python3*）
 *      —— 因为「python 没加进 PATH」是最常见的踩坑
 */
function probe(cmd, args = ['-c', 'import sys; print(sys.version_info[0])']) {
  try {
    // 注意：这里**不能**用 shell —— 否则 `-c "import sys; print(...)"` 里的空格
    // 会被 cmd.exe 拆成多个参数，导致永远探测失败（曾经的踩坑点）。
    const r = spawnSync(cmd, args, { encoding: 'utf-8' })
    if (r.error) return null
    return r.status === 0 && String(r.stdout).trim() === '3' ? cmd : null
  } catch (_) {
    return null
  }
}

function winPythonCandidates() {
  if (!isWin) return []
  const roots = [
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python'),
    'C:\\',
    path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Python'),
  ]
  const out = []
  for (const root of roots) {
    if (!root || !existsSync(root)) continue
    try {
      for (const dir of readdirSync(root)) {
        if (/^Python3\d+$/i.test(dir) || /^Python3\d+-32$/i.test(dir)) {
          out.push(path.join(root, dir, 'python.exe'))
        }
      }
    } catch (_) {
      /* 目录不可读则跳过 */
    }
  }
  return out
}

function resolvePython() {
  if (process.env.PYTHON) return process.env.PYTHON

  // py -3 是官方的启动器，优先于裸 python
  if (isWin && probe('py', ['-3', '-c', 'import sys; print(sys.version_info[0])'])) {
    return 'py'
  }

  const names = isWin ? ['python', 'python3'] : ['python3', 'python']
  for (const name of names) {
    if (probe(name)) return name
  }

  for (const abs of winPythonCandidates()) {
    if (probe(abs)) return abs
  }
  return null
}

const PYTHON = resolvePython()

const children = []
let shuttingDown = false

function track(name, child) {
  children.push({ name, child })
  child.on('exit', (code, signal) => {
    if (!shuttingDown && code !== 0 && code !== null && signal !== 'SIGTERM') {
      console.error(`\n[dev] ✗ ${name} 异常退出（code=${code}），正在停止另一个进程…`)
      shutdown(1)
    }
  })
}

function shutdown(exitCode = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const { child } of children) {
    if (child && !child.killed) {
      try {
        child.kill()
      } catch (_) {
        /* 忽略 */
      }
    }
  }
  setTimeout(() => process.exit(exitCode), 150)
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

console.log('══════════════════════════════════════════════')
console.log('  study-liu Web · 开发环境')
console.log('══════════════════════════════════════════════')
console.log(`  项目根目录 : ${ROOT}`)
console.log(`  Python     : ${PYTHON || '(未找到)'}`)
console.log(`  后端端口   : ${API_PORT}`)
console.log(`  前端地址   : ${WEB_URL}`)
console.log('══════════════════════════════════════════════\n')

// 已经跑着一份了 → 直接开浏览器，不重复占用端口（想强制重启用 FORCE=1）
if (process.env.FORCE !== '1' && (await checkPort(Number(WEB_PORT)))) {
  console.log(`[dev] 检测到 ${WEB_PORT} 端口已有服务在运行，直接打开浏览器。`)
  console.log(`[dev] 如需强制重启，请设置环境变量 FORCE=1 后重新运行。\n`)
  if (process.env.OPEN !== '0') openBrowser(WEB_URL)
  process.exit(0)
}

if (!PYTHON) {
  console.error('[dev] ✗ 找不到可用的 Python 3，请安装后重试，或设置 PYTHON 环境变量。')
  process.exit(1)
}

// 前端依赖没装 → 先装依赖（装完提示用户重新运行，避免并发装包导致 vite 起不来）
if (!existsSync(VITE_BIN)) {
  console.log('[dev] 未检测到 web/node_modules，正在执行 npm install …\n')
  const installer = spawn(
    isWin ? 'npm.cmd' : 'npm',
    ['install', '--no-audit', '--no-fund'],
    { cwd: WEB_DIR, stdio: 'inherit', shell: isWin },
  )
  installer.on('exit', (code) => {
    if (code === 0) {
      console.log('\n[dev] ✓ 依赖安装完成，请重新执行 npm run dev 启动前后端。')
    } else {
      console.error(`\n[dev] ✗ npm install 失败（code=${code}）`)
    }
  })
} else {
  // ① Python API 后端（自动定位 study-liu 源码）
  const serverScript = path.join(ROOT, 'server', 'api_server.py')
  const pyArgs = [
    // `py` 是 Windows 启动器，需要显式指定版本
    ...(PYTHON === 'py' ? ['-3'] : []),
    serverScript,
    '--host',
    '127.0.0.1',
    '--port',
    API_PORT,
  ]
  const api = spawn(PYTHON, pyArgs, { cwd: ROOT, stdio: 'inherit' })
  track('api_server', api)

  // ② Vite 前端（直接跑 vite.js，绕开 npm 一层壳）
  //    --strictPort：端口被占就直接报错，避免 vite 悄悄换端口导致自动打开的地址失效
  const web = spawn(
    process.execPath,
    [VITE_BIN, '--host', '127.0.0.1', '--port', WEB_PORT, '--strictPort'],
    {
      cwd: WEB_DIR,
      stdio: 'inherit',
      env: { ...process.env, VITE_API_TARGET: `http://127.0.0.1:${API_PORT}` },
    },
  )
  track('vite', web)

  console.log(`\n[dev] 浏览器打开 → ${WEB_URL}`)
  console.log(`[dev] 接口地址   → http://127.0.0.1:${API_PORT}/api/health`)
  console.log('[dev] 按 Ctrl+C 停止\n')

  // ③ 前后端都就绪后再自动打开浏览器（OPEN=0 可关闭）
  if (process.env.OPEN !== '0') {
    waitForPort(Number(WEB_PORT)).then(async (webReady) => {
      if (shuttingDown || !webReady) return
      const apiReady = await checkPort(Number(API_PORT))
      console.log(
        `[dev] ✓ 服务就绪（前端 ${webReady ? 'OK' : '×'} / 后端 ${apiReady ? 'OK' : '×'}），正在打开浏览器 …`,
      )
      openBrowser(WEB_URL)
    })
  }
}
