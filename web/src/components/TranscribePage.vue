<script setup>
/**
 * TranscribePage —— 语音转文字（离线识别，非录音）
 *
 * 为什么是「上传/录一段音频」而不是「按住说话」：
 *   2026-09-26 摘掉录音转写，根因是 getUserMedia / MediaRecorder 属于
 *   「安全上下文」API，线上是 http://47.106.76.244，浏览器直接拒绝。
 *   <input type="file"> 不受这个限制，手机端加 capture 还能直接唤起系统录音机，
 *   所以这条路径在**不改 HTTPS** 的前提下今天就能用。
 *
 * 识别引擎是 Vosk（离线中文模型，跑在我们自己的服务器上）：
 *   音频不上传任何第三方 AI 接口，学生声音不出这台机器 —— 对教学场景是硬需求。
 *
 * 另注：复制按钮**不能只用 navigator.clipboard** —— 它同样要求安全上下文，
 *   http 下是 undefined。所以下面做了 execCommand 兜底。
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from '@/i18n'
import SnakeBar from './SnakeBar.vue'
import { api } from '@/api/client'
import {
  MAX_FILE_BYTES,
  canDecodeAudio,
  decodeToPcm16k,
  probeDuration,
} from '@/utils/audio'

const emit = defineEmits(['back', 'open-knowledge', 'go-course'])
const { t } = useI18n()

const ACCEPT = 'audio/*,.mp3,.m4a,.aac,.wav,.ogg,.oga,.webm,.flac,.opus,.mp4'

/** 引擎状态：null = 还在探测；false = 不可用（展示 reason） */
const engine = ref(null)
/** 'pick' | 'reading' | 'uploading' | 'done' */
const stage = ref('pick')
const file = ref(null)
const duration = ref(0)
const progress = ref(0)
const error = ref('')
const hint = ref('')
const result = ref('')
const stats = ref(null)
const saving = ref(false)
const saved = ref(false)
const noteTitle = ref('')
const dragOn = ref(false)

const pickInput = ref(null)
const captureInput = ref(null)

const decoding = computed(() => stage.value === 'reading' || stage.value === 'uploading')
const maxSeconds = computed(() => engine.value?.max_seconds || 480)
const busyLabel = computed(() => (stage.value === 'reading' ? '正在解码音频…' : '服务器识别中…'))
// SnakeBar 只认 waiting / uploading / parsing / ready 四种。
// 出错退回 'pick' 时必须给 waiting —— 给 ready 会画成满格，看着像"已完成"。
const barStatus = computed(() =>
  decoding.value ? 'uploading' : stage.value === 'done' ? 'ready' : 'waiting'
)

api
  .asrStatus()
  .then((s) => {
    engine.value = s
  })
  .catch((e) => {
    engine.value = { available: false, reason: e.message || '能力探测失败' }
  })

/** 走一次能力探测，refresh 用得上（换了服务器 / 补装模型后不必刷新页面） */
function recheck() {
  engine.value = null
  api
    .asrStatus()
    .then((s) => {
      engine.value = s
    })
    .catch((e) => {
      engine.value = { available: false, reason: e.message || '能力探测失败' }
    })
}

function fmtSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB'
  if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB'
  return bytes + ' B'
}

