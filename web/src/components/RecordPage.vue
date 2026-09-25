<script setup>
/**
 * RecordPage —— 课堂录音与转写
 *
 * 能力分三档，界面按实际能力渲染（不假装能用）：
 *   ① 完整：安全上下文 + MediaRecorder + SpeechRecognition → 边录边出文字
 *   ② 半能：安全上下文 + MediaRecorder，但没有识别引擎 → 只录音 + 手动补文字
 *   ③ 不可用：非安全上下文（http://IP）→ 浏览器直接拒绝麦克风，
 *      提示原因，并给「粘贴整理」通道，页面在任何环境都有用
 *
 * ⚠️ 为什么会有第 ③ 档：getUserMedia 与 webkitSpeechRecognition 都要求
 *    secure context（https 或 localhost）。线上是 http://47.106.76.244，
 *    属于非安全上下文 —— 这不是代码能绕过的浏览器策略。
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

const emit = defineEmits(['back', 'go-course', 'notify'])
const { t } = useI18n()

// ---------- 能力探测 ----------
const isSecure = typeof window !== 'undefined' && window.isSecureContext === true
const hasRecorder = typeof window !== 'undefined' && typeof window.MediaRecorder !== 'undefined'
const SR = typeof window !== 'undefined'
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null
const hasSpeech = !!SR

const canRecord = isSecure && hasRecorder
const canTranscribe = canRecord && hasSpeech

const capability = computed(() => {
  if (!isSecure) return 'insecure'
  if (!hasRecorder) return 'no-recorder'
  if (!hasSpeech) return 'no-speech'
  return 'full'
})

const capText = computed(() => t({
  full: 'cap.full',
  'no-speech': 'cap.noSpeech',
  'no-recorder': 'cap.noRecorder',
  insecure: 'cap.insecure',
}[capability.value]))

// ---------- 录音状态 ----------
const recording = ref(false)
const elapsed = ref(0)
const level = ref(0)
const audioUrl = ref('')
const audioBlob = ref(null)
const errorText = ref('')

let mediaStream = null
let recorder = null
let chunks = []
let timer = null
let audioCtx = null
let analyser = null
let rafId = 0

// ---------- 转写文本 ----------
const transcript = ref('')
const interim = ref('')
let recognition = null
let recognitionWanted = false

const fullText = computed(() => {
  const a = transcript.value.trim()
  const b = interim.value.trim()
  if (!a) return b
  return b ? `${a}\n${b}` : a
})

const mmss = computed(() => {
  const s = elapsed.value
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})

function fmtSize(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

// ---------- 语音识别 ----------
function startRecognition() {
  if (!hasSpeech || recognition) return
  try {
    recognition = new SR()
  } catch (_) {
    recognition = null
    return
  }
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true

  recognition.onresult = (e) => {
    let finalText = ''
    let interimText = ''
    for (let i = e.resultIndex; i < e.results.length; i += 1) {
      const r = e.results[i]
      if (r.isFinal) finalText += r[0].transcript
      else interimText += r[0].transcript
    }
    if (finalText) {
      transcript.value = (transcript.value ? transcript.value + '\n' : '') + finalText.trim()
    }
    interim.value = interimText
  }

  recognition.onerror = (e) => {
    // not-allowed / service-not-allowed 多半是没权限或网络到不了识别服务
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      errorText.value = '语音识别被拒绝（可能是没给麦克风权限，或当前网络到不了识别服务）'
    } else if (e.error === 'network') {
      errorText.value = '语音识别服务连不上（浏览器内置识别依赖外部服务，国内网络可能不稳定）'
    }
    recognitionWanted = false
  }

  recognition.onend = () => {
    // 浏览器会在静默后自动结束，只要还在录就重新挂上
    if (recognitionWanted && recording.value) {
      try { recognition.start() } catch (_) { /* 已在运行 */ }
    }
  }

  recognitionWanted = true
  try { recognition.start() } catch (_) { /* 忽略重复启动 */ }
}

