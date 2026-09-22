<script setup>
/**
 * App.vue —— study-liu Web 主界面
 *
 * 页面即「一条完整链路」的可视化：
 *   ① 输入课程名 + 选画像  →  ② Agent 流水线（Planner→Searcher→Writer→Reviewer）
 *   →  ③ 三栏结果（大纲 / 资源 / 计划）  →  ④ 导出 / 问答 / 日志回放
 *
 * 所有业务逻辑都在后端（复用 study-liu 桌面版的 core / agents / tools），
 * 前端只做展示与交互。
 */
import { computed, onMounted, ref, watch } from 'vue'
import AppHeader from './components/AppHeader.vue'
import WelcomeScreen from './components/WelcomeScreen.vue'
import PipelineStepper from './components/PipelineStepper.vue'
import CourseForm from './components/CourseForm.vue'
import ResultsGrid from './components/ResultsGrid.vue'
import ChatPanel from './components/ChatPanel.vue'
import TraceDrawer from './components/TraceDrawer.vue'
import StatusBar from './components/StatusBar.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import HistoryDialog from './components/HistoryDialog.vue'
import { usePlanStream } from './composables/usePlanStream'
import { api } from './api/client'

// ---------- 基础状态 ----------
const booted = ref(false)

// ---------- 首访欢迎层 ----------
// 首访（localStorage 无标记）显示 WelcomeScreen；深链（?course= / ?auto=1）不弹，
// 避免打断可分享的演示链接；?welcome=1 可强制重新打开（演示 / 截图用）。
function shouldShowWelcome() {
  try {
    const qs = new URLSearchParams(window.location.search)
    if (qs.get('welcome') === '1') return true
    if (qs.get('welcome') === '0') return false
    if (qs.get('course') || qs.get('auto') === '1') return false
    return !localStorage.getItem('zjxt.welcomed')
  } catch (_) {
    return false
  }
}
const showWelcome = ref(shouldShowWelcome())

function onWelcomeDone() {
  try {
    localStorage.setItem('zjxt.welcomed', '1')
  } catch (_) {
    /* 存不上也不阻塞进入 */
  }
  showWelcome.value = false
}

// 欢迎层显示期间锁住 body 滚动，避免底层工具界面跟着滚
watch(
  showWelcome,
  (v) => {
    document.body.style.overflow = v ? 'hidden' : ''
  },
  { immediate: true },
)

const mode = ref({})
const options = ref({ levels: [], daily_hours: [], goals: [] })
const suggestedDays = ref(7)
const traceFile = ref('')
const sourceDir = ref('')

const course = ref('')
const profile = ref({ level: '入门', daily_hours: '2h', goal: '兴趣', deadline: '' })
const useCache = ref(true)

// ---------- 弹窗 / 抽屉 ----------
const showSettings = ref(false)
/** 处于 LLM 模式但没配 Key —— 需要主动提示用户去填 */
const needsKey = ref(false)
const showHistory = ref(false)
const showTrace = ref(false)

// ---------- 状态栏 ----------
const statusText = ref('就绪')
const statusTone = ref('normal')

// ---------- Toast ----------
const toasts = ref([])
let toastId = 0
function notify(payload) {
  const id = ++toastId
  const item = {
    id,
    type: payload?.type || 'info',
    text: payload?.text || '',
  }
  toasts.value.push(item)
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 4200)
}

// ---------- 链路状态机 ----------
const stream = usePlanStream()
const {
  STAGES,
  status,
  steps,
  traces,
  traceError,
  result,
  meta,
  error,
  activeIndex,
  progress,
  usedFallback,
} = stream

const busy = computed(() => status.value === 'running')

// 把链路状态同步到状态栏
watch(status, (v) => {
  if (v === 'running') {
    statusTone.value = 'warn'
  } else if (v === 'error') {
    statusTone.value = 'error'
  } else if (v === 'done') {
    statusTone.value = 'success'
  } else {
    statusTone.value = 'normal'
  }
})

watch(
  () => result.value,
  (r) => {
    if (!r) return
    const head = r.from_cache ? '⚡ 命中缓存！' : '✓ 完成！'
    statusText.value = `${head}课程「${r.course}」方案已生成`
  },
)