function fmtClock(sec) {
  const s = Math.max(0, Math.round(sec || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function reset() {
  file.value = null
  duration.value = 0
  progress.value = 0
  error.value = ''
  hint.value = ''
  result.value = ''
  stats.value = null
  saved.value = false
  noteTitle.value = ''
  stage.value = 'pick'
}

function onPickClick() {
  if (decoding.value) return
  pickInput.value?.click()
}

function onCaptureClick() {
  if (decoding.value) return
  captureInput.value?.click()
}

function onFileChange(e) {
  const f = e.target.files?.[0]
  e.target.value = '' // 允许重复选同一个文件
  if (f) start(f)
}

function onDrop(e) {
  e.preventDefault()
  dragOn.value = false
  if (decoding.value) return
  const f = e.dataTransfer?.files?.[0]
  if (f) start(f)
}

/** 选中文件后的完整流程：校验 → 探测时长 → 解码成 16k PCM → 上传识别 */
async function start(f) {
  reset()

  if (!canDecodeAudio()) {
    error.value = '当前浏览器不支持音频解码，请换 Chrome / Edge / Safari 打开。'
    return
  }
  if (f.size > MAX_FILE_BYTES) {
    error.value = `文件 ${fmtSize(f.size)} 超过 ${fmtSize(MAX_FILE_BYTES)} 上限，请先裁剪。`
    return
  }

  file.value = f

  // ① 先只读时长。超过上限就早点拒，免得白白解码几十 MB 把手机浏览器搞崩。
  const probed = await probeDuration(f)
  if (Number.isFinite(probed) && probed > maxSeconds) {
    error.value =
      `音频 ${fmtClock(probed)}，超过单次 ${fmtClock(maxSeconds)} 的上限。` +
      '请分段上传，或先用手机自带的剪辑功能切短。'
    file.value = null
    return
  }

  // ② 解码 + 重采样到 16k 单声道（全在浏览器里做，服务器因此不用装 ffmpeg）
  stage.value = 'reading'
  let out
  try {
    out = await decodeToPcm16k(f, {
      onProgress: (p) => {
        progress.value = Math.round(p * 100)
      },
    })
  } catch (e) {
    error.value = e.message || String(e)
    stage.value = 'pick'
    file.value = null
    return
  }

  if (!out.pcm.length) {
    error.value = '这段音频里没有可识别的声音（时长 0 或全静音）。'
    stage.value = 'pick'
    file.value = null
    return
  }
  if (out.duration > maxSeconds) {
    error.value = `解码后时长 ${fmtClock(out.duration)} 超限，请分段上传。`
    stage.value = 'pick'
    file.value = null
    return
  }

  duration.value = out.duration
  noteTitle.value = (f.name || '语音笔记').replace(/\.[^.]+$/, '')

  // ③ 上传原始 PCM 字节流
  stage.value = 'uploading'
  progress.value = 0
  try {
    const r = await api.asrTranscribe(out.pcm, {
      onProgress: (p) => {
        progress.value = Math.round(p * 100)
      },
    })
    result.value = r.text || ''
    stats.value = r
    stage.value = 'done'
    hint.value = r.hint || ''
    if (!r.text) hint.value = r.hint || '没有识别到中文内容。请确认音频里是普通话人声。'
  } catch (e) {
    error.value = e.message || String(e)
    stage.value = 'pick'
  }
}

/**
 * 复制全文。
 * navigator.clipboard 只在安全上下文（https / localhost）下存在，
 * 线上是 http，所以必须留 execCommand 这条老路 —— 否则点了没反应。
 */
async function copyText() {
  const text = result.value
  if (!text) return
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      hint.value = '已复制到剪贴板。'
      return
    }
  } catch (_) {
    /* 落到下面的兜底 */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    hint.value = ok ? '已复制到剪贴板。' : '复制失败，请手动选中文本复制。'
  } catch (_) {
    hint.value = '复制失败，请手动选中文本复制。'
  }
}

function downloadTxt() {
  if (!result.value) return
  const base = (noteTitle.value || '语音转写').trim() || '语音转写'
  const blob = new Blob([result.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${base}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 存进知识库 —— 之后在「课程问答」里就能基于这段文字提问（RAG 读的就是知识库） */
async function saveToKnowledge() {
  if (saving.value || saved.value || !result.value) return
  const title = (noteTitle.value || '').trim() || '语音笔记'
  saving.value = true
  error.value = ''
  try {
    const r = await api.knowledgeCreate({
      title,
      content: result.value,
      tags: ['#voice'],
    })
    if (r && r.ok === false) throw new Error(r.error || '写入失败')
    saved.value = true
    hint.value = `已存入知识库「${title}」，可以去课程问答里就这段内容提问。`
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    saving.value = false
  }
}

onBeforeUnmount(reset)
</script>

<template>
  <div class="tr">
    <p class="crumb">
      <button type="button" class="link" @click="emit('back')">{{ t('page.transcribeBack') }}</button>
      <span>/</span>
      <em>{{ t('page.transcribeTitle') }}</em>
    </p>
    <p class="eyebrow">Speech · Offline ASR</p>
    <h2>{{ t('page.transcribeTitle') }}</h2>
    <p class="lead">{{ t('trPage.lead') }}</p>

    <!-- 引擎不可用：直接把原因和修法说清楚，别让用户白录一遍 -->
    <div v-if="engine && !engine.available" class="warn-box">
      <b>{{ t('trPage.engineDown') }}</b>
      <p>{{ engine.reason }}</p>
      <button type="button" class="ghost small" @click="recheck">{{ t('common.refresh') }}</button>
    </div>

    <div v-if="!engine" class="loading">{{ t('common.loading') }}</div>

    <div v-else class="grid" :class="{ disabled: !engine.available }">
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
          <h3>{{ t('trPage.pickTitle') }}</h3>
          <p>{{ t('trPage.pickHint') }}</p>
          <div class="drop-btns">
            <button type="button" class="ok" :disabled="!engine.available || decoding" @click.stop="onPickClick">
              {{ t('trPage.browse') }}
            </button>
            <button
              type="button"
              class="ghost"
              :disabled="!engine.available || decoding"
              @click.stop="onCaptureClick"
            >{{ t('trPage.capture') }}</button>
          </div>
          <input
            ref="pickInput"
            type="file"
            :accept="ACCEPT"
            class="hidden-input"
            @change="onFileChange"
          />
          <!-- capture：手机端直接唤起系统录音机，录完当文件交回来（桌面端忽略该属性） -->
          <input
            ref="captureInput"
            type="file"
            accept="audio/*"
            capture
            class="hidden-input"
            @change="onFileChange"
          />
        </div>

        <div v-if="file" class="queue">
          <header>
            <h3>{{ t('trPage.current') }}</h3>
            <span>{{ duration ? fmtClock(duration) : '—' }}</span>
          </header>
          <div class="q-row">
            <div class="q-meta">
              <b>{{ file.name }}</b>
              <span>{{ fmtSize(file.size) }} · {{ (file.name.split('.').pop() || '').toUpperCase() }}</span>
            </div>
            <div class="q-prog">
              <SnakeBar :progress="progress" :status="barStatus" />
            </div>
            <div class="q-status" :class="stage">
              <template v-if="decoding">{{ busyLabel }}</template>
              <template v-else-if="stage === 'done'">{{ t('trPage.done') }}</template>
              <template v-else>{{ t('trPage.wait') }}</template>
            </div>
          </div>
        </div>

        <p v-if="error" class="err">{{ error }}</p>
        <p v-else-if="hint" class="demo-note">{{ hint }}</p>

        <!-- 转写结果 -->
        <div v-if="stage === 'done'" class="result">
          <header>
            <h3>{{ t('trPage.result') }}</h3>
            <span v-if="stats">
              {{ t('trPage.speed', { x: stats.rtf ? (1 / stats.rtf).toFixed(1) : '—' }) }}
            </span>
          </header>
          <textarea v-model="result" rows="12" spellcheck="false"></textarea>
          <p class="count">{{ t('trPage.chars', { n: result.length }) }}</p>
        </div>

        <div class="act">
          <button type="button" class="ghost" :disabled="decoding" @click="reset">
            {{ t('trPage.again') }}
          </button>
          <button type="button" class="ghost" :disabled="!result" @click="copyText">
            {{ t('trPage.copy') }}
          </button>
          <button type="button" class="ghost" :disabled="!result" @click="downloadTxt">
            {{ t('trPage.download') }}
          </button>
        </div>
      </div>

      <aside>
        <div class="card">
          <h3>{{ t('trPage.engine') }}</h3>
          <p>
            <span>{{ t('trPage.engineName') }}</span>
            <em>{{ engine.available ? engine.model : '—' }}</em>
          </p>
          <p>
            <span>{{ t('trPage.limit') }}</span>
            <em>{{ fmtClock(engine.max_seconds) }}</em>
          </p>
          <small>{{ t('trPage.privacy') }}</small>
        </div>

        <div class="card">
          <h3>{{ t('trPage.toKb') }}</h3>
          <label>{{ t('trPage.kbTitle') }}<input v-model="noteTitle" type="text" /></label>
          <button
            type="button"
            class="ok"
            :disabled="!result || saving || saved"
            @click="saveToKnowledge"
          >
            {{ saved ? t('trPage.saved') : saving ? t('common.loading') : t('trPage.saveBtn') }}
          </button>
          <p class="hint">{{ t('trPage.kbHint') }}</p>
        </div>

        <div class="card">
          <h3>{{ t('trPage.howto') }}</h3>
          <p><span>{{ t('trPage.howto1') }}</span><em>mp3 / m4a / wav / ogg</em></p>
          <p><span>{{ t('trPage.howto2') }}</span><em>{{ t('trPage.howto2v') }}</em></p>
          <p><span>{{ t('trPage.howto3') }}</span><em>{{ t('trPage.howto3v') }}</em></p>
          <small>{{ t('trPage.howtoTip') }}</small>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.tr { min-width: 0; }
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
.lead { max-width: 44em; color: var(--text-secondary); }
.loading { margin-top: 18px; color: var(--text-muted); font-size: 13px; }

.warn-box {
  margin: 16px 0;
  padding: 14px 16px;
  border: 1px solid var(--warning);
  background: var(--warning-soft);
  border-radius: var(--radius);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.warn-box b { color: var(--text-primary); }
.warn-box p { margin: 0; flex: 1 1 260px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.65; }

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(220px, 1fr);
  gap: 18px;
  margin-top: 18px;
}
.grid.disabled { opacity: 0.55; pointer-events: none; }

.drop {
  border: 1px dashed var(--border);
  background: var(--bg-soft);
  padding: 48px 20px;
  text-align: center;
  cursor: pointer;
  border-radius: var(--radius);
}
.drop.on { border-color: var(--accent); background: var(--warning-soft); }
.drop-btns { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 14px; }

.queue, .card, .result {
  margin-top: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.queue header, .result header, .q-row, .card p {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.queue header, .q-row, .card, .result header { padding: 14px 16px; }
.q-row { border-top: 1px solid var(--border); flex-wrap: wrap; min-width: 0; }
.q-meta { min-width: 0; flex: 1 1 140px; }
.q-meta b { display: block; font-weight: 400; }
.q-meta span, .q-status, .count, small, .card em, .demo-note { color: var(--text-muted); font-size: 12px; }
.demo-note { margin: 10px 0 0; line-height: 1.65; }
.q-prog { width: 160px; }
.q-status.done { color: var(--success); }
.q-status.reading, .q-status.uploading { color: var(--accent); }

.ok, .ghost {
  border-radius: 1000px;
  padding: 8px 16px;
  font-size: 13px;
}
.ok { border: 1px solid var(--primary); background: var(--primary); color: #fff; }
.ghost { border: 1px solid var(--border); background: var(--bg-card); color: var(--text-primary); }
.ok:disabled, .ghost:disabled { opacity: 0.5; }
.small { padding: 5px 12px; font-size: 12px; }

.card { display: flex; flex-direction: column; gap: 10px; }
.card label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-muted); }
.card p { margin: 0; }
.card input[type="text"] {
  height: 36px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  width: 100%;
  padding: 0 10px;
  font-size: 13px;
}
.hint { margin: 0; font-size: 12px; color: var(--text-muted); line-height: 1.6; }

.result textarea {
  display: block;
  width: 100%;
  border: none;
  border-top: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 14px 16px;
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.85;
  resize: vertical;
  min-height: 160px;
}
.result textarea:focus { outline: none; }
.count { margin: 0; padding: 0 16px 12px; font-size: 12px; color: var(--text-muted); }

.act { margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; }
.err {
  margin: 12px 0 0;
  padding: 10px 14px;
  border: 1px solid var(--error);
  background: var(--error-soft);
  border-radius: var(--radius-sm);
  color: var(--error);
  font-size: 12.5px;
  line-height: 1.6;
}
.hidden-input { display: none; }

@media (max-width: 760px) {
  .grid { grid-template-columns: 1fr; }
  /* 单栏时把说明卡提到上传区之前，免得要点半天才看到「存入知识库」 */
  .grid > aside { order: -1; }
  .drop { padding: 32px 16px; }
  h2 { font-size: 26px; }
}
@media (max-width: 390px) {
  .q-prog, .q-status { width: 100%; }
  .drop-btns .ok, .drop-btns .ghost, .act .ok, .act .ghost { width: 100%; }
  h2 { font-size: 22px; }
}
</style>