function stopRecognition() {
  recognitionWanted = false
  if (recognition) {
    try { recognition.stop() } catch (_) { /* 已停止 */ }
    recognition = null
  }
  interim.value = ''
}

// ---------- 电平表 ----------
function startMeter(stream) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext
    audioCtx = new Ctx()
    const src = audioCtx.createMediaStreamSource(stream)
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 512
    src.connect(analyser)
    const buf = new Uint8Array(analyser.frequencyBinCount)

    const tick = () => {
      if (!analyser) return
      analyser.getByteTimeDomainData(buf)
      let peak = 0
      for (let i = 0; i < buf.length; i += 1) {
        peak = Math.max(peak, Math.abs(buf[i] - 128))
      }
      level.value = Math.min(100, Math.round((peak / 128) * 100))
      rafId = requestAnimationFrame(tick)
    }
    tick()
  } catch (_) {
    /* 电平只是氛围，拿不到就算了 */
  }
}

function stopMeter() {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = 0
  analyser = null
  if (audioCtx) {
    try { audioCtx.close() } catch (_) { /* 忽略 */ }
    audioCtx = null
  }
  level.value = 0
}

// ---------- 录音主流程 ----------
async function start() {
  errorText.value = ''
  if (!canRecord) return

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    errorText.value = e?.name === 'NotAllowedError'
      ? '麦克风权限被拒绝，请在浏览器地址栏左侧的权限设置里允许'
      : `无法打开麦克风：${e.message || e.name}`
    return
  }

  chunks = []
  try {
    recorder = new MediaRecorder(mediaStream)
  } catch (e) {
    errorText.value = `录音器初始化失败：${e.message}`
    return
  }

  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data)
  }
  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
    audioBlob.value = blob
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
    audioUrl.value = URL.createObjectURL(blob)
  }

  recorder.start()
  recording.value = true
  elapsed.value = 0
  timer = setInterval(() => { elapsed.value += 1 }, 1000)

  startMeter(mediaStream)
  startRecognition()
}

function stop() {
  recording.value = false
  if (timer) { clearInterval(timer); timer = null }
  stopRecognition()
  stopMeter()

  if (recorder && recorder.state !== 'inactive') {
    try { recorder.stop() } catch (_) { /* 忽略 */ }
  }
  recorder = null

  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop())
    mediaStream = null
  }
}

function reset() {
  stop()
  transcript.value = ''
  interim.value = ''
  errorText.value = ''
  elapsed.value = 0
  audioBlob.value = null
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audioUrl.value = ''
}

onBeforeUnmount(reset)

// ---------- 落地：入库 / 下载 ----------
const saving = ref(false)
const saveTitle = ref('')

async function saveToKnowledge() {
  const text = fullText.value.trim()
  if (!text) {
    emit('notify', { type: 'error', text: '还没有可保存的内容' })
    return
  }
  saving.value = true
  try {
    const title = saveTitle.value.trim() || `课堂录音转写 ${new Date().toLocaleString('zh-CN')}`
    await api.knowledgeCreate({
      title,
      content: text,
      tags: ['课堂录音', '转写'],
    })
    emit('notify', { type: 'success', text: `已存入知识库：${title}` })
  } catch (e) {
    emit('notify', { type: 'error', text: `存入失败：${e.message}` })
  } finally {
    saving.value = false
  }
}

