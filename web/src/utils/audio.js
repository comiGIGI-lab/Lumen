/**
 * 浏览器端音频 → 16kHz 单声道 16bit PCM。
 *
 * 为什么这层放在浏览器而不是服务器：
 *   服务器（1.6G 内存的 ECS）**没有装 ffmpeg**，装一套要拖进上百 MB 依赖。
 *   而浏览器的 Web Audio API 自带解码器，mp3 / m4a / aac / webm / ogg / wav
 *   都能直接解，并且 OfflineAudioContext 指定 16000 采样率时
 *   decodeAudioData 会**自动重采样并混成单声道** —— 零依赖、零安装。
 *
 * 为什么不用 getUserMedia / MediaRecorder 录音：
 *   那两个 API 要求「安全上下文」（https 或 localhost）。线上是
 *   http://47.106.76.244，浏览器会直接拒绝，这正是 2026-09-26 把录音功能
 *   整体摘掉的原因。而 <input type="file"> 不受这个限制 —— 手机端加 capture
 *   属性还能直接唤起系统录音机，录完当文件交回来。
 */

/** 16k * 16bit * 单声道 = 每秒 32000 字节，与后端 asr.SAMPLE_RATE 对齐 */
export const SAMPLE_RATE = 16000

/** 单个原始文件体积上限。比解码后的 PCM 上限更早拦住，避免浏览器解码时爆内存。 */
export const MAX_FILE_BYTES = 60 * 1024 * 1024

function AudioCtx() {
  return typeof window === 'undefined'
    ? null
    : window.OfflineAudioContext || window.webkitOfflineAudioContext || null
}

/** 浏览器是否具备解码能力（老 Safari / 极简内嵌浏览器会没有） */
export function canDecodeAudio() {
  return !!AudioCtx()
}

/**
 * 只读取时长，不做完整解码。
 *
 * 为什么需要：decodeAudioData 会把整段音频解成 Float32 常驻内存
 * （48k 立体声 20 分钟 ≈ 460MB）。先问一下时长，超限就直接拒掉，
 * 既省时间也不会把手机浏览器搞崩。
 *
 * @returns {Promise<number>} 秒；读不出来时返回 NaN（不阻塞后续流程）
 */
export function probeDuration(file) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') return resolve(NaN)
    const url = URL.createObjectURL(file)
    const el = document.createElement('audio')
    let done = false
    const finish = (v) => {
      if (done) return
      done = true
      URL.revokeObjectURL(url)
      el.removeAttribute('src')
      resolve(v)
    }
    // 有些容器（容器头里没写时长）读不出 loadedmetadata，给个超时兜底
    const timer = setTimeout(() => finish(NaN), 4000)
    el.addEventListener('loadedmetadata', () => {
      clearTimeout(timer)
      const d = el.duration
      finish(Number.isFinite(d) && d > 0 ? d : NaN)
    })
    el.addEventListener('error', () => {
      clearTimeout(timer)
      finish(NaN)
    })
    el.preload = 'metadata'
    el.src = url
  })
}

/** 读文件为 ArrayBuffer，带真实进度（FileReader 支持 onprogress） */
function readFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onprogress = (e) => {
      if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total)
    }
    fr.onload = () => resolve(fr.result)
    fr.onerror = () => reject(new Error('读取文件失败，可能文件已损坏或无权限'))
    fr.readAsArrayBuffer(file)
  })
}

/** 线性插值重采样。仅在浏览器没有按 16k 给我们结果时的兜底。 */
function resampleTo16k(data, fromRate) {
  if (fromRate === SAMPLE_RATE) return data
  const ratio = fromRate / SAMPLE_RATE
  const n = Math.max(1, Math.floor(data.length / ratio))
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const pos = i * ratio
    const i0 = Math.floor(pos)
    const i1 = Math.min(i0 + 1, data.length - 1)
    const frac = pos - i0
    out[i] = data[i0] * (1 - frac) + data[i1] * frac
  }
  return out
}

/**
 * 把任意浏览器可解码的音频文件转成 16k 单声道 Int16 小端 PCM。
 *
 * @param {File} file
 * @param {object} [opts]
 *   onProgress —— (0~1) 读取文件的进度；解码阶段无法上报，调用方展示为不确定态
 * @returns {Promise<{pcm: Int16Array, duration: number, sampleRate: number}>}
 */
export async function decodeToPcm16k(file, { onProgress } = {}) {
  const Ctx = AudioCtx()
  if (!Ctx) throw new Error('当前浏览器不支持音频解码，请改用 Chrome / Edge / Safari')

  const raw = await readFile(file, onProgress)
  if (!raw || !raw.byteLength) throw new Error('文件是空的')

  let audio
  try {
    // numOfChannels=1 / length=1 —— 只为拿一个 16k 的解码上下文，不真的渲染
    const ctx = new Ctx(1, 1, SAMPLE_RATE)
    audio = await ctx.decodeAudioData(raw)
  } catch (e) {
    throw new Error(
      '这个音频格式浏览器解不开（常见于微信的 .amr、以及加密的 .m4p）。' +
        '请转成 mp3 / m4a / wav 再试。'
    )
  }

  const src = audio.getChannelData(0) // decodeAudioData 已按上下文采样率重采样
  const data = audio.sampleRate === SAMPLE_RATE ? src : resampleTo16k(src, audio.sampleRate)

  const pcm = new Int16Array(data.length)
  for (let i = 0; i < data.length; i++) {
    // 夹到 [-1, 1] 再映射：越界样本直接转换会回绕成刺耳的爆音
    let v = data[i]
    if (v > 1) v = 1
    else if (v < -1) v = -1
    pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff
  }

  return { pcm, duration: pcm.length / SAMPLE_RATE, sampleRate: SAMPLE_RATE }
}