watch(error, (e) => {
  if (e) statusText.value = `✗ 生成失败：${e}`
})

// ---------- 初始化 ----------
async function loadBootstrap() {
  try {
    const data = await api.bootstrap()
    mode.value = data.mode || {}
    options.value = data.options || options.value
    profile.value = { ...(data.profile || profile.value) }
    suggestedDays.value = data.suggested_days || 7
    sourceDir.value = data.source_dir || ''
    traceFile.value = data.trace_file || ''
    statusText.value = `就绪 · ${data.mode?.label || ''} ｜ 后端已挂载 study-liu 源码`
    // LLM 模式却没 Key：不主动提示的话，用户只能看着「LLM 模式」角标
    // 却不知道去哪儿填自己的 API Key（之前就是这样，体验很差）
    needsKey.value = !!data.mode && data.mode.mode !== 'mock' && !data.mode.has_key
    booted.value = true
  } catch (e) {
    statusTone.value = 'error'
    statusText.value = `后端未启动：${e.message}（请先运行 python server/api_server.py）`
    notify({ type: 'error', text: '无法连接后端，请在 study-liu-web 目录先启动 server' })
  }
}

onMounted(async () => {
  await loadBootstrap()

  // 支持深链：?course=机器学习&auto=1&level=进阶&daily_hours=4h&goal=考试&deadline=2026-10-10
  // 便于把「一条完整链路」直接做成可分享的演示链接，也方便自动化截图验证。
  const qs = new URLSearchParams(window.location.search)
  const qCourse = (qs.get('course') || '').trim()
  if (qs.get('level')) profile.value.level = qs.get('level')
  if (qs.get('daily_hours')) profile.value.daily_hours = qs.get('daily_hours')
  if (qs.get('goal')) profile.value.goal = qs.get('goal')
  if (qs.get('deadline') !== null) profile.value.deadline = qs.get('deadline') || ''
  if (qs.get('cache') === '0') useCache.value = false

  if (qCourse) {
    course.value = qCourse
    if (qs.get('auto') === '1') onGenerate(qCourse)
  }

  // 需要填 Key 时自动弹设置，别让用户在一堆按钮里找入口。
  // 可用 ?settings=0 关掉，?settings=1 强制打开；演示链接（auto=1）不打扰。
  const wantSettings = qs.get('settings')
  if (wantSettings === '1') {
    showSettings.value = true
  } else if (wantSettings !== '0' && needsKey.value && qs.get('auto') !== '1') {
    showSettings.value = true
    statusTone.value = 'warn'
    statusText.value = '⚠ 当前是 LLM 模式但还没填 API Key —— 请在这里填入你自己的 Key'
  }
})

// ---------- 交互 ----------
function onGenerate(name) {
  if (!name) {
    statusTone.value = 'warn'
    statusText.value = '⚠ 请先输入课程名'
    notify({ type: 'warn', text: '请先输入课程名' })
    return
  }
  course.value = name
  statusText.value = `⏳ 正在为「${name}」生成方案，链路执行中…`
  showTrace.value = false
  stream.generate(name, { ...profile.value }, useCache.value)
}

async function onProfileChange(p) {
  // ⚠️ 这里**绝对不能**再写回 `profile.value = p`。
  //
  // CourseForm 用 `watch(profile, ..., { deep: true })` 监听，回调里
  // `emit('profile-change', { ...profile.value })` 每次都是一个**新对象**。
  // 若这里把新对象写回 profile，子组件的 model 值身份就变了，
  // 深度监听会再次触发 → 再次 emit → 再次写回……形成无限渲染循环。
  //
  // 后果：页面首屏能渲染出来，但 JS 线程随即被 100% 占满，
  // 表现为「所有按钮点了都没反应」+ CPU 飙升。
  //
  // 画像本来就已经通过 `v-model:profile` 双向同步过了，这里只需保存。
  try {
    const res = await api.saveProfile(p)
    suggestedDays.value = res.suggested_days || suggestedDays.value
  } catch (_) {
    /* 画像保存失败不阻断主流程 */
  }
}