function downloadText() {
  const text = fullText.value.trim()
  if (!text) return
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `课堂转写-${new Date().toISOString().slice(0, 10)}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function downloadAudio() {
  if (!audioBlob.value) return
  const a = document.createElement('a')
  a.href = audioUrl.value
  a.download = `课堂录音-${new Date().toISOString().slice(0, 10)}.webm`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>

<template>
  <section class="rp">
    <header class="rp-head">
      <div>
        <p class="kicker">Lecture capture</p>
        <h1>{{ t('page.recordTitle') }}</h1>
        <p class="sub">{{ t('recordPage.2') }}</p>
      </div>
      <div class="head-actions">
        <button type="button" class="btn btn-ghost" @click="emit('back')">{{ t('recordPage.3') }}</button>
      </div>
    </header>

    <!-- 能力状态 -->
    <div class="cap" :class="`cap-${capability}`">
      <span class="cap-dot" />
      <div>
        <b>{{ capText }}</b>
        <p v-if="capability === 'insecure'" class="cap-detail">{{ t('recordPage.4') }}<code>https</code> 或 <code>localhost</code>{{ t('recordPage.5') }}<code>http</code>{{ t('recordPage.6') }}<code>http://127.0.0.1:5173</code>{{ t('recordPage.7') }}</p>
        <p v-else-if="capability === 'no-speech'" class="cap-detail">{{ t('recordPage.8') }}</p>
      </div>
    </div>

    <!-- 录音区 -->
    <div class="rec-card">
      <div class="rec-main">
        <button
          type="button"
          class="rec-btn"
          :class="{ on: recording }"
          :disabled="!canRecord"
          :title="canRecord ? '' : t('recordPageX.1')"
          @click="recording ? stop() : start()"
        >
          <span class="rec-ico">{{ recording ? '■' : '●' }}</span>
          <span>{{ recording ? t('recordPageX.2') : t('recordPageX.3') }}</span>
        </button>

        <div class="rec-meta">
          <div class="timer">{{ mmss }}</div>
          <div class="meter" :class="{ live: recording }">
            <i :style="{ width: level + '%' }" />
          </div>
          <div class="rec-hint">
            {{ recording
              ? (canTranscribe ? t('recordPageX.4') : t('recordPageX.5'))
              : t('recordPageX.6') }}
          </div>
        </div>
      </div>

      <p v-if="errorText" class="rec-err">{{ errorText }}</p>

      <div v-if="audioUrl" class="playback">
        <div class="pb-label">{{ t('recordPage.9') }}</div>
        <audio :src="audioUrl" controls preload="metadata" />
        <div class="pb-actions">
          <span class="pb-size">{{ fmtSize(audioBlob?.size) }}</span>
          <button type="button" class="btn btn-ghost sm" @click="downloadAudio">{{ t('recordPage.10') }}</button>
          <button type="button" class="btn btn-ghost sm" @click="reset">{{ t('recordPage.11') }}</button>
        </div>
      </div>
    </div>

    <!-- 转写区 -->
    <div class="txt-card">
      <div class="txt-head">
        <h2>{{ t('recordPage.12') }}</h2>
        <div class="txt-actions">
          <span class="cnt">{{ fullText.length }} 字</span>
          <button
            type="button"
            class="btn btn-ghost sm"
            :disabled="!fullText"
            @click="transcript = ''; interim = ''"
          >{{ t('recordPage.13') }}</button>
        </div>
      </div>

      <div v-if="interim" class="interim">正在识别：{{ interim }}</div>

      <textarea
        v-model="transcript"
        class="txt-area"
        rows="12"
        :placeholder="canTranscribe
          ? t('recordPageX.7')
          : t('recordPageX.8')"
      />

      <div class="save-row">
        <input
          v-model="saveTitle"
          class="save-title"
          type="text"
          :placeholder="t('recordPage.1')"
        />
        <button type="button" class="btn btn-primary" :disabled="saving || !fullText" @click="saveToKnowledge">
          {{ saving ? t('recordPageX.9') : t('recordPageX.10') }}
        </button>
        <button type="button" class="btn btn-ghost" :disabled="!fullText" @click="downloadText">{{ t('recordPage.14') }}</button>
      </div>

      <p class="tip">{{ t('recordPage.15') }}</p>
    </div>
  </section>
</template>

<style scoped>
.rp {
  max-width: 900px;
  margin: 0 auto;
  padding: 4px 0 40px;
}

.rp-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.kicker {
  font-family: var(--font-serif);
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--primary);
}

.rp-head h1 {
  margin: 4px 0 6px;
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 400;
  color: var(--text-primary);
}

.sub {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 560px;
  line-height: 1.7;
}

/* ---------- 能力提示 ---------- */
.cap {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border-radius: 10px;
  padding: 13px 16px;
  margin-bottom: 14px;
  font-size: 13px;
  line-height: 1.7;
  border: 1px solid var(--border);
  background: var(--bg-card);
}

.cap-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 7px;
  background: var(--text-faint);
}

/* 状态色一律走变量 —— 写死的浅底在暗色主题下会非常突兀 */
.cap-full { border-color: var(--border); border-left: 3px solid var(--success); background: var(--success-soft); color: var(--text-primary); }
.cap-full .cap-dot { background: var(--success); }

.cap-no-speech, .cap-no-recorder { border-color: var(--border); border-left: 3px solid var(--warning); background: var(--warning-soft); color: var(--text-primary); }
.cap-no-speech .cap-dot, .cap-no-recorder .cap-dot { background: var(--warning); }

.cap-insecure { border-color: var(--border); border-left: 3px solid var(--error); background: var(--error-soft); color: var(--text-primary); }
.cap-insecure .cap-dot { background: var(--error); }

.cap-detail {
  margin: 5px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.cap code {
  font-family: var(--font-mono);
  font-size: 11.5px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0 4px;
}

/* ---------- 录音卡 ---------- */
.rec-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 22px;
  margin-bottom: 14px;
}

.rec-main {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.rec-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  border: 1px solid var(--border-strong);
  background: var(--bg-card);
  color: var(--text-primary);
  border-radius: 999px;
  padding: 13px 26px;
  font-size: 14.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.rec-btn:hover:not(:disabled) {
  border-color: var(--primary-light);
}

.rec-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.rec-btn.on {
  background: var(--error-soft);
  border-color: var(--error);
  color: var(--error);
}

.rec-ico {
  font-size: 13px;
  line-height: 1;
  color: var(--primary);
}

.rec-btn.on .rec-ico {
  color: #dc2626;
}

.rec-meta {
  flex: 1 1 240px;
  min-width: 0;
}

.timer {
  font-family: var(--font-mono);
  font-size: 26px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  line-height: 1.2;
}

.meter {
  height: 6px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  overflow: hidden;
  margin: 7px 0 6px;
}

.meter i {
  display: block;
  height: 100%;
  width: 0;
  background: var(--text-faint);
  transition: width 0.08s linear;
}

.meter.live i {
  background: var(--primary);
}

.rec-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.rec-err {
  margin: 14px 0 0;
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--error-soft);
  border: 1px solid var(--error);
  color: var(--error);
  font-size: 12.5px;
}

/* ---------- 回放 ---------- */
.playback {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.pb-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 7px;
}

.playback audio {
  width: 100%;
  height: 36px;
}

.pb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 9px;
}

.pb-size {
  font-size: 11.5px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  margin-right: auto;
}

/* ---------- 转写区 ---------- */
.txt-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px 20px;
}

.txt-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.txt-head h2 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 400;
  color: var(--text-primary);
}

.txt-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cnt {
  font-size: 11.5px;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}

.interim {
  font-size: 12.5px;
  color: var(--text-muted);
  background: var(--bg-soft);
  border: 1px dashed var(--border-strong);
  border-radius: 8px;
  padding: 8px 11px;
  margin-bottom: 10px;
}

.txt-area {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.85;
  font-family: inherit;
  color: var(--text-primary);
  background: var(--bg-card);
  resize: vertical;
}

.txt-area:focus {
  outline: none;
  border-color: var(--primary-light);
}

.save-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.save-title {
  flex: 1 1 260px;
  min-width: 180px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 11px;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-card);
}

.save-title:focus {
  outline: none;
  border-color: var(--primary-light);
}

.tip {
  margin: 11px 0 0;
  font-size: 11.5px;
  color: var(--text-faint);
  line-height: 1.7;
}

.btn.sm {
  padding: 5px 11px;
  font-size: 12px;
}

@media (max-width: 620px) {
  .rec-main { gap: 14px; }
  .rec-btn { width: 100%; justify-content: center; }
}
</style>
