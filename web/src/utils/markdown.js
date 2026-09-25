/**
 * markdown.js —— 轻量 Markdown → HTML 渲染器（零依赖）
 *
 * 为什么不用 marked / markdown-it：
 *   1. 生产服务器只有 1.6G 内存，多一个依赖就要在服务器上多跑一次 npm install，
 *      多一个「构建失败 → dist 被清空 → 白屏」的失败点；
 *   2. 大模型返回的文本属于不可信输入，自己实现可以保证「先整体转义、再渲染」，
 *      全程不解析任何原始 HTML 标签，天然没有 XSS 面。
 *
 * 支持：标题(1~6)、无序/有序列表（含嵌套）、围栏代码块、行内代码、
 *      粗体/斜体/删除线、链接、裸链接、引用块、分割线、表格、段落内换行。
 * 刻意不支持：原始 HTML、图片（降级成链接）、脚注、setext 标题。
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

/** HTML 转义：所有文本进入渲染流程前必须先过这一关 */
export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch])
}

/** 只允许这几种协议/相对路径，挡掉 javascript: / data: / vbscript: */
const SAFE_URL = /^(?:https?:\/\/|mailto:|tel:|\/|\.{1,2}\/|#)/i

function safeUrl(raw) {
  const url = String(raw || '').trim()
  return SAFE_URL.test(url) ? url : '#'
}

const MARK = '\u0000'

function stash(list, html) {
  return `${MARK}${list.push(html) - 1}${MARK}`
}

function unstash(text, list) {
  return text.replace(/\u0000(\d+)\u0000/g, (_, n) => list[Number(n)])
}

const LINK_ATTRS = 'target="_blank" rel="noopener noreferrer"'

/* ---------------- 块操作栏（表格 / 代码块右上角的复制、下载） ---------------- */
const SVG_HEAD =
  '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'

const ICON_COPY =
  `${SVG_HEAD}<rect x="9.2" y="9.2" width="11" height="11" rx="2.2"/>` +
  '<path d="M5.6 15.4V5.7A2.1 2.1 0 0 1 7.7 3.6h9.7"/></svg>'

const ICON_DOWNLOAD =
  `${SVG_HEAD}<path d="M12 3.5v11"/><path d="m7.6 10.4 4.4 4.4 4.4-4.4"/>` +
  '<path d="M5 19.5h14"/></svg>'

const ICON_CHECK =
  `${SVG_HEAD}<path d="m4.5 12.5 5 5 10-11"/></svg>`

function blockButton(act, title, icon) {
  return (
    `<button type="button" class="md-act" data-md-act="${act}" ` +
    `title="${title}" aria-label="${title}">${icon}</button>`
  )
}

function blockBar(name, buttons) {
  return (
    `<div class="md-block-bar"><span class="md-block-name">${name}</span>` +
    `<span class="md-block-acts">${buttons}</span></div>`
  )
}

/* ---------------- 行内 ----------------
 * 入参 escaped：已经过 escapeHtml 的文本。返回 HTML。
 * 行内代码 / 链接先抽成占位符，避免后面的强调规则把它们内部的 * _ 当作语法。
 */
function renderInline(escaped) {
  const box = []
  let out = escaped

  // 行内代码
  out = out.replace(/`([^`\n]+)`/g, (_, code) =>
    stash(box, `<code class="md-code">${code.trim()}</code>`),
  )

  // 图片 → 降级成文字链接（不加载外链图片，避免离线裂图与追踪像素）
  out = out.replace(/!\[([^\]]*)\]\(\s*([^)\s]*)[^)]*\)/g, (_, alt, url) =>
    stash(box, `<a href="${safeUrl(url)}" ${LINK_ATTRS}>${alt || url}</a>`),
  )

  // 链接 [文案](地址)
  out = out.replace(
    /\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\s*\)/g,
    (_, label, url) => stash(box, `<a href="${safeUrl(url)}" ${LINK_ATTRS}>${label || url}</a>`),
  )

  // 裸链接
  out = out.replace(
    /(^|[\s(（])(https?:\/\/[^\s<>）)]+)/g,
    (_, pre, url) => `${pre}${stash(box, `<a href="${safeUrl(url)}" ${LINK_ATTRS}>${url}</a>`)}`,
  )

  // 强调：粗斜 → 粗 → 斜 → 删除线
  out = out.replace(/\*\*\*([^\n]+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  out = out.replace(/\*\*([^\n]+?)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/__([^\n_]+?)__/g, '<strong>$1</strong>')
  out = out.replace(/~~([^\n]+?)~~/g, '<del>$1</del>')
  out = out.replace(/(^|[^*\w])\*([^*\n]+?)\*(?=[^*\w]|$)/g, '$1<em>$2</em>')
  out = out.replace(/(^|[^_\w])_([^_\n]+?)_(?=[^_\w]|$)/g, '$1<em>$2</em>')

  return unstash(out, box)
}

/* ---------------- 块级识别 ---------------- */
const RE_HEADING = /^(#{1,6})\s+(.*)$/
const RE_FENCE = /^\s{0,3}(`{3,}|~{3,})\s*([\w+#-]*)\s*$/
const RE_HR = /^\s{0,3}(?:([-*_])\s*){3,}$/
const RE_UL = /^(\s*)([-*+])\s+(.*)$/
const RE_OL = /^(\s*)(\d{1,3})[.)]\s+(.*)$/
const RE_QUOTE = /^\s{0,3}>\s?(.*)$/
const RE_TABLE_SEP = /^\s{0,3}\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/

function isFenceClose(line, marker) {
  const t = line.trim()
  return marker === '`' ? /^`{3,}$/.test(t) : /^~{3,}$/.test(t)
}

function isBlockStart(line) {
  return (
    line.trim() === '' ||
    RE_HEADING.test(line) ||
    RE_FENCE.test(line) ||
    RE_QUOTE.test(line) ||
    RE_HR.test(line) ||
    RE_UL.test(line) ||
    RE_OL.test(line)
  )
}

function splitRow(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split('|').map((c) => c.trim())
}

function alignOf(cell) {
  const left = cell.startsWith(':')
  const right = cell.endsWith(':')
  if (left && right) return 'center'
  if (right) return 'right'
  if (left) return 'left'
  return ''
}

const styleOf = (a) => (a ? ` style="text-align:${a}"` : '')

/* ---------------- 入口 ---------------- */
export function renderMarkdown(source) {
  const text = String(source ?? '').replace(/\r\n?/g, '\n')
  if (!text.trim()) return ''

  const lines = text.split('\n')
  const out = []
  let i = 0
  const stack = [] // 列表栈：{ tag, indent }
  let liOpen = false

  const closeLi = () => {
    if (liOpen) {
      out.push('</li>')
      liOpen = false
    }
  }
  const closeLists = () => {
    while (stack.length) {
      closeLi()
      out.push(`</${stack.pop().tag}>`)
    }
  }

  while (i < lines.length) {
    const line = lines[i]

    // 空行：列表内部视为「松散列表」，不打断
    if (!line.trim()) {
      i += 1
      continue
    }

    // 围栏代码块
    const fence = line.match(RE_FENCE)
    if (fence) {
      closeLists()
      const marker = fence[1][0]
      const lang = fence[2] || ''
      const buf = []
      i += 1
      while (i < lines.length && !isFenceClose(lines[i], marker)) {
        buf.push(lines[i])
        i += 1
      }
      if (i < lines.length) i += 1
      const cls = lang ? ` class="md-code lang-${lang}"` : ' class="md-code"'
      const label = lang ? escapeHtml(lang) : '代码'
      out.push(
        `<div class="md-block md-block-code">` +
          blockBar(label, blockButton('copy', '复制代码', ICON_COPY)) +
          `<pre class="md-pre"><code${cls}>${escapeHtml(buf.join('\n'))}</code></pre>` +
          `</div>`,
      )
      continue
    }

    // 标题
    const h = line.match(RE_HEADING)
    if (h) {
      closeLists()
      const lv = h[1].length
      out.push(`<h${lv} class="md-h md-h${lv}">${renderInline(escapeHtml(h[2].trim()))}</h${lv}>`)
      i += 1
      continue
    }

    // 分割线
    if (RE_HR.test(line)) {
      closeLists()
      out.push('<hr class="md-hr" />')
      i += 1
      continue
    }

    // 表格（当前行是表头，且下一行是分隔行）
    if (
      line.includes('|') &&
      i + 1 < lines.length &&
      lines[i + 1].includes('-') &&
      RE_TABLE_SEP.test(lines[i + 1])
    ) {
      closeLists()
      const head = splitRow(line)
      const aligns = splitRow(lines[i + 1]).map(alignOf)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        rows.push(splitRow(lines[i]))
        i += 1
      }
      const th = head
        .map((c, k) => `<th${styleOf(aligns[k])}>${renderInline(escapeHtml(c))}</th>`)
        .join('')
      const tbody = rows
        .map(
          (r) =>
            `<tr>${r
              .map((c, k) => `<td${styleOf(aligns[k])}>${renderInline(escapeHtml(c))}</td>`)
              .join('')}</tr>`,
        )
        .join('')
      out.push(
        `<div class="md-block md-block-table">` +
          blockBar(
            '表格',
            blockButton('copy', '复制表格', ICON_COPY) +
              blockButton('download', '下载 CSV', ICON_DOWNLOAD),
          ) +
          `<div class="md-table-wrap"><table class="md-table"><thead><tr>${th}</tr></thead>` +
          `<tbody>${tbody}</tbody></table></div>` +
          `</div>`,
      )
      continue
    }

    // 引用块
    if (RE_QUOTE.test(line)) {
      closeLists()
      const buf = []
      while (i < lines.length) {
        const m = lines[i].match(RE_QUOTE)
        if (m) {
          buf.push(m[1])
          i += 1
          continue
        }
        if (!lines[i].trim() && i + 1 < lines.length && RE_QUOTE.test(lines[i + 1])) {
          buf.push('')
          i += 1
          continue
        }
        break
      }
      out.push(`<blockquote class="md-quote">${renderMarkdown(buf.join('\n'))}</blockquote>`)
      continue
    }

    // 列表（缩进 2 空格视为一层嵌套）
    const ul = line.match(RE_UL)
    const ol = ul ? null : line.match(RE_OL)
    if (ul || ol) {
      const m = ul || ol
      const indent = m[1].replace(/\t/g, '    ').length
      const tag = ul ? 'ul' : 'ol'

      while (stack.length && indent < stack[stack.length - 1].indent) {
        closeLi()
        out.push(`</${stack.pop().tag}>`)
      }
      const top = stack[stack.length - 1]
      const openList = () => {
        const start = tag === 'ol' && Number(m[2]) !== 1 ? ` start="${Number(m[2])}"` : ''
        out.push(`<${tag}${start} class="md-list">`)
        stack.push({ tag, indent })
      }
      if (!top || indent > top.indent) {
        openList() // 嵌套：直接落在上一层未闭合的 <li> 里
      } else if (top.tag !== tag) {
        closeLi()
        out.push(`</${stack.pop().tag}>`)
        openList()
      } else {
        closeLi()
      }
      out.push(`<li class="md-li">${renderInline(escapeHtml(m[3]))}`)
      liOpen = true
      i += 1
      continue
    }

    // 段落：连续非块首行合并，单个换行保留成 <br>
    closeLists()
    const buf = []
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      buf.push(lines[i].trim())
      i += 1
    }
    if (!buf.length) {
      buf.push(lines[i].trim())
      i += 1
    }
    const html = renderInline(escapeHtml(buf.join('\n'))).replace(/\n/g, '<br />')
    out.push(`<p class="md-p">${html}</p>`)
  }

  closeLists()
  return out.join('\n')
}

/* ============================================================
 * 块操作：复制 / 下载
 * 线上站点是 http（非安全上下文），navigator.clipboard 根本不存在，
 * 所以复制一律走 textarea + execCommand 这条老路，并对 clipboard API 做优先尝试。
 * ============================================================ */

/** 把表格读成二维数组（含表头） */
function readTable(table) {
  return Array.from(table.querySelectorAll('tr')).map((tr) =>
    Array.from(tr.querySelectorAll('th,td')).map((td) =>
      (td.textContent || '').replace(/\s+/g, ' ').trim(),
    ),
  )
}

/** 复制到 Excel / 飞书表格 / Word：用制表符分隔最通用 */
export function tableToTsv(table) {
  return readTable(table)
    .map((row) => row.map((c) => c.replace(/[\t\r\n]/g, ' ')).join('\t'))
    .join('\n')
}

/** 下载成 CSV：加了 UTF-8 BOM，Excel 双击打开中文不乱码 */
export function tableToCsv(table) {
  return readTable(table)
    .map((row) =>
      row
        .map((c) => (/[",\r\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c))
        .join(','),
    )
    .join('\r\n')
}

/** 写剪贴板。返回是否成功（调用方据此决定要不要提示失败） */
export function copyText(text) {
  const s = String(text ?? '')
  if (!s) return false

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(s).catch(() => {})
      return true
    }
  } catch (_) {
    /* 落到下面的兜底 */
  }

  try {
    const ta = document.createElement('textarea')
    ta.value = s
    ta.setAttribute('readonly', '')
    ta.style.cssText = 'position:fixed;top:-1000px;left:-1000px;opacity:0'
    document.body.appendChild(ta)
    ta.select()
    ta.setSelectionRange(0, s.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch (_) {
    return false
  }
}

/** 触发浏览器下载（Blob 方式，不需要后端参与） */
export function downloadText(filename, text, mime = 'text/csv;charset=utf-8') {
  try {
    const blob = new Blob(['\ufeff' + String(text ?? '')], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 2000)
    return true
  } catch (_) {
    return false
  }
}

/** 按钮点完闪一下对勾，1.2 秒后复原 */
function flashDone(btn) {
  if (!btn || btn.dataset.state === 'ok') return
  const original = btn.innerHTML
  btn.dataset.state = 'ok'
  btn.innerHTML = ICON_CHECK
  setTimeout(() => {
    if (!btn.isConnected) return
    btn.dataset.state = ''
    btn.innerHTML = original
  }, 1200)
}

/**
 * 挂在 .md-body 的父容器上做事件代理：
 *   <div class="md-body" v-html="renderMarkdown(t)" @click="handleMdAction" />
 * 返回 true 表示这次点击被处理掉了。
 */
export function handleMdAction(event) {
  const target = event && event.target
  if (!target || typeof target.closest !== 'function') return false

  const btn = target.closest('[data-md-act]')
  if (!btn) return false

  const block = btn.closest('.md-block')
  if (!block) return false

  const act = btn.getAttribute('data-md-act')
  const table = block.querySelector('table')
  const code = block.querySelector('pre code')

  if (act === 'copy') {
    const text = table ? tableToTsv(table) : code ? code.textContent : ''
    if (copyText(text)) flashDone(btn)
    return true
  }

  if (act === 'download' && table) {
    if (downloadText('表格.csv', tableToCsv(table))) flashDone(btn)
    return true
  }

  return true
}

export default renderMarkdown
