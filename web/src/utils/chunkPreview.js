/**
 * 知识库分块预览。只负责显示，不改入库正文。
 *
 * 上传解析出来的换行在 HTML 里会被压成空格，所以这里按行还原。
 * 常见公式（$...$、$$...$$、\( \)、\[ \]）以及 a^{2}、H_2、x_1 这类简写
 * 转成带上下标的纯文本，不引入公式渲染库。
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch])
}

function stash(list, html) {
  return `\u0000${list.push(html) - 1}\u0000`
}

function unstashEscaped(escaped, list) {
  const parts = escaped.split(/\u0000(\d+)\u0000/)
  let html = ''
  for (let i = 0; i < parts.length; i += 1) {
    if (i % 2 === 0) html += escapeHtml(parts[i])
    else html += list[Number(parts[i])]
  }
  return html
}

function commandsToHtml(source) {
  return escapeHtml(source)
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '<span class="fx-frac"><span>$1</span><span>$2</span></span>')
    .replace(/\\sqrt\{([^{}]+)\}/g, '√<span class="fx-group">$1</span>')
    .replace(/_\{([^{}]+)\}/g, '<sub>$1</sub>')
    .replace(/\^\{([^{}]+)\}/g, '<sup>$1</sup>')
    .replace(/_([A-Za-z0-9])/g, '<sub>$1</sub>')
    .replace(/\^([A-Za-z0-9])/g, '<sup>$1</sup>')
    .replace(/\\([A-Za-z]+)/g, '$1')
}

function protectMath(text, box) {
  const patterns = [
    /\$\$[\s\S]+?\$\$/g,
    /\\\[[\s\S]+?\\\]/g,
    /\\\([\s\S]+?\\\)/g,
    /\$(?:\\\$|[^$\n])+\$/g,
  ]
  let out = text
  for (const re of patterns) {
    out = out.replace(re, (raw) => {
      const inner = raw
        .replace(/^\$\$|\$\$$/g, '')
        .replace(/^\\\[|\\\]$/g, '')
        .replace(/^\\\(|\\\)$/g, '')
        .replace(/^\$|\$$/g, '')
      return stash(box, `<span class="fx">${commandsToHtml(inner.trim())}</span>`)
    })
  }
  return out
}

function lightMarkup(escaped) {
  return escaped
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '<span class="fx-frac"><span>$1</span><span>$2</span></span>')
    .replace(/\\sqrt\{([^{}]+)\}/g, '√<span class="fx-group">$1</span>')
    .replace(/_\{([^{}]+)\}/g, '<sub>$1</sub>')
    .replace(/\^\{([^{}]+)\}/g, '<sup>$1</sup>')
    .replace(/_(\d)/g, '<sub>$1</sub>')
    .replace(/\^(\d)/g, '<sup>$1</sup>')
}

/**
 * 把一块原文转成预览 HTML。已经转义，调用方可以用 v-html。
 */
export function renderChunkPreview(text) {
  const source = String(text ?? '').replace(/\r\n?/g, '\n').trim()
  if (!source) return ''
  const box = []
  const protectedText = protectMath(source, box)
  const blocks = protectedText.split(/\n{2,}/)
  return blocks.map((block) => {
    const lines = block.split('\n').map((line) => lightMarkup(unstashEscaped(line, box)))
    return `<p>${lines.join('<br>')}</p>`
  }).join('')
}
