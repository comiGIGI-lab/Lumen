<script setup>
/**
 * ImportPage —— 主应用内正式文档导入页（已接真实后端）
 *
 * 与后端 /api/knowledge/import 对接：选中/拖入文件 → 逐个上传 → 后端解析入库
 * （PDF 走 pypdf、Markdown/txt 直读、图片走多模态模型识图），上传完就能在知识库看到。
 * 逐文件上传而不是一次全发：这样每一行的进度是**真实**的，一个文件失败也不拖累其它。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SnakeBar from './SnakeBar.vue'
import { api } from '@/api/client'
import { useKnowledge } from '@/composables/useKnowledge'

const emit = defineEmits(['back', 'open-knowledge', 'go-course'])

/** 与后端 kb_ingest 支持的扩展名保持一致 */
const ACCEPT = '.pdf,.md,.markdown,.txt,.text,.png,.jpg,.jpeg,.webp,.bmp,.gif'
const MAX_FILES = 10
const MAX_BYTES = 16 * 1024 * 1024

const { notes, current, currentId, pickNote, createNote, refresh, ensureLoaded } = useKnowledge()

ensureLoaded()

const picked = ref([]) // {id,file,name,size,type,status,progress,error,chunks}
const newTitle = ref('')
/** '' = 不指定（每个文件按自己的文件名成一条笔记） */
const targetId = ref('')
const dragOn = ref(false)
const running = ref(false)
const step = ref(1)
const hint = ref('')
const summary = ref(null)
const caps = ref(null)
const fileInput = ref(null)
let seq = 0

api
  .knowledgeCapabilities()
  .then((c) => {
    caps.value = c
  })
  .catch(() => {
    /* 能力探测失败不阻塞导入，后端会给明确报错 */
  })

watch(currentId, (id) => {
  if (id && notes.value.some((n) => n.id === id) && !targetId.value) targetId.value = id
}, { immediate: true })

const targetNote = computed(() => notes.value.find((n) => n.id === targetId.value) || null)
const allReady = computed(() => picked.value.length > 0 && picked.value.every((f) => f.status === 'ready'))
const anyFailed = computed(() => picked.value.some((f) => f.status === 'failed'))
const startLabel = computed(() => {
  if (running.value) return '上传解析中'
  if (allReady.value) return '重新选择'
  return '开始导入'
})

const statusText = (f) =>
  ({
    waiting: '待开始',
    uploading: `上传中 ${Math.round(f.progress)}%`,
    parsing: '解析中',
    ready: '已入库',
    failed: '失败',
  }[f.status] || f.status)

function fmtSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB'
  return bytes + ' B'
}

function resetQueue() {
  picked.value = []
  hint.value = ''
  summary.value = null
  step.value = 1
}

function addFiles(fileList) {
  const incoming = Array.from(fileList || [])
  if (!incoming.length) return
  const room = MAX_FILES - picked.value.length
  if (room <= 0) {
    hint.value = `一次最多 ${MAX_FILES} 个文件。`
    return
  }
  const accepted = []
  const rejected = []
  incoming.slice(0, room).forEach((file) => {
    if (file.size > MAX_BYTES) {
      rejected.push(`${file.name}（${fmtSize(file.size)} 超过 16 MB）`)
      return
    }
    accepted.push({
      id: 'f' + ++seq,
      file,
      name: file.name,
      size: fmtSize(file.size),
      type: (file.name.split('.').pop() || '').toUpperCase(),
      status: 'waiting',
      progress: 0,
      error: '',
      chunks: 0,
    })
  })
  picked.value = picked.value.concat(accepted)
  step.value = 1
  summary.value = null
  hint.value = rejected.length
    ? `已跳过：${rejected.join('、')}`
    : accepted.length
      ? `已选 ${accepted.length} 个文件，点「开始导入」上传解析。`
      : ''
}

function onPickClick() {
  if (running.value) return
  fileInput.value?.click()
}

function onFileChange(e) {
  addFiles(e.target.files)
  e.target.value = '' // 允许重复选同一个文件
}

function onDrop(e) {
  e.preventDefault()
  dragOn.value = false
  if (running.value) return
  addFiles(e.dataTransfer?.files)
}

function removePicked(row) {
  if (running.value) return
  picked.value = picked.value.filter((f) => f.id !== row.id)
}

/** 把界面上的「归入笔记」翻成后端要的 title（不指定就留空，按文件名各成一条） */
function targetTitle() {
  return targetNote.value?.title || ''
}

async function addNoteThenImport() {
  const title = newTitle.value.trim()
  if (!title) {
    hint.value = '请先填一个笔记标题。'
    return
  }
  await createNote(title)
  const created = notes.value.find((n) => n.title === title)
  if (created) {
    targetId.value = created.id
    pickNote(created.id)
  }
  newTitle.value = ''
  hint.value = `已新建「${title}」，这次导入的材料会归到它下面。`
}