function copyText(text, label) {
  if (!text) return
  const done = () => notify({ type: 'success', text: `${label}已复制到剪贴板` })
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done))
  } else {
    fallbackCopy(text, done)
  }
}

function fallbackCopy(text, done) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand('copy')
    done()
  } catch (_) {
    notify({ type: 'error', text: '复制失败，请手动选择文本' })
  }
  document.body.removeChild(ta)
}

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

async function onExport() {
  if (!result.value) return
  try {
    const res = await api.exportMarkdown(result.value.course, null)
    download(res.filename || '学习方案.md', res.markdown)
    notify({ type: 'success', text: `已导出 ${res.filename}` })
  } catch (e) {
    notify({ type: 'error', text: `导出失败：${e.message}` })
  }
}

function onCopyOutline() {
  const list = (result.value?.outline || [])
    .map((c, i) => `${i + 1}. ${c}`)
    .join('\n')
  copyText(`【${result.value?.course}】课程大纲\n${list}`, '大纲')
}

function onCopyPlan() {
  const list = (result.value?.plan_items || [])
    .map((d) => `Day ${d.day}｜${d.title}${d.chapters?.length ? '（' + d.chapters.join(' / ') + '）' : ''}`)
    .join('\n')
  copyText(`【${result.value?.course}】学习计划\n${list}`, '计划')
}

async function openTrace() {
  showTrace.value = true
  await stream.refreshTrace()
}

function onLoadHistory(payload) {
  showHistory.value = false
  if (!payload?.ok) return
  // 把历史方案回填到三栏（不走流水线，因此节点全部标记完成）
  stream.reset()
  for (const s of STAGES) stream.steps[s.key].status = 'done'
  result.value = payload
  stream.status.value = 'done'
  course.value = payload.course
  statusText.value = `📜 已载入历史方案：${payload.course}（大纲 ${payload.stats.outline} 章 / 计划 ${payload.stats.plan} 天）`
  statusTone.value = 'success'
  notify({ type: 'success', text: `已载入「${payload.course}」的历史方案` })
}

function onSettingsSaved(newMode) {
  if (newMode) {
    mode.value = newMode
    // 保存后重新判断是否仍缺 Key，角标高亮才会及时消失
    needsKey.value = newMode.mode !== 'mock' && !newMode.has_key
  }
  notify({ type: 'success', text: '运行模式已更新' })
}

const isMockMode = computed(() => mode.value?.mode === 'mock')

/**
 * 降级提示分两种语气（与桌面版逻辑一致，但 Web 上更直观）：
 * - Mock 模式：本来就是内置数据，用中性提示即可，不要吓用户；
 * - LLM 模式：大模型调用失败走了模板，必须橙色告警，明确说明「这不是大模型生成的」。
 */
const degradedBanner = computed(() => {
  const d = result.value?.degraded
  if (!d) return null
  const agents = (d.agents || []).join(' / ')
  if (isMockMode.value) {
    return {
      tone: 'info',
      icon: '📦',
      title: '当前为 Mock 模式，方案由内置模板生成',
      detail: `兜底节点：${agents}。章节来自课程分类模板，资源来自内置 20 门课程资源库，不消耗任何 API 额度。`,
    }
  }
  return {
    tone: 'warn',
    icon: '⚠',
    title: '本次方案并非大模型生成',
    detail: `${agents} 走了内置模板兜底（原因：${d.error}）。请检查 API Key / 网络 / 账户余额后重新生成。`,
  }
})
</script>

