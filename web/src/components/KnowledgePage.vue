<script setup>
/**
 * KnowledgePage —— 主应用内正式知识库页（已接真实后端）
 *
 * 数据来自 /api/knowledge；笔记/文档/分块的层级由 useKnowledge 从后端的扁平条目映射出来。
 * 搜索框走**后端的打分检索**（分词 + 字段加权 + 覆盖率），所以「换个说法问」也能命中，
 * 这正是把「整句子串匹配」换掉的意义所在。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { useAuth } from '@/composables/useAuth'
import SnakeBar from './SnakeBar.vue'
import { api } from '@/api/client'
import { TAG_LABEL, useKnowledge } from '@/composables/useKnowledge'

const emit = defineEmits(['back', 'open-import', 'go-course'])
const { t } = useI18n()
// 删除是管理员专属；服务端还会再校验一次角色
const { isAdmin } = useAuth()

const TAGS = [
  { id: 'all', label: '全部' },
  { id: 'high-math', label: '高数' },
  { id: 'english', label: '英语' },
  { id: 'mistakes', label: '错题' },
  { id: 'others', label: '其他' },
]

const TYPE_LABEL = { pdf: 'PDF', image: '图片', md: 'Markdown', txt: '文本', note: '笔记' }
const STATUS_LABEL = { ready: '已入库', parsing: '解析中', queue: '排队中', failed: '失败' }

const ACCEPT = '.pdf,.md,.markdown,.txt,.text,.png,.jpg,.jpeg,.webp,.bmp,.gif'
const MAX_FILES = 10
const MAX_BYTES = 16 * 1024 * 1024

const {
  notes,
  currentId,
  current,
  currentDocs,
  currentChunks,
  loading,
  error,
  lastQuery,
  refresh,
  ensureLoaded,
  pickNote,
  createNote,
  removeDoc,
  retryDoc,
  setRemark,
} = useKnowledge()

ensureLoaded()

const filter = ref('all')
const keyword = ref('')
const showImport = ref(false)
const savedHint = ref(false)
const picked = ref([])
const dragOn = ref(false)
const running = ref(false)
const importNote = ref('')
const fileInput = ref(null)
const caps = ref(null)
let seq = 0
let searchTimer = 0
let hintTimer = 0

api.knowledgeCapabilities().then((c) => { caps.value = c }).catch(() => {})

/** 搜索防抖 300ms 后打后端；清空则回到全量列表 */
watch(keyword, (q) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => refresh(String(q || '').trim()), 300)
})

const empty = computed(() => !loading.value && notes.value.length === 0)

const filtered = computed(() => {
  if (filter.value === 'all') return notes.value
  return notes.value.filter((n) => n.tag === filter.value)
})

function reload() {
  refresh(lastQuery.value || '')
}

function newNote() {
  const title = window.prompt('新笔记标题', '未命名笔记')
  if (title === null) return
  createNote(title.trim() || '未命名笔记')
}

function saveRemark() {
  if (!current.value) return
  setRemark(current.value.id, current.value.remark || '')
  savedHint.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => {
    savedHint.value = false
  }, 1400)
}

async function deleteDoc(doc) {
  if (!current.value || !doc) return
  if (!window.confirm(`删除「${doc.name}」及其全部 ${doc.chunks} 个分块？`)) return
  await removeDoc(current.value.id, doc.id)
}

// ---------- 页内快速导入（与导入文档页共用后端的同一个接口）----------
function fmtSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB'
  return bytes + ' B'
}

function openImport() {
  showImport.value = true
  picked.value = []
  importNote.value = ''
  dragOn.value = false
}

function closeImport() {
  if (running.value) return
  showImport.value = false
  picked.value = []
}

function addFiles(fileList) {
  const room = MAX_FILES - picked.value.length
  const list = Array.from(fileList || []).slice(0, Math.max(0, room))
  list.forEach((file) => {
    if (file.size > MAX_BYTES) {
      importNote.value = `已跳过「${file.name}」：${fmtSize(file.size)} 超过 16 MB`
      return
    }
    picked.value.push({
      id: 'k' + ++seq,
      file,
      name: file.name,
      size: fmtSize(file.size),
      status: 'waiting',
      chunks: 0,
      error: '',
    })
  })
}

function onPickClick() {
  if (running.value) return
  fileInput.value?.click()
}

function onFileChange(e) {
  addFiles(e.target.files)
  e.target.value = ''
}

function onDrop(e) {
  e.preventDefault()
  dragOn.value = false
  if (!running.value) addFiles(e.dataTransfer?.files)
}