async function startParse() {
  if (running.value) return
  if (allReady.value) {
    resetQueue()
    return
  }
  if (!picked.value.length) {
    hint.value = '请先选择文件。'
    return
  }

  running.value = true
  step.value = 2
  hint.value = '正在上传并解析…'
  const groupTitle = targetTitle()

  let okCount = 0
  let failCount = 0
  const details = []

  for (const row of picked.value) {
    if (row.status === 'ready') {
      okCount += 1
      continue
    }
    row.status = 'uploading'
    row.progress = 0
    row.error = ''
    try {
      const res = await api.knowledgeImport([row.file], {
        title: groupTitle,
        onProgress: (p) => {
          row.progress = Math.round(p * 100)
          if (p >= 1) row.status = 'parsing'
        },
      })
      const r = (res.results || [])[0] || {}
      if (r.ok) {
        row.status = 'ready'
        row.progress = 100
        row.chunks = r.chunks || 0
        okCount += 1
        details.push(`「${row.name}」入库 ${r.chunks || 0} 块`)
      } else {
        row.status = 'failed'
        row.error = r.error || '导入失败'
        failCount += 1
      }
    } catch (e) {
      row.status = 'failed'
      row.error = e.message || String(e)
      failCount += 1
    }
  }

  summary.value = { ok: okCount, failed: failCount, total: picked.value.length }
  await refresh('')
  // 导入后把焦点切到刚归入的笔记（或第一条），用户点「去知识库查看」能直接看到
  const landed = groupTitle ? notes.value.find((n) => n.title === groupTitle) : null
  if (landed) pickNote(landed.id)

  if (failCount === 0) {
    hint.value = `已入库 ${okCount} 个文件。${details.join('；')}`
    step.value = 3
  } else {
    hint.value = `完成：成功 ${okCount} 个，失败 ${failCount} 个。失败的请看每行提示。`
    step.value = okCount ? 3 : 2
  }
  running.value = false
}

function cancelTask() {
  if (running.value) return // 上传中不给取消，避免半截状态
  resetQueue()
  hint.value = '已清空待导入列表。'
}

onBeforeUnmount(() => {
  picked.value = []
})
</script>

<template>
  <div class="imp">
    <p class="crumb">
      <button type="button" class="link" @click="emit('back')">课程生成</button>
      <span>/</span>
      <em>导入文档</em>
    </p>
    <p class="eyebrow">Step 1 · Upload</p>
    <h2>导入文档</h2>
    <p class="lead">
      上传课件与讲义，解析后进入知识库。PDF 走文本层抽取，Markdown / txt 直读，图片走多模态模型识图。
      材料进库之后，到课程问答里提问就能引用到。
    </p>

    <div class="steps">
      <span :class="{ on: step === 1 }">01 选择文件</span>
      <span :class="{ on: step === 2 }">02 上传解析</span>
      <span :class="{ on: step === 3 }">03 入库可查看</span>
    </div>

    <div class="grid">
      <div class="main">
        <div
          class="drop"
          :class="{ on: dragOn }"
          @click="onPickClick"
          @dragenter.prevent="dragOn = true"
          @dragover.prevent="dragOn = true"
          @dragleave.prevent="dragOn = false"
          @drop="onDrop"
        >
          <h3>把文件拖到这里</h3>
          <p>支持 PDF / Markdown / txt / 图片（png·jpg·webp），单个 ≤ 16 MB，一次最多 10 个</p>
          <button type="button" class="ok" @click.stop="onPickClick">选择文件</button>
          <input
            ref="fileInput"
            type="file"
            multiple
            :accept="ACCEPT"
            class="hidden-input"
            @change="onFileChange"
          />
        </div>
        <p v-if="hint" class="demo-note">{{ hint }}</p>
        <p v-if="caps && caps.document && !caps.document.pdf" class="demo-note">
          提示：服务器未装 pypdf，PDF 暂时解析不了；Markdown / txt / 图片不受影响。
        </p>

        <div class="queue">
          <header>
            <h3>待导入文件</h3>
            <span>共 {{ picked.length }} 个文件</span>
          </header>
          <div v-for="f in picked" :key="f.id" class="q-row">
            <div class="q-meta">
              <b>{{ f.name }}</b>
              <span>{{ f.size }} · {{ f.type }}</span>
            </div>
            <div class="q-prog">
              <SnakeBar :progress="f.progress" :status="f.status" />
            </div>
            <div class="q-status" :class="f.status">
              {{ statusText(f) }}
              <em v-if="f.status === 'failed' && f.error" class="q-err">{{ f.error }}</em>
            </div>
            <button
              v-if="!running && f.status !== 'ready'"
              type="button"
              class="ghost small"
              @click="removePicked(f)"
            >移除</button>
          </div>
          <p v-if="!picked.length" class="none">还没有选择文件。</p>
        </div>

        <div v-if="summary && summary.ok" class="done">
          <div>
            <b>已入库 {{ summary.ok }} 个文件{{ summary.failed ? `，${summary.failed} 个失败` : '' }}</b>
            <p v-if="targetNote">
              已归入「{{ targetNote.title }}」，共切出
              {{ picked.filter((f) => f.status === 'ready').reduce((s, f) => s + f.chunks, 0) }} 个分块。
            </p>
            <p v-else>每个文件按自己的文件名各成一条笔记。材料进库之后，到课程问答里提问。</p>
          </div>
          <div class="done-btns">
            <button type="button" class="ok" @click="emit('open-knowledge')">去知识库查看</button>
            <button type="button" class="ok" @click="emit('go-course')">去课程问答</button>
          </div>
        </div>

        <div class="act">
          <button type="button" class="ghost" :disabled="running" @click="cancelTask">清空</button>
          <button type="button" class="ok" :disabled="running || !picked.length" @click="startParse">
            {{ startLabel }}
          </button>
          <span>上传即时解析入库；图片要过模型识图，会稍慢一些。</span>
        </div>
      </div>

      <aside>
        <div class="card">
          <h3>归入笔记</h3>
          <label>
            归入
            <select v-model="targetId">
              <option value="">不指定（每个文件各成一条）</option>
              <option v-for="n in notes" :key="n.id" :value="n.id">{{ n.title }}</option>
            </select>
          </label>
          <p class="hint">
            选定一条笔记，这批文件切出的分块会归到它下面；不指定就按文件名各成一条。
          </p>
          <div class="new-note">
            <input v-model="newTitle" type="text" placeholder="新笔记标题" />
            <button type="button" class="ghost" @click="addNoteThenImport">新建并归入</button>
          </div>
        </div>
        <div class="card">
          <h3>支持格式</h3>
          <p><span>课件 / 讲义</span><em>.pdf .md .txt</em></p>
          <p><span>板书 / 题目截图</span><em>.png .jpg .webp</em></p>
          <small>单个文件 ≤ 16 MB，单次最多 10 个。音频暂不支持。</small>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.imp { min-width: 0; }