<template>
  <div class="app">
    <!-- 首访欢迎层：关闭后进入下方工具界面 -->
    <WelcomeScreen v-if="showWelcome" @start="onWelcomeDone" />

    <AppHeader
      :mode="mode"
      :has-result="!!result"
      :busy="busy"
      :needs-key="needsKey"
      @export="onExport"
      @open-trace="openTrace"
      @open-settings="showSettings = true"
      @open-history="showHistory = true"
    />

    <main class="main">
      <!-- ① 课程名 + 画像 -->
      <CourseForm
        v-model:course="course"
        v-model:profile="profile"
        :options="options"
        :busy="busy"
        :suggested-days="suggestedDays"
        @generate="onGenerate"
        @profile-change="onProfileChange"
      />

      <!-- 生成选项 -->
      <div class="opts">
        <label class="check">
          <input v-model="useCache" type="checkbox" :disabled="busy" />
          允许命中结果缓存（同一课程 + 同一画像 24 小时内不重复调用大模型）
        </label>
        <span v-if="usedFallback" class="chip chip-warn">
          当前使用非流式模式（SSE 不可用，已自动降级）
        </span>
        <span v-if="sourceDir" class="src-path" :title="sourceDir">
          业务逻辑来源：{{ sourceDir }}
        </span>
      </div>

      <!-- ② Agent 流水线 -->
      <PipelineStepper
        :steps="steps"
        :status="status"
        :active-index="activeIndex"
        :progress="progress"
        :meta="meta"
      />

      <!-- 降级 / 错误提示 -->
      <div v-if="degradedBanner" class="banner" :class="degradedBanner.tone">
        <span class="b-ico">{{ degradedBanner.icon }}</span>
        <div>
          <b>{{ degradedBanner.title }}</b>
          <p>{{ degradedBanner.detail }}</p>
        </div>
      </div>

      <div v-if="error" class="banner err">
        <span class="b-ico">✗</span>
        <div>
          <b>链路执行失败</b>
          <p>{{ error }}</p>
        </div>
      </div>

      <!-- ③ 三栏结果 -->
      <ResultsGrid
        :result="result"
        :loading="busy"
        @copy-outline="onCopyOutline"
        @copy-plan="onCopyPlan"
      />

      <!-- ④ 课程问答 -->
      <ChatPanel
        :course-context="result?.course || course"
        :mode="mode"
        @notify="notify"
      />
    </main>

    <!-- 抽屉 / 弹窗 -->
    <TraceDrawer
      :open="showTrace"
      :lines="traces"
      :trace-file="traceFile"
      :error="traceError"
      @close="showTrace = false"
      @refresh="stream.refreshTrace()"
    />

    <SettingsDialog
      :open="showSettings"
      :mode="mode"
      @close="showSettings = false"
      @saved="onSettingsSaved"
    />

    <HistoryDialog
      :open="showHistory"
      @close="showHistory = false"
      @load="onLoadHistory"
      @notify="notify"
    />

    <!-- Toast -->
    <div class="toasts">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="`t-${t.type}`">
        {{ t.text }}
      </div>
    </div>

    <StatusBar
      :text="statusText"
      :tone="statusTone"
      :stats="result?.stats || null"
      :duration="result?.duration_ms || 0"
      :from-cache="!!result?.from_cache"
    />
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  padding-bottom: 44px;
}

.main {
  max-width: 1360px;
  margin: 0 auto;
  padding: 16px 26px 26px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.opts {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 0 4px;
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
}

.check input {
  accent-color: var(--primary);
  width: 14px;
  height: 14px;
}

.src-path {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  max-width: 46%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.banner {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 12.5px;
  line-height: 1.65;
}

.banner b {
  font-size: 13px;
}

.banner p {
  margin-top: 2px;
  opacity: 0.9;
}

.banner.warn {
  background: var(--warning-soft);
  border: 1px solid #fde68a;
  color: #92400e;
}

.banner.info {
  background: var(--bg-disabled);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.banner.err {
  background: var(--error-soft);
  border: 1px solid #fecaca;
  color: #991b1b;
}

.b-ico {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.7);
}

/* ---------- Toast ---------- */
.toasts {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 340px;
}

.toast {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  font-weight: 600;
  box-shadow: var(--shadow);
  animation: fade-up 0.22s ease both;
  background: #fff;
  border-left: 4px solid var(--primary);
  color: var(--text-secondary);
}

.toast.t-success {
  border-left-color: var(--success);
}

.toast.t-warn {
  border-left-color: var(--warning);
}

.toast.t-error {
  border-left-color: var(--error);
}

@media (max-width: 860px) {
  .main {
    padding: 14px 16px 22px;
  }
  .src-path {
    display: none;
  }
}
</style>
