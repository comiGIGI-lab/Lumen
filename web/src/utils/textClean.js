/**
 * cleanMarkdown —— 把大模型回复里夹带的轻量 markdown 转成可读纯文本 + 安全 HTML 结构。
 * 设计原则：
 * - 零外部依赖，体积极小，执行高效；
 * - 清理 **bold**、*italic*、***bold-italic***、### heading、- list 等星号和 markdown 标记；
 * - 保留可读文字，仅在必要处转为 <strong> 和 <code> 等语义化标签；
 * - 严格对 HTML 特殊字符进行实体转义，防止 XSS；
 * - 清理未闭合的残留星号，确保问答输出视觉整洁、无星号污染。
 */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function cleanMarkdown(text) {
  if (!text) return ''
  let s = escapeHtml(String(text))

  // 1. 行首水平分割线（---, ***, ___）移除
  s = s.replace(/^\s*[-*_]{3,}\s*$/gm, '')

  // 2. 行首标题（# / ## / ###）去掉井号和空格，仅保留标题文字
  s = s.replace(/^\s*#{1,6}\s+/gm, '')

  // 3. 行内代码块 `code` → <code>code</code>
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>')

  // 4. 粗斜体 ***text*** → <strong>text</strong>
  s = s.replace(/\*\*\*([^*\n]+)\*\*\*/g, '<strong>$1</strong>')

  // 5. 粗体 **text** 或 __text__ → <strong>text</strong>
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__([^_\n]+)__/g, '<strong>$1</strong>')

  // 6. 斜体 *text* 或 _text_ → <strong>text</strong>（在中文问答语境下转为重点强调）
  s = s.replace(/(^|[^*])\*([^*\s\n][^*\n]*?)\*([^*]|$)/g, '$1<strong>$2</strong>$3')

  // 7. 行首无序列表（- 或 * 加空格）→「· 」；保留缩进层级感
  s = s.replace(/^\s*[-*]\s+/gm, '· ')

  // 8. 清理任何孤立或未闭合的连续星号（如 "**加粗截断" 或 "***"）
  s = s.replace(/\*{2,}/g, '')

  return s
}