.crumb { display: flex; gap: 8px; font-size: 12px; color: var(--text-muted); }
.link, .crumb em { background: none; border: none; padding: 0; color: inherit; font-style: normal; }
.eyebrow {
  margin-top: 10px;
  font-family: var(--font-serif);
  font-style: italic;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-size: 13px;
}
h2 { font-size: 32px; margin: 6px 0 10px; }
.lead { max-width: 40em; color: var(--text-secondary); }
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 18px 0;
}
.steps span {
  border: 1px solid var(--border);
  border-radius: 1000px;
  padding: 6px 14px;
  font-size: 12px;
  color: var(--text-muted);
}
.steps span.on {
  border-color: var(--accent);
  color: var(--accent);
}
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
  gap: 18px;
}
.drop {
  border: 1px dashed var(--border);
  background: var(--bg-soft);
  padding: 48px 20px;
  text-align: center;
  cursor: pointer;
}
.drop.on { border-color: var(--accent); background: #ffe8d6; }
.queue, .card, .done {
  margin-top: 16px;
  background: #fff;
  border: 1px solid var(--border);
}
.queue header, .done, .act, .q-row, .card p {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.queue header, .q-row, .card, .done { padding: 14px 16px; }
.q-row { border-top: 1px solid var(--border); flex-wrap: wrap; min-width: 0; }
.q-meta { min-width: 0; flex: 1 1 140px; }
.q-meta b { display: block; font-weight: 400; }
.q-meta span, .q-status, .act span, small, .card em, .demo-note { color: var(--text-muted); font-size: 12px; }
.demo-note { margin: 10px 0 0; line-height: 1.65; }
.q-prog { width: 160px; }
.q-status.ready { color: #2e7d32; }
.q-status.uploading, .q-status.parsing { color: var(--accent); }
.ok, .ghost, .chip {
  border-radius: 1000px;
  padding: 8px 16px;
  font-size: 13px;
}
.ok { border: 1px solid var(--primary); background: var(--primary); color: #fff; }
.ghost { border: 1px solid var(--border); background: #fff; }
.ok:disabled { opacity: 0.6; }
.card { display: flex; flex-direction: column; gap: 10px; }
.card label, .chk { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-muted); }
.chk { flex-direction: row; align-items: center; }
select, .new-note input {
  height: 36px;
  border: 1px solid var(--border);
  background: #fff;
  width: 100%;
  padding: 0 10px;
}
.hint { margin: 0; font-size: 12px; color: var(--text-muted); line-height: 1.6; }
.new-note { display: flex; flex-direction: column; gap: 8px; }
.act { margin-top: 16px; flex-wrap: wrap; }
.done { border-color: var(--border); flex-wrap: wrap; }
.done-btns { display: flex; flex-wrap: wrap; gap: 8px; }
/* 接入真实上传后补的几条 */
.hidden-input { display: none; }
.q-status.failed { color: #c62828; }
.q-err { display: block; margin-top: 3px; color: #c62828; font-size: 11px; line-height: 1.5; }
.none { margin: 8px 0 0; font-size: 12px; color: var(--text-muted); }

@media (max-width: 860px) {
  .grid { grid-template-columns: 1fr; }
  h2 { font-size: 26px; }
}
@media (max-width: 390px) {
  .q-prog, .q-status { width: 100%; }
  .act .ok, .act .ghost, .done-btns .ok { width: 100%; }
  h2 { font-size: 22px; }
}
</style>
