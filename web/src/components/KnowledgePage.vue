<script setup>
/**
 * KnowledgePage —— 主应用内正式知识库页
 * 笔记 / 文档 / 分块走 useKnowledge 单例；分块只来自当前笔记的关联文档。
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import SnakeBar from './SnakeBar.vue'
import { DEMO_FILES, TAG_LABEL, useKnowledge } from '@/composables/useKnowledge'

const emit = defineEmits(['back', 'open-import', 'go-course'])

const TAGS = [
  { id: 'all', label: '全部' },
  { id: 'high-math', label: '高数' },
  { id: 'english', label: '英语' },
  { id: 'mistakes', label: '错题' },
  { id: 'others', label: '其他' },
]

const TYPE_LABEL = { pdf: 'PDF', image: '图片', audio: '音频' }
const STATUS_LABEL = { ready: '演示完成', parsing: '解析中', queue: '排队中', failed: '解析失败' }

const {
  notes,
  currentId,
  current,
  currentDocs,
  currentChunks,
  pickNote,
  createNote,
  removeDoc,
  retryDoc,
  attachDemoDocs,
  loadDemo,
} = useKnowledge()

const filter = ref('all')
const keyword = ref('')
const empty = ref(false)
const showImport = ref(false)
const importPhase = ref('drop')
const uploadRows = ref([])
const savedHint = ref(false)
const dragOn = ref(false)
const demoNote = ref('')
let uploadTimer = 0
let hintTimer = 0

const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return notes.value.filter((n) => {
    if (filter.value !== 'all' && n.tag !== filter.value) return false
    if (!q) return true
    return (n.title + (TAG_LABEL[n.tag] || '')).toLowerCase().includes(q)
  })
})

function newNote() {
  createNote()
  filter.value = 'all'
  empty.value = false
}

function saveRemark() {
  savedHint.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => {
    savedHint.value = false
  }, 1400)
}

function deleteDoc(doc) {
  if (!current.value || !doc) return
  removeDoc(current.value.id, doc.id)
}

function openImport() {
  showImport.value = true
  importPhase.value = 'drop'
  uploadRows.value = []
  demoNote.value = ''
  if (uploadTimer) clearInterval(uploadTimer)
}

function cancelImport() {
  if (uploadTimer) {
    clearInterval(uploadTimer)
    uploadTimer = 0
  }
  importPhase.value = 'drop'
  uploadRows.value = []
  demoNote.value = '上传任务已取消。'
}

function closeImport() {
  cancelImport()
  showImport.value = false
}

function noteNoWrite() {
  demoNote.value = '写入接口尚未接入，本次不会选择或上传本地文件。要看解析动画，请点开始解析。这是演示。'
}

function startUpload() {
  if (importPhase.value !== 'drop') return
  demoNote.value = `正在播放演示动画，示例文件将归档到「${current.value?.title || '当前笔记'}」。写入接口还没接。`
  importPhase.value = 'run'
  uploadRows.value = DEMO_FILES.map((f) => ({ ...f, progress: 0, status: 'uploading' }))
  const speed = [7, 11, 4]
  uploadTimer = setInterval(() => {
    let allDone = true
    uploadRows.value.forEach((row, i) => {
      if (row.progress < 100) {
        allDone = false
        row.progress = Math.min(100, row.progress + speed[i])
        if (row.progress >= 100) row.status = 'ready'
      }
    })
    if (allDone) {
      clearInterval(uploadTimer)
      uploadTimer = 0
      importPhase.value = 'done'
      attachDemoDocs(current.value?.id)
      demoNote.value = '演示完成。示例文件已归档到当前笔记，不是真实上传。'
      setTimeout(() => {
        showImport.value = false
        importPhase.value = 'drop'
        uploadRows.value = []
      }, 900)
    }
  }, 180)
}

function onDrop(e) {
  e.preventDefault()
  dragOn.value = false
  noteNoWrite()
}

function loadSeed() {
  empty.value = false
  loadDemo()
}

onBeforeUnmount(() => {
  if (uploadTimer) clearInterval(uploadTimer)
  clearTimeout(hintTimer)
})
</script>

<template>
  <div class="kb">
    <div class="kb-bar">
      <div>
        <p class="eyebrow">Knowledge</p>
        <h2>知识库</h2>
        <p class="lead">这里查看笔记和文档。提问在学习方案生成页底部的课程问答。当前是演示数据，写入接口还没接，拖文件或点解析不会真的进库。</p>
      </div>
      <div class="kb-actions">
        <button type="button" class="ghost" @click="emit('back')">课程生成</button>
        <button type="button" class="ghost" @click="emit('open-import')">文档导入</button>
        <button type="button" class="ok" @click="openImport">导入文档</button>
      </div>
    </div>

    <div class="kb-search">
      <input v-model="keyword" type="search" placeholder="搜索笔记标题、标签或知识点" />
    </div>

    <div v-if="empty" class="empty">
      <h3>知识库还是空的</h3>
      <p>这里查看笔记和文档。材料进库之后，到课程问答里提问。当前是演示数据，写入接口还没接。</p>
      <ol>
        <li><b>01 上传课件</b><span>支持 PDF / 图片 / 音频，当前为演示</span></li>
        <li><b>02 自动解析</b><span>OCR + 转写 + 分块索引，动画可看，不会真的进库</span></li>
        <li><b>03 去课程问答</b><span>提问不在这一页，在学习方案生成页底部</span></li>
      </ol>
      <div class="empty-btns">
        <button type="button" class="ok" @click="openImport">导入第一份文档</button>
        <button type="button" class="ghost" @click="loadSeed">载入示例笔记</button>
        <button type="button" class="ghost" @click="emit('go-course')">去课程问答</button>
      </div>
    </div>

    <div v-else class="shell">
      <aside>
        <div class="sb-head">
          <span>我的笔记</span>
          <em>共 {{ filtered.length }} 条笔记</em>
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
          <p v-if="!filtered.length" class="none">没有匹配的笔记</p>
        </div>
        <button type="button" class="ghost new" @click="newNote">新建笔记</button>
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
          <span>笔记标题</span>
          <input v-model="current.title" />
        </label>

        <dl class="meta">
          <div><dt>创建时间</dt><dd>{{ current.created }}</dd></div>
          <div><dt>最近更新</dt><dd>{{ current.updated }}</dd></div>
          <div><dt>标签</dt><dd>{{ TAG_LABEL[current.tag] }}</dd></div>
          <div><dt>关联文档</dt><dd>{{ currentDocs.length }} 个</dd></div>
        </dl>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>文档名</th>
                <th>类型</th>
                <th>状态</th>
                <th>分块数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!currentDocs.length">
                <td colspan="5" class="empty-cell">这条笔记还没有关联文档。分块只来自这里的材料。</td>
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
                  <button v-if="d.status === 'failed'" type="button" class="danger" @click="retryDoc(d)">重试</button>
                  <button type="button" class="ghost small" @click="deleteDoc(d)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="chunks">
          <h3>分块预览</h3>
          <p v-if="!currentDocs.length" class="empty-chunk">
            还没有材料。分块只来自这条笔记的关联文档。
            <button type="button" class="ok" @click="openImport">导入到这条笔记</button>
          </p>
          <p v-else-if="!currentChunks.length" class="empty-chunk">
            这条笔记还没有可查看的分块。解析完成的文档才会出现在这里。
            <button type="button" class="ok" @click="openImport">导入到这条笔记</button>
          </p>
          <article v-for="c in currentChunks" :key="c.id">
            <header><span>{{ c.src }}</span></header>
            <p>{{ c.text }}</p>
          </article>
        </div>

        <div class="remark">
          <h3>备注</h3>
          <textarea v-model="current.remark" rows="4" placeholder="记录你的复习计划、易错点"></textarea>
          <div class="remark-row">
            <button type="button" class="ok" @click="saveRemark">保存备注</button>
            <em :class="{ show: savedHint }">已保存</em>
            <span>修改后可手动保存，数据留在这台浏览器</span>
          </div>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="showImport" class="mask" @click.self="closeImport">
        <div class="modal" role="dialog" aria-label="导入文档">
          <header>
            <h3>导入文档</h3>
            <button type="button" class="x" @click="closeImport">×</button>
          </header>
          <div
            v-if="importPhase === 'drop'"
            class="drop"
            :class="{ on: dragOn }"
            @click="noteNoWrite"
            @dragenter.prevent="dragOn = true"
            @dragover.prevent="dragOn = true"
            @dragleave.prevent="dragOn = false"
            @drop="onDrop"
          >
            <p>把文件拖到这里，或点击选择</p>
            <span>这是演示。写入接口还没接，拖进来不会进库。支持 PDF / 图片 / 音频</span>
          </div>
          <p v-if="demoNote" class="demo-note">{{ demoNote }}</p>
          <div v-if="importPhase !== 'drop'" class="up">
            <p>正在播放演示动画，示例文件不会真正入库</p>
            <div v-for="row in uploadRows" :key="row.name" class="up-row">
              <div class="up-meta">
                <span>{{ row.name }}</span>
                <em>{{ Math.round(row.progress) }}%</em>
              </div>
              <SnakeBar :progress="row.progress" :status="row.status" />
            </div>
            <p v-if="importPhase === 'done'">演示完成。示例文件已归档到「{{ current?.title }}」，不是真实上传。</p>
          </div>
          <footer>
            <button type="button" class="ghost" @click="cancelImport">取消</button>
            <button type="button" class="ok" :disabled="importPhase !== 'drop'" @click="startUpload">开始解析</button>
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
  background: #fff;
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
  background: #fff;
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
  border-color: #191919;
}
.meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  background: #fff;
  border: 1px solid var(--border);
  padding: 12px;
}
dt {
  color: var(--text-muted);
  font-size: 12px;
}
.table-wrap {
  overflow-x: auto;
  background: #fff;
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
  background: #fdecee;
}
.st.ready { color: #2e7d32; }
.st.parsing, .st.queue { color: var(--accent); }
.st.failed { color: var(--error); }
.pct { font-size: 11px; color: var(--text-muted); margin-left: 6px; }
.chunks article,
.remark,
.title-lab,
.empty {
  background: #fff;
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
  background: #fff;
}
.danger {
  border: 1px solid var(--error);
  color: var(--error);
  background: #fff;
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
  background: #fbf9f6;
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
.drop.on { border-color: var(--accent); background: #ffe8d6; }
.up { display: flex; flex-direction: column; gap: 10px; margin: 12px 0; }
.up-meta { display: flex; justify-content: space-between; font-size: 12px; }

@media (max-width: 860px) {
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
