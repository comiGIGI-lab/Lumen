<script setup>
/**
 * ExportPreview —— 学习方案讲义预览
 * 封面 + 大纲 / 资源 / 计划，固定顺序。Markdown 与 Word 都走 /api/export
 * （用 format 区分，Word 回的是 .docx 二进制流）；PDF 用浏览器打印。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  result: { type: Object, default: null },
  profile: { type: Object, default: () => ({}) },
  generatedAt: { type: String, default: '' },
})

const emit = defineEmits(['close'])

const mdBusy = ref(false)
const mdHint = ref('')
const wordBusy = ref(false)

function pad(n) {
  return String(n).padStart(2, '0')
}

function todayLabel() {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const courseName = computed(() => (props.result?.course || '未命名课程').trim())

const coverDate = computed(() => {
  const raw = (props.generatedAt || '').trim()
  if (!raw) return todayLabel()
  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10)
  return raw
})

const coverProfile = computed(() => {
  const p = props.result?.profile || props.profile || {}
  return {
    level: p.level || '—',
    daily: p.daily_hours || '—',
    goal: p.goal || '—',
  }
})

const chapters = computed(() => {
  const list = props.result?.outline || []
  return list.map((ch, i) => {
    if (ch && typeof ch === 'object' && !Array.isArray(ch)) {
      const title = String(ch.title || ch.name || `第 ${i + 1} 章`).trim()
      const points = (ch.points || ch.items || []).map((p) => String(p).trim()).filter(Boolean)
      const note = String(ch.summary || ch.desc || ch.description || '').trim()
      return { no: i + 1, title, points, note }
    }
    return { no: i + 1, title: String(ch || '').trim() || `第 ${i + 1} 章`, points: [], note: '' }
  })
})

const resources = computed(() => {
  return (props.result?.resources || []).map((r, i) => {
    if (r && typeof r === 'object') {
      return {
        i,
        type: r.type || '资源',
        title: r.title || '未命名资源',
        url: r.url || '',
      }
    }
    return { i, type: '资源', title: String(r), url: '' }
  })
})

function stripDayPrefix(text, day) {
  let t = String(text || '').trim()
  t = t.replace(/^\s*第\s*\d+\s*天\s*[：:.\-]?\s*/, '')
  t = t.replace(/^\s*Day\s*\d+\s*[：:.\-]?\s*/i, '')
  const n = String(day)
  if (!t || t === `Day ${n}` || t === `第 ${n} 天` || t === `第${n}天`) return ''
  return t
}

const days = computed(() => {
  const structured = props.result?.plan_items
  const list = Array.isArray(structured) && structured.length
    ? structured
    : (props.result?.plan || [])
  return list.map((item, i) => {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const n = item.day ?? i + 1
      const title = stripDayPrefix(item.title, n)
      const chapters = (item.chapters || []).map((c) => String(c).trim()).filter(Boolean)
      const tasks = (item.tasks || []).map((t) => String(t).trim()).filter(Boolean)
      const lines = tasks.length ? tasks : title ? [title] : []
      return { n, title: tasks.length ? title : '', chapters, tasks: lines }
    }
    const n = i + 1
    const text = stripDayPrefix(item, n)
    return { n, title: '', chapters: [], tasks: text ? [text] : [] }
  })
})

function download(filename, content, mime = 'text/markdown;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function onMarkdown() {
  if (!props.result?.course || mdBusy.value) return
  mdBusy.value = true
  mdHint.value = '正在导出 Markdown'
  try {
    const res = await api.exportMarkdown(props.result.course, props.result)
    download(res.filename || `${courseName.value}学习方案.md`, res.markdown)
    mdHint.value = `已下载 ${res.filename || '学习方案.md'}`
  } catch (e) {
    mdHint.value = `导出失败：${e.message}`
  } finally {
    mdBusy.value = false
  }
}

