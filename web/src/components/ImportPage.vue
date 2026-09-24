<script setup>
/**
 * ImportPage —— 主应用内正式文档导入页
 * 归档目标走知识库笔记列表。取消只停解析，不返回课程生成。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SnakeBar from './SnakeBar.vue'
import { DEMO_FILES, useKnowledge } from '@/composables/useKnowledge'

const emit = defineEmits(['back', 'open-knowledge', 'go-course'])

const SPEED = [7, 11, 4]
const { notes, current, currentId, pickNote, createNote, attachDemoDocs } = useKnowledge()

function blankQueue() {
  return DEMO_FILES.map((f, i) => ({
    id: 'f' + (i + 1),
    name: f.name,
    size: f.size,
    type: f.type.toUpperCase(),
    status: 'waiting',
    progress: 0,
  }))
}

const files = ref(blankQueue())
const targetId = ref(currentId.value)
watch(currentId, (id) => {
  if (id && notes.value.some((n) => n.id === id)) targetId.value = id
}, { immediate: true })
const newTitle = ref('')
const ocr = ref('自动识别')
const chunk = ref('自动（按语义）')
const transcribe = ref(true)
const dragOn = ref(false)
const running = ref(false)
const step = ref(1)
const hint = ref('')
let timer = 0

const targetNote = computed(() => notes.value.find((n) => n.id === targetId.value) || current.value)
const allReady = computed(() => files.value.length && files.value.every((f) => f.status === 'ready'))
const startLabel = computed(() => {
  if (running.value) return '解析中'
  if (allReady.value) return '重新演示'
  return '开始解析'
})
const statusText = (f) => {
  if (f.status === 'uploading') return '上传中 ' + Math.round(f.progress) + '%'
  return { waiting: '待开始', parsing: '解析中', ready: '演示完成', cancelled: '已取消' }[f.status]
}

function setStep(n) {
  step.value = n
}

function noteNoWrite() {
  hint.value = '写入接口尚未接入，本次不会选择或上传本地文件。要看解析动画，请点开始解析。这是演示。'
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = 0
  }
  running.value = false
}

function resetQueue() {
  stopTimer()
  files.value = blankQueue()
  hint.value = ''
  setStep(1)
}

function cancelTask() {
  stopTimer()
  files.value.forEach((f) => {
    f.status = 'waiting'
    f.progress = 0
    delete f.parseAt
  })
  hint.value = '上传任务已取消，队列回到待开始。返回课程生成请用面包屑或顶栏。'
  setStep(1)
}

function addNoteThenImport() {
  const title = newTitle.value.trim() || '未命名笔记'
  const id = createNote(title)
  targetId.value = id
  pickNote(id)
  newTitle.value = ''
  hint.value = `已新建「${title}」，演示导入将归档到这条笔记。`
}

function startParse() {
  if (running.value) return
  if (allReady.value) {
    resetQueue()
    return
  }
  const dest = targetNote.value
  if (!dest) {
    hint.value = '请先选择或新建一条笔记再导入。'
    return
  }
  pickNote(dest.id)
  hint.value = `正在播放演示动画，示例文件将归档到「${dest.title}」。写入接口还没接。`
  running.value = true
  files.value.forEach((f) => {
    f.status = 'uploading'
    f.progress = 0
    delete f.parseAt
  })
  setStep(2)
  timer = setInterval(() => {
    let done = true
    files.value.forEach((f, i) => {
      if (f.status === 'uploading') {
        done = false
        f.progress = Math.min(100, f.progress + SPEED[i])
        if (f.progress >= 100) {
          f.status = 'parsing'
          f.parseAt = Date.now()
        }
      } else if (f.status === 'parsing') {
        done = false
        if (Date.now() - f.parseAt > 1100) {
          f.status = 'ready'
          f.progress = 100
        }
      }
    })
    if (done) {
      stopTimer()
      attachDemoDocs(dest.id)
      hint.value = `演示完成。示例文件已归档到「${dest.title}」，不是真实上传。`
      setStep(3)
    }
  }, 220)
}

function onDrop(e) {
  e.preventDefault()
  dragOn.value = false
  noteNoWrite()
}

onBeforeUnmount(() => {
  stopTimer()
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
    <p class="lead">支持课件 PDF、板书照片与课堂录音。材料进库之后，到课程问答里提问。当前是演示数据，写入接口还没接，拖文件或点解析不会真的进库。</p>

    <div class="steps">
      <span :class="{ on: step === 1 }">01 选择文件</span>
      <span :class="{ on: step === 2 }">02 解析分块</span>
      <span :class="{ on: step === 3 }">03 入库可查看</span>
    </div>

    <div class="grid">
      <div class="main">
        <div
          class="drop"
          :class="{ on: dragOn }"
          @click="noteNoWrite"
          @dragenter.prevent="dragOn = true"
          @dragover.prevent="dragOn = true"
          @dragleave.prevent="dragOn = false"
          @drop="onDrop"
        >
          <h3>把文件拖到这里</h3>
          <p>这是演示。写入接口还没接，拖进来不会进库。支持 PDF / 图片 / 音频，单个 ≤ 50 MB</p>
          <button type="button" class="ok" @click.stop="noteNoWrite">选择文件</button>
        </div>
        <p v-if="hint" class="demo-note">{{ hint }}</p>

        <div class="queue">
          <header>
            <h3>待导入文件</h3>
            <span>共 {{ files.length }} 个文件</span>
          </header>
          <div v-for="f in files" :key="f.id" class="q-row">
            <div class="q-meta">
              <b>{{ f.name }}</b>
              <span>{{ f.size }} · {{ f.type }}</span>
            </div>
            <div class="q-prog">
              <SnakeBar :progress="f.progress" :status="f.status" />
            </div>
            <div class="q-status" :class="f.status">{{ statusText(f) }}</div>
          </div>
        </div>

        <div v-if="allReady" class="done">
          <div>
            <b>演示完成</b>
            <p>示例文件已归档到「{{ targetNote?.title }}」，不是真实上传。材料进库之后，到课程问答里提问。</p>
          </div>
          <div class="done-btns">
            <button type="button" class="ok" @click="emit('open-knowledge')">去知识库查看</button>
            <button type="button" class="ok" @click="emit('go-course')">去课程问答</button>
          </div>
        </div>

        <div class="act">
          <button type="button" class="ghost" @click="cancelTask">取消</button>
          <button type="button" class="ok" :disabled="running" @click="startParse">{{ startLabel }}</button>
          <span>取消只停解析。返回课程生成请用上方面包屑或顶栏。</span>
        </div>
      </div>

      <aside>
        <div class="card">
          <h3>解析设置</h3>
          <label>
            OCR 语言
            <select v-model="ocr">
              <option>自动识别</option>
              <option>中文优先</option>
              <option>英文优先</option>
            </select>
          </label>
          <label>
            分块策略
            <select v-model="chunk">
              <option>自动（按语义）</option>
              <option>按页切分</option>
              <option>按章节切分</option>
            </select>
          </label>
          <label>
            归入笔记
            <select v-model="targetId">
              <option v-for="n in notes" :key="n.id" :value="n.id">{{ n.title }}</option>
            </select>
          </label>
          <p class="hint">默认当前正在看的笔记。也可以新建一条再导入。这是演示，写入接口还没接。</p>
          <div class="new-note">
            <input v-model="newTitle" type="text" placeholder="新笔记标题" />
            <button type="button" class="ghost" @click="addNoteThenImport">新建并归入</button>
          </div>
          <label class="chk">
            <input v-model="transcribe" type="checkbox" />
            音频自动转写为文本
          </label>
        </div>
        <div class="card">
          <h3>支持格式</h3>
          <p><span>课件 / 讲义 PDF</span><em>.pdf</em></p>
          <p><span>板书 / 题目截图</span><em>.jpg .png</em></p>
          <p><span>课堂录音</span><em>.mp3 .wav .m4a</em></p>
          <small>单个文件 ≤ 50 MB，单次最多 20 个</small>
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