async function startUpload() {
  if (running.value || !picked.value.length) return
  running.value = true
  importNote.value = '正在上传解析…'
  let ok = 0
  for (const row of picked.value) {
    row.status = 'uploading'
    try {
      const res = await api.knowledgeImport([row.file], {
        title: current.value?.title || '', // 归到当前正在看的这条笔记下
      })
      const r = (res.results || [])[0] || {}
      if (r.ok) {
        row.status = 'ready'
        row.chunks = r.chunks || 0
        ok += 1
      } else {
        row.status = 'failed'
        row.error = r.error || '导入失败'
      }
    } catch (e) {
      row.status = 'failed'
      row.error = e.message || String(e)
    }
  }
  await refresh('')
  keyword.value = ''
  running.value = false
  importNote.value = ok
    ? `已入库 ${ok} 个文件${picked.value.length - ok ? `，${picked.value.length - ok} 个失败` : ''}。`
    : '全部失败，请看每行的原因。'
}

onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  clearTimeout(hintTimer)
})
</script>

<template>
  <div class="kb">
    <div class="kb-bar">
      <div>
        <p class="eyebrow">Knowledge</p>
        <h2>{{ t('knowledgePage.5') }}</h2>
        <p class="lead">{{ t('knowledgePage.6') }}</p>
      </div>
      <div class="kb-actions">
        <button type="button" class="ghost" @click="emit('back')">{{ t('knowledgePage.7') }}</button>
        <button type="button" class="ghost" @click="emit('open-import')">{{ t('knowledgePage.8') }}</button>
        <button type="button" class="ok" @click="openImport">{{ t('knowledgePage.9') }}</button>
      </div>
    </div>

    <div class="kb-search">
      <input v-model="keyword" type="search" :placeholder="t('knowledgePage.1')" />
      <span v-if="loading" class="kb-state">{{ t('knowledgePage.10') }}</span>
      <span v-else-if="error" class="kb-state err">{{ error }}</span>
      <span v-else-if="lastQuery" class="kb-state">正在显示「{{ lastQuery }}」的检索结果</span>
    </div>

    <div v-if="empty" class="empty">
      <h3>{{ t('knowledgePage.11') }}</h3>
      <p>{{ t('knowledgePage.12') }}</p>
      <ol>
        <li><b>{{ t('knowledgePage.13') }}</b><span>{{ t('knowledgePage.14') }}</span></li>
        <li><b>{{ t('knowledgePage.15') }}</b><span>{{ t('knowledgePage.16') }}</span></li>
        <li><b>{{ t('knowledgePage.17') }}</b><span>{{ t('knowledgePage.18') }}</span></li>
      </ol>
      <div class="empty-btns">
        <button type="button" class="ok" @click="openImport">{{ t('knowledgePage.19') }}</button>
        <button type="button" class="ghost" @click="emit('open-import')">{{ t('knowledgePage.20') }}</button>
        <button type="button" class="ghost" @click="emit('go-course')">{{ t('knowledgePage.21') }}</button>
      </div>
    </div>

    <div v-else class="shell">
      <aside>
        <div class="sb-head">
          <span>{{ t('knowledgePage.22') }}</span>
          <em>{{ t('stat.knowledge', { n: filtered.length }) }}</em>
          <button type="button" class="ghost small" @click="reload">{{ t('knowledgePage.23') }}</button>
        </div>
        <div class="note-list">
          <button
            v-for="n in filtered"
            :key="n.id"
            type="button"
            class="note"
            :class="{ on: n.id === currentId }"
            @click="pickNote(n.id)"
          >
            <span class="note-t">{{ n.title }}</span>
            <span class="chip">{{ TAG_LABEL[n.tag] }}</span>
            <span class="note-d">{{ n.updated }}</span>
          </button>
          <p v-if="!filtered.length" class="none">{{ t('knowledgePage.24') }}</p>
        </div>
        <button type="button" class="ghost new" @click="newNote">{{ t('knowledgePage.25') }}</button>
      </aside>

      <section v-if="current" class="detail">
        <div class="chips">
          <button
            v-for="t in TAGS"
            :key="t.id"
            type="button"
            class="chip"
            :class="{ on: filter === t.id }"
            @click="filter = t.id"
          >{{ t.label }}</button>
        </div>

        <label class="title-lab">
          <span>{{ t('knowledgePage.26') }}</span>
          <input v-model="current.title" readonly :title="t('knowledgePage.2')" />
        </label>

        <dl class="meta">
          <div><dt>{{ t('knowledgePage.27') }}</dt><dd>{{ current.created }}</dd></div>
          <div><dt>{{ t('knowledgePage.28') }}</dt><dd>{{ current.updated }}</dd></div>
          <div><dt>{{ t('knowledgePage.29') }}</dt><dd>{{ TAG_LABEL[current.tag] }}</dd></div>
          <div><dt>{{ t('knowledgePage.30') }}</dt><dd>{{ currentDocs.length }} 个</dd></div>
        </dl>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ t('knowledgePage.31') }}</th>
                <th>{{ t('knowledgePage.32') }}</th>
                <th>{{ t('knowledgePage.33') }}</th>
                <th>{{ t('knowledgePage.34') }}</th>
                <th>{{ t('knowledgePage.35') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!currentDocs.length">
                <td colspan="5" class="empty-cell">{{ t('knowledgePage.36') }}</td>
              </tr>
              <tr v-for="d in currentDocs" :key="d.id" :class="{ fail: d.status === 'failed' }">
                <td>{{ d.name }}</td>
                <td>{{ TYPE_LABEL[d.type] }}</td>
                <td>
                  <span class="st" :class="d.status">{{ STATUS_LABEL[d.status] }}</span>
                  <span v-if="d.status === 'parsing'" class="pct">{{ d.progress }}%</span>
                  <SnakeBar v-if="d.status === 'parsing'" :progress="d.progress" status="parsing" />
                </td>
                <td>{{ d.chunks || '—' }}</td>
                <td class="ops">
                  <button v-if="d.status === 'failed'" type="button" class="danger" @click="retryDoc(d)">{{ t('knowledgePage.37') }}</button>
                  <button v-if="isAdmin" type="button" class="ghost small" @click="deleteDoc(d)">{{ t('knowledgePage.38') }}</button>
                  <span v-else class="admin-only" :title="t('auth.adminOnlyTip')">{{ t('auth.adminOnly') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="chunks">
          <h3>{{ t('knowledgePage.39') }}</h3>
          <p v-if="!currentDocs.length" class="empty-chunk">{{ t('knowledgePage.40') }}<button type="button" class="ok" @click="openImport">{{ t('knowledgePage.41') }}</button>
          </p>
          <p v-else-if="!currentChunks.length" class="empty-chunk">{{ t('knowledgePage.42') }}<button type="button" class="ok" @click="openImport">{{ t('knowledgePage.43') }}</button>
          </p>
          <article v-for="c in currentChunks" :key="c.id">
            <header><span>{{ c.src }}</span></header>
            <p>{{ c.text }}</p>
          </article>
        </div>

        <div class="remark">
          <h3>{{ t('knowledgePage.44') }}</h3>
          <textarea v-model="current.remark" rows="4" :placeholder="t('knowledgePage.3')"></textarea>
          <div class="remark-row">
            <button type="button" class="ok" @click="saveRemark">{{ t('knowledgePage.45') }}</button>
            <em :class="{ show: savedHint }">{{ t('knowledgePage.46') }}</em>
            <span>{{ t('knowledgePage.47') }}</span>
          </div>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="showImport" class="mask" @click.self="closeImport">
        <div class="modal" role="dialog" :aria-label="t('knowledgePage.4')">
          <header>
            <h3>{{ t('knowledgePage.48') }}</h3>
            <button type="button" class="x" :disabled="running" @click="closeImport">×</button>
          </header>
          <div
            class="drop"
            :class="{ on: dragOn }"
            @click="onPickClick"
            @dragenter.prevent="dragOn = true"
            @dragover.prevent="dragOn = true"
            @dragleave.prevent="dragOn = false"
            @drop="onDrop"
          >
            <p>{{ t('knowledgePage.49') }}</p>
            <span>{{ t('knowledgePage.50') }}</span>
            <input
              ref="fileInput"
              type="file"
              multiple
              :accept="ACCEPT"
              class="hidden-input"
              @change="onFileChange"
            />
          </div>
          <p class="modal-hint">导入的材料会归入当前笔记「{{ current?.title || t('knowledgePageX.1') }}」。</p>
          <div v-if="picked.length" class="up">
            <div v-for="row in picked" :key="row.id" class="up-row">
              <div class="up-meta">
                <span>{{ row.name }}</span>
                <em v-if="row.status === 'ready'">已入库 {{ row.chunks }} 块</em>
                <em v-else-if="row.status === 'failed'" class="err">{{ row.error }}</em>
                <em v-else>{{ row.status === 'uploading' ? t('knowledgePageX.2') : t('knowledgePageX.3') }}</em>
              </div>
            </div>
          </div>
          <p v-if="importNote" class="demo-note">{{ importNote }}</p>
          <footer>
            <button type="button" class="ghost" :disabled="running" @click="closeImport">{{ t('knowledgePage.51') }}</button>
            <button type="button" class="ok" :disabled="running || !picked.length" @click="startUpload">
              {{ running ? t('knowledgePageX.4') : t('knowledgePageX.5') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.kb {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.kb-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.eyebrow {
  font-family: var(--font-serif);
  font-style: italic;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-size: 13px;
}
h2 {
  font-size: 28px;
  margin-top: 4px;
}
.lead {
  max-width: 40em;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.demo-note {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-muted);
}
.kb-actions,
.empty-btns,
.remark-row,
.sb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.kb-search input,
.title-lab input,
textarea {
  width: 100%;
  border: 1px solid var(--border);
  background: var(--bg-card);
  padding: 10px 12px;
  border-radius: 1000px;
}
textarea {
  border-radius: 12px;
  resize: vertical;
}
.shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}
aside {
  min-width: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 10px;
}
.sb-head {
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.note-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 420px;
  overflow: auto;
}
.note {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  padding: 8px;
}
.note.on {
  background: var(--bg-soft);
  box-shadow: inset 3px 0 0 var(--accent);
}
.note-t {
  grid-column: 1;
  font-size: 13px;
}
.note .chip {
  grid-column: 2;
}
.note-d {
  grid-column: 1 / -1;
  font-size: 11px;
  color: var(--text-muted);
}
.new {
  width: 100%;
  margin-top: 8px;
}
/* 「没有匹配的笔记」原来只共享了颜色规则，没有内边距 ——
   .note-list 是 flex 容器、自身无 padding，所以这行字会贴着侧栏左边缘，
   和上面 .note 按钮里的文字对不齐。这里补上与 .note 一致的内缩。 */
.none {
  padding: 6px 12px;
  line-height: 1.6;
}
.detail {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  border-radius: 1000px;
  padding: 4px 10px;
  font-size: 12px;
}
.chip.on {
  background: #191919;
  color: #fff;
  border-color: var(--text-primary);
}
.meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 12px;
}
dt {
  color: var(--text-muted);
  font-size: 12px;
}
.table-wrap {
  overflow-x: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 560px;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.empty-cell {
  color: var(--text-muted);
  font-size: 12px;
}
.fail {
  background: var(--primary-soft);
}
.st.ready { color: #2e7d32; }
.st.parsing, .st.queue { color: var(--accent); }
.st.failed { color: var(--error); }
.pct { font-size: 11px; color: var(--text-muted); margin-left: 6px; }
.chunks article,
.remark,
.title-lab,
.empty {
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 14px;
}
.chunks header {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
}
.ok, .ghost, .danger {
  border-radius: 1000px;
  padding: 7px 14px;
  font-size: 13px;
}
.ok {
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
}
.ghost {
  border: 1px solid var(--border);
  background: var(--bg-card);
}
.danger {
  border: 1px solid var(--error);
  color: var(--error);
  background: var(--bg-card);
}
.remark-row em {
  opacity: 0;
  font-style: normal;
  color: #2e7d32;
  font-size: 12px;
}
.remark-row em.show { opacity: 1; }
.remark-row span, .none, .tm, .empty-chunk { color: var(--text-muted); font-size: 12px; }
.empty-chunk {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 0;
  line-height: 1.7;
}
.ops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.small {
  padding: 4px 10px;
  font-size: 12px;
}
.empty ol {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 0;
  list-style: none;
}
.empty li {
  border: 1px solid var(--border);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.empty b { font-weight: 400; font-family: var(--font-serif); }
.mask {
  position: fixed;
  inset: 0;
  z-index: 170;
  background: rgba(25, 25, 25, 0.28);
  display: grid;
  place-items: center;
  padding: 16px;
}
.modal {
  width: min(520px, 100%);
  background: var(--bg-app);
  border: 1px solid var(--border);
  padding: 16px;
}
.modal header, .modal footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.x { border: none; background: transparent; font-size: 20px; }
.drop {
  margin: 12px 0;
  padding: 36px 16px;
  border: 1px dashed var(--border);
  background: var(--bg-soft);
  text-align: center;
  cursor: pointer;
}
.drop.on { border-color: var(--accent); background: var(--warning-soft); }
.up { display: flex; flex-direction: column; gap: 10px; margin: 12px 0; }
.up-meta { display: flex; justify-content: space-between; font-size: 12px; }
/* 接真实后端后补的几条 */
.hidden-input { display: none; }
.kb-state { margin-left: 10px; font-size: 12px; color: var(--text-muted); }
.kb-state.err { color: #c62828; }
.modal-hint { margin: 10px 0 0; font-size: 12px; color: var(--text-muted); line-height: 1.6; }
.up-meta em.err { color: #c62828; }

/* 断点从 860 下调到 760：860 偏高，窗口稍窄（或系统缩放 150%）就压成一栏，
   侧栏变成横向滚动条、右侧详情挤到下面，页面看着很空。 */
@media (max-width: 760px) {
  .shell { grid-template-columns: 1fr; }
  .note-list { flex-direction: row; overflow-x: auto; max-height: none; }
  .note { min-width: 190px; }
  .meta, .empty ol { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 390px) {
  h2 { font-size: 22px; }
  .meta, .empty ol { grid-template-columns: 1fr; }
  .kb-actions { width: 100%; }
  .kb-actions button { flex: 1 1 auto; }
}
</style>