async function onWord() {
  if (!props.result?.course || wordBusy.value) return
  wordBusy.value = true
  mdHint.value = '正在生成 Word 文档'
  try {
    const { blob, filename } = await api.exportDocx(props.result.course, props.result)
    download(
      filename,
      blob,
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    mdHint.value = `已下载 ${filename}`
  } catch (e) {
    mdHint.value = `导出失败：${e.message}`
  } finally {
    wordBusy.value = false
  }
}

function onPdf() {
  window.print()
}

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  (v) => {
    document.documentElement.classList.toggle('export-preview-open', v)
    document.body.style.overflow = v ? 'hidden' : ''
    if (v) {
      window.addEventListener('keydown', onKey)
      mdHint.value = ''
    } else {
      window.removeEventListener('keydown', onKey)
    }
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  document.documentElement.classList.remove('export-preview-open')
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="export-preview" role="dialog" aria-label="学习方案预览">
      <div class="export-chrome no-print">
        <div class="chrome-left">
          <p class="chrome-kicker">LUMEN</p>
          <h2>方案预览</h2>
          <p class="chrome-hint">先看排版，再选择下载格式。打印时只输出这份讲义。</p>
        </div>
        <div class="chrome-actions">
          <button type="button" class="btn btn-primary" :disabled="mdBusy" @click="onMarkdown">
            {{ mdBusy ? '导出中' : '下载 Markdown' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="onPdf">打印为 PDF</button>
          <button type="button" class="btn btn-ghost" :disabled="wordBusy" @click="onWord">
            {{ wordBusy ? '生成中' : '下载 Word' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="emit('close')">关闭</button>
        </div>
        <p v-if="mdHint" class="chrome-status">{{ mdHint }}</p>
        <p class="chrome-pdf-note">打印为 PDF：在系统打印对话框里把目标选成「另存为 PDF」。</p>
      </div>

      <article class="export-paper">
        <div class="ep-print-head" aria-hidden="true">LUMEN · 智识有方</div>
        <div class="ep-print-foot" aria-hidden="true">LUMEN，拉丁语意为光。智识有方：光之所至，学有其方。</div>
        <header class="ep-banner">
          <span class="ep-mark">LUMEN</span>
          <span class="ep-brand">智识有方</span>
          <span class="ep-kind">学习方案</span>
        </header>

        <section class="ep-cover">
          <p class="ep-kicker">Course plan</p>
          <h1>{{ courseName }}</h1>
          <dl class="ep-meta">
            <div>
              <dt>生成日期</dt>
              <dd>{{ coverDate }}</dd>
            </div>
            <div>
              <dt>程度</dt>
              <dd>{{ coverProfile.level }}</dd>
            </div>
            <div>
              <dt>每日时长</dt>
              <dd>{{ coverProfile.daily }}</dd>
            </div>
            <div>
              <dt>目标</dt>
              <dd>{{ coverProfile.goal }}</dd>
            </div>
          </dl>
        </section>

        <section class="ep-block">
          <h2>课程大纲</h2>
          <ol v-if="chapters.length" class="ep-chapters">
            <li v-for="ch in chapters" :key="ch.no">
              <div class="ch-head">
                <span class="ch-no">{{ String(ch.no).padStart(2, '0') }}</span>
                <h3>{{ ch.title }}</h3>
              </div>
              <ul v-if="ch.points.length" class="ch-points">
                <li v-for="(p, pi) in ch.points" :key="pi">{{ p }}</li>
              </ul>
              <p v-else-if="ch.note" class="ch-note">{{ ch.note }}</p>
              <p v-else class="ep-pending">要点待补充</p>
            </li>
          </ol>
          <p v-else class="ep-empty">大纲待写入。生成方案后，章节会按顺序排在这里。</p>
        </section>

        <section class="ep-block">
          <h2>推荐资源</h2>
          <table v-if="resources.length" class="ep-table">
            <thead>
              <tr>
                <th>类型</th>
                <th>标题</th>
                <th>链接</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in resources" :key="r.i">
                <td class="td-type">{{ r.type }}</td>
                <td>{{ r.title }}</td>
                <td>
                  <a v-if="r.url" :href="r.url" target="_blank" rel="noopener noreferrer">{{ r.url }}</a>
                  <span v-else class="ep-dash">—</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="ep-empty">资源待写入。检索完成后，条目会以表的形式列在这里。</p>
        </section>

        <section class="ep-block">
          <h2>每日计划</h2>
          <ol v-if="days.length" class="ep-days">
            <li v-for="d in days" :key="d.n">
              <h3>
                <span class="day-no">第 {{ d.n }} 天</span>
                <span v-if="d.title" class="day-title">{{ d.title }}</span>
              </h3>
              <p v-if="d.chapters.length" class="day-ch">关联章节：{{ d.chapters.join(' / ') }}</p>
              <ul v-if="d.tasks.length" class="day-tasks">
                <li v-for="(t, ti) in d.tasks" :key="ti">{{ t }}</li>
              </ul>
              <p v-else class="ep-pending">当日任务待补充</p>
            </li>
          </ol>
          <p v-else class="ep-empty">计划待写入。编排完成后，每天的任务会按日列在这里。</p>
        </section>

        <footer class="ep-foot">
          <span>LUMEN，拉丁语意为光。智识有方：光之所至，学有其方。</span>
          <span class="ep-foot-en">LUMEN, Latin for light.</span>
        </footer>
      </article>
    </div>
  </Teleport>
</template>

<style scoped>
.export-preview {
  position: fixed;
  inset: 0;
  z-index: 220;
  overflow: auto;
  overflow-x: hidden;
  background: #fbf9f6;
}

.export-chrome {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 16px 22px 12px;
  background: rgba(251, 249, 246, 0.96);
  border-bottom: 1px solid #e4ded5;
}

.chrome-kicker {
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 11px;
  letter-spacing: 0.28em;
  color: #e51520;
}

.chrome-left h2 {
  margin-top: 2px;
  font-size: 20px;
  letter-spacing: 0.06em;
}

.chrome-hint,
.chrome-pdf-note,
.chrome-status,
.word-note {
  font-size: 12px;
  color: #808080;
}

.chrome-hint {
  margin-top: 4px;
}

.chrome-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
}

.word-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chrome-status {
  margin-top: 8px;
  color: #4a4540;
}

.chrome-pdf-note {
  margin-top: 6px;
}

.export-paper {
  width: min(210mm, calc(100% - 32px));
  margin: 22px auto 48px;
  background: #fff;
  color: #191919;
  border: 1px solid #e4ded5;
  padding: 28px 32px 24px;
}

.ep-banner {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 2px solid #e51520;
  flex-wrap: wrap;
}

.ep-mark {
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  letter-spacing: 0.28em;
  color: #e51520;
  font-size: 12px;
}

.ep-brand {
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 16px;
  letter-spacing: 0.1em;
}

.ep-kind {
  margin-left: auto;
  font-size: 12px;
  color: #808080;
  letter-spacing: 0.08em;
}

.ep-cover {
  padding: 28px 0 8px;
}

.ep-kicker {
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #808080;
}

.ep-cover h1 {
  margin-top: 8px;
  font-size: 32px;
  line-height: 1.25;
  letter-spacing: 0.04em;
  word-break: break-word;
}

.ep-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px 16px;
  margin-top: 22px;
  padding: 16px 0;
  border-top: 1px solid #e4ded5;
  border-bottom: 1px solid #e4ded5;
}

.ep-meta dt {
  font-size: 11px;
  color: #808080;
  letter-spacing: 0.08em;
}

.ep-meta dd {
  margin-top: 4px;
  font-size: 14px;
  color: #191919;
}

.ep-block {
  padding: 28px 0 8px;
}

.ep-block h2 {
  font-size: 18px;
  letter-spacing: 0.08em;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4ded5;
}

.ep-chapters,
.ep-days,
.ch-points,
.day-tasks {
  list-style: none;
  margin: 0;
  padding: 0;
}

.ep-chapters > li,
.ep-days > li {
  padding: 16px 0;
  border-bottom: 1px solid #f1ece4;
}

.ch-head {
  display: flex;
  gap: 12px;
  align-items: baseline;
}

.ch-no,
.day-no {
  flex: none;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 13px;
  color: #e51520;
  letter-spacing: 0.08em;
}

.ch-head h3,
.ep-days h3 {
  font-size: 16px;
  line-height: 1.45;
  word-break: break-word;
}

.day-title {
  margin-left: 10px;
  font-size: 15px;
  color: #4a4540;
}

.ch-points,
.day-tasks {
  margin-top: 8px;
  padding-left: 2px;
}

.ch-points li,
.day-tasks li {
  position: relative;
  padding: 3px 0 3px 16px;
  font-size: 13.5px;
  color: #4a4540;
  line-height: 1.65;
}

.ch-points li::before,
.day-tasks li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.75em;
  width: 6px;
  height: 1px;
  background: #e51520;
}

.ch-note,
.day-ch {
  margin-top: 8px;
  font-size: 13px;
  color: #4a4540;
}

.ep-pending,
.ep-empty,
.ep-dash {
  color: #a39b92;
}

.ep-pending {
  margin-top: 8px;
  font-size: 13px;
}

.ep-empty {
  margin-top: 16px;
  font-size: 13.5px;
  line-height: 1.7;
}

.ep-table {
  width: 100%;
  margin-top: 14px;
  border-collapse: collapse;
  font-size: 13px;
}

.ep-table th,
.ep-table td {
  text-align: left;
  vertical-align: top;
  padding: 8px 10px 8px 0;
  border-bottom: 1px solid #f1ece4;
  word-break: break-word;
}

.ep-table th {
  font-weight: 600;
  color: #808080;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.td-type {
  width: 72px;
  white-space: nowrap;
  color: #4a4540;
}

.ep-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 36px;
  padding-top: 12px;
  border-top: 1px solid #e4ded5;
  font-size: 11.5px;
  color: #808080;
}

.ep-foot-en {
  letter-spacing: 0.04em;
}

@media (max-width: 860px) {
  .export-paper {
    width: calc(100% - 24px);
    padding: 22px 18px 18px;
  }
  .ep-cover h1 {
    font-size: 26px;
  }
  .ep-meta {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 390px) {
  .export-chrome {
    padding: 12px;
  }
  .export-paper {
    width: calc(100% - 16px);
    margin: 12px auto 32px;
    padding: 18px 14px 16px;
  }
  .ep-cover h1 {
    font-size: 22px;
  }
  .ep-meta {
    grid-template-columns: 1fr;
  }
  .ep-kind {
    margin-left: 0;
  }
  .day-title {
    display: block;
    margin: 4px 0 0;
  }
}

.ep-print-head,
.ep-print-foot {
  display: none;
}

@media print {
  .export-preview {
    position: static;
    overflow: visible;
    background: #fff;
  }
  .export-paper {
    width: auto;
    margin: 0;
    border: none;
    padding: 22px 0 28px;
  }
  .ep-print-head,
  .ep-print-foot {
    display: flex;
    justify-content: space-between;
    position: fixed;
    left: 0;
    right: 0;
    font-family: Georgia, "Times New Roman", "Songti SC", serif;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: #808080;
  }
  .ep-print-head {
    top: 0;
    color: #e51520;
    border-bottom: 1px solid #e4ded5;
    padding-bottom: 6px;
  }
  .ep-print-foot {
    bottom: 0;
    border-top: 1px solid #e4ded5;
    padding-top: 6px;
  }
  .ep-banner,
  .ep-cover,
  .ep-chapters > li,
  .ep-days > li,
  .ep-table tr {
    break-inside: avoid;
  }
  .ep-foot {
    break-inside: avoid;
  }
}
</style>
